# SPIRE — Correctness, Consistency, and Growth

**Making the NL-to-Data Pipeline Trustworthy, Then Extensible**

**Document version:** 3.0
**Created:** 2026-09-13
**Author:** Bhagavan (with architectural analysis by DeepSeek)
**Status:** Living document. The design is frozen at v3.0. Status sections are appended per completed phase. **Never edit a Design section — record deviations in that phase's Status section.**

---

## How to read this document

**Part I (§1–§4) explains why we are doing this work.** It is the origin story: where SPIRE came from, what it is, where it falls short, and what the plan achieves. Read this first.

**Part II (§5–§12) is the seven-phase plan.** Each phase has a Design section (frozen at v3.0) and a Status section (updated as work proceeds).

**Part III (§13–§14) is the tracking machinery.** The Phase Index and the Session Log are the two places that change every session.

**Rules for cross-session continuity:**

1. **Never edit a Design section.** If the design turns out to be wrong, record the deviation in that phase's Status section.
2. **Update the Phase Index (§5) at the end of every session.**
3. **Add a Session Log entry (§14) at the end of every session.** Newest at the top.
4. **When resuming in a new DeepSeek window, paste this document and say:** *"Resume SPIRE work. Read §5 Phase Index and §14 Session Log. Current phase is [X]. Here is the repo state: [paste `git status`, `git branch`, `pytest -q`]."*

---

## Table of Contents

**Part I — Why we are doing this**
1. [The origin: a graph database, a natural-language question, and SQL](#1-the-origin-a-graph-database-a-natural-language-question-and-sql)
2. [What SPIRE is today](#2-what-spire-is-today)
3. [Where SPIRE falls short](#3-where-spire-falls-short)
4. [What this plan achieves](#4-what-this-plan-achieves)

**Part II — The seven phases**
5. [Phase Index](#5-phase-index)
6. [Phase 1 — Audit & Baseline](#6-phase-1--audit--baseline)
7. [Phase 2 — Correctness](#7-phase-2--correctness)
8. [Phase 3 — Consistency](#8-phase-3--consistency)
9. [Phase 4 — Structure](#9-phase-4--structure)
10. [Phase 5 — Observability](#10-phase-5--observability)
11. [Phase 6 — Performance](#11-phase-6--performance)
12. [Phase 7 — Extensibility](#12-phase-7--extensibility)

**Part III — Tracking**
13. [Phase completion checklist](#13-phase-completion-checklist)
14. [Session Log](#14-session-log)

**Appendices**
- [A — Baseline state (2026-09-13)](#appendix-a--baseline-state-2026-09-13)
- [B — Evidence capture templates](#appendix-b--evidence-capture-templates)
- [C — Decisions log](#appendix-c--decisions-log)
- [D — The dependency argument (why this order)](#appendix-d--the-dependency-argument-why-this-order)

---

# Part I — Why we are doing this

## 1. The origin: a graph database, a natural-language question, and SQL

**The founding idea.** Model a domain as a graph — entities, edges, vocabularies — and use that graph to translate a natural-language question into a SQL query. The graph is the knowledge; the translation is the pipeline; the SQL is the answer.

The insight behind the idea: an LLM alone cannot reliably produce correct SQL. It hallucinates join keys, invents column names, and chooses the wrong table. But an LLM *plus a graph that declares what's true* can. The graph holds the domain; the LLM reads from the graph; the pipeline executes against the data.

**What we learned.** The graph alone is not enough. To turn a question into an answer, you need a pipeline between them:

- **Parse** — the question becomes a structured Intent.
- **Plan** — the Intent becomes a sequence of operations, chosen deterministically from the graph.
- **Execute** — the operations run against the target data source.
- **Synthesize** — the results become a readable answer.

The graph is inert without the pipeline. The pipeline is the actual work. And the pipeline's correctness depends entirely on the graph being the single source of truth — if the graph says one thing and the code says another, the code wins, and the graph's guarantees evaporate.

**SPIRE is a working realization of this idea — one step removed from SQL.** It has:

- A **KG** stored in Oracle — structurally a graph database (entity, edge, vocabulary, pattern tables).
- A **pipeline** that reads the KG to plan.
- A **target** that is Oracle Fusion REST endpoints, not SQL tables.

SPIRE is graph-to-REST. The SQL target was the original vision; REST was the concrete platform available; SQL remains a future direction.

**This plan is about making SPIRE a foundation for that future.** Making it correct, consistent, and structured is what turns it from a working prototype into a system that can be trusted, extended, and — eventually — retargeted to SQL or any other backend.

---

## 2. What SPIRE is today

A seven-part pipeline. Two LLM calls. A knowledge graph. Thirty-four tools.

```
prompt
  │
  ▼
[Router]        classify to a Fusion module      (LLM or gazetteer)
  │
  ▼
[Parser]        prompt → structured Intent        (LLM)
  │
  ▼
[Planner]       Intent → plan of tool steps       (deterministic, reads KG)
  │
  ▼
[Executor]      run the plan against MCP tools    (deterministic)
  │
  ▼
[Synthesizer]   results → structured answer       (local 90%, LLM 10%)
  │
  ▼
[Renderer]      answer → screen                   (deterministic)
```

**What's already good:**

- **The KG-driven planner is the right architecture.** Tool selection is a deterministic lookup, not an LLM judgement. This is the founding idea working.
- **The synthesizer is 90% local.** Most shapes build their records and summaries from code. The remaining 10% is documented and shrinking.
- **Refusals are first-class.** Out-of-scope prompts get a Reason/Solution/Example message, not a stack trace.
- **Truncation is disclosed.** When a result is a sample, the answer says so.
- **The test suite is broad** — 996 tests, most fast, most passing.

**What's working well enough to build on:**

- The three-language interface (KG in Oracle, pipeline in Python, tools in MCP) is coherent.
- The design decisions in `docs/spire_plan.md` are sound.
- The refusal and truncation work is ahead of most comparable systems.

---

## 3. Where SPIRE falls short

SPIRE has accreted. As it grew from five endpoints to twenty-two entities, from three tools to thirty-four, from one prompt file to fifty-one, parallel registries emerged that must stay in sync by hand. That accretion is the source of the problems this plan addresses.

**Problem 1 — Parallel registries drift.**

The KG declares entities, filters, edges, vocabularies. But the parser prompt hand-writes the same information. The tool files hand-code the same endpoints. The tripwire tests hand-count the same rows. When any one of these is updated without the others, drift appears — and the drift is silent. The codebase itself documents this as a recurring defect class, calling out "the four places that must move together, not two as earlier notes implied."

**Problem 2 — Bugs hide in the drift.**

When the KG says "the supplier filter routes to `supplier_number`" and the tool hardcodes `supplier_name`, the bug is invisible until a prompt hits it. When the parser prompt teaches one shape and the planner expects another, the failure surfaces three phases downstream.

**Problem 3 — Extensibility is expensive.**

Adding one new endpoint touches sixteen files. Adding a filter touches five. Adding a module touches dozens. Every one of these is a place to forget a step. The work compounds: each addition makes the next addition more expensive because more parallel registries exist.

**Problem 4 — The code is structured for the past, not the present.**

The `src/spire/` layout reflects an earlier version of the system. Some modules bundle multiple concerns. Some concerns are scattered across modules. Tests are flat. Entry points are in scripts, not in the package. None of this is fatal, but it makes the true architecture invisible.

**Problem 5 — There is no clear seam for the future.**

The founding vision was graph-to-SQL. SPIRE is graph-to-REST. To retarget to SQL — or to any other backend — you need a clean interface between "the pipeline that understands questions" and "the layer that talks to the data source." Today that interface is implicit, embedded in thirty-four tool files and a hand-written dispatch.

**The common thread:** SPIRE's *capability* grows linearly with developer effort, but its *trustworthiness* and *velocity* decrease. That is the wrong shape for a system that is supposed to keep growing — and eventually to serve as the foundation for the SQL vision.

---

## 4. What this plan achieves

**The plan makes SPIRE correct, consistent, and structured — in that order — so it becomes a foundation that can be trusted, extended, and eventually retargeted.**

Concretely, by the end of all seven phases:

**Correctness.**

- Every known bug is fixed with a regression test that proves it stays fixed.
- The audit's findings are turned into a bug list, and the bug list is turned into zero.

**Consistency.**

- The KG is the single source of truth. The parser prompt is generated from it. The tool dispatch is generated from it. The tripwire counts are generated from it. Drift becomes structurally impossible.
- Adding a filter is one KG row. Adding a field is one KG row. No code change.

**Structure.**

- The tree reflects the architecture. Modules have clear boundaries. Tests are organized by concern. Entry points are installable console scripts.
- A new contributor can find what they need without reading the whole codebase.

**Observability.**

- Every pipeline stage emits a span. Latency, tokens, and errors are visible per stage.
- A failing request can be diagnosed from a single trace.

**Performance.**

- Repeated questions reuse cached results. Independent steps run in parallel.
- Latency per request drops. Growing the system stays neutral-or-better on wall-clock.

**Extensibility.**

- Adding a new endpoint is one YAML file and one command.
- Adding a filter or field is one line in that file.
- Adding a new Fusion module is a data operation, not a code migration.

**And the ultimate purpose.** With all of the above in place, the interface between SPIRE's pipeline and its data source becomes explicit — one clean seam where "REST endpoints" could become "SQL tables" or any other backend. SPIRE is not the destination; it is the platform on which the original graph-to-SQL vision can eventually be realized.

**Extensibility is a consequence, not a goal.** A correct, consistent, structured system is extensible by construction. A system that is extensible but inconsistent simply has more places to be wrong. That is why extensibility is Phase 7, not Phase 1.

---

# Part II — The seven phases

## 5. Phase Index

**This table is the single source of truth for progress.** Update it at the end of every session.

| Phase | Name | Status | Branch | Started | Completed | PR |
|---|---|---|---|---|---|---|
| 1 | Audit & Baseline | ⬜ Not started | — | — | — | — |
| 2 | Correctness | ⬜ Not started | — | — | — | — |
| 3a | Consistency — Prompt coverage validation | ⬜ Not started | — | — | — | — |
| 3b | Consistency — Prompt generation from KG | ⬜ Not started | — | — | — | — |
| 3c | Consistency — Generic executor (prototype) | ⬜ Not started | — | — | — | — |
| 3d | Consistency — Generic executor (full) | ⬜ Not started | — | — | — | — |
| 3e | Consistency — Delete legacy tools | ⬜ Not started | — | — | — | — |
| 4a | Structure — Source-tree reorg | ⬜ Not started | — | — | — | — |
| 4b | Structure — Test suite split | ⬜ Not started | — | — | — | — |
| 4c | Structure — Module boundaries | ⬜ Not started | — | — | — | — |
| 5 | Observability | ⬜ Not started | — | — | — | — |
| 6a | Performance — Tool-result cache | ⬜ Not started | — | — | — | — |
| 6b | Performance — Parallel execution | ⬜ Not started | — | — | — | — |
| 6c | Performance — Intent cache | ⬜ Not started | — | — | — | — |
| 7a | Extensibility — Endpoint spec format | ⬜ Not started | — | — | — | — |
| 7b | Extensibility — `add-endpoint` generator | ⬜ Not started | — | — | — | — |
| 7c | Extensibility — `add-module` generator | ⬜ Not started | — | — | — | — |
| 7d | Extensibility — Documentation + walkthrough | ⬜ Not started | — | — | — | — |

**Legend:** ⬜ Not started · 🟡 In progress · 🟢 Complete · 🔴 Blocked · ⚪ Deferred

### 5.1 Why this order, in one paragraph

**Audit before correctness** — you can't fix what you haven't measured. **Correctness before consistency** — consolidating buggy code consolidates the bug. **Consistency before structure** — you can't decide where a module belongs until you know what the module *is*, and consistency work makes the code's true shape visible. **Structure before observability** — instrument stable code, not code that's about to move. **Observability before performance** — you can't prove a performance change helped without a baseline. **Performance before extensibility** — you want to generate new capabilities against a fast, well-understood system, not a slow, drifting one. **Extensibility last** — it is the *output* of everything above; a correct, consistent, structured, instrumented, fast system is extensible by construction. See Appendix D for the full dependency argument.

---

## 6. Phase 1 — Audit & Baseline

### 6.1 Objective

Measure everything. Find drift, bugs, dead code, and inconsistencies. Untrack `personas.yaml`. Perform small mechanical hygiene that unblocks later phases.

### 6.2 Why here

The audit is the *prerequisite* of every other phase. Correctness work needs a bug list. Consistency work needs a list of parallel registries. Structure work needs a map of what exists. Observability, performance, and extensibility all need the baseline metrics the audit produces.

An audit done at any other point would miss the state that earlier phases changed. It has to come first.

### 6.3 Design

**6.3.1 Security pre-work.**

`personas.yaml` is currently tracked in git. It contains live Fusion and Oracle credentials. This is the first commit on the branch.

```bash
git rm --cached personas.yaml
echo "personas.yaml" >> .gitignore
git add .gitignore
git commit -m "security: untrack personas.yaml; gitignore it"
```

After this commit, rotate the credentials. They are in git history.

**6.3.2 Mechanical hygiene.**

Small, safe moves that later phases assume.

- Move `scripts/display_formatters.py` → `src/spire/rendering/formatters.py`, with a re-export `__init__.py`. Update four imports.
- Move PDFs (`docs/*.pdf`, `tests/*.pdf`) → `docs/pdf/`.
- Move `docs/spire_tools_modules.xlsx` → `docs/data/`.
- Remove `source-tree.txt` and `isolation/` from the repo. Add them to `.gitignore`.

These are the only structural changes Phase 1 makes. The substantive restructuring happens in Phase 4, after consistency work has revealed the architecture.

**6.3.3 The audit.**

A systematic survey of the codebase. Deliverable is a document, `docs/audit/phase-1-audit.md`, with the following sections:

**A. Registry drift map.** For each piece of information that appears in more than one place, list every place it appears and whether they agree.

Example rows:

| Information | Where it lives | Agreement |
|---|---|---|
| Entity list | `kg_entity`, `_SYSTEM_PROMPT_PREAMBLE`, `classifier_menu.sysprompt`, `test_kg_metadata.py`, `print.py` | Check each |
| Filter → tool arg mapping | `kg_entity_filter.tool_arg_name`, `plan_builders._VALUE_SHAPE_ROUTED_ARGS`, `.sysprompt` blocks | Check each |
| Tool name → arg name | `kg_entity_tool.mcp_tool_name`, `_TOOL_PRIMARY_ARG`, tool function signature | Check each |
| Row counts | `kg_entity`, `test_kg_metadata.py`, `print.py`, `schema.sql` banners | Check each |
| Column lists | `kg_entity_field`, tool `_PROJECTED_FIELDS`, `.sysprompt` blocks | Check each |
| Aggregation ops | `_AGGREGATION_TOOLS`, `_AGGREGATION_PARAMS`, `DraftAggregate`, `.sysprompt` `m_aggregation` | Check each |

**B. Bug inventory.** Prompts that fail today. Run the full prompt suite, read every answer, and record what's wrong. Each entry: prompt, expected, actual, suspected root cause. Cross-reference the open items already documented in `docs/spire_overnight_findings.md` and `docs/spire_findings_11-Sep-2026.md`.

**C. Dead code inventory.** Modules, functions, or files not referenced by any test, tool, or prompt. `pytest --collect-only` plus `grep` for importers.

**D. Inconsistency inventory.** Style, naming, error handling, logging. Where the codebase says the same thing two ways. Where similar code has different shapes.

**E. Baseline metrics.** The numbers every later phase will compare against:

- Test count (`pytest -q --collect-only | tail -1`).
- Test wall-clock (`pytest -q`).
- Prompt suite pass count (`run_prompt_set.py` on all sets).
- Per-prompt latency (mean, median, p95).
- Per-prompt LLM calls (classify, parse, synth).
- Per-prompt tokens (in, out).
- KG row counts.
- MCP tool count.
- `.sysprompt` file count.

**F. Behavioural byte-diffs.** Three prompt outputs saved as golden files, to be used as the byte-equality oracle for every subsequent phase:

- `"Count of suppliers"` (count path)
- `"Show PO 2144 and its lines"` (child path)
- `"Which suppliers have open purchase orders?"` (join path)

Save the exact stdout to `docs/audit/golden/*.txt`.

**6.3.4 The audit is not a wishlist.**

The audit is a factual document. It says what *is*, not what *should be*. Fixes go in Phase 2 (correctness) or Phase 3 (consistency).

### 6.4 Tasks

| # | Task | Output |
|---|---|---|
| 1.1 | Untrack `personas.yaml`, gitignore it | commit |
| 1.2 | Move `display_formatters.py` to `src/spire/rendering/` | commit |
| 1.3 | Move PDFs and XLSX out of the source tree | commit |
| 1.4 | Remove scratch files from the repo | commit |
| 1.5 | Write the registry drift map | `docs/audit/phase-1-audit.md` §A |
| 1.6 | Write the bug inventory | `docs/audit/phase-1-audit.md` §B |
| 1.7 | Write the dead code inventory | `docs/audit/phase-1-audit.md` §C |
| 1.8 | Write the inconsistency inventory | `docs/audit/phase-1-audit.md` §D |
| 1.9 | Capture baseline metrics | `docs/audit/phase-1-audit.md` §E |
| 1.10 | Save three golden outputs | `docs/audit/golden/*.txt` |

### 6.5 Acceptance criteria

- `personas.yaml` is untracked; credentials rotated.
- The audit document exists and is complete.
- The golden outputs are saved and reproducible: running the same three prompts today produces byte-identical output.
- All tests still pass (the mechanical moves shouldn't break anything).
- No code changes beyond the mechanical hygiene.

### 6.6 Rollback

Revert the merge commit. Restore the moved files. If credentials were rotated, no rollback — the rotation stands.

### 6.7 Phase 1 Status

**Current status:** ⬜ Not started

**Evidence:**

*(to be filled in after Phase 1 completes)*

**Deviations from plan:**

---

## 7. Phase 2 — Correctness

### 7.1 Objective

Fix every bug the audit found. Add a regression test for each. Do not consolidate or restructure; just make the code correct.

### 7.2 Why here

Buggy code should not be consolidated (Phase 3) or moved (Phase 4). Consolidation duplicates bugs. Restructuring hides bugs in a wave of imports.

The audit (Phase 1) produced a bug list. Phase 2 turns that list into zero.

### 7.3 Design

**7.3.1 Prioritize by severity.**

Not every bug is equally important. Sort the audit's bug list into:

- **Wrong-data bugs** — the answer says something false. Fix first.
- **Crash bugs** — the pipeline errors out. Fix second.
- **Missing-capability bugs** — the prompt refuses when it shouldn't. Fix third.
- **Cosmetic bugs** — the answer is right but ugly. Fix last.

**7.3.2 One bug, one branch, one test.**

Do not bundle bugs. Each fix:

- Gets its own small branch (or its own commit on the phase-2 branch).
- Gets its own regression test.
- Gets verified with the exact prompt that exposed it.

**7.3.3 The regression test proves the fix stays fixed.**

The test asserts the *correct* behaviour, not just the absence of the bug. If the bug was "supplier sites returns addresses," the test asserts that supplier sites returns sites *and* that the entity name in the answer is Site, not Address.

**7.3.4 No behaviour changes beyond the fixes.**

Phase 2 is not the place for cleanup, refactoring, or style changes. The only changes are the bugs.

**7.3.5 The byte-diff oracle applies.**

Before Phase 2, run the three golden prompts and save the output. After each bug fix, re-run the three golden prompts and confirm the output for those three is unchanged (unless the bug *was* in one of those prompts' output, in which case update the golden file and note the change).

### 7.4 Tasks

| # | Task | Output |
|---|---|---|
| 2.1 | Triage the audit's bug list by severity | revised `docs/audit/phase-1-audit.md` §B |
| 2.2 | Fix wrong-data bugs | one commit per bug + regression test |
| 2.3 | Fix crash bugs | one commit per bug + regression test |
| 2.4 | Fix missing-capability bugs | one commit per bug + regression test |
| 2.5 | Fix cosmetic bugs | one commit per bug |
| 2.6 | Re-run the full prompt suite | updated pass count |
| 2.7 | Update the golden files if any of the three prompts changed | refreshed golden outputs |
| 2.8 | Verify every fix's regression test fails without the fix | evidence in PR |

### 7.5 Acceptance criteria

- Every bug in the audit's list is either fixed with a regression test or deferred with a documented reason.
- The full prompt suite pass count has improved or stayed the same.
- No new failures.
- Every fix's regression test fails without the fix.

### 7.6 Rollback

Phase 2 is composed of independent bug fixes. Each can be reverted individually. The branch as a whole can be reverted if the phase is abandoned.

### 7.7 Phase 2 Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

## 8. Phase 3 — Consistency

### 8.1 Objective

Make the KG the single source of truth. Generate the parser prompt, the classifier menu, the tool dispatch, and the tripwire counts from it. The result: adding a filter becomes one KG row, not five code changes.

### 8.2 Why here

This is the biggest single lever in the plan. Almost every bug the audit finds will trace back to a drift between two parallel registries. Fixing the drift at the source eliminates the *class* of bug, not just individual instances.

Consistency must come *after* correctness because consolidating a buggy registry just produces a buggier one. It must come *before* structure because structure needs to know what belongs where, and consistency makes the code's true architecture visible.

### 8.3 Design

Phase 3 is split into five sub-phases. Each has its own branch and its own PR.

#### 8.3.1 Phase 3a — Prompt coverage validation

**Objective.** Add a test that fails when the KG declares an entity, filter, or field that the parser prompt does not cover.

**Design.** New test:

```python
@pytest.mark.integration
def test_every_entity_appears_in_prompt():
    from spire.nl_parser.context_assembly import _ASSEMBLED_PREAMBLE
    from spire.nl_parser.vocabulary import load_kg_menu
    menu = load_kg_menu()
    missing = [
        e for e in menu.entity_descriptions
        if e not in _ASSEMBLED_PREAMBLE
    ]
    assert not missing, (
        f"Entities in kg_entity but not mentioned in the prompt: {missing}"
    )
```

Plus similar for filters and fields.

**Acceptance.** The test passes today. If it fails, the gap is real; fix the prompt before proceeding.

#### 8.3.2 Phase 3b — Prompt generation from KG

**Objective.** Replace the 51 hand-written `.sysprompt` files with a generator plus a small overlay set.

**Design.**

- A new generator, `src/spire/ops/context/build_parser_context.py`, reads `kg_entity`, `kg_entity_field`, `kg_entity_filter`, `kg_vocabulary`, `kg_edge`, `kg_edge_tool` and emits `.sysprompt` files.
- Overlays in `src/spire/ops/context/overlays/<module>/<filter>.overlay` hold the warnings and examples the generator can't derive.
- The `_SYSTEM_PROMPT_PREAMBLE` literal in `context_assembly.py` is removed. Files are the only source.
- A `--check` mode runs the generator in-memory and compares against committed files.

**Caveat.** The generator halves prompt-authoring work, not eliminates it. ~15 overlays remain hand-written.

**Acceptance.**

- `--check` returns 0.
- `--validate` on all corpora: same tool pass count.
- Adding a filter to the KG produces a new `.sysprompt` file when the generator runs.
- Assembled prompt size is within ±5% of baseline.

#### 8.3.3 Phase 3c — Generic executor (prototype)

**Objective.** Implement `execute_operation` for one entity-level fetch (`search_suppliers`). Prove the pattern works.

**Design.**

- New file `src/spire/mcp_server/tools/execute.py`.
- Reads the KG spec, calls the pod, projects fields, applies client-side filters, returns a `ToolResult`.
- Registered alongside the 34 existing tools.
- Byte-equality test against the legacy tool.

**Acceptance.** The prototype's output matches the legacy tool's output for several argument combinations.

#### 8.3.4 Phase 3d — Generic executor (full)

**Objective.** Extend `execute_operation` to every entity-level fetch, every edge traversal, and every child fetch.

**Design.**

- `kind=entity_level`: direct fetch.
- `kind=edge_traversal`: single parent-id child call.
- `kind=child`: direct child call.
- All variations handled by one dispatch reading the KG.

**Scope.** 8 entities × ~20 filters + 16 edges + all child fetches.

**Acceptance.** Every operation byte-equals its legacy counterpart. `--validate` on all corpora passes. Full prompt suite runs clean.

#### 8.3.5 Phase 3e — Delete legacy tools

**Objective.** Delete the 24 fetch-only tool files. Keep the 7 semantic tools (aggregations, comparisons, lifecycle).

**Design.**

- Delete 24 files.
- Remove their `@mcp.tool()` wrappers.
- Update `planner.py` to emit `execute_operation` instead of tool names.
- Update KG: `kg_entity_tool.mcp_tool_name` becomes `'execute_operation'`.
- Delete corresponding test files.
- Regenerate corpora with `--generate`, review, commit.

**Acceptance.** Only semantic tools + `execute_operation` registered. All tests pass. Full prompt suite passes. Tool count drops from 34 to 12.

### 8.4 Tasks

| # | Task | Branch |
|---|---|---|
| 3.1 | Prompt coverage validation | `phase-3a-prompt-coverage` |
| 3.2 | Rewrite the prompt generator | `phase-3b-prompt-generation` |
| 3.3 | Migrate to generated prompts | same branch |
| 3.4 | Implement `execute_operation` prototype | `phase-3c-generic-executor-prototype` |
| 3.5 | Extend to all entity-level fetches | `phase-3d-generic-executor-entity` |
| 3.6 | Extend to edge traversals and children | `phase-3d-generic-executor-edges` |
| 3.7 | Delete legacy tool files | `phase-3e-delete-legacy-tools` |
| 3.8 | Regenerate corpora | same branch |

### 8.5 Acceptance criteria

- The KG is the single source of truth for: entity list, field list, filter definitions, edge definitions, tool dispatch, classifier menu, parser prompt.
- `--check` on the prompt generator returns 0.
- Adding a filter is one KG row.
- Adding a field is one KG row.
- The full test suite passes.
- The full prompt suite passes.
- Tool count is 12 (1 generic + 11 semantic), down from 34.

### 8.6 Rollback

Each sub-phase has its own rollback. Phase 3e (deleting legacy tools) keeps the deleted files in a `legacy/` directory for one sprint.

### 8.7 Phase 3 Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

## 9. Phase 4 — Structure

### 9.1 Objective

Reorganize the source tree and the code so the layout reflects the actual architecture. Split tests by concern. Move entry points into the package.

### 9.2 Why here

Consistency work (Phase 3) made the code's true shape visible. Before that, the architecture was obscured by drift. After it, the boundaries are obvious: the KG layer, the pipeline stages, the rendering layer, the operators, the entry points.

Structure must come *after* consistency because you can't decide where a module belongs until you know what it is. It must come *before* observability because you want to instrument stable code, not code that's about to move.

### 9.3 Design

#### 9.3.1 Phase 4a — Source-tree reorganization

**Target tree:**

```
spire/
├── pyproject.toml
├── README.md
├── persona.example.yaml
├── context_bundles.yaml
├── specs/                        ← new: endpoint and module specs
│
├── src/spire/
│   ├── config.py
│   ├── diagnostics.py
│   ├── cli/                      ← new: installable entry points
│   │   ├── run.py
│   │   ├── prompt_set.py
│   │   ├── promptkit.py
│   │   ├── promptkit_overnight.py
│   │   ├── overnight.py
│   │   └── inspect_trace.py
│   ├── ops/                      ← new: operator tooling (installable)
│   │   ├── kg/
│   │   │   ├── rebuild.py
│   │   │   ├── print.py
│   │   │   ├── schema.sql
│   │   │   └── smoke_test.py
│   │   ├── context/
│   │   │   ├── build_parser_context.py
│   │   │   └── build_classifier_context.py
│   │   ├── endpoint/             ← Phase 7 lives here
│   │   │   ├── add.py
│   │   │   └── validate.py
│   │   ├── build_context.py
│   │   ├── draw_graph.py
│   │   └── flag_matrix.sh
│   ├── rendering/                ← new: display layer
│   │   ├── __init__.py
│   │   └── formatters.py
│   ├── executor/
│   ├── fusion/
│   ├── graph/
│   ├── kg/
│   ├── mcp_server/
│   ├── nl_parser/
│   ├── oracle/
│   ├── planner/
│   └── synthesizer/
│
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   ├── unit/
│   ├── integration/
│   └── manual/
│
├── prompts/                      ← new top-level
│   ├── sets/
│   ├── corpora/
│   └── scorer/
│
├── archive/                      ← new: one-off probes, historical scripts
│   ├── probes/
│   └── migrations/
│
├── docs/
└── data/                         ← gitignored runtime artifacts
    ├── traces/
    ├── context_out/
    └── .spire_cache/
```

**Console scripts:**

```toml
[project.scripts]
spire = "spire.cli.run:main"
spire-promptkit = "spire.cli.promptkit:main"
spire-kg = "spire.ops.kg.print:main"
```

#### 9.3.2 Phase 4b — Test suite split

Move `tests/` from flat to component-organized:

```
tests/
├── unit/
│   ├── planner/
│   ├── nl_parser/
│   ├── executor/
│   ├── synthesizer/
│   ├── mcp_server/
│   ├── graph/
│   ├── core/
│   └── regressions/
├── integration/
│   ├── fusion/
│   ├── kg/
│   ├── agent/
│   ├── nl_parser/
│   └── mcp_tools/
└── manual/
```

`tests/conftest.py` auto-marks anything under `tests/integration/`.

`pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["integration: tests requiring external services"]
addopts = "-m 'not integration'"
```

#### 9.3.3 Phase 4c — Module boundaries

Where Phase 3 revealed that a module bundles multiple concerns, split it. Where it revealed that a concern is scattered, consolidate it.

Examples (actual splits depend on Phase 3's findings):

- If `synthesizer.py` still holds multiple concerns despite the earlier split, finish the split.
- If `planner.py` has business logic that belongs in a builder, move it.
- If the display layer and the render layer are tangled, separate them.

This is the smallest sub-phase and the most judgement-dependent. It's also the one where doing it *after* consistency matters most — before Phase 3, you'd split things along the wrong seams.

### 9.4 Tasks

| # | Task | Branch |
|---|---|---|
| 4.1 | Move `scripts/` → `src/spire/cli/` and `src/spire/ops/` | `phase-4a-source-tree` |
| 4.2 | Move `scripts/prompts/` → `prompts/` | same |
| 4.3 | Move runtime artifacts → `data/` | same |
| 4.4 | Move `test_tools/` → `tests/manual/` | same |
| 4.5 | Add console scripts to `pyproject.toml` | same |
| 4.6 | Move `archive/` probes out | same |
| 4.7 | Split `tests/` by component | `phase-4b-test-split` |
| 4.8 | Add `tests/conftest.py` auto-marker | same |
| 4.9 | Split bundled modules | `phase-4c-module-boundaries` |

### 9.5 Acceptance criteria

- `spire --prompt "Count of suppliers"` works from anywhere after `pip install -e .`.
- `pytest -q` passes with the same count as before.
- `pytest -q tests/unit/` runs fast (<30s).
- Three golden prompts still byte-identical.
- Every import that referenced a moved file is updated.

### 9.6 Rollback

Each sub-phase reverts independently. The `src/spire/cli/` and `src/spire/ops/` moves are the largest single change; the rest is mechanical.

### 9.7 Phase 4 Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

## 10. Phase 5 — Observability

### 10.1 Objective

Instrument every pipeline stage with OpenTelemetry spans. Replace the `--show-*` flag diagnostics with structured traces for production use.

### 10.2 Why here

Observability must come *after* structure because you want to instrument stable code — code that isn't about to move. It must come *before* performance because you can't prove a performance change helped without a baseline.

The `--show-*` flags remain for local development. OTel is for production: multiple requests, aggregated metrics, distributed traces.

### 10.3 Design

**New module:** `src/spire/observability/`.

```python
# src/spire/observability/__init__.py
from opentelemetry import trace

_tracer = trace.get_tracer("spire")

def get_tracer():
    return _tracer

def setup_otel(exporter="console", service_name="spire"):
    """Configure the OTel tracer. Called once at startup."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    # ...
```

**Wrapping.** Each pipeline stage wraps its work in a span.

- `graph/pipeline.py` — one span per node (`parse`, `plan`, `execute`, `synthesize`).
- `executor/executor.py` — one span per plan step.
- `nl_parser/parser.py` — one span per LLM call, with attributes for model, tokens in/out, cache status.
- `mcp_server/tools/execute.py` — one span per tool invocation, with attributes for endpoint, row count, truncation.

**Attributes.** Every span sets at least:

- `spire.entity` — the entity being queried.
- `spire.stage` — the pipeline stage.
- `spire.tokens.in` / `spire.tokens.out` — for LLM spans.
- `spire.cache.hit` — for cacheable work.
- `spire.truncated` — for fetch spans.

**Exporter.** Configurable via env var. Default: console (dev). Production: OTLP to a collector.

**The `--show-*` flags stay.** They're local, fast, and useful. OTel is additive.

### 10.4 Tasks

| # | Task |
|---|---|
| 5.1 | Add `src/spire/observability/` |
| 5.2 | Wrap pipeline nodes in spans |
| 5.3 | Wrap executor steps in spans |
| 5.4 | Wrap LLM calls in spans with token attributes |
| 5.5 | Wrap tool invocations in spans |
| 5.6 | Configure exporter via env var |
| 5.7 | Document the trace shape |

### 10.5 Acceptance criteria

- One full request produces a trace with the expected span hierarchy.
- Attributes are present and correct.
- Overhead is under 1% of wall-clock.
- The `--show-*` flags still work.

### 10.6 Rollback

Remove the span wrappers. The observability module can stay as dead code or be deleted.

### 10.7 Phase 5 Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

## 11. Phase 6 — Performance

### 11.1 Objective

Reduce latency and cost without changing answers. Add caching and parallel execution.

### 11.2 Why here

Performance must come *after* observability because you need a baseline to prove the change helped. It must come *before* extensibility because you want the generator to produce endpoints into a fast, well-understood system, not a slow, drifting one.

### 11.3 Design

#### 11.3.1 Phase 6a — Tool-result cache

**Objective.** TTL cache around MCP tool calls.

**Design.** New `src/spire/mcp_server/tools/cache.py`. Keyed on `(tool_name, frozen_args)`. TTL 300s (configurable). Env flag `SPIRE_TOOL_CACHE_DISABLE=1` for testing.

Wrap `session.call_tool` in the executor.

**Constraint.** The cache must respect `truncated`. Cached results carry truncation metadata verbatim, and the synthesizer narrates it as the cache's own truncation.

**Acceptance.** Two concurrent identical requests → one pod fetch. No answer change.

#### 11.3.2 Phase 6b — Parallel execution

**Objective.** Replace sequential `for step in plan` with a dependency-aware parallel executor.

**Design.** Add `depends_on: list[str]` to `Step`. `plan_builders.py` sets it for each step (it already knows the `iterate_over.from_step` chain). The executor runs ready steps concurrently.

**Acceptance.** The anchor question drops from ~17s to under 5s. Byte-diff identical to sequential.

#### 11.3.3 Phase 6c — Intent cache

**Objective.** Implement the three-stage intent cache from `docs/cache_architecture.md`.

**Design.** New modules: `intent_cache.py`, `intent_cache_backends.py`, `intent_cache_verify.py`. The router consults the cache before classify+parse.

**Acceptance.** Ten repeats of one prompt → one LLM parse call. Zero new failures in `--validate`. Cache invalidates on KG rebuild.

### 11.4 Tasks

| # | Task | Branch |
|---|---|---|
| 6.1 | Implement tool-result cache | `phase-6a-tool-cache` |
| 6.2 | Add `depends_on` to plan steps | `phase-6b-parallel` |
| 6.3 | Implement parallel executor | same |
| 6.4 | Implement three-stage intent cache | `phase-6c-intent-cache` |
| 6.5 | Verify no byte-diff changes | same |

### 11.5 Acceptance criteria

- Anchor question latency drops measurably.
- All answers byte-identical to pre-Phase-6 output.
- Cache respects truncation.
- All tests pass.

### 11.6 Rollback

Each sub-phase reverts independently. The cache is disableable by env flag.

### 11.7 Phase 6 Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

## 12. Phase 7 — Extensibility

### 12.1 Objective

Turn the accumulated machinery (KG as source of truth, generic dispatch, generated prompts) into a single command a developer can run to add a new endpoint.

### 12.2 Why last

Extensibility is the *output* of doing everything else well. It needs:

- **Correctness** — don't generate specs for buggy endpoints.
- **Consistency** — generators read from a single source of truth.
- **Structure** — generators write into a settled tree.
- **Observability** — new endpoints should be observable from day one.
- **Performance** — new endpoints should be fast without extra work.

Doing extensibility earlier would build a generator over unstable ground. Every later phase would invalidate it.

### 12.3 Design

Phase 7 is split into four sub-phases.

#### 12.3.1 Phase 7a — Endpoint spec format

**Objective.** Define the YAML spec that declares one endpoint.

**Design.** One YAML file per endpoint in `specs/endpoints/`. The spec is the *only* artifact a developer writes.

**Full schema:**

```yaml
name: get_supplier_sites            # MCP tool name (unique)
entity: Site                         # canonical entity name
module: supplier                     # one of the four Fusion modules
kind: child                          # entity_level | edge_traversal | child

endpoint:
  path: /fscmRestApi/resources/11.13.18.05/suppliers/{supplier_id}/child/sites
  fields: [SupplierSiteId, SupplierSite, ProcurementBU, ProcurementBUId, Status]
  parent_id_field: SupplierId

entity_meta:
  canonical_id_field: SupplierSiteId
  display_name_field: SupplierSite
  description: |
    A supplier site (an assignment point). A supplier can have many sites,
    each in a different ProcurementBU. Only accessible as a child of Supplier.

fields:
  - {name: SupplierSiteId,  role: canonical_id, type: numeric}
  - {name: SupplierSite,    role: display_id,   type: string}
  - {name: ProcurementBU,   role: projection,   type: string}
  - {name: ProcurementBUId, role: projection,   type: numeric}
  - {name: Status,          role: status,       type: string}

filters:
  - name: has_site_in_bu
    kind: edge_traversal
    tool_arg: business_unit
    vocab_kind: supplier_site_bu
    server_q: "ProcurementBU='{value}'"
    keep_parent_when: nonempty

parent_edge:
  name: HAS_SITE
  from_entity: Supplier
  from_join_field: SupplierId
  to_join_field: SupplierId
  cardinality: one_to_many
  tool: get_supplier_sites

prompt_overlay: |
  - 'suppliers with a site in business unit X' -> a 'has_site_in_bu'
    filter whose value is the canonical display string for that business unit.

test_hint:
  example_args: {business_unit: "US1 Business Unit"}
  expected_item_keys: [SupplierSiteId, SupplierSite, ProcurementBU]
```

**Validation.** A `spire validate-endpoint` command checks:

- Required fields present.
- Module and kind are known.
- Every field in `endpoint.fields` is declared.
- No name collision (unless `--update`).
- Referenced vocab kinds exist.

**Acceptance.** A real existing endpoint (`supplier_sites`) can be spec'd and validated.

#### 12.3.2 Phase 7b — `spire add-endpoint` generator

**Objective.** One command takes a validated spec and applies every change needed to make the endpoint live.

**Design.**

```bash
spire add-endpoint specs/endpoints/supplier_sites.yaml
```

Behind the scenes:

1. Load and validate the spec.
2. Apply KG changes in one transaction: entity, fields, edge, edge_tool, filter, entity_tool.
3. Rebuild the KG.
4. Regenerate the parser prompt.
5. Regenerate the classifier menu.
6. Update tripwire counts (`test_kg_metadata.py`, `ops/kg/print.py`, `schema.sql` banners).
7. Emit a stub integration test.
8. Print a diff summary.

**Flags.**

- `--dry-run` — show what would change without applying.
- `--update` — for adding fields/filters to an existing entity.
- `--no-rebuild` — skip KG rebuild (batch additions).
- `--yes` — skip confirmation.

**Acceptance.**

- Applies every change cleanly.
- `pytest -q` passes after.
- Endpoint is queryable end-to-end via a natural-language prompt.
- `--dry-run` shows the same summary without applying.
- Idempotent: running twice on the same spec errors unless `--update`.

#### 12.3.3 Phase 7c — `spire add-module` generator

**Objective.** Adding a new Fusion module is a data operation.

**Design.**

```yaml
# specs/modules/hcm.yaml
name: hcm
display_name: "HCM / Human Capital"
description: |
  Human Capital Management — employees, positions, payroll, and
  related workforce data.
entities: [Employee, Position, PayrollRelationship]
```

```bash
spire add-module specs/modules/hcm.yaml
```

Applies:

1. Update the `chk_kg_entity_module` CHECK constraint.
2. Update `KNOWN_MODULES` in `context_assembly.py`.
3. Create `src/spire/nl_parser/context/hcm/`.
4. Regenerate the classifier menu.
5. Regenerate the parser prompt.
6. Emit a README in the new context directory.

**Acceptance.** Adding a module works, and adding endpoints to it works via Phase 7b.

#### 12.3.4 Phase 7d — Documentation + walkthrough

**Objective.** Write the developer-facing docs that make Phase 7a–7c usable.

**Deliverables.**

- `docs/extending/adding-an-endpoint.md`
- `docs/extending/adding-a-module.md`
- `docs/extending/adding-a-field-or-filter.md`
- `docs/extending/spec-reference.md`
- `docs/extending/troubleshooting.md`
- A worked walkthrough showing the 15-minute flow.

**Acceptance.** A developer who has never seen SPIRE can add an endpoint in 30 minutes following the docs. A tripwire test asserts the walkthrough's commands still work.

### 12.4 Tasks

| # | Task | Branch |
|---|---|---|
| 7.1 | Define the endpoint spec format + validator | `phase-7a-spec-format` |
| 7.2 | Implement `spire add-endpoint` | `phase-7b-add-endpoint` |
| 7.3 | Implement `spire add-module` | `phase-7c-add-module` |
| 7.4 | Write the extensibility docs | `phase-7d-extensibility-docs` |
| 7.5 | Record the 15-minute walkthrough | same |

### 12.5 Acceptance criteria

- Adding a new endpoint touches ≤2 files (the spec + a test stub).
- Adding a filter is one line in the spec.
- Adding a field is one line in the spec.
- Adding a module is one YAML file plus endpoints.
- The walkthrough works from a fresh clone.

### 12.6 Rollback

Each sub-phase reverts independently. The generator can be bypassed by hand-editing the KG (the old way still works).

### 12.7 Phase 7 Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

# Part III — Tracking

## 13. Phase completion checklist

Before merging any sub-phase's PR, run this checklist. Every box must be ticked.

### 13.1 Tests

- [ ] `pytest -q` → all tests pass.
- [ ] `pytest -q --collect-only | tail -1` → new test count recorded.
- [ ] Full prompt suite runs with no new failures.

### 13.2 Byte-diffs

- [ ] `"Count of suppliers"` — stdout identical to the golden file.
- [ ] `"Show PO 2144 and its lines"` — stdout identical.
- [ ] `"Which suppliers have open purchase orders?"` — stdout identical.
- (For phases that intentionally change output — record and explain; update the golden file.)

### 13.3 KG integrity

- [ ] `spire-ops kg rebuild` succeeds.
- [ ] `spire-ops kg print --counts-only` matches expected.
- [ ] `tests/integration/kg/test_kg_metadata.py` passes.

### 13.4 Branch and PR

- [ ] Branch named `phase-{N}{letter}-...` per §5.
- [ ] Commits use named `git add`, not `-A`.
- [ ] PR uses the template at §13.6.
- [ ] PR linked to this document (§{N}).

### 13.5 Documentation

- [ ] §5 Phase Index row updated.
- [ ] §{N} Status section updated.
- [ ] §14 Session Log has a new entry.
- [ ] README references updated.

### 13.6 PR template

```markdown
## Phase {N}{letter} — {Name}

**Objective:** {one sentence}
**Branch:** `{branch}`
**Tracking:** §{section} of SPIRE_CORRECTNESS_CONSISTENCY_GROWTH.md

### Changes
- {bullet}

### Test evidence
- `pytest --collect-only` before: {N} selected
- `pytest --collect-only` after: {N'} selected
- `pytest -q` after: {pass_count} passed
- Byte-diff of three golden prompts: {identical / diff link}

### Rollback
`git revert {sha}`. Delete: {new files}.

### Deviations from plan
{none / list}

### Status update
After merge, update §5 Phase Index and §14 Session Log.
```

---

## 14. Session Log

**Append-only. Newest entry at the top.**

### Template

```markdown
### YYYY-MM-DD — Session N

**Phase in progress:** {phase}
**Branch:** `{branch}`
**Session goal:** {what you set out to do}

**Done:**
- {bullet}

**Evidence:**
- `pytest -q`: {pass count}
- Full prompt suite: {pass count}
- Byte-diff of three golden prompts: {identical / diff}

**Blockers / open questions:**
- {bullet}

**Next session should:**
- {bullet}

**Commits on branch:**
- `{sha}` — {message}
```

### Entries

*(No entries yet. The first session will add the first entry.)*

---

# Appendices

## Appendix A — Baseline state (2026-09-13)

| Metric | Value | How measured |
|---|---|---|
| Test count | **996 selected, 18 deselected, 1014 total** | `pytest -q --collect-only \| tail -1` |
| Test collection time | 2.47s | same |
| Python files in `src/spire/` | 71 | `find src/spire -name "*.py" \| wc -l` |
| Python files in `scripts/` | 33 | `find scripts -name "*.py" \| wc -l` |
| Python files in `tests/` | 55 | `find tests -name "*.py" \| wc -l` |
| MCP tool count | 34 | `server.py` `@mcp.tool()` occurrences |
| `.sysprompt` files | 51 | `find src/spire/nl_parser/context -name "*.sysprompt" \| wc -l` |
| Parser prompt input tokens | 8,805–8,819 | from `[llm] stage=parse in=...` logs |
| LLM calls per request (typical) | 2 | classify + parse |
| LLM calls per request (worst case) | 3 | classify + parse + synthesize |
| Anchored query wall-clock | ~16s | `run_graph.py` on PO 701337 prompt |

**Dependency versions:**

| Package | Version |
|---|---|
| fastmcp | 3.4.3 |
| mcp | 1.27.1 |
| langgraph | 1.2.0 |
| langchain-core | 1.4.0 |
| langchain-google-genai | 4.2.2 |
| langchain-mcp-adapters | 0.2.2 |
| oracledb | 4.0.0 |
| pydantic | 2.13.4 |

**KG row counts (2026-09-13):**

| Table | Rows |
|---|---|
| `kg_entity` | 22 |
| `kg_entity_field` | 210 |
| `kg_edge` | 17 |
| `kg_pattern` | 3 |
| `kg_vocabulary` | 120 |
| `kg_pattern_binding` | 3 |
| `kg_entity_tool` | 10 |
| `kg_entity_filter` | 26 |
| `kg_edge_tool` | 16 |

---

## Appendix B — Evidence capture templates

### B.1 Test evidence block

```
$ pytest -q --collect-only | tail -1
{N} selected, {M} deselected, {T} total

$ pytest -q
{N} passed, {M} deselected in {T}s
```

### B.2 Byte-diff evidence block

```bash
python -m spire.cli.run --prompt "Count of suppliers" > /tmp/after.txt 2>&1
diff docs/audit/golden/count_suppliers.txt /tmp/after.txt
```

### B.3 Timing evidence block

```bash
$ time python -m spire.cli.run --prompt "Show PO 2144 and its lines"
[...]
real  0m{N}.{M}s
```

### B.4 KG integrity block

```bash
$ spire-ops kg rebuild
$ spire-ops kg print --counts-only
```

---

## Appendix C — Decisions log

Cross-session decisions that affect multiple phases.

| Date | Decision | Rationale |
|---|---|---|
| 2026-09-13 | **The origin: SPIRE is a graph-to-REST realization of the graph-to-SQL vision.** It exists to make NL-to-data trustworthy. | This framing grounds the plan; extensibility is a consequence, not a goal. |
| 2026-09-13 | **The seven phases are ordered Audit → Correctness → Consistency → Structure → Observability → Performance → Extensibility.** | Each is a provable prerequisite of the next. See Appendix D. |
| 2026-09-13 | **Extensibility is Phase 7, not Phase 1.** | A correct, consistent, structured system is extensible by construction. |
| 2026-09-13 | **Consistency is the biggest single lever.** | Almost every audit bug will trace back to drift between parallel registries. |
| 2026-09-13 | The KG stays. No agent loop. | Every bug lives in code that reads the KG, not in the KG itself. |
| 2026-09-13 | The synthesizer is 90% local already. Do not rewrite. | Two remaining LLM-path shapes finish incrementally in Phase 6. |
| 2026-09-13 | `personas.yaml` tracking is a security issue. Fixed in Phase 1, first commit. | Contains live credentials; rotation required separately. |
| 2026-09-13 | Entry points move to `src/spire/cli/`, operators to `src/spire/ops/`. | Installable console scripts. |
| 2026-09-13 | Phase 3b halves prompt-authoring work, not eliminates it. | Warnings and examples are not derivable; overlays preserve them. |
| 2026-09-13 | Phase 3e target: 34 tools → 12 (1 generic + 11 semantic). | Aggregations, comparisons, lifecycle stay as dedicated tools. |
| 2026-09-13 | Phase 6b (parallel) is the highest user-visible latency win. | ~17s → <5s on the anchor question. |
| 2026-09-13 | Endpoint spec format is YAML, one file per endpoint, in `specs/endpoints/`. | Readable, diffable, validated. |
| 2026-09-13 | `spire add-endpoint` is idempotent; requires `--update` for re-runs. | Prevents accidental double-inserts. |

---

## Appendix D — The dependency argument (why this order)

Every phase is a prerequisite of every phase after it. Here is the proof by construction.

**1 → 2: Audit before Correctness.**
You cannot fix what you have not measured. The audit produces the bug list that Phase 2 turns into zero.

**2 → 3: Correctness before Consistency.**
Consolidating buggy code consolidates the bug. A bug in a hand-written prompt that gets generated becomes a bug in the generator. A bug in a hand-written tool that becomes a dispatch becomes a bug in the dispatch.

**3 → 4: Consistency before Structure.**
You cannot decide where a module belongs until you know what the module *is*. Consistency work reveals the true architecture by making the KG the source of truth — the code that reads it becomes the pipeline, the code that generates it becomes tooling, the code that displays it becomes rendering.

**4 → 5: Structure before Observability.**
You want to instrument stable code, not code that is about to move. Wrapping spans around code that will be split next phase means re-wrapping spans.

**5 → 6: Observability before Performance.**
You cannot prove a performance change helped without a baseline. OTel spans give you the per-stage latency data that makes each cache and each parallelization provably worthwhile.

**6 → 7: Performance before Extensibility.**
You want the generator to produce new endpoints into a fast, well-understood system. If the system is slow or drifting, every new endpoint inherits the slowness or the drift.

**7 is the output.**
A system that is correct, consistent, structured, observable, and fast is extensible by construction. `add-endpoint` is not a separate capability; it is the emergence of a well-built system into a single command.

**What the old order (v2.0) got wrong.**
It put Structure first and Extensibility last-but-one, with Consistency and Correctness in between. That ordering forces rework: Structure (Phase 0) reshapes the tree; Consistency (Phase 2) reveals a different architecture; Extensibility (Phase 6) wants to write into a third. Three tree changes for one goal.

The v3.0 order eliminates the rework. Structure is Phase 4, after Consistency has revealed the true shape. Extensibility is Phase 7, after everything else has stabilized. No phase forces a later phase to undo it.

---

## End of document

**Next action:** Open a new DeepSeek window, paste this document, and say:

> *"Resume SPIRE work. Read §5 Phase Index and §14 Session Log. Start Phase 1. Here is the current repo state: [paste `git status`, `git branch`, `pytest -q`]"*

---

**Document version:** 3.0
**Last updated:** 2026-09-13
**Next revision:** After Phase 1 completes, add the first Session Log entry and update §5 Phase Index.