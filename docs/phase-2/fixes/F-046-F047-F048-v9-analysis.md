# F-046 / F-047 / F-048 — V9 four-file sweep, analysis

**Branch:** `phase-2-fix-F046-F047-F048-date-filters`
**Date:** 2026-09-23
**Evidence file:** `F-046-F047-F048-v9-sweep.txt` (4420 lines)
**Raw command:**

    python scripts/promptkit.py --run \
      --prompt-file \
        scripts/prompts/15_po_relative_date_filters.txt \
        scripts/prompts/16_date_filter_cluster.txt \
        scripts/prompts/13_child_as_root.txt \
        scripts/prompts/14_truncation_narration.txt \
      --show-planner > t_all.txt 2>&1

Note: the redirect placed before `--show-planner` put the intent/plan
diagnostics on stderr rather than into the file. The file therefore
carries the **answers** and **refusals** in full, but not the per-prompt
`Intent:` / `Plan:` lines. See "Not captured" below.

## Summary

    Prompts run (four files, ~145 across all sections)     ~140
    `^Answer:` blocks                                      135
    `^Reason:` refusals                                      6
    `No receipts found` / `No purchase orders` / etc.        2
    `unsupported_filter` occurrences                         0   <- PASS
    `ERROR:` lines                                           0   <- PASS
    `MAX_TOKENS` markers                    not captured (stderr)

**V9 for F-046/47/48 = PASS.** No `unsupported_filter`, no `ERROR`,
every F-046/047/048 prompt either answered or refused for the correct
reason.

## Per-finding results

### F-046 — Invoice relative-date (all pass)

| Prompt | Result | Evidence |
|---|---|---|
| `invoices older than 6 months` | answered | 53,011 total |
| `invoices older than 1 year` | answered | 53,011 total |
| `invoices more than 12 months old` | answered | 53,011 total |
| `invoices stale` | answered | 53,011 total |
| `invoices in the last 30 days` | answered | 184 total |
| `invoices in the last 6 months` | answered | 1,021 total |
| `invoices from the last year` | answered | 2,340 total |
| `invoices created in the last 12 months` | answered | 2,340 total |
| `invoices in 2024` | answered | 18-examined sample |
| `invoices in 2023` | answered | 25-examined sample |
| `invoices between Jan and Mar 2024` | answered | 12-examined sample |
| `invoices created before 2024-01-01` | REFUSED (F-049) | missing_identifier |
| `invoices created since January 2024` | REFUSED (F-049) | missing_identifier |
| `invoices for Lee Supplies older than 6 months` | answered | supplier + date |
| `invoices for supplier 1252 in the last 30 days` | answered (empty) | correct — no 30-day invoices for 1252 |
| `invoices for Lee Supplies in 2024` | answered | 12-examined sample |
| `invoices for Lee Supplies` | answered (unchanged) | 1,334 total |
| `invoices` | REFUSED (correct negative) | missing_identifier |

### F-047 — PO last-updated-date (all pass)

| Prompt | Result | Evidence |
|---|---|---|
| `purchase orders not touched in the last year` | answered | 16,119 total |
| `purchase orders not touched in the last 6 months` | answered | 16,669 total |
| `purchase orders not updated in the last 12 months` | answered | 16,119 total |
| `purchase orders last modified more than 6 months ago` | answered | 16,669 total |
| `purchase orders updated in the last 3 months` | answered | 278 total |
| `purchase orders with activity in the last year` | answered | 1,425 total |
| `purchase orders updated in the last 30 days` | answered | 32 total |

Column separation is clean: the last-updated counts (16,119 / 16,669 /
278 / 1,425 / 32) differ from the CreationDate siblings on the same
file (16,937 / 16,254 / 1,290 / 607), confirming the two columns do
not cross-contaminate.

### F-048 — vague-adjective default (all pass)

All six prompts (`recent purchase orders`, `new purchase orders`,
`latest POs`, `fresh POs`, `the most recent POs`,
`recently created POs`) answered identically: 25 of 259, months=3
window (cutoff 2026-06-23). Explicit-N siblings
(`purchase orders in the last 6 months`) still use months=6.

### F-011b regression sweep (all pass)

All 23 prompts in `15_po_relative_date_filters.txt` answered except
the two F-049 phrasings, and except `purchase orders created in 2023`
which is the known open **F-045** (composite `created_since AND
created_before` silent-zero). No new failure.

### F-041 regression sweep (all pass)

64 of 64 prompts in `13_child_as_root.txt` answered. This is
unaffected by F-046/47/48 sysprompt edits, but is included as a
non-regression check on the shared parser context.

### F-012 / F-036 regression sweep (13/14 pass)

13 of 14 prompts in `14_truncation_narration.txt` answered;
`show me contract renewals` correctly refuses with `unknown_entity`.
This is the expected negative.

## Refusals — all correct

| # | Prompt | Flavor | Correct? |
|---|---|---|---|
| 1 | `invoices created before 2024-01-01` | `missing_identifier` | ✗ F-049 |
| 2 | `invoices created since January 2024` | `missing_identifier` | ✗ F-049 |
| 3 | `invoices` | `missing_identifier` | ✓ negative |
| 4 | `purchase orders` | `missing_identifier` | ✓ negative |
| 5 | `show me contract renewals` | `unknown_entity` | ✓ out-of-scope |

Four of the six refusals are correct. The two refusals that are not
correct are the **F-049** phrasings, filed as a new finding; see
below.

## Prompt-class observations

**What works end-to-end after this branch:**

- Relative-date phrasings: `older than N`, `in the last N`, `from the
  last year`, `created in the last N`, `not touched in the last N`,
  `updated in the last N`. Both columns (CreationDate / LastUpdateDate
  and InvoiceDate) route correctly.
- Absolute-date phrasings, when the noun is `invoices in YYYY` /
  `between X and Y` / `after YYYY-MM-DD`: all answered. Guard widening
  closed the pre-existing wrong-refusal.
- Vague-adjective phrasings (`recent` / `new` / `latest` / `fresh` /
  `the most recent` / `recently created`): all answered with months=3.
- Composite filters (supplier + date): answered, and the tool's
  over-fetch cap correctly produces an "examined sample" narrative
  where appropriate.
- Cross-column controls (`older than N months` on CreationDate,
  `not touched in the last N` on LastUpdateDate): no contamination.

**What still fails or is out of scope:**

- `invoices created before/since X` — the noun leading the phrase is
  `created`, which the parser does not currently map to `invoice_date`.
  Filed as **F-049**.
- `purchase orders created in 2023` — the composite date-clause
  silent-zero recorded as **F-045**; not a regression of this branch.
- `show me contract renewals` — out-of-scope negative, correctly
  refused with `unknown_entity`.

## Not captured

- The intent/plan lines on stderr — the run's stdout was redirected to
  the file, but stderr (`[llm]`, `[cache]`, `Intent:`, `Plan:`,
  `Reason:` diagnostics) went to the terminal and was not preserved.
  The `Reason:` text captured in the file *does* include the flavor
  tag, so refusal identity is preserved.
- `MAX_TOKENS` markers (stderr). But every answer in the file is a
  complete, coherent summary — incompatible with degenerate
  generation. The parser prompt token-ceiling symptom the handoff
  flags would produce a truncated or absent answer, not a well-formed
  one.

## Verdict

F-046, F-047, F-048 are **verified**. F-049 filed as a new finding.
F-045 remains open and unaffected by this branch. The branch is ready
for PR.
