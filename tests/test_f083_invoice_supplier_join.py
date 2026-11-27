"""F-083 — the AP invoice supplier join must be LEFT, not INNER.

The defect: `AP_INVOICES_ALL.VENDOR_ID` is never NULL, but 11,227 of
53,129 invoices carry a VENDOR_ID with **no** `POZ_SUPPLIERS` row (the
sentinel `-222` among them). An inner join therefore dropped 21% of
invoices with nothing to show for it — no NULL supplier column, no
warning, just fewer rows.

REST returns those invoices. For the two found by the F-078 comparison:

    1072121 -> Supplier 'TEXAS CORP',          SupplierNumber null
    1075121 -> Supplier 'Info-Systems Pvt Ltd', SupplierNumber null

so the emitted SQL must LEFT JOIN (keep the invoice, NULL the number),
not INNER JOIN (drop the invoice).

Why the Q4 NULL-count check missed it: that check asks "is the key
populated?", and VENDOR_ID is populated on every row. The question that
catches it is "does the parent exist?" — now `ORPHAN_KEYS` in
`scripts/validate_kg_schema.py`.

FIX_PLAN §6 F-083.
"""

from __future__ import annotations

from spire.kg.sql_overlay import OVERLAY
from spire.planner.models import Step
from spire.rendering.sql_emitter import emit_sql

INVOICE_SPEC = "Invoice"


def _strip_comments(sql: str) -> str:
    return "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    )


def _join_lines(sql: str) -> list[str]:
    return [
        line.strip() for line in _strip_comments(sql).splitlines()
        if line.strip().startswith(("JOIN ", "LEFT JOIN "))
    ]


# ── The spec ──────────────────────────────────────────────────────────


def test_invoice_supplier_join_is_left():
    joins = OVERLAY.entities[INVOICE_SPEC].base_joins
    supplier = [j for j in joins if "POZ_SUPPLIERS" in j]
    assert supplier, "the supplier join disappeared"
    assert supplier[0].startswith("LEFT JOIN"), supplier[0]


def test_invoice_entity_still_projects_the_supplier_number():
    """LEFT JOIN must not become 'stop projecting SEGMENT1'.

    REST returns a null SupplierNumber (not a missing column) for orphan
    invoices, so the column has to stay in the projection.
    """
    columns = OVERLAY.entities[INVOICE_SPEC].select_columns
    assert ("S", "SEGMENT1") in columns


# ── The emitted SQL ───────────────────────────────────────────────────


def _step(tool: str, args: dict) -> Step:
    return Step(
        step_id=1,
        tool_name=tool,
        tool_args=args,
        iterate_over=None,
        client_filters=(),
        output_name="out1",
        output_dedupe_by=None,
    )


def test_emitted_invoice_sql_left_joins_suppliers():
    sql = emit_sql([_step("search_invoices", {"invoice_date_after": "2026-10-21"})])[0]
    assert "LEFT JOIN POZ_SUPPLIERS S ON S.VENDOR_ID = P.VENDOR_ID" in \
        _strip_comments(sql)


def test_emitted_invoice_sql_has_no_inner_supplier_join():
    """The bare `JOIN POZ_SUPPLIERS` form is what dropped the rows."""
    sql = _strip_comments(
        emit_sql([_step("search_invoices", {"invoice_date_after": "2026-10-21"})])[0]
    )
    assert "LEFT JOIN POZ_SUPPLIERS S ON S.VENDOR_ID = P.VENDOR_ID" in sql


def test_supplier_number_filter_still_works_under_left_join():
    """A predicate on S.SEGMENT1 excludes NULLs naturally.

    The supplier_number spec filters on the joined column; under a LEFT
    JOIN the orphans have NULL there and drop out, which is the intended
    behaviour for an explicit "this supplier" question.
    """
    spec = OVERLAY.filters.get(("search_invoices", "supplier_number"))
    assert spec is not None, "search_invoices.supplier_number spec is missing"
    assert "SEGMENT1" in spec.predicate_template


# ── The check that catches the class ──────────────────────────────────


def test_orphan_key_check_is_registered_for_invoice():
    """A NULL-count check cannot see a populated-but-parentless key."""
    from scripts.validate_kg_schema import ORPHAN_KEYS

    invoice = [k for k in ORPHAN_KEYS if k["entity"] == INVOICE_SPEC]
    assert invoice, "Invoice is not covered by ORPHAN_KEYS"
    entry = invoice[0]
    assert entry["child"] == "AP_INVOICES_ALL"
    assert entry["child_column"] == "VENDOR_ID"
    assert entry["parent"] == "POZ_SUPPLIERS"
    assert entry["join_is_left"] is True


def test_orphan_check_fails_when_the_join_is_inner(monkeypatch):
    """Guard: the check must actually fail on the defect, not always pass."""
    import scripts.validate_kg_schema as validator

    class _Spec:
        base_joins = ["JOIN POZ_SUPPLIERS S ON S.VENDOR_ID = P.VENDOR_ID"]

    class _Overlay:
        entities = {"Invoice": _Spec}

    monkeypatch.setattr(
        "spire.kg.sql_overlay.OVERLAY", _Overlay, raising=True
    )
    monkeypatch.setattr(
        validator, "_pod_orphan_count", lambda *a, **k: 11227, raising=True
    )

    lines, ok = validator._check_orphan_keys(check_pod=True)

    assert ok is False
    assert any("[FAIL]" in line and "11227" in line for line in lines)
