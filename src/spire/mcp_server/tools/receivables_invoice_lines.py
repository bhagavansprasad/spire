"""Receivables invoice lines tool: the line children of one AR invoice.

Lines are a child of the AR invoice record, at
/receivablesInvoices/{CustomerTransactionId}/child/receivablesInvoiceLines.
Each line carries its own identity (CustomerTransactionLineId, LineNumber),
a description, quantity/price, and the line amount.

This is the lines half of AR-invoice detail. The header is a separate tool
(get_receivables_invoice_by_id), composed by the KG/planner — the
invoice->lines join lives in the KG, not baked into one tool. Mirrors the PO
lines tool exactly in shape: per-parent child fetch keyed on the parent id in
the URL path.

POD QUIRK — a misspelled field
The line body exposes `TransacationBusinessCategory` — Oracle's own
misspelling ("Transacation", missing the second 's'). It must be requested
with the typo exactly as the pod spells it or `?fields=` drops it silently.
It is included in the projection below spelled the pod's way; do not
"correct" it.

Not-found: an unknown CustomerTransactionId 404s on the child path (same as
the other child paths on this pod), so this tool catches the 404 and returns
an empty ToolResult — "no lines for a non-existent invoice" — mirroring
get_purchase_order_lines' not-found contract. Non-404 errors are re-raised.
In the normal pipeline the header is fetched first, so this tool only runs
for a real invoice; the guard is defensive.

Returns a ToolResult (like the PO child tools) so callers can tell a
complete result from a capped subset.
"""

import httpx

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


# Child-lines path template; formatted with a CustomerTransactionId per call.
RECEIVABLES_INVOICE_LINES_PATH_TEMPLATE = (
    "/fscmRestApi/resources/11.13.18.05/receivablesInvoices"
    "/{customer_transaction_id}/child/receivablesInvoiceLines"
)

_PROJECTED_FIELDS = [
    "CustomerTransactionLineId",
    "LineNumber",
    "Description",
    "Quantity",
    "UnitSellingPrice",
    "LineAmount",
    "UnitOfMeasure",
    "ItemNumber",
    "TaxClassificationCode",
    "TaxExemptionHandling",
    "LineAmountIncludesTax",
    "AssessableValue",
    # Oracle's own misspelling — must match the pod exactly (see docstring).
    "TransacationBusinessCategory",
]


async def get_receivables_invoice_lines(
    client: FusionClient,
    customer_transaction_id,
    limit: int = 25,
) -> ToolResult:
    """Fetch the lines of one AR invoice.

    Args:
        customer_transaction_id: The CustomerTransactionId of the parent
            invoice, e.g. 300000248096352.
        limit: Max line records to return. An invoice's line count is
            normally small; the default of 25 covers typical invoices.

    Returns:
        ToolResult whose items are the projected line dicts for this
        invoice, in the order Fusion returns them. Empty items means the
        invoice has no lines (or the id did not resolve).
    """
    path = RECEIVABLES_INVOICE_LINES_PATH_TEMPLATE.format(
        customer_transaction_id=customer_transaction_id
    )
    params = {
        "onlyData": "true",
        "limit": limit,
        "fields": ",".join(_PROJECTED_FIELDS),
    }
    try:
        response = await client.get(path, params=params)
    except httpx.HTTPStatusError as exc:
        # An unknown CustomerTransactionId 404s on the child path. Treat that
        # as "no lines" (empty ToolResult), mirroring
        # get_receivables_invoice_by_id's not-found contract. Any other
        # status is a real error — re-raise it.
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
