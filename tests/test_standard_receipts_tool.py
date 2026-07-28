"""Tests for the standard_receipts tool.

INTERFACE NOTE
search_standard_receipts takes customer_name, NOT account_number. The
name is resolved to an account number inside the tool via
get_customer_account_by_name, so a scoped call makes TWO calls: the
resolution, then the receipts fetch. These tests patch the resolver in
the standard_receipts namespace (where it is imported) rather than at
its source.

Its sibling aggregate_standard_receipts_by_method still accepts BOTH
customer_name and account_number. That asymmetry between two tools over
the same /standardReceipts resource is deliberate as far as these tests
are concerned, but it is worth revisiting: a user asking "receipts for
account 26360" can be served by one and not the other.
"""

import pytest
from unittest.mock import AsyncMock

import spire.mcp_server.tools.standard_receipts as standard_receipts
from spire.mcp_server.tools.standard_receipts import (
    OVERFETCH_LIMIT,
    search_standard_receipts,
)


RECEIPTS_PATH = "/fscmRestApi/resources/11.13.18.05/standardReceipts"


@pytest.fixture
def resolver(monkeypatch):
    """Patch the name->account resolver in the standard_receipts namespace.

    Returns a setter so each test declares what the resolution yields:
    an account list, or [] for "no such customer".
    """
    def _set(accounts):
        async def fake_resolver(client, customer_name, limit=25):
            return accounts
        monkeypatch.setattr(
            standard_receipts, "get_customer_account_by_name", fake_resolver
        )
    return _set


@pytest.mark.asyncio
async def test_search_standard_receipts_no_filters_raises():
    """Calling with neither customer_name nor customer_site raises."""
    client = AsyncMock()
    with pytest.raises(
        ValueError, match="At least one of customer_name or customer_site"
    ):
        await search_standard_receipts(client)


@pytest.mark.asyncio
async def test_search_standard_receipts_resolves_name_to_account(resolver):
    """customer_name is resolved to an account number, which is sent
    server-side as the q clause."""
    resolver([{"AccountId": 1, "AccountNumber": "26360"}])
    client = AsyncMock()
    client.get.return_value = {"items": []}

    result = await search_standard_receipts(
        client, customer_name="ABC Application Software"
    )

    client.get.assert_called_with(
        RECEIPTS_PATH,
        params={
            "limit": OVERFETCH_LIMIT,
            "onlyData": "true",
            "q": "CustomerAccountNumber=26360",
            "orderBy": "ReceiptDate:desc",
        },
    )
    assert result.items == []


@pytest.mark.asyncio
async def test_search_standard_receipts_unknown_customer_returns_empty(resolver):
    """A name that resolves to nothing yields an empty result — and makes
    NO receipts call. Without this the tool would fall through to an
    unscoped pod-wide fetch and present someone else's receipts."""
    resolver([])
    client = AsyncMock()

    result = await search_standard_receipts(client, customer_name="Nobody Ltd")

    assert result.items == []
    assert result.total_available == 0
    client.get.assert_not_called()


@pytest.mark.asyncio
async def test_search_standard_receipts_site_only_sends_no_q(resolver):
    """customer_site alone is a valid scope. No account resolution happens,
    so no q clause is sent and the filtering is entirely client-side."""
    client = AsyncMock()
    client.get.return_value = {
        "items": [
            {"StandardReceiptId": 1, "CustomerSite": "Santa Clara"},
            {"StandardReceiptId": 2, "CustomerSite": "San Francisco"},
        ]
    }

    result = await search_standard_receipts(client, customer_site="Santa Clara")

    params = client.get.call_args.kwargs["params"]
    assert "q" not in params
    assert len(result.items) == 1
    assert result.items[0]["StandardReceiptId"] == 1


@pytest.mark.asyncio
async def test_search_standard_receipts_with_site_filter(resolver):
    """customer_site is applied client-side, on top of the server-side
    account scope."""
    resolver([{"AccountId": 1, "AccountNumber": "26360"}])
    client = AsyncMock()
    client.get.return_value = {
        "items": [
            {
                "StandardReceiptId": 1,
                "CustomerSite": "Santa Clara",
                "CustomerAccountNumber": "26360",
            },
            {
                "StandardReceiptId": 2,
                "CustomerSite": "San Francisco",
                "CustomerAccountNumber": "26360",
            },
        ]
    }

    result = await search_standard_receipts(
        client,
        customer_name="ABC Application Software",
        customer_site="Santa Clara",
    )

    items = result.items
    assert len(items) == 1
    assert items[0]["StandardReceiptId"] == 1
    assert items[0]["CustomerSite"] == "Santa Clara"


@pytest.mark.xfail(
    reason=(
        "BUG: search_standard_receipts can never report truncated=True. "
        "It computes `truncated` locally, then passes "
        "total_available=None when truncated is True — and "
        "ToolResult.build derives truncated from total_available, so a "
        "None total forces truncated=False. The detection is thrown "
        "away. A user gets a capped 25-row slice of 500+ with nothing "
        "saying so. Fix belongs in the tool or in ToolResult (which "
        "currently cannot express 'truncated, total unknown')."
    ),
    strict=True,
)
@pytest.mark.asyncio
async def test_search_standard_receipts_truncation(resolver):
    """Hitting the over-fetch cap with more matches than `limit` must
    report truncated=True."""
    resolver([{"AccountId": 1, "AccountNumber": "26360"}])
    client = AsyncMock()
    # OVERFETCH_LIMIT rows that all MATCH the site filter, so the cap is
    # hit and the 25-row limit genuinely hides matching records.
    client.get.return_value = {
        "items": [
            {"StandardReceiptId": i, "CustomerSite": "Santa Clara"}
            for i in range(OVERFETCH_LIMIT)
        ]
    }

    result = await search_standard_receipts(
        client,
        customer_name="ABC Application Software",
        customer_site="Santa Clara",
        limit=25,
    )

    assert len(result.items) == 25
    assert result.truncated is True
