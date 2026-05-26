# How to run Spire

Two paths are runnable today:

- **Design 3 (recommended)** — KG-driven planner + executor + LLM
  synthesizer. Scores 7/7 on the anchor question.
- **Track A (legacy baseline)** — LangGraph agent + LLM-as-planner.
  Scores 1/7 on the same question. Kept runnable for comparison.

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

2. **Oracle 26ai container** (for the Knowledge Graph). Default
   container name: `oracle26ai_db_bhagavan`. Schema: `SPIRE`. Service:
   `FREEPDB1`. Override with `SPIRE_DB_USER` / `SPIRE_DB_PASSWORD` /
   `SPIRE_DB_DSN` env vars if your setup differs.

3. **Fusion Cloud pod** with READ access to suppliers, invoices,
   purchaseOrders, and HCM publicWorkers.

4. **Gemini API key** for the synthesizer:

   ```bash
   export GEMINI_API_KEY="your-key-here"
   ```

---

## One-time configuration

### Personas (Fusion credentials)

Spire reads pod credentials from `personas.yaml`, which is **gitignored**.
Copy the example file and fill in your real values:

```bash
cp personas.example.yaml personas.yaml
```

Then edit `personas.yaml`:

```yaml
default_dev:
  fusion:
    base_url: "https://<your-pod>.oraclepdemos.com"
    username: "<your-fusion-username>"
    password: "<your-fusion-password>"
    auth_type: "basic"
  oracle:
    dsn: "localhost:1521/FREEPDB1"
    username: "spire"
    password: "<your-oracle-password>"
```

**Security note:** `personas.yaml` is in `.gitignore` and should NEVER
be committed. Do not paste real credentials into commit messages, log
files, or chat tools either.

### Knowledge Graph

Populate the SPIRE schema in Oracle:

```bash
./scripts/rebuild_kg.sh
```

This is idempotent — safe to re-run. It drops + recreates all 8 KG
tables and re-seeds them. Expected verification output at the end:
8 tables, 3 patterns, 3 pattern bindings, ~83 rows total.

---

## Running Design 3 (the recommended path)

Two terminals.

**Terminal 1 — MCP server** (must stay running):

```bash
python -m spire.mcp_server.server
```

Serves on `http://127.0.0.1:3333/mcp/`. The server reads
`personas.yaml` for Fusion credentials.

**Terminal 2 — the pipeline**:

```bash
# Default: full original Track A prompt with negation clause
python scripts/run_plan.py

# Or explicitly:
python scripts/run_plan.py --intent original

# Or the simpler v1 anchor (no negation clause):
python scripts/run_plan.py --intent anchor
```

Expected behavior:
- Prints the parsed Intent
- Generates and prints the 4-step (or 3-step) Plan
- Executes against the live MCP server (~2 minutes for the
  4-step plan; dominated by ~50 sequential Fusion calls)
- Calls Gemini for the synthesizer (~2-5 seconds, ~13s typical)
- Prints the structured response (prose + per-supplier list)
- Writes a trace JSONL to `traces/<timestamp>.jsonl`

Exit codes:
- `0` — success
- `1` — plan generation failed
- `2` — plan execution failed
- `3` — synthesis failed (including hallucination detection)

---

## Running Track A (the legacy baseline)

Track A scores 1/7 on the anchor question; kept runnable for
comparison and historical interest. Same MCP server as Design 3.

```bash
# Terminal 1: MCP server (same as Design 3)
python -m spire.mcp_server.server

# Terminal 2: the LangGraph agent
python scripts/ask.py "Show me suppliers in US with no invoices in 6 months but with open purchase orders, including the buyer assigned to each."
```

Other example prompts the Track A agent was tested against:

```bash
python scripts/ask.py "Show invoices for Lee Supplies after January 2024"
python scripts/ask.py "Find any invoices for Lee Supplies"
python scripts/ask.py "Find open purchase orders for EIP"
python scripts/ask.py "Who is the buyer with ID 300000047340498?"
python scripts/ask.py "Find suppliers in US"
python scripts/ask.py "Find suppliers in the United Kingdom"
python scripts/ask.py "Show all closed purchase orders"
python scripts/ask.py "What tools do you have available?"

# Two-step composition (expected to fail on this path; that's the baseline finding)
python scripts/ask.py "Who is the buyer for Lee Supplies' open POs?"
```

See [`docs/phase_a5_baseline_report.md`](docs/phase_a5_baseline_report.md)
for the formal scoring of Track A against the rubric.

---

## Running the tests

```bash
# Unit tests only (fast, no infrastructure needed)
pytest tests/

# Plus integration tests (requires MCP server running, GEMINI_API_KEY set,
# and Oracle KG populated)
pytest tests/ -m integration
```

Current expected results: **235 passed, 5 deselected** (the 5
integration tests run only with `-m integration`).

---

## Troubleshooting

**`KeyError: No vocab for ...`** — KG schema is empty or stale.
Re-run `./scripts/rebuild_kg.sh`.

**`HallucinationError`** — Synthesizer produced an ID not in the
executor's data. Re-run; the structured part is usually identical
across runs, but Gemini at T=0 is not strictly deterministic.

**`oracledb.exceptions.OperationalError` connecting to Oracle** —
Container probably isn't running. Start it, then re-run.

**MCP `streamablehttp_client` connection errors** — The MCP server
isn't running in Terminal 1, or it's serving on a different port.

**Tests that need `personas.yaml`** automatically skip if it's
missing, so test failures with that file absent are usually
infrastructure issues (Oracle down, MCP down) rather than missing
config.

---

## Where things live

- `scripts/run_plan.py` — Design 3 entry point
- `scripts/ask.py` — Track A entry point
- `scripts/rebuild_kg.sh` — KG rebuild
- `src/spire/planner/planner.py` — deterministic planner
- `src/spire/executor/executor.py` — plan executor
- `src/spire/synthesizer/synthesizer.py` — LLM synthesizer
- `src/spire/mcp_server/` — 5 MCP tools
- `personas.yaml` — credentials (gitignored)
- `traces/` — per-run JSONL traces
- `docs/` — design docs, measurement reports, working log
