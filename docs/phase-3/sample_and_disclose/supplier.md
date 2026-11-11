# Phase 3 — Sample-and-disclose: Supplier

**Branch:** `Phase3-Supplier-Sample`
**PR:** TBD (this file is committed before the branch's PR is opened;
PR number added when the PR is raised, per `FIX_PLAN.md` §8 step 8)
**State:** in-progress
**Finding:** MEETING_2026-11-10 §6 row 2 — the second entity in the
seven-PR sample-and-disclose sequence. Supplier already samples on
`master`: `SupplierResponse` carries `narrowing_tip`, and
`build_narrowing_tip`'s default filter-label map is the Supplier one.
PR #2 is therefore mostly a proof that the extractor path works for
the shape that already has all the plumbing — not a wiring change on
the Supplier path itself.

## V0 — Fix statement

Supplier sample-and-disclose is already implemented on `master`. The
synthesizer's plain-list branch (`synthesizer.py` — the
`plain_supplier_bucket` guard) returns a `SupplierResponse` with a
bounded sample and a populated `narrowing_tip` for any filter-less
Supplier intent, with **no** parser, planner, or synthesizer change
needed. PR #2 does not introduce the Supplier path.

What PR #2 contributes:

  (a) **Coverage.** Tests that would have failed if the plain-list
      path, the two-bucket open-PO join, the F-053 four-bucket
      join, or the empty-supplier path were broken. These lock the
      behaviour PR #1 and earlier windows built, and they are the
      regression base for later Supplier work.

  (b) **One new shape.** A Supplier prompt that names **two or more
      distinct child buckets at once** — e.g. contacts *and* sites,
      or contacts *and* addresses *and* open purchase orders — is
      not covered by any local builder on `master`. Every
      `_supplier_with_*` helper in `p2p.py` handles exactly ONE
      child bucket (plus the supplier bucket); a three-bucket shape
      produces `len(outputs) != 1`, so `plain_supplier_bucket`
      returns `None`, no other local builder claims the shape, and
      the response falls to the LLM path. That is the same
      overrun risk the degenerate-output guard was written
      against, and the same class of failure PR #1's
      `get po with distribution details` surfaced on the PO side.
      PR #2 fixes this shape locally, mirroring the existing
      join-builder pattern (`_supplier_with_open_pos` and its
      siblings).

  (c) **Evidence.** The V-walk below records what the plain-list
      case does live, what the two-bucket and four-bucket cases do,
      what the new multi-child case does before and after the fix,
      and which shapes are covered by which local builder — the
      same discovery discipline `purchase_order.md` §Deviations
      recorded for PR #1.

**What PR #2 does NOT do.** It does not introduce a Supplier sibling
extractor. The PurchaseOrder guard in `planner.py`
(`if not intent.filters and not intent.list_all:`) is
PurchaseOrder-specific; there is no Supplier equivalent, so
`intent.list_all` has no Supplier reader and setting it for Supplier
would be a flag that fires and lands nowhere. The original V0
committed at `f36b11c` proposed exactly that; see `## V0 — history`
below. The correction is the finding: **the Supplier path is already
in place, and the PR is coverage plus one shape, not a wiring
change.**

**One carry-forward this V0 records.** PR #2 will not touch
`sql_emitter.py` or `sql_overlay.py`. The Issue C finding file
(`SQL_EMITTER_MULTIFIELD_ITERATION.md`, commit `fe5a41f`) is the
record; a future window fixes both defects in its own PR. If V1's
SQL projection output happens to surface them again, they are noted
here and not fixed in PR #2 — same discipline PR #1's
`purchase_order.md` §Deviations followed.

## V0 — history

The original V0, committed at `f36b11c` and superseded by the V0
above, is preserved here so the branch's own record of what it first
claimed is not lost:

> The parser will set `intent.list_all=True` for a Supplier intent
> that names no narrowing filter, via a sibling extractor
> `_is_sampleable_supplier_request` beside `_is_explicit_po_list` and
> the PR #1 sibling `_is_sampleable_po_request`; the planner's
> existing Supplier path will then permit a bounded 25-row sample,
> and the Supplier `narrowing_tip` that already exists on `master`
> will be populated so the sample discloses itself and tells the
> user how to narrow.

**Why it was wrong.** B7a's inspection on this branch showed that
`intent.list_all` has no Supplier reader: the only guard that
consults it is the PurchaseOrder block in `planner.py`. A sibling
extractor that sets `list_all` for Supplier would fire and land
nowhere. The corrected V0 reflects the code; the original is kept
here for the record.


## V-walk state

TBD after the first live run. Filled in by the cells that follow this
commit; frozen `State: closed` at PR merge, per `FIX_PLAN.md` §8 step 9.
