# SPIRE — Findings

**Purpose.** One file per finding. This is the live bug record for the
current phase. Phase-1 findings (F-001..F-051) are frozen under
`docs/audit/archive/phase-1/findings/` and are not edited here.

**Finding ID:** `F-NNN`, monotonic. Never reused. Never renumbered.
Numbering continues from the archived corpus. Next free ID when this
folder was created: **F-052**.

**One file per finding.** `findings/F-NNN.md`. Never append a second
finding to an existing file.

**Every entry walks S0–S11** (see `docs/plan/WORKING_STYLE.md`).
The walk is the entry. Do not write an F-NNN without it.

**Status vocabulary** (from `FIX_PLAN.md` §5):
`open` · `root-caused` · `fix-in-progress` · `fixed` · `verified` ·
`closed` · `closed-as-reclassified` · `closed-as-duplicate` ·
`closed-as-not-a-bug`.

**Two-way link to runs.** Each finding's `Seen in runs` table lists
every run that has touched it, with the prompt. Each run's
`_touched.md` lists every F-NNN that run contributed to. The F-ID is
the only durable identifier; run IDs are labels.

---

## Template

~~~markdown
## F-NNN — {one-line title}

**Date:** YYYY-MM-DD
**Status:** open
**Cross-refs:** audit rows, prior F-NNNs, run IDs

### S0 — Claim
One sentence: "X is a bug" or "X is not a bug."

### S1 — Harm
Exactly one of: wrong data returned · wrong narration · crash ·
refusal of an in-scope prompt · silent omission · cost regression ·
inconsistency between two paths.

### S2 — Evidence
Verbatim. Tier 1 curl, tier 2 runtime output, tier 3 file:line.
Paste, do not paraphrase. Tier 4 ("I recall") is not evidence.

### S3 — Mechanism
The specific file:line or function that produces the harm.

### S4 — Probable root cause
Why the mechanism is written that way. One of: a design decision that
is wrong · a plan-template selection gap · a parser grammar gap · a
missing guard or default · a stale assumption about pod data.
If unknown, state "mechanism known, root cause unknown".

### S5 — Alternative disproven
One alternative explanation, and the evidence that rules it out.

### S6 — Falsifier
One command that would prove this is not a bug.

### S7 — Classification
Confirmed (S1–S6 all passed) · Candidate (note which failed) ·
Observation (S1 failed) · Closed-as-not-a-bug (cite old entry).

### S8 — The miss record
1. Did a prompt of this shape exist? existing / passed-but-wrong / absent.
2. Why did it not surface? The reason, not the category.
3. What would have caught it? The prompt or check that did not exist.

### S9 — Cross-links
At least one §A / §B / §D row or another F-NNN.

### S10 — What was NOT checked
Explicit.

### S11 — Coverage expansion
Sibling prompts that exercise the same shape, existing or to-be-written,
with the tier each belongs to (smoke / verify / exhaust).

### Seen in runs

| run_id | role | prompt | resolution |
|---|---|---|---|
| 20260925_150333 | first observed | <prompt verbatim> | C-00N → F-NNN |

### Fix

**Fix location:** (Phase 2's job; this records where, not what)
**PR:** —
**Commit:** —
~~~

---

*End of findings README.*
