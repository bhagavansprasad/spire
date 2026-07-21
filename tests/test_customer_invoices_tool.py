"""Integration tests for the customer-invoices tools
(get_customer_account_by_name and get_customer_transactions).

These hit the live pod, mirroring test_receivables_invoice_detail_tool.py,
and skip when personas.yaml is absent. "ABC Corporation Americas" resolves
to exactly one account (AccountId 300000047368527, AccountNumber 26370) on
the demo pod; that account carries 25 Invoice-class transactions.

Unlike the AR-invoice endpoint (whose customer fields are NOT queryable),
the account-activities resource DOES accept q=CustomerName=, so the resolver
filters by name server-side. The transaction child's TransactionClass is NOT
queryable, so the tool keeps Invoice-class rows client-side.
"""

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.customer_account_by_name import (
    get_customer_account_by_name,
)
from spire.mcp_server.tools.customer_transactions import (
    get_customer_transactions,
)


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)


# Known customer on the demo pod: one account, AccountId 300000047368527,
# AccountNumber 26370, with 25 Invoice-class transactions.
KNOWN_CUSTOMER_NAME = "ABC Corporation Americas"
KNOWN_ACCOUNT_ID = 300000047368527


@pytest.mark.asyncio
async def test_get_customer_account_by_name_resolves_known_customer():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        accounts = await get_customer_account_by_name(
            client, customer_name=KNOWN_CUSTOMER_NAME
        )
    assert len(accounts) == 1
    acct = accounts[0]
    assert acct["AccountId"] == KNOWN_ACCOUNT_ID
    assert acct["AccountNumber"] == "26370"
    assert acct["CustomerName"] == KNOWN_CUSTOMER_NAME


@pytest.mark.asyncio
async def test_get_customer_account_by_name_empty_for_unknown_customer():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        accounts = await get_customer_account_by_name(
            client, customer_name="No Such Customer ZZZ"
        )
    # The name query returns an empty item set for a non-match; the tool
    # returns an empty list.
    assert accounts == []


@pytest.mark.asyncio
async def test_get_customer_transactions_returns_invoices():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await get_customer_transactions(
            client, account_id=KNOWN_ACCOUNT_ID, limit=25
        )
    assert len(result.items) > 0
    # Every returned row is Invoice-class (the client-side filter kept only
    # invoices out of the account's mixed transaction classes).
    assert all(
        item["TransactionClass"] == "Invoice" for item in result.items
    )
    # Each row carries a transaction number and the balance field the
    # (deferred) open-only filter will use.
    first = result.items[0]
    assert first["TransactionNumber"]
    assert "TotalBalanceAmount" in first


@pytest.mark.asyncio
async def test_get_customer_transactions_open_only_keeps_positive_balance():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await get_customer_transactions(
            client, account_id=KNOWN_ACCOUNT_ID, open_only=True, limit=25
        )
    # With open_only, every returned row has a positive open balance. (The
    # set may be empty if this account has no open invoices — that is still
    # valid; the invariant is that nothing with a non-positive balance
    # slips through.)
    assert all(
        item["TotalBalanceAmount"] is not None
        and item["TotalBalanceAmount"] > 0
        for item in result.items
    )


@pytest.mark.asyncio
async def test_get_customer_transactions_open_only_is_balance_descending():
    # AR-P2c: open_only relies on orderBy=TotalBalanceAmount:desc to surface
    # open rows within the fetch window (the account has thousands of rows;
    # open ones do not appear on the default-order page). This asserts the
    # sort is actually applied: the open set is non-empty AND balance-
    # descending, with the top balances matching the known values. Would
    # fail (empty or unordered) if the orderBy were removed.
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await get_customer_transactions(
            client, account_id=KNOWN_ACCOUNT_ID, open_only=True, limit=5
        )
    balances = [item["TotalBalanceAmount"] for item in result.items]
    # Non-empty: this account has open invoices; an empty result here means
    # the sort is NOT surfacing them (the default-order page is all paid).
    assert balances, "expected open invoices; orderBy likely not applied"
    # Descending: the fetcher returns rows sorted by balance desc.
    assert balances == sorted(balances, reverse=True)
    # Top open balances on this anchor account (from live discovery).
    assert balances[:5] == [216378, 206008, 198286, 56412, 39969]
