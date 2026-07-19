# Spire — Architecture

*A KG-driven, bounded pipeline that answers natural-language procurement
questions against live Oracle Fusion.*

This is the living reference for what Spire is, why it is built the way it
is, its current coverage, and how to extend it. It consolidates the former
`spire_architecture_explainer.md` and `spire_integration_coverage.md`.
Design *decisions* (the options weighed to reach this architecture) live
separately in `spire_design_decisions.md`; the forward build plan lives in
`spire_expansion_plan.md`; pod-level endpoint truth lives in
`spire_fusion_endpoints_reference.md`.

Audience: technical reviewer and integration partner. Current-state counts
below come from `scripts/print_kg.py` and the tool list in
`src/spire/mcp_server/server.py` — run those for the authoritative numbers;
the figures here are a snapshot.

---

## 1. The one-line story

Spire turns a natural-language question from a Fusion consultant into a
correct, structured answer against a live Oracle Fusion pod — by confining
the LLM to two narrow roles and doing all Fusion logic deterministically.

---

## 2. The problem

Fusion's REST surface is large, quirky, and pod-specific. A single
consultant question maps to several endpoints across FSCM and HCM, with
join asymmetries and filters Fusion will not perform server-side.

Reference question:

> "Suppliers in the US with no invoices in the last 6 months but with
> open purchase orders, including the buyer."

Answering this correctly requires knowing things that are not obvious from
the API alone:

- Invoice references a supplier by `SupplierNumber`, but PurchaseOrder
  references the same supplier by `SupplierId`. Same supplier, two
  different keys.
- Buyer is not in FSCM at all. `BuyerId` on a PO equals `PersonId` on HCM
  `publicWorkers`. There is no `/buyers` endpoint on the pod.
- Composite `q=` filters are unreliable on this pod, so you must
  over-fetch and filter client-side.
- "No invoices in 6 months" is negation-by-absence — the answer is the
  *empty* result, which naive tool-calling routinely mishandles.

---

## 3. Why traditional tool-calling (an agent) is the wrong fit

An agent hands the LLM a pile of tools and lets it reason live about which
to call and in what order. On a surface like Fusion this fails in
predictable ways:

1. It guesses join keys it cannot know (the SupplierId vs SupplierNumber
   asymmetry).
2. It hunts for endpoints that do not exist (a FSCM `/buyers`).
3. It trusts the API and does not know pod quirks (composite `q=`).
4. It mishandles "absence is the signal" cases.
5. It loops, picks wrong tools, and fails *unattributably* — when the
   answer is wrong you cannot say which step broke.
6. **Selection degrades as the tool catalog grows.** With a handful of
   tools an LLM can usually pick correctly. As the count climbs into the
   dozens, selection accuracy drops — the model misroutes, picks
   near-duplicate tools, or stalls. Spire sidesteps this: the planner
   routes to tools deterministically from the KG, so adding endpoints does
   not degrade selection. (Spire is now at 19 tools and rising — exactly
   the regime where an agent's selection would start to fray.)

This is not hypothetical. An agent baseline was built specifically as the
comparison arm to test this. The bounded design was then committed
deliberately — an engineering decision backed by the comparison, not an
assumption.

### Traditional tool-calling vs Spire

| Dimension | Traditional tool-calling | Spire |
|---|---|---|
| What the LLM sees | Tool catalog: names, descriptions, arg schemas | Domain model: entities, fields, edges, vocabulary, patterns |
| What the LLM is asked | "Which tool do I call, with what args?" | "What does this question mean?" |
| Nature of the task | Routing decision (selection) | Comprehension (interpretation) |
| LLM output | A tool call (or a chain of them) | A structured Intent — entities/edges/filters, no tools |
| Where tool selection happens | Inside the LLM, at generation time | In the planner — deterministic code, by KG table lookup |
| Determinism | Non-deterministic; same prompt can pick different tools | Deterministic; same Intent always selects the same tools |
| Effect of more tools | Selection accuracy degrades as the catalog grows | Lookup table grows; no added LLM reasoning load |
| Failure mode | Wrong tool, looping, unattributable | Attributable to a stage (parse vs plan vs execute) |
| Join-key / pod-quirk knowledge | LLM must infer it from tool descriptions | Encoded once in the KG; code applies it |

The crux: traditional tool-calling asks the LLM *which function to call*;
Spire asks the LLM *what the question means*, and lets deterministic code
select the tools. The first is a routing decision made at generation time;
the second is a comprehension task, which LLMs do far more reliably.

---

## 4. The architecture: a bounded pipeline

![Spire bounded pipeline architecture](images/spire_pipeline_architecture.png)

```
NL prompt → 1·Parse (LLM) → 2·Plan (code) → 3·Execute (code) → 4·Synthesize (LLM) → answer or refusal
```

The LLM appears only at the two ends. The middle is deterministic. Each
stage:

**1 · Parse (LLM).** Reads the prompt and produces a structured Intent.
This is the only place language is interpreted. It is bounded by the KG:
it may only use entities and fields the KG defines, and it resolves the
user's words through the KG Vocabulary — mapping business terms to
canonical values ("vendor" → Supplier, "open" → "OPEN", "US" → the country
code).

**2 · Plan (deterministic).** Plain code turns the Intent into ordered
steps: which entity to fetch, which filters to apply, which joins to
follow. The same Intent always yields the same plan.

**3 · Execute (deterministic).** Plain code runs each step by calling
Fusion through MCP tools, applying filters client-side where the pod
requires it. This is the only stage that touches the network.

**4 · Synthesize (LLM).** Phrases the raw results into a readable answer.
A hallucination guard cross-validates every ID in the response against the
executor's source data; an invented ID raises `HallucinationError`. Output
is a Pydantic-typed structured response. (Aggregations and comparisons
skip the LLM here entirely — their tools already computed every number, so
the response is templated deterministically; see §6.)

**Output.** A structured, verifiable answer — or an honest refusal if the
prompt falls outside the KG's scope. Refusal is a designed outcome, not a
failure.

---

## 5. What the Knowledge Graph does

The KG is metadata stored in Oracle tables. It is the institutional
knowledge a senior consultant holds in their head, made machine-readable.
It encodes:

- **Entities and fields** — the query targets and their attributes.
- **Edges** — how entities join, including the join keys and their
  asymmetries (SupplierNumber vs SupplierId), and the cross-pillar hop
  (PO → Buyer via BuyerId → PersonId on HCM).
- **Vocabulary** — business terms mapped to canonical Fusion codes.
- **Patterns** — reusable query shapes (e.g. "no child of type C in the
  last N months").
- **Tool bindings** — which MCP tool realizes each filter or traversal.

The LLM never improvises Fusion mechanics. It picks from what the KG
already knows to be true.

**The KG holds metadata, never instance data.** Zero rows of supplier,
invoice, PO, or buyer data live in it — every factual answer is a live
Fusion call. The KG is the *map*; Fusion is the *territory*. It changes
when the Fusion schema changes (new endpoint, renamed field, new
relationship), not when Fusion data changes. So it never goes stale
relative to the pod. (The full metadata-not-data rationale is in
`spire_design_decisions.md`.)

---

## 6. Three routing kinds

Every parsed Intent is routed one of three ways. Which one a prompt needs
decides what a new capability wires into.

1. **Entity/filter queries** (list, detail, child traversal) route through
   the **KG tables** — `kg_entity`, `kg_entity_filter`, `kg_edge`, and the
   tool-binding tables. Adding one means KG rows + a rebuild + tripwire
   bumps. This is the bulk of Spire.
2. **Aggregations** (rank, count, sum) route through the planner's
   **aggregation op-registry** (`_AGGREGATION_TOOLS` / `_AGGREGATION_PARAMS`),
   via an `aggregate` block on the Intent — NOT the KG. The grouping and
   measure are fixed by identity (a different grouping/measure is a
   different tool, never a flag), which keeps the aggregation layer a set
   of bounded tools rather than a generic engine.
3. **Comparisons** (invoiced-vs-ordered, two-source joins) route through
   the **comparison op-registry** (`_COMPARISON_TOOLS` / `_COMPARISON_PARAMS`),
   via a `compare` block — NOT the KG. Same discipline as aggregation.

Aggregation and comparison both bypass the KG (their Intents carry no
target entity) and both skip entity validation; the parser has a
"do NOT refuse" instruction block for each. Their synthesizer output is
deterministic — the tool computes every figure, the responder templates
it, the LLM does no arithmetic (it is unreliable at it).

---

## 7. With KG vs without KG

**Without (a traditional agent).** The LLM sees a prompt plus a pile of
tools, reasons live, guesses keys, may loop, and fails silently. When
wrong, the failure is not attributable to any one place.

**With (Spire).** The LLM only *interprets* the prompt into a
KG-constrained Intent, and later *phrases* the guarded answer.
Deterministic code does the planning and the Fusion calls in between.
Every failure is attributable to a specific stage — parse, plan, execute,
or synthesize.
---

## 8. Current scope (what works today)

*Snapshot; authoritative counts come from `scripts/print_kg.py` and
`server.py`. As of this writing: 11 entities, 84 fields, 10 edges, 19
filters, 81 vocabulary rows, 3 patterns, 5 entity-fetch tool bindings, 9
edge-traversal tool bindings, and 19 MCP tools.*

**Query targets (entities that can root a query):** Supplier, PurchaseOrder,
Invoice, and Address. Buyer, Contact, Site, Classification,
PurchaseOrderLine, POSchedule, and PODistribution are include-only — reached
by traversing an edge from a rooted query, not queried directly.

The early scope (Supplier-only, Invoice/PO prompts refused) is long
superseded. What works now:

- **Supplier** — list and filter by status, country, name fragment,
  business relationship, creation date; and by edge-traversal filters:
  has an open PO, has no recent invoices, has an invoice over an amount,
  has a site in a business unit, has a business classification.
- **PurchaseOrder** — list (by supplier, status, or creation-date bound),
  fetch one by id (resolving OrderNumber OR POHeaderId), and traverse to its
  lines, schedules, and distributions.
- **Invoice** — list by supplier, by date, or by PO (`PurchaseOrderNumber`).
- **Address / Site / Classification / Contact** — as supplier children.
- **Buyer** — the cross-pillar hop from a PO (`BuyerId` → HCM
  `publicWorkers.PersonId`).
- **Aggregations** — top suppliers by invoice spend; top suppliers by PO
  value; PO count + value by status; open-PO committed-spend summary.
- **Comparisons** — invoiced-vs-ordered for one PO, one supplier, or the
  top-N suppliers by PO value.
- **Received-vs-ordered** — from PO schedule received/billed fields.
- **Projection** — return only requested columns (KG-field-driven).
- **Count** — "how many X" answered as a count, not a list.

**Pillars:** FSCM confirmed end-to-end. HCM reachable in principle (Buyer
via `publicWorkers`) but HCM access on the dev pod is not yet granted (see
§10).

**Refusal is a feature.** Out-of-scope prompts (an entity or filter the KG
doesn't model, an unbounded query, a relative-date PO window) yield a typed
refusal that names what's missing, rather than a wrong-but-plausible answer.

Live pod: `fa-esll-dev37`.

---

## 9. Integration coverage

### Endpoints

Spire integrates these Oracle Fusion REST endpoints. Base paths:
`/fscmRestApi/resources/11.13.18.05/` (FSCM),
`/hcmRestApi/resources/11.13.18.05/` (HCM).

| Module | Endpoint | Type |
|---|---|---|
| Procurement | `/suppliers` | base |
| Procurement | `/suppliers/{id}/child/addresses` | child |
| Procurement | `/suppliers/{id}/child/sites` | child |
| Procurement | `/suppliers/{id}/child/businessClassifications` | child |
| Procurement | `/suppliers/{id}/child/contacts` | child |
| Procurement | `/purchaseOrders` | base |
| Procurement | `/purchaseOrders/{id}` | base (single-record) |
| Procurement | `/purchaseOrders/{id}/child/lines` | child |
| Procurement | `/purchaseOrderSchedules` | base (flat, `q=POHeaderId=`) |
| Procurement | `…/lines/{id}/child/schedules/{id}/child/distributions` | deep nested |
| Payables | `/invoices` | base |
| HCM Workforce | `/publicWorkers` | base |

Received-vs-ordered reads from `/purchaseOrderSchedules` (the receipts
resources — `receivingTransactions`, `receivingReceipts`,
`receivingReceiptRequests` — are unusable on this pod; see the endpoints
reference).

### MCP tools (19)

Entity fetchers and traversals: `search_suppliers`, `search_invoices`,
`search_addresses`, `search_purchase_orders`, `search_suppliers_by_site_bu`,
`search_suppliers_by_classification`, `get_buyer`, `get_purchase_order_by_id`,
`get_purchase_order_lines`, `get_purchase_order_schedules`,
`get_supplier_contacts`, `get_purchase_order_distributions`.

Aggregations: `aggregate_invoices_by_supplier`,
`aggregate_purchase_orders_by_supplier`, `aggregate_purchase_orders_by_status`,
`summarize_open_purchase_orders`.

Comparisons: `compare_purchase_order_to_invoices`,
`compare_supplier_orders_to_invoices`,
`compare_top_suppliers_orders_to_invoices`.

### Query coverage

The parser maps free-form English onto supported filters, so phrasing is
flexible. Representative prompts, one per capability area:

- List active / inactive suppliers; US suppliers; suppliers in the UK
- Suppliers named Lee; prospective suppliers; suppliers created between
  Jan and Mar 2025
- Suppliers with a site in the France business unit; woman-owned suppliers;
  suppliers that are small business
- Suppliers with open purchase orders; suppliers with invoices over 10000
- How many suppliers do we have (count)
- Top 10 suppliers by spend in 2022; top 5 suppliers by purchase order value
- How many purchase orders are there and what are they worth (by status)
- How much have we committed in open purchase orders
- Invoices for supplier 1252; invoices for Lee Supplies in 2023
- Addresses for supplier 1252; suppliers with their addresses
- Show PO 2144 and its lines / schedules / distributions
- How much of PO 2144 was received; which invoices were raised against a PO
- Show supplier EIP Inc and its contacts
- Purchase orders created before 2015
- How does invoiced compare to ordered for PO 162034 / for our top suppliers

### Output columns

Each query returns a curated default column set, and Spire can also return
**specific columns on request** (e.g. "show only supplier name and status",
"invoice number and amount for supplier 1252"). Column sets are reviewed by
running the review prompt set (`scripts/spire_v1.2_review_prompts.txt`) and
aligning the default and requested sets to what reviewers expect per prompt.

---

## 10. Extending into HCM — what's needed from the integration partner

Spire was originally built from endpoint signatures alone; the edges,
vocabulary, and patterns were derived from them plus a target question.
Adding a new HCM domain (for example, "retrieve paystubs per employee")
follows the same path, and needs three things:

1. **HCM access on the dev pod.** A 401 was hit on HCM endpoints — the
   existing credentials cover FSCM scope but not HCM. This is a
   credential/scope grant, not a code change.
2. **Endpoint truth for the new domain.** Confirm the real join keys and
   filterable fields — e.g. whether a payslip keys on `PersonId` or
   `PayrollRelationshipId`. These asymmetries are the whole game.
3. **The security model.** Whether cross-employee payslip retrieval is
   reachable via REST at all, or gated to self-service. A couple of real
   target prompts will surface this quickly.

Given those, the KG additions (entities, edges, vocabulary, patterns, tool
bindings) and the matching MCP tools are mechanical to produce.

---

## 11. The line that matters for a reviewer

The bounded-beats-agent claim was not asserted — an agent baseline was
built as a comparison arm, then the bounded design was committed. The LLM
is confined so that every failure is attributable to one stage. That is an
engineering argument, not a marketing one.
