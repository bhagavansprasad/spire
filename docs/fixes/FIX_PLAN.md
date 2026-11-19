# SPIRE — Fix Plan

**Branch:** `Phase3-Fix-Nullable-Keys`
**Created:** 2026-11-19 (fresh; prior FIX_PLAN content is superseded and
not carried forward — see docs/plan/PENDING_KG_SCHEMA_CORPUS.md for the
live KG-schema work queue)
**Status:** Open — F-074 / F-062 / F-063 and the §2.3 backlog resolved this
window; F-061 / F-072 / F-073 remain open
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

Both items resolved 2026-11-19 (`Phase3-Fix-Nullable-Keys`).

| Group | Tests | Cause | Status |
|---|---|---|---|
| Q5 emitter surface | `tests/test_sql_overlay_coverage.py` ×1 | `search_customer_accounts` + `search_receivables_invoices` (the two filter-less sample-and-disclose fetchers) had no SQL overlay entry | **FIXED** — `tool_to_entity` now maps `search_receivables_invoices → ReceivablesInvoice` and `search_customer_accounts → CustomerAccount`; xfail removed, test green |
| Stale `:supplier_id` assertion | `tests/test_sql_emitter.py::test_shape_4_suppliers_with_site_in_bu` | Site filter emitted no `:supplier_id` bind — the `supplier_id` iteration arg had no FilterSpec, so the emitted SQL was malformed (`WHERE -- unmapped iteration arg` then `AND`) | **FIXED** — added `("search_suppliers_by_site_bu","supplier_id")` FilterSpec `{alias}.VENDOR_ID = {value}` + `site_supplier_id_maps_to_vendor_id` assumption; the emitted SQL is now `WHERE S.VENDOR_ID = :iteration_value AND S.PRC_BU_ID = …`; xfail removed, test green |

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

**Status:** Fixed (2026-11-19). Carrier = derived `line UNIT_PRICE × schedule
QUANTITY`.

`PO_LINE_LOCATIONS_ALL.AMOUNT` is NULL on 310,807 of 310,947 rows (99.95%)
— the same R-7 stub shape as F-060. `POSchedule.Amount` (`kg_sql_column`
→ `AMOUNT`, `is_default_projection='Y'`) therefore emits NULL where REST
returns a schedule amount. `PO_LINE_LOCATIONS_ALL` has **no** `UNIT_PRICE`
(ORA-00904), so the schedule extended amount cannot be derived on-table;
it needs a join back to `PO_LINES_ALL` via `PO_LINE_ID`.

**Resolution (2026-11-19).** The `AMOUNT` `kg_sql_column` row is removed
and replaced with a `kg_derived_projection`:
`(SELECT L.UNIT_PRICE FROM PO_LINES_ALL L WHERE L.PO_LINE_ID = S.PO_LINE_ID) * S.QUANTITY`.
The multiplier is the **schedule** quantity (a schedule is a shipment of a
portion of the line), verified exact against REST on PO 300000133123880:
line 300000133123881 qty 738/3/86 → 12064.824 / 49.044 / 1405.928, all
equal REST `Amount`. Row counts: `kg_sql_column` 128→127,
`kg_derived_projection` 9→10.

### F-063 — `Total`/`TotalTax` read a stub tax column, NULL on every line

**Status:** Fixed (2026-11-19). Reclassified from observation to
Confirmed bug: the tax carrier was a complete stub.

`TotalTax` = `(SELECT SUM(LL.ESTIMATED_TAX_AMOUNT) …)` read
`PO_LINE_LOCATIONS_ALL.ESTIMATED_TAX_AMOUNT`, which is NULL on **all
310,952** schedule rows (a complete stub, not just "NULL when tax is
unset"). So `TotalTax` and `Total` (= `Ordered + NULL`) were NULL on
**every** PO line, while REST returns real tax. The original framing
("NULL, not 0, when the schedule tax is NULL") understated it: the column
is never populated, so the SQL path was wrong everywhere, not just on
tax-less lines.

**Resolution (2026-11-19).** The line tax is `RECOVERABLE_TAX +
NONRECOVERABLE_TAX` on `PO_DISTRIBUTIONS_ALL`, summed over the line's
distributions. Both derived projections now use
`NVL((SELECT SUM(D.RECOVERABLE_TAX + D.NONRECOVERABLE_TAX) FROM PO_DISTRIBUTIONS_ALL D WHERE D.PO_LINE_ID = L.PO_LINE_ID), 0)`.
Verified exact against REST: PO 2144 line 1 → TotalTax 3135 / Total 36135
(REST 3135 / 36135); PO 65 line 2 → 1045.4 / 6272.4; PO 300000133123880
(multi-distribution) lines 300000133123881/…888/…893 → 2298.37 / 2605.46 /
73461.53, all equal REST `TotalTax`/`Total`. The `NVL(…, 0)` returns 0
(not NULL) for the 5,189 lines with no distributions and 10 lines whose
distribution tax is all-NULL — and those no-distribution lines largely
sit on POs REST 404s on (e.g. 300000048657237), so they are not a
SQL-vs-REST divergence source.

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

### F-066 — `CustomerTransaction.TransactionId` maps to `CUSTOMER_TRX_ID`, not `PAYMENT_SCHEDULE_ID`

**Status:** Fixed 2026-11-19 (`Phase3-F060-Amount-Carrier`, role map
seeded).

**S0.** The hand-authored `CustomerTransaction` EntitySpec projects
`PAYMENT_SCHEDULE_ID` as the row id, but REST's `TransactionId` field is
the physical `CUSTOMER_TRX_ID` — a different value on the same row.

**S1 (harm).** SQL ≠ REST at the id column. The emitted SQL's first
column (`PAYMENT_SCHEDULE_ID`=1398398) is a different number than the REST
`TransactionId` (1624374) on the same transaction, so the SQL path would
report the wrong id for every row. Amount/date/number columns agree; only
the id is mismapped.

**S2 (evidence).** Prompt "Show me AR invoices for customer ABC Corporation
Americas" (dipstick depth 5). REST row: `TransactionId=1624374,
TransactionNumber=1471201, TotalOriginalAmount=693.83`. Against the pod:

    -- hand-authored map: PAYMENT_SCHEDULE_ID as the id
    SELECT T.PAYMENT_SCHEDULE_ID, T.CUSTOMER_TRX_ID, T.TRX_NUMBER
    FROM AR_PAYMENT_SCHEDULES_ALL T WHERE T.TRX_NUMBER = '1471201';
    -- PAYMENT_SCHEDULE_ID=1398398, CUSTOMER_TRX_ID=1624374, TRX_NUMBER=1471201

    REST TransactionId (1624374) == CUSTOMER_TRX_ID, NOT PAYMENT_SCHEDULE_ID.

The tool contract (`customer_transactions.py`) projects
`TransactionId` first; the EntitySpec comment even labels
`PAYMENT_SCHEDULE_ID` as "InstallmentId", which no REST field is named.

**S3 (mechanism).** `src/spire/kg/sql_overlay.py`
`"CustomerTransaction"` EntitySpec:
`pk_column="PAYMENT_SCHEDULE_ID"` and
`select_columns[0]=("T","PAYMENT_SCHEDULE_ID")`.

**S4 (root cause).** Hand-authored guess, exactly like the Procurement
stubs; this entity has no KG rows (it is one of the 11 un-drafted
Receivables), so nothing overrode the guess.

**S5 (alternative disproven).** `CUST_TRX_TYPE_SEQ_ID`=34 and
`PAYMENT_SCHEDULE_ID`=1398398 are both real but neither equals 1624374;
only `CUSTOMER_TRX_ID` does.

**Fix (deferred to role map).** `pk_column` and the first select column →
`CUSTOMER_TRX_ID`. Verified amount/date/status columns
(`TRX_NUMBER`→TransactionNumber, `AMOUNT_DUE_ORIGINAL`→TotalOriginalAmount,
`AMOUNT_DUE_REMAINING`→TotalBalanceAmount, `STATUS`→InstallmentStatus,
`CLASS`→TransactionClass, `TRX_DATE`→TransactionDate,
`DUE_DATE`→PaymentScheduleDueDate) all agree — only the id is wrong.

**S8 (miss record).** No Receivables SQL-emitter test exists yet, and the
dipstick prompts had not been run against the KG-backed emitter; this is
the first Receivables column verified end-to-end.

**S9 (cross-link).** Same shape as F-065 (wrong column mapped to a role),
but in an un-drafted entity rather than a filter.

**Resolution (2026-11-19).** CustomerTransaction role map drafted and
seeded into `kg_schema.sql` — `pk_column` and the first column →
`CUSTOMER_TRX_ID`. All 8 columns verified against the pod and REST.
The `_kg_backed_overlay` now reads CustomerTransaction from the KG, so
the emitted SQL projects `T.CUSTOMER_TRX_ID` (matching REST
`TransactionId`). Verified live: `CUSTOMER_ID=300000047368527` returns the
account's transactions.

### F-067 — `ReceivablesInvoice` binds to header stubs: `ENTERED_AMOUNT` absent, `STATUS_TRX` a stub, amount/balance off-header

**Status:** Fixed 2026-11-19 (`Phase3-F060-Amount-Carrier`, role map
seeded).

**S0.** `RA_CUSTOMER_TRX_ALL` has no amount column and no due date, and its
`STATUS_TRX` only ever holds `'OP'` — so the hand-authored
`ReceivablesInvoice` map projected `ENTERED_AMOUNT` (absent) and
`STATUS_TRX` (stub), returning NULL/`'OP'` where REST returns the invoice
amount and status.

**S2 (evidence).** REST "Get the AR invoice with CustomerTransactionId
300000248096352" → `EnteredAmount=39969`, `InvoiceBalanceAmount=0`,
`InvoiceStatus='Complete'`, `BillToCustomerName='ABC Corporation Americas'`,
`BillToCustomerNumber='26370'`, `InvoiceCurrencyCode='GBP'`. Against the
pod:

    -- RA_CUSTOMER_TRX_ALL has NO amount column; ENTERED_AMOUNT -> ORA-00904
    -- STATUS_TRX: only ever 'OP' (206,653 rows) or NULL — never 'Complete'
    -- SUM(AR_PAYMENT_SCHEDULES_ALL.AMOUNT_DUE_ORIGINAL) = 39969 = EnteredAmount
    -- SUM(AR_PAYMENT_SCHEDULES_ALL.AMOUNT_DUE_REMAINING) = 0 = InvoiceBalanceAmount
    -- COMPLETE_FLAG = 'Y' = InvoiceStatus 'Complete'

**Fix.** ReceivablesInvoice role map seeded: `EnteredAmount`/`InvoiceBalanceAmount`
as derived projections over `AR_PAYMENT_SCHEDULES_ALL`; `InvoiceStatus` →
`COMPLETE_FLAG`; `BillToCustomerNumber` → `HZ_CUST_ACCOUNTS.ACCOUNT_NUMBER`.
The `Y`→"Complete" display mapping is F-061-class (cosmetic).

**Verification.** Emitted SQL runs on the pod and returns
`39969` / `0` / `Y` / `26370` / `GBP` / `ABC Corporation Americas` — all
agreeing with REST.

**S8 (miss record).** `ENTERED_AMOUNT` was the Phase-1 sweep's named first
failure for ReceivablesInvoice but was never pursued; the role-map pass
finally resolved it and the two adjacent stubs (`STATUS_TRX`, off-header
amounts).

---

## 5. Receivables role-map findings (2026-11-19, `Phase3-KG-Receivables-RoleMaps`)

The 9 remaining Receivables role maps landed (kg_entity_sql 13→22,
kg_sql_column 71→128, kg_derived_projection 7→9). Several hand-authored
specs were wrong and were fixed in the seed; several roles have no clean
carrier and are dropped. Findings below, fixed-then-open.

### F-068 — `AccountCreditMemo.CreditMemoId` maps to `CUSTOMER_TRX_ID`, not `PAYMENT_SCHEDULE_ID` (FIXED)

**S0.** The hand-authored `AccountCreditMemo` EntitySpec projected
`PAYMENT_SCHEDULE_ID` as `CreditMemoId`. REST `CreditMemoId`=1581292 ==
`AR_PAYMENT_SCHEDULES_ALL.CUSTOMER_TRX_ID` (21), while
`PAYMENT_SCHEDULE_ID`=1343229 on the same row.

**S1 (harm).** SQL ≠ REST at the id column — the same F-066 shape in the
account-credit-memo child.

**S2 (evidence).** REST `get_account_credit_memos(300000047368527)` row:
`CreditMemoId=1581292, CreditMemoNumber=1447816`. Pod:
`CUSTOMER_TRX_ID=1581292, PAYMENT_SCHEDULE_ID=1343229, TRX_NUMBER=1447816`.

**Fix.** Seed `CreditMemoId → CUSTOMER_TRX_ID`; `pk_column` → `CUSTOMER_TRX_ID`.
Verified live: `CUSTOMER_TRX_ID=1581292` returns the memo's rows agreeing
with REST. Also noted: `CreditMemoStatus` (`STATUS`='OP'/'CL') and
`TransactionClass` (`CLASS`='CM') are code-vs-display (F-061 class).

### F-069 — `AccountReceiptApplication` filter reached the account through the wrong path (FIXED)

**S0.** The filter `get_account_receipt_applications.account_id` was
`{alias}.CUSTOMER_TRX_ID IN (SELECT TRX_ID FROM RA_CUSTOMER_TRX_ALL …)` —
wrong twice: `TRX_ID` is not a column (it is `CUSTOMER_TRX_ID`), and the
receipt's own `CUSTOMER_TRX_ID` is the on-account transaction, not the
applied one.

**Fix.** Applications are children of receipts, so the account link is the
receipt path: `{alias}.CASH_RECEIPT_ID IN (SELECT CASH_RECEIPT_ID FROM
AR_CASH_RECEIPTS_ALL WHERE PAY_FROM_CUSTOMER = {value})`. Also
`ReferenceTransactionId` → `APPLIED_CUSTOMER_TRX_ID` (not `PAYMENT_SCHEDULE_ID`).
Verified live: application 994531 → amount 487.2, status 'APP', receipt 621464,
applied tx 1624341 — all equal REST.

### F-070 — `ReceivablesTaxLine` points at the wrong table (FIXED, one open item)

**S0.** The hand-authored spec pointed at `RA_CUST_TRX_LINE_GL_DIST_ALL` and
projected `TAX_LINE_NUMBER`/`TAX_JURISDICTION_CODE`/`TAX_RATE`/
`TAX_RATE_CODE`/`TAX_REGIME_CODE`/`TAX`/`TAXABLE_AMOUNT` — none exist on that
table (9 of 11 projected columns absent). The real source is `ZX_LINES` (the
tax engine), joined `TRX_ID`=`CUSTOMER_TRX_ID`, `TRX_LINE_ID`=
`CUSTOMER_TRX_LINE_ID`, `ENTITY_CODE`='TRANSACTIONS'.

**Fix.** `fusion_table` → `ZX_LINES`; all 10 detail fields map cleanly
(`TAX_LINE_NUMBER`, `TAX_JURISDICTION_CODE`, `TAX_RATE`, `TAX_RATE_CODE`,
`TAX_REGIME_CODE`, `TAX_STATUS_CODE`, `TAX`, `TAX_AMT`, `TAXABLE_AMT`,
`TAX_POINT_DATE`). Filter rewritten to `TRX_ID`/`TRX_LINE_ID`/`ENTITY_CODE`.
Verified live: invoice 1002 line 74 → COUNTY 2.25% / STATE 6.5% exactly equal REST.

**OPEN — canonical-id discrepancy.** REST `CustomerTransactionLineId` on the
tax line is 112/113 (the GL-dist `RA_CUST_TRX_LINE_GL_DIST_ALL.CUSTOMER_TRX_LINE_ID`),
a different id space from `ZX_LINES.TAX_LINE_ID` (9039/9040). The role map
binds the canonical id to `TAX_LINE_ID`; the REST-vs-physical id mismatch is
unresolved. `TaxInclusiveIndicator` ('No') → `TAX_AMT_INCLUDED_FLAG` (code) is
dropped (F-061 class).

### F-071 — `ReceivablesTransactionDFF` overlay name mismatch (FIXED)

**S0.** `sql_overlay.py` named the entity `ReceivablesTransactionDFF`, but the
KG (kg_entity / kg_entity_field / kg_edge / kg_vocabulary / nl_parser /
synthesizer / tests) names it `ReceivablesInvoiceTransactionDFF`. The mismatch
was latent (no KG rows) and surfaced as an ORA-02291 on the first `kg_entity_sql`
insert.

**Fix.** Renamed the overlay EntitySpec + `tool_to_entity` entry to
`ReceivablesInvoiceTransactionDFF`. The DFF role map: `CustomerTrxId` →
`CUSTOMER_TRX_ID`, `__FLEX_Context` → `ATTRIBUTE_CATEGORY`; `ATTRIBUTE1`
(dropped — no populated segment on this pod) and `__FLEX_Context_DisplayValue`
(null) are dropped.

### F-072 — `CustomerAccount` balances have no clean carrier (OPEN)

`TotalOpenReceivablesForAccount` (14418895.83) and
`TotalTransactionsDueForAccount` (15872395) live on the
`/receivablesCustomerAccountActivities` service, not `HZ_CUST_ACCOUNTS`.
`TotalTransactionsDueForAccount` = `SUM(AMOUNT_DUE_REMAINING) WHERE CLASS='INV'`
(verified exact), but `TotalOpenReceivablesForAccount` does **not** reduce to a
single clean SUM (all-class remaining 14418344, INV+DM+CM 14419844 — both off by
~550–950). Both balance roles are **dropped** (no carrier) until the exact
aggregation is pinned. The four identity fields (`AccountId`, `AccountNumber`,
`CustomerName`, `CustomerId`) are bound and verified.

### F-073 — `StandardReceipt` `customer_site` filter names an absent column (OPEN)

`search_standard_receipts.customer_site` → `{alias}.CUSTOMER_SITE = {value}`,
but `AR_CASH_RECEIPTS_ALL` has no `CUSTOMER_SITE` column (only
`CUSTOMER_SITE_USE_ID`, 51, NUMBER). The tool matches `customer_site`
client-side. Deferred — not a role-map (column) item; belongs to the §3.3b
Receivables-filter pass. Also open: `AccountReceipt.State` ('Applied'/'Unapplied')
and `ProcessStatus` ('Open'/'Closed') have no clean single column on
`AR_CASH_RECEIPTS_ALL` — both dropped, documented in KG_ROLE_MAPS.md §AccountReceipt.

### F-074 — `StandardReceipt` nullable join key `AR_CASH_RECEIPTS_ALL.PAY_FROM_CUSTOMER` has 39 NULLs (FIXED)

**Status:** Fixed (2026-11-19). LEFT JOIN with NULL propagation (option 2).

**S0.** `AR_CASH_RECEIPTS_ALL.PAY_FROM_CUSTOMER` — the StandardReceipt role
map's 6th nullable join key — is NULL on **39 of 79,777** rows, so the
entity's inner join `JOIN HZ_CUST_ACCOUNTS CA ON CA.CUST_ACCOUNT_ID =
R.PAY_FROM_CUSTOMER` silently drops those 39 receipts.

**S1 (harm).** SQL ≠ REST at the row-count level: the top-level
`/standardReceipts` list returns receipts with no customer
(`CustomerName`/`CustomerAccountNumber` null), but the emitted SQL joins
`HZ_CUST_ACCOUNTS` + `HZ_PARTIES` to project those two columns and drops
every receipt whose `PAY_FROM_CUSTOMER` is NULL.

**S2 (evidence).** `scripts/validate_kg_schema.py` Q4 check → **FAIL**:
`StandardReceipt AR_CASH_RECEIPTS_ALL.PAY_FROM_CUSTOMER: NULLs = 39`.
Pod confirmation: `COUNT(*) TOTAL = 79777`, `COUNT(PAY_FROM_CUSTOMER)
NON_NULL = 79738` → 39 NULL. Characterization by `STATUS`:
`UNID` 25 (321,177.32), `REV` 10 (10,625,331.37), `NSF` 2 (21,000,000),
`APP` 2 (1,602.95).

**S3 (mechanism).** `src/spire/kg/sql_overlay.py` StandardReceipt
`base_joins` = `JOIN HZ_CUST_ACCOUNTS CA ON CA.CUST_ACCOUNT_ID =
R.PAY_FROM_CUSTOMER` (+ `JOIN HZ_PARTIES HP ON HP.PARTY_ID = CA.PARTY_ID`).
`KG_ROLE_MAPS.md` §StandardReceipt recorded `PAY_FROM_CUSTOMER` nullable
(Y) as the "6th nullable join key" but never ran the NULL-count; the §3.4
validator is the first command to run it, and it is non-zero.

**S4 (root cause).** Unidentified (UNID), reversed (REV), bounced (NSF)
and two applied (APP) receipts legitimately carry no `PAY_FROM_CUSTOMER`.
Unlike `PO_HEADERS_ALL.VENDOR_ID` (§4.1 — where the 5 NULL rows are all
`DOCUMENT_STATUS='INCOMPLETE'` and correctly dropped), these 39 are not
obviously "non-real" receipts, so the inner-join drop is not clearly
correct.

**S5 (alternative disproven).** Not a validator bug — the same count is
reproduced directly on the pod (39 NULL of 79,777), and the other five
nullable keys all report 0 under the same checker.

**Decision (2026-11-19).** Option 2 — switch StandardReceipt to LEFT JOIN
with NULL propagation. Unlike §4.1's PO case (5 NULLs, all
`DOCUMENT_STATUS='INCOMPLETE'`, correctly dropped), these 39 receipts are
**not** non-real: REST's top-level `/standardReceipts` returns them with
`CustomerName`/`CustomerAccountNumber` null (verified on receipt
`300000066476398`, `STATUS='REV'`). So the correct behavior is to **keep**
them with NULL customer fields — an INNER JOIN drop is a row-count
mismatch, and Q4's "LEFT JOIN + NULL propagation rejected" rule applies to
join keys meant to be non-null, not to a column whose NULLs REST itself
projects as null.

**Fix applied.** `src/spire/kg/sql_overlay.py` StandardReceipt `base_joins`
→ `LEFT JOIN HZ_CUST_ACCOUNTS` + `LEFT JOIN HZ_PARTIES`. The
`NULLABLE_KEYS` entry for StandardReceipt was removed from
`scripts/validate_kg_schema.py` (no INNER join to guard); its absence is
documented in the list header.

**Verification.** Emitted SQL shape (`LEFT JOIN …`) returns **79,777** rows
(the full `AR_CASH_RECEIPTS_ALL` count) vs **79,738** under the old INNER
JOIN — the 39 null-customer receipts are kept, not dropped. Receipt
`300000066476398` is returned with NULL `ACCOUNT_NUMBER`/`PARTY_NAME`,
matching REST's `CustomerName`/`CustomerAccountNumber` = null.
`scripts/validate_kg_schema.py` → `Result: PASS`. Regression test
`test_standard_receipt_uses_left_join_for_nullable_pay_from_customer` in
`tests/test_sql_emitter.py`.

**S8 (miss record).** The Receivables role-map pass flagged the key as
nullable but did not run the Q4 NULL-count; the §3.4 self-check (this
window) is the first command to run it.
