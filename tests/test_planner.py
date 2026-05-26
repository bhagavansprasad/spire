"""
Tests for the planner.

Three kinds of tests live here:

1. Contract tests for the dataclasses (Intent, Step, Plan) — no DB
   required. These verify the design doc and the stub file stay in sync.

2. Live KG tests for the lookup layer (resolve_vocab, find_entity,
   find_entity_tool, find_edge, find_edge_tool, find_pattern_for_filter).

3. Helper + orchestrator tests, culminating in the end-to-end
   anchor-question trace. The orchestrator test is the headline:
   generate_plan(anchor_intent) must equal anchor_plan.

If KG-dependent tests fail, run ./scripts/rebuild_kg.sh to reload seed
data.
"""

import pytest

from spire.planner.planner import (
    Intent,
    Plan,
    Step,
    _arg_name_for_tool,
    _build_fetcher_args,
    _filter_target_entity,
    _filters_needing_edge_traversal,
    _make_output_name,
    _pick_entity_filter,
    _resolve_client_filters,
    find_edge,
    find_edge_tool,
    find_entity,
    find_entity_tool,
    find_pattern_for_filter,
    generate_plan,
    resolve_vocab,
)


# ─────────────────────────────────────────────────────────────────────
# Anchor question — the worked example from the design doc
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def anchor_intent() -> Intent:
    """
    The structured intent produced by the LLM parser for the anchor
    question: 'Show me suppliers in US with open purchase orders,
    including the buyer assigned to each.'
    """
    return Intent(
        target_entity="Supplier",
        filters=[
            {"type": "country", "value": "US"},
            {"type": "has_open_PO", "value": True},
        ],
        include=["Buyer"],
    )


@pytest.fixture
def anchor_plan() -> Plan:
    """
    The plan that generate_plan(anchor_intent) must eventually produce.
    Mirrors the worked example in docs/designs/phase_2_planner_design.md.
    """
    return [
        Step(
            step_id=1,
            tool_name="search_suppliers_by_country",
            tool_args={"country": "US"},
            iterate_over=None,
            client_filters=[],
            output_name="us_suppliers",
            output_dedupe_by=None,
        ),
        Step(
            step_id=2,
            tool_name="search_purchase_orders",
            tool_args={"supplier_id": "$iteration_value"},
            iterate_over={"from_step": "us_suppliers", "field": "SupplierId"},
            client_filters=[
                {"field": "StatusCode", "op": "equals", "value": "OPEN"},
            ],
            output_name="open_pos",
            output_dedupe_by=None,
        ),
        Step(
            step_id=3,
            tool_name="get_buyer",
            tool_args={"buyer_id": "$iteration_value"},
            iterate_over={"from_step": "open_pos", "field": "BuyerId"},
            client_filters=[],
            output_name="buyers",
            output_dedupe_by="BuyerId",
        ),
    ]


# ─────────────────────────────────────────────────────────────────────
# Dataclass contract tests (no DB)
# ─────────────────────────────────────────────────────────────────────


def test_intent_dataclass_matches_design(anchor_intent: Intent) -> None:
    """The Intent dataclass accepts the fields the design doc requires."""
    assert anchor_intent.target_entity == "Supplier"
    assert len(anchor_intent.filters) == 2
    assert anchor_intent.include == ["Buyer"]


def test_step_dataclass_matches_design(anchor_plan: Plan) -> None:
    """The Step dataclass accepts every field the design doc requires."""
    step1 = anchor_plan[0]
    assert step1.step_id == 1
    assert step1.tool_name == "search_suppliers_by_country"
    assert step1.tool_args == {"country": "US"}
    assert step1.iterate_over is None
    assert step1.client_filters == []
    assert step1.output_name == "us_suppliers"
    assert step1.output_dedupe_by is None


def test_plan_is_a_list_of_steps(anchor_plan: Plan) -> None:
    """Plan is just list[Step]; tests confirm the alias works."""
    assert isinstance(anchor_plan, list)
    assert all(isinstance(s, Step) for s in anchor_plan)
    assert len(anchor_plan) == 3


def test_anchor_plan_tool_names_match_kg(anchor_plan: Plan) -> None:
    """Tool names referenced in the plan must be the MCP tools we have."""
    expected_tools = [
        "search_suppliers_by_country",
        "search_purchase_orders",
        "get_buyer",
    ]
    assert [step.tool_name for step in anchor_plan] == expected_tools


def test_iteration_value_sentinel_used(anchor_plan: Plan) -> None:
    """
    Iterating steps use the '$iteration_value' sentinel in tool_args
    (the Option-b choice from 2b).
    """
    step2 = anchor_plan[1]
    step3 = anchor_plan[2]
    assert step2.tool_args["supplier_id"] == "$iteration_value"
    assert step3.tool_args["buyer_id"] == "$iteration_value"


def test_step3_dedupes_on_join_field(anchor_plan: Plan) -> None:
    """Buyer lookup must dedupe BuyerId before iterating, per the design."""
    step3 = anchor_plan[2]
    assert step3.output_dedupe_by == "BuyerId"


def test_step_ids_are_sequential(anchor_plan: Plan) -> None:
    """Step IDs increment by 1 starting from 1."""
    assert [s.step_id for s in anchor_plan] == [1, 2, 3]


# ─────────────────────────────────────────────────────────────────────
# resolve_vocab — live KG tests
#
# Hit the live KG (oracle26ai_db_bhagavan container). Seed data lives in
# scripts/rebuild_kg.sh. If these fail, run ./scripts/rebuild_kg.sh first
# to ensure the vocabulary is loaded.
# ─────────────────────────────────────────────────────────────────────


def test_resolve_vocab_country_canonical() -> None:
    """Canonical form ('US') resolves to itself."""
    assert resolve_vocab("country", "US") == "US"


def test_resolve_vocab_country_three_letter() -> None:
    """'USA' resolves to canonical 'US'."""
    assert resolve_vocab("country", "USA") == "US"


def test_resolve_vocab_country_full_name() -> None:
    """'United States' resolves to 'US'."""
    assert resolve_vocab("country", "United States") == "US"


def test_resolve_vocab_country_full_formal_name() -> None:
    """'United States of America' resolves to 'US'."""
    assert resolve_vocab("country", "United States of America") == "US"


def test_resolve_vocab_status_open() -> None:
    """'open' resolves to canonical 'OPEN'."""
    assert resolve_vocab("po_status", "open") == "OPEN"


def test_resolve_vocab_status_synonym() -> None:
    """'active' (synonym for open) resolves to 'OPEN'."""
    assert resolve_vocab("po_status", "active") == "OPEN"


def test_resolve_vocab_british_spelling() -> None:
    """British 'cancelled' resolves to American 'CANCELED'."""
    assert resolve_vocab("po_status", "cancelled") == "CANCELED"


def test_resolve_vocab_unknown_term_raises_key_error() -> None:
    """Unknown term raises KeyError."""
    with pytest.raises(KeyError):
        resolve_vocab("country", "Atlantis")


def test_resolve_vocab_unknown_kind_raises_key_error() -> None:
    """Unknown vocab_kind raises KeyError (no matching row)."""
    with pytest.raises(KeyError):
        resolve_vocab("nonexistent_kind", "US")


def test_resolve_vocab_is_case_sensitive() -> None:
    """Lowercase 'us' does not match (case-sensitive by design)."""
    with pytest.raises(KeyError):
        resolve_vocab("country", "us")


# ─────────────────────────────────────────────────────────────────────
# find_entity — live KG tests
# ─────────────────────────────────────────────────────────────────────


def test_find_entity_supplier_returns_endpoint_and_id_fields() -> None:
    """Supplier has the canonical fields and the FSCM endpoint."""
    result = find_entity("Supplier")
    assert result["endpoint_path"] == "/fscmRestApi/resources/11.13.18.05/suppliers"
    assert result["canonical_id_field"] == "SupplierId"
    assert result["display_name_field"] == "Supplier"
    assert isinstance(result["description"], str)
    assert len(result["description"]) > 0


def test_find_entity_invoice_returns_canonical_fields() -> None:
    """Invoice's canonical id is InvoiceId, display id is InvoiceNumber."""
    result = find_entity("Invoice")
    assert result["endpoint_path"] == "/fscmRestApi/resources/11.13.18.05/invoices"
    assert result["canonical_id_field"] == "InvoiceId"
    assert result["display_name_field"] == "InvoiceNumber"


def test_find_entity_buyer_uses_hcm_endpoint() -> None:
    """Buyer's endpoint is on HCM, not FSCM. This is the cross-pillar
    detail the KG must surface."""
    result = find_entity("Buyer")
    assert result["endpoint_path"] == (
        "/hcmRestApi/resources/11.13.18.05/publicWorkers"
    )
    assert result["canonical_id_field"] == "PersonId"


def test_find_entity_address_has_no_display_name() -> None:
    """Address has no display name field (display_name_field is NULL)."""
    result = find_entity("Address")
    assert result["display_name_field"] is None


def test_find_entity_unknown_raises_key_error() -> None:
    """Unknown entity name raises KeyError."""
    with pytest.raises(KeyError):
        find_entity("UnicornEntity")


def test_find_entity_is_case_sensitive() -> None:
    """Lowercase 'supplier' does not match 'Supplier' (case-sensitive)."""
    with pytest.raises(KeyError):
        find_entity("supplier")


# ─────────────────────────────────────────────────────────────────────
# find_entity_tool — live KG tests
# ─────────────────────────────────────────────────────────────────────


def test_find_entity_tool_default_supplier_fetcher() -> None:
    """filter_type='none' returns the default Supplier fetcher."""
    assert find_entity_tool("Supplier", "none") == "search_suppliers"


def test_find_entity_tool_country_filter_uses_specialised_tool() -> None:
    """filter_type='country' returns the country-aware Supplier fetcher."""
    assert (
        find_entity_tool("Supplier", "country")
        == "search_suppliers_by_country"
    )


def test_find_entity_tool_unknown_entity_raises_key_error() -> None:
    """Unknown entity_name raises KeyError."""
    with pytest.raises(KeyError):
        find_entity_tool("UnicornEntity", "none")


def test_find_entity_tool_unknown_filter_type_raises_key_error() -> None:
    """Unknown filter_type for a known entity raises KeyError."""
    with pytest.raises(KeyError):
        find_entity_tool("Supplier", "color")


def test_find_entity_tool_no_default_fetcher_for_invoice_raises() -> None:
    """v1 only declares fetchers for Supplier. Invoice has none —
    invoices are reached via the HAS_INVOICE edge instead. Confirms
    absence is meaningful: raise rather than silently return."""
    with pytest.raises(KeyError):
        find_entity_tool("Invoice", "none")


# ─────────────────────────────────────────────────────────────────────
# find_edge — live KG tests
# ─────────────────────────────────────────────────────────────────────


def test_find_edge_has_invoice_uses_supplier_number() -> None:
    """HAS_INVOICE joins via SupplierNumber, not SupplierId.
    This is the asymmetry that crashed Track A."""
    result = find_edge("Supplier", "Invoice")
    assert result["edge_name"] == "HAS_INVOICE"
    assert result["from_join_field"] == "SupplierNumber"
    assert result["to_join_field"] == "SupplierNumber"
    assert result["cardinality"] == "one_to_many"
    assert result["server_filter_rule"] == "join_only"


def test_find_edge_has_purchase_order_uses_supplier_id() -> None:
    """HAS_PURCHASE_ORDER joins via SupplierId (numeric), not SupplierNumber.
    The other half of the Track A asymmetry."""
    result = find_edge("Supplier", "PurchaseOrder")
    assert result["edge_name"] == "HAS_PURCHASE_ORDER"
    assert result["from_join_field"] == "SupplierId"
    assert result["to_join_field"] == "SupplierId"
    assert result["cardinality"] == "one_to_many"


def test_find_edge_assigned_to_crosses_pillars() -> None:
    """PurchaseOrder -> Buyer crosses FSCM -> HCM. The notes field
    must call this out explicitly."""
    result = find_edge("PurchaseOrder", "Buyer")
    assert result["edge_name"] == "ASSIGNED_TO"
    assert result["from_join_field"] == "BuyerId"
    assert result["to_join_field"] == "PersonId"
    assert result["cardinality"] == "many_to_one"
    assert "CROSS-PILLAR" in (result["notes"] or "").upper()


def test_find_edge_has_address_uses_expand() -> None:
    """HAS_ADDRESS is a parent-child relationship traversed via
    expand=addresses, not a separate query."""
    result = find_edge("Supplier", "Address")
    assert result["edge_name"] == "HAS_ADDRESS"
    assert "expand=addresses" in (result["traversal_hint"] or "")


def test_find_edge_reverse_direction_raises_key_error() -> None:
    """Edges are directional. v1 declares Supplier -> PurchaseOrder but
    NOT PurchaseOrder -> Supplier. Reverse lookup must raise."""
    with pytest.raises(KeyError):
        find_edge("PurchaseOrder", "Supplier")


def test_find_edge_nonexistent_raises_key_error() -> None:
    """Two entities with no declared edge raises KeyError."""
    with pytest.raises(KeyError):
        find_edge("Buyer", "Invoice")


# ─────────────────────────────────────────────────────────────────────
# find_edge_tool — live KG tests
# ─────────────────────────────────────────────────────────────────────


def test_find_edge_tool_has_invoice() -> None:
    """HAS_INVOICE is traversed by search_invoices."""
    assert find_edge_tool("HAS_INVOICE") == "search_invoices"


def test_find_edge_tool_has_purchase_order() -> None:
    """HAS_PURCHASE_ORDER is traversed by search_purchase_orders."""
    assert find_edge_tool("HAS_PURCHASE_ORDER") == "search_purchase_orders"


def test_find_edge_tool_assigned_to() -> None:
    """ASSIGNED_TO (PO -> Buyer) uses get_buyer."""
    assert find_edge_tool("ASSIGNED_TO") == "get_buyer"


def test_find_edge_tool_has_address_returns_none() -> None:
    """HAS_ADDRESS deliberately has no row in kg_edge_tool.
    Addresses come bundled with search_suppliers_by_country via
    expand=addresses; absence of a row is meaningful."""
    assert find_edge_tool("HAS_ADDRESS") is None


def test_find_edge_tool_unknown_edge_returns_none() -> None:
    """Unknown edge name also returns None (same shape as 'no row')."""
    assert find_edge_tool("NONEXISTENT_EDGE") is None


# ─────────────────────────────────────────────────────────────────────
# find_pattern_for_filter — live KG tests
# ─────────────────────────────────────────────────────────────────────


def test_find_pattern_for_filter_country_on_supplier() -> None:
    """The country filter on Supplier binds to country_filter_via_address."""
    result = find_pattern_for_filter("Supplier", "country")
    assert result["pattern_name"] == "country_filter_via_address"
    bindings = result["parameter_bindings"]
    # parameter_bindings should be a parsed dict, not a string.
    assert isinstance(bindings, dict)
    assert bindings["parent"] == "Supplier"
    assert bindings["child_edge"] == "HAS_ADDRESS"
    assert bindings["country_term_param"] == "country"


def test_find_pattern_for_filter_status_on_po() -> None:
    """The status filter on PurchaseOrder binds to status_filter."""
    result = find_pattern_for_filter("PurchaseOrder", "status")
    assert result["pattern_name"] == "status_filter"
    bindings = result["parameter_bindings"]
    assert isinstance(bindings, dict)
    assert bindings["X"] == "PurchaseOrder"
    assert bindings["status_field"] == "StatusCode"
    assert bindings["status_term_param"] == "status"


def test_find_pattern_for_filter_parameter_bindings_is_parsed_json() -> None:
    """parameter_bindings comes back as a Python dict, not a JSON string.
    Callers should never have to call json.loads themselves."""
    result = find_pattern_for_filter("Supplier", "country")
    assert isinstance(result["parameter_bindings"], dict)
    # Verify a key with type-string value to confirm it's structured data.
    assert isinstance(result["parameter_bindings"]["parent"], str)


def test_find_pattern_for_filter_unknown_entity_raises() -> None:
    """No pattern binding for an unknown entity raises KeyError."""
    with pytest.raises(KeyError):
        find_pattern_for_filter("UnicornEntity", "country")


def test_find_pattern_for_filter_unknown_filter_type_raises() -> None:
    """No pattern binding for an unknown filter_type raises KeyError."""
    with pytest.raises(KeyError):
        find_pattern_for_filter("Supplier", "color")


def test_find_pattern_for_filter_no_binding_for_status_on_supplier() -> None:
    """v1 only binds status to PurchaseOrder, not Supplier.
    Confirms that bindings are entity-specific."""
    with pytest.raises(KeyError):
        find_pattern_for_filter("Supplier", "status")


# ─────────────────────────────────────────────────────────────────────
# Helpers — focused unit tests (mostly no DB)
# ─────────────────────────────────────────────────────────────────────


def test_pick_entity_filter_finds_country() -> None:
    """Among mixed filters, the country filter is the entity-level one."""
    filters = [
        {"type": "country", "value": "US"},
        {"type": "has_open_PO", "value": True},
    ]
    assert _pick_entity_filter(filters) == "country"


def test_pick_entity_filter_returns_none_when_no_match() -> None:
    """If no filter has a dedicated fetcher, returns the literal 'none'."""
    filters = [{"type": "has_open_PO", "value": True}]
    assert _pick_entity_filter(filters) == "none"


def test_pick_entity_filter_empty_returns_none() -> None:
    """An intent with no filters returns 'none'."""
    assert _pick_entity_filter([]) == "none"


def test_build_fetcher_args_none_returns_empty() -> None:
    """filter_type='none' produces an empty arg dict."""
    assert _build_fetcher_args("none", []) == {}


def test_build_fetcher_args_country_canonical_passthrough() -> None:
    """Already-canonical 'US' resolves to 'US' (a real KG lookup)."""
    filters = [{"type": "country", "value": "US"}]
    assert _build_fetcher_args("country", filters) == {"country": "US"}


def test_build_fetcher_args_country_normalizes_full_name() -> None:
    """Full name 'United States' normalizes to 'US' via vocab."""
    filters = [{"type": "country", "value": "United States"}]
    assert _build_fetcher_args("country", filters) == {"country": "US"}


def test_filters_needing_edge_traversal_returns_only_traversal_filters() -> None:
    """country (entity-level) is excluded; has_open_PO (edge-level) is kept."""
    filters = [
        {"type": "country", "value": "US"},
        {"type": "has_open_PO", "value": True},
    ]
    result = _filters_needing_edge_traversal(filters)
    assert result == [{"type": "has_open_PO", "value": True}]


def test_filters_needing_edge_traversal_empty_for_country_only() -> None:
    """A filter list with only entity-level filters yields no traversals."""
    filters = [{"type": "country", "value": "US"}]
    assert _filters_needing_edge_traversal(filters) == []


def test_filter_target_entity_has_open_po_maps_to_purchase_order() -> None:
    """has_open_PO is a filter on the PurchaseOrder entity."""
    spec = {"type": "has_open_PO", "value": True}
    assert _filter_target_entity(spec) == "PurchaseOrder"


def test_filter_target_entity_unknown_raises() -> None:
    """Unknown filter types raise KeyError — v1 is explicit about scope."""
    with pytest.raises(KeyError):
        _filter_target_entity({"type": "unknown_filter", "value": "x"})


def test_resolve_client_filters_has_open_po_produces_status_filter() -> None:
    """has_open_PO on PurchaseOrder produces a StatusCode==OPEN client filter.

    This is the headline behavior: intent vocabulary ('has_open_PO') becomes
    KG-pattern-driven client filter ('StatusCode' field, 'OPEN' canonical
    value).
    """
    spec = {"type": "has_open_PO", "value": True}
    result = _resolve_client_filters(spec, "PurchaseOrder")
    assert result == [
        {"field": "StatusCode", "op": "equals", "value": "OPEN"}
    ]


def test_resolve_client_filters_unknown_filter_raises() -> None:
    """Unknown filter type raises KeyError before hitting the KG."""
    with pytest.raises(KeyError):
        _resolve_client_filters(
            {"type": "unknown_filter", "value": "x"}, "PurchaseOrder"
        )


def test_arg_name_for_tool_search_purchase_orders() -> None:
    """search_purchase_orders takes supplier_id as primary arg."""
    assert _arg_name_for_tool("search_purchase_orders") == "supplier_id"


def test_arg_name_for_tool_get_buyer() -> None:
    """get_buyer takes buyer_id as primary arg."""
    assert _arg_name_for_tool("get_buyer") == "buyer_id"


def test_arg_name_for_tool_search_invoices() -> None:
    """search_invoices takes supplier_number (not supplier_id) — the
    SupplierNumber/SupplierId asymmetry the planner must carry forward."""
    assert _arg_name_for_tool("search_invoices") == "supplier_number"


def test_arg_name_for_tool_unknown_raises() -> None:
    """Unknown tool name raises KeyError so the gap is loud, not silent."""
    with pytest.raises(KeyError):
        _arg_name_for_tool("nonexistent_tool")


def test_make_output_name_country_filtered_supplier() -> None:
    """Country-filtered Supplier fetch produces 'us_suppliers'."""
    filters = [{"type": "country", "value": "US"}]
    assert _make_output_name("Supplier", "country", filters) == "us_suppliers"


def test_make_output_name_country_full_name_normalized() -> None:
    """'United States' as the country value still produces 'us_suppliers'."""
    filters = [{"type": "country", "value": "United States"}]
    assert _make_output_name("Supplier", "country", filters) == "us_suppliers"


def test_make_output_name_purchase_order_special_cased() -> None:
    """v1 special-cases PurchaseOrder as 'open_pos' to match anchor plan."""
    assert _make_output_name("PurchaseOrder", None, []) == "open_pos"


def test_make_output_name_buyer_plural() -> None:
    """Buyer becomes 'buyers' via the default convention."""
    assert _make_output_name("Buyer", None, []) == "buyers"


# ─────────────────────────────────────────────────────────────────────
# Orchestrator — end-to-end against the anchor question (live KG)
# ─────────────────────────────────────────────────────────────────────


def test_generate_plan_anchor_question_produces_expected_plan(
    anchor_intent: Intent, anchor_plan: Plan
) -> None:
    """
    The headline test: generate_plan(anchor_intent) must equal anchor_plan
    step-by-step.

    If this passes, the whole planning layer is correct end-to-end for v1.
    """
    produced = generate_plan(anchor_intent)
    assert produced == anchor_plan


def test_generate_plan_anchor_step_count(anchor_intent: Intent) -> None:
    """Anchor intent must produce exactly 3 steps."""
    produced = generate_plan(anchor_intent)
    assert len(produced) == 3


def test_generate_plan_anchor_step_ids_sequential(anchor_intent: Intent) -> None:
    """Step IDs are 1, 2, 3 in order."""
    produced = generate_plan(anchor_intent)
    assert [s.step_id for s in produced] == [1, 2, 3]


def test_generate_plan_step1_no_iteration(anchor_intent: Intent) -> None:
    """Step 1 (entity fetch) never iterates over a previous output."""
    produced = generate_plan(anchor_intent)
    assert produced[0].iterate_over is None


def test_generate_plan_step2_iterates_supplier_id(anchor_intent: Intent) -> None:
    """Step 2 iterates SupplierId from Step 1's output — the Track A asymmetry
    that the KG encodes."""
    produced = generate_plan(anchor_intent)
    step2 = produced[1]
    assert step2.iterate_over == {
        "from_step": "us_suppliers", "field": "SupplierId"
    }


def test_generate_plan_step2_client_filter_is_open_status(
    anchor_intent: Intent,
) -> None:
    """Step 2's status filter is client-side, with the canonical 'OPEN' value."""
    produced = generate_plan(anchor_intent)
    step2 = produced[1]
    assert step2.client_filters == [
        {"field": "StatusCode", "op": "equals", "value": "OPEN"}
    ]


def test_generate_plan_step3_dedupes_buyer_id(anchor_intent: Intent) -> None:
    """Step 3 dedupes on BuyerId so the same buyer isn't looked up twice."""
    produced = generate_plan(anchor_intent)
    step3 = produced[2]
    assert step3.output_dedupe_by == "BuyerId"


def test_generate_plan_country_full_name_normalizes_to_us() -> None:
    """An intent with 'United States' as the country value produces the
    same plan as 'US' — vocab normalization happens in the planner."""
    intent = Intent(
        target_entity="Supplier",
        filters=[
            {"type": "country", "value": "United States"},
            {"type": "has_open_PO", "value": True},
        ],
        include=["Buyer"],
    )
    produced = generate_plan(intent)
    # Step 1's tool args should carry the canonical 'US' (not 'United States').
    assert produced[0].tool_args == {"country": "US"}
    # Step 1's output name should also normalize to 'us_suppliers'.
    assert produced[0].output_name == "us_suppliers"
