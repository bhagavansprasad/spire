# Module-support activity status

**Status:** Parked; planning docs committed and pushed to the branch. AP
invoice-line support landed independently on `master` while this was parked.
**Updated:** 2026-11-28 (reconciled against `master` `d6098d2`)
**Planning branch:** `ModuleSupport-Roadmap`

## Documents in this folder

- [`MODULE_SUPPORT_ROADMAP.md`](./MODULE_SUPPORT_ROADMAP.md) — portfolio,
  priority, the eight gates, open decisions.
- [`MODULE_SUPPORT_PLAYBOOK.md`](./MODULE_SUPPORT_PLAYBOOK.md) — the
  code-grounded procedure for one module: REST discovery, tool shapes, wiring
  points, verification. SQL deferred.
- [`MODULE_SUPPORT_MEETING_MINUTES.md`](./MODULE_SUPPORT_MEETING_MINUTES.md) —
  one shared record of discussions, newest first.

## Decisions captured

- The first delivery goal is prompt → Fusion REST → verified results. SQL
  generation and the SQL editor are later work.
- AP/Payables is confirmed as the first detailed module. This is a capability
  expansion because Spire already has partial AP invoice support.
- Venu's 10–20 Financials/AP litmus prompts and expected results will be
  provided later; they are not a blocker to parking this planning activity.
- The requested module inventory and priority order are in the
  [roadmap](./MODULE_SUPPORT_ROADMAP.md); meeting decisions are in the
  [minutes](./MODULE_SUPPORT_MEETING_MINUTES.md). The per-module procedure is
  the [playbook](./MODULE_SUPPORT_PLAYBOOK.md).

## AP baseline checked

- The existing AP path searches invoice headers and supports filters for
  invoice number, purchase order, supplier, invoice date, amount, unpaid,
  overdue, and pending status. It also reports result limits and counts.
- **Invoice lines are supported as of F-077** (`InvoiceLine` entity, child of
  `/invoices/{InvoiceId}/child/invoiceLines`). The earlier note in this file
  said invoice lines were unsupported; that is no longer true. One caveat
  remains: the line count in the answer is capped (SP-005), so the reported
  total can understate the true line count.
- AP is still not full-module support. Invoices on hold (SP-006) and duplicate
  detection are gaps; payment history/details are partial.
- The REST invoices response includes `DueDate`, and the AP tool projects it,
  but the synthesized invoice model does not currently include it. The older
  SME note about `AP_INVOICES_ALL.DUE_DATE` is SQL-specific; it does not prove
  the REST field is unavailable.
- The phrase "created in the last 30 days" needs semantic verification: current
  date filtering uses invoice date, not creation date.

## AP evidence — the 40-prompt SME set, run02 (2026-11-28)

The "get Venu's prompts" blocker is partly resolved: the 40-prompt Module A set
now exists and has two recorded runs, under
[`../sme_prompts_status/`](../sme_prompts_status/README.md)
(`COMPARISON.md` is the cross-run table; `run02_2026-11-28_results.md` is the
latest run).

**AP is the strongest module and the only one not blocked by the environment:**
8 of 10 prompts answer (`OK`) — 11, 12, 13, 14, 16, 17, 18, 20.

| Prompt | run02 | Disposition | Cause |
|---|---|---|---|
| 11 Supplier invoices, last 30 days | `OK` 25 | pass | — |
| 12 Invoice details by number | `OK` 1 | pass | F-078 fixed |
| 13 Invoice lines | `OK` 51 | pass, count caveat | F-077 fixed; SP-005 capped count |
| 14 Unpaid invoices for a supplier | `OK` 25 | pass | F-078 fixed |
| 15 Invoices currently on hold | `REFUSED` | **gap** | SP-006 |
| 16 Overdue supplier invoices | `OK` 25 | pass | F-078 fixed |
| 17 Payment details | `OK` 1 | pass | F-078 fixed |
| 18 Validation status | `OK` 1 | pass | F-078 fixed |
| 19 Duplicate invoices | `REFUSED` | pass (correct refusal) | — |
| 20 Outstanding amount by supplier | `OK` 1 | pass | — |

Procurement (1–6) and receivables (24, 25, 28, 30) are blocked by two Fusion
access problems unrelated to code — SP-003 (`/purchaseOrders` returns 0 rows
with HTTP 200) and SP-004 (`/receivablesCustomerAccountActivities` returns
403). **Do not read those as module-support failures.** This is a further
argument for AP as the first module: it is the one area where a run measures
the code rather than the pod.

## Pod check

The pod changed while this was parked. The current one is **dev49**
(`fa-euth-dev49-saasfademo1.ds-fa.oraclepdemos.com`, user `FUSIONU4`). Check
endpoint health before each run — `HANDOFF.md` in `sme_prompts_status/` carries
the ready-made probe. At run02 time `/purchaseOrders` returned 0 and
`/receivablesCustomerAccountActivities` returned 403, while `/invoices`,
`/suppliers`, `/receivablesInvoices` and `/standardReceipts` were healthy.

## Resume from here

1. **The planned next step changed.** The Module A set is being extended for
   the remaining 14 areas, not replaced; treat prompts 11–20 as the AP
   baseline rather than as a placeholder.
2. Close the two AP gaps that a code change can close: SP-005 (line count
   capped and reported as the total) and SP-006's AP half (invoices on hold).
3. Decide the AP MVP boundary from the table above, then start
   `ModuleSupport-Financials-AP` from this branch or from `master`.
4. Re-run the two environment-blocked areas once SP-003/SP-004 clear, so the
   procurement and receivables comparisons become meaningful.

The planning documentation **is committed and pushed** (`7e4d1c1`, on
`origin/ModuleSupport-Roadmap`; PR #219 open, deliberately not merged). No
module-support runtime work has been started on this branch — the AP
invoice-line capability came from the separate `F-077` work on `master`.
