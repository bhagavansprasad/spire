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

from spire.kg.sql_overlay import (
    OVERLAY,
    FilterSpec,
    Overlay,
)


def emit_sql(plan: Iterable[Any], overlay: Overlay = OVERLAY) -> list[str]:
    """Return one SQL string per Plan step, in order."""
    return [_emit_step(step, overlay) for step in plan]


def _emit_step(step: Any, overlay: Overlay) -> str:
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

    # Iterating steps: the primary arg is $iteration_value.
    parameterized = step.iterate_over is not None
    iterate_placeholder: str | None = None

    for arg_name, arg_value in step.tool_args.items():
        if arg_name == "include_addresses":
            if arg_value:
                _maybe_add_join(
                    ("Supplier", "Address"), joins, assumptions, overlay
                )
            continue

        if arg_value == "$iteration_value":
            iterate_placeholder = f"{entity.alias}.VENDOR_ID"
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

    if parameterized and iterate_placeholder is not None:
        where.append(f"{iterate_placeholder} = :supplier_id")

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


__all__ = ["emit_sql"]
