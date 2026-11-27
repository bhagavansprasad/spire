# SME prompt sheet — 4 modules, fill values verified on the pod (2026-11-21)

**Purpose.** The 40 prompts from Module A are only meaningful tests if the
placeholder values point at records that actually have children. A PO with
no lines returns `[]` from Fusion, which is indistinguishable from SPIRE
being broken. Every value below was pulled from the pod with `runsql.sh`
and its child counts verified — the query and its output file are named
beside each group.

**Companion doc:** `docs/plan/DEMO_SME_2026-11-20.md` (the 6 prompts
already demoed). This sheet supersedes its prompt list for breadth; the
"do NOT demo" list there still applies.

**Authoritative copy:** the runnable set and its expectations now live in
`prompts/sme_module_a/` (`sme_module_a_litmus.txt` +
`sme_module_a_expected.md`). This file is the session record; if they
disagree, `prompts/sme_module_a/` wins.

**Evidence:** `t_f078_verify.csv`, `t_f078_verify2.csv`, `t_f078_q1..q13`
(`.sql` + `.csv`), `t_f078_cols*.csv`, `t_f078_kg.txt`.

**Status legend**

| Mark | Meaning |
|---|---|
| ✅ | SPIRE has the tool + filter; expect a correct answer |
| ⚠️ | Tool exists but a filter/field is missing; answer may be wrong or need the value phrased differently |
| ❌ | No entity/tool exists; SPIRE cannot answer regardless of fill value |

---

## 0. The values, in one table

| Value | Use for | Verified content |
|---|---|---|
| PO **`55040`** | PO details, lines, schedules, distributions | 52 lines, 52 schedules, 52 distributions (CLOSED) |
| PO **`55250`** | Pending approval | PENDING APPROVAL, 52 lines |
| PO **`UK555867`** | Overdue/pending shipments | OPEN, 52 overdue schedules, 52 qty outstanding |
| Buyer **`Eleanor White`** | POs by buyer | **3,773 POs** |
| Buyer **`Calvin Roth`** | POs by buyer (alt) | **2,601 POs** (5,202 name-rows; see caveat §5) |
| Supplier **`Dell Inc.`** | POs for supplier | 32 sites |
| AP invoice **`ERS-53004-755598`** | Invoice details + lines | 184 lines, 138,864.62, Staffing Services |
| AP invoice **`ERS-52987-751583`** | Invoice details (alt) | 184 lines, 296,073.77, JGA |
| AR invoice **`61765`** / id `300000248096352` | AR details + lines | already demoed 2026-11-20 |
| AR invoice **`112390`** | AR details + lines (rich) | 240 lines, 180 tax lines, Sykes Gym |
| Customer **`ABC Application Software`** | Receipts | account `26360`, 2,329 receipts (all orgs) |
| Receipt **`Brad-234`** | Applications | 579 applications |
| Receipt **`2001`** | Partially applied | 100,000 amount, 10,000 unapplied |
| Receipt **`558877`** | Partially applied (alt) | 50,000 / 25,500 unapplied |
| Credit memo **`29822`** | CM details | 24 lines, Bradshaw Hotels |
| Credit memo **`1457709_CM1`** | CM details (alt) | 20 lines, Motique Gym |
| Supplier **`1262`** / id `300000047507499` | Supplier master, all children | 22 sites, 45 contacts, 3 classifications |
| Supplier **`1252`** | Supplier master (alt) | 35 sites, 34 contacts, 4 classifications |
| Classification **`SMALL_BUSINESS`** | Suppliers by classification | 13 suppliers |
| Classification **`HUB_ZONE`** | Suppliers by classification (alt) | 18 suppliers |

Nothing in this table is guessed. Section 0's source is
`t_f078_verify.csv` (exit 0) and `t_f078_q13.csv` (exit 0).

---

## 1. Procurement — Purchase Orders

| # | Prompt (with verified fill) | Status | Note |
|---|---|---|---|
| 1 | Show me all purchase orders created in the last 30 days. Include PO number, supplier name, buyer, creation date, total amount, and status. | ✅ | 171 POs in window. Total amount is derived (`UNIT_PRICE × QUANTITY` + tax) — this is the F-060/63 engine on every row. |
| 2 | Get the complete details of purchase order **55040**, including supplier, business unit, buyer, currency, total amount, and approval status. | ⚠️ | Tool takes `POHeaderId`, not the number → use `Get PO by id 67`. Approval status is `DOCUMENT_STATUS`; `AUTHORIZATION_STATUS` **does not exist** (F-064, re-confirmed: ORA-00904). |
| 3 | Show all lines for purchase order **55040**. Include item description, quantity, unit price, UOM, and line amount. | ✅ | 52 lines. Line amount is derived. |
| 4 | Show the shipment schedules for purchase order **55040**. Include shipment number, ordered quantity, received quantity, promised date, and shipment status. | ✅ | 52 schedules. |
| 5 | Show the distribution details for purchase order **55040**. Include distribution number, charge account, quantity, amount, and deliver-to location. | ✅ | 52 distributions — the deepest chain (PO → line → schedule → distribution). |
| 6 | Find all purchase orders for supplier **Dell Inc.** Show PO number, order date, total amount, and status. | ✅ | Filter is `supplier`; Dell has 32 sites. |
| 7 | Show all purchase orders assigned to buyer **Eleanor White**. Include PO number, supplier, amount, and approval status. | ❌ | No `buyer` filter on `search_purchase_orders`. 3,773 POs exist for her; SPIRE cannot filter to them. |
| 8 | Find purchase orders that are pending approval. Show PO number, supplier, buyer, amount, and submission date. | ✅ | Use `55250`, or the status filter. 64 PENDING APPROVAL on the pod. |
| 9 | Show purchase orders with pending or overdue shipments. Include PO number, supplier, shipment number, promised delivery date, and outstanding quantity. | ❌ | No schedule-level "overdue" predicate; `search_purchase_orders` cannot reach `PROMISED_DATE`. `UK555867` has 52 such schedules. |
| 10 | Get the total purchase order amount by supplier for the current month. Display supplier name, number of purchase orders, and total amount. | ⚠️ | No PO-by-supplier aggregate tool (`aggregate_purchase_orders_by_status` exists, not by supplier). |

---

## 2. Payables — Supplier Invoices

| # | Prompt (with verified fill) | Status | Note |
|---|---|---|---|
| 1 | Show all supplier invoices created in the last 30 days. Include invoice number, supplier name, invoice date, amount, and status. | ✅ | 781 invoices in window. |
| 2 | Get the complete details of invoice **ERS-53004-755598**. Include supplier, invoice date, due date, invoice amount, currency, business unit, and payment status. | ⚠️ | 184 lines, 138,864.62, Staffing Services. **`DUE_DATE` does not exist on `AP_INVOICES_ALL`** (ORA-00904) — due date is not answerable. |
| 3 | Show all invoice lines for invoice **ERS-53004-755598**. Include line number, description, quantity, unit price, amount, and line type. | ❌ | No InvoiceLine entity/tool. 184 lines exist; SPIRE has nothing to call. |
| 4 | Find all unpaid invoices for supplier **Staffing Services**. Show invoice number, invoice date, due date, amount, and remaining balance. | ⚠️ | `unpaid` filter exists (`PAYMENT_STATUS_FLAG='N'`, 12,347 rows). See §5 caveat: filter by `INVOICE_AMOUNT > 0` or the top results are all zero-amount. Due date/remaining balance not modelled. |
| 5 | Show all invoices currently on hold. Include invoice number, supplier, invoice amount, hold reason, and hold status. | ❌ | Holds not modelled. |
| 6 | Find all overdue supplier invoices. Show invoice number, supplier, due date, outstanding amount, and number of overdue days. | ⚠️ | `overdue` filter exists; `DUE_DATE` absent, so "overdue days" is unanswerable. |
| 7 | Show the payment details for invoice **ERS-53004-755598**. Include payment number, payment date, payment method, payment amount, and payment status. | ❌ | No Payment entity. |
| 8 | Check whether invoice **ERS-53004-755598** has completed validation and accounting. Show validation status, accounting status, and any errors. | ⚠️ | Validation/accounting status not modelled beyond `PAYMENT_STATUS_FLAG`. |
| 9 | Find duplicate invoices for supplier **Staffing Services**. Compare invoice numbers, invoice dates, and invoice amounts. | ⚠️ | No duplicate tool. Answerable only as "list the supplier's invoices and let the reader compare" — and 184-line invoices make that noisy. |
| 10 | Show the total outstanding invoice amount grouped by supplier for the current month. Include supplier name, invoice count, and outstanding amount. | ✅ | `aggregate_invoices_by_supplier` with `date_from`/`date_to`. |

---

## 3. Receivables — AR Invoices, Customers, Receipts, Credit Memos

| # | Prompt (with verified fill) | Status | Note |
|---|---|---|---|
| 1 | Show all AR invoices created in the last 30 days. Include invoice number, customer name, invoice date, due date, amount, and status. | ❌ | **`ReceivablesInvoice` has only a `by_id` filter.** No date filter, so "last 30 days" is impossible. 107 such invoices exist. |
| 2 | Get the complete details of AR invoice **112390**. Include customer, transaction date, transaction type, currency, total amount, and outstanding balance. | ✅ | 240 lines, 180 tax lines, Sykes Gym. Balance is the F-067 derived projection. |
| 3 | Show all customers with active customer accounts. Include customer name, account number, account status, and customer type. | ✅ | `search_customer_accounts` (plain list, sample-and-disclose). |
| 4 | Get the complete details of customer account **26360**. Include account name, account number, account status, customer sites, and account profile. | ⚠️ | Resolves by name; account 26360 = ABC Application Software, 1 site. Site list and profile not projected. |
| 5 | Show all receipts received from customer **ABC Application Software**. Include receipt number, receipt date, receipt amount, receipt method, and status. | ✅ | 2,329 receipts (all orgs). `customer_name` filter resolves to account 26360. F-076 caveat: REST shows the session BU only. |
| 6 | Get the application details of receipt **Brad-234**. Show the invoices against which the receipt was applied, applied amount, and unapplied amount. | ✅ | 579 applications. Unapplied comes from the PMT schedule (F-075), **not** `AMOUNT − SUM(applied)`. |
| 7 | Find all unapplied and partially applied receipts. Include receipt number, customer, receipt amount, applied amount, and unapplied balance. | ✅ | Use `2001` (100,000 / 10,000) or `558877` (50,000 / 25,500). Must filter on the derived PMT remainder — filtering on the applications sum returns only NSF/REV rows with `applied = 0`. |
| 8 | Show all credit memos created for customer **Bradshaw Hotels**. Include credit memo number, transaction date, amount, reason, and status. | ✅ | `29822` belongs to Bradshaw Hotels. `list_receivables_credit_memos` is a top-level list; account-scoped via `get_account_credit_memos`. |
| 9 | Get the complete details of credit memo **29822**. Include customer, original invoice reference, credit amount, reason, and accounting status. | ⚠️ | 24 lines exist. "Original invoice reference" and "reason" are not modelled. |
| 10 | Find overdue AR invoices for customer **ABC Corporation Americas**. Include invoice number, due date, original amount, outstanding balance, and overdue days. | ❌ | No `overdue` filter on `ReceivablesInvoice` (only AP has one). |

---

## 4. Supplier — Master Data

| # | Prompt (with verified fill) | Status | Note |
|---|---|---|---|
| 1 | Search for suppliers matching **Dell**. Show supplier name, supplier number, supplier type, business relationship, and status. | ✅ | `name_fragment` filter. |
| 2 | Get the complete details of supplier **1262**. Include supplier name, supplier number, tax registration details, supplier type, and status. | ⚠️ | No by-number filter (only `name_fragment`); SPIRE has `SupplierId`. Tax registration partly modelled. |
| 3 | Show all active supplier sites for supplier **1262**. Include site name, procurement business unit, address, and site status. | ✅ | 22 sites. |
| 4 | Show all inactive supplier sites for supplier **1262**. Include site name, business unit, and inactive date if available. | ⚠️ | Same fetch; inactive filtering is client-side at best. |
| 5 | Get the contact details of supplier **1262**. Include contact name, email address, phone number, and contact status. | ✅ | 45 contacts via `get_supplier_contacts`. |
| 6 | Show all addresses associated with supplier **1262**. Include address name, address lines, city, state, country, and postal code. | ✅ | `search_addresses` with `supplier` filter. |
| 7 | Find suppliers based on supplier classification **SMALL_BUSINESS**. Include supplier name, supplier number, classification, and status. | ✅ | 13 suppliers. `has_classification` edge filter. 11 lookup codes exist. |
| 8 | Show the procurement and payment-related site assignments for supplier **1262**. Include site name, procurement business unit, payment method, and payment terms where available. | ⚠️ | `has_site_in_bu` exists; payment method/terms may not be projected. |
| 9 | Find suppliers with inactive or expired supplier records. Include supplier number, supplier name, status, and inactive date. | ⚠️ | 8 suppliers have `END_DATE_ACTIVE <= SYSDATE`. **`INACTIVE_FLAG` does not exist** (ORA-00904) — the carrier is `END_DATE_ACTIVE`. |
| 10 | Compare the supplier details for **1262** and show all associated sites, contacts, addresses, and classifications. | ✅ | The best single traversal test: 22 sites / 45 contacts / 22 addresses / 3 classifications off one parent — four different KG edges. |

---

## 5. Caveats found while verifying — read before presenting

1. **Buyer counts double when joined naively.** `PER_PERSON_NAMES_F` holds
   **2 rows** per `PERSON_ID` (effective dating), so joining it to
   `PO_HEADERS_ALL` returns 7,546 for a buyer with **3,773** POs
   (`t_f078_verify2.csv`). Any "POs by buyer" number must be counted before
   the name join, or de-duplicated. Also present: one `PERSON_ID` can carry
   two different display names (`Camille Procurement` /
   `Camille Fredricks`).
2. **Supplier contacts do not join by `VENDOR_ID`.** `POZ_SUPPLIER_CONTACTS`
   has no `VENDOR_ID`; the path is contact → `PARTY_SITE_ID` →
   `POZ_SUPPLIER_SITES_ALL_M.PARTY_SITE_ID`. The obvious join returns **0
   contacts for every supplier**.
3. **"Partially applied" ≠ `AMOUNT > SUM(applications)`.** Ordering by the
   applications sum returns only NSF/REV receipts with `applied = 0`. The
   carrier is the PMT schedule `AMOUNT_DUE_REMAINING <> 0` (the F-075
   lesson).
4. **Unpaid AP invoices default to zero amount.** The highest-line-count
   unpaid invoices are all `INVOICE_AMOUNT = 0` with 184 lines. Filter
   `INVOICE_AMOUNT > 0`.
5. **Three columns named in the prompts do not exist on the pod.**
   `PO_HEADERS_ALL.AUTHORIZATION_STATUS` (use `DOCUMENT_STATUS`; F-064),
   `AP_INVOICES_ALL.DUE_DATE`, `POZ_SUPPLIERS.INACTIVE_FLAG` (use
   `END_DATE_ACTIVE`). Each was confirmed by ORA-00904, not by assumption.
6. **F-076 touches every count.** All row counts here are pod-wide, across
   business units; REST returns the session BU only. Do not call a SPIRE
   count "wrong" against these numbers without the BU decision resolved.

---

## 6. The short list — 8 prompts that would prove SPIRE works

Chosen because each fails a "call one endpoint and echo it" implementation.

| # | Prompt | Why this one |
|---|---|---|
| 1 | POs last 30 days **with total amount** (171 in window) | Derived totals on every row, not a stored column. |
| 2 | Distributions for PO **55040** | 4-level chain; a wrong join returns plausible numbers. |
| 3 | Receipt applications for **Brad-234** (579 apps) | Unapplied must come from the schedule, not the obvious subtraction. |
| 4 | Partially applied receipts — **2001** | Filter on a *derived* value no endpoint offers. |
| 5 | Supplier **1262** across sites, contacts, addresses, classifications | Pure graph traversal, four edges, no single endpoint. |
| 6 | POs pending approval (**55250**) | Vocabulary mapping: "Pending Approval" → `DOCUMENT_STATUS`. |
| 7 | Credit memos for **Bradshaw Hotels** | Account-scoped traversal + derived amounts. |
| 8 | Total outstanding invoice by supplier this month | Aggregation with an authoritative total (REST `count` is per-page). |
