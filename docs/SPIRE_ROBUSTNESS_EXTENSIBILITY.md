# SPIRE — Robustness & Extensibility Design

**What SPIRE should become, and how we get there.**

**Document version:** 2.0
**Created:** 2026-09-13
**Author:** Bhagavan (with architectural analysis by DeepSeek)
**Status:** Living document. Initial design frozen at v2.0; status sections appended per completed phase. **Do not edit existing design sections — add new dated subsections under each phase's Status section.**

---

## How to read this document

**The purpose comes first (§1–§4).** The phases (§6–§12) are the *delivery mechanism*, not the point. Read the purpose before the phases.

**This document is designed to survive across multiple DeepSeek sessions.** Rules:

1. **Never edit a "Design (frozen)" section.** It is the plan agreed at v2.0. If the plan is wrong, record the deviation in that phase's "Status / Deviations" section.
2. **Each phase has a Status section** with `Current status`, `Evidence`, and `Deviations from plan`. Update as work proceeds.
3. **The Phase Index table at §5 is the single source of truth** for progress.
4. **The Session Log at §14 is append-only.** Newest entry at the top.
5. **When starting a new DeepSeek window, paste this document and say:** *"Resume SPIRE work. Read §5 Phase Index and §14 Session Log. Current phase is [X]. Here is the repo state: [paste `git status`, `git branch`, `pytest -q`]."*

---

## Table of Contents

**Part I — Why we're doing this**
1. [Purpose: what SPIRE should become](#1-purpose-what-spire-should-become)
2. [The end state — what "done" looks like](#2-the-end-state--what-done-looks-like)
3. [Today's pain — why this work is needed](#3-todays-pain--why-this-work-is-needed)

**Part II — The design**
4. [Target architecture — one source of truth, one dispatch, one prompt](#4-target-architecture--one-source-of-truth-one-dispatch-one-prompt)

**Part III — The delivery**
5. [Phase Index](#5-phase-index)
6. [Phase 0 — Repo hygiene & source-tree reorganisation](#6-phase-0--repo-hygiene--source-tree-reorganisation)
7. [Phase 1 — Deterministic classifier](#7-phase-1--deterministic-classifier)
8. [Phase 2 — Parser prompt generation from KG](#8-phase-2--parser-prompt-generation-from-kg)
9. [Phase 3 — Tool consolidation (generic KG-driven executor)](#9-phase-3--tool-consolidation-generic-kg-driven-executor)
10. [Phase 4 — Caching & parallel execution](#10-phase-4--caching--parallel-execution)
11. [Phase 5 — Observability & multi-tenancy](#11-phase-5--observability--multi-tenancy)
12. [Phase 6 — Endpoint onboarding: making extensibility real](#12-phase-6--endpoint-onboarding-making-extensibility-real)

**Part IV — Tracking**
13. [Phase completion checklist](#13-phase-completion-checklist)
14. [Session Log](#14-session-log)

**Appendices**
- [A — Baseline state (2026-09-13)](#appendix-a--baseline-state-2026-09-13)
- [B — Evidence capture templates](#appendix-b--evidence-capture-templates)
- [C — Decisions log](#appendix-c--decisions-log)
- [D — Extensibility walkthroughs (today vs target)](#appendix-d--extensibility-walkthroughs-today-vs-target)

---

# Part I — Why we're doing this

## 1. Purpose: what SPIRE should become

SPIRE today answers procurement and receivables questions well on a defined set of endpoints. It is also **hard to grow**. Adding one new Fusion endpoint takes hours and touches dozens of files across the KG, the MCP server, the parser prompt, the synthesizer, the display layer, and multiple tripwire counts. Adding a new Fusion module takes a week. Adding a new MCP tool means writing a new Python file from scratch and remembering to update eight other places that must stay in sync.

**The purpose of this work is to make SPIRE grow easily.** Concretely:

- **Adding an endpoint** should take ~15 minutes and touch ~1 file.
- **Adding a tool** should be a declaration, not a code change.
- **Adding a Fusion module** should be a data operation, not a code migration.
- **Adding a filter or field** should be a row in the KG, not a change to Python.

**The work below is not a "phase plan for its own sake." It is the concrete set of changes that transforms SPIRE from a system that is *finished* to a system that is *growable*.** Every phase exists to reduce the ceremony of the next change.

Two secondary goals follow from this one:

- **Robustness.** The system should not regress when it grows. Behaviour that was correct on five endpoints should be correct on twenty-five. The current architecture has parallel registries that drift; the target architecture has one source of truth.
- **Performance.** Growth currently *slows* SPIRE down. A page-capped aggregation over a bigger collection takes longer; more endpoints mean more opportunities for an LLM call. The target architecture has caching and parallel execution so that growth is *neutral or better* on latency.

**The unifying metric:** how many files does a developer touch to add one new endpoint? Today, 16. Target, 1. This document exists to close that gap.

---

## 2. The end state — what "done" looks like

**The flagship proof of success is this flow.** If SPIRE can do this, all six phases have delivered.

### 2.1 Adding a new endpoint in 15 minutes

> **Scenario:** Add `/suppliers/{id}/child/sites` (supplier sites, a real endpoint that is currently supported but was expensive to add).

**Step 1 — Discover the endpoint (5 min).** Curl it. Note the URL, the fields, the filters, the quirks.

```bash
curl -s --compressed -u "$USER:$PASS" \
  "$BASE/fscmRestApi/resources/11.13.18.05/suppliers/300000047414503/child/sites?limit=1" \
  | python -m json.tool
```

**Step 2 — Write the spec (5 min).** One YAML file.

```yaml
# specs/endpoints/supplier_sites.yaml
name: get_supplier_sites
entity: Site
module: supplier
kind: child
parent_entity: Supplier
parent_id_field: SupplierId
endpoint:
  path: /fscmRestApi/resources/11.13.18.05/suppliers/{supplier_id}/child/sites
  fields: [SupplierSiteId, SupplierSite, ProcurementBU, ProcurementBUId, Status]
fields:
  - {name: SupplierSiteId, role: canonical_id, type: numeric}
  - {name: SupplierSite,   role: display_id,   type: string}
  - {name: ProcurementBU,  role: projection,   type: string}
  - {name: ProcurementBUId,role: projection,   type: numeric}
  - {name: Status,         role: status,       type: string}
filters:
  - name: has_site_in_bu
    kind: edge_traversal
    tool_arg: business_unit
    vocab_kind: supplier_site_bu
    server_q: "ProcurementBU='{value}'"
    keep_parent_when: nonempty
```

**Step 3 — Register (1 min).**

```bash
spire add-endpoint specs/endpoints/supplier_sites.yaml
```

This one command:
- Rebuilds the KG (adds the `Site` entity, its fields, the `HAS_SITE` edge, the `HAS_SITE` edge-tool, the `has_site_in_bu` filter).
- Regenerates the parser prompt (adds a `b_site_in_bu.sysprompt` block, updates the manifest).
- Regenerates the classifier menu (adds `Site` to the `supplier` module menu).
- Regenerates the tripwire counts.
- Emits a stub test.
- Prints a diff for review.

**Step 4 — Verify (3 min).**

```bash
pytest -q
python -m spire.cli.prompt_set --prompt-file prompts/sets/00_dipstick.txt
```

**Step 5 — Commit.**

```bash
git add specs/endpoints/supplier_sites.yaml \
        ops/kg/schema.sql \
        src/spire/nl_parser/context/ \
        tests/unit/synthesizer/test_supplier_sites.py
git commit -m "Add supplier sites endpoint"
```

**Total: ~15 minutes. Files touched by the developer: 2.** (`specs/endpoints/supplier_sites.yaml` and the generated stub test, both of which they write or review.)

**Compare to today.** Today, this same change touches 16 files. See Appendix D for the side-by-side walkthrough.

### 2.2 Adding a new tool, a new filter, and a new module

The same flow scales to all three:

| What you add | Today | After Phase 6 |
|---|---|---|
| **New endpoint** | ~16 files, ~4 hours | 1 spec file, ~15 min |
| **New filter on existing endpoint** | 5 files (KG row, prompt block, manifest, tripwire count, tests) | 1 line in the spec file, ~5 min |
| **New field on existing endpoint** | 3 files (KG row, projection, projection test) | 1 line in the spec file, ~3 min |
| **New MCP tool** | New Python file + registration + tests | 1 spec file, ~15 min |
| **New Fusion module** | New subdirectory, new classifier entry, new prompt blocks, new KG rows, new tests | 1 module header file + endpoints, ~1 hour |

**This is the target.** The phases below exist to build the machinery that makes it possible.

### 2.3 What "robust" means concretely

Robustness isn't vague. It means:

- **No parallel registries.** The KG is the source of truth. Prompts, tool dispatch, tripwire counts, and test stubs all derive from it.
- **No drift between counts.** The four-place count bug (which the codebase already documents multiple times) becomes structurally impossible.
- **No silent additions.** Adding an endpoint without a test fails the build.
- **No unhandled shapes.** Every entity-level fetch, edge traversal, and child fetch is dispatchable through one code path.

---

## 3. Today's pain — why this work is needed

**The 16-file ceremony.** Adding one endpoint today requires editing:

1. `src/spire/mcp_server/tools/<new_tool>.py` — new file
2. `src/spire/mcp_server/server.py` — register the tool
3. `ops/kg/schema.sql` — add entity, fields, edge, edge_tool, filter rows
4. `tests/test_kg_metadata.py` — bump expected counts
5. `ops/kg/print.py` — bump expected counts
6. `ops/kg/schema.sql` — bump "PROMPT Seeded ... (N rows)" banners
7. `src/spire/nl_parser/context/<module>/b_<name>.sysprompt` — new file
8. `src/spire/nl_parser/context/order.manifest` — add the block
9. `src/spire/nl_parser/context_assembly.py` — update the `_SYSTEM_PROMPT_PREAMBLE` literal
10. `src/spire/synthesizer/<module>.py` — add a record type
11. `src/spire/synthesizer/response_validation.py` — add validation
12. `src/spire/rendering/formatters.py` — add a display branch
13. `context_bundles.yaml` — add the new files to the appropriate bundle
14. `tests/unit/synthesizer/test_<new_tool>.py` — new test
15. `ops/kg/rebuild.py` — (no change, but must be re-run)
16. (If the tool is a new entity) — update the classifier menu

**Every one of these is a place to forget a step.** And several of them carry *counts* that must be updated in lockstep — the codebase already documents this as a recurring defect class ("the four places that must move together, not two as earlier notes implied").

**Every one of these is avoidable.** The information needed to write each file already exists in the KG, once the KG has the endpoint declaration. The ceremony is not essential complexity — it is accidental complexity that accumulated as SPIRE grew.

**The pain compounds.** Every new module multiplies the ceremony. The result: SPIRE's *capability* grows linearly with developer effort, but its *velocity* decreases. That is the wrong shape for a system that is supposed to keep growing.

---

# Part II — The design

## 4. Target architecture — one source of truth, one dispatch, one prompt

The five principles that make growth cheap. Each maps to specific phase work below.

### 4.1 Principle 1 — The KG is the single source of truth

If the KG declares it, the system uses it. If the KG does not declare it, the system does not know it exists.

Every piece of the current ceremony that could be derived from the KG becomes **derived from the KG**. Endpoint URLs, projected fields, filters, edges, tool names, prompts, tripwire counts, test stubs — all read from or generated by the KG.

**Realised in:** Phase 2 (prompt generation), Phase 3 (tool dispatch), Phase 6 (endpoint spec + generator).

### 4.2 Principle 2 — One dispatch, not thirty-four tools

Entity-level fetches, edge traversals, and child fetches all share the same shape: read a spec from the KG, call the pod, project fields, apply client-side filters, return a `ToolResult`.

That is **one code path**, not 34. The 34 tool files are a parallel registry — they exist because the KG was not yet the source of truth. Once it is, they collapse to one dispatch function.

**Realised in:** Phase 3.

### 4.3 Principle 3 — One prompt, generated from the KG

The parser prompt is 51 hand-written `.sysprompt` files totalling ~8.8k tokens. Nearly every rule maps to a KG row. The content is derivable; the warnings and examples are not.

A generator produces the derivable skeleton; a small set of overlays preserves the human-authored warnings. Adding an endpoint becomes: 1 SQL insert + 1 generator run.

**Realised in:** Phase 2.

### 4.4 Principle 4 — One declaration per endpoint

The endpoint is declared **once**, in a YAML spec. The spec is the input. Everything else is a generated or derived artifact.

**Realised in:** Phase 6 (the endpoint spec format and the `spire add-endpoint` command).

### 4.5 Principle 5 — Growth is neutral-or-better on latency

Today, growing the system makes it slower:
- More endpoints = more pages to fetch.
- More entities = longer classifier menus.
- More prompt blocks = bigger parse calls.
- No caching means the same slow query runs twice.

Caching and parallel execution invert this. Growth continues to add capability, but wall-clock per request stays flat or improves.

**Realised in:** Phase 4.

---

# Part III — The delivery

## 5. Phase Index

**This table is the single source of truth for progress.** Update it at the end of every session.

| Phase | Name | Status | Branch | Started | Completed | PR |
|---|---|---|---|---|---|---|
| 0 | Repo hygiene & source-tree reorganisation | ⬜ Not started | — | — | — | — |
| 1 | Deterministic classifier | ⬜ Not started | — | — | — | — |
| 2a | Parser prompt coverage validation | ⬜ Not started | — | — | — | — |
| 2b | Parser prompt generation from KG | ⬜ Not started | — | — | — | — |
| 3a | Generic executor — prototype on one operation | ⬜ Not started | — | — | — | — |
| 3b | Generic executor — all entity-level fetches | ⬜ Not started | — | — | — | — |
| 3c | Generic executor — edge traversals + children | ⬜ Not started | — | — | — | — |
| 3d | Delete legacy tool files | ⬜ Not started | — | — | — | — |
| 4a | Tool-result cache (TTL) | ⬜ Not started | — | — | — | — |
| 4b | Parallel step execution | ⬜ Not started | — | — | — | — |
| 4c | Intent cache (3-stage, from `cache_architecture.md`) | ⬜ Not started | — | — | — | — |
| 5a | OpenTelemetry spans | ⬜ Not started | — | — | — | — |
| 5b | Multi-tenant KG | ⬜ Not started | — | — | — | — |
| **6a** | **Endpoint spec format** | ⬜ Not started | — | — | — | — |
| **6b** | **`spire add-endpoint` generator** | ⬜ Not started | — | — | — | — |
| **6c** | **`spire add-module` generator** | ⬜ Not started | — | — | — | — |
| **6d** | **Extensibility documentation + walkthrough** | ⬜ Not started | — | — | — | — |

**Legend:** ⬜ Not started · 🟡 In progress · 🟢 Complete · 🔴 Blocked · ⚪ Deferred

### 5.1 Why Phase 6 is last, and why it is the point

**Phase 6 is the reason for Phases 2 and 3.** Phase 2 makes prompts generated. Phase 3 makes tools dispatchable. Phase 6 turns those two capabilities into a single command a developer can run.

**Phase 6 depends on Phase 2 and 3.** The generator needs generated prompts (Phase 2) and generated dispatch (Phase 3) to have something to generate.

**Phase 6 is a week of work.** It is not a large phase. But it is the phase that finally delivers the purpose stated in §1.

**Do not skip to Phase 6.** Without Phases 2 and 3, there is nothing for `add-endpoint` to generate.

---

## 6. Phase 0 — Repo hygiene & source-tree reorganisation

### 6.1 Objective

Make the source tree navigable. Fix the `personas.yaml` security issue. Establish the directory structure that later phases assume.

### 6.2 Design rationale

Reading the source tree: `src/spire/` is well-organised. Everything else is ad hoc. `scripts/` holds entry points, operator tools, one-off migrations, throwaway probes, data, and config all mixed together. `tests/` is flat (57 files). `test_tools/` is a second test root. The `prompts/` are buried under `scripts/`.

This is a pure refactor with no code change. It is the safest change to make first, and it pays back on every subsequent phase (developers can find things, and Phase 6's spec files have a natural home).

### 6.3 Task 0 — Security: untrack `personas.yaml`

**This must be the first commit on the branch.**

```bash
git rm --cached personas.yaml
echo "personas.yaml" >> .gitignore
git add .gitignore
git commit -m "security: untrack personas.yaml; gitignore it

personas.yaml was tracked in git and contains Fusion + Oracle
credentials. Untracking it does not remove it from history; credentials
must be rotated separately. See SPIRE_ROBUSTNESS_EXTENSIBILITY.md §6.3."
```

**Acceptance:** `git ls-files | grep personas.yaml` returns nothing.

### 6.4 Task 1 — Move `display_formatters.py` to `src/spire/rendering/`

It is a library, not a script. It is imported by `cli/run_graph.py`, `cli/run_prompt_set.py`, `cli/promptkit.py`, and one test file — all via `from display_formatters import ...`, which only works because Python puts the script directory on `sys.path`. That is fragile.

**Procedure:**

```bash
mkdir -p src/spire/rendering
git mv scripts/display_formatters.py src/spire/rendering/formatters.py
```

Create `src/spire/rendering/__init__.py` re-exporting every public name.

Update imports in:
- `scripts/run_graph.py`
- `scripts/run_prompt_set.py`
- `scripts/promptkit.py`
- `tests/test_display_summary_only.py`

**Acceptance:** `grep -r "from display_formatters" .` returns nothing.

### 6.5 Task 2 — Restructure `scripts/` into `src/spire/cli/` and `src/spire/ops/`

Move the entry points into the package so they become installable console scripts. This is cleaner than a top-level `cli/` because it makes `spire --prompt "..."` work from anywhere after `pip install -e .`.

```
src/spire/cli/                    ← entry points (installable)
  ├── __init__.py
  ├── run.py                      ← was scripts/run_graph.py
  ├── prompt_set.py               ← was scripts/run_prompt_set.py
  ├── promptkit.py                ← was scripts/promptkit.py
  ├── promptkit_overnight.py      ← was scripts/promptkit_overnight.py
  ├── overnight.py                ← was scripts/run_overnight.py
  └── inspect_trace.py            ← was scripts/inspect_trace.py

src/spire/ops/                    ← operator tooling (also installable)
  ├── __init__.py
  ├── kg/
  │   ├── __init__.py
  │   ├── rebuild.py              ← was scripts/rebuild_kg.py
  │   ├── print.py                ← was scripts/print_kg.py
  │   ├── schema.sql              ← was scripts/sql/kg_schema.sql
  │   └── smoke_test.py           ← was scripts/test_kg_connection.py
  ├── context/
  │   ├── __init__.py
  │   ├── build_parser_context.py ← was scripts/build_parser_context.py
  │   └── build_classifier_context.py
  ├── build_context.py            ← was scripts/build_context.py
  ├── draw_graph.py               ← was scripts/draw_graph.py
  ├── flag_matrix.sh              ← was scripts/flag_matrix.sh
  └── score_parser_prompts.py     ← was scripts/score_parser_prompts.py

archive/                          ← new top-level directory
  ├── README.md
  ├── probes/
  │   ├── probe_cache.py
  │   ├── probe_cache_v2.py
  │   ├── t_s1_isolate.py
  │   ├── t_s1_repro.py
  │   ├── verify_bug1.py
  │   ├── verify_bug1_step2.py
  │   ├── verify_bug1_step3.py
  │   ├── verify_bug2.py
  │   ├── verify_bug3.py
  │   ├── verify_bug4.py
  │   ├── verify_business_relationship.py
  │   ├── verify_invoices.py
  │   └── verify_nested_addresses.py
  └── migrations/
      ├── add_entity_module.py
      └── apply_bug1_step2_context_assembly.py

prompts/                          ← was scripts/prompts/
  ├── sets/
  ├── corpora/
  ├── scorer/
  └── README.md
```

Delete `scripts/rebuild_kg.sh` (docker-only; superseded by `rebuild.py`).

Add console scripts to `pyproject.toml`:

```toml
[project.scripts]
spire = "spire.cli.run:main"
spire-promptkit = "spire.cli.promptkit:main"
spire-kg = "spire.ops.kg.print:main"
```

**Update paths in:** `context_bundles.yaml` (largest edit), all CLI paths to `prompts/`, `README.md`, `how-to-run.md`, `docs/spire_*.md`.

### 6.6 Task 3 — Subdivide `tests/`

Move to:

```
tests/
├── conftest.py              (new)
├── fixtures/
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
    ├── try_po_lifecycle.py
    └── verify_rank_invoices.py
```

`tests/conftest.py`:

```python
def pytest_collection_modifyitems(config, items):
    import pytest
    for item in items:
        if "tests/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
```

`pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "integration: marks tests requiring external services (MCP server, Gemini, Fusion pod)",
]
addopts = "-m 'not integration'"
```

### 6.7 Task 4 — Move runtime artifacts to `data/`

```
traces/         → data/traces/
context_out/    → data/context_out/
.spire_cache/   → data/.spire_cache/
```

Update: `src/spire/agent/tracing.py` (`TRACES_DIR`), `src/spire/graph/pipeline.py` (`_CACHE_DIR`), `src/spire/ops/build_context.py` (default out-dir), `.gitignore`.

Replace individual `.gitignore` entries with one: `data/`.

### 6.8 Task 5 — Move PDFs and XLSX out of the source tree

```
docs/*.pdf                  → docs/pdf/
docs/spire_tools_modules.xlsx → docs/data/
tests/*.pdf                 → docs/pdf/
```

### 6.9 Task 6 — Clean root

Root should have: `pyproject.toml`, `README.md`, `LICENSE`, `.gitignore`, `personas.example.yaml`, `context_bundles.yaml`, `how-to-run.md`, `prompt_coverage.md`, `requirements*.txt`, `run-server.sh`.

Remove: `source-tree.txt`, `isolation/` (add to `.gitignore`).

### 6.10 Acceptance criteria

| Check | Command | Expected |
|---|---|---|
| personas.yaml untracked | `git ls-files \| grep personas.yaml` | empty |
| no `scripts/` at top level | `ls scripts/` | not found (or only README) |
| all tests pass | `pytest -q` | 996 passed |
| unit tests run fast | `time pytest -q tests/unit/` | <30s |
| three-prompt byte-diff | run three prompts, diff | identical |
| console script works | `spire --prompt "Count of suppliers"` | answer printed |
| bundle build succeeds | `python -m spire.ops.build_context --all` | 10 bundles |

### 6.11 Rollback

`git revert` the merge commit. Delete `src/spire/cli/`, `src/spire/ops/`, `src/spire/rendering/`, `archive/`, `prompts/`, `data/`.

### 6.12 Phase 0 Status

**Current status:** ⬜ Not started

**Evidence:**

*(Paste after Phase 0 completes)*

```
pytest --collect-only output: ...
pytest -q output: ...
byte-diff of three prompts: ...
```

**Deviations from plan:**

---

## 7. Phase 1 — Deterministic classifier

### 7.1 Objective

Eliminate the classifier LLM call for the vast majority of prompts by replacing it with a gazetteer lookup over `KGMenu.entity_synonyms`.

### 7.2 Design rationale

The classifier's job is to match prompt tokens against entity synonyms. That is a lookup, not a classification problem. The `KGMenu` already carries `entity_synonyms` (from `kg_vocabulary` where `vocab_kind='entity_synonym'`) and `entity_descriptions` (from `kg_entity`). The classifier's grounding menu is generated from exactly that data.

Measured cost of the classify call: ~1.4k prompt tokens plus latency. For a prompt the gazetteer can handle, that entire call is unnecessary. The LLM remains as fallback.

### 7.3 Code changes

**7.3.1 Extend `KGMenu`** in `src/spire/nl_parser/vocabulary.py`:

Add `entity_modules: dict[str, str]` (entity_name → module). Populate in `load_kg_menu()` from `kg_entity.module`.

**7.3.2 Add `classify_modules_deterministic`** in `src/spire/nl_parser/router.py`:

```python
import re

def classify_modules_deterministic(
    prompt: str,
    menu: KGMenu,
) -> list[str] | None:
    """Classify a prompt to Fusion module(s) by gazetteer lookup.

    Returns a sorted list of module names if any synonym matched,
    or None if nothing matched (caller falls back to the LLM).
    """
    p = prompt.lower()
    tokens = set(re.findall(r"[a-z0-9]+", p))

    module_votes: dict[str, int] = {}
    for term, entity in menu.entity_synonyms.items():
        t = term.lower()
        matched = (t in p) if " " in t else (t in tokens)
        if not matched:
            continue
        module = menu.entity_modules.get(entity)
        if module is None:
            continue
        module_votes[module] = module_votes.get(module, 0) + len(t.split())

    if not module_votes:
        return None
    return sorted(module_votes.keys())
```

**7.3.3 Modify `route_and_parse`** to try the gazetteer first, then fall back:

```python
modules = classify_modules_deterministic(prompt, menu)
if modules is None:
    try:
        modules = classify_modules(prompt, llm=llm)
    except ClassificationError:
        return parse(prompt, llm=llm, menu=menu)
scoped = assemble_subset(modules, menu)
return parse(prompt, llm=llm, menu=menu, system_prompt=scoped)
```

### 7.4 Tests

**New:** `tests/unit/nl_parser/test_router_deterministic.py`

- Single-synonym prompt classifies without the LLM.
- No-synonym prompt returns `None`.
- Multi-module prompt returns both modules.
- Parametrized over every `entity_synonym` in the KG.
- A "forbidden LLM" mock that fails the test if touched.

**Modify:** `tests/unit/nl_parser/test_router.py` — pass an empty `KGMenu` so the gazetteer returns `None` and the LLM path is exercised.

**New:** `tests/integration/nl_parser/test_router_live.py` — run `--validate` on all corpora; tool pass count unchanged. Count `[llm] stage=classify` lines before/after.

### 7.5 Acceptance criteria

| Check | Expected |
|---|---|
| All tests pass | same pass count |
| Classify calls drop | ≥80% reduction |
| Gazetteer handles ≥80% of prompts | measured |
| Byte-diff of three prompts | identical |
| Fallback works | LLM is called on no-synonym prompt |

### 7.6 Rollback

Revert the merge. Delete `classify_modules_deterministic`.

### 7.7 Phase 1 Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

## 8. Phase 2 — Parser prompt generation from KG

### 8.1 Phase 2a — Prompt coverage validation

#### 8.1.1 Objective

Add a test that fails when the KG declares an entity, filter, or field that the hand-written prompt does not cover.

#### 8.1.2 Design rationale

The parser prompt *should* cover everything the KG declares, because the parser can only produce Intents using KG-declared entities and filters. Nothing enforces that today. The validation test is the low-risk version of Phase 2.

#### 8.1.3 Code changes

**New:** `tests/integration/nl_parser/test_prompt_coverage.py`

```python
@pytest.mark.integration
def test_every_entity_appears_in_prompt():
    from spire.nl_parser.context_assembly import _ASSEMBLED_PREAMBLE
    from spire.nl_parser.vocabulary import load_kg_menu
    menu = load_kg_menu()
    missing = [e for e in menu.entity_descriptions
               if e not in _ASSEMBLED_PREAMBLE]
    assert not missing, (
        f"Entities in kg_entity but not mentioned in the prompt: {missing}"
    )


@pytest.mark.integration
def test_every_filter_appears_in_prompt():
    menu = load_kg_menu()
    missing = [f for f in menu.filter_types
               if f not in _ASSEMBLED_PREAMBLE]
    assert not missing
```

#### 8.1.4 Acceptance criteria

Test passes today (the prompt does cover everything). If it fails, fix the prompt first.

#### 8.1.5 Phase 2a Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

### 8.2 Phase 2b — Parser prompt generation

#### 8.2.1 Objective

Replace the 51 hand-written `.sysprompt` files with a generator that derives most content from the KG plus a smaller set of overlay files for warnings and examples.

#### 8.2.2 Design rationale

Every `b_*.sysprompt` contains "phrase → filter" rules that map to KG rows. The content is derivable; the *phrasing* is not (yet). The generator produces the skeleton; the overlay preserves the human-authored judgement.

Adding a new entity becomes: 1 SQL insert + 1 generator run. Time drops from 3 hours to 15 minutes.

**Important caveat:** this halves prompt-authoring work, not eliminates it. ~15 overlays remain hand-written.

#### 8.2.3 Code changes

**Rewrite:** `src/spire/ops/context/build_parser_context.py`. The new generator reads the KG and emits `.sysprompt` files, appending overlay content if present.

**New directory:** `src/spire/ops/context/overlays/<module>/<filter>.overlay` — holds the warnings and examples.

**Update:** `src/spire/nl_parser/context_assembly.py` — remove the `_SYSTEM_PROMPT_PREAMBLE` literal.

**Update:** `tests/unit/nl_parser/test_parser_context_assembly.py` — the oracle changes:

- Old: assembled == hand-written literal
- New: files match the generator's output (via a `--check` mode)

#### 8.2.4 Migration plan

1. Run the generator. It produces new `.sysprompt` files.
2. Diff against current.
3. Where the generator is missing something, add it to the overlay.
4. When the assembled prompt is functionally equivalent, commit the generated files, delete the hand-written ones.

**Note:** "functionally equivalent" is tested by the prompt suite, not by a byte-diff (the phrasing differs).

#### 8.2.5 Acceptance criteria

| Check | Expected |
|---|---|
| Idempotent generation | no diff on second run |
| Files match committed (`--check`) | 0 exit |
| All tests pass | same pass count |
| `--validate` on all corpora | same tool pass count |
| Adding a filter test | new `.sysprompt` appears after adding a KG row |

#### 8.2.6 Rollback

Keep hand-written files in `legacy/` for one sprint.

#### 8.2.7 Phase 2b Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

## 9. Phase 3 — Tool consolidation (generic KG-driven executor)

This is the largest phase. Split into four sub-phases.

### 9.1 Design rationale (all sub-phases)

The 34 MCP tools share ~90% of their code. The variation is entirely encoded in the KG: endpoint, projection, filters, parent-or-child, edge semantics.

Collapsing them to one dispatch is the change that makes adding a tool **not a Python task**.

**Target:** 34 tools → 12 (1 generic + 11 semantic). The 11 semantic tools are aggregations, comparisons, and lifecycle — code that does Python-side math the KG cannot express.

### 9.2 Phase 3a — Prototype on one operation

#### 9.2.1 Objective

Implement `execute_operation` for `search_suppliers`. Prove the pattern.

#### 9.2.2 Code changes

**New:** `src/spire/mcp_server/tools/execute.py` — reads the KG spec, calls the pod, projects fields, applies client-side filters, returns a `ToolResult`. Reuses helpers from `plan_builders.py` where possible.

**Register:** add `execute_operation` to `server.py`. The 34 legacy tools stay.

#### 9.2.3 Tests

**New:** `tests/integration/mcp_tools/test_execute_operation_prototype.py` — parametrized byte-equality vs the legacy tool.

#### 9.2.4 Acceptance criteria

All prototype operations produce identical `ToolResult` dicts. 34 legacy tools untouched. Full test suite passes.

#### 9.2.5 Phase 3a Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

### 9.3 Phase 3b — All entity-level fetches

#### 9.3.1 Objective

Extend the prototype to every entity-level fetch (8 entities, ~20 operation specs).

#### 9.3.2 Scope

Supplier (none, country, status, name_fragment, created_date), Invoice (none, supplier, invoice_date, invoice_amount), Address (none, supplier, country), PurchaseOrder (none, by_id, created_before, created_since, lifecycle_status), ReceivablesInvoice (by_id), CustomerAccount (by_customer_name), CreditMemo (none), StandardReceipt (none, customer_name, customer_site).

#### 9.3.3 Code changes

Extend the prototype for:
- `tool_arg_name_hi` (range filters)
- Value-shape routing (digits → id, else name)
- Client-side status filtering

#### 9.3.4 Acceptance criteria

All entity-level fetches byte-equal their legacy counterparts. `--validate` on all corpora passes.

#### 9.3.5 Phase 3b Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

### 9.4 Phase 3c — Edge traversals + child fetches

#### 9.4.1 Objective

Cover all 16 edges and all child fetches.

#### 9.4.2 Code changes

The executor gains dispatch branches for `edge_traversal` and `child` kinds. Edge traversal wraps the existing iteration logic; child fetch reads the parent-id path template from the KG.

#### 9.4.3 Acceptance criteria

All edges and children byte-equal their legacy counterparts. Full prompt suite runs clean.

#### 9.4.4 Phase 3c Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

### 9.5 Phase 3d — Delete legacy tools

#### 9.5.1 Objective

Delete the 24 fetch-only tool files. Keep the 7 semantic tools.

#### 9.5.2 Files to delete

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

That is **24 files**, keeping these 7:

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

#### 9.5.3 Code changes

- Delete the 24 files and their `@mcp.tool()` wrappers.
- Update `planner.py` to emit `execute_operation` instead of tool names.
- Update `executor.py`.
- Update KG: `kg_entity_tool.mcp_tool_name` becomes `'execute_operation'` for the affected rows.
- Update `context_bundles.yaml`.
- Delete corresponding `tests/integration/mcp_tools/test_*_tool.py`.

#### 9.5.4 Acceptance criteria

- Only semantic tools + `execute_operation` are registered.
- All tests pass.
- Full prompt suite runs with no regression.
- Corpora regenerated (`--generate`), reviewed, committed.

#### 9.5.5 Phase 3d Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

## 10. Phase 4 — Caching & parallel execution

### 10.1 Phase 4a — Tool-result cache

#### 10.1.1 Objective

TTL cache around MCP tool calls.

#### 10.1.2 Design rationale

Two users asking "top 10 suppliers by spend in 2022" within a minute should share one pod fetch. The spend aggregation is the canonical slow case.

**Constraint:** the cache must respect `truncated`. Cached results carry truncation metadata verbatim.

#### 10.1.3 Code changes

**New:** `src/spire/mcp_server/tools/cache.py` — keyed on `(tool_name, frozen_args)`, `threading.Lock`, TTL 300s (configurable), `SPIRE_TOOL_CACHE_DISABLE=1` env flag.

**Modify:** `src/spire/executor/executor.py` — wrap `session.call_tool`.

#### 10.1.4 Acceptance criteria

2 concurrent identical requests → 1 pod fetch. Cache respects truncation. No answer change. `--validate` passes.

#### 10.1.5 Phase 4a Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

### 10.2 Phase 4b — Parallel step execution

#### 10.2.1 Objective

Replace sequential `for step in plan` with a dependency-aware parallel executor.

#### 10.2.2 Design rationale

The anchor question has N independent PO fetches and M independent buyer lookups. They can run concurrently.

#### 10.2.3 Code changes

**Modify:** `src/spire/planner/models.py` — add `depends_on: list[str]`.

**Modify:** `src/spire/planner/plan_builders.py` — every `Step` sets `depends_on`.

**Modify:** `src/spire/executor/executor.py` — new `execute_plan_parallel` using `asyncio.gather` for ready steps.

**Modify:** `src/spire/graph/pipeline.py` — call the parallel version.

#### 10.2.4 Acceptance criteria

Anchor question wall-clock drops from ~17s to <5s. Byte-diff identical to sequential.

#### 10.2.5 Phase 4b Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

### 10.3 Phase 4c — Intent cache

#### 10.3.1 Objective

Implement the 3-stage intent cache from `docs/cache_architecture.md`.

#### 10.3.2 Design rationale

Every prompt ships ~8.8k input tokens. Repeat prompts can reuse cached Intents.

#### 10.3.3 Code changes

**New:** `src/spire/nl_parser/intent_cache.py` — three stages.
**New:** `src/spire/nl_parser/intent_cache_backends.py` — SQLite + vector store.
**New:** `src/spire/nl_parser/intent_cache_verify.py` — Stage 3.
**Modify:** `router.py` — consult the cache.

#### 10.3.4 Acceptance criteria

10 repeats of one prompt → 1 parse call. Zero new failures in `--validate`. Cache invalidates on KG rebuild.

#### 10.3.5 Phase 4c Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

## 11. Phase 5 — Observability & multi-tenancy

### 11.1 Phase 5a — OpenTelemetry spans

#### 11.1.1 Objective

Replace `--show-*` diagnostics with OTel spans for production observability.

#### 11.1.2 Code changes

**New:** `src/spire/observability/` — tracer setup, span helpers.
**Modify:** `graph/pipeline.py`, `executor/executor.py`, `nl_parser/parser.py` — wrap stages in spans.

#### 11.1.3 Acceptance criteria

Full request produces a trace with expected span hierarchy. Metrics exported. <1% overhead.

#### 11.1.4 Phase 5a Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

### 11.2 Phase 5b — Multi-tenant KG

#### 11.2.1 Objective

Support multiple Fusion pods from one SPIRE installation.

#### 11.2.2 Code changes

**Modify:** `ops/kg/schema.sql` — add `tenant_id` to every table.
**Modify:** `src/spire/planner/kg_db.py` — `_kg_cursor(tenant_id='default')`.
**Modify:** `personas.yaml` shape — `tenants:` list.
**Modify:** `src/spire/config.py` — `load_tenant()`.
**Modify:** `src/spire/mcp_server/server.py` — read tenant from request.

#### 11.2.3 Acceptance criteria

Two tenants work independently. Cross-tenant leakage impossible.

#### 11.2.4 Phase 5b Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

## 12. Phase 6 — Endpoint onboarding: making extensibility real

**Phase 6 is the phase that delivers the purpose stated in §1.** Phases 2 and 3 build the machinery. Phase 6 packages it into a single command a developer can run.

### 12.1 Phase 6a — Endpoint spec format

#### 12.1.1 Objective

Define the YAML spec that declares one endpoint. This is the single artifact a developer writes to add a new endpoint.

#### 12.1.2 Design rationale

The spec is the **only file** a developer touches. Everything else is generated. The spec must be:

- **Complete enough** to generate every artifact (entity rows, field rows, edge rows, filter rows, tool dispatch spec, prompt block, classifier menu entry, tripwire counts, stub test).
- **Small enough** to write in 5 minutes.
- **Validated** so a typo fails fast with a clear message.

#### 12.1.3 The spec format

One YAML file per endpoint, in `specs/endpoints/`.

**Full schema:**

```yaml
# Identity
name: get_supplier_sites            # MCP tool name (unique)
entity: Site                         # canonical entity name (unique)
module: supplier                     # one of: payables, procurement, receivables, supplier

# Endpoint declaration
kind: child                          # entity_level | edge_traversal | child
endpoint:
  path: /fscmRestApi/resources/11.13.18.05/suppliers/{supplier_id}/child/sites
  fields:                            # fields to request via ?fields=
    - SupplierSiteId
    - SupplierSite
    - ProcurementBU
    - ProcurementBUId
    - Status
  server_q: null                     # single server clause template, optional
  order_by: null                     # orderBy, optional
  parent_id_field: SupplierId        # for kind=child: which PO field carries the parent id

# Entity declaration (kg_entity)
entity_meta:
  canonical_id_field: SupplierSiteId
  display_name_field: SupplierSite
  description: |
    A supplier site (an assignment point). A supplier can have many sites,
    each in a different ProcurementBU. Only accessible as a child of Supplier.

# Fields (kg_entity_field)
fields:
  - {name: SupplierSiteId,  role: canonical_id, type: numeric, notes: "System primary key."}
  - {name: SupplierSite,    role: display_id,   type: string,  notes: "Site name."}
  - {name: ProcurementBU,   role: projection,   type: string,  notes: "Business unit."}
  - {name: ProcurementBUId, role: projection,   type: numeric}
  - {name: Status,          role: status,       type: string}

# Filters (kg_entity_filter)
filters:
  - name: has_site_in_bu
    kind: edge_traversal
    tool_arg: business_unit
    vocab_kind: supplier_site_bu
    server_q: "ProcurementBU='{value}'"
    keep_parent_when: nonempty
    notes: |
      Edge filter: supplier has at least one site in a given ProcurementBU.

# Parent edge (kg_edge + kg_edge_tool), for kind=child or edge_traversal
parent_edge:
  name: HAS_SITE
  from_entity: Supplier
  from_join_field: SupplierId
  to_join_field: SupplierId
  cardinality: one_to_many
  tool: get_supplier_sites              # this endpoint's name
  traversal_hint: |
    GET /fscmRestApi/resources/11.13.18.05/suppliers/{SupplierId}/child/sites
  notes: |
    Per-supplier child call; one HTTP call per parent supplier.

# Prompt overlay (optional)
# If provided, appended to the generated parser prompt block.
prompt_overlay: |
  - 'suppliers with a site in business unit X' / 'suppliers with a supplier
    site based on business unit X' -> a 'has_site_in_bu' filter whose value
    is the canonical display string for that business unit.

# Test stub (optional)
test_hint:
  example_args: {business_unit: "US1 Business Unit"}
  expected_item_keys: [SupplierSiteId, SupplierSite, ProcurementBU]
```

**Minimal spec** (a trivial entity-level fetch):

```yaml
name: search_currencies
entity: Currency
module: payables
kind: entity_level
endpoint:
  path: /fscmRestApi/resources/11.13.18.05/currencies
  fields: [CurrencyCode, Name, Description]
entity_meta:
  canonical_id_field: CurrencyCode
  display_name_field: Name
  description: "A currency enabled in the Fusion instance."
fields:
  - {name: CurrencyCode, role: canonical_id, type: string}
  - {name: Name,         role: display_name, type: string}
  - {name: Description,  role: projection,   type: string}
```

That is ~20 lines and adds a fully functional tool.

#### 12.1.4 Validation

A separate command validates the spec:

```bash
spire validate-endpoint specs/endpoints/supplier_sites.yaml
```

Checks:

- All required fields present.
- `module` is one of the four (or declared in `modules.yaml`).
- `kind` is one of the three.
- Every field referenced in `endpoint.fields` is declared in `fields`.
- Every filter's `vocab_kind` (if set) exists in `kg_vocabulary`.
- The `entity` does not collide with an existing entity unless `--update` is passed.
- The `name` does not collide with an existing tool.

Errors are line-numbered and actionable.

#### 12.1.5 Acceptance criteria

- A spec for a real existing endpoint (e.g. `supplier_sites`) can be written and validated.
- The validator catches common mistakes (typo in module, missing field, name collision).
- The spec format is documented in `docs/extending/adding-an-endpoint.md`.

#### 12.1.6 Phase 6a Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

### 12.2 Phase 6b — `spire add-endpoint` generator

#### 12.2.1 Objective

One command takes a validated spec and applies every change needed to make the endpoint live.

#### 12.2.2 Code changes

**New:** `src/spire/ops/endpoint/add.py` — the generator.

```bash
spire add-endpoint specs/endpoints/supplier_sites.yaml
```

Behind the scenes:

1. **Load and validate the spec.**
2. **Apply KG changes.** Runs the equivalent of:
   - `INSERT INTO kg_entity (...)`
   - `INSERT INTO kg_entity_field (...)`
   - `INSERT INTO kg_edge (...)`
   - `INSERT INTO kg_edge_tool (...)`
   - `INSERT INTO kg_entity_filter (...)`
   - `INSERT INTO kg_entity_tool (...)` (if `kind=entity_level`)
   All within one transaction. Rollback on any error.
3. **Rebuild the KG.** Runs `spire-ops kg rebuild`.
4. **Regenerate the parser prompt.** Runs the Phase 2b generator.
5. **Regenerate the classifier menu.** Runs the classifier generator.
6. **Update tripwire counts.** Reads the actual counts from the KG and updates:
   - `tests/integration/kg/test_kg_metadata.py`
   - `src/spire/ops/kg/print.py`
   - The `PROMPT Seeded ... (N rows)` banners in `schema.sql`
7. **Emit a stub test.** Writes `tests/integration/mcp_tools/test_<name>.py` with a parametrized template that calls the generic executor.
8. **Print a diff summary.** Every file touched, every KG row added.
9. **Dry-run mode.** `--dry-run` prints the same summary without applying.

**Flags:**

- `--dry-run` — show what would change.
- `--update` — for adding fields/filters to an existing entity.
- `--no-rebuild` — skip the KG rebuild (for batch additions).
- `--yes` — skip confirmation.

#### 12.2.3 What the developer sees

```
$ spire add-endpoint specs/endpoints/supplier_sites.yaml
Loaded spec: get_supplier_sites (Site, module=supplier, kind=child)
Validating... OK

KG changes:
  INSERT kg_entity: Site (1 row)
  INSERT kg_entity_field: SupplierSiteId, SupplierSite, ProcurementBU, ProcurementBUId, Status (5 rows)
  INSERT kg_edge: HAS_SITE (1 row)
  INSERT kg_edge_tool: HAS_SITE -> get_supplier_sites (1 row)
  INSERT kg_entity_filter: has_site_in_bu (1 row)

Generated files:
  src/spire/nl_parser/context/supplier/b_site_in_bu.sysprompt (new)
  src/spire/nl_parser/context/order.manifest (modified)
  src/spire/nl_parser/context/routing/classifier_menu.sysprompt (regenerated)

Updated counts:
  tests/integration/kg/test_kg_metadata.py: 22 -> 23 entities, 210 -> 215 fields, ...
  src/spire/ops/kg/print.py: same
  ops/kg/schema.sql: banners updated

Stub test written:
  tests/integration/mcp_tools/test_get_supplier_sites.py

Apply? [y/N] y
Rebuilding KG... OK
Regenerating parser prompt... OK
Regenerating classifier menu... OK

Done. Next:
  1. Review the diff: git diff
  2. Run: pytest -q
  3. Add the endpoint to context_bundles.yaml if desired
  4. Commit
```

**Time: ~30 seconds.** Developer's work: write the spec (5 min), review (3 min), test (3 min), commit (1 min). Total ~15 minutes.

#### 12.2.4 Files the developer touches

1. `specs/endpoints/supplier_sites.yaml` — the spec (they write it).
2. `tests/integration/mcp_tools/test_get_supplier_sites.py` — the stub (they review and possibly extend it).
3. Optionally `context_bundles.yaml` — if the new endpoint belongs in an existing bundle.

**Target: ≤2 files that require the developer's judgment.**

#### 12.2.5 Acceptance criteria

- `spire add-endpoint` on a real spec applies every change cleanly.
- `pytest -q` passes after.
- The new endpoint is queryable end-to-end via a natural-language prompt.
- `--dry-run` shows the same summary without applying.
- A bad spec fails with a clear error and no partial application.
- The tool is idempotent: running it twice on the same spec errors unless `--update`.

#### 12.2.6 Phase 6b Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

### 12.3 Phase 6c — `spire add-module` generator

#### 12.3.1 Objective

Adding a new Fusion module (e.g. `financials` or `hcm`) should be a data operation, not a code change.

#### 12.3.2 Design rationale

Currently adding a module means:
- New subdirectory in `context/`
- New classifier menu entry
- New KG CHECK constraint values (the `module IN (...)` constraint)
- New prompt blocks
- New tests

After Phase 6, it should mean:
- One `specs/modules/<name>.yaml` file declaring the module.
- One command.

#### 12.3.3 The module spec

```yaml
# specs/modules/hcm.yaml
name: hcm
display_name: "HCM / Human Capital"
description: |
  Human Capital Management — employees, positions, payroll, and
  related workforce data.
entities:
  - Employee
  - Position
  - PayrollRelationship
```

#### 12.3.4 The command

```bash
spire add-module specs/modules/hcm.yaml
```

Applies:

1. Updates the KG CHECK constraint (`chk_kg_entity_module`) to include `hcm`.
2. Updates `KNOWN_MODULES` in `src/spire/nl_parser/context_assembly.py`.
3. Creates `src/spire/nl_parser/context/hcm/` directory.
4. Regenerates the classifier menu.
5. Regenerates the parser prompt (empty for now, ready for endpoints).
6. Emits a README in the new context directory.

The developer then adds endpoints one by one via Phase 6b.

#### 12.3.5 Acceptance criteria

- `spire add-module` on a new module name succeeds.
- The new module appears in the classifier menu.
- Adding an endpoint to the new module works via Phase 6b.
- A prompt routed to the new module uses the correct scoped prompt.

#### 12.3.6 Phase 6c Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

### 12.4 Phase 6d — Extensibility documentation + walkthrough

#### 12.4.1 Objective

Write the developer-facing documentation that makes Phase 6a–6c usable by someone who has not read this design document.

#### 12.4.2 Deliverables

- `docs/extending/adding-an-endpoint.md` — step-by-step with a worked example.
- `docs/extending/adding-a-module.md` — the module flow.
- `docs/extending/adding-a-field-or-filter.md` — the update flow.
- `docs/extending/spec-reference.md` — the full spec schema.
- `docs/extending/troubleshooting.md` — common errors and fixes.
- A recorded walkthrough (text or short video) showing the 15-minute flow.

#### 12.4.3 Acceptance criteria

- A developer who has never seen SPIRE can add an endpoint in 30 minutes following the docs.
- The docs are tested: the worked example is a spec in `specs/endpoints/` that `spire add-endpoint` applies cleanly.
- A tripwire test asserts the walkthrough's commands still work.

#### 12.4.4 Phase 6d Status

**Current status:** ⬜ Not started

**Evidence:**

**Deviations from plan:**

---

# Part IV — Tracking

## 13. Phase completion checklist

Before merging any phase's PR, run this checklist. Every box must be ticked.

### 13.1 Tests

- [ ] `pytest -q` → all tests pass.
- [ ] `pytest -q --collect-only | tail -1` → new test count recorded.
- [ ] Full prompt suite runs with no new failures.
- [ ] For Phase 6: the "add an endpoint" walkthrough succeeds end-to-end.

### 13.2 Byte-diffs

- [ ] `"Count of suppliers"` — stdout identical.
- [ ] `"Show PO 2144 and its lines"` — stdout identical.
- [ ] `"Which suppliers have open purchase orders?"` — stdout identical.
- (For phases that intentionally change output — record and explain.)

### 13.3 KG integrity

- [ ] `spire-ops kg rebuild` succeeds.
- [ ] `spire-ops kg print --counts-only` matches expected.
- [ ] `tests/integration/kg/test_kg_metadata.py` passes.

### 13.4 Branch and PR

- [ ] Branch named `phase-{N}...` per §5.1.
- [ ] Commits use named `git add`, not `-A`.
- [ ] PR uses the template at §13.6.
- [ ] PR is linked to this document (§{N}).

### 13.5 Documentation

- [ ] §5 Phase Index row updated.
- [ ] §{N} Status section updated.
- [ ] §14 Session Log has a new entry.
- [ ] README references updated.

### 13.6 PR template

```markdown
## Phase {N} — {Name}

**Objective:** {one sentence}
**Branch:** `{branch}`
**Tracking:** §{section} of SPIRE_ROBUSTNESS_EXTENSIBILITY.md

### Changes
- {bullet 1}

### Test evidence
- `pytest --collect-only` before: {N} selected, {M} total
- `pytest --collect-only` after: {N'} selected, {M'} total
- `pytest -q` after: {pass_count} passed
- Byte-diff of three prompts: {identical / diff link}

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
- `--validate`: {pass count}
- Byte-diff: {identical / diff}

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

**KG row counts:**

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
python -m spire.cli.run --prompt "Count of suppliers" > /tmp/before.txt 2>&1
# [make change]
python -m spire.cli.run --prompt "Count of suppliers" > /tmp/after.txt 2>&1
diff /tmp/before.txt /tmp/after.txt
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
| 2026-09-13 | The KG stays. No agent loop. | Every bug is in code reading the KG, not the KG itself. |
| 2026-09-13 | The synthesizer is 90% local already. Do not rewrite. | Two remaining LLM-path shapes can be finished incrementally. |
| 2026-09-13 | Phases are ordered 0 → 1 → 2 → 3 → 4 → 5 → 6. | 0 mechanical, 1 small, 2 a lift, 3 biggest risk, 4 latency, 5 production, 6 the capstone. |
| 2026-09-13 | **Extensibility is the primary goal.** Phases 2, 3, 6 exist to make adding endpoints/tools/modules trivial. | The point of this work is that SPIRE grows easily. |
| 2026-09-13 | The `personas.yaml` tracking is a critical security issue. Fixed in Phase 0's first commit. | It contains live credentials. Rotation required separately. |
| 2026-09-13 | Entry points move to `src/spire/cli/`, operator tools to `src/spire/ops/`. | Makes them installable as `spire ...` console scripts. |
| 2026-09-13 | The Phase 2 generator halves prompt-authoring work, not eliminates it. | Warnings and examples are not derivable; overlays preserve them. |
| 2026-09-13 | Phase 3 target is 34 tools → 12 (1 generic + 11 semantic). | Aggregations, comparisons, lifecycle stay. |
| 2026-09-13 | Phase 4b (parallel) is the highest user-visible latency win. | ~17s → <5s on the anchor question. |
| 2026-09-13 | **Endpoint spec format is YAML, one file per endpoint, in `specs/endpoints/`.** | Readable, diffable, validated. |
| 2026-09-13 | **`spire add-endpoint` is idempotent and requires `--update` for re-runs.** | Prevents accidental double-inserts. |

---

## Appendix D — Extensibility walkthroughs (today vs target)

Concrete side-by-side of the flagship extensibility scenarios. These are the acceptance criteria for Phase 6 in narrative form.

### D.1 Adding a new endpoint

**Scenario:** Add `/suppliers/{id}/child/sites` (supplier sites).

**Today (16 files, ~4 hours):**

1. Curl the endpoint.
2. Write `src/spire/mcp_server/tools/supplier_sites.py` (~80 lines).
3. Register in `server.py` (import + `@mcp.tool()`).
4. Add to `ops/kg/schema.sql`: `kg_entity` (Site), `kg_entity_field` (5 rows), `kg_edge` (HAS_SITE), `kg_edge_tool`, `kg_entity_filter` (has_site_in_bu).
5. Bump counts in `tests/integration/kg/test_kg_metadata.py`.
6. Bump counts in `src/spire/ops/kg/print.py`.
7. Bump banners in `ops/kg/schema.sql`.
8. Add `src/spire/nl_parser/context/supplier/b_site_in_bu.sysprompt`.
9. Add to `order.manifest`.
10. Update `_SYSTEM_PROMPT_PREAMBLE` in `context_assembly.py`.
11. Add `SupplierSiteInfo` to `src/spire/synthesizer/p2p.py`.
12. Add to `SupplierRecord` schema.
13. Add to `build_supplier_records`.
14. Add validation to `response_validation.py`.
15. Add display branch to `src/spire/rendering/formatters.py`.
16. Add to `context_bundles.yaml`.
17. Write `tests/integration/mcp_tools/test_supplier_sites_tool.py`.
18. Rebuild the KG (`spire-ops kg rebuild`).
19. Run the full suite.

**Target (2 files, ~15 min):**

1. Curl the endpoint.
2. Write `specs/endpoints/supplier_sites.yaml` (~40 lines).
3. Run `spire add-endpoint specs/endpoints/supplier_sites.yaml`.
4. Review the generated stub test and the diff.
5. Run `pytest -q`.
6. Commit.

**Files the developer writes:** 1 (the spec).
**Files the developer reviews:** 1 (the stub test).

### D.2 Adding a new filter to an existing entity

**Scenario:** Add a `has_invoice_over_amount` filter to `Supplier`.

**Today (5 files):**

1. Add `kg_entity_filter` row to `ops/kg/schema.sql`.
2. Bump counts in `test_kg_metadata.py`, `print.py`.
3. Add `b_invoice_over_amount.sysprompt`.
4. Add to `order.manifest`.
5. Update `_SYSTEM_PROMPT_PREAMBLE` literal.
6. Rebuild the KG.

**Target (1 line):**

1. Add to `specs/endpoints/supplier.yaml`:
   ```yaml
   filters:
     - name: has_invoice_over_amount
       kind: edge_traversal
       tool_arg: amount_min
       server_q: "InvoiceAmount>={value}"
       keep_parent_when: nonempty
   ```
2. Run `spire add-endpoint specs/endpoints/supplier.yaml --update`.
3. Commit.

### D.3 Adding a new field to an existing entity

**Scenario:** Add `TaxpayerCountryCode` to `Supplier`'s projection.

**Today (3 files):**

1. Add `kg_entity_field` row.
2. Bump counts.
3. Add to the projection list in `suppliers.py` (`_PROJECTED_FIELDS`).
4. Rebuild the KG.

**Target (1 line):**

1. Add to `specs/endpoints/supplier.yaml`:
   ```yaml
   fields:
     - {name: TaxpayerCountryCode, role: projection, type: string}
   ```
2. Run `spire add-endpoint specs/endpoints/supplier.yaml --update`.
3. Commit.

### D.4 Adding a new module

**Scenario:** Add an `hcm` module.

**Today (a week):**

1. Update the CHECK constraint on `kg_entity.module`.
2. Update `KNOWN_MODULES` in `context_assembly.py`.
3. Create `src/spire/nl_parser/context/hcm/`.
4. Add module to the classifier menu generator.
5. Regenerate the classifier menu.
6. Add module header to the parser prompt.
7. Add module to any code that enumerates modules.
8. Add endpoints (each = the 16-file ceremony from D.1).
9. Write tests.

**Target (1 file + endpoints):**

1. Write `specs/modules/hcm.yaml` (~10 lines).
2. Run `spire add-module specs/modules/hcm.yaml`.
3. Add endpoints one by one via Phase 6b.
4. Commit.

**Time:** ~1 hour for the module + ~15 min per endpoint.

### D.5 The flagship metric

Across all four scenarios:

| Scenario | Today | Target | Reduction |
|---|---|---|---|
| New endpoint | 16 files, 4h | 1-2 files, 15 min | **16x files, 16x time** |
| New filter | 5 files, 30 min | 1 line, 5 min | **5x files, 6x time** |
| New field | 3 files, 20 min | 1 line, 3 min | **3x files, 7x time** |
| New module | ~30 files, 1 week | 1 file + endpoints, ~1 hour | **30x files, 40x time** |

**This is the metric that matters.** If Phase 6 delivers these numbers, the purpose stated in §1 has been achieved.

---

## End of document

**Next action:** Confirm this plan, then start Phase 0. Paste this document into the next DeepSeek window and say:

> *"Resume SPIRE work. Read §5 Phase Index. Start Phase 0. Here is the current repo state: [paste `git status`, `git branch`, `pytest -q`]"*

---

**Document version:** 2.0
**Last updated:** 2026-09-13
**Next revision:** After Phase 0 completes, add the first Session Log entry and update §5 Phase Index.