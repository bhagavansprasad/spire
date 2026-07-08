# Spire — Session Handoff

Snapshot of where the Spire project stands, written so a new working
session (or person) can continue without re-deriving context.

Repo: `github.com:bhagavansprasad/spire` · working dir `~/pocs/spire`
(also runs as user `saketh` at `~/spire`). Branch flow: branch → PR →
merge to master.

---

## What Spire is

Converts a natural-language procurement prompt into a structured answer
against a live Oracle Fusion pod:

```
prompt → parse (LLM) → plan (deterministic) → execute (MCP tools) → synthesize (LLM)
```

This is "Design 3": a **bounded** pipeline, deliberately not an agent.
The LLM is confined to two single-shot roles (parser, synthesizer); the
planner and executor are deterministic. KG metadata (entities, fields,
edges, vocabulary, tool bindings) lives in Oracle tables and constrains
what the parser can produce.

Only **Supplier** is a valid query target entity. Invoice/Contract-rooted
prompts are refused by design.

---

## Current architecture

**Entry point:** `scripts/run_graph.py` — runs the pipeline as a
LangGraph custom graph (`src/spire/graph/pipeline.py`). The graph has
four nodes (parse → plan → execute → synthesize) wrapping the existing
functions; refusal and node errors short-circuit to END. It is bounded —
fixed edges, no tool-calling loop. This replaced the imperative
`run_plan.py` as the primary path; `run_plan.py` is retained for now.

**LLM provider seam:** `config.build_llm()` selects the provider from
`SPIRE_LLM_PROVIDER` (gemini | openai | anthropic), model overridable via
`SPIRE_LLM_MODEL`. Parser and synthesizer call `build_llm()`. Each run
prints `[llm] provider=… model=…`.

**MCP:** server and client both use `fastmcp`. Server exposes the tools;
`run_graph.py`/`run_plan.py` open `async with Client(url)` and the
executor calls `session.call_tool(...)`.

**Aggregation:** `aggregate_invoices_by_supplier` ranks suppliers by
spend over a date range. Paginates the full range (200/page, 50-page
cap), reports per-page progress back to the caller. Bounded tool, not a
generic engine.

**Credentials:** all DB credentials come from `personas.yaml` (gitignored)
or `SPIRE_DB_*` env vars — no hardcoded passwords. KG rebuild via
`scripts/rebuild_kg.py` (network-based, oracledb; works local or remote;
SQL in `scripts/sql/kg_schema.sql`).

---

## Provider status

- **Gemini** — default. Verified live (via Vertex AI on bhagavan's
  setup; public API key also supported).
- **OpenAI** — wired, verified live (gpt-5 via SPIRE_LLM_MODEL; default
  gpt-4o). Needs a funded account.
- **Anthropic** — wired, NOT yet verified live. The committed default
  model ID may be stale; use a current ID (`claude-sonnet-4-6` or
  `claude-opus-4-8`) and a funded key. Confirm structured output works on
  the parser/synthesizer schemas.

---

## How to run (quick)

```bash
# Terminal 1
python -m spire.mcp_server.server
# Terminal 2
python scripts/run_graph.py --prompt "List all suppliers in India"
# switch provider
SPIRE_LLM_PROVIDER=openai python scripts/run_graph.py --prompt "..."
# batch
python scripts/run_prompt_set.py
# tests
pytest tests/
```

Full setup/keys/prompts: `how-to-run-02.md`. Roadmap and open tasks:
`docs/feature_roadmap.md`.

---

## Done recently (merged to master)

- Feature 7 — aggregation (supplier spend ranking), with pagination fix
  (was reading only the first 500 of 8534 invoices → wrong rankings).
- fastmcp migration on the client side.
- MCP progress reporting (tool → server → graph → caller).
- DB credential centralization into `personas.yaml`; network-based
  `rebuild_kg.py`.
- LangGraph pipeline (Option A, bounded) as the primary entry point.
- Multi-provider seam: Gemini + OpenAI + Anthropic wired.
- `how-to-run-02.md` rewritten (setup / keys / run / prompts / legacy).

---

## Open tasks (see docs/feature_roadmap.md → Future tasks)

1. **Retire Track A** — remove `scripts/ask.py` and `src/spire/agent/`;
   `run_graph.py` is the single entry point now. Deliberate cleanup.
2. **Parallelize the aggregation fetch** — currently ~185s/prompt
   (sequential ~43 pages). Count first, then `asyncio.gather` the pages.
3. **Finish Anthropic** — verify end-to-end with a valid model ID +
   funded key; check structured-output parity across providers.
4. **Feature 6 — contracts** — add Contract entity + `search_contracts`
   so "contract renewals" stops being refused (still pending design).

---

## Gotchas learned this work

- `pyppeteer` (for graph PNG) downgrades `websockets` to 10.4, breaking
  uvicorn (MCP server) and google-genai. Fix: `pip install
  'websockets>=13,<17'` and don't use pyppeteer — the default
  `draw_mermaid_png()` (remote renderer) is used instead. PNG auto-saves
  on graph build when `SPIRE_GRAPH_PNG` is set.
- `src/spire/graph/__init__.py` MUST be empty (a stray `run_graph.py`
  copy there caused `ModuleNotFoundError: run_plan`).
- Vertex vs public Gemini: `GOOGLE_GENAI_USE_VERTEXAI=TRUE` makes the SDK
  ignore the API key and route through the Vertex project. A 429
  "credits depleted" with a working key usually means the wrong routing.
- Multi-user: a ghost `PYTHONPATH` and Vertex auth (`gcloud auth
  application-default login` per user) bit the second user; not a code
  issue.
