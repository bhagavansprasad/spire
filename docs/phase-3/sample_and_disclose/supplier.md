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

The parser will set `intent.list_all=True` for a Supplier intent that
names no narrowing filter, via a sibling extractor
`_is_sampleable_supplier_request` beside `_is_explicit_po_list` and the
PR #1 sibling `_is_sampleable_po_request`; the planner's existing
Supplier path will then permit a bounded 25-row sample, and the
Supplier `narrowing_tip` that already exists on `master` will be
populated so the sample discloses itself and tells the user how to
narrow.

**The scope question this V0 does not yet answer, deliberately.** V0
is opened before any source read. STATUS.md §Next concrete action says
"Supplier already samples" and the file is opened with V0 only — the
same discipline `purchase_order.md` was opened with. Whether the fix
is:

  (a) a parser sibling only (analogous to PR #1's
      `_is_sampleable_po_request`, wired into `parse()` and setting
      `intent.list_all` for the Supplier entity);

  (b) a parser sibling **plus** a planner guard change (the Supplier
      guard may already accept filter-less intents — checked in V1);

  (c) a parser sibling **plus** nothing else (the Supplier tip already
      fires when `intent.list_all` is True and a Supplier bucket is
      returned — checked in V1);

will be settled by V1's first live run against `fa-esll-saasfademo1`,
before any source edit. This V0 does not assume which of (a), (b), (c)
holds. The V0 sentence is the outcome the fix must produce; the V-walk
fills in the mechanism.

**One carry-forward this V0 records.** PR #2 will not touch
`sql_emitter.py` or `sql_overlay.py`. The Issue C finding file
(`SQL_EMITTER_MULTIFIELD_ITERATION.md`, commit `fe5a41f`) is the
record; a future window fixes both defects in its own PR. If V1's SQL
projection output happens to surface them again, they are noted here
and not fixed in PR #2 — same discipline PR #1's `purchase_order.md`
§Deviations followed.

## V-walk state

TBD after the first live run. Filled in by the cells that follow this
commit; frozen `State: closed` at PR merge, per `FIX_PLAN.md` §8 step 9.
