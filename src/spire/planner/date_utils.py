"""Date arithmetic for computed iteration filters.

Naive calendar-month math with day clamping, used by
_build_iteration_args_with_computed for filters like
'no_invoices_in_N_months'. Pure functions, no dependency on anything else
in the planner — pulled out on its own because it is the one piece of
plan_builders.py with zero KG or registry involvement.
"""

from __future__ import annotations

from datetime import date


def _compute_date_n_months_ago(months: int, reference_date: date) -> date:
    """
    Return reference_date minus ``months`` months.

    Naive month arithmetic — handles month rollover with day clamping.
    Example: 2026-03-31 minus 1 month -> 2026-02-28 (not 2026-02-31).

    Pure function for testability; reference_date defaulting happens
    in the orchestrator, not here.
    """
    year = reference_date.year
    month = reference_date.month - months
    while month <= 0:
        month += 12
        year -= 1
    # Clamp day to last day of target month.
    day = min(reference_date.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    """Return the number of days in the given (year, month)."""
    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    last_day = (next_month_first - _one_day()).day
    return last_day


def _one_day():
    """Return a one-day timedelta. Helper to avoid a top-level import
    when most of this module doesn't need timedelta."""
    from datetime import timedelta
    return timedelta(days=1)

