
"""
Planner for the KG-driven path (Architecture Option 3).

This module is the contract between the LLM intent-parsing step and the
MCP executor. It reads only from the KG (see scripts/rebuild_kg.sh) and emits a
structured plan. No LLM in the planning step. No prose-reading for
decisions.

Status: KG-lookup layer, helpers, orchestrator, intent validation,
and the F2 'no_invoices_in_N_months' negation pattern all
implemented. v1.1 covers the anchor question + the original Track A
prompt's negation clause. See design doc for known limitations.

Companion design doc: docs/designs/phase_2_planner_design.md
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterator

import oracledb


# ─────────────────────────────────────────────────────────────────────
# v1 mapping tables (intent vocabulary -> KG vocabulary)
#
# Intent filter types come from the LLM parser, which uses
# domain-friendly names ('country', 'has_open_PO',
# 'has_no_recent_invoices'). The KG uses normalized names
# ('country' as kg_entity_tool.filter_type, 'status' as
# kg_pattern_binding.filter_type). These tables bridge the two.
#
# v1.2 candidate: move these into the KG itself so the planner is
# fully data-driven. For v1.1 they're hardcoded so the planner stays
# small and the KG schema stays simple.
# ─────────────────────────────────────────────────────────────────────

# Filter definitions (entity-level vs edge-traversal, vocab kinds,
# implicit values) are no longer hardcoded here. They live in the KG
# table kg_entity_filter and are read lazily by _load_filter_defs()
# below. See the "Filter definitions" section further down.

# Map MCP tool name -> primary argument name (the one the executor
# substitutes $iteration_value into when iterating).
# v1.2 candidate: store this in the KG (e.g., kg_edge_tool.arg_name).
_TOOL_PRIMARY_ARG: dict[str, str] = {
    "search_invoices": "supplier_number",
    "search_purchase_orders": "supplier_id",
    "get_buyer": "buyer_id",
}

# Map aggregation op -> (mcp_tool_name, arg names it accepts). One op
# per tool, by design (feature 7 boundedness rule): a new aggregation
# shape is a new op + new tool, never a parameter on an existing one.
_AGGREGATION_TOOLS: dict[str, str] = {
    "by_supplier": "aggregate_invoices_by_supplier",
}

# Friendly output-name prefixes per entity. Pure naming convention;
# the executor doesn't interpret these.
_OUTPUT_NAME_BY_ENTITY: dict[str, str] = {
    "Supplier": "suppliers",
    "Invoice": "invoices",
    "PurchaseOrder": "pos",
    "Buyer": "buyers",
    "Address": "addresses",
}

# Filter-type -> short suffix used when the step's output is the
# filtered parent list (i.e. filter_source_when_empty=True).
# Composed with the source output name as
# "{source_output_name}_{suffix}". v1.2 candidate: move into the KG.
_FILTER_SOURCE_NAME_SUFFIX: dict[str, str] = {
    "has_no_recent_invoices": "no_recent_invoices",
}


# ─────────────────────────────────────────────────────────────────────
# KG connection
# ─────────────────────────────────────────────────────────────────────

# Oracle KG credentials resolve in this order, per field:
#   1. Environment variable (SPIRE_DB_USER / _PASSWORD / _DSN) — for CI
#      and ad-hoc overrides.
#   2. The persona's `oracle` block in personas.yaml — the normal source
#      and the single place to configure DB credentials.
# There is no hardcoded credential fallback: if neither source supplies a
# value, _oracle_credentials raises. (The DSN, being a non-secret local
# address, keeps a default; user and password must be configured.)

_DEFAULT_DSN = "localhost:1521/FREEPDB1"


def _oracle_credentials() -> tuple[str, str, str]:
    """Resolve (user, password, dsn) for the KG connection.

    Env vars win, then the persona's oracle block. No credential is
    hardcoded: if neither source provides a username/password, raise a
    clear error rather than silently using a baked-in default. The DSN
    falls back to the local address (not a secret) if unspecified."""
    persona_oracle = None
    try:
        from spire.config import load_persona

        persona_name = os.environ.get("SPIRE_PERSONA", "default_dev")
        persona_oracle = load_persona(persona_name).oracle
    except Exception:
        # No personas.yaml, unknown persona, or no oracle block — env
        # vars may still supply the credentials.
        persona_oracle = None

    user = os.environ.get("SPIRE_DB_USER") or (
        persona_oracle.username if persona_oracle else None
    )
    password = os.environ.get("SPIRE_DB_PASSWORD") or (
        persona_oracle.password if persona_oracle else None
    )
    dsn = os.environ.get("SPIRE_DB_DSN") or (
        persona_oracle.dsn if persona_oracle else None
    ) or _DEFAULT_DSN

    if not user or not password:
        raise RuntimeError(
            "No Oracle DB credentials. Set the oracle block in "
            "personas.yaml (username + password), or export "
            "SPIRE_DB_USER / SPIRE_DB_PASSWORD."
        )
    return user, password, dsn


@contextmanager
def _kg_cursor() -> Iterator[oracledb.Cursor]:
    """
    Yield a cursor against the KG database. Closes connection on exit.

    Every KG-lookup function opens a fresh connection; pooling can be
    added later if profiling shows it matters.
    """
    user, password, dsn = _oracle_credentials()
    connection = oracledb.connect(user=user, password=password, dsn=dsn)
    try:
        with connection.cursor() as cursor:
            yield cursor
    finally:
        connection.close()


def _read_clob(value: Any) -> str:
    """
    Coerce a possibly-CLOB column value to a Python str.

    Sync oracledb sometimes returns CLOB values as oracledb.LOB objects
    (which have a sync .read() method), and sometimes — depending on
    driver version and column size — as plain strings. Handle both.

    Returns empty string for None.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    # Sync oracledb.LOB: .read() is synchronous (unlike AsyncLOB).
    return value.read()


# ─────────────────────────────────────────────────────────────────────
# Filter definitions — loaded from kg_entity_filter (lazy, cached).
#
# Replaces the hardcoded filter dicts. Read once on first use, cached
# for the process lifetime. Mirrors the lazy-read style of the other
# KG lookups in this module.
# ─────────────────────────────────────────────────────────────────────

_FILTER_DEFS_CACHE: dict[str, dict[str, Any]] | None = None


def _load_filter_defs() -> dict[str, dict[str, Any]]:
    """Read kg_entity_filter once; cache by filter_type.

    Each value carries: mechanism, tool_arg_name, vocab_kind,
    target_entity, kg_filter_type, implicit_vocab_kind, implicit_term.
    """
    global _FILTER_DEFS_CACHE
    if _FILTER_DEFS_CACHE is not None:
        return _FILTER_DEFS_CACHE

    defs: dict[str, dict[str, Any]] = {}
    with _kg_cursor() as cursor:
        cursor.execute(
            "SELECT filter_type, mechanism, tool_arg_name, tool_arg_name_hi, "
            "vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, "
            "implicit_term FROM kg_entity_filter"
        )
        for row in cursor.fetchall():
            (ftype, mechanism, tool_arg, tool_arg_hi, vocab_kind, target,
             kg_filter_type, imp_vocab, imp_term) = row
            defs[ftype] = {
                "mechanism": mechanism,
                "tool_arg_name": tool_arg,
                "tool_arg_name_hi": tool_arg_hi,
                "vocab_kind": vocab_kind,
                "target_entity": target,
                "kg_filter_type": kg_filter_type,
                "implicit_vocab_kind": imp_vocab,
                "implicit_term": imp_term,
            }
    _FILTER_DEFS_CACHE = defs
    return defs


def _entity_level_filter_types() -> set[str]:
    """Filter types with a dedicated entity-level fetcher."""
    return {
        ftype for ftype, d in _load_filter_defs().items()
        if d["mechanism"] == "entity_level"
    }


def _edge_traversal_filters() -> dict[str, tuple[str, str]]:
    """Edge-traversal filters: type -> (target_entity, kg_filter_type)."""
    return {
        ftype: (d["target_entity"], d["kg_filter_type"])
        for ftype, d in _load_filter_defs().items()
        if d["mechanism"] == "edge_traversal"
    }


def _edge_filter_implicit_values() -> dict[str, tuple[str, str]]:
    """Edge filters with an implicit value: type -> (vocab_kind, term)."""
    return {
        ftype: (d["implicit_vocab_kind"], d["implicit_term"])
        for ftype, d in _load_filter_defs().items()
        if d["implicit_vocab_kind"] is not None
    }


def _filter_value_vocab_kind() -> dict[str, str]:
    """Filter types whose value resolves via a vocab kind."""
    return {
        ftype: d["vocab_kind"]
        for ftype, d in _load_filter_defs().items()
        if d["vocab_kind"] is not None
    }


# ─────────────────────────────────────────────────────────────────────
# Types
# ─────────────────────────────────────────────────────────────────────


@dataclass
class Intent:
    """
    Output of the LLM intent-parsing step.
    Input to ``generate_plan``.

    Example (for the original Track A prompt
    'suppliers in US with no invoices in 6 months but with open POs,
    including the buyer assigned to each'):

        Intent(
            target_entity="Supplier",
            filters=[
                {"type": "country", "value": "US"},
                {"type": "has_no_recent_invoices", "value": {"months": 6}},
                {"type": "has_open_PO", "value": True},
            ],
            include=["Buyer"],
        )
    """

    target_entity: str
    filters: list[dict[str, Any]] = field(default_factory=list)
    include: list[str] = field(default_factory=list)
    # Feature 7: when set, the question is an aggregation, not a list.
    # The LLM parser fills this when it detects aggregation/ranking
    # wording; it is None for ordinary list queries (the default), so
    # all existing behavior is unchanged. Shape:
    #   {"op": "by_supplier", "date_from": "...", "date_to": "...",
    #    "top_n": 10}
    # The planner maps a populated aggregate to a single tool step; the
    # op names the bounded aggregation tool (one op per tool, by design).
    aggregate: dict[str, Any] | None = None


@dataclass
class Step:
    """
    One step in a Plan. The executor reads these top-to-bottom.

    - ``tool_args`` values may be literals or the sentinel string
      ``"$iteration_value"`` (substituted by the executor when iterating).
    - ``iterate_over`` is ``None`` when the step runs once; otherwise
      ``{"from_step": <output_name>, "field": <field_name>}``.
    - ``client_filters`` are applied in Python after each tool call.
      All v1 edges have ``server_filter_rule = 'join_only'``, so any
      filter beyond the join key lives here.
    - ``filter_source_when_empty`` (F2): when True, the step's output
      is the SOURCE step's items, filtered to those whose per-iteration
      tool call returned an empty list. Used for "negation by absence"
      filters like "suppliers with NO invoices in the last 6 months".
      The executor honors this flag; it defaults to False so existing
      steps behave unchanged.
    """

    step_id: int
    tool_name: str
    tool_args: dict[str, Any]
    iterate_over: dict[str, str] | None
    client_filters: list[dict[str, Any]]
    output_name: str
    output_dedupe_by: str | None
    filter_source_when_empty: bool = False


Plan = list[Step]


# ─────────────────────────────────────────────────────────────────────
# KG entity lookups
# ─────────────────────────────────────────────────────────────────────


def find_entity(entity_name: str) -> dict[str, Any]:
    """
    Look up an entity by name in ``kg_entity``.

    Returns a dict with keys:
        endpoint_path, canonical_id_field, display_name_field, description

    Raises ``KeyError`` if no row exists for the given entity_name.
    Match is case-sensitive (entity_name is a primary key).
    """
    with _kg_cursor() as cursor:
        cursor.execute(
            """
            SELECT endpoint_path, canonical_id_field,
                   display_name_field, description
            FROM kg_entity
            WHERE entity_name = :entity_name
            """,
            entity_name=entity_name,
        )
        row = cursor.fetchone()

    if row is None:
        raise KeyError(f"No entity in KG: {entity_name!r}")

    endpoint_path, canonical_id_field, display_name_field, description = row
    return {
        "endpoint_path": endpoint_path,
        "canonical_id_field": canonical_id_field,
        "display_name_field": display_name_field,
        "description": description,
    }


def find_entity_tool(entity_name: str, filter_type: str) -> str:
    """
    Find the MCP tool that fetches this entity with the given filter type.

    Queries ``kg_entity_tool``. Use ``filter_type='none'`` for the default
    (unfiltered) fetcher.

    Examples:
        find_entity_tool('Supplier', 'none')    -> 'search_suppliers'
        find_entity_tool('Supplier', 'country') -> 'search_suppliers_by_country'

    Returns the MCP tool name as a string.
    Raises ``KeyError`` if no row exists for the (entity_name, filter_type)
    pair.
    """
    with _kg_cursor() as cursor:
        cursor.execute(
            """
            SELECT mcp_tool_name
            FROM kg_entity_tool
            WHERE entity_name = :entity_name
              AND filter_type = :filter_type
            """,
            entity_name=entity_name,
            filter_type=filter_type,
        )
        row = cursor.fetchone()

    if row is None:
        raise KeyError(
            f"No entity tool for ({entity_name!r}, {filter_type!r})"
        )

    return row[0]


# ─────────────────────────────────────────────────────────────────────
# KG edge lookups
# ─────────────────────────────────────────────────────────────────────


def find_edge(from_entity: str, to_entity: str) -> dict[str, Any]:
    """
    Look up the edge connecting two entities in ``kg_edge``.

    Returns a dict with keys:
        edge_name, from_join_field, to_join_field,
        cardinality, server_filter_rule, traversal_hint, notes

    Raises ``KeyError`` if no edge connects from_entity to to_entity.
    Note: edges are directional. find_edge('Supplier', 'PurchaseOrder')
    finds HAS_PURCHASE_ORDER; find_edge('PurchaseOrder', 'Supplier')
    will NOT find it (no reverse edge declared in v1).
    """
    with _kg_cursor() as cursor:
        cursor.execute(
            """
            SELECT edge_name, from_join_field, to_join_field,
                   cardinality, server_filter_rule, traversal_hint, notes
            FROM kg_edge
            WHERE from_entity = :from_entity
              AND to_entity   = :to_entity
            """,
            from_entity=from_entity,
            to_entity=to_entity,
        )
        row = cursor.fetchone()

    if row is None:
        raise KeyError(
            f"No edge from {from_entity!r} to {to_entity!r}"
        )

    (
        edge_name,
        from_join_field,
        to_join_field,
        cardinality,
        server_filter_rule,
        traversal_hint,
        notes,
    ) = row
    return {
        "edge_name": edge_name,
        "from_join_field": from_join_field,
        "to_join_field": to_join_field,
        "cardinality": cardinality,
        "server_filter_rule": server_filter_rule,
        "traversal_hint": traversal_hint,
        "notes": notes,
    }


def find_edge_tool(edge_name: str) -> str | None:
    """
    Find the MCP tool that traverses this edge in ``kg_edge_tool``.

    Returns the tool name string, or ``None`` if the edge has no row
    (e.g. ``HAS_ADDRESS`` is bundled with ``search_suppliers_by_country``
    via ``expand=addresses``; absence of a row is meaningful and signals
    the edge is not independently traversable).

    Examples:
        find_edge_tool('HAS_PURCHASE_ORDER') -> 'search_purchase_orders'
        find_edge_tool('ASSIGNED_TO')        -> 'get_buyer'
        find_edge_tool('HAS_ADDRESS')        -> None
    """
    with _kg_cursor() as cursor:
        cursor.execute(
            """
            SELECT mcp_tool_name
            FROM kg_edge_tool
            WHERE edge_name = :edge_name
            """,
            edge_name=edge_name,
        )
        row = cursor.fetchone()

    if row is None:
        return None

    return row[0]


# ─────────────────────────────────────────────────────────────────────
# KG pattern lookups
# ─────────────────────────────────────────────────────────────────────


def find_pattern_for_filter(
    entity_name: str, filter_type: str
) -> dict[str, Any]:
    """
    Find which pattern handles this filter type on this entity.

    Queries ``kg_pattern_binding``. Returns:
        {
          "pattern_name": <str>,
          "parameter_bindings": <dict parsed from JSON>,
        }

    ``parameter_bindings`` is stored as a JSON string in a CLOB and is
    parsed before return — callers receive a Python dict, not a string.

    Examples:
        find_pattern_for_filter('Supplier', 'country')
          -> {
               "pattern_name": "country_filter_via_address",
               "parameter_bindings": {
                   "parent": "Supplier",
                   "child_edge": "HAS_ADDRESS",
                   "country_term_param": "country",
               },
             }

    Raises ``KeyError`` if no binding exists for the (entity_name,
    filter_type) pair.
    Raises ``json.JSONDecodeError`` if parameter_bindings is malformed
    (indicates seed-data corruption, not a user error).
    """
    with _kg_cursor() as cursor:
        cursor.execute(
            """
            SELECT pattern_name, parameter_bindings
            FROM kg_pattern_binding
            WHERE entity_name = :entity_name
              AND filter_type = :filter_type
            """,
            entity_name=entity_name,
            filter_type=filter_type,
        )
        row = cursor.fetchone()
        if row is None:
            raise KeyError(
                f"No pattern binding for ({entity_name!r}, {filter_type!r})"
            )
        # Read CLOB while the connection is still open. Sync oracledb's
        # LOB.read() is synchronous (unlike the async driver's AsyncLOB).
        pattern_name, parameter_bindings_raw = row
        parameter_bindings_str = _read_clob(parameter_bindings_raw)

    parameter_bindings = json.loads(parameter_bindings_str)
    return {
        "pattern_name": pattern_name,
        "parameter_bindings": parameter_bindings,
    }


# ─────────────────────────────────────────────────────────────────────
# KG vocabulary lookups
# ─────────────────────────────────────────────────────────────────────


def resolve_vocab(vocab_kind: str, term: str) -> str:
    """
    Resolve a business term to its canonical Fusion code.

    Queries ``kg_vocabulary``. Examples:
        resolve_vocab('country', 'US')        -> 'US'
        resolve_vocab('country', 'USA')       -> 'US'
        resolve_vocab('po_status', 'open')    -> 'OPEN'
        resolve_vocab('po_status', 'active')  -> 'OPEN'

    Raises ``KeyError`` if no matching row exists for the
    (vocab_kind, term) pair. Match is case-insensitive on the term.
    """
    with _kg_cursor() as cursor:
        cursor.execute(
            """
            SELECT canonical_value
            FROM kg_vocabulary
            WHERE vocab_kind = :vocab_kind AND LOWER(term) = LOWER(:term)
            """,
            vocab_kind=vocab_kind,
            term=term,
        )
        row = cursor.fetchone()

    if row is None:
        raise KeyError(f"No vocab for ({vocab_kind!r}, {term!r})")

    return row[0]


# ─────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────


def generate_plan(
    intent: Intent, reference_date: date | None = None
) -> Plan:
    """
    Produce an ordered, executable plan from a structured intent.

    Uses only KG lookups. No LLM. No prose interpretation.

    Three-block flow:

    1. Fetch target entity (with entity-level filter if applicable).
    2. For each filter needing an edge traversal, add an iterating step.
       Some filters (negation-by-absence, e.g. has_no_recent_invoices)
       emit a step whose output is the FILTERED PARENT list, not the
       child list. Such steps carry filter_source_when_empty=True for
       the executor.
    3. For each include, add a lookup step (with dedup on the join field).

    Args:
        intent: The structured intent (validated; unknown filter types
            raise NotImplementedError before any plan work happens).
        reference_date: For testability of date-computing filters
            (e.g. has_no_recent_invoices computes today - N months).
            Defaults to date.today() in production.

    Raises NotImplementedError if any filter in ``intent.filters`` has
    a ``type`` not supported in v1 (silent-drop defect fix — F1).
    """
    # ── Feature 7: aggregation short-circuit ──────────────────────
    # When the intent carries an aggregate block, the question is a
    # ranking/total, not a list. Emit a single non-iterating step that
    # calls the bounded aggregation tool. This bypasses the entity-fetch
    # / edge-traversal / include flow entirely — aggregation owns its
    # own fetch+filter+math inside the tool.
    if intent.aggregate is not None:
        return _build_aggregation_plan(intent.aggregate)

    # Validate up front so unknown filter types raise loudly instead
    # of being silently dropped by _filters_needing_edge_traversal.
    _validate_intent_filters(intent.filters)

    # Invoice queries require a supplier reference. Without it the fetch
    # would pull every invoice on the pod. Refuse loudly instead.
    if intent.target_entity == "Invoice":
        has_supplier = any(
            f.get("type") == "supplier" for f in intent.filters
        )
        if not has_supplier:
            raise ValueError(
                "Invoice queries require a supplier. Name the supplier by "
                "number (e.g. 'invoices for supplier 1252') or by name "
                "(e.g. 'invoices for Lee Supplies')."
            )

    ref_date = reference_date if reference_date is not None else date.today()

    plan: Plan = []
    step_id = 1

    # ── Block 1: entity fetch ─────────────────────────────────────
    # All entity-level filters go to the entity's single default
    # fetcher (kg_entity_tool filter_type='none'), combined into one
    # tool_args dict. This lets filters stack (e.g. active US suppliers
    # named Lee) instead of each needing its own fetcher tool.
    entity_filter_type = _pick_entity_filter(intent.filters)
    fetcher_tool = find_entity_tool(intent.target_entity, "none")
    fetcher_args = _build_entity_fetcher_args(intent.filters)

    plan.append(
        Step(
            step_id=step_id,
            tool_name=fetcher_tool,
            tool_args=fetcher_args,
            iterate_over=None,
            client_filters=[],
            output_name=_make_output_name(
                intent.target_entity, entity_filter_type, intent.filters
            ),
            output_dedupe_by=None,
        )
    )
    previous_entity = intent.target_entity
    previous_output_name = plan[-1].output_name
    step_id += 1

    # ── Block 2: edge-traversal filters ───────────────────────────
    for filter_spec in _filters_needing_edge_traversal(intent.filters):
        filter_type = filter_spec["type"]
        target_entity = _filter_target_entity(filter_spec)
        edge = find_edge(previous_entity, target_entity)
        tool = find_edge_tool(edge["edge_name"])
        if tool is None:
            # v1 invariant: any edge used for traversal must have a tool.
            # HAS_ADDRESS doesn't, but no filter type targets Address in v1.
            raise RuntimeError(
                f"Edge {edge['edge_name']!r} has no tool binding; "
                "cannot traverse independently."
            )

        # Decide step shape based on the filter type:
        #
        # - status-style filters (has_open_PO): per-iteration client
        #   filter on the child results; output is the child list.
        #
        # - negation-by-absence filters (has_no_recent_invoices): no
        #   client filter; output is the PARENT items whose per-iteration
        #   call returned empty. filter_source_when_empty=True.
        filter_source_when_empty = filter_type in _FILTER_SOURCE_NAME_SUFFIX

        if filter_source_when_empty:
            # Build args including computed values (e.g. invoice_date_after).
            tool_args = _build_iteration_args_with_computed(
                filter_spec, tool, ref_date
            )
            client_filters: list[dict[str, Any]] = []
            output_name = _make_filtered_source_output_name(
                previous_output_name, filter_type
            )
            # Output is parent items, so previous_entity stays as parent.
            new_previous_entity = previous_entity
        else:
            tool_args = {_arg_name_for_tool(tool): "$iteration_value"}
            client_filters = _resolve_client_filters(
                filter_spec, target_entity
            )
            output_name = _make_output_name(target_entity, None, [])
            new_previous_entity = target_entity

        plan.append(
            Step(
                step_id=step_id,
                tool_name=tool,
                tool_args=tool_args,
                iterate_over={
                    "from_step": previous_output_name,
                    "field": edge["from_join_field"],
                },
                client_filters=client_filters,
                output_name=output_name,
                output_dedupe_by=None,
                filter_source_when_empty=filter_source_when_empty,
            )
        )
        previous_entity = new_previous_entity
        previous_output_name = plan[-1].output_name
        step_id += 1

    # ── Block 3: includes ─────────────────────────────────────────
    for include_entity in intent.include:
        edge = find_edge(previous_entity, include_entity)
        tool = find_edge_tool(edge["edge_name"])
        if tool is None:
            raise RuntimeError(
                f"Edge {edge['edge_name']!r} has no tool binding; "
                "cannot satisfy include."
            )
        plan.append(
            Step(
                step_id=step_id,
                tool_name=tool,
                tool_args={_arg_name_for_tool(tool): "$iteration_value"},
                iterate_over={
                    "from_step": previous_output_name,
                    "field": edge["from_join_field"],
                },
                client_filters=[],
                output_name=_make_output_name(include_entity, None, []),
                output_dedupe_by=edge["from_join_field"],
            )
        )
        previous_entity = include_entity
        previous_output_name = plan[-1].output_name
        step_id += 1

    return plan


# ─────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────


def _build_aggregation_plan(aggregate: dict[str, Any]) -> Plan:
    """
    Build a single-step plan for an aggregation intent (feature 7).

    The aggregate block names an op (which maps to a bounded aggregation
    tool) plus the tool's parameters (date_from, date_to, top_n). The
    result is one non-iterating Step; the tool does the fetch + math and
    returns a structured ranking, which the executor passes through to
    the synthesizer.

    Raises NotImplementedError if the op has no registered tool — the
    aggregation analog of _validate_intent_filters' unknown-type guard,
    so an unsupported aggregation fails loudly rather than silently.
    """
    op = aggregate.get("op")
    tool = _AGGREGATION_TOOLS.get(op)
    if tool is None:
        raise NotImplementedError(
            f"Aggregation op {op!r} is not supported in v1. "
            f"Supported ops: {sorted(_AGGREGATION_TOOLS)}."
        )

    # Pass through only the recognized tool params, dropping None so the
    # tool's own defaults (e.g. top_n=10) apply when unspecified.
    tool_args: dict[str, Any] = {}
    for key in ("date_from", "date_to", "top_n"):
        if aggregate.get(key) is not None:
            tool_args[key] = aggregate[key]

    return [
        Step(
            step_id=1,
            tool_name=tool,
            tool_args=tool_args,
            iterate_over=None,
            client_filters=[],
            output_name="aggregation",
            output_dedupe_by=None,
        )
    ]


def _validate_intent_filters(filters: list[dict[str, Any]]) -> None:
    """
    Verify every filter in the intent has a known handler in v1.

    Called from generate_plan before any other work, so unknown filter
    types raise loudly instead of being silently dropped further down
    the pipeline. (v1's _filters_needing_edge_traversal would otherwise
    silently exclude filters whose type isn't an edge-traversal filter,
    which means an intent like {"type": "has_no_recent_invoices", ...}
    would execute as if that clause weren't in the prompt — a silent
    miss that's worse than a crash.)

    Raises NotImplementedError listing ALL unknown filter types at once,
    with a message naming the v1-supported alternatives.
    """
    known_types = _entity_level_filter_types() | set(_edge_traversal_filters())
    unknown = [
        f.get("type") for f in filters if f.get("type") not in known_types
    ]
    if unknown:
        raise NotImplementedError(
            f"Intent contains filter types not supported in v1: {unknown}. "
            f"Supported entity-level filters: "
            f"{sorted(_entity_level_filter_types())}. "
            f"Supported edge-traversal filters: "
            f"{sorted(_edge_traversal_filters())}."
        )


def _pick_entity_filter(filters: list[dict[str, Any]]) -> str:
    """
    Decide which filter (if any) has a dedicated entity-level fetcher tool.

    Returns the filter type as a string, or ``'none'`` if no filter has a
    dedicated fetcher. Examples:
        [{"type": "country", ...}, {"type": "has_open_PO", ...}] -> 'country'
        [{"type": "has_open_PO", ...}]                            -> 'none'

    Checks against the entity-level filter types from the KG.
    Returns the FIRST matching filter type. v1's anchor intent has at
    most one entity-level filter, so order-stability suffices.
    """
    entity_level = _entity_level_filter_types()
    for f in filters:
        if f.get("type") in entity_level:
            return f["type"]
    return "none"


def _build_fetcher_args(
    filter_type: str, filters: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Build the ``tool_args`` dict for the entity-level fetcher.

    Resolves the filter's value through ``resolve_vocab`` if a vocab
    kind is registered for the filter type.

    Examples:
        _build_fetcher_args('none', [...])
          -> {}
        _build_fetcher_args('country', [{"type":"country","value":"US"}])
          -> {"country": "US"}
        _build_fetcher_args('country', [{"type":"country","value":"United States"}])
          -> {"country": "US"}   (vocab-normalized)
    """
    if filter_type == "none":
        return {}

    # Find the matching filter (v1: assumes at most one of each type).
    matching = next(f for f in filters if f.get("type") == filter_type)
    raw_value = matching["value"]

    # Normalize via vocab if a vocab kind is registered.
    vocab_kind = _filter_value_vocab_kind().get(filter_type)
    if vocab_kind is not None:
        normalized = resolve_vocab(vocab_kind, raw_value)
    else:
        normalized = raw_value

    return {filter_type: normalized}


def _build_entity_fetcher_args(
    filters: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Build combined ``tool_args`` for the per-entity default fetcher.

    Loops over every entity-level filter in the intent and maps each to
    the tool argument name declared in the KG (kg_entity_filter.
    tool_arg_name). Values are vocab-normalized when a vocab kind is
    registered for the filter. This lets a single fetcher receive
    several filters at once (e.g. status + country + name).

    Example:
        [{"type":"status","value":"active"},
         {"type":"country","value":"United States"}]
          -> {"status": "ACTIVE", "country": "US"}
    """
    defs = _load_filter_defs()
    vocab_kinds = _filter_value_vocab_kind()
    entity_level = _entity_level_filter_types()

    args: dict[str, Any] = {}
    for f in filters:
        ftype = f.get("type")
        if ftype not in entity_level:
            continue
        arg_name = defs[ftype].get("tool_arg_name")
        if not arg_name:
            continue
        raw_value = f.get("value")

        # Range filters carry a dict value with a low and/or high bound.
        # The two tool args come from the KG (tool_arg_name = low,
        # tool_arg_name_hi = high). Accept either {"from","to"} (dates)
        # or {"min","max"} (amounts) as the value keys.
        arg_name_hi = defs[ftype].get("tool_arg_name_hi")
        if isinstance(raw_value, dict):
            low = raw_value.get("from", raw_value.get("min"))
            high = raw_value.get("to", raw_value.get("max"))
            if low is not None:
                args[arg_name] = low
            if high is not None and arg_name_hi:
                args[arg_name_hi] = high
            continue

        # The Invoice 'supplier' filter carries a supplier reference whose
        # arg depends on its shape: an all-digit value is a SupplierNumber;
        # anything else is treated as a name substring.
        if arg_name == "supplier":
            value_str = str(raw_value).strip()
            if value_str.isdigit():
                args["supplier_number"] = value_str
            else:
                args["supplier_name"] = value_str
            continue

        vocab_kind = vocab_kinds.get(ftype)
        if vocab_kind is not None:
            args[arg_name] = resolve_vocab(vocab_kind, raw_value)
        else:
            args[arg_name] = raw_value
    return args


def _filters_needing_edge_traversal(
    filters: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Return the subset of filters not handled by the entity-level fetcher
    and therefore needing a separate edge traversal step.

    Returns filters whose type is an edge-traversal filter (from the KG).
    Entity-level filters (already consumed by Block 1) and unknown
    filter types are excluded.

    Note: this function used to silently drop unknown filter types
    (the v1 defect surfaced in the Design 3 measurement report).
    _validate_intent_filters is now called from generate_plan before
    this function runs, so unknown types raise before reaching here.
    """
    edge_filters = _edge_traversal_filters()
    return [f for f in filters if f.get("type") in edge_filters]


def _filter_target_entity(filter_spec: dict[str, Any]) -> str:
    """
    Given a filter spec, return the entity it constrains.

    Example: {"type": "has_open_PO", ...} -> "PurchaseOrder"

    Raises KeyError if the filter type is unknown to v1.
    """
    filter_type = filter_spec.get("type")
    edge_filters = _edge_traversal_filters()
    if filter_type not in edge_filters:
        raise KeyError(
            f"Filter type {filter_type!r} has no edge-traversal target "
            "in the KG filter table."
        )
    target_entity, _kg_filter_type = edge_filters[filter_type]
    return target_entity


def _resolve_client_filters(
    filter_spec: dict[str, Any], target_entity: str
) -> list[dict[str, Any]]:
    """
    Translate a filter spec into the list of client-side filters to apply
    after the tool call.

    Internally calls ``find_pattern_for_filter``, parses the pattern's
    ``parameter_bindings``, resolves vocab values, and constructs the
    filter list in the ``{field, op, value}`` shape.

    v1 only implements ``status_filter`` here. country_filter_via_address
    is handled by the entity-level fetcher in Block 1.
    no_child_in_N_months is handled via filter_source_when_empty in the
    orchestrator, not via client filters.

    Example: {"type": "has_open_PO", ...} on PurchaseOrder
        -> [{"field": "StatusCode", "op": "equals", "value": "OPEN"}]
    """
    intent_filter_type = filter_spec.get("type")
    edge_filters = _edge_traversal_filters()
    if intent_filter_type not in edge_filters:
        raise KeyError(
            f"Filter type {intent_filter_type!r} is not an edge-traversal "
            "filter and has no client-filter mapping."
        )
    _target_entity, kg_filter_type = edge_filters[intent_filter_type]

    binding = find_pattern_for_filter(target_entity, kg_filter_type)
    pattern_name = binding["pattern_name"]
    bindings = binding["parameter_bindings"]

    if pattern_name == "status_filter":
        # bindings carry: X (entity), status_field, status_term_param.
        field_name = bindings["status_field"]
        vocab_kind, implicit_term = _edge_filter_implicit_values()[intent_filter_type]
        canonical = resolve_vocab(vocab_kind, implicit_term)
        return [{"field": field_name, "op": "equals", "value": canonical}]

    # Other patterns (e.g., country_filter_via_address, no_child_in_N_months)
    # are NOT handled here in v1.1 — they're handled elsewhere in the
    # orchestrator (Block 1 entity fetcher, or filter_source_when_empty
    # respectively). If we get here, the planner is being asked
    # something v1 doesn't cover.
    raise NotImplementedError(
        f"Client-filter construction for pattern {pattern_name!r} "
        "is not implemented in v1."
    )


def _build_iteration_args_with_computed(
    filter_spec: dict[str, Any],
    tool_name: str,
    reference_date: date,
) -> dict[str, Any]:
    """
    Build tool_args for an iterating step whose args include a
    computed value (e.g. invoice_date_after = today - N months).

    The primary iteration key is always set to the iteration sentinel.
    Additional computed args are added based on the filter type.

    For has_no_recent_invoices with value {"months": 6}, returns:
        {"supplier_number": "$iteration_value",
         "invoice_date_after": "2025-11-26"}
    where the date is reference_date minus 6 months.

    v1.1 only handles has_no_recent_invoices. Other computed-arg
    filter types would extend this function.
    """
    intent_filter_type = filter_spec["type"]
    primary_arg = _arg_name_for_tool(tool_name)
    args: dict[str, Any] = {primary_arg: "$iteration_value"}

    if intent_filter_type == "has_no_recent_invoices":
        value = filter_spec.get("value") or {}
        months = value.get("months")
        if not isinstance(months, int) or months <= 0:
            raise ValueError(
                f"has_no_recent_invoices requires value={{'months': <positive int>}}; "
                f"got {filter_spec.get('value')!r}."
            )
        cutoff = _compute_date_n_months_ago(months, reference_date)
        args["invoice_date_after"] = cutoff.isoformat()
        return args

    # Other filter types with computed args would dispatch here.
    raise NotImplementedError(
        f"Computed iteration args not implemented for filter type "
        f"{intent_filter_type!r}."
    )


def _compute_date_n_months_ago(months: int, reference_date: date) -> date:
    """
    Return reference_date minus ``months`` months.

    Naive month arithmetic — handles month rollover with day clamping.
    Example: 2026-03-31 minus 1 month -> 2026-02-28 (not 2026-02-31).

    Pure function for testability; reference_date defaulting happens
    in the orchestrator, not here.
    """
    year = reference_date.year
    month = reference_date.month - months
    while month <= 0:
        month += 12
        year -= 1
    # Clamp day to last day of target month.
    day = min(reference_date.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    """Return the number of days in the given (year, month)."""
    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    last_day = (next_month_first - _one_day()).day
    return last_day


def _one_day():
    """Return a one-day timedelta. Helper to avoid a top-level import
    when most of this module doesn't need timedelta."""
    from datetime import timedelta
    return timedelta(days=1)


def _arg_name_for_tool(tool_name: str) -> str:
    """
    Return the argument name the given MCP tool expects for its primary
    input.

    Examples:
        search_purchase_orders -> 'supplier_id'
        get_buyer              -> 'buyer_id'
        search_invoices        -> 'supplier_number'

    v1: static dict (_TOOL_PRIMARY_ARG). v2 may want this in the KG.
    Raises KeyError if the tool is not in the table.
    """
    if tool_name not in _TOOL_PRIMARY_ARG:
        raise KeyError(
            f"No primary-arg mapping for tool {tool_name!r}. "
            "Add it to _TOOL_PRIMARY_ARG."
        )
    return _TOOL_PRIMARY_ARG[tool_name]


def _make_output_name(
    entity_name: str,
    filter_type: str | None = None,
    filters: list[dict[str, Any]] | None = None,
) -> str:
    """
    Stable, readable output name for a step's results.

    Examples:
        _make_output_name('Supplier', 'country', [{"type":"country","value":"US"}])
          -> 'us_suppliers'
        _make_output_name('PurchaseOrder')
          -> 'open_pos'    (v1 special-cases PO since the only PO-producing
                            step in the anchor plan is the open-PO traversal)
        _make_output_name('Buyer')
          -> 'buyers'

    Implementation note: the executor doesn't interpret these; pure
    convention. The 'open_pos' special-case matches the anchor-plan
    fixture; v1.1 can derive the prefix from filter context.
    """
    base = _OUTPUT_NAME_BY_ENTITY.get(entity_name, entity_name.lower())

    # Country-filtered entity fetch: prefix with the country code.
    if filter_type == "country" and filters:
        matching = next((f for f in filters if f.get("type") == "country"), None)
        if matching is not None:
            country_value = matching["value"]
            vocab_kind = _filter_value_vocab_kind().get("country")
            if vocab_kind is not None:
                try:
                    country_value = resolve_vocab(vocab_kind, country_value)
                except KeyError:
                    pass  # Fall back to the raw value.
            return f"{country_value.lower()}_{base}"

    # v1 special-case: PurchaseOrder steps in the anchor plan always
    # carry the open-PO filter, so the canonical output name is 'open_pos'.
    if entity_name == "PurchaseOrder":
        return "open_pos"

    return base


def _make_filtered_source_output_name(
    source_output_name: str, filter_type: str
) -> str:
    """
    Compose the output name for a step that filters its source items by
    iteration-emptiness (filter_source_when_empty=True).

    Example: source='us_suppliers', filter='has_no_recent_invoices'
        -> 'us_suppliers_no_recent_invoices'

    Raises KeyError if filter_type has no suffix mapping in
    _FILTER_SOURCE_NAME_SUFFIX.
    """
    if filter_type not in _FILTER_SOURCE_NAME_SUFFIX:
        raise KeyError(
            f"No filter-source name suffix for {filter_type!r}. "
            "Add it to _FILTER_SOURCE_NAME_SUFFIX."
        )
    suffix = _FILTER_SOURCE_NAME_SUFFIX[filter_type]
    return f"{source_output_name}_{suffix}"


def _previous_entity(plan: Plan) -> str:
    """
    Return the entity name that the previous step's output represents.

    NOTE: v1 does NOT use this helper; the orchestrator tracks the
    previous entity as a local variable instead, because Step doesn't
    carry the entity name and reverse-deriving it from output_name is
    brittle. Kept here as a stub so the design-doc contract is visible.

    v1.1 candidate: add an `entity` field to Step and derive this from
    plan[-1].entity.
    """
    raise NotImplementedError(
        "v1 tracks previous entity inline in generate_plan. "
        "This helper exists for design symmetry; do not call it."
    )




