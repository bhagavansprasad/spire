# Design 3 — Measurement Report

**Track:** Design 3 — Graph-Guided Orchestration (planner + executor, no LLM in planning)
**Date:** 2026-05-26
**Architecture under test:** KG (8 tables in Oracle 26ai) + deterministic planner (`spire.planner.generate_plan`) + async MCP executor (`spire.executor.execute_plan`) + 5 MCP tools over HTTP. No LLM in the planning step. Intent hardcoded for v1.
**Tester:** Bhagavan

---

## What this report measures and what it does not

This is **not** a like-for-like 5-run measurement against Track A's
phase A.5 baseline. Two protocol differences are called out up front
so the comparison stays honest:

1. **One run, not five.** Design 3's planning step is deterministic
   — there is no LLM in the planner or executor, and the Intent for
   v1 is hardcoded. Five runs would produce five identical traces.
   The 5-run protocol was designed to expose LLM variance in
   Track A; that variance does not exist here.

2. **Two scorings of one trace.** The same execution is scored
   against two prompts: the v1 anchor question (which the Design 3
   v1 KG is built to handle) and the original Track A prompt (which
   includes a negation clause Design 3 v1 does NOT handle). The
   two-scoring approach makes both the gain and the gap visible.

Reproduction is `python scripts/run_plan.py` against the live MCP
server and the demo Fusion pod. Determinism was confirmed
empirically: two independent runs of the script two hours apart
on the same day produced byte-identical record counts at every
step (25 US suppliers, 29 OPEN POs, 8 unique buyers). The trace
referenced below is the later of the two runs.

---

## The reference prompts

**Original Track A prompt** (from `docs/phase_a5_baseline_report.md`):

```
Show me suppliers in US with no invoices in 6 months but with open
purchase orders, including the buyer assigned to each.
```

**v1 anchor question** (what Design 3 v1 was built around; negation
clause dropped):

```
Show me suppliers in US with open purchase orders, including the
buyer assigned to each.
```

The v1 anchor is the original prompt minus the `no invoices in 6 months`
clause.

---

## The rubric

Same 7 rows as the Track A baseline, verbatim. Scored ✅ (fully
present and correct) / ⚠️ (partially present) / ❌ (absent or wrong).
Adds N/A for rows the prompt does not require.

| # | Behavior | What to look for in the trace |
|---|---|---|
| 1 | Find US suppliers | `search_suppliers_by_country(country="US")` called |
| 2 | Check invoices in last 6 months | `search_invoices(invoice_date_after="…")` (or similar) called for each candidate |
| 3 | Filter to "no recent invoices" | Final answer excludes suppliers with invoices in window |
| 4 | Check open POs | `search_purchase_orders(supplier_*=…, status="OPEN")` called for remaining candidates |
| 5 | Filter to "has open PO" | Final answer includes only suppliers with at least one open PO |
| 6 | Look up buyer | `get_buyer(buyer_id=…)` called for matched suppliers' POs |
| 7 | Final answer structure | Coherent supplier → buyer pairing presented to user |

**Not scored:** factual correctness of individual records (no ground
truth available), tool-call argument spelling latitude, formatting of
the script's printed output.

---

## The run

`python scripts/run_plan.py`, hardcoded v1 anchor Intent, executed
against the live MCP server and the `fa-esll-dev37-saasfademo1`
Fusion pod on 2026-05-26.

### Plan generated (deterministic, KG-driven)

```
Step 1: search_suppliers_by_country
  tool_args:      {'country': 'US'}
  iterate_over:   (none — runs once)
  client_filters: (none)
  dedupe_by:      (none)
  output_name:    us_suppliers

Step 2: search_purchase_orders
  tool_args:      {'supplier_id': '$iteration_value'}
  iterate_over:   us_suppliers.SupplierId
  client_filters: [{'field': 'StatusCode', 'op': 'equals', 'value': 'OPEN'}]
  dedupe_by:      (none)
  output_name:    open_pos

Step 3: get_buyer
  tool_args:      {'buyer_id': '$iteration_value'}
  iterate_over:   open_pos.BuyerId
  client_filters: (none)
  dedupe_by:      BuyerId
  output_name:    buyers
```

### Execution against live Fusion

| Step | Tool | Calls | Records returned |
|---|---|---|---|
| 1 | `search_suppliers_by_country` | 1 | 25 US suppliers |
| 2 | `search_purchase_orders` (iterated × 25) | 25 | 29 OPEN POs after `StatusCode=='OPEN'` client filter |
| 3 | `get_buyer` (iterated × 8 unique BuyerIds after dedup) | 8 | 8 unique buyers |

**Total: 62 records returned across 3 outputs. Wall-clock runtime
~67 seconds (per trace timestamps: `14:05:26` plan_executed-start
to `14:06:33` plan_executed-end), dominated by ~33 sequential
Fusion calls in Steps 2 and 3.**

Trace file: `traces/2026-05-26T14-05-26-496350.jsonl`.

---

## Scoring 1 — v1 anchor question

Scored as if the prompt was the v1 anchor (no negation clause).

| # | Behavior | Score | Evidence in trace |
|---|---|---|---|
| 1 | Find US suppliers | ✅ | Step 1 returned 25 US suppliers |
| 2 | Check invoices in last 6 months | N/A | Not requested by v1 anchor |
| 3 | Filter to "no recent invoices" | N/A | Not requested by v1 anchor |
| 4 | Check open POs | ✅ | Step 2 iterated 25 PO searches |
| 5 | Filter to "has open PO" | ✅ | Client filter `StatusCode=='OPEN'` reduced 200+ raw POs to 29 |
| 6 | Look up buyer | ✅ | Step 3 called `get_buyer` 8 times after `BuyerId` dedup |
| 7 | Final answer structure | ⚠️ | The script prints structured output (intent / plan / per-step results / summary) but does NOT pair each supplier with its buyer in a human-friendly answer. The data to do so is present in `open_pos` (each PO has `SupplierId` and `BuyerId`); no synthesis step composes it. |

**Aggregate (5 applicable rows): 4 ✅, 1 ⚠️.**

If row 7 is graded as ⚠️ → ✅ assuming a downstream response synthesizer
(LLM or template) composes the data, the score becomes 5/5 applicable
rows. If row 7 is graded as ❌ because the current script doesn't
compose it, the score is 4/5.

---

## Scoring 2 — original Track A prompt

Scored as if the prompt was the original Track A prompt (with the
`no invoices in 6 months` negation clause). Same trace, different
applicability.

| # | Behavior | Score | Evidence in trace |
|---|---|---|---|
| 1 | Find US suppliers | ✅ | Step 1 returned 25 US suppliers |
| 2 | Check invoices in last 6 months | ❌ | No `search_invoices` calls in the trace. See "Defect" section below. |
| 3 | Filter to "no recent invoices" | ❌ | Not reached |
| 4 | Check open POs | ✅ | Step 2 iterated 25 PO searches |
| 5 | Filter to "has open PO" | ✅ | Client filter `StatusCode=='OPEN'` reduced 200+ raw POs to 29 |
| 6 | Look up buyer | ✅ | Step 3 called `get_buyer` 8 times after dedup |
| 7 | Final answer structure | ❌ | The answer would be misleading on this prompt. The script returns suppliers with open POs whose invoice history was never checked. A user asking the original Track A prompt would receive results that do NOT honor the negation clause and would not be told the clause was dropped. |

**Aggregate (7 rows): 4 ✅, 3 ❌. Score: 4/7.**

Track A baseline on the same 7 rows: 1/7.

---

## Comparison with Track A baseline

| # | Behavior | Track A (best of 5 runs) | Design 3 v1 |
|---|---|---|---|
| 1 | Find US suppliers | ✅ | ✅ |
| 2 | Check invoices in last 6 months | ⚠️ (attempted; crashed) | ❌ (silently skipped) |
| 3 | Filter to "no recent invoices" | ❌ | ❌ |
| 4 | Check open POs | ❌ (crashed on param confusion) | ✅ |
| 5 | Filter to "has open PO" | ❌ | ✅ |
| 6 | Look up buyer | ❌ | ✅ |
| 7 | Final answer structure | ❌ | ❌ on original prompt; ⚠️ on v1 anchor |
| | **Aggregate** | **1/7** | **4/7** |

Net gain on the original Track A prompt: **+3 rubric rows**.

Where Track A failed (rows 4, 5, 6 — the composition steps that
involve join-key asymmetries and cross-pillar lookups), Design 3
succeeds. Where Track A also failed (rows 2, 3 — the negation
clause), Design 3 also fails, but for a different reason — the
planner's coverage gap, not LLM composition failure.

The gap is named: the v1 KG has no `not_X_in_N_months` pattern,
and the planner's intent vocabulary has no `has_no_recent_invoices`
filter type. Both are bookkeeping work, not architectural.

---

## Defect found — silent filter dropping

A defect in `generate_plan` was surfaced while preparing this
report.

**Behavior:** if an Intent contains a filter whose `type` is not
in `_EDGE_TRAVERSAL_FILTERS` and not in `_ENTITY_LEVEL_FILTER_TYPES`,
`_filters_needing_edge_traversal` silently excludes it. The plan
runs without the filter; the user is not told the filter was
dropped.

**Worked example:** an Intent for the original Track A prompt
would include three filters: `country`, `has_no_recent_invoices`,
`has_open_PO`. `country` is consumed by Block 1 (entity-level
fetcher). `has_no_recent_invoices` is unknown to the planner —
it is dropped without an error. `has_open_PO` is handled by
Block 2. Result: the plan executes as if the negation clause was
never in the prompt.

**Why this matters:** silent miss is worse than a crash. A crash
tells the user "I cannot answer that." A silent miss returns an
answer that *looks* correct but does not honor the prompt. On
the original Track A prompt, Design 3 v1 returns a list of US
suppliers with open POs — but those suppliers may have been
invoiced last week, contradicting the user's intent.

**Recommended v1.1 fix:** `_filter_target_entity` already raises
`KeyError` on unknown filter types. The orchestrator should reach
that error path before silently dropping. Concretely:

`_filters_needing_edge_traversal` should be replaced with logic
that, for each filter, either matches it to an entity-level
fetcher OR an edge-traversal pattern. Any filter that matches
neither must raise `NotImplementedError` with a message naming
the unknown filter type. This converts the silent miss into a
loud failure: the user sees that the prompt was understood but
not all of it could be answered.

This is the most important deliverable of this measurement.

---

## Failure patterns

### Track A failure patterns that Design 3 v1 does NOT exhibit

Both Track A failure modes (premature termination after one tool
call; parameter confusion between tools) are absent in Design 3.

- **No premature termination.** The plan is fully constructed
  before execution. There is no LLM step that can decide to stop
  after one tool call.
- **No parameter confusion.** The join key for each edge is read
  from `kg_edge.from_join_field`. `HAS_INVOICE` uses
  `SupplierNumber`; `HAS_PURCHASE_ORDER` uses `SupplierId`. The
  planner emits the right parameter name into `tool_args` because
  the KG carries the asymmetry as data, not docstring prose.

### Design 3 v1 failure patterns the measurement exposed

- **Silent filter dropping** (described above).
- **No response synthesis.** `scripts/run_plan.py` prints
  structured per-step output but does not compose a natural-
  language answer pairing each supplier with its buyer. Row 7's
  ⚠️ on the v1-anchor scoring reflects this gap. A response
  synthesizer (LLM template or otherwise) is the obvious next
  artifact, separate from the planner's coverage gap.
- **Hardcoded Intent.** The Intent is constructed in
  `scripts/run_plan.py` by hand. There is no LLM intent parser
  to translate the user's prompt into an Intent. This is the
  Design 3 component noted as "next" in the working log. Without
  it, no actual user prompt can drive a run; every measurement
  starts from a hand-built Intent.

---

## Honest interpretation

The architectural hypothesis is supported.

The hypothesis — that moving tool selection and join-key resolution
from in-the-loop LLM prose interpretation into a KG-driven planner
would close Track A's composition gap — is borne out by the score
delta (1/7 → 4/7) on the original Track A prompt. The three rows
Track A failed on for *composition* reasons (4, 5, 6) all flip to
✅ in Design 3 v1. Track A's parameter-confusion crash on rows 4-5
in particular does not occur, exactly as predicted.

The architectural hypothesis is not fully validated.

Two rows on the original Track A prompt remain ❌ (rows 2-3, the
negation clause). The reason is not LLM composition failure —
it's v1 KG coverage. The patterns needed (`not_X_in_N_months`)
and the intent vocabulary (`has_no_recent_invoices`) simply
weren't built. Building them is straightforward bookkeeping,
not new architecture.

The measurement also surfaced a real defect (silent filter
dropping) that, in isolation, makes the v1 Design 3 path *less
safe* than Track A on the original prompt. Track A crashed loudly
on rows 4-5; Design 3 v1 returns a partial answer silently. A
v1.1 fix is required before Design 3 v1 can be considered safer
than Track A for any prompt outside the v1 anchor.

### Scope of the conclusion

This is **one measurement on one prompt** (one prompt scored
two ways). The result is not a claim about Design 3's
generalization to other prompts, other domains, or other Fusion
pillars. It is a single, honest data point about the
architectural hypothesis on the prompt the POC was built around.

---

## Discipline notes

Confirming what was *not* done while preparing this report:

- ❌ The Intent was not modified to make the score look better
- ❌ The KG was not edited to add missing patterns mid-measurement
- ❌ The planner was not edited to handle the negation clause
- ❌ The trace was not re-run after observing partial failures
- ❌ The Track A rubric was not loosened

The defect found (silent filter dropping) was documented in the
report rather than fixed in-place. A v1.1 PR can address it
afterward without invalidating this measurement.

---

## Exit criteria

| Criterion | Status |
|---|---|
| Reproduction harness exists (`scripts/run_plan.py`) | ✅ |
| Same rubric as Track A applied to a Design 3 run | ✅ |
| Honest scoring on the original Track A prompt | ✅ (4/7) |
| Comparative artifact written | ✅ (this document) |
| Defects and gaps named explicitly | ✅ (silent filter drop; no response synthesis; no intent parser) |
| Recommendations for the next phase identified | ✅ (v1.1 fix + intent parser + `not_X_in_N_months` pattern) |

---

## What's next

In priority order:

1. **v1.1 fix — silent filter dropping.** Make the planner raise on
   unknown filter types. Single PR, small change in
   `_filters_needing_edge_traversal` and/or `generate_plan`. This
   is a safety fix and should land before any other Design 3 work.

2. **`not_X_in_N_months` pattern + `has_no_recent_invoices` intent
   filter.** Adds the KG row, the planner mapping table entry, the
   pattern handler in `_resolve_client_filters`, and the tests. After
   this, a re-run of the original Track A prompt against Design 3
   should score 6/7 or 7/7 (depending on how row 7 is graded).

3. **LLM intent parser.** Turns the user's natural-language prompt
   into an `Intent`. Currently the Intent is hardcoded in
   `scripts/run_plan.py`. With a parser, real user prompts (variants,
   typos, paraphrases) drive runs. This is also where prompt-
   interpretation variance re-enters the system; a second
   measurement after the parser lands would honestly use multiple
   runs and report variance.

4. **Response synthesizer.** Turns the executor's output dict into
   a natural-language answer. Closes row 7 of the rubric properly,
   not just structurally.

Items 1, 2, 4 are bookkeeping. Item 3 is the only new architectural
piece, and it intentionally puts the LLM back into the pipeline
at the boundary (not in the planning step).

---

## Trace file

- `traces/2026-05-26T14-05-26-496350.jsonl` — the Design 3 v1 run
  on which both scorings above are based. An earlier run at
  `traces/2026-05-26T12-04-09-851785.jsonl` produced byte-identical
  record counts at every step; kept as evidence of empirical
  determinism but not the canonical reference for scoring.
