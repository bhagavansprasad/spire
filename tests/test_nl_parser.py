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

from spire.nl_parser.draft import DraftAggregate, DraftFilter, DraftIntent
from spire.nl_parser.parser import parse
from spire.nl_parser.result import RefusalFlavor
from spire.nl_parser.vocabulary import KGMenu, add_child_include_from_prompt
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
        # COL-03: the Supplier field catalog, so validate_intent's Step 4
        # can tell a real column from an unknown one. These are the four
        # confirmed Supplier fields in the live KG.
        entity_columns={
            "Supplier": ["Supplier", "Status", "SupplierId", "SupplierNumber"],
        },
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
# COL-03: partial column resolution (validate_intent Step 4)
#
# An unknown COLUMN does not refuse the query — the entity and filters are
# valid, so it runs. The requested column list is split against the KG
# field catalog: known names stay in intent.fields, unknown ones move to
# intent.unresolved_fields. Every case below is a SUCCESS (not a refusal),
# which is the whole point — before Step 4, a single unknown column made
# the model declare the query unanswerable, discarding the valid columns.
# ─────────────────────────────────────────────────────────────────────


def test_all_requested_columns_resolve(menu):
    """All columns known -> all stay in fields, nothing unresolved, no
    refusal."""
    draft = DraftIntent(
        target_entity="Supplier",
        filters=[DraftFilter(type="country", value_json='"US"')],
        include=[],
        fields=["Supplier", "SupplierNumber"],
    )
    result = parse("US suppliers with name and number", llm=MockLLM(draft), menu=menu)

    assert not result.is_refusal
    assert result.intent.fields == ["Supplier", "SupplierNumber"]
    assert result.intent.unresolved_fields == []


def test_partial_columns_split_not_refused(menu):
    """The SME case: two valid columns and one unknown. The query is NOT
    refused — valid columns stay, the unknown one is recorded."""
    draft = DraftIntent(
        target_entity="Supplier",
        filters=[DraftFilter(type="country", value_json='"US"')],
        include=[],
        fields=["Supplier", "Status", "created by"],
    )
    result = parse(
        "suppliers with name, status, and created by",
        llm=MockLLM(draft),
        menu=menu,
    )

    # Not a refusal — the defect this fixes was wholesale refusal here.
    assert not result.is_refusal
    assert result.intent.fields == ["Supplier", "Status"]
    assert result.intent.unresolved_fields == ["created by"]


def test_all_columns_unknown_still_not_refused(menu):
    """Every requested column is unknown. Still NOT a refusal: the rows can
    run, and the query becomes rows-with-a-note (COL-03: not an inability
    case). fields empties; all names land in unresolved."""
    draft = DraftIntent(
        target_entity="Supplier",
        filters=[],
        include=[],
        fields=["credit rating", "risk score"],
    )
    result = parse(
        "suppliers with credit rating and risk score",
        llm=MockLLM(draft),
        menu=menu,
    )

    assert not result.is_refusal
    assert result.intent.fields == []
    assert result.intent.unresolved_fields == ["credit rating", "risk score"]


def test_column_split_preserves_requested_order(menu):
    """Known and unknown columns keep their requested order within each
    list — the table prints columns in the order asked, and the note names
    the misses in the order asked."""
    draft = DraftIntent(
        target_entity="Supplier",
        filters=[],
        include=[],
        fields=["created by", "Supplier", "risk score", "Status"],
    )
    result = parse("...", llm=MockLLM(draft), menu=menu)

    assert not result.is_refusal
    assert result.intent.fields == ["Supplier", "Status"]
    assert result.intent.unresolved_fields == ["created by", "risk score"]


def test_no_columns_named_is_a_noop(menu):
    """When no columns are requested, Step 4 does nothing: both lists stay
    empty. This is the common case and must be untouched."""
    draft = DraftIntent(
        target_entity="Supplier",
        filters=[DraftFilter(type="country", value_json='"US"')],
        include=[],
    )
    result = parse("US suppliers", llm=MockLLM(draft), menu=menu)

    assert not result.is_refusal
    assert result.intent.fields == []
    assert result.intent.unresolved_fields == []


# ─────────────────────────────────────────────────────────────────────
# Explicit unanswerable flag (silent-rewrite fix)
# ─────────────────────────────────────────────────────────────────────


def test_explicit_unanswerable_refused(menu):
    """When the model sets unanswerable=true, the parser refuses with its
    reason and never inspects target_entity/filters.

    Phase 2 (UX-01) changed WHO decides the flavor. The model now states
    it in ``unanswerable_kind`` and names the record type in
    ``unanswerable_entity`` — this draft mirrors what a real parse
    produces. ``target_entity`` stays empty, as the silent-rewrite guard
    requires.
    """
    draft = DraftIntent(
        unanswerable=True,
        unanswerable_reason="needs a Contract entity, which is not supported",
        unanswerable_kind="unknown_entity",
        unanswerable_entity="Contract",
        target_entity="",
        filters=[],
        include=[],
    )
    result = parse("Show contract renewals", llm=MockLLM(draft), menu=menu)

    assert result.is_refusal
    assert result.refusal.flavor == RefusalFlavor.UNKNOWN_ENTITY
    assert "Contract" in result.refusal.detail
    # The entity is carried through for wording, from the descriptive
    # field rather than from target_entity.
    assert result.refusal.offending_entity == "Contract"


def test_unanswerable_without_a_kind_falls_back_to_unparseable(menu):
    """A draft that declares itself unanswerable and nothing else.

    Before Phase 2 this returned UNKNOWN_ENTITY, because derive_flavor
    scanned the reason prose for capitalized words and "Contract" matched.
    That scan is gone: it matched "To", "ID", "Filtering" and "Receipt"
    just as readily, and returned UNKNOWN_ENTITY for four of four
    refusals measured against the pod.

    UNPARSEABLE is now the honest answer here — the model said it could
    not answer and gave no classification, so we do not invent one. This
    test exists so that behaviour is deliberate rather than incidental,
    and so reintroducing a prose heuristic breaks something.
    """
    draft = DraftIntent(
        unanswerable=True,
        unanswerable_reason="needs a Contract entity, which is not supported",
        target_entity="",
    )
    result = parse("Show contract renewals", llm=MockLLM(draft), menu=menu)

    assert result.is_refusal
    assert result.refusal.flavor == RefusalFlavor.UNPARSEABLE
    assert "Contract" in result.refusal.detail


def test_unanswerable_kind_survives_an_empty_target_entity(menu):
    """The distinction the second new field exists for.

    ``target_entity`` is REQUIRED to be empty on a self-declared refusal,
    so a message needing the record type had nowhere to get it and fell
    back to "I'm not sure which record you mean" for a record Spire has.
    """
    draft = DraftIntent(
        unanswerable=True,
        unanswerable_reason="no invoice id given",
        unanswerable_kind="missing_identifier",
        unanswerable_entity="Supplier",
        target_entity="",
    )
    result = parse("verify the invoice", llm=MockLLM(draft), menu=menu)

    assert result.refusal.flavor == RefusalFlavor.MISSING_IDENTIFIER
    assert result.refusal.offending_entity == "Supplier"


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



# ─────────────────────────────────────────────────────────────────────
# add_child_include_from_prompt: the receipt/receipt-application
# subsumption guard.
#
# The function reads _CHILD_INCLUDE_WHEN_PRESENT and the raw prompt; it
# does NOT use `menu` (kept in the signature for parity with
# correct_include_from_prompt), so these call it directly with the
# fixture menu and assert the include it produces. The bug: "receipt
# applications" tokenises to {receipt, applications}, so AccountReceipt's
# bare "receipt" trigger fired alongside AccountReceiptApplication's
# "receipt applications" phrase and BOTH children were added — a
# redundant receipt fetch that also reordered the answer. The guard
# suppresses the bare trigger only when every occurrence of the word is
# inside a longer sibling phrase that is itself present.
# ─────────────────────────────────────────────────────────────────────


def test_add_child_include_pure_applications_excludes_receipt(menu):
    """'receipt applications' alone must not also pull AccountReceipt.

    Starting from an empty include (the child-led case the function
    exists for), only the application child is added — not the receipt.
    """
    result = add_child_include_from_prompt(
        "Show receipt applications for customer ABC Application Software",
        "CustomerAccount",
        [],
        menu,
    )
    assert result == ["AccountReceiptApplication"]
    assert "AccountReceipt" not in result


def test_add_child_include_applications_does_not_append_receipt(menu):
    """Even when the include already holds the application, the bare
    'receipt' trigger must not append AccountReceipt on top."""
    result = add_child_include_from_prompt(
        "Show receipt applications for customer ABC Application Software",
        "CustomerAccount",
        ["AccountReceiptApplication"],
        menu,
    )
    assert result == ["AccountReceiptApplication"]


def test_add_child_include_bare_receipts_still_adds_receipt(menu):
    """The guard must not swallow a genuine bare-receipts request."""
    result = add_child_include_from_prompt(
        "Show receipts for ABC Application Software",
        "CustomerAccount",
        [],
        menu,
    )
    assert result == ["AccountReceipt"]


def test_add_child_include_both_named_adds_both(menu):
    """When the prompt names receipts standalone AND receipt applications,
    both children are added — 'receipts' stands alone, so it still fires."""
    result = add_child_include_from_prompt(
        "Show receipts and receipt applications for ABC",
        "CustomerAccount",
        [],
        menu,
    )
    assert set(result) == {"AccountReceipt", "AccountReceiptApplication"}


def test_add_child_include_guard_leaves_other_children_untouched(menu):
    """The guard is specific to the receipt/application overlap: credit
    memos and transactions have no such prefix collision and are added
    exactly as before."""
    memos = add_child_include_from_prompt(
        "Show credit memos for ABC", "CustomerAccount", [], menu
    )
    assert memos == ["AccountCreditMemo"]
    txns = add_child_include_from_prompt(
        "Show transactions for ABC", "CustomerAccount", [], menu
    )
    assert txns == ["CustomerTransaction"]


# ─────────────────────────────────────────────────────────────────────
# The two receivables aggregation ops — exposure_ranking and
# receipt_method_distribution — were fully wired downstream (tool,
# planner registries, synthesizer, display) but the parser refused them
# as unsupported_operation: the router's scoped context drops the mode
# sysprompt, so the only op teaching the scoped LLM sees is the
# DraftAggregate.op FIELD DESCRIPTION, which listed only by_supplier and
# top_invoices_by_amount. These pin that both ops now survive the
# DraftAggregate -> Intent conversion (the schema accepts them; nothing
# downstream of the LLM rejects the op string). Choosing the op from
# natural language is the LLM's job and is verified by the live
# end-to-end run, not here — these mock-LLM tests hold the draft constant
# and check the plumbing, matching the rest of this module.
# ─────────────────────────────────────────────────────────────────────


def test_exposure_ranking_aggregate_converts(menu):
    """A DraftAggregate op='exposure_ranking' reaches the Intent verbatim."""
    draft = DraftIntent(
        target_entity="",
        aggregate=DraftAggregate(op="exposure_ranking", top_n=10),
    )
    result = parse("rank top accounts by exposure", llm=MockLLM(draft), menu=menu)
    assert not result.is_refusal
    assert result.intent.aggregate == {
        "op": "exposure_ranking",
        "date_from": None,
        "date_to": None,
        "top_n": 10,
    }


def test_receipt_method_distribution_aggregate_converts(menu):
    """A DraftAggregate op='receipt_method_distribution' reaches the Intent
    verbatim; the customer scope, when present, rides as a filter (not in
    the aggregate block)."""
    draft = DraftIntent(
        target_entity="CustomerAccount",
        filters=[DraftFilter(type="by_customer_name",
                             value_json='"ABC Application Software"')],
        aggregate=DraftAggregate(op="receipt_method_distribution", top_n=10),
    )
    result = parse(
        "receipt method distribution for ABC Application Software",
        llm=MockLLM(draft), menu=menu,
    )
    assert not result.is_refusal
    assert result.intent.aggregate["op"] == "receipt_method_distribution"
    assert {"type": "by_customer_name",
            "value": "ABC Application Software"} in result.intent.filters


# ─────────────────────────────────────────────────────────────────────
# COL-03 + includes: a field the active include already provides is
# SATISFIED by it, not unresolved. "supplier name, number, and address"
# (or "country") comes back with include=['Address'] and the location
# field in fields; the Address include renders that data as its own
# column, so the field must NOT be reported as an unavailable column —
# previously the display printed "column isn't available" ABOVE the very
# Address column that answered it (the AI-10 address-mapping quirk
# surfacing at the field split). The guard only fires when the covering
# include is active, so a genuine unknown, or the same word without the
# include, still resolves to unresolved_fields.
# ─────────────────────────────────────────────────────────────────────


def test_field_satisfied_by_active_address_include_is_not_unresolved(menu):
    """'address'/'country' requested WITH the Address include: satisfied by
    the include, so neither projected as a base column nor reported
    unavailable."""
    draft = DraftIntent(
        target_entity="Supplier",
        filters=[DraftFilter(type="country", value_json='"US"')],
        include=["Address"],
        fields=["Supplier", "SupplierNumber", "country"],
    )
    result = parse(
        "US suppliers with supplier name, supplier number, and country",
        llm=MockLLM(draft), menu=menu,
    )
    assert not result.is_refusal
    # country is satisfied by the Address include: not in fields, not unresolved.
    assert result.intent.fields == ["Supplier", "SupplierNumber"]
    assert result.intent.unresolved_fields == []


def test_location_field_without_the_include_still_unresolves(menu):
    """The guard is scoped to an ACTIVE covering include. 'country' with NO
    Address include stays unresolved — nothing renders it, so the honest
    'not available' note must still fire."""
    draft = DraftIntent(
        target_entity="Supplier",
        filters=[],
        include=[],
        fields=["Supplier", "country"],
    )
    result = parse(
        "suppliers with name and country", llm=MockLLM(draft), menu=menu,
    )
    assert not result.is_refusal
    assert result.intent.fields == ["Supplier"]
    assert result.intent.unresolved_fields == ["country"]
