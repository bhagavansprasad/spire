# PO Expansion — Phased Plan

Stable plan for adding Oracle Fusion Purchase Orders / Procurement endpoints
to Spire. Source catalog: `spire_expansion_endpoints.md` (Module 4, PO).
Live status is tracked separately in `kg_expansion_phases.md`.

---

## Why this is phased the way it is

The PO catalog lists 25 prompts, but PO **overlaps Spire's existing coverage**
(`/purchaseOrders`, `/suppliers` + children, `/invoices`, buyer). The catalog
itself flags "dedupe before building." So the genuinely new surface is
narrower than 25 prompts suggests:

- **New:** PO child hierarchy (lines → schedules → distributions), supplier
  contacts, `/receivingReceiptRequests`, and PO projection/aggregate prompts.
- **Already integrated:** base `/purchaseOrders`, `/suppliers` (+ sites,
  classifications, addresses), `/invoices`, buyer.

Phases run in dependency order so each builds on the last.

Every phase follows the proven build sequence (Phases 12–13):
live curl discovery → standalone tool → KG rows (rebuilt from scratch) →
planner edits → parser line → server wrapper → tripwires → verify end-to-end →
git branch / PR / merge.

Branch convention: `po-phase-N-description`.

---

## P1 — Dedupe + discovery scope  ✓ done

**Goal:** Map every PO catalog prompt to one of: already-covered /
new-tool-needed / aggregate. Decide the true new surface. No code.

**Result.** Grounded in the existing `search_purchase_orders` tool, which
filters by `supplier_name` / `supplier_id` / `status`, projects a fixed field
set (POHeaderId, OrderNumber, Status, StatusCode, Supplier, SupplierId, Buyer,
BuyerId, Ordered, CurrencyCode, Description, CreationDate), and is list-only
over `/purchaseOrders` — no child calls, no projection control, no aggregation.

| Prompt(s) | Verdict | Lands in |
|---|---|---|
| 1, 11, 15 | Already covered (PO/supplier list, empty-result handling) | — |
| 6, 12, 13 | Already covered (invoice by supplier+date; supplier sites, Phase 12) | — |
| 2, 9 | New — PO detail + line children / nested | P2 |
| 16, 25 | New — projection control (return only named columns, KG-field-driven à la Phase 7) | P2 |
| 10 | New — PO schedules | P3 |
| 14 | New — PO distributions | P3b |
| 4 | Partial — sites covered; **contacts** new | P4 |
| 3 | New — received vs ordered (`/receivingReceiptRequests`) | P5 |
| 5 | New — invoices filtered **by PO** (invoice tool filters by supplier, not PO) | P5 |
| 7, 17, 18, 19, 20, 21–24 | New — aggregates (count, sum, rank, concentration) | P6 |

**Net:** P2–P6 all stand. P2 is the largest new surface (child lines +
projection). Prompt 5 folded into P5 alongside received-vs-ordered — both are
small PO-join filters over an adjacent resource.

---

## P2 — PO detail + lines

**Goal:** Single-PO fetch and its line children, with column projection.

**Endpoints:**
- `/purchaseOrders/{POHeaderId}`
- `/purchaseOrders/{POHeaderId}/child/lines`

**Catalog prompts:** 2 (PO detail + lines), 16 (projection: OrderNumber,
Supplier, Total), 25 (recent POs projection).

**Notes:** Projection prompts live here — register returned columns as
`kg_entity_field` rows, never hardcode in tool/response code.

---

## P3 — PO schedules

**Goal:** A PO's shipment schedules, fetched as a clean one-hop by POHeaderId.

**Endpoint:**
- `/purchaseOrderSchedules?q=POHeaderId=...` (flat top-level collection —
  confirmed on the pod, HTTP 200)

**Catalog prompts:** 10 (schedules for a PO, ship-to + need-by).

**Notes:** Discovery found a flat `/purchaseOrderSchedules` collection, so
this is a one-hop fetch keyed on POHeaderId — mirrors the P2 lines tool.
The schedule row carries POLineId and LineLocationId (must be in the
projection) so P3b's distributions can later iterate from it. Flat-endpoint
field names differ from the nested view: ScheduleStatus (not Status),
Amount (not Ordered), ShipToLocation (not ShipToLocationCode).

---

## P3b — PO distributions (deferred; blocked on planner work)

**Goal:** Distribution accounts (charge / accrual / variance) per schedule.

**Endpoint:**
- `…/lines/{POLineId}/child/schedules/{LineLocationId}/child/distributions`
  (nested only — there is NO flat `/purchaseOrderDistributions`; confirmed
  404 on the pod)

**Catalog prompts:** 14 (distribution accounts behind a PO's schedules).

**Blocker.** The nested path needs THREE ids per parent schedule row
(POHeaderId, POLineId, LineLocationId). Iterating distributions over a PO's
schedules therefore needs multi-field iteration — passing several parent-row
fields into the tool's args. Block 3 today threads a single
`$iteration_value` per parent, so this requires a planner (and executor)
enhancement. Scoped as its own phase so that enhancement is designed and
tested in isolation, not bolted onto the simple schedules build.

---

## P4 — Supplier contacts

**Goal:** Supplier contacts child, mirroring existing sites / classifications.

**Endpoints:**
- `/suppliers/{SupplierId}/child/contacts`

**Catalog prompts:** 4 (find supplier, show sites + contacts).

**Notes:** Edge-filter pattern already proven in Phases 12–13. Per-supplier
child call (bulk `expand` silently ignored on this pod). Sites side of
prompt 4 is already covered — only contacts is new.

---

## P5 — Receipt requests + invoices-by-PO

**Goal:** Received-versus-ordered via receiving receipts, plus filtering
invoices by PO.

**Endpoints:**
- `/receivingReceiptRequests`
- `/invoices` (new filter: by PO rather than by supplier)

**Catalog prompts:** 3 (received vs ordered for a PO), 5 (invoices raised
against a PO).

**Notes:** New top-level resource for receipts. Discovery must find the join
key back to PO (header id vs order number) and confirm which fields filter
server-side. For prompt 5, confirm the PO reference field on `/invoices`
(e.g. PO number vs POHeaderId) — the existing invoice tool filters by
supplier only.

---

## P6 — PO aggregates

**Goal:** Count, sum, ranking, concentration analysis over POs.

**Endpoints:**
- `/purchaseOrders` (+ client-side aggregation)
- `/purchaseOrders` + `/invoices` (invoiced vs ordered)

**Catalog prompts:** 7 (status + total value), 17 (high-level summary),
18 (committed spend + open count), 19 (top 5 suppliers by value),
20 (stale POs), 21–24 (invoiced vs ordered, health summary, concentration
risk).

**Notes:** Page-limit cap (~200 on POs, ~25 on suppliers) — aggregates scan
a bounded window only; state this honestly in output. Reuse the aggregation
pattern from Phase 7 / `aggregate_invoices.py`.

---

## Open items (logged, not blocking)

- **Synthesizer doesn't narrate PO lines.** As of P2, "show PO X and its
  lines" fetches the header and lines correctly (parse/plan/execute all
  right), but the synthesized prose describes only the PO header — the line
  items are in the outputs yet absent from the answer. Same class as the
  pre-existing "0 open PO(s); buyer(s)" boilerplate: the synthesizer is
  entity-shaped around suppliers/POs and has no PO-line narration. Deferred
  as its own small synthesizer pass; P2's fetch mechanism is proven.

## Cross-cutting reminders

- **Composite `q=` fails** on this pod — single-clause server-side, rest
  client-side.
- **`expand=` for child collections silently ignored** — per-parent child
  calls.
- **Record ALL columns during discovery** even if only some register now —
  makes later expansion additive (no re-curl).
- **Bump tripwires** in both `scripts/print_kg.py` and
  `tests/test_kg_metadata.py` when adding KG rows.
- **Update** `docs/spire_fusion_endpoints_reference.md` after every discovery
  session.
