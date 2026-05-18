"""Integration tests for spire.fusion.client.

These hit the real Fusion pod and require personas.yaml to exist
with a 'default_dev' persona. Skipped if personas.yaml is missing.
"""

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.fusion.client import FusionClient


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)


@pytest.mark.asyncio
async def test_get_suppliers_returns_records():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        data = await client.get(
            "/fscmRestApi/resources/11.13.18.05/suppliers",
            params={"limit": 5},
        )
    assert "items" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) == 5
    assert "SupplierId" in data["items"][0]


@pytest.mark.asyncio
async def test_unsupported_auth_type_raises():
    persona = load_persona("default_dev")
    persona.fusion.auth_type = "oauth2"
    with pytest.raises(ValueError, match="Unsupported auth_type"):
        FusionClient(persona)
