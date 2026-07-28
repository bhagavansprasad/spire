# Design 3 — Measurement Report

**Track:** KG-driven path (Design 3, the "Graph-Guided Orchestration"
architecture in `docs/designs/spire_design_alternatives.md`)
**Date:** 2026-05-26
**Status:** v1.1 — post-F1, F2, F3 fix track. Supersedes the v1.0 4/7
report.
**Tester:** Bhagavan
**Architecture under test:** Python planner that reads a Knowledge
Graph (Oracle 26ai) and emits a structured `Plan`. The plan is run
sequentially by a Python executor against the 5 existing MCP tools.
A Gemini 2.0 Flash synthesizer with structured output and
hallucination validation produces the final answer. No LLM in
planning or execution; LLM only at output synthesis.

---

## What this report measures and what it does not

This report scores Design 3 v1.1 against the **same 7-row rubric**
used for the Track A baseline in `docs/phase_a5_baseline_report.md`.
The rubric is reproduced unchanged in the relevant section below so
the two reports can be compared side by side.

Two scope notes carried forward from the v1.0 report, still
applicable:

1. **One prompt.** Same single anchor question Track A was tested on
   (the original Track A prompt with the negation clause). No
   broader benchmark.

2. **One trace per run; three runs.** The planner and executor are
   deterministic; the synthesizer is an LLM call. The v1.0 report
   used 1 run because no LLM was in the pipeline at the output. v1.1
   restores the **3-run protocol** so synthesizer variance is
   reported honestly.

The data shape that the executor returns is now empirically stable:
**five independent runs across two sessions** (the v1.0 report's two
runs plus three v1.1 runs) all produced byte-identical record counts
at every step.

Reproduction is `python scripts/run_plan.py` against the live MCP
server and the demo Fusion pod. The synthesizer call adds ~13s on
top of the executor's ~125s, for a total wall-clock of roughly 2.5
minutes per run.

---

## What changed between v1.0 (4/7) and v1.1 (this report)

Three focused fixes landed on master between the two reports. Each
landed as its own branch + PR with full unit test coverage before
merging:

- **F1** (`fix/f1-silent-filter-drop`, commit `eff11bd`) — Closed
  the silent-drop defect surfaced in the v1.0 report. The planner
  now raises `NotImplementedError` on unknown filter types instead
  of executing the plan with the unknown clause silently removed.
  73 → 79 planner tests.

- **F2** (`fix/f2-negation-pattern`, commit `d93ca80`) — Added the
  `no_invoices_in_N_months` pattern end-to-end. New KG pattern +
  binding, planner support for negation-by-absence (a new step
  shape that filters parent items by per-iteration emptiness),
  executor support for the new step shape. The flag on `Step` that
  carries this is `filter_source_when_empty: bool`. 79 → 102 planner
  tests; 37 → 45 executor unit tests; 2 → 3 executor integration
  tests including a live-Fusion test of the new semantic.

- **F3** (this branch, before this report commits) — Added the
  LLM-based response synthesizer with Pydantic-typed structured
  output and ID-cross-reference hallucination validation against
  the executor's source data. New `src/spire/synthesizer/` module.
  22 unit tests (mocked LLM) + 1 live-Gemini integration test.
  `scripts/run_plan.py` updated with `--intent {anchor,original}`
  CLI arg, exit codes for each pipeline stage, and trace logging
  of the synthesized response.

Nothing in the KG schema or v1 mapping tables was changed in a way
that affects the v1 anchor question. v1.0's anchor-only score is
unchanged by these fixes; they only widen what the system can
handle.

---

## The reference prompt

Same as the v1.0 report. Same as the Track A baseline.

```
Show me suppliers in US with no invoices in 6 months but with open
purchase orders, including the buyer assigned to each.
```

The intent the planner receives:

```python
Intent(
    target_entity="Supplier",
    filters=[
        {"type": "country", "value": "US"},
        {"type": "has_no_recent_invoices", "value": {"months": 6}},
        {"type": "has_open_PO", "value": True},
    ],
    include=["Buyer"],
)
```

All three filter types are now recognized. The v1.0 report's
"silent-drop" defect for `has_no_recent_invoices` is closed by F1
(would raise if still unsupported) and F2 (now actually supported).

---

## The plan produced

Four steps. The third filter (`has_no_recent_invoices`) is the F2
addition; everything else carries through from the v1 anchor.

```
Step 1: search_suppliers_by_country({"country": "US"})
        → us_suppliers

Step 2: search_invoices, iterating us_suppliers.SupplierNumber,
        tool_args={"supplier_number": "$iteration_value",
                   "invoice_date_after": "<today minus 6 months>"},
        filter_source_when_empty=True
        → us_suppliers_no_recent_invoices

Step 3: search_purchase_orders, iterating
        us_suppliers_no_recent_invoices.SupplierId,
        client_filter StatusCode=='OPEN'
        → open_pos

Step 4: get_buyer, iterating open_pos.BuyerId (deduped)
        → buyers
```

Notable: Step 2's iteration field is `SupplierNumber`, not
`SupplierId`, because `HAS_INVOICE` joins on `SupplierNumber` per
the KG. The asymmetry that crashed Track A in earlier runs is
encoded in the KG and carried by the planner without any prose-
reading.

The `invoice_date_after` value is computed at plan-generation time
from `date.today()` minus 6 months (with day-clamping to handle
month rollover). Tests pin this to a fixed reference date for
determinism; production uses today.

---

## Execution results (three runs, same day)

| Output | Run 1 | Run 2 | Run 3 |
|---|---:|---:|---:|
| us_suppliers | 25 | 25 | 25 |
| us_suppliers_no_recent_invoices | 24 | 24 | 24 |
| open_pos | 28 | 28 | 28 |
| buyers | 7 | 7 | 7 |
| **Total records** | **84** | **84** | **84** |

**Identical record counts across all three runs.** Step 2's
negation semantic worked: of 25 US suppliers, 1 had invoices in
the last 6 months (dropped) and 24 had none (kept). Of those 24,
11 had at least one open PO. Those 11 suppliers' open POs added
up to 28, served by 7 unique buyers (one buyer can be on many POs;
deduped via `output_dedupe_by=BuyerId`).

For comparison with the v1.0 anchor execution (which did not run
Step 2 because the negation clause was silently dropped): v1.0
produced 25/29/8/62 (suppliers/open_pos/buyers/total). v1.1
produces 25/24/28/7/84. The negation filter eliminated one
supplier with one open PO and one unique buyer, propagating
through Steps 3 and 4 consistently. The numbers add up.

Trace files (newest first):
- `traces/2026-05-26T18-48-38-758019.jsonl`
- `traces/2026-05-26T18-46-17-260341.jsonl`
- `traces/2026-05-26T18-43-52-939963.jsonl`

Wall-clock per run: 123-135 seconds. Dominated by the 25
sequential `search_invoices` calls in Step 2 (~80s) plus 24
sequential `search_purchase_orders` calls in Step 3 (~30s) plus
the synthesizer LLM call (~13s).

---

## Synthesized response (three runs)

The synthesizer returns a Pydantic-typed structured response. Each
response has two parts:

- **`summary`**: one paragraph of natural-language prose.
- **`suppliers`**: a structured list, one entry per supplier in
  the final result. Each entry carries `supplier_id`,
  `supplier_number`, `supplier_name`, `open_po_count`, and a list
  of `BuyerInfo` (with `person_id` and `display_name`).

Every `supplier_id`, `supplier_number`, and `person_id` in the
response is cross-checked against the executor's outputs before
the response is returned. If any ID is invented, `synthesize_response`
raises `HallucinationError` and the script exits with code 3. The
hallucination guard did NOT fire on any of the three runs.

### Structured part — variance across 3 runs

The structured suppliers list is byte-identical across all three
runs. Specifically:

- Same 11 suppliers (same `supplier_id` values, same order)
- Same `open_po_count` per supplier (9, 3, 1, 1, 1, 2, 1, 1, 1, 2, 6)
- Same buyer assignments per supplier (same `person_id` values,
  same display names)

This is the regime the structured-output design was meant to
produce: schema-constrained extraction with bounded variance.

### Prose part — variance across 3 runs

The `summary` field varies in compression:

| Run | Summary length | Wording |
|---|---:|---|
| 1 | 834 chars | "Lee Supplies (SupplierId 300000047414503) has 9 open purchase orders…" |
| 2 | 834 chars | Identical to Run 1 |
| 3 | 572 chars | Compressed; same facts, fewer sentences |

Runs 1 and 2 produced character-identical summaries. Run 3 chose a
shorter phrasing. Same facts in all three; the variance is in
verbosity, not content. No invented details, no contradictions.

---

## The rubric (reproduced unchanged from Track A baseline)

| # | Behavior | What to look for in the trace |
|---|---|---|
| 1 | Find US suppliers | `search_suppliers_by_country(country="US")` called |
| 2 | Check invoices in last 6 months | `search_invoices(invoice_date_after="2025-11-26")` (or similar) called for each candidate |
| 3 | Filter to "no recent invoices" | Final answer excludes suppliers with invoices in window |
| 4 | Check open POs | `search_purchase_orders(supplier_*=..., status="OPEN")` called for remaining candidates |
| 5 | Filter to "has open PO" | Final answer includes only suppliers with at least one open PO |
| 6 | Look up buyer | `get_buyer(buyer_id=...)` called for matched suppliers' POs |
| 7 | Final answer structure | Coherent supplier → buyer pairing presented to user |

**Not scored:** factual correctness of the final answer (no ground
truth available on the demo pod), tool/argument name spelling
latitude, exact wording of the prose summary.

---

## Score

| # | Track A baseline (5 runs avg) | Design 3 v1.0 (1 run) | Design 3 v1.1 (3 runs, this report) |
|---|---|---|---|
| 1 | ✅ | ✅ | ✅ |
| 2 | ⚠️ (1 of 5 attempted, crashed) | ❌ (filter silently dropped — F1 defect) | ✅ — 25 invoice queries with `invoice_date_after=2025-11-27` |
| 3 | ❌ | ❌ (filter silently dropped — F1 defect) | ✅ — 1 supplier dropped (had recent invoices), 24 kept |
| 4 | ❌ (3 of 5 crashed before reaching) | ✅ | ✅ — 24 PO queries; 28 OPEN POs across 11 suppliers |
| 5 | ❌ | ✅ | ✅ — client filter `StatusCode=='OPEN'` |
| 6 | ❌ | ✅ | ✅ — 7 unique buyers (deduped from 28 PO BuyerId values) |
| 7 | ❌ (4 of 5 empty answers, 1 crash) | ⚠️ (raw printout, no synthesis) | ✅ — synthesized response, structured, hallucination-guarded, structurally identical across 3 runs |
| **Total** | **1/7** | **4/7** | **7/7** |

---

## Comparison summary

| Dimension | Track A baseline | Design 3 v1.0 | Design 3 v1.1 |
|---|---|---|---|
| Architecture | LLM-as-planner (LangGraph) | KG-driven planner (deterministic) + raw executor output | KG-driven planner + executor + Pydantic-typed LLM synthesizer with hallucination guard |
| LLM in planning | yes | no | no |
| LLM at output | yes (free prose) | no (raw printout) | yes (structured output) |
| Test prompt scope | original 7-step prompt | v1 anchor (3-step subset of the prompt) + original prompt with silent gap | full original prompt |
| 7-row rubric score | 1/7 average across 5 runs | 4/7 on original prompt | **7/7 average across 3 runs** |
| Determinism (planner+executor) | low — 5 runs varied | high — byte-identical across runs | high — byte-identical across runs (5 reproductions across 2 sessions) |
| Determinism (output) | low — 4 empty + 1 crash | n/a — no LLM | high (structured) + small variance (prose only) |
| Hallucination protection | none | n/a | structured-output schema + ID cross-check; raises on any invented ID |
| Wall-clock per run | seconds (most runs crashed early) | ~67 seconds | ~125 seconds |

---

## What this report does NOT claim

Same caveats as the v1.0 report, restated honestly because the new
score is high and easy to misread:

1. **One prompt, one demo pod.** The 7/7 score is on the single
   original Track A prompt against the single demo Fusion pod we
   have access to. We have NOT measured this design against other
   prompts, other entities, other Fusion endpoints, or other pods.

2. **Schema is hardcoded.** The synthesizer's `SynthesizedResponse`
   schema is specific to the supplier → buyer answer shape. A
   different prompt (e.g. "show me the top 5 buyers by PO count")
   would need a different schema. Generalizing the schema is a v1.2
   candidate.

3. **Intent is hardcoded too.** `scripts/run_plan.py` carries the
   intent as a Python constant (selected via `--intent`). There is
   no LLM intent parser; a natural-language prompt is not actually
   accepted at the top of the pipeline. The Track A baseline DID
   accept the natural-language prompt; Design 3 hands the parsed
   intent in directly. The Intent parsing layer is unbuilt; it's a
   v1.2 candidate.

4. **All filter types still come from the v1 mapping tables.** Add
   a new business question (e.g. "suppliers above $X in spend") and
   the planner will raise (F1 defect closed; no silent drops). But
   the KG / planner / synthesizer would all need new rows to actually
   handle it. The 7/7 measures the system on questions it was built
   for, not on questions it wasn't.

5. **Sequential execution.** 125 seconds per run, dominated by ~50
   sequential Fusion calls. Production would parallelize. Out of
   scope for this measurement.

6. **No comparison against Track A on the same prompt.** Track A
   crashed and produced empty answers on this prompt; that's the 1/7.
   Design 3 v1.1 produces a complete, validated answer. The
   architectures are doing fundamentally different things at the
   planning step (deterministic Python vs LLM-as-planner), so the
   comparison is honest but the categories aren't strictly
   apples-to-apples.

---

## What the result actually means

**Net rubric gain on the original Track A prompt: Track A 1/7 →
Design 3 v1.1 7/7, a +6 jump across 7 rows.**

The breakdown of where that came from:

- **+3 rows from the architectural pivot (Design 3 v1.0)**: the
  composition steps (PO lookup, OPEN filter, cross-pillar buyer
  resolution) that Track A failed on for LLM-decision reasons.
  Deterministic planning + KG-encoded join keys solved these.

- **+2 rows from F1 + F2**: the negation clause that v1.0 silently
  dropped. F1 made the gap visible; F2 actually closed it via a
  new KG pattern, new step shape, and new executor semantic.

- **+1 row from F3**: row 7 (final structured answer). Structured-
  output LLM with a Pydantic schema + ID cross-check against
  source data. Bounded variance (structured part byte-identical
  across 3 runs; prose part varies in compression only).

**What still keeps the result honest:** the work needed to claim
generalization (different prompts, intent parsing, schema
generalization) is NOT done. The 7/7 is a real measurement on a
real prompt against a real pod, but it's one data point. The next
harder measurement — how the design holds up on prompts it wasn't
specifically built for — is a separate exercise.

---

## Trace files

- `traces/2026-05-26T18-43-52-939963.jsonl` — Run 1 of 3 (v1.1)
- `traces/2026-05-26T18-46-17-260341.jsonl` — Run 2 of 3 (v1.1)
- `traces/2026-05-26T18-48-38-758019.jsonl` — Run 3 of 3 (v1.1)
- `traces/2026-05-26T14-05-26-496350.jsonl` — v1.0 run (4/7, anchor
  intent without negation, no synthesizer)
- `traces/2026-05-26T12-04-09-851785.jsonl` — earlier v1.0 run,
  byte-identical executor counts to the 14:05 run; kept as
  empirical determinism evidence
