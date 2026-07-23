"""StandardReceipt search tool — top-level cash receipts (Prompt 13).

Fetches from /standardReceipts (the top-level collection, not the account child).
Accepts customer_name (resolved to account number) and customer_site (client-side).
`fields=` is broken on this endpoint (500s), so fetch full rows and discard
fields client-side.

Composite q= fails silently (returns zero), so only one server clause is used.

Used for "receipts for customer X at site Y" (Prompt 13).
"""

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.customer_account_by_name import get_customer_account_by_name
from spire.mcp_server.tools.tool_result import ToolResult

STANDARD_RECEIPTS_PATH = "/fscmRestApi/resources/11.13.18.05/standardReceipts"

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
    "RemittanceBankName",
    "RemittanceBankBranch",
    "RemittanceBankAccountNumber",
]

OVERFETCH_LIMIT = 500


async def search_standard_receipts(
    client: FusionClient,
    customer_name: str | None = None,
    customer_site: str | None = None,
    limit: int = 25,
) -> ToolResult:
    """Search top-level standard receipts.

    Args:
        customer_name: Customer name (e.g. "ABC Application Software"). Resolved to
            account number server-side.
        customer_site: CustomerSite (e.g. "Santa Clara"). Applied client-side.
        limit: Max records to return after client-side filtering.

    Returns:
        ToolResult with projected receipt dicts.
    """
    if not customer_name and not customer_site:
        raise ValueError("At least one of customer_name or customer_site is required.")

    # Resolve customer_name to account number
    account_number = None
    if customer_name:
        accounts = await get_customer_account_by_name(client, customer_name, limit=1)
        if not accounts:
            # No such customer; return empty result
            return ToolResult.build(items=[], limit_applied=limit, total_available=0)
        account_number = accounts[0].get("AccountNumber")
        if not account_number:
            # Account has no number? Shouldn't happen, but fall back.
            return ToolResult.build(items=[], limit_applied=limit, total_available=0)

    params = {"limit": OVERFETCH_LIMIT, "onlyData": "true"}
    if account_number:
        params["q"] = f"CustomerAccountNumber={account_number}"
    params["orderBy"] = "ReceiptDate:desc"

    response = await client.get(STANDARD_RECEIPTS_PATH, params=params)
    items = response.get("items", [])

    # Client-side filter by customer_site (case-sensitive, handle nulls)
    filtered = []
    for item in items:
        if customer_site is not None:
            site = item.get("CustomerSite")
            if site != customer_site:
                continue
        projected = {k: item.get(k) for k in _PROJECTED_FIELDS}
        filtered.append(projected)

    capped = filtered[:limit]
    total = len(filtered)
    truncated = len(items) >= OVERFETCH_LIMIT and len(capped) < len(filtered)

    return ToolResult.build(
        items=capped,
        limit_applied=limit,
        total_available=total if not truncated else None,
    )