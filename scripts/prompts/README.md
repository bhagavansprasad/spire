# Spire prompt sets

## Layout

```
scripts/prompts/
  00_dipstick.txt          6    fast depth-ordered triage — run this first
  01_supplier.txt         38    supplier-rooted
  02_purchase_order.txt    9    PO-rooted
  03_ar.txt               15    accounts receivable
  04_columns.txt           8    column selection (WORKS as of 2026-07-24)
  05_refusals.txt         10    out-of-scope, consolidated
  06_slow.txt             16    edge filters + aggregations (minutes each)
  07_alacarte.txt         14    column-feature regression (run_graph path)
  scorer/
    parser_stress.txt     60    EXPECT ||| format — SCORER ONLY
```

Roughly 115 runnable prompts, down from ~160 before deduplication.

`00_dipstick` and `07_alacarte` are both fast and both worth running first:
dipstick samples the whole pipeline by depth; à la carte drills the
column-output feature (table, address flatten, graceful overrun, and the
paths that must stay unchanged).

## Two formats — do not mix them

`00`–`06` are plain prompts, one per line, for `run_prompt_set.py`.

`scorer/parser_stress.txt` uses `EXPECT ||| prompt` and needs the scorer.
Feeding it to `run_prompt_set.py` sends the `filter:status |||` prefix to
the parser as part of the prompt. It lives in a subfolder for that reason.

## Running

Quick verification (about 3 minutes):

```
python scripts/run_prompt_set.py --prompt-file scripts/prompts/00_dipstick.txt
```

Full run excluding the slow set:

```
for s in 00_dipstick 01_supplier 02_purchase_order 03_ar 04_columns 05_refusals 07_alacarte; do
  echo "########## $s ##########"
  python scripts/run_prompt_set.py --prompt-file scripts/prompts/$s.txt
done > run_$(date +%Y%m%d).txt 2>&1
```

Everything, overnight:

```
nohup bash -c '
for s in 00_dipstick 01_supplier 02_purchase_order 03_ar 04_columns 05_refusals 07_alacarte 06_slow; do
  echo "########## $s ##########"
  python scripts/run_prompt_set.py --prompt-file scripts/prompts/$s.txt
done' > overnight_$(date +%Y%m%d).txt 2>&1 &
```

The MCP server must stay up for the duration. If it is running in a
foreground terminal you plan to close, background it too.

## Reading the results

**The summary line proves nothing.** `run_prompt_set.py` has previously
reported "38/38 ran cleanly" while several prompts were being wrongly
REFUSED. Read the ANSWERS.

Score each prompt into one of three buckets:

- **pass** — right rows, right claims
- **fail** — errored, refused when it should not have
- **wrong but did not error** — the one that matters

For the third bucket, check specifically:

- an empty data array behind confident narrative prose
- a page count stated as a total ("25 suppliers" where 421 exist)
- claims about fields absent from the displayed projection
- arithmetic in the narration that is not in the rows
- customer-scoped results that never resolve an AccountNumber
- a generalisation true of the first few rows but not the set

## Order matters

`00_dipstick` is depth-ordered on purpose. If depth 2 fails, the filter
layer is broken and every later failure is probably downstream of it.
Run it first and read it first.

## What was removed in the 2026-07-24 reorganisation

- `03_test_prompts_failed.txt` — a re-test of a fix that landed sessions
  ago. Spent.
- `02_test_prompts_e2e.txt` — merged into `01_supplier.txt`; the unique
  paraphrase variants and collision traps were kept, the duplicates
  dropped.
- `spire_v1_2_review_prompts.txt` — merged. Its column-selection section
  became `04_columns.txt`; the rest duplicated the supplier set.
- One of three near-identical spend aggregations. They exercise one code
  path at ~2 minutes each.

## What changed 2026-07-24 (column feature)

- Column selection now works on the `run_graph` path. When a prompt names
  columns, the output is an aligned table of exactly those columns; the
  synthesizer summary prints above it. `04_columns.txt` was flipped from a
  failure-capture set to a verification set.
- Nested addresses flatten to an Address column.
- A synthesizer token-cap overrun is caught (DegenerateOutputError) and the
  table prints alone instead of the run aborting.
- `07_alacarte.txt` added as the regression set for all of the above.
- KNOWN follow-up: the address query still runs the synthesizer only to
  discard its overrun output (~25K wasted tokens). Skipping the synthesizer
  for column-only queries is the next optimisation, not yet done.
