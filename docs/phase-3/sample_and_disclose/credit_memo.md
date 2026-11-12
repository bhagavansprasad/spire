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

## V-walk state

| V | Status | Note |
|---|---|---|
| V0 | pending | this file |
| V1 | pending | positive sample; expected `narrowing_tip=""` |
| V2 | pending | paraphrase; expected same shape |
| V3 | pending | siblings unchanged (Supplier, PO, Invoice, StandardReceipt) |
| V4 | pending | negative; cross-entity tip leak check |
| V5 | pending | goldens Intent-only |
| V6 | pending | scoped + narrow + synth blast-radius; full deferred per MCP conflict |
| V7 | pending | test fails without the fix |
| V8 | pending | deferred to MCP migration PR |
| V9 | not required | no `.sysprompt` change |

**State:** draft.
