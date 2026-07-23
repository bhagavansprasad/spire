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
= 'Unapplied' with all ReferenceTransaction* fields null. A naive recent-N
slice returns rows whose entire transaction side is empty. This tool filters
client-side for ApplicationStatus == 'Applied', following the over-fetch pattern
of customer_transactions.py.

VOLUME: 15,636 rows on the anchor account. The tool over-fetches up to
fetch_limit (default 500), filters client-side, then caps at the caller's
limit. A caller wanting "recent applications" needs enough raw rows fetched to
find the desired number of applied ones, hence fetch_limit defaults well above
the display limit.

ORDERING: orderBy=ApplicationDate:desc works server-side (confirmed live).
"""

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


# Child path template; formatted with an AccountId per call.
ACCOUNT_RECEIPT_APPLICATIONS_PATH_TEMPLATE = (
    "/fscmRestApi/resources/11.13.18.05/receivablesCustomerAccountActivities"
    "/{account_id}/child/standardReceiptApplications"
)

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
    limit: int = 25,
    fetch_limit: int = 500,
) -> ToolResult:
    """Fetch one account's receipt applications, applied only, newest first.

    Args:
        account_id: The AccountId of the customer account (from
            get_customer_account_by_name).
        limit: Max applications to return AFTER filtering (the caller's
            display cap, e.g. 25).
        fetch_limit: Max raw rows to pull from the pod BEFORE filtering.
            Larger than `limit` because filtering discards unapplied rows;
            defaults high enough to find enough applied rows on large accounts.

    Returns:
        ToolResult whose items are the filtered application dicts, capped at
        `limit`. total_available is the filtered count (before the cap).
    """
    path = ACCOUNT_RECEIPT_APPLICATIONS_PATH_TEMPLATE.format(account_id=account_id)
    params = {
        "onlyData": "true",
        "limit": fetch_limit,
        "orderBy": "ApplicationDate:desc",
        "fields": ",".join(_PROJECTED_FIELDS),
    }
    response = await client.get(path, params=params)
    items = response.get("items", [])

    # Client-side filter: keep only Applied rows (unapplied cash rows have no
    # transaction side and are noise for "applications").
    filtered = []
    for item in items:
        if item.get("ApplicationStatus") != "Applied":
            continue
        filtered.append({k: item.get(k) for k in _PROJECTED_FIELDS})

    total_filtered = len(filtered)
    capped = filtered[:limit]

    return ToolResult.build(
        items=capped,
        limit_applied=limit,
        total_available=total_filtered,
    )