# Phase 3 — Sample-and-disclose: WINDOW STATUS

**Window state at last update.** Read this first when resuming. It is
the resume surface; the per-PR evidence files are the durable record.

**Last updated:** 2026-11-12
**Branch:** `Phase3-ReceivablesInvoice-Sample` — PR #6 open (opened
against `master` at `3b27bf1`'s ancestor `2327fd0`; the branch tip is
`c9df032`, nine commits past the merge point).
**Merged:** PR #203 (PurchaseOrder) at `2a23906`; PR #204 (Supplier)
at `850feb5`; PR #205 (Invoice) at `3f3ff11`; PR #206 (StandardReceipt)
at `5eadf7b`; PR #207 (CreditMemo) at `4d301c4`.
**Post-merge docs commits:** `05d7978` (froze `supplier.md` at
`State: closed`), `983a7fb` (PR #3 `STATUS.md` hand-off), `9724282`
(PR #3 resume-docs correction), `5f9b554` (froze `invoice.md`),
`e7d31b2` (froze `standard_receipt.md`), `0c9f3ec` (PR #4
`STATUS.md` advance), `7e786c7` (PR #4 `HANDOFF.md` advance),
`341b9f9` (PR #5 extended prompt set findings), `5ef278c` (froze
`credit_memo.md`), this commit and the `HANDOFF.md` commit below
(PR #5 `STATUS.md`/`HANDOFF.md` advance).
**Base for this window:** `master` at `4d301c4`.
**Uncommitted (NOT part of any PR):** `personas.yaml` — a local
credential change made outside this work. Do not stage it. Do not
commit it.

---

## Issue A — the feature (all five PRs merged)

PRs #203 (PurchaseOrder, anchor), #204 (Supplier), #205 (Invoice),
#206 (StandardReceipt), #207 (CreditMemo) have all merged. The
seven-PR sample-and-disclose sequence's first five rows are done. The
durable record for each is its evidence file, frozen at
`State: closed`:

- `docs/phase-3/sample_and_disclose/purchase_order.md` — `#203`
- `docs/phase-3/sample_and_disclose/supplier.md` — `#204`
- `docs/phase-3/sample_and_disclose/invoice.md` — `#205`
- `docs/phase-3/sample_and_disclose/standard_receipt.md` — `#206`
- `docs/phase-3/sample_and_disclose/credit_memo.md` — `#207`

### Merge SHAs

| PR | Merge commit | Entity |
|---|---|---|
| #203 | `2a23906` | PurchaseOrder (anchor) |
| #204 | `850feb5` | Supplier |
| #205 | `3f3ff11` | Invoice |
| #206 | `5eadf7b` | StandardReceipt |
| #207 | `4d301c4` | CreditMemo |
| #208 | `TBD` | ReceivablesInvoice (PR #6, open) |

Post-merge docs commits: `05d7978` (froze `supplier.md`),
`983a7fb` (handoff to PR #3), `9724282` (resume docs correction),
`5f9b554` (froze `invoice.md`), `e7d31b2` (froze `standard_receipt.md`),
`0c9f3ec` (PR #4 `STATUS.md` advance), `7e786c7` (PR #4 `HANDOFF.md`
advance), `341b9f9` (PR #5 extended prompt set findings), `5ef278c`
(froze `credit_memo.md`).

### What each PR proved

- **PR #203 (PurchaseOrder).** Introduced the bounded sample path
  (`_is_sampleable_po_request` beside `_is_explicit_po_list`),
  `narrowing_tip` on `PurchaseOrderResponse`, and the `labels_map`
  parameter on `build_narrowing_tip`. V-walk found three defects
  the unit tests did not catch (Fix A/B/C in
  `purchase_order.md` §Deviations).
- **PR #204 (Supplier).** Established that Supplier **already
  sampled** on `master`; PR #2 became coverage + one new shape
  (the multi-child builder `build_suppliers_with_children`). V-walk
  found three defects (Fix D-a/D-b/E in `supplier.md` §Deviations).
- **PR #205 (Invoice).** Established that the plain-list Invoice
  path **already samples** on `master`; PR #3 added the
  `narrowing_tip` field, `_INVOICE_FILTER_LABELS`, and a
  sample-only guard (`len(rows) < total_available`) at the
  plain-invoice return. V-walk found one defect (V3c — the tip
  fired on a 1-row complete fetch; fixed at `d7d78c5`).
- **PR #206 (StandardReceipt).** Established that the SCOPED
  StandardReceipt path already samples on `master`; PR #4 added the
  `narrowing_tip` field, `_STANDARD_RECEIPT_FILTER_LABELS` (two
  entries — the KG's entity-level set for this entity), and the
  sample-only guard at the StandardReceipt return. The unscoped case
  stays refused by design (recorded in
  `standard_receipt.md` §Deviations). V-walk found one defect (Fix P
  — the empty-truncated summary narrating the cap as the cause; fixed
  at `3d7f4b6`).
- **PR #207 (CreditMemo).** Established that the plain-list
  CreditMemo path already samples on `master`; PR #5 added the
  `narrowing_tip` field and the guarded kwarg at the CreditMemo
  return. **The tip ships empty by construction on this pod** — the
  CreditMemo entity-level filter set in `kg_entity_filter` is `[]`,
  so `build_narrowing_tip(set(), ...)` returns `""` before it inspects
  `total_available`. The field exists for contract uniformity with
  the four prior entities and seeds the future KG-filter-set PR that
  will make it fire. The extended prompt set (ten prompts) confirmed
  the F-016 `list_limit` extractor works on CreditMemo, the
  `b_credit_memos.sysprompt` aggregation EXCEPTION clause is honoured,
  and the customer-scoped boundary holds across three paraphrases.
  Two out-of-scope findings recorded in `credit_memo.md` §Deviations
  (`capability.py` `_FILTER_GUIDANCE["CreditMemo"]` live; count-path
  pluralisation).
- **PR #208 (ReceivablesInvoice — PR #6, open).** Established that the
  plain-list AR-invoice path does **not** exist on master at `c8580c4`:
  no filter-less fetcher, no `(ReceivablesInvoice, 'none')` KG row, no
  filter-less sysprompt rule, and the planner guard refuses a
  filter-less intent before Block 1. PR #6 is a real wiring PR (the
  second after PR #1): a new fetcher `search_receivables_invoices`, a
  new `kg_entity_tool` row (first KG touch in the sequence), a new
  sysprompt block `b_ar_invoices.sysprompt`, a planner guard relaxation
  for `list_all`, a `narrowing_tip` field on `ReceivablesInvoiceResponse`
  and a **new plain-list branch** in the synthesizer (before
  `single_parent_shape`, which cannot fire on a 25-row sample), a new
  parser helper `_is_filter_less_receivables_invoice_request` that sets
  `list_all=True` when the model has already produced the filter-less
  shape and the prompt carries no by-id-shaped number, and — discovered
  at V9 — a `server.py` registration. **The tip ships empty by
  construction** on this pod (`['by_id']` minus `by_id` is `{}`), same
  shape as PR #5. **V9 required** (first sysprompt change in the
  sequence) and **V9-full discovered to be impossible on this branch**:
  the `--validate` flag the briefs name does not exist on
  `promptkit.py`. V9-scoped ran six prompts and all six are green;
  V9-full is deferred to the MCP migration PR with the tool's absence
  recorded as a queue item. The V-walk surfaced one **wiring defect**
  (`server.py` registration omitted; `Unknown tool` in the V9-scoped
  run) and the write-up records it as the pattern that future PRs in
  the sequence must carry forward: module + registration + KG row land
  together, before V9.

### Next

The seven-PR sequence continues with PR #6 onward — the next entity
from `MEETING_2026-11-10_sample_and_disclose.md` §6,
ReceivablesInvoice. A new window opens the branch from `master` at
`4d301c4` (or its successor). The V0 must be based on a read of
`master`, not on the meeting's row; PR #2's `7b7bb51` correction, PR
#3's `invoice.md` V0, PR #4's `standard_receipt.md` V0 (the unscoped
`get all receipts` case is refused by design), and PR #5's
`credit_memo.md` V0 (the tip ships empty by construction because the
KG has no CreditMemo entity-level filters) all proved that lesson.

**Two carry-forward notes from PR #1/#2/#3/#4/#5:**

- **`personas.yaml`.** Local credential edit. Confirm `git status`
  is clean before staging anything. It does not go into any PR.
- **V-walk is not a rubber stamp.** PR #1 found three defects the
  unit tests did not catch; PR #2 found three; PR #3 found one
  (V3c); PR #4 found one (Fix P — the empty-truncated summary
  narrating the cap as the cause); PR #5 found zero IN-SCOPE defects
  (the tip is empty by construction and never fires), but the
  extended prompt set surfaced two out-of-scope findings
  (`capability.py` `_FILTER_GUIDANCE["CreditMemo"]` live;
  `aggregation.py` count-path pluralisation) — the V-walk is still
  where the real fix set lives. Expect at least one
  V-walk-surfaced fix per PR. The test you write at step 4 is the
  test PR #N *starts* with, not the test it needs.

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

## Queue

Items surfaced during PRs #1–#3 that are not yet scheduled, none
blocking the next window:

1. **`STATUS.md` body migration** — closed (PR #3 by `9724282`;
   PR #4 and PR #5 completed by this commit).
2. **`HANDOFF.md` rewrite** — the sibling docs commit (next cell).
3. **Parser: AP-invoice-lines include** — PR #3's V3a refused
   `show invoices for supplier 1252 and their lines` with
   `Invoice lines for AP invoices are not supported`. A parser-
   sysprompt window can add the include; multi-bucket Invoice
   coverage depends on it.
4. **SQL overlay: Invoice FilterSpecs** — `invoice_date_before`,
   `unpaid` (and likely `overdue`, `pending`) absent from
   `kg_sql_filter`. Same class as the multi-field-iteration
   finding; belongs with the SQL emitter fix window.
5. **MCP migration PR** — V6/V8 of PRs #1, #2, #3 all deferred to
   it. Still unscheduled.
6. **PR #6 onward** — the next entity from the seven-PR sequence,
   ReceivablesInvoice (PR #6, open).
7. **`--validate` tool does not exist.** The briefs' V9 mechanism —
   `promptkit.py --validate` against the full prompt corpus — was never
   implemented on this branch. PRs #1–#5 never surfaced its absence
   because their sysprompts were untouched (`V9: not required`); PR #6
   is the first PR that needs V9 and the first that discovers the
   missing mechanism. V9-scoped (a chosen subset run with
   `--show-parser --show-planner` and inspected for shape) is what
   PR #6 used. Building `--validate` proper is its own tooling PR;
   recorded in `receivables_invoice.md` §V9.


## Pointers

- This PR's evidence: `docs/phase-3/sample_and_disclose/credit_memo.md`
- The seven-PR design: `docs/plan/MEETING_2026-11-10_sample_and_disclose.md` §6
- The V0–V9 standard: `docs/fixes/FIX_PLAN.md` §6
- The working cadence: `docs/plan/WORKING_STYLE.md` §15.3
- Issue B (MCP): `docs/phase-3/sample_and_disclose/MCP_DEPENDENCY_CONFLICT.md`
- Issue C (SQL emitter): finding file at
  `SQL_EMITTER_MULTIFIELD_ITERATION.md` (landed `fe5a41f`); fix is a
  future window's PR
