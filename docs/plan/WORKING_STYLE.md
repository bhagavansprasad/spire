# SPIRE — Working Style

The rulebook for every session in this repository, whether the worker is a
human or GitHub Copilot. Read it at the start of a new window; read the
section you need when a rule here is not enough.

`.github/copilot-instructions.md` is auto-loaded and carries the short form.
This file is the long form and governs where the two differ.

**Provenance (2026-11-28).** This file supersedes `COPILOT_WORKING_STYLE.md`
and the older general-purpose working style. The old document instructed a
human-paste workflow — heredoc patch cells, "ask for a context bundle, never
individual files", Doc A / Doc B — which contradicts how an editor-based
agent actually works. Its durable rules are carried here. **Section numbers
cited in handovers written before this date do not map onto this file.** Those
handovers are historical records and are left as written.

---

## Part A — Behavior rules

1. **Do not modify files until asked.** Default to read-only. Explore,
   explain, and propose — never edit, create, or delete a file without an
   explicit go-ahead.

2. **Explain before modifying.** Before any change, state what will change
   and why, then wait for approval.

3. **Keep answers short.** Answer the question, then stop. No preamble, no
   extra background, no "consider also" — unless the user asks a specific
   follow-up question.

4. **Ask once when ambiguous.** If the answer changes what you produce, ask
   — once, concisely. Do not re-litigate resolved points; if the answer was
   given in a prior turn, use it.

---

## Part B — Editing mechanics

Copilot edits files directly and has a shared terminal, so there are no
paste cells to corrupt. The guarantees of a paste-and-verify workflow still
apply to every edit:

- **Old block present before** the edit (read the file first).
- **Text actually changed.**
- **Old block absent after** the edit.
- **New block present after** the edit.

Copilot runs these checks itself (`grep` / `git diff`) and shows the result,
rather than asking the user to run a second cell.

- **Per-file verification, not per-commit.** For a commit landing N files,
  edit and verify each file before the single commit. A non-landed patch is
  then attributable to its own file, at the moment of failure, rather than
  to a commit that has already absorbed N−1 good files.
- **`|| true` after a `grep -c` that legitimately expects zero.** A
  `grep -c` that finds nothing exits non-zero, so a check that treats a
  non-zero exit as failure reports the *desired* outcome as an error. Write
  `grep -c 'pattern' file || true` and say in the same breath that zero is
  expected.
- **Anchor on the invariant character, not the predicted end of line.** A
  pattern ending `$` after a name verifies nothing if the file's definition
  lines end with `():`. Anchor on the character guaranteed to follow the
  token you are locating.
- **Fences:** use `~~~` for the outer fence whenever the content contains a
  ` ``` ` fence. A mis-fenced block is a wasted turn.
- **Python edits get a syntax check.** For a `.py` file the four
  postconditions are necessary but not sufficient: a patch can satisfy all
  four and still break the module. Run `ast.parse` (or import) before
  calling it done.

---

## Part C — Project conventions

### Context and communication

- **Read source directly.** No need to assemble a context bundle first. Use
  `build_context.py` (`--files ...`) only when a diagnostic needs a
  persistent on-disk record of its code + evidence, not as the way to read
  code.
- **Name a bundle for the diagnostic, not `adhoc`.** `diag_2144`,
  `fusion_err`, `sql_diag` — the name is how a future session recognises
  what was looked at. Raw artifacts (a request/response pair, a log, a
  captured output) ride in the same bundle as the code that failed.
- **One logical step at a time.** Split on uncertainty, not on command
  count. Run one command, read the output, then the next. Commands whose
  outcome is known in advance may share a step; a command whose output
  changes what you do next gets its own.

### Branching and merging

- **Branch-first** for code, features, tooling, and bug fixes. Docs may go
  direct or ride a branch.
- **PR-based merges always.** Integration branch is `master`. No local
  merge into `master` — push the branch, open the PR, merge it there.
- **Branch naming:** `Phase{N}-{Descriptive}` (e.g.
  `Phase3-Merge-Working-Style`). Not `phase-3`.
- **After a PR merges, the next window starts on a NEW branch off
  `master`** — never a continuation of the merged branch. Merge via
  `gh pr create --base master --head <branch>` then
  `gh pr merge <num> --merge`, then `git checkout master && git pull
  --ff-only origin master`.
- **Ledger reconciliation opens every window.** Before picking new work,
  list recently merged PRs and grep the fix register for rows still at
  `fixed`:

      gh pr list --state merged --limit 20 --json number,title,mergedAt \
        --jq '.[] | "\(.number)\t\(.mergedAt)\t\(.title)"'
      grep -nE '^\| F-0[0-9]+ .*\| fixed \| — \|' docs/fixes/FIX_PLAN.md

  Every merged PR whose row still shows `fixed | —` is drift. Flip it to
  `verified | #NNN` before any new work. The `fixed → verified` flip
  happens at merge time, often in a different window from the one that
  landed the code; without this step no checklist owns it.
- *(Historical.)* Until 2026-10-08 the integration branch was
  `hardening-master-v2`, with `master` frozen at the fork point. That
  arrangement was retired when the SQL Overlay POC promoted to `master`
  (PR #191, merge `3c4b208`). `hardening-master-v2` is a historical
  branch, left in place, not used for new work.

### Window discipline

- **Keep windows medium-sized.** Switch to a fresh window at a natural
  checkpoint — a coherent unit of work committed and verified — not
  mid-task, and not after the context has grown huge. Flag the switch
  point at wrap-up; do not stop mid-edit.
- **At every window close:** (a) commit any pending work, (b) push,
  (c) update the live status/handoff document for the work in progress,
  (d) record open findings in the fix register, (e) name the next window's
  starting point.

**Resume by pointer, not by paste.** A new window in this workspace can
read the files itself, so the resume brief is a short pointer plus the one
thing a file cannot tell it — which document to open first:

```
Resume <task> (SPIRE) on a new branch off master.
Read <path/to/HANDOFF.md>, then <path/to/FIX_PLAN.md>.
```

That is the whole brief. Pasting a 300-line rulebook into every new window
costs context and goes stale the moment the file changes; pointing at it
gets the current text for two lines. Paste content only when the next
window genuinely cannot read the workspace.

The pointer must state the branch instruction explicitly — the next window
starts on a **new** branch off `master`, not on the branch that just
merged. Name it: `git checkout master && git pull --ff-only origin master
&& git checkout -b Phase{N}-{Descriptive}`.

### Documentation

- **An index describes; it does not duplicate.** If a folder index goes
  stale it is worse than absent, because a reader trusts it. Prefer one
  workspace-level index (`docs/README.md`) over a per-folder second index.
- **Audit rows close in place.** The findings log is append-only;
  corrections are new entries, nothing is deleted.
- **A defect that belongs to a known finding class gets one line, not a
  section.** When a review surfaces a defect that already has its own
  finding file, the review records a single line pointing at that file.
  The defect and its fix live in the finding file and ride their own
  branch; a deferred class is not a blocker for the current PR.
- **Dated documents are historical.** A snapshot titled with a date is a
  record of that date. Do not update it to stay current — that destroys the
  record — and do not file it where a resuming window reads it first.
- **Evidence is cited by path.** Scratch captures live under `evidence/`,
  which is gitignored, so nothing there is committed. Filenames are stable:
  a citation written as `t_f081_litmus_run.txt` before the move resolves as
  `evidence/t_f081_litmus_run.txt` today. Cite the path you can actually
  open; do not conclude a citation is broken when it has only been
  relocated.

### Evidence and findings

- **Every claim needs a command and its output.** No output = not
  evidence. "I recall the code does X" is a hypothesis: it may be
  investigated, it may not be written up.
- **Capture complete stdout+stderr to a file, then grep the file.** Never
  pipe the run itself through a filter at capture time. A filtered run bakes
  one question into the output and discards everything that question did not
  anticipate; the next question then needs a re-run with a new filter, which
  may miss something else. One unfiltered file answers every later question
  by grep, at no extra cost. This applies to every run whose output you will
  read at all — including runs judged "one-shot".
- **Name a slow command's cost before running it.** If wall-clock may
  exceed ~30s, say so with a rough figure and why. Where a cheaper
  reproducer exists, offer it; where none does, say the cost is inherent
  rather than the tool being slow. This is a rule about consent, not
  laziness: a long fetch the user did not agree to spend time on is a
  longer conversation than one they did.
- **Emitted SQL must be validated by execution, not just inspection.** Run
  it against the pod with `./runsql.sh "<SQL>"` and confirm it (a) executes
  and (b) returns the **same values as Spire's own REST answer** for that
  prompt. "The SQL executes" is not enough — "the SQL agrees with the REST
  answer" is the standard. This is what caught the F-060 stub-column defect.
- **Column existence ≠ column populated.** A column present in a schema
  dump may still be NULL on every row. When a role is bound to a physical
  column, sanity-check population with a `COUNT(<col>)` / NULL-count, not
  just a presence grep.
- **A page count is not a total.** Never report `len(page)` as the number
  of records. Check the response's own continuation flag before asserting a
  count; when the true total is unknown, say unknown rather than stating the
  page size. This is the SP-005 shape, and it was in three tools at once.
- **Deferred test failures get an `xfail` + a register note, not a silent
  ignore.** A failing test you are not fixing this window is marked
  `@pytest.mark.xfail(reason="... (FIX_PLAN §n)", strict=False)` and
  recorded in the fix register. Do not delete or comment out the test. Note
  that an `xfail` on a *guard* reports failure as an expected outcome — if
  the guard is the thing protecting you, prefer fixing the drift.
- **Nondeterminism claims need N≥20.** A claim that a prompt behaves
  differently across runs is not falsifiable from one observation or seven.
  Twenty runs of the same prompt, same invocation, is the threshold. Report
  the raw pass/fail shape across the N; a rate as high as ~14% is not
  formally excluded by 20 clean runs, but 20 clean runs is a closed finding,
  not a suspended one.
- **The SME test.** When Spire refuses a prompt, the first question is not
  "is the prompt well-formed?" and not "does this capability exist today?"
  It is: could a Fusion SME, given this prompt and read access to Fusion,
  produce an answer? If yes, the prompt is answerable, and Spire's refusal
  is a **defect** — not a coverage gap, not a narrowing of scope, not "the
  user asked the wrong thing." Descriptions of the gap — no vocabulary, no
  parameter, no tool binding, outside this POC's scope — describe the
  defect; they never excuse it.

#### The findings walk: R then S0–S11

Before anything enters a findings log as a bug, the claim walks R and then
S0–S11 **in order**. If a step fails, the claim stops at that step and is
classified accordingly. The point is not caution for its own sake — a wrong
finding costs as much as a missed one, because a later session acts on it.

**R — Reproduce.** Read the prompt end to end. Run it against the current
pod. Run it again. Run the nearest sibling prompt of the same shape that
passed. Capture all three to files and paste the outputs.

- Fails the same way as logged → proceed to S0.
- Now passes → closed **not-reproducible**; cite the original run id.
- Fails intermittently → N≥20 runs before any classification. This is the
  only case in which a rate may be quoted.

**S0 — State the claim in one sentence.** "X is a bug" or "X is not a bug."
No other forms. "X looks wrong" / "X is drift" / "X is odd" are hunches;
hunches live in conversation and do not enter a document.

**S1 — Name the harm.** Exactly one: wrong data returned · wrong narration
(data right, words wrong) · crash · refusal of an in-scope prompt · silent
omission · cost regression · inconsistency between two paths. No harm →
stop; it is an observation, not a bug. Observations attach as a note to a
related finding; they do not get their own ID.

**S2 — Paste the evidence.** Tiers, best to worst: (1) curl-verified, the
pod directly confirms; (2) runtime output pasted verbatim; (3) static,
cited by `file:line`; (4) "I recall". Tier 4 is not evidence.

**S3 — Name the mechanism.** The specific `file:line` or function that
causes the harm. No line, no mechanism — only a correlation.

**S4 — Name the probable root cause.** Wrong design decision · plan-template
selection gap · parser grammar gap · missing guard or default · stale
assumption about pod data. If none can be named, record "mechanism known,
root cause unknown" explicitly — that tells the fix window it may be about
to patch a symptom.

**S5 — Disprove one alternative.** Pod data changed between runs · a
different code path was taken · the diagnostic is lying · it is by design
(read the design doc first). If no alternative can be named, the cause is
not isolated.

**S6 — Name the falsifier.** What one command would prove the claim wrong?
If none can be named, the claim is not falsifiable and cannot enter the log.

**S7 — Classify.** *Confirmed* (S1–S6 all passed) · *Candidate* (note which
failed) · *Observation* (S1 failed; a note under a related finding) ·
*Closed-as-not-a-bug* (a prior claim disproven by stronger evidence; cite
the old ID).

**S7-notes — the two `closed-as-not-a-bug` shapes.** Naming which one it is
tells future sessions what may and may not be re-opened.

- **Nondeterminism cleared at N≥20.** An intermittent symptom was recorded;
  N runs produce identical output and the reproducer does not fire. The
  original row stays as written. Re-open only if the same prompt starts
  varying again, or the underlying fetch/aggregation changes.
- **Observation-time symptom diverged.** The recorded symptom does not
  appear at its own reproducer. Either the code changed or the pod state
  changed. No git archaeology at closure time; the row stays as written and
  the finding records both the closure and a "not checked" clause naming
  which side may have moved. Re-open only if the original shape reappears.

Both shapes cite the original row and include its claim for comparison.
Neither edits the original row's text.

**S8 — The miss record.** A confirmed bug is also a miss by the prior
audit. Answer three questions in order: (1) Did a prompt of this shape
exist — existing / passed-but-wrong / absent? (2) Why did it not surface —
the *reason*, not the category. "The prompt existed and passed" is a
category; "it passed because its plan happened to set
`filter_source_when_nonempty` while the sibling plan did not" is a reason.
(3) What would have caught it? This is the record a future audit reads to
find its blind spots.

**S9 — Cross-link.** Every entry cites at least one other row or finding.
Orphan entries get re-checked before the next session.

**S10 — List what was NOT checked.** Explicit. This is what a future
session reads to decide where to look next. "Nothing else was checked" is a
valid and useful entry.

**S11 — Coverage expansion.** Every confirmed bug has a shape. List the
sibling prompts that exercise it, naming the tier each belongs to (smoke /
verify / exhaust). Sibling prompts land in the fix's branch, in
`prompts/<capability>/<tier>.txt` — a list in the fix file alone is not
coverage, because the next sweep does not read fix files.

**The contract.** Every time an F-NNN is proposed, R and S0–S11 are walked
in order and it is shown which passed. Any time "is this a bug?" is asked,
the answer names the step, not a paragraph.

**A worked example — a claim wrongly filed as a bug.** "`top_invoices_by_amount`
is in `draft.py` but not in `modes/m_aggregation.sysprompt`; that is a
bug." S0 passed (stated). S1 failed (no harm named — no prompt broke, no
wrong answer, no crash, no refusal). Under this standard it should have
stopped at S1 as an observation under the related finding. It was instead
written up as its own finding and disproven later, at the cost of a probe
and a rewrite. The lesson is not that it was hard — it is that a label
("drift") was treated as a finding before a harm had been shown.

### Dev / runtime

- Run, start/stop/restart, and the port layout are in
  `Quick_how_to_run.md`. Dev uses 4001/4002/4003; production 5000/5001/5002
  (testers via ngrok). `SPIRE-PORTS.env` is the single source of truth — to
  change a port, change it there only.
- **Restart the API/MCP server after any change under `src/spire/`.**
  Imports are cached at startup, so editing the file does not change the
  running process's behavior. Host mode: `./spire-host.sh --restart dev`.
  Docker mode: `./spire-docker.sh --restart dev`. Every subpackage counts:
  `mcp_server/`, `kg/`, `rendering/`, `api/`, `synthesizer/`, `nl_parser/`,
  `planner/`, `executor/`. The failure this prevents: a UI showing stale
  output while `master` is current and the CLI is correct for the same
  prompt — two responses to one prompt, one current and one stale, and
  indistinguishable from a real bug without restarting to check.
- **`spire-host.sh` needs the venv on `PATH`.** It shells out to
  `fastmcp`; without the venv active the MCP server fails to start and the
  failure reads as a port timeout. Export
  `PATH="/home/bhagavan/virtenv/spire/bin:$PATH"` first.
- **Stop services with `./spire-host.sh --stop`, never a broad `pkill`.**
  A pattern like `pkill -f "spire.mcp_server.server"` also matches servers
  started by the user or by another mode.
- **Python interpreter is `/home/bhagavan/virtenv/spire/bin/python`**, not
  bare `python`/`python3` — the bare interpreter lacks `oracledb`. Use the
  full path for `python`, `pip`, and `pytest`. `./runsql.sh` (Oracle via
  curl) does not need it.
- **`./runsql.sh "<SQL>"` is the pod-SQL validator.** It posts to the
  Fusion BI Publisher report and returns tabular rows. Credentials come from
  `IKS_FUSION_USERNAME` / `IKS_FUSION_PASSWORD`.
- **A check that costs nothing is not automatically worth running.** Match
  the scope of the verification to the scope of the change: a docs-and-
  scripts commit needs the tests that guard docs and scripts, not the whole
  suite. State which tests you ran and why that set covers the change.

### Auth

- **No auth at the tunnel or app layer.** When auth lands, SPIRE owns it.
  Do not add an extra module in front.

### Reply discipline

- Short, plain, no preamble.
- **Report the queue after every closure.** After every bug fix or closure,
  state how many rows remain pending in the fix register and name the next
  one being picked up — a fix, a `closed-as-not-a-bug`, or a merge with its
  tracking flip. This appears in the same reply that delivers the closure
  news, before the next task. The user should never have to ask "what's
  next?"
- **The SME test governs S1.** "In-scope" there means an SME could answer
  it, not that Spire supports it today. An SME-answerable refusal passes S1
  as "refusal of an in-scope prompt", and the capability gap that caused the
  refusal is the finding's root cause.

---

## Appendix — log analysis

The discipline for reading promptkit runs (smoke / verify / exhaust tiers),
pytest output, and any tool-run log. It runs alongside the findings walk:
the walk governs what becomes a finding; this governs how logs are read and
how candidates surface *before* the review gate.

**LA-1 Read-only until the review gate.** No code fixes, no findings-log
writes, no repository changes except under `docs/` and the analysis
workspace. Output is a candidate list plus the on-disk record. Logging and
fixing happen after the gate, with its own approval.

**LA-2 On-disk files are the source of truth.** Chat is not. If the window
dies, the next one reads the files and resumes; nothing depends on chat
history.

**LA-3 One set at a time, one command at a time.** Extract one set, read
it, classify it, write its file, update the index, move on. Never batch
sets into one analytical pass unless the batch is small and explicitly
named.

**LA-4 Priority order for reading a run.** (1) Structural integrity: set
count, per-set triad, timestamps, manifest match. (2) Exit-code triage —
cheapest, highest signal. (3) Signature extraction on non-zero sets.
(4) Prompt-level classification for all sets. (5) Cross-fix regression for
the findings whose reproducers live in this tier. (6) Candidate list.
(7) Review gate. Stop and ask.

**LA-5 Four classes per prompt, exactly.**
- `pass` — right rows, right claims.
- `fail` — errored, or refused when it should not have.
- `wrong-but-no-error` — reads correctly but says something false.
- `regression` — a previously fixed behavior has reverted.

An observation (no harm named) is not a class. Observations go under
`## Observations` and may be promoted to a candidate only if a harm can be
named.

**LA-6 Watchlist of failure shapes.** These are the shapes that have
actually shipped:
- Empty data behind confident prose.
- **A page count stated as a total.**
- A computation over a truncated sample stated as fact.
- Customer-scoped results that never resolve an `AccountNumber`.
- A generalisation true of the first few rows but not of the set.
- A list-shaped answer with no `Showing N of M` and no truncation line.
- A count computed over the sample rather than over the full set.
- Two prompts of the same shape that plan differently — one filters, one
  does not.
- A collection returning zero rows where the partition is known non-empty.
  A 0-row HTTP 200 is not evidence that the data does not exist, and it
  produces a *confident wrong answer* rather than an error.

**LA-7 Cross-set consistency.** The same prompt in two sets should behave
the same. When it does not, that is a candidate until proven otherwise.

**LA-8 Extraction.** Capture complete output to a file first; never pipe
the run through a filter at capture time. Plans only:
`awk '/^Intent:/,/^Outputs:/' <log>`. Answers only:
`awk '/^PROMPT: /{p=1} p' <log>`. Prefer header plus truncation for the
first pass; drop into full `cat` only for the prompt the header cannot
classify.

**LA-9 The review gate.** Analysis ends here. Bring the candidate list, the
findings walk per candidate, and the blast radius. Decide together: log as
a new finding, link to an existing one, or close as not-a-bug. Priority is
decided. Stop. **Do not propose fixes at the gate.**
