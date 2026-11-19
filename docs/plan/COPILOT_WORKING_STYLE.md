# SPIRE — Copilot Working Style

Self-contained working style for GitHub Copilot in VS Code. It states
the Copilot-specific behavior rules and records the project's durable
conventions in full, so it does not depend on `WORKING_STYLE.md` (which
may eventually be retired). Where both exist, this file governs Copilot
sessions.

---

## Part A — Copilot-specific behavior rules

1. **Do not modify files until asked.** Default to read-only. Explore,
   explain, and propose — never edit, create, or delete a file without
   an explicit go-ahead.

2. **Explain before modifying.** Before any change, state what will
   change and why, then wait for approval.

3. **Keep answers short.** Answer the question, then stop. No preamble,
   no extra background, no "consider also" — unless the user asks a
   specific follow-up question.

4. **Ask once when ambiguous.** If the answer changes what you produce,
   ask — once, concisely. Do not re-litigate resolved points.

---

## Part B — Editing mechanics (VS Code native tools)

Copilot edits files directly and has a shared terminal, so there are no
paste cells and no copy/paste to corrupt. The guarantees of a
paste-and-verify workflow still apply to every edit:

- **Old block present before** the edit (read the file first).
- **Text actually changed.**
- **Old block absent after** the edit.
- **New block present after** the edit.

Copilot runs these checks itself (via `grep` / `git diff`) and shows the
evidence, rather than asking the user to run a second cell.

---

## Part C — Project conventions

### Context and communication

- **Read source directly.** Copilot reads files in the workspace
  directly — no need to assemble a context bundle first. Use
  `build_context.py` (`--files ...`) only when a diagnostic needs a
  persistent on-disk record of its code + evidence, not as the way to
  read code.
- **One logical step at a time.** Split on uncertainty, not on command
  count. Run one command, read the output, then the next.

### Branching and merging

- **Branch-first** for code, features, tooling, and bug fixes. Docs may
  go direct or ride a branch.
- **PR-based merges always.** Integration branch is `master`. No local
  merge into `master`.
- **Branch naming:** `Phase{N}-{Descriptive}` (e.g.
  `Phase1-Audit-and-Baseline`).

### Documentation

- Doc A is frozen (status/deviation notes only). Doc B is split into
  `Doc_B_Index.md` + per-phase `NN_Phase_NN_Name.md`.
- Audit rows close in place. The findings log is append-only;
  corrections are new entries, nothing is deleted.
- Every window opens with a ledger reconciliation: list recently merged
  PRs and grep `FIX_PLAN` for `fixed` rows still not flipped to
  `verified`.

### Evidence and findings

- **Every claim needs a command and its output.** No output = not
  evidence.
- **Capture complete stdout+stderr to a file, then grep the file.**
  Never pipe the run itself through a filter at capture time.
- **Name a slow command's cost before running it.** If wall-clock may
  exceed ~30s, say so with a rough figure and why.
- **Emitted SQL must be validated by execution, not just inspection.**
  After the SQL emitter produces SQL, run it against the pod with
  `./runsql.sh "<SQL>"` and confirm it (a) executes (exit 0) and (b)
  returns the **same values as Spire's own REST answer** for that prompt.
  SQL and REST must agree; "the SQL executes" is not enough — "the SQL
  agrees with the REST answer" is the standard. This is how the
  F-060 stub-column defect (a column that exists but is NULL) was caught.
- **Column existence ≠ column populated.** A column present in
  `t_task2_all.txt` may still be NULL on every row (the R-7 stub-view
  shape at the column level). When a role is bound to a physical column,
  sanity-check population with a `COUNT(<col>)` / NULL-count, not just a
  presence grep.
- **Deferred test failures get an `xfail` + a `FIX_PLAN` note, not a
  silent ignore.** A failing test you are not fixing this window is marked
  `@pytest.mark.xfail(reason="... (FIX_PLAN §n)", strict=False)` and
  recorded in `docs/fixes/FIX_PLAN.md`. Do not delete or comment out the
  test.
- **Findings walk R then S0–S11 in order before any F-NNN entry.**
  - **R — reproduce** the prompt: run it, run it again, run the sibling
    that passed. Intermittent results need N≥20 runs before classifying.
  - **S0** — state the claim in one sentence ("X is a bug" / "X is not a
    bug").
  - **S1** — name the harm (wrong data, wrong narration, crash, refusal
    of an in-scope prompt, silent omission, cost regression,
    inconsistency between two paths). No harm = observation, not a bug.
  - **S2** — paste evidence (curl-verified > runtime output > static
    `file:line` > "I recall"; the last is not evidence).
  - **S3** — name the mechanism (the specific `file:line`/function that
    causes the harm).
  - **S4** — name the probable root cause (design decision, plan-template
    gap, parser-grammar gap, missing guard, stale assumption — or
    "mechanism known, root cause unknown").
  - **S5** — disprove one alternative explanation.
  - **S6** — name the falsifier (the one command that would prove it not
    a bug).
  - **S7** — classify: Confirmed / Candidate / Observation /
    closed-as-not-a-bug.
  - **S8** — the miss record (did a prompt of this shape exist? why did
    it not surface? what would have caught it?).
  - **S9** — cross-link to another entry.
  - **S10** — list what was NOT checked.
  - **S11** — coverage expansion: list sibling prompts of the same shape
    for the prompt-set tree.

### Dev/runtime

- How to run, start/stop/restart, and the port layout are in
  `Quick_how_to_run.md`. Dev uses 4001/4002/4003; production
  5000/5001/5002 (testers via ngrok), per `SPIRE-PORTS.env`.
- Restart the API/MCP server after any change under `src/spire/` —
  imports are cached at startup.
- **Python interpreter is `/home/bhagavan/virtenv/spire/bin/python`**, not
  bare `python`/`python3`. The bare interpreter lacks `oracledb`. Use the
  full path for `python`, `pip`, and `pytest`; `./runsql.sh` (Oracle via
  curl) does not need it.
- **`./runsql.sh "<SQL>"` is the pod-SQL validator.** It posts to the
  Fusion BI Publisher report and returns tabular rows. Use it to execute
  emitted SQL and check real data (credentials come from
  `IKS_FUSION_USERNAME`/`IKS_FUSION_PASSWORD`).

### Reply discipline

- Short, plain, no preamble.
- After every bug fix or closure, report the pending
  `docs/fixes/FIX_PLAN.md` queue and name the next row, before the next
  task.
- SME test: an SME-answerable refusal is a defect, not a coverage gap.

### Log analysis

- Read-only until the review gate; on-disk files are the source of
  truth; one set at a time; four classes per prompt (`pass` / `fail` /
  `wrong-but-no-error` / `regression`); the review gate stops before
  proposing fixes.
