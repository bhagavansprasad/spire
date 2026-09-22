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
one clause silently returns empty), so the server-side filter is on
Classification ONLY. The currency filter runs client-side after the
response, over the rows the pod already narrowed.

F-008: on the FILTER path (a classification value was given), rows
whose Status is not "CURRENT" are dropped. "Suppliers with classification
X" is naturally read as "currently certified X", and on this pod a
supplier can carry an EXPIRED classification of the same name — returning
it as a match asserts a currency the data does not support.

On the INCLUDE path (no classification value — F-043's "show
classifications for supplier X"), the filter is NOT applied: the user
asked to see the supplier's classifications, and the row's own Status
field ("CURRENT" / "EXPIRED") is information they asked for. Filtering
the display would hide it.

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


# The pod's currency value on a businessClassifications row. Observed
# statuses on this pod: "CURRENT" and "EXPIRED". Any other value is
# treated as not-current.
_CURRENT_STATUS = "CURRENT"


def _filter_to_current(items: list[dict]) -> list[dict]:
    """Keep only classification rows whose Status is CURRENT.

    Pure: no I/O. The pod's single-clause q= rule forbids ANDing
    Classification AND Status in one query, so the currency filter is
    applied here, over the rows the server already filtered by
    Classification.

    A row whose Status is missing is DROPPED, not treated as current.
    The pod always returns Status on this child; a missing Status is
    a malformed row, and treating it as CURRENT would re-introduce
    the exact defect this function exists to close.
    """
    return [i for i in items if i.get("Status") == _CURRENT_STATUS]


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

    # F-008: on the FILTER path, drop rows that are not CURRENT. The
    # pod's single-clause rule forbids ANDing Classification AND Status
    # in one q=, so the currency test runs here, client-side. A supplier
    # whose matching classification has lapsed is not a match for
    # "has classification X" — that phrase is read as "currently
    # certified X". Rows keep their own Status field, so a caller that
    # wants to surface "the match is EXPIRED" can still see it.
    #
    # NOT applied on the INCLUDE path (no classification value): the
    # user asked to SEE the supplier's classifications, and the Status
    # of each row is information they asked for. Hiding expired rows
    # would hide data.
    if classification:
        items = _filter_to_current(items)

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
