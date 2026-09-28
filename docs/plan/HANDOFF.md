# SPIRE — Session Handoff, 2026-09-28 (window 23)

**This file supersedes the window-22 handoff.** Window 23 was a fix
window: F-053 and F-055, both from the smoke-round log analysis, are
fixed and merged. Phase 3a is still not started.

**Read this first.** Then `docs/fixes/FIXES.md` (the playbook), then
`docs/fixes/FIX_PLAN.md` — §5 is the closed Phase 2 ledger; §5.1 is
the live Phase 3 ledger. The `plan` context bundle carries this file
plus everything referenced below.

---

## Where we are

**Branch:** `hardening-master` at `dc61e42`.

**Test suite:** 1243 passed, 1 skipped, 22 deselected (4m00s), measured
2026-09-28 after F-055 merged.

**Pod:** dev instance (MCP 4001 / API 4002 / UI 4003).

**Ledger:**
- FIX_PLAN §5 (Phase 2) — closed 24/24, unchanged.
- FIX_PLAN §5.1 (Phase 3) — F-052 closed-as-not-a-bug, F-053
  verified (#174), F-054 closed-as-not-a-bug, F-055 verified (#175).

---

## What shipped in window 23

**F-053** (#174, `e948b3d`) — `has_open_PO` missing from
`_FILTER_SOURCE_NONEMPTY_SUFFIX`; `suppliers with open purchase orders`
listed suppliers with zero open POs. Three-file fix: the registry
entry; a computed-args branch in `plan_builders.py` sending
`status='OPEN'`; and a Block 3 re-fetch step in `planner.py` so the
anchor prompt's `Buyer` include still chains. Golden
`suppliers_with_open_pos.txt` updated — the golden captured the bug.

**F-055** (#175, `dc61e42`) — `invoices in the last 7 days` refused
every run because the model converted days to fractional months
(`{'months': 0.23}`). The sysprompt (`b_invoice_date.sysprompt`) and
its byte-equality mirror (`context_assembly.py`) teach a rounding-up
conversion. N=20 sweep: 20/20 `{'months': 1}`, 0 refusals.

**Process doc updates:**
- `WORKING_STYLE.md` rules 2.1 / 2.2 — "one command at a time" splits
  on uncertainty, not on count; obvious commands run together.
- `FIX_PLAN.md` §8 / §11.1 / §12 — V0 written and committed first
  (before any source file); test-first with a failing commit; V7 uses
  `git checkout HEAD~1` not `git stash`; §12 gains two session-start
  boxes.

---

## What's not done

- **Phase 3a — the prompt-coverage test design.** The A/B/C decision
  from window 19 remains open. Not started.
- **S11 expansions** from F-053 and F-055 — new prompts in
  `supplier/exhaust`, `date_filters/verify`, `date_filters/exhaust`.
  Recorded in each finding's S11 section.
- **A new finding surfaced during F-053's V3.** The anchor prompt
  `List US suppliers with open purchase orders, include the buyer`
  returns `Synthesized response: (none)` — the synthesis output cap
  is hit (`synthesize out≈7985`). Reproduces pre-fix and post-fix;
  not caused by F-053. Not yet filed.

---

## Next action

1. **File the anchor-prompt synthesis overrun** as a new F-NNN. The
   symptom signature (`synthesize out≈7985` → empty answer) matches
   the "Suppliers with their addresses" bug that
   `build_supplier_records` closed. Walk R + S0–S11.
2. **Phase 3a** — the prompt-coverage test design; choose A/B/C, then
   implement.
3. **S11 expansions** — extend each capability's tier files per the
   findings' S11 sections.

---

## Working-style reminders that keep biting

- **Rule 2.1** — obvious commands run together; split only on
  uncertainty.
- **Rule 15.1** — capture complete output to a file first, then grep.
- **Rule 15.2** — name a slow command's cost before handing it over.
- **Rule 15.3** — edits are two cells: Python script, then shell
  verification.
- **Rule 16** — ledger reconciliation on open.
- **V-standard** — V0 first (before any source file), test-first with
  a failing commit, V7 via checkout not stash.

---

## Commits on `hardening-master`, window 23 (newest first)

    dc61e42  Phase 3 — Fix F-055: days-based Invoice windows convert to
             whole months (#175)
    e948b3d  Phase 3 — Fix F-053: has_open_PO keeps only suppliers with
             open POs (#174)
    825ed37  context_bundles: add log_analysis.py, live findings,
             smoke-round entries

The individual branch commits (before the squash merges) are preserved
on the (now-deleted) `Phase3-Fix-F-053` and `Phase3-Fix-F-055` branches
in the reflog only.

---

## Known doc-drift, recorded not fixed

- **`docs/audit/findings-log.md`** and **`docs/fixes/evidence/F-0*.md`**
  quote `scripts/prompts/...` paths. Append-only forensic records;
  editing would rewrite history.
- **Doc A §9.3.1** cites `_ASSEMBLED_PREAMBLE` for Phase 3a. That name
  is the wrong surface for the field-coverage check.
- **`source-tree.txt`** at repo root is stale and gitignored.
- **`docs/phase-2/fixes/`** is where Phase 3 fix files live, despite
  the directory name. The fix-machinery document is FIX_PLAN; the
  finding is Phase 3; the mechanism is Phase 2's.
- **F-053's V3 flagged a behaviour change** — the answer is now a
  plain supplier list without per-supplier counts, matching F-010's
  sibling. Deliberate, recorded in the fix file.

---

## SPIRE log analysis — where to read current progress

Pointers only. Stable across windows. On-disk files are the source of
truth.

- Round index:        `docs/audit/log_analysis_sessions/20260925_150333_smoke.md`
- Per-set index:      `docs/audit/log_analysis_sessions/20260925_150333_smoke/_index.md`
- Per-set files:      `docs/audit/log_analysis_sessions/20260925_150333_smoke/<set>.md`
- Candidates:         `docs/audit/log_analysis_sessions/20260925_150333_smoke/_candidates.md`
- Action items:       `docs/audit/log_analysis_sessions/20260925_150333_smoke/_action_items.md`
- Analysis plan:      `docs/audit/SPIRE_log_analysis_plan.md`
- Raw run logs:       `overnights/20260925_150333/<set>/smoke.log`

Resume protocol: read `_index.md`, find the first set still `pending`,
extract that set, write `<set>.md`, update `_index.md`, continue.

---

## SPIRE log analysis — current status and next

<!-- BEGIN SPIRE-LOG-ANALYSIS-STATUS -->

- Round:               20260925_150333 smoke
- Tier:                smoke
- Total sets:          16
- Total prompts:       71
- Gate:                closed 2026-09-27

### Gate results

| candidate | disposition | finding |
|---|---|---|
| C-001 | closed-as-not-a-bug (latent) | F-054 |
| C-002 | observation, no F-NNN | - |
| C-003 | confirmed | F-053 |
| C-004 | closed-as-not-a-bug | F-052 |
| C-005 | confirmed | F-055 |

### Findings

- **F-052** — closed-as-not-a-bug. Columns list + non-column field
  (`and address`). R: N=20 clean.
- **F-053** — fixed, verified (#174). `has_open_PO` missing from
  `_FILTER_SOURCE_NONEMPTY_SUFFIX`. Three-file fix.
- **F-054** — closed-as-not-a-bug (latent). `invoices in the last 30
  days` compiles to a one-sided date filter.
- **F-055** — fixed, verified (#175). `last 7 days` refused on
  fractional-months conversion. Sysprompt + mirror; N=20 sweep 20/20.

### Where things live

- Findings: `docs/audit/findings/F-052.md` .. `F-055.md`
- Fix files: `docs/phase-2/fixes/F-053.md`, `F-055.md`
- Run analysis: `docs/audit/log_analysis_sessions/20260925_150333_smoke/`
- Plan: `docs/audit/SPIRE_log_analysis_plan.md`
- Archive (frozen): `docs/audit/archive/phase-1/`
- Smoke PR: #172
- Generalization PR: #173 (merged 2026-09-28)

### Next window

1. **New finding** — the anchor-prompt synthesis overrun. See "Next
   action" above.
2. **Phase 3a** — prompt-coverage test design.
3. **S11 expansions** from F-053 and F-055.

<!-- END SPIRE-LOG-ANALYSIS-STATUS -->

---

*End of handover.*
