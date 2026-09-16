# SPIRE — Phase 1 Audit

**Phase:** Phase 1 — Audit & Baseline (Doc A §7)
**Task:** 1.5 (registry drift map) in progress; §B–§H pending
**Branch:** `Phase1-Audit-and-Baseline`
**Started:** 2026-09-16
**Last revised:** 2026-09-16

**What this file is.** The audit deliverable for Phase 1 (Doc A §7.3.3).
It is factual — it says what *is*, not what *should be*. Fixes go in
Phase 2 (correctness) or Phase 3 (consistency).

**Method.** A drift row exists when the same fact is carried in two or
more places and the places can disagree. Each row is numbered `A-NN` and
carries: the fact, every place it lives, whether they agree, and what
breaks if they drift further. A row marked *self-enforced* means a test
currently holds the copies in agreement — the coupling still exists, but
it fails loudly rather than silently.

**Scope.** §A is populated from `graph_kg`, `parser_planner`, and
`mcp_server_tools`. It is complete for those three bundles. The
`parser_context` bundle would confirm A-18/A-19 but is not required for
any open row.

---

## §A — Registry drift map

### A.1 Confirmed drift

| ID | Fact | Where it lives | Agree? | Impact |
|---|---|---|---|---|
| A-01 | The full KG schema (tables, columns, CHECK constraints, seed rows) | (1) `scripts/sql/kg_schema.sql` — current. (2) `scripts/rebuild_kg.sh` — an embedded copy of an older version. | **No.** The .sh has no `module` column on `kg_entity`, no `kg_entity_filter` table, 5 entities vs 22, 27 fields vs 210, 4 edges vs 17, ~40 vocab rows vs 120, 2 entity tools vs 10, 3 edge tools vs 16; its `chk_kg_vocabulary_kind` allows 4 kinds vs the current 9. | Running the .sh produces a KG that lacks tables and columns the current planner reads. `rebuild_kg.py` uses the .sql and is correct; the .sh is dead but present, and would mislead. **→ §C.** |
| A-02 | KG row counts | (1) `kg_schema.sql` PROMPT banners. (2) `test_kg_metadata.py::test_kg_table_row_counts_match_v1_1` `expected` dict. (3) `print_kg.py` `expected_rows` per table. (4) `rebuild_kg.sh` banners (stale; see A-01). | Live three agree; the .sh does not. | A test comment warns "FOUR places that must move together" but names three. A count change that misses any live copy fails a test or prints a false "drift" banner. |
| A-03 | Entity list (22 names) | (1) `kg_schema.sql` kg_entity inserts. (2) `test_kg_entity_has_twentytwo_rows` expected list. (3) `test_kg_entity_module_mapping` expected dict keys. (4) `rebuild_kg.sh` (stale; 5 names). | Live three agree; the .sh does not. | Three hand-maintained copies. |
| A-04 | Entity→module mapping | (1) `kg_schema.sql` INSERT rows (`module` column). (2) `test_kg_entity_module_mapping` `expected` dict. (3) `chk_kg_entity_module` CHECK constraint. | Yes. | The CHECK pins the vocabulary; the test pins the assignment. Adding a module means editing the CHECK plus the test plus the seed. |
| A-05 | `vocab_kind` allowed list | (1) `kg_schema.sql` `chk_kg_vocabulary_kind` — 9 kinds. (2) `rebuild_kg.sh` — 4 kinds. (3) `loader.py::_format_vocabulary` `kind_order`/`kind_titles` — 4 kinds. | **No.** | See A-06. |
| A-06 | Every vocabulary kind the KG carries is rendered into the agent's markdown | (1) `kg_schema.sql` CHECK — 9 kinds. (2) `loader.py::_format_vocabulary` `kind_order` — 4 kinds. | **No.** `supplier_status`, `supplier_business_relationship`, `supplier_site_bu`, `supplier_classification`, `field_synonym` are SELECTed by `_SQL_VOCABULARY` and then dropped by the renderer. | A parser reading only the assembled prompt cannot resolve "active suppliers" via `supplier_status`, or "who columns" via `field_synonym`. **→ §B.** |
| A-07 | `kg_entity_tool.mcp_tool_name` → actual MCP tool function names | (1) `kg_schema.sql` (10 rows). (2) `src/spire/mcp_server/tools/*.py` + `server.py` registrations. | **Yes.** All 10 entity-tool rows name a tool that exists and is registered: `search_suppliers`, `search_invoices`, `search_addresses`, `get_purchase_order_by_id`, `search_purchase_orders`, `get_purchase_order_lifecycle_status`, `get_receivables_invoice_by_id`, `get_customer_account_by_name`, `list_receivables_credit_memos`, `search_standard_receipts`. | No live drift. Recorded as a negative result — the tool boundary is currently in agreement. |
| A-08 | `kg_entity_filter.tool_arg_name` (and `_hi`) → tool function parameter names | (1) `kg_schema.sql` (26 rows). (2) tool function signatures. | **Yes.** Every literal arg name matches a parameter: `country`, `status`, `business_relationship`, `supplier_name_contains`, `created_from`/`created_to`, `invoice_date_after`/`invoice_date_before`, `amount_min`/`amount_max`, `po_header_id`, `po_number`, `purchase_order`, `created_before`/`created_since`, `customer_transaction_id`, `customer_name`, `customer_site`. The two value-shape placeholders (`supplier`, `supplier_po`) both resolve to parameter names (`supplier_number`/`supplier_name`, `supplier_id`/`supplier_name`) that exist. | No live drift. See A-31 for a type-vs-behaviour divergence on one of these. |
| A-09 | `kg_edge_tool.mcp_tool_name` → edge-traversal tool function names | (1) `kg_schema.sql` (16 rows). (2) tool signatures. | **Yes.** All 16 edge-tool rows name a tool that exists. | No live drift. |
| A-10 | Foreign-key relationships | (1) `kg_schema.sql` — 8 FK constraints. (2) `print_kg.py::FK_RELATIONS` — 9 tuples (splits `kg_edge.to_entity` out from `.from_entity`). | Agree in substance; differ in granularity. | Two representations of the same facts. Adding an FK means editing both. |
| A-11 | `kg_edge.iter_fields_json` | (1) `kg_schema.sql` — column exists, populated for HAS_DISTRIBUTION and HAS_TAX_LINE. (2) `loader.py::_SQL_EDGES` — does **not** SELECT it. (3) `print_kg.py` `kg_edge` columns — does **not** include it. (4) `lookup.py::find_edge` — SELECTs and parses it. (5) `planner.py::generate_plan` — reads it via `edge.get("iter_fields")`. | **Partially.** Two of four consumers read it; two omit it. | `load_kg_context` and `print_kg` under-describe multi-field iteration edges. **→ §D.** |
| A-12 | `kg_edge.server_filter_rule` | (1) `kg_schema.sql` — column exists. (2) `loader.py::_SQL_EDGES` — does not SELECT it. (3) `lookup.py::find_edge` — SELECTs and returns it. | **Partially.** Planner reads it; loader drops it. | Fact the loader omits. Also for §D. |
| A-13 | `kg_entity.canonical_id_field` vs. presence of a matching `kg_entity_field` row | (1) `kg_schema.sql` — every entity declares a canonical id. (2) `kg_entity_field` rows — `Site` and `Classification` have none. | **No** for those two entities. | Either intentional (filter-only entities) or a gap. **→ §D.** |
| A-14 | Doc A §7.3.3 §A's own example rows | Doc A's example says the entity list lives in five places including `print.py` and `_SYSTEM_PROMPT_PREAMBLE`. | **Partially wrong.** `print_kg.py` carries only the count (A-02), not the list. `_SYSTEM_PROMPT_PREAMBLE` carries entity-keyed rules, not the list. | The plan document's own example is not audit-grade. |
| A-15 | The four Fusion module names (`payables`, `procurement`, `receivables`, `supplier`) | (1) `kg_schema.sql` `chk_kg_entity_module` CHECK. (2) `context_assembly.py::KNOWN_MODULES` — a tuple. (3) `test_kg_entity_module_mapping` expected dict values. | Yes — self-enforced by (3). | Adding a module means editing a CHECK constraint, a Python tuple, a test dict, and the seed. The comment on `KNOWN_MODULES` claims it mirrors the CHECK; nothing enforces that claim at import. |
| A-16 | Supplier business-unit vocabulary (`us1` → `US1 Business Unit`, …) | (1) `kg_vocabulary` WHERE `vocab_kind='supplier_site_bu'`. (2) `context_assembly.py::_SYSTEM_PROMPT_PREAMBLE` — a hardcoded list of the same ten BUs in the `has_site_in_bu` rule. | **Yes, currently — by hand.** Nothing enforces it. | Adding a business unit to the KG leaves the prompt silent; adding one to the prompt leaves the parser unable to resolve it. Highest-risk drift in §A: vocabulary changes are exactly the kind the plan exists to make cheap. |
| A-17 | Supplier business-classification vocabulary (`small business` → `Small Business`, …) | Same shape as A-16 for `vocab_kind='supplier_classification'`. Nine classifications in both places. | **Yes, currently — by hand.** No enforcement. | Same as A-16. |
| A-18 | Filter semantics (`has_open_PO`, `has_no_recent_invoices`, `by_id`, `lifecycle_status`, etc.) | (1) `kg_entity_filter` — the row exists, with `mechanism`, `target_entity`, `query_style`, and `notes`. (2) `context_assembly.py::_SYSTEM_PROMPT_PREAMBLE` — prose blocks teaching when to emit each filter. | **Partially.** The KG is the source of *which* filters exist; the preamble is the source of *when to emit them*. Authored independently. | A filter added to the KG with no preamble rule is silently unemittable by the parser. A preamble rule for a filter the KG does not carry is a promise the planner refuses. Neither case is tested. |
| A-19 | The parser preamble text | (1) `src/spire/nl_parser/context/**/*.sysprompt` — production, assembled from `order.manifest`. (2) `context_assembly.py::_SYSTEM_PROMPT_PREAMBLE` — a literal retained only as the byte-equality oracle for the assembly test. | **Yes — self-enforced** by `tests/test_parser_context_assembly.py`. | Editing a .sysprompt file requires updating the literal in the same commit or the test fails. Right shape; still two places a preamble change must land. |
| A-20 | Tool names and their primary argument names (`search_invoices` → `supplier_number`, `get_purchase_order_by_id` → `po_header_id`, …) | (1) `registries.py::_TOOL_PRIMARY_ARG` — 25 entries. (2) `registries.py::_AGGREGATION_TOOLS` / `_COMPARISON_TOOLS`. (3) actual tool signatures. | **Yes.** All entries in `_TOOL_PRIMARY_ARG` name a parameter that exists. | No live drift. |
| A-21 | The fields an `Address` include is considered to satisfy | (1) `parser.py::_ADDRESS_SATISFIED_FIELDS` — `{country, address, city, state, formatted_address, address_id}`. (2) `intent_validation.py::_FIELDS_SATISFIED_BY_INCLUDE["Address"]` — `{address, addresses, country, city, state}`. | **No.** The two sets differ: (1) has `formatted_address` and `address_id`; (2) has `addresses`. | **Live divergence.** Three fields are treated differently by the two code paths. A request for `formatted_address` is subtracted on one path and reported unresolved on the other; vice-versa for `addresses`. Which is right needs deciding before Phase 2 closes it. **→ §D.** |
| A-22 | Placeholder tool-arg names that route by value shape (`"supplier"` → all-digit `supplier_number` else `supplier_name`; `"supplier_po"` → all-digit `supplier_id` else `supplier_name`) | (1) `plan_builders.py::_VALUE_SHAPE_ROUTED_ARGS` — the live implementation. (2) `kg_entity_filter.notes` for the Invoice/supplier, Address/supplier, and PurchaseOrder/supplier rows — the same rule, in prose. | Yes — but the rule lives in code and its own description lives in a DB note, with no test linking them. | A change to either side leaves the other describing the old behaviour. `plan_builders.py`'s own comment proposes making this declarative. |
| A-23 | The five planner entity guards (Invoice needs supplier, Address needs supplier/country, PurchaseOrder needs filters or `list_all`, ReceivablesInvoice needs `by_id`, StandardReceipt needs customer or site) | (1) `planner.py::generate_plan` — the five `if intent.target_entity == …` blocks. (2) `capability.py::_IDENTIFIER_GUIDANCE` — the per-entity wording each guard's `RefusalError` renders through. | Yes — coupled by convention. | Adding a guarded entity means adding BOTH a guard and an `_IDENTIFIER_GUIDANCE` entry. Forgetting the second yields a generic message. |
| A-24 | The set of entities that cannot be an include (Site, Classification — their only tools are reverse filters) | (1) `intent_validation.py::_NON_INCLUDABLE_ENTITIES` — a two-element frozenset. (2) `kg_edge_tool` — absence of a forward row for HAS_SITE / HAS_CLASSIFICATION. | Yes — by hand. | If a forward tool for Site is ever added, the KG is updated and the code is not, and the include gate keeps refusing valid intents. |
| A-25 | Entity labels for user-facing refusal text | (1) `capability.py::_ENTITY_LABELS` — 22 entries. (2) `kg_entity` — 22 rows. | **Yes — self-enforced** by `tests/test_nl_parser_capability.py`. | Adding a KG entity without a label fails the test. The code cannot fall back to a class name, so the test is load-bearing for message quality. |
| A-26 | Refusal examples (`_FILTER_GUIDANCE`, `_FIELD_GUIDANCE`, `_IDENTIFIER_GUIDANCE`, `_NOT_A_ROOT_GUIDANCE`, `_OPERATION_EXAMPLES`) | (1) `capability.py` — the guidance dicts. (2) `scripts/prompts/10_refusal_examples.txt`. | **Yes — self-enforced** by `test_every_promised_example_is_verifiable`. | Right shape; still two places a new example must land. |
| A-27 | Edge knowledge the parser corrects deterministically before validate_intent: `_CHILD_INCLUDE_WHEN_PRESENT`, `_INCLUDE_OVERRIDE_WHEN_PRESENT`, `_STRIP_INCLUDE_WHEN_NO_EDGE` | (1) `vocabulary.py` — the three tables. (2) `kg_edge` — the actual edge list. | **Partially.** `_STRIP_INCLUDE_WHEN_NO_EDGE` is KG-aware and self-retiring. The other two are hardcoded (child→parent, entity-displacement) with no runtime check. | The two non-self-retiring tables encode KG facts in code. Adding a new child edge does not add a corresponding entry. `_CHILD_INCLUDE_WHEN_PRESENT` even names grandchild entities as *deferred* — a code comment, not a KG fact. |
| A-28 | Which edge-traversal filters get which step shape | (1) `kg_entity_filter` `mechanism='edge_traversal'`. (2) `registries.py::_FILTER_SOURCE_NAME_SUFFIX` — negation filters. (3) `registries.py::_FILTER_SOURCE_NONEMPTY_SUFFIX` — presence-with-value filters. | KG and (2)+(3) agree today. But a filter in the KG's edge-traversal set and NOT in (2) or (3) is treated as a status-style filter — the wrong step shape. | **Silent failure mode.** A new negation or presence filter requires editing the KG row AND one of these two dicts; forgetting the second produces a plan that runs but returns wrong results. |
| A-29 | Every MCP tool the pipeline can dispatch | (1) `kg_entity_tool` (10 rows). (2) `kg_edge_tool` (16 rows). (3) `registries.py::_AGGREGATION_TOOLS` (7 entries). (4) `registries.py::_COMPARISON_TOOLS` (3 entries). | Split across four registries. **The aggregation and comparison tools have no KG representation** — they are selected by the `aggregate`/`compare` block, not by the entity/filter path. | Phase 3's design says the KG will be the single source of truth for tool dispatch. Ten tools are not in the KG and would need a schema change (or a decision to leave them out) before that claim holds. |
| A-30 | The list of tools registered on the MCP server | (1) `server.py` module docstring — 19 tools. (2) `server.py` `@mcp.tool()` decorators — 34 tools. | **No.** The docstring is stale by 15 tools: it omits `aggregate_invoices_by_supplier`, `rank_invoices_by_amount`, all nine AR tools, `get_account_receipt_applications`, `search_standard_receipts`, `rank_customer_accounts_by_exposure`, `aggregate_standard_receipts_by_method`. | Same class as the `context_bundles.yaml` path drift (A.3). A reader relying on the docstring under-counts the surface. **→ §D.** |
| A-31 | `get_purchase_order_by_id`'s declared input type | (1) `server.py` wrapper — `async def get_purchase_order_by_id(po_header_id: int)`. (2) `purchase_order_by_id.py` module docstring + function body — accepts **OrderNumber (string) or POHeaderId (int)**, tries OrderNumber first via `q=OrderNumber='X'`, falls back to `/purchaseOrders/X`. | **No.** FastMCP enforces the `int` annotation via Pydantic before the function body runs, so the resolution logic is unreachable for a string value. | **Direct cause of the `US164932` crash (§A.4).** The parser prompt teaches "pass the number through EXACTLY as given" — the MCP contract rejects anything non-int. Two declarations of the same tool's input, disagreeing. **→ §B.** |
| A-32 | `kg_entity_filter.query_style` for `(StandardReceipt, customer_name)` | (1) `kg_schema.sql` — `query_style='client_side'`, `filter_field='CustomerName'`, `filter_op='equals'`, note says "resolved to account number by the tool before the server call." (2) `standard_receipts.py` — resolves `customer_name` → `AccountNumber` via `get_customer_account_by_name`, then sends `q=CustomerAccountNumber=...` **server-side**. | **No.** The note acknowledges the resolution, but `query_style` says `client_side` while the fetch is server-side. | A future plan-builder that trusts `query_style` would apply a redundant client-side filter, or fail to send the server clause and scan the wrong slice. **→ §D.** |
| A-33 | `kg_entity_filter.query_style` for `(PurchaseOrder, status)` | (1) `kg_schema.sql` — `query_style='client_side'`, `filter_field='StatusCode'`, note says "Applied client-side by search_purchase_orders after over-fetch: SupplierId (if present) takes the server q= clause." (2) `purchase_orders.py` — `status` **is** sent server-side when it is the highest-priority filter (no `supplier_id` present). | **No.** The note describes the case where `supplier_id` also runs; it does not describe the case where `status` alone is the clause. `query_style` cannot express "server-side when alone, client-side when combined." | Same risk as A-32: a plan-builder that reads `query_style` would misroute. **→ §D.** |

### A.2 Cross-bundle rows awaiting confirmation

None. A-07/08/09/20 closed clean against `mcp_server_tools`; A-18/A-19 are self-consistent within `parser_planner`. The `parser_context` bundle would enumerate exactly what entity/filter/vocabulary the preamble carries (to firm up A-16/A-17/A-18) but is not required for any open row.

### A.3 Observations carried into later sections

- **Doc A/Status path in `context_bundles.yaml`.** The config lists `docs/SPIRE_ROBUSTNESS_EXTENSIBILITY_v3.2.md` and `..._Status.md` — neither exists at that path (they moved to `docs/spire-robustness/`). The same config still lists `scripts/display_formatters.py`, moved in WI-S002-01. **→ §D.**
- **`--show-stages` produced no output** on the two promptkit runs of 2026-09-16. Either a no-op flag or a defect. **→ §D.**
- **Double `classify` LLM call per prompt.** Confirmed real across two independent runs (2026-09-16). `router.classify_modules` is called once per `route_and_parse`; the second call comes from a caller above the router. **→ §H, §B.**
- **`test_kg_metadata.py` marker.** The module touches real Oracle but is not marked `integration`, so it runs by default. **→ §D.**
- **`_CLASSIFIER_MENU` load is fail-loud, no fallback.** `context_assembly._CLASSIFIER_MENU` is read at import; a missing file raises `FileNotFoundError`. `load_classifier_menu`'s comment names the regenerator (`scripts/build_classifier_context.py`). Whether the file can go stale against the KG is untested. **→ §C.**

### A.4 Bug inventory preview (for §B, task 1.6)

- **`US164932` crash.** Prompt: `"What is purchase order US164932 about? Show its lines."` Result: `get_purchase_order_by_id` raised a Pydantic int-parsing error. **Root cause is A-31**: the MCP wrapper's `po_header_id: int` annotation rejects a string before the tool's own resolution logic runs. The tool can resolve an OrderNumber; the contract forbids it. **Severity: crash.** The fix is one annotation (`str | int`) in `server.py`, but Phase 1 records it; Phase 2 fixes it.
- **Buyer-name filter.** Prompt: `"Give me all active POs related to the buyer 'White, Eleanor'"`. Result: honest refusal — "Filtering purchase orders by buyer name is not supported." Confirmed by the KG: no `has_buyer` filter row. **Severity: missing-capability.**
- **`StandardReceipt` `account_number` crash (historical).** Documented in `kg_schema.sql` STEP 11: the tool takes `customer_name`/`customer_site` and rejects `account_number`; the stale `kg_entity_filter` row built an argument the tool rejects. Row removed. **Severity: crash (historical).**
- **`lag_query` DB-vs-seed drift (historical).** Live DB carried a `lag_query` filter and a `get_receipts_with_lag` entity tool that were in neither the seed nor `master`. Removed. **Severity: wrong-data (historical).**
- **`test_kg_metadata.py` marker.** **Severity: test-harness gap.**
- **A-06.** Loader drops 5 of 9 vocab kinds. **Severity: wrong-data.**
- **A-28.** A new edge-traversal filter added only to the KG runs with the wrong step shape. **Severity: wrong-data (latent).**
- **A-31.** MCP wrapper annotation rejects OrderNumber inputs to `get_purchase_order_by_id`. **Severity: crash.**

---

## §B — Bug inventory

*To be written in task 1.6. Preview above.*

## §C — Dead code inventory

*To be written in task 1.7. First entries:*
- `scripts/rebuild_kg.sh` (A-01) — a full, runnable, older copy of the schema.
- `src/spire/mcp_server/tools/suppliers_by_country.py` — no longer imported by `server.py`; `suppliers.py`'s docstring says it supersedes this tool.
- `_previous_entity` in `plan_builders.py` — raises `NotImplementedError`; comment says it is a design-symmetry stub and must not be called.

## §D — Inconsistency inventory

*To be written in task 1.8. §A.3 entries feed this section, plus A-11, A-12, A-13, A-21, A-30, A-32, A-33.*

## §E — In-flight work inventory

*To be written in task 1.9.*

## §F — Baseline metrics

*To be written in task 1.10.*

## §G — Behavioural byte-diffs

*Golden outputs already captured to `docs/audit/golden/` in S001. To be verified and completed in task 1.11.*

## §H — Probabilistic-behaviour map

*To be written in task 1.12. The double-classify observation (§A.3) is the first entry.*

---

*End of audit. Phase detail in `00_Doc_B_Index.md`.*