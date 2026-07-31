# How to run Spire

Primary entry point: `scripts/run_graph.py` (the LangGraph pipeline).

Commands below are marked:
- 🔵 **ONE-TIME** — run once during setup
- 🟢 **EVERY TIME** — run each session

---

## 1. Setup

🔵 **ONE-TIME**
```bash
python -m venv ~/venv/spire
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
GEMINI_MODEL = "gemini-2.5-flash"
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

# Terminal 2 — a prompt
python scripts/run_graph.py --prompt "List all suppliers in India"
```

> **Restart the MCP server after ANY change under `src/spire/mcp_server/`.**

Override provider or model for one command:

```bash
SPIRE_LLM_PROVIDER=openai python scripts/run_graph.py --prompt "..."
SPIRE_LLM_MODEL=gemini-2.5-pro python scripts/run_graph.py --prompt "..."
```

Exit codes: `0` ok · `2` node error · `4` refusal (out of scope).

> Don't print a raw exit code next to a refusal in a loop — a screen of
> `exit=4` reads as a screen of crashes.

---

## 4. Diagnostic flags

**Default is quiet.** `stdout` carries the answer; `stderr` carries
everything else.

```bash
python scripts/run_graph.py --prompt "..." 2>/dev/null    # answer alone
```

Identical flags on `run_graph.py` and `run_prompt_set.py`.

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
python scripts/run_graph.py --prompt "..." --show-all --no-show-tokens
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

## 5. Prompt sets

```bash
python scripts/run_prompt_set.py --prompt-file scripts/prompts/00_dipstick.txt
```

| Option | Effect |
|---|---|
| `--prompt-file FILE [FILE ...]` | one or more files, in the order given. Globs work: `scripts/prompts/0*.txt` |
| `--prompts "..." ["..."]` | inline prompts, overriding the set |
| `--all` | every legacy `prompt_set_*.txt` in the **scripts** dir — not `scripts/prompts/`. Mutually exclusive with `--prompt-file`. |

### The sets

Counts are runnable prompts (comments and blanks excluded), measured
2026-07-31.

| File | n | Purpose | Baseline |
|---|---|---|---|
| `00_dipstick.txt` | 6 | depth-ordered triage, fast. **Run first** — the first failure tells you the depth at which the pipeline breaks | — |
| `01_supplier.txt` | 40 | supplier-rooted, incl. paraphrase variety and collision traps | — |
| `02_purchase_order.txt` | 9 | PO-rooted (P2, P3, P3b, P5, P6c) | — |
| `03_ar.txt` | 16 | accounts receivable | — |
| `04_columns.txt` | 8 | column selection — verification set since the feature shipped | — |
| `05_refusals.txt` | 9 | out-of-scope, consolidated. Fast, no pod call. **A refusal is a pass** — what matters is *how* it refuses | 9/9 |
| `06_slow.txt` | 15 | edge filters + aggregations. **Minutes each** — run overnight | — |
| `07_alacarte.txt` | 12 | column-feature regression (table, address flatten, graceful overrun) | 12/12 |
| `08_lifecycle.txt` | 31 | PO lifecycle regression. The five delivery prompts **must answer** — a refusal there is a failure | 31/31 |
| `10_refusal_examples.txt` | 18 | every example Spire promises in a refusal. **All must answer** — a refusal here is a bug in `capability.py` | 18/18 |
| `qa_testcases.txt` | 34 | captured external QA prompts, verbatim, with per-prompt status labels. Not a regression set | — |

Two fast sets worth running first: `00_dipstick` samples the whole
pipeline by depth; `07_alacarte` drills the column-output feature.

> ⚠️ **`scripts/prompts/scorer/parser_stress.txt` is a different format**
> (`EXPECT ||| prompt`) and needs the scorer. Feeding it to
> `run_prompt_set.py` sends `filter:status |||` to the parser as part of
> the prompt. It lives in a subfolder for that reason.

> `scripts/prompts/0*.txt` picks up `00`–`08` but **not** `10` or
> `qa_testcases`.

> `scripts/prompts/README.md` is stale — it predates `08`, `10` and
> `qa_testcases`, and five of its eight counts disagree with the files.

### Reading the results

> **The tally is not a verdict.** `N/N clean` means nothing errored, not
> that the answers are right. `run_prompt_set.py` has reported "38/38 ran
> cleanly" while prompts were being wrongly refused, and `05_refusals`
> once reported 9/9 with three messages wrong.

Score each prompt into pass · fail · **wrong but did not error**. The third
bucket is the one that matters. Check specifically for:

- an empty data array behind confident narrative prose
- a page count stated as a total ("25 suppliers" where 421 exist)
- claims about fields absent from the displayed projection
- arithmetic in the narration that is not in the rows
- customer-scoped results that never resolve an `AccountNumber`
- a generalisation true of the first few rows but not the set

### Batch runs

Full run excluding the slow set:

```bash
for s in 00_dipstick 01_supplier 02_purchase_order 03_ar 04_columns 05_refusals 07_alacarte; do
  echo "########## $s ##########"
  python scripts/run_prompt_set.py --prompt-file scripts/prompts/$s.txt
done 2>&1 | tee run_$(date +%Y%m%d).txt
```

Everything, overnight:

```bash
nohup bash -c '
for s in 00_dipstick 01_supplier 02_purchase_order 03_ar 04_columns 05_refusals 07_alacarte 08_lifecycle 06_slow; do
  echo "########## $s ##########"
  python scripts/run_prompt_set.py --prompt-file scripts/prompts/$s.txt
done' > overnight_$(date +%Y%m%d).txt 2>&1 &
```

The MCP server must stay up for the duration. If it is in a foreground
terminal you plan to close, background it too.

Flag surface regression (only when the flag surface changes):

```bash
bash scripts/flag_matrix.sh      # ~17 min, 67 LLM calls
```

---

## 6. Example prompts

**Return data:**
```bash
python scripts/run_graph.py --prompt "List all suppliers in India"
python scripts/run_graph.py --prompt "US suppliers with no invoices in the last 6 months"
python scripts/run_graph.py --prompt "Suppliers in the US with open purchase orders and no invoices in 6 months, include the buyer"
```

**Aggregation (slow — paginates the full range):**
```bash
python scripts/run_graph.py --prompt "Top 10 suppliers by spend in 2022"
```

**Refused:**
```bash
python scripts/run_graph.py --prompt "Show me contract renewals due next quarter"
python scripts/run_graph.py --prompt "Top 10 suppliers by total spend"     # no date range
```

---

## 7. Tests

```bash
python -m pytest -q                  # 762 passed, 18 deselected, 1 xfailed (~2.5 min)
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

> `run_plan.py` was deprecated and deleted. Use `run_graph.py`.
