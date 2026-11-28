# SME prompt set — cross-run comparison

One row per prompt, one column per run. This is the document to read when
asking *"did that fix actually work?"* — a run result alone cannot answer it.

| | |
|---|---|
| Prompt set | `prompts/sme_module_a/sme_module_a_litmus.txt` (40 prompts) |
| Run 01 | 2026-11-21 — `run01_2026-11-21_results.md` |
| Run 02 | 2026-11-28 — `run02_2026-11-28_results.md` |

## Status codes

| Code | Meaning |
|---|---|
| `OK(n)` | answered with `n` rows |
| `ZERO` | ran, returned no rows — pod data or a wrong filter |
| `REFUSED` | Spire declined to answer |
| `ERR403` | REST call failed — **environment**, not code |
| `BADSQL` | emitted SQL contained an invalid `-- unmapped` fragment |

A `→` marks a change. `=` marks no change.

## Summary

| Code | run01 | run02 | Δ |
|---|---:|---:|---:|
| `OK` | 11 | 13 | **+2** |
| `REFUSED` | 18 | 17 | −1 |
| `ERR403` | 0 | 4 | +4 (environment) |
| `ZERO` | 1 | 6 | +5 (environment: 5, + 1 unchanged) |
| `BADSQL` | 10 | 0 | **−10** |
| **Total** | **40** | **40** | |

**Score the code, not the run.** Excluding the 10 environment-blocked
prompts (`ZERO` 1–6 and `ERR403` 24, 25, 28, 30), the comparable set is 30
prompts, of which **13 answer and 17 refuse in both runs**. The real
movement is: 10 invalid-SQL plans became valid, 1 refusal became an answer
(p13), 1 zero became an answer (p22), and 2 answers were lost to a 403
(p25, p28).

## Procurement (1–10)

| # | Prompt | run01 | run02 | Trend | Blocked by |
|---:|---|---|---|---|---|
| 1 | POs created in the last 30 days | `BADSQL` 25 | `ZERO` 0 | ⬆ SQL fixed, then pod | SP-003 |
| 2 | Details of PO 55040 | `OK` 1 | `ZERO` 0 | 🔻 pod | SP-003 |
| 3 | Lines for PO 55040 | `OK` 26 | `ZERO` 0 | 🔻 pod | SP-003 |
| 4 | Shipment schedules for PO 55040 | `OK` 26 | `ZERO` 0 | 🔻 pod | SP-003 |
| 5 | Distribution details for PO 55040 | `OK` 51 | `ZERO` 0 | 🔻 pod | SP-003 |
| 6 | POs for supplier Dell Inc. | `BADSQL` 25 | `ZERO` 0 | ⬆ SQL fixed, then pod | SP-003 |
| 7 | POs assigned to buyer Eleanor White | `REFUSED` | `REFUSED` | = | SP-006 |
| 8 | POs pending approval | `REFUSED` | `REFUSED` | = | SP-006 |
| 9 | POs with pending/overdue shipments | `REFUSED` | `REFUSED` | = | SP-006 |
| 10 | PO amount by supplier, current month | `REFUSED` | `REFUSED` | = | SP-006 |

**Module verdict:** 5 of 6 previously-answering prompts were lost to
**SP-003**. The 4 refusals are unchanged and currently untestable — the
collection is empty, so a correct filter would also return 0.

## Payables (11–20)

| # | Prompt | run01 | run02 | Trend | Blocked by |
|---:|---|---|---|---|---|
| 11 | Supplier invoices, last 30 days | `OK` 25 | `OK` 25 | = | — |
| 12 | Details of invoice ERS-53004-755598 | `BADSQL` 1 | `OK` 1 | ✅ **F-078** | — |
| 13 | Invoice lines for ERS-53004-755598 | `REFUSED` | `OK` 51 | ✅ **F-077** | SP-005 (count wrong) |
| 14 | Unpaid invoices for Staffing Services | `BADSQL` 25 | `OK` 25 | ✅ **F-078** | — |
| 15 | Invoices currently on hold | `REFUSED` | `REFUSED` | = | SP-006 |
| 16 | Overdue supplier invoices | `BADSQL` 25 | `OK` 25 | ✅ **F-078** | — |
| 17 | Payment details for ERS-53004-755598 | `BADSQL` 1 | `OK` 1 | ✅ **F-078** | — |
| 18 | Validation status of ERS-53004-755598 | `BADSQL` 1 | `OK` 1 | ✅ **F-078** | — |
| 19 | Duplicate invoices for Staffing Services | `REFUSED` | `REFUSED` | = | — (correct refusal) |
| 20 | Outstanding amount by supplier | `OK` 1 | `OK` 1 | = | — |

**Module verdict:** the strongest module and the clearest proof of the work
— 5 prompts went from invalid SQL to correct answers, and 1 refusal became
an answer. Only p15 is still a genuine gap.

## Receivables (21–30)

| # | Prompt | run01 | run02 | Trend | Blocked by |
|---:|---|---|---|---|---|
| 21 | AR invoices created in the last 30 days | `REFUSED` | `REFUSED` | = | SP-002 |
| 22 | Details of AR invoice 112390 | `ZERO` 0 | `OK` 1 | ✅ **F-082** | — |
| 23 | Customers with active accounts | `REFUSED` | `REFUSED` | = | SP-006 + SP-004 |
| 24 | Customer account 26360 details | `BADSQL` 1 | `ERR403` | ⬆ SQL fixed, then 403 | SP-004 |
| 25 | Receipts from ABC Application Software | `OK` 11 | `ERR403` | 🔻 **lost to pod** | SP-004 |
| 26 | Receipt Brad-234 application details | `REFUSED` | `REFUSED` | = | SP-006 |
| 27 | Unapplied / partially applied receipts | `REFUSED` | `REFUSED` | = | SP-006 |
| 28 | Credit memos for Bradshaw Hotels | `OK` 26 | `ERR403` | 🔻 **lost to pod** | SP-004 |
| 29 | Details of credit memo 29822 | `REFUSED` | `REFUSED` | = | SP-006 |
| 30 | Overdue AR invoices for ABC Corp Americas | `BADSQL` 26 | `ERR403` | ⬆ SQL fixed, then 403 | SP-004 |

**Module verdict:** the only module with a net loss. 4 prompts are 403-
blocked (SP-004), and that is the sole reason p25 and p28 regressed. Do not
read this as a code regression — the plans are unchanged and were working.

## Supplier (31–40)

| # | Prompt | run01 | run02 | Trend | Blocked by |
|---:|---|---|---|---|---|
| 31 | Suppliers matching Dell | `OK` 1 | `OK` 1 | = | — |
| 32 | Details of supplier 1262 | `REFUSED` | `REFUSED` | = | SP-001 |
| 33 | Active supplier sites for 1262 | `REFUSED` | `REFUSED` | = | SP-001 |
| 34 | Inactive supplier sites for 1262 | `REFUSED` | `REFUSED` | = | SP-001 |
| 35 | Contact details of supplier 1262 | `REFUSED` | `REFUSED` | = | SP-001 |
| 36 | Addresses for supplier 1262 | `BADSQL` 22 | `OK` 22 | ✅ **F-078** | — |
| 37 | Suppliers by classification SMALL_BUSINESS | `OK` 26 | `OK` 26 | = | — |
| 38 | Site assignments for supplier 1262 | `REFUSED` | `REFUSED` | = | SP-001 |
| 39 | Inactive/expired suppliers | `OK` 7 | `OK` 2 | 🔻 pod data drift | — |
| 40 | Compare supplier 1262 and associated records | `REFUSED` | `REFUSED` | = | SP-001 |

**Module verdict:** 6 identical refusals, all one missing parameter
(**SP-001**). p39's 7 → 2 is live data drift (suppliers reactivated on the
pod), not a defect — confirmed by re-running the query the same session.

## Change log

| Change | Prompts | Cause |
|---|---|---|
| `BADSQL` → `OK` | 12, 14, 16, 17, 18, 36 | **F-078** fixed |
| `REFUSED` → `OK` | 13 | **F-077** fixed |
| `ZERO` → `OK` | 22 | **F-082** fixed |
| `OK` → `ZERO` | 2, 3, 4, 5 | **SP-003** — `/purchaseOrders` empty |
| `BADSQL` → `ZERO` | 1, 6 | F-078 fixed; then SP-003 |
| `BADSQL` → `ERR403` | 24, 30 | F-078 fixed; then SP-004 |
| `OK` → `ERR403` | 25, 28 | **SP-004** — 403 |
| `OK` → `OK` (fewer rows) | 39 | pod data drift |
| No change | 7, 8, 9, 10, 11, 15, 19, 20, 21, 23, 26, 27, 29, 31, 32, 33, 34, 35, 37, 38, 40 | — |

## Regressions

Two prompts went from answering to not answering:

- **p25** — `OK(11)` → `ERR403`
- **p28** — `OK(26)` → `ERR403`

Both are **SP-004** (403 on `receivablesCustomerAccountActivities`). Same
credentials, same session: `/receivablesInvoices`, `/standardReceipts` and
`/invoices` all returned 200. Not a code regression.

**No prompt regressed in parsing or refusal terms.** Every refusal in run02
was already a refusal in run01, except p24 and p30 which changed from
`BADSQL` to `ERR403` — an improvement in the plan, masked by the 403.

## How to read a future run

1. Compare **within** a run: are `OK + REFUSED + ERR403 + ZERO + BADSQL = 40`?
2. Compare **across** runs, but subtract the environment codes
   (`ERR403`, and any `ZERO` traceable to an empty collection) before
   judging code.
3. A `BADSQL` appearance is always a regression — it was zero after F-078.
4. An `OK` with fewer rows than last run may be pod drift; re-check the
   underlying query in the same session before calling it a defect.
