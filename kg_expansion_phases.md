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
| P3 | PO schedules (flat endpoint, one-hop) | `po-phase-3-schedules` | merged | merged to master |
| P3b | PO distributions (multi-field iteration) | `po-phase-3b-distributions` | merged | merged to master |
| P4 | Supplier contacts | `po-phase-4-supplier-contacts` | merged | merged to master |
| P5 | Received-vs-ordered + invoices-by-PO | `po-phase-5-received-invoices-by-po` | in progress | — |
| P5b | Synthesizer: narrate child entities | `po-phase-5b-synthesizer` | merged | merged to master |
| P6 | PO aggregates | `po-phase-6-aggregates` | not started | — |

---

## Notes / open items

- P1 dedupe result feeds back into the plan — P2–P6 scope may tighten.
- P3 was split: schedules (flat `/purchaseOrderSchedules` endpoint, a clean
  one-hop fetch by POHeaderId) shipped as P3. Distributions became P3b
  because they have no flat endpoint — only the deep nested path, needing
  three ids per parent row (POHeaderId, POLineId, LineLocationId). That
  required multi-field iteration, which P3b added to the executor and
  planner as an additive branch. Both are merged.
- P5b (synthesizer) is sequenced BEFORE P6. Every phase since P2 fetches
  child data correctly but the synthesized prose ignores it — lines,
  schedules, contacts, distributions and received-vs-ordered are all in the
  outputs yet absent from the answer. Several catalog prompts (2, 3, 4, 10,
  14) are therefore data-complete but answer-incomplete. P6's value is
  entirely prose, so the synthesizer is fixed first.
- **Known test failures (not bugs).** Three supplier tests assert
  `truncated is False` on an empty result and fail on pods with more
  suppliers than OVERFETCH_LIMIT (500): `search_suppliers` over-fetches,
  examines 500, finds no match, and honestly reports truncated=True
  ("there may be more I didn't examine"). The code is correct; the tests
  encode a data-volume assumption that held on esll-dev37 and doesn't on
  eqjz. Fixing them properly is part of the deferred test-portability work
  — do not "fix" by weakening the assertion or raising the cap.
- Keep rows short; update status as each phase moves.
