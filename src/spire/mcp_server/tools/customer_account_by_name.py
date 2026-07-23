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

BALANCES ARE ROUNDED TO 2dp HERE — deliberately, and not for display.
The pod returns TotalTransactionsDueForAccount as 1179915.3225 for account
26370. Four decimal places do not terminate in IEEE-754, and the
synthesizer emitted the full binary expansion —
1179915.3225000001207768917083740234375 — then trailing zeros until it hit
the output token cap (finish_reason=MAX_TOKENS, out=7983). The summary and
every other field in that response were correct; the run died on this one
number. Captured in traces/degenerate_synthesize_20260724_014659.txt.

The failure is sampling-dependent: the same prompt succeeded earlier the
same day at out=3066. Rounding removes the pathological value rather than
asking the model not to expand it, on the principle that compute belongs in
the tool. Currency to 2dp loses nothing an AR answer needs.
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

# Monetary fields rounded to 2dp before they leave the tool. See the
# module docstring: an un-rounded value ran the synthesizer to its token
# cap emitting a float's full binary expansion.
_MONEY_FIELDS = (
    "TotalOpenReceivablesForAccount",
    "TotalTransactionsDueForAccount",
)


def _project(source: dict) -> dict:
    row = {k: source.get(k) for k in _PROJECTED_FIELDS}
    for field in _MONEY_FIELDS:
        value = row.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            row[field] = round(value, 2)
    return row


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
        account. Empty if the name matches no account. Balance fields are
        rounded to 2dp — see the module docstring for why this is not
        merely cosmetic.
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
