# Spire POC — Working Log

A single rolling log of POC progress. One section per phase. Curl commands, sample outputs (trimmed), and status live inline. Updated as work progresses.

---

## Environment

- **Pod:** `https://fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com`
- **Pod type:** Oracle Fusion demo pod (multi-pillar: FSCM + HCM)
- **API version path:** `/fscmRestApi/resources/11.13.18.05/`
- **Auth:** Basic Auth
- **Env vars used:** `FUSION_BASE_URL`, `FUSION_USERNAME`, `FUSION_PASSWORD`
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

Empty file skeleton only — no executable code. Establishes the structure that Phase 2b/2c/2d will fill in.

```
spire/
├── .gitignore
├── LICENSE
├── README.md
├── personas.example.yaml
├── requirements.txt
├── requirements-dev.txt
├── docs/
│   └── spire_poc_log.md          (this file)
├── src/
│   └── spire/
│       ├── __init__.py
│       ├── config.py             (Phase 2b)
│       ├── fusion/
│       │   ├── __init__.py
│       │   └── client.py         (Phase 2c)
│       └── mcp_server/
│           ├── __init__.py
│           ├── server.py         (Phase 2d)
│           └── tools/
│               ├── __init__.py
│               └── suppliers.py  (Phase 2d)
└── tests/
    ├── __init__.py
    └── test_suppliers_tool.py    (Phase 2d)
```

### Decisions locked

- **Layout:** src-layout (`src/spire/...`) — namespaced imports, forces install for tests to behave like real users
- **Package manager:** plain pip with split `requirements.txt` / `requirements-dev.txt` — defer real tooling decision until needed
- **Persona schema:** YAML, one persona per top-level key, fields = `base_url`, `username`, `password`, `auth_type`

### `.gitignore` covers

- Python artifacts (`__pycache__/`, `*.py[codz]`, `.pyre/`)
- Virtualenvs (`.venv`, `venv/`, `env/`, `ENV/`)
- Env files (`.env`, `.envrc`)
- Project secrets (`personas.yaml`, `how-to-run.md`)
- Scratch (`temp/`, `traces/`)
- Editor / OS noise (`.DS_Store`, `.idea/`, `.vscode/`, `*.swp`, `*.Zone.Identifier`)

### Exit criteria

| Criterion | Status |
|---|---|
| Source tree matches src-layout plan | ✅ |
| `personas.example.yaml` documents persona schema | ✅ |
| `.gitignore` excludes secrets and scratch | ✅ |
| Committed and merged via PR | ✅ |

---

## Phase 2b — Persona Loader  ✅ DONE

**Verified:** 2026-05-15
**PR:** `phase-2b-persona-loader` → `master`

### What was built

`src/spire/config.py` — Pydantic-validated persona loader. Reads `personas.yaml` from repo root, returns the named persona as a `Persona` model.

```python
from spire.config import load_persona
persona = load_persona("default_dev")
# persona.base_url, persona.username, persona.password, persona.auth_type
```

### Design choices

- **`auth_type` is plain `str`** — no `Literal` restriction. Lets `oauth2` land later without editing the model.
- **No caching** — re-reads `personas.yaml` per call. CLI tools call this once per run; caching is premature.
- **Exceptions bubble naturally** — `FileNotFoundError`, `KeyError`, `pydantic.ValidationError`. No custom exception classes for the POC.

### Tests

`tests/test_config.py` — 3 tests covering:
- Happy path (valid persona returns populated model)
- Unknown persona raises `KeyError`
- Malformed YAML entry raises `ValidationError`

Tests use `tmp_path` fixture + `unittest.mock.patch` to redirect `PERSONAS_FILE` — no real `personas.yaml` is touched.

### Dependencies added

`requirements.txt`:
- `pydantic>=2,<3`
- `pyyaml>=6`

`requirements-dev.txt`:
- `pytest>=8`

### `pyproject.toml`

Minimal setuptools config — needed for `pip install -e .` to work with src-layout. Re-added after 2a deletion.

### `.gitignore` addition

`*.egg-info/` — generated by editable install.

### Exit criteria

| Criterion | Status |
|---|---|
| `Persona` model defined with locked schema | ✅ |
| `load_persona(name)` returns validated model | ✅ |
| Unit tests pass (3/3) | ✅ |
| No network calls in module or tests | ✅ |

---

## Phase 2c — Fusion HTTP Client  ✅ DONE

**Verified:** 2026-05-15
**PR:** `phase-2c-fusion-client` → `master`

### What was built

`src/spire/fusion/client.py` — async HTTP client for Oracle Fusion REST API. Wraps `httpx.AsyncClient` with persona-driven auth and base URL.

```python
from spire.config import load_persona
from spire.fusion.client import FusionClient

persona = load_persona("default_dev")
async with FusionClient(persona) as client:
    data = await client.get(
        "/fscmRestApi/resources/11.13.18.05/suppliers",
        params={"limit": 5},
    )
```

### Design choices

- **Hardcoded full paths** (e.g., `/fscmRestApi/resources/11.13.18.05/suppliers`) — no URL builder. Phase 4 will revisit if duplication becomes painful with 4–5 tools.
- **GET only** for this phase. POST/PATCH/DELETE come when needed.
- **Basic Auth only** — `auth_type != "basic"` raises `ValueError` at construction. `oauth2` placeholder for later.
- **Async context manager** — explicit lifecycle for the underlying `httpx.AsyncClient`.
- **Errors bubble** — `response.raise_for_status()` lets `httpx.HTTPStatusError` propagate naturally.

### Tests

`tests/test_fusion_client.py` — 2 tests:
- Happy path: hits real pod, asserts supplier shape (integration test)
- Unsupported `auth_type` raises `ValueError` (unit test)

Tests skip cleanly if `personas.yaml` is missing.

### Dependencies added

`requirements.txt`:
- `httpx>=0.27`

`requirements-dev.txt`:
- `pytest-asyncio>=0.23`

### `pyproject.toml` addition

`asyncio_mode = "auto"` under `[tool.pytest.ini_options]` — lets `@pytest.mark.asyncio` tests run without per-test config.

### Exit criteria

| Criterion | Status |
|---|---|
| Async client authenticates to real pod | ✅ |
| GET returns parsed JSON | ✅ |
| Unsupported auth raises clear error | ✅ |
| Tests skip gracefully without credentials | ✅ |

---

## Phase 2d — Supplier Tool + MCP Server  ✅ DONE

**Verified:** 2026-05-15
**PR:** `phase-2d-supplier-tool` → `master`

### What was built

`src/spire/mcp_server/tools/suppliers.py` — plain async `search_suppliers(client, ...)` function. Tool logic decoupled from FastMCP registration.

`src/spire/mcp_server/server.py` — FastMCP server. Loads `default_dev` persona at startup, registers `search_suppliers` as an MCP tool that opens a `FusionClient` per call.

```python
# Direct use (testing)
from spire.mcp_server.tools.suppliers import search_suppliers
items = await search_suppliers(client, supplier_name_contains="Lee", limit=5)

# Via MCP (runtime)
# fastmcp dev src/spire/mcp_server/server.py
```

### Design choices

- **Tool function ≠ MCP registration.** Plain async function in `tools/`; `@mcp.tool()` wrapper in `server.py`. Tool can be unit-tested without FastMCP. Slight extra plumbing in `server.py`.
- **Persona loaded once at server startup.** Single hardcoded `default_dev`. Multi-persona switching is a Phase 3+ concern.
- **`country_code` filtering deferred to Phase 4.** Requires the `addresses` child resource — flagged tricky in the master plan. Out of scope for 2d.
- **`supplier_name_contains` uses Fusion `q=` syntax:** `q=Supplier LIKE '%foo%'`.
- **Return shape:** just the `items` list. Pagination wrapper (`count`, `hasMore`) dropped — LLM doesn't need it yet.

### Tests

`tests/test_suppliers_tool.py` — 2 integration tests:
- Default search (no filter, limit=5) → list of 5 dicts, each with `SupplierId` and `Supplier`
- Name filter (`"Lee"`) → at least one result, contains "Lee" in supplier name

Both skip if `personas.yaml` missing. No FastMCP-in-test machinery; tool function called directly.

### Manual verification

```bash
fastmcp dev src/spire/mcp_server/server.py
```

Opens FastMCP inspector — tool callable via UI. Manual confirmation step, not automated.

### Dependencies added

`requirements.txt`:
- `fastmcp>=2`

### Exit criteria

| Criterion | Status |
|---|---|
| `search_suppliers` callable directly | ✅ |
| `search_suppliers` callable via FastMCP | ✅ (manual verification) |
| Integration tests pass against real pod | ✅ |
| Tool returns supplier records | ✅ |

---

## Phase 3 — LangGraph Agent  ⏳ PENDING

Not started.
