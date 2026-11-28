"""p15 — invoice holds, and the join that is NOT by invoice number alone.

Discovery (dev49, 2026-11-28): holds live on `/invoiceHolds`, active means
`ReleaseReason is null`, and that predicate is server-side queryable — 374
rows in one page. The invoice row carries no hold field at all.

`/invoiceHolds` does not expose `InvoiceId`, so the amount must be joined
through `/invoices` by invoice number. Invoice numbers are **not unique** on
this pod:

    active holds                    374
    distinct invoice numbers        168
    numbers shared by >1 invoice      6

Invoice 1122 alone is 295,759.13 for Staffing Services and 2,000 for ABDUL — a
number-only join can overstate the held amount by 148x. These tests pin the
supplier corroboration that prevents it, and pin "unsure" to None rather than
an arbitrary row.
"""

from __future__ import annotations

import pytest

from spire.mcp_server.tools.invoice_holds import (
    ACTIVE_HOLD_CLAUSE,
    _is_active,
    _pick_amount,
)


# The real ambiguity, as REST returned it for q=InvoiceNumber='1122'.
_AMBIGUOUS_1122 = [
    {"InvoiceNumber": "1122", "Supplier": "Staffing Services", "InvoiceAmount": 295759.13},
    {"InvoiceNumber": "1122", "Supplier": "ABDUL", "InvoiceAmount": 2000},
]


# ── the amount join ────────────────────────────────────────────────


def test_supplier_disambiguates_the_ambiguous_number():
    """The held invoice is ABDUL's 2,000 — NOT the 295,759.13 next to it."""
    assert _pick_amount(_AMBIGUOUS_1122, "ABDUL") == 2000.0


def test_the_wrong_supplier_is_never_chosen():
    """Guards the 148x error directly."""
    assert _pick_amount(_AMBIGUOUS_1122, "ABDUL") != 295759.13


def test_unknown_supplier_returns_none_not_a_guess():
    """A supplier the rows do not carry must not fall back to a row."""
    assert _pick_amount(_AMBIGUOUS_1122, "Nonexistent Co") is None


def test_unambiguous_number_without_supplier_resolves():
    """One row and no supplier on the hold row: the amount is knowable."""
    rows = [{"InvoiceNumber": "ADV60182", "Supplier": "Advanced Corp", "InvoiceAmount": 20000}]
    assert _pick_amount(rows, None) == 20000.0


def test_ambiguous_number_without_supplier_returns_none():
    assert _pick_amount(_AMBIGUOUS_1122, None) is None


def test_empty_result_returns_none():
    """2 of the 376 active holds are orphans with no invoice row."""
    assert _pick_amount([], "ABDUL") is None


def test_duplicate_supplier_rows_return_none():
    """The composite key is not unique for this number: refuse to choose."""
    rows = [
        {"InvoiceNumber": "X", "Supplier": "Same Co", "InvoiceAmount": 10},
        {"InvoiceNumber": "X", "Supplier": "Same Co", "InvoiceAmount": 20},
    ]
    assert _pick_amount(rows, "Same Co") is None


@pytest.mark.parametrize("bad", [None, "1234.5", True])
def test_non_numeric_amounts_are_not_coerced(bad):
    """A string or a bool is not an amount; do not invent one."""
    rows = [{"InvoiceNumber": "X", "Supplier": "S", "InvoiceAmount": bad}]
    assert _pick_amount(rows, "S") is None


# ── the active-hold test ───────────────────────────────────────────


def test_unreleased_hold_is_active():
    assert _is_active({"ReleaseDate": None, "ReleaseReason": None}) is True


def test_released_hold_is_not_active():
    assert (
        _is_active(
            {"ReleaseDate": "2014-01-03T13:21:03+00:00", "ReleaseReason": "Fixed."}
        )
        is False
    )


def test_partially_released_fields_are_not_active():
    """Either release marker means the hold is over."""
    assert _is_active({"ReleaseDate": "2014-01-03T13:21:03+00:00"}) is False
    assert _is_active({"ReleaseReason": "Variance corrected."}) is False


# ── the server-side predicate ──────────────────────────────────────


def test_the_predicate_is_the_one_rest_accepts():
    """Pinned because it was measured: ReleaseDate is null does NOT work.

    RELEASE_LOOKUP_CODE IS NULL and RELEASE_REASON IS NULL select the same
    376 rows in the pod's database; only the latter is queryable over REST.
    Changing this string silently turns a 1-page lookup back into a 14,772-row
    scan, or empties the result entirely.
    """
    assert ACTIVE_HOLD_CLAUSE == "ReleaseReason is null"
