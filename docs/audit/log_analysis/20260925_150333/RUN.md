# 20260925_150333 smoke - round index

Read-only analysis. On-disk files are the source of truth. Chat is not.
If the window dies, resume from `20260925_150333_smoke/_index.md`.

## Round parameters

- tier: smoke
- run_root: overnights/20260925_150333/
- manifest: scripts/manifests/smoke_sets.yaml
- expected_set_count: 16
- known_mechanisms: F-052, HDFE finite
- fixes_under_test: F-001, F-007, F-008, F-010, F-012, F-015
- forbidden_inputs: overnights/03_verify_sets/

## Exit codes

- payables/smoke      exit 1   79s
- procurement/smoke   exit 1   60s
- truncation/smoke    exit 1   48s
- other 13 sets       exit 0

## Set map (16 sets, 71 prompts)

| set | prompts | refusals | trunc | exit | status |
|---|---|---|---|---|---|
| refusals | 4 | 3 | 1 | 0 | done |
| payables | 6 | 1 | 5 | 1 | done |
| procurement | 5 | 1 | 1 | 1 | done |
| truncation | 4 | 1 | 3 | 1 | done |
| payables_supplier | 2 | 0 | 2 | 0 | pending |
| procurement_supplier | 2 | 0 | 2 | 0 | pending |
| payables_procurement | 2 | 0 | 0 | 0 | pending |
| columns | 5 | 1 | 4 | 0 | pending |
| fields_and_include | 3 | 0 | 1 | 0 | pending |
| modes | 4 | 0 | 0 | 0 | pending |
| date_filters | 6 | 0 | 5 | 0 | pending |
| lifecycle | 5 | 0 | 0 | 0 | pending |
| child_as_root | 5 | 0 | 0 | 0 | pending |
| dipstick | 6 | 1 | 1 | 0 | pending |
| supplier | 6 | 1 | 2 | 0 | pending |
| receivables | 6 | 1 | 1 | 0 | pending |

Per-set detail: see `20260925_150333_smoke/<set>.md`.
Candidates:   see `20260925_150333_smoke/_candidates.md`.
Action items: see `20260925_150333_smoke/_action_items.md`.
