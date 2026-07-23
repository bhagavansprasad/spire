"""Test for standard_receipts tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from spire.mcp_server.tools.standard_receipts import search_standard_receipts


@pytest.mark.asyncio
async def test_search_standard_receipts_no_filters_raises():
    """Calling with neither account_number nor customer_site raises."""
    client = AsyncMock()
    with pytest.raises(ValueError, match="At least one of account_number or customer_site"):
        await search_standard_receipts(client)


@pytest.mark.asyncio
async def test_search_standard_receipts_with_account_number():
    """account_number is sent server-side."""
    client = AsyncMock()
    client.get.return_value = {"items": []}
    result = await search_standard_receipts(client, account_number="26360")
    client.get.assert_called_with(
        "/fscmRestApi/resources/11.13.18.05/standardReceipts",
        params={
            "limit": 500,
            "onlyData": "true",
            "q": "CustomerAccountNumber=26360",
            "orderBy": "ReceiptDate:desc",
        },
    )
    assert result.items == []


@pytest.mark.asyncio
async def test_search_standard_receipts_with_site_filter():
    """customer_site is applied client-side."""
    client = AsyncMock()
    client.get.return_value = {
        "items": [
            {"StandardReceiptId": 1, "CustomerSite": "Santa Clara", "CustomerAccountNumber": "26360"},
            {"StandardReceiptId": 2, "CustomerSite": "San Francisco", "CustomerAccountNumber": "26360"},
        ]
    }
    result = await search_standard_receipts(client, account_number="26360", customer_site="Santa Clara")
    items = result.items
    assert len(items) == 1
    assert items[0]["StandardReceiptId"] == 1
    assert items[0]["CustomerSite"] == "Santa Clara"


@pytest.mark.asyncio
async def test_search_standard_receipts_truncation():
    """If over-fetch cap is reached and not all items filtered, truncated=True."""
    client = AsyncMock()
    # Simulate OVERFETCH_LIMIT rows (500) – we just need to reach the cap
    # Return 500 items with mismatched site so they are all filtered out,
    # so len(capped) < len(filtered) and len(items) >= OVERFETCH_LIMIT.
    items = []
    for i in range(500):
        items.append({"StandardReceiptId": i, "CustomerSite": "Other"})
    client.get.return_value = {"items": items}
    result = await search_standard_receipts(client, account_number="26360", customer_site="Santa Clara")
    # truncated should be True because we fetched 500 and the result is < 500
    assert result.truncated is True