# Spire

**AI-native natural-language query over Oracle Fusion Cloud (P2P + AR).**

Spire turns a plain-English question about a Fusion Cloud pod into a real,
verifiable answer — through a deterministic Knowledge-Graph pipeline with
exactly two LLM boundaries and a hallucination guard.

Example:

> *"Show me suppliers in the US with no invoices in 6 months but with open
> purchase orders, including the buyer assigned to each."*

---

## How it works

```
prompt
  │
  ▼
[Router + Parser]  ── classify the prompt to its Fusion module(s), then parse
  │  (LLM)            against ONLY that module's scoped context → an Intent.
  │                   Scoping cuts parser tokens ~56% per request.
  ▼
Intent
  │
  ▼
[Planner]  ── reads ──▶  Knowledge Graph (Oracle)
  │   deterministic KG lookup → a Plan (list of tool steps). NO LLM.
  ▼
Plan
  │
  ▼
[Executor] ── calls ──▶  MCP server ── calls ──▶  Oracle Fusion REST API
  │   runs the plan step by step against the live pod. NO LLM.
  ▼
outputs
  │
  ▼
[Synthesizer]  ── local, deterministic rendering of records → answer.
  │              A hallucination guard cross-checks every ID against the
  ▼              executor's source data; invented IDs are rejected.
answer
```

Two LLM boundaries only: the **parser** (words → Intent) and the module
**classifier** in front of it. Planning, execution, and synthesis are
deterministic. The pipeline runs on a LangGraph graph.

A thin HTTP layer exposes the pipeline to a browser UI:

```
   browser  ─►  Streamlit (:8888)  ─►  FastAPI (:8000)  ─►  the pipeline above
```

---

## Quick start

```bash
git clone https://github.com/bhagavansprasad/spire.git
cd spire
python -m venv ~/venv/spire && source ~/venv/spire/bin/activate
pip install -r requirements.txt && pip install -e .

cp personas.example.yaml personas.yaml   # add your Fusion pod + DB creds
python scripts/rebuild_kg.py             # build the Knowledge Graph
```

Then, in **three** terminals — **in this order**:

```bash
# Terminal 1 — MCP server (must be running first; the API connects to it)
python -m spire.mcp_server.server
# Listening on http://127.0.0.1:3333

# Terminal 2 — API server (waits for the MCP server above)
python -m spire.api.server
# Listening on http://0.0.0.0:8000

# Terminal 3 — Streamlit UI (talks to the API above)
spire-ui
# Listening on http://0.0.0.0:8888
```

Open `http://localhost:8888` in a browser. The connection pill in the
top-right corner turns **green** when the UI can reach the API.

To run a prompt from the CLI instead of the UI (no API server needed):

```bash
python scripts/promptkit.py --run --prompt "List all suppliers in India"
```

Full setup, keys, diagnostics, prompt sets, and troubleshooting are in
[`how-to-run.md`](how-to-run.md).

---

## Running the UI

The UI is two processes — a FastAPI backend and a Streamlit frontend — plus
the MCP server they both sit in front of. **The order matters:** each layer
connects to the one below it at startup.

| Layer | Process | Default port | Depends on |
|---|---|---|---|
| MCP server | `python -m spire.mcp_server.server` | `3333` | Oracle, Fusion pod |
| API server | `python -m spire.api.server` | `8000` | MCP server |
| UI | `spire-ui` | `8888` | API server |

Starting them out of order is fine — the API comes up with
`pipeline_ready=false` if it cannot reach the MCP server and reports the
reason on `GET /status`; the UI shows a red **Not connected** pill and the
error text. Restart the missing layer and refresh the browser.

**Configuration** (all optional; defaults match the ports above):

| Env var | Default | Applies to |
|---|---|---|
| `SPIRE_API_HOST` | `0.0.0.0` | API bind address |
| `SPIRE_API_PORT` | `8000` | API port |
| `SPIRE_MCP_URL` | `http://127.0.0.1:3333/mcp` | API → MCP |
| `SPIRE_UI_HOST` | `0.0.0.0` | UI bind address |
| `SPIRE_UI_PORT` | `8888` | UI port |
| `SPIRE_UI_ORIGIN` | `http://localhost:8888` | API CORS allowlist |
| `SPIRE_API_URL` | `http://localhost:8000` | UI → API |
| `SPIRE_UI_TIMEOUT` | `180` | UI → API request timeout (seconds) |

**No authentication.** The API and UI bind `0.0.0.0` with no auth. Fine on a
trusted LAN, wrong for anything reachable from the public internet. Auth is
deferred (Doc A §4.6).

**The API.** Two endpoints:

- `GET /status` — liveness and readiness. `200` when the pipeline is up;
  `503` when it is not, with the reason in the `error` field.
- `POST /prompt` — takes `{"prompt": "..."}`, returns a single JSON envelope.
  Interactive OpenAPI docs at `http://localhost:8000/docs`.

Every response has the same shape:

```json
{
  "request_id": "...",
  "kind": "text | table | refusal | partial | error",
  "answer": { ... },
  "metadata": {
    "latency_ms": 12158,
    "llm_calls": 0,
    "tokens_in": 0,
    "tokens_out": 0,
    "kg_version": null,
    "stages": [
      {"name": "parse",    "ms": 6156},
      {"name": "plan",     "ms": 1540},
      {"name": "execute",  "ms": 4104},
      {"name": "synthesize","ms": 0}
    ]
  }
}
```

`kind` tells the client what shape `answer` has:

- `text` — a plain answer; `records` is empty
- `table` — `records` carries the rows; render as a dataframe
- `refusal` — Spire declined (out of scope, missing argument); `answer.refusal`
  carries `reason` / `solution` / `example`
- `partial` — some steps succeeded, some failed (unreachable today; arrives
  with Phase 2 §8.3.7)
- `error` — the pipeline failed; `answer.error` carries `stage`, `message`,
  `retryable`

---

## Key concepts

- **Knowledge Graph (Oracle):** metadata about Fusion's structure — entities,
  the join fields on each edge, reusable query patterns, business-term
  vocabulary, and which MCP tool fetches what. The planner reads it; there is
  no LLM in planning. Rebuild with `python scripts/rebuild_kg.py`.

- **Router + parser:** a small classifier routes each prompt to its Fusion
  module(s) (payables / procurement / receivables / supplier), and the parser
  runs against only that module's scoped prompt. This removes the parser's
  token-ceiling as a constraint and cuts tokens ~56% per request.

- **Planner / executor:** deterministic. The planner turns an Intent into a
  Plan via KG lookup; the executor runs the plan against the Fusion REST API
  through the MCP tool layer. No LLM in either.

- **Synthesizer:** renders the executor's records into the answer locally
  (no LLM synthesis call), with a guard that rejects any ID not present in the
  source data.

- **API + UI:** a thin FastAPI server (`src/spire/api/`) exposes the pipeline
  over HTTP; a Streamlit page (`src/spire/ui/`) provides a browser interface.
  Both are clients of the pipeline, not part of it — the pipeline behaves
  identically whether it is driven by the CLI, the API, or the UI.

- **promptkit** (`scripts/promptkit.py`): one tool to run a single prompt, run
  a whole prompt set end to end, or validate that prompts still route to the
  right module and tool. See [`how-to-run.md`](how-to-run.md) §5.

---

## Working with prompt sets

`promptkit` has three modes — **generate** a corpus from plain prompts,
**validate** that a corpus still routes correctly, and **run** prompts end to
end against the pod. JSON is the single corpus format.

```bash
# 1. GENERATE — turn a plain-text prompt list into a JSON corpus.
#    Each prompt is run through the router; the chosen module + tool are
#    recorded. The result is a DRAFT — a human curates the module/tool values,
#    because the classifier is non-deterministic (see docs/ findings).
python scripts/promptkit.py --generate scripts/prompts/08_lifecycle.txt

# 2. VALIDATE — check a corpus still routes as recorded (no execution).
#    Pass/fail is decided by the TOOL; a module-set mismatch on a tool-correct
#    prompt is a non-failing "OK*" warning, listed under MODULE WARNINGS.
python scripts/promptkit.py --validate scripts/prompts/08_lifecycle.json
python scripts/promptkit.py --validate scripts/prompts/*.json        # all sets

# 3. RUN — execute end to end against the live pod (full pipeline → answer).
python scripts/promptkit.py --run scripts/prompts/08_lifecycle.json  # a whole set
python scripts/promptkit.py --run --prompt "List all suppliers in India"  # one ad-hoc prompt
```

**Diagnostics** (with `--run` only) show inside the pipeline. The committed
defaults in `pyproject.toml` (`[tool.spire.diagnostics]`) apply; override per
run with any of `--show-parser` (Intent + the routing decision),
`--show-planner` (the Plan / tool), `--show-raw-output`, `--show-synthesizer`,
`--show-tokens`, `--show-timings`, or `--show-all` — and `--no-show-*` to
silence one.

```bash
# ad-hoc run with every stage visible
python scripts/promptkit.py --run --prompt "show suppliers in US" --show-all

# a corpus run, but silence token accounting
python scripts/promptkit.py --run scripts/prompts/01_supplier.json --no-show-tokens
```

The typical loop for a new or changed prompt set is **generate → curate the
JSON → validate → run**. The curation step is manual and load-bearing: a fresh
`--generate` records whatever the classifier emitted that run, so the draft
must be reviewed before it becomes the routing baseline.

---

## Tests

```bash
python -m pytest -q                  # unit + API tests; integration deselected
python -m pytest -q -m integration   # needs MCP server + KG + a provider key
```

The API has two test files:

- `tests/test_api_translate.py` — pure unit tests of `GraphState →
  ResponseEnvelope` (no server needed).
- `tests/test_api_endpoints.py` — integration tests via FastAPI's
  `TestClient`; marked `integration` and deselected from the default run.

Manual UI checklist: `tests/manual/ui/checklist.md`.

---

## License

See [`LICENSE`](LICENSE).