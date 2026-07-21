"""Receivables credit memos tool: recent AR credit memos (top-level list).

Credit memos are a top-level resource at /receivablesCreditMemos — unlike
AR invoice lines, there is NO parent id in the path. Each memo carries its
own identity (CustomerTransactionId, TransactionNumber), a date, the entered
amount, the bill-to customer, currency, and status.

Same object model as ReceivablesInvoice, with two differences that matter:
- EnteredAmount is normally NEGATIVE (a credit). Do NOT assume the sign —
  the demo pod has at least one POSITIVE, Incomplete memo mixed in.
- The status field is CreditMemoStatus (e.g. 'Complete', 'Incomplete').

"Recent" ordering is done SERVER-SIDE via orderBy=TransactionDate:desc
(confirmed working on this pod), so the newest memos come first and `limit`
gives a clean top-N. The total credit value is computed by the caller (the
server wrapper) over the returned rows as the raw sum of EnteredAmount — the
ledger figure, letting a positive outlier offset the negatives.

Returns a ToolResult (like the other AR tools) so callers can tell a
complete result from a capped subset. The total is layered on by the wrapper.
"""

import httpx

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


# Top-level credit-memos resource — no parent id in the path.
RECEIVABLES_CREDIT_MEMOS_PATH = (
    "/fscmRestApi/resources/11.13.18.05/receivablesCreditMemos"
)

_PROJECTED_FIELDS = [
    "CustomerTransactionId",
    "TransactionNumber",
    "TransactionDate",
    "EnteredAmount",
    "CreditMemoCurrency",
    "CreditMemoStatus",
    "BillToCustomerName",
    "BillToCustomerNumber",
]


async def list_receivables_credit_memos(
    client: FusionClient,
    limit: int = 25,
) -> ToolResult:
    """List recent AR credit memos, newest first.

    Args:
        limit: Max credit-memo records to return. Ordered by TransactionDate
            descending server-side, so this is a true top-N of the most
            recent memos. Default 25.

    Returns:
        ToolResult whose items are the projected credit-memo dicts, newest
        first. Empty items means no credit memos exist on the pod.
    """
    params = {
        "onlyData": "true",
        "orderBy": "TransactionDate:desc",
        "limit": limit,
        "fields": ",".join(_PROJECTED_FIELDS),
    }
    try:
        response = await client.get(RECEIVABLES_CREDIT_MEMOS_PATH, params=params)
    except httpx.HTTPStatusError as exc:
        # A 404 on a top-level list is unexpected, but treat it as "no memos"
        # (empty ToolResult) rather than crashing. Any other status is a real
        # error — re-raise it.
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
