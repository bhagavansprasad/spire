# Feature Roadmap

The set of features taking Spire from "works on hand-built intents" to
"works on natural language across common procurement queries."

This is the *what* and *why* document. Design and implementation
details for each feature are written when work on that feature
starts — not in advance, so they don't go stale.

Companion: `docs/prompt_coverage.md` — the gap analysis that surfaced
most of these features.

---

## Scope for v1

**Audience:** internal consultants and end users (procurement/finance).

**Bar for "done":** depth before breadth. Handle a focused set of
common prompts very well, with honest refusal on the rest. Broaden
coverage in a follow-up cut.

**Out of scope for v1:** production hygiene (caching, observability,
deployment), domains beyond procurement.

---

## Features

### 1. Natural-language entry to Design 3

**Status:** done (implemented + verified live). See
`docs/designs/feature_1_nl_parser_design.md`.

**What:** An LLM-driven layer that converts a natural-language prompt
into an Intent. The Intent is what the deterministic planner already
consumes today.

**Why:** Today every prompt shape requires a hand-built Intent in
`run_plan.py`. Doesn't scale. This is the single largest unlock —
removes the bottleneck on what prompts the system can handle.

**Bounded by:** the KG. The parser can only produce Intents using
entities, filters, and patterns the KG declares. Anything outside
that returns a clear "can't answer" Intent.

**Dependencies:** 5 (satisfied).

**Effort:** large.

---

### 2. Invoice date upper bound

**Status:** done. Closes G1.

---

### 3. Supplier status filter

**Status:** done. Closes G2.

---

### 4. Migrate remaining tools to ToolResult

**Status:** done (search_suppliers + search_purchase_orders; get_buyer
intentionally not migrated — single unique-key lookup). Closes G3.

---

### 5. Synthesizer schema generalization

**Status:** done. Three sibling per-entity schemas selected by
target_entity.

---

### 6. New entity: contracts

**What:** Add Contract to the KG (entity, fields, edges, vocabulary).
Build `search_contracts` tool.

**Why:** "Contract renewals due next quarter" fails today because
Contract isn't in the system. Adds a new data domain.

**Dependencies:** ideally after 1, 4, 5 — so contracts get NL-parsed
entry, truncation honesty, and flexible schema.

**Design:** pending a brainstorming session before work starts.

**Effort:** small to medium.

---

### 7. Aggregation tools

**What:** Tools that aggregate server-side, returning small structured
results. First: `aggregate_invoices_by_supplier` with date range and
top_n. More as prompts demand.

**Why:** Closes G4. "Top 10 suppliers by spend" etc. The LLM never does
math; the tool aggregates in Python.

**Note:** keep aggregation shapes bounded — specific tools per shape,
not a generic engine.

**Dependencies:** parser (1) should route aggregation prompts here.

**Design:** pending a brainstorming session before work starts.

**Effort:** medium per shape.

---

### 8. Graceful refusal for unsupported prompts

**Status:** done. Closes G5 in part.

**What:** Turns the parser's structured refusal into a polished,
capability-framed user message generated from the KG. New
`capability.py` module: `derive_flavor` re-derives the correct flavor
from the draft + KG menu (a self-declared refusal naming an unknown
entity is now UNKNOWN_ENTITY, aggregation is UNSUPPORTED_OPERATION,
genuinely vague prompts stay UNPARSEABLE); `capability_message` builds
the user-facing wording — what Spire can do (from the KG menu, so it
never goes stale) plus why the prompt is outside it. Wired into
`run_plan.py`'s refusal printer.

**Why:** Closed G5 in part. The feature-1 refusal was honest but blunt
and mislabeled self-declared refusals.

**Dependencies:** 1 (done).

**Effort:** small.

---

## Execution order

### Phase one: foundation — DONE
**2 -> 3 -> 4 -> 5.** Closed known gaps, strengthened the tool layer.

### Phase two: architectural shift — DONE
**1 -> 8.** NL parser landed; graceful refusal wording landed.

### Phase three: capability expansion — NEXT
**6, 7 (parallel, as demand surfaces).** Demand-driven; don't build
preemptively. Design for each is settled in a brainstorming session
before work starts.

---

## Backlog summary

| # | Feature                                  | Effort  | Status | Closes |
|---|------------------------------------------|---------|--------|--------|
| 2 | Invoice date upper bound                 | small   | done   | G1     |
| 3 | Supplier status filter                   | small   | done   | G2     |
| 4 | Migrate remaining tools to ToolResult    | medium  | done   | G3     |
| 5 | Synthesizer schema generalization        | medium  | done   | —      |
| 1 | Natural-language entry                   | large   | done   | —      |
| 8 | Graceful refusal                         | small   | done   | G5     |
| 6 | New entity: contracts                    | small-medium | open | —    |
| 7 | Aggregation tools                        | medium  | open   | G4     |

Features 1–5 verified against the live Fusion pod. Feature 1 also
verified against live Gemini (parser integration suite green).

---

## Component lifecycle

### Track A agent — cleared for removal

The Track A agent (`ask.py` -> `runner.py`, the LLM-as-planner baseline)
is **not** part of the Design 3 runtime and is never invoked by the
Design 3 pipeline. It was kept as the evaluation baseline — the
comparison arm that would justify the Design 3 architecture.

**Decision: the baseline comparison will not be run.** Design 3 / Way 2
is the committed architecture; the agent's only remaining job was to
justify that choice, and the choice is made. So the agent is now
**cleared for removal** — its lifecycle no longer gates on a comparison
that won't happen.

Code to remove when the cleanup is done:
- `scripts/ask.py` (the agent entry point)
- `src/spire/agent/` (`runner.py`, `prompts.py`, `lg_utility.py`,
  `tracing.py` — confirm `tracing.py` isn't shared by `run_plan.py`
  before deleting it)
- `tests/test_agent_runner.py`, `tests/test_prompts.py`
- `inspect_trace.py` is agent-shaped and doesn't parse `run_plan`
  traces; remove or repoint as part of the same cleanup.

Not yet deleted — this is a tracked, deliberate cleanup step, not done
in passing.

### Design 3 (Way 2) is deliberately NOT an agent

Design 3 is not an agentic architecture and is not meant to become one.
The LLM is bounded to two single-shot roles — the interpreter (the
feature-1 parser) and the synthesizer — with a deterministic planner and
executor in between. There is no tool-calling loop, no
`assistant -> tools -> assistant` cycle, no LLM-driven control flow. This
is the property that makes the pipeline predictable and its failures
attributable to a specific stage, and it is the defining difference from
the Track A agent. Future features add bounded tools and schemas; they do
not reintroduce agent-style orchestration.
