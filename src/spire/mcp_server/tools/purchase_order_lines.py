"""Purchase-order lines tool: the line children of one PO.

Lines are a child of the PO record, at
/purchaseOrders/{POHeaderId}/child/lines. Each line carries its own
identity (POLineId, LineNumber), a Category, quantity/price, and amounts
(Ordered, TotalTax, Total).

Unlike the supplier children (sites / classifications), the PO line body
DOES carry the parent id — both POHeaderId and OrderNumber are present on
each line row. The join key is therefore available in the body, though we
still fetch per-parent via the URL path.

This is the lines half of PO detail. The header is a separate tool
(get_purchase_order_by_id), composed by the KG/planner — the PO→lines
join lives in the KG, not baked into one tool.

Not-found: an unknown POHeaderId 404s on the child path (same as the
single-PO header path), so this tool catches the 404 and returns an
empty ToolResult — "no lines for a non-existent PO" — mirroring
get_purchase_order_by_id's not-found contract. Non-404 errors are
re-raised. In the normal pipeline the header is fetched first, so this
tool only runs for a real PO; the guard is defensive.

Returns a ToolResult (like the supplier-child tools) so callers can tell
a complete result from a capped subset.
"""

import httpx

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


# Child-lines path template; formatted with a POHeaderId per call.
PO_LINES_PATH_TEMPLATE = (
    "/fscmRestApi/resources/11.13.18.05/purchaseOrders"
    "/{po_header_id}/child/lines"
)

_PROJECTED_FIELDS = [
    "POLineId",
    "POHeaderId",
    "LineNumber",
    "OrderNumber",
    "LineType",
    "Description",
    "Category",
    "Quantity",
    "UOM",
    "Price",
    "Ordered",
    "TotalTax",
    "Total",
    "Status",
    "StatusCode",
]


async def get_purchase_order_lines(
    client: FusionClient,
    po_header_id,
    limit: int = 25,
) -> ToolResult:
    """Fetch the lines of one purchase order.

    Args:
        po_header_id: The POHeaderId of the parent PO, e.g. 2144.
        limit: Max line records to return. A PO's line count is normally
            small; the default of 25 covers typical orders.

    Returns:
        ToolResult whose items are the projected line dicts for this PO,
        in the order Fusion returns them. Empty items means the PO has no
        lines (or the id did not resolve).
    """
    path = PO_LINES_PATH_TEMPLATE.format(po_header_id=po_header_id)
    params = {
        "onlyData": "true",
        "limit": limit,
        "fields": ",".join(_PROJECTED_FIELDS),
    }
    try:
        response = await client.get(path, params=params)
    except httpx.HTTPStatusError as exc:
        # An unknown POHeaderId 404s on the child path. Treat that as "no
        # lines" (empty ToolResult), mirroring get_purchase_order_by_id.
        # Any other status is a real error — re-raise it.
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
