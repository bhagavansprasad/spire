# SPIRE — Phase 1 Audit

**Phase:** Phase 1 — Audit & Baseline (Doc A §7.3.3)
**Session:** S002, opened 2026-09-15
**Last revised:** 2026-09-16
**Status:** All prompt-set files classified (12 files, ~200 prompts).
§A.1 is complete for the `graph_kg` scope; §A.2's pending rows close
when `parser_planner`, `parser_context`, and `mcp_server_tools` are read.
§B is complete from the prompt-set evidence: 26 confirmed rows, 4
candidates, ~150 correct answers/refusals, 12 positive examples. §D has
14 confirmed rows and 2 closures. §C, §E–§G not started. §H has twelve
observations.

**Companion documents:**
- Doc A — `SPIRE_ROBUSTNESS_EXTENSIBILITY_v3.2.md`
- Doc B index — `00_Doc_B_Index.md`
- Phase 1 log — `01_Phase_01_Audit_and_Baseline.md`

---

## Methodology

A row enters §A when a **fact** appears in more than one place and the
places must move together. Each row names the fact, every place it
appears, and whether they currently agree. Rows get stable IDs so §B
and §D can cross-reference.

A row enters §B when a prompt that the pipeline **should** answer either
(a) crashes, (b) returns a wrong answer, (c) silently omits requested
content, or (d) refuses when the capability exists. Each confirmed bug
carries a reproducer prompt and, where we have it, a `curl` verification
that the pod holds the data the pipeline missed.

A row enters §D when two parts of the codebase say the same thing two
ways, when an error message is inconsistent with the code path that
produced it, or when two prompts asking for different things produce
identical answers. §D.2 records rows that were suspected and closed as
not-a-bug after verification.

**Verification discipline.** A claim is confirmed only when the command
and its output are pasted. "The docs say X" is not evidence — Doc A
§7.3.2 said "update four imports" and the real count was 8.

**Classification.** Every prompt produces one of: answered,
honest-refusal, wrong-answer, crash, silent-omit, empty-scan. Prompts
that answer correctly are recorded in §B.3 so a future audit does not
re-open them. Prompts that refuse correctly are recorded there too.
Prompts that exhibit notably *correct* handling of a hard case are
recorded in §B.4 as positive examples.

---

## §A. Registry drift map

### A.1 Confirmed rows

| ID | Fact | Where it lives | State |
|---|---|---|---|
| A-01 | "Update four imports" — count of `display_formatters` import sites | Doc A §7.3.2 (says 4), actual code (8 import statements + 1 hard path + 2 docstring edits) | **disagree** |
| A-02 | Row counts per KG table | Seed banners, `test_kg_metadata.py::test_kg_table_row_counts_match_v1_1` `expected` dict, `print_kg.py::TABLES[].expected_rows`, `rebuild_kg.sh` PROMPT banners | **disagree** — `.sh` is stale; `kg_vocabulary` banner in seed has no count |
| A-03 | Entity list (22 names) | `kg_schema.sql` seed inserts, `test_kg_entity_has_twentytwo_rows`, `test_kg_entity_module_mapping` (keys) | **agree** |
| A-04 | Entity → module mapping | `kg_entity.module` column, `test_kg_entity_module_mapping` `expected` dict | **agree** |
| A-05 | `scripts/rebuild_kg.sh` vs `scripts/sql/kg_schema.sql` | `.sh` is a stale fork: table set 8 vs 9, no `module` column, 4 vocab kinds vs 9, entity rows 5 vs 22, entity_field rows 27 vs 210, entity_tool rows 2 vs 10, edge_tool rows 3 vs 16 | **disagree** |
| A-06 | Vocabulary kinds rendered by loader | `chk_kg_vocabulary_kind` (9 kinds), `loader.py::kind_order` (4 kinds) | **disagree** |
| A-07 | KG tables read by loader | 9 in schema; `loader.py` reads 5 | **disagree** |
| A-08 | `canonical_id_field` for Site and Classification | Declared on `kg_entity`; no rows in `kg_entity_field` | **disagree** |
| A-09 | FK relationships | `kg_schema.sql` FK constraints (8), `print_kg.py::FK_RELATIONS` (8, same) | **agree** but hand-maintained |
| A-10 | Column lists per table | `kg_schema.sql` CREATE TABLE, `print_kg.py::TABLES[].columns` | **agree** but hand-maintained |
| A-11 | Drop-order comment in `kg_schema.sql` | Comment lists 8 tables; code drops 9 (`kg_entity_filter` missing) | **disagree** |
| A-12 | KG `mcp_tool_name` vs actual MCP tool names | KG seed lists 10 + 16 | **pending** — `mcp_server_tools` |
| A-13 | KG `tool_arg_name` vs tool signatures | KG seed lists 26 filter rows | **pending** — `mcp_server_tools` |
| A-18 | `context_bundles.yaml` references moved files | Lists `scripts/display_formatters.py` (moved) and the two Doc A/B files (moved to `docs/spire-robustness/`) | **disagree** |
| A-19 | `MatchedCountry` field | Injected by `search_suppliers` when country filter applied; not declared in `kg_entity_field` | **disagree** |
| A-20 | Aggregate tool names | `kg_entity_tool`/`kg_edge_tool` don't list aggregate tools but the pipeline routes to them | **pending** — `parser_planner` |

### A.2 Pending cross-bundle verification

| ID | Fact | Needs |
|---|---|---|
| A-14 | Entity list vs `_SYSTEM_PROMPT_PREAMBLE` | `parser_planner` + `parser_context` |
| A-15 | Entity list vs `classifier_menu.sysprompt` | `parser_context` |
| A-16 | Vocabulary terms vs parser prompt coverage | `parser_context` + `parser_planner` |
| A-17 | Live KG vs seed file | `spire-ops kg print --counts-only` |

### A.3 Observations carried forward

- Doc A §7.3.2's "four imports" was already a §A row at authoring time. Establishes the failure class the audit exists to enumerate.

---

## §B. Bug inventory

### B.1 Confirmed bugs

| ID | Kind | Prompt(s) | Expected | Actual | Verify |
|---|---|---|---|---|---|
| B-01 | missing-capability (crash) | `What is purchase order US164932 about? Show its lines.` | Description with lines | `ERROR: execute: 1 validation error … po_header_id` | curl: `q=OrderNumber='US164932'` returns POHeaderId 560869 |
| B-02 | wrong-answer (narration) | `Get tax lines for invoice 300000248096352` | Invoice + "no tax lines" | Tax lines silently omitted | curl: child returns `"items": [], "count": 0`. See §B.4 for counter-example. |
| B-03 | wrong-answer | `suppliers with classification Minority Owned` | Currently certified | 1 match, no EXPIRED warning | curl: 1272 carries `"Status": "EXPIRED"` |
| B-04 | wrong-answer (scope) | ~35 prompts across seven files asking for classification/site/amount-filtered supplier or contact counts | Count over all suppliers | "N match" from 25 of ~455 examined, always the same insertion-order sample | Reproducible. Bounded by a `SITE_SCAN_LIMIT`. |
| B-05 | missing-capability | `addresses for supplier 1252` | Addresses | Refusal: no supplier-number filter | Reproducible. |
| B-06 | missing-capability | `Purchase orders older than 6 months` | POs before 6 months ago | Refusal: relative date windows not supported | `kg_entity_filter` has `created_before`/`created_since` with a comment naming the exact question. |
| B-07 | wrong-answer (metadata loss) | 5 prompts: composite filters on invoices/receipts | Truncation line naming the true total | `unknown total in source; N examined` | Any composite filter loses the total. |
| B-10 | wrong-answer (intermittent) | `Show PO 2144 and its distributions` | 5 records | 1 run in 7 returned 0 records | ~14% at n=7. `cache_mode: None` confirms execution cache not involved. Needs N ≥ 20. |
| B-11 | wrong-answer (silent) | `How much of PO 2144 was received?` | Lifecycle for PO 2144 | `found: False`, "No purchase order found for '2144'." | User-supplied PO reference routed to wrong field. Cross-reference D-07. |
| B-12 | wrong-answer (vacuous) | `How does invoiced compare to ordered for Lee Supplies?` | "No POs found" | `po_count: 0` → "**fully invoiced**." | Zero-equals-zero read as satisfied. |
| B-13 | wrong-refusal | `List all purchase orders`, `list purchase orders` | A list | Refusal: "doesn't say which one. Solution: Give me the PO number." | Two phrasings of the same class. `kg_entity_tool` has a `(PurchaseOrder, 'none')` row. Cross-check A-12/A-13. |
| B-14 | missing-projection | `Supplier number and country for active suppliers`, `Supplier name, number, status and country for active suppliers` | `SupplierNumber, CountryCode` | `SupplierNumber, Address` (full formatted blob) | Parser routed "country" to `include: ['Address']`. |
| B-15 | missing-capability (include never fires) | 12 prompts across `12_po_supplier_include.txt` and `11_column_vocabulary.txt` | Traversal to the supplier (and children) from the PO | PO header inline fields only; no edge traversal fires | KG declares `HAS_SITE`, `HAS_CONTACT`, `HAS_CLASSIFICATION`, `HAS_ADDRESS`, reachable from `PurchaseOrder.SupplierId`. |
| B-16 | missing-projection (NL field name not resolved) | `List active suppliers with supplier_name and supplier_number`, `List active suppliers with SupplierName and SupplierNumber` | `Supplier`, `SupplierNumber` | Refuses both | **Narrowed:** `field_synonym` vocabulary is honoured (`vendor name` → `Supplier`). B-16 is specifically names with no `field_synonym` row, even when the target field exists on the entity. |
| B-17 | wrong-answer (aggregate projection) | `Top 5 suppliers by invoice spend last year with supplier name and total`, `Top 5 suppliers by invoice spend last year with supplier name and total` (repeat) | Table with 5 rows | Em-dashes: `— | —`. Prose names the winner. | **Narrowed twice.** Aggregate alone is fine; specific to intents carrying explicit `fields` alongside `aggregate`. |
| B-18 | wrong-refusal (regression) | `Show lag between creation and last update for receipts of ABC Application Software` | Lag calculation | Refusal: "unsupported operation" | Endpoints reference documents lag as working twice. |
| B-19 | wrong-answer | `Show receipts for ABC Corporation Americas at Santa Clara` | Receipts for account 26370 at site Santa Clara | `No receipts found matching the criteria.` | curl: 500 records on the pod, all with `CustomerSite='Santa Clara'`. |
| B-20 | wrong-refusal | `How many purchase orders are there and what are they worth?`, `How much have we committed in open purchase orders?` | Count/sum | Refusal: "sum aggregation is not supported" | `aggregate_purchase_orders` exists. See A-20. |
| B-21 | wrong-answer (nondeterministic) | `Top 10 suppliers by spend in 2022` vs `Which suppliers did we spend the most with in 2022` | Same totals | Different totals and invoice counts | Same class as `/standardReceipts` ordering instability. Needs N ≥ 20. |
| B-22 | missing-projection (child-field scope) | 7 prompts across `11_column_vocabulary.txt` asking for child-entity fields | Child fields projected to the child rows | Refusal listing target-entity columns | Projection validation runs against the **target entity**, not the included child. Fields on both target and child (`Ordered`, `Total`, `Status`) project fine. |
| B-23 | wrong-answer (include dropped by `fields`) | `Show the AR invoice with CustomerTransactionId 300000248096352 with transaction number and flexfield` | `TransactionNumber` **and** DFF value | Only `TransactionNumber`; DFF child not rendered | Reproducer weak because DFF value is None in both cases. Needs a targeted run on invoice 1002 (DFF `"DOO"`). |
| B-24 | wrong-refusal (invoice number not recognised as an identifier) — **new** | `show details for invoice number LEE-01-1006-111` | Details of the named invoice | Refusal: "Invoice root has no supplier reference" — and the suggested fix is "give me the invoice number," **which the user already did.** | Same class as B-13: the parser's rooted-entity requirement blocks a sufficient identifier the user provided. |
| B-25 | wrong-answer (account number routed to name) — **new** | `Trace receipt applications for account 25750` | Receipt applications for account 25750 | `customer_name='25750'` → 0 records → "No customer accounts found." The account number was treated as a customer name. | Same class as B-05/B-11. Cross-reference D-13 (same account produces silent-0 in one prompt, honest refusal in another). |
| B-26 | missing-capability (top_n ignored on list queries) — **new** | `List recent credit memos, top 5` | 5 records | 25 records — the `top 5` was silently dropped from the intent | The parser extracts `top_n` for aggregate queries (`Show account activity summary for top accounts` → `top_n: 10` correctly set) but not for list queries. |
| B-27 | wrong-answer (run-on narration) — **new, cosmetic** | `Get Supplier contacts` | Contacts grouped per supplier | Same, **plus** a 47-name comma-separated run-on sentence ("Lee, Ryan, Lee, Jason, Cross, Sara, … — administrative contacts") inserted before the tables. | Cosmetic; the data underneath is correct. |

### B.2 Candidates

| ID | Kind | Prompt | Note |
|---|---|---|---|
| B-c1 | wrong-answer (suspected) | `What is the risk rating on PO 701337 and why?` | Needs a curl against the lifecycle source fields. |
| B-c2 | wrong-answer (suspected) | Supplier count across runs | 452 / 453 / 450 / 455 observed across the audit. Plausibly correct; belongs in §H until N-run evidence. |
| B-c3 | wrong-answer (semantics) | `suppliers that are not inactive` | Parses to `status=ACTIVE`. Correct on this pod but semantically different. |
| B-c4 | wrong-answer (silent, class) | Same root as B-10, B-12, B-19, B-21, B-25 | Consider collapsing once mechanisms are understood. |

### B.3 Correct answers and refusals

Recorded so future audits do not re-open them.

**Cross-file correct refusals and out-of-scope declines**

- Contract entity queries (out of scope)
- `suppliers with net 30 payment terms` / `payment terms` on Supplier
- `suppliers with the highest quality score` / `risk score` / `credit rating` / `rating`
- `who should we stop buying from`
- `show me purchase order line items` (as a target entity) — and its AR twin `Show invoice lines for invoice …`
- `recent invoices` / `Show invoices` / `invoices for US1 Business Unit` / `invoices for …` without a supplier
- `supplier sites for Lee Supplies` / `Get supplier sites for suppliers` / `List active suppliers … include supplier-site`
- `Get standardReceipts` / `Get the most recent standard receipts` / `Get the most recent standard receipts for account 25750`
- `list purchase orders` (as a raw list)
- `get account receivables transactions` / `get transaction number` / `Verify a newly created AR invoice` / `Trace receipt applications for this account` / `List all open invoices for the customer, top 5` / `Get tax lines for that invoice line` / `Fetch descriptive flexfield (DFF) values for this invoice.` / `For that PO, how much has actually been received versus ordered` — all correctly refused on missing identifiers.
- `Get all credit memos for account 300000047368512` — correctly refused (account number filter not supported on CustomerAccount).
- `Identify cash collection trends …` / `Summarise receipt volume and value by month` / `Summarise receipt volume and value by month for account 25750` — aggregation/grouping over time unsupported.
- `List active suppliers with supplier name and quantum flux` — nonsense field correctly refused.

**Per-file correct answers**

- `01_supplier.txt` — 35 correct answers (active/inactive queries, country filters, name fragments, business relationship, dates, counts, contacts, addresses, plain `show me suppliers`, `everything about supplier 1252` refusal).
- `02_purchase_order.txt` — 5 correct.
- `03_ar.txt` — 15 correct.
- `04_columns.txt` — 6 correct.
- `05_refusals.txt` — 6 correct refusals.
- `06_slow.txt` — 4 correct.
- `07_alacarte.txt` — 10 correct.
- `10_refusal_examples.txt` — the correct subset.
- `11_column_vocabulary.txt` — many correct (see §B.4 for the positive classes).
- `12_po_supplier_include.txt` — 6 correct for the PO header itself; the supplier-attach part is B-15.
- `qa_testcases.txt` — `Get list of Active Suppliers`, `Suppliers with their addresses`, `List all open purchase orders for supplier 'EIP Inc`, `invoices for Lee Supplies`, `Show PO 2144 and its distributions`, `List suppliers`, `Get the AR invoice with CustomerTransactionId 300000248096352`, `Get Supplier contacts` (aside from B-27), `Show account activity summary for top accounts`, `List recent credit memos, top 5` (aside from B-26).

### B.4 Positive examples — correct handling of a hard case

| Prompt | Behaviour | Counter-example to |
|---|---|---|
| `Show supplier name and credit rating for active suppliers` | Correctly identified the missing column, listed alternatives. | **B-02** — narration path exists. |
| `Show the AR invoice with CustomerTransactionId 1002 and its tax lines` | Full three-level traversal (invoice → lines → taxLines) works end to end. | **B-02** — the fetch-and-render path is fine; only empty-include narration is broken. |
| `What is the total value of credit memos?` | Currency-aware non-total with explanation. | **B-02** — same narration machinery. |
| `Rank top accounts by outstanding exposure` | `exposure_ranking` projects `rows` correctly. | **B-17** |
| `Top 10 suppliers by spend in 2022` | `supplier_spend_ranking` renders correctly — because the intent carries no `fields`. | **B-17** |
| `List active suppliers with vendor name and vendor number` | `field_synonym` vocabulary honoured. | **B-16** — narrows it. |
| `Show PO 2144 and its lines with ordered and total` | Projects `Ordered` and `Total` to the child rows. | **B-22** — narrows it. |
| `List active suppliers with supplier name and quantum flux` | Correctly refuses the nonsense field with the same unavailable-column note as genuine misses. | Nothing — good defensive behaviour. |
| `Show account activity summary for top accounts` | `top_n: 10` correctly extracted from a natural-language "top accounts" phrase for an aggregate query. | **B-26** — the parser handles `top_n` for aggregates, just not for list queries. |
| `List all open purchase orders for supplier 'EIP Inc` | Parser handled an unbalanced quote and a leading space; filter `status='OPEN'` + `supplier='EIP Inc'` both correct. | Nothing — good defensive parsing. |
| `Show PO 2144 and its distributions` (this session) | Correct — 5 records, matching the earlier successful runs. | **B-10** — confirms the success path dominates. |
| `Get Supplier contacts` | Cross-entity traversal works: contacts fetched for all 25 sampled suppliers, grouped per supplier. | **B-15** — narrows it: the traversal mechanism exists for `Supplier → Contact`; the failure is specific to `PO → Supplier → children`. |

### B.5 Cost bugs

| ID | Kind | Description | Evidence |
|---|---|---|---|
| B-09 | cost (LLM) | Double `classify` LLM call on every request. ~25% of LLM input tokens. | Every run across 12 prompt files. |

---

## §C. Dead code inventory

*To be written in task 1.7.*

---

## §D. Inconsistency inventory

### D.1 Confirmed

| ID | Where | What | Note |
|---|---|---|---|
| D-01 | `Show invoice lines for invoice 300000248096352` refusal | Router chose `payables`; reason names `ReceivablesInvoiceLine`. | Entity family named does not match routing decision. |
| D-02 | `suppliers with the highest quality score` refusal | Solution: "…total or average." | Aggregation template applied to a field-availability refusal. |
| D-03 | `Addresses for supplier 1252` vs `everything about supplier 1252` | Two different messages for the same root cause. | The second is factually wrong about `name_fragment`. |
| D-04 | Truncation wording | `Suppliers with their addresses` prints "25 examined for filtering" when no filter requested. | "Filtering" applied to an unfiltered fetch. |
| D-05 | `Purchase orders created before 2015` | Truncation block present in one run, absent in another. | Cross-reference §H.1. |
| D-07 | `Show PO 2144 and its lines` vs `How much of PO 2144 was received?` | `"PO 2144"` routed to `by_id` vs `lifecycle_status`. | Cross-reference B-11. |
| D-09 | `12_po_supplier_include.txt` prompts 7–15 | Seven prompts produce byte-identical answers. | Cross-reference B-15. |
| D-10 | `07_alacarte.txt` and `11_column_vocabulary.txt` | Duplicated prompts within and between files. | Test-set hygiene. |
| D-11 | `Compare ordered vs invoiced for our top 3 suppliers` | "under-invoiced by 864,399,645.92" is accurate but invites misreading. | ~1% of invoices are PO-linked on these pods. |
| D-12 | `Show invoice lines for invoice 300000248096352` | Two different refusal messages in two files: `unknown_entity` vs `unparseable`. | Same input, different message. |
| D-13 | `Trace receipt applications for account 25750` vs `Get the most recent standard receipts for account 25750` — **new** | First returns silent-0 ("No customer accounts found"); second returns honest refusal ("Filtering receipts by account number is not supported"). | Same account reference, two different behaviours. The silent-0 is B-25. |
| D-14 | Supplier count across the audit — **new** | `452` (`qa_testcases` P9), `453` (`01_supplier`), `450` (`01_supplier` active), `455` (`qa_testcases` P10), `451` (`11_column_vocabulary`). | See §H.1. |
| D-15 | `List recent credit memos, top 5` — **new** | Returns 25 records; `List recent credit memos` (no top-5) also returns 25 records. | The 5 was dropped silently (B-26). The two prompts produce effectively the same answer. |

### D.2 Closed as not-a-bug

| ID | Where | What | Why it closed |
|---|---|---|---|
| D-06 | `How does invoiced compare to ordered for PO 162034?` | `po_header_id: 1` | Low 1–16 POHeaderIds coexist with 300-million-range ones. |
| D-08 | `Suppliers created between Jan and Mar 2025` | 0 records | curl-verified: 0 in the window, 269 after. |

### D.3 Candidates

None.

---

## §E. In-flight work inventory

*To be written in task 1.9.*

---

## §F. Baseline metrics

*To be written in task 1.10.*

---

## §G. Behavioural byte-diffs

Golden files at `docs/audit/golden/`: `count_suppliers.txt`, `po_2144_and_lines.txt`, `suppliers_with_open_pos.txt`. Re-run confirmation pending.

---

## §H. Probabilistic-behaviour map

### H.1 Confirmed observations

- **`Show PO 2144 and its distributions` is intermittent.** 1 failure in 7 (~14%). Step 1 returns empty; downstream steps empty; synthesizer prints "No POs found." `cache_mode: None` confirms execution cache not involved. Needs N ≥ 20.
- **Aggregate totals are nondeterministic across runs.** `Top 10 suppliers by spend in 2022` vs `Which suppliers did we spend the most with in 2022`. Both succeed; both see different rows. Same class as `/standardReceipts` ordering instability.
- **Supplier count varies widely across files.** 450 / 451 / 452 / 453 / 455 observed. Some variation is legitimate (`status=ACTIVE` vs unfiltered); some may be pod growth during the audit. Needs N ≥ 20 for any specific query shape.
- **Relative date window resolution is not stable.** "last year" resolved to 2024-01-01–2025-01-01 in one file and 2023-01-01–2024-01-01 in another.
- **Truncation metadata is nondeterministic.** `Purchase orders created before 2015` — block present/absent across runs.
- **Parse-stage empty-draft retry is systemic.** `[parse] empty draft … retrying once` appears in **seven** files. Each retry succeeds. **Material to Phase 6c.**
- **Parser output length varies across runs on identical cached input.**
- **Insertion-order bias in all supplier scans.** Same first-25 list across prompts and files.
- **`MatchedCountry` field injected by `search_suppliers`.** See A-19.
- **Parser prompt cache is live and hitting on all sampled prompts.**
- **`ReferenceTransactionId` id-space anomaly.** One receipt-application record with a 300-billion-range id.
- **`Get Supplier contacts` produces the largest answer observed.** 25 suppliers × their contacts, ~117 records. Whether the answer should have been refused (no supplier named) or should have summarised is unclear; it currently renders everything.

---

## Cross-references

- Session log: Doc B `01_Phase_01_Audit_and_Baseline.md`.
- Doc A §7.3.3, §7.4, §7.5.

---

*End of Phase 1 audit (partial). §C, §E–§G to be written. §A.2 rows close when `parser_planner`, `parser_context`, and `mcp_server_tools` are read.*