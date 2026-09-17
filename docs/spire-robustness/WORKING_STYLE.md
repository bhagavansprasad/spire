# SPIRE — Working Style

**Reference for every session.** Read at the start of a new window.
Cross-references Doc B index §7.

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
   content to a separate file.

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
    spawn off it and merge back via PR. `master` stays frozen at the
    fork point until the entire v3.2 plan completes. The runtime clone
    pulls from `hardening-master`.

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

14. **Append-only.** Corrections are new entries referencing old IDs.
    Nothing is deleted.

15. **Every claim needs a command and an output.** If a command and its
    output cannot be pasted, it is not evidence.

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

**S7 — Cross-link.**
Every entry cites at least one §A / §B / §D row or another F-NNN.
Orphan entries get re-checked before the next session.

**S8 — List what was NOT checked.**
Explicit. This is what a future session reads to decide where to look
next. "Nothing else was checked" is a valid and useful entry.

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

20. **The `run-all.sh --dev | --runtime` flag is required.** There is
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

---

*End of working style.*