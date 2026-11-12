"""Customer account search tool — filter-less list of customer accounts.

Plain async function — not coupled to FastMCP. Registration happens
in spire.mcp_server.server, exactly like search_receivables_invoices.

WHY THIS EXISTS
PR #7 / Phase 3 sample-and-disclose. The CustomerAccount entity had a
resolver (`get_customer_account_by_name`) reached by `by_customer_name`
or `by_account_number`, but no filter-less fetcher. A prompt that names
no narrowing filter ("show me all customer accounts") therefore could
not be answered: the planner's `find_entity_tool('CustomerAccount',
'none')` had no row, so the intent never reached a plan.

This tool is the missing fetcher. It returns the most recent N customer
accounts with the pod's own total on `total_available`, so a caller can
honestly say "25 of N" rather than "25 customer accounts".

RELATIONSHIP TO get_customer_account_by_name
Same underlying endpoint (`receivablesCustomerAccountActivities`).
The resolver requires `q=CustomerName=` or `q=AccountNumber=` — it
answers "which account is THIS customer". This tool takes no filter
— it answers "give me a bounded sample of customer accounts". The two
are not interchangeable, and a filter-less prompt routes here.

POD QUIRKS
  - `receivablesCustomerAccountActivities` accepts a query with no
    `q=` at all; the full collection is 435 rows on this pod, so a
    bounded fetch of 25 is cheap and deterministic.
  - `orderBy=CustomerName:asc` makes the 25-row sample reproducible
    run-to-run. Without an orderBy, the fetch returns whichever rows
    the pod happens to return first — a different sample each call.
  - `totalResults=true` returns the collection count on the response,
    so a caller can state "25 of N" honestly. If the endpoint omits
    the count on some parameter combination, the row count is the
    honest floor, not an invented total.

WHAT THIS TOOL DOES NOT DO
  - No filter parameter. The filter-less fetch is the whole point;
    filtered customer-account queries route to the resolver.
  - No projection. The endpoint's row carries all fields we need;
    `?fields=` works on this endpoint but the projection is cheap
    and the 25-row cap bounds the payload.
"""
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


CUSTOMER_ACCOUNTS_PATH = (
    "/fscmRestApi/resources/11.13.18.05/receivablesCustomerAccountActivities"
)

_PROJECTED_FIELDS = [
    "AccountId",
    "AccountNumber",
    "CustomerName",
    "CustomerId",
    "TotalOpenReceivablesForAccount",
    "TotalTransactionsDueForAccount",
]


async def search_customer_accounts(
    client: FusionClient,
    limit: int = 25,
) -> ToolResult:
    """List customer accounts, filter-less, newest by CustomerName.

    Args:
        limit: Max account records to return. Ordered by CustomerName
            ascending server-side, so this is a true first-N of the
            alphabetical collection, not a page slice. Default 25.

    Returns:
        A ToolResult dict: items (each carrying AccountId, AccountNumber,
        CustomerName, CustomerId, TotalOpenReceivablesForAccount,
        TotalTransactionsDueForAccount), total_available (the collection
        count from totalResults), limit_applied, truncated. Empty items
        means the pod has no customer accounts.
    """
    params: dict[str, str | int] = {
        "onlyData": "true",
        "orderBy": "CustomerName:asc",
        "limit": limit,
        "totalResults": "true",
        "fields": ",".join(_PROJECTED_FIELDS),
    }

    response = await client.get(CUSTOMER_ACCOUNTS_PATH, params=params)
    items = response.get("items", [])
    projected = [
        {k: item.get(k) for k in _PROJECTED_FIELDS} for item in items
    ]

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
