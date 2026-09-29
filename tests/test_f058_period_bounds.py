"""F-058 - period-anchored phrases on the aggregate path.

Reproducer:
    Top 5 suppliers by spend this year

Pre-fix, the parse emitted one of two wrong shapes (see finding R):
    r1-r3: date_from=None, date_to=None  (all time)
    r4:    date_from='2025-01-01', date_to=None  (wrong year)

The fix is a deterministic post-parse correction in parser.py that
detects the four period-anchored phrases (`this year`, `this quarter`,
`this month`, `last year`) and overrides the aggregate block's date
window with calendar bounds computed from date.today().

Scope: only the `by_supplier` aggregate op accepts a date range per
_AGGREGATION_PARAMS; the call site guards on op.

The tests build a minimal KGMenu by hand - same convention as
test_f027_country_column.py. The aggregate path skips validate_intent,
so no filter or column catalogues are needed. The mock LLM returns a
DraftIntent whose aggregate carries no dates; the correction fills them.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from spire.nl_parser.draft import DraftAggregate, DraftIntent
from spire.nl_parser.parser import _extract_period_bounds, parse
from spire.nl_parser.vocabulary import KGMenu
from spire.planner.planner import Intent


def _menu() -> KGMenu:
    """Minimal menu: Supplier as the only target entity."""
    return KGMenu(
        target_entities={"Supplier"},
        entity_descriptions={"Supplier": "a supplier"},
    )


def _mock_llm_returning(draft: DraftIntent) -> MagicMock:
    """Mock whose structured-output call returns the given DraftIntent."""
    llm = MagicMock()
    structured = MagicMock()
    structured.invoke.return_value = {"parsed": draft, "raw": None}
    llm.with_structured_output.return_value = structured
    return llm


# ---------------------------------------------------------------------
# Calendar bounds - computed in the test, not hard-coded, so the tests
# do not break on 1 January.
# ---------------------------------------------------------------------


def _expected_year_bounds(offset: int = 0) -> tuple[str, str]:
    year = date.today().year + offset
    return f"{year}-01-01", f"{year + 1}-01-01"


def _expected_month_bounds() -> tuple[str, str]:
    today = date.today()
    start = f"{today.year}-{today.month:02d}-01"
    if today.month == 12:
        end = f"{today.year + 1}-01-01"
    else:
        end = f"{today.year}-{today.month + 1:02d}-01"
    return start, end


def _expected_quarter_bounds() -> tuple[str, str]:
    today = date.today()
    q = (today.month - 1) // 3
    start_month = q * 3 + 1
    start = f"{today.year}-{start_month:02d}-01"
    if start_month == 10:
        end = f"{today.year + 1}-01-01"
    else:
        end = f"{today.year}-{start_month + 3:02d}-01"
    return start, end


# ---------------------------------------------------------------------
# _extract_period_bounds - pure function
# ---------------------------------------------------------------------


def test_this_year_returns_calendar_bounds():
    assert _extract_period_bounds(
        "Top 5 suppliers by spend this year"
    ) == _expected_year_bounds()


def test_last_year_returns_previous_year_bounds():
    assert _extract_period_bounds(
        "Top 5 suppliers by spend last year"
    ) == _expected_year_bounds(offset=-1)


def test_this_quarter_returns_quarter_bounds():
    assert _extract_period_bounds(
        "Top 5 suppliers by spend this quarter"
    ) == _expected_quarter_bounds()


def test_this_month_returns_month_bounds():
    assert _extract_period_bounds(
        "Top 5 suppliers by spend this month"
    ) == _expected_month_bounds()


def test_case_insensitive():
    assert _extract_period_bounds(
        "Top 5 suppliers by spend This Year"
    ) == _expected_year_bounds()


def test_no_period_phrase_returns_none():
    assert _extract_period_bounds(
        "Top 5 suppliers by spend in 2022"
    ) is None


def test_relative_months_not_a_period():
    """`in the last 6 months` is a rolling window, not a calendar period.
    That shape is F-046/F-055's territory; the helper must not fire."""
    assert _extract_period_bounds(
        "Top 5 suppliers by spend in the last 6 months"
    ) is None


def test_bare_noun_returns_none():
    assert _extract_period_bounds("Count of suppliers") is None


# ---------------------------------------------------------------------
# End-to-end via parse() - mock LLM returns an empty-dates draft
# ---------------------------------------------------------------------


def _aggregate_draft(
    date_from: str = "", date_to: str = "", top_n: int = 5, op: str = "by_supplier"
) -> DraftIntent:
    return DraftIntent(
        target_entity="Supplier",
        aggregate=DraftAggregate(
            op=op, date_from=date_from, date_to=date_to, top_n=top_n
        ),
    )


def test_parse_reproducer_fills_empty_dates():
    """The r1-r3 shape: model emitted no dates. The correction fills them."""
    result = parse(
        "Top 5 suppliers by spend this year",
        llm=_mock_llm_returning(_aggregate_draft()),
        menu=_menu(),
    )
    assert not result.is_refusal
    expected = _expected_year_bounds()
    assert result.intent.aggregate["date_from"] == expected[0]
    assert result.intent.aggregate["date_to"] == expected[1]


def test_parse_reproducer_overrides_wrong_dates():
    """The r4 shape: model emitted date_from='2025-01-01'. Override it."""
    result = parse(
        "Top 5 suppliers by spend this year",
        llm=_mock_llm_returning(_aggregate_draft(date_from="2025-01-01")),
        menu=_menu(),
    )
    assert not result.is_refusal
    expected = _expected_year_bounds()
    assert result.intent.aggregate["date_from"] == expected[0]
    assert result.intent.aggregate["date_to"] == expected[1]


def test_parse_leaves_non_period_prompt_alone():
    """A model-emitted 2022 window on a `in 2022` prompt: untouched."""
    result = parse(
        "Top 5 suppliers by spend in 2022",
        llm=_mock_llm_returning(
            _aggregate_draft(date_from="2022-01-01", date_to="2023-01-01")
        ),
        menu=_menu(),
    )
    assert not result.is_refusal
    assert result.intent.aggregate["date_from"] == "2022-01-01"
    assert result.intent.aggregate["date_to"] == "2023-01-01"


def test_parse_leaves_non_by_supplier_op_alone():
    """`top_invoices_by_amount` takes no date range. The period phrase
    must not inject one."""
    result = parse(
        "Top 5 invoices this year",
        llm=_mock_llm_returning(_aggregate_draft(op="top_invoices_by_amount")),
        menu=_menu(),
    )
    assert not result.is_refusal
    assert result.intent.aggregate["date_from"] is None
    assert result.intent.aggregate["date_to"] is None


def test_parse_leaves_no_aggregate_alone():
    """A plain list prompt with a period phrase. No aggregate block to
    correct; the intent is whatever the model emitted."""
    draft = DraftIntent(
        target_entity="Supplier",
        filters=[],
        include=[],
    )
    result = parse(
        "Show me suppliers from this year",
        llm=_mock_llm_returning(draft),
        menu=_menu(),
    )
    assert not result.is_refusal
    assert result.intent.aggregate is None
