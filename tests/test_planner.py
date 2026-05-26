"""
Tests for the planner stubs (Phase 2 step 0 verification).

This test does NOT exercise any planner logic — the stubs all raise
NotImplementedError. It verifies the *contract*: that the dataclasses
defined in planner.py can express the worked-example plan from
docs/designs/phase_2_planner_design.md exactly as written.

If this test passes, we know:
  - The module imports cleanly (no syntax errors in the stub file)
  - The Intent, Step, and Plan types are as designed
  - The anchor-question plan from the design doc is representable
  - Field names and types haven't drifted between doc and code

If this test fails, the stub file and the design doc are out of sync.
"""

import pytest

from spire.planner.planner import Intent, Plan, Step


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
# Tests
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
