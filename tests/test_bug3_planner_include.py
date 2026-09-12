"""
Regression tests for BUG-3 — planner raises RefusalError, not KeyError,
for an unsatisfiable include.

BACKGROUND

An Intent whose include list names an entity with no declared edge from
the target (or from the previous include in a chain, or from the root)
reached the planner's Block 3, which raised a raw KeyError:

    KeyError("No edge to include 'Supplier': it is neither a child of
              'PurchaseOrder' (chain) nor of 'PurchaseOrder' (sibling
              under the root).")

plan_node wraps any exception from generate_plan as
{"error": f"plan: {exc}"}, but WITHOUT setting plan_refusal=True, so
run_graph.py treated it as a HARD FAILURE — printing "ERROR: plan: ..."
to stderr and exiting 2 — instead of the refusal path (which prints the
readable Reason/Solution/Example message to stdout and exits 4).

The fix routes the same condition as a RefusalError wrapping a Refusal
with flavor UNSUPPORTED_OPERATION. plan_node already catches RefusalError
and drops exc.refusal into state["refusal"] — the same channel a parser
decline uses — so the crash becomes an answer.

REACHABILITY

For parser-generated intents, this path is now unreachable: the
validate_intent include gate (BUG-2) refuses the shape at parse time,
before generate_plan runs. This fix is the LAYERED BACKSTOP for the two
cases the gate cannot reach:

  1. Hand-built Intents. The planner is a public API — run_plan.py and
     several tests construct Intents directly, bypassing the parser.
  2. KG drift. A future KG change that removes an edge a working parser
     include still assumes.

These tests exercise the planner DIRECTLY (not through the pipeline),
because that is where the backstop lives. They hit the live KG via
find_edge, so they are skipped when personas.yaml is absent, matching
the pattern used by test_bug2_include_gate.py.
"""

from __future__ import annotations

import pytest

from spire.config import PERSONAS_FILE
from spire.nl_parser.result import RefusalError
from spire.planner.planner import Intent, generate_plan


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping KG-backed integration tests",
)


# ── The S1 shape: RefusalError, not KeyError ───────────────────────────


def test_s1_shape_raises_refusal_error_not_keyerror() -> None:
    """The exact S1 shape must raise RefusalError, not KeyError.

    Before the fix this raised a raw KeyError, which plan_node passed to
    run_graph as a hard failure. After the fix, it raises a structured
    RefusalError that plan_node routes to state["refusal"].
    """
    intent = Intent(
        target_entity="PurchaseOrder",
        filters=[{"type": "by_id", "value": "701337"}],
        include=["Supplier"],
    )
    with pytest.raises(RefusalError) as excinfo:
        generate_plan(intent)

    # Sanity: it is NOT a KeyError (RefusalError inherits from Exception
    # directly, not from KeyError, so this assertion documents intent).
    assert not isinstance(excinfo.value, KeyError)

    refusal = excinfo.value.refusal
    assert refusal.flavor.name == "UNSUPPORTED_OPERATION"
    assert refusal.offending_entity == "Supplier"


def test_bad_include_after_valid_include_raises_refusal_error() -> None:
    """The bad element is caught regardless of position in the list.

    A valid first include chains the previous_entity forward; the second
    (bad) include then fails on both the chain hop and the sibling hop.
    The refusal must name the bad element, not the valid one.
    """
    intent = Intent(
        target_entity="PurchaseOrder",
        filters=[{"type": "by_id", "value": "701337"}],
        include=["POSchedule", "Supplier"],
    )
    with pytest.raises(RefusalError) as excinfo:
        generate_plan(intent)

    assert excinfo.value.refusal.offending_entity == "Supplier"
    assert excinfo.value.refusal.flavor.name == "UNSUPPORTED_OPERATION"


# ── Controls: valid includes still plan ────────────────────────────────


def test_valid_buyer_include_still_plans() -> None:
    """ASSIGNED_TO (PurchaseOrder -> Buyer) exists; must still plan."""
    intent = Intent(
        target_entity="PurchaseOrder",
        filters=[{"type": "by_id", "value": "701337"}],
        include=["Buyer"],
    )
    plan = generate_plan(intent)
    assert len(plan) == 2
    assert plan[0].tool_name == "get_purchase_order_by_id"
    assert plan[1].tool_name == "get_buyer"


def test_valid_chain_still_plans() -> None:
    """The two-hop chain the parser prompt emits for 'show PO and its
    distributions' must still plan — no false refusal from the fix."""
    intent = Intent(
        target_entity="PurchaseOrder",
        filters=[{"type": "by_id", "value": "701337"}],
        include=["POSchedule", "PODistribution"],
    )
    plan = generate_plan(intent)
    tool_names = [s.tool_name for s in plan]
    assert "get_purchase_order_by_id" in tool_names
    assert "get_purchase_order_schedules" in tool_names
    assert "get_purchase_order_distributions" in tool_names


# ── plan_node routing (the layer the fix actually changes) ─────────────


def test_plan_node_routes_unsatisfiable_include_to_refusal_key() -> None:
    """plan_node must return {'refusal': Refusal}, NOT {'error': ...}.

    This is the specific behaviour the fix changes. Before: plan_node
    returned {'error': 'plan: ...'} with plan_refusal MISSING, which
    run_graph treats as a hard failure. After: plan_node returns
    {'refusal': Refusal}, which run_graph renders as an answer.
    """
    from spire.graph.pipeline import plan_node

    state = {
        "intent": Intent(
            target_entity="PurchaseOrder",
            filters=[{"type": "by_id", "value": "701337"}],
            include=["Supplier"],
        )
    }
    result = plan_node(state)

    assert "refusal" in result, (
        "plan_node should route an unsatisfiable include to "
        "state['refusal'], not state['error']"
    )
    assert "error" not in result, (
        "plan_node must not put anything in state['error'] for an "
        "unsatisfiable include"
    )
    assert result["refusal"].flavor.name == "UNSUPPORTED_OPERATION"
    assert result["refusal"].offending_entity == "Supplier"


def test_plan_node_still_routes_existing_refusals_cleanly() -> None:
    """Regression: an existing MISSING_IDENTIFIER guard (Invoice with no
    supplier) must still route through state['refusal'] unchanged. This
    pins the shape of the RefusalError path the fix relies on — if
    plan_node ever stopped catching RefusalError, this test would fail
    before any of the new ones."""
    from spire.graph.pipeline import plan_node

    state = {
        "intent": Intent(target_entity="Invoice", filters=[], include=[]),
    }
    result = plan_node(state)

    assert "refusal" in result
    assert "error" not in result
    assert result["refusal"].flavor.name == "MISSING_IDENTIFIER"
    assert result["refusal"].offending_entity == "Invoice"