# Spire — Executive Summary (Internal)

**Date:** 2026-07-24
**Audience:** internal — Bhagavan, Siva, next session
**Purpose:** current-state snapshot after a full verification-and-fix
session. Written to be honest about what is verified, what is claimed, and
what has never been observed running.

---

## 1. What Spire is

An AI-native natural-language query system over Oracle Fusion Cloud
procurement (P2P) and receivables (AR) data. Deterministic KG-driven
pipeline — **parse → plan → execute → synthesize** (Design 3). Tool
selection is a knowledge-graph lookup, not an LLM judgment. Not an agent
architecture.

Two LLM boundaries: the parser (NL → Intent) and the synthesizer
(rows → prose + structured response). Everything between them is
deterministic.

---

## 2. Modules supported

| Module | Status | Tools | Endpoints | Notes |
|---|---|---|---|---|
| **Supplier** | Complete | 6 | 5 | Filters, contacts, addresses, sites, classifications, counts, spend aggregation |
| **Purchase Order** | Complete through P6c | 9 | 3 | Detail, lines, schedules, distributions, received-vs-ordered, invoiced-vs-ordered, aggregates |
| **AP Invoice** | Complete | 3 | 1 | By supplier, by PO, date and amount ranges |
| **Accounts Receivable** | ~17 of 18 prompts built | 13 | 4 | Invoices, lines, tax lines, DFF, credit memos, account balance, receipts, receipt applications, exposure ranking, receipt-method distribution |
| **Buyer** | Complete | 1 | 1 | Cross-pillar (FSCM → HCM) |
| **Total** | | **32** | **11** (14 incl. child paths) | |

Tool counts are MCP-exposed tools (`@mcp.tool()` in `server.py`), assigned
to the module whose entity they root on. The three comparison tools span
PO and Invoice; each is counted once, under the module it is invoked from.
Endpoint counts are distinct top-level Fusion resources; child and
grandchild paths under the same resource are not double-counted except
where the child is a genuinely separate resource with its own projection
(the supplier children).

**Not yet supported:** Contracts, payment terms, supplier ratings/quality
scores, requisitions, sourcing, inventory. These refuse cleanly rather
than guessing — verified.

---

## 3. Fusion endpoints in use

Derived from the tool sources. **11 distinct endpoints**, several with
child and grandchild paths.

### Procurement (FSCM) — 6

| Endpoint | Used by |
|---|---|
| `/suppliers` | supplier search, addresses (via `expand=addresses`), count |
| `/suppliers/{id}` | supplier by id |
| `/suppliers/{id}/child/sites` | site-by-business-unit filter |
| `/suppliers/{id}/child/businessClassifications` | classification filter |
| `/suppliers/{id}/child/contacts` | supplier contacts |
| `/invoices` | AP invoice search, spend aggregation, invoiced-vs-ordered |

### Purchase Orders (FSCM) — 3

| Endpoint | Used by |
|---|---|
| `/purchaseOrders` | PO search, by id, status breakdown, value ranking, open-PO summary |
| `/purchaseOrders/{id}/child/lines` | PO lines |
| `/purchaseOrderSchedules` | schedules (flat endpoint); distributions via the deep nested path |

### Receivables (FSCM) — 4

| Endpoint | Used by |
|---|---|
| `/receivablesInvoices` | AR invoice by id, lines, tax lines (grandchild), transaction DFF |
| `/receivablesCreditMemos` | top-level credit memo list + total |
| `/receivablesCustomerAccountActivities` | customer account resolution by name; **seven children**: transactions, credit memos, receipts, receipt applications, adjustments, payment schedules, transactions-paid-by-others |
| `/standardReceipts` | top-level receipts, site-filtered receipts, receipt-method aggregation |

### HCM — 1

| Endpoint | Used by |
|---|---|
| `/publicWorkers` | buyer lookup (the `/buyers` endpoint does not exist on this pod) |

---

## 4. Knowledge graph size

| Table | Rows |
|---|---|
| `kg_entity` | 22 |
| `kg_entity_field` | 194 |
| `kg_edge` | 17 |
| `kg_edge_tool` | 16 |
| `kg_entity_tool` | 10 |
| `kg_entity_filter` | 25 |
| `kg_vocabulary` | 97 |
| `kg_pattern` | 3 |
| `kg_pattern_binding` | 3 |

**Tripwire drift, unresolved:** `kg_entity_tool` reads 10 against an
expected 9; `kg_entity_filter` reads 25 against an expected 23. Rows were
added without bumping the expected values in `scripts/print_kg.py` and
`tests/test_kg_metadata.py`. `test_kg_metadata.py` is failing on this.

---

## 5. MCP tools

**32 tools** exposed by `server.py`, backed by ~25 standalone tool
modules. Breakdown by kind:

- Search / list: 8
- By-id fetch: 5
- Child traversal: 9
- Aggregation: 6 (invoice spend, PO value, PO status, open-PO summary, exposure ranking, receipt-method distribution)
- Comparison: 3 (PO vs invoices, supplier vs invoices, top-suppliers)
- Cross-pillar: 1 (buyer)

---

## 6. Prompt coverage

| Set | File | Prompts |
|---|---|---|
| Purchase Order | `prompt_set_po.txt` | 14 |
| Supplier | `prompt_set_supplier.txt` | 19 |
| Accounts Receivable | `prompt_set_ar.txt` | 15 runnable (+1 placeholder, not built) |
| Dipstick | `dipstick/01_prompt_set_dipstick.txt` | 6 |
| Parser stress | `01_test_prompts_parser.txt` | 60 (scorer format) |
| E2E stress | `02_test_prompts_e2e.txt` | ~50 |

AR is tracked as a numbered 1–18 series. **17 built, 1 unbuilt**
(prompt 16, DSO / cash-collection trends — design pending, spans
`/standardReceipts` plus AR balance).

---

## 7. This session — verification and fixes

The session began with the handoff's own warning that its status was
partly unverified. That warning was correct. **Nine bugs found and
fixed**, all verified end-to-end against the live pod.

| # | Bug | Prompts affected |
|---|---|---|
| 1 | `tool_arg_name: 'supplier'` was a placeholder nothing implemented; value-shape routing (digit → `supplier_number`, else `supplier_name`) missing | Address/supplier, Invoice/supplier |
| 2 | Invoice guard demanded a supplier filter, rejected `purchase_order` — the widening was described in a neighbouring comment but never applied | Invoice/purchase_order |
| 3 | Synthesizer registry key was `ExposureRanking` (PascalCase) where the parser emits `exposure_ranking` | Prompt 10 |
| 4 | Aggregation planner never read `intent.filters`; customer scope silently dropped. Plus a duplicate dict key silently shadowing | Prompt 17 |
| 5 | Server wrapper missing `customer_name` | Prompt 17 |
| 6 | Aggregation tool capped at 500 rows with no pagination — reported a sample as a total (500 of 1,386) | Prompt 17 |
| 7 | Receipt applications over-fetched 500 and filtered client-side; bucket name wrong in **four** places | Prompt 9 |
| 8 | `total_available` discarded by the executor; count reported page size (10) as account total (7,038) | Prompt 9 |
| 9 | Synthesizer expanded a float to the token cap (`1179915.3225` → full IEEE-754 binary expansion) | AR invoices by customer |

**Plus: a validator that had never fired.** The empty-array guard in
`synthesize_response` checked a bucket name that does not exist. It has
been silently passing since it was written. Corrected, it immediately
caught two real failures.

---

## 8. Open issues

### Confirmed this session, unfixed

| Issue | Detail |
|---|---|
| **Column selection does not work** | See section 9 — the largest open gap |
| **`count_only` dropped by the planner** | Intent carries `count_only: True`; the plan ignores it and fetches 25 rows. The answer ("424 suppliers") is plausible but its provenance is unverified |
| **Synthesizer asserts unshown fields** | Seen 5+ times across different prompts: "all currently closed with a balance of 0.00", "the administrative contact is John Kim", "all in USD". Fields absent from the displayed projection. Probably real data behind display truncation — unverified |
| **Page presented as total** | "The query returned 25 suppliers" where 421 exist. The truncation block reports it; the narration does not always use it |
| **Over-generalised narration** | "These suppliers are active and have a 'Spend Authorized' business relationship" — true of the five rows shown, not the set |
| **KG tripwire drift** | `kg_entity_tool` 10 vs 9, `kg_entity_filter` 25 vs 23 |
| **`pytest` has not been run this session** | `execute_plan`'s signature changed from 2 return values to 3. `test_executor.py` very likely asserts the old shape. **Highest-risk unknown.** |

### Structural / carried forward

| Issue | Detail |
|---|---|
| **Row-count ceiling on nested child arrays** | 25 wide rows → synthesizer returns an EMPTY array with a short summary rather than truncating. 10 works. Distinct from the token-cap runaway: output is small, not truncated. Currently handled by capping limits at 10 |
| **Synthesizer arithmetic (Issue 4 in the plan)** | Prompt-level prohibition has repeatedly proved insufficient. The structural fix is to compute in the TOOL and stamp per row |
| **Validator bucket names unverified** | The credit-memo, receipts and `customertransaction` guards use names that were changed on a guess or never changed. `_OUTPUT_NAME_BY_ENTITY` is authoritative. The receipts one is the guard that missed prompt 8's empty array |
| **Metadata block is hardcoded** | `_build_synthesis_prompt` special-cases `account_receipt_applications`; does not generalise |
| **Prompt phrasing is load-bearing** | AR prompts 6, 7 and 8 have specific phrasings recorded above them in the prompt set. Alternate forms ran the parser away. May now be historical — not re-confirmed across the set |

### Never observed running

Prompt 13 (site-filtered receipts, "Santa Clara"). Note the trap: Santa
Clara spans accounts 26360 AND 26370, and composite `q=` returns a silent
zero on `/standardReceipts`.

---

## 9. Column selection — status: NOT WORKING

Design intent: a user names the columns they want and the output honours
them. Four variants tested tonight against the same query (active
suppliers).

| Prompt | Parsed `fields` | Result |
|---|---|---|
| "Show only supplier name and status for active suppliers" | `['Supplier', 'Status']` | **Ignored** — 6 columns returned |
| "Just the names of active suppliers" | `['Supplier']` | **Ignored** — 6 columns returned |
| "Supplier number and country for active suppliers" | parsed | **MAX_TOKENS runaway**, `in=16881` |
| "Supplier name, number, status and country for active suppliers" | parsed (`out=820`, 3× normal) | **MAX_TOKENS runaway**, `in=16881` |

**Two distinct defects.**

**9a. `fields` is parsed but never applied.** The parser extracts the
field list into the Intent correctly. Nothing downstream uses it.
`_project_outputs(outputs, fields)` exists in `graph/pipeline.py`, but
`run_plan.py` calls `execute_plan` and `synthesize_response` directly and
never invokes it. Evidence: asking for ONE field and asking for TWO
produced **byte-identical output** — same token counts, same answer text,
same six columns.

**9b. Requesting `country` triggers an over-fetch that overruns the
synthesizer.** Both failing prompts name `country`. Synthesizer input was
16,881 tokens against 2,729 for the working prompts — six times the
payload. Per the KG, `Supplier`/`country` is `client_side` with the note
"Country lives on the addresses child; over-fetch." Requesting country as
a FIELD appears to trigger the same address expansion used for country
FILTERING, pulling every supplier's addresses into the payload.

Prompt 4's parse also degraded (`out=820` vs 227–285), so the four-field
form strains the parser before the synthesizer is reached.

**Assessment:** 9a is a missing wire-up — likely small. 9b is a real
design question: field requests and filter mechanisms are being conflated.

---

## 10. What to do next, in order

1. **Run `python -m pytest -q`.** It has not run this session. The
   executor signature change is unvalidated. Everything else is built on
   this.
2. **Bump the two KG tripwires** to 10 and 25 in both `print_kg.py` and
   `tests/test_kg_metadata.py`.
3. **Verify the validator bucket names** against `_OUTPUT_NAME_BY_ENTITY`.
   Three guards are suspect; one of them is the guard that missed prompt
   8's empty array.
4. **Wire up column selection (9a)** — connect the parsed `fields` to
   `_project_outputs` on the `run_plan.py` path.
5. **Investigate the country over-fetch (9b).**
6. **Run prompt 13**, the last never-observed AR prompt.
7. **Design and build AR prompt 16** (DSO / cash-collection).

---

## 11. Method note

Nine fixes landed. The ones that stuck were the ones where a `curl` was
run against the pod BEFORE changing code — the supplier arg routing, the
aggregation pagination, the receipt-application counts. The attempts that
failed and were reverted were the ones reasoned from symptom similarity.

Two specific traps this session, both worth remembering:

- **A handoff diagnosis can go stale.** Issue 6 in the expansion plan
  described a tuple-keying bug in `_load_filter_defs`. That bug had
  already been fixed; the three "broken" prompts were failing for three
  different reasons, and one was not broken at all.
- **Repair code placed before a check disables the check.** A structural
  fallback that populated an empty list ran before the validator that
  tested for an empty list. Removing it revealed the model had never been
  populating that list at all.
