<!-- ───── merged from: docs/cache_architecture.md ───── -->

# Spire — Cache Architecture

A three-stage semantic cache that returns a cached **intent** for a prompt without
re-sending the large context bundle to the LLM on every request.

---

## 1. Purpose

In Spire, producing an intent means sending a prompt **plus a large context bundle**
(assembled by `build_context.py` from `context_bundles.yaml`, selected by persona and
module) to the LLM. The prompt is a handful of tokens; the context is the overwhelming
majority of every call. So every call is expensive, and repeated or reworded prompts pay
that cost again and again for what is effectively the same answer.

The cache exists to avoid re-sending the context. Its size is **not** a design parameter —
the cache is size-agnostic. A large context is simply the *reason* caching is worth doing.

The cache has three stages, cheapest first. A prompt exits at the earliest stage that can
answer it:

- **Stage 1** — exact match. Zero LLM cost.
- **Stage 2** — vector similarity within scope. Zero LLM cost on accept.
- **Stage 3** — a cheap two-prompt verification (no context) for borderline matches.
- **Miss** — only a true miss pays the full context cost, and the result is written back so
  the next equivalent prompt hits.

---

## 2. Reference architecture (overview)

![Three-stage cache overview](images/00_overview_three_stage.png)

Green boxes are exits — the earlier a prompt exits, the cheaper it was. Stage 3's **no** is
the only true cache miss. The **learns** arrow is the write-back: every miss (and every
confirmed Stage 3 match) adds an entry, so the same phrasing exits earlier next time.

Write-back is **automatic**. The guardrails against bad entries are the high Stage 2
threshold and the Stage 3 yes/no check — not a human reviewer.

---

## 3. Scope key and entry shape (shared by all stages)

### Scope key

The cache key is **not** `hash(prompt)`. It is:

```
key = hash(module + persona + normalized_prompt)
```

The intent a prompt produces depends on which context bundle was sent, and the bundle is
chosen by **module + persona**. So the scope key is really "which context produced this
intent." The same words under a different module *or* persona hash to a different key and
land on a different entry — they can never collide.

This is a deliberate no-collision guarantee: more distinct keys, more misses, more LLM
calls are all acceptable; a wrong-meaning collision is not.

### Normalization

Minimal and meaning-preserving only:

- lowercase
- trim
- collapse internal whitespace

Nothing that changes meaning (no synonym folding, no punctuation-stripping that could merge
distinct prompts). Aggressive normalization is exactly what would create collisions, so it
is excluded. Stage 1 is therefore a **narrow** exact-match gate; meaning-level matching is
Stage 2's job.

### Entry shape

Every stored entry — in both stores — carries:

| Field | Purpose |
|---|---|
| `intent` | the cached result |
| `original_prompt` | exact words the user typed (debugging, auditing bad hits) |
| `hit_count` | how often served (identifies hot prompts) |
| `created_at`, `last_hit_at` | timestamps (staleness, cold-entry detection) |
| `intent_version` | schema tag for the intent shape |

---

## 4. Stage 1 — exact cache

![Stage 1 exact cache](images/01_stage1_exact_cache.png)

Module and persona are folded into the key **before** the hash, so scope is baked into the
lookup. The store is exact-match only — it does no fuzzy work. A hit returns the intent;
a miss falls straight through to Stage 2.

- **Key:** `hash(module + persona + normalized_prompt)`
- **Store:** `key -> entry`, exact match only
- **Hit:** return `intent`
- **Miss:** fall to Stage 2

---

## 5. Stage 2 — vector similarity

![Stage 2 vector similarity](images/02_stage2_vector_similarity.png)

The scope filter runs **before** the similarity search. Only same-module, same-persona
entries are ever compared, so cross-scope matches are impossible — the filter removes them
before any distance math runs. This carries the Stage 1 no-collision guarantee into Stage 2.

- **Embed:** the prompt
- **Filter:** vector store by `module + persona`
- **Search:** top-k within scope, **k = 1** for now (held as config so k can widen later
  without reshaping the flow)
- **Threshold:** tunable config, defaults **0.90 / 0.75**
  - `>= 0.90` → **accept**, return intent
  - `0.75 – 0.90` → **grey zone**, hand to Stage 3
  - `< 0.75` → **reject**, cache miss → full LLM call

---

## 6. Stage 3 — verify and write-back

![Stage 3 verify and write-back](images/03_stage3_verify_writeback.png)

A grey-zone candidate goes to a **cheap** LLM call — just the two prompts (incoming +
saved), no context — asking "same meaning? yes/no." This is what makes Stage 3 affordable:
it touches the LLM but skips the context bundle entirely.

Both outcomes converge on the same **write-back**, which is why the cache learns — every
outcome except a served hit leaves the cache richer.

- **Verify call:** two prompts only, tight yes/no, no context
- **Yes:** return the cached intent; add the new phrasing to **both** stores (exact store =
  instant repeats; vector store = thickens the cluster)
- **No:** fall through to the full LLM call
- **Full LLM call (miss):** produces a fresh intent; write it to **both** stores, keyed by
  scope
- **Near-miss recording:** deferred to v2 (a repeated near-miss simply re-runs one cheap
  verify call for now)

---

## 7. Cache-miss path

Two branches reach the full LLM call: a **Stage 2 reject** (`< 0.75`) and a **Stage 3 no**.
Both run the full call (prompt + context → intent) and then use the **same** write-back
logic as a confirmed learn: the fresh intent is stored in **both** stores, keyed by
`module + persona`. Every intent the LLM produces is cached.

---

## 8. Deferred items

- **Context-version stamp (staleness fix).** The context bundle is not frozen — editing
  `context_bundles.yaml` can change the intent a given prompt should produce, but the cache
  will keep serving intents built from the old bundle (silent staleness). The fix is to
  stamp every entry with a **context version**, bump it when the bundle changes, and have
  Stages 1 and 2 ignore or flush stale-version entries. **Noted, not yet built.**
- **Near-miss recording (v2).** Record confirmed "not the same" prompt pairs so the same
  losing pair isn't re-verified each time.
- **Bulk expansion (optional).** Pre-generate paraphrase variants only for known
  high-frequency prompts. The Stage 3 learning loop is preferred for general coverage — it
  captures phrasings users *actually* send, avoiding the bloat and meaning-drift risk of
  speculative expansion.



<!-- ───── merged from: docs/developer/context_bundles.md ───── -->

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
scripts `spire.sh` / `spire.sh` / `SPIRE-PORTS.env`, and the four
`.puml` design sketches.

**When to request it:** a new session that needs repo orientation.
Usually too broad for one focused task.


### `plan` — the master plan, the audit, and the log

**Files:** 10. **Size:** ~437 KB, ~112k tokens.

Contains the master plan (`SPIRE_ROBUSTNESS_EXTENSIBILITY_v3.2.md`),
the Phase 1 audit (`docs/audit/phase-1-audit.md`), the findings log
(`docs/audit/findings-log.md`), the three golden files
(`docs/audit/golden/*.txt`), the Phase 1 session log
(`01_Phase_01_Audit_and_Baseline.md`), the Phase 4 structure file, the
session template, and the Doc B index. The audit, log, and goldens were
added 2026-09-18 — this bundle is now the single request that reproduces
the audit's current state, which is what the handoff says a new window
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

