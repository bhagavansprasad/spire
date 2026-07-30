"""
Refusal messages — UX-01.

A refusal is an ANSWER, not a failure, and it is rendered as three
labelled lines::

    Reason:   I can look up receipts, but not by customer account number.
    Solution: Scope them by customer or site instead — those I can do.
    Example:  receipts for ABC Application Software

WHAT CHANGED IN PHASE 2, AND WHY THESE TESTS LOOK DIFFERENT

The previous version of this file asserted that the message LED with the
KG capability list — "Spire can look up Address, CreditMemo, ... filter
them (business_relationship, by_customer_name, ...)". That ~90-word
preamble was the defect: readers hit the wall and stopped before reaching
the one sentence that said what was actually wrong.

It also had a test named ``test_aggregation_wins_over_stray_capitalized_token``,
which is a fossil worth remembering. It existed because someone already
knew ``derive_flavor``'s prose scan misread capitalized words — and the
fix at the time was to make aggregation win the tie, rather than to stop
scanning prose. The scan went on to return UNKNOWN_ENTITY for four of
four measured refusals, matching "To", "ID", "Filtering" and "Receipt".
The scan is now gone, and so is that test.

THE THREE TRIPWIRES AT THE BOTTOM OF THIS FILE

Each guards a mistake actually made on 2026-07-30, not a hypothetical:

1. ``_ENTITY_LABELS`` covers every KG entity. The table was first filled
   from the 8 TARGET entities, but a refusal can name any of the 22 — so
   "tax lines for that invoice line" printed the class name
   ``ReceivablesTaxLine`` at a user.

2. Every example the messages promise appears in
   ``scripts/prompts/10_refusal_examples.txt``, which is a runnable set.
   The examples were written from what looked plausible and never run;
   "open purchase orders for supplier EIP Inc" turned out to REFUSE, and
   it was offered as the fix for that very refusal, in three tables.

3. No message leaks an internal name — not a class name, not a filter
   key. Both leaked at different points during the rewrite.

Pure unit tests over a menu fixture: no LLM, no pod, no DB.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from spire.nl_parser.capability import (
    _ENTITY_LABELS,
    _FALLBACK,
    _FILTER_GUIDANCE,
    _IDENTIFIER_GUIDANCE,
    _NOT_A_ROOT_GUIDANCE,
    _OPERATION_EXAMPLES,
    capabilities_sentence,
    capability_message,
    derive_flavor,
)
from spire.nl_parser.result import Refusal, RefusalFlavor
from spire.nl_parser.vocabulary import KGMenu


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_FILE = REPO_ROOT / "scripts" / "prompts" / "10_refusal_examples.txt"


# Every entity the KG declares, as of 2026-07-30. Static on purpose: this
# file must run in the default (non-integration) suite, with no database.
# `test_labels_match_the_live_kg` checks the same thing against the real
# KG and is marked integration.
#
# ADDING A KG ENTITY? Add it here AND to _ENTITY_LABELS in capability.py.
# Same discipline as the expected-count values in test_kg_metadata.py.
KNOWN_KG_ENTITIES = frozenset({
    "AccountCreditMemo",
    "AccountReceipt",
    "AccountReceiptApplication",
    "Address",
    "Buyer",
    "Classification",
    "Contact",
    "CreditMemo",
    "CustomerAccount",
    "CustomerTransaction",
    "Invoice",
    "PODistribution",
    "POSchedule",
    "PurchaseOrder",
    "PurchaseOrderLine",
    "ReceivablesInvoice",
    "ReceivablesInvoiceLine",
    "ReceivablesInvoiceTransactionDFF",
    "ReceivablesTaxLine",
    "Site",
    "StandardReceipt",
    "Supplier",
})


@pytest.fixture
def menu() -> KGMenu:
    """A menu shaped like the live KG: some entities are query ROOTS,
    others exist only as related records.

    That distinction is load-bearing here. ``PurchaseOrderLine`` is a real
    entity that cannot be a root, and conflating "we don't have it" with
    "you can't start there" is the bug this rewrite removes.
    """
    return KGMenu(
        target_entities={"Supplier", "PurchaseOrder", "ReceivablesInvoice",
                         "StandardReceipt", "Invoice"},
        filter_types={"country", "has_open_PO", "customer_account_number"},
        entity_descriptions={
            "Supplier": "A vendor or service provider.",
            "Invoice": "An accounts-payable invoice.",
            "PurchaseOrder": "A purchase order issued to a supplier.",
            "PurchaseOrderLine": "A line on a purchase order.",
            "ReceivablesInvoice": "An AR invoice.",
            "ReceivablesTaxLine": "A tax line on an AR invoice.",
            "StandardReceipt": "A customer receipt.",
            "Buyer": "The purchasing agent assigned to a PO.",
            "Address": "A supplier's address.",
        },
        country_terms={"US": "US", "United Kingdom": "GB", "India": "IN"},
    )


def _lines(msg: str) -> dict[str, str]:
    """Split a rendered message into {'Reason': ..., 'Solution': ...}."""
    out: dict[str, str] = {}
    for line in msg.splitlines():
        m = re.match(r"^(Reason|Solution|Example):\s+(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


# ─────────────────────────────────────────────────────────────────────
# derive_flavor — the model decides, we sanity-check
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("missing_identifier", RefusalFlavor.MISSING_IDENTIFIER),
        ("unsupported_filter", RefusalFlavor.UNSUPPORTED_FILTER),
        ("unsupported_operation", RefusalFlavor.UNSUPPORTED_OPERATION),
        ("unknown_entity", RefusalFlavor.UNKNOWN_ENTITY),
        ("unparseable", RefusalFlavor.UNPARSEABLE),
    ],
)
def test_model_supplied_kind_is_trusted(menu, kind, expected):
    assert derive_flavor("some reason", "", menu, draft_kind=kind) == expected


def test_kind_is_case_and_space_insensitive(menu):
    assert (
        derive_flavor("x", "", menu, draft_kind="  Missing_Identifier ")
        == RefusalFlavor.MISSING_IDENTIFIER
    )


def test_unrecognised_kind_degrades_rather_than_crashing(menu):
    """The model is asked for one of five strings. A sixth must not raise."""
    assert (
        derive_flavor("x", "", menu, draft_kind="banana")
        == RefusalFlavor.UNPARSEABLE
    )


def test_unknown_entity_about_a_valid_root_is_downgraded(menu):
    """The self-contradiction guard.

    If the model claims 'unknown_entity' about a type that IS a query
    root, the message would list it as supported and then deny it. That
    exact contradiction is what made refusals read as breakage.
    """
    assert (
        derive_flavor("x", "", menu, draft_kind="unknown_entity",
                      draft_entity="Supplier")
        == RefusalFlavor.UNPARSEABLE
    )


def test_unknown_entity_about_a_non_root_is_kept(menu):
    """But a known entity that cannot be a ROOT is a legitimate
    UNKNOWN_ENTITY refusal — it has its own branch in the renderer.

    An earlier guard tested is_known_entity here instead of
    target_entities, which downgraded these to UNPARSEABLE and skipped
    that branch, leaking the raw class name from the model's prose.
    """
    assert (
        derive_flavor("x", "", menu, draft_kind="unknown_entity",
                      draft_entity="PurchaseOrderLine")
        == RefusalFlavor.UNKNOWN_ENTITY
    )


def test_explicit_target_entity_unknown_to_kg(menu):
    """With no kind supplied, an entity the KG does not know is still
    UNKNOWN_ENTITY."""
    assert (
        derive_flavor("needs a Contract entity", "Contract", menu)
        == RefusalFlavor.UNKNOWN_ENTITY
    )


def test_vague_reason_falls_back_to_unparseable(menu):
    assert (
        derive_flavor("too vague to pin to a specific entity", "", menu)
        == RefusalFlavor.UNPARSEABLE
    )


def test_prose_is_never_scanned_for_entity_names(menu):
    """The regression this whole rewrite exists to prevent.

    Every string below is a real ``unanswerable_reason`` measured from
    the pod on 2026-07-30. The old scan matched "The"/"ID", "To",
    "Filtering" and "Receipt" in them and returned UNKNOWN_ENTITY for
    all four. With no kind supplied and no target_entity, the only
    honest answer is UNPARSEABLE.
    """
    measured = [
        "The question refers to 'that invoice line' but does not provide a "
        "specific invoice ID or line ID to retrieve tax lines for.",
        "To verify a specific AR invoice, I need an identifier such as the "
        "CustomerTransactionId or TransactionNumber.",
        "There is no filter to retrieve receipt applications by account "
        "number. Receipt applications can only be retrieved by customer name.",
        "Filtering StandardReceipt by account number is not a supported "
        "filter type.",
    ]
    for reason in measured:
        assert derive_flavor(reason, "", menu) == RefusalFlavor.UNPARSEABLE, reason


# ─────────────────────────────────────────────────────────────────────
# Message shape
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("flavor", list(RefusalFlavor))
def test_every_flavor_renders_all_three_lines(menu, flavor):
    msg = capability_message(Refusal(flavor=flavor, detail="something"), menu)
    parts = _lines(msg)
    assert set(parts) == {"Reason", "Solution", "Example"}, msg
    assert all(v.strip() for v in parts.values()), msg


def test_the_capability_dump_no_longer_leads(menu):
    """The whole point of UX-01.

    The message used to open with eight entity names and twenty-one
    filter names before saying anything specific. Now the first line is
    the specific one.
    """
    r = Refusal(flavor=RefusalFlavor.UNSUPPORTED_FILTER, detail="x",
                offending_entity="StandardReceipt",
                offending_filters=["customer_account_number"])
    first = capability_message(r, menu).splitlines()[0]
    assert first.startswith("Reason:")
    assert "has_open_PO" not in first
    assert "ReceivablesInvoice" not in first


def test_capabilities_sentence_still_available(menu):
    """It is no longer in the refusal, but "what can you do?" is a fair
    question and something must answer it."""
    sentence = capabilities_sentence(menu)
    assert "suppliers" in sentence
    assert "country" in sentence


# ─────────────────────────────────────────────────────────────────────
# Per-flavor wording
# ─────────────────────────────────────────────────────────────────────


def test_unsupported_filter_names_the_filter_in_plain_words(menu):
    r = Refusal(flavor=RefusalFlavor.UNSUPPORTED_FILTER, detail="x",
                offending_entity="StandardReceipt",
                offending_filters=["customer_account_number"])
    reason = _lines(capability_message(r, menu))["Reason"]

    assert "receipts" in reason
    assert "customer account number" in reason      # humanized
    assert "customer_account_number" not in reason  # not the raw key


def test_unsupported_filter_without_named_filters_still_reads(menu):
    """The KG path names the offending filters; the self-declared path
    does not. Without a second branch the latter fell through to raw
    model prose, which leaked "the 'by_customer_name' filter"."""
    r = Refusal(flavor=RefusalFlavor.UNSUPPORTED_FILTER,
                detail="requires the 'by_customer_name' filter",
                offending_entity="PurchaseOrder")
    reason = _lines(capability_message(r, menu))["Reason"]
    assert "by_customer_name" not in reason


def test_missing_identifier_names_the_record_type(menu):
    r = Refusal(flavor=RefusalFlavor.MISSING_IDENTIFIER, detail="x",
                offending_entity="ReceivablesInvoice")
    parts = _lines(capability_message(r, menu))
    assert "AR invoices" in parts["Reason"]
    assert "ReceivablesInvoice" not in parts["Reason"]


def test_known_entity_that_is_not_a_root_is_not_denied(menu):
    """"show me purchase order line items" once answered "PurchaseOrderLine
    isn't something I know about" — which is false. Spire has them; they
    are simply not a starting point."""
    r = Refusal(flavor=RefusalFlavor.UNKNOWN_ENTITY, detail="x",
                offending_entity="PurchaseOrderLine")
    parts = _lines(capability_message(r, menu))

    assert "purchase order lines" in parts["Reason"]
    assert "isn't something I know about" not in parts["Reason"]
    assert "PO" in parts["Solution"]


def test_genuinely_absent_entity_still_lists_what_exists(menu):
    """The ONE flavor where the capability list is the actual answer."""
    r = Refusal(flavor=RefusalFlavor.UNKNOWN_ENTITY, detail="x",
                offending_entity="Contract")
    parts = _lines(capability_message(r, menu))

    assert "Contract" in parts["Reason"]
    assert "suppliers" in parts["Solution"]


def test_unsupported_operation_covers_more_than_arithmetic(menu):
    """"compare the lifecycle of PO 701337 and PO 162034" is neither a
    total nor a trend, and was told it needed one."""
    r = Refusal(flavor=RefusalFlavor.UNSUPPORTED_OPERATION, detail="x")
    reason = _lines(capability_message(r, menu))["Reason"]
    assert "side by side" in reason or "comparison" in reason.lower()


def test_operation_example_matches_the_entity(menu):
    """The advice is "ask for the records and do the rest your side", so
    the example must show THOSE records. An entity-blind fallback
    answered a supplier question with a receipts example."""
    r = Refusal(flavor=RefusalFlavor.UNSUPPORTED_OPERATION, detail="x",
                offending_entity="Supplier")
    assert "supplier" in _lines(capability_message(r, menu))["Example"].lower()


# ─────────────────────────────────────────────────────────────────────
# TRIPWIRE 1 — every KG entity has a human label
# ─────────────────────────────────────────────────────────────────────


def test_every_kg_entity_has_a_label():
    """A refusal can name ANY entity, not just the eight query roots.

    The table was first filled from ``target_entities`` alone, so "tax
    lines for that invoice line" printed ``ReceivablesTaxLine`` — a class
    name — at a user. Fourteen entities were missing.

    Add a KG entity and this fails until a label lands in
    ``_ENTITY_LABELS``.
    """
    missing = sorted(KNOWN_KG_ENTITIES - set(_ENTITY_LABELS))
    assert not missing, f"no label for: {missing}"


def test_no_label_for_an_entity_the_kg_does_not_have():
    """The reverse: a label for something the KG dropped is dead weight
    and a sign the two have drifted."""
    extra = sorted(set(_ENTITY_LABELS) - KNOWN_KG_ENTITIES)
    assert not extra, f"label for unknown entity: {extra}"


def test_labels_are_not_class_names():
    """Class names are ours; a label is the reader's.

    Tests for a CamelCase RUN — a lowercase letter immediately followed
    by an uppercase one, as in "ReceivablesTaxLine". An all-lowercase
    rule would be wrong: "PO distributions" and "AR invoices" are the
    abbreviations people actually use, and spelling them out would be a
    worse message, not a better one.
    """
    camel = [v for v in _ENTITY_LABELS.values() if re.search(r"[a-z][A-Z]", v)]
    assert not camel, f"still class-shaped: {camel}"

    same = [k for k, v in _ENTITY_LABELS.items() if k == v]
    assert not same, f"label identical to the class name: {same}"


@pytest.mark.integration
def test_labels_match_the_live_kg():
    """The same check against the real KG. Marked integration because it
    needs the database; ``KNOWN_KG_ENTITIES`` above is the copy that runs
    in the default suite. If these two disagree, the static list is
    stale."""
    from spire.nl_parser.vocabulary import load_kg_menu

    live = set(load_kg_menu().entity_descriptions)
    assert live == KNOWN_KG_ENTITIES, (
        "KNOWN_KG_ENTITIES is out of date; "
        f"live-only={sorted(live - KNOWN_KG_ENTITIES)}, "
        f"stale={sorted(KNOWN_KG_ENTITIES - live)}"
    )


# ─────────────────────────────────────────────────────────────────────
# TRIPWIRE 2 — every promised example is in the runnable set
# ─────────────────────────────────────────────────────────────────────


def _promised_examples() -> set[str]:
    """Every example string the guidance tables can put in front of a user."""
    out: set[str] = set()
    for table in (_FILTER_GUIDANCE, _IDENTIFIER_GUIDANCE, _NOT_A_ROOT_GUIDANCE):
        out.update(example for _, example in table.values())
    out.update(_OPERATION_EXAMPLES.values())
    out.update(example for _, example in _FALLBACK.values())
    return {e for e in out if e}


def _examples_file_prompts() -> set[str]:
    lines = EXAMPLES_FILE.read_text(encoding="utf-8").splitlines()
    return {
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    }


def test_examples_file_exists():
    assert EXAMPLES_FILE.is_file(), f"missing: {EXAMPLES_FILE}"


def test_every_promised_example_is_verifiable():
    """An Example is a PROMISE, made to someone who has just been told no.

    On 2026-07-30 the examples were written from what looked plausible
    and never run. "open purchase orders for supplier EIP Inc" REFUSES —
    filtering POs by supplier name is unsupported, which is the very
    refusal that example was offered to resolve. It sat in three tables.

    Every example must appear in the runnable set, so it cannot ship
    without someone having typed it.
    """
    missing = sorted(_promised_examples() - _examples_file_prompts())
    assert not missing, (
        "example(s) not in 10_refusal_examples.txt — add them and RUN the "
        f"set before committing: {missing}"
    )


def test_examples_file_has_no_orphans():
    """The reverse: a prompt in the file that no table offers is being
    verified for nothing, and probably marks a deleted example."""
    orphans = sorted(_examples_file_prompts() - _promised_examples())
    assert not orphans, f"in the file but promised by nothing: {orphans}"


# ─────────────────────────────────────────────────────────────────────
# TRIPWIRE 3 — no internal names reach a user
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("entity", sorted(KNOWN_KG_ENTITIES))
@pytest.mark.parametrize(
    "flavor",
    [
        RefusalFlavor.MISSING_IDENTIFIER,
        RefusalFlavor.UNSUPPORTED_FILTER,
        RefusalFlavor.UNSUPPORTED_OPERATION,
    ],
)
def test_reason_line_never_prints_a_class_name(menu, flavor, entity):
    """Two separate leaks happened during the rewrite: ``_label`` falling
    back to the class name, and a flavor downgrade routing past the
    branch that would have translated it.

    UNKNOWN_ENTITY is excluded: naming a type the KG genuinely lacks is
    the correct behaviour there, and the model's own word for it is the
    most useful thing available.
    """
    menu.entity_descriptions.setdefault(entity, "x")
    r = Refusal(flavor=flavor, detail="x", offending_entity=entity)
    reason = _lines(capability_message(r, menu))["Reason"]
    assert entity not in reason, reason


def test_reason_line_never_prints_a_filter_key(menu):
    """Filter keys are snake_case identifiers from the KG. Users have
    never seen them and should not start now.

    Only multi-word keys can be checked this way. A single-word key like
    ``country`` humanizes to itself, so "the key must not appear" can
    never hold — and should not: "not by country" is exactly right.
    """
    multiword = [k for k in menu.filter_types if "_" in k]
    assert multiword, "fixture needs at least one snake_case filter key"

    for key in multiword:
        r = Refusal(flavor=RefusalFlavor.UNSUPPORTED_FILTER, detail="x",
                    offending_entity="Supplier", offending_filters=[key])
        reason = _lines(capability_message(r, menu))["Reason"]
        assert key not in reason, reason
        assert key.replace("_", " ") in reason, reason

    # Single-word keys still appear, humanized to themselves. Assert the
    # message reads properly rather than that the word is absent.
    for key in menu.filter_types:
        if "_" in key:
            continue
        r = Refusal(flavor=RefusalFlavor.UNSUPPORTED_FILTER, detail="x",
                    offending_entity="Supplier", offending_filters=[key])
        reason = _lines(capability_message(r, menu))["Reason"]
        assert f"not by {key}" in reason, reason
