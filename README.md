# Spire

**AI-native workspace for Oracle Fusion Cloud developers and consultants.**

Spire turns natural-language questions about a Fusion Cloud pod into
real, verifiable answers — using a Knowledge Graph + a deterministic
planner + an MCP-based tool layer + an LLM synthesizer with a
hallucination guard.

The anchor question:

> *"Show me suppliers in US with no invoices in 6 months but with
> open purchase orders, including the buyer assigned to each."*

The Design 3 v1.1 pipeline answers this end-to-end against a live
Fusion pod in ~2 minutes, scoring **7/7 on a 7-row rubric across 3
runs**. See [`docs/design3_measurement_report.md`](docs/design3_measurement_report.md).

---

## Architecture at a glance

```
prompt
  │
  ▼                         ┌─────────────────────────────┐
[Intent parser]             │  Coming in Phase C of the   │
  │  (NOT YET BUILT —       │  roadmap. Today the Intent  │
  │   intent is hardcoded   │  is supplied via --intent   │
  │   via run_plan.py)      │  arg on run_plan.py.        │
  ▼                         └─────────────────────────────┘
Intent
  │
  ▼
[Planner]  ── reads ──▶  Knowledge Graph (Oracle 26ai)
  │                       - 8 tables, ~83 rows
  │                       - entities, edges, patterns, vocab,
  │                         bindings, tool maps
  │                       - NO LLM in planning
  ▼
Plan (list[Step])
  │
  ▼
[Executor] ── calls ──▶  MCP server  ── calls ──▶  Oracle Fusion REST API
  │                       (5 tools)                (live pod, real data)
  │                       - NO LLM in execution
  ▼
outputs (dict[output_name, list[dict]])
  │
  ▼
[Synthesizer] ──── calls ──▶  Gemini 2.0 Flash
  │   - Pydantic-typed structured output
  │   - Hallucination guard: every ID in the response is
  │     cross-checked against the executor's source data;
  │     invented IDs raise HallucinationError
  ▼
SynthesizedResponse (validated; prose summary + structured suppliers)
```

The LLM is the ONLY non-deterministic part of the pipeline, and even
its output is bounded by a Pydantic schema and validated against
ground truth.

---

## Quick start

### Prerequisites

- Python 3.12+
- An Oracle 26ai container running locally (the KG lives here)
- Network reachability to a Fusion Cloud demo pod
- A `GEMINI_API_KEY` environment variable

### Setup

```bash
# Clone and install
git clone https://github.com/bhagavansprasad/spire.git
cd spire
python -m venv ~/venv/spire
source ~/venv/spire/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -e .

# Configure your Fusion pod credentials
cp personas.example.yaml personas.yaml
# Edit personas.yaml with your pod details (see file comments)

# Populate the Knowledge Graph
./scripts/rebuild_kg.sh
```

See [`how-to-run.md`](how-to-run.md) for full setup details including
the MCP server and credential management.

### Run end-to-end

```bash
# Terminal 1: start the MCP server
python -m spire.mcp_server.server

# Terminal 2: run the deterministic pipeline (the Design 3 path)
python scripts/run_plan.py
```

Defaults to the original Track A prompt
(`--intent original`). Use `--intent anchor` for the simpler v1
anchor without the negation clause.

---

## Key concepts

### Knowledge Graph (Oracle 26ai)

Metadata about Fusion's structure, not Fusion data. Encodes:

- **Entities** (Supplier, Invoice, PurchaseOrder, Buyer, Address) and
  their endpoints + canonical id fields
- **Edges** with their join fields per direction — crucial because
  Fusion's endpoints are inconsistent (e.g., HAS_INVOICE joins on
  `SupplierNumber` but HAS_PURCHASE_ORDER joins on `SupplierId`)
- **Patterns** (`status_filter`, `country_filter_via_address`,
  `no_child_in_N_months`) — reusable query shapes the planner
  composes
- **Vocabulary** mapping ("United States" → "US", "open" → "OPEN",
  etc.)
- **Tool bindings** — which MCP tool fetches which entity / traverses
  which edge

Rebuild with `./scripts/rebuild_kg.sh`. The full schema is documented
in [`docs/designs/kg_schema_v1.md`](docs/designs/kg_schema_v1.md).

### Planner (Python, deterministic)

Reads an `Intent`, queries the KG, emits an executable `Plan` (list
of `Step`). No LLM. ~600 lines of Python; 102 unit tests.

See [`src/spire/planner/planner.py`](src/spire/planner/planner.py) and
[`docs/designs/phase_2_planner_design.md`](docs/designs/phase_2_planner_design.md).

### Executor (Python, deterministic)

Consumes a `Plan` step by step, calls the MCP tools, aggregates
results. Handles three step shapes: non-iterating, iterating-and-
accumulate, and iterating-and-filter-source (the negation-by-absence
semantic added in F2).

See [`src/spire/executor/executor.py`](src/spire/executor/executor.py).
45 unit tests + 3 live-Fusion integration tests.

### Synthesizer (LLM, schema-constrained)

The only LLM in the pipeline. Takes the executor's outputs dict and
produces a Pydantic-typed `SynthesizedResponse`. Cross-validates every
ID (`SupplierId`, `SupplierNumber`, `PersonId`) against the source
data; invented IDs raise `HallucinationError`.

See [`src/spire/synthesizer/synthesizer.py`](src/spire/synthesizer/synthesizer.py).
22 unit tests + 1 live-Gemini integration test.

### MCP server (5 tools)

A FastMCP server exposing 5 Oracle Fusion REST tools:

| Tool | What it does |
|---|---|
| `search_suppliers` | List suppliers |
| `search_suppliers_by_country` | Country-filtered (uses `expand=addresses`) |
| `search_invoices` | Per-supplier invoices, optional date filter |
| `search_purchase_orders` | Per-supplier POs |
| `get_buyer` | HCM `publicWorkers` lookup by PersonId (cross-pillar) |

See [`src/spire/mcp_server/tools/`](src/spire/mcp_server/tools/).

---

## Two paths through the codebase

This repo contains two architectures:

**Track A — Direct tool orchestration** (`scripts/ask.py` + LangGraph
agent). The original baseline. LLM-as-planner. Scores 1/7 on the
anchor question across 5 runs. Documented as the baseline; not the
path forward.

**Design 3 — Graph-guided orchestration** (`scripts/run_plan.py`).
The current path. KG-driven planner, deterministic executor, schema-
constrained LLM synthesizer. Scores 7/7 on the same question across
3 runs.

The architectural rationale is in
[`docs/designs/spire_design_alternatives.md`](docs/designs/spire_design_alternatives.md).
The measurement gap between them is documented in
[`docs/phase_a5_baseline_report.md`](docs/phase_a5_baseline_report.md)
(Track A baseline) and
[`docs/design3_measurement_report.md`](docs/design3_measurement_report.md)
(Design 3 v1.1).

---

## What this is NOT

Honest scope. The 7/7 result is on **one prompt against one demo
pod**. Areas explicitly NOT yet built:

- **LLM intent parser.** Today the `Intent` is hardcoded in
  `run_plan.py`. Adding the natural-language → `Intent` layer is
  Phase C of the roadmap.
- **Generalized synthesizer schema.** Today the `SynthesizedResponse`
  schema is specific to the supplier→buyer answer shape. Different
  questions need different schemas. Phase B of the roadmap.
- **Production hygiene.** Sequential Fusion calls; no parallelism,
  no caching. Phase E of the roadmap.
- **Multi-tenant / multi-pod.** Single-pod, single-credential
  today.
- **A UI.** CLI / API only.

See
[`docs/designs/design3_v1_to_production_roadmap.md`](docs/designs/design3_v1_to_production_roadmap.md)
for the planned Phases A–F.

---

## Repository structure

```
src/spire/
  agent/         # Track A (LangGraph) runner, prompts, tracing
  config.py      # Persona/credentials loading
  executor/      # Design 3 deterministic executor
  fusion/        # HTTP client for Oracle Fusion REST
  kg/            # KG loader (markdown bundle for the Track A path)
  mcp_server/    # FastMCP server exposing the 5 tools
  oracle/        # Async Oracle client (for KG queries)
  planner/       # Design 3 KG-driven planner
  synthesizer/   # Design 3 LLM synthesizer with hallucination guard

scripts/
  ask.py             # Track A entry point (NL prompt → LangGraph)
  run_plan.py        # Design 3 entry point (hardcoded Intent → pipeline)
  rebuild_kg.sh      # Reload the KG from scratch
  ...

tests/             # 235 tests passing; 5 deselected (integration)
docs/              # Design docs, measurement reports, working log
```

---

## Status & current results

- Test suite: **235 passing**, 5 deselected (integration; opt-in via
  `pytest -m integration`)
- Design 3 v1.1 on the anchor question: **7/7 across 3 runs**
- Track A baseline on the same question: **1/7 averaged across 5
  runs**
- Stable point: tag
  [`design3-v1.1-7of7`](https://github.com/bhagavansprasad/spire/releases/tag/design3-v1.1-7of7)

---

## License

See [`LICENSE`](LICENSE).
