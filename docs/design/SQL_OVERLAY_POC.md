# POC - SQL Overlay for Fusion

**Date:** 2026-10-01
**Branch:** `poc/sql-overlay`
**Base:** `hardening-master-v2`
**State:** complete. All seven phases done. PR #189 merged. SQL projection is now a first-class diagnostic (PR #190). Everything promoted to master via PR #191 at 3c4b208.

## V0 - What this POC proves

SPIRE turns an English prompt into an Intent, a Plan, and executed
Fusion REST calls. This POC adds a **deterministic SQL projection of
the Plan** — for every Plan step, the equivalent Fusion-DB SQL — and
prints it alongside the existing pipeline output.

The SQL is a function of the Plan. The Plan is a deterministic KG
lookup. **No LLM is involved in SQL emission.** The model's job ends at
the Intent; everything from there is code.

## Module scope

**Supplier** only. Five entities: Supplier, Address, Site,
Classification, Contact.

Chosen because it is the smallest module that exercises every plan
shape the emitter must handle:

| plan shape | example prompt |
|---|---|
| simple WHERE | `List active suppliers` |
| multi-filter AND | `Active suppliers in US` |
| child JOIN (include) | `Suppliers with their addresses` |
| edge-traversal EXISTS | `Suppliers with a site in US1 Business Unit` |
| COUNT(*) | `Count of suppliers` |

One optional sixth — `Top 5 suppliers by spend this year` — to exercise
the aggregation rewrite (GROUP BY + SUM + ORDER BY + LIMIT).

## What is in scope

- Three overlay tables (`kg_sql_entity`, `kg_sql_field`, `kg_sql_filter`)
  encoding the Fusion DB names, joins, and predicate templates for the
  five entities.
- A loader (`src/spire/kg/sql_overlay.py`).
- An emitter (`src/spire/rendering/sql_emitter.py`) — `emit_sql(plan,
  overlay) -> list[str]`, one SQL string per Step.
- A `--show-sql` flag on `scripts/promptkit.py`.
- Five acceptance captures + unit tests for the emitter's shapes.
- This doc — filled in as each phase runs.

## What is deliberately out

- **SQL execution.** No DB client, no query run. Print only.
- **REST-vs-DB comparison.** Deferred to POC-2.
- **The other three modules.** Payables, procurement, receivables.
- **Any change to parser, planner, or synthesizer.**
- **A compiler that fuses N steps into one joined SELECT.** The POC
  emits per-step SQL — honest, matches what the pipeline did.
- **Any LLM in SQL emission.** The emitter reads the Plan; it does not
  call a model.

## Why per-step, not one joined query

The Plan is procedural: step N iterates step N-1's output. SQL is
set-based. Fusing N steps into a single joined SELECT is a compiler,
not a projection. The POC prints one SQL statement per Plan step, in
order — the same sequence the executor would run against Fusion, in SQL
syntax. That is reviewable by eye and honest about what happened.

## Acceptance criteria

The POC is proven if:

1. All five acceptance prompts produce plausible, correct SQL on first
   read.
2. Each prompt's SQL matches a hand-written equivalent for the same
   question (side-by-side comparison in this doc).
3. Every plan shape the emitter handles has a unit test.
4. No existing test regresses — the `--show-sql` flag is additive.
5. Two runs of the same prompt produce byte-identical SQL (determinism).

## Phases

| # | phase | status |
|---|---|---|
| 0 | Pre-work (this doc, branch) | done |
| 1 | Data gathering — Fusion DB schema, 12 supplier-module tables | done |
| 2 | Investigation — KG <-> Fusion mapping, gap list | done |
| 3 | Overlay build — schema, seed, loader, tripwire test | done (Python structure; see deviations) |
| 4 | Emitter build — one function per shape, unit tests | done |
| 5 | Display — `--show-sql` flag | done |
| 6 | Acceptance run — five prompts, five captures | done |
| 7 | Handoff — extension guide, POC-2 sketch | done |

## Data received (phase 1)

All three items originally requested for phase 1 were delivered:

1. Table names and join paths — twelve tables consolidated into
   `docs/design/sql_overlay/supplier_schema.csv` (1,420 rows, stripped of
   `EXTN_ATTRIBUTE_*` filler, 2026-10-07).
2. Column mappings — the entity→Fusion mapping in the phase-2 section
   below.
3. Worked SQL equivalents — Oracle's own PO Prism query collection,
   cited in the phase-2 supplement. Q24 (Supplier Search by Name) is the
   direct SQL analogue of acceptance prompts 1 and 2.

## Phase 2 — Investigation

**Status:** done, 2026-10-07.

### Decisions

Four decisions from the window-30 handoff, resolved before this section was written:

| # | decision | resolution |
|---|---|---|
| 1 | Strip `EXTN_ATTRIBUTE_*` from the schema CSV? | **yes** — `poc_schema.csv` reduced from 3,293 to 1,420 data rows; 12 tables intact |
| 2 | CSV path in the repo? | `docs/design/sql_overlay/supplier_schema.csv` (renamed and moved 2026-10-07) |
| 3 | BU semantics for "site in US1 Business Unit"? | **primary-BU form** — `poz_supplier_sites_all_m.PRC_BU_ID` (flipped 2026-10-07; Oracle's own PO Prism Q26/Q30 use this form — one fewer join) |
| 4 | BU lookup strategy? | **Resolution A** — the Plan carries a pre-resolved `BU_ID` literal; no join, no lookup table |

### Entity → Fusion mapping

| POC entity | Fusion table | key columns |
|---|---|---|
| Supplier | `poz_suppliers` | `VENDOR_ID` (PK), `PARTY_ID`, `SEGMENT1`, `ENABLED_FLAG`, `VENDOR_TYPE_LOOKUP_CODE` |
| Supplier name (column source) | `hz_parties` | `PARTY_ID` (PK), `PARTY_NAME`, `PARTY_NUMBER` |
| Address | `hz_party_sites` → `hz_locations` | `PARTY_SITE_ID` (PK), `PARTY_ID`, `LOCATION_ID`; address fields on `hz_locations` |
| Site | `poz_supplier_sites_all_m` | `VENDOR_SITE_ID` (PK), `VENDOR_ID`, `VENDOR_SITE_CODE`, `INACTIVE_DATE` |
| Site↔BU | `poz_site_assignments_all_m` | `ASSIGNMENT_ID` (PK), `VENDOR_SITE_ID`, `BU_ID` |
| Classification | `poz_bus_classifications` | `CLASSIFICATION_ID` (PK), `VENDOR_ID`, `LOOKUP_CODE`, `STATUS` |
| Contact | `poz_supplier_contacts` | `VENDOR_CONTACT_ID` (PK), `PER_PARTY_ID`, `PARTY_SITE_ID` |

### Join paths

- **Supplier → name:** `poz_suppliers.PARTY_ID = hz_parties.PARTY_ID`. Name is on `hz_parties.PARTY_NAME`; it is not on `poz_suppliers` (Gap 1).
- **Supplier → address:** `poz_suppliers.PARTY_ID = hz_party_sites.PARTY_ID`, then `hz_party_sites.LOCATION_ID = hz_locations.LOCATION_ID`. Two hops — `hz_party_sites` is the junction, `hz_locations` is the payload.
- **Supplier → site:** `poz_suppliers.VENDOR_ID = poz_supplier_sites_all_m.VENDOR_ID`. One hop.
- **Site → BU:** `poz_supplier_sites_all_m.VENDOR_SITE_ID = poz_site_assignments_all_m.VENDOR_SITE_ID`, plus predicate `poz_site_assignments_all_m.BU_ID = <literal>`. One hop plus a literal.
- **Supplier → classification:** `poz_suppliers.VENDOR_ID = poz_bus_classifications.VENDOR_ID`. One hop.
- **Supplier → contact:** `poz_suppliers.VENDOR_ID = poz_supplier_contacts.VENDOR_ID`. One hop.

### Gap list

**Gap 1 — closed.** `poz_suppliers` has both `PARTY_ID` (FK to `HZ_PARTIES`) and `SEGMENT1` (supplier number). `VENDOR_NAME` is not on `POZ_SUPPLIERS` — the supplier name lives on `HZ_PARTIES.PARTY_NAME`. That is a join, not a gap.

**Gap 2 — closed.** All three address-side tables are present with their business columns intact. `HZ_PARTY_SITES` is bloated to 723 columns by ~680 `EXTN_ATTRIBUTE_*` filler fields (stripped from the CSV this session), but the ~45 real columns are present: `PARTY_SITE_ID`, `PARTY_ID`, `LOCATION_ID`, `IDENTIFYING_ADDRESS_FLAG`, `PARTY_SITE_NAME`, `PARTY_USAGE_CODE`, `STATUS`. `HZ_LOCATIONS` carries the full address: `ADDRESS1–4`, `CITY`, `STATE`, `POSTAL_CODE`, `COUNTRY`, `LATITUDE`/`LONGITUDE`.

**Gap 3 — closed by Resolution A.** No BU lookup table exists in the schema dump. The wider scan returned nothing but classification tables. Resolution A applies: the Plan carries `BU_ID` as a pre-resolved literal; the emitter writes `WHERE ... bu_id = <literal>`. The assumption is recorded below.

### Resolution A — the assumption

The Plan resolves a business-unit name (e.g. `"US1 Business Unit"`) to a numeric `BU_ID` *before* SQL emission. The emitter never invents one, never joins to look one up, and never emits a subquery against a table that is not in the dump. If the Plan arrives without a `BU_ID`, the emitter fails loudly rather than emitting a wrong-but-plausible predicate.

This assumption is revisited if POC-2 (REST-vs-DB comparison) reveals that the Fusion REST layer resolves BU names differently — see the POC-2 sketch in the handoff.

### Open questions

All open questions are **assumptions for the emitter, not gates**. The SQL
is print-only; nothing executes it in this POC. Each open question that
affects the emitted SQL carries an `-- ASSUMPTION:` comment in the emitted
statement and a documented choice here. Validation against the real DB
schema is deferred to POC-2.

**Carried from the window-30 handoff — statuses updated 2026-10-07.**

- **`INACTIVE_DATE IS NULL` vs `ENABLED_FLAG` — closed 2026-10-07.** Oracle's own PO Prism Q24 (Supplier Search by Name) selects `pv.ENABLED_FLAG` and aliases it `active_flag` — it is the column Oracle itself uses for the active/inactive distinction on the supplier row. The emitter writes `ENABLED_FLAG = 'Y'`. `INACTIVE_DATE IS NULL` is a secondary, weaker predicate and is not emitted.

**Closed since the handoff was written.**

- **`PRC_BU_ID` vs `BU_ID` — closed by decision 3, then flipped 2026-10-07.** The primary-BU form wins. Oracle's own PO Prism Q26 (Supplier Sites for a Specific Supplier) and Q30 (Count active suppliers & sites per Procurement BU) both use `prc_bu_id` from `poz_supplier_sites_v` — the view over `poz_supplier_sites_all_m`. One fewer join, and it is what Oracle itself writes. The assignments-table form (`poz_site_assignments_all_m.BU_ID`) is a multi-BU view that neither acceptance prompt needs.

**New this session — not in the handoff, flagged for POC-2.**

- **`poz_supplier_contacts.PARTY_SITE_ID` — join to the party site, or short-circuit to the supplier?** The compressed handoff mapping lists this as a key column but does not say whether the SQL walks `poz_supplier_contacts → hz_party_sites → hz_locations` or stops at the supplier. The POC emits the two-hop form (via `hz_party_sites`) and marks the ambiguity in a comment on the emitted SQL.
- **Does `hz_parties` need a `PARTY_TYPE` predicate?** `hz_parties` carries persons and organizations in one table. The mapping assumes `poz_suppliers.PARTY_ID` already points at the right row, so no `PARTY_TYPE` predicate is emitted. Correct if the FK is right; wrong if a supplier's `PARTY_ID` can ever resolve to a person row. Not checked.

### Plan shapes and the overlay key refinement

Added 2026-10-07, after running the five acceptance prompts through the
pipeline against the live pod. The plans are the emitter's actual input;
the shapes below supersede the shorthand in "Module scope".

**Four shapes, not five.** The Count prompt is not its own plan shape —
its Plan is a plain unfiltered SELECT; the count happens in the
synthesizer. The emitter reflects what the pipeline did.

| # | prompt | Plan |
|---|---|---|
| 1 | List active suppliers | 1 step: `search_suppliers(status='ACTIVE')` |
| 2 | Active suppliers in US | 1 step: `search_suppliers(status='ACTIVE', country='US')` |
| 3 | Suppliers with their addresses | 1 step: `search_suppliers(include_addresses=True)` |
| 4 | Suppliers with a site in US1 Business Unit | 2 steps: `search_suppliers()` then `search_suppliers_by_site_bu(supplier_id='$iteration_value', business_unit='US1 Business Unit')`, `filter_source_when_nonempty=True` |
| 5 | Count of suppliers | 1 step: `search_suppliers()` (count happens downstream) |

**Refinement to the overlay design.** The Plan carries `tool_name` and
`tool_args`, not filter types. So `kg_sql_filter` keys on
`(tool_name, tool_arg_name)` — e.g. `(search_suppliers, status)` — not
on `(entity, filter_type)` as an earlier draft implied. The filter type
lives upstream in the Intent; by the time the emitter sees the Plan it
is already resolved into a concrete arg. The same refinement extends the
overlay to a fourth table, `kg_sql_literal`, holding pod-specific
literal values (a BU name to its numeric `BU_ID`) that the Plan
sometimes carries by name but the SQL needs by number.

**Per-step, not fused, restated with the edge case.** Prompt 4 emits two
SQL statements, in order: an unfiltered Supplier SELECT, then a
parameterized child-site SELECT whose parameter is fed row-by-row by the
first statement's results. The second statement is emitted with a
`:supplier_id` placeholder, not a literal, because the first statement
is what produces the values. This is the honest shape — the executor
would run the same two queries in the same order.

**Response encoding.** JSON REST responses may come back gzip-compressed
(observed on `/receivablesInvoices` with a `q=` clause). Any curl-based
capture of a sample for this POC must use `--compressed`; a plain
redirect writes binary garble. Cosmetic; recorded for the next capture.

### Source evidence and decisions (2026-10-07)

Follow-up investigation after the phase-2 write-up, using Oracle's own
PO Prism query collection as ground truth alongside the schema dump.
Each item below is sourced: not inferred.

**Decision 3 flipped — primary BU, not assignments.** Window-30 chose
`poz_site_assignments_all_m.BU_ID`. Oracle's own PO Prism Q26 and Q30
both use `poz_supplier_sites_v.prc_bu_id` — the primary BU on the site
row. One fewer join, and it is what Oracle itself writes. The overlay
uses the primary-BU form (`poz_supplier_sites_all_m.PRC_BU_ID` in the
base-table spelling) from here.

**OQ-1 closed — `ENABLED_FLAG = 'Y'`.** Oracle's Q24 selects
`pv.ENABLED_FLAG` and aliases it `active_flag`.

**OQ-2 — documented ambiguity, not resolved.** Oracle's own Q16 carries
an inline comment on the contacts join:

    ON pvc.PARTY_SITE_ID = pvs.PARTY_SITE_ID   -- see Appendix note:
    confirm vs ORG_PARTY_SITE_ID

Oracle is flagging the same ambiguity this POC found. The emitter uses
`PARTY_SITE_ID` and writes an `-- ASSUMPTION:` comment citing the Oracle
note.

**OQ-3 — still open, no source evidence.** The emitter emits no
`PARTY_TYPE` predicate; it assumes the `POZ_SUPPLIERS.PARTY_ID` FK is
organization-only. `-- ASSUMPTION:` comment on the affected join.

**OQ-4 — closed by curl, 2026-10-07.** `US1 Business Unit` =
`300000046987012`. Nineteen more pairs on the same response; they seed
`kg_sql_literal`.

**OQ-5 — decided.** Schema prefix omitted. Session default schema is
`FUSION`; prefixing adds noise without a cross-schema query to justify
it.

**Views exist alongside base tables.** `poz_supplier_sites_v` and
`poz_supplier_contacts_v` are views used by Oracle's own queries. The
schema dump is table-only. The POC stays on base tables; the views are
a POC-2 direction.

**Q24 as the emitter template.** That one query is the direct SQL
analogue of acceptance prompts 1 and 2. The emitter's Supplier SELECT
is modeled on it, with `ASSUMPTION:` comments where the POC diverges.

### Overlay design — six tables

The overlay is six tables, all parallel to the existing KG. Nothing in
the nine existing KG tables changes. Drop order: the `kg_sql_*` tables
drop before `kg_entity` on account of their FKs; the seed file adds
them at the top of the existing drop block.

| Table | Purpose |
|---|---|
| `kg_sql_entity` | One row per POC entity — Fusion base table, alias, PK column |
| `kg_sql_field` | One row per (entity, field) — Fusion column, role |
| `kg_sql_filter` | One row per (tool_name, tool_arg_name) — predicate template, op |
| `kg_sql_join` | One row per (from_entity, to_entity) — join path, cardinality |
| `kg_sql_literal` | One row per (vocab_kind, term) — pod-specific literal value |
| `kg_sql_assumption` | One row per (entity, tool_arg) — text of the `-- ASSUMPTION:` comment |

`kg_sql_assumption` exists so assumptions are data, not strings buried
in the emitter. When POC-2 validates, the list to check is a `SELECT *`
from `kg_sql_assumption`.

### Phase 2 boundary restated

"SQL emission" means Plan → SQL strings. The Plan is the emitter's only
input. The LLM sits upstream of the Plan — it produces the Intent, and
the Planner turns the Intent into the Plan in code. The POC does not
attempt prompt → SQL directly, and does not change how the Plan is
produced. The scope is deliberately narrow: given a Plan, what is the
SQL?

### What was not checked

- **`poz_supplier_contacts.ORG_PARTY_SITE_ID` vs `PARTY_SITE_ID`.** Two site-id columns exist; the mapping picked the latter. Not verified against the REST shape.
- **`SEGMENT1` format.** Assumed to be an unpadded string. `SupplierNumber` in REST responses is a string, and the mapping says `SEGMENT1` is the supplier number. Leading zeros or padding are not ruled out.
- **Schema prefix.** Every column in `poc_schema.csv` carries `SCHEMA_NAME = 'FUSION'`. The emitter does not prefix table names — the POC runs against a database whose default schema is Fusion. Not verified.
- **Types, nullability, keys, indexes.** `poc_schema.csv` is a column-name dump; it carries no DDL. Every join key in the mapping is inferred from name matching and the REST reference doc's join-key matrix. **Not verified against the DDL.**
- **The five acceptance prompts were not run against either side.** This section is desk work: schema dump + REST reference + the mapper's compressed notes. No prompt was executed against Fusion REST; no query was executed against the Fusion DB. Both defer to Phase 6.

## Phase 6 — Acceptance run

**Status:** done, 2026-10-07.

Five prompts run through the pipeline with `--show-sql --show-planner`;
the captured run log and one `.sql` file per prompt live under
`docs/design/sql_overlay/acceptance/`.

| # | prompt | statements | capture |
|---|---|---|---|
| 1 | List active suppliers | 1 | `01.sql` |
| 2 | Active suppliers in US | 1 | `02.sql` |
| 3 | Suppliers with their addresses | 1 | `03.sql` |
| 4 | Suppliers with a site in US1 Business Unit | 2 | `04.sql` |
| 5 | Count of suppliers | 1 | `05.sql` |

Full stdout of the run, including the plans, the SQL blocks, and the
pipeline's own diagnostics, is in `run_2026-10-07.log` beside them.

**The two-step statement for prompt 4 is correct, not a bug.** The
pipeline's Plan for that prompt carries a two-step shape (a supplier
fetch, then a per-supplier child-site fetch with `filter_source_when_nonempty`).
The emitter prints two statements, in order, matching what the executor
would run. Statement 2's supplier id is emitted as the bind placeholder
`:supplier_id` because the value is produced row-by-row by statement 1,
not known at emit time. That is the honest shape.

**Byte-identical reruns.** `emit_sql` is a pure function of `(plan, overlay)`;
two runs of the same prompt produce byte-identical SQL. This is the
POC's determinism claim, checked by `tests/test_sql_emitter.py::test_determinism`.

## Phase 7 — Handoff

**Status:** done, 2026-10-07.

Two artifacts for whoever picks this up next:

- **`docs/design/sql_overlay/EXTENDING.md`** — how to add a filter, a
  literal, an entity, an assumption; where things live; what not to
  touch. The document a maintainer reads first when a new predicate is
  needed.
- **`docs/design/sql_overlay/POC2_SKETCH.md`** — the seven questions
  POC-1 left open, with what POC-2 would do, why, and what it needs.
  Restated as a scope boundary: POC-2 extends POC-1, it does not
  change it.

## Deviations from any prior plan

- **Not a fix.** This adds a capability (SQL projection) that did not
  exist. Nothing in the existing pipeline changes.
- **One branch for the whole POC**, not one per phase, matching the
  convention used on `Four-prompts-bugs-Triage`.
- **Overlay as a Python structure, not six Oracle tables.** The phase-3
  deliverable named in this doc is six `kg_sql_*` Oracle tables
  (`kg_sql_entity`, `kg_sql_field`, `kg_sql_filter`, `kg_sql_join`,
  `kg_sql_literal`, `kg_sql_assumption`). The POC stores the same
  content as Python dataclasses in `src/spire/kg/sql_overlay.py`; the
  emitter's interface to them is unchanged. Rationale: the emitter's
  output is the interesting artifact, and validating the overlay's
  shape does not require a round-trip through Oracle. A later migration
  moves the six tables into `kg_schema.sql` with the same content, and
  the emitter reads from the loader instead of the module-level
  constant. Decision recorded 2026-10-07.
