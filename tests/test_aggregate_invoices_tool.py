"""
Tests for the aggregate_invoices_by_supplier tool (feature 7).

Two layers (mirrors tests/test_executor.py):

1. Unit tests with a mocked FusionClient. Cover the pure ranking logic
   (grouping, sum, tiebreaker, top_n cut, empty input) and the tool's
   fetch/filter/truncation behavior. No infrastructure required.

2. Integration tests against the live Fusion pod. Marked
   @pytest.mark.integration so they're skipped by default. Run with:
       pytest -m integration tests/test_aggregate_invoices_tool.py

   Requires personas.yaml present and the pod reachable.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.aggregate_invoices import (
    MAX_PAGES,
    OVERFETCH_LIMIT,
    _PAGE_SIZE,
    _aggregate_rows,
    aggregate_invoices_by_supplier,
)


def _inv(supplier, number, amount, date):
    return {
        "Supplier": supplier,
        "SupplierNumber": number,
        "InvoiceAmount": amount,
        "InvoiceDate": date,
    }


def _mock_client(items, total_results=None) -> AsyncMock:
    """A FusionClient whose .get returns a canned /invoices payload.

    The limit=1 totalResults probe and the main fetch both return the
    same items list; tests that care about the distinction assert on the
    recorded call params instead.

    total_results IS STUBBED EXPLICITLY. The tool calls
    client.total_results(...) before paging, and on a bare AsyncMock that
    returns another AsyncMock rather than an int — which then blew up on
    the first comparison:

        TypeError: '>' not supported between instances of
                   'AsyncMock' and 'int'

    Six tests failed that way, and failing was the right outcome: a mock
    that answered the probe with a plausible-looking object would have
    let the cap-warning arithmetic run on nonsense. FusionClient.
    total_results returns int | None, and None is a real and documented
    answer — Fusion omits totalResults on some resources — so the default
    here exercises the degrade path that most of these tests want.

    Pass a number to exercise the probe path instead.
    """
    client = AsyncMock()
    client.total_results = AsyncMock(return_value=total_results)

    async def _get(path, params=None):
        params = params or {}
        # totalResults probe (limit=1), if any caller still uses it.
        if params.get("limit") == 1:
            return {"totalResults": total_results, "items": items[:1]}
        # Paginated fetch: serve the slice at offset, report hasMore.
        offset = params.get("offset", 0)
        limit = params.get("limit", len(items))
        page = items[offset : offset + limit]
        has_more = offset + limit < len(items)
        return {"items": page, "hasMore": has_more}

    client.get.side_effect = _get
    return client


# ─────────────────────────────────────────────────────────────────────
# Unit: pure ranking logic (_aggregate_rows)
# ─────────────────────────────────────────────────────────────────────


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
    assert rows[0]["supplier"] == "S00"
    assert rows[-1]["supplier"] == "S09"


def test_tie_at_boundary_cut_is_deterministic():
    """11 suppliers; the bottom two tie on spend. top_n=10 cuts at exactly
    10, and which one is dropped is stable (name ascending: Xray kept,
    Yankee dropped)."""
    invoices = [
        _inv(f"S{i:02d}", str(i), 1000 - i, "2026-01-01") for i in range(9)
    ]
    invoices.append(_inv("Yankee", "98", 0, "2026-01-01"))
    invoices.append(_inv("Xray", "99", 0, "2026-01-01"))
    rows, total = _aggregate_rows(invoices, top_n=10)
    assert total == 11
    assert len(rows) == 10
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
    assert rows[0]["invoice_count"] == 3


def test_unattributable_invoice_skipped():
    invoices = [
        _inv("", "", 100, "2026-01-01"),
        _inv("Acme", "1", 50, "2026-01-02"),
    ]
    rows, total = _aggregate_rows(invoices, top_n=10)
    assert total == 1
    assert rows[0]["supplier"] == "Acme"


def test_empty_input():
    rows, total = _aggregate_rows([], top_n=10)
    assert rows == []
    assert total == 0


# ─────────────────────────────────────────────────────────────────────
# Unit: tool behavior (mocked client)
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_happy_path():
    items = [
        _inv("Acme", "1", 100, "2026-01-05"),
        _inv("Acme", "1", 200, "2026-02-09"),
        _inv("Globex", "2", 500, "2026-03-10"),
    ]
    client = _mock_client(items)
    result = await aggregate_invoices_by_supplier(
        client, date_from="2026-01-01", date_to="2026-04-01", top_n=10
    )
    assert result["shape"] == "supplier_spend_ranking"
    assert result["date_from"] == "2026-01-01"
    assert result["date_to"] == "2026-04-01"
    assert result["total_suppliers"] == 2
    assert result["returned"] == 2
    assert result["truncated"] is False
    assert result["rows"][0]["supplier"] == "Globex"
    assert result["rows"][1]["supplier"] == "Acme"


@pytest.mark.asyncio
async def test_tool_sends_date_from_as_server_clause():
    client = _mock_client([])
    await aggregate_invoices_by_supplier(client, date_from="2026-01-01")
    # Every fetch page carries the date clause as q=.
    calls = client.get.call_args_list
    assert calls
    params = calls[0].kwargs.get("params") or calls[0].args[1]
    assert params["q"] == "InvoiceDate >= '2026-01-01'"
    assert params["limit"] == _PAGE_SIZE


@pytest.mark.asyncio
async def test_tool_client_side_upper_bound():
    items = [
        _inv("Acme", "1", 100, "2026-01-05"),
        _inv("Acme", "1", 9999, "2026-12-31"),  # past date_to
    ]
    client = _mock_client(items)
    result = await aggregate_invoices_by_supplier(
        client, date_from="2026-01-01", date_to="2026-04-01"
    )
    assert result["rows"][0]["total_spend"] == 100


@pytest.mark.asyncio
async def test_tool_empty_range_is_well_formed():
    client = _mock_client([])
    result = await aggregate_invoices_by_supplier(
        client, date_from="2030-01-01", date_to="2030-02-01"
    )
    assert result["total_suppliers"] == 0
    assert result["returned"] == 0
    assert result["rows"] == []
    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_tool_truncation_flag_when_page_cap_hit():
    # More invoices than MAX_PAGES * _PAGE_SIZE means the page cap is hit
    # before the pod runs out, so the aggregate is incomplete -> truncated.
    items = [
        _inv(f"S{i}", str(i), 10, "2026-01-01")
        for i in range(OVERFETCH_LIMIT + _PAGE_SIZE)
    ]
    client = _mock_client(items)
    result = await aggregate_invoices_by_supplier(client, date_from="2026-01-01")
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_tool_not_truncated_when_pod_runs_out():
    # Fewer invoices than the cap: the pod signals hasMore=false and the
    # aggregate is exact -> not truncated.
    items = [
        _inv(f"S{i}", str(i), 10, "2026-01-01") for i in range(_PAGE_SIZE + 5)
    ]
    client = _mock_client(items)
    result = await aggregate_invoices_by_supplier(client, date_from="2026-01-01")
    assert result["truncated"] is False
    # All distinct suppliers were seen.
    assert result["total_suppliers"] == _PAGE_SIZE + 5


@pytest.mark.asyncio
async def test_tool_carries_the_probe_count_to_the_caller():
    """total_available and examined ride on the result.

    Without them a summary can say the fetch stopped at the cap but not
    how much was missed, and the difference between those two sentences
    is the difference between a footnote and a warning. Measured on the
    live pod: /invoices holds 48,931 records against a 25,000 cap, so a
    spend ranking covers 51% — worth stating as a number rather than as
    "there may be more".
    """
    items = [_inv("Acme", "1", 100, "2026-01-05")]
    client = _mock_client(items, total_results=48931)

    result = await aggregate_invoices_by_supplier(
        client, date_from="2026-01-01"
    )

    assert result["total_available"] == 48931
    assert result["examined"] == len(items)


@pytest.mark.asyncio
async def test_tool_survives_a_pod_that_reports_no_total():
    """None is a real answer, not a failure.

    Fusion omits totalResults on some resources and some parameter
    combinations. Everything the probe enables — the denominator, the
    up-front cap warning, the count in the truncation note — degrades to
    what the loop did before the probe existed, and the aggregate itself
    is unaffected.
    """
    items = [
        _inv("Acme", "1", 100, "2026-01-05"),
        _inv("Globex", "2", 500, "2026-01-06"),
    ]
    client = _mock_client(items, total_results=None)

    result = await aggregate_invoices_by_supplier(
        client, date_from="2026-01-01"
    )

    assert result["total_available"] is None
    assert result["total_suppliers"] == 2
    assert result["truncated"] is False


# ─────────────────────────────────────────────────────────────────────
# Integration: live Fusion pod (skipped by default)
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)
async def test_aggregate_live_pod_shape_and_ordering():
    """Against the live pod: the result has the right shape, returns at
    most top_n rows, and rows are ranked by spend descending."""
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await aggregate_invoices_by_supplier(
            client, date_from="2022-01-01", date_to="2023-01-01", top_n=10
        )
    assert result["shape"] == "supplier_spend_ranking"
    assert result["returned"] <= 10
    assert result["returned"] <= result["total_suppliers"]
    spends = [r["total_spend"] for r in result["rows"]]
    assert spends == sorted(spends, reverse=True)
