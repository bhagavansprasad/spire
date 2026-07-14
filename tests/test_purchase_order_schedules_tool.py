"""Integration tests for the PO schedules tool
(get_purchase_order_schedules).

Hits the live pod, mirroring test_purchase_order_detail_tool.py, and skips
when personas.yaml is absent. PO 2144 (OrderNumber 162352, EIP Inc) has two
schedules on the demo pod.

Unlike the single-PO header path (which 404s for an unknown id), the flat
purchaseOrderSchedules collection returns an empty set for an unknown
POHeaderId — so the unknown-id case asserts empty items, not a raise.
"""

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.purchase_order_schedules import (
    get_purchase_order_schedules,
)


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)


# Known PO on the demo pod: OrderNumber 162352, EIP Inc, two schedules.
KNOWN_PO_HEADER_ID = 2144


@pytest.mark.asyncio
async def test_get_purchase_order_schedules_returns_schedules():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await get_purchase_order_schedules(
            client, po_header_id=KNOWN_PO_HEADER_ID
        )
    assert len(result.items) == 2
    first = result.items[0]
    assert first["POHeaderId"] == KNOWN_PO_HEADER_ID
    # Flat-endpoint field names (differ from the nested schedules view).
    assert first["ShipToLocation"] == "Seattle"
    assert first["ScheduleStatus"] == "Closed"


@pytest.mark.asyncio
async def test_schedule_row_carries_ids_for_distributions():
    # The distributions phase (no flat endpoint) must iterate the nested
    # path, which needs POHeaderId, POLineId and LineLocationId. Confirm the
    # schedule row carries all three so that iteration is possible.
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await get_purchase_order_schedules(
            client, po_header_id=KNOWN_PO_HEADER_ID
        )
    first = result.items[0]
    assert first["POHeaderId"] is not None
    assert first["POLineId"] is not None
    assert first["LineLocationId"] is not None


@pytest.mark.asyncio
async def test_get_purchase_order_schedules_empty_for_unknown_id():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await get_purchase_order_schedules(
            client, po_header_id=999999999
        )
    # The flat collection returns an empty set (not 404) for an unknown
    # POHeaderId, so the tool yields empty items rather than raising.
    assert result.items == []
