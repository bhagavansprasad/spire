# SPIRE — window handoff

**Window close:** 2026-11-12 (PR #5 close).
**Tip:** `master` at `4d301c4` (merge commit for PR #207, CreditMemo).
**Branch:** `master` (clean working tree except untracked evidence
files under repo root; `personas.yaml` local-only, never staged).

This file is the resume surface. Per `WORKING_STYLE.md` §1, read it
before any other file when opening a new window.

---

## What is live

Phase 3 (sample-and-disclose) sequence from
`docs/plan/MEETING_2026-11-10_sample_and_disclose.md` §6. The first
five PRs are merged:

| PR | Merge commit | Entity | Evidence file (frozen, `State: closed`) |
|---|---|---|---|
| #203 | `2a23906` | PurchaseOrder (anchor) | `purchase_order.md` |
| #204 | `850feb5` | Supplier | `supplier.md` |
| #205 | `3f3ff11` | Invoice | `invoice.md` |
| #206 | `5eadf7b` | StandardReceipt | `standard_receipt.md` |
| #207 | `4d301c4` | CreditMemo | `credit_memo.md` |

Post-merge docs commits on `master`: `05d7978` (freeze
`supplier.md`), `983a7fb` (handoff to PR #3), `9724282` (resume
docs correction), `5f9b554` (freeze `invoice.md`), `e7d31b2` (freeze
`standard_receipt.md`), `0c9f3ec` (PR #4 `STATUS.md` advance),
`7e786c7` (PR #4 `HANDOFF.md` advance), `341b9f9` (PR #5 extended
prompt set findings), `5ef278c` (freeze `credit_memo.md`),
`d2a689b` (PR #5 `STATUS.md` advance), and this commit (PR #5
`HANDOFF.md` advance).

---

## Resume state — what is next

The next window starts **PR #6** (the sixth entity, ReceivablesInvoice,
from `MEETING_2026-11-10_sample_and_disclose.md` §6) on a fresh branch
off `master` at `4d301c4` or its current successor.

The V0 for PR #6 must be based on a **read of `master`**, not on the
meeting's row. PR #2's V0 correction (`7b7bb51`), PR #3's
`invoice.md` V0, PR #4's `standard_receipt.md` V0 (the unscoped
`get all receipts` case is refused by design), and PR #5's
`credit_memo.md` V0 (the tip ships empty by construction because the
KG has no CreditMemo entity-level filters) all proved that lesson.

**PR #6 scope, established by a read of `master` at `168e48a`:**

- `ReceivablesInvoice`'s entity-level filter set is `['by_id']` — the
  tip ships empty by construction, same shape as PR #5.
- No filter-less AR-invoice fetcher exists: `receivables_invoice_by_id.py`
  is the only fetcher, reached only by `by_id`.
- No parser sysprompt block teaches a filter-less `ReceivablesInvoice`
  shape; every AR-invoice rule names `by_id`, and every customer-scoped
  rule routes to `CustomerAccount`.
- The planner guard on `ReceivablesInvoice` refuses filter-less intents
  before Block 1, and no `kg_entity_tool` row exists for
  `(ReceivablesInvoice, 'none')`.
- **PR #6 is a real wiring PR, not "coverage + one small shape":** new
  tool `search_receivables_invoices`, new KG `kg_entity_tool` row
  (first in the sequence), new `b_ar_invoices.sysprompt` block, planner
  guard relaxation, response field, synthesizer kwarg. **V9 is
  required** (first sysprompt change in the sequence).

### Two carry-forward notes (updated through PR #5)

- **`personas.yaml`.** Local credential edit. Confirm `git status`
  is clean before staging anything. It does not go into any PR.
- **V-walk will surface defects the unit tests do not catch.** PR
  #1 found three (Fix A/B/C in `purchase_order.md` §Deviations).
  PR #2 found three (Fix D-a/D-b/E in `supplier.md` §Deviations).
  PR #3 found one (V3c in `invoice.md` §V3 and §Deviations). PR #4
  found one (Fix P in `standard_receipt.md` §Deviations — the
  empty-truncated summary narrating the cap as the cause). PR #5
  found zero in-scope defects (the tip is empty by construction and
  never fires), but the extended prompt set surfaced two out-of-scope
  findings in `credit_memo.md` (the `capability.py`
  `_FILTER_GUIDANCE["CreditMemo"]` entry and the `aggregation.py`
  count-path pluralisation). Expect at least one per PR. The tests
  you write at step 4 are the tests PR #N **starts** with, not the
  tests it needs.

---

## Open queue (non-blocking)

Surfaced during PRs #1 through PR #5, not yet scheduled:

1. **Parser: AP-invoice-lines include.** PR #3's V3a refused
   `show invoices for supplier 1252 and their lines` with
   `Invoice lines for AP invoices are not supported`. A parser-
   sysprompt window can add the include; multi-bucket Invoice
   coverage depends on it.
2. **SQL overlay: Invoice FilterSpecs.** `invoice_date_before`,
   `unpaid` (and likely `overdue`, `pending`) absent from
   `kg_sql_filter`. Same class as the multi-field-iteration
   finding; belongs with the SQL emitter fix window.
3. **MCP migration PR.** V6/V8 of PRs #1, #2, #3, #4, #5 all deferred
   to it. Still unscheduled.
4. **PR #6 onward** — ReceivablesInvoice, the next entity from the
   seven-PR sequence.

**Two additional items recorded by PR #5's extended prompt set:**

5. **`capability.py` `_FILTER_GUIDANCE["CreditMemo"]` live
   finding.** The refusal for a date-scoped CreditMemo prompt advises
   narrowing by a customer-name filter that does not exist on the
   CreditMemo entity; following the advice routes to `CustomerAccount`.
   Recorded in `credit_memo.md` §Deviations. Separate `capability.py`
   branch.
6. **`aggregation.py` count-path pluralisation.** `how many credit
   memos are there` answers `There are 2261 creditmemos.` — no space,
   no thousands separator. `_build_count_response`'s template is
   `f"...{target_entity.lower()}s."`; correct for `suppliers` /
   `invoices`, wrong for `CreditMemo`. Recorded in `credit_memo.md`
   §Deviations. Separate `aggregation.py` branch.

No `FIX_PLAN.md` rows are touched by any of the above.

---

## Working style pointers

- `docs/plan/WORKING_STYLE.md` — the standing rules. §1 (context
  bundles), §2 (one command at a time), §15.3 (Python script + shell
  verification), §27 (queue report after every closure), Rule 28
  (SME test).
- `docs/fixes/FIX_PLAN.md` §6 (V0–V9 standard) and §8 (per-fix
  workflow: file first, then branch, then failing test, then fix).
- `docs/phase-3/sample_and_disclose/STATUS.md` — the resume surface
  for Phase 3.
- The five evidence files (`purchase_order.md`, `supplier.md`,
  `invoice.md`, `standard_receipt.md`, `credit_memo.md`) — the durable
  record per merged PR.

---

## What this handoff does not carry

Anything before PR #203 is in `master`'s history and in the audit
records (`docs/audit/`, `docs/fixes/`, `docs/phase-2/`). This file
exists to tell a new window where it is now, not where everything
has ever been.

