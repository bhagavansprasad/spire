"""Tests for aggregate_standard_receipts_by_method.

THIS TOOL HAD NO TESTS UNTIL 2026-08-04, which is worth stating plainly
because of what it has been doing. It is the tool behind the longest-
running wrong-number defect in the project:

    2026-07-22  account 26360, consecutive days, identical code:
                both runs 1,386 receipts, totals 215,721,775.28 and
                250,557,301.49 — a 35M difference, no error either time
    2026-08-04  pod-wide, minutes apart:
                both runs 5,000 receipts, totals 874,836,787.64 and
                977,327,230.90, Lockbox moving 4,754 -> 4,934

/standardReceipts has no default ordering, so walking `offset` without
an `orderBy` sees a different slice on every call. The endpoints
reference recorded the rule — any paginated fetch here must specify a
deterministic orderBy — with the sort key unconfirmed. It is confirmed
now, the tool sends it, and these tests hold it in place.

Note test_standard_receipts_tool.py covers the SEARCH tool over the same
resource, not this one. Running it after this tool changed reported five
passes and proved nothing, which is how a file named for the wrong tool
reads as coverage.

WHY EACH ASSERTION EXISTS
Every test here corresponds to a way this tool has produced, or could
produce, a plausible wrong answer with no error:

  - no orderBy          -> a different sample each run
  - too low a cap       -> a systematically skewed sample, stably wrong
  - unscoped fallback   -> one customer's question answered pod-wide
  - offset by page size -> silently skipped or repeated rows
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import spire.mcp_server.tools.aggregate_standard_receipts_by_method as mod
from spire.mcp_server.tools.aggregate_standard_receipts_by_method import (
    MAX_UNSCOPED_PAGES,
    PAGE_SIZE,
    aggregate_standard_receipts_by_method,
)


RECEIPTS_PATH = "/fscmRestApi/resources/11.13.18.05/standardReceipts"


def _receipt(method: str, amount: float) -> dict:
    return {"ReceiptMethod": method, "Amount": amount}


def _paging_client(pages: list[list[dict]]) -> AsyncMock:
    """A client that serves the given pages in order and records params.

    hasMore is derived: true while pages remain. That models the pod
    closely enough for paging assertions, and the recorded params are
    what the ordering tests read.
    """
    client = AsyncMock()
    remaining = list(pages)

    async def _get(path, params=None):
        items = remaining.pop(0) if remaining else []
        return {"items": items, "hasMore": bool(remaining)}

    client.get.side_effect = _get
    return client


@pytest.fixture
def resolver(monkeypatch):
    """Patch the name->account resolver in this module's namespace."""
    def _set(accounts):
        async def fake_resolver(client, customer_name, limit=1):
            return accounts
        monkeypatch.setattr(mod, "get_customer_account_by_name", fake_resolver)
    return _set


# ─────────────────────────────────────────────────────────────────────
# Ordering — the reproducibility fix
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_every_page_requests_a_deterministic_order():
    """orderBy on EVERY page, not just the first.

    Offset paging is only meaningful against a stable order. A first page
    ordered and the rest not would still shuffle, and would look correct
    in any test that only inspected call zero.
    """
    client = _paging_client([
        [_receipt("Lockbox", 100.0)],
        [_receipt("Check", 50.0)],
        [],
    ])

    await aggregate_standard_receipts_by_method(client)

    assert client.get.call_count >= 2
    for call in client.get.call_args_list:
        params = call.kwargs.get("params") or call.args[1]
        assert params["orderBy"] == "StandardReceiptId"


@pytest.mark.asyncio
async def test_sort_key_is_the_primary_key():
    """StandardReceiptId, not ReceiptNumber.

    An ordered fetch returned two rows both numbered "1", so
    ReceiptNumber is not unique on this pod and gives no deterministic
    tiebreak — rows sharing a sort value can still swap between calls.
    The PK cannot.
    """
    assert mod._ORDER_BY == "StandardReceiptId"


@pytest.mark.asyncio
async def test_offset_advances_by_the_rows_actually_returned():
    """A short page must not desync the offset.

    Advancing by PAGE_SIZE when the pod returned fewer rows skips the
    difference silently; advancing by len(items) cannot.
    """
    client = _paging_client([
        [_receipt("Lockbox", 10.0)] * 3,
        [_receipt("Check", 5.0)] * 2,
        [],
    ])

    await aggregate_standard_receipts_by_method(client)

    offsets = [
        (call.kwargs.get("params") or call.args[1])["offset"]
        for call in client.get.call_args_list
    ]
    assert offsets[:3] == [0, 3, 5]


# ─────────────────────────────────────────────────────────────────────
# The cap
# ─────────────────────────────────────────────────────────────────────


def test_the_unscoped_cap_clears_the_collection():
    """100 pages x 500 rows = 50,000, against 37,338 receipts.

    Raised from 10 in the same change that added the ordering, and the
    two had to ship together. Ordered by PK ascending, a 10-page cap
    takes the OLDEST 5,000 rather than an arbitrary 5,000 — measured, the
    method split went from 4,754 Lockbox / 179 Check to 4,998 Lockbox and
    no Check at all, while the full 37,338 shows Check at 18,480, within
    a percent of Lockbox. Ordering alone would have shipped a repeatable
    answer that was more wrong than the random one it replaced.

    Asserted as a number so that lowering it is a deliberate act with a
    failing test attached.
    """
    assert PAGE_SIZE * MAX_UNSCOPED_PAGES >= 37338


@pytest.mark.asyncio
async def test_unscoped_fetch_stops_at_the_cap_and_says_so(monkeypatch):
    monkeypatch.setattr(mod, "MAX_UNSCOPED_PAGES", 2)
    # Always another page: the pod never signals the end.
    client = AsyncMock()

    async def _get(path, params=None):
        return {"items": [_receipt("Lockbox", 1.0)], "hasMore": True}

    client.get.side_effect = _get

    result = await aggregate_standard_receipts_by_method(client)

    assert result["truncated"] is True
    assert client.get.call_count == 2


@pytest.mark.asyncio
async def test_a_completed_fetch_is_not_flagged_truncated():
    client = _paging_client([[_receipt("Lockbox", 100.0)]])

    result = await aggregate_standard_receipts_by_method(client)

    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_scoped_fetch_is_not_bounded_by_the_unscoped_cap(monkeypatch):
    """An account's receipts page to exhaustion.

    The cap exists because the pod-wide set is unbounded; an account's is
    not (1,386 on the largest demo account). A scoped fetch that stopped
    at the cap would under-report a customer's own receipts.
    """
    monkeypatch.setattr(mod, "MAX_UNSCOPED_PAGES", 1)
    client = _paging_client([
        [_receipt("Lockbox", 10.0)],
        [_receipt("Lockbox", 10.0)],
        [_receipt("Check", 5.0)],
        [],
    ])

    result = await aggregate_standard_receipts_by_method(
        client, account_number="26360"
    )

    assert client.get.call_count > 1
    assert result["truncated"] is False
    assert result["total_receipts"] == 3


# ─────────────────────────────────────────────────────────────────────
# Scoping — refusing rather than widening
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scoped_fetch_sends_the_account_clause(resolver):
    resolver([{"AccountId": 1, "AccountNumber": "26360"}])
    client = _paging_client([[_receipt("Lockbox", 100.0)]])

    await aggregate_standard_receipts_by_method(
        client, customer_name="ABC Application Software"
    )

    params = client.get.call_args_list[0].kwargs["params"]
    assert params["q"] == "CustomerAccountNumber='26360'"
    # Single clause. Composite q= returns HTTP 200 with totalResults 0 on
    # this endpoint — the silent-zero failure, with no error to catch.
    assert " AND " not in params["q"]


@pytest.mark.asyncio
async def test_unresolvable_customer_raises_rather_than_widening(resolver):
    """A name that resolves to nothing must NOT fall through pod-wide.

    That would answer a customer-scoped question with every customer's
    receipts and attach the customer's name to it — plausible, wholly
    wrong, and no error.
    """
    resolver([])
    client = _paging_client([[_receipt("Lockbox", 100.0)]])

    with pytest.raises(ValueError, match="No customer account found"):
        await aggregate_standard_receipts_by_method(
            client, customer_name="Nobody Ltd"
        )

    client.get.assert_not_called()


@pytest.mark.asyncio
async def test_no_scope_sends_no_clause():
    """Pod-wide is a legitimate call, not a missing argument."""
    client = _paging_client([[_receipt("Lockbox", 100.0)]])

    await aggregate_standard_receipts_by_method(client)

    params = client.get.call_args_list[0].kwargs["params"]
    assert "q" not in params


@pytest.mark.asyncio
async def test_no_fields_projection_is_ever_sent():
    """/standardReceipts 500s on fields= even when every name is valid.

    Confirmed twice in the endpoints reference, and it cost six
    misdiagnosed calls — twice read as a dead endpoint. Fetch full rows
    and discard client-side.
    """
    client = _paging_client([[_receipt("Lockbox", 100.0)]])

    await aggregate_standard_receipts_by_method(client)

    for call in client.get.call_args_list:
        params = call.kwargs.get("params") or call.args[1]
        assert "fields" not in params


# ─────────────────────────────────────────────────────────────────────
# The arithmetic
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_groups_by_method_and_sums_across_pages():
    client = _paging_client([
        [_receipt("Lockbox", 100.0), _receipt("Check", 50.0)],
        [_receipt("Lockbox", 25.0)],
        [],
    ])

    result = await aggregate_standard_receipts_by_method(client)

    assert result["shape"] == "receipt_method_distribution"
    assert result["total_receipts"] == 3
    assert result["total_amount"] == 175.0
    rows = {r["receipt_method"]: r for r in result["rows"]}
    assert rows["Lockbox"]["receipt_count"] == 2
    assert rows["Lockbox"]["total_amount"] == 125.0
    assert rows["Check"]["receipt_count"] == 1


@pytest.mark.asyncio
async def test_rows_are_sorted_by_amount_descending():
    client = _paging_client([[
        _receipt("Small", 1.0),
        _receipt("Big", 900.0),
        _receipt("Mid", 50.0),
    ]])

    result = await aggregate_standard_receipts_by_method(client)

    assert [r["receipt_method"] for r in result["rows"]] == [
        "Big", "Mid", "Small"
    ]


@pytest.mark.asyncio
async def test_a_missing_method_is_grouped_not_dropped():
    """A null ReceiptMethod becomes "(unknown)".

    Dropping it would make the group counts disagree with
    total_receipts — a discrepancy nothing downstream would notice.
    """
    client = _paging_client([[
        {"ReceiptMethod": None, "Amount": 10.0},
        _receipt("Lockbox", 5.0),
    ]])

    result = await aggregate_standard_receipts_by_method(client)

    methods = {r["receipt_method"] for r in result["rows"]}
    assert "(unknown)" in methods
    assert result["total_receipts"] == 2


@pytest.mark.asyncio
async def test_a_non_numeric_amount_counts_but_adds_zero():
    """The receipt was seen; its amount was not usable.

    Counting it keeps total_receipts honest; adding nothing keeps the
    total honest. Skipping the row entirely would lose both.
    """
    client = _paging_client([[
        {"ReceiptMethod": "Lockbox", "Amount": None},
        _receipt("Lockbox", 5.0),
    ]])

    result = await aggregate_standard_receipts_by_method(client)

    assert result["total_receipts"] == 2
    assert result["total_amount"] == 5.0
    assert result["rows"][0]["receipt_count"] == 2


@pytest.mark.asyncio
async def test_limit_trims_groups_after_ranking_not_before():
    """The limit is a display cut, not a fetch bound.

    Trimming before the sort would return an arbitrary N rather than the
    top N, and the totals must still cover every receipt seen.
    """
    client = _paging_client([[
        _receipt("Small", 1.0),
        _receipt("Big", 900.0),
        _receipt("Mid", 50.0),
    ]])

    result = await aggregate_standard_receipts_by_method(client, limit=2)

    assert [r["receipt_method"] for r in result["rows"]] == ["Big", "Mid"]
    assert result["returned"] == 2
    # Totals still describe everything fetched, not just what is shown.
    assert result["total_receipts"] == 3
    assert result["total_amount"] == 951.0


@pytest.mark.asyncio
async def test_empty_result_is_well_formed():
    """Zero receipts is an answer, not an error."""
    client = _paging_client([[]])

    result = await aggregate_standard_receipts_by_method(client)

    assert result["total_receipts"] == 0
    assert result["total_amount"] == 0.0
    assert result["rows"] == []
    assert result["truncated"] is False
