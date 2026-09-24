# SPIRE — audit and fix

**Purpose.** How to work a bug in this repository. Not how the
repository is organized — how the audit-and-fix activity is. When a
session opens with a finding to work, this is the reference.

## What we are doing

Auditing the whole source tree against two source-of-truth documents
and fixing every confirmed bug. Read the record, reproduce the bug,
walk the discipline, fix or close, track.

## Where things live

**Inputs — everything starts here.**

| Doc | Path |
|---|---|
| Audit | `docs/audit/phase-1-audit.md` — §A drift · §B bugs · §C dead code · §D inconsistencies · §E in-flight · §F baseline · §G goldens · §H probabilistic |
| Findings log | `docs/audit/findings-log.md` — one `## F-NNN` entry per harm, append-only, newest at top |

Every audit row in §B maps to exactly one F-NNN (§B.6 reverse index).
Every F-NNN cites the audit row(s) it derives from.

**State — where the work is right now.**

| Doc | Path |
|---|---|
| Fix queue | `docs/phase-2/FIX_PLAN.md` — one row per F-NNN with status |
| Session state | `docs/SPIRE_SESSION_HANDOFF.md` — where the previous session stopped |

**Rules — read once, don't re-read every session.**

| Doc | Path |
|---|---|
| The plan | `docs/spire-robustness/SPIRE_ROBUSTNESS_EXTENSIBILITY_v3.2.md` — Phase 2 rules: §8.3.1 severity, §8.3.2 deterministic vs probabilistic, §8.3.5 no scope creep |
| Working style | `docs/spire-robustness/WORKING_STYLE.md` — the S0–S8 discipline, reply rules |
| Startup checklist | `docs/spire-robustness/SESSION_STARTUP_CHECKLIST.md` — open and close |

## What to work on

Open `docs/phase-2/FIX_PLAN.md`. Take the highest-severity row with
`status = not-started`. Sort by §8.3.1: **wrong-data > crash >
missing-capability > cosmetic**. Tiebreak F-NNN ascending.

If FIX_PLAN has no `not-started` rows, open the findings log and find
the topmost entry whose `**Status:**` is `root-caused` or `confirmed`.
That is the next row to add to FIX_PLAN.

## How to reproduce a finding

Every F-NNN entry has an `**Evidence.**` block. It contains the exact
command and its pasted output at the time the finding was written.

Run the same command. One command, paste the output.

- Output **matches the finding's "actual"** → likely still a bug.
- Output **does not match** → the code or pod state has changed.
  Investigate which, then classify.

## How to classify — S0–S8

From `WORKING_STYLE.md` §Evidence standard. Nine steps, in order.

- **S1 is the gate.** No harm, no F-NNN. If the observed behaviour
  has no harm, close as observation; do not carry it forward as a bug.
- **S3 requires a `file:line`.** A finding without a cited mechanism
  isn't a finding yet — it's a hypothesis.
- **S5 requires a falsifier.** If nothing could prove the claim wrong,
  it isn't falsifiable. Don't write it up.

One of four outcomes:

| Outcome | Action |
|---|---|
| **Confirmed** | Bug exists. Proceed to fix. |
| **Closed-as-not-a-bug** | Bug doesn't reproduce. Two shapes (S6-notes): *nondeterminism cleared at N≥20* or *audit-time observation diverged*. Update status in log; update FIX_PLAN. Done. |
| **Observation** | S1 failed. Attach as a note under a related finding. Not a fix. |
| **Candidate** | Some S-steps failed. Note which. Leave open. |

## How to fix a confirmed bug

Per the plan's §8.3.

- **Severity bucket.** Wrong-data > crash > missing-capability > cosmetic.
- **Deterministic or probabilistic.** Deterministic = fires every time;
  one-run test. Probabilistic = N≥20 runs, distribution asserted, marked
  `@pytest.mark.slow`.
- **Branch.** `phase-2-fix-F{NNN}-{short-name}`. One bug, one branch.
- **Regression test.** Asserts the correct behaviour, not just the
  absence of the bug.
- **Byte-diff.** Note which of the three golden prompts might change.

Apply. One bug, one commit. Named `git add`, not `-A`. Heredoc message.

## How to verify

1. Regression test passes.
2. The same test fails without the fix (revert, confirm failure, re-apply).
3. Golden prompts unchanged — or, if changed, the change is explained
   and the golden updated.

## How to track

Four places must move in lockstep. Broken lockstep = drift.

| Place | Change |
|---|---|
| `FIX_PLAN.md` row | status → `fixed` when the regression test is proven real; status → `verified` when the PR merges. The two flips are separate moments, not one decision. |
| `findings-log.md` | append a new dated `**Update YYYY-MM-DD**` block inside the entry, recording the verification. Never edit the original. |
| `phase-1-audit.md` | if the fix closes a §B/§D/§H row, close it in place with the F-NNN citation |
| `docs/SPIRE_SESSION_HANDOFF.md` | add the fix to "first steps in the new window" for the next session |

Once the branch merges: FIX_PLAN status → `closed`.

## Recovery — you have lost all context

Read these three, in this order. You are back in the loop.

1. `docs/phase-2/FIX_PLAN.md` — the queue.
2. `docs/audit/findings-log.md` — topmost open entry.
3. `docs/audit/phase-1-audit.md` §B.6 — the map.

Then run the top FIX_PLAN row's reproducer.

## Invariants — broken = drifting

1. Every `F-NNN` entry has a `FIX_PLAN.md` row.
2. Every F-NNN status line matches its `FIX_PLAN.md` row.
3. Every confirmed finding cites a `file:line` mechanism (S3).
4. Newest entry in the findings log is at the top.
5. No fix lands without a regression test that fails without it.
6. No golden prompt changes without a documented reason.
7. Every audit row in §B has an F-NNN, or is `pending` with a named
   follow-up.

## The one rule

**Reproduce before you plan.** A finding whose reproducer no longer
fires is `closed-as-not-a-bug`; a finding whose reproducer still fires
is the next fix. Guessing which costs more than running the command.