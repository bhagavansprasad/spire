# Spire — POC Master Plan

**Product:** Spire — an AI-native workspace for Oracle Fusion Cloud developers and consultants
**Document scope:** End-to-end plan to build a focused proof-of-concept that evaluates two architectural approaches against a single representative prompt
**Status:** Planning complete. Phases approved through prior incremental review.
**Companion document:** `docs/designs/spire_design_alternatives.md` describes the four architectural alternatives considered and explains why the POC builds two of them.

---

## Table of Contents

1. [Vision & Positioning](#1-vision--positioning)
2. [The POC Prompt](#2-the-poc-prompt)
3. [Tech Stack](#3-tech-stack)
4. [The Two POC Tracks](#4-the-two-poc-tracks)
5. [Track A — Direct Tool Orchestration](#5-track-a--direct-tool-orchestration)
6. [Track B — Dynamic Orchestration](#6-track-b--dynamic-orchestration)
7. [Comparative Evaluation](#7-comparative-evaluation)
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
- **Primary:** Oracle Fusion technical consultants writing SQL, building reports, configuring integrations
- **Secondary:** Functional consultants and BI analysts who don't write SQL but need data answers

**Strategic differentiator:** Spire operates at the level of "AI that orchestrates Fusion's published API surface to get work done" — not the narrower "AI that writes SQL." The work isn't writing queries; it's reasoning over endpoints, patterns, and relationships.

---

## 2. The POC Prompt

A single, representative prompt is used for both tracks so comparisons are apples-to-apples.

**The prompt:**

> *Show me suppliers in US with no invoices in 6 months but with open purchase orders, including the buyer assigned to each.*

**Why this prompt:**

- Spans multiple Fusion modules (Procurement, Payables)
- Requires multiple entity hops (Supplier → Invoice, Supplier → PO → Buyer)
- Includes negation logic ("no invoices in 6 months")
- Includes status semantics ("open" POs)
- Includes organizational scoping ("in US" — resolved as country, via supplier address)
- Realistic enough that a CFO or procurement lead might actually ask it

**Interpretation of "US":** Country = US, resolved through the supplier's address (child resource on the suppliers endpoint).

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

**Git repository:** `git@github.com:bhagavansprasad/spire.git`

**Note on Oracle 26ai:** Oracle AI Database 26ai is the current long-term support release with native vector search (VECTOR data type, HNSW indexes), SQL Property Graph support (SQL/PGQ standard), and in-database embedding generation via ONNX. This bundle removes the need for separate vector and graph databases in the POC.

**Strategic context:** Oracle's own *Select AI* feature provides NL-to-SQL in 26ai. Spire is positioned at a different layer — agentic orchestration of Fusion's published API surface, with KG-driven intelligence — and addresses problems that Select AI does not (multi-step reasoning, endpoint orchestration, SaaS API constraints).

---

## 4. The Two POC Tracks

The POC builds two of the four architectures described in `docs/designs/spire_design_alternatives.md`:

| Track | Architecture | Role |
|---|---|---|
| **Track A** | Design 2 — Direct Tool Orchestration | Baseline. LangGraph agent + MCP tools wrapping Fusion REST endpoints. No KG, no embeddings. |
| **Track B** | Design 4 — Dynamic Orchestration | Full architecture. Adds Knowledge Graph (in Oracle 26ai SQL Property Graph) and embedding-based dynamic tool retrieval (in Oracle 26ai VECTOR storage). |

**Two designs from the alternatives document are not built as separate POC phases:**

- **Design 1 (Reference Library + Validation)** — the SME's design. Documented for transparency but not built as a POC track. Its limitations (no agent loop, no error recovery, no multi-step reasoning) are well-understood and its natural evolution converges with Design 2.
- **Design 3 (Graph-Guided Orchestration)** — the Knowledge Graph is built, but as a *component* of Track B, not as a separate version. Building it twice as a separate Design 3 phase plus a Design 4 phase would duplicate work without adding signal.

The POC's central comparative question: *"Does the full architecture (Track B) meaningfully outperform the baseline (Track A) on a realistic prompt?"*

**What gets cached or replicated:** Nothing. Spire stores **metadata** (table names, endpoint definitions, relationship structures, query patterns), **configuration** (pod URLs, encrypted credentials, custom DFF mappings), **audit logs** (who ran what, when), and **conversation history** (the prompts and queries themselves, not their results). **Customer transactional data never leaves the Fusion pod.** This is an architectural hard rule.

---

## 5. Track A — Direct Tool Orchestration

The simplest architecture that actually solves the POC prompt: hand-picked MCP tools wrapping Fusion REST endpoints, an LLM that orchestrates them based on tool descriptions alone. Establishes the baseline against which Track B is measured.

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

### Phase A.1 — Environment & Access Setup

**Goal:** A working, authenticated connection to a real Fusion test pod, with one endpoint successfully called manually. No code yet.

**What we'll do:**

1. **Secure a Fusion test pod.** Options in parallel: Oracle Partner Network (OPN) membership for a development pod, friendly customer sandbox, or a paid Fusion test instance. Confirm pod is on a recent release (25C, 26A, or later).
2. **Create or obtain a service account** with appropriate roles for the POC scope (Supplier read, Invoice read, PO read, Person read). Likely roles: `Procurement Integration Specialist`, `Accounts Payable Specialist`, or a custom read-only role.
3. **Choose authentication method.** Basic Auth for POC (simplest). OAuth 2.0 client credentials for production roadmap.
4. **Pick one endpoint to test manually:** `GET /fscmRestApi/resources/11.13.18.05/suppliers?limit=5`.
5. **Make the manual call** via Postman or curl. Confirm auth works, URL is correct, JSON response returns supplier records.
6. **Document what worked** securely (password manager, not text file).

**Out of scope:** Code, MCP setup, LLM integration, multiple endpoints, error handling logic.

**Exit criteria:**
- Service account authenticates against the pod
- Manual GET returns valid JSON with supplier records
- Credentials, URL, sample response documented securely
- The call is reliably repeatable

**Time estimate:** 1–3 days if pod access is arranged; 2–6 weeks if access requires OPN application or customer arrangement.

**Key risks:** Pod access time is the biggest unknown — start the acquisition process before everything else.

**Deliverables:** 1-page setup doc and a working Postman collection or curl script.

---

### Phase A.2 — Single Endpoint Wrapped as a Tool

**Goal:** Build one MCP tool wrapping the Fusion supplier endpoint. Tested in isolation — no LLM yet.

**What we'll do:**

1. **Set up project skeleton:**
   ```
   spire/
   ├── pyproject.toml
   ├── README.md
   ├── .gitignore
   ├── personas.yaml             (gitignored)
   ├── personas.example.yaml     (committed)
   ├── src/
   │   └── spire/
   │       ├── config.py
   │       ├── mcp_server/
   │       │   ├── server.py
   │       │   └── tools/
   │       │       └── suppliers.py
   │       └── fusion/
   │           └── client.py
   └── tests/
       └── test_suppliers_tool.py
   ```
2. **Build the persona loader** (`config.py`) — reads YAML, validates with Pydantic.
3. **Build the Fusion HTTP client** — thin wrapper around `httpx.AsyncClient`, Basic Auth, structured logging.
4. **Build the supplier tool:**
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
6. **Write a pytest integration test** that hits the real pod.
7. **Validate via `fastmcp dev`** to confirm MCP roundtrip works.

**Out of scope:** LLM, additional tools, complex filtering, CLI for end users, Oracle 26ai integration.

**Exit criteria:**
- Project skeleton committed to git
- Persona loader switches pods correctly
- Fusion client successfully calls the supplier endpoint with auth
- `search_suppliers` returns clean list of supplier dicts (pytest passes)
- Same tool works through `fastmcp dev`
- Errors handled gracefully

**Time estimate:** 2–4 days.

**Key risks:** Fusion's REST `q=` query syntax (test in Postman first); async/await gotchas; FastMCP version churn.

**Deliverables:** Working repo with the supplier tool, passing tests, README with setup notes.

---

### Phase A.3 — Connect LLM to the Single Tool

**Goal:** Wire up Gemini via LangGraph to discover and call the `search_suppliers` MCP tool. Tested with a trivial prompt.

**What we'll do:**

1. **Add LangGraph + Gemini dependencies.** Pin versions.
2. **Configure Gemini access.** `GEMINI_API_KEY` in `.env` (gitignored).
3. **Build MCP adapter layer** using `langchain-mcp-adapters`. Spin up MCP server as subprocess.
4. **Build minimal LangGraph agent:**
   ```
   src/spire/agent/
   ├── graph.py
   └── prompts.py
   ```
   Graph: LLM node + tool executor node, looping until final answer (standard ReAct-style).
5. **Write a short system prompt** — Spire is an Oracle Fusion assistant.
6. **Build a CLI entry point** with `typer`:
   `spire run --persona <name> --prompt "<text>"`
7. **Test with a trivial prompt:** *"Show me 5 suppliers from the US."*
8. **Capture trace logs** in `traces/`.

**Out of scope:** Additional tools, KG, embeddings, complex reasoning, streaming UI.

**Exit criteria:**
- End-to-end CLI works
- Agent calls the supplier tool and produces a sensible summary
- Trace logs captured
- Persona switching works
- Errors surface usefully

**Time estimate:** 2–4 days. Expect 1–2 days debugging Gemini tool-use quirks.

**Key risks:** Gemini's tool-use format differences from OpenAI/Claude; MCP subprocess management; rate limits during dev; token cost during iteration (use `flash` early, `pro` once stable).

**Deliverables:** Working CLI agent, captured traces, updated README.

---

### Phase A.4 — Add Remaining Tools One by One

**Goal:** Grow the tool catalog from 1 to 4–5 tools needed for the POC prompt. Each tool added, tested in isolation, then tested via the agent before the next is added.

**Tools (in order):**

1. `search_invoices`
2. `search_purchase_orders`
3. `get_buyer`
4. `search_suppliers_by_country` (enriched supplier lookup that includes address data — country lives on the child address resource)

**Sub-phase pattern (per tool):**

1. **Validate the endpoint manually** in Postman.
2. **Build the tool** with a clear docstring (the LLM reads it).
3. **Test in isolation** via pytest with real Fusion data.
4. **Register with MCP server**, confirm via `fastmcp dev`.
5. **Smoke test via agent** with a tool-specific prompt; capture trace.

**Notes on specific tools:**

- **`search_purchase_orders`** — `status` parameter docstring must clearly state what "OPEN" means (typically `AUTHORIZATION_STATUS='APPROVED' AND CLOSED_CODE='OPEN'`).
- **`search_suppliers_by_country`** — country lives on the child address resource. Three implementation options: use `expand=addresses` on `/suppliers`; or list suppliers then query addresses per supplier; or use a parent-level query with join-like filter. Test in Postman first.

**After all tools added:** Run a moderately complex multi-tool prompt (e.g., *"Show me the first 5 US suppliers and tell me how many invoices each has from 2024"*).

**Out of scope:** KG, embeddings, advanced agent features, parallel tool call optimization.

**Exit criteria:**
- All 4–5 tools registered and individually tested
- Agent picks the right tool for tool-specific prompts
- Multi-tool prompt works end-to-end
- Traces captured

**Time estimate:** 1–2 days per tool, 4–8 days total.

**Key risks:** Endpoint variations between Fusion versions; `expand` parameter quirks; tool-selection accuracy degrading with more tools; pagination defaults.

**Deliverables:** 4–5 working tools, all tested individually and through the agent.

---

### Phase A.5 — End-to-End Test with the POC Prompt

**Goal:** Run the POC prompt against the agent and observe — without intervention — how Direct Tool Orchestration handles a real, multi-entity, multi-hop request.

**What we'll do:**

1. **Confirm environment.** All tools from Phase A.4 registered, pod has realistic test data.
2. **Define expected behavior upfront** — write a rubric before running:
   - Find US suppliers (`search_suppliers_by_country`)
   - For each, check invoices in last 6 months (`search_invoices`)
   - Exclude those with recent invoices
   - For remaining, check open POs (`search_purchase_orders` with status='OPEN')
   - For matches, get buyer details (`get_buyer`)
3. **Run the prompt once** (observation): `spire run --persona default_dev --prompt "Show me suppliers in US with no invoices in 6 months but with open purchase orders, including the buyer assigned to each."`. Do NOT modify, pre-load context, or hint at tool choices.
4. **Score against the rubric** — ✅ correct, ⚠️ partial, ❌ wrong or skipped.
5. **Run 4 more times** (5 total runs) for non-determinism.
6. **Document baseline honestly** in `phase_a5_baseline_report.md`.
7. **Identify failure patterns** — these motivate Track B.

**Critical discipline:** Do NOT prompt-engineer to help the agent. Do NOT retry with corrections. Do NOT tweak tool descriptions mid-test.

**Out of scope:** Track B work, comparison, infrastructure error retries.

**Exit criteria:**
- 5 runs completed and traced
- Each scored against the same rubric
- Honest baseline report written
- Failure patterns identified

**Time estimate:** 1–2 days.

**Key risks:** Agent might succeed (great signal); non-determinism makes scoring feel subjective (mitigation: rubric written before running); temptation to optimize prompts (resist).

**Deliverables:** Baseline report with prompt, rubric, 5 traces, 5 scores, aggregate stats, failure patterns, verbatim final answers.

---

### Phase A.6 — Capture Baseline Results

**Goal:** Convert raw Phase A.5 outputs into a clean, comparison-ready artifact.

**What we'll do:**

1. **Consolidate the 5 traces** into `docs/poc/track_a_baseline.md` with standard sections: prompt, rubric, environment, per-run details, aggregate metrics, failure analysis, verbatim final answers, honest verdict.
2. **Build the metrics table** (used identically across both tracks):

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

3. **Document failure patterns with examples** — for each: name, what happened, example from trace, why it matters, what would fix it.
4. **Write honest verdict.**
5. **Generate 1-page executive summary** for the SME.
6. **Preserve all raw traces** in `traces/phase_a5/`.
7. **Identify open questions for Track B** in `open_questions.md`.

**Out of scope:** New code, agent tweaks, Track B work.

**Exit criteria:**
- Full baseline report written
- Metrics table populated
- Failure patterns documented
- Honest verdict and 1-page exec summary ready

**Time estimate:** 1 day.

**Deliverables:** Baseline report, exec summary, open questions doc, preserved trace logs. **Track A is now complete.**

---

## 6. Track B — Dynamic Orchestration

The full architecture. Builds on Track A by adding two new capability layers — a Knowledge Graph (encoding entities, relationships, query patterns, and lookups) and embedding-based dynamic tool retrieval (enabling the tool catalog to scale beyond what fits in LLM context). Tests whether structured knowledge and dynamic retrieval together meaningfully outperform tool descriptions alone.

### Architecture sketch

```
User prompt
   ↓
Pre-LLM step:
   • Embed user prompt
   • Vector search over endpoint/tool catalog (Oracle 26ai VECTOR)
   • Retrieve top-N most relevant tools
   ↓
LLM with:
   • KG consultation tools (always available)
   • Top-N Fusion tools (dynamically selected)
   ↓
LangGraph agent loop:
   1. Consult KG: "what entities? what joins? what patterns?"
   2. Plan tool calls based on KG guidance
   3. Execute Fusion tools (same as Track A)
   4. Loop until final answer
   ↓
Oracle Fusion REST endpoints (unchanged)
   ↓
Results back; LLM composes answer with KG context
```

**What we reuse from Track A:** All Fusion tools, MCP server, agent skeleton, CLI, persona system, baseline report format.

**What we add in Track B:**
- Knowledge Graph stored in Oracle 26ai (SQL Property Graph)
- Graph-query tools the agent can consult
- Embeddings over the tool catalog (Oracle 26ai VECTOR)
- Pre-LLM retrieval step that filters which tools enter context
- Updates to the agent's prompt and flow

---

### Phase B.1 — Design the Minimal Knowledge Graph

**Goal:** Written design document defining the smallest possible KG that could improve agent performance on the POC prompt. No DB work, no code — design first.

**What we'll do:**

1. **Decompose the POC prompt** into specific knowledge needs (canonical entities, traversals, patterns).
2. **Define entity nodes** — for each: name, canonical Fusion table, canonical endpoint, primary identifier, aliases, module, description. Initial list (6 entities): `Supplier`, `Invoice`, `PurchaseOrder`, `Buyer`, `Address`, `Country`.
3. **Define relationship edges:**
   - `Supplier --HAS_ADDRESS--> Address`
   - `Address --IN_COUNTRY--> Country`
   - `Supplier --HAS_INVOICES--> Invoice`
   - `Supplier --HAS_PURCHASE_ORDERS--> PurchaseOrder`
   - `PurchaseOrder --ASSIGNED_TO--> Buyer`
4. **Define query patterns** — natural-language trigger + logic. Initial patterns:
   - `negation_no_y_in_n_months` ("no invoices in 6 months")
   - `status_filter_open_po` (encodes what "open" means)
   - `country_filter_via_address` (country lookup requires child resource)
   - `buyer_resolution_from_po` (PO → Person traversal)
5. **Define lookup values** — explicit mappings ("US" → 'US', "open PO" → composite condition).
6. **Write the design document** at `docs/poc/kg_design.md`.
7. **List what's OUT of scope** explicitly: no DFFs, no Party indirection, no BU/LE modeling, no invoice line-level data, no HCM entities, no GL/journals/ledgers.
8. **Sanity-check by mental execution** of the POC prompt against the graph.

**Out of scope:** Oracle 26ai work, SQL Property Graph syntax, code, populating data, agent integration.

**Exit criteria:**
- `docs/poc/kg_design.md` written and reviewed
- Every needed entity, relationship, pattern, lookup is captured
- Out-of-scope list is explicit
- Mental walkthrough confirms sufficiency

**Time estimate:** 1–2 days.

**Key risks:** Scope creep is the #1 risk; confusing "canonical for Fusion" with "canonical for POC"; modeling the schema instead of the *knowledge*; designing for all future questions instead of this one.

**Deliverables:** Design document, scope statement (~6 entities, ~5 relationships, ~4 patterns, ~3 lookups), out-of-scope list, open questions.

---

### Phase B.2 — Set Up Oracle 26ai for the Graph

**Goal:** Get Oracle 26ai's SQL Property Graph features working end-to-end with a trivial test graph. Prove infrastructure before loading real data.

**What we'll do:**

1. **Confirm Oracle 26ai readiness.** Container healthy. `COMPATIBLE` ≥ 23.4.0. SQL/PGQ enabled.
2. **Create a `SPIRE` database user** with `CONNECT`, `RESOURCE`, `CREATE TABLE`, `CREATE VIEW`, `CREATE PROPERTY GRAPH`, `UNLIMITED TABLESPACE`.
3. **Add Oracle connection support to Spire:**
   ```
   src/spire/db/
   ├── client.py     (oracledb connection helper)
   └── config.py     (DB config in persona file)
   ```
4. **Create a trivial test schema** — two tables (entities + relationships), ~5 nodes, ~3 edges of throwaway data.
5. **Define a test property graph** using SQL/PGQ.
6. **Run a basic SQL/PGQ query from SQLcl** and confirm it returns expected traversals.
7. **Run the same query from Python** — proves the full stack works.
8. **Document setup gotchas** in `docs/runbooks/oracle_26ai_setup.md`.
9. **Clean up test artifacts** — keep the runbook and connection module.

**Out of scope:** Real KG data, vector storage (deferred to B.5), agent integration.

**Exit criteria:**
- Oracle 26ai confirmed healthy from WSL
- `SPIRE` user exists with required privileges
- `python-oracledb` thin mode connects successfully
- Test property graph created, populated, queryable from SQLcl and Python
- Setup runbook written

**Time estimate:** 2–3 days.

**Key risks:** SQL/PGQ syntax differs from Cypher; `COMPATIBLE` parameter blocking features; thin-mode limitations; WSL networking; permissions surprises; doc lag.

**Deliverables:** `SPIRE` user ready, working Python DB client, setup runbook, end-to-end proof.

---

### Phase B.3 — Populate the Graph with the Minimal Model

**Goal:** Turn the Phase B.1 design into a real, queryable knowledge graph in Oracle 26ai.

**What we'll do:**

1. **Design the relational schema** backing the graph — 5 tables:
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
   ├── loader.py
   ├── schema.py
   └── seed_data/
       ├── entities.yaml
       ├── endpoints.yaml
       ├── patterns.yaml
       ├── lookups.yaml
       └── relationships.yaml
   ```
   CLI: `spire kg load --reset`.
4. **Author the seed YAML files** — exactly the 6 entities, ~5 relationships, ~4 patterns, ~3 lookups from Phase B.1.
5. **Define the property graph view** in SQL/PGQ.
6. **Run validation queries** from SQLcl.
7. **Document the populated graph** in `docs/poc/kg_populated.md`.

**Out of scope:** Agent integration, tools exposing the graph (B.4), embeddings, entities beyond design.

**Exit criteria:**
- 5 relational tables exist in Oracle 26ai under `SPIRE`
- Property graph view defined and queryable
- Seed data loaded successfully
- `spire kg load --reset` is idempotent
- Validation queries return expected results

**Time estimate:** 2–4 days.

**Key risks:** YAML authoring rabbit-holes; property graph syntax errors; cross-file inconsistencies (Pydantic validates); modeling drift; idempotency bugs.

**Deliverables:** Populated KG in Oracle 26ai, Python loader, YAML seed files, property graph definition, validation queries.

---

### Phase B.4 — Build the Graph Query Tools

**Goal:** Create curated MCP tools the agent calls to consult the graph. The agent doesn't write SQL/PGQ; it calls these tools and gets structured answers.

**What we'll do:**

1. **Identify the queries the agent needs to make:**
   - `resolve_entity(name)` — "supplier"/"vendor" → canonical entity record
   - `get_canonical_endpoint(entity)` — REST endpoint and traversal notes
   - `get_relationship(from_entity, to_entity)` — join semantics
   - `find_pattern(natural_language_phrase)` — match phrase to pattern
   - `lookup_business_term(term)` — Oracle code for a business term
2. **Build the graph query tools** as MCP tools:
   ```
   src/spire/mcp_server/tools/kg/
   ├── resolve_entity.py
   ├── get_endpoint.py
   ├── get_relationship.py
   ├── find_pattern.py
   └── lookup_term.py
   ```
3. **Implement each tool** against the KG. Most use SQL or SQL/PGQ over the relational tables.
4. **For `find_pattern`**, start with substring matching. Note that embedding-based matching comes in Phase B.6.
5. **Test each tool in isolation** via pytest.
6. **Register tools with the MCP server.** Agent now has Fusion tools + KG tools.
7. **Validate via `fastmcp dev`**.

**Out of scope:** Agent integration with KG (B.5); embedding-based pattern matching (B.6); KG modification by agent (read-only).

**Exit criteria:**
- All KG query tools work in isolation
- All tools registered and validated via `fastmcp dev`
- Tool docstrings are clear enough for the LLM to choose correctly
- Test queries on seed data return expected results

**Time estimate:** 2–4 days.

**Key risks:** Tool catalog grows large (~9–10 tools); pattern matching brittle with substring approach (acceptable for now); SQL/PGQ ergonomics.

**Deliverables:** 5 working KG query tools, pytest coverage, MCP integration confirmed.

---

### Phase B.5 — Integrate the Graph into the Agent Flow

**Goal:** Modify the LangGraph agent so it consults the KG *before* deciding which Fusion tools to call.

**What we'll do:**

1. **Update the agent's system prompt** to instruct it: "When the user asks a question, first consult the KG tools to understand entities, relationships, and patterns. Then plan and execute Fusion tool calls based on what the KG tells you."
2. **Decide the orchestration pattern.** Two viable options:
   - **Single-loop pattern (recommended):** KG tools and Fusion tools in one toolkit; system prompt guides usage. Simpler.
   - **Two-phase pattern:** Explicit "plan" phase (KG only) then "execute" phase (Fusion only). More controlled but more complex. Defer unless single-loop fails.
3. **Update the LangGraph graph** if using two-phase; otherwise expand tool list and prompt.
4. **Build a trace inspector view** to show, in any run, when the agent consulted the KG and what it received. Crucial for debugging and SME demo.
5. **Iteratively test with progressively harder prompts:**
   - Easy: "Show me suppliers in US"
   - Medium: "Show me suppliers in US with invoices in 2024"
   - Hard: The full POC prompt
6. **Iterate on prompts and pattern descriptions** based on findings.
7. **Document the integration** in `docs/poc/agent_kg_integration.md`.

**Out of scope:** Embeddings (B.6); formal 5-run POC test (B.8); KG modification by agent.

**Exit criteria:**
- Agent reliably consults the KG before Fusion tool calls
- Trace inspector clearly shows KG consultation
- Easy, medium, and hard prompts all flow correctly
- System prompt and integration documented

**Time estimate:** 4–7 days. **Highest-uncertainty phase in Track B.**

**Key risks:** Agent ignores the KG (mitigation: clearer prompt, or switch to two-phase); pattern matching too brittle (improve trigger phrases); over-prompting bias (verify by comparing to Track A with same prompt complexity).

**Deliverables:** Working graph-guided agent, trace inspector, integration documentation.

---

### Phase B.6 — Add Embeddings for Dynamic Tool Retrieval

**Goal:** Replace the static tool list with a dynamic retrieval layer. The full tool catalog is embedded; only top-N relevant tools enter the LLM's context per prompt.

**What we'll do:**

1. **Confirm Oracle 26ai vector readiness** — `VECTOR` data type accessible, HNSW indexes work.
2. **Design the vector schema:**
   ```sql
   CREATE TABLE tool_embeddings (
     tool_id VARCHAR2(100) PRIMARY KEY,
     tool_name VARCHAR2(200),
     description CLOB,
     embedding VECTOR(768, FLOAT32),
     metadata JSON
   );
   CREATE VECTOR INDEX tool_embeddings_idx ON tool_embeddings (embedding)
     ORGANIZATION INMEMORY NEIGHBOR GRAPH
     DISTANCE COSINE WITH TARGET ACCURACY 95;
   ```
3. **Pick an embedding model.** Default: Gemini's `text-embedding-004` for provider consistency. Document the choice.
4. **Build the embedding pipeline** in Python:
   ```
   src/spire/embeddings/
   ├── client.py        (calls embedding model)
   ├── indexer.py       (embeds tool descriptions, stores in Oracle)
   ├── retriever.py     (embeds user prompt, runs vector search)
   └── catalog.yaml     (registry of tool descriptions to embed)
   ```
5. **Embed the existing tool catalog** — all Fusion tools from Track A plus the KG tools. CLI: `spire embeddings reindex`.
6. **Test retrieval quality** — create 10–20 prompt → expected-tool mappings. Verify the retriever surfaces the right tools.
7. **Add the retrieval step to the agent flow** — before invoking the LLM, embed the user prompt, retrieve top-N tools (default N=15), present only those to the LLM along with KG tools.
8. **Upgrade `find_pattern` to use embeddings** instead of substring matching.
9. **Document the retrieval design** in `docs/poc/embeddings_design.md`.

**Out of scope:** Per-tenant vector store isolation (production work); embedding past successful queries (could be added later); fine-tuning the embedding model.

**Exit criteria:**
- Tool catalog embedded in Oracle 26ai VECTOR
- Retrieval returns the right tools for representative prompts
- Agent now operates against a dynamically-retrieved tool set
- `find_pattern` uses embedding similarity
- Retrieval quality benchmarks documented

**Time estimate:** 4–6 days.

**Key risks:** Retrieval quality is a new failure mode — if embeddings miss the right tool, the LLM never sees it (mitigation: tune top-N, verify with curated benchmark); embedding model choice locks in significant migration cost; SQL/PGQ vs vector interaction can be subtle.

**Deliverables:** Working embedding pipeline, retrieval-quality benchmarks, agent integrated with dynamic retrieval, design doc.

---

### Phase B.7 — Integration Polish & Trace Visibility

**Goal:** Before running the formal comparison, make sure Track B's complete flow (KG consultation + embedding-based retrieval + agent loop) is robust and traceable.

**What we'll do:**

1. **End-to-end smoke tests** with several prompts spanning the POC use case.
2. **Trace visibility audit** — for each run, the trace should clearly show:
   - What the user asked
   - Which tools were retrieved by embeddings
   - When and what the KG was consulted for
   - What Fusion tools were called and their results
   - How the agent composed the final answer
3. **Fix any UX or logging gaps** discovered during smoke tests.
4. **Document the full architecture flow** in `docs/poc/track_b_architecture.md`.

**Out of scope:** Formal 5-run POC test (B.8); changes to the KG or embedding model.

**Exit criteria:**
- Track B passes several representative prompts end-to-end
- Traces are clear and complete
- Architecture documentation finalized

**Time estimate:** 1–2 days.

**Deliverables:** Robust end-to-end Track B, clean traces, architecture doc.

---

### Phase B.8 — End-to-End Test with the POC Prompt

**Goal:** Run the same POC prompt through Track B under the same protocol as Track A's Phase A.5.

**What we'll do:**

1. **Confirm environment.** All Fusion tools, KG tools, KG populated, embeddings indexed, agent system prompt finalized.
2. **Use the exact same rubric** as Phase A.5. Apples-to-apples.
3. **Run the prompt 5 times.** Same prompt verbatim. No hints.
4. **Capture full traces** including KG consultations and retrieval steps.
5. **Score against the rubric.** ✅/⚠️/❌ per step.
6. **Additional Track B–specific observations:**
   - Did embeddings retrieve the right tools?
   - Did the agent consult the KG? How many times?
   - Did KG guidance change the tool plan vs. Track A's?
   - Did patterns fire correctly?
   - Did any KG-provided knowledge get ignored?
7. **Document in `phase_b8_track_b_report.md`** — same format as Track A's baseline.

**Out of scope:** Comparison work (B.9); mid-run changes; infrastructure error retries.

**Exit criteria:**
- 5 runs completed and traced
- Each scored against the same rubric
- Honest report written
- Track B–specific observations documented

**Time estimate:** 1–2 days.

**Key risks:** Same as A.5 (non-determinism, scoring discipline, prompt-engineering temptation); plus Track B–specific risk that the agent performs well due to over-prompting rather than KG/embedding value (mitigate by verifying that the *same* system prompt would not have helped Track A).

**Deliverables:** Track B run report with 5 traces, 5 scores, KG and retrieval observations.

---

### Phase B.9 — Capture Comparative Results

**Goal:** Produce the artifact that answers: *"Does Track B meaningfully outperform Track A on this prompt?"*

**What we'll do:**

1. **Build the side-by-side comparison report** at `docs/poc/track_comparison.md`:
   - Section 1: The prompt
   - Section 2: The rubric
   - Section 3: Side-by-side metrics table — Track A vs. Track B
   - Section 4: Failure patterns in Track A and how Track B addressed each
   - Section 5: New failure patterns introduced by Track B (if any — be honest)
   - Section 6: Side-by-side verbatim final answers (one example pair)
   - Section 7: Honest verdict — does the full architecture earn its complexity?
2. **Build the SME-facing demo deck or document** (`docs/poc/sme_demo.md`):
   - 1 section per concept: prompt, architecture diagrams, Track A trace, Track B trace with KG and retrieval highlighted, metrics, verdict
3. **Make a clear recommendation:**
   - **If Track B clearly wins:** validates the architecture; recommend committing to production build
   - **If Track B marginally wins:** evaluate whether KG/embedding complexity is worth the gain; consider whether the prompt was a good test
   - **If Track B doesn't win:** significant finding; investigate whether the KG, the embeddings, or the integration design needs revisiting
4. **Preserve all artifacts** in `traces/phase_b8/` and the full reports.
5. **Identify open questions** for the production roadmap.

**Out of scope:** Starting the production build; revising Track A or B based on the comparison (those phases are closed).

**Exit criteria:**
- Side-by-side comparison report completed
- SME-facing demo material ready
- Clear recommendation on next steps
- All artifacts preserved

**Time estimate:** 1–2 days.

**Key risks:** Spinning the results (resist — honest verdicts compound trust); over-claiming on small differences (use the metrics, not narrative); making the SME demo overly polished instead of investigative.

**Deliverables:** Comparison report, SME demo material, recommendation, preserved artifacts. **Track B is now complete.**

---

## 7. Comparative Evaluation

The POC's central output is the comparison between Track A and Track B. Both tracks use the same prompt, same rubric, same 5-run protocol, same metrics. The metrics table:

| Metric | Track A | Track B | Δ | % change |
|---|---|---|---|---|
| Correctness (avg, 0–10) | | | | |
| Tool calls made (avg) | | | | |
| Tool selection accuracy | | | | |
| Time to final answer | | | | |
| Tokens consumed | | | | |
| Estimated cost (USD) | | | | |
| KG consultations | n/a | | | |
| Retrieved tools (avg) | n/a | | | |
| Useful to consultant? | | | | |

**Attribution caveat for the comparison:** Because Track B introduces *both* the KG and embeddings simultaneously, attributing Track B's improvements (or lack thereof) between the two layers requires careful trace analysis. The comparison establishes whether the full architecture is worth building; it does not cleanly isolate whether the KG alone or embeddings alone would have sufficed. For a deeper attribution analysis, a future evaluation could disable one layer at a time.

---

## 8. Working Principles

Principles that guide every phase, codified here so they don't have to be re-stated:

1. **Approval gates are mandatory.** No phase begins implementation until its detailed plan is approved.
2. **Smaller steps are better than larger ones.** Most phases break into sub-phases.
3. **Test before integrating.** Every layer is tested in isolation before being wired into the next.
4. **Honest baselines.** No prompt-engineering "to help it." Whatever it does, that's the data.
5. **One database for everything in the POC.** Oracle 26ai stores relational, graph, and vector. No separate Neo4j, no pgvector.
6. **Metadata in, data out.** Spire never replicates customer transactional data.
7. **Endpoints, not tables.** All Fusion data access is via published REST endpoints.
8. **Document as you go.** Every phase produces written deliverables.
9. **Reuse aggressively.** Track B reuses Track A's tools, MCP server, agent skeleton, CLI, report format.
10. **Resist scope creep.** Especially in design phases (KG design, embedding strategy).

---

## 9. Open Questions & Future Considerations

Items deferred or unresolved at the time of this plan:

**Pod access timeline:** The single biggest schedule risk. Acquisition of a Fusion test pod (OPN, customer sandbox, or paid) is on the critical path. All other planning assumes this is in flight.

**Endpoint discovery at scale:** Beyond the supplier/invoice/PO/buyer set, Spire's catalog will grow. A discovery pipeline (parsing OpenAPI specs, ingesting documentation) is needed for production. Out of scope for the POC.

**Authentication evolution:** Basic Auth for the POC; OAuth 2.0 for production. The persona system should accommodate both without rework.

**Pagination:** Single-page fetches with adjustable `limit` for the POC. Production needs proper pagination.

**Multi-tenancy:** The POC uses a single tenant. Production requires per-tenant isolation of KG overlays, embeddings, audit logs, and credentials.

**Result caching:** No caching in the POC. Whether to introduce caching is a production conversation.

**Streaming and UI:** CLI-only for the POC. A web UI per the Spire vision is post-POC work.

**Compliance:** SOC 2, ISO 27001, GDPR considerations for production deployment.

**Comparison to Oracle's Select AI:** Oracle ships a native NL-to-SQL feature in 26ai. Strategic positioning of Spire vs. Select AI deserves explicit thought before going to market.

**Embedding model choice for production:** Default to Gemini's embeddings for provider consistency, but benchmark against alternatives during Phase B.6.

**Attribution of Track B improvements:** As noted in section 7, the comparison doesn't cleanly isolate the contributions of the KG and the embeddings. A follow-up evaluation can disable one layer at a time if warranted.

**Whether to add a Design 1 (Reference Library) baseline:** If the SME pushes for explicitly testing their proposed architecture, the POC plan can be reframed to include it as a third track. This would lengthen the POC but provide more evidence-based decision support.

---

## Document End

This master plan is a living document. As the POC progresses, phase reports and the final comparison report will be linked back to this plan. Updates should be tracked in version control.

**Last updated:** Plan generation date (see git history)
**Status of plan execution:** Not started — awaiting kickoff (blocked on Fusion pod access)