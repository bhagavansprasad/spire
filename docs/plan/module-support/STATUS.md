# Module-support activity status

**Status:** Parked while other work proceeds.
**Updated:** 2026-11-26
**Planning branch:** `ModuleSupport-Roadmap`

## Decisions captured

- The first delivery goal is prompt → Fusion REST → verified results. SQL
  generation and the SQL editor are later work.
- AP/Payables is confirmed as the first detailed module. This is a capability
  expansion because Spire already has partial AP invoice support.
- Venu's 10–20 Financials/AP litmus prompts and expected results will be
  provided later; they are not a blocker to parking this planning activity.
- The requested module inventory and priority order are in the
  [roadmap](./MODULE_SUPPORT_ROADMAP.md); meeting decisions are in the
  [minutes](./MODULE_SUPPORT_MEETING_MINUTES.md).

## AP baseline checked

- The existing AP path searches invoice headers and supports filters for
  invoice number, purchase order, supplier, invoice date, amount, unpaid,
  overdue, and pending status. It also reports result limits and counts.
- AP is not full-module support. Invoice lines, holds, payment history/details,
  and duplicate detection are not fully supported. Validation and accounting
  fields are not surfaced in the synthesized invoice output.
- The REST invoices response includes `DueDate`, and the AP tool projects it,
  but the synthesized invoice model does not currently include it. The older
  SME note about `AP_INVOICES_ALL.DUE_DATE` is SQL-specific; it does not prove
  the REST field is unavailable.
- The phrase "created in the last 30 days" needs semantic verification: current
  date filtering uses invoice date, not creation date.

## Pod check

After the pod configuration was updated, bounded read-only requests to
`/invoices?limit=1` and `/suppliers?limit=1` both succeeded on 2026-11-26.
Only the AP response shape and field names were inspected; no invoice values
were inspected. This confirms connectivity, not end-to-end AP coverage.

## Resume from here

1. Get Venu's Financials/AP litmus prompts and expected results.
2. Mark each prompt pass, partial, or gap against current Spire behavior;
   verify date and due-date semantics against the authorized pod.
3. Agree the AP MVP boundary, expected results, and tests.
4. After the roadmap is reviewed and merged, start the AP implementation on
   `ModuleSupport-Financials-AP` from the updated `master`.

The planning documentation is not yet committed. No module runtime
implementation has started.
