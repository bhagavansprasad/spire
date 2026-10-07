# SPIRE — SQL Overlay POC, window-30 handoff

**Date:** 2026-10-07
**Branch:** `poc/sql-overlay`, tip `efd096d`, clean tree, in sync with `origin/poc/sql-overlay`
**Parent:** `hardening-master-v2` at `db40182`
**Phase:** 1 done (schema gathered); 2 started (mapping exists in conversation, not in doc, not committed)

## What this POC is

Deterministic SQL projection of the Plan. For every Plan step, print the
equivalent Fusion-DB SQL. No LLM in SQL emission — the Plan is a KG lookup,
the SQL is the Plan. **Supplier module only.** Five entities: Supplier,
Address, Site, Classification, Contact. Print only, no execution. Scope
document: `docs/design/SQL_OVERLAY_POC.md`.

## What this window did

1. Gathered the Fusion schema for the Supplier module — twelve tables,
   consolidated into `~/poc_schema.csv` (3,294 rows + header).
2. Produced the entity → Fusion mapping — five entities against base
   tables and join paths.
3. Produced the gap list — three gaps, two closed, one open.

Nothing committed. No repo file edited.

## On disk but not in the repo

| path | content | disposition |
|---|---|---|
| `~/poc_schema.csv` | 3,294 rows, 12 tables, header on line 1 | move into repo |
| `~/all_columns.csv` | raw Fusion column dump (source) | keep as source |
| `~/poc_tables.txt` | first-pass filtered rows | discard |
| `/tmp/poc/*.cols` | per-table column lists | discard (transient) |

## The mapping (compressed)

| POC entity | Fusion table | key columns |
|---|---|---|
| Supplier | `poz_suppliers` | `VENDOR_ID`, `PARTY_ID`, `SEGMENT1`, `ENABLED_FLAG`, `VENDOR_TYPE_LOOKUP_CODE` |
| Supplier name | `hz_parties` | `PARTY_ID`, `PARTY_NAME`, `PARTY_NUMBER` |
| Address | `hz_party_sites` → `hz_locations` | `PARTY_SITE_ID`, `PARTY_ID`, `LOCATION_ID`; `ADDRESS1-4`, `CITY`, `STATE`, `COUNTRY` |
| Site | `poz_supplier_sites_all_m` | `VENDOR_SITE_ID`, `VENDOR_ID`, `VENDOR_SITE_CODE`, `INACTIVE_DATE` |
| Site↔BU | `poz_site_assignments_all_m` | `ASSIGNMENT_ID`, `VENDOR_SITE_ID`, `BU_ID` |
| Classification | `poz_bus_classifications` | `CLASSIFICATION_ID`, `VENDOR_ID`, `LOOKUP_CODE`, `STATUS` |
| Contact | `poz_supplier_contacts` | `VENDOR_CONTACT_ID`, `PER_PARTY_ID`, `PARTY_SITE_ID` |

## Four decisions the next window must make

1. **Strip `EXTN_ATTRIBUTE_*` from the schema CSV?** Drops ~2,000 filler
   rows (mostly on `hz_party_sites`, `hz_organization_profiles`,
   `hz_person_profiles`); file lands ~40 KB. Default: yes.
2. **CSV path in the repo?** Default: `docs/design/sql_overlay/schema.csv`.
3. **BU semantics for "site in US1 Business Unit"?**
   `poz_supplier_sites_all_m.PRC_BU_ID` (primary BU) or
   `poz_site_assignments_all_m.BU_ID` (multi-BU). Default: the
   assignments-table form.
4. **BU lookup strategy?** Resolution A — the Plan carries `BU_ID` as a
   pre-resolved literal; no join needed. No BU lookup table exists in
   the dump. Default: yes.

## Next window agenda (in order)

1. Make decisions 1–4 above.
2. Move `~/poc_schema.csv` into the repo at the chosen path (possibly
   stripped).
3. Edit `docs/design/SQL_OVERLAY_POC.md` — fill in the phase-2 section:
   mapping table, join paths, gap list, Resolution A, the two remaining
   open questions (`PRC_BU_ID` vs `BU_ID`; `INACTIVE_DATE IS NULL` vs
   `ENABLED_FLAG`), "what was not checked".
4. Update the phases table in the POC doc — 1 and 2 → done; 3 pending.
5. Commit both on `poc/sql-overlay`.
6. Begin phase 3: overlay seed (`kg_sql_entity`, `kg_sql_field`,
   `kg_sql_filter` rows for the five entities), loader
   `src/spire/kg/sql_overlay.py`, tripwire test.

## Rules that shape this work

- Rule 5 — approval before generating anything
- Rule 15.1 — capture complete output to a file, then grep
- Rule 15.2 — name a slow command's cost before handing it over
- Rule 15.3 — every file edit is a Python script (cell 1) + shell
  verification (cell 2), two cells, one command at a time
- Rule 4 — no nested code fences; `~~~` for an outer fence whose content
  contains ` ``` `
- Rule 7 — branch-first for code; rule 10 — PR into
  `hardening-master-v2`, never into `master`

## What to share with the new window

- **This handoff** — the single anchor.
- **`plan` bundle** from `context_bundles.yaml` — current-state docs,
  WORKING_STYLE, FIX_PLAN, ARCHITECTURE, FEATURES, SQL_OVERLAY_POC.
- **`reference` bundle** — the endpoints reference is the lookup
  material.
- **`~/poc_schema.csv`** — either pasted, or committed to the branch
  first so the new window can read it via git. Committing first is
  recommended: the file is 3,295 lines and pasting it is a large turn.