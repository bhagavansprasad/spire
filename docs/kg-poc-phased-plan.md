# Knowledge Graph POC — Phased Execution Plan

> **For:** Oracle Fusion SME & POC team 
> **Companion docs:** `kg-poc-scoping.md` (background, principles, Q1/Q2) and `spire_fusion_endpoints_reference.md` (endpoint signatures, quirks, join keys). 
> **Purpose:** A small, validated, kill-point-driven plan to prove or disprove that a metadata-only KG in Oracle 26ai produces more reliable plans than the existing LLM-driven Spire agent for known multi-hop Fusion REST queries.

---

## Guiding principle (from scoping doc)

> **The KG must describe what the agent can *do*, not what the data model *contains*.**

Every phase below is in service of testing this principle — nothing more.

---

## Plan shape

**Analogy:** We're not laying the whole subway in one go. We start by **drawing one line between two stations, running one train, and seeing if passengers reach their destination.** Only then do we add the next line.

Each phase answers **one question**. If the answer is "no" or "not good enough," we stop and rethink — not pile on more phases.

---

## Phase summary

| Phase | Question it answers | Kill-point check |
|---|---|---|
| **0. Foundation** | Do we have the raw materials? | Endpoint reference already exists; SME confirms test set |
| **1. Minimal map** | Can we model Fusion REST as a graph? | Graph loads in 26ai; PGQ traverses it; hand-verified |
| **2. Plan generation** | Can PGQ emit an executable REST plan? | Plan matches the documented call sequence for the reference prompt |
| **3. End-to-end execution** | Does the plan actually answer the question against live Fusion? | Reference prompt returns correct answer end-to-end |
| **4. Comparison vs existing Spire agent** | Is KG-driven planning *better* than the existing LLM-driven agent? | Wins on correctness OR stability; no loss on failure quality |
| **5. Stretch — patterns & cost** | Can we encode reusable patterns and prefer cheaper paths? | Only if Phase 4 shows promise |

---

## Locked-in decisions

| Decision | Choice |
|---|---|
| **Scope** | AP slice + HCM buyer lookup — exactly the 5 endpoints in `spire_fusion_endpoints_reference.md` |
| **Entities in scope** | `Supplier`, `Address`, `Invoice`, `PurchaseOrder`, `Buyer` |
| **Anchor question** | *"Show me suppliers in US with no invoices in 6 months but with open purchase orders, including the buyer assigned to each."* |
| **LLM baseline** | The existing Spire agent — it already exhibits the failure mode (1–59 calls variably). No new baseline to build. |
| **Fusion access** | Existing paid dev pod (`fa-esll-dev37-saasfademo1`), real data, no synthetic setup needed |
| **Correctness ground truth** | SME cross-verifies against live Fusion via the documented curl commands |
| **Test question sourcing** | Reference prompt + variants the team drafts; SME critiques and adds |
| **Phase 4 pass criteria** | KG wins on correctness OR stability; no loss on failure quality |

---

# Phase 0 — Foundation

**Question this phase answers:** Do we have the raw materials and agreement to start?

## Status: Mostly done

The endpoint reference document already covers:
- Endpoint inventory (5 endpoints, AP + HCM buyer)
- Full signatures (curl, params, response shapes)
- Join key matrix (SupplierNumber/SupplierId asymmetry)
- Quirks catalog (composite `q=` failures, country expansion, OWSM 401s)
- Documented end-to-end call sequence for the reference prompt

## What's left

- **Round out the test set** — draft 5–7 more questions of varying difficulty, share with SME for critique.
- **Confirm credentials access** — POC team has working `FUSION_USERNAME` / `FUSION_PASSWORD` for the dev pod.

## Proposed test set for SME review

| # | Question | Hops | Purpose |
|---|---|---|---|
| 1 | Find supplier "Lee Supplies" | 1 | Baseline — single endpoint, no joins |
| 2 | Show all invoices for supplier 1252 since 2024-01-01 | 1 + date filter | Tests client-side date filtering |
| 3 | Show open POs for supplier ID 300000047572113 | 1 + status filter | Tests client-side status filtering (composite `q=` workaround) |
| 4 | List suppliers in the US | 1 + nested-resource filter | Tests `expand=addresses` pattern |
| 5 | **Show suppliers in US with no invoices in 6 months but with open POs, including the buyer** | 4 hops, cross-pillar | **Anchor question** — the documented failure case |
| 6 | Which US suppliers have open POs but no invoices at all? | 3 hops, "absence" reasoning | Variant of anchor — simpler absence case |
| 7 | List all buyers across US suppliers with open POs (deduplicated) | 3 hops + aggregation | Tests result composition |
| 8 | Show approval status for invoices over $50k for supplier X | Unknown — likely unanswerable with current 5 endpoints | Deliberate stretch — does KG fail informatively? |

## What we need from the SME

- Confirm the endpoint reference doc is current and complete for the AP slice.
- Mark any test question that is unrealistic or oddly worded.
- Add 2–3 real questions they wish a tool like this could answer.

## Kill-point check

✅ SME signs off on the endpoint reference doc and at least 6 of 8 test questions (with edits).

---

# Phase 1 — Minimal map

**Question this phase answers:** Can we model the 5-endpoint AP slice of Fusion REST as a property graph in 26ai?

## What we build

Based on the endpoint reference doc's KG sketch:

**Vertex tables** (one row per entity type):
- `Supplier` — endpoint `/suppliers`, canonical ID `SupplierId`, also has `SupplierNumber`
- `Address` — child resource of `Supplier`, accessed via `expand=addresses`
- `Invoice` — endpoint `/invoices`, canonical ID `InvoiceId`
- `PurchaseOrder` — endpoint `/purchaseOrders`, canonical ID `POHeaderId`
- `Buyer` — endpoint `/publicWorkers` (HCM!), canonical ID `PersonId`

**Edge tables** (one row per declared relationship):
- `Supplier --HAS_ADDRESS--> Address` — via `expand=addresses` on `/suppliers`
- `Supplier --HAS_INVOICE--> Invoice` — join key from-side: `SupplierNumber`, to-side: `q=SupplierNumber=...`
- `Supplier --HAS_PURCHASE_ORDER--> PurchaseOrder` — join key from-side: `SupplierId`, to-side: `q=SupplierId=...` ← **the asymmetry**
- `PurchaseOrder --ASSIGNED_TO--> Buyer` — join key from-side: `BuyerId`, to-side: `q=PersonId=...` ← **cross-pillar**

**Vocabulary table:**
- `"vendor"` → `Supplier`
- `"bill"` → `Invoice`
- `"open"` → `StatusCode=OPEN`
- `"US"` / `"United States"` → `Country=US`
- (etc.)

Hand-write all of this. No automation in this phase.

## Kill-point check

✅ Graph loads cleanly in 26ai. 
✅ A PGQ query like "find all paths from `Supplier` to `Buyer`" returns the expected path: `Supplier → PurchaseOrder → Buyer`. 
✅ Hand-verify: the path's join keys match the documented asymmetry (SupplierId → BuyerId → PersonId).

---

# Phase 2 — Plan generation

**Question this phase answers:** Can PGQ emit an ordered, executable REST plan from a structured question?

## What we build

A PGQ query (or small set) that takes structured input — e.g.:

```json
{
  "entity": "Supplier",
  "filters": [
    {"type": "country", "value": "US"},
    {"type": "no_invoices_within", "months": 6},
    {"type": "has_open_po", "value": true}
  ],
  "include": ["Buyer"]
}
```

…and returns an ordered list of REST calls with ID handoff rules and client-side filters.

## Validation approach

Compare PGQ's output for the **anchor question** against the call sequence already documented in the endpoint reference:

```
Step 1. GET /suppliers?expand=addresses → filter Country='US'
Step 2. For each US supplier: GET /invoices?q=SupplierNumber=... → filter InvoiceDate cutoff
Step 3. For suppliers with zero recent invoices: GET /purchaseOrders?q=SupplierId=... → filter StatusCode='OPEN'
Step 4. For each unique BuyerId: GET /publicWorkers?q=PersonId=...
```

Do the same for 2 simpler questions from the test set.

## Kill-point check

✅ For 3/3 questions, generated plan matches the documented sequence (same endpoints, order, join keys). 
✅ If 2/3, debug and rerun. 
✅ If <2/3, **stop and rethink the KG model** before proceeding.

---

# Phase 3 — End-to-end execution

**Question this phase answers:** Does the generated plan actually return correct data when executed against the live dev pod?

## What we build

A **thin plan executor** — not the full agent, just enough to:
- Take PGQ's plan
- Make HTTP calls to the dev pod with Basic Auth
- Thread IDs from one call's output to the next call's input
- Apply client-side filters (date arithmetic in Python, not LLM — per the endpoint reference's note)
- Return the final result as JSON

Date arithmetic specifically must be in Python (`date.today() - timedelta(days=180)`), never asked of the LLM — the endpoint reference flags this as a recurring failure mode.

## Validation approach

Run the same 3 questions from Phase 2 through the executor against the live dev pod. SME verifies answers using the documented curl commands.

## Kill-point check

✅ 3/3 questions return correct answers. 
✅ Anchor question executes in roughly the documented number of calls (~35–40), not 1, not 59. 
✅ If <3/3, debug whether it's the KG model, executor, or endpoint annotations.

---

# Phase 4 — Comparison vs existing Spire agent (the actual hypothesis test)

**Question this phase answers:** Is the KG-driven planner measurably better than the existing LLM-driven Spire agent?

This is the phase the POC exists for. Phases 0–3 just get us to the starting line.

## What we use

- **Baseline:** existing Spire agent, unchanged. Documented failure mode: 1–59 calls per run on the anchor prompt.
- **Treatment:** KG-driven planner + thin executor from Phase 3.

No new baseline to build — the existing agent IS the LLM-orchestration comparison.

## How we test

Run **all 8 questions** through **both systems**, **5 times each**.

## Metrics

| Metric | Weight | How we score |
|---|---|---|
| **Correctness** | ✅ Mandatory | SME cross-verifies against live Fusion via curl. % correct across runs. |
| **Stability** | ✅ Mandatory | Across 5 runs of the same question, count distinct plans/call-counts produced. KG target = 1. Existing agent baseline = 1–59 (documented). |
| **Failure quality** | ✅ Important | For unanswerable question (#8): does the system fail *before* calling Fusion, or *after* wasted calls? |
| **Latency** | ⚪ Bonus | Record but don't gate. |
| **Explainability** | ⚪ Bonus | SME's subjective read on which plan is easier to audit. |

## Pass criteria

**KG wins on correctness OR stability AND doesn't lose on failure quality.**

- KG better on both correctness and stability → **strong win**, proceed to Phase 5.
- KG equal on correctness, better on stability → **win** (determinism was the hypothesis).
- KG worse on correctness, even if stable → **fail**. Stability of wrong answers isn't useful.
- Both roughly equal → **inconclusive**. Use failure quality and explainability to break tie.

## Kill-point check

If Phase 4 doesn't produce a clear win, **Phase 5 doesn't run.** Write up findings honestly and decide whether to rethink or shelve.

---

# Phase 5 — Stretch: patterns & cost

**Only run this if Phase 4 produces a clear win.**

**Question this phase answers:** Can we encode reusable query patterns and prefer cheaper traversal paths?

## What we build

- **Named query patterns** — e.g., the `no_Y_in_N_months` template from the endpoint reference doc, parameterized so other questions ("suppliers with no POs in 3 months") reuse it.
- **Cost annotations** on edges — pagination cost, expansion cost, expected fan-out.
- A PGQ query that **prefers cheaper paths** when multiple paths exist.

## Validation approach

- Pattern reuse: feed a new question that fits an existing pattern; verify PGQ matches it instead of re-deriving.
- Cost-aware: introduce a scenario with two valid paths; verify PGQ picks the cheaper one.

## Kill-point check

✅ Pattern matching works on at least one question. 
✅ Cost-based path selection works on at least one scenario.

---

# Timing — when each input is needed

| Need | When | Notes |
|---|---|---|
| Endpoint URL list | ❌ Already done | Phase 0 — covered by endpoint reference doc |
| Endpoint signatures (params, response shapes) | ❌ Already done | Phase 1 — covered by endpoint reference doc |
| Fusion dev pod credentials | Start of **Phase 3** | Phases 0–2 are offline |
| SME availability for verification | **Phases 0, 3, 4** | Bounded reviews, not open-ended work |
| Spire agent source tree | When Phase 4 starts | Needed to set up the baseline runs consistently |

---

# What we need from the Oracle Fusion SME at each phase

| Phase | SME involvement |
|---|---|
| **0. Foundation** | Confirm endpoint reference doc is current; critique test questions; add real ones |
| **1. Minimal map** | Sanity-check entity model and edge declarations against Fusion reality |
| **2. Plan generation** | Confirm the documented call sequence for the anchor prompt is still correct |
| **3. End-to-end execution** | Verify results against live Fusion via curl |
| **4. Comparison vs Spire** | Cross-verify correctness on all 8 questions × 5 reruns × 2 systems; subjective explainability call |
| **5. Stretch** | Identify cost characteristics; review patterns for realism |

---

# Summary

- **Six phases, each with a single yes/no kill-point.**
- **Phase 4 is the actual hypothesis test.** Phases 0–3 are setup.
- **Phase 5 is optional** — only if Phase 4 wins.
- **No new LLM baseline to build** — the existing Spire agent IS the baseline.
- **Ground truth is live Fusion** on the existing dev pod — no synthetic data.
- **The reference prompt is the documented failure case** — we have a clear target to beat.
