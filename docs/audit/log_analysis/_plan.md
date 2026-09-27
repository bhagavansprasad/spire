# SPIRE Log Analysis Plan — Template

> Read-only analysis. No code fixes. No findings-log writes. No repo changes.
> Surface candidates, then stop and ask before logging or planning fixes.
> Modify this document as new issues, signatures, or priorities are found.

---

## 0. Round parameters

Fill these in before reading any logs.

```yaml
tier:                 smoke | verify | exhaust
run_root:             overnights/<run_id>/
manifest:             scripts/manifests/<tier>_sets.yaml
expected_set_count:   <N>
known_mechanisms:     [F-052, HDFE finite, ...]
fixes_under_test:     [F-001, F-007, F-008, F-010, F-012, F-015]
forbidden_inputs:     [overnights/03_verify_sets/]
previous_round:       <run_id or none>
```

---

## 1. Scope lock and input check

Purpose: make sure the analysis is valid before reading answers.

Do:

- Confirm `run_root`, tier, manifest, and expected set count.
- Confirm required artifacts exist:
  - `_manifest.yaml`
  - `_run_log.txt`
  - `_summary.log`
  - per-set `<set>.log`
  - per-set `<set>.txt`
  - per-set `<set>_summary.log`
- Confirm no in-progress or forbidden run is being read.

Gate: if expected files are missing or mixed, stop and report missing inputs.

Output: structural pass/fail and file inventory.

---

## 2. Structural integrity

Purpose: catch incomplete or mixed runs before interpreting answers.

Do:

- Verify set count matches the manifest.
- Verify every set folder has the expected log/txt/summary triad.
- Verify `_run_log.txt` start/end timestamps are consistent.
- Verify `_summary.log` set list matches the manifest.

Output: set-count table and any missing/extra sets.

---

## 3. Exit-code triage — first analytical priority

Purpose: find hard failures and known exit-code artifacts first.

Do:

- Read `_summary.log` and `_run_log.txt`.
- List every set with `exit != 0`.
- Record set name, exit code, seconds, and status text.
- Separate `exit 1` from other non-zero exits.

Why first:

- Exit codes are objective and cheap to read.
- They narrow the search to sets most likely to contain real failures.
- They directly test known mechanisms such as F-052.
- Semantic answer classification is expensive; do not start there
  until you know which sets failed mechanically.

Output: exit-code anomaly table.

```text
set                exit  secs  status
<set>/<tier>       <n>   <n>   <status>
```

---

## 4. Signature extraction for non-zero sets

Purpose: identify the failure mechanism before reading full answers.

Do:

- For each non-zero set, grep its log for:
  - `^ERROR:`
  - `^Reason:`
  - `Refusal`
  - `Traceback`
  - `KeyError`
  - `no plan`
  - `error`
  - `HDFE`
  - `finite`
- Count signatures.
- Compare the signature pattern to known mechanisms.

### Known mechanism: F-052

Expected signature:

- `^ERROR: 0`
- `^Reason: <n>`
- Refusal rendered
- No `ERROR` banner
- Execution never succeeded

Mechanism (for reference):

1. `plan_node` `except RefusalError` returns `{"refusal": ...}` only.
2. Edge after plan is `_continue_or_end`, which returns `"end"` only when
   `error` is set. A `refusal` does not short-circuit.
3. `execute_node` runs, does `state["plan"]` on a state with no plan,
   raises `KeyError`, is caught by the blanket `except Exception`, and
   writes error.
4. State now carries BOTH refusal and error.
   `_emit_run_graph_output` checks refusal first, prints the refusal,
   returns — no `ERROR` banner ever emitted.
5. `_run_async` counts `error and not plan_refusal` as a failure. Exit 1.

Answers are correct. Only the exit code is wrong.

Fix location (not applied): widen `_continue_or_end` to end on refusal
too, or add a dedicated `_after_plan` edge.

### Known mechanism: HDFE finite

Status: `TODO: define signature and mechanism`.

Do:

- Grep non-zero logs for `HDFE` and `finite`.
- Record file, line, and surrounding context.
- Determine whether it is:
  - a plan-time refusal
  - a runtime error
  - a silent wrong answer
  - a data-shape issue
- Add the confirmed signature back into this section.

Output: signature table per non-zero set.

---

## 5. Prompt-level classification for all sets

Purpose: classify every prompt, not just the failed sets.

Do:

- Read every prompt and answer.
- Classify each prompt as:
  - `pass` — right rows, right claims
  - `fail` — errored, or refused when it should not have
  - `wrong-but-no-error` — reads correctly but says something false

Watch specifically for:

- empty data behind confident prose
- a page count stated as a total
- a computation over a truncated sample stated as fact
- customer-scoped results that never resolve an `AccountNumber`
- a generalisation true of the first few rows but not the set

Output: per-prompt classification table.

```text
set              prompt                       class
<set>/<tier>     <prompt>                     pass | fail | wrong-but-no-error
```

---

## 6. Known-fix regression cross-check

Purpose: confirm previously fixed findings have not regressed.

Do:

- For each known F-number with a reproducer in this tier, locate the
  reproducer prompt.
- Compare observed behavior to expected fixed behavior.
- Note any regression.

Example mapping:

```text
F-001  list_all flag on explicit PO list
F-007  empty requested child acknowledgement
F-008  expired supplier classification
F-010  filtered count over the matched bucket
F-012  truncation sample sentence
F-015  empty bucket truncation acknowledgement
```

Output: regression table.

```text
F-NNN  reproducer prompt              expected        observed        regression
```

---

## 7. Candidate findings list

Purpose: surface candidates without logging or fixing.

Format per candidate:

```text
file:   <folder>/<name>.log
prompt: <the prompt>
class:  pass | fail | wrong-but-no-error | regression
note:   <one sentence>
```

Rules:

- Do not log anything.
- Do not propose fixes.
- Surface, then stop and ask.

Output: candidate findings list.

---

## 8. Review gate

Purpose: decide together what to log and in what order.

Do:

- Review candidate list.
- Decide which candidates are real findings.
- Decide order.
- Decide whether a fix plan is warranted.

Stop until that decision is made.

---

## 9. Severity and confidence (next level)

Add once the basic plan is stable.

```text
severity:    blocking | misleading | cosmetic
confidence:  confirmed-by-reproducer | suspected | observation
clustering:  same root cause across multiple sets
trend:       compared to previous batch
gate:        S0–S8 (WORKING_STYLE.md), S1 is the gate: no harm, no F-NNN
fix-map:     finding -> code location
```

---

## 10. Open items and priority reorder log

Keep a running record so priorities can be reordered as new issues surface.

```text
date         item                       action
2026-09-25   add HDFE finite check      TODO: define signature
```

---

## 11. Working-style rules (carry forward)

- One command at a time. Wait for output. Then next.
- Every file edit is two cells: a Python script that reads / verifies /
  replaces / writes, then shell commands that read the file back.
  Never blended.
- Capture complete output to a file, then grep from the file. Never pipe
  a run through a filter at capture time.
- Name a slow command's cost before handing it over.
- Every finding walks S0–S8 (WORKING_STYLE.md). S1 is the gate: no harm,
  no F-NNN. An observation is not a bug.
- Reproduce before you plan. A finding whose reproducer no longer fires
  is closed-as-not-a-bug; a finding whose reproducer still fires is the
  next fix.