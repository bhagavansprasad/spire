"""Integration tests for the search_suppliers tool.

Calls the tool function directly with a real FusionClient. Skips if
personas.yaml is missing.

Updated for feature 3+4: search_suppliers now returns a ToolResult and
supports a client-side `status` filter.
"""

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.suppliers import search_suppliers
from spire.mcp_server.tools.tool_result import ToolResult


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)


@pytest.mark.asyncio
async def test_search_suppliers_default_returns_toolresult():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_suppliers(client, limit=5)
    assert isinstance(result, ToolResult)
    assert len(result.items) == 5
    first = result.items[0]
    for field in ["SupplierId", "Supplier", "Status"]:
        assert field in first


@pytest.mark.asyncio
async def test_search_suppliers_name_filter():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_suppliers(
            client, supplier_name_contains="Lee", limit=5
        )
    assert isinstance(result, ToolResult)
    # At least one match expected — "Lee Supplies" is in the pod
    assert len(result.items) >= 1
    assert any("Lee" in (item.get("Supplier") or "") for item in result.items)


@pytest.mark.asyncio
async def test_search_suppliers_status_filter():
    """Every returned supplier must carry the requested status.

    Uses whatever status the first supplier reports, so the test is
    robust to the pod's actual status vocabulary.
    """
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        seed = await search_suppliers(client, limit=1)
        assert len(seed.items) == 1
        some_status = seed.items[0]["Status"]

        result = await search_suppliers(client, status=some_status, limit=10)
    assert isinstance(result, ToolResult)
    assert len(result.items) >= 1
    for item in result.items:
        assert item["Status"] == some_status


@pytest.mark.asyncio
async def test_search_suppliers_status_filter_no_match():
    """A status no supplier has should return empty, not truncated."""
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_suppliers(client, status="__NOPE__", limit=10)
    assert isinstance(result, ToolResult)
    assert result.items == []
    assert result.truncated is False
    assert result.total_available == 0
