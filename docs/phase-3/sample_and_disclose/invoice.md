# Phase 3 — Sample-and-disclose: Invoice

**Branch:** `Phase3-Invoice-Sample`
**PR:** TBD (this file is committed before the PR is opened; PR number
added when the PR is opened, per FIX_PLAN.md §8 step 8)
**State:** in-progress
**Finding:** MEETING_2026-11-10 §6 row 3 — the third entity in the
seven-PR sample-and-disclose sequence. The Invoice plain-list path
already samples on `master`: `synthesizer.py:1088–1113` returns a
local `InvoiceResponse` built by `plain_invoice_bucket`
(`p2p.py:1182–1201`), with a local summary and truncation disclosure.
PR #3 is therefore a coverage + one-new-shape PR (the `narrowing_tip`),
not a wiring change on the Invoice path.

## V0 — Fix statement

Invoice sample-and-disclose is **already implemented on `master` at
`9724282`** for the plain single-bucket case. `synthesizer.py:1088–1113`
returns a local `InvoiceResponse` built by `plain_invoice_bucket`
(`p2p.py:1182–1201`), with `local_list_summary` producing the count
line and `_bucket_truncated` the sample flag. The
`test_synthesize_response_invoice_entity_selects_invoice_schema` test
(`tests/test_synthesizer.py:477`) already asserts this path is local
(`with_structured_output.assert_not_called()`). **PR #3 does not
introduce the Invoice plain-list path.**

What PR #3 contributes:

  (a) **The narrowing tip.** `InvoiceResponse` (`p2p.py:340–347`)
      carries `summary`, `invoices`, and `truncation_notes` only —
      no `narrowing_tip` field. `PurchaseOrderResponse` (immediately
      below in the same file) and `SupplierResponse` both carry it.
      PR #3 adds the field to `InvoiceResponse`, adds an
      `_INVOICE_FILTER_LABELS` dict beside `_SUPPLIER_FILTER_LABELS`
      and `_PURCHASE_ORDER_FILTER_LABELS` (no such dict exists today
      — R3), and adds a
      `narrowing_tip=build_narrowing_tip(…, labels_map=_INVOICE_FILTER_LABELS)`
      kwarg at the `synthesizer.py:1088` return, mirroring the PO
      plain-list call-site at `synthesizer.py:1049`. The
      `build_narrowing_tip` function itself (`p2p.py:1481–1510`)
      already accepts `labels_map=` and de-duplicates labels (PR #1's
      Fix A); **it needs no change.**

  (b) **Coverage.** Tests that lock the plain-list path (already
      green at `tests/test_synthesizer.py:477`), add coverage for the
      multi-bucket `ReceivablesInvoice` paths Invoice users reach
      (lines / tax / DFF — currently only `ReceivablesInvoiceResponse`
      paths are covered, per R10), lock the empty path via
      `_all_buckets_empty`, and lock the new `narrowing_tip`
      population. The last can only exist after (a).

  (c) **Evidence.** The V-walk below.

**What PR #3 does NOT do, and why.** The meeting §6 row 3
prescription ("Extend extractor; `sample_all=True` arg on
`search_invoices`") describes a change master's Invoice path does not
need and cannot use.

- `search_invoices` (`src/spire/mcp_server/tools/invoices.py:86–100`)
  has **no `sample_all`** argument (R5, and `grep 'sample_all'` on
  the file returns nothing).
- The planner's Invoice guard
  (`src/spire/planner/planner.py:130–151`) has **no `list_all`**
  reader (R6); `intent.list_all`'s sole reader is the PurchaseOrder
  guard.
- A parser-side sibling extractor that set `list_all` for Invoice
  would therefore fire and land nowhere — the `f36b11c` defect
  `supplier.md` §V0-history records for Supplier, one entity over.
- `search_invoices` **is** in `_LIMIT_CAPABLE_TOOLS`
  (`registries.py:246`), so `intent.list_limit` would reach it if a
  cap were set — but PR #3 does not set one, because PR #3 does not
  add a `list_all` reader. The limit path exists and PR #3 does not
  engage it.

**Out of scope, noted here as required.**

- `SQL_EMITTER_MULTIFIELD_ITERATION.md` — exists on `master` at
  `850feb5` (landed at `fe5a41f` on the PR #2 branch). A future
  window's PR. **Not** fixed in PR #3.
- `MCP_DEPENDENCY_CONFLICT.md` — the conflict is unresolved; the
  recommended fix is a separate PR. **V6/V8 are deferred for PR #3,
  same as PR #1 and PR #2.** They will run once the migration lands.
- `personas.yaml` — local credential edit, never staged, not part of
  any PR.

## Deviations

### Deviations from the STATUS.md hand-off

Two `STATUS.md` statements read at `9724282` are stale and this PR's
V0 supersedes them. Per the "report, do not patch" rule, they are
recorded here and the `STATUS.md` body migration is scheduled as a
**fifth docs correction**, separate from this PR, on top of the
V0-only commit's tip.

**(a) `STATUS.md`'s PR #1-window body.** `STATUS.md`'s
`## Issue A` — specifically the "What is done", "V-walk state
table", "Next concrete action", "Issue B" closing, and "Pointers"
last line — still describe the PR #1 window. The header was
corrected at `9724282` (`Phase3-Invoice-Sample`; base `983a7fb`;
merges `2a23906`/`850feb5`; docs commits `05d7978`/`983a7fb`), but
the body migration is a fifth docs correction, scheduled
separately. It does not block this PR.

**(b) `STATUS.md`'s `§Next concrete action` bullet 3.** The bullet
says *"the Invoice path already carries a `narrowing_tip` field on
its response"*. That is false at `9724282`. `p2p.py:340–347` shows
`InvoiceResponse` with `summary` / `invoices` / `truncation_notes`
only; `narrowing_tip` is on `PurchaseOrderResponse` and
`SupplierResponse`, not on `InvoiceResponse`. There is no
`_INVOICE_FILTER_LABELS` beside `_SUPPLIER_FILTER_LABELS` and
`_PURCHASE_ORDER_FILTER_LABELS`. PR #3 **adds** the field. The
statement is superseded by this V0.

## V1–V9

TBD (this file is committed V0-only, per FIX_PLAN.md §8 step 1;
the V-walk below fills in as PR #3 proceeds.)

## Not checked

TBD

## S11 — Coverage expansion

TBD
