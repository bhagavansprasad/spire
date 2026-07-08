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

**Status:** DONE (merged to master)

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

## Phase 8 — Business relationship filter

**Status:** DONE (merged to master)

**Goal:** Filter suppliers by BusinessRelationship. Two values exist on
the pod, confirmed via curl across 500 rows: `Spend Authorized` and
`Prospective`.

**Supported before:** business-relationship prompts refuse.

**New after:** works, matched client-side, equals. Mirrors the status
filter exactly.

**Status definition:** canonical values are the literal pod strings —
`Spend Authorized`, `Prospective` — not underscored codes. The API
returns those strings; client-side equals matches them directly.

**KG changes:**
- A `supplier_business_relationship` vocab kind. Friendly terms map to
  the literal pod strings, covering both the bare-adjective form
  ("prospective", "spend authorized") and the explicit form.
- A `business_relationship` filter row on Supplier: entity_level,
  client_side, filter_field `BusinessRelationship`, op equals.

**Tool changes:** a `business_relationship` arg on `search_suppliers`,
applied client-side. Added to the server registration.

**Parser:** instruction line mapping both phrasing families to the filter.

**Sample prompts and expected results:**
- `Suppliers with business relationship Spend Authorized` → suppliers
  whose BusinessRelationship is `Spend Authorized`.
- `Prospective suppliers` → suppliers whose BusinessRelationship is
  `Prospective`.
- `Spend authorized suppliers` → same as the first.

**Test:** filtered subset matches a direct curl. Suite green.

**Done when:** anchor prompts pass, suite green, merged.

---

## Phase 9 — Nested addresses on a supplier query

**Status:** OPEN

**Goal:** Root on Supplier, return each supplier with its addresses
nested underneath.

**Supported before:** Address works as its own target ("addresses for
supplier X"), but not as an include on a supplier-rooted query. This is
the partly-addressed item from the SME feedback.

**New after:** `Suppliers with their addresses` returns a supplier list,
each with its addresses nested.

**KG / parser:** parser adds `Address` to the intent's include list for
this phrasing. Planner requests expand=addresses on the supplier fetch
(the expand path is already used).

**Synthesizer:** SupplierRecord gains an optional nested addresses field;
the supplier prompt block describes it. Validate address ids as in
Phase 6.

**Sample prompts and expected results:**
- `Suppliers with their addresses` → supplier list, addresses nested.
- `List suppliers with supplier address` → same.

**Test:** nested shape returned vs live pod. Suite green.

**Done when:** anchor prompts pass, suite green, merged.

---

## Phase 10 — Supplier count

**Status:** OPEN

**Goal:** Answer "count of suppliers", and by extension simple counts of
a filtered entity set.

**Supported before:** the only aggregation is supplier spend ranking. A
plain count is a different shape.

**New after:** count works, reusing the existing fetchers'
`total_available`.

**KG / planner:** the parser recognises "count of X" / "how many X" and
sets a count marker on the intent. The planner routes to the entity's
default fetcher, flagged count-only. The synthesizer emits a count
summary rather than a record list. Keep count as its own intent shape —
do not let it silently combine with ranking.

**Data discovery:** none. Uses existing fetchers and their
total_available.

**Sample prompts and expected results:**
- `Count of suppliers` → total supplier count.
- `How many active suppliers` → count of ACTIVE suppliers.
- `How many US suppliers` → count of suppliers with a US address.

**Test:** count matches a direct curl total. Suite green.

**Done when:** anchor prompts pass, suite green, merged.

---

## Phase 11 — Suppliers by invoice amount over N

**Status:** OPEN

**Goal:** Root on Supplier, keep suppliers that have at least one invoice
over an amount — a value comparison across the edge, not just presence.

**Supported before:** edge filters (`has_open_PO`,
`has_no_recent_invoices`) test presence/absence only.

**New after:** an edge-traversal filter that walks Supplier → Invoice and
applies a value test.

**KG changes:**
- An edge-traversal filter on Supplier, `has_invoice_over_amount`, target
  Invoice, carrying the threshold value.
- Reuse the HAS_INVOICE edge (SupplierNumber join).

**Planner / executor:** for each supplier, fetch invoices (the executor
already iterates edges); keep the supplier if any invoice's InvoiceAmount
meets the threshold. Presence pattern plus a value test.

**Design caution:** keep the first version to amount-over only.
Generalise (any child field, any op) only if a second case demands it.

**Sample prompts and expected results:**
- `Suppliers with invoice amount greater than 10000` → suppliers with at
  least one invoice over 10000.

**Test:** subset matches a curl-derived expectation. Suite green.

**Done when:** anchor prompt passes, suite green, merged.

---

## Phase 12 — Supplier sites by business unit (new endpoint)

**Status:** OPEN — needs discovery first

**Goal:** Query supplier sites, filter by procurement business unit.

**Supported before:** sites are a new endpoint
(`/suppliers/{SupplierId}/child/sites`), not modelled.

**New after:** sites queryable, filtered by ProcurementBU.

**Discovery (must precede KG design):**
- Curl the sites child for a known supplier; capture real field names
  (ProcurementBU, SiteName, site-level fields).
- Classify ProcurementBU filtering server-side vs client-side, one clause
  at a time.
- Confirm whether sites reach only via the child path or also via expand.
- Confirm the join key back to Supplier.

**Likely shape (to confirm with data):**
- A Site entity as a child of Supplier via an edge.
- A `search_sites` tool flattening sites to records with parent supplier
  identity — mirrors the address tool.
- KG: Site entity + fields, an edge Supplier → Site, a tool row, a
  business-unit filter.

**Sample prompts and expected results (draft):**
- `Sites for supplier 1252` → that supplier's sites.
- `Suppliers with a site in business unit X` → sites filtered by
  ProcurementBU.

**Test:** site records returned vs live pod. Suite green.

**Done when:** discovery captured, anchor prompts pass, suite green,
merged.

---

## Phase 13 — Business classifications (new endpoint)

**Status:** OPEN — needs discovery first

**Goal:** Expose supplier business classifications.

**Supported before:** new endpoint
(`/suppliers/{SupplierId}/child/businessClassifications`), not modelled.

**New after:** classifications queryable.

**Discovery (must precede KG design):**
- Curl the businessClassifications child for a known supplier; capture
  field names (classification code, category, certificate details).
- Confirm filterability and whether expand works.
- Confirm the join key back to Supplier.

**Likely shape (to confirm with data):**
- Classification as a child of Supplier via an edge, flattened by a
  `search_classifications` tool, mirroring addresses/sites.
- KG: entity + fields, edge, tool row, any useful filter.

**Sample prompts and expected results (draft):**
- `Business classifications for supplier 1252` → that supplier's
  classifications.

**Test:** classification records returned vs live pod. Suite green.

**Done when:** discovery captured, anchor prompts pass, suite green,
merged.

---

## SME coverage

The nine-phase expansion (phases 1–7 above) resolved most of the SME test
comments. This table maps each test to its status and how it was, or will
be, addressed.

| Test | Prompt | Status | How addressed |
|---|---|---|---|
| 1 | Suppliers created in a time window | Fixed | Created-date range filter (Phase 3b) |
| 2 | Supplier sites by business unit | Planned | New sites endpoint (Phase 12) |
| 3 | Suppliers with their addresses | Partly | Address works standalone; nested shape (Phase 9) |
| 4 | Suppliers we spent most with in 2022 | Worked | Spend ranking (pre-existing) |
| 5 | Suppliers with their addresses | Partly | Same as Test 3 (Phase 9) |
| 6 | Suppliers with open purchase orders | Worked | has_open_PO filter (pre-existing) |
| 8 | Get list of active suppliers | Fixed | Status filter (Phase 3a) |
| 9 | Only SupplierName and SupplierNumber | Fixed | Column projection (Phase 7) |
| 10 | Sun Pvt Ltd invoices, number + amount | Fixed | Invoice target (Phase 4) + projection (Phase 7); empty only because that supplier has no invoices on the pod |
| 11 | Business relationship filter | Fixed | Business relationship filter (Phase 8) |
| 12 | Suppliers by invoice amount over N | Planned | Cross-entity value filter (Phase 11) |
| 13 | Top 10 suppliers by spend | Worked | Spend ranking (pre-existing) |
| 14 | Count of suppliers | Planned | Supplier count (Phase 10) |
| 16 | Inactive suppliers | Fixed | Status filter (Phase 3a) |
| 17 | Business classifications | Planned | New classifications endpoint (Phase 13) |

Suggested order for the remaining open phases: 9 → 10 → 11 → 12 → 13
(Phase 8 done). Quick wins
first; the two new-endpoint phases last, since they need a live-data
session before their KG rows can be authored.

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
- Phase 7 done: cross-entity column projection. LLM fills Intent.fields
  with exact column names (from a per-entity list the menu reads from
  kg_entity_field). Graph trims raw output to those columns; synthesized
  prose and validation use full records. Roadmap complete.
- Phases 8–13 planned: business relationship filter (8), nested
  addresses (9), supplier count (10), suppliers by invoice amount (11),
  supplier sites (12, new endpoint), business classifications (13, new
  endpoint). Merged in from the former SME follow-up plan; the SME
  coverage table is now the "SME coverage" section above. Ordered
  easiest-first; the two new-endpoint phases need curl discovery before
  their KG rows can be authored.
- Phase 8 done: supplier business_relationship filter. Two pod values
  (`Spend Authorized`, `Prospective`), canonical = the literal display
  strings. Client-side equals, mirroring status (server-side q= works on
  this field but client-side keeps it combinable). Added the tool arg on
  search_suppliers + server registration, a supplier_business_relationship
  vocab kind (2 rows) and a business_relationship filter row
  (kg_entity_filter 11->12, kg_vocabulary 44->46), and a parser line for
  both the bare-adjective and explicit phrasings. Verified end-to-end on
  the pod; prompt added to run_prompt_set. print_kg and the kg-metadata
  test updated for the new counts.
