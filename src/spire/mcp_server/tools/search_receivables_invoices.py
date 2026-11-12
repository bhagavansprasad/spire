"""AR invoice search tool — the filter-less fetcher.

Fetches from /receivablesInvoices, the top-level AR-invoice collection.
The ONLY AR-invoice fetcher on master before this is
receivables_invoice_by_id.py, which is reached only by `by_id` — so a
prompt with no id (e.g. `get all AR invoices`) had no fetcher to reach.
This is that fetcher.

WHY FILTER-LESS
The Phase 3 sample-and-disclose sequence gives each sampleable entity a
plain-list path. Every other entity already has one (PurchaseOrder's
`search_purchase_orders` with no filters, Invoice's `search_invoices`
with no filters, Supplier's `search_suppliers` with no filters,
StandardReceipt via the site filter's cap, CreditMemo's
`list_receivables_credit_memos`). ReceivablesInvoice had no such path
and is the sixth entity in the sequence. The filter-less fetcher is the
missing half; the narrowing filters (by customer, by date, by status)
would be a separate PR — this one exists to sample the entity so a
plain-list query has an answer at all.

WHY `orderBy=TransactionDate:desc`
The fetcher's job is to return the newest N AR invoices, deterministically.
Without an `orderBy` the pod returns an arbitrary page; two identical
calls can return different rows. `TransactionDate:desc` is server-side
orderable on this pod (confirmed live via the same order key CreditMemo
uses — see receivables_credit_memos.py) and matches the "recent AR
invoices" reading the SME would give the prompt.

WHY `totalResults=true`
Without it the pod returns `count`, which is the PAGE size, not the
collection total — a page of 25 reports a "total" of 25, indistinguishable
from a complete fetch. `totalResults=true` reads the collection count
onto the response; the wrapper then lifts it onto `ToolResult.total_available`
so the synthesizer can say "Showing 25 of 1,343 AR invoices" honestly.

The projection copies `receivables_invoice_by_id.py`'s `_PROJECTED_FIELDS`
exactly: same header fields, same order, so a plain-list row is
byte-identical to a by-id row of the same invoice. That is a contract,
not a coincidence — the synthesizer's `ReceivablesInvoiceRecord` builder
reads the same keys off both fetchers, and a mismatch would produce a
row with missing fields that the schema validator cannot see (it only
checks ids).

Returns a ToolResult so a caller can distinguish a complete fetch from
a capped page. The same shape as every other filter-less fetcher in this
codebase.
"""

import httpx

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


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


async def search_receivables_invoices(
    client: FusionClient,
    limit: int = 25,
) -> ToolResult:
    """List recent AR invoices, newest first, filter-less.

    The sixth entity in the Phase 3 sample-and-disclose sequence. Called
    with no filters (the only call shape — this is the filter-less
    fetcher, by design), it returns up to `limit` AR invoices ordered by
    TransactionDate descending, plus the collection total on
    `total_available`.

    Args:
        limit: Max invoice records to return. Default 25 — the sample size
            the SME's own framing named ("print the first 25"). Ordered
            server-side, so this is a true top-N of the newest invoices,
            not a page slice.

    Returns:
        ToolResult whose items are the projected AR-invoice dicts, newest
        first. Empty items means the pod has no AR invoices. total_available
        is the pod's own count for the collection (from totalResults),
        NOT the number returned — so a caller can honestly say
        "25 of 1,343" rather than "25 AR invoices".
    """
    params = {
        "onlyData": "true",
        "orderBy": "TransactionDate:desc",
        "limit": limit,
        "totalResults": "true",
        "fields": ",".join(_PROJECTED_FIELDS),
    }
    try:
        response = await client.get(RECEIVABLES_INVOICES_PATH, params=params)
    except httpx.HTTPStatusError as exc:
        # A 404 on a top-level list is unexpected, but treat it as "no
        # invoices" rather than crashing. Any other status is a real
        # error — re-raise it.
        if exc.response.status_code == 404:
            return ToolResult.build(
                items=[], limit_applied=limit, total_available=0
            )
        raise

    items = response.get("items", [])
    projected = [{k: item.get(k) for k in _PROJECTED_FIELDS} for item in items]

    # The pod's own count for this collection. Without it, total_available
    # equals the returned row count, ToolResult.build computes
    # `total_available > len(items)` as false, and the result claims
    # nothing was truncated — so a capped slice is indistinguishable from
    # a complete answer. Falls back to the row count when the endpoint
    # omits totalResults: an honest floor, not an invented total.
    total_available = response.get("totalResults")
    if not isinstance(total_available, int):
        total_available = len(projected)

    return ToolResult.build(
        items=projected,
        limit_applied=limit,
        total_available=total_available,
    )
