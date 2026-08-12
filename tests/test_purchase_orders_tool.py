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
        # Seed off a PO that HAS a supplier. The unfiltered list is ordered
        # by OrderNumber (REC-2), whose first row is the pod's Incomplete
        # OrderNumber "1" with SupplierId=None — using that as the seed would
        # filter on a null id. Over-fetch a small page and pick the first row
        # with a non-null SupplierId, so the seed is robust to ordering and to
        # supplierless POs existing at all.
        seed = await search_purchase_orders(client, limit=25)
        sid = next(
            (row["SupplierId"] for row in seed.items if row.get("SupplierId")),
            None,
        )
        assert sid is not None, "no PO with a supplier in the first page"

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
