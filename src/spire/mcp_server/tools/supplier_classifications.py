"""Supplier-classification edge tool: does one supplier have a given
business classification?

Classifications are a child of the supplier record, at
/suppliers/{SupplierId}/child/businessClassifications. Each carries a
Classification (display string, e.g. "Small Business"), a
ClassificationCode ("SMALL_BUSINESS"), a Status ("CURRENT"), and a
CertifyingAgency ("SBA"). Classification filters reliably server-side on
this child (confirmed on pod: a matching value returns the row, a
non-existent value returns empty).

This is an EDGE tool, called once per parent supplier by the executor's
keep-parent-when-nonempty path (mirror of search_suppliers_by_site_bu for
has_site_in_bu). It takes ONE supplier_id plus the target classification,
and returns that supplier's matching classifications. A non-empty result
tells the executor to keep the parent supplier.

Status note: the pod rejects composite q= (Classification AND Status in
one clause silently returns empty), so this tool filters on Classification
ONLY and does not constrain Status. A supplier with a lapsed classification
still matches. "Current only" would require a client-side Status pass; not
done here (no prompt requires it yet).

The whole-pod scan is NOT here — the executor does the iteration across
suppliers. This tool only answers the per-supplier question.
"""

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


# Child-classifications path template; formatted with a SupplierId per call.
CLASSIFICATIONS_PATH_TEMPLATE = (
    "/fscmRestApi/resources/11.13.18.05/suppliers/{supplier_id}"
    "/child/businessClassifications"
)

_PROJECTED_FIELDS = [
    "ClassificationId",
    "Classification",
    "ClassificationCode",
    "Status",
    "CertifyingAgency",
]


async def search_suppliers_by_classification(
    client: FusionClient,
    supplier_id,
    classification: str,
    limit: int = 25,
) -> ToolResult:
    """Fetch one supplier's business classifications matching a value.

    Called once per parent supplier by the executor. A non-empty result
    means the supplier has at least one matching classification (keep the
    parent).

    Args:
        supplier_id: The SupplierId of the parent supplier to check.
        classification: Exact Classification display string, e.g.
            "Small Business". Matched server-side via q= on the child.
        limit: Max classification records to return (existence is what
            matters, but we return the matches for transparency).

    Returns:
        ToolResult whose items are the matching classification dicts for
        this supplier. Empty items means no matching classification.
    """
    path = CLASSIFICATIONS_PATH_TEMPLATE.format(supplier_id=supplier_id)
    params = {
        "onlyData": "true",
        "limit": limit,
        "fields": ",".join(_PROJECTED_FIELDS),
        "q": f"Classification='{classification}'",
    }
    response = await client.get(path, params=params)
    items = response.get("items", [])
    projected = [{k: item.get(k) for k in _PROJECTED_FIELDS} for item in items]

    return ToolResult.build(
        items=projected,
        limit_applied=limit,
        total_available=len(projected),
    )
