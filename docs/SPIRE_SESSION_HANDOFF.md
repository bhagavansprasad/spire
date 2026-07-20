# SPIRE — SESSION HANDOFF

## Project

Spire: an AI-native NL query system over Oracle Fusion procurement data.
Deterministic KG-driven pipeline (Design 3): **parse → plan → execute →
synthesize**. Tool selection is a KG lookup, not an LLM judgment. Not an
agent architecture.

## Repo & environment

- Repo: `github.com/bhagavansprasad/spire`
- Working dir: `~/pocs/spire`, branch `master`
- Pod: `fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com`
- Creds: `personas.yaml` (gitignored) via `load_persona('default_dev')`

## Canonical docs (in `docs/`)

- `spire_expansion_plan.md` — master build plan (start here)
- `spire_architecture.md` — current-state reference
- `spire_design_decisions.md` — frozen design records
- `spire_fusion_endpoints_reference.md` — pod quirks + curl reference (the
  authority on pod behavior)
- `spire_pipeline_playbook.md` — how-to-add-a-prompt playbook (outline stage)

## Current state

PO module complete. AR module in progress:

- **AR-P2 Shape A** ✓ merged — prompts 11, 12, 2 (AR invoice by-id + lines).
  Entities: ReceivablesInvoice, ReceivablesInvoiceLine. Edge HAS_AR_LINE.
- **AR-P2 Shape B** ✓ merged — prompt 15 (a customer's invoices via account
  traversal). Entities: CustomerAccount, CustomerTransaction. Edge
  HAS_CUSTOMER_TRANSACTION. Mechanism: resolve customer by name → traverse
  to that account's transactions, keep Invoice-class client-side.

KG now: **15 entities, 125 fields, 12 edges, 21 filters, 85 vocab, 7
entity-tools, 11 edge-tools**. Full test suite: **388 passing**.

## Next activities (in order)

1. **AR-P2c — prompt 1** (open invoices, top 5). The deferred novel bit:
   wire `open_only` as a filter-driven arg on an edge traversal — nothing in
   the planner does this yet. The tools already carry the `open_only` flag
   (unused). Needs: parser detects "open", planner passes the flag through
   the edge-traversal step. Open = TotalBalanceAmount > 0. Its own phase.
2. **AR-P3** — prompt 3 (tax lines: a deep-nested grandchild,
   invoice → line → taxLines, needs 3-id iteration like PO distributions) +
   prompt 4 (DFF — TWO DFF children exist, must pick which).
3. **AR-P4–P6** — credit memos, account children, and the three aggregates
   (exposure ranking, DSO/cash-collection trends, receipt-method
   distribution).

## Build sequence (followed per prompt — KEEP DOING THIS)

curl discovery → standalone tool(s), pod-proven in isolation → KG rows
(rebuild from scratch) → planner → parser → server wrapper → synthesizer
(FIVE places, do all at once) → run_plan.py display → tripwire bump →
tests → verify → branch / PR / merge.

The synthesizer's five places (miss one and it errors — learned the slow
way in Shape A):
1. registry (`SYNTHESIS_SCHEMAS`)
2. `_SYSTEM_PROMPT_BY_ENTITY`
3. id-harvest (`_collect_valid_ids`)
4. validator function
5. validator dispatch dict

## Key conventions

- KG rebuilds from scratch: `python scripts/rebuild_kg.py`. Bump tripwires
  in `scripts/print_kg.py` AND `tests/test_kg_metadata.py` when KG rows
  change. Also update `tests/test_synthesizer.py`'s empty-outputs id-set
  assertion when the synthesizer gains id sets.
- One command at a time, verify each step. Output to `t.txt` (overwrite `>`,
  append `>>`).
- Ask permission before generating code or significant content.
- Git: one branch per change (`ar-phase-N-description`), PR-based, named
  files in `git add` (NEVER `-A`), heredoc commit messages. Docs-only
  changes may go straight to master.

## Working style

Short questions, interactive, plain-text numbered options (no widgets),
concise, ask before generating. When a decision has options, present them as
a short numbered list and (if asked) give a recommendation.

## Hard-won lessons / pod quirks

- Synthesizer keys entities in FIVE places (above) — do all at once.
- `run_plan.py` has type-dispatched formatters (`_format_synthesized`,
  `_format_summary`) needing a per-entity branch, plus the response import.
- Pod: composite `q=` fails (single clause only); MANY fields are not
  server-queryable (e.g. BillToCustomerName/Number on the invoice endpoint,
  TransactionClass on the schedules child) — filter client-side. CustomerName
  IS queryable on the account endpoint.
- Pod may gzip — use `curl --compressed`. Use `+` for spaces and `%27` for
  quotes in `q=`. Redirect curl to `t.txt`, don't pipe to json.tool (breaks
  on gzip/empty).
- CONFIRM a field is queryable with a curl before designing a server-side
  filter — don't assume.
- Oracle misspells one AR field: `TransacationBusinessCategory` (sic) — must
  be requested with the typo.
- FILE DRIFT: the working files change as we build. Always re-share the
  CURRENT version of a file before editing it, rather than relying on an
  earlier upload. We hit stale-file confusion several times.

## Files to share in the new window

Core docs (upfront):
- `docs/spire_expansion_plan.md`
- `docs/spire_fusion_endpoints_reference.md`

Context bundles (upfront — these carry the code):
- `context_parser_planner.md`
- `context_mcp_server_tools.md`
- `context_graph_kg.md`

Per-step (share the ACTUAL current file when the step is reached):
- `scripts/sql/kg_schema.sql`
- `src/spire/planner/planner.py`
- `src/spire/nl_parser/parser.py`
- `src/spire/mcp_server/server.py`
- `src/spire/synthesizer/synthesizer.py`
- `scripts/run_plan.py`
- `scripts/print_kg.py`, `tests/test_kg_metadata.py`, `tests/test_synthesizer.py`

For AR-P2c specifically, the parser + planner are the focus (the open_only
mechanism). For AR-P3, the executor also matters (the 3-id grandchild
iteration) — share `src/spire/executor/executor.py` too.
