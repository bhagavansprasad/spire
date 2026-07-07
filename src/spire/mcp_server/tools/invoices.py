
"""Invoice search tool.

Plain async function — not coupled to FastMCP. Registration happens
in spire.mcp_server.server.

Composite filter note:
Fusion REST's q= parameter on /invoices does not reliably AND-combine
clauses on this pod (clauses combine to empty result). Workaround: send
the most selective single clause via q=, filter remaining clauses in
Python. Over-fetch is capped at OVERFETCH_LIMIT.

Filters supported:
- supplier_number: exact match on SupplierNumber
- supplier_name: substring match (LIKE) on Supplier
- invoice_date_after: ISO date string; matches invoices on or after this date
- invoice_date_before: ISO date string; matches invoices strictly before
  this date (exclusive). Client-side only — never sent as the server q=
  clause, so a lone invoice_date_before with no other filter over-fetches
  up to `limit` unfiltered and may miss older records beyond the fetch
  window. Pair it with invoice_date_after for a bounded range.
- limit: max records returned after client-side filtering (default 25)
"""

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


INVOICES_PATH = "/fscmRestApi/resources/11.13.18.05/invoices"

# Upper bound on the server-side fetch so client-side filtering has
# enough to work with. Tunable; higher means more network, lower
# means we may miss matches.
OVERFETCH_LIMIT = 200

_PROJECTED_FIELDS = [
    "InvoiceId",
    "InvoiceNumber",
    "InvoiceDate",
    "InvoiceAmount",
    "InvoiceCurrency",
    "Supplier",
    "SupplierNumber",
    "PaidStatus",
    "ApprovalStatus",
    "PurchaseOrderNumber",
]


async def _fetch_total_for_clause(
    client: FusionClient, server_clause: str | None
) -> int | None:
    """Cheaply ask Fusion how many records match the server clause.

    Uses limit=1 + totalResults=true so we pay minimum bandwidth.
    Returns None if the response doesn't carry totalResults.
    """
    params: dict[str, str | int] = {
        "limit": 1,
        "totalResults": "true",
        "onlyData": "true",
    }
    if server_clause:
        params["q"] = server_clause
    response = await client.get(INVOICES_PATH, params=params)
    total = response.get("totalResults")
    return total if isinstance(total, int) else None


async def search_invoices(
    client: FusionClient,
    supplier_number: str | None = None,
    supplier_name: str | None = None,
    invoice_date_after: str | None = None,
    invoice_date_before: str | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    limit: int = 25,
) -> ToolResult:
    """Search Oracle Fusion invoices.

    Args:
        supplier_number: Exact SupplierNumber, e.g., "1252".
        supplier_name: Substring match on Supplier name.
        invoice_date_after: ISO date "YYYY-MM-DD". Matches invoices on
            or after this date (inclusive).
        invoice_date_before: ISO date "YYYY-MM-DD". Matches invoices
            strictly before this date (exclusive). Applied client-side
            only. For a calendar month, pair with invoice_date_after:
            e.g. Jan 2022 -> after="2022-01-01", before="2022-02-01".
        amount_min: Lower bound on InvoiceAmount (inclusive). Client-side.
        amount_max: Upper bound on InvoiceAmount (inclusive). Client-side.
        limit: Max records to return AFTER client-side filtering.

    Returns:
        ToolResult with:
          - items: projected invoice dicts (up to `limit`)
          - total_available: true source count when computable, else None
          - limit_applied: the limit value used
          - truncated: True iff we know more records match than returned
    """
    # Pick the most selective filter to send to Fusion via q=.
    # Priority: exact match (supplier_number) > LIKE > date lower bound.
    # invoice_date_before is intentionally never the server clause; it
    # stays a pure client-side filter to keep the truncation logic intact.
    server_clause: str | None = None
    if supplier_number:
        server_clause = f"SupplierNumber='{supplier_number}'"
    elif supplier_name:
        server_clause = f"Supplier LIKE '%{supplier_name}%'"
    elif invoice_date_after:
        server_clause = f"InvoiceDate >= '{invoice_date_after}'"

    # Over-fetch if we'll be filtering further; otherwise use limit directly.
    needs_client_filter = sum(
        bool(x)
        for x in (
            supplier_number,
            supplier_name,
            invoice_date_after,
            invoice_date_before,
            amount_min is not None,
            amount_max is not None,
        )
    ) > 1
    fetch_limit = OVERFETCH_LIMIT if needs_client_filter else limit

    params: dict[str, str | int] = {"limit": fetch_limit}
    if server_clause:
        params["q"] = server_clause

    response = await client.get(INVOICES_PATH, params=params)
    items = response.get("items", [])

    # Apply remaining filters in Python.
    def matches(item: dict) -> bool:
        if supplier_number and item.get("SupplierNumber") != supplier_number:
            return False
        if supplier_name and supplier_name.lower() not in (item.get("Supplier") or "").lower():
            return False
        if invoice_date_after and (item.get("InvoiceDate") or "") < invoice_date_after:
            return False
        if invoice_date_before and (item.get("InvoiceDate") or "") >= invoice_date_before:
            return False
        if amount_min is not None or amount_max is not None:
            amt = item.get("InvoiceAmount")
            if amt is None:
                return False
            if amount_min is not None and amt < amount_min:
                return False
            if amount_max is not None and amt > amount_max:
                return False
        return True

    filtered = [item for item in items if matches(item)]
    final_items = filtered[:limit]
    projected = [{k: item.get(k) for k in _PROJECTED_FIELDS} for item in final_items]

    # ---- Determine total_available and truncated ----
    #
    # Three cases:
    #
    # 1. Composite filter, server overfetch hit OVERFETCH_LIMIT:
    #    The server clause matched more than we examined; we may have
    #    missed records that would satisfy the full filter. We know
    #    truncation occurred but can't compute the true total.
    #
    # 2. Result is full at the client-side cap (len(final) == limit) AND
    #    no composite filtering happened:
    #    Single server-side filter, capped at limit. A cheap totalResults
    #    call gives the authoritative count.
    #
    # 3. Otherwise:
    #    We have every record that matches. total_available is len(filtered);
    #    truncated is False.

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


