# SPIRE — Working Style

**Reference for every session.** Read at the start of a new window.
For the procedural checklist that accompanies this file, see
`SESSION_STARTUP_CHECKLIST.md`. Cross-references Doc B index §7.

---

## Context and communication

1. **Ask for context bundles, never individual files.** `context_bundles.yaml`
   defines the bundles (`graph_kg`, `synthesizer`, `parser_planner`,
   `mcp_server_tools`, `scripts`, etc.). When you need to see code, ask
   for the bundle.

2. **One command at a time.** In an interactive session, never give a
   block of commands. Give one, wait for the output, then the next. If
   a command fails mid-block, the remaining commands fire against an
   unintended state.

2.1. **"One command at a time" splits on uncertainty, not on count.**
    Rule 2's "block of commands" means a block where a later command's
    meaning depends on an earlier one's output. Commands whose outcome
    is known in advance — `git checkout -b`, `git add <path>`,
    `git commit`, `git stash pop`, `git branch`, `git status` on a
    clean tree — do not qualify. They belong in the same cell as the
    work they surround.

    The reason rule 2 exists is that a failed command mid-block fires
    the rest against an unintended state. `git checkout -b` either
    creates the branch or fails loudly; there is no partial state for
    the next command to trip over. Split only what can leave the tree
    in a state the next command would misread.

    What DOES take its own cell: a test run, a grep whose result
    decides whether a fix landed, a build — any command whose
    next-step meaning changes if the output surprises you.

2.2. **The user pastes once per cell when the shape is obvious.**
    When the commands in a cell are all obvious (2.1), the user runs
    them together and returns ONE output block — not one per
    command, not "paste that, then paste this". Do not ask for the
    output of a command whose result is predetermined. The user reads
    their own terminal; they paste back when the shape of the output
    determines what you hand them next.

3. **Complete files, never fragments.** When producing a file, produce
   the whole file in one block. Never "replace section X with Y" or
   "insert this between lines N and M". If a change is small, still
   produce the whole file. Fragments waste time and break copy/paste
   tools.

4. **No nested code fences.** Nested ` ``` ` inside ` ``` ` breaks copy
   and download. Use `~~~` for the outer fence, or move the inner
   content to a separate file. **This applies to every pasteable block
   you produce** — findings, audit edits, handoffs. If the content
   contains even one ` ``` ` inside it, the outer wrapper is `~~~`.
   The user pastes verbatim; a mis-fenced block is a wasted turn.

## Generation and approval

5. **Approval before generating anything.** Never produce code, files,
   or doc text without an explicit go-ahead. Acknowledge a task,
   describe what you will produce, and wait.

6. **Draft first, permission after.** Do not ask permission for
   something already designed and approved in an earlier turn. Produce
   the artifact. Ask only when the answer changes what you write.

## Branching and merging

7. **Branch-first for code, features, tooling, bug fixes.** Everything
   that is not a pure doc lands on a branch first, then merges via PR.

8. **Docs may go direct or branch.** README, Doc A, Doc B, tester-intro
   — direct to the integration branch is fine if standalone; ride a
   branch if bundled with code.

9. **PR-based merges always.** No local `git merge` into a long-lived
   branch. Push the branch, open a PR, merge the PR.

10. **Integration branch is `master`.** All phase branches spawn off it
    and merge back via PR. The runtime clone pulls from `master`.

    No local merges into `master`; every change arrives via a PR. Do
    not `git merge` a feature branch into `master` locally and push;
    open the PR and merge it there.

    (Until 2026-10-08 the integration branch was `hardening-master-v2`,
    with `master` frozen at the fork point. That arrangement was
    retired on 2026-10-08 when the SQL Overlay POC promoted to
    `master` (PR #191, merge commit `3c4b208`). `hardening-master-v2`
    is now a historical branch, left in place, not used for new work.)
11. **Branch naming: `Phase{N}-{Descriptive}`.** Examples:
    `Phase1-Audit-and-Baseline`, `Phase2-Correctness-Fixes`. Not
    `phase-1`.

## Documentation structure

12. **Doc A is frozen.** No design edits, no phase renumbering, no
    reordering. Status and deviation notes only.

13. **Doc B is split:**
    - `Doc_B_Index.md` — snapshot, registers, test taxonomy, session
      pointers, design pointers, dev/runtime, working-style.
    - `NN_Phase_NN_Name.md` — one file per phase, containing that
      phase's session entries and designs.
    - `TEMPLATE_Session_Entry.md` — the session template.
    - Created only as phases begin.

14. **Three update disciplines, three documents.**
    - **Doc A — frozen.** No design edits, no renumbering. Status and
      deviation notes only (see §12).
    - **The phase-1 audit — working document.** Rows close in place: a
      `pending` state changes to `agree` / `disagree`, with a closure
      clause naming the F-NNN. Appending rather than editing a stale
      state is the exception, not the rule.
    - **The findings log — append-only.** Corrections are new entries
      referencing old IDs. Nothing is deleted. Newest at the top.

    In practice: an audit row that says "Pending — needs bundle X"
    becomes "agree" or "disagree" once the bundle is read; the audit
    keeps a clean current state. A finding that was written wrong is
    not edited — a new finding cites the old and corrects it.

15. **Every claim needs a command and an output.** If a command and its
    output cannot be pasted, it is not evidence.

    **Every edit to a file is delivered as a Python script plus shell
    verification commands — see rule 15.3.** The anchor-uniqueness
    discipline still holds; it is asserted by the cell-1 script and
    confirmed by cell 2.

15.1. **Capture the complete output of every run to a file, then grep
    from the file. Always. No exceptions for "one-shot" checks.**
    Redirect the COMPLETE stdout AND stderr to a file first, then run
    `grep` / `sed` / `awk` against the file. Never pipe the run itself
    through a filter (`grep`, `awk`, `head`, `tail`) at capture time.

    This applies to EVERY run whose output you will read at all —
    multi-prompt sweeps, single diagnostic runs, pytest invocations,
    golden-prompt checks, ad-hoc probes. The earlier wording here read
    "for any run you may inspect more than once", and that hedge has
    tempted exactly the mistake it should forbid: a run judged
    "one-shot" gets piped through a filter, and the full output is gone
    the moment a follow-up question needs a line the filter did not
    anticipate. The cost of guessing wrong is a re-run; the cost of
    always capturing is one file on disk.

    The reason is cost, not purity. A filtered run bakes one question
    into the output and throws away everything that question did not
    anticipate. When a later question needs a line the filter did not
    match, the run has to be repeated — with a new filter, which may
    itself miss something. One unfiltered file answers every subsequent
    question by grep, at no extra cost.

    The shape:

        for p in ...; do
            python scripts/promptkit.py --run --prompt "$p" --show-planner
        done > t_<finding>.txt 2>&1

    Inspection (any number of times, no re-run):

        grep -nE 'pattern' t_<finding>.txt
        sed -n '/start/,/end/p' t_<finding>.txt

    Never:

        ... | grep 'pattern'    # the question is baked in; a second
                                # question means a second run
        ... | head -80          # truncated permanently

15.2. **Name a slow command's cost before the user runs it.**
    Before handing over any command whose wall-clock may exceed about
    thirty seconds, say so in the same reply, with a rough figure and,
    when known, why it is slow. "This walks ~13k invoices across 26
    pages, expect 2-4 minutes" is enough. Without it the user has no
    way to decide whether to run it now, later, or ask for a cheaper
    path.

    Where a cheaper reproducer exists, offer it. Where none does — an
    aggregate whose fetch is inherently the whole collection — say that
    too, so the user knows the cost is not avoidable rather than the
    tool being slow.

    This is not a rule about laziness; it is a rule about consent. A
    long fetch the user did not agree to spend time on is a longer
    conversation than one they did.

15.3. **Search-and-replace is a Python script + shell verification, in
    two cells.** Every edit to a file — code, docs, this file itself — is
    delivered as two cells, one command at a time.

    **Cell 1 — the edit.** One Python script that does the search and
    replace and writes the file. That is its whole job. It does not
    verify its own work, does not print diagnostic checks, and the user
    does not paste its output back.

    **Cell 2 — the verification.** A separate list of SHELL commands —
    `grep`, `sed -n`, `wc -l`, `tail` — that the user runs on its own,
    after cell 1 has finished. The commands re-read the patched file
    from disk and print the evidence directly: new content present, old
    content absent, surrounding anchors intact, count-preserving edits
    still count-preserving. The user pastes THIS output. Cell 2's output
    is the only evidence that comes back.

    **Do not blend the two.** The edit script and the verification
    commands are separate cells, run separately. A script that edits
    then checks itself reports whatever it wrote — the check is worth
    nothing. The verification reads the file a second time, in a fresh
    process, and the user sees the raw lines.

    **Why a script, not a paste block.** The paste step is one that can
    silently fail: a truncated selection, a dropped trailing newline, an
    editor that auto-indents a block it should not. And the payload lives
    inside Python string literals, not a Markdown fence, so rule 4's
    outer-fence discipline does not apply — an edit whose content
    contains ``` is a non-problem in a script and a real problem in a
    paste block.

    **Relationship to rule 15's former paragraph.** Rule 15 used to
    describe a paste-block-with-grep-anchors procedure. That procedure is
    superseded by this rule. Rule 15's principle — every claim needs a
    command and its output — is unchanged. The anchor-uniqueness
    discipline still holds; it is asserted by cell 1 and confirmed by
    cell 2.

## Evidence standard for findings (S0–S11)

Before anything is written into a findings log as a bug, the claim
walks through R and then S0–S11 in order. If a step fails, the claim stops at that
step and is classified accordingly. The point is not caution for its
own sake — it is that a wrong finding costs as much as a missed one,
because a later session acts on it.

**R — Reproduce the prompt.**
Read the prompt end to end, exactly as it was written. Run it against
the current pod. Run it again. Run the sibling prompt — the one nearest
it in shape that passed. Capture all three runs to files (rule 15.1),
paste the outputs.

  - The prompt fails the same way it failed in the log → proceed to S0.
  - The prompt now passes → the bug is closed as **not-reproducible**;
    nothing further is walked. Cite the original run_id in the closure.
  - The prompt fails intermittently → N≥20 runs before any
    classification. This is the only case in which a rate may be quoted.

Without R, a claim written from a stale log is a hypothesis. R is what
makes it a bug.

**S0 — State the claim in one sentence.**
Either "X is a bug" or "X is not a bug." No other forms. "X looks
wrong," "X is drift," "X is odd" are hunches. Hunches live in
conversation; they do not enter a document.

**S1 — Name the harm.**
A bug is a harm. Pick exactly one:
  - wrong data returned
  - wrong narration (data right, words wrong)
  - crash
  - refusal of an in-scope prompt (Rule 28 — "in-scope" means an SME could answer it)
  - silent omission
  - cost regression (extra calls, tokens)
  - inconsistency between two paths

No harm → stop. It is an observation, not a bug. Observations can be
attached to a related finding as a note; they do not get their own
F-NNN.

**S2 — Paste the evidence.**
Evidence tiers, best to worst:
  1. curl-verified — the pod directly confirms or refutes
  2. runtime, output pasted — a prompt run, output pasted verbatim
  3. static, cited by `file:line` — grep or code read
  4. "I recall the code does X"

Tier 4 is not evidence. It is a hypothesis. It may be investigated;
it may not be written up.

**S3 — Name the mechanism.**
Cite the specific `file:line` or function that causes the harm. No
line, no mechanism — just a correlation.

**S4 — Name the probable root cause.**
The mechanism is the line that fails. The root cause is why that line
is written that way. State one:
  - a design decision that is wrong
  - a plan-template selection gap
  - a parser grammar gap
  - a missing guard or default
  - a stale assumption about pod data

If no root cause can be named, record "mechanism known, root cause
unknown" explicitly. That tells the fix window it may be about to
patch a symptom.

**S5 — Disprove the alternative.**
Name one alternative explanation and show it is not the cause. Common
ones:
  - the pod data changed between runs
  - a different code path was actually taken
  - the diagnostic is lying; the pipeline is fine
  - it is by design (read the design doc first)

If no alternative can be named, the cause has not been isolated.

**S6 — Name the falsifier.**
If someone said "no, this isn't a bug," what one command would prove
them right? If no such command can be named, the claim is not
falsifiable and cannot enter the log.

**S7 — Classify.** Only now write the F-NNN entry:
  - **Confirmed** — S1–S6 all passed.
  - **Candidate** — some steps failed; note which.
  - **Observation** — S1 failed; goes as a note under a related
    finding, not its own entry.
  - **Closed-as-not-a-bug** — a prior claim disproven by stronger
    evidence; cite the old entry ID.

**S7-notes — the two `closed-as-not-a-bug` shapes.**

When a prior claim is disproven, it falls into one of two shapes.
Naming which one it is clarifies what future sessions should and should
not re-open.

  - **Nondeterminism cleared at N≥20.** The audit recorded an
    intermittent symptom; N runs of the same prompt (the audit's own
    threshold is N≥20) produce identical output. The specific
    reproducer does not fire; the audit row stays as written. Re-open
    only if the same prompt starts varying again or the underlying
    fetch/aggregation tool changes.
  - **Audit-time observation diverged.** The audit's recorded symptom
    does not appear at its own reproducer. Either the code changed
    (silently, or with a fix whose comment names the prompt) or the pod
    state changed. No git archaeology is done at closure time; the
    audit row stays as written; the finding records both the closure
    and the "not checked" clause about which side moved. Re-open only
    if the original shape reappears or a change touches the named site.

Both shapes cite the audit row in `Cross-refs` and both include the
audit's original claim in the `Evidence` block for comparison. Neither
edits the audit row's text.

**S8 — The miss record.**
A confirmed bug is also a miss by the prior audit. Answer three
questions in order:

  1. Did a prompt of this shape exist? — existing / passed-but-wrong /
     absent.
  2. Why did it not surface? — the reason, not the category. "The
     prompt existed and passed" is a category. "The prompt existed and
     passed because its plan happened to set
     `filter_source_when_nonempty` while the sibling plan did not" is a
     reason.
  3. What would have caught it? — the prompt or check that did not
     exist at the time.

This is the record a future audit reads to find its blind spots.

**S9 — Cross-link.**
Every entry cites at least one §A / §B / §D row or another F-NNN.
Orphan entries get re-checked before the next session.

**S10 — List what was NOT checked.**
Explicit. This is what a future session reads to decide where to look
next. "Nothing else was checked" is a valid and useful entry.

**S11 — Coverage expansion.**
Every confirmed bug has a shape. List the sibling prompts that
exercise the same shape — existing or to-be-written — naming the tier
each belongs to (smoke / verify / exhaust). This produces work for the
prompt-set tree, not the findings log. It is the step that closes the
gap between "we found this bug" and "we find its siblings before a
user does. Sibling prompts land in the fix's branch, in `prompts/<capability>/<tier>.txt`. A list in the fix file alone is not coverage; the next prompt-set sweep does not read fix files."

**Nondeterminism claims need N≥20.** A claim that a prompt behaves
differently across runs is not falsifiable from one observation or
seven. Twenty runs of the same prompt, same invocation, is the
threshold. Report the raw pass/fail shape across the N; a rate as high
as ~14% is not formally excluded by 20 clean runs, but the audit's
own threshold is N≥20 and empirical clean results at that N are a
closed finding, not a suspended one.

**The contract.** Every time an F-NNN is proposed, the steps R and S0–S11
are walked in order and it is shown which passed. Any time the question
"is this a bug?" is asked, the answer names the step, not a paragraph.

**A worked example — F-006, wrongly filed as a bug.** The claim was
"`top_invoices_by_amount` is in `draft.py` but not in
`modes/m_aggregation.sysprompt`; that is a bug." Under this standard:

  - S0 passed — the claim was stated.
  - S1 failed — no harm was named. No prompt broke because of the
    disagreement; no wrong answer, no crash, no refusal.
  - Under the standard, the claim should have stopped at S1 as an
    observation, attached to F-003 (which it turned out to belong to)
    rather than given its own F-NNN.
  - It was instead written up as F-006 and only disproven later, at the
    cost of a probe and a rewrite.

The lesson is not "F-006 was hard." It is that a label ("drift") was
treated as a finding before a harm had been shown. S1 is the step that
was skipped.

16. **Every window opens with a ledger reconciliation.** Before
    picking the next FIX_PLAN row, list recently-merged PRs and
    grep FIX_PLAN §5 for rows still at `fixed`:

        gh pr list --state merged --limit 20 --json number,title,mergedAt \
          --jq '.[] | "\(.number)\t\(.mergedAt)\t\(.title)"'
        grep -nE '^\| F-0[0-9]+ .*\| fixed \| — \|' docs/fixes/FIX_PLAN.md

    Every merged PR whose F-NNN row still shows `fixed | —` is
    drift. Flip to `verified | #NNN` (and phase-1-audit §B.6
    accordingly) before any new work.

    The `fixed → verified` flip happens at PR-merge time, often a
    different window from the one that landed the code. Without
    this step, the flip is a fact no checklist owns.

## Deferred items

17. **`personas.yaml` untrack (task 1.1) — deferred.** Handled at the
    end of the plan. Not recorded as a deviation anywhere.

18. **Integration tests (the 22 marked `integration`) — deferred.** Not
    run, not investigated, not fixed during Phase 1.

## Dev / runtime separation

19. **Runtime clone at `~/pocs/spire-runtime` is never disturbed.**
    Ports 3001/3002/3003. Testers reach it via ngrok.

20. **Dev tree at `~/pocs/spire` uses 4001/4002/4003.** Set by the
    `spire()` shell function from `SPIRE-PORTS.env`. The two sets are
    `X00Y`, X=3 for runtime and 4 for dev.

21. **The `spire.sh --dev | --runtime` flag is required.** There is
    no default mode. `SPIRE_MODE` is set by `spire()` / `spirer()` in
    `~/.bashrc`. `--status` and `--stop` are scoped to the current
    mode and never touch the other tree's ports.

22. **No promotion script.** Runtime updates are manual, deliberate,
    rare — `git fetch && git reset --hard` in the runtime tree.

## Auth

23. **No auth at the tunnel or app layer.** When auth lands, SPIRE owns
    it. Do not add an extra module in front.

## Reply discipline

24. **Short, plain, no preamble.** Skip "Great question!" and similar.
    Answer, then stop.

25. **Ask before assuming.** If something is ambiguous and the answer
    changes what you produce, ask — but ask once, concisely.

26. **No re-litigating resolved points.** If the answer was given in a
    prior turn, use it.

27. **After every bug fix, report the queue.** State how many rows
    remain pending in `docs/fixes/FIX_PLAN.md` and name the next
    one being picked up. This runs after every closure — a fix, a
    `closed-as-not-a-bug`, a merge with its tracking flip — and it
    appears in the same reply that delivers the closure news, before
    the next task's commands. The user should never have to ask
    "what's next?"; that question is answered proactively.

28. **The SME test — an SME-answerable refusal is a defect.** When Spire
    refuses a prompt, the first question is not "is the prompt
    well-formed?" and not "does this capability exist today?" It is:
    could a Fusion SME, given this prompt and read access to Fusion,
    produce an answer? If yes, the prompt is answerable, and Spire's
    refusal is a defect — not a coverage gap, not a narrowing of scope,
    not an observation, not "the user asked the wrong thing."

    Descriptions of the gap — no vocabulary, no parameter, no tool
    binding, outside this POC's scope — describe the defect. They never
    excuse it.

    This governs S1. "In-scope" there means an SME could answer it, not
    Spire supports it today. An SME-answerable refusal passes S1 as
    "refusal of an in-scope prompt", and the capability gap that caused
    the refusal is the finding's root cause.
    
---

## Log analysis — reading, classifying, recording

This is the discipline for analyzing promptkit runs (smoke, verify,
exhaust tiers), pytest output, and any future tool-run log. It runs
alongside S0–S11: S0–S11 governs what becomes a finding; this governs how
logs are read and how candidates are surfaced *before* the review gate.

**LA-1 — Read-only until the review gate.**
During log analysis: no code fixes, no findings-log writes, no
repository changes except under `docs/plan/` and the analysis workspace.
Output is a candidate list plus the on-disk session record. Logging and
fixing happen after the gate, in a separate window with its own
approval.

**LA-2 — On-disk files are the source of truth.**
Chat is not. Every candidate, action item, classification, and set
observation goes into a file before the window closes. If the window
dies, the next reads the files and resumes; nothing depends on chat
history.

**LA-3 — Per-set files, not one growing document.**
Layout under `docs/audit/log_analysis_sessions/<run_id>_<tier>/`:

- `_index.md` — resume protocol + per-set status table.
- `_candidates.md` — stable IDs C-001, C-002, ...
- `_action_items.md` — S0–S11 walk per candidate.
- `<set>.md` — one per set.
- `_step6_regression.md` — one per multi-set step that produces its own
  artifact.
- `_next_window.md` — read order and steps for the next window.

Append-only. Corrections go under `## Corrections` at the bottom of the
per-set file; do not rewrite history.

**LA-4 — One set at a time, one command at a time.**
Extract one set, read it, classify it, write its file, update the
index, move on. Never batch multiple sets into one analytical pass
unless the batch is small and explicitly named.

**LA-5 — Priority order for reading a run.**

1. Structural integrity: set count, per-set triad (`.log`, `.txt`,
   `_summary.log`), timestamps, manifest match.
2. Exit-code triage: every non-zero exit from `_summary.log` and
   `_run_log.txt`. Cheapest, highest-signal first pass.
3. Signature extraction on non-zero sets.
4. Prompt-level classification for all sets.
5. Cross-fix regression check for the F-NNNs whose reproducers live in
   this tier.
6. Candidate list.
7. Review gate. Stop and ask.

**LA-6 — Classification vocabulary.**
Exactly four classes per prompt:

- `pass` — right rows, right claims.
- `fail` — errored, or refused when it should not have.
- `wrong-but-no-error` — reads correctly but says something false.
- `regression` — a previously fixed behavior has reverted.

An observation (no harm named) is not a class. Observations go in the
per-set file under `## Observations`, and may be promoted to a
candidate only if a harm can be named.

**LA-7 — Extraction patterns.**
Capture complete output to a file first; never pipe the run through a
filter at capture time.

- Plans only: `awk '/^Intent:/,/^Outputs:/' <log>`
- Answers only: `awk '/^PROMPT: /{p=1} p' <log>`
- Signatures: `grep -nE '^(ERROR:|Reason:|Refusal|Traceback|KeyError|no plan|error|HDFE|finite)' <log>`
- Header + first answer line + truncation per prompt: `awk '/^PROMPT: /{p=1; print "---"; print} /^Answer:/{print; getline; print} /^Reason:/{print} /^Truncation:/{getline; print}' <log>`
- Set map across all sets: a `for` loop producing prompts / refusals /
  truncations / prompt list.

Prefer header + truncation for the initial pass; drop into full `cat`
only for a specific prompt when the header is not enough to classify.

**LA-8 — Watchlist of failure shapes.**

- Empty data behind confident prose.
- A page count stated as a total.
- A computation over a truncated sample stated as fact.
- Customer-scoped results that never resolve an `AccountNumber`.
- A generalisation true of the first few rows but not the set.
- A list-shaped answer with no `Showing N of M` and no `Truncation:`
  line.
- A count computed over the sample rather than over the full set (the
  F-010 shape).
- Two prompts of the same shape that plan differently (one filters, one
  does not).

**LA-9 — Cross-set consistency.**
Same prompt in two sets should behave the same. When it does not, that
is a candidate until proven otherwise. Same for the same idempotent
query across tiers.

**LA-10 — Known mechanisms.**
Maintain a list per run. For `20260925_150333 smoke`: `F-052`
(confirmed at signature level) and `HDFE finite` (signature undefined,
TODO). Add a mechanism to the plan file when confirmed.

**LA-11 — The plan template.**
The reusable plan lives at `docs/audit/SPIRE_log_analysis_plan.md`. It
carries the parameter block, step order, signature patterns,
classification table shapes, review gate, severity-and-confidence
extension, and the priority-reorder log. Read it before starting a new
run; update it when a new mechanism or a new recording shape is found.

**LA-12 — Slow commands.**
Name the cost before handing a command over. A full `cat` of a log can
be large; a set extraction is instant. Prefer the smallest read that
answers the current question.

**LA-13 — Review gate.**
Analysis ends here. Bring the candidate list, the S0–S11 walk per
candidate, and blast-radius findings. Decide together: log as new
F-NNN, link to existing, or close-as-not-a-bug. Priority is decided.
Stop. Do not propose fixes at the gate.

**LA-14 — Working example.**
The `20260925_150333 smoke` run is the first full application. Its
artifacts live at `docs/audit/log_analysis_sessions/20260925_150333_smoke/`.
Its handoff is `docs/plan/HANDOFF.md` Section B. Its next-window steps
are in `_next_window.md`.

---

*End of working style.*
