"""Supplier contacts tool: the contact people of one supplier.

Contacts are a child of the supplier record, at
/suppliers/{SupplierId}/child/contacts. Each contact has a name, email,
optional job title, a status, and an administrative-contact flag marking
the primary contact.

Like the other supplier children (sites, businessClassifications), the
contact body from Fusion does NOT carry the parent SupplierId — the join
key lives in the URL path. So this is a per-supplier child call: one HTTP
call per supplier, mirroring supplier_sites / supplier_classifications.
To preserve the join key past the executor's unwrap, this tool STAMPS the
parent SupplierId onto every returned contact row (see the projection
below), so a multi-supplier contacts query can group contacts back to
their supplier locally instead of via the LLM.

This is an include-only expansion (used by the HAS_CONTACT edge to attach
a supplier's contacts to a supplier fetch), not a filter. There is no
"suppliers that have a contact matching X" filter in scope.

Not-found: an unknown SupplierId 404s on the child path, so this tool
catches the 404 and returns an empty ToolResult ("no contacts for a
non-existent supplier"). Non-404 errors are re-raised. In the normal
pipeline the supplier is fetched first, so this tool only runs for a real
supplier; the guard is defensive.

Returns a ToolResult (like the other supplier-child tools) so callers can
tell a complete result from a capped subset.
"""

import httpx

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


# Child-contacts path template; formatted with a SupplierId per call.
SUPPLIER_CONTACTS_PATH_TEMPLATE = (
    "/fscmRestApi/resources/11.13.18.05/suppliers"
    "/{supplier_id}/child/contacts"
)

_PROJECTED_FIELDS = [
    "SupplierContactId",
    "ContactName",
    "FirstName",
    "LastName",
    "Email",
    "JobTitle",
    "Status",
    "AdministrativeContactFlag",
]


async def get_supplier_contacts(
    client: FusionClient,
    supplier_id,
    limit: int = 25,
) -> ToolResult:
    """Fetch the contacts of one supplier.

    Args:
        supplier_id: The SupplierId of the parent supplier, e.g.
            300000047507499.
        limit: Max contact records to return. The default of 25 covers
            typical suppliers.

    Returns:
        ToolResult whose items are the projected contact dicts for this
        supplier, in the order Fusion returns them. Empty items means the
        supplier has no contacts (or the id did not resolve).
    """
    path = SUPPLIER_CONTACTS_PATH_TEMPLATE.format(supplier_id=supplier_id)
    params = {
        "onlyData": "true",
        "limit": limit,
        "fields": ",".join(_PROJECTED_FIELDS),
    }
    try:
        response = await client.get(path, params=params)
    except httpx.HTTPStatusError as exc:
        # An unknown SupplierId 404s on the child path. Treat that as "no
        # contacts" (empty ToolResult). Any other status is a real error.
        if exc.response.status_code == 404:
            return ToolResult.build(
                items=[], limit_applied=limit, total_available=0
            )
        raise

    items = response.get("items", [])
    # Stamp the parent SupplierId onto each contact row. The contact body
    # itself does NOT carry it (the child endpoint knows the parent only
    # from the path), so without this the join key is lost the moment the
    # executor unwraps the ToolResult to a flat items list — a multi-supplier
    # "contacts for suppliers in US" could not group contacts back to their
    # supplier. Stamping the scalar we already hold (supplier_id) onto every
    # row is the documented fix for exactly this unwrap.
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
