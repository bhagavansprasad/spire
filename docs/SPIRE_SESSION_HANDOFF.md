# SPIRE — Session Handoff, 2026-09-24 (window 16)

**This file supersedes the 2026-09-23 window-5 handoff.** Window 16 closed
F-003, F-050 and F-004 on PR #167; the F-003 regression set shipped as
`ee2b6ca`; WORKING_STYLE 15.1 tightened and 15.3 added. This window
starts the remaining Phase 2 queue.

**Read this first.** Then `docs/AUDIT_AND_FIX.md` (the playbook), which
points to everything else.

---

## Where we are

**Branch:** `hardening-master` at `ac06469`.

**Test suite:** 1214 passed, 1 skipped, 22 deselected (verify at window open).

**Pod:** `dabpqy`.

**Ledger state — FIX_PLAN §5:**

- `verified | #167 | 2026-09-24`: F-003, F-004, F-050.
- `verified | #168 | 2026-09-24`: F-049.
- `not-started`: F-045, F-051, Reg #30.

**Everything before window 16 shipped under earlier windows:** F-002,
F-006–F-020, F-033, F-036, F-039, F-041, F-043–F-044, F-046–F-048,
F-016, F-017, F-027, F-014, and the closed-as-not-a-bug family (F-013,
F-022–F-026, F-028–F-031, F-042). Full ledger in FIX_PLAN §5.

---

## What shipped in window 16

- **PR #167** (`d93d5fd`) — F-003 / F-050 / F-004 on one `_TIER1` edit
  in `src/spire/nl_parser/context_assembly.py`. Every router-scoped
  parse now loads `modes/` and `columns/`. Two op registries synced:
  `draft.py`'s `DraftAggregate.op` gained three PO ops;
  `modes/m_aggregation.sysprompt` gained `top_invoices_by_amount`; the
  `_SYSTEM_PROMPT_PREAMBLE` oracle carries the same. New test
  `tests/test_f003_modes_reachable.py`.
- **`ee2b6ca`** — `scripts/prompts/17_modes_and_columns.txt`, 85-prompt
  regression set for the three fixes. Not in the manifest; run via
  `--prompt-file`.
- **WORKING_STYLE.md 15.1 / 15.3** — two-cell edit discipline;
  15.1's "one-shot" hedge removed.
- **`scripts/prompts/*.json` deleted** — 13 files; recorded metadata
  stale by construction after a scoped-parse change.
- **`tests/test_corpus_consistency.py`** — the file's guard test
  asserted .json corpora existed, which now fails by design; and its
  two content tests passed vacuously on the empty entry list.
  Module-level skip, reason named in the pytest output.
- **Doc B S004** — `02_Phase_02_Correctness.md`; index snapshot
  refreshed.

---

## Outstanding — remaining Phase 2 queue

Three items, in severity order (wrong-data > crash > missing-capability
> cosmetic) per FIX_PLAN §8.3.1:

1. ~~**F-049**~~ — **shipped under PR #168, 2026-09-24.** "invoices
   created before/since X" now routes to `invoice_date`; sysprompt-only,
   mirrors F-046's split.

2. **F-045** — composite `created_since AND created_before` on
   `/purchaseOrders` returns 0 with a misleading capped note
   (wrong-data). Two fix sites: the tool, and the note wording.

3. **F-051** — `fields` + `include`: the caller's `summary_only` gate
   drops child content. Three sites (`promptkit.py:437`,
   `run_prompt_set.py:227`, `run_graph.py:194`). Small.

4. **Reg #30** — compare path pages all POs before narrowing (perf,
   may slip to Phase 6 if architectural).

**Recommendation for window 17 (updated mid-window).** **F-051** next —
three sites, one shape, deterministic, no pod probe. **F-045** after
(wrong-data, two sites, needs a probe against /purchaseOrders).
**Reg #30** last, or defer to Phase 6.

---

## First steps in the new window

1. `git checkout hardening-master && git pull`
2. `git log --oneline -3` — expect `ac06469` at HEAD.
3. `git status` — expect clean tree.
4. `pytest -q` — expect 1214 passed, 22 deselected.
5. Open `docs/phase-2/FIX_PLAN.md` §5. Pick the next `not-started` row
   in §4 order.

---

## What to watch — operational notes

- **Slow commands cost minutes.** Rule 15.2. Aggregations paginate
  ~17,552 POs across 36 pages, ~4 minutes each. Say so before handing
  the command over. Unit tests are the cheap evidence for deterministic
  fixes.

- **Two cells per edit (rule 15.3).** Cell 1 = Python script that
  writes the file. Cell 2 = shell commands whose output is the
  evidence. Cell 1's output does not come back.

- **Full-output capture first.** Rule 15.1. Redirect complete stdout
  AND stderr to a file, then grep. Never pipe the run through a filter
  at capture time — the "one-shot" hedge that used to live in the rule
  is gone.

- **`parse()` vs `route_and_parse()`.** The direct call loads the full
  preamble; the router loads a scoped subset. A pipeline bug must be
  reproduced through the pipeline (`promptkit --run --show-planner`),
  not through `parse()`.

- **MCP server restart after tool signature changes.** Any edit under
  `src/spire/mcp_server/` requires `spire` restart before the new
  signature is live.

- **Terminal shell exits in WSL.** Environmental. Redirect long runs
  to a file so the output survives.

---

## Known doc-drift, recorded not fixed

- `docs/spire-robustness/SESSION_HANDOVER.md` — a second handover file
  in the repo. Not the one a new window reads; the entry point is
  this file. Retire or reconcile — a later decision.
- `scripts/prompts/*.json` corpora are deleted. `--validate` has
  nothing to compare against until they are regenerated. Regeneration
  is a separate task.
- `docs/spire-robustness/00_Doc_B_Index.md` §2.1 Bug register is
  empty (has been since creation). The findings log is the working
  register.
- `scripts/promptkit_sets.yaml` does not list `17_modes_and_columns`.

---

## Commit hashes for reference (window 16)

    1f980d1  test_corpus_consistency: skip module when no .json
             corpora (hardening-master tip)
    081e842  context_bundles: refresh for PR #167 +
             17_modes_and_columns corpus
    14e7cfa  post-merge bookkeeping: F-003 / F-004 / F-050
             -> verified | #167
    ee2b6ca  prompts: add 17_modes_and_columns
    d93d5fd  Merge pull request #167 (F-003 / F-050 / F-004)
    98bd6d9  F-003 / F-050 / F-004: load modes/ and columns/ from a
             router-scoped parse
    a672398  working style: rules 15.1 tightened and 15.3 added
    4c09ae6  scripts/prompts: delete recorded-metadata .json corpora
    9d1bfe0  tracking: close F-003 / F-004 / F-050 in FIX_PLAN,
             findings log, audit
    52dd040  docs: context_bundles (before this window)

---

*End of handover.*
