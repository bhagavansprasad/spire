"""
Regression tests for BUG-1 Step 3 — the supplier SITE and supplier
CONTACT on a PO answer.

BACKGROUND

After Step 1 (strip) and Step 2 (parser prompt rule), the S1 prompt
answers correctly with the supplier name read from the PO header. Two
fields the SME asked for (four_bugs.md §5.1, option c) were still
missing from the answer:

  - SupplierSite ('JGA Progress US' for PO 701337): fetched by the
    by_id tool (it was already in _PROJECTED_FIELDS), but dropped by
    the synthesizer — PurchaseOrderRecord did not carry it, so the
    display never showed it.

  - SupplierContactDisplayName ('Seth Ries' for PO 701337): not
    fetched by the tool at all — not in _PROJECTED_FIELDS.

The fix spans three layers, exactly as the probe
(scripts/verify_bug1_step3.py) showed: tool, synthesizer schema + both
builders, display formatter.

These tests pin all three layers. They do NOT touch the live pod — the
builders and the display are pure functions; the tool's projection is a
module constant.
"""

from __future__ import annotations

from spire.mcp_server.tools.purchase_order_by_id import _PROJECTED_FIELDS
from spire.synthesizer.p2p import (
    BuyerInfo,
    PurchaseOrderRecord,
    PurchaseOrderResponse,
    build_po_with_children,
    build_purchase_order_records,
)
from spire.rendering.formatters import _format_synthesized


# ── Layer 1: tool projection ─────────────────────────────────────────


def test_tool_projects_supplier_site():
    """Regression guard for behaviour that was already correct."""
    assert "SupplierSite" in _PROJECTED_FIELDS


def test_tool_projects_supplier_contact_display_name():
    """The new projection field. Without it the contact never reaches the
    synthesizer, and 'Seth Ries' cannot be shown."""
    assert "SupplierContactDisplayName" in _PROJECTED_FIELDS


# ── Layer 2: typed record ────────────────────────────────────────────


def test_record_defaults_site_and_contact_to_empty_strings():
    """Both fields default to '' — matching supplier_name / status, and
    keeping the record constructible without them so existing tests and
    callers need no change."""
    record = PurchaseOrderRecord(
        po_header_id=1,
        order_number="701337",
        status="Open",
        supplier_name="JGA",
        supplier_id=300000047414635,
    )
    assert record.supplier_site == ""
    assert record.supplier_contact == ""


def test_record_accepts_the_new_fields():
    record = PurchaseOrderRecord(
        po_header_id=1,
        order_number="701337",
        status="Open",
        supplier_name="JGA",
        supplier_id=300000047414635,
        supplier_site="JGA Progress US",
        supplier_contact="Seth Ries",
    )
    assert record.supplier_site == "JGA Progress US"
    assert record.supplier_contact == "Seth Ries"


# ── Layer 2: builders ────────────────────────────────────────────────


def _po_row(**over):
    """One executor row shaped like the by_id tool's projection."""
    row = {
        "POHeaderId": 300000081255594,
        "OrderNumber": "701337",
        "Status": "Open",
        "StatusCode": "OPEN",
        "Supplier": "JGA",
        "SupplierId": 300000047414635,
        "SupplierSite": "JGA Progress US",
        "SupplierContactDisplayName": "Seth Ries",
        "Buyer": "White, Eleanor",
        "BuyerId": 300000076218768,
    }
    row.update(over)
    return row


def test_build_purchase_order_records_copies_site_and_contact():
    [record] = build_purchase_order_records([_po_row()])
    assert record.supplier_site == "JGA Progress US"
    assert record.supplier_contact == "Seth Ries"


def test_build_purchase_order_records_tolerates_missing_site_and_contact():
    """A row with null site/contact must not raise — the record fields
    fall back to ''."""
    [record] = build_purchase_order_records([
        _po_row(SupplierSite=None, SupplierContactDisplayName=None),
    ])
    assert record.supplier_site == ""
    assert record.supplier_contact == ""


def test_build_po_with_children_copies_site_and_contact():
    """The children builder is a SECOND path that instantiates the
    record. A fix that touched only build_purchase_order_records would
    leave 'Show PO X and its lines' without site or contact."""
    outputs = {"po": [_po_row()]}
    [record] = build_po_with_children(outputs, {"po": "po"})
    assert record.supplier_site == "JGA Progress US"
    assert record.supplier_contact == "Seth Ries"


def test_build_po_with_children_tolerates_missing_site_and_contact():
    outputs = {
        "po": [_po_row(SupplierSite=None, SupplierContactDisplayName=None)]
    }
    [record] = build_po_with_children(outputs, {"po": "po"})
    assert record.supplier_site == ""
    assert record.supplier_contact == ""


# ── Layer 3: display ─────────────────────────────────────────────────


def _response(site="JGA Progress US", contact="Seth Ries", buyer=None):
    record = PurchaseOrderRecord(
        po_header_id=300000081255594,
        order_number="701337",
        status="Open",
        supplier_name="JGA",
        supplier_id=300000047414635,
        supplier_site=site,
        supplier_contact=contact,
        buyer=buyer,
    )
    return PurchaseOrderResponse(
        summary="PO 701337.",
        purchase_orders=[record],
        truncation_notes=[],
    )


def test_display_renders_site_column_when_present():
    out = _format_synthesized(_response())
    assert "JGA Progress US" in out
    assert "Site" in out


def test_display_renders_contact_column_when_present():
    out = _format_synthesized(_response())
    assert "Seth Ries" in out
    assert "Contact" in out


def test_display_omits_site_and_contact_columns_when_empty():
    """Same rule as Buyer: the column only appears when at least one row
    carries a value. A blank Site/Contact column on a plain PO list
    would be noise."""
    out = _format_synthesized(_response(site="", contact=""))
    assert "JGA Progress US" not in out
    assert "Seth Ries" not in out


def test_display_renders_site_contact_and_buyer_together():
    """The three conditional columns are independent — presence of one
    does not suppress the others."""
    buyer = BuyerInfo(
        person_id=300000076218768, display_name="White, Eleanor"
    )
    out = _format_synthesized(_response(buyer=buyer))
    assert "White, Eleanor" in out
    assert "JGA Progress US" in out
    assert "Seth Ries" in out