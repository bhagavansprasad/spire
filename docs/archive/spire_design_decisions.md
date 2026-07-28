# Spire — Design Decisions

The consolidated record of *how* Spire's architecture was decided — the
options weighed, the decisions locked, and the reasoning captured at the
time each was made. This file merges eight design documents that previously
lived separately.

**These are frozen records, not living docs.** Each section is preserved as
it was written, at its point in time. Their value is exactly this: they
capture the reasoning behind a decision as it stood when made, including the
honest uncertainties and revisions. Do not rewrite them to match the current
system — for what Spire *is now*, see `spire_architecture.md`; for what's
being *built next*, see `spire_expansion_plan.md`. Update these sections only
to correct an outright error in the historical record, not to track drift.

Some sections describe an earlier, smaller system (e.g. the v1 KG schema's
"5 entities" — now 11). That is intentional and correct for a frozen record.
Where a section has been superseded, the current state is in
`spire_architecture.md`; this file keeps the decision as it was made.

---

## Contents

1. **Design Alternatives & Comparison** — the four candidate designs and why
   Design 3 (graph-guided orchestration) was chosen. The foundational
   decision everything else builds on.
2. **Knowledge Graph Schema v1** — what the KG models and why; the
   metadata-not-instance-data decision. (v1 = 5 entities; now 11.)
3. **Agent-KG Integration Design** — how the KG connects to the agent /
   pipeline.
4. **Feature 1 — Natural-Language Parser** — the prompt → Intent design,
   including the structured-refusal decision.
5. **Phase 2 — Planner** — the Intent → Plan design; deterministic tool
   selection by KG lookup.
6. **Feature 7 — Aggregation** — the aggregation-op design; the
   "grouping/measure fixed by identity" rule.
7. **KG Evaluation Framework** — how the KG-driven approach is measured.
8. **Design 3 v1.1 → Production Roadmap** — the path from the validated v1
   toward production.

---


---

<!-- ============================================================ -->
<!-- SECTION 1 — Design Alternatives & Comparison (frozen record, from spire_design_alternatives.md) -->
<!-- ============================================================ -->

# Spire — Design Alternatives & Comparison

**Purpose:** This document captures the architectural designs considered for Spire's agent layer. Each design is described in its own terms, with an honest assessment of its strengths and limitations, and a visual diagram showing the flow.

**Companion document:** `../spire_poc_master_plan.md` covers the POC plan that tests selected designs against a representative prompt.

**A note on scope: this POC is single-tenant.** Multi-tenancy (serving multiple isolated customer organizations from one deployed system) is a separate, post-POC concern and is not part of any design discussed here. All architectures assume a single customer organization with a single Fusion pod connection.

---

## What Is Documented vs. What Is Implemented

This document describes **four** architectural alternatives. The POC builds **two** of them as full implementations.

| # | Design | Documented | Implemented in POC | Role |
|---|---|---|---|---|
| 1 | LLM + Reference Query Library + Validation + Tool | ✅ Yes | ❌ No | SME's proposal — documented for transparency; natural evolution converges with Design 2 |
| 2 | Direct Tool Orchestration (Agent Loop) | ✅ Yes | ✅ Yes (Track A) | POC baseline — measures what tool descriptions alone can accomplish |
| 3 | Graph-Guided Orchestration | ✅ Yes | ❌ Not as a separate track | KG component is built and used inside Design 4; not measured independently |
| 4 | Dynamic Orchestration (KG + Embeddings) | ✅ Yes | ✅ Yes (Track B) | POC full architecture — combines KG + embedding-based dynamic tool retrieval |

**Why this structure:**
- **Design 1** is documented to validate that the SME's idea was considered. Its limitations (no agent loop, no error recovery, no multi-step reasoning) are well-understood, and its natural evolution converges with Design 2. If a future SME conversation requests it, the master plan can be reframed to include it as an additional baseline.
- **Design 3** is documented as a meaningful conceptual step between Designs 2 and 4. The Knowledge Graph it introduces is built as a *component* of Design 4 rather than as a separate POC track — building it twice would duplicate work without adding signal.

**Trade-off worth flagging:** Because Design 4 includes both the KG (Design 3's contribution) and embeddings, the POC's comparison answers *"is the full architecture worth it?"* rather than *"is the KG alone worth it?"* See section 9 for details.

---

## Table of Contents

1. [Comparison Reference Prompt](#1-comparison-reference-prompt)
2. [Design 1 — LLM + Reference Query Library + Validation + Tool](#2-design-1--llm--reference-query-library--validation--tool) (documented only)
3. [Design 2 — Direct Tool Orchestration (Agent Loop)](#3-design-2--direct-tool-orchestration-agent-loop) (POC: Track A)
4. [Design 3 — Graph-Guided Orchestration](#4-design-3--graph-guided-orchestration) (documented only; KG built inside Design 4)
5. [Design 4 — Dynamic Orchestration](#5-design-4--dynamic-orchestration) (POC: Track B)
6. [Side-by-Side Comparison](#6-side-by-side-comparison)
7. [Natural Evolution Path](#7-natural-evolution-path)
8. [Recommendation Framework](#8-recommendation-framework)
9. [POC Build Decisions](#9-poc-build-decisions)

---

## 1. Comparison Reference Prompt

All designs are evaluated against the same prompt:

> *Show me suppliers in US with no invoices in 6 months but with open purchase orders, including the buyer assigned to each.*

This prompt deliberately stresses:

- Multiple entities (Supplier, Invoice, PurchaseOrder, Buyer, Address, Country)
- Negation logic (no invoices in 6 months)
- Status semantics (open POs)
- Multi-hop relationships (Supplier → PO → Buyer)
- Organizational scoping (US, resolved via address)

---

## 2. Design 1 — LLM + Reference Query Library + Validation + Tool

> **POC status: documented only — not implemented as a separate POC track.**

**Origin:** The SME's design — a more thoughtful version of "LLM generates the query, tool executes it."

![Design 1: LLM + Reference Query Library + Validation + Tool](./spire_design_1_reference_library_validation.svg)

### Key characteristics

- First LLM pass generates a query (typically SQL)
- Second LLM pass validates against reference queries from a local library
- Validation is **syntactic** — no execution
- Tool's role is narrow: just execution
- Reference library is the knowledge source
- Two LLM calls in sequence, but still a single overall pass (no agent loop)

### Pros and Cons

| Pros | Cons |
|---|---|
| Conceptually simple to explain | Reference retrieval is the hidden problem |
| Reference query library is a real asset | Syntactic validation misses semantic errors |
| Validation catches obvious hallucinations | SQL-shaped blind spot — assumes SQL is the answer |
| Modest infrastructure required | No multi-step reasoning |
| Familiar text-to-SQL pattern | No error recovery path |
| Library is human-readable for SMEs | Reference library is implicitly a KG, just less queryable |

### When sufficient vs. when it breaks down

| Sufficient when | Breaks down when |
|---|---|
| Question patterns are bounded (~30–50 cover 90% of usage) | Reference library outgrows context window |
| SQL-based access is acceptable | Multi-step orchestration is required |
| Raw errors to users are tolerable | Error recovery and graceful degradation matter |

### A note on its honest position

This is not a naive design. It is a real architecture used in production text-to-SQL systems. The SME's instinct reflects sound engineering caution — *start simple, don't over-build*. The question is whether Spire's product goals exceed what this design can sustain. Its natural evolution under production pressures converges with Designs 2, 3, and 4.

---

## 3. Design 2 — Direct Tool Orchestration (Agent Loop)

> **POC status: implemented as Track A — the POC baseline.**

**Origin:** The POC's baseline architecture — the version against which more sophisticated designs are measured.

![Design 2: Direct Tool Orchestration (Agent Loop)](./spire_design_2_direct_tool_orchestration.svg)

### Key characteristics

- MCP tools wrap Fusion REST endpoints; tools execute against the live pod
- **Critical addition: an agent loop.** The LLM is invoked iteratively, not once.
- Each iteration: LLM sees prompt, tools, history of calls → decides next call or finalize
- Multi-step reasoning is native
- Tool descriptions are the only knowledge surface — no KG, no embeddings

### Pros and Cons

| Pros | Cons |
|---|---|
| Multi-step reasoning works natively | No formal knowledge representation |
| Error recovery built in via the loop | Tool selection accuracy degrades with catalog size |
| Tool call history accumulates signal across iterations | No place for reusable query patterns |
| Standard, well-supported architecture (Cursor, Devin pattern) | Compounding improvement is limited |
| Naturally auditable — every iteration is traced | Higher infrastructure cost than Design 1 |
| Endpoint-aware tool selection | Loop iterations cost tokens |
| Honest baseline with no extra magic | |

### When sufficient vs. when it breaks down

| Sufficient when | Breaks down when |
|---|---|
| Tool catalog is moderate (5–30 tools) | Tool catalog needs to scale toward "all of Fusion" |
| Multi-step reasoning needed but patterns are recurring | Common patterns are wasted re-derivation effort |
| Team prefers operational simplicity over compounding intelligence | Production trust requires verifiable, explainable reasoning |

---

## 4. Design 3 — Graph-Guided Orchestration

> **POC status: documented only — the KG it introduces is built as a *component* of Design 4 (Track B), not as a separate POC track.**

**Origin:** An architectural alternative that tests whether structured knowledge meaningfully outperforms tool descriptions alone.

![Design 3: Graph-Guided Orchestration](./spire_design_3_graph_guided_orchestration.svg)

### What's in the Knowledge Graph

Stored in Oracle 26ai as a SQL Property Graph plus supporting relational tables:

- **Entities** — canonical Fusion entities (Supplier, Invoice, PurchaseOrder, Buyer, Address, Country)
- **Relationships** — typed edges with join semantics and endpoint traversal hints
- **Query patterns** — reusable logic ("no Y in N months", "open PO status filter")
- **Lookups** — business-term-to-Oracle-code mappings ("US" → 'US', "open PO" → composite status condition)

### Key characteristics

- Same Fusion execution layer as Designs 1 and 2
- Same agent loop as Design 2
- **Critical addition: a Knowledge Graph the agent consults via dedicated tools**
- KG holds structured knowledge that doesn't fit cleanly in tool docstrings

### Pros and Cons

| Pros | Cons |
|---|---|
| Solves the precise traversal problem | Significant upfront design and curation investment |
| Patterns are reusable across entities and queries | Cold-start problem — empty KG provides no value |
| Negation and complex logic become tractable | New operational surface (mitigated by Oracle 26ai) |
| Explainable — agent can cite KG sources | Agent integration is non-trivial to tune |
| Compounding improvement is natural | Risk of over-engineering the model |
| Cross-agent knowledge sharing (BIP, OIC, FBDI) | Stale or incorrect KG actively misleads the agent |
| Reduces LLM cognitive load and token cost | |

### When sufficient vs. when overkill

| Sufficient when | Overkill when |
|---|---|
| Product targets real-world Fusion work | Use case is genuinely narrow |
| Common patterns recur across queries | Team can't sustain ongoing KG curation |
| Explainability and trust are valued | Time-to-first-demo dominates other concerns |

---

## 5. Design 4 — Dynamic Orchestration

> **POC status: implemented as Track B — the POC full architecture. Combines Design 3's KG with embedding-based dynamic tool retrieval.**

**Origin:** The production-target architecture, addressing the SME's stated requirement for dynamic endpoint addition.

![Design 4: Dynamic Orchestration](./spire_design_4_dynamic_orchestration.svg)

### What this design adds

- **Knowledge Graph** (same as Design 3) — encodes entities, relationships, patterns, lookups in Oracle 26ai SQL Property Graph
- **Embedding-based tool retrieval** — full tool catalog embedded in Oracle 26ai's VECTOR data type; only the top-N most relevant tools enter the LLM's context per prompt
- **Endpoints can be added at runtime** — no code changes, no redeploys
- **Pattern matching upgraded to embeddings** — handles synonymy and paraphrase
- **Past successful queries can be embedded** for few-shot retrieval

### Pros and Cons

| Pros | Cons |
|---|---|
| Scales to thousands of endpoints | Most complex of all four designs |
| Dynamic endpoint addition without redeploy | Retrieval quality is a new failure mode |
| Better pattern matching via embeddings | Cold start is more severe |
| Compounding intelligence at the retrieval layer | Embedding model choice matters significantly |
| Solves precise traversal via the KG | Hardest to demo — retrieval happens silently |
| Same operational footprint as a KG-only design (Oracle 26ai handles both) | |
| Production-realistic architecture | |

### When sufficient vs. when overkill

| Sufficient when | Overkill when |
|---|---|
| Product must scale to "all of Fusion" | POC stage with bounded tool catalog only |
| Endpoints must be added without engineering involvement | Tool catalog is small and stable |
| Production-grade operations are feasible | Time-to-first-demo dominates |

---

## 6. Side-by-Side Comparison

| Capability | Design 1: Ref Library *(documented only)* | Design 2: Direct Tools *(Track A)* | Design 3: Graph-Guided *(documented only)* | Design 4: Dynamic *(Track B)* |
|---|---|---|---|---|
| Tools (execution) | ✅ Yes (narrow role) | ✅ Yes | ✅ Yes | ✅ Yes |
| Agent loop (multi-step) | ❌ No | ✅ Yes | ✅ Yes | ✅ Yes |
| Error recovery | ❌ No | ✅ Built in | ✅ Built in | ✅ Built in |
| Reference query library | ✅ Static file | ⚠️ Could be added | ⚠️ Could be added | ⚠️ Could be added |
| Validation step | ✅ Syntactic only | ⚠️ Implicit via tool errors | ⚠️ Implicit + KG-informed | ⚠️ Implicit + KG-informed |
| Knowledge Graph | ❌ No | ❌ No | ✅ Yes | ✅ Yes |
| Embeddings for retrieval | ❌ No | ❌ No | ❌ No | ✅ Yes |
| Tool catalog growth | ❌ Library bloats validation | ⚠️ Degrades at ~30+ tools | ⚠️ Same as Design 2 | ✅ Scales to thousands |
| Dynamic endpoint addition | ❌ No (redeploy) | ❌ No (redeploy) | ❌ No (redeploy) | ✅ Yes |
| Multi-step reasoning | ❌ Single pass | ✅ Native | ✅ Native | ✅ Native |
| Complex logic (negation, joins) | ⚠️ Library-dependent | ⚠️ LLM-derived per call | ✅ Pattern library | ✅ Pattern library |
| Compounding improvement | ⚠️ Manual library curation | ❌ None | ✅ KG enrichment | ✅ KG + past-query embeddings |
| Auditability | ⚠️ Tool-level only | ✅ Full trace | ✅ Full trace + KG citations | ✅ Full trace + KG citations |
| Explainability | ⚠️ Reference queries | ⚠️ Tool descriptions | ✅ KG-cited reasoning | ✅ KG-cited reasoning |
| Time to first demo | ✅ Fast | ⚠️ Moderate | ⚠️ Slower | ❌ Slowest |
| Production-readiness ceiling | ⚠️ Moderate | ⚠️ Moderate-high | ✅ High | ✅ Highest |
| Operational complexity | ✅ Low | ⚠️ Moderate | ⚠️ Higher | ❌ Highest |
| **Measured baseline on POC prompt (5 runs × 7-step rubric)** | n/a (not implemented) | **1/7** (Phase A.5; see `phase_a5_baseline_report.md`) | n/a (not implemented as separate track) | pending (Track B not started) |

Legend: ✅ Strong, ⚠️ Conditional/partial, ❌ Absent or weak

---

## 7. Natural Evolution Path

Each design naturally evolves toward the next under real production pressures.

| Transition | Pressure | Response |
|---|---|---|
| Design 1 → Design 2 | Some queries need iteration the library can't cover | Let the LLM iterate; generate multiple queries; refine on failure |
| Design 2 → Design 3 | Tool descriptions can't carry structured relationship knowledge | Extract that knowledge into a queryable graph |
| Design 3 → Design 4 | Tool catalog must grow toward "all of Fusion" without bloating context | Embed tools; retrieve only relevant ones per prompt |

**Key insight:** No design is "wrong." Each is the right answer for a particular set of constraints. The question is which constraints apply to Spire.

---

## 8. Recommendation Framework

Rather than declaring one design the winner, here are the questions whose answers determine the right choice.

| Question | Answer → Design |
|---|---|
| How large will the tool catalog become? | < 15 tools → Designs 1–3 work; 15–50 → Designs 2 or 3; 50+ → Design 4 |
| Will questions require multi-step reasoning? | Mostly single-step → Design 1; multi-step common → Design 2+ |
| Is error recovery and graceful degradation important? | Errors can surface raw → Design 1; errors should retry → Design 2+ |
| How important is explainability and audit-grade trust? | Tool-level logging sufficient → any design; citation-able reasoning needed → Design 3 or 4 |
| Should the system improve over time without retraining? | No → Designs 1 or 2; yes → Design 3 or 4 |
| How much operational complexity can the team sustain? | Minimal → Design 1; moderate → Design 2 or 3; production-grade → Design 4 |

### A practical recommendation for Spire specifically

Based on the conversation so far:

- The SME's stated requirement (dynamic endpoint addition) implies **Design 4 is the production destination**
- The build path (incremental, smaller-better-than-larger) implies **starting with Design 2 as the baseline**, then layering Design 4 as the full architecture
- Design 3's value (the KG) is incorporated as a component of Design 4 — see section 9

---

## 9. POC Build Decisions

This section documents which designs are built and which are documented as alternatives only.

### What gets built (POC tracks)

| Design | POC track | Why |
|---|---|---|
| **Design 2 — Direct Tool Orchestration** | **Track A — Baseline** | Provides a clean, honest measurement of what tool descriptions alone can accomplish. Without this baseline, claims about Design 4's improvements are unfounded. |
| **Design 4 — Dynamic Orchestration** | **Track B — Full architecture** | The production target. Combines the KG (Design 3's contribution) with embedding-based dynamic retrieval. Directly addresses the SME's stated scaling requirement. |

### What does not get built as a separate POC track

| Design | Why excluded from build |
|---|---|
| **Design 1 — Reference Library + Validation** | The SME's design. Documented here for transparency and to validate that the design conversation considered it. Its limitations (no agent loop, no error recovery, no multi-step reasoning) are well-understood, and its natural evolution converges with Design 2. If a future SME conversation requests it, the master plan can be reframed to include Design 1 as an additional baseline. |
| **Design 3 — Graph-Guided Orchestration** | The KG itself is built — but as a *component* of Design 4 / Track B, not as a separate POC track. Building Design 3 as its own version would duplicate work, since Design 4 reuses the same KG. Treating the KG integration as one of Track B's phases keeps the build incremental without requiring a full Design 3 measurement cycle. |

### Why this structure

The original POC plan proposed three versions (baseline, KG, full). On reflection, that structure creates duplicate work: the KG built in version 2 is the same KG used in version 3. Building it twice as separate phases adds overhead without adding signal. By collapsing the KG work into Design 4's phases (Track B), the POC delivers the same architectural validation with less ceremony.

The trade-off worth flagging: the original three-version structure made the "is the KG worth it?" question into its own measurable phase. The collapsed structure folds that question into Track B's overall build — meaning if Track B underperforms relative to Track A, attribution between "the KG didn't help" and "the embeddings didn't help" requires careful trace analysis. This is acceptable for a POC; in production, the KG and embeddings should be evaluated independently.

### Measured results so far

| Track | Status | Baseline score | Reference |
|---|---|---|---|
| Track A — Direct Tool Orchestration | ✅ Complete | 1/7 (5 runs, single rubric) | `phase_a5_baseline_report.md` |
| Track B — Dynamic Orchestration | ⏳ Not started | pending | — |

Track A's 1/7 baseline reflects honest discipline: no prompt engineering, no retries with corrections, no tool-description tweaks during the test. The agent reliably finds US suppliers and reliably fails to compose further. Failure patterns documented in the A.5 report. This is the comparison target Track B's runs will be measured against.

---

## Document End

This is a living document. As the POC progresses, real measurements should be added to the comparison table (replacing qualitative ✅/⚠️/❌ with quantitative data). Updates should be tracked in version control alongside `../spire_poc_master_plan.md`.

**Last updated:** Document generation date (see git history)
---

<!-- ============================================================ -->
<!-- SECTION 2 — Knowledge Graph Schema v1 (frozen record, from kg_schema_v1.md) -->
<!-- ============================================================ -->

# Knowledge Graph Schema v1

**Phase:** Dynamic Orchestration 01 — KG Schema Design (rev. 2026-05-18 during phase 03)
**Status:** Design document — no implementation
**Scope:** Single document. Minimal viable KG for the POC. Companion to `spire_design_alternatives.md` and `../spire_poc_master_plan.md`.

This document defines *what* the KG models and *why*. It deliberately does not specify how the KG is stored (Dynamic Orchestration 03 picks the DDL shape), what tools the agent calls to query it (Dynamic Orchestration 04), or how embeddings interact with it (Dynamic Orchestration 06).

**Revision note (during phase 03):** The first version of this doc was unclear on one critical point — whether the KG stores instances of Fusion business data, or only structural metadata about how Fusion data is organized. This revision makes the answer explicit: **metadata only, never instance data.** Wording throughout has been adjusted to remove ambiguity. The entity set, edge set, pattern set, and lookup set are unchanged from the original draft, except that Country has been recategorized from "entity" to "vocabulary" (it never had an endpoint or instances anyway).

---

## 1. What the KG Is, and What It Is Not

### What the KG is

The Spire KG holds **structural knowledge about Fusion** — not Fusion data itself.

Concretely, the KG stores:

- **Entity declarations** — "there exists a concept called Supplier; it is materialized by the endpoint `/fscmRestApi/.../suppliers`; its canonical identifier is `SupplierId`."
- **Relationship declarations** — "Supplier relates to PurchaseOrder via the edge `HAS_PURCHASE_ORDER`; the join key is `SupplierId`; to traverse the edge, query `/purchaseOrders?q=SupplierId=X`."
- **Endpoint metadata** — supported filter fields, projection fields, known quirks (composite-`q=` reliability, child-resource requirements).
- **Query patterns** — reusable logical shapes like `no_Y_in_N_months`, with the steps and parameters needed to realize them.
- **Vocabulary tables** — business terms mapped to Fusion codes ("US" → `'US'`, "open" → `'OPEN'`, "vendor" → Supplier).

### What the KG is not

The KG does **not** store:

- Rows of supplier data, invoice data, PO data, or buyer data.
- Snapshots, samples, ETL'd copies, or cached extracts of Fusion records.
- Anything that could go stale relative to the live Fusion pod.

Every factual question the agent answers — "which suppliers are in the US?", "does supplier X have invoices in the last 6 months?", "who is the buyer for this PO?" — is answered by a **live call to Fusion**. The KG is the *map*; Fusion is the *territory*.

### Why this distinction matters

The KG is the navigation layer above Fusion, not a parallel data store. Two consequences:

- **The KG never needs to be refreshed.** It changes when the Fusion *schema* changes (new endpoint, renamed field, new relationship), not when Fusion *data* changes (new supplier added, invoice paid, PO closed).
- **Staleness is not a concern.** A KG that's a year old still tells the agent how to fetch today's data — because endpoints, join keys, and business vocabulary change far less than the underlying records do.

### What this means in scale

A v1 KG populated with everything in this document fits in **a few dozen rows total**: ~5 entities, ~4 edges, ~5 endpoint records, ~4 patterns, ~50 vocabulary entries. Not pod-data-sized. Schema-sized.

---

## 2. Purpose and Scope Boundaries

### Why a KG at all

Track A's baseline (1/7 on the reference prompt — see `../phase_a5_baseline_report.md`) showed two specific failure modes:

1. **Premature termination.** Agent calls one tool and stops, because nothing in its context tells it that "country → supplier → invoice → PO → buyer" is a multi-hop traversal it must complete.
2. **Parameter confusion across tools.** Agent called `search_purchase_orders(supplier_number='1252')` — `supplier_number` exists on `search_invoices` but not on `search_purchase_orders`. The relationship "supplier identifies a PO" is encoded three different ways across three tools, and docstrings alone weren't enough to keep them straight.

The KG addresses both. It encodes:

- **The traversal structure** — Supplier connects to PO via SupplierId; PO connects to Buyer via BuyerId; etc. The agent reads this from the KG, not from docstring archaeology.
- **The vocabulary** — what "open PO" means in Fusion codes; what "US" maps to in CountryCode; what "buyer" is in HCM terms.
- **Reusable reasoning patterns** — "no Y in N months" is a logic shape that recurs (no invoices, no payments, no orders); encoding it once means the agent looks it up rather than re-derives it.

### Scope boundaries — what v1 IS

- **Minimal entity set** sufficient to support the POC reference prompt:
  > *Show me suppliers in US with no invoices in 6 months but with open purchase orders, including the buyer assigned to each.*
- **Metadata-only KG** — see §1.
- **Static schema** — entities, relationships, patterns, and lookups defined in this document.
- **Single-tenant** — one customer, one pod, one persona.
- **Read-only** — the KG describes how to read from Fusion. It does not model writes.

### Scope boundaries — what v1 is NOT

Explicitly excluded so later phases don't drift:

- **Not a complete Fusion model.** Fusion has hundreds of entities; v1 has five entities. The point is to test the hypothesis, not to model the world.
- **No instance business data.** Restated from §1 because it bears repeating: the KG holds no rows of supplier, invoice, PO, or buyer data. (See §7 for the full non-goals list.)
- **No per-tenant overlays.** Customer-specific DFFs, custom value sets, and custom business rules are post-POC concerns. The KG schema *can* be extended to support tenant-scoped overlays later; v1 doesn't model them.
- **No write operations.**
- **No multi-pod federation.** One pod, one persona.
- **No historical / temporal modeling.** The KG describes current Fusion structure, not record histories or audit trails.

### Success criterion for v1

The KG is sufficient if, after Dynamic Orchestration 03–08 build it out and integrate it, an agent that consults the KG can score meaningfully higher than 1/7 on the reference prompt under the same rubric. If it scores 1/7 again, either the KG is too thin, the integration is wrong, or the hypothesis is wrong — and that's signal the POC needs to capture, not paper over.

---

## 3. Entity Model

Five entities. Each section is a *declaration* — a record the KG holds about that entity type, not a row of business data. Each declaration specifies: what the entity represents, the canonical identifier the KG uses to refer to it, what attributes the entity *has* (so the agent knows what to project and filter on), and which Fusion endpoint materializes the entity.

A note on attributes: the KG declares which fields *exist* on each entity, but does not store values. When the agent needs an actual supplier record, it calls Fusion and Fusion returns the live values. The KG's attribute list is closer to a small projection contract — "when you fetch a Supplier, expect at least these fields back" — than to a database schema.

### 3.1 Supplier

Represents a vendor or service provider in Fusion's supplier master.

| Aspect | Value |
|---|---|
| Canonical identifier | `SupplierId` (numeric) |
| Display identifier | `SupplierNumber` (string, e.g. `"1252"`) |
| Display name field | `Supplier` (string, e.g. `"Lee Supplies"`) |
| Status field | `Status` (string, e.g. `"ACTIVE"`) |
| Materialized by | `GET /fscmRestApi/resources/11.13.18.05/suppliers` |
| Country accessed via | `GET /fscmRestApi/.../suppliers?expand=addresses` (country lives on child Address; see §4.2) |

**Why `SupplierId` is canonical:** It's the join key across PO, invoice, and address. `SupplierNumber` is human-readable but is a string and can drift across pods; `SupplierId` is the system primary key.

### 3.2 Invoice

Represents an accounts-payable invoice tied to a supplier.

| Aspect | Value |
|---|---|
| Canonical identifier | `InvoiceId` (numeric) |
| Display identifier | `InvoiceNumber` (string) |
| Date field | `InvoiceDate` (ISO date string) |
| Amount fields | `InvoiceAmount` (numeric) + `InvoiceCurrency` (string) |
| Status fields | `PaidStatus`, `ApprovalStatus` |
| Supplier reference field | `SupplierNumber` (string) — note: not `SupplierId` on this endpoint |
| Materialized by | `GET /fscmRestApi/resources/11.13.18.05/invoices` |

**Note on the supplier reference asymmetry:** The invoices endpoint exposes `SupplierNumber` but not `SupplierId`. The PO endpoint exposes `SupplierId` but not `SupplierNumber`. This is the asymmetry that caused the Track A parameter confusion. §4.1 documents the implications.

### 3.3 PurchaseOrder

Represents a purchase order issued to a supplier and assigned to a buyer.

| Aspect | Value |
|---|---|
| Canonical identifier | `POHeaderId` (numeric) |
| Display identifier | `OrderNumber` (string) |
| Status field | `StatusCode` (string; values include `"OPEN"`, `"CLOSED"`, `"INCOMPLETE"`, `"CANCELED"`) |
| Status display field | `Status` (human-readable, e.g. `"Open"`) |
| Supplier reference field | `SupplierId` (numeric) |
| Buyer reference field | `BuyerId` (numeric) |
| Amount fields | `Ordered` (numeric) + `CurrencyCode` (string) |
| Materialized by | `GET /fscmRestApi/resources/11.13.18.05/purchaseOrders` |

### 3.4 Buyer

Represents the purchasing agent assigned to a PO. **Critical detail: buyers are HCM workers, not FSCM entities.** There is no `/fscmRestApi/.../buyers` endpoint on this pod (see `../phase_a5_baseline_report.md` and the A.4.3 log entry).

| Aspect | Value |
|---|---|
| Canonical identifier | `PersonId` (numeric) — same value as `BuyerId` on a PO |
| Display name field | `DisplayName` (string, e.g. `"Calvin Roth"`) |
| Email field | `WorkEmail` |
| Username field | `Username` |
| Person number | `PersonNumber` |
| Materialized by | `GET /hcmRestApi/resources/11.13.18.05/publicWorkers` |

**Cross-pillar implication:** Supplier → Invoice and Supplier → PO live in FSCM. PO → Buyer crosses into HCM. This is one of the most important things the KG encodes; without it, the agent has no reason to know it should switch pillars.

### 3.5 Address

Represents a supplier's address. Modeled as a separate entity (rather than collapsed into Supplier attributes) because a supplier can have multiple addresses in multiple countries.

| Aspect | Value |
|---|---|
| Canonical identifier | Not exposed as a top-level resource on this pod — addresses are child records of Supplier |
| Country fields | `CountryCode` (ISO-2, e.g. `"US"`), `Country` (full name, e.g. `"United States"`) |
| Other fields | (street, city, etc. — not modeled in v1) |
| Materialized by | `GET /fscmRestApi/.../suppliers?expand=addresses` (as `supplier.addresses[]`) |

**Why separate from Supplier:** Folding country into Supplier attributes would model "a supplier has *a* country," which is incorrect. A supplier can have addresses in many countries; the question "is this supplier *in* country X" means "does this supplier have *any* address in country X." That distinction matters for the reference prompt.

### Note on Country

Country was modeled as an "entity" in the first revision of this doc. On reflection, it's not an entity in the same sense as Supplier or Invoice — there's no Country endpoint we fetch instances from, no country records to traverse to. Country is a **vocabulary table**: a mapping from natural-language country terms to Fusion codes. It now lives in §5 (Vocabulary), not here.

---

## 4. Relationship Model

Four typed edges. Each specifies: semantic meaning, the join mechanic in Fusion, and the endpoint traversal hint (which Fusion query realizes the edge at runtime).

The KG's job in this section is to make explicit what Track A asked the LLM to infer from docstrings. If the agent needs to go from Supplier to Buyer, it should read the path from the KG — it should not have to derive `Supplier → PO → Buyer (via BuyerId → PersonId on publicWorkers)` from natural-language tool descriptions.

These edges are KG declarations, not instance edges. There is no row in the KG saying "supplier #1252 has invoice #X" — that's instance data and lives in Fusion. The KG declares the edge type once and how to traverse it; the agent applies the declaration to instances retrieved live from Fusion.

### 4.1 Supplier → Invoice (`HAS_INVOICE`)

**Semantic meaning:** A supplier has zero or more invoices.

**Join mechanic:** `Supplier.SupplierNumber == Invoice.SupplierNumber` (string equality).

**Important caveat:** The invoices endpoint exposes `SupplierNumber`, not `SupplierId`. So even though `SupplierId` is the canonical supplier identifier in the KG, traversal via this edge uses `SupplierNumber` at the Fusion query layer. The KG schema must make this explicit; otherwise the agent will repeat the Track A mistake of passing `SupplierId` where `SupplierNumber` is expected.

**Endpoint traversal hint:** Given a Supplier, the agent calls:
```
GET /invoices?q=SupplierNumber='{supplier.SupplierNumber}'
```
…optionally with additional filters (date, etc.). Composite `q=` clauses against this endpoint are unreliable on this pod (see `../phase_a5_baseline_report.md` and the A.4.1 log entry); additional filters are applied client-side after over-fetch.

**Cardinality:** One-to-many. A supplier can have many invoices; an invoice has exactly one supplier.

### 4.2 Supplier → Address (`HAS_ADDRESS`)

**Semantic meaning:** A supplier has one or more addresses. Each address belongs to a country.

**Join mechanic:** Address is a child resource of Supplier. There is no standalone Address endpoint to query independently; addresses come back inside a Supplier record when `expand=addresses` is set.

**Endpoint traversal hint:** Given a Supplier or a search for Suppliers, the agent calls:
```
GET /suppliers?expand=addresses
```
The address records appear inline as `supplier.addresses[]`. Country filtering is client-side (see §4.3 for why).

**Cardinality:** One-to-many. A supplier has at least one address (typically); each address belongs to exactly one supplier.

### 4.3 Address → Country attribute (no `LOCATED_IN` edge)

**Revision note:** The first version of this doc modeled `Address LOCATED_IN Country` as an edge. With Country recategorized as vocabulary (not an entity), it's not an edge between two entities anymore. It's now a *filter*: "filter addresses by their CountryCode/Country field, using the vocabulary table to map the user's term to the right code."

**How the agent uses it:**
- User says "in the US"
- Agent consults the Country vocabulary table (§5.1) to map `"US"` to `CountryCode='US'`
- Agent fetches suppliers with addresses expanded, then client-side filters addresses where `CountryCode='US'`

**A subtlety the KG still encodes:** Saying "supplier S is in country C" means "supplier S has *at least one* address in country C," not "all of supplier S's addresses are in country C." A supplier with offices in the US and UK is *in* the US *and* in the UK — both, simultaneously, for the purposes of any country-filter prompt.

### 4.4 Supplier → PurchaseOrder (`HAS_PURCHASE_ORDER`)

**Semantic meaning:** A supplier has zero or more purchase orders.

**Join mechanic:** `Supplier.SupplierId == PurchaseOrder.SupplierId` (numeric equality). Note: `SupplierId`, *not* `SupplierNumber`. This is the asymmetry with §4.1.

**Endpoint traversal hint:** Given a Supplier, the agent calls:
```
GET /purchaseOrders?q=SupplierId={supplier.SupplierId}
```
…optionally with status filter. Composite `q=` clauses are unreliable; status is applied client-side after over-fetch.

**Cardinality:** One-to-many. A supplier can have many POs; a PO has exactly one supplier.

### 4.5 PurchaseOrder → Buyer (`ASSIGNED_TO`)

**Semantic meaning:** A purchase order is assigned to exactly one buyer.

**Join mechanic:** `PurchaseOrder.BuyerId == Buyer.PersonId` (numeric equality). **This crosses pillars** — the PO is in FSCM, the buyer is in HCM.

**Endpoint traversal hint:** Given a PO, the agent calls:
```
GET /hcmRestApi/resources/11.13.18.05/publicWorkers?q=PersonId={po.BuyerId}
```
This is the single most important relationship the KG encodes that docstrings alone failed to convey in Track A — there is no `/fscmRestApi/.../buyers` endpoint on this pod, and the cross-pillar nature is not obvious from any tool name.

**Cardinality:** Many-to-one. Many POs can share a buyer; each PO has exactly one buyer.

### Relationship summary

| Edge | From | To | Join key | Endpoint hint |
|---|---|---|---|---|
| `HAS_INVOICE` | Supplier | Invoice | `SupplierNumber` (string) | `GET /invoices?q=SupplierNumber='X'` |
| `HAS_ADDRESS` | Supplier | Address | child via `expand=addresses` | `GET /suppliers?expand=addresses` |
| `HAS_PURCHASE_ORDER` | Supplier | PurchaseOrder | `SupplierId` (numeric) | `GET /purchaseOrders?q=SupplierId=X` |
| `ASSIGNED_TO` | PurchaseOrder | Buyer | `BuyerId` → `PersonId` | `GET /publicWorkers?q=PersonId=X` (HCM) |

(Note: only four edges; the former `LOCATED_IN` is now a vocabulary lookup, not an edge.)

---

## 5. Vocabulary Tables

Two kinds of metadata in the KG (§1):

- **Entity declarations** — §3 and §4 above; "where does this concept come from in Fusion?"
- **Vocabulary tables** — this section; "what does this business term mean in Fusion?"

Vocabulary tables are simple lookups. The agent consults them at planning time to translate the user's words into Fusion codes and identifiers.

### 5.1 Country

Mapping between business names, alternate forms, and ISO-2 codes. v1 includes the countries most likely to appear in POC prompts; extending is one-row-per-country.

| Business term(s) | ISO-2 code | Full name |
|---|---|---|
| `"US"`, `"USA"`, `"United States"`, `"United States of America"` | `US` | United States |
| `"UK"`, `"United Kingdom"`, `"Britain"`, `"Great Britain"`, `"GB"` | `GB` | United Kingdom |
| `"India"`, `"IN"` | `IN` | India |
| `"Canada"`, `"CA"` | `CA` | Canada |
| `"Australia"`, `"AU"`, `"AUS"` | `AU` | Australia |

**Note on the existing `search_suppliers_by_country` tool:** It already accepts ISO-2 codes and full names but explicitly does not accept three-letter codes like `"USA"` (it returns empty — see `tests/test_suppliers_by_country_tool.py`). The KG lookup *can* normalize `"USA"` to `"US"` before invoking the tool; that's a planned improvement on the existing tool's behavior, made possible by having the KG as an intermediary.

### 5.2 PO Status

| Business term | StatusCode |
|---|---|
| `"open"`, `"active"` | `OPEN` |
| `"closed"`, `"completed"` | `CLOSED` |
| `"incomplete"`, `"draft"` | `INCOMPLETE` |
| `"canceled"`, `"cancelled"` | `CANCELED` |

Other PO statuses exist in Fusion (`FROZEN`, `ON_HOLD`, etc.) — they are not modeled in v1 because the reference prompt doesn't exercise them.

### 5.3 Entity Synonyms

Maps the words a consultant would say to the canonical entity name.

| Business term | Entity |
|---|---|
| `"supplier"`, `"vendor"` | Supplier |
| `"invoice"`, `"bill"` | Invoice |
| `"purchase order"`, `"PO"`, `"order"` | PurchaseOrder |
| `"buyer"`, `"purchasing agent"`, `"agent"` | Buyer |

This list is short on purpose. The point is to disambiguate the highest-frequency synonyms, not to build a thesaurus.

### 5.4 Relationship Phrases

Maps natural-language phrases to KG edges.

| Phrase pattern | Edge |
|---|---|
| `"<supplier> has <invoice>"`, `"<invoice> for <supplier>"` | `HAS_INVOICE` |
| `"<supplier> in <country>"`, `"<country> supplier"` | `HAS_ADDRESS` + Country vocabulary lookup |
| `"<supplier> has <PO>"`, `"<PO> for <supplier>"` | `HAS_PURCHASE_ORDER` |
| `"<buyer> assigned to <PO>"`, `"<PO> buyer"` | `ASSIGNED_TO` |

This list is illustrative for v1. The agent does not pattern-match these phrases mechanically; the lookups are here to make explicit what the KG considers a known phrasing of each edge. How the agent uses them (substring match? embedding similarity? LLM-driven matching?) is later-phase work.

---

## 6. Query Patterns

Patterns are reusable logical shapes the agent can look up rather than re-derive. Each pattern is named, defined in entity/relationship terms (not tool calls), and accompanied by the Fusion mechanics that realize it.

The agent's job at query time is: parse the user's prompt → identify the pattern(s) it matches → fill in the entity/parameter slots → execute. The KG holds the patterns; the agent applies them.

### 6.1 `no_Y_in_N_months` — Negation over a time-windowed relationship

**Shape:** Given a set of entities of type X, filter to those that have *no* related entity of type Y in the last N months.

**Reference-prompt instantiation:**
> *Suppliers with no invoices in 6 months* → `no_Y_in_N_months(X=Supplier, Y=Invoice, edge=HAS_INVOICE, date_field=InvoiceDate, N=6)`

**Mechanics:**
1. Compute the cutoff date: `today - N months` (ISO format).
2. For each X (in our case, each candidate Supplier), query Y filtered by the date attribute being `>= cutoff` AND the parent reference matching X's join key.
3. Keep X if the query returns *zero* matches; drop X if it returns one or more.

**Why this is a pattern, not just a tool call:** The logic shape ("entity has no related entity in window") recurs across the domain — no invoices, no payments, no shipments, no logins. Encoding it once as a pattern means future agent prompts can match against it; encoding it once per tool means re-deriving it every time.

**Edge case the KG should flag:** Negation over an unbounded set is dangerous. If an agent is asked "suppliers with no invoices ever," and the invoices endpoint is large, naive client-side iteration is expensive. The pattern documentation should note that this is the time-bounded variant; an unbounded "ever" variant needs different mechanics (probably aggregation, not per-supplier query).

### 6.2 `status_filter` — Status-coded attribute filter

**Shape:** Given a set of entities of type X, filter to those whose status attribute matches a business-term-named status value.

**Reference-prompt instantiation:**
> *Open purchase orders* → `status_filter(X=PurchaseOrder, status_term="open" → StatusCode="OPEN")`

**Mechanics:**
1. Look up the business term in the PO Status vocabulary (§5.2) to get the Fusion code.
2. Query the endpoint with the status filter applied.

**Why this is a pattern:** Track A's baseline ran without this. The agent had to know that "open" maps to `StatusCode='OPEN'` (uppercase, specific value) from a docstring. With the lookup explicit, the LLM's job is recognition ("the user said 'open', the KG says 'open PO' means `StatusCode='OPEN'`") rather than guessing.

### 6.3 `country_filter_via_address` — Parent → child traversal with attribute filter

**Shape:** Filter a set of parent entities by an attribute that lives on a child resource.

**Reference-prompt instantiation:**
> *Suppliers in US* → `country_filter_via_address(parent=Supplier, child_relationship=HAS_ADDRESS, child_attribute=CountryCode, value="US")`

**Mechanics:**
1. Resolve the country term using the Country vocabulary (§5.1).
2. Fetch parents with the child resource expanded (`expand=addresses` for suppliers).
3. Client-side: keep a parent if *any* child matches the attribute value.

**Why this is a pattern:** The instinct from a SQL background is "suppliers have a country" — i.e., that country is a parent attribute. In Fusion REST, country is genuinely on the child. Without encoding this, the agent will keep trying `q=CountryCode='US'` against `/suppliers` and getting nothing. The pattern makes the parent-vs-child distinction explicit.

### 6.4 `cross_pillar_lookup` — Following an ID across modules

**Shape:** Given an ID that's exposed on entity X (in pillar A) and is the primary key of entity Y (in pillar B), perform a lookup from pillar B.

**Reference-prompt instantiation:**
> *The buyer assigned to each PO* → `cross_pillar_lookup(from=PurchaseOrder.BuyerId, to=Buyer.PersonId, target_endpoint=hcmRestApi/publicWorkers)`

**Mechanics:**
1. Take the ID from the source entity (FSCM PO's `BuyerId`).
2. Query the target endpoint in the other pillar (HCM `publicWorkers` filtered by `PersonId=X`).
3. Return the target entity's display fields (name, email, username) joined back to the source.

**Honest framing:** This pattern is the one I'm least confident about as a *named* pattern. v1 has exactly one instance of it (PO → Buyer). It may turn out in phase 04 that the `ASSIGNED_TO` edge already carries enough information to make a separate "cross-pillar" pattern redundant. If so, v1.1 will drop the pattern and rely on the edge alone. Documenting this as a soft pattern in v1 keeps the option open without committing to it.

### 6.5 Pattern composition for the reference prompt

The reference prompt composes all four patterns:

> *Show me suppliers in US with no invoices in 6 months but with open purchase orders, including the buyer assigned to each.*

| Clause | Pattern |
|---|---|
| "suppliers in US" | `country_filter_via_address(Supplier, US)` |
| "with no invoices in 6 months" | `no_Y_in_N_months(Supplier, Invoice, 6)` |
| "with open purchase orders" | `HAS_PURCHASE_ORDER` traversal + `status_filter(PO, "open")` |
| "the buyer assigned to each" | `cross_pillar_lookup(PO.BuyerId, Buyer.PersonId)` |

If the KG encodes these four patterns correctly, the agent's planning task collapses from "derive the join structure" to "match clauses to patterns and execute them in order." That is the entire bet of Track B.

---

## 7. What v1 Deliberately Omits

A consolidated list of non-goals, so later phases can refer to it and so scope creep has a name.

### Excluded from v1, with reasons

- **No instance business data.** The most important non-goal, restated for emphasis: no rows of Fusion suppliers, invoices, POs, buyers, or addresses live in the KG. The KG stores structural metadata only. (§1)
- **No per-tenant overlays / customer-specific knowledge.** v1 assumes one customer, one pod, one persona. Per-tenant DFFs, custom value sets, and custom business rules are post-POC concerns. The KG schema *can* be extended to support tenant-scoped overlays later; v1 doesn't model them.
- **No DFFs and custom attributes.** Fusion's Descriptive Flexfields allow customers to add custom fields. v1 does not model them. If a prompt requires a DFF, v1 fails — and that's documented as an expected limitation.
- **No setup and reference data ingestion.** Country codes, currency codes, status code lists, business unit hierarchies — Fusion exposes all of these via setup endpoints. v1 holds a small static vocabulary (§5) rather than ingesting them. Ingestion is a later phase if/when needed.
- **No currency conversion or unit semantics.** Invoice amounts are stored with their currency code; v1 does not convert across currencies. A prompt like "suppliers with > $10K in invoices" would need explicit currency disambiguation; v1 doesn't help with that.
- **No historical / temporal modeling.** The KG describes current Fusion *structure*; not record histories, audit trails, or temporal validity.
- **No approval flows, payment workflows, requisitioning lifecycle.** None of these are entities or relationships in v1. They are deliberately excluded because the reference prompt doesn't need them and modeling them well is itself a multi-week effort.
- **No write operations.**
- **No multi-pod federation.** One pod, one persona.
- **No inverse and transitive relationships.** v1 models edges in one direction (Supplier → PO, not PO → Supplier). The agent can traverse backward by using the same edge in reverse at query time, but the KG doesn't model the reverse as a distinct edge. Transitive closures are not in scope.
- **No cardinality enforcement.** The KG documents cardinality (1-to-many, many-to-1) but doesn't enforce it — because v1 is read-only and there's no write surface to enforce against.
- **No provenance and confidence.** The KG doesn't model "this relationship was added on date D by user U with confidence C." v1 treats all schema content as trusted and static.

### When these omissions will bite

Some of the omissions matter for the reference prompt; some don't. The ones that don't matter for the prompt but are likely to matter in production work:

- **DFFs** — the moment Spire targets real customer pods, DFFs appear.
- **Per-tenant overlays** — multi-tenant deployment is in the SME's stated requirements (see `spire_design_alternatives.md` §5).
- **Setup data ingestion** — the static country vocabulary will not scale to thousands of countries × hundreds of currencies × dozens of value sets.

These are flagged here so they don't get rediscovered in panic at a later phase. The plan is: validate the POC with v1; if the hypothesis holds, expand the KG with the above in deliberate, phased work.

---

## 8. Open Questions

A short list of questions that are *not* answered in v1 and that may need answers in later Dynamic Orchestration phases. These are deliberately not resolved here because resolving them changes the design without changing what the POC tests.

1. **How does the agent match prompt clauses to patterns?** v1 names four patterns and shows how the reference prompt decomposes into them. But the *mechanism* by which the agent matches a prompt clause to a pattern — substring matching, LLM-driven matching, embedding similarity — is not specified. This is Dynamic Orchestration 04 (KG Query Tools) / 06 (Embeddings) territory.

2. **What's the contract between the KG and the existing tools?** The MCP tools from Track A still execute the actual Fusion calls. The KG tells the agent *what* to call; the tools handle *how*. The interface between "KG says: traverse `HAS_PURCHASE_ORDER` from supplier S filtered to OPEN" and "tool call: `search_purchase_orders(supplier_id=S, status='OPEN')`" needs to be defined. v1 hand-waves this; Dynamic Orchestration 04 will need to make it precise.

3. **How is the KG kept in sync with the schema as it evolves?** v1 is a static document. If the schema grows (new entities, new patterns), version-control discipline is one answer; automated regression tests against the schema is another. Out of scope for v1.

4. **What's the error contract when a pattern can't be applied?** If the user asks something the KG doesn't model, what should the agent do — fall back to docstrings (Track A behavior), surface "I don't have a pattern for this" to the user, or attempt a best-effort answer with a warning? Not specified in v1.

(Note: the original revision-1 of this doc had a fifth open question about KG storage. That has now been answered by Dynamic Orchestration 02: Oracle 26ai with SQL Property Graph, accessed via `OracleClient`.)

These questions don't block Dynamic Orchestration 03 (populating the KG) but will need answers before 04 (building the query tools) and 05 (agent integration).

---

## 9. Summary

v1 in one screen:

- **The KG holds metadata, not instance data.** Zero rows of Fusion business data.
- **5 entities** declared, each with endpoint + canonical id + projection fields: Supplier, Invoice, PurchaseOrder, Buyer, Address
- **4 edges** declared, each with join key + endpoint hint: `HAS_INVOICE`, `HAS_ADDRESS`, `HAS_PURCHASE_ORDER`, `ASSIGNED_TO`
- **4 vocabulary tables**: Country, PO Status, Entity Synonyms, Relationship Phrases
- **4 query patterns**: `no_Y_in_N_months`, `status_filter`, `country_filter_via_address`, `cross_pillar_lookup`
- **1 reference prompt** the schema is sized to support
- **1 success criterion**: a Track B agent built on this schema scores meaningfully higher than the 1/7 Track A baseline

The schema is deliberately thin. If it turns out to be too thin, later Track B phases will surface that and v1.1 will add what's missing. The risk of being too thin is real; the risk of over-modeling is worse.

---

**Document status:** v1, revised during phase 03 (KG Population) to clarify the metadata-vs-instance-data distinction and recategorize Country. Will be refined as later Dynamic Orchestration phases discover gaps. Update this document — don't fork it — when changes are needed.

---

<!-- ============================================================ -->
<!-- SECTION 3 — Agent-KG Integration Design (frozen record, from agent_kg_integration.md) -->
<!-- ============================================================ -->

# Agent-KG Integration Design

**Phase:** Dynamic Orchestration 04 — KG Query Tools (design doc, lands first commit)
**Status:** Decision recorded; implementation in subsequent phase 04 commits
**Decision:** Option B-lite — KG content statically embedded in the system prompt at startup. No per-request planner; no KG MCP tools.

This document captures the architectural decision for how the agent talks to the KG, the alternatives considered, the failure-mode evidence that drove the choice, and how the decision was reached (including an honest revision).

Companion docs:
- `kg_schema_v1.md` — what the KG models
- `kg_evaluation_framework.md` — how the decision will be tested
- `../phase_a5_baseline_report.md` — Track A's failure evidence

---

## 1. The Question

Phase 03 built the KG as five flat tables in the SPIRE schema. The KG is queryable. But the central architectural question for Track B remains open:

**How does the agent talk to the KG?**

The three boxes don't change between options:

- **LLM (Gemini)** — does the reasoning
- **KG (Oracle tables, populated)** — holds structural knowledge
- **Agent loop (LangGraph)** — orchestrates between them

What changes is **the path the KG knowledge takes to reach the LLM**.

---

## 2. The Four-Context View

Five actors split across four contexts (deployment/process boundaries):

| Context | Actors | Where it runs |
|---|---|---|
| **User context** | User | Terminal / `ask.py` CLI invocation |
| **Backend context** | Agent loop (LangGraph) + LLM call site | The Python process that runs `ask.py`; LLM is called from here but lives at Google |
| **MCP server context** | MCP tools (Fusion + KG), FusionClient, OracleClient | Separate process on `127.0.0.1:3333` (FastMCP) |
| **External endpoints** | Fusion REST + Oracle 26ai + Gemini | Cloud (Fusion, Gemini), local Docker (Oracle) |

The architectural question reframes as: **which context owns the decision about what KG knowledge the LLM gets to see on a given run?**

---

## 3. The Four Options Considered

### Option A — KG queries as MCP tools the LLM can call

The KG is exposed as a set of MCP tools (`kg_get_entity`, `kg_get_edge`, `kg_get_pattern`, `kg_lookup_vocabulary`, etc.) alongside the existing Fusion tools. The LLM sees them in its tool list; it decides when to consult.

**Owner of the decision:** the LLM. Backend context just runs the loop.

**Strengths:**
- Cleanest ablation (remove KG tools from the tool list)
- Symmetric with how Fusion tools already work
- Smallest mental model — "more tools"

**Weaknesses:**
- The LLM may *ignore* the KG tools and pattern-match like Track A did
- Inherits Track A's failure mode rather than addressing it

### Option B (full) — Pre-LLM planner builds a KG context bundle per request

A new "planner" component runs **before** the LLM. It analyzes the user prompt, identifies which entities/edges/patterns/vocabulary are relevant, queries the KG, and packages a context bundle into the system prompt. The LLM then runs as in Track A, with Fusion tools and the bundle in its context.

**Owner of the decision:** backend context (the planner).

**Strengths:**
- Bypasses Track A's failure mode (LLM can't ignore knowledge it can't avoid)
- Per-prompt relevance: only the KG content this prompt needs is loaded

**Weaknesses:**
- The planner is non-trivial to build — how does it know what's relevant without already understanding the prompt?
- Likely needs an LLM-driven extraction step (turns into two LLM calls)
- Adds a new component with its own failure modes
- Ablation is messier (the planner does more than KG injection)

### Option B-lite — Static KG context, loaded once, embedded in the system prompt

A small loader queries the KG **once at agent startup**, formats the full v1 KG into a structured text section, and includes it in the system prompt for every conversation. No per-request planning, no per-request KG queries.

**Owner of the decision:** backend context. But the "decision" is trivial — always show the LLM the whole v1 KG.

**Strengths:**
- Bypasses Track A's failure mode same as B
- Tiny engineering surface — one loader, no planner
- Trivial ablation (swap system prompt to one without KG content)
- KG knowledge is **always in front of the LLM**, not optional

**Weaknesses:**
- System prompt is bigger (a few thousand tokens of KG content per request)
- Same content every prompt — no per-prompt tuning
- Doesn't scale to large KGs (but v1 is ~80 rows; not a v1 concern)
- The LLM might glaze over a dense system prompt (mitigation: format and tune the KG section for readability)

### Option C — Hybrid (static summary + drill-down tools)

KG summary in the system prompt (like B-lite) **and** KG MCP tools available for the LLM to call when it wants more detail (like A).

**Strengths:**
- Belt-and-suspenders for production
- LLM always sees basics; can drill down on demand

**Weaknesses:**
- Two integration points to design and test
- Hardest to ablate — disabling "the KG" means disabling both, and if scores move, attribution is muddy
- Largest engineering surface
- POC-inappropriate (production pattern, not measurement pattern)

---

## 4. Evidence That Drove the Decision

Track A's baseline measured 1/7 on the reference prompt across 5 runs. Failure breakdown:

| Failure mode | Runs affected | Root cause |
|---|---|---|
| Premature termination | 3 of 5 | LLM called one tool, didn't iterate, didn't ask for more |
| Parameter confusion across tools | 2 of 5 | LLM passed `supplier_number` to a tool expecting `supplier_id`; crashed |
| No error recovery | 2 of 5 (the crashes) | LangGraph propagated the tool exception; LLM never saw or recovered from it |

Common thread: **the LLM didn't recognize when it needed more information** — neither asked for help with disambiguation, nor iterated to find the next step, nor recovered from a tool error.

This is the recognition skill Option A relies on. If the LLM can't recognize "I need more information," it won't recognize "I should consult the KG" either. Option A asks the LLM to do exactly the kind of self-aware querying Track A showed it does poorly.

Options B and B-lite bypass this by making the knowledge **present in the LLM's context whether it asks or not.** The LLM doesn't have to recognize a need; the information is just there.

This evidence weights against A and toward B / B-lite.

---

## 5. The Decision: B-lite

Among B-lite, B (full), and C:

- **B-lite** has the smallest engineering surface and the cleanest ablation among the options that bypass Track A's failure mode. It addresses the right problem with the lightest tool.
- **B (full)** addresses the same problem but adds a per-request planner. The planner is its own engineering project. For v1, the static-bundle approach is sufficient because the KG fits in context comfortably.
- **C** is a production architecture, not a measurement architecture. Two integration points muddy the ablation.

**B-lite it is.**

### What B-lite looks like in code

| Layer | What changes |
|---|---|
| New loader | Loads all 5 KG tables at startup, formats them into a structured text section |
| `runner.py` | System prompt gains a `{{ kg_context }}` section, populated at agent build time |
| `src/spire/mcp_server/` | **No new MCP tools.** Existing Fusion tools unchanged. |
| Tests | New test verifies the loader produces a non-empty, well-formed context section |
| Configuration | Add a way to swap KG context in/out (for ablation in phase 08) |

The new code lives in **backend context** (the `ask.py` / `runner.py` process), not in the MCP server. The MCP server is unchanged. This is intentional: the KG content is part of *how the agent thinks*, not part of *what the agent does*.

### What B-lite explicitly does NOT do

- No new MCP tools. The agent's tool list is unchanged from Track A.
- No per-request KG queries. KG is loaded once at startup.
- No planner. No prompt analysis. No relevance scoring.
- No graph queries (`MATCH`). The loader uses plain SQL to fetch table rows.
- No embeddings. KG content is plain text. Phase 06 may add embeddings if Tier 1 evaluation suggests they'd help.

### How the evaluation framework ablation works under B-lite

`kg_evaluation_framework.md` §3 calls for an ablation run to isolate the KG's contribution. Under B-lite, ablation is:

1. Configure the agent to use a system prompt **without** the KG context section
2. Same Fusion tools, same model, same prompt, same rubric
3. Re-run the 5-run measurement

The delta between with-KG and without-KG is the KG's contribution. Other improvements (better system prompt framing, tool description refinements landed during Track B) are still present in both, so the ablation isolates the KG component cleanly.

---

## 6. Honest Revision Note

The first lean recorded for this decision was Option A, with the reasoning "cleanest to evaluate; ablation is trivial." That lean was sloppy: it optimized for measurability without weighing the failure-mode mismatch with Track A's evidence.

After working through the four options with sequence diagrams and the four-context framing, the revised read was that A inherits exactly the failure mode Track A demonstrated (LLM doesn't ask for help when it should). B-lite bypasses that mode while keeping ablation clean enough.

Recording this because the working agreement values honest framing over revisionist tidiness, and because future readers (including future-self) should see that the architecture wasn't obvious on first pass. Both leans were defensible; B-lite is better-supported by the evidence.

---

## 7. Implications for Subsequent Phases

| Phase | Implication |
|---|---|
| 04 (rest of this phase) | Build the KG context loader. Update `runner.py` to inject KG content into the system prompt. Add tests. No new MCP tools. |
| 05 (Agent integration) | Largely subsumed by phase 04 under B-lite — there's no separate "integrate the KG" step because the KG enters the agent at startup, not at runtime. Phase 05 becomes "verify end-to-end on a smaller variant of the reference prompt before phase 08." |
| 06 (Embeddings) | Open question. B-lite doesn't need embeddings for v1. If Tier 1 evaluation suggests the static bundle is too dense and LLM glaze is a real problem, phase 06 might introduce embedding-based selection of which KG content to include. Defer the decision. |
| 07 (Polish) | Mostly tracing improvements. Verify KG section is recorded in trace files for later inspection. |
| 08 (End-to-end test) | 5-run measurement with KG-on. |
| 09 (Comparative) | Ablation: 5-run measurement with KG-off (system prompt sans KG section). Tier 2 from `kg_evaluation_framework.md`. |

The phase 05 implication is the biggest: under B-lite, phase 05 shrinks because there's no agent loop change required. The integration *is* the system prompt change.

---

## 8. What This Decision Does Not Settle

A few questions deliberately deferred:

- **Format of the KG context section in the system prompt.** Markdown table? Structured JSON? Prose bullets? This is a tuning decision; phase 04's implementation will pick a default and we can iterate.
- **Should KG content include the full pattern `mechanics` text, or just pattern names + parameters?** Bigger means denser prompt; smaller means LLM may not have enough to act on. Tunable.
- **Should the KG context be in the system prompt or in a special first user/assistant turn?** Implementation detail; either works. System prompt is simpler.
- **How big is "too big" for the system prompt?** Empirically tunable. Gemini handles long context well; not a v1 risk.
- **What happens if the KG is empty or unreachable at startup?** Edge case. The loader should fail fast with a clear error rather than silently producing an empty bundle.
- **Whether `cross_pillar_lookup` survives as a pattern.** Phase 03 flagged this as the pattern least confident about. Phase 04 implementation may find it redundant with the `ASSIGNED_TO` edge content; if so, v1.1 schema update drops it.

These are tuning knobs, not architectural decisions. The architecture is settled; the tuning happens during phase 04's iteration.

---

## 9. Summary

- The question: how does the agent talk to the KG?
- Four options considered: A (tools), B (planner), B-lite (static bundle), C (hybrid)
- Track A's evidence: LLM doesn't recognize when it needs more information
- Decision: **B-lite** — bypasses the recognition problem with the smallest engineering surface
- Implementation lives in backend context; MCP server is unchanged
- Ablation cleanly isolates the KG's contribution by swapping the system prompt
- Phase 05 shrinks as a result; phase 04 absorbs most of the integration work
- Tuning decisions (bundle format, density, etc.) deferred to phase 04 implementation

The architecture is settled. The phase 04 work that follows is implementation against this design.

---

<!-- ============================================================ -->
<!-- SECTION 4 — Natural-Language Parser Design (frozen record, from feature_1_nl_parser_design.md) -->
<!-- ============================================================ -->

# Feature 1 — Natural-Language Parser: Design

**Status:** IMPLEMENTED and verified (live Gemini + full suite green).
**Date:** 2026-06-01.
**Module:** `src/spire/nl_parser/` — `result.py`, `vocabulary.py`, `draft.py`,
`validation.py`, `parser.py`. Tests: `tests/test_nl_parser.py` (mock, 14) and
`tests/test_nl_parser_integration.py` (live Gemini, 8).
**Companion docs:** `docs/feature_roadmap.md` (feature 1, the *what/why*);
the 2026-06-01 handoff (section 4, the design questions this doc answers);
`docs/designs/phase_2_planner_design.md` (the `Intent` / `Plan` contract the
parser feeds).

This document records the feature 1 design discussion AND its implementation
outcome. The five design questions and their decisions are in section 2;
what was actually built (including two fixes that only surfaced under the live
model) is in section 6.

---

## 1. What feature 1 is

An LLM-driven layer that converts a natural-language prompt into an `Intent` —
the structured object the deterministic planner (`generate_plan`) already
consumes. Today every prompt shape requires a hand-built `Intent` in
`run_plan.py`; the parser removes that bottleneck.

It is the **interpreter** stage of the Design 3 pipeline:

```
Prompt -> LLM (interpreter / parser) -> KG (planner) -> MCP (executor)
       -> Tools -> Fusion -> Data -> LLM (formatter / synthesizer) -> Output
```

Two LLMs sit in the pipeline, doing opposite jobs:
- the **interpreter** (this feature) constrains its *input* against the KG;
- the **formatter** (the existing synthesizer) validates its *output* against
  the fetched data.

Everything between the Intent and the answer — planner, executor, MCP tools,
synthesizer — is unchanged. Feature 5 (synthesizer schema generalization, now
merged) was the prerequisite that lets the synthesizer accept whatever Intent
shapes the parser produces.

---

## 2. The five design questions — decisions

### Q1 — Where does the parser live?

**Decision: a new module beside the planner (e.g. `src/spire/nl_parser/`),
modeled on the synthesizer, using the planner's synchronous KG path.**

Rejected alternatives:
- **Modify the Track A agent (`runner.py`).** The agent's architecture is
  built for multi-step tool-calling (`bind_tools`, the
  `assistant -> tools -> assistant` LangGraph loop, an MCP session). The
  parser makes a single LLM call and emits a single structured Intent — it
  needs none of that machinery. Reusing the agent means threading a one-shot
  path through a module whose whole shape assumes a tool loop, and inheriting
  its async execution model (which conflicts with the Q2 sync decision).
- **Fold parsing into the planner (`planner.py`).** The planner's defining
  property is that it contains **no LLM**. Putting an LLM call inside it
  contaminates the one deterministic module. Do not.

The correct reuse target is the **synthesizer**, not the agent: the
synthesizer is already the parser's mirror image — one bounded LLM call with
structured output and post-validation. The parser copies that pattern into its
own module.

### Q2 — How is the parser constrained to KG-valid Intents only?

**Decision: synchronous, two-way communication between the parser and the KG.**

- **Direction 1 (KG -> parser), before the LLM call:** the parser reads the
  allowed vocabulary (entities, filters, patterns) from the KG and embeds it in
  the LLM prompt as the menu the model may order from.
- **Direction 2 (parser -> KG), after the LLM call:** the parser validates the
  draft Intent back against the KG and rejects anything the model invented
  (an undeclared entity or filter).

Both directions are **synchronous** — the parser calls, blocks, and waits
inline. This is achieved by routing through the **planner's** synchronous KG
path (`oracledb.connect()` cursor, the existing `find_*` / `resolve_vocab` /
`_validate_intent_filters` functions), **not** the agent's async
`load_kg_context()`. The validation step reuses the planner's existing
`_validate_intent_filters` rather than reimplementing it.

The synchronous parser runs *before* the async planner/executor section; the
handoff from a sync parser to the async pipeline is a clean sequential
boundary, not a conflict. (Confirm at implementation time.)

### Q3 — How are out-of-scope prompts handled?

**Decision: the parser emits a structured "can't answer" result that names the
flavor and the raw facts. The user-facing message is framed in terms of what
Spire *can* do, sourced from the KG. Detection is built in feature 1; polished
wording is feature 8.**

When a prompt is out of scope, the user is told **what Spire's capabilities
are** and that their prompt falls outside them — not a bare "I can't answer,"
and not a low-level reason. The capability statement is generated from the KG
(the same source the parser already reads), so it never goes stale: when
contracts are added (feature 6), the message updates itself.

Three flavors are distinguished, because the KG comparison already reveals
which check failed — so distinguishing them is nearly free:
1. **Unknown entity** — the target entity isn't in `kg_entity` at all
   (e.g. `Contract`, prompt-6).
2. **Unsupported filter** — the entity is known but the filter isn't in the
   KG's filter set (e.g. `amount_over` on POs, prompt-2). This is the check
   `_validate_intent_filters` already performs.
3. **Unsupported operation** — the entity is known but the operation isn't
   (e.g. aggregation / `target_entity=Buyer`, prompt-5). This is what the
   synthesizer's `UnsupportedEntityError` already rejects.

Implementation note: messaging uses **one template filled from the KG**, not
three hand-written paragraphs. The flavor only changes the "what's missing"
slot.

Division with feature 8:
- **Feature 1 (now):** detect out-of-scope, identify the flavor, emit a
  structured "can't answer" result carrying the flavor tag and raw facts. This
  is intrinsic to feature 1 — the parser cannot emit a knowingly-broken Intent,
  so it must detect un-answerability to function.
- **Feature 8 (later):** turn the structured refusal into polished,
  capability-framed user-facing wording.
- **Test for the line:** feature 1's output should be *correct and structured*
  but may be bluntly worded; feature 8 makes it *gracious*.

### Q4 — Testing without flaky or hidden LLM failures

**Decision: keep both mock unit tests and live LLM tests. Run the live tests as
part of regular verification (not deselected-and-forgotten), so LLM regressions
surface early. Keep the two split so a failure points at the culprit.**

- **Mock unit tests** (fast, deterministic, always run): inject a mock LLM that
  returns canned output. These hold the LLM constant and test the parser's own
  logic — KG vocabulary loading, draft-Intent validation, refusal-flavor
  detection, clean pass-through of valid Intents. They assert **exact** Intent
  output. A mock failure means **our code** is wrong.
- **Live tests** (real Gemini, run regularly): send real prompts to the model
  and check the parser produces a sane result. A live failure means **the
  model** is the problem — drift, a broken prompt, unparseable output. Because
  LLM output is non-deterministic, live tests assert **properties**
  (`target_entity == "Supplier"`, the country filter resolved to `US`, this
  out-of-scope prompt produced a refusal), **not** exact equality — otherwise
  they flake and get ignored.

Follows the synthesizer's existing pattern (optional injected `llm`,
`@pytest.mark.integration` for live), with the difference that the live tests
are treated as first-class regular verification, not a rare opt-in.

Fixture shape: a `(prompt, expected_intent_or_refusal)` case table, reusing the
existing gap-analysis prompts from `run_plan.py` (anchor, original, prompt-1
through prompt-6), which have known expected outcomes. The table doubles as
documentation of what the parser is supposed to handle.

### Q5 — Relationship to the synthesizer's `UnsupportedEntityError`

**Decision (Option 1): the parser is the user-facing gatekeeper; the
synthesizer's check is retained as a loud developer-facing backstop.**

The parser owns *user-facing* refusal (gracious, capability-framed, for real
prompts). The synthesizer's `UnsupportedEntityError` stays as a
*developer-facing* invariant (loud, for "this should be impossible" cases).
Same error class, two audiences, two jobs — layered defense, not conflict.

How "stop" is signaled: the parser does **not** raise an exception for
out-of-scope prompts (that would reintroduce the loud-failure problem feature 8
fixes). It returns a **checked refusal result**, and the pipeline gates on it:

```
result = parse(prompt)
if result is a refusal:
    show the capability message          # stop — never plan/execute/synthesize
else:
    plan -> execute -> synthesize        # only valid Intents flow downstream
```

So in normal flow an out-of-scope request never reaches the synthesizer — which
is exactly why the synthesizer's check should essentially never fire. If it
*does* fire, it means something bypassed the gate: a hand-built Intent from
`run_plan.py`, or a parser regression. That is the case the backstop exists for.

**Option 2 (delete the synthesizer's check) is explicitly rejected:** hand-built
intents in `run_plan.py` bypass the parser entirely, so the synthesizer's check
is the only thing protecting that path. As long as the hand-built path exists
(it does, for testing), the check must stay.

---

## 3. New components, and what is untouched

**New (feature 1):**
- The NL parser module (own folder, beside the planner; bounded single LLM
  call inside).
- The KG-vocabulary read it performs (sync, via the planner's KG path) and the
  draft-Intent validation it performs back against the KG.
- A structured "can't answer" result type carrying a flavor tag + raw facts.
  *(Touches the `Intent` contract — adds a way to represent "no Intent, here's
  why," e.g. a sibling type or a refusal field. Confirm nothing downstream
  assumes every parser output is a plannable Intent.)*

**Unchanged:** planner, executor, MCP tools, Fusion client, synthesizer. The
`Intent` object the planner consumes is the same — only its *source* changes
(was hand-written in `run_plan.py`, now generated by the parser).

---

## 4. Component lifecycle — the Track A agent

The Track A agent (`ask.py` -> `runner.py`, the LLM-as-planner baseline) is
**not** part of the Design 3 runtime and is never invoked by the Design 3
pipeline. It is kept solely as the **evaluation baseline** — the comparison arm
that justifies the Design 3 architecture.

- **Keep until** Design 3 consistently produces valid results — specifically,
  until the feature-1 parser-driven path has been run against the agent
  baseline and the before/after comparison is recorded.
- **Then** the agent has served its purpose and should be deleted.
- **Do not** remove the agent mid-feature-1: doing so destroys the ability to
  demonstrate the before/after that justifies feature 1. Removal is a
  deliberate later step gated on the final baseline comparison — not a cleanup
  to do now.
- **Rationale:** the repo is still a POC; in the "prove the architecture" phase
  the baseline earns its keep. Feature 1 is built identically whether or not
  the agent is later removed, so this is a tracked lifecycle policy, not a
  blocker.

*(This section is also intended for `docs/feature_roadmap.md` as a "Component
lifecycle" section.)*

---

## 5. Implementation record

Built in checkpoints, each run against the live KG / model before the next:

1. Result type + sync KG vocabulary read.
2. LLM call + draft production (mock unit tests).
3. Two-way KG validation, B1 ordering.
4. Pipeline gate in `run_plan.py` (`--prompt`, exit 4 on refusal).
5. Live integration tests, run as regular verification.

### Two fixes that only surfaced under the live model

1. **Silent rewrite (serious).** The first prompt iteration told the model to
   "emit the closest Intent" for out-of-scope prompts and rely on later
   validation. The model instead silently rewrote "contract renewals" as a
   bare Supplier query — validation never fired because nothing INVALID was
   emitted. Fix: (a) the prompt now forbids salvaging and instructs explicit
   refusal; (b) `DraftIntent` gained an `unanswerable` + `unanswerable_reason`
   slot so the model can *choose* to refuse. This is the structural defense —
   the model self-declares un-answerability.

2. **Fragile value encoding.** `value_json` required JSON-quoted strings, but
   the model unreliably emitted bare `GB` instead of `"GB"`, causing
   intermittent malformed-value refusals. Fix: `to_intent()` decodes leniently
   — a non-JSON `value_json` is taken as a plain string; bools/objects still
   decode as JSON. Safe because the planner validates values downstream.

Also tightened: a "completeness" block in the prompt (extract EVERY in-scope
constraint, with concrete NL->filter mappings) after the live tests caught the
model dropping the country, buyer-include, and no-recent-invoices clauses.

### Test outcome
- Full suite: 277 passed, 13 deselected (was 263 + 5; +22 parser tests).
- Live integration suite: 8/8 green across repeated runs (stable, not lucky).

### Known follow-ups (not blockers)
- The model self-declared refusal maps to flavor `UNPARSEABLE` today even when
  the truer flavor is `UNKNOWN_ENTITY` (e.g. contracts). Honest but coarse;
  feature 8's capability-framed wording refines this.
- The parser imports the planner's private filter constants so its menu can't
  drift from `_validate_intent_filters`. When filters move into the KG
  (planner v1.2), read them from the KG instead.
- Refusal wording is blunt (feature 1 scope); capability-framed wording is
  feature 8.

---

<!-- ============================================================ -->
<!-- SECTION 5 — Planner Design (frozen record, from phase_2_planner_design.md) -->
<!-- ============================================================ -->

# Phase 2 Planner Design

> **Status:** Design only. Implementation pending.
> **Purpose:** Capture the verified design decisions from Phase 2 step 0 (2a, 2b, 2c) before writing the planner code.
> **Companion file:** `src/spire/planner/planner.py` — Python stubs that mirror this design.

---

## Context

The Spire POC tests whether a Knowledge Graph (KG) can drive deterministic tool selection for an agent that queries Oracle Fusion via MCP-wrapped REST endpoints. The architecture is **Option 3** (locked in earlier):

```
Prompt
  → LLM (Intent Parser)
  → Knowledge Graph (Planner)         ← this phase's work
  → MCP (Executor)                    ← Phase 3
  → Tools → Fusion Endpoints → Data
  → LLM (Response Synthesizer)
  → Output
```

The planner sits between the LLM's intent parsing and the MCP executor. It reads only from the KG (Items 1–8 already in master) and emits a structured plan. **No LLM in the planning step.** No prose-reading for decisions.

---

## Verified design decisions (Phase 2 step 0)

| Decision | Choice | Verified by |
|---|---|---|
| Language | Python (oracledb 4.0.0) | 2a — connection test against the KG |
| Plan representation | Structured Python data (list of dataclasses / dicts) | 2b — full plan for the anchor question expressed with zero prose |
| Code organization | Composed small functions, one per KG concept; thin orchestrator | 2c — orchestrator traces cleanly through the anchor question |

---

## The anchor question

All design choices were validated against:

> *"Show me suppliers in US with open purchase orders, including the buyer assigned to each."*

The LLM parses this into structured intent:

```python
Intent(
    target_entity="Supplier",
    filters=[
        {"type": "country", "value": "US"},
        {"type": "has_open_PO", "value": True},
    ],
    include=["Buyer"],
)
```

---

## Plan data structure (2b)

A plan is a **list of Steps**. Each Step is a dataclass with these fields:

| Field | Type | Purpose |
|---|---|---|
| `step_id` | `int` | Execution order |
| `tool_name` | `str` | Which MCP tool to invoke (resolved from `kg_entity_tool` or `kg_edge_tool`) |
| `tool_args` | `dict` | Arguments for the tool; values are either literals or the special token `"$iteration_value"` |
| `iterate_over` | `dict \| None` | `{"from_step": <output_name>, "field": <field_name>}` when the step iterates over previous output; `None` otherwise |
| `client_filters` | `list[dict]` | Python-side filters applied to results (`server_filter_rule = 'join_only'` for all current edges, so non-join filters go here) |
| `output_name` | `str` | Stable name for this step's output, referenced by later steps |
| `output_dedupe_by` | `str \| None` | Field to deduplicate output items on; `None` = no dedup |

### Cross-step references

Iteration sources use a dict:

```python
{"from_step": "us_suppliers", "field": "SupplierId"}
```

Within `tool_args`, the literal string `"$iteration_value"` means *"substitute the current iteration's value here."* This avoids the redundancy of repeating the source reference inside `tool_args`.

### Client filter shape

```python
{"field": "StatusCode", "op": "equals", "value": "OPEN"}
```

Operators supported in v1: `equals`, `any_child_equals` (for `expand=addresses` style nested matching).

### Worked example — the anchor question

```python
plan = [
    Step(
        step_id=1,
        tool_name="search_suppliers_by_country",
        tool_args={"country": "US"},
        iterate_over=None,
        client_filters=[],
        output_name="us_suppliers",
        output_dedupe_by=None,
    ),
    Step(
        step_id=2,
        tool_name="search_purchase_orders",
        tool_args={"supplier_id": "$iteration_value"},
        iterate_over={"from_step": "us_suppliers", "field": "SupplierId"},
        client_filters=[
            {"field": "StatusCode", "op": "equals", "value": "OPEN"},
        ],
        output_name="open_pos",
        output_dedupe_by=None,
    ),
    Step(
        step_id=3,
        tool_name="get_buyer",
        tool_args={"buyer_id": "$iteration_value"},
        iterate_over={"from_step": "open_pos", "field": "BuyerId"},
        client_filters=[],
        output_name="buyers",
        output_dedupe_by="BuyerId",
    ),
]
```

### Kill-point check for 2b

Every decision the executor needs is encoded as data:
- ✅ Tool to call (`tool_name`)
- ✅ Arguments (`tool_args`)
- ✅ Iteration source (`iterate_over`)
- ✅ Filters applied after each call (`client_filters`)
- ✅ Result naming and deduplication (`output_name`, `output_dedupe_by`)

No prose. No "and obviously the executor would just know…"

---

## Function organization (2c)

The planner is organized as **small functions, one per KG concept**, with a thin orchestrator. Each function performs one KG query and returns parsed structured data.

### Small functions — one per KG lookup

| Function | KG table queried | Returns |
|---|---|---|
| `find_entity(entity_name)` | `kg_entity` | endpoint_path, canonical_id_field, display_name_field |
| `find_entity_tool(entity_name, filter_type)` | `kg_entity_tool` | MCP tool name |
| `find_edge(from_entity, to_entity)` | `kg_edge` | edge_name, join fields, server_filter_rule |
| `find_edge_tool(edge_name)` | `kg_edge_tool` | MCP tool name, or `None` if not independently traversable |
| `find_pattern_for_filter(entity_name, filter_type)` | `kg_pattern_binding` | pattern_name, parameter_bindings |
| `resolve_vocab(vocab_kind, term)` | `kg_vocabulary` | canonical Fusion code |

Each is independently testable — mock the DB connection, supply a fixture row, assert the parsed result.

### The orchestrator

```python
def generate_plan(intent: Intent) -> Plan:
    plan = []
    step_counter = 1

    # Step 1: Fetch the target entity (with any entity-level filter
    #         that has a dedicated fetcher tool)
    entity_filter = _pick_entity_filter(intent.filters)
    fetcher_tool = find_entity_tool(intent.target_entity, entity_filter)
    fetcher_args = _build_fetcher_args(entity_filter, intent.filters)
    plan.append(Step(step_id=step_counter, tool_name=fetcher_tool, ...))
    previous_output = plan[-1].output_name
    step_counter += 1

    # Steps 2..N: For each filter that needs an edge traversal,
    #             add an iterating step
    for filter_spec in _filters_needing_edge_traversal(intent.filters):
        target = _filter_target_entity(filter_spec)
        edge = find_edge(intent.target_entity, target)
        tool = find_edge_tool(edge["edge_name"])
        client_filters = _resolve_client_filters(filter_spec, target)
        plan.append(Step(
            step_id=step_counter,
            tool_name=tool,
            tool_args={_arg_name_for_tool(tool): "$iteration_value"},
            iterate_over={"from_step": previous_output, "field": edge["from_join_field"]},
            client_filters=client_filters,
            ...
        ))
        previous_output = plan[-1].output_name
        step_counter += 1

    # Steps N+1..: For each include, add a lookup step
    for include_entity in intent.include:
        edge = find_edge(_previous_entity(plan), include_entity)
        tool = find_edge_tool(edge["edge_name"])
        plan.append(Step(
            step_id=step_counter,
            tool_name=tool,
            tool_args={_arg_name_for_tool(tool): "$iteration_value"},
            iterate_over={"from_step": previous_output, "field": edge["from_join_field"]},
            output_dedupe_by=edge["from_join_field"],
            ...
        ))
        step_counter += 1

    return plan
```

### Helper functions (private)

These absorb the non-trivial logic that would otherwise clutter the orchestrator:

| Helper | Job |
|---|---|
| `_pick_entity_filter(filters)` | Decide which filter (if any) has a dedicated entity-level fetcher tool |
| `_build_fetcher_args(filter_type, filters)` | Resolve vocab values into tool arguments |
| `_filters_needing_edge_traversal(filters)` | Identify filters that require an edge hop (not handled by the entity-level fetcher) |
| `_filter_target_entity(filter_spec)` | Which entity does this filter constrain? |
| `_resolve_client_filters(filter_spec, target)` | Look up pattern + bindings, resolve vocab, build filter list |
| `_arg_name_for_tool(tool_name)` | What argument name does the MCP tool expect? |
| `_make_output_name(entity_name)` | Stable, readable output name for a step |
| `_previous_entity(plan)` | What entity did the previous step's output represent? |

### Kill-point check for 2c

- ✅ Orchestrator reads top-to-bottom; three clear blocks (entity fetch, filter loops, include loops); deepest nesting is one `for` loop
- ✅ Each KG concept = one function call in the orchestrator
- ✅ Tracing the anchor question through the orchestrator produces the 2b plan
- ✅ `_resolve_client_filters` accepted as a clean abstraction (orchestrator doesn't need to see how client filters are built)

---

## Known limitations of this design (v1)

Worth being explicit about, so future-you doesn't assume they're handled:

1. **Three-block orchestrator generalizes for the anchor question's *shape*, but not all shapes.** Questions with no filters but multiple includes, or filters needing multi-edge traversals, would require additional orchestrator logic. Acceptable for v1 (the POC's goal is to prove the mechanism, not to cover every question shape).

2. **No conditional steps** (e.g., "if step N returns empty, skip step N+1"). Anchor question doesn't need them.

3. **No parallelism.** Step execution is sequential. The executor in Phase 3 could parallelize iteration calls, but the plan doesn't mandate or describe that.

4. **No error / retry / fallback in the plan.** These are executor concerns.

5. **Operator set in `client_filters` is minimal** — `equals`, `any_child_equals`. Sufficient for the anchor question.

---

## What this design does NOT include

To preempt confusion when implementing:

- **The LLM intent parser** — produces `Intent`. Out of scope for this phase.
- **The MCP executor** — consumes a `Plan` and runs it. Phase 3 work.
- **The response synthesizer** — converts step outputs into a natural-language answer. Out of scope.
- **Connection pooling, retries, transaction management** — implementation concerns not visible in the design.

---

## Implementation order (next phase)

1. Implement the six small KG-query functions, each with unit tests against fixtures
2. Implement the helpers
3. Implement the orchestrator
4. Test end-to-end against the anchor question; compare emitted plan against the worked example above
5. Hand off the plan to Phase 3's executor

---

<!-- ============================================================ -->
<!-- SECTION 6 — Aggregation Design (frozen record, from feature_7_aggregation_design.md) -->
<!-- ============================================================ -->

# Feature 7 — Aggregation: Design

**Status:** design settled, not yet built. Companion to `docs/feature_roadmap.md`
(feature 7) and the `docs/designs/feature_1_nl_parser_design.md` parser design.

**Settled in:** brainstorming session (this doc is its output). The roadmap
required a design before work starts; this is that design. A build session can
implement against it without re-litigating the decisions below.

---

## 1. Problem

Spire answers "show me invoices from supplier X" — it fetches rows and returns
them. It cannot answer "top 10 suppliers by spend." That question needs *math
over many rows*: group invoices by supplier, sum the amounts, sort, take the
top N. The existing pipeline returns rows; aggregation returns computed numbers
over rows. That is the gap (closes G4).

The math never runs in the LLM. LLMs are unreliable at arithmetic over many
rows and the rows would not fit in context anyway. A Python tool does the math;
the LLM only interprets the prompt and phrases the answer.

---

## 2. Architecture: a tool, not a path

Aggregation is a **specific tool the planner routes to** — not a new pipeline
path and not a general aggregation engine.

- The LLM parser reads the prompt and emits an aggregation Intent.
- The planner deterministically maps that Intent to a named tool. The planner
  does not "decide" in any clever sense — it routes, the same way it routes a
  list Intent to `search_invoices` today.
- The tool fetches, filters, and computes — all in Python, all inside itself.
- The synthesizer phrases the structured result.

No control-flow branching is introduced. Routing-an-Intent-to-a-tool *is* the
architecture, and it already exists. This preserves the Design 3 property that
failures pin to a specific stage: a bad aggregate lives in one named tool.

This was reached after explicitly considering and rejecting alternatives that
branch the pipeline on an "is this aggregation?" flag (a type-branch, a unified
path with an optional aggregation tail, or a late branch after a shared
fetch+filter). All three are unnecessary once aggregation is a tool: the tool
owns its own fetch+filter+math, so there is no shared step to branch and no
drift between paths.

---

## 3. First tool: `aggregate_invoices_by_supplier`

**Inputs**
- `date_from`, `date_to` — the range. Pushed down into the fetch (filter goes
  to Fusion), so out-of-range invoices are never read.
- `top_n` — number of suppliers to return.

**Logic**
1. Fetch invoices in `[date_from, date_to]` (filter at source).
2. Group by supplier (Python).
3. Sum invoice amount per supplier.
4. Sort by spend descending, then supplier name ascending.
5. Take `top_n`.

**Fixed by identity (not parameters)**
- Grouping is by supplier and the measure is sum-of-spend. Both are baked into
  the tool's identity. A different grouping or measure is a *different tool*,
  never a parameter on this one. (See the boundedness rule, §6.)

**Determinism rules**
- Ties at the `top_n` boundary: cut at exactly `top_n`. The name-ascending
  secondary sort makes "the Nth supplier" the same supplier on every run, so
  the cut is deterministic rather than arbitrary.
- Exactly `top_n` rows returned (or fewer only when fewer suppliers exist).

**Output** (`shape: "supplier_spend_ranking"`)
```
{
  shape: "supplier_spend_ranking",
  date_from: "2026-01-01",
  date_to: "2026-03-31",
  total_suppliers: 47,        # distinct suppliers in range, before the top_n cut
  returned: 10,               # rows actually returned
  rows: [
    { supplier: "Acme",   total_spend: 482000, invoice_count: 31 },
    { supplier: "Globex", total_spend: 391500, invoice_count: 22 },
    ...
  ]
}
```
- `total_suppliers` vs `returned` preserves truncation honesty (the
  feature 4/5 theme): the synthesizer can say "top 10 of 47" instead of
  implying 10 is all there are.
- `invoice_count` is cheap to compute while summing and gives useful context.
- The output is fully self-describing — everything the synthesizer needs to
  phrase an honest sentence is present. This is what makes deferring the
  synthesizer (§5) safe.

**Empty result**
- Zero matching invoices returns a well-formed empty ranking
  (`total_suppliers: 0`, `returned: 0`, `rows: []`) — never an error. The
  synthesizer later phrases "no invoices in that range." Closing this at the
  tool level (not the synthesizer) keeps the deferral in §5 safe.

---

## 4. Intent vocabulary and routing

**Vocabulary.** The aggregation Intent carries `group_by`, the measure (implied
by the chosen tool, not a free field), the date range, and `top_n` — enough for
the planner to map deterministically to the tool.

**Who reads the prompt signal.** The *parser* (the LLM), never the planner. The
planner has no language understanding by design; it only maps structured Intent
to a tool. So the parser must already have turned "top 10 by spend" into
structured aggregation vocabulary.

**Routing decision**
- Aggregation signal present (e.g. "top", "by", "total", "how many") →
  aggregation Intent → planner routes to the matching `aggregate_*` tool.
- No signal, or ambiguous (e.g. bare "suppliers in Q1 2026") → **default to
  list.** List is the safer, cheaper, more common shape; aggregation is the
  rarer ask, so defaulting away from it rarely surprises anyone. Refusing a
  perfectly answerable list prompt would be too aggressive.

---

## 5. Synthesizer: deferred (deliberately)

The synthesizer phrasing layer is **not** designed here. It is deferred until
all aggregation prompt shapes are settled, so it can be written once against the
full set of shapes rather than piecemeal per tool.

This deferral is safe **only because** the tool output is fully self-describing
(§3): no honest sentence the synthesizer needs to write later is made impossible
by missing data. When the synthesizer is built, it gets a schema branch keyed on
`shape` (parallel to feature 5's per-entity schemas) — an aggregation result is
a ranking with metadata, not a row set, so it needs its own branch. It should
phrase the ranking, the date range, the "top N of M" truncation, and the empty
case.

---

## 6. Boundedness rule (what keeps this from becoming an engine)

The roadmap says "specific tools per shape, not a generic engine." Made
concrete and applicable:

- A new aggregation shape = a **new named tool**, added demand-driven, not built
  ahead.
- Each tool fixes its grouping and its measure as part of its identity.
- **The line:** parameters may shape the *input and output size* (date range,
  `top_n`) but never the *operation* (grouping, measure). Adding a `group_by` or
  `measure` parameter to an existing tool is exactly the move that turns N tools
  into one engine — forbidden.

**Naming convention.** Aggregation tools are prefixed `aggregate_`
(`aggregate_invoices_by_supplier`, future `aggregate_spend_by_buyer`, …). This
is a *convention*, not a safety guard: it gives the parser a predictable pattern
to emit and makes the code readable, which lowers the chance of a malformed
name. It does **not** prevent hallucination. The actual hallucination defense is
KG-menu validation — a tool name the parser emits must resolve to a tool
declared in the KG menu, or it falls to graceful refusal (feature 8). That guard
works regardless of naming; the prefix just makes correct names more likely.

---

## 7. Same data, different operation

`search_invoices` (list) and `aggregate_invoices_by_supplier` (aggregate) read
the **same** invoice source in Fusion. The difference is the operation, not the
data: the list tool returns rows, the aggregation tool sums them. Both push the
date filter down to the same source and read only in-range rows. Aggregation
does not fork or duplicate the data layer.

---

## 8. Decisions log (so they are not re-litigated)

1. Aggregation is a tool the planner routes to — not a pipeline branch, not an
   engine.
2. Measure and grouping are fixed per tool, never parameters.
3. Tie at the `top_n` boundary → cut at exactly `top_n`, name-ascending
   tiebreaker for determinism.
4. Empty result → well-formed empty ranking at the tool level, not an error.
5. Routing signal is parser-read; ambiguous prompts default to list.
6. Synthesizer phrasing deferred until all shapes are settled; safe because tool
   output is self-describing.
7. `aggregate_` prefix is a convention for readability/parser-predictability;
   KG-menu validation is the hallucination defense.

---

## 9. Open / out of scope for this design

- Synthesizer phrasing (deferred, §5).
- Tool #2 and beyond — defined by demand, per the boundedness rule (§6).
- Unchanged by this design: feature 6 (contracts) and the carried loose ends in
  the handoff (agent removal, cosmetic refusal noun, password rotation).

*End of design doc.*

---

<!-- ============================================================ -->
<!-- SECTION 7 — KG Evaluation Framework (frozen record, from kg_evaluation_framework.md) -->
<!-- ============================================================ -->

# KG Evaluation Framework

**Phase:** Dynamic Orchestration 03 — KG Population (framework doc)
**Status:** Design document — implementation lives in phases 08 and 09
**Purpose:** Define how Track B's success or failure will be measured, and how we will iterate if results are weak.

This document is locked in *before* phases 04–07 implement the agent-KG integration, so the test bar isn't moved to match the result. The discipline matters: if we write the rubric after seeing the score, the result means less.

Companion docs:
- `kg_schema_v1.md` — what the KG models
- `../phase_a5_baseline_report.md` — Track A baseline this is measured against
- `../spire_poc_log.md` — running log

---

## 1. Why This Framework Exists

The POC's central claim is that a Knowledge Graph helps an LLM agent reason about Fusion better than tool descriptions alone. That claim has to be testable, or it isn't a real claim.

Track A's baseline (`phase_a5_baseline_report.md`) measured 1/7 on the reference prompt across 5 runs. That's the comparison point. The question this framework answers: **how much better must Track B do, and how do we know the KG is what made it better — rather than incidental changes (different prompts, different model behavior, lucky day)?**

Three things must be true for Track B to count as validating the KG hypothesis:

1. Track B scores meaningfully higher than Track A on the same rubric.
2. The improvement is attributable to the KG (not to other changes).
3. The agent is actually using the KG (not ignoring it while still scoring well via other means).

Each gets its own tier below.

---

## 2. Tier 1 — Headline Measurement (Phase 08)

The headline number is "what score does Track B's agent get on the same reference prompt under the same rubric?"

### Protocol

Replicates the phase A.5 protocol exactly. Discipline matters more than ceremony.

- **Same reference prompt, unchanged:**
  > Show me suppliers in US with no invoices in 6 months but with open purchase orders, including the buyer assigned to each.
- **Same 7-step rubric**, scored ✅ / ⚠️ / ❌ per step
- **5 runs**, same prompt each time
- **No prompt engineering, no retries with corrections, no tool-description tweaks**
- **No mid-test fixes** — if a tool breaks, we record the failure and continue; we don't patch it between runs
- **Same scoring rules** — a run scores against the rubric as it actually ran, not as it could have run

### Bands of meaning

These bands are committed to *now*, before the runs. The point is to make the result interpretable without post-hoc rationalization.

| Aggregate score (best of 5 per rubric row) | What it means |
|---|---|
| **1/7 or 2/7** | KG didn't help. Track B failed to beat the baseline. Hypothesis as stated did not hold. Honest write-up required: what specifically didn't work, what we'd try differently, whether further investment is warranted. |
| **3/7 to 4/7** | Partial improvement. KG helped on some clauses, not others. Per-clause dissection required: which rubric rows improved and why, which didn't and why not. |
| **5/7 to 6/7** | Material improvement. Hypothesis validated at POC scale. Proceed to ablation (Tier 2) to confirm attribution. |
| **7/7 across 5 runs** | Strong validation, but suspicious. Inspect carefully for accidental help (system-prompt drift, tools modified mid-development, prompt loosened). If holds up, validated. |

### What "honest write-up" looks like for low scores

If Track B scores 1/7 or 2/7, the temptation will be to find reasons it "almost worked" or to claim "the agent would have done better if X." This temptation must be resisted in writing.

The phase 08 / phase 09 reports must:

- State the score plainly in the first paragraph
- Walk through each rubric row and what the agent actually did vs what was needed
- Identify the specific failure modes (mirroring how A.5 did this — premature termination, parameter confusion, error recovery)
- *Not* claim partial credit beyond what the rubric supports
- *Not* propose fixes-and-rerun until the honest read is captured

The honest read is the deliverable. The fixes can come after, on a different branch.

---

## 3. Tier 2 — Ablation (Phase 09)

The headline measurement answers "did Track B do better?" It doesn't answer "did the **KG** do it?"

### The ablation test

After the Tier 1 runs complete and the headline score is recorded, run a second batch of 5 runs with the **same Track B codebase but with KG-consultation disabled**.

Two ways to disable, depending on how phase 05 wired things in:
- **If KG queries are exposed as MCP tools the agent can choose**: remove them from the tool list passed to the LLM. Same code path, but the agent can't reach the KG.
- **If KG queries are baked into the planning step**: bypass that step; pass the raw prompt and tool list directly, the way Track A did.

Either way, the agent must lose access to the KG without other changes — same model, same tools (minus KG), same system prompt structure.

### Interpreting the ablation

| Tier 1 score | Ablation score | Interpretation |
|---|---|---|
| 5/7 | 5/7 | KG didn't matter. Improvement came from elsewhere (system prompt, tool descriptions, parameter unification, etc.). **The KG hypothesis fails even though Track B "won."** This is the most important honesty test. |
| 5/7 | 3/7 | KG helped meaningfully. The 2-point delta is the KG's contribution. |
| 5/7 | 1/7 | KG was the difference. The full Track B win is attributable to the KG. |
| 1/7 | 1/7 | KG didn't help; ablation confirms. Consistent failure. |
| 2/7 | 5/7 | KG made things *worse*. Possible if the KG misled the agent. Worth investigating; doesn't necessarily kill the architecture, but signals a v1.1 redesign. |

The ablation cost is one extra evaluation phase — maybe 30 minutes of run time plus an hour of write-up. It's the single cheapest insurance against shipping an overstated POC result.

### Confounders to be honest about

The ablation isn't perfect. Even with KG disabled, Track B's agent may have inherited:

- Better tool descriptions written during phase 04 work
- A more sophisticated system prompt
- Better parameter unification across tools
- Generally better engineering hygiene that accumulated through Track B's phases

If the ablation score is markedly better than A.5's 1/7, **those other improvements are doing real work** and should be named in the write-up. The KG's contribution is the *delta* between Tier 1 and Tier 2, not the absolute Tier 2 score.

---

## 4. Tier 3 — Failure-Mode Audit

A score isn't enough on its own. Three behavioral questions need affirmative answers for the result to be trustworthy.

### 4.1 Did the agent actually consult the KG?

Inspect the phase 08 trace files. For each run, count:
- Number of KG-related tool calls (or KG queries, depending on phase 05's design)
- At what step in the reasoning chain they occurred
- Whether their results influenced subsequent tool calls

**Pass condition:** every successful Tier 1 run made at least one KG consultation that demonstrably influenced a later Fusion call. Example: KG consulted, returned that "open PO" means `StatusCode='OPEN'`, agent then called `search_purchase_orders(status='OPEN')`.

**Failure mode caught here:** agent scores 5/7 but never consulted the KG. The headline number "validates" the KG architecture but in reality the LLM solved it from docstrings (somehow). Not a real validation.

### 4.2 Did the KG mislead the agent in any run?

For each KG consultation, verify the response was correct:
- Did the join key returned by the KG match what Fusion's endpoint actually expects?
- Did the vocabulary lookup map to a real Fusion code?
- Did the pattern definition's mechanics, if followed literally, produce a valid call?

**Pass condition:** zero misleading KG responses in the 5 runs. Or, if misleads occurred, they are catalogued and a v1.1 schema update is identified to fix each.

**Failure mode caught here:** the KG returned wrong/stale info, the agent dutifully followed it, the run failed. This is the most painful failure mode because the agent did the right thing and the KG was the bug. Documenting these is how the KG improves.

### 4.3 Did the KG cost more than it gained?

Compare Tier 1 traces against A.5 traces on three dimensions:
- **Tool call count** — how many calls did the agent make per run?
- **Token usage** — total tokens in/out (approximate from message lengths)
- **Wall-clock time** — from `agent_started` to `agent_finished` in the trace

**Pass condition:** Track B uses at most ~2x the Track A budget on any dimension for an equivalent answer. (Track B *should* use more — that's the point — but not 5x more for a 1-step improvement.)

**Failure mode caught here:** the "compounding intelligence" claim in `spire_design_alternatives.md` is weakened if every KG consultation adds three LLM turns. If Tier 1 takes 30 tool calls to pass 5 rubric rows where A.5 took 5 calls to pass 1, that's a different story than "KG made the agent smarter."

---

## 5. The Iteration Loop

If Tier 1 + Tier 2 + Tier 3 don't all pass, the POC isn't done. The framework is:

1. **Diagnose.** Which of the three tiers failed, and on which specific rubric row or behavioral question?
2. **Localize.** Is the gap in (a) the schema (v1.1 needs more), (b) the query tools (phase 04 missed something), or (c) the integration (phase 05 didn't wire the KG in well enough)?
3. **Smallest change that addresses the diagnosis.** Don't redesign everything.
4. **Re-run.** Both Tier 1 and Tier 2, with the same discipline.
5. **Time-box.** Allow at most three iteration cycles before declaring the POC's result whatever it is.

The time-box matters. Without it, the temptation is to iterate until results look good, which destroys the meaning of the measurement.

### What a v1.1 schema change might look like

If diagnosis says "the `cross_pillar_lookup` pattern was misleading — the agent confused source and target entities" — v1.1 might:
- Drop the pattern; expand the `ASSIGNED_TO` edge's `notes` field instead
- Or restructure the pattern's `parameters` JSON to make source/target unambiguous
- Or add a worked example to the `example` field

Whichever change is made, the schema doc gets updated (don't fork), the seed SQL gets a new revision (e.g. `sql/kg/v2/`), and the v1 schema is preserved as historical record.

### What a phase 04 change might look like

If diagnosis says "the query tools returned KG data in a format the LLM couldn't parse" — phase 04's tool surface gets revised. Same KG content, different tool shape.

### What a phase 05 change might look like

If diagnosis says "the agent had access to KG tools but never called them" — the integration is wrong. System prompt may need to direct attention to the KG, or KG tools may need to be called proactively at planning time before the agent decides what Fusion tools to use.

---

## 6. What This Framework Does NOT Promise

Honest scoping of the framework's limits:

- **It does not predict generalization.** Track B passing the reference prompt does not mean it would pass an arbitrary Fusion question. The POC is sized to one prompt deliberately.
- **It does not control for LLM variance.** Five runs sample the model's variability for one prompt; a different model or a different day might score differently. Documented but not eliminated.
- **It does not measure user satisfaction.** No human-rated quality scores. The rubric is mechanical.
- **It does not measure latency at production scale.** Tier 3's wall-clock dimension is informational, not a SLA test.
- **It does not validate the architecture for multi-tenant production.** That's a separate question; see `spire_design_alternatives.md` for the scope boundary.

---

## 7. Deliverables

What the evaluation phases must produce:

| Phase | Deliverable | Source of truth |
|---|---|---|
| 08 | `docs/phase_08_track_b_results.md` | 5 trace files + per-run rubric scoring |
| 09 | `docs/phase_09_comparative_results.md` | A.5 vs phase 08 (Tier 1) vs phase 08-ablation (Tier 2) side-by-side; Tier 3 audit results |
| 09 | Updated comparison table in `spire_design_alternatives.md` §6 — measured baselines for both tracks |
| 09 (if iteration occurred) | Iteration history: what changed, why, what the re-run showed |

Each deliverable cites trace files by path so the result is reproducible from the artifacts.

---

## 8. Summary

The KG is not assumed to work. It is required to:

1. Score meaningfully higher than 1/7 on the reference prompt (Tier 1)
2. Cause that improvement attributably (Tier 2 ablation)
3. Behave honestly along the way (Tier 3 audit)

If any tier fails, we iterate within a time-box. If iteration doesn't close the gap, the POC reports an honest negative result — and that is a successful POC outcome, not a failure. A POC that can't say "the architecture didn't work" can't say "the architecture worked" either.

---

<!-- ============================================================ -->
<!-- SECTION 8 — Design 3 v1.1 → Production Roadmap (frozen record, from design3_v1_to_production_roadmap.md) -->
<!-- ============================================================ -->

# Design 3 v1.1 → Production Roadmap

**Date:** 2026-05-26
**Author:** Bhagavan (with Claude)
**Status:** Plan — not yet executed. Phase A is the first piece of
work. Phases B-F lock the order and shape; their internal details
are sketched here but should be re-confirmed at the start of each
phase based on what earlier phases revealed.

---

## Where we are starting from

Master is at commit `6b8979d`. Design 3 v1.1 scores 7/7 on the
original Track A prompt across three runs (see
`docs/design3_measurement_report.md`).

What works:
- KG-driven deterministic planner (102 unit tests)
- Plan executor against 5 MCP tools, including negation-by-absence
  (45 unit + 3 integration tests)
- LLM-based structured-output synthesizer with hallucination guard
  (22 unit + 1 integration tests)
- End-to-end script `scripts/run_plan.py` with `--intent` arg

What is hardcoded (and limits the system):
- The Intent itself (no natural-language parser — caller hands the
  parsed Intent to `run_plan.py` via `--intent` choice)
- The synthesizer schema (`SynthesizedResponse` is specific to the
  "suppliers + buyers" answer shape)
- All filter-type → KG-pattern mappings live in Python constants in
  `planner.py`, not in the KG

What is unmeasured:
- Anything other than the one Track A prompt
- Performance under any non-trivial workload
- Behavior on intentionally adversarial or out-of-scope prompts

---

## The roadmap at a glance

| Phase | What | Why this order | Size estimate | Done when |
|---|---|---|---|---|
| **A** | Gap analysis on diverse prompts | Cheapest, highest signal; shapes B–E | Half day | Gap document committed; sized list of fixes |
| **B** | Schema generalization (synthesizer) | Unblocks C (parser needs to know answer shapes) | 2-3 days | Synthesizer accepts intent-derived schema; tests prove ≥2 distinct answer shapes work |
| **C** | LLM intent parser | Top of pipeline, the last hardcoding | 3-4 days | NL prompt → Intent works for ≥3 prompt classes; ≥1 integration test per class |
| **D** | Re-validate against Phase A prompts | Real generalization test | 1-2 days | All Phase A prompts run end-to-end; rubric-style score per prompt; report committed |
| **E** | Production hygiene | After we know real workload shape | 3-5 days | Parallelization + caching + observability + error hardening; perf report |
| **F** | Handoff documentation | Last; can only be true once E lands | 1-2 days | Architecture doc + runbook + decision log committed |

**Total: roughly 2-3 weeks of focused work.** Each phase has explicit
approval gates; we don't proceed to phase N+1 without finishing N.

---

## Phase A — Gap analysis on diverse prompts

### Goal

Pick a small set of deliberately diverse prompts and walk each one
through the system *as it stands today*. Catalog what raises, what
silently does the wrong thing, what's missing, and what would need
to be built to handle it.

**Do not build fixes during Phase A.** Just measure and document.
Fixing the gaps is what Phases B-E are for.

### Why this comes first

Without Phase A, we'd plan B-E based on guesses about what's
needed. With Phase A, we plan B-E based on what we actually saw
fail. F1 was a perfect example: we couldn't even *see* the silent-
drop defect until we tried to measure the system honestly. Phase A
is the same idea at a larger scope.

### Sub-tasks

**A.1** — Pick 5-7 prompts spanning these categories:
- One that's essentially the Track A prompt with one variable
  changed (e.g., country=UK instead of US). Tests vocabulary
  expansion.
- One with a different `target_entity` (e.g., "show me POs over
  $100k with their supplier and buyer"). Tests whether the planner
  can pivot away from Supplier as the root.
- One with no negation (e.g., "list all suppliers in India"). Tests
  simpler intents still work.
- One with multiple negations (e.g., "suppliers in US with no
  invoices in 6 months AND no POs in 3 months"). Tests pattern
  composition.
- One whose answer shape is fundamentally different (e.g., "what's
  the total open PO value by buyer?" — aggregations, no per-supplier
  output). Tests synthesizer schema limits.
- One deliberately out of scope (e.g., "show me the contract
  renewals due next quarter"). Tests honest "I can't do this" path.
- One ambiguous (e.g., "who's our best supplier?"). Tests how the
  system handles vagueness.

Approval gate: locked prompt list before any measurement runs.

**A.2** — For each prompt, manually construct the `Intent` that the
LLM parser would (eventually) produce. Document why this is the
"right" Intent — capture the reasoning so Phase C's parser can be
held to the same standard.

Approval gate: Intent list reviewed.

**A.3** — For each Intent, attempt to run it via `scripts/run_plan.py`
(extended to take an inline Intent — small CLI tweak). Capture:
- Did the planner accept the Intent? (F1 means unknowns raise.)
- Did the executor run? Counts at each step?
- Did the synthesizer produce a structured response? Or did the
  hardcoded schema break?
- Hallucination guard fire?
- Wall-clock time?

If a step raises, log the raise and move on — do NOT debug or fix
in Phase A.

**A.4** — Write `docs/design3_gap_analysis.md`. One section per
prompt. Each section names: the prompt, the constructed Intent,
the actual behavior, the gap classification (one of: missing-KG-
pattern, missing-filter-type, missing-mcp-tool, schema-too-narrow,
needs-intent-parser, genuinely-out-of-scope), and the rough size of
the fix.

Approval gate: gap analysis reviewed; categorized fixes inform
Phase B and C scope.

### Done criteria

- 5-7 prompts captured with their Intents
- Each run end-to-end (or failure documented honestly)
- Gap analysis doc committed to `docs/`
- A categorized list of fixes that Phases B-E should address

### Size

**Half day** of focused work. Most of the time is in choosing good
prompts and writing the analysis. The runs themselves are 2-3
minutes each.

### Dependencies

None. Can start immediately on master.

### Honest risks

- **The prompts I list above might miss the real failure modes.**
  If you have prompts your consultants actually ask, those should
  replace some of mine. The list above is "Claude's guess at
  diverse"; user-sourced prompts beat any guess.
- **Out-of-scope handling might be terrible.** Today the planner
  raises NotImplementedError; the script catches it but the user
  experience is bad. Phase A documents this; Phases B-E may or may
  not fix it depending on priority.

---

## Phase B — Schema generalization (synthesizer)

### Goal

Replace the hardcoded `SynthesizedResponse` schema with one that's
derived from the Intent's target entity (and possibly its includes).
Make the synthesizer support at least two distinct answer shapes
without code changes per shape.

### Why this order

- Phase A surfaces what answer shapes are actually needed.
- Phase C (intent parser) will produce more shapes than the current
  schema can hold; without Phase B, the parser is blocked by the
  schema.
- Generalizing the schema *before* generalizing the input means we
  can test schema flexibility against the existing planner+executor
  without also debugging a new parser at the same time.

### Sub-tasks

(Detailed plan to be drafted at the start of Phase B based on what
Phase A revealed about the needed shapes. Sketch follows.)

**B.1** — Decide the parameterization model:
- Option (a): per-target-entity schemas (Supplier → SupplierAnswer,
  PurchaseOrder → POAnswer, etc.) Registry pattern.
- Option (b): one fully-generic schema that just nests rows and
  fields. Synthesizer infers what to highlight.
- Option (c): schema is generated dynamically from the Intent's
  target entity + the executor's actual output keys. No registry.

Each option has different tradeoffs in fidelity vs. flexibility.
Decision made AT START of Phase B, not now.

**B.2** — Refactor `src/spire/synthesizer/synthesizer.py`:
- Schema selection layer (based on B.1's decision)
- Update `_collect_valid_ids` to be schema-aware
- Update `_validate_no_hallucinated_ids` to handle multiple schema
  shapes
- System prompt construction parameterized per schema

**B.3** — Move `BuyerInfo` / `SupplierSummary` into a per-shape
module. Add at least one new shape (the one Phase A told us we
need most).

**B.4** — Tests:
- Existing 22 synthesizer tests should still pass (the Supplier
  shape continues to work)
- ≥10 new tests for the new shape (mirroring the existing test
  structure: schema validation, hallucination guard for the new
  ID types, end-to-end with mocked LLM)
- Integration test that the new shape works against live Gemini

**B.5** — Update `run_plan.py` to wire the right schema based on
intent.

### Done criteria

- Synthesizer handles ≥2 distinct answer shapes
- All existing tests still pass
- New tests for the new shape pass
- Integration test against live Gemini for the new shape passes
- The 7/7 measurement on the Track A prompt still reproduces (no
  regression)

### Size

**2-3 days.** Most of the time is in B.1 (deciding the
parameterization model) and B.4 (tests). The actual refactor is
small (~200 lines).

### Dependencies

- Phase A complete (we need to know which second shape to build)

### Honest risks

- **Choice in B.1 is irreversible-ish.** Picking (a) means we add
  schemas one at a time forever; picking (b) means the synthesizer
  is less specific; picking (c) means generation logic is complex.
  This is the biggest decision in the roadmap. Plan to review
  thoroughly at start of B.
- **Hallucination guard generalization is non-trivial.** Today it
  knows about SupplierId, SupplierNumber, PersonId. Different
  schemas reference different ID types. The validator needs to
  know the universe per schema, not globally.

---

## Phase C — LLM intent parser

### Goal

Build the natural-language → `Intent` layer. Until now, the user
provides the parsed Intent via `--intent` flag or via API. Phase C
puts the LLM at the top: user types English, system produces a
validated Intent.

### Why this order

- Phase B generalized the output side; Phase C generalizes the
  input side. Doing them in this order means each phase has a
  stable thing on the other side to test against.
- Doing C before B would mean every new Intent the parser produces
  immediately breaks the synthesizer's hardcoded schema. We'd build
  C twice.

### Sub-tasks

**C.1** — Design the parser's contract:
- Input: a natural-language prompt (string)
- Output: an `Intent` (the existing dataclass)
- Failure modes: ambiguous prompt, out-of-scope prompt, malformed
  filters
- Validation: the parser's output goes through
  `_validate_intent_filters` before reaching the planner

**C.2** — Build `src/spire/intent_parser/intent_parser.py`:
- Pydantic-typed structured output (same pattern as synthesizer)
- System prompt enumerates the valid filter types and their value
  shapes (read from the planner's mapping tables)
- Returns Intent or raises a clear error

**C.3** — Handle ambiguity. Three options to evaluate at start of
phase C:
- Reject ambiguous prompts and ask the user to clarify
- Make a best-guess Intent + flag confidence
- Generate multiple candidate Intents and ask the user to pick
The choice will probably depend on what Phase A revealed about
ambiguity in real prompts.

**C.4** — Tests:
- Unit tests with mocked LLM (similar shape to synthesizer tests)
- Integration tests against live Gemini for each of the Phase A
  prompt categories
- Regression test: the Phase A constructed Intents are reproduced
  by the parser from the corresponding prompts (within reason —
  some variation is acceptable)

**C.5** — Update `run_plan.py` (or add a new `scripts/ask.py`-style
entry point) that takes a natural-language prompt.

### Done criteria

- Parser produces Intents for ≥3 prompt classes from Phase A
- Each class has ≥1 integration test against live Gemini
- Existing pipeline (planner → executor → synthesizer) unchanged;
  parser is purely additive at the top
- 7/7 measurement on Track A prompt still reproduces, now starting
  from the natural-language prompt instead of a hardcoded Intent

### Size

**3-4 days.** Bigger than B because parsing is harder than
synthesis (more ambiguity, more failure modes, more LLM behavior
to validate).

### Dependencies

- Phase B complete (synthesizer can handle the answer shapes that
  the parser will produce intents for)

### Honest risks

- **Ambiguity handling is genuinely hard.** Even with a clear KG
  vocabulary, real prompts use words the KG doesn't cover. The
  parser needs to either expand the vocabulary or honestly say
  "I don't know what 'best supplier' means; can you clarify?"
- **Two LLM calls per request now.** Latency and cost both up.
  Phase E will need to consider whether the parser can be skipped
  for already-structured inputs (API callers don't need NL parsing).

---

## Phase D — Re-validate against Phase A prompts

### Goal

Run the Phase A prompts through the *full* pipeline (parser →
planner → executor → flexible synthesizer) and produce a
generalization report.

This is the real "does Design 3 v1.2 work on more than one prompt"
measurement.

### Sub-tasks

**D.1** — Re-run each Phase A prompt end-to-end. For prompts that
needed new KG patterns / new MCP tools / new schemas to support,
land those fixes first (decided at start of D based on Phase A's
categorized gap list).

**D.2** — Score each prompt against a per-prompt rubric. Same shape
as the Track A rubric, adapted per prompt. Each row asks "did the
right tool get called for the right reason" and "is the final
answer coherent."

**D.3** — Write `docs/design3_generalization_report.md`. One
section per prompt, with the score, the failure modes if any, and
a comparison to the corresponding Phase A "before" measurement.

**D.4** — Honest summary: across N prompts, system achieved ≥X/Y on
M prompts; ≥X/Y on K prompts with caveats; failed on (N-M-K)
prompts because of (reasons). No averaging into a single percentage
(meaningless for prompts of different shapes); per-prompt scores
side by side.

### Done criteria

- Generalization report committed
- For each Phase A prompt, a real measurement result (not a guess)
- Phase A's categorized gap list crossed off (each gap either fixed
  or explicitly deferred with reason)
- Anything that's still broken is documented honestly

### Size

**1-2 days** for the runs and the report. Plus however long the
gap fixes from D.1 take — likely another 2-5 days depending on
what Phase A revealed.

### Dependencies

- Phases A, B, C complete

### Honest risks

- **D.1 is the open-ended part.** "Land the fixes Phase A surfaced"
  could be small (a few KG rows) or large (new MCP tools, new
  executor capabilities). Phase A's sizing will tell us.
- **The generalization report might show real architectural limits.**
  E.g., maybe the planner's three-block structure doesn't fit
  aggregation prompts. If so, we'd surface that honestly and decide
  whether to extend it or call it scope.

---

## Phase E — Production hygiene

### Goal

Make the system handle real production characteristics: latency,
throughput, observability, error recovery.

The 125-second per-run wall-clock from the v1.1 measurement is fine
for a POC; not fine for production.

### Sub-tasks

(Sketch only. Final scope locked at start of Phase E based on what
Phases A and D revealed about workload shape.)

**E.1** — Parallelize iteration steps in the executor:
- `_execute_iterating_step` currently sequential
- `_execute_filter_source_step` currently sequential
- Both should support `asyncio.gather` over per-iteration calls
- Concurrency cap (don't hammer Fusion); start conservative (5?)
- Tests: mocked-MCP correctness under parallelism + load test
  against live Fusion to find the safe concurrency

**E.2** — Add request-level caching:
- Same query against same Fusion endpoint, same args, within same
  run → don't re-fetch
- KG lookups can be cached for the lifetime of the process
- Cache hit/miss metrics in the trace

**E.3** — Observability:
- Per-step latency in trace events
- Tool call counts per Fusion endpoint
- LLM call counts and token usage
- Synthesizer hallucination-guard fire rate

**E.4** — Error hardening:
- Fusion 5xx responses should retry with backoff (not just fail
  the whole plan)
- LLM rate-limit errors should retry
- Partial-result mode? (Today: fail-the-whole-plan; production may
  want "return what we have plus a warning")

**E.5** — Performance measurement: re-run Phase D prompts after
parallelization. Report the latency improvement (and any
correctness regressions if Fusion's rate-limit behavior surfaced).

### Done criteria

- Parallelization safely lands; Track A 7/7 measurement still
  reproduces
- Per-run latency drops measurably (target: <30s for the original
  Track A prompt; subject to Fusion's rate limits)
- Observability metrics visible in traces
- Error-handling decisions documented (retry policy, partial-result
  policy)
- Performance report committed

### Size

**3-5 days.** Highly dependent on what Fusion's rate limits and
error behavior actually look like under load.

### Dependencies

- Phases A, B, C, D complete

### Honest risks

- **Parallelization changes the executor's semantics subtly.** If
  Fusion has rate limits we haven't seen, parallelism reveals them.
  The "fail-the-whole-plan" policy may need to relax.
- **Concurrency cap is a guess until we measure.** Start
  conservative; tune up while monitoring 429s and 5xxs.
- **Caching breaks reproducibility.** A cached result is stale data
  in some sense. Trace metadata needs to make cache hits obvious.

---

## Phase F — Handoff documentation

### Goal

Write the architecture-level documentation that lets someone else
pick this up, extend it, or hand it to a customer.

### Sub-tasks

**F.1** — Architecture overview: one diagram + 2-3 pages of prose.
What's the data flow, where do decisions get made, where are the
extension points.

**F.2** — Decision log: a chronological record of the architectural
calls made across Track A → Design 3 v1.0 → v1.1 → v1.2 → production.
Each entry: what was decided, why, what alternatives were
considered, what we'd revisit.

**F.3** — Runbook: how to add a new MCP tool, how to add a new KG
pattern, how to add a new filter type, how to add a new answer
schema. Each as a worked example.

**F.4** — Performance characteristics: from Phase E, what does the
system actually do under load. Latency, throughput, cost (LLM
tokens), Fusion call counts per typical query.

**F.5** — Known limits: things the system can't do or does badly,
honestly enumerated. Includes the things we deferred during this
roadmap.

### Done criteria

- Documents committed to `docs/`
- A walkthrough: someone reading the docs cold should be able to
  understand the system, run it, and make a small extension
  without needing to read the source first

### Size

**1-2 days.** Writing time. The content is what we know by the end
of Phase E.

### Dependencies

- Phases A through E complete

### Honest risks

- **Documentation rots.** What's true at the end of Phase F won't
  be true in 3 months unless someone maintains it. The runbook is
  the most likely thing to rot first.

---

## What this roadmap does NOT include

Things explicitly out of scope, so we don't accidentally creep:

- **Multi-tenant / multi-pod support.** Today personas.yaml has one
  pod. Production might need many. Out of scope for now.
- **Auth / authorization beyond what the MCP tools already do.**
  Today: basic auth, single user. Out of scope.
- **A UI.** The system stays CLI/API-driven. UI is a separate
  workstream.
- **Comparison against Track A on broader prompts.** Track A
  remains at 1/7 on its one prompt; we're not re-measuring it
  across the Phase A prompt set. Different architecture; the
  comparison would be misleading.
- **Cost optimization.** Gemini Flash is cheap and current usage
  is small. Worth re-visiting if production usage scales 100×.

---

## Working agreements for executing this roadmap

Same as F1-F4:

- Approval gates at the start of each phase AND before any code
  generation within a phase
- Each phase lands on its own branch + PR, the way F1/F2/F3 did
- Honest framing throughout: what we did, what we didn't, what we
  don't know
- Small checkpoints; do not generate 1000-line files without
  approving the scope first
- If a phase reveals that a later phase's plan needs to change,
  pause and re-plan rather than barrel ahead

---

## Open questions to lock before starting Phase A

1. **The Phase A prompt list.** I've sketched 7 prompts. Do you
   want to replace any with prompts your consultants actually ask?
   User-sourced beats Claude-sourced for this.

2. **Phase A timing.** Half a day if focused. Want to start now,
   or close out the F-track first (the housekeeping items I flagged
   after F3 merged: stale SQL files, README update, log update,
   merged-branch cleanup)?

3. **Granularity of approval gates.** F1-F4 used "approve scope
   before generation, then run + share output." Want to keep that,
   or tighten / loosen?
