"""AP invoice lines tool: the line children of one payables invoice.

Lines are a child of the AP invoice record, at
/invoices/{InvoiceId}/child/invoiceLines. Each line carries a line number, a
description, quantity/price, the line amount and a line type.

This is the lines half of AP-invoice detail. The header is a separate tool
(get_purchase_order_lines / search_invoices), composed by the KG/planner —
the invoice->lines join lives in the KG, not baked into one tool. Mirrors the
AR and PO lines tools exactly in shape: per-parent child fetch keyed on the
parent id in the URL path.

WHY THIS TOOL EXISTS (F-077)
Before it, an "invoice lines for <AP invoice>" prompt was refused with
"the InvoiceLine entity is not available in the API schema". That assertion
was false: this child resource returns every field such a prompt asks for.
The refusal happened because no AP line entity existed in the KG, and the
prompt was additionally misrouted to `receivables` (whose own line entity
does exist). Both halves had to be fixed; see docs/fixes/FIX_PLAN.md F-077.

PATH CAVEAT — the child segment is `invoiceLines`, not `lines`
`/invoices/{id}/child/lines` returns 404 on this pod. `invoiceLines` is the
only correct segment. Verified on dev49 against invoice 1601397.

NOT-FOUND AND EMPTY ARE THE SAME SHAPE
An unknown InvoiceId 404s on the child path (same as the other child paths on
this pod), so this tool catches the 404 and returns an empty ToolResult — "no
lines for a non-existent invoice" — mirroring get_purchase_order_lines'
not-found contract. Non-404 errors are re-raised. In the normal pipeline the
header is fetched first, so this tool only runs for a real invoice; the guard
is defensive.

Returns a ToolResult (like the other child tools) so callers can tell a
complete result from a capped subset.
"""

import httpx

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


# Child-lines path template; formatted with an InvoiceId per call.
INVOICE_LINES_PATH_TEMPLATE = (
    "/fscmRestApi/resources/11.13.18.05/invoices"
    "/{invoice_id}/child/invoiceLines"
)

# The six fields the F-077 prompt names, plus the identity and the handful of
# columns the KG projects on this entity. Kept in the order the answer reads.
_PROJECTED_FIELDS = [
    "LineNumber",
    "Description",
    "Quantity",
    "UnitPrice",
    "LineAmount",
    "LineType",
    "ItemDescription",
    "UOM",
    "AccountingDate",
    "AssessableValue",
]


async def get_invoice_lines(
    client: FusionClient,
    invoice_id,
    limit: int = 50,
) -> ToolResult:
    """Fetch the lines of one AP (payables) invoice.

    Args:
        invoice_id: The InvoiceId of the parent AP invoice, e.g. 1601397.
            This is the numeric id, NOT the invoice number — the KG edge
            supplies it from the resolved header.
        limit: Max line records to return. An AP invoice can carry many
            lines (tax auto-lines included): invoice 1601397 has 184. Callers
            that need every line must pass a limit at or above the count.

    Returns:
        ToolResult whose items are the projected line dicts for this
        invoice, in the order Fusion returns them. Empty items means the
        invoice has no lines (or the id did not resolve).
    """
    path = INVOICE_LINES_PATH_TEMPLATE.format(invoice_id=invoice_id)
    params = {
        "onlyData": "true",
        "limit": limit,
        "fields": ",".join(_PROJECTED_FIELDS),
    }
    try:
        response = await client.get(path, params=params)
    except httpx.HTTPStatusError as exc:
        # An unknown InvoiceId 404s on the child path. Treat that as "no
        # lines" (empty ToolResult), mirroring search_invoices' not-found
        # contract. Any other status is a real error — re-raise it.
        if exc.response.status_code == 404:
            return ToolResult.build(
                items=[], limit_applied=limit, total_available=0
            )
        raise

    items = response.get("items", [])
    projected = [{k: item.get(k) for k in _PROJECTED_FIELDS} for item in items]

    return ToolResult.build(
        items=projected,
        limit_applied=limit,
        total_available=len(projected),
    )
