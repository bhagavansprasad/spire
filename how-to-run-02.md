# How to run Spire

Two paths are runnable today:

- **Design 3 (recommended)** — KG-driven planner + executor + LLM
  synthesizer. Scores 7/7 on the anchor question.
- **Track A (legacy baseline)** — LangGraph agent + LLM-as-planner.
  Scores 1/7 on the same question. Kept runnable for comparison; cleared
  for removal.

---

## Prerequisites

1. **Python 3.12+** with a virtual environment

   ```bash
   python -m venv ~/venv/spire
   source ~/venv/spire/bin/activate
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   pip install -e .
   ```

2. **Oracle 26ai** (for the Knowledge Graph), reachable either as a
   local container or over the network. Credentials come from
   `personas.yaml` (see below); env vars
   `SPIRE_DB_USER` / `SPIRE_DB_PASSWORD` / `SPIRE_DB_DSN` override it for
   CI or ad-hoc runs.

3. **Fusion Cloud pod** with READ access to suppliers, invoices,
   purchaseOrders, and HCM publicWorkers.

4. **Gemini access** for the parser and synthesizer. Two modes:

   **a) Public Gemini API** — a single key:

   ```bash
   export GEMINI_API_KEY="your-key-here"
   ```

   **b) Vertex AI** — routes calls through a Google Cloud project
   (use this when the public key's prepay credits are depleted, or to
   share a project's billing across users). Set:

   ```bash
   export GOOGLE_GENAI_USE_VERTEXAI=TRUE
   export GOOGLE_CLOUD_PROJECT=<your-project-id>
   export GOOGLE_CLOUD_LOCATION=us-central1
   export VERTEXAI_PROJECT_ID=<your-project-id>
   export VERTEXAI_LOCATION=us-central1
   ```

   Vertex also needs Google credentials (not just the env vars):

   ```bash
   gcloud auth application-default login
   gcloud auth application-default set-quota-project <your-project-id>
   ```

   When `GOOGLE_GENAI_USE_VERTEXAI=TRUE` is set, the API key is ignored
   and all calls go through Vertex. Each user on a shared machine needs
   their own `gcloud auth application-default login`.

   The model is centralized in `src/spire/config.py`
   (`GEMINI_MODEL`, currently `gemini-2.5-pro`).

---

## One-time configuration

### Personas and credentials

Spire reads both Fusion and Oracle credentials from `personas.yaml`,
which is **gitignored**. It is the single place DB credentials live.
Copy the example and fill in real values:

```bash
cp personas.example.yaml personas.yaml
```

```yaml
default_dev:
  fusion:
    base_url: "https://<your-pod>.oraclepdemos.com"
    username: "<your-fusion-username>"
    password: "<your-fusion-password>"
    auth_type: "basic"
  oracle:
    dsn: "localhost:1521/FREEPDB1"   # or host:port/service for a remote DB
    username: "spire"
    password: "<your-oracle-password>"
```

There is no hardcoded DB password anywhere in the code: if neither
`personas.yaml` nor the `SPIRE_DB_*` env vars supply a username and
password, the KG connection fails with a clear error.

**Security note:** `personas.yaml` is in `.gitignore` and must NEVER be
committed. Do not paste real credentials into commit messages, logs, or
chat tools.

### Knowledge Graph

Populate the SPIRE schema. Two options:

**Python (recommended) — works local or remote, no docker/sqlplus:**

```bash
python scripts/rebuild_kg.py
```

Connects over the network using the credentials above, runs all schema
statements, and commits. Use `--quiet` to suppress per-statement echo.

**Shell (local container only):** runs `sqlplus` inside a named
container; pass the container name as the first argument:

```bash
./scripts/rebuild_kg.sh <container-name>     # e.g. oracle26ai_db_spire
```

Both are idempotent — they drop and recreate the 8 KG tables and
re-seed them. Verify with:

```bash
python scripts/print_kg.py
```

Expected: kg_entity 5, kg_entity_field 27, kg_edge 4, kg_pattern 3,
kg_vocabulary 42, kg_pattern_binding 3, kg_entity_tool 2, kg_edge_tool 3.

You can also smoke-test the DB connection alone:

```bash
python scripts/test_kg_connection.py
```

---

## Running Design 3 (the recommended path)

Two terminals.

**Terminal 1 — MCP server** (must stay running):

```bash
python -m spire.mcp_server.server
```

Serves on `http://127.0.0.1:3333/mcp/`. Reads `personas.yaml` for Fusion
credentials.

**Terminal 2 — the pipeline** (natural-language prompt):

```bash
python scripts/run_plan.py --prompt "Show me suppliers in US"
python scripts/run_plan.py --prompt "Top 10 suppliers by spend in 2022"
```

What it does: parses the prompt to an Intent, generates and prints the
Plan, executes against the live MCP server, calls Gemini for the
synthesizer, prints the structured answer, and writes a trace JSONL to
`traces/<timestamp>.jsonl`.

Exit codes:
- `0` — success
- `1` — plan generation failed
- `2` — plan execution failed
- `3` — synthesis failed (including hallucination detection)
- `4` — graceful refusal (prompt out of scope)

### Aggregation prompts

Ranking/total prompts route to a bounded aggregation tool
(`aggregate_invoices_by_supplier`), e.g. "top 10 suppliers by spend in
2022" or "which suppliers did we spend the most with last year". The
tool paginates the full date range, so wide ranges take longer
(sequential Fusion calls); page progress is reported back to the caller
as it runs.

### Running a batch of prompts

```bash
python scripts/run_prompt_set.py
```

Runs a fixed mixed set (aggregation, list, refusal) through the live
pipeline in one process. `--prompts "..." "..."` overrides the set.

---

## Running Track A (the legacy baseline)

Track A scores 1/7 on the anchor question; kept runnable for comparison.
Cleared for removal. Same MCP server as Design 3.

```bash
# Terminal 1: MCP server (same as Design 3)
python -m spire.mcp_server.server

# Terminal 2: the LangGraph agent
python scripts/ask.py "Show invoices for Lee Supplies after January 2024"
```

---

## Running the tests

```bash
# Unit tests only (fast, no infrastructure needed)
pytest tests/

# Integration tests (require MCP server running, GEMINI_API_KEY set,
# and Oracle KG populated)
pytest tests/ -m integration
```

---

## Troubleshooting

**`429 RESOURCE_EXHAUSTED` / "prepayment credits are depleted"** — the
public Gemini API key is out of credit. Switch to Vertex AI (set the
`GOOGLE_GENAI_USE_VERTEXAI=TRUE` block above), or use a key with credit.
Note: if Vertex is *not* enabled, the SDK uses the API key even when env
vars look set.

**`DefaultCredentialsError: Your default credentials were not found`** —
Vertex is enabled but Google credentials aren't set up for this user.
Run `gcloud auth application-default login`. On a shared machine each
user needs to do this for their own account.

**`UserWarning: ... without a quota project`** — harmless, but clear it
with `gcloud auth application-default set-quota-project <project-id>`.

### Fixing Google config via the Cloud Console

Some issues are resolved in the browser at https://console.cloud.google.com
(select the right project first, e.g. `bhagavangenai-444212`):

- **Out of API credits / billing (429):** manage the public Gemini API
  key and its credits in AI Studio (https://ai.studio). For Vertex,
  Console → Billing → confirm a billing account is linked to the project.
- **"API not enabled" on Vertex calls:** Console → APIs & Services →
  Library → search "Vertex AI API" → Enable.
- **Give another user Vertex access** (so they don't borrow someone
  else's credentials): Console → IAM & Admin → IAM → Grant Access → add
  the user's Google email → roles `Vertex AI User` and
  `Service Usage Consumer`. The user then runs their own
  `gcloud auth application-default login`.
- **Quota project (console equivalent of the warning above):** ensure
  the user has `Service Usage Consumer` on the project.

**`ORA-01017: invalid credential`** — the DB password in
`personas.yaml` (or `SPIRE_DB_PASSWORD`) doesn't match the database.
Fix it in `personas.yaml`.

**`No Oracle DB credentials` (RuntimeError)** — neither `personas.yaml`
nor the `SPIRE_DB_*` env vars supplied a username/password.

**`KeyError: No vocab for ...`** — KG schema is empty or stale. Re-run
`python scripts/rebuild_kg.py`.

**`HallucinationError`** — synthesizer produced an ID not in the
executor's data. Re-run; the structured part is usually identical across
runs, but Gemini at T=0 is not strictly deterministic.

**`oracledb` connection errors** — the database isn't reachable. For a
local container, confirm it's running; for a remote DB, check the DSN
host/port in `personas.yaml`.

**MCP connection errors** — the MCP server isn't running in Terminal 1,
or it's on a different port.

**Tests needing `personas.yaml`** skip automatically if it's missing, so
failures with that file absent are usually infrastructure issues (DB
down, MCP down) rather than missing config.
