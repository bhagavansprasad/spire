# Spire KG Experiment — Context Handoff

**Date:** 2026-05-19
**Owner:** Bhagavan
**Carrying forward to:** a new conversation focused on the property-graph KG experiment

This document is self-contained. Read it before starting work in the new conversation. It carries forward only what's needed for the experiment ahead — not the full Spire history.

---

## What we're trying to do

Build a **standalone proof-of-concept** that demonstrates whether Oracle 26ai's property graph (PGQ) can drive tool selection deterministically for an agent that queries Oracle Fusion REST endpoints.

**Goal:** Prove or disprove that PGQ-driven plan generation outperforms LLM-driven tool orchestration for known query patterns.

**Approach:** Build it outside the main Spire repo first. Small. Focused. Verifiable. If it works, then we integrate into Spire as a real phase.

---

## Hard constraints

These are non-negotiable. The previous conversation established them.

1. **Source of truth is Oracle Fusion REST.** Always. The 26ai database **never** caches, copies, or syncs Fusion data. Not for performance, not for graph queries, not ever.

2. **The KG in 26ai holds metadata only.** Entity *types*, edge *declarations*, query patterns, vocabulary. Never instance data ("Lee Supplies" never appears in the KG).

3. **Fusion data is fetched only via REST tool calls** at query time. The agent calls Fusion; results are used and discarded.

---

## Background: where Spire is today

The main Spire POC has merged through phase 07. State of play:

- **Track A (LLM-only baseline):** 1/7 on the reference prompt across 5 runs. Failed to compose multi-step queries.
- **Track B (LLM + KG as system-prompt text, "B-lite"):** Tested with `gemini-2.0-flash` → 1/5 success. Re-tested with `gemini-2.5-pro` → 5/5 reach 6/7 on the rubric, but with partial answers (agent finds 1-6 of ~6 expected suppliers; never all). Date arithmetic also wrong (model has stale "today" sense).
- **The KG in Spire is currently five flat relational tables** that describe entities/edges/patterns/vocabulary. It is *not* declared as `CREATE PROPERTY GRAPH`. The patterns are prose the LLM reads, not executable templates.

**Honest assessment of B-lite:** The KG was used as documentation, not as a computational structure. The "KG architecture" claim was thinly demonstrated. The model swap (2.0→2.5-pro) was the dominant variable, not the KG.

The new experiment addresses this by building a real property graph and a real pattern executor.

---

## The reference prompt (the only prompt we're testing)

```
Show me suppliers in US with no invoices in 6 months but with open
purchase orders, including the buyer assigned to each.
```

This prompt exercises 4 query patterns:
- `country_filter_via_address` — supplier filtered by country (lives on child address resource)
- `no_Y_in_N_months` — entity with no related entity in time window (negation)
- `status_filter` — entity with attribute value (e.g., status='OPEN')
- `cross_pillar_lookup` — PO buyer is in HCM, not FSCM

---

## Fusion endpoints in scope

All on the demo pod (`https://fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com`). Basic Auth.

| Endpoint | Returns | Used for |
|---|---|---|
| `/fscmRestApi/resources/11.13.18.05/suppliers?expand=addresses` | Suppliers with embedded addresses | Country filtering (country on child resource) |
| `/fscmRestApi/resources/11.13.18.05/invoices` | Invoices | Date-bound invoice lookup per supplier |
| `/fscmRestApi/resources/11.13.18.05/purchaseOrders` | POs | Open POs per supplier |
| `/hcmRestApi/resources/11.13.18.05/publicWorkers` | HCM workers | Buyer lookup (cross-pillar) |

**Critical asymmetry (the SoT-honoring bit):**
- `search_invoices` filters by `supplierNumber` (string, e.g., `"1252"`)
- `search_purchase_orders` filters by `SupplierId` (numeric, e.g., `300000047572113`)
- The KG must encode which join field each endpoint expects

**Known Fusion quirks:**
- Composite `q=` filters (multi-clause `AND`) fail silently on `/invoices` and `/purchaseOrders`. Workaround: send the most selective single clause, fetch over-fetch (~200), filter remaining clauses client-side.
- No `/fscmRestApi/.../buyers` endpoint — buyers live in HCM `publicWorkers` keyed by `PersonId`.
- Country lives on the child `addresses` resource — use `?expand=addresses`, filter client-side.

---

## What's been demonstrated to work

The previous conversation surfaced these working artifacts (stored separately, not in Spire's repo):

1. **`PEOPLE_GRAPH` property graph in Oracle 26ai** with `PERSON`, `ORGANIZATION` vertex tables and `KNOWS`, `ROLE_ASSIGNMENT` edge tables. `CREATE PROPERTY GRAPH` works end-to-end.

2. **PGQ queries via `GRAPH_TABLE` operator** for 1-hop, multi-hop (`{1,3}`), variable-depth, and path queries. Including `ELEMENT_NUMBER(v)` for depth tracking and `ONE ROW PER STEP` for full paths.

3. **A Python BFS implementation** mirroring the same graph, used to cross-verify PGQ results.

4. **`SQL_vs_PGQ.md`** demonstrating the structural difference: SQL needs 2/4/6 joins for 1/2/3-hop; PGQ needs `{1,3}` changed to whatever depth.

The owner has verified PGQ works on their local Oracle 26ai instance with sample data. This is the foundation the new experiment builds on.

---

## The experiment to build

A scratch directory **outside** `~/pocs/spire/`. Proposed location: `~/pocs/spire-kg-experiment/`.

### Scope (minimum viable)

1. **Property graph DDL** for the Spire entity/edge schema.
   - Vertex tables for entity *types* (5 types: Supplier, Invoice, PurchaseOrder, Buyer, Address)
   - Edge tables for edge *declarations* (4 edges with join-field metadata)
   - Pattern table holding parameterized PGQ templates (start with 1 pattern)

2. **One pattern encoded end-to-end** — `country_filter_via_address` (simplest, exercises join-field metadata, no date arithmetic).

3. **A Python pattern executor** that:
   - Takes structured input (e.g., `{"entity": "Supplier", "filter": {"country": "US"}}`)
   - Runs a PGQ query against the KG to match the pattern
   - Returns a plan: a list of tool calls to make against Fusion
   - **Does not** call Fusion. Plan only.

4. **A separate test/demo script** that takes the plan output and executes it via direct `httpx` Fusion calls (no MCP, no agent). Compares the result to a known good answer.

### Out of scope (deliberately)

- No agent
- No LLM (yet)
- No MCP server
- No NL prompt parsing — input to the executor is structured JSON
- No integration with Spire's existing code
- Only one pattern; the other 3 come later if pattern 1 works

### Success criterion for the experiment

"Given structured input, the KG produces a deterministic plan. The plan, when executed against Fusion, returns the expected suppliers."

If this works, we then plan how to add the other 3 patterns + how to handle natural-language input (the LLM-as-prompt-parser step).

---

## Open design questions to settle in the new conversation

These were raised but not finalized:

**Q1.** How does a natural-language prompt get mapped to a structured pattern input?
- Lean: LLM extracts entities/filters into structured JSON; executor PGQ-matches that against the KG.
- This step is *out of scope* for the first experiment — start with structured input directly.

**Q2.** Hard execution vs soft guidance?
- Lean: hard execution. When a pattern matches, the plan is authoritative; the LLM only renders the final answer.
- The whole point of going graph-driven is determinism.

**Q3.** First pattern?
- Lean: `country_filter_via_address`. Simplest, exercises join semantics, no date math.

If you (the new conversation owner) want different leans, change them — these are starting points, not commitments.

---

## Working environment

- WSL Ubuntu 22.04 on Windows 11
- Python 3.12, virtualenv at `~/venv/spire`
- Oracle 26ai Free Release 23.26.1.0.0 in Docker container `oracle26ai_db_bhagavan`
- PDB `FREEPDB1`, host port 1521
- SPIRE user exists (password `jnjnuh`), has `CREATE PROPERTY GRAPH` privilege
- Or use the existing BHAGAVAN schema where `PEOPLE_GRAPH` lives — your call

For the experiment, I'd suggest a **new schema** (e.g., `SPIRE_KG_EXP`) to keep things clean and avoid polluting either SPIRE or BHAGAVAN. Or use SPIRE since the grants are already there.

---

## What the new conversation should do first

1. **Confirm the SoT constraint** is understood: KG holds metadata only, never Fusion data.
2. **Confirm the experiment scope:** one pattern, structured input only, output is a plan not an answer.
3. **Decide the schema choice** (new vs existing SPIRE).
4. **Generate the DDL** for the property graph (vertex tables, edge tables, pattern table).
5. **Generate the seed data** for the 5 entity types, 4 edges (no actual suppliers!), and 1 pattern.
6. **Run the DDL + seeds** and verify with a simple PGQ query.

Step 7 onward is the Python pattern executor.

---

## What to bring forward, what to leave behind

**Bring forward:**
- The hard constraints (SoT, metadata-only KG, Fusion via REST)
- The reference prompt
- The Fusion endpoint shapes (especially the SupplierNumber/SupplierId asymmetry)
- The 4 known query patterns by name
- The PEOPLE_GRAPH PGQ syntax as reference

**Leave behind (irrelevant for the experiment):**
- All Spire phase commits, branches, PRs
- The B-lite agent integration
- The evaluation framework, rubric scoring, phase 08/09/10 runs
- The MCP server, the LangGraph runner, the existing tools
- Process discussions about commit hygiene

The experiment is small and standalone. Most of Spire's history is just noise here.

---

## Honest framing for the new conversation

The B-lite approach in the main Spire repo gave us a working POC at the "demoable" level (5/5 reach 6/7 with 2.5-pro), but the KG was barely doing any computational work — it was decorative.

This experiment is testing whether the KG can be made **load-bearing**: whether real PGQ-driven plan generation can outperform LLM judgment on the kinds of structured queries Fusion supports.

If yes: phase 11 of Spire becomes "integrate the pattern executor into the agent loop."

If no: we honestly document that PGQ-driven planning didn't help, and the POC stops at phase 10.

The experiment is small enough to fail cheap and learn fast. That's the point.

---

## One small file to share

If the new conversation owner wants to see the working PEOPLE_GRAPH samples, they're in:

- `SQL_vs_PGQ.md` — SQL vs SQL/PGQ side-by-side with sample data
- `KG_Queries_replies.md` — 10 working PGQ queries with results
- `bfs_graph.py` — Python BFS that mirrors the PGQ semantics

These are reference material, not part of the experiment. They prove PGQ works on the owner's setup.

---

**End of handoff. New conversation starts here.**
