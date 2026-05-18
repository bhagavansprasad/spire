# Spire POC — Working Log

A single rolling log of POC progress. Phase numbering follows the master plan (`spire_poc_master_plan.md`): Track A is Direct Tool Orchestration, Track B is Dynamic Orchestration.

Earlier entries in this log used bare numbering (Phase 1, 2a–2d, 3, 4). The log has been re-aligned to the master plan's lettered scheme (A.1, A.2, A.3, A.4, …) for consistency. Phase content is unchanged; only labels.

---

## Environment

- **Pod:** `https://fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com`
- **Pod type:** Oracle Fusion demo pod (multi-pillar: FSCM + HCM)
- **API version paths:** `/fscmRestApi/resources/11.13.18.05/`, `/hcmRestApi/resources/11.13.18.05/`
- **Auth:** Basic Auth
- **Env vars used:** `FUSION_BASE_URL`, `FUSION_USERNAME`, `FUSION_PASSWORD`, `GEMINI_API_KEY`
- **Credential storage:** Shell environment variables + `personas.yaml` (see A.1 deviation note)

---

## Phase A.1 — Environment & Access Setup  ✅ DONE

**Verified:** 2026-05-15

Confirmed pod reachable, FSCM REST API enabled, service account authenticates (Basic Auth), `GET /suppliers` returns valid JSON, call is repeatable.

```bash
curl -u "$FUSION_USERNAME:$FUSION_PASSWORD" \
  "$FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?limit=5" \
  -w "\nHTTP %{http_code}\n"
```

Returns 200 with real records (Lee Supplies, supplier #1252, etc).

### Deviation

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

**1. Fusion `q=` composite filter bug (A.4.2).** Single-clause filters work; composite `AND` filters fail silently or with HTTP 500 on `/invoices` and `/purchaseOrders`. Workaround applied to both tools: send the most selective single clause via `q=`, over-fetch up to `OVERFETCH_LIMIT=200`, filter remaining clauses in Python. SME consult sent on underlying syntax.

**2. No FSCM `buyers` endpoint (A.4.3).** `/fscmRestApi/.../buyers` returns 404. Buyers are HCM workers; `BuyerId` maps to `PersonId` on `/hcmRestApi/.../publicWorkers`. Used `publicWorkers` (flat record) over `/workers?expand=names,emails`.

**3. Suppliers have country on child address (A.4.4).** Used `expand=addresses`, filtered client-side for any matching address. A supplier with multiple-country addresses can match multiple — that's correct behavior.

**4. Pod credential drift / OWSM policy lag.** REST APIs returned 401 with empty body for ~30 minutes mid-day while BPM kept 200. Resolved itself. Worth noting: empty-body 401 with `WWW-Authenticate: Basic realm="owsm"` is OWSM/server-side, not client.

### Design patterns established

- All tools project to a small subset of fields (avoid LLM context bloat)
- Client-side filter composition where Fusion `q=` is unreliable
- Tool function in `tools/<name>.py`; MCP registration in `server.py`
- `dict | None` for singular lookups (`get_buyer`); `list[dict]` for searches

### Tool catalog at end of A.4

```
search_suppliers              - search by name fragment
search_suppliers_by_country   - filter by address country
search_invoices               - search by supplier + date
search_purchase_orders        - search by supplier + status
get_buyer                     - look up buyer by ID
```

### Tests

23 passing, 1 deselected (the agent integration test, requires MCP server).

---

## Phase A.5 — End-to-End Test with the POC Prompt  ✅ DONE

**Verified:** 2026-05-18
**Report:** `docs/phase_a5_baseline_report.md`

Five runs of the reference prompt against the Track A agent. Rubric written before runs. No prompt engineering, no retries with corrections, no tool-description tweaks. Honest baseline.

**Result: 1/7.** Agent reliably finds US suppliers; reliably fails to compose further.

### Failure patterns

1. **Premature termination (runs 1–3).** Agent calls `search_suppliers_by_country` once and stops. LangGraph loop supports iteration; the LLM didn't iterate.
2. **Parameter confusion across tools (runs 4–5).** Agent called `search_purchase_orders(supplier_number='1252')` — a parameter that exists on `search_invoices` but not `search_purchase_orders`. Pydantic validation raised; LangGraph had no recovery; runs crashed.
3. **No error recovery.** ToolException propagated through the graph unhandled.

### What this baseline measures

Composition, not execution. Each tool works individually (23/23 pytest passing). The agent struggles to chain 4+ tool calls based on docstrings alone. This is the gap Track B's KG is meant to close.

### Discipline confirmation

- Tool descriptions not edited mid-test ✓
- Prompt unchanged across runs ✓
- Failed runs not retried ✓
- System prompt unchanged ✓
- Parameter naming inconsistency NOT unified (would invalidate the baseline) ✓

Full per-run details, trace tails, and verbatim outcomes in `docs/phase_a5_baseline_report.md`.

---

## Phase A.6 — Capture Baseline Results  ✅ DONE

**Verified:** 2026-05-18

Documentation-only phase. Two updates:

1. **`docs/designs/spire_design_alternatives.md`** — added a "Measured baseline" row to the comparison table (`1/7` for Track A; `pending` for Track B; `n/a` for the two documented-only designs). Added a "Measured results so far" subsection in section 9 referencing the A.5 report.

2. **`docs/spire_poc_log.md`** (this file) — re-aligned phase naming to the master plan (A.1, A.2, A.3, A.4, A.5, A.6) for consistency. Earlier entries used bare numbering (Phase 1, 2a–2d, 3, 4); content unchanged, only labels.

### Track A status: complete

| Phase | Status |
|---|---|
| A.1 | ✅ |
| A.2 | ✅ (A.2.a–A.2.d) |
| A.3 | ✅ |
| A.4 | ✅ (A.4.1–A.4.4) |
| A.5 | ✅ |
| A.6 | ✅ |

### What carries forward to Track B

- The 5 MCP tools, the LangGraph runner, the persona loader, the Fusion HTTP client, the trace format, the test harness — all reused
- The 1/7 baseline as the comparison target
- The known-but-deliberately-unfixed parameter naming inconsistency (left in place to avoid invalidating the baseline; will be fixed if/when both tracks are re-evaluated under matched conditions)
- The composite `q=` workaround pattern (will inform how KG-driven tools build their server-side queries)

---

## Track B — Dynamic Orchestration  ⏳ NOT STARTED

9 phases per master plan:

| Phase | Name |
|---|---|
| B.1 | Design the Minimal Knowledge Graph |
| B.2 | Set Up Oracle 26ai for the Graph |
| B.3 | Populate the Graph with the Minimal Model |
| B.4 | Build the Graph Query Tools |
| B.5 | Integrate the Graph into the Agent Flow |
| B.6 | Add Embeddings for Dynamic Tool Retrieval |
| B.7 | Integration Polish & Trace Visibility |
| B.8 | End-to-End Test with the POC Prompt |
| B.9 | Capture Comparative Results |

B.1 is the natural next step.

## Dynamic Orchestration 01 — KG Schema Design  ✅ DONE

**Verified:** 2026-05-18
**Deliverable:** `docs/designs/kg_schema_v1.md`
**Branch:** `dynamic-orchestration/01-kg-schema-design`

Design-only phase — no code, no infrastructure, no tests. Wrote the minimal Knowledge Graph schema that Track B's later phases will build on.

### What was decided

- **6 entities:** Supplier, Invoice, PurchaseOrder, Buyer, Address, Country
- **5 typed edges:** `HAS_INVOICE`, `HAS_ADDRESS`, `LOCATED_IN`, `HAS_PURCHASE_ORDER`, `ASSIGNED_TO` (the last crosses FSCM → HCM)
- **4 query patterns:** `no_Y_in_N_months`, `status_filter`, `country_filter_via_address`, `cross_pillar_lookup`
- **4 lookup categories:** countries, PO statuses, entity terms, relationship phrases

Sized to support the POC reference prompt (and no broader). Single-tenant, read-only, single-pod, storage-agnostic.

### Key decisions

- **Country and Address as separate entities, not Supplier attributes.** A supplier can have addresses in multiple countries; folding country into Supplier would model "a supplier has *a* country," which is wrong. Keeping them separate makes `country_filter_via_address` an explicit named pattern rather than a hidden assumption.
- **`SupplierNumber` vs `SupplierId` asymmetry called out prominently (§3.1 and §3.4).** This is the parameter confusion that crashed runs 4 and 5 in the A.5 baseline. Edge definitions specify which join key Fusion exposes on which endpoint, so the agent reads it from the KG rather than from docstring archaeology.
- **`ASSIGNED_TO` (PO → Buyer) flagged as cross-pillar.** The single most important relationship docstrings alone failed to convey in Track A. There is no `/fscmRestApi/.../buyers` endpoint; buyers are HCM workers via `publicWorkers`. KG makes this explicit.
- **Country lookups held as static table (§5.1), not ingested from Fusion setup endpoints.** Ingestion is a later phase if needed; static is sufficient for the POC reference prompt.
- **Storage decision deferred** to Dynamic Orchestration 02. The schema doc describes the *model*, not how it's stored.

### Explicit non-goals (§6)

Listed so later phases don't drift: per-tenant overlays, DFFs, setup-data ingestion, writes, multi-pod federation, currency conversion, historical/temporal modeling, approval/payment workflows, inverse/transitive relationships, cardinality enforcement, provenance.

### Open questions deferred (§7)

Five questions intentionally not resolved in v1:

1. How does the agent match prompt clauses to patterns? (substring / LLM / embedding — Dynamic Orchestration 04 or 06)
2. What's the contract between KG queries and the existing MCP tools? (Dynamic Orchestration 04)
3. Where does the KG live physically? (Dynamic Orchestration 02)
4. How is the KG kept in sync with the schema as it evolves?
5. What's the error contract when a pattern can't be applied?

None block Dynamic Orchestration 02. Items 1 and 2 will need answers before 04 and 05.

### Honest framing

The schema is deliberately thin. **The four patterns are the load-bearing claim** — entities and edges are bookkeeping; patterns are what the agent will actually consult. `cross_pillar_lookup` is the pattern I'm least confident in as named (only one instance in v1; may fold into the `ASSIGNED_TO` edge once Dynamic Orchestration 04 starts). The doc explicitly says "update — don't fork" so v1.1 can drop or refactor it without ceremony.

Success criterion for v1: a Track B agent built on this schema scores meaningfully higher than the 1/7 Track A baseline on the reference prompt under the same rubric. If it scores 1/7 again, either the KG is too thin, the integration is wrong, or the hypothesis is wrong — and that's signal the POC needs to capture, not paper over.

### What comes next

Dynamic Orchestration 02 — Oracle 26ai Setup. Infrastructure-heavy (local Docker, persistence config, networking from WSL, `python-oracledb` wiring, first SQL Property Graph smoke test). Will likely break into sub-phases. To be scoped with approval gates when we start.

---