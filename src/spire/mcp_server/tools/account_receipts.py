"""Standard receipts for one receivables account.

Fetches the standardReceipts child of a customer account and returns the
receipt rows, newest first. This is the second half of the
account-receipts flow (prompt 8): after get_customer_account_by_name
resolves the customer to account(s), this reads each account's receipts.

A receipt is CASH RECEIVED — a payment from the customer. Distinct from
an AR invoice (money owed) and from a credit memo (a credit issued).

NOT THE SAME PROJECTION AS THE TOP-LEVEL /standardReceipts
The same receipts are reachable two ways on this pod, and the two differ:
- this account child carries `ProcessStatus` and omits `CustomerName`,
  `CustomerAccountNumber` and every bank field.
- the TOP-LEVEL /standardReceipts carries `Status` (not ProcessStatus),
  plus customer and remittance-bank columns.
Do not carry a field name across from one to the other — naming
`ProcessStatus` in a `?fields=` list against the top-level resource is
what 500s it (see the endpoints reference, quirk 7). Prompt 13 will use
the top-level resource for its site filter; this tool is the child only.

The two also disagree on COUNT: this child reports 1,559 receipts for the
anchor account while the top-level filtered by CustomerAccountNumber
reports 1,386. Unexplained as of 2026-07-22 — do not treat them as
interchangeable sources for a receipt total.

MIXED ID WIDTHS — the thing most likely to trip up downstream code
`StandardReceiptId` is NOT uniformly sized in this collection. Backfilled
demo rows carry small ints (130, 131); recent rows carry large ones
(300000313660599). Both are valid receipt ids. Never infer anything from
an id's magnitude, and never assume a width when comparing or storing.

NO CLIENT-SIDE FILTERING
The child holds receipts only, so there is nothing to filter out: `limit`
applies server-side directly and is a true top-N. No fetch_limit, no
post-filter — the same simplification that account_credit_memos gets, and
unlike customer_transactions, which must over-fetch because its
collection mixes transaction classes.

THE LIMIT DEFAULTS TO 10, NOT 25
Its sibling account_credit_memos defaults to 25 and works. This tool does
not, and the reason is downstream: 25 varied receipt rows exceeded the
SYNTHESIZER's output-token ceiling on the AR-P5 anchor account. The model
returned structurally valid JSON with an EMPTY receipts array while still
narrating the receipts in prose — so the answer looked plausible and the
structured rows silently vanished. Notably the SAME 25-row fetch
succeeded on an account whose receipts were nearly identical to one
another (out=3657) and failed on one with varied dates, amounts, methods
and states (out=7985). Row count alone does not predict it; payload
entropy does. Do not raise this default without an end-to-end run against
a varied account.

SERVER-SIDE ORDERING
orderBy=ReceiptDate:desc works on this child (confirmed live), and
matters: the anchor account carries 1,559 receipts whose default order is
oldest-first (2012). Without the sort, "recent" receipts would be the
least recent ones. ?fields= is also confirmed working HERE (again, unlike
the top-level resource).

NULLABLE SITE
`CustomerSite` is present but sparsely populated — null on the newest row
of the anchor account. Any consumer that groups or filters on it must
handle nulls, not just non-matches.

The row does NOT echo AccountId — the join key is the URL path only, the
established pattern for AR account children.

Returns a ToolResult whose items are the receipt dicts.
"""

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


# Child path template; formatted with an AccountId per call.
ACCOUNT_RECEIPTS_PATH_TEMPLATE = (
    "/fscmRestApi/resources/11.13.18.05/receivablesCustomerAccountActivities"
    "/{account_id}/child/standardReceipts"
)

_PROJECTED_FIELDS = [
    "StandardReceiptId",
    "ReceiptNumber",
    "ReceiptDate",
    "Amount",
    "Currency",
    "ReceiptMethod",
    "State",
    "ProcessStatus",
    "UnappliedAmount",
    "CustomerSite",
    "BusinessUnit",
]


async def get_account_receipts(
    client: FusionClient,
    account_id,
    limit: int = 10,
) -> ToolResult:
    """Fetch one account's standard receipts, newest first.

    Args:
        account_id: The AccountId of the customer account (from
            get_customer_account_by_name).
        limit: Max receipts to return. Applied SERVER-SIDE alongside the
            date sort, so this is a true "N most recent" — no
            over-fetching is needed because the child holds receipts only
            and nothing is filtered out client-side.

            DEFAULT IS 10, NOT 25 (the value its sibling
            account_credit_memos uses). 25 varied receipt rows exceeded
            the synthesizer's output-token ceiling on the AR-P5 anchor
            account: the model returned valid JSON with an EMPTY receipts
            array while still describing the receipts in prose, so the
            structured answer silently lost every row. The same 25-row
            fetch succeeded on an account whose receipts were nearly
            identical to each other (out=3657) and failed on one with
            varied dates, amounts, methods and states (out=7985) — the
            payload's entropy, not its row count, is what costs tokens.
            10 rows keeps a realistic worst case well under the ceiling.
            Raise it only with an end-to-end check on a varied account.

    Returns:
        ToolResult whose items are the receipt dicts, newest first.
        total_available is the account's full receipt count (from
        totalResults), not the number returned — so a caller can honestly
        say "10 of 1,386" rather than "10 receipts".
    """
    path = ACCOUNT_RECEIPTS_PATH_TEMPLATE.format(account_id=account_id)
    params = {
        "onlyData": "true",
        "limit": limit,
        "orderBy": "ReceiptDate:desc",
        "totalResults": "true",
        "fields": ",".join(_PROJECTED_FIELDS),
    }
    response = await client.get(path, params=params)
    items = response.get("items", [])

    projected = [{k: item.get(k) for k in _PROJECTED_FIELDS} for item in items]

    # The pod's own count for this collection. Without it, total_available
    # equals the returned row count, ToolResult.build computes
    # `total_available > len(items)` as false, and the result claims nothing
    # was truncated — so a capped slice is indistinguishable from a complete
    # answer. Falls back to the row count when the endpoint omits
    # totalResults: an honest floor, not an invented total.
    total_available = response.get("totalResults")
    if not isinstance(total_available, int):
        total_available = len(projected)

    return ToolResult.build(
        items=projected,
        limit_applied=limit,
        total_available=total_available,
    )

