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
| P3 | PO schedules (flat endpoint, one-hop) | `po-phase-3-schedules` | not started | — |
| P3b | PO distributions (needs multi-field iteration) | `po-phase-3b-distributions` | blocked | — |
| P4 | Supplier contacts | `po-phase-4-supplier-contacts` | not started | — |
| P5 | Receipt requests + invoices-by-PO | `po-phase-5-receipt-requests` | not started | — |
| P6 | PO aggregates | `po-phase-6-aggregates` | not started | — |

---

## Notes / open items

- P1 dedupe result feeds back into the plan — P2–P6 scope may tighten.
- P3 was split: schedules (flat `/purchaseOrderSchedules` endpoint, a clean
  one-hop fetch by POHeaderId) ships as P3. Distributions became P3b because
  it has no flat endpoint — it lives only on the deep nested path and needs
  three ids per parent row (POHeaderId, POLineId, LineLocationId). Iterating
  it over schedules requires multi-field iteration, which Block 3 does not
  yet support (it threads one `$iteration_value` per parent). P3b is blocked
  on that planner enhancement.
- Keep rows short; update status as each phase moves.
