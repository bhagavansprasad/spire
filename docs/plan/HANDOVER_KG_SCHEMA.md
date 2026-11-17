# HANDOVER — KG schema corpus (feed Spire the columns)

**For:** a fresh window picking up this work.
**From:** the window that diagnosed the `P.AMOUNT` failure and reversed its approach.
**Branch:** `SQL-Emitter-Multifield-Fix`, uncommitted changes present (see §5). Nothing from the discarded approach is committed.
**Design doc of record:** `docs/design/SQL_EMITTER_SCHEMA_CORPUS.md` is **superseded** by this handover. Do not build from it. It is retained as "the discarded approach, for the record".

---

## 0. How to use this file

This is the resume point for a new window. Read it top to bottom.
Sections 1–2 are the state. Sections 3–4 are the design and the first tasks. Section 5 is the tree, so a new window knows what to clean up before starting. Sections 6–7 are reads and a `WORKING_STYLE.md` update made alongside this file.

The single most important sentence: **the runtime-gate approach this window produced is discarded; do not continue it.** Section 5 says what to revert. Section 3 says what to build instead.

---

## 1. The problem, in one paragraph

`sql_overlay.py` is a hand-authored model of the physical Fusion schema. It names tables (`EntitySpec.fusion_table`), SELECT columns (`EntitySpec.select_columns`), WHERE columns (`FilterSpec.predicate_template`), and aggregation measures. None of those names is validated against the pod. On `fa-euth-dev63-saasfademo1` two have been observed wrong (`PO_HEADERS_ALL.AMOUNT`, `RA_CUSTOMER_TRX_ALL.ATTRIBUTE1`), and a `WHERE 1=0` sweep of every entity's `select_columns` found **10 of 22 entities** with at least one invalid column. The overlay's hand-authored columns are the cause; a validator is a symptom-treater. The fix is to stop hand-authoring columns and have the KG carry them, learned from the pod at KG-build time. The emitter reads columns from the KG.

The strategy sentence, from the user: *"PRISM will never know what columns are there in the Fusion tables. Somebody has to feed it. Somebody has to make it learn. … Then spire can emit any kind of column that they are asking for."*

## 2. What is currently known

**Modules Spire supports (four):** Supplier, Procurement (PO), Payables (AP), Receivables (AR).

**Entities Spire exposes (22), from `sql_overlay.py`'s `tool_to_entity`:**
Supplier, Address, Site, Classification, Contact, PurchaseOrder, PurchaseOrderLine, POSchedule, PODistribution, Buyer, Invoice, ReceivablesInvoice, ReceivablesInvoiceLine, ReceivablesTaxLine, ReceivablesTransactionDFF, CreditMemo, CustomerAccount, CustomerTransaction, AccountCreditMemo, AccountReceipt, AccountReceiptApplication, StandardReceipt.

**Tables the overlay *names* (to be verified, not trusted):**
`POZ_SUPPLIERS`, `POZ_SUPPLIER_SITES_ALL_M`, `POZ_SUPPLIER_CONTACTS`, `POZ_BUS_CLASSIFICATIONS`, `HZ_PARTIES`, `HZ_PARTY_SITES`, `HZ_LOCATIONS`, `PO_HEADERS_ALL`, `PO_LINES_ALL`, `PO_LINE_LOCATIONS_ALL`, `PO_DISTRIBUTIONS_ALL`, `PER_ALL_PEOPLE_F`, `AP_INVOICES_ALL`, `RA_CUSTOMER_TRX_ALL`, `RA_CUSTOMER_TRX_LINES_ALL`, `RA_CUST_TRX_LINE_GL_DIST_ALL`, `AR_PAYMENT_SCHEDULES_ALL`, `AR_CASH_RECEIPTS_ALL`, `AR_RECEIVABLE_APPLICATIONS_ALL`.
Some of these are guesses at the table level, exactly as `AMOUNT` was a guess at the column level. The first task is to verify them.

**The 10-entity validation sweep (`WHERE 1=0` per entity, one failure named per entity — first-failure-only):**

| Entity | First failing column |
|---|---|
| Contact | CT.VENDOR_ID |
| PurchaseOrder | P.AUTHORIZATION_STATUS |
| ReceivablesInvoice | P.ENTERED_AMOUNT |
| PurchaseOrderLine | L.STATUS_LOOKUP_CODE |
| POSchedule | S.BILLED_QUANTITY |
| PODistribution | D.STATUS |
| Buyer | B.EMAIL_ADDRESS |
| ReceivablesTaxLine | T.TAXABLE_AMOUNT |
| CreditMemo | C.ENTERED_AMOUNT |
| AccountReceipt | R.AMOUNT_APPLIED |

This is **first-failure-per-entity**, not exhaustive. Oracle named the first invalid identifier and stopped. The true per-entity count is at least this and may be higher. `P.AMOUNT` is not in the list: on the sweep for `PurchaseOrder`, `P.AUTHORIZATION_STATUS` failed first. Whether `P.AMOUNT` is also invalid on the pod is unresolved — the sweep cannot answer it, and it should not be assumed either way.

**The corpus (`docs/reference/data/oracle_fusion_schema_updated_tables.xlsx`):**
sheet `Retained Columns`, header `(SCHEMA_NAME, TABLE_NAME, COLUMN_NAME)`, 10,518 rows, **lowercase**, `OWNER='FUSION'` only.
Confirmed coverage: `po_headers_all` 288, `po_lines_all` 262, `po_line_locations_all` 277, `po_distributions_all` 217, `ra_customer_trx_all` 259, `ra_cust_trx_line_gl_dist_all` 97, `ar_cash_receipts_all` 139, `poz_supplier_contacts` 70.
**Not** covered: `per_all_people_f` (zero rows — HR is a different owner; a `FUSION`-filtered export omits it; Oracle documents its object owner as `PER`, schema `FUSION`, so the export's filter dropped it).

## 3. What must be built

### 3.1 The KG schema additions

Two changes, both to the existing KG (`scripts/sql/kg_schema.sql`):

**`kg_entity.fusion_table`** — a new column on the existing entity table. Holds the physical table or view name for the entity (`PurchaseOrder` → `PO_HEADERS_ALL`). This is the one fact `sql_overlay.py` currently owns that belongs in the KG. It is populated by Task 4 (§4) from the verified module table lists.

**`kg_sql_column`** — new table:

| Column | Type | Description |
|---|---|---|
| `entity_name` | `VARCHAR2(64)` | e.g. "PurchaseOrder" |
| `physical_table` | `VARCHAR2(64)` | e.g. "PO_HEADERS_ALL" |
| `column_name` | `VARCHAR2(64)` | e.g. "SEGMENT1" |
| `data_type` | `VARCHAR2(32)` | |
| `data_length` | `NUMBER` | |
| `is_default_projection` | `CHAR(1)` | 'Y' for the columns the overlay currently selects |

Primary key `(entity_name, physical_table, column_name)`. Foreign key to `kg_entity(entity_name)`.

### 3.2 The build step

`scripts/rebuild_kg.py` gains a step that, for each entity's `fusion_table`, queries `ALL_TAB_COLUMNS` on the pod and writes the result into `kg_sql_column`. The `is_default_projection` flag is set from a curated list (a small config, not the query) — "these are the columns Spire projects by default for this entity". That list is the only hand-authored piece left; it names columns by **role** ("the PO total", "the PO status"), not by physical column name. The mapping from role to physical column is chosen by a human once, at KG build, from the real column list the query returns.

### 3.3 The emitter's change

`sql_overlay.py`'s `_ENTITIES[*].select_columns` becomes a lookup at import time: `SELECT column_name FROM kg_sql_column WHERE entity_name=? AND is_default_projection='Y'`. The `predicate_template`'s columns become the same lookup — every `{alias}.COLUMN` in a template is resolved via `kg_sql_column` before formatting. The emitter reads columns from the KG, not from literals.

### 3.4 The validator's new role

The script `scripts/validate_overlay_columns.py` (present, untracked, from this window) becomes the **KG-build self-check**: at rebuild time, does `kg_sql_column` match the pod for every table Spire names? It is no longer a runtime gate on the emitter. It is a CI check on the KG build. It reports, per entity, every absent column and candidate replacements from the real column list.

### 3.5 What goes away when 3.1–3.4 land

- `src/spire/rendering/schema_corpus.py` — obsolete (was the runtime gate).
- `sql_emitter.py`'s `_corpus_or_comment` and its `has_column` import — obsolete.
- The `("P", "AMOUNT")` removal comment in `sql_overlay.py` — obsolete; the column was never in the KG to begin with.
- `docs/design/SQL_EMITTER_SCHEMA_CORPUS.md` — superseded by this handover; add a header pointing here.

## 4. Data collection — the first tasks of the new window

### Task 1 — the module table lists

For each module prefix, query the pod for tables and views. Supplier:

```sql
SELECT OWNER, TABLE_NAME, 'TABLE' FROM ALL_TABLES
WHERE OWNER='FUSION' AND (TABLE_NAME LIKE 'POZ\_%' ESCAPE '\'
                       OR TABLE_NAME LIKE 'HZ\_%'  ESCAPE '\')
UNION ALL
SELECT OWNER, VIEW_NAME, 'VIEW' FROM ALL_VIEWS
WHERE OWNER='FUSION' AND (VIEW_NAME LIKE 'POZ\_%' ESCAPE '\'
                       OR VIEW_NAME LIKE 'HZ\_%'  ESCAPE '\')
ORDER BY 2
```

The same query with `PO\_%` for Procurement, `AP\_%` for Payables, `RA\_%`/`AR\_%` for Receivables. The output verifies the overlay's table names and reveals any it misses (e.g. site-to-BU assignment tables the overlay does not currently name).

### Task 2 — the per-table column lists

For each table named in `sql_overlay.py`'s `_ENTITIES`, query `ALL_TAB_COLUMNS`:

```sql
SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE, NULLABLE, COLUMN_ID
FROM ALL_TAB_COLUMNS
WHERE OWNER='FUSION' AND TABLE_NAME='PO_HEADERS_ALL'
ORDER BY COLUMN_ID
```

`ORDER BY COLUMN_ID` matters — it returns columns in the view's own order, which is more readable than alphabetical. Per table, one query. Paste each. This is the real column set for `kg_sql_column`.

### Task 3 — the HR-side gap

`per_all_people_f` is not in the FUSION-owned corpus. Run the Task 1 query with `OWNER='HR'` or `OWNER='PER'` (or no owner filter) to find the actual owner of `PER_ALL_PEOPLE_F`. Oracle documentation confirms it is `Object owner: PER`, `Schema: FUSION` — so the query against `OWNER='FUSION'` should have found it, and did not. Either the pod's view lives under a different owner or the export missed it. Resolve before `Buyer` can be KG-driven.

### Task 4 — collect the field-role map

For each entity, the human chooses which real columns are "the default projection". This is the one hand-authored input to the new design. It replaces `select_columns`'s hand-authored physical names with curated role names, and the physical name comes from `kg_sql_column`. That choice is made against Task 2's output — the real columns — not against a guess.

## 5. State of the tree

**Branch:** `SQL-Emitter-Multifield-Fix`. Has unmerged commits from prior work (the multifield fix at `5a853e6`, its resolution record at `15d81ca`, and a tail of docs/tooling commits). Nothing from this window's discarded approach is committed.

**Uncommitted, in the working tree (do not commit; do not carry forward):**
- `src/spire/rendering/schema_corpus.py` — the runtime gate's loader. Superseded.
- `src/spire/rendering/sql_emitter.py` — modified with `_corpus_or_comment` and the `has_column` import. Superseded.
- `src/spire/kg/sql_overlay.py` — modified: `("P", "AMOUNT")` removed, a comment added. Superseded by the KG approach.
- `docs/design/SQL_EMITTER_SCHEMA_CORPUS.md` — the discarded design. Retain as historical record; add a superseded-by header when the new design lands.
- `scripts/validate_overlay_columns.py` — the validator. Its role changes to KG-build self-check; keep it, revise it.
- Untracked scratch: `request.xml`, `response.xml`, `runsql.sh`, `schema_report.csv`, `oracle_fusion_schema_updated_tables.xlsx`. The `.xlsx` and `.csv` are corpus artifacts; keep them out of commits until the design says where they live. The others are scratch.
- `build_context.py` — modified from a prior window, unrelated. Leave alone.

**Recommended first action of the new window:** revert the three superseded source files to `HEAD`, so the new work starts from a clean `sql_overlay.py` and `sql_emitter.py`:

```bash
git checkout -- src/spire/kg/sql_overlay.py src/spire/rendering/sql_emitter.py
rm -f src/spire/rendering/schema_corpus.py
```

Then Task 1 (module table lists) is the first thing the new window does.

## 6. What the new window should read first

1. This handover.
2. `docs/design/SQL_EMITTER_SCHEMA_CORPUS.md` — for the discarded approach and the validator's current shape. Skip §3–4 (the runtime gate); read §2 (corpus format) and §6 (verification plan).
3. `WORKING_STYLE.md` — the rulebook, updated by this window.
4. `src/spire/kg/sql_overlay.py` — the overlay to be replaced.
5. `docs/design/KG_Enhancements/KG_TO_PROPERTY_GRAPH_MIGRATION_PLAN.md` — a sibling design for KG changes. Check it for overlap before adding `kg_sql_column`.
6. `docs/design/ARCHITECTURE.md` — the current architecture, so the new design slots into it rather than beside it.

## 7. WORKING_STYLE.md update made by this window

Two additions, both in the working style document:

**§20.1 — Per-diagnostic context bundles are permitted.** The `context_bundles.yaml` static bundles serve session startup. A per-diagnostic `--files` bundle (e.g. `python build_context.py --files a.py b.py --name diag_x`) is the right shape for "here is one failure, show me the files that touch it". Both are sanctioned.

**§29 — Findings that reverse a prior approach are recorded as handovers, not deleted.** When a window diagnoses a problem, produces an approach, and then a later conversation reveals the approach is wrong-shaped (symptom-treating rather than cause-removing), the approach is **retained as "the discarded approach, for the record"**, not deleted. A new design supersedes it. This is how the repo learns from its own reversals — the record shows both what was tried and why it did not work, so a future session does not re-derive the wrong approach. The current handover is the worked example.

---

*End of handover.*