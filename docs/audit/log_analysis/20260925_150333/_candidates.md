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
- status: candidate, not reproduced outside batch, S0-S8 not yet walked

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
- status: observation, needs mechanism confirmation


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
- status: candidate, not reproduced outside batch, S0-S8 not yet walked


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
- resolution: see findings/F-052.md
