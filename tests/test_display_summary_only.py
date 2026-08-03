"""Column queries print the summary and the TABLE — not the record block.

THE BUG THESE PIN
display_formatters' own docstring says the projected table goes
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

from scripts.display_formatters import _format_synthesized
from spire.synthesizer.synthesizer import (
    AddressInfo,
    SupplierRecord,
    SupplierResponse,
    POLifecycleResponse,
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