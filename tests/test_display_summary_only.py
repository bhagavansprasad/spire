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
    assert "address: 7 Saxon Close,AGHORY,Armagh,UNITED KINGDOM" in out


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
