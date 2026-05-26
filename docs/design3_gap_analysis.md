# Design 3 — Phase A Gap Analysis

**Date:** 2026-05-26
**Status:** Complete. Six runnable prompts executed against live MCP +
Fusion. Findings documented honestly, including one correction to an
initially-wrong reading.
**Roadmap reference:** Phase A of
`docs/designs/design3_v1_to_production_roadmap.md`.

---

## Scope

Phase A asks one question:

> *Beyond the original Track A prompt that Design 3 v1.1 scores 7/7
> on, where does this design generalize, and where does it break?*

Seven prompts were chosen deliberately to stress different parts of
the system. Six were runnable; the seventh ("Who's our best
supplier?") cannot be turned into an Intent without an intent parser
that asks clarifying questions, so it's documented as a known
architectural gap rather than run.

**Phase A explicitly did not:**
- Add new KG patterns
- Add new MCP tools
- Modify the planner, executor, or synthesizer
- Fix anything that was surfaced

The fixes implied by the findings below go to Phases B-E of the
roadmap.

---

## One process note up front

While analyzing the runs, I (Claude) initially mis-read the data from
Prompts 1 (UK) and 3 (India). The 25 suppliers returned for those
country queries are the same 25 returned for the US anchor query,
and I jumped from "same suppliers" to "tool is broken / returning
wrong data." That was wrong.

A direct REST API check against Fusion confirmed: Lee Supplies (the
first supplier in each list) has addresses in **12 different
countries** including the US, UK, India, Japan, Mexico, Germany,
Belgium, Poland, Saudi Arabia, Australia, Netherlands, and Sweden.
The `kg_pattern` for `country_filter_via_address` explicitly notes
that this case is supported:

> *"A parent with addresses in multiple countries can match multiple
> country filters; that is correct behavior."*

The tool is working as designed. The data is correct. I was wrong.

This is documented here because it matters: measurement work demands
verifying surprising data before drawing conclusions, and I should
have done that before suggesting the tool was broken. The corrected
analysis is what follows.

---

## Method

Each runnable prompt has:

1. **The natural-language prompt** — what a user might type.
2. **The constructed `Intent`** — hand-built since we have no intent
   parser yet (Phase C).
3. **The expected outcome** — what we predicted before running.
4. **The actual outcome** — what `run_plan.py --intent prompt-N`
   produced.
5. **Gap classification** — `works`, `missing-kg-pattern`,
   `missing-filter-type`, `missing-mcp-tool`, `missing-entity`,
   `schema-too-narrow`, `needs-intent-parser`, or
   `genuinely-out-of-scope`.
6. **Rough size of fix** — `trivial` (KG row), `small` (planner
   mapping table entry), `medium` (planner code), `large` (new
   architecture).

---

## Prompts

### Prompt 1 — Vocabulary variant of the anchor

**Natural-language prompt:**

> *"Show me suppliers in the United Kingdom with open purchase orders,
> including the buyer assigned to each."*

**Constructed Intent:**

```python
Intent(
    target_entity="Supplier",
    filters=[
        {"type": "country", "value": "United Kingdom"},
        {"type": "has_open_PO", "value": True},
    ],
    include=["Buyer"],
)
```

**Expected outcome:**

Vocabulary should resolve "United Kingdom" → "GB". Planner should
emit a 3-step plan identical in shape to the anchor. Whether the demo
pod actually has GB suppliers with open POs was unknown going in.

**Actual outcome:**

- Trace: `traces/2026-05-26T19-51-43-686286.jsonl`
- Vocabulary resolution: "United Kingdom" → "GB" ✓
- Plan steps: 3 (identical shape to anchor)
- Executor counts: 25 gb_suppliers / 62 open_pos / 12 unique buyers
- Synthesizer outcome: succeeded; 11-supplier structured response;
  hallucination guard did not fire ✓
- Final answer included real suppliers (Lee Supplies, Consolidated
  Supplies, Dell, EIP, EDF, Staples, Amazon, etc.) with real open PO
  counts and real buyer assignments

**Gap classification:** `works`

**Rough size of fix:** N/A

**Note worth surfacing:** The synthesizer's prose said "25 active
suppliers" while the structured `suppliers` list contained 11. The
prose is reporting the number of suppliers fetched in Step 1; the
structured list is reporting suppliers that actually had open POs and
buyers (the 11 that survived through Step 3's join). Both numbers are
truthful; the inconsistency between them is a minor synthesizer-prose
issue. Minor enough to note here but not fix.

---

### Prompt 2 — Different target entity (PurchaseOrder, not Supplier)

**Natural-language prompt:**

> *"Show me open purchase orders over $100,000 with their supplier
> and buyer."*

**Constructed Intent:**

```python
Intent(
    target_entity="PurchaseOrder",
    filters=[
        {"type": "has_open_PO", "value": True},
        {"type": "amount_over", "value": {"amount": 100000}},
    ],
    include=["Supplier", "Buyer"],
)
```

**Expected outcome:**

F1 should raise on `amount_over` (unknown filter type). Even if
`amount_over` were known, the planner would then find no entity-level
fetcher for `PurchaseOrder` and raise. Either way: planner raises,
exit code 1.

**Actual outcome:**

```
ERROR generating plan: Intent contains filter types not supported in
v1: ['amount_over']. Supported entity-level filters: ['country'].
Supported edge-traversal filters: ['has_no_recent_invoices',
'has_open_PO'].
```

F1 raised cleanly with a useful error message naming both the
unsupported filter AND the supported alternatives. ✓

**Gap classification:** `missing-filter-type` and `missing-mcp-tool`
(amount-based filtering doesn't exist; PO-rooted querying isn't
supported)

**Rough size of fix:** `medium`. Three things needed for this prompt
class to work:
1. New KG pattern `amount_compare` and binding for PurchaseOrder
2. New entity-level fetcher for PurchaseOrder (new MCP tool +
   `kg_entity_tool` row + `_ENTITY_LEVEL_FILTER_TYPES` extension)
3. The planner's `_build_fetcher_args` would need to accept comparison
   operators, not just equality

**Note:** the planner caught the FIRST unknown filter and stopped.
It did NOT also report that `target_entity="PurchaseOrder"` has no
fetcher. F1's error surfacing is single-shot per validation pass; a
caller fixing the filter would then hit the entity error on retry.
This is acceptable today but worth noting for the eventual intent
parser — the parser should pre-check both filters and target entity
in one pass and surface all gaps together.

---

### Prompt 3 — Simplest possible intent

**Natural-language prompt:**

> *"List all suppliers in India."*

**Constructed Intent:**

```python
Intent(
    target_entity="Supplier",
    filters=[
        {"type": "country", "value": "India"},
    ],
    include=[],
)
```

**Expected outcome:**

1-step plan, simplest case. Sanity check that the architecture
handles minimal Intents.

**Actual outcome:**

- Trace: `traces/2026-05-26T19-51-20-988312.jsonl`
- Plan: 1 step (`search_suppliers_by_country(country="IN")`) ✓
- Executor: 25 suppliers returned, each with `MatchedCountry="IN"`
- Vocabulary resolution: "India" → "IN" ✓
- Synthesizer outcome: succeeded BUT returned **0 structured
  suppliers** with prose describing 25

The synthesizer's prose accurately described the 25 suppliers in
natural language. But the structured `suppliers` field of the
`SynthesizedResponse` was empty.

Reason: the `SupplierSummary` schema requires `open_po_count: int`
and `buyers: list[BuyerInfo]`. Prompt 3 has no `has_open_PO` filter
and no `include=["Buyer"]`, so the executor never produced `open_pos`
or `buyers` outputs. The synthesizer correctly refused to invent
those values, but then dropped the suppliers entirely from the
structured output rather than including them with `open_po_count=0`
and `buyers=[]`.

**Gap classification:** `schema-too-narrow`

**Rough size of fix:** `medium`. Two layers:

1. **Immediate fix (Phase B candidate):** make `open_po_count` and
   `buyers` optional in the schema, OR teach the synthesizer that
   missing buckets means zero/empty. Trivial code change once Phase B
   decides on the parameterization model.

2. **Deeper architectural question:** the schema being supplier-shaped
   at all is the real limit. Prompt 3 is "list suppliers" — the
   right answer shape is a list of suppliers with minimal fields, not
   "list suppliers with their open POs and buyers." Phase B's
   parameterization choice should let the schema vary per Intent
   shape, not just patch defaults onto the existing shape.

---

### Prompt 4 — Two negations composed

**Natural-language prompt:**

> *"Suppliers in US with no invoices in 6 months and no purchase
> orders in 3 months."*

**Constructed Intent:**

```python
Intent(
    target_entity="Supplier",
    filters=[
        {"type": "country", "value": "US"},
        {"type": "has_no_recent_invoices", "value": {"months": 6}},
        {"type": "has_no_recent_POs", "value": {"months": 3}},
    ],
    include=[],
)
```

**Expected outcome:**

F1 should raise on `has_no_recent_POs`. The interesting question is
how much work would be required to support it: ideally just KG and
mapping-table additions, since the F2 `no_child_in_N_months` pattern
should be reusable.

**Actual outcome:**

```
ERROR generating plan: Intent contains filter types not supported in
v1: ['has_no_recent_POs']. Supported entity-level filters: ['country'].
Supported edge-traversal filters: ['has_no_recent_invoices',
'has_open_PO'].
```

F1 raised cleanly ✓

**Gap classification:** `missing-filter-type`

**Rough size of fix:** `trivial`–`small`. The F2 pattern
(`no_child_in_N_months`) is generic; it already takes `parent`,
`child_edge`, `date_field`, `months_param` as parameters. Adding
`has_no_recent_POs` should be:

1. One row in `kg_pattern_binding` (Supplier + has_no_recent_POs →
   no_child_in_N_months with bindings for PurchaseOrder/HAS_PURCHASE_ORDER/
   OrderDate)
2. One entry in `_EDGE_TRAVERSAL_FILTERS` mapping table
3. One entry in `_FILTER_SOURCE_NAME_SUFFIX`
4. One branch in `_build_iteration_args_with_computed` (it currently
   hardcodes the `invoice_date_after` arg name; needs to generalize
   to the per-tool date-arg name)

Items 1-3 are KG/mapping rows. Item 4 is genuine planner code that
exposes a small generalization gap: F2 generalized the *pattern*
across child entities, but the planner's argument-building code is
still hardcoded for the invoice case. Worth fixing during Phase D
(re-validation) so the planner generalizes too.

**Honest note:** that the F2 pattern generalized cleanly (items 1-3
are mostly KG additions, not code) is good news for the architecture.
The hardcoded date-arg name in item 4 is the small wart that proves
the F2 abstraction wasn't quite generic enough.

---

### Prompt 5 — Aggregation; different answer shape

**Natural-language prompt:**

> *"What's the total open PO value by buyer? Top 5 buyers by total."*

**Constructed Intent:**

```python
Intent(
    target_entity="Buyer",
    filters=[
        {"type": "po_aggregate_top_n", "value": {"metric": "Ordered", "n": 5}},
    ],
    include=[],
)
```

**Expected outcome:**

F1 should raise on `po_aggregate_top_n`. Even if accepted, the
executor has no aggregate or sort capability, and the synthesizer
schema can't represent ranked aggregates.

**Actual outcome:**

```
ERROR generating plan: Intent contains filter types not supported in
v1: ['po_aggregate_top_n']. Supported entity-level filters: ['country'].
Supported edge-traversal filters: ['has_no_recent_invoices',
'has_open_PO'].
```

F1 raised cleanly ✓

**Gap classification:** `missing-filter-type`, `schema-too-narrow`,
plus an architectural gap in the executor (no aggregation)

**Rough size of fix:** `large`. This prompt class needs all three of:

1. An intent parser that produces aggregate-shaped Intents (Phase C)
2. A planner that can express aggregation/rank — this is a NEW step
   shape on top of the current non-iterating / iterating /
   filter-source-when-empty trio (medium-to-large; possibly Phase D
   extension, possibly its own phase)
3. A flexible synthesizer schema that can represent "buyer X has
   total $Y" rows (Phase B)

The current architecture is built for "filter parent entities by
child-entity attributes." Aggregation flips the relationship: now
you're computing OVER the children grouped BY the parent. That's a
different shape of query and probably needs a new pattern type in the
KG (`aggregate_children_by_parent` or similar).

Honest assessment: this is the prompt class where Design 3 needs the
most new work to support. Not a small extension.

---

### Prompt 6 — Out of scope: contracts

**Natural-language prompt:**

> *"Show me contract renewals due next quarter."*

**Constructed Intent:**

```python
Intent(
    target_entity="Contract",
    filters=[
        {"type": "renewal_due_in", "value": {"period": "next_quarter"}},
    ],
    include=[],
)
```

**Expected outcome:**

The KG has no Contract entity, no contract MCP tool. Planner should
raise.

**Actual outcome:**

```
ERROR generating plan: Intent contains filter types not supported in
v1: ['renewal_due_in']. Supported entity-level filters: ['country'].
Supported edge-traversal filters: ['has_no_recent_invoices',
'has_open_PO'].
```

F1 raised on the unknown filter type FIRST. ✓

**Gap classification:** `genuinely-out-of-scope` (until contract
support is built) plus a smaller error-message concern

**Rough size of fix:** `large` (to support contracts) or `none` (to
keep refusing them — which is the correct behavior for now).

**Honest note on the error message:** F1's error said the filter type
is unknown, but the REAL reason this prompt can't be answered is that
the system has no concept of contracts AT ALL (no entity, no tool, no
addresses in Fusion mapped to contract data). A user reading
"`renewal_due_in` is not supported" might reasonably ask "OK, what
contract filters ARE supported?" — and the answer is "none, because
we don't support contracts." The error message is technically correct
but misleading at the user-facing level.

This is the kind of issue the eventual intent parser should handle:
when a user asks about an entity the system doesn't know, the parser
should say "I don't have access to contract data" rather than letting
the planner produce a `renewal_due_in` error. Captured for Phase C.

---

### Prompt 7 — Ambiguous (not constructible)

**Natural-language prompt:**

> *"Who's our best supplier?"*

**Constructed Intent:**

```
None — cannot be constructed.
```

**Why this is in the gap analysis:**

"Best" has no defined metric. By spend? By PO count? By reliability?
By recency? Different stakeholders would mean different things. No
defensible Intent exists.

Today, this prompt has no path through the system: no `--intent`
choice for it, no LLM intent parser to ask a clarifying question.
The prompt simply has no entry point.

**Actual outcome:** N/A — not runnable.

**Gap classification:** `needs-intent-parser`

**Rough size of fix:** `large` — Phase C of the roadmap.

---

## Summary

| # | Prompt | Outcome | Gap classification | Size of fix |
|---|---|---|---|---|
| 1 | UK suppliers + open POs | ✓ Works | works | N/A |
| 2 | POs over $100k | F1 raised | missing-filter-type + missing-mcp-tool | medium |
| 3 | List India suppliers | ⚠ Works partially | schema-too-narrow | medium |
| 4 | Two negations | F1 raised | missing-filter-type | trivial-to-small |
| 5 | Aggregation by buyer | F1 raised | multiple architectural gaps | large |
| 6 | Contracts | F1 raised (misleading message) | genuinely-out-of-scope | large (or none) |
| 7 | "Best supplier" | N/A | needs-intent-parser | large |

### Honest findings

**What works:**
- **Country generalization is real.** Prompt 1 (UK) succeeded
  end-to-end with the same pipeline shape as the US anchor. The
  architecture isn't secretly US-only.
- **F1 catches what it's supposed to catch.** Four prompts with
  unknown filter types were stopped cold, with clear error messages
  naming both what's missing and what's supported.
- **The negation pattern (F2) was generalized at the KG level, not
  the planner level.** Prompt 4 reveals this is mostly true — adding
  has_no_recent_POs is mostly KG additions plus one small generalization
  in `_build_iteration_args_with_computed`.

**What doesn't work as well as the 7/7 anchor suggested:**
- **Synthesizer schema is too narrow.** Prompt 3 surfaced that the
  schema silently drops suppliers it can't fully describe. The 7/7
  score was on a query whose answer shape exactly matched the
  hardcoded schema; once the query asks for less (no POs, no
  buyers), the structured output goes empty.
- **Error messages aren't user-facing.** Prompt 6's error tells the
  truth at the technical level but doesn't help a user understand
  the actual gap. This is intent-parser territory (Phase C).
- **The architecture has real limits for aggregate-shaped queries.**
  Prompt 5 isn't a minor extension; it's a different query shape.

**What's not yet measured:**
- Variance — only one run per prompt. F4 used 3 runs because the
  synthesizer is non-deterministic; Phase A used 1 because most
  prompts didn't reach the synthesizer. Worth re-running Prompts 1
  and 3 a few times if synthesizer behavior on them turns out to
  matter.

### How this changes the roadmap

The roadmap (`docs/designs/design3_v1_to_production_roadmap.md`) was
written before Phase A's findings. Now that we've measured, the
roadmap holds up, but two adjustments are worth surfacing for the
start of Phase B:

1. **Phase B's parameterization choice should be informed by
   Prompt 3 and Prompt 5.** Prompt 3 needs the existing schema to
   gracefully degrade (suppliers with no PO/buyer data still appear);
   Prompt 5 needs a fundamentally different schema (ranked
   aggregates). A single schema parameterization needs to handle
   both extremes.

2. **Phase D's "fix what Phase A revealed" list should include the
   small generalization in `_build_iteration_args_with_computed`** so
   that adding `has_no_recent_POs` is purely KG work, not Python
   changes. Small fix; high value as a proof that F2's abstraction
   is solid.

Nothing in Phase A's findings invalidates the overall A→F sequence.
The work proceeds.

---

## Trace files

- `traces/2026-05-26T19-51-20-988312.jsonl` — Prompt 3 (India)
- `traces/2026-05-26T19-51-43-686286.jsonl` — Prompt 1 (UK)
- Prompts 2, 4, 5, 6 raised at plan-generation time; no MCP session;
  no trace files written (the planner error happens before the trace
  logger is fully engaged for execution events).
- Prompt 7 not run.
