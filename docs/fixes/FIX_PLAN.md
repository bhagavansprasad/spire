# SPIRE — Fix Plan

**Branch:** `KG-Schema-Corpus`
**Created:** 2026-11-19 (fresh; prior FIX_PLAN content is superseded and
not carried forward — see docs/plan/PENDING_KG_SCHEMA_CORPUS.md for the
live KG-schema work queue)
**Status:** Open — KG schema corpus in progress; no fix-cluster work started
**Scope:** Deferred test failures recorded here so they are not lost, plus
the live KG-schema-corporus queue (tracked in `docs/plan/PENDING_KG_SCHEMA_CORPUS.md`).

---

## 1. Purpose

A single live queue of deferred/known test failures and their
disposition, so a future session does not re-derive "why does the suite
show these red?" This file is a *note of record*, not a re-listing of the
retired Phase 2 fix plan. The KG-schema-corpus work items live in
`docs/plan/PENDING_KG_SCHEMA_CORPUS.md`; only the test-failure deferrals
are recorded here.

---

## 2. Deferred test failures (2026-11-19)

Recorded from a full `pytest` run (1375 collected) against the
`KG-Schema-Corpus` branch. These are **deferred, not fixed now**; each
group names its cause and its owning file.

### 2.1 Environmental — Oracle session churn (`ORA-12516`) — FIXED 2026-11-19

**Tests:** `tests/test_planner.py` (up to 13 of its `test_generate_plan_*`
tests, non-deterministic count across runs).

**Cause:** `src/spire/planner/kg_db.py` opened a fresh
`oracledb.connect()` per KG lookup. A full planner file run churned
~1300 connections in ~5s; the pod's `processes=200` (~85 background,
~115 free) could not reclaim fast enough, so tests late in the file hit
the listener cap.

**Evidence:** `pytest -k "original_track_a"` alone → **7 passed**; the
same tests failed only inside the full-file run, with
`DPY-6000: Listener refused connection (Similar to ORA-12516)` at
connection-open time.

**Resolution:** `kg_db.py` now draws from a process-lifetime
`oracledb.ConnectionPool` (min=1, max=4, increment=1), created lazily and
reused. Full planner file now **136 passed in ~0.4s** (was ~8.5s with
intermittent failures). The 7 planner xfail markers added during triage
were removed — the tests pass deterministically.

### 2.2 Real code bugs — deferred to their own fix windows

| Group | Tests | Cause |
|---|---|---|
| F-015 narration | `tests/test_f015_empty_bucket_truncation.py` ×2 | Empty capped-fetch result narrated as clean "nothing found"; source total not named |
| Parser assembly drift | `tests/test_parser_context_assembly.py` ×3 | Preamble block count 52 vs 50; module/direct-vs-literal divergence |
| Bundle manifest drift | `tests/test_bundle_manifest.py` ×2 | Files (`.dockerignore`, `Dockerfile`, `.env.example`, `.github/copilot-instructions.md`, …) not in any bundle; stale bundle entries |
| Supplier-contacts pod data | `tests/test_supplier_contacts_tool.py` ×2 | Pod now returns 2 administrative contacts; test asserts 1 |

### 2.3 Known backlog — owned by the KG-schema-corpus task

| Group | Tests | Cause |
|---|---|---|
| Q5 emitter surface | `tests/test_sql_overlay_coverage.py` ×1 | `search_customer_accounts` + `search_receivables_invoices` have no SQL overlay entry — the 11 un-drafted Receivables entities |
| Stale `:supplier_id` assertion | `tests/test_sql_emitter.py::test_shape_4_suppliers_with_site_in_bu` | Site filter emitted no `:supplier_id` bind; assertion predates the KG column work; resolved by §3.3 |

---

## 3. Fixed in this branch (for the record, not open)

- `tests/test_agent_runner.py` collection error — guarded legacy
  `spire.agent.runner` import with `pytest.importorskip`
  (`langchain-mcp-adapters` requires `mcp<2`; app is on mcp 2.x +
  fastmcp 4.x).
- `tests/test_kg_metadata.py` row counts — `kg_entity_field` 210→217;
  added the 3 SQL satellites to the count contract.

---

## 4. Confirmed findings — open (KG schema corpus)

### F-060 — `PurchaseOrderLine.amount` binds to a stub column; SQL ≠ REST

**Status:** Confirmed (S0–S6 walked). Not fixed — needs a deliberate
carrier decision.

**S0.** `PO_LINES_ALL.AMOUNT` is the wrong carrier for the
`PurchaseOrderLine.amount` role — it is NULL on ~100% of pod rows, so the
SQL path returns null where the REST path returns the real line amount.

**S1 (harm).** Inconsistency between two paths: the emitted SQL returns
NULL line amounts while Spire's own REST answer returns `33000` / `8250`.
The corpus's whole purpose is that SQL and REST agree; they do not.

**S2 (evidence).** Prompt `Show PO 2144 and its lines` (REST answer
`Ordered = 33000.0` / `8250.0`). SQL against the pod:

    SELECT LINE_NUM, NVL(AMOUNT,-999), UNIT_PRICE FROM PO_LINES_ALL
    WHERE PO_HEADER_ID = 2144 ORDER BY LINE_NUM;
    -- 1  -999  33000
    -- 2  -999  8250

Aggregate: `AMOUNT` is NULL on **315,857 of 315,970** rows (99.96%);
`TAX_EXCLUSIVE_PRICE` is populated where `AMOUNT` is not (46,206 rows
non-null). Evidence scratch: `t_compare_agg.txt`, `t_compare_amt.txt`,
`t_compare_candidates.txt`.

**S3 (mechanism).** `kg_sql_column` binds `PurchaseOrderLine.amount →
PO_LINES_ALL.AMOUNT` (seeded in `scripts/sql/kg_schema.sql` STEP 12, from
`KG_ROLE_MAPS.md` §PurchaseOrderLine).

**S4 (root cause).** The R-7 stub-view shape, recurring at the column
level. The discovery method (§6 of `SCHEMA_DISCOVERY_METHOD.md`) verifies
a column **exists** in `t_task2_all.txt`, not that it is **populated**.
`AMOUNT` exists; it is just never set. The method has a gap: existence ≠
populated.

**S5 (alternative disproven).** Not a one-off — `AMOUNT` is broadly null
(315,857 rows), so it is a persistent pod property, not PO-2144-specific
data.

**S6 (falsifier).** A `COUNT(AMOUNT)` showing it is populated on most
rows would refute it; it shows the opposite.

**Decision needed (next window).** Pick the real carrier: `TAX_EXCLUSIVE_PRICE`
(populated, 33000/8250 confirmed) or a derived `UNIT_PRICE × QUANTITY`.
`TAX_EXCLUSIVE_PRICE` is the closer semantic match to REST `Ordered`
(excluding tax), but the naming and the many sibling amount columns
(`COMMITTED_AMOUNT`, `BASE_UNIT_PRICE`, etc.) need a deliberate choice, not
a quick swap. This is the first column-level R-7 recurrence — the fix
likely also tightens `SCHEMA_DISCOVERY_METHOD.md` §6 to check population,
not just existence.

### F-061 — buyer name format: SQL `DISPLAY_NAME` ≠ REST `Buyer`

**Status:** Observation (S1 border). Cosmetic.

SQL returns `PER_PERSON_NAMES_F.DISPLAY_NAME = "May Gee"` (first last);
REST returns `Buyer = "Gee, May"` (last, first). Same person, different
format. Recorded here so a future session does not treat it as a column
bug. Resolution (if any) is a display/formatting decision, not a schema
one.
