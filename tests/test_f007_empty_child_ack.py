"""F-007 regression — a requested child that came back empty must be
acknowledged in the answer.

F-007: ``Get tax lines for invoice 300000248096352`` returns the AR
invoice and its line, and never mentions tax. The user asked a specific
question ("what tax was charged") and got an answer that answers a
different one, with no signal that the specific part was answered
"none".

The mechanism is local. ``synthesize_response``'s ReceivablesInvoice
branch builds the response without an LLM and its summary from
``local_list_summary``, which sees only the parent rows and has no
notion of requested children. Meanwhile ``children`` (passed to
``build_receivables_invoice_records``) already carries the signal: a
bucket present-but-empty means the user asked and there were none; an
absent bucket means the user never asked. The two were indistinguishable
in the answer, and F-007's fix uses that distinction.

Three tests below, one per state the fix must distinguish:

  * empty-but-asked  -> acknowledge ("no tax lines")
  * not-asked        -> silence (no spurious "no tax lines")
  * populated        -> no acknowledgement (the data speaks for itself)

None of these touches the LLM. The ReceivablesInvoice path has been
local since before F-007; the summary comes from local_list_summary and
the new acknowledgement from _empty_ar_invoice_child_notes, both pure.
"""
from __future__ import annotations

from spire.synthesizer.synthesizer import (
    ReceivablesInvoiceResponse,
    synthesize_response,
)

# The fix's helper is imported lazily inside its tests, not at module
# level. On a reverted tree the module-level import would fail at
# COLLECTION, aborting the whole file and telling us nothing about the
# behavioural tests (1–4). Importing locally means the four behavioural
# tests still run and give their own answer, and the two helper tests
# fail on the missing symbol at test time — a stronger, more granular
# signal than one collection error.
def _helper():
    from spire.synthesizer.synthesizer import _empty_ar_invoice_child_notes
    return _empty_ar_invoice_child_notes


# A minimal invoice + one line. Field names match the executor's actual
# output, since synthesize_response's shape detection keys on them
# (CustomerTransactionId, TransactionNumber, InvoiceCurrencyCode).
def _parent_row() -> dict:
    return {
        "CustomerTransactionId": 300000248096352,
        "TransactionNumber": "61765",
        "BillToCustomerName": "ABC Corporation Americas",
        "BillToCustomerNumber": "26370",
        "InvoiceCurrencyCode": "GBP",
        "EnteredAmount": 39969,
        "InvoiceBalanceAmount": 39969,
        "TransactionDate": "2017-06-30",
        "InvoiceStatus": "Complete",
    }


def _line_row() -> dict:
    return {
        "CustomerTransactionLineId": 300000248096353,
        "LineNumber": 1,
        "Description": "Consultation",
        "Quantity": 1,
        "UnitSellingPrice": 39969,
        "LineAmount": 39969,
        "CustomerTransactionId": 300000248096352,
    }


# ─────────────────────────────────────────────────────────────────────
# The bug — an empty requested child must be acknowledged
# ─────────────────────────────────────────────────────────────────────


def test_requested_empty_tax_lines_acknowledged_in_summary():
    """F-007's reproducer.

    The tax bucket is PRESENT and EMPTY — the executor emits a bucket for
    every step the plan ran, and the plan ran a tax step because the
    user asked. The response must say so.
    """
    outputs = {
        "receivables_invoices": [_parent_row()],
        "receivables_invoice_lines": [_line_row()],
        "receivablestaxline": [],  # present, empty — the reproducer
    }
    result = synthesize_response(
        outputs, target_entity="ReceivablesInvoice", llm=None
    )
    assert isinstance(result, ReceivablesInvoiceResponse)
    assert "no tax lines" in result.summary.lower(), (
        f"F-007: the answer did not acknowledge the empty tax bucket. "
        f"Summary was: {result.summary!r}"
    )


# ─────────────────────────────────────────────────────────────────────
# The over-reach guard — a plain AR query must NOT gain the line
# ─────────────────────────────────────────────────────────────────────


def test_unrequested_tax_not_mentioned():
    """Battery prompt 4: 'Show the AR invoice with CustomerTransactionId
    300000248096352' (no tax include).

    The executor never ran a tax step, so no tax bucket is present at
    all. The answer must stay silent about tax — the user did not ask.
    This is the guard against emitting the acknowledgement
    unconditionally.
    """
    outputs = {
        "receivables_invoices": [_parent_row()],
        "receivables_invoice_lines": [_line_row()],
        # no receivablestaxline key — nothing was asked, nothing was
        # fetched, nothing to acknowledge
    }
    result = synthesize_response(
        outputs, target_entity="ReceivablesInvoice", llm=None
    )
    assert isinstance(result, ReceivablesInvoiceResponse)
    assert "tax" not in result.summary.lower(), (
        f"F-007 over-reach: a plain AR invoice query gained a tax "
        f"acknowledgement. Summary was: {result.summary!r}"
    )


# ─────────────────────────────────────────────────────────────────────
# Sibling — a populated child must NOT gain the acknowledgement
# ─────────────────────────────────────────────────────────────────────


def test_populated_tax_lines_not_acknowledged():
    """Battery prompts 2 and 3: invoice 1002 with 8 tax rows.

    The acknowledgement is for ABSENCE. A populated bucket renders its
    own tax sub-tables and needs no "no tax lines" line contradicting
    them.
    """
    outputs = {
        "receivables_invoices": [_parent_row()],
        "receivables_invoice_lines": [_line_row()],
        "receivablestaxline": [
            {
                "CustomerTransactionLineId": 111,
                "ParentCustomerTransactionLineId": 300000248096353,
                "TaxLineNumber": 1,
                "Tax": "STATE",
                "TaxRate": 6.5,
                "TaxAmount": 100,
                "TaxableAmount": 1000,
                "TaxJurisdictionCode": "CA",
            }
        ],
    }
    result = synthesize_response(
        outputs, target_entity="ReceivablesInvoice", llm=None
    )
    assert isinstance(result, ReceivablesInvoiceResponse)
    assert "no tax lines" not in result.summary.lower(), (
        f"F-007: populated tax rows produced a 'no tax lines' "
        f"acknowledgement. Summary was: {result.summary!r}"
    )


# ─────────────────────────────────────────────────────────────────────
# The helper, directly — one call so a rename fails loudly here
# ─────────────────────────────────────────────────────────────────────


def test_helper_returns_nothing_when_no_children_present():
    """A dict with no AR-child keys at all yields an empty list."""
    assert _helper()({}) == []


def test_helper_returns_one_line_per_empty_child():
    """Two empty buckets produce two acknowledgements."""
    notes = _helper()(
        {
            "receivables_invoice_lines": [{"x": 1}],  # populated
            "receivablestaxline": [],                 # empty
            "receivablesinvoicetransactiondff": [],   # empty
        }
    )
    assert len(notes) == 2
    joined = " ".join(notes).lower()
    assert "tax lines" in joined
    assert "flexfield values" in joined
    assert "line items" not in joined
