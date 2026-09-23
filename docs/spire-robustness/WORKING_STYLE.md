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

10. **Integration branch is `hardening-master`.** All phase branches
    spawn off it and merge back via PR. The runtime clone pulls from
    `hardening-master`.

    **Nothing merges to `master` without explicit instruction from
    the user.** Not a PR, not a fast-forward, not a one-off doc fix.
    The only merge target is `hardening-master`; the only merges are
    PR branches into it. `master` stays where it was at the fork
    point until the user says otherwise — and the user's word on
    this is the only trigger.
11. **Branch naming: `Phase{N}-{Descriptive}`.** Examples:
    `Phase1-Audit-and-Baseline`, `Phase2-Correctness-Fixes`. Not
    `phase-1`.

## Documentation structure

12. **Doc A is frozen.** No design edits, no phase renumbering, no
    reordering. Status and deviation notes only.

13. **Doc B is split:**
    - `00_Doc_B_Index.md` — snapshot, registers, test taxonomy, session
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

    **And every pasteable edit ships with its verification commands.**
    When handing over a block for the user to search-and-replace into a
    document, include the two or three commands that confirm:
    - the anchor was unique before the paste (a `grep -c` on the anchor,
      expecting `1`);
    - the anchor is intact after (a `grep -n` on the anchor and the
      lines below it);
    - the file's sentinel — its end-marker, its newest-entry header —
      is still unique.

    Paste-and-verify is one motion, not two. The user runs the commands
    and reports back; the finding is not considered landed until the
    verification output has been seen.

## Evidence standard for findings (S0–S8)

Before anything is written into a findings log as a bug, the claim
walks through S0–S8 in order. If a step fails, the claim stops at that
step and is classified accordingly. The point is not caution for its
own sake — it is that a wrong finding costs as much as a missed one,
because a later session acts on it.

**S0 — State the claim in one sentence.**
Either "X is a bug" or "X is not a bug." No other forms. "X looks
wrong," "X is drift," "X is odd" are hunches. Hunches live in
conversation; they do not enter a document.

**S1 — Name the harm.**
A bug is a harm. Pick exactly one:
  - wrong data returned
  - wrong narration (data right, words wrong)
  - crash
  - refusal of an in-scope prompt
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

**S4 — Disprove the alternative.**
Name one alternative explanation and show it is not the cause. Common
ones:
  - the pod data changed between runs
  - a different code path was actually taken
  - the diagnostic is lying; the pipeline is fine
  - it is by design (read the design doc first)

If no alternative can be named, the cause has not been isolated.

**S5 — Name the falsifier.**
If someone said "no, this isn't a bug," what one command would prove
them right? If no such command can be named, the claim is not
falsifiable and cannot enter the log.

**S6 — Classify.** Only now write the F-NNN entry:
  - **Confirmed** — S1–S5 all passed.
  - **Candidate** — some steps failed; note which.
  - **Observation** — S1 failed; goes as a note under a related
    finding, not its own entry.
  - **Closed-as-not-a-bug** — a prior claim disproven by stronger
    evidence; cite the old entry ID.

**S6-notes — the two `closed-as-not-a-bug` shapes.**

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

**S7 — Cross-link.**
Every entry cites at least one §A / §B / §D row or another F-NNN.
Orphan entries get re-checked before the next session.

**S8 — List what was NOT checked.**
Explicit. This is what a future session reads to decide where to look
next. "Nothing else was checked" is a valid and useful entry.

**Nondeterminism claims need N≥20.** A claim that a prompt behaves
differently across runs is not falsifiable from one observation or
seven. Twenty runs of the same prompt, same invocation, is the
threshold. Report the raw pass/fail shape across the N; a rate as high
as ~14% is not formally excluded by 20 clean runs, but the audit's
own threshold is N≥20 and empirical clean results at that N are a
closed finding, not a suspended one.

**The contract.** Every time an F-NNN is proposed, the steps S0–S8 are
walked in order and it is shown which passed. Any time the question
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

## Deferred items

16. **`personas.yaml` untrack (task 1.1) — deferred.** Handled at the
    end of the plan. Not recorded as a deviation anywhere.

17. **Integration tests (the 22 marked `integration`) — deferred.** Not
    run, not investigated, not fixed during Phase 1.

## Dev / runtime separation

18. **Runtime clone at `~/pocs/spire-runtime` is never disturbed.**
    Ports 3001/3002/3003. Testers reach it via ngrok.

19. **Dev tree at `~/pocs/spire` uses 4001/4002/4003.** Set by the
    `spire()` shell function from `SPIRE-PORTS.env`. The two sets are
    `X00Y`, X=3 for runtime and 4 for dev.

20. **The `spire.sh --dev | --runtime` flag is required.** There is
    no default mode. `SPIRE_MODE` is set by `spire()` / `spirer()` in
    `~/.bashrc`. `--status` and `--stop` are scoped to the current
    mode and never touch the other tree's ports.

21. **No promotion script.** Runtime updates are manual, deliberate,
    rare — `git fetch && git reset --hard` in the runtime tree.

## Auth

22. **No auth at the tunnel or app layer.** When auth lands, SPIRE owns
    it. Do not add an extra module in front.

## Reply discipline

23. **Short, plain, no preamble.** Skip "Great question!" and similar.
    Answer, then stop.

24. **Ask before assuming.** If something is ambiguous and the answer
    changes what you produce, ask — but ask once, concisely.

25. **No re-litigating resolved points.** If the answer was given in a
    prior turn, use it.

26. **After every bug fix, report the queue.** State how many rows
    remain pending in `docs/phase-2/FIX_PLAN.md` and name the next
    one being picked up. This runs after every closure — a fix, a
    `closed-as-not-a-bug`, a merge with its tracking flip — and it
    appears in the same reply that delivers the closure news, before
    the next task's commands. The user should never have to ask
    "what's next?"; that question is answered proactively.

---

*End of working style.*