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

## Deferred items

16. **`personas.yaml` untrack (task 1.1) — deferred.** Handled at the
    end of the plan. Not recorded as a deviation anywhere.

17. **Integration tests (the 22 marked `integration`) — deferred.** Not
    run, not investigated, not fixed during Phase 1.

## Dev / runtime separation

18. **Runtime clone at `~/pocs/spire-runtime` is never disturbed.**
    Ports 3333/8000/8888. Testers reach it via ngrok.

19. **Dev tree at `~/pocs/spire` uses 4444/9000/9999.** Set via
    `.spire-dev.env` (gitignored). Runtime never sees this file, so it
    stays on defaults.

20. **No promotion script.** Runtime updates are manual, deliberate,
    rare — `git fetch && git reset --hard` in the runtime tree.

## Auth

21. **No auth at the tunnel or app layer.** When auth lands, SPIRE owns
    it. Do not add an extra module in front.

## Reply discipline

22. **Short, plain, no preamble.** Skip "Great question!" and similar.
    Answer, then stop.

23. **Ask before assuming.** If something is ambiguous and the answer
    changes what you produce, ask — but ask once, concisely.

24. **No re-litigating resolved points.** If the answer was given in a
    prior turn, use it.

---

*End of working style.*