"""SP-005 — a child collection's page size must never be stated as its total.

The defect: p13 answered "The invoice contains 50 line items" for an invoice
with 184. `total_available=len(projected)` made the capped page look
complete, `truncated` therefore computed False, and no disclosure was
emitted. The same three lines were copied into four sibling child tools.

Measured on dev49 (2026-11-28), invoice 1601397:

    limit=50   count=50  hasMore=True   totalResults=184   items=50
    limit=100  count=58  hasMore=False  totalResults=58    items=58

So `count` is min(total, limit) and carries no information the caller cannot
already see, while `totalResults` is the real total. The fix asks for it and
falls back to `hasMore` (total unknown, but not complete) when the pod omits
it.

These tests are the only proof for the PO and AR halves: `/purchaseOrders`
returns 0 rows on dev49 (SP-003) and the AR customer-account endpoint 403s
(SP-004), so those tools cannot be exercised live. The AP half is verified
against the pod separately.
"""

from __future__ import annotations

import httpx
import pytest

from spire.mcp_server.tools.tool_result import ToolResult, child_page_count


class _FakeChild:
    """A child collection that reports a page, not a total.

    Mirrors the pod: `count` is the page size, `hasMore` says whether more
    exist, and `totalResults` is present only when asked for — which is
    exactly the trap the old code fell into.
    """

    def __init__(self, items, total=None, total_results=True):
        self._items = items
        self._total = total
        self._total_results = total_results
        self.calls: list[tuple[str, dict]] = []

    async def get(self, path, params=None):
        params = params or {}
        self.calls.append((path, params))
        page = self._items
        body = {
            "items": page,
            "count": len(page),
            "hasMore": self._total is not None and self._total > len(page),
        }
        if self._total_results and self._total is not None:
            body["totalResults"] = self._total
        return body


def _rows(n: int) -> list[dict]:
    return [{"LineNumber": i + 1} for i in range(n)]


# ── the shared helper ─────────────────────────────────────────────────


def test_total_results_is_the_total():
    total, capped = child_page_count(
        {"items": [], "count": 50, "hasMore": True, "totalResults": 184},
        _rows(50),
    )
    assert total == 184
    assert capped is False


def test_has_more_without_a_total_is_capped_not_zero():
    """The case the counts cannot express: more exist, count unknown.

    Reporting total=None must still suppress "this is everything", which is
    why `capped` exists.
    """
    total, capped = child_page_count({"hasMore": True}, _rows(50))
    assert total is None
    assert capped is True


def test_a_complete_page_reports_its_own_size():
    total, capped = child_page_count({"hasMore": False}, _rows(3))
    assert total == 3
    assert capped is False


# ── ToolResult.build ──────────────────────────────────────────────────


def test_capped_without_a_total_still_truncates():
    result = ToolResult.build(
        items=_rows(50),
        limit_applied=50,
        total_available=None,
        capped=True,
    )
    assert result.truncated is True
    assert result.total_available is None


def test_unknown_total_and_not_capped_is_not_truncated():
    """The old default must not change: no total, nothing claimed."""
    result = ToolResult.build(
        items=_rows(3), limit_applied=3, total_available=None
    )
    assert result.truncated is False


def test_known_total_beyond_the_page_truncates():
    result = ToolResult.build(
        items=_rows(50), limit_applied=50, total_available=184
    )
    assert result.truncated is True


# ── every child tool, so a sixth copy of the bug fails here ───────────

_TOOLS = [
    (
        "get_invoice_lines",
        "spire.mcp_server.tools.invoice_lines",
        {"invoice_id": 1601397},
    ),
    (
        "get_purchase_order_lines",
        "spire.mcp_server.tools.purchase_order_lines",
        {"po_header_id": 2144},
    ),
    (
        "get_receivables_invoice_lines",
        "spire.mcp_server.tools.receivables_invoice_lines",
        {"customer_transaction_id": 1002},
    ),
    (
        "get_receivables_invoice_tax_lines",
        "spire.mcp_server.tools.receivables_invoice_tax_lines",
        {"customer_transaction_id": 1002, "line_id": 74},
    ),
    (
        "get_receivables_invoice_transaction_dff",
        "spire.mcp_server.tools.receivables_invoice_transaction_dff",
        {"customer_transaction_id": 1002},
    ),
]


@pytest.mark.parametrize("name,module,kwargs", _TOOLS)
@pytest.mark.asyncio
async def test_capped_child_never_claims_a_total(name, module, kwargs):
    """184 lines behind a 50-row page must not read as 50."""
    import importlib

    tool = getattr(importlib.import_module(module), name)
    client = _FakeChild(_rows(50), total=184)

    result = await tool(client, limit=50, **kwargs)

    assert result.total_available == 184, (
        f"{name} reported {result.total_available} for a 184-row child — "
        "the page size is being stated as the total"
    )
    assert result.truncated is True
    assert client.calls[0][1]["totalResults"] == "true", (
        f"{name} does not ask for totalResults, so it cannot know the total"
    )


@pytest.mark.parametrize("name,module,kwargs", _TOOLS)
@pytest.mark.asyncio
async def test_complete_child_is_not_flagged_as_truncated(name, module, kwargs):
    import importlib

    tool = getattr(importlib.import_module(module), name)
    client = _FakeChild(_rows(4), total=4)

    result = await tool(client, limit=200, **kwargs)

    assert result.total_available == 4
    assert result.truncated is False


@pytest.mark.parametrize("name,module,kwargs", _TOOLS)
@pytest.mark.asyncio
async def test_missing_total_results_falls_back_to_capped(name, module, kwargs):
    """A pod that omits totalResults must degrade, not assert."""
    import importlib

    tool = getattr(importlib.import_module(module), name)
    client = _FakeChild(_rows(50), total=184, total_results=False)

    result = await tool(client, limit=50, **kwargs)

    assert result.total_available is None
    assert result.truncated is True


# ── the rendering half: a sample must not read as the answer ──────────


def test_sample_without_a_total_says_so():
    from spire.synthesizer.local_summary import local_list_summary

    lines = local_list_summary(
        _rows(50),
        "line items",
        total_available=None,
        truncated=True,
    )
    joined = " ".join(lines).lower()
    assert "sample" in joined
    assert "not known" in joined


def test_known_total_renders_showing_n_of_m():
    from spire.synthesizer.local_summary import local_list_summary

    lines = local_list_summary(
        _rows(50),
        "line items",
        total_available=184,
        truncated=True,
    )
    assert any("50 of 184" in line for line in lines)
