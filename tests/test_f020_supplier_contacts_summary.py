"""F-020 - the supplier-contacts summary no longer comma-joins admin names.

The bug: `Get Supplier contacts` printed a long comma-joined run-on of
every administrative contact's name at the end of the summary line:

    Showing 25 of 307 suppliers. These 25 suppliers have 93 contacts
    between them. Lee, Ryan, Lee, Jason, Cross, Sara, ... - administrative
    contacts.

Two harms in one shape. The sentence was unreadably long (27 names today,
47 when the finding was recorded), and it asserted a property -
`is_administrative=True` for each named contact - that the reader could
not check against the tables below, which showed only name and email.

The fix moves the property to where the reader can verify it: each
contact row now carries an "Admin" column when at least one contact in
the response is flagged. The summary states only the counts.

These tests exercise the display layer. The synthesizer change (removing
the run-on sentence) is verified end-to-end via the pipeline run in the
fix file's V4 - its summary is built inline in `synthesize_response`, and
reaching that path in a unit test would need the full pipeline.
"""

from spire.rendering.formatters import _format_synthesized
from spire.synthesizer.p2p import (
    ContactInfo,
    SupplierRecord,
    SupplierResponse,
)


def _contact(cid, name, email, admin=False):
    return ContactInfo(
        supplier_contact_id=cid,
        contact_name=name,
        email=email,
        is_administrative=admin,
    )


def _supplier(sid, name, contacts):
    return SupplierRecord(
        supplier_id=sid,
        supplier_number=str(sid),
        supplier_name=name,
        contacts=contacts,
    )


def _response(suppliers):
    return SupplierResponse(
        summary="Get Supplier contacts.",
        suppliers=suppliers,
    )


# ---------------------------------------------------------------------
# Presence / absence of the Admin column
# ---------------------------------------------------------------------


def test_admin_column_present_when_any_contact_is_admin():
    resp = _response([
        _supplier(1, "Lee Supplies", [
            _contact(10, "Lee, Ryan", "ryan@x", admin=True),
            _contact(11, "Hertz, Maria", "maria@x", admin=False),
        ]),
    ])
    out = _format_synthesized(resp)
    assert "Admin" in out


def test_admin_column_absent_when_no_contact_is_admin():
    resp = _response([
        _supplier(1, "Lee Supplies", [
            _contact(10, "Lee, Ryan", "ryan@x", admin=False),
            _contact(11, "Hertz, Maria", "maria@x", admin=False),
        ]),
    ])
    out = _format_synthesized(resp)
    assert "Admin" not in out


def test_admin_column_is_per_response_not_per_supplier():
    """If any contact in the whole response is flagged, every contact
    table renders the column - so column counts are consistent across
    the answer. A single flagged contact in supplier A must not leave
    supplier B's table two-column while A's is three-column."""
    resp = _response([
        _supplier(1, "A", [_contact(10, "X", "x@x", admin=True)]),
        _supplier(2, "B", [_contact(20, "Y", "y@y", admin=False)]),
    ])
    out = _format_synthesized(resp)
    assert out.count("Admin") >= 2


# ---------------------------------------------------------------------
# The marker distinguishes flagged from unflagged
# ---------------------------------------------------------------------


def test_admin_marker_y_for_flagged():
    resp = _response([
        _supplier(1, "Mixed", [
            _contact(10, "Admin Person", "a@x", admin=True),
            _contact(11, "Regular Person", "r@x", admin=False),
        ]),
    ])
    out = _format_synthesized(resp)
    rows = [ln for ln in out.splitlines() if "Admin Person" in ln]
    assert rows, "Admin Person not found in output"
    assert rows[0].rstrip().endswith("Y")


def test_admin_marker_em_dash_for_unflagged():
    resp = _response([
        _supplier(1, "Mixed", [
            _contact(10, "Admin Person", "a@x", admin=True),
            _contact(11, "Regular Person", "r@x", admin=False),
        ]),
    ])
    out = _format_synthesized(resp)
    rows = [ln for ln in out.splitlines() if "Regular Person" in ln]
    assert rows, "Regular Person not found in output"
    assert rows[0].rstrip().endswith("—")


# ---------------------------------------------------------------------
# Regression guard against the run-on pattern reappearing in display
# ---------------------------------------------------------------------


def test_no_run_on_sentence_in_display():
    """The run-on was emitted by the synthesizer, not the display layer;
    this guards against someone reintroducing the shape here by accident.
    The bad shape is `<name>, <name>, ... - administrative contacts.`"""
    resp = _response([
        _supplier(1, "A", [_contact(10, "One", "1@x", admin=True)]),
    ])
    out = _format_synthesized(resp)
    assert "— administrative contacts" not in out
    assert "— administrative contact." not in out
