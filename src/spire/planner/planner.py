"""
Planner stubs for the KG-driven path (Architecture Option 3).

This module is the contract between the LLM intent-parsing step and the
MCP executor. It reads only from the KG (see sql/kg/v1/) and emits a
structured plan. No LLM in the planning step. No prose-reading for
decisions.

Status: DESIGN ONLY. All functions are unimplemented stubs.
Companion design doc: docs/designs/phase_2_planner_design.md

The dataclasses and signatures here must remain in sync with the design
doc. When you implement: write tests against the worked example in the
design doc, then fill in bodies one function at a time, smallest first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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

    Raises if no row found.
    """
    raise NotImplementedError


def find_entity_tool(entity_name: str, filter_type: str) -> str:
    """
    Find the MCP tool that fetches this entity with the given filter type.

    Queries ``kg_entity_tool``. Use ``filter_type='none'`` for the default
    (unfiltered) fetcher.

    Returns the MCP tool name, e.g. ``"search_suppliers_by_country"``.
    Raises if no row found.
    """
    raise NotImplementedError


# ─────────────────────────────────────────────────────────────────────
# KG edge lookups
# ─────────────────────────────────────────────────────────────────────


def find_edge(from_entity: str, to_entity: str) -> dict[str, Any]:
    """
    Look up the edge connecting two entities in ``kg_edge``.

    Returns a dict with keys:
        edge_name, from_join_field, to_join_field,
        cardinality, server_filter_rule, traversal_hint

    Raises if no edge found.
    """
    raise NotImplementedError


def find_edge_tool(edge_name: str) -> str | None:
    """
    Find the MCP tool that traverses this edge in ``kg_edge_tool``.

    Returns the tool name, or ``None`` if the edge has no row
    (e.g. ``HAS_ADDRESS`` is bundled with ``search_suppliers_by_country``
    via ``expand=addresses`` — absence is meaningful).
    """
    raise NotImplementedError


# ─────────────────────────────────────────────────────────────────────
# KG pattern lookups
# ─────────────────────────────────────────────────────────────────────


def find_pattern_for_filter(entity_name: str, filter_type: str) -> dict[str, Any]:
    """
    Find which pattern handles this filter type on this entity.

    Queries ``kg_pattern_binding``. Returns:
        {"pattern_name": <str>, "parameter_bindings": <dict>}

    ``parameter_bindings`` is parsed from the JSON stored in the table.
    Raises if no binding found.
    """
    raise NotImplementedError


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

    Raises if no row found (caller must handle unknown terms).
    """
    raise NotImplementedError


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

    Tracing the anchor question through this orchestrator must produce
    the 3-step plan shown in the design doc.
    """
    raise NotImplementedError


# ─────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────


def _pick_entity_filter(filters: list[dict[str, Any]]) -> str:
    """
    Decide which filter (if any) has a dedicated entity-level fetcher tool.

    Returns the filter type as a string, or ``'none'`` if no filter has a
    dedicated fetcher. Examples:
        [{"type": "country", ...}, {"type": "has_open_PO", ...}] -> 'country'
        [{"type": "has_open_PO", ...}]                            -> 'none'

    Implementation note: cross-references against ``kg_entity_tool`` rows.
    """
    raise NotImplementedError


def _build_fetcher_args(
    filter_type: str, filters: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Build the ``tool_args`` dict for the entity-level fetcher.

    Resolves the filter's value through ``resolve_vocab`` if applicable.
    Example: filter_type='country', filter value='US' -> {"country": "US"}.
    """
    raise NotImplementedError


def _filters_needing_edge_traversal(
    filters: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Return the subset of filters not handled by the entity-level fetcher
    and therefore needing a separate edge traversal step.
    """
    raise NotImplementedError


def _filter_target_entity(filter_spec: dict[str, Any]) -> str:
    """
    Given a filter spec, return the entity it constrains.

    Example: {"type": "has_open_PO", ...} -> "PurchaseOrder"
    """
    raise NotImplementedError


def _resolve_client_filters(
    filter_spec: dict[str, Any], target_entity: str
) -> list[dict[str, Any]]:
    """
    Translate a filter spec into the list of client-side filters to apply
    after the tool call.

    Internally calls ``find_pattern_for_filter``, parses the pattern's
    ``parameter_bindings``, resolves vocab values, and constructs the
    filter list in the ``{field, op, value}`` shape.

    Example: {"type": "has_open_PO", ...} on PurchaseOrder
        -> [{"field": "StatusCode", "op": "equals", "value": "OPEN"}]
    """
    raise NotImplementedError


def _arg_name_for_tool(tool_name: str) -> str:
    """
    Return the argument name the given MCP tool expects for its primary
    input.

    Examples:
        search_purchase_orders -> 'supplier_id'
        get_buyer              -> 'buyer_id'
        search_invoices        -> 'supplier_number'

    Implementation note: in v1 this can be a static dict keyed by tool
    name. In v2 it may want to live in the KG itself.
    """
    raise NotImplementedError


def _make_output_name(entity_name: str) -> str:
    """
    Stable, readable output name for a step's results.

    Examples:
        Supplier      -> 'us_suppliers' (or similar — depends on context)
        PurchaseOrder -> 'open_pos'
        Buyer         -> 'buyers'

    Implementation note: pure naming convention; the executor doesn't
    interpret these, only references them.
    """
    raise NotImplementedError


def _previous_entity(plan: Plan) -> str:
    """
    Return the entity name that the previous step's output represents.

    Needed when adding include-lookup steps: the planner must know what
    entity to traverse *from*.
    """
    raise NotImplementedError
