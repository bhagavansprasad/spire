# HANDOVER — KG schema corpus, Phase 2 (data collection + role maps)

**For:** the next window, resuming from the Phase 1 design.
**From:** the window that completed Tasks 1–3 and drafted 6 of 22 Task-4 role maps on `KG-Schema-Corpus`.
**Branch:** `KG-Schema-Corpus`, working tree clean at window close.
**Read first:** the Phase 1 handover (`docs/plan/HANDOVER_KG_SCHEMA.md`) — §1 strategy and §3 design still authoritative. This document covers what happened in Tasks 1–4 and what remains.

---

## 0. How to use this file

This is the resume point for the next window. It is **not** a replacement for the Phase 1 handover — the strategy (§1) and design (§3) there are still the reference. This file captures:

- What the pod actually contains (six findings that revise Phase 1's assumptions).
- Task status at window close.
- Six role maps drafted, ready to write into `kg_sql_column`.
- The pattern the next window will follow for the remaining 16 entities.
- Open design questions the KG-build (§3.1) needs resolved before code.
- The regeneration command for `t_task2_all.txt`, if it has been removed.

Read top to bottom. Everything is evidence-backed by pasted output from this window.

---

## 1. What this window found — six reversals of Phase 1's assumptions, and two derived findings

Each is a claim the Phase 1 handover made that the pod contradicts, followed by the evidence and the working consequence. These belong in the closure handover per WORKING_STYLE §29.

### R-1 — FUSION exposes views, not tables

Phase 1 (§2) said the overlay names 18 physical tables. **On this pod, all 18 are views.** Every overlay-named object appears under `ALL_VIEWS WHERE OWNER='FUSION'`; zero appear under `ALL_TABLES`.

- Supplier module (7 objects): `POZ_SUPPLIERS`, `POZ_SUPPLIER_SITES_ALL_M`, `POZ_SUPPLIER_CONTACTS`, `POZ_BUS_CLASSIFICATIONS`, `HZ_PARTIES`, `HZ_PARTY_SITES`, `HZ_LOCATIONS` — all VIEW.
- Procurement (4): `PO_HEADERS_ALL`, `PO_LINES_ALL`, `PO_LINE_LOCATIONS_ALL`, `PO_DISTRIBUTIONS_ALL` — all VIEW.
- Payables (1): `AP_INVOICES_ALL` — VIEW.
- Receivables (6): `RA_CUSTOMER_TRX_ALL`, `RA_CUSTOMER_TRX_LINES_ALL`, `RA_CUST_TRX_LINE_GL_DIST_ALL`, `AR_PAYMENT_SCHEDULES_ALL`, `AR_CASH_RECEIPTS_ALL`, `AR_RECEIVABLE_APPLICATIONS_ALL` — all VIEW.

**Consequence:** overlay table names ship forward unchanged. They are not wrong. Task 1's verification is a pass, not a fix. `ALL_TAB_COLUMNS WHERE OWNER='FUSION'` returns columns for views, so Task 2 is unaffected.

### R-2 — `per_all_people_f` IS accessible via FUSION (Task 3 closed)

Phase 1 (§2) said `per_all_people_f` is missing from the FUSION corpus, and Task 3 (§4) framed the gap as "find the actual owner." **It was found under FUSION as a view; the corpus export missed it because it was almost certainly `ALL_TABLES`-only.**

- `FUSION.PER_ALL_PEOPLE_F` — a 105-column view.
- `FUSION_DYNAMIC.PER_ALL_PEOPLE_F` — synonym to the FUSION view.
- `FUSION_RO.PER_ALL_PEOPLE_F` — synonym to the FUSION view.

**Consequence:** Task 3 is closed. No `OWNER='PER'` or `OWNER='HR'` detour needed. Buyer is not blocked on availability. **But** — as R-4 shows — the 105-column view is not the same object the overlay's Buyer spec expected.

### R-3 — The 10-entity sweep is not per-entity reliable

Phase 1 (§2) reported the sweep as "first failure per entity." The pattern held for 5 of 6 entities verified this window (Supplier, Contact, Site, Address, Classification — all correct), and **failed for Buyer**.

For Buyer, the sweep reported `B.EMAIL_ADDRESS` as the first failing column. If that were the true first failure, `B.EMPLOYEE_NUMBER` and `B.DISPLAY_NAME` (positions 2 and 3 in projection order) must have passed. They did not — neither exists on `FUSION.PER_ALL_PEOPLE_F`. If those had been tested first, the sweep should have reported `B.EMPLOYEE_NUMBER`.

Three candidate explanations (not resolved this window):

1. The sweep ran against a different Buyer spec (branch divergence — Phase 1 §5 records uncommitted `sql_overlay.py` changes on `SQL-Emitter-Multifield-Fix`).
2. The sweep is stale (pre-dates a `sql_overlay.py` change that altered Buyer).
3. Oracle's "first invalid identifier" is not the leftmost in projection order.

**Consequence:** the sweep's headline ("10 of 22 entities have at least one invalid column") survives. Its per-entity named column is treated as a **hint**, not as authoritative. **Every projected column of the remaining 8 sweep-flagged entities is verified against `t_task2_all.txt` regardless of what the sweep named.** That's the pattern established this window.

**Confirmed ×3 (2026-11-18).** See R-8 for the consolidated evidence (Buyer, PurchaseOrder, PurchaseOrderLine) and the promotion to a drafting rule. Contact (§3.2) had one sweep-named failure and one actual bug — not understated, because the table was shallow enough that the first failure was the only one. The pattern breaks whenever the table is wider.

### R-4 — Buyer's structural model was wrong, not just column-level

Overlay's Buyer spec projected four columns:

```
[('B', 'PERSON_ID'), ('B', 'EMPLOYEE_NUMBER'),
 ('B', 'DISPLAY_NAME'), ('B', 'EMAIL_ADDRESS')]
```

On this pod:

- `PERSON_ID` — present (col 1 of `PER_ALL_PEOPLE_F`).
- `EMPLOYEE_NUMBER` — absent. Substitute: `PERSON_NUMBER` on `PER_ALL_PEOPLE_F`.
- `DISPLAY_NAME` — absent. Lives on `PER_PERSON_NAMES_F.DISPLAY_NAME` (verified).
- `EMAIL_ADDRESS` — absent. Lives on `PER_EMAIL_ADDRESSES.EMAIL_ADDRESS` (verified), joined via `PRIMARY_EMAIL_ID` on `PER_ALL_PEOPLE_F`.

**Consequence:** the Buyer fix is not "change one column name." It's "change one column name and add two joins." This is the shape of bug the KG approach is designed to catch: the overlay author assumed a wide `PER_ALL_PEOPLE_F`; the pod has a narrower view that splits across three tables. `kg_sql_column` carries the real column per role, joined from the real tables.

### R-5 — `HZ_LOCATIONS.COUNTRY` is a code (`VARCHAR2(8)`), not a display name

The Address entity projects `L.COUNTRY`. The pod confirms `VARCHAR2(8)` — an ISO-style code, not "United States" etc.

**Consequence:** not a bug in the overlay — the projection returns a code, as it likely always did. But if any consumer displays `COUNTRY` as-is, it shows `US`/`GB`/`IN`. Resolving names requires joining `HZ_GEOGRAPHIES` or `FND_TERRITORIES`. A **display concern**, not a KG-build concern. Flagged so the next window does not confuse it with a column-existence bug.

### R-6 — `supplier_contacts.py` uses REST, not the SQL overlay

`src/spire/mcp_server/tools/supplier_contacts.py` was read for how it uses the Contact entity. Grep found no `SELECT`, no `select_columns`, no `_ENTITIES` reference, no `HZ_PARTIES` — imports are `httpx`, `FusionClient`, `ToolResult`. The tool issues REST calls and reshapes responses.

**Consequence:** some entities in `_ENTITIES` are **swept-only** — the sweep tests them, no production MCP tool emits them. The Contact bug fixed this window matters for the sweep and any future SQL-emitter path, but does not change what `supplier_contacts.py` returns today. **Which of the 22 entities the SQL emitter actually produces is a separate question** — deferred, not blocking Task 4's role maps. Recorded so the next window does not assume "overlay bug fixed ⇒ production behavior changed."

### R-7 — `PO_HEADERS_ALL` is a stub view with no ordered-total carrier

Discovered while drafting PurchaseOrder's role map. `PO_HEADERS_ALL` does not carry `AUTHORIZATION_STATUS` (the sweep-named failure), `AMOUNT` (Phase 1 §2's second suspect), or `DISPLAY_NAME` — three of six projected columns absent.

Sibling-view search (SCHEMA_DISCOVERY_METHOD §9.3) across the eleven `PO_HEADERS%` objects — `PO_HEADERS_ALL`, `_ALL_SEC`, `_ARCHIVE_ALL`, `_ARCHIVE_ALL_SEC`, `_DRAFT_ALL`, `_DRAFT_ALL_SEC`, `_GT`, `_INTERFACE`, `_INTERFACE_SEC`, plus two synonyms — surfaced only `AMOUNT_LIMIT`, `AMOUNT_RELEASED`, `BLANKET_TOTAL_AMOUNT`, `MIN_RELEASE_AMOUNT`. Ceilings, released amounts, floors — never the ordered total. No operational or sibling view on this pod carries it.

**Consequence:** `PO_HEADERS_ALL` is a stub view, same shape as `PER_ALL_PEOPLE_F` (R-2, R-4). This is a persistent pod property, not a one-off. Any role whose semantics require "the header-level total" must be derived from children. `PO_LINES_ALL.AMOUNT` is the leaf, and `(SELECT SUM(L.AMOUNT) FROM PO_LINES_ALL L WHERE L.PO_HEADER_ID = P.PO_HEADER_ID)` is the only correct substitute on this pod. Drove the `kg_derived_projection` mechanism (Q6). Expect the same pattern on `AP_INVOICES_ALL` and `RA_CUSTOMER_TRX_ALL` when those entities are drafted.

### R-8 — the sweep's per-entity first-failure list is a hint, never a count

Confirmed on three entities checked to full depth. Each sweep entry names one column; each entity had more.

| Entity | Sweep named | Actual absent |
|---|---|---|
| Buyer | `B.EMAIL_ADDRESS` | 3 of 4 |
| PurchaseOrder | `P.AUTHORIZATION_STATUS` | 3 of 6 |
| PurchaseOrderLine | `L.STATUS_LOOKUP_CODE` | 5 of 10 |

Contact (Phase 2 §3.2) had one sweep-named failure and one actual bug — not understated, but only because the table was shallow. The pattern breaks whenever the table is wider than the sweep's first-failure trap catches.

**Consequence:** promoted to a drafting rule. No entity's role map is drafted from the sweep. Every projected column is verified against `t_task2_all.txt` per SCHEMA_DISCOVERY_METHOD §6, and every join key per §7. The rule lives in the `KG_ROLE_MAPS.md` header so a future window drafting an entity cannot miss it. The sweep's §4 output remains useful as an "is this entity flagged at all" pre-filter; it is not useful as a column-level count.

---

## 2. Task status at window close

| Task | Status | Notes |
|---|---|---|
| Task 1 — module table lists | complete | All 4 modules scanned (1641 objects); all 18 overlay names verified present; all are VIEWs (R-1). |
| Task 2 — per-table column lists | complete | `t_task2_all.txt` on disk, 4101 lines, 19 tables. Regeneration in §6. |
| Task 3 — HR-side gap | closed | `per_all_people_f` found under FUSION as a 105-col view (R-2). |
| Task 4 — role maps | 6/22 | Supplier, Contact, Site, Address, Classification (5 entities); Buyer (first Procurement). 16 remaining. |

---

## 3. Role maps drafted this window

Each table is one entity's contribution to `kg_sql_column` with `is_default_projection='Y'`, and its `kg_entity` row for `fusion_table` / `pk_column`.

The next window does not re-derive these; it transcribes them into `scripts/sql/kg_schema.sql` (as seed data) or into `scripts/rebuild_kg.py` (as curated role config) — the exact form is §3.1's design decision, discussed in §5.

### 3.1 Supplier (`POZ_SUPPLIERS`)

`kg_entity`: `(Supplier, POZ_SUPPLIERS, VENDOR_ID)`

`base_joins`: `['JOIN HZ_PARTIES HP ON HP.PARTY_ID = P.PARTY_ID']`

| role | table | column |
|---|---|---|
| `supplier_id` | `POZ_SUPPLIERS` | `VENDOR_ID` |
| `supplier_number` | `POZ_SUPPLIERS` | `SEGMENT1` |
| `supplier_name` | `HZ_PARTIES` | `PARTY_NAME` |
| `enabled` | `POZ_SUPPLIERS` | `ENABLED_FLAG` |

All four verified on the pod. Not in the sweep's failure list.

### 3.2 Contact (`POZ_SUPPLIER_CONTACTS`)

`kg_entity`: `(Contact, POZ_SUPPLIER_CONTACTS, VENDOR_CONTACT_ID)`

`base_joins`: `['JOIN POZ_SUPPLIER_SITES_ALL_M PS ON PS.PARTY_SITE_ID = CT.ORG_PARTY_SITE_ID']`

| role | table | column |
|---|---|---|
| `contact_id` | `POZ_SUPPLIER_CONTACTS` | `VENDOR_CONTACT_ID` |
| `supplier_id` | `POZ_SUPPLIER_SITES_ALL_M` | `VENDOR_ID` |
| `party_site_id` | `POZ_SUPPLIER_CONTACTS` | `PARTY_SITE_ID` |

**Fixed bug.** The overlay's `('CT','VENDOR_ID')` names a column absent from `POZ_SUPPLIER_CONTACTS` (verified: not among its 70 columns). Corrected by joining to `POZ_SUPPLIER_SITES_ALL_M` via `ORG_PARTY_SITE_ID`. Both join-key columns (`PS.PARTY_SITE_ID`, `PS.VENDOR_ID`) verified on the joined table. `PS.PARTY_SITE_ID` is nullable — see §5 Q4.

### 3.3 Site (`POZ_SUPPLIER_SITES_ALL_M`)

`kg_entity`: `(Site, POZ_SUPPLIER_SITES_ALL_M, VENDOR_SITE_ID)`

`base_joins`: *(none)*

| role | table | column |
|---|---|---|
| `site_id` | `POZ_SUPPLIER_SITES_ALL_M` | `VENDOR_SITE_ID` |
| `site_code` | `POZ_SUPPLIER_SITES_ALL_M` | `VENDOR_SITE_CODE` |
| `procurement_bu_id` | `POZ_SUPPLIER_SITES_ALL_M` | `PRC_BU_ID` |

All three verified. No joins.

### 3.4 Address (`HZ_PARTY_SITES`)

`kg_entity`: `(Address, HZ_PARTY_SITES, PARTY_SITE_ID)`

`base_joins`: `['JOIN HZ_LOCATIONS L ON L.LOCATION_ID = PS.LOCATION_ID']`

| role | table | column |
|---|---|---|
| `party_site_id` | `HZ_PARTY_SITES` | `PARTY_SITE_ID` |
| `party_id` | `HZ_PARTY_SITES` | `PARTY_ID` |
| `address1` | `HZ_LOCATIONS` | `ADDRESS1` |
| `city` | `HZ_LOCATIONS` | `CITY` |
| `state` | `HZ_LOCATIONS` | `STATE` |
| `country` | `HZ_LOCATIONS` | `COUNTRY` |

All six verified. Join key `HZ_PARTY_SITES.LOCATION_ID` present (col 3), matches `HZ_LOCATIONS.LOCATION_ID` (col 1). **Caveat:** `COUNTRY` is `VARCHAR2(8)` code, not name (R-5). `ADDRESS1`/`CITY`/`STATE` nullable.

### 3.5 Classification (`POZ_BUS_CLASSIFICATIONS`)

`kg_entity`: `(Classification, POZ_BUS_CLASSIFICATIONS, CLASSIFICATION_ID)`

`base_joins`: *(none)*

| role | table | column |
|---|---|---|
| `classification_id` | `POZ_BUS_CLASSIFICATIONS` | `CLASSIFICATION_ID` |
| `supplier_id` | `POZ_BUS_CLASSIFICATIONS` | `VENDOR_ID` |
| `lookup_code` | `POZ_BUS_CLASSIFICATIONS` | `LOOKUP_CODE` |
| `status` | `POZ_BUS_CLASSIFICATIONS` | `STATUS` |

All four verified. `VENDOR_ID` at col 74 (70 DFF columns before it). No joins.

### 3.6 Buyer (`PER_ALL_PEOPLE_F`)

`kg_entity`: `(Buyer, PER_ALL_PEOPLE_F, PERSON_ID)`

`base_joins` (rendered below without SQL escaping so this handover reads as prose):

```
JOIN PER_PERSON_NAMES_F PN ON PN.PERSON_ID = B.PERSON_ID AND PN.NAME_TYPE = 'GLOBAL'
JOIN PER_EMAIL_ADDRESSES EA ON EA.EMAIL_ADDRESS_ID = B.PRIMARY_EMAIL_ID
```

| role | table | column |
|---|---|---|
| `buyer_id` | `PER_ALL_PEOPLE_F` | `PERSON_ID` |
| `employee_number` | `PER_ALL_PEOPLE_F` | `PERSON_NUMBER` |
| `display_name` | `PER_PERSON_NAMES_F` | `DISPLAY_NAME` |
| `email_address` | `PER_EMAIL_ADDRESSES` | `EMAIL_ADDRESS` |

**Fixed bug (structural).** Three of four projected columns absent from `PER_ALL_PEOPLE_F` (R-4). `EMPLOYEE_NUMBER`→`PERSON_NUMBER` (same table). `DISPLAY_NAME` and `EMAIL_ADDRESS` need joins to sibling tables. Both join targets verified: `PER_PERSON_NAMES_F` has `PERSON_ID`, `NAME_TYPE`, `DISPLAY_NAME`; `PER_EMAIL_ADDRESSES` has `EMAIL_ADDRESS_ID`, `EMAIL_ADDRESS`, `PERSON_ID`.

---

## 4. The pattern for the remaining 16 role maps

Every entity follows the same four-step cell sequence. It is established and does not need re-derivation; copy the cells, swap the entity name.

**Step 1 — dump the entity spec.**

```
PYTHONPATH=src python -c "from spire.kg import sql_overlay as m; e = m._ENTITIES['<Entity>']; import pprint; pprint.pprint(vars(e))"
```

Read: `select_columns` (what physical names the overlay currently projects), `base_joins` (what joins exist today), `fusion_table`, `pk_column`.

**Step 2 — verify every projected column against `t_task2_all.txt`.**

Do not trust the sweep's named first failure. Grep all projected columns.

```
for COL in <col1> <col2> <col3>; do
  awk '/^=== Table: <TABLE> ===/{f=1;next} /^=== Table: /{f=0} f' t_task2_all.txt | grep -E "^${COL}[[:space:]]"
done
```

Columns present: keep the physical name. Columns absent: real bug — the entity's role map must locate the real column (substitute on the same table, or a join target on a sibling table).

**Step 3 — verify every join key on both sides.**

The sweep tests `select_columns` only; it does not test `base_joins`. Every join in the spec needs its ON clause verified column-by-column:

- Left side: does the column exist on the aliased table?
- Right side: does the column exist on the joined table?

```
awk '/^=== Table: <LEFT_TABLE> ===/{f=1;next} /^=== Table: /{f=0} f' t_task2_all.txt | grep -E '^<JOIN_COL>[[:space:]]'
awk '/^=== Table: <RIGHT_TABLE> ===/{f=1;next} /^=== Table: /{f=0} f' t_task2_all.txt | grep -E '^<JOIN_COL>[[:space:]]'
```

**Step 4 — draft the role map.**

Roles are the semantic names the current `select_columns` uses, plus a physical column that exists. If the original column exists, keep it. If not, the role map chooses a substitute on the same table (e.g. `EMPLOYEE_NUMBER`→`PERSON_NUMBER`) or a join target (e.g. `DISPLAY_NAME`→`PER_PERSON_NAMES_F.DISPLAY_NAME`).

**Two entities to handle with extra care, when reached:**

- **POSchedule / PODistribution** — likely use `PO_LINE_LOCATIONS_ALL` and `PO_DISTRIBUTIONS_ALL`, both large; the same "verify all projected columns" applies, and joins to `PO_LINES_ALL` / `PO_HEADERS_ALL` are likely.
- **ReceivablesInvoice and the DFF entities** — `RA_CUSTOMER_TRX_ALL` has 263 cols with a DFF extension block that may contain the "missing" attributes under different names. The overlay's `RA_CUSTOMER_TRX_ALL.ATTRIBUTE1` failure suggests a DFF column that either exists under a different name or is not carried in the view. Verify both before drafting.

---

## 5. Design decisions the §3.1 build needs resolved

These are decisions the KG schema (§3.1) needs answered before code. Q2, Q3, Q4 and Q6 were resolved in the window that drafted PurchaseOrder and PurchaseOrderLine (2026-11-18). Q1 and Q5 remain open with a named deferral.

**Q1 — `pk_column` placement.** Phase 1 §3.1 adds only `fusion_table` to `kg_entity`. The overlay also carries `pk_column` per entity — same class of fact (a physical name). Recommendation: add `kg_entity.pk_column` alongside `fusion_table`, populated by the same build step. Alternative: leave `pk_column` in the overlay, accepting that one physical-name authoring path stays open.

**Deferred (2026-11-18)** to the §3.1 build. Not resolved in this window because the answer interacts with Q6's `kg_derived_projection` shape — a derived role has no physical column, so whether a per-entity PK belongs on `kg_entity`, `kg_sql_column`, or split between them depends on the full schema. Decide at §3.1 with all rows visible.

**Q2 — `predicate_template` surface.** `EntitySpec` (which `vars()` dumps) has no `predicate_template` field. The WHERE-clause columns that Phase 1 §3.3 says to resolve via `kg_sql_column` live on a separate `FilterSpec` structure elsewhere in `sql_overlay.py`. Next window's first action on §3.3 is to locate `FilterSpec` and read it.

**Resolved (2026-11-18).** `FilterSpec` is a dataclass at `sql_overlay.py:23` with `predicate_template: str` at line 26. Filters are keyed `(tool_name, filter_name)` in `_FILTERS` at line 444, **not** by entity — one entity spans multiple tools (Supplier has three: `search_suppliers`, `search_suppliers_by_site_bu`, `search_suppliers_by_classification`). §3.3's predicate-column resolution is three steps, not one: (1) `tool_name → entity_name` via `tool_to_entity`; (2) `entity.base_joins → alias→table map` (`JOIN HZ_PARTIES HP ON ...` → `HP = HZ_PARTIES`); (3) `kg_sql_column` lookup on `(entity_name, table, column)`. Same mechanism as `select_columns`, plus the alias translation. No schema change needed for §3.3.

**Q3 — `kg_sql_column` keying.** PK is `(entity_name, physical_table, column_name)` per Phase 1 §3.1. Same physical table under multiple entities yields multiple rows — e.g. `HZ_PARTIES` under Supplier, Address, Contact will have three rows per column. Correct: the table is joined differently per entity. But confirm the intent, because it means `kg_sql_column` row count is larger than "sum of all tables' columns."

**Resolved (2026-11-18).** PK `(entity_name, physical_table, column_name)` stands as written in Phase 1 §3.1. Same physical table under multiple entities yields multiple rows, correctly — the table is joined differently per entity, and `is_default_projection` is per-entity. Note for §3.2 only, not §3.1: if every column of every joined table is carried with `is_default_projection='N'` for non-projections (SCHEMA_DISCOVERY_METHOD §8), the row count is "sum over entities of all joined-table columns," larger than "sum of all tables' columns." Confirm the intent at §3.2 build.

**Q4 — nullable join key.** `POZ_SUPPLIER_SITES_ALL_M.PARTY_SITE_ID` (Contact's join right-side) is `NULLABLE='Y'`. An inner join drops site rows whose `PARTY_SITE_ID` is NULL, and their contacts vanish silently. Option accepted this window: **add a build self-check that counts NULL `PARTY_SITE_ID` rows on `POZ_SUPPLIER_SITES_ALL_M` and requires zero.** If non-zero on the pod, revisit join semantics. Alternative (LEFT JOIN, NULL supplier_id for such rows) rejected as shipping surprises the caller.

**Resolved (2026-11-18).** Build self-check accepted as written, and **extended to every nullable join key in any `base_joins`**, not only Contact's. Each nullable key gets a §3.4 build check counting NULLs on the joining-side table; non-zero fails the build. LEFT JOIN + NULL propagation remains rejected. At time of writing, two nullable keys are known: `POZ_SUPPLIER_SITES_ALL_M.PARTY_SITE_ID` (Contact) and `PO_HEADERS_ALL.VENDOR_ID` (PurchaseOrder). The mechanism is per-key, not per-entity — later entities extend the list.

**Q5 — entity-vs-tool surface mismatch.** R-6 shows `supplier_contacts.py` uses REST, not the overlay. Which of the 22 entities the SQL emitter actually produces is unresolved. Not blocking Task 4 (KG carries columns; emitter reads them if/when it emits), but is required before §3.3's emitter change is testable. Next window's first action on §3.3: `grep -l sql_overlay src/spire/mcp_server/tools/*.py` to identify overlay-consuming tools.

**Deferred (2026-11-18)** to §3.3. First action unchanged; not run in this window. Task 4 work does not depend on the answer.

**Q6 — roles with no direct column carrier.** Discovered during PurchaseOrder drafting. `PO_HEADERS_ALL.AMOUNT` does not exist on the pod, and no sibling view across the eleven `PO_HEADERS%` objects carries the ordered total (R-7). Same class will recur on PurchaseOrderLine (`TOTAL_TAX`, `TOTAL`) and on the receivables DFF entities per Phase 2 §4.

**Resolved (2026-11-18).** Derived projections live in a new sibling table `kg_derived_projection`, keyed `(entity_name, role_name)`, columns `expression VARCHAR2(4000)` and `is_default_projection CHAR(1)`. The expression carries a correlated scalar subquery in the form `(SELECT ... FROM <child> <alias> WHERE <alias>.<fk> = <base_alias>.<pk>)`. Every physical column inside the expression is validated against `kg_sql_column` at build — the expression is not a new unvalidated hand-authored name, it is an expression over validated ones. §3.4's check walks both tables. §3.3's emitter gains one branch: role → `kg_sql_column` lookup, else role → `kg_derived_projection` expression, else error. Q1 and Q3 are undisturbed by this addition.

---

## 6. Artifact on disk

**`t_task2_all.txt`** — the Task 2 column-list capture. 4101 lines, 19 tables. Currently untracked scratch in the working tree at the repo root.

If it has been removed, regenerate with (single cell; known-shape batch per WORKING_STYLE §2.1):

```
for T in POZ_SUPPLIERS POZ_SUPPLIER_SITES_ALL_M POZ_SUPPLIER_CONTACTS POZ_BUS_CLASSIFICATIONS \
         HZ_PARTIES HZ_PARTY_SITES HZ_LOCATIONS \
         PO_HEADERS_ALL PO_LINES_ALL PO_LINE_LOCATIONS_ALL PO_DISTRIBUTIONS_ALL PER_ALL_PEOPLE_F \
         AP_INVOICES_ALL \
         RA_CUSTOMER_TRX_ALL RA_CUSTOMER_TRX_LINES_ALL RA_CUST_TRX_LINE_GL_DIST_ALL \
         AR_PAYMENT_SCHEDULES_ALL AR_CASH_RECEIPTS_ALL AR_RECEIVABLE_APPLICATIONS_ALL; do
  echo "=== Table: $T ==="
  ./runsql.sh "SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE, NULLABLE, COLUMN_ID FROM ALL_TAB_COLUMNS WHERE OWNER='FUSION' AND TABLE_NAME='$T' ORDER BY COLUMN_ID"
  echo
done > t_task2_all.txt 2>&1
```

Wall clock: sub-minute. Do not commit this file to git; it is derivable and 400KB. Keep it as working-tree scratch.

**Not covered by `t_task2_all.txt` and needed when reached:** `PER_PERSON_NAMES_F` and `PER_EMAIL_ADDRESSES` (verified by ad-hoc queries this window; full column lists not in the file). If the next window drafts additional HR-side entities, extend the loop rather than regenerating.

---

## 7. Reading order for the next window

1. This handover.
2. `docs/plan/HANDOVER_KG_SCHEMA.md` — Phase 1 strategy (§1) and design (§3), still authoritative. Skip §4's task list (this document supersedes its Task 1–3 status) and §5's "state of tree" (branch changed; tree is clean on `KG-Schema-Corpus`).
3. `WORKING_STYLE.md` — §15.3 patch/verify contract for the handover edits that produced this document.
4. `src/spire/kg/sql_overlay.py` — the current overlay; grep `_ENTITIES` for the 16 remaining entity names.
5. `scripts/sql/kg_schema.sql` — the current KG schema.
6. `scripts/rebuild_kg.py` — the KG-build entry point; how existing entity data is written.

---

## 8. Recommended next-window sequence

The order below minimizes back-tracking: complete each module before touching the next, and resolve open design questions (§5) before writing `kg_schema.sql`.

**Before any Task 4 work:**

- Resolve Q1–Q5.
- Regenerate `t_task2_all.txt` if absent.
- Read `FilterSpec` (Q2's target structure).

**Procurement module (4 entities remaining):**

1. `PurchaseOrder` — sweep named `P.AUTHORIZATION_STATUS`. Verify all projected columns.
2. `PurchaseOrderLine` — sweep named `L.STATUS_LOOKUP_CODE`.
3. `POSchedule` — sweep named `S.BILLED_QUANTITY`.
4. `PODistribution` — sweep named `D.STATUS`.

**Payables module (1 entity):**

5. `Invoice` — `AP_INVOICES_ALL`; sweep has no named failure for this entity. Verify all.

**Receivables module (11 entities remaining):**

6. `ReceivablesInvoice` — sweep named `P.ENTERED_AMOUNT`.
7. `ReceivablesInvoiceLine`, `ReceivablesTaxLine` (sweep: `T.TAXABLE_AMOUNT`), `ReceivablesTransactionDFF`, `CreditMemo` (sweep: `C.ENTERED_AMOUNT`), `CustomerAccount`, `CustomerTransaction`, `AccountCreditMemo`, `AccountReceipt` (sweep: `R.AMOUNT_APPLIED`), `AccountReceiptApplication`, `StandardReceipt`.

**After Task 4 complete:**

- §3.1 schema build — `kg_entity.fusion_table`, `kg_entity.pk_column`, `kg_sql_column`.
- §3.2 rebuild step — populate `kg_sql_column` from pod via `ALL_TAB_COLUMNS`.
- §3.4 self-check — repurpose `validate_overlay_columns.py` to a KG-build check.
- §3.3 emitter change — `sql_overlay.py`'s `select_columns` becomes a `kg_sql_column` lookup at import.
- §3.5 deletion — `schema_corpus.py`, `_corpus_or_comment`, `has_column` import, `("P", "AMOUNT")` comment.

---

*End of handover, Phase 2.*