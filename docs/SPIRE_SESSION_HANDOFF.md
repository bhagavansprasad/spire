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

- `spire_expansion_plan.md` — master build plan (start here; now current
  through AR-P3 tax lines)
- `spire_architecture.md` — current-state reference
- `spire_design_decisions.md` — frozen design records
- `spire_fusion_endpoints_reference.md` — pod quirks + curl reference (the
  authority on pod behavior)
- `spire_pipeline_playbook.md` — how-to-add-a-prompt playbook

## Current state

PO module complete. AR module in progress: **6 of 18 AR prompts done**.

Done and merged (AR):
- **AR-P2a** — AR invoice by-id + lines (prompts 11, 12, 2).
- **AR-P2b** — a customer's invoices via account (prompt 15).
- **AR-P2c** — open invoices for a customer (prompt 1, `open_only`).
- **Top-5 open-invoices limit** (`ar-invoice-limit-top-n`) — finishes
  prompt 1. `invoice_limit` parsed arg, gated to the open-invoices shape;
  planner Block 3 passes it as the fetcher's `limit`. Parser + planner
  only, no KG rows.
- **AR-P3 tax lines** (`ar-p3-tax-lines`, merged 2026-07-21) — prompt 3.
  See below.

KG now: **16 entities, 137 fields, 13 edges, 12 edge-tools**, 21 filters,
7 entity-tools, 85 vocab, 3 patterns. Full suite: **399 passing**.

## AR-P3 tax lines — what shipped this session (the important detail)

"AR invoice X and its tax lines" fetches each line's tax lines
(jurisdiction/rate/amount) and nests them under the parent line.

**Shape: TWO ids, not three.** The plan first assumed the PO-distribution
3-id pattern; verify proved it wrong. Tax lines need only invoice id +
line id, so HAS_TAX_LINE is a **two-field `iter_fields`** edge off
ReceivablesInvoiceLine → ReceivablesTaxLine.

**Two mechanisms added (both general, both caught by end-to-end verify):**

1. **Executor `_parent_stamp`, GATED by `Step.stamp_parent_key`.** AR
   invoice lines do NOT echo `CustomerTransactionId` in the row body, so a
   grandchild step that must iterate on the invoice id has no source for
   it. The executor now stamps the parent iteration key onto child rows —
   but ONLY when the planner sets `stamp_parent_key` on a child step that
   feeds a further include. Off by default, so every other iterating
   step's output is byte-for-byte unchanged (this gating fixed 4
   regressions the ungated version caused).

2. **The tax-lines tool stamps its own parent line id** as
   `ParentCustomerTransactionLineId`. The tax row's own
   `CustomerTransactionLineId` is the TAX-line PK (e.g. 112), a DIFFERENT
   value from the parent line id (74) — so the synthesizer nests by
   `ParentCustomerTransactionLineId == line.CustomerTransactionLineId`.

Files touched (all merged): new tool `receivables_invoice_tax_lines.py`,
server wrapper, `kg_schema.sql` (entity+12 fields+edge+binding),
`print_kg.py` + `test_kg_metadata.py` tripwires (16/137/13/12), parser
(tax-lines include rule), planner (Step flag + Block 3 + `_TOOL_PRIMARY_ARG`),
synthesizer (ReceivablesTaxLineInfo nested + validator + prompt),
executor (`_parent_stamp` gated), `run_plan.py` (nested display),
`prompt_set_ar.txt` (tax anchor + prompt), `test_executor.py` +
`test_synthesizer.py`.

Taxed anchor: invoice **1002** (TransactionNumber 5), line **74** →
2 tax lines (STATE 6.5%, COUNTY 2.25%); lines 84/93/107 also carry 2 each.
The 61765 anchor from earlier phases is UNtaxed (count:0, not 404).

## Next activities (AR module, in order)

**12 AR prompts left.** Next is prompt 4 to finish AR-P3.

1. **AR-P3 DFF (prompt 4)** — finishes AR-P3. Must pick between
   `receivablesInvoiceDFF` and `receivablesInvoiceTransactionDFF` (two DFF
   children exist — see endpoints-reference quirk 8). Decide which the
   prompt wants before wiring.
2. **AR-P4** — credit memos: list + total value (prompts 5, 14).
3. **AR-P5** — account children, all keyed by `AccountId`: activity/balance
   summary (6), account credit memos (7), account receipts (8), receipt
   applications (9), site-filtered receipts (13).
4. **AR-P6** — aggregates (op-registry, like PO's): exposure ranking (10),
   DSO / cash-collection (16), receipt-method distribution (17),
   creation-to-update lag (18).

Two complications flagged in the plan for later:
- Prompt 16 (DSO) spans two endpoints (`/standardReceipts` + AR balance) —
  decide one aggregate tool vs two composed.
- Prompt 13 (site-filtered receipts) — confirm a Santa Clara receipt
  anchor exists first; the demo's ABC-entity family is a trap (ABC
  Corporation Americas / Worldwide / ABC Application Software are different
  customers).

## Build sequence (followed per prompt — KEEP DOING THIS)

curl discovery → standalone tool(s), pod-proven in isolation → KG rows
(rebuild from scratch) → planner → parser → server wrapper → synthesizer
(five places, do all at once) → run_plan.py display → tripwire bump →
tests → verify end-to-end → branch / PR / merge.

The synthesizer's five places (miss one and it errors):
1. registry (`SYNTHESIS_SCHEMAS`)
2. `_SYSTEM_PROMPT_BY_ENTITY`
3. id-harvest (`_collect_valid_ids`)
4. validator function
5. validator dispatch dict

NOTE: not every phase is a five-place change. AR-P3 tax lines EXTENDED an
existing entity (ReceivablesInvoice) rather than adding a new rooted one,
so it touched the schema + validator + prompt, not all five. A modifier on
an existing traversal (like the top-5 limit) can be parser + planner only.
Reason from the actual shape, not the worst case.

## Hard-won lessons this session

- **Verify end-to-end at each stage — don't trust "no change needed"
  reasoning.** AR-P3 had THREE design corrections that only surfaced by
  running the full pipeline: (a) HAS_TAX_LINE is 2-id not 3-id (missing
  `_TOOL_PRIMARY_ARG` entry); (b) the line child doesn't carry the invoice
  id (→ executor stamp); (c) the tax-row PK collides with the parent line
  id (→ distinct `ParentCustomerTransactionLineId`). Each was caught by a
  failing run, not by inspection.
- **A general executor capability must be opt-in.** The `_parent_stamp`
  ungated broke 4 existing tests by polluting every iteration's output.
  Gating behind a Step flag the planner sets deliberately kept all other
  behavior byte-for-byte identical.
- **A child endpoint often does not echo its parent id.** Confirmed for AR
  invoice lines (no `CustomerTransactionId` in the body). Any future
  grandchild iteration must account for this.

## Key conventions

- KG rebuilds from scratch: `python scripts/rebuild_kg.py`. Bump tripwires
  in `scripts/print_kg.py` AND `tests/test_kg_metadata.py` ONLY when KG
  rows change (count of rows — not a column value on an existing row).
- One command at a time, verify each step. Output to `t.txt` (overwrite `>`,
  append `>>`). Heredoc for throwaway scripts.
- Ask permission before generating code or significant content.
- Git: one branch per change (`ar-phase-N-description`), PR-based, named
  files in `git add` (NEVER `-A`), heredoc commit messages. Docs-only
  changes may go straight to master.
- FILE DRIFT: working files change as we build. Always re-share the CURRENT
  version of a file before editing — do not rely on an earlier upload.
- `spire_fusion_endpoints_reference.md` is the pod authority — update it
  after every new curl discovery.

## Pod quirks that mattered this session

- AR tax lines: grandchild at
  `/receivablesInvoices/{id}/child/receivablesInvoiceLines/{lineId}/child/receivablesInvoiceLineTaxLines`.
  Two ids (invoice + line) in the URL path. Untaxed lines return
  `count:0`, not 404.
- The tax-line row's own `CustomerTransactionLineId` is the TAX-line PK,
  distinct from the parent line id. Don't conflate.
- AR invoice line rows do NOT expose `CustomerTransactionId` — the parent
  invoice id is absent from the child body and cannot be projected via
  `?fields=` (400s if you try).

## Files to share in the new window

Core docs (upfront):
- `docs/spire_expansion_plan.md`
- `docs/spire_fusion_endpoints_reference.md`

Context bundles (upfront — these carry the code):
- `context_parser_planner.md`
- `context_mcp_server_tools.md`
- `context_graph_kg.md`

Per-step (share the ACTUAL current file when the step is reached — file
drift):
- `scripts/sql/kg_schema.sql`
- `src/spire/planner/planner.py`
- `src/spire/nl_parser/parser.py`
- `src/spire/nl_parser/draft.py`
- `src/spire/mcp_server/server.py`
- `src/spire/synthesizer/synthesizer.py`
- `src/spire/executor/executor.py`
- `scripts/run_plan.py`
- `scripts/print_kg.py`, `tests/test_kg_metadata.py`,
  `tests/test_synthesizer.py`, `tests/test_executor.py`

For AR-P3 DFF (prompt 4) specifically: it's an invoice child like tax
lines but likely a plain single-parent child (not a grandchild), so it may
be lighter — probably no executor change. The DFF-child pick (which of the
two) is the real question; resolve it with curl first.
