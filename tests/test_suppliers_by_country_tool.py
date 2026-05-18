"""Integration tests for the search_suppliers_by_country tool."""

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.suppliers_by_country import search_suppliers_by_country


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)


@pytest.mark.asyncio
async def test_search_suppliers_by_country_us_iso_code():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        items = await search_suppliers_by_country(client, country="US", limit=10)
    assert isinstance(items, list)
    assert len(items) > 0
    first = items[0]
    for field in ["SupplierId", "Supplier", "Status", "MatchedCountry"]:
        assert field in first
    assert first["MatchedCountry"] == "US"


@pytest.mark.asyncio
async def test_search_suppliers_by_country_us_full_name():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        items = await search_suppliers_by_country(
            client, country="United States", limit=10
        )
    assert isinstance(items, list)
    assert len(items) > 0


@pytest.mark.asyncio
async def test_search_suppliers_by_country_three_letter_unsupported():
    """'USA' (3-letter ISO) is not supported; per design, should return empty."""
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        items = await search_suppliers_by_country(client, country="USA", limit=10)
    assert items == []


@pytest.mark.asyncio
async def test_search_suppliers_by_country_unknown_country():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        items = await search_suppliers_by_country(client, country="ZZ", limit=10)
    assert items == []
