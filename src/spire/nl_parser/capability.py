"""
Capability-framed refusal — feature 8.

Feature 1 already detects out-of-scope prompts and emits a structured
``Refusal`` (flavor + raw facts). It left two things blunt, both fixed here:

1. FLAVOR DERIVATION. When the model self-declares ``unanswerable`` (the
   structural half of the silent-rewrite fix), feature 1 tagged the refusal
   ``UNPARSEABLE`` unconditionally — even when the truer flavor is
   UNKNOWN_ENTITY (contracts) or UNSUPPORTED_OPERATION (aggregation). The model
   knows it can't answer but not *which kind* of can't; the KG does. So
   ``derive_flavor`` re-derives the flavor from the draft + the KG menu, the
   same source the rest of the parser trusts, and only falls back to
   UNPARSEABLE when nothing more specific fits.

2. CAPABILITY-FRAMED WORDING. Feature 1's user-facing line was a bare
   "Spire can't answer this (flavor): <detail>". ``capability_message`` replaces
   that with what Spire *can* do, derived from the KG menu (so it never goes
   stale — when contracts are added in feature 6, the message updates itself),
   followed by a one-line note on why this particular prompt falls outside it.

WHY KG-SOURCED, NOT HAND-WRITTEN (Q3): the capability statement is generated
from the same KGMenu the parser already reads. There is exactly ONE template;
the flavor only changes the "what's missing" slot. No three hand-written
paragraphs to drift out of sync with the KG.
"""

from __future__ import annotations

import re
from typing import Optional

from spire.nl_parser.result import Refusal, RefusalFlavor
from spire.nl_parser.vocabulary import KGMenu

# Phrases in a self-declared ``unanswerable_reason`` that signal an aggregation
# / ranking / totals request — i.e. an operation the system has no concept of,
# which is UNSUPPORTED_OPERATION rather than a vague-prompt UNPARSEABLE.
_AGGREGATION_HINTS = (
    "aggregat",   # aggregate, aggregation
    "sum ",
    "total",
    "top ",
    "rank",
    "count of",
    "average",
    "group by",
    "per ",
    "by buyer",
    "by supplier",
)


def _looks_like_aggregation(reason: str) -> bool:
    text = reason.lower()
    return any(hint in text for hint in _AGGREGATION_HINTS)


def _mentioned_unknown_entity(reason: str, menu: KGMenu) -> Optional[str]:
    """Return an entity name mentioned in the reason that the KG does NOT know,
    if any. Lets a self-declared refusal that names 'Contract' be tagged
    UNKNOWN_ENTITY instead of UNPARSEABLE.

    Deliberately conservative: only matches capitalized words that look like
    entity names, and only returns one not already in the KG. A miss just
    leaves the flavor at UNPARSEABLE — honest, if coarse.
    """
    # Candidate entity-like tokens: Capitalized words (Contract, Warehouse).
    candidates = re.findall(r"\b[A-Z][a-zA-Z]+\b", reason)
    for tok in candidates:
        # Singularize a trailing 's' so "Contracts" matches a "Contract" check.
        singular = tok[:-1] if tok.endswith("s") and len(tok) > 3 else tok
        for form in (tok, singular):
            if not menu.is_known_entity(form):
                # Only treat it as an unknown ENTITY if it isn't obviously a
                # stray English word. Heuristic: entity names referenced in a
                # reason are usually nouns the prompt centered on; we accept the
                # token as-is. The cost of a false positive is a slightly-wrong
                # flavor, never a crash or a wrong answer.
                if form.lower() not in _ENGLISH_STOPWORDS:
                    return form
    return None


# Capitalized words that can open a sentence in unanswerable_reason but are not
# entity names. Keeps "Needs spend aggregation" from being read as entity
# "Needs". Lowercased for comparison.
_ENGLISH_STOPWORDS = {
    "needs", "need", "the", "this", "that", "spire", "it", "requires",
    "require", "no", "not", "cannot", "there", "query", "prompt", "request",
    "ask", "asking", "wants", "want",
}


def derive_flavor(draft_reason: str, draft_target_entity: str, menu: KGMenu) -> RefusalFlavor:
    """Derive the best flavor for a SELF-DECLARED unanswerable draft.

    Feature 1 mapped every self-declared refusal to UNPARSEABLE. Here we do
    better using the KG menu:

      - If the model left a target_entity and the KG doesn't know it
        -> UNKNOWN_ENTITY (e.g. 'Contract').
      - Else if the reason describes aggregation/ranking/totals
        -> UNSUPPORTED_OPERATION (checked before the loose entity scan, so
        "PO total by buyer" reads as aggregation, not unknown-entity 'PO').
      - Else if the reason names an entity the KG doesn't know
        -> UNKNOWN_ENTITY (e.g. reason "needs a Contract entity").
      - Else -> UNPARSEABLE (genuinely vague; the honest fallback).

    Note this is only for the self-declared path. KG-validation refusals
    (validate_intent) already carry a precise flavor and are not rerouted here.
    """
    entity = (draft_target_entity or "").strip()
    if entity and not menu.is_known_entity(entity):
        return RefusalFlavor.UNKNOWN_ENTITY

    # Aggregation is checked BEFORE the loose entity-name scan: a reason like
    # "total open PO value by buyer" mentions 'PO' (an unknown capitalized
    # token) but is fundamentally an aggregation request, not an unknown-entity
    # one. The operation signal wins when both are present.
    if _looks_like_aggregation(draft_reason or ""):
        return RefusalFlavor.UNSUPPORTED_OPERATION

    named_unknown = _mentioned_unknown_entity(draft_reason or "", menu)
    if named_unknown is not None:
        return RefusalFlavor.UNKNOWN_ENTITY

    return RefusalFlavor.UNPARSEABLE


def _capabilities_sentence(menu: KGMenu) -> str:
    """One sentence describing what Spire CAN do, built from the KG menu."""
    targets = sorted(menu.target_entities)
    if targets:
        entity_phrase = _join_human(targets)
        can = f"Spire can look up {entity_phrase}"
    else:
        can = "Spire can look up procurement records"

    # Filters, lightly humanized. These are the menu's filter types; we keep
    # the wording generic so adding a filter to the KG needs no code change.
    filters = sorted(menu.filter_types)
    if filters:
        can += f", filter them ({_join_human(filters)})"

    return can + "."


def _join_human(items: list[str]) -> str:
    """Join a list as 'a, b and c'. Empty -> ''. One -> itself."""
    items = [str(i) for i in items]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _whats_missing(refusal: Refusal) -> str:
    """The flavor-specific 'why this prompt falls outside' clause."""
    flavor = refusal.flavor
    if flavor is RefusalFlavor.UNKNOWN_ENTITY:
        what = refusal.offending_entity or "that kind of record"
        return f"This question is about {what}, which Spire doesn't track yet."
    if flavor is RefusalFlavor.UNSUPPORTED_OPERATION:
        return (
            "This question needs an aggregation or ranking "
            "(totals, top-N, grouping), which Spire can't compute yet."
        )
    if flavor is RefusalFlavor.UNSUPPORTED_FILTER:
        if refusal.offending_filters:
            bad = _join_human(refusal.offending_filters)
            return f"It asks to filter by {bad}, which isn't supported."
        return "It asks for a filter that isn't supported."
    # UNPARSEABLE
    return (
        "This question is too open-ended to pin to a specific record and "
        "filter. Try naming the entity and the constraint you want."
    )


def capability_message(refusal: Refusal, menu: KGMenu) -> str:
    """Build the capability-framed user message for a refusal (feature 8).

    Two sentences: what Spire CAN do (from the KG), then why THIS prompt is
    outside that. Replaces feature 1's blunt 'can't answer (flavor): detail'.
    """
    return f"{_capabilities_sentence(menu)} {_whats_missing(refusal)}"
