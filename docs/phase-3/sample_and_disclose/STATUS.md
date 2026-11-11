# Phase 3 — Sample-and-disclose: WINDOW STATUS

**Window state at last update.** Read this first when resuming. It is
the resume surface; the per-PR evidence files are the durable record.

**Last updated:** 2026-11-11
**Branch:** `Phase3-PurchaseOrder-Sample`
**Base:** `master` at `a78c00b`
**Branch commits:** `2681217` (failing test, V7 evidence base),
`c71488d` (MCP conflict finding, not a fix)
**Uncommitted (four, the PR's source change set):**
`src/spire/nl_parser/parser.py`, `src/spire/synthesizer/p2p.py`,
`src/spire/synthesizer/synthesizer.py`,
`tests/test_sample_and_disclose_po.py`
**Uncommitted (NOT part of the PR):** `personas.yaml` — a local
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

V-walk is complete for what can run this window (V1–V5, V7 green;
V6 and V8 deferred behind the MCP conflict; V9 not required).

Remaining before PR #1 is opened:

1. Commit the **source change set** — four files
   (`parser.py`, `p2p.py`, `synthesizer.py`,
   `tests/test_sample_and_disclose_po.py`) — as one commit on
   `Phase3-PurchaseOrder-Sample`, on top of `2681217`. Message
   names the extractor, the tip parameterisation, and the two
   V1-surfaced fixes (label de-dup, `lifecycle_status` exclusion).
2. Commit the **doc changes** — `purchase_order.md`
(V1–V9 filled) and `STATUS.md` (this file) — as one commit,
   so the branch history shows `fix → evidence` cleanly.
3. Open PR #1 with the template from `docs/fixes/FIX_PLAN.md`
   §11.2. PR body names V6/V8 as deferred with a pointer to
   `MCP_DEPENDENCY_CONFLICT.md`.

Do **not** stage `personas.yaml` (a local credential edit; not
part of the PR).

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

**Permanent fix** (separate PR, separate window): the overlay's
`kg_sql_join` rows must declare the named binds for multi-field
iteration, or `_emit_step` in `sql_emitter.py` needs a new shape. It
is a real design change, not a patch.

**Finding recorded:** `docs/phase-3/sample_and_disclose/SQL_EMITTER_MULTIFIELD_ITERATION.md`
(NOT yet written — **next window must write it before touching the
emitter**; the finding is recorded here in the interim).

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
