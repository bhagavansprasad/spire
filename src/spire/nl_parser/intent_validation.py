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
  4. columns: split requested fields   -> NO refusal; the query
     into known / unknown                runs, unknown names are
                                         recorded on the Intent

Step 3 mirrors the planner's own _validate_intent_filters, which reports ALL
unknown filter types at once rather than the first.

Step 4 (COL-03) is deliberately NOT a refusal gate. An unknown COLUMN does
not make a query out of scope the way an unknown entity or filter does: the
records still exist and the valid columns can still be shown. So instead of
refusing, Step 4 mutates the Intent — known columns stay in ``fields``,
unknown ones move to ``unresolved_fields`` — and returns None. Display names
the unresolved columns back to the user and offers the entity's available
columns. This is the one step that mutates the Intent rather than only
inspecting it, and the only column handling that is deterministic rather
than left to the model; before it, an unknown column was refused wholesale
by the model, discarding the valid columns named alongside it.

Returns None when the draft is fully valid — including the partial-column
case, which is a SUCCESS (rows with a note), not a refusal.
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
        None if the Intent is fully KG-valid, OR valid except for unknown
        columns (which are moved to intent.unresolved_fields rather than
        refused — see Step 4). Otherwise a Refusal naming the single flavor
        that applies (B1 ordering).

    Side effect:
        On the field-split step (COL-03), MUTATES ``intent``: unknown column
        names are removed from ``intent.fields`` and placed in
        ``intent.unresolved_fields``. The Intent is fresh per parse and not
        shared, so this is safe. No other step mutates the Intent.
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

    # ── Step 3b: reject includes that have no standalone fetcher ─────
    # AI-11 / QA-04. "supplier sites for X" parses to Supplier with
    # include=['Site']. Site has no site-listing tool — the only Site tool
    # (search_suppliers_by_site_bu) is a BU *filter* and needs a
    # business_unit the listing does not carry. The planner builds a step
    # calling it with supplier_id only, and the executor crashes on the
    # missing required arg (the sole exit-1 in the QA campaign). Refuse
    # here, at parse time, before a plan is built — the same principle the
    # findings doc drew: validate required args at PLAN time, not execute
    # time. Site is refused honestly rather than silently substituting a
    # different resource (contrast AI-10, where "sites" degrades to
    # addresses — a separate parser-mapping bug, not fixed here).
    if "Site" in intent.include:
        return Refusal(
            flavor=RefusalFlavor.UNSUPPORTED_OPERATION,
            detail=(
                "Supplier sites aren't available as a standalone listing "
                "(there is no site-list fetcher; the only site tool filters "
                "suppliers by business unit). Ask for suppliers with a site "
                "in a named business unit, or for the supplier's addresses."
            ),
            offending_entity=entity,
        )

    # ── Step 4: split requested columns into resolvable vs unresolved ──
    # COL-03. Unlike the gates above, an unknown COLUMN does not refuse the
    # query. The entity and filters are valid, so the query runs; the
    # requested column list is split against the KG field catalog. Known
    # names stay in intent.fields (projection prints them); unknown ones
    # move to intent.unresolved_fields, which display names back to the
    # user alongside the entity's available columns. No substitution: an
    # unknown column is reported, never swapped for a near-match.
    #
    # This MUTATES the intent (the only gate that does) — resolving fields
    # is the point, not merely checking them. Safe because parse() builds a
    # fresh Intent immediately before this call; it is never shared.
    #
    # No-op when no columns were named (the common case) and for aggregate/
    # compare intents, which skip validate_intent entirely upstream.
    if intent.fields:
        known: list[str] = []
        unresolved: list[str] = []
        for col in intent.fields:
            (known if menu.is_known_field(entity, col) else unresolved).append(col)
        intent.fields = known
        intent.unresolved_fields = unresolved

    return None

