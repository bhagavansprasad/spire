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

## P3b — PO distributions (design; blocked on planner work)

**Goal:** Distribution accounts (charge / accrual / variance) per schedule.

**Endpoint:**
- `…/lines/{POLineId}/child/schedules/{LineLocationId}/child/distributions`
  (nested only — there is NO flat `/purchaseOrderDistributions`; confirmed
  404 on the pod)

**Catalog prompts:** 14 (distribution accounts behind a PO's schedules).

**Blocker.** The nested path needs THREE ids per parent schedule row
(POHeaderId, POLineId, LineLocationId), all carried on each schedule row (P3
already projects POLineId and LineLocationId for this). The natural traversal
iterates over a PO's schedules, passing three fields per row to the tool. But
the executor's iteration (`_collect_iteration_values` /
`_execute_iterating_step`) threads a SINGLE `$iteration_value` per parent:
`iterate_over = {from_step, field}` with one field → one arg. So P3b needs an
additive multi-field iteration enhancement.

### Design (review before code)

**Principle — additive, single-field path untouched.** Lines, schedules,
contacts, invoices, buyer, and every supplier edge filter use the single-field
path and must not change. The multi-field path is a NEW branch entered ONLY
when a step declares it; every existing plan runs the same code as today.

**Edge direction.** The edge is `POSchedule → PODistribution` (the traversal
iterates over schedules), so the include chain is
PurchaseOrder → POSchedule → PODistribution — two sequential include hops,
which Block 3 already chains via `previous_entity`.

**KG shape.** New entity `PODistribution` (canonical `PODistributionId`,
display `DistributionNumber`, include-only). ~13 fields: the three parent id
references, DistributionNumber, POChargeAccount, POAccrualAccount,
POVarianceAccount, DeliverToLocationCode, Percentage, Quantity, Ordered,
Status. New edge `HAS_DISTRIBUTION` plus edge-tool binding.

The multi-id edge needs to declare it requires three parent fields mapped to
three tool args. **Chosen: a new nullable `iter_fields_json` column on
kg_edge** holding `{tool_arg: parent_field}` — present only for multi-field
edges, NULL for all existing edges (so single-field edges are untouched).
`from_join_field`/`to_join_field` stay `LineLocationId` (the primary id) so any
code reading a single field still works. The HAS_DISTRIBUTION map:
`{"po_header_id": "POHeaderId", "po_line_id": "POLineId", "line_location_id": "LineLocationId"}`.
(Rejected alternative: overloading `from_join_field` as a comma list by
convention — implicit and fragile.)

**Tool.**
`get_purchase_order_distributions(po_header_id, po_line_id, line_location_id, limit=25)`
— nested-path fetch, returns a ToolResult, 404→empty guard. Three ids instead
of one.

**Executor (the core change, additive).**
- `_collect_iteration_values`: if `iterate_over` has a `fields` map, return a
  list of DICTS (one per parent row, `{tool_arg: row[parent_field]}`); rows
  missing any required field are dropped; dedupe on the value tuple. The
  existing `field` branch is unchanged (returns scalars).
- `_execute_iterating_step`: if the collected values are dicts, merge each into
  a copy of `tool_args` (several sentinel keys); if scalars, run the existing
  single-key substitution. Dispatch by shape, so no existing step reaches the
  new branch.

**Planner (Block 3).** When the edge carries `iter_fields_json`, emit
`tool_args={arg: "$iteration_value" for arg in fields}` and
`iterate_over={from_step, fields}`. When absent (every existing edge), emit the
current single-field form unchanged.

**Parser.** Hint: "and its distributions" / "the distribution accounts" on a PO
question → include POSchedule AND PODistribution. **Chosen: auto-include the
POSchedule hop** (asking for distributions implies the schedule traversal);
surface distributions in the answer.

**Executor value shape.** **Chosen: list of dicts** for the multi-field case —
simplest, smallest diff.

**Tripwires.** entity 10→11, field 61→74, edge 9→10, edge_tool 8→9, vocab
69→71, plus the entity-names test and the new `iter_fields_json` column in
the CREATE.

**Regression (load-bearing).** Rerun ALL existing includes (lines, schedules,
contacts) end to end AND the full suite, to prove the single-field path is
byte-for-byte unaffected by the executor change.

### Build order
1. Live curl: re-confirm the distributions path + capture full field list.
2. Standalone tool, verified live.
3. KG: add `iter_fields_json` column; PODistribution entity/fields;
   HAS_DISTRIBUTION edge with the fields map; edge-tool; vocab. Rebuild.
4. Executor: additive multi-field branch; unit-test single-field (unchanged)
   AND multi-field paths.
5. Planner Block 3 multi-field emission; parser hint; server wrapper;
   tripwire bumps.
6. Verify end to end; rerun all includes; full suite.
7. Git branch `po-phase-3b-distributions`, PR, merge.

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
