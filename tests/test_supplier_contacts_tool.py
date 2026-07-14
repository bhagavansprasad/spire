"""Integration tests for the supplier contacts tool
(get_supplier_contacts).

Hits the live pod, mirroring the other supplier-child tool tests, and skips
when personas.yaml is absent. EIP Inc (SupplierId 300000047507499,
SupplierNumber 1262) has 10 contacts on the demo pod, the first of which
(Kim, John) is the administrative contact.

An unknown SupplierId 404s on the child path; the tool's guard maps that to
an empty ToolResult, so the unknown-id case asserts empty items.
"""

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.supplier_contacts import get_supplier_contacts


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)


# Known supplier on the demo pod: EIP Inc, 10 contacts.
KNOWN_SUPPLIER_ID = 300000047507499


@pytest.mark.asyncio
async def test_get_supplier_contacts_returns_contacts():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await get_supplier_contacts(
            client, supplier_id=KNOWN_SUPPLIER_ID
        )
    assert len(result.items) == 10
    names = {c["ContactName"] for c in result.items}
    assert "Kim, John" in names


@pytest.mark.asyncio
async def test_supplier_contacts_marks_administrative_contact():
    # Exactly one contact should be flagged as the administrative
    # (primary) contact — Kim, John on this supplier.
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await get_supplier_contacts(
            client, supplier_id=KNOWN_SUPPLIER_ID
        )
    admins = [
        c for c in result.items if c["AdministrativeContactFlag"] is True
    ]
    assert len(admins) == 1
    assert admins[0]["ContactName"] == "Kim, John"


@pytest.mark.asyncio
async def test_get_supplier_contacts_empty_for_unknown_id():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await get_supplier_contacts(
            client, supplier_id=999999999
        )
    # An unknown SupplierId 404s on the child path; the tool's guard maps
    # that to an empty ToolResult rather than raising.
    assert result.items == []
