# Spire KG → Oracle SQL Property Graph Migration Plan

**Status:** Draft
**Scope:** Replace the planner's relational KG lookup with Oracle 26ai SQL Property Graph (`GRAPH_TABLE`). Executor, MCP tools, parser, synthesizer unchanged.
**Out of scope:** RDF/ontology (real knowledge graph), dynamic planning (Design 4), in-database algorithms.

---

## 1. Goal and non-goals

### Goal
Make Spire traverse its KG through Oracle's native SQL Property Graph feature instead of hand-written `SELECT ... FROM kg_edge WHERE ...` queries, and prove the change with a before/after prompt test set.

### Non-goals (explicitly deferred or rejected)
- **Not** adopting RDF/OWL/SPARQL. Oracle's property graph is not a knowledge graph; it has no ontology or inference layer.
- **Not** adopting Neo4j or any external graph database.
- **Not** dynamic planning. The planner still selects from a fixed set of step shapes.
- **Not** in-database algorithms (PageRank etc.) — capability gained, not needed at 17 edges.
- **Not** replacing the nine `kg_*` tables. The property graph is a view over them.

---

## 2. What changes vs. what stays

| Component | Change? | Notes |
|---|---|---|
| `kg_entity`, `kg_edge`, other 7 `kg_*` tables | No | Still the source of truth. Property graph points at them. |
| `scripts/sql/kg_schema.sql` | **Yes** | Add `CREATE OR REPLACE PROPERTY GRAPH`. |
| `scripts/rebuild_kg.py` | **Yes** | Add `ALTER PROPERTY GRAPH ... COMPILE` after seeding. |
| `src/spire/planner/kg_db.py` (or equivalent lookup) | **Yes** | Rewrite edge/entity lookups as `GRAPH_TABLE` queries. |
| `src/spire/planner/planner.py` | No | Plan-selection logic unchanged. |
| `src/spire/executor/executor.py` | No | All step shapes unchanged. |
| `src/spire/mcp_server/tools/*` | No | MCP tools unchanged. |
| `src/spire/nl_parser/*` | No | Parser, router, context assembly unchanged. |
| `src/spire/synthesizer/*` | No | Unchanged. |

---

## 3. Phases

### Phase 0 — Preconditions

**Checklist (verify before any code change):**

- [ ] Oracle pod is 26ai (or 23ai with SQL Property Graph enabled).
- [ ] `kg_*` tables exist and are seeded (current row counts: 22 / 210 / 17 / 3 / 129 / 3 / 11 / 37 / 16).
- [ ] `kg_entity.entity_name` has a PK (it does).
- [ ] `kg_edge.edge_name` has a PK (it does).
- [ ] `kg_edge.from_entity` and `kg_edge.to_entity` have indexes (add if missing — traversal performance depends on these).
- [ ] No `kg_*` table is a view, object table, or database link (SQL Property Graph forbids these as element tables).
- [ ] The baseline prompt test set (§9) has been run and its results captured as the "before" reference.

**Deliverable:** signed-off checklist in the PR description, with the captured "before" baseline attached.

**Risk:** Low.

---

### Phase 1 — Create the property graph

**Action:** append to `scripts/sql/kg_schema.sql` after the seed section:

```sql
CREATE OR REPLACE PROPERTY GRAPH spire_kg
  VERTEX TABLES (
    kg_entity
      KEY (entity_name)
      LABEL Entity
      PROPERTIES (entity_name, canonical_id_field, module)
  )
  EDGE TABLES (
    kg_edge
      KEY (edge_name)
      SOURCE KEY (from_entity) REFERENCES kg_entity (entity_name)
      DESTINATION KEY (to_entity) REFERENCES kg_entity (entity_name)
      LABEL Edge
      PROPERTIES (edge_name, from_join_field, to_join_field, cardinality)
  );
```

**Why `OR REPLACE`:** SQL property graph definitions are immutable and cannot be modified in place; redefinition is the only way to change them.

**Why minimal:** map only `kg_entity` and `kg_edge` in Phase 1. The other seven tables (`kg_entity_field`, `kg_vocabulary`, `kg_entity_tool`, etc.) are metadata *about* the graph, not the graph itself. Adding them as vertices would confuse the model.

**Verification query:**

```sql
SELECT * FROM GRAPH_TABLE (spire_kg
  MATCH (a IS Entity WHERE a.entity_name = 'Supplier') -[e IS Edge]-> (b IS Entity)
  COLUMNS (b.entity_name AS to_entity, e.edge_name AS via_edge)
) FETCH FIRST 5 ROWS ONLY;
```

Expected: returns Supplier's outgoing edges (HAS_INVOICE, HAS_ADDRESS, HAS_PURCHASE_ORDER, HAS_SITE, HAS_CLASSIFICATION, HAS_CONTACT).

**Deliverable:** `spire_kg` graph exists and returns correct edges.

**Effort:** 2–3 hours.
**Risk:** Low.

---

### Phase 2 — Replace the planner's lookup

**Current behavior (illustrative):**

```sql
SELECT to_entity, to_join_field
  FROM kg_edge
 WHERE from_entity = :from AND to_entity = :to;
```

**New behavior:**

```sql
SELECT to_entity, via_edge, to_join_field
FROM GRAPH_TABLE (spire_kg
  MATCH (a IS Entity WHERE a.entity_name = :from)
        -[e IS Edge]->
        (b IS Entity WHERE b.entity_name = :to)
  COLUMNS (b.entity_name AS to_entity,
           e.edge_name   AS via_edge,
           e.to_join_field AS to_join_field)
);
```

**Scope of change:**

- Locate `find_edge` / `find_entity_tool` (or equivalent) in `src/spire/planner/kg_db.py`.
- Rewrite the SQL string. The function signature and return shape stay identical, so callers are unaffected.
- If the planner does multi-hop composition (e.g., "Supplier → PurchaseOrder → Buyer"), each hop remains a separate `find_edge` call. **Do not** collapse multi-hop into a single `{1,3}` pattern in this phase — that is Phase 4 (deferred).

**What stays identical:**

- `kg_entity_filter` rows with `mechanism='edge_traversal'` still drive filter selection.
- `kg_entity_tool` and `kg_edge_tool` mappings still resolve entity/edge names to MCP tool names.
- Plan objects (`Step`, `Plan`) are constructed the same way.
- Executor consumes `Plan` unchanged.

**Tests to run:**

- `tests/test_planner.py` — must pass without modification.
- `tests/test_kg_metadata.py` — must pass (validates the tables, not the query mechanism).
- `tests/test_executor.py` — must pass (executor doesn't know about the lookup mechanism).
- Full prompt test set (§9) — zero regressions.

**Deliverable:** planner uses `GRAPH_TABLE`; all existing tests pass; prompt test set green.

**Effort:** 1–2 days.
**Risk:** Medium. The rewrite is mechanical but touches the planner's core data-access path. Any shape change in the returned rows will surface here.

---

### Phase 3 — Handle graph invalidation

**Problem:** if a column is added to `kg_entity` or `kg_edge` (or their types change), the property graph becomes `INVALID` and queries fail.

**Action:** in `scripts/rebuild_kg.py`, after the seed SQL executes and commits, append:

```python
# After the last seed statement, before connection close:
cursor.execute("ALTER PROPERTY GRAPH spire_kg COMPILE")
```

If `COMPILE` fails (structure genuinely changed), the rebuild script should fall back to re-running the `CREATE OR REPLACE PROPERTY GRAPH` statement from `kg_schema.sql`.

**Test:**

1. Add a dummy column to `kg_entity` via `ALTER TABLE kg_entity ADD (test_col VARCHAR2(10))`.
2. Run `python scripts/rebuild_kg.py`.
3. Confirm `COMPILE` succeeds (or `CREATE OR REPLACE` re-creates the graph).
4. Confirm a `GRAPH_TABLE` query still works.
5. Drop the dummy column.

**Deliverable:** `rebuild_kg.py` handles invalidation gracefully.

**Effort:** 2–3 hours.
**Risk:** Low.

---

### Phase 4 — (Deferred) Variable-length traversal

**What it would buy:** express multi-hop paths as `MATCH (a)-[e]->{1,3}(b)` in one query, replacing N planner steps with one.

**Why deferred:** Spire's plans are fixed two- and three-hop chains. Variable-length matching only matters if a prompt requires arbitrary depth. None currently does. **Do not implement until a concrete prompt demands it.**

**When to revisit:** when a prompt like "find any path from X to Y within 4 hops" enters the corpus and cannot be expressed as a fixed chain.

**Effort (when triggered):** 1–2 weeks. Requires planner restructuring (the fixed-chain guarantee weakens).

---

### Phase 5 — (Deferred) In-database graph algorithms

**What it would buy:** PageRank, Bellman-Ford, WCC via `DBMS_OGA`. Oracle advertises 80+ pre-built algorithms.

**Why deferred:** Spire's graph has 17 edges. Centrality and community detection produce meaningless results at that size. No prompt asks for them.

**When to revisit:** if Spire's KG grows to thousands of edges and a prompt requires centrality, ranking, or clustering.

**Effort (when triggered):** 1 week (wire `DBMS_OGA` into a new MCP tool; not a planner change).

---

## 4. Success criteria

| Criterion | Verification |
|---|---|
| `spire_kg` property graph exists and queries correctly | Phase 1 verification query returns expected edges |
| Planner's edge lookups use `GRAPH_TABLE` | Code review: no `FROM kg_edge` remains in `kg_db.py` |
| All existing tests pass | `pytest tests/` green |
| Prompt test set (§9) has zero regressions | Before/after comparison shows identical plan shapes |
| Graph invalidation is handled | Phase 3 test passes |
| Executor, MCP tools, parser, synthesizer untouched | `git diff --stat` shows no changes in those directories |

---

## 5. Rollback plan

If Phase 2 proves problematic:

1. Revert the planner changes (`kg_db.py` back to relational SQL).
2. Keep the property graph (`spire_kg`) in the schema — it is inert metadata; it does not affect the relational queries.
3. Ship the graph definition alone as a Phase 1 deliverable. The native feature is available for future use without the planner depending on it.

**Rollback risk:** Low. The property graph is a view; the tables are untouched.

---

## 6. Explicitly rejected alternatives

| Alternative | Why rejected |
|---|---|
| **Neo4j / external graph database** | Adds an operational dependency (separate process, separate backup, separate auth). Spire's 17-edge graph does not justify it. Would require rewriting the planner, executor, and tool-mapping layer. |
| **RDF triple store (GraphDB, Stardog, Jena)** | This is what "knowledge graph" actually means, but it requires an ontology, a reasoner, and SPARQL. Spire has none of these, and its prompts don't need them. Large architectural change for no current benefit. |
| **Dynamic planning (Design 4)** | Removes the fixed-chain guarantee that makes the executor testable. Not needed while traversals are 2–3 hops. |

---

## 7. Effort summary

| Phase | Effort | Risk | Ship? |
|---|---|---|---|
| 0 — Preconditions | 1 hour | Low | — |
| 1 — Create graph | 2–3 hours | Low | Yes |
| 2 — Replace lookup | 1–2 days | Medium | Yes |
| 3 — Invalidation handling | 2–3 hours | Low | Yes |
| **Core migration total** | **~2–3 days** | — | — |
| 4 — Variable-length | 1–2 weeks | Medium | Deferred |
| 5 — Algorithms | 1 week | Low | Deferred |

---

## 8. Open questions to resolve before Phase 2

1. **Where exactly does the planner construct the `SELECT ... FROM kg_edge` query today?** Locate the function(s) and count call sites before rewriting.
2. **Does the planner ever query `kg_entity_field` or `kg_vocabulary` via the same data-access layer?** If so, decide whether those remain relational (recommended) or become graph queries (not recommended — they are metadata, not graph structure).
3. **Is the pod actually 26ai, or 23ai with the feature backported?** Confirm before Phase 1; the DDL syntax is the same but some algorithm APIs differ.
4. **What is the prompt test set's pass/fail baseline today?** Capture it before Phase 2 (§9.1), so regressions are measurable.

---

## 9. Testing: before/after prompt comparison

This chapter is the acceptance test for the whole migration. It defines a fixed set of prompts, captures the plan and output under the current relational lookup, then captures the same under `GRAPH_TABLE`, and requires the **plan shapes and final answers to be identical** for every case where Graph DB is claimed to be equivalent.

The purpose is not to show Graph DB is better. It is to show that **replacing the lookup mechanism does not change what Spire answers**. If any prompt changes its plan or its answer, that is a regression and Phase 2 has failed.

### 9.1 Test corpus structure

The corpus has four groups. Each prompt is run once before Phase 2 (relational baseline) and once after (Graph DB), and the two results are compared.

| Group | What it tests | Expected change |
|---|---|---|
| A — One-hop lookups | Single `find_edge` call, one MCP tool | **No change.** Same plan, same tool call, same output. |
| B — Multi-hop fixed chains | Planner composes two `find_edge` calls | **No change.** Same plan, same tool sequence, same output. |
| C — Graph DB-only capabilities | Variable-length paths, algorithms | **Before: Spire cannot plan it** (refusal or wrong plan). After: still refused unless Phase 4/5 is implemented. This group documents the *gap*, not a regression. |
| D — Edge-case semantic tests | Negation, empty results, join-field asymmetry | **No change.** Same plan, same answer. Proves the migration did not alter semantics. |

### 9.2 Group A — one-hop lookups

**A1. "List invoices for supplier 1252."**

- *Before:* planner emits one Step: `search_invoices(supplier_number="1252")`. The join field `SupplierNumber` is read from `kg_edge` via `SELECT to_join_field FROM kg_edge WHERE from_entity='Supplier' AND to_entity='Invoice'`.
- *After:* the same planner Step is emitted; the join field is read via `GRAPH_TABLE (spire_kg MATCH (a IS Entity ...)-[e IS Edge]->(b IS Entity ...) COLUMNS (e.to_join_field))`.
- **Acceptance:** identical `Plan` object, identical MCP tool call, identical invoice list.

**A2. "Show purchase orders for supplier 1252."**

- *Before:* `SELECT to_join_field FROM kg_edge WHERE ...` returns `SupplierId`.
- *After:* `GRAPH_TABLE` returns `SupplierId`.
- **Acceptance:** identical plan, identical tool args, identical PO list. This also proves the join-field asymmetry (SupplierNumber for Invoice, SupplierId for PO) is preserved across the migration.

**A3. "Get supplier 1252's addresses."**

- *Before:* `HAS_ADDRESS` edge has no `kg_edge_tool` row; the planner routes to `search_suppliers` with `expand=addresses`.
- *After:* same routing. The graph query returns the same edge row; the absence of a `kg_edge_tool` row is unchanged.
- **Acceptance:** identical plan. The absence-of-edge-tool signal still works under `GRAPH_TABLE`.

### 9.3 Group B — multi-hop fixed chains

**B1. "Who is the buyer for supplier 1252's open purchase orders?"**

- *Before:* two Steps. Step 1: `search_purchase_orders(supplier_id=1252, status="OPEN")`. Step 2 (iterating): for each `BuyerId`, call `get_buyer(buyer_id)`. Each hop is a separate `find_edge` call.
- *After:* the same two Steps. Each `find_edge` call is now a `GRAPH_TABLE` query.
- **Acceptance:** identical plan (two Steps, same iteration field), identical tool sequence, identical buyer list. **The number of database queries to the KG is the same** — Graph DB does not collapse the two hops in this phase.

**B2. "Show the lines for PO 2144."**

- *Before:* one Step: `get_purchase_order_lines(po_header_id=...)`, reached via `HAS_LINE`.
- *After:* same.
- **Acceptance:** identical output. This is a single-hop expansion; the interesting part is that the planner still resolves `HAS_LINE` correctly through the graph.

**B3. "AR invoice 1002 with its lines and tax lines."**

- *Before:* three-level traversal: `ReceivablesInvoice` → `HAS_AR_LINE` → `ReceivablesInvoiceLine` → `HAS_TAX_LINE` → `ReceivablesTaxLine`. The tax-line step is a **multi-field iteration** (needs both `CustomerTransactionId` and `CustomerTransactionLineId`).
- *After:* same three-level plan, each hop via `GRAPH_TABLE`.
- **Acceptance:** identical plan, including the multi-field iteration on `HAS_TAX_LINE`. This proves the graph query returns the `iter_fields_json` metadata (or its equivalent) correctly.

### 9.4 Group C — capabilities Graph DB adds (documented gap)

These prompts are **not expected to pass** after Phase 2. They document what Graph DB *would* enable and why Spire does not implement it yet.

**C1. "Find any entity reachable from Supplier within 2 hops."**

- *Before:* Spire refuses — no fixed plan shape for variable-depth traversal.
- *After Phase 2:* still refuses. **Acceptance:** the refusal is unchanged.
- *After Phase 4:* would pass via `MATCH ... {1,2}`. Not in scope here.

**C2. "Rank suppliers by PageRank over the KG."**

- *Before:* Spire refuses — no in-database algorithm support.
- *After Phase 2:* still refuses.
- *After Phase 5:* would pass via `DBMS_OGA`. Not in scope here.

**Acceptance for Group C:** the refusal text is **byte-identical** before and after Phase 2. This is a negative test — it proves Phase 2 did not accidentally break the refusal path.

### 9.5 Group D — edge-case semantic tests

**D1. "Suppliers with no invoices in the last 6 months."**

- *Before:* `filter_source_when_empty=True` step. For each supplier, call `search_invoices(supplier, invoice_date_after=<6mo>)`; keep the supplier if the result is empty.
- *After:* same plan. The `HAS_INVOICE` edge is resolved via `GRAPH_TABLE`, but the executor's emptiness test is unchanged.
- **Acceptance:** identical supplier list. This is the most important semantic test — it proves the negation-by-absence logic is unaffected by the lookup mechanism.

**D2. "Suppliers with an invoice over $10,000."**

- *Before:* `filter_source_when_nonempty=True` step, `amount_min` carried into the child call.
- *After:* same.
- **Acceptance:** identical supplier list.

**D3. "Invoices for supplier with number 1252 — what is the join field?"**

- *Purpose:* pin the asymmetry. The KG must return `SupplierNumber` for Invoice and `SupplierId` for PO, before and after.
- *Before:* `SELECT to_join_field FROM kg_edge ...` returns `SupplierNumber`.
- *After:* `GRAPH_TABLE` returns `SupplierNumber`.
- **Acceptance:** both return the same field. This is the test that guards against a subtle bug where `GRAPH_TABLE` returns columns in a different order and the planner picks the wrong one.

**D4. "Supplier that does not exist — supplier 999999."**

- *Before:* planner emits a step, tool returns empty, synthesizer says "no records found."
- *After:* same.
- **Acceptance:** identical empty-result handling. The graph query returns nothing, but the *plan* was still built (it doesn't need the graph to resolve an edge for an unknown entity name).

### 9.6 How to run the comparison

**Before Phase 2 (baseline capture):**

```bash
# Capture the current plan and output for every prompt in §9.2–9.5
python scripts/run_prompt_set.py \
    --set migration_baseline \
    --out docs/migration/baseline_relational.json
```

**After Phase 2 (comparison):**

```bash
python scripts/run_prompt_set.py \
    --set migration_baseline \
    --out docs/migration/after_graphdb.json

python scripts/compare_prompt_runs.py \
    docs/migration/baseline_relational.json \
    docs/migration/after_graphdb.json \
    --assert-plan-identical \
    --assert-output-identical
```

The comparison must check **three** things per prompt:

1. **Plan shape**: same number of steps, same `tool_name` per step, same `iterate_over` / `filter_source_when_*` flags.
2. **Tool arguments**: same values passed to each MCP tool. A change here means the join field or iteration value changed.
3. **Final output**: same `outputs` dict (same records, same order) and same synthesizer response.

Any difference in (1) or (2) is a **hard failure** — the migration changed behavior. A difference in (3) with (1) and (2) unchanged is suspicious and must be investigated.

### 9.7 The prompt set file

Create `prompts/migration/migration_baseline.txt` with one prompt per line. The nine prompts from §9.2–9.5:

```
List invoices for supplier 1252
Show purchase orders for supplier 1252
Get supplier 1252's addresses
Who is the buyer for supplier 1252's open purchase orders
Show the lines for PO 2144
Show AR invoice 1002 with its lines and tax lines
Find any entity reachable from Supplier within 2 hops
Rank suppliers by PageRank over the KG
Suppliers with no invoices in the last 6 months
Suppliers with an invoice over 10000
Invoices for supplier with number 1252 - what is the join field
Supplier that does not exist - supplier 999999
```

Add the set to `scripts/manifests/` so `run_prompt_set.py` can load it by name.

### 9.8 What "pass" means

- **Group A and B:** every prompt returns identical plan, identical tool args, identical output. **This is the migration's acceptance criterion.**
- **Group C:** every refusal is byte-identical. The migration did not accidentally enable or disable a capability.
- **Group D:** every prompt returns identical plan and output. **This is the semantic-safety criterion.**

If any Group A, B, or D prompt fails, Phase 2 is reverted per §5.

### 9.9 What the test does NOT prove

- That Graph DB is faster. It is not, for this workload — the queries are equivalent.
- That Graph DB produces better answers. It does not — the data is the same.
- That Spire should adopt Graph DB. It proves the migration is **safe**, not that it is **worthwhile**. The worthwhileness argument is in §1 and §6.

The test exists to answer one question: **"If we change the lookup mechanism, does Spire still answer the same way?"** The answer must be yes for every non-deferred prompt.

---

## 10. Testing integration with the existing test suite

In addition to §9, the migration must keep the existing suite green. The following tests are load-bearing for this change:

| Test file | What it guards |
|---|---|
| `tests/test_planner.py` | Plan construction from `kg_entity_filter` rows. Must pass unchanged. |
| `tests/test_kg_metadata.py` | KG table row counts and FK integrity. Must pass unchanged. |
| `tests/test_executor.py` | Executor step shapes. Must pass unchanged — the executor does not see the lookup mechanism. |
| `tests/test_graph_pipeline.py` | End-to-end pipeline. Must pass unchanged. |
| `tests/test_f011_po_relative_date.py` | Date-filter semantics on PO edges. Guards that relative-date filters still route correctly. |
| `tests/test_f053_open_po_filter.py` | Open-PO edge traversal. Guards `has_open_PO`. |
| `tests/test_f056_supplier_pos_buyers.py` | Multi-hop Supplier → PO → Buyer chain. Guards the chain the migration touches most directly. |
| `tests/test_f041_ar_child_root.py` | AR child entity routing. Guards the AR side of the graph. |

If any of these fail, the migration has changed behavior and Phase 2 does not ship.

---

## 11. Deliverables checklist

Before merging:

- [ ] `spire_kg` property graph created in `kg_schema.sql`.
- [ ] `rebuild_kg.py` runs `ALTER PROPERTY GRAPH ... COMPILE` after seeding.
- [ ] `kg_db.py` (or equivalent) uses `GRAPH_TABLE` for edge lookups.
- [ ] No `FROM kg_edge` remains in the planner's data-access path.
- [ ] `tests/` full suite passes.
- [ ] `prompts/migration/migration_baseline.txt` created and added to manifests.
- [ ] Baseline run captured in `docs/migration/baseline_relational.json`.
- [ ] After run captured in `docs/migration/after_graphdb.json`.
- [ ] Comparison report shows zero differences in Group A, B, D; identical refusals in Group C.
- [ ] Rollback procedure (§5) documented in the PR description.

---

*End of plan.*