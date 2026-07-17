"""Unit tests for the PO aggregation functions.

These test the PURE functions — _aggregate_rows, _aggregate_by_status and
_summarize — which take a list of PO dicts and return computed results.
No pod, no client, no mocking: the arithmetic is the thing under test.

Why these matter more than usual: the synthesizer's hallucination guard
checks that IDs exist in the source, but an aggregation's NUMBERS are the
answer, and the guard cannot validate them. If the grouping or summing is
wrong, nothing downstream catches it — the LLM will faithfully report a
wrong total. These tests are that check.

Deliberately NOT asserting live pod totals: the demo pod's data shifts
(a PO moved from CLOSED to another status mid-session during P6), so
exact-value assertions against it would be flaky. Fixtures here are
hand-built and stable.
"""

import pytest

from spire.mcp_server.tools.aggregate_purchase_orders import (
    _aggregate_by_status,
    _aggregate_rows,
    _summarize,
)


def _po(supplier_id=1, supplier="Acme", ordered=100.0, status="OPEN"):
    """One PO dict shaped like the tool's projection."""
    return {
        "SupplierId": supplier_id,
        "Supplier": supplier,
        "Ordered": ordered,
        "StatusCode": status,
    }


# ── _aggregate_rows: group by supplier, sum Ordered, rank ──


def test_aggregate_rows_groups_and_sums_by_supplier():
    pos = [
        _po(1, "Acme", 100.0),
        _po(1, "Acme", 50.0),
        _po(2, "Globex", 30.0),
    ]
    rows, total_suppliers = _aggregate_rows(pos, top_n=10)
    assert total_suppliers == 2
    assert rows[0] == {
        "supplier": "Acme",
        "supplier_id": 1,
        "total_ordered": 150.0,
        "po_count": 2,
    }


def test_aggregate_rows_ranks_by_value_descending():
    pos = [_po(1, "Small", 10.0), _po(2, "Big", 900.0), _po(3, "Mid", 50.0)]
    rows, _ = _aggregate_rows(pos, top_n=10)
    assert [r["supplier"] for r in rows] == ["Big", "Mid", "Small"]


def test_aggregate_rows_tiebreaks_on_name_for_determinism():
    """Equal totals must rank by name ascending, so 'the Nth supplier' is
    the same supplier on every run and the top_n cut isn't arbitrary."""
    pos = [_po(1, "Zeta", 100.0), _po(2, "Alpha", 100.0)]
    rows, _ = _aggregate_rows(pos, top_n=10)
    assert [r["supplier"] for r in rows] == ["Alpha", "Zeta"]


def test_aggregate_rows_cuts_to_top_n_but_counts_all_suppliers():
    pos = [_po(i, f"S{i}", float(i)) for i in range(1, 6)]
    rows, total_suppliers = _aggregate_rows(pos, top_n=2)
    assert len(rows) == 2
    # total_suppliers is the count BEFORE the cut, so a caller can say
    # "top 2 of 5".
    assert total_suppliers == 5


def test_aggregate_rows_skips_unattributable_pos():
    """A PO with neither SupplierId nor Supplier can't be attributed."""
    pos = [_po(1, "Acme", 100.0), {"Ordered": 999.0, "StatusCode": "OPEN"}]
    rows, total_suppliers = _aggregate_rows(pos, top_n=10)
    assert total_suppliers == 1
    assert rows[0]["total_ordered"] == 100.0


def test_aggregate_rows_counts_po_with_missing_amount_but_adds_zero():
    """A missing/non-numeric Ordered contributes 0 to the sum but still
    counts — po_count stays an honest 'how many POs we saw'."""
    pos = [_po(1, "Acme", 100.0), _po(1, "Acme", None), _po(1, "Acme", "n/a")]
    rows, _ = _aggregate_rows(pos, top_n=10)
    assert rows[0]["total_ordered"] == 100.0
    assert rows[0]["po_count"] == 3


def test_aggregate_rows_empty_input():
    rows, total_suppliers = _aggregate_rows([], top_n=10)
    assert rows == []
    assert total_suppliers == 0


# ── _aggregate_by_status: group by StatusCode, count + sum ──


def test_aggregate_by_status_groups_counts_and_sums():
    pos = [
        _po(1, "Acme", 100.0, "OPEN"),
        _po(2, "Globex", 50.0, "OPEN"),
        _po(3, "Initech", 25.0, "CLOSED"),
    ]
    rows, grand_count, grand_total = _aggregate_by_status(pos)
    assert grand_count == 3
    assert grand_total == 175.0
    assert rows[0] == {"status": "OPEN", "po_count": 2, "total_ordered": 150.0}


def test_aggregate_by_status_orders_by_value_descending():
    pos = [
        _po(1, "A", 10.0, "CANCELED"),
        _po(2, "B", 500.0, "CLOSED"),
        _po(3, "C", 100.0, "OPEN"),
    ]
    rows, _, _ = _aggregate_by_status(pos)
    assert [r["status"] for r in rows] == ["CLOSED", "OPEN", "CANCELED"]


def test_aggregate_by_status_keeps_closed_variants_distinct():
    """CLOSED, CLOSED FOR RECEIVING and CLOSED FOR INVOICING are genuinely
    different states and must NOT be merged — merging them would silently
    change the answer to 'how many closed POs'."""
    pos = [
        _po(1, "A", 100.0, "CLOSED"),
        _po(2, "B", 50.0, "CLOSED FOR RECEIVING"),
        _po(3, "C", 25.0, "CLOSED FOR INVOICING"),
    ]
    rows, grand_count, _ = _aggregate_by_status(pos)
    assert len(rows) == 3
    assert grand_count == 3
    assert {r["status"] for r in rows} == {
        "CLOSED",
        "CLOSED FOR RECEIVING",
        "CLOSED FOR INVOICING",
    }


def test_aggregate_by_status_buckets_missing_status_rather_than_dropping():
    """A PO with no StatusCode is still a real PO whose value belongs in
    the total — dropping it would understate the answer."""
    pos = [_po(1, "Acme", 100.0, "OPEN"), {"SupplierId": 2, "Ordered": 40.0}]
    rows, grand_count, grand_total = _aggregate_by_status(pos)
    assert grand_count == 2
    assert grand_total == 140.0
    assert any(r["status"] == "(unknown)" for r in rows)


def test_aggregate_by_status_empty_input():
    rows, grand_count, grand_total = _aggregate_by_status([])
    assert rows == []
    assert grand_count == 0
    assert grand_total == 0.0


# ── _summarize: count + sum + distinct suppliers ──


def test_summarize_counts_sums_and_counts_distinct_suppliers():
    pos = [
        _po(1, "Acme", 100.0),
        _po(1, "Acme", 50.0),
        _po(2, "Globex", 30.0),
    ]
    po_count, total_ordered, supplier_count = _summarize(pos)
    assert po_count == 3
    assert total_ordered == 180.0
    assert supplier_count == 2


def test_summarize_counts_po_with_missing_amount():
    pos = [_po(1, "Acme", 100.0), _po(1, "Acme", None)]
    po_count, total_ordered, _ = _summarize(pos)
    assert po_count == 2
    assert total_ordered == 100.0


def test_summarize_empty_input():
    assert _summarize([]) == (0, 0.0, 0)


# ── cross-consistency: the tools must agree with each other ──


def test_status_breakdown_open_row_matches_summarize():
    """The same POs must produce the same open figures whether you get
    them from the status breakdown or the open summary. On the live pod
    these agreed exactly (201 POs / 116,643,997.40); this pins that
    consistency without depending on pod data."""
    open_pos = [_po(1, "Acme", 100.0, "OPEN"), _po(2, "Globex", 50.0, "OPEN")]
    all_pos = open_pos + [_po(3, "Initech", 999.0, "CLOSED")]

    rows, _, _ = _aggregate_by_status(all_pos)
    open_row = next(r for r in rows if r["status"] == "OPEN")
    po_count, total_ordered, _ = _summarize(open_pos)

    assert open_row["po_count"] == po_count
    assert open_row["total_ordered"] == total_ordered


def test_ranking_supplier_count_matches_summarize():
    """The ranking's total_suppliers and the summary's supplier_count are
    computed independently; for the same POs they must agree."""
    pos = [_po(1, "Acme", 100.0), _po(1, "Acme", 50.0), _po(2, "Globex", 30.0)]
    _, total_suppliers = _aggregate_rows(pos, top_n=10)
    _, _, supplier_count = _summarize(pos)
    assert total_suppliers == supplier_count
