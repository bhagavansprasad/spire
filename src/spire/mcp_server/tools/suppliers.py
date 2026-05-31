"""Supplier search tool.

Plain async function — not coupled to FastMCP. Registration happens
in spire.mcp_server.server. This lets us test the tool directly.

Filters supported:
- supplier_name_contains: LIKE match on Supplier field (server-side q=)
- status: exact match on Status (client-side; Fusion REST rejects
  q=Status='...' on this endpoint)
- limit: max records returned after client-side filtering (default 25)

Country-code filtering requires the 'addresses' child resource and lives
in the search_suppliers_by_country tool.

Returns a ToolResult so callers can distinguish "this is everything"
from "this is a capped subset." Items are projected to a useful subset
of fields (see _PROJECTED_FIELDS) — matching search_suppliers_by_country.
"""

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


SUPPLIERS_PATH = "/fscmRestApi/resources/11.13.18.05/suppliers"

# Over-fetch cap for when status filtering happens client-side, so the
# filter has enough records to work with.
OVERFETCH_LIMIT = 500

_PROJECTED_FIELDS = [
    "SupplierId",
    "SupplierNumber",
    "Supplier",
    "Status",
    "BusinessRelationship",
    "TaxpayerCountryCode",
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
    response = await client.get(SUPPLIERS_PATH, params=params)
    total = response.get("totalResults")
    return total if isinstance(total, int) else None


async def search_suppliers(
    client: FusionClient,
    supplier_name_contains: str | None = None,
    status: str | None = None,
    limit: int = 25,
) -> ToolResult:
    """Search Oracle Fusion suppliers.

    Args:
        supplier_name_contains: Substring match on Supplier name (LIKE).
            Sent server-side via q=.
        status: Exact match on Status (e.g., "ACTIVE", "INACTIVE").
            Applied client-side — Fusion REST rejects q=Status='...' on
            this endpoint.
        limit: Max records to return AFTER client-side filtering.

    Returns:
        ToolResult with:
          - items: projected supplier dicts (up to `limit`)
          - total_available: true source count when computable, else None
          - limit_applied: the limit value used
          - truncated: True iff we know more records match than returned
    """
    # Only the name fragment can be a server-side clause. status is
    # client-side only (endpoint rejects it), so when status is present
    # we over-fetch and filter in Python.
    server_clause: str | None = None
    if supplier_name_contains:
        server_clause = f"Supplier LIKE '%{supplier_name_contains}%'"

    needs_client_filter = status is not None
    fetch_limit = OVERFETCH_LIMIT if needs_client_filter else limit

    params: dict[str, str | int] = {"limit": fetch_limit}
    if server_clause:
        params["q"] = server_clause

    response = await client.get(SUPPLIERS_PATH, params=params)
    items = response.get("items", [])

    def matches(item: dict) -> bool:
        if status is not None and item.get("Status") != status:
            return False
        return True

    filtered = [item for item in items if matches(item)]
    final_items = filtered[:limit]
    projected = [{k: item.get(k) for k in _PROJECTED_FIELDS} for item in final_items]

    # ---- total_available / truncated, mirroring invoices.py ----
    #
    # 1. Client-side filtering hit the over-fetch cap: we did not examine
    #    every supplier; truncation occurred but the true count is unknown.
    # 2. No client-side filtering and the result is full at limit: a cheap
    #    totalResults call gives the authoritative count.
    # 3. Otherwise: we have every matching record.

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
