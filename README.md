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

Then, in two terminals:

```bash
# Terminal 1 — MCP server (keep running)
python -m spire.mcp_server.server

# Terminal 2 — run a prompt
python scripts/promptkit.py --run --prompt "List all suppliers in India"
```

Full setup, keys, diagnostics, prompt sets, and troubleshooting are in
[`how-to-run.md`](how-to-run.md).

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

- **promptkit** (`scripts/promptkit.py`): one tool to run a single prompt, run
  a whole prompt set end to end, or validate that prompts still route to the
  right module and tool. See [`how-to-run.md`](how-to-run.md) §5.

---

## Tests

```bash
python -m pytest -q                  # ~886 passed, 18 deselected (integration)
python -m pytest -q -m integration   # needs MCP server + KG + a provider key
```

---

## License

See [`LICENSE`](LICENSE).
