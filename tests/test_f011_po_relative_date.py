"""F-011 - PurchaseOrder.created_in_last_n_months.

Reproducer: "Purchase orders older than 6 months"

Pre-fix the pipeline refused with `unsupported_filter — needs relative date
filtering (older than 6 months), which is not supported`, while the KG's
created_before row names exactly this question class as the filter's
purpose. Post-fix the sysprompt emits created_in_last_n_months; the planner
computes the ISO cutoff and forwards it as created_before.
"""

from datetime import date

import pytest

from spire.planner.plan_builders import _build_entity_fetcher_args


def test_relative_months_computed_to_iso_cutoff():
    """{"months": 6} + a pinned reference_date -> ISO date of (ref - 6mo)."""
    args = _build_entity_fetcher_args(
        [{"type": "created_in_last_n_months", "value": {"months": 6}}],
        "PurchaseOrder",
        reference_date=date(2026, 9, 23),
    )
    assert args == {"created_before": "2026-03-23"}


def test_relative_months_bare_int_accepted():
    """A bare int value ({months: N} shorthand) is tolerated."""
    args = _build_entity_fetcher_args(
        [{"type": "created_in_last_n_months", "value": 12}],
        "PurchaseOrder",
        reference_date=date(2026, 9, 23),
    )
    assert args == {"created_before": "2025-09-23"}


def test_relative_months_day_clamp():
    """Naive month arithmetic clamps the day (2026-03-31 - 1mo -> 2026-02-28)."""
    args = _build_entity_fetcher_args(
        [{"type": "created_in_last_n_months", "value": {"months": 1}}],
        "PurchaseOrder",
        reference_date=date(2026, 3, 31),
    )
    assert args == {"created_before": "2026-02-28"}


def test_relative_months_rejects_zero():
    with pytest.raises(ValueError):
        _build_entity_fetcher_args(
            [{"type": "created_in_last_n_months", "value": {"months": 0}}],
            "PurchaseOrder",
            reference_date=date(2026, 9, 23),
        )


def test_relative_months_rejects_negative():
    with pytest.raises(ValueError):
        _build_entity_fetcher_args(
            [{"type": "created_in_last_n_months", "value": {"months": -1}}],
            "PurchaseOrder",
            reference_date=date(2026, 9, 23),
        )


def test_relative_months_rejects_bool():
    """True == 1 in Python; must not be accepted as one month."""
    with pytest.raises(ValueError):
        _build_entity_fetcher_args(
            [{"type": "created_in_last_n_months", "value": {"months": True}}],
            "PurchaseOrder",
            reference_date=date(2026, 9, 23),
        )


def test_absolute_date_unchanged():
    """The existing absolute-date filter is unaffected by the new branch."""
    args = _build_entity_fetcher_args(
        [{"type": "created_before", "value": "2024-01-01"}],
        "PurchaseOrder",
        reference_date=date(2026, 9, 23),
    )
    assert args == {"created_before": "2024-01-01"}
