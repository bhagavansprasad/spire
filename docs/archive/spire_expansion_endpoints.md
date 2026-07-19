# Spire Expansion — Endpoints, Prompts & Outputs

Consolidated reference of Oracle Fusion endpoints across four modules, for
expanding Spire. Each module has its endpoint catalog and its prompts with
returned columns.

- **Type** — Read · Aggregate (computes over data) · Write (POST/PATCH/DELETE) · Action (Oracle /action/).
- **Columns returned** — "— to fill" = output was in a source image not yet captured.
- Base REST path for all: `/fscmRestApi/resources/11.13.18.05/`.

Modules: [1. Accounts Receivable](#1-accounts-receivable-ar) ·
[2. General Ledger](#2-general-ledger-gl) ·
[3. Accounts Payable](#3-accounts-payable-ap) ·
[4. Purchase Orders / Procurement](#4-purchase-orders--procurement-po)

---

# 1. Accounts Receivable (AR)

Source: Oracle Fusion AR MCP execution document (pod esll-dev37). 8 resources, ~36 tools.

## Endpoints

| Resource | Tool | REST endpoint | Purpose |
|---|---|---|---|
| Account Activities | `list_customer_account_activities` | `/receivablesCustomerAccountActivities` | Account headers — balances, open receivables, due |
| › credit memos | `get_account_credit_memos` | `…/{accountId}/child/creditMemos` | Credit memos for one account |
| › standard receipts | `get_account_standard_receipts` | `…/{accountId}/child/standardReceipts` | Cash receipts for one account |
| › receipt applications | `get_account_standard_receipt_applications` | `…/{accountId}/child/standardReceiptApplications` | Applied vs unapplied |
| Credit Memos | `list_credit_memos` | `/receivablesCreditMemos` | Credit memos; supports q filter |
| › credit memo lines | `get_credit_memo_lines` | `/receivablesCreditMemos/{id}/child/receivablesCreditMemoLines` | Lines of one credit memo |
| Invoices | `get_invoice_lines` | `/receivablesInvoices` | AR invoices and billing lines |
| › invoice tax lines | `get_invoice_line_tax_lines` | `/receivablesInvoices/{id}/child/receivablesInvoiceLines/{lineId}/child/taxLines` | Tax per invoice line |
| › invoice DFF | `get_invoice_transaction_dff` | `/receivablesInvoices/{id}/child/invoiceDFF` | Flexfield segments |
| Customers | `receivables_customer` | `/receivablesCustomers` | Customer master |
| Transactions | `receivables_transaction` | `/receivablesTransactions` | AR billing transactions |
| Standard Receipts | `standard_receipt` | `/standardReceipts` | Cash receipts base object |
| › apply / unapply | `apply_receipt_to_invoice` / `unapply_receipt_application` | `/standardReceipts/{id}/child/receivableApplications` | Match cash to invoices |
| Misc Receipts | `misc_receipt` | `/miscReceipts` | Miscellaneous cash receipts |
| Receipt Methods | `receipt_method` | `/receiptMethods` | Receipt method config |

## Prompts

| # | Prompt | Type | Endpoint (tool) | Columns returned |
|---|---|---|---|---|
| 1 | List all open invoices for the customer, top 5 | Read | `list_receivables_invoices` | Invoice #, Customer, Amount, Currency, Due Date, Status |
| 2 | Show invoice lines for invoice 300000248096352 | Read | `get_invoice_lines` | Line, Description, Quantity, Unit Price, Line Amount, Tax Handling |
| 3 | Get tax lines for that invoice line | Read | `get_invoice_line_tax_lines` | (0 tax lines found — none shown) |
| 4 | Fetch DFF values for this invoice | Read | `get_invoice_transaction_dff` | __FLEX_Context (=null here) |
| 5 | List recent credit memos, top 5 | Read | `list_credit_memos` | Memo #, Customer, Amount, Date, Status |
| 6 | Show account activity summary for top accounts | Read | `list_customer_account_activities` | Account, Customer, Open Receivables, Total Due |
| 7 | Get all credit memos for account 300000047368512 | Read | `get_account_credit_memos` | — to fill |
| 8 | Get all standard receipts for this account | Read | `get_account_standard_receipts` | — to fill |
| 9 | Trace receipt applications for this account | Read | `get_account_standard_receipt_applications` | — to fill |
| 10 | Rank the top accounts by outstanding exposure | Read | `list_customer_account_activities` | — to fill |
| 11 | Get the AR invoice with CustomerTransactionId 300000248096352 | Read | `get_invoice` | — to fill |
| 12 | Retrieve invoice details for CustomerTransactionId 300000248096352 | Read | `get_invoice` | — to fill |
| 13 | Get recent standard receipts for Santa Clara site | Read | `get_account_standard_receipts` | — to fill |
| 14 | Show the 5 most recent credit memos and their total value | Read | `list_credit_memos` | — to fill |
| 15 | Find invoices for ABC Corporation Americas | Read | `list_receivables_invoices` | — to fill |
| 16 | Identify cash collection trends, month-over-month, DSO, risks, improvements | Aggregate | `get_account_standard_receipts` | — to fill |
| 17 | Receipt method distribution — % of cash by method (Lockbox/ACH/Wire/Manual) | Aggregate | `get_account_standard_receipts` | — to fill |
| 18 | Lag between CreationDate and LastUpdateDate for each receipt | Aggregate | `get_account_standard_receipts` | — to fill |

---

# 2. General Ledger (GL)

Source: Oracle Fusion GL MCP Functional Capability Document (v1.0). 21 tools (17 read, 4 write).
Note: Oracle exposes no create (POST) on journal resources — journal creation is Import Journals, not REST.

## Endpoints

| Resource | Methods | Purpose |
|---|---|---|
| `journalBatches` | GET / PATCH / DELETE | GL journal batch — read, update, delete drafts, post, reverse |
| `journalBatches/{id}/journalHeaders` | GET | Journals (headers) within a batch |
| `journalBatches/{id}/journalLines` | GET | Debit/credit lines within a journal |
| `ledgersLOV` | GET | Ledgers with currencies and IDs |
| `ledgerBalances` | GET | Account balances by combination/group, period, currency (finder) |
| `accountingPeriodsLOV` | GET | GL calendar periods — name, type, year |
| `accountingPeriodStatusLOV` | GET | Per-ledger period open/close status |
| `journalSourcesLOV` | GET | Valid journal source values |
| `journalCategoriesLOV` | GET | Valid journal category values |
| `chartOfAccountsLOV` | GET | Chart of accounts structures |
| `currenciesLOV` | GET | Enabled currencies and ISO codes |

## Prompts

| # | Prompt | Type | Tool | Oracle API | Columns returned |
|---|---|---|---|---|---|
| 1 | Show all ledgers set up in our instance | Read | `gl_get_ledgers` | `ledgersLOV` | Ledger Name, Currency, Ledger ID |
| 2 | Get details for one ledger | Read | `gl_get_ledger_by_id` | `ledgersLOV/{id}` | Single ledger detail |
| 3 | Balance of account 101-10-1110 for Jun-26 in USD | Read | `gl_get_ledger_balances` | `ledgerBalances` | Account, Period, Currency, Balance amount |
| 4 | List accounting periods | Read | `gl_get_accounting_periods` | `accountingPeriodsLOV` | Period Name, Type, Year |
| 5 | Get one period by name | Read | `gl_get_accounting_period` | `accountingPeriodsLOV` | Single period row |
| 6 | Which periods are open for the US Primary Ledger? | Read | `gl_get_accounting_period_statuses` | `accountingPeriodStatusLOV` | Period Name, Status (Open/Closed) |
| 7 | List journal batches created this period | Read | `gl_get_journal_batches` | `journalBatches` | Batch Name, Status, Source, Period |
| 8 | Get one batch | Read | `gl_get_journal_batch_by_id` | `journalBatches/{id}` | Batch detail |
| 9 | Find all posted journals from the Manual source | Read | `gl_search_journals` | `journalBatches` | Filtered batch list |
| 10 | Show journals inside batch 100045 | Read | `gl_get_journals` | `…/journalHeaders` | Journal Name, Category, Currency |
| 11 | Get one journal | Read | `gl_get_journal_by_id` | `…/journalHeaders/{id}` | Journal header detail |
| 12 | Drill into the lines of that journal | Read | `gl_get_journal_lines` | `…/journalLines` | Account, Debit, Credit, Description |
| 13 | Get one line | Read | `gl_get_journal_line_by_id` | `…/journalLines/{id}` | Single line detail |
| 14 | What journal sources can we use? | Read | `gl_get_journal_sources` | `journalSourcesLOV` | Valid source values |
| 15 | What journal categories can we use? | Read | `gl_get_journal_categories` | `journalCategoriesLOV` | Valid category values |
| 16 | What chart of accounts structures do we have? | Read | `gl_get_chart_of_accounts` | `chartOfAccountsLOV` | COA structures with identifiers |
| 17 | List the currencies enabled | Read | `gl_get_currencies` | `currenciesLOV` | Currency codes & names |
| 18 | Update the completion status of batch 100045 | Write | `gl_update_journal_batch` | `journalBatches/{id}` PATCH | Updated batch confirmation |
| 19 | Delete draft batch 100060 | Write | `gl_delete_journal_batch` | `journalBatches/{id}` DELETE | Deletion confirmation |
| 20 | Post journal batch 100045 | Write | `gl_post_journal` | `journalBatches/{id}` PATCH `{Status:P}` | Posted batch confirmation |
| 21 | Reverse batch 100051 into Jul-26 | Write | `gl_reverse_journal` | `journalBatches/{id}` PATCH `{ReversalFlag:Y, ReversalPeriod}` | Reversal confirmation |

---

# 3. Accounts Payable (AP)

Source: Oracle Fusion AP MCP Functional Capability Document. 75 tools (`ap_<action>_<object>`);
representative subset below. ~18 resources across invoice-to-pay.

## Endpoints

| Resource | Methods | Purpose |
|---|---|---|
| `invoices` | GET POST PATCH DELETE | Full lifecycle of AP invoices |
| `invoiceLines` | GET POST PATCH | Line-level detail within an invoice |
| `invoiceDistributions` | GET POST PATCH | How each line is charged to accounts |
| `invoiceInstallments` | GET PATCH | Payment schedules — due dates, amounts |
| `attachments` (invoice) | GET POST | Supporting files on invoices |
| `appliedPrepayments` / `availablePrepayments` | GET | Prepayments applied / available |
| `invoiceHolds` | GET POST PATCH | Place, review, release holds |
| `suppliers` | GET POST PATCH | Supplier master data |
| `suppliers/…/sites` | GET POST PATCH | Site-level purchasing and pay setup |
| `suppliers/…/addresses` | GET POST PATCH | Address records for a supplier |
| `suppliers/…/contacts` | GET POST PATCH | Contact people for a supplier |
| `payablesPayments` | GET POST PATCH | Create and manage supplier payments |
| `payablesPayments/…/relatedInvoices` | GET POST | Which invoices a payment settles |
| `paymentProcessRequests` | GET POST PATCH | Payment batches (PPR) |
| `expenseReports` | GET POST PATCH | Employee expense reports feeding AP |
| Invoice actions `/action/…` | POST | Validate, cancel, calculate tax, apply/unapply prepayment, generate/reverse distributions |
| Payment actions `/action/…` | POST | Stop payment, initiate escheatment |
| Reference lists (LOVs) | GET | Suppliers, payment terms, hold codes, business units, ledgers, legal entities, currencies |

## Prompts

| # | Prompt | Type | Tool | Oracle API | Columns returned |
|---|---|---|---|---|---|
| 1 | Show all invoices created today | Read | `ap_list_invoices` | GET `invoices` | Invoice Number, Supplier, Amount, Currency, Status |
| 2 | List unpaid invoices over 10,000 for Vision Operations | Read | `ap_list_invoices` (filter) | GET `invoices?q=InvoiceStatus=Unpaid;InvoiceAmount>1000` | Invoice, Supplier, Amount, Due Date |
| 3 | Get details of invoice 300100123 | Read | `ap_get_invoice` | GET `invoices/{id}` | Full header: supplier, dates, amount, terms, status, business unit, description |
| 4 | Create an invoice | Write | `ap_create_invoice` | POST `invoices` | New invoice with its id |
| 5 | Update an invoice | Write | `ap_update_invoice` | PATCH `invoices/{id}` | Updated invoice fields |
| 6 | Delete an invoice | Write | `ap_delete_invoice` | DELETE `invoices/{id}` | Deletion confirmation |
| 7 | Validate invoice INV-1042 | Action | `ap_validate_invoice` | POST `…/validateInvoice` | Validation outcome |
| 8 | Cancel invoice INV-1099 | Action | `ap_cancel_invoice` | POST `…/cancelInvoice` | Cancellation result |
| 9 | Apply available prepayments to invoice 300100123 | Action | `ap_apply_prepayment` | POST `…/applyPrepayments` | Prepayment application result |
| 10 | Which invoices are on hold for Advanced Network Devices? | Read | `ap_list_invoice_holds` | GET `invoiceHolds` | Held invoices with hold name and reason |
| 11 | Put invoice 300100123 on hold | Write | `ap_create_invoice_hold` | POST `invoiceHolds` | New hold record with reference |
| 12 | Release the hold on invoice 300100123 | Write | `ap_update_invoice_hold` | PATCH `invoiceHolds/{id}` | Updated (released) hold |
| 13 | Show me 10 active suppliers | Read | `ap_list_suppliers` | GET `suppliers` | Supplier Name, Number, Type, Status |
| 14 | Create a new supplier called Globex Ltd | Write | `ap_create_supplier` | POST `suppliers` | New supplier number and id |
| 15 | What sites does supplier Acme have? | Read | `ap_list_supplier_sites` | GET `suppliers/…/sites` | Sites with procurement business unit and pay setup |
| 16 | List payments made this month | Read | `ap_list_payments` | GET `payablesPayments` | Payment Number, Supplier, Amount, Date, Status |
| 17 | Create a payment | Write | `ap_create_payment` | POST `payablesPayments` | New payment with its id |
| 18 | Stop payment on check 45012 | Action | `ap_stop_payment` | POST `…/initiateStopPayment` | Stop-payment confirmation |
| 19 | List payment batches | Read | `ap_list_payment_process_requests` | GET `paymentProcessRequests` | PPRs and status |
| 20 | List expense reports | Read | `ap_list_expense_reports` | GET `expenseReports` | Expense reports table |
| 21 | Supplier lookup | Read | `ap_lov_suppliers` | GET `suppliersLOV` | Matching suppliers with ids |
| 22 | What payment terms are available? | Read | `ap_lov_payment_terms` | GET `payablesPaymentTerms` | Payment terms (Net 30, Net 45) with ids |
| 23 | Business-unit lookup | Read | `ap_lov_business_units` | GET `finBusinessUnitsLOV` | Business units with ids |

_Full 75 tools follow `ap_<action>_<object>` across every resource above._

---

# 4. Purchase Orders / Procurement (PO)

Source: Oracle Fusion Procurement MCP Tool document. Overlaps with Spire's existing
Supplier / PO / Invoice coverage — dedupe before building.

## Endpoints

| Resource | Endpoint |
|---|---|
| Purchase Orders | `/purchaseOrders` |
| PO Details | `/purchaseOrders/{POHeaderId}` |
| PO Lines | `/purchaseOrders/{POHeaderId}/child/lines` |
| PO Schedules | `/purchaseOrders/{POHeaderId}/child/lines/{POLineId}/child/schedules` |
| PO Distributions | `…/schedules/{ScheduleId}/child/distributions` |
| Suppliers | `/suppliers` |
| Supplier Sites | `/suppliers/{SupplierId}/child/sites` |
| Supplier Contacts | `/suppliers/{SupplierId}/child/contacts` |
| Invoices | `/invoices` |
| Receipt Requests | `/receivingReceiptRequests` |

## Prompts

| # | Prompt | Type | Endpoint | Columns returned |
|---|---|---|---|---|
| 1 | List all open POs for supplier 'EIP Inc' | Read | `/purchaseOrders` (filter supplier) | — to fill |
| 2 | What is PO US164932 about? Show its lines | Read | `/purchaseOrders/{id}` + `/child/lines` | Header: Supplier, Status, Buyer, Bill-to/Ship-to, Payment Terms, Total, Order Date. Lines: Line, Description, Category, Qty, Price, Ordered, Tax, Total, Status |
| 3 | For that PO, how much received versus ordered | Read | `/purchaseOrders` + `/receivingReceiptRequests` | — to fill |
| 4 | Find supplier 'Lee Supplies' and show sites and contacts | Read | `/suppliers` + `/child/sites` + `/child/contacts` | Sites (name, business unit); Contacts (Name, Email) |
| 5 | Which invoices raised against PO US164932? | Read | `/invoices` (filter PO) | — to fill |
| 6 | All invoices for supplier 'Staffing Services' this year | Read | `/invoices` (filter supplier + date) | — to fill |
| 7 | List POs with status 'Incomplete' and total value | Aggregate | `/purchaseOrders` (filter + sum) | Count + total (e.g. "200 POs, $3,655,946.16"); page-limit cap 200 |
| 8 | Analyze PO data — delayed POs, commitments, budget, concentration risk | Aggregate | `/purchaseOrders` (+ analysis) | — to fill |
| 9 | Get one PO with expand=all; full nested structure | Read | `/purchaseOrders/{id}?expand=all` | Header (~90 attrs: OrderNumber, Status, Supplier, SupplierSite, Buyer, Total, TotalTax, PaymentTerms, ShipTo/BillTo), DFF, lines, schedules, distributions (nested) |
| 10 | Schedules for line 1 of PO 560869, incl ship-to and need-by date | Read | `…/lines/{id}/child/schedules` | — to fill |
| 11 | Retrieve suppliers whose name contains 'Corp' | Read | `/suppliers` (name filter) | Supplier, Number, Status |
| 12 | Pull invoices created in last 30 days, newest first | Read | `/invoices` (date filter, sorted) | — to fill |
| 13 | For supplier id 300000047507499, list sites, flag pay vs purchasing | Read | `/suppliers/{id}/child/sites` | — to fill |
| 14 | Distribution accounts behind PO US164932's schedules | Read | `…/schedules/{id}/child/distributions` | — to fill |
| 15 | Test PO number 'DOES-NOT-EXIST' (error case) | Read | `/purchaseOrders` | — to fill |
| 16 | Return only OrderNumber, Supplier, Total for latest 20 POs | Read | `/purchaseOrders` (projection, limit 20) | OrderNumber, Supplier, Total (requested) |
| 17 | High-level PO summary — total value, count, top suppliers, month trend | Aggregate | `/purchaseOrders` (+ analysis) | — to fill |
| 18 | Total committed PO spend and open PO count | Aggregate | `/purchaseOrders` (sum + count) | — to fill |
| 19 | Top 5 suppliers by PO value | Aggregate | `/purchaseOrders` (group + rank) | — to fill |
| 20 | Any POs stuck or stale? Explain why | Aggregate | `/purchaseOrders` (+ analysis) | — to fill |
| 21 | How much invoiced vs ordered with largest supplier | Aggregate | `/purchaseOrders` + `/invoices` | — to fill |
| 22 | (duplicate of #21) | Aggregate | `/purchaseOrders` + `/invoices` | — to fill |
| 23 | One-paragraph procurement health summary | Aggregate | `/purchaseOrders` (+ narrative) | — to fill |
| 24 | Flag single supplier over-reliance and quantify risk | Aggregate | `/purchaseOrders` (concentration) | — to fill |
| 25 | 10 most recent POs with supplier, status, total | Read | `/purchaseOrders` (projection, limit 10) | Supplier, Status, Total (requested) |

---

## Status of column capture

| Module | Source | Columns |
|---|---|---|
| AR | docx (images) | #1–6 captured; #7–18 to fill |
| GL | PDF | complete |
| AP | PDF | complete (23 representative of 75 tools) |
| PO | docx (images) | #2, 4, 7, 9, 11, 16, 25 captured; rest to fill |

"— to fill" cells are outputs that live in source-document images not yet
readable; complete them from the originals.
