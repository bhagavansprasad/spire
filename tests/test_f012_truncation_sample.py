"""F-012 regression — a capped fetch with no source total must be
narrated as a sample, not presented as the complete answer.

F-012: 'invoices for supplier 1252 over 10000' returns 20 rows. The
summary says nothing about the sample — 20 rows read as the count.
Cause: ``local_list_summary`` emits a count line only when
``total_available`` is not None; on the composite-filter path
``total_available`` is None (the tool's honest 'unknown total'), so
nothing is said about the sample.

The fix: ``local_list_summary`` gains a ``truncated`` flag, threaded
from each plain-list branch's truncation entry. When ``truncated`` is
True and ``total_available`` is None, the summary says the result is
a sample.

Deterministic — no LLM, no pod. Both defect and fix live in
deterministic synthesizer code.
"""
from __future__ import annotations

from spire.synthesizer.synthesizer import synthesize_response


def _invoices(n: int) -> list[dict]:
    return [
        {
            "InvoiceId": i,
            "InvoiceNumber": f"INV-{i:04d}",
            "InvoiceDate": "2022-03-15",
            "InvoiceAmount": 50000,
            "InvoiceCurrency": "USD",
            "Supplier": "Lee Supplies",
            "SupplierNumber": "1252",
        }
        for i in range(n)
    ]


def test_truncated_sample_with_unknown_total_is_narrated_as_sample():
    """F-012's reproducer: 20 invoice rows, total_available=None,
    truncated=True. The answer must say the result is a sample."""
    outputs = {"invoices": _invoices(20)}
    truncation = {
        "invoices": {
            "total_available": None,
            "truncated": True,
            "limit_applied": 25,
        }
    }
    result = synthesize_response(
        outputs,
        target_entity="Invoice",
        truncation_by_step=truncation,
    )
    assert "sample" in result.summary.lower(), (
        f"F-012: a capped fetch with no source total was not narrated "
        f"as a sample. Summary was: {result.summary!r}"
    )


def test_truncated_via_metadata_also_narrated():
    """The truncation flag may ride in metadata_by_step rather than
    truncation_by_step (non-iterating steps). Same outcome expected."""
    outputs = {"invoices": _invoices(20)}
    metadata = {
        "invoices": {
            "total_available": None,
            "truncated": True,
            "limit_applied": 25,
        }
    }
    result = synthesize_response(
        outputs,
        target_entity="Invoice",
        metadata_by_step=metadata,
    )
    assert "sample" in result.summary.lower(), (
        f"F-012: truncation in metadata_by_step was not narrated. "
        f"Summary was: {result.summary!r}"
    )


def test_untruncated_list_not_narrated_as_sample():
    """F-012's guard: a complete list is not a sample. The fix must not
    fire on a fetch that completed."""
    outputs = {"invoices": _invoices(5)}
    result = synthesize_response(outputs, target_entity="Invoice")
    assert "sample" not in result.summary.lower(), (
        f"F-012 over-reach: a complete list gained a 'sample' caveat. "
        f"Summary was: {result.summary!r}"
    )


def test_populated_total_still_uses_the_count_line():
    """The other guard: with a known total the existing 'Showing N of M'
    line is the honest one. The fix must not add a 'sample' sentence on
    top of it."""
    outputs = {"invoices": _invoices(20)}
    truncation = {
        "invoices": {
            "total_available": 48931,
            "truncated": True,
            "limit_applied": 25,
        }
    }
    result = synthesize_response(
        outputs,
        target_entity="Invoice",
        truncation_by_step=truncation,
    )
    # The existing count line fires (20 of 48,931).
    assert "48,931" in result.summary, (
        f"F-012: with a known total the 'Showing N of M' line should "
        f"still fire. Summary was: {result.summary!r}"
    )
