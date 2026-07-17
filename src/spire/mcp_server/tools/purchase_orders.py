"""Purchase order search tool.

Plain async function — not coupled to FastMCP. Registration happens
in spire.mcp_server.server.

Composite filter note:
Fusion REST's q= parameter on /purchaseOrders does not reliably
AND-combine clauses on this pod. Workaround: send the most selective
single clause via q=, filter remaining clauses in Python.

Filters supported:
- supplier_name: substring match on Supplier
- supplier_id: exact match on SupplierId (numeric)
- status: exact match on StatusCode (e.g., "OPEN", "CLOSED")
- created_before: CreationDate < this ISO date (exclusive upper bound)
- created_since: CreationDate >= this ISO date (inclusive lower bound)
- limit: max records returned after client-side filtering (default 25)

DATE FILTERING — READ THIS
The date filters work on **CreationDate, not OrderDate**. OrderDate is
projectable but NOT queryable on this pod ("The attribute(s) [OrderDate]
are not queriable", HTTP 400). CreationDate is queryable. They are minutes
apart in the demo data but they are not the same thing — a PO can be
created well before it is ordered. The params are named for what they
actually filter rather than for what a "stale PO" question is really
asking.

Unusually, BOTH bounds work server-side standalone (verified: `>=` and
`<` each return rows). They still cannot be composited — the pod's
single-clause rule applies as everywhere else — so one bound goes to the
server and the other is filtered client-side.

Returns a ToolResult so callers can distinguish a complete result from
a capped subset.
"""

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


PURCHASE_ORDERS_PATH = "/fscmRestApi/resources/11.13.18.05/purchaseOrders"

OVERFETCH_LIMIT = 200

_PROJECTED_FIELDS = [
    "POHeaderId",
    "OrderNumber",
    "Status",
    "StatusCode",
    "Supplier",
    "SupplierId",
    "Buyer",
    "BuyerId",
    "Ordered",
    "CurrencyCode",
    "Description",
    "CreationDate",
]


async def _fetch_total_for_clause(
    client: FusionClient, server_clause: str | None
) -> int | None:
    """Cheaply ask Fusion how many records match the server clause."""
    params: dict[str, str | int] = {
        "limit": 1,
        "totalResults": "true",
        "onlyData": "true",
    }
    if server_clause:
        params["q"] = server_clause
    response = await client.get(PURCHASE_ORDERS_PATH, params=params)
    total = response.get("totalResults")
    return total if isinstance(total, int) else None


async def search_purchase_orders(
    client: FusionClient,
    supplier_name: str | None = None,
    supplier_id: int | None = None,
    status: str | None = None,
    created_before: str | None = None,
    created_since: str | None = None,
    limit: int = 25,
) -> ToolResult:
    """Search Oracle Fusion purchase orders.

    Args:
        supplier_name: Substring match on Supplier name.
        supplier_id: Exact SupplierId match (numeric).
        status: Exact StatusCode match. The pod has eleven values —
            OPEN, CLOSED, CLOSED FOR RECEIVING, REJECTED, PENDING
            APPROVAL, WITHDRAWN, INCOMPLETE, CLOSED FOR INVOICING,
            PENDING SIGNATURE, CANCELED, ON HOLD (spaces, not
            underscores).
        created_before: ISO "YYYY-MM-DD". CreationDate strictly BEFORE
            this date. This is the bound a "stale POs / older than N
            months" question needs.
        created_since: ISO "YYYY-MM-DD". CreationDate on or after this
            date.
        limit: Max records to return AFTER client-side filtering.

    Returns:
        ToolResult with:
          - items: projected PO dicts (up to `limit`)
          - total_available: true source count when computable, else None
          - limit_applied: the limit value used
          - truncated: True iff we know more records match than returned
    """
    # Only ONE clause can go to the server (the pod cannot AND-combine),
    # so pick the most selective. Priority: exact id > status > dates >
    # LIKE. The dates sit above LIKE because a stale-PO question usually
    # carries nothing else, and without a server clause it would page the
    # whole collection (~3,362 POs). They sit below status because status
    # is an exact match and cheaper. Whichever bound loses the slot is
    # still applied client-side.
    server_clause: str | None = None
    if supplier_id is not None:
        server_clause = f"SupplierId={supplier_id}"
    elif status:
        server_clause = f"StatusCode='{status}'"
    elif created_before:
        server_clause = f"CreationDate < '{created_before}'"
    elif created_since:
        server_clause = f"CreationDate >= '{created_since}'"
    elif supplier_name:
        server_clause = f"Supplier LIKE '%{supplier_name}%'"

    needs_client_filter = sum(
        bool(x)
        for x in (
            supplier_name,
            supplier_id is not None,
            status,
            created_before,
            created_since,
        )
    ) > 1
    fetch_limit = OVERFETCH_LIMIT if needs_client_filter else limit

    params: dict[str, str | int] = {"limit": fetch_limit}
    if server_clause:
        params["q"] = server_clause

    response = await client.get(PURCHASE_ORDERS_PATH, params=params)
    items = response.get("items", [])

    def matches(item: dict) -> bool:
        if supplier_id is not None and item.get("SupplierId") != supplier_id:
            return False
        if status and item.get("StatusCode") != status:
            return False
        if supplier_name and supplier_name.lower() not in (item.get("Supplier") or "").lower():
            return False
        # Dates are ISO timestamps ("2014-03-04T05:26:50+00:00"); a
        # date-only bound compares correctly as a string prefix.
        created = item.get("CreationDate") or ""
        if created_before and created >= created_before:
            return False
        if created_since and created < created_since:
            return False
        return True

    filtered = [item for item in items if matches(item)]
    final_items = filtered[:limit]
    projected = [{k: item.get(k) for k in _PROJECTED_FIELDS} for item in final_items]

    # ---- total_available / truncated, mirroring invoices.py ----
    if needs_client_filter and len(items) >= OVERFETCH_LIMIT:
        return ToolResult(
            items=projected,
            total_available=None,
            limit_applied=limit,
            truncated=True,
        )

    if not needs_client_filter and len(final_items) >= limit:
        total = await _fetch_total_for_clause(client, server_clause)
        return ToolResult.build(
            items=projected,
            limit_applied=limit,
            total_available=total,
        )

    return ToolResult.build(
        items=projected,
        limit_applied=limit,
        total_available=len(filtered),
    )
