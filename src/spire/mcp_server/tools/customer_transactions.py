"""Customer transactions for one receivables account.

Fetches the transactionPaymentSchedules child of a customer account and
returns the invoice rows, filtered client-side. This is the SECOND half of
the customer-invoices flow (prompts 1 and 15): after
get_customer_account_by_name resolves the customer to account(s), this
reads each account's transactions.

CLIENT-SIDE FILTERING — why
TransactionClass is NOT queryable on this pod (confirmed live; see the
endpoints reference's non-queryable list), so the class filter cannot go in
q=. The child also carries no server-side balance filter we can rely on.
Both filters are therefore applied client-side after fetching:
- ALWAYS keep TransactionClass == 'Invoice' (the collection also holds
  credit memos and other classes; prompts 1 and 15 are about invoices).
- WHEN open_only: additionally keep TotalBalanceAmount > 0. "Open" means
  money still owed; a zero balance is paid, and a negative balance is a
  credit (this pod has customers in credit), neither of which is an open
  invoice.

VOLUME
One account can carry thousands of schedule rows (the ABC Corporation
Americas account has 7,404). Client-side filtering must over-fetch: the
tool pulls up to `fetch_limit` rows from the pod, filters them, then
applies the caller's `limit` to the filtered result. A caller wanting "top
5 open" (prompt 1) still needs enough raw rows fetched to find 5 open ones,
hence fetch_limit defaults well above the display limit.

NOTE these rows are payment schedules/installments, not the ReceivablesInvoice
entity (Shape A): different id space (TransactionId, small ints, vs
CustomerTransactionId) and different fields (TotalOriginalAmount/
TotalBalanceAmount vs EnteredAmount/InvoiceBalanceAmount).

Returns a ToolResult whose items are the filtered transaction dicts.
"""

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


# Child path template; formatted with an AccountId per call.
CUSTOMER_TRANSACTIONS_PATH_TEMPLATE = (
    "/fscmRestApi/resources/11.13.18.05/receivablesCustomerAccountActivities"
    "/{account_id}/child/transactionPaymentSchedules"
)

_PROJECTED_FIELDS = [
    "TransactionId",
    "TransactionNumber",
    "TransactionClass",
    "TransactionDate",
    "PaymentScheduleDueDate",
    "TotalOriginalAmount",
    "TotalBalanceAmount",
    "InstallmentStatus",
]


async def get_customer_transactions(
    client: FusionClient,
    account_id,
    open_only: bool = False,
    limit: int = 25,
    fetch_limit: int = 500,
) -> ToolResult:
    """Fetch one account's invoice transactions, filtered client-side.

    Args:
        account_id: The AccountId of the customer account (from
            get_customer_account_by_name).
        open_only: When True, keep only invoices with a positive open
            balance (TotalBalanceAmount > 0). When False, keep all
            Invoice-class rows.
        limit: Max transactions to return AFTER filtering (the caller's
            display cap, e.g. 5 for "top 5 open").
        fetch_limit: Max raw rows to pull from the pod BEFORE filtering.
            Larger than `limit` because filtering discards non-invoice and
            (when open_only) paid rows; defaults high enough to find enough
            matches on large accounts.

    Returns:
        ToolResult whose items are the filtered transaction dicts, capped at
        `limit`. total_available is the filtered count (before the cap).
    """
    path = CUSTOMER_TRANSACTIONS_PATH_TEMPLATE.format(account_id=account_id)
    params = {
        "onlyData": "true",
        "limit": fetch_limit,
        "fields": ",".join(_PROJECTED_FIELDS),
    }
    response = await client.get(path, params=params)
    items = response.get("items", [])

    # Client-side filter: Invoice class always; positive balance when open.
    filtered = []
    for item in items:
        if item.get("TransactionClass") != "Invoice":
            continue
        if open_only:
            balance = item.get("TotalBalanceAmount")
            if balance is None or balance <= 0:
                continue
        filtered.append({k: item.get(k) for k in _PROJECTED_FIELDS})

    total_filtered = len(filtered)
    capped = filtered[:limit]

    return ToolResult.build(
        items=capped,
        limit_applied=limit,
        total_available=total_filtered,
    )
