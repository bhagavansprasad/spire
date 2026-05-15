# Spire — POC Master Plan

**Product:** Spire — an AI-native workspace for Oracle Fusion Cloud developers and consultants
**Document scope:** End-to-end plan to build a focused proof-of-concept that evaluates three architectural approaches against a single representative prompt
**Status:** Living document — phases approved through Direct Tool Orchestration (full) and Graph-Guided Orchestration Phase 3. Remaining phases drafted based on natural continuation.

---

## Table of Contents

1. [Vision & Positioning](#1-vision--positioning)
2. [The POC Prompt](#2-the-poc-prompt)
3. [Tech Stack](#3-tech-stack)
4. [The Three Architectures](#4-the-three-architectures)
5. [Direct Tool Orchestration — Plan](#5-direct-tool-orchestration--plan)
6. [Graph-Guided Orchestration — Plan](#6-graph-guided-orchestration--plan)
7. [Dynamic Orchestration — Plan](#7-dynamic-orchestration--plan)
8. [Working Principles](#8-working-principles)
9. [Open Questions & Future Considerations](#9-open-questions--future-considerations)

---

## 1. Vision & Positioning

**Spire is an AI-native workspace for Oracle Fusion Cloud developers and consultants.**

Spire combines two strengths into one product:

- A multi-pod environment for working with Fusion data (inspired by SQLConnect — `https://sqlconnect.com/`)
- A multi-agent AI assistant for Oracle Fusion development tasks (inspired by OracleWings — `https://oraclewings.ai/`)

**Critical positioning:** Spire is an AI product first, not a SQL IDE with AI bolted on. The AI conversation is the home; SQL editors, schema browsers, and results are workspace surfaces summoned when work requires them. Reference mental models: ChatGPT Canvas, Claude with artifacts, v0.dev.

**Target users:**
- **Primary:** Oracle Fusion technical consultants writing SQL, building reports, and configuring integrations
- **Secondary:** Functional consultants and BI analysts who don't write SQL but need data answers

**Strategic differentiator:** While competitors (OracleWings.AI, SQLConnect, others) operate at the level of "AI that writes SQL," Spire operates at the level of "AI that orchestrates Fusion's published API surface to get work done." The work isn't writing queries — it's reasoning over endpoints, patterns, and relationships.

---

## 2. The POC Prompt

A single, representative prompt is used for all three architectures so comparisons are apples-to-apples.

**The prompt:**

> *Show me suppliers in US with no invoices in 6 months but with open purchase orders, including the buyer assigned to each.*

**Why this prompt:**

- Spans multiple Fusion modules (Procurement, Payables)
- Requires multiple entity hops (Supplier → Invoice, Supplier → PO → Buyer)
- Includes negation logic ("no invoices in 6 months")
- Includes status semantics ("open" POs)
- Includes organizational scoping ("in US" — resolved as country, via supplier address)
- Realistic enough that a CFO or procurement lead might actually ask it

**Interpretation of "US":** Country = US, resolved through the supplier's address (child resource on the suppliers endpoint). This is a deliberate design decision; alternate interpretations (Business Unit, Legal Entity) are out of scope.

**Source documentation referenced for endpoint design:**
- Oracle Fusion Financials REST API — Invoices: `https://docs.oracle.com/en/cloud/saas/financials/26a/farfa/api-invoices.html`
- Related Oracle Fusion API docs for Suppliers and Purchase Orders

---

## 3. Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Standard for AI/LLM/agent ecosystem |
| Backend API | FastAPI | Modern, async-native, lightweight |
| Agent orchestration | LangGraph | Explicit graph-based control, state management, tool integration |
| MCP server framework | FastMCP | De facto Python framework for MCP servers |
| LLM | Google Gemini (`gemini-2.5-pro` for the agent, `gemini-2.5-flash` for cheap subtasks) via the `google-genai` SDK | Mature tool-use support, favorable pricing |
| HTTP client (Fusion endpoint calls) | `httpx` (async) | Modern, async, plays well with FastAPI |
| CLI | `typer` | Ergonomic developer experience |
| Database (relational + vector + graph) | Oracle AI Database 26ai (local Docker) | Native VECTOR data type, SQL Property Graph, single source of truth |
| Python Oracle driver | `python-oracledb` in thin mode | No Instant Client install needed |
| Persona/credential management | YAML file (`personas.yaml`, gitignored), `--persona <name>` CLI flag | Simple, file-based, supports identity switching |
| Validation | Pydantic v2 | Comes with FastAPI |
| Testing | `pytest`, `pytest-asyncio` | Standard |
| Logging | `structlog` | Structured, queryable logs |
| Local environment | WSL Ubuntu, no Docker Compose for POC | Per direction; can add later |
| Package management | TBD | Decision deferred |

**Git repository name:** `spire`

**Note on Oracle 26ai:** Oracle AI Database 26ai is the current long-term support release with native vector search (VECTOR data type, HNSW indexes), SQL Property Graph support (SQL/PGQ standard), and in-database embedding generation via ONNX. This bundle removes the need for separate vector and graph databases in the POC.

**Strategic context:** Oracle's own *Select AI* feature provides NL-to-SQL in 26ai. Spire is positioned at a different layer — agentic orchestration of Fusion's published API surface, with KG-driven intelligence — and addresses problems that Select AI does not (multi-step reasoning, endpoint orchestration, SaaS API constraints).

---

## 4. The Three Architectures

| Title | What's special |
|---|---|
| **Direct Tool Orchestration** | Fixed tools, no retrieval, no graph. LLM picks tools from descriptions alone. |
| **Graph-Guided Orchestration** | Fixed tools, plus a Knowledge Graph that informs how the LLM plans tool composition. |
| **Dynamic Orchestration** | Tools discovered at runtime via embeddings, plus the KG for relationship intelligence. The production architecture. |

**POC strategy:**

- Build Direct Tool Orchestration end-to-end → measure baseline
- Build Graph-Guided Orchestration on top → measure improvement
- Define Dynamic Orchestration as the production roadmap; build only if the KG investment is validated

**Why this strategy:** The "with KG vs without KG" comparison is the costliest decision to get wrong. Embeddings-for-tool-retrieval is well-understood; the KG's value is the unknown. The POC focuses on what's uncertain.

**What gets cached or replicated:** Nothing. Spire stores **metadata** (table names, endpoint definitions, relationship structures, query patterns), **configuration** (pod URLs, encrypted credentials, custom DFF mappings), **audit logs** (who ran what, when), and **conversation history** (the prompts and queries themselves, not their results). **Customer transactional data never leaves the Fusion pod.** This is an architectural hard rule.

---

## 5. Direct Tool Orchestration — Plan

The simplest architecture: hand-picked MCP tools wrapping Fusion REST endpoints, an LLM that orchestrates them based on tool descriptions alone. Establishes the baseline.

### Architecture sketch

```
User prompt
   ↓
LLM (Gemini, with tool descriptions in context)
   ↓
LangGraph agent loop (LLM ↔ tool executor)
   ↓
MCP Client
   ↓
MCP Server (FastMCP)
   ↓
Tools (one per Fusion resource family)
   ↓
Oracle Fusion REST endpoints
   ↓
Results flow back up; LLM composes natural-language answer
```

### Phase 1 — Environment & Access Setup

**Goal:** A working, authenticated connection to a real Fusion test pod, with one endpoint successfully called manually. No code yet.

**What we'll do:**

1. **Secure a Fusion test pod.** Options to pursue in parallel: Oracle Partner Network (OPN) membership for a development pod, friendly customer sandbox, or a paid Fusion test instance. Confirm pod is on a recent release (25C, 26A, or later).
2. **Create or obtain a service account** with appropriate roles for the POC scope (Supplier read, Invoice read, PO read, Person read). Likely roles: `Procurement Integration Specialist`, `Accounts Payable Specialist`, or a custom read-only role.
3. **Choose authentication method.** Basic Auth for POC (simplest). OAuth 2.0 client credentials for production roadmap.
4. **Pick one endpoint to test manually:** `GET /fscmRestApi/resources/11.13.18.05/suppliers?limit=5`.
5. **Make the manual call** via Postman or curl. Confirm: auth works (no 401), URL is correct (no 404), JSON response returns supplier records matching Oracle's schema.
6. **Document what worked:** pod URL, service account name, working endpoint URL, sample response payload — stored securely (password manager, not text file).

**Out of scope:** Code, MCP setup, LLM integration, multiple endpoints, error handling logic.

**Exit criteria:**
- Service account authenticates successfully against the pod
- Manual GET request returns valid JSON with supplier records
- Credentials, URL, sample response are documented securely
- The call is reliably repeatable

**Time estimate:** 1–3 days if pod access is arranged; 2–6 weeks if access requires OPN application or customer arrangement.

**Key risks:** Pod access time is the biggest unknown — start the acquisition process before everything else.

**Deliverables:** A 1-page setup document and a working Postman collection or curl script.

---

### Phase 2 — Single Endpoint Wrapped as a Tool

**Goal:** Build one MCP tool wrapping the Fusion supplier endpoint. Runs in a Python MCP server, accepts parameters, calls Fusion, parses the response, returns clean structured data. Tested in isolation — no LLM yet.

**What we'll do:**

1. **Set up project skeleton.** Initialize `spire` git repo; project structure:
   ```
   spire/
   ├── pyproject.toml
   ├── README.md
   ├── .gitignore
   ├── personas.yaml             (gitignored)
   ├── personas.example.yaml     (committed)
   ├── src/
   │   └── spire/
   │       ├── config.py         (persona loader)
   │       ├── mcp_server/
   │       │   ├── server.py     (FastMCP entry)
   │       │   └── tools/
   │       │       └── suppliers.py
   │       └── fusion/
   │           └── client.py     (httpx Fusion client)
   └── tests/
       └── test_suppliers_tool.py
   ```
2. **Build the persona loader** (`config.py`) — reads YAML, validates with Pydantic, fails loudly on missing or malformed personas.
3. **Build the Fusion HTTP client** (`fusion/client.py`) — thin wrapper around `httpx.AsyncClient`, handles Basic Auth, structured logging, common error codes (401, 404, 5xx, timeouts).
4. **Build the supplier tool** (`mcp_server/tools/suppliers.py`):
   ```python
   @mcp.tool()
   async def search_suppliers(
       country_code: str | None = None,
       supplier_name_contains: str | None = None,
       limit: int = 25
   ) -> list[dict]:
       """Search Oracle Fusion suppliers."""
   ```
5. **Wire up the FastMCP server** with the tool registered.
6. **Write a pytest integration test** that hits the real Fusion pod and asserts response shape.
7. **Validate via `fastmcp dev`** to confirm MCP roundtrip works.

**Out of scope:** LLM, additional tools, complex filtering (negation, joins), end-user CLI, Oracle 26ai integration.

**Exit criteria:**
- Project skeleton committed to git
- Persona loader switches pods correctly
- Fusion client successfully calls the supplier endpoint with auth
- `search_suppliers` returns clean list of supplier dicts (pytest passes)
- Same tool works through `fastmcp dev`
- Errors handled gracefully (wrong country code, bad credentials)

**Time estimate:** 2–4 days.

**Key risks:** Fusion's REST `q=` query syntax (test in Postman first); async/await gotchas; FastMCP version churn.

**Deliverables:** Working repo with the supplier tool, passing tests, README with setup notes.

---

### Phase 3 — Connect LLM to the Single Tool

**Goal:** Wire up Gemini via LangGraph to discover and call the `search_suppliers` MCP tool. Tested with a trivial prompt.

**What we'll do:**

1. **Add LangGraph + Gemini dependencies.** Install `langgraph`, `langchain-google-genai`, `langchain-mcp-adapters`, `google-genai`. Pin versions.
2. **Configure Gemini access.** `GEMINI_API_KEY` in `.env` (gitignored). Confirm access to `gemini-2.5-pro`.
3. **Build MCP adapter layer.** Use `langchain-mcp-adapters` to expose FastMCP tools to LangGraph. Spin up MCP server as subprocess (standard stdio pattern).
4. **Build minimal LangGraph agent.**
   ```
   src/spire/
   ├── agent/
   │   ├── graph.py     (LangGraph agent definition)
   │   └── prompts.py   (system prompt)
   ```
   Graph: LLM node + tool executor node, looping until final answer (standard ReAct-style).
5. **Write a short system prompt** — Spire is an Oracle Fusion assistant, can search suppliers, should call tools when needed.
6. **Build a CLI entry point** with `typer`:
   ```
   src/spire/cli.py
   ```
   Single command: `spire run --persona <name> --prompt "<text>"`.
7. **Test with a trivial prompt:** `spire run --persona default_dev --prompt "Show me 5 suppliers from the US"`. Verify agent calls the tool, receives results, summarizes.
8. **Capture trace logs** in `traces/` for debugging and future demo.

**Out of scope:** Additional tools, KG, embeddings, complex reasoning, streaming UI.

**Exit criteria:**
- End-to-end CLI works
- Agent calls the supplier tool and produces a sensible summary
- Trace logs captured
- Persona switching works
- Errors surface usefully

**Time estimate:** 2–4 days. Expect 1–2 days debugging Gemini tool-use quirks.

**Key risks:** Gemini's tool-use format differences from OpenAI/Claude; MCP subprocess management; rate limits/quota during dev; token cost during iteration (use `flash` early, `pro` once stable).

**Deliverables:** Working CLI agent, captured traces, updated README.

---

### Phase 4 — Add Remaining Tools One by One

**Goal:** Grow the tool catalog from 1 to 4–5 tools needed for the POC prompt. Each tool added, tested in isolation, then tested via the agent before the next is added.

**Tools (in order of addition):**

1. `search_invoices`
2. `search_purchase_orders`
3. `get_buyer`
4. `search_suppliers_by_country` (enriched supplier lookup that includes address data — this is the tricky one because country lives on the child address resource)

**Sub-phase pattern (repeated for each tool):**

1. **Validate the endpoint manually** in Postman.
2. **Build the tool** with a clear docstring (the LLM reads it).
3. **Test in isolation** via pytest with real Fusion data.
4. **Register with MCP server**, confirm via `fastmcp dev`.
5. **Smoke test via agent** with a tool-specific prompt; capture trace.

**Notes on specific tools:**

- **`search_purchase_orders`** — the `status` parameter docstring must clearly state what "OPEN" means (typically `AUTHORIZATION_STATUS='APPROVED' AND CLOSED_CODE='OPEN'`).
- **`search_suppliers_by_country`** — country lives on the child address resource. Three implementation options: use `expand=addresses` on `/suppliers` if it filters correctly; or list suppliers then query addresses per supplier; or use a parent-level query with join-like filter. Test in Postman first.

**After all tools added:** Run a moderately complex multi-tool prompt (e.g., *"Show me the first 5 US suppliers and tell me how many invoices each has from 2024"*). Capture trace.

**Out of scope:** KG, embeddings, advanced agent features (planning, memory, retry logic beyond defaults), parallel tool call optimization.

**Exit criteria:**
- All 4–5 tools registered and individually tested
- Agent picks the right tool for tool-specific prompts
- Multi-tool prompt works end-to-end
- Traces captured

**Time estimate:** 1–2 days per tool, 4–8 days total.

**Key risks:** Fusion endpoint variations between versions; `expand` parameter quirks; tool-selection accuracy degrading with more tools; pagination defaults (Fusion returns 25 records by default).

**Deliverables:** 4–5 working tools, all tested individually and through the agent.

---

### Phase 5 — End-to-End Test with the POC Prompt

**Goal:** Run the actual POC prompt against the agent and observe — without intervention — how Direct Tool Orchestration handles a real, multi-entity, multi-hop request.

**What we'll do:**

1. **Confirm environment.** All tools from Phase 4 registered, pod has realistic test data.
2. **Define expected behavior upfront** — write a rubric before running:
   - Find US suppliers (`search_suppliers_by_country`)
   - For each, check invoices in last 6 months (`search_invoices`)
   - Exclude those with recent invoices
   - For remaining, check open POs (`search_purchase_orders` with status='OPEN')
   - For matches, get buyer details (`get_buyer`)
   - Return: supplier list with buyer info
3. **Run the prompt once** (observation run): `spire run --persona default_dev --prompt "Show me suppliers in US with no invoices in 6 months but with open purchase orders, including the buyer assigned to each."`. Do NOT modify the prompt, pre-load context, or hint at tool choices.
4. **Score against the rubric** — mark each rubric step as ✅ correct, ⚠️ partial, ❌ wrong or skipped. Note specifically: did the agent understand negation? Did it correctly interpret "open"? Did it chain across multiple entities? How many tool calls? Efficient or wasteful?
5. **Run 4 more times** (5 total runs) — LLM outputs are non-deterministic, one run isn't a measurement.
6. **Document the baseline honestly** in `phase_5_baseline_report.md`.
7. **Identify failure patterns** — these directly motivate the KG.

**Critical discipline:** Do NOT prompt-engineer to help the agent. Do NOT retry with corrections. Do NOT tweak tool descriptions mid-test. Whatever the agent does, that's the baseline.

**Out of scope:** KG, comparison work, infrastructure error retries (those don't count as agent results).

**Exit criteria:**
- 5 runs completed and traced
- Each scored against the same rubric
- Honest baseline report written
- Failure patterns identified

**Time estimate:** 1–2 days.

**Key risks:** The agent might succeed (great signal, harder demo); non-determinism makes scoring feel subjective (mitigation: rubric written before running); test data shape matters (document honestly); temptation to optimize prompts is strong (resist).

**Deliverables:** Baseline report with prompt, rubric, 5 traces, 5 scores, aggregate stats, failure patterns, verbatim final answers.

---

### Phase 6 — Capture Baseline Results

**Goal:** Convert raw Phase 5 outputs into a clean, comparison-ready artifact for three audiences: the Oracle SME, the engineering team building Graph-Guided next, and the decision-maker comparing versions.

**What we'll do:**

1. **Consolidate the 5 traces** into `docs/poc/direct_tool_orchestration_baseline.md` with standard sections: prompt, rubric, environment, per-run details, aggregate metrics, failure analysis, verbatim final answers, honest verdict.
2. **Build the metrics table** (used identically across all versions for clean comparison):

   | Metric | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 | Avg | Notes |
   |---|---|---|---|---|---|---|---|
   | Correctness (rubric score, 0–10) | | | | | | | |
   | Tool calls made | | | | | | | |
   | Tool selection accuracy (% right) | | | | | | | |
   | Time to final answer (seconds) | | | | | | | |
   | Tokens consumed (in + out) | | | | | | | |
   | Estimated cost (USD) | | | | | | | |
   | Hit infrastructure error? (Y/N) | | | | | | | |
   | Result useful to a consultant? (Y/N/Partial) | | | | | | | |

3. **Document failure patterns with examples** — for each pattern: name, what happened, example from trace, why it matters, what would fix it.
4. **Write honest verdict** — direct paragraph answering: did it solve the prompt? how reliable? what did it consistently get wrong?
5. **Generate 1-page executive summary** for the SME (`direct_tool_orchestration_summary.md`).
6. **Preserve all raw traces** in `traces/phase_5/`.
7. **Identify open questions** for Graph-Guided Orchestration in `open_questions.md`.

**Critical discipline:** No re-running Phase 5 if results look bad. No softening failures. No interpretation in the data sections — save it for the verdict.

**Out of scope:** New code, agent tweaks, comparison to KG version.

**Exit criteria:**
- Full baseline report written
- Metrics table populated
- Failure patterns documented with concrete trace examples
- Honest verdict and 1-page exec summary ready
- Open questions captured

**Time estimate:** 1 day.

**Key risks:** Over-polishing (it's a working doc, not a publication); soft-pedaling failures (failures are the value); confusing the report for the conversation (plan to walk the SME through traces live).

**Deliverables:** Baseline report, exec summary, open questions doc, preserved trace logs. **Direct Tool Orchestration is now complete.**

---

## 6. Graph-Guided Orchestration — Plan

Builds on Direct Tool Orchestration. Adds a Knowledge Graph layer that informs the agent's planning *before* tool calls. Tests whether structured relationship knowledge meaningfully outperforms tool descriptions alone.

### Architecture sketch

```
User prompt
   ↓
LLM (with KG-consultation tools added to the toolkit)
   ↓
LangGraph agent loop:
   1. Agent consults KG: "what entities? what joins? what patterns?"
   2. Agent plans: based on KG, decides tool sequence
   3. Agent calls Fusion tools (same as Direct Tool Orchestration)
   ↓
Oracle Fusion REST endpoints (unchanged)
   ↓
Results back; LLM composes answer with KG context
```

**What we reuse from Direct Tool Orchestration:** All Fusion tools, MCP server, agent skeleton, CLI, persona system, baseline report format.

**What we add:** Knowledge Graph stored in Oracle 26ai (SQL Property Graph), graph-query tools the agent can call, and updates to the agent's prompt and flow that route through the KG before tool execution.

---

### Phase 1 — Design the Minimal Knowledge Graph

**Goal:** Written design document defining the smallest possible KG that could improve agent performance on the POC prompt. No DB work, no code — design first.

**What we'll do:**

1. **Decompose the POC prompt** into specific knowledge needs (canonical entities, traversals, patterns).
2. **Define entity nodes** — for each: name, canonical Fusion table, canonical endpoint, primary identifier, aliases, module, description. Initial list (6 entities): `Supplier`, `Invoice`, `PurchaseOrder`, `Buyer`, `Address`, `Country`.
3. **Define relationship edges** — for each: name, direction, cardinality, join keys, endpoint traversal hint. Initial list:
   - `Supplier --HAS_ADDRESS--> Address`
   - `Address --IN_COUNTRY--> Country`
   - `Supplier --HAS_INVOICES--> Invoice`
   - `Supplier --HAS_PURCHASE_ORDERS--> PurchaseOrder`
   - `PurchaseOrder --ASSIGNED_TO--> Buyer`
4. **Define query patterns** — natural-language-trigger + logic. Initial patterns:
   - `negation_no_y_in_n_months` ("no invoices in 6 months", etc.)
   - `status_filter_open_po` (encodes what "open" means)
   - `country_filter_via_address` (encodes that country requires the child resource)
   - `buyer_resolution_from_po` (encodes PO → Person traversal)
5. **Define lookup values** — explicit business-term-to-Oracle-code mappings ("US" → `'US'`, "open PO" → composite condition, etc.).
6. **Write the design document** at `docs/poc/kg_design.md`.
7. **List what's OUT of scope** explicitly: no DFFs, no Party indirection, no BU/LE modeling, no invoice line-level data, no HCM entities, no GL/journals/ledgers, no items/inventory.
8. **Sanity-check by mental execution** of the POC prompt against the graph.

**Out of scope:** Oracle 26ai work, SQL Property Graph syntax, code, populating data, agent integration.

**Exit criteria:**
- `docs/poc/kg_design.md` written and reviewed
- Every needed entity, relationship, pattern, lookup is captured
- Out-of-scope list is explicit
- Mental walkthrough confirms sufficiency

**Time estimate:** 1–2 days.

**Key risks:** Scope creep (#1 risk — strict POC discipline); confusing "canonical for Fusion" with "canonical for POC"; modeling the schema instead of the *knowledge*; designing for all future questions instead of this one.

**Deliverables:** Design document, scope statement (~6 entities, ~5 relationships, ~4 patterns, ~3 lookups), out-of-scope list, open questions.

---

### Phase 2 — Set Up Oracle 26ai for the Graph

**Goal:** Get Oracle 26ai's SQL Property Graph features working end-to-end with a trivial test graph. Prove infrastructure before loading real data.

**What we'll do:**

1. **Confirm Oracle 26ai readiness.** Container healthy. `COMPATIBLE` parameter ≥ 23.4.0. SQL/PGQ enabled.
2. **Create a `SPIRE` database user** with `CONNECT`, `RESOURCE`, `CREATE TABLE`, `CREATE VIEW`, `CREATE PROPERTY GRAPH`, `UNLIMITED TABLESPACE`.
3. **Add Oracle connection support to Spire** — `python-oracledb` in thin mode, project structure:
   ```
   src/spire/
   ├── db/
   │   ├── client.py     (oracledb connection helper)
   │   └── config.py     (database config in persona file)
   ```
4. **Create a trivial test schema** — two tables (entities + relationships), insert ~5 nodes and ~3 edges of throwaway data.
5. **Define a test property graph** using SQL/PGQ:
   ```sql
   CREATE PROPERTY GRAPH test_graph
     VERTEX TABLES (test_entities KEY (entity_id) LABEL Entity PROPERTIES (...))
     EDGE TABLES (test_relationships KEY (rel_id)
       SOURCE KEY (from_entity_id) REFERENCES test_entities (entity_id)
       DESTINATION KEY (to_entity_id) REFERENCES test_entities (entity_id)
       LABEL Relationship PROPERTIES (...));
   ```
6. **Run a basic SQL/PGQ query from SQLcl** and confirm it returns the expected traversals.
7. **Run the same query from Python** — proves the full stack works end-to-end.
8. **Document setup gotchas** in `docs/runbooks/oracle_26ai_setup.md`.
9. **Clean up test artifacts** — keep the runbook and Python connection module; drop the test graph and tables.

**Out of scope:** Real KG data, agent integration, vector storage, graph visualization tools, performance tuning.

**Exit criteria:**
- Oracle 26ai container confirmed healthy from WSL
- `SPIRE` user exists with required privileges
- `python-oracledb` thin mode connects successfully
- Test property graph created, populated, queryable from SQLcl and Python
- Setup runbook written
- Test artifacts cleaned up; DB ready for real data

**Time estimate:** 2–3 days.

**Key risks:** SQL/PGQ syntax differs from Cypher (don't trust Neo4j muscle memory); `COMPATIBLE` parameter blocking features; thin-mode limitations; WSL networking quirks; permissions surprises (`CREATE PROPERTY GRAPH` may need extra privileges); doc lag (26ai docs still partially reference 23ai).

**Deliverables:** `SPIRE` user ready, working Python DB client, setup runbook, end-to-end proof of stack, clean DB ready for Phase 3.

---

### Phase 3 — Populate the Graph with the Minimal Model

**Goal:** Turn the Phase 1 design into a real, queryable knowledge graph in Oracle 26ai. By the end, graph queries return the curated knowledge needed for the POC prompt.

**What we'll do:**

1. **Design the relational schema** that backs the graph — 5 tables:
   - `kg_entities` (canonical Fusion entities)
   - `kg_endpoints` (Fusion REST endpoints per entity)
   - `kg_patterns` (reusable query patterns)
   - `kg_lookups` (business-term-to-Oracle-code mappings)
   - `kg_relationships` (edges)
2. **Build idempotent migration scripts:**
   ```
   src/spire/kg/migrations/
   ├── 001_create_tables.sql
   └── 002_create_property_graph.sql
   ```
3. **Build the data loader** in Python:
   ```
   src/spire/kg/
   ├── loader.py            (loads YAML into Oracle tables)
   ├── schema.py            (Pydantic models)
   └── seed_data/
       ├── entities.yaml
       ├── endpoints.yaml
       ├── patterns.yaml
       ├── lookups.yaml
       └── relationships.yaml
   ```
   CLI: `spire kg load --reset`.
4. **Author the seed YAML files** — exactly the 6 entities, ~5 relationships, ~4 patterns, ~3 lookups from Phase 1. Strict discipline: small enough to scan in 60 seconds.
5. **Define the property graph view** in SQL/PGQ over the populated tables.
6. **Run validation queries** from SQLcl: "How do I find suppliers in a country?", "What's the pattern for 'no invoices in 6 months'?", "What does 'open PO' mean?", "How is a Buyer related to a Supplier?".
7. **Document the populated graph** in `docs/poc/kg_populated.md`.

**Out of scope:** Agent integration, tools exposing the graph (Phase 4), embeddings, entities beyond the Phase 1 design.

**Exit criteria:**
- 5 relational tables exist in Oracle 26ai under `SPIRE`
- Property graph view defined and queryable
- Seed data loaded successfully (matches Phase 1 design)
- `spire kg load --reset` is idempotent
- Validation queries return expected results

**Time estimate:** 2–4 days.

**Key risks:** YAML authoring rabbit-holes; property graph syntax errors with cryptic messages; cross-file inconsistencies (Pydantic validates); modeling drift from Phase 1 design (document and update Phase 1 if needed); idempotency bugs (test `--reset` repeatedly).

**Deliverables:** Populated KG in Oracle 26ai, Python loader, YAML seed files, property graph definition, validation queries documented.

---

### Phase 4 — Build the Graph Query Tool

**Goal:** Create curated MCP tools the agent calls to consult the graph — "what's canonical for X?", "how do I join X to Y?", "what pattern handles 'no Y in N months'?". The agent doesn't write SQL/PGQ; it calls these tools and gets structured answers.

**What we'll do:**

1. **Identify the queries the agent needs to make against the KG.** Anchor list (revisit and refine based on Phase 5 integration work):
   - `resolve_entity(name)` — given "supplier"/"vendor", returns canonical entity record
   - `get_canonical_endpoint(entity)` — returns the right REST endpoint and any traversal notes
   - `get_relationship(from_entity, to_entity)` — returns join semantics and endpoint traversal hint
   - `find_pattern(natural_language_phrase)` — fuzzy-matches a phrase to a pattern; returns implementation hint
   - `lookup_business_term(term)` — returns the Oracle code/condition for a business term
2. **Build the graph query tools** as MCP tools (FastMCP):
   ```
   src/spire/mcp_server/tools/kg/
   ├── resolve_entity.py
   ├── get_endpoint.py
   ├── get_relationship.py
   ├── find_pattern.py
   └── lookup_term.py
   ```
   Each tool: clear name, clear docstring, returns structured data.
3. **Implement each tool against the KG.** Most queries use plain SQL or SQL/PGQ over the relational tables; the graph view is queried when the agent needs to find paths or traversals.
4. **For `find_pattern`,** start simple (exact or substring match against `trigger_phrases`); note that fuzzy matching can be upgraded later (this is precisely where embeddings could help in Dynamic Orchestration).
5. **Test each tool in isolation** via pytest using the Phase 3 seed data.
6. **Register tools with the MCP server.** The agent now has 4–5 Fusion tools + 5 KG tools.
7. **Validate via `fastmcp dev`** that all KG tools work end-to-end.

**Out of scope:** Agent integration (next phase); KG modification tools (read-only for POC); fuzzy matching beyond simple substring (defer to Dynamic Orchestration).

**Exit criteria:**
- All KG query tools work in isolation (pytest passes)
- All tools registered and validated via `fastmcp dev`
- Tool docstrings are clear enough for the LLM to choose them correctly
- Test queries on the seed data return expected results

**Time estimate:** 2–4 days.

**Key risks:** Tool catalog grows too large (4–5 Fusion + 5 KG = 9–10 tools; manageable but watch tool-selection accuracy); pattern matching being too brittle with substring approach (acceptable for POC but flag for production); SQL/PGQ ergonomics slowing implementation (lean on plain SQL where possible).

**Deliverables:** 5 working KG query tools, pytest coverage, MCP integration confirmed, tool docs updated.

---

### Phase 5 — Integrate the Graph into the Agent Flow

**Goal:** Modify the LangGraph agent so it consults the KG *before* deciding which Fusion tools to call. The KG informs planning; existing Fusion tools still execute the actual work. This is the most novel work in Graph-Guided Orchestration.

**What we'll do:**

1. **Update the agent's system prompt** to explicitly instruct it: "When the user asks a question, first consult the KG tools to understand the entities, relationships, and patterns involved. Then plan and execute Fusion tool calls based on what the KG tells you."
2. **Decide the orchestration pattern.** Two viable patterns:
   - **Single-loop pattern (recommended for POC):** the agent has both KG tools and Fusion tools in one toolkit; the system prompt guides it to use KG first. Simpler, fewer moving parts.
   - **Two-phase pattern:** the LangGraph explicitly has a "plan" phase (KG consultation only) followed by an "execute" phase (Fusion only). More controlled but more complex. Defer unless single-loop fails.
3. **Update the LangGraph graph** if using the two-phase pattern; otherwise just expand the tool list and prompt.
4. **Build a "trace inspector" view** to make it easy to see, in any run, when the agent consulted the KG and what it received. Crucial for debugging and for the SME demo.
5. **Iteratively test with progressively harder prompts:**
   - Easy: "Show me suppliers in US" (just resolves entity + country pattern)
   - Medium: "Show me suppliers in US with invoices in 2024" (resolves country, joins to invoices)
   - Hard: The full POC prompt
   - For each, inspect: did the agent consult the KG appropriately? Did the KG's guidance improve tool selection? Did patterns fire correctly?
6. **Iterate on prompts and pattern descriptions** based on findings — this phase is where the design from Phase 1 meets reality. Expect adjustments to pattern wording, entity descriptions, lookup phrasings.
7. **Document the final integration** in `docs/poc/agent_kg_integration.md` — including the system prompt, orchestration pattern chosen, any tweaks made to the KG content.

**Out of scope:** Running the formal 5-run POC test (that's Phase 6); embedding-based pattern matching (defer to Dynamic Orchestration); KG modification by the agent (read-only).

**Exit criteria:**
- The agent reliably consults the KG before Fusion tool calls
- Trace inspector clearly shows KG consultation
- Easy, medium, and hard prompts all flow correctly
- System prompt and integration documented

**Time estimate:** 4–7 days. This is the highest-uncertainty phase — getting the agent to *use* the graph well is the core engineering risk.

**Key risks:** Agent ignores the KG and goes straight to Fusion tools (mitigation: clearer system prompt, possibly switch to two-phase pattern); pattern matching is too brittle in `find_pattern` (mitigation: improve trigger phrases in Phase 3's YAML); KG consultation adds latency without value on simple queries (mitigation: prompt can let the agent skip KG for trivially simple questions); subtle bias from over-prompting (the agent does well because the prompt tells it exactly what to do, not because the KG is useful — verify by comparing to Direct Tool Orchestration with the same prompt complexity).

**Deliverables:** Working graph-guided agent, trace inspector, integration documentation, progressively-harder prompt tests passing.

---

### Phase 6 — End-to-End Test with the POC Prompt

**Goal:** Run the same POC prompt through the graph-guided agent under the same protocol as Direct Tool Orchestration's Phase 5. Same rubric, same 5 runs.

**What we'll do:**

1. **Confirm environment.** All Fusion tools + KG tools registered. KG populated. Agent's system prompt finalized.
2. **Use the exact same rubric** as Direct Tool Orchestration's Phase 5. No changes — apples-to-apples.
3. **Run the prompt 5 times.** Same prompt verbatim. No hints. No retries with corrections.
4. **Capture full traces** including KG consultation steps.
5. **Score against the rubric.** For each rubric step: ✅ correct, ⚠️ partial, ❌ wrong.
6. **Additional KG-specific observations** to note:
   - Did the agent consult the KG? How many times?
   - Did the KG guidance change the tool plan vs. what Direct Tool Orchestration did?
   - Did patterns fire correctly?
   - Did any KG-provided knowledge get ignored?
7. **Document in `phase_6_graph_guided_report.md`** — same format as the Direct Tool Orchestration baseline.

**Out of scope:** Comparison work (that's Phase 7); changes to the agent or KG mid-run; infrastructure error retries.

**Exit criteria:**
- 5 runs completed and traced (with KG consultations visible)
- Each scored against the same rubric
- Honest report written
- KG-specific observations documented

**Time estimate:** 1–2 days.

**Key risks:** Same as Direct Tool Orchestration Phase 5 (non-determinism, temptation to optimize, data shape); plus KG-specific risk that the agent does well because the prompt over-specifies what to do, not because the KG adds value.

**Deliverables:** Graph-guided run report with 5 traces, 5 scores, KG consultation observations.

---

### Phase 7 — Capture Comparative Results

**Goal:** Produce the artifact that answers the question: *"Does the KG meaningfully improve the agent on this prompt?"*

**What we'll do:**

1. **Build the side-by-side comparison report** at `docs/poc/orchestration_comparison.md`:
   - Section 1: The prompt
   - Section 2: The rubric (single rubric, both versions)
   - Section 3: Side-by-side metrics table — Direct Tool Orchestration vs. Graph-Guided Orchestration

     | Metric | Direct (avg) | Graph-Guided (avg) | Δ | % change |
     |---|---|---|---|---|
     | Correctness (0–10) | | | | |
     | Tool calls made | | | | |
     | Tool selection accuracy | | | | |
     | Time to final answer | | | | |
     | Tokens consumed | | | | |
     | Estimated cost | | | | |
     | Useful to consultant? | | | | |
     | KG consultations | n/a | | | |

   - Section 4: Failure patterns in Direct Tool Orchestration — and how the KG addressed each one
   - Section 5: New failure patterns introduced by Graph-Guided (if any — be honest)
   - Section 6: Side-by-side verbatim final answers (one example pair, edited for length if needed)
   - Section 7: Honest verdict — does the KG earn its place?
2. **Build the SME-facing demo deck or document** (`docs/poc/sme_demo.md`):
   - 1 slide / section per concept: the prompt, the architecture diagrams, the Direct trace, the Graph-Guided trace with KG consultations highlighted, the metrics, the verdict
   - Designed to walk through live, not be read alone
3. **Make a clear recommendation** for next steps:
   - **If KG clearly wins:** proceed to Dynamic Orchestration (add embeddings for tool retrieval). Production architecture validated.
   - **If KG marginally wins:** evaluate whether the KG complexity is worth the marginal gain. Consider whether the prompt was a good test or too easy.
   - **If KG doesn't win:** stop building. Significant finding. Investigate whether a better-designed KG would help or whether tool descriptions truly suffice.
4. **Preserve all artifacts** in `traces/phase_6/` and the full reports for future reference.
5. **Identify open questions for Dynamic Orchestration** — if proceeding, what does the embedding layer need to solve that the KG didn't?

**Out of scope:** Starting Dynamic Orchestration (separate version); revising Direct Tool Orchestration or Graph-Guided based on the comparison (those phases are closed).

**Exit criteria:**
- Side-by-side comparison report completed
- SME-facing demo material ready
- Clear go/no-go recommendation on Dynamic Orchestration
- All artifacts preserved

**Time estimate:** 1–2 days.

**Key risks:** Spinning the results (resist — honest verdicts compound trust); over-claiming on small differences (use the metrics, not narrative); making the SME demo overly polished instead of investigative (it's a working session, not a sales pitch).

**Deliverables:** Comparison report, SME demo material, recommendation, preserved artifacts. **Graph-Guided Orchestration is now complete.**

---

## 7. Dynamic Orchestration — Plan

**Status note:** Dynamic Orchestration is the production-target architecture. It is *not part of the POC*. This section is a forward-looking plan, not committed work. Whether Dynamic Orchestration is built depends on the outcome of Graph-Guided Orchestration's Phase 7.

### Why this architecture matters

The Oracle SME's requirement: *the solution should work dynamically if more endpoints are added at runtime, without being restricted to a fixed catalog.*

This requirement directly motivates Dynamic Orchestration. Fusion has thousands of REST endpoints; even within a single module like Financials, the catalog is too large to load into the LLM's context. Embeddings over the endpoint catalog let the agent surface only the most relevant 10–20 tools per user query — making the system scalable to "all of Fusion" without redeployments.

The KG continues to provide the *relationship intelligence* (the graph-guided value); embeddings add *scale handling* (dynamic tool discovery).

### Architecture sketch

```
User prompt
   ↓
Pre-LLM step:
   - Embed prompt
   - Vector search over the endpoint/tool catalog → top-N relevant tools
   ↓
LLM (with only top-N tools in context, plus KG tools)
   ↓
LangGraph agent loop:
   1. Consult KG (as in Graph-Guided Orchestration)
   2. Plan and call Fusion tools (now from a dynamic, retrieval-filtered set)
   ↓
Oracle Fusion REST endpoints (unchanged)
   ↓
Results back; LLM composes answer
```

**What gets embedded** (revisiting from earlier work):

| Embedding store | Purpose | Priority for POC handoff |
|---|---|---|
| **Endpoint / tool catalog** | Dynamic tool retrieval based on user prompt | High — the core motivation |
| **Query patterns** | Fuzzy-match natural-language phrases to KG patterns | Medium |
| **Past successful tool plans** | Few-shot examples retrieved by prompt similarity | Medium — value compounds |
| **Tenant-specific knowledge** (DFFs, value sets) | Per-tenant personalization | Low for POC, high for production |
| **Documentation chunks** | Runbook-style operational knowledge | Low for POC |

**What we explicitly do not embed:** Customer transactional data. This boundary holds in Dynamic Orchestration the same way it did before.

### Phase Outline

**Phase 1 — Design the Embedding Strategy.** Decide which of the embedding stores above to build first, how to chunk/format each, which embedding model to use (likely Gemini's `text-embedding-004` or `gemini-embedding-001` to keep within one provider).

**Phase 2 — Set Up Vector Storage in Oracle 26ai.** Use Oracle 26ai's native `VECTOR` data type and `HNSW` index. Prove a trivial similarity search works end-to-end (Python → 26ai → vector → result).

**Phase 3 — Embed the Endpoint Catalog.** Build descriptions for all Fusion endpoints in scope (at first, this is the same 4–5 from the POC, plus 20–50 more chosen for breadth). Generate embeddings; store in 26ai. Validate retrieval quality with manually-curated prompt → expected-tool pairs.

**Phase 4 — Build the Dynamic Tool Retriever.** A pre-LLM component that takes the user's prompt, embeds it, retrieves top-N relevant tools, and presents them to the agent. Configurable N (default 15–20). Test in isolation: does retrieval surface the right tools for the POC prompt and for varied prompts?

**Phase 5 — Embed Query Patterns; Upgrade `find_pattern`.** Replace the simple substring matcher in Graph-Guided Orchestration's `find_pattern` tool with an embedding-based matcher. Test that fuzzy-matching now handles paraphrases the substring matcher missed.

**Phase 6 — Integrate Dynamic Retrieval into the Agent Flow.** Modify the LangGraph agent: at startup of each turn, run dynamic tool retrieval and load only the surfaced tools into the LLM context. KG tools remain always-available.

**Phase 7 — End-to-End Test with the POC Prompt + Extended Prompt Set.** Run the POC prompt under the same protocol. Additionally, test with prompts that stress dynamic retrieval: prompts that would have required tools *not in the original Direct Tool Orchestration catalog* (e.g., asking about journal entries, asking about HCM workers). Measure: did retrieval surface the right tools? Did the agent use them?

**Phase 8 — Capture Comparative Results.** Side-by-side: Direct vs. Graph-Guided vs. Dynamic. Update the master comparison report. Identify whether Dynamic earns its complexity over Graph-Guided for the POC prompt specifically — and whether it earns its complexity for the broader prompt set.

### Notes for Dynamic Orchestration

- **The POC prompt alone won't show Dynamic Orchestration's full value.** The POC prompt only needs ~5 tools. Dynamic retrieval shines when the catalog is in the hundreds. Plan the extended prompt set carefully to stress this — otherwise the metrics may suggest Dynamic Orchestration is overkill.
- **Embedding model choice matters more than people think.** Test 2–3 candidates (e.g., Gemini's embeddings, OpenAI's `text-embedding-3-large`, an open-source ONNX model imported into 26ai) with the same retrieval-quality benchmark before committing.
- **Operational complexity rises sharply** in Dynamic Orchestration: schema-change-tracking, embedding refresh pipelines, per-tenant isolation in the vector store, retrieval-quality monitoring. Production-grade Dynamic Orchestration is a significant ongoing investment, not a one-time build.
- **The KG never goes away.** Embeddings handle *fuzzy match* (which tools); the KG handles *precise traversal* (how entities relate). Both are needed in the production architecture.

---

## 8. Working Principles

A few principles that guide every phase, codified here so they don't have to be re-stated in each:

1. **Approval gates are mandatory.** No phase begins implementation until its detailed plan is approved. No major architectural decision is made mid-phase.
2. **Smaller steps are better than larger ones.** Most phases break into sub-phases; sub-phases break into tasks. The smaller the unit, the easier the debugging.
3. **Test before integrating.** Every layer (single tool, single endpoint, single graph query) is tested in isolation before being wired into the next layer.
4. **Honest baselines.** When a version is being tested, no prompt-engineering "to help it." Whatever it does, that's the data.
5. **One database for everything in the POC.** Oracle 26ai stores relational, graph, and (eventually) vector data. No separate Neo4j, no pgvector, no Pinecone. Simpler ops, single source of truth.
6. **Metadata in, data out.** Spire never replicates customer transactional data. The product stores schema knowledge, configuration, audit logs, and conversation history — never invoices, journals, or supplier records themselves.
7. **Endpoints, not tables.** All Fusion data access is via published REST endpoints (and BIP for SQL execution). No direct database connection to Fusion.
8. **Document as you go.** Every phase produces written deliverables. Runbooks, design docs, baseline reports — the documentation is part of the value, not an afterthought.
9. **Reuse aggressively.** Each version builds on what the previous version proved. Graph-Guided reuses Direct Tool Orchestration's tools, MCP server, agent skeleton, CLI, and report formats. Dynamic Orchestration reuses everything Graph-Guided produces.
10. **Resist scope creep.** Especially in design phases (KG design, embedding strategy). Every "while I'm at it..." addition is a distraction from validating the architectural decision at hand.

---

## 9. Open Questions & Future Considerations

Items that are knowingly deferred or unresolved at the time of this plan:

**Pod access timeline:** The single biggest schedule risk. Acquisition of a Fusion test pod (OPN, customer sandbox, or paid) is on the critical path. All other planning assumes this is in flight.

**Endpoint discovery:** Beyond the supplier/invoice/PO/buyer set, the Spire catalog will grow. A discovery pipeline (parsing Oracle's OpenAPI specs, ingesting documentation) will be needed for Dynamic Orchestration — out of scope for the POC.

**Authentication evolution:** Basic Auth for the POC; OAuth 2.0 for production. The persona system should be designed to accommodate both without rework.

**Pagination:** All Fusion tools currently use a single-page fetch with adjustable `limit`. Real production tools will need pagination. Out of scope for POC.

**Multi-tenancy:** The POC uses a single tenant. Production will require per-tenant isolation of KG overlays, embeddings, audit logs, and credentials. Not addressed in this plan.

**Result caching:** No caching in the POC. Whether to introduce result caching (and how to handle staleness in an ERP context) is a production conversation.

**Streaming and UI:** The POC is CLI-only. A web UI (per the Spire vision) is post-POC work and not in this plan.

**Compliance:** SOC 2, ISO 27001, GDPR considerations for production deployment. Out of scope for POC.

**Comparison to Oracle's Select AI:** Oracle ships a native NL-to-SQL feature in 26ai. The strategic positioning of Spire vs. Select AI deserves explicit thought before going to market. Worth raising during SME conversations.

**Embedding model choice for Dynamic Orchestration:** Default to Gemini's embeddings for provider consistency, but benchmark against alternatives. Decision deferred to Dynamic Orchestration Phase 1.

---

## Document End

This master plan is a living document. As the POC progresses, phase reports and the final comparison report will be linked back to this plan. Updates should be tracked in version control.

**Last updated:** Plan generation date (see git history)
**Status of plan execution:** Not started — awaiting kickoff
