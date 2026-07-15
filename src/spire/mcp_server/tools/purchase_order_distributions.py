"""Purchase-order distributions tool: the distribution accounts of one
PO schedule.

Distributions are the deepest PO child — the charge / accrual / variance
accounts a schedule's amount is booked to. They have NO flat endpoint on
this pod (a top-level /purchaseOrderDistributions 404s), so they are
reachable ONLY on the deep nested path:

    /purchaseOrders/{POHeaderId}/child/lines/{POLineId}
        /child/schedules/{LineLocationId}/child/distributions

That path needs THREE ids: POHeaderId, POLineId and LineLocationId. All
three are carried on the parent SCHEDULE row (POSchedule projects them), so
the planner iterates distributions over a PO's schedules, passing all three
ids per schedule. This is why P3b needed multi-field iteration.

Not-found: an unknown id chain 404s on the nested path, so this tool
catches the 404 and returns an empty ToolResult. Non-404 errors are
re-raised. In the normal pipeline the schedule is fetched first, so this
tool only runs for a real schedule; the guard is defensive.

Returns a ToolResult (like the other child tools) so callers can tell a
complete result from a capped subset.
"""

import httpx

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


# Deep nested distributions path; formatted with all three parent ids.
PO_DISTRIBUTIONS_PATH_TEMPLATE = (
    "/fscmRestApi/resources/11.13.18.05/purchaseOrders"
    "/{po_header_id}/child/lines/{po_line_id}"
    "/child/schedules/{line_location_id}/child/distributions"
)

_PROJECTED_FIELDS = [
    "PODistributionId",
    "POHeaderId",
    "POLineId",
    "OrderNumber",
    "DistributionNumber",
    "ScheduleNumber",
    "POChargeAccount",
    "POAccrualAccount",
    "POVarianceAccount",
    "DeliverToLocationCode",
    "Percentage",
    "Quantity",
    "Ordered",
    "Total",
    "Status",
    "StatusCode",
]


async def get_purchase_order_distributions(
    client: FusionClient,
    po_header_id,
    po_line_id,
    line_location_id,
    limit: int = 25,
) -> ToolResult:
    """Fetch the distributions of one PO schedule.

    All three parent ids are required because the distributions resource
    exists only on the deep nested path (there is no flat endpoint). They
    come from the parent schedule row.

    Args:
        po_header_id: The POHeaderId of the PO.
        po_line_id: The POLineId of the line the schedule belongs to.
        line_location_id: The LineLocationId (schedule id).
        limit: Max distribution records to return (default 25).

    Returns:
        ToolResult whose items are the projected distribution dicts for
        this schedule, in the order Fusion returns them. Empty items means
        the schedule has no distributions (or the id chain did not
        resolve).
    """
    path = PO_DISTRIBUTIONS_PATH_TEMPLATE.format(
        po_header_id=po_header_id,
        po_line_id=po_line_id,
        line_location_id=line_location_id,
    )
    params = {
        "onlyData": "true",
        "limit": limit,
        "fields": ",".join(_PROJECTED_FIELDS),
    }
    try:
        response = await client.get(path, params=params)
    except httpx.HTTPStatusError as exc:
        # An unknown id chain 404s on the nested path. Treat that as "no
        # distributions" (empty ToolResult). Any other status is a real
        # error — re-raise it.
        if exc.response.status_code == 404:
            return ToolResult.build(
                items=[], limit_applied=limit, total_available=0
            )
        raise

    items = response.get("items", [])
    projected = [{k: item.get(k) for k in _PROJECTED_FIELDS} for item in items]

    return ToolResult.build(
        items=projected,
        limit_applied=limit,
        total_available=len(projected),
    )
