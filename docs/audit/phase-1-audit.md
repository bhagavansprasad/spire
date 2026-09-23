# SPIRE — Phase 1 Audit

**Phase:** Phase 1 — Audit & Baseline (Doc A §7.3.3)
**Session:** S002, opened 2026-09-15
**Last revised:** 2026-09-22
**Status:** All prompt-set files classified (12 files, ~200 prompts).
§A.1 is complete for the `graph_kg` scope. §A.2 closed 2026-09-18 in full:
A-12 through A-16 and A-20 verified from the three pending bundles, A-17
verified live (`print_kg.py --counts-only`, all 9 tables match the seed).
§B is complete from the prompt-set evidence. Findings-log coverage as of
2026-09-22: 23 §B.1 rows carry their own F-NNN entry; 3 rows (B-09, B-13,
B-20) are covered by cross-reference; all 4 §B.2 candidates have entries
(B-c4 folded into F-024's class note). No unwritten §B rows remain. §B.6
is the full audit-row-to-finding map. §D has 13 confirmed rows and 2
closures. §C, §E, §F, §G drafted 2026-09-18 (partial; see each section's
notes). §H has twelve observations, four of which closed at their own
N≥20 thresholds — F-022, F-023, F-024, F-040.

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
| A-12 | KG `mcp_tool_name` vs actual MCP tool names | KG seed lists 10 + 16; all present in `mcp_server/server.py` (34 tools registered) | **agree** |
| A-13 | KG `tool_arg_name` vs tool signatures | KG seed lists 26 filter rows; literal names match; two placeholders (`supplier`, `supplier_po`) resolved by `_resolve_arg_name` by value shape | **agree** (F-006 covers the `po_header_id` int/str type mismatch — a signature-type defect, not a name defect) |
| A-18 | `context_bundles.yaml` references moved files | Lists `scripts/display_formatters.py` (moved) and the two Doc A/B files (moved to `docs/spire-robustness/`) | **disagree** |
| A-19 | `MatchedCountry` field | Injected by `search_suppliers` when country filter applied; not declared in `kg_entity_field` | **disagree** |
| A-20 | Aggregate tool names | `kg_entity_tool`/`kg_edge_tool` don't list the 10 aggregate/comparison tools; `registries.py::_AGGREGATION_TOOLS` and `_COMPARISON_TOOLS` are a second registration channel | **disagree** (dual-registry design, not a drift bug) |

### A.2 Pending cross-bundle verification

| ID | Fact | Needs |
|---|---|---|
### A.2 Cross-bundle verification — closed 2026-09-18

| ID | Fact | Where it lives | State |
|---|---|---|---|
| A-14 | Entity list vs `_SYSTEM_PROMPT_PREAMBLE` | `kg_entity` (22 rows); preamble and `.sysprompt` blocks use no entity name outside the KG; menu is generated from the KG at runtime by `_format_menu`, so agreement is structural post-modularization | **agree** |
| A-15 | Entity list vs `classifier_menu.sysprompt` | Generated menu groups all 22 entities into the 4 modules; each group matches `kg_entity.module` exactly (also pinned by `test_kg_entity_module_mapping`); generator is `scripts/build_classifier_context.py` | **agree** |
| A-16 | Vocabulary terms vs parser prompt coverage | `kg_vocabulary` (120 rows, 9 kinds) vs parser-visible sources (`_format_menu` and the `.sysprompt` blocks). Per-kind breakdown below. | **disagree** — `po_status` untaught by any rule, but four representative probes (2026-09-18) pass; `relationship_phrase` is dead (see §A.2-notes) |
| A-17 | Live KG vs seed file | Seed banners (`kg_schema.sql`) vs live DB; `print_kg.py --counts-only` 2026-09-18: all 9 tables match (22/210/17/3/120/3/10/26/16) | **agree** |

**A.2-notes — A-16 breakdown by vocabulary kind.**

| kind | rows | where the parser sees it | state |
|---|---|---|---|
| country | 16 | `_format_menu` renders these into the menu | agree |
| supplier_status | 2 | `b_status.sysprompt` teaches 'active'/'inactive' | agree |
| supplier_business_relationship | 2 | `b_business_relationship.sysprompt` teaches both values | agree |
| supplier_site_bu | 10 | `b_site_in_bu.sysprompt` hardcodes the same 10 BUs | agree (duplicated list, currently in sync) |
| supplier_classification | 9 | `b_classification.sysprompt` hardcodes the same 9 classifications | agree (duplicated list, currently in sync) |
| entity_synonym | many | Classifier menu shows a subset; parser infers from prompt examples | partial (by design) |
| field_synonym | many | `expand_field_synonyms` runs post-parse; `b_who_columns.sysprompt` teaches the `who columns` term | partial (by design) |
| po_status | 18 | No rule teaches these values — no `b_po_status.sysprompt`, no menu rendering | **disagree** — parser works from model prior. Probed 2026-09-18 at four representative values (`closed for receiving`, `held`, `pending signature`, `pending approval`); the parser emitted either the pod value or a case/synonym variant the KG resolves, and the pod filtered correctly in every case that produced output. No F-NNN; risk measured and low. |
| relationship_phrase | 8 | Corrected 2026-09-18: loaded by `load_kg_menu` (loader.py:182 includes it in `kind_order`; line 190 iterates). Not consumed by any downstream reader — `grep -rn "relationship_phrase" src/` finds only the loader's own three references. | **disagree** — loaded-but-never-read vocabulary (see C-07) |

**A-16 recommendation — closed 2026-09-18.** The probe ran; see the `po_status` row above. No fix warranted for `po_status` — the vocab-resolution path handles case differences and divergent user words without the parser needing the pod's exact forms. `relationship_phrase` (8 rows, unread by every consumer) is a §C dead-code cleanup: delete the rows or wire them into a rule; leaving them is a maintenance hazard.

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
| B-28 | wrong-answer (composite) — **new** | `purchase orders created in 2023` | POs in 2023 | 0 records + "capped" note; pod has ~13,500 in the 2015-2024 window | F-045 |
| B-31 | missing-capability (vague-relative default) — **new** | `recent purchase orders`, `new purchase orders` | POs in a default recent window | Refuses `unsupported_filter`. Parser has no rule for a vague adjective with no N. | F-048 |
| B-30 | missing-capability (last-updated-date on PO) — **new** | `purchase orders not touched in the last year`, `purchase orders with no recent activity` | POs filtered by last-modified | Refuses `unsupported_filter`. Tool filters on CreationDate only. | F-047 |
| B-29 | missing-capability (relative-date on Invoice) — **new** | `invoices older than 6 months`, `invoices in the last 30 days` | Invoice list filtered by date | Refuses `missing_identifier`. `search_invoices` already accepts `invoice_date_after`/`invoice_date_before`. | F-046 |
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

### B.6 Findings-log mapping (2026-09-18)

Reverse index. Every §B row and candidate, its findings-log entry, and the finding's state. Kept beside §B so a reader of the audit does not have to flip to the findings log to see what has been written up.

| Audit row | Finding | Finding state |
|---|---|---|
| B-01 | F-006 | fixed 2026-09-22 |
| B-02 | F-007 | fixed 2026-09-22 |
| B-03 | F-008 | fixed 2026-09-22 |
| B-04 | F-010 | fixed 2026-09-22 |
| B-05 | F-009 | fixed 2026-09-19 |
| B-06 | F-011 | fixed 2026-09-23 |
| B-07 | F-012 | closed 2026-09-22 (PR #157) |
| B-09 | F-002 (cross-ref) | confirmed |
| B-10 | F-022 | closed-as-not-a-bug |
| B-11 | F-013 | closed-as-not-a-bug |
| B-12 | F-026 | closed-as-not-a-bug (mechanism latent) |
| B-13 | F-001 (cross-ref) | fixed 2026-09-22 |
| B-14 | F-027 | confirmed |
| B-15 | F-025 | closed-as-not-a-bug |
| B-16 | F-028 | closed-as-not-a-bug |
| B-17 | F-014 | confirmed |
| B-18 | F-029 | closed-as-not-a-bug (capability on parked branch; see E-12) |
| B-19 | F-015 | fixed 2026-09-22 |
| B-20 | F-003 / F-004 (cross-ref) | confirmed |
| B-21 | F-023 | closed-as-not-a-bug |
| B-22 | F-017 | confirmed |
| B-23 | F-021 | confirmed (root-cause partial — display mechanism unresolved) |
| B-24 | F-018 | fixed 2026-09-23 |
| B-25 | F-019 | fixed 2026-09-23 |
| B-26 | F-016 | confirmed |
| B-27 | F-020 | fixed 2026-09-23 |
| B-28 | F-045 | confirmed |
| B-29 | F-046 | fixed 2026-09-23 |
| B-30 | F-047 | fixed 2026-09-23 |
| B-31 | F-048 | confirmed |
| B-c1 | F-030 | closed-as-not-a-bug |
| B-c2 | F-024 | closed-as-not-a-bug |
| B-c3 | F-031 | closed-as-not-a-bug (observation) |
| B-c4 | F-024 (class note) | folded |

**Tally.** 27 §B.1 rows with own F-NNN; 3 cross-referenced (B-09, B-13, B-20); all 4 §B.2 candidates have entries (B-c4 folded into F-024's class note). No unwritten rows.

**§B is complete.** Every §B.1 row and every §B.2 candidate carries a findings-log entry or a cross-reference; no unwritten rows remain. §B.6 stays as the audit-row-to-finding map for future sessions.

---

## ¬ßC. Dead code inventory

### C.1 Confirmed orphans

| ID | Where | What | Confirm |
|---|---|---|---|
| C-01 | `src/spire/mcp_server/tools/suppliers_by_country.py` | Module not registered in `server.py`; not in `kg_entity_tool` or `kg_edge_tool`. Its replacement (`suppliers.py::search_suppliers`) documents the supersession. **Not a clean delete:** `tests/test_suppliers_by_country_tool.py` imports and tests the module directly, and `tests/test_executor.py` uses `search_suppliers_by_country` as a mock tool name in ~15 fixtures. Deleting requires renaming those mocks. | `grep -rn "search_suppliers_by_country\|suppliers_by_country" src/ tests/ scripts/` — ran 2026-09-18 |
| C-02 | `src/spire/planner/plan_builders.py::_previous_entity` | Declared, docstring reads "v1 does NOT use this helper... do not call it. Kept here as a stub so the design-doc contract is visible." Confirmed 2026-09-18: the definition is the only production hit; `planner.py:66` imports the name but never calls it, so the import is a second, latent orphan. The `previous_entity` local variable in `planner.py:410,417,435` is unrelated to the stub. | `grep -rn "_previous_entity" src/` — ran 2026-09-18: 1 def, 1 dead import |
| C-03 | `src/spire/nl_parser/capability.py::capabilities_sentence` (path corrected 2026-09-18) | Public helper. Docstring reads "No longer used by `capability_message`... Kept public because 'what can you do?' is a fair question." Reclassified from "orphan" to "test-guarded public helper": `tests/test_nl_parser_capability.py:62,276,279` imports and exercises it. The original row's path (`src/spire/synthesizer/capability.py`) was wrong; no such file exists. No production caller — the test guard is the only consumer. | `grep -rn "capabilities_sentence\|_capabilities_sentence" src/ tests/` — ran 2026-09-18 |
| C-04 | `src/spire/synthesizer/p2p.py::SupplierSummaryResponse` | Pydantic model, no construction site. Docstring describes an LLM summary-only path that has since gone fully local. Confirmed 2026-09-18: the only production hit outside the definition is an unused import in `synthesizer.py:89`. The original row's "re-exported" claim is not proven — there is no `__all__` entry and no consumer. Latent cleanup: delete the import and the model together. | `grep -rn "SupplierSummaryResponse" src/ tests/` — ran 2026-09-18 |
| C-05 | `src/spire/planner/lookup.py::find_entity` | Function defined and re-exported from `planner.py:50`. No call site in production: `planner.py` body, `plan_builders.py`, `kg_db.py`, and the parser modules do not call it. Only consumers are tests. | `grep -rn "find_entity\b" src/ tests/ scripts/` — ran 2026-09-18 |
| C-06 | `src/spire/nl_parser/context/modes/*.sysprompt` (6 files) | `m_account_balance`, `m_aggregation`, `m_comparison`, `m_count`, `m_open_invoices`, `m_topn_open_invoices`. Listed in `order.manifest` under folder `modes`, which is in neither `_TIER1` nor `KNOWN_MODULES`; `assemble_subset` never loads them. **Cross-ref: F-003.** Confirmed 2026-09-18: the manifest carries exactly 6 `modes/` entries. | `grep -c "modes/" src/spire/nl_parser/context/order.manifest` — ran 2026-09-18: 6 |
| C-07 | `scripts/sql/kg_schema.sql`, `kg_vocabulary` — `relationship_phrase` rows (8) | KG kind seeded but no downstream consumer reads it. Corrected 2026-09-18: the loader DOES iterate it — `src/spire/kg/loader.py:182` includes `relationship_phrase` in `kind_order`, and line 190 loops over that list, so the rows ARE loaded into the menu. The dead-code claim survives on a different mechanism: no downstream reader consumes the loaded value (`grep -rn "relationship_phrase" src/` finds only the loader's own three references — the comment on line 181, the `kind_order` list, and the label map). This is "loaded-but-never-read", not "never loaded". Also note `kind_order` lists 4 kinds, not the 5 the prior wording claimed. **Cross-ref: A-16.** | `grep -rn "relationship_phrase" src/` — ran 2026-09-18: 3 hits, all in `loader.py` |

### C.2 Candidates — need a grep outside the read bundles

| ID | Where | What | Confirm |
|---|---|---|---|
| C-08 | `_read_clob` in `kg_db.py`, `vocabulary.py`, `loader.py` | Three separate definitions of the same helper. Each is used by a different module; the duplication is real, not an orphan. §C-adjacent — a consolidation item, not a delete item. | `grep -rn "def _read_clob" src/` — expect 3 |
| C-09 | `src/spire/planner/registries.py::_OUTPUT_NAME_BY_ENTITY` (partial) | The map has 11 entries. Several entities (`Site`, `Classification`, `Contact`, `POSchedule`, `PurchaseOrderLine`, `PODistribution`) have no entry; their `output_name` falls back to `entity_name.lower()`. The fallback makes the map's coverage invisible. | `grep -c "_OUTPUT_NAME_BY_ENTITY\[" src/` — if 0, the map is only read via `.get()`, silent partial coverage |
| C-10 | `src/spire/mcp_server/tools/purchase_order_schedules.py` — `ReceivedAmount` | Projected and returned on every schedule row; `po_lifecycle.py` docstring says the value is 0 or null on every row on this pod (~4,500 checked). The lifecycle derives received from quantities; the field is dead weight on the wire. | `grep -rn "ReceivedAmount" src/` |
| C-11 | `scripts/verify_bug*.py`, `scripts/apply_bug1_step2_context_assembly.py`, `scripts/t_s1_*.py`, `scripts/probe_cache*.py` | Scratch scripts from S1 remediation and cache-probing. Not referenced by any module in the read bundles; each is self-contained. Confirmed 2026-09-18: no module imports any of these; the only grep hit is a docstring reference, not an import. | `grep -rn "verify_bug1\|t_s1_repro\|probe_cache" src/ tests/` — ran 2026-09-18: one hit, a docstring in `tests/test_bug1_step3_supplier_details.py` naming `scripts/verify_bug1_step3.py`. Not an import. |
| C-12 | `docs/designs/*.puml` and `*.svg` | Excluded from bundles by `build_context.py` (`.puml`, `.svg` in `DEFAULT_EXCLUDES`). §C candidate only if "dead code" is read broadly to include documentation artifacts. | Not applicable — the exclusion itself is the classification |

### C.3 Unreachable — need a bundle share

- `tests/*` — unused helpers, skipped tests, imports of removed modules.
- `scripts/*` — unused imports in `promptkit.py`, `run_graph.py`, `rebuild_kg.py`, `draw_graph.py`, `build_classifier_context.py`.
- `promptkit_sets.yaml` and `scripts/prompts/*` — unused prompt entries.
- `personas.example.yaml` — drift from `personas.yaml` if any.

### C.3 — Closed 2026-09-18

The four remaining bundles were read (`prompts` earlier; `scripts`, `tests`, `corpora` this session). Findings:

| ID | Where | What | Confirm |
|---|---|---|---|
| C-13 | `scripts/prompts/scorer/tool_selection.txt` | Corpus file whose header names its runner as `scripts/validate_tool_selection.py`. That script does not exist in the repository. The corpus is dead — nothing reads it. | `grep -rn "validate_tool_selection" src/ scripts/ tests/` — expect one hit, the header comment in this file. `ls scripts/validate_tool_selection.py` — expect not found. |
| C-14 | `scripts/prompts/README.md` Layout section | Lists 10 prompt files (`00`–`10`, `qa_testcases`, `README.md`, `scorer/parser_stress.txt`). The source tree has 15 — missing `11_column_vocabulary.txt`, `12_po_supplier_include.txt`, `mini.txt`/`mini.json`, `new/retest_prompts.txt`, `scorer/tool_selection.txt`. | `ls scripts/prompts/` vs the README's Layout block. |
| C-15 | `scripts/prompts/mini.txt` / `mini.json` | Six-prompt ad-hoc test set. Not in `promptkit_sets.yaml`. Not in the README's Layout. No runner references it. | `grep -rn "mini" scripts/promptkit_sets.yaml scripts/prompts/README.md` — expect zero. |
| C-16 | `scripts/prompts/new/retest_prompts.txt` | One-off re-test set whose header names a past analysis ("the dumps ran on gemini-3.6-flash") and a model version not used today. No runner references it. | `grep -rn "retest_prompts" src/ scripts/ tests/` — expect zero. |

**Two scripts kept alive by tests** (recorded because §C would otherwise read as if all scripts are unreferenced):

- `scripts/promptkit.py` — loaded by `tests/test_promptkit.py` via `importlib.util.spec_from_file_location`.
- `scripts/inspect_trace.py` — loaded by `tests/test_inspect_trace.py` via `sys.path.insert`.

**Unused-import check on the five named files:** clean. No unused imports found.

**Test-skip check:** no permanently-skipped tests. Every `pytest.mark.skipif` in the tests bundle has a satisfiable condition.

**Not checked:** `personas.example.yaml` vs `personas.yaml` drift — `personas.yaml` is excluded from every bundle for credential reasons. The comparison needs both files pasted directly, or `diff personas.example.yaml personas.yaml`.

### C.4 Notes

- **C-06 is F-003's raw inventory.** F-003 records the harm of `modes/` being unreachable; C-06 records that six files sit in that state. F-003's fix closes both. Cross-referenced above.
- **C-01's cleanest endpoint** is not deletion but either (a) retirement plus test rename, or (b) re-registration if the tool is still wanted. The `suppliers.py` docstring's "supersedes" is a design statement; a follow-on should confirm the design still holds.
- **C-05's grep needs `\b`.** Without the word boundary, `find_entity_tool` matches on every call site in `planner.py` and `plan_builders.py` and the orphan claim is invisible.
- **§C's format** follows the audit's other sections: an ID-prefixed table per subsection. Split into C.1/C.2/C.3 because the read-scope is genuinely partial; the C.3 rows close when the remaining bundles are read.
- **Methodology note.** C.1's rows were confirmed by reading the bundles, then by greps where the grep output was captured (C-01, C-05 ran 2026-09-18). C.2's rows are drafts; every "Confirm" line is a proposed command, not an executed one.

### C.5 What I did not do

Updated 2026-09-18. The earlier version of this section listed proposed-but-unrun greps and unnamed "not checked" scopes; most are now closed by the §C.5 greps (2026-09-18) and the §C.3 sweep (2026-09-18).

Still not checked:

- (closed 2026-09-18) `personas.example.yaml` vs `personas.yaml` — diffed. No schema drift: both files carry the same key structure (`fusion.{base_url, username, password, auth_type}` and `oracle.{dsn, username, password}`). The differences are three, all benign at the schema level: (1) the example carries a ten-line documentation header the live file does not need; (2) the example's values are placeholders where the live file's are real; (3) the live file carries multiple commented-out persona blocks, which the example does not. Items (1) and (2) are expected; item (3) is a credential-hygiene note that belongs with the deferred personas.yaml-untrack task (E-05), not with §C.
- `src/spire/agent/`, `src/spire/api/`, `src/spire/ui/`, `src/spire/oracle/` — read only via what appeared in other bundles.
- Parts of `src/spire/executor/` beyond what appeared in the `graph_kg` bundle.
- `tests/manual/ui/` (a checklist file only, per source-tree.txt).
- `docs/archive/` (excluded from bundles by design).

Resolved this session:

- C-02, C-04, C-06 confirmed; C-03 and C-07 corrected (2026-09-18 §C.5 greps).
- §C.3's three parts swept; C-13 through C-16 added.
- C-11's Confirm expectation corrected: the grep returns one hit (a docstring, not an import).

---

## §D. Inconsistency inventory

### D.1 Confirmed

| ID | Where | What | Note |
|---|---|---|---|
| D-01 | `Show invoice lines for invoice 300000248096352` refusal | Router chose `payables`; reason names `ReceivablesInvoiceLine`. | Entity family named does not match routing decision. |
| D-02 | `suppliers with the highest quality score` refusal | Solution: "…total or average." | Aggregation template applied to a field-availability refusal. |
| D-03 | `Addresses for supplier 1252` vs `everything about supplier 1252` | Two different messages for the same root cause. | The second is factually wrong about `name_fragment`. |
| D-04 | Truncation wording | `Suppliers with their addresses` prints "25 examined for filtering" when no filter requested. | Fixed in F-036 (PR #157). |
| D-05 | `Purchase orders created before 2015` | Truncation block present in one run, absent in another. | Closed in F-040 (N=20 clean). |
| D-07 | `Show PO 2144 and its lines` vs `How much of PO 2144 was received?` | `"PO 2144"` routed to `by_id` vs `lifecycle_status`. | Cross-reference B-11. |
| D-09 | `12_po_supplier_include.txt` prompts 7–15 | Seven prompts produce byte-identical answers. | Cross-reference B-15. |
| D-10 | `07_alacarte.txt` and `11_column_vocabulary.txt` | Duplicated prompts within and between files. | Test-set hygiene. |
| D-11 | `Compare ordered vs invoiced for our top 3 suppliers` | "under-invoiced by 864,399,645.92" is accurate but invites misreading. | Fixed in F-039 (PR pending). ~1% of invoices are PO-linked on these pods. |
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

## ¬ßE. In-flight work inventory

*Drafted 2026-09-18 from the handoff, `WORKING_STYLE.md`, `source-tree.txt`, and the bundles read this session. Branch-state claims are "as named in the branch list, not verified by `git log`"; each carries a proposed command.*

### E.1 Named in-flight items (from the handoff)

| ID | Item | State | Source |
|---|---|---|---|
| E-01 | **S1 — planner throws raw KeyError instead of degrading/refusing.** The unsupported-include path lacked the graceful handling the unsupported-filter path has. Partially addressed by BUG-3 (`RefusalError` wrap); whether S1 is fully closed needs re-verification. | open — partially addressed | `SPIRE_SESSION_HANDOFF.md` |
| E-02 | **S2 — the LLM model is a silent dependency.** Switching `GEMINI_MODEL` in `config.py` measurably degrades routing; nothing warns. | open | `SPIRE_SESSION_HANDOFF.md` |
| E-03 | **S3 — `--generate` freezes classifier flakiness into the corpus.** A single non-deterministic classify run is written as the corpus `module` value. | open | `SPIRE_SESSION_HANDOFF.md` |
| E-04 | **Carry-forward: main register verification pass.** `docs/spire_overnight_findings.md` lists ~14 issues as open/verified, not re-verified against current code. | open | `SPIRE_SESSION_HANDOFF.md` |

### E.2 Explicitly deferred (already recorded elsewhere)

| ID | Item | State | Source |
|---|---|---|---|
| E-05 | **`personas.yaml` untrack (task 1.1).** Deferred to end of plan; not recorded as a deviation. | deferred | `WORKING_STYLE.md` §16 |
| E-06 | **Integration tests (the 22 marked `integration`).** Not run, not investigated, not fixed during Phase 1. | deferred | `WORKING_STYLE.md` §17 |

### E.3 Scratch artifacts (per `source-tree.txt`, not referenced by any module in the read bundles)

| ID | Artifacts | Note |
|---|---|---|
| E-07 | `scripts/t_s1_isolate.py`, `scripts/t_s1_repro.py` | Isolation/repro harnesses for S1. The landed fix (BUG-2/BUG-3) has tests; the ad-hoc scripts are cleanup candidates. |
| E-08 | `scripts/verify_bug1.py` through `verify_bug4.py` (5 files), `scripts/verify_bug1_step2.py`, `scripts/verify_bug1_step3.py`, `scripts/apply_bug1_step2_context_assembly.py` | Verification and apply scripts for the S1 remediation. Each BUG-N has a corresponding `tests/test_bugN_*.py` that is the durable artifact. Scripts are cleanup candidates (same shape as C-11). |
| E-09 | `scripts/probe_cache.py`, `scripts/probe_cache_v2.py` | Cache-probing scratch. The prompt cache is now covered by `tests/test_prompt_cache.py`. |
| E-10 | `test_tools/try_po_lifecycle.py`, `test_tools/verify_rank_invoices.py` | Manual test helpers. No automated use; not in the test suite. |

### E.4 Parked / off-plan (per the branch list)

| ID | Item | Note |
|---|---|---|
| E-11 | **`phase-4d-ui-api` branch.** Corrected 2026-09-18: this is Phase 4d of the v3.2 plan, marked Complete in Doc A §6 and §10.7 on 2026-09-15 — not a parked off-plan branch. | `git log --oneline phase-4d-ui-api \| head` ran 2026-09-18: branch exists locally; tip is `1b7733e phase 4d: FastAPI backend + Streamlit UI for SPIRE`, with no commits on top of the 4d work. Recent history also carries the parser-prompt-cache merges (PRs #143, #144) and three "Defining/Reordering scope" commits from earlier phases. Merge state into `hardening-master` confirmed 2026-09-18: `git log hardening-master..phase-4d-ui-api --oneline` is empty — every commit on the branch is in `hardening-master`. |
| E-12 | **`feature/ar-prompt-18-parking` (referenced in KG seed comments).** A `lag_query` filter and a `get_receipts_with_lag` entity tool were live in the KG database but in neither the seed nor `hardening-master`; the code sits on this parked branch. The KG rows were removed to reconcile seed and database (per the `kg_schema.sql` `kg_entity_filter` seed comment). | `git branch -a \| grep prompt-18` ran 2026-09-18: branch exists on origin as `remotes/origin/feature/ar-prompt-18-parking`. Remote-only; not checked out locally. The earlier "not in the visible branch list" clause was true of the local list only. The branch's commits were not inspected beyond the grep — what prompt-18 carries beyond the lag work is still unknown. **Cross-ref: F-029.** |

| E-13 | **`fix/overnight-20260904`, `fix/overnight-batch2`.** Named as overnight fix batches; whether they are merged into `hardening-master` or carry unmerged work is not visible from the branch list alone. | `git log hardening-master..fix/overnight-20260904 --oneline` and the batch2 equivalent both ran 2026-09-18: **both empty.** No commits on either branch are outside `hardening-master`. Both are fully merged; no unmerged work to absorb. Row closes. |
| E-14 | **`feat/parser-prompt-cache`, `feat/router-show-parser-diagnostic`.** Per the handoff, the router diagnostic is merged (`34044d8`, `16a22f6`, `b0cb73e`); whether the branches themselves are still live is a hygiene question. | `git branch --merged hardening-master \| grep feat/` ran 2026-09-18: outputs `feat/parser-prompt-cache` and `feat/router-show-parser-diagnostic`. Both feature branches exist locally and are merged into `hardening-master`. No further hygiene work required; optional cleanup is `git branch -d` on each. |

### E.5 Not inspected

- `docs/spire_overnight_findings.md` (the "main register" E-04 refers to) — not read.
- Uncommitted work on any branch — not inspected.
- The commits on `feature/ar-prompt-18-parking` beyond the lag work — not inspected; what prompt-18 carries is unknown.

### E.6 Notes

- **E-01 is the only item that overlaps a finding written this session.** F-006 confirmed the S1 crash does not reproduce for its specific reproducer (`What is purchase order US164932 about? Show its lines.`). But S1 in the handoff is broader — "planner NEVER throws raw; always degrades or refuses" is the goal, and one reproducer passing does not close it. E-01 stands as in-flight.
- **E-04's register has been partially addressed by this session.** Three of the overnight register's likely issues (intermittency, aggregate nondeterminism, count variance) closed clean (F-022, F-023, F-024), but the register itself has not been re-read.
- **E-07 through E-10 are the same cleanup class as §C.2's C-11.** If C-11 is retired, these should be retired in the same pass — the argument for deletion is identical (the landed fix has a durable test; the scratch script served its purpose).

---

## ¬ßF. Baseline metrics

*Drafted 2026-09-18. The suite and validate counts are cited from the handoff and not re-measured this session; the token table is measured from this session's `Token usage:` blocks. Anything requiring a fresh test run carries a "verify" line.*

### F.1 Suite and routing baselines

| Metric | Value | Source | Status |
|---|---|---|---|
| Test suite (master) | 1011 passed, 22 deselected | `pytest -q`, 2026-09-18 | measured — 3m43s. Supersedes the prior handoff's cited 913/18; suite grew ~95 tests since that snapshot. |
| `--validate` pass rate (12-set, `gemini-3.5-flash`) | 236 / 240 | `SPIRE_SESSION_HANDOFF.md` | cited; not re-run this session |
| `--validate` pass rate (`gemini-3.1-flash-lite`) | 205 / 240 | `SPIRE_SESSION_HANDOFF.md`, S2 | cited; the degradation that motivated S2 |
| KG tables matching seed (9 tables) | 9 / 9 | `print_kg.py --counts-only`, 2026-09-18 | measured (A-17) |
| Golden-file byte-diffs matching | 1 / 3 (byte-identical); 2 / 3 pod-drift only | `docs/audit/golden/`, 2026-09-18 | measured (§G) |

### F.2 Per-prompt-class token usage

Twenty-one prompts run this session with full `--show-stages`. Totals are the `TOTAL in= / out=` line from each run's `Token usage:` block. Input includes the two classify calls (F-002) and the parse. Output includes classify, parse, and any synthesizer call.

| Class | Prompt | in | out | Notes |
|---|---|---|---|---|
| Count | `count of suppliers` | 4,412 | 397 | smallest output; no LLM synthesis |
| Count | `count of suppliers with classification Minority Owned` | 4,424 | 559 | F-010 (wrong bucket) |
| Entity list | `addresses for supplier 1252` | 4,427 | 1,388 | F-009 (rule unreachable) |
| Entity list | `Get Supplier contacts` | 4,412 | 1,005 | F-020 (run-on narration) |
| Single entity | `Show PO 2144 and its lines` | 5,022 | 615 | golden byte-identical |
| Single entity | `How much of PO 2144 was received?` | 5,028 | 2,059 | F-013 (lifecycle, resolved) |
| Single entity | `Show the AR invoice with CustomerTransactionId 1002 and its tax lines` | 5,382 | 1,019 | counter-example to F-007 |
| Aggregate | `Top 10 suppliers by spend in 2022` | 4,445 | 1,000 | F-023 (stable at N=20) |
| Refusal | `purchase orders older than 6 months` | 5,013 | 633 | F-011 (KG/sysprompt drift) |
| Refusal | `show details for invoice number LEE-01-1006-111` | 3,924 | 1,432 | F-018 (identifier dropped) |
| Composite filter | `invoices for supplier 1252 over 10000` | 4,973 | 1,089 | F-012 (overfetch cap) |
| Filtered count | `suppliers with classification Minority Owned` | 4,418 | 597 | F-008 |
| Account resolve | `Trace receipt applications for account 25750` | 5,364 | 1,641 | F-019 |
| PO status | `purchase orders closed for receiving` | 5,007 | 1,090 | A-16 probe 1 |
| PO status | `purchase orders pending signature` | 5,004 | 1,164 | A-16 probe 3 |
| PO status | `held purchase orders` | 5,001 | 1,274 | A-16 probe 2 |
| PO include | `PO 701337 including the supplier's address and classifications` | 6,098 | 3,066 | **largest output this session**; F-025 (design refusal) |
| Empty child | `Get tax lines for invoice 300000248096352` | 5,394 | 1,691 | F-007 |
| Truncated-to-zero | `Show receipts for ABC Corporation Americas at Santa Clara` | — | — | run captured, totals not extracted |
| Corpus prompt | `What is purchase order US164932 about? Show its lines.` | — | — | F-006; totals not extracted |
| Corpus prompt | `Show PO 2144 and its distributions` | — | — | run 20 times (F-022); totals not extracted per run |

**Observations from the table.**

- **Input cost is roughly flat** at ~4,400–6,100 tokens across every prompt class. The variation tracks the length of the assembled parser context (the scoped subset), not the prompt. The two largest inputs — `PO 701337 with address and classifications` (6,098) and `suppliers with open purchase orders` (6,068) — both routed to two modules, adding the second module's `.sysprompt` blocks.
- **Output cost varies by 8×** (397 → 3,066). The three highest — F-025's PO include (3,066), F-013's lifecycle (2,059), F-007's tax lines (1,691) — all involve a multi-step plan or a long synthesizer narration. The three lowest — F-024's count (397), F-010's filtered count (559), F-008 (597) — all resolve without synthesis.
- **Two classify calls per prompt (F-002) are ~25% of input.** The `Token usage:` block prints two `classify` lines; their combined input is roughly 1,100 of every run's ~5,000 input. Fixing F-002 would reduce every prompt's cost by roughly the same amount.

### F.3 Not measured

- `pytest -q` re-run 2026-09-18. A first attempt with the pod down returned `957 passed, 54 failed, 22 deselected` — every failure a `503 Service Unavailable` against `eqjz.ds-fa.oraclepdemos.com`. Not a code regression. After pod recovery, the same suite returned `1011 passed, 22 deselected in 3:43` — the two runs reconcile exactly (`957 + 54 = 1011`). The prior handoff's cited 913/18 is superseded. Design note for Phase 4b: the 54 pod-dependent tests are NOT `@pytest.mark.integration` — they only `skipif(not PERSONAS_FILE.exists())`, so with `personas.yaml` present and the pod down they fail rather than skip. The 22 deselected are the genuinely-marked integration tests. `pytest -q` is therefore not a pod-independent gate today.
- No `--validate` run this session — the 236/240 figure is cited from the handoff.
- No latency figures. Wall-clock timing was not captured; the F-022 and F-023 loops ran to completion without timing instrumentation.
- No cost-in-currency figures. Token totals are the raw counts from the `Token usage:` block.
- The token table covers 18 of the 21 prompts run this session. Three rows are `—`: the totals were not extracted from those runs' pastes. Not re-run for the table.
- No comparison to a prior session's totals. This is the first baseline of its kind in the audit.

### F.4 Notes

- **This table is a snapshot, not a target.** Its value is that a future session can compare against it after Phase 2 fixes land — e.g. does F-002's fix halve per-prompt input as predicted; does F-020's fix reduce the supplier-contacts prompt's output.
- **The `—` cells could be filled cheaply.** Three prompts re-run would complete the table; each is one command. Deferred unless a specific comparison needs them.
- **§F.1's cited values carry the same "verify" caveat as §B's other cited figures.** The audit's own methodology (§Methodology) says "a claim is confirmed only when the command and its output are pasted." The 913 and 236/240 figures are pasted elsewhere (the handoff) but not re-run here.

---

## ¬ßG. Behavioural byte-diffs

Golden files at `docs/audit/golden/`. Re-run 2026-09-18. Each run filtered to the semantic content — `Router:`, `Intent:`, `Plan:`, `Outputs:`, `Answer:`, `Summary:` — excluding `[llm]` token lines, `[cache]` lines, `[debug]` shape lines, and the `Token usage:` block, which vary by invocation.

| File | Prompt (inferred) | Diff | Disposition |
|---|---|---|---|
| `count_suppliers.txt` | `count of suppliers` | 1 line: `There are 431 suppliers.` → `There are 620 suppliers.` | Pod growth; regenerate golden. |
| `po_2144_and_lines.txt` | `Show PO 2144 and its lines` | Identical (byte-for-byte after filtering) | Clean; no action. |
| `suppliers_with_open_pos.txt` | `suppliers with open purchase orders` | 4 lines: module-set order (`['procurement', 'supplier']` → `['supplier', 'procurement']`); supplier count `431` → `620` in three places (summary, truncation note, narrowing tip) | Pod growth (3 lines) + module-order variance (1 line); regenerate golden. |

### G.1 Observations

- **Pod growth is real and monotone.** The golden captures 431 suppliers; today is 620. Four sample points: 450–455 (audit time), 593 (earlier this session), 600 (F-024's loop), 620 (here). §B.1's B-c2 row anticipated this ("some may be pod growth during the audit"). Goldens keyed on the pod's own counts will drift on every regeneration; either write a pod-state header (supplier count, date) into each golden so the drift is explicit, or drop the count-bearing lines from the byte-diff.
- **Module-set ordering varies run-to-run and does not affect the answer.** `suppliers_with_open_pos` produced `['procurement', 'supplier']` in the golden and `['supplier', 'procurement']` today — same set, different order; `classify_modules` preserves the model's returned order via a first-seen dedup. This is the third corroboration this session of the handoff's claim that the module set is a diagnostic, not a correctness signal (F-023 recorded the second). Goldens that capture the `Router:` line will always show one spurious diff on any multi-module prompt. Options: drop `Router:` from the byte-diff, normalize module order before comparing, or accept the noise as a known artefact.
- **`po_2144_and_lines.txt` is a working regression guard.** Header and line data stable; the PO the audit sampled has not changed. This is the one golden currently functioning as intended.

### G.2 What was not done

- The `Token usage:` block was filtered out of the comparison. Whether to track totals as a cost metric (potentially §F material) is separate.
- No golden was regenerated this session. Whether to overwrite in place or archive before refreshing is a decision for the audit owner.
- No new goldens were added. Prompts now covered by findings (e.g. `Show PO 2144 and its distributions`, or F-022's N=20 run of the same prompt) are candidates, but adding them is Phase 2 work, not this pass's.

---

## §H. Probabilistic-behaviour map

### H.1 Confirmed observations

- **`Show PO 2144 and its distributions` is intermittent.** 1 failure in 7 (~14%). Step 1 returns empty; downstream steps empty; synthesizer prints "No POs found." `cache_mode: None` confirms execution cache not involved. **Closed 2026-09-18.** Re-run at N=20 (the threshold this note set): twenty clean runs, byte-identical (`Records returned: 5`, `Final raw output: 2 record(s) under 'podistribution'`). F-022, closed-as-not-a-bug.
- **Aggregate totals are nondeterministic across runs.** `Top 10 suppliers by spend in 2022` vs `Which suppliers did we spend the most with in 2022`. Both succeed; both see different rows. Same class as `/standardReceipts` ordering instability. **Closed 2026-09-18.** Twenty same-phrasing runs of the first prompt, byte-identical (`Top 10 of 50 suppliers by spend.` / `EIP Inc leads with 141,171,590.98 — 3.3x the next.`). Cross-phrasing run produced an identical intent and identical totals. F-023, closed-as-not-a-bug. Note the two phrasings routed to different module sets (`['procurement', 'supplier']` vs `['supplier']`) and produced identical answers — corroborating the handoff's observation that the module set is a diagnostic, not a correctness signal.
- **Supplier count varies widely across files.** 450 / 451 / 452 / 453 / 455 observed. Some variation is legitimate (`status=ACTIVE` vs unfiltered); some may be pod growth during the audit. **Closed 2026-09-18.** Twenty runs of `count of suppliers` in a single session, byte-identical at `There are 600 suppliers.`. The variance is cross-prompt (different prompts count different sets) plus pod growth, not same-prompt instability. Three sample points corroborate growth: 450–455 (audit), 593 (earlier in this session), 600 (this run). F-024, closed-as-not-a-bug.
- **Relative date window resolution is not stable.** "last year" resolved to 2024-01-01–2025-01-01 in one file and 2023-01-01–2024-01-01 in another.
- **Truncation metadata is nondeterministic.** `Purchase orders created before 2015` — block present/absent across runs.
- **Parse-stage empty-draft retry is systemic.** `[parse] empty draft … retrying once` appears in **seven** files. Each retry succeeds. **Material to Phase 6c.**
- **Parser output length varies across runs on identical cached input.**
- **Insertion-order bias in all supplier scans.** Same first-25 list across prompts and files.
- **`MatchedCountry` field injected by `search_suppliers`.** See A-19.
- **Parser prompt cache is live and hitting on all sampled prompts.**
- **`ReferenceTransactionId` id-space anomaly.** One receipt-application record with a 300-billion-range id.
- **`Get Supplier contacts` produces the largest answer observed.** 25 suppliers × their contacts, ~117 records (this session: 92 contacts, 25 suppliers). Reproduced 2026-09-18; the run-on administrative-contacts sentence (47 names, comma-joined, unattributed) is F-020 / B-27. Open — F-020 records the mechanism (unbounded `', '.join(...)` over a nested comprehension in `synthesize_response`) and the fix options; the finding's audit-row classification was refined from "cosmetic" to "narration defect" (the reader cannot verify `is_administrative` against the displayed tables, which do not show the flag).

---

## Cross-references

- Session log: Doc B `01_Phase_01_Audit_and_Baseline.md`.
- Doc A §7.3.3, §7.4, §7.5.

---

*End of Phase 1 audit. §A complete 2026-09-18; §B complete 2026-09-18; §C, §E, §F, §G drafted 2026-09-18; §D, §H under active revision. Last refreshed 2026-09-22.*
