"""Credit memos for one receivables account.

Fetches the creditMemos child of a customer account and returns the memo
rows, newest first. This is the second half of the account-credit-memos
flow (prompt 7): after get_customer_account_by_name resolves the customer
to account(s), this reads each account's memos.

NOT THE SAME RESOURCE AS AR-P4 — the important distinction
Spire has two credit-memo fetchers and they are NOT interchangeable:
- receivables_credit_memos.py (AR-P4, prompts 5/14) reads the TOP-LEVEL
  /receivablesCreditMemos collection. Its PK is CustomerTransactionId — the
  SAME id space as AR invoices — and it carries TransactionNumber /
  TransactionDate / EnteredAmount.
- this tool reads the PER-ACCOUNT child. Its PK is CreditMemoId, a small
  int in a DIFFERENT id space, and it carries CreditMemoNumber /
  CreditMemoDate / TotalOriginalAmount / TotalBalanceAmount /
  AvailableAmount / InstallmentId.
The two describe the same business objects through different projections:
the child is the installment/payment-schedule view (hence InstallmentId and
the balance/available pair), a sibling of transactionPaymentSchedules, not
the transaction view. Confirmed live 2026-07-22; see the endpoints
reference. Do NOT assume an id from one resolves in the other.

NO CLIENT-SIDE FILTERING — why this is simpler than customer_transactions
The sibling tool (customer_transactions) must over-fetch and filter
client-side because TransactionClass is not queryable and the collection
mixes classes. This child holds credit memos ONLY, so there is nothing to
filter out: `limit` can be applied server-side directly and is a true
top-N. No fetch_limit, no post-filter.

SERVER-SIDE ORDERING
orderBy=CreditMemoDate:desc works on this child (confirmed live), and
matters: the anchor account carries 280 memos whose default order is
oldest-first (2012). Without the sort, "recent" memos would be the least
recent ones. ?fields= is also confirmed working here — unlike
/standardReceipts, where a projection 500s even with valid names.

VOLUME
280 memos on the anchor account (AccountId 300000047368512). The caller's
`limit` bounds the fetch; there is no path that pulls all of them.

STATUS
CreditMemoStatus is "Open" or "Closed"; open memos carry a non-zero
TotalBalanceAmount while closed ones sit at 0. Amounts are normally
negative, but do NOT assume it — the demo pod carries a positive memo on
the top-level resource, so treat the sign as data, not an invariant.

The row does NOT echo AccountId — the join key is the URL path only, the
established pattern for AR account children.

Returns a ToolResult whose items are the memo dicts.
"""

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


# Child path template; formatted with an AccountId per call.
ACCOUNT_CREDIT_MEMOS_PATH_TEMPLATE = (
    "/fscmRestApi/resources/11.13.18.05/receivablesCustomerAccountActivities"
    "/{account_id}/child/creditMemos"
)

_PROJECTED_FIELDS = [
    "CreditMemoId",
    "CreditMemoNumber",
    "CreditMemoDate",
    "TransactionClass",
    "TotalOriginalAmount",
    "TotalBalanceAmount",
    "AvailableAmount",
    "CreditMemoStatus",
    "CreditMemoCurrency",
    "BillToSiteNumber",
]


async def get_account_credit_memos(
    client: FusionClient,
    account_id,
    limit: int = 25,
) -> ToolResult:
    """Fetch one account's credit memos, newest first.

    Args:
        account_id: The AccountId of the customer account (from
            get_customer_account_by_name).
        limit: Max memos to return. Applied SERVER-SIDE alongside the
            date sort, so this is a true "N most recent" — no
            over-fetching is needed because the child holds credit memos
            only and nothing is filtered out client-side.

    Returns:
        ToolResult whose items are the memo dicts, newest first.
        total_available is the number returned (the pod's own
        totalResults is not requested, so this is not the account's full
        memo count).
    """
    path = ACCOUNT_CREDIT_MEMOS_PATH_TEMPLATE.format(account_id=account_id)
    params = {
        "onlyData": "true",
        "limit": limit,
        "orderBy": "CreditMemoDate:desc",
        "fields": ",".join(_PROJECTED_FIELDS),
    }
    response = await client.get(path, params=params)
    items = response.get("items", [])

    projected = [{k: item.get(k) for k in _PROJECTED_FIELDS} for item in items]

    return ToolResult.build(
        items=projected,
        limit_applied=limit,
        total_available=len(projected),
    )
