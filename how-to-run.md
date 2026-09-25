# How to run Spire

Primary entry point: **`scripts/promptkit.py`** — one tool that runs a single
prompt, runs a whole prompt set end to end, or validates routing (§5).

Commands below are marked:
- 🔵 **ONE-TIME** — run once during setup
- 🟢 **EVERY TIME** — run each session

---

## 1. Setup

🔵 **ONE-TIME**
```bash


source ~/venv/spire/bin/activate
pip install -r requirements.txt
pip install -e .
```

> `pip install -e .` is required — code lives under `src/spire/`, not the
> project root. Without it: `ModuleNotFoundError: No module named 'spire'`.

**Credentials**

🔵 **ONE-TIME**
```bash
cp personas.example.yaml personas.yaml
```

```yaml
default_dev:
  fusion:
    base_url: "https://<your-pod>.oraclepdemos.com"
    username: "<fusion-user>"
    password: "<fusion-pass>"
    auth_type: "basic"
  oracle:
    dsn: "localhost:1521/FREEPDB1"
    username: "spire"
    password: "<db-pass>"
```

> ⚠️ **`personas.yaml` is the single source for all pod and DB
> credentials. Update it whenever a password, pod URL or DB user
> changes** — a rotated Fusion password or a rebuilt DB container will
> otherwise fail at the first call with `ORA-01017` or a 401, with
> nothing else changed. It is gitignored, so nobody else's copy updates
> with yours.

**Create the Oracle DB user:**

🔵 **ONE-TIME**
```bash
docker exec -i oracle26ai_db sqlplus sys/Abcd1234@localhost:1521/FREEPDB1 as sysdba <<'EOF'
CREATE USER spire IDENTIFIED BY "<db-pass>";
GRANT CONNECT, RESOURCE, CREATE VIEW, UNLIMITED TABLESPACE TO spire;
EXIT;
EOF
```

> Use `sys ... as sysdba`, not `pdbadmin` (`ORA-01031` on this image).
> `IDENTIFIED BY` must match `oracle.password` in `personas.yaml`.

---

## 2. LLM keys

Provider via `SPIRE_LLM_PROVIDER` (default `gemini`), model via
`SPIRE_LLM_MODEL`. Each run prints `[llm] provider=… model=…`.

Defaults live in `src/spire/config.py`:

```python
GEMINI_MODEL = "gemini-3.5-flash"
ANTHROPIC_MODEL = "claude-sonnet-4-6"
OPENAI_MODEL = "gpt-5"
```

> `2.5-flash` not `2.5-pro`: a fresh `GEMINI_API_KEY` commonly has a
> **0 free-tier quota** for `2.5-pro` (`429 RESOURCE_EXHAUSTED, limit: 0`).

**Gemini** — public API key:

🔵 **ONE-TIME per machine**
```bash
export GEMINI_API_KEY="..."
```

or Vertex AI:

```bash
export GOOGLE_GENAI_USE_VERTEXAI=TRUE
export GOOGLE_CLOUD_PROJECT=<project-id>
export GOOGLE_CLOUD_LOCATION=us-central1
gcloud auth application-default login
gcloud auth application-default set-quota-project <project-id>
```

**OpenAI**
```bash
export OPENAI_API_KEY="sk-..."
export SPIRE_LLM_PROVIDER=openai
```

**Anthropic**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export SPIRE_LLM_PROVIDER=anthropic
```

> To change a default permanently, edit the constant in `config.py` —
> one file, one place.

---

## 3. Run

🟢 **EVERY TIME** — environment. These must match `personas.yaml`; if you
change credentials, change both:
```bash
export IKS_FUSION_BASE_URL="https://fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com"
export IKS_FUSION_USERNAME="<fusion-user>"
export IKS_FUSION_PASSWORD="<fusion-pass>"
```

🟢 **EVERY TIME** — Knowledge Graph. Always rebuilt from scratch, never
incrementally:
```bash
python scripts/rebuild_kg.py
```

Optional checks:
```bash
python scripts/print_kg.py
python scripts/print_kg.py --counts-only
```

Two terminals:

```bash
# Terminal 1 — MCP server (keep running)
python -m spire.mcp_server.server

# Terminal 2 — a single prompt (end to end)
python scripts/promptkit.py --run --prompt "List all suppliers in India"
```

> **Restart the MCP server after ANY change under `src/spire/mcp_server/`.**

Override provider or model for one command:

```bash
SPIRE_LLM_PROVIDER=openai python scripts/promptkit.py --run --prompt "..."
SPIRE_LLM_MODEL=gemini-2.5-pro python scripts/promptkit.py --run --prompt "..."
```

Exit codes: `0` ok · `2` node error · `4` refusal (out of scope).

> Don't print a raw exit code next to a refusal in a loop — a screen of
> `exit=4` reads as a screen of crashes.

---

## 4. Diagnostic flags

**Default is quiet.** `stdout` carries the answer; `stderr` carries
everything else.

```bash
python scripts/promptkit.py --run --prompt "..." 2>/dev/null    # answer alone
```

The flags apply to `promptkit.py --run` (a single `--prompt` or a `.json` corpus). The committed `pyproject.toml` defaults apply too.

| Flag | Shows |
|---|---|
| `--show-parser` | parsed intent, KG menu size, refusal detail |
| `--show-planner` | selected plan, tool, arguments, filters |
| `--show-raw-output` | executor output per step |
| `--show-synthesizer` | response object prior to rendering |
| `--show-tokens` | per-call and end-of-run token counts |
| `--show-timings` | per-stage latency |
| `--show-all` | enable every flag above |

Every flag except `--show-all` has a `--no-` twin:

```bash
python scripts/promptkit.py --run --prompt "..." --show-all --no-show-tokens
```

Progress lines and the summary footer are **never gated** — both on
`stderr`, so `stdout` is unaffected.

The root logger is never touched (langchain, httpx, oracledb and fastmcp
all log at DEBUG).

### Precedence

Later beats earlier:

```
defaults  →  pyproject.toml  →  environment  →  command line
```

Committed default:

```toml
[tool.spire.diagnostics]
show_planner = true
```

Per-machine default:

```bash
export SPIRE_SHOW_PLANNER=1
```

Invalid flag names are reported, not silently ignored.

> `show_all = true` is a **no-op** in a file that already spells out every
> key. Set the individual keys, or use `--show-all` on the CLI.

---

## 5. Prompt sets with promptkit

`scripts/promptkit.py` is the single tool for prompt sets. **JSON** is the one
format; pick exactly one action:

| Action | Input | What it does |
|---|---|---|
| `--generate` | plain `.txt` (one prompt per line) | run each prompt through the router; write a `.json` beside it — each entry `{prompt, module, tool, note}`, the router's ACTUAL choices |
| `--validate` | `.json` | check every prompt still routes to its recorded module + tool. **No execution** — fast |
| `--run` | `.json` | execute each prompt end to end against Fusion AND re-check routing, reporting **which stage** fails (module → intent → tool → plan → execute) |
| `--run --prompt "..."` | — | run one ad-hoc prompt end to end |

Multiple files are accepted per action.

**The JSON format** (one entry per prompt):

```json
{ "prompt": "which vendors are in the US",
  "module": ["supplier"],
  "tool": "search_suppliers",
  "note": "" }
```

- `module` is a list (empty `[]` = nothing matched, i.e. out of scope).
- `tool` is a tool name, `"refuse"` (clean refusal), or `"error"` (a crash).
- `note` is empty on success; carries the reason on refuse/error.

### Generate a corpus (`.txt` -> `.json`)

Write prompts one per line in a `.txt`, then let the router fill in the labels:

```bash
python scripts/promptkit.py --generate prompts/supplier/smoke.txt
# writes prompts/supplier/smoke.json — REVIEW the module/tool it captured
```

Generate several at once:

```bash
find prompts -name '*.txt' -print0 | xargs -0 python scripts/promptkit.py --generate
```

### Validate routing (fast, no pod)

```bash
python scripts/promptkit.py --validate prompts/supplier/smoke.json
```

A mismatch means the router now routes a prompt differently than the corpus
recorded — a regression to investigate. Deterministic; no MCP server needed.

### Run end to end (with per-stage failure isolation)

The point of the corpus: run every prompt for real and see *where* a failing
one breaks.

```bash
# MCP server must be up (§3)
python scripts/promptkit.py --run --prompt-file prompts/supplier/smoke.txt
```

Each prompt prints its intent, plan, and answer (like a single run), then the
staged check:

```
------------------------------------------------------------------------
PROMPT: which vendors are in the US
------------------------------------------------------------------------
Intent: ...
Plan: ...
Answer: ...
    module   OK   (['supplier'])
    intent   OK   (Supplier)
    tool     OK   (search_suppliers)
    plan     OK   (1 step(s))
    execute  OK   (25 record(s))
  => PASS: 25 record(s)
```

A failing prompt reports the exact stage — `FAILED AT: planning`,
`FAILED AT: module`, etc. — so you know whether the break is in routing,
intent, tool selection, planning, or the Fusion call, without tracing by hand.
`--run` honours the diagnostics flags (§4) and `pyproject.toml`.

### Overnight runs (all sets, unattended)

`scripts/promptkit_overnight.py` runs promptkit over every set in a manifest,
doing all three phases per set — **generate → validate → run** — one after
another. Each set runs as a separate subprocess with a per-phase timeout, so one
hung or crashing set cannot stop the batch. Built for an unattended run: the
results are there to read in the morning.

The manifest `scripts/manifests/promptkit_sets.yaml` is a top-level `sets:` list of set
names (each resolves to `prompts/<name>.txt` and `<name>.json`). Comment
a line out to skip it; the slow sets (`06_slow`, `08_lifecycle`) are commented
out by default.

**Quick dry run** — generate + validate only, no pod, to confirm it works:

```bash
python scripts/promptkit_overnight.py --skip-run
```

**Full overnight run** — all three phases, end to end. The MCP server must be up
(§3); background it so you can close the terminal:

```bash
# Terminal 1: MCP server running (and backgrounded if you'll close the shell)
nohup python scripts/promptkit_overnight.py \
  > promptkit_overnight_$(date +%Y%m%d).log 2>&1 &
```

**Output** lands in `promptkit_<YYYYMMDD>/`:

```
<name>.txt      full generate + validate + run output for that set
_run_log.txt    one line per set/phase: start, end, duration, exit code
_summary.txt    a compact table (per set/phase: exit code, seconds, status)
```

Read `_summary.txt` first, then open the per-set `.txt` for anything that
errored or looks wrong. Remember the tally is not a verdict (below).

**Useful flags:**

| Flag | Effect |
|---|---|
| `--skip-run` | generate + validate only (fast, no pod) |
| `--skip-generate` | reuse existing `.json`, don't regenerate |
| `--timeout N` | per-phase timeout in seconds (default 3600) |
| `--manifest FILE` / `--outdir DIR` | override the manifest or output dir |

> Exit code per phase: `0` completed · `124` timed out (partial output saved) ·
> other errored (see the set's `.txt`). A non-zero from any phase makes the
> whole run exit non-zero, so an automated caller can tell.

### Reading the results

> **A green tally is not a verdict.** "N/N passed" means nothing errored and
> routing matched the corpus — NOT that every answer is correct. Score each
> prompt into pass / fail / **wrong but did not error**. The third bucket is
> the one that matters. Check specifically for:

- an empty data array behind confident narrative prose
- a page count stated as a total ("25 suppliers" where 421 exist)
- claims about fields absent from the displayed projection
- arithmetic in the narration that is not in the rows
- customer-scoped results that never resolve an `AccountNumber`
- a generalisation true of the first few rows but not the set

### The prompt files

Plain prompt files live in `prompts/` (one prompt per line, `#`
comments). Run `--generate` on them to produce the matching `.json` corpora,
then `--validate` / `--run`. Full inventory in `docs/prompt-sets/SURFACE.md`.

| Path | Purpose |
|---|---|
| `prompts/dipstick/smoke.txt` | depth-ordered triage. **Run first** |
| `prompts/supplier/` | supplier module — smoke / verify / exhaust |
| `prompts/payables/` | payables module |
| `prompts/procurement/` | procurement module |
| `prompts/receivables/` | receivables module |
| `prompts/payables_supplier/` (etc.) | cross-module capabilities, top-level folders |
| `prompts/refusals/smoke.txt` | out-of-scope. **A refusal is a pass** |
| `prompts/columns/verify.txt` | column selection |
| `prompts/sme/testcases.txt` | external QA corpus, verbatim |

> `prompts/scorer/` holds parser-scorer corpora in a different format
> (`EXPECT ||| prompt`) — not for promptkit.

### After you pull

Already set up, just pulled the latest? The KG can change between versions —
rebuild it, confirm counts, then re-validate routing:

```bash
git pull
pip install -e .                       # only if deps changed; harmless otherwise
python scripts/rebuild_kg.py           # always from scratch
python scripts/print_kg.py --counts-only   # all tables should report ok
python scripts/promptkit.py --validate prompts/supplier/smoke.json   # routing still holds?
```

## 6. Example prompts

**Return data:**
```bash
python scripts/promptkit.py --run --prompt "List all suppliers in India"
python scripts/promptkit.py --run --prompt "US suppliers with no invoices in the last 6 months"
python scripts/promptkit.py --run --prompt "Suppliers in the US with open purchase orders and no invoices in 6 months, include the buyer"
```

**Aggregation (slow — paginates the full range):**
```bash
python scripts/promptkit.py --run --prompt "Top 10 suppliers by spend in 2022"
```

**Refused:**
```bash
python scripts/promptkit.py --run --prompt "Show me contract renewals due next quarter"
python scripts/promptkit.py --run --prompt "Top 10 suppliers by total spend"     # no date range
```

---

## 7. Tests

```bash
python -m pytest -q                  # 886 passed, 18 deselected (~3.5 min)
python -m pytest -q -m integration   # needs MCP server + KG + a provider key
```

> The 18 deselections are deliberate — `addopts = "-m 'not integration'"`
> in `pyproject.toml`. If that count changes unexpectedly, something in
> `pyproject.toml` was overwritten.

---

## Troubleshooting

- **`ModuleNotFoundError: No module named 'spire'`** — `pip install -e .`
- **`ORA-01017`** — wrong DB password in `personas.yaml`, or the `spire`
  user doesn't exist (§1).
- **`ORA-01031`** creating the user — use `sys ... as sysdba`.
- **`401` from the pod** — Fusion password rotated; update `personas.yaml`
  and the `IKS_FUSION_*` exports.
- **`429 RESOURCE_EXHAUSTED` / `limit: 0`** — zero free-tier quota for
  that model. Use `gemini-2.5-flash` or switch provider.
- **`429 / credits depleted`** — provider out of credit.
- **`404 not_found: model ...`** — bad `SPIRE_LLM_MODEL`.
- **`DefaultCredentialsError`** — `gcloud auth application-default login`.
- **`No Oracle DB credentials`** — `personas.yaml` oracle block missing
  and no `SPIRE_DB_*` env vars.
- **MCP connection errors** — server not running, or not restarted after
  an `mcp_server/` change.
- **Diagnostics print above the answer when piped** — fixed;
  `diagnostics.answer()` flushes.
- **A whole set refuses with a short entity list** — the KG is stale
  relative to the code. Run `scripts/rebuild_kg.py` before reading
  anything into the results.

---

## Legacy

```bash
# ask.py — Track A LangGraph agent (1/7 baseline; cleared for removal)
python scripts/ask.py "Show invoices for Lee Supplies after January 2024"
```

> `run_plan.py` was deprecated and deleted. `run_graph.py` still exists but
> `promptkit.py --run --prompt "..."` is the current single-prompt entry point
> (same pipeline, same diagnostics, plus corpus support).
