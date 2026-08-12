"""Receivables invoice header lookup tool.

Fetches ONE AR invoice by its CustomerTransactionId and returns its header.

WHY SINGLE-PATH (unlike get_purchase_order_by_id)
The PO header tool resolves two identifiers — OrderNumber (a string a user
reads off a document) vs POHeaderId (the system id) — because a bare number
in a PO prompt is ambiguous. AR's P2 prompts are not ambiguous that way: the
two detail prompts both name the CustomerTransactionId explicitly, e.g. "the
AR invoice with CustomerTransactionId 300000248096352". So this tool takes a
single numeric id and does one lookup. TransactionNumber resolution (the AR
analogue of OrderNumber, e.g. "invoice 61765") is deliberately NOT baked in —
no P2 prompt needs it, and the PO tool's history shows how easily unused
resolution paths hide bugs. Add it only when a prompt demands it.

THE FILTER
q=CustomerTransactionId=<id> on the /receivablesInvoices collection.
CustomerTransactionId is numeric on the pod, so the clause is unquoted —
confirmed live: the probe q=CustomerTransactionId=300000248096352 returned
exactly the one invoice (totalResults=1). Note the pod's other AR quirks
surfaced during discovery: BillToCustomerName and BillToCustomerNumber are
NOT queryable via q= (a customer's invoices come via the account-activity
path, not this endpoint — that is Shape B / a separate tool). The PK,
however, IS queryable, which is what this tool relies on.

Returns a single dict (not a list), mirroring get_purchase_order_by_id and
get_buyer, since a CustomerTransactionId resolves to at most one invoice.
Returns None when the id matches nothing.

Not-found: the COLLECTION path returns empty items for a non-match (not a
404). Handled as None.

This is the header half of AR-invoice detail. Lines are a separate tool
(receivables_invoice_lines), composed by the KG/planner — the invoice->lines
join lives in the KG, not baked into one tool.
"""

from spire.fusion.client import FusionClient


RECEIVABLES_INVOICES_PATH = (
    "/fscmRestApi/resources/11.13.18.05/receivablesInvoices"
)

_PROJECTED_FIELDS = [
    "CustomerTransactionId",
    "TransactionNumber",
    "BillToCustomerName",
    "BillToCustomerNumber",
    "InvoiceCurrencyCode",
    "EnteredAmount",
    "InvoiceBalanceAmount",
    "TransactionDate",
    "DueDate",
    "AccountingDate",
    "InvoiceStatus",
    "TransactionType",
    "TransactionSource",
    "BusinessUnit",
    "CreatedBy",
    "CreationDate",
    "LastUpdatedBy",
    "LastUpdateDate",
]


def _project(source: dict) -> dict:
    return {k: source.get(k) for k in _PROJECTED_FIELDS}


async def get_receivables_invoice_by_id(
    client: FusionClient, customer_transaction_id
) -> dict | None:
    """Look up one AR invoice by its CustomerTransactionId.

    Args:
        customer_transaction_id: The CustomerTransactionId of the invoice,
            e.g. 300000248096352. Numeric; the pod's PK for the invoice.

    Returns:
        Dict with the projected AR invoice header fields, or None if the id
        matches no invoice.
    """
    params = {
        "onlyData": "true",
        "q": f"CustomerTransactionId={customer_transaction_id}",
        "fields": ",".join(_PROJECTED_FIELDS),
        "limit": 1,
    }
    response = await client.get(RECEIVABLES_INVOICES_PATH, params=params)
    items = response.get("items", [])
    if not items:
        return None
    return _project(items[0])
