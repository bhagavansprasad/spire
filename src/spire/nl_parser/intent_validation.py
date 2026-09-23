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
  3b. entity valid: check every
     include against the KG's edge
     graph                             -> UNSUPPORTED_OPERATION (first bad)
  4. columns: split requested fields   -> NO refusal; the query
     into known / unknown                runs, unknown names are
                                         recorded on the Intent

Step 3 mirrors the planner's own _validate_intent_filters, which reports ALL
unknown filter types at once rather than the first.

Step 3b (BUG-2) is the include gate. Two failure modes it catches, both of
which reach the planner or the executor today and cause a raw crash:

  (a) The requested include has NO declared edge from the target entity
      (or from its root, for the sibling case). This is the S1 case:
      PurchaseOrder + include=['Supplier']. The KG declares
      Supplier -> PurchaseOrder (HAS_PURCHASE_ORDER) but no reverse, and
      the planner's Block 3 tries only the forward direction. It raises
      a raw KeyError, which plan_node wraps as an error and run_graph
      prints to stderr as a hard failure.

  (b) The requested include HAS an edge but its only tool is a REVERSE
      filter — it needs an argument beyond the parent key that the
      executor will not supply. This is the Classification case on
      Supplier: HAS_CLASSIFICATION exists, and its only tool
      (search_suppliers_by_classification) needs a 'classification'
      argument, so the executor crashes on the missing arg. Site is the
      same shape and is caught today by a hardcoded gate; Classification
      is not.

The gate refuses BOTH classes with UNSUPPORTED_OPERATION. It is deliberately
conservative: a single-element include list is checked against the target;
multi-element lists are checked as a CHAIN (each item against the previous
item, with the sibling-under-root fallback the planner uses). The chain
matters because the parser prompt explicitly emits two-hop include chains
(e.g. PurchaseOrder + ['POSchedule','PODistribution']), and a
per-element-from-target check would falsely refuse the second hop.

The validator also SIMULATES the planner's Block 2 before running the
include chain, because an edge-traversal filter (has_open_PO,
has_no_recent_invoices, ...) updates the "previous entity" the first
include chains from. Without the simulation, an intent like
Supplier + has_open_PO + include=['Buyer'] would be falsely refused:
the include chains from PurchaseOrder (after Block 2), not from Supplier.

WHEN THE GATE IS A NO-OP (the edge_pairs precondition)
The general include gate is SKIPPED when the menu carries no edge data
(``menu.edge_pairs`` is empty). A KGMenu can legitimately be built by hand
with a minimal set of fields — the parser's unit-test fixtures do exactly
this, populating entity names, filter types and columns but not edges.
The gate cannot validate edges it does not have, so it declines to fire.
This mirrors the contract KGMenu already follows for its other optional
fields: ``field_synonyms={}`` makes synonym expansion a no-op,
``entity_columns={}`` makes available_columns return [], and an empty
``edge_pairs`` makes the include gate pass everything through.

The production menu from ``load_kg_menu()`` ALWAYS populates ``edge_pairs``
(17 rows on this pod, asserted by the load path), so production is
unaffected. When the gate is skipped, an un-wireable include reaches the
planner — which is exactly the case BUG-3 handles by raising a structured
RefusalError instead of a raw KeyError. The skip is safe because the
layered defence still holds.

The Site gate is NOT subject to this precondition — it is a hardcoded
string check and does not consult edge data.

Step 4 (COL-03) is deliberately NOT a refusal gate. An unknown COLUMN does
not make a query out of scope the way an unknown entity, filter or include
does: the records still exist and the valid columns can still be shown. So
instead of refusing, Step 4 mutates the Intent — known columns stay in
``fields``, unknown ones move to ``unresolved_fields`` — and returns None.
Display names the unresolved columns back to the user and offers the
entity's available columns. This is the one step that mutates the Intent
rather than only inspecting it, and the only column handling that is
deterministic rather than left to the model; before it, an unknown column
was refused wholesale by the model, discarding the valid columns named
alongside it.

Returns None when the draft is fully valid — including the partial-column
case, which is a SUCCESS (rows with a note), not a refusal.
"""

from __future__ import annotations

from typing import Optional

from spire.nl_parser.result import Refusal, RefusalFlavor
from spire.nl_parser.vocabulary import KGMenu
from spire.planner.planner import Intent


# Entities whose edge has a REVERSE-only tool — the tool can FILTER parents
# by a child value, but cannot LIST a parent's children. Site and
# Classification are the two such entities on this pod; Site has its own
# gate below (for its specific user-facing message, keyed in capability.py),
# so this set is really just Classification today. Kept as a set so a
# future reverse-tool entity is one line, not a new branch.
# F-043: Site and Classification were reverse-only — the pod could list
# a supplier's sites/classifications, but SPIRE's only tools for them ran
# the OTHER direction (find suppliers BY a site/classification), so a
# Site or Classification include had no forward fetch and refused. The
# reverse tools now accept their filter as optional, serving both
# directions on the same edge, so both entities are includable. Kept as
# an empty frozenset so the check below stays a no-op if a future
# reverse-only entity is added.
_NON_INCLUDABLE_ENTITIES: frozenset[str] = frozenset()


def validate_intent(intent: Intent, menu: KGMenu) -> Optional[Refusal]:
    """Validate a draft Intent against the KG menu.

    Args:
        intent: The shape-valid Intent produced from the LLM's draft.
        menu: The KG menu (allowed entities, targets, filter types, edges).

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

    # ── Step 3b: reject includes that cannot be satisfied (BUG-2) ────
    #
    # Two failure modes; both crash the pipeline today, in different layers.
    # See the module docstring for the full analysis. In brief:
    #
    #   (a) no forward edge from the target (or its root) — the planner's
    #       Block 3 raises a raw KeyError, which run_graph prints as a
    #       hard failure. This is the S1 crash.
    #   (b) edge exists but its tool is a reverse filter — planning
    #       succeeds, the executor crashes on a missing required arg.
    #       This is the Classification case.
    #
    # The gate handles both. It preserves the existing Site check first,
    # because capability.py keys the Site refusal's user-facing Solution
    # and Example on offending_entity='SupplierSiteListing'. Then it runs
    # a general loop that mirrors the planner's Block 3 chain/sibling
    # logic, so a valid chain is not falsely refused.
    #
    # A note on scope. This is a VALIDATOR gate, not a planner fix. The
    # planner still raises the raw KeyError if it is reached with a bad
    # include — that is BUG-3, fixed separately. This gate makes the
    # crash unreachable for well-formed intents; BUG-3 makes it safe
    # even if a future intent slips past this check.
    #
    # Site is checked unconditionally — it is a hardcoded string test and
    # does not consult edge data, so the "menu has no edges" precondition
    # below does not apply to it.
    # The general include gate requires the menu to declare edges. When it
    # does not (hand-built minimal fixtures, or any caller that constructs
    # KGMenu by hand without edges), the gate cannot validate and declines
    # to fire — the same "absent data => no-op" contract KGMenu already
    # follows for field_synonyms / entity_synonyms / entity_columns. The
    # production menu from load_kg_menu() always populates edge_pairs, so
    # production is unaffected; when the skip does happen, BUG-3's
    # RefusalError is the layered backstop for anything the gate would have
    # caught.
    if intent.include and menu.edge_pairs:
        # Simulate the planner's Block 2: an edge-traversal filter walks
        # the intent to a child entity, and Block 3 chains the FIRST
        # include from there, not from the intent's target. Use the last
        # edge-traversal filter's target as the "previous entity".
        #
        # Without this simulation, an intent like
        # Supplier + has_open_PO + include=['Buyer'] would be falsely
        # refused — the include chains from PurchaseOrder (after Block 2),
        # not from Supplier.
        _previous = entity
        _root = entity
        for f in intent.filters:
            tgt = menu.edge_traversal_target(f.get("type"))
            if tgt is not None:
                _previous = tgt

        for include_entity in intent.include:
            # (b) reverse-tool entities. Refused with a clear message;
            # capability.py falls through to the general
            # UNSUPPORTED_OPERATION wording for unknown offending_entity
            # values, which is fine for now.
            if include_entity in _NON_INCLUDABLE_ENTITIES:
                return Refusal(
                    flavor=RefusalFlavor.UNSUPPORTED_OPERATION,
                    detail=(
                        f"{include_entity} is not available as an include "
                        f"on {entity}."
                    ),
                    offending_entity=include_entity,
                )

            # Address on a Supplier target is the expand-path special case
            # (the addresses child is fetched inline via include_addresses,
            # not via an edge traversal). It does not become the new
            # "previous entity" — the planner does not chain further
            # includes from it. Mirror that here.
            if entity == "Supplier" and include_entity == "Address":
                continue

            # (a) forward-edge check. Try the chain hop first (previous
            # entity -> include), then the sibling hop (root -> include),
            # exactly as the planner's Block 3 does. Either succeeds: the
            # include has a declared edge and is safe to plan. On success,
            # update _previous to the include entity — the next item in
            # the chain will try its own edge from there.
            if menu.has_edge(_previous, include_entity) or menu.has_edge(
                _root, include_entity
            ):
                _previous = include_entity
                continue

            return Refusal(
                flavor=RefusalFlavor.UNSUPPORTED_OPERATION,
                detail=(
                    f"{include_entity} is not a valid include on {entity}."
                ),
                offending_entity=include_entity,
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
        # Fields an active include already provides are neither projected
        # base-row columns nor unresolved — the include's own column renders
        # them. Collect that set from the active includes and skip those
        # fields in the split, so no false "not available" note is emitted
        # for a field the answer actually shows (see
        # _FIELDS_SATISFIED_BY_INCLUDE).
        # Two sources feed "this field is satisfied by an active
        # include":
        #
        #   (a) the curated _FIELDS_SATISFIED_BY_INCLUDE map, for
        #       reader-facing synonyms that do NOT correspond to a
        #       column on the include's KG catalog (Address's "city",
        #       "state", "addresses" — see the map's docstring).
        #   (b) the KG field catalog of every entity in intent.include.
        #       This is what lets a CHILD field (e.g. PurchaseOrderLine's
        #       "Description") resolve against its own entity instead of
        #       being classified against the target's catalog and wrongly
        #       reported unavailable. F-017.
        #
        # The TARGET's own catalog is checked FIRST for each column, so
        # a field present on both the target and an include (OrderNumber
        # is a column on PurchaseOrder AND on PurchaseOrderLine) stays
        # in `fields` for the target's projection, rather than being
        # short-circuited by the include branch.
        satisfied_by_include: set[str] = set()
        for inc in intent.include:
            satisfied_by_include |= _FIELDS_SATISFIED_BY_INCLUDE.get(inc, set())
            for inc_col in menu.entity_columns.get(inc, []):
                satisfied_by_include.add(inc_col.lower())
        known: list[str] = []
        unresolved: list[str] = []
        for col in intent.fields:
            if menu.is_known_field(entity, col):
                known.append(col)
            elif col.lower() in satisfied_by_include:
                # Satisfied by the include; not an unresolved miss and
                # not a target-catalog column either.
                continue
            else:
                unresolved.append(col)
        intent.fields = known
        intent.unresolved_fields = unresolved

    return None


# Fields an active include already provides, so a request for them is
# SATISFIED by the include rather than unresolved. The Address include
# attaches the supplier's formatted address (a single Address column); the
# location a user asks for — "address", "country", "city", "state" — is
# carried there, so naming one of these is answered by that column, not a
# missing one. Without this, Step 4 split such a field into
# unresolved_fields (it is not a base-row column) and the display printed a
# "column isn't available" note ABOVE the very Address column that answers
# it — a self-contradicting answer (the AI-10 address-mapping quirk shows
# up here; this removes the contradiction at the field-split, it does not
# change how the parser maps the phrasing to the include).
_FIELDS_SATISFIED_BY_INCLUDE: dict[str, set[str]] = {
    "Address": {"address", "addresses", "country", "city", "state"},
    # F-041 residual: DFF columns live on the included DFF child, not
    # on ReceivablesInvoice. Without this entry the field-split moves
    # them to unresolved_fields and the display prints a false
    # "column not available" note over data the pipeline already
    # fetched. Same pattern as the Address entry above.
    "ReceivablesInvoiceTransactionDFF": {
        "__flex_context",
        "__flex_context_displayvalue",
        "customertrxid",
    },
}