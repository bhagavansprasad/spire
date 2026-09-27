
# SPIRE — Session Startup Checklist

**Follow in order when opening a new window.** For the *why* behind
each step, see `WORKING_STYLE.md`. This file is the procedure; that
file is the standard.

---

## Part A — Before the new window

**A1. Confirm the previous session is closed.**
- `git status` is clean (or only shows files you intend to keep).
- The previous session's commits are on origin (`git log --oneline -3`).
- The handoff (`docs/00-plan/HANDOFF.md`) was updated by the
  previous window.

**A2. Assemble the three attachment files.**
- `docs/00-plan/HANDOFF.md`
- `docs/01-audit/phase-1-audit.md`
- `docs/01-audit/findings-log.md`

Do **not** attach `source-tree.txt`, the golden files, or individual
source files. Regenerable or bundle-served.

**A3. Copy the opening prompt into the new window's first message,
alongside the three files.**

```
Read docs/00-plan/HANDOFF.md first — it describes the working
process. Then read docs/01-audit/phase-1-audit.md and
docs/01-audit/findings-log.md.

Begin with "First steps in the new window" at the end of the handoff.

For every paste you give me: one-line anchor + fenced block + the four
verification commands. I search-and-replace; you wait for my verification
output before proceeding.
```

---

## Part B — In the new window, first turn

**B1. Confirm ground truth.** Run these four; share the outputs.
- `git log --oneline -3`
- `git status`
- `python -m pytest -q` (expect 913 passed, 18 deselected — if
  different, the handoff's baseline is stale; note the discrepancy)
- Confirm the MCP server is up and the persona resolves to the pod
  named in the handoff

**B2. Confirm the handoff was read.** The new window should summarise
back, in 3–5 lines, the current state: which audit sections are closed,
which are drafted, which batches remain, which carry-forward items
are open. If any of that is wrong, stop and correct it before
proceeding.

**B3. Begin the handoff's "First steps in the new window"** — usually
the §C.5 confirmation greps (Batch 1) or the §E.4 branch-state checks
(Batch 2).

---

## Part C — The working loop

**C1. One command at a time.** Give one command; wait for its output;
then the next. Never a block. If a command fails mid-block, the rest
fire against an unintended state.

**C2. Ask for a bundle, never an individual file** — unless the file is
truly a single-file question. `context_bundles.yaml` defines the bundles;
the handoff names the five that matter for audit work.

**C3. Every finding walks S0–S8.** S1 is the gate: no harm, no F-NNN.

**C4. Every paste ships with verification.** When handing the user a
block for search-and-replace, include:
- the single-line anchor (unique);
- the fenced block (outer fence is `~~~` if the content contains ` ``` `);
- the four verification commands (`grep` for the anchor, `grep -c` for
  uniqueness, `sed -n` for the neighbourhood, `grep -c` for the
  end-marker).

**C5. Wait for the user's verification output** before starting the
next finding. A paste is not landed until the four commands pass.

**C6. Update the audit as rows close.** When a §B / §D / §H row is
closed, give the matching search-and-replace for the audit file, in
the same form as C4.

**C7. Commit at logical checkpoints.** One branch per phase; PRs into
long-lived branches; named `git add`, never `-A`; heredoc commit
messages for multi-paragraph summaries.

---

## Part D — Before closing the window

**D1. Update the handoff.** Overwrite `docs/00-plan/HANDOFF.md`
in place (no archive, no dated filename). Carry forward any items
still open from the previous handoff so nothing is lost.

**D2. Confirm the findings log is append-clean.** Newest at top,
end-marker unique.

**D3. Confirm the audit's row states match the day's closures.**
§B.6's map, §D.1's closure notes, §H.1's cross-references.

**D4. Commit and push.**
- Audit + findings log: one commit.
- Handoff + supporting docs: one commit.
- `git push`; confirm `HEAD` == `origin/<branch>`.

**D5. Decide the next window's name.** Pattern: `NN_SPIRE_<topic>`.
Keep it descriptive of the session, not of a specific finding range.

**D6. Assemble the next window's three files.** The handoff you just
wrote, plus the audit and the log.

---

## The one rule that matters most

**Do not batch.** One command, wait, next. The discipline is what makes
every finding reproducible and every paste verifiable. Every other rule
in this checklist is downstream of that one.
