# Spire POC — Working Log

A single rolling log of POC progress. One section per phase. Phase numbering follows the master plan (`spire_poc_master_plan.md`): Track A is Direct Tool Orchestration, Track B is Dynamic Orchestration (not yet started).

---

## Environment

- **Pod:** `https://fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com`
- **Pod type:** Oracle Fusion demo pod (multi-pillar: FSCM + HCM)
- **API version path:** `/fscmRestApi/resources/11.13.18.05/`, `/hcmRestApi/resources/11.13.18.05/`
- **Auth:** Basic Auth
- **Env vars used:** `FUSION_BASE_URL`, `FUSION_USERNAME`, `FUSION_PASSWORD`, `GEMINI_API_KEY`
- **Credential storage:** Shell environment variables + `personas.yaml` (see Phase A.1 deviation note)

---

## Phase A.1 — Environment & Access Setup  ✅ DONE

**Verified:** 2026-05-15

Confirmed pod reachable, FSCM REST API enabled, service account authenticates (Basic Auth), `GET /suppliers` returns valid JSON, call is repeatable.

```bash
curl -u "$FUSION_USERNAME:$FUSION_PASSWORD" \
  "$FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?limit=5" \
  -w "\nHTTP %{http_code}\n"
```

Returns 200 with real supplier records (Lee Supplies, supplier #1252, etc).

### Deviation from plan

Master plan A.1 requires credentials stored in a password manager. Currently held in shell env vars + `personas.yaml`. Owner accepts this risk; to be revisited if/when secret hygiene becomes a Spire-level concern.

---

## Phase A.2 — Single Endpoint Wrapped as a Tool  ✅ DONE

**Verified:** 2026-05-15
**Sub-phases:** A.2.a (skeleton) → A.2.b (persona loader) → A.2.c (HTTP client) → A.2.d (MCP server)

### What was built

Project skeleton, persona loader, async HTTP client, FastMCP server, one tool (`search_suppliers`).

```
spire/
├── src/spire/
│   ├── config.py                       (Persona loader, Pydantic-validated)
│   ├── fusion/client.py                (FusionClient — async httpx wrapper)
│   └── mcp_server/
│       ├── server.py                   (FastMCP server, HTTP transport)
│       └── tools/suppliers.py          (search_suppliers tool)
└── tests/                              (config, fusion client, supplier tool tests)
```

### Locked decisions

- src-layout (`src/spire/...`)
- Plain pip with split `requirements.txt` / `requirements-dev.txt`
- Persona schema: `base_url`, `username`, `password`, `auth_type` in YAML
- Tool function decoupled from MCP registration (testable directly)
- Persona loaded once at server startup
- Returns `items` list directly (no pagination wrapper)
- Async context manager for HTTP client lifecycle
- Exceptions bubble naturally (no custom exception classes)

---

## Phase A.3 — Connect LLM to the Single Tool  ✅ DONE

**Verified:** 2026-05-15

### What was built

End-to-end agent: prompt → MCP HTTP → Gemini picks `search_suppliers` → tool runs → answer.

- `src/spire/agent/runner.py` — LangGraph single-pass graph (`START → assistant → tools → assistant → END`)
- `src/spire/agent/tracing.py` — `structlog` → `traces/{timestamp}.jsonl` per run
- `src/spire/agent/lg_utility.py` — graph viz helper
- `scripts/ask.py`, `scripts/draw_graph.py`
- MCP server converted from stdio to HTTP transport on `127.0.0.1:3333`
- Integration test marked `@pytest.mark.integration`, skipped by default

### Key decisions

- **`langchain-google-genai`, not `google-genai`.** Direct `google-genai` SDK hit `aiplatform.googleapis.com` (Vertex AI) and required OAuth. The langchain wrapper uses the consumer Gemini API and accepts an API key cleanly.
- **Model: `gemini-2.0-flash`.**
- **HTTP MCP transport.** Two-terminal dev workflow.
- **System prompt hardcoded in `runner.py`.**

### Verified

```
$ python scripts/ask.py "Find suppliers with 'Lee' in the name"
I found two suppliers with 'Lee' in the name: Lee Supplies and Lee Testing for UK BU.
```

---

## Phase A.4 — Add Remaining Tools One by One  ✅ DONE

**Verified:** 2026-05-18
**Sub-phases:** A.4.1, A.4.2, A.4.3, A.4.4 (each merged separately)

### Tools added

| Sub-phase | Tool | Endpoint | Notes |
|---|---|---|---|
| A.4.1 | `search_invoices` | `/fscmRestApi/.../invoices` | Filter by supplier_number, supplier_name, invoice_date_after |
| A.4.2 | `search_purchase_orders` | `/fscmRestApi/.../purchaseOrders` | Filter by supplier_name, supplier_id, status |
| A.4.3 | `get_buyer` | `/hcmRestApi/.../publicWorkers` | BuyerId → PersonId lookup |
| A.4.4 | `search_suppliers_by_country` | `/fscmRestApi/.../suppliers?expand=addresses` | Country lives on child address resource |

### Major discoveries

**1. Fusion `q=` composite filter bug (A.4.2).**

Single-clause filters work; composite `AND` filters fail silently or with HTTP 500 on `/invoices` and `/purchaseOrders`:

```
GET /purchaseOrders?q=Supplier LIKE '%EIP%' AND StatusCode='OPEN'  → 200, empty
GET /purchaseOrders?q=SupplierId=X AND StatusCode='OPEN'           → 500
GET /invoices?q=SupplierNumber='1252' AND InvoiceDate>='2020-01-01' → 200, empty
```

**Workaround:** in both `invoices.py` and `purchase_orders.py`, pick the most selective single clause to send via `q=`, over-fetch up to `OVERFETCH_LIMIT=200`, filter remaining clauses in Python. SME consult sent for the underlying syntax issue.

**2. No FSCM `buyers` endpoint (A.4.3).**

`/fscmRestApi/.../buyers` returns 404 on this pod. Buyers are HCM workers; `BuyerId` maps to `PersonId` on `/hcmRestApi/.../publicWorkers`. Used `publicWorkers` (flat record with `DisplayName`, `WorkEmail`, `Username`) over `/workers?expand=names,emails` for simpler results.

**3. Suppliers have country on child address resource, not parent (A.4.4).**

The master plan flagged this. Used `expand=addresses` on `/suppliers`, then filtered client-side for any address matching the requested country. A supplier with multiple addresses can match multiple countries — that's correct behavior.

**4. Pod credential drift / OWSM policy lag.**

REST APIs (`fscmRestApi`, `hcmRestApi`) returned 401 with empty body for ~30 minutes mid-day while BPM endpoint kept returning 200. Resolved itself with no client-side change. Worth documenting as a pattern — empty-body 401 with `WWW-Authenticate: Basic realm="owsm"` is OWSM/server-side, not client.

### Design patterns established

- All tools project to a small subset of fields (avoid LLM context bloat from full ~100-field records)
- Client-side filter composition where Fusion `q=` is unreliable
- Tool function in `tools/<name>.py`; MCP registration in `server.py`
- One integration test per filter dimension; loose assertions where data may change
- `dict | None` for singular lookups (`get_buyer`); `list[dict]` for searches

### Verified end-to-end

All four tools confirmed working through the agent via smoke tests:

```
$ python scripts/ask.py "Find any invoices for Lee Supplies"
→ search_invoices(supplier_name="Lee Supplies") → 25 records

$ python scripts/ask.py "Find open purchase orders for EIP"
→ search_purchase_orders(supplier_name="EIP", status="OPEN") → 23 records

$ python scripts/ask.py "Who is the buyer with ID 300000047340498?"
→ get_buyer(buyer_id=300000047340498) → Calvin Roth + email + username

$ python scripts/ask.py "Find suppliers in US"
→ search_suppliers_by_country(country="US") → 25 US-addressed suppliers
```

### Tool catalog at end of Phase A.4

```
search_suppliers              - search by name fragment
search_suppliers_by_country   - filter by address country
search_invoices               - search by supplier + date
search_purchase_orders        - search by supplier + status
get_buyer                     - look up buyer by ID
```

### Tests

23 passing, 1 deselected (the agent integration test, requires MCP server).

### Open questions / deferred work

- SME response on Fusion composite-`q=` syntax (workaround in place)
- Over-fetch cap means filters can miss matches beyond OVERFETCH_LIMIT — acceptable for POC
- 500 supplier over-fetch on `search_suppliers_by_country` is slow (~30s with addresses expanded); pagination later

---

## Phase A.5 — End-to-End Test with the POC Prompt  ⏳ PENDING

Run the reference prompt 5 times, score against rubric written upfront, document failure patterns honestly. No prompt engineering or tool-description tweaking during the test.

The reference prompt:

> *Show me suppliers in US with no invoices in 6 months but with open purchase orders, including the buyer assigned to each.*

---

## Phase A.6 — Capture Baseline Results  ⏳ PENDING

Write the baseline report. Becomes the comparison target for Track B.

---

## Track B — Dynamic Orchestration  ⏳ NOT STARTED

9 phases (B.1 through B.9). Begins after A.6 establishes the baseline.
