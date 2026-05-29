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