# Actionable Refusals — Design

Status: **Proposed** (design captured; open questions parked below; implement
when scheduled). Depends on the prompt-to-intent router landing first (see
§6 Dependencies).

---

## 0. What this is, in one paragraph

When Spire cannot serve a query, it currently refuses with a machine **flavor**
— `unsupported_filter`, `missing_identifier`, `unknown_entity` — and little
else. A flavor tells the *system* why the parse failed; it does not tell the
*user* what went wrong or what to do instead. This feature turns every refusal
into an actionable one, in Spire's established **Reason / Solution / Example**
shape: a plain-language reason, a concrete way forward, and an example prompt
that would work. The key enabler is that the KG already encodes the information
needed to generate the "way forward" — in particular, for the large class of
**child-only entities** (a supplier site, a PO line, a receipt), the KG's
`HAS_*` edges already record the parent-then-child path a user should take.

---

## 1. The problem, precisely

A refusal today carries a `RefusalFlavor` and stops there. Two real cases from
increment-1 validation of the router show the gap:

- **Child-only entity.** "list supplier sites for vendor 1252" refuses. `Site`
  has no direct fetcher (`kg_entity_tool` has no row for it); it is reachable
  only as a child of a specific `Supplier` via the `HAS_SITE` edge. The refusal
  is *correct*, but it says `unsupported_filter` / `unknown_entity` and offers
  the user nothing. A good refusal would say: *sites aren't listable on their
  own — fetch the supplier and its sites are in the record; e.g. "show supplier
  1252".*
- **No-fetcher filter.** "which invoices were created last month" can produce an
  Intent of `Invoice + created_date`, but `Invoice` has no `created_date` filter
  wired (`kg_entity_filter` lists only `invoice_amount`, `invoice_date`,
  `purchase_order`, `supplier` for Invoice). The refusal is again correct but
  unhelpful. A good refusal would name the filters Invoice *does* support and
  give a working example (e.g. filter by `invoice_date` instead).

The common thread: **the reason a query can't be served, and the closest thing
that can, are both facts the KG already holds** — which entities have fetchers,
which filters each supports, and how a child entity is reached from its parent.
The refusal layer just isn't using them.

---

## 2. The core idea — refusals grounded in the KG

The KG is the single source of truth for capability. A refusal should be
generated *from* it, not hand-authored per case:

- **Which entities are directly fetchable** — `kg_entity_tool` (10 rows today).
- **Which filters each entity supports** — `kg_entity_filter` (24 rows).
- **How a child entity is reached from its parent** — `kg_edge` `HAS_*` edges.

### 2.1 Child-only entities the KG can already route around

There are **14 entities with no direct fetcher**, every one of which the KG
already gives a parent path for via an edge:

| child-only entity                | reached via edge          | from parent        |
|----------------------------------|---------------------------|--------------------|
| AccountCreditMemo                | HAS_ACCOUNT_CREDIT_MEMO   | CustomerAccount    |
| AccountReceipt                   | HAS_ACCOUNT_RECEIPT       | CustomerAccount    |
| AccountReceiptApplication        | HAS_RECEIPT_APPLICATION   | CustomerAccount    |
| CustomerTransaction              | HAS_CUSTOMER_TRANSACTION  | CustomerAccount    |
| Classification                   | HAS_CLASSIFICATION        | Supplier           |
| Contact                          | HAS_CONTACT               | Supplier           |
| Site                             | HAS_SITE                  | Supplier           |
| PurchaseOrderLine                | HAS_LINE                  | PurchaseOrder      |
| POSchedule                       | HAS_SCHEDULE              | PurchaseOrder      |
| PODistribution                   | HAS_DISTRIBUTION          | POSchedule         |
| ReceivablesInvoiceLine           | HAS_AR_LINE               | ReceivablesInvoice |
| ReceivablesTaxLine               | HAS_TAX_LINE              | ReceivablesInvoiceLine |
| ReceivablesInvoiceTransactionDFF | HAS_TRANSACTION_DFF       | ReceivablesInvoice |
| Buyer                            | ASSIGNED_TO               | PurchaseOrder      |

So for the entire child-only class, the "Solution" and "Example" of the refusal
are **derivable from the edge**: *«{child} isn't listable on its own — fetch the
{parent} and its {child} are in the record; e.g. "show {parent} <id>"».* No
per-entity prose needs to be written; the KG already knows the shape.

(Note: `Address` is a mild exception — it has a fetcher (`search_addresses`)
*and* is reached via `HAS_ADDRESS`. "Has a fetcher" and "is also a child" are
not mutually exclusive; the design must key off the *absence* of a fetcher for
"child-only", not off edge membership.)

### 2.2 No-fetcher filters

For the filter case, the KG likewise holds the answer: `kg_entity_filter` lists
exactly which filters an entity supports. A refusal for an unsupported filter can
enumerate the supported ones and pick one for the example — again, generated, not
authored.

---

## 3. Proposed architecture (recommended direction)

The pipeline is `parse → plan → execute → synthesize`, with the refusal decided
at parse. Two plausible homes for generating the Reason/Solution/Example:

- **At the parser** — the parse already decides *to* refuse and knows the flavor;
  it could attach a structured, KG-derived suggestion to the refusal Intent.
- **At the synthesizer / a refusal renderer** — a dedicated step that takes the
  refusal flavor + the offending Intent and renders the Reason/Solution/Example,
  reading the KG for the suggestion.

**Recommended direction (not locked):** keep the parser thin — it emits the
*flavor* and the *offending target/filter* it tried, as it does now — and put the
KG-grounded Reason/Solution/Example generation in a **deterministic refusal
renderer** downstream (synthesizer-side), because:

- It is a KG lookup, not an LLM judgment — deterministic, testable, no tokens.
- It keeps refusal *wording* out of the parser prompt, which matters because the
  parser is at its token ceiling (§6).
- It mirrors how the rest of Spire is moving: local deterministic builders for
  output shapes, LLM only where judgment is genuinely required.

Under this direction the parser's job is unchanged in spirit (decide + flavor);
the new work is a renderer that, given (flavor, attempted target, attempted
filter), consults the KG (`kg_entity_tool`, `kg_entity_filter`, `kg_edge`) and
produces the three-part refusal.

---

## 4. Scope sketch (for when this is built)

A likely increment order, to be refined at implementation:

1. **Child-only refusals** — the 14-entity class in §2.1. Highest value, cleanest
   KG derivation (one edge lookup → parent path → example). Covers the Site case.
2. **Unsupported-filter refusals** — enumerate supported filters from
   `kg_entity_filter`, pick one for the example. Covers the Invoice+created_date
   case.
3. **Other flavors** — `missing_identifier` and the rest, case by case.

Non-goals (at least initially): rewriting the parser's *decision* to refuse (this
feature improves the *explanation*, not the decision); LLM-generated refusal prose
(the point is deterministic KG-grounded generation).

---

## 5. What this reuses

- `kg_entity_tool`, `kg_entity_filter`, `kg_edge` — the capability facts the
  renderer reads. All already populated and rebuilt from the seed.
- The existing `RefusalFlavor` and refusal path in the parser — the entry points
  the renderer hooks onto.
- The Reason / Solution / Example refusal contract Spire already commits to — this
  feature makes every refusal actually meet it.

---

## 6. Dependencies

- **The prompt-to-intent router must land first.** If any part of this ends up
  needing the parser to emit richer refusal context via the *prompt*, that hits
  the parser's ~8,000-token ceiling (see the router design,
  `prompt_to_intent_framework.md` §1.1 and §7.1). The router frees per-module
  headroom; this feature should be designed on top of it, not before it. Even
  under the recommended synthesizer-side direction (§3), which avoids prompt
  growth, the router should land first so the two efforts don't contend.

---

## 7. Open questions (resolve when work starts)

These are deliberately **not** decided here; lock them at implementation, the way
the router's D1–D4 were locked before its build.

1. **Where is the Reason/Solution/Example generated — parser or synthesizer/
   renderer?** §3 recommends a downstream deterministic renderer, but the parser
   already holds the flavor and offending Intent; the trade-off (thin parser vs.
   fewer hand-offs) needs a decision.

2. **What is the refusal data contract?** Does the refusal Intent carry structured
   fields (e.g. `reason_code`, `attempted_target`, `attempted_filter`,
   `suggested_parent`, `suggested_example`), and which stage fills each? The
   renderer needs enough structured input to do a KG lookup without re-parsing.

3. **Is the suggestion fully KG-derived, or partly authored?** §2 argues the
   child-only and unsupported-filter suggestions are derivable from edges/filters.
   But phrasing ("sites aren't listable on their own…") is prose — is there a small
   authored template per flavor, filled with KG values, or something more general?

4. **Multi-hop children.** Some children are two hops from a fetchable root
   (e.g. `PODistribution` via `POSchedule` via `PurchaseOrder`;
   `ReceivablesTaxLine` via `ReceivablesInvoiceLine` via `ReceivablesInvoice`).
   Does the suggestion walk to the *nearest* parent, or to the *fetchable root*?
   The edge table supports either; the UX question is which is more helpful.

5. **Ambiguous parents.** If a child is reachable from more than one parent, which
   does the suggestion name? (Most are single-parent today, but the design should
   not assume it.)

6. **Does this interact with the router's classifier?** A refusal for a child-only
   entity is still single-module (Site → supplier). Whether the renderer needs the
   classified module, or only the Intent, is a small open point.

7. **Scope of "actionable" for non-capability refusals.** Truly out-of-scope
   prompts (nothing to do with P2P/AR) have no KG-derived suggestion. What does an
   actionable refusal look like there — a generic capability summary, or just a
   clear "out of scope" with examples of what Spire *can* do?

8. **Testing oracle.** Like the router, this should be validated against the KG
   deterministically: given a child-only entity, assert the renderer names the
   correct parent edge and a valid example. The prompt→refusal path itself is
   subject to the same parser non-determinism noted in the router design (§7.1),
   so the *renderer* (deterministic, KG-driven) is what gets unit-tested, not the
   flaky parse that precedes it.
