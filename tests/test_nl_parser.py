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



# ─────────────────────────────────────────────────────────────────────
# AR shapes: draft -> Intent conversion for the account-rooted prompts
#
# These stay in this file's stated scope — draft -> Intent conversion,
# LLM held constant. They do NOT assert that Gemini follows the parser
# rules for these prompts; that is only knowable from a live call and
# lives in the prompt set / E2E instead.
#
# What IS worth pinning here: the flags and shapes added by AR-P5 travel
# through to_intent() intact. balance_only in particular is a new
# DraftIntent field whose passthrough had no coverage — a dropped line in
# to_intent() would silently disable prompt 6 and no unit test would fail.
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def ar_menu() -> KGMenu:
    """A menu covering the AR account shapes.

    The default `menu` fixture only knows Supplier, so an AR draft would
    be refused at the entity gate before conversion is ever exercised.
    """
    return KGMenu(
        target_entities={"Supplier", "CustomerAccount"},
        filter_types={"country", "by_customer_name"},
        entity_descriptions={
            "Supplier": "A vendor or service provider.",
            "CustomerAccount": "A customer's accounts-receivable account.",
            "CustomerTransaction": "A transaction on a customer account.",
            "AccountCreditMemo": "A credit memo on a customer account.",
            "AccountReceipt": "Cash received from a customer.",
        },
        country_terms={"US": "US"},
    )


def test_balance_only_survives_conversion(ar_menu):
    """AR-P5 prompt 6: the balance_only flag reaches the Intent.

    The planner reads this flag to skip Block 3 entirely, so losing it in
    conversion would turn a balance question into a full transaction
    traversal — a wrong answer, not an error.
    """
    draft = DraftIntent(
        target_entity="CustomerAccount",
        filters=[
            DraftFilter(
                type="by_customer_name",
                value_json='"ABC Application Software"',
            )
        ],
        include=[],
        balance_only=True,
    )
    result = parse(
        "Show me the account balance for customer ABC Application Software",
        llm=MockLLM(draft),
        menu=ar_menu,
    )

    assert not result.is_refusal
    assert result.intent.balance_only is True
    assert result.intent.include == []
    assert result.intent.filters == [
        {"type": "by_customer_name", "value": "ABC Application Software"}
    ]


def test_balance_only_defaults_false(ar_menu):
    """A draft that never mentions balance_only converts with it false.

    Guards the default: if it ever flipped, every customer-invoices query
    would silently lose its transaction traversal.
    """
    draft = DraftIntent(
        target_entity="CustomerAccount",
        filters=[
            DraftFilter(
                type="by_customer_name",
                value_json='"ABC Corporation Americas"',
            )
        ],
        include=["CustomerTransaction"],
    )
    result = parse(
        "Show me AR invoices for customer ABC Corporation Americas",
        llm=MockLLM(draft),
        menu=ar_menu,
    )

    assert not result.is_refusal
    assert result.intent.balance_only is False
    assert result.intent.include == ["CustomerTransaction"]


def test_account_credit_memo_include_converts(ar_menu):
    """AR-P5 prompt 7: the memo child rides through as an include."""
    draft = DraftIntent(
        target_entity="CustomerAccount",
        filters=[
            DraftFilter(
                type="by_customer_name",
                value_json='"ABC Application Software"',
            )
        ],
        include=["AccountCreditMemo"],
    )
    result = parse(
        "Show credit memos for ABC Application Software",
        llm=MockLLM(draft),
        menu=ar_menu,
    )

    assert not result.is_refusal
    assert result.intent == Intent(
        target_entity="CustomerAccount",
        filters=[
            {"type": "by_customer_name", "value": "ABC Application Software"}
        ],
        include=["AccountCreditMemo"],
    )


def test_account_receipt_include_converts(ar_menu):
    """AR-P5 prompt 8: the receipts child rides through as an include."""
    draft = DraftIntent(
        target_entity="CustomerAccount",
        filters=[
            DraftFilter(
                type="by_customer_name",
                value_json='"ABC Application Software"',
            )
        ],
        include=["AccountReceipt"],
    )
    result = parse(
        "Show receipts for ABC Application Software",
        llm=MockLLM(draft),
        menu=ar_menu,
    )

    assert not result.is_refusal
    assert result.intent == Intent(
        target_entity="CustomerAccount",
        filters=[
            {"type": "by_customer_name", "value": "ABC Application Software"}
        ],
        include=["AccountReceipt"],
    )


def test_open_only_and_invoice_limit_survive_conversion(ar_menu):
    """AR-P2c and the top-N limit: both parsed args reach the Intent.

    Neither had coverage in this file. The planner injects them onto the
    CustomerTransaction step, so a dropped passthrough would silently
    return ALL invoices instead of the top 5 open ones.
    """
    draft = DraftIntent(
        target_entity="CustomerAccount",
        filters=[
            DraftFilter(
                type="by_customer_name",
                value_json='"ABC Corporation Americas"',
            )
        ],
        include=["CustomerTransaction"],
        open_only=True,
        invoice_limit=5,
    )
    result = parse(
        "Show me the top 5 open invoices for customer ABC Corporation Americas",
        llm=MockLLM(draft),
        menu=ar_menu,
    )

    assert not result.is_refusal
    assert result.intent.open_only is True
    assert result.intent.invoice_limit == 5
    assert result.intent.balance_only is False
