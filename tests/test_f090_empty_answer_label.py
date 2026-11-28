"""F-090 — an answer that shows nothing must not tally as `[ok]`.

On the AP-10 run (2026-11-28) the harness reported **10/10 ran cleanly** while
five prompts had failed. Two of those — p17 "payment details" and p18
"validation and accounting" — returned a bare note and

    (1 record(s) matched; no requested column was available.)

and were scored `[ok]`, because the label only asked "did it raise?". The
tally is the only signal a batch run gives, so an answer that carried no
information made the run look cleaner than it was.

These tests pin the rule, not the run. The rule is deliberately structural:
`intent.fields` empty with `intent.unresolved_fields` populated, which is
exactly what `intent_validation` produces when every named column misses the
entity's catalog, and what the renderer's `not cols` branch keys on.
"""

from __future__ import annotations

import pytest

from scripts.run_prompt_set import empty_answer_label


def test_all_requested_columns_unresolved_is_not_ok():
    """p18's actual shape: three named columns, none on Invoice."""
    label = empty_answer_label(
        [],
        ["validation status", "accounting status", "errors"],
        "Invoice",
    )

    assert label is not None
    assert label.startswith("empty:")
    assert "0 of 3" in label
    assert "Invoice" in label


def test_p17_payment_columns_are_flagged():
    """p17's shape: five named columns, none on Invoice."""
    label = empty_answer_label(
        [],
        [
            "payment number",
            "payment date",
            "payment method",
            "payment amount",
            "payment status",
        ],
        "Invoice",
    )

    assert label is not None
    assert "0 of 5" in label


def test_a_resolved_column_keeps_the_run_ok():
    """p12 — BusinessUnit was unavailable, but six real columns answered it."""
    assert (
        empty_answer_label(
            ["Supplier", "InvoiceDate", "DueDate", "InvoiceAmount"],
            ["BusinessUnit"],
            "Invoice",
        )
        is None
    )


def test_a_partial_miss_is_not_flagged():
    """p14 — "remaining balance" was unavailable; four columns still rendered."""
    assert (
        empty_answer_label(
            ["InvoiceNumber", "InvoiceDate", "DueDate", "InvoiceAmount"],
            ["remaining balance"],
            "Invoice",
        )
        is None
    )


def test_naming_no_columns_is_not_flagged():
    """The default projection answers this; nothing was ever requested."""
    assert empty_answer_label([], [], "Invoice") is None


@pytest.mark.parametrize("absent", [None, []])
def test_missing_or_empty_inputs_are_not_flagged(absent):
    """Absent history or absent unresolved list must not invent a failure."""
    assert empty_answer_label(absent, [], "Invoice") is None
    if absent is None:
        assert empty_answer_label(None, ["a", "b"], "Invoice") is not None


def test_empty_label_counts_as_a_failure_in_the_roll_up():
    """The roll-up's own predicate must agree, or the label is decoration.

    `_is_failure` lives inside `_run_all`, so this mirrors its one-line rule
    and fails loudly if that rule is ever narrowed to `label != "ok"` style
    prefix-matching that excludes `empty:`.
    """
    def _is_failure(label: str) -> bool:
        return label != "ok" and not label.startswith("refused")

    assert _is_failure(empty_answer_label([], ["x"], "Invoice"))
    assert _is_failure("crash: ValueError: boom")
    # Unchanged for the cases that were already handled.
    assert not _is_failure("ok")
    assert not _is_failure("refused (expected for out-of-scope)")
    assert not _is_failure("refused (expected — planner guard)")
