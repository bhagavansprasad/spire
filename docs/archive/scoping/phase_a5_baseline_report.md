# Phase A.5 — Baseline Report

**Track:** A — Direct Tool Orchestration
**Date:** 2026-05-18
**Architecture under test:** LangGraph single-pass agent + Gemini 2.0 Flash + 5 MCP tools over HTTP, no Knowledge Graph, no embeddings
**Tester:** Bhagavan

---

## The reference prompt

```
Show me suppliers in US with no invoices in 6 months but with open
purchase orders, including the buyer assigned to each.
```

Run unchanged across all 5 attempts. No prompt engineering, no retries with corrections, no tool-description tweaks mid-test.

---

## The rubric

Written before any runs. Each row scored ✅ (fully present and correct) / ⚠️ (partially present) / ❌ (absent or wrong).

| # | Behavior | What to look for in the trace |
|---|---|---|
| 1 | Find US suppliers | `search_suppliers_by_country(country="US")` called |
| 2 | Check invoices in last 6 months | `search_invoices(invoice_date_after="2025-11-18")` (or similar) called for each candidate |
| 3 | Filter to "no recent invoices" | Final answer excludes suppliers with invoices in window |
| 4 | Check open POs | `search_purchase_orders(supplier_*=..., status="OPEN")` called for remaining candidates |
| 5 | Filter to "has open PO" | Final answer includes only suppliers with at least one open PO |
| 6 | Look up buyer | `get_buyer(buyer_id=...)` called for matched suppliers' POs |
| 7 | Final answer structure | Coherent supplier → buyer pairing presented to user |

**Not scored:** factual correctness of the final answer (no ground truth available), tool/argument name spelling latitude, wording of the final answer.

---

## Results per run

### Run 1 (trace 2026-05-18T*)

**Final answer:** *(empty — agent printed nothing visible)*

**Trace events:**
```
agent_started
mcp_session_initialized
tools_loaded
graph_built
message
message
[ search_suppliers_by_country(country="US") ]
message
message
agent_finished
```

**Score:** ✅❌❌❌❌❌❌ → **1/7**

**Notes:** Agent called the right first tool, received the US supplier list, then terminated without further iteration. No invoice check, no PO check, no buyer lookup.

---

### Run 2

**Final answer:** *(empty)*

**Trace events:** identical pattern to Run 1.

**Score:** ✅❌❌❌❌❌❌ → **1/7**

---

### Run 3

**Final answer:** *(empty)*

**Trace events:** identical pattern to Run 1.

**Score:** ✅❌❌❌❌❌❌ → **1/7**

---

### Run 4

**Final answer:** *(crash — uncaught exception printed to terminal)*

**Trace events:**
```
agent_started
mcp_session_initialized
tools_loaded
graph_built
... (truncated by crash)
```

**Error:**
```
langchain_core.tools.base.ToolException: 1 validation error for
call[search_purchase_orders]
supplier_number
  Unexpected keyword argument [type=unexpected_keyword_argument,
  input_value='1252', input_type=str]
```

**Score:** ✅⚠️❌❌❌❌❌ → **1/7**

**Notes:** Agent reached the multi-tool composition stage, but called `search_purchase_orders` with parameter `supplier_number='1252'` — a parameter that exists on `search_invoices` but NOT on `search_purchase_orders` (which has `supplier_name`, `supplier_id`, `status`). Pydantic validation raised, the exception propagated through LangGraph, and the agent loop crashed without recovery.

The ⚠️ on row 2 reflects that we can infer (from `supplier_number='1252'`, Lee Supplies' number) that the agent had at least gotten as far as picking a supplier to drill into — implying it was attempting some composition rather than just terminating.

---

### Run 5

**Final answer:** *(crash — same error as Run 4)*

**Trace events:** identical pattern to Run 4.

**Error:** identical to Run 4.

**Score:** ✅⚠️❌❌❌❌❌ → **1/7**

---

## Aggregate

| Step | Best score across 5 runs |
|---|---|
| 1 — Find US suppliers | ✅ (all 5 runs) |
| 2 — Check invoices in last 6 months | ⚠️ (2 runs attempted; never executed cleanly) |
| 3 — Filter to "no recent invoices" | ❌ (never reached) |
| 4 — Check open POs | ❌ (attempted but crashed in 2 runs) |
| 5 — Filter to "has open PO" | ❌ (never reached) |
| 6 — Look up buyer | ❌ (never reached) |
| 7 — Final answer structure | ❌ (no coherent final answer in any run) |

**Aggregate baseline: 1/7** across all 5 runs. The agent reliably finds US suppliers and reliably fails to compose further.

---

## Failure patterns

Three distinct failure modes observed:

### 1. Premature termination (Runs 1, 2, 3)

Agent calls `search_suppliers_by_country` once, receives the result, and stops. The LangGraph loop supports iteration (`tools_condition` routes back to assistant after each tool call), but Gemini's response after seeing the supplier list contained no further tool calls — so the graph terminated. The final assistant message produced no visible content.

This is a planning failure, not an architectural one. The graph would loop if asked to; the LLM didn't ask.

### 2. Parameter confusion across tools (Runs 4, 5)

The agent attempted multi-step composition but called `search_purchase_orders` with the parameter `supplier_number`. That parameter exists on `search_invoices` but not on `search_purchase_orders`. The tool signatures are:

| Tool | Supplier-reference params |
|---|---|
| `search_invoices` | `supplier_number`, `supplier_name` |
| `search_purchase_orders` | `supplier_name`, `supplier_id` |
| `search_suppliers_by_country` | (none — country only) |

The same conceptual entity ("which supplier?") has three different parameter names across three tools. The LLM mixed them up. Tool docstrings explain the difference, but docstrings alone weren't enough to keep the mapping straight under composition pressure.

### 3. No error recovery (Runs 4, 5)

LangGraph's `tools_condition` doesn't have built-in recovery from tool-validation errors. The exception bubbled up through the graph and ended the run. A human seeing the error could trivially correct the parameter name; the agent had no mechanism to do so.

---

## Honest interpretation

This is the expected baseline for Direct Tool Orchestration on a multi-step prompt with no structural guidance. Each individual tool works (proven in A.3 and A.4 smoke tests; 23/23 pytest passing). The failure is **composition**, not execution.

The reference prompt requires:
- 5 distinct entity types (Supplier, Invoice, PurchaseOrder, Buyer, Address)
- Multi-hop traversal (Supplier → Address for country; Supplier → Invoice for date filter; Supplier → PO → Buyer for the final join)
- Negation logic ("no invoices in 6 months")
- Status semantics ("open" POs)

Tool descriptions cannot reliably encode this structure. The LLM is asked to derive the join structure from prose docstrings every time, and on this prompt it didn't.

---

## What Track B is meant to address

Per the master plan, Track B introduces:

- **A Knowledge Graph** in Oracle 26ai SQL Property Graph: entities, typed relationships with join semantics, reusable query patterns ("no Y in N months", "open PO status filter"), and business-term lookups ("US" → 'US').
- **Embedding-based tool retrieval** so only relevant tools enter the LLM's context per prompt (less context bloat, fewer parameter-name confusions across tools).

The hypothesis the POC is testing: with the KG, the LLM no longer needs to derive the supplier → PO → buyer traversal from docstrings. The graph encodes it. The agent's planning surface narrows from "everything is possible" to "here's the traversal pattern the KG suggests."

Whether that hypothesis holds is what Track B's runs against this same prompt will tell us.

---

## Discipline notes

Confirming what was *not* done during this test:

- ❌ Tool descriptions were not edited
- ❌ The prompt was not modified
- ❌ Failed runs were not retried with corrections
- ❌ The system prompt was not edited
- ❌ Parameter naming was not unified (still `supplier_number` vs `supplier_name` vs `supplier_id` across tools)

Fixing the parameter-naming inconsistency is tempting but would be tweaking the system mid-baseline. The honest result includes that the system has this confusion built in.

---

## Phase A.5 exit criteria

| Criterion | Status |
|---|---|
| 5 runs completed and traced | ✅ |
| Each scored against the same rubric | ✅ |
| Honest baseline report written | ✅ (this document) |
| Failure patterns identified | ✅ |

---

## What's next

**Phase A.6** consists of two parts:

1. Add aggregate baseline numbers (above) to the comparison table in `docs/designs/spire_design_alternatives.md`, replacing qualitative ✅/⚠️/❌ symbols with measured data where applicable.
2. Update the working log (`docs/spire_poc_log.md`) with a Phase A.5/A.6 summary entry.

After A.6, **Track A is complete.** Track B (9 phases — KG design, Oracle 26ai setup, KG population, KG query tools, agent integration, embeddings, evaluation) begins.

---

## Trace files

All 5 trace files are preserved in `traces/` directory:
- `traces/2026-05-18T*-*.jsonl` (5 files, one per run)

The trace tails embedded above are extracted from these files. Full traces include LLM message contents (prompt, intermediate reasoning, final answer attempt) at INFO level.
