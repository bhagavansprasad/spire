# Spire — SME Feedback Follow-up Plan

Tracks the SME test comments (SpireV1.docx) against what Spire now does,
and lays out detailed phases for the items still open.

Convention matches `kg_expansion_phases.md`: one branch per phase, PR,
merge; the KG is rebuilt from scratch, never incrementally inserted;
build one piece, verify against the live pod, then proceed.

---

## Part 1 — What we addressed, and how

The nine-phase KG expansion (see `kg_expansion_phases.md`) resolved most
of the SME comments. Mapping each test:

| Test | Prompt | Status | How addressed |
|---|---|---|---|
| 1 | Suppliers created in a time window | Fixed | Created-date range filter (Phase 3b) |
| 4 | Which suppliers did we spend most with in 2022 | Worked | Spend ranking (pre-existing) |
| 6 | Suppliers with open purchase orders | Worked | has_open_PO filter (pre-existing) |
| 8 | Get list of active suppliers | Fixed | Status filter (Phase 3a) |
| 9 | Only SupplierName and SupplierNumber | Fixed | Column projection (Phase 7) |
| 10 | Sun Pvt Ltd invoices, number + amount | Fixed | Invoice target (Phase 4) + projection (Phase 7). Empty only because that supplier has no invoices on the pod |
| 13 | Top 10 suppliers by spend in 2023 | Worked | Spend ranking (pre-existing) |
| 16 | Inactive suppliers | Fixed | Status filter (Phase 3a) |

Supporting capability now in place: Invoice and Address are queryable
targets; suppliers carry five combinable filters (country, status,
name, created-date, plus the two edge filters); invoices filter by
supplier, amount, and date; the filter mechanism and column list are
fully KG-driven.

---

## Part 2 — Partly addressed

**Test 3 / Test 5 — "Suppliers with their addresses"**

We built Address as its own queryable target. "Addresses for supplier
1252" and "US supplier addresses" work. But the SME's exact phrasing
roots on Supplier and wants each supplier's addresses nested underneath.
That include-shape (addresses as a child of a supplier list) is not
wired. Covered by Phase F below.

---

## Part 3 — Detailed plan for the open items

Six phases. Ordered easiest-first, so quick wins land before the
new-endpoint and aggregation work.

### Phase A — Business relationship filter (Test 11)

**Goal:** Filter suppliers by BusinessRelationship (e.g. "Spend
Authorized", "Prospective").

**Why open:** We deliberately dropped this during Phase 3 scoping.

**Approach:** It mirrors the status filter exactly. BusinessRelationship
is a field on the supplier record (seen in supplier curls). Single-value
client-side match, like status.

**KG changes:**
- Add a `supplier_business_relationship` vocab kind, mapping friendly
  terms to canonical codes (e.g. "spend authorized" -> "SPEND_AUTHORIZED",
  "prospective" -> "PROSPECTIVE"). Confirm exact codes via curl first.
- Add a `business_relationship` filter row on Supplier: entity_level,
  client_side, filter_field `BusinessRelationship`, op equals.

**Tool changes:** Add a `business_relationship` arg to `search_suppliers`,
applied client-side. Add it to the server registration.

**Parser:** Instruction line mapping the phrasing to the filter.

**Data discovery:** One curl to confirm the canonical values of
BusinessRelationship on the pod (SPEND_AUTHORIZED, PROSPECTIVE, and any
others).

**Sample prompts and expected results:**
- `Suppliers with business relationship Spend Authorized` -> suppliers
  whose BusinessRelationship is SPEND_AUTHORIZED.
- `Prospective suppliers` -> suppliers whose BusinessRelationship is
  PROSPECTIVE.

**Effort:** Small. Same shape as status.

---

### Phase B — Supplier count / aggregation (Test 14)

**Goal:** Answer "count of suppliers", and by extension simple counts of
a filtered entity set.

**Why open:** The only aggregation Spire does today is supplier spend
ranking. A plain count is a different aggregation shape.

**Approach:** Two options.
1. A dedicated `count` aggregation op with its own tool, matching the
   one-op-per-tool rule the spend ranking follows.
2. Derive count from the existing fetch — run the normal filtered fetch,
   then report the total_available already returned in ToolResult.

Option 2 is lighter and reuses everything. The fetchers already return
`total_available`. A count query becomes: fetch with the given filters,
report the count, list nothing (or a short sample).

**KG / planner:** The parser recognises "count of X" / "how many X" and
sets an aggregate/count marker on the intent. The planner routes to the
entity's default fetcher but flags the step as count-only. The
synthesizer emits a count summary rather than a record list.

**Boundedness note:** Keep count as its own intent shape, not a filter.
Do not let it silently combine with ranking.

**Data discovery:** None. Uses existing fetchers and their
total_available.

**Sample prompts and expected results:**
- `Count of suppliers` -> total supplier count.
- `How many active suppliers` -> count of ACTIVE suppliers.
- `How many US suppliers` -> count of suppliers with a US address.

**Effort:** Medium. Parser + a count path in planner/synthesizer.

---

### Phase C — Cross-entity filter: suppliers by invoice amount (Test 12)

**Goal:** "Suppliers with invoice amount greater than 10000" — root on
Supplier, filter by a property of their invoices.

**Why open:** All current filters constrain the target entity or walk one
edge with a simple presence/absence test. This asks for suppliers whose
invoices satisfy an amount condition — a value comparison across the
edge, not just presence.

**Approach:** Extend the edge-traversal mechanism. Today `has_open_PO`
and `has_no_recent_invoices` walk Supplier -> child and test presence.
This adds a variant that walks Supplier -> Invoice and keeps suppliers
that have at least one invoice matching an amount condition.

**KG changes:**
- Add an edge-traversal filter on Supplier, e.g.
  `has_invoice_over_amount` (or a more general `invoice_amount_over`),
  target Invoice, carrying the threshold value.
- Reuse the HAS_INVOICE edge (SupplierNumber join).

**Planner / executor:** For each supplier, fetch invoices (the executor
already iterates edges); keep the supplier if any invoice's InvoiceAmount
meets the threshold. This is the presence pattern plus a value test.

**Design caution:** This is the general "filter parent by child property"
case. Keep the first version to amount-over only. Generalise (any child
field, any op) only if a second case demands it — matches the
don't-over-generalise principle.

**Data discovery:** None new; invoice amount behaviour already verified.

**Sample prompts and expected results:**
- `Suppliers with invoice amount greater than 10000` -> suppliers with at
  least one invoice over 10000.

**Effort:** Medium-large. New edge-filter variant with a value test.

---

### Phase D — Supplier sites endpoint (Test 2)

**Goal:** "List suppliers with supplier site based on business unit" —
query supplier sites, filter by procurement business unit.

**Why open:** Sites are a new endpoint
(`/suppliers/{SupplierId}/child/sites`) not yet modelled.

**Approach:** Follow the agreed endpoint-onboarding process. Share the
endpoint and target prompts; Claude suggests curls; run them and share
JSON; build KG rows together; output SQL for the rebuild.

**New-endpoint discovery (must precede KG design):**
- Curl the sites child for a known supplier; capture the real field names
  (ProcurementBU, SiteName, and the site-level fields).
- Confirm how ProcurementBU filtering behaves (server q= vs client-side),
  and whether sites are reachable only via the child path or also via
  expand.

**Likely shape (to confirm with data):**
- New `Site` entity, or Site as a child of Supplier via an edge.
- A `search_sites` tool (or a supplier fetch with expand), flattening
  sites to records with parent supplier identity — mirrors the address
  tool.
- KG: Site entity + fields, an edge Supplier -> Site, a tool row, and a
  business-unit filter.

**Sample prompts and expected results (draft):**
- `Sites for supplier 1252` -> that supplier's sites.
- `Suppliers with a site in business unit X` -> sites filtered by
  ProcurementBU.

**Effort:** Large. New endpoint; needs data discovery first.

---

### Phase E — Business classifications endpoint (Test 17)

**Goal:** "Get all classifications" — expose supplier business
classifications.

**Why open:** New endpoint
(`/suppliers/{SupplierId}/child/businessClassifications`), not modelled.

**Approach:** Same onboarding process as Phase D.

**New-endpoint discovery (must precede KG design):**
- Curl the businessClassifications child for a known supplier; capture
  field names (classification code, category, certificate details, etc.).
- Confirm filterability and whether expand works.

**Likely shape (to confirm with data):**
- Classification as a child of Supplier via an edge, flattened by a
  `search_classifications` tool, mirroring addresses/sites.
- KG: entity + fields, edge, tool row, and any useful filter.

**Sample prompts and expected results (draft):**
- `Business classifications for supplier 1252` -> that supplier's
  classifications.

**Effort:** Large. New endpoint; needs data discovery first.

---

### Phase F — Nested addresses on a supplier query (Test 3 / Test 5)

**Goal:** "Suppliers with their addresses" — root on Supplier, return
each supplier with its addresses nested underneath.

**Why open:** Address works as its own target, but not as an include on a
supplier-rooted query.

**Approach:** Add Address as an include (like Buyer on a PO). When the
supplier fetch runs, expand=addresses is already available; attach each
supplier's addresses to its record. The synthesizer's SupplierRecord
gains an optional addresses list.

**KG / parser:** Parser adds `Address` to the intent's `include` list for
this phrasing. Planner requests expand=addresses on the supplier fetch.

**Synthesizer:** SupplierRecord gains an optional nested addresses field;
the supplier prompt block describes it. Validate address ids as in
Phase 6.

**Data discovery:** None; the expand path is already used.

**Sample prompts and expected results:**
- `Suppliers with their addresses` -> supplier list, each with its
  addresses nested.
- `List suppliers with supplier address` -> same.

**Effort:** Medium. Include-shape plus a nested synthesizer field.

---

## Suggested order

1. Phase A — business relationship (small, mirrors status).
2. Phase F — nested addresses (medium, closes Test 3/5 cleanly).
3. Phase B — count (medium).
4. Phase C — suppliers by invoice amount (medium-large).
5. Phase D — sites endpoint (large, needs discovery).
6. Phase E — classifications endpoint (large, needs discovery).

Quick wins first; the two new endpoints last, since they need a live-data
session before their KG rows can be authored.

---

## Change log

- _(empty — update as phases complete)_
