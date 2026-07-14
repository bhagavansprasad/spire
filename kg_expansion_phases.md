# KG Expansion — Phase Tracker

Live status for the Purchase Orders / Procurement (PO) expansion.
Detailed plan: `docs/po_expansion_plan.md`. Catalog:
`spire_expansion_endpoints.md` (Module 4).

Status vocab: `not started` · `in progress` · `blocked` · `merged`.
Branch convention: `po-phase-N-description`.

---

| Phase | Goal | Branch | Status | PR |
|---|---|---|---|---|
| P1 | Dedupe + discovery scope | `po-phase-1-dedupe` | done (docs-only) | — |
| P2 | PO detail + lines + projection | `po-phase-2-po-lines` | merged | merged to master |
| P3 | PO schedules + distributions | `po-phase-3-schedules-distributions` | not started | — |
| P4 | Supplier contacts | `po-phase-4-supplier-contacts` | not started | — |
| P5 | Receipt requests + invoices-by-PO | `po-phase-5-receipt-requests` | not started | — |
| P6 | PO aggregates | `po-phase-6-aggregates` | not started | — |

---

## Notes / open items

- P1 dedupe result feeds back into the plan — P2–P6 scope may tighten.
- Update this table as each phase moves; keep rows short.
