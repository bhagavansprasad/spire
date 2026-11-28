"""R1a — the invoice row carries the money; compute what it implies.

Three prompts in the AP litmus asked for columns the answer could not show:

    p14  "remaining balance"
    p16  "outstanding amount", "number of overdue days"
    p18  "validation status", "accounting status"

A direct probe of `/invoices` for `ERS-53004-755598` returned **101 fields**,
including `AmountPaid`, `ValidationStatus`, `AccountingStatus` and
`AccountingDate`. Nothing was missing from the pod; the projection was
discarding them, and `OutstandingAmount` / `OverdueDays` had no carrier
column at all and were never computed.

`OutstandingAmount` and `OverdueDays` are derived here rather than fetched.
The floor at zero and the None-for-paid rule are the two decisions worth
pinning: a negative "still owed" and an overdue count against settled money
are both wrong answers that would look plausible in a table.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from spire.mcp_server.tools.invoices import _derive_invoice_fields


def _row(**overrides):
    base = {
        "InvoiceAmount": 1000.0,
        "AmountPaid": 250.0,
        "DueDate": "2026-01-01",
        "PaidStatus": "Unpaid",
    }
    base.update(overrides)
    return base


# ── OutstandingAmount ──────────────────────────────────────────────


def test_outstanding_is_amount_minus_paid():
    assert _derive_invoice_fields(_row())["OutstandingAmount"] == 750.0


def test_outstanding_is_floored_at_zero():
    """A prepayment or credit leaves AmountPaid above InvoiceAmount.

    "Still owed: -500" is not an answer anyone can act on, and the
    outstanding-by-supplier aggregation already applies GREATEST(..., 0).
    The item view must not disagree with the ranking it sits beside.
    """
    row = _row(InvoiceAmount=100.0, AmountPaid=600.0)
    assert _derive_invoice_fields(row)["OutstandingAmount"] == 0.0


def test_null_amount_paid_means_nothing_paid():
    row = _row(AmountPaid=None)
    assert _derive_invoice_fields(row)["OutstandingAmount"] == 1000.0


def test_fully_paid_outstanding_is_zero():
    row = _row(AmountPaid=1000.0)
    assert _derive_invoice_fields(row)["OutstandingAmount"] == 0.0


def test_missing_amounts_leave_the_key_absent():
    """No guessing: the renderer prints an em dash for an absent key."""
    row = _row(InvoiceAmount=None, AmountPaid=None)
    assert "OutstandingAmount" not in _derive_invoice_fields(row)


# ── OverdueDays ────────────────────────────────────────────────────


def test_overdue_days_counts_past_due():
    past = (date.today() - timedelta(days=10)).isoformat()
    assert _derive_invoice_fields(_row(DueDate=past))["OverdueDays"] == 10


def test_not_yet_due_is_zero_not_negative():
    future = (date.today() + timedelta(days=5)).isoformat()
    assert _derive_invoice_fields(_row(DueDate=future))["OverdueDays"] == 0


def test_paid_invoice_has_no_overdue_days():
    """A settled invoice is not overdue, however old the due date.

    None rather than 0: "0 days overdue" reads as "due today", which is a
    different statement from "this does not apply".
    """
    past = (date.today() - timedelta(days=400)).isoformat()
    row = _row(DueDate=past, PaidStatus="Paid")
    assert _derive_invoice_fields(row)["OverdueDays"] is None


def test_partially_paid_counts_as_overdue():
    """Partially paid money is still owed, so it is still overdue."""
    past = (date.today() - timedelta(days=3)).isoformat()
    row = _row(DueDate=past, PaidStatus="Partially paid")
    assert _derive_invoice_fields(row)["OverdueDays"] == 3


@pytest.mark.parametrize("bad", [None, "", "not-a-date", "2026-13-45"])
def test_unparseable_due_date_leaves_the_key_absent(bad):
    row = _row(DueDate=bad)
    assert "OverdueDays" not in _derive_invoice_fields(row)


def test_derivation_does_not_disturb_source_fields():
    row = _derive_invoice_fields(_row())
    assert row["InvoiceAmount"] == 1000.0
    assert row["AmountPaid"] == 250.0
    assert row["DueDate"] == "2026-01-01"


def test_the_probe_values_that_prompted_this():
    """ERS-53004-755598 exactly as the pod returned it on 2026-11-28."""
    row = _derive_invoice_fields(
        {
            "InvoiceAmount": 138864.62,
            "AmountPaid": 0,
            "DueDate": "2026-12-04",
            "PaidStatus": "Unpaid",
        }
    )
    assert row["OutstandingAmount"] == 138864.62
    # Due date is in the future relative to the probe date, so not overdue.
    assert row["OverdueDays"] == 0
