# Spire — Context Handoff (Session ending 2026-06-02)

**For:** Bhagavan, picking up Spire in a new chat session.
**By:** Claude (this session).
**Replaces:** the 2026-06-01 evening handoff for forward work. Read alongside
`docs/feature_roadmap.md` and `docs/designs/feature_1_nl_parser_design.md`.

---

## 1. What changed this session

**Feature 8 (graceful refusal) is DONE — implemented and verified, full suite
green.** It builds on the structured refusal feature 1 already produced.

### What was built
- New module `src/spire/nl_parser/capability.py` with two functions:
  - `derive_flavor(reason, target_entity, menu)` — re-derives the refusal
    flavor for a SELF-DECLARED `unanswerable` draft, which feature 1 had
    hardcoded to UNPARSEABLE. Order: explicit unknown target_entity ->
    UNKNOWN_ENTITY; aggregation/ranking wording -> UNSUPPORTED_OPERATION;
    unknown entity named in the reason -> UNKNOWN_ENTITY; else UNPARSEABLE.
    Aggregation is checked BEFORE the loose entity-name scan so "total open PO
    value by buyer" reads as aggregation, not unknown-entity "PO".
  - `capability_message(refusal, menu)` — user-facing wording: one sentence on
    what Spire CAN do (built from the KG menu, so it never goes stale) plus one
    on why this prompt is outside it.
- `src/spire/nl_parser/parser.py` — the `unanswerable` branch now calls
  `derive_flavor` and populates `offending_entity`.
- `scripts/run_plan.py` — refusal printer uses `capability_message`; the KG
  menu is loaded once and shared with both the parser and the printer.
- `tests/test_nl_parser_capability.py` — 10 new unit tests (flavor derivation +
  message). All pass.
- `tests/test_nl_parser.py` — one existing test updated:
  `test_explicit_unanswerable_refused` now asserts UNKNOWN_ENTITY (was
  UNPARSEABLE — that mislabel is exactly what feature 8 fixed).

### Verified
- `tests/test_nl_parser.py`: 14 passed.
- `tests/test_nl_parser_capability.py`: 10 passed.
- Full suite: 286 passed + 10 new = 296 passing, 13 deselected.
- Live end-to-end: `run_plan.py --prompt "Show me contract renewals due next
  quarter"` now refuses with UNKNOWN_ENTITY and a capability-framed message,
  exit 4.

### Known cosmetic follow-up (not a blocker)
The contract refusal message reads "...about that kind of record..." instead of
"...about Contract...". Cause: the model self-declared `unanswerable` with an
empty `target_entity` and put "Contract" only in the reason text, so
`offending_entity` was never populated and `capability_message` fell back to
the generic phrase. Fix (a few lines): when the flavor is derived from an
entity NAMED IN THE REASON, capture that name into `offending_entity` too.
Deferred — the flavor and exit code are correct; only the noun is generic.

---

## 2. Roadmap decisions this session

Two decisions, now reflected in `docs/feature_roadmap.md`:

1. **Way 2 (Design 3) is the committed architecture.** No comparison against
   the Track A agent will be run — the comparison's only job was to justify the
   choice, and the choice is made.

2. **Track A agent is cleared for removal.** It no longer gates on the
   (now-cancelled) baseline comparison. Files to remove when cleanup happens:
   `scripts/ask.py`, `src/spire/agent/` (runner, prompts, lg_utility, tracing),
   `tests/test_agent_runner.py`, `tests/test_prompts.py`, and the agent-shaped
   `inspect_trace.py`.

   **IMPORTANT before deleting:** `scripts/run_plan.py` imports
   `make_trace_logger` from `spire.agent.tracing`. So `tracing.py` CANNOT be
   deleted with the rest of the agent — relocate that helper (e.g. into a
   neutral `src/spire/tracing.py` or into the executor package) first, then
   repoint `run_plan.py`'s import. The other agent files can go directly.

3. The roadmap also now records that **Design 3 is deliberately NOT an agent**:
   the LLM is bounded to two single-shot roles (interpreter + synthesizer) with
   a deterministic planner/executor between — no tool-calling loop. Future
   features add bounded tools, not agent-style orchestration.

---

## 3. NEXT: Features 6 and 7 (phase three)

Both are open, demand-driven, and their DESIGNS ARE PENDING A BRAINSTORMING
SESSION (Bhagavan has thoughts to work through first — do not start building
either without that discussion).

- **Feature 6 — Contracts.** Add a Contract entity to the KG (entity, fields,
  edges, vocabulary) and a `search_contracts` tool. Turns the current
  "contract renewals" refusal into a real answer.
- **Feature 7 — Aggregation.** Server-side aggregation tools returning small
  structured results (e.g. `aggregate_invoices_by_supplier` with date range +
  top_n). The LLM never does the math; a Python tool aggregates. Keep shapes
  bounded — specific tools per shape, not a generic engine.

---

## 4. Loose ends carried forward

1. **Agent removal** — cleared but not yet done (see section 2; mind the
   `tracing.py` import).
2. **Cosmetic refusal noun** — "that kind of record" -> "Contract" (section 1).
3. **Parser imports planner privates** (`_ENTITY_LEVEL_FILTER_TYPES`,
   `_EDGE_TRAVERSAL_FILTERS`) so its menu matches `_validate_intent_filters`.
   When filters move into the KG (planner v1.2), read them from the KG instead.
4. **Carried from before:** rotate the exposed Fusion password; confirm the
   Supplier `Status` vocabulary; fix `prompt_coverage.md` path references;
   merged-branch cleanup.

---

## 5. How to verify in a new session

```bash
# Parser unit tests (fast, offline)
pytest tests/test_nl_parser.py -v             # expect 14 passed
pytest tests/test_nl_parser_capability.py -v  # expect 10 passed

# Full suite
pytest tests/                                 # expect 296 passed, 13 deselected

# Live end-to-end refusal (needs GEMINI_API_KEY + KG reachable)
python scripts/run_plan.py --prompt "Show me contract renewals due next quarter"
# expect: capability-framed message, UNKNOWN_ENTITY, exit 4
```

---

*End of handoff doc.*
