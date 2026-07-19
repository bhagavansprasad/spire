# Design 3 v1.1 → Production Roadmap

**Date:** 2026-05-26
**Author:** Bhagavan (with Claude)
**Status:** Plan — not yet executed. Phase A is the first piece of
work. Phases B-F lock the order and shape; their internal details
are sketched here but should be re-confirmed at the start of each
phase based on what earlier phases revealed.

---

## Where we are starting from

Master is at commit `6b8979d`. Design 3 v1.1 scores 7/7 on the
original Track A prompt across three runs (see
`docs/design3_measurement_report.md`).

What works:
- KG-driven deterministic planner (102 unit tests)
- Plan executor against 5 MCP tools, including negation-by-absence
  (45 unit + 3 integration tests)
- LLM-based structured-output synthesizer with hallucination guard
  (22 unit + 1 integration tests)
- End-to-end script `scripts/run_plan.py` with `--intent` arg

What is hardcoded (and limits the system):
- The Intent itself (no natural-language parser — caller hands the
  parsed Intent to `run_plan.py` via `--intent` choice)
- The synthesizer schema (`SynthesizedResponse` is specific to the
  "suppliers + buyers" answer shape)
- All filter-type → KG-pattern mappings live in Python constants in
  `planner.py`, not in the KG

What is unmeasured:
- Anything other than the one Track A prompt
- Performance under any non-trivial workload
- Behavior on intentionally adversarial or out-of-scope prompts

---

## The roadmap at a glance

| Phase | What | Why this order | Size estimate | Done when |
|---|---|---|---|---|
| **A** | Gap analysis on diverse prompts | Cheapest, highest signal; shapes B–E | Half day | Gap document committed; sized list of fixes |
| **B** | Schema generalization (synthesizer) | Unblocks C (parser needs to know answer shapes) | 2-3 days | Synthesizer accepts intent-derived schema; tests prove ≥2 distinct answer shapes work |
| **C** | LLM intent parser | Top of pipeline, the last hardcoding | 3-4 days | NL prompt → Intent works for ≥3 prompt classes; ≥1 integration test per class |
| **D** | Re-validate against Phase A prompts | Real generalization test | 1-2 days | All Phase A prompts run end-to-end; rubric-style score per prompt; report committed |
| **E** | Production hygiene | After we know real workload shape | 3-5 days | Parallelization + caching + observability + error hardening; perf report |
| **F** | Handoff documentation | Last; can only be true once E lands | 1-2 days | Architecture doc + runbook + decision log committed |

**Total: roughly 2-3 weeks of focused work.** Each phase has explicit
approval gates; we don't proceed to phase N+1 without finishing N.

---

## Phase A — Gap analysis on diverse prompts

### Goal

Pick a small set of deliberately diverse prompts and walk each one
through the system *as it stands today*. Catalog what raises, what
silently does the wrong thing, what's missing, and what would need
to be built to handle it.

**Do not build fixes during Phase A.** Just measure and document.
Fixing the gaps is what Phases B-E are for.

### Why this comes first

Without Phase A, we'd plan B-E based on guesses about what's
needed. With Phase A, we plan B-E based on what we actually saw
fail. F1 was a perfect example: we couldn't even *see* the silent-
drop defect until we tried to measure the system honestly. Phase A
is the same idea at a larger scope.

### Sub-tasks

**A.1** — Pick 5-7 prompts spanning these categories:
- One that's essentially the Track A prompt with one variable
  changed (e.g., country=UK instead of US). Tests vocabulary
  expansion.
- One with a different `target_entity` (e.g., "show me POs over
  $100k with their supplier and buyer"). Tests whether the planner
  can pivot away from Supplier as the root.
- One with no negation (e.g., "list all suppliers in India"). Tests
  simpler intents still work.
- One with multiple negations (e.g., "suppliers in US with no
  invoices in 6 months AND no POs in 3 months"). Tests pattern
  composition.
- One whose answer shape is fundamentally different (e.g., "what's
  the total open PO value by buyer?" — aggregations, no per-supplier
  output). Tests synthesizer schema limits.
- One deliberately out of scope (e.g., "show me the contract
  renewals due next quarter"). Tests honest "I can't do this" path.
- One ambiguous (e.g., "who's our best supplier?"). Tests how the
  system handles vagueness.

Approval gate: locked prompt list before any measurement runs.

**A.2** — For each prompt, manually construct the `Intent` that the
LLM parser would (eventually) produce. Document why this is the
"right" Intent — capture the reasoning so Phase C's parser can be
held to the same standard.

Approval gate: Intent list reviewed.

**A.3** — For each Intent, attempt to run it via `scripts/run_plan.py`
(extended to take an inline Intent — small CLI tweak). Capture:
- Did the planner accept the Intent? (F1 means unknowns raise.)
- Did the executor run? Counts at each step?
- Did the synthesizer produce a structured response? Or did the
  hardcoded schema break?
- Hallucination guard fire?
- Wall-clock time?

If a step raises, log the raise and move on — do NOT debug or fix
in Phase A.

**A.4** — Write `docs/design3_gap_analysis.md`. One section per
prompt. Each section names: the prompt, the constructed Intent,
the actual behavior, the gap classification (one of: missing-KG-
pattern, missing-filter-type, missing-mcp-tool, schema-too-narrow,
needs-intent-parser, genuinely-out-of-scope), and the rough size of
the fix.

Approval gate: gap analysis reviewed; categorized fixes inform
Phase B and C scope.

### Done criteria

- 5-7 prompts captured with their Intents
- Each run end-to-end (or failure documented honestly)
- Gap analysis doc committed to `docs/`
- A categorized list of fixes that Phases B-E should address

### Size

**Half day** of focused work. Most of the time is in choosing good
prompts and writing the analysis. The runs themselves are 2-3
minutes each.

### Dependencies

None. Can start immediately on master.

### Honest risks

- **The prompts I list above might miss the real failure modes.**
  If you have prompts your consultants actually ask, those should
  replace some of mine. The list above is "Claude's guess at
  diverse"; user-sourced prompts beat any guess.
- **Out-of-scope handling might be terrible.** Today the planner
  raises NotImplementedError; the script catches it but the user
  experience is bad. Phase A documents this; Phases B-E may or may
  not fix it depending on priority.

---

## Phase B — Schema generalization (synthesizer)

### Goal

Replace the hardcoded `SynthesizedResponse` schema with one that's
derived from the Intent's target entity (and possibly its includes).
Make the synthesizer support at least two distinct answer shapes
without code changes per shape.

### Why this order

- Phase A surfaces what answer shapes are actually needed.
- Phase C (intent parser) will produce more shapes than the current
  schema can hold; without Phase B, the parser is blocked by the
  schema.
- Generalizing the schema *before* generalizing the input means we
  can test schema flexibility against the existing planner+executor
  without also debugging a new parser at the same time.

### Sub-tasks

(Detailed plan to be drafted at the start of Phase B based on what
Phase A revealed about the needed shapes. Sketch follows.)

**B.1** — Decide the parameterization model:
- Option (a): per-target-entity schemas (Supplier → SupplierAnswer,
  PurchaseOrder → POAnswer, etc.) Registry pattern.
- Option (b): one fully-generic schema that just nests rows and
  fields. Synthesizer infers what to highlight.
- Option (c): schema is generated dynamically from the Intent's
  target entity + the executor's actual output keys. No registry.

Each option has different tradeoffs in fidelity vs. flexibility.
Decision made AT START of Phase B, not now.

**B.2** — Refactor `src/spire/synthesizer/synthesizer.py`:
- Schema selection layer (based on B.1's decision)
- Update `_collect_valid_ids` to be schema-aware
- Update `_validate_no_hallucinated_ids` to handle multiple schema
  shapes
- System prompt construction parameterized per schema

**B.3** — Move `BuyerInfo` / `SupplierSummary` into a per-shape
module. Add at least one new shape (the one Phase A told us we
need most).

**B.4** — Tests:
- Existing 22 synthesizer tests should still pass (the Supplier
  shape continues to work)
- ≥10 new tests for the new shape (mirroring the existing test
  structure: schema validation, hallucination guard for the new
  ID types, end-to-end with mocked LLM)
- Integration test that the new shape works against live Gemini

**B.5** — Update `run_plan.py` to wire the right schema based on
intent.

### Done criteria

- Synthesizer handles ≥2 distinct answer shapes
- All existing tests still pass
- New tests for the new shape pass
- Integration test against live Gemini for the new shape passes
- The 7/7 measurement on the Track A prompt still reproduces (no
  regression)

### Size

**2-3 days.** Most of the time is in B.1 (deciding the
parameterization model) and B.4 (tests). The actual refactor is
small (~200 lines).

### Dependencies

- Phase A complete (we need to know which second shape to build)

### Honest risks

- **Choice in B.1 is irreversible-ish.** Picking (a) means we add
  schemas one at a time forever; picking (b) means the synthesizer
  is less specific; picking (c) means generation logic is complex.
  This is the biggest decision in the roadmap. Plan to review
  thoroughly at start of B.
- **Hallucination guard generalization is non-trivial.** Today it
  knows about SupplierId, SupplierNumber, PersonId. Different
  schemas reference different ID types. The validator needs to
  know the universe per schema, not globally.

---

## Phase C — LLM intent parser

### Goal

Build the natural-language → `Intent` layer. Until now, the user
provides the parsed Intent via `--intent` flag or via API. Phase C
puts the LLM at the top: user types English, system produces a
validated Intent.

### Why this order

- Phase B generalized the output side; Phase C generalizes the
  input side. Doing them in this order means each phase has a
  stable thing on the other side to test against.
- Doing C before B would mean every new Intent the parser produces
  immediately breaks the synthesizer's hardcoded schema. We'd build
  C twice.

### Sub-tasks

**C.1** — Design the parser's contract:
- Input: a natural-language prompt (string)
- Output: an `Intent` (the existing dataclass)
- Failure modes: ambiguous prompt, out-of-scope prompt, malformed
  filters
- Validation: the parser's output goes through
  `_validate_intent_filters` before reaching the planner

**C.2** — Build `src/spire/intent_parser/intent_parser.py`:
- Pydantic-typed structured output (same pattern as synthesizer)
- System prompt enumerates the valid filter types and their value
  shapes (read from the planner's mapping tables)
- Returns Intent or raises a clear error

**C.3** — Handle ambiguity. Three options to evaluate at start of
phase C:
- Reject ambiguous prompts and ask the user to clarify
- Make a best-guess Intent + flag confidence
- Generate multiple candidate Intents and ask the user to pick
The choice will probably depend on what Phase A revealed about
ambiguity in real prompts.

**C.4** — Tests:
- Unit tests with mocked LLM (similar shape to synthesizer tests)
- Integration tests against live Gemini for each of the Phase A
  prompt categories
- Regression test: the Phase A constructed Intents are reproduced
  by the parser from the corresponding prompts (within reason —
  some variation is acceptable)

**C.5** — Update `run_plan.py` (or add a new `scripts/ask.py`-style
entry point) that takes a natural-language prompt.

### Done criteria

- Parser produces Intents for ≥3 prompt classes from Phase A
- Each class has ≥1 integration test against live Gemini
- Existing pipeline (planner → executor → synthesizer) unchanged;
  parser is purely additive at the top
- 7/7 measurement on Track A prompt still reproduces, now starting
  from the natural-language prompt instead of a hardcoded Intent

### Size

**3-4 days.** Bigger than B because parsing is harder than
synthesis (more ambiguity, more failure modes, more LLM behavior
to validate).

### Dependencies

- Phase B complete (synthesizer can handle the answer shapes that
  the parser will produce intents for)

### Honest risks

- **Ambiguity handling is genuinely hard.** Even with a clear KG
  vocabulary, real prompts use words the KG doesn't cover. The
  parser needs to either expand the vocabulary or honestly say
  "I don't know what 'best supplier' means; can you clarify?"
- **Two LLM calls per request now.** Latency and cost both up.
  Phase E will need to consider whether the parser can be skipped
  for already-structured inputs (API callers don't need NL parsing).

---

## Phase D — Re-validate against Phase A prompts

### Goal

Run the Phase A prompts through the *full* pipeline (parser →
planner → executor → flexible synthesizer) and produce a
generalization report.

This is the real "does Design 3 v1.2 work on more than one prompt"
measurement.

### Sub-tasks

**D.1** — Re-run each Phase A prompt end-to-end. For prompts that
needed new KG patterns / new MCP tools / new schemas to support,
land those fixes first (decided at start of D based on Phase A's
categorized gap list).

**D.2** — Score each prompt against a per-prompt rubric. Same shape
as the Track A rubric, adapted per prompt. Each row asks "did the
right tool get called for the right reason" and "is the final
answer coherent."

**D.3** — Write `docs/design3_generalization_report.md`. One
section per prompt, with the score, the failure modes if any, and
a comparison to the corresponding Phase A "before" measurement.

**D.4** — Honest summary: across N prompts, system achieved ≥X/Y on
M prompts; ≥X/Y on K prompts with caveats; failed on (N-M-K)
prompts because of (reasons). No averaging into a single percentage
(meaningless for prompts of different shapes); per-prompt scores
side by side.

### Done criteria

- Generalization report committed
- For each Phase A prompt, a real measurement result (not a guess)
- Phase A's categorized gap list crossed off (each gap either fixed
  or explicitly deferred with reason)
- Anything that's still broken is documented honestly

### Size

**1-2 days** for the runs and the report. Plus however long the
gap fixes from D.1 take — likely another 2-5 days depending on
what Phase A revealed.

### Dependencies

- Phases A, B, C complete

### Honest risks

- **D.1 is the open-ended part.** "Land the fixes Phase A surfaced"
  could be small (a few KG rows) or large (new MCP tools, new
  executor capabilities). Phase A's sizing will tell us.
- **The generalization report might show real architectural limits.**
  E.g., maybe the planner's three-block structure doesn't fit
  aggregation prompts. If so, we'd surface that honestly and decide
  whether to extend it or call it scope.

---

## Phase E — Production hygiene

### Goal

Make the system handle real production characteristics: latency,
throughput, observability, error recovery.

The 125-second per-run wall-clock from the v1.1 measurement is fine
for a POC; not fine for production.

### Sub-tasks

(Sketch only. Final scope locked at start of Phase E based on what
Phases A and D revealed about workload shape.)

**E.1** — Parallelize iteration steps in the executor:
- `_execute_iterating_step` currently sequential
- `_execute_filter_source_step` currently sequential
- Both should support `asyncio.gather` over per-iteration calls
- Concurrency cap (don't hammer Fusion); start conservative (5?)
- Tests: mocked-MCP correctness under parallelism + load test
  against live Fusion to find the safe concurrency

**E.2** — Add request-level caching:
- Same query against same Fusion endpoint, same args, within same
  run → don't re-fetch
- KG lookups can be cached for the lifetime of the process
- Cache hit/miss metrics in the trace

**E.3** — Observability:
- Per-step latency in trace events
- Tool call counts per Fusion endpoint
- LLM call counts and token usage
- Synthesizer hallucination-guard fire rate

**E.4** — Error hardening:
- Fusion 5xx responses should retry with backoff (not just fail
  the whole plan)
- LLM rate-limit errors should retry
- Partial-result mode? (Today: fail-the-whole-plan; production may
  want "return what we have plus a warning")

**E.5** — Performance measurement: re-run Phase D prompts after
parallelization. Report the latency improvement (and any
correctness regressions if Fusion's rate-limit behavior surfaced).

### Done criteria

- Parallelization safely lands; Track A 7/7 measurement still
  reproduces
- Per-run latency drops measurably (target: <30s for the original
  Track A prompt; subject to Fusion's rate limits)
- Observability metrics visible in traces
- Error-handling decisions documented (retry policy, partial-result
  policy)
- Performance report committed

### Size

**3-5 days.** Highly dependent on what Fusion's rate limits and
error behavior actually look like under load.

### Dependencies

- Phases A, B, C, D complete

### Honest risks

- **Parallelization changes the executor's semantics subtly.** If
  Fusion has rate limits we haven't seen, parallelism reveals them.
  The "fail-the-whole-plan" policy may need to relax.
- **Concurrency cap is a guess until we measure.** Start
  conservative; tune up while monitoring 429s and 5xxs.
- **Caching breaks reproducibility.** A cached result is stale data
  in some sense. Trace metadata needs to make cache hits obvious.

---

## Phase F — Handoff documentation

### Goal

Write the architecture-level documentation that lets someone else
pick this up, extend it, or hand it to a customer.

### Sub-tasks

**F.1** — Architecture overview: one diagram + 2-3 pages of prose.
What's the data flow, where do decisions get made, where are the
extension points.

**F.2** — Decision log: a chronological record of the architectural
calls made across Track A → Design 3 v1.0 → v1.1 → v1.2 → production.
Each entry: what was decided, why, what alternatives were
considered, what we'd revisit.

**F.3** — Runbook: how to add a new MCP tool, how to add a new KG
pattern, how to add a new filter type, how to add a new answer
schema. Each as a worked example.

**F.4** — Performance characteristics: from Phase E, what does the
system actually do under load. Latency, throughput, cost (LLM
tokens), Fusion call counts per typical query.

**F.5** — Known limits: things the system can't do or does badly,
honestly enumerated. Includes the things we deferred during this
roadmap.

### Done criteria

- Documents committed to `docs/`
- A walkthrough: someone reading the docs cold should be able to
  understand the system, run it, and make a small extension
  without needing to read the source first

### Size

**1-2 days.** Writing time. The content is what we know by the end
of Phase E.

### Dependencies

- Phases A through E complete

### Honest risks

- **Documentation rots.** What's true at the end of Phase F won't
  be true in 3 months unless someone maintains it. The runbook is
  the most likely thing to rot first.

---

## What this roadmap does NOT include

Things explicitly out of scope, so we don't accidentally creep:

- **Multi-tenant / multi-pod support.** Today personas.yaml has one
  pod. Production might need many. Out of scope for now.
- **Auth / authorization beyond what the MCP tools already do.**
  Today: basic auth, single user. Out of scope.
- **A UI.** The system stays CLI/API-driven. UI is a separate
  workstream.
- **Comparison against Track A on broader prompts.** Track A
  remains at 1/7 on its one prompt; we're not re-measuring it
  across the Phase A prompt set. Different architecture; the
  comparison would be misleading.
- **Cost optimization.** Gemini Flash is cheap and current usage
  is small. Worth re-visiting if production usage scales 100×.

---

## Working agreements for executing this roadmap

Same as F1-F4:

- Approval gates at the start of each phase AND before any code
  generation within a phase
- Each phase lands on its own branch + PR, the way F1/F2/F3 did
- Honest framing throughout: what we did, what we didn't, what we
  don't know
- Small checkpoints; do not generate 1000-line files without
  approving the scope first
- If a phase reveals that a later phase's plan needs to change,
  pause and re-plan rather than barrel ahead

---

## Open questions to lock before starting Phase A

1. **The Phase A prompt list.** I've sketched 7 prompts. Do you
   want to replace any with prompts your consultants actually ask?
   User-sourced beats Claude-sourced for this.

2. **Phase A timing.** Half a day if focused. Want to start now,
   or close out the F-track first (the housekeeping items I flagged
   after F3 merged: stale SQL files, README update, log update,
   merged-branch cleanup)?

3. **Granularity of approval gates.** F1-F4 used "approve scope
   before generation, then run + share output." Want to keep that,
   or tighten / loosen?
