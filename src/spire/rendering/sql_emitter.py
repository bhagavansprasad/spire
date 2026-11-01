"""SQL emitter — a deterministic projection of a Plan into Fusion-DB SQL.

Pure function of (plan, overlay). No LLM, no DB, no side effects. See
docs/design/SQL_OVERLAY_POC.md for scope and the assumptions policy.

Usage:
    from spire.rendering.sql_emitter import emit_sql
    statements = emit_sql(plan)               # uses OVERLAY by default
    statements = emit_sql(plan, my_overlay)   # or a custom overlay

Statement shape:
    [-- Step N: <tool> (<shape>)]   ← header comment, when applicable
    SELECT ... ;
    <blank line>
    -- ASSUMPTION [key]: text
    -- ASSUMPTION [key]: text

The SQL body ends with its semicolon. Assumption lines follow as a
separate block; they are commentary and are not part of the statement.
"""

from __future__ import annotations

from typing import Any, Iterable

from spire.executor.executor import ITERATION_SENTINEL
from spire.kg.sql_overlay import (
    OVERLAY,
    FilterSpec,
    Overlay,
)


def emit_sql(plan: Iterable[Any], overlay: Overlay = OVERLAY) -> list[str]:
    """Return one SQL string per Plan step, in order."""
    return [_emit_step(step, overlay) for step in plan]


def _emit_step(step: Any, overlay: Overlay) -> str:
    # Tools in `not_expressible` cannot be reduced to one SELECT (multi-
    # resource reconciliation, Python-side joins that are not equivalent
    # to a single query). They are declared covered for the guardrail
    # invariant; the emitter prints an explicit comment rather than a
    # fake SELECT that would return wrong rows.
    if step.tool_name in overlay.not_expressible:
        return (
            f"-- Step {step.step_id}: {step.tool_name}\n"
            f"-- (not expressible as one SELECT — this tool composes "
            f"multiple resources into a single record; see "
            f"docs/design/SQL_OVERLAY_COMPLETENESS.md §7)"
        )

    # Aggregation tools emit a GROUP BY query. The spec carries the
    # base entity, the column to group on, and the measure template.
    # Selection here precedes tool_to_entity: a tool appears in one
    # dispatch table or the other, never both.
    agg_spec = overlay.aggregations.get(step.tool_name)
    if agg_spec is not None:
        return _emit_aggregation_step(step, agg_spec, overlay)

    entity_name = overlay.tool_to_entity.get(step.tool_name)
    if entity_name is None:
        return (
            f"-- Step {step.step_id}: {step.tool_name} "
            f"(no overlay entity for this tool — SQL not emitted)"
        )
    entity = overlay.entities[entity_name]

    select_list = ",\n       ".join(
        f"{a}.{c}" for a, c in entity.select_columns
    )
    from_line = f"FROM {entity.fusion_table} {entity.alias}"
    joins: list[str] = list(entity.base_joins)
    where: list[str] = []
    assumptions: list[str] = []

    # Iterating steps: the primary arg is $iteration_value. Handled in
    # the per-arg loop below via FilterSpec, same as any other arg.
    parameterized = step.iterate_over is not None

    for arg_name, arg_value in step.tool_args.items():
        if arg_name == "include_addresses":
            if arg_value:
                _maybe_add_join(
                    ("Supplier", "Address"), joins, assumptions, overlay
                )
            continue

        if arg_value == ITERATION_SENTINEL:
            # Route the sentinel through its FilterSpec exactly as the
            # non-iterating path does. The template's {value} slot is
            # filled with a bind placeholder, not a literal, because the
            # actual value comes from the parent step's output at
            # execution time.
            fspec = overlay.filters.get((step.tool_name, arg_name))
            if fspec is None:
                where.append(
                    f"-- unmapped iteration arg: {arg_name}"
                )
                continue
            if fspec.requires_join is not None:
                _maybe_add_join(
                    fspec.requires_join, joins, assumptions, overlay
                )
            where.append(
                fspec.predicate_template.format(
                    alias=entity.alias, value=":iteration_value"
                )
            )
            if fspec.assumption:
                assumptions.append(fspec.assumption)
            continue

        fspec = overlay.filters.get((step.tool_name, arg_name))
        if fspec is None:
            where.append(f"-- unmapped tool_arg: {arg_name}={arg_value!r}")
            continue

        # Pull in any join the filter's predicate depends on.
        if fspec.requires_join is not None:
            _maybe_add_join(
                fspec.requires_join, joins, assumptions, overlay
            )

        sql_value = _resolve_value(fspec, arg_value, overlay)
        if sql_value is None:
            where.append(
                f"-- unresolved literal for {arg_name}={arg_value!r} "
                f"(vocab_kind={fspec.vocab_kind})"
            )
            if fspec.assumption:
                assumptions.append(fspec.assumption)
            continue

        where.append(
            fspec.predicate_template.format(
                alias=entity.alias, value=sql_value
            )
        )
        if fspec.assumption:
            assumptions.append(fspec.assumption)

    # ── Build SQL body ─────────────────────────────────────────────
    body_lines: list[str] = [f"SELECT {select_list}", from_line]
    body_lines.extend(joins)
    if where:
        if len(where) == 1:
            body_lines.append(f"WHERE {where[0]}")
        else:
            body_lines.append("WHERE " + "\n  AND ".join(where))
    sql_body = "\n".join(body_lines) + ";"

    # ── Build assumption block ─────────────────────────────────────
    assumption_lines: list[str] = []
    seen: set[str] = set()
    for a in assumptions:
        if a in seen:
            continue
        seen.add(a)
        text = overlay.assumptions.get(a, a)
        assumption_lines.append(f"-- ASSUMPTION [{a}]: {text}")

    if entity_name == "Supplier" and "party_type_not_filtered" not in seen:
        assumption_lines.append(
            f"-- ASSUMPTION [party_type_not_filtered]: "
            f"{overlay.assumptions['party_type_not_filtered']}"
        )

    # ── Compose ────────────────────────────────────────────────────
    parts: list[str] = []
    if parameterized:
        keep = (
            "keep parents where this returns rows"
            if step.filter_source_when_nonempty
            else "filter source by emptiness"
            if step.filter_source_when_empty
            else "iterating"
        )
        parts.append(f"-- Step {step.step_id}: {step.tool_name} ({keep})")
    elif step.step_id > 1 or step.tool_name != "search_suppliers":
        parts.append(f"-- Step {step.step_id}: {step.tool_name}")

    parts.append(sql_body)
    if assumption_lines:
        parts.append("")
        parts.extend(assumption_lines)

    return "\n".join(parts)


def _maybe_add_join(
    key: tuple[str, str],
    joins: list[str],
    assumptions: list[str],
    overlay: Overlay,
) -> None:
    """Add the join clause for ``key`` if not already present. Also pulls
    the join's assumption, if any."""
    join_spec = overlay.joins.get(key)
    if join_spec is None:
        return
    if join_spec.join_clause in joins:
        return
    joins.append(join_spec.join_clause)
    if join_spec.assumption:
        assumptions.append(join_spec.assumption)


def _resolve_value(
    fspec: FilterSpec, raw: Any, overlay: Overlay
) -> str | None:
    key = str(raw)
    if fspec.value_map is not None:
        return fspec.value_map.get(key)
    if fspec.vocab_kind is not None:
        return overlay.literals.get((fspec.vocab_kind, key))
    safe = key.replace("'", "''")
    return f"'{safe}'"


def _qualify_measure(template: str, alias: str) -> str:
    """Prefix the column inside a measure template with an alias.

    "SUM(AMOUNT)" -> "SUM(P.AMOUNT)"
    "SUM(INVOICE_AMOUNT)" -> "SUM(P.INVOICE_AMOUNT)"
    "COUNT(DISTINCT VENDOR_ID)" -> "COUNT(DISTINCT P.VENDOR_ID)"

    The base table's columns are the ones intended; without the alias,
    a joined table that happens to have a same-named column makes the
    query ambiguous. None of the current aggregations collide, but the
    rule is too narrow to leave implicit.

    If the template does not match the `<FN>(<COL>)` shape, it is
    returned unchanged — a composite expression (e.g. a ratio) would
    not have one column to qualify and would need per-tool handling.
    """
    import re

    m = re.match(r"^(\w+)\((.+)\)$", template)
    if not m:
        return template
    fn, inner = m.group(1), m.group(2)
    inner_stripped = inner.strip()
    # COUNT(DISTINCT col)
    if inner_stripped.upper().startswith("DISTINCT "):
        col = inner_stripped[len("DISTINCT "):].strip()
        return f"{fn}(DISTINCT {alias}.{col})"
    return f"{fn}({alias}.{inner_stripped})"


def _emit_aggregation_step(step: Any, spec: Any, overlay: Overlay) -> str:
    """Emit a GROUP BY query for an aggregation tool.

    Shape:
        SELECT <group_by>, <measure>
        FROM <base_table> <alias>
        [joins from base_entity.base_joins]
        GROUP BY <group_by>
        [ORDER BY <measure> DESC]   (if order_desc_by_measure)

    Filters on the step's tool_args are applied the same way the
    non-aggregating path applies them, but only simple-equality filters
    make sense for aggregations (a > filter would be a HAVING clause,
    not a WHERE, and no current aggregation tool takes a range filter).
    If any arg fails to resolve through the FilterSpec lookup, a
    comment line is emitted rather than a WHERE, so the SQL is not
    silently wrong.
    """
    base = overlay.entities.get(spec.base_entity)
    if base is None:
        return (
            f"-- Step {step.step_id}: {step.tool_name} "
            f"(aggregation's base_entity {spec.base_entity!r} not in "
            f"overlay — SQL not emitted)"
        )

    measure_sql = _qualify_measure(spec.measure_template, base.alias)
    select_lines = [
        f"{base.alias}.{spec.group_by_column}",
        f"       {measure_sql}",
    ]
    from_line = f"FROM {base.fusion_table} {base.alias}"
    joins = list(base.base_joins)
    where: list[str] = []

    # Aggregation args fall into four categories:
    #   1. skip_args — fetch caps or tool-internal knobs, deliberately
    #      not translated (e.g. 'limit' which bounds the FETCH).
    #   2. spec.top_n_arg — the top-N limit; becomes FETCH FIRST N ROWS
    #      ONLY after the ORDER BY, not a WHERE.
    #   3. filter args — mapped via FilterSpec into the WHERE clause.
    #   4. unknown args — emitted as a comment so nothing is silently
    #      dropped.
    top_n_value: int | None = None
    for arg_name, arg_value in step.tool_args.items():
        if arg_name in spec.skip_args:
            continue
        if arg_name == spec.top_n_arg:
            try:
                top_n_value = int(arg_value)
            except (TypeError, ValueError):
                where.append(
                    f"-- non-numeric top_n: {arg_name}={arg_value!r}"
                )
            continue
        if arg_value == ITERATION_SENTINEL:
            fspec = overlay.filters.get((step.tool_name, arg_name))
            if fspec is None:
                where.append(f"-- unmapped iteration arg: {arg_name}")
                continue
            where.append(
                fspec.predicate_template.format(
                    alias=base.alias, value=":iteration_value"
                )
            )
            continue
        fspec = overlay.filters.get((step.tool_name, arg_name))
        if fspec is None:
            where.append(f"-- unmapped tool_arg: {arg_name}={arg_value!r}")
            continue
        sql_value = _resolve_value(fspec, arg_value, overlay)
        if sql_value is None:
            where.append(
                f"-- unresolved literal for {arg_name}={arg_value!r}"
            )
            continue
        where.append(
            fspec.predicate_template.format(
                alias=base.alias, value=sql_value
            )
        )

    body_lines = [f"SELECT {select_lines[0]},", select_lines[1]]
    body_lines.append(from_line)
    body_lines.extend(joins)
    if where:
        body_lines.append("WHERE " + "\n  AND ".join(where))
    body_lines.append(f"GROUP BY {base.alias}.{spec.group_by_column}")
    if spec.order_desc_by_measure:
        body_lines.append(f"ORDER BY {measure_sql} DESC")
    if top_n_value is not None:
        body_lines.append(f"FETCH FIRST {top_n_value} ROWS ONLY")

    sql_body = "\n".join(body_lines) + ";"
    header = f"-- Step {step.step_id}: {step.tool_name} (aggregation)"
    parts = [header, sql_body]
    if spec.assumption:
        text = overlay.assumptions.get(spec.assumption, spec.assumption)
        parts.append("")
        parts.append(f"-- ASSUMPTION [{spec.assumption}]: {text}")
    return "\n".join(parts)


__all__ = ["emit_sql"]
