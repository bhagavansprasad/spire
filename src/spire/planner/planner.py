"""
Planner for the KG-driven path (Architecture Option 3).

This module is the contract between the LLM intent-parsing step and the
MCP executor. It reads only from the KG (see sql/kg/v1/) and emits a
structured plan. No LLM in the planning step. No prose-reading for
decisions.

Status: KG-lookup layer, helpers, orchestrator, and intent validation
all implemented. v1 covers the anchor question; see design doc
§"Known limitations" for what other intent shapes are NOT supported.

Companion design doc: docs/designs/phase_2_planner_design.md
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

import oracledb


# ─────────────────────────────────────────────────────────────────────
# v1 mapping tables (intent vocabulary -> KG vocabulary)
#
# Intent filter types come from the LLM parser, which uses
# domain-friendly names ('country', 'has_open_PO'). The KG uses
# normalized names ('country' as kg_entity_tool.filter_type, 'status'
# as kg_pattern_binding.filter_type). These tables bridge the two.
#
# v1.1 candidate: move these into the KG itself so the planner is
# fully data-driven. For v1 they're hardcoded so the planner stays
# small and the KG schema stays simple.
# ─────────────────────────────────────────────────────────────────────

# Intent filter types that have a dedicated entity-level fetcher tool.
# Anything not in this set is assumed to require an edge traversal.
_ENTITY_LEVEL_FILTER_TYPES: set[str] = {"country"}

# Intent filter types that require an edge traversal to a child entity.
# Maps the intent filter type to (target_entity, kg_filter_type) so
# the orchestrator knows which edge to walk and which pattern binding
# to look up.
_EDGE_TRAVERSAL_FILTERS: dict[str, tuple[str, str]] = {
    "has_open_PO": ("PurchaseOrder", "status"),
}

# Per-edge-traversal filter, the vocab kind to resolve the implicit value.
# 'has_open_PO' implies status='open'; we resolve 'open' via po_status vocab.
_EDGE_FILTER_IMPLICIT_VALUES: dict[str, tuple[str, str]] = {
    "has_open_PO": ("po_status", "open"),
}

# Map MCP tool name -> primary argument name (the one the executor
# substitutes $iteration_value into when iterating).
# v1.1 candidate: store this in the KG (e.g., kg_edge_tool.arg_name).
_TOOL_PRIMARY_ARG: dict[str, str] = {
    "search_invoices": "supplier_number",
    "search_purchase_orders": "supplier_id",
    "get_buyer": "buyer_id",
}

# Map intent filter type -> the vocab_kind used to resolve its value.
# Only filter types with a free-form value need this; entity-level
# filters whose value is already canonical (country='US') still go
# through resolve_vocab for normalization (e.g., 'United States' -> 'US').
_FILTER_VALUE_VOCAB_KIND: dict[str, str] = {
    "country": "country",
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


# ─────────────────────────────────────────────────────────────────────
# KG connection
# ─────────────────────────────────────────────────────────────────────

# Connection details mirror scripts/rebuild_kg.sh. The DSN points at the
# port-mapped Oracle container on the host. Override via environment for
# CI or alternate setups.
_DEFAULT_USER = "spire"
_DEFAULT_PASSWORD = "jnjnuh"
_DEFAULT_DSN = "localhost:1521/FREEPDB1"


@contextmanager
def _kg_cursor() -> Iterator[oracledb.Cursor]:
    """
    Yield a cursor against the KG database. Closes connection on exit.

    Every KG-lookup function opens a fresh connection; pooling can be
    added later if profiling shows it matters.
    """
    connection = oracledb.connect(
        user=os.environ.get("SPIRE_DB_USER", _DEFAULT_USER),
        password=os.environ.get("SPIRE_DB_PASSWORD", _DEFAULT_PASSWORD),
        dsn=os.environ.get("SPIRE_DB_DSN", _DEFAULT_DSN),
    )
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
# Types
# ─────────────────────────────────────────────────────────────────────


@dataclass
class Intent:
    """
    Output of the LLM intent-parsing step.
    Input to ``generate_plan``.

    Example (for the anchor question
    'Show me suppliers in US with open POs, including the buyer'):

        Intent(
            target_entity="Supplier",
            filters=[
                {"type": "country", "value": "US"},
                {"type": "has_open_PO", "value": True},
            ],
            include=["Buyer"],
        )
    """

    target_entity: str
    filters: list[dict[str, Any]] = field(default_factory=list)
    include: list[str] = field(default_factory=list)


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
    """

    step_id: int
    tool_name: str
    tool_args: dict[str, Any]
    iterate_over: dict[str, str] | None
    client_filters: list[dict[str, Any]]
    output_name: str
    output_dedupe_by: str | None


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
    (vocab_kind, term) pair. Match is case-sensitive.
    """
    with _kg_cursor() as cursor:
        cursor.execute(
            """
            SELECT canonical_value
            FROM kg_vocabulary
            WHERE vocab_kind = :vocab_kind AND term = :term
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


def generate_plan(intent: Intent) -> Plan:
    """
    Produce an ordered, executable plan from a structured intent.

    Uses only KG lookups. No LLM. No prose interpretation.

    Three-block flow (sufficient for v1's anchor question; see design doc
    for known limitations):

    1. Fetch target entity (with entity-level filter if applicable).
    2. For each filter needing an edge traversal, add an iterating step.
    3. For each include, add a lookup step (with dedup on the join field).

    Tracing the anchor question through this orchestrator produces the
    3-step plan shown in the design doc.

    Raises NotImplementedError if any filter in ``intent.filters`` has
    a ``type`` not supported in v1 (silent-drop defect fix — F1).
    """
    # Validate up front so unknown filter types raise loudly instead
    # of being silently dropped by _filters_needing_edge_traversal.
    _validate_intent_filters(intent.filters)

    plan: Plan = []
    step_id = 1

    # ── Block 1: entity fetch ─────────────────────────────────────
    entity_filter_type = _pick_entity_filter(intent.filters)
    fetcher_tool = find_entity_tool(intent.target_entity, entity_filter_type)
    fetcher_args = _build_fetcher_args(entity_filter_type, intent.filters)

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
        client_filters = _resolve_client_filters(filter_spec, target_entity)
        plan.append(
            Step(
                step_id=step_id,
                tool_name=tool,
                tool_args={_arg_name_for_tool(tool): "$iteration_value"},
                iterate_over={
                    "from_step": previous_output_name,
                    "field": edge["from_join_field"],
                },
                client_filters=client_filters,
                output_name=_make_output_name(target_entity, None, []),
                output_dedupe_by=None,
            )
        )
        previous_entity = target_entity
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


def _validate_intent_filters(filters: list[dict[str, Any]]) -> None:
    """
    Verify every filter in the intent has a known handler in v1.

    Called from generate_plan before any other work, so unknown filter
    types raise loudly instead of being silently dropped further down
    the pipeline. (v1's _filters_needing_edge_traversal would otherwise
    silently exclude filters whose type isn't in _EDGE_TRAVERSAL_FILTERS,
    which means an intent like {"type": "has_no_recent_invoices", ...}
    would execute as if that clause weren't in the prompt — a silent
    miss that's worse than a crash.)

    Raises NotImplementedError listing ALL unknown filter types at once,
    with a message naming the v1-supported alternatives.
    """
    known_types = _ENTITY_LEVEL_FILTER_TYPES | set(_EDGE_TRAVERSAL_FILTERS)
    unknown = [
        f.get("type") for f in filters if f.get("type") not in known_types
    ]
    if unknown:
        raise NotImplementedError(
            f"Intent contains filter types not supported in v1: {unknown}. "
            f"Supported entity-level filters: "
            f"{sorted(_ENTITY_LEVEL_FILTER_TYPES)}. "
            f"Supported edge-traversal filters: "
            f"{sorted(_EDGE_TRAVERSAL_FILTERS)}."
        )


def _pick_entity_filter(filters: list[dict[str, Any]]) -> str:
    """
    Decide which filter (if any) has a dedicated entity-level fetcher tool.

    Returns the filter type as a string, or ``'none'`` if no filter has a
    dedicated fetcher. Examples:
        [{"type": "country", ...}, {"type": "has_open_PO", ...}] -> 'country'
        [{"type": "has_open_PO", ...}]                            -> 'none'

    v1: checks against _ENTITY_LEVEL_FILTER_TYPES (module-level constant).
    Returns the FIRST matching filter type. v1's anchor intent has at
    most one entity-level filter, so order-stability suffices.
    """
    for f in filters:
        if f.get("type") in _ENTITY_LEVEL_FILTER_TYPES:
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
    vocab_kind = _FILTER_VALUE_VOCAB_KIND.get(filter_type)
    if vocab_kind is not None:
        normalized = resolve_vocab(vocab_kind, raw_value)
    else:
        normalized = raw_value

    return {filter_type: normalized}


def _filters_needing_edge_traversal(
    filters: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Return the subset of filters not handled by the entity-level fetcher
    and therefore needing a separate edge traversal step.

    v1: returns filters whose type is in _EDGE_TRAVERSAL_FILTERS.
    Entity-level filters (already consumed by Block 1) and unknown
    filter types are excluded.

    Note: this function used to silently drop unknown filter types
    (the v1 defect surfaced in the Design 3 measurement report).
    _validate_intent_filters is now called from generate_plan before
    this function runs, so unknown types raise before reaching here.
    """
    return [f for f in filters if f.get("type") in _EDGE_TRAVERSAL_FILTERS]


def _filter_target_entity(filter_spec: dict[str, Any]) -> str:
    """
    Given a filter spec, return the entity it constrains.

    Example: {"type": "has_open_PO", ...} -> "PurchaseOrder"

    Raises KeyError if the filter type is unknown to v1.
    """
    filter_type = filter_spec.get("type")
    if filter_type not in _EDGE_TRAVERSAL_FILTERS:
        raise KeyError(
            f"Filter type {filter_type!r} has no edge-traversal target "
            "in v1's mapping table."
        )
    target_entity, _kg_filter_type = _EDGE_TRAVERSAL_FILTERS[filter_type]
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

    v1 only implements ``status_filter``. country_filter_via_address is
    handled by the entity-level fetcher in Block 1, not as a client
    filter.

    Example: {"type": "has_open_PO", ...} on PurchaseOrder
        -> [{"field": "StatusCode", "op": "equals", "value": "OPEN"}]
    """
    intent_filter_type = filter_spec.get("type")
    if intent_filter_type not in _EDGE_TRAVERSAL_FILTERS:
        raise KeyError(
            f"Filter type {intent_filter_type!r} is not an edge-traversal "
            "filter and has no client-filter mapping."
        )
    _target_entity, kg_filter_type = _EDGE_TRAVERSAL_FILTERS[intent_filter_type]

    binding = find_pattern_for_filter(target_entity, kg_filter_type)
    pattern_name = binding["pattern_name"]
    bindings = binding["parameter_bindings"]

    if pattern_name == "status_filter":
        # bindings carry: X (entity), status_field, status_term_param.
        field_name = bindings["status_field"]
        vocab_kind, implicit_term = _EDGE_FILTER_IMPLICIT_VALUES[intent_filter_type]
        canonical = resolve_vocab(vocab_kind, implicit_term)
        return [{"field": field_name, "op": "equals", "value": canonical}]

    # Other patterns (e.g., country_filter_via_address) don't apply
    # as client filters in v1's anchor question. If we get here, the
    # planner is being asked something v1 doesn't cover.
    raise NotImplementedError(
        f"Client-filter construction for pattern {pattern_name!r} "
        "is not implemented in v1."
    )


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
            vocab_kind = _FILTER_VALUE_VOCAB_KIND.get("country")
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
