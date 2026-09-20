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
    business_unit: str | None = None,
    limit: int = 25,
) -> ToolResult:
    """Fetch a supplier's sites, optionally filtered by ProcurementBU.

    Serves two call shapes, both driven by the same edge (HAS_SITE,
    Supplier -> Site):

    - FILTER path (edge-traversal filter `has_site_in_bu`): executor passes
      a `business_unit` value; the pod filters server-side via single-clause
      q=, and a non-empty result keeps the parent supplier.
    - INCLUDE path (Block 3 include on a Supplier target): executor passes
      only `supplier_id`; the tool returns ALL sites for that supplier with
      no server filter. This is F-043: previously the tool required
      `business_unit`, so the include path raised TypeError, and a
      Site-include intent refused before dispatch.

    Args:
        supplier_id: The SupplierId of the parent supplier.
        business_unit: Optional exact ProcurementBU display string, e.g.
            "US1 Business Unit". When provided, filters server-side via q=.
            When None/empty, no q= clause is sent and all sites are returned.
        limit: Max site records to return.

    Returns:
        ToolResult whose items are the matching site dicts for this
        supplier. Empty items means no sites matched (either no sites at
        all, or none in the requested BU).
    """
    path = SITES_PATH_TEMPLATE.format(supplier_id=supplier_id)
    params = {
        "onlyData": "true",
        "limit": limit,
        "fields": ",".join(_PROJECTED_FIELDS),
    }
    if business_unit:
        params["q"] = f"ProcurementBU='{business_unit}'"
    response = await client.get(path, params=params)
    items = response.get("items", [])
    # F-043: stamp the parent SupplierId onto each site row. The pod's
    # child body does NOT carry it (the endpoint knows the parent only
    # from the URL path), so without this the join key is lost the
    # moment the executor unwraps the ToolResult. build_suppliers_with_sites
    # groups site rows back to their supplier by this key.
    projected = [
        {
            **{k: item.get(k) for k in _PROJECTED_FIELDS},
            "SupplierId": supplier_id,
        }
        for item in items
    ]

    return ToolResult.build(
        items=projected,
        limit_applied=limit,
        total_available=len(projected),
    )
