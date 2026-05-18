"""Integration tests for the search_invoices tool."""

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.invoices import search_invoices


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)


@pytest.mark.asyncio
async def test_search_invoices_no_filter():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        items = await search_invoices(client, limit=5)
    assert isinstance(items, list)
    assert len(items) > 0
    first = items[0]
    for field in ["InvoiceId", "InvoiceNumber", "InvoiceDate", "Supplier", "SupplierNumber"]:
        assert field in first


@pytest.mark.asyncio
async def test_search_invoices_by_supplier_number():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        items = await search_invoices(client, supplier_number="1252", limit=10)
    assert isinstance(items, list)
    for item in items:
        assert item["SupplierNumber"] == "1252"


@pytest.mark.asyncio
async def test_search_invoices_by_supplier_name():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        items = await search_invoices(client, supplier_name="Lee", limit=10)
    assert isinstance(items, list)
    if items:
        assert any("Lee" in (item.get("Supplier") or "") for item in items)


@pytest.mark.asyncio
async def test_search_invoices_with_date_filter():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        items = await search_invoices(
            client,
            invoice_date_after="2020-01-01",
            limit=5,
        )
    assert isinstance(items, list)
    for item in items:
        assert item["InvoiceDate"] >= "2020-01-01"


@pytest.mark.asyncio
async def test_search_invoices_composite_supplier_and_date():
    """Verifies the client-side filter composition works:
    Lee Supplies (1252) has a Feb 2024 invoice; combining the two filters
    must surface it.
    """
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        items = await search_invoices(
            client,
            supplier_number="1252",
            invoice_date_after="2020-01-01",
            limit=10,
        )
    assert isinstance(items, list)
    assert len(items) >= 1
    for item in items:
        assert item["SupplierNumber"] == "1252"
        assert item["InvoiceDate"] >= "2020-01-01"
