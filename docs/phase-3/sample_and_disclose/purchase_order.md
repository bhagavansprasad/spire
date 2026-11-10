# Phase 3 — Sample-and-disclose: PurchaseOrder

**Branch:** `Phase3-PurchaseOrder-Sample`
**PR:** TBD (this file is committed before the branch exists; PR number
added when the PR is opened, per FIX_PLAN.md §8 step 8)
**State:** in-progress
**Finding:** meeting capture §1 — `get po with distribution details`
refuses with `missing_identifier`; an SME would answer it. Rule 28
defect.

## V0 — Fix statement

The parser will set `intent.list_all=True` for a PurchaseOrder intent
that names a Spire-supported child (PO line, schedule, distribution)
without naming a specific PO, via a sibling extractor
`_is_sampleable_po_request` beside `_is_explicit_po_list`; the
planner's existing guard then permits a bounded 25-row sample, and
`PurchaseOrderResponse` gains a `narrowing_tip` field populated by
`build_narrowing_tip` (parameterised with `labels_map` and a
`_PURCHASE_ORDER_FILTER_LABELS` dict) so the sample discloses itself and
tells the user how to narrow.

## V1 — Reproducer

TBD (fill after the failing test is committed and run)

## V2 — Paraphrase

TBD

## V3 — Sibling (unchanged)

TBD

## V4 — Negative (still refuses)

TBD

## V5 — Goldens

TBD

## V6 — pytest

TBD

## V7 — Test fails without the fix

TBD

## V8 — N≥20 (parser changes)

TBD

## V9 — --validate (sysprompt changes)

TBD

## Deviations from the F-NNN entry's suggested fix

TBD

## Not checked

TBD

## S11 — Coverage expansion

TBD
