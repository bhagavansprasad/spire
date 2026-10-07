# POC-2 sketch

Not a plan; a set of questions POC-1 deliberately left open. Each item
names what POC-2 would do, why, and what it would need.

## 1. Validate the emitted SQL against the real DB

**Question.** Does `SELECT P.VENDOR_ID ... FROM POZ_SUPPLIERS P
JOIN HZ_PARTIES HP ...` return the same rows as the REST call
`/suppliers?q=SupplierNumber='1252'`?

**POC-2 does.** For each acceptance prompt, run the emitted SQL against
the Fusion DB, run the REST call, compare row counts and key columns.

**Needs.** A DB client (SQL*Plus, python-oracledb, or similar) and read
access to the Fusion schema. The POC-1 schema dump has column names
only — POC-1 never touched the live DB.

**Deliverable.** A table, one row per prompt, showing REST count vs DB
count vs match/mismatch.

## 2. Close OQ-2 and OQ-3

**OQ-2.** Contact joins via `PARTY_SITE_ID` or `ORG_PARTY_SITE_ID`?
Oracle's own Q16 carries a comment flagging the same ambiguity. POC-2
reads the actual `POZ_SUPPLIER_CONTACTS` column definitions and settles
it.

**OQ-3.** Does the supplier→name join need a `HZ_PARTIES.PARTY_TYPE`
predicate? Read the column, sample rows, decide.

## 3. The views question

The schema dump is table-only. Oracle's own PO Prism queries use views
(`poz_supplier_sites_v`, `poz_supplier_contacts_v`). POC-2 decides
whether the overlay targets views or base tables, and if views, dumps
their DDL.

## 4. Extend to payables, procurement, receivables

POC-1 scoped five supplier entities. The other three modules have their
own entity sets. POC-2 adds their schemas and mappings, following the
same pattern.

**Deliverable.** Three additional overlay modules:
`payables_overlay.py`, `procurement_overlay.py`,
`receivables_overlay.py`.

## 5. Migrate the overlay to Oracle tables

POC-1 stored the overlay as Python dataclasses (see the deviations
section of `../SQL_OVERLAY_POC.md`). POC-2 moves the six tables
(`kg_sql_entity`, `kg_sql_field`, `kg_sql_filter`, `kg_sql_join`,
`kg_sql_literal`, `kg_sql_assumption`) into `scripts/sql/kg_schema.sql`
and adds a loader `src/spire/kg/sql_overlay_loader.py`. The emitter's
interface does not change — it takes an `Overlay` object either way.

## 6. Optional — fuse N steps into one SELECT

POC-1 emits per-step SQL (see "Why per-step, not one joined query" in
the scope doc). POC-2 could add a compiler that recognizes a two-step
fetch-then-filter shape and emits a single `EXISTS`-joined SELECT.

**Non-trivial.** The Plan is procedural; SQL is set-based. An N+1 fetch
pattern is a Plan shape, not a query shape.

**Defer unless there is a reason.** The current form is reviewable by
eye and matches what the executor actually does.

## 7. Coverage sweep against the supplier prompt corpus

POC-1 ran five acceptance prompts plus a small supplemental set. The
full supplier corpus (`prompts/supplier/{smoke,verify,exhaust}.txt`,
`prompts/sme/testcases.txt`, and the supplier halves of
`prompts/payables_supplier/` and `prompts/procurement_supplier/`) has
not been run with `--show-sql`.

**Deliverable.** A pass/fail table, one row per prompt: plan emitted,
SQL emitted, SQL correct by eye, or honest gap.

## Scope boundary

POC-2 is a separate POC. It does not change POC-1's code; it extends
it. The POC-1 branch merges as a self-contained artifact, with these
items as named follow-ups.

## Not in POC-2

- Any change to the KG, parser, planner, or synthesizer.
- A re-litigation of POC-1's design decisions (per-step emission,
  Python-stored overlay, no LLM in emission).
- Anything from the main plan's phases 3f, 6c, 6d.
