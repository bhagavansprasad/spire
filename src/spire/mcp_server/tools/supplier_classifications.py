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
    classification: str | None = None,
    limit: int = 25,
) -> ToolResult:
    """Fetch a supplier's business classifications, optionally filtered.

    Serves two call shapes, both driven by the same edge
    (HAS_CLASSIFICATION, Supplier -> Classification):

    - FILTER path (edge-traversal filter `has_classification`): executor
      passes a `classification` value; server-side q= filters; a non-empty
      result keeps the parent supplier.
    - INCLUDE path (Block 3 include on a Supplier target): executor passes
      only `supplier_id`; the tool returns ALL classifications for that
      supplier. F-043: previously `classification` was required, so the
      include path raised TypeError and a Classification-include intent
      refused before dispatch.

    Args:
        supplier_id: The SupplierId of the parent supplier.
        classification: Optional exact Classification display string, e.g.
            "Small Business". When provided, filters server-side via q=.
            When None/empty, no q= clause is sent and all classifications
            are returned.
        limit: Max classification records to return.

    Returns:
        ToolResult whose items are the matching classification dicts for
        this supplier. Empty items means no classifications matched.
    """
    path = CLASSIFICATIONS_PATH_TEMPLATE.format(supplier_id=supplier_id)
    params = {
        "onlyData": "true",
        "limit": limit,
        "fields": ",".join(_PROJECTED_FIELDS),
    }
    if classification:
        params["q"] = f"Classification='{classification}'"
    response = await client.get(path, params=params)
    items = response.get("items", [])
    # F-043: stamp the parent SupplierId onto each classification row —
    # the child body does not carry it; the synthesizer groups by it.
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
