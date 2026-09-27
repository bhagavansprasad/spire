# SPIRE — Session Handoff, 2026-09-24 (window 19)

**This file supersedes the window-18 handoff.** Window 18 closed the
last two Phase 2 rows (F-045, Reg #30). Window 19 was a single-purpose
session: the prompt-set reorg. Phase 3a has not been started.

**Read this first.** Then `docs/fixes/FIXES.md` (the playbook). The
`plan` context bundle carries this file plus everything referenced
below.

---

## Where we are

**Branch:** `hardening-master` at `369cc63`.

**Test suite:** not re-run this session. Last known good after the
reorg's test-path fix: `tests/test_nl_parser_capability.py` — 101
passed, 1 deselected. Full suite was 1229 passed / 1 skipped / 22
deselected at window 18 close.

**Pod:** `dabpqy`.

**Ledger:** FIX_PLAN §5 unchanged — Phase 2 closed 24/24. No new
F-NNNs from this session.

---

## What shipped in window 19

Three commits on `hardening-master`, all pushed:

- `aacf9b2` — `docs/prompt-sets/SURFACE.md`. Capability surface, tier
  plan, legacy cross-walk. Stages 1+2 of the reorg.
- `374afd3` — the reorg itself. `scripts/prompts/` moved to `prompts/`
  at the repo root; new tiered structure; every live reference
  patched.
- `369cc63` — `.gitignore` gains `t_*.txt` (run-capture artifacts).

### The reorg, in one paragraph

Prompt sets are content, not build tooling. They moved out of
`scripts/` to `prompts/` at the repo root — the location Doc A §10.3.1
already specified for Phase 4a. The new tree has two axes: **modules
and combinations** are folders, each holding three tiers
(`smoke.txt` / `verify.txt` / `exhaust.txt`); **cross-cutting
features** are flat files at the root, named `<tier>_<feature>.txt`.
16 capabilities, 37 files, ~1,512 runnable prompts — roughly 3x the
pre-reorg ~500.

### What "the tiers" mean

- **smoke** — alive. Does it work at all. Every prompt must answer.
- **verify** — correct. Normal shapes, edges, refusals.
- **exhaust** — stress. Every variation we know. Goal: find a crash.
  If exhaust runs clean, the prompts are not exhaustive enough yet.

### Capability surface

Four modules: `supplier`, `payables`, `procurement`, `receivables`.
Three combinations: `payables_supplier`, `payables_procurement`,
`procurement_supplier`. Nine cross-cutting features: `columns`,
`refusals`, `lifecycle`, `child_as_root`, `truncation`,
`date_filters`, `fields_and_include`, `modes`, `dipstick`. Full
inventory and per-capability tier plan in `docs/prompt-sets/SURFACE.md`
§10.

### Other files in the tree

- `prompts/refusals/refusal_examples.txt` — renamed from
  `10_refusal_examples.txt` and moved out of archive. It is a live
  contract file: `tests/test_nl_parser_capability.py` asserts a
  bijection between it and the guidance tables in `capability.py`.
- `prompts/sme/testcases.txt` — external, verbatim, no tier.
- `prompts/scorer/` — different format (`EXPECT ||| prompt`).
  Not for `promptkit --run`.
- `prompts/retest/prompts.txt` — disposition pending.
- `prompts/archive/` — the pre-2026-09-24 sets `00`–`19`, the old
  README, `mini.txt`. Forensic reference. Do not run.

---

## What's verified this session

- `tests/test_nl_parser_capability.py` — **101 passed, 1 deselected.**
  Three tests were red when the file lived under `scripts/prompts/`
  and the test still pointed there; the rename and the test's path
  update restored them.
- `prompts/dipstick/smoke.txt` — **6/6 clean.** All six depths
  exercised end-to-end against the pod. The full run capture is not
  committed (grep pattern `t_*.txt` in `.gitignore`); the six prompts
  are in the set file itself.
- `promptkit.py`'s default `--prompts-dir` resolves to `prompts/`;
  the manifest at `scripts/manifests/promptkit_sets.yaml` lists all 49 sets and
  is picked up correctly.

## What's not done

**Every other prompt set remains unexecuted.** 15 other smoke sets, 16
verify sets, 16 exhaust sets — all built, none run. This is the next
session's work; it is not a defect.

**Phase 3a has not been started.** The prompt-coverage test
(`tests/test_prompt_coverage.py`, Doc A §9.3.1) is still the next
*design* action. The A/B/C decision about which surfaces to assert
against remains open:

- **A** — entity + filter checks only; record the field-coverage gap.
- **B** — add the field check against the full prompt (tautological).
- **C** — assert against `_ASSEMBLED_PREAMBLE` literally; fails today.

Window 19 chose A as the honest floor; the decision was not
formalized.

---

## Next action

**Run the prompt sets.** The entry point is the manifest:

    python scripts/promptkit.py --run --manifest scripts/manifests/promptkit_sets.yaml

It runs all 49 sets in tier order — smoke, verify, corpus, exhaust.
Comment out the exhaust block for a faster pass. Or run one set:

    python scripts/promptkit.py --run --prompt-file prompts/supplier/smoke.txt

**Read the answers, not the tally.** A screen of "ran cleanly" once
meant several prompts were being wrongly refused. Score each answer
into pass / fail / wrong-but-no-error, and check specifically for:
empty data behind confident prose, a page count stated as a total, a
computation over a truncated sample stated as fact, customer-scoped
results that never resolve an AccountNumber.

Any failure becomes a new F-NNN by the standard S0–S8 discipline.

---

## Standing rules for the prompt-set work

- **The unit is the set.** A bug's V1 reproducer lands in the
  capability it belongs to; it does not create its own file. The
  `exhaust` tier is where reproducers live by default — they test an
  edge that has already bitten.
- **Do not add a single prompt as its own file.** Extend the
  capability's file at the tier the prompt's depth warrants.
- **Do not run a set without capturing to a file first.** Rule 15.1.
- **Do not edit `prompts/archive/`.** Content preserved verbatim; it
  is a forensic record.
- **`SURFACE.md` is the source of truth for what exists.** If a new
  capability is added to the code but not to SURFACE.md, the mapping
  is out of date before the prompt is written.

---

## Working-style reminders that keep biting

- **One command at a time.** Wait for output. Then next.
- **Complete files, never fragments.** Whole file, one block.
- **`~~~` for any outer fence whose content contains ` ``` `.** Rule 4.
- **Every file edit is two cells (rule 15.3).** Cell 1: a program that
  reads the file, checks, replaces, writes. Cell 2: shell commands
  that read the file back from disk. Do not blend them.
- **Long heredocs and `python - <<'EOF'` blocks are the way to land
  multi-line edits.** Do not paste multi-line Python at the shell
  prompt.
- **Name a slow command's cost (rule 15.2).** Exhaust sets page full
  collections.
- **Ledger reconciliation on open (rule 16).**

      gh pr list --state merged --limit 20 --json number,title,mergedAt \
        --jq '.[] | "\(.number)\t\(.mergedAt)\t\(.title)"'
      grep -nE '^\| F-0[0-9]+ .*\| fixed \| — \|' docs/fixes/FIX_PLAN.md

  Last merged PR is **#170**. Both should come back clean.
- **`git stash` does not stash a committed change.** V7 against a
  committed fix uses `git checkout HEAD~1 -- <path>` /
  `git checkout HEAD -- <path>`.
- **`t_*.txt` captures are gitignored.** Every prompt run writes one.

---

## Commits on `hardening-master`, window 19 (newest first)

    369cc63  gitignore: t_*.txt (run-capture artifacts)
    374afd3  prompt-sets: move out of scripts/, tiered reorg, all paths updated
    aacf9b2  prompt-sets: SURFACE.md — capability surface, tier plan, legacy cross-walk

### Window 18, for reference

    4b3737c  Reg #30: evidence capture for the closure
    97bed63  Reg #30: closed as not-a-bug; residual latency deferred to Phase 6
    2573e3c  endpoints ref: /purchaseOrders scan-order facts from F-045
    6d5f76a  F-045: verified | #170
    f77a093  Phase 2 — Fix F-045: created_since beats created_before;
             date fetch gets an orderBy (#170)
    ea4022c  handoff: remove the deprecated sibling; clean up its references

---

## Known doc-drift, recorded not fixed

- **`docs/audit/findings-log.md`** and **`docs/fixes/evidence/F-0*.md`**
  still quote `scripts/prompts/...` paths. These are append-only
  forensic records; editing them would rewrite history. Read them with
  the knowledge that the paths have moved.
- **Doc A §9.3.1** cites `_ASSEMBLED_PREAMBLE` for Phase 3a. That name
  still exists in `context_assembly.py`, but is the wrong surface for
  the field-coverage check. Recorded in the open decision above.
- **`source-tree.txt`** at repo root is stale and gitignored.
  Reconciliation is a follow-up, not scheduled.
- **Doc B's `Phase_02_Correctness.md`** carries S003 and S004 only.
  Window 19 had no Doc B session entry; the reorg's record is this
  handoff plus the commit messages.

---



---

## SPIRE log analysis — where to read current progress

Pointers only. Stable across windows. On-disk files are the source of truth.

- Round index:        `docs/audit/log_analysis_sessions/20260925_150333_smoke.md`
- Per-set index:      `docs/audit/log_analysis_sessions/20260925_150333_smoke/_index.md`
- Per-set files:      `docs/audit/log_analysis_sessions/20260925_150333_smoke/<set>.md`
- Candidates:         `docs/audit/log_analysis_sessions/20260925_150333_smoke/_candidates.md`
- Action items:       `docs/audit/log_analysis_sessions/20260925_150333_smoke/_action_items.md`
- Analysis plan:      `docs/audit/SPIRE_log_analysis_plan.md`
- Raw run logs:       `overnights/20260925_150333/<set>/smoke.log`

Resume protocol: read `_index.md`, find the first set still `pending`,
extract that set, write `<set>.md`, update `_index.md`, continue.



## SPIRE log analysis — current status and next

<!-- BEGIN SPIRE-LOG-ANALYSIS-STATUS -->

- Round:               20260925_150333 smoke
- Tier:                smoke
- Run root:            overnights/20260925_150333/
- Total sets:          16
- Total prompts:       71
- Sets classified:     16 of 16   (complete)
- Prompts classified:  71 of 71   (complete)
- Step 5:              complete
- Step 6:              complete  (see _step6_regression.md)
- Step 7:              pending   (consolidated candidate view)
- Step 8:              pending   (review gate)
- Known mechanisms:    F-052 (confirmed at signature level)
                       HDFE finite (signature undefined, TODO)
- Rules in force:      read-only, append-only, on-disk is source of truth

### Candidates recorded

- C-001  payables/smoke  "invoices in the last 30 days"
         wrong-but-no-error. Open-ended date filter admits future rows.
         Isolated to this one prompt; not a class in this batch.
- C-002  batch-level     exit code appears tied to the final prompt's
         state, not to whether the set contained a refusal. Observation.
- C-003  procurement_supplier/smoke  "suppliers with open purchase orders"
         wrong-but-no-error. Partial F-010 regression: plan step 2 does
         not set filter_source_when_nonempty, so suppliers with 0 open POs
         appear. Same shape passes in payables_supplier.
- C-004  columns/smoke   "List active suppliers with supplier name,
         supplier number, and address"
         fail. Parser produced no target_entity; refused unparseable.

### Step 6 summary

| F-NNN | reproduced | verdict |
|---|---|---|
| F-001 | no direct reproducer | cannot confirm |
| F-007 | yes (all pass)     | no regression |
| F-008 | no reproducer       | cannot confirm |
| F-010 | yes                | PASS in payables_supplier, FAIL in procurement_supplier (C-003) |
| F-012 | yes                | no regression |
| F-015 | no reproducer       | cannot confirm |

### Next window — pick up here

Read order for the next window:

1. This file (HANDOFF.md). Section A pointers, then this Section B.
2. `docs/plan/WORKING_STYLE.md` — "Log analysis" section, LA-1..LA-14.
3. `docs/audit/log_analysis_sessions/20260925_150333_smoke/_index.md`.
4. `docs/audit/log_analysis_sessions/20260925_150333_smoke/_candidates.md`.
5. `docs/audit/log_analysis_sessions/20260925_150333_smoke/_action_items.md`.
6. `docs/audit/log_analysis_sessions/20260925_150333_smoke/_step6_regression.md`.

Steps:

1. Optional Step 7: consolidated candidate view. `_candidates.md`
   already holds all four candidates. Step 7 is a read-through, not new
   analysis. Produce a single consolidated view if useful.
2. Step 8: review gate. For each of C-001 through C-004, decide:
   - log as a new F-NNN
   - link to an existing open finding (C-003 -> F-010)
   - close-as-not-a-bug
   Then set priority relative to F-052. Then stop and ask.
3. Do not propose fixes at the gate.

### Do not

- Fix code.
- Write to `docs/audit/findings-log.md`.
- Read `overnights/03_verify_sets/`.

### After Step 8

The smoke analysis window closes. Any fixes go into a fresh window with
explicit approval, on a branch, per WORKING_STYLE rules 7-11.
<!-- END SPIRE-LOG-ANALYSIS-STATUS -->


*End of handover.*
