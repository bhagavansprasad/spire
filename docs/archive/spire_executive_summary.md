# Spire — Executive Summary (Internal)

**Date:** 2026-07-24
**Audience:** internal — Bhagavan, Siva, next session
**Purpose:** current-state snapshot after a full 103-prompt verification
run. Written to be honest about what is verified, what is claimed, and
what has never been observed running.

---

## 1. What Spire is

An AI-native natural-language query system over Oracle Fusion Cloud procurement (P2P) and receivables (AR) data. Deterministic KG-driven pipeline — **parse → plan → execute → synthesize** (Design 3). Tool selection is a knowledge-graph lookup, not an LLM judgment. Not an agent architecture.

Two LLM boundaries: the parser (NL → Intent) and the synthesizer (rows → prose + structured response). Everything between them is deterministic.

---

## 2. Modules supported

| Module | Status | Tools | Endpoints | Prompts run | Result |
|---|---|---|---|---|---|
| **Supplier** | Complete | 6 | 5 | 40 | Retrieval clean; page-size and generalisation defects in narration |
| **Purchase Order** | Complete through P6c | 9 | 3 | 9 | Clean |
| **AP Invoice** | Complete | 3 | 1 | — | Exercised via supplier and PO sets |
| **Accounts Receivable** | ~17 of 18 prompts built | 13 | 4 | 16 | 6 wrong or suspicious |
| **Buyer** | Complete | 1 | 1 | — | Not exercised this run |
| **Total** | | **32** | **11** (14 incl. child paths) | **103** | |

Tool counts are MCP-exposed tools (`@mcp.tool()` in `server.py`), assigned
to the module whose entity they root on. The three comparison tools span
PO and Invoice; each is counted once, under the module it is invoked from.
Endpoint counts are distinct top-level Fusion resources; child and
grandchild paths under the same resource are not double-counted except
where the child is a genuinely separate resource with its own projection
(the supplier children).

**Not yet supported:** Contracts, payment terms, supplier ratings/quality
scores, requisitions, sourcing, inventory. These refuse cleanly rather
than guessing — **re-verified this run**, all 9 refusal prompts correct.

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
`tests/test_kg_metadata.py`.

---

## 5. MCP tools

**32 tools** exposed by `server.py`, backed by 26 standalone tool
modules. Breakdown by kind:

- Search / list: 8
- By-id fetch: 5
- Child traversal: 9
- Aggregation: 6 (invoice spend, PO value, PO status, open-PO summary, exposure ranking, receipt-method distribution)
- Comparison: 3 (PO vs invoices, supplier vs invoices, top-suppliers)
- Cross-pillar: 1 (buyer)

---

## 6. Prompt coverage

Prompt sets were reorganised on 2026-07-24. Current layout:

| Set | File | Prompts | Run result |
|---|---|---|---|
| Dipstick | `scripts/prompts/00_dipstick.txt` | 6 | Depth-ordered triage |
| Supplier | `scripts/prompts/01_supplier.txt` | 40 | Mostly clean |
| Purchase Order | `scripts/prompts/02_purchase_order.txt` | 9 | Clean |
| Accounts Receivable | `scripts/prompts/03_ar.txt` | 16 | 6 wrong or suspicious |
| Columns | `scripts/prompts/04_columns.txt` | 8 | Feature broken; set documents it |
| Refusals | `scripts/prompts/05_refusals.txt` | 9 | Clean |
| Slow | `scripts/prompts/06_slow.txt` | 15 | Aggregations, minutes each |
| Parser stress | `scripts/prompts/scorer/parser_stress.txt` | 60 | Scorer format, not in this run |
| **Total run** | | **103** | |

AR is tracked as a numbered 1–18 series. **17 built, 1 unbuilt**
(prompt 16, DSO / cash-collection trends — design pending).

---

## 7. This run — outcome

**103 prompts, 7 sets, live pod.**

| | Count | Share |
|---|---|---|
| Completed without error | 100 | 97% |
| Errored | 3 | 3% |

The three errors share **one** root cause: address expansion overrunning
the synthesizer token cap.

### Quality behind the tally

| Score | Count | Meaning |
|---|---|---|
| Pass | ~70 | Answer matches the data |
| Wrong or unverifiable | ~30 | Ran cleanly, answer not supported |
| Error | 3 | MAX_TOKENS |

**The tally counts errors, not correctness.** Roughly thirty prompts
returned confident, well-formed prose that the data does not support.

### Layer health

| Layer | State | Evidence |
|---|---|---|
| Parse | Healthy | Intents correct across all sets |
| Plan | Healthy | Multi-hop traversals land correctly |
| Execute | Healthy | Filters resolve, joins hold |
| Synthesize | **Defective** | Source of nearly all wrong answers |
| Display | Weak | Projection hides rows the narration cites |

Retrieval is sound. All nine fixes from the previous session held; no
regressions. The defects are concentrated in the last stage.

---

## 8. Open issues

### Failure patterns — thirty wrong answers, six causes

| # | Pattern | Prompts | Root cause |
|---|---|---|---|
| 1 | Narration cites fields not in output | ~12 | Model sees full rows, display shows a subset |
| 2 | Page size stated as total | ~8 | Truncation metadata not threaded to narration |
| 3 | Arithmetic over undisplayed rows | ~4 | Model computes instead of copying tool output |
| 4 | Parsed intent ignored downstream | ~4 | `count_only`, `open_only`, `fields` never applied |
| 5 | Address expansion overrun | 3 | Nested addresses exceed token cap |
| 6 | Generalisation from visible rows | ~3 | True of 25 shown, asserted of the set |

**Sharpest example.** Two AR prompts over the same 25 rows reported two
different amount ranges — 211.09–75313.86 and 7039.39–216378.00. At least
one was invented.

### Designed features, parsed but inert

| Feature | Parsed | Applied | Evidence |
|---|---|---|---|
| `count_only` | Yes | No | Fetches 25 rows anyway |
| `open_only` | Yes | No | Same 25 rows as unfiltered prompt |
| `fields` | Yes | No | One-field and two-field output byte-identical |

### Structural / carried forward

| Issue | Detail |
|---|---|
| **Credit-memo total** | Sums 25 of an unknown total, mixes USD and CAD, and includes a positive 10,000.00 row inside a credit-memo set |
| **List vs total conflation** | "List recent credit memos" and "What is the total value of credit memos?" returned byte-identical prose |
| **Row-count ceiling on nested child arrays** | 25 wide rows → synthesizer returns an EMPTY array with a short summary. 10 works. Currently handled by capping limits at 10 |
| **Metadata block is hardcoded** | `_build_synthesis_prompt` special-cases `account_receipt_applications`; does not generalise |
| **`pytest` has not been run** | `execute_plan`'s signature changed from 2 return values to 3. **Highest-risk unknown.** |

### Receipt-method stability — downgraded

Previously suspected unstable: two consecutive runs gave 215.7M and
250.6M on the same 1,386 rows.

**This run matched the first exactly** — 1,386 receipts, 215,721,775.28,
Lockbox 993, Check 393. Two of three runs now agree.

The divergence is real but intermittent, not systematic. **Do not treat
the pagination hypothesis as confirmed.**

### Still never observed working

`Show lag between creation and last update for receipts of X` — refuses
as out-of-scope. The KG has a `lag_query` filter and a
`get_receipts_with_lag` tool is registered. Either the filter is not
reaching the parser menu or the tool is not wired.

---

## 9. Column selection — status: STILL NOT WORKING

Design intent: a user names the columns they want and the output honours
them. Eight prompts in `04_columns.txt`; the defect is unchanged from the
previous session.

| Prompt | Result |
|---|---|
| "Show only supplier name and status for active suppliers" | **Ignored** — 6 columns returned |
| "Just the names of active suppliers" | **Ignored** — 6 columns returned |
| "Supplier number and country for active suppliers" | **MAX_TOKENS**, `out=7985` |
| "Supplier name, number, status and country for active suppliers" | **MAX_TOKENS**, `out=7985` |

**Two distinct defects.**

**9a. `fields` is parsed but never applied.** The parser extracts the
field list into the Intent correctly. Nothing downstream uses it.
`_project_outputs(outputs, fields)` exists in `graph/pipeline.py`, but
`run_plan.py` calls `execute_plan` and `synthesize_response` directly and
never invokes it. Evidence: asking for ONE field and asking for TWO
produced **byte-identical output**.

**9b. Requesting `country` triggers an over-fetch that overruns the
synthesizer.** Both failing prompts name `country`. Per the KG,
`Supplier`/`country` is `client_side` with the note "Country lives on the
addresses child; over-fetch." Requesting country as a FIELD triggers the
same address expansion used for country FILTERING.

**Same root cause as `Suppliers with their addresses`** — one defect
accounts for all three of the run's errors.

**Assessment:** 9a is a missing wire-up — likely small. 9b is a real
design question: field requests and filter mechanisms are being conflated.

---

## 10. What to do next, in order

**Prerequisites — before any code:**

1. **Run `python -m pytest -q`.** Still not run. The executor signature
   change is unvalidated. Everything else is built on this.
2. **Bump the two KG tripwires** to 10 and 25 in both `print_kg.py` and
   `tests/test_kg_metadata.py`.
3. **Curl `/standardReceipts` with `orderBy`** before touching pagination.

**Fixes, by yield:**

| # | Fix | Kills patterns | Effort |
|---|---|---|---|
| 4 | Narrate only from displayed projection | 1, 3, 6 | Medium |
| 5 | Thread truncation metadata into every narration | 2 | Small |
| 6 | Wire `_project_outputs` into `run_plan.py` (9a) | 4 | Small |
| 7 | Apply `count_only` in the planner | 4 | Small |
| 8 | Apply `open_only` to the transaction filter | 4 | Small |
| 9 | Cap or flatten address expansion (9b) | 5 | Medium |
| 10 | Route credit-memo total to an aggregate tool | 3 | Medium |

Fix 4 is the highest yield: one change, three patterns, roughly nineteen
prompts. Fix 9 is the only one that clears the three hard errors.

Then: **build AR prompt 16** (DSO / cash-collection), the last unbuilt
item in the AR series.

---

## 11. Method note

**The summary line is not a verdict.** "100/103 ran cleanly" was true of a
run in which roughly thirty answers were wrong. Every defect recorded here
was invisible at the summary level and required reading the answers.

Two lessons this run reinforced:

- **A diagnosis from a previous session is a claim, not a fact.** The
  receipt-method instability was carried forward as established and did
  not reproduce. Re-observe before acting.
- **Compute in the tool, not the prompt.** Every numeric defect still open
  is one where the model was asked to do arithmetic. Where the tool
  computed and the synthesizer copied, the answer was right.

---

## 12. Codebase size

**By area**

| Area | Lines | Share |
|---|---|---|
| `src/spire` | ~12,900 | 52% |
| `tests` | 8,371 | 34% |
| `scripts` | 2,764 | 11% |
| Other Python | 612 | 3% |
| **Total** | **24,837** | |

**Source modules**

| Module | Lines |
|---|---|
| `mcp_server` (incl. 26 tool files, 4,421) | 5,619 |
| `synthesizer` | 2,382 |
| `planner` | 1,669 |
| `nl_parser` | 1,606 |
| `executor` | 686 |
| `agent` | 295 |
| `kg` | 262 |
| `graph` | 214 |
| `oracle` | 94 |
| `fusion` | 61 |

**Observation.** The synthesizer is the second-largest source module and
the origin of nearly every wrong answer in this run. The executor, planner
and parser — 3,961 lines combined — produced no observed defects.

Tests are 8,371 lines against roughly 12,900 of source. A healthy ratio on
paper, but the suite has not run since the executor signature changed, so
the figure is currently unverified.
