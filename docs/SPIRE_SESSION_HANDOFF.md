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
- `spire_pipeline_playbook.md` — how-to-add-a-prompt playbook

## Current state

PO module complete. AR module in progress.

- **AR-P2 Shape A** ✓ merged — prompts 11, 12, 2 (AR invoice by-id + lines).
- **AR-P2 Shape B** ✓ merged — prompt 15 (a customer's invoices via account
  traversal).
- **AR-P2c** ✓ merged THIS SESSION — prompt 1 (open invoices for a
  customer). Mechanism: `open_only` is a PARSED ARG on the existing
  HAS_CUSTOMER_TRANSACTION traversal — NOT a KG filter, NOT a schema
  change. Parser detects open/outstanding/unpaid → sets `open_only`;
  planner Block 3 injects `open_only=True` into the CustomerTransaction
  include step's tool_args (scoped by entity name); the tool sorts
  `TotalBalanceAmount:desc` (sortable but NOT queryable on this pod) and
  keeps positive-balance Invoice rows client-side. Verified end-to-end.

KG unchanged by AR-P2c (no rows added): still **15 entities, 125 fields,
12 edges, 21 filters, 85 vocab, 7 entity-tools, 11 edge-tools**. Full
suite: **391 passing** (was 388; +3 this session).

## Also shipped this session (bundled into the AR-P2c merge)

- **LLM output-token cap** in `build_llm` (`config.py`),
  `LLM_MAX_OUTPUT_TOKENS = 8000`, all providers. Without a cap a
  non-converging structured-output parse generates to the model ceiling
  (65520 on gemini-flash) → ~4-minute hang. The cap makes it fail fast.
  8000 chosen because the synthesizer legitimately needs ~3400 tokens to
  narrate a 25-row list (2000 clipped it); 8000 is safely above real need
  and well below the runaway.

## Hard-won lesson from this session (put in spire_design_decisions.md)

**A boolean-flag parser instruction belongs in its own labeled section,
not buried among entity-routing bullets.** AR-P2c's `open_only`
instruction, when placed inside the dense customer-invoices bullet list,
destabilized Gemini structured-output into the max-token runaway EVERY
time the flag should fire (`open`/`outstanding`/`unpaid` all triggered
it; plain prompt 15 was fine). Moving it to a standalone labeled section
(mirroring `count_only`'s structure) fixed it completely — parse dropped
from ~260s/out=65520 to ~6s/out~250. Placement mattered as much as
wording. The token cap (above) was what made this diagnosable — each test
went from 260s to ~12s.

## Parked (in the plan's Reliability backlog)

1. **Open-invoices top-N limit** — prompt 1 is "top 5" but AR-P2c shipped
   `open_only` only; it returns ALL open invoices, not 5. The tool already
   takes `limit` and returns balance-desc, so: parser extracts "top N" → a
   limit on the Intent → planner passes it to the CustomerTransaction step.
   Small; finishes prompt 1.
2. **Parser runaway defence** — the token cap (done) is item (a). Remaining:
   detect `finish_reason=length` / out-near-ceiling and log/retry; a
   wall-clock timeout on the parse; document the failure mode.
3. **Synthesizer does arithmetic (pre-existing)** — the CustomerAccount
   narration sums amounts in prose and gets it wrong (observed on prompt 1:
   a wrong "combined original amount"; the account's negative credit
   balance reported as the open-invoice total). Violates the no-arithmetic
   rule. Affects Shape B narration generally, not just open invoices.

## Next activities (AR module, in order)

Remaining AR prompts (13 of 18): see the AR — Prompts table in the plan.

1. **AR-P3** — prompt 3 (tax lines: deep-nested grandchild, invoice → line
   → taxLines, needs 3-id iteration like PO distributions) + prompt 4 (DFF —
   TWO DFF children exist, must pick which).
2. **AR-P4** — credit memos: list + total value (prompts 5, 14).
3. **AR-P5** — account children (prompts 6, 7, 8, 9, 13).
4. **AR-P6** — the three aggregates (prompt 10 exposure ranking; prompt 16
   DSO / cash-collection trends; prompt 17 receipt-method distribution;
   prompt 18 creation-vs-update lag).

(Consider closing the top-N limit before/with AR-P3 — it's small and
finishes an already-shipped prompt.)

## Build sequence (followed per prompt — KEEP DOING THIS)

curl discovery → standalone tool(s), pod-proven in isolation → KG rows
(rebuild from scratch) → planner → parser → server wrapper → synthesizer
(FIVE places, do all at once) → run_plan.py display → tripwire bump →
tests → verify → branch / PR / merge.

The synthesizer's five places (miss one and it errors):
1. registry (`SYNTHESIS_SCHEMAS`)
2. `_SYSTEM_PROMPT_BY_ENTITY`
3. id-harvest (`_collect_valid_ids`)
4. validator function
5. validator dispatch dict

NOTE: AR-P2c touched NONE of these — it added no entity (reused
CustomerAccount from Shape B) and no KG rows. Not every phase is a
five-place change; a modifier on an existing traversal can be
parser + planner only.

## Key conventions

- KG rebuilds from scratch: `python scripts/rebuild_kg.py`. Bump tripwires
  in `scripts/print_kg.py` AND `tests/test_kg_metadata.py` ONLY when KG
  rows change (AR-P2c changed none, so no bump).
- One command at a time, verify each step. Output to `t.txt` (overwrite `>`,
  append `>>`). Heredoc for throwaway scripts (no file needed).
- Ask permission before generating code or significant content.
- Git: one branch per change (`ar-phase-N-description`), PR-based, named
  files in `git add` (NEVER `-A`), heredoc commit messages. Docs-only
  changes may go straight to master.
- FILE DRIFT: working files change as we build. Always re-share the CURRENT
  version of a file before editing — do not rely on an earlier upload.

## Pod quirks that mattered this session

- `TotalBalanceAmount` (on the `transactionPaymentSchedules` child) is
  **sortable but NOT queryable** — `q=TotalBalanceAmount>0` is rejected,
  but `orderBy=TotalBalanceAmount:desc` works. This is the open-invoice
  window strategy (recorded in the endpoints reference, 2026-07-21).
- An account can carry thousands of rows (the ABC Corporation Americas
  anchor has 7,404). The open filter is applied via SORT + client-side
  `>0`, not paging.
- Anchor: customer "ABC Corporation Americas" → one account, AccountId
  300000047368527, with open invoices; top balances 216378, 206008,
  198286, 56412, 39969. 91 open invoices total on that account.

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
- `src/spire/nl_parser/draft.py`
- `src/spire/mcp_server/server.py`
- `src/spire/synthesizer/synthesizer.py`
- `src/spire/executor/executor.py` (AR-P3 needs it — 3-id grandchild
  iteration for tax lines, same pattern as PO distributions)
- `scripts/run_plan.py`
- `scripts/print_kg.py`, `tests/test_kg_metadata.py`, `tests/test_synthesizer.py`

For AR-P3 specifically the executor matters most (the tax-lines grandchild
is a 3-id iteration like PO distributions — HAS_DISTRIBUTION's
`iter_fields` map is the precedent).
