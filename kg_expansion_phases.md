# Spire KG Expansion — Phase Tracker

Tracks the phased work to widen Spire's KG scope, starting with Invoice
as a queryable target entity.

**Principles (carried across all phases):**
- KG logic handles classes of prompts, not specific ones. No per-prompt branches.
- KG does not hardcode columns. Field selection is prompt-driven, backed by `kg_entity_field`.
- Build one piece, verify against the live pod, then proceed.
- Each phase: branch → implement → test → PR → merge.

**Workflow per phase:** branch off master → implement → test on live pod →
open PR → merge → mark phase done here.

---

## Baseline (before expansion)

What works today, verified:
- Target entity: **Supplier** only.
- Filters: `country`, `has_open_PO`, `has_no_recent_invoices`.
- Aggregation: supplier spend ranking (top-N, optional date window).

Refused cleanly (correct, out of scope):
- Invoice / Address / PurchaseOrder / Buyer as a **target** entity.
- Count and other aggregations beyond spend ranking.
- Field projection, status filters, date-created filters, name-fragment filters.

KG size at baseline: 5 entities, 27 fields, 4 edges, 3 patterns,
42 vocabulary rows, 3 pattern bindings, 2 entity tools, 3 edge tools.

---

## Phase 1 — Invoice as a queryable target

**Status:** NOT STARTED

**Goal:** Let the user root a query on Invoice, filtered by supplier.
Return default invoice fields.

**Scope:**
- Parser admits `Invoice` as a valid `target_entity`.
- Supplier identified by **number or name**.
  - Number → direct (matches `HAS_INVOICE` join key `SupplierNumber`).
  - Name → resolve name → `SupplierNumber` first, then fetch invoices.
- Planner routes Invoice-target to `search_invoices` (tool already exists).
- Synthesizer gets an Invoice response shape (sibling model per existing pattern).
- Default fields only. No amount/date filters yet (Phase 2).
- No column projection yet (Phase 4). Prompts naming specific fields
  return the default set.

**Anchor prompts:**
1. `Show me invoices for supplier 1252` — by number.
2. `Invoices for Lee Supplies` — by name; exercises name→number lookup.
3. `Get Sun Pvt Ltd supplier with invoice number and invoice amount`
   — by name; returns default fields in this phase (projection deferred).

**KG changes:**
- No new endpoint (invoices endpoint already modeled).
- Confirm Invoice entity is targetable, not just a child.
- Bind Invoice-target to `search_invoices` in `kg_entity_tool`.

**Test:** all three anchor prompts return invoice records against the
live pod. Full existing suite still passes.

**Done when:** anchor prompts pass, suite green, merged to master.

---

## Phase 2 — Invoice filters (amount, date)

**Status:** NOT STARTED

**Goal:** Add general filter types for invoices: amount and date.

**Scope:**
- New filter types (generalized, not prompt-specific):
  - `amount` comparison (e.g. `> 10000`).
  - `invoice_date` window.
- Still Invoice target. Builds on Phase 1.
- Filters expressed as KG-backed filter types, routed deterministically.

**Anchor prompts (draft — confirm at phase start):**
1. `Invoices over $10,000`
2. `Invoices for supplier 1252 in 2023`

**Test:** amount and date filters return correct subsets vs a direct
curl against the invoices endpoint.

**Done when:** anchor prompts pass, suite green, merged.

---

## Phase 3 — Address as a queryable target

**Status:** NOT STARTED

**Goal:** Let the user root a query on Address. Proves the "add a target
entity" path repeats cleanly.

**Scope:**
- Parser admits `Address` as a valid `target_entity`.
- Fetched via `suppliers?expand=addresses` (no standalone endpoint).
- Synthesizer gets an Address response shape.
- Default fields only (projection is Phase 4).

**Anchor prompts (draft — confirm at phase start):**
1. `Suppliers with their addresses`
2. `Lee Supplies address`

**Test:** address records returned against live pod. Suite green.

**Done when:** anchor prompts pass, suite green, merged.

---

## Phase 4 — Column projection (generalized, cross-entity)

**Status:** NOT STARTED

**Goal:** When a prompt names specific fields, return exactly those
fields. Works across all entities, not one.

**Scope:**
- Prompt-driven field selection, backed by `kg_entity_field`.
- Generic: applies to Supplier, Invoice, Address — every entity.
- No hardcoded column lists.
- Deferred prompts from earlier phases (e.g. Phase 1 anchor #3,
  Phase 3 "specific columns") now return only the named fields.

**Anchor prompts (draft — confirm at phase start):**
1. `Get SupplierName and SupplierNumber for India`
2. `Get Sun Pvt Ltd supplier with invoice number and invoice amount`

**Test:** output contains only requested fields, across multiple
entities. Suite green.

**Done when:** anchor prompts pass, suite green, merged.

---

## Change log

- _(empty — update as phases complete)_
