"""Rank customer accounts by outstanding exposure (Prompt 10).

Fetches all customer accounts from /receivablesCustomerAccountActivities,
sorts them by TotalOpenReceivablesForAccount descending, and returns the top N.
This is a bounded aggregation tool: grouping by account and measure (sum of
open receivables) are fixed by identity.

No date range; the endpoint returns live account balances.
Only 435 rows on the pod, so fetching all is cheap and deterministic.
"""

from spire.fusion.client import FusionClient

CUSTOMER_ACCOUNT_PATH = "/fscmRestApi/resources/11.13.18.05/receivablesCustomerAccountActivities"

_PROJECTED_FIELDS = [
    "AccountId",
    "AccountNumber",
    "CustomerName",
    "TotalOpenReceivablesForAccount",
    "TotalTransactionsDueForAccount",
]


async def rank_customer_accounts_by_exposure(
    client: FusionClient,
    top_n: int = 10,
) -> dict:
    """Rank customer accounts by outstanding exposure (open receivables).

    Args:
        top_n: Number of accounts to return (default 10). The result is sorted
            by TotalOpenReceivablesForAccount descending, highest exposure first.

    Returns:
        A dict with shape "exposure_ranking":
            shape: "exposure_ranking",
            total_accounts: int,      # all accounts considered
            returned: int,            # rows returned (<= top_n)
            rows: [
                {
                    account_id,
                    account_number,
                    customer_name,
                    open_receivables,
                    transactions_due,
                },
                ...
            ]
    """
    # Fetch all accounts (no filter, no over-fetch needed; endpoint has 435 rows).
    params = {
        "onlyData": "true",
        "limit": 500,  # enough to cover all accounts (435)
        "fields": ",".join(_PROJECTED_FIELDS),
    }
    response = await client.get(CUSTOMER_ACCOUNT_PATH, params=params)
    items = response.get("items", [])

    # Sort by TotalOpenReceivablesForAccount descending; handle None as 0.
    sorted_items = sorted(
        items,
        key=lambda x: x.get("TotalOpenReceivablesForAccount") or 0,
        reverse=True,
    )

    # Project fields and cap at top_n.
    rows = []
    for item in sorted_items[:top_n]:
        rows.append({
            "account_id": item.get("AccountId"),
            "account_number": item.get("AccountNumber"),
            "customer_name": item.get("CustomerName"),
            "open_receivables": item.get("TotalOpenReceivablesForAccount"),
            "transactions_due": item.get("TotalTransactionsDueForAccount"),
        })

    return {
        "shape": "exposure_ranking",
        "total_accounts": len(items),
        "returned": len(rows),
        "rows": rows,
    }