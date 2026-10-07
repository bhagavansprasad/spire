# SPIRE — SQL Overlay POC, window-31 handoff

**Date:** 2026-10-07
**Branch:** `poc/sql-overlay`, tip `3538263`, in sync with `origin/poc/sql-overlay`
**Parent:** `hardening-master-v2` at `db40182`
**Phase:** all phases (1-7) done; PR #189 open; waiting on review
**Predecessor:** the window-30 handoff, replaced by this document

## What this POC is

Deterministic SQL projection of the Plan. For every Plan step, print the
equivalent Fusion-DB SQL. No LLM in SQL emission — the Plan is a KG lookup,
the SQL is the Plan. **Supplier module only.** Five entities: Supplier,
Address, Site, Classification, Contact. Print only, no execution.

Scope document: `docs/design/SQL_OVERLAY_POC.md`.

## What this window did

1. Confirmed decisions 1–4 from the window-30 handoff.
2. Stripped `EXTN_ATTRIBUTE_*` from the schema CSV (3,293 → 1,420 rows).
3. Renamed and moved the schema to `docs/design/sql_overlay/supplier_schema.csv`.
4. Wrote the phase-2 section: entity → Fusion mapping, join paths,
   gap list, Resolution A, open questions.
5. Ran the five acceptance prompts through the pipeline with `--show-planner`,
   captured the plans.
6. Investigated the OQs with Oracle's own PO Prism query collection:
   - OQ-1 closed (`ENABLED_FLAG = 'Y'`; Q24)
   - OQ-4 closed by curl (`US1 Business Unit = 300000046987012`)
   - OQ-5 decided (schema prefix omitted)
   - Decision 3 flipped to primary-BU form (`PRC_BU_ID`; Q26/Q30)
   - OQ-2 flagged with Oracle's own comment in Q16
   - OQ-3 still open, carried as assumption
7. Built the overlay as Python dataclasses (`src/spire/kg/sql_overlay.py`).
8. Built the emitter (`src/spire/rendering/sql_emitter.py`).
9. Added `--show-sql` to `scripts/promptkit.py`.
10. Ran the acceptance suite; captured five `.sql` files + the full run log.
11. Wrote phase 7: `EXTENDING.md`, `POC2_SKETCH.md`.
12. Fixed the manifest test: bundled every tracked file the branch added.

## Repository state

| Path | What |
|---|---|
| `docs/design/SQL_OVERLAY_POC.md` | Scope doc; 8 phases, all done |
| `docs/design/sql_overlay/supplier_schema.csv` | 12 tables, 1,420 rows |
| `docs/design/sql_overlay/acceptance/` | Five `.sql` captures + run log + plans |
| `docs/design/sql_overlay/EXTENDING.md` | Maintainer guide |
| `docs/design/sql_overlay/POC2_SKETCH.md` | Seven follow-up questions |
| `src/spire/kg/sql_overlay.py` | Overlay as dataclasses |
| `src/spire/rendering/sql_emitter.py` | `emit_sql(plan, overlay)` |
| `tests/test_sql_emitter.py` | 9 tests |
| `docs/reference/sql/` | Four Oracle SQL collections (PO, Cash, PA) |

## Commits on the branch

```
3538263  poc/sql-overlay: phase 7 — extension guide, POC-2 sketch
5b64797  poc/sql-overlay: bundle the overlay files
f33e000  poc/sql-overlay: phases 2-6
```

## Test status

- `pytest -q` → **1290 passed, 1 skipped, 22 deselected** in 222s.
- `pytest tests/test_sql_emitter.py -q` → **9 passed**.
- `pytest tests/test_bundle_manifest.py -q` → **2 passed**.

## What is NOT in this branch

- No SQL execution. Print only.
- No KG tables added. The overlay is parallel.
- No parser, planner, or synthesizer changes.
- No LLM in SQL emission.

## Open questions carried forward (documented, non-blocking)

- **OQ-2** — `POZ_SUPPLIER_CONTACTS.PARTY_SITE_ID` vs `ORG_PARTY_SITE_ID`.
  Emitted SQL uses `PARTY_SITE_ID` with an `-- ASSUMPTION:` comment.
  Oracle's own PO Prism Q16 carries a comment flagging the same ambiguity.
- **OQ-3** — whether `HZ_PARTIES.PARTY_TYPE` needs a predicate. Emitter
  emits none, flags the assumption.

Both deferred to POC-2. See `POC2_SKETCH.md`.

## Deviations from the scope doc

- **Overlay as Python, not six Oracle tables.** Content matches what the
  six `kg_sql_*` tables would hold; storage differs. Migration is a POC-2
  item. Recorded in the scope doc's Deviations section.
- **Decision 3 flipped.** Primary-BU form (`PRC_BU_ID`), not assignments
  form. Oracle's own Q26/Q30 use this form.

## Next window agenda (in order)

1. **Review PR #189.** It is `poc/sql-overlay` → `hardening-master-v2`.
2. If approved, merge. Do not merge to `master`.
3. If changes requested, apply on the branch; PR auto-updates.
4. If the reviewer wants the overlay as Oracle tables before merge, that
   is a re-scope. It is not in the current PR.
5. When merged, decide whether to start POC-2 (`POC2_SKETCH.md`).

## Rules that shaped this work

- Rule 5 — approval before generating anything
- Rule 15.1 — capture complete output to a file, then grep
- Rule 15.2 — name a slow command's cost before handing it over
- Rule 15.3 — every file edit is a Python script + shell verification,
  two cells, one command at a time
- Rule 4 — no nested code fences
- Rule 7 — branch-first for code
- Rule 10 — PR into `hardening-master-v2`, never into `master`

## What to share with the new window

- **This handoff** — the single anchor.
- **`plan` bundle** from `context_bundles.yaml` — current-state docs,
  WORKING_STYLE, FIX_PLAN, ARCHITECTURE, FEATURES, SQL_OVERLAY_POC.
- **`reference` bundle** — the endpoints reference.
- **The branch** `poc/sql-overlay` on origin, or a fresh clone with
  `git checkout poc/sql-overlay`.
