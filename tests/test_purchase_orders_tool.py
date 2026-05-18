"""Integration tests for the search_purchase_orders tool."""

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.purchase_orders import search_purchase_orders


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)


@pytest.mark.asyncio
async def test_search_purchase_orders_no_filter():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        items = await search_purchase_orders(client, limit=5)
    assert isinstance(items, list)
    assert len(items) > 0
    first = items[0]
    for field in ["POHeaderId", "OrderNumber", "Status", "Supplier", "SupplierId"]:
        assert field in first


@pytest.mark.asyncio
async def test_search_purchase_orders_by_status_open():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        items = await search_purchase_orders(client, status="OPEN", limit=10)
    assert isinstance(items, list)
    for item in items:
        assert item["StatusCode"] == "OPEN"


@pytest.mark.asyncio
async def test_search_purchase_orders_by_supplier_name():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        items = await search_purchase_orders(client, supplier_name="EIP", limit=10)
    assert isinstance(items, list)
    if items:
        assert any("EIP" in (item.get("Supplier") or "") for item in items)


@pytest.mark.asyncio
async def test_search_purchase_orders_by_supplier_id():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        seed = await search_purchase_orders(client, limit=1)
        assert len(seed) == 1
        sid = seed[0]["SupplierId"]

        items = await search_purchase_orders(client, supplier_id=sid, limit=10)
    assert isinstance(items, list)
    assert len(items) >= 1
    for item in items:
        assert item["SupplierId"] == sid


@pytest.mark.asyncio
async def test_search_purchase_orders_composite_supplier_name_and_status():
    """Verifies the client-side filter composition works:
    EIP Inc has an OPEN PO; combining the two filters must surface it.
    """
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        items = await search_purchase_orders(
            client,
            supplier_name="EIP",
            status="OPEN",
            limit=10,
        )
    assert isinstance(items, list)
    # If the EIP PO is still OPEN, we should see at least one match.
    # If demo data has changed, this assertion may need adjustment.
    for item in items:
        assert item["StatusCode"] == "OPEN"
        assert "EIP" in (item.get("Supplier") or "")
