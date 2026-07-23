# SPIRE — SESSION HANDOFF

Last updated: 2026-07-22, end of session.

## READ THIS FIRST — the status in this document is PARTLY UNVERIFIED

This session ended without running the full prompt set or the full test
suite. Some of what follows was observed directly; some is inferred from
file listings and a status summary produced elsewhere. **The two are
separated below and the distinction matters** — a previous version of this
handoff asserted "12 of 18 AR prompts done" and was wrong, because work
had happened outside the window that produced it.

**FIRST TASK for the next session is verification**, not building. Two
commands settle most of it:

```
python scripts/run_prompt_set.py --prompt-file scripts/prompt_set_ar.txt
python -m pytest -q
```

CAUTION on the first: `run_prompt_set.py` has previously reported prompts
as passing when they were being wrongly REFUSED ("38/38 ran cleanly" while
several were refusing). A clean summary is not proof. Check the answers.

---

## VERIFIED THIS SESSION (observed directly)

### AR prompts confirmed working end-to-end

Five ran clean — plan, fetch, synthesize, display:

- "Show me the account balance for customer ABC Application Software"
- "Show credit memos for ABC Application Software"
- "Show receipts for ABC Application Software" (10 receipts, all populated)
- "Show me AR invoices for customer ABC Corporation Americas"
- "List recent credit memos" (25 records)

### The parser runaway class appears CLOSED

All eleven documented bad prompts now parse correctly, `out=190–465`,
where they previously produced `out=7983/7984` with degenerate empty
Intents. This includes the four "PO 2144" prompts, "active US suppliers"
(both filters recovered), and the three AR interrogative forms.

**Four of these now pass END-TO-END** — the PO 2144 lines / schedules /
distributions / received prompts all synthesized successfully.

**The cause is not fully understood.** The change that fixed it altered
how `kg_entity_filter` rows are loaded and keyed, which changed the KG
menu, which changed the parser prompt (`in=` moved 7384 → 7415 → 8117
across the session). Whether that is the mechanism or a side effect is
NOT established. A fix that is not understood can regress silently.

### THREE PROMPTS ARE BROKEN — a regression, in the deterministic layer

These previously worked and now fail at plan time:

- "Which invoices were raised against PO 162034?" — `Invoice`/`purchase_order`
- "Show supplier EIP Inc and its contacts" — `Supplier`/`name_fragment`
- "Invoices for supplier 1252 over 100000" — `Invoice`/`supplier` + `invoice_amount`

Error: `Intent contains filter types not supported for entity 'Invoice':
['purchase_order']. Supported entity-level: [].`

**`Supported entity-level: []` is the tell** — the list is EMPTY, though
`kg_entity_filter` holds 25 rows including all of these.

**Root cause, diagnosed but NOT fixed: a half-applied change in the
planner's filter layer.** `_load_filter_defs()` returns a dict keyed by
the TUPLE `(filter_type, target_entity)` — confirmed live:

```
('by_id', None) -> entity_level customer_transaction_id
('supplier', None) -> entity_level supplier
('name_fragment', None) -> entity_level supplier_name_contains
```

But its consumers — `_entity_level_filter_types()`,
`_validate_intent_filters()`, `_pick_entity_filter()`,
`_build_entity_fetcher_args()` — iterate expecting `ftype, d` and so bind
`ftype` to the whole TUPLE. The resulting set contains tuples; validation
compares a plain string like `"supplier"` against it and never matches.

Note also every entity-level row shows `None` as its target, so the
per-entity keying may never have been fully wired into the KG rows.

**Two coherent directions, opposite to each other:**
1. Finish the revert — make `_load_filter_defs` key by `ftype` alone,
   matching its consumers. Loses per-entity `by_id` resolution
   (`po_header_id` vs `customer_transaction_id`), which is why the
   per-entity version was introduced.
2. Finish the per-entity design — update the consumers to unpack tuples,
   and populate `target_entity` on the entity-level KG rows.

Direction 2 preserves the capability; direction 1 is smaller. Decide
before touching it, and check `git log` for which version was committed.

### KG tripwire DRIFT — two tables

```
kg_entity_tool     10   expected  9   !! drift
kg_entity_filter   25   expected 23   !! drift
```

Rows were added without bumping the expected values in
`scripts/print_kg.py` and `tests/test_kg_metadata.py`. The other seven
tables read `ok`. Convention is to bump both files together whenever KG
row COUNTS change. `tests/test_kg_metadata.py` will be failing on this.

### Synthesizer arithmetic — STILL PRESENT (Issue 4)

Observed again this session: "Two receipts, totaling 16347.42 USD, are
currently unapplied" — a sum (1347.42 + 15000) the prompt explicitly
forbids. Three earlier instances are logged in the plan under Issue 4.
The instruction is present, unambiguous, and adjacent to the data, and is
ignored anyway. **Prompt-level prohibition has been shown insufficient.**
The structural fix is to compute in the TOOL and stamp the value onto
each row, exactly as AR-P4 does for `total_credit`.

### Display change on the receipts prompt

The account line now prints `receipts: 10` as a count rather than listing
each receipt. Earlier in the session it printed one line per receipt with
`StandardReceiptId` shown in full — deliberately, because the collection
mixes id widths and a short id beside a long one reads as a display bug.
Worth deciding which is wanted.

---

## NOT VERIFIED — treat as claims, confirm before relying on them

A status summary produced outside this window reports **17 of 18 AR
prompts merged**, with prompt 18 in progress and prompt 16 pending design.
File evidence is CONSISTENT with more work than this session saw:

- Tools present for prompts not built in this window:
  `account_receipt_applications.py` (9),
  `rank_customer_accounts_by_exposure.py` (10), `standard_receipts.py`
  (13), `aggregate_standard_receipts_by_method.py` (17)
- KG at **22 entities / 194 fields / 17 edges / 16 edge-tools / 97
  vocab** — well beyond the 20/169/16/15/93 recorded after prompt 8

So the claim is plausible. But NONE of prompts 9, 10, 13 or 17 was
observed running in this session. The tools existing is not the same as
the prompts working — prompt 8 had a complete tool, KG rows, planner
entries and passing unit tests while still returning an EMPTY receipts
array end-to-end.

**Unverified list, in the order worth checking:**
- Prompt 9 (receipt applications) — does it filter to `ApplicationStatus
  == 'Applied'`? Its newest rows are unapplied cash with a null
  transaction side, so a naive top-N shows rows whose entire point is
  missing.
- Prompt 13 (site-filtered receipts) — does it scope to the account?
  "Santa Clara" spans accounts 26360 AND 26370, and composite `q=`
  returns a SILENT ZERO on `/standardReceipts`.
- Prompt 10 (exposure ranking) and 17 (receipt-method distribution) —
  aggregates. Check the numbers are computed in the TOOL, not narrated by
  the model (see Issue 4).
- Prompt 18 (creation-to-update lag) — reported as needing a `lag_query`
  parameter added to the server wrapper.
- Prompt 16 (DSO / cash-collection) — reported as the only unbuilt one.
  Spans `/standardReceipts` + AR balance; the open design question is one
  aggregate tool vs two composed.

Also unverified: the full test suite. Last confirmed green at **435
passing** after prompt 8. The KG drift above means
`tests/test_kg_metadata.py` is failing now, so the true count differs.

---

## RECOMMENDED ORDER FOR THE NEXT SESSION

1. **`python -m pytest -q`** — establish the real baseline. Expect
   `test_kg_metadata.py` failures from the tripwire drift, and possibly
   `test_planner.py` failures from the filter-layer state.
2. **Run the AR prompt set end-to-end** and read the ANSWERS, not the
   summary line. This converts the unverified list above into fact.
3. **Fix the three broken PO/Supplier prompts** — decide direction 1 or 2
   on the filter layer first.
4. **Bump the two KG tripwires** to 10 and 25 in both `print_kg.py` and
   `test_kg_metadata.py`.
5. **Then** finish prompt 18 and design prompt 16.

Items 1–4 are cleanup of known breakage. Building on top of them without
fixing them is how the prompt-8 empty-array bug survived a full green
suite.

---

## OPEN ISSUES CARRIED FORWARD

- **Synthesizer arithmetic (Issue 4)** — structural fix needed; see above.
- **No degenerate-output detection.** Both LLM boundaries can return
  structurally valid but hollow results with nothing raising. A parse
  failure surfaces downstream as a planner error naming the WRONG problem;
  a synthesis failure surfaces as plausible prose with no rows. The plan
  carries a backlog item specifying a guard plus raw-output capture. The
  parser half may now be moot if the runaway is genuinely fixed, but the
  SYNTHESIZER half is not — prompt 8's empty array was a synthesizer
  failure and nothing detected it.
- **Payload entropy drives synthesizer output size**, not row count. 25
  varied receipt rows overran the budget; 25 near-identical ones did not.
  `get_account_receipts` caps at 10 for this reason.
- **The account-child receipt count (1,559) exceeds the top-level count
  filtered by account number (1,386).** Unexplained. Do not treat the two
  as interchangeable sources for a receipt total.
- **Prompt phrasing was load-bearing** for prompts 6, 7 and 8, and
  `prompt_set_ar.txt` records the failing forms above each. If the
  runaway is genuinely fixed those notes are now historical — but do not
  delete them until that is confirmed across the set.

---

# REFERENCE

## Project

Spire: an AI-native NL query system over Oracle Fusion procurement data.
Deterministic KG-driven pipeline (Design 3): **parse → plan → execute →
synthesize**. Tool selection is a KG lookup, not an LLM judgment. Not an
agent architecture.

Note on the architecture, given this session's findings: when the parser
produced a degenerate Intent, the planner REFUSED rather than guessing.
That is Design 3 working. The three broken prompts are a bug IN the
deterministic layer, not a failure of the idea — a lookup whose key shape
changed under its callers.

## Repo & environment

- Repo: `github.com/bhagavansprasad/spire`
- Working dir: `~/pocs/spire`, branch `master`
- Pod: `fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com`
- Creds: `personas.yaml` (gitignored) via `load_persona('default_dev')`

## Canonical docs (in `docs/`)

- `spire_expansion_plan.md` — master build plan; carries the backlog
  items and the numbered Issues list
- `spire_architecture.md` — current-state reference
- `spire_design_decisions.md` — frozen design records
- `spire_fusion_endpoints_reference.md` — pod quirks + curl reference,
  the authority on pod behavior
- `spire_pipeline_playbook.md` — how-to-add-a-prompt playbook

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
- TRAVERSED entity nesting under an existing root (prompts 7, 8) = four.
- EXTENDING an existing entity (AR-P3 tax lines) = schema + validator +
  prompt.
- A modifier on an existing traversal (top-5 limit) = parser + planner.
- Prompt 6 (balance_only) = two places.

The PLANNER also has per-entity/per-tool maps that are easy to miss:
`_OUTPUT_NAME_BY_ENTITY` (the bucket name) and **`_TOOL_PRIMARY_ARG`**
(the iterated arg). A missing `_TOOL_PRIMARY_ARG` entry is what broke
AR-P3. Both are covered by tests in `test_planner.py`.

## Hard-won lessons

- **Verify end-to-end at each stage.** A prompt is not "passing" until it
  runs from the set. Prompt 8 had a complete tool, KG rows, planner
  entries and a green unit suite while returning an EMPTY array.
- **Parse output alone is not a pass.** This session mistook eleven
  correct parses for eleven working prompts; three fail at plan time.
- **Check before doubting a status claim.** This session dismissed a
  status summary as inaccurate; the file listing proved it right. One
  `ls` would have settled it.
- **The executor unwraps a ToolResult to its `items` list and DISCARDS
  every other top-level key.** A scalar added alongside `items` never
  reaches the synthesizer — stamp it onto every row. This is also the
  template for the Issue 4 fix.
- **A rule keyed on the ABSENCE of an enumerated list breaks when the
  list grows.** Prompt 6's BALANCE-ONLY rule had to be widened twice.
- **Two module-level `def`s with the same name silently shadow.** Check
  `grep "^def test_" FILE | sort | uniq -d` after adding a batch.
- **An unexplained 500 is a projection suspect.** On `/standardReceipts` a
  `fields=` projection 500s even with valid names.
- **Retest before writing a pod finding into a doc.** Three 500s in a row
  led to "the endpoint is dead"; a fourth plain call returned 200.
- **COMMIT WITHIN THE BRANCH.** A file overwrite lost every uncommitted
  synthesizer change during prompt 7.
- **A general executor capability must be opt-in.** `_parent_stamp`
  ungated broke 4 existing tests.
- **A child endpoint often does not echo its parent id** — the join key
  is the URL path.

## Key conventions

- KG rebuilds from scratch: `python scripts/rebuild_kg.py`. Bump tripwires
  in `scripts/print_kg.py` AND `tests/test_kg_metadata.py` whenever KG row
  COUNTS change.
- One command at a time, verify each step. Output to `t.txt` (overwrite
  `>`, append `>>`).
- Ask permission before generating code or significant content.
- Offer numbered options in plain text with a recommendation and why.
- Git: one branch per logical change, PR-based, named files in `git add`
  (NEVER `-A`), heredoc commit messages. Multiple commits per branch.
  Docs-only changes may go straight to master.
- FILE DRIFT: always re-share the CURRENT version of a file before
  editing. Claude returns the COMPLETE updated file, never a patch.
- `spire_fusion_endpoints_reference.md` is the pod authority — update it
  after every new curl discovery.

## Pod quirks

- AR account children hang off
  `/receivablesCustomerAccountActivities/{AccountId}/child/...`; seven
  children: `creditMemos`, `standardReceipts`,
  `standardReceiptApplications`, `creditMemoApplications`,
  `transactionAdjustments`, `transactionPaymentSchedules`,
  `transactionsPaidByOtherCustomers`. NONE echo `AccountId`.
- **SIX distinct AR id spaces.** `CustomerTransactionId` (AR invoices +
  top-level credit memos) · `TransactionId` (payment schedules) ·
  `CreditMemoId` (account memos) · `StandardReceiptId` (receipts, MIXED
  WIDTH — small ints for backfilled rows, large for recent) ·
  `ApplicationId` (applications) · `ReferenceTransactionId` (small, the
  payment-schedule space). Each needs its own synthesizer id set.
- The account `creditMemos` child is NOT the top-level
  `receivablesCreditMemos`. Different id space, different projection.
- The account `standardReceipts` child is NOT the top-level
  `/standardReceipts`. The child has `ProcessStatus`; the top-level has
  `Status` plus customer and bank columns. Naming `ProcessStatus` against
  the top-level 500s it.
- `/standardReceipts` (top level): `q=` and `totalResults=true` work;
  `fields=` 500s even with valid names; NO default ordering; composite
  `q=` returns a SILENT ZERO.
- **The ABC-entity trap, with numbers:** "ABC Application Software"
  (26360, Santa Clara), "ABC Corporation Americas" (26370, Santa Clara),
  "ABC Corporation Worldwide" (25750, San Francisco). TWO SHARE A SITE.
  Resolve to an AccountNumber/AccountId before trusting a customer-scoped
  result.
- **`IsLatestApplication` does NOT mean what its name suggests** — "N" on
  the newest rows, "Y" on 2012 rows. Do not filter on it.
- AR tax lines: grandchild path with two ids; untaxed lines return
  `count:0`, not 404.
- AR invoice line rows do NOT expose `CustomerTransactionId`; it cannot
  be projected via `?fields=` (400s).
- AR invoice TransactionDFF echoes the parent as `CustomerTrxId`.
- Balance figures DRIFT (680,271.11 on 2026-07-19; 678,923.69 on
  2026-07-22) — never assert an exact value in a test.

## Files to share in a new window

Upfront:
- this handoff
- `docs/spire_expansion_plan.md`
- `docs/spire_fusion_endpoints_reference.md`

For the filter-layer fix specifically:
- `src/spire/planner/planner.py`
- `src/spire/nl_parser/vocabulary.py`
- `scripts/sql/kg_schema.sql` (the `kg_entity_filter` rows)
- `scripts/print_kg.py`, `tests/test_kg_metadata.py` (the tripwires)

Per-step, the ACTUAL current file when the step is reached (file drift):
`parser.py`, `draft.py`, `server.py`, `synthesizer.py`, `executor.py`,
`run_plan.py`, `test_synthesizer.py`, `test_planner.py`,
`test_nl_parser.py`, `test_executor.py`
