"""Sample-and-disclose tests for StandardReceipt (PR #4).

Mirrors ``tests/test_sample_and_disclose_invoice.py``'s shape: five tests
that lock the scoped StandardReceipt path's tip behaviour and the fact
that it is already built locally (no LLM).

The current synthesizer branch for StandardReceipt is:

    if target_entity == "StandardReceipt" and len(outputs) == 1:
        ...
        return StandardReceiptResponse(
            summary=...,
            standard_receipts=build_standard_receipt_records(rows),
            truncation_notes=notes,
        )

It is already local. What it does NOT do is populate a narrowing tip —
the field is absent from ``StandardReceiptResponse``. These tests fail
on that absence before the fix, and pass after.

RED-BASE DISCIPLINE
Assertions on ``result.narrowing_tip`` are written to raise
``AttributeError`` on the current code (field missing), not to compare
against ``""``. A test that asserts ``result.narrowing_tip == ""`` on a
missing field passes for the wrong reason — the exact defect PR #1's
Fix C and PR #2's 257bf56 red-base commit record. Every assertion in
this file touches the field first.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from spire.synthesizer.synthesizer import (
    StandardReceiptResponse,
    synthesize_response,
)


def _forbidden_llm() -> MagicMock:
    """An LLM that fails the test if anything touches it.

    Local definition, not a cross-file import — matching the shape of
    tests/test_sample_and_disclose_invoice.py:29 and
    tests/test_sample_and_disclose_supplier.py:59. The two prior PRs each
    defined their own; the third follows.

    A MagicMock that merely RECORDS calls is not enough. Raising on
    contact is what turns "no LLM call" from an unobserved implementation
    detail into a tested property. See tests/test_synthesizer_aggregation.py
    for the precedent that first stated this.
    """
    llm = MagicMock()
    llm.with_structured_output.side_effect = AssertionError(
        "synthesize_response called the LLM on a StandardReceipt path "
        "that should be local"
    )
    return llm


def _receipt_row(i: int, receipt_number: str = "R-001") -> dict:
    """One executor row in the shape the StandardReceipt branch detects.

    Content signature, not name: the branch checks
    ``"StandardReceiptId" in rows[0]`` and
    ``"CustomerAccountNumber" in rows[0]``. Both must be present.
    """
    return {
        "StandardReceiptId": 130 + i,
        "ReceiptNumber": f"{receipt_number}-{i:03d}",
        "ReceiptDate": "2026-01-15",
        "Amount": 100.0 + i,
        "Currency": "USD",
        "ReceiptMethod": "Lockbox",
        "Status": "Cleared",
        "CustomerName": "ABC Application Software",
        "CustomerAccountNumber": "26360",
        "CustomerSite": "Santa Clara",
        "RemittanceBankName": "Bank of America",
        "RemittanceBankBranch": "Main",
        "RemittanceBankAccountNumber": "1234567890",
    }


@pytest.fixture
def sampled_outputs() -> dict[str, list[dict]]:
    """25 rows returned of a larger source — the SAMPLE case.

    The synthesizer branch computes ``total_available`` from the
    truncation entry, so a sampled shape needs that entry present.
    Without it, ``total_available`` is ``None`` and the tip (guarded on
    ``len(rows) < total_available``) does not fire.
    """
    return {"standard_receipts": [_receipt_row(i) for i in range(25)]}


@pytest.fixture
def sampled_truncation() -> dict[str, dict]:
    """Truncation entry for the sampled shape: 25 of 1,386."""
    return {
        "standard_receipts": {
            "total_available": 1386,
            "limit_applied": 25,
            "truncated": True,
        }
    }


@pytest.fixture
def complete_outputs() -> dict[str, list[dict]]:
    """3 rows returned of 3 — the COMPLETE fetch case. Not a sample."""
    return {"standard_receipts": [_receipt_row(i) for i in range(3)]}


@pytest.fixture
def complete_truncation() -> dict[str, dict]:
    """Truncation entry for the complete shape: 3 of 3."""
    return {
        "standard_receipts": {
            "total_available": 3,
            "limit_applied": 25,
            "truncated": False,
        }
    }


# ─────────────────────────────────────────────────────────────────────
# Test 1 — the tip fires on a sample, and names the two label entries
# ─────────────────────────────────────────────────────────────────────


def test_plain_receipt_list_carries_narrowing_tip(
    sampled_outputs, sampled_truncation,
):
    """A sampled StandardReceipt list must carry a populated tip.

    Before the fix, ``StandardReceiptResponse`` has no ``narrowing_tip``
    field, so this assertion raises AttributeError — a RED, not a
    confusing False. After the fix, the field exists and the tip names
    the two KG entity-level filters (customer name, customer site).
    """
    result = synthesize_response(
        sampled_outputs,
        target_entity="StandardReceipt",
        llm=_forbidden_llm(),
        truncation_by_step=sampled_truncation,
    )
    assert isinstance(result, StandardReceiptResponse)
    # Attribute access first — raises on the missing field, does not
    # silently pass on an empty default.
    tip = result.narrowing_tip
    assert tip, "sampled StandardReceipt must carry a non-empty tip"
    assert "customer name" in tip
    assert "customer site" in tip
    # The two labels, not the seven an Invoice tip names. A StandardReceipt
    # tip that mentions "invoice date" or "unpaid" would mean the label
    # map leaked across entities.
    assert "invoice date" not in tip
    assert "unpaid" not in tip


# ─────────────────────────────────────────────────────────────────────
# Test 2 — the tip is absent on a complete fetch
# ─────────────────────────────────────────────────────────────────────


def test_narrowing_tip_absent_when_source_is_complete(
    complete_outputs, complete_truncation,
):
    """A complete fetch is not a sample; the tip must be empty.

    Same V3c class PR #3 landed at ``d7d78c5``: the tip is for a SAMPLE,
    not for every list. This test locks the sample-only guard on the
    StandardReceipt call site.

    RED-BASE: attribute access is first, so this test fails on the
    missing field (AttributeError) rather than passing on the ``""`` a
    missing field would produce.
    """
    result = synthesize_response(
        complete_outputs,
        target_entity="StandardReceipt",
        llm=_forbidden_llm(),
        truncation_by_step=complete_truncation,
    )
    assert isinstance(result, StandardReceiptResponse)
    # Attribute access — raises on the missing field.
    tip = result.narrowing_tip
    assert tip == "", (
        "complete fetch must not carry a tip; got " + repr(tip)
    )


# ─────────────────────────────────────────────────────────────────────
# Test 3 — the scoped path is local (no LLM)
# ─────────────────────────────────────────────────────────────────────


def test_plain_receipt_list_builds_locally_no_llm(
    sampled_outputs, sampled_truncation,
):
    """The scoped StandardReceipt path must not fall to the LLM.

    This test PASSES on the current code — the path is already local,
    as ``synthesizer.py``'s StandardReceipt branch shows. It exists to
    lock that fact: a future change that routes StandardReceipt through
    the model without restoring the hallucination guard would hit
    ``_forbidden_llm``'s AssertionError, which is louder than a silently
    different-shaped answer.

    Precedent: tests/test_synthesizer_aggregation.py:57 and the
    equivalent fixture in tests/test_sample_and_disclose_invoice.py.
    """
    result = synthesize_response(
        sampled_outputs,
        target_entity="StandardReceipt",
        llm=_forbidden_llm(),
        truncation_by_step=sampled_truncation,
    )
    assert isinstance(result, StandardReceiptResponse)
    # The forbidden_llm's side effect would have raised inside
    # synthesize_response if the model had been reached. Reaching this
    # assertion means it was not.
    assert len(result.standard_receipts) == 25


# ─────────────────────────────────────────────────────────────────────
# Test 4 — the tip does not fire on a trivially-complete fetch that
# still reports total_available (edge case: 0 total, 0 rows)
# ─────────────────────────────────────────────────────────────────────


def test_empty_result_does_not_carry_narrowing_tip():
    """The empty-result short-circuit fires before the tip guard.

    When ``_all_buckets_empty(outputs)`` is true, synthesize_response
    returns early with an empty response (the "No receipts found"
    summary) and no tip is computed — ``total_available`` for an empty
    fetch is ``0``, ``len(rows)`` is ``0``, and ``0 < 0`` is false.

    This test is here rather than folded into test 2 because the two
    reach the empty-return-by-different-paths: test 2 reaches it via
    the branch's ``total_available is not None and len(rows) <
    total_available`` guard, this test reaches it via
    ``_all_buckets_empty``. A future change that removed the
    ``_all_buckets_empty`` short-circuit could leave test 2 passing
    while this behavior regressed.
    """
    result = synthesize_response(
        {"standard_receipts": []},
        target_entity="StandardReceipt",
        llm=_forbidden_llm(),
    )
    assert isinstance(result, StandardReceiptResponse)
    # Attribute access — raises on the missing field.
    tip = result.narrowing_tip
    assert tip == "", "empty result must not carry a tip; got " + repr(tip)


# ─────────────────────────────────────────────────────────────────────
# Test 5 — the tip does not leak across entities
# ─────────────────────────────────────────────────────────────────────


def test_tip_labels_do_not_leak_from_invoice(sampled_outputs, sampled_truncation):
    """The StandardReceipt tip names only StandardReceipt labels.

    A StandardReceipt-shaped outputs dict routed through
    ``synthesize_response`` must produce a tip whose labels match
    ``_STANDARD_RECEIPT_FILTER_LABELS`` exactly. This is the inverse of
    the PR #3 V4 negative tests: those asserted Invoice's labels did not
    leak into Supplier/PO; this asserts the reverse for PR #4.

    The two candidate labels (customer name, customer site) are the whole
    of the KG entity-level filter set for StandardReceipt, read at
    ``6b299d0`` via ``_entity_level_filter_types()``.
    """
    result = synthesize_response(
        sampled_outputs,
        target_entity="StandardReceipt",
        llm=_forbidden_llm(),
        truncation_by_step=sampled_truncation,
    )
    assert isinstance(result, StandardReceiptResponse)
    tip = result.narrowing_tip
    assert tip, "sampled StandardReceipt must carry a non-empty tip"
    # Invoice labels must not appear.
    for invoice_label in (
        "supplier", "purchase order", "invoice number",
        "invoice date", "unpaid", "overdue", "pending approval",
    ):
        assert invoice_label not in tip, (
            f"Invoice label {invoice_label!r} leaked into a "
            f"StandardReceipt tip: " + repr(tip)
        )
    # Supplier and PO labels must not appear either.
    for supplier_label in (
        "country", "status", "business relationship",
        "creation date", "last-updated date",
    ):
        assert supplier_label not in tip, (
            f"Supplier/PO label {supplier_label!r} leaked into a "
            f"StandardReceipt tip: " + repr(tip)
        )
