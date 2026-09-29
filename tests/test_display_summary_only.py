"""Column queries print the summary and the TABLE — not the record block.

THE BUG THESE PIN
formatters.py's own docstring says the projected table goes
"instead of the typed per-entity block". The runners honoured that only
by accident: the typed block was printed unconditionally, but on the
query that made it hurt — "List active suppliers with supplier name,
supplier number, and address" — synthesis overran the token cap and
failed, so synth_failed fired and only the table printed.

Once the synthesizer stopped failing on that shape, nothing enforced the
rule. The output became ~200 lines of

    - Lee Supplies (SupplierId=..., SupplierNumber=1252)
        address: 7 Saxon Close,AGHORY,Armagh,UNITED KINGDOM
        address: 6302 England St,HOUSTON, TX 77021 Harris
        ... 23 more, for each of 25 suppliers ...

followed by a table containing the same data, one line per supplier.
A bug fix removed the failure that had been hiding a display rule.
"""

import pytest

from spire.rendering.formatters import _format_synthesized
from spire.synthesizer.synthesizer import (
    AddressInfo,
    SupplierRecord,
    SupplierResponse,
    POLifecycleResponse,
    CustomerAccountResponse,
    CustomerAccountRecord,
    AccountReceiptInfo,
)

@pytest.fixture
def response_with_addresses():
    return SupplierResponse(
        summary="This report shows 25 active suppliers, out of 425 available.",
        suppliers=[
            SupplierRecord(
                supplier_id=300000047414503,
                supplier_number="1252",
                supplier_name="Lee Supplies",
                addresses=[
                    AddressInfo(
                        address_id=1,
                        country="United Kingdom",
                        city="AGHORY",
                        state="Armagh",
                        formatted_address="7 Saxon Close,AGHORY,Armagh,UNITED KINGDOM",
                    ),
                    AddressInfo(
                        address_id=2,
                        country="United States",
                        city="HOUSTON",
                        state="TX",
                        formatted_address="6302 England St,HOUSTON, TX 77021 Harris",
                    ),
                ],
            )
        ],
        truncation_notes=["suppliers: 425 total in source; 25 examined."],
    )


def test_summary_only_omits_the_record_block(response_with_addresses):
    """The whole point: no per-supplier lines, no address lines."""
    out = _format_synthesized(response_with_addresses, summary_only=True)
    assert "25 active suppliers" in out
    assert "Suppliers:" not in out
    assert "address:" not in out
    assert "Lee Supplies" not in out


def test_summary_only_keeps_truncation_notes(response_with_addresses):
    """Truncation must survive. It is the one thing the table cannot say —
    a table of 25 rows looks complete whether or not 425 exist."""
    out = _format_synthesized(response_with_addresses, summary_only=True)
    assert "Truncation:" in out
    assert "425 total in source" in out


def test_full_render_is_unchanged(response_with_addresses):
    """Non-column queries still get the record block. This mode is opt-in;
    a regression here would strip detail from every other query."""
    out = _format_synthesized(response_with_addresses)
    assert "Suppliers:" in out
    assert "Lee Supplies" in out
    # Records render as a table (many) or field-per-line (one) since
    # 2026-08-03; this used to assert the bullet form "address: ...".
    # The point of the test is that the DETAIL survives, not the layout,
    # so it asserts the value and not the prefix. A supplier with more
    # than one address shows the first and a count of the rest.
    assert "7 Saxon Close,AGHORY,Armagh,UNITED KINGDOM" in out
    assert "more)" in out


def test_summary_only_on_a_shape_without_summary_falls_back():
    """Defensive: an unexpected shape must render something rather than an
    empty answer. Printing nothing would look identical to the synthesis
    failure this change exists to stop masking."""
    out = _format_synthesized({"raw": "dict"}, summary_only=True)
    assert "raw" in out


def test_none_response_is_unchanged():
    assert _format_synthesized(None, summary_only=True) == (
        "Synthesized response: (none)"
    )

def test_lifecycle_not_found_display_asserts_nothing():
    """Defect 2, display half: an absent PO gets a header and a sentence.

    The verdict row and the stage line are the damage. The row reads
    "cannot be determined" per leg, which implies the order exists; the
    stage line prints an empty owner and an empty risk as if they were
    values. Emptiness of `legs` is the signal — a found record always
    carries all four.
    """
    response = POLifecycleResponse(
        summary="No purchase order 999999 exists.",
        order_number="999999",
        legs=[],
        lifecycle_stage="Not found",
        responsible_team="",
        risk="",
        recommended_action="",
        exceptions=["no purchase order found with OrderNumber '999999'"],
    )

    rendered = _format_synthesized(response)

    assert "999999" in rendered
    assert "No purchase order 999999 exists." in rendered
    assert "cannot be determined" not in rendered
    assert "Stage:" not in rendered
    assert "Owner:" not in rendered
    assert "Amounts" not in rendered
    assert "no purchase order found with OrderNumber" not in rendered
    assert response.exceptions  # kept on the response, just not printed    

# ─────────────────────────────────────────────────────────────────────
# Record rendering — tables, added 2026-08-03
#
# Eight entity branches printed records as bullets with the field names
# repeated inline; column queries had printed tables since projection
# shipped. One renderer now serves both.
#
# These are here because the rendering change shipped on visual
# inspection alone and broke this file twice on the way. Every defect it
# had was found by running a prompt and reading the screen — "1
# suppliers", a doubled blank line, a contacts column joined with commas
# where the names themselves contain commas. None was found by reading
# code, and none of them would have been caught by the tests that
# existed.
# ─────────────────────────────────────────────────────────────────────


from spire.rendering.formatters import _is_quantity, _render_records


def test_many_records_render_as_a_table():
    """Two or more records get a header, a rule, and aligned columns."""
    out = "\n".join(
        _render_records(
            "Suppliers",
            [
                {"Supplier": "Lee Supplies", "SupplierNumber": "1252"},
                {"Supplier": "JGA", "SupplierNumber": "1254"},
            ],
            ["Supplier", "SupplierNumber"],
            "none",
        )
    )
    assert "Supplier" in out and "SupplierNumber" in out
    assert "-+-" in out          # the rule
    assert " | " in out          # the separator
    assert "Lee Supplies" in out and "JGA" in out


def test_one_record_renders_vertically():
    """A one-row table is as wide as its widest value and forces the
    reader across the screen to read a single thing. Field per line."""
    out = "\n".join(
        _render_records(
            "Suppliers",
            [{"Supplier": "Dell Inc.", "SupplierNumber": "1255"}],
            ["Supplier", "SupplierNumber"],
            "none",
        )
    )
    assert "-+-" not in out      # NOT a table
    assert "Supplier" in out
    assert "Dell Inc." in out
    # field : value, one per line
    assert len([ln for ln in out.splitlines() if " : " in ln]) == 2


def test_missing_values_show_an_em_dash():
    """Absent must be visibly different from empty."""
    out = "\n".join(
        _render_records(
            "Receipts",
            [{"Receipt": "R1", "Bank": None}, {"Receipt": "R2", "Bank": "HSBC"}],
            ["Receipt", "Bank"],
            "none",
        )
    )
    assert "—" in out


def test_no_records_uses_the_empty_text():
    out = _render_records("Suppliers", [], ["Supplier"], "No suppliers found.")
    assert out == ["No suppliers found."]


def test_quantities_right_align_and_identifiers_do_not():
    """The alignment rule, which has now been wrong in both directions.

    First version: right-align anything numeric, minus a denylist of
    id-ish names. "Transaction" carries no marker, so a transaction
    NUMBER right-aligned as though it were an amount while
    "AccountNumber" did not — the same kind of value rendered two ways
    depending on whether its name happened to contain a marker word.

    Inverted to an allowlist of quantity names. Its predicted miss
    appeared on the first run: "Invoices" (261, 122, 78) is a count with
    no quantity word in its name, and left-aligned with the text.
    """
    assert _is_quantity("Amount", [-150.0, 10000.0])
    assert _is_quantity("Total Spend", ["141,171,590.98"])
    assert _is_quantity("Open Receivables", ["165,428,563.24"])
    assert _is_quantity("Rank", [1, 2, 3])
    assert _is_quantity("Invoices", [261, 122])       # the allowlist miss
    assert _is_quantity("Lines", [4])

    assert not _is_quantity("Transaction", [11001, 130766])
    assert not _is_quantity("CustomerTransactionId", [300000313072555])
    assert not _is_quantity("SupplierNumber", ["1252"])
    assert not _is_quantity("Customer", ["DMART"])


def test_a_quantity_name_with_textual_values_is_not_right_aligned():
    """BOTH tests must pass — the name AND the values. A column called
    "Total" holding words is not a quantity."""
    assert not _is_quantity("Total", ["high", "low"])
    assert not _is_quantity("Total", [])


def test_an_empty_summary_leaves_no_blank_line(response_with_addresses):
    """An empty summary is a legitimate answer now: with records in a
    table below, there is often nothing to say the table does not show.
    Appending "" anyway left a blank line under "Answer:" and another
    under that, which reads as something having gone missing.
    """
    response_with_addresses.summary = ""
    out = _format_synthesized(response_with_addresses)
    assert "Answer:\n\n\n" not in out
    assert "Lee Supplies" in out



# ─────────────────────────────────────────────────────────────────────
# Child-table headers state the honest scope: "showing N of M" when the
# tool reported more of a child than the rows shown, and a plain header
# otherwise. The account with thousands of receipts must not present ten
# as the whole set. Uses child_totals on the record (populated upstream
# from the executor's truncation metadata).
# ─────────────────────────────────────────────────────────────────────


def _account_with_receipts(child_totals):
    return CustomerAccountResponse(
        summary="",
        customer_accounts=[
            CustomerAccountRecord(
                account_id=300000047368512,
                account_number="26360",
                customer_name="ABC Application Software",
                open_receivables=45989.16,
                transactions_due=44017.52,
                receipts=[
                    AccountReceiptInfo(
                        receipt_id=300000343850475,
                        receipt_number="155766_03",
                        receipt_date="2026-09-08",
                        amount=118.75,
                        currency="USD",
                        receipt_method="check",
                        state="Unapplied",
                        unapplied_amount=118.75,
                    ),
                    AccountReceiptInfo(
                        receipt_id=300000344034011,
                        receipt_number="1464202",
                        receipt_date="2026-09-08",
                        amount=800.0,
                        currency="USD",
                        receipt_method="Lockbox",
                        state="Unapplied",
                        unapplied_amount=800.0,
                    ),
                ],
                child_totals=child_totals,
            )
        ],
        truncation_notes=[],
    )


def test_child_header_states_showing_n_of_m_when_truncated():
    """Two receipts shown of 2,319 -> the child table header says so, so
    the page is never mistaken for the whole set."""
    out = _format_synthesized(_account_with_receipts({"receipts": 2319}))
    assert "— receipts (showing 2 of 2,319)" in out
    # The rows still render.
    assert "155766_03" in out
    assert "1464202" in out


def test_child_header_is_plain_when_not_truncated():
    """total_available equal to the rows shown is not truncation — no
    count in the header, nothing unverifiable claimed."""
    out = _format_synthesized(_account_with_receipts({"receipts": 2}))
    assert "— receipts" in out
    assert "showing" not in out


def test_child_header_is_plain_when_total_unknown():
    """No total for the child (empty map) -> plain header."""
    out = _format_synthesized(_account_with_receipts({}))
    assert "— receipts" in out
    assert "showing" not in out
