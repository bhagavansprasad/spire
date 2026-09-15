# SPIRE — Correctness, Consistency, and Growth

**Making the NL-to-Data Pipeline Trustworthy, Then Extensible**

**Document version:** 3.2
**Created:** 2026-09-13
**Last revised:** 2026-09-14 (v3.2 plus Addendum A: two-document model; Addendum B: UI and API layer)
**Author:** Bhagavan (with architectural analysis by DeepSeek)
**Status:** Living document. The design is frozen at v3.2. Status sections are appended per completed phase. **Never edit a Design section — record deviations in that phase's Status section.**
**Companion document:** `SPIRE_ROBUSTNESS_EXTENSIBILITY_v3.2_Status.md` — the append-only forensic record. Session detail, bugs, investigations, commands, and outputs live there.

**Change log**

| Version | Date | Change |
|---|---|---|
| 3.0 | 2026-09-13 | Initial seven-phase structure; purpose-first framing. |
| 3.1 | 2026-09-13 | Review-driven additions: drift evidence (S1/S4) in §3; `quirks` spec block in Phase 3d; strengthened Phase 3e acceptance; in-flight work inventory in Phase 1; baseline-snapshot caveat in Appendix A; N-run evidence template in Appendix B; three decisions-log entries; prompt-cache reference in Phase 6c; new §4.5 "In-flight work at v3.1 authoring." |
| 3.2 | 2026-09-14 | Initial-review merge. Adds sub-phases **3f** (deterministic classifier), **3g** (KG versioning), **6d** (plan cache), **6e** (concurrency & back-pressure); adds **§8.3.7** (partial results + explicit gaps); adds **§4.6** (explicit non-goals); adds task **4.12** (`docs/architecture/`). No phase renumbering. No phase reordering. |
| 3.2 | 2026-09-14 | Addendum A — Two-document model. Introduces the companion status document. Adds a "Two-document model" subsection to "How to read this document." Updates §15 Session Log to a pointer index. Updates §14.5 checklist. No design changes. No phase renumbering. |
| 3.2 | 2026-09-14 | Addendum B — UI and API layer. Adds sub-phase **4d** (UI and API layer). Adds §10.3.5. Adds task rows 4.13–4.17. Adds two console scripts (`spire-api`, `spire-ui`) and two source directories (`src/spire/api/`, `src/spire/ui/`) to the Phase 4a target tree. No design changes elsewhere. No phase renumbering. No phase reordering. |

---

## How to read this document

**Part I (§1–§4) explains why we are doing this work.** It is the origin story: where SPIRE came from, what it is, where it falls short, what the plan achieves, and what is already in flight. Read this first.

**Part II (§5–§12) is the seven-phase plan.** Each phase has a Design section (frozen at v3.2) and a Status section (updated as work proceeds).

**Part III (§13–§14) is the tracking machinery.** The Phase Index and the Session Log are the two places that change every session.

**Rules for cross-session continuity:**

1. **Never edit a Design section.** If the design turns out to be wrong, record the deviation in that phase's Status section.
2. **Update the Phase Index (§6) at the end of every session.**
3. **Add a Session Log entry (§15) at the end of every session.** Newest at the top.
4. **When resuming in a new DeepSeek window, paste this document and say:** *"Resume SPIRE work. Read §6 Phase Index and §15 Session Log. Current phase is [X]. Here is the repo state: [paste `git status`, `git branch`, `pytest -q`]."*

### Two-document model

This plan is maintained as two files:

- **Doc A** — this document. The frozen plan. It changes only when a phase completes or the design is formally revised. It carries the seven phases, the sub-phases, the acceptance criteria, and the dependency argument.
- **Doc B** — `SPIRE_ROBUSTNESS_EXTENSIBILITY_v3.2_Status.md`. The append-only forensic record. Every session, every bug, every investigation, every test, every command, and every output lives here. Nothing is deleted.

**Where each kind of content lives:**

| Content | Doc A | Doc B |
|---|---|---|
| Phase design and acceptance criteria | ✅ frozen | — |
| Phase status (not started / in progress / complete) | ✅ §6 Index and §{N}.7 Status | ✅ §1 snapshot |
| Session detail (work items, commands, outputs) | — | ✅ §4 |
| Bug register | — | ✅ §2.1 |
| Investigation register | — | ✅ §2.2 |
| Session-level decisions | Appendix C (when promoted) | ✅ §2.3 |
| Open questions | — | ✅ §2.4 |
| Session pointer (one line) | ✅ §15 | — |

**Checkpoint discipline.** At every checkpoint:

1. Update Doc B §1 (snapshot) and §2 (registers).
2. Add the full session entry to Doc B §4.
3. Add a one-line pointer to Doc A §15.
4. Update Doc A §6 Phase Index and the phase's §{N}.7 Status.
5. Emit the checkpoint block. Copy it into Doc B. Copy the pointer into Doc A.

**Why two documents.** Doc A must stay small enough to paste into a new window without dragging history. Doc B must be complete enough that no history is lost when a window reaches its limit. The split keeps the plan invariant and the record complete.

---

## Table of Contents

**Part I — Why we are doing this**
1. [The origin: a graph database, a natural-language question, and SQL](#1-the-origin-a-graph-database-a-natural-language-question-and-sql)
2. [What SPIRE is today](#2-what-spire-is-today)
3. [Where SPIRE falls short](#3-where-spire-falls-short)
4. [What this plan achieves](#4-what-this-plan-achieves)
   - 4.6 [Explicit non-goals and when to revisit](#46-explicit-non-goals-and-when-to-revisit)
5. [In-flight work at v3.1 authoring](#5-in-flight-work-at-v31-authoring)

**Part II — The seven phases**
6. [Phase Index](#6-phase-index)
7. [Phase 1 — Audit & Baseline](#7-phase-1--audit--baseline)
8. [Phase 2 — Correctness](#8-phase-2--correctness)
   - 8.3.7 [Partial results and explicit gaps](#837-partial-results-and-explicit-gaps)
9. [Phase 3 — Consistency](#9-phase-3--consistency)
   - 9.3.6 [Phase 3f — Deterministic classifier](#936-phase-3f--deterministic-classifier)
   - 9.3.7 [Phase 3g — KG versioning](#937-phase-3g--kg-versioning)
10. [Phase 4 — Structure](#10-phase-4--structure)
11. [Phase 5 — Observability](#11-phase-5--observability)
12. [Phase 6 — Performance](#12-phase-6--performance)
    - 12.3.4 [Phase 6d — Plan cache](#1234-phase-6d--plan-cache)
    - 12.3.5 [Phase 6e — Concurrency and back-pressure](#1235-phase-6e--concurrency-and-back-pressure)
13. [Phase 7 — Extensibility](#13-phase-7--extensibility)

**Part III — Tracking**
14. [Phase completion checklist](#14-phase-completion-checklist)
15. [Session Log](#15-session-log)

**Appendices**
- [A — Baseline snapshot (2026-09-13)](#appendix-a--baseline-snapshot-2026-09-13)
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
- **The test suite is broad** — approximately 1,000 tests, most fast, most passing.

**What's working well enough to build on:**

- The three-language interface (KG in Oracle, pipeline in Python, tools in MCP) is coherent.
- The design decisions in `docs/spire_plan.md` are sound.
- The refusal and truncation work is ahead of most comparable systems.

---

## 3. Where SPIRE falls short

SPIRE has accreted. As it grew from five endpoints to twenty-two entities, from three tools to thirty-four, from one prompt file to fifty-one, parallel registries emerged that must stay in sync by hand. That accretion is the source of the problems this plan addresses.

**Problem 1 — Parallel registries drift.**

The KG declares entities, filters, edges, vocabularies. But the parser prompt hand-writes the same information. The tool files hand-code the same endpoints. The tripwire tests hand-count the same rows. When any one of these is updated without the others, drift appears — and the drift is silent. The codebase itself documents this as a recurring defect class, calling out "the four places that must move together, not two as earlier notes implied."

**This is not theoretical.** Two shipped, documented bugs in the recent history are direct instances of this pattern:

- **S1** — the parser prompt taught one shape ("supplier details for PO X is a lifecycle query") while the planner expected another (a PurchaseOrder root with a `by_id` filter), and the model flipped between the two on identical input. The bug was not in either side individually; it was in the drift between the prompt's teaching and the planner's expectation.
- **S4** — a `supplier_number` vs `supplier_id` mismatch across the KG row, the tool signature, and the routing placeholder. The KG said one thing, the tool hardcoded another, and the routing layer held a third. Each was internally consistent; the join between them was not.

These are the exact shape the plan is designed to eliminate. Citing them here is deliberate: **the failure class is proven, not hypothetical, and the two bugs that motivated this plan are instances of it.**

**Problem 2 — Bugs hide in the drift.**

When the KG says "the supplier filter routes to `supplier_number`" and the tool hardcodes `supplier_name`, the bug is invisible until a prompt hits it. When the parser prompt teaches one shape and the planner expects another, the failure surfaces three phases downstream. The bug's *mechanism* is a mismatch between two registries, not an error in either one.

**Problem 3 — Extensibility is expensive.**

Adding one new endpoint touches sixteen files. Adding a filter touches five. Adding a module touches dozens. Every one of these is a place to forget a step. The work compounds: each addition makes the next addition more expensive because more parallel registries exist.

**Problem 4 — The code is structured for the past, not the present.**

The `src/spire/` layout reflects an earlier version of the system. Some modules bundle multiple concerns. Some concerns are scattered across modules. Tests are flat. Entry points are in scripts, not in the package. None of this is fatal, but it makes the true architecture invisible.

**Problem 5 — There is no clear seam for the future.**

The founding vision was graph-to-SQL. SPIRE is graph-to-REST. To retarget to SQL — or to any other backend — you need a clean interface between "the pipeline that understands questions" and "the layer that talks to the data source." Today that interface is implicit, embedded in thirty-four tool files and a hand-written dispatch.

**Problem 6 — Determinism is assumed but not always enforced.**

Two LLM calls per request means two places where the same input can produce different output across runs. The parser's include list flips. The classifier's module set flips. The synthesizer's summary drifts. Each of these has been observed in the last two weeks. The plan's correctness phase must account for bugs that fire probabilistically, not just ones that fire every time.

**Problem 7 — The pipeline has no partial-failure behaviour.**

`execute_plan` iterates steps and any exception fails the whole plan. A five-step plan that fails at step four returns nothing. This is not just a UX wart — it is a correctness gap. The pipeline discards successful work when a later step fails.

**The common thread:** SPIRE's *capability* grows linearly with developer effort, but its *trustworthiness* and *velocity* decrease. That is the wrong shape for a system that is supposed to keep growing — and eventually to serve as the foundation for the SQL vision.

---

## 4. What this plan achieves

**The plan makes SPIRE correct, consistent, and structured — in that order — so it becomes a foundation that can be trusted, extended, and eventually retargeted.**

Concretely, by the end of all seven phases:

**Correctness.**

- Every known bug is fixed with a regression test that proves it stays fixed.
- The audit's findings are turned into a bug list, and the bug list is turned into zero.
- Probabilistic bugs (parser non-determinism, classifier drift) are held to a repeated-run evidence standard, not a single-pass test.
- The pipeline behaves correctly under partial failure: successful steps are returned, failed steps are reported, and the synthesizer narrates the gap. (§8.3.7)

**Consistency.**

- The KG is the single source of truth. The parser prompt is generated from it. The tool dispatch is generated from it. The tripwire counts are generated from it. Drift becomes structurally impossible.
- Adding a filter is one KG row. Adding a field is one KG row. No code change.
- The classifier is a deterministic gazetteer, not an LLM call. (§9.3.6)
- The KG carries a version stamp; caches invalidate correctly. (§9.3.7)

**Structure.**

- The tree reflects the architecture. Modules have clear boundaries. Tests are organized by concern. Entry points are installable console scripts.
- A new contributor can find what they need without reading the whole codebase.

**Observability.**

- Every pipeline stage emits a span. Latency, tokens, and errors are visible per stage.
- A failing request can be diagnosed from a single trace.

**Performance.**

- Repeated questions reuse cached results. Independent steps run in parallel. Concurrent requests are handled without saturating the LLM or the pod.
- Latency per request drops. Growing the system stays neutral-or-better on wall-clock.
- LLM calls per request drop from three to one for most prompts (parse only). (§9.3.6, §12.3.3)

**Extensibility.**

- Adding a new endpoint is one YAML file and one command.
- Adding a filter or field is one line in that file.
- Adding a new Fusion module is a data operation, not a code migration.

**And the ultimate purpose.** With all of the above in place, the interface between SPIRE's pipeline and its data source becomes explicit — one clean seam where "REST endpoints" could become "SQL tables" or any other backend. SPIRE is not the destination; it is the platform on which the original graph-to-SQL vision can eventually be realized.

**Extensibility is a consequence, not a goal.** A correct, consistent, structured system is extensible by construction. A system that is extensible but inconsistent simply has more places to be wrong. That is why extensibility is Phase 7, not Phase 1.

### 4.6 Explicit non-goals and when to revisit

These are deliberately deferred. They are not missing; they are out of scope for the current plan. Each has a revisit trigger.

- **Page-cap-at-scale / materialized views.** Not needed for current POC scope. The 25k-row `page_all` cap silently truncates at production scale. Revisit when a tenant exceeds ~50k rows for an ordinary aggregation.
- **Multi-tenancy.** Deferred. The KG is single-tenant. Revisit when moving from demo pod to shared production.
- **Streaming.** Deferred. Revisit when partial-result UX (§8.3.7) is in place.
- **Auth.** Deferred. Revisit before any non-internal deployment.

Recording these as non-goals is more honest than silently dropping them. They remain in the initial review's record; they are simply not scheduled.

---

## 5. In-flight work at v3.1 authoring

**This section exists because the plan assumes a starting state, and the starting state is not clean.** Several pieces of work are in progress or recently landed. The audit in Phase 1 will find them; this section is the map so the audit can interpret what it finds.

**Work in flight or recently merged:**

| Item | State | Relationship to phases |
|---|---|---|
| Parser prompt cache (`feat/parser-prompt-cache`) | Merged or in review | Interacts with Phase 6c (Intent cache). The caching work has an important lesson: caching interacts with the model's thinking-step budget, and a cache hit can change the reasoning path, not just the timing. Phase 6c must reference this lesson. |
| S1 remediation (the "supplier details for PO X" bug) | Shipped | Feeds Phase 1's bug inventory as a **closed** example — the fix exists, so the audit records it as evidence of the drift class, not as an open item. |
| S4 remediation (PO supplier filter) | Shipped | Same as S1: closed, cited as evidence. |
| `qa_testcases.json` corpus | Stale | Contains at least one entry that expects `refuse` where the system now returns `search_purchase_orders` (EIP Inc supplier filter). This is a **live, unfixed drift bug** and belongs in Phase 1's bug inventory as a concrete example. |
| Classifier lifecycle flip fix (`feat/router-show-parser-diagnostic`) | Shipped | Related to Phase 3's consistency work — the classifier's teaching and the parser's teaching have to agree, and today they don't always. Phase 3's prompt generation should make the classifier menu a first-class generated artifact. Phase 3f replaces the LLM classifier with a gazetteer. |
| `--validate` philosophy change (tool-gates-pass, module-warns) | Shipped | Affects Phase 3's acceptance criteria. Validation keying on the TOOL, not the module set, is the correct model — but it means "validate passes" is weaker evidence than it looks. Phase 3's byte-equality gate remains the stronger check. |

**What this means for Phase 1's audit:**

1. **The bug inventory is not a greenfield list.** It has closed items (S1, S4) that serve as evidence, open items (the `qa_testcases` drift), and items that will surface as the audit runs.
2. **The registry drift map is not a greenfield survey.** Several registries already have known drift. The audit's job is to *enumerate* the drift, not to discover whether it exists.
3. **Baselines must be re-measured.** See Appendix A. The numbers there are a snapshot from authoring; Phase 1 re-measures.

**A note on phase ordering given in-flight work:**

Some in-flight items naturally belong to phases later in the plan — the parser prompt cache is Phase 6c territory, the S1 fix is Phase 2 territory. **Do not try to absorb them into Phase 1.** Phase 1 audits. The fixes land in their phases. If the audit finds that the in-flight work has introduced *new* drift (which it may have — the cache changes parser timing and behaviour), that goes in the bug inventory.

---

# Part II — The seven phases

## 6. Phase Index

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
| 3f | Consistency — Deterministic classifier | ⬜ Not started | — | — | — | — |
| 3g | Consistency — KG versioning | ⬜ Not started | — | — | — | — |
| 4a | Structure — Source-tree reorg | ⬜ Not started | — | — | — | — |
| 4b | Structure — Test suite split | ⬜ Not started | — | — | — | — |
| 4c | Structure — Module boundaries | ⬜ Not started | — | — | — | — |
| 4d | Structure — UI and API layer | ⬜ Not started | — | — | — | — |
| 5 | Observability | ⬜ Not started | — | — | — | — |
| 6a | Performance — Tool-result cache | ⬜ Not started | — | — | — | — |
| 6b | Performance — Parallel execution | ⬜ Not started | — | — | — | — |
| 6c | Performance — Intent cache | ⬜ Not started | — | — | — | — |
| 6d | Performance — Plan cache | ⬜ Not started | — | — | — | — |
| 6e | Performance — Concurrency & back-pressure | ⬜ Not started | — | — | — | — |
| 7a | Extensibility — Endpoint spec format | ⬜ Not started | — | — | — | — |
| 7b | Extensibility — `add-endpoint` generator | ⬜ Not started | — | — | — | — |
| 7c | Extensibility — `add-module` generator | ⬜ Not started | — | — | — | — |
| 7d | Extensibility — Documentation + walkthrough | ⬜ Not started | — | — | — | — |

**Legend:** ⬜ Not started · 🟡 In progress · 🟢 Complete · 🔴 Blocked · ⚪ Deferred

### 6.1 Why this order, in one paragraph

**Audit before correctness** — you can't fix what you haven't measured. **Correctness before consistency** — consolidating buggy code consolidates the bug. **Consistency before structure** — you can't decide where a module belongs until you know what the module *is*, and consistency work makes the code's true shape visible. **Structure before observability** — instrument stable code, not code that's about to move. **Observability before performance** — you can't prove a performance change helped without a baseline. **Performance before extensibility** — you want to generate new capabilities against a fast, well-understood system, not a slow, drifting one. **Extensibility last** — it is the *output* of everything above; a correct, consistent, structured, instrumented, fast system is extensible by construction. See Appendix D for the full dependency argument.

**v3.2 note.** Sub-phases 3f, 3g, 6d, 6e, and 4d are additions inside existing phases. They do not change the order. The dependency argument is unchanged.

---

## 7. Phase 1 — Audit & Baseline

### 7.1 Objective

Measure everything. Find drift, bugs, dead code, and inconsistencies. Untrack `personas.yaml`. Perform small mechanical hygiene that unblocks later phases. Produce an in-flight work inventory.

### 7.2 Why here

The audit is the *prerequisite* of every other phase. Correctness work needs a bug list. Consistency work needs a list of parallel registries. Structure work needs a map of what exists. Observability, performance, and extensibility all need the baseline metrics the audit produces.

An audit done at any other point would miss the state that earlier phases changed. It has to come first.

### 7.3 Design

**7.3.1 Security pre-work.**

`personas.yaml` is currently tracked in git. It contains live Fusion and Oracle credentials. This is the first commit on the branch.

```bash
git rm --cached personas.yaml
echo "personas.yaml" >> .gitignore
git add .gitignore
git commit -m "security: untrack personas.yaml; gitignore it"
```

After this commit, rotate the credentials. They are in git history.

**7.3.2 Mechanical hygiene.**

Small, safe moves that later phases assume.

- Move `scripts/display_formatters.py` → `src/spire/rendering/formatters.py`, with a re-export `__init__.py`. Update four imports.
- Move PDFs (`docs/*.pdf`, `tests/*.pdf`) → `docs/pdf/`.
- Move `docs/spire_tools_modules.xlsx` → `docs/data/`.
- Remove `source-tree.txt` and `isolation/` from the repo. Add them to `.gitignore`.

These are the only structural changes Phase 1 makes. The substantive restructuring happens in Phase 4, after consistency work has revealed the architecture.

**7.3.3 The audit.**

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

**Closed items to record as evidence** (not to fix — they're already fixed):

- S1 — the parser/planner drift on "supplier details for PO X" (closed).
- S4 — the `supplier_number`/`supplier_id` mismatch (closed).

**Open items known at authoring time:**

- The `qa_testcases.json` corpus expects `refuse` for "list open purchase orders for supplier EIP Inc" where the system now correctly returns `search_purchase_orders`. The corpus is stale; the code is correct. A **corpus-drift bug**.

**C. Dead code inventory.** Modules, functions, or files not referenced by any test, tool, or prompt. `pytest --collect-only` plus `grep` for importers.

**D. Inconsistency inventory.** Style, naming, error handling, logging. Where the codebase says the same thing two ways. Where similar code has different shapes.

**E. In-flight work inventory.** Enumerate the branches and recent merges that the plan must absorb. Start from §5 of this document, but re-verify against the actual git state. For each item: name, state, whether it introduced new drift, whether it left partial work.

**F. Baseline metrics.** The numbers every later phase will compare against:

- Test count (`pytest -q --collect-only | tail -1`).
- Test wall-clock (`pytest -q`).
- Prompt suite pass count (`run_prompt_set.py` on all sets).
- Per-prompt latency (mean, median, p95).
- Per-prompt LLM calls (classify, parse, synth).
- Per-prompt tokens (in, out).
- KG row counts.
- MCP tool count.
- `.sysprompt` file count.

**G. Behavioural byte-diffs.** Three prompt outputs saved as golden files, to be used as the byte-equality oracle for every subsequent phase:

- `"Count of suppliers"` (count path)
- `"Show PO 2144 and its lines"` (child path)
- `"Which suppliers have open purchase orders?"` (join path)

Save the exact stdout to `docs/audit/golden/*.txt`.

**H. Probabilistic-behaviour map.** For every LLM-boundary behaviour — parser include-list, classifier module-set, synthesizer summary — record the *distribution* of outcomes across N runs (N ≥ 20). Note which behaviours are deterministic and which are not. This map is the input to Phase 2's correctness work for probabilistic bugs; without it, "the parser sometimes flips" stays a rumour.

**7.3.4 The audit is not a wishlist.**

The audit is a factual document. It says what *is*, not what *should be*. Fixes go in Phase 2 (correctness) or Phase 3 (consistency).

### 7.4 Tasks

| # | Task | Output |
|---|---|---|
| 1.1 | Untrack `personas.yaml`, gitignore it | commit |
| 1.2 | Move `display_formatters.py` to `src/spire/rendering/` | commit |
| 1.3 | Move PDFs and XLSX out of the source tree | commit |
| 1.4 | Remove scratch files from the repo | commit |
| 1.5 | Write the registry drift map | `docs/audit/phase-1-audit.md` §A |
| 1.6 | Write the bug inventory (including S1, S4, and the `qa_testcases` corpus drift) | `docs/audit/phase-1-audit.md` §B |
| 1.7 | Write the dead code inventory | `docs/audit/phase-1-audit.md` §C |
| 1.8 | Write the inconsistency inventory | `docs/audit/phase-1-audit.md` §D |
| 1.9 | **Write the in-flight work inventory** | `docs/audit/phase-1-audit.md` §E |
| 1.10 | Capture baseline metrics | `docs/audit/phase-1-audit.md` §F |
| 1.11 | Save three golden outputs | `docs/audit/golden/*.txt` |
| 1.12 | **Write the probabilistic-behaviour map (N≥20 runs per behaviour)** | `docs/audit/phase-1-audit.md` §H |

### 7.5 Acceptance criteria

- `personas.yaml` is untracked; credentials rotated.
- The audit document exists and is complete, including the in-flight work inventory and the probabilistic-behaviour map.
- The golden outputs are saved and reproducible: running the same three prompts today produces byte-identical output.
- All tests still pass (the mechanical moves shouldn't break anything).
- No code changes beyond the mechanical hygiene.

### 7.6 Rollback

Revert the merge commit. Restore the moved files. If credentials were rotated, no rollback — the rotation stands.

### 7.7 Phase 1 Status

**Current status:** ⬜ Not started

**Evidence:**

*(to be filled in after Phase 1 completes)*

**Deviations from plan:**

---

## 8. Phase 2 — Correctness

### 8.1 Objective

Fix every bug the audit found. Add a regression test for each. Do not consolidate or restructure; just make the code correct.

**v3.2 note.** Phase 2's thesis is expanded to include correctness under partial failure. See §8.3.7. The pipeline must not discard successful work when a later step fails.

### 8.2 Why here

Buggy code should not be consolidated (Phase 3) or moved (Phase 4). Consolidation duplicates bugs. Restructuring hides bugs in a wave of imports.

The audit (Phase 1) produced a bug list. Phase 2 turns that list into zero.

### 8.3 Design

**8.3.1 Prioritize by severity.**

Not every bug is equally important. Sort the audit's bug list into:

- **Wrong-data bugs** — the answer says something false. Fix first.
- **Crash bugs** — the pipeline errors out. Fix second.
- **Missing-capability bugs** — the prompt refuses when it shouldn't. Fix third.
- **Cosmetic bugs** — the answer is right but ugly. Fix last.

**8.3.2 Deterministic bugs vs probabilistic bugs.**

The audit produces two kinds of bugs. They need different treatment.

**Deterministic bugs** fire every time. They fit "one bug, one branch, one test" cleanly. The regression test is a single-run assertion: given the input, the output must be correct.

**Probabilistic bugs** fire some fraction of the time. The S1 include flip fired roughly 9 times in 20. The classifier module-set flips fire less often. A single-run test passes most of the time even when the bug is live. **A probabilistic bug needs N-run evidence, not a single pass.**

For a probabilistic bug:

- The regression test runs the input N times (N ≥ 20) and asserts a distribution — for example, "at least 19 of 20 runs produce the correct output."
- The test is marked `@pytest.mark.slow` (or similar) because N× cost matters.
- The fix is not "make the failing case pass" but "make the distribution converge to deterministic." If the flip is driven by an LLM, the fix is usually to move the decision out of the LLM, not to add a hedge around it.
- The test *does not* assert byte-equality across runs (that's a different property); it asserts that the *correct outcome dominates*.

The template for N-run evidence is in Appendix B.2.

**8.3.3 One bug, one branch, one test.**

Do not bundle bugs. Each fix:

- Gets its own small branch (or its own commit on the phase-2 branch).
- Gets its own regression test.
- Gets verified with the exact prompt that exposed it.

**8.3.4 The regression test proves the fix stays fixed.**

The test asserts the *correct* behaviour, not just the absence of the bug. If the bug was "supplier sites returns addresses," the test asserts that supplier sites returns sites *and* that the entity name in the answer is Site, not Address.

**8.3.5 No behaviour changes beyond the fixes.**

Phase 2 is not the place for cleanup, refactoring, or style changes. The only changes are the bugs. (The one exception is §8.3.7, which is a capability change explicitly scoped into Phase 2 by v3.2.)

**8.3.6 The byte-diff oracle applies.**

Before Phase 2, run the three golden prompts and save the output. After each bug fix, re-run the three golden prompts and confirm the output for those three is unchanged (unless the bug *was* in one of those prompts' output, in which case update the golden file and note the change).

**8.3.7 Partial results and explicit gaps.**

**The problem.** `execute_plan` iterates steps and any exception fails the whole plan. A five-step plan that fails at step four returns nothing. The user asking "suppliers in the US with open POs and no recent invoices" gets an error instead of "here are 12 suppliers with open POs; I couldn't check their invoices."

This is a **correctness** concern, not a UX detail. The pipeline is incorrect if it discards successful work when a later step fails. Phase 2's thesis is expanded from "fix bugs" to "fix bugs and behave correctly under partial failure."

**Design.**

The executor returns a structured result instead of raising:

```python
{
    "completed_steps": [{"step": 1, "output": ...}, {"step": 2, "output": ...}],
    "failed_steps":    [{"step": 4, "error": "...", "error_kind": "timeout"}],
    "outputs":         {...},   # everything that succeeded, keyed by step name
    "coverage":        "partial"  # or "complete"
}
```

The synthesizer receives `coverage` and `failed_steps` and narrates the gap:

> "I found 12 suppliers with open purchase orders, but I couldn't check their invoices (the invoice service timed out). Here's what I have."

The renderer displays the gap as a first-class section, not as an error banner.

**Rules.**

- A step failure does not abort the plan unless a later step depends on it.
- Independent steps continue.
- `coverage` is `"complete"` only if every step succeeded.
- The synthesizer must mention the gap. It must not silently omit it.
- A plan where every step succeeds is byte-identical to pre-§8.3.7 output.

**Acceptance.**

- A plan with an induced failure in one step returns the successful steps' outputs.
- The synthesizer mentions the gap.
- `coverage` is `"partial"`.
- No answer changes for plans where all steps succeed.
- The byte-diff of the three golden prompts is unchanged.

### 8.4 Tasks

| # | Task | Output |
|---|---|---|
| 2.1 | Triage the audit's bug list by severity, and separate deterministic from probabilistic | revised `docs/audit/phase-1-audit.md` §B |
| 2.2 | Fix wrong-data bugs (deterministic) | one commit per bug + regression test |
| 2.3 | Fix wrong-data bugs (probabilistic) | one commit per bug + N-run regression test |
| 2.4 | Fix crash bugs | one commit per bug + regression test |
| 2.5 | Fix missing-capability bugs | one commit per bug + regression test |
| 2.6 | Fix corpus-drift bugs (e.g. `qa_testcases.json`) | regenerate the affected corpus; review; commit |
| 2.7 | Fix cosmetic bugs | one commit per bug |
| 2.8 | Re-run the full prompt suite | updated pass count |
| 2.9 | Update the golden files if any of the three prompts changed | refreshed golden outputs |
| 2.10 | Verify every fix's regression test fails without the fix | evidence in PR |
| 2.11 | **Implement partial execution + gap reporting in `execute_plan`** | commit + regression test |
| 2.12 | **Induced-failure regression test (one step fails, others succeed)** | test |
| 2.13 | **Synthesizer gap-narration test** | test |

### 8.5 Acceptance criteria

- Every bug in the audit's list is either fixed with a regression test or deferred with a documented reason.
- The full prompt suite pass count has improved or stayed the same.
- No new failures.
- Every fix's regression test fails without the fix.
- Every probabilistic bug has an N-run regression test that demonstrates convergence.
- Partial-failure behaviour is verified: successful steps are returned, gaps are reported, and the synthesizer narrates them.

### 8.6 Rollback

Phase 2 is composed of independent bug fixes. Each can be reverted individually. The branch as a whole can be reverted if the phase is abandoned.

### 8.7 Phase 2 Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

## 9. Phase 3 — Consistency

### 9.1 Objective

Make the KG the single source of truth. Generate the parser prompt, the classifier menu, the tool dispatch, and the tripwire counts from it. The result: adding a filter becomes one KG row, not five code changes.

### 9.2 Why here

This is the biggest single lever in the plan. Almost every bug the audit finds will trace back to a drift between two parallel registries. Fixing the drift at the source eliminates the *class* of bug, not just individual instances.

Consistency must come *after* correctness because consolidating a buggy registry just produces a buggier one. It must come *before* structure because structure needs to know what belongs where, and consistency makes the code's true architecture visible.

### 9.3 Design

Phase 3 is split into seven sub-phases. Each has its own branch and its own PR.

#### 9.3.1 Phase 3a — Prompt coverage validation

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

#### 9.3.2 Phase 3b — Prompt generation from KG

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

#### 9.3.3 Phase 3c — Generic executor (prototype)

**Objective.** Implement `execute_operation` for one entity-level fetch (`search_suppliers`). Prove the pattern works.

**Design.**

- New file `src/spire/mcp_server/tools/execute.py`.
- Reads the KG spec, calls the pod, projects fields, applies client-side filters, returns a `ToolResult`.
- Registered alongside the 34 existing tools.
- Byte-equality test against the legacy tool.

**Acceptance.** The prototype's output matches the legacy tool's output for several argument combinations.

#### 9.3.4 Phase 3d — Generic executor (full)

**Objective.** Extend `execute_operation` to every entity-level fetch, every edge traversal, and every child fetch.

**Design.**

- `kind=entity_level`: direct fetch.
- `kind=edge_traversal`: single parent-id child call.
- `kind=child`: direct child call.
- All variations handled by one dispatch reading the KG.

**Scope.** 8 entities × ~20 filters + 16 edges + all child fetches.

**THE RISK — per-endpoint quirks resist generalization.**

This is the phase where the plan's biggest risk lives. Individual legacy tools carry hard-won, non-obvious quirks baked into their code:

- The composite-`q=` silent-zero (a filter that composes two server clauses returns HTTP 200 with an empty result).
- `fields=` breaking on `/standardReceipts` (500s even with valid field names).
- `SupplierNumber` 400ing on `/purchaseOrders` (the endpoint doesn't expose it).
- The over-fetch-200-then-client-filter pattern (used because a single server clause is unreliable but a composite is worse).
- Per-endpoint ordering requirements (`orderBy=StandardReceiptId` on `/standardReceipts` because the endpoint has no default order).

These are documented in `docs/spire_fusion_endpoints_reference.md` precisely because they are *not* derivable from the KG schema. A generic executor has to reproduce every one of these per-endpoint idiosyncrasies from declarative spec — and the ones it misses won't fail loudly; they'll silent-zero or 500 or return wrong counts.

**Byte-equality on sampled combinations is not sufficient evidence.** The quirks bite on the combinations nobody tested. A generic executor that passes the golden prompts and the corpora can still ship a silent wrong answer on a filter pair that nobody exercised.

**The design response — declarative `quirks`.**

The spec format must have a first-class `quirks` block so that each per-endpoint idiosyncrasy is declarative and testable.

```yaml
quirks:
  # Example: composite q= silently zeroes on this endpoint.
  - kind: no_composite_q
    description: |
      ANDing two clauses in a single q= returns HTTP 200 with an empty
      result set on this endpoint, even when each clause alone returns
      thousands and the intersection is non-empty. Send one clause
      server-side and the rest client-side.

  # Example: fields= 500s on this endpoint even with valid names.
  - kind: no_fields_projection
    description: |
      Passing fields= to this endpoint returns HTTP 500 regardless of
      whether the field names are valid. Fetch full rows and project
      client-side.

  # Example: this endpoint has no default order; paginating without
  # an explicit orderBy produces a different sample each call.
  - kind: requires_order_by
    field: StandardReceiptId
    description: |
      This collection has no default ordering. Paginating via offset
      without an explicit orderBy returns overlapping or missing rows
      across calls. The PK is the deterministic key; note that
      ReceiptNumber is NOT unique on this pod.

  # Example: this endpoint's body does not echo the parent id.
  - kind: parent_id_not_in_body
    description: |
      Child rows do not carry the parent id in the body; the join key is
      the URL path. The executor must stamp the parent id onto each row
      when a following step needs to iterate on it.
```

The generic executor reads the `quirks` block and behaves accordingly. The acceptance criterion becomes: **for every quirk kind the executor knows about, there is a per-quirk test that exercises it**. Not "for each of the 24 tools, byte-equality on sampled combinations."

**What the per-quirk tests look like:**

- `no_composite_q`: assert that the executor sends exactly one clause via q= when two filters are requested, and applies the second client-side.
- `no_fields_projection`: assert that the executor does not send fields= on this endpoint and that the returned items carry the full row.
- `requires_order_by`: assert that the executor sends orderBy with the specified field on every page.
- `parent_id_not_in_body`: assert that the executor stamps the parent id onto each child row.

Each quirk kind is tested once, not once per endpoint. The `quirks` block in each endpoint's spec says *which* quirks apply; the executor's test suite says *how* each quirk kind is honoured.

**Scope.** 8 entities × ~20 filters + 16 edges + all child fetches.

**Acceptance.**

- Every operation byte-equals its legacy counterpart **on the tested argument combinations**.
- Every quirk kind the endpoint declares has a per-quirk test in the executor's test suite.
- The endpoints reference is the checklist: every quirk documented there must have a corresponding declarative quirk and a corresponding test.
- `--validate` on all corpora passes.
- Full prompt suite runs clean.

#### 9.3.5 Phase 3e — Delete legacy tools

**Objective.** Delete the 24 fetch-only tool files. Keep the 7 semantic tools (aggregations, comparisons, lifecycle).

**Design.**

- Delete 24 files.
- Remove their `@mcp.tool()` wrappers.
- Update `planner.py` to emit `execute_operation` instead of tool names.
- Update KG: `kg_entity_tool.mcp_tool_name` becomes `'execute_operation'`.
- Delete corresponding test files.
- Regenerate corpora with `--generate`, review, commit.

**Files to delete:**

```
addresses.py  buyer.py  customer_account_by_name.py  customer_transactions.py
invoices.py  purchase_order_by_id.py  purchase_order_distributions.py
purchase_order_lines.py  purchase_order_schedules.py  purchase_orders.py
receivables_credit_memos.py  receivables_invoice_by_id.py
receivables_invoice_lines.py  receivables_invoice_tax_lines.py
receivables_invoice_transaction_dff.py  standard_receipts.py
supplier_classifications.py  supplier_contacts.py  supplier_sites.py
suppliers.py  suppliers_by_country.py
account_credit_memos.py  account_receipt_applications.py  account_receipts.py
```

That is **24 files**, keeping these 7 semantic tools:

```
aggregate_invoices.py
aggregate_purchase_orders.py
aggregate_standard_receipts_by_method.py
compare_orders_to_invoices.py
po_lifecycle.py
rank_customer_accounts_by_exposure.py
rank_invoices_by_amount.py
```

Plus helpers: `pagination.py`, `tool_result.py`. Total `mcp_server/tools/`: **9 files + execute.py = 10.**

**THE ACCEPTANCE BAR — stronger than byte-equality.**

The plan does not ship Phase 3e until the acceptance bar is provably met. This means:

1. **Every per-endpoint quirk is enumerated.** The endpoints reference (`docs/spire_fusion_endpoints_reference.md`) documents the quirks each legacy tool encodes. Extract them into the `quirks` block for each endpoint's spec.

2. **Every quirk has a per-quirk test.** For each quirk kind (`no_composite_q`, `no_fields_projection`, `requires_order_by`, `parent_id_not_in_body`, etc.), there is a test in the executor's suite that verifies the executor honours it.

3. **For each of the 24 tools being deleted, byte-equality on *at least three argument combinations*.** The combinations must include at least one that exercises the endpoint's declared quirks. Not just the happy path.

4. **A negative test for each tool.** For the tool being deleted, construct an argument combination that the legacy tool handled *unusually* — a composite filter, a specific `fields=` request, an ordering-sensitive fetch — and confirm the generic executor produces the same result.

5. **A documented diff.** The PR includes a table showing, per tool: its quirks, the tests that verify each quirk, and the diff between its legacy output and the generic executor's output on multiple combinations.

**What this bar is designed to prevent:**

The failure mode is: the generic executor passes the golden prompts and the corpora, ships, and then silent-wrong-answers on a combination nobody put in a test. This is exactly the failure SPIRE exists to prevent. The per-quirk test bar makes that failure impossible — if the quirk is declared, it's tested; if it's not declared, the tool doesn't get deleted.

**A note on the risk.** The reviewer of an earlier draft of this plan observed: *"tool code is where the ERP's ugliness is absorbed, and ugliness resists generalization."* The response is not to refuse consolidation, but to make the ugliness **declarative** so the consolidation is auditable. `quirks` is the mechanism.

**Acceptance.**

- Only semantic tools + `execute_operation` are registered.
- All tests pass.
- Full prompt suite runs with no regression.
- Corpora regenerated (`--generate`), reviewed, committed.
- **Per-quirk test suite passes.**
- **The tool-by-tool diff table is in the PR.**

#### 9.3.6 Phase 3f — Deterministic classifier

**Objective.** Replace the LLM classifier with a gazetteer lookup for prompts whose tokens match entity synonyms. Keep the LLM classifier as a fallback for prompts with no synonym match.

**Why here.** The classifier's job is to match prompt tokens against entity synonyms. That is a gazetteer lookup, not a classification problem. The classifier menu (generated in Phase 3b) already contains entity names and their synonyms. The gazetteer reads from the same source. This is Phase 3's thesis applied to routing: replace an LLM call with a deterministic KG lookup.

This is a **Tier 1 item** from the initial architecture review. It removes one LLM call from ~80% of requests. The original review called it out as the second-biggest risk after the per-entity maintenance ceremony.

**Design.**

```python
def classify_modules(prompt: str, menu: KGMenu) -> list[str]:
    tokens = set(re.findall(r"[a-z]+", prompt.lower()))
    modules = set()
    for term, entity in menu.entity_synonyms.items():
        if term in tokens:
            entity_module = menu.entity_modules.get(entity)
            if entity_module:
                modules.add(entity_module)
    return list(modules)
```

The LLM classifier is called only when the gazetteer returns an empty set. The fallback is logged with `[classifier] fallback=llm` so its rate is visible.

**Target: 1 LLM call per request for most prompts.**

After Phase 3f, the pipeline is:

```
gazetteer (code)  →  parse (LLM)  →  plan (code)  →  execute (code)  →  synthesize (local 90% / LLM 10%)
```

For the majority of prompts, the classify call disappears entirely. Combined with Phase 6c (intent cache) and Phase 6d (plan cache), the LLM-call count for repeated or common prompts approaches one.

**Acceptance.**

- Gazetteer handles ≥80% of prompts in the corpora without LLM fallback.
- Zero new failures in `--validate`.
- One fewer LLM call per request for gazetteer-handled prompts.
- Byte-identical answers for prompts where the gazetteer and LLM agree.
- The fallback rate is reported in the phase's evidence block.
- The classifier-teaching and parser-teaching drift (S-class bug) is structurally eliminated: both read from the same generated menu.

**Rollback.** Revert to LLM classifier by removing the gazetteer dispatch; the LLM path remains present as fallback.

#### 9.3.7 Phase 3g — KG versioning

**Objective.** The KG carries a version stamp. The menu exposes it. Caches use it as an invalidation key.

**Why here.** Phase 6's caches (tool cache 6a, intent cache 6c, plan cache 6d) need an invalidation key. Without a KG version, a cache can serve stale intents or plans after a KG rebuild. This is infrastructure that Phase 6 depends on, and it belongs in Phase 3 because it is about the KG's integrity as the single source of truth.

**Design.**

- A `kg_version` table (or a row in an existing metadata table) holding a monotonic version or a content hash.
- `load_kg_menu()` returns `(menu, kg_version)`.
- The KG rebuild increments the version.
- Cache keys include the version. Phase 6c and 6d reference this.

**Acceptance.**

- KG version is present and stable across reads.
- KG rebuild changes the version.
- `load_kg_menu()` returns the version alongside the menu.
- No answer changes.
- Cache invalidation on KG rebuild is testable.

**Rollback.** Remove the `kg_version` table and the tuple return from `load_kg_menu()`. Phase 6 caches must then be disabled or keyed on a coarser signal.

### 9.4 Tasks

| # | Task | Branch |
|---|---|---|
| 3.1 | Prompt coverage validation | `phase-3a-prompt-coverage` |
| 3.2 | Rewrite the prompt generator | `phase-3b-prompt-generation` |
| 3.3 | Migrate to generated prompts | same branch |
| 3.4 | Implement `execute_operation` prototype | `phase-3c-generic-executor-prototype` |
| 3.5 | **Define the `quirks` spec block and the per-quirk tests** | `phase-3d-generic-executor-entity` |
| 3.6 | Extend to all entity-level fetches | same |
| 3.7 | Extend to edge traversals and children | `phase-3d-generic-executor-edges` |
| 3.8 | **Enumerate every legacy tool's quirks into its spec** | `phase-3e-delete-legacy-tools` |
| 3.9 | Delete legacy tool files | same |
| 3.10 | Regenerate corpora | same |
| 3.11 | **Produce the tool-by-tool diff table** | same |
| 3.12 | **Implement gazetteer `classify_modules`** | `phase-3f-deterministic-classifier` |
| 3.13 | **Wire LLM fallback for empty-gazetteer prompts** | same |
| 3.14 | **Measure gazetteer coverage on all corpora** | same |
| 3.15 | **Add `kg_version` to the KG schema** | `phase-3g-kg-versioning` |
| 3.16 | **Expose version from `load_kg_menu()`** | same |
| 3.17 | **Document cache-key usage for Phase 6** | same |

### 9.5 Acceptance criteria

- The KG is the single source of truth for: entity list, field list, filter definitions, edge definitions, tool dispatch, classifier menu, parser prompt.
- `--check` on the prompt generator returns 0.
- Adding a filter is one KG row.
- Adding a field is one KG row.
- The full test suite passes.
- The full prompt suite passes.
- Tool count is 12 (1 generic + 11 semantic), down from 34.
- **Every endpoint quirk is declared in its spec; every quirk kind has a test; the tool-by-tool diff table is documented.**
- **The gazetteer handles ≥80% of prompts without LLM fallback.**
- **The KG version is exposed and caches can key on it.**

### 9.6 Rollback

Each sub-phase has its own rollback. Phase 3e (deleting legacy tools) keeps the deleted files in a `legacy/` directory for one sprint. If any per-quirk test fails in production data, the legacy tool can be restored. Phase 3f falls back to the LLM classifier by removing the gazetteer dispatch. Phase 3g removes the `kg_version` table; caches must then be disabled or re-keyed.

### 9.7 Phase 3 Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

## 10. Phase 4 — Structure

### 10.1 Objective

Reorganize the source tree and the code so the layout reflects the actual architecture. Split tests by concern. Move entry points into the package. Update documented commands to match.

### 10.2 Why here

Consistency work (Phase 3) made the code's true shape visible. Before that, the architecture was obscured by drift. After it, the boundaries are obvious: the KG layer, the pipeline stages, the rendering layer, the operators, the entry points.

Structure must come *after* consistency because you can't decide where a module belongs until you know what it is. It must come *before* observability because you want to instrument stable code, not code that's about to move.

### 10.3 Design

#### 10.3.1 Phase 4a — Source-tree reorganization

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
│   ├── api/                      ← new (Phase 4d): FastAPI server
│   │   ├── __init__.py
│   │   ├── server.py
│   │   └── models.py
│   ├── ui/                       ← new (Phase 4d): Streamlit app
│   │   ├── __init__.py
│   │   └── app.py
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
spire-api = "spire.api.server:main"
spire-ui = "spire.ui.app:main"
```

**The documented-command problem.**

Moving entry points into `src/spire/cli/` and making them console scripts will break every `python scripts/promptkit.py ...` invocation in the repo's documentation. This is not hypothetical — the codebase has extensive documentation of exact commands:

- `README.md`
- `how-to-run.md`
- `docs/SPIRE_SESSION_HANDOFF.md`
- `docs/four_bugs.md`
- `docs/spire_findings_11-Sep-2026.md`
- Every session log entry
- Every handoff document

**The fix has two parts, both required:**

1. **Thin forwarding shims.** Keep `scripts/run_graph.py`, `scripts/promptkit.py`, etc. as small forwarding files that import and call the new entry point. They print a deprecation warning to stderr and forward. One release cycle later, they can be deleted. This preserves muscle memory and prevents the docs from rotting on day one.

   ```python
   # scripts/promptkit.py
   import sys
   from spire.cli.promptkit import main

   print(
       "[deprecation] scripts/promptkit.py has moved to "
       "spire.cli.promptkit. Run `spire-promptkit` instead.",
       file=sys.stderr,
   )
   sys.exit(main())
   ```

2. **A documentation update task.** Phase 4a includes a task to grep every doc for `python scripts/*.py` and `scripts/*.sh` invocations and either update them to the new form or ensure the shim covers them. The grep must be exhaustive; a partial update leaves half the docs pointing at old paths.

The shims are a temporary measure; the doc update is the permanent fix. Both ship in Phase 4a.

#### 10.3.2 Phase 4b — Test suite split

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

#### 10.3.3 Phase 4c — Module boundaries

Where Phase 3 revealed that a module bundles multiple concerns, split it. Where it revealed that a concern is scattered, consolidate it.

Examples (actual splits depend on Phase 3's findings):

- If `synthesizer.py` still holds multiple concerns despite the earlier split, finish the split.
- If `planner.py` has business logic that belongs in a builder, move it.
- If the display layer and the render layer are tangled, separate them.

This is the smallest sub-phase and the most judgement-dependent. It's also the one where doing it *after* consistency matters most — before Phase 3, you'd split things along the wrong seams.

#### 10.3.4 Phase 4a task — `docs/architecture/`

Create a top-level `docs/architecture/` directory for the "how does this fit together" documents. Move `spire_architecture.md` and related overview documents there. Add a README explaining what belongs there. This separates "design of X" documents from "overview of the system" documents, so a new contributor knows what to read first.

#### 10.3.5 Phase 4d — UI and API layer

**Objective.** Give SPIRE a minimal browser interface and the HTTP backend that serves it. One input. One output. One page. No multi-set, no batch, no multi-turn.

**Why here.** The API and UI are clients of the pipeline, so the pipeline must be stable first (Phase 3). They are packaging artefacts — new packages, new console scripts — which is Phase 4 territory. They must be in place before Phase 5 so their spans and metrics are instrumented from day one, and before Phase 6 so caching and parallelism can be observed end-to-end. They change nothing in the pipeline. No answer changes.

**Scope.**

- `src/spire/api/` — FastAPI server. Two endpoints. No state. No auth.
- `src/spire/ui/` — Streamlit app. One page. One prompt. One answer.
- Console scripts `spire-api` (default `:8000`) and `spire-ui` (default `:8501`).

**Non-goals.** Streaming, multi-turn history, authentication, file upload, batch or multi-set execution, custom CSS or JS, persistence, rate limiting, caching, metrics export. All are deferred to their respective phases or to §4.6 non-goals.

**Backend design.** FastAPI + Uvicorn + Pydantic. Async-native; the pipeline is called via `await`; any sync code runs inside `run_in_threadpool`.

Two endpoints.

- `GET /status` — liveness and version banner.
  - 200: `{"ok": true, "service": "spire-api", "version": "0.1.0", "started_at": "...", "uptime_s": 3600, "kg_version": "abc123", "pipeline_ready": true}`
  - 503: `{"ok": false, "service": "spire-api", "error": "pipeline not initialised", "pipeline_ready": false}`

- `POST /prompt` — the prompt endpoint. Request: `{"prompt": "...", "session_id": "optional-client-uuid"}`. `session_id` is optional and used only for log grouping; SPIRE is single-turn.

Every response uses the same top-level envelope:

- `request_id` — opaque identifier
- `kind` — discriminator: `text` · `table` · `refusal` · `partial` · `error`
- `answer` — shape varies by `kind`
- `metadata` — always present

`answer` by `kind`:

- `text` — `{"text": "...", "records": [], "truncated": false, "truncation_note": null}`
- `table` — same, with `records` populated
- `refusal` — `{"text": null, "refusal": {"reason": "...", "solution": "...", "example": "..."}}`
- `partial` — text + records + `coverage: "partial"` + `failed_steps: [...]` (see §8.3.7)
- `error` — `{"text": "...", "error": {"stage": "...", "message": "...", "retryable": true}}`

`metadata` — `latency_ms`, `llm_calls`, `tokens_in`, `tokens_out`, `kg_version`, and `stages` (an array of `{name, ms}` entries: classify, parse, plan, execute, synthesize).

HTTP status codes reflect reality: `200` for `kind ∈ {text, table, refusal, partial}`; `422` for malformed request; `500` for `kind = "error"`; `503` when `pipeline_ready` is false.

Configuration via environment: `SPIRE_API_HOST` (default `0.0.0.0`), `SPIRE_API_PORT` (default `8000`), `SPIRE_UI_ORIGIN` (CORS allowlist; default `http://localhost:8501`), `SPIRE_KG_VERSION` (read from KG). OpenAPI docs at `/docs` for debugging.

**Frontend design.** Streamlit only. No custom CSS. No JS. One page, three zones.

- Zone 1 — header: title "SPIRE" and a connection indicator that calls `/status` on load.
- Zone 2 — input: `st.text_input("Ask a question")` and `st.button("Submit")`; Enter also submits.
- Zone 3 — answer: renders one of the five `kind` values. Text via `st.markdown`. Records via `st.dataframe`. Refusal via three styled blocks (warning/info/code). Partial via `st.warning` + records. Error via `st.error`. Truncation warning above records. Metadata in a collapsed `st.expander("Metadata")`.

States the UI handles: idle (empty), loading (`st.spinner`), text, table, refusal, partial, error, disconnected (`/status` fails → top banner).

No history. No settings. No persistence. Configuration via `SPIRE_API_URL` (default `http://localhost:8000`).

**Acceptance criteria.**

- `pip install -e .` installs `spire-api` and `spire-ui`.
- `spire-api` starts on `:8000` with `/status` and `/prompt`.
- `spire-ui` starts on `:8501` and reaches the API.
- All five `kind` values render correctly.
- Truncation warnings appear when `truncated = true`.
- Metadata expander shows the stage breakdown.
- Three golden prompts produce byte-identical answers via CLI, API, and UI.
- No answer changes.

**Rollback.** Delete `src/spire/api/` and `src/spire/ui/`; remove the two console scripts and the two tree entries. The CLI path (`scripts/run_graph.py`, `spire`) is untouched and continues to work.

**A note on future UI replacement.** The API is a plain JSON HTTP service. Streamlit is one client; React (or anything else) is another. When the UI is rewritten, the API does not change. This is why the API and the UI are separate packages and separate processes.


### 10.4 Tasks

| # | Task | Branch |
|---|---|---|
| 4.1 | Move `scripts/` → `src/spire/cli/` and `src/spire/ops/` | `phase-4a-source-tree` |
| 4.2 | Move `scripts/prompts/` → `prompts/` | same |
| 4.3 | Move runtime artifacts → `data/` | same |
| 4.4 | Move `test_tools/` → `tests/manual/` | same |
| 4.5 | Add console scripts to `pyproject.toml` | same |
| 4.6 | Move `archive/` probes out | same |
| 4.7 | **Add thin forwarding shims in `scripts/`** | same |
| 4.8 | **Grep-and-update every doc reference to `scripts/*.py` invocations** | same |
| 4.9 | Split `tests/` by component | `phase-4b-test-split` |
| 4.10 | Add `tests/conftest.py` auto-marker | same |
| 4.11 | Split bundled modules | `phase-4c-module-boundaries` |
| 4.12 | **Create `docs/architecture/` and move overview docs there** | `phase-4a-source-tree` |
| 4.13 | **Create `src/spire/api/`** — FastAPI app, models, `/status`, `/prompt` | `phase-4d-ui-api` |
| 4.14 | **Add `spire-api` console script** | same |
| 4.15 | **Create `src/spire/ui/`** — Streamlit app, one page | same |
| 4.16 | **Add `spire-ui` console script** | same |
| 4.17 | **Add API smoke tests (`tests/integration/api/`) and UI smoke tests (`tests/manual/ui/`)** | same |

### 10.5 Acceptance criteria

- `spire --prompt "Count of suppliers"` works from anywhere after `pip install -e .`.
- `python scripts/promptkit.py ...` still works (via shim) for one release.
- `pytest -q` passes with the same count as before.
- `pytest -q tests/unit/` runs fast (<30s).
- Three golden prompts still byte-identical.
- Every import that referenced a moved file is updated.
- **Every doc reference to a `scripts/*.py` command is either updated or covered by a shim.**
- **`spire-api` starts on `:8000` with `/status` and `/prompt`.**
- **`spire-ui` starts on `:8501` and reaches the API.**
- **All five `kind` values render correctly in the UI.**
- **Three golden prompts produce byte-identical answers via CLI, API, and UI.**
- **`docs/architecture/` exists with a README and the overview documents.**

### 10.6 Rollback

Each sub-phase reverts independently. The `src/spire/cli/` and `src/spire/ops/` moves are the largest single change; the rest is mechanical. The forwarding shims mean that even a full revert of the tree move leaves old commands working.

Phase 4d reverts by deleting `src/spire/api/` and `src/spire/ui/` and removing the two console scripts. The CLI path is untouched and continues to work.

### 10.7 Phase 4 Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

## 11. Phase 5 — Observability

### 11.1 Objective

Instrument every pipeline stage with OpenTelemetry spans. Replace the `--show-*` flag diagnostics with structured traces for production use.

### 11.2 Why here

Observability must come *after* structure because you want to instrument stable code — code that isn't about to move. It must come *before* performance because you can't prove a performance change helped without a baseline.

The `--show-*` flags remain for local development. OTel is for production: multiple requests, aggregated metrics, distributed traces.

### 11.3 Design

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

### 11.4 Tasks

| # | Task |
|---|---|
| 5.1 | Add `src/spire/observability/` |
| 5.2 | Wrap pipeline nodes in spans |
| 5.3 | Wrap executor steps in spans |
| 5.4 | Wrap LLM calls in spans with token attributes |
| 5.5 | Wrap tool invocations in spans |
| 5.6 | Configure exporter via env var |
| 5.7 | Document the trace shape |

### 11.5 Acceptance criteria

- One full request produces a trace with the expected span hierarchy.
- Attributes are present and correct.
- Overhead is under 1% of wall-clock.
- The `--show-*` flags still work.

### 11.6 Rollback

Remove the span wrappers. The observability module can stay as dead code or be deleted.

### 11.7 Phase 5 Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

## 12. Phase 6 — Performance

### 12.1 Objective

Reduce latency and cost without changing answers. Add caching, parallel execution, and concurrency handling.

### 12.2 Why here

Performance must come *after* observability because you need a baseline to prove the change helped. It must come *before* extensibility because you want the generator to produce endpoints into a fast, well-understood system, not a slow, drifting one.

### 12.3 Design

#### 12.3.1 Phase 6a — Tool-result cache

**Objective.** TTL cache around MCP tool calls.

**Design.** New `src/spire/mcp_server/tools/cache.py`. Keyed on `(tool_name, frozen_args)`. TTL 300s (configurable). Env flag `SPIRE_TOOL_CACHE_DISABLE=1` for testing.

Wrap `session.call_tool` in the executor.

**Constraint.** The cache must respect `truncated`. Cached results carry truncation metadata verbatim, and the synthesizer narrates it as the cache's own truncation.

**Acceptance.** Two concurrent identical requests → one pod fetch. No answer change.

#### 12.3.2 Phase 6b — Parallel execution

**Objective.** Replace sequential `for step in plan` with a dependency-aware parallel executor.

**Design.** Add `depends_on: list[str]` to `Step`. `plan_builders.py` sets it for each step (it already knows the `iterate_over.from_step` chain). The executor runs ready steps concurrently.

**Acceptance.** The anchor question drops from ~17s to under 5s. Byte-diff identical to sequential.

#### 12.3.3 Phase 6c — Intent cache

**Objective.** Implement the three-stage intent cache from `docs/cache_architecture.md`.

**Design.** New modules: `intent_cache.py`, `intent_cache_backends.py`, `intent_cache_verify.py`. The router consults the cache before classify+parse.

**Reference to prior work — the parser prompt cache.**

A parser prompt cache was implemented earlier (branch `feat/parser-prompt-cache`) and merged. Its lesson is directly relevant to Phase 6c:

- **Caching interacts with the model's thinking-step budget.** A cache hit can change the *reasoning path* the model takes, not just the timing. The cached prompt arrives in a different internal state than the fresh prompt would, and the model may skip a step it would otherwise have taken.
- **This was observed as a regression during the cache work** and fixed. Phase 6c must reference this lesson and include a test that verifies the intent cache does not silently change the model's reasoning path.
- The specific failure mode: a cached intent may be *structurally correct* but reflect a different internal reasoning than a fresh parse would. If the intent feeds a downstream decision (planner choice, filter shape), the difference can surface as a wrong answer three phases later.

Phase 6c's acceptance criteria must include: **for a sample of prompts, the cache hit and the cache miss produce byte-identical Intents.** If they don't, the difference must be investigated before shipping the cache.

**Dependency on Phase 3g.** Cache keys include the KG version. On KG rebuild, the version changes and the cache invalidates.

**Acceptance.** Ten repeats of one prompt → one LLM parse call. Zero new failures in `--validate`. Cache invalidates on KG rebuild. Cache hits and misses produce identical Intents on the sample.

#### 12.3.4 Phase 6d — Plan cache

**Objective.** Cache the planner's output keyed on `(intent_hash, kg_version)`.

**Why here.** Sibling of the tool cache (6a) and intent cache (6c). The planner is deterministic, so the plan for a given intent and KG version is stable. Caching it removes a planner invocation from repeated identical requests.

**Design.**

- New `src/spire/planner/cache.py`.
- Key: `hash(intent, kg_version)`.
- Value: `Plan`.
- TTL: 3600s (configurable).
- Env flag: `SPIRE_PLAN_CACHE_DISABLE=1`.
- Depends on Phase 3g (KG version) and Phase 6c (intent cache).

**Acceptance.**

- Two identical Intents with the same KG version → one planner invocation.
- Cache hit and miss produce byte-identical Plans.
- Cache invalidates on KG version change.
- No answer changes.

**Rollback.** Delete `planner/cache.py` and remove the cache lookup from the planner. The planner falls back to computing every plan.

#### 12.3.5 Phase 6e — Concurrency and back-pressure

**Objective.** Handle concurrent requests without saturating the LLM or the pod.

**Why here.** Performance must handle concurrency, not just latency. The current implementation has one `_persona` and one `FusionClient` per tool call, no connection pooling, no rate limiting, and no queue. With 10 concurrent users, the LLM quota and the pod saturate.

**Design.**

- **Connection pooling** for the Fusion client: a shared pool with request-level isolation.
- **Rate limiting** on LLM calls: a token bucket or semaphore, so 100 prompts don't all queue on the LLM.
- **A bounded queue** for incoming requests with a clear rejection path.
- **Back-pressure signal** to the caller when the queue is full.

**Acceptance.**

- 10 concurrent identical requests → pooled client, no connection exhaustion.
- LLM calls are rate-limited; no thundering herd.
- Queue overflow returns a clear error, not a hang.
- No answer changes.

**Rollback.** Remove the pool, the rate limiter, and the queue. The executor falls back to one client per tool call.

### 12.4 Tasks

| # | Task | Branch |
|---|---|---|
| 6.1 | Implement tool-result cache | `phase-6a-tool-cache` |
| 6.2 | Add `depends_on` to plan steps | `phase-6b-parallel` |
| 6.3 | Implement parallel executor | same |
| 6.4 | Implement three-stage intent cache | `phase-6c-intent-cache` |
| 6.5 | **Test cache-hit vs cache-miss Intent identity** | same |
| 6.6 | Verify no byte-diff changes | same |
| 6.7 | **Implement plan cache** | `phase-6d-plan-cache` |
| 6.8 | **Test cache-hit vs cache-miss Plan identity** | same |
| 6.9 | **Pool the Fusion client** | `phase-6e-concurrency` |
| 6.10 | **Rate-limit LLM calls** | same |
| 6.11 | **Bounded queue + rejection path** | same |

### 12.5 Acceptance criteria

- Anchor question latency drops measurably.
- All answers byte-identical to pre-Phase-6 output.
- Cache respects truncation.
- **Cache hit and cache miss produce identical Intents on the sample.**
- **Cache hit and cache miss produce identical Plans on the sample.**
- **10 concurrent requests are handled without connection exhaustion or LLM thundering herd.**
- All tests pass.

### 12.6 Rollback

Each sub-phase reverts independently. The caches are disableable by env flag. The pool, rate limiter, and queue are removable individually.

### 12.7 Phase 6 Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

## 13. Phase 7 — Extensibility

### 13.1 Objective

Turn the accumulated machinery (KG as source of truth, generic dispatch, generated prompts) into a single command a developer can run to add a new endpoint.

### 13.2 Why last

Extensibility is the *output* of doing everything else well. It needs:

- **Correctness** — don't generate specs for buggy endpoints.
- **Consistency** — generators read from a single source of truth.
- **Structure** — generators write into a settled tree.
- **Observability** — new endpoints should be observable from day one.
- **Performance** — new endpoints should be fast without extra work.

Doing extensibility earlier would build a generator over unstable ground. Every later phase would invalidate it.

### 13.3 Design

Phase 7 is split into four sub-phases.

#### 13.3.1 Phase 7a — Endpoint spec format

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

quirks:                              # see Phase 3d
  - kind: parent_id_not_in_body
    description: |
      Child rows do not carry the parent id in the body; the join key is
      the URL path.

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
- Every `quirks[].kind` is a known quirk kind.
- No name collision (unless `--update`).
- Referenced vocab kinds exist.

**Acceptance.** A real existing endpoint (`supplier_sites`) can be spec'd and validated.

#### 13.3.2 Phase 7b — `spire add-endpoint` generator

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
8. Emit a per-quirk test if the spec declares quirks the endpoint doesn't already have coverage for.
9. Print a diff summary.

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

#### 13.3.3 Phase 7c — `spire add-module` generator

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

#### 13.3.4 Phase 7d — Documentation + walkthrough

**Objective.** Write the developer-facing docs that make Phase 7a–7c usable.

**Deliverables.**

- `docs/extending/adding-an-endpoint.md`
- `docs/extending/adding-a-module.md`
- `docs/extending/adding-a-field-or-filter.md`
- `docs/extending/spec-reference.md`
- `docs/extending/troubleshooting.md`
- A worked walkthrough showing the 15-minute flow.

**Acceptance.** A developer who has never seen SPIRE can add an endpoint in 30 minutes following the docs. A tripwire test asserts the walkthrough's commands still work.

### 13.4 Tasks

| # | Task | Branch |
|---|---|---|
| 7.1 | Define the endpoint spec format + validator (including `quirks`) | `phase-7a-spec-format` |
| 7.2 | Implement `spire add-endpoint` | `phase-7b-add-endpoint` |
| 7.3 | Implement `spire add-module` | `phase-7c-add-module` |
| 7.4 | Write the extensibility docs | `phase-7d-extensibility-docs` |
| 7.5 | Record the 15-minute walkthrough | same |

### 13.5 Acceptance criteria

- Adding a new endpoint touches ≤2 files (the spec + a test stub).
- Adding a filter is one line in the spec.
- Adding a field is one line in the spec.
- Adding a module is one YAML file plus endpoints.
- The walkthrough works from a fresh clone.

### 13.6 Rollback

Each sub-phase reverts independently. The generator can be bypassed by hand-editing the KG (the old way still works).

### 13.7 Phase 7 Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

# Part III — Tracking

## 14. Phase completion checklist

Before merging any sub-phase's PR, run this checklist. Every box must be ticked.

### 14.1 Tests

- [ ] `pytest -q` → all tests pass.
- [ ] `pytest -q --collect-only | tail -1` → new test count recorded.
- [ ] Full prompt suite runs with no new failures.
- [ ] For probabilistic-bug fixes: N-run evidence collected (see Appendix B.2).
- [ ] For Phase 3e: per-quirk tests pass.
- [ ] For Phase 3f: gazetteer coverage measured.
- [ ] For Phase 3g: KG version exposure verified.

### 14.2 Byte-diffs

- [ ] `"Count of suppliers"` — stdout identical to the golden file.
- [ ] `"Show PO 2144 and its lines"` — stdout identical.
- [ ] `"Which suppliers have open purchase orders?"` — stdout identical.
- (For phases that intentionally change output — record and explain; update the golden file.)

### 14.3 KG integrity

- [ ] `spire-ops kg rebuild` succeeds.
- [ ] `spire-ops kg print --counts-only` matches expected.
- [ ] `tests/integration/kg/test_kg_metadata.py` passes.
- [ ] KG version is present and stable.

### 14.4 Branch and PR

- [ ] Branch named `phase-{N}{letter}-...` per §6.
- [ ] Commits use named `git add`, not `-A`.
- [ ] PR uses the template at §14.6.
- [ ] PR linked to this document (§{N}).

### 14.5 Documentation

- [ ] §6 Phase Index row updated.
- [ ] §{N} Status section updated.
- [ ] §15 Session Log has a one-line pointer to the session entry.
- [ ] **Doc B §1 snapshot updated.**
- [ ] **Doc B §2 registers updated (bugs, investigations, decisions, questions).**
- [ ] **Doc B §4 has the full session entry (work items, commands, outputs, evidence).**
- [ ] **Every doc reference to a moved/renamed file is updated, or covered by a shim.**

### 14.6 PR template

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
- (For probabilistic fixes) N-run evidence: {link}
- (For Phase 3e) Per-quirk test results: {link}
- (For Phase 3f) Gazetteer coverage: {percentage}
- (For Phase 3g) KG version exposure: {link}

### Rollback
`git revert {sha}`. Delete: {new files}.

### Deviations from plan
{none / list}

### Status update
After merge, update §6 Phase Index and §15 Session Log.
```

---

## 15. Session Log

**Append-only. Newest entry at the top.**

**This section is a pointer index, not a full log.** The full forensic record for every session lives in the companion document:

`SPIRE_ROBUSTNESS_EXTENSIBILITY_v3.2_Status.md` §4.

Each entry here is three lines: phase, branch, summary, and a pointer. That keeps Doc A small enough to paste into a new window without dragging history with it. Detail lives in Doc B.

### Pointer template

```markdown
### YYYY-MM-DD — Session S###

**Phase:** {phase number and name}
**Branch:** `{branch}`
**Summary:** {one sentence — what was done}
**Full record:** Doc B §4 S###.
```

### Entries

*(No entries yet. Session S001 will add the first pointer.)*

---

# Appendices

## Appendix A — Baseline snapshot (2026-09-13)

**These numbers are a snapshot from the document's authoring date. They are illustrative, not authoritative. Phase 1 re-measures from scratch, and the Phase 1 numbers become the baseline that every subsequent phase compares against. Do not treat any number below as a gate.**

| Metric | Value at authoring | How measured |
|---|---|---|
| Test count | ~996 selected, 18 deselected, ~1,014 total | `pytest -q --collect-only \| tail -1` |
| Test collection time | ~2.5s | same |
| Python files in `src/spire/` | ~71 | `find src/spire -name "*.py" \| wc -l` |
| Python files in `scripts/` | ~33 | `find scripts -name "*.py" \| wc -l` |
| Python files in `tests/` | ~55 | `find tests -name "*.py" \| wc -l` |
| MCP tool count | 34 | `server.py` `@mcp.tool()` occurrences |
| `.sysprompt` files | 51 | `find src/spire/nl_parser/context -name "*.sysprompt" \| wc -l` |
| Parser prompt input tokens | 8,805–8,819 | from `[llm] stage=parse in=...` logs |
| LLM calls per request (typical) | 2 | classify + parse |
| LLM calls per request (worst case) | 3 | classify + parse + synthesize |
| Anchored query wall-clock | ~16s | `run_graph.py` on PO 701337 prompt |

**Dependency versions at authoring:**

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

**KG row counts at authoring:**

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

### B.1 Deterministic test evidence block

For a bug that fires every time, or for a phase that makes a deterministic change:

```
$ pytest -q --collect-only | tail -1
{N} selected, {M} deselected, {T} total

$ pytest -q
{N} passed, {M} deselected in {T}s

$ python -m spire.cli.run --prompt "Count of suppliers" > /tmp/after.txt 2>&1
$ diff docs/audit/golden/count_suppliers.txt /tmp/after.txt
{empty diff}
```

### B.2 N-run evidence block (for probabilistic behaviour)

For a bug that fires probabilistically, or for a change that affects a probabilistic behaviour:

```
$ for i in $(seq 1 20); do
    python -m spire.cli.run --prompt "{prompt}" 2>&1 | grep "{assertion}" >> /tmp/nrun.txt
  done
$ sort /tmp/nrun.txt | uniq -c
{count of each outcome}

$ python -c "
from collections import Counter
outcomes = open('/tmp/nrun.txt').read().splitlines()
c = Counter(outcomes)
print(f'Runs: {sum(c.values())}')
for outcome, n in c.most_common():
    print(f'  {outcome}: {n} ({n/sum(c.values()):.0%})')
"
{Runs: 20
  correct_outcome: 19 (95%)
  incorrect_outcome: 1 (5%)}
```

The evidence must show:

- N ≥ 20 for any probabilistic bug fix.
- The correct outcome dominates (typically ≥ 95% of runs).
- The failure mode is documented (what the incorrect outcome looks like).
- For a *fix*, the pre-fix distribution and post-fix distribution are both recorded.

### B.3 Timing evidence block

For a performance phase:

```
$ time python -m spire.cli.run --prompt "Show PO 2144 and its lines"
[...]
real  0m{N}.{M}s

# Run 5 times, report mean, median, p95
```

### B.4 KG integrity block

```
$ spire-ops kg rebuild
$ spire-ops kg print --counts-only
$ spire-ops kg version
```

### B.5 Phase 3e per-quirk evidence block

For the generic-executor acceptance bar:

```
# For each endpoint being migrated:
#   - list its declared quirks
#   - for each quirk, link the test that verifies it
#   - byte-equality on 3+ argument combinations, including one that exercises a quirk

Tool: suppliers.py
  Declared quirks:
    - no_composite_q
    - no_fields_projection (not applicable; suppliers does project)
  Per-quirk tests:
    - tests/unit/executor/test_quirks.py::test_no_composite_q_honoured
  Byte-equality combinations:
    - {"status": "ACTIVE"}  ✓
    - {"country": "US"}  ✓
    - {"status": "ACTIVE", "country": "US"}  ✓  (composite-q case)
```

### B.6 Phase 3f gazetteer evidence block

For the deterministic-classifier phase:

```
$ python -m spire.ops.classifier.coverage --corpora prompts/corpora/
Corpora: {N} prompts
Gazetteer-resolved: {N_g} ({percentage}%)
LLM-fallback: {N_l} ({percentage}%)

Sample fallback prompts:
  - {prompt_1}
  - {prompt_2}
```

### B.7 Phase 6e concurrency evidence block

For the concurrency & back-pressure phase:

```
$ python -m spire.ops.loadtest --concurrency 10 --prompt "Count of suppliers"
Requests: 10
  Completed: 10
  Failures: 0
  Mean latency: {N}ms
  Pool saturation: none
  LLM rate-limited: {N} calls throttled

$ python -m spire.ops.loadtest --concurrency 100 --prompt "Count of suppliers"
Requests: 100
  Completed: {N}
  Rejected (queue full): {N}
  Mean latency: {N}ms
  Rejection message: "{...}"
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
| 2026-09-13 (v3.1) | **Drift is the proven root-cause class — S1 and S4 are shipped, documented instances, not hypotheticals.** | The document's §3 argument for consistency is now backed by evidence, not just theory. Phase 1's audit cites them. |
| 2026-09-13 (v3.1) | **LLM-boundary changes require N-run evidence (N ≥ 20), not single-pass tests.** | Probabilistic bugs pass a single-run test 95% of the time when live. The caching regression this session was caught by running 40 times, not once. |
| 2026-09-13 (v3.1) | **Per-endpoint quirks are declared in the spec, not re-derived from code.** | The generic executor must reproduce each legacy tool's quirks. Making them declarative makes consolidation auditable. Phase 3d defines the `quirks` block; Phase 3e's acceptance bar requires per-quirk tests before deleting any legacy tool. |
| 2026-09-13 (v3.1) | **Entry-point moves require thin forwarding shims, not just a move.** | Moving `scripts/*.py` to `src/spire/cli/` breaks every documented command in the repo. The shims preserve muscle memory and prevent doc rot; Phase 4a also greps and updates every doc reference. |
| 2026-09-14 (v3.2) | **Deterministic classifier merged into Phase 3f.** | Tier 1 item from the initial review. Fits Phase 3's thesis: replace an LLM call with a KG lookup. Removes one LLM call from ~80% of requests. |
| 2026-09-14 (v3.2) | **KG versioning merged into Phase 3g.** | Infrastructure required by Phase 6 caches. Belongs in Phase 3 because it is about the KG's integrity as the single source of truth. |
| 2026-09-14 (v3.2) | **Plan cache merged into Phase 6d.** | Sibling of tool cache (6a) and intent cache (6c). The planner is deterministic; caching it is cheap and effective. |
| 2026-09-14 (v3.2) | **Partial results merged into Phase 2 §8.3.7.** | Expands Phase 2's thesis from "fix bugs" to "fix bugs and behave correctly under partial failure." This is a correctness concern, not a UX detail. |
| 2026-09-14 (v3.2) | **Concurrency and back-pressure merged into Phase 6e.** | Production concern. Fits Phase 6's performance thesis. Pooled client, LLM rate limiting, bounded queue. |
| 2026-09-14 (v3.2) | **Page-cap-at-scale, multi-tenancy, streaming, auth marked explicit non-goals in §4.6.** | Deferred with revisit triggers. More honest than silent omission. |
| 2026-09-14 (v3.2) | **`docs/architecture/` added as a Phase 4a task.** | Separates "design of X" documents from "overview of the system" documents. Helps new contributors know what to read first. |
| 2026-09-14 (v3.2) | **No phase renumbering. No phase reordering. Merge only.** | The dependency argument (Appendix D) is unchanged. The seven phases cover every kind of work. Merge preserves every prior session log, PR, and branch reference. |
| 2026-09-14 (v3.2 Addendum A) | **Two-document model: Doc A frozen plan, Doc B append-only status.** | Separates the invariant plan from the evolving forensic record. The plan never drifts; history never gets lost to a window limit. Doc A carries one-line pointers only; session detail, bugs, investigations, commands, and outputs live in Doc B. |
| 2026-09-14 (v3.2 Addendum B) | **UI and API layer merged into Phase 4d.** | Fits Phase 4 (Structure) because it is a packaging change: new packages, new console scripts. Must follow Phase 3 (stable pipeline) and precede Phase 5 (instrumentation) and Phase 6 (performance observation). |
| 2026-09-14 (v3.2 Addendum B) | **Backend is FastAPI, async, with two endpoints (`GET /status`, `POST /prompt`).** | Async is the scalable choice; the pipeline is already async. Two endpoints is the minimum: one for health, one for work. No other endpoints are required. |
| 2026-09-14 (v3.2 Addendum B) | **HTTP status codes reflect reality (200 for normal answers, 5xx for pipeline errors).** | Lets the UI distinguish "SPIRE answered" from "SPIRE broke" before parsing JSON. Plays well with load balancers and monitoring. |
| 2026-09-14 (v3.2 Addendum B) | **Frontend is Streamlit, one page, no history, no settings.** | The requirement is a minimal prompt-in / answer-out interface. Streamlit is the least-code path. History, settings, and multi-turn are out of scope. |
| 2026-09-14 (v3.2 Addendum B) | **API and UI are separate packages and separate processes.** | The API is a plain JSON HTTP service. Streamlit is one client; React (or anything else) is another. When the UI is rewritten, the API does not change. |

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

The v3.1 order eliminated the rework. Structure is Phase 4, after Consistency has revealed the true shape. Extensibility is Phase 7, after everything else has stabilized. No phase forces a later phase to undo it.

**The v3.1 additions strengthened the argument in two places.**

The first is the ordering's *evidence*: S1 and S4 prove that the drift class is real, not theoretical. Correctness + Consistency aren't just good ideas; they address a defect class with shipped instances.

The second is the ordering's *risk*: Phase 3e is the phase where consolidation can go wrong, and v3.1 made the acceptance bar per-quirk rather than per-sample. This doesn't change the ordering; it makes the hardest phase in it survivable.

**v3.2 note.** The initial-review merge adds sub-phases inside existing phases (3f, 3g, 6d, 6e) and one section inside Phase 2 (§8.3.7). The dependency argument is unchanged. The seven-phase order remains Audit → Correctness → Consistency → Structure → Observability → Performance → Extensibility. No phase was renumbered. No phase was reordered. Every prior session log, PR, and branch reference remains valid.

**Addendum A note.** The two-document model is a tracking change, not a design change. Doc A stays frozen; Doc B (`SPIRE_ROBUSTNESS_EXTENSIBILITY_v3.2_Status.md`) carries the append-only forensic record. The seven-phase order and the dependency argument are unchanged. Every prior session log, PR, and branch reference remains valid.

**Addendum B note.** Phase 4d (UI and API layer) is a sub-phase inside Phase 4 (Structure). It adds two clients of the pipeline — a FastAPI server and a Streamlit app — with no change to the pipeline itself. The dependency argument is unchanged: it is placed after Phase 3 (stable pipeline) and before Phase 5 (instrumentation). No phase was renumbered. No phase was reordered. Every prior session log, PR, and branch reference remains valid.

---

## End of document

**Next action:** Open a new DeepSeek window, paste this document, and say:

> *"Resume SPIRE work. Read §6 Phase Index and §15 Session Log. Start Phase 1. Here is the current repo state: [paste `git status`, `git branch`, `pytest -q`]"*

---

**Document version:** 3.2
**Last updated:** 2026-09-14
**Next revision:** After Phase 1 completes, add the first Session Log entry and update §6 Phase Index.

---
