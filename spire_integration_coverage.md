# Spire — Integration Coverage

## 1. Endpoints by module

Spire integrates **7 Oracle Fusion REST endpoints (4 base + 3 child)**
across **3 module areas**, exposed via 10 MCP tools.

| Module | Endpoint | Type |
|---|---|---|
| Procurement | `/suppliers` | base |
| Procurement | `/suppliers/{id}/child/addresses` | child |
| Procurement | `/suppliers/{id}/child/sites` | child |
| Procurement | `/suppliers/{id}/child/businessClassifications` | child |
| Procurement | `/purchaseOrders` | base |
| Payables | `/invoices` | base |
| HCM Workforce | `/publicWorkers` | base |

## 2. Query coverage

The parser maps free-form English onto supported filters, so phrasing is
flexible. Representative prompts, one per capability:

- List active suppliers
- List inactive suppliers
- US suppliers
- Suppliers in the UK
- Suppliers named Lee
- Prospective suppliers
- Suppliers created between Jan and Mar 2025
- Suppliers with a site in the France business unit
- Woman owned suppliers
- Suppliers that are small business
- Suppliers with open purchase orders
- Suppliers with invoices over 10000
- How many suppliers do we have
- Top 10 suppliers by spend in 2022
- Invoices for supplier 1252
- Invoices for Lee Supplies in 2023
- Addresses for supplier 1252
- Suppliers with their addresses

## 3. Output columns — review requested

Each query returns a curated default column set, and Spire can also return
**specific columns on request** (e.g. "show only supplier name and status",
"invoice number and amount for supplier 1252").

The gaps raised in the first review have been addressed in the KG
framework. **Request:** please re-run the prompts in
`spire_v1.2_review_prompts.txt` against Spire V1.2 and share review
comments — including, for each prompt, which columns you expect in the
output. That will let us align the default and requested column sets to
what reviewers actually need.