"""Integration tests for the search_invoices tool.

Calls the tool function directly with a real FusionClient. Skips if
personas.yaml is missing.
"""

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
    # Projected field shape
    for field in ["InvoiceId", "InvoiceNumber", "InvoiceDate", "Supplier", "SupplierNumber"]:
        assert field in first


@pytest.mark.asyncio
async def test_search_invoices_by_supplier_number():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        items = await search_invoices(client, supplier_number="1252", limit=10)
    assert isinstance(items, list)
    # Every returned invoice should be for SupplierNumber 1252 (Lee Supplies)
    for item in items:
        assert item["SupplierNumber"] == "1252"


@pytest.mark.asyncio
async def test_search_invoices_by_supplier_name():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        items = await search_invoices(client, supplier_name="Lee", limit=10)
    assert isinstance(items, list)
    # Loose assertion — at least one result if Lee has invoices
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
    # If results came back, dates should all be on or after 2020-01-01
    for item in items:
        assert item["InvoiceDate"] >= "2020-01-01"
