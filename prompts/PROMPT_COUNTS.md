# Prompt counts

Snapshot taken 2026-10-10 on `hardening-master-v3`, after the folder-prefix rename (PR #194).

A count is the number of non-blank, non-comment lines in a file. A prompt that appears in more than one tier file of a folder is counted each time.

## Capability folders

| Folder | Smoke | Verify | Exhaust | Total |
|---|---:|---:|---:|---:|
| child_as_root | 5 | 30 | 95 | 130 |
| columns | 5 | 34 | 55 | 94 |
| date_filters | 8 | 47 | 107 | 162 |
| dipstick | 6 | 10 | 22 | 38 |
| fields_and_include | 3 | 15 | 40 | 58 |
| lifecycle | 5 | 31 | 59 | 95 |
| modes | 4 | 40 | 96 | 140 |
| payables | 6 | 28 | 62 | 96 |
| payables_procurement | 2 | 20 | 53 | 75 |
| payables_supplier | 2 | 3 | 44 | 49 |
| procurement | 5 | 35 | 72 | 112 |
| procurement_supplier | 2 | 22 | 44 | 68 |
| receivables | 6 | 35 | 106 | 147 |
| refusals | 4 | 28 | 73 | 105 |
| supplier | 6 | 36 | 61 | 103 |
| truncation | 4 | 14 | 42 | 60 |
| **Total** | **73** | **428** | **1,031** | **1,532** |

## Other sets

| File | Count |
|---|---:|
| refusals/refusals_refusal_examples.txt | 20 |
| release_gate/release_gate_litmus.txt | 10 |
| rerun/rerun_01_failed.txt | 63 |
| retest/retest_prompts.txt | 17 |
| scorer/scorer_parser_stress.txt | 68 |
| scorer/scorer_tool_selection.txt | 24 |
| sme/sme_testcases.txt | 34 |
| **Total** | **236** |

Grand total across both tables: **1,768**.

## Notes

- `scorer/` files use the EXPECT / pipe-separated format and `sme/` is the external corpus, so their figures are line counts and may not equal prompt counts.
- `rerun/` is not tracked in git, so its count reflects one local working copy.
- `release_gate/release_gate_baseline.md` and `supplier/supplier_t_log_analysis_src.txt` are not counted.

## How to regenerate

Run from the `prompts/` folder:

```bash
grep -vcE '^\s*(#|$)' */*.txt | column -t -s:
```
