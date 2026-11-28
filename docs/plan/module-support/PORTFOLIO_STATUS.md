# Module support — portfolio status

**One row per module and sub-module.** This is the only place live module
state is recorded. Updated in the same commit as the work it describes, never
from memory.

**Updated:** 2026-11-28 (first issue)

## States

A state names the last gate closed (roadmap §4). No other vocabulary.

| State | Gate | Means |
|---|---:|---|
| `not started` | — | no discovery |
| `discovered` | 1 | endpoints, fields, counts captured |
| `prompts collected` | 2 | scored prompt set exists |
| `boundary agreed` | 3 | MVP in/out written down |
| `modelled` | 4–5 | prompt→endpoint→field mapping and Spire design agreed |
| `implemented` | 6 | reaches REST end to end |
| `verified` | 7 | executed results checked against REST |
| `released` | 8 | merged to `master` |

Three further values, each of which **must name its reason**, and a decision id
once the module has a `DECISIONS.md`: `blocked` (naming who unblocks),
`accepted refusal`, `out of scope`.

## Financials — Payables (AP), first detailed module

Module file: [`financials/payables.md`](./financials/payables.md) — sub-module
rows, boundary, decisions, coverage, open defects.
Evidence: `AP_COVERAGE_ASSESSMENT.md` (run02, 2026-11-28).

| Sub | Scope | Prompts | State | Branch / blocker |
|---|---|---|---:|---|
| AP.1 | Supplier invoices — list, date window, supplier, amount, unpaid, overdue, pending, by-id | 11, 12, 14, 16 | `verified` with open defects | AP-1 field vocabulary narrower than the tool projection; AP-4 zero-amount overdue; AP-6 "created" disclosure |
| AP.2 | Invoice lines | 13 | `verified` — count is wrong | `SP-005-line-count` (the count is a page size, not a total) |
| AP.3 | Holds | 15 | `blocked` | holds live on `/child/invoiceInstallments`, not the invoice header; p15 wording is an **open decision** |
| AP.4 | Outstanding and paid amounts | 20, 14 (partial) | `boundary agreed` | header `AmountPaid` is the only usable paid figure; installments are context, never money |
| AP.5 | Validation and accounting status | 18 | `modelled` | `ValidationStatus` / `FundsStatus` on the invoice header |
| AP.6 | Payment documents | 17 | `accepted refusal` | no payment document exists anywhere on the AP REST path — an absence, not an undiscovered endpoint |
| AP.7 | Duplicate detection | 19 | `accepted refusal` | needs cross-record logic; refusal unchanged since run01 and correct |

## Other modules

| Module | State | Note |
|---|---|---|
| Procurement (PO) | `discovered` | `/purchaseOrders` returns 0 rows with HTTP 200 — SP-003, not code |
| Receivables (AR) | `discovered` | SP-004 (403) blocks 4 prompts; SP-002 blocks 1 |
| Supplier | `prompts collected` | [`financials/supplier.md`](./financials/supplier.md); SP-001 blocks 6 prompts with one missing parameter |
| GL, CM (Cash Management), FA, SLA, OM, INV, WIP, BOM, Cost Management | `not started` | roadmap §2; confirm `CM` = Cash Management with the product owner |
| HCM — Global HR, Payroll, Absence, Benefits, OTL, ORC | `not started` | HCM is not a routed module today |

## Cross-module open items that move this table

| Id | Effect |
|---|---|
| SP-005 | AP.2, plus the PO and AR line sub-modules — the same copied bug sits in five tools |
| SP-003, SP-004 | block the procurement and receivables rows entirely; **environment, not code** |
| PR #219 | planning docs only; `STATUS.md` retirement is gated on it |
