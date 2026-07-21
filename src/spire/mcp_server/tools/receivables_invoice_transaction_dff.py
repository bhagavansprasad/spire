"""Receivables invoice TransactionDFF tool: the transaction descriptive
flexfield child of one AR invoice.

The DFF is a child of the AR invoice record, at
/receivablesInvoices/{CustomerTransactionId}/child/receivablesInvoiceTransactionDFF.
It carries the descriptive-flexfield context and (when configured) its
segment values for the invoice.

TWO DFF CHILDREN — why this one
AR invoices expose two DFF children: `receivablesInvoiceDFF` and
`receivablesInvoiceTransactionDFF` (endpoints-reference quirk 8). Curled
2026-07-21 on invoice 1002: the plain `receivablesInvoiceDFF` returns
`__FLEX_Context = null`, while `receivablesInvoiceTransactionDFF` returns
`__FLEX_Context = "DOO"`. So this tool targets the TransactionDFF child —
the populated one on this pod — which is what prompt 4 ("Fetch DFF values
for this invoice") wants.

POD QUIRK — a context label, not segment values
On this demo pod the "DOO" context is SET but carries NO populated segment
columns. The child row exposes only `CustomerTrxId`, `__FLEX_Context`, and
`__FLEX_Context_DisplayValue` (null). There are no `attribute*`/`_FLEX_*`
segment columns to project. If a future pod configures segments under the
context, extend `_PROJECTED_FIELDS` after confirming the names by curl —
`?fields=` drops any name that doesn't exist on the endpoint (quirk 7).

Note the id field spelling: the DFF child echoes the parent id as
`CustomerTrxId` (short form), NOT the `CustomerTransactionId` used on the
invoice header and lines. Match the pod's spelling exactly.

Not-found: an unknown CustomerTransactionId 404s on the child path (same as
the other AR child paths on this pod), so this tool catches the 404 and
returns an empty ToolResult, mirroring get_receivables_invoice_lines'
not-found contract. Non-404 errors are re-raised. In the normal pipeline
the header is fetched first, so this tool only runs for a real invoice; the
guard is defensive.

Returns a ToolResult (like the other AR child tools) so callers can tell a
complete result from a capped subset.
"""

import httpx

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


# Child-DFF path template; formatted with a CustomerTransactionId per call.
RECEIVABLES_INVOICE_TRANSACTION_DFF_PATH_TEMPLATE = (
    "/fscmRestApi/resources/11.13.18.05/receivablesInvoices"
    "/{customer_transaction_id}/child/receivablesInvoiceTransactionDFF"
)

_PROJECTED_FIELDS = [
    # The DFF child echoes the parent id as CustomerTrxId (short form) —
    # NOT CustomerTransactionId. Match the pod spelling exactly.
    "CustomerTrxId",
    "__FLEX_Context",
    "__FLEX_Context_DisplayValue",
]


async def get_receivables_invoice_transaction_dff(
    client: FusionClient,
    customer_transaction_id,
    limit: int = 25,
) -> ToolResult:
    """Fetch the transaction DFF of one AR invoice.

    Args:
        customer_transaction_id: The CustomerTransactionId of the parent
            invoice, e.g. 1002.
        limit: Max DFF records to return. An invoice has a single DFF row;
            the default of 25 is a safe ceiling.

    Returns:
        ToolResult whose items are the projected DFF dicts for this invoice
        (normally one row). Empty items means the id did not resolve.
    """
    path = RECEIVABLES_INVOICE_TRANSACTION_DFF_PATH_TEMPLATE.format(
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
        # as "no DFF" (empty ToolResult), mirroring
        # get_receivables_invoice_lines' not-found contract. Any other
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
