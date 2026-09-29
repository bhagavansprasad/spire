# SPIRE — Capability Surface

**Purpose.** Name every capability Spire supports today, and say where its prompts live (or will live). The prompt-set inventory mirrors the capability inventory: if Spire supports X, a prompt set tests X.

**Source of truth.** `kg_entity` (entity → module) and `kg_entity_tool` (rootable entities). Read 2026-09-24; 22 entities, 4 modules, 8 rootable targets. Row counts match the seed — no drift.

**Status:** Stage 1 — DRAFT.

---

## 1. The four modules

| Module | Entities | Rootable targets |
|---|---|---|
| `payables` | Invoice | Invoice |
| `procurement` | PurchaseOrder, PurchaseOrderLine, POSchedule, PODistribution, Buyer | PurchaseOrder |
| `receivables` | ReceivablesInvoice, ReceivablesInvoiceLine, ReceivablesTaxLine, ReceivablesInvoiceTransactionDFF, CreditMemo, AccountCreditMemo, CustomerAccount, CustomerTransaction, StandardReceipt, AccountReceipt, AccountReceiptApplication | ReceivablesInvoice, CustomerAccount, CreditMemo, StandardReceipt |
| `supplier` | Supplier, Address, Site, Classification, Contact | Supplier, Address |

"Rootable" = has a row in `kg_entity_tool`; a query can start here. Everything else is reached through its parent.

---

## 2. Combinations

Cross-module capabilities the KG declares. Only three — the KG is deliberately thin here.

| Combination | Trigger | KG evidence |
|---|---|---|
| `payables_supplier` | Invoice filtered by supplier; supplier filtered by invoice-side attributes | `Invoice.supplier` filter; `Supplier.has_invoice_over_amount`; `Supplier.has_no_recent_invoices` |
| `payables_procurement` | Invoice filtered by PO; ordered-vs-invoiced compare | `Invoice.purchase_order` filter; the compare block (`po_invoiced_vs_ordered`, `supplier_invoiced_vs_ordered`, `top_suppliers_invoiced_vs_ordered`) |
| `procurement_supplier` | PurchaseOrder filtered by supplier; supplier filtered by PO presence | `PurchaseOrder.supplier` filter; `Supplier.has_open_PO`; `HAS_PURCHASE_ORDER` edge |

The `top_suppliers_invoiced_vs_ordered` op spans all three modules. Folded into `payables_procurement` rather than given its own folder — one prompt is a section, not a folder.

---

## 3. Cross-cutting features

Capabilities that apply to more than one module and are not themselves modules. Tested with flat `<tier>_<feature>.txt` files at the root.

| Feature | What it tests | Existing files |
|---|---|---|
| `columns` | Column projection: `fields` on the intent, projected table, address flatten, over-run catch, column vocabulary, field synonyms | 04, 07, 11 |
| `refusals` | Out-of-scope decline: correct flavor, right reason, every promised Example answers | 05, 10 |
| `lifecycle` | The PO lifecycle filter — status matrix, diagnosis, executive summary | 08 |
| `child_as_root` | A prompt naming a child entity plus its parent's id — must root on the parent and fetch the child | 13 |
| `truncation` | Truncation narration: sample vs total, "returned" vs "examined for filtering" | 14 |
| `date_filters` | Absolute and relative date bounds across PO (CreationDate, LastUpdateDate) and Invoice (InvoiceDate) | 15, 16, 18 |
| `fields_and_include` | Intents carrying both `fields` and `include` — the F-051 shape | 19 |
| `modes` | Aggregation, comparison, count, open-invoices, balance — the mode flags on the intent | 17 (partial) |
| `dipstick` | Depth-ordered triage: one prompt per pipeline depth | 00 |
| `release_gate` | Cross-module release gate - 10 prompts spanning all four modules, one refusal, one cross-module join. Single file, not tiered. | release_gate/litmus |

---

## 4. Folder structure

~~~
prompts/
  supplier/          smoke.txt  verify.txt  exhaust.txt
  payables/          smoke.txt  verify.txt  exhaust.txt
  procurement/       smoke.txt  verify.txt  exhaust.txt
  receivables/       smoke.txt  verify.txt  exhaust.txt
  payables_supplier/       smoke.txt  verify.txt  exhaust.txt
  payables_procurement/    smoke.txt  verify.txt  exhaust.txt
  procurement_supplier/    smoke.txt  verify.txt  exhaust.txt
  columns/                smoke.txt  verify.txt  exhaust.txt
  refusals/               smoke.txt  verify.txt  exhaust.txt  refusal_examples.txt
  lifecycle/              smoke.txt  verify.txt  exhaust.txt
  child_as_root/          smoke.txt  verify.txt  exhaust.txt
  truncation/             smoke.txt  verify.txt  exhaust.txt
  date_filters/           smoke.txt  verify.txt  exhaust.txt
  fields_and_include/     smoke.txt  verify.txt  exhaust.txt
  modes/                  smoke.txt  verify.txt  exhaust.txt
  dipstick/               smoke.txt  verify.txt  exhaust.txt
  scorer/                 parser_stress.txt  tool_selection.txt
  sme/                    testcases.txt
  retest/                 prompts.txt
  release_gate/           litmus.txt
~~~

Rule: every capability — module, combination, or cross-cutting feature — is a folder at prompts/ root, holding three tier files (`smoke.txt` / `verify.txt` / `exhaust.txt`). One level of folders only; one file at root, this tree's README. `refusals/` additionally holds `refusal_examples.txt`, the contract file enforced by `tests/test_nl_parser_capability.py`. `release_gate/` is the exception: a single-file cross-cutting set, not a capability tier - see section 3.

---

## 5. Tiers

| Tier | Purpose | Size | Runtime |
|---|---|---|---|
| `smoke` | Alive. Does it work at all. Every prompt must answer. | 5-10 per file | Seconds |
| `verify` | Correct. Normal shapes, edges, refusals. | 20-40 per file | Minutes |
| `exhaust` | Stress. Every variation we know. Goal: find a crash. | 50+ per file | Overnight |

The exhaustive target: at least double the current runnable prompt count, and Spire should *crash* on at least one. If exhaust runs clean, the prompts are not exhaustive enough yet.

---

## 6. Legacy cross-walk

Where each existing file's content goes.

| Current file | New home |
|---|---|
| 00_dipstick.txt | dipstick/smoke.txt |
| 01_supplier.txt | supplier/verify.txt (some prompts → smoke, some → exhaust) |
| 02_purchase_order.txt | procurement/verify.txt |
| 03_ar.txt | receivables/verify.txt |
| 04_columns.txt | columns/verify.txt |
| 05_refusals.txt | refusals/verify.txt |
| 06_slow.txt | split: supplier parts → supplier/exhaust.txt; PO scans → procurement/exhaust.txt; compare → payables_procurement/exhaust.txt |
| 07_alacarte.txt | columns/verify.txt (merge with 04) |
| 08_lifecycle.txt | lifecycle/verify.txt |
| 10_refusal_examples.txt | refusals/verify.txt (merge with 05) |
| 11_column_vocabulary.txt | columns/verify.txt (merge) |
| 12_po_supplier_include.txt | procurement_supplier/verify.txt |
| 13_child_as_root.txt | child_as_root/verify.txt |
| 14_truncation_narration.txt | truncation/verify.txt |
| 15_po_relative_date_filters.txt | date_filters/verify.txt (merge) |
| 16_date_filter_cluster.txt | date_filters/verify.txt (merge) |
| 17_modes_and_columns.txt | split: modes → modes/verify.txt; columns → columns/verify.txt |
| 18_invoice_created_dates.txt | date_filters/verify.txt (merge) |
| 19_fields_and_include.txt | fields_and_include/verify.txt |

Merged files retain every prompt verbatim and every comment. Nothing is deleted.

---

## 7. Not in this pass

| File | Why |
|---|---|
| sme/testcases.txt | External, kept verbatim by design. Labels stale from 2026-07-28. |
| scorer/parser_stress.txt | Different format (EXPECT prefix, pipe-separated). Feeds the scorer, not promptkit run. |
| scorer/tool_selection.txt | Same. |
| retest/prompts.txt | Fold in to its targets (receivables, payables, columns). Header retained until the fold-in pass. |
| refusals/refusal_examples.txt | Kept as a separate contract file inside refusals/. Its guard — "every Example in capability.py appears here" — is enforced by `tests/test_nl_parser_capability.py`, not by the prompt set. The file is not a tier file. |

---

## 8. Unmapped — capabilities the KG declares with no prompt coverage today

Candidates to confirm against a live `promptkit --validate` run after the reorg.

- `po_status` vocabulary — 18 rows, no prompt tests the values. Audit §A-16 flagged this; four representative probes passed, but no file pins them.
- `relationship_phrase` vocabulary — 8 rows, loaded by the loader but never read by any consumer. Likely dead; confirm before writing prompts against it.
- `Buyer` via `ASSIGNED_TO` — the include is tested inside 02, but no dedicated prompt covers the cross-pillar HCM hop.
- `StandardReceipt` vs `AccountReceipt` — two entities over the same underlying receipts with different projections and different counts. The hazard is noted in test_kg_metadata.py; no prompt tests whether the parser picks the right one for a given phrasing.

---

## 9. What happens next

1. **Stage 2** — cut the tiers. For each capability, decide what its smoke/verify/exhaust files contain. Written into this doc as a per-capability tier plan.
2. **Stage 3** — fill and bulk. Work one capability at a time.
3. **Stage 4** — run and record. Full promptkit run per set. Failures become F-NNN.

---

## 10. Tier plan

For every capability in §1–§3, what each tier file contains. Smoke ⊂ verify ⊂ exhaust in scope — the same capability tested at increasing depth. Prompt strings are not duplicated across tiers; each tier has its own prompts, drawn from the same content categories.

### 10.1 `supplier` — folder

| Tier | Content | Target |
|---|---|---|
| smoke | count of suppliers · list active · one contact include · one address root · one expand-addresses · one out-of-scope refusal | 6 |
| verify | smoke shapes × 2 paraphrases · every `supplier_status` value · every `country` term · name fragments · 2-filter stacks · country-vs-BU collision traps · count with a filter | 30 |
| exhaust | verify + every `supplier_site_bu` value (10) · every `supplier_classification` value (9) · all 5 supplier edge filters · by-supplier aggregations with date ranges · F-008 / F-010 / F-020 V1 reproducers verbatim · boundary cases | 60 |

### 10.2 `payables` — folder

| Tier | Content | Target |
|---|---|---|
| smoke | invoices by supplier number · by name · one amount bound · one date bound · bare "invoices" refusal · one projection | 6 |
| verify | smoke shapes × paraphrases · both supplier shapes (number/name) × 3 phrasings · every Invoice date filter (relative + absolute) · every amount bound · `purchase_order` filter · `invoice_number` filter · combinations | 28 |
| exhaust | verify + F-012 V1 · F-018 V1 · F-044 V1 · F-046 V1 · F-049 V1 · every `purchase_order` phrasing · boundary | 55 |

### 10.3 `procurement` — folder

| Tier | Content | Target |
|---|---|---|
| smoke | by_id fetch with lines · list all POs · by_id fetch with distributions · PO status filter · bare "purchase orders" refusal | 5 |
| verify | smoke × paraphrases · every PO child include × 3 phrasings (lines, schedules, distributions) · date bounds (creation + last-update, absolute + relative) · `supplier` filter · `status` filter · F-045 reproducer | 35 |
| exhaust | verify + every PO status value (13) · every child include × 5 phrasings · lifecycle V1 · F-001 V1 · F-006 V1 · F-045 V1 · F-047 V1 · F-048 V1 · boundary | 65 |

### 10.4 `receivables` — folder

| Tier | Content | Target |
|---|---|---|
| smoke | AR invoice by id with lines · customer's invoices · recent credit memos · receipts for a customer · exposure ranking · one refusal | 6 |
| verify | smoke × paraphrases · every AR child (lines, tax, DFF) · every CustomerAccount child (transactions, receipts, credit memos, applications) · every mode (count, open_only, balance_only, invoice_limit) · StandardReceipt vs AccountReceipt | 35 |
| exhaust | verify + F-041 V1 (all 16 AR-child reproducers) · F-051 V1 · F-019 V1 · F-007 V1 · F-015 V1 · every aggregation op · every StandardReceipt phrasing · boundary | 70 |

### 10.5 `payables_supplier` — folder

| Tier | Content | Target |
|---|---|---|
| smoke | invoices for supplier 1252 · suppliers with an invoice over 10000 | 2 |
| verify | supplier filter × 4 phrasings · invoice-over-amount edge filter × 2 · no-recent-invoices edge filter × 2 · both directions of the join | 20 |
| exhaust | verify + F-009 V1 · F-012 V1 · F-036 V1 · F-044 V1 · boundary | 50 |

### 10.6 `payables_procurement` — folder

| Tier | Content | Target |
|---|---|---|
| smoke | how does invoiced compare to ordered for PO 162034 · which invoices were raised against PO 162034 | 2 |
| verify | smoke × paraphrases · all three compare ops · `purchase_order` filter × 3 phrasings · date-bounded comparisons | 20 |
| exhaust | verify + F-004 V1 · every compare op × 3 phrasings · every PO status × compare · boundary | 55 |

### 10.7 `procurement_supplier` — folder

| Tier | Content | Target |
|---|---|---|
| smoke | PO 701337 with supplier details · Show PO 701337 with the full supplier record | 2 |
| verify | 12_po_supplier_include's gradient (15) · `has_open_PO` edge filter · PO-by-supplier filter × 3 · both directions of the join | 22 |
| exhaust | verify × 2 paraphrases per gradient band · boundary (nonexistent PO, nonexistent supplier) · every safe/middle/dangerous phrasing | 50 |

### 10.8 `columns` — folder

Content merged from 04, 07, 11.

| Tier | Content | Target |
|---|---|---|
| smoke | baseline 3-col supplier · baseline Invoice 3-col · baseline PO 2-col · one address flatten · one over-run catch | 5 |
| verify | 04's 8 · 07's 12 · 11's baseline + normalization sections | 35 |
| exhaust | verify + 11's synonyms / jargon / EBS / must-not-resolve sections · F-014 V1 · F-017 V1 · F-027 V1 · F-051 V1 · boundary | 90 |

### 10.9 `refusals` — folder

Content merged from 05, 10.

| Tier | Content | Target |
|---|---|---|
| smoke | contract renewals · net 30 · who should we stop buying from · who columns / created by refusal | 4 |
| verify | 05's 9 · 10's 18 | 27 |
| exhaust | verify + every example in `capability.py` · every flavor × 2 prompts · every entity × 1 unanswerable · cross-entity ambiguous | 60 |

### 10.10 `lifecycle` — folder

Content from 08.

| Tier | Content | Target |
|---|---|---|
| smoke | 08's first 5 (A.2, A.3, A.4, A.7, A.10) | 5 |
| verify | 08's 31 (all sections) | 31 |
| exhaust | verify × paraphrases · every lifecycle shape · boundary (nonexistent PO, multiple POs, no PO) · regression guards vs neighbours | 55 |

### 10.11 `child_as_root` — folder

Content from 13.

| Tier | Content | Target |
|---|---|---|
| smoke | one prompt per parent entity (AR invoice, PO, supplier, customer account) | 4 |
| verify | 13's 64 filtered to a representative 30 (10 per family × 3 families plus one) | 30 |
| exhaust | all 64 from 13 + new variants per phrasing | 75 |

### 10.12 `truncation` — folder

Content from 14.

| Tier | Content | Target |
|---|---|---|
| smoke | invoices for supplier 1252 over 10000 · suppliers with their addresses · invoices for supplier 1252 (sibling) · invoices (negative) | 4 |
| verify | 14's 14 | 14 |
| exhaust | verify × 2 thresholds · every over-fetch-capable tool × 2 · boundary (empty source, one-row source, cap-exact) | 50 |

### 10.13 `date_filters` — folder

Content merged from 15, 16, 18.

| Tier | Content | Target |
|---|---|---|
| smoke | POs older than 6 months · POs created before 2024-01-01 · invoices in the last 30 days · invoices in 2024 · POs not touched in the last year · invoices created before 2024-01-01 | 6 |
| verify | 15's 23 · 16's date cluster (PO + Invoice) · 18's 12 | 40 |
| exhaust | verify × phrasings · every PO status × date · every Invoice amount × date · cross-column traps | 90 |

### 10.14 `fields_and_include` — folder

Content from 19.

| Tier | Content | Target |
|---|---|---|
| smoke | F-051 V1 (AR invoice + DFF) · one PO + lines · one fields-only sibling | 3 |
| verify | 19's 15 | 15 |
| exhaust | verify × every entity with a child · every child × field naming × 2 phrasings | 60 |

### 10.15 `modes` — folder

Content from 17 (mode sections).

| Tier | Content | Target |
|---|---|---|
| smoke | one aggregation · one comparison · one count · one open_only | 4 |
| verify | 17's mode sections · every op from the KG registries | 40 |
| exhaust | verify · every op × 3 phrasing variants · every op × boundary | 70 |

### 10.16 `dipstick` — folder

Content from 00.

| Tier | Content | Target |
|---|---|---|
| smoke | 00's 6, unchanged | 6 |
| verify | 00's 6 plus one prompt per depth on a different entity | 10 |
| exhaust | every depth × 3 entities × 2 phrasings | 20 |

---

## 11. Aggregate target

| Metric | Today | Target |
|---|---|---|
| Capabilities with a smoke file | 0 of 16 | 16 |
| Capabilities with a verify file | 0 of 16 | 16 |
| Capabilities with an exhaust file | 0 of 16 | 16 |
| Runnable prompts, all tiers | ~500 | ~1,500 |
| Minimum exhaust file | — | 50 |
| Average exhaust file | — | 60 |

Doubling today's total is the floor. Each capability's exhaust file at ≥ 50 gives ~975 exhaust prompts alone; with verify (~430) and smoke (~70), the total clears 1,400. The user's stated target — every combination possible, and Spire should crash on the exhaustive set — is met when exhaust stops passing.
