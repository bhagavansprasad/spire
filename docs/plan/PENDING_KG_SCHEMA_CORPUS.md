# PENDING — KG schema corpus (remaining role maps + §3.1–3.3 build)

**For:** the next window resuming this work.
**Created:** 2026-11-18, after 11 of 22 role maps were drafted.
**Companions:** `HANDOVER_KG_SCHEMA.md` (Phase 1 strategy/design), `HANDOVER_KG_SCHEMA_PHASE2.md` (Tasks 1–3 + reversals), `KG_ROLE_MAPS.md` (drafted role maps), `SCHEMA_DISCOVERY_METHOD.md` (procedure).

This document is the **pending-work register**. The handovers carry what was done and why; this carries what is left and in what order. When an item here is finished, strike it and cite where its result landed.

---

## 0. Status snapshot (2026-11-19)

| Item | Status |
|---|---|
| Task 1 — module table lists | complete |
| Task 2 — per-table column lists | complete (`t_task2_all.txt`, 19 tables) |
| Task 3 — HR-side gap | closed (`PER_ALL_PEOPLE_F` found under FUSION) |
| Task 4 — role maps | **22 of 22** drafted (all 11 Receivables done 2026-11-19: ReceivablesInvoiceLine, CreditMemo, StandardReceipt, AccountReceipt, CustomerAccount, AccountCreditMemo, AccountReceiptApplication, ReceivablesTaxLine, ReceivablesInvoiceTransactionDFF) |
| §3.1 — KG schema additions (`kg_entity_sql`, `kg_sql_column`, `kg_derived_projection`) | **complete** — now **22/128/9** rows (was 13/71/7 at PR #213); all 22 entities drafted |
| §3.2 — `rebuild_kg.py` build step | **superseded** (R-9) — hermetic static seed in `kg_schema.sql`, executed by `rebuild_kg.py` |
| §3.3 — emitter reads from KG | **3.3a complete**; **3.3b drafted-entities done** (F-064, F-065); **3.3b Receivables** now auto-reads all 22 entities with KG rows |
| §3.4 — build self-check | **complete** — `scripts/validate_kg_schema.py` (9 derived projections validated; 6 nullable keys checked; 1 open: F-074) |

### 0.2 Branch / merge record (2026-11-19)

- **PR #212** (`KG-Schema-Corpus`) merged to `master` (merge commit
  `6755d3d`, 2026-11-19) — carried 11/57/4 SQL satellites, gap register
  reversed.
- **PR #213** (`Phase3-F060-Amount-Carrier`) merged to `master` (merge
  commit `069fb40`) — F-060/F-064/F-065 fixed + CustomerTransaction /
  ReceivablesInvoice role maps (F-066/F-067).
- **PR #214** (`Phase3-KG-Receivables-RoleMaps`) merged to `master`
  (merge commit `a288925`, 2026-11-19) — the 9 remaining Receivables
  role maps landed (kg_entity_sql 13→22, kg_sql_column 71→128,
  kg_derived_projection 7→9), plus F-068..F-073.
- **PR #215** (`Phase3-Validate-Kg-Schema`) merged to `master` (merge
  commit `29ed948`, 2026-11-19) — §3.4 build self-check
  `scripts/validate_kg_schema.py` + new finding F-074 (StandardReceipt
  `PAY_FROM_CUSTOMER` 39 NULLs).
- Satellite counts now: `kg_entity_sql`=22, `kg_sql_column`=128,
  `kg_derived_projection`=9.
- **Next branch** (next window): `Phase3-Fix-Nullable-Keys` off `master`
  — resolve F-074 first.

### 0.3 F-060 — FIXED 2026-11-19 (branch `Phase3-F060-Amount-Carrier`)

`PO_LINES_ALL.AMOUNT` is a stub column (NULL on 99.96% of 315,970 rows),
so `PurchaseOrderLine.amount` bound wrong: emitted SQL returned NULL where
REST returns the real line amount (33000/8250 on PO 2144). **Fixed** — the
carrier is a derived `UNIT_PRICE × QUANTITY`, not `TAX_EXCLUSIVE_PRICE`
(the latter is a *unit* price, populated on only 14.9% of rows, and equals
`UNIT_PRICE`). Three derived projections changed:
`PurchaseOrderLine.Ordered` → `L.UNIT_PRICE * L.QUANTITY`;
`PurchaseOrder.Ordered` → `SUM(L.UNIT_PRICE * L.QUANTITY)`;
`PurchaseOrderLine.Total` → `(L.UNIT_PRICE * L.QUANTITY) + tax`.
Row counts moved `kg_sql_column` 57→56, `kg_derived_projection` 4→5.
`SCHEMA_DISCOVERY_METHOD.md` §6 now requires a population check
("existence ≠ populated"). Full record: `docs/fixes/FIX_PLAN.md` F-060.

**Two new findings from the same walk** (recorded in FIX_PLAN, not fixed
this window): **F-062** — `POSchedule.amount` binds to
`PO_LINE_LOCATIONS_ALL.AMOUNT`, also a stub (NULL 99.95%), and the table
has no `UNIT_PRICE`, so the schedule extended amount needs a join back to
`PO_LINES_ALL` via `PO_LINE_ID`. **F-063** — `Total`/`TotalTax` return
NULL (not 0) when the schedule tax is NULL (observation, pre-existing).


### 0.1 Revisions recorded 2026-11-19

These supersede earlier text; the old lines are **not edited** (verified maps
are append-only). They are the "facts not in the docs" carried forward from
the resume brief.

- **R-9 — the build is hermetic / static seed.** Phase 1 §3.2 (and this
  document's §3, and `HANDOVER_KG_SCHEMA.md` §3.2) describe the build as
  querying `ALL_TAB_COLUMNS` on the pod at build time. That is superseded.
  Rows are static `INSERT`s in `scripts/sql/kg_schema.sql`, created on every
  `python scripts/rebuild_kg.py`. Pod re-verification is a separate on-demand
  script (proposed, not yet written), run at release/CI.
- **Q1 resolved — `pk_column` goes on the new satellite `kg_entity_sql`, not
  on `kg_entity`.** Reason: `kg_entity`'s 22 seed rows are positional
  (`INSERT INTO kg_entity VALUES (...)` with no column list); adding columns
  breaks them. `kg_entity_sql(entity_name, fusion_table, pk_column)` matches
  the existing satellite pattern (`kg_entity_tool`, `kg_entity_filter`,
  `kg_entity_field`). `KG_FIELD_TRANSLATION.md` §4 still says "on kg_entity"
  — that line is stale; the satellite is the decision.

**Drafted (11):** Supplier, Contact, Site, Address, Classification (Supplier module); Buyer, PurchaseOrder, PurchaseOrderLine, POSchedule, PODistribution (Procurement); Invoice (Payables).

**Remaining (11, all Receivables):** ReceivablesInvoice, ReceivablesInvoiceLine, ReceivablesTaxLine, ReceivablesTransactionDFF, CreditMemo, CustomerAccount, CustomerTransaction, AccountCreditMemo, AccountReceipt, AccountReceiptApplication, StandardReceipt.

---

## 1. Pending — the 11 Receivables role maps

**DONE 2026-11-19 (`Phase3-KG-Receivables-RoleMaps`).** All 11 are now
drafted and seeded; full sections in `KG_ROLE_MAPS.md` (Receivables
subsection). Counts moved to kg_entity_sql=22 / kg_sql_column=128 /
kg_derived_projection=9. Open items recorded in FIX_PLAN §5: F-072
(CustomerAccount balances — no clean carrier), F-073 (StandardReceipt
`customer_site` filter + AccountReceipt State/ProcessStatus no-carrier),
and the ReceivablesTaxLine canonical-id discrepancy (F-070 OPEN).

Each follows the four-step pattern (Phase 2 §4): dump spec → verify every projected column against `t_task2_all.txt` → verify every join key both sides → draft. Header rules in `KG_ROLE_MAPS.md` apply (never trust the sweep; verify every column; cite evidence; flag NULL-returning roles).

**Known trouble spots, per entity (to be confirmed, not assumed):**

| Entity | `fusion_table` (to verify) | Anticipated shape |
|---|---|---|
| ReceivablesInvoice | `RA_CUSTOMER_TRX_ALL` | ~259 cols incl. a large DFF block. Phase 1 sweep named `P.ENTERED_AMOUNT` — verify whether that role is still projected (R-3 stale-flag shape) and whether a direct carrier exists. |
| ReceivablesInvoiceLine | `RA_CUSTOMER_TRX_LINES_ALL` | Likely derived total/tax roles; verify line-amount carriers. |
| ReceivablesTaxLine | `RA_CUST_TRX_LINE_GL_DIST_ALL` | Sweep named `T.TAXABLE_AMOUNT` — verify; may be a DFF-block attribute under a different name. |
| ReceivablesTransactionDFF | `RA_CUSTOMER_TRX_ALL` (DFF) | The DFF block itself. Phase 1 named `RA_CUSTOMER_TRX_ALL.ATTRIBUTE1` as wrong — resolve whether the attribute exists under a different name or is not carried in the view. This is the hardest discovery case; do it with the method's §9.4 DFF diagnostic. |
| CreditMemo | `RA_CUSTOMER_TRX_ALL` | Sweep named `C.ENTERED_AMOUNT` — same stale/understated check as ReceivablesInvoice. |
| CustomerAccount | `AR_PAYMENT_SCHEDULES_ALL` (verify) | Verify table; confirm which of the 22 entities maps here. |
| CustomerTransaction | `AR_PAYMENT_SCHEDULES_ALL` (verify) | Verify table + join to `RA_CUSTOMER_TRX_ALL`. |
| AccountCreditMemo | `AR_PAYMENT_SCHEDULES_ALL` / `AR_CASH_RECEIPTS_ALL` (verify) | Verify which table; likely a payment-schedule slice. |
| AccountReceipt | `AR_CASH_RECEIPTS_ALL` | Sweep named `R.AMOUNT_APPLIED` — verify; amount may live on `AR_RECEIVABLE_APPLICATIONS_ALL`. |
| AccountReceiptApplication | `AR_RECEIVABLE_APPLICATIONS_ALL` | Verify application amount carriers. |
| StandardReceipt | `AR_CASH_RECEIPTS_ALL` | Verify; shares table with AccountReceipt — two entities, one table, different joins (Q3 note). |

**Two caution flags from Phase 2 §4 still apply:**
- **ReceivablesInvoice and the DFF entities** — `RA_CUSTOMER_TRX_ALL` has 263 cols with a DFF extension block; the "missing" attributes may exist under different names or not be carried. Verify both before drafting.
- **PODistribution precedent (R-7/R-8):** expect at least one role with **no carrier at all** in the Receivables cluster (as `PERCENTAGE` was for PODistribution). When it happens, the decision is drop / derive-from-parent / flag — a named decision, recorded in the role map's observations.

**Nullable join keys expected:** the Receivables joins (payment schedules → customer trx, receipts → applications) may add nullable keys. Each nullable left-side key gets a Q4 build self-check entry. Current known nullable keys are 3 (§4 below); extend the list as each entity is drafted.

---

## 2. Pending — §3.1 KG schema additions

Design of record: Phase 1 §3.1 (still authoritative). Decisions settled in Phase 2 §5: Q2, Q3, Q4, Q6 resolved; **Q1 and Q5 deferred to this build**.

**Work items:**

1. **`kg_entity` columns** — add `fusion_table VARCHAR2(64)` and (per Q1, to be settled now) `pk_column VARCHAR2(64)`. Populated by the build step from the verified role maps.
2. **`kg_sql_column` table** — `(entity_name, physical_table, column_name, data_type, data_length, is_default_projection CHAR(1))`, PK `(entity_name, physical_table, column_name)`, FK to `kg_entity(entity_name)`. Per Phase 2 Q3: same physical table under multiple entities yields multiple rows; row count is "sum over entities of all joined-table columns," not "sum of all tables' columns."
3. **`kg_derived_projection` table** — `(entity_name, role_name, expression VARCHAR2(4000), is_default_projection CHAR(1))`, PK `(entity_name, role_name)`. Expression is a correlated scalar subquery over already-validated columns (Phase 2 Q6).
4. **The curated role config** — the one hand-authored input: per entity, role → physical column (or derived expression). Seeded from the 11 drafted role maps. The mapping is chosen once, against the real column list, not guessed. This replaces `sql_overlay.py`'s hand-authored physical names.
5. **Q1 decision** — `pk_column` on `kg_entity` (recommended) vs left in the overlay. Decide with all rows visible; a derived role has no physical column, so confirm the split between `kg_entity`, `kg_sql_column`, and `kg_derived_projection`.

**Seed data available now:** 11 entities, exercising direct columns (many), derived projections (PurchaseOrder `amount`; PurchaseOrderLine `total_tax`, `total`; PODistribution `status`), multi-table joins (PurchaseOrder 4-join, Buyer 2-join, Invoice 1-join, Contact 1-join, Address 1-join), and no-join entities (Site, Classification, POSchedule). Sufficient to prove every schema feature before the DFF cases add variables.

---

## 3. Pending — §3.2 build step (`rebuild_kg.py`)

For each entity's `fusion_table`, query `ALL_TAB_COLUMNS` on the pod and write into `kg_sql_column`; write derived expressions into `kg_derived_projection`; set `is_default_projection` from the curated role config. The build is where a wrong column becomes a build failure, not a runtime surprise.

**Work items:**
- The build step itself, idempotent (re-runnable against the pod).
- §3.4 self-check wired into the build (see §4 below) — non-zero NULL join keys or absent columns fail the build.
- CI hook so the build runs on the KG, not only locally.

---

## 4. Pending — §3.4 build self-check

Per Phase 2 Q4: every nullable join key gets a build check counting NULLs on the joining-side table; require zero; non-zero fails the §3.4 build. LEFT JOIN + NULL propagation remains rejected.

**Status 2026-11-19 — complete.** The self-check is now
`scripts/validate_kg_schema.py` (on-demand release/CI). It (a) walks the
9 `kg_derived_projection` expressions and validates every referenced
physical column — a `kg_sql_column` carrier is a validated measure; a
column not in `kg_sql_column` is checked for existence on the pod (a join
key); a column in neither is a MISSING-column failure (Q6) — and (b) runs
the 6 nullable-key NULL-count checks below (Q4). Run it with
`/home/bhagavan/virtenv/spire/bin/python scripts/validate_kg_schema.py`
(`--kg-only` skips the pod checks).

**Known nullable join keys (6), encoded as checks:**

| Entity | Join key column | Check |
|---|---|---|
| Contact | `POZ_SUPPLIER_SITES_ALL_M.PARTY_SITE_ID` | count NULLs = 0 |
| PurchaseOrder | `PO_HEADERS_ALL.VENDOR_ID` | count NULLs = 0 **except** `DOCUMENT_STATUS='INCOMPLETE'` (see §4.1) |
| Invoice | `AP_INVOICES_ALL.VENDOR_ID` | count NULLs = 0 |
| ReceivablesInvoice | `RA_CUSTOMER_TRX_ALL.BILL_TO_CUSTOMER_ID` | count NULLs = 0 |
| CreditMemo | `RA_CUSTOMER_TRX_ALL.BILL_TO_CUSTOMER_ID` | count NULLs = 0 (shares the physical column with ReceivablesInvoice) |
| StandardReceipt | `AR_CASH_RECEIPTS_ALL.PAY_FROM_CUSTOMER` | count NULLs = 0 **— but the pod has 39** (see §4.2, F-074) |

The mechanism is **per-key, not per-entity**. The self-check also walks
`kg_derived_projection` expressions, validating every physical column
inside each expression against `kg_sql_column` (Phase 2 Q6) and against
the pod for join keys not in `kg_sql_column`.

### 4.1 Revision 2026-11-19 — `PO_HEADERS_ALL.VENDOR_ID` is not zero-NULL

The "count NULLs = 0" check for `PO_HEADERS_ALL.VENDOR_ID` **fails on the
pod**: 5 rows have NULL `VENDOR_ID`, all with `DOCUMENT_STATUS='INCOMPLETE'`
(PO_HEADER_IDs `300000186856532`, `300000186856537`, `300000192322260`,
`300000265577099`, `300000303465673`; SEGMENT1 `163737`, `711231`, `52257`,
`NL411565`, `PU283348`).

**Decision (option 1):** accept the omission. An incomplete PO with no vendor
is not yet a "real" PO; the inner `JOIN POZ_SUPPLIERS S ON S.VENDOR_ID =
P.VENDOR_ID` silently drops exactly these 5 rows, which is correct. LEFT JOIN
+ NULL propagation remains rejected (Q4). The self-check refines from "zero
NULLs" to "zero NULLs **except** on `DOCUMENT_STATUS='INCOMPLETE'` rows."

Evidence: `t_verify_nullable.txt` (counts `0 / 5 / 0`),
`t_verify_null_vendor_po.txt` (the 5 rows, all INCOMPLETE).

### 4.2 Revision 2026-11-19 — `AR_CASH_RECEIPTS_ALL.PAY_FROM_CUSTOMER` is not zero-NULL

The "count NULLs = 0" check for `AR_CASH_RECEIPTS_ALL.PAY_FROM_CUSTOMER`
(the StandardReceipt 6th nullable key) **fails on the pod**: 39 rows of
79,777 have NULL `PAY_FROM_CUSTOMER`, by `STATUS`: `UNID` 25 (321,177.32),
`REV` 10 (10,625,331.37), `NSF` 2 (21,000,000), `APP` 2 (1,602.95).

**Not yet decided** (open, F-074). Unlike §4.1's PO case — where all 5
NULL rows are `DOCUMENT_STATUS='INCOMPLETE'` and dropping them is clearly
correct — these 39 are unidentified / reversed / bounced / applied
receipts, which are not obviously "non-real". The inner
`JOIN HZ_CUST_ACCOUNTS CA ON CA.CUST_ACCOUNT_ID = R.PAY_FROM_CUSTOMER`
drops them; whether that is correct (option 1, with a documented
`exclude` carve-out) or should become LEFT JOIN + NULL propagation or an
explicit filter is a separate decision. Until it lands,
`scripts/validate_kg_schema.py` fails on this key by design.

Evidence: `scripts/validate_kg_schema.py` (Q4 check → FAIL, NULLs = 39);
pod `COUNT(*) TOTAL = 79777`, `COUNT(PAY_FROM_CUSTOMER) NON_NULL = 79738`.

---

## 5. Pending — §3.3 emitter change

`sql_overlay.py`'s `_ENTITIES[*].select_columns` becomes a KG lookup at import time (`SELECT column_name FROM kg_sql_column WHERE entity_name=? AND is_default_projection='Y'`); `predicate_template` columns resolve via the same lookup plus alias translation (Phase 2 Q2 — three steps: tool→entity, base_joins→alias→table map, `kg_sql_column` lookup). The emitter reads columns from the KG, not from literals.

**Q5 deferred here:** which of the 22 entities the SQL emitter actually produces. First action: `grep -l sql_overlay src/spire/mcp_server/tools/*.py` to identify overlay-consuming tools. Not blocking role maps; blocking §3.3's testability.

**Q6 emitter branch:** role → `kg_sql_column` lookup, else role → `kg_derived_projection` expression, else error.

---

## 6. Pending — what goes away when §3.1–§3.4 land

Per Phase 1 §3.5 (restated so the cleanup is not forgotten):
- `src/spire/rendering/schema_corpus.py` — delete (discarded runtime gate).
- `sql_emitter.py`'s `_corpus_or_comment` and `has_column` import — delete.
- The `("P", "AMOUNT")` removal comment in `sql_overlay.py` — obsolete.
- `docs/design/SQL_EMITTER_SCHEMA_CORPUS.md` — add a superseded-by header pointing at the handovers.

**Status 2026-11-19 (verified):** the first two and the last are already
gone from the tree — `schema_corpus.py` and `docs/design/SQL_EMITTER_SCHEMA_CORPUS.md`
were never committed (no git history) and `sql_emitter.py` has no
`corpus`/`has_column` reference. The superseded-by header is therefore
moot (the file to carry it no longer exists). The only surviving item is
the hand-authored stub columns in `sql_overlay.py` — `PurchaseOrder`
`("P", "AMOUNT")` (line ~172) and `PurchaseOrderLine` `("L", "AMOUNT")`,
`("L", "TOTAL_TAX")`, `("L", "TOTAL")` (line ~233). These are dead for
the KG-backed path (`_kg_backed_overlay` replaces select_columns for both
drafted entities) but still wrong if anything reads `OVERLAY` directly.
Clean them up in §3.3b, which revisits the hand-authored overlay anyway.

---

## 7. Deferred questions (named, not lost)

| Q | Topic | Status | Where decided |
|---|---|---|---|
| Q1 | `pk_column` placement on `kg_entity` vs overlay | **deferred to §3.1 build** | decide at §2 above |
| Q2 | `predicate_template` surface | resolved (Phase 2) — `FilterSpec` at `sql_overlay.py:23`, `_FILTERS` keyed by `(tool, filter)` | Phase 2 §5 |
| Q3 | `kg_sql_column` keying | resolved (Phase 2) — PK `(entity_name, physical_table, column_name)` | Phase 2 §5 |
| Q4 | nullable join keys | resolved (Phase 2) — per-key build self-check, list extends | §4 above |
| Q5 | which entities the emitter produces | **deferred to §3.3** | §5 above |
| Q6 | roles with no direct carrier | resolved (Phase 2) — `kg_derived_projection` | §2 item 3 above |

---

## 8. Recommended order of work

1. **Decide (A) or (B)** — keep drafting Receivables, or build §3.1–3.2 now against the 11 seeded entities. Recommendation: **(B)** — the 11 seeded entities exercise every schema feature; proving the schema before the DFF cases is cheaper than debugging schema-shape and DFF together.
2. If (B): §2 → §3 → §4 (build with self-check) → §5 (emitter) → §6 (cleanup).
3. Then resume role maps: ReceivablesInvoice first, ReceivablesTransactionDFF last (hardest discovery).

---

*End of pending register.*
