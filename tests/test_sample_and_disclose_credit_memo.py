"""Phase 3, PR #5 — the CreditMemo narrowing tip.

CreditMemo already samples on master: the plain-credit-memo branch in
synthesize_response builds a local CreditMemoListResponse from the
tool's rows. This test file locks that path and the ONE thing PR #5
adds: the narrowing_tip field on CreditMemoListResponse.

WHAT THIS FILE PROVES

Two structural facts about the CreditMemo entity on this pod, both
recorded in credit_memo.md's V0:

  1. narrowing_tip exists on CreditMemoListResponse (before PR #5 it
     does not; the attribute access raises AttributeError, which is
     the red this test lands as).
  2. narrowing_tip is "" on every CreditMemo response today, because
     the CreditMemo entity-level filter set is [] and build_narrowing_tip
     returns "" when given no filter types to name. The test asserts
     "" on both a sampled fetch (25 of N) and a complete fetch (N of N).

The assertions on total_credit are coverage, not fix surface: PR #5
does not touch compute_total_credit, but the field is read verbatim
off the tool's rows and the test locks that the synthesizer does not
recompute it.
"""

from unittest.mock import MagicMock

import pytest

from spire.synthesizer.synthesizer import (
    CreditMemoListResponse,
    synthesize_response,
)


def _forbidden_llm() -> MagicMock:
    """An LLM that fails the test if anything touches it.

    Mirrors the fixture in test_synthesizer_aggregation.py — three
    separate LLM-call removals in this project left the suite passing
    because a recording mock is silent when the code path skips it.
    Raising on contact makes "no LLM call" a tested property.
    """
    llm = MagicMock()
    llm.with_structured_output.side_effect = AssertionError(
        "synthesize_response called the LLM on the local CreditMemo path"
    )
    return llm


def _memo_row(
    cid: int,
    number: str,
    amount: float,
    currency: str,
    *,
    total_credit=None,
    total_credit_note=None,
) -> dict:
    """One credit-memo row as the tool projects it.

    The tool STAMPS total_credit and total_credit_note onto each row
    (server.py's list_receivables_credit_memos does the stamping) so
    they survive the executor's unwrap. The synthesizer reads them off
    the first row verbatim. These fixtures carry them so the test
    exercises the same shape the live path produces.
    """
    return {
        "CustomerTransactionId": cid,
        "TransactionNumber": number,
        "TransactionDate": "2024-01-15",
        "EnteredAmount": amount,
        "CreditMemoCurrency": currency,
        "CreditMemoStatus": "Complete",
        "BillToCustomerName": "ABC Application Software",
        "BillToCustomerNumber": "1001",
        "total_credit": total_credit,
        "total_credit_note": total_credit_note,
    }


def _sampled_outputs() -> dict[str, list[dict]]:
    """25 rows of N, with a known total_available of 1000.

    The synthesizer's CreditMemo branch runs on a single credit-memo
    bucket. The truncation_by_step carries total_available so
    _local_truncation sees 1000. That makes len(rows) < total_available
    true: a SAMPLE, which is the case PR #3 and PR #4's guard covers.
    """
    rows = [
        _memo_row(10000 + i, f"CM-{i:04d}", -100.0 - i, "USD",
                  total_credit=-2626.0)
        for i in range(25)
    ]
    return {"credit_memos": rows}


def _complete_outputs() -> dict[str, list[dict]]:
    """3 rows of N, with total_available equal to the row count.

    The complete-fetch case: len(rows) == total_available. The guard's
    positive branch must NOT fire. Same shape as invoice.md V3c.
    """
    rows = [
        _memo_row(20000 + i, f"CM-FULL-{i:04d}", -50.0 - i, "USD",
                  total_credit=-153.0)
        for i in range(3)
    ]
    return {"credit_memos": rows}


# ─────────────────────────────────────────────────────────────────────
# The field's existence — this is what goes red before PR #5's fix
# ─────────────────────────────────────────────────────────────────────


def test_credit_memo_response_has_narrowing_tip_field():
    """CreditMemoListResponse must carry narrowing_tip.

    Before PR #5 the field does not exist on the class. Attribute
    access on an instance raises AttributeError — the red signature
    this test lands as. After PR #5 the field exists with default "".
    """
    resp = CreditMemoListResponse(summary="x", credit_memos=[])
    assert hasattr(resp, "narrowing_tip")
    assert resp.narrowing_tip == ""


# ─────────────────────────────────────────────────────────────────────
# The tip is "" on a SAMPLE — because CreditMemo has no filter types
# ─────────────────────────────────────────────────────────────────────


def test_sampled_credit_memo_carries_empty_narrowing_tip():
    """25 of 1000 memos: a sample, but the tip has nothing to name.

    This is the honest case the V0 records. The guard `len(rows) <
    total_available` fires (25 < 1000), so build_narrowing_tip is
    called — but its filter_types argument is set(), and the function
    returns "" before it inspects total. The result is a sample with
    an empty tip, which is what the KG's state produces today.
    """
    outputs = _sampled_outputs()
    truncation = {
        "credit_memos": {"total_available": 1000, "truncated": True},
    }
    result = synthesize_response(
        outputs,
        target_entity="CreditMemo",
        llm=_forbidden_llm(),
        truncation_by_step=truncation,
    )
    assert isinstance(result, CreditMemoListResponse)
    assert len(result.credit_memos) == 25
    assert result.narrowing_tip == ""


# ─────────────────────────────────────────────────────────────────────
# The tip is "" on a COMPLETE fetch — the guard's negative branch
# ─────────────────────────────────────────────────────────────────────


def test_complete_credit_memo_carries_empty_narrowing_tip():
    """3 of 3 memos: complete, guard false, tip "".

    The guard is `len(rows) < total_available`. On a complete fetch,
    3 < 3 is false, so build_narrowing_tip is not even called. The
    result is "" by the guard, not by the filter-set-emptiness. Both
    branches produce "" today; the guard is correct for the future KG
    change that gives the tip something to name on a sample and
    nothing on a complete fetch.
    """
    outputs = _complete_outputs()
    truncation = {
        "credit_memos": {"total_available": 3, "truncated": False},
    }
    result = synthesize_response(
        outputs,
        target_entity="CreditMemo",
        llm=_forbidden_llm(),
        truncation_by_step=truncation,
    )
    assert isinstance(result, CreditMemoListResponse)
    assert len(result.credit_memos) == 3
    assert result.narrowing_tip == ""


# ─────────────────────────────────────────────────────────────────────
# total_credit is read verbatim — PR #5 does not recompute it
# ─────────────────────────────────────────────────────────────────────


def test_total_credit_copied_from_first_row():
    """total_credit on the response equals total_credit on row[0].

    The tool computes the total; the synthesizer copies it. This locks
    the copy — if a future change recomputes the total in Python, a
    multi-currency or truncated case would silently give a different
    number than the tool intended.
    """
    outputs = _sampled_outputs()
    truncation = {"credit_memos": {"total_available": 1000, "truncated": True}}
    result = synthesize_response(
        outputs, target_entity="CreditMemo", llm=_forbidden_llm(),
        truncation_by_step=truncation,
    )
    assert result.total_credit == -2626.0
    assert result.total_credit_note is None


def test_total_credit_none_when_tool_withholds_it():
    """When compute_total_credit returns (None, note), the synthesizer
    copies both verbatim.

    Multi-currency and truncation both cause compute_total_credit to
    withhold the total. The synthesizer must not invent one. This
    locks that it does not.
    """
    rows = [
        _memo_row(30000 + i, f"CM-MC-{i:04d}", -100.0, "USD" if i % 2 == 0 else "EUR",
                  total_credit=None,
                  total_credit_note="Not totalled: these memos span 2 currencies (EUR, USD).")
        for i in range(10)
    ]
    outputs = {"credit_memos": rows}
    truncation = {"credit_memos": {"total_available": 10, "truncated": False}}
    result = synthesize_response(
        outputs, target_entity="CreditMemo", llm=_forbidden_llm(),
        truncation_by_step=truncation,
    )
    assert result.total_credit is None
    assert result.total_credit_note is not None
    assert "Not totalled" in result.total_credit_note
