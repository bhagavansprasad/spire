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
  through AR-P4 credit memos — AR-P4 complete)
- `spire_architecture.md` — current-state reference
- `spire_design_decisions.md` — frozen design records
- `spire_fusion_endpoints_reference.md` — pod quirks + curl reference (the
  authority on pod behavior)
- `spire_pipeline_playbook.md` — how-to-add-a-prompt playbook

## Current state

PO module complete. AR module in progress: **9 of 18 AR prompts done**.

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
  AR-P3.
- **AR-P4 credit memos** (`ar-p4-credit-memos`, merged 2026-07-21) —
  prompts 5, 14. See below.

KG now: **18 entities, 148 fields, 14 edges, 13 edge-tools**, 21 filters,
8 entity-tools, 87 vocab, 3 patterns. Full suite: **406 passing**.

## AR-P4 credit memos — what shipped this session (the important detail)

"List recent credit memos" (prompt 5) and "total value of credit memos"
(prompt 14) both route to ONE fetcher over the top-level
`receivablesCreditMemos` resource: the newest memos
(orderBy=TransactionDate:desc, server-side) with a total credit value.

**Shape: a rooted, list-only entity.** No by-id, no edge, no filter — the
simplest fetch shape. `find_entity_tool('CreditMemo','none')` in Block 1
handles it; the fetcher orders and limits server-side. First NEW rooted AR
entity since AR-P2, so the synthesizer WAS a five-place change (schema,
registry, prompt, validator, dispatch). BUT id-harvest needed NO change:
credit memos share the `CustomerTransactionId` id space with AR invoices,
so their ids land in the existing `customer_transaction_ids` set and the
validator reuses it. Planner was ONE line (`_OUTPUT_NAME_BY_ENTITY`).

**total_credit = raw sum of EnteredAmount.** A ledger net figure: the demo
pod has a POSITIVE, Incomplete memo (TransactionNumber 1001, +10000) that
offsets the negatives, so the total for the recent-25 set is -17232.52.
Sign is NOT guaranteed — never assume EnteredAmount < 0. Caveat: the sum
mixes currencies (USD/CAD/GBP/EUR) into one number; acceptable for the demo
but not a real multi-currency total.

**The bug that a failing test caught (the important lesson).** The wrapper
first put `total_credit` as a TOP-LEVEL key on the tool payload. But the
executor unwraps a ToolResult to its `items` list and DISCARDS every other
top-level key (`_parse_tool_result` → `return payload["items"]`), so
top-level total_credit NEVER reached the synthesizer — the LLM was silently
summing the amounts itself (it got the right number, but by forbidden
arithmetic, not the computed value). Fix: the wrapper STAMPS total_credit
onto EACH memo row so it survives the unwrap; the prompt reads it off any
row and copies it exactly. This surfaced only because a synthesizer test
fixture put total_credit top-level and `_collect_valid_ids` crashed
iterating the int — inspection had missed it.

Files touched (all merged): new tool `receivables_credit_memos.py`, server
wrapper (stamps total onto each item), `kg_schema.sql` (entity + 8 fields +
entity-tool + 2 vocab), `print_kg.py` + `test_kg_metadata.py` tripwires
(18/148/8, vocab 87), parser (credit-memo rule + an explicit "total is NOT
an unsupported aggregation, do not refuse" carve-out in TWO places),
planner (`_OUTPUT_NAME_BY_ENTITY` entry), synthesizer (five places:
`CreditMemoRecord`/`CreditMemoListResponse` + registry + prompt + validator
+ dispatch), `run_plan.py` (credit-memo display), `prompt_set_ar.txt` (both
prompts + anchor note), `test_synthesizer.py` (4 credit-memo tests).

Credit-memo anchors: ~25 recent memos, newest first (top:
TransactionNumber 11001, DMART, -150, 2026-07-09). Positive outlier: 1001,
+10000, Incomplete. Verified end-to-end: both prompts pass; total -17232.52
sourced from the stamped value, not LLM math.

## Next activities (AR module, in order)

**9 AR prompts left.** AR-P4 is complete; next is AR-P5.

1. **AR-P5** — account children, all keyed by `AccountId`: activity/balance
   summary (6), account credit memos (7), account receipts (8), receipt
   applications (9), site-filtered receipts (13).
2. **AR-P6** — aggregates (op-registry, like PO's): exposure ranking (10),
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
- **The executor unwraps a ToolResult to its `items` list and DISCARDS
  every other top-level key.** (`_parse_tool_result` → `return
  payload["items"]`.) So a scalar the wrapper adds alongside `items` (e.g.
  AR-P4's `total_credit`) never reaches the synthesizer — put it INSIDE
  each item instead (stamp it onto every row). AR-P4 first placed the total
  top-level; the LLM silently summed the amounts itself (right number,
  forbidden arithmetic) and the miss only surfaced because a test fixture
  crashed `_collect_valid_ids` iterating the int. Any future
  per-fetch scalar (a total, a computed flag) must ride on the items, not
  beside them.
- **A supported operation can be swallowed by the aggregation-refusal
  path.** "Total value of credit memos" LOOKS like an aggregation the
  parser refuses (totals/rankings it can't compute), so the LLM refused it
  even though the fetcher returns the total. Fix was an explicit carve-out
  in the parser rule AND at the aggregation block ("this is NOT an
  unsupported aggregation, route to CreditMemo, do not refuse"). When a new
  supported feature overlaps a refusal category, carve it out where the
  refusal instinct lives, not only where the feature is defined.

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
- AR credit memos: `receivablesCreditMemos` is a TOP-LEVEL resource (no
  parent id), accepts `orderBy=TransactionDate:desc` and `limit`
  server-side, and the id field is `CustomerTransactionId` (same as AR
  invoices — shared id space). EnteredAmount is normally negative but NOT
  guaranteed: the demo has a positive Incomplete memo (1001, +10000).

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

For AR-P5 (account children, prompts 6-9, 13) specifically: all five are
keyed by `AccountId` and hang off the customer account (resolved by
CustomerName, as in AR-P2b). Likely a family of per-account child
traversals (edges off CustomerAccount), similar in shape to AR-P2b's
HAS_CUSTOMER_TRANSACTION but to different children (activity/balance,
account credit memos, receipts, receipt applications). Prompt 13
(site-filtered receipts) has a flagged trap: confirm a Santa Clara receipt
anchor exists first, and beware the ABC-entity family (ABC Corporation
Americas / Worldwide / ABC Application Software are DIFFERENT customers).
Curl each child endpoint first to confirm shape, the AccountId join, and a
demo anchor before wiring. Note the credit-memo endpoint already exists
(AR-P4) — prompt 7 "account credit memos" may reuse it filtered by account,
or be a distinct account-child endpoint; curl to decide.
