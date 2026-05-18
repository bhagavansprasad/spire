"""Invoice search tool.

Plain async function — not coupled to FastMCP. Registration happens
in spire.mcp_server.server.

Filters supported:
- supplier_number: exact match on SupplierNumber
- supplier_name: substring match (LIKE) on Supplier
- invoice_date_after: ISO date string; matches invoices on or after this date
- limit: max records returned (default 25)

Response is projected to a small subset of fields to keep LLM context
manageable. Full fields are available via the underlying endpoint if
needed later.
"""

from spire.fusion.client import FusionClient


INVOICES_PATH = "/fscmRestApi/resources/11.13.18.05/invoices"

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
        supplier_number: Exact SupplierNumber match (e.g., "1252").
        supplier_name: Substring match on Supplier name (LIKE).
        invoice_date_after: ISO date "YYYY-MM-DD"; returns invoices on
            or after this date.
        limit: Max records to return.

    Returns:
        List of invoice dicts, projected to a useful subset of fields.
    """
    clauses = []
    if supplier_number:
        clauses.append(f"SupplierNumber='{supplier_number}'")
    if supplier_name:
        clauses.append(f"Supplier LIKE '%{supplier_name}%'")
    if invoice_date_after:
        clauses.append(f"InvoiceDate >= '{invoice_date_after}'")

    params: dict[str, str | int] = {"limit": limit}
    if clauses:
        params["q"] = " AND ".join(clauses)

    response = await client.get(INVOICES_PATH, params=params)
    items = response.get("items", [])
    return [{k: item.get(k) for k in _PROJECTED_FIELDS} for item in items]
