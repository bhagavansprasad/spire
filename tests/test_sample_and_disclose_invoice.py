"""Sample-and-disclose for Invoice — PR #3's starting test file.

Two groups of tests:

  (1) Locks the ALREADY-GREEN behaviour on master at 9724282 — the
      plain-list Invoice path is built locally, no LLM. These pass
      today (test_synthesize_response_invoice_entity_selects_invoice_
      schema in test_synthesizer.py:477 already locks this; these
      re-assert it in this PR's own file so the PR carries its own
      evidence).

  (2) The RED: narrowing_tip must be populated on the plain-list
      path once the Invoice sample is disclosure. InvoiceResponse
      carries no narrowing_tip field today (p2p.py:340-347), so
      these tests fail at collection with AttributeError — the
      red shape the fix is meant to remove. This is the V7 base:
      red because the field is absent, not because of a post-hoc
      stash.
"""

from __future__ import annotations

from spire.synthesizer.synthesizer import (
    InvoiceResponse,
    synthesize_response,
)


def _forbidden_llm():
    """An LLM that fails the test if anything touches it.

    Same shape as tests/test_synthesizer.py::_forbidden_llm — the
    plain-list Invoice path must not reach the model. If PR #3's fix
    accidentally routes the plain-list shape through the LLM, this
    raises before the test's assertions, and the failure names the
    regression.
    """
    from unittest.mock import MagicMock

    llm = MagicMock()
    llm.with_structured_output.side_effect = AssertionError(
        "synthesize_response called the LLM on the plain-list Invoice "
        "path — this shape is built locally and must not fall to the "
        "model."
    )
    return llm


def _invoice_rows(n: int) -> list[dict]:
    """n plain invoice rows, shaped like the executor's projection."""
    return [
        {
            "InvoiceId": 9000 + i,
            "InvoiceNumber": f"INV-{9000 + i}",
            "InvoiceDate": "2022-03-15",
            "InvoiceAmount": 1000.0 + i,
            "InvoiceCurrency": "USD",
            "Supplier": "Lee Supplies",
            "SupplierNumber": "1252",
        }
        for i in range(n)
    ]


def _truncation(total: int) -> dict:
    """The truncation entry _local_truncation reads to build the count
    line and (post-fix) the tip's total."""
    return {
        "invoices": {
            "total_available": total,
            "truncated": True,
            "limit_applied": 25,
        }
    }


# ---------------------------------------------------------------------
# Group 1 — already-green on master: plain-list Invoice is local.
# ---------------------------------------------------------------------


def test_plain_invoice_list_builds_locally_no_llm():
    """The plain single-bucket Invoice list is built from the rows,
    with no LLM call. Already true on master (synthesizer.py:1088-1113,
    p2p.py:1182-1201). This is the Invoice-side sibling of the
    Supplier and PurchaseOrder coverage PR #1 and PR #2 added.
    """
    outputs = {"invoices": _invoice_rows(5)}
    result = synthesize_response(
        outputs, target_entity="Invoice", llm=_forbidden_llm()
    )
    assert isinstance(result, InvoiceResponse)
    assert len(result.invoices) == 5
    assert result.invoices[0].invoice_number == "INV-9000"


# ---------------------------------------------------------------------
# Group 2 — RED on master: narrowing_tip field absent.
# ---------------------------------------------------------------------


def test_plain_invoice_list_carries_narrowing_tip():
    """The plain-list Invoice response must carry a populated
    narrowing_tip when the source total is known and larger than the
    sample. This is the shape PR #3 adds — RED on master at 9724282
    because InvoiceResponse has no narrowing_tip field
    (p2p.py:340-347). The test fails at attribute access
    (result.narrowing_tip), which is the correct red: the field is
    absent, not the value empty.
    """
    outputs = {"invoices": _invoice_rows(5)}
    result = synthesize_response(
        outputs,
        target_entity="Invoice",
        truncation_by_step=_truncation(total=48_931),
        llm=_forbidden_llm(),
    )
    assert isinstance(result, InvoiceResponse)
    # The narrowing tip must be a non-empty string on the sample path.
    tip = getattr(result, "narrowing_tip", None)
    assert isinstance(tip, str) and tip, (
        "InvoiceResponse must carry a non-empty narrowing_tip on the "
        "plain-list path when the source total exceeds the sample. "
        "Missing today (p2p.py:340-347); PR #3 adds the field."
    )
    # The total is the one the truncation entry carries — not the
    # row count. Same rule as the Supplier and PO tips.
    assert "48,931" in tip, (
        f"tip must name the source total from the truncation entry; "
        f"got {tip!r}"
    )


def test_narrowing_tip_absent_when_source_is_complete():
    """A complete fetch is not a sample, so no tip. The Supplier and
    PO tips return "" when total is unknown or not exceeded. PR #3's
    Invoice tip must behave the same way — RED today because the
    field is absent, GREEN after the fix with the same total-null
    branch.
    """
    outputs = {"invoices": _invoice_rows(3)}
    result = synthesize_response(
        outputs, target_entity="Invoice", llm=_forbidden_llm()
    )
    tip = getattr(result, "narrowing_tip", None)
    # Post-fix: field exists and is empty (no total known, no tip).
    assert tip == "", (
        f"narrowing_tip must be the empty string when the source "
        f"total is unknown or not exceeded; got {tip!r}"
    )


# ---------------------------------------------------------------------
# V3c red — the tip must NOT fire on a non-sample Invoice result.
#
# At commit d964bb6, `invoice_number LEE-01-1006-111` (a by-number
# fetch, one row, complete) produced:
#   "Reading all 1 invoices is slow. Narrow with a filter: ..."
# The tip is for a SAMPLE; a complete fetch of one row is not one.
# Fix: guard the call-site in the plain-invoice branch on
# `len(rows) < total_available`. These two tests pin the red.
# ---------------------------------------------------------------------


def test_by_invoice_number_does_not_carry_narrowing_tip():
    """A single-invoice fetch is not a sample, so the tip must be empty.

    RED at d964bb6 (V3c): the tip fires on a 1-row complete fetch with
    the false sentence 'Reading all 1 invoices is slow'.
    """
    outputs = {
        "invoices": [
            {
                "InvoiceId": 489503,
                "InvoiceNumber": "LEE-01-1006-111",
                "InvoiceDate": "2016-10-17",
                "InvoiceAmount": 11138.34,
                "InvoiceCurrency": "USD",
                "Supplier": "Lee Supplies",
                "SupplierNumber": "1252",
            }
        ]
    }
    truncation = {
        "invoices": {
            "total_available": 1,
            "truncated": False,
            "limit_applied": 25,
        }
    }
    result = synthesize_response(
        outputs,
        target_entity="Invoice",
        truncation_by_step=truncation,
        llm=_forbidden_llm(),
    )
    assert isinstance(result, InvoiceResponse)
    assert result.narrowing_tip == "", (
        f"narrowing_tip must be empty on a single-invoice fetch; "
        f"got {result.narrowing_tip!r}"
    )


def test_complete_fetch_does_not_carry_narrowing_tip():
    """A complete fetch (all matching rows returned) is not a sample.

    RED at d964bb6: the same plain-invoice branch builds the tip
    whenever total_available is non-null, regardless of whether the
    rows are the whole set.
    """
    outputs = {"invoices": _invoice_rows(3)}
    truncation = {
        "invoices": {
            "total_available": 3,
            "truncated": False,
            "limit_applied": 25,
        }
    }
    result = synthesize_response(
        outputs,
        target_entity="Invoice",
        truncation_by_step=truncation,
        llm=_forbidden_llm(),
    )
    assert isinstance(result, InvoiceResponse)
    assert result.narrowing_tip == "", (
        f"narrowing_tip must be empty when all matching rows were "
        f"returned; got {result.narrowing_tip!r}"
    )


# ---------------------------------------------------------------------
# V3b coverage lock — the empty result carries no tip.
#
# Exercised live in V3b (`invoices for supplier 1252 over 999999999`):
# empty result, no tip, no truncation block. This test locks that
# behaviour in PR #3's own file.
# ---------------------------------------------------------------------


def test_empty_invoice_list_carries_no_tip():
    """An empty Invoice result has no tip.

    Two paths converge on empty: the all-buckets-empty shortcut (no
    truncation block at all) and the plain-invoice branch with a
    truncation entry of total 0. Both must produce empty
    narrowing_tip. V3b live evidence at t_v3b_invoice_empty.txt
    (though that file was produced under the pre-fix `d964bb6`;
    the guard from d7d78c5 (`len(rows) < total_available`) preserves
    the empty case since 0 < 0 is False).
    """
    # Case 1: empty invoices bucket, no truncation entry (all-buckets
    # empty shortcut).
    outputs = {"invoices": []}
    result = synthesize_response(
        outputs,
        target_entity="Invoice",
        llm=_forbidden_llm(),
    )
    assert isinstance(result, InvoiceResponse)
    assert result.narrowing_tip == "", (
        f"empty result (no truncation) must have empty narrowing_tip; "
        f"got {result.narrowing_tip!r}"
    )

    # Case 2: empty invoices bucket with a truncation entry of total 0.
    outputs = {"invoices": []}
    truncation = {
        "invoices": {
            "total_available": 0,
            "truncated": False,
            "limit_applied": 25,
        }
    }
    result = synthesize_response(
        outputs,
        target_entity="Invoice",
        truncation_by_step=truncation,
        llm=_forbidden_llm(),
    )
    assert isinstance(result, InvoiceResponse)
    assert result.narrowing_tip == "", (
        f"empty result (total 0) must have empty narrowing_tip; "
        f"got {result.narrowing_tip!r}"
    )
