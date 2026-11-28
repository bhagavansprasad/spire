"""AP-1 — the Invoice field vocabulary must be at least as wide as the tool.

The defect: `/invoices` returns `DueDate` and `Supplier`,
`tools/invoices.py` projects both, and `kg_entity_field` declared neither. So
a request for a due date was refused with "the following columns aren't
available on Invoice: 'DueDate'" **while the value sat in the row**. Same for
"supplier name", on an entity whose own table printed a Supplier column.

That is a defect by the repository's SME test, not a coverage boundary: an SME
with read access can answer "what is the due date", so refusing it is wrong.
Recorded as AP-1 in docs/plan/module-support/AP_COVERAGE_ASSESSMENT.md §5.

Verified live on dev49 (2026-11-28), invoice ERS-53004-755598:
`DueDate: '2026-12-04'`, `Supplier: 'Staffing Services'`.

Three layers had to agree, and this file pins all three — the KG accepts the
name, the record model carries the value, and the renderer shows a column when
there is one. Fixing one layer alone reproduces the original defect in a new
place, which is exactly what happened to F-086.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spire.synthesizer.p2p import InvoiceRecord, build_invoice_records

REPO = Path(__file__).resolve().parents[1]
SEED = REPO / "scripts" / "sql" / "kg_schema.sql"

# What the pod returns for invoice 1601397, and what /invoices projects.
_POD_ROW = {
    "InvoiceId": 1601397,
    "InvoiceNumber": "ERS-53004-755598",
    "InvoiceDate": "2026-10-04",
    "DueDate": "2026-12-04",
    "InvoiceAmount": 138864.62,
    "InvoiceCurrency": "USD",
    "Supplier": "Staffing Services",
    "SupplierNumber": "1253",
    "PaidStatus": "Unpaid",
    "ApprovalStatus": "Required",
}


# ── the KG half: the names must be accept-able ────────────────────────


def test_due_date_is_a_declared_invoice_field():
    """The seed must declare Invoice.DueDate, or the parser refuses it."""
    text = SEED.read_text()
    assert ("'Invoice', 'DueDate'" in text), (
        "kg_entity_field declares no Invoice.DueDate, so a due-date request "
        "is refused as an unavailable column"
    )


def test_supplier_display_name_is_a_declared_invoice_field():
    text = SEED.read_text()
    assert ("'Invoice', 'Supplier'," in text), (
        "kg_entity_field declares no Invoice.Supplier, so 'supplier name' "
        "is refused on an entity that returns it"
    )


def test_supplier_is_a_display_name_not_a_reference():
    """Role matters: display_name is what makes it renderable as a column.

    SupplierNumber stays the reference/join key; conflating the two is how
    "supplier name" ended up refused while "supplier number" worked.
    """
    text = SEED.read_text()
    line = next(
        ln for ln in text.splitlines()
        if "'Invoice', 'Supplier'," in ln and "INSERT" in ln
    )
    assert "'display_name'" in line, line


def test_due_date_has_no_sql_carrier():
    """REST exposes it; AP_INVOICES_ALL does not. The split is deliberate.

    A kg_sql_column row for DueDate would bind a physical column that does
    not exist — ORA-00904 is the recorded evidence. Adding one would make the
    SQL emitter fabricate a field.
    """
    text = SEED.read_text()
    sql_column_lines = [
        ln for ln in text.splitlines()
        if "INSERT INTO kg_sql_column" in ln and "'Invoice'" in ln
    ]
    assert sql_column_lines, "the kg_sql_column check found no Invoice rows"
    assert not any("'DueDate'" in ln for ln in sql_column_lines), (
        "DueDate must not appear in kg_sql_column — the physical column "
        "does not exist on AP_INVOICES_ALL"
    )


def test_supplier_name_synonym_exists():
    """The legacy phrase was mapped; the everyday one was not."""
    text = SEED.read_text()
    assert "'supplier name'" in text
    assert "'Supplier'" in text


# ── the record half: the value must survive the model ─────────────────


def test_record_carries_the_three_previously_dropped_fields():
    rec = build_invoice_records([_POD_ROW])[0]
    assert rec.due_date == "2026-12-04"
    assert rec.paid_status == "Unpaid"
    assert rec.approval_status == "Required"


def test_record_defaults_to_empty_rather_than_failing():
    """An older row shape degrades to an omitted column, not a crash."""
    rec = build_invoice_records([{"InvoiceId": 1, "InvoiceNumber": "X"}])[0]
    assert rec.due_date == ""
    assert rec.paid_status == ""
    assert rec.approval_status == ""


def test_supplier_name_still_comes_from_the_row():
    """Regression guard: the record already rendered this and must keep it."""
    rec = build_invoice_records([_POD_ROW])[0]
    assert rec.supplier_name == "Staffing Services"
    assert rec.supplier_number == "1253"


def test_paid_status_is_a_status_not_a_money_figure():
    """D-PAY-001: a partly paid invoice is not in 'Paid' status.

    The record carries no amount-paid field on purpose; money must come from
    the header's AmountPaid when AP-2 lands, never from this flag.
    """
    rec = InvoiceRecord(
        invoice_id=1,
        invoice_number="X",
        invoice_date="2026-01-01",
        invoice_amount=100.0,
        supplier_name="S",
        supplier_number="1",
        paid_status="Partially paid",
    )
    assert not hasattr(rec, "amount_paid")
    assert not hasattr(rec, "outstanding")


# ── the renderer half: a column appears only when it has a value ──────


def _render(invoices: list[InvoiceRecord]) -> str:
    from spire.rendering.formatters import _format_synthesized
    from spire.synthesizer.p2p import InvoiceResponse

    return _format_synthesized(InvoiceResponse(summary="", invoices=invoices))


def test_due_and_status_columns_render_when_present():
    out = _render(build_invoice_records([_POD_ROW]))
    assert "Due" in out
    assert "2026-12-04" in out
    assert "Paid" in out
    assert "Approval" in out


def test_plain_invoice_list_is_unchanged():
    """No due date, no statuses -> exactly the six columns it always had.

    The same rule as the PO block's Site/Contact: a column earns its place
    only when some row carries a value, so a plain list renders as before.
    """
    out = _render(
        build_invoice_records(
            [{"InvoiceId": 1, "InvoiceNumber": "X", "InvoiceDate": "2026-01-01",
              "InvoiceAmount": 10.0, "Supplier": "S", "SupplierNumber": "1"}]
        )
    )
    assert "2026-01-01" in out
    for absent in ("| Due", "| Paid", "| Approval"):
        assert absent not in out, f"{absent!r} appeared with no data behind it"
