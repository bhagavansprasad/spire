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

**Effort:** medium per shape.

---

### 8. Graceful refusal for unsupported prompts

**Status:** open — NEXT. Partially set up by feature 1.

**What:** Turn the parser's structured refusal into a polished,
capability-framed user message generated from the KG. Feature 1 already
detects out-of-scope prompts and returns a `Refusal` (flavor + facts)
and `run_plan.py` exits 4; feature 8 adds the gracious wording and
derives the correct flavor from the KG (today a self-declared refusal
maps to UNPARSEABLE even when it's really UNKNOWN_ENTITY / aggregation).

**Why:** Closes G5 in part. The current refusal is honest but blunt.

**Dependencies:** 1 (done).

**Effort:** small.

---

## Execution order

### Phase one: foundation — DONE
**2 -> 3 -> 4 -> 5.** Closed known gaps, strengthened the tool layer.

### Phase two: architectural shift — feature 1 DONE, feature 8 NEXT
**1 -> 8.** NL parser landed. 8 (graceful refusal wording) follows.

### Phase three: capability expansion
**6, 7 (parallel, as demand surfaces).** Demand-driven; don't build
preemptively.

---

## Backlog summary

| # | Feature                                  | Effort  | Status | Closes |
|---|------------------------------------------|---------|--------|--------|
| 2 | Invoice date upper bound                 | small   | done   | G1     |
| 3 | Supplier status filter                   | small   | done   | G2     |
| 4 | Migrate remaining tools to ToolResult    | medium  | done   | G3     |
| 5 | Synthesizer schema generalization        | medium  | done   | —      |
| 1 | Natural-language entry                   | large   | done   | —      |
| 8 | Graceful refusal                         | small   | open (next) | G5 |
| 6 | New entity: contracts                    | small-medium | open | —    |
| 7 | Aggregation tools                        | medium  | open   | G4     |

Features 1–5 verified against the live Fusion pod. Feature 1 also
verified against live Gemini (parser integration suite green).

---

## Component lifecycle

### Track A agent — retire after Design 3 is proven

The Track A agent (`ask.py` -> `runner.py`, the LLM-as-planner baseline)
is **not** part of the Design 3 runtime and is never invoked by the
Design 3 pipeline. It is kept solely as the **evaluation baseline** —
the comparison arm that justifies the Design 3 architecture.

- **Keep until** Design 3 consistently produces valid results —
  specifically, until the feature-1 parser-driven path has been run
  against the agent baseline and the before/after comparison is recorded.
- **Then** the agent has served its purpose and should be deleted.
- **Do not** remove it before that comparison exists — doing so destroys
  the ability to demonstrate the before/after that justifies feature 1.
- **Rationale:** the repo is still a POC; in the "prove the architecture"
  phase the baseline earns its keep.
