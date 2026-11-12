# Phase 3 — Sample-and-disclose: Invoice

**Branch:** `Phase3-Invoice-Sample`
**PR:** #205
**State:** closed
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

## V1 — Reproducer (live)

Prompt: `invoices in 2024` against the dev pod (MCP server on 4001,
post-`d964bb6`). The Invoice analogue of PR #1's `get po with
distribution details` and PR #2's `get all suppliers` — a filter-scoped
list where the source total is known and the tip must populate.

Result (green):
- Intent: `Invoice`, `invoice_date` filter `{from: '2024-01-01', to: '2024-12-31'}`
- Plan: 1 step, `search_invoices` with `invoice_date_after` / `invoice_date_before`
- Outputs: `invoices: 25 record(s)` (complete rows; +9 projected fields)
- Summary: `Showing 25 of 2,689 invoices.`
- Truncation: `invoices: 2689 total in source; 25 returned.`
- Tip: `Reading all 2,689 invoices is slow. Narrow with a filter:
  invoice date, invoice number, overdue, pending approval, purchase
  order, supplier, unpaid.`

The seven tip labels are `_INVOICE_FILTER_LABELS` de-duplicated and
sorted: `invoice date` (from three date-mapped filters) appears once,
`by_id` is absent (Invoice has no `by_id`; the equivalent is
`invoice_number`, which is present). No `lifecycle_status` (PO-only).

**Sibling V1-control: `list all invoices` refuses.** Correct — the
Invoice guard requires one of the nine scoping filters; PR #3 does not
add a `list_all` reader. Recorded here as the by-design sibling, same
class as PR #1's V3 (`list all purchase orders` does list because PO
has a filter-less fetcher; Invoice does not).

## V2 — Paraphrase (two, different filters)

Two prompts, both reaching the same plain-invoice branch through
different filters — the Invoice analogue of PR #1's different-trigger /
different-child discipline.

Prompt 1: `invoices for supplier 1252`. Prompt 2: `unpaid invoices`.

Result (green, both):
- V2a Intent: `Invoice`, `supplier: '1252'`; plan `supplier_number: '1252'`
- V2a Summary: `Showing 25 of 1,326 invoices.`
- V2a Tip: seven labels, same as V1
- V2b Intent: `Invoice`, `unpaid: True`; plan `unpaid: True`
- V2b Summary: `Showing 25 of 12,805 invoices.`
- V2b Tip: seven labels, same as V1

The tip tracks the filter — 1,326 for the supplier, 12,805 for unpaid
— which is the per-query behaviour PR #2's Supplier tip demonstrated
and PR #1's PurchaseOrder tip demonstrated.

## V3 — Sibling (unchanged)

Three sub-cases, one per class of sibling PR #3 could have over-reached
into.

### V3a — multi-bucket Invoice (N/A)

Prompt: `show invoices for supplier 1252 and their lines`.
Refused: `Invoice lines for AP invoices are not supported`.

The parser has no AP-invoice-lines include. **AP Invoice has no
multi-bucket sibling on master.** The multi-bucket shape V0 (b) named
as coverage is **not reachable at the pipeline level for AP Invoice**
today; deferred to a future parser-sysprompt window that adds the
include. Recorded as a parser gap, not a PR #3 defect.

### V3b — empty result (green)

Prompt: `invoices for supplier 1252 over 999999999`.
Result: `No invoices found matching the criteria.` / `No invoices
found.` No tip, no truncation block. The empty short-circuit fires
before the tip's guard (`len(rows) < total_available` with
`0 < 0` returns false). Correct.

### V3c — single-record fetch (RED then fixed)

Prompt: `invoice number LEE-01-1006-111` (a by-number fetch, one
row, complete).

**At `d964bb6`** the response carried:
  `Reading all 1 invoices is slow. Narrow with a filter: ...`

That is over-reach: the tip is for a SAMPLE, and a complete
single-record fetch is not one. Same class as PR #1's V4a `show me
PO 2144` (a single PO is not a sample, so no tip).

**Fix at `d7d78c5`:** the plain-invoice branch's `narrowing_tip` kwarg
is guarded on `len(rows) < total_available` — sample-only. Effect on
the four shapes:
  - V1/V2 (25 of 2,689) → 25 < 2,689, tip fires
  - V3b (0 of 0) → 0 < 0, no tip
  - V3c (1 of 1) → 1 < 1, no tip
  - complete fetch (3 of 3) → 3 < 3, no tip

Two new tests (`test_by_invoice_number_does_not_carry_narrowing_tip`,
`test_complete_fetch_does_not_carry_narrowing_tip`) were red before
the fix (`t_v3c_red.log`: 2 failed, 3 passed) and green after
(`t_v3c_green.log`: 5 passed).

## V4 — Negative (cross-entity, unchanged)

Three prompts proving PR #3 did not widen the tip beyond Invoice.

- **V4a** `list all suppliers` → Supplier tip present, naming the
  Supplier labels (`business relationship, country, creation date,
  name, status`). No Invoice labels. Green.
- **V4b** `list all purchase orders` → PO tip present, naming the PO
  labels (`creation date, last-updated date, status, supplier`). No
  Invoice labels. Green.
- **V4c** `get all addresses` → `missing_identifier` refusal, same
  `Reason`/`Solution`/`Example` as PR #1's V4b. No plan, no tip.
  Green.

`_INVOICE_FILTER_LABELS` did not leak into the Supplier or PO paths.

## V5 — Goldens (Intent-only)

Same scope PR #1 and PR #2 used: compare the `Intent:` block from each
golden to the current pipeline's `Intent:` block for the same prompt.

| Golden | Golden Intent | Current Intent | Result |
|---|---|---|---|
| `count_suppliers.txt` | Supplier, `count_only: True` | same | **MATCH** |
| `po_2144_and_lines.txt` | PurchaseOrder, `by_id: 2144`, `include: ['PurchaseOrderLine']` | same | **MATCH** |
| `suppliers_with_open_pos.txt` | Supplier, `has_open_PO: True` | same | **MATCH** |

Three intents matched, byte-for-byte modulo whitespace. Pod drift in
the goldens' body (supplier count 431 → current pod; supplier 1256
renamed from `US Gas and Electric Rushi`) is pre-existing and not
caused by PR #3 — V5's Intent-only scope exists precisely so that
drift does not interfere.

## V6 — pytest (scoped green; full deferred)

Full-suite pytest cannot complete on this environment (pre-existing
MCP dependency conflict; `tests/test_agent_runner.py` collection
error). **V6-full deferred to the MCP migration PR**, same as PR #1
and PR #2.

Branch's own tests: **`5 passed` in
`tests/test_sample_and_disclose_invoice.py`** (t_v3c_green.log).

## V7 — Test fails without the fix

Two red bases on the branch, each committed **before** its
corresponding source fix, per FIX_PLAN.md §8 step 3:

- `68b85a4` — the narrowing_tip tests
  (`test_plain_invoice_list_carries_narrowing_tip`,
  `test_narrowing_tip_absent_when_source_is_complete`) red on
  `abebc9e`; green at `d964bb6` (`t_v7_green.log`).
- `d7d78c5` — the V3c tests
  (`test_by_invoice_number_does_not_carry_narrowing_tip`,
  `test_complete_fetch_does_not_carry_narrowing_tip`) red on
  `d964bb6` (`t_v3c_red.log`); green at `d7d78c5` (`t_v3c_green.log`).

Neither red was a post-hoc stash; both were committed and pytest-run
before the fix.

## V8 — N≥20 (deferred)

Deferred alongside V6. The single V1 and V2 runs are green; a 20-run
sweep is deferred to the same window that lands the MCP migration.

## V9 — --validate (not required)

No `.sysprompt` block was changed in this PR. The tip call-site and
the label map are pure-Python; the guard is a Python conditional.
Following PR #1's precedent (`_is_explicit_po_list` is code-only and
had no V9 requirement).

## Deviations from the F-NNN entry's suggested fix

### V-walk deviations

Three deviations from V0, one from the V-walk and two non-fixes that
are out-of-scope by design.

### V3c deviation — the tip over-reached onto a non-sample

The deviation PR #3's V-walk found. Same class as PR #1's Fix A/B/C
and PR #2's Fix D-a/D-b/E: a live defect the unit tests did not catch,
found by a real prompt against the pod.

At `d964bb6`, `invoice number LEE-01-1006-111` produced a tip on a
one-row complete fetch. The fix at `d7d78c5` guards the plain-invoice
branch's `narrowing_tip` kwarg on `len(rows) < total_available` —
sample-only. The guard fires on V1/V2 (25 of 2,689) and does not fire
on V3b (0 of 0), V3c (1 of 1), or any complete fetch.

### Out of scope — V3a parser gap

`show invoices for supplier 1252 and their lines` refuses with
`Invoice lines for AP invoices are not supported`. The parser has no
AP-invoice-lines include. AP Invoice has no multi-bucket sibling on
master, so V0 (b)'s multi-bucket coverage is not reachable at the
pipeline level. Deferred to a future parser-sysprompt window; not
PR #3's defect.

### Out of scope — Issue C (SQL emitter)

The `SQL projection:` block for `invoices in 2024` and
`unpaid invoices` shows unmapped-arg comments for
`invoice_date_before` and `unpaid` — the SQL overlay has no
`FilterSpec` for these Invoice-side filters. Pre-existing,
diagnostic-only (per `SQL_OVERLAY_POC.md`, "SQL execution is
deliberately out"), not caused by PR #3. The fix site is
`kg_sql_filter` (a future window's PR alongside the
multi-field-iteration finding). Recorded here as the same class
as PR #1's Issue C deviation.

### `personas.yaml` in the working tree

Local credential edit, never staged, not part of any PR.

### Design decision: sysprompt stays untouched on this PR

Same as PR #1 and PR #2: pure-Python fix, no `.sysprompt` change, so
no V9 sweep required. `_INVOICE_FILTER_LABELS` is Python data.

## Not checked

- **V6-full** and **V8** — both deferred to the MCP migration PR,
  same as PR #1 and PR #2.
- **V3a multi-bucket** — not reachable at the pipeline level for
  AP Invoice; deferred to a parser-sysprompt window.
- **The pod's `overdue` / `pending` filters** — not run in this
  V-walk; `unpaid` (V2b) exercised the same `search_invoices`
  plain-list branch, but the other two status filters were not
  individually prompted. A future window's N≥20 sweep (V8) will
  cover them.
- **The other pod's `invoice_number` variants** — V3c exercised
  `LEE-01-1006-111`; whether other number shapes (e.g. `PCS10027_0825`)
  behave identically is F-018's coverage, not PR #3's.

## S11 — Coverage expansion

V0 (b) named three coverage contributions beyond the tip population.
Status at `d7d78c5`:

- **Plain-list Invoice lock** — already green at
  `tests/test_synthesizer.py:477`; additionally locked in PR #3's
  test file by `test_plain_invoice_list_builds_locally_no_llm`.
- **Tip population** — `test_plain_invoice_list_carries_narrowing_tip`,
  `test_narrowing_tip_absent_when_source_is_complete` (V7a),
  `test_by_invoice_number_does_not_carry_narrowing_tip`,
  `test_complete_fetch_does_not_carry_narrowing_tip` (V3c).
- **Empty path** — exercised green in V3b live; not yet locked in
  PR #3's test file; a follow-up commit adds one test.
- **Multi-bucket** — not reachable at the pipeline level for AP
  Invoice; deferred to a parser-sysprompt window (V3a).

Sibling prompts (existing or to-be-written) for the same shape:

- `prompts/payables/payables_exhaust.txt` — the nine filter types
  reachable on Invoice, plus their paraphrases.
- A future prompt that names an AP-invoice-lines child, once the
  parser-sysprompt window adds it.
