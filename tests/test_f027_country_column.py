"""F-027 — "country" as a column on Supplier queries.

The parser emits two different wrong shapes on the same prompt (16/20
blob-rendered, 4/20 false-unresolved, 0/20 correct per the entry's N=20
sweep). The fix is a deterministic post-parse correction in parser.py
plus a display-side extraction in formatters.py. These tests pin the
discriminator, the two behaviours, and the guard against over-reach.

The tests build a minimal KGMenu by hand — same convention as
test_f017_child_field_resolution.py. No pod, no LLM in the display
tests; the parser tests inject a mock LLM returning the wrong shape and
assert the correction fixes it.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from spire.nl_parser.draft import DraftFilter, DraftIntent
from spire.nl_parser.parser import _has_country_column_phrasing, parse
from spire.nl_parser.vocabulary import KGMenu
from spire.planner.planner import Intent
from spire.rendering.formatters import _format_projected_table


def _menu() -> KGMenu:
    """Minimal menu: Supplier with the columns the corrections read,
    Address with the columns the display extraction reads."""
    return KGMenu(
        target_entities={"Supplier"},
        filter_types={"status", "country"},
        entity_descriptions={
            "Supplier": "a supplier",
            "Address": "a supplier address",
        },
        entity_columns={
            "Supplier": ["SupplierId", "SupplierNumber", "Supplier", "Status"],
            "Address": ["CountryCode", "Country"],
        },
    )


def _mock_llm_returning(draft: DraftIntent) -> MagicMock:
    """Mock whose structured-output call returns the given DraftIntent."""
    llm = MagicMock()
    structured = MagicMock()
    structured.invoke.return_value = {"parsed": draft, "raw": None}
    llm.with_structured_output.return_value = structured
    return llm


# ─────────────────────────────────────────────────────────────────────
# The discriminator — column request vs filter value
# ─────────────────────────────────────────────────────────────────────


def test_column_phrasing_detected_on_supplier():
    """'supplier number and country' is a column request — no country
    filter on the intent."""
    intent = Intent(
        target_entity="Supplier",
        filters=[{"type": "status", "value": "active"}],
    )
    assert _has_country_column_phrasing(
        "Supplier number and country for active suppliers", intent
    )


def test_filter_phrasing_not_detected():
    """'active suppliers in US' carries a country FILTER. The correction
    must not fire — the filter path is the correct answer for that prompt."""
    intent = Intent(
        target_entity="Supplier",
        filters=[{"type": "country", "value": "US"}],
    )
    assert not _has_country_column_phrasing("active suppliers in US", intent)


def test_non_supplier_target_not_detected():
    """The correction is scoped to Supplier roots. A PO prompt that
    happens to contain the word 'country' must not be touched."""
    intent = Intent(
        target_entity="PurchaseOrder",
        filters=[{"type": "by_id", "value": "2144"}],
    )
    assert not _has_country_column_phrasing(
        "Show PO 2144 and its country", intent
    )


# ─────────────────────────────────────────────────────────────────────
# The parser correction — needs a wrong-shape draft from the LLM
# ─────────────────────────────────────────────────────────────────────


def test_parser_adds_country_and_address_on_shape_b():
    """Shape B reproducer: the parser returned no include and no country
    field. The correction must add both."""
    draft = DraftIntent(
        target_entity="Supplier",
        filters=[DraftFilter(type="status", value_json='"active"')],
        fields=["SupplierNumber"],
        include=[],
    )
    result = parse(
        "Supplier number and country for active suppliers",
        llm=_mock_llm_returning(draft),
        menu=_menu(),
    )
    assert not result.is_refusal
    assert result.intent.include == ["Address"]
    assert "country" in result.intent.fields


def test_parser_adds_country_when_include_already_present():
    """Shape A reproducer: the parser already added the Address include
    but dropped the country field. The correction adds only the field."""
    draft = DraftIntent(
        target_entity="Supplier",
        filters=[DraftFilter(type="status", value_json='"active"')],
        fields=["SupplierNumber"],
        include=["Address"],
    )
    result = parse(
        "Supplier number and country for active suppliers",
        llm=_mock_llm_returning(draft),
        menu=_menu(),
    )
    assert not result.is_refusal
    assert result.intent.include == ["Address"]
    assert "country" in result.intent.fields


def test_parser_leaves_filter_shape_alone():
    """The country FILTER prompt. The correction must not fire."""
    draft = DraftIntent(
        target_entity="Supplier",
        filters=[
            DraftFilter(type="status", value_json='"active"'),
            DraftFilter(type="country", value_json='"US"'),
        ],
        fields=[],
        include=[],
    )
    result = parse(
        "active suppliers in US",
        llm=_mock_llm_returning(draft),
        menu=_menu(),
    )
    assert not result.is_refusal
    assert result.intent.include == []
    assert "country" not in result.intent.fields


# ─────────────────────────────────────────────────────────────────────
# The display extraction — pure function over synthetic rows
# ─────────────────────────────────────────────────────────────────────


def _columns_line(rendered: str) -> str:
    return next(
        (ln for ln in rendered.split("\n") if "columns:" in ln),
        "",
    )


def test_display_extracts_country_from_nested_address():
    """When 'country' is in fields and rows carry addresses[], the country
    column is populated from the first address, and the Address blob
    column is NOT appended."""
    outputs = {
        "suppliers": [
            {
                "SupplierNumber": "1252",
                "addresses": [
                    {"Country": "United States", "City": "Houston"}
                ],
            },
            {
                "SupplierNumber": "1265",
                "addresses": [
                    {"Country": "Canada", "City": "Calgary"}
                ],
            },
        ]
    }
    rendered = _format_projected_table(
        outputs,
        fields=["SupplierNumber", "country"],
        unresolved_fields=[],
        available_columns=[],
        entity="Supplier",
    )
    cols = _columns_line(rendered)
    assert "country" in cols
    assert "Address" not in cols
    assert "United States" in rendered
    assert "Canada" in rendered


def test_display_extracts_countrycode_with_country_fallback():
    """'CountryCode' falls back to the full Country name when the code is
    absent — the reader asked for a country, not for a code."""
    outputs = {
        "suppliers": [
            {
                "SupplierNumber": "1252",
                "addresses": [
                    {"CountryCode": None, "Country": "United States"}
                ],
            }
        ]
    }
    rendered = _format_projected_table(
        outputs,
        fields=["SupplierNumber", "CountryCode"],
        unresolved_fields=[],
        available_columns=[],
        entity="Supplier",
    )
    cols = _columns_line(rendered)
    # Both assertions are load-bearing. "United States in rendered" alone
    # passes PRE-fix by accident: the auto-appended Address blob contains
    # the same string. "Address not in cols" is the discriminator — pre-fix
    # the blob is appended beside the (empty) CountryCode column; post-fix
    # the extraction populates CountryCode and suppresses the blob.
    assert "CountryCode" in cols
    assert "Address" not in cols
    assert "United States" in rendered


def test_display_appends_address_when_no_component_requested():
    """Over-reach guard: fields name no address component, so the blob
    must still be appended (the pre-F-027 behaviour, unchanged)."""
    outputs = {
        "suppliers": [
            {
                "SupplierNumber": "1252",
                "addresses": [
                    {
                        "FormattedAddress": "6302 England St, HOUSTON, TX",
                        "Country": "United States",
                    }
                ],
            }
        ]
    }
    rendered = _format_projected_table(
        outputs,
        fields=["SupplierNumber"],
        unresolved_fields=[],
        available_columns=[],
        entity="Supplier",
    )
    cols = _columns_line(rendered)
    assert "Address" in cols
    assert "6302 England St" in rendered
