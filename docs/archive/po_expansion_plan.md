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

## P3b — PO distributions  ✓ built

**Goal:** Distribution accounts (charge / accrual / variance) per schedule.

**Endpoint:**
- `…/lines/{POLineId}/child/schedules/{LineLocationId}/child/distributions`
  (nested only — there is NO flat `/purchaseOrderDistributions`; confirmed
  404 on the pod)

**Catalog prompts:** 14 (distribution accounts behind a PO's schedules).

**The problem (now solved).** The nested path needs THREE ids per parent schedule row
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

**Tripwires.** entity 10→11, field 61→77, edge 9→10, edge_tool 8→9, vocab
69→71, plus the entity-names test and the new `iter_fields_json` column in
the CREATE. (16 distribution fields registered, not the ~13 first estimated.)

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

## P5 — Received-vs-ordered + invoices-by-PO

**Goal:** Answer "how much of PO X was received vs ordered" and "which
invoices were raised against PO X".

**Discovery reshaped this phase.** The original plan assumed a
`/receivingReceiptRequests` endpoint and a hard invoice→PO join. Neither
holds:

- `receivingTransactions` — **403 Forbidden** for our user. This is the
  natural receipts query resource; access would need a receiving role.
- `receivingReceipts` — **400**: requires ShipmentHeaderId or
  ReceiptNumber. It is a lookup-by-receipt resource; you cannot query it
  by PO.
- `receivingReceiptRequests` — exists with data, but it is an
  **interface/staging** resource (HeaderInterfaceId, ProcessingStatusCode,
  submitForApproval action). Its header carries **no PO reference** at all.
- `purchaseOrderSchedules` — already carries **ReceivedQuantity,
  BilledQuantity, ShippedQuantity, AcceptedQuantity, ReceivedAmount,
  BilledAmount** alongside ordered Quantity/Amount. This IS received-vs-
  ordered, per schedule, on a resource P3 already fetches.
- `/invoices` — carries **PurchaseOrderNumber on the HEADER** (not just on
  lines, as assumed). `q=PurchaseOrderNumber=<num>` filters **server-side**
  (single clause, per the pod rule).

**Scope (both halves are small; no new endpoint, tool, entity or edge):**

- **Prompt 3 (received vs ordered)** — add the received/billed fields to the
  schedules tool projection and register them as POSchedule
  `kg_entity_field` rows. The data is already being fetched.
- **Prompt 5 (invoices by PO)** — one new `kg_entity_filter` row on Invoice
  (`purchase_order` → server_q on PurchaseOrderNumber) plus the arg on the
  existing `search_invoices` tool.

**Join key:** the PO **number** (string, e.g. "162034"), not POHeaderId —
consistent with invoices joining on SupplierNumber rather than SupplierId.

**Anchors:** PO 162034 (Lee Supplies) has invoice 162034inv (830.01). Note
PO 2144 / 162352 has **no** invoices, so it is not a usable anchor for
prompt 5.


## P5b — Synthesizer: narrate child entities  (before P6)

**Goal:** Make the synthesized prose actually answer the questions whose
data we already fetch.

**Why this comes before P6.** Every phase since P2 fetches child data
correctly — PO lines, schedules, distributions, contacts, and the
received/billed figures — but the synthesizer describes only the parent
(the PO header or the supplier) and ignores the children entirely. The data
sits in the outputs; the answer never mentions it. So several catalog
prompts are **data-complete but answer-incomplete**:

- prompt 2 ("PO detail + lines") — 2 lines fetched, not narrated
- prompt 3 ("received vs ordered") — the comparison IS the question; the
  answer currently describes the PO's status and buyer instead
- prompt 4 ("supplier + contacts") — 10 contacts fetched, not narrated
- prompt 10 ("schedules, ship-to + need-by") — fetched, not narrated
- prompt 14 ("distribution accounts") — fetched, not narrated

P6's value is **entirely prose** (summaries, rankings, concentration risk).
Fixing the synthesizer first means P6 builds on something that can speak.

**Scope:**
- Narrate child entities generically: PurchaseOrderLine, POSchedule,
  PODistribution, Contact. The synthesizer is currently entity-shaped
  around Supplier/PurchaseOrder only.
- Received-vs-ordered comparison (prompt 3): compare Quantity/Amount against
  ReceivedQuantity/ReceivedAmount/BilledQuantity/BilledAmount per schedule.
- Fix the pre-existing boilerplate: "0 open PO(s); buyer(s): (no buyer)"
  fires on every supplier query regardless of relevance.

**Note:** logged as an open item from P2 onward, it grew with every phase.
It is now the bottleneck — not the fetching.

### Design (review before code)

**Three things change together — schema, prompt, validator.** They are
coupled: the schema decides what CAN be said, the prompt decides when it IS
said, the validator decides whether it can be trusted. Changing one alone
does nothing.

**1. Sub-models (follow the existing `AddressInfo` precedent).** Four, each
summary-shaped — only the fields its prompt needs, not every column we fetch
(verbosity burns context and invites invention):

- `LineInfo` — line_number, description, category, quantity, amount
- `ScheduleInfo` — schedule_number, ship_to_location,
  requested_delivery_date, ordered_quantity, ordered_amount,
  received_quantity, billed_quantity, received_amount, billed_amount
- `DistributionInfo` — distribution_number, charge_account, accrual_account,
  variance_account, percentage, amount
- `ContactInfo` — contact_name, email, job_title, is_administrative

**2. Nest them on the parent record**, exactly as `addresses` nests on
`SupplierRecord` — optional lists, `default_factory=list`, empty when the
query didn't ask:

- `PurchaseOrderRecord`: + `lines`, `schedules`, `distributions`
- `SupplierRecord`: + `contacts`

**3. Make `open_po_count` optional** (`int | None = None`). It is currently a
REQUIRED int, so every supplier answer must state it — which is exactly why
"0 open PO(s); buyer(s): (no buyer)" appears on queries that never mentioned
POs. Populate only when an open_pos bucket is present.

**4. Prompt blocks.** The PurchaseOrder block currently says "emit header id,
order number, status, supplier name/id... include the buyer if present" — it
is silent on children, matching the schema. Extend both blocks to say when to
emit each child list, and (Supplier) to leave open_po_count null when there
is no open_pos bucket.

**5. Received-vs-ordered (prompt 3).** Expose the raw ordered/received/billed
numbers on `ScheduleInfo`; let the summary state the comparison ("1 of 1
received; 33,000 of 33,000 billed"). Do NOT ask the LLM to compute
percentages or deltas — follow the SupplierSpendRanking block's existing
"the totals are already computed, do not do arithmetic" discipline. The LLM
is unreliable at arithmetic (cf. the date-computation lesson).

**6. Hallucination guard.** Every new id must be cross-referenced against the
executor's output, as supplier_id/person_id/address_id are today: POLineId,
LineLocationId, PODistributionId, SupplierContactId. Without this, the new
fields are precisely where invented data would appear — a schema that permits
detail without validating it is worse than one that says nothing.

**Verification is qualitative.** Unlike every previous phase, "did the right
rows come back?" is already true. The question is "does the answer answer the
question?" — so verification means reading the prose for prompts 2, 3, 4, 10
and 14, not asserting row counts. The schema and validator changes are
unit-testable; the narration is judged by eye.

### Build order
1. Sub-models + nest on the two records + open_po_count optional.
2. Extend the two prompt blocks.
3. Extend the validators for the four new id types.
4. Re-run prompts 2/3/4/10/14 and read the answers.
5. Full suite (synthesizer has 32 tests + 6 aggregation tests).
6. Git branch `po-phase-5b-synthesizer`, PR, merge.

**Different in kind:** every phase so far has been fetch-shaped (discover an
endpoint, write a tool, wire the KG, check the rows come back). P5b is
output-shaped: the data is already there. Verification is qualitative —
"does this answer the question?" — not "did the right rows return?"

---

## P6 — PO aggregates

**Goal:** Every PO aggregate prompt in the catalog works. Nothing is dropped —
the split below is about landable commits, not scope.

**The architectural rule (from `aggregate_invoices.py`).** "Grouping and the
measure are FIXED BY IDENTITY — they are not parameters. A different grouping
or measure is a different tool, never a flag on this one. This is the line that
keeps the aggregation layer a set of bounded tools rather than a generic
engine." P6 obeys this: each distinct grouping/measure is its own tool.

Judged against that rule, the catalog's prompts are three kinds of work:

| Prompt | Grouping | Measure | Kind |
|---|---|---|---|
| 19 — top N suppliers by PO value | supplier | sum(Ordered) | single-source aggregation |
| 7 — PO count + total value by status | status | count + sum | single-source aggregation |
| 18 — committed spend + open PO count | none | sum + count | single-source aggregation |
| 20 — stale POs | none | none — a date filter + list | PO list query, not aggregation |
| 21-24 — invoiced vs ordered, concentration | two sources | comparison | two-source join |

### Commit 1 — single-source aggregations (7, 18, 19)

Three tools mirroring `aggregate_invoices_by_supplier`: page the source, group,
measure, return a small structured result; the LLM never does the arithmetic.
Each gets a synthesizer shape alongside `supplier_spend_ranking`.

- `aggregate_purchase_orders_by_supplier` — group by supplier, sum `Ordered`,
  rank, top_n. Near-twin of the invoice tool; different source and measure.
- `aggregate_purchase_orders_by_status` — group by `StatusCode`, count + sum.
- `summarize_open_purchase_orders` — no grouping; committed spend + open count.

### Commit 2 — stale POs (20) and two-source comparison (21-24)

**Prompt 20 needs a PO date filter.** `search_purchase_orders` cannot filter by
date today, and the planner guard refuses PO-rooted queries without an id.
**Decision: add a PO date filter and let it satisfy the guard** — exactly as
P5's `purchase_order` filter now satisfies the Invoice guard. The rule becomes
"PO queries need an id OR a date filter", so a bounded PO list is allowed while
an unbounded one still refuses.

**Prompts 21-24 need a two-source join**: fetch POs, fetch invoices, match on
`PurchaseOrderNumber` (the P5 join key — a string, not POHeaderId), compare
ordered against invoiced. Concentration risk is that ranking plus a stated
judgement; the judgement must come from the synthesizer phrasing computed
numbers, never from the LLM doing arithmetic.

**Both commits land on one branch, one PR.**

### Discovered: the PO status vocabulary is incomplete

Running the status breakdown surfaced the pod's REAL StatusCode values —
**eleven**, not the four the KG knows:

| StatusCode | POs | Total ordered |
|---|---|---|
| CLOSED | 2731 | 487,343,212.13 |
| OPEN | 201 | 116,643,997.40 |
| CLOSED FOR RECEIVING | 215 | 81,348,599.88 |
| REJECTED | 39 | 4,266,419.00 |
| PENDING APPROVAL | 8 | 743,047.12 |
| WITHDRAWN | 6 | 217,144.00 |
| INCOMPLETE | 47 | 184,944.45 |
| CLOSED FOR INVOICING | 8 | 18,291.00 |
| PENDING SIGNATURE | 3 | 7,470.00 |
| CANCELED | 102 | 4,000.00 |
| ON HOLD | 2 | 2,250.00 |

Note the values use **spaces, not underscores** ("PENDING APPROVAL", not
PENDING_APPROVAL — the endpoints reference says otherwise and is wrong).

`kg_vocabulary` maps only open/closed/canceled/incomplete. Consequences:
"POs on hold", "rejected POs" and "POs pending approval" cannot be asked
today; and **"closed POs" silently means only the plain CLOSED bucket,
missing the 223 POs in CLOSED FOR RECEIVING / CLOSED FOR INVOICING**.

P6's KG step adds the missing `po_status` rows. Whether the three closed-ish
states should collapse under "closed" is a judgement call to make explicitly
rather than by omission — they are genuinely different states, so the default
is to keep them distinct and add separate terms.

### Discovered: vocabulary alone doesn't unlock status questions

Adding the eleven `po_status` rows makes the terms resolvable, but
"suppliers with rejected purchase orders" still refuses — correctly, and
with a precise reason:

> There is no filter to find suppliers based on the status of their
> purchase orders (other than 'open').

`has_open_PO` is the only supplier-to-PO status filter and its status is
hardcoded (`implicit_term='open'`). A general `has_PO_with_status` filter
taking the status as a value would unlock the other ten — that is a filter
change, not a vocabulary one, and belongs to its own phase. The vocab rows
still earn their place: they serve the aggregations and are the
prerequisite for any such filter.

Worth noting the refusal is the system diagnosing its own gap accurately —
better than answering wrongly.

### Honest constraints
- **Bounded window.** `aggregate_invoices` pages to MAX_PAGES and flags the
  result truncated at the cap; sums are then lower bounds. The PO tools inherit
  this. A "total value" answer is honest only about what was examined — the
  synthesizer must say so when truncated.
- **Composite `q=` fails**, so each tool sends one selective server clause and
  filters the rest client-side, like every other tool here.

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
