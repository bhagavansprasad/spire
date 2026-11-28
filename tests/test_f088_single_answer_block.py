"""F-088 — one result must not print two `Answer:` blocks.

The defect, observed 2026-11-28 on a manual p14 run:

    Answer:
    Showing 25 of 935 invoices.
    ...
    Truncation:
      - invoices: 935 total in source; 25 returned.
    --- Tip ---
    Reading all 935 invoices is slow. Narrow with a filter: ...

    Answer:                                  <- second block, same result
    Note: the following columns aren't available on Invoice: 'due date',
    'remaining balance'.
    Available columns: ...
    invoices (25 record(s)) — columns: InvoiceNumber, InvoiceDate, InvoiceAmount

Two summaries of one result, and the second buries a column refusal inside a
successful list — which reads as a partial failure of a query that succeeded.

S3 was left unresolved in the register ("two candidates, not yet
distinguished"). The mechanism is now known, and it is neither of those
candidates: `render_answer` and `render_cli_stdout` both emit the synthesized
summary AND then the projected-columns table, and BOTH opened with the literal
heading `Answer:`. The second is a continuation, not a second answer.

A second symptom in the same shape, seen on p12: the first block was EMPTY —
`Answer:` with nothing under it — because `_format_synthesized`'s summary_only
branch printed the heading unconditionally, even for an empty summary.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from spire.rendering import formatters
from spire.synthesizer.p2p import InvoiceResponse


class _Menu:
    def available_columns(self, entity):
        return ["InvoiceNumber", "InvoiceDate", "InvoiceAmount"]


def _intent(fields):
    return SimpleNamespace(
        target_entity="Invoice",
        filters=[],
        include=[],
        fields=fields,
        unresolved_fields=[],
        aggregate=None,
        compare=None,
        count_only=False,
        open_only=False,
        invoice_limit=None,
        balance_only=False,
    )


def _response(summary: str, invoices=None) -> InvoiceResponse:
    return InvoiceResponse(
        summary=summary,
        invoices=invoices or [],
        truncation_notes=[],
        narrowing_tip="",
    )


def _state(fields, summary):
    return {
        "intent": _intent(fields),
        "outputs": {"invoices": [{"InvoiceNumber": "X"}]},
        "response": _response(summary),
        "synth_failed": False,
    }


# ── the heading count ─────────────────────────────────────────────────


def test_one_result_gets_one_answer_heading():
    """A non-empty summary plus the table must not produce two headings."""
    out = formatters.render_cli_stdout(
        _state(["InvoiceNumber"], "Showing 25 of 935 invoices."), _Menu()
    )
    assert out.count("Answer:") == 1, out


def test_empty_summary_puts_the_heading_on_the_table():
    """p12: an empty summary printed a bare `Answer:` and then a second one.

    The fix must leave exactly ONE heading — on the table, because nothing
    was printed above it.
    """
    out = formatters.render_cli_stdout(_state(["InvoiceNumber"], ""), _Menu())
    assert out.count("Answer:") == 1, out
    assert out.startswith("Answer:"), out


def test_table_still_carries_a_heading_when_standing_alone():
    """No fields at all -> the table IS the answer and needs its heading.

    Reached when only unresolved columns exist: there is no summary to print,
    so the table must not be left headless.
    """
    state = _state([], "")
    state["intent"].unresolved_fields = ["business unit"]
    out = formatters.render_cli_stdout(state, _Menu())
    assert out.count("Answer:") == 1, out


# ── the empty-summary block ───────────────────────────────────────────


def test_empty_summary_prints_no_bare_heading():
    """p12 rendered 'Answer:' with nothing under it. Say nothing instead."""
    out = formatters._format_synthesized(
        _response(""), summary_only=True
    )
    assert out.strip() == "", repr(out)


def test_non_empty_summary_still_prints():
    out = formatters._format_synthesized(
        _response("Showing 25 of 935 invoices."), summary_only=True
    )
    assert "Answer:" in out
    assert "Showing 25 of 935 invoices." in out


# ── the table itself ──────────────────────────────────────────────────


def test_projected_table_honours_the_heading_flag():
    outputs = {"invoices": [{"InvoiceNumber": "X", "InvoiceAmount": 10}]}
    with_heading = formatters._format_projected_table(
        outputs, ["InvoiceNumber", "InvoiceAmount"],
        None, ["InvoiceNumber", "InvoiceAmount"], "Invoice",
    )
    without = formatters._format_projected_table(
        outputs, ["InvoiceNumber", "InvoiceAmount"],
        None, ["InvoiceNumber", "InvoiceAmount"], "Invoice",
        heading=False,
    )
    assert with_heading.startswith("Answer:")
    assert not without.startswith("Answer:")
    # The content is otherwise identical — only the heading differs.
    assert "InvoiceNumber" in without


def test_unresolved_only_path_keeps_its_heading():
    """The 'no resolvable column' early return must not lose its heading."""
    outputs = {"invoices": [{"InvoiceNumber": "X"}]}
    out = formatters._format_projected_table(
        outputs, [], ["business unit"], ["InvoiceNumber"], "Invoice",
    )
    assert out.startswith("Answer:")
    assert "business unit" in out


def test_unresolved_only_path_can_suppress_its_heading():
    outputs = {"invoices": [{"InvoiceNumber": "X"}]}
    out = formatters._format_projected_table(
        outputs, [], ["business unit"], ["InvoiceNumber"], "Invoice",
        heading=False,
    )
    assert not out.startswith("Answer:")
    assert "business unit" in out
