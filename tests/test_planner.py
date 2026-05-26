"""
Tests for the planner.

Two kinds of tests live here:

1. Contract tests for the dataclasses (Intent, Step, Plan) — no DB
   required. These verify the design doc and the stub file stay in sync.

2. Live KG tests for implemented lookup functions — hit the live KG
   (oracle26ai_db_bhagavan container). If these fail, run
   ./scripts/rebuild_kg.sh first to ensure seed data is loaded.
"""

import pytest

from spire.planner.planner import Intent, Plan, Step, resolve_vocab


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
