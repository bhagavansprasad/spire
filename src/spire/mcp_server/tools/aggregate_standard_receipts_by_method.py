"""Aggregate standard receipts by receipt method (Prompt 17).

Groups top-level /standardReceipts by ReceiptMethod, counts them, and sums
Amount per method. Optionally filter by customer name (resolved to account number)
or direct account_number. Returns groups sorted by total amount descending.

This is a bounded aggregation tool: grouping by ReceiptMethod and measure
(sum of amount) are fixed by identity.

PAGINATION. An earlier version issued ONE call with limit=500 and reported
whatever came back as the total. Account 26360 has 1,386 receipts, so the
result was a 500-row sample presented as a distribution — and because this
endpoint has NO DEFAULT ORDERING, two identical calls sampled different
rows and produced totals differing by ~32M. Nothing flagged it. This
version pages to exhaustion when scoped to an account, and caps with an
explicit truncated flag when unscoped (the pod-wide set is unbounded).
"""

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.customer_account_by_name import get_customer_account_by_name

STANDARD_RECEIPTS_PATH = "/fscmRestApi/resources/11.13.18.05/standardReceipts"

# Rows per request. The endpoint accepts larger, but 500 keeps each
# response a reasonable size — fields= 500s here, so every row comes back
# full-width and there is no way to project it down.
PAGE_SIZE = 500

# Page ceiling for the UNSCOPED (pod-wide) case only. The scoped case pages
# to exhaustion: an account's receipt count is bounded and knowable
# (1,386 on the largest demo account). Pod-wide has no such bound, so it
# stops here and says so rather than paging indefinitely.
MAX_UNSCOPED_PAGES = 10


async def aggregate_standard_receipts_by_method(
    client: FusionClient,
    customer_name: str | None = None,
    account_number: str | None = None,
    limit: int | None = None,
) -> dict:
    """Aggregate receipts by receipt method.

    Args:
        customer_name: Customer name to filter receipts (resolved to account number).
        account_number: Direct CustomerAccountNumber (if customer_name not provided).
        limit: If provided, return only the top N groups by total amount
            (descending). Omit to return all groups.

    Returns:
        A dict with shape "receipt_method_distribution":
            shape: "receipt_method_distribution",
            total_receipts: int,
            total_amount: float,
            returned: int,
            truncated: bool,
            rows: [
                {
                    "receipt_method": str,
                    "receipt_count": int,
                    "total_amount": float,
                },
                ...
            ]

    Raises:
        ValueError: if customer_name is given but resolves to no account.
            Falling through to an unfiltered fetch would silently turn a
            customer-scoped question into a pod-wide one and answer it
            with the customer's name attached.
    """
    # Resolve customer_name to account_number if given.
    resolved_account = account_number
    if customer_name:
        accounts = await get_customer_account_by_name(client, customer_name, limit=1)
        if not accounts:
            raise ValueError(
                f"No customer account found for {customer_name!r}. "
                "Refusing to aggregate pod-wide receipts for a "
                "customer-scoped question."
            )
        resolved_account = accounts[0].get("AccountNumber")
        if not resolved_account:
            raise ValueError(
                f"Customer {customer_name!r} resolved to an account with no "
                "AccountNumber; cannot scope the receipt aggregation."
            )

    scoped = resolved_account is not None

    # Group as we page, so only the aggregate is held in memory.
    groups: dict[str, dict] = {}
    total_receipts = 0
    total_amount = 0.0
    truncated = False

    offset = 0
    pages = 0
    while True:
        params: dict[str, str | int] = {
            "limit": PAGE_SIZE,
            "offset": offset,
            "onlyData": "true",
        }
        if scoped:
            params["q"] = f"CustomerAccountNumber='{resolved_account}'"

        response = await client.get(STANDARD_RECEIPTS_PATH, params=params)
        items = response.get("items", [])

        for item in items:
            method = item.get("ReceiptMethod") or "(unknown)"
            if method not in groups:
                groups[method] = {
                    "receipt_method": method,
                    "receipt_count": 0,
                    "total_amount": 0.0,
                }
            groups[method]["receipt_count"] += 1
            amount = item.get("Amount")
            if isinstance(amount, (int, float)):
                groups[method]["total_amount"] += amount
                total_amount += amount
            total_receipts += 1

        pages += 1

        if not response.get("hasMore"):
            break
        if not items:
            # Defensive: hasMore true with an empty page would loop forever.
            break
        if not scoped and pages >= MAX_UNSCOPED_PAGES:
            truncated = True
            break

        offset += len(items)

    # Sort by total_amount descending
    sorted_rows = sorted(groups.values(), key=lambda x: x["total_amount"], reverse=True)
    if limit is not None:
        sorted_rows = sorted_rows[:limit]

    return {
        "shape": "receipt_method_distribution",
        "total_receipts": total_receipts,
        "total_amount": total_amount,
        "returned": len(sorted_rows),
        "truncated": truncated,
        "rows": sorted_rows,
    }
