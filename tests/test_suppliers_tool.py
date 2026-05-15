"""Integration tests for the search_suppliers tool.

Calls the tool function directly with a real FusionClient. Skips if
personas.yaml is missing.
"""

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.suppliers import search_suppliers


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)


@pytest.mark.asyncio
async def test_search_suppliers_default():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        items = await search_suppliers(client, limit=5)
    assert isinstance(items, list)
    assert len(items) == 5
    assert "SupplierId" in items[0]
    assert "Supplier" in items[0]


@pytest.mark.asyncio
async def test_search_suppliers_name_filter():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        items = await search_suppliers(client, supplier_name_contains="Lee", limit=5)
    assert isinstance(items, list)
    # At least one match expected — "Lee Supplies" is in the pod
    assert len(items) >= 1
    assert any("Lee" in (item.get("Supplier") or "") for item in items)
