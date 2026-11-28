# Copilot Instructions (SPIRE)

Auto-loaded at the start of every VS Code session. These rules govern
how Copilot works in this repository. The full rulebook lives in
`docs/plan/WORKING_STYLE.md` — read the relevant section when a rule
here is not enough.

## Behavior rules (apply always)

1. **Do not modify files until asked.** Default to read-only: explore,
   explain, and propose. Never edit, create, or delete a file without an
   explicit go-ahead from the user.

2. **Explain before modifying.** Before making any change, state what
   you will change and why, then wait for approval.

3. **Keep answers short.** Answer the question and stop. Do not add
   explanations, background, or "consider also" notes unless the user
   asks a specific follow-up question.

## Editing mechanics

- Use native file edits and the shared terminal. Do not produce heredoc
  paste cells (`python3 - <<'PYEOF'`) or pasteable code blocks.
- After editing, verify and show evidence: the new content is present,
  the old content is absent, and surrounding context is intact. Run the
  verification yourself (grep / git diff) and show the result.
- For a commit landing N files, edit and verify each file before the
  single commit; verify per-file, not per-commit.

## Durable project rules (from WORKING_STYLE.md)
- Integration branch is `master`. Code/features/tooling/bug fixes go on
  a branch named `Phase{N}-{Descriptive}`, then merge via PR. No local
  merge into `master`.
- Every claim needs a command and its output. Capture complete stdout
  and stderr to a file, then grep the file — never filter at capture
  time.
- Report the pending `docs/fixes/FIX_PLAN.md` queue after every bug fix
  or closure, before the next task.
- SME test: an SME-answerable refusal is a defect, not a coverage gap.

See `docs/plan/WORKING_STYLE.md` for the full rulebook.
