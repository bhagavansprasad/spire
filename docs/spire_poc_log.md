# Spire POC — Working Log

A single rolling log of POC progress. One section per phase. Curl commands, sample outputs (trimmed), and status live inline. Updated as work progresses.

---

## Environment

- **Pod:** `https://fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com`
- **Pod type:** Oracle Fusion demo pod (multi-pillar: FSCM + HCM)
- **API version path:** `/fscmRestApi/resources/11.13.18.05/`
- **Auth:** Basic Auth
- **Env vars used:** `FUSION_BASE_URL`, `FUSION_USERNAME`, `FUSION_PASSWORD`, `GEMINI_API_KEY`
- **Credential storage:** Shell environment variables (see Phase 1 deviation note)

---

## Phase 1 — Environment & Access Setup  ✅ DONE

**Verified:** 2026-05-15

### What was confirmed

- Pod reachable, FSCM REST API enabled
- Service account authenticates (Basic Auth)
- `GET /suppliers` returns valid JSON
- Call is repeatable (limit=1 and limit=5 both return 200)

### Working command

```bash
curl -u "$FUSION_USERNAME:$FUSION_PASSWORD" \
  "$FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?limit=5" \
  -w "\nHTTP %{http_code}\n"
```

### Sample response (trimmed)

```json
{
  "items": [
    {
      "SupplierId": 300000047414503,
      "Supplier": "Lee Supplies",
      "SupplierNumber": "1252",
      "Status": "ACTIVE",
      "BusinessRelationship": "Spend Authorized",
      "TaxpayerCountryCode": "US",
      "CreationDate": "2013-11-07T20:14:36.428+00:00"
    }
  ],
  "count": 1,
  "hasMore": true,
  "limit": 1,
  "offset": 0
}
```

Full response also includes child resource links: `addresses`, `sites`, `contacts`, `businessClassifications`, `DFF` (custom fields), etc. The `addresses` child is relevant for Phase 4 (`search_suppliers_by_country`).

### Exit criteria

| Criterion | Status |
|---|---|
| Service account authenticates | ✅ |
| Manual GET returns valid JSON with supplier records | ✅ |
| Credentials documented securely | ⚠️ See deviation below |
| Call is reliably repeatable | ✅ |

### Deviation from plan

Master plan Phase 1 requires credentials stored in a password manager. Currently held in shell environment variables only. Owner accepts this risk; to be revisited if/when secret hygiene becomes a Spire-level concern.

---

## Phase 2a — Project Skeleton  ✅ DONE

**Verified:** 2026-05-15
**PR:** `phase-2a-skeleton` → `master` (merged)

### What was built

Empty file skeleton — establishes the structure that Phase 2b/2c/2d fill in. src-layout under `src/spire/`. `tests/` skeleton. `.gitignore` covering Python artifacts, virtualenvs, env files, `personas.yaml`, `how-to-run.md`, `temp/`, `traces/`, editor noise. `personas.example.yaml` template.

### Decisions locked

- **Layout:** src-layout (`src/spire/...`)
- **Package manager:** plain pip with split `requirements.txt` / `requirements-dev.txt`
- **Persona schema:** YAML, fields = `base_url`, `username`, `password`, `auth_type`

---

## Phase 2b — Persona Loader  ✅ DONE

**Verified:** 2026-05-15
**PR:** `phase-2b-persona-loader` → `master` (merged)

### What was built

`src/spire/config.py` — Pydantic-validated persona loader. Reads `personas.yaml`, returns named persona as `Persona` model.

```python
from spire.config import load_persona
persona = load_persona("default_dev")
```

### Design choices

- `auth_type` as plain `str` (no `Literal` restriction)
- No caching — re-reads YAML per call
- Exceptions bubble naturally (`FileNotFoundError`, `KeyError`, `ValidationError`)

### Tests

`tests/test_config.py` — 3 tests (happy path, unknown persona, malformed entry).

### Dependencies

`pydantic>=2,<3`, `pyyaml>=6`, `pytest>=8`. `pyproject.toml` restored for editable install.

---

## Phase 2c — Fusion HTTP Client  ✅ DONE

**Verified:** 2026-05-15
**PR:** `phase-2c-fusion-client` → `master` (merged)

### What was built

`src/spire/fusion/client.py` — async HTTP client wrapping `httpx.AsyncClient` with persona-driven auth.

```python
async with FusionClient(persona) as client:
    data = await client.get("/fscmRestApi/resources/11.13.18.05/suppliers", params={"limit": 5})
```

### Design choices

- Hardcoded full paths (no URL builder yet)
- GET only
- Basic Auth only; other `auth_type` values raise `ValueError`
- Errors bubble (`httpx.HTTPStatusError`)

### Tests

`tests/test_fusion_client.py` — integration test against real pod + unit test for unsupported auth.

### Dependencies

`httpx>=0.27`, `pytest-asyncio>=0.23`. `pyproject.toml`: `asyncio_mode = "auto"`.

---

## Phase 2d — Supplier Tool + MCP Server  ✅ DONE

**Verified:** 2026-05-15
**PR:** `phase-2d-supplier-tool` → `master` (merged)

### What was built

`src/spire/mcp_server/tools/suppliers.py` — plain async `search_suppliers(client, ...)` function. Tool logic decoupled from FastMCP registration.

`src/spire/mcp_server/server.py` — FastMCP server. Loads `default_dev` at startup, registers `search_suppliers`. Original implementation used stdio; updated to HTTP in Phase 3.

### Design choices

- Tool function decoupled from MCP registration (testable directly)
- Persona loaded once at server startup
- `country_code` filter deferred to Phase 4
- `supplier_name_contains` via Fusion `q=` syntax
- Returns `items` list directly (no pagination wrapper)

### Tests

`tests/test_suppliers_tool.py` — 2 integration tests against real pod.

### Dependencies

`fastmcp>=2`.

---

## Phase 3 — LangGraph Agent  ✅ DONE

**Verified:** 2026-05-15
**PR:** `phase-3-agent` → `master`

### What was built

First end-to-end agent. Reads a prompt, connects to the Spire MCP server over HTTP, lets Gemini pick `search_suppliers`, runs it, returns the answer. Built on LangGraph + `langchain-google-genai` + `langchain-mcp-adapters`.

Originally planned as 3a (Gemini + direct tool calling) + 3b (LangGraph + MCP). Collapsed into a single phase after adopting a working LangGraph reference pattern — direct `google-genai` SDK was hitting Vertex AI and required OAuth, so we shifted to `langchain-google-genai` which uses the consumer API with an API key cleanly.

### Components

- `src/spire/agent/runner.py` — `run_agent(prompt)`. Single-pass graph: `START → assistant → tools → assistant → END`. `tools_condition` routes back to assistant after each tool call; terminates when assistant produces a final message with no tool calls.
- `src/spire/agent/tracing.py` — `structlog` config. Each run writes a JSONL file to `traces/{ISO timestamp}.jsonl`. Events: `agent_started`, `mcp_session_initialized`, `tools_loaded`, `graph_built`, `message` (one per message in final state), `agent_finished`.
- `src/spire/agent/lg_utility.py` — `save_graph_as_png` helper (only used by `scripts/draw_graph.py`).
- `src/spire/mcp_server/server.py` — updated to run HTTP transport on `127.0.0.1:3333` instead of stdio.
- `scripts/ask.py` — standalone driver. `python scripts/ask.py "..."`.
- `scripts/draw_graph.py` — one-shot graph viz → `docs/agent_graph.png`.

### Design choices

- **HTTP MCP transport.** Two-terminal dev workflow.
- **LangGraph from the start.** Reused proven pattern.
- **`langchain-google-genai`, not `google-genai`.** Sidesteps Vertex AI / OAuth requirement.
- **Model: `gemini-2.0-flash`.**
- **System prompt hardcoded in `runner.py`.** Single source of truth.
- **No MCP prompt loading.**
- **Graph viz off by default.** Run `scripts/draw_graph.py` explicitly.
- **Integration tests skipped by default** via `addopts = "-m 'not integration'"` in `pyproject.toml`. Run with `pytest -m integration`.

### Dev workflow

Terminal 1:
```bash
python -m spire.mcp_server.server
```

Terminal 2:
```bash
export GEMINI_API_KEY=...   # or use GOOGLE_API_KEY if that's what langchain-google-genai expects in your env
python scripts/ask.py "Find suppliers with 'Lee' in the name"
```

### Tests

`tests/test_agent_runner.py` — 1 integration test, marked `@pytest.mark.integration`. Requires MCP server running + `GEMINI_API_KEY` set. Skipped by default; run with `pytest -m integration`.

### Verified end-to-end

```
$ python scripts/ask.py "Find suppliers with 'Lee' in the name"
I found two suppliers with 'Lee' in the name: Lee Supplies and Lee Testing for UK BU.
```

Trace shows correct flow: HumanMessage → AIMessage (tool call) → ToolMessage (Fusion response) → AIMessage (final answer).

### Dependencies

Added: `langchain-google-genai`, `langgraph`, `langchain-mcp-adapters`, `mcp`, `structlog`.
Dropped: `google-genai` (Vertex routing issue).

### Known issues

- Deprecation warning: `streamablehttp_client` should be `streamable_http_client` in newer `mcp` releases. One-line fix; deferred to follow-up.
- `Key 'additionalProperties' is not supported in schema, ignoring` warnings from Gemini when loading the MCP tool. Harmless; cosmetic.

### Exit criteria

| Criterion | Status |
|---|---|
| Agent reads prompt and produces answer | ✅ |
| Tool selection via LLM (not hardcoded) | ✅ |
| MCP transport over HTTP | ✅ |
| Tracing wired with structured output | ✅ |
| Integration test passes | ✅ |
| Default test suite remains green without external services | ✅ |

---

## Phase 4 — Additional Tools  ⏳ PENDING

Not started. Adds `search_suppliers_by_country`, `search_invoices`, `search_purchase_orders`, `get_buyer` — the remaining tools needed for the reference prompt:

> *Show me suppliers in US with no invoices in 6 months but with open purchase orders, including the buyer assigned to each.*
