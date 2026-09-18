# SPIRE — Context Bundles

A short explainer for anyone (human or a fresh AI window) who needs to
understand how source code is packaged and shared in this repo.

---

## What a context bundle is

A context bundle is a single Markdown file containing several source
files concatenated together, each preceded by a header naming its path.
It exists so that code can be shared in one paste instead of many, and
so that a reader (often an AI session) can see a coherent slice of the
repo — the parser and planner together, or the KG loader and its SQL —
rather than scattered individual files.

The bundle format is plain and readable:

```
# Context bundle: `parser_planner`

Generated from `/home/.../spire`.
Files included: 18.

---

## src/spire/nl_parser/draft.py

```python
<contents>
```

## src/spire/nl_parser/parser.py

```python
<contents>
```
```

The header carries the bundle name, the repo root it was generated from,
and the file count. Each file is a `## relative/path` heading followed
by a fenced code block. Language hints in the fence follow the file
extension (`.py` → `python`, `.sh` → `bash`, `.sql` → `sql`, `.md` →
`markdown`, and so on).

---

## How to build them

The builder is `build_context.py` at the repo root. Bundle definitions
live in `context_bundles.yaml`, also at the repo root. If the YAML is
missing, the script writes out its built-in defaults on first run so you
can edit them.

Output goes to `./context_out/<name>.md`. The directory is created
if missing.

### Common commands

| Command | What it does |
|---|---|
| `python build_context.py --list` | Print every bundle name and its include patterns. Builds nothing. |
| `python build_context.py --all` | Build every bundle defined in `context_bundles.yaml`. |
| `python build_context.py parser_planner` | Build one bundle. |
| `python build_context.py parser_planner synthesizer` | Build several named bundles. |
| `python build_context.py --files src/spire/config.py docs/spire_poc_log.md --name adhoc` | Ad-hoc bundle of exactly these paths. Output goes to `context_out/context_adhoc.md`. |
| `python build_context.py --lines` | Report code-line counts for the `.py` files in every bundle. Builds nothing. |
| `python build_context.py --lines parser_planner mcp_server_tools` | Same, restricted to named bundles. |

### What "building" does

For each bundle, the script:

1. Expands each include pattern against the repo root. A pattern may be
   a directory (recursed), a specific file, or a glob (`docs/*.md`).
2. Applies `excludes` from `context_bundles.yaml`. Common excludes:
   `personas.yaml` (credentials), `.git`, `traces`, `context_out`,
   `.pyc`, `__pycache__`, `*.pdf`, `*.svg`, `docs/archive/*`.
3. De-duplicates while preserving order (so a file listed in two
   patterns appears once).
4. Renders each file as a `## path` heading plus a fenced code block.
   The fence length grows if the file itself contains triple backticks,
   so the fence cannot be broken by the content.
5. Writes the concatenation to `context_out/context_<name>.md` and prints
   a summary table (file count, size, approximate token count).

---

## The bundles

There are eleven bundles defined in `context_bundles.yaml`. Sizes below
are from a run on 2026-09-18; they grow as the repo grows.

### `root` — project root and content files

**Files:** 32. **Size:** ~487 KB, ~125k tokens.

The general front door. Contains `README.md`, `how-to-run.md`,
`prompt_coverage.md`, `pyproject.toml`, `requirements.txt`,
`personas.example.yaml`, `src/spire/config.py`,
`src/spire/diagnostics.py`, the Doc A/B files under
`docs/spire-robustness/`, the handoff, `docs/developer/context_bundles.md`
(this document), the endpoints reference, the SME checklist, the cache
architecture doc, the feature docs under `docs/features/`, the launcher
scripts `run-server.sh` / `run-all.sh` / `SPIRE-PORTS.env`, and the four
`.puml` design sketches.

**When to request it:** a new session that needs repo orientation.
Usually too broad for one focused task.


### `plan` — the master plan, the audit, and the log

**Files:** 10. **Size:** ~437 KB, ~112k tokens.

Contains the master plan (`SPIRE_ROBUSTNESS_EXTENSIBILITY_v3.2.md`),
the Phase 1 audit (`docs/audit/phase-1-audit.md`), the findings log
(`docs/audit/findings-log.md`), the Phase 1 session log
(`01_Phase_01_Audit_and_Baseline.md`), the Phase 4 structure file, the
session template, and the Doc B index. The audit and log were added
2026-09-18 — this bundle is now the single request that reproduces the
audit's current state, which is what the handoff says a new window
should read first.

**When to request it:** starting a new phase, resuming audit work, or
needing the plan + audit + findings at a glance.

### `prompts` — the prompt-set `.txt` files

**Files:** 19. **Size:** ~158 KB, ~40k tokens.

The twelve prompt-set text files (`01_supplier.txt` through
`qa_testcases.txt`), the test runner (`run_prompt_set.py`), the prompt
README, and the rendering helpers in `src/spire/rendering/formatters.py`.

**When to request it:** inspecting or extending the test corpus,
or comparing prompt coverage.

### `corpora` — the generated JSON corpora

**Files:** 14. **Size:** ~45 KB, ~12k tokens.

The `--generate` output of the prompt sets — every `.json` alongside
its `.txt`. Each JSON carries a `prompt`, a `module` list, a `tool`
name, and a `note` recording the outcome of the last generation.

**When to request it:** checking classifier behaviour against the
frozen baseline, or looking at what the corpus records for a prompt.

### `scripts` — the scripts directory

**Files:** 33. **Size:** ~268 KB, ~69k tokens.

Everything under `scripts/`, including `promptkit.py` (the current test
tooling), `print_kg.py`, `rebuild_kg.py`, `draw_graph.py`,
`inspect_trace.py`, and the S1-remediation verifiers
(`verify_bug1.py` through `verify_bug4.py`).

**When to request it:** working on tooling, or looking for scratch
scripts to retire.

### `graph_kg` — the KG and its plumbing

**Files:** 13. **Size:** ~254 KB, ~65k tokens.

`scripts/sql/kg_schema.sql` (the KG seed), `src/spire/kg/loader.py`,
`src/spire/executor/executor.py`, `src/spire/fusion/client.py`,
`src/spire/graph/pipeline.py`, `src/spire/agent/*`, `tests/test_kg_metadata.py`,
`scripts/print_kg.py`, `scripts/rebuild_kg.py`, `scripts/rebuild_kg.sh`.

**When to request it:** checking KG-table-vs-code drift, or reading the
executor's step semantics.

### `mcp_server_tools` — the MCP server and its tools

**Files:** 34. **Size:** ~293 KB, ~75k tokens.

`src/spire/mcp_server/server.py` plus every file under
`src/spire/mcp_server/tools/` — 34 tools covering suppliers, invoices,
purchase orders, AR invoices, credit memos, receipts, and the aggregations.

**When to request it:** working on a specific tool, checking an argument
name, or tracing a tool-result shape.

### `parser_planner` — the parser and planner core

**Files:** 18. **Size:** ~292 KB, ~75k tokens.

`draft.py`, `parser.py`, `router.py`, `context_assembly.py`,
`vocabulary.py`, `intent_validation.py`, `result.py`, `capability.py`,
the planner package (`planner.py`, `plan_builders.py`, `lookup.py`,
`registries.py`, `models.py`, `kg_db.py`, `date_utils.py`), and the
parser's prompt-cache modules (`cached_llm.py`, `prompt_cache.py`).

**When to request it:** the most common bundle for audit work. Every
question about how an Intent is built, validated, or planned lives here.

### `parser_context` — every `.sysprompt` block

**Files:** 51. **Size:** ~36 KB, ~9k tokens.

`order.manifest`, `classifier_menu.sysprompt`, and every block under
`context/core/`, `context/refusals/`, `context/supplier/`,
`context/payables/`, `context/procurement/`, `context/receivables/`,
`context/columns/`, `context/modes/`.

**When to request it:** checking what the model is told, or comparing
a sysprompt rule against the code that consumes its output.

### `synthesizer` — the synthesis layer

**Files:** 16. **Size:** ~302 KB, ~77k tokens.

`src/spire/synthesizer/synthesizer.py` plus `ar.py`, `p2p.py`,
`aggregation.py`, `lifecycle.py`, `response_validation.py`,
`local_summary.py`, `ranking_summary.py`, `prompts.py`,
`models_common.py`, `constants.py`, `errors.py`,
`src/spire/graph/pipeline.py`, and the three
`tests/test_synthesizer_*.py` files.

**When to request it:** any question about how a response is assembled,
validated, narrated, or rendered.

### `tests` — the test suite

**Files:** 57. **Size:** ~631 KB, ~162k tokens.

Every `tests/test_*.py` file plus the SME checklist.

**When to request it:** checking what is covered, or adding a test.

---

## When NOT to build a bundle

Bundles are for sharing *code with a reader who needs to reason about
it*. They are not a substitute for `git ls-files` (a file manifest),
`grep` (a targeted search), or reading a single file directly (fastest
for a one-file question). If a session needs one file, ask for the
file. If it needs the whole parser and planner together, ask for the
bundle.

---

## Credentials and exclusions

`personas.yaml` is never bundled — it holds credentials. If a bundle
would otherwise include it, `build_context.py` excludes it and warns.
The same exclusion covers `.git`, `traces/`, `context_out/`, compiled
artefacts, PDFs, SVGs, and `docs/archive/`.

If a needed file is missing from a bundle, check `context_bundles.yaml`
and either add the pattern or use the `--files` ad-hoc mode:

```
python build_context.py --files path/to/one.py path/to/another.py --name adhoc
```

That produces `context_out/context_adhoc.md` with exactly those files.