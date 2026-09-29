# 20260925_150333 smoke - candidate findings

One entry per candidate. Stable ID. Class is one of:
pass | fail | wrong-but-no-error | regression.

Do not log to the findings log from this window.

---

## C-001

- file:   payables/smoke.log
- prompt: invoices in the last 30 days
- class:  wrong-but-no-error
- note:   Plan is search_invoices(invoice_date_after='2026-08-25') with no
          upper bound. Future-dated invoices dated 2026-10-01 through
          2027-02-01 appear in a "last 30 days" window without
          qualification.
- status: promoted to F-054 (closed-as-not-a-bug, latent-shape;
          S0-S11 walked 2026-09-27)
- resolution: see docs/audit/findings/F-054.md

---

## C-002

- file:   batch-level
- prompt: n/a
- class:  observation
- note:   The three exit-1 sets all have a refusal as the final prompt.
          The five exit-0 sets that also contain refusals have a
          non-refusal as the final prompt. F-052 explains the exit-1
          case; the exit-0 case with earlier refusals is a separate
          observation and needs its own mechanism.
- status: observation — not promoted to F-NNN. S1 fails: no user-facing
          harm named. The behaviour is: exit code reflects the FINAL
          prompt's state; the F-052 exit-code mechanism documented in
          log_analysis/_plan.md explains the observed exit-1 sets. A set
          whose refusal is non-final exits 0, which is correct — the
          refusal is a valid answer, not a failure.
- resolution: attached as a clarifying note to the exit-code mechanism
              in log_analysis/_plan.md. No new F-NNN.


---

## C-003

- file:   procurement_supplier/smoke.log
- prompt: suppliers with open purchase orders
- class:  wrong-but-no-error
- note:   Plan step 1 returns the first 25 suppliers unfiltered. Step 2
          searches open POs per supplier but does not set
          `filter_source_when_nonempty`. Answer lists all 25 suppliers,
          including nine with Open POs = 0, in response to a prompt that
          asks for suppliers with open POs.
- related: F-010 (filtered count over the matched bucket). The same
          "suppliers with X" shape in payables_supplier sets
          `filter_source_when_nonempty: True`; here it does not.
- status: promoted to F-053 (confirmed, S0-S11 walked 2026-09-27)
- resolution: see docs/audit/findings/F-053.md


---

## C-004

- file:   columns/smoke.log
- prompt: List active suppliers with supplier name, supplier number, and address
- class:  fail
- note:   Parser produced no target_entity after one retry. Refusal
          classified as unparseable. Same shape as columns prompt 1
          (which passed) plus address include. The similar prompt
          "Suppliers with their addresses" in truncation/smoke succeeded,
          so the failure is specific to this combination of list + explicit
          fields + address.
- related: F-001 (list_all flag on explicit list). F-001 adjacent.
- status: promoted to F-052 (confirmed, S0-S11 walked 2026-09-27)
- resolution: see docs/audit/findings/F-052.md


<!-- BEGIN RESOLUTIONS -->

- C-001 -> F-054 (promoted 2026-09-27, closed-as-not-a-bug latent)
- C-002 -> observation (no F-NNN; attached to the exit-code mechanism)
- C-003 -> F-053 (promoted 2026-09-27, confirmed)
- C-004 -> F-052 (promoted 2026-09-27, closed-as-not-a-bug)

<!-- END RESOLUTIONS -->


## Corrections

Appended 2026-09-28, on the generalization branch. Two historical
slips, recorded not rewritten.

- Earlier status lines read `S0-S8`. The standard was R + S0-S11
  before this round closed; `S0-S8` predates R's addition and is
  the wording of an earlier draft. The status lines above now
  carry the current standard.
- C-002's note cites `F-052` as explaining the exit-1 case. F-052
  is the columns-list finding, unrelated. The mechanism that
  explains the exit-1 sets is the `exit-code-on-final-refusal`
  entry in `docs/audit/log_analysis/_plan.md`. C-002's resolution
  line names it correctly; the note's reference is wrong.
