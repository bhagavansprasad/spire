# Prompt-to-Intent Framework — Design

Status: **Proposed** (design only; implementation to follow in increments)
Branch: `feat/prompt-to-intent-framework`
Builds on: Phase 1 parser context modularization
(`docs/features/parser_context_modularization.md`) — the 48 module-partitioned
`.sysprompt` blocks, the `order.manifest` assembly, the `parse(system_prompt=…)`
seam, and the `kg_entity.module` mapping are all prerequisites this work uses.

---

## 0. What this is, in one paragraph

Spire turns a natural-language prompt into an `Intent` (via the LLM parser),
then turns that `Intent` into a selected MCP tool (via a deterministic KG
lookup), then executes. Two problems have emerged at the prompt→intent boundary:
the parser sends an **all-modules** system prompt (~8,000 tokens) on every
request, which is at its token ceiling and cannot absorb new capability without
risking runaway generation; and when a new prompt misbehaves, there is **no
cheap way to see where it broke** — was the Intent wrong, or was the tool
selection wrong? This design adds two things: a **module-scoping router** that
classifies a prompt to its Fusion module(s) and parses against only that
module's context (solving the token ceiling structurally), and a **generic
prompt→intent→tool-selection validation framework** that, for any prompt in any
module, reports exactly which boundary failed — with **no tool execution**.

---

## 1. The core problem

### 1.1 The token ceiling blocks new capability
The parser's system prompt is the union of all four Fusion modules' guidance
(payables, procurement, receivables, supplier) plus cross-cutting concerns.
Phase 1 split this monolith into per-module `.sysprompt` blocks, but **production
still assembles and sends all of them** — the split organized the text without
changing what is sent. The assembled preamble is ~8,000 tokens and empirically
fragile: LLM-visible additions have tipped certain phrasings into MAX_TOKENS
runaway (observed 3× on issue #32). So any new capability that must be taught to
the parser — e.g. "top-N invoices by amount is supported" — cannot simply be
added to the prompt; there is no headroom.

The structural fix is **not** to keep trimming the prompt, but to stop sending
the whole thing. A prompt about invoices does not need supplier, procurement,
and receivables guidance. If the parser only received the payables context
(~2,000 tokens), the ceiling would cease to bind and new capability could be
taught in the relevant module with room to spare.

### 1.2 Failures are not localized
When a prompt produces a wrong or refused answer, the current tools do not say
*where* it went wrong. The `score_parser_prompts.py` harness validates
prompt→intent, but stops there. The next boundary — intent→tool-selection (the
planner's KG lookup) — is unvalidated in isolation. So a failure could be the
parser producing a wrong `Intent`, or the parser producing a correct `Intent`
that the planner then maps to the wrong tool (or no tool), and telling these
apart currently requires manual tracing. For a system meant to accept *any*
prompt, this is the wrong debugging posture: a new prompt that fails should
announce its failure point.

---

## 2. The solution, in two parts

### 2.1 The module-scoping router (produces the Intent)
A two-request flow replaces the single all-modules parse:

```
user prompt
  → [classify]      one small LLM call: "which Fusion module(s)?"  → e.g. ["payables"]
  → [assemble]      core + refusals + the named module(s) only     (not all four)
  → [parse]         parse(prompt, system_prompt=scoped)             (existing seam)
  → Intent
```

The classifier is cheap and separate. The parse it feeds is now **smaller**
(scoped to one module), so total tokens typically drop even with the extra call,
and — crucially — the scoped prompt has headroom for new capability.

### 2.2 The validation framework (checks two boundaries, no execution)
A generic harness that, for any prompt in any module, traces and validates:

```
PROMPT
  ├─ Stage 1: prompt → intent            (does the parser produce the expected Intent?)
  └─ Stage 2: intent → tool-selection    (does the planner's KG lookup pick the expected tool?)

  ✗ NO execution — no MCP call, no tool invocation, no results.
```

Stage 1 is what `score_parser_prompts.py` already does. Stage 2 is new: run the
planner's deterministic tool-selection on the produced `Intent` and check which
tool it *would* call — without calling it. The framework is **module-agnostic by
construction** (it reads the KG); invoices today, but supplier / PO / AR prompts
work the same way. Execution and result-correctness are explicitly out of scope
— Spire already has end-to-end scripts for that, and this framework is about
isolating *where* prompt→intent→tool-selection breaks, not re-testing execution.

---

## 3. Design decisions (locked)

These were resolved during design and govern the router's shape.

**D1 — The classifier returns a *list* of module names, not a single string.**
Even in the single-module case it returns `["payables"]`. Rationale:
increment 2 (cross-module prompts) will need multiple modules; a list keeps the
contract stable so union support does not force a caller refactor. `assemble_subset`
already accepts a collection, so a list drops straight in.

**D2 / D3 — The classifier is grounded in entity names *and* entity-synonyms,
per module, generated from the KG.**
The classifier's prompt lists, for each module, its entities (from
`kg_entity.module`) and their colloquial synonyms (from `kg_vocabulary` where
`vocab_kind = 'entity_synonym'`). Rationale: the strongest signal for which
module a prompt targets is which entity it names, and synonyms catch colloquial
phrasing ("vendor" → Supplier, "bill" → Invoice, "AR invoice" →
ReceivablesInvoice) so the classifier is unlikely to misroute. Scoped to
`entity_synonym` only — other vocab kinds (field synonyms, statuses, countries)
do not inform module choice and would only add noise. Generated from the KG so
it stays in sync automatically.

**D4 — The classifier context is generated into a committed file, read and
cached at import.**
A generator queries the KG and writes a `.sysprompt`-style file; the router
reads it once at import and caches it. Rationale: consistency with Phase 1
(generated, committed, readable, byte-stable prompt content), auditability (the
routing prompt can be read and diffed in a file), and no per-request DB
dependency. A tripwire keeps it in sync with the KG, as with the KG row-count
tripwires.

**D-router — The router is a separate layer *around* `parse`, not inside it.**
A `route_and_parse(prompt)` unit calls the classifier, assembles the subset, and
calls the unchanged `parse(prompt, system_prompt=scoped)`. Rationale: single
responsibility (`parse` does prompt+context→Intent; the router decides the
context), independent testability of the classifier, `parse` stays frozen, and a
clean home for the increment-2 fallback logic. The graph pipeline calls
`route_and_parse` instead of `parse`.

---

## 4. Scope and increments

### Increment 1 — single-module happy path (this effort)
- Classifier returns exactly one module for cleanly single-module prompts.
- Scoped assembly = Tier 1 (core + refusals) + the one module.
- `route_and_parse` wires classifier → assemble → parse.
- **Fidelity check:** for single-module prompts, `route_and_parse(prompt)` must
  produce the **same Intent** as `parse(prompt)` with the full all-modules
  context. Routing must change the token cost, not the Intent.

### Increment 2 — cross-module + fallback (deferred)
- Classifier may return multiple modules; assembly unions their blocks.
- "Unsure" → fall back to all modules (never worse than today).
- Not started here; noted so the D1/D-router choices are understood as
  forward-compatible.

### The validation framework (this effort, after the router)
- Extends `score_parser_prompts.py` with Stage 2 (intent → tool-selection).
- Generic across modules; no execution.
- Serves as the standing way to localize any new prompt's failure to a boundary.

---

## 5. Build order

The router is built **before** the framework, because the router *is* the
prompt→intent machinery — the framework validates prompt→intent→tool-selection,
and there is no scoped prompt→intent to validate until the router produces it.

1. **This design document.**
2. **The router (increment 1):** classifier-context generator + committed file →
   lift `assemble_subset` to production → the classifier → `route_and_parse` →
   fidelity test → commit.
3. **The validation framework:** add the intent→tool-selection stage to the
   harness, generic, no execution → prove it localizes failures → commit.

---

## 6. What this reuses (already built, Phase 1)

- `parse(system_prompt=…)` — the seam the router feeds the scoped context through.
- `assemble_subset(modules, menu)` — proven in the scorer harness; lifted to a
  production location so router and harness share one copy (no drift).
- `order.manifest` + the 48 `.sysprompt` blocks — the scoped content on disk.
- `kg_entity.module` — the entity→module mapping the classifier generator reads.

---

## 7. Costs and honest caveats

- **Two LLM calls per query** (classify + parse) instead of one. The classify
  call is small and the parse call is now smaller, so total tokens usually drop,
  but it is two round-trips — slightly more latency. This is inherent to the
  two-request design.
- **Increment 1 is single-module only.** A genuinely cross-module prompt
  ("compare invoices to POs") will classify to one module and may parse
  incompletely until increment 2. Fidelity tests should use cleanly
  single-module prompts; cross-module underperformance is expected, not a
  regression.
- **The framework stops at tool-selection.** It confirms the *right tool would
  be called*, not that calling it returns correct data. Execution correctness
  remains with the existing end-to-end scripts, by design.
- **A misroute poisons the parse.** If the classifier picks the wrong module,
  the scoped context lacks what the prompt needs and the parse suffers. This is
  why the classifier is grounded richly (D2/D3) and why increment 2 adds an
  all-modules fallback for the unsure case.
