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

- **promptkit** (`scripts/promptkit.py`): one tool to run Spire prompts end to
  end — a single prompt, a file of prompts, or a whole manifest of prompt sets
  under a per-set timeout. See [`docs/prompt-sets/SURFACE.md`](docs/prompt-sets/SURFACE.md)
  for the set inventory and examples.

---

## Working with prompt sets

`promptkit` runs prompts end to end against the pod — through the full
pipeline, from router to synthesizer. Three ways to feed it: one or more
prompt strings, one or more prompt files, or one or more manifest files. All
three are under `--run`, and only one of the three per invocation.

```bash
# ONE PROMPT — the full pipeline, answer to stdout
python scripts/promptkit.py --run --prompt "List all suppliers in India"

# MULTIPLE PROMPTS — space-separated, each run in turn
python scripts/promptkit.py --run --prompt \
    "Suppliers with their addresses" \
    "active suppliers in US"

# A FILE OF PROMPTS — one prompt per line; '#'/blank skipped
python scripts/promptkit.py --run --prompt-file prompts/supplier/supplier_smoke.txt

# MULTIPLE PROMPT FILES — files run in order, prompts in line order
python scripts/promptkit.py --run --prompt-file \
    prompts/dipstick/dipstick_smoke.txt \
    prompts/supplier/supplier_smoke.txt

# A MANIFEST — a YAML 'sets:' list; each set is its own subprocess with a
# per-set timeout, so one hung set cannot stop the batch
python scripts/promptkit.py --run --manifest scripts/manifests/promptkit_sets.yaml

# MULTIPLE MANIFESTS — each gets a <stem>/ subfolder under --outdir
python scripts/promptkit.py --run --manifest \
    scripts/manifests/promptkit_sets.yaml \
    smoke.yaml \
    --outdir results/tonight
```

A **prompt file** is plain text, one prompt per line. A **manifest** is a
YAML file with a top-level `sets:` list of set names; each name resolves to
`<prompts-dir>/<name>.txt` (default `prompts/`). Comment a line out
to skip a set. `scripts/manifests/promptkit_sets.yaml` is the committed manifest.

**Manifest output.** Each set writes its own file; the run also writes a log
and a summary. Default outdir is `promptkit_<YYYYMMDD_HHMMSS>/` in the cwd,
or `--outdir` if given:

```
promptkit_20260922_165958/
    00_dipstick.txt      per-set stdout, one file per set
    01_supplier.txt
    ...
    _run_log.txt         start/end/exit/duration, one line per set
    _summary.txt         a compact table
```

`--timeout` (default `3600` seconds) applies per set. `--prompts-dir` changes
where set names resolve. A single manifest writes flat into `--outdir`;
multiple manifests each get a `<stem>/` subfolder so set names can't collide
between them.

**Diagnostics** show inside the pipeline. The committed defaults in
`pyproject.toml` (`[tool.spire.diagnostics]`) apply; override per run with any
of `--show-parser` (Intent + the routing decision), `--show-planner` (the Plan
/ tool), `--show-raw-output`, `--show-synthesizer`, `--show-tokens`,
`--show-timings`, or `--show-all` — and `--no-show-*` to silence one. In
manifest mode the flags are forwarded to each child run, so they land on every
set.

```bash
# ad-hoc run with every stage visible
python scripts/promptkit.py --run --prompt "show suppliers in US" --show-all

# a manifest run, but silence token accounting on every set
python scripts/promptkit.py --run --manifest scripts/manifests/promptkit_sets.yaml \
    --no-show-tokens
```

The prompt-set inventory, known-good baselines, and guidance on reading
results are in [`docs/prompt-sets/SURFACE.md`](docs/prompt-sets/SURFACE.md).

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