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

**Status:** Fixed (2026-11-19). Carrier chosen: derived
`UNIT_PRICE × QUANTITY`. See **Resolution** below.

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

**Resolution (2026-11-19).** Carrier = derived `UNIT_PRICE × QUANTITY`,
not `TAX_EXCLUSIVE_PRICE`. Decisive pod evidence:

- `TAX_EXCLUSIVE_PRICE` is populated on only **47,206 / 315,970** rows
  (14.9%), and — the deciding fact — it is a **unit** price, not the
  extended amount. On PO 3 line 1: `UNIT_PRICE`=444, `QUANTITY`=2,
  `TAX_EXCLUSIVE_PRICE`=425, but the extended amount is 888. It equals
  `UNIT_PRICE` on rows where both are populated, so it cannot carry
  `Ordered` ("line extended amount excluding tax") whenever `QUANTITY`≠1.
- `UNIT_PRICE` (99.96%) and `QUANTITY` (98.3%) are near-universal.
- PO 2144: `UNIT_PRICE × QUANTITY` = 33000 / 8250 = REST `Ordered`. ✓

**Fix applied** (`Phase3-F060-Amount-Carrier`):

1. `scripts/sql/kg_schema.sql` — removed the `kg_sql_column` row
   `PurchaseOrderLine.Ordered → AMOUNT`; added `kg_derived_projection`
   `PurchaseOrderLine.Ordered → L.UNIT_PRICE * L.QUANTITY`.
2. Fixed the two derived projections that also read the stub `L.AMOUNT`:
   - `PurchaseOrder.Ordered` → `(SELECT SUM(L.UNIT_PRICE * L.QUANTITY) …)`
   - `PurchaseOrderLine.Total` → `(L.UNIT_PRICE * L.QUANTITY) + (tax subquery)`
3. Row counts: `kg_sql_column` 57→56, `kg_derived_projection` 4→5
   (updated in `test_kg_metadata.py` and `scripts/print_kg.py`).
4. `SCHEMA_DISCOVERY_METHOD.md` §6 — added the population check
   ("existence ≠ populated").

**Verification** (emitted SQL ran via `runsql.sh`): line `Ordered` =
33000 / 8250 (REST ✓); header `Ordered` = 41250 (SUM of the two lines).

### F-062 — `POSchedule.amount` binds to `PO_LINE_LOCATIONS_ALL.AMOUNT`, also a stub

**Status:** Confirmed. Not fixed — schedule-level carrier needs a separate
discovery decision.

`PO_LINE_LOCATIONS_ALL.AMOUNT` is NULL on 310,807 of 310,947 rows (99.95%)
— the same R-7 stub shape as F-060. `POSchedule.Amount` (`kg_sql_column`
→ `AMOUNT`, `is_default_projection='Y'`) therefore emits NULL where REST
returns a schedule amount. `PO_LINE_LOCATIONS_ALL` has **no** `UNIT_PRICE`
(ORA-00904), so the schedule extended amount cannot be derived on-table;
it needs a join back to `PO_LINES_ALL` via `PO_LINE_ID`
(`L.UNIT_PRICE × S.QUANTITY`, schedule quantity). That derivation (and the
schedule-amount semantics vs line amount) must be verified against REST
before binding — deferred to the POSchedule role-map pass.

### F-063 — `Total`/`TotalTax` return NULL, not 0, when the schedule tax is NULL

**Status:** Observation (pre-existing, not introduced by F-060).

`TotalTax` = `(SELECT SUM(LL.ESTIMATED_TAX_AMOUNT) …)` returns NULL (not 0)
when the line's schedules carry a NULL `ESTIMATED_TAX_AMOUNT` (PO 2144 has
schedule rows with NULL tax), so `Total` = `Ordered + NULL` = NULL. This
was already flagged in `KG_ROLE_MAPS.md` §PurchaseOrderLine ("NULL, not 0,
for a line with no schedules"); F-060's carrier fix did not change the
NULL-propagation behavior of the tax subquery. If REST returns `TotalTax=0`
and `Total=Ordered` in this case, an `NVL(SUM(…), 0)` is warranted — a
separate decision, not part of F-060.

### F-061 — buyer name format: SQL `DISPLAY_NAME` ≠ REST `Buyer`

**Status:** Observation (S1 border). Cosmetic.

SQL returns `PER_PERSON_NAMES_F.DISPLAY_NAME = "May Gee"` (first last);
REST returns `Buyer = "Gee, May"` (last, first). Same person, different
format. Recorded here so a future session does not treat it as a column
bug. Resolution (if any) is a display/formatting decision, not a schema
one.

### F-064 — PO-status filter/aggregation named the absent `AUTHORIZATION_STATUS` (fixed §3.3b)

**Status:** Fixed 2026-11-19 (`Phase3-F060-Amount-Carrier`, §3.3b filter
part).

`PO_HEADERS_ALL` has `DOCUMENT_STATUS`, not `AUTHORIZATION_STATUS` (and no
`AMOUNT` column — only `AMOUNT_LIMIT`/`AMOUNT_RELEASED`/…). Two live
hand-authored sites still named the absent column, so the emitted SQL
failed ORA-00904 on the pod:

1. `search_purchase_orders` status filter — `predicate_template="{alias}.AUTHORIZATION_STATUS = …"`.
2. `aggregate_purchase_orders_by_status` — `group_by_column="AUTHORIZATION_STATUS"` **and** `measure_template="SUM(AMOUNT)"` (the `AMOUNT` stub again, at the aggregation level).

**Fix:** filter + `group_by_column` → `DOCUMENT_STATUS` (the KG-carried
`StatusCode` carrier); measure → derived
`SUM((SELECT SUM(L.UNIT_PRICE * L.QUANTITY) FROM PO_LINES_ALL L WHERE L.PO_HEADER_ID = P.PO_HEADER_ID))`;
`_qualify_measure` now passes a nested-subquery measure through unchanged
instead of mangling it into `SUM(P.(SELECT …))`. Three regression tests in
`tests/test_sql_emitter.py`.

**Verification:** both statements run on the pod — status filter returns
OPEN POs; aggregation returns 14 statuses with summed derived amounts.

This closes the drafted-entities half of §3.3b (filters/aggregations
resolve to verified carriers). The remaining half — the 11 Receivables
entities — is blocked on their role maps (task 5).

### F-065 — `search_purchase_orders.supplier_id` filter matched SEGMENT1 (SupplierNumber), not VENDOR_ID (SupplierId)

**Status:** Fixed 2026-11-19 (`Phase3-F060-Amount-Carrier`, found by the
end-to-end promptkit ↔ runsql verification).

**S0.** The `supplier_id` filter's `predicate_template` matched
`POZ_SUPPLIERS.SEGMENT1` (the human SupplierNumber) against a value that is
actually the numeric internal SupplierId (`PO_HEADERS_ALL.VENDOR_ID`), so
the emitted SQL returned 0 rows where REST returned the supplier's rows.

**S1 (harm).** SQL ≠ REST. Prompt "Which suppliers have open purchase
orders?" — REST answer: 17 of 25 sampled suppliers have open POs. The
emitted step-2 SQL (SEGMENT1 = numeric SupplierId) returned 0 rows for
every supplier, so the SQL path would report **0** suppliers with open POs.

**S2 (evidence).** The tool contract
(`src/spire/mcp_server/tools/purchase_orders.py`) declares `supplier_id:
int` = "Exact SupplierId match (numeric)" and sets
`server_clause=f"SupplierId={supplier_id}"`. The plan iterates
`iterate_over.field='SupplierId'` (numeric). Against the pod:

    -- CORRECT (REST semantics): VENDOR_ID = 300000047414503 → 274 OPEN rows
    -- EMITTED (old): SEGMENT1 = 300000047414503 → (no rows returned)

**S3 (mechanism).** `src/spire/kg/sql_overlay.py`
`("search_purchase_orders","supplier_id")` FilterSpec's
`predicate_template="P.VENDOR_ID IN (SELECT VENDOR_ID FROM POZ_SUPPLIERS
WHERE SEGMENT1 = {value})"`.

**S4 (root cause).** The overlay assumed `supplier_id` could be a
SupplierNumber; the tool never does — it is the numeric SupplierId. The
comment and assumption encoded the wrong polarity.

**S5 (alternative disproven).** Not a data quirk — `SEGMENT1='1252'`
(string) is the SupplierNumber, `VENDOR_ID=300000047414503` (number) is
the SupplierId; the two live in different columns.

**Fix.** `predicate_template="{alias}.VENDOR_ID = {value}"`,
assumption → `supplier_maps_to_vendor_id` (already defined, previously
unused). The old `supplier_number_not_vendor_id` assumption text marked
OBSOLETE. Regression test
`test_po_supplier_id_filter_uses_vendor_id_not_segment1`.

**Verification.** `P.VENDOR_ID = 300000047414503 AND DOCUMENT_STATUS='OPEN'`
returns open POs for Lee Supplies (matches REST).

**S8 (miss record).** The FilterSpec was drafted against the overlay's
hand-authored assumptions, not the tool signature; the end-to-end
promptkit ↔ runsql discipline surfaced it in one run.
