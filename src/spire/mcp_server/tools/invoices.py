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
- limit: max records returned after client-side filtering (default 25)
"""

from spire.fusion.client import FusionClient


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


async def search_invoices(
    client: FusionClient,
    supplier_number: str | None = None,
    supplier_name: str | None = None,
    invoice_date_after: str | None = None,
    limit: int = 25,
) -> list[dict]:
    """Search Oracle Fusion invoices.

    Args:
        supplier_number: Exact SupplierNumber, e.g., "1252".
        supplier_name: Substring match on Supplier name.
        invoice_date_after: ISO date "YYYY-MM-DD".
        limit: Max records to return AFTER client-side filtering.

    Returns:
        List of invoice dicts, projected to a useful subset of fields.
    """
    # Pick the most selective filter to send to Fusion via q=.
    # Priority: exact match (supplier_number) > LIKE > date range.
    server_clause: str | None = None
    if supplier_number:
        server_clause = f"SupplierNumber='{supplier_number}'"
    elif supplier_name:
        server_clause = f"Supplier LIKE '%{supplier_name}%'"
    elif invoice_date_after:
        server_clause = f"InvoiceDate >= '{invoice_date_after}'"

    # Over-fetch if we'll be filtering further; otherwise use limit directly.
    needs_client_filter = sum(
        bool(x) for x in (supplier_number, supplier_name, invoice_date_after)
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
        return True

    filtered = [item for item in items if matches(item)][:limit]
    return [{k: item.get(k) for k in _PROJECTED_FIELDS} for item in filtered]
