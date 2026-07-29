"""
Tests for the planner.

Three kinds of tests live here:

1. Contract tests for the dataclasses (Intent, Step, Plan) — no DB
   required. These verify the design doc and the stub file stay in sync.

2. Live KG tests for the lookup layer (resolve_vocab, find_entity,
   find_entity_tool, find_edge, find_edge_tool, find_pattern_for_filter).

3. Helper + orchestrator tests, culminating in the end-to-end
   anchor-question trace AND the original-prompt trace. The orchestrator
   tests are the headlines.

If KG-dependent tests fail, run ./scripts/rebuild_kg.sh to reload seed
data.
"""

from datetime import date

import pytest

from spire.planner.planner import (
    Intent,
    Plan,
    Step,
    _arg_name_for_tool,
    _build_entity_fetcher_args,
    _build_iteration_args_with_computed,
    _compute_date_n_months_ago,
    _filter_target_entity,
    _filters_needing_edge_traversal,
    _make_filtered_source_output_name,
    _make_output_name,
    _pick_entity_filter,
    _resolve_client_filters,
    _validate_intent_filters,
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
            tool_name="search_suppliers",
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


@pytest.fixture
def original_track_a_intent() -> Intent:
    """
    The structured intent for the original Track A prompt
    (with the 'no invoices in 6 months' negation clause).
    """
    return Intent(
        target_entity="Supplier",
        filters=[
            {"type": "country", "value": "US"},
            {"type": "has_no_recent_invoices", "value": {"months": 6}},
            {"type": "has_open_PO", "value": True},
        ],
        include=["Buyer"],
    )


@pytest.fixture
def fixed_reference_date() -> date:
    """A fixed date for testable date arithmetic. 2026-05-26."""
    return date(2026, 5, 26)


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
    assert step1.tool_name == "search_suppliers"
    assert step1.tool_args == {"country": "US"}
    assert step1.iterate_over is None
    assert step1.client_filters == []
    assert step1.output_name == "us_suppliers"
    assert step1.output_dedupe_by is None
    # F2 addition: filter_source_when_empty defaults to False
    # so existing Steps stay compatible.
    assert step1.filter_source_when_empty is False


def test_step_dataclass_accepts_filter_source_when_empty() -> None:
    """F2: Step can be constructed with filter_source_when_empty=True."""
    s = Step(
        step_id=1,
        tool_name="search_invoices",
        tool_args={"supplier_number": "$iteration_value"},
        iterate_over={"from_step": "us_suppliers", "field": "SupplierNumber"},
        client_filters=[],
        output_name="us_suppliers_no_recent_invoices",
        output_dedupe_by=None,
        filter_source_when_empty=True,
    )
    assert s.filter_source_when_empty is True


def test_plan_is_a_list_of_steps(anchor_plan: Plan) -> None:
    """Plan is just list[Step]; tests confirm the alias works."""
    assert isinstance(anchor_plan, list)
    assert all(isinstance(s, Step) for s in anchor_plan)
    assert len(anchor_plan) == 3


def test_anchor_plan_tool_names_match_kg(anchor_plan: Plan) -> None:
    """Tool names referenced in the plan must be the MCP tools we have."""
    expected_tools = [
        "search_suppliers",
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


def test_resolve_vocab_is_case_insensitive() -> None:
    """Lowercase 'us' matches; vocab lookup is case-insensitive on the term."""
    assert resolve_vocab("country", "us") == "US"


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


def test_find_entity_tool_country_has_no_dedicated_tool() -> None:
    """Country no longer has its own fetcher; it routes through the
    default search_suppliers with combined args. So there is no
    (Supplier, country) row in kg_entity_tool."""
    with pytest.raises(KeyError):
        find_entity_tool("Supplier", "country")


def test_find_entity_tool_unknown_entity_raises_key_error() -> None:
    """Unknown entity_name raises KeyError."""
    with pytest.raises(KeyError):
        find_entity_tool("UnicornEntity", "none")


def test_find_entity_tool_unknown_filter_type_raises_key_error() -> None:
    """Unknown filter_type for a known entity raises KeyError."""
    with pytest.raises(KeyError):
        find_entity_tool("Supplier", "color")


def test_find_entity_tool_default_invoice_fetcher() -> None:
    """Invoice has a default fetcher (search_invoices); Phase 4 made it
    a queryable target."""
    assert find_entity_tool("Invoice", "none") == "search_invoices"


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
    Addresses come bundled with search_suppliers via expand=addresses
    when a country filter is present; absence of a row is meaningful."""
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


def test_find_pattern_for_filter_no_recent_invoices_on_supplier() -> None:
    """F2: The no_recent_invoices filter on Supplier binds to
    no_child_in_N_months."""
    result = find_pattern_for_filter("Supplier", "no_recent_invoices")
    assert result["pattern_name"] == "no_child_in_N_months"
    bindings = result["parameter_bindings"]
    assert isinstance(bindings, dict)
    assert bindings["parent"] == "Supplier"
    assert bindings["child_edge"] == "HAS_INVOICE"
    assert bindings["date_field"] == "InvoiceDate"
    assert bindings["months_param"] == "months"


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
    assert _pick_entity_filter(filters, "Supplier") == "country"


def test_pick_entity_filter_returns_none_when_no_match() -> None:
    """If no filter has a dedicated fetcher, returns the literal 'none'."""
    filters = [{"type": "has_open_PO", "value": True}]
    assert _pick_entity_filter(filters, "Supplier") == "none"


def test_pick_entity_filter_empty_returns_none() -> None:
    """An intent with no filters returns 'none'."""
    assert _pick_entity_filter([], "Supplier") == "none"


def test_build_entity_fetcher_args_empty_returns_empty() -> None:
    """No filters produces an empty arg dict."""
    assert _build_entity_fetcher_args([], "Supplier") == {}


def test_build_entity_fetcher_args_country_canonical_passthrough() -> None:
    """Already-canonical 'US' resolves to 'US' (a real KG lookup)."""
    filters = [{"type": "country", "value": "US"}]
    assert _build_entity_fetcher_args(filters, "Supplier") == {"country": "US"}


def test_build_entity_fetcher_args_country_normalizes_full_name() -> None:
    """Full name 'United States' normalizes to 'US' via vocab."""
    filters = [{"type": "country", "value": "United States"}]
    assert _build_entity_fetcher_args(filters, "Supplier") == {"country": "US"}


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


def test_filters_needing_edge_traversal_includes_no_recent_invoices() -> None:
    """F2: has_no_recent_invoices is an edge-traversal filter, kept."""
    filters = [
        {"type": "country", "value": "US"},
        {"type": "has_no_recent_invoices", "value": {"months": 6}},
        {"type": "has_open_PO", "value": True},
    ]
    result = _filters_needing_edge_traversal(filters)
    assert len(result) == 2
    assert result[0]["type"] == "has_no_recent_invoices"
    assert result[1]["type"] == "has_open_PO"


def test_filter_target_entity_has_open_po_maps_to_purchase_order() -> None:
    """has_open_PO is a filter on the PurchaseOrder entity."""
    spec = {"type": "has_open_PO", "value": True}
    assert _filter_target_entity(spec) == "PurchaseOrder"


def test_filter_target_entity_has_no_recent_invoices_maps_to_invoice() -> None:
    """F2: has_no_recent_invoices targets the Invoice entity (the
    child being checked for absence)."""
    spec = {"type": "has_no_recent_invoices", "value": {"months": 6}}
    assert _filter_target_entity(spec) == "Invoice"


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
# _validate_intent_filters — unit tests (F1)
# ─────────────────────────────────────────────────────────────────────


def test_validate_intent_filters_accepts_all_known_types() -> None:
    """A mix of supported entity-level and edge-traversal filter types
    passes validation without raising."""
    filters = [
        {"type": "country", "value": "US"},
        {"type": "has_open_PO", "value": True},
    ]
    # Should not raise.
    _validate_intent_filters(filters, "Supplier")


def test_validate_intent_filters_accepts_all_known_types_including_no_recent() -> None:
    """F2: has_no_recent_invoices is now also a known type."""
    filters = [
        {"type": "country", "value": "US"},
        {"type": "has_no_recent_invoices", "value": {"months": 6}},
        {"type": "has_open_PO", "value": True},
    ]
    _validate_intent_filters(filters, "Supplier")


def test_validate_intent_filters_accepts_empty_list() -> None:
    """No filters at all is a valid intent shape (e.g., a fetch-all).
    Validation passes."""
    _validate_intent_filters([], "Supplier")


def test_validate_intent_filters_raises_on_single_unknown_type() -> None:
    """An unknown filter type raises NotImplementedError naming the type."""
    filters = [{"type": "is_strategic_supplier", "value": True}]
    with pytest.raises(NotImplementedError) as exc_info:
        _validate_intent_filters(filters, "Supplier")
    assert "is_strategic_supplier" in str(exc_info.value)


def test_validate_intent_filters_lists_all_unknown_types_at_once() -> None:
    """If multiple unknown filter types are present, the error message
    lists ALL of them — the user shouldn't have to fix one at a time."""
    filters = [
        {"type": "country", "value": "US"},          # known
        {"type": "is_strategic_supplier", "value": True},   # unknown
        {"type": "has_open_PO", "value": True},      # known
        {"type": "is_diversity_supplier", "value": True},   # unknown
    ]
    with pytest.raises(NotImplementedError) as exc_info:
        _validate_intent_filters(filters, "Supplier")
    msg = str(exc_info.value)
    assert "is_strategic_supplier" in msg
    assert "is_diversity_supplier" in msg


def test_validate_intent_filters_error_message_names_supported_types() -> None:
    """The error message must point the caller at what IS supported,
    so the gap is actionable, not just a 'no'."""
    filters = [{"type": "is_strategic_supplier", "value": True}]
    with pytest.raises(NotImplementedError) as exc_info:
        _validate_intent_filters(filters, "Supplier")
    msg = str(exc_info.value)
    assert "country" in msg          # entity-level support listed
    assert "has_open_PO" in msg      # edge-traversal support listed
    assert "has_no_recent_invoices" in msg  # F2: now also supported


def test_generate_plan_raises_on_unknown_filter_type() -> None:
    """End-to-end: generate_plan must propagate the validation error."""
    intent = Intent(
        target_entity="Supplier",
        filters=[
            {"type": "country", "value": "US"},
            {"type": "is_strategic_supplier", "value": True},
            {"type": "has_open_PO", "value": True},
        ],
        include=["Buyer"],
    )
    with pytest.raises(NotImplementedError) as exc_info:
        generate_plan(intent)
    assert "is_strategic_supplier" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────
# W1 — refusal quality: guards run BEFORE filter validation
#
# An intent naming a filter an entity does not support is often really a
# missing-root-reference intent in disguise. "show details for invoice
# number LEE-01-1006-111" parses to Invoice + by_id, but what the user
# needs to hear is "name the supplier" — not a dump of internal filter
# names. Validation used to run first and win every time.
# ─────────────────────────────────────────────────────────────────────


def test_invoice_by_id_reaches_the_supplier_guard() -> None:
    """Invoice + by_id hits the supplier guard (ValueError with a worked
    example), NOT the filter-validation dump."""
    intent = Intent(
        target_entity="Invoice",
        filters=[{"type": "by_id", "value": "LEE-01-1006-111"}],
    )
    with pytest.raises(ValueError) as exc_info:
        generate_plan(intent)
    msg = str(exc_info.value)
    assert "require a supplier" in msg
    assert "Lee Supplies" in msg          # a prompt the user can type
    assert "Intent contains filter types" not in msg


def test_purchase_order_status_filter_reaches_the_po_guard() -> None:
    """PurchaseOrder + status/supplier hits the PO guard, which names the
    supplier route — the actual answer to 'open POs for supplier X'."""
    intent = Intent(
        target_entity="PurchaseOrder",
        filters=[
            {"type": "status", "value": "OPEN"},
            {"type": "supplier", "value": "EIP Inc"},
        ],
    )
    with pytest.raises(ValueError) as exc_info:
        generate_plan(intent)
    msg = str(exc_info.value)
    assert "PO id or a date bound" in msg
    assert "EIP Inc" in msg


def test_standard_receipt_unscoped_is_refused() -> None:
    """"Get standardReceipts" reached the executor and failed inside the
    tool: "At least one of customer_name or customer_site is required."
    The KG advertises a (none) entity tool for StandardReceipt, but that
    tool refuses to run unscoped — so the planner promised something the
    tool would not honour, and the user saw a raw exception."""
    intent = Intent(target_entity="StandardReceipt")
    with pytest.raises(ValueError) as exc_info:
        generate_plan(intent)
    msg = str(exc_info.value)
    assert "require a customer or a site" in msg
    assert "ABC Application Software" in msg      # something typeable


def test_standard_receipt_with_customer_name_plans() -> None:
    """A scoped receipt query must still plan."""
    intent = Intent(
        target_entity="StandardReceipt",
        filters=[{"type": "customer_name", "value": "ABC Application Software"}],
    )
    plan = generate_plan(intent)
    assert plan
    assert plan[0].tool_name == "search_standard_receipts"


def test_standard_receipt_with_site_alone_plans() -> None:
    """Site alone is a valid scope — the tool accepts either."""
    intent = Intent(
        target_entity="StandardReceipt",
        filters=[{"type": "customer_site", "value": "Santa Clara"}],
    )
    assert generate_plan(intent)


def test_unguarded_entity_still_validates_with_an_example() -> None:
    """An entity with no guard falls through to validation — which must
    still name what IS supported and give something typeable."""
    intent = Intent(
        target_entity="CustomerAccount",
        filters=[{"type": "account_number", "value": "300000047368512"}],
    )
    with pytest.raises(NotImplementedError) as exc_info:
        generate_plan(intent)
    msg = str(exc_info.value)
    assert "account_number" in msg              # what was rejected
    assert "by_customer_name" in msg            # what works instead
    assert "For example:" in msg                # something typeable


def test_validation_message_carries_no_internal_jargon() -> None:
    """The old message opened with 'Intent contains filter types not
    supported for entity ...' and printed Python list reprs. Nothing a
    user can act on."""
    with pytest.raises(NotImplementedError) as exc_info:
        _validate_intent_filters(
            [{"type": "is_strategic_supplier", "value": True}], "Supplier"
        )
    msg = str(exc_info.value)
    assert "Intent contains filter types" not in msg
    assert msg.startswith("Spire can't filter Supplier by")


def test_validation_still_precedes_plan_building() -> None:
    """Moving validation after the guards must not let an unknown filter
    reach the plan blocks — Supplier has no guard, so validation is the
    only thing standing between this intent and a silent drop."""
    intent = Intent(
        target_entity="Supplier",
        filters=[{"type": "is_diversity_supplier", "value": True}],
    )
    with pytest.raises(NotImplementedError):
        generate_plan(intent)



# ─────────────────────────────────────────────────────────────────────
# F2 helpers — unit tests (no DB for the pure-Python ones)
# ─────────────────────────────────────────────────────────────────────


def test_compute_date_n_months_ago_simple(fixed_reference_date: date) -> None:
    """2026-05-26 minus 6 months = 2025-11-26."""
    result = _compute_date_n_months_ago(6, fixed_reference_date)
    assert result == date(2025, 11, 26)


def test_compute_date_n_months_ago_one_month(fixed_reference_date: date) -> None:
    """2026-05-26 minus 1 month = 2026-04-26."""
    result = _compute_date_n_months_ago(1, fixed_reference_date)
    assert result == date(2026, 4, 26)


def test_compute_date_n_months_ago_twelve_months(fixed_reference_date: date) -> None:
    """2026-05-26 minus 12 months = 2025-05-26."""
    result = _compute_date_n_months_ago(12, fixed_reference_date)
    assert result == date(2025, 5, 26)


def test_compute_date_n_months_ago_handles_day_overflow() -> None:
    """2026-03-31 minus 1 month = 2026-02-28 (day clamped to last of Feb)."""
    ref = date(2026, 3, 31)
    result = _compute_date_n_months_ago(1, ref)
    assert result == date(2026, 2, 28)


def test_compute_date_n_months_ago_crosses_year_boundary() -> None:
    """2026-02-15 minus 3 months = 2025-11-15."""
    ref = date(2026, 2, 15)
    result = _compute_date_n_months_ago(3, ref)
    assert result == date(2025, 11, 15)


def test_compute_date_n_months_ago_crosses_year_boundary_multiyear() -> None:
    """2026-05-26 minus 30 months = 2023-11-26."""
    ref = date(2026, 5, 26)
    result = _compute_date_n_months_ago(30, ref)
    assert result == date(2023, 11, 26)


def test_build_iteration_args_has_no_recent_invoices(
    fixed_reference_date: date,
) -> None:
    """F2: build_iteration_args composes primary key + computed date."""
    spec = {"type": "has_no_recent_invoices", "value": {"months": 6}}
    args = _build_iteration_args_with_computed(
        spec, "search_invoices", fixed_reference_date
    )
    assert args == {
        "supplier_number": "$iteration_value",
        "invoice_date_after": "2025-11-26",
    }


def test_build_iteration_args_missing_months_raises(
    fixed_reference_date: date,
) -> None:
    """F2: missing 'months' key in value raises ValueError."""
    spec = {"type": "has_no_recent_invoices", "value": {}}
    with pytest.raises(ValueError, match="months"):
        _build_iteration_args_with_computed(
            spec, "search_invoices", fixed_reference_date
        )


def test_build_iteration_args_negative_months_raises(
    fixed_reference_date: date,
) -> None:
    """F2: negative months value raises ValueError (nonsense input)."""
    spec = {"type": "has_no_recent_invoices", "value": {"months": -3}}
    with pytest.raises(ValueError, match="months"):
        _build_iteration_args_with_computed(
            spec, "search_invoices", fixed_reference_date
        )


def test_make_filtered_source_output_name_no_recent_invoices() -> None:
    """F2: source 'us_suppliers' + 'has_no_recent_invoices' ->
    'us_suppliers_no_recent_invoices'."""
    result = _make_filtered_source_output_name(
        "us_suppliers", "has_no_recent_invoices"
    )
    assert result == "us_suppliers_no_recent_invoices"


def test_make_filtered_source_output_name_unknown_filter_raises() -> None:
    """F2: unknown filter type raises KeyError so missing mappings are loud."""
    with pytest.raises(KeyError, match="filter-source name suffix"):
        _make_filtered_source_output_name("us_suppliers", "unknown_filter")


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


def test_generate_plan_anchor_no_filter_source_when_empty(
    anchor_intent: Intent,
) -> None:
    """F2: the anchor intent has no negation filter; no step should
    carry filter_source_when_empty=True."""
    produced = generate_plan(anchor_intent)
    for step in produced:
        assert step.filter_source_when_empty is False


# ─────────────────────────────────────────────────────────────────────
# Orchestrator — original Track A prompt with negation (F2 headline)
# ─────────────────────────────────────────────────────────────────────


def test_generate_plan_original_track_a_prompt_produces_four_steps(
    original_track_a_intent: Intent,
    fixed_reference_date: date,
) -> None:
    """F2 headline: original prompt with has_no_recent_invoices
    produces a 4-step plan, with Step 2 being the negation filter."""
    produced = generate_plan(
        original_track_a_intent, reference_date=fixed_reference_date
    )
    assert len(produced) == 4


def test_generate_plan_original_track_a_step1_is_country_fetch(
    original_track_a_intent: Intent,
    fixed_reference_date: date,
) -> None:
    """Step 1 fetches US suppliers (unchanged from anchor)."""
    produced = generate_plan(
        original_track_a_intent, reference_date=fixed_reference_date
    )
    step1 = produced[0]
    assert step1.tool_name == "search_suppliers"
    assert step1.tool_args == {"country": "US"}
    assert step1.output_name == "us_suppliers"


def test_generate_plan_original_track_a_step2_is_negation_filter(
    original_track_a_intent: Intent,
    fixed_reference_date: date,
) -> None:
    """F2 headline: Step 2 iterates us_suppliers.SupplierNumber, calls
    search_invoices with invoice_date_after = ref_date - 6 months,
    and carries filter_source_when_empty=True. Its output is
    us_suppliers_no_recent_invoices (parent items, filtered)."""
    produced = generate_plan(
        original_track_a_intent, reference_date=fixed_reference_date
    )
    step2 = produced[1]
    assert step2.tool_name == "search_invoices"
    assert step2.iterate_over == {
        "from_step": "us_suppliers", "field": "SupplierNumber"
    }
    assert step2.tool_args == {
        "supplier_number": "$iteration_value",
        "invoice_date_after": "2025-11-26",  # 2026-05-26 minus 6 months
    }
    assert step2.client_filters == []
    assert step2.output_name == "us_suppliers_no_recent_invoices"
    assert step2.filter_source_when_empty is True


def test_generate_plan_original_track_a_step3_iterates_filtered_suppliers(
    original_track_a_intent: Intent,
    fixed_reference_date: date,
) -> None:
    """Step 3 (has_open_PO) iterates from the FILTERED supplier list,
    not the original. This wiring is the key correctness check."""
    produced = generate_plan(
        original_track_a_intent, reference_date=fixed_reference_date
    )
    step3 = produced[2]
    assert step3.tool_name == "search_purchase_orders"
    assert step3.iterate_over == {
        "from_step": "us_suppliers_no_recent_invoices",
        "field": "SupplierId",
    }
    assert step3.client_filters == [
        {"field": "StatusCode", "op": "equals", "value": "OPEN"}
    ]
    assert step3.filter_source_when_empty is False


def test_generate_plan_original_track_a_step4_is_buyer_lookup(
    original_track_a_intent: Intent,
    fixed_reference_date: date,
) -> None:
    """Step 4 (include Buyer) iterates from open_pos with BuyerId dedup."""
    produced = generate_plan(
        original_track_a_intent, reference_date=fixed_reference_date
    )
    step4 = produced[3]
    assert step4.tool_name == "get_buyer"
    assert step4.iterate_over == {
        "from_step": "open_pos", "field": "BuyerId"
    }
    assert step4.output_dedupe_by == "BuyerId"


def test_generate_plan_original_track_a_step_ids_sequential(
    original_track_a_intent: Intent,
    fixed_reference_date: date,
) -> None:
    """Step IDs are 1, 2, 3, 4."""
    produced = generate_plan(
        original_track_a_intent, reference_date=fixed_reference_date
    )
    assert [s.step_id for s in produced] == [1, 2, 3, 4]


# ─────────────────────────────────────────────────────────────────────
# AR-P2c: open_only on the customer-invoices traversal (prompt 1)
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def open_invoices_intent() -> Intent:
    """
    The structured intent for prompt 1: 'open invoices for customer
    ABC Corporation Americas'. CustomerAccount-rooted, resolved by name,
    with the customer's transactions included and open_only set (AR-P2c).
    """
    return Intent(
        target_entity="CustomerAccount",
        filters=[
            {"type": "by_customer_name", "value": "ABC Corporation Americas"},
        ],
        include=["CustomerTransaction"],
        open_only=True,
    )


def test_generate_plan_open_only_sets_tool_arg_on_transaction_step(
    open_invoices_intent: Intent,
) -> None:
    """AR-P2c: open_only=True puts open_only in the CustomerTransaction
    include step's tool_args, so the fetcher restricts to open invoices."""
    produced = generate_plan(open_invoices_intent)
    ct_steps = [
        s for s in produced if s.tool_name == "get_customer_transactions"
    ]
    assert len(ct_steps) == 1
    assert ct_steps[0].tool_args.get("open_only") is True


def test_generate_plan_open_only_false_omits_tool_arg() -> None:
    """Without open_only, the CustomerTransaction step carries no open_only
    arg — prompt 15's plain listing is unchanged."""
    plain = Intent(
        target_entity="CustomerAccount",
        filters=[
            {"type": "by_customer_name", "value": "ABC Corporation Americas"},
        ],
        include=["CustomerTransaction"],
        open_only=False,
    )
    produced = generate_plan(plain)
    ct_steps = [
        s for s in produced if s.tool_name == "get_customer_transactions"
    ]
    assert len(ct_steps) == 1
    assert "open_only" not in ct_steps[0].tool_args


# ─────────────────────────────────────────────────────────────────────
# Top-N open invoices: invoice_limit on the open-invoices traversal
# (prompt 1 complete — caps the open set to the N highest-balance rows)
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def top_open_invoices_intent() -> Intent:
    """
    The structured intent for prompt 1's capped form: 'top 5 open invoices
    for customer ABC Corporation Americas'. Same open-invoices shape as
    open_invoices_intent, plus invoice_limit=5. The fetcher returns the
    open set balance-desc, so the limit keeps the top 5.
    """
    return Intent(
        target_entity="CustomerAccount",
        filters=[
            {"type": "by_customer_name", "value": "ABC Corporation Americas"},
        ],
        include=["CustomerTransaction"],
        open_only=True,
        invoice_limit=5,
    )


def test_generate_plan_invoice_limit_sets_limit_on_transaction_step(
    top_open_invoices_intent: Intent,
) -> None:
    """invoice_limit=5 (with open_only) puts limit=5 in the
    CustomerTransaction include step's tool_args, alongside open_only."""
    produced = generate_plan(top_open_invoices_intent)
    ct_steps = [
        s for s in produced if s.tool_name == "get_customer_transactions"
    ]
    assert len(ct_steps) == 1
    assert ct_steps[0].tool_args.get("open_only") is True
    assert ct_steps[0].tool_args.get("limit") == 5


def test_generate_plan_invoice_limit_none_omits_limit(
    open_invoices_intent: Intent,
) -> None:
    """With invoice_limit unset (default None), the open-invoices step
    carries no limit arg — the uncapped open listing is unchanged."""
    produced = generate_plan(open_invoices_intent)
    ct_steps = [
        s for s in produced if s.tool_name == "get_customer_transactions"
    ]
    assert len(ct_steps) == 1
    assert "limit" not in ct_steps[0].tool_args


# ─────────────────────────────────────────────────────────────────────
# AR-P5 prompt 6: balance_only suppresses the include traversal
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def balance_only_intent() -> Intent:
    """
    The structured intent for prompt 6: 'show me the account balance for
    customer ABC Application Software'. Same root as the customer-invoices
    shape, but balance_only is set and no child is traversed — the balance
    figures ride on the account record Block 1 already fetches.
    """
    return Intent(
        target_entity="CustomerAccount",
        filters=[
            {"type": "by_customer_name", "value": "ABC Application Software"},
        ],
        include=[],
        balance_only=True,
    )


def test_generate_plan_balance_only_produces_single_step(
    balance_only_intent: Intent,
) -> None:
    """balance_only yields exactly the account fetch and nothing else."""
    produced = generate_plan(balance_only_intent)
    assert len(produced) == 1
    assert produced[0].tool_name == "get_customer_account_by_name"
    # Assert the customer reaches the tool, not the exact arg dict — the
    # arg name is KG metadata and may legitimately gain fields.
    assert (
        produced[0].tool_args.get("customer_name")
        == "ABC Application Software"
    )


def test_generate_plan_balance_only_ignores_a_populated_include() -> None:
    """The FLAG decides the shape, not the include list.

    This is the guard's whole point. The parser normally emits an empty
    include for a balance question, but it is an LLM and need not — an
    earlier build of this rule had it dropping the by_customer_name filter
    instead. So balance_only must suppress the traversal even when
    CustomerTransaction IS present, rather than trusting the list to be
    empty.
    """
    intent = Intent(
        target_entity="CustomerAccount",
        filters=[
            {"type": "by_customer_name", "value": "ABC Application Software"},
        ],
        include=["CustomerTransaction"],
        balance_only=True,
    )
    produced = generate_plan(intent)
    assert len(produced) == 1
    assert not [
        s for s in produced if s.tool_name == "get_customer_transactions"
    ]


def test_generate_plan_balance_only_false_keeps_the_traversal() -> None:
    """Without the flag, the same include still traverses.

    Pins that the guard is gated on balance_only alone — AR-P2b/P2c and
    prompt 15 must be byte-for-byte unaffected.
    """
    intent = Intent(
        target_entity="CustomerAccount",
        filters=[
            {"type": "by_customer_name", "value": "ABC Corporation Americas"},
        ],
        include=["CustomerTransaction"],
        balance_only=False,
    )
    produced = generate_plan(intent)
    ct_steps = [
        s for s in produced if s.tool_name == "get_customer_transactions"
    ]
    assert len(ct_steps) == 1


def test_generate_plan_balance_only_suppresses_open_only_and_limit() -> None:
    """No transaction step means the AR-P2c/top-N args have nowhere to go.

    open_only and invoice_limit are injected onto the CustomerTransaction
    step inside the include loop. With the loop skipped, they must not
    leak onto the account step or raise.
    """
    intent = Intent(
        target_entity="CustomerAccount",
        filters=[
            {"type": "by_customer_name", "value": "ABC Application Software"},
        ],
        include=["CustomerTransaction"],
        balance_only=True,
        open_only=True,
        invoice_limit=5,
    )
    produced = generate_plan(intent)
    assert len(produced) == 1
    assert "open_only" not in produced[0].tool_args
    assert "limit" not in produced[0].tool_args


# ─────────────────────────────────────────────────────────────────────
# AR-P5 prompts 7 and 8: the account-child traversals
#
# Both are plain single-parent expansions off CustomerAccount, and both
# depend on TWO planner dicts that are pure data — easy to delete, and
# a deletion currently fails only at plan time or in a live run. A
# missing _TOOL_PRIMARY_ARG entry is exactly what broke AR-P3, so these
# pin both maps rather than trusting end-to-end runs to catch it.
#
# The bucket-name assertions matter most: AccountCreditMemo and
# AccountReceipt must land in SEPARATE buckets. If they ever shared one,
# nothing would raise — one would silently overwrite the other.
# ─────────────────────────────────────────────────────────────────────


def _account_child_intent(include_entity: str) -> Intent:
    """A customer-scoped intent traversing to one account child."""
    return Intent(
        target_entity="CustomerAccount",
        filters=[
            {"type": "by_customer_name", "value": "ABC Application Software"},
        ],
        include=[include_entity],
    )


def test_generate_plan_account_credit_memos_traversal() -> None:
    """Prompt 7: resolve the account, then walk to its credit memos."""
    produced = generate_plan(_account_child_intent("AccountCreditMemo"))
    assert len(produced) == 2
    assert produced[0].tool_name == "get_customer_account_by_name"
    assert produced[1].tool_name == "get_account_credit_memos"
    # _TOOL_PRIMARY_ARG must name account_id, and the value comes from
    # iterating the parent step's AccountId.
    assert "account_id" in produced[1].tool_args
    assert produced[1].output_name == "account_credit_memos"


def test_generate_plan_account_receipts_traversal() -> None:
    """Prompt 8: the same shape, to a different child."""
    produced = generate_plan(_account_child_intent("AccountReceipt"))
    assert len(produced) == 2
    assert produced[0].tool_name == "get_customer_account_by_name"
    assert produced[1].tool_name == "get_account_receipts"
    assert "account_id" in produced[1].tool_args
    assert produced[1].output_name == "account_receipts"


def test_account_children_use_distinct_output_buckets() -> None:
    """Memos and receipts must NOT share a bucket name.

    A collision here would be silent: the executor writes both under one
    key and the second overwrites the first, so the synthesizer would
    narrate receipts as memos (or lose one entirely) with no error. Also
    guards against either bucket colliding with AR-P4's top-level
    'credit_memos'.
    """
    memo_plan = generate_plan(_account_child_intent("AccountCreditMemo"))
    receipt_plan = generate_plan(_account_child_intent("AccountReceipt"))
    memo_bucket = memo_plan[1].output_name
    receipt_bucket = receipt_plan[1].output_name
    assert memo_bucket != receipt_bucket
    assert memo_bucket == "account_credit_memos"
    assert receipt_bucket == "account_receipts"
    # AR-P4's rooted CreditMemo owns the bare name; neither child may take it.
    assert memo_bucket != "credit_memos"
    assert receipt_bucket != "credit_memos"


def test_generate_plan_account_child_iterates_on_account_id() -> None:
    """The child step iterates the parent's AccountId, not a literal.

    The account children do NOT echo AccountId in their row bodies — the
    join key is the URL path — so the planner must feed it from the
    resolve step's output.
    """
    produced = generate_plan(_account_child_intent("AccountReceipt"))
    child = produced[1]
    assert child.iterate_over is not None
    assert "AccountId" in str(child.iterate_over)
