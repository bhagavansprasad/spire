<!-- ───── merged from: docs/features/actionable_refusals.md ───── -->

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


<!-- ───── merged from: docs/features/parser_context_modularization.md ───── -->

# Parser Context Modularization — Architecture (Fusion-Module Axis)

Status: **Phase 1 in progress** — the split (part 1 of 4) is implemented and
merged behind the string-equality invariant. KG `module` mapping, the
selective-load harness, and the #32a case remain.
Supersedes: the functional-split draft. The organizing axis is now the
**Oracle Fusion module**, not functional concern.
Scope: the NL parser's system prompt (`_SYSTEM_PROMPT_PREAMBLE` in
`src/spire/nl_parser/parser.py`), the prompt/test corpus, and — as a documented
principle, not a refactor here — the tools.

> **Implementation note (updates §3, §4).** The delivered split refines the file
> mechanism this doc originally sketched. Two things changed, both forced by the
> §4.1 byte-identical guardrail:
> - **Files are `.sysprompt`, not `.txt`**, and the extension is deliberate:
>   these are LLM-visible system-prompt fragments, not prose docs.
> - **The split is per-*block*, in per-module sub-directories**, not one flat
>   file per module. The original literal interleaves modules bullet-by-bullet,
>   so grouping each module into one contiguous file could not reproduce the
>   original byte order. Instead each block is its own file under
>   `context/<module>/`, and a single `context/order.manifest` lists the blocks
>   in the original emit order. Assembly walks the manifest and joins — preserving
>   bytes exactly. A cross-cutting **`modes`** concern was also added (the
>   AGGREGATION / COMPARISON / COUNT / OPEN-INVOICES / ACCOUNT-BALANCE / TOP-N
>   blocks), since those span modules and belong with `columns` as a concern, not
>   on the module axis. Net: 48 block files across 8 directories
>   (`core`, `refusals`, four modules, `columns`, `modes`) + the manifest.
>
> The **design intent is unchanged**: two tiers, module-partitioned Tier 2,
> byte-identical all-modules assembly in Phase 1, KG-sourced module mapping,
> Phase 2 deferred. Only the on-disk shape is finer-grained than first drawn.

---

## 0. The organizing principle

**The Oracle Fusion module is the single axis of organization for Spire.**
Tools, parser context, and prompts are all partitioned along the same module
boundaries. Adding a new Fusion module means adding, as one coherent unit: its
tool group, its parser-context module, and its prompts. Everything derives from
the module.

Spire supports **four** Fusion modules:

| Module | Domain | Root entities |
|---|---|---|
| **payables** | AP invoices (money owed to suppliers) | Invoice |
| **procurement** | Purchasing — POs and their lifecycle | PurchaseOrder |
| **receivables** | AR — money owed to the company | ReceivablesInvoice, CreditMemo, CustomerAccount, StandardReceipt |
| **supplier** | Supplier master data | Supplier, Address |

The tools already follow this axis (see §8). This document brings the **parser
context** and the **prompts** onto the same axis, and defines how the system
knows which module context a prompt needs.

---

## 1. Problem

### 1.1 The monolith

The parser sends the LLM one large system prompt on **every** parse:

- `_SYSTEM_PROMPT_PREAMBLE` — a single string literal
  (`parser.py:48`, ~470 lines): role, entity rules, the PO lifecycle block, flag
  instructions, column rules, refusal/capability guidance, worked examples — for
  **all four modules at once**.
- `+ _format_menu(menu)` — the KG menu appended by `_build_system_prompt`
  (`parser.py:570`).

Measured cost: **~8000 input tokens per parse**; the preamble is the dominant,
fixed part.

### 1.2 Two costs this imposes

**Cost 1 — testing is expensive.** Every prompt→intent check ships the full
~8000-token, all-module context, even to test one module's behavior.

**Cost 2 — no module isolation.** Payables, Procurement, Receivables and
Supplier instructions are one undifferentiated blob. You cannot test, edit, or
reason about one module's parser behavior in isolation, and you cannot bisect
which module's rules drive a misclassification.

### 1.3 Concrete motivation (issue #32)

Fixing #32 fault (b) took ~5 hours partly because of Cost 2. The Procurement
phrasing "Is PO N complete?" deterministically misclassifies (drops the PO id),
and there was no way to isolate the Procurement rules to see why. Attempts to fix
it by adding prompt text induced **non-deterministic MAX_TOKENS runaway** — the
all-module monolith has no headroom. A module-partitioned context (a
Procurement-only file, testable alone) would have localized the diagnosis
immediately.

**Lesson banked:** add parser signals in **code**, not prompt (the monolith is
fragile). The module split does not change this; it makes the prose *organized*
and *testable*, but per-behavior signals still belong in deterministic code.

---

## 2. What already exists (build on, don't reinvent)

- **`scripts/score_parser_prompts.py`** — a parse-only scorer. Reads
  `EXPECT=... ||| prompt`, runs `parse()` (intent only, no execution), reduces to
  a comparable summary, reports failures. **This is the harness's execution
  engine.**
- **`scripts/prompts/scorer/parser_stress.txt`** — a ~60-prompt corpus in the
  `EXPECT=... ||| prompt` format. **The corpus format to extend.**
- **Module-partitioned tools** — the tool files already group by module (§8).
- **Module-aligned prompt sets** — `01_supplier`, `02_purchase_order`, `03_ar`
  already map to modules; `04_columns`, `05_refusals`, `10_refusal_examples`,
  `11_column_vocabulary` are cross-cutting (§6).

---

## 3. Context tiers and files

The parser context splits into **two tiers**.

### 3.1 Tier 1 — always loaded

Present in **every** parse, phase 1 and phase 2. Not Fusion modules — the shared
base. Two always-loaded concerns, each a sub-directory of `.sysprompt` blocks
(see the implementation note above for why per-block, not one file):

```
src/spire/nl_parser/context/
  core/        # role/Intent contract (role_contract), the completeness tail,
               # and the sign-off — the shared spine, split across 3 blocks
  refusals/    # refusal format + capability guidance (out_of_scope)
```

**Why `refusals` is always-on and not router-selected:** you cannot know a
prompt will be refused until you try to parse it, so refusal guidance cannot be
selected on a pre-parse signal. It must be present for every parse.

### 3.2 Tier 2 — selected (by the router in phase 2; all-loaded in phase 1)

```
  payables/      # Payables — AP invoice queries
  procurement/   # Procurement — PO / purchasing / lifecycle queries
  receivables/   # Receivables — AR invoices, credit memos, receipts, customers
  supplier/      # Supplier model — suppliers, sites, contacts, classifications, addresses
  columns/       # column-projection / column-selection rules (cross-cutting CONCERN)
  modes/         # aggregation / comparison / count / open-invoices / account-balance /
                 # top-N mode instructions (cross-cutting CONCERN — spans modules)
```

Each directory holds one or more `.sysprompt` blocks; `context/order.manifest`
fixes the global emit order across all of them.

The four Fusion-module directories are selected on a **domain** signal (which
module the prompt targets). `columns/` and `modes/` are selected on a **concern**
signal (does the prompt name specific columns? does it ask for an aggregate /
comparison / count?) — detectable from the raw prompt, so they are
router-selectable unlike refusals. (`modes` did not exist in the original sketch;
it was added during the split — see the implementation note.)

### 3.3 Assembly

`_build_system_prompt` joins the assembled preamble with the menu. In phase 1 the
preamble is "everything," assembled once at import from the manifest; in phase 2
the router narrows Tier 2 and the signature grows a `selected_modules` argument.

Phase 1 (delivered) — no selection yet, manifest-driven, cached at import:

```
_load_preamble_from_files():           # runs once at import
    parts = [read(block) for block in order.manifest]   # all blocks, in order
    return "".join(parts)              # byte-identical to the old literal

_ASSEMBLED_PREAMBLE = _load_preamble_from_files()

_build_system_prompt(menu):
    return _ASSEMBLED_PREAMBLE + "\n" + _format_menu(menu)
```

Phase 2 (planned) — the router selects a subset, still in manifest order:

```
_build_system_prompt(menu, selected_modules):
    blocks = tier1_always + selected_tier2_blocks(selected_modules)
    preamble = "".join(read(b) for b in manifest_order(blocks))
    return preamble + "\n" + _format_menu(menu)
```

---

## 4. Phase 1 — static all-modules assembly (byte-identical)

**Goal:** split the monolith into the Tier-1 + Tier-2 files, organized by Fusion
module, while production keeps loading **all** of them — byte-identical to today.

### 4.1 The production invariant (THE critical guardrail)

The assembled **all-files** preamble must be **string-equal** to the current
`_SYSTEM_PROMPT_PREAMBLE`. A test enforces this. Phase 1 changes *where the text
lives*, not *what production sends*. **Until string-equality holds, the split is
not done.** This is what makes phase 1 unable to regress production.

> Migration: capture the current literal; carve it into the tier/module files;
> assert the joined result equals the original byte-for-byte. Only reorganize
> text — never reword prose in a split that is meant to change nothing but
> layout. Any semantic change to production behavior is out of scope for
> phase 1.

### 4.2 What phase 1 delivers

1. **[DONE]** The context blocks (`core`, `refusals`, four modules, `columns`,
   `modes`) under `src/spire/nl_parser/context/` — 48 `.sysprompt` files in 8
   sub-directories, plus `order.manifest`. Generated by
   `scripts/build_parser_context.py`, which carves the live literal at the
   approved boundaries and self-verifies byte-equality.
2. **[DONE]** `_build_system_prompt` reads+joins them (once at import, cached in
   `_ASSEMBLED_PREAMBLE`); string-equality test green
   (`tests/test_parser_context_assembly.py`: constant == literal, disk assembly
   == literal, manifest complete, no orphans, count == 48).
3. **[DONE]** Production parses **unchanged** — the assembled preamble is
   byte-identical to the retained literal, verified live.
4. **[TODO]** A selective-load **test harness** (§7) that can assemble a chosen
   subset — e.g. `procurement`-only — to test/bisect one module cheaply.
5. **[TODO]** #32 fault (a) captured as a tracked KNOWN-FAIL case (§7.3),
   asserted on the full assembly.

Still remaining in Phase 1: the KG `module` mapping (§4.3), item 4, and item 5.

### 4.3 The entity→module mapping lives in the KG

Something must map a root entity to its Fusion module (Invoice→payables,
PurchaseOrder→procurement, CreditMemo/ReceivablesInvoice/CustomerAccount/
StandardReceipt→receivables, Supplier/Address→supplier). **This mapping is a KG
attribute** — a `module` field per entity — consistent with Spire's principle
that the KG is the source of truth and everything derives from it. Tools,
context selection, and the phase-2 router all read the same KG fact.

> KG change: add `module` to the entity metadata; bump the row-count tripwires in
> `scripts/print_kg.py` and `tests/test_kg_metadata.py` together; rebuild with
> `python scripts/rebuild_kg.py`.

---

## 5. Phase 2 — module-scoped runtime context (the router)

**Goal:** production sends only the context the prompt needs — Tier 1 always,
plus the targeting Fusion module(s) and `columns` when relevant. Real
per-parse token reduction and a tighter, less fragile prompt.

### 5.1 The chicken-and-egg, and how it is resolved

To scope parser context by module you must know the module **before** parsing —
but knowing the module is what parsing determines. This circularity is real and
exists **only at the parser boundary** (everything downstream — plan, execute,
synthesize — already derives the module deterministically from the parsed
`target_entity` via the KG).

Resolution: a **tiny first-pass LLM classifier** runs before the main parse. It
reads the raw prompt and returns the set of Fusion module(s) the prompt targets
(and whether column rules are needed). The main parse then runs with Tier 1 +
those modules.

### 5.2 The router contract

- **Input:** the raw prompt.
- **Output:** a set of module tags (e.g. `{procurement}`, or
  `{supplier, procurement}`), plus a `columns` flag.
- **Multi-module prompts load the UNION.** "Show suppliers with open purchase
  orders, include the buyer" -> `{supplier, procurement}` -> both contexts
  loaded. A prompt's primary module (its root entity's module) plus any modules
  pulled in by includes are all selected.
- **Unsure -> fall back to ALL modules.** When the classifier is not confident,
  it returns all four. This degrades to phase-1 behavior — proven safe — so a
  router miss never causes a misparse from missing context. Safety over savings.

### 5.3 Why a tiny LLM classifier (not deterministic keywords)

Chosen: a small first-pass LLM call. It is more robust to paraphrase than a
keyword map and can express "unsure -> all" naturally. Costs: an extra (small)
call and latency, and a new failure mode — both bounded by the all-modules
fallback. The classifier prompt is itself tiny (module names + one-line
descriptions), nowhere near the monolith's size, so it does not reintroduce the
token-ceiling fragility.

### 5.4 The fidelity guarantee (how phase 2 is proven safe)

A module-scoped parse must produce the **same Intent** as the full-context parse
for the same prompt. This is verified with phase 1's harness: run the corpus once
with the **full** assembly (the oracle) and once with **router-selected**
context; every case must match. Where they differ, either the router
under-selected (fix the router / widen the fallback) or a module file has a
hidden cross-module dependency (fix the split). **The full assembly is always the
correctness oracle; the router is an optimization measured against it.**

### 5.5 Phase 2 acceptance

1. A first-pass module classifier with an all-modules fallback.
2. For the full corpus, router-selected context yields the **same intents** as
   the full assembly (fidelity).
3. Measured token/latency reduction vs the monolith, the classifier's own cost
   included.
4. No new misclassification from under-selection on the tracked corpus.

---

## 6. Prompts / test corpus on the module axis

- **Module-specific prompt sets** partition by Fusion module. The existing
  `01_supplier`, `02_purchase_order`, `03_ar` already align; formalize the set as
  one per module (payables, procurement, receivables, supplier).
- **Cross-cutting prompt sets stay as-is.** `04_columns`, `05_refusals`,
  `10_refusal_examples`, `11_column_vocabulary` test the always-on tier
  (refusals) and the `columns` concern, which are not specific to one Fusion
  module. **Do not fragment these into module folders** — that would break
  coherent cross-module coverage. Keeping them unchanged also guarantees nothing
  currently working breaks.

---

## 7. The selective-load test harness (delivered in phase 1)

Extends `scripts/score_parser_prompts.py`.

### 7.1 Module selection per case

```
EXPECT=<intent expectation> ||| MODULES=procurement ||| <prompt>
```

- `MODULES=<subset>` -> assemble Tier 1 + the named Tier-2 files only. Cheap
  (hundreds of tokens vs 8000). Used to **bisect** which module drives a behavior.
- `MODULES` absent -> assemble **all** files (the fidelity default / oracle).

### 7.2 Richer intent expectations

Extend the `EXPECT` grammar:

```
target:PurchaseOrder      target_entity  (existing)
filter:lifecycle_status   intent carries a specific filter
list_all                  intent.list_all is True
no_filters                intent.filters == []   (the dropped-id shape)
combo:a+b                 multiple filters (existing)
count / aggregate         (existing)
refuse[:flavor]           refusal, optional flavor
```

### 7.3 #32 fault (a) as a tracked case

```
# KNOWN-FAIL (#32a): terse completion question should route to lifecycle,
# but the full-context parser drops the id. Procurement module. Severity high.
filter:lifecycle_status ||| MODULES=all ||| Is PO 162034 complete?
```

### 7.4 The fidelity caveat (keep the harness honest)

A subset-context run is a **diagnosis** tool, not a production oracle — a slim
context can classify a prompt correctly that the full context (or a
router-selected context) gets wrong. So: **`MODULES=<subset>` runs DIAGNOSE**
which module drives a behavior; **the full assembly VERIFIES** production-
equivalent behavior. Every tracked correctness expectation is asserted on the
full assembly. In phase 2, fidelity is: router-selected == full assembly (§5.4).

---

## 8. Tools on the module axis (documented; not reorganized here)

The tools already group by Fusion module. Reorganizing them into module
subdirectories (`tools/procurement/…`) is **deferred** — a separate refactor with
import churn, out of scope for this document. Current grouping:

- **payables:** `invoices.py`, `aggregate_invoices.py`
- **procurement:** `purchase_orders.py`, `purchase_order_by_id.py`,
  `purchase_order_lines.py`, `purchase_order_schedules.py`,
  `purchase_order_distributions.py`, `po_lifecycle.py`,
  `aggregate_purchase_orders.py`, `buyer.py`
- **receivables:** `receivables_invoice_by_id.py`, `receivables_invoice_lines.py`,
  `receivables_invoice_tax_lines.py`, `receivables_invoice_transaction_dff.py`,
  `receivables_credit_memos.py`, `account_credit_memos.py`, `account_receipts.py`,
  `account_receipt_applications.py`, `standard_receipts.py`,
  `aggregate_standard_receipts_by_method.py`, `customer_account_by_name.py`,
  `customer_transactions.py`, `rank_customer_accounts_by_exposure.py`
- **supplier:** `suppliers.py`, `suppliers_by_country.py`, `supplier_sites.py`,
  `supplier_contacts.py`, `supplier_classifications.py`, `addresses.py`
- **cross-module (note):** `compare_orders_to_invoices.py` spans Procurement +
  Payables — a case the phase-2 router must load two modules for.
- **shared infra (not module-specific):** `tool_result.py`, `pagination.py`.

`compare_orders_to_invoices` confirms cross-module queries are real and the
router's union behavior (§5.2) is necessary, not hypothetical.

---

## 9. Sequencing & risk

| | Phase 1 | Phase 2 |
|---|---|---|
| Changes production? | **No** (byte-identical all-modules assembly) | **Yes** (router-scoped context) |
| Value | Module-organized, module-testable context | Token/latency reduction; tighter prompt |
| Main risk | Low (string-equality invariant) | Medium (classifier is a new component) |
| Guardrail | Assembled == original literal | Router-selected == full assembly (fidelity) |
| Depends on | Existing scorer + corpus; KG `module` field | Phase 1 (files, harness, mapping) |
| Order | **First** | After phase 1 |

**Recommended path:** phase 1 first, in small steps, each guarded by
string-equality and the green suite. Land the context blocks (done), the KG
`module` mapping, and the selective-load harness; capture #32a. Then phase 2: the
first-pass classifier, verified against the full-assembly oracle.

---

## 10. Relationship to issue #32

- **#32 fault (b)** — fixed, merged (PR #132). Filter-less PO queries refuse
  instead of dumping; the signal is set in deterministic code, prompt untouched.
- **#32 fault (a)** — terse Procurement phrasings ("Is PO N complete?") drop the
  PO id. Measured: **not** a token-cap problem (short, valid, wrong parses),
  **not** a KG-definition problem (the lifecycle target exists and explicit
  phrasings reach it). A classification miss in the all-module monolith; adding
  prompt text induced MAX_TOKENS runaway (proven 3x). De-risked by the (b) guard
  (fails safe to a refusal). Severity high, tracked.
- This framework is (a)'s home: the `procurement` module file makes the relevant
  rules editable and testable in isolation; the harness bisects which module (or
  which added text) misclassifies "complete?"; any fix — a code-side injection
  like `_is_explicit_po_list`, or reweighting the `procurement/` blocks — is
  verified on the full assembly.

---

## 11. Open questions

Resolved during the Phase-1 split (part 1):

1. **Exact carve of the literal** — **RESOLVED.** Carved into 48 blocks by
   original bullet ownership; emit order preserved exactly via
   `order.manifest` (no reword, no reorder). Shared sentences were **not**
   duplicated into each module — the split follows the literal's own structure,
   and any bullet that sits between two modules stays where it was, in its own
   block, at its original manifest position. A cross-cutting `modes` concern was
   added alongside `columns`.
2. **Module dependency rules** — **RESOLVED for Phase 1.** Tier 1 (`core`,
   `refusals`) is always included by virtue of being listed in the manifest;
   Phase 1 loads all blocks unconditionally, so no module can be assembled
   without `core`. The harness's "Tier 1 always included" enforcement (§7) is a
   Phase-1 TODO item, not yet built.
4. **KG `module` field shape** — **RESOLVED (design).** One module per entity
   (one-to-one); cross-module queries are handled by the Phase-2 router's union,
   not by multi-module entities. Implementation of the field is the next Phase-1
   step (§4.3).
6. **Menu handling** — **RESOLVED.** The KG menu stays a separate always-on
   append: `_build_system_prompt` returns `_ASSEMBLED_PREAMBLE + "\n" +
   _format_menu(menu)`. It is not part of `core`.

Still open (deferred to the harness step / Phase 2):

3. **Corpus expectation grammar** — finalize the `EXPECT` extensions (§7.2) and
   migrate `parser_stress.txt` without losing coverage. (Harness step, Phase 1.)
5. **Classifier confidence threshold** — what counts as "unsure" (-> all-modules
   fallback) for the phase-2 router; how it is tuned and measured. (Phase 2.)


<!-- ───── merged from: docs/features/prompt_to_intent_framework.md ───── -->

# Prompt-to-Intent Framework — Design

Status: **Proposed** (design only; implementation to follow in increments)
Branch: `feat/prompt-to-intent-framework`
Builds on: Phase 1 parser context modularization
(`docs/features/parser_context_modularization.md`) — the 48 module-partitioned
`.sysprompt` blocks, the `order.manifest` assembly, the `parse(system_prompt=…)`
seam, and the `kg_entity.module` mapping are all prerequisites this work uses.

---

## 0. What this is, in one paragraph

Spire turns a natural-language prompt into an `Intent` (via the LLM parser),
then turns that `Intent` into a selected MCP tool (via a deterministic KG
lookup), then executes. Two problems have emerged at the prompt→intent boundary:
the parser sends an **all-modules** system prompt (~8,000 tokens) on every
request, which is at its token ceiling and cannot absorb new capability without
risking runaway generation; and when a new prompt misbehaves, there is **no
cheap way to see where it broke** — was the Intent wrong, or was the tool
selection wrong? This design adds two things: a **module-scoping router** that
classifies a prompt to its Fusion module(s) and parses against only that
module's context (solving the token ceiling structurally), and a **generic
prompt→intent→tool-selection validation framework** that, for any prompt in any
module, reports exactly which boundary failed — with **no tool execution**.

---

## 1. The core problem

### 1.1 The token ceiling blocks new capability
The parser's system prompt is the union of all four Fusion modules' guidance
(payables, procurement, receivables, supplier) plus cross-cutting concerns.
Phase 1 split this monolith into per-module `.sysprompt` blocks, but **production
still assembles and sends all of them** — the split organized the text without
changing what is sent. The assembled preamble is ~8,000 tokens and empirically
fragile: LLM-visible additions have tipped certain phrasings into MAX_TOKENS
runaway (observed 3× on issue #32). So any new capability that must be taught to
the parser — e.g. "top-N invoices by amount is supported" — cannot simply be
added to the prompt; there is no headroom.

The structural fix is **not** to keep trimming the prompt, but to stop sending
the whole thing. A prompt about invoices does not need supplier, procurement,
and receivables guidance. If the parser only received the payables context
(~2,000 tokens), the ceiling would cease to bind and new capability could be
taught in the relevant module with room to spare.

### 1.2 Failures are not localized
When a prompt produces a wrong or refused answer, the current tools do not say
*where* it went wrong. The `score_parser_prompts.py` harness validates
prompt→intent, but stops there. The next boundary — intent→tool-selection (the
planner's KG lookup) — is unvalidated in isolation. So a failure could be the
parser producing a wrong `Intent`, or the parser producing a correct `Intent`
that the planner then maps to the wrong tool (or no tool), and telling these
apart currently requires manual tracing. For a system meant to accept *any*
prompt, this is the wrong debugging posture: a new prompt that fails should
announce its failure point.

---

## 2. The solution, in two parts

### 2.1 The module-scoping router (produces the Intent)
A two-request flow replaces the single all-modules parse:

```
user prompt
  → [classify]      one small LLM call: "which Fusion module(s)?"  → e.g. ["payables"]
  → [assemble]      core + refusals + the named module(s) only     (not all four)
  → [parse]         parse(prompt, system_prompt=scoped)             (existing seam)
  → Intent
```

The classifier is cheap and separate. The parse it feeds is now **smaller**
(scoped to one module), so total tokens typically drop even with the extra call,
and — crucially — the scoped prompt has headroom for new capability.

### 2.2 The validation framework (checks two boundaries, no execution)
A generic harness that, for any prompt in any module, traces and validates:

```
PROMPT
  ├─ Stage 1: prompt → intent            (does the parser produce the expected Intent?)
  └─ Stage 2: intent → tool-selection    (does the planner's KG lookup pick the expected tool?)

  ✗ NO execution — no MCP call, no tool invocation, no results.
```

Stage 1 is what `score_parser_prompts.py` already does. Stage 2 is new: run the
planner's deterministic tool-selection on the produced `Intent` and check which
tool it *would* call — without calling it. The framework is **module-agnostic by
construction** (it reads the KG); invoices today, but supplier / PO / AR prompts
work the same way. Execution and result-correctness are explicitly out of scope
— Spire already has end-to-end scripts for that, and this framework is about
isolating *where* prompt→intent→tool-selection breaks, not re-testing execution.

---

## 3. Design decisions (locked)

These were resolved during design and govern the router's shape.

**D1 — The classifier returns a *list* of module names, not a single string.**
Even in the single-module case it returns `["payables"]`. Rationale:
increment 2 (cross-module prompts) will need multiple modules; a list keeps the
contract stable so union support does not force a caller refactor. `assemble_subset`
already accepts a collection, so a list drops straight in.

**D2 / D3 — The classifier is grounded in entity names *and* entity-synonyms,
per module, generated from the KG.**
The classifier's prompt lists, for each module, its entities (from
`kg_entity.module`) and their colloquial synonyms (from `kg_vocabulary` where
`vocab_kind = 'entity_synonym'`). Rationale: the strongest signal for which
module a prompt targets is which entity it names, and synonyms catch colloquial
phrasing ("vendor" → Supplier, "bill" → Invoice, "AR invoice" →
ReceivablesInvoice) so the classifier is unlikely to misroute. Scoped to
`entity_synonym` only — other vocab kinds (field synonyms, statuses, countries)
do not inform module choice and would only add noise. Generated from the KG so
it stays in sync automatically.

**D4 — The classifier context is generated into a committed file, read and
cached at import.**
A generator queries the KG and writes a `.sysprompt`-style file; the router
reads it once at import and caches it. Rationale: consistency with Phase 1
(generated, committed, readable, byte-stable prompt content), auditability (the
routing prompt can be read and diffed in a file), and no per-request DB
dependency. A tripwire keeps it in sync with the KG, as with the KG row-count
tripwires.

**D-router — The router is a separate layer *around* `parse`, not inside it.**
A `route_and_parse(prompt)` unit calls the classifier, assembles the subset, and
calls the unchanged `parse(prompt, system_prompt=scoped)`. Rationale: single
responsibility (`parse` does prompt+context→Intent; the router decides the
context), independent testability of the classifier, `parse` stays frozen, and a
clean home for the increment-2 fallback logic. The graph pipeline calls
`route_and_parse` instead of `parse`.

---

## 4. Scope and increments

### Increment 1 — single-module happy path (this effort)
- Classifier returns exactly one module for cleanly single-module prompts.
- Scoped assembly = Tier 1 (core + refusals) + the one module.
- `route_and_parse` wires classifier → assemble → parse.
- **Fidelity check:** for single-module prompts, `route_and_parse(prompt)` must
  produce the **same Intent** as `parse(prompt)` with the full all-modules
  context. Routing must change the token cost, not the Intent.

### Increment 2 — cross-module + fallback (deferred)
- Classifier may return multiple modules; assembly unions their blocks.
- "Unsure" → fall back to all modules (never worse than today).
- Not started here; noted so the D1/D-router choices are understood as
  forward-compatible.

### The validation framework (this effort, after the router)
- Extends `score_parser_prompts.py` with Stage 2 (intent → tool-selection).
- Generic across modules; no execution.
- Serves as the standing way to localize any new prompt's failure to a boundary.

---

## 5. Build order

The router is built **before** the framework, because the router *is* the
prompt→intent machinery — the framework validates prompt→intent→tool-selection,
and there is no scoped prompt→intent to validate until the router produces it.

1. **This design document.**
2. **The router (increment 1):** classifier-context generator + committed file →
   lift `assemble_subset` to production → the classifier → `route_and_parse` →
   fidelity test → commit.
3. **The validation framework:** add the intent→tool-selection stage to the
   harness, generic, no execution → prove it localizes failures → commit.

---

## 6. What this reuses (already built, Phase 1)

- `parse(system_prompt=…)` — the seam the router feeds the scoped context through.
- `assemble_subset(modules, menu)` — proven in the scorer harness; lifted to a
  production location so router and harness share one copy (no drift).
- `order.manifest` + the 48 `.sysprompt` blocks — the scoped content on disk.
- `kg_entity.module` — the entity→module mapping the classifier generator reads.

---

## 7. Costs and honest caveats

- **Two LLM calls per query** (classify + parse) instead of one. The classify
  call is small and the parse call is now smaller, so total tokens usually drop,
  but it is two round-trips — slightly more latency. This is inherent to the
  two-request design.
- **Increment 1 is single-module only.** A genuinely cross-module prompt
  ("compare invoices to POs") will classify to one module and may parse
  incompletely until increment 2; cross-module underperformance is expected,
  not a regression. (The comparison-based fidelity check this bullet originally
  described was retired — see §7.1.)
- **The framework stops at tool-selection.** It confirms the *right tool would
  be called*, not that calling it returns correct data. Execution correctness
  remains with the existing end-to-end scripts, by design.
- **A misroute poisons the parse.** If the classifier picks the wrong module,
  the scoped context lacks what the prompt needs and the parse suffers. This is
  why the classifier is grounded richly (D2/D3) and why increment 2 adds an
  all-modules fallback for the unsure case.


### 7.1 Update from increment-1 validation — the full parse is non-deterministic

The original increment-1 plan (§4) proposed a **fidelity check**:
`route_and_parse(prompt)` should produce the *same Intent* as the full-context
`parse(prompt)` on single-module prompts. Building and running it showed the
premise is unsound, and the comparison harness was **removed**.

**What we observed.** Running the same prompt through the full ~8,000-token
context **three times at temperature 0 produced three different outcomes** —
"list bills over 5000" refused (`missing_identifier`) on one run and parsed
correctly (`Invoice` + `invoice_amount`) on the next two. The full parse does
not preserve its *own* Intent across identical runs, so "matches the full parse"
is not a definable oracle; the comparison was measuring against noise. This is
consistent with the token-ceiling fragility in §1.1: at ~8,000 tokens the parser
sits near a decision boundary and tips stochastically, even at temperature 0.

Two points, stated with care:

- **The over-refusal is flaky, not systematic.** The full context *sometimes*
  over-refuses valid list/filter queries, unpredictably — not always.
- **Scoped contexts appeared more stable, but this is observed, not
  quantified.** In the same runs the payables-scoped parse of "list bills over
  5000" passed every time while the full parse flaked — consistent with the
  smaller context sitting further from the boundary. This is a handful of runs,
  not a controlled variance measurement; it supports, but does not prove, that
  scoping reduces non-determinism. If quantified later, reduced non-determinism
  may be a stronger argument for the router than the token saving itself.

**Consequence for validation.** The correct oracle is the **KG, not a second
parse**. Increment-1 correctness is validated by the intent→tool-selection
stage (§2.2): a routed Intent is checked against the KG's fetcher map for
*serviceability* — does `(target_entity, filter)` resolve to a real tool —
which is **deterministic** and does not flake. This also catches a class the
comparison approach could not: an Intent naming a filter with **no fetcher**
(e.g. `Invoice + created_date`, absent from `kg_entity_tool`) is flagged
regardless of what any parse produced on a given run.


