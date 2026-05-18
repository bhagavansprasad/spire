"""Integration tests for the get_buyer tool."""

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.buyer import get_buyer


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)


# Known buyer on the demo pod — Calvin Roth, BuyerId from the PO sample
KNOWN_BUYER_ID = 300000047340498


@pytest.mark.asyncio
async def test_get_buyer_returns_known_buyer():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        buyer = await get_buyer(client, buyer_id=KNOWN_BUYER_ID)
    assert buyer is not None
    assert buyer["PersonId"] == KNOWN_BUYER_ID
    assert buyer["DisplayName"] == "Calvin Roth"
    assert buyer["WorkEmail"] is not None
    assert buyer["Username"] is not None


@pytest.mark.asyncio
async def test_get_buyer_returns_none_for_unknown_id():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        buyer = await get_buyer(client, buyer_id=999999999999)
    assert buyer is None
