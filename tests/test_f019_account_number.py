"""F-019 - CustomerAccount resolves by account number.

Reproducer: "Trace receipt applications for account 25750"
Pre-fix: 17/20 runs returned "No customer accounts found" (the parser
routed the digit value into by_customer_name, CustomerName='25750'
returned zero); 3/20 refused in three different texts.

Fix: an account_number channel on the resolve path (tool argument,
KG filter row, KG tool row, sysprompt rule) plus a deterministic
post-parse correction that rewrites by_customer_name(digits) into
by_account_number.
"""

import pytest

from spire.mcp_server.tools.customer_account_by_name import (
    get_customer_account_by_name,
)
from spire.nl_parser.parser import _is_all_digit_customer_value


class _FakeClient:
    def __init__(self, response):
        self._response = response
        self.calls = []

    async def get(self, path, params=None):
        self.calls.append(params or {})
        return self._response


def _account(aid, num, name):
    return {
        "AccountId": aid,
        "AccountNumber": num,
        "CustomerName": name,
        "CustomerId": 1,
        "TotalOpenReceivablesForAccount": 0.0,
        "TotalTransactionsDueForAccount": 0.0,
    }


# ---------------------------------------------------------------------
# The tool: account_number vs customer_name choose different clauses
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_account_number_uses_account_number_clause():
    fake = _FakeClient({"items": [
        _account(300000047368542, "25750", "ABC Corporation Worldwide"),
    ]})
    result = await get_customer_account_by_name(fake, account_number="25750")
    assert fake.calls[0].get("q") == "AccountNumber='25750'", fake.calls[0]
    assert len(result) == 1
    assert result[0]["AccountNumber"] == "25750"


@pytest.mark.asyncio
async def test_customer_name_uses_name_clause():
    fake = _FakeClient({"items": [
        _account(300000047368527, "26370", "ABC Corporation Americas"),
    ]})
    await get_customer_account_by_name(
        fake, customer_name="ABC Corporation Americas"
    )
    assert fake.calls[0].get("q") == (
        "CustomerName='ABC Corporation Americas'"
    )


@pytest.mark.asyncio
async def test_neither_arg_raises():
    fake = _FakeClient({"items": []})
    with pytest.raises(ValueError):
        await get_customer_account_by_name(fake)


@pytest.mark.asyncio
async def test_account_number_wins_when_both_given():
    fake = _FakeClient({"items": []})
    await get_customer_account_by_name(
        fake, customer_name="ABC", account_number="25750"
    )
    assert fake.calls[0].get("q") == "AccountNumber='25750'"


# ---------------------------------------------------------------------
# The post-parse correction helper
# ---------------------------------------------------------------------


def test_looks_like_account_number_accepts_digits():
    assert _is_all_digit_customer_value("25750") is True
    assert _is_all_digit_customer_value("00125") is True


def test_looks_like_account_number_rejects_text():
    assert _is_all_digit_customer_value("ABC Corp") is False
    assert _is_all_digit_customer_value("ABC 25750") is False
    assert _is_all_digit_customer_value("") is False
    assert _is_all_digit_customer_value("  ") is False
    assert _is_all_digit_customer_value(None) is False
    assert _is_all_digit_customer_value(25750) is False
