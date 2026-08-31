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
