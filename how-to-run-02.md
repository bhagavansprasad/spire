# How to run Spire

Primary entry point: `scripts/run_graph.py` (the LangGraph pipeline).
Legacy entry points are at the bottom.

---

## 1. Setup

```bash
python -m venv ~/venv/spire
source ~/venv/spire/bin/activate
pip install -r requirements.txt
pip install -e .
```

**Credentials** — copy the template and fill in real values (gitignored):

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
    password: "<oracle-pass>"
```

**Knowledge Graph** — populate the schema (works local or remote):

```bash
python scripts/rebuild_kg.py
python scripts/print_kg.py        # verify row counts
```

---

## 2. LLM keys

Pick a provider with `SPIRE_LLM_PROVIDER` (default `gemini`). Override
the model with `SPIRE_LLM_MODEL`. Each run prints `[llm] provider=… model=…`.

**Gemini** (default) — either a public API key:

```bash
export GEMINI_API_KEY="..."
```

or Vertex AI (shared project billing):

```bash
export GOOGLE_GENAI_USE_VERTEXAI=TRUE
export GOOGLE_CLOUD_PROJECT=<project-id>
export GOOGLE_CLOUD_LOCATION=us-central1
gcloud auth application-default login
gcloud auth application-default set-quota-project <project-id>
```

**OpenAI** — key from platform.openai.com (needs billing):

```bash
export OPENAI_API_KEY="sk-..."
export SPIRE_LLM_PROVIDER=openai          # default model: gpt-4o
```

**Anthropic** — key from console.anthropic.com (needs billing):

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export SPIRE_LLM_PROVIDER=anthropic       # default model: claude-sonnet-4-6
```

---

## 3. Run

Two terminals.

```bash
# Terminal 1 — MCP server (keep running)
python -m spire.mcp_server.server

# Terminal 2 — a prompt
python scripts/run_graph.py --prompt "List all suppliers in India"
```

Switch provider inline:

```bash
SPIRE_LLM_PROVIDER=openai python scripts/run_graph.py --prompt "..."
SPIRE_LLM_PROVIDER=anthropic SPIRE_LLM_MODEL=claude-opus-4-8 python scripts/run_graph.py --prompt "..."
```

Batch a fixed set:

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

```bash
pytest tests/                  # unit
pytest tests/ -m integration   # needs MCP server + KG + a provider key
```

---

## Troubleshooting

- **`429 / quota / credits depleted`** — provider account out of credit.
  Add billing, or switch provider via `SPIRE_LLM_PROVIDER`.
- **`404 not_found: model ...`** — bad `SPIRE_LLM_MODEL`. Use a current
  ID (Anthropic: `claude-sonnet-4-6`, `claude-opus-4-8`; OpenAI: `gpt-4o`).
- **`DefaultCredentialsError`** — Vertex enabled but no Google login:
  `gcloud auth application-default login` (per user).
- **`ORA-01017`** — wrong DB password in `personas.yaml`.
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
