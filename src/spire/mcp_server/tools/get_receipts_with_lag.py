"""Get receipts with creation‑to‑update lag (Prompt 18).

Fetches top‑level /standardReceipts (optionally filtered by customer name),
computes the lag in days between LastUpdateDate and CreationDate, and returns
the receipts sorted by lag descending (largest gap first). The lag is computed
as (LastUpdateDate - CreationDate).days.

This is a list‑style tool with a computed field. The synthesizer can summarize
min/max/avg from the returned rows.
"""

from datetime import datetime
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.customer_account_by_name import get_customer_account_by_name
from spire.mcp_server.tools.tool_result import ToolResult

STANDARD_RECEIPTS_PATH = "/fscmRestApi/resources/11.13.18.05/standardReceipts"

# We'll fetch full rows (fields= is broken on this endpoint) and project.
_PROJECTED_FIELDS = [
    "StandardReceiptId",
    "ReceiptNumber",
    "ReceiptDate",
    "Amount",
    "Currency",
    "ReceiptMethod",
    "Status",
    "CustomerName",
    "CustomerAccountNumber",
    "CustomerSite",
    "CreationDate",
    "LastUpdateDate",
    "RemittanceBankName",
]


def _compute_lag_days(creation: str | None, last_update: str | None) -> int | None:
    """Compute (LastUpdateDate - CreationDate) in days."""
    if creation is None or last_update is None:
        return None
    try:
        dt1 = datetime.fromisoformat(creation)
        dt2 = datetime.fromisoformat(last_update)
        delta = dt2 - dt1
        return abs(delta.days)
    except (ValueError, TypeError):
        return None


async def get_receipts_with_lag(
    client: FusionClient,
    customer_name: str | None = None,
    limit: int = 25,
    lag_query: bool = False,  # ignored – the tool always computes lag
) -> ToolResult:
    """Fetch receipts with computed creation‑to‑update lag.

    Args:
        client: FusionClient.
        customer_name: Optional customer name; resolved to account number.
        limit: Max records to return.
        lag_query: Ignored – the tool always computes lag.

    Returns:
        ToolResult with items containing receipt fields plus lag_days.
    """
    # Resolve customer_name to account number.
    resolved_account = None
    if customer_name:
        accounts = await get_customer_account_by_name(client, customer_name, limit=1)
        if accounts:
            resolved_account = accounts[0].get("AccountNumber")

    params = {"limit": 500, "onlyData": "true"}
    if resolved_account:
        params["q"] = f"CustomerAccountNumber={resolved_account}"
    params["orderBy"] = "CreationDate:desc"

    response = await client.get(STANDARD_RECEIPTS_PATH, params=params)
    items = response.get("items", [])

    result_items = []
    for item in items:
        creation = item.get("CreationDate")
        last_update = item.get("LastUpdateDate")
        lag_days = _compute_lag_days(creation, last_update)

        projected = {k: item.get(k) for k in _PROJECTED_FIELDS}
        projected["lag_days"] = lag_days
        result_items.append(projected)

    # Sort by lag descending (largest lag first)
    result_items.sort(key=lambda x: x.get("lag_days") or 0, reverse=True)

    capped = result_items[:limit]
    total = len(result_items)

    return ToolResult.build(
        items=capped,
        limit_applied=limit,
        total_available=total,
    )