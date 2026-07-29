"""Truncation reporting across the AR list tools.

THE BUG THESE PIN
All three tools set total_available to the number of rows RETURNED:

    total_available=len(projected)

ToolResult.build then computes `total_available > len(items)` — which is
`25 > 25`, false. Every capped result claimed nothing was truncated. The
synthesizer faithfully narrated that, so "List recent credit memos"
showed 25 rows of an unknown larger set with nothing saying more
existed. Two of the three even documented it in their own docstrings
("the pod's own totalResults is not requested") without fixing it.

The fix follows account_receipt_applications.py, which already did this
correctly: request totalResults, read it, fall back to the row count
when the endpoint omits it.

These are the first tests for account_credit_memos and account_receipts.
"""

import pytest
from unittest.mock import AsyncMock

from spire.mcp_server.tools.account_credit_memos import get_account_credit_memos
from spire.mcp_server.tools.account_receipts import get_account_receipts
from spire.mcp_server.tools.receivables_credit_memos import (
    list_receivables_credit_memos,
)


def _rows(n, **extra):
    return [{"CustomerTransactionId": i, **extra} for i in range(n)]


# ─────────────────────────────────────────────────────────────────────
# receivables_credit_memos — the tool behind "List recent credit memos"
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_credit_memos_report_pod_total_not_row_count():
    """25 rows out of 1,343 must report 1,343 — the number that makes the
    result honestly describable as a slice."""
    client = AsyncMock()
    client.get.return_value = {"items": _rows(25), "totalResults": 1343}

    result = await list_receivables_credit_memos(client, limit=25)

    assert len(result.items) == 25
    assert result.total_available == 1343
    assert result.truncated is True


@pytest.mark.asyncio
async def test_credit_memos_request_total_results():
    """totalResults must be asked for. Without the param the pod does not
    return the count, and every fix downstream is moot."""
    client = AsyncMock()
    client.get.return_value = {"items": [], "totalResults": 0}

    await list_receivables_credit_memos(client, limit=25)

    params = client.get.call_args.kwargs["params"]
    assert params["totalResults"] == "true"


@pytest.mark.asyncio
async def test_credit_memos_complete_result_is_not_truncated():
    """A result that IS everything must not claim truncation. The fix
    must not trade one wrong answer for the opposite one."""
    client = AsyncMock()
    client.get.return_value = {"items": _rows(7), "totalResults": 7}

    result = await list_receivables_credit_memos(client, limit=25)

    assert result.total_available == 7
    assert result.truncated is False


@pytest.mark.asyncio
async def test_credit_memos_fall_back_when_pod_omits_total():
    """No totalResults in the response: fall back to the row count. That
    understates rather than inventing a number — the honest floor."""
    client = AsyncMock()
    client.get.return_value = {"items": _rows(25)}

    result = await list_receivables_credit_memos(client, limit=25)

    assert result.total_available == 25
    assert result.truncated is False


@pytest.mark.asyncio
async def test_credit_memos_ignore_non_integer_total():
    """Some endpoints return totalResults as a string or null. Anything
    that is not an int is not a count."""
    client = AsyncMock()
    client.get.return_value = {"items": _rows(3), "totalResults": "many"}

    result = await list_receivables_credit_memos(client, limit=25)

    assert result.total_available == 3


# ─────────────────────────────────────────────────────────────────────
# account_credit_memos — per-account child
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_account_credit_memos_report_pod_total():
    client = AsyncMock()
    client.get.return_value = {"items": _rows(10), "totalResults": 214}

    result = await get_account_credit_memos(client, account_id=1, limit=10)

    assert result.total_available == 214
    assert result.truncated is True


@pytest.mark.asyncio
async def test_account_credit_memos_request_total_results():
    client = AsyncMock()
    client.get.return_value = {"items": [], "totalResults": 0}

    await get_account_credit_memos(client, account_id=1, limit=10)

    params = client.get.call_args.kwargs["params"]
    assert params["totalResults"] == "true"


@pytest.mark.asyncio
async def test_account_credit_memos_fall_back_when_pod_omits_total():
    client = AsyncMock()
    client.get.return_value = {"items": _rows(10)}

    result = await get_account_credit_memos(client, account_id=1, limit=10)

    assert result.total_available == 10
    assert result.truncated is False


# ─────────────────────────────────────────────────────────────────────
# account_receipts — per-account child. The docstring cites an account
# with 1,386 receipts against a 10-row display cap, so this tool was
# understating by two orders of magnitude.
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_account_receipts_report_pod_total():
    client = AsyncMock()
    client.get.return_value = {"items": _rows(10), "totalResults": 1386}

    result = await get_account_receipts(client, account_id=1, limit=10)

    assert result.total_available == 1386
    assert result.truncated is True


@pytest.mark.asyncio
async def test_account_receipts_request_total_results():
    client = AsyncMock()
    client.get.return_value = {"items": [], "totalResults": 0}

    await get_account_receipts(client, account_id=1, limit=10)

    params = client.get.call_args.kwargs["params"]
    assert params["totalResults"] == "true"


@pytest.mark.asyncio
async def test_account_receipts_fall_back_when_pod_omits_total():
    client = AsyncMock()
    client.get.return_value = {"items": _rows(10)}

    result = await get_account_receipts(client, account_id=1, limit=10)

    assert result.total_available == 10
    assert result.truncated is False
