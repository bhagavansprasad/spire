# Phase 3 — Sample-and-disclose: StandardReceipt

**Branch:** `Phase3-StandardReceipt-Sample`
**PR:** TBD (filled when the PR is opened, per FIX_PLAN.md §8 step 8)
**State:** open
**Finding:** MEETING_2026-11-10 §6 row 4 — the fourth entity in the
seven-PR sample-and-disclose sequence. StandardReceipt's **scoped** path
already samples on `master`: `synthesizer.py` returns a local
`StandardReceiptResponse` built by `build_standard_receipt_records`
(`ar.py`), with a local summary from `local_list_summary` and a
truncation disclosure from `_local_truncation`. PR #4 is therefore a
coverage + one-new-shape PR (the `narrowing_tip`), not a wiring change
on the StandardReceipt path.

The **unscoped** case (`get all receipts`) is a separate matter — see
"What PR #4 does NOT do" and §Deviations.

## V0 — Fix statement

StandardReceipt sample-and-disclose is **already implemented on
`master` at `6b299d0`** for the scoped single-bucket case. The
synthesizer branch

    if target_entity == "StandardReceipt" and len(outputs) == 1:
        name, rows = next(iter(outputs.items()))
        if rows and isinstance(rows[0], dict) \
                and "StandardReceiptId" in rows[0] \
                and "CustomerAccountNumber" in rows[0]:
            total_available, notes = _local_truncation(...)
            return StandardReceiptResponse(
                summary="\n".join(local_list_summary(...)),
                standard_receipts=build_standard_receipt_records(rows),
                truncation_notes=notes,
            )

returns a local, no-LLM `StandardReceiptResponse` with a bounded
sample, a local summary, and a truncation disclosure. **PR #4 does not
introduce the StandardReceipt scoped-list path.**

What PR #4 contributes:

  (a) **The narrowing tip.** `StandardReceiptResponse` (`ar.py`)
      carries `summary`, `standard_receipts`, and `truncation_notes`
      only — no `narrowing_tip` field. `PurchaseOrderResponse`,
      `SupplierResponse`, and `InvoiceResponse` all carry it. PR #4
      adds the field to `StandardReceiptResponse`, adds a
      `_STANDARD_RECEIPT_FILTER_LABELS` dict beside
      `_INVOICE_FILTER_LABELS` and `_SUPPLIER_FILTER_LABELS` in
      `p2p.py` (two entries — see (c)), and adds a
      `narrowing_tip=build_narrowing_tip(…, labels_map=_STANDARD_RECEIPT_FILTER_LABELS)`
      kwarg at the StandardReceipt return, mirroring the PO
      plain-list call-site and the Invoice plain-list call-site. The
      `build_narrowing_tip` function itself (`p2p.py`) already
      accepts `labels_map=` and de-duplicates labels (PR #1's Fix A);
      **it needs no change.**

  (b) **Coverage.** Tests that lock the scoped-list path (the
      synthesizer branch above), lock the new `narrowing_tip`
      population on a sampled result, and lock that the tip is
      **absent** on a complete fetch (mirroring PR #3's V3c guard).
      The `len(rows) < total_available` guard on the kwarg is the
      same sample-only guard PR #3 landed at `d7d78c5`; the tests
      exercise it on StandardReceipt.

  (c) **Evidence.** The V-walk below.

**The label map is two entries, not seven.** The KG's entity-level
filter set for StandardReceipt, read at `6b299d0` via
`_entity_level_filter_types()`, is:

    ['customer_name', 'customer_site']

That is the whole narrowing surface for this entity. `_STANDARD_RECEIPT_FILTER_LABELS`
maps exactly those two, and StandardReceipt has **no `by_id` filter in
the KG's entity-level set**, so the `if ft != "by_id"` exclusion every
other entity's call site uses is a no-op here — but the call site
keeps it anyway, matching the pattern, so a future KG change that adds
`by_id` does not silently widen the tip.

**What PR #4 does NOT do, and why.** The meeting §6 row 4
prescription ("Extend extractor; `sample_all=True` on
`search_standard_receipts`; field on `StandardReceiptResponse`; tip
block") describes a change master's StandardReceipt path does not need
and cannot use:

- `search_standard_receipts` (`src/spire/mcp_server/tools/standard_receipts.py`)
  has **no `sample_all`** argument.
- The tool **refuses to run unscoped**: its first statement is
  `raise ValueError("At least one of customer_name or customer_site is
  required.")`. The planner's StandardReceipt guard
  (`planner.py`, the `if intent.target_entity == "StandardReceipt":`
  block) exists precisely to pre-empt that ValueError — the planner's
  own comment records this: *"The KG advertised a fetcher the tool
  would not honour … The user saw a raw tool exception; the planner
  had every means to say so first."*
- A parser-side sibling extractor that set `list_all` for
  StandardReceipt would therefore fire and land at the planner's
  `MISSING_IDENTIFIER` refusal — the `f36b11c` defect
  `supplier.md` §V0-history records for Supplier, one entity over, but
  worse: for Supplier, `list_all` landed nowhere; for StandardReceipt,
  it would land in an explicit refusal.

**Out of scope, noted here as required.**

- The unscoped StandardReceipt case (`get all receipts`) is refused
  at `planner.py`'s `MISSING_IDENTIFIER` guard by design. The tool
  (`standard_receipts.py`) requires a `customer_name` or
  `customer_site` and raises `ValueError` without one; the guard
  pre-empts that. Relaxing the tool and the guard is a separate PR
  (tool-side scope-check relaxation plus honest-total work), not this
  one's scope. See §Deviations for the one-line pointer.
- `SQL_EMITTER_MULTIFIELD_ITERATION.md` and `MCP_DEPENDENCY_CONFLICT.md`
  — same as PR #1, PR #2, PR #3. A future window's PRs.
- `personas.yaml` — local credential edit, never staged, not part of
  any PR.

## V0 — history

The original V0 would have been the meeting §6 row 4 prescription
above, corrected on reading master. Preserved here per the
`supplier.md` §V0-history precedent so the branch's own record of
what it first claimed is not lost:

> The parser will set `intent.list_all=True` for a
> StandardReceipt intent that names no narrowing filter, via a
> sibling extractor beside `_is_explicit_po_list` and the PR #1
> sibling `_is_sampleable_po_request`; `search_standard_receipts`
> will accept `sample_all=True`; the planner's existing
> StandardReceipt path will then permit a bounded 25-row sample;
> and `StandardReceiptResponse` will gain a `narrowing_tip` field
> so the sample discloses itself.

**Why it was wrong.** Read from `master` at `6b299d0`:

- `search_standard_receipts` has no `sample_all` argument
  (`grep 'sample_all' src/spire/mcp_server/tools/standard_receipts.py`
  returns nothing).
- The tool raises `ValueError` if both `customer_name` and
  `customer_site` are absent — the scope check is a hard requirement,
  not a missing default.
- `intent.list_all` has exactly one reader in the planner: the
  PurchaseOrder guard. A parser-side sibling that set it for
  StandardReceipt would hit the StandardReceipt guard first, which
  raises `RefusalError(MISSING_IDENTIFIER)`. It would fire and land
  in a refusal, not a sample.
- `StandardReceiptResponse` does carry `summary`, `standard_receipts`,
  `truncation_notes` — the fields needed by the scoped path — and the
  scoped path already runs locally in `synthesize_response`.

**The correction is the finding.** StandardReceipt's scoped path is
already in place; PR #4 is coverage plus one shape (the tip), not a
wiring change. The unscoped case stays refused by design, recorded as
one line in §Deviations.

This is the **fourth** such correction in four PRs:
- PR #1 (PurchaseOrder): `purchase_order.md` §Deviations Fix A/B/C —
  three defects the unit tests did not catch, surfaced by the V-walk.
- PR #2 (Supplier): `supplier.md` §V0-history — the `f36b11c`
  defect; the V0 itself corrected at `7b7bb51`.
- PR #3 (Invoice): `invoice.md` §Deviations — V3c; the V0 itself
  corrected on reading `master`.
- PR #4 (StandardReceipt): this file — meeting row's Verify column
  ("`get all receipts` answers") is not satisfiable from master without
  changing the tool and the planner guard; recorded rather than
  silently patched.

The brief's prediction ("expect to repeat that correction") is no
longer a prediction; it is the observed four-for-four rate.

## V1 — Reproducer (live)

TBD

## V2 — Paraphrase

TBD

## V3 — Sibling (unchanged)

TBD

## V4 — Negative

TBD

## V5 — Goldens

TBD

## V6 — pytest

TBD

## V7 — Test fails without the fix

TBD

## V8 — N-run reproducibility

TBD

## V9 — --validate (not required)

No `.sysprompt` block was changed in this PR. The tip call-site and the
label map are pure-Python; the guard is a Python conditional. Following
PR #1's precedent (`_is_explicit_po_list` is code-only and had no V9
requirement) and PR #2's and PR #3's same conclusion.

## V-walk state

| V | Status | Note |
|---|---|---|
| V0 | done | opened with the meeting row's prescription; corrected on reading `master` at `6b299d0` to reflect the already-implemented scoped path |
| V1 | pending | |
| V2 | pending | |
| V3 | pending | |
| V4 | pending | |
| V5 | pending | |
| V6 | pending | |
| V7 | pending | |
| V8 | pending | |
| V9 | not required | no `.sysprompt` change on the branch |

## Deviations

### Unscoped StandardReceipt is refused by design

`get all receipts` is refused at `planner.py`'s `MISSING_IDENTIFIER`
guard (`if intent.target_entity == "StandardReceipt": has_scope = …;
if not has_scope: raise RefusalError(...)`). The tool
`search_standard_receipts` requires one of `customer_name` or
`customer_site` and raises `ValueError` without one; the guard
pre-empts that ValueError with a structured refusal. Relaxing the
tool and the planner guard together — and adding honest total-count
handling for an unscoped fetch (the tool's `OVERFETCH_LIMIT=500`
caps the observable count, so `total_available` for an unscoped fetch
is a lower bound) — is a separate PR with its own V0, not PR #4's
scope. The meeting §6 row-4 Verify column ("`get all receipts`
answers with 25 rows + tip") is therefore not satisfied by this PR,
and this note records that rather than patching it.

### `personas.yaml` in the working tree

Local credential edit, never staged, not part of any PR.

### Design decision: sysprompt stays untouched on this PR

Same as PR #1, PR #2, PR #3: pure-Python fix, no `.sysprompt` change,
so no V9 sweep required. `_STANDARD_RECEIPT_FILTER_LABELS` is Python
data.

## Not checked

- V1–V8, pending the failing-test-first commit and the V-walk.
- The other entity's tip call-sites — PR #4 does not touch them.
- `SQL_EMITTER_MULTIFIELD_ITERATION.md` and `MCP_DEPENDENCY_CONFLICT.md`
  — out of scope, as recorded above.

## S11 — Coverage expansion

TBD

**State:** open. PR number filled at close, per `FIX_PLAN.md` §8 step 9.
