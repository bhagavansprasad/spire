"""
KG validation of a draft Intent — Q2 direction 2 (checkpoint 3).

After the LLM produces a draft Intent, the parser validates it BACK against
the KG menu and rejects anything out of scope, producing a typed Refusal
(see docs/designs/feature_1_nl_parser_design.md, Q3).

VALIDATION ORDER (decision B1):
The target entity is a FIRST-FAIL GATE; filters are COLLECTED all-at-once
only once the entity is known to be valid. Rationale: filters only mean
something relative to the entity. If the entity is wrong, listing filter
problems is noise — "Contracts aren't in the system" is the complete answer.
So a single Refusal never mixes flavors.

  1. entity not in the KG at all      -> UNKNOWN_ENTITY        (stop)
  2. entity known but not a valid
     target (no fetcher)              -> UNSUPPORTED_OPERATION (stop)
  3. entity valid: collect every
     filter type not in the KG        -> UNSUPPORTED_FILTER    (all at once)

Step 3 mirrors the planner's own _validate_intent_filters, which reports ALL
unknown filter types at once rather than the first.

Returns None when the draft is fully valid (nothing to refuse).
"""

from __future__ import annotations

from typing import Optional

from spire.nl_parser.result import Refusal, RefusalFlavor
from spire.nl_parser.vocabulary import KGMenu
from spire.planner.planner import Intent


def validate_intent(intent: Intent, menu: KGMenu) -> Optional[Refusal]:
    """Validate a draft Intent against the KG menu.

    Args:
        intent: The shape-valid Intent produced from the LLM's draft.
        menu: The KG menu (allowed entities, targets, filter types).

    Returns:
        None if the Intent is fully KG-valid. Otherwise a Refusal naming the
        single flavor that applies (B1 ordering).
    """
    entity = intent.target_entity

    # ── Gate 1: entity must exist in the KG at all ───────────────────
    if not menu.is_known_entity(entity):
        return Refusal(
            flavor=RefusalFlavor.UNKNOWN_ENTITY,
            detail=(
                f"target_entity {entity!r} is not a known entity. "
                f"Known target entities: {sorted(menu.target_entities)}."
            ),
            offending_entity=entity,
        )

    # ── Gate 2: entity must be a valid target (have a fetcher) ───────
    if not menu.is_valid_target(entity):
        return Refusal(
            flavor=RefusalFlavor.UNSUPPORTED_OPERATION,
            detail=(
                f"target_entity {entity!r} is a known entity but cannot be "
                f"queried directly (no entity-level fetcher). Valid target "
                f"entities: {sorted(menu.target_entities)}."
            ),
            offending_entity=entity,
        )

    # ── Step 3: collect all unsupported filter types at once ─────────
    bad_filters = [
        f.get("type")
        for f in intent.filters
        if not menu.is_known_filter(f.get("type"))
    ]
    if bad_filters:
        return Refusal(
            flavor=RefusalFlavor.UNSUPPORTED_FILTER,
            detail=(
                f"Unsupported filter type(s): {bad_filters}. "
                f"Supported filters: {sorted(menu.filter_types)}."
            ),
            offending_entity=entity,
            offending_filters=[bf for bf in bad_filters if bf is not None],
        )

    return None
