# SPIRE — Session Handover

**Written:** 2026-09-24
**Phase:** Phase 3a — Consistency (opens next window)
**Branch:** `hardening-master`
**Mode:** Phase 2 closed at 24/24. Phase 3a begins the consistency phase.

---

## Read these first, in this order

1. `docs/spire-robustness/SPIRE_ROBUSTNESS_EXTENSIBILITY_v3.2.md` §6 (Phase
   Index) and §9.3.1 (Phase 3a design). This is the resume reference.
2. `docs/spire-robustness/WORKING_STYLE.md` — the S0–S8 evidence
   discipline, rules 15.1 / 15.2 (full-output capture; name the cost of
   a slow command), rule 16 (open every window with a ledger
   reconciliation).
3. `docs/AUDIT_AND_FIX.md` — the playbook.
4. `docs/phase-2/FIX_PLAN.md` §5 (the ledger — now closed at 24/24) and
   §4.1 (Reg #30 closure). Not the source of any pending work, but the
   record of what Phase 2 did and why.

---

## Current state

**Repo**
- Branch `hardening-master`, HEAD `8012b1b` (Doc B index snapshot
  refresh; the handover you are reading is the next commit). Clean tree.
- Integration branch: `hardening-master`. `master` frozen at `14dce82`.
- Phase branches spawn off `hardening-master` and merge back via PR.
  Nothing merges to `master` without explicit instruction.
- Test count: **1229 passed / 1 skipped / 22 deselected** (measured
  2026-09-24, post-F-045).

**Runtime**
- Dev tree:  `~/pocs/spire`, MCP 4001 / API 4002 / UI 4003.
- Runtime:   `~/pocs/spire-runtime`, MCP 3333 / API 8000 / UI 8888,
  ngrok-exposed. Do not disturb without a deliberate plan.
- Ports come from `SPIRE-PORTS.env` and `spire.sh --dev | --runtime`.

---

## Phase 2 — closed 24/24

Every row on the FIX_PLAN §5 ledger is `verified`, `closed`, or
`closed-as-not-a-bug`. No `not-started` rows remain. The last two
closed this session (window 18):

| Row | Closure | PR | Date |
|---|---|---|---|
| F-045 | composite `created_since AND created_before` returned 0 with a misleading capped note — fixed with a priority reorder plus an `orderBy` on the creation-date fetch. | #170 | 2026-09-24 |
| Reg #30 | compare-path perf — **closed as not-a-bug.** The entry's specific claim (top-N compare fetches the entire PO universe → pod timeout at 145.7s) does not reproduce. The residual 5m19s latency is real, is arithmetic (~104 sequential HTTP calls), and is deferred to Phase 6 by §4 row 9's own arrangement. | — | 2026-09-24 |

Also shipped this window: 4 tracking-flip commits (F-045 fixed →
verified, audit §B.6 flips), and three endpoint-reference additions to
`docs/spire_fusion_endpoints_reference.md` recording the pod's
purchase-order scan-order behaviour discovered during the F-045 probe.

**Two new pod facts now in the endpoints reference** — worth knowing
before touching any date-bounded fetch on `/purchaseOrders`:

1. Composite `q=` on `/purchaseOrders` returns HTTP 400, not
   silent-zero. Different family member from F-012's `/invoices`
   falsifier.
2. The default physical scan order is **not stable across query
   shapes**. Adding `fields=` or `orderBy=` shifts where the 200-row
   window starts. `orderBy=CreationDate:asc` composes with `q=` and is
   the stable sort key for a date-bounded fetch on that field.
   `LastUpdateDate >=` does NOT need it — the default scan for that
   field already starts at the range's lower edge. Sort-key stability
   is field-specific; verify per field.

---

## Next action

**Phase 3a — Prompt coverage validation.** Doc A §9.3.1:

> **Objective.** Add a test that fails when the KG declares an entity,
> filter, or field that the parser prompt does not cover.

> **Design.** New test reads `kg_entity` (and `kg_entity_filter`,
> `kg_entity_field`) via `load_kg_menu()`, then asserts every entity
> name appears in `_ASSEMBLED_PREAMBLE`; then similar for filters and
> fields.

Acceptance: the test passes today. If it fails, the gap is real — fix
the prompt before proceeding.

**Before writing any test**, read Doc A §9.3.1 in full. It gives the
shape. The `_ASSEMBLED_PREAMBLE` variable name may not match what the
code exposes today (Phase 2 changed `context_assembly.py` several
times); find the equivalent surface first, then write the test.

Do not open Phase 3b (prompt generation) until 3a passes. The whole
point of 3a is to establish that the current prompt covers what the KG
declares; 3b's generator is only meaningful against that baseline.

---

## The one rule

**Reproduce before you plan.** A finding whose reproducer no longer
fires is `closed-as-not-a-bug`; a finding whose reproducer still fires
is the next fix. Guessing which costs more than running the command.

This session's instance: the F-045 entry proposed two fix shapes, and
the pod probe revealed the mechanism was neither. Had the fix been
written from the entry's description, it would have been wrong — and
would have looked right until a range below the pod's physical scan
window was asked for.

---

## Known doc-drift, recorded not fixed

- `docs/spire-robustness/SESSION_HANDOVER.md` — this file. Rewritten
  2026-09-24 for window 19; prior version framed for Phase 2 with
  F-045 and Reg #30 open.
- The session-start instruction in some windows names
  `docs/SPIRE_SESSION_HANDOFF.md`. The entry point is
  `docs/spire-robustness/SESSION_HANDOVER.md`. Both files exist;
  `SPIRE_SESSION_HANDOFF.md` is a different, older document that reads
  as stale. Reconciliation is a follow-up, not a blocker.
- Doc B's `02_Phase_02_Correctness.md` has entries for S003 and S004.
  Windows 17 and 18 ran without Doc B session entries — consistent
  with the deliberate gap noted in that file's header. The forensic
  record for window 18 lives in FIX_PLAN §4.1, §5, and the fix files
  under `docs/phase-2/fixes/` (F-045.md, Reg-30-v1-repro.txt). Whether
  to back-fill an S005 is a decision for the next window; the current
  convention is not to.
- Doc A §6 Phase Index was not updated this session. Phase 2 has been
  Complete since window 16's close; the index row already reflects
  that. Phase 3a's row (`not-started`) is correct as-is — it becomes
  `in-progress` when window 19 opens it.

---

## Working-style reminders that have bitten us

- **One command at a time.** Wait for output. Then next.
- **Complete files, never fragments.** Whole file, one block.
- **`~~~` for any outer fence whose content contains ` ``` `.** Rule 4.
- **Full-output capture (rule 15.1).** Redirect long runs to a file,
  then grep from the file. Never pipe the run itself through a filter.
- **Name a slow command's cost (rule 15.2)** before handing it over.
  The Reg #30 reproducer was 5m19s — named before running.
- **Every file edit is two cells (rule 15.3).** Cell 1 is a Python
  script that reads the file, checks the anchor, replaces, writes,
  exits. Cell 2 is shell verification commands that read the file
  back from disk. The two do not blend.
- **Ledger reconciliation on open (rule 16).**
      gh pr list --state merged --limit 20 --json number,title,mergedAt \
        --jq '.[] | "\(.number)\t\(.mergedAt)\t\(.title)"'
      grep -nE '^\| F-0[0-9]+ .*\| fixed \| — \|' docs/phase-2/FIX_PLAN.md
  Both should come back clean. Last merged PR is #170.
- **The audit is the report; the findings log is the notebook.**
  Audit rows close in place. Findings-log corrections are new dated
  update blocks appended inside the entry — never edits to the
  original text.
- **`git stash` does not stash committed changes.** V7 for a committed
  fix needs `git checkout HEAD~1 -- <path>` and `git checkout HEAD --
  <path>`. Recorded because window 18 got this wrong once.

---

*End of handover.*
