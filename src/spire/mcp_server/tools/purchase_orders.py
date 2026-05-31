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
- limit: max records returned after client-side filtering (default 25)

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
    limit: int = 25,
) -> ToolResult:
    """Search Oracle Fusion purchase orders.

    Args:
        supplier_name: Substring match on Supplier name.
        supplier_id: Exact SupplierId match (numeric).
        status: Exact StatusCode match. Common values: "OPEN", "CLOSED",
            "INCOMPLETE", "CANCELED".
        limit: Max records to return AFTER client-side filtering.

    Returns:
        ToolResult with:
          - items: projected PO dicts (up to `limit`)
          - total_available: true source count when computable, else None
          - limit_applied: the limit value used
          - truncated: True iff we know more records match than returned
    """
    # Priority for server-side clause: exact id > status > LIKE.
    server_clause: str | None = None
    if supplier_id is not None:
        server_clause = f"SupplierId={supplier_id}"
    elif status:
        server_clause = f"StatusCode='{status}'"
    elif supplier_name:
        server_clause = f"Supplier LIKE '%{supplier_name}%'"

    needs_client_filter = sum(
        bool(x) for x in (supplier_name, supplier_id is not None, status)
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
