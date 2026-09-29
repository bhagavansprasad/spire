# SPIRE — Session Handoff, 2026-09-28 (window 25)

**This file supersedes the window-22 handoff.** Window 23 was a fix
window: F-053 and F-055, both from the smoke-round log analysis, are
fixed and merged. Phase 3a is still not started.

**Read this first.** Then `docs/fixes/FIXES.md` (the playbook), then
`docs/fixes/FIX_PLAN.md` — §5 is the closed Phase 2 ledger; §5.1 is
the live Phase 3 ledger. The `plan` context bundle carries this file
plus everything referenced below.

---

## Where we are

**Branch:** `hardening-master` at `3633c1e`.

**Test suite:** 1266 passed, 1 skipped, 22 deselected (3m32s), measured
2026-09-28 after F-056 and the S11 expansions merged.

**Pod:** dev instance (MCP 4001 / API 4002 / UI 4003).

**Ledger:**
- FIX_PLAN §5 (Phase 2) — closed 24/24, unchanged.
- FIX_PLAN §5.1 (Phase 3) — F-052 closed-as-not-a-bug, F-053
  verified (#174), F-054 closed-as-not-a-bug, F-055 verified (#175),
  F-056 verified (#177).

---

## What shipped in window 25

**F-056** (#177, `0cf45ec`) — the anchor prompt
`List US suppliers with open purchase orders, include the buyer`
returned `Synthesized response: (none)` because the F-053 four-bucket
plan shape had no local synthesizer builder; the LLM was asked to
transcribe 183 records and hit its output-token cap (`out=7985`, two
windows running). Fix: `_supplier_pos_buyers` detector and
`build_suppliers_with_open_pos_and_buyers` builder in
`synthesizer/p2p.py`, routed by a branch in `synthesize_response`. No
LLM call on the path. 23 new tests. A pre-existing fixture collision in
`tests/test_synthesizer.py` was also closed (rename of one bucket to
break a `{source}_{suffix}` prefix that accidentally matched the new
detector).

**S11 expansions** (#178, `3633c1e`) — 18 sibling prompts added across
six files, exercising the F-053 (presence-edge filter) and F-055
(day-count conversion) classes. No code changes.

**Doc-drift sweep** (this window, PR pending) — §9.7 of the plan gains
a Status note flagging §9.3.1's stale `_ASSEMBLED_PREAMBLE` reference.
`source-tree.txt` deleted locally (gitignored, nothing to commit). The
three other items on the previous window's doc-drift list dispositioned
as no-action (see "Known doc-drift" below).

---

## What's not done

- **Phase 3a — the prompt-coverage test design.** The A/B/C decision
  from window 19 remains open. The stale §9.3.1 reference is now
  Status-noted (see §9.7). Not started.
- **The display fallback for `synth_failed`.** F-056's fix closed the
  anchor-prompt overrun with a local builder; the display path that
  shows the raw `Synthesized response: (none)` marker for
  `fields`-less intents was deferred as scaffolding for a case not
  observed. Recorded in the F-056 fix file's Deviations section.
- **A country-path total.** V1 of F-056 showed
  `Examined 25 of an unknown number of suppliers`. The suppliers tool
  honestly reports no total on the country-filtered path (client-side
  filter caps the over-fetch; the pod-side `q=` carries only the
  server clause). Not a defect, but a follow-up if the wording ever
  matters — a second probe the current single-clause pattern does not
  make.

---

## Next action

1. **Phase 3a** — the prompt-coverage test design. Choose A/B/C (see
   §9.7's Design note for what the three options are), then implement
   the test. This is the only Phase 3 sub-phase still open.
2. **Sweep the F-056 four-bucket shape across the prompt sets.** Only
   the anchor prompt was tested for the shape. Any prompt combining a
   `filter_source_when_nonempty` step, a downstream include whose edge
   requires a refetch, and a parent-of-the-filter root would produce
   the same shape. A sweep would surface the class before the next
   bug report.

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

## Commits on `hardening-master`, window 25 (newest first)

    3633c1e  S11 expansions: presence-edge filters (F-053) and
             day-count conversion (F-055) (#178)
    0cf45ec  F-056: local builder for the F-053 four-bucket synthesizer
             shape (#177)
    01da2ae  fix file: F-056 V0 (four-bucket local builder) — committed
             on `hardening-master` before branching
    55bb66d  audit: F-056 — anchor prompt overruns synthesize on the
             F-053 four-bucket shape
    b4c9d8c  handoff: branch SHA ec2fe14; add three newer commits
    ec2fe14  context_bundles: sync with source tree — fix files,
             log-analysis session, F-053/F-055 tests

The individual branch commits (before the squash merges) are preserved
on the (now-deleted) `Phase3-Fix-F-056` and `Phase3-S11-expansions`
branches in the reflog only.

---

## Known doc-drift, recorded not fixed

Window 25 dispositioned all five items from the previous list.

- **`docs/audit/findings-log.md`** and **`docs/fixes/evidence/F-0*.md`**
  quote `scripts/prompts/...` paths. **No action** — append-only
  forensic records; editing would rewrite history. `ls prompts/` shows
  the current paths.
- **Doc A §9.3.1** cites `_ASSEMBLED_PREAMBLE` for Phase 3a. **Fixed
  as a Status note in §9.7** rather than a Design-section edit, per
  the plan's "never edit a Design section" rule.
- **`source-tree.txt`** at repo root was stale and gitignored.
  **Deleted locally** (nothing to commit; gitignored).
- **`docs/phase-2/fixes/`** is where Phase 3 fix files live, despite
  the directory name. **No action** — the directory name is a label,
  not a contract; which phase a fix belongs to is read from the fix
  file's header. Renaming would move 30+ Phase 2 files.
- **F-053's V3 flagged a behaviour change.** **Already recorded** in
  the F-053 fix file and the finding's V5. No further action.

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
