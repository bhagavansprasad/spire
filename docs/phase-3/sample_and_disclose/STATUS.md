# Phase 3 — Sample-and-disclose: WINDOW STATUS

**Window state at last update.** Read this first when resuming. It is
the resume surface; the per-PR evidence files are the durable record.

**Last updated:** 2026-11-12
**Branch:** `Phase3-Invoice-Sample` — newly created for PR #3
(Invoice). Base commit `983a7fb`.
**Merged:** PR #203 (PurchaseOrder) at `2a23906`; PR #204 (Supplier)
at `850feb5`.
**Post-merge docs commits:** `05d7978` (froze `supplier.md` at
`State: closed`), `983a7fb` (this file — PR #3 hand-off).
**Base for this window:** `master` at `983a7fb`.
**Uncommitted (NOT part of any PR):** `personas.yaml` — a local
credential change made outside this work. Do not stage it. Do not
commit it.

---

## Issue A — the feature (this branch)

PR #1 of the seven-PR sequence in
`docs/plan/MEETING_2026-11-10_sample_and_disclose.md` §6:
**PurchaseOrder sample-and-disclose**, the anchor PR.

### What is done

- Evidence file opened on `master` (V0 only): `purchase_order.md`.
- Failing test committed on branch: `2681217`.
- Source change set (uncommitted, above): the sibling extractor
  `_is_sampleable_po_request` in `parser.py`, `_PURCHASE_ORDER_FILTER_LABELS`
  + `labels_map` parameter + `narrowing_tip` field in `p2p.py`, PO tip
  blocks (with `lifecycle_status` excluded) in `synthesizer.py`.
- Test file `tests/test_sample_and_disclose_po.py` has 12 tests,
  all passing.
- Three fixes landed after the initial V-walk failures:
  - Fix A: `build_narrowing_tip` de-duplicates labels (`sorted(set(labels))`)
    so four PO filters sharing "creation date" do not repeat the label.
  - Fix B: the two PO tip call sites in `synthesizer.py` exclude
    `lifecycle_status` alongside `by_id`. `lifecycle_status` is a
    fetch-by-value filter, not a narrowing filter; suggesting it in a
    sample tip is noise.
  - Fix C: replaced a tautological `test_build_narrowing_tip_excludes_
    lifecycle_status` with a `synthesize_response`-level test that
    actually exercises the caller-side exclusion.

### V-walk state

| Step | State | Note |
|---|---|---|
| V0 — fix statement | done | in `purchase_order.md` |
| V1 — reproducer (live) | **green** | `get po with distribution details` → 25-row sample + tip `creation date, last-updated date, status, supplier` |
| V2 — paraphrase | **green** | `show purchase orders with their schedules` → 2-step plan, `POSchedule` child, same tip; reproduced twice |
| V3 — sibling unchanged | **green** | `list all purchase orders` → 1-step plan, empty include (no over-reach by the new extractor) |
| V4 — negative still refuses | **green** | V4a `show me PO 2144` → `by_id` fetch, 1 record, no tip; V4b `get all addresses` → `missing_identifier` refusal |
| V5 — goldens unchanged | **green** | three intents matched (`count_suppliers`, `po_2144_and_lines`, `suppliers_with_open_pos`); full-file drift explained (SQL projection block predates goldens; pod supplier count 431→395) |
| V6 — full pytest | **deferred** | blocked by MCP dependency conflict; pointer below; branch's own tests: `12 passed` |
| V7 — test fails without fix | **green** | commit `2681217` is the red evidence |
| V8 — N≥20 | **deferred** | depends on V6; same MCP conflict |
| V9 — `--validate` | **not required** | no `.sysprompt` changed in this PR |

### Next concrete action

**This branch is done.** PR #204 merged to `master` at `850feb5`.
The V-walk for what could run in that window is complete (V1–V5,
V7, V9 green; V6 scoped + narrow + synth-blast-radius green, full
deferred; V8 partial at N=4). The evidence file
(`supplier.md`) is frozen at `State: closed`.

The next window starts **PR #3 (Invoice sample-and-disclose)**,
the third row of the seven-PR sequence in
`docs/plan/MEETING_2026-11-10_sample_and_disclose.md` §6:

    git checkout -b Phase3-Invoice-Sample

Prerequisites and first tasks, in order:

1. **Read** `MCP_DEPENDENCY_CONFLICT.md` before any work. If the
   MCP migration has landed as its own PR by then, V6 and V8 are
   unblocked for PR #3; if not, they are deferred again the same
   way PR #1 and PR #2 deferred them.
2. **Check the Issue C finding is on `master`** —
   `docs/phase-3/sample_and_disclose/SQL_EMITTER_MULTIFIELD_ITERATION.md`
   landed on `master` as part of PR #204 (commit `fe5a41f` on the
   branch, `850feb5` on `master`). It is a finding only; the
   emitter is not fixed. Do not fix it in PR #3 — it is a future
   window's PR, not Invoice's.
3. **Open the PR #3 evidence file** —
   `docs/phase-3/sample_and_disclose/invoice.md` — with V0 only,
   same pattern as `supplier.md` was opened. The V0 statement
   must be based on a read of `master`'s current Invoice path
   (does `plain_invoice_bucket` already sample? Does the tip fire?
   Is there a guard?) — **not** on the meeting's prescription.
   The meeting §6 row 3 names the shape ("Extend extractor;
   `sample_all=True` arg on `search_invoices`; `narrowing_tip` on
   `InvoiceResponse`; tip block"), but the V0 may discover the
   shape is different on `master` — exactly as PR #2's V0
   correction at `7b7bb51` discovered Supplier already sampled and
   PR #2 became a coverage + one-new-shape PR, not a wiring
   change.
4. **Write the failing test first** — `tests/test_sample_and_disclose_invoice.py`.
   Red before fix, per `FIX_PLAN.md` §8 step 3. Read
   `test_sample_and_disclose_supplier.py` first: its five original
   tests (plain list, two-bucket join, four-bucket join, empty,
   multi-child) are the coverage template. Do not assume Invoice
   will be the same shape as Supplier — the Invoice path already
   carries a `narrowing_tip` field on its response, but whether
   the tip is *populated* on `master` is the question PR #2
   had to answer for Supplier, and PR #3 must answer it for
   Invoice.

**Two carry-forward notes from PR #2.**

- **`personas.yaml`.** Confirm `git status` is clean before
  staging anything in the new window. It is a local credential
  edit; it does not go into any PR.
- **V-walk will surface defects the unit tests do not catch.**
  PR #1 found three (Fix A/B/C); PR #2 found three more (Fix
  D-a, D-b, E). Expect the same on PR #3. Read `supplier.md`
  §Deviations for the shape of those fixes: a live-run surface, a
  targeted fix commit, a re-run that proves the fix. Do not
  assume the tests you write at step 4 are the tests PR #3
  needs; they are the tests PR #3 *starts* with.

---

## Issue B — MCP dependency conflict (separate work, not this branch)

`fastmcp 4` requires `mcp 2.x`. `langchain-mcp-adapters` 0.3.1
requires `mcp<2` (imports `mcp.server.fastmcp`, removed in mcp 2.x).
They cannot share one Python environment. This breaks
`tests/test_agent_runner.py` collection on `master` and on this
branch alike.

**Permanent fix** (separate PR, separate branch, separate window):
migrate `src/spire/agent/runner.py` off `langchain-mcp-adapters` to
`fastmcp.Client` (or `langchain[mcp]` with a `fastmcp.Client` target)
and remove `langchain-mcp-adapters` from `requirements.txt`. The rest
of the codebase (three files) uses `fastmcp 4` directly and is
unaffected by the pin change.

**Finding recorded:** `docs/phase-3/sample_and_disclose/MCP_DEPENDENCY_CONFLICT.md`
(committed `c71488d`).

**Why deferred in this window:** the feature and the environment
conflict are separate issues; fixing the conflict would expand PR #1
from "sample-and-disclose for PO" to "sample-and-disclose for PO and
repair the entire MCP dependency triangle", and the codebase would
have to be migrated in one PR. The user explicitly chose to separate
the two.

**V6/V8 are deferred, not skipped, because of this.** They will run
once the MCP migration lands as its own PR. All PR #1's own tests pass
in isolation (`12 passed`).

---

## Issue C — SQL emitter multi-field iteration (separate work, not this branch)

Discovered during V1: the SQL projection emits malformed SQL for a
plan with multi-field iteration (the PO-distributions step uses three
parent fields per call). The output contains

    AND -- unmapped iteration arg: po_line_id
    AND -- unmapped iteration arg: line_location_id;

which is not valid SQL.

**Permanent fix** (separate PR, separate window): `_emit_step` in
`sql_emitter.py` needs a new shape. The overlay's `kg_sql_join` rows
are already correct; the defect is that `_emit_step` treats a
multi-field sentinel set as if it were a single-field one. It is a
real design change, not a patch. The finding file records the
three candidate shapes and the recommended one (`FilterSpec.value_kind`).

**Finding recorded:** `docs/phase-3/sample_and_disclose/SQL_EMITTER_MULTIFIELD_ITERATION.md`
— landed at `fe5a41f` on the PR #2 branch, on `master` at `850feb5`.
Out of scope for PR #3; a dedicated PR fixes §1 and §2 of that
finding.

**Why deferred:** the SQL emitter is diagnostic-only (per
`docs/design/SQL_OVERLAY_POC.md`, "SQL execution is deliberately
out"); the malformed output is a POC-2 issue, not a PR #1 defect. The
user explicitly chose to defer.

---

## Working rules this window is running under

- **One cell = one action.** Edit is its own cell. Verify is its own
  cell. `git add` is its own cell. `git commit` is its own cell.
  Test is its own cell. No bundling across those boundaries.
- **Patch cells are two cells.** The patch script is cell 1; the
  shell verification is cell 2; cell 2's output is the only evidence
  the patch landed. Do not skip cell 2. (Skipping it is how Fix B
  failed the first time: the patch did not land, and the test I
  designed did not catch it, and the live run showed `lifecycle`
  still in the tip.)
- **The test must fail first, then pass.** Commit the red; commit the
  green.
- **Issue A and Issue B/C are separate.** Do not fix environment or
  emitter problems in PR #1. Record them as their own findings.
- **No `git add personas.yaml`.** Not part of the PR.

---

## Pointers

- This PR's evidence: `docs/phase-3/sample_and_disclose/purchase_order.md`
- The seven-PR design: `docs/plan/MEETING_2026-11-10_sample_and_disclose.md` §6
- The V0–V9 standard: `docs/fixes/FIX_PLAN.md` §6
- The working cadence: `docs/plan/WORKING_STYLE.md` §15.3
- Issue B (MCP): `docs/phase-3/sample_and_disclose/MCP_DEPENDENCY_CONFLICT.md`
- Issue C (SQL emitter): **not yet written** — see §Issue C above
