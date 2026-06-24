# Spire — Context Handoff (Session ending 2026-06-01, evening)

**For:** Bhagavan, picking up Spire in a new chat session.
**By:** Claude (this session).
**Replaces:** the earlier 2026-06-01 handoff for forward work. Read alongside
`docs/feature_roadmap.md`, `docs/designs/feature_1_nl_parser_design.md`, and
`docs/prompt_coverage.md`.

---

## 1. What changed this session

**Feature 1 (natural-language parser) is DONE — designed, implemented, and
verified against live Gemini + the live KG.** This was a design discussion
first (five questions settled), then a checkpointed build.

### The design (full detail in `docs/designs/feature_1_nl_parser_design.md`)
- **Q1 — where it lives:** new module `src/spire/nl_parser/`, beside the
  planner, modeled on the synthesizer. NOT folded into the agent or planner.
- **Q2 — KG-bounded:** synchronous, two-way. Menu read from the KG before the
  LLM call; draft Intent validated back against the KG after. Uses the
  planner's sync KG path, not the agent's async loader.
- **Q3 — out of scope:** structured "can't answer" result naming the flavor;
  capability-framed wording deferred to feature 8.
- **Q4 — testing:** mock unit tests (exact match, our-code bugs) + live tests
  (properties, run regularly, catch model regressions), kept split.
- **Q5 — vs synthesizer:** parser is the user-facing gatekeeper via a checked
  refusal result (the pipeline stops before planning); the synthesizer's
  `UnsupportedEntityError` stays as a loud developer-facing backstop.

### What was built
- `src/spire/nl_parser/`: `result.py`, `vocabulary.py`, `draft.py`,
  `validation.py`, `parser.py`.
- `run_plan.py` gained `--prompt "<nl>"`. Refusal -> message + exit 4; valid
  Intent -> existing planner/executor/synthesizer unchanged. `--intent`
  hand-built path untouched.
- Tests: `tests/test_nl_parser.py` (14 mock), `tests/test_nl_parser_integration.py`
  (8 live, `@pytest.mark.integration`).

### Two bugs the live model surfaced (both fixed)
1. **Silent rewrite:** model rewrote out-of-scope "contract renewals" as a bare
   Supplier query instead of refusing. Fixed by (a) prompt forbidding salvage,
   (b) an explicit `unanswerable` slot on `DraftIntent` so the model can choose
   to refuse.
2. **Fragile value encoding:** model emitted bare `GB` not `"GB"`; `to_intent()`
   now decodes leniently (non-JSON value -> plain string).

---

## 2. Current state

- Full suite: **277 passed, 13 deselected** (was 263 + 5; +22 parser tests).
- Live parser suite: **8/8 green across repeated runs.**
- Verified live end-to-end:
  - `run_plan.py --prompt "List all US suppliers with open POs, include the buyer"`
    -> correct Intent, full pipeline, correct answer.
  - `run_plan.py --prompt "Show me contract renewals due next quarter"`
    -> refuses, exit 4, no silent supplier dump.
- `run_plan.py --intent original` (hand-built path) still works unchanged.

**Architecture unchanged:** Design 3 — deterministic planner + executor, LLM
bounded to the interpreter (new, feature 1) and the synthesizer.

---

## 3. NEXT: Feature 8 — graceful refusal

The roadmap pairs 1 -> 8. Feature 1 already produces structured refusals; what
remains is the *wording*.

- **What's done:** the parser detects out-of-scope prompts and returns a
  `Refusal` with a flavor tag + raw facts. `run_plan.py` prints it and exits 4.
- **What feature 8 adds:** turn that structured refusal into a polished,
  capability-framed user message generated from the KG ("Spire can look up
  suppliers, invoices, and POs, filter by country/status/date, and find the
  buyer on a PO — it can't do contracts or spend aggregation yet").
- **Specific fix to fold in:** the model's self-declared refusal currently maps
  to flavor `UNPARSEABLE` even when it's really `UNKNOWN_ENTITY` (contracts) or
  `UNSUPPORTED_OPERATION` (aggregation). Feature 8 should derive the right
  flavor and message from the KG.

The `RefusalFlavor` enum, `Refusal.detail`, `offending_entity`, and
`offending_filters` already carry the facts feature 8 needs.

---

## 4. Loose ends (none block feature 8)

1. **Agent lifecycle:** keep the Track A agent (`ask.py`/`runner.py`) as the
   evaluation baseline until the parser-driven Design 3 has been compared
   against it and the result recorded. Then delete. Do NOT delete yet — that
   comparison hasn't been run. (Now a section in `feature_roadmap.md`.)
2. **Run the baseline comparison:** the actual parser-vs-agent before/after
   that justifies feature 1 and gates the agent's deletion.
3. **Parser imports planner privates** (`_ENTITY_LEVEL_FILTER_TYPES`,
   `_EDGE_TRAVERSAL_FILTERS`) so its menu matches `_validate_intent_filters`.
   When filters move into the KG (planner v1.2), read them from the KG.
4. **Carried from before:** rotate the exposed Fusion password; confirm the
   Supplier `Status` vocabulary; fix `prompt_coverage.md` path references;
   merged-branch cleanup. `inspect_trace.py` doesn't parse run_plan traces
   (it's agent-shaped) — minor.

---

## 5. How to verify in a new session

```bash
# Full suite — expect 277 passed, 13 deselected
pytest tests/

# Parser mock tests only (fast, offline)
pytest tests/test_nl_parser.py -v

# Parser live tests (needs GEMINI_API_KEY + KG reachable)
pytest -m integration tests/test_nl_parser_integration.py -v

# End-to-end NL path (MCP server in another terminal + Gemini key)
python -m spire.mcp_server.server                                  # terminal 1
python scripts/run_plan.py --prompt "List all US suppliers with open POs, include the buyer"   # terminal 2
python scripts/run_plan.py --prompt "Show me contract renewals due next quarter"   # should refuse, exit 4
```

---

*End of handoff doc.*
