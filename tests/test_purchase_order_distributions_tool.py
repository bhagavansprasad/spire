"""Integration tests for the PO distributions tool
(get_purchase_order_distributions).

Hits the live pod and skips when personas.yaml is absent.

NOTE ON ANCHORS: these ids are pod-specific. They currently point at the
eqjz pod (PO US165380, Lee Supplies). Distributions have no flat endpoint,
so the tool needs all three ids of the nested path — POHeaderId, POLineId
and LineLocationId — which in the pipeline come from the parent POSchedule
row. Pod-portability of live-pod anchors is a known open item across the
test suite.
"""

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.purchase_order_distributions import (
    get_purchase_order_distributions,
)


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)


# Known chain on the pod: PO 162352 (POHeaderId 2144, EIP Inc), line 1,
# schedule 1 — the same PO the other PO tests anchor on. It carries one
# distribution (DistributionNumber 1, POChargeAccount 101.10.63120...).
KNOWN_PO_HEADER_ID = 2144
KNOWN_PO_LINE_ID = 19782
KNOWN_LINE_LOCATION_ID = 18954


@pytest.mark.asyncio
async def test_get_distributions_returns_distributions():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await get_purchase_order_distributions(
            client,
            po_header_id=KNOWN_PO_HEADER_ID,
            po_line_id=KNOWN_PO_LINE_ID,
            line_location_id=KNOWN_LINE_LOCATION_ID,
        )
    assert len(result.items) >= 1
    first = result.items[0]
    # The distribution body carries the parent ids.
    assert first["POHeaderId"] == KNOWN_PO_HEADER_ID
    assert first["POLineId"] == KNOWN_PO_LINE_ID
    # The accounts are the point of the resource.
    assert first["POChargeAccount"] is not None


@pytest.mark.asyncio
async def test_distribution_carries_accounts_and_percentage():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await get_purchase_order_distributions(
            client,
            po_header_id=KNOWN_PO_HEADER_ID,
            po_line_id=KNOWN_PO_LINE_ID,
            line_location_id=KNOWN_LINE_LOCATION_ID,
        )
    first = result.items[0]
    for field in (
        "POChargeAccount",
        "POAccrualAccount",
        "DistributionNumber",
        "Percentage",
        "Status",
    ):
        assert field in first


@pytest.mark.asyncio
async def test_get_distributions_empty_for_unknown_chain():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await get_purchase_order_distributions(
            client,
            po_header_id=KNOWN_PO_HEADER_ID,
            po_line_id=KNOWN_PO_LINE_ID,
            line_location_id=999999999,
        )
    # An unknown id chain 404s on the nested path; the tool's guard maps
    # that to an empty ToolResult rather than raising.
    assert result.items == []


