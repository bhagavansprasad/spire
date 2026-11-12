# Phase 3 — Sample-and-disclose: CreditMemo

**Branch:** `Phase3-CreditMemo-Sample`
**PR:** pending
**State:** draft
**Finding:** MEETING_2026-11-10 §6 row 5 — the fifth entity in the
seven-PR sample-and-disclose sequence. CreditMemo already samples on
`master`: the `list_receivables_credit_memos` tool returns the newest N
memos with `total_available` from `totalResults`, and the synthesizer's
plain-credit-memo branch builds a local `CreditMemoListResponse` from
those rows. PR #5 is therefore a coverage + one-new-shape PR (the
`narrowing_tip` field), not a wiring change on the CreditMemo path — and
with one structural caveat, recorded in §V0-history and §Deviations: the
CreditMemo entity-level filter set on this pod is `[]`, so the tip ships
empty on every CreditMemo response.

## V0 — Fix statement

CreditMemo sample-and-disclose is **already implemented on `master` at
`7e786c7`** for the plain single-bucket case. The synthesizer branch

    memo_bucket = (
        plain_credit_memo_bucket(outputs)
        if target_entity == "CreditMemo" else None
    )
    if memo_bucket is not None:
        rows = outputs[memo_bucket]
        total_available, notes = _local_truncation(
            memo_bucket, rows, truncation_by_step, metadata_by_step
        )
        first = rows[0] if rows else {}
        total_credit = first.get("total_credit")
        total_note = first.get("total_credit_note")
        return CreditMemoListResponse(
            summary="\n".join(local_list_summary(rows, ...)),
            credit_memos=build_credit_memo_records(rows),
            total_credit=total_credit,
            total_credit_note=total_note,
            truncation_notes=notes,
        )

returns a local, no-LLM `CreditMemoListResponse` with a bounded sample,
a local summary, a truncation disclosure, and the `total_credit` /
`total_credit_note` pair read verbatim off the tool's stamped rows. **PR
#5 does not introduce the CreditMemo plain-list path.**

What PR #5 contributes:

  (a) **The narrowing tip field.** `CreditMemoListResponse` (`ar.py`)
      carries `summary`, `credit_memos`, `total_credit`,
      `total_credit_note`, `truncation_notes` only — no `narrowing_tip`
      field. `PurchaseOrderResponse`, `SupplierResponse`,
      `InvoiceResponse` and `StandardReceiptResponse` all carry it. PR
      #5 adds the field to `CreditMemoListResponse` and a
      `narrowing_tip=` kwarg at the CreditMemo return, mirroring the
      Invoice call site (post `d7d78c5`) and the StandardReceipt call
      site (post `3d7f4b6`).

      **No `_CREDIT_MEMO_FILTER_LABELS` dict is added to `p2p.py`.**
      The CreditMemo entity-level filter set on this pod, read at
      `7e786c7` via `_entity_level_filter_types().get("CreditMemo",
      set())`, is **`[]`** — the empty set. `build_narrowing_tip` with
      an empty filter set returns `""` by its own `if not labels:
      return ""` guard, before it ever inspects `total`. An empty label
      map beside the three populated ones would be dead code; the
      correct call is `build_narrowing_tip(set(), ...)`, which is
      honest about the KG's state.

  (b) **The sample-only guard.** The `narrowing_tip` kwarg is guarded
      on `len(rows) < total_available`, the same sample-only guard PR
      #3 landed at `d7d78c5` and PR #4 landed at `3d7f4b6`. On
      CreditMemo today the guard's positive branch is unreachable — the
      tip returns `""` on both branches — but the guard is correct and
      is what a future KG change would wire into cleanly.

  (c) **Coverage.** Tests that lock the plain-list CreditMemo path
      (already green on master), lock that the `narrowing_tip` field
      exists and is `""` on both a sampled fetch (25 of N with
      `total_available > 25`) and a complete fetch (`total_available
      == len(rows)`), and lock that `total_credit` is populated only
      when `compute_total_credit` returns it (not on multi-currency and
      not on truncation).

  (d) **Evidence.** The V-walk below.

**What PR #5 does NOT do, and why.** The meeting §6 row-5 prescription
("Extend extractor; `narrowing_tip` field on `CreditMemoListResponse`;
tip block") describes a change master's CreditMemo path mostly does not
need:

- `list_receivables_credit_memos`
  (`src/spire/mcp_server/tools/receivables_credit_memos.py`) has no
  scope check — it accepts a filter-less fetch and returns newest-first
  via server-side `orderBy=TransactionDate:desc`. There is nothing to
  "extend" on the tool.
- The parser already routes filter-less CreditMemo requests to
  `target_entity='CreditMemo'` with no filters, via the sysprompt
  block at
  `src/spire/nl_parser/context/receivables/b_credit_memos.sysprompt`.
  There is nothing to "extend" on the parser.
- The planner has no CreditMemo guard (unlike Invoice, Address,
  PurchaseOrder, ReceivablesInvoice, StandardReceipt); a filter-less
  CreditMemo intent falls straight through to Block 1's entity fetch.
  There is nothing to "extend" on the planner.
- The tip block exists as a mechanism (`build_narrowing_tip` in
  `p2p.py`), but has no filter types to name on CreditMemo, so the tip
  is empty by construction. The field is added for contract
  uniformity — five of the eight `SYNTHESIS_SCHEMAS` entries carry it
  today, six after PR #5 — and to seed the future KG-filter-set PR
  that would make it fire.

**The CreditMemo special case: `total_credit` is `None` for two
reasons, not one, and neither blocks the tip.** `compute_total_credit`
returns `(None, note)` in two situations:

  (i) The returned memos span more than one currency
      (`len(currencies) > 1`): "Not totalled: these memos span N
      currencies (...)."
  (ii) The fetch is truncated (`total_available > len(items)`):
      "Not totalled: these are the N most recent of M credit memos."

Neither is a defect; both are withheld totals where a number would be a
figure in no currency or over a partial set. **The tip's guard is on
`total_available`, not on `total_credit`.** Case (i) is a genuine sample
of multi-currency memos; case (ii) is precisely a sample. If CreditMemo
had filter types to name, the tip would fire on both — the tip's
question ("is this a sample?") and `total_credit`'s question ("is there
one currency and a complete set?") are independent. On this pod the tip
cannot fire at all, because the KG gives it nothing to name; but the
field's guard must not be written as if `total_credit is not None` were
the tip's precondition.

## V0 — history

The original V0 would have been the meeting §6 row-5 prescription
above, corrected on reading `master` at `7e786c7`. Preserved here per
the `supplier.md` §V0-history precedent so the branch's own record of
what it first claimed is not lost:

> The parser will set `intent.list_all=True` for a CreditMemo intent
> that names no narrowing filter, via a sibling extractor beside
> `_is_explicit_po_list` and `_is_sampleable_po_request`; the planner's
> existing CreditMemo path will then permit a bounded 25-row sample;
> `CreditMemoListResponse` will gain a `narrowing_tip` field so the
> sample discloses itself and tells the user how to narrow.

**Why it was wrong.** Read from `master` at `7e786c7`:

- The parser already produces a filter-less CreditMemo intent for the
  five taught phrasings in `b_credit_memos.sysprompt`. No sibling
  extractor is needed; the sysprompt rule already fires.
- The planner has no CreditMemo guard; `intent.list_all` has no
  CreditMemo reader and setting it would fire and land nowhere — the
  `f36b11c` defect `supplier.md` §V0-history records for Supplier, two
  entities over.
- The tool has no scope check and no filter args to wire a
  `by_customer_name` filter into; extending the tool is a separate PR.
- The tip, once added, is empty by construction because the KG's
  CreditMemo entity-level filter set is `[]`.

**The correction is the finding.** CreditMemo's plain-list path is
already in place; PR #5 is a field, a guard, and tests that exercise
both — a contract-uniformity contribution today, not a live user-facing
tip.

This is the **fifth** such correction in five PRs. The pattern is now
fully established: the meeting's row describes a wiring change, and
master's code is nearly always "already samples locally, add one small
shape, and one structural caveat per PR."

## Deviations

### The tip is empty by construction on this pod

`build_narrowing_tip` returns `""` when its `filter_types` argument
produces no labels — before it inspects `total`. The CreditMemo
entity-level filter set on this pod is `[]`, so every CreditMemo
response PR #5 produces carries `narrowing_tip=""`. The field is
correct; its positive branch is unreachable today. Wiring it to a
non-empty set requires a KG `kg_entity_filter` insert plus a
`list_receivables_credit_memos` signature extension that takes the new
filter — a separate PR with its own V0 and its own V-walk, not PR #5's
scope. Deferred to that branch.

### `capability.py` `_FILTER_GUIDANCE["CreditMemo"]` is a live but narrow finding

`_FILTER_GUIDANCE["CreditMemo"]` (`("Narrow by customer name instead.",
"credit memos for ABC Application Software")`) advises narrowing by a
customer-name filter that **does not exist on the CreditMemo entity**.
The parser teaches "credit memos for customer [name]" to route to
`CustomerAccount` with `by_customer_name`, not to a filtered CreditMemo.
The advice is reachable only through fallback — a model that misfires
onto `CreditMemo` with an unsupported filter — but when reached, it is
self-contradicting: the Solution line names a filter the Reason line
just refused. Same class `capability.py`'s own `UNSUPPORTED_FIELD`
docstring calls out (a menu with no right option produces a wrong
available choice). Separate `capability.py` branch; recorded here as a
pointer, not fixed in PR #5.

### Out of scope — the `total_credit` multi-currency rule

`compute_total_credit` withholds `total_credit` across currencies **and**
on a truncated fetch. PR #5 reads both from the tool verbatim and does
not recompute either. Any change to the withholding rule belongs with
the tool, not the synthesizer.

### Out of scope — `SQL_EMITTER_MULTIFIELD_ITERATION.md` and `MCP_DEPENDENCY_CONFLICT.md`

Same as PRs #1–#4. Future windows.

### `personas.yaml` in the working tree

Local credential edit, never staged, not part of any PR.

### Design decision: sysprompt stays untouched on this PR

Same as PR #1–#4: pure-Python fix, no `.sysprompt` change, so no V9
sweep required. The parser rule in `b_credit_memos.sysprompt` is
already correct.

## V1 — Reproducer (live)

Prompt: `list credit memos` against `fa-esll-saasfademo1`, run after
the MCP server was restarted to pick up the CreditMemo fix at
`35a0095` (WORKING_STYLE §22.1). Saved transcript at
`/tmp/v1_credit_memo_positive.txt` (89 lines, `exit=0`).

Result (green):

- Intent: `target_entity: CreditMemo`, no filters, no include.
- Plan: one step, `list_receivables_credit_memos`, `tool_args: {}`
  (the tool's default limit of 25 applies).
- Answer: `Showing 25 of 2,261 credit memos.` — 25 rows, newest first
  (server-side `orderBy=TransactionDate:desc`).
- Currency split: `23 USD, 2 INR`. Status split: `23 Complete, 2
  Incomplete`. Both are the local summary's uniformity-then-split rule
  on the corresponding columns.
- Total-credit note (line 76): `Not totalled: these memos span 2
  currencies (INR, USD). A single sum across them would be a figure in
  no currency at all.` The multi-currency case exercised
  `compute_total_credit`'s `(None, note)` return; the note is
  `server.py`'s wrapped output, stamped onto every row, read verbatim
  by the synthesizer, rendered by `formatters.py`'s
  `CreditMemoListResponse` branch.
- Truncation: `credit_memos: 2261 total in source; 25 returned.`
  Matches the summary's `2,261`.
- **No `─── Tip ───` block.** `grep -cE 'Tip' /tmp/v1_credit_memo_positive.txt`
  → `0`. `grep -c 'narrowing_tip' ...` → `0`. The field is on the
  response and empty by construction; the renderer's `if tip:` gate
  suppressed the block. This is the intended Shape A positive case.

**The V1 assertion is the absence of a Tip block.** PR #5 adds the
field and the guarded kwarg; the field's value is `""` because the
CreditMemo entity-level filter set is `[]`. A Tip block *would* be the
defect (the tip should not fire when it has no filter types to name).

## V2 — Paraphrase

Prompt: `recent credit memos` against `fa-esll-saasfademo1`. Saved
transcript at `/tmp/v2_credit_memo_paraphrase.txt` (89 lines,
`exit=0`).

The parser's `b_credit_memos.sysprompt` teaches five phrasings; V1
used `list credit memos` and V2 uses a different one to confirm the
extractor is not hardcoded to a single verb.

Result (green): **byte-identical shape to V1.**

- Intent: `CreditMemo`, no filters, no include.
- Plan: one step, `list_receivables_credit_memos`, `tool_args: {}`.
- Answer: `Showing 25 of 2,261 credit memos.` Same count as V1 — the
  pod's total did not drift between the two runs.
- Same currency split, same status split, same 25-row table, same
  first row (`103002 | 300000348453912 | -25000.0 | INR | 2026-11-12 |
  Torrent Pharmaceuticals Limited | Complete`).
- No `─── Tip ───` block.

The extractor fires the same way on both phrasings. V2 green on one
run; a second run was not made (paraphrase non-determinism is V8's
domain, deferred).

## V3 — Siblings unchanged (Supplier, PO, Invoice)

Three cross-entity prompts proving PR #5 did not leak into the other
tip paths. Saved transcripts at `/tmp/v3a_supplier_tip.txt` (89 lines),
`/tmp/v3b_po_tip.txt` (92 lines), `/tmp/v3c_invoice_tip.txt` (95
lines).

| Prompt | Tip block | Labels |
|---|---|---|
| `list all suppliers` | present at line 77 | `business relationship, country, creation date, name, status` (Supplier's five) |
| `list all purchase orders` | present at line 80 | `creation date, last-updated date, status, supplier` (PO's four, minus `by_id` and `lifecycle_status`) |
| `unpaid invoices` | present at line 83 | `invoice date, invoice number, overdue, pending approval, purchase order, supplier, unpaid` (Invoice's seven, de-duplicated and sorted) |

**No sibling tip names `credit memo` or `CreditMemo`.** PR #5's two-file
change touches `ar.py` and `synthesizer.py`; it does not touch
`p2p.py`'s label maps or the Supplier / PO / Invoice branches. The
three sibling paths are unchanged.

## V4 — Negative (customer-scoped routes away from CreditMemo)

Prompt: `credit memos for customer ABC Application Software`. Saved
transcript at `/tmp/v4_credit_memo_scoped.txt` (117 lines, `exit=0`).

The parser's `b_customer_credit_memos.sysprompt` teaches: *"naming a
customer is the whole difference"* — a customer-scoped credit-memo
question routes to `CustomerAccount` with `AccountCreditMemo` in
include, not to `CreditMemo`. This V-step confirms the boundary.

Result (green):

- Intent: `target_entity: CustomerAccount`; filter `{type:
  by_customer_name, value: 'ABC Application Software'}`; include
  `['AccountCreditMemo']`.
- Plan: **two** steps — `get_customer_account_by_name` (customer_name
  literal), then `get_account_credit_memos` (iterating on `AccountId`).
  **Not** `list_receivables_credit_memos`.
- `grep -cE '^─── Tip ───'` → **`0`**. `CustomerAccountResponse` has no
  `narrowing_tip` field, so the renderer never emits a Tip block on
  this path.
- `grep -cE 'AccountCreditMemo|account_credit_memos|CustomerAccount'`
  → **`8`** matches across Intent, Plan, SQL projection, answer section
  header, summary. The account-child include is present and populated.

The parser boundary is intact: naming a customer routes away from
`CreditMemo`, away from `list_receivables_credit_memos`, and onto the
account-child path. PR #5's field and kwarg on `CreditMemoListResponse`
never reach this path. The structural fact confirmed live.

## V5 — Goldens (Intent-only)

Same scope PRs #1–#4 used: compare each golden's `Intent:` block to
the current pipeline's. Full-output byte-diff is not achievable (pod
drift, `sql_emitter` block, supplier 1256 rename) — Intent is the
shape decision.

| Golden | Prompt | Result |
|---|---|---|
| `count_suppliers.txt` | `Count of suppliers` | **MATCH** — `Supplier`, `count_only: True` |
| `po_2144_and_lines.txt` | `Show PO 2144 and its lines` | **MATCH** — `PurchaseOrder`, `by_id: 2144`, `include: ['PurchaseOrderLine']` |
| `suppliers_with_open_pos.txt` | `Which suppliers have open purchase orders?` | **MATCH** — `Supplier`, `has_open_PO: True` |

Saved transcripts at `/tmp/v5_1_count_suppliers.txt` (53 lines),
`/tmp/v5_2_po_2144_lines.txt` (97 lines),
`/tmp/v5_3_suppliers_open_pos.txt` (122 lines).

**V5-3 did not hit the transient upstream timeout this run.** The
`has_open_PO` shape does 25 sequential `search_purchase_orders`
fan-out calls; PR #2 (`supplier.md` §V5-3), PR #3 (`invoice.md` §V5-3),
and PR #4 (`standard_receipt.md` §V5-3) all recorded a timeout on the
first attempt that cleared on retry. This run produced the Intent on
the first try, so no retry was needed. Recorded as green on one run.

## V6 — pytest (scoped + synth blast-radius; full deferred)

**V6-full cannot run to completion on this environment.** Same class
as PRs #1–#4: the `mcp 2.x` / `langchain-mcp-adapters 0.3.1` conflict
breaks `tests/test_agent_runner.py` collection. Deferred to the MCP
migration PR.

V6 was run in the two scoped forms:

| Layer | Command | Result |
|---|---|---|
| scoped | `pytest -q tests/test_sample_and_disclose_credit_memo.py` | **`5 passed in 0.14s`** |
| synth blast-radius | four files: `test_synthesizer`, `test_synthesizer_supplier_records`, `test_synthesizer_truncation_narration`, `test_synthesizer_aggregation` | **`97 passed, 1 deselected in 0.18s`** |

Saved logs: `/tmp/t_pr5_v6_scoped.log`, `/tmp/t_pr5_v6_synth.log`.

**The `97 passed, 1 deselected` count matches PRs #2 and #4 exactly**
for the same four-file set. PR #5's two-file change did not perturb
the synthesizer surface those files cover.

What is **not** established: whether some test in the full suite
regresses for reasons PR #5 caused indirectly. Same gap PRs #1–#4
recorded; the same `MCP_DEPENDENCY_CONFLICT.md` blocks its resolution.

## V7 — Test fails without the fix

Two source commits on the branch, and their red-then-green evidence:

- **`742a431`** — `test(phase-3): credit_memo — failing test for
  narrowing_tip on CreditMemoListResponse`. Committed **before** the
  fix. Ran against the pre-fix tree; `/tmp/t_pr5_red.log` records
  **`3 failed, 2 passed`** with `AttributeError:
  'CreditMemoListResponse' object has no attribute 'narrowing_tip'` on
  the three failing tests (`test_credit_memo_response_has_narrowing_tip_field`,
  `test_sampled_credit_memo_carries_empty_narrowing_tip`,
  `test_complete_credit_memo_carries_empty_narrowing_tip`). The two
  passing tests (`test_total_credit_copied_from_first_row`,
  `test_total_credit_none_when_tool_withholds_it`) were green on red
  — PR #5 does not touch `total_credit` handling, and the coverage
  locks that fact in.

- **`35a0095`** — `feat(phase-3): credit_memo — add narrowing_tip
  field and guarded kwarg`. Committed **after** the red. Ran against
  the post-fix tree; `/tmp/t_pr5_final_green.log` records **`5 passed
  in 0.11s`**.

The red-green pair is the standard FIX_PLAN §8 step 3 discipline:
red committed before green, both pytest-run, neither a post-hoc stash.

## V8 — N-run reproducibility (deferred)

Deferred alongside V6. A 20-run sweep of `list credit memos` would
test whether the parser's CreditMemo routing and the multi-currency
note are deterministic across runs. The single V1 and V2 runs are each
green; the N≥20 sweep is deferred to the same window that lands the
MCP migration.

## V9 — --validate (not required)

No `.sysprompt` block was changed in this PR. Confirmed on the branch:
`git diff master..HEAD -- 'src/spire/nl_parser/context/' | wc -l` → `0`.

Per PR #1's precedent (`_is_explicit_po_list` is code-only and had no
V9 requirement), PR #2's, PR #3's, and PR #4's: pure-Python fix, no
`.sysprompt` change, no `--validate` sweep required.

## V-walk state

| V | Status | Note |
|---|---|---|
| V0 | green | opened as Shape A after reading master at `7e786c7` — path already samples; field + guard + empty-by-construction tip |
| V1 | green | `list credit memos` — 25 of 2,261, multi-currency note fired, no Tip block (correct) |
| V2 | green | `recent credit memos` — byte-identical shape to V1 |
| V3 | green | `list all suppliers` / `list all purchase orders` / `unpaid invoices` — three tips populated, none mentions CreditMemo |
| V4 | green | `credit memos for customer ABC Application Software` — routes to CustomerAccount + AccountCreditMemo, no Tip block |
| V5 | green | three golden Intents matched; V5-3 no timeout this run |
| V6 | scoped + synth green; full deferred | branch tests `5 passed`; synth blast-radius `97 passed, 1 deselected`; full-suite blocked by MCP conflict |
| V7 | green | two commits (`742a431` red, `35a0095` fix), red-then-green verified |
| V8 | deferred | N≥20 sweep deferred to MCP migration PR |
| V9 | not required | no `.sysprompt` change (`git diff` confirms 0 lines) |

**State:** draft.
