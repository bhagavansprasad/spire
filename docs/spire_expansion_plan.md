# Spire Expansion — Master Plan

The single source of truth for expanding Spire's Oracle Fusion coverage.
Consolidates what used to live in three files: `po_expansion_plan.md`
(the PO phased plan), `kg_expansion_phases.md` (the live status tracker),
and `spire_expansion_endpoints.md` (the endpoints/prompts catalog). Those
are now merged here; keep updating this file only.

Structure:
- **Conventions & build sequence** — how every phase is built and shipped.
- **Cross-cutting reference** — pod quirks, architecture rules, routing
  mechanisms. Read before building anything.
- **Live status** — every phase across every module, one table.
- **Module 4: PO** — the completed reference module (P1–P6c, all merged).
- **Module 1: AR** · **Module 2: GL** · **Module 3: AP** — basic plans,
  to be fleshed out at each module's P1 discovery.
- **Endpoints catalog** — the raw endpoint/prompt tables for all four
  modules, plus column-capture status.

---

## Conventions & build sequence

**Branch convention:** `<module>-phase-N-description` (e.g.
`po-phase-6c-invoiced-vs-ordered`, `ar-phase-2-invoices`).

**Git discipline:**
- One branch per logical change, PR-based merges.
- Named files in `git add` — never `-A`.
- Heredoc commit messages (`git commit -F- <<'EOF'`).
- Docs-only changes may go straight to master.

**The proven build sequence** (every code phase follows it):
1. Live curl discovery — hit the pod, record every column (even ones not
   registered yet, so later expansion is additive).
2. Standalone tool — a plain async function, not coupled to FastMCP.
3. KG rows *or* op-registry entry — rebuilt from scratch (`rebuild_kg.py`),
   never incrementally. (Which one depends on the query kind — see Routing
   below.)
4. Planner edits.
5. Parser line / instruction block.
6. Server wrapper (`@mcp.tool()`).
7. Tripwires — bump expected counts in both `scripts/print_kg.py` and
   `tests/test_kg_metadata.py` when KG rows change.
8. Tests — pod-free unit tests + pod-gated integration tests.
9. Verify end-to-end (prompt set).
10. Git branch → PR → merge.

**Permission gates:** ask before generating code or significant content;
one command at a time; verify each step before the next.

**Pod:** `fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com`. Credentials
live in `personas.yaml` (single source; `load_persona('default_dev')`).
Base REST path for all resources: `/fscmRestApi/resources/11.13.18.05/`.

---

## Cross-cutting reference

### Pod quirks (confirmed)
- **Composite `q=` fails** — send one selective server clause, filter the
  rest client-side. Every tool does this.
- **`expand=` for child collections is silently ignored** — use per-parent
  child calls, not expansion.
- **`totalResults=true`** is required to get a real total count; without it
  `count` reflects only the returned page size.
- **Supplier.Status is unreliable server-side** — match client-side.
- **Country requires `expand=addresses`** (address records use
  `SupplierAddressId`, not `AddressId`).
- **Join-key asymmetry:** invoices reference suppliers by `SupplierNumber`
  (string) and POs by `SupplierId` (numeric); invoice↔PO joins use
  `PurchaseOrderNumber` (string), NOT POHeaderId. POs carry NO
  `SupplierNumber` (`SupplierNumber` in `?fields=` on `/purchaseOrders` is
  HTTP 400).
- **Flat `/purchaseOrderSchedules` exists** and accepts `q=POHeaderId=`
  server-side; there is NO flat `/purchaseOrderDistributions` (404) — those
  need the deep nested path with three ids.
- **OrderDate is NOT queryable** on POs; use `CreationDate` for date bounds.
- **PO OrderNumber vs POHeaderId** are different identifiers and look
  identical in a prompt (OrderNumber "162034" is POHeaderId 1). The PO
  lookup tool resolves either (tries OrderNumber first, then POHeaderId).
- **OWSM 401s** can appear right after a pod switch and self-resolve in
  ~30 min — a transient, not a credential problem.
- Keep `spire_fusion_endpoints_reference.md` updated after every discovery
  session — it's the authority on pod quirks.

### Architecture rules
- **Deterministic KG-driven pipeline** (Design 3): parse → plan → execute →
  synthesize. Tool selection is a lookup, not an LLM judgment. Not an agent
  architecture.
- **Grouping and measure are FIXED BY IDENTITY, never parameters.** A
  different grouping or measure is a different tool, never a flag. This is
  the line that keeps the aggregation/comparison layers a set of bounded
  tools rather than a generic engine. (From `aggregate_invoices.py`.)
- **The LLM never does arithmetic.** Tools compute every number; the
  synthesizer templates them. The LLM is unreliable at arithmetic (cf. the
  date-computation lesson). Aggregation and comparison synthesizer shapes
  are deterministic (no LLM) for exactly this reason.
- **Hallucination guard:** every structured id in a synthesized response is
  cross-referenced against the executor's output. A schema that permits
  detail without validating it is worse than one that says nothing.
- **Bounded windows:** page to `MAX_PAGES` and flag `truncated` at the cap;
  sums past the cap are lower bounds, and the synthesizer must say so.

### Reliability backlog (cross-cutting, not tied to a module)
- **Parser runaway defence** (post-AR-P2c, not started). A structured-output
  parse can hang for minutes if the LLM fails to converge and generates to
  its output-token ceiling. Observed in AR-P2c: a single cross-referencing
  sentence in the parser prompt (naming `has_open_PO` inside the
  customer-invoices instruction) sent Gemini flash to `out=65520` tokens,
  ~267s, on every run — deterministic, not flaky. Removing the sentence:
  `out=293`, ~8s. Detection signal already in logs: `[llm] out=` near the
  model's max (with `finish_reason=length`, not `stop`) means a runaway,
  not a real parse. Work: (a) cap `max_output_tokens` in `build_llm` so a
  runaway fails in ~2s not ~4min — highest-value, do first; (b) detect
  ceiling-hit / `finish_reason=length` and log a warning, optionally retry
  once; (c) wall-clock timeout on the parse call; (d) capture the failure
  mode (symptom + cause: cross-referencing an unrelated concept in a
  structured-output instruction can block convergence) in
  `spire_design_decisions.md`. Needs `config.py`.
- **Open-invoices top-N limit** (finishes AR-P2c prompt 1, not started).
  Prompt 1 is "top 5 open invoices" but the phase shipped open_only only;
  it returns ALL open invoices, not the top 5. The tool already takes
  `limit` and returns rows balance-desc, so the wiring is small: parser
  extracts "top N" → a limit on the Intent → planner passes it to the
  CustomerTransaction step. Its own small phase.
- **Synthesizer does arithmetic (pre-existing, broader than AR-P2c).**
  The CustomerAccount narration sums invoice amounts and reports totals in
  prose (observed on prompt 1: a wrong "combined original amount", and the
  account's negative credit-balance field reported as the open-invoice
  total). Violates the no-arithmetic rule — tools must compute, the
  synthesizer only templates. Affects Shape B narration generally, not
  just open invoices. Fix belongs in the synthesizer, not this phase.

### Routing mechanisms — three kinds of query
The planner routes a parsed Intent one of three ways. Knowing which a new
prompt needs decides what you wire.

1. **Entity/filter queries** (list, detail, child traversal) → routed
   through the **KG tables** (`kg_entity`, `kg_entity_filter`, `kg_edge`,
   etc.). Adding one means KG rows + a rebuild + tripwire bumps.
2. **Aggregations** (rank, count, sum) → routed through the planner's
   **op-registry** (`_AGGREGATION_TOOLS` / `_AGGREGATION_PARAMS`), via a
   `aggregate` block on the Intent. NOT the KG. Adding one means a registry
   row pair + a parser instruction + a synthesizer shape.
3. **Comparisons** (invoiced-vs-ordered, two-source joins) → routed through
   the **comparison op-registry** (`_COMPARISON_TOOLS` / `_COMPARISON_PARAMS`),
   via a `compare` block on the Intent. NOT the KG. Same shape as
   aggregation. Added in P6c.

Aggregation and comparison both bypass the KG and both skip
`validate_intent` (their Intents carry no target_entity). The parser has a
"do NOT refuse" instruction block for each, and `validate_intent` exempts
each.

---

## Live status

Status vocab: `not started` · `in progress` · `blocked` · `merged`.

| Module | Phase | Goal | Branch | Status |
|---|---|---|---|---|
| PO | P1 | Dedupe + discovery scope | `po-phase-1-dedupe` | merged (docs-only) |
| PO | P2 | PO detail + lines + projection | `po-phase-2-po-lines` | merged |
| PO | P3 | PO schedules (flat endpoint) | `po-phase-3-schedules` | merged |
| PO | P3b | PO distributions (multi-field iteration) | `po-phase-3b-distributions` | merged |
| PO | P4 | Supplier contacts | `po-phase-4-supplier-contacts` | merged |
| PO | P5 | Received-vs-ordered + invoices-by-PO | `po-phase-5-received-invoices-by-po` | merged |
| PO | P5b | Synthesizer: narrate child entities | `po-phase-5b-synthesizer` | merged |
| PO | P6 | PO aggregates (by-supplier / by-status / open) | `po-phase-6-aggregates` | merged |
| PO | P6b | PO date filter (stale POs) | `po-phase-6b-po-dates` | merged |
| PO | P6c | Invoiced-vs-ordered comparison | `po-phase-6c2-invoiced-vs-ordered` | merged |
| **AR** | **P1** | **Dedupe + column capture + plan** | `ar-phase-1-dedupe` | **merged (docs-only)** |
| **AR** | **P2a** | **AR invoice by-id + lines (prompts 11, 12, 2)** | `ar-phase-2-invoices` | **merged** |
| **AR** | **P2b** | **Customer invoices via account (prompt 15)** | `ar-phase-2b-customer-invoices` | **merged** |
| AR | P2c | Open invoices top-5 (prompt 1) | `ar-phase-2c-open-invoices` | not started |
| AR | P3+ | Tax lines, DFF, credit memos, aggregates | — | not started |
| **GL** | **P1** | **Dedupe + plan** | `gl-phase-1-dedupe` | **not started** |
| GL | P2+ | (defined at P1) | — | not started |
| **AP** | **P1** | **Dedupe + write-safety design + plan** | `ap-phase-1-dedupe` | **not started** |
| AP | P2+ | (defined at P1) | — | not started |

**Next up:** AR P1 — the module is read-heavy and closest to Spire's
existing supplier/invoice patterns, so it reuses the most and risks the
least. See Module 1 below.

### Known test notes (not bugs)
- **Three supplier `truncated is False` assertions** fail on pods with more
  suppliers than `OVERFETCH_LIMIT` (500): `search_suppliers` over-fetches,
  examines 500, finds no match, honestly reports `truncated=True`. The code
  is correct; the tests encode a data-volume assumption. Do NOT "fix" by
  weakening the assertion or raising the cap — this is deferred
  test-portability work. (The assumption held on esll-dev37 and flipped on
  eqjz; with the pod back on esll-dev37 it may hold again.)
- **Distribution test anchors are pod-specific.** The integration test
  anchors on PO 2144's chain (POHeaderId 2144, POLineId 19782,
  LineLocationId 18954), valid on esll-dev37. A pod switch may require
  re-capturing them (find a PO with distributions, update the constants).

---

# Module 4: PO (Purchase Orders / Procurement) — COMPLETE

The reference module. All phases merged. Kept in full as the worked example
of how a module is built.

Source: Oracle Fusion Procurement MCP Tool document. Overlaps Spire's
existing Supplier / PO / Invoice coverage — which is why P1 was a dedupe.

## P1 — Dedupe + discovery scope ✓ merged (docs-only)

**Goal:** map every PO catalog prompt to already-covered / new-tool-needed /
aggregate. No code.

Grounded in the existing `search_purchase_orders` tool (filters by
`supplier_name` / `supplier_id` / `status`, projects a fixed field set,
list-only over `/purchaseOrders` — no child calls, no projection control, no
aggregation).

| Prompt(s) | Verdict | Lands in |
|---|---|---|
| 1, 11, 15 | Already covered (PO/supplier list, empty-result) | — |
| 6, 12, 13 | Already covered (invoice by supplier+date; supplier sites) | — |
| 2, 9 | New — PO detail + line children / nested | P2 |
| 16, 25 | New — projection control (KG-field-driven) | P2 |
| 10 | New — PO schedules | P3 |
| 14 | New — PO distributions | P3b |
| 4 | Partial — sites covered; contacts new | P4 |
| 3 | New — received vs ordered (`/receivingReceiptRequests`) | P5 |
| 5 | New — invoices filtered by PO | P5 |
| 7, 17, 18, 19, 20, 21–24 | New — aggregates + comparison | P6 |

## P2 — PO detail + lines ✓ merged

Single-PO fetch and line children, with column projection.
- `/purchaseOrders/{POHeaderId}` and `…/child/lines`.
- Projection prompts (16, 25): register returned columns as `kg_entity_field`
  rows, never hardcode in tool/response code.
- **Identifier resolution:** the PO lookup resolves OrderNumber OR
  POHeaderId (tries OrderNumber first — what a user reads off a PO). Latent
  bug before this: every test used 2144, which happens to be a POHeaderId,
  so the OrderNumber path was never exercised.

## P3 — PO schedules ✓ merged

A PO's shipment schedules as a clean one-hop by POHeaderId.
- Flat `/purchaseOrderSchedules?q=POHeaderId=…` (confirmed HTTP 200).
- The schedule row carries POLineId and LineLocationId (in the projection) so
  P3b's distributions can iterate from it.
- Flat-endpoint field names differ from the nested view: ScheduleStatus (not
  Status), Amount (not Ordered), ShipToLocation (not ShipToLocationCode).

## P3b — PO distributions ✓ merged

Distribution accounts (charge / accrual / variance) per schedule.
- Nested only: `…/lines/{POLineId}/child/schedules/{LineLocationId}/child/distributions`
  — no flat endpoint (404).
- **The problem:** the nested path needs THREE ids per parent schedule row
  (POHeaderId, POLineId, LineLocationId). The executor's iteration threaded a
  SINGLE `$iteration_value` per parent.
- **The solution (additive):** a new nullable `iter_fields_json` column on
  `kg_edge` holding `{tool_arg: parent_field}` — present only for multi-field
  edges, NULL for all existing ones. The executor gained a multi-field branch
  entered ONLY when a step declares it; every existing plan runs unchanged.
  New entity `PODistribution`, edge `HAS_DISTRIBUTION`.

## P4 — Supplier contacts ✓ merged

Contact people on a supplier. Per-supplier child call (no bulk endpoint).
New entity `Contact`, edge `HAS_CONTACT`.

## P5 — Received-vs-ordered + invoices-by-PO ✓ merged

- Received vs ordered via `/receivingReceiptRequests` (prompt 3).
- Invoices filtered by PO (prompt 5) — the `purchase_order` filter on Invoice,
  which also satisfies the Invoice planner guard (invoices need a supplier OR
  a PO).

## P5b — Synthesizer: narrate child entities ✓ merged

Sequenced BEFORE P6 because every phase since P2 fetched child data correctly
but the prose ignored it — lines, schedules, contacts, distributions,
received-vs-ordered all in the outputs yet absent from the answer.
Output-shaped work, not fetch-shaped: verification is qualitative ("does the
answer answer the question?"). Received-vs-ordered exposes the raw
ordered/received/billed numbers and lets the summary state the comparison —
the LLM does NOT compute percentages or deltas.

## P6 — PO aggregates ✓ merged

**The rule:** grouping and measure fixed by identity; each distinct
grouping/measure is its own tool. The catalog's aggregate prompts are three
kinds of work:

| Prompt | Grouping | Measure | Kind |
|---|---|---|---|
| 19 — top N suppliers by PO value | supplier | sum(Ordered) | single-source aggregation |
| 7 — PO count + total by status | status | count + sum | single-source aggregation |
| 18 — committed spend + open count | none | sum + count | single-source aggregation |
| 20 — stale POs | none | none — date filter + list | PO list query |
| 21-24 — invoiced vs ordered, concentration | two sources | comparison | two-source join |

**Commit 1 — single-source aggregations (7, 18, 19):** three tools mirroring
`aggregate_invoices_by_supplier`. `aggregate_purchase_orders_by_supplier`,
`aggregate_purchase_orders_by_status`, `summarize_open_purchase_orders`. Each
gets a synthesizer shape. Routed via the aggregation op-registry, not the KG.

**Discovered — PO status vocabulary was incomplete.** The pod has ELEVEN
StatusCode values, not the four the KG knew, and they use **spaces, not
underscores** ("PENDING APPROVAL", not PENDING_APPROVAL — the endpoints
reference said otherwise and was wrong): CLOSED, OPEN, CLOSED FOR RECEIVING,
REJECTED, PENDING APPROVAL, WITHDRAWN, INCOMPLETE, CLOSED FOR INVOICING,
PENDING SIGNATURE, CANCELED, ON HOLD. Commit 1 added the eleven `po_status`
vocab rows. Note "closed POs" plainly meant only the CLOSED bucket, missing
the CLOSED FOR RECEIVING / CLOSED FOR INVOICING POs — the three closed-ish
states are kept distinct by default.

**Still open (logged):** `has_PO_with_status` filter. Adding the vocab rows
makes the terms resolvable, but "suppliers with rejected POs" still refuses —
`has_open_PO` is the only supplier-to-PO status filter and its status is
hardcoded to 'open'. A general `has_PO_with_status` filter taking the status
as a value would unlock the other ten. A filter change, its own phase. The
vocab rows still earn their place (they serve the aggregations).

## P6b — PO date filter (stale POs, prompt 20) ✓ merged

`search_purchase_orders` couldn't filter by date, and the planner guard
refused PO-rooted queries without an id. Added `created_before` /
`created_since` filters (on `CreationDate`, since OrderDate isn't queryable)
and widened the guard: "PO queries need an id OR a date filter." A bounded PO
list is allowed; an unbounded one still refuses. Relative windows ("older than
6 months") deliberately refuse — the LLM must not compute a cutoff itself.

## P6c — Invoiced-vs-ordered comparison (prompts 21-24) ✓ merged

**Design question resolved: a bounded TOOL, not a planner join-step** — as the
aggregation rule argued (making the planner do joins is the generic engine the
rule exists to prevent). Three tools, scope fixed by identity:
- `compare_purchase_order_to_invoices` (one PO)
- `compare_supplier_orders_to_invoices` (one supplier, resolved by name)
- `compare_top_suppliers_orders_to_invoices` (top-N by PO value, each compared
  — ranks via the existing aggregation, then resolves each supplier's
  SupplierNumber from its id, since POs carry no SupplierNumber)

Match on `PurchaseOrderNumber` (string). Both sides server-filtered so totals
are exact. Deliberately NO "across everything" version — 53k invoices vs 3k
POs; a truncated comparison lies (every PO would look under-invoiced).

Routed via a `compare` block + `_COMPARISON_TOOLS`/`_PARAMS` registry (NOT the
KG), with a deterministic no-LLM synthesizer shape. over/under-invoiced
phrasing is neutral — an over-invoice is real data (tax, freight, variance).

**Data note.** On the demo pods most invoices are NOT PO-linked (debit memos,
prepayments): PO-linked fraction is ~0–7% across suppliers. So PO-matched
invoiced totals run far below total invoiced; each result surfaces
`unmatched_invoice_count`. A demo-data limitation, not a product one — real
customers PO-match their invoices (three-way matching is standard AP practice).
The feature is correct; it just demos thin on these pods. Reported to Venu.

---

# Module 1: AR (Accounts Receivable) — NEXT

Source: Oracle Fusion AR MCP execution document (pod esll-dev37). 8 resources,
~36 tools. **All read except receipt apply/unapply.**

**Why AR first.** Read-heavy, customer-and-invoice shaped — conceptually the
closest of the three to what Spire already does with suppliers/invoices. It
reuses the most existing patterns and risks the least (no writes to design, no
new balance-by-combination shape). GL and AP come after.

**Shape.** The domain mirror of what Spire has: where PO/supplier is the buy
side, AR is the sell side. Customers (≈ suppliers), AR invoices (≈ AP
invoices), receipts (cash in), credit memos, account activities (balances /
open receivables / exposure). Much of Spire's supplier/invoice machinery
should transfer.

**Known gap before planning.** AR's catalog columns are INCOMPLETE (#1–6
captured from docx images, #7–18 to fill). So AR's P1 must include a
**column-capture step** — live curl against the pod to discover the missing
output columns — before the plan can register `kg_entity_field` rows. This is
the "record all columns during discovery" discipline; AR just starts further
back than PO did.

## AR P1 — Dedupe + column capture + plan ✓ complete (2026-07-19)

> **AR shipped state (as of P2b merge).** AR-P2a and AR-P2b are merged; 4 of
> the 6 P2 prompts (11, 12, 2, 15) are live. KG now holds 15 entities, 125
> fields, 12 edges, 21 filters, 85 vocab, 7 entity-tools, 11 edge-tools;
> full suite 388 passing. NAMING NOTE: the entity/edge tables below were
> sketched at P1 with provisional names; the build used concrete names —
> `ARInvoice`→`ReceivablesInvoice`, `ARInvoiceLine`→`ReceivablesInvoiceLine`,
> `HAS_LINE`→`HAS_AR_LINE`. The account path (P2b) added CustomerAccount +
> CustomerTransaction + HAS_CUSTOMER_TRANSACTION, which the P1 sketch folded
> into "CustomerAccount". The forward tables (P3–P6) are kept as design
> intent and may still be renamed when built.

**Done:** all 18 AR prompts mapped to endpoints; missing columns (#7–18)
captured via live curl against pod `fa-esll-dev37`; entities/edges sketched;
phases confirmed. No feature code (correct for P1). Full column detail and pod
quirks are in `spire_fusion_endpoints_reference.md` §9.

**Dedupe result.** AR is a genuinely new pillar — no existing Spire tool
covers an AR prompt. The supplier/invoice *machinery* transfers (list+filter
shape, per-parent child fetch, the number-vs-id join asymmetry, op-registry
aggregates) but every AR endpoint and object is new. The AP `/invoices`
(payables) Spire already wraps is a DIFFERENT object from AR
`/receivablesInvoices` — do not conflate.

**Column capture.** 6 endpoints curled, all columns recorded (§9):
`/receivablesInvoices` (173,531 rows), its `receivablesInvoiceLines` child,
`/standardReceipts` (37,335), `/receivablesCustomerAccountActivities` (435),
`/receivablesCreditMemos` (2,111), and CRM `/accounts` (1,476, ruled out).
Two catalog names were wrong: `/receivablesCustomers` 404s, and the customer
master is not CRM `/accounts` either.

### AR entities (6)

| Entity | Endpoint | Canonical id | Display |
|---|---|---|---|
| ARInvoice | `/receivablesInvoices` | `CustomerTransactionId` | `TransactionNumber` |
| ARInvoiceLine | invoice `/child/receivablesInvoiceLines` | `CustomerTransactionLineId` | `LineNumber` |
| CreditMemo | `/receivablesCreditMemos` | `CustomerTransactionId` | `TransactionNumber` |
| StandardReceipt | `/standardReceipts` | `StandardReceiptId` | `ReceiptNumber` |
| CustomerAccount | `/receivablesCustomerAccountActivities` | `AccountId` | `CustomerName` |
| ARTaxLine | invoice-line `/child/receivablesInvoiceLineTaxLines` | (line PK + tax seq) | — |

**CustomerAccount is AR's customer entity.** No standalone customer master:
`/receivablesCustomers` does not exist, and CRM `/accounts` is a sales object
in a different id space. CustomerAccount carries `CustomerId`, `AccountNumber`,
`CustomerName`, and the two balance fields — everything the 18 prompts need
from "a customer".

CreditMemo and ARInvoice share one underlying object (`receivablesTransactions`,
split by `TransactionType`); model CreditMemo as its own entity but expect the
field catalog to mirror ARInvoice (negative `EnteredAmount`, `CreditMemoStatus`).

### AR edges

| Edge | From → To | Join | Mechanism |
|---|---|---|---|
| HAS_LINE | ARInvoice → ARInvoiceLine | `CustomerTransactionId` (path) | per-invoice child |
| HAS_TAX_LINE | ARInvoiceLine → ARTaxLine | invoice id + line id (path) | deep nested, 3 ids |
| HAS_ACCOUNT_CREDIT_MEMO | CustomerAccount → CreditMemo | `AccountId` (path) | per-account child |
| HAS_ACCOUNT_RECEIPT | CustomerAccount → StandardReceipt | `AccountId` (path) | per-account child |
| HAS_RECEIPT_APPLICATION | CustomerAccount → (application) | `AccountId` (path) | per-account child |

Customer identity links ARInvoice / CreditMemo / StandardReceipt to
CustomerAccount via `CustomerId` (numeric) / `AccountNumber` (string) — a
projection join, same shape as the supplier number/id asymmetry, encode
per-edge.

### Phase breakdown (confirmed)

- **AR-P2a** ✓ merged — ReceivablesInvoice by-id + lines (prompts 11, 12,
  2). Entities ReceivablesInvoice, ReceivablesInvoiceLine; edge HAS_AR_LINE.
  Single-path by-id (CustomerTransactionId); the invoice endpoint's customer
  name/number fields are NOT queryable (a customer's invoices go via the
  account path instead — see P2b). Prompts 11 and 12 collapse to one
  fetch-by-id tool.
- **AR-P2b** ✓ merged — a customer's invoices via account (prompt 15).
  Entities CustomerAccount, CustomerTransaction; edge
  HAS_CUSTOMER_TRANSACTION. Mechanism: resolve customer by name
  (CustomerName IS queryable on the account endpoint) → traverse the
  account's transactionPaymentSchedules, keep Invoice-class rows client-side
  (TransactionClass not queryable). Note these transaction rows are a
  distinct entity/id-space from ReceivablesInvoice (TransactionId vs
  CustomerTransactionId).
- **AR-P2c** (deferred, not started) — open invoices top-5 (prompt 1). Same
  account path as P2b plus an open-balance filter (TotalBalanceAmount > 0).
  Needs `open_only` wired as a filter-driven arg on the edge traversal — a
  mechanism the planner does not yet have. The P2b tools already carry the
  `open_only` flag (unused).
- **AR-P3** — invoice children: tax lines (prompt 3 — deep-nested grandchild,
  reuse the PO-distribution 3-id iteration pattern), DFF (prompt 4 — must pick
  between `receivablesInvoiceDFF` and `receivablesInvoiceTransactionDFF`; see
  quirk 8).
- **AR-P4** — credit memos: list + total value (prompts 5, 14).
- **AR-P5** — CustomerAccount + account children: activity/balance summary
  (prompt 6), account credit memos (7), account receipts (8), receipt
  applications (9), site-filtered receipts (13). All keyed by `AccountId`.
- **AR-P6** — aggregates (op-registry, exactly like PO's): exposure ranking
  (10, sort on `TotalOpenReceivablesForAccount` over 435 rows), cash-collection
  / DSO trends (16), receipt-method distribution (17, bucket `ReceiptMethod`),
  creation-to-update lag (18, `LastUpdateDate` − `CreationDate` per receipt).

### Open questions

**Resolved at P1:**
- *Customer entity?* → CustomerAccount (`/receivablesCustomerAccountActivities`).
  No separate master. CRM `/accounts` and `/receivablesCustomers` both ruled
  out with evidence (§9).
- *Aggregate shape?* → each is a bounded tool + op-registry entry +
  deterministic synthesizer shape, same as PO. All three have their source
  columns verified present on `/standardReceipts` (and account activities for
  10).

**Newly surfaced — carry into P6:**
- Prompt 16 (DSO) needs cash-in (`/standardReceipts`) AND AR balance (invoice
  `InvoiceBalanceAmount` or account `TotalOpenReceivablesForAccount`). Decide:
  one aggregate tool spanning two sources, or two composed tools. DSO =
  (AR balance / credit sales) × days — the balance and the receipts are
  different endpoints.
- Prompt 13 (Santa Clara receipts): confirm a Santa Clara receipt exists before
  locking a test anchor. The demo has an ABC-entity family — "ABC Corporation
  Americas" (invoice), "ABC Corporation Worldwide" (receipt), "ABC Application
  Software" (account) — across different sites; don't assume one resolves the
  prompt.

### Build order for AR-P2 (when P1 signed off)

Per the proven sequence: live curl (done) → standalone ARInvoice tool → KG
rows (ARInvoice entity + fields + fetch-by-id filter, rebuilt) → planner →
parser → server wrapper → tripwire bump (`print_kg.py`, `test_kg_metadata.py`)
→ tests → verify → branch `ar-phase-2-invoices` → PR → merge.

---

# Module 2: GL (General Ledger) — LATER

Source: Oracle Fusion GL MCP Functional Capability Document (v1.0). 21 tools
(17 read, 4 write). Note: Oracle exposes NO create (POST) on journal resources
— journal creation is Import Journals, not REST. GL columns are complete in
the catalog (PDF source).

**Shape — different from PO/AR.** GL is not entity-list shaped. Its core is
**balances by account combination / period / currency** (a finder query,
`ledgerBalances`) and **journal batches → headers → lines** (a hierarchy).
Plus a stack of LOVs (ledgers, periods, sources, categories, chart of
accounts, currencies) — reference lists that are simple reads. The
balance-by-combination query is a new pattern Spire hasn't built.

**Writes (4).** Update / delete-draft / post / reverse journal batches. These
are PATCH/DELETE on `journalBatches`. Whether Spire does GL writes is the same
write-safety question as AP (see below) — deferrable; the 17 reads are the
bulk of the value and can ship first.

## GL P1 — Dedupe + plan (not started)

**Goal:** plan GL's 17 reads (and decide on the 4 writes). Columns are already
captured, so no column-capture step — but the balance-finder and journal
hierarchy shapes need discovery.

**Candidate phase shape (to confirm at P1):**
- GL-P2: LOVs — ledgers, periods, period statuses, sources, categories, COA,
  currencies (prompts 1, 2, 4, 5, 6, 14, 15, 16, 17). Simple reads; a natural
  first phase.
- GL-P3: ledger balances — the finder query by account/period/currency
  (prompt 3). The new pattern; needs its own discovery.
- GL-P4: journals — batches → headers → lines hierarchy (prompts 7–13).
- GL-P5 (optional): journal writes — update / delete-draft / post / reverse
  (prompts 18–21). Gated on the write-safety decision.

**Open questions for P1:**
- The `ledgerBalances` finder: what parameters does it require, and does it fit
  the entity/filter routing or need something closer to the aggregation shape?
- Read-only first, or include the 4 journal writes? (Recommend read-only P2–P4,
  writes as a separate gated phase.)

---

# Module 3: AP (Accounts Payable) — LAST

Source: Oracle Fusion AP MCP Functional Capability Document. **75 tools**
(`ap_<action>_<object>`), ~18 resources across invoice-to-pay. Columns
complete in the catalog (PDF; 23 representative tools shown of 75).

**Why AP last — and why it needs a design phase.** AP is the biggest module
(75 tools) AND the only one dominated by **writes and actions**: create /
update / delete invoices, put/release holds, create suppliers, create
payments, stop payments, validate / cancel / apply-prepayment actions. Spire
has NEVER done a write — everything to date is read-only. Starting AP means
solving "how does Spire perform mutations safely" (confirmation, idempotency,
dry-run, auth scope, audit) — a whole new capability class — on top of a large
surface. Doing it last means the read patterns are solid first and the write
design gets its own focused attention.

## AP P1 — Dedupe + write-safety design + plan (not started)

**Goal:** plan AP's reads, and DESIGN the write/action capability before any
mutation ships. Two distinct pieces of work.

**Read planning (buildable like the others):**
- AP invoices — list + filter + detail + lines + distributions + installments
  (prompts 1, 2, 3, 10; resources `invoices`, `invoiceLines`,
  `invoiceDistributions`, `invoiceInstallments`).
- AP suppliers — list + sites (prompts 13, 15) — likely overlaps Spire's
  existing supplier coverage; DEDUPE carefully.
- AP payments — list + batches (prompts 16, 19).
- Expense reports (prompt 20).
- LOVs — suppliers, payment terms, business units (prompts 21, 22, 23).

**Write/action design (the gate):** the big open question. Does Spire do AP
writes at all? If yes:
- **Confirmation model** — how a mutation is proposed and confirmed before it
  fires (create invoice, create payment, stop payment are consequential).
- **Dry-run / preview** — can Spire show what would happen without doing it?
- **Idempotency** — retries must not double-create payments.
- **Auth scope & audit** — which persona may mutate; how it's logged.
- **The architecture question** — writes don't fit the read pipeline (parse →
  plan → execute → synthesize). A mutation isn't a query. This likely needs a
  new routing kind alongside entity/aggregation/comparison, with a
  human-in-the-loop confirmation step.

**Recommendation:** AP splits into a read module (buildable now, like the
others) and a write module (needs the design phase first). Ship AP reads;
treat AP writes as their own project with the design gate above.

**Open questions for P1:**
- Read-only AP first — how much overlaps Spire's existing supplier/invoice
  coverage (dedupe)?
- Does the product actually want write operations, or is AP read-only
  sufficient for the demo/customer? (This decision scopes the whole module.)

---

# Appendix: Endpoints Catalog

The raw endpoint and prompt tables for all four modules, preserved from
`spire_expansion_endpoints.md`. Reference material for planning each module.

- **Type** — Read · Aggregate (computes over data) · Write (POST/PATCH/DELETE)
  · Action (Oracle `/action/`).
- **Columns returned** — "— to fill" = output was in a source image not yet
  captured; complete from the originals during that module's P1.
- Base REST path for all: `/fscmRestApi/resources/11.13.18.05/`.

## Column-capture status

| Module | Source | Columns |
|---|---|---|
| AR | docx (images) | #1–6 captured; #7–18 to fill |
| GL | PDF | complete |
| AP | PDF | complete (23 representative of 75 tools) |
| PO | docx (images) | #2, 4, 7, 9, 11, 16, 25 captured; rest to fill |

## AR — Endpoints

| Resource | Tool | REST endpoint | Purpose |
|---|---|---|---|
| Account Activities | `list_customer_account_activities` | `/receivablesCustomerAccountActivities` | Account headers — balances, open receivables, due |
| › credit memos | `get_account_credit_memos` | `…/{accountId}/child/creditMemos` | Credit memos for one account |
| › standard receipts | `get_account_standard_receipts` | `…/{accountId}/child/standardReceipts` | Cash receipts for one account |
| › receipt applications | `get_account_standard_receipt_applications` | `…/{accountId}/child/standardReceiptApplications` | Applied vs unapplied |
| Credit Memos | `list_credit_memos` | `/receivablesCreditMemos` | Credit memos; supports q filter |
| › credit memo lines | `get_credit_memo_lines` | `/receivablesCreditMemos/{id}/child/receivablesCreditMemoLines` | Lines of one credit memo |
| Invoices | `get_invoice_lines` | `/receivablesInvoices` | AR invoices and billing lines |
| › invoice tax lines | `get_invoice_line_tax_lines` | `/receivablesInvoices/{id}/child/receivablesInvoiceLines/{lineId}/child/taxLines` | Tax per invoice line |
| › invoice DFF | `get_invoice_transaction_dff` | `/receivablesInvoices/{id}/child/invoiceDFF` | Flexfield segments |
| Customers | `receivables_customer` | `/receivablesCustomers` | Customer master |
| Transactions | `receivables_transaction` | `/receivablesTransactions` | AR billing transactions |
| Standard Receipts | `standard_receipt` | `/standardReceipts` | Cash receipts base object |
| › apply / unapply | `apply_receipt_to_invoice` / `unapply_receipt_application` | `/standardReceipts/{id}/child/receivableApplications` | Match cash to invoices |
| Misc Receipts | `misc_receipt` | `/miscReceipts` | Miscellaneous cash receipts |
| Receipt Methods | `receipt_method` | `/receiptMethods` | Receipt method config |

## AR — Prompts

| # | Prompt | Type | Endpoint (tool) | Columns returned |
|---|---|---|---|---|
| 1 | List all open invoices for the customer, top 5 | Read | `list_receivables_invoices` | Invoice #, Customer, Amount, Currency, Due Date, Status |
| 2 | Show invoice lines for invoice 300000248096352 | Read | `get_invoice_lines` | Line, Description, Quantity, Unit Price, Line Amount, Tax Handling |
| 3 | Get tax lines for that invoice line | Read | `get_invoice_line_tax_lines` | (0 tax lines found — none shown) |
| 4 | Fetch DFF values for this invoice | Read | `get_invoice_transaction_dff` | __FLEX_Context (=null here) |
| 5 | List recent credit memos, top 5 | Read | `list_credit_memos` | Memo #, Customer, Amount, Date, Status |
| 6 | Show account activity summary for top accounts | Read | `list_customer_account_activities` | Account, Customer, Open Receivables, Total Due |
| 7 | Get all credit memos for account 300000047368512 | Read | `get_account_credit_memos` | — to fill |
| 8 | Get all standard receipts for this account | Read | `get_account_standard_receipts` | — to fill |
| 9 | Trace receipt applications for this account | Read | `get_account_standard_receipt_applications` | — to fill |
| 10 | Rank the top accounts by outstanding exposure | Read | `list_customer_account_activities` | — to fill |
| 11 | Get the AR invoice with CustomerTransactionId 300000248096352 | Read | `get_invoice` | — to fill |
| 12 | Retrieve invoice details for CustomerTransactionId 300000248096352 | Read | `get_invoice` | — to fill |
| 13 | Get recent standard receipts for Santa Clara site | Read | `get_account_standard_receipts` | — to fill |
| 14 | Show the 5 most recent credit memos and their total value | Read | `list_credit_memos` | — to fill |
| 15 | Find invoices for ABC Corporation Americas | Read | `list_receivables_invoices` | — to fill |
| 16 | Identify cash collection trends, MoM, DSO, risks, improvements | Aggregate | `get_account_standard_receipts` | — to fill |
| 17 | Receipt method distribution — % of cash by method (Lockbox/ACH/Wire/Manual) | Aggregate | `get_account_standard_receipts` | — to fill |
| 18 | Lag between CreationDate and LastUpdateDate for each receipt | Aggregate | `get_account_standard_receipts` | — to fill |

## GL — Endpoints

| Resource | Methods | Purpose |
|---|---|---|
| `journalBatches` | GET / PATCH / DELETE | GL journal batch — read, update, delete drafts, post, reverse |
| `journalBatches/{id}/journalHeaders` | GET | Journals (headers) within a batch |
| `journalBatches/{id}/journalLines` | GET | Debit/credit lines within a journal |
| `ledgersLOV` | GET | Ledgers with currencies and IDs |
| `ledgerBalances` | GET | Account balances by combination/group, period, currency (finder) |
| `accountingPeriodsLOV` | GET | GL calendar periods — name, type, year |
| `accountingPeriodStatusLOV` | GET | Per-ledger period open/close status |
| `journalSourcesLOV` | GET | Valid journal source values |
| `journalCategoriesLOV` | GET | Valid journal category values |
| `chartOfAccountsLOV` | GET | Chart of accounts structures |
| `currenciesLOV` | GET | Enabled currencies and ISO codes |

## GL — Prompts

| # | Prompt | Type | Tool | Oracle API | Columns returned |
|---|---|---|---|---|---|
| 1 | Show all ledgers set up in our instance | Read | `gl_get_ledgers` | `ledgersLOV` | Ledger Name, Currency, Ledger ID |
| 2 | Get details for one ledger | Read | `gl_get_ledger_by_id` | `ledgersLOV/{id}` | Single ledger detail |
| 3 | Balance of account 101-10-1110 for Jun-26 in USD | Read | `gl_get_ledger_balances` | `ledgerBalances` | Account, Period, Currency, Balance amount |
| 4 | List accounting periods | Read | `gl_get_accounting_periods` | `accountingPeriodsLOV` | Period Name, Type, Year |
| 5 | Get one period by name | Read | `gl_get_accounting_period` | `accountingPeriodsLOV` | Single period row |
| 6 | Which periods are open for the US Primary Ledger? | Read | `gl_get_accounting_period_statuses` | `accountingPeriodStatusLOV` | Period Name, Status (Open/Closed) |
| 7 | List journal batches created this period | Read | `gl_get_journal_batches` | `journalBatches` | Batch Name, Status, Source, Period |
| 8 | Get one batch | Read | `gl_get_journal_batch_by_id` | `journalBatches/{id}` | Batch detail |
| 9 | Find all posted journals from the Manual source | Read | `gl_search_journals` | `journalBatches` | Filtered batch list |
| 10 | Show journals inside batch 100045 | Read | `gl_get_journals` | `…/journalHeaders` | Journal Name, Category, Currency |
| 11 | Get one journal | Read | `gl_get_journal_by_id` | `…/journalHeaders/{id}` | Journal header detail |
| 12 | Drill into the lines of that journal | Read | `gl_get_journal_lines` | `…/journalLines` | Account, Debit, Credit, Description |
| 13 | Get one line | Read | `gl_get_journal_line_by_id` | `…/journalLines/{id}` | Single line detail |
| 14 | What journal sources can we use? | Read | `gl_get_journal_sources` | `journalSourcesLOV` | Valid source values |
| 15 | What journal categories can we use? | Read | `gl_get_journal_categories` | `journalCategoriesLOV` | Valid category values |
| 16 | What chart of accounts structures do we have? | Read | `gl_get_chart_of_accounts` | `chartOfAccountsLOV` | COA structures with identifiers |
| 17 | List the currencies enabled | Read | `gl_get_currencies` | `currenciesLOV` | Currency codes & names |
| 18 | Update the completion status of batch 100045 | Write | `gl_update_journal_batch` | `journalBatches/{id}` PATCH | Updated batch confirmation |
| 19 | Delete draft batch 100060 | Write | `gl_delete_journal_batch` | `journalBatches/{id}` DELETE | Deletion confirmation |
| 20 | Post journal batch 100045 | Write | `gl_post_journal` | `journalBatches/{id}` PATCH `{Status:P}` | Posted batch confirmation |
| 21 | Reverse batch 100051 into Jul-26 | Write | `gl_reverse_journal` | `journalBatches/{id}` PATCH `{ReversalFlag:Y, ReversalPeriod}` | Reversal confirmation |

## AP — Endpoints

| Resource | Methods | Purpose |
|---|---|---|
| `invoices` | GET POST PATCH DELETE | Full lifecycle of AP invoices |
| `invoiceLines` | GET POST PATCH | Line-level detail within an invoice |
| `invoiceDistributions` | GET POST PATCH | How each line is charged to accounts |
| `invoiceInstallments` | GET PATCH | Payment schedules — due dates, amounts |
| `attachments` (invoice) | GET POST | Supporting files on invoices |
| `appliedPrepayments` / `availablePrepayments` | GET | Prepayments applied / available |
| `invoiceHolds` | GET POST PATCH | Place, review, release holds |
| `suppliers` | GET POST PATCH | Supplier master data |
| `suppliers/…/sites` | GET POST PATCH | Site-level purchasing and pay setup |
| `suppliers/…/addresses` | GET POST PATCH | Address records for a supplier |
| `suppliers/…/contacts` | GET POST PATCH | Contact people for a supplier |
| `payablesPayments` | GET POST PATCH | Create and manage supplier payments |
| `payablesPayments/…/relatedInvoices` | GET POST | Which invoices a payment settles |
| `paymentProcessRequests` | GET POST PATCH | Payment batches (PPR) |
| `expenseReports` | GET POST PATCH | Employee expense reports feeding AP |
| Invoice actions `/action/…` | POST | Validate, cancel, calculate tax, apply/unapply prepayment, generate/reverse distributions |
| Payment actions `/action/…` | POST | Stop payment, initiate escheatment |
| Reference lists (LOVs) | GET | Suppliers, payment terms, hold codes, business units, ledgers, legal entities, currencies |

## AP — Prompts

| # | Prompt | Type | Tool | Oracle API | Columns returned |
|---|---|---|---|---|---|
| 1 | Show all invoices created today | Read | `ap_list_invoices` | GET `invoices` | Invoice Number, Supplier, Amount, Currency, Status |
| 2 | List unpaid invoices over 10,000 for Vision Operations | Read | `ap_list_invoices` (filter) | GET `invoices?q=InvoiceStatus=Unpaid;InvoiceAmount>1000` | Invoice, Supplier, Amount, Due Date |
| 3 | Get details of invoice 300100123 | Read | `ap_get_invoice` | GET `invoices/{id}` | Full header: supplier, dates, amount, terms, status, business unit, description |
| 4 | Create an invoice | Write | `ap_create_invoice` | POST `invoices` | New invoice with its id |
| 5 | Update an invoice | Write | `ap_update_invoice` | PATCH `invoices/{id}` | Updated invoice fields |
| 6 | Delete an invoice | Write | `ap_delete_invoice` | DELETE `invoices/{id}` | Deletion confirmation |
| 7 | Validate invoice INV-1042 | Action | `ap_validate_invoice` | POST `…/validateInvoice` | Validation outcome |
| 8 | Cancel invoice INV-1099 | Action | `ap_cancel_invoice` | POST `…/cancelInvoice` | Cancellation result |
| 9 | Apply available prepayments to invoice 300100123 | Action | `ap_apply_prepayment` | POST `…/applyPrepayments` | Prepayment application result |
| 10 | Which invoices are on hold for Advanced Network Devices? | Read | `ap_list_invoice_holds` | GET `invoiceHolds` | Held invoices with hold name and reason |
| 11 | Put invoice 300100123 on hold | Write | `ap_create_invoice_hold` | POST `invoiceHolds` | New hold record with reference |
| 12 | Release the hold on invoice 300100123 | Write | `ap_update_invoice_hold` | PATCH `invoiceHolds/{id}` | Updated (released) hold |
| 13 | Show me 10 active suppliers | Read | `ap_list_suppliers` | GET `suppliers` | Supplier Name, Number, Type, Status |
| 14 | Create a new supplier called Globex Ltd | Write | `ap_create_supplier` | POST `suppliers` | New supplier number and id |
| 15 | What sites does supplier Acme have? | Read | `ap_list_supplier_sites` | GET `suppliers/…/sites` | Sites with procurement business unit and pay setup |
| 16 | List payments made this month | Read | `ap_list_payments` | GET `payablesPayments` | Payment Number, Supplier, Amount, Date, Status |
| 17 | Create a payment | Write | `ap_create_payment` | POST `payablesPayments` | New payment with its id |
| 18 | Stop payment on check 45012 | Action | `ap_stop_payment` | POST `…/initiateStopPayment` | Stop-payment confirmation |
| 19 | List payment batches | Read | `ap_list_payment_process_requests` | GET `paymentProcessRequests` | PPRs and status |
| 20 | List expense reports | Read | `ap_list_expense_reports` | GET `expenseReports` | Expense reports table |
| 21 | Supplier lookup | Read | `ap_lov_suppliers` | GET `suppliersLOV` | Matching suppliers with ids |
| 22 | What payment terms are available? | Read | `ap_lov_payment_terms` | GET `payablesPaymentTerms` | Payment terms (Net 30, Net 45) with ids |
| 23 | Business-unit lookup | Read | `ap_lov_business_units` | GET `finBusinessUnitsLOV` | Business units with ids |

_Full 75 AP tools follow `ap_<action>_<object>` across every resource above._

## PO — Endpoints & Prompts

The PO catalog is preserved here for completeness; the module is COMPLETE
(see Module 4 above).

| Resource | Endpoint |
|---|---|
| Purchase Orders | `/purchaseOrders` |
| PO Details | `/purchaseOrders/{POHeaderId}` |
| PO Lines | `/purchaseOrders/{POHeaderId}/child/lines` |
| PO Schedules | `/purchaseOrders/{POHeaderId}/child/lines/{POLineId}/child/schedules` (also flat `/purchaseOrderSchedules?q=POHeaderId=`) |
| PO Distributions | `…/schedules/{LineLocationId}/child/distributions` (nested only) |
| Suppliers | `/suppliers` |
| Supplier Sites | `/suppliers/{SupplierId}/child/sites` |
| Supplier Contacts | `/suppliers/{SupplierId}/child/contacts` |
| Invoices | `/invoices` |
| Receipt Requests | `/receivingReceiptRequests` |

PO prompts 1–25 and their build dispositions are captured in Module 4's P1
dedupe table above.
