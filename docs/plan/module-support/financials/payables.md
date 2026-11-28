# Payables (AP)

**Family:** Financials · **Routable module id:** `payables` ·
**Prompts:** Module A 11–20 · **Evidence:** run02 (2026-11-28)

The first detailed module. AP is not greenfield: Spire already answers 8 of its
10 litmus prompts, so this is a **capability expansion with a measured
boundary**, not a new module.

## Sub-modules

Every sub-module is a row here. A sub-module leaves this file only when it
needs its own branch and its own record.

| Sub | Scope | Prompts | State | Note |
|---|---|---|---:|---|
| AP.1 | Supplier invoices — list, date window, supplier, amount, unpaid, overdue, pending, by-id | 11, 12, 14, 16 | `verified` with open defects | AP-1/AP-4/AP-6 below |
| AP.2 | Invoice lines (`InvoiceLine`, child `/invoices/{id}/child/invoiceLines`) | 13 | `verified` — **count is wrong** | SP-005; fixed on `SP-005-line-count` |
| AP.3 | Holds | 15 | `blocked` — wording decision | holds are not on the invoice header |
| AP.4 | Outstanding and paid amounts | 20, 14 (partial) | `boundary agreed` | D-PAY-002 |
| AP.5 | Validation and accounting status | 18 | `modelled` | `ValidationStatus` / `FundsStatus` are on the header |
| AP.6 | Payment documents | 17 | `accepted refusal` | D-PAY-003 |
| AP.7 | Duplicate detection | 19 | `accepted refusal` | needs cross-record logic; correct since run01 |

## MVP boundary (gate 3)

**In:** the `Invoice` entity and its `InvoiceLine` child; filters already
backed by a tool argument (invoice number, supplier, invoice-date window,
amount range, unpaid, overdue, pending, purchase-order number); the
by-supplier aggregation; truthful counts and truncation; explicit refusals for
the three gaps.

**Out of v1:** any new root entity; holds answered across the whole
collection; payment documents; SQL overlay and KG SQL rows (Track B, deferred).

**Acceptance shape (roadmap §5.4):** every in-scope prompt either passes its
declared disposition or is an explicitly accepted refusal with a decision id.
No answer may state a count it cannot support.

## Decisions

Append-only. Overturned decisions get `superseded by D-PAY-NNN`, never an
edit.

**D-PAY-001 — a bare "status" resolves to `PaidStatus`; render both status
columns.**
Why: `kg_entity_field` declares `PaidStatus` and `ApprovalStatus`, `tools/
invoices.py` fetches both, and `InvoiceRecord` carries neither — so the value
is fetched and dropped. Only `b_invoice_status.sysprompt` teaches a status
reading, and only for "pending" → `ApprovalStatus`. A bare "status" has no
teaching block, and the p11/p14 readers mean paid/unpaid.
Constrains: `PaidStatus` is a *status*, never a money figure — a partly paid
invoice is not in Paid status, so money comes from the header's `AmountPaid`.
Accepted 2026-11-28.

**D-PAY-002 — "outstanding by supplier" is answered, not refused.**
Why: the SME test. An SME can answer "outstanding amount by supplier this
month", so a refusal is a defect, not a boundary. `AmountPaid` is on the
invoice header and `po_lifecycle._summarise_invoices` already sums it; only
the AP aggregation does not use it.
Shape: a measure over header `AmountPaid` (never over `invoiceInstallments`,
which are context and capped), with the period emitted by the parser and a
truncation disclosure plus a "narrow the filters" hint when the scan is
sampled. One-op-one-tool: this is a new tool, not a flag on the spend
aggregation.
Accepted 2026-11-28; tool name and registry entries settled at gate 5.

**D-PAY-003 — payment documents stay refused; the refusal is named.**
Why: no payment number, payment date or payments child exists anywhere on the
AP REST path — an absence, not an undiscovered endpoint. An SME can still see
payments in the Fusion UI, so this is a REST-coverage boundary and is recorded
as a product gap, not a completed capability.
Constrains: p17 must refuse in the structured shape that names the absence.
Today it answers `OK(1)` with "(1 record(s) matched; no requested column was
available.)", which reads like a hit.
Accepted 2026-11-28.

**D-PAY-004 — the line-count defect is its own branch.**
Why: the same copied bug sits in five tools across payables, procurement and
receivables. Inside the AP branch, a PR called "AP module support" would edit
two other modules and stop being readable as the AP boundary.
Branch: `SP-005-line-count` off `master`, merged before AP work starts.
Accepted 2026-11-28.

**D-PAY-005 — AP implementation is `ModuleSupport-Financials-AP` off
`master`.**
Why: the AP boundary is defined by planning docs on `ModuleSupport-Roadmap`
(PR #219). Branching off master after SP-005 lands keeps the code PR free of
planning churn and of the shared line-count fix.
Accepted 2026-11-28.

## Coverage (run02, 2026-11-28)

| # | Prompt | Disposition | Observed | Verdict |
|---:|---|---|---|---|
| 11 | Supplier invoices, last 30 days | PASS | `OK` 25 | pass — refuses `DueDate` and supplier name, both fetched |
| 12 | Invoice details incl. due date | PARTIAL | `OK` 1 | pass by disclosure — declines a field the pod returned |
| 13 | Invoice lines | (stale GAP) | `OK` 51 | **FAIL** — states 50 lines; the invoice has 184 |
| 14 | Unpaid invoices for a supplier | PARTIAL | `OK` 25 | pass — declines due date and remaining balance |
| 15 | Invoices on hold | GAP | `REFUSED` | correct refusal, capability is reachable |
| 16 | Overdue supplier invoices | PARTIAL | `OK` 25 | pass — discloses "all 25 have InvoiceAmount 0" |
| 17 | Payment details | GAP | `OK` 1 | pass by disclosure; the shape is wrong (D-PAY-003) |
| 18 | Validation / accounting status | PARTIAL | `OK` 1 | pass by disclosure |
| 19 | Duplicate invoices | PARTIAL | `REFUSED` | correct refusal |
| 20 | Outstanding by supplier, current month | PASS | `OK` 1 | **FAIL** — answers spend, all time |

Detail and quoted evidence: `../AP_COVERAGE_ASSESSMENT.md` (frozen, run02).

## Known gaps and open defects

| Id | Defect | Effect | Fix |
|---|---|---|---|
| AP-1 | `kg_entity_field` is narrower than the tool projection: no `DueDate`, no `Supplier`; no `supplier name` synonym; `InvoiceRecord` has no `due_date` and no status fields | asks for a fetched column and is refused | KG rows + synonym + record fields |
| AP-2 | p20 substitutes spend for outstanding and drops the period | confident wrong answer | D-PAY-002 + parser period |
| AP-3 | line count is a page size, stated as a total | confident wrong number | `SP-005-line-count` |
| AP-4 | the overdue set is dominated by zero-amount invoices | answer is honest but useless | product decision; disclose until then |
| AP-5 | litmus annotations are stale: p13 still says GAP though F-077 closed it, and the due-date notes are SQL-only (`ORA-00904`) | the prompt ledger describes a different system | re-annotate the disposition comments only — **not yet approved** |
| AP-6 | "created" is read as invoice date, silently | low severity | disclose the field used |

## Open decisions

| # | Question | Blocks |
|---:|---|---|
| 1 | p15 wording: rework as "holds on invoice X / for supplier Y", or keep the whole-collection question as an accepted refusal? Holds live on `/child/invoiceInstallments`, so a collection-wide answer means one call per invoice across 53k invoices | AP.3 |
| 2 | Approve the AP-5 litmus re-annotation (comments only, prompts byte-identical) | the prompt ledger |
| 3 | AP-4: should overdue exclude zero-amount invoices by default? | AP.1 |
| 4 | Move `AP_COVERAGE_ASSESSMENT.md` into this file's evidence trail once PR #219 resolves | doc layout |

## Next

1. `SP-005-line-count` off `master` (D-PAY-004).
2. `ModuleSupport-Financials-AP` off the new master (D-PAY-005): AP-1, AP.2
   count display, AP.4, AP.5, AP.6 refusal shape, AP-6 disclosure.
3. Re-run prompts 11–20 and record run03.
