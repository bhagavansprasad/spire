# SQL Overlay Completeness (SOC)

**Status:** Planned
**Owner:** (assign)
**Related:** `docs/design/SQL_OVERLAY_POC.md` (the POC this completes), `docs/feature_roadmap.md` (feature index)

---

## 1. The Invariant

> **Every prompt Spire accepts and executes against Fusion produces equivalent
> executable SQL in the same response. Every prompt Spire refuses produces no
> SQL. There is no third state.**

Today the SQL Overlay covers 9 of the ~22 MCP tools that can appear in a Plan.
That is a 40% coverage. The remaining 13 are the target of this feature.

### What "equivalent SQL" means

The SQL emitted in `metadata.sql` must return **the same rows the REST tools
return for the same prompt**, up to:

- Column ordering within `SELECT` (must be documented per entity, not required
  to match the REST projection exactly, but must contain the same columns).
- `WHERE` clause structure (`IN (SELECT ...)` vs `JOIN` vs `EXISTS` — any is
  acceptable if the result is identical).
- Sort order when the REST API does not guarantee one (document per tool if
  SQL imposes an order the REST path does not).

What must NOT differ: the set of rows. A prompt that returns 25 suppliers via
REST must return 25 suppliers via the emitted SQL, not 24, not 26.

### Two testable sub-invariants

1. **Coverage:** `set(OVERLAY.tool_to_entity) ⊇ set(MCP tool names)`. A unit
   test enforces this; it fails loudly the moment a new tool is added without
   an overlay entry.
2. **Execution parity:** a prompt-set smoke test compares row counts between
   the REST execution and the emitted SQL execution (against the same pod).

---

## 2. What Is Currently Mapped

As of the start of this feature (Phase 0), `sql_overlay.py` covers:

| Module | Tools | Status |
|---|---|---|
| Supplier | `search_suppliers`, `search_suppliers_by_site_bu`, `search_suppliers_by_classification` | ✅ Mapped |
| Address | `search_addresses` | ✅ Mapped |
| Contact | `get_supplier_contacts` | ✅ Mapped |
| Procurement (header) | `search_purchase_orders`, `get_purchase_order_by_id` | ✅ Mapped |
| Payables | `search_invoices` | ✅ Mapped |
| Receivables (header) | `get_receivables_invoice_by_id` | ✅ Mapped |

Nine tools. The overlay produces real, executable `SELECT` statements against
`POZ_SUPPLIERS`, `HZ_PARTIES`, `HZ_LOCATIONS`, `HZ_PARTY_SITES`,
`POZ_SUPPLIER_CONTACTS`, `PO_HEADERS_ALL`, `PER_ALL_PEOPLE_F`,
`AP_INVOICES_ALL`, `RA_CUSTOMER_TRX_ALL`, `HZ_CUST_ACCOUNTS`.

---

## 3. What Is Not Mapped (the Feature Scope)

The remainder of the MCP surface, grouped by phase. Each phase is independently
deliverable and testable.

### Phase 1 — Child fetchers
Easy wins: each takes one parent id, filters one child table on it.

- `get_purchase_order_lines(po_header_id)` → `PO_LINES_ALL`
- `get_purchase_order_schedules(po_header_id)` → `PO_LINE_LOCATIONS_ALL`
- `get_purchase_order_distributions(po_header_id, po_line_id, line_location_id)` → `PO_DISTRIBUTIONS_ALL`
- `get_receivables_invoice_lines(customer_transaction_id)` → `RA_CUSTOMER_TRX_LINES_ALL`

**Covers prompts like:** "Show PO 2144 and its lines", "Get invoice 1002 and its lines".

### Phase 2 — Supplier children, AR grandchildren
Extends Phase 1's pattern to deeper paths.

- `get_receivables_invoice_tax_lines(customer_transaction_id, line_id)` → tax-line table (curl confirmation needed)
- `get_receivables_invoice_transaction_dff(customer_transaction_id)` → `RA_CUSTOMER_TRX_ALL` DFF columns

**Covers prompts like:** "Show tax lines for AR invoice 1002", "Get the DFF for invoice 1002".

### Phase 3 — Customer-account paths
The hardest multi-table group: two-step traversal.

- `get_customer_account_by_name(customer_name)` → `HZ_CUST_ACCOUNTS JOIN HZ_PARTIES`
- `get_customer_transactions(account_id)` → `AR_PAYMENT_SCHEDULES_ALL`
- `get_account_credit_memos(account_id)` → `AR_CASH_RECEIPTS_ALL` (credit memos subset)
- `get_account_receipts(account_id)` → `AR_CASH_RECEIPTS_ALL`
- `get_account_receipt_applications(account_id)` → `AR_RECEIVABLE_APPLICATIONS_ALL`

**Covers prompts like:** "Show AR invoices for customer ABC Corporation Americas", "Receipts for account 26360".

### Phase 4 — Aggregations and comparisons
Requires new emitter structure (`AggregationSpec`) — not a simple `SELECT`.

- `aggregate_invoices_by_supplier` — top N suppliers by spend
- `aggregate_purchase_orders_by_status` — PO status breakdown
- `compare_orders_to_invoices` — ordered vs invoiced per PO
- `aggregate_standard_receipts_by_method` — receipt method distribution
- `rank_customer_accounts_by_exposure` — top N accounts by open receivables

**Covers prompts like:** "Top 5 suppliers by spend", "POs by status", "Exposure ranking".

---

## 4. The Guardrail Test

`tests/test_sql_overlay_coverage.py` asserts:

```python
from spire.mcp_server.tools import ALL_TOOL_NAMES  # or equivalent
from spire.kg.sql_overlay import OVERLAY

def test_every_tool_has_an_overlay():
    missing = set(ALL_TOOL_NAMES) - set(OVERLAY.tool_to_entity)
    assert not missing, f"Tools without overlay: {sorted(missing)}"
```

The test **fails today**, listing the tools in Phases 1-4. That is the point:
the failure list is the backlog. Each phase closes a chunk of that list, and
the test turns green when all phases land. Adding a new tool without an overlay
fails the test — which is the invariant.

---

## 5. Phase Delivery Contract

For each phase, the work is:

1. Confirm the physical table + joins (via the endpoint reference doc plus curl
   against the live pod, when the reference is incomplete).
2. Add `EntitySpec`, `FilterSpec`, join, and assumptions to `sql_overlay.py`.
3. Add the tool name to `OVERLAY.tool_to_entity`.
4. Run a representative prompt from the phase; capture the emitted SQL.
5. Spot-execute the emitted SQL against the pod (via SQL Developer, or via a
   `sqlplus` one-liner) and compare row counts to the REST result.
6. Update this document's status for the phase to **Landed**.

A phase is not "Landed" until step 5 confirms row parity for at least one
prompt in that phase.

---

## 6. Assumption Discipline

Every `ASSUMPTION` in `_ASSUMPTIONS` must state:

- What the mapping assumes.
- What would falsify it (a specific prompt + the observed incorrect result).
- How to correct it if falsified.

Example, from Phase 0:
> `supplier_number_not_vendor_id` — The `search_purchase_orders` tool takes a
> supplier reference that may be a SupplierNumber (all-digit string) OR a
> SupplierId (numeric). The filter assumes SupplierNumber and joins through
> `POZ_SUPPLIERS.SEGMENT1`. If executed against a pod where the plan passes
> an internal `VENDOR_ID`, this filter returns 0 rows; the fix is to compare
> against `P.VENDOR_ID` directly.

Assumptions are not scaffolding to be removed later — they are the honest
record of every place the overlay makes a guess. A future maintainer reading
the overlay should be able to know exactly which parts are proven and which
are inferred.

---

## 7. Out of Scope

- **Performance.** The emitted SQL is not optimized — it joins tables that
  the REST API joins implicitly. Query tuning is a separate concern.
- **BIP/OTBI.** Complex multi-table queries that Spire routes to `compare_*`
  tools may need `AggregationSpec` (Phase 4). Anything beyond that stays
  out of this feature.
- **Writes.** Every mapped tool is a read-only fetcher. No `INSERT` /
  `UPDATE` / `DELETE` will ever be emitted.
- **Cross-pod portability.** The overlay is calibrated against the specific
  Fusion pod's physical schema. A different pod with schema drift requires
  re-confirmation, but the overlay structure survives.

---

## 8. Timeline

Not scheduled — this is a phase-driven feature, not a time-driven one. Each
phase is picked up when it is next in the FIX_PLAN queue or when a prompt-set
sweep exposes a specific coverage gap.

Phases are expected to run roughly in order (1 → 2 → 3 → 4), but Phase 3 and
Phase 4 are independent of each other and can swap if a prompt set demands it.
