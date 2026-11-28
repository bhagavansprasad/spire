"""Receivables invoice header lookup tool.

Fetches ONE AR invoice from whatever number the user gave — a
TransactionNumber or a CustomerTransactionId — and returns its header.

WHY THIS NOW RESOLVES BOTH SPACES (F-082)
This tool used to take a CustomerTransactionId only, on the argument that
the P2 prompts named it explicitly ("the AR invoice with
CustomerTransactionId 300000248096352"). The SME litmus run showed that
assumption was too narrow: "Get the complete details of AR invoice 112390"
supplies the *printed* number, this tool bound it to
CustomerTransactionId, and the answer was a confident "No AR invoices
found matching the criteria" for an invoice that exists
(CUSTOMER_TRX_ID=1533822, 240 lines, 180 tax lines).

The PO tool had already solved this exact problem — a bare number does not
say which space it is in — so this mirrors it:

  1. q=TransactionNumber='X' on the collection. Tried FIRST because the
     number is what a user reads off the invoice.
  2. q=CustomerTransactionId=X. Tried only if (1) found nothing.

Both clauses are quoted deliberately. TransactionNumber is a string
('112390', 'ERS-53004-755598'); CustomerTransactionId is numeric, and the
pod accepts it quoted as well — verified live, both return the one
invoice. Quoting both keeps a single code path for either identifier.

THE FILTER
Two cheap calls worst case, one in the common case. Note the pod's other
AR quirks surfaced during discovery: BillToCustomerName and
BillToCustomerNumber are NOT queryable via q= (a customer's invoices come
via the account-activity path, not this endpoint — that is Shape B / a
separate tool). The PK and TransactionNumber are, which is what this tool
relies on.

Returns a single dict (not a list), mirroring get_purchase_order_by_id and
get_buyer, since either identifier resolves to at most one invoice.
Returns None when neither lookup finds anything.

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


async def _lookup(client: FusionClient, clause: str) -> dict | None:
    """Run one collection query and project the first row, or None.

    A non-match on a collection returns empty items, not a 404, so an
    absent row and an unknown identifier are the same result here.
    """
    params = {
        "onlyData": "true",
        "q": clause,
        "fields": ",".join(_PROJECTED_FIELDS),
        "limit": 1,
    }
    response = await client.get(RECEIVABLES_INVOICES_PATH, params=params)
    items = response.get("items", [])
    if not items:
        return None
    return _project(items[0])


async def _try_transaction_number(client: FusionClient, value) -> dict | None:
    """Look the value up as a TransactionNumber (what the user reads)."""
    return await _lookup(client, f"TransactionNumber='{value}'")


async def _try_customer_transaction_id(
    client: FusionClient, value
) -> dict | None:
    """Look the value up as the numeric CustomerTransactionId."""
    return await _lookup(client, f"CustomerTransactionId='{value}'")


async def get_receivables_invoice_by_id(
    client: FusionClient, customer_transaction_id
) -> dict | None:
    """Look up one AR invoice by its number OR its customer transaction id.

    Tries TransactionNumber first (what a user reads off an invoice), then
    falls back to CustomerTransactionId. See the module docstring for why
    both are tried (F-082).

    Args:
        customer_transaction_id: The number the user gave — a
            TransactionNumber (e.g. "112390") or a CustomerTransactionId
            (e.g. 1533822). The arg name is historical; either identifier
            works.

    Returns:
        Dict with the projected AR invoice header fields, or None if
        neither lookup finds an invoice.
    """
    by_number = await _try_transaction_number(client, customer_transaction_id)
    if by_number is not None:
        return by_number
    return await _try_customer_transaction_id(client, customer_transaction_id)

