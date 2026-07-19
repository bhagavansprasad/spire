# Feature 7 — Aggregation: Design

**Status:** design settled, not yet built. Companion to `docs/feature_roadmap.md`
(feature 7) and the `docs/designs/feature_1_nl_parser_design.md` parser design.

**Settled in:** brainstorming session (this doc is its output). The roadmap
required a design before work starts; this is that design. A build session can
implement against it without re-litigating the decisions below.

---

## 1. Problem

Spire answers "show me invoices from supplier X" — it fetches rows and returns
them. It cannot answer "top 10 suppliers by spend." That question needs *math
over many rows*: group invoices by supplier, sum the amounts, sort, take the
top N. The existing pipeline returns rows; aggregation returns computed numbers
over rows. That is the gap (closes G4).

The math never runs in the LLM. LLMs are unreliable at arithmetic over many
rows and the rows would not fit in context anyway. A Python tool does the math;
the LLM only interprets the prompt and phrases the answer.

---

## 2. Architecture: a tool, not a path

Aggregation is a **specific tool the planner routes to** — not a new pipeline
path and not a general aggregation engine.

- The LLM parser reads the prompt and emits an aggregation Intent.
- The planner deterministically maps that Intent to a named tool. The planner
  does not "decide" in any clever sense — it routes, the same way it routes a
  list Intent to `search_invoices` today.
- The tool fetches, filters, and computes — all in Python, all inside itself.
- The synthesizer phrases the structured result.

No control-flow branching is introduced. Routing-an-Intent-to-a-tool *is* the
architecture, and it already exists. This preserves the Design 3 property that
failures pin to a specific stage: a bad aggregate lives in one named tool.

This was reached after explicitly considering and rejecting alternatives that
branch the pipeline on an "is this aggregation?" flag (a type-branch, a unified
path with an optional aggregation tail, or a late branch after a shared
fetch+filter). All three are unnecessary once aggregation is a tool: the tool
owns its own fetch+filter+math, so there is no shared step to branch and no
drift between paths.

---

## 3. First tool: `aggregate_invoices_by_supplier`

**Inputs**
- `date_from`, `date_to` — the range. Pushed down into the fetch (filter goes
  to Fusion), so out-of-range invoices are never read.
- `top_n` — number of suppliers to return.

**Logic**
1. Fetch invoices in `[date_from, date_to]` (filter at source).
2. Group by supplier (Python).
3. Sum invoice amount per supplier.
4. Sort by spend descending, then supplier name ascending.
5. Take `top_n`.

**Fixed by identity (not parameters)**
- Grouping is by supplier and the measure is sum-of-spend. Both are baked into
  the tool's identity. A different grouping or measure is a *different tool*,
  never a parameter on this one. (See the boundedness rule, §6.)

**Determinism rules**
- Ties at the `top_n` boundary: cut at exactly `top_n`. The name-ascending
  secondary sort makes "the Nth supplier" the same supplier on every run, so
  the cut is deterministic rather than arbitrary.
- Exactly `top_n` rows returned (or fewer only when fewer suppliers exist).

**Output** (`shape: "supplier_spend_ranking"`)
```
{
  shape: "supplier_spend_ranking",
  date_from: "2026-01-01",
  date_to: "2026-03-31",
  total_suppliers: 47,        # distinct suppliers in range, before the top_n cut
  returned: 10,               # rows actually returned
  rows: [
    { supplier: "Acme",   total_spend: 482000, invoice_count: 31 },
    { supplier: "Globex", total_spend: 391500, invoice_count: 22 },
    ...
  ]
}
```
- `total_suppliers` vs `returned` preserves truncation honesty (the
  feature 4/5 theme): the synthesizer can say "top 10 of 47" instead of
  implying 10 is all there are.
- `invoice_count` is cheap to compute while summing and gives useful context.
- The output is fully self-describing — everything the synthesizer needs to
  phrase an honest sentence is present. This is what makes deferring the
  synthesizer (§5) safe.

**Empty result**
- Zero matching invoices returns a well-formed empty ranking
  (`total_suppliers: 0`, `returned: 0`, `rows: []`) — never an error. The
  synthesizer later phrases "no invoices in that range." Closing this at the
  tool level (not the synthesizer) keeps the deferral in §5 safe.

---

## 4. Intent vocabulary and routing

**Vocabulary.** The aggregation Intent carries `group_by`, the measure (implied
by the chosen tool, not a free field), the date range, and `top_n` — enough for
the planner to map deterministically to the tool.

**Who reads the prompt signal.** The *parser* (the LLM), never the planner. The
planner has no language understanding by design; it only maps structured Intent
to a tool. So the parser must already have turned "top 10 by spend" into
structured aggregation vocabulary.

**Routing decision**
- Aggregation signal present (e.g. "top", "by", "total", "how many") →
  aggregation Intent → planner routes to the matching `aggregate_*` tool.
- No signal, or ambiguous (e.g. bare "suppliers in Q1 2026") → **default to
  list.** List is the safer, cheaper, more common shape; aggregation is the
  rarer ask, so defaulting away from it rarely surprises anyone. Refusing a
  perfectly answerable list prompt would be too aggressive.

---

## 5. Synthesizer: deferred (deliberately)

The synthesizer phrasing layer is **not** designed here. It is deferred until
all aggregation prompt shapes are settled, so it can be written once against the
full set of shapes rather than piecemeal per tool.

This deferral is safe **only because** the tool output is fully self-describing
(§3): no honest sentence the synthesizer needs to write later is made impossible
by missing data. When the synthesizer is built, it gets a schema branch keyed on
`shape` (parallel to feature 5's per-entity schemas) — an aggregation result is
a ranking with metadata, not a row set, so it needs its own branch. It should
phrase the ranking, the date range, the "top N of M" truncation, and the empty
case.

---

## 6. Boundedness rule (what keeps this from becoming an engine)

The roadmap says "specific tools per shape, not a generic engine." Made
concrete and applicable:

- A new aggregation shape = a **new named tool**, added demand-driven, not built
  ahead.
- Each tool fixes its grouping and its measure as part of its identity.
- **The line:** parameters may shape the *input and output size* (date range,
  `top_n`) but never the *operation* (grouping, measure). Adding a `group_by` or
  `measure` parameter to an existing tool is exactly the move that turns N tools
  into one engine — forbidden.

**Naming convention.** Aggregation tools are prefixed `aggregate_`
(`aggregate_invoices_by_supplier`, future `aggregate_spend_by_buyer`, …). This
is a *convention*, not a safety guard: it gives the parser a predictable pattern
to emit and makes the code readable, which lowers the chance of a malformed
name. It does **not** prevent hallucination. The actual hallucination defense is
KG-menu validation — a tool name the parser emits must resolve to a tool
declared in the KG menu, or it falls to graceful refusal (feature 8). That guard
works regardless of naming; the prefix just makes correct names more likely.

---

## 7. Same data, different operation

`search_invoices` (list) and `aggregate_invoices_by_supplier` (aggregate) read
the **same** invoice source in Fusion. The difference is the operation, not the
data: the list tool returns rows, the aggregation tool sums them. Both push the
date filter down to the same source and read only in-range rows. Aggregation
does not fork or duplicate the data layer.

---

## 8. Decisions log (so they are not re-litigated)

1. Aggregation is a tool the planner routes to — not a pipeline branch, not an
   engine.
2. Measure and grouping are fixed per tool, never parameters.
3. Tie at the `top_n` boundary → cut at exactly `top_n`, name-ascending
   tiebreaker for determinism.
4. Empty result → well-formed empty ranking at the tool level, not an error.
5. Routing signal is parser-read; ambiguous prompts default to list.
6. Synthesizer phrasing deferred until all shapes are settled; safe because tool
   output is self-describing.
7. `aggregate_` prefix is a convention for readability/parser-predictability;
   KG-menu validation is the hallucination defense.

---

## 9. Open / out of scope for this design

- Synthesizer phrasing (deferred, §5).
- Tool #2 and beyond — defined by demand, per the boundedness rule (§6).
- Unchanged by this design: feature 6 (contracts) and the carried loose ends in
  the handoff (agent removal, cosmetic refusal noun, password rotation).

*End of design doc.*
