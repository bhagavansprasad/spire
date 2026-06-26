"""
Unit tests for the NL parser (checkpoint 2).

These are the MOCK-LLM tests (Q4): the LLM is held constant by injecting a
mock, so a failure here means OUR code is wrong, not the model. They assert
EXACT Intent output. Live tests (real Gemini, property assertions) are
separate and marked @pytest.mark.integration.

Scope: checkpoint 2 — prompt-building, the LLM call wiring, and draft ->
Intent conversion. KG validation of the draft (checkpoint 3) is not tested
here yet; these tests pass a shape-valid draft straight through.
"""

from __future__ import annotations

import pytest

from spire.nl_parser.draft import DraftFilter, DraftIntent
from spire.nl_parser.parser import parse
from spire.nl_parser.result import RefusalFlavor
from spire.nl_parser.vocabulary import KGMenu
from spire.planner.planner import Intent


# ─────────────────────────────────────────────────────────────────────
# Test doubles
# ─────────────────────────────────────────────────────────────────────


class _StructuredStub:
    """Stands in for llm.with_structured_output(DraftIntent). Its .invoke
    returns whatever canned value it was constructed with."""

    def __init__(self, canned):
        self._canned = canned
        self.invoked_with = None

    def invoke(self, messages):
        self.invoked_with = messages
        return self._canned


class MockLLM:
    """Minimal mock matching the surface parse() uses: with_structured_output
    then invoke. Returns a fixed DraftIntent (or dict, or None) to drive each
    test case."""

    def __init__(self, canned):
        self._canned = canned
        self.structured_for = None

    def with_structured_output(self, schema, **kwargs):
        self.structured_for = schema
        return _StructuredStub(self._canned)


@pytest.fixture
def menu() -> KGMenu:
    """A fixed menu mirroring the live KG (confirmed values), so tests never
    hit the database."""
    return KGMenu(
        target_entities={"Supplier"},
        filter_types={"country", "has_open_PO", "has_no_recent_invoices"},
        entity_descriptions={
            "Supplier": "A vendor or service provider.",
            "Invoice": "An accounts-payable invoice.",
            "PurchaseOrder": "A purchase order issued to a supplier.",
            "Buyer": "The purchasing agent assigned to a PO.",
            "Address": "A supplier's address.",
        },
        country_terms={"US": "US", "USA": "US", "United States": "US",
                       "United Kingdom": "GB", "UK": "GB", "India": "IN"},
    )


# ─────────────────────────────────────────────────────────────────────
# Successful parses (exact-match)
# ─────────────────────────────────────────────────────────────────────


def test_simple_country_intent(menu):
    """A draft with one string-valued filter converts to the exact Intent."""
    draft = DraftIntent(
        target_entity="Supplier",
        filters=[DraftFilter(type="country", value_json='"US"')],
        include=[],
    )
    result = parse("List all US suppliers", llm=MockLLM(draft), menu=menu)

    assert not result.is_refusal
    assert result.intent == Intent(
        target_entity="Supplier",
        filters=[{"type": "country", "value": "US"}],
        include=[],
    )


def test_bool_and_object_values_decode(menu):
    """value_json decodes bool and object values to native Python types."""
    draft = DraftIntent(
        target_entity="Supplier",
        filters=[
            DraftFilter(type="country", value_json='"US"'),
            DraftFilter(type="has_no_recent_invoices", value_json='{"months": 6}'),
            DraftFilter(type="has_open_PO", value_json="true"),
        ],
        include=["Buyer"],
    )
    result = parse("US suppliers, no invoices in 6 months, with open POs, "
                   "include the buyer", llm=MockLLM(draft), menu=menu)

    assert not result.is_refusal
    assert result.intent == Intent(
        target_entity="Supplier",
        filters=[
            {"type": "country", "value": "US"},
            {"type": "has_no_recent_invoices", "value": {"months": 6}},
            {"type": "has_open_PO", "value": True},
        ],
        include=["Buyer"],
    )


def test_empty_filters_and_include(menu):
    draft = DraftIntent(target_entity="Supplier", filters=[], include=[])
    result = parse("List all suppliers", llm=MockLLM(draft), menu=menu)

    assert not result.is_refusal
    assert result.intent == Intent(
        target_entity="Supplier", filters=[], include=[]
    )


# ─────────────────────────────────────────────────────────────────────
# Unparseable / malformed output
# ─────────────────────────────────────────────────────────────────────


def test_none_response_is_unparseable_refusal(menu):
    """If the model yields nothing, the parser refuses (not crashes)."""
    result = parse("aoeu qwerty", llm=MockLLM(None), menu=menu)

    assert result.is_refusal
    assert result.refusal.flavor == RefusalFlavor.UNPARSEABLE


def test_non_json_value_falls_back_to_string(menu):
    """A filter value that isn't valid JSON is treated as a plain string
    (lenient decoding), not refused. Models often emit bare 'US' instead of
    '\"US\"'."""
    draft = DraftIntent(
        target_entity="Supplier",
        filters=[DraftFilter(type="country", value_json="US")],  # not JSON
        include=[],
    )
    result = parse("US suppliers", llm=MockLLM(draft), menu=menu)

    assert not result.is_refusal
    assert result.intent == Intent(
        target_entity="Supplier",
        filters=[{"type": "country", "value": "US"}],
        include=[],
    )


# ─────────────────────────────────────────────────────────────────────
# Wiring
# ─────────────────────────────────────────────────────────────────────


def test_dict_response_is_normalized(menu):
    """Some backends return a dict instead of the model; parse() coerces it."""
    draft_dict = {
        "target_entity": "Supplier",
        "filters": [{"type": "country", "value_json": '"IN"'}],
        "include": [],
    }
    result = parse("India suppliers", llm=MockLLM(draft_dict), menu=menu)

    assert not result.is_refusal
    assert result.intent == Intent(
        target_entity="Supplier",
        filters=[{"type": "country", "value": "IN"}],
        include=[],
    )


def test_structured_output_bound_to_draft_intent(menu):
    """parse() binds the DraftIntent schema to the LLM."""
    draft = DraftIntent(target_entity="Supplier", filters=[], include=[])
    mock = MockLLM(draft)
    parse("List all suppliers", llm=mock, menu=menu)

    assert mock.structured_for is DraftIntent


# ─────────────────────────────────────────────────────────────────────
# KG validation refusals (checkpoint 3)
# ─────────────────────────────────────────────────────────────────────


def test_unknown_entity_refused(menu):
    """An entity not in the KG at all -> UNKNOWN_ENTITY."""
    draft = DraftIntent(target_entity="Contract", filters=[], include=[])
    result = parse("Show contract renewals", llm=MockLLM(draft), menu=menu)

    assert result.is_refusal
    assert result.refusal.flavor == RefusalFlavor.UNKNOWN_ENTITY
    assert result.refusal.offending_entity == "Contract"


def test_known_but_invalid_target_refused(menu):
    """A real entity with no fetcher (e.g. Buyer) -> UNSUPPORTED_OPERATION."""
    draft = DraftIntent(target_entity="Buyer", filters=[], include=[])
    result = parse("Top buyers by spend", llm=MockLLM(draft), menu=menu)

    assert result.is_refusal
    assert result.refusal.flavor == RefusalFlavor.UNSUPPORTED_OPERATION
    assert result.refusal.offending_entity == "Buyer"


def test_unsupported_filter_refused(menu):
    """A valid entity with an unknown filter -> UNSUPPORTED_FILTER."""
    draft = DraftIntent(
        target_entity="Supplier",
        filters=[DraftFilter(type="amount_over", value_json="100000")],
        include=[],
    )
    result = parse("Suppliers over $100k", llm=MockLLM(draft), menu=menu)

    assert result.is_refusal
    assert result.refusal.flavor == RefusalFlavor.UNSUPPORTED_FILTER
    assert result.refusal.offending_filters == ["amount_over"]


def test_unsupported_filters_collected_all_at_once(menu):
    """Multiple bad filters are reported together (B1: collect-all on
    filters once the entity is valid)."""
    draft = DraftIntent(
        target_entity="Supplier",
        filters=[
            DraftFilter(type="country", value_json='"US"'),  # ok
            DraftFilter(type="amount_over", value_json="100000"),  # bad
            DraftFilter(type="weight_over", value_json="50"),  # bad
        ],
        include=[],
    )
    result = parse("...", llm=MockLLM(draft), menu=menu)

    assert result.is_refusal
    assert result.refusal.flavor == RefusalFlavor.UNSUPPORTED_FILTER
    assert result.refusal.offending_filters == ["amount_over", "weight_over"]


def test_bad_entity_gates_before_bad_filter(menu):
    """B1: a bad entity refuses on the entity alone, ignoring bad filters."""
    draft = DraftIntent(
        target_entity="Contract",
        filters=[DraftFilter(type="amount_over", value_json="100000")],
        include=[],
    )
    result = parse("...", llm=MockLLM(draft), menu=menu)

    assert result.is_refusal
    assert result.refusal.flavor == RefusalFlavor.UNKNOWN_ENTITY
    # The filter problem is not reported — entity gate fired first.
    assert result.refusal.offending_filters == []


# ─────────────────────────────────────────────────────────────────────
# Explicit unanswerable flag (silent-rewrite fix)
# ─────────────────────────────────────────────────────────────────────


def test_explicit_unanswerable_refused(menu):
    """When the model sets unanswerable=true, the parser refuses with its
    reason and never inspects target_entity/filters."""
    draft = DraftIntent(
        unanswerable=True,
        unanswerable_reason="needs a Contract entity, which is not supported",
        target_entity="",
        filters=[],
        include=[],
    )
    result = parse("Show contract renewals", llm=MockLLM(draft), menu=menu)

    assert result.is_refusal
    # Feature 8: a self-declared refusal naming an entity the KG doesn't
    # know is now UNKNOWN_ENTITY, not the old catch-all UNPARSEABLE.
    assert result.refusal.flavor == RefusalFlavor.UNKNOWN_ENTITY
    assert "Contract" in result.refusal.detail


def test_unanswerable_takes_precedence_over_empty_entity(menu):
    """An unanswerable draft with an empty target_entity refuses cleanly
    rather than failing entity validation on the empty string."""
    draft = DraftIntent(
        unanswerable=True,
        unanswerable_reason="needs spend aggregation",
        target_entity="",
    )
    result = parse("Top suppliers by spend", llm=MockLLM(draft), menu=menu)

    assert result.is_refusal
    assert result.refusal.detail == "needs spend aggregation"

