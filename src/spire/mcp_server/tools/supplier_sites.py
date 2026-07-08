"""Supplier-site edge tool: does one supplier have a site in a given BU?

Sites are a child of the supplier record, at
/suppliers/{SupplierId}/child/sites. Each site carries a ProcurementBU
(display string, e.g. "US1 Business Unit"). ProcurementBU filters
reliably server-side on this child (confirmed on pod: a matching value
returns the site, a non-existent value returns empty).

This is an EDGE tool, called once per parent supplier by the executor's
keep-parent-when-nonempty path (mirror of search_invoices with amount_min
for has_invoice_over_amount). It takes ONE supplier_id plus the target
business_unit, and returns that supplier's sites in that BU. A non-empty
result tells the executor to keep the parent supplier.

The whole-pod scan is NOT here — the executor does the iteration across
suppliers. This tool only answers the per-supplier question.
"""

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


# Child-sites path template; formatted with a SupplierId per call.
SITES_PATH_TEMPLATE = (
    "/fscmRestApi/resources/11.13.18.05/suppliers/{supplier_id}/child/sites"
)

_PROJECTED_FIELDS = [
    "SupplierSiteId",
    "SupplierSite",
    "ProcurementBU",
    "ProcurementBUId",
]


async def search_suppliers_by_site_bu(
    client: FusionClient,
    supplier_id,
    business_unit: str,
    limit: int = 25,
) -> ToolResult:
    """Fetch one supplier's sites in a given ProcurementBU.

    Called once per parent supplier by the executor. A non-empty result
    means the supplier has at least one site in that BU (keep the parent).

    Args:
        supplier_id: The SupplierId of the parent supplier to check.
        business_unit: Exact ProcurementBU display string, e.g.
            "US1 Business Unit". Matched server-side via q= on the child.
        limit: Max site records to return (existence is what matters, but
            we return the matches for transparency).

    Returns:
        ToolResult whose items are the matching site dicts for this
        supplier. Empty items means no site in that BU.
    """
    path = SITES_PATH_TEMPLATE.format(supplier_id=supplier_id)
    params = {
        "onlyData": "true",
        "limit": limit,
        "fields": ",".join(_PROJECTED_FIELDS),
        "q": f"ProcurementBU='{business_unit}'",
    }
    response = await client.get(path, params=params)
    items = response.get("items", [])
    projected = [{k: item.get(k) for k in _PROJECTED_FIELDS} for item in items]

    return ToolResult.build(
        items=projected,
        limit_applied=limit,
        total_available=len(projected),
    )
