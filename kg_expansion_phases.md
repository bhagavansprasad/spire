# Spire KG Expansion — Phase Tracker

Tracks the phased work to widen Spire's KG scope.

**Principles (all phases):**
- KG logic handles classes of prompts, not specific ones. No per-prompt branches.
- KG does not hardcode columns. Field selection is prompt-driven, backed by `kg_entity_field`.
- Filters are data-driven from the KG, not hardcoded constants.
- Build one piece, verify against the live pod, then proceed.

**Workflow per phase:** branch off master → implement → test on live pod →
open PR → merge → mark phase done here. Separate branch, PR, commit per phase.

---

## Baseline (before expansion)

Works today, verified:
- Target entity: **Supplier** only.
- Filters: `country`, `has_open_PO`, `has_no_recent_invoices`.
- Aggregation: supplier spend ranking (top-N, optional date window).

Refused cleanly (correct, out of scope):
- Invoice / Address / PurchaseOrder / Buyer as a **target** entity.
- Count and aggregations beyond spend ranking.
- Field projection, status filters, creation-date filters, name-fragment filters.

KG size at baseline: 5 entities, 27 fields, 4 edges, 3 patterns,
42 vocabulary rows, 3 pattern bindings, 3 entity tools, 3 edge tools.

Known internal issue: filter types come from hardcoded Python constants
(`_ENTITY_LEVEL_FILTER_TYPES`, `_EDGE_TRAVERSAL_FILTERS`, plus two mapping
dicts), not the KG. Phases 1–2 fix this.

---

## Phase 1 — Add `kg_entity_filter` table (seed only)

**Status:** DONE (merged to master)

**Goal:** Add a KG table that holds filter definitions. Seed it to match
today's hardcoded values exactly. Nothing reads it yet.

**Supported before:** filters live in four hardcoded Python dicts.

**New after:** same behavior. The KG now *also* carries the filter
definitions, ready for Phase 2 to consume. No user-facing change.

**KG change:** new table `kg_entity_filter`. Proposed columns:
entity_name, filter_type, mechanism (entity_level / edge_traversal),
tool_arg_name, vocab_kind, target_entity, kg_filter_type.
Seeded rows reproduce: country, has_open_PO, has_no_recent_invoices.

**Sample prompts (regression — must behave identically):**
- `Suppliers in US` → 25 US suppliers, as today.
- `US suppliers with open purchase orders` → open-PO suppliers, as today.

**Test:** KG rebuilds cleanly. `print_kg.py` shows the new table.
Full suite unchanged (nothing reads the table yet).

**Done when:** table seeded, KG rebuilds, suite green, merged.

---

## Phase 2 — Rewire planner to read `kg_entity_filter`

**Status:** DONE (merged to master)

**Goal:** Planner reads filter definitions from the KG table. Delete the
hardcoded dicts. Behavior must be identical.

**Supported before:** planner routes filters via hardcoded constants.

**New after:** planner routes filters via the KG. Filters are fully
data-driven. Adding a filter later = a KG row, not code.

**Code change:** rewire the six functions that consume the constants
(`_pick_entity_filter`, `_filters_needing_edge_traversal`,
`_build_fetcher_args`, `_filter_target_entity`, value-vocab resolution,
validation). Remove the four dicts.

**Sample prompts (regression — must behave identically):**
- `Suppliers in US` → same result as Phase 1.
- `US suppliers with no invoices in 6 months` → same as today.
- `US suppliers with open POs, including the buyer` → same as today.

**Test:** full suite passes byte-identically. No behavior drift.

**Done when:** dicts deleted, suite green, merged.

---

## Phase 3a — Visible supplier filters: status, name

**Status:** DONE (merged to master)

**Goal:** Add status and name-fragment filters, and merge the two
supplier tools into one per-entity fetcher so filters combine.

**Supported before:** status/name prompts refused. Country had its own
tool and could not combine with other filters.

**New after:** status and name work. All supplier filters live on one
`search_suppliers` and stack (e.g. "active US suppliers named Lee").
Country routes through the merged fetcher; its dedicated tool is gone.

**Status definition:** settled Status-based. active=ACTIVE,
inactive=INACTIVE, matched client-side. Not InactiveDate-based.

**Sample prompts and expected results:**
- `Get list of active suppliers` → suppliers with ACTIVE status.
- `List suppliers which are inactive` → the INACTIVE suppliers.
- `Suppliers named Lee` → suppliers whose name contains "Lee".
- `active US suppliers` → active suppliers with a US address (combo).

---

## Phase 3b — Supplier creation-date filter

**Status:** DONE (merged to master)

**Goal:** Add the creation-date range filter for suppliers.

**Supported before:** creation-date prompts refuse.

**New after:** creation-date range works.

**Note:** the merged tool already accepts `created_from`/`created_to`.
Remaining work is parser-side: teach the parser the value shape for a
date range, then route it. Lower bound is server-side q=; upper bound
client-side (composite q= fails on this pod).

**Sample prompts and expected results:**
- `Suppliers created between Jan and Mar 2025` → suppliers in that range.
- `Suppliers created after 2022` → suppliers with CreationDate >= 2022.

**Test:** range returns correct subset vs a direct curl.

**Done when:** anchor prompts pass, suite green, merged.

---

## Phase 4 — Invoice as a queryable target

**Status:** DONE (merged to master)

**Goal:** Root a query on Invoice, filtered by supplier. Default fields.

**Supported before:** Invoice refused as a target.

**New after:** Invoice queries work when a supplier is given.
No supplier → clean refusal.

**Scope:**
- Supplier by number (direct) or name (substring). Tool `search_invoices`
  already supports both.
- Supplier is required. No supplier → refuse.
- Uses the generalized filter mechanism from Phase 2.
- Synthesizer gets an Invoice response shape.

**Sample prompts and expected results:**
- `Show me invoices for supplier 1252` → invoices for Lee Supplies.
- `Invoices for Lee Supplies` → same, via name lookup.
- `Get Sun Pvt Ltd supplier with invoice number and invoice amount`
  → invoices for Sun Pvt Ltd; default fields (projection is Phase 7).

**Test:** all three return invoice records vs live pod. Suite green.

**Done when:** anchor prompts pass, suite green, merged.

---

## Phase 5 — Invoice filters (amount, date)

**Status:** DONE (merged to master)

**Goal:** Add amount and date filters for invoices.

**Supported before:** invoices filterable by supplier only.

**New after:** invoices filterable by amount and date too.

**Sample prompts and expected results:**
- `Invoices over 10000 for supplier 1252` → invoices above that amount.
- `Invoices for supplier 1252 in 2023` → invoices in that date window.

**Test:** filtered subsets match a direct curl.

**Done when:** anchor prompts pass, suite green, merged.

---

## Phase 6 — Address as a queryable target

**Status:** DONE (merged to master)

**Goal:** Root a query on Address. Fetched via `suppliers?expand=addresses`.

**Supported before:** Address refused as a target.

**New after:** Address queries work.

**Sample prompts and expected results:**
- `Suppliers with their addresses` → suppliers plus their address rows.
- `Lee Supplies address` → address(es) for Lee Supplies.

**Test:** address records returned vs live pod. Suite green.

**Done when:** anchor prompts pass, suite green, merged.

---

## Phase 7 — Column projection (generalized, cross-entity)

**Status:** NOT STARTED

**Goal:** When a prompt names fields, return only those fields. Works
across all entities.

**Supported before:** output always returns default fields.

**New after:** output returns exactly the requested fields, any entity.

**Scope:**
- Prompt-driven field selection, backed by `kg_entity_field`.
- No hardcoded column lists.
- Deferred prompts from earlier phases now honor field selection.

**Sample prompts and expected results:**
- `Get SupplierName and SupplierNumber for India` → only those two fields.
- `Get Sun Pvt Ltd supplier with invoice number and invoice amount`
  → only invoice number and amount.

**Test:** output contains only requested fields, across entities. Suite green.

**Done when:** anchor prompts pass, suite green, merged.

---

## Change log

- Phase 1 done: added `kg_entity_filter` table, seeded to match the
  prior hardcoded values. `print_kg.py` updated for the 9th table.
- Phase 2 done: planner and `load_kg_menu` read filters from
  `kg_entity_filter`; four hardcoded dicts removed. Behavior unchanged.
- Phase 3a done: status and name filters added; the two supplier tools
  merged into one combinable `search_suppliers`; country row removed;
  resolve_vocab made case-insensitive. Phase 3 split into 3a (status +
  name, done) and 3b (created_date, open).
- Phase 3b done: supplier creation-date range filter. Parser emits a
  from/to object; planner expands it to created_from/created_to.
- Phase 4 done: Invoice as a queryable target, filtered by supplier
  (number or name). Planner refuses an Invoice query with no supplier.
- Phase 5 done: invoice amount and date range filters. Added
  `tool_arg_name_hi` so range filters carry both bound args in the KG;
  planner range expansion generalized (from/to and min/max). 9 filter
  rows.
- Phase 6 done: Address as a queryable target via a new
  `search_addresses` tool (flattens supplier.addresses[]). Filtered by
  supplier or country; planner refuses if neither given. Added
  AddressRecord/AddressResponse with id validation. 3 entity_tool, 11
  filter rows.