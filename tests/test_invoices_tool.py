"""Integration tests for the search_invoices tool."""

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.invoices import search_invoices
from spire.mcp_server.tools.tool_result import ToolResult


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)


@pytest.mark.asyncio
async def test_search_invoices_no_filter():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_invoices(client, limit=5)
    assert isinstance(result, ToolResult)
    assert len(result.items) > 0
    first = result.items[0]
    for field in ["InvoiceId", "InvoiceNumber", "InvoiceDate", "Supplier", "SupplierNumber"]:
        assert field in first


@pytest.mark.asyncio
async def test_search_invoices_by_supplier_number():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_invoices(client, supplier_number="1252", limit=10)
    assert isinstance(result, ToolResult)
    for item in result.items:
        assert item["SupplierNumber"] == "1252"


@pytest.mark.asyncio
async def test_search_invoices_by_supplier_name():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_invoices(client, supplier_name="Lee", limit=10)
    assert isinstance(result, ToolResult)
    if result.items:
        assert any("Lee" in (item.get("Supplier") or "") for item in result.items)


@pytest.mark.asyncio
async def test_search_invoices_with_date_filter():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_invoices(
            client,
            invoice_date_after="2020-01-01",
            limit=5,
        )
    assert isinstance(result, ToolResult)
    for item in result.items:
        assert item["InvoiceDate"] >= "2020-01-01"


@pytest.mark.asyncio
async def test_search_invoices_composite_supplier_and_date():
    """Verifies the client-side filter composition works:
    Lee Supplies (1252) has a Feb 2024 invoice; combining the two filters
    must surface it.
    """
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_invoices(
            client,
            supplier_number="1252",
            invoice_date_after="2020-01-01",
            limit=10,
        )
    assert isinstance(result, ToolResult)
    assert len(result.items) >= 1
    for item in result.items:
        assert item["SupplierNumber"] == "1252"
        assert item["InvoiceDate"] >= "2020-01-01"


# ---- Truncation reporting ----


@pytest.mark.asyncio
async def test_search_invoices_reports_truncation_for_broad_date_filter():
    """A broad date filter (>= 2022-01-01) is known to match thousands.
    With default limit=25, truncated should be True and total_available
    should be a known integer larger than the items list.
    """
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_invoices(
            client,
            invoice_date_after="2022-01-01",
            limit=25,
        )
    assert isinstance(result, ToolResult)
    assert result.truncated is True
    assert result.total_available is not None
    assert result.total_available > len(result.items)
    assert result.limit_applied == 25


@pytest.mark.asyncio
async def test_search_invoices_not_truncated_when_limit_exceeds_matches():
    """When the limit is much larger than matching records, truncated
    should be False. Uses a far-future date that no invoice should
    satisfy.
    """
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_invoices(
            client,
            invoice_date_after="2099-01-01",
            limit=100,
        )
    assert isinstance(result, ToolResult)
    assert result.truncated is False
    assert len(result.items) == 0


# ---- Feature 2: invoice_date_before (upper bound) ----


@pytest.mark.asyncio
async def test_search_invoices_date_before_upper_bound():
    """invoice_date_before is exclusive: every returned invoice must be
    strictly before the bound. Uses a wide window so the pod returns rows.
    """
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_invoices(
            client,
            invoice_date_before="2024-01-01",
            limit=25,
        )
    assert isinstance(result, ToolResult)
    for item in result.items:
        assert item["InvoiceDate"] < "2024-01-01"


@pytest.mark.asyncio
async def test_search_invoices_month_range_for_supplier():
    """Closes G1: a calendar-month range for one supplier.
    Lee Supplies (1252) in a 2022 window — every row must fall inside
    [after, before) and belong to 1252.
    """
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_invoices(
            client,
            supplier_number="1252",
            invoice_date_after="2022-01-01",
            invoice_date_before="2023-01-01",
            limit=25,
        )
    assert isinstance(result, ToolResult)
    for item in result.items:
        assert item["SupplierNumber"] == "1252"
        assert "2022-01-01" <= item["InvoiceDate"] < "2023-01-01"




# ── P5: invoices by purchase order ──
#
# Invoices carry PurchaseOrderNumber on the HEADER and it filters
# server-side, so "which invoices were raised against PO X" is a single
# selective query. The value is the PO NUMBER (OrderNumber), not
# POHeaderId — consistent with invoices joining on SupplierNumber rather
# than SupplierId.
#
# Anchors: PO 162034 (Lee Supplies) has invoice 162034inv. PO 162352
# (POHeaderId 2144) is ordered but never invoiced — a useful negative case.


@pytest.mark.asyncio
async def test_search_invoices_by_purchase_order():
    """P5: invoices raised against a PO, filtered server-side on
    PurchaseOrderNumber."""
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_invoices(client, purchase_order="162034", limit=10)
    assert isinstance(result, ToolResult)
    assert len(result.items) >= 1
    for item in result.items:
        assert item["PurchaseOrderNumber"] == "162034"


@pytest.mark.asyncio
async def test_search_invoices_by_purchase_order_no_invoices():
    """A PO with no invoices returns empty — not an error."""
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_invoices(client, purchase_order="162352", limit=10)
    assert isinstance(result, ToolResult)
    assert result.items == []


@pytest.mark.asyncio
async def test_purchase_order_filter_wins_server_clause():
    """purchase_order is the most selective filter, so it takes the single
    server q= clause even when a supplier is also given. The supplier is
    then applied client-side, so results must satisfy BOTH."""
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_invoices(
            client, purchase_order="162034", supplier_name="Lee", limit=10
        )
    assert isinstance(result, ToolResult)
    for item in result.items:
        assert item["PurchaseOrderNumber"] == "162034"
        assert "Lee" in (item.get("Supplier") or "")


# ── Window 35: invoice_status filters ──
#
# unpaid / overdue / pending ride as server-side single clauses (composite
# q= is unreliable on this pod). unpaid also runs a second single-clause
# call for PaidStatus='Partially paid' and merges, so "not settled" covers
# both spellings. overdue is Unpaid-only and adds a client-side DueDate
# test. pending is ApprovalStatus='Required', the default AP reading.
# See docs/design/INVOICE_STATUS_ACCEPTANCE.md §4.


@pytest.mark.asyncio
async def test_search_invoices_unpaid_filter():
    """unpaid keeps Unpaid and Partially paid rows; every row is one of them."""
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_invoices(client, unpaid=True, limit=20)
    assert isinstance(result, ToolResult)
    for item in result.items:
        assert item["PaidStatus"] in ("Unpaid", "Partially paid")


@pytest.mark.asyncio
async def test_search_invoices_overdue_filter():
    """overdue keeps only non-Paid rows whose DueDate is strictly before today.

    Partially paid rows are outside this reading — see the tool docstring.
    Every returned row must be non-Paid AND past due.
    """
    from datetime import date as _date
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_invoices(client, overdue=True, limit=20)
    assert isinstance(result, ToolResult)
    today = _date.today().isoformat()
    for item in result.items:
        assert item["PaidStatus"] != "Paid"
        assert (item.get("DueDate") or "") < today


@pytest.mark.asyncio
async def test_search_invoices_pending_filter():
    """pending keeps ApprovalStatus=Required rows — the default reading."""
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_invoices(client, pending=True, limit=20)
    assert isinstance(result, ToolResult)
    for item in result.items:
        assert item["ApprovalStatus"] == "Required"


@pytest.mark.asyncio
async def test_search_invoices_projects_due_date():
    """DueDate is in the projection so the overdue filter has a field to read."""
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_invoices(client, supplier_number="1252", limit=5)
    assert isinstance(result, ToolResult)
    for item in result.items:
        assert "DueDate" in item


@pytest.mark.asyncio
async def test_search_invoices_unpaid_total_includes_partials():
    """The 'unpaid' total is the union of Unpaid + Partially paid.

    Two single-clause fetches merge their rows; the reported total must
    cover the union, not just the server clause. On this pod there are a
    handful of Partially paid rows (9 as of window 34), so the union
    total must exceed the PaidStatus='Unpaid' count alone. Guards the
    undercount the sweep first surfaced.
    """
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_invoices(client, unpaid=True, limit=5)
        raw_unpaid = await client.total_results(
            "/fscmRestApi/resources/11.13.18.05/invoices",
            "PaidStatus='Unpaid'",
        )
    assert isinstance(result, ToolResult)
    assert result.total_available is not None
    assert raw_unpaid is not None
    assert result.total_available > raw_unpaid, (
        f"unpaid total {result.total_available} should exceed the "
        f"Unpaid-only count {raw_unpaid} by the Partially paid count"
    )


@pytest.mark.asyncio
async def test_search_invoices_overdue_reports_unknown_total_not_wrong_number():
    """'overdue' must not report the full Unpaid count as its total.

    overdue is a strict subset of Unpaid (an extra DueDate < today
    test). Without a full scan the intersection count is unknowable, so
    the tool reports total_available=None. Guards the wrong-number
    narration the sweep surfaced.
    """
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_invoices(client, overdue=True, limit=5)
    assert isinstance(result, ToolResult)
    assert result.total_available is None
    assert result.truncated is True
