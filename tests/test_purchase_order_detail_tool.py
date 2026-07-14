"""Integration tests for the PO detail tools (get_purchase_order_by_id
and get_purchase_order_lines).

These hit the live pod, mirroring test_buyer_tool.py, and skip when
personas.yaml is absent. PO 2144 (OrderNumber 162352, EIP Inc) is a
stable closed PO on the demo pod with two lines.
"""

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.purchase_order_by_id import (
    get_purchase_order_by_id,
)
from spire.mcp_server.tools.purchase_order_lines import (
    get_purchase_order_lines,
)


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)


# Known PO on the demo pod: OrderNumber 162352, EIP Inc, two lines.
KNOWN_PO_HEADER_ID = 2144


@pytest.mark.asyncio
async def test_get_purchase_order_by_id_returns_known_po():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        po = await get_purchase_order_by_id(
            client, po_header_id=KNOWN_PO_HEADER_ID
        )
    assert po is not None
    assert po["POHeaderId"] == KNOWN_PO_HEADER_ID
    assert po["OrderNumber"] == "162352"
    assert po["Supplier"] == "EIP Inc"
    # Both money fields are projected: Ordered (pre-tax) and Total (incl).
    assert po["Ordered"] is not None
    assert po["Total"] is not None


@pytest.mark.asyncio
async def test_get_purchase_order_by_id_returns_none_for_unknown_id():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        po = await get_purchase_order_by_id(
            client, po_header_id=999999999
        )
    # The single-record path 404s for an unknown id; the tool maps that
    # to None rather than raising.
    assert po is None


@pytest.mark.asyncio
async def test_get_purchase_order_lines_returns_lines():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await get_purchase_order_lines(
            client, po_header_id=KNOWN_PO_HEADER_ID
        )
    assert len(result.items) == 2
    first = result.items[0]
    assert first["POHeaderId"] == KNOWN_PO_HEADER_ID
    assert first["LineNumber"] == 1
    # The line body carries the parent OrderNumber (unlike supplier
    # children, which omit the parent id).
    assert first["OrderNumber"] == "162352"


@pytest.mark.asyncio
async def test_get_purchase_order_lines_empty_for_unknown_id():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await get_purchase_order_lines(
            client, po_header_id=999999999
        )
    # An unknown parent yields no lines; the child path returns an empty
    # collection rather than raising.
    assert result.items == []
