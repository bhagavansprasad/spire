# 20260925_150333 smoke - per-set folder index

## Resume protocol

If the chat window dies:

1. Read this file.
2. Read `_candidates.md` and `_action_items.md`.
3. Find the first set with status `pending` in the round index.
4. Continue extracting that set's answers with:
   awk '/^PROMPT: /{p=1} p' overnights/20260925_150333/<set>/smoke.log
5. Write the per-set file. Update this index. Move to the next set.
6. Do not depend on chat history.

## Files in this folder

- `_index.md`       - this file
- `_candidates.md`  - running candidate findings list
- `_action_items.md`- S0-S8 walk per candidate
- `<set>.md`        - one per analyzed set

## Set status

| set | file | status |
|---|---|---|
| refusals | refusals.md | done |
| payables | payables.md | done |
| procurement | procurement.md | done |
| truncation | truncation.md | done |
| payables_supplier | payables_supplier.md | done |
| procurement_supplier | procurement_supplier.md | done |
| payables_procurement | payables_procurement.md | done |
| columns | columns.md | done |
| fields_and_include | fields_and_include.md | done |
| modes | modes.md | done |
| date_filters | date_filters.md | done |
| lifecycle | lifecycle.md | done |
| child_as_root | child_as_root.md | done |
| dipstick | dipstick.md | done |
| supplier | supplier.md | done |
| receivables | receivables.md | done |

## Rules

- One file per set. Append to the set file as you learn more about that
  set. Do not rewrite history; add corrections under a `## Corrections`
  section at the bottom.
- `_candidates.md` is the only growing list. Each candidate has a stable
  ID like C-001, C-002, ...
- `_action_items.md` holds the S0-S8 walk per candidate.
- Do not write to the findings log from this window.
