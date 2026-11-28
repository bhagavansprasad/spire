# Supplier (shared master data)

**Family:** Financials (filing) · **Routable module id:** `supplier` ·
**Prompts:** Module A 31–40 · **Evidence:** run02 (2026-11-28)

Supplier is shared master data: procurement, payables and receivables all read
it. It is filed under `financials/` because that is where its prompts and its
owning family sit — filing is not a statement about who may query it.

Partial support already exists and is measurable: 4 of the 10 prompts answer,
and **6 of the 6 refusals have a single root cause**.

## Sub-modules

| Sub | Scope | Prompts | State | Note |
|---|---|---|---:|---|
| SUP.1 | Supplier header — name search, status, business relationship, country, creation window | 31, 37, 39 | `verified` | 3 prompts answer; p39 drifted 7 → 2 by pod data, not code |
| SUP.2 | Addresses (`Address`, child `expand=addresses`) | 36 | `verified` | 22 rows; address is the only place `Country` lives |
| SUP.3 | Lookup by supplier **number** | 32, 33, 34, 35, 38, 40 | `discovered` | SP-001 — one missing parameter blocks 6 prompts |
| SUP.4 | Sites (`Site`, `/suppliers/{id}/child/sites`) | 33, 34, 38 | `discovered` | blocked by SUP.3; `ProcurementBU` filters server-side, `Status` does not |
| SUP.5 | Classifications (`Classification`) | 37, 40 | `verified` | classification filters server-side; `Status` cannot be AND-combined with it |
| SUP.6 | Contacts (`Contact`) | 35, 40 | `discovered` | include-only child; the body carries no parent `SupplierId`, the URL path is the join |

## Measured state (run02)

| # | Prompt | Observed | Verdict |
|---:|---|---|---|
| 31 | Suppliers matching Dell | `OK` 1 | pass |
| 32 | Details of supplier 1262 | `REFUSED` | SP-001 gap |
| 33 | Active sites for 1262 | `REFUSED` | SP-001 gap |
| 34 | Inactive sites for 1262 | `REFUSED` | SP-001 gap |
| 35 | Contacts of supplier 1262 | `REFUSED` | SP-001 gap |
| 36 | Addresses for 1262 | `OK` 22 | pass (F-078) |
| 37 | Suppliers by classification SMALL_BUSINESS | `OK` 26 | pass |
| 38 | Site assignments for 1262 | `REFUSED` | SP-001 gap |
| 39 | Inactive or expired suppliers | `OK` 2 | pass — was 7 in run01, pod data drift |
| 40 | Compare 1262 with associated records | `REFUSED` | SP-001 gap |

## The one defect worth naming

**SP-001 — no `supplier_number` parameter.** `search_suppliers` takes
`supplier_name_contains`, `status`, `business_relationship`, `country`,
`created_from`, `created_to` — and no number. The capability exists on the pod
(`?q=SupplierNumber='1262'` returns 1 row; `POZ_SUPPLIERS.SEGMENT1` holds it),
so **this is a defect, not a boundary**: an SME-answerable question is refused.

It is missing at four layers, so all four must change together: tool argument,
`kg_entity_filter` row, parser teaching block, and the SQL overlay spec that
`validate_sql_coverage.py` enforces.

Effort S–M, unblocks 6 prompts — the best ratio on the open queue. It is
*not* in the AP branch; it is supplier work.

## MVP boundary (gate 3) — not yet agreed

Nothing here is claimed. Gates 1 (endpoints) and 2 (prompt set) are satisfied;
the boundary needs a decision on whether SUP.3 ships with the header or as its
own increment.

## Decisions

Append-only.

**D-SUP-001 — file supplier under `financials/`, keep the routable id
`supplier`.**
Why: it is used by three modules, but its prompts and owning family are
financial. Renaming the id would break the module CHECK, the router list and
the classifier menu in six places for no gain.
Accepted 2026-11-28.

## Open questions

| # | Question |
|---:|---|
| 1 | Does SP-001 ship as its own small branch before any boundary work, as SP-005 does for payables? |
| 2 | Is `Supplier.Status` filterable server-side at all, or is client-side the permanent shape? The KG notes say it cannot be AND-combined with another clause. |
| 3 | p39's 7 → 2 drift: which register records pod-data changes that are not defects? |
