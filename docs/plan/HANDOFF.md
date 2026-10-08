# SPIRE — SQL Overlay POC, window-33 handoff

**Date:** 2026-10-08
**Branch:** SQL-overlay work complete. Integration branch is now `master`.
**master tip:** `3c4b208` (PR #191 merged 2026-10-08T11:32Z)
**Predecessor:** the window-32 handoff, superseded by this document

## What changed since window 32

**Integration branch moved from `hardening-master-v2` to `master`.**
The SQL Overlay POC promoted to `master` via PR #191 on 2026-10-08. All
new work branches from and merges into `master`. `hardening-master-v2`
is a historical branch, left in place, not used for new work. The
runtime clone now pulls from `master`.

WORKING_STYLE rule 10 has been updated to match. The old
"Nothing merges to master without explicit instruction" clause has
been retired — it existed to protect a frozen `master`, and `master`
is no longer frozen.

## What this POC is

Deterministic SQL projection of the Plan. For every Plan step, print
the equivalent Fusion-DB SQL. No LLM in SQL emission — the Plan is a
KG lookup, the SQL is the Plan. **Supplier module only.** Five
entities: Supplier, Address, Site, Classification, Contact. Print
only, no execution.

Scope document: `docs/design/SQL_OVERLAY_POC.md`.

## What landed in window 32

Three PRs merged end to end:

| PR | Title | Merged into | Merge commit |
|---|---|---|---|
| #189 | SQL Overlay POC (supplier module) | hardening-master-v2 | a8e83e7 |
| #190 | SQL projection as a first-class diagnostic | hardening-master-v2 | a076ded |
| #191 | promote: hardening-master-v2 → master | master | 3c4b208 |

Branches deleted after merge: `poc/sql-overlay`,
`feat/show-sql-diagnostic`, `promote/hardening-master-to-master`.
History is reachable through the merge commits on `master`.

## What changed in the POC

1. **SQL projection became a first-class diagnostic.** `show_sql` is
   a registered flag in `src/spire/diagnostics.py` (logger
   `spire.sql`). It honours the file / env / CLI / `--show-all` layers
   uniformly, and `--manifest` batch mode forwards it automatically.

2. **`show_all` semantics: override, not default.** When
   `show_all = true`, every gated flag becomes true regardless of any
   explicit value in any layer.

3. **`prompts/sample_prompts.txt` added** — a cross-module smoke set.
   Not part of the SQL overlay POC.

4. **`personas.yaml` credentials rotated on master** (`47907f8`).
   Task 1.1 of the main plan (untrack + gitignore) is still pending.

5. **Schema CSV renamed and stripped.**
   `docs/design/poc_schema.csv` → `docs/design/sql_overlay/supplier_schema.csv`,
   3,293 → 1,420 rows.

## Repository state

| Path | What |
|---|---|
| `docs/design/SQL_OVERLAY_POC.md` | POC-1 scope doc; all seven phases done |
| `docs/design/sql_overlay/supplier_schema.csv` | 12 tables, 1,420 rows |
| `docs/design/sql_overlay/acceptance/` | Five `.sql` captures + run log + plans |
| `docs/design/sql_overlay/EXTENDING.md` | Maintainer guide |
| `docs/design/sql_overlay/POC2_SKETCH.md` | Seven follow-up questions |
| `src/spire/kg/sql_overlay.py` | Overlay as Python dataclasses |
| `src/spire/rendering/sql_emitter.py` | `emit_sql(plan, overlay)` |
| `src/spire/diagnostics.py` | `show_sql` flag registered; `spire.sql` logger |
| `scripts/promptkit.py` | `--show-sql` via the diagnostics layer |
| `tests/test_sql_emitter.py` | 9 tests |
| `tests/test_diagnostics.py` | 65 tests (GATED set now 7 flags) |
| `docs/reference/sql/` | Four Oracle SQL collections (PO, Cash, PA) |

## Test status

- `pytest -q` → 1290 passed, 1 skipped, 22 deselected (last full run
  before the diagnostic change).
- `pytest tests/test_sql_emitter.py -q` → 9 passed.
- `pytest tests/test_diagnostics.py -q` → 65 passed.
- `pytest tests/test_bundle_manifest.py -q` → 2 passed.

Note: the full suite has not been re-run after the diagnostic merge.
A fresh window should re-run `pytest -q` before starting POC-2.

## What is NOT in this POC

- No SQL execution. Print only.
- No KG tables added. The overlay is parallel.
- No parser, planner, or synthesizer changes.
- No LLM in SQL emission.

## Open questions carried forward (documented, non-blocking)

- **OQ-2** — `POZ_SUPPLIER_CONTACTS.PARTY_SITE_ID` vs
  `ORG_PARTY_SITE_ID`. Emitted SQL uses `PARTY_SITE_ID` with an
  `-- ASSUMPTION:` comment. Oracle's own PO Prism Q16 carries a
  comment flagging the same ambiguity.
- **OQ-3** — whether `HZ_PARTIES.PARTY_TYPE` needs a predicate.
  Emitter emits none, flags the assumption.

Both deferred to POC-2. See `POC2_SKETCH.md`.

## Deviations from the scope doc

- **Overlay as Python, not six Oracle tables.** Content matches what
  the six `kg_sql_*` tables would hold; storage differs. Migration is
  a POC-2 item. Recorded in the scope doc's Deviations section.
- **Decision 3 flipped.** Primary-BU form (`PRC_BU_ID`), not the
  assignments form. Oracle's own Q26/Q30 use this form.

## Next window agenda (in order)

POC-2 starts from `master` at `3c4b208`.

1. **Create `poc/sql-overlay-2` from `master`.**
2. **Confirm DB access first.** The POC so far is print-only; no query
   has run. Before any plan is proposed, confirm what exists —
   SQL*Plus, python-oracledb, a read-only account, or nothing — and
   whether the Fusion DB is reachable from this environment.
3. **If DB access exists**, start POC-2 item 1 of `POC2_SKETCH.md`:
   validate the emitted SQL against the real Fusion DB.
4. **If DB access does not exist**, item 1 is blocked. Pick a
   different POC-2 item — sketch items 2 (close OQ-2/OQ-3 by schema
   read), 3 (views vs base tables), or 5 (migrate overlay to Oracle
   tables) do not require a live DB.
5. **PR into `master`.** Every change arrives via a PR; no local
   merges.

## Rules that shaped this work

- Rule 5 — approval before generating anything
- Rule 15.1 — capture complete output to a file, then grep
- Rule 15.2 — name a slow command's cost before handing it over
- Rule 15.3 — every file edit is a Python script + shell verification,
  two cells, one command at a time
- Rule 4 — no nested code fences
- Rule 7 — branch-first for code
- Rule 10 — integration branch is `master`; PR into it

## What to share with the new window

- **This handoff** — the single anchor.
- **`docs/design/sql_overlay/POC2_SKETCH.md`** — the working document.
- **`docs/design/SQL_OVERLAY_POC.md`** — the POC-1 scope doc.
- **`docs/design/sql_overlay/EXTENDING.md`** — maintainer guide.
- **`context_bundles.yaml`** — bundle definitions.
- Repo state — the output of `git branch` / `git status` /
  `git log --oneline -5`.
