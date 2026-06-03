"""Offline unit tests for aggregate_invoices_by_supplier.

No network, no Fusion, no KG. The pure ranking function is tested
directly; the async tool is tested with a fake client that returns a
canned /invoices response.

Run: python -m pytest test_aggregate_invoices.py -v
(or just `python test_aggregate_invoices.py` for a quick smoke run.)
"""

from __future__ import annotations

import asyncio

from spire.mcp_server.tools.aggregate_invoices import (
    _aggregate_rows, aggregate_invoices_by_supplier, OVERFETCH_LIMIT,
)

# ── Fake client ───────────────────────────────────────────────────────

class FakeClient:
    """Stand-in for FusionClient. Returns a fixed payload for .get and
    records the params it was called with so tests can assert on the
    server clause."""

    def __init__(self, items, total_results=None):
        self._items = items
        self._total = total_results
        self.calls = []

    async def get(self, path, params=None):
        self.calls.append((path, params or {}))
        # totalResults probe (limit=1) gets the count; the main fetch
        # gets the items.
        if params and params.get("limit") == 1:
            return {"totalResults": self._total, "items": self._items[:1]}
        return {"items": self._items}


def _inv(supplier, number, amount, date):
    return {
        "Supplier": supplier,
        "SupplierNumber": number,
        "InvoiceAmount": amount,
        "InvoiceDate": date,
    }


# ── Pure ranking function ─────────────────────────────────────────────

def test_basic_grouping_and_sum():
    invoices = [
        _inv("Acme", "1", 100, "2026-01-05"),
        _inv("Acme", "1", 200, "2026-01-09"),
        _inv("Globex", "2", 50, "2026-01-10"),
    ]
    rows, total = _aggregate_rows(invoices, top_n=10)
    assert total == 2
    assert rows[0]["supplier"] == "Acme"
    assert rows[0]["total_spend"] == 300
    assert rows[0]["invoice_count"] == 2
    assert rows[1]["supplier"] == "Globex"
    assert rows[1]["total_spend"] == 50


def test_sorted_by_spend_descending():
    invoices = [
        _inv("Small", "1", 10, "2026-01-01"),
        _inv("Big", "2", 1000, "2026-01-01"),
        _inv("Mid", "3", 500, "2026-01-01"),
    ]
    rows, _ = _aggregate_rows(invoices, top_n=10)
    assert [r["supplier"] for r in rows] == ["Big", "Mid", "Small"]


def test_tiebreaker_name_ascending():
    # Equal spend; names must break the tie ascending and deterministically.
    invoices = [
        _inv("Zeta", "1", 100, "2026-01-01"),
        _inv("Alpha", "2", 100, "2026-01-01"),
        _inv("Mike", "3", 100, "2026-01-01"),
    ]
    rows, _ = _aggregate_rows(invoices, top_n=10)
    assert [r["supplier"] for r in rows] == ["Alpha", "Mike", "Zeta"]


def test_top_n_cut_is_exact():
    invoices = [
        _inv(f"S{i:02d}", str(i), 100 - i, "2026-01-01") for i in range(20)
    ]
    rows, total = _aggregate_rows(invoices, top_n=10)
    assert total == 20
    assert len(rows) == 10
    # Highest spend is S00 (100-0); lowest kept is S09 (100-9=91).
    assert rows[0]["supplier"] == "S00"
    assert rows[-1]["supplier"] == "S09"


def test_tie_at_boundary_cut_is_deterministic():
    # 11 suppliers, the 10th and 11th tie on spend. top_n=10 must cut at
    # exactly 10, and which one is dropped must be stable (name order).
    invoices = [
        _inv(f"S{i:02d}", str(i), 1000 - i, "2026-01-01") for i in range(9)
    ]
    # two suppliers tied at spend 0
    invoices.append(_inv("Yankee", "98", 0, "2026-01-01"))
    invoices.append(_inv("Xray", "99", 0, "2026-01-01"))
    rows, total = _aggregate_rows(invoices, top_n=10)
    assert total == 11
    assert len(rows) == 10
    # Of the tied pair, "Xray" < "Yankee", so Xray is kept, Yankee dropped.
    kept = {r["supplier"] for r in rows}
    assert "Xray" in kept
    assert "Yankee" not in kept


def test_non_numeric_amount_counts_but_adds_zero():
    invoices = [
        _inv("Acme", "1", None, "2026-01-01"),
        _inv("Acme", "1", "bad", "2026-01-02"),
        _inv("Acme", "1", 100, "2026-01-03"),
    ]
    rows, _ = _aggregate_rows(invoices, top_n=10)
    assert rows[0]["total_spend"] == 100
    assert rows[0]["invoice_count"] == 3  # all three counted


def test_unattributable_invoice_skipped():
    invoices = [
        _inv("", "", 100, "2026-01-01"),   # no supplier at all -> skip
        _inv("Acme", "1", 50, "2026-01-02"),
    ]
    rows, total = _aggregate_rows(invoices, top_n=10)
    assert total == 1
    assert rows[0]["supplier"] == "Acme"


def test_empty_input():
    rows, total = _aggregate_rows([], top_n=10)
    assert rows == []
    assert total == 0


# ── Async tool ────────────────────────────────────────────────────────

def test_tool_happy_path():
    items = [
        _inv("Acme", "1", 100, "2026-01-05"),
        _inv("Acme", "1", 200, "2026-02-09"),
        _inv("Globex", "2", 500, "2026-03-10"),
    ]
    client = FakeClient(items)
    result = asyncio.run(
        aggregate_invoices_by_supplier(
            client, date_from="2026-01-01", date_to="2026-04-01", top_n=10
        )
    )
    assert result["shape"] == "supplier_spend_ranking"
    assert result["date_from"] == "2026-01-01"
    assert result["date_to"] == "2026-04-01"
    assert result["total_suppliers"] == 2
    assert result["returned"] == 2
    assert result["truncated"] is False
    assert result["rows"][0]["supplier"] == "Globex"  # 500 > 300
    assert result["rows"][1]["supplier"] == "Acme"


def test_tool_sends_date_from_as_server_clause():
    client = FakeClient([])
    asyncio.run(
        aggregate_invoices_by_supplier(client, date_from="2026-01-01")
    )
    # The main fetch (limit=OVERFETCH_LIMIT) must carry the date clause.
    main_calls = [c for c in client.calls if c[1].get("limit") == OVERFETCH_LIMIT]
    assert main_calls
    assert main_calls[0][1]["q"] == "InvoiceDate >= '2026-01-01'"


def test_tool_client_side_upper_bound():
    # Two invoices, one inside the range and one past date_to. Only the
    # in-range one should aggregate.
    items = [
        _inv("Acme", "1", 100, "2026-01-05"),
        _inv("Acme", "1", 9999, "2026-12-31"),  # past date_to
    ]
    client = FakeClient(items)
    result = asyncio.run(
        aggregate_invoices_by_supplier(
            client, date_from="2026-01-01", date_to="2026-04-01"
        )
    )
    assert result["rows"][0]["total_spend"] == 100  # 9999 excluded


def test_tool_empty_range_is_well_formed():
    client = FakeClient([])
    result = asyncio.run(
        aggregate_invoices_by_supplier(
            client, date_from="2030-01-01", date_to="2030-02-01"
        )
    )
    assert result["total_suppliers"] == 0
    assert result["returned"] == 0
    assert result["rows"] == []
    assert result["truncated"] is False


def test_tool_truncation_flag_when_ceiling_hit():
    # Fabricate OVERFETCH_LIMIT identical-shape invoices so the raw fetch
    # hits the ceiling and truncated must be True.
    items = [
        _inv(f"S{i}", str(i), 10, "2026-01-01") for i in range(OVERFETCH_LIMIT)
    ]
    client = FakeClient(items)
    result = asyncio.run(
        aggregate_invoices_by_supplier(client, date_from="2026-01-01")
    )
    assert result["truncated"] is True


if __name__ == "__main__":
    # Lightweight runner so this works without pytest installed.
    import traceback

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
