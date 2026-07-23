"""Aggregate standard receipts by receipt method (Prompt 17).

Groups top-level /standardReceipts by ReceiptMethod, counts them, and sums
Amount per method. Optionally filter by customer name (resolved to account number)
or direct account_number. Returns groups sorted by total amount descending.

This is a bounded aggregation tool: grouping by ReceiptMethod and measure
(sum of amount) are fixed by identity.
"""

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.customer_account_by_name import get_customer_account_by_name

STANDARD_RECEIPTS_PATH = "/fscmRestApi/resources/11.13.18.05/standardReceipts"

# We'll fetch full rows (fields= is broken on this endpoint) and project.
_PROJECTED_FIELDS = [
    "ReceiptMethod",
    "Amount",
]


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
            rows: [
                {
                    "receipt_method": str,
                    "receipt_count": int,
                    "total_amount": float,
                },
                ...
            ]
    """
    # Resolve customer_name to account_number if given.
    resolved_account = account_number
    if customer_name:
        accounts = await get_customer_account_by_name(client, customer_name, limit=1)
        if accounts:
            resolved_account = accounts[0].get("AccountNumber")

    params = {"limit": 500, "onlyData": "true"}
    if resolved_account:
        params["q"] = f"CustomerAccountNumber={resolved_account}"

    response = await client.get(STANDARD_RECEIPTS_PATH, params=params)
    items = response.get("items", [])

    # Group by ReceiptMethod
    groups: dict[str, dict] = {}
    total_receipts = 0
    total_amount = 0.0

    for item in items:
        method = item.get("ReceiptMethod") or "(unknown)"
        if method not in groups:
            groups[method] = {"receipt_method": method, "receipt_count": 0, "total_amount": 0.0}
        groups[method]["receipt_count"] += 1
        amount = item.get("Amount")
        if isinstance(amount, (int, float)):
            groups[method]["total_amount"] += amount
            total_amount += amount
        total_receipts += 1

    # Sort by total_amount descending
    sorted_rows = sorted(groups.values(), key=lambda x: x["total_amount"], reverse=True)
    if limit is not None:
        sorted_rows = sorted_rows[:limit]

    return {
        "shape": "receipt_method_distribution",
        "total_receipts": total_receipts,
        "total_amount": total_amount,
        "returned": len(sorted_rows),
        "rows": sorted_rows,
    }