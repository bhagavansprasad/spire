"""F-039 - aggregate comparisons stop over-claiming with "under-invoiced".

The bug: `Compare ordered vs invoiced for our top 3 suppliers` printed

    - EIP Inc: ordered 865,287,107.89, PO-matched invoiced 710,712.31
      -- under-invoiced by 864,576,395.58 (3,207 non-PO invoices excluded).

across three suppliers whose unmatched-invoice ratios were 97.7%,
99.4%, and 97.6% respectively. The number is arithmetically correct
(the tool computed ordered minus PO-matched invoiced exactly); the
word "under-invoiced" asserts a billing state the arithmetic does
not establish. What it establishes is a document-matching state:
EIP's invoices almost never carry a PO number to match against.

The fix introduces _aggregate_difference_phrase, used by the two
aggregate summarizers (supplier-scoped and top-N). When the unmatched
ratio crosses MOST_UNMATCHED_RATIO, it reports the state of the data
instead of a billing behaviour. The single-PO summarizer continues to
use _direction_phrase: an invoice not linked to one specific PO is
genuinely outside that comparison, so the wording is fair there.
"""

import pytest

from spire.synthesizer.aggregation import (
    MOST_UNMATCHED_RATIO,
    _aggregate_difference_phrase,
    _direction_phrase,
    _summarize_po_comparison,
    _summarize_supplier_comparison,
    _summarize_top_suppliers_comparison,
)


# ---------------------------------------------------------------------
# Threshold constant: sanity
# ---------------------------------------------------------------------


def test_threshold_is_a_sane_fraction():
    """The constant is a ratio between 0 and 1, not a percentage."""
    assert 0 < MOST_UNMATCHED_RATIO < 1


# ---------------------------------------------------------------------
# The helper, in isolation
# ---------------------------------------------------------------------


def test_high_unmatched_negative_diff_describes_matching_gap():
    """97.7% unmatched, ordered > invoiced -> document-matching phrase.
    Must NOT contain 'under-invoiced'."""
    phrase = _aggregate_difference_phrase(-864_576_395.58, 3207, 3284)
    assert "under-invoiced" not in phrase
    assert "864,576,395.58" in phrase
    assert "no PO-matched invoice" in phrase


def test_high_unmatched_positive_diff_states_the_arithmetic():
    """Positive diff with high unmatched -> a different neutral phrase."""
    phrase = _aggregate_difference_phrase(1_500_000.00, 90, 100)
    assert "under-invoiced" not in phrase
    assert "over-invoiced" not in phrase
    assert "PO-matched invoiced exceeds ordered by" in phrase
    assert "1,500,000.00" in phrase


def test_high_unmatched_zero_diff_reports_equality():
    phrase = _aggregate_difference_phrase(0.0, 80, 100)
    assert phrase == "PO-matched invoiced equals ordered"


def test_low_unmatched_negative_diff_uses_direction_phrase():
    """10% unmatched -> _direction_phrase's 'under-invoiced' is fair;
    the excluded set is a minority of what was compared."""
    phrase = _aggregate_difference_phrase(-50_000.00, 10, 100)
    assert phrase == _direction_phrase(-50_000.00)
    assert phrase.startswith("under-invoiced")


def test_low_unmatched_positive_diff_uses_direction_phrase():
    phrase = _aggregate_difference_phrase(50_000.00, 10, 100)
    assert phrase == _direction_phrase(50_000.00)
    assert phrase.startswith("over-invoiced")


def test_exactly_at_threshold_uses_matching_gap_phrase():
    """Boundary is >=: exactly MOST_UNMATCHED_RATIO crosses over."""
    phrase = _aggregate_difference_phrase(-100.0, 75, 100)
    assert "under-invoiced" not in phrase
    assert "no PO-matched invoice" in phrase


def test_just_below_threshold_uses_direction_phrase():
    phrase = _aggregate_difference_phrase(-100.0, 74, 100)
    assert "under-invoiced" in phrase


def test_zero_total_falls_through_to_direction_phrase():
    """Defensive: no invoices at all is not a matching gap; the caller's
    own wording applies."""
    phrase = _aggregate_difference_phrase(-100.0, 0, 0)
    assert phrase == _direction_phrase(-100.0)


# ---------------------------------------------------------------------
# The summarizers
# ---------------------------------------------------------------------


def _comparison_row(supplier, ordered, invoiced, unmatched, total_invoices):
    return {
        "supplier": supplier,
        "total_ordered": ordered,
        "total_invoiced": invoiced,
        "total_difference": round(invoiced - ordered, 2),
        "unmatched_invoice_count": unmatched,
        "invoice_count": total_invoices,
        "po_count": 100,
    }


def test_top_suppliers_high_unmatched_drops_under_invoiced():
    """The F-039 reproducer, reduced. Three suppliers, all with >97%
    unmatched. 'under-invoiced' must not appear anywhere in the output."""
    data = {
        "suppliers": [
            _comparison_row("EIP Inc", 865_287_107.89, 710_712.31, 3207, 3284),
            _comparison_row("Staffing Services", 328_053_963.10, 31_312.91, 2422, 2436),
            _comparison_row("JGA", 159_598_443.36, 4_566_124.36, 2267, 2322),
        ],
        "returned": 3,
    }
    out = _summarize_top_suppliers_comparison(data)
    assert "under-invoiced" not in out
    assert "no PO-matched invoice" in out
    # The parenthetical disclosure is preserved.
    assert "3,207 non-PO invoices excluded" in out
    assert "2,422 non-PO invoices excluded" in out
    assert "2,267 non-PO invoices excluded" in out


def test_top_suppliers_low_unmatched_keeps_under_invoiced():
    """Small excluded set -> current wording unchanged."""
    data = {
        "suppliers": [
            _comparison_row("Somebody", 100_000.00, 60_000.00, 5, 50),
        ],
        "returned": 1,
    }
    out = _summarize_top_suppliers_comparison(data)
    assert "under-invoiced" in out


def test_supplier_scoped_high_unmatched_drops_under_invoiced():
    data = {
        "found": True,
        "ambiguous": False,
        "supplier": "EIP Inc",
        "total_ordered": 865_287_107.89,
        "total_invoiced": 710_712.31,
        "total_difference": -864_576_395.58,
        "unmatched_invoice_count": 3207,
        "invoice_count": 3284,
        "po_count": 2015,
    }
    out = _summarize_supplier_comparison(data)
    assert "under-invoiced" not in out
    assert "no PO-matched invoice" in out


def test_single_po_still_uses_under_invoiced():
    """The single-PO shape is unchanged: an invoice not linked to one
    specific PO is genuinely outside that comparison."""
    data = {
        "found": True,
        "order_number": "162034",
        "supplier": "Lee Supplies",
        "ordered": 758.00,
        "invoiced": 100.00,
        "difference": -658.00,
        "invoice_count": 1,
    }
    out = _summarize_po_comparison(data)
    assert "under-invoiced" in out
    assert "658.00" in out
