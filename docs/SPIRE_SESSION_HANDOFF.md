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
  through AR-P3 DFF — AR-P3 complete)
- `spire_architecture.md` — current-state reference
- `spire_design_decisions.md` — frozen design records
- `spire_fusion_endpoints_reference.md` — pod quirks + curl reference (the
  authority on pod behavior)
- `spire_pipeline_playbook.md` — how-to-add-a-prompt playbook

## Current state

PO module complete. AR module in progress: **7 of 18 AR prompts done**.

Done and merged (AR):
- **AR-P2a** — AR invoice by-id + lines (prompts 11, 12, 2).
- **AR-P2b** — a customer's invoices via account (prompt 15).
- **AR-P2c** — open invoices for a customer (prompt 1, `open_only`).
- **Top-5 open-invoices limit** (`ar-invoice-limit-top-n`) — finishes
  prompt 1. `invoice_limit` parsed arg, gated to the open-invoices shape;
  planner Block 3 passes it as the fetcher's `limit`. Parser + planner
  only, no KG rows.
- **AR-P3 tax lines** (`ar-p3-tax-lines`, merged 2026-07-21) — prompt 3.
- **AR-P3 DFF** (`ar-p3-dff`, merged 2026-07-21) — prompt 4. Finishes
  AR-P3. See below.

KG now: **17 entities, 140 fields, 14 edges, 13 edge-tools**, 21 filters,
7 entity-tools, 85 vocab, 3 patterns. Full suite: **402 passing**.

## AR-P3 DFF — what shipped this session (the important detail)

"AR invoice X and its DFF values" fetches the invoice's
receivablesInvoiceTransactionDFF child and nests it under the invoice.

**Which DFF child.** AR invoices expose two DFF children (quirk 8). Curl on
invoice 1002: `receivablesInvoiceDFF` returns `__FLEX_Context=null`;
`receivablesInvoiceTransactionDFF` returns `__FLEX_Context="DOO"`. So the
tool targets the **TransactionDFF** child — the populated one. On this pod
the context is set but carries NO segment columns; the row exposes only
`CustomerTrxId`, `__FLEX_Context`, `__FLEX_Context_DisplayValue` (null).

**Shape: a plain single-parent child.** One id in the URL path (like
HAS_AR_LINE), no iteration, no grandchild. This made it the LIGHTEST AR
phase so far:
- **Executor**: no change (the handoff predicted this).
- **Planner**: ONE `_TOOL_PRIMARY_ARG` entry
  (`get_receivables_invoice_transaction_dff` → `customer_transaction_id`).
  Block 3's plain-include branch (iter_fields is NULL) handled the rest.
- **Synthesizer**: 2-place change (schema + prompt), NOT five. The DFF
  extends ReceivablesInvoice and has NO id of its own to validate
  (`CustomerTrxId` echoes the parent), so no harvest and no validator
  change. `ReceivablesInvoiceTransactionDFFInfo` model + a `dff` field on
  the record + the DFF bucket in the ReceivablesInvoice prompt.

**Also fixed: a pre-existing short-id parser bug.** A short
CustomerTransactionId (e.g. 1002) was being silently DROPPED — the parser
produced `target_entity=ReceivablesInvoice` with EMPTY filters/include
because the by_id examples were all the 18-digit form and the LLM did not
treat "1002" as a CustomerTransactionId. The by_id rule now states the id
may be short and must still get a by_id filter regardless of length. This
also unblocked the **tax-lines prompt (prompt 3)**, which uses 1002 and was
NOT actually passing end-to-end until this fix (it shared the same bug).

Files touched (all merged): new tool
`receivables_invoice_transaction_dff.py`, server wrapper, `kg_schema.sql`
(entity + 3 fields + edge + edge-tool), `print_kg.py` +
`test_kg_metadata.py` tripwires (17/140/14/13), parser (DFF include rule +
short-id fix), planner (`_TOOL_PRIMARY_ARG` entry), synthesizer (DFF model
+ field + prompt), `run_plan.py` (DFF display), `prompt_set_ar.txt` (DFF
prompt), `test_synthesizer.py` (3 DFF tests). Endpoints-reference quirk 8
updated (committed separately, docs-only).

DFF anchor: invoice **1002** (TransactionNumber 5) → TransactionDFF
`__FLEX_Context="DOO"` (no segment values). Verified end-to-end: 6/6 AR
prompts pass, "DOO" surfaces in the answer.

## Next activities (AR module, in order)

**11 AR prompts left.** AR-P3 is complete; next is AR-P4.

1. **AR-P4** — credit memos: list + total value (prompts 5, 14).
2. **AR-P5** — account children, all keyed by `AccountId`: activity/balance
   summary (6), account credit memos (7), account receipts (8), receipt
   applications (9), site-filtered receipts (13).
3. **AR-P6** — aggregates (op-registry, like PO's): exposure ranking (10),
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
- **A prompt in the set is not "passing" until it runs end-to-end.** The
  tax-lines prompt (prompt 3) used the short id 1002 and silently failed —
  the parser dropped the by_id filter for short ids, so it never fetched
  anything, but nothing flagged it until AR-P3 DFF ran the same id through
  the pipeline. Lesson: a short numeric id is still a valid
  CustomerTransactionId; run every prompt in the set end-to-end, don't
  assume a merged prompt works. The parser now handles short ids
  explicitly.

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
- AR invoice TransactionDFF: the two DFF children differ on this pod.
  `/receivablesInvoices/{id}/child/receivablesInvoiceDFF` returns
  `__FLEX_Context=null`;
  `/receivablesInvoices/{id}/child/receivablesInvoiceTransactionDFF` returns
  `__FLEX_Context="DOO"` on invoice 1002. The context is SET but has NO
  segment columns — the row is just `CustomerTrxId`, `__FLEX_Context`,
  `__FLEX_Context_DisplayValue` (null). Note the child echoes the parent id
  as `CustomerTrxId` (short spelling), not `CustomerTransactionId`.

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

For AR-P4 (credit memos, prompts 5 + 14) specifically: `receivablesCreditMemos`
is a top-level resource (not a child), so prompt 5 ("list recent credit
memos, top 5") is likely a rooted entity with its own fetcher — closer to
the AR-invoice by-id/list shape than to the DFF/tax-line child shape. It may
be a full new-entity phase (new entity-tool, entity-filter, and possibly the
five-place synthesizer change), unlike the two child phases just shipped.
Prompt 14 ("total value") may add an aggregate. Curl `receivablesCreditMemos`
first to confirm the endpoint shape and a demo anchor before wiring.
