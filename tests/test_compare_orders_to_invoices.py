"""
Tests for the invoiced-vs-ordered comparison feature (P6c).

Three layers (mirrors test_aggregate_invoices_tool.py and
test_aggregation_routing.py):

1. Unit tests for the pure join logic (_compare_by_po, _sum_invoice_amounts)
   and the tool's fetch/compose behaviour with a mocked FusionClient. No
   infrastructure required — these are where a join or arithmetic bug would
   be invisible downstream, so they carry the weight.

2. Unit tests for the deterministic synthesizer builders and the planner's
   comparison routing (compare Intent -> single-step Plan; DraftCompare ->
   Intent). No DB, no pod.

3. Integration tests against the live Fusion pod. Marked
   @pytest.mark.integration so they're skipped by default. Run with:
       pytest -m integration tests/test_compare_orders_to_invoices.py
   Requires personas.yaml present and the pod reachable.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.compare_orders_to_invoices import (
    _compare_by_po,
    _sum_invoice_amounts,
    compare_purchase_order_to_invoices,
    compare_supplier_orders_to_invoices,
    compare_top_suppliers_orders_to_invoices,
)
from spire.synthesizer.synthesizer import (
    ComparisonResponse,
    _build_comparison_response,
    _comparison_shape,
    _direction_phrase,
)
from spire.nl_parser.draft import DraftCompare, DraftIntent
from spire.planner.planner import Intent, generate_plan


# Test-data anchors from the pod (verified live):
#   PO 162034 (Lee Supplies) — ordered 758.00, invoiced 830.01 (one invoice).
KNOWN_PO_NUMBER = "162034"


def _po(order_number, ordered, header_id=1, status="CLOSED"):
    return {
        "POHeaderId": header_id,
        "OrderNumber": order_number,
        "Supplier": "Test Supplier",
        "SupplierId": 111,
        "Ordered": ordered,
        "StatusCode": status,
    }


def _inv(po_number, amount, number="INV"):
    return {
        "InvoiceId": 1,
        "InvoiceNumber": number,
        "Supplier": "Test Supplier",
        "SupplierNumber": "111",
        "PurchaseOrderNumber": po_number,
        "InvoiceAmount": amount,
    }


# ─────────────────────────────────────────────────────────────────────
# Unit: _sum_invoice_amounts
# ─────────────────────────────────────────────────────────────────────


def test_sum_invoice_amounts_basic():
    invoices = [_inv("A", 100.0), _inv("A", 50.5), _inv("B", 10.0)]
    assert _sum_invoice_amounts(invoices) == 160.5


def test_sum_invoice_amounts_skips_non_numeric():
    invoices = [_inv("A", 100.0), _inv("A", None), _inv("A", "oops")]
    assert _sum_invoice_amounts(invoices) == 100.0


def test_sum_invoice_amounts_empty_is_zero():
    assert _sum_invoice_amounts([]) == 0.0


# ─────────────────────────────────────────────────────────────────────
# Unit: _compare_by_po — the join
# ─────────────────────────────────────────────────────────────────────


def test_compare_matches_invoice_to_po_on_number():
    pos = [_po("100", 758.0)]
    invoices = [_inv("100", 830.01)]
    rows, total_ordered, total_invoiced = _compare_by_po(pos, invoices)
    assert total_ordered == 758.0
    assert total_invoiced == 830.01
    assert rows[0]["difference"] == 72.01
    assert rows[0]["invoice_count"] == 1


def test_compare_po_with_no_invoices_is_zero_not_dropped():
    """A PO with no matching invoices is a real answer (ordered but never
    billed), not an absence to filter out."""
    pos = [_po("100", 500.0)]
    rows, total_ordered, total_invoiced = _compare_by_po(pos, [])
    assert len(rows) == 1
    assert rows[0]["invoiced"] == 0.0
    assert rows[0]["invoice_count"] == 0
    assert total_invoiced == 0.0


def test_compare_ignores_invoices_with_no_po_number():
    """Invoices whose PurchaseOrderNumber is None (debit memos,
    prepayments) are not folded into any PO's total."""
    pos = [_po("100", 500.0)]
    invoices = [_inv("100", 200.0), _inv(None, 999.0)]
    rows, _, total_invoiced = _compare_by_po(pos, invoices)
    assert total_invoiced == 200.0
    assert rows[0]["invoiced"] == 200.0


def test_compare_unmatched_invoice_not_added_to_a_po():
    """An invoice referencing a PO we didn't fetch stays out of the totals
    rather than landing in some other PO's bucket."""
    pos = [_po("100", 500.0)]
    invoices = [_inv("100", 200.0), _inv("999", 300.0)]
    rows, _, total_invoiced = _compare_by_po(pos, invoices)
    assert total_invoiced == 200.0
    assert len(rows) == 1


def test_compare_string_numeric_key_coercion():
    """OrderNumber and PurchaseOrderNumber must match even when one side is
    an int and the other a string (the join coerces to str)."""
    pos = [_po(100, 500.0)]        # numeric OrderNumber
    invoices = [_inv("100", 200.0)]  # string PurchaseOrderNumber
    _, _, total_invoiced = _compare_by_po(pos, invoices)
    assert total_invoiced == 200.0


def test_compare_rows_sorted_by_abs_difference_desc():
    pos = [_po("A", 100.0), _po("B", 100.0), _po("C", 100.0)]
    invoices = [_inv("A", 105.0), _inv("B", 300.0), _inv("C", 101.0)]
    rows, _, _ = _compare_by_po(pos, invoices)
    # B has the biggest gap (+200), then A (+5), then C (+1)
    assert [r["order_number"] for r in rows] == ["B", "A", "C"]


# ─────────────────────────────────────────────────────────────────────
# Unit: mocked-client tool behaviour
# ─────────────────────────────────────────────────────────────────────


def _mock_po_client(po_item, invoices):
    """A FusionClient whose .get serves one PO on the purchaseOrders path
    and the given invoices on the invoices path."""
    client = AsyncMock()

    async def _get(path, params=None):
        params = params or {}
        if "purchaseOrders" in path:
            return {"items": [po_item] if po_item else []}
        # invoices path, paged
        offset = params.get("offset", 0)
        limit = params.get("limit", len(invoices))
        page = invoices[offset : offset + limit]
        has_more = offset + limit < len(invoices)
        return {"items": page, "hasMore": has_more}

    client.get.side_effect = _get
    return client


@pytest.mark.asyncio
async def test_po_tool_found_computes_difference():
    po_item = _po("100", 758.0)
    client = _mock_po_client(po_item, [_inv("100", 830.01)])
    result = await compare_purchase_order_to_invoices(client, "100")
    assert result["shape"] == "po_invoiced_vs_ordered"
    assert result["found"] is True
    assert result["ordered"] == 758.0
    assert result["invoiced"] == 830.01
    assert result["difference"] == 72.01


@pytest.mark.asyncio
async def test_po_tool_not_found():
    client = _mock_po_client(None, [])
    result = await compare_purchase_order_to_invoices(client, "999")
    assert result["shape"] == "po_invoiced_vs_ordered"
    assert result["found"] is False


@pytest.mark.asyncio
async def test_supplier_tool_ambiguous_refuses():
    """Several name matches -> ambiguous, no comparison run."""
    client = AsyncMock()

    async def _get(path, params=None):
        return {"items": [
            {"SupplierId": 1, "SupplierNumber": "1", "Supplier": "Lee Supplies"},
            {"SupplierId": 2, "SupplierNumber": "2", "Supplier": "Lee Supplies56"},
        ]}

    client.get.side_effect = _get
    result = await compare_supplier_orders_to_invoices(client, "Lee Supplies")
    assert result["ambiguous"] is True
    assert "Lee Supplies" in result["candidates"]


@pytest.mark.asyncio
async def test_supplier_tool_not_found():
    client = AsyncMock()
    client.get.side_effect = AsyncMock(return_value={"items": []})
    result = await compare_supplier_orders_to_invoices(client, "Nobody")
    assert result["found"] is False


# ─────────────────────────────────────────────────────────────────────
# Unit: deterministic synthesizer builders
# ─────────────────────────────────────────────────────────────────────


def test_direction_phrase_over_under_equal():
    assert "over-invoiced by 72.01" in _direction_phrase(72.01)
    assert "under-invoiced by 72.01" in _direction_phrase(-72.01)
    assert "fully invoiced" in _direction_phrase(0.0)


def test_comparison_shape_reads_bucket():
    outputs = {"comparison": [{"shape": "po_invoiced_vs_ordered"}]}
    assert _comparison_shape(outputs) == "po_invoiced_vs_ordered"


def test_comparison_shape_none_when_absent():
    assert _comparison_shape({"po": [{"POHeaderId": 1}]}) is None


def test_build_po_comparison_response():
    outputs = {"comparison": [{
        "shape": "po_invoiced_vs_ordered", "found": True,
        "order_number": "162034", "supplier": "Lee Supplies",
        "ordered": 758.0, "invoiced": 830.01, "difference": 72.01,
        "invoice_count": 1, "truncated": False,
    }]}
    resp = _build_comparison_response(outputs, "po_invoiced_vs_ordered")
    assert isinstance(resp, ComparisonResponse)
    assert "over-invoiced by 72.01" in resp.summary
    assert "162034" in resp.summary


def test_build_supplier_comparison_reports_unmatched():
    outputs = {"comparison": [{
        "shape": "supplier_invoiced_vs_ordered", "found": True,
        "ambiguous": False, "supplier": "Advanced Corp", "po_count": 301,
        "total_ordered": 100.0, "total_invoiced": 30.0,
        "total_difference": -70.0, "unmatched_invoice_count": 2865,
        "truncated": False,
    }]}
    resp = _build_comparison_response(outputs, "supplier_invoiced_vs_ordered")
    assert "under-invoiced by 70.00" in resp.summary
    assert "2,865" in resp.summary  # unmatched invoices surfaced


def test_build_top_suppliers_comparison_lists_each():
    outputs = {"comparison": [{
        "shape": "top_suppliers_invoiced_vs_ordered", "returned": 2,
        "truncated": True,
        "suppliers": [
            {"supplier": "A", "total_ordered": 100.0, "total_invoiced": 0.0,
             "total_difference": -100.0, "unmatched_invoice_count": 5},
            {"supplier": "B", "total_ordered": 50.0, "total_invoiced": 50.0,
             "total_difference": 0.0, "unmatched_invoice_count": 0},
        ],
    }]}
    resp = _build_comparison_response(outputs, "top_suppliers_invoiced_vs_ordered")
    assert "A:" in resp.summary and "B:" in resp.summary
    assert resp.truncation_notes  # truncated -> a note


# ─────────────────────────────────────────────────────────────────────
# Unit: planner routing (compare Intent -> Plan)
# ─────────────────────────────────────────────────────────────────────


def test_po_comparison_intent_builds_single_step():
    intent = Intent(target_entity="", compare={
        "op": "po_invoiced_vs_ordered", "po_number": "162034",
        "supplier_name": None, "top_n": 5, "status": None,
    })
    plan = generate_plan(intent)
    assert len(plan) == 1
    step = plan[0]
    assert step.tool_name == "compare_purchase_order_to_invoices"
    assert step.tool_args == {"po_number": "162034"}
    assert step.output_name == "comparison"


def test_supplier_comparison_intent_forwards_name_and_top_n():
    intent = Intent(target_entity="", compare={
        "op": "supplier_invoiced_vs_ordered", "po_number": None,
        "supplier_name": "Lee Supplies", "top_n": 5, "status": None,
    })
    step = generate_plan(intent)[0]
    assert step.tool_name == "compare_supplier_orders_to_invoices"
    assert step.tool_args == {"supplier_name": "Lee Supplies", "top_n": 5}


def test_top_suppliers_comparison_intent_forwards_top_n_status():
    intent = Intent(target_entity="", compare={
        "op": "top_suppliers_invoiced_vs_ordered", "po_number": None,
        "supplier_name": None, "top_n": 3, "status": "OPEN",
    })
    step = generate_plan(intent)[0]
    assert step.tool_name == "compare_top_suppliers_orders_to_invoices"
    assert step.tool_args == {"top_n": 3, "status": "OPEN"}


def test_po_comparison_does_not_forward_top_n():
    """The PO op's tool takes no top_n; the planner must not forward it
    even though the parser sets a default."""
    intent = Intent(target_entity="", compare={
        "op": "po_invoiced_vs_ordered", "po_number": "162034",
        "supplier_name": None, "top_n": 5, "status": None,
    })
    step = generate_plan(intent)[0]
    assert "top_n" not in step.tool_args


def test_unknown_comparison_op_raises():
    intent = Intent(target_entity="", compare={"op": "nonsense"})
    with pytest.raises(NotImplementedError):
        generate_plan(intent)


def test_aggregate_wins_when_both_set():
    """If a confused parse sets both, aggregate is checked first."""
    intent = Intent(
        target_entity="",
        aggregate={"op": "po_value_by_supplier", "top_n": 5},
        compare={"op": "po_invoiced_vs_ordered", "po_number": "1"},
    )
    step = generate_plan(intent)[0]
    assert step.tool_name == "aggregate_purchase_orders_by_supplier"


# ─────────────────────────────────────────────────────────────────────
# Unit: draft conversion (DraftCompare -> Intent)
# ─────────────────────────────────────────────────────────────────────


def test_draft_compare_converts_to_intent():
    draft = DraftIntent(
        target_entity="",
        compare=DraftCompare(op="po_invoiced_vs_ordered", po_number="162034"),
    )
    intent = draft.to_intent()
    assert intent.compare is not None
    assert intent.compare["op"] == "po_invoiced_vs_ordered"
    assert intent.compare["po_number"] == "162034"


def test_draft_compare_empty_strings_become_none():
    draft = DraftIntent(
        target_entity="",
        compare=DraftCompare(
            op="top_suppliers_invoiced_vs_ordered", top_n=3
        ),
    )
    intent = draft.to_intent()
    assert intent.compare["po_number"] is None
    assert intent.compare["supplier_name"] is None
    assert intent.compare["status"] is None
    assert intent.compare["top_n"] == 3


def test_draft_no_compare_is_none():
    draft = DraftIntent(target_entity="Supplier")
    assert draft.to_intent().compare is None


# ─────────────────────────────────────────────────────────────────────
# Integration: live pod (skipped by default)
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)
async def test_po_comparison_live_anchor():
    """PO 162034 on the pod: ordered 758.00 vs invoiced 830.01."""
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await compare_purchase_order_to_invoices(
            client, KNOWN_PO_NUMBER
        )
    assert result["found"] is True
    assert result["order_number"] == KNOWN_PO_NUMBER
    assert result["ordered"] == 758.0
    assert result["invoiced"] == 830.01
    assert result["difference"] == 72.01


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)
async def test_top_suppliers_comparison_live_shape():
    """Against the pod: top-2 comparison has the right shape and returns at
    most the requested number of supplier comparisons."""
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await compare_top_suppliers_orders_to_invoices(
            client, top_n=2
        )
    assert result["shape"] == "top_suppliers_invoiced_vs_ordered"
    assert result["returned"] <= 2
    for s in result["suppliers"]:
        assert s["shape"] == "supplier_invoiced_vs_ordered"
        # supplier_number was resolved from supplier_id
        assert s["supplier_number"] is not None
