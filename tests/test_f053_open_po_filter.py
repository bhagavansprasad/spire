"""F-053 regression — `has_open_PO` keeps only suppliers that have at
least one open purchase order.

F-053: "suppliers with open purchase orders" listed nine suppliers with
`Open POs = 0`. The plan's Step 2 fetched each supplier's POs but never
set `filter_source_when_nonempty` on the step, so the answer rendered the
full source supplier list joined to their (possibly empty) child lists.
Same shape F-010 fixed for `has_invoice_over_amount`; `has_open_PO` was
the sibling filter that fix did not cover.

Two files carry the fix:

  registries._FILTER_SOURCE_NONEMPTY_SUFFIX gains has_open_PO, so Block 2
  of generate_plan emits the parent-filtering shape.

  plan_builders._build_iteration_args_with_computed gains a has_open_PO
  branch that sends `status='OPEN'` to search_purchase_orders — the
  server filters, so "empty child result" means genuinely no open POs.

Tests below split by what they touch. The registry and helper tests need
nothing. The plan-shape test needs the live KG (load_kg_menu); it is
gated on personas.yaml, matching the sibling KG-backed tests. The
executor tests build the plan by hand and run against a mocked MCP
session — no pod.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock
import json

import pytest

from spire.config import PERSONAS_FILE
from spire.executor.executor import execute_plan
from spire.planner.models import Intent, Step
from spire.planner.plan_builders import (
    _build_iteration_args_with_computed,
    _make_filtered_source_output_name,
)
from spire.planner.registries import _FILTER_SOURCE_NONEMPTY_SUFFIX


# ---- Registry membership — the one-line fix -----------------------


def test_has_open_po_is_in_nonempty_suffix_registry():
    """The F-053 defect: `has_open_PO` was in neither registry, so Block 2
    fell to the else shape and the parent bucket was never filtered."""
    assert "has_open_PO" in _FILTER_SOURCE_NONEMPTY_SUFFIX, (
        "F-053: has_open_PO missing from _FILTER_SOURCE_NONEMPTY_SUFFIX. "
        "The planner will emit the child-list shape instead of the "
        "parent-filtered shape."
    )


def test_sibling_filters_still_present():
    """Guards the fix against accidentally dropping a neighbour."""
    for name in (
        "has_invoice_over_amount",
        "has_site_in_bu",
        "has_classification",
    ):
        assert name in _FILTER_SOURCE_NONEMPTY_SUFFIX, name


# ---- Output-name composition --------------------------------------


def test_filtered_output_name_for_has_open_po():
    """With has_open_PO in the registry, _make_filtered_source_output_name
    produces `<source>_has_open_PO`, matching the sibling shape."""
    assert (
        _make_filtered_source_output_name("suppliers", "has_open_PO")
        == "suppliers_has_open_PO"
    )


# ---- Computed-args helper -----------------------------------------


def test_has_open_po_sends_status_open_to_tool():
    """The status filter rides as a server-side tool_arg. search_purchase_
    orders accepts `status`; the tool sends StatusCode='OPEN' to the pod,
    so an empty result means genuinely no open POs."""
    args = _build_iteration_args_with_computed(
        {"type": "has_open_PO", "value": True},
        "search_purchase_orders",
        date(2026, 9, 28),
    )
    assert args == {"supplier_id": "$iteration_value", "status": "OPEN"}


def test_has_open_po_branch_precedes_the_raise():
    """If the branch is removed, the helper raises NotImplementedError
    and the fix regresses silently at plan time. Pin the branch."""
    try:
        _build_iteration_args_with_computed(
            {"type": "has_open_PO", "value": True},
            "search_purchase_orders",
            date(2026, 9, 28),
        )
    except NotImplementedError as exc:
        pytest.fail(
            f"has_open_PO branch missing in "
            f"_build_iteration_args_with_computed: {exc}"
        )


# ---- Plan shape — needs the live KG -------------------------------


@pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping KG-backed plan-shape test",
)
def test_plan_for_has_open_po_sets_filter_source_when_nonempty():
    """The end-to-end plan shape. The failure this reproduces is the
    2026-09-25 smoke-log Step 2:

        output_name:    open_pos
        (no filter_source_when_nonempty)

    Post-fix Step 2 must carry filter_source_when_nonempty=True and
    output_name='suppliers_has_open_PO'.
    """
    from spire.planner.planner import generate_plan

    intent = Intent(
        target_entity="Supplier",
        filters=[{"type": "has_open_PO", "value": True}],
    )
    plan = generate_plan(intent)
    assert len(plan) == 2
    step1, step2 = plan
    assert step1.tool_name == "search_suppliers"
    assert step1.output_name == "suppliers"
    assert step2.tool_name == "search_purchase_orders"
    assert step2.filter_source_when_nonempty is True, (
        "F-053: the PO step did not set filter_source_when_nonempty; "
        "suppliers with zero open POs will appear in the answer."
    )
    assert step2.filter_source_when_empty is False
    assert step2.output_name == "suppliers_has_open_PO"
    assert step2.tool_args.get("status") == "OPEN"
    assert step2.tool_args.get("supplier_id") == "$iteration_value"
    assert step2.iterate_over == {
        "from_step": "suppliers", "field": "SupplierId",
    }


# ---- Executor drop-empty-parents — no KG --------------------------


def _mock_session(payloads):
    """Session that returns a different payload per call."""
    def block(p):
        return type("B", (), {"type": "text", "text": json.dumps(p)})()
    session = AsyncMock()
    session.call_tool.side_effect = [
        type("R", (), {"content": [block(p)]})() for p in payloads
    ]
    return session


def _two_step_plan():
    return [
        Step(
            step_id=1,
            tool_name="search_suppliers",
            tool_args={},
            iterate_over=None,
            client_filters=[],
            output_name="suppliers",
            output_dedupe_by=None,
        ),
        Step(
            step_id=2,
            tool_name="search_purchase_orders",
            tool_args={"supplier_id": "$iteration_value", "status": "OPEN"},
            iterate_over={
                "from_step": "suppliers", "field": "SupplierId",
            },
            client_filters=[],
            output_name="suppliers_has_open_PO",
            output_dedupe_by=None,
            filter_source_when_nonempty=True,
        ),
    ]


@pytest.mark.asyncio
async def test_executor_drops_suppliers_with_no_open_pos():
    """Three source suppliers; only two have open POs. The output bucket
    must contain the two, and the empty one must be absent."""
    session = _mock_session([
        [
            {"SupplierId": 100, "Supplier": "Has Two Open POs"},
            {"SupplierId": 200, "Supplier": "No Open POs"},
            {"SupplierId": 300, "Supplier": "Has One Open PO"},
        ],
        [{"POHeaderId": 1, "StatusCode": "OPEN"},
         {"POHeaderId": 2, "StatusCode": "OPEN"}],
        [],
        [{"POHeaderId": 3, "StatusCode": "OPEN"}],
    ])
    outputs, _, _ = await execute_plan(_two_step_plan(), session)
    kept = outputs["suppliers_has_open_PO"]
    kept_ids = {row["SupplierId"] for row in kept}
    assert kept_ids == {100, 300}, (
        f"F-053: expected suppliers 100 and 300 in the filtered bucket; "
        f"got {sorted(kept_ids)}. Supplier 200 (no open POs) should be "
        f"absent."
    )


@pytest.mark.asyncio
async def test_executor_keeps_all_when_every_supplier_has_open_pos():
    """Guards the nonempty branch against over-filtering: when every
    source item has a matching child, the filtered bucket equals the
    source bucket."""
    session = _mock_session([
        [{"SupplierId": 100}, {"SupplierId": 200}],
        [{"POHeaderId": 1}],
        [{"POHeaderId": 2}],
    ])
    outputs, _, _ = await execute_plan(_two_step_plan(), session)
    assert len(outputs["suppliers_has_open_PO"]) == 2


@pytest.mark.asyncio
async def test_executor_empties_bucket_when_no_supplier_has_open_pos():
    """Every source item's child call is empty -> the filtered bucket is
    empty. Correct answer for a prompt where nobody has an open PO."""
    session = _mock_session([
        [{"SupplierId": 100}, {"SupplierId": 200}],
        [],
        [],
    ])
    outputs, _, _ = await execute_plan(_two_step_plan(), session)
    assert outputs["suppliers_has_open_PO"] == []
