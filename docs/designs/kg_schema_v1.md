# Knowledge Graph Schema v1

**Phase:** Dynamic Orchestration 01 — KG Schema Design (rev. 2026-05-18 during phase 03)
**Status:** Design document — no implementation
**Scope:** Single document. Minimal viable KG for the POC. Companion to `spire_design_alternatives.md` and `../spire_poc_master_plan.md`.

This document defines *what* the KG models and *why*. It deliberately does not specify how the KG is stored (Dynamic Orchestration 03 picks the DDL shape), what tools the agent calls to query it (Dynamic Orchestration 04), or how embeddings interact with it (Dynamic Orchestration 06).

**Revision note (during phase 03):** The first version of this doc was unclear on one critical point — whether the KG stores instances of Fusion business data, or only structural metadata about how Fusion data is organized. This revision makes the answer explicit: **metadata only, never instance data.** Wording throughout has been adjusted to remove ambiguity. The entity set, edge set, pattern set, and lookup set are unchanged from the original draft, except that Country has been recategorized from "entity" to "vocabulary" (it never had an endpoint or instances anyway).

---

## 1. What the KG Is, and What It Is Not

### What the KG is

The Spire KG holds **structural knowledge about Fusion** — not Fusion data itself.

Concretely, the KG stores:

- **Entity declarations** — "there exists a concept called Supplier; it is materialized by the endpoint `/fscmRestApi/.../suppliers`; its canonical identifier is `SupplierId`."
- **Relationship declarations** — "Supplier relates to PurchaseOrder via the edge `HAS_PURCHASE_ORDER`; the join key is `SupplierId`; to traverse the edge, query `/purchaseOrders?q=SupplierId=X`."
- **Endpoint metadata** — supported filter fields, projection fields, known quirks (composite-`q=` reliability, child-resource requirements).
- **Query patterns** — reusable logical shapes like `no_Y_in_N_months`, with the steps and parameters needed to realize them.
- **Vocabulary tables** — business terms mapped to Fusion codes ("US" → `'US'`, "open" → `'OPEN'`, "vendor" → Supplier).

### What the KG is not

The KG does **not** store:

- Rows of supplier data, invoice data, PO data, or buyer data.
- Snapshots, samples, ETL'd copies, or cached extracts of Fusion records.
- Anything that could go stale relative to the live Fusion pod.

Every factual question the agent answers — "which suppliers are in the US?", "does supplier X have invoices in the last 6 months?", "who is the buyer for this PO?" — is answered by a **live call to Fusion**. The KG is the *map*; Fusion is the *territory*.

### Why this distinction matters

The KG is the navigation layer above Fusion, not a parallel data store. Two consequences:

- **The KG never needs to be refreshed.** It changes when the Fusion *schema* changes (new endpoint, renamed field, new relationship), not when Fusion *data* changes (new supplier added, invoice paid, PO closed).
- **Staleness is not a concern.** A KG that's a year old still tells the agent how to fetch today's data — because endpoints, join keys, and business vocabulary change far less than the underlying records do.

### What this means in scale

A v1 KG populated with everything in this document fits in **a few dozen rows total**: ~5 entities, ~4 edges, ~5 endpoint records, ~4 patterns, ~50 vocabulary entries. Not pod-data-sized. Schema-sized.

---

## 2. Purpose and Scope Boundaries

### Why a KG at all

Track A's baseline (1/7 on the reference prompt — see `../phase_a5_baseline_report.md`) showed two specific failure modes:

1. **Premature termination.** Agent calls one tool and stops, because nothing in its context tells it that "country → supplier → invoice → PO → buyer" is a multi-hop traversal it must complete.
2. **Parameter confusion across tools.** Agent called `search_purchase_orders(supplier_number='1252')` — `supplier_number` exists on `search_invoices` but not on `search_purchase_orders`. The relationship "supplier identifies a PO" is encoded three different ways across three tools, and docstrings alone weren't enough to keep them straight.

The KG addresses both. It encodes:

- **The traversal structure** — Supplier connects to PO via SupplierId; PO connects to Buyer via BuyerId; etc. The agent reads this from the KG, not from docstring archaeology.
- **The vocabulary** — what "open PO" means in Fusion codes; what "US" maps to in CountryCode; what "buyer" is in HCM terms.
- **Reusable reasoning patterns** — "no Y in N months" is a logic shape that recurs (no invoices, no payments, no orders); encoding it once means the agent looks it up rather than re-derives it.

### Scope boundaries — what v1 IS

- **Minimal entity set** sufficient to support the POC reference prompt:
  > *Show me suppliers in US with no invoices in 6 months but with open purchase orders, including the buyer assigned to each.*
- **Metadata-only KG** — see §1.
- **Static schema** — entities, relationships, patterns, and lookups defined in this document.
- **Single-tenant** — one customer, one pod, one persona.
- **Read-only** — the KG describes how to read from Fusion. It does not model writes.

### Scope boundaries — what v1 is NOT

Explicitly excluded so later phases don't drift:

- **Not a complete Fusion model.** Fusion has hundreds of entities; v1 has five entities. The point is to test the hypothesis, not to model the world.
- **No instance business data.** Restated from §1 because it bears repeating: the KG holds no rows of supplier, invoice, PO, or buyer data. (See §7 for the full non-goals list.)
- **No per-tenant overlays.** Customer-specific DFFs, custom value sets, and custom business rules are post-POC concerns. The KG schema *can* be extended to support tenant-scoped overlays later; v1 doesn't model them.
- **No write operations.**
- **No multi-pod federation.** One pod, one persona.
- **No historical / temporal modeling.** The KG describes current Fusion structure, not record histories or audit trails.

### Success criterion for v1

The KG is sufficient if, after Dynamic Orchestration 03–08 build it out and integrate it, an agent that consults the KG can score meaningfully higher than 1/7 on the reference prompt under the same rubric. If it scores 1/7 again, either the KG is too thin, the integration is wrong, or the hypothesis is wrong — and that's signal the POC needs to capture, not paper over.

---

## 3. Entity Model

Five entities. Each section is a *declaration* — a record the KG holds about that entity type, not a row of business data. Each declaration specifies: what the entity represents, the canonical identifier the KG uses to refer to it, what attributes the entity *has* (so the agent knows what to project and filter on), and which Fusion endpoint materializes the entity.

A note on attributes: the KG declares which fields *exist* on each entity, but does not store values. When the agent needs an actual supplier record, it calls Fusion and Fusion returns the live values. The KG's attribute list is closer to a small projection contract — "when you fetch a Supplier, expect at least these fields back" — than to a database schema.

### 3.1 Supplier

Represents a vendor or service provider in Fusion's supplier master.

| Aspect | Value |
|---|---|
| Canonical identifier | `SupplierId` (numeric) |
| Display identifier | `SupplierNumber` (string, e.g. `"1252"`) |
| Display name field | `Supplier` (string, e.g. `"Lee Supplies"`) |
| Status field | `Status` (string, e.g. `"ACTIVE"`) |
| Materialized by | `GET /fscmRestApi/resources/11.13.18.05/suppliers` |
| Country accessed via | `GET /fscmRestApi/.../suppliers?expand=addresses` (country lives on child Address; see §4.2) |

**Why `SupplierId` is canonical:** It's the join key across PO, invoice, and address. `SupplierNumber` is human-readable but is a string and can drift across pods; `SupplierId` is the system primary key.

### 3.2 Invoice

Represents an accounts-payable invoice tied to a supplier.

| Aspect | Value |
|---|---|
| Canonical identifier | `InvoiceId` (numeric) |
| Display identifier | `InvoiceNumber` (string) |
| Date field | `InvoiceDate` (ISO date string) |
| Amount fields | `InvoiceAmount` (numeric) + `InvoiceCurrency` (string) |
| Status fields | `PaidStatus`, `ApprovalStatus` |
| Supplier reference field | `SupplierNumber` (string) — note: not `SupplierId` on this endpoint |
| Materialized by | `GET /fscmRestApi/resources/11.13.18.05/invoices` |

**Note on the supplier reference asymmetry:** The invoices endpoint exposes `SupplierNumber` but not `SupplierId`. The PO endpoint exposes `SupplierId` but not `SupplierNumber`. This is the asymmetry that caused the Track A parameter confusion. §4.1 documents the implications.

### 3.3 PurchaseOrder

Represents a purchase order issued to a supplier and assigned to a buyer.

| Aspect | Value |
|---|---|
| Canonical identifier | `POHeaderId` (numeric) |
| Display identifier | `OrderNumber` (string) |
| Status field | `StatusCode` (string; values include `"OPEN"`, `"CLOSED"`, `"INCOMPLETE"`, `"CANCELED"`) |
| Status display field | `Status` (human-readable, e.g. `"Open"`) |
| Supplier reference field | `SupplierId` (numeric) |
| Buyer reference field | `BuyerId` (numeric) |
| Amount fields | `Ordered` (numeric) + `CurrencyCode` (string) |
| Materialized by | `GET /fscmRestApi/resources/11.13.18.05/purchaseOrders` |

### 3.4 Buyer

Represents the purchasing agent assigned to a PO. **Critical detail: buyers are HCM workers, not FSCM entities.** There is no `/fscmRestApi/.../buyers` endpoint on this pod (see `../phase_a5_baseline_report.md` and the A.4.3 log entry).

| Aspect | Value |
|---|---|
| Canonical identifier | `PersonId` (numeric) — same value as `BuyerId` on a PO |
| Display name field | `DisplayName` (string, e.g. `"Calvin Roth"`) |
| Email field | `WorkEmail` |
| Username field | `Username` |
| Person number | `PersonNumber` |
| Materialized by | `GET /hcmRestApi/resources/11.13.18.05/publicWorkers` |

**Cross-pillar implication:** Supplier → Invoice and Supplier → PO live in FSCM. PO → Buyer crosses into HCM. This is one of the most important things the KG encodes; without it, the agent has no reason to know it should switch pillars.

### 3.5 Address

Represents a supplier's address. Modeled as a separate entity (rather than collapsed into Supplier attributes) because a supplier can have multiple addresses in multiple countries.

| Aspect | Value |
|---|---|
| Canonical identifier | Not exposed as a top-level resource on this pod — addresses are child records of Supplier |
| Country fields | `CountryCode` (ISO-2, e.g. `"US"`), `Country` (full name, e.g. `"United States"`) |
| Other fields | (street, city, etc. — not modeled in v1) |
| Materialized by | `GET /fscmRestApi/.../suppliers?expand=addresses` (as `supplier.addresses[]`) |

**Why separate from Supplier:** Folding country into Supplier attributes would model "a supplier has *a* country," which is incorrect. A supplier can have addresses in many countries; the question "is this supplier *in* country X" means "does this supplier have *any* address in country X." That distinction matters for the reference prompt.

### Note on Country

Country was modeled as an "entity" in the first revision of this doc. On reflection, it's not an entity in the same sense as Supplier or Invoice — there's no Country endpoint we fetch instances from, no country records to traverse to. Country is a **vocabulary table**: a mapping from natural-language country terms to Fusion codes. It now lives in §5 (Vocabulary), not here.

---

## 4. Relationship Model

Four typed edges. Each specifies: semantic meaning, the join mechanic in Fusion, and the endpoint traversal hint (which Fusion query realizes the edge at runtime).

The KG's job in this section is to make explicit what Track A asked the LLM to infer from docstrings. If the agent needs to go from Supplier to Buyer, it should read the path from the KG — it should not have to derive `Supplier → PO → Buyer (via BuyerId → PersonId on publicWorkers)` from natural-language tool descriptions.

These edges are KG declarations, not instance edges. There is no row in the KG saying "supplier #1252 has invoice #X" — that's instance data and lives in Fusion. The KG declares the edge type once and how to traverse it; the agent applies the declaration to instances retrieved live from Fusion.

### 4.1 Supplier → Invoice (`HAS_INVOICE`)

**Semantic meaning:** A supplier has zero or more invoices.

**Join mechanic:** `Supplier.SupplierNumber == Invoice.SupplierNumber` (string equality).

**Important caveat:** The invoices endpoint exposes `SupplierNumber`, not `SupplierId`. So even though `SupplierId` is the canonical supplier identifier in the KG, traversal via this edge uses `SupplierNumber` at the Fusion query layer. The KG schema must make this explicit; otherwise the agent will repeat the Track A mistake of passing `SupplierId` where `SupplierNumber` is expected.

**Endpoint traversal hint:** Given a Supplier, the agent calls:
```
GET /invoices?q=SupplierNumber='{supplier.SupplierNumber}'
```
…optionally with additional filters (date, etc.). Composite `q=` clauses against this endpoint are unreliable on this pod (see `../phase_a5_baseline_report.md` and the A.4.1 log entry); additional filters are applied client-side after over-fetch.

**Cardinality:** One-to-many. A supplier can have many invoices; an invoice has exactly one supplier.

### 4.2 Supplier → Address (`HAS_ADDRESS`)

**Semantic meaning:** A supplier has one or more addresses. Each address belongs to a country.

**Join mechanic:** Address is a child resource of Supplier. There is no standalone Address endpoint to query independently; addresses come back inside a Supplier record when `expand=addresses` is set.

**Endpoint traversal hint:** Given a Supplier or a search for Suppliers, the agent calls:
```
GET /suppliers?expand=addresses
```
The address records appear inline as `supplier.addresses[]`. Country filtering is client-side (see §4.3 for why).

**Cardinality:** One-to-many. A supplier has at least one address (typically); each address belongs to exactly one supplier.

### 4.3 Address → Country attribute (no `LOCATED_IN` edge)

**Revision note:** The first version of this doc modeled `Address LOCATED_IN Country` as an edge. With Country recategorized as vocabulary (not an entity), it's not an edge between two entities anymore. It's now a *filter*: "filter addresses by their CountryCode/Country field, using the vocabulary table to map the user's term to the right code."

**How the agent uses it:**
- User says "in the US"
- Agent consults the Country vocabulary table (§5.1) to map `"US"` to `CountryCode='US'`
- Agent fetches suppliers with addresses expanded, then client-side filters addresses where `CountryCode='US'`

**A subtlety the KG still encodes:** Saying "supplier S is in country C" means "supplier S has *at least one* address in country C," not "all of supplier S's addresses are in country C." A supplier with offices in the US and UK is *in* the US *and* in the UK — both, simultaneously, for the purposes of any country-filter prompt.

### 4.4 Supplier → PurchaseOrder (`HAS_PURCHASE_ORDER`)

**Semantic meaning:** A supplier has zero or more purchase orders.

**Join mechanic:** `Supplier.SupplierId == PurchaseOrder.SupplierId` (numeric equality). Note: `SupplierId`, *not* `SupplierNumber`. This is the asymmetry with §4.1.

**Endpoint traversal hint:** Given a Supplier, the agent calls:
```
GET /purchaseOrders?q=SupplierId={supplier.SupplierId}
```
…optionally with status filter. Composite `q=` clauses are unreliable; status is applied client-side after over-fetch.

**Cardinality:** One-to-many. A supplier can have many POs; a PO has exactly one supplier.

### 4.5 PurchaseOrder → Buyer (`ASSIGNED_TO`)

**Semantic meaning:** A purchase order is assigned to exactly one buyer.

**Join mechanic:** `PurchaseOrder.BuyerId == Buyer.PersonId` (numeric equality). **This crosses pillars** — the PO is in FSCM, the buyer is in HCM.

**Endpoint traversal hint:** Given a PO, the agent calls:
```
GET /hcmRestApi/resources/11.13.18.05/publicWorkers?q=PersonId={po.BuyerId}
```
This is the single most important relationship the KG encodes that docstrings alone failed to convey in Track A — there is no `/fscmRestApi/.../buyers` endpoint on this pod, and the cross-pillar nature is not obvious from any tool name.

**Cardinality:** Many-to-one. Many POs can share a buyer; each PO has exactly one buyer.

### Relationship summary

| Edge | From | To | Join key | Endpoint hint |
|---|---|---|---|---|
| `HAS_INVOICE` | Supplier | Invoice | `SupplierNumber` (string) | `GET /invoices?q=SupplierNumber='X'` |
| `HAS_ADDRESS` | Supplier | Address | child via `expand=addresses` | `GET /suppliers?expand=addresses` |
| `HAS_PURCHASE_ORDER` | Supplier | PurchaseOrder | `SupplierId` (numeric) | `GET /purchaseOrders?q=SupplierId=X` |
| `ASSIGNED_TO` | PurchaseOrder | Buyer | `BuyerId` → `PersonId` | `GET /publicWorkers?q=PersonId=X` (HCM) |

(Note: only four edges; the former `LOCATED_IN` is now a vocabulary lookup, not an edge.)

---

## 5. Vocabulary Tables

Two kinds of metadata in the KG (§1):

- **Entity declarations** — §3 and §4 above; "where does this concept come from in Fusion?"
- **Vocabulary tables** — this section; "what does this business term mean in Fusion?"

Vocabulary tables are simple lookups. The agent consults them at planning time to translate the user's words into Fusion codes and identifiers.

### 5.1 Country

Mapping between business names, alternate forms, and ISO-2 codes. v1 includes the countries most likely to appear in POC prompts; extending is one-row-per-country.

| Business term(s) | ISO-2 code | Full name |
|---|---|---|
| `"US"`, `"USA"`, `"United States"`, `"United States of America"` | `US` | United States |
| `"UK"`, `"United Kingdom"`, `"Britain"`, `"Great Britain"`, `"GB"` | `GB` | United Kingdom |
| `"India"`, `"IN"` | `IN` | India |
| `"Canada"`, `"CA"` | `CA` | Canada |
| `"Australia"`, `"AU"`, `"AUS"` | `AU` | Australia |

**Note on the existing `search_suppliers_by_country` tool:** It already accepts ISO-2 codes and full names but explicitly does not accept three-letter codes like `"USA"` (it returns empty — see `tests/test_suppliers_by_country_tool.py`). The KG lookup *can* normalize `"USA"` to `"US"` before invoking the tool; that's a planned improvement on the existing tool's behavior, made possible by having the KG as an intermediary.

### 5.2 PO Status

| Business term | StatusCode |
|---|---|
| `"open"`, `"active"` | `OPEN` |
| `"closed"`, `"completed"` | `CLOSED` |
| `"incomplete"`, `"draft"` | `INCOMPLETE` |
| `"canceled"`, `"cancelled"` | `CANCELED` |

Other PO statuses exist in Fusion (`FROZEN`, `ON_HOLD`, etc.) — they are not modeled in v1 because the reference prompt doesn't exercise them.

### 5.3 Entity Synonyms

Maps the words a consultant would say to the canonical entity name.

| Business term | Entity |
|---|---|
| `"supplier"`, `"vendor"` | Supplier |
| `"invoice"`, `"bill"` | Invoice |
| `"purchase order"`, `"PO"`, `"order"` | PurchaseOrder |
| `"buyer"`, `"purchasing agent"`, `"agent"` | Buyer |

This list is short on purpose. The point is to disambiguate the highest-frequency synonyms, not to build a thesaurus.

### 5.4 Relationship Phrases

Maps natural-language phrases to KG edges.

| Phrase pattern | Edge |
|---|---|
| `"<supplier> has <invoice>"`, `"<invoice> for <supplier>"` | `HAS_INVOICE` |
| `"<supplier> in <country>"`, `"<country> supplier"` | `HAS_ADDRESS` + Country vocabulary lookup |
| `"<supplier> has <PO>"`, `"<PO> for <supplier>"` | `HAS_PURCHASE_ORDER` |
| `"<buyer> assigned to <PO>"`, `"<PO> buyer"` | `ASSIGNED_TO` |

This list is illustrative for v1. The agent does not pattern-match these phrases mechanically; the lookups are here to make explicit what the KG considers a known phrasing of each edge. How the agent uses them (substring match? embedding similarity? LLM-driven matching?) is later-phase work.

---

## 6. Query Patterns

Patterns are reusable logical shapes the agent can look up rather than re-derive. Each pattern is named, defined in entity/relationship terms (not tool calls), and accompanied by the Fusion mechanics that realize it.

The agent's job at query time is: parse the user's prompt → identify the pattern(s) it matches → fill in the entity/parameter slots → execute. The KG holds the patterns; the agent applies them.

### 6.1 `no_Y_in_N_months` — Negation over a time-windowed relationship

**Shape:** Given a set of entities of type X, filter to those that have *no* related entity of type Y in the last N months.

**Reference-prompt instantiation:**
> *Suppliers with no invoices in 6 months* → `no_Y_in_N_months(X=Supplier, Y=Invoice, edge=HAS_INVOICE, date_field=InvoiceDate, N=6)`

**Mechanics:**
1. Compute the cutoff date: `today - N months` (ISO format).
2. For each X (in our case, each candidate Supplier), query Y filtered by the date attribute being `>= cutoff` AND the parent reference matching X's join key.
3. Keep X if the query returns *zero* matches; drop X if it returns one or more.

**Why this is a pattern, not just a tool call:** The logic shape ("entity has no related entity in window") recurs across the domain — no invoices, no payments, no shipments, no logins. Encoding it once as a pattern means future agent prompts can match against it; encoding it once per tool means re-deriving it every time.

**Edge case the KG should flag:** Negation over an unbounded set is dangerous. If an agent is asked "suppliers with no invoices ever," and the invoices endpoint is large, naive client-side iteration is expensive. The pattern documentation should note that this is the time-bounded variant; an unbounded "ever" variant needs different mechanics (probably aggregation, not per-supplier query).

### 6.2 `status_filter` — Status-coded attribute filter

**Shape:** Given a set of entities of type X, filter to those whose status attribute matches a business-term-named status value.

**Reference-prompt instantiation:**
> *Open purchase orders* → `status_filter(X=PurchaseOrder, status_term="open" → StatusCode="OPEN")`

**Mechanics:**
1. Look up the business term in the PO Status vocabulary (§5.2) to get the Fusion code.
2. Query the endpoint with the status filter applied.

**Why this is a pattern:** Track A's baseline ran without this. The agent had to know that "open" maps to `StatusCode='OPEN'` (uppercase, specific value) from a docstring. With the lookup explicit, the LLM's job is recognition ("the user said 'open', the KG says 'open PO' means `StatusCode='OPEN'`") rather than guessing.

### 6.3 `country_filter_via_address` — Parent → child traversal with attribute filter

**Shape:** Filter a set of parent entities by an attribute that lives on a child resource.

**Reference-prompt instantiation:**
> *Suppliers in US* → `country_filter_via_address(parent=Supplier, child_relationship=HAS_ADDRESS, child_attribute=CountryCode, value="US")`

**Mechanics:**
1. Resolve the country term using the Country vocabulary (§5.1).
2. Fetch parents with the child resource expanded (`expand=addresses` for suppliers).
3. Client-side: keep a parent if *any* child matches the attribute value.

**Why this is a pattern:** The instinct from a SQL background is "suppliers have a country" — i.e., that country is a parent attribute. In Fusion REST, country is genuinely on the child. Without encoding this, the agent will keep trying `q=CountryCode='US'` against `/suppliers` and getting nothing. The pattern makes the parent-vs-child distinction explicit.

### 6.4 `cross_pillar_lookup` — Following an ID across modules

**Shape:** Given an ID that's exposed on entity X (in pillar A) and is the primary key of entity Y (in pillar B), perform a lookup from pillar B.

**Reference-prompt instantiation:**
> *The buyer assigned to each PO* → `cross_pillar_lookup(from=PurchaseOrder.BuyerId, to=Buyer.PersonId, target_endpoint=hcmRestApi/publicWorkers)`

**Mechanics:**
1. Take the ID from the source entity (FSCM PO's `BuyerId`).
2. Query the target endpoint in the other pillar (HCM `publicWorkers` filtered by `PersonId=X`).
3. Return the target entity's display fields (name, email, username) joined back to the source.

**Honest framing:** This pattern is the one I'm least confident about as a *named* pattern. v1 has exactly one instance of it (PO → Buyer). It may turn out in phase 04 that the `ASSIGNED_TO` edge already carries enough information to make a separate "cross-pillar" pattern redundant. If so, v1.1 will drop the pattern and rely on the edge alone. Documenting this as a soft pattern in v1 keeps the option open without committing to it.

### 6.5 Pattern composition for the reference prompt

The reference prompt composes all four patterns:

> *Show me suppliers in US with no invoices in 6 months but with open purchase orders, including the buyer assigned to each.*

| Clause | Pattern |
|---|---|
| "suppliers in US" | `country_filter_via_address(Supplier, US)` |
| "with no invoices in 6 months" | `no_Y_in_N_months(Supplier, Invoice, 6)` |
| "with open purchase orders" | `HAS_PURCHASE_ORDER` traversal + `status_filter(PO, "open")` |
| "the buyer assigned to each" | `cross_pillar_lookup(PO.BuyerId, Buyer.PersonId)` |

If the KG encodes these four patterns correctly, the agent's planning task collapses from "derive the join structure" to "match clauses to patterns and execute them in order." That is the entire bet of Track B.

---

## 7. What v1 Deliberately Omits

A consolidated list of non-goals, so later phases can refer to it and so scope creep has a name.

### Excluded from v1, with reasons

- **No instance business data.** The most important non-goal, restated for emphasis: no rows of Fusion suppliers, invoices, POs, buyers, or addresses live in the KG. The KG stores structural metadata only. (§1)
- **No per-tenant overlays / customer-specific knowledge.** v1 assumes one customer, one pod, one persona. Per-tenant DFFs, custom value sets, and custom business rules are post-POC concerns. The KG schema *can* be extended to support tenant-scoped overlays later; v1 doesn't model them.
- **No DFFs and custom attributes.** Fusion's Descriptive Flexfields allow customers to add custom fields. v1 does not model them. If a prompt requires a DFF, v1 fails — and that's documented as an expected limitation.
- **No setup and reference data ingestion.** Country codes, currency codes, status code lists, business unit hierarchies — Fusion exposes all of these via setup endpoints. v1 holds a small static vocabulary (§5) rather than ingesting them. Ingestion is a later phase if/when needed.
- **No currency conversion or unit semantics.** Invoice amounts are stored with their currency code; v1 does not convert across currencies. A prompt like "suppliers with > $10K in invoices" would need explicit currency disambiguation; v1 doesn't help with that.
- **No historical / temporal modeling.** The KG describes current Fusion *structure*; not record histories, audit trails, or temporal validity.
- **No approval flows, payment workflows, requisitioning lifecycle.** None of these are entities or relationships in v1. They are deliberately excluded because the reference prompt doesn't need them and modeling them well is itself a multi-week effort.
- **No write operations.**
- **No multi-pod federation.** One pod, one persona.
- **No inverse and transitive relationships.** v1 models edges in one direction (Supplier → PO, not PO → Supplier). The agent can traverse backward by using the same edge in reverse at query time, but the KG doesn't model the reverse as a distinct edge. Transitive closures are not in scope.
- **No cardinality enforcement.** The KG documents cardinality (1-to-many, many-to-1) but doesn't enforce it — because v1 is read-only and there's no write surface to enforce against.
- **No provenance and confidence.** The KG doesn't model "this relationship was added on date D by user U with confidence C." v1 treats all schema content as trusted and static.

### When these omissions will bite

Some of the omissions matter for the reference prompt; some don't. The ones that don't matter for the prompt but are likely to matter in production work:

- **DFFs** — the moment Spire targets real customer pods, DFFs appear.
- **Per-tenant overlays** — multi-tenant deployment is in the SME's stated requirements (see `spire_design_alternatives.md` §5).
- **Setup data ingestion** — the static country vocabulary will not scale to thousands of countries × hundreds of currencies × dozens of value sets.

These are flagged here so they don't get rediscovered in panic at a later phase. The plan is: validate the POC with v1; if the hypothesis holds, expand the KG with the above in deliberate, phased work.

---

## 8. Open Questions

A short list of questions that are *not* answered in v1 and that may need answers in later Dynamic Orchestration phases. These are deliberately not resolved here because resolving them changes the design without changing what the POC tests.

1. **How does the agent match prompt clauses to patterns?** v1 names four patterns and shows how the reference prompt decomposes into them. But the *mechanism* by which the agent matches a prompt clause to a pattern — substring matching, LLM-driven matching, embedding similarity — is not specified. This is Dynamic Orchestration 04 (KG Query Tools) / 06 (Embeddings) territory.

2. **What's the contract between the KG and the existing tools?** The MCP tools from Track A still execute the actual Fusion calls. The KG tells the agent *what* to call; the tools handle *how*. The interface between "KG says: traverse `HAS_PURCHASE_ORDER` from supplier S filtered to OPEN" and "tool call: `search_purchase_orders(supplier_id=S, status='OPEN')`" needs to be defined. v1 hand-waves this; Dynamic Orchestration 04 will need to make it precise.

3. **How is the KG kept in sync with the schema as it evolves?** v1 is a static document. If the schema grows (new entities, new patterns), version-control discipline is one answer; automated regression tests against the schema is another. Out of scope for v1.

4. **What's the error contract when a pattern can't be applied?** If the user asks something the KG doesn't model, what should the agent do — fall back to docstrings (Track A behavior), surface "I don't have a pattern for this" to the user, or attempt a best-effort answer with a warning? Not specified in v1.

(Note: the original revision-1 of this doc had a fifth open question about KG storage. That has now been answered by Dynamic Orchestration 02: Oracle 26ai with SQL Property Graph, accessed via `OracleClient`.)

These questions don't block Dynamic Orchestration 03 (populating the KG) but will need answers before 04 (building the query tools) and 05 (agent integration).

---

## 9. Summary

v1 in one screen:

- **The KG holds metadata, not instance data.** Zero rows of Fusion business data.
- **5 entities** declared, each with endpoint + canonical id + projection fields: Supplier, Invoice, PurchaseOrder, Buyer, Address
- **4 edges** declared, each with join key + endpoint hint: `HAS_INVOICE`, `HAS_ADDRESS`, `HAS_PURCHASE_ORDER`, `ASSIGNED_TO`
- **4 vocabulary tables**: Country, PO Status, Entity Synonyms, Relationship Phrases
- **4 query patterns**: `no_Y_in_N_months`, `status_filter`, `country_filter_via_address`, `cross_pillar_lookup`
- **1 reference prompt** the schema is sized to support
- **1 success criterion**: a Track B agent built on this schema scores meaningfully higher than the 1/7 Track A baseline

The schema is deliberately thin. If it turns out to be too thin, later Track B phases will surface that and v1.1 will add what's missing. The risk of being too thin is real; the risk of over-modeling is worse.

---

**Document status:** v1, revised during phase 03 (KG Population) to clarify the metadata-vs-instance-data distinction and recategorize Country. Will be refined as later Dynamic Orchestration phases discover gaps. Update this document — don't fork it — when changes are needed.
