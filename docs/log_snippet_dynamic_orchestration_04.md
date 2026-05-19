## Dynamic Orchestration 04 — KG Query Tools (B-lite)  ✅ DONE

**Verified:** 2026-05-19
**Branch:** `dynamic-orchestration/04-kg-query-tools`
**Decision:** Option B-lite (static KG bundle in system prompt). See `docs/designs/agent_kg_integration.md` for the full design.

### What "phase 04" turned out to mean

The master plan named this phase "Build the Graph Query Tools." Under B-lite, there are no graph query tools — the KG is loaded once and embedded in the system prompt as markdown. So the phase reshaped: instead of designing an MCP tool surface for the agent to query the KG, the phase built a loader, a prompt-composition helper, an ablation switch, and the smoke tests to confirm the wiring works end-to-end.

The name "KG Query Tools" no longer fits what's in this phase. We're keeping the branch name and the master-plan number (04) for traceability, but everything described below is B-lite scaffolding, not query tools.

### What was decided before code

The phase opened with a design conversation about how the agent should consult the KG. Four options were considered:

- **A** — KG as MCP tools the LLM can call
- **B (full)** — pre-LLM planner builds a per-request KG context bundle
- **B-lite** — static KG bundle loaded once, embedded in the system prompt
- **C** — hybrid of A and B-lite

Initial lean was A (cleanest ablation). Revised to B-lite after weighing Track A's failure evidence: Track A's 1/7 baseline failed because the LLM didn't recognize when it needed more information. Option A relies on exactly that recognition skill. B-lite bypasses the recognition problem by putting the KG content in front of the LLM whether it asks or not.

The four options and the revision are captured in `docs/designs/agent_kg_integration.md`, committed as the first commit on this branch (alongside four PlantUML diagrams, one per option).

### What was built

**New code:**

| File | Purpose |
|---|---|
| `src/spire/kg/__init__.py` | New `kg/` package, parallels `fusion/` and `oracle/` |
| `src/spire/kg/loader.py` | `load_kg_context(persona)` — queries all 5 KG tables and formats them as a markdown bundle (~12.5K chars for v1) |
| `src/spire/agent/prompts.py` | `SYSTEM_PROMPT_BASE` constant + `build_system_prompt(kg_context)` composer; extracted from `runner.py` for readability |

**Modified:**

| File | Change |
|---|---|
| `src/spire/agent/runner.py` | Imports prompt logic; adds `kg_enabled` parameter (default `True`); calls `load_kg_context` when enabled; logs `kg_context_loaded` or `kg_context_skipped` and `system_prompt_built` events |
| `scripts/ask.py` | Adds `--no-kg` flag mapped to `kg_enabled=False` |

**Tests:**

| File | Tests | Type |
|---|---|---|
| `tests/test_prompts.py` | 6 | Pure unit (no DB, no MCP) |
| `tests/test_kg_loader.py` | 8 | Integration (real Oracle, no MCP) |

Total: 49 passed, 1 deselected (was 35 / 1; +14 new tests). All Track A's Fusion integration tests still green against the live pod.

### Implementation decisions worth recording

| Decision | Choice | Why |
|---|---|---|
| Bundle format | Markdown | Human-readable, LLMs work well with it from training, easy to debug visually |
| Bundle location | System prompt | The system prompt is where instructions live; KG knowledge is reference instructions for how to think about Fusion |
| Code location | `src/spire/kg/` | Parallels `fusion/` and `oracle/`; KG is its own conceptual layer |
| Ablation switch | `run_agent(prompt, kg_enabled=True)` parameter | Most explicit; visible at call site; trivial to test both modes |
| Load frequency | Per `run_agent()` call | Spire runs one call per CLI invocation; no module-level state, easier to test; ~50ms per load is fine |
| Long prompts | Extracted to `prompts.py` | Bhagavan's call — easier to read code when prompt strings aren't inline |
| `SYSTEM_PROMPT_BASE` | Lightly revised to mention the KG | Pointer sentence in the base; used for both KG-on and KG-off so ablation isolates only the KG content |

### Bundle composition

The `load_kg_context` function produces a markdown document with four top-level sections:

1. **Entities** — markdown table (5 rows), followed by per-entity sub-sections with field projection details
2. **Edges (Relationships)** — markdown table (4 rows), followed by per-edge details including traversal hints and notes
3. **Query Patterns** — prose blocks for each of the 4 patterns; includes shape, parameters (as JSON code block), mechanics (as numbered steps), and worked example
4. **Vocabulary** — grouped by `vocab_kind`; markdown table per kind

The notes columns from `kg_edge` are included prominently — this is where the SupplierNumber-vs-SupplierId asymmetry and the cross-pillar caveat for `ASSIGNED_TO` live.

For v1 the bundle is ~12,480 chars (~3,000 Gemini tokens). Well within context limits.

### Smoke test — end-to-end works in both modes

Ran the simple prompt "Find suppliers with 'Lee' in the name" both with and without KG:

- **KG-enabled** (`python scripts/ask.py "..."`): system prompt 13,140 chars (base + KG bundle); answer correct ("Lee Supplies and Lee Testing for UK BU")
- **KG-disabled** (`python scripts/ask.py --no-kg "..."`): system prompt 653 chars (base only); answer correct (same)

Trace files confirm `kg_enabled` flows through to the logger and the loader runs (or doesn't) based on the flag.

Honest observation: for a single-step prompt, both modes produce the same answer. That's expected — the KG isn't supposed to help when there's nothing structural to figure out. The real test is the multi-step reference prompt, which happens in phase 08.

### Implications for subsequent phases

| Phase | Impact |
|---|---|
| 05 — Agent Integration | Substantially absorbed by this phase. Under B-lite, integration *is* the system prompt change. Phase 05 may shrink to a verification step ("run the agent against a multi-step variant of the reference prompt and inspect the trace") or fold into phase 07. |
| 06 — Embeddings | Open. B-lite doesn't need embeddings for v1 (the full bundle fits in context). If Tier 1 evaluation surfaces "LLM glaze" on the dense system prompt, phase 06 might introduce embedding-based selection of which KG content to include. Defer decision until Tier 1 results. |
| 07 — Integration Polish & Trace Visibility | Existing trace events from this phase (`kg_enabled`, `kg_context_loaded`, `system_prompt_built`) give phase 07 something to build on. Worth adding: a trace-inspection helper that surfaces "did the agent see the KG?" cleanly. |
| 08 — End-to-end Test | Tier 1 measurement of the evaluation framework. 5 runs of the reference prompt with `kg_enabled=True`. Same rubric, same protocol as A.5. |
| 09 — Comparative Results | Tier 2 ablation. 5 more runs of the reference prompt with `kg_enabled=False`. Delta between phase 08 and the ablation = the KG's contribution. |

### Known gaps and deferred work

- **The "Key 'additionalProperties' is not supported in schema, ignoring" warnings** still appear (cosmetic, from langchain-google-genai parsing MCP tool schemas). Same noise as Track A; not fixed.
- **No trace-inspection tooling yet.** The traces are JSONL files; reading them requires `jq` or `cat | python -m json.tool`. Phase 07's job.
- **`cross_pillar_lookup` pattern still in v1.** Phase 03 flagged this as the pattern least confident about. Phase 04 didn't have a reason to drop it; we'll see in phase 08 whether the agent uses it or whether the `ASSIGNED_TO` edge content alone is sufficient.
- **The bundle is always the full v1 KG.** No per-prompt filtering. If we discover the LLM glazes over the 13K-char prompt, phase 06 (embeddings) or a smaller hand-crafted bundle becomes the fix.

### Honest framing

Phase 04 was much smaller than the master plan anticipated. The "query tools" name implied a substantial tool layer; under B-lite there are no new tools. The phase built scaffolding (loader, prompt composition, ablation switch) and tests, and that's it. ~536 lines of code across the new files.

This is consistent with the architectural decision. B-lite was chosen because the smallest engineering surface was the right answer, not because it would make phase 04 cheap. The phase being cheap is a consequence of the decision being right, not a problem.

The real measurement of whether the B-lite choice was right happens in phase 08 and the Tier 2 ablation. That's the test the framework is set up for.

---
