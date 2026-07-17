"""Purchase-order schedules tool: the shipment schedules of one PO.

Unlike PO lines (a child collection under /purchaseOrders/{id}), schedules
are reachable as a FLAT top-level collection on this pod:
/purchaseOrderSchedules?q=POHeaderId=<id>. That makes this a clean one-hop
fetch keyed on a single id — the same shape as the P2 lines tool.

The flat schedule row carries the full parent id chain: POHeaderId,
POLineId, LineLocationId, plus OrderNumber, LineNumber and ScheduleNumber.
POLineId and LineLocationId are included in the projection deliberately:
a later phase (PO distributions) has no flat endpoint and must iterate the
nested distributions path, which needs all three ids from each schedule row.

Flat-endpoint field names differ from the nested schedules view:
ScheduleStatus (not Status), Amount (not Ordered), ShipToLocation (not
ShipToLocationCode). We key off the flat names here.

Note the pod's single-clause q= rule: q=POHeaderId=<id> is one clause and
works server-side. Any further filtering would be client-side.

The projection also carries the received/billed figures
(ReceivedQuantity, BilledQuantity, ShippedQuantity, AcceptedQuantity,
ReceivedAmount, BilledAmount) alongside the ordered Quantity/Amount — this
row is Fusion's record of received-vs-ordered for the PO.

Returns a ToolResult (like the other child/collection tools) so callers
can tell a complete result from a capped subset.
"""

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


PO_SCHEDULES_PATH = (
    "/fscmRestApi/resources/11.13.18.05/purchaseOrderSchedules"
)

_PROJECTED_FIELDS = [
    "LineLocationId",
    "POHeaderId",
    "POLineId",
    "OrderNumber",
    "LineNumber",
    "ScheduleNumber",
    "ShipToLocation",
    "RequestedDeliveryDate",
    "Quantity",
    "UOM",
    "Amount",
    "ScheduleStatus",
    # P5: received-vs-ordered. The schedule row is where Fusion records
    # what was actually received/billed against the ordered Quantity and
    # Amount, so "how much of PO X was received" is answered here rather
    # than from a receipts resource (receivingTransactions is 403 for us;
    # receivingReceipts needs a receipt number; receivingReceiptRequests
    # is a staging interface with no PO reference).
    "ReceivedQuantity",
    "BilledQuantity",
    "ShippedQuantity",
    "AcceptedQuantity",
    "ReceivedAmount",
    "BilledAmount",
]


async def get_purchase_order_schedules(
    client: FusionClient,
    po_header_id,
    limit: int = 25,
) -> ToolResult:
    """Fetch the shipment schedules of one purchase order.

    Args:
        po_header_id: The POHeaderId of the PO, e.g. 2144.
        limit: Max schedule records to return. A PO's schedule count is
            normally small; the default of 25 covers typical orders.

    Returns:
        ToolResult whose items are the projected schedule dicts for this
        PO, in the order Fusion returns them. Empty items means the PO has
        no schedules (or the id did not resolve — the flat collection
        returns an empty set rather than 404 for an unknown POHeaderId).
    """
    params = {
        "onlyData": "true",
        "q": f"POHeaderId={po_header_id}",
        "limit": limit,
        "fields": ",".join(_PROJECTED_FIELDS),
    }
    response = await client.get(PO_SCHEDULES_PATH, params=params)
    items = response.get("items", [])
    projected = [{k: item.get(k) for k in _PROJECTED_FIELDS} for item in items]

    return ToolResult.build(
        items=projected,
        limit_applied=limit,
        total_available=len(projected),
    )
