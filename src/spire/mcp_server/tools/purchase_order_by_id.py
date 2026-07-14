"""Purchase-order header lookup tool.

Fetches ONE purchase order by its POHeaderId, from
/purchaseOrders/{POHeaderId}. On this pod the single-record path returns
one PO header (HTTP 200), not a collection — ~90 attributes. POHeaderId
is a small integer here (e.g. 2144), not the long 3000000… form.

Returns a single dict (not a list), mirroring get_buyer, since a
POHeaderId is unique. Returns None when no PO matches the given id.

Not-found: unlike the collection endpoints (which return empty items for
a non-match), the single-record path returns HTTP 404 for an unknown id.
FusionClient.get raises on that, so this tool catches the 404 and returns
None — giving the same "no PO" contract as get_buyer. Non-404 errors are
re-raised untouched.

This is the header half of PO detail. Lines are a separate tool
(purchase_order_lines), composed by the KG/planner — the PO→lines join
lives in the KG, not baked into one tool.
"""

import httpx

from spire.fusion.client import FusionClient


# Single-PO path template; formatted with a POHeaderId per call.
PO_BY_ID_PATH_TEMPLATE = (
    "/fscmRestApi/resources/11.13.18.05/purchaseOrders/{po_header_id}"
)

_PROJECTED_FIELDS = [
    "POHeaderId",
    "OrderNumber",
    "Status",
    "StatusCode",
    "Supplier",
    "SupplierId",
    "Buyer",
    "BuyerId",
    "SupplierSite",
    "Ordered",
    "Total",
    "TotalTax",
    "CurrencyCode",
    "PaymentTerms",
    "ShipToLocationCode",
    "BillToLocation",
    "OrderDate",
    "Description",
]


async def get_purchase_order_by_id(
    client: FusionClient, po_header_id
) -> dict | None:
    """Look up one purchase order by its POHeaderId.

    The single-record path returns one PO header, not a collection.

    Args:
        po_header_id: The POHeaderId of the PO, e.g. 2144.

    Returns:
        Dict with the projected PO header fields, or None if no PO with
        that id exists.
    """
    path = PO_BY_ID_PATH_TEMPLATE.format(po_header_id=po_header_id)
    params = {
        "onlyData": "true",
        "fields": ",".join(_PROJECTED_FIELDS),
    }
    try:
        response = await client.get(path, params=params)
    except httpx.HTTPStatusError as exc:
        # A non-existent POHeaderId 404s on the single-record path. Treat
        # that as "no PO" (return None), mirroring get_buyer's contract.
        # Any other status is a real error — re-raise it.
        if exc.response.status_code == 404:
            return None
        raise

    # The single-record path returns the header object directly, not an
    # {"items": [...]} envelope. Guard for both shapes defensively: some
    # Fusion pods wrap even single fetches. If we somehow get a
    # collection, take the first item; if we get an empty/None body,
    # report not-found.
    if not response:
        return None
    if "items" in response:
        items = response.get("items", [])
        if not items:
            return None
        source = items[0]
    else:
        source = response

    # A missing POHeaderId in the body means the fetch didn't resolve to
    # a real PO (e.g. an error object) — treat as not found.
    if source.get("POHeaderId") is None:
        return None

    return {k: source.get(k) for k in _PROJECTED_FIELDS}
