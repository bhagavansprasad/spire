# Spire Pipeline Playbook

How a prompt becomes an answer, and how to add support for a new one.
Companion to the four canonical docs: the expansion plan says *what/when*,
the architecture doc says *current state*, the design decisions say *why
frozen*, the endpoints reference says *pod truth* — this playbook says
*how to add a prompt*.

> First cut: titles and subtitles only. Each leaf will later expand into
> what / why / how.

---

## Part A — The runtime pipeline (prompt → answer)

### A1. Prompt intake
- A1.1 What a prompt is (NL question in scope)
- A1.2 Scope boundaries — what Spire will and won't answer
- A1.3 Prompt sets and where they live

### A2. Parse — NL prompt → Intent
- A2.1 The parser's job (NL → structured Intent)
- A2.2 Vocabulary resolution (synonyms, statuses, countries → canonical)
- A2.3 Capability check — is this prompt answerable?
- A2.4 `validate_intent` — when it runs, when it's exempt
- A2.5 The Intent object — shape and fields

### A3. Plan — route the Intent
- A3.1 The three routing kinds (the central decision)
- A3.2 Entity/filter route → KG tables
- A3.3 Aggregation route → op-registry
- A3.4 Comparison route → comparison op-registry
- A3.5 Tool selection as lookup, not LLM judgment
- A3.6 Plan output — the executable step(s)

### A4. Execute — run the tools
- A4.1 The executor's job (plan → tool calls → raw data)
- A4.2 Entity fetchers (list, detail-by-id)
- A4.3 Edge traversals (parent → child, multi-id iteration)
- A4.4 Cross-pillar reads (FSCM ↔ HCM; e.g. buyer/worker lookups)
- A4.5 Bounded windows — paging, `MAX_PAGES`, `truncated` flag
- A4.6 Pod-quirk handling at call time (single-clause q=, compression, etc.)

### A5. Synthesize — data → answer
- A5.1 The synthesizer's job (structured data → NL response)
- A5.2 Entity/child narration (LLM-templated)
- A5.3 Aggregation & comparison shapes (deterministic, no LLM)
- A5.4 The no-arithmetic rule (tools compute, synthesizer templates)
- A5.5 Hallucination guard (every id cross-referenced to executor output)

### A6. Output
- A6.1 Response shape delivered to the caller
- A6.2 Truncation / lower-bound disclosure
- A6.3 Tracing — what's captured for inspection

---

## Part B — The build sequence (adding a new prompt)

### B0. Frame the prompt
- B0.1 Which prompt(s) am I adding
- B0.2 Dedupe — does existing coverage already serve it
- B0.3 Decide the routing kind up front (drives everything below)
- B0.4 Author / update the prompt in the prompt set (→ Part E)

### B1. Curl discovery
- B1.1 Why discovery precedes code (pod truth over assumption)
- B1.2 Endpoint + column capture (`limit=1`, `totalResults=true`)
- B1.3 Filter discovery — which fields are queryable via `q=`
- B1.4 Child / traversal path confirmation
- B1.5 Record findings in the endpoints reference (§ per module)

### B2. Standalone tool
- B2.1 Curl-backed Python fetcher, tested in isolation
- B2.2 Input args and output shape
- B2.3 Pod-quirk guards baked into the tool
- B2.4 Prove it against the live pod before wiring

### B3. Register the capability (route-dependent)
- B3.1 Entity/filter → KG rows (`kg_entity`, `kg_entity_field`,
  `kg_entity_filter`, `kg_edge`, …)
- B3.2 Aggregation → op-registry pair (`_AGGREGATION_TOOLS` /
  `_AGGREGATION_PARAMS`)
- B3.3 Comparison → comparison op-registry pair (`_COMPARISON_TOOLS` /
  `_COMPARISON_PARAMS`)
- B3.4 Rebuild the KG from scratch (`rebuild_kg.py`)

### B4. Planner wiring
- B4.1 Make the planner emit the new step
- B4.2 Filter / mechanism binding
- B4.3 Planner-level test

### B5. Parser wiring
- B5.1 Teach the parser to produce the Intent
- B5.2 Vocabulary additions (terms → canonical values)
- B5.3 "Do NOT refuse" instruction blocks (aggregation / comparison)
- B5.4 Parser-level test

### B6. Server wrapper
- B6.1 Expose the tool via the MCP server
- B6.2 Tool signature and registration

### B7. Synthesizer shape
- B7.1 Add / extend the narration or deterministic shape for this output
- B7.2 Wire the hallucination guard for any new ids

### B8. Tripwires
- B8.1 Bump row-count expectations (`print_kg.py`)
- B8.2 Bump KG metadata test (`tests/test_kg_metadata.py`)
- B8.3 When tripwires change vs. when they don't (KG rows vs. op-registry)

### B9. Tests
- B9.1 Tool test
- B9.2 Pipeline / integration test
- B9.3 Parser + planner coverage
- B9.4 Run the prompt-set harness (→ Part E)

### B10. Verify
- B10.1 End-to-end run against the live pod
- B10.2 Promote the prompt (failed → parser-pass → e2e-pass) (→ Part E)
- B10.3 SME validation checklist
- B10.4 Trace inspection

### B11. Ship
- B11.1 One branch per change (`<module>-phase-N-description>`)
- B11.2 Named files in `git add`, heredoc commit message
- B11.3 PR → merge; docs-only edits straight to master

---

## Part C — Worked example (end to end)
- C1. The chosen prompt
- C2. Its runtime path (Part A applied)
- C3. Its build path (Part B applied)

---

## Part D — Routing decision guide
- D1. "Which of the three kinds is my prompt?" — the decision
- D2. Signals for entity/filter
- D3. Signals for aggregation
- D4. Signals for comparison
- D5. Consequences of each (what you wire, what you rebuild)

---

## Part E — Prompt sets: artifact + harness

Prompt sets bookend the build: you **author** them upstream (before
discovery) and **run** them downstream (test + verify). This section is the
single home both ends point to.

> The file taxonomy below is read off the repo tree — confirm against the
> actual `scripts/` convention and correct if the split differs.

### F1. Prompt sets as artifact (authoring)
- F1.1 Where they live (`scripts/prompt_set_<module>.txt`, per module)
- F1.2 Writing a new prompt — phrasing and the NL variations to cover
- F1.3 The prompt catalog table (# → type → tool → columns returned)
- F1.4 Adding vs. updating — a new prompt vs. a changed one
- F1.5 Keeping the catalog in sync with what's actually built

### F2. Prompt sets as harness (running)
- F2.1 `01_test_prompts_parser.txt` — parser-only (Intent correctness)
- F2.2 `02_test_prompts_e2e.txt` — full pipeline (prompt → answer)
- F2.3 `03_test_prompts_failed.txt` — known failures / regression watch
- F2.4 `prompt_set_<module>.txt` — the per-module working set
- F2.5 Runners — `run_prompt_set.py`, `score_parser_prompts.py`,
  `run_prompt.py`

### F3. The promotion path
- F3.1 A prompt's lifecycle: failed → parser-passing → e2e-passing
- F3.2 When a prompt moves between sets
- F3.3 Regression discipline — nothing silently drops back to failing

### F4. Prompt sets vs. unit tests
- F4.1 What the prompt-set harness covers that `tests/*.py` doesn't
- F4.2 What `tests/test_prompts.py` bridges between the two

---

## Part F — Conventions quick reference
- E1. Output to `t.txt` (overwrite `>` / append `>>`)
- E2. KG always rebuilds from scratch
- E3. Branch / PR / commit discipline
- E4. One command at a time, verify each step
- E5. Pod-quirk catalog pointer (→ endpoints reference)
