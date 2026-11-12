"""Phase 3, PR #6 — sample-and-disclose for ReceivablesInvoice.

Red-on-master tests for the wiring PR that gives the AR-invoice entity a
filter-less fetcher, a `narrowing_tip` field, and a local plain-list
branch.

WHAT IS RED ON MASTER, AND WHY
==============================

Three separate red shapes, one per source-file the fix lands:

  - search_receivables_invoices does not exist. Test 5 imports it; the
    import fails at collection time, which is a hard red (ImportError).
  - ReceivablesInvoiceResponse carries summary / receivables_invoices /
    truncation_notes only. Tests 2, 3, 4 assert `narrowing_tip` exists
    and is "". They fail with AttributeError.
  - The plain-list branch does not exist. A 25-row `receivables_invoices`
    bucket with no children falls through the synthesizer's
    single_parent_shape guard (which requires exactly one parent row)
    and reaches the LLM path. Test 1 uses the _forbidden_llm() pattern
    from test_synthesizer_aggregation.py, so the red is a loud
    AssertionError naming the LLM call rather than a silent pass.

Test 6 (empty list) is GREEN on master — the empty-bucket shortcut
already handles a zero-row AR bucket — and stays green. It is here to
lock that fact against regression, not to be red.

THE _forbidden_llm PATTERN
==========================

Copied from test_synthesizer_aggregation.py. A MagicMock that merely
RECORDS calls is not enough: three separate LLM-call removals in this
codebase left the suite count unchanged, because nothing asserted the
absence of a call. Raising on contact turns "no LLM call" from an
unobserved implementation detail into a tested property.

WHAT THIS FILE DOES NOT TEST
============================

The new tool's behaviour against the live pod (that is V1), the planner
guard relaxation (that is V4), the sysprompt block's wording (that is
V9's --validate sweep), and the KG row's presence (that is V1 too).
Unit tests test the shape the fix lands; the V-walk tests what the pod
does with it.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from spire.synthesizer.synthesizer import (
    ReceivablesInvoiceResponse,
    synthesize_response,
)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _forbidden_llm() -> MagicMock:
    """An LLM that fails the test if anything touches it.

    Mirrors test_synthesizer_aggregation._forbidden_llm. A silent mock
    lets a regression back onto the LLM path pass, because nothing
    downstream distinguishes "no LLM needed" from "LLM returned the
    right thing by luck".
    """
    llm = MagicMock()
    llm.with_structured_output.side_effect = AssertionError(
        "synthesize_response called the LLM on a plain AR-invoice list"
    )
    return llm


def _ar_row(ctid: int, number: str, amount: float = 100.0) -> dict:
    """One projected AR-invoice row, as receivables_invoice_by_id would
    return it. Field names match the tool's `_PROJECTED_FIELDS`."""
    return {
        "CustomerTransactionId": ctid,
        "TransactionNumber": number,
        "BillToCustomerName": "ABC Application Software",
        "BillToCustomerNumber": "1001",
        "InvoiceCurrencyCode": "USD",
        "EnteredAmount": amount,
        "InvoiceBalanceAmount": amount,
        "TransactionDate": "2024-01-15",
        "DueDate": "2024-02-15",
        "AccountingDate": "2024-01-15",
        "InvoiceStatus": "Complete",
        "TransactionType": "Invoice",
        "TransactionSource": "Manual",
        "BusinessUnit": "US1 Business Unit",
        "CreatedBy": "SVC_USER",
        "CreationDate": "2024-01-15T00:00:00",
        "LastUpdatedBy": "SVC_USER",
        "LastUpdateDate": "2024-01-15T00:00:00",
    }


def _plain_ar_bucket(n: int) -> dict[str, list[dict]]:
    """A plain AR-invoice list: one bucket, n rows, no children.

    This is exactly the shape a 25-row `get all AR invoices` produces
    after the new fetcher lands. On master it falls through
    single_parent_shape (which requires len(parent) == 1) and reaches
    the LLM path.
    """
    return {
        "receivables_invoices": [
            _ar_row(300000248096352 + i, f"TXN-{i:04d}", 100.0 + i)
            for i in range(n)
        ],
    }


def _truncation(total: int, returned: int) -> dict[str, dict]:
    """Executor truncation_by_step for the AR-invoice bucket."""
    return {
        "receivables_invoices": {
            "total_available": total,
            "limit_applied": 25,
            "truncated": total > returned,
        }
    }


# ─────────────────────────────────────────────────────────────────────
# Test 1 — plain 25-row list builds locally, no LLM
# ─────────────────────────────────────────────────────────────────────


def test_plain_receivables_invoice_list_builds_locally_no_llm():
    """A 25-row `receivables_invoices` bucket with no children returns a
    ReceivablesInvoiceResponse with 25 records, without ever touching
    the LLM.

    RED on master: the bucket falls through single_parent_shape
    (which requires exactly one parent row) and reaches
    `llm.with_structured_output(...)`, which the _forbidden_llm mock
    turns into a loud AssertionError.
    """
    outputs = _plain_ar_bucket(25)
    result = synthesize_response(
        outputs,
        target_entity="ReceivablesInvoice",
        llm=_forbidden_llm(),
        truncation_by_step=_truncation(1000, 25),
    )

    assert isinstance(result, ReceivablesInvoiceResponse)
    assert len(result.receivables_invoices) == 25
    # Order preserved — these are the executor's rows, not a model's
    # re-emission, so first-in-first-out is a property of the code.
    assert result.receivables_invoices[0].transaction_number == "TXN-0000"
    assert result.receivables_invoices[24].transaction_number == "TXN-0024"


# ─────────────────────────────────────────────────────────────────────
# Test 2 — narrowing_tip field exists on the response model
# ─────────────────────────────────────────────────────────────────────


def test_receivables_invoice_response_has_narrowing_tip_field():
    """ReceivablesInvoiceResponse carries a narrowing_tip field,
    defaulting to "".

    RED on master: the field does not exist; AttributeError.
    """
    resp = ReceivablesInvoiceResponse(
        summary="x", receivables_invoices=[], truncation_notes=[]
    )
    assert hasattr(resp, "narrowing_tip")
    assert resp.narrowing_tip == ""


# ─────────────────────────────────────────────────────────────────────
# Test 3 — sampled fetch carries empty narrowing_tip
# ─────────────────────────────────────────────────────────────────────


def test_sampled_receivables_invoice_carries_empty_narrowing_tip():
    """25 of 1000 rows: the answer is a SAMPLE, so the sample-only guard
    fires, but the tip text is "" because the KG has no entity-level
    narrowing filters to name on this pod.

    The empty tip is the intended value, not a bug: `['by_id']` minus
    `by_id` is `{}`, so `build_narrowing_tip(set(), ...)` returns ""
    before it ever inspects total_available. PR #5 established the same
    shape on CreditMemo.

    RED on master: AttributeError on `narrowing_tip`.
    """
    outputs = _plain_ar_bucket(25)
    result = synthesize_response(
        outputs,
        target_entity="ReceivablesInvoice",
        llm=_forbidden_llm(),
        truncation_by_step=_truncation(1000, 25),
    )
    assert result.narrowing_tip == ""


# ─────────────────────────────────────────────────────────────────────
# Test 4 — complete fetch carries empty narrowing_tip
# ─────────────────────────────────────────────────────────────────────


def test_complete_receivables_invoice_carries_empty_narrowing_tip():
    """N of N rows: the answer is COMPLETE, so the sample-only guard does
    NOT fire. The tip is "" on both branches — the positive branch is
    unreachable today, and the negative branch is the correct behaviour
    on a complete fetch.

    RED on master: AttributeError on `narrowing_tip`.
    """
    outputs = _plain_ar_bucket(5)
    result = synthesize_response(
        outputs,
        target_entity="ReceivablesInvoice",
        llm=_forbidden_llm(),
        truncation_by_step=_truncation(5, 5),
    )
    assert result.narrowing_tip == ""


# ─────────────────────────────────────────────────────────────────────
# Test 5 — the new fetcher exists and returns a ToolResult
# ─────────────────────────────────────────────────────────────────────


def test_search_receivables_invoices_returns_tool_result():
    """The new module exposes a plain async fetcher with the shape every
    other fetcher here uses: returns a ToolResult.

    RED on master: ImportError — the module does not exist.

    What this asserts is STRUCTURE, not behaviour. Behaviour (25 rows of
    1,000 in TransactionDate:desc order, honest total_available) is V1's
    job; a unit test cannot fetch from the pod.
    """
    from spire.mcp_server.tools.search_receivables_invoices import (
        search_receivables_invoices,
    )
    from spire.mcp_server.tools.tool_result import ToolResult

    import inspect

    sig = inspect.signature(search_receivables_invoices)
    params = list(sig.parameters)
    # The fetcher takes a FusionClient positional arg plus limit (and
    # nothing else narrowing — this is the FILTER-LESS fetcher, by
    # design). A future filtered fetcher is a separate function.
    assert "client" in params
    assert "limit" in params

    # Returns a ToolResult, not a raw list — the same contract as the
    # other list-shaped fetchers in this codebase.
    assert inspect.iscoroutinefunction(search_receivables_invoices)
    # The annotation is a string here (from __future__ import
    # annotations in every tool module); the check is the import's
    # success, not the annotation's identity.
    _ = ToolResult


# ─────────────────────────────────────────────────────────────────────
# Test 6 — empty list still says so (green on red, locks a fact)
# ─────────────────────────────────────────────────────────────────────


def test_empty_receivables_invoice_list_says_so():
    """A zero-row bucket short-circuits to the empty response, with the
    entity label "AR invoices" and a plain "No AR invoices found" summary.

    GREEN on master: the empty-bucket shortcut in synthesize_response
    fires before any branch, and _ENTITY_LABEL["ReceivablesInvoice"]
    is already "AR invoices". This test locks that fact — PR #6 must
    not disturb the empty path while adding the plain-list branch.
    """
    result = synthesize_response(
        {"receivables_invoices": []},
        target_entity="ReceivablesInvoice",
        llm=_forbidden_llm(),
    )
    assert isinstance(result, ReceivablesInvoiceResponse)
    assert "No AR invoices" in result.summary
    assert result.receivables_invoices == []
