# SPIRE — SESSION HANDOFF

## THE NEXT SESSION IS AN INVESTIGATION, NOT A BUILD

Read this section first. Building has been deliberately PAUSED.

12 of 18 AR prompts are done and merged. Six remain. But two failures kept
recurring across AR-P5, and after prompt 8 the decision was to stop adding
prompts and find the root cause before writing more code. The concern that
prompted this was: *is the KG framework itself flawed?* The short answer
below is no — but the LLM boundaries around it are fragile, and the
failures are SILENT, which is worse than fragile.

### Is the KG design at fault? Evidence says NO.

Every failure observed sits OUTSIDE the KG-driven path:

- The parser runs away BEFORE the KG is consulted. It is an LLM producing
  a degenerate structured output; the KG is not in that code path.
- The synthesizer skipped a populated array. Downstream of the KG.
- The synthesizer does forbidden arithmetic. Downstream of the KG.

Meanwhile every KG lookup that ran, worked. Every plan the planner built
from KG rows was correct — right tool, right arg, right bucket, every
time, across 12 prompts. When the parser handed the planner a degenerate
Intent, the planner REFUSED rather than guessing ("No entity tool for
('CustomerAccount', 'none')"). That is the Design 3 premise holding:
tool selection is a deterministic lookup, so a bad Intent produces an
error, not a confidently wrong answer.

CAVEAT, stated honestly: this rests on the KG never having failed.
Absence of failure is evidence, not proof. If you want it tested rather
than argued, the observability work below is what makes that possible.

### What IS at fault: both LLM boundaries

Spire has exactly two places where an LLM produces structured output —
**parse** and **synthesize**. Both fail, and both fail the same way.

**Shared signature:** output tokens near the ceiling; early schema fields
populated correctly; later fields empty or missing; the result is
STRUCTURALLY VALID, so nothing raises.

### Evidence log — parser

- `LLM_MAX_OUTPUT_TOKENS = 8000` (`src/spire/config.py`, a plain constant,
  no env override). Failing parses report `out=7983` or `7984`.
- **It is NOT truncation.** Patched to 32000 at runtime → `out=31983` and
  the SAME empty Intent. The model never converges; the cap only bounds
  how long the failure takes. (This corrected a standing assumption in the
  plan.)
- **Deterministic.** Same prompt, same token count, to the token, on
  repeat runs.
- **Editing the parser prompt does NOT move it.** Prompt 6 absorbed FOUR
  separate rewrites — removing an "empty include" instruction, making a
  filter REQUIRED, deleting an aggregation carve-out, restoring it —
  with `out=7983` every single time, unchanged.
- **Rewording the QUESTION does, but unpredictably.** Prompt 6 needed 2
  phrasings; prompt 7 needed 5; prompt 8 worked on the 1st.
- **Weak pattern, UNCONFIRMED:** the working phrasings for prompts 7 and 8
  are both "Show X for [name]" with NO "customer" before the name. But
  prompt 6's working phrasing DOES contain "customer", so this is not a
  rule. Try it first when hunting; do not trust it.

### Evidence log — synthesizer (NEW, prompt 8)

This is the more interesting half, and it is newer than most of the plan's
existing notes.

- Prompt 8 fetched 25 receipts. The synthesizer returned
  `out=7985` and a response containing `"receipts": []` — an EMPTY array —
  while the prose summary correctly described all 25 ("There are 25
  receipts... Two are unapplied... The remaining 23 are applied").
- **The JSON was VALID and COMPLETE**, with `truncation_notes: []`. So
  unlike the parser case, nothing was cut off. The model read the data,
  described it accurately, and simply declined to populate the array.
- **The same 25-row fetch SUCCEEDED on a different account**, `out=3657`,
  all rows populated. The difference: that account's receipts were
  near-identical to one another (same date, same 15000.0 amount, same
  method). The failing account's were varied — different dates, amounts,
  methods, and a mix of Applied/Unapplied.
- **Conclusion: payload ENTROPY predicts this, not row count.** Both
  fetched 25 rows; one needed 3,657 output tokens and the other exceeded
  7,985.
- **Workaround applied:** `get_account_receipts` caps at 10, not 25. At 10
  the same account gives `out=1596` and every row present. This is a
  mitigation, NOT a fix — it just keeps a known-bad case under the
  ceiling.

### Evidence log — synthesizer arithmetic (Issue 4, now with new proof)

Prompts 7 and 8 both carry an EXPLICIT per-bucket instruction: "COPY every
amount exactly; do NOT total them, do NOT negate them, do NOT compute a
net." The model computed anyway, three observed times, each producing a
CORRECT number by a forbidden route:

- prompt 7: "amounts ranging from -156.6 to -495.9" (min/max scan)
- prompt 8: "Two receipts, totaling 16347.42 USD" (a sum: 1347.42 + 15000)
- prompt 8: "The remaining 23 receipts are applied" (25 − 2)

The numbers being right is the danger — nothing flags them, and the same
pattern on a messier set would be wrong with equal confidence. This is
evidence that prompt-level prohibition is insufficient: the instruction is
present, unambiguous, and adjacent to the data it governs.

NOTE THE PARALLEL: at both boundaries, editing the prompt text changed
nothing. That is the strongest hint that the fix is structural.

### THE REAL PRODUCTION RISK: silence

Both failures return structurally valid results.

- A degenerate parse returns a valid `ParseResult`. It surfaces downstream
  as a planner error naming the WRONG problem — "No entity tool for..."
  reads as a missing KG row, not a failed parse. And a runaway that
  happens to produce a ROUTABLE Intent would answer confidently from a
  wrong parse with no error anywhere.
- An empty `receipts` array returns a valid response with plausible prose.
  The demo shows a correct-sounding summary and no rows.

Neither is detected. Nothing logs, warns, or raises.

### Why the investigation has been blind so far

Roughly fifteen probe runs across one session produced ONLY token counts.
The 32,000 generated tokens from the cap experiment were never seen.
`with_structured_output` buffers, so a 30s+ generation prints nothing
until it completes. There is no raw-output capture anywhere.

Every diagnosis attempted from that position was wrong — four consecutive
wrong root causes on the parser, two on the synthesizer. This is not a
reasoning problem; there is genuinely nothing to reason FROM.

### PROPOSED SEQUENCE (do these in order)

**1. Degenerate-parse / degenerate-synthesis guard.** After each LLM call,
flag when output tokens are within ~95% of the cap, and/or
`finish_reason != 'stop'`, and/or a structurally-suspicious result (a
`target_entity` with no filters where the prompt named a customer; an
empty child array when the executor bucket was non-empty). Raise a typed
error rather than returning the result. Converts a silent wrong answer
into an honest failure. Small, mechanical, highest value.

**2. Raw-output capture.** When the guard fires, write the raw model
response to the existing trace file (`traces/*.jsonl` — note the trace
ALREADY records `synthesis_completed` with the full parsed response, which
is how the empty-array finding was confirmed; what is missing is the raw
pre-parse text and the parser-side equivalent). ONE captured runaway would
likely explain more than every A/B test run so far.

**DO 1 AND 2 BEFORE ATTEMPTING A ROOT-CAUSE FIX.** Without (2) there is
nothing to root-cause from — that is the lesson of the session.

**3. Then root-cause**, with evidence.

**4. Structural fix for the arithmetic (Issue 4)** — compute totals in the
TOOL and stamp them onto the rows, exactly as AR-P4 does for
`total_credit`, rather than asking the model not to compute. Alternatively
validate numeric claims in the summary against fetched values.

**5. Optional, worth knowing:** nobody has systematically tested phrasing
variants. Prompt 7 had 4 failing forms out of 5 tried. The documented list
of ~11 bad prompts is what has been STUMBLED UPON, not a survey. Testing
3–4 phrasings per prompt across the suite would size the problem.

### Files that matter for the investigation

- `src/spire/config.py` — `LLM_MAX_OUTPUT_TOKENS = 8000`, `build_llm()`
- `src/spire/nl_parser/parser.py` — the parse call
- `src/spire/synthesizer/synthesizer.py` — the synthesize call
- `scripts/inspect_trace.py` — existing trace reader
- `traces/*.jsonl` — what IS captured today
- `docs/spire_expansion_plan.md` — "Parser runaway defence" and "Parser
  observability" backlog items; Issues 1 and 4

---

# BUILD STATE (reference — paused, not abandoned)

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

- `spire_expansion_plan.md` — master build plan (current through AR-P5
  prompt 8)
- `spire_architecture.md` — current-state reference
- `spire_design_decisions.md` — frozen design records
- `spire_fusion_endpoints_reference.md` — pod quirks + curl reference (the
  authority on pod behavior; carries the full AR-P5 curl discovery)
- `spire_pipeline_playbook.md` — how-to-add-a-prompt playbook

## Current state

PO module complete. AR module: **12 of 18 AR prompts done**.

Merged (AR): AR-P2a (prompts 11, 12, 2) · AR-P2b (15) · AR-P2c (1,
`open_only`) · top-5 limit (`invoice_limit`) · AR-P3 tax lines (3) ·
AR-P3 DFF (4) · AR-P4 credit memos (5, 14) · **AR-P5 prompt 6** (account
balance, `balance_only`) · **AR-P5 prompt 7** (`AccountCreditMemo`) ·
**AR-P5 prompt 8** (`AccountReceipt`).

KG now: **20 entities, 169 fields, 16 edges, 15 edge-tools**, 21 filters,
8 entity-tools, 93 vocab, 3 patterns. Full suite: **435 passing**.

## What remains (6 prompts)

**AR-P5 — 2 left.** Curl discovery for BOTH is DONE; go straight to the
tool.

- **Prompt 9 — receipt applications.** Child
  `standardReceiptApplications`, 15,636 rows on the anchor (the largest).
  PRE-JOINED: carries the receipt side (`StandardReceiptId`,
  `ReceiptNumber`, `ReceiptMethod`) AND the transaction side
  (`ReferenceTransactionId`, `ReferenceTransactionNumber`,
  `ReferenceTransactionStatus`) on ONE row — no second fetch needed. PK
  `ApplicationId`, a sixth id space. `ReferenceTransactionId` is a SMALL
  int (the `transactionPaymentSchedules` space), NOT
  `/receivablesInvoices`' `CustomerTransactionId`.
  **TRAP: the newest rows are unapplied cash, not applications** —
  `ApplicationStatus: "Unapplied"` with ALL THREE `ReferenceTransaction*`
  fields null. A naive recent-N slice returns rows whose entire
  transaction side is empty. Needs client-side
  `ApplicationStatus == 'Applied'` filtering — the first AR-P5 prompt that
  does, so follow `customer_transactions.py`'s over-fetch pattern, not
  prompts 7/8's simple shape. **`IsLatestApplication` does NOT mean what
  its name suggests** — "N" on the newest rows, "Y" on 2012 rows. Do not
  filter on it.
- **Prompt 13 — site-filtered receipts.** Uses the TOP-LEVEL
  `/standardReceipts`, not the child. `q=CustomerSite='Santa Clara'` IS
  queryable (1,735 rows) but the site SPANS ACCOUNTS (26360 AND 26370), so
  site alone is not customer-scoped. **Composite `q=` returns a SILENT
  ZERO** (HTTP 200, `totalResults: 0`) although each clause alone returns
  thousands. Design: `q=CustomerAccountNumber=<n>` server-side, then match
  `CustomerSite` client-side, handling nulls. **`fields=` is UNUSABLE on
  `/standardReceipts`** — it 500s even when every named field is valid.

**AR-P6 — 4 left, all aggregates.** Exposure ranking (10), DSO /
cash-collection (16), receipt-method distribution (17), creation-to-update
lag (18). These need an op-registry like PO's — a separate path that
bypasses the KG entirely, using the `aggregate` block on the Intent. NONE
of the AR-P5 patterns transfer. Flagged: prompt 16 spans two endpoints
(`/standardReceipts` + AR balance) — decide one aggregate tool vs two
composed.

## AR-P5 discovery results (DONE — do not re-curl)

Anchor: `AccountId=300000047368512` = ABC Application Software,
AccountNumber 26360. Balance figures DRIFT (680,271.11 on 2026-07-19;
678,923.69 on 2026-07-22) — never assert an exact value.

Per-account child row counts: `creditMemos` 280, `standardReceipts` 1,559,
`standardReceiptApplications` 15,636. All need `orderBy` + a hard `limit`.
Every one is fetched by `AccountId` in the URL PATH and **none echoes
`AccountId` in the row body**.

OPEN QUESTION: the account-child receipt count (1,559) EXCEEDS the
top-level count filtered by account number (1,386). Unexplained. Do not
treat the two as interchangeable sources for a receipt total.

## Build sequence (per prompt)

curl discovery → standalone tool, pod-proven in isolation → KG rows
(rebuild from scratch) → planner → parser → server wrapper → synthesizer →
run_plan.py display → tripwire bump → tests → verify end-to-end →
branch / PR / merge.

The synthesizer's five places (miss one and it errors):
1. registry (`SYNTHESIS_SCHEMAS`)
2. `_SYSTEM_PROMPT_BY_ENTITY`
3. id-harvest (`_collect_valid_ids`)
4. validator function
5. validator dispatch dict

NOT every phase is five places. **Reason from the actual shape.**
- NEW ROOTED entity (AR-P4 CreditMemo) = all five.
- TRAVERSED entity nesting under an existing root (prompts 7, 8) = four;
  registry and dispatch already cover the response type.
- EXTENDING an existing entity (AR-P3 tax lines) = schema + validator +
  prompt.
- A modifier on an existing traversal (top-5 limit) = parser + planner.
- Prompt 6 = two places.

The PLANNER also has per-entity/per-tool maps that are easy to miss:
`_OUTPUT_NAME_BY_ENTITY` (the bucket name) and **`_TOOL_PRIMARY_ARG`**
(the iterated arg). A missing `_TOOL_PRIMARY_ARG` entry is what broke
AR-P3; check both when adding an edge tool. Both are now covered by tests
in `test_planner.py`.

## Hard-won lessons

- **Verify end-to-end at each stage.** AR-P3 had THREE design corrections
  that only surfaced by running the full pipeline.
- **A general executor capability must be opt-in.** The `_parent_stamp`
  ungated broke 4 existing tests.
- **A child endpoint often does not echo its parent id.** Confirmed for AR
  invoice lines AND all three AR-P5 account children.
- **A prompt is not "passing" until it runs end-to-end from the set.**
- **The executor unwraps a ToolResult to its `items` list and DISCARDS
  every other top-level key.** A scalar the wrapper adds alongside `items`
  (AR-P4's `total_credit`) never reaches the synthesizer — stamp it onto
  every row instead. This is also the template for the Issue 4 fix.
- **A supported operation can be swallowed by the aggregation-refusal
  path.** Carve it out where the refusal instinct lives, not only where
  the feature is defined.
- **A rule keyed on the ABSENCE of an enumerated list breaks when the list
  grows.** Prompt 6's BALANCE-ONLY synthesizer rule keyed on "no
  `customertransaction` bucket"; prompt 7 added a second child and prompt
  8 a third, and it had to be widened BOTH times. It now requires no child
  bucket at all.
- **Two module-level `def`s with the same name silently shadow.** A new
  `test_validate_catches_hallucinated_credit_memo_id` displaced AR-P4's
  identically-named test — it simply stopped running, and only a
  suspicious test COUNT caught it. Check
  `grep "^def test_" FILE | sort | uniq -d` after adding a batch.
- **An unexplained 500 is a projection suspect.** On `/standardReceipts` a
  `fields=` projection 500s even with valid names. Twice misdiagnosed as a
  dead endpoint, costing six calls. Drop `fields=` first when diagnosing.
- **Retest before writing a pod finding into the doc.** Three 500s in a
  row led to "the endpoint is dead"; a fourth plain call returned 200.
- **COMMIT WITHIN THE BRANCH.** A local file overwrite during prompt 7
  lost every uncommitted synthesizer change; prompt 6 was safe because it
  was committed. Multiple commits per branch is fine — one PR at the end.
- **Payload entropy, not row count, drives synthesizer output size.** See
  the prompt 8 evidence above.

## Key conventions

- KG rebuilds from scratch: `python scripts/rebuild_kg.py`. Bump tripwires
  in `scripts/print_kg.py` AND `tests/test_kg_metadata.py` ONLY when KG
  rows change.
- One command at a time, verify each step. Output to `t.txt` (overwrite
  `>`, append `>>`). Heredoc for throwaway scripts.
- Ask permission before generating code or significant content.
- Offer numbered options in plain text with a recommendation and why.
- Git: one branch per logical change (`ar-phase-N-description`), PR-based,
  named files in `git add` (NEVER `-A`), heredoc commit messages. Multiple
  commits per branch. Docs-only changes may go straight to master.
- FILE DRIFT: always re-share the CURRENT version of a file before
  editing. Claude returns the COMPLETE updated file, never a patch.
- `spire_fusion_endpoints_reference.md` is the pod authority — update it
  after every new curl discovery.

## Pod quirks

- AR account children hang off
  `/receivablesCustomerAccountActivities/{AccountId}/child/...`; the seven
  children are `creditMemos`, `standardReceipts`,
  `standardReceiptApplications`, `creditMemoApplications`,
  `transactionAdjustments`, `transactionPaymentSchedules`,
  `transactionsPaidByOtherCustomers`.
- **SIX distinct AR id spaces now.** `CustomerTransactionId` (AR invoices
  + top-level credit memos) · `TransactionId` (payment schedules) ·
  `CreditMemoId` (account memos) · `StandardReceiptId` (receipts, MIXED
  WIDTH — small ints for backfilled rows, large for recent) ·
  `ApplicationId` (applications, prompt 9) · `ReferenceTransactionId`
  (small, the payment-schedule space). Each gets its own fully-qualified
  synthesizer id set; a test pins that one cannot validate against
  another.
- The account `creditMemos` child is NOT the top-level
  `receivablesCreditMemos`. Different id space, different projection.
- The account `standardReceipts` child is NOT the top-level
  `/standardReceipts`. The child has `ProcessStatus`; the top-level has
  `Status` plus customer and bank columns. Field names do NOT carry
  across — naming `ProcessStatus` against the top-level 500s it.
- `/standardReceipts` (top level): `q=` and `totalResults=true` work;
  `fields=` 500s even with valid names; NO default ordering (two identical
  unordered calls returned different first rows); composite `q=` returns a
  silent zero.
- The ABC-entity trap, with numbers: "ABC Application Software" (26360,
  Santa Clara), "ABC Corporation Americas" (26370, Santa Clara), "ABC
  Corporation Worldwide" (25750, San Francisco). TWO SHARE A SITE.
  Resolve to an AccountNumber/AccountId before trusting a customer-scoped
  result.
- AR tax lines: grandchild path with two ids; untaxed lines return
  `count:0`, not 404. The tax-line row's own `CustomerTransactionLineId`
  is the TAX-line PK, distinct from the parent line id.
- AR invoice line rows do NOT expose `CustomerTransactionId`; it cannot be
  projected via `?fields=` (400s).
- AR invoice TransactionDFF echoes the parent as `CustomerTrxId` (short
  spelling).
- `receivablesCreditMemos` (top level) shares the `CustomerTransactionId`
  space with AR invoices. `EnteredAmount` normally negative but NOT
  guaranteed (positive Incomplete memo 1001, +10000).

## Files to share in the new window

For the INVESTIGATION, share upfront:
- this handoff
- `docs/spire_expansion_plan.md` (the two backlog items + Issues 1 and 4)
- `src/spire/config.py`
- `src/spire/nl_parser/parser.py`
- `src/spire/synthesizer/synthesizer.py`
- `scripts/inspect_trace.py`
- a recent `traces/*.jsonl` from a FAILING run if one can be reproduced

For BUILD work (when it resumes):
- `docs/spire_fusion_endpoints_reference.md`
- context bundles: `context_parser_planner.md`,
  `context_mcp_server_tools.md`, `context_graph_kg.md`
- per-step, the ACTUAL current file when the step is reached (file drift):
  `scripts/sql/kg_schema.sql`, `planner.py`, `parser.py`, `draft.py`,
  `server.py`, `synthesizer.py`, `executor.py`, `run_plan.py`,
  `print_kg.py`, `test_kg_metadata.py`, `test_synthesizer.py`,
  `test_planner.py`, `test_nl_parser.py`, `test_executor.py`

Closest precedents for the remaining AR-P5 prompts:
- `src/spire/mcp_server/tools/account_receipts.py` — prompt 8's tool; the
  simple account-child shape, and the 10-row limit with its reasoning.
- `src/spire/mcp_server/tools/customer_transactions.py` — the
  over-fetch-and-filter-client-side pattern, which prompt 9 needs.
