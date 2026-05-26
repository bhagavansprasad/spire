## Post-anchor measurement and fix track (F1 → F2 → F3 → F4)

**Date:** 2026-05-26

Continued the work after the deterministic anchor pipeline landed.
The "What's next" items above (formal measurement + scaling beyond
the anchor) drove this batch.

**Initial measurement (`docs/design3_measurement_report.md` v1.0)**
scored Design 3 at **4/7** on the original Track A prompt (the one
with "no invoices in 6 months"). The anchor question itself scored
better, but the original-prompt scoring surfaced two real defects:

1. The planner SILENTLY DROPPED filter types it didn't recognize.
   An intent with `has_no_recent_invoices` executed as if the
   negation clause weren't there — partial answer presented as
   complete. Strictly worse than a crash.
2. No response synthesizer existed. Row 7 of the rubric (final
   structured answer) was a raw printout of executor records.

These drove a four-stage fix track, each landed as its own branch
and PR:

- **F1** (`fix/f1-silent-filter-drop`, merged as `eff11bd`) —
  Planner now raises `NotImplementedError` on unknown filter types
  with a message listing all unknowns plus the supported alternatives.
  Closes the silent-drop defect. 73 → 79 planner tests.

- **F2** (`fix/f2-negation-pattern`, merged as `d93ca80`) — Added
  the `no_invoices_in_N_months` semantic end-to-end. New KG pattern
  (`no_child_in_N_months`) + new pattern binding + planner support
  for a new step shape (`Step.filter_source_when_empty`) + executor
  support for "negation by absence" iteration semantics. The
  executor now dispatches three ways: non-iterating, iterating-and-
  accumulate, iterating-and-filter-source. 79 → 102 planner tests;
  37 → 45 executor unit tests; 2 → 3 executor integration tests
  including a live-Fusion test of the new semantic.

- **F3** (`fix/f3-response-synthesizer`, merged as `6b8979d`) —
  Added the LLM-based response synthesizer. New
  `src/spire/synthesizer/` module with Pydantic-typed structured
  output (`SynthesizedResponse`), ID cross-reference hallucination
  validation against the executor's source data, and 22 unit tests
  + 1 live-Gemini integration test. `scripts/run_plan.py` updated
  with `--intent {anchor,original}` CLI arg, three exit codes per
  pipeline stage, and trace logging of the synthesized response.

- **F4** (same branch as F3) — Re-measurement. Three runs of the
  full pipeline against the original prompt: byte-identical
  executor counts (25/24/28/7 across all three), byte-identical
  structured synthesizer output, prose summary varying only in
  compression (runs 1+2 character-identical at 834 chars; run 3
  shorter at 572 chars). Hallucination guard did not fire on any
  run. **Score: 7/7 on the same rubric Track A scored 1/7 on.**
  See `docs/design3_measurement_report.md` v1.1.

**Stable point tagged as `design3-v1.1-7of7` (commit `6b8979d`).**

### Post-F3 housekeeping

Discovered while running the full test suite that
`tests/test_kg_metadata.py` and `tests/test_kg_loader.py` had been
silently broken on master throughout the F-track: 3 failures out of
235 tests. They had not been caught because our F1/F2/F3 test runs
only targeted the modules we touched (`tests/test_planner.py`,
`tests/test_executor.py`, `tests/test_synthesizer.py`). Real
discipline gap: documenting here so we run full-suite checks
earlier in future work.

Housekeeping branch (`chore/post-f3-housekeeping`):

1. Fixed the stale KG tests — pattern count updated from 4 → 3,
   `no_Y_in_N_months` references renamed to `no_child_in_N_months`,
   parameter expectations updated to the F2 binding's vocabulary.
2. Deleted the 11 per-table SQL files under `sql/kg/v1/`. These
   were the v1.0 seed sequence; `scripts/rebuild_kg.sh` has been
   the monolithic source of truth since v1.0 launched, and F2
   added `no_child_in_N_months` to the rebuild script only —
   leaving the per-table files silently stale. Confirmed safe to
   delete: no Python code imports or executes them; only docstring
   references existed and were updated in the same branch.
3. Rewrote `README.md` (was a 2-line placeholder; now ~180 lines
   with architecture diagram and quick start) and `how-to-run.md`
   (replaced inline credentials with placeholders + added Design 3
   path documentation).

### Roadmap

The planned Phases A → F to move from Design 3 v1.1 to production
are documented in
`docs/designs/design3_v1_to_production_roadmap.md`. Headline order:
gap analysis on diverse prompts → synthesizer schema generalization
→ LLM intent parser → re-validation → production hygiene
(parallelization, caching, observability) → handoff documentation.
