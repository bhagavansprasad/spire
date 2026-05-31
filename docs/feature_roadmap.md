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

**What:** An LLM-driven layer that converts a natural-language prompt
into an Intent. The Intent is what the deterministic planner already
consumes today.

**Why:** Today every prompt shape requires a hand-built Intent in
`run_plan.py`. Doesn't scale. This is the single largest unlock —
removes the bottleneck on what prompts the system can handle.

**Bounded by:** the KG. The parser can only produce Intents using
entities, filters, and patterns the KG declares. Anything outside
that returns a clear "can't answer" Intent.

**Dependencies:** 5 (synthesizer must accept varied Intent shapes
before the parser starts generating them).

**Effort:** large.

---

### 2. Invoice date upper bound

**Status:** merged (PR #37), live verification pending.

---

### 3. Supplier status filter

**What:** Add `status` parameter to `search_suppliers`. Implement
client-side (Fusion REST rejects `q=Status='...'` on this endpoint).

**Why:** Closes G2. Enables "active suppliers," "inactive suppliers,"
and any status-based filtering. Status field exists in response data;
client-side filtering is viable per curl verification.

**Dependencies:** worth combining with 4 since this tool is in the
unmigrated set.

**Effort:** small.

---

### 4. Migrate remaining tools to ToolResult

**What:** `search_suppliers`, `search_purchase_orders`, and
`get_buyer` start returning ToolResult with truncation metadata.
Today only `search_invoices` and `search_suppliers_by_country` do.

**Why:** Closes G3. Inconsistent honesty across tools today — a broad
supplier query can silently return 25 of hundreds with no signal.
Once all tools report truncation uniformly, both the agent (NL path)
and the synthesizer have complete information.

**Dependencies:** none.

**Effort:** medium (three tools, but each migration is similar to the
earlier two).

---

### 5. Synthesizer schema generalization

**What:** Replace the supplier-rooted `SynthesizedResponse` schema
with one that adapts to the Intent's target entity. An invoice-rooted
query should produce structured invoice output, not be forced into
supplier shape.

**Why:** Today the synthesizer only handles the original prompt
shape. Anything else fits awkwardly or returns empty structured
fields (see `prompt-3` in the gap analysis). Required before 1 lands,
because the NL parser will generate Intents the current schema can't
represent.

**Open design decision:** three options on the table —
per-entity schemas, one generic schema, or schemas generated
dynamically from the Intent. Decision deferred to feature start.

**Dependencies:** none.

**Effort:** medium.

---

### 6. New entity: contracts

**What:** Add Contract to the KG (entity, fields, relevant edges,
vocabulary). Build `search_contracts` tool.

**Why:** "Contract renewals due next quarter" is a real prompt that
fails today because Contract isn't in the system at all. Adds a new
data domain, not just a new filter.

**Dependencies:** ideally lands after 1, 4, 5 — so contracts get the
same NL-parsed entry, truncation honesty, and flexible schema as the
existing entities.

**Effort:** small to medium (one entity, similar shape to existing
ones, but new KG content and one new tool).

---

### 7. Aggregation tools

**What:** Add tools that perform aggregations server-side, returning
small structured results. First: `aggregate_invoices_by_supplier`
with date range and top_n parameters. More to follow as prompts
demand.

**Why:** Closes G4. "Top 10 suppliers by spend," "spend by supplier,"
etc. all fall here. The LLM never does math; the tool fetches and
aggregates in Python, returning a small ranked result the LLM can
present.

**Note on design:** keep aggregation shapes bounded. Add specific
tools per shape rather than building a generic aggregation engine.
If too many shapes accumulate, revisit.

**Dependencies:** parser (1) should know to route aggregation prompts
to these tools.

**Effort:** medium per aggregation shape.

---

### 8. Graceful refusal for unsupported prompts

**What:** When the planner can't handle a request, return a helpful
message instead of raising the F1 loud error. E.g., "This looks like
an aggregation request; aggregation tools aren't available yet."

**Why:** Closes G5 in part. The current loud failure is correct from
a code-safety standpoint but bad UX. Track A handles this gracefully
today; Design 3 should match.

**Dependencies:** 1 (NL parser). Loud failure is fine for hand-built
intents — only matters once real users send arbitrary prompts.

**Effort:** small.

---

## Execution order

Two-phase ordering. Small foundational work first, then the
architectural shift, then capability expansion.

### Phase one: foundation
**Order: 2 → 3 → 4 → 5**

Closes known gaps. Each is independently useful. Builds momentum and
strengthens the tool layer before the parser lands. Roughly a week
of effort across the four.

### Phase two: architectural shift
**Order: 1 → 8**

NL parser is the major investment. 8 follows naturally once 1 is in
place. Roughly a week of focused work.

### Phase three: capability expansion
**Order: 6, 7 (parallel, as demand surfaces)**

New entities and aggregation shapes. Demand-driven; don't build
preemptively.

---

## Backlog summary

| # | Feature                                  | Effort  | Status      | Closes |
|---|------------------------------------------|---------|-------------|--------|
| 2 | Invoice date upper bound                 | small   | merged*     | G1     |
| 3 | Supplier status filter                   | small   | merged*     | G2     |
| 4 | Migrate remaining tools to ToolResult    | medium  | merged*†    | G3     |
| 5 | Synthesizer schema generalization        | medium  | merged*     | —      |
| 1 | Natural-language entry                   | large   | open        | —      |
| 8 | Graceful refusal                         | small   | open        | G5     |
| 6 | New entity: contracts                    | small-medium | open   | —      |
| 7 | Aggregation tools                        | medium  | open        | G4     |

\* **merged** = code merged to master (PR #37), but **live verification
against the Fusion pod is still pending** (auth unavailable at merge
time). Not yet `done`. Before marking `done`:
- grep executor/planner/synthesizer for callers expecting `list[dict]`
  from the two migrated tools (static, no auth needed)
- `pytest tests/` with `personas.yaml` present
- confirm supplier `Status` vocabulary (docstrings currently guess
  ACTIVE/INACTIVE)

† Feature 4 migrated `search_suppliers` and `search_purchase_orders`
only. `get_buyer` was intentionally left unmigrated — it's a single
unique-key lookup, so truncation metadata is meaningless. Feature 4 is
considered complete in scope despite this.