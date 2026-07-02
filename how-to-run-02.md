# How to run Spire

Primary entry point: `scripts/run_graph.py` (the LangGraph pipeline).
Legacy entry points are at the bottom.

Commands below are marked:
- 🔵 **ONE-TIME** — run once during setup, not needed again
- 🟢 **EVERY TIME** — run each session / each time you work

---

## 1. Setup

🔵 **ONE-TIME**
```bash
python -m venv ~/venv/spire
source ~/venv/spire/bin/activate
pip install -r requirements.txt
pip install -e .
```

> `pip install -e .` installs the `spire` package in editable mode.
> Without it, scripts fail with `ModuleNotFoundError: No module named
> 'spire'` since the code lives under `src/spire/`, not at the project
> root.

**Credentials** — copy the template and fill in real values (gitignored):

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
    dsn: "localhost:1521/FREEPDB1"   # or host:port/service for remote
    username: "spire"
    password: "jnjnuh"
```

**Create the Oracle DB user** — the `oracle` block above assumes a `spire`
database user already exists in `FREEPDB1`. On a fresh Oracle container
it doesn't (only `SYS`/`SYSTEM`/`PDBADMIN` exist).

🔵 **ONE-TIME**
```bash
docker exec -i oracle26ai_db sqlplus sys/Abcd1234@localhost:1521/FREEPDB1 as sysdba <<'EOF'
CREATE USER spire IDENTIFIED BY "jnjnuh";
GRANT CONNECT, RESOURCE, CREATE VIEW, UNLIMITED TABLESPACE TO spire;
EXIT;
EOF
```

> Use `sys ... as sysdba`, not `pdbadmin` — `pdbadmin` can fail with
> `ORA-01031: insufficient privileges` on `CREATE USER`/`GRANT` in this
> image. The password in `IDENTIFIED BY` must match `oracle.password`
> in `personas.yaml` exactly.

**Knowledge Graph** — populate the schema (works local or remote):

🔵 **ONE-TIME** (safe to re-run any time the schema needs a reset)
```bash
python scripts/rebuild_kg.py
python scripts/print_kg.py        # verify row counts
```

---

## 2. LLM keys

Pick a provider with `SPIRE_LLM_PROVIDER` (default `gemini`). Override
the model with `SPIRE_LLM_MODEL`. Each run prints `[llm] provider=… model=…`.

The default model per provider is set once in `src/spire/config.py`:

```python
GEMINI_MODEL = "gemini-2.5-flash"   # default when SPIRE_LLM_MODEL is unset
ANTHROPIC_MODEL = "claude-sonnet-4-6"
OPENAI_MODEL = "gpt-5"
```

> `gemini-2.5-flash` is the default here (not `gemini-2.5-pro`) because a
> fresh `GEMINI_API_KEY` commonly has a **0 free-tier quota for
> `gemini-2.5-pro`**, failing immediately with `429 RESOURCE_EXHAUSTED
> ... limit: 0`. If you have billing enabled and want `2.5-pro`, change
> the constant in `config.py`, or override per-run with
> `SPIRE_LLM_MODEL=gemini-2.5-pro`.

**Gemini** (default) — either a public API key:

🔵 **ONE-TIME per machine** (add to your shell profile if you want it permanent, otherwise export per session)
```bash
export GEMINI_API_KEY="..."
```

or Vertex AI (shared project billing):

🔵 **ONE-TIME per machine**
```bash
export GOOGLE_GENAI_USE_VERTEXAI=TRUE
export GOOGLE_CLOUD_PROJECT=<project-id>
export GOOGLE_CLOUD_LOCATION=us-central1
gcloud auth application-default login
gcloud auth application-default set-quota-project <project-id>
```

**OpenAI** — key from platform.openai.com (needs billing):

🔵 **ONE-TIME per machine**
```bash
export OPENAI_API_KEY="sk-..."
export SPIRE_LLM_PROVIDER=openai          # default model: gpt-5
```

**Anthropic** — key from console.anthropic.com (needs billing):

🔵 **ONE-TIME per machine**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export SPIRE_LLM_PROVIDER=anthropic       # default model: claude-sonnet-4-6
```

> **Changing defaults permanently, without `.env` or `~/.bashrc`:**
> edit the constants directly in `src/spire/config.py`
> (`GEMINI_MODEL`, `ANTHROPIC_MODEL`, `OPENAI_MODEL`, or `LLM_PROVIDER`'s
> fallback string). Since `config.py` is the single source of truth the
> file already documents, this avoids scattering config across env files
> and shell profiles — one file, one place to change the default.

---

## 3. Run

Two terminals.

🟢 **EVERY TIME**
```bash
# Terminal 1 — MCP server (keep running)
python -m spire.mcp_server.server

# Terminal 2 — a prompt
python scripts/run_graph.py --prompt "List all suppliers in India"
```

With the `config.py` default now set to `gemini-2.5-flash`, no
`SPIRE_LLM_MODEL` prefix is needed for normal runs.

Switch provider or model inline (optional, overrides `config.py` for
just this one command):

```bash
SPIRE_LLM_PROVIDER=openai python scripts/run_graph.py --prompt "..."
SPIRE_LLM_PROVIDER=anthropic SPIRE_LLM_MODEL=claude-opus-4-8 python scripts/run_graph.py --prompt "..."
SPIRE_LLM_MODEL=gemini-2.5-pro python scripts/run_graph.py --prompt "..."
```

Batch a fixed set:

🟢 **EVERY TIME**
```bash
python scripts/run_prompt_set.py
```

Exit codes: `0` ok · `2` node error · `4` refusal (out of scope).

---

## 4. Example prompts

**Supported — return data:**

```bash
python scripts/run_graph.py --prompt "List all suppliers in India"
python scripts/run_graph.py --prompt "Show me suppliers in the United Kingdom"
python scripts/run_graph.py --prompt "US suppliers with no invoices in the last 6 months"
python scripts/run_graph.py --prompt "Suppliers in the US with open purchase orders and no invoices in 6 months, include the buyer"
```

**Aggregation (slow — paginates the full range):**

```bash
python scripts/run_graph.py --prompt "Top 10 suppliers by spend in 2022"
python scripts/run_graph.py --prompt "Which suppliers did we spend the most with in 2022"
```

**Refused (out of scope — Supplier is the only target entity):**

```bash
python scripts/run_graph.py --prompt "Show me invoices for supplier 1252"
python scripts/run_graph.py --prompt "Show me contract renewals due next quarter"
python scripts/run_graph.py --prompt "Top 10 suppliers by total spend"     # no date range
```

---

## 5. Tests

🟢 **EVERY TIME** (whenever you want to verify things still work)
```bash
pytest tests/                  # unit
pytest tests/ -m integration   # needs MCP server + KG + a provider key
```

---

## Troubleshooting

- **`ModuleNotFoundError: No module named 'spire'`** — run `pip install -e .`
  from the project root.
- **`ORA-01017`** — wrong DB password in `personas.yaml`, or the `spire`
  DB user hasn't been created yet (see the `CREATE USER` step in Section 1).
- **`ORA-01031: insufficient privileges`** (while creating the `spire`
  user) — use `sys ... as sysdba` instead of `pdbadmin`.
- **`429 RESOURCE_EXHAUSTED` / `limit: 0` (Gemini)** — free-tier quota
  for that model is zero. `config.py` now defaults to
  `gemini-2.5-flash`, which usually has a working free quota; if you
  still hit this, try a different provider via `SPIRE_LLM_PROVIDER`.
- **`429 / quota / credits depleted`** (other providers) — provider
  account out of credit. Add billing, or switch provider via
  `SPIRE_LLM_PROVIDER`.
- **`404 not_found: model ...`** — bad `SPIRE_LLM_MODEL`. Use a current
  ID (Anthropic: `claude-sonnet-4-6`, `claude-opus-4-8`; OpenAI: `gpt-5`).
- **`DefaultCredentialsError`** — Vertex enabled but no Google login:
  `gcloud auth application-default login` (per user).
- **`No Oracle DB credentials`** — `personas.yaml` oracle block missing
  and no `SPIRE_DB_*` env vars.
- **MCP connection errors** — server not running in Terminal 1.

---

## Legacy ways of running

Both still work; not recommended. Same MCP server as above.

```bash
# run_plan.py — imperative version of the same pipeline
python scripts/run_plan.py --prompt "Show me suppliers in US"

# ask.py — Track A LangGraph agent (1/7 baseline; cleared for removal)
python scripts/ask.py "Show invoices for Lee Supplies after January 2024"
```