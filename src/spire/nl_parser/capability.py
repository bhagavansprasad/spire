"""
Capability-framed refusal — feature 8, rewritten in Phase 2 (UX-01).

A refusal is an ANSWER, not a failure. It should read like one.

WHAT PHASE 2 CHANGED, AND WHY

Refusals were being reported as breakage — by SMEs, and by the project's
own developer reading a screen of them. Three faults, one root cause.

1. ``derive_flavor`` scanned the model's free-text reason for capitalized
   words and treated any that was not an exact KG entity name as an unknown
   entity. Sentences start with capitals, so it matched "To", "ID",
   "Filtering" and "Receipt" and returned UNKNOWN_ENTITY for essentially
   every self-declared refusal. Measured 2026-07-30: wrong four times out of
   four. It was also unstable — the same prompt flipped flavor when the model
   wrote "The request" instead of "The question", because "The" is a stopword
   and "A" is one letter.

   The scan is GONE. The model now supplies ``unanswerable_kind`` directly
   (see draft.py); it had the right answer all along and we were discarding
   it to re-derive a worse one.

2. Because the flavor was UNKNOWN_ENTITY but ``offending_entity`` was never
   set, the message fell back to "that kind of record, which Spire doesn't
   track yet" — while the capability sentence immediately above it listed
   that very record type as supported. The message contradicted itself in a
   single paragraph.

3. The one sentence that said what was actually wrong came LAST, after ~90
   words listing eight entities and twenty-one filter names. Readers skimmed,
   hit the wall, and stopped.

THE FORMAT

Three labelled lines, adapted from the planner guard that was already the
best refusal in the codebase:

    Reason:   I can look up receipts, but not by customer account number.
    Solution: Scope them by customer or site instead — those I can do.
    Example:  receipts for ABC Application Software

Reason says what happened. Solution says what to do. Example is a prompt
that can be typed as-is.

TWO REFUSAL PATHS, ONE RENDERER

Refusals arrive from two places and they carry different quality of
information:

  - SELF-DECLARED (parser: ``response.unanswerable``) — flavor now from the
    model's ``unanswerable_kind``; detail is readable model prose.
  - KG VALIDATION (``validate_intent``) — flavor already precise; detail is
    a raw dump ("Unsupported filter type(s): ['customer_account_number'].
    Supported filters: [21 more]").

So the renderer prefers STRUCTURED FACTS (``offending_filters``,
``offending_entity``) whenever it has them, and falls back to the prose
detail only when it does not. That way the KG path's raw dump never reaches
a user, and the model's good prose is not thrown away.

WHY EXAMPLES COME FROM CODE, NOT THE MODEL

A model-invented example could name a customer or supplier that does not
exist. A suggestion that fails when typed is worse than no suggestion. The
model classifies; code supplies a known-good example.

WHAT PHASE 2A ADDED (COL-03, clauses 3 and 4)

A sixth flavor, UNSUPPORTED_FIELD, for a prompt that asks for a COLUMN the
entity does not have. Before it there were five kinds and none of them fit
a column problem, so the model chose the nearest — unsupported_filter —
which was the correct choice from a bad menu. The defect was the missing
option, not the model's judgement.

The visible consequence: a request for a 'created by' column was answered
"I can look up suppliers, but not the way this question narrows them. /
Narrow by country, status or name instead." Narrowing advice for a problem
about what to SHOW. A filter decides WHICH records come back; a field
decides WHAT IS SHOWN about them. The message layer had no way to tell
them apart.

Underneath that sat the same fault Phase 2 removed once already. Every one
of those refusals carried an accurate reason in ``detail`` — "The 'created
by' field is not available for suppliers." — and the renderer replaced it
with the generic sentence. The model's diagnosis was correct and was
discarded, exactly as the prose scan discarded it before. Two occurrences,
different code paths, same shape: if a third turns up, treat it as a
pattern rather than a coincidence.

This flavor should become RARE once COL-03's partial-resolution clause
lands. A prompt naming one good column and one bad one currently returns
nothing; it should return the good column and name the bad one. At that
point a total column refusal means every requested column failed, which is
the only case where refusing is the right answer.
"""

from __future__ import annotations

from typing import Optional

from spire.nl_parser.result import Refusal, RefusalFlavor
from spire.nl_parser.vocabulary import KGMenu


# ─────────────────────────────────────────────────────────────────────
# Human wording
# ─────────────────────────────────────────────────────────────────────

# Class names are ours, not the reader's. "ReceivablesInvoice" is a schema
# artifact; "AR invoices" is what someone asked for.
#
# This is the one place the message stops being self-updating from the KG: a
# new entity needs a label here or it falls back to its class name. That is a
# deliberate trade — a readable message beats a message that never needs
# touching.
# EVERY KG entity needs a row here, not just the eight TARGET entities. A
# refusal can name any record type the model saw — "tax lines for that
# invoice line" answers `ReceivablesTaxLine`, which is a real KG entity that
# simply cannot be a query ROOT. An earlier version listed only the target
# eight, so every related type fell through and the message went vague about
# a record Spire genuinely has.
#
# tests/test_nl_parser_capability.py asserts this table covers the KG. If a
# new entity is added, that test fails until a label lands here.
_ENTITY_LABELS: dict[str, str] = {
    "AccountCreditMemo": "credit memos on an account",
    "AccountReceipt": "account receipts",
    "AccountReceiptApplication": "receipt applications",
    "Address": "addresses",
    "Buyer": "buyers",
    "Classification": "supplier classifications",
    "Contact": "supplier contacts",
    "CreditMemo": "credit memos",
    "CustomerAccount": "customer accounts",
    "CustomerTransaction": "customer transactions",
    "Invoice": "supplier invoices",
    "PODistribution": "PO distributions",
    "POSchedule": "PO schedules",
    "PurchaseOrder": "purchase orders",
    "PurchaseOrderLine": "purchase order lines",
    "ReceivablesInvoice": "AR invoices",
    "ReceivablesInvoiceLine": "AR invoice lines",
    "ReceivablesInvoiceTransactionDFF": "AR invoice flexfield values",
    "ReceivablesTaxLine": "tax lines",
    "Site": "supplier sites",
    "StandardReceipt": "receipts",
    "Supplier": "suppliers",
}


def _label(entity: Optional[str]) -> str:
    """Plain-English plural for an entity. Never emits a raw class name.

    The old fallback returned the class name itself, which leaked
    "ReceivablesTaxLine" into a user-facing line — a schema artifact nobody
    outside this repo has seen. An unmapped entity now degrades to a generic
    phrase: less specific, but never wrong-looking.

    A NEW ENTITY THEREFORE NEEDS A LABEL HERE. If a message starts saying
    "those records" where it used to name a type, this table is what is out
    of date. That is the deliberate cost of readable wording — see the module
    docstring.
    """
    if not entity:
        return "those records"
    return _ENTITY_LABELS.get(entity, "those records")


def _humanize(name: str) -> str:
    """'customer_account_number' -> 'customer account number'."""
    return name.replace("_", " ").strip()


def _join_human(items: list[str]) -> str:
    """Join a list as 'a, b and c'. Empty -> ''. One -> itself."""
    items = [str(i) for i in items]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


# ─────────────────────────────────────────────────────────────────────
# Solutions and examples — code-supplied, never model-invented
# ─────────────────────────────────────────────────────────────────────

# Per-entity guidance for filter refusals: what DOES narrow this entity, and
# a prompt proving it. Identifiers here are real records on the demo pod.
_FILTER_GUIDANCE: dict[str, tuple[str, str]] = {
    "StandardReceipt": (
        "Scope them by customer or site instead — those I can do.",
        "receipts for ABC Application Software",
    ),
    "Supplier": (
        "Narrow by country, status or name instead.",
        "active suppliers in US",
    ),
    # NOT "narrow by supplier" — filtering POs by supplier name is exactly
    # what fails ("Open POs for supplier JGA" refuses, and so does "open
    # purchase orders for supplier EIP Inc"). Suggesting it sent the user
    # straight back into the same refusal. Mirrors the planner guard, which
    # asks for a PO number or a date bound.
    "PurchaseOrder": (
        "Give me a PO number instead, or a date bound.",
        "Show PO 2144 and its lines",
    ),
    "Invoice": (
        "Narrow by supplier or date instead.",
        "invoices for Lee Supplies",
    ),
    "ReceivablesInvoice": (
        "Narrow by customer name instead.",
        "open invoices for ABC Corporation Americas",
    ),
    "CustomerAccount": (
        "Narrow by customer name instead.",
        "account balance for ABC Corporation Americas",
    ),
    "CreditMemo": (
        "Narrow by customer name instead.",
        "credit memos for ABC Application Software",
    ),
}

# Per-entity guidance for COLUMN refusals: a prompt that names columns the
# entity actually has. Separate from _FILTER_GUIDANCE because the advice is
# a different shape — a filter refusal sends the user to a different way of
# NARROWING, a column refusal sends them to a different set of things to
# SHOW. Reusing the filter table here produced the measured defect: a
# request for a 'created by' column answered with "narrow by country,
# status or name instead".
#
# Every example below was RUN against the pod on 2026-07-31 and answered.
# They are also in scripts/prompts/10_refusal_examples.txt, which
# test_every_promised_example_is_verifiable enforces. Do not add an entry
# here without adding it there and running it — an example that refuses is
# worse than no example, because it is offered to someone who has just been
# told no.
_FIELD_GUIDANCE: dict[str, tuple[str, str]] = {
    "Supplier": (
        "Ask for the columns I do have — name, number, status.",
        "List active suppliers with supplier name, supplier number, and status",
    ),
    "Invoice": (
        "Ask for the columns I do have — invoice number, amount, date.",
        "Show me invoices for EIP Inc with invoice number, amount, and date",
    ),
    "PurchaseOrder": (
        "Ask for the columns I do have — order number, status, supplier.",
        "Order number and status for purchase orders created before 2015",
    ),
}

# Per-entity guidance when the record type is fine but no id was given.
_IDENTIFIER_GUIDANCE: dict[str, tuple[str, str]] = {
    "ReceivablesInvoice": (
        "Give me the transaction number or the CustomerTransactionId.",
        "Get the AR invoice with CustomerTransactionId 300000248096352",
    ),
    "PurchaseOrder": (
        "Give me the PO number.",
        "What is the risk rating on PO 701337 and why?",
    ),
    "Invoice": (
        "Name the supplier, or give me the invoice number.",
        "invoices for Lee Supplies",
    ),
    "Supplier": (
        "Give me the supplier name.",
        "supplier sites for Lee Supplies",
    ),
    # Address and StandardReceipt are scoped by ONE OF TWO things, not a
    # single id — so the solution names both options. The planner guards for
    # these entities raise MISSING_IDENTIFIER; without an entry here the
    # message would fall to the generic identifier fallback and lose the
    # "supplier OR country" / "customer OR site" nuance the guards enforce.
    "Address": (
        "Name the supplier, or give me a country.",
        "addresses for supplier 1252",
    ),
    "StandardReceipt": (
        "Name the customer, or give me a site.",
        "receipts for ABC Application Software",
    ),
    # Child records are identified by their PARENT, which is what the user
    # has to supply — naming a tax-line id would be no help to anyone.
    "ReceivablesTaxLine": (
        "Name the invoice — its number or its id.",
        "Get tax lines for invoice 300000248096352",
    ),
    "ReceivablesInvoiceLine": (
        "Name the invoice — its number or its id.",
        "Show invoice lines for invoice 300000248096352",
    ),
    "ReceivablesInvoiceTransactionDFF": (
        "Name the invoice — its number or its id.",
        "Get the AR invoice with CustomerTransactionId 300000248096352",
    ),
    "PurchaseOrderLine": (
        "Name the PO — its order number.",
        "Show PO 2144 and its lines",
    ),
    "POSchedule": (
        "Name the PO — its order number.",
        "Show PO 2144 and its schedules",
    ),
    "PODistribution": (
        "Name the PO — its order number.",
        "Show PO 2144 and its distributions",
    ),
    "Contact": (
        "Name the supplier.",
        "Get supplier contacts for Lee Supplies",
    ),
    "Site": (
        "Name the supplier.",
        "supplier sites for Lee Supplies",
    ),
}

# Entities Spire HAS but which cannot be a query root — you reach them
# through their parent. "show me purchase order line items" is not an
# unknown record type; it is a known one asked for the wrong way, and saying
# "isn't something I know about" is simply false.
#
# Keyed by entity, giving the parent to ask for instead.
_NOT_A_ROOT_GUIDANCE: dict[str, tuple[str, str]] = {
    "PurchaseOrderLine": (
        "Ask for the PO and its lines together.",
        "Show PO 2144 and its lines",
    ),
    "POSchedule": (
        "Ask for the PO and its schedules together.",
        "Show PO 2144 and its schedules",
    ),
    "PODistribution": (
        "Ask for the PO and its distributions together.",
        "Show PO 2144 and its distributions",
    ),
    "ReceivablesInvoiceLine": (
        "Ask for the invoice and its lines together.",
        "Show invoice lines for invoice 300000248096352",
    ),
    "ReceivablesTaxLine": (
        "Ask for the invoice and its tax lines together.",
        "Get tax lines for invoice 300000248096352",
    ),
    "ReceivablesInvoiceTransactionDFF": (
        "Ask for the invoice and its flexfield values together.",
        "Get the AR invoice with CustomerTransactionId 300000248096352",
    ),
    "CustomerTransaction": (
        "Ask for the customer account and its transactions together.",
        "open invoices for ABC Corporation Americas",
    ),
    "AccountReceipt": (
        "Ask for the customer account and its receipts together.",
        "receipts for ABC Application Software",
    ),
    "AccountReceiptApplication": (
        "Ask for the customer account and its receipts together.",
        "receipts for ABC Application Software",
    ),
    "AccountCreditMemo": (
        "Ask for the customer account and its credit memos together.",
        "credit memos for ABC Application Software",
    ),
    "Contact": (
        "Ask for the supplier and its contacts together.",
        "Get supplier contacts for Lee Supplies",
    ),
    "Site": (
        "Ask for the supplier and its sites together.",
        "supplier sites for Lee Supplies",
    ),
    "Classification": (
        "Ask for the supplier and its classifications together.",
        "suppliers with classification Minority Owned",
    ),
    "Address": (
        "Ask for the supplier and its addresses together.",
        "Suppliers with their addresses",
    ),
    "Buyer": (
        "Ask for the PO and its buyer together.",
        "Show PO 2144 and its buyer",
    ),
}

# Entity-aware examples for aggregation refusals. The advice is "ask for the
# records and total them yourself" — so the example must show THOSE records,
# not some other entity's. An entity-blind fallback answered a supplier
# question with a receipts example.
_OPERATION_EXAMPLES: dict[str, str] = {
    "Supplier": "active suppliers in US",
    "PurchaseOrder": "Show PO 2144 and its lines",
    "Invoice": "invoices for Lee Supplies",
    "ReceivablesInvoice": "open invoices for ABC Corporation Americas",
    "StandardReceipt": "receipts for ABC Application Software",
    "CreditMemo": "credit memos for ABC Application Software",
    "CustomerAccount": "account balance for ABC Corporation Americas",
    "Address": "Suppliers with their addresses",
}

# Fallback per flavor, used when there is no entity-specific entry.
#
# Each example DEMONSTRATES its own Solution — naming a record for
# missing_identifier, a supported filter for unsupported_filter, and so on.
# An earlier draft reused one example across four flavors; it read as filler,
# because an example that does not illustrate the advice above it is filler.
_FALLBACK: dict[RefusalFlavor, tuple[str, str]] = {
    RefusalFlavor.MISSING_IDENTIFIER: (
        "Name the record — its number or its id.",
        "Get tax lines for invoice 300000248096352",
    ),
    RefusalFlavor.UNSUPPORTED_FILTER: (
        "Narrow it by something I do have — a name, a country, a status.",
        "active suppliers in US",
    ),
    RefusalFlavor.UNSUPPORTED_FIELD: (
        "Ask for columns the record actually has.",
        "List active suppliers with supplier name, supplier number, and status",
    ),
    RefusalFlavor.UNSUPPORTED_OPERATION: (
        "Ask me for the records themselves and do the rest your side.",
        "receipts for ABC Application Software",
    ),
    RefusalFlavor.UNKNOWN_ENTITY: (
        "",  # filled from the KG menu — see _solution_and_example
        "invoices for Lee Supplies",
    ),
    RefusalFlavor.UNPARSEABLE: (
        "Name a record type and one thing to narrow it by.",
        "invoices for Lee Supplies",
    ),
}


# ─────────────────────────────────────────────────────────────────────
# Flavor derivation
# ─────────────────────────────────────────────────────────────────────

# Accepted values of DraftIntent.unanswerable_kind, mapped to flavors. A
# value outside this set is ignored rather than trusted — the model is asked
# for one of five strings and usually gives one, but a typo should degrade to
# the honest fallback, not crash.
_KIND_TO_FLAVOR: dict[str, RefusalFlavor] = {
    "missing_identifier": RefusalFlavor.MISSING_IDENTIFIER,
    "unsupported_filter": RefusalFlavor.UNSUPPORTED_FILTER,
    "unsupported_field": RefusalFlavor.UNSUPPORTED_FIELD,
    "unsupported_operation": RefusalFlavor.UNSUPPORTED_OPERATION,
    "unknown_entity": RefusalFlavor.UNKNOWN_ENTITY,
    "unparseable": RefusalFlavor.UNPARSEABLE,
}


def derive_flavor(
    draft_reason: str,
    draft_target_entity: str,
    menu: KGMenu,
    draft_kind: str = "",
    draft_entity: str = "",
) -> RefusalFlavor:
    """Flavor for a SELF-DECLARED unanswerable draft.

    Order of trust:

    1. ``draft_kind`` — the model's own classification. It has the prompt,
       the entity list and the filter list in front of it, and measurement
       showed it classifying correctly where our re-derivation did not.
    2. ``draft_target_entity`` against the KG — a hard, checkable fact. If
       the model named an entity the KG does not know, that is
       UNKNOWN_ENTITY whatever else it said.
    3. UNPARSEABLE — the honest fallback.

    ``draft_kind`` is keyword-only in spirit but positional-compatible: it
    was appended last so existing three-argument callers keep working.

    **There is deliberately no prose scan.** The previous implementation
    searched the reason text for capitalized words and treated unrecognised
    ones as entity names. It matched "To", "ID", "Filtering" and "Receipt",
    and returned UNKNOWN_ENTITY for four of four measured refusals. Removing
    it is the point of this rewrite, not an oversight — do not reintroduce a
    heuristic over model prose here. If the kind is unreliable, fix the field
    description in draft.py, where the model can act on it.
    """
    kind = (draft_kind or "").strip().lower()
    flavor = _KIND_TO_FLAVOR.get(kind)

    # `draft_target_entity` is REQUIRED to be empty on a self-declared
    # refusal, so checking only it meant the guard below never ran on the
    # path that needed it most. `draft_entity` is the descriptive field the
    # model fills purely to word the reply.
    entity = (draft_target_entity or draft_entity or "").strip()
    entity_unknown = bool(entity) and not menu.is_known_entity(entity)

    if flavor is not None:
        # One correction we DO apply: the model may say "unknown_entity"
        # about a record type that IS a valid query root. That produced the
        # self-contradicting message — listing a type as supported and then
        # denying it.
        #
        # The test is TARGET entity, not merely known. An entity that is in
        # the KG but cannot be a root (PurchaseOrderLine, ReceivablesTaxLine)
        # is a legitimate UNKNOWN_ENTITY refusal with its own branch in
        # _reason_line — "I can look up purchase order lines, but only as
        # part of the record they belong to". An earlier version tested
        # `is_known_entity` here, which downgraded those to UNPARSEABLE and
        # so skipped that branch entirely, leaking the raw class name from
        # the model's prose into the user's face.
        if flavor is RefusalFlavor.UNKNOWN_ENTITY and entity in menu.target_entities:
            return RefusalFlavor.UNPARSEABLE
        return flavor

    if entity_unknown:
        return RefusalFlavor.UNKNOWN_ENTITY

    return RefusalFlavor.UNPARSEABLE


# ─────────────────────────────────────────────────────────────────────
# Message rendering
# ─────────────────────────────────────────────────────────────────────


def _known_entity(refusal: Refusal, menu: KGMenu) -> Optional[str]:
    """The refusal's entity, but only if it is a real KG entity we can name.

    ``unanswerable_entity`` is model-supplied prose-adjacent input: on "tax
    lines for that invoice line" the model answered "ReceivablesTaxLine",
    which is a plausible-sounding type the KG does not have. Filtering here
    means one check protects every branch below, rather than each branch
    having to remember.
    """
    entity = refusal.offending_entity
    if not entity:
        return None
    if not menu.is_known_entity(entity):
        # Not a KG entity at all — the model invented a plausible-sounding
        # type. Decline to name it rather than repeat the invention back.
        return None
    if entity not in _ENTITY_LABELS:
        # A real entity with no label yet. Degrade to the generic phrase
        # rather than leak a class name — and the tripwire test will have
        # already failed, so this should not survive a commit.
        return None
    return entity


def _reason_line(refusal: Refusal, menu: KGMenu) -> str:
    """The 'what happened' line.

    Structured facts win over prose. The KG-validation path's ``detail`` is a
    raw dump of every supported filter name; the self-declared path's is
    readable. Preferring facts means the dump never reaches a user, and the
    model's prose is used only where it is the best thing available.
    """
    flavor = refusal.flavor
    entity = _known_entity(refusal, menu)
    entity_label = _label(entity)

    if flavor is RefusalFlavor.UNSUPPORTED_FILTER:
        # The KG-validation path names the offending filters; the
        # self-declared path does not. Without this second branch the latter
        # fell through to raw model prose, which leaked internal filter names
        # ("requires ... the 'by_customer_name' filter") straight to the user.
        if refusal.offending_filters:
            bad = _join_human([_humanize(f) for f in refusal.offending_filters])
            if entity:
                return f"I can look up {entity_label}, but not by {bad}."
            return f"I can't narrow records by {bad}."
        if entity:
            return (
                f"I can look up {entity_label}, but not the way this "
                "question narrows them."
            )
        return "I can't narrow records that way."

    if flavor is RefusalFlavor.UNSUPPORTED_FIELD:
        # Structured facts first, as everywhere else.
        if refusal.offending_fields:
            bad = _join_human(
                [f"'{_humanize(f)}'" for f in refusal.offending_fields]
            )
            if entity:
                return f"I can look up {entity_label}, but I don't have {bad}."
            return f"I don't have {bad} on that record."
        # No structured columns — fall back to the model's own words.
        #
        # A DELIBERATE departure from "structured facts win over prose", and
        # the reason is measured rather than assumed. On the KG-validation
        # path `detail` is a raw dump and must never reach a user; on the
        # SELF-DECLARED path, which is the only one that produces this
        # flavor, it was accurate in all five cases measured 2026-07-31:
        #
        #   "The 'created by' field is not available for suppliers."
        #   "The requested \"audit columns\" are not available as a
        #    specific field."
        #   "The field 'quantum flux' is not supported for the Supplier
        #    entity."
        #   "The requested field 'flurbles' is not supported."
        #
        # Every one of those was discarded in favour of "not the way this
        # question narrows them". Throwing away a correct diagnosis to print
        # a wrong one is the UX-01 defect in a second location; this branch
        # is that fix. If a dump ever does appear here, prefer widening
        # `offending_fields` upstream over deleting this fallback — the
        # words are good, they were simply never used.
        if refusal.detail:
            return refusal.detail
        if entity:
            return (
                f"I can look up {entity_label}, but not the columns this "
                "asks for."
            )
        return "I don't have the columns this asks for."

    if flavor is RefusalFlavor.UNKNOWN_ENTITY:
        # Two very different situations wear this flavor, and conflating them
        # produced a message that was flatly false. "show me purchase order
        # line items" got "PurchaseOrderLine isn't something I know about" —
        # but PurchaseOrderLine IS a KG entity; it just cannot be a query
        # root. Denying a record type Spire has is the same contradiction
        # this rewrite exists to remove, wearing a different hat.
        if entity and entity not in menu.target_entities:
            return (
                f"I can look up {entity_label}, but only as part of the "
                "record they belong to."
            )
        if entity:
            return f"I don't have {entity_label}."
        # Not a KG entity at all. `offending_entity` is the model's own word
        # for it — safe to echo, because there is no label to look up and
        # naming it is more useful than "that kind of record".
        what = refusal.offending_entity or "that kind of record"
        return f"{what} isn't something I know about."

    if flavor is RefusalFlavor.MISSING_IDENTIFIER:
        if entity:
            return (
                f"I can look up {entity_label}, but this doesn't say "
                "which one."
            )
        return "I'm not sure which record you mean."

    if flavor is RefusalFlavor.UNSUPPORTED_OPERATION:
        # QA-05: surface the specific reason when the refusal carries one,
        # the same rule UNSUPPORTED_FIELD follows above. This flavor is
        # broad — it covers aggregations, rankings, comparisons, AND
        # deliberate carve-outs like the Site-listing refusal (AI-11) and
        # "everything about supplier X". The generic sentence below is
        # right ONLY for the aggregation/compare family; for a carve-out
        # that set a precise detail, printing "needs a total, a ranking, a
        # trend" throws away the correct diagnosis for a wrong one — the
        # same misdirection UX-01 removed elsewhere. When detail is set,
        # it IS the reason; fall back to the generic line only when it is
        # not.
        if refusal.detail:
            return refusal.detail
        # Deliberately broader than "totals and grouping". This flavor also
        # covers rankings and side-by-side comparisons — "compare the
        # lifecycle of PO 701337 and PO 162034" is neither a total nor a
        # trend, and telling that user their question "needs totals" was
        # simply wrong.
        return (
            "This needs something I can't work out yet — a total, a "
            "ranking, a trend, or two records set side by side."
        )

    # UNPARSEABLE — the model's own words are the best available.
    return refusal.detail or "I'm not sure which records you're after here."


def _solution_and_example(refusal: Refusal, menu: KGMenu) -> tuple[str, str]:
    """The 'what to do' and 'type this' lines."""
    flavor = refusal.flavor
    entity = _known_entity(refusal, menu)

    if flavor is RefusalFlavor.UNSUPPORTED_FILTER and entity in _FILTER_GUIDANCE:
        return _FILTER_GUIDANCE[entity]

    if flavor is RefusalFlavor.UNSUPPORTED_FIELD and entity in _FIELD_GUIDANCE:
        return _FIELD_GUIDANCE[entity]

    if flavor is RefusalFlavor.MISSING_IDENTIFIER and entity in _IDENTIFIER_GUIDANCE:
        return _IDENTIFIER_GUIDANCE[entity]

    if (
        flavor is RefusalFlavor.UNKNOWN_ENTITY
        and entity
        and entity not in menu.target_entities
        and entity in _NOT_A_ROOT_GUIDANCE
    ):
        return _NOT_A_ROOT_GUIDANCE[entity]

    solution, example = _FALLBACK[flavor]

    if flavor is RefusalFlavor.UNSUPPORTED_OPERATION and entity in _OPERATION_EXAMPLES:
        example = _OPERATION_EXAMPLES[entity]

    if flavor is RefusalFlavor.UNKNOWN_ENTITY and not entity:
        # The ONLY case where listing what exists is the actual answer: the
        # record type genuinely is not there. When the entity IS known but
        # is not a root, _NOT_A_ROOT_GUIDANCE above has already returned.
        # Everywhere else the list is noise in front of the point.
        known = [_label(e) for e in sorted(menu.target_entities)]
        if known:
            solution = f"What I do have: {_join_human(known)}."
        else:
            solution = "I don't have that record type."

    return solution, example


def capability_message(refusal: Refusal, menu: KGMenu) -> str:
    """Build the user-facing refusal message: three labelled lines.

        Reason:   ...

        Solution: ...

        Example:  ...

    A blank line separates each label so the refusal reads as three distinct
    points rather than one wrapped block — the parts are what the reader acts
    on. Joined with a blank line for every refusal (parser and planner guard
    alike), so the spacing is uniform wherever a refusal is shown.

    Kept under the original name so the runners need no change.
    """
    reason = _reason_line(refusal, menu)
    solution, example = _solution_and_example(refusal, menu)

    lines = [f"Reason:   {reason}"]
    if solution:
        lines.append(f"Solution: {solution}")
    if example:
        lines.append(f"Example:  {example}")
    return "\n\n".join(lines)


def capabilities_sentence(menu: KGMenu) -> str:
    """One sentence describing what Spire CAN do, built from the KG menu.

    No longer used by ``capability_message`` — it was the ~90-word preamble
    that buried the point. Kept public because "what can you do?" is a fair
    question and something should be able to answer it directly.
    """
    targets = sorted(menu.target_entities)
    if targets:
        can = f"Spire can look up {_join_human([_label(t) for t in targets])}"
    else:
        can = "Spire can look up procurement records"

    filters = sorted(menu.filter_types)
    if filters:
        can += f", filter them ({_join_human([_humanize(f) for f in filters])})"

    return can + "."


# Backward-compatible alias: the previous private name, in case anything
# outside this module imported it.
_capabilities_sentence = capabilities_sentence


