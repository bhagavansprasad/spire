"""Tax lines for one AR invoice line.

Fetches the receivablesInvoiceLineTaxLines grandchild of an AR invoice — the
tax breakdown (jurisdiction, rate, amount) for a single invoice line. This is
the leaf of the invoice -> line -> taxLines chain (prompt 3).

TWO-ID PATH, SINGLE-PARENT FETCH
The tax lines hang three levels deep, but the fetch needs only TWO ids: the
invoice CustomerTransactionId and the parent line's CustomerTransactionLineId,
both in the URL path. Unlike PO distributions (three sibling ids from one
schedule row, via the HAS_DISTRIBUTION iter_fields branch), the only id needed
beyond the invoice is the line id — which the parent line row already carries.
So this tool stays single-parent, exactly like get_receivables_invoice_lines:
one line id in, that line's tax lines out. Looping an invoice's lines to reach
every line's tax lines is the executor's job (invoice -> lines, then each line
-> its tax lines as chained single-parent iterations), not this tool's.

ID CAUTION
A tax-line row carries its OWN CustomerTransactionLineId (the tax line's PK,
e.g. 112) — a DIFFERENT value from the parent invoice-line id (e.g. 74) passed
in as line_id. Both are projected; don't confuse them.

Untaxed lines return an empty collection (count:0), not a 404 — an untaxed
line (e.g. a plain "Consultation" line) simply has no tax rows.

Returns a ToolResult whose items are the projected tax-line dicts.
"""

import httpx

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


# Grandchild tax-lines path template; formatted with the parent invoice
# CustomerTransactionId and the parent line CustomerTransactionLineId per call.
RECEIVABLES_INVOICE_TAX_LINES_PATH_TEMPLATE = (
    "/fscmRestApi/resources/11.13.18.05/receivablesInvoices"
    "/{customer_transaction_id}/child/receivablesInvoiceLines"
    "/{line_id}/child/receivablesInvoiceLineTaxLines"
)

_PROJECTED_FIELDS = [
    "TaxLineNumber",
    "TaxJurisdictionCode",
    "TaxRate",
    "TaxRateCode",
    "TaxRegimeCode",
    "TaxStatusCode",
    # The tax type, e.g. "COUNTY" / "STATE".
    "Tax",
    "TaxAmount",
    "TaxableAmount",
    "TaxInclusiveIndicator",
    "TaxPointDate",
    # The tax line's OWN PK — distinct from the parent line_id (see docstring).
    "CustomerTransactionLineId",
]


async def get_receivables_invoice_tax_lines(
    client: FusionClient,
    customer_transaction_id,
    line_id,
    limit: int = 25,
) -> ToolResult:
    """Fetch the tax lines of one AR invoice line.

    Args:
        customer_transaction_id: The CustomerTransactionId of the parent
            invoice, e.g. 1002.
        line_id: The CustomerTransactionLineId of the parent invoice line,
            e.g. 74. This is the parent line's PK, NOT the tax line's.
        limit: Max tax-line records to return. A line's tax-line count is
            small (typically 1-2); the default of 25 covers any line.

    Returns:
        ToolResult whose items are the projected tax-line dicts for this
        line, in the order Fusion returns them. Empty items means the line
        has no tax lines (an untaxed line), or the ids did not resolve.
    """
    path = RECEIVABLES_INVOICE_TAX_LINES_PATH_TEMPLATE.format(
        customer_transaction_id=customer_transaction_id,
        line_id=line_id,
    )
    params = {
        "onlyData": "true",
        "limit": limit,
        "fields": ",".join(_PROJECTED_FIELDS),
    }
    try:
        response = await client.get(path, params=params)
    except httpx.HTTPStatusError as exc:
        # An unknown invoice/line id 404s on the grandchild path. Treat that
        # as "no tax lines" (empty ToolResult), mirroring
        # get_receivables_invoice_lines's not-found contract. Any other
        # status is a real error — re-raise it.
        if exc.response.status_code == 404:
            return ToolResult.build(
                items=[], limit_applied=limit, total_available=0
            )
        raise

    items = response.get("items", [])
    projected = [{k: item.get(k) for k in _PROJECTED_FIELDS} for item in items]
    # Stamp the parent line id onto each tax row under a DISTINCT name. The
    # tax row's own CustomerTransactionLineId is the TAX line's PK (e.g. 112),
    # NOT the parent line's (e.g. 74) — so the parent link would collide with
    # that field if reused. Emitting it under ParentCustomerTransactionLineId
    # gives the synthesizer an unambiguous key to nest each tax line under its
    # invoice line. line_id is exactly that parent id (it's how we fetched).
    for row in projected:
        row["ParentCustomerTransactionLineId"] = line_id

    return ToolResult.build(
        items=projected,
        limit_applied=limit,
        total_available=len(projected),
    )
