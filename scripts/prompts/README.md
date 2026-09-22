# Spire prompt sets

## Layout

Counts are runnable prompts — comments and blank lines excluded.
Measured 2026-07-31.

```
scripts/prompts/
  00_dipstick.txt            6   fast depth-ordered triage — run this first
  01_supplier.txt           40   supplier-rooted
  02_purchase_order.txt      9   PO-rooted
  03_ar.txt                 16   accounts receivable
  04_columns.txt             8   column selection (WORKS as of 2026-07-24)
  05_refusals.txt            9   out-of-scope, consolidated
  06_slow.txt               15   edge filters + aggregations (minutes each)
  07_alacarte.txt           12   column-feature regression (run_graph path)
  08_lifecycle.txt          31   PO lifecycle regression (Module 5)
  10_refusal_examples.txt   18   every example a refusal promises
  qa_testcases.txt          34   captured external QA prompts, verbatim
  README.md
  scorer/
    parser_stress.txt       60   EXPECT ||| format — SCORER ONLY
```

164 runnable prompts across `00`–`10`, or 198 counting `qa_testcases`.
`00`–`07` alone is 115, down from ~160 before the 2026-07-24
deduplication.

There is no `09_*`. The gap is deliberate spacing, not a missing file.

`00_dipstick` and `07_alacarte` are both fast and both worth running first:
dipstick samples the whole pipeline by depth; à la carte drills the
column-output feature (table, address flatten, graceful overrun, and the
paths that must stay unchanged).

## Known-good baselines

Where a set has a clean baseline, it is recorded here. A number below
means "nothing errored" — it is not a claim that the answers were right.
See *Reading the results*.

| Set | Baseline | Dated |
|---|---|---|
| `05_refusals.txt` | 9/9, every message rewritten | 2026-07-30 |
| `07_alacarte.txt` | 12/12 | 2026-07-24 |
| `08_lifecycle.txt` | 31/31 | 2026-07-30 |
| `10_refusal_examples.txt` | 18/18 — **all must answer** | 2026-07-30 |

`10_refusal_examples` is the one set where a refusal is unambiguously a
bug: every line is an example Spire offers to a user it has just declined.
A refusal there is a defect in `src/spire/nl_parser/capability.py`, not in
the file. `tests/test_nl_parser_capability.py` asserts the guidance tables
and this file cannot drift apart.

Conversely, in `05_refusals` a refusal is a **pass**. What is under test is
*how* it refuses — right flavor, no guessing at a nearby entity, and the
reason legible without reading past the first three lines.

In `08_lifecycle`, the five delivery prompts (A.2, A.3, A.4, A.7, A.10)
**must answer**. A refusal there is a failure, not a feature request.
Everything after its section 5 is stability probing, where a clean refusal
is correct.

## Two formats — do not mix them

`00`–`10` and `qa_testcases` are plain prompts, one per line, for
`promptkit.py --run --prompt-file`.

`scorer/parser_stress.txt` uses `EXPECT ||| prompt` and needs the scorer.
Feeding it to `promptkit.py` sends the `filter:status |||` prefix to the
parser as part of the prompt. It lives in a subfolder for that reason.

## Running

All runs go through `promptkit.py --run`. It takes one or more prompt
files via `--prompt-file`, a manifest of set names via `--manifest`, or a
one-off `--prompt "..."`. `--prompt`, `--prompt-file`, and `--manifest`
are mutually exclusive; within each, list multiple values space-separated.

Quick verification — the dipstick set, about 3 minutes:

```
python scripts/promptkit.py --run --prompt-file scripts/prompts/00_dipstick.txt
```

Several files, in the order given. `--prompt-file` takes one or more
paths; files run left to right, each file's prompts in line order:

```
python scripts/promptkit.py --run --prompt-file \
    scripts/prompts/00_dipstick.txt \
    scripts/prompts/01_supplier.txt \
    scripts/prompts/02_purchase_order.txt
```

Full run excluding the slow set, tee'd to a dated log:

```
python scripts/promptkit.py --run --prompt-file \
    scripts/prompts/00_dipstick.txt \
    scripts/prompts/01_supplier.txt \
    scripts/prompts/02_purchase_order.txt \
    scripts/prompts/03_ar.txt \
    scripts/prompts/04_columns.txt \
    scripts/prompts/05_refusals.txt \
    scripts/prompts/07_alacarte.txt \
    scripts/prompts/08_lifecycle.txt \
    scripts/prompts/10_refusal_examples.txt \
  2>&1 | tee run_$(date +%Y%m%d).txt
```

Everything, overnight, via the manifest:

```
python scripts/promptkit.py --run --manifest scripts/promptkit_sets.yaml
```

The manifest (`scripts/promptkit_sets.yaml`) lists the set names in run
order; each name resolves to `<prompts-dir>/<name>.txt` (default
`scripts/prompts/`). Comment a line out to skip a set. Each set runs as
its own subprocess with a per-set timeout (`--timeout`, default 3600s),
so one hung or crashing set cannot stop the batch. Output goes to
`promptkit_<YYYYMMDD_HHMMSS>/` in the cwd unless `--outdir` is given:

```
promptkit_20260922_165958/
    00_dipstick.txt      per-set stdout, one file per set
    01_supplier.txt
    ...
    _run_log.txt         start/end/exit/duration, one line per set
    _summary.txt         a compact table
```

To background it and keep a top-level log:

```
nohup python scripts/promptkit.py --run --manifest scripts/promptkit_sets.yaml \
    > overnight_$(date +%Y%m%d).txt 2>&1 &
```

The MCP server must stay up for the duration. If it is running in a
foreground terminal you plan to close, background it too.

Diagnostics are off by default and go to stderr. Add `--show-planner`,
`--show-parser`, `--show-all` and so on when you need them; the answer
stays on stdout either way. In `--manifest` mode the diagnostic flags are
forwarded to each child run, so they land on every set.

## Reading the results

**The summary line proves nothing.** A tally of exit codes has previously
reported "38/38 ran cleanly" while several prompts were being wrongly
REFUSED, and `05_refusals` once reported 9/9 while three of the nine
messages were wrong. Read the ANSWERS.

Score each prompt into one of three buckets:

- **pass** — right rows, right claims
- **fail** — errored, refused when it should not have
- **wrong but did not error** — the one that matters

For the third bucket, check specifically:

- an empty data array behind confident narrative prose
- a page count stated as a total ("25 suppliers" where 421 exist)
- a total, average or trend computed over a truncated sample and stated
  as fact
- claims about fields absent from the displayed projection
- arithmetic in the narration that is not in the rows
- customer-scoped results that never resolve an AccountNumber
- a generalisation true of the first few rows but not the set

Do not print a raw exit code beside each prompt in a loop. A screen of
`exit=4` reads as a screen of crashes even to someone who knows exit 4 is
a refusal — that misreading is documented and is what UX-01 was built to
fix.

## Order matters

`00_dipstick` is depth-ordered on purpose. If depth 2 fails, the filter
layer is broken and every later failure is probably downstream of it.
Run it first and read it first.

## If a whole set refuses

Check the KG before anything else. A stale or partial KG makes every
prompt refuse with a short entity list — the 2026-07-28 `qa_testcases`
baseline recorded 21 failures for exactly this reason, all of them
reporting `Known target entities: ['Address', 'Invoice', 'Supplier']`.

```
python scripts/rebuild_kg.py
python scripts/print_kg.py --counts-only
```

## About `qa_testcases.txt`

Externally captured prompts, kept verbatim — including a malformed one
with a leading space and an unbalanced quote, and several carrying
unresolvable pronouns. Do not tidy them: the wording IS the test.

It is not a regression set. Each prompt carries a status label
(`PASS` / `FAIL` / `FAIL-KG` / `REFUSE-OK` / `REFUSE-BAD-MSG`) and most
labels date from 2026-07-28, before the KG rebuild. Re-run the whole set
before trusting any `FAIL-KG` label.

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

## What changed 2026-07-30 (refusal messages, UX-01)

- Refusals are now three labelled lines — Reason, Solution, Example —
  replacing the entity-and-filter dump that opened every message.
- `10_refusal_examples.txt` added: every example the refusal tables
  promise, as a runnable set. Baseline 18/18.
- `qa_testcases.txt` gained the `REFUSE-BAD-MSG` label, and nine AR
  prompts from an external SME report.
- `promptkit.py` takes the same diagnostic flags as `run_graph.py`.

## Quick reference

Two file types feed `promptkit.py`:

- **Prompt file** (`*.txt`) — one prompt per line. `#` and blank lines
  skipped. Run with `--prompt-file`.
- **Manifest file** (`*.yaml`) — a `sets:` list of set names. Each name
  resolves to `<prompts-dir>/<name>.txt` (default `scripts/prompts/`).
  Run with `--manifest`.

Five ways to run — just the commands.

**1. One prompt file**

```
python scripts/promptkit.py --run --prompt-file scripts/prompts/00_dipstick.txt
```

**2. Multiple prompts (space-separated)**

```
python scripts/promptkit.py --run --prompt \
    "Suppliers with their addresses" \
    "active suppliers in US" \
    "show me contract renewals"
```

**3. Multiple prompt files**

```
python scripts/promptkit.py --run --prompt-file \
    scripts/prompts/00_dipstick.txt \
    scripts/prompts/01_supplier.txt
```

**4. One manifest file**

```
python scripts/promptkit.py --run --manifest scripts/promptkit_sets.yaml
```

Writes to `promptkit_<YYYYMMDD_HHMMSS>/` in the cwd unless `--outdir` is
given. One output file per set, plus `_run_log.txt` and `_summary.txt`.

**5. Multiple manifest files**

```
python scripts/promptkit.py --run --manifest \
    scripts/promptkit_sets.yaml \
    scripts/promptkit_sets_smoke.yaml \
    --outdir results/tonight
```

Each manifest gets its own `<stem>/` subfolder under `--outdir`, so set
names can't collide between manifests.