# SCHEMA DISCOVERY METHOD — how to inventory a new Fusion module against the pod

**Purpose:** the reusable procedure for discovering a Fusion module's tables, views, synonyms, columns, and joins — and verifying them against the live pod — before the KG carries them.

**Origin:** distilled from Phase 2's discovery of four modules (Supplier, Procurement, Payables, Receivables) on `fa-euth-dev63-saasfademo1`. See `docs/plan/HANDOVER_KG_SCHEMA_PHASE2.md` for the work that produced it.

**For:** any window introducing Spire to a new Fusion module.

---

## 0. When to use this document

Use it when Spire is about to support a module whose tables are not yet in `kg_sql_column`. The procedure:

1. Inventories every object the module's naming prefix exposes under the pod's owner.
2. Cross-checks the overlay's current hand-authored names against what the pod has.
3. Verifies every projected column and every join key against the real column list.
4. Produces the role map that `kg_sql_column` will hold.

Do not use this document to *build* the KG — §3.1–3.4 of the Phase 1 handover covers that. This document covers **discovery** — collecting the facts the KG will hold.

---

## 1. The three-layer strategy

Discovery proceeds in three layers, in order. Each layer answers a question the next layer assumes.

| Layer | Question | Query | Output |
|---|---|---|---|
| **1. Objects** | Which tables, views, synonyms exist under the module's prefix? | `ALL_TABLES` ∪ `ALL_VIEWS` ∪ `ALL_SYNONYMS` | `t_task1_<module>.txt` |
| **2. Columns** | What columns does each object carry, in what order, with what types? | `ALL_TAB_COLUMNS` per object | `t_task2_<module>.txt` |
| **3. Relationships** | How do objects join? Are the join-key columns real on both sides? | Manual, per join, against `t_task2_<module>.txt` | Role map per entity |

The principle: **never trust an exported schema document; always trust the pod.** The corpus export (`oracle_fusion_schema_updated_tables.xlsx`) that the original handover relied on was found to be `ALL_TABLES`-only, so it missed every view-exposed object — which turned out to be every object the overlay names. See §9 failure mode 2.

---

## 2. Prerequisites

Before running any cell:

- **`./runsql.sh` on the pod.** Sends a query to Oracle, returns tabular output to stdout. Verify with a trivial query: `./runsql.sh "SELECT 1 FROM DUAL"`.
- **The owner name.** Fusion's owner is typically `FUSION`, but some objects live under `PER`, `HR`, `FND`, `FUSION_DYNAMIC`, `FUSION_RO`. The queries below filter by owner; when an object is "missing" under `FUSION`, check the other owners (see §9 failure mode 3).
- **The module's naming prefix.** POZ and HZ for Supplier; PO for Procurement; AP for Payables; RA and AR for Receivables. New modules have their own prefix; confirm from Oracle's Fusion documentation or by looking at any known object's name.

---

## 3. Step 1 — Object inventory

**The query, generalized.** Substitute `<PREFIX>` (one or more prefixes; use `UNION ALL` for each additional prefix — see §12 for the four-module worked example).

```sql
SELECT OWNER, TABLE_NAME, 'TABLE' FROM ALL_TABLES
WHERE OWNER='FUSION' AND TABLE_NAME LIKE '<PREFIX>\_%' ESCAPE '\'
UNION ALL
SELECT OWNER, VIEW_NAME, 'VIEW' FROM ALL_VIEWS
WHERE OWNER='FUSION' AND VIEW_NAME LIKE '<PREFIX>\_%' ESCAPE '\'
UNION ALL
SELECT OWNER, SYNONYM_NAME, 'SYNONYM' FROM ALL_SYNONYMS
WHERE OWNER='FUSION' AND SYNONYM_NAME LIKE '<PREFIX>\_%' ESCAPE '\'
ORDER BY 2
```

**Three branches are mandatory.** `ALL_TABLES` alone misses every view-exposed object — which, on the Fusion pod we inventoried, was **every object** the overlay names. `ALL_VIEWS` alone misses actual tables (rare under FUSION, but non-zero: `AR_REV_REC_QT`, `AR_TRX_BALANCES_QT` in the Receivables scan). `ALL_SYNONYMS` alone misses the underlying object — synonyms point at views or tables, they are not the object.

**The escape clause matters.** `LIKE 'PO\_%' ESCAPE '\'` matches literally `PO_` at the start. Without `ESCAPE`, `_` matches any single character and `PO\_%` becomes `PO<any>%` — the query returns thousands of unrelated objects. Every module prefix ending in `_` needs this.

**Capture the output to a file, do not pipe through grep.** See §10.

```
./runsql.sh "<the query above>" > t_task1_<module>.txt 2>&1
```

**Read the file for shape, not content.**

```
wc -l t_task1_<module>.txt
grep -c "VIEW$" t_task1_<module>.txt
grep -c "TABLE$" t_task1_<module>.txt
grep -c "SYNONYM$" t_task1_<module>.txt
```

Sanity checks:

- **Total rows** should be plausible for the module — dozens (small, focused module) to a few hundred (large, cross-cutting). Zero means the prefix is wrong; thousands means the escape clause is missing.
- **All-VIEW is normal.** Fusion exposes the logical data model as views. `TABLE` rows are usually queue/internal tables. `SYNONYM` rows are short-name aliases — the canonical target is the `_ALL`/`_B`/`_TL` view, not the synonym.

**Acknowledge to the user what the file says.** "535 rows, all VIEW." "266 rows, 13 SYNONYM, no TABLE." Do not proceed to Step 2 until the shape is stated.

---

## 4. Step 2 — Cross-check against the overlay

**Goal:** for every entity in the overlay that scopes to this module, confirm its `fusion_table` is on the pod, and note objects the overlay misses.

**The read.** For each entity name in scope:

```
PYTHONPATH=src python -c "from spire.kg import sql_overlay as m; e = m._ENTITIES['<Entity>']; import pprint; pprint.pprint(vars(e))"
```

The `vars()` dump gives `fusion_table`, `select_columns`, `base_joins`, `pk_column`, `alias`. Note: `predicate_template` is **not** on `EntitySpec`; it lives on a separate `FilterSpec` structure. That structure is Task 4's concern, not discovery's.

**The check.** For every `fusion_table`, confirm it appears in `t_task1_<module>.txt` as a `VIEW` or `TABLE` (a `SYNONYM` target is acceptable but the `_ALL`/`_B` view it points to must also be present — check):

```
grep -E '^FUSION  <FUSION_TABLE>  ' t_task1_<module>.txt
```

**Outcomes:**

| Finding | Action |
|---|---|
| Object present as `VIEW`/`TABLE` | ✓ Proceed to Step 3 |
| Object absent entirely | Overlay is wrong at the table level. **Real bug.** Search `ALL_SYNONYMS WHERE SYNONYM_NAME='<NAME>'` — if a synonym exists, its target is the real table. If nothing, the object genuinely doesn't exist under this owner on this pod. |
| Object present as `SYNONYM` only | The overlay is using a short name — works, but the `_ALL` target should be the `fusion_table` (canonical). Note for Task 4. |

**Opportunistic gap finding.** While reading `t_task1_<module>.txt`, note objects that *should* be in the overlay but aren't — e.g., site-to-BU assignment tables for a Supplier site entity. This is gap-finding, not verification; the object is a candidate for Task 4's role map. Example: Phase 2 found `POZ_SITE_ASSIGNMENTS_ALL_M` and `HZ_PARTY_SITE_USES` present but not overlay-named for Supplier.

Do not act on gaps this step. Record them. Task 4 decides whether the overlay *needs* them.

---

## 5. Step 3 — Column inventory

**The query, one per table.**

```sql
SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE, NULLABLE, COLUMN_ID
FROM ALL_TAB_COLUMNS
WHERE OWNER='FUSION' AND TABLE_NAME='<TABLE>'
ORDER BY COLUMN_ID
```

**`ORDER BY COLUMN_ID` is mandatory.** It returns columns in the physical order the view defines them, not alphabetical. Physical order is:
- More readable (adjacent semantic columns stay adjacent — all `ATTRIBUTE1..N` together, all `DATE` columns together).
- More diagnostic (`VENDOR_ID` at `COLUMN_ID=74` tells you it comes after 70 DFF columns; alphabetical sorts it to the top and hides the DFF block).
- Faster to scan for extension/Draft/Archive conventions.

**`ALL_TAB_COLUMNS` covers views as well as tables.** No separate query needed for `ALL_VIEW_COLUMNS` — `ALL_TAB_COLUMNS` is the union view Oracle provides.

**Batch the per-table queries into one cell.** Per WORKING_STYLE §2.1, known-shape commands belong in one cell. The pattern from Phase 2:

```
for T in <TABLE1> <TABLE2> <TABLE3> ...; do
  echo "=== Table: $T ==="
  ./runsql.sh "SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE, NULLABLE, COLUMN_ID FROM ALL_TAB_COLUMNS WHERE OWNER='FUSION' AND TABLE_NAME='$T' ORDER BY COLUMN_ID"
  echo
done > t_task2_<module>.txt 2>&1
```

Wall clock: sub-second per table. A 20-table batch is under a minute.

**The `=== Table: NAME ===` marker is what makes the file greppable.** Every subsequent read uses `awk '/^=== Table: NAME ===/{f=1;next} /^=== Table: /{f=0} f'` to extract exactly one table's section from the combined file.

**Sanity check the file before using it:**

```
wc -l t_task2_<module>.txt
grep -c '^=== Table: ' t_task2_<module>.txt
grep -n '^=== Table: ' t_task2_<module>.txt
```

- `wc -l` — total lines. 5,000–15,000 for a medium module; suspiciously low (<100) means the `runsql.sh` call is failing or `$T` isn't expanding.
- `grep -c '^=== Table: '` — the count of tables scanned. Must equal the number in the `for` list.
- `grep -n '^=== Table: '` — the line number of each table's section. Bookmark these; every later extraction cites them.

**Do not paste the full file to a chat window unless the file is small** (under ~50KB). Above that, use targeted awk extractions per table as needed. The file lives on disk; the chat reads per-entity slices.

---

## 6. Step 4 — Verify every projected column

**The principle:** every column the overlay's `select_columns` names must be verified against `t_task2_<module>.txt`. **Do not trust the sweep's "first failing column" per entity.** The sweep tests one column at a time and stops at the first failure; it cannot tell you the other columns are valid.

**Why this matters — the Buyer case.** Phase 2 found the sweep reported `B.EMAIL_ADDRESS` as Buyer's first failure. Two earlier projected columns (`EMPLOYEE_NUMBER`, `DISPLAY_NAME`) were *also* absent — but the sweep never reported them, because it stopped at the first (in its execution order) failure. A per-entity "first failure" list understates the bug. On the pod, Buyer had **3 of 4** projected columns missing.

**The verification cell, per entity:**

```
for COL in <COL1> <COL2> <COL3> ...; do
  awk '/^=== Table: <TABLE> ===/{f=1;next} /^=== Table: /{f=0} f' t_task2_<module>.txt | grep -E "^${COL}[[:space:]]"
done
```

**Outcomes per column:**

- **Line printed** — column exists on the pod. Note its `DATA_TYPE / DATA_LENGTH / NULLABLE` for the role map.
- **Nothing printed for that column** — the column is absent. Real bug in the overlay. The role map needs a substitute or a join.

**`grep -E "^${COL}[[:space:]]"` guards against prefix collisions.** Without the `[[:space:]]` anchor, `VENDOR_ID` matches `VENDOR_ID_X` and `VENDOR_IDENTIFIER`. With it, only `VENDOR_ID` followed by whitespace (the column-name column's separator) matches.

**Every entity's every projected column is checked.** Not just the sweep's named one. Not just the "likely" ones. All of them.

**Population check — existence ≠ populated.** A column present in `t_task2_<module>.txt` can still be NULL on ~100% of rows — the R-7 stub-view shape, at the column level. Existence in `ALL_TAB_COLUMNS` is not evidence the column is a real carrier. Before binding a role to a physical column (especially an amount/measure column), count its population:

```
./runsql.sh "SELECT COUNT(*) TOTAL, COUNT(<COL>) NON_NULL FROM <TABLE>"
```

- `NON_NULL` ≈ `TOTAL` — the column is a real carrier. ✓
- `NON_NULL` is a small fraction of `TOTAL` — the column is a stub; do not bind the role to it. Find the populated carrier instead (an adjacent column, or a derived expression over populated columns).
- `NON_NULL` = 0 — the column is never set; existence is an illusion.

**F-060 is the canonical case.** `PO_LINES_ALL.AMOUNT` exists (it is in `t_task2_all.txt`) but is NULL on 315,857 of 315,970 rows (99.96%). `PurchaseOrderLine.amount` bound to it emitted SQL that returned NULL where REST returned the real line amount (33000/8250 on PO 2144). `TAX_EXCLUSIVE_PRICE` was populated on only 47,206 rows and — decisively — is a *unit* price (it equals `UNIT_PRICE`), not the extended amount. The correct carrier is derived `UNIT_PRICE * QUANTITY` (both populated on ~98%+ of rows).

The population check applies to the projected column itself **and** to every physical column inside a `kg_derived_projection` expression — a derived `SUM(X)` over a stub `X` returns NULL, so the derived role is stubbed too. F-060 fixed `PurchaseOrder.Ordered` (`SUM(L.AMOUNT)` → `SUM(L.UNIT_PRICE * L.QUANTITY)`) and `PurchaseOrderLine.Total` (`L.AMOUNT + tax` → `(L.UNIT_PRICE * L.QUANTITY) + tax`) for exactly this reason.

---

## 7. Step 5 — Verify every join key

**The principle:** the sweep tests `select_columns` only. It does not test `base_joins`. Every join in the overlay is an unverified assumption until proven against `t_task2_<module>.txt`.

**The cell, per join:**

```
awk '/^=== Table: <LEFT_TABLE> ===/{f=1;next} /^=== Table: /{f=0} f' t_task2_<module>.txt | grep -E '^<JOIN_COL>[[:space:]]'
awk '/^=== Table: <RIGHT_TABLE> ===/{f=1;next} /^=== Table: /{f=0} f' t_task2_<module>.txt | grep -E '^<JOIN_COL>[[:space:]]'
```

**Both sides must return a row.** A join where one side has the column and the other doesn't is a runtime error the sweep cannot catch. Phase 2 verified three joins this way: `HZ_PARTIES.PARTY_ID` (Supplier), `POZ_SUPPLIER_SITES_ALL_M.PARTY_SITE_ID` (Contact), `HZ_PARTY_SITES.LOCATION_ID` (Address). All present. But the check was necessary — none of those three would have been caught by the sweep.

**Check `NULLABLE` on the join key.** A nullable join key makes an inner join silently drop rows. Phase 2 found `POZ_SUPPLIER_SITES_ALL_M.PARTY_SITE_ID` nullable; the mitigation chosen was a build-time self-check that counts rows with NULL join key and requires zero (see Phase 2 §5 Q4). Do the same for every nullable join key — either add a build check, or plan for LEFT JOIN semantics with NULL propagation.

**Ad-hoc extensions.** Some join targets aren't in `t_task2_<module>.txt` — they were discovered during role-map drafting (e.g., `PER_PERSON_NAMES_F`, `PER_EMAIL_ADDRESSES` for Buyer). Run a direct column query for those join targets, and append the result to a companion file (`t_task2_<module>_extra.txt`):

```
./runsql.sh "SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH FROM ALL_TAB_COLUMNS WHERE OWNER='FUSION' AND TABLE_NAME='<NEW_TABLE>' ORDER BY COLUMN_ID"
```

Note the file name in the module's role map so the next session doesn't have to re-run the query.

---

## 8. Step 6 — Draft the role map

**The role map is one entity's contribution to `kg_sql_column`.** Per entity:

| role | table | column |
|---|---|---|
| semantic name | physical table | physical column |

**Semantic name** — the role the projection plays for the entity ("supplier_id", "site_code", "display_name"). The overlay's `select_columns` uses aliases like `('P', 'VENDOR_ID')` where `P` is a table alias and `VENDOR_ID` is the current physical column. Task 4's role names are human-readable substitutes for the physical names.

**Physical table + column** — the verified values from Step 4.

**The role map, in full for one entity:**

- **`kg_entity`** row: `(entity_name, fusion_table, pk_column)` — the primary table and PK.
- **`base_joins`** — the overlay's current join list, unchanged if verified by Step 5, corrected if not.
- **`kg_sql_column`** entries — one row per projected column, with `is_default_projection='Y'`, and every other column of every joined table with `is_default_projection='N'` (so any future column request can be answered).
- **Any bug fixed** — the role map section records the finding ("the overlay named `VENDOR_ID` on `POZ_SUPPLIER_CONTACTS`; the pod doesn't carry it; joined to `POZ_SUPPLIER_SITES_ALL_M` instead").

**Persist the role map in the module's handover or a running role-map file.** Phase 2 put them in `HANDOVER_KG_SCHEMA_PHASE2.md` §3. Any format works so long as the next session can find them without re-running the queries.

---

## 9. The failure modes (from Phase 2, apply to any new module)

Six traps discovered while doing this for the four modules of Phase 2. Assume all six recur in a new module.

### 9.1 Tables may actually be views

On the Fusion pod we scanned, `FUSION`-owned objects under `POZ_`, `HZ_`, `PO_`, `AP_`, `RA_`, `AR_` are **views**, not tables. Every overlay-named object was a view. `ALL_TAB_COLUMNS` works fine for views, so column inventory is unaffected — but **object inventory must include `ALL_VIEWS`**, not just `ALL_TABLES`.

**Consequence for a new module:** the same. Include both. If the module has any tables at all, they're usually queue/temp (`_QT`, `_GT`) or interface objects — not the logical data model.

### 9.2 Export documents may be `ALL_TABLES`-only

The Phase 1 corpus export (`oracle_fusion_schema_updated_tables.xlsx`) claimed `per_all_people_f` was "not found". The pod had it — as a view. The export was `ALL_TABLES`-only and dropped every view.

**Consequence for a new module:** if a "missing" object appears in Oracle documentation but not in an export, check the pod's `ALL_VIEWS` and `ALL_SYNONYMS` before concluding it's unavailable. The export is a convenience, not the truth.

### 9.3 Objects may be stubs

`FUSION.PER_ALL_PEOPLE_F` is a 105-column view. The vanilla Fusion `PER_ALL_PEOPLE_F` table has 250+ columns. The pod's view is a proxy: it keeps identity keys, drops the wide human-readable columns (name, email).

**Consequence for a new module:** if projected columns are missing from a FUSION view of an object that Oracle documents as wider, **look for sibling views** before concluding the data isn't available. Buyer's fix: `DISPLAY_NAME` on `PER_PERSON_NAMES_F`, `EMAIL_ADDRESS` on `PER_EMAIL_ADDRESSES`. Both views exist under FUSION.

### 9.4 Wide DFF views

`HZ_PARTY_SITES` has 723 columns. `PO_HEADERS_ALL` has ~292. Most of the width is the DFF extension block (`ATTRIBUTE1..N`, `ATTRIBUTE_DATE1..N`, `EXTN_ATTRIBUTE_CHAR1..N`). Roughly 80 columns are the semantic address columns; the rest are extension.

**Consequence for a new module:** a 700-column table is normal, not a pod artifact. Project the semantic columns; ignore the DFF block by design (the current overlay does, and so should a new module's role map). Do not try to guess "meaningful" DFF columns without a business reason.

**Diagnostic:** if a table is anomalously wide (10× the typical shape), check whether the extra columns are all DFF. If they're `ATTRIBUTE<n>` / `EXTN_ATTRIBUTE_*` / `ATTRIBUTE_DATE<n>`, they're DFF. If they're distinct semantic names (`SHIP_TO_SITE_ID`, `BILL_TO_SITE_ID`, `PRIMARY_SITE_FLAG`), the view is genuinely wide.

### 9.5 Nullable join keys

`POZ_SUPPLIER_SITES_ALL_M.PARTY_SITE_ID` is `NULLABLE='Y'`. An inner join through it silently drops rows where `PARTY_SITE_ID` is null.

**Consequence for a new module:** check `NULLABLE` on every join key. Two mitigations:

- **(A) Build self-check.** Count rows with NULL join key on the joined table; require zero. If non-zero on the pod, revisit join semantics. (Phase 2 chose this.)
- **(B) LEFT JOIN + NULL propagation.** Preserves rows, but ships NULLs to callers — the caller must be told. Rejected in Phase 2 for shipping surprises.

### 9.6 Aliases are overlay artifacts, not pod facts

The overlay's `('HP', 'PARTY_NAME')` renders as `HP.PARTY_NAME` in the emitted SQL, where `HP` is the alias for `HZ_PARTIES` in `base_joins`. The pod knows the column as `HZ_PARTIES.PARTY_NAME`. The alias is a rendering convenience.

**Consequence for a new module:** when collecting columns, the pod is authoritative — table name and column name, not alias. When reading `select_columns`, translate each `(alias, column)` pair to `(table, column)` using `base_joins` before verifying. Phase 2's step 4 wording assumes this translation happens first.

---

## 10. Capture discipline (WORKING_STYLE §15.1)

**Every run's full output is captured to a file before any inspection.**

The shape:

```
./runsql.sh "<query>" > t_task1_<module>.txt 2>&1
```

The temptation that fails: piping the run through a filter at capture time.

```
./runsql.sh "<query>" | grep 'pattern'    # ← NEVER
```

The reason: the filter bakes a question into the output. Every subsequent question ("do we have this column?", "how many views?") is a re-run — which means a new filter, which may miss what the next question needs. One unfiltered file answers every question by grep, at no extra cost.

**Inspect via grep, any number of times:**

```
grep -c 'pattern' t_task1_<module>.txt
awk '/^=== Table: NAME ===/{f=1;next} /^=== Table: /{f=0} f' t_task2_<module>.txt
```

**Name the file for its task, not its contents.** `t_task1_supplier.txt` = task 1's capture for the supplier module. `t_task2_procurement.txt` = task 2's capture. A file named `output.txt` or `dump.txt` loses its origin. Six months later, the task number is how you know the file is stale.

**Do not commit discovery files to git.** They're 100KB–500KB each, they're derivable from a fresh query, and they change with the pod. Keep them as working-tree scratch. The handover carries the regeneration command (see the Phase 2 handover §6).

---

## 11. Anti-patterns — what not to do

| Anti-pattern | Why it fails | Do this instead |
|---|---|---|
| `ALL_TABLES` alone | Misses view-exposed objects | Include `ALL_VIEWS` and `ALL_SYNONYMS` |
| `LIKE 'PO_%'` (no escape) | `_` matches any character; wrong scope | `LIKE 'PO\_%' ESCAPE '\'` |
| Pipe the run through grep | Lose full output; re-run per question | Redirect to file, grep from file |
| Trust the sweep's first-failure | Understates bug count (Buyer: 3 of 4, not 1) | Verify every projected column |
| Trust Oracle documentation | Docs describe the base table, not the FUSION view | Verify against the pod |
| Conclude "missing" without checking views/synonyms | Object exists under a different object type or owner | Run the ownership disambiguation query (§9.3) |
| Assume column name is derivable from role | Buyer: role "employee_number" is `PERSON_NUMBER`, not `EMPLOYEE_NUMBER` | Verify each column against the pod |
| Assume `OWNER='FUSION'` is universal | Some objects under `PER`, `HR`, `FND` | Disambiguate ownership on "missing" objects |
| Alphabetical column order | Hides DFF block boundaries, hides column position | `ORDER BY COLUMN_ID` |
| Commit discovery files | 100KB–500KB, derivable, pod-dependent | Regeneration command in the handover |

---

## 12. Worked example — the four modules of Phase 2

For reference; a new module does not repeat this. Module → prefix mapping, scope, and the single notable finding from Phase 2.

| Module | Prefix(es) | Objects | Notable finding |
|---|---|---|---|
| **Supplier** | `POZ_`, `HZ_` | 535 | All views; synonyms alias `_ALL` names to short forms. Site-to-BU assignment (`POZ_SITE_ASSIGNMENTS_ALL_M`) present but not overlay-named — gap for Supplier site scope. |
| **Procurement** | `PO_` | 186 | All views + 13 synonyms; no tables. `PO_HEADERS_ALL` has ~292 columns including a large DFF block. |
| **Payables** | `AP_` | 266 | All views + synonyms; no tables. |
| **Receivables** | `RA_`, `AR_` | 654 | 2 actual tables (`AR_REV_REC_QT`, `AR_TRX_BALANCES_QT` — both queue tables, not overlay scope); rest views. Overlay's six RA_/AR_ objects all present as views. |

Total: 1,641 objects scanned, **all 18 overlay-named objects verified as views**.

The combined query for a two-prefix module (Supplier shown; adapt for others):

```sql
SELECT OWNER, TABLE_NAME, 'TABLE' FROM ALL_TABLES
WHERE OWNER='FUSION' AND (TABLE_NAME LIKE 'POZ\_%' ESCAPE '\' OR TABLE_NAME LIKE 'HZ\_%' ESCAPE '\')
UNION ALL
SELECT OWNER, VIEW_NAME, 'VIEW' FROM ALL_VIEWS
WHERE OWNER='FUSION' AND (VIEW_NAME LIKE 'POZ\_%' ESCAPE '\' OR VIEW_NAME LIKE 'HZ\_%' ESCAPE '\')
UNION ALL
SELECT OWNER, SYNONYM_NAME, 'SYNONYM' FROM ALL_SYNONYMS
WHERE OWNER='FUSION' AND (SYNONYM_NAME LIKE 'POZ\_%' ESCAPE '\' OR SYNONYM_NAME LIKE 'HZ\_%' ESCAPE '\')
ORDER BY 2
```

For a new module: substitute the prefix list; one `OR` clause per additional prefix inside each of the three `WHERE` groups.

---

## 13. When to update this document

Update it when a discovery produces:

- **A new failure mode** not among §9's six. Add it there with the concrete example.
- **A new owner** beyond `FUSION` / `PER` / `HR` / `FND`. Update §2's prerequisites and §9.3's disambiguation query.
- **A new naming pattern** — non-prefix-based discovery (e.g., objects linked by a common suffix). Update §3's query.
- **A new layer** — if relationships need more than "verify both sides of the join" (e.g., FK graph discovery). Update §1's three-layer table.
- **A tooling improvement** — if a `runsql.sh` variant becomes available that formats output better, or a `--csv` flag for pandas. Update §10.

Do not update it for one-off findings — the module's handover carries those. This document carries the *method*, not the *work*.

---

## 14. Reusable cell templates

Copy-paste-ready, parameterized by `<module>` and `<TABLE>`.

### T1 — object inventory (one prefix)

```
./runsql.sh "SELECT OWNER, TABLE_NAME, 'TABLE' FROM ALL_TABLES WHERE OWNER='FUSION' AND TABLE_NAME LIKE '<PREFIX>\_%' ESCAPE '\' UNION ALL SELECT OWNER, VIEW_NAME, 'VIEW' FROM ALL_VIEWS WHERE OWNER='FUSION' AND VIEW_NAME LIKE '<PREFIX>\_%' ESCAPE '\' UNION ALL SELECT OWNER, SYNONYM_NAME, 'SYNONYM' FROM ALL_SYNONYMS WHERE OWNER='FUSION' AND SYNONYM_NAME LIKE '<PREFIX>\_%' ESCAPE '\' ORDER BY 2"
```

### T2 — object inventory shape

```
wc -l t_task1_<module>.txt
grep -c 'VIEW$' t_task1_<module>.txt
grep -c 'TABLE$' t_task1_<module>.txt
grep -c 'SYNONYM$' t_task1_<module>.txt
```

### T3 — column inventory (batch)

```
for T in <TABLE1> <TABLE2> <TABLE3>; do
  echo "=== Table: $T ==="
  ./runsql.sh "SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE, NULLABLE, COLUMN_ID FROM ALL_TAB_COLUMNS WHERE OWNER='FUSION' AND TABLE_NAME='$T' ORDER BY COLUMN_ID"
  echo
done > t_task2_<module>.txt 2>&1
```

### T4 — column inventory shape

```
wc -l t_task2_<module>.txt
grep -c '^=== Table: ' t_task2_<module>.txt
grep -n '^=== Table: ' t_task2_<module>.txt
```

### T5 — extract one table's section

```
awk '/^=== Table: <TABLE> ===/{f=1;next} /^=== Table: /{f=0} f' t_task2_<module>.txt
```

### T6 — verify one column on one table

```
awk '/^=== Table: <TABLE> ===/{f=1;next} /^=== Table: /{f=0} f' t_task2_<module>.txt | grep -E '^<COLUMN>[[:space:]]'
```

### T7 — verify multiple projected columns

```
for COL in <COL1> <COL2> <COL3>; do
  awk '/^=== Table: <TABLE> ===/{f=1;next} /^=== Table: /{f=0} f' t_task2_<module>.txt | grep -E "^${COL}[[:space:]]"
done
```

### T8 — dump entity spec

```
PYTHONPATH=src python -c "from spire.kg import sql_overlay as m; e = m._ENTITIES['<Entity>']; import pprint; pprint.pprint(vars(e))"
```

### T9 — ownership disambiguation for a "missing" object

```
./runsql.sh "SELECT OWNER, 'TABLE' K, TABLE_NAME FROM ALL_TABLES WHERE TABLE_NAME='<NAME>' UNION ALL SELECT OWNER, 'VIEW', VIEW_NAME FROM ALL_VIEWS WHERE VIEW_NAME='<NAME>' UNION ALL SELECT OWNER, 'SYNONYM', SYNONYM_NAME FROM ALL_SYNONYMS WHERE SYNONYM_NAME='<NAME>'"
```

### T10 — find where a column lives across tables

```
./runsql.sh "SELECT OWNER, TABLE_NAME, COLUMN_NAME FROM ALL_TAB_COLUMNS WHERE COLUMN_NAME='<COLUMN>' AND OWNER IN ('FUSION','PER','HR') ORDER BY OWNER, TABLE_NAME"
```

Use when a projected column is absent from its primary table — finds sibling tables that carry the same-name column.

---

*End of schema discovery method.*