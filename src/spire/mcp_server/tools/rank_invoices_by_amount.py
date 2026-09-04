"""Rank invoices by amount (server-side top-N).

Plain async function — not coupled to FastMCP. Registration happens in
spire.mcp_server.server.

WHY A DEDICATED TOOL (not a flag on search_invoices): the aggregation layer's
rule is that a different measure is a different tool, never a flag on an
existing one (see the planner's _AGGREGATION_TOOLS registry). "Top N invoices
by amount" is a ranking by InvoiceAmount, distinct from search_invoices'
list-with-filters, so it is its own tool wired to its own aggregate op.

SERVER-SIDE TOP-N — verified by curl (docs/spire_fusion_endpoints_reference.md,
2026-09-02, re-confirmed on the eqjz pod): /invoices supports
``orderBy=InvoiceAmount:desc`` server-side, so ``limit=N`` returns the actual N
highest-amount invoices across the whole collection (not a page slice), strictly
descending. For supplier 1252 (Lee Supplies), totalResults=1355 and the top 10
come back 5,414,782.13, 5,414,782.12, ... — a true top-N.

PER-SUPPLIER: when a supplier is named, the ranking is scoped with
``q=SupplierNumber='<num>'`` — the curl-confirmed combination. A supplier NAME
is resolved to its SupplierNumber first (via search_suppliers), so the invoice
query always uses the confirmed SupplierNumber+orderBy call rather than an
unverified ``Supplier LIKE ... & orderBy`` composite.
"""

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.suppliers import search_suppliers


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


async def _resolve_supplier_number(
    client: FusionClient, supplier_name: str
) -> str | None:
    """Resolve a supplier name substring to a single SupplierNumber.

    Uses the supplier fetcher's LIKE match. Returns the SupplierNumber of the
    first match, or None if no supplier matched. When the name is ambiguous
    (matches several), the first is used — the caller's ranking is then scoped
    to that supplier; a more precise name narrows it.
    """
    result = await search_suppliers(
        client, supplier_name_contains=supplier_name, limit=1
    )
    items = result.items if hasattr(result, "items") else result.get("items", [])
    if not items:
        return None
    return items[0].get("SupplierNumber")


async def rank_invoices_by_amount(
    client: FusionClient,
    supplier_name: str | None = None,
    top_n: int = 10,
) -> dict:
    """Return the top-N invoices by InvoiceAmount, highest first.

    Args:
        supplier_name: Optional substring of a supplier's name. When given, the
            ranking is scoped to that supplier's invoices (resolved to its
            SupplierNumber first). When omitted, the ranking is across all
            invoices.
        top_n: How many invoices to return (the N in "top N"). Default 10.

    Returns:
        An aggregation-shaped dict (shape="invoice_amount_ranking"):
          - rows: projected invoice dicts, strictly descending by
            InvoiceAmount (up to top_n)
          - total_available: the honest total matching count (all invoices, or
            all of the supplier's invoices)
          - returned: how many rows are in this result
          - truncated: True iff more invoices exist than returned
          - supplier_name: echoed back (None when unscoped)
    """
    server_clause: str | None = None
    if supplier_name:
        supplier_number = await _resolve_supplier_number(client, supplier_name)
        if supplier_number is None:
            # No such supplier — an empty, honest result rather than ranking
            # across everyone (which would silently ignore the supplier).
            return {
                "shape": "invoice_amount_ranking",
                "supplier_name": supplier_name,
                "total_available": 0,
                "returned": 0,
                "truncated": False,
                "rows": [],
            }
        server_clause = f"SupplierNumber='{supplier_number}'"

    # orderBy makes limit a TRUE top-N server-side (no over-fetch needed).
    params: dict[str, str | int] = {
        "orderBy": "InvoiceAmount:desc",
        "limit": top_n,
    }
    if server_clause:
        params["q"] = server_clause

    response = await client.get(INVOICES_PATH, params=params)
    items = response.get("items", [])
    rows = [{k: item.get(k) for k in _PROJECTED_FIELDS} for item in items]

    # The honest total for this ranking's scope (all invoices, or the
    # supplier's). total_results probes totalResults with the same clause.
    total = await client.total_results(INVOICES_PATH, server_clause)

    # Aggregation-shaped result: the synthesizer routes on the "shape" tag
    # (AGGREGATION_SCHEMAS / _LOCAL_AGGREGATION_BUILDERS), not on target_entity
    # (a ranking Intent carries an aggregate block, no target). The executor
    # wraps this dict under the "aggregation" bucket. Same shape contract as
    # aggregate_invoices_by_supplier's supplier_spend_ranking.
    return {
        "shape": "invoice_amount_ranking",
        "supplier_name": supplier_name,
        "total_available": total,
        "returned": len(rows),
        "truncated": total is not None and total > len(rows),
        "rows": rows,
    }
