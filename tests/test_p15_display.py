"""p15 display — a readable table, and a sample that says it is a sample.

Two display defects in the first working p15 answer, both visible in
`evidence/t_p15_display.txt`:

1. **The table was unreadable.** `HoldReason` values run to 163 characters, so
   a five-column table emitted lines of 247 characters that wrapped into
   ribbons in any terminal. The widest cell is now clipped at 64 with an
   ellipsis, which is long enough to print every common reason in full —
   345 of the 376 active holds have a reason of 61 characters or less — so the
   only values shortened are the rare long ones.

2. **A 100-row sample was presented as the whole answer.** The table was
   headed "invoicehold (100 record(s))" while the source held 222, and nothing
   said so. That is the SP-005 defect shape: a page size read as a total.

   The cause is specific. Truncation is normally disclosed in the synthesized
   summary, and when synthesis overruns its token cap the summary is skipped —
   taking the disclosure with it. `_truncation_disclosure` re-states it from
   the same executor metadata, so the note survives the summary being dropped.

Both fixes are in the shared projected-table path, so they apply to every
column-named answer, not just p15.
"""

from __future__ import annotations

from spire.rendering.formatters import (
    _MAX_CELL_WIDTH,
    _clip_cell,
    _format_projected_table,
    _truncation_disclosure,
)


# The real widest HoldReason on dev49 (163 characters).
_LONG_REASON = (
    "Invoice price exceeds purchase order price for PO or receipt matched "
    "invoice line and exceeds consumption advice price for consumption advice "
    "matched invoice line."
)
# The most common reason (61 characters, 104 of 376 rows).
_COMMON_REASON = "Total of invoice distributions does not equal invoice amount."


def _rows(reason: str, n: int = 2) -> list[dict]:
    return [
        {
            "InvoiceNumber": f"10130{i}",
            "Supplier": "Progressive Corp",
            "InvoiceAmount": 11192.7,
            "HoldReason": reason,
            "HoldStatus": "On hold",
        }
        for i in range(n)
    ]


# ── the width cap ──────────────────────────────────────────────────


def test_short_values_are_untouched():
    assert _clip_cell("On hold") == "On hold"


def test_a_value_at_the_cap_is_untouched():
    exact = "x" * _MAX_CELL_WIDTH
    assert _clip_cell(exact) == exact


def test_a_long_value_is_clipped_with_an_ellipsis():
    clipped = _clip_cell(_LONG_REASON)

    assert len(clipped) == _MAX_CELL_WIDTH
    assert clipped.endswith("…")
    # Visibly a truncation, not a silently shorter stored value.
    assert clipped != _LONG_REASON


def test_the_common_reason_survives_in_full():
    """345 of 376 holds have a reason this short; clipping them would be loss."""
    assert len(_COMMON_REASON) <= _MAX_CELL_WIDTH
    assert _clip_cell(_COMMON_REASON) == _COMMON_REASON


def test_the_table_has_a_bounded_line_width():
    out = _format_projected_table(
        {"invoicehold": _rows(_LONG_REASON)},
        ["InvoiceNumber", "Supplier", "InvoiceAmount", "HoldReason", "HoldStatus"],
    )

    # Before the cap this table emitted 247-character lines.
    assert max(len(line) for line in out.splitlines()) < 160


def test_the_clip_keeps_the_leading_text_that_distinguishes_rows():
    """A reader must still be able to tell the rows apart."""
    out = _format_projected_table(
        {"invoicehold": _rows(_LONG_REASON)},
        ["HoldReason"],
    )

    assert "Invoice price exceeds purchase order price" in out


def test_header_and_rows_stay_aligned():
    """Clipping the value but not the width (or the reverse) breaks the rule."""
    out = _format_projected_table(
        {"invoicehold": _rows(_LONG_REASON)}, ["InvoiceNumber", "HoldReason"]
    )
    lines = [ln for ln in out.splitlines() if ln.startswith("  101")]
    rule = next(ln for ln in out.splitlines() if "-+-" in ln)

    assert len({len(ln) for ln in lines}) == 1
    assert len(lines[0]) == len(rule)


# ── the truncation disclosure ──────────────────────────────────────


def test_a_truncated_fetch_states_the_real_total():
    note = _truncation_disclosure(
        {
            "metadata_by_step": {
                "invoicehold": {
                    "truncated": True,
                    "total_available": 222,
                    "limit_applied": 100,
                }
            }
        }
    )

    assert "222" in note
    assert "sample" in note


def test_a_complete_fetch_says_nothing():
    """A note about nothing would train the reader to ignore the note."""
    assert (
        _truncation_disclosure(
            {"metadata_by_step": {"invoicehold": {"truncated": False, "total_available": 222}}}
        )
        == ""
    )


def test_no_metadata_says_nothing():
    assert _truncation_disclosure({}) == ""


def test_a_capped_fetch_with_an_unknown_total_still_discloses():
    """'There are more' is still a disclosure; silence would read as complete."""
    note = _truncation_disclosure(
        {"metadata_by_step": {"invoicehold": {"truncated": True, "total_available": None}}}
    )

    assert "more" in note


def test_truncation_by_step_is_read_too():
    """Iterating steps report through the other field; both must be honoured."""
    note = _truncation_disclosure(
        {"truncation_by_step": {"invoiceline": {"truncated": True, "total_available": 184}}}
    )

    assert "184" in note
