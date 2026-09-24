"""F-051 — a fields+include intent must render the child, not just the table.

The bug: `render_answer`'s column-mode branch passes summary_only=True
whenever `fields` is non-empty, regardless of whether `include` is also
set. summary_only suppresses the typed record block; the projected table
that follows renders only the PARENT bucket. Any child content the
include fetched is built into the response and never shown.

The fix (in this branch, commit 2): `summary_only=not intent.include`.

These tests assert the CALL SHAPE, not the rendered text — the text
belongs to the real _format_synthesized, and mocking it keeps the
assertion narrow: which branch did the gate pick?
"""
from types import SimpleNamespace
from unittest.mock import patch

from spire.rendering import formatters


class _Menu:
    def available_columns(self, entity):
        return ["TransactionNumber", "TransactionId"]


def _intent(fields, include):
    return SimpleNamespace(
        target_entity="ReceivablesInvoice",
        filters=[],
        include=include,
        fields=fields,
        unresolved_fields=[],
        aggregate=None,
        compare=None,
        count_only=False,
        open_only=False,
        invoice_limit=None,
        balance_only=False,
    )


def _state(fields, include):
    return {
        "intent": _intent(fields, include),
        "outputs": {"receivables_invoices": [{"TransactionNumber": "5"}]},
        "response": SimpleNamespace(
            summary="", truncation_notes=[], narrowing_tip=""
        ),
        "synth_failed": False,
    }


def _run(fields, include, capture):
    with patch.object(
        formatters, "_format_synthesized", side_effect=capture
    ), patch.object(
        formatters, "_format_projected_table", return_value="TABLE"
    ):
        formatters.render_answer(
            _state(fields, include), _Menu(), lambda _: None
        )


def test_fields_plus_include_renders_full_response():
    """The F-051 fix: summary_only must be False when include is set."""
    calls: list[bool] = []

    def capture(response, summary_only=False):
        calls.append(summary_only)
        return "FULL" if not summary_only else "SUMMARY"

    _run(["TransactionNumber"], ["ReceivablesInvoiceTransactionDFF"], capture)

    assert False in calls, (
        "F-051: fields+include must call _format_synthesized with "
        "summary_only=False so the child content renders. Observed "
        f"summary_only values: {calls!r}"
    )


def test_fields_only_still_suppresses_records():
    """F-020 regression guard: no include -> summary_only=True stays."""
    calls: list[bool] = []

    def capture(response, summary_only=False):
        calls.append(summary_only)
        return "SUMMARY" if summary_only else "FULL"

    _run(["TransactionNumber"], [], capture)

    assert calls == [True], (
        "F-020 regression: fields-only must still pass summary_only=True. "
        f"Observed: {calls!r}"
    )
