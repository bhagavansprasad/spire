# Knowledge Graph POC — Scoping & Alignment

> **For:** Oracle Fusion SME 
> **Purpose:** Align on what a Knowledge Graph (KG) can and cannot do for our agent before we build a POC. 
> **Audience note:** Assumes deep Fusion expertise, no prior KG background. Analogies (subway/train system) are used throughout to make KG concepts concrete. 
> **Companion doc:** `spire_fusion_endpoints_reference.md` (endpoint signatures, quirks, join keys) and `kg-poc-phased-plan.md` (execution plan).

---

## Context

We're scoping a POC to evaluate **Oracle 26ai's Knowledge Graph (PGQ)** for an agent that queries Oracle Fusion via REST. The existing Spire agent (LLM-driven orchestration over 5 AP endpoints) is unstable — for the reference prompt below, it variably executes 1–59 endpoint calls depending on the run. We want to test whether a metadata-only KG can make planning deterministic.

**Reference prompt the POC is built around:**

> *"Show me suppliers in US with no invoices in 6 months but with open purchase orders, including the buyer assigned to each."*

---

## Hard constraints (already established)

1. **Source of truth is Oracle Fusion REST.** The 26ai database never caches, copies, or syncs Fusion data.
2. **The KG holds metadata only** — entity types, edge declarations, query patterns, vocabulary. Never instance data.
3. **Fusion data is fetched only via REST tool calls at query time;** results are used and discarded.

---

## What we're trying to understand: what KG can do better than LLM-driven orchestration

The existing Spire agent uses an LLM to decide which endpoints to call, in what order, with what IDs. That's the step we're replacing with KG-driven planning. The candidate benefits:

1. **Deterministic multi-hop plan synthesis** — given a question requiring several REST calls with ID handoffs, PGQ traverses the metadata graph and emits an ordered, executable plan. Same question, same plan, every time. No hallucinated endpoints, no wrong join order, no 1-vs-59 calls.
2. **Feasibility checking before execution** — PGQ can determine upfront whether a question is answerable with the available endpoints, and fail fast with a precise reason if not.
3. **Vocabulary grounding and disambiguation** — mapping user terms ("vendor," "bill," "open") to canonical entities and codes, encoded explicitly in the graph instead of guessed by the LLM.
4. **Query pattern reuse** — common question shapes (e.g., "no Y in N months") become named patterns; PGQ matches the question to a pattern and emits a proven plan instead of re-deriving it.
5. **Explainability and auditability** — every plan is traceable to graph edges, giving a real audit trail rather than an LLM chain-of-thought.
6. **Cost and latency optimization** — when multiple traversal paths exist, PGQ can prefer cheaper ones based on endpoint cost characteristics encoded in the graph.
7. **Schema evolution containment** — Fusion endpoint changes are updated once in the KG; every plan touching affected nodes picks up the new contract.

**Note:** The LLM doesn't disappear from the system. It still parses the user's question into structured input and synthesizes the final natural-language answer. We're replacing only the *planning* step — the part that's currently unstable.

---

## What we have

- **(a)** Oracle 26ai with Knowledge Graph
- **(b)** Oracle Fusion REST endpoint signatures — already documented in `spire_fusion_endpoints_reference.md` (5 endpoints, the AP slice + HCM buyer lookup)
- **(c)** Oracle Fusion table schemas (publicly available)

---

## Our current understanding — please confirm or correct

1. A KG is useful when built from tables, schemas, and their relationships (e.g., Oracle Fusion HCM or Finance modules).
2. A KG may not be useful if built from **only REST endpoint signatures**, without the underlying Fusion tables and their schema.

---

## Questions

- **Q1.** With only (a) and (b), can we build a KG?
- **Q2.** To build a KG, is having (a) and (c) mandatory?

---

# Walkthrough — building intuition before answering

To answer Q1 and Q2 properly, we first need a shared mental model of what a KG actually *is* in our setup. The subway analogy carries us all the way through.

---

## 1. What is a KG, really?

Think of a KG like a **subway map**.

It doesn't tell you who's riding the trains right now (that's instance data — lives in Fusion). It only shows you the **stations and which lines connect them**.

If someone asks *"how do I get from Airport to Museum?"* — the map gives you the route: Airport → Central → Museum, Blue line then Red line.

That's what our KG does for Fusion: it shows entity "stations" (`Supplier`, `Invoice`, `PO`, `Buyer`) and which "lines" (REST endpoints) connect them. The agent uses the map to plan the trip. The actual passengers (data) are fetched from Fusion when needed.

---

## 2. What are the "stations" and "lines" in our KG?

| Subway concept | KG equivalent | Example from our 5 endpoints |
|---|---|---|
| **Stations** | Entity types | `Supplier`, `Invoice`, `PurchaseOrder`, `Buyer`, `Address` |
| **Lines** | Relationships between entities | `Supplier --has--> Invoice`, `Supplier --has--> PO`, `PO --assignedTo--> Buyer`, `Supplier --has--> Address` |
| **Trains running on a line** | REST endpoints | The line `Supplier → Invoice` is serviced by `GET /invoices?q=SupplierNumber=...` |
| **Tickets & signage** | Vocabulary | "vendor" → `Supplier`; "open" → `StatusCode=OPEN`; "US" / "United States" → `Country=US` |

So our KG = **stations + lines + which trains run on them + signage.** All metadata. No passengers.

**Important detail from the endpoint reference:** the *same* line can require *different join keys* depending on which train (endpoint) you're boarding. `Supplier → Invoice` uses `SupplierNumber` (string). `Supplier → PO` uses `SupplierId` (numeric). The KG must encode this per-edge — see `spire_fusion_endpoints_reference.md` for the full asymmetry.

---

## 3. Q1 — Can we build the KG with only (a) + (b)?

**Short answer: Yes.**

**Analogy:** REST endpoints are like **train timetables**. A timetable tells you:
- Which stations exist (`/suppliers`, `/invoices`, `/purchaseOrders`, `/publicWorkers`)
- Which stations connect (`/invoices?q=SupplierNumber=...` → `Supplier` connects to `Invoice`)
- Which direction trains run (GET vs POST)
- What you need to board (required params, join keys)

You can draw the whole subway map from timetables alone. You don't need the city's underground utility blueprints (tables) to know the trains run between these stations.

**What we get:** A map that mirrors exactly what the agent can actually do — because the agent rides trains (REST), not utility tunnels (SQL).

**What we miss:** Connections that exist underground but have no train service. If two entities are related in the tables but no REST endpoint exposes that link, our map won't show it. *But* — our agent couldn't use that link anyway, so it may not matter.

---

## 4. Sub-question — Does missing table relationships reduce KG quality?

**Short answer: Sometimes yes, sometimes no. Depends on whether the missing relationship is *reachable* by our agent.**

**Analogy:** Imagine the subway map misses a tunnel between two stations.

- **Case 1:** No train runs through that tunnel anyway → missing it costs nothing. The agent couldn't have used it.
- **Case 2:** A train *does* run through it, but the timetable described it confusingly (two separate routes that are actually the same tunnel) → now the map has a gap the agent *could* have used. Quality drops.

**For our case:**

REST endpoints expose *most* important relationships — that's their job. But they can hide:
- **Implicit joins** — `Invoice` has `SupplierNumber`, but there's no endpoint that joins client-side; we work around it.
- **Shared reference data** — two endpoints both reference the same lookup, but neither declares so.
- **Same entity, different endpoints** — e.g., the SupplierNumber/SupplierId asymmetry, where one logical "supplier" is identified differently by different APIs.

Table schemas (c) would catch these. So missing (c) does reduce quality — but only on the margin, and only for relationships REST already exposes weakly.

**Rule of thumb:** Build from (b). Use (c) as a **reference to enrich** the map where REST is ambiguous. Don't add anything from (c) that has no REST path — that's a tunnel with no train.

---

## 5. The trap — and the guiding principle

It's tempting to build a "rich, complete" KG from table schemas because they look more authoritative. But every relationship in the KG that has no REST path is a **dead end** — the agent can plan a route to it, then fail when it tries to ride a train that doesn't exist.

**Analogy:** A subway map that shows tunnels with no trains is *worse* than a map that shows only running lines. Passengers (the agent) plan trips that strand them mid-route.

### 🎯 Guiding principle

> **The KG must describe what the agent can *do*, not what the data model *contains*.**

REST is our action surface. The KG should be a faithful map of that surface — no more, no less.

### Practical implication

| Source | Role |
|---|---|
| **(b) REST signatures** | **Primary** — defines what edges exist in the KG |
| **(c) Table schemas** | **Reference only** — used to *clarify* edges already in (b), never to *add* new ones |

So (c) helps us say: *"these two REST endpoints return the same logical entity"* or *"this `SupplierNumber` field is the same supplier referenced by `/suppliers`."* It does **not** earn the right to add a `Supplier → BankAccount` edge if no REST endpoint traverses it.

---

## 6. Q2 — Is (a) + (c) — 26ai + table schemas — mandatory?

**Short answer: No. In fact, (a) + (c) *alone* is the wrong combination.**

**Analogy:** Table schemas without REST is like having the city's **underground utility blueprints** but no train timetables.

You'd know every pipe, cable, and tunnel in the city. Beautiful, complete map. But our agent can't ride pipes — it can only board trains (REST). So a KG built only from (c) would describe a world the agent **can't navigate**.

### Ranking of combinations

| Combination | Verdict | Why |
|---|---|---|
| **(a) + (b)** | ✅ Works | Map matches the agent's action surface |
| **(a) + (b) + (c)** | ✅ Best | (c) refines and disambiguates (b) |
| **(a) + (c) only** | ❌ Wrong shape | Describes data, not actions |
| **(a) only** | ❌ Empty map | No content to encode |

**Takeaway:** (b) is mandatory. (c) is optional and supplementary. The guiding principle holds: *the KG describes what the agent can do.*

---

# Summary

- **What the KG is:** a metadata-only subway map of Fusion entities and the REST endpoints connecting them. Never holds Fusion instance data.
- **Why it's worth doing:** the existing LLM-driven Spire agent variably executes 1–59 calls for the same prompt. KG-driven planning aims to make that deterministic.
- **What to build from:** REST signatures (b) are primary — already documented in `spire_fusion_endpoints_reference.md`. Table schemas (c) are supplementary, used only to clarify ambiguity in (b).
- **The principle to hold:** *the KG describes what the agent can do, not what the data model contains.*

---

# What we need from the Oracle Fusion SME

1. **Confirm or correct** the entity/relationship view above for the 5 endpoints in scope.
2. **Flag REST ambiguities** beyond what's already documented — places where multiple endpoints return the same logical entity, or where a relationship is awkward/hidden in REST.
3. **Identify a few more multi-hop question patterns** real users ask in the AP/Procurement space — to widen the test set beyond the reference prompt.
4. **Highlight endpoints with notable cost characteristics** (pagination behavior, expensive expansions, rate limits) — for the cost-optimization angle in Phase 5.
