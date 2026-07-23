"""Account receipt applications (Prompt 9) — the applied/unapplied cash matching.

Fetches the standardReceiptApplications child of a customer account and returns
the applied rows (ApplicationStatus='Applied'), newest first. This is the
second half of the receipt-applications flow: after get_customer_account_by_name
resolves the customer to account(s), this reads each account's applications.

PRE-JOINED: each row carries both the receipt side (StandardReceiptId,
ReceiptNumber, ReceiptMethod) and the transaction side
(ReferenceTransactionId, ReferenceTransactionNumber, ReferenceTransactionStatus)
on ONE record — no second fetch is needed.

TRAP: the newest rows are unapplied cash, not applications — ApplicationStatus
= 'Unapplied' with all ReferenceTransaction* fields null. Confirmed live on the
anchor account: of 15,636 rows, 8,598 are Unapplied and 7,038 Applied. The
unapplied rows are largely sign-mirrored reversals of applied ones (e.g.
-2434.55 against +2434.55), so mixing them in makes any total meaningless.

FILTERING IS SERVER-SIDE. q=ApplicationStatus='Applied' is honoured by this
child resource (confirmed live), so there is no need to over-fetch and discard.
An earlier version pulled 500 raw rows and filtered client-side, which meant
total_available reported the applied count WITHIN THAT PAGE — the caller then
stated "25 receipt applications" for an account with 7,038. The client-side
pass below is retained only as a cheap safety net if the server-side clause is
ever silently dropped.

ORDERING: orderBy=ApplicationDate:desc works server-side (confirmed live).
Without it this endpoint returns oldest-first (2012 rows), which is not what
"recent applications" means.

ROW LIMIT: 10, not 25. These rows are wide (twelve fields, both the receipt and
the transaction side), and 25 of them overran the synthesizer's output budget —
finish_reason=MAX_TOKENS at out=7985 against an 8000 cap. Same reasoning as the
10-row cap in account_receipts.py. Raise this only if an end-to-end run proves
a larger value safe.
"""

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


# Child path template; formatted with an AccountId per call.
ACCOUNT_RECEIPT_APPLICATIONS_PATH_TEMPLATE = (
    "/fscmRestApi/resources/11.13.18.05/receivablesCustomerAccountActivities"
    "/{account_id}/child/standardReceiptApplications"
)

# The status this tool reports on. Unapplied rows have a null transaction
# side and are excluded by the server-side clause.
APPLIED_STATUS = "Applied"

_PROJECTED_FIELDS = [
    "ApplicationId",
    "StandardReceiptId",
    "ReceiptNumber",
    "ReceiptMethod",
    "ReferenceTransactionId",
    "ReferenceTransactionNumber",
    "ReferenceTransactionStatus",
    "ApplicationAmount",
    "ApplicationDate",
    "ApplicationStatus",
    "EnteredCurrency",
    "CustomerSite",
]


async def get_account_receipt_applications(
    client: FusionClient,
    account_id,
    limit: int = 10,
) -> ToolResult:
    """Fetch one account's receipt applications, applied only, newest first.

    Args:
        account_id: The AccountId of the customer account (from
            get_customer_account_by_name).
        limit: Max applications to return (the caller's display cap).
            Defaults to 10 — see the ROW LIMIT note in the module docstring.

    Returns:
        ToolResult whose items are the application dicts, capped at `limit`.
        total_available is the pod's count of APPLIED applications for this
        account (from totalResults), not the number returned — so a caller
        can honestly say "10 of 7,038" rather than "10 applications".
    """
    path = ACCOUNT_RECEIPT_APPLICATIONS_PATH_TEMPLATE.format(account_id=account_id)
    params = {
        "onlyData": "true",
        "limit": limit,
        "orderBy": "ApplicationDate:desc",
        "q": f"ApplicationStatus='{APPLIED_STATUS}'",
        "totalResults": "true",
        "fields": ",".join(_PROJECTED_FIELDS),
    }
    response = await client.get(path, params=params)
    items = response.get("items", [])

    # Safety net only: the server-side q= above should already have excluded
    # these. If this ever discards rows, the server clause stopped working
    # and total_available below is no longer trustworthy.
    rows = [
        {k: item.get(k) for k in _PROJECTED_FIELDS}
        for item in items
        if item.get("ApplicationStatus") == APPLIED_STATUS
    ]

    # The pod's count of applied applications for this account. Falls back to
    # the returned row count if the endpoint omits totalResults, which is the
    # honest floor rather than an invented total.
    total_available = response.get("totalResults")
    if not isinstance(total_available, int):
        total_available = len(rows)

    return ToolResult.build(
        items=rows[:limit],
        limit_applied=limit,
        total_available=total_available,
    )
