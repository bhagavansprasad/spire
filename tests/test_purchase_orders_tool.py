"""Integration tests for the search_purchase_orders tool.

Updated for feature 4: search_purchase_orders now returns a ToolResult.
"""

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.purchase_orders import search_purchase_orders
from spire.mcp_server.tools.tool_result import ToolResult


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)


@pytest.mark.asyncio
async def test_search_purchase_orders_no_filter():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_purchase_orders(client, limit=5)
    assert isinstance(result, ToolResult)
    assert len(result.items) > 0
    first = result.items[0]
    for field in ["POHeaderId", "OrderNumber", "Status", "Supplier", "SupplierId"]:
        assert field in first


@pytest.mark.asyncio
async def test_search_purchase_orders_by_status_open():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_purchase_orders(client, status="OPEN", limit=10)
    assert isinstance(result, ToolResult)
    for item in result.items:
        assert item["StatusCode"] == "OPEN"


@pytest.mark.asyncio
async def test_search_purchase_orders_by_supplier_name():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_purchase_orders(client, supplier_name="EIP", limit=10)
    assert isinstance(result, ToolResult)
    if result.items:
        assert any("EIP" in (item.get("Supplier") or "") for item in result.items)


@pytest.mark.asyncio
async def test_search_purchase_orders_by_supplier_id():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        seed = await search_purchase_orders(client, limit=1)
        assert len(seed.items) == 1
        sid = seed.items[0]["SupplierId"]

        result = await search_purchase_orders(client, supplier_id=sid, limit=10)
    assert isinstance(result, ToolResult)
    assert len(result.items) >= 1
    for item in result.items:
        assert item["SupplierId"] == sid


@pytest.mark.asyncio
async def test_search_purchase_orders_composite_supplier_name_and_status():
    """Verifies client-side filter composition: EIP Inc has an OPEN PO."""
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_purchase_orders(
            client,
            supplier_name="EIP",
            status="OPEN",
            limit=10,
        )
    assert isinstance(result, ToolResult)
    for item in result.items:
        assert item["StatusCode"] == "OPEN"
        assert "EIP" in (item.get("Supplier") or "")
