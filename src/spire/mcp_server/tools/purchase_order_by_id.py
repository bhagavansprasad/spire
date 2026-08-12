"""Purchase-order header lookup tool.

Resolves ONE purchase order from whatever number the user gave — an
OrderNumber or a POHeaderId — and returns its header.

WHY THIS RESOLVES RATHER THAN FETCHES
"PO 162034" and "PO 2144" look identical in a prompt: both are bare
numbers. But they are DIFFERENT identifiers on different fields, and on
this pod they are wildly different values for the same PO — OrderNumber
"162034" is POHeaderId 1. Nothing in the phrasing says which one the user
meant, so guessing would just move the bug somewhere quieter. This tool
tries both instead:

  1. q=OrderNumber='X' on the collection. Tried FIRST because OrderNumber
     is what a user reads off a PO document — it is the number they are
     most likely holding.
  2. /purchaseOrders/X, treating X as POHeaderId. Tried only if (1) found
     nothing.

Two cheap calls worst case, one in the common case, correct for both
phrasings.

(This was a live bug before P6: the by_id filter mapped to po_header_id
while the parser told the LLM to use it for "the id or number". Every
test had used 2144 — which happens to be a POHeaderId — so it never
surfaced. A user naming a PO by its printed number got the wrong PO or
nothing.)

NAMING
The function is still called get_purchase_order_by_id and its arg is
still po_header_id, both now slightly wrong — it resolves an identifier
rather than fetching by a known id. Kept deliberately: renaming ripples
through the KG entity-tool row, the planner's _TOOL_PRIMARY_ARG and the
server wrapper, and P6 has already shown how easily a wrapper gets missed
in a multi-file rename. The behaviour is documented instead.

Returns a single dict (not a list), mirroring get_buyer, since either
identifier resolves to at most one PO. Returns None when neither lookup
finds anything.

Not-found: the COLLECTION path returns empty items for a non-match, while
the SINGLE-RECORD path returns HTTP 404. Both are handled; non-404 errors
are re-raised untouched.

This is the header half of PO detail. Lines are a separate tool
(purchase_order_lines), composed by the KG/planner — the PO->lines join
lives in the KG, not baked into one tool.
"""

import httpx

from spire.fusion.client import FusionClient


PURCHASE_ORDERS_PATH = "/fscmRestApi/resources/11.13.18.05/purchaseOrders"

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
    "CreatedBy",
    "CreationDate",
    "LastUpdatedBy",
    "LastUpdateDate",
]


def _project(source: dict) -> dict:
    return {k: source.get(k) for k in _PROJECTED_FIELDS}


async def _try_order_number(client: FusionClient, value) -> dict | None:
    """Look the value up as an OrderNumber via the collection.

    OrderNumber is a string on the pod, so the clause is quoted. A
    non-match returns empty items (not a 404) — collections and
    single-record paths differ that way.
    """
    params = {
        "onlyData": "true",
        "q": f"OrderNumber='{value}'",
        "fields": ",".join(_PROJECTED_FIELDS),
        "limit": 1,
    }
    response = await client.get(PURCHASE_ORDERS_PATH, params=params)
    items = response.get("items", [])
    if not items:
        return None
    return _project(items[0])


async def _try_header_id(client: FusionClient, value) -> dict | None:
    """Look the value up as a POHeaderId via the single-record path.

    An unknown id 404s here; that is mapped to None.
    """
    path = PO_BY_ID_PATH_TEMPLATE.format(po_header_id=value)
    params = {
        "onlyData": "true",
        "fields": ",".join(_PROJECTED_FIELDS),
    }
    try:
        response = await client.get(path, params=params)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise

    # The single-record path returns the header object directly, not an
    # {"items": [...]} envelope. Guard for both shapes defensively: some
    # Fusion pods wrap even single fetches.
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

    return _project(source)


async def get_purchase_order_by_id(
    client: FusionClient, po_header_id
) -> dict | None:
    """Look up one purchase order by its order number OR its header id.

    Tries OrderNumber first (what a user reads off a PO), then falls back
    to POHeaderId. See the module docstring for why both are tried.

    Args:
        po_header_id: The number the user gave — an OrderNumber (e.g.
            "162034") or a POHeaderId (e.g. 2144). The arg name is
            historical; either identifier works.

    Returns:
        Dict with the projected PO header fields, or None if neither
        lookup finds a PO.
    """
    by_number = await _try_order_number(client, po_header_id)
    if by_number is not None:
        return by_number
    return await _try_header_id(client, po_header_id)
