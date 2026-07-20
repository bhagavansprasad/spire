"""Customer account lookup by name.

Resolves a customer name to their receivables account(s) via
/receivablesCustomerAccountActivities, returning one row per matching
account. This is the FIRST half of the customer-invoices flow (prompts 1
and 15): resolve the customer to account(s), then traverse each account's
transactions (get_customer_transactions).

WHY BY NAME (and why a list)
Unlike the AR-invoice endpoint — whose BillToCustomerName/Number are NOT
queryable — the account-activities resource DOES accept q=CustomerName=
(confirmed live: q=CustomerName='ABC Corporation Americas' returned the
account directly). So a customer named in a prompt resolves here in one
call. A customer can in principle hold more than one account, so this
returns ALL matches as a list; the edge traversal iterates them, so a
customer's invoices span every account they hold. "ABC Corporation
Americas" happens to map to exactly one account on this pod.

CustomerName is queryable; the child transaction rows are then filtered
client-side (TransactionClass is NOT queryable — see the endpoints
reference's non-queryable list).

Returns a list of account dicts (possibly empty if the name matches
nothing). Each carries AccountId (the key the transaction traversal needs),
AccountNumber, CustomerName, CustomerId, and the account balance.
"""

from spire.fusion.client import FusionClient


ACCOUNT_ACTIVITIES_PATH = (
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


def _project(source: dict) -> dict:
    return {k: source.get(k) for k in _PROJECTED_FIELDS}


async def get_customer_account_by_name(
    client: FusionClient, customer_name: str, limit: int = 25
) -> list[dict]:
    """Resolve a customer name to their receivables account(s).

    Args:
        customer_name: The customer's display name, e.g. "ABC Corporation
            Americas". Matched via q=CustomerName= (server-side, exact).
        limit: Max accounts to return (a customer rarely holds many).

    Returns:
        A list of account dicts with the projected fields, one per matching
        account. Empty if the name matches no account.
    """
    params = {
        "onlyData": "true",
        "q": f"CustomerName='{customer_name}'",
        "fields": ",".join(_PROJECTED_FIELDS),
        "limit": limit,
    }
    response = await client.get(ACCOUNT_ACTIVITIES_PATH, params=params)
    items = response.get("items", [])
    return [_project(item) for item in items]
