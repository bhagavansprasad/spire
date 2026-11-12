# SPIRE — window handoff

**Window close:** 2026-11-12 (PR #3 close).
**Tip:** `master` at `5f9b554` (freeze of `invoice.md` for PR #3).
**Branch:** `master` (clean working tree except untracked evidence
files under repo root; `personas.yaml` local-only, never staged).

This file is the resume surface. Per `WORKING_STYLE.md` §1, read it
before any other file when opening a new window.

---

## What is live

Phase 3 (sample-and-disclose) sequence from
`docs/plan/MEETING_2026-11-10_sample_and_disclose.md` §6. The first
three PRs are merged:

| PR | Merge commit | Entity | Evidence file (frozen, `State: closed`) |
|---|---|---|---|
| #203 | `2a23906` | PurchaseOrder (anchor) | `purchase_order.md` |
| #204 | `850feb5` | Supplier | `supplier.md` |
| #205 | `3f3ff11` | Invoice | `invoice.md` |

Post-merge docs commits on `master`: `05d7978` (freeze
`supplier.md`), `983a7fb` (handoff to PR #3), `9724282` (resume
docs correction), `5f9b554` (freeze `invoice.md`).

---

## Resume state — what is next

The next window starts **PR #4** (the fourth entity from
`MEETING_2026-11-10_sample_and_disclose.md` §6) on a fresh branch
off `master` at `5f9b554` or its current successor.

The V0 for PR #4 must be based on a **read of `master`**, not on the
meeting's row. PR #2's V0 correction (`7b7bb51`) and PR #3's
`invoice.md` V0 both established this: the meeting describes what
the meeting said; master's code is what the PR must react to.

### Two carry-forward notes

- **`personas.yaml`.** Local credential edit. Confirm `git status`
  is clean before staging anything. It does not go into any PR.
- **V-walk will surface defects the unit tests do not catch.** PR
  #1 found three (Fix A/B/C in `purchase_order.md` §Deviations).
  PR #2 found three (Fix D-a/D-b/E in `supplier.md` §Deviations).
  PR #3 found one (V3c in `invoice.md` §V3 and §Deviations). Expect
  at least one per PR. The tests you write at step 4 are the tests
  PR #N **starts** with, not the tests it needs.

---

## Open queue (non-blocking)

Surfaced during PRs #1–#3, not yet scheduled:

1. **Parser: AP-invoice-lines include.** PR #3's V3a refused
   `show invoices for supplier 1252 and their lines` with
   `Invoice lines for AP invoices are not supported`. A parser-
   sysprompt window can add the include; multi-bucket Invoice
   coverage depends on it.
2. **SQL overlay: Invoice FilterSpecs.** `invoice_date_before`,
   `unpaid` (and likely `overdue`, `pending`) absent from
   `kg_sql_filter`. Same class as the multi-field-iteration
   finding; belongs with the SQL emitter fix window.
3. **MCP migration PR.** V6/V8 of PRs #1, #2, #3 all deferred to it.
   Still unscheduled.
4. **PR #4 onward** — next entity from the seven-PR sequence.

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
- The three evidence files (`purchase_order.md`, `supplier.md`,
  `invoice.md`) — the durable record per merged PR.

---

## What this handoff does not carry

Anything before PR #203 is in `master`'s history and in the audit
records (`docs/audit/`, `docs/fixes/`, `docs/phase-2/`). This file
exists to tell a new window where it is now, not where everything
has ever been.

---

*End of window handoff.*
