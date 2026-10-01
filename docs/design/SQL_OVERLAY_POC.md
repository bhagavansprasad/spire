# POC - SQL Overlay for Fusion

**Date:** 2026-10-01
**Branch:** `poc/sql-overlay`
**Base:** `hardening-master-v2`
**State:** open

## V0 - What this POC proves

SPIRE turns an English prompt into an Intent, a Plan, and executed
Fusion REST calls. This POC adds a **deterministic SQL projection of
the Plan** — for every Plan step, the equivalent Fusion-DB SQL — and
prints it alongside the existing pipeline output.

The SQL is a function of the Plan. The Plan is a deterministic KG
lookup. **No LLM is involved in SQL emission.** The model's job ends at
the Intent; everything from there is code.

## Module scope

**Supplier** only. Five entities: Supplier, Address, Site,
Classification, Contact.

Chosen because it is the smallest module that exercises every plan
shape the emitter must handle:

| plan shape | example prompt |
|---|---|
| simple WHERE | `List active suppliers` |
| multi-filter AND | `Active suppliers in US` |
| child JOIN (include) | `Suppliers with their addresses` |
| edge-traversal EXISTS | `Suppliers with a site in US1 Business Unit` |
| COUNT(*) | `Count of suppliers` |

One optional sixth — `Top 5 suppliers by spend this year` — to exercise
the aggregation rewrite (GROUP BY + SUM + ORDER BY + LIMIT).

## What is in scope

- Three overlay tables (`kg_sql_entity`, `kg_sql_field`, `kg_sql_filter`)
  encoding the Fusion DB names, joins, and predicate templates for the
  five entities.
- A loader (`src/spire/kg/sql_overlay.py`).
- An emitter (`src/spire/rendering/sql_emitter.py`) — `emit_sql(plan,
  overlay) -> list[str]`, one SQL string per Step.
- A `--show-sql` flag on `scripts/promptkit.py`.
- Five acceptance captures + unit tests for the emitter's shapes.
- This doc — filled in as each phase runs.

## What is deliberately out

- **SQL execution.** No DB client, no query run. Print only.
- **REST-vs-DB comparison.** Deferred to POC-2.
- **The other three modules.** Payables, procurement, receivables.
- **Any change to parser, planner, or synthesizer.**
- **A compiler that fuses N steps into one joined SELECT.** The POC
  emits per-step SQL — honest, matches what the pipeline did.
- **Any LLM in SQL emission.** The emitter reads the Plan; it does not
  call a model.

## Why per-step, not one joined query

The Plan is procedural: step N iterates step N-1's output. SQL is
set-based. Fusing N steps into a single joined SELECT is a compiler,
not a projection. The POC prints one SQL statement per Plan step, in
order — the same sequence the executor would run against Fusion, in SQL
syntax. That is reviewable by eye and honest about what happened.

## Acceptance criteria

The POC is proven if:

1. All five acceptance prompts produce plausible, correct SQL on first
   read.
2. Each prompt's SQL matches a hand-written equivalent for the same
   question (side-by-side comparison in this doc).
3. Every plan shape the emitter handles has a unit test.
4. No existing test regresses — the `--show-sql` flag is additive.
5. Two runs of the same prompt produce byte-identical SQL (determinism).

## Phases

| # | phase | status |
|---|---|---|
| 0 | Pre-work (this doc, branch) | in progress |
| 1 | Data gathering — Fusion DB schema, Supplier module | pending |
| 2 | Investigation — KG <-> Fusion mapping, gap list | pending |
| 3 | Overlay build — schema, seed, loader, tripwire test | pending |
| 4 | Emitter build — one function per shape, unit tests | pending |
| 5 | Display — `--show-sql` flag | pending |
| 6 | Acceptance run — five prompts, five captures | pending |
| 7 | Handoff — extension guide, POC-2 sketch | pending |

## Data required from the user (phase 1)

1. Table names and join paths for each of the five REST entities.
2. Column mappings for the ~15 Supplier fields a WHERE or SELECT would
   name.
3. One worked REST call + its DB SQL equivalent, to calibrate join
   depth and predicate shape.

## Deviations from any prior plan

- **Not a fix.** This adds a capability (SQL projection) that did not
  exist. Nothing in the existing pipeline changes.
- **One branch for the whole POC**, not one per phase, matching the
  convention used on `Four-prompts-bugs-Triage`.
