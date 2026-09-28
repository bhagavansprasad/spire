# SPIRE Log Analysis Plan

## Part A - Scope and contract

**Purpose.** This pipeline is a starting assistant, not a
bug-finder. It surfaces the material a developer needs to begin and
continue an investigation - errors, exceptions, refusals,
signatures, exit codes, per-prompt heads - and hands it over. Its
output is not expected to be identical across rounds, even on the
same tier: two smoke rounds with different failures should read
differently, because the logs differ. It is not expected to find
every bug; it is expected to point at where the investigation
should start.

**What this is.** The repeatable pipeline for analyzing one tier's
promptkit run, from raw run output to merged findings. Every new round
follows this document.

**Scope.** One tier, one run_id. Smoke, verify, and exhaust all follow
the same process; only the size and depth of the sets differ.

**Input.** A completed run under `overnights/<run_id>/`. The round
folder carries a frozen `_manifest.yaml` (the manifest that was
run) and one subfolder per set. The live manifest lives at
`scripts/manifests/<tier>_sets.yaml`; the frozen copy is what this
pipeline reads.

**Output.** A set of F-NNN findings written into `docs/audit/findings/`,
plus a closed review gate with a disposition per candidate (promoted,
linked, or closed).

**Audience.** Whoever runs the analysis. This document assumes
`docs/plan/WORKING_STYLE.md` has been read - R and S0-S11 are the
standards every finding must satisfy, and this document does not
restate them. It references them.

**How to read this document.** Part B is the map - the whole pipeline
as a numbered list. Part C is the terrain - each step, what it does,
why it matters, and the command to run. Parts D through G are the
reference material: file templates, the helper script, working-style
reminders, and the worked example from the first full application.

**What this document is not.** It is not the finding template
(`docs/audit/findings/README.md`), not the working style
(`docs/plan/WORKING_STYLE.md`), and not the helper script's source
(`scripts/log_analysis.py`). It points at each of them and explains
when to use them.

**Contract.** This pipeline applies to promptkit runs only.
Promptkit is SPIRE's single trigger: it takes one prompt string,
sends it to SPIRE, captures the output. A run folder is a frozen
`_manifest.yaml` at the round root plus one subfolder per set, each
holding the per-set triad. No other producer writes this shape
today; if one ever does, this section changes with it.

The tier (smoke / verify / exhaust) is a property of the set names
in the frozen manifest, not of the analysis. Every set basename in
one round is the same tier. The tier names the per-set files; it
never reaches SPIRE. Because SPIRE sees only the prompt string, the
signature list (`SIGNATURE_PATTERNS` in `scripts/log_analysis.py`)
is flat - one list, checked in every tier. A tier-specific
signature would be a category error: SPIRE does not know the tier.

Corrections to this document are made in place. There is no
superseding sibling. The smoke round's own artifacts name
`smoke.log` and stay correct under the `<tier>` abstraction;
history is not rewritten by keeping a stale copy alive.

---

## Part B - The pipeline at a glance

One tier, one run_id, fourteen steps. Steps 1-6 are mechanical. Step 7
is a hard stop - the review gate. Steps 8-14 turn candidates into
findings and land them.

| # | step | output |
|---|---|---|
| 1 | Confirm the round exists and derive its tier | structural pass/fail |
| 2 | Read `_summary.log` - exit-code triage | anomaly table |
| 3 | Extract signatures from non-zero sets | signature table |
| 4 | Classify every prompt: pass / fail / wrong-but-no-error | classification table |
| 5 | Cross-check known-fix regression | regression table |
| 6 | Write candidates to `_candidates.md` | candidate list |
| 7 | **Review gate. Stop and ask.** | disposition per candidate |
| 8 | **R - reproduce.** Run the prompt and its sibling. Capture to file. | run capture, decision |
| 9 | **S0-S11 walk** for anything that survives R | completed walk |
| 10 | Write the F-NNN file | `findings/F-NNN.md` |
| 11 | Update `_candidates.md` and `_touched.md` | resolutions recorded |
| 12 | Commit the F-NNN file | one commit per finding |
| 13 | Push branch, open PR to `hardening-master` | PR number |
| 14 | Update `HANDOFF.md` Section B | gate-closed state |

**Steps 1-6: read-only.** No code fixes. No findings-log writes. No
repository changes except under `docs/audit/log_analysis/<run_id>/`.
This is the LA-1 discipline (`WORKING_STYLE.md`, Log analysis).

**Step 7: the gate.** Analysis ends here. Bring the candidate list and
a walk-status per candidate. Decide together: promote to a new F-NNN,
link to an existing one, or close. Do not propose fixes at the gate.

**Steps 8-14: findings.** These are the steps the earlier version of
this document was missing. R is new - it forces a re-run against the
current pod before any candidate is written as a bug. The S0-S11 walk
is `WORKING_STYLE.md`'s standard, applied per candidate. The commit /
PR / handoff steps are how the finding reaches `hardening-master`.

**Why R is step 8 and not step 1.** Reproduction before analysis, not
after. A finding written from a stale log is a hypothesis. In the first
full application of this pipeline (smoke, 2026-09-25 run), R falsified
one candidate's mechanism (F-052), confirmed another in a single run
(F-053), closed a third on latent-shape grounds (F-054), and surfaced
a finding no other step would have caught (F-055).

## Part C - Step-by-step

Each step follows the same shape: **What it does. Why it matters.
Commands. Output. Gate.**

---

### Step 1 - Confirm the round exists and derive its tier

**What it does.** Structural inventory of the run before any answer is
read. Verifies the round folder exists under `overnights/`, that the
top-level files (`_manifest.yaml`, `_run_log.txt`, `_summary.log`) are
present, and that every set folder named in the manifest has its triad
of per-set files.

The tier is derived from the frozen `_manifest.yaml` at the round root:
every set name is `<folder>/<tier>` and all sets in one round share a
single tier. The script reads the manifest, extracts the common
basename, and uses it to name the per-set files — `<tier>.log` (the
raw run log), `<tier>.txt` (the frozen input copy), and
`<folder>_summary.log` (the per-folder summary). No tier name is
hardcoded in the script or in this document; the manifest is the
single source of truth.

**Why it matters.** A missing set or a half-written log means any
classification done on this round is invalid. Catching it here costs
seconds; catching it after classification costs the whole analysis.

**Command.**

```bash
python scripts/log_analysis.py verify-round <run_id>
```

**Output.** A per-file `ok` / `MISSING` table for the top level, then
one row per set showing whether each file in the triad is present.

**Gate.** Every file must read `ok`. A single `MISSING` stops the
analysis - report it and do not proceed. If the round folder itself is
absent, the run did not complete; nothing to analyze.

---

### Step 2 - Exit-code triage

**What it does.** Reads `_summary.log` and lists every set whose exit
code is non-zero. Records set name, exit code, and seconds for each.
Separates exit 1 from other non-zero exits - exit 1 in this codebase
has a specific meaning (see Step 3's exit-code mechanism).

**Why it matters.** Exit codes are objective and cheap. They narrow
the search to sets most likely to contain real failures before any
semantic answer reading begins. Semantic classification is expensive;
do not start there until the mechanical failures are known.

**Command.**

```bash
python scripts/log_analysis.py exit-codes <run_id>
```

**Output.** One row per set with `exit=N` in the summary. Compare
against the manifest's expected set count.

**Gate.** Every non-zero exit must be accounted for by the end of the
round - either by a known mechanism (Step 3) or by a candidate (Step 6).
An exit code with no explanation is a stopping point: re-read
`_run_log.txt` before moving on.

---

### Step 3 - Signature extraction for non-zero sets

**What it does.** For each set with a non-zero exit, greps its
`<tier>.log` for failure signatures. Counts hits per pattern. Compares
the shape to the known mechanisms below.

**Why it matters.** A non-zero exit has a cause. The signature tells
you whether it is a known artifact (which needs no new F-NNN) or a new
shape (which becomes a candidate in Step 6). This is the cheapest way
to sort the failures before reading any answers.

**Command.**

```bash
python scripts/log_analysis.py signatures <run_id> <set>
```

**Output.** A count per signature pattern. Zero counts are not shown.
"No signature matched" is itself meaningful - it means the failure is
silent and needs a different probe.

**Gate.** Every signature must be accounted for before Step 4 begins.
Either it matches a known mechanism, or it enters the candidate list.

---

#### Known mechanism - exit-code-on-final-refusal

**Not a bug.** Documented artifact. Answers are correct; only the exit
code is wrong.

**Signature.**

```text
exit=1 on the set, but no ERROR banner in the log
REFUSED (planner guard): ... OR a parser Reason: line as the final prompt
```

**Mechanism.**

1. `plan_node` catches `RefusalError` and returns `{"refusal": ...}`
   without a plan.
2. The edge after plan is `_continue_or_end`, which ends only when
   `error` is set. A refusal does not short-circuit.
3. `execute_node` runs, does `state["plan"]` on a state with no plan,
   raises `KeyError`, caught by the blanket `except Exception`, writes
   `error`.
4. State now carries BOTH refusal and error.
   `_emit_run_graph_output` checks refusal first, prints the refusal,
   and returns - no `ERROR` banner is ever emitted.
5. `_run_async` counts `error and not plan_refusal` as a failure.
   Exit 1.

**What it means in Step 2.** A set that exits 1 with a refusal as its
final prompt is this mechanism. Do not open an F-NNN for it. If the
refusal is not the final prompt, exit is 0 and the mechanism does not
apply.

**Fix location (not applied):** widen `_continue_or_end` to end on
refusal too, or add a dedicated `_after_plan` edge.

---

#### Known mechanism - HDFE finite

**Status: signature undefined.** TODO.

**What to do when it appears.** Grep the non-zero log for `HDFE` and
`finite`. Record file, line, and surrounding context. Determine
whether it is a plan-time refusal, a runtime error, a silent wrong
answer, or a data-shape issue. Once confirmed, add the signature to
the pattern list in `scripts/log_analysis.py` (see Part E) and write
the mechanism here.

---

#### Adding a new mechanism

When a signature is confirmed to be a documented artifact rather than
a bug, add it here. Two edits:

1. Add the grep pattern to `SIGNATURE_PATTERNS` in
   `scripts/log_analysis.py` so future rounds detect it automatically.
2. Write the mechanism into this section, in the shape of
   exit-code-on-final-refusal: signature, mechanism, what-it-means,
   fix location.

Do not give a mechanism an F-number. Mechanisms are artifacts; F-NNNs
are bugs.

---

### Step 4 - Classify every prompt

**What it does.** Reads every prompt and its answer across every set
in the round - not just the non-zero ones. Classifies each as one of
three values.

**Why it matters.** Exit codes catch mechanical failures. They miss
the silent ones: an answer that reads fine and says something false.
Step 4 is the first pass that reads answers, and it runs over the
whole round. A set that exited 0 can still contain a wrong answer.

**Classification vocabulary.** Exactly three values. Do not invent a
fourth.

```text
pass               right rows, right claims
fail               errored, or refused when it should not have
wrong-but-no-error reads correctly but says something false
```

A fourth word, `regression`, is used only in Step 5 for a previously
fixed finding whose reproducer still fires. It is not a classification
of the prompt; it is a classification of the outcome against a prior fix.

**Command.**

```bash
python scripts/log_analysis.py classify <run_id> <set>
```

This prints, for each prompt in the set, the PROMPT line, the first
Answer line, and any Truncation or Reason line. That is usually enough
to classify. When it is not, read the raw block directly:

```bash
grep -n '^PROMPT: ' overnights/<run_id>/<set>/<tier>.log
sed -n '<start>,<end>p' overnights/<run_id>/<set>/<tier>.log
```

**Watch for - LA-8 failure shapes.** These are the shapes that read
fine but say something false. Every classified prompt is checked
against this list.

- Empty data behind confident prose.
- A page count stated as a total.
- A computation over a truncated sample stated as fact.
- Customer-scoped results that never resolve an `AccountNumber`.
- A generalisation true of the first few rows but not the set.
- A list-shaped answer with no `Showing N of M` and no `Truncation:` line.
- A count computed over the sample rather than over the full set.
- Two prompts of the same shape that plan differently.

**Output.** A per-prompt classification table. Written into the run's
per-set files, one file per set:

```text
set              prompt                          class
<set>/<tier>     <prompt>                        pass | fail | wrong-but-no-error
```

**Gate.** Every prompt is classified. A prompt that cannot be classified
is itself a candidate - it means the answer is neither clearly right nor
clearly wrong, which is worth naming.

---

#### Where the classification table is written

Per-set files under `docs/audit/log_analysis/<run_id>/<set>.md`. Each
file carries the prompt list, the classification, and a short note per
prompt. The `_index.md` in the same folder carries the per-set status
table - which sets are done, which are pending.

These files are append-only. Corrections go under a `## Corrections`
section at the bottom; history is not rewritten (LA-3).

---

### Step 5 - Known-fix regression cross-check

**What it does.** For each finding that has a reproducer in this tier
- a prior F-NNN whose fix is already merged - locates the reproducer
prompt and compares observed behavior to expected fixed behavior.

**Why it matters.** A fix that is not re-tested can regress silently.
This step is the reason a new round is worth running even when nothing
has changed: to catch a fix that a later commit undid, or a fix whose
underlying assumptions no longer hold.

**Source of the list.** `FIX_PLAN.md` section 5 (the ledger) names
every verified fix. Cross-check against the prompts already in this
tier's sets. Only findings with a reproducer in this tier appear here;
the rest are noted as "not reproducible in this run".

**Do.**

- List every F-NNN in the ledger.
- For each, locate the reproducer prompt in this round's sets.
- Run the reproducer. Capture the run to a file (rule 15.1).
- Compare observed behavior to expected fixed behavior.
- Record the result.

**Output.** A regression table. Written to
`docs/audit/log_analysis/<run_id>/_step6_regression.md`. The filename
keeps the old "step6" label for historical continuity; the table is
produced at this step.

```text
F-NNN   reproducer prompt              expected        observed        regression
F-001   list_all flag on explicit PO   lists POs       refuses         yes
F-007   empty child acknowledgement    acknowledges    silent          yes
...
F-016   no reproducer in this tier     -               -               cannot confirm
```

**Verdict values.**

- `no regression` - reproducer fires and behaves as fixed.
- `regression` - reproducer fires and the old bug is back. This
  becomes a candidate in Step 6.
- `cannot confirm` - no reproducer in this tier. Not a bug; noted.

**Gate.** Every reproducer run. Every result recorded. A `regression`
verdict produces a candidate - either a new F-NNN if the shape is
distinct, or a re-open of the original F-NNN if it is the same shape.

**Why this is separate from Step 4.** Step 4 classifies every prompt
in the round. Step 5 compares a specific subset against a specific
prior expectation. The same prompt can be `pass` in Step 4 and still
be a `regression` in Step 5 if the fix that made it `pass` no longer
holds, or `fail` in Step 4 and `no regression` in Step 5 if the failure
is a different shape than the one the fix addressed.

---

### Step 6 - Write candidates to `_candidates.md`

**What it does.** Every prompt that did not classify `pass` in Step 4,
or that produced a `regression` verdict in Step 5, becomes a candidate.
Each candidate gets a stable ID (`C-001`, `C-002`, ...) and one entry
in `docs/audit/log_analysis/<run_id>/_candidates.md`.

**Why it matters.** A candidate is a *thing under consideration*, not
a bug. The C-IDs are scratch IDs, used only inside one analysis round.
They become F-NNNs only after the review gate (Step 7) and R (Step 8).
Conflating the two is the mistake the pipeline exists to prevent - a
candidate written as an F-NNN skips the harm check (S1) and the
reproduction (R).

**What a candidate is not.**

- Not a bug. Bugs are F-NNNs.
- Not a harm. The harm is named at S1, in Step 9.
- Not a fix. Fixes come after the gate, in a separate window.

**Entry format.** One block per candidate, stable ID, in
`_candidates.md`:

```markdown
## C-NNN

- file:   <set>/<tier>.log
- prompt: <the prompt, verbatim>
- class:  fail | wrong-but-no-error | regression
- note:   <one sentence naming the shape>
- related: <existing F-NNN, or "none">
- status: candidate, not reproduced outside batch, R not yet run
```

**When candidates are written.** As Step 4 and Step 5 complete, not at
the end. Candidates accumulate across the round. The file is append-only
- a candidate's status changes in place, but its first entry is not
rewritten. `_candidates.md` is the record of what was noticed, before
the gate decided what mattered.

**Command.**

```bash
python scripts/log_analysis.py candidate-status <run_id>
```

Prints the current list of C-IDs and their status lines. Use it to
confirm the file is up to date before the gate.

**Output.** `_candidates.md` with one block per candidate. Plus a
status table in the run's `_index.md`.

**Gate.** This is the last read-only step. Step 7 is the review gate -
the hard stop where the analysis pauses and the disposition of each
candidate is decided together. Do not proceed past Step 6 without the
lead present.

---

### Step 7 - Review gate

**What it does.** Analysis ends here. The candidate list is reviewed
together with the lead. Each candidate gets a disposition. Then the
analysis window closes and a new window opens for findings work.

**Why it matters.** This is the boundary between "we noticed something"
and "we are treating it as a bug". Everything before this step is
cheap and reversible - a candidate can be dropped without consequence.
Everything after commits to a walk (R + S0-S11), a file, a commit, and
a fix. The gate is where that commitment is made deliberately, not by
default.

**Who is present.** The analyst and the lead. This is not a step done
alone. The lead makes the disposition calls; the analyst brings the
evidence and the walk-status per candidate.

**What to bring.**

- The candidate list from `_candidates.md`, one line per C-NNN.
- The current status of each: what evidence exists, which steps of
  S0-S11 have been walked (if any), and what remains uncertain.
- The blast radius notes: is this one prompt or a family? Related to
  an existing F-NNN, or new?
- Any regression verdicts from Step 5 that became candidates.

**What to do at the gate.** For each candidate, decide one of three:

```text
promote   -> becomes a new F-NNN. Continues to Step 8 (R).
link      -> attaches to an existing F-NNN as a related case.
             Does not become its own F-NNN.
close     -> not a bug. Recorded as an observation. Does not continue.
```

**What not to do at the gate.**

- Do not propose fixes. Fixes come after R and S0-S11; proposing them
  here skips the harm check and the falsifier.
- Do not open F-NNN files. That is Step 10.
- Do not commit anything except the gate's own record (a short note in
  `_candidates.md` naming the disposition per candidate).

**Output.** Each candidate's status line in `_candidates.md` is updated:

```text
- status: promoted to F-NNN
- status: linked to F-NNN
- status: closed as observation
```

Plus a short gate note at the top of `_candidates.md` recording the
date and the disposition decisions.

**Gate.** Nothing proceeds to Step 8 without an explicit "promote"
disposition. A candidate not promoted stays where it is - as a
candidate, not a finding.

**Why this is a stop, not a checkpoint.** The original plan document
said "surface, then stop and ask" (LA-13, `WORKING_STYLE.md`). The
stop is not a formality. It is the only place where "is this worth
committing to" is asked without the momentum of an in-progress
analysis pushing toward yes.

---

### Step 8 - R, reproduce

**What it does.** For each candidate promoted at the gate, run the
prompt against the current pod. Run it again. Run the sibling prompt -
the one nearest it in shape that passed. Capture all runs to files.
Read the results. Decide the disposition.

**Why it matters.** A finding written from a log captured days ago is
a hypothesis. The pod data moves; the LLM's output varies; a
downstream fix can land without notice. R is the cheap check that
distinguishes a bug from a stale observation before any analysis time
is spent walking S0-S11.

This is a required step in the S0-S11 standard, not a Phase-3
invention. `WORKING_STYLE.md` places R ahead of S0: "Without R, a
claim written from a stale log is a hypothesis. R is what makes it a
bug."

**What to run.**

Three runs per candidate, minimum.

1. **The same prompt.** The exact string from the log. This is the
   reproducer.
2. **A second run of the same prompt.** Distinguishes a deterministic
   failure from a stochastic one. Two clean runs is not N=20 (see
   below), but a single clean run after a recorded failure is already
   informative - it means the failure was not deterministic.
3. **The sibling prompt.** The nearest passing prompt in the same
   shape. Confirms the shape is not broadly broken. If the sibling
   also fails, the candidate's blast radius is bigger than the original
   observation suggested.

**Command shape.** One prompt per command. Capture to a file per rule
15.1 - the capture happens at the run, not at the read.

```bash
python scripts/promptkit.py --run --prompt "<exact prompt>" --show-planner > t_<F-NNN>_same.txt 2>&1
python scripts/promptkit.py --run --prompt "<exact prompt>" --show-planner > t_<F-NNN>_same_2.txt 2>&1
python scripts/promptkit.py --run --prompt "<sibling prompt>" --show-planner > t_<F-NNN>_sibling.txt 2>&1
```

Read from the file, never from a piped run:

```bash
grep -A6 '^Intent:' t_<F-NNN>_same.txt
grep -E '^  Step [0-9]:|tool_args:|filter_source_when_nonempty' t_<F-NNN>_same.txt
sed -n '/^Answer:/,/^Summary:/p' t_<F-NNN>_same.txt | head -30
```

**Cost.** Name it before handing the command over (rule 15.2). A single
prompt run through the pipeline is 20-60 seconds depending on how many
tool calls the plan makes. Three runs is 1-3 minutes per candidate.

**Reading the result.** Three outcomes, three dispositions.

```text
Fails the same way it failed in the log   -> proceed to Step 9 (S0-S11 walk)
Now passes                                -> close as not-reproducible. Cite the
                                             original run_id. Record in S7-notes
                                             as "audit-time observation diverged".
Fails intermittently                      -> N>=20 runs required. Do not classify
                                             on a small sample.
```

**N >= 20 for nondeterminism.** A claim that a prompt behaves
differently across runs is not falsifiable from two observations. If
the failure fires once in ten, that is not enough to name a rate.
Twenty runs of the same prompt, same invocation, is the threshold.
Report the raw pass/fail shape across N; a rate as high as ~14% is not
formally excluded by 20 clean runs, but the audit's own threshold is
N >= 20.

**Where R's evidence goes.** The output of the same prompt run is
pasted into the finding's `### R - Reproduction` section at Step 10.
Not summarized - pasted. The sibling's output goes alongside it.

**What R does not decide.** R does not classify the bug, does not name
the harm, does not walk S0-S11. R answers one question: does the
observed failure still fire today. Everything else comes after.

**Worked example.** During the smoke round's gate close, R produced
four different dispositions on four candidates:

- F-052 - N=20 clean. Closed as not-reproducible. The grammar-gap
  theory recorded in the finding's S3/S4 did not survive; the failure
  was the documented ~3% JSON-mode empty-draft mode.
- F-053 - one run, reproduced exactly. Planner registry omission; the
  behavior is deterministic. Confirmed on first run.
- F-054 - N=10 identical, harm did not fire. The plan shape is
  present (one-sided date filter) but the pod no longer carries
  future-dated rows. Closed on latent-shape grounds under S7-notes.
- F-055 - surfaced by R's sibling run. `invoices in the last 7 days`
  fails every run on a fractional-months conversion. No prompt in the
  original smoke set exercised this N; R's discipline of running a
  sibling forced it into view.

**Gate.** R runs before any S0-S11 walk. A candidate whose reproducer
no longer fires is closed here, not promoted onward.

---

### Step 9 - The S0-S11 walk

**What it does.** For each candidate that survived R, walk the
standard in `WORKING_STYLE.md` - R plus S0 through S11 - and show for
each step whether it passed. The walk is the finding.

**Why it matters.** The walk is what separates a bug from a label.
Every claim is checked against a fixed order: state the claim, name
the harm, paste the evidence, name the mechanism, name the root cause,
disprove an alternative, name the falsifier, classify, record the miss,
cross-link, list what was not checked, expand coverage. A claim that
stops at any step is classified by where it stopped - not by whether
it "looks like" a bug.

**The standard is not in this document.** Read
`docs/plan/WORKING_STYLE.md`, "Evidence standard for findings". The
walk is R then S0 through S11. The next paragraph explains what the
walk produces, not what each step says.

**What the walk produces.** A completed S0-S11 record for the finding,
in the shape of `docs/audit/findings/F-052.md`, `F-053.md`, `F-054.md`,
or `F-055.md`. Each of those is a real, applied walk from the smoke
round; read one to see the shape.

**The walk's key gates.**

- **S1 - Harm.** No harm, no F-NNN. An observation attaches to a
  related finding; it does not get its own ID.
- **S3 - Mechanism.** `file:line` or function. No line, no mechanism -
  just a correlation.
- **S4 - Root cause.** The mechanism is the failing line. The root
  cause is why it is written that way. If unknown, say so explicitly.
- **S6 - Falsifier.** Name the command that would prove the claim
  wrong. R has already run it; this step records the command in the
  finding so a future reader can re-run it.
- **S7 - Classification.** Confirmed, Candidate, Observation,
  Closed-as-not-a-bug. This is where the finding's status line comes
  from.

**The two S7-notes shapes.** When a prior claim is disproven, it is
one of two shapes - "nondeterminism cleared at N>=20" or "audit-time
observation diverged". Both cite the original audit row. Both preserve
the original text of the row. Neither edits history. See
`WORKING_STYLE.md` S7-notes for the exact wording.

**How the walk is written.** Directly, into the F-NNN file. The finding
file is the walk. There is no separate document that the walk is
summarized into.

**Command for the analyst.** There is no script for this step. The
walk is judgement work. The helper script does not touch it.

**Output.** Nothing written yet. The walk is composed in the analyst's
workspace and lands at Step 10.

**Gate.** Every step of S0-S11 must be recorded as passed, failed, or
not-checked. A walk that stops early is a Candidate, not Confirmed. A
walk with S1 failed is not an F-NNN.

**Why this is one step and not twelve.** Each S-step is short. Writing
a section of this plan per S-step would restate `WORKING_STYLE.md`.
The standard is the reference; this document points at it. What is
unique to the pipeline is that the walk happens at Step 9 - after R,
after the gate, after the candidate became a finding. Everything
before Step 9 is preparation; the walk is the finding.

---

### Step 10 - Write the F-NNN file

**What it does.** The completed S0-S11 walk is written into
`docs/audit/findings/F-NNN.md`. One file per finding. The file is the
walk.

**Why it matters.** A finding that lives only in a log or in a chat
window is not a record. The F-NNN file is the durable artifact - it
survives the run's raw logs (which are gitignored), survives the
branch that produced it, and survives the analysis window that wrote
it. A future reader opens the file and has everything: the prompt, the
plan excerpt, the answer excerpt, the mechanism, the root cause, the
fix location, and the run history.

**The next free ID.** `docs/audit/findings/README.md` records the next
free number when the folder was created. In practice, list the folder
and take the highest F-NNN + 1:

```bash
ls docs/audit/findings/F-*.md | sort | tail -1
```

Never reuse an ID. Never renumber. An F-NNN that turns out to be wrong
is closed-as-not-a-bug; the number stays on file.

**File shape.** The template lives at
`docs/audit/findings/README.md` under the `~~~markdown` block. Use the
helper to create a stub:

```bash
python scripts/log_analysis.py walk-stub F-NNN
```

Then fill in each section. The template's section order is the S0-S11
walk order, and the `Seen in runs` table plus the `Fix` block sit at
the bottom.

**What each section carries.**

- **Title line.** `## F-NNN - {one-line title}`. The title names the
  shape, not the symptom. "suppliers with open purchase orders lists
  suppliers with zero open POs" - not "procurement_supplier prompt 2
  is wrong".
- **Header.** Date, Status (`open` at first write; the status flips to
  `confirmed` / `closed-as-not-a-bug` at Step 11), Cross-refs.
- **R - Reproduction.** The run command and the observed result.
  Pasted, not summarized.
- **S0 through S11.** One section per step. Short.
- **Seen in runs.** Table of every run that has touched this finding,
  with the prompt and the C-to-F resolution.
- **Fix.** The fix location (where the change goes, not the change),
  the PR number once it lands, the commit hash.

**Write discipline.** Write the whole file in one cell. Do not append
sections across multiple cells - the file is a unit and a half-written
finding is worse than none. If a section is not yet known, write
"Not yet walked" and move on. The file is not the place for partial
edits.

**Commit immediately.** One finding, one commit. The commit message
names the finding and the shape:

```bash
git add docs/audit/findings/F-NNN.md
git commit -m "audit: F-NNN {short shape}"
```

Never bundle multiple findings into one commit. Each finding is a
record; each record is separately revertable.

**Output.** `docs/audit/findings/F-NNN.md`, committed.

**Gate.** The file walks S0-S11 completely. A section that reads
"Not yet walked" is a Candidate, not a Confirmed finding. The status
line in the file must match the walk's completeness.

---

### Step 11 - Update `_candidates.md` and `_touched.md`

**What it does.** Two files are updated to record what the round
produced.

- `_candidates.md` in the round folder gets the C-to-F resolution per
  candidate: which C-ID promoted to which F-NNN, which linked, which
  closed.
- `_touched.md` in the round folder gets a row per F-NNN the run
  touched. This is the run's contribution to the findings log.

**Why it matters.** Two-way link. The finding file says which run
found it; the run file says which findings it touched. Neither is the
primary record - the F-NNN file is. But without the link, a future
reader who starts from the run (to see what the smoke round produced)
has to grep every finding to find the ones from this round.

**`_candidates.md` update.** Each C-NNN's status line changes from
"candidate, R not yet run" to one of:

```text
- status: promoted to F-NNN (confirmed, S0-S11 walked YYYY-MM-DD)
- status: linked to F-NNN
- status: closed as observation
- status: closed as not-reproducible (R: <result>)
```

Plus a short resolution line under the status naming the file:

```text
- resolution: see findings/F-NNN.md
```

**`_touched.md` update.** One row per F-NNN the run touched. Appended,
not rewritten.

```markdown
| F-NNN | role | prompt | resolution |
|---|---|---|---|
| F-052 | first observed | List active suppliers with ... and address | C-004 to F-052 |
| F-053 | first observed | suppliers with open purchase orders | C-003 to F-053 |
| F-054 | first observed | invoices in the last 30 days | C-001 to F-054 |
| F-055 | sibling-surfaced | invoices in the last 7 days | C-005 to F-055 |
```

The `role` column values:

```text
first observed     the run that first saw the bug
reproduced         a later run confirming the bug
regression check   a prior fix's reproducer re-run
sibling-surfaced   a sibling prompt surfaced the shape
adjacent           a related shape, not the same bug
```

**Command.**

```bash
python scripts/log_analysis.py candidate-status <run_id>
```

Prints the current state of `_candidates.md`. Use it to confirm the
file is current before committing.

**Commit.**

```bash
git add docs/audit/log_analysis/<run_id>/_candidates.md
git add docs/audit/log_analysis/<run_id>/_touched.md
git commit -m "audit: <run_id> - C-IDs resolved, F-NNN cross-link"
```

One commit for the two files. They are updated together and reviewed
together.

**Output.** `_candidates.md` fully resolved. `_touched.md` with the
round's contribution to each finding.

**Gate.** Every promoted or linked candidate has a resolution row in
both files. Every F-NNN touched by this round has a row in
`_touched.md`.

---

### Step 12 - Commit the F-NNN file

**What it does.** The F-NNN file is added and committed. One finding,
one commit.

**Why it matters.** A finding that is not committed is not a record.
The finding files are the durable output of the round - everything
else in the round folder is scaffolding. Committing per-finding keeps
each record separately revertable; a later session that disagrees with
one finding reverts one commit, not a batch.

**When to commit.** As soon as the F-NNN file is written and verified.
Do not batch. Do not wait until the round is done. The commit is part
of writing the finding, not a follow-up task.

**Command.**

```bash
git add docs/audit/findings/F-NNN.md
git commit -m "audit: F-NNN {short shape}"
```

**Commit message shape.** `audit: F-NNN` prefix, then a short phrase
naming the shape. Not the symptom, not the file, not "fixed" - the
shape.

```text
audit: F-052 - columns list with non-column field refuses unparseable
audit: F-053 - has_open_PO missing from nonempty-suffix registry
audit: F-055 - last 7 days refuses on fractional months conversion
audit: F-054 written, closed-as-not-a-bug (R: latent shape, harm not reproducible)
```

Note the last one: F-054 was closed on first write, so the commit
message records the closure. When the status is not `open`, the
message says so.

**What not to commit in this step.**

- The round folder changes (those are Step 11's commit).
- The `_candidates.md` update (also Step 11).
- Anything in `src/` or `scripts/` - fixes are separate work, in a
  separate branch.
- Anything under `overnights/` - raw runs are gitignored.

**Revert discipline.** A finding that is later shown to be wrong is
not deleted. Its status line flips to `closed-as-not-a-bug` and a
`### Closure` section is appended (Step 13's discipline, applied
retroactively). The file stays; the commit stays. History is not
rewritten.

**Output.** One commit per F-NNN, on the branch.

**Gate.** Every F-NNN written in Step 10 has exactly one commit in
this step. No F-NNN is left uncommitted at the end of the round.

---

### Step 13 - Push branch, open PR to `hardening-master`

**What it does.** The analysis branch is pushed and a pull request is
opened against `hardening-master`. The PR carries the round's findings
and scaffolding.

**Why it matters.** Per `WORKING_STYLE.md` rules 9 and 10: PR-based
merges always, into `hardening-master`. Nothing lands on `master` -
ever - without explicit instruction from the user. The PR is the
review gate at the code level; the review gate in Step 7 was the
analysis-level gate. Both gates exist, and both are stopping points.

**Branch name.** `Phase{N}{letter}-{Descriptive}` per rule 11. For a
log-analysis round bundled with findings, the branch names the phase
and the round:

```text
Phase3b-Log-Analysis-Restructure
Phase3c-Findings-Fix-<cluster>
```

A findings round that produces fixes creates a separate branch per
rule 7. The log-analysis branch carries the F-NNN files; the fix
branch carries the code. They are separate PRs.

**Commands.**

```bash
git push -u origin <branch-name>

gh pr create \
  --base hardening-master \
  --head <branch-name> \
  --title "<Phase>: <one-line scope>" \
  --body "<body>"
```

The first push of a new branch uses `-u` to set upstream. Subsequent
pushes use `git push` alone.

**PR body shape.** The body should name:

- What the branch does (analysis structure, findings, or fixes).
- The gate results: which candidates became which F-NNNs.
- What is not in this branch (fixes, if this is the analysis PR).
- The run_id the analysis covers.

**PR title.** Names the phase and the scope, not the effort. "Phase
3b: log-analysis restructure, findings split, smoke gate closed", not
"lots of audit work".

**Never merge locally.** Rule 9: no local `git merge` into a
long-lived branch. The PR merge is done via the PR interface (or
`gh pr merge`), which is a remote operation on the origin branch.

**Merge strategy.** For a branch of docs and audit structure:
`--squash` collapses the branch's commits into one entry on
`hardening-master`. For a branch with per-finding commits that should
stay individually visible: `--merge`. Default to `--squash` for
analysis rounds; use `--merge` only when the per-commit history has
value a future reader needs.

```bash
gh pr merge <PR-number> --squash --delete-branch
```

**The `gh --delete-branch` quirk.** After merge, `gh` fetches the
repository's *default* branch (`master`) and switches the local
checkout to it. This is not the merge target; it is a local checkout
side-effect. `hardening-master` is where the merge landed. Confirm with:

```bash
git fetch origin hardening-master
git log origin/hardening-master --oneline -3
```

**Output.** The PR is open. The branch is on the remote. The gate
results are visible in the PR body.

**Gate.** The PR is open and its body names the round's outcome. A
branch pushed without a PR is not a landing; it is a suspended push.

---

### Step 14 - Update HANDOFF.md Section B

**What it does.** `docs/plan/HANDOFF.md` Section B is rewritten with
the round's gate results and the next window's open items. This is the
document a new session reads first.

**Why it matters.** The run folder records what happened. The finding
files record what was found. Section B records *the state* - what is
closed, what is open, what the next window should pick up. Without
Step 14, the next session reads a HANDOFF that describes a round that
already finished and does not know the new F-NNNs exist.

**Section B's boundaries.** The status block is delimited by markers:

```markdown
<!-- BEGIN SPIRE-LOG-ANALYSIS-STATUS -->
... status content ...
<!-- END SPIRE-LOG-ANALYSIS-STATUS -->
```

Replace everything between the markers. Do not touch anything outside
them - the rest of Section B (round pointers, rules-in-force lines) is
unchanged and hand-maintained.

**What Section B carries after a round closes.**

- Round id, tier, set count, prompt count.
- Gate status: `closed YYYY-MM-DD` (or `pending` if the gate is not
  yet closed).
- Gate results table: candidate -> disposition -> finding.
- Findings list: one line per F-NNN with status and short shape.
- Where things live: paths to findings, run analysis, plan, archive,
  and the PR.
- Next window: the open items carried forward.

**Command.** There is no helper for this step. The update is a single
Python patch of the delimited block, in two cells (write, verify).
The gate results and findings list are copied from the round's
`_candidates.md` and the F-NNN files.

**Commit.**

```bash
git add docs/plan/HANDOFF.md
git commit -m "handoff: <round-id> gate closed; F-NNN..F-NNN recorded"
git push
```

**Output.** HANDOFF Section B reflects the round's outcome. The next
window's read order starts with this file.

**Gate.** The status block reads `Gate: closed YYYY-MM-DD`. A gate
marked `pending` in Section B after a round is done means Step 14 did
not run.

---

### Part C ends here

Fourteen steps. Six read-only (1-6), one stop (7), seven findings-side
(8-14). The next parts are reference material: file templates (Part D),
the helper script reference (Part E), working-style reminders (Part F),
and the worked example pointer (Part G).

## Part D - File templates

Every file the pipeline reads or writes, in its exact shape. Copy the
template, fill the fields, keep the ordering. The ordering is not
decoration - it is what makes a round folder scannable.

All templates below sit in the run folder
`docs/audit/log_analysis/<run_id>/`, except where noted.

---

### Template - `RUN.md`

The round's provenance. One page. Answers "what is this run and where
did its raw logs go".

~~~markdown
# Run <run_id>

- tier:              smoke | verify | exhaust
- date:              YYYY-MM-DD
- manifest:          scripts/manifests/<tier>_sets.yaml
- structure:         <the discovered per-set file names>
- sets:              <N>
- prompts:           <N>
- raw:               overnights/<run_id>/ - retained: yes | no
- gate:              open | closed YYYY-MM-DD
- branch:            <branch-name>
- pr:                #<PR-number>

## Read order for this round

1. `_index.md` - per-set status table.
2. `_candidates.md` - C-IDs with resolutions.
3. `_touched.md` - F-NNN cross-links.
4. `_step6_regression.md` - regression cross-check.
5. `<set>.md` - per-set narrative, one per set.
~~~

When the raw tree is deleted, the `raw:` line flips from
`retained: yes` to `retained: no`. Nothing else changes. The finding
files stand on their own - they do not link back to the raw.

---

### Template - `_index.md`

The per-set status table. Rewritten in place as sets complete. This is
a dashboard, not a log.

~~~markdown
# <run_id> - per-set index

## Resume protocol

If the window dies:

1. Read this file.
2. Read `_candidates.md` and `_touched.md`.
3. Find the first set with status `pending`.
4. Continue extracting that set's answers with the `classify`
   helper (Part E).
5. Write the per-set file. Update this index. Move on.

## Set status

| set | file | status |
|---|---|---|
| <set> | <set>.md | done |
| <set> | <set>.md | pending |

## Rules

- One file per set. Append to the set file as you learn more. Do not
  rewrite history; corrections go under `## Corrections` at the bottom.
- `_candidates.md` is the only growing list. Stable IDs C-001, C-002.
- `_touched.md` holds the F-NNN cross-link table.
- `_step6_regression.md` holds the regression cross-check.
- Do not write to the findings log from this window.
~~~

---

### Template - `_candidates.md`

The candidate list. Append-only per candidate; resolutions appended
under a delimited block.

~~~markdown
# <run_id> - candidate findings

One entry per candidate. Stable ID. Class is one of:
fail | wrong-but-no-error | regression.

Do not log to the findings log from this window.

---

## C-NNN

- file:   <set>/<tier>.log
- prompt: <the prompt, verbatim>
- class:  fail | wrong-but-no-error | regression
- note:   <one sentence naming the shape>
- related: <existing F-NNN, or "none">
- status: candidate, not reproduced outside batch, R not yet run

---

<!-- BEGIN RESOLUTIONS -->

- C-001 -> F-NNN (promoted YYYY-MM-DD)
- C-002 -> observation (no F-NNN)
- C-003 -> F-NNN (linked to F-NNN)
- C-004 -> closed as not-reproducible (R: N=20 clean)

<!-- END RESOLUTIONS -->
~~~

**The four resolution states.**

- `promoted` - becomes a new F-NNN. Continues to Step 8 (R).
- `linked` - attaches to an existing F-NNN. No new F-NNN.
- `observation` - not a bug; S1 failed. No new F-NNN.
- `closed as not-reproducible` - R failed on re-run. No new F-NNN.

---

### Template - `_touched.md`

The round's contribution to the findings record. One row per F-NNN
the run touched. Append-only.

~~~markdown
# <run_id> - F-NNN cross-links

One row per finding this run touched. Appended at the review gate,
after each candidate resolves.

| F-NNN | role | prompt | resolution |
|---|---|---|---|
| F-NNN | first observed | <prompt verbatim> | C-NNN to F-NNN |
| F-NNN | reproduced | <prompt verbatim> | C-NNN to F-NNN |
| F-NNN | regression check | <reproducer prompt> | no regression |
| F-NNN | sibling-surfaced | <sibling prompt> | C-NNN to F-NNN |
| F-NNN | adjacent | <prompt> | linked, no new F |
~~~

**Role values.**

- `first observed` - the run that first saw the bug.
- `reproduced` - a later run confirming the bug.
- `regression check` - a prior fix's reproducer re-run.
- `sibling-surfaced` - a sibling prompt surfaced the shape.
- `adjacent` - a related shape, not the same bug.

---

### Template - `_step6_regression.md`

The known-fix regression cross-check. Written once per round, at
Step 5. One row per F-NNN in the fix ledger with a reproducer in this
tier.

~~~markdown
# <run_id> - regression cross-check

Source: `docs/fixes/FIX_PLAN.md` section 5 (the ledger).

| F-NNN | reproducer prompt | expected | observed | regression |
|---|---|---|---|---|
| F-NNN | <prompt verbatim> | <fixed behavior> | <observed> | no / yes / cannot confirm |
~~~

**Verdict values.**

- `no regression` - reproducer fires and behaves as fixed.
- `regression` - reproducer fires and the old bug is back. Becomes a
  candidate in Step 6.
- `cannot confirm` - no reproducer in this tier. Not a bug; noted.

---

### Template - `<set>.md`

The per-set narrative. One file per set. Header table, one block per
prompt. Append-only; corrections go under `## Corrections` at the
bottom.

~~~markdown
# <set>/<tier>

Run: <run_id>
Status: done | pending

## Classification

| prompt | class | note |
|---|---|---|
| <prompt> | pass | - |
| <prompt> | fail | <one-line reason> |
| <prompt> | wrong-but-no-error | <one-line reason> |

## Prompt blocks

### <prompt>

- intent: <target_entity and filters, summarized>
- plan shape: <N steps, key tool_args>
- answer shape: <N rows shown, N total, truncation disclosed>
- class: pass | fail | wrong-but-no-error
- note: <one sentence>

## Corrections

Appended after first write. Never rewrite an earlier block.
~~~

---

### The finding template

`docs/audit/findings/README.md` carries the F-NNN template. Use
`python scripts/log_analysis.py walk-stub F-NNN` to create a stub in
the correct shape. The template is not repeated here - one canonical
copy, in the README.

---

## Part E - The helper script

`scripts/log_analysis.py` does the mechanical extraction. It is one
file, six subcommands, read-only except for `walk-stub`. Every command
in Part C that is not judgement work routes through it.

**Why it exists.** The alternative is a document full of bash blocks
that every reader has to copy and adapt. That drifts: the doc says one
thing, the terminal does another, and a new reader cannot tell which
grep pattern is current. The script is the single place where the
extraction patterns live. When a new signature is discovered, it is
added once, and every future round picks it up.

**Where it lives.** `scripts/log_analysis.py`. Source is short enough
to read in one sitting. The doc points at it; the doc does not restate
its internals.

---

### Subcommand reference

~~~text
python scripts/log_analysis.py verify-round      <run_id>
python scripts/log_analysis.py exit-codes        <run_id>
python scripts/log_analysis.py signatures        <run_id> <set>
python scripts/log_analysis.py classify          <run_id> <set>
python scripts/log_analysis.py candidate-status  <run_id>
python scripts/log_analysis.py walk-stub         <F-NNN>
~~~

---

**`verify-round <run_id>`** - Step 1.

Inventories the round: top-level files (`_manifest.yaml`,
`_run_log.txt`, `_summary.log`), then one row per set showing the
triad (`<tier>.log`, `<tier>.txt`, `<folder>_summary.log`). Each file is
marked `ok` or `MISSING`.

Reads: `overnights/<run_id>/`.
Output: printed table.

---

**`exit-codes <run_id>`** - Step 2.

Reads `_summary.log`, extracts every line matching `exit=N`, prints
one row per set with exit code and seconds.

Reads: `overnights/<run_id>/_summary.log`.
Output: printed table.

---

**`signatures <run_id> <set>`** - Step 3.

Greps the set's `<tier>.log` for the signature patterns listed in the
script's `SIGNATURE_PATTERNS`. Counts hits per pattern, prints patterns
with at least one hit. "No signature matched" means the failure is
silent - it needs a different probe.

Reads: `overnights/<run_id>/<set>/<tier>.log`.
Output: printed count table.

---

**`classify <run_id> <set>`** - Step 4.

Extracts, per prompt: the PROMPT line, the first Answer line, and any
Reason or Truncation line. Cheap first pass to classify each prompt as
pass / fail / wrong-but-no-error. When the header is not enough, drop
into the raw log for that one prompt.

Reads: `overnights/<run_id>/<set>/<tier>.log`.
Output: printed per-prompt header.

---

**`candidate-status <run_id>`** - Steps 6, 11.

Reads `_candidates.md`, prints each C-ID with its current status line.
Use to confirm the candidate file is current before the gate (Step 7)
and before committing resolutions (Step 11).

Reads: `docs/audit/log_analysis/<run_id>/_candidates.md`.
Output: printed C-ID list.

---

**`walk-stub F-NNN`** - Step 10.

Creates `docs/audit/findings/F-NNN.md` from the `~~~markdown` template
block in `docs/audit/findings/README.md`. Refuses if the file already
exists - never overwrite a finding.

Writes: `docs/audit/findings/F-NNN.md`.
Output: the path written.

---

### Extending the script

Two extension points.

1. **A new signature pattern.** Add a row to `SIGNATURE_PATTERNS` at
   the top of the script. Every future `signatures` call picks it up.
   Example: the F-055 fractional-months shape is
   `r"'months': [0-9]*\.[0-9]+"` - any run producing a fractional
   months value will surface as a signature.

2. **A new subcommand.** For a repeated extraction that does not fit
   an existing command. Keep the shape: parse args, read files, print
   to stdout, no writes. The only exception remains `walk-stub`.

---

### What the script does not do

Everything that requires judgement. It does not:

- Classify a prompt. It prints the header; the analyst decides
  pass / fail / wrong-but-no-error.
- Decide harm. That is S1.
- Reproduce a prompt. That is R, and it runs `promptkit.py`, not this
  script.
- Walk S0-S11.
- Write a finding. It can create the stub; the analyst fills it.
- Any git operation. Commits and PRs are separate.

---

## Part F - Working-style reminders

These are the rules that keep biting. They are restated from
`WORKING_STYLE.md` because the round touches each of them repeatedly.

- **One command at a time** (rule 2). In an interactive session, give
  one command, wait for output, then the next. Never a block of
  commands. If a command fails mid-block, the rest fire against an
  unintended state.
- **Complete files, never fragments** (rule 3). A finding file, a
  template file, a plan section - produce the whole file in one block.
- **~~~ for any outer fence whose content contains ```** (rule 4). This
  applies to every pasteable block: findings, plan sections, handoff
  text. A mis-fenced block is a wasted turn.
- **Capture the complete output of every run to a file, then grep from
  the file** (rule 15.1). Never pipe a run through a filter at capture
  time. The cost of always capturing is one file on disk; the cost of
  guessing wrong is a re-run.
- **Name a slow command's cost before handing it over** (rule 15.2).
  "This walks ~13k invoices, expect 2-4 minutes" is enough.
- **Every file edit is a Python script plus shell verification, in two
  cells** (rule 15.3). The edit script does not verify itself. The
  verification reads the file back from disk.
- **No local merges into long-lived branches** (rule 9). PR-based
  merges always.
- **The integration branch is `hardening-master`** (rule 10). Nothing
  lands on `master` without explicit instruction.
- **The evidence standard is R + S0-S11** (`WORKING_STYLE.md`,
  "Evidence standard for findings"). R runs first, always. S1 is the
  gate: no harm, no F-NNN.
- **Reproduce before you plan a fix.** A finding whose reproducer no
  longer fires is closed-as-not-a-bug; a finding whose reproducer
  still fires is the next fix.
- **Append-only for record files, rewrite for dashboards.** A file
  that shows current state (like `_index.md`) gets rewritten. A file
  that records history (like `_candidates.md`, `<set>.md`, the
  findings log) gets appended.

---

## Part G - The worked example

The first full application of this pipeline is the smoke round
`20260925_150333`. Its artifacts are the reference. Read them in this
order.

1. **The run:** `docs/audit/log_analysis/20260925_150333/RUN.md`.
   Provenance; one page.
2. **The candidates:** `_candidates.md` in the same folder. Four
   candidates, all resolved.
3. **The findings:** `docs/audit/findings/F-052.md` through
   `F-055.md`. Four real, complete S0-S11 walks. These are the shape
   to match.
4. **The handoff state:** `docs/plan/HANDOFF.md` Section B. Gate
   closed, next-window open items.
5. **The PR:** #172 on GitHub. The full diff, the merge commit, the
   review record.

What this round demonstrates:

- Four candidates at the gate, four different outcomes. F-052 closed
  as not-reproducible after N=20. F-053 confirmed in one run. F-054
  closed on latent-shape grounds. F-055 surfaced by R's sibling run -
  a finding no other step would have caught.
- The pipeline changed itself during this round. R was added to
  `WORKING_STYLE.md` mid-round, because four candidates in a row
  could not be honestly classified without a re-run against the
  current pod. The plan document you are reading is the one that
  followed from that change.

The pipeline is not fixed. When a round shows that a step is missing
or wrong, the step changes, and this document changes with it. The
smoke round is where R earned its place; a future round is where the
next amendment will come from.
