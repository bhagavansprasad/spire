"""PR #7 — CustomerAccount sample-and-disclose, red base.

The six tests below lock the plain-list path for CustomerAccount:
the fetcher `search_customer_accounts`, the `narrowing_tip` field on
`CustomerAccountResponse`, the plain-list branch in
`synthesize_response`, and the boundary that customer-scoped prompts
route away from it. At the red base (this commit), the fetcher module
does not exist, the field does not exist, and the plain-list branch
does not exist — so five or six of these tests fail. They go green
after the fix lands.

Modeled on `tests/test_sample_and_disclose_receivables_invoice.py`
(PR #6). The `_forbidden_llm` pattern is copied verbatim from that
file.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from spire.synthesizer.synthesizer import (
    CustomerAccountResponse,
    synthesize_response,
)


def _forbidden_llm() -> MagicMock:
    llm = MagicMock()
    llm.with_structured_output.side_effect = AssertionError(
        "synthesize_response called the LLM on a plain customer-account list"
    )
    return llm


def _row(i: int) -> dict:
    return {
        "AccountId": 300000047000000 + i,
        "AccountNumber": str(26000 + i),
        "CustomerName": f"Customer {i}",
        "CustomerId": 100000000000000 + i,
        "TotalOpenReceivablesForAccount": 1000.0 + i,
        "TotalTransactionsDueForAccount": 1100.0 + i,
    }


def test_plain_customer_account_list_builds_locally_no_llm():
    outputs = {"customer_accounts": [_row(i) for i in range(25)]}
    llm = _forbidden_llm()
    result = synthesize_response(
        outputs, target_entity="CustomerAccount", llm=llm,
    )
    assert isinstance(result, CustomerAccountResponse)
    assert len(result.customer_accounts) == 25
    assert result.customer_accounts[0].account_number == "26000"
    llm.with_structured_output.assert_not_called()


def test_plain_customer_account_list_carries_narrowing_tip():
    outputs = {"customer_accounts": [_row(i) for i in range(25)]}
    llm = _forbidden_llm()
    result = synthesize_response(
        outputs, target_entity="CustomerAccount", llm=llm,
    )
    assert hasattr(result, "narrowing_tip")
    assert result.narrowing_tip == ""


def test_narrowing_tip_absent_when_source_is_complete():
    rows = [_row(i) for i in range(3)]
    outputs = {"customer_accounts": rows}
    truncation = {
        "customer_accounts": {
            "total_available": 3,
            "truncated": False,
            "limit_applied": 25,
        }
    }
    llm = _forbidden_llm()
    result = synthesize_response(
        outputs, target_entity="CustomerAccount", llm=llm,
        truncation_by_step=truncation,
    )
    assert hasattr(result, "narrowing_tip")
    assert result.narrowing_tip == ""


def test_empty_result_does_not_carry_narrowing_tip():
    outputs = {"customer_accounts": []}
    llm = _forbidden_llm()
    result = synthesize_response(
        outputs, target_entity="CustomerAccount", llm=llm,
    )
    assert isinstance(result, CustomerAccountResponse)
    assert result.customer_accounts == []
    assert hasattr(result, "narrowing_tip")
    assert result.narrowing_tip == ""
    assert "No customer accounts" in result.summary


def test_tip_labels_do_not_leak_from_invoice():
    outputs = {"customer_accounts": [_row(i) for i in range(25)]}
    llm = _forbidden_llm()
    result = synthesize_response(
        outputs, target_entity="CustomerAccount", llm=llm,
    )
    tip = result.narrowing_tip.lower()
    assert "invoice" not in tip
    assert "by_customer_name" not in tip
    assert "by_account_number" not in tip


def test_customer_scoped_prompt_routes_away_from_plain_list():
    parent = {
        "AccountId": 300000047368527,
        "AccountNumber": "26370",
        "CustomerName": "ABC Corporation Americas",
        "CustomerId": 100000000395795,
        "TotalOpenReceivablesForAccount": 678923.69,
        "TotalTransactionsDueForAccount": 699039.33,
    }
    child_txn = {
        "TransactionId": 10464,
        "TransactionNumber": "1002215",
        "TransactionClass": "Invoice",
        "TransactionDate": "2012-03-21",
        "TotalOriginalAmount": 1591.28,
        "TotalBalanceAmount": 0,
        "InstallmentStatus": "Closed",
    }
    outputs = {
        "customer_accounts": [parent],
        "customer_transactions": [child_txn],
    }
    llm = _forbidden_llm()
    result = synthesize_response(
        outputs, target_entity="CustomerAccount", llm=llm,
    )
    assert isinstance(result, CustomerAccountResponse)
    assert len(result.customer_accounts) == 1
    assert hasattr(result, "narrowing_tip")
    assert result.narrowing_tip == ""
