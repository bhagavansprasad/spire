"""Integration tests for the search_suppliers_by_country tool."""

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.suppliers_by_country import search_suppliers_by_country
from spire.mcp_server.tools.tool_result import ToolResult


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)


@pytest.mark.asyncio
async def test_search_suppliers_by_country_us_iso_code():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_suppliers_by_country(client, country="US", limit=10)
    assert isinstance(result, ToolResult)
    assert len(result.items) > 0
    first = result.items[0]
    for field in ["SupplierId", "Supplier", "Status", "MatchedCountry"]:
        assert field in first
    assert first["MatchedCountry"] == "US"


@pytest.mark.asyncio
async def test_search_suppliers_by_country_us_full_name():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_suppliers_by_country(
            client, country="United States", limit=10
        )
    assert isinstance(result, ToolResult)
    assert len(result.items) > 0


@pytest.mark.asyncio
async def test_search_suppliers_by_country_three_letter_unsupported():
    """'USA' (3-letter ISO) is not supported; per design, should return empty."""
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_suppliers_by_country(client, country="USA", limit=10)
    assert isinstance(result, ToolResult)
    assert result.items == []
    assert result.truncated is False


@pytest.mark.asyncio
async def test_search_suppliers_by_country_unknown_country():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_suppliers_by_country(client, country="ZZ", limit=10)
    assert isinstance(result, ToolResult)
    assert result.items == []
    assert result.truncated is False


@pytest.mark.asyncio
async def test_search_suppliers_by_country_reports_truncation_for_broad_match():
    """US is known to have more than 10 matching suppliers in the pod.
    With limit=10, truncated should be True and total_available > 10.
    """
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await search_suppliers_by_country(client, country="US", limit=10)
    assert isinstance(result, ToolResult)
    assert result.truncated is True
    # total_available may be None (overfetch capped) or an integer.
    if result.total_available is not None:
        assert result.total_available > len(result.items)
