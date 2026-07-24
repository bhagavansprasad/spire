# Spire Fusion Endpoints Reference

**Purpose:** A single reference for the Oracle Fusion REST endpoints used in the Spire POC. Each entry describes what the endpoint is for, how to call it, what it returns, and known quirks.

**For:** The KG experiment POC, where the property graph encodes which endpoint to call for what purpose and which join keys connect them.

**Pod:** `https://fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com`
**Auth:** Basic Auth (use `-u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD"`)
**API version path:** `/fscmRestApi/resources/11.13.18.05/` (FSCM) and `/hcmRestApi/resources/11.13.18.05/` (HCM)

---

## Discovery log

Findings observed during POC work that updated or corrected this document.

| Date | Endpoint | Discovery |
|---|---|---|
| 2026-05-20 | /invoices       | `PaidStatus` and `ApprovalStatus` exist on default response; values are display strings (`"Paid"`, `"Not required"`), not codes |
| 2026-05-20 | /purchaseOrders | Field is `Ordered` (not `OrderTotalAmount`). Also: `Total` (includes tax), `OrderDate`, `PaymentTerms`, `SupplierSiteId` exist on default response |
| 2026-05-20 | (all)           | The `?fields=...` parameter is strict: if any field in the list is invalid, the whole response is empty with no error |
| 2026-05-22 | /suppliers      | Composite `q=` clauses (e.g., `q=Supplier LIKE '%Lee%' AND Status='ACTIVE'`) silently return 0 items with HTTP 200, even when matches exist. Confirms the composite-`q=` quirk is not just on `/invoices` and `/purchaseOrders` — it applies to `/suppliers` too. Likely applies across all Fusion REST endpoints on this pod. |
| 2026-07-08 | /suppliers      | Server-side `q=BusinessRelationship='Spend Authorized'` **works** (returned `totalResults: 372`) — unlike `Status`, this field is reliable via `q=`. Two values on the pod: `Spend Authorized` (372), `Prospective` (40), confirmed across 500 rows. Spire still applies this filter client-side by choice, to keep it combinable (only one server `q=` clause is reliable per call). |
| 2026-07-08 | /suppliers      | `expand=addresses` returns a DIFFERENT child count depending on query shape. A bulk fetch (`limit=500`, no `q=`) returned 30 addresses for supplier 1252; a single-supplier fetch (`q=SupplierNumber='1252'&expand=addresses`) returned 25. All 30 are ACTIVE — the extra 5 are real, not inactive/junk. The single-supplier `q=` path appears to cap or filter child rows. Use the bulk path for the complete active address set; do not treat a single-supplier expand as ground truth for address counts. |
| 2026-07-09 | /suppliers/{id}/child/sites | Supplier sites carry `ProcurementBU` (display, e.g. `"US1 Business Unit"`), `ProcurementBUId` (numeric), `SupplierSiteId`, `SupplierSite`. Single-clause `q=ProcurementBU='...'` **works server-side** on this child (positive returns the row, non-existent value returns empty — both verified). No SupplierId in the child body; join key is the URL path. **`expand=sites` on the bulk supplier fetch is silently ignored** (HTTP 200, no `sites` key) — child data is only reachable per-supplier via the `/child/sites` path. Used for Phase 12 (`has_site_in_bu`). |
| 2026-07-09 | /suppliers/{id}/child/businessClassifications | Classifications carry `Classification` (display, e.g. `"Small Business"`), `ClassificationCode` (`"SMALL_BUSINESS"`), `Status` (`"CURRENT"`), `CertifyingAgency` (`"SBA"`), `ClassificationId`. Single-clause `q=Classification='...'` **works server-side** (positive returns the row, non-existent value returns empty — both verified). Suppliers carry multiple classifications; no SupplierId in the child body (join key is the path). A `Status='CURRENT'` condition cannot be AND-combined with `Classification` in one `q=` (composite quirk) — apply Status client-side if needed. Used for Phase 13 (`has_classification`). |
| 2026-07-14 | /purchaseOrderSchedules | **A FLAT top-level schedules collection exists** and accepts single-clause `q=POHeaderId=<id>` server-side — so a PO's schedules are a ONE-HOP fetch by a single id, unlike lines (a nested child). Flat field names DIFFER from the nested `/child/schedules` view: `ScheduleStatus` (not Status), `Amount` (not Ordered), `ShipToLocation` (not ShipToLocationCode). The flat row carries `LineLocationId` (schedule PK), `POHeaderId`, `LineNumber`, `ScheduleNumber`, `OrderNumber` — and `POLineId` IF requested in `fields=` (not in the default projection). |
| 2026-07-14 | /purchaseOrderDistributions | **Does NOT exist — 404.** No flat distributions collection. Distributions are reachable ONLY via the deep nested path, which needs three ids. |
| 2026-07-14 | /purchaseOrders/{h}/child/lines/{l}/child/schedules/{ll}/child/distributions | The four-level nested path **works**. Needs THREE ids (POHeaderId, POLineId, LineLocationId), all carried on the parent flat-schedule row — which is why distributions are fetched by iterating a PO's schedules. Fields: `PODistributionId`, `DistributionNumber`, `POChargeAccount`, `POAccrualAccount`, `POVarianceAccount`, `DeliverToLocationCode`, `Percentage`, `Quantity`, `Ordered`, `Total`, `Status`/`StatusCode`. Body carries POHeaderId, POLineId, OrderNumber, ScheduleNumber, LineNumber — but NOT LineLocationId. |
| 2026-07-14 | /purchaseOrderSchedules/{id}/child/distributions | **404.** The flat schedules resource has no distributions child; the deep path under `/purchaseOrders` is the only route. |
| 2026-07-14 | /suppliers/{id}/child/contacts | Supplier contacts child. Fields: `SupplierContactId`, `ContactName` (display, last-first e.g. `"Kim, John"`), `FirstName`, `LastName`, `Email`, `JobTitle` (null on this pod), `Status`, `AdministrativeContactFlag` (marks the primary contact), plus phone/fax (all null on demo data). Like sites/classifications, the body does NOT carry SupplierId — join key is the URL path. |
| 2026-07-17 | /invoices | **`PurchaseOrderNumber` is on the invoice HEADER** and `q=PurchaseOrderNumber='<num>'` **filters server-side**. The value is the PO NUMBER (OrderNumber, e.g. `"162034"`), NOT POHeaderId — the same string-vs-numeric asymmetry as SupplierNumber vs SupplierId. Many invoices have it null (e.g. IMAGE-source invoices with no PO). Invoice numbers often follow `<PO>-inv` / `<PO>inv`. |
| 2026-07-17 | receivingTransactions | **403 Forbidden.** The natural receipts query resource; our user lacks the receiving role. |
| 2026-07-17 | receivingReceipts | **400**: "At least one of the following attributes ShipmentHeaderId, ReceiptNumber is required." A lookup-by-receipt resource — you CANNOT query it by PO. |
| 2026-07-17 | receivingReceiptRequests | Exists with data, but it is an **interface/staging** resource (`HeaderInterfaceId`, `ProcessingStatusCode`, `submitForApproval` action). Its header carries **no PO reference at all**. Not a query view of receipts. |
| 2026-07-17 | /purchaseOrderSchedules | **Received-vs-ordered lives here.** The schedule row carries `ReceivedQuantity`, `BilledQuantity`, `ShippedQuantity`, `AcceptedQuantity`, `ReceivedAmount`, `BilledAmount` alongside the ordered `Quantity`/`Amount`. Given the receipts resources above are unusable, this is the source for "how much of PO X was received". |
| 2026-07-17 | (all children) | **Child paths 404 for an unknown parent id** — they do NOT return an empty collection. `/purchaseOrders/999999999/child/lines`, `/suppliers/999999999/child/contacts` and the nested distributions path all 404. Child-fetch tools must catch the 404 and map it to "no rows". By contrast, FLAT collections filtered by `q=` (e.g. `/purchaseOrderSchedules?q=POHeaderId=999999999`) return an empty item set, not a 404. |
| 2026-07-17 | /purchaseOrders/{id} | **Single-record fetch 404s for an unknown id** (unlike the collection, which returns empty items). A by-id tool must map the 404 to "not found". |
| 2026-07-17 | (pod switch) | **An empty collection on a freshly-provisioned pod may mean "still loading"** — not "no access", not "bad fields". On pod `eqjz`, `/purchaseOrders` returned `count: 0` (HTTP 200) for a period, with AND without `fields=`, while `/purchaseOrderSchedules` returned rows referencing those same POs. It later populated normally. Before escalating an empty collection as a permissions problem, re-test after a delay and cross-check a sibling resource. |
| 2026-07-19 | /purchaseOrders | **POs carry NO `SupplierNumber`.** Naming `SupplierNumber` in `?fields=` on `/purchaseOrders` returns **HTTP 400** — POs expose only `SupplierId` (numeric). This is the reason the top-N supplier comparison must resolve each supplier's number from its id (one `/suppliers?q=SupplierId=` lookup) before it can filter invoices (which use `SupplierNumber`). |
| 2026-07-19 | (all collections) | **`totalResults=true` is required for a real total count.** Without it, the `count` field reflects only the returned page size (e.g. `limit=1` → `count: 1`, not the true total). Pass `totalResults=true` to get the authoritative `totalResults` value. Easy to misread `count` as a total during discovery. |
| 2026-07-19 | AR receivables | **`TransactionClass` is not queryable.** A `q=` filter on `TransactionClass` (on the AR receivables resources) is rejected: *"The attribute(s) [TransactionClass] are not queriable."* The attribute is returned in the body but not server-filterable — filter client-side. See the "Non-queryable attributes" section for the running list. |
| 2026-07-19 | /invoices | **Most invoices are NOT PO-linked — quantified.** `PurchaseOrderNumber` is null for the overwhelming majority of invoices on the demo pods. Sampled PO-linked fraction by supplier: Staffing Services 0%, Allied Manufacturing 0%, Advanced Corp 1%, Lee Supplies 7%; ~1% overall across a 1,000-invoice sample of 48,904 total. The non-PO invoices are debit memos, prepayments, and credits (e.g. `StafDM 01`, `PREPAYMENT001`, negative amounts). Consequence: a supplier-level "invoiced vs ordered" comparison is thin on these pods — PO-matched invoiced runs far below total invoiced. A demo-data limitation, not a product one (real customers PO-match via three-way matching). Report `unmatched_invoice_count` so the gap is visible. |
| 2026-07-19 | (pod) | **Active pod is `fa-esll-dev37`** (this reference's pod). The `eqjz` and `dabpqy` pods seen in earlier sessions are alternates in `personas.yaml`. Anchor ids are pod-specific — a pod switch can invalidate hard-coded test anchors (e.g. distribution chain ids); re-capture from the active pod rather than assuming. |
| 2026-07-19 | /receivablesInvoices | **AR invoice header.** Canonical id is `CustomerTransactionId` (NOT "InvoiceId"); human number is `TransactionNumber`. Amount is `EnteredAmount`; open balance is `InvoiceBalanceAmount` (0 = paid). Also: `BillToCustomerName`/`BillToCustomerNumber`/`BillToPartyId`, `InvoiceCurrencyCode`, `TransactionDate`/`DueDate`/`AccountingDate`, `InvoiceStatus` (display, e.g. "Complete"), `TransactionType`, `TransactionSource`, `BusinessUnit`. 173,531 rows. Children: `receivablesInvoiceLines`, `receivablesInvoiceInstallments`, `receivablesInvoiceDistributions`, `receivablesInvoiceDFF`, `receivablesInvoiceTransactionDFF` (TWO DFF children — see quirk 8), `attachments`, `notes`, `receivablesInvoiceGdf`. Actions (WRITES): `approve`, `rework`, `splitInstallments`. |
| 2026-07-19 | /receivablesInvoices/{id}/child/receivablesInvoiceLines | AR invoice lines. Fields: `CustomerTransactionLineId` (PK), `LineNumber`, `Description`, `Quantity`, `UnitSellingPrice`, `LineAmount`, `UnitOfMeasure`, `ItemNumber`, `TaxClassificationCode`, `TaxExemptionHandling`, `LineAmountIncludesTax`, `AssessableValue`. **`TransacationBusinessCategory` is misspelled by Oracle** ("Transacation") — must match the typo exactly. Line children: `receivablesInvoiceLineTaxLines` (prompt 3 tax lines — a GRANDCHILD of the invoice, three levels deep), `receivablesInvoiceLineDFF`, `receivablesInvoiceLineTransactionDFF`. |
| 2026-07-19 | /standardReceipts | **AR cash receipts — carries everything the three AR aggregates need.** Fields: `StandardReceiptId`, `ReceiptNumber`, `Amount`, `Currency`, `ReceiptDate`, `ReceiptMethod` (display, e.g. "Lockbox" — prompt 17 buckets by this), `State` ("Applied"), `Status` ("Cleared"), `UnappliedAmount`, `AccountedAmount`, `CustomerName`, `CustomerAccountNumber`, `CustomerSite`, `RemittanceBankName`/`Branch`/`AccountNumber`, `CreationDate` + `LastUpdateDate` (prompt 18 lag), `AccountingDate`, `MaturityDate`, `ReceiptBatchName`/`Date`. 37,335 rows. Action (WRITE): `applyReceipt`. NOTE: demo data backfilled — `ReceiptDate` (2012) can predate `CreationDate` (2014); `LastUpdatedBy` seen as "0". |
| 2026-07-19 | /receivablesCustomerAccountActivities | **The AR customer/balance view — Spire's customer entity for AR.** Fields: `AccountId` (PK), `AccountNumber`, `CustomerName`, `CustomerId`, `TotalOpenReceivablesForAccount` (prompt 10 exposure sort key), `TotalTransactionsDueForAccount`, `CreationDate`/`LastUpdateDate`. Only 435 rows (≈ customer-account count — exposure ranking is cheap). Children (account-scoped prompts hang here by `AccountId`): `creditMemos` (prompt 7), `standardReceipts` (prompt 8), `standardReceiptApplications` (prompt 9), `creditMemoApplications`, `transactionAdjustments`, `transactionPaymentSchedules`, `transactionsPaidByOtherCustomers`. |
| 2026-07-19 | /receivablesCreditMemos | AR credit memos. **Same object model as `/receivablesInvoices`** — `CustomerTransactionId`, `TransactionNumber`, `BillToCustomerName`/`Number`, same child set + `approve`/`rework` actions. Both are `receivablesTransactions` split by `TransactionType`. Distinct: `EnteredAmount` is NEGATIVE (e.g. -408.90), `CreditMemoStatus`, `TransactionBalanceDue`, `CreditReason`. 2,111 rows. |
| 2026-07-19 | /receivablesCustomers | **404 — resource does not exist.** The name in the AR source catalog is wrong. For AR customer identity/balances, use `/receivablesCustomerAccountActivities`. Do not model a customer entity from a `/receivablesCustomers` endpoint. |
| 2026-07-19 | crmRestApi /accounts | Exists (1,476 rows) but is the **CRM/Sales customer**, NOT the AR master. Keys on `PartyId`/`PartyNumber` — a DIFFERENT id space from AR's `CustomerId`/`AccountNumber`. Carries sales data (opportunities, territories, `AccountScore`, DUNS), not receivables. Ruled out as AR's customer source. The collection action `getFinancialCustomerInfo` is the documented sales→financial bridge for a future cross-pillar prompt. |
| 2026-07-21 | /receivablesCustomerAccountActivities/{id}/child/transactionPaymentSchedules | **`TotalBalanceAmount` is sortable but NOT queryable — the open-invoice window strategy (AR-P2c).** `q=TotalBalanceAmount>0` is rejected (*"The attribute(s) [TotalBalanceAmount] are not queriable."*), BUT `orderBy=TotalBalanceAmount:desc` **works server-side**. Since an account can carry thousands of rows (this anchor has `totalResults: 7404`), the open filter is applied via SORT, not paging: `orderBy=TotalBalanceAmount:desc`, over-fetch a bounded window, then keep `TransactionClass=='Invoice'` AND `TotalBalanceAmount>0` client-side, slice top N. Open rows carry `InstallmentStatus: "Open"` (paid rows: `"Closed"`, balance 0). Anchor `AccountId=300000047368527` (ABC Corporation Americas): top open invoices 216378, 206008, 198286, 56412, 39969. NOTE: `orderBy` sorts across transaction classes, so the client-side Invoice-class keep still matters on mixed accounts. |
| 2026-07-21 | /receivablesInvoices/{txnId}/child/receivablesInvoiceLines/{lineId}/child/receivablesInvoiceLineTaxLines | **AR tax lines (prompt 3) — a grandchild reached with TWO ids (invoice + line), NOT three.** Unlike PO distributions (three sibling ids from one schedule row), the tax child needs only the parent line id, which the line row carries — so it's a plain nested grandchild fetched by chaining single-parent iterations (invoice→lines→taxLines), reusing the existing executor path, NOT the HAS_DISTRIBUTION `iter_fields` branch. The nested path resolves for an untaxed line but returns `count:0` (original anchor invoice 61765 is untaxed). Fields: `TaxLineNumber`, `TaxJurisdictionCode`, `TaxRate` (e.g. 2.25), `TaxRateCode` ("STD"), `TaxRegimeCode` ("US SALES AND USE TAX"), `TaxStatusCode` ("STANDARD"), `Tax` (the tax type, e.g. "COUNTY"), `TaxAmount`, `TaxableAmount`, `TaxInclusiveIndicator` ("No"/"Yes"), `TaxPointDate`, plus audit fields. NOTE: the tax-line row's own `CustomerTransactionLineId` is the TAX line PK (e.g. 112), distinct from the parent invoice-line id (74). Taxed anchor: invoice `1002` (TransactionNumber 5), line `74` → 2 tax lines (STD/COUNTY 2.25%, and a second); lines 84/93/107 each carry 2 as well. |
| 2026-07-22 | /receivablesCustomerAccountActivities/{id}/child/creditMemos | **A DISTINCT child, NOT a filtered view of `/receivablesCreditMemos` (settles the AR-P5 prompt-7 open question).** Different id space: PK is `CreditMemoId` (small int, e.g. 12222 / 1284799) — NOT the top-level resource's `CustomerTransactionId`. Different projection too: `CreditMemoNumber`, `CreditMemoDate`, `TotalOriginalAmount`, `TotalBalanceAmount`, `AvailableAmount`, `InstallmentId`, `TransactionClass` (\"On Account Credit Memo\"), `CreditMemoStatus`, `CreditMemoCurrency`, `BillToSiteNumber` — this is the installment/payment-schedule view, a sibling of `transactionPaymentSchedules`, not the transaction view. So prompt 7 needs its OWN entity, tool and synthesizer id set; it cannot reuse AR-P4. `orderBy=CreditMemoDate:desc` and `fields=` both work server-side. Anchor `AccountId=300000047368512`: `totalResults: 280`, newest 2023-07-15 (CreditMemoId 1284799, -215.33, Open). Open memos carry a non-zero `TotalBalanceAmount`; closed ones sit at 0. Row does NOT echo `AccountId` — join key is the URL path. |
| 2026-07-22 | /receivablesCustomerAccountActivities/{id}/child/standardReceipts | **Prompt 8 — account receipts.** `orderBy=ReceiptDate:desc` and `fields=` work server-side. Thinner and DIFFERENTLY named than the top-level `/standardReceipts`: has `ProcessStatus` where the top-level has `Status`, and omits `CustomerName`, `CustomerAccountNumber` and all bank fields. **`StandardReceiptId` mixes id widths in one collection** — backfilled rows are small ints (130, 131), recent ones are large (300000313660599). Never assume id width. `CustomerSite` is present but NULLABLE (null on the newest row). Anchor `AccountId=300000047368512`: `totalResults: 1559`, newest 2026-06-30. Row does NOT echo `AccountId`. |
| 2026-07-22 | /receivablesCustomerAccountActivities/{id}/child/standardReceiptApplications | **Prompt 9 — receipt applications, a PRE-JOINED bridge row (no join needed).** Carries the receipt side (`StandardReceiptId`, `ReceiptNumber`, `ReceiptMethod`) AND the transaction side (`ReferenceTransactionId`, `ReferenceTransactionNumber`, `ReferenceTransactionStatus`, `ReferenceInstallmentId`) on ONE record, plus `ApplicationAmount`, `ApplicationDate`, `ApplicationStatus`, `EnteredCurrency`, `CustomerSite`. PK is `ApplicationId` — a FOURTH distinct AR id space. `ReferenceTransactionId` is a SMALL int (8869) matching the `transactionPaymentSchedules` space, NOT `/receivablesInvoices`' `CustomerTransactionId`. `orderBy=ApplicationDate:desc` and `fields=` work. **TRAP: the newest rows are unapplied cash, not applications** — `ApplicationStatus: \"Unapplied\"` with ALL THREE `ReferenceTransaction*` fields null, so a naive recent-N top slice returns rows whose entire transaction side is empty. Filter `ApplicationStatus == 'Applied'` client-side. **`IsLatestApplication` does NOT mean what its name suggests** — \"N\" on the newest rows, \"Y\" on 2012 rows; do not filter on it. Anchor: `totalResults: 15636` (largest AR-P5 child). Has its own `standardReceiptApplicationDFF` child. |
| 2026-07-22 | /standardReceipts | **A `?fields=` projection 500s here.** First observed by naming `ProcessStatus` (a child-only field, absent from the top-level resource); initially read as a dead endpoint, costing four misdiagnosed calls. **SUPERSEDED by the row below — the failure is not limited to invalid names; all-valid projections 500 too.** Separately confirmed on the same day: `q=` and `totalResults=true` are BOTH fine on this collection — `q=CustomerAccountNumber=26360` returns `totalResults: 1386` server-side, a bare `totalResults=true` returns 37,337. Also: the collection has **no default ordering** — two identical unordered calls returned different first rows (117, then 11350), so unordered fetches are not reproducible. |
| 2026-07-22 | (AR account children) | **The account-child receipt count (1559) EXCEEDS the account-number-filtered top-level count (1386).** Same anchor account (`AccountId=300000047368512` / `CustomerAccountNumber=26360`), same nominal concept, 173-row gap. Unexplained — the child collection appears more broadly scoped than the `CustomerAccountNumber` filter. **OPEN QUESTION:** do not treat the two as interchangeable sources for a receipt count, and settle this before any prompt reports a receipt total. |
| 2026-07-22 | /standardReceipts | **`?fields=` is UNUSABLE on this endpoint — it 500s even when every named field is valid.** Confirmed twice: a projection of `StandardReceiptId,ReceiptDate,Amount,CustomerName,CustomerAccountNumber,CustomerSite` — every one of which appears in a live unprojected response from this same resource — returned HTTP 500 when combined with `q=`. Dropping `fields=` and changing nothing else returned 200. This is STRONGER than quirk 7 (which is about invalid names): here even valid names fail. Do not project on `/standardReceipts`; fetch the full row and discard fields client-side. Cost six misdiagnosed calls across this session, twice read as a dead endpoint. |
| 2026-07-22 | /standardReceipts | **`CustomerSite` IS queryable here** (unlike on the `standardReceipts` child, where it 400s): `q=CustomerSite='Santa Clara'` returns HTTP 200, `totalResults: 1735`. `orderBy=CustomerAccountNumber` also works. **BUT the site spans multiple customer accounts** — ascending sort returns account 26360 (ABC Application Software), descending returns 26370 (ABC Corporation Americas), both at site "Santa Clara". So a site-only filter is NOT customer-scoped: 1,735 site-wide vs 1,386 for account 26360 alone. A prompt asking for "receipts at Santa Clara" for a named customer MUST constrain both. |
| 2026-07-22 | /standardReceipts | **Composite `q=` fails SILENTLY here — HTTP 200 with `totalResults: 0`.** `q=CustomerSite='Santa Clara' AND CustomerAccountNumber=26360` returns zero rows, although each clause alone returns thousands (1,735 and 1,386 respectively) and their true intersection is non-empty. Confirms quirk 1 applies to this endpoint. **This is the dangerous failure mode**: a tool built on composite `q=` would report "no receipts at that site for this customer" — a plausible-looking, wholly wrong answer, with no error to catch. Prompt 13's design follows from this: filter `q=CustomerAccountNumber` server-side (the more selective clause), then match `CustomerSite` client-side, handling nulls. |
---

## Environment setup (run once in your shell)

```bash
export IKS_FUSION_BASE_URL="https://fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com"
export IKS_FUSION_USERNAME="<your username>"
export IKS_FUSION_PASSWORD="<your password>"

# Sanity check
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?limit=1" \
  -w "\nHTTP %{http_code}\n"
```

Expected: HTTP 200 with a JSON body containing one supplier.

---

## Quick reference table

| Endpoint | Path | Purpose | Spire tool that wraps it |
|---|---|---|---|
| 1 | `/suppliers` | Find suppliers by name fragment | `search_suppliers` |
| 2 | `/suppliers?expand=addresses` | Find suppliers in a country | `search_suppliers_by_country` |
| 3 | `/invoices` | Find invoices by supplier + date | `search_invoices` |
| 4 | `/purchaseOrders` | Find POs by supplier + status | `search_purchase_orders` |
| 5 | `/publicWorkers` (HCM) | Look up a buyer by ID | `get_buyer` |

---

## Join key matrix (critical for the KG)

This is the **SupplierNumber-vs-SupplierId asymmetry** that crashed Track A:

| To search this | Use this join key on the supplier side | Numeric or string? |
|---|---|---|
| `/invoices` | `SupplierNumber` | string (e.g., `"1252"`) |
| `/purchaseOrders` | `SupplierId` | numeric (e.g., `300000047572113`) |
| `/publicWorkers` | `PersonId` | numeric (matches PO's `BuyerId`) |

**The KG must encode this per-edge.** The same conceptual entity (a supplier) is identified differently by different endpoints. Don't assume one ID works everywhere.

---

## Known Fusion quirks (apply to multiple endpoints)

These hit you on more than one endpoint, so call them out once:

1. **Composite q= filters fail**. Multi-clause q= strings (q=Field1=X AND Field2=Y) return HTTP 500 or silently empty results on every endpoint tested so far (/suppliers, /invoices, /purchaseOrders, and — confirmed 2026-07-22 — /standardReceipts, where two individually-valid clauses returning 1,735 and 1,386 rows combined to HTTP 200 / `totalResults: 0`). Assume this quirk applies to all Fusion REST endpoints on this pod until proven otherwise. Workaround used in Spire: send the most selective single clause via q=, over-fetch (limit=200), filter the rest client-side. NOTE the silent-zero variant is the dangerous one — a tool built on composite q= returns a plausible "no matching rows" with no error to catch.

2. **Country isn't on supplier directly.** Suppliers have addresses as a child resource. Country lookup needs `?expand=addresses`, then filter client-side for any address with matching `Country` code.

3. **No FSCM `buyers` endpoint.** Buyers are HCM workers. There is no `/fscmRestApi/.../buyers`. Use `/hcmRestApi/.../publicWorkers` with `PersonId = BuyerId`.

4. **OWSM 401 noise.** Sometimes REST calls return 401 with empty body and `WWW-Authenticate: Basic realm="owsm"` for ~30 minutes mid-day. Resolves itself. Not a credential problem; it's pod-side.

5. **Pagination via `offset` and `limit`.** Standard Fusion pattern. Default `limit` is often small (10 or 25). If you need more, pass `limit=N`. Max practical limit before things get slow: ~200.

6. **Fields parameter to project.** Use `?fields=Field1,Field2,Field3` to limit what comes back. Spire tools project to small field sets to avoid bloating LLM context.

7. **`?fields=` is strict on invalid names — and the failure mode VARIES by endpoint.** If even one field in a `?fields=...` list doesn't exist on the endpoint, the request fails. On most endpoints the response comes back empty with no error and no warning. **On `/standardReceipts` it returns HTTP 500 — and worse, that endpoint 500s on projections where every named field IS valid** (confirmed 2026-07-22, twice). Treat `fields=` as unusable on `/standardReceipts`: fetch full rows and discard fields client-side. Elsewhere, verify each field name against a live unprojected response before relying on a projection. When any 500 appears, drop `fields=` first to isolate it — an unexplained 500 is a projection suspect, not just a dead endpoint (this cost six misdiagnosed calls during AR-P5 discovery, twice read as a dead resource). A corollary of the child-vs-parent field drift below: field names do NOT carry across from a child resource to its top-level namesake.

8. **Two DFF children on AR transactions.** AR invoices, invoice lines, and credit memos each expose TWO descriptive-flexfield children: `...DFF` and `...TransactionDFF` (e.g. `receivablesInvoiceDFF` and `receivablesInvoiceTransactionDFF`). A prompt asking for "DFF values" is ambiguous — decide which, or fetch both. Curled 2026-07-21 on invoice 1002: `receivablesInvoiceDFF` returns `__FLEX_Context = null`; `receivablesInvoiceTransactionDFF` returns `__FLEX_Context = "DOO"` — the context is SET but carries NO populated segment columns (only `CustomerTrxId`, `__FLEX_Context`, `__FLEX_Context_DisplayValue=null`). So `TransactionDFF` is the populated child on this pod, but "populated" means a context label only, not segment values. Prompt 4 uses `receivablesInvoiceTransactionDFF`.

9. **Responses may be gzip-compressed.** Some requests (seen on `/receivablesInvoices` with a `q=` clause) return a gzip-compressed body. A plain `curl ... > t.txt` then writes binary garble. Use `curl --compressed` so curl advertises gzip and decompresses the body. For `q=` values with spaces/quotes, encode with `+` for spaces and `%27` for single-quotes (the existing supplier-LIKE pattern), and redirect to a file — do NOT pipe to `python -m json.tool`, which errors on a gzip/empty body and hides the real output.

---

## Non-queryable attributes (growing list)

Some Fusion attributes are returned in the response body but **cannot be
used in a `q=` filter** — the server rejects the query with:

> `The attribute(s) [<Name>] are not queriable.`

(Note Oracle's spelling: "queriable".) This is distinct from an unknown
field: the attribute is real and appears in results, it just isn't indexed
for server-side filtering. When you hit this, drop the clause and filter
client-side (the same approach used for other non-queryable fields on this
pod). Capture each one here as it's discovered.

| Attribute | Endpoint(s) | Error | Notes |
|---|---|---|---|
| `TransactionClass` | AR receivables resources (e.g. `/receivablesInvoices`, `/receivablesTransactions`) and the `transactionPaymentSchedules` child | `The attribute(s) [TransactionClass] are not queriable.` | Discovered during AR exploration. Returned in the body but not server-filterable. Prompt 15 keeps Invoice-class rows client-side. |
| `BillToCustomerName` | `/receivablesInvoices` | `The attribute(s) [BillToCustomerName] are not queriable.` | Confirmed live (AR-P2b). Cannot filter AR invoices by customer NAME on this endpoint. |
| `BillToCustomerNumber` | `/receivablesInvoices` | `The attribute(s) [BillToCustomerNumber] are not queriable.` | Confirmed live (AR-P2b). Cannot filter AR invoices by customer NUMBER either. A customer's invoices are reached via the account path (`/receivablesCustomerAccountActivities` → `transactionPaymentSchedules`), NOT by filtering this collection. |
| `SupplierNumber` | `/purchaseOrders` | HTTP 400 when named in `?fields=` | POs expose only `SupplierId` (numeric), not `SupplierNumber`. See the join-key matrix and the 2026-07-19 discovery-log row. |
| `TotalBalanceAmount` | `transactionPaymentSchedules` child (of `/receivablesCustomerAccountActivities`) | `The attribute(s) [TotalBalanceAmount] are not queriable.` | Confirmed live (AR-P2c). **But it IS sortable** — `orderBy=TotalBalanceAmount:desc` works server-side, unlike the other rows here. This is the open-invoice window strategy: sort desc, over-fetch, keep `>0` client-side, slice top N (avoids paging the account's thousands of rows). See the 2026-07-21 discovery-log row. |
| `CustomerSite` | `standardReceipts` child (of `/receivablesCustomerAccountActivities`) | `The attribute(s) [CustomerSite] are not queriable.` | Confirmed live (AR-P5 discovery, 2026-07-22). Also **NULLABLE and sparsely populated** — null on the newest receipt of the anchor account — so a client-side site filter must handle nulls, not just non-matches. Appears on three of the four AR account children (`creditMemos` carries it as `BillToSiteNumber` instead). **NOT yet tested for sortability** — if `orderBy=CustomerSite` works, the `TotalBalanceAmount` window strategy above would apply to prompt 13 too. |
| `CustomerSite` (top-level) | `/standardReceipts` | — **IS QUERYABLE** — | Resolved 2026-07-22. `q=CustomerSite='Santa Clara'` returns HTTP 200 / `totalResults: 1735`. (The earlier 500 was the `fields=` projection, not this clause.) **But it is not customer-scoped** — the same site name spans accounts 26360 and 26370 — and it CANNOT be AND-combined with `CustomerAccountNumber` (composite `q=` returns a silent 0 here). So a customer-scoped site query filters by account server-side and matches site client-side. Contrast the `standardReceipts` CHILD, where the same attribute is NOT queryable. |

> Contrast — a field that IS queryable: `CustomerName` on
> `/receivablesCustomerAccountActivities` accepts `q=CustomerName='...'`
> (exact match), confirmed live (AR-P2b). This is the resolve point for
> customer-scoped AR queries: customer name → account(s) → traverse to the
> account's transactions. So the account endpoint filters by customer name
> even though the invoice endpoint does not.

---

## 1. `/suppliers` — find suppliers by name fragment

**Purpose:** Search for suppliers whose name contains a substring. Used when the user names a supplier (e.g., "find Lee Supplies").

**Spire tool:** `search_suppliers(name_contains: str)`

**Curl — search for "Lee":**

```bash
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?q=Supplier+LIKE+%27%25Lee%25%27&fields=SupplierId,SupplierNumber,Supplier,Status&limit=25" \
  | python -m json.tool
```

**The `q=` clause unencoded:** `Supplier LIKE '%Lee%'`

**Response shape (truncated):**

```json
{
  "items": [
    {
      "SupplierId": 300000047572113,
      "SupplierNumber": "1252",
      "Supplier": "Lee Supplies",
      "Status": "ACTIVE",
      "links": [...]
    },
    {
      "SupplierId": 300000133943993,
      "SupplierNumber": "1342",
      "Supplier": "Lee Testing for UK BU",
      "Status": "ACTIVE",
      "links": [...]
    }
  ],
  "count": 2,
  "hasMore": false,
  "limit": 25,
  "offset": 0,
  "links": [...]
}
```

**Fields used by Spire:** `SupplierId`, `SupplierNumber`, `Supplier`, `Status`.

**Notes:**
- `SupplierId` is the canonical ID (numeric).
- `SupplierNumber` is a human-readable string ID (used by `/invoices`).
- `Supplier` is the display name.
- `q=` here is single-clause, so it's reliable.

---

## 2. `/suppliers?expand=addresses` — find suppliers in a country

**Purpose:** Filter suppliers by country. Country lives on the child `addresses` resource, not on the supplier itself.

**Spire tool:** `search_suppliers_by_country(country: str)`

**Curl — find US suppliers:**

```bash
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?expand=addresses&fields=SupplierId,SupplierNumber,Supplier,Status,addresses&limit=200" \
  | python -m json.tool
```

**Response shape (truncated):**

```json
{
  "items": [
    {
      "SupplierId": 300000047572113,
      "SupplierNumber": "1252",
      "Supplier": "Lee Supplies",
      "Status": "ACTIVE",
      "addresses": {
        "items": [
          {
            "AddressId": 300000047572200,
            "Country": "US",
            "AddressLine1": "...",
            "City": "...",
            "State": "..."
          }
        ]
      }
    },
    ...
  ],
  "count": 200,
  "hasMore": true
}
```

**How filtering works in Spire:** the tool fetches with `expand=addresses`, then iterates client-side: a supplier matches if **any** of its addresses has `Country == "US"`. A supplier with addresses in multiple countries matches multiple country filters — that's correct behavior.

**Notes:**
- This endpoint over-fetches (limit=200) because there's no server-side filter on a nested-resource field.
- For the demo pod, US-supplier count is ~25.
- Country code is the ISO 2-letter form (`"US"`, `"GB"`, `"FR"`, etc.).

---

## 3. `/invoices` — find invoices by supplier + date

**Purpose:** Find invoices for a specific supplier, optionally filtered by date. Used for "no invoices in the last 6 months" checks.

**Spire tool:** `search_invoices(supplier_number, supplier_name, invoice_date_after)`

**Curl — invoices for supplier 1252 since 2025-11-19:**

```bash
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/invoices?q=SupplierNumber%3D%271252%27&fields=InvoiceId,InvoiceNumber,SupplierNumber,Supplier,InvoiceDate,InvoiceAmount,InvoiceCurrency,PaidStatus,ApprovalStatus&limit=200" \
  | python -m json.tool
```

**The `q=` clause unencoded:** `SupplierNumber='1252'`

**Response shape (truncated):**

```json
{
  "items": [
    {
      "InvoiceId": 300000095000123,
      "InvoiceNumber": "INV-2024-001",
      "SupplierNumber": "1252",
      "Supplier": "Lee Supplies",
      "InvoiceDate": "2024-08-15",
      "InvoiceAmount": 1500.00,
      "InvoiceCurrency": "USD",
      "PaidStatus": "Paid",
      "ApprovalStatus": "Not required"
    },
    ...
  ],
  "count": 5,
  "hasMore": false
}
```

**Notes on status fields:**
- `PaidStatus` values are display strings: `"Paid"`, `"Unpaid"`, etc. — **not** codes.
- `ApprovalStatus` values are display strings: `"Not required"`, `"Approved"`, etc. — **not** codes.
- If you ever build invoice-status vocabulary in the KG, mirror the existing `po_status` pattern but map to these display strings (`"unpaid"` → `"Unpaid"`).

**Date filtering — the workaround:**

Spire does NOT pass `InvoiceDate>='2025-11-19'` as a second `q=` clause. Composite `q=` is broken on this endpoint. Instead:

1. Server-side: `q=SupplierNumber='1252'` (single clause)
2. Over-fetch up to `limit=200`
3. Client-side: filter `items` where `InvoiceDate >= cutoff_date`

The `invoice_date_after` parameter on the Spire tool becomes a client-side filter, not a `q=` clause.

**Notes:**
- Join key from supplier: **`SupplierNumber`** (string), NOT `SupplierId`.
- `InvoiceDate` is ISO date (`YYYY-MM-DD`).
- Currency varies; convert with caution.

---

## 4. `/purchaseOrders` — find POs by supplier + status

**Purpose:** Find purchase orders for a supplier, optionally filtered by status. Used for "has open purchase orders" checks.

**Spire tool:** `search_purchase_orders(supplier_id, supplier_name, status)`

**Curl — open POs for supplier_id 300000047572113:**

```bash
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/purchaseOrders?q=SupplierId%3D300000047572113&fields=POHeaderId,OrderNumber,SupplierId,Supplier,StatusCode,BuyerId,Buyer,ApprovedDate,Ordered,Total&limit=200" \
  | python -m json.tool
```

**The `q=` clause unencoded:** `SupplierId=300000047572113`

**Response shape (truncated):**

```json
{
  "items": [
    {
      "POHeaderId": 300000115234567,
      "OrderNumber": "163588",
      "SupplierId": 300000047572113,
      "Supplier": "Lee Supplies",
      "StatusCode": "OPEN",
      "BuyerId": 300000047340498,
      "Buyer": "Calvin Roth",
      "ApprovedDate": "2024-06-12",
      "Ordered": 3.00,
      "Total": 3.30
    },
    ...
  ],
  "count": 3,
  "hasMore": false
}
```

**Status filtering — same workaround as invoices:**

Composite `q=` is broken here too. Spire does:
1. Server-side: `q=SupplierId=300000047572113`
2. Over-fetch up to `limit=200`
3. Client-side: filter `items` where `StatusCode == "OPEN"`

**StatusCode values observed:**
- `OPEN` — open and active
- `CLOSED`
- `CANCELED`
- `PENDING_APPROVAL`
- (and others)

**Notes:**
- Join key from supplier: **`SupplierId`** (numeric), NOT `SupplierNumber`. **This is the asymmetry that crashed Track A.**
- `BuyerId` is what you pass to `/publicWorkers` to look up the buyer's HCM record.
- `Buyer` (display name) is sometimes present inline, sometimes not — depends on the PO. Don't rely on it.
- The amount field is `Ordered` (excluding tax). `Total` includes tax. The field name `OrderTotalAmount` does NOT exist; do not project it.

---

## 5. `/publicWorkers` (HCM) — look up buyer by PersonId

**Purpose:** Get buyer details (full name, email, username). Buyers live in HCM, not FSCM. The `BuyerId` from `/purchaseOrders` maps to `PersonId` here.

**Spire tool:** `get_buyer(buyer_id: int)`

**Curl — look up buyer with BuyerId 300000047340498:**

```bash
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/hcmRestApi/resources/11.13.18.05/publicWorkers?q=PersonId%3D300000047340498&fields=PersonId,PersonNumber,DisplayName,WorkEmail,Username&limit=1" \
  | python -m json.tool
```

**The `q=` clause unencoded:** `PersonId=300000047340498`

**Response shape:**

```json
{
  "items": [
    {
      "PersonId": 300000047340498,
      "PersonNumber": "1010",
      "DisplayName": "Roth, Calvin",
      "WorkEmail": "CALVIN.ROTH_esll-dev37@oraclepdemos.com",
      "Username": "CALVIN.ROTH"
    }
  ],
  "count": 1,
  "hasMore": false
}
```

**Notes:**
- **Cross-pillar lookup:** this is the only endpoint in this list that's on the HCM API, not FSCM. The path is `/hcmRestApi/...`, not `/fscmRestApi/...`.
- `BuyerId` from `/purchaseOrders` equals `PersonId` here. The KG should encode this explicitly.
- There is NO `/fscmRestApi/.../buyers` endpoint. Don't waste a request looking.
- `DisplayName` is "Last, First" formatted. If you need "First Last", parse it.
- Single buyer at a time. To look up many, call N times (or batch via parallel requests).

---

## End-to-end example: solving the anchor prompt

To answer the POC anchor question:

> *"Show me suppliers in US with open purchase orders, including the buyer assigned to each."*

The conceptual sequence of endpoint calls:

```
Step 1. List US suppliers
        → GET /suppliers?expand=addresses
        → Client-side filter: any address with Country='US'
        → Returns: ~25 US suppliers, each with SupplierId + SupplierNumber

For each US supplier:
  Step 2. Check open POs
          → GET /purchaseOrders?q=SupplierId=<id>
          → Client-side filter: StatusCode == 'OPEN'
          → Keep only suppliers with at least one open PO
          → Collect each open PO's BuyerId

For each unique BuyerId collected:
  Step 3. Look up buyer details
          → GET /publicWorkers?q=PersonId=<buyer_id>
          → Returns: DisplayName, WorkEmail, etc.
```

**Total requests for the anchor prompt against the demo pod:**
- 1 call to `/suppliers?expand=addresses`
- ~25 calls to `/purchaseOrders` (one per US supplier)
- ~3–5 calls to `/publicWorkers` (one per unique buyer found)

So: ~30 endpoint calls total to fully answer the prompt.

**The KG-driven POC's job is to derive this sequence deterministically from the prompt structure**, then execute it. The LLM-based Spire agent variably executes 1–59 of these calls depending on the run (which is exactly why we're trying the KG-driven approach).

> **Historical note:** an earlier version of the anchor prompt included absence reasoning ("no invoices in 6 months"). That clause is out of scope for v1 of the KG (the `no_Y_in_N_months` pattern was removed). If/when absence reasoning is added back, an invoice-check step would precede the PO step.

---

## Date arithmetic (you'll need this)

The "last N months" cutoff is computed by the client, not Fusion. Use Python's `datetime`:

```python
from datetime import date, timedelta

today = date.today()  # e.g., date(2026, 5, 19)
cutoff = today - timedelta(days=180)  # e.g., date(2025, 11, 19)
cutoff_iso = cutoff.isoformat()  # "2025-11-19"
```

Then filter dates where `<DateField> >= cutoff_iso`.

**Important:** the LLM does NOT have a reliable sense of "today" — every phase 10 run got this date wrong by months or years. In a KG-driven executor, this computation MUST happen in Python with `date.today()`, never asked of the LLM.

---

## Curl command quick reference (copy-paste for testing)

All commands assume `IKS_FUSION_BASE_URL`, `IKS_FUSION_USERNAME`, `IKS_FUSION_PASSWORD` are set.

### 1. Find suppliers with "Lee" in name
```bash
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?q=Supplier+LIKE+%27%25Lee%25%27&fields=SupplierId,SupplierNumber,Supplier,Status&limit=25"
```

### 2. List all US suppliers (with addresses expanded)
```bash
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?expand=addresses&fields=SupplierId,SupplierNumber,Supplier,Status,addresses&limit=200"
```

### 3. Get all invoices for supplier number "1252"
```bash
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/invoices?q=SupplierNumber%3D%271252%27&fields=InvoiceId,InvoiceNumber,SupplierNumber,Supplier,InvoiceDate,InvoiceAmount,InvoiceCurrency,PaidStatus,ApprovalStatus&limit=200"
```

### 4. Get all POs for supplier_id 300000047572113
```bash
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/purchaseOrders?q=SupplierId%3D300000047572113&fields=POHeaderId,OrderNumber,SupplierId,Supplier,StatusCode,BuyerId,Buyer,ApprovedDate,Ordered,Total&limit=200"
```

### 5. Look up buyer with PersonId 300000047340498
```bash
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/hcmRestApi/resources/11.13.18.05/publicWorkers?q=PersonId%3D300000047340498&fields=PersonId,PersonNumber,DisplayName,WorkEmail,Username&limit=1"
```

### 6 Date-range queries on /invoices (workaround)

Fusion's q= clause supports `>=` and `<` separately but not compounded
(see Composite-q quirk above). To get records in a date range, send the
lower bound via q= and filter the upper bound client-side.

curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  --get \
  --data-urlencode "q=InvoiceDate >= '2022-01-01'" \
  --data-urlencode "fields=InvoiceDate" \
  --data-urlencode "limit=500" \
  --data-urlencode "onlyData=true" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/invoices"

Verified 2026-05-30: For Jan 2022 query, first 500 records span
2022-01-01 to 2022-03-14, so client-side filtering for Jan 2022 is
complete (212 records). At higher invoice volumes, this pattern may
need overfetch tuning or pagination.

---

## Notes for the KG experiment

When you build the property graph:

1. **Vertex tables encode entity *types*** — `Supplier`, `Invoice`, `PurchaseOrder`, `Buyer`, `Address`. Five rows total (one per type). Each row records the endpoint path, the canonical ID field, and the field projection list.

2. **Edge tables encode *declarations*** — `HAS_INVOICE`, `HAS_ADDRESS`, `HAS_PURCHASE_ORDER`, `ASSIGNED_TO`. Each row records:
   - From-entity and to-entity
   - **From-join-field and to-join-field** (this is where the SupplierNumber/SupplierId asymmetry lives)
   - The Fusion API path for the join

3. **Pattern templates encode reusable query shapes** — v1 patterns are `status_filter` (e.g., "open POs") and `country_filter_via_address` (e.g., "suppliers in US"). The `no_Y_in_N_months` (absence) and `cross_pillar_lookup` patterns were dropped from v1 scope; the latter because `ASSIGNED_TO` already encodes the only cross-pillar case.

4. **Vocabulary handles term-to-canonical translation** — `"US"` → `"US"`, `"United States"` → `"US"`, `"open"` → `"OPEN"`, `"active"` → `"OPEN"`, etc.

The PGQ executor's job: take structured input (e.g., `{entity: "Supplier", filters: [country=US, has_open_po=true]}`) and produce the sequence of endpoint calls listed above.

---

## What's NOT covered here

This doc covers only the endpoints Spire's existing 5 tools use. Other Fusion endpoints exist for the same domain:
- `/suppliers/{id}/child/addresses` — addresses as separate resource (Spire uses `expand=` instead)
- `/suppliers/{id}/child/sites` — supplier site records
- `/items` — items catalog
- `/orders` — sales orders (separate from purchase orders)
- `/journals`, `/ledgers` — financials

If the KG experiment needs any of these, you'll be building net-new tool integrations.

---

## 6. Supplier filter experiments (KG expansion session)

**Note on credentials.** All curls in this document use the three shell
variables `$IKS_FUSION_BASE_URL`, `$IKS_FUSION_USERNAME`,
`$IKS_FUSION_PASSWORD` (set in `.bashrc`). These are the only credential
variables used anywhere; no other names apply. The pod and
paths are unchanged.

These experiments confirmed how each new supplier/invoice/address filter
behaves server-side vs client-side. All against `/suppliers`,
`/invoices`, and the `addresses` child on pod `esll-dev37`.

### 6.1 Supplier status — server-side unreliable, use client-side

`q=Status='INACTIVE'` and `q=Status <> 'ACTIVE'` both returned **0 rows**
even though INACTIVE suppliers exist. `q=InactiveDate IS NOT NULL`
**worked** and surfaced them.

Conclusion: do not filter Status server-side on this pod. Over-fetch and
match `Status` client-side. Definition is **Status-based**: active =
`Status='ACTIVE'`, inactive = `Status='INACTIVE'`. Not InactiveDate-based
— some ACTIVE suppliers carry a future InactiveDate (e.g. 2026-12-31).

```bash
# Worked (found inactive suppliers via a different field):
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" --get \
  --data-urlencode "q=InactiveDate IS NOT NULL" \
  --data-urlencode "fields=SupplierNumber,Supplier,Status,InactiveDate" \
  --data-urlencode "limit=20" --data-urlencode "onlyData=true" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers"
```

### 6.2 Supplier name fragment — server-side works

`q=Supplier LIKE '%Lee%'` **worked** (single clause). Two "Lee" suppliers
returned. This is the reliable server-side path for name search.

### 6.3 Supplier creation-date range — lower bound server, upper client

- `q=CreationDate >= '2022-01-01'` **worked**.
- `q=CreationDate < '2023-01-01'` **worked** on its own.
- Composite `q=CreationDate >= 'x' AND CreationDate < 'y'` returned
  **0 rows** (composite-q quirk again).

Conclusion: send the lower bound via `q=`; apply the upper bound
client-side. CreationDate is a full timestamp
(`2022-05-03T15:33:00.240+00:00`); date-only comparison values work.

### 6.4 Supplier business relationship — server-side works, Spire applies client-side

Supplier records carry `BusinessRelationshipCode` / `BusinessRelationship`.
The pod has exactly two values, confirmed across 500 rows:
`Spend Authorized` (372) and `Prospective` (40). These are the **display
strings** returned by `BusinessRelationship`; the paired
`BusinessRelationshipCode` field holds the underscored codes
(`SPEND_AUTHORIZED`, `PROSPECTIVE`).

Server-side filterability: **tested and works.**
`q=BusinessRelationship='Spend Authorized'` returned `totalResults: 372`
— unlike `Status`, this field is reliable via `q=`.

Spire nevertheless applies this filter **client-side**, matching the
display string with equals (canonical value = the literal pod string,
e.g. `Spend Authorized`). Rationale: only one server `q=` clause is
reliable per call (composite `q=` fails on this pod), so keeping the
filter client-side lets it combine freely with name-fragment and
created-date without competing for the single server slot. Same shape as
Status. Built as Phase 8.

### 6.5 Invoice amount — client-side

No amount `q=` clause was needed. `InvoiceAmount` is in the projected
fields; Spire filters `amount_min` / `amount_max` client-side. Verified
via the tool: min-only, min+max range, all correct.

### 6.6 Invoice date range — lower bound server, upper client

Same pattern as creation-date. `invoice_date_after` maps to a server
`q=InvoiceDate >= 'x'`; `invoice_date_before` is client-side. Verified a
2023-only window returns only 2023 invoices.

### 6.7 Invoice by supplier — required

`q=SupplierNumber='1252'` **worked**. Invoice queries require a supplier
(number or name); with none, Spire refuses rather than pull every
invoice. Note: some suppliers legitimately have **0 invoices** (e.g.
Sun Pvt Ltd / VX_11 returned empty by both name and number) — an empty
result is not a bug.

### 6.8 Addresses via expand — flatten the child

`/suppliers?q=SupplierNumber='1252'&expand=addresses` **worked** and
returned an `addresses` array per supplier. Real child field names:
`SupplierAddressId`, `AddressName`, `CountryCode`, `Country`,
`AddressLine1`, `City`, `State`, `PostalCode`, `County`,
`FormattedAddress`, `Status`. Note the id is **SupplierAddressId**, not
AddressId.

Country lives on the address child, so country filtering is client-side
against `CountryCode` / `Country`. Address queries require a supplier or
a country (bounded fetch).

```bash
# Worked (addresses child, flattened by the Spire tool):
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" --get \
  --data-urlencode "q=SupplierNumber='1252'" \
  --data-urlencode "expand=addresses" \
  --data-urlencode "onlyData=true" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers"
```

### 6.9 Summary of filter classifications

| Filter | Endpoint | Server-side `q=`? | How Spire applies it |
|---|---|---|---|
| name fragment | /suppliers | Yes (LIKE) | server |
| status | /suppliers | No (unreliable) | client-side on Status |
| created-date lower | /suppliers | Yes (>=) | server |
| created-date upper | /suppliers | No (composite fails) | client-side |
| business relationship | /suppliers | Yes (=), tested | client-side by choice (keeps it combinable) |
| country | /suppliers (expand) | No (on child) | client-side |
| invoice amount | /invoices | No | client-side |
| invoice-date lower | /invoices | Yes (>=) | server |
| invoice-date upper | /invoices | No | client-side |
| invoice by supplier | /invoices | Yes (=) | server |
| address by supplier | /suppliers (expand) | Yes (supplier q=) | server + flatten |
| address by country | /suppliers (expand) | No | client-side on child |
| site business unit | /suppliers/{id}/child/sites | Yes (=), tested | server on the child (per-supplier edge walk) |
| classification | /suppliers/{id}/child/businessClassifications | Yes (=), tested | server on the child (per-supplier edge walk) |

### 6.10 Supplier child endpoints (curled 2026-07-09)

Both child endpoints named in the SME feedback have now been discovered
live. Both filter by a single-clause server-side `q=` on the child, and
both are consumed by a per-supplier edge walk (keep the parent supplier
when the filtered child call returns something). Neither child body
carries `SupplierId` — the join key is the URL path.

#### `/suppliers/{SupplierId}/child/sites` (Test 2 / Phase 12)

Fields: `SupplierSiteId`, `SupplierSite`, `ProcurementBU` (display,
e.g. `"US1 Business Unit"`), `ProcurementBUId` (numeric), plus `Status`,
`Address`, and many purchasing/invoicing config flags.

Filter: `q=ProcurementBU='<display>'` — reliable server-side (verified
positive and negative). Example:

```bash
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" --get \
  --data-urlencode "onlyData=true" \
  --data-urlencode "fields=SupplierSiteId,SupplierSite,ProcurementBU,ProcurementBUId" \
  --data-urlencode "q=ProcurementBU='US1 Business Unit'" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers/300000047414503/child/sites"
```

Caveat: **`expand=sites` on the bulk supplier fetch is silently dropped**
(HTTP 200, no `sites` key), so sites are only reachable per-supplier via
this child path — one child call per parent supplier.

#### `/suppliers/{SupplierId}/child/businessClassifications` (Test 17 / Phase 13)

Fields: `ClassificationId`, `Classification` (display, e.g.
`"Small Business"`), `ClassificationCode` (`"SMALL_BUSINESS"`), `Status`
(`"CURRENT"`), `CertifyingAgency` (`"SBA"`), plus certificate
number/dates, notes, and provided-by contact fields (mostly null on the
demo pod).

Filter: `q=Classification='<display>'` — reliable server-side (verified
positive and negative). Example:

```bash
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" --get \
  --data-urlencode "onlyData=true" \
  --data-urlencode "fields=ClassificationId,Classification,ClassificationCode,Status" \
  --data-urlencode "q=Classification='Small Business'" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers/300000047414503/child/businessClassifications"
```

Distinct `Classification` values seen across the first 50 suppliers:
Hub Zone (6), Workers' Compensation Insurance (4), General Liability
Insurance (4), Woman Owned (3), Small Business (3), ISO 14001 (3),
Veteran Owned (2), Minority Owned (1), Kbis (1).

Caveat: a `Status='CURRENT'` condition **cannot** be AND-combined with
`Classification` in one `q=` (composite quirk — returns empty). Send
`Classification` as the single server clause; if "current only" is ever
required, filter `Status` client-side.

Note: `expand=businessClassifications` on the bulk fetch was not
separately tested; assume it behaves like `expand=sites` (silently
dropped) until proven otherwise.

---

## 7. PO child hierarchy and related endpoints (P2–P5)

The PO detail hierarchy is PO -> lines -> schedules -> distributions, but
the three levels behave very differently. Read this before adding tools.

### `/purchaseOrders/{POHeaderId}` — single PO header

Returns ONE record (HTTP 200), ~90 attributes — not a collection.
**404s for an unknown id** (the collection returns empty items instead).

```bash
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" --get \
  --data-urlencode "onlyData=true" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/purchaseOrders/2144"
```

Fields Spire registers: `POHeaderId`, `OrderNumber`, `Status`/`StatusCode`,
`Supplier`/`SupplierId`, `SupplierSite`, `SupplierContact`, `Buyer`/`BuyerId`,
`Ordered`, `Total`, `TotalTax`, `CurrencyCode`, `PaymentTerms`,
`ShipToLocationCode`, `BillToLocation`, `OrderDate`, `Description`.

### `/purchaseOrders/{POHeaderId}/child/lines` — PO lines

Nested child. **The line body carries BOTH `POHeaderId` and `OrderNumber`** —
the join key is IN the body, unlike the supplier children which omit it.

Fields: `POLineId`, `LineNumber` (= "Line"), `LineType`, `Description`,
`Category`/`CategoryCode`, `Quantity`, `UOM`, `BasePrice`, `Price`,
`Ordered`, `TotalTax` (= "Tax"), `Total`, `Status`/`StatusCode`.

### `/purchaseOrderSchedules` — FLAT schedules collection

**Not a child** — a top-level collection, filterable server-side by a
single clause. This makes a PO's schedules a one-hop fetch.

```bash
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" --get \
  --data-urlencode "onlyData=true" \
  --data-urlencode "q=POHeaderId=2144" \
  --data-urlencode "fields=POHeaderId,POLineId,LineLocationId,ScheduleNumber,ShipToLocation,RequestedDeliveryDate,Quantity,Amount,ScheduleStatus,ReceivedQuantity,BilledQuantity,ReceivedAmount,BilledAmount" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/purchaseOrderSchedules"
```

**Flat names differ from the nested `/child/schedules` view:**
`ScheduleStatus` (not Status), `Amount` (not Ordered), `ShipToLocation`
(not ShipToLocationCode).

**`POLineId` is NOT in the default projection** — you must name it in
`fields=`. It matters: the distributions path needs it.

**Received-vs-ordered lives here**: `ReceivedQuantity`, `BilledQuantity`,
`ShippedQuantity`, `AcceptedQuantity`, `ReceivedAmount`, `BilledAmount`,
against ordered `Quantity`/`Amount`.

### Distributions — deep nested path ONLY

There is **no flat `/purchaseOrderDistributions`** (404), and the flat
schedules resource has **no distributions child** (404). The only route:

```bash
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" --get \
  --data-urlencode "onlyData=true" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/purchaseOrders/2144/child/lines/19782/child/schedules/18954/child/distributions"
```

Needs THREE ids: POHeaderId, POLineId, LineLocationId — all carried on the
parent flat-schedule row. Spire therefore iterates a PO's schedules and
passes all three per row (this is what drove the executor's multi-field
iteration).

Fields: `PODistributionId`, `DistributionNumber`, `POChargeAccount`,
`POAccrualAccount`, `POVarianceAccount`, `DeliverToLocationCode`,
`Percentage`, `Quantity`, `Ordered`, `Total`, `Status`/`StatusCode`.

### `/suppliers/{SupplierId}/child/contacts` — supplier contacts

Same shape as sites/classifications: per-supplier child call, body does NOT
carry SupplierId (join key is the URL path).

Fields: `SupplierContactId`, `ContactName` (last-first, e.g. "Kim, John"),
`FirstName`, `LastName`, `Email`, `JobTitle` (null on this pod), `Status`,
`AdministrativeContactFlag` (marks the primary contact).

### Receipts — all three routes unusable (as of 2026-07-17)

Recorded so nobody re-runs these curls:

| Resource | Result |
|---|---|
| `receivingTransactions` | **403** — needs a receiving role we don't have |
| `receivingReceipts` | **400** — requires ShipmentHeaderId or ReceiptNumber; cannot be queried by PO |
| `receivingReceiptRequests` | Staging/interface resource (HeaderInterfaceId, ProcessingStatusCode, submitForApproval). **No PO reference on the header.** |

Use `purchaseOrderSchedules` received/billed fields instead.

### `/invoices` — filtering by PO

`PurchaseOrderNumber` is on the invoice **header** and filters server-side:

```bash
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" --get \
  --data-urlencode "onlyData=true" \
  --data-urlencode "q=PurchaseOrderNumber='162034'" \
  --data-urlencode "fields=InvoiceId,InvoiceNumber,Supplier,PurchaseOrderNumber,InvoiceAmount" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/invoices"
```

The value is the PO **number** (OrderNumber), NOT POHeaderId. Many invoices
have it null — in fact MOST do on the demo pods (~1% PO-linked; see the
2026-07-19 discovery-log row). Not every PO has invoices (PO 162352 has none).

---

## 8. Join-key matrix — PO hierarchy additions

| To search this | Join key | Numeric or string? |
|---|---|---|
| `/purchaseOrders/{id}/child/lines` | `POHeaderId` (also in body) | numeric (e.g. `2144`) |
| `/purchaseOrderSchedules` | `POHeaderId` via `q=` | numeric |
| `.../child/distributions` | POHeaderId + POLineId + LineLocationId (all three, from the schedule row) | numeric |
| `/suppliers/{id}/child/contacts` | `SupplierId` (URL path only) | numeric |
| `/invoices` by PO | `PurchaseOrderNumber` | **string** (e.g. `"162034"`) — NOT POHeaderId |

## 9. AR endpoints (receivables) — P1 discovery (curled 2026-07-19)

The AR pillar's read surface. All under `/fscmRestApi/resources/11.13.18.05/`
except the CRM account object (ruled out — see below). Captured live against
pod `fa-esll-dev37`; the source catalog's endpoint and column names were
partly wrong, so these supersede it.

### `/receivablesInvoices` — AR invoice header

173,531 rows. Canonical id `CustomerTransactionId` (NOT "InvoiceId"), human
number `TransactionNumber`. Key fields:

- Amounts: `EnteredAmount` (invoice amount), `InvoiceBalanceAmount` (open
  balance; 0 = paid)
- Customer: `BillToCustomerName`, `BillToCustomerNumber`, `BillToPartyId`,
  plus ShipTo/PayingCustomer variants
- Currency: `InvoiceCurrencyCode`
- Dates: `TransactionDate`, `DueDate`, `AccountingDate`, `CreationDate`,
  `LastUpdateDate`
- Status/type: `InvoiceStatus` (display, e.g. "Complete"), `TransactionType`,
  `TransactionSource`, `BusinessUnit`

Children: `receivablesInvoiceLines`, `receivablesInvoiceInstallments`,
`receivablesInvoiceDistributions`, `receivablesInvoiceDFF`,
`receivablesInvoiceTransactionDFF` (TWO DFF children — see quirk 8),
`attachments`, `notes`, `receivablesInvoiceGdf`.
Actions (WRITES, out of read scope): `approve`, `rework`, `splitInstallments`.

Test anchor: `CustomerTransactionId=300000248096352` → TransactionNumber
61765, BillToCustomerName "ABC Corporation Americas", Santa Clara, UK Business
Unit, GBP 39,969, InvoiceStatus Complete.

### `/receivablesInvoices/{id}/child/receivablesInvoiceLines` — invoice lines

Fields: `CustomerTransactionLineId` (PK), `LineNumber`, `Description`,
`Quantity`, `UnitSellingPrice`, `LineAmount`, `UnitOfMeasure`, `ItemNumber`,
`TaxClassificationCode`, `TaxExemptionHandling`, `LineAmountIncludesTax`,
`AssessableValue`.

**`TransacationBusinessCategory` is misspelled by Oracle** ("Transacation",
missing an 's') — the field name must match the typo exactly or it won't
resolve in `?fields=`.

Line children: `receivablesInvoiceLineTaxLines` (the tax lines — a GRANDCHILD
of the invoice, reached three levels deep: invoice → line → taxLines),
`receivablesInvoiceLineDFF`, `receivablesInvoiceLineTransactionDFF`.

### `/receivablesInvoices/{txnId}/child/receivablesInvoiceLines/{lineId}/child/receivablesInvoiceLineTaxLines` — AR tax lines (prompt 3)

The tax lines for an invoice line — a grandchild of the invoice, reached
three levels deep but keyed by only TWO ids: the invoice
`CustomerTransactionId` and the parent line `CustomerTransactionLineId`, both
in the URL path.

**Contrast with PO distributions.** Distributions need THREE ids (POHeaderId,
POLineId, LineLocationId) taken from one flat schedule row, which is why they
use the HAS_DISTRIBUTION `iter_fields` multi-field iteration. Tax lines do NOT:
the only id needed beyond the invoice is the line id, and the parent line row
already carries it. So tax lines are a PLAIN nested grandchild — fetched by
chaining two ordinary single-parent iterations (invoice → lines, then each
line → its tax lines), reusing the existing executor iteration. No new
multi-field branch.

Fields: `TaxLineNumber`, `TaxJurisdictionCode`, `TaxRate`, `TaxRateCode`,
`TaxRegimeCode`, `TaxStatusCode`, `Tax` (the tax type — e.g. "COUNTY"),
`TaxAmount`, `TaxableAmount`, `TaxInclusiveIndicator`, `TaxPointDate`, plus
`Created`/`LastUpdate` audit columns.

CAUTION: the tax-line row's own `CustomerTransactionLineId` is the TAX line's
PK (e.g. 112), a DIFFERENT value from the parent invoice-line id (74). Don't
confuse the two when joining or displaying.

Untaxed lines return `count:0`, not a 404 — the original anchor invoice 61765
("Consultation") is untaxed. Taxed anchor: invoice `1002` (TransactionNumber
5), line `74` → 2 tax lines; lines 84/93/107 also carry 2 each.

### `/standardReceipts` — AR cash receipts

37,335 rows. Carries every column the three AR aggregates need.

- Core: `StandardReceiptId` (PK), `ReceiptNumber`, `Amount`, `Currency`,
  `ReceiptDate`, `State` ("Applied"), `Status` ("Cleared"),
  `UnappliedAmount`, `AccountedAmount`
- `ReceiptMethod` (display, e.g. "Lockbox") — the field prompt 17 buckets by
- Customer: `CustomerName`, `CustomerAccountNumber`, `CustomerSite`
- Bank: `RemittanceBankName`, `RemittanceBankBranch`,
  `RemittanceBankAccountNumber`, `RemittanceBankDepositDate`
- Dates: `CreationDate` + `LastUpdateDate` (prompt 18 lag), `AccountingDate`,
  `MaturityDate`; `ReceiptBatchName`, `ReceiptBatchDate`

Action (WRITE): `applyReceipt`. Children: `remittanceReferences`,
`standardReceiptDFF`, `standardReceiptGdf`.

CAUTION: demo data is backfilled — `ReceiptDate` (e.g. 2012) can predate
`CreationDate` (e.g. 2014); `LastUpdatedBy` seen as "0". The lag calc (18)
still works, but the timestamps look odd.

**Confirmed working (2026-07-22, AR-P5 discovery).** This collection is HEALTHY
— an earlier read of it as "dead" was a misdiagnosis of quirk-7 projection 500s.
- `q=CustomerAccountNumber=26360` filters server-side → `totalResults: 1386`.
- `totalResults=true` alone works → 37,337 rows (up from the 37,335 recorded
  2026-07-19; the pod's data moves).
- **`fields=` is UNUSABLE here — it 500s even with all-valid field names.**
  Not just quirk 7's invalid-name case: a projection naming only fields
  confirmed present in a live response still 500s when combined with `q=`.
  Drop `fields=` first when diagnosing any 500 on this endpoint, and fetch
  full rows in tools, discarding fields client-side.
- **Composite `q=` fails SILENTLY** — HTTP 200, `totalResults: 0`, no error.
  See the discovery-log row; this drives prompt 13's design.
- **No default ordering** — two identical unordered calls returned different
  first rows (StandardReceiptId 117, then 11350). Always pass `orderBy` if the
  result must be reproducible.

**Prompt 13 (site-filtered receipts) — the CONFIRMED path.** `CustomerSite` IS
populated, IS queryable on this top-level collection, and DOES discriminate
(unlike within a single account): sampled values include "Santa Clara",
"San Francisco" (ABC Corporation Worldwide, acct 25750) and null (Department of
Education, acct 60800). The Santa Clara anchor the plan asked us to confirm
EXISTS — 1,735 receipts carry it.

**But site alone is NOT customer-scoped, and the two clauses cannot be
combined.** "Santa Clara" spans at least accounts 26360 (ABC Application
Software) and 26370 (ABC Corporation Americas) — verified by sorting
`orderBy=CustomerAccountNumber` ascending then descending against the same
site filter. And composite `q=` returns a SILENT ZERO here (see the
discovery-log row), so `CustomerSite AND CustomerAccountNumber` cannot be
asked of the server.

Design: `q=CustomerAccountNumber=<n>` server-side (1,386 rows for our anchor —
the more selective clause), then match `CustomerSite` client-side, handling
nulls. Do NOT project with `fields=` — it 500s on this endpoint even with
valid names.

**The ABC-entity trap is real and confirmed, with numbers.** THREE different
customers match a naive "ABC" search, two of them at the SAME site:
- "ABC Application Software" — acct 26360, Santa Clara (AR-P5 anchor)
- "ABC Corporation Americas" — acct 26370, Santa Clara (AR-P2b anchor)
- "ABC Corporation Worldwide" — acct 25750, San Francisco

So neither the customer name fragment NOR the site is sufficient alone.
Resolve to an `AccountNumber`/`AccountId` before trusting any customer-scoped
receipt result.

### `/receivablesCustomerAccountActivities` — AR customer / balance view

**This is Spire's customer entity for AR.** Only 435 rows (≈ the
customer-account count — so the exposure ranking in prompt 10 is cheap).

Fields: `AccountId` (PK), `AccountNumber`, `CustomerName`, `CustomerId`,
`TotalOpenReceivablesForAccount` (prompt 10 exposure sort key),
`TotalTransactionsDueForAccount`, `CreationDate`, `LastUpdateDate`.

Children (the account-scoped prompts all hang here, keyed by `AccountId` in
the URL path):
- `creditMemos` — prompt 7 (credit memos for an account)
- `standardReceipts` — prompt 8 (standard receipts for an account)
- `standardReceiptApplications` — prompt 9 (receipt applications)
- `creditMemoApplications`, `transactionAdjustments`,
  `transactionPaymentSchedules`, `transactionsPaidByOtherCustomers`

Test anchor: `AccountId=300000047368512` → AccountNumber 26360, CustomerName
"ABC Application Software", TaxpayerIdentificationNumber "88-5694712".

**The balance fields DRIFT — never hard-code them in a test.**
`TotalOpenReceivablesForAccount` read 680,271.11 on 2026-07-19 and 678,923.69
on 2026-07-22 for the same account; `TotalTransactionsDueForAccount` was
699,039.33 on 2026-07-22. Assert on presence and type, not value.

**Prompt 6 (activity/balance summary) needs NO child fetch** — the balance
fields sit on the account record itself, so prompt 6 is the simplest of the
AR-P5 five: resolve the account by `CustomerName` (as in AR-P2b) and read the
record.

NOTE: standard receipts are reachable BOTH here (per-account child) and as the
top-level `/standardReceipts` collection. **The two do NOT agree** — the child
reports 1,559 rows for this account while the top-level filtered by
`q=CustomerAccountNumber=26360` reports 1,386. See the 2026-07-22 discovery-log
row; treat this as an open question.

**Per-account child row counts on this anchor (2026-07-22):** `creditMemos`
280, `standardReceipts` 1,559, `standardReceiptApplications` 15,636. All three
need `orderBy` + a hard `limit`; none can be fetched whole. Every one of these
children is fetched by `AccountId` in the URL PATH and **none echoes `AccountId`
in the row body** — the established AR child pattern.

**AR-P5 introduces FOUR distinct id spaces.** Do not conflate them, and give
each its own fully-qualified named set in the synthesizer:
`CreditMemoId` (account creditMemos child, small int) ·
`StandardReceiptId` (receipts, MIXED width — small for backfilled rows, large
for recent) · `ApplicationId` (receipt applications) ·
`ReferenceTransactionId` (small int, the `transactionPaymentSchedules` space —
NOT `/receivablesInvoices`' `CustomerTransactionId`).

### `/receivablesCreditMemos` — AR credit memos

2,111 rows. **Same object model as `/receivablesInvoices`** — same
`CustomerTransactionId`, `TransactionNumber`, `BillToCustomerName`/`Number`,
same child set, same `approve`/`rework` actions. Both are
`receivablesTransactions` split by `TransactionType`. Distinct: `EnteredAmount`
is NEGATIVE (e.g. -408.90), `CreditMemoStatus`, `TransactionBalanceDue`,
`CreditReason`.

**AR-P4 (curled 2026-07-21, merged as `ar-p4-credit-memos`).** Confirmed
server-side: `orderBy=TransactionDate:desc` WORKS (newest-first), `limit=N`
gives a clean top-N, and `fields=` projection works — so "list recent credit
memos" is a pure server-side top-N, no client sort. Projected the 8 fields
Spire uses: `CustomerTransactionId`, `TransactionNumber`, `TransactionDate`,
`EnteredAmount`, `CreditMemoCurrency`, `CreditMemoStatus`,
`BillToCustomerName`, `BillToCustomerNumber`. Modeled as a rooted, LIST-ONLY
entity `CreditMemo` (top-level, no parent id, no by-id, no edge).

**Sign is NOT guaranteed.** EnteredAmount is *normally* negative, but the pod
has at least one POSITIVE, Incomplete memo (TransactionNumber 1001, +10000,
"Digital Customer 1"). So `total_credit` (Spire's raw sum of EnteredAmount) is
a ledger NET figure — the +10000 offsets the negatives (recent-25 total
= -17232.52). Never assume EnteredAmount < 0, and note the raw sum mixes
currencies (USD/CAD/GBP/EUR) — fine for the demo, not a real multi-currency
total. Newest anchor: TransactionNumber 11001 (DMART, -150, 2026-07-09).

### `/receivablesCustomers` — DOES NOT EXIST (404)

The name in the AR source catalog is wrong; there is no such resource. For AR
customer identity and balances, use `/receivablesCustomerAccountActivities`.
Do not attempt to model a customer entity from `/receivablesCustomers`.

### `crmRestApi /accounts` — CRM/Sales customer, NOT the AR master

Exists (1,476 rows) but is the sales-and-marketing account view, ruled out for
AR. Keys on `PartyId` / `PartyNumber` — a DIFFERENT id space from AR's
`CustomerId` / `AccountNumber` (verified: sample keyed on PartyId
100000220363437 / PartyNumber 571206, "Astil Electronique", a French sales
prospect — unrelated to the ABC receivables customers). Carries opportunities,
territories, `AccountScore`, DUNS — not receivables. The collection action
`getFinancialCustomerInfo` is the documented sales→financial bridge, if a
future cross-pillar prompt ever needs to join sales to AR.

### `/receivablesCustomerAccountActivities/{AccountId}/child/transactionPaymentSchedules` — a customer's transactions (AR-P2b)

The child that lists an account's transactions (payment schedules /
installments). This is the customer-invoice-listing path (prompt 15): after
resolving a customer to their `AccountId` via `q=CustomerName=`, traverse
here. Fields: `TransactionId` (PK — a SMALL int, distinct id-space from the
invoice endpoint's `CustomerTransactionId`), `TransactionNumber`,
`TransactionClass` (e.g. "Invoice" — NOT queryable, filter client-side),
`TransactionDate`, `PaymentScheduleDueDate`, `TotalOriginalAmount`,
`TotalBalanceAmount` (0 = paid; > 0 = open — the basis for the deferred
open-invoices filter), `InstallmentStatus` (e.g. "Closed"). One account can
carry thousands of rows (the ABC Corporation Americas account has 7,404), so
client-side filtering must over-fetch. The collection holds multiple
transaction classes; keep `TransactionClass == 'Invoice'` for invoice
listings.

Test anchor: `CustomerName='ABC Corporation Americas'` → one account,
`AccountId=300000047368527`, `AccountNumber=26370`, with 25 Invoice-class
transactions.

### Join-key matrix — AR additions

| To search this | Join key | Numeric or string? |
|---|---|---|
| `/receivablesInvoices` (by customer) | — NOT queryable — | Customer name/number are not server-filterable here (AR-P2b). Use the account path below. |
| `/receivablesCustomerAccountActivities` (resolve customer) | `CustomerName` | string, exact — the customer-scoped resolve point (AR-P2b) |
| `transactionPaymentSchedules` (a customer's invoices) | `AccountId` (URL path) | numeric — traverse from the resolved account |
| `/receivablesCreditMemos` (by customer) | `BillToCustomerNumber` | string (NOTE: not yet verified queryable — assume client-side like the invoice endpoint until confirmed) |
| `/standardReceipts` (by customer) | `CustomerAccountNumber` | string (e.g. "25750") |
| account children (memos/receipts/applications) | `AccountId` (URL path) | numeric — confirmed AR-P5; NONE of these children echo `AccountId` in the row body |
| `creditMemos` child (an account's memos) | `AccountId` (URL path) | numeric — row PK is `CreditMemoId` (small int), a DIFFERENT id space from `/receivablesCreditMemos`' `CustomerTransactionId` |
| `standardReceipts` child (an account's receipts) | `AccountId` (URL path) | numeric — row PK is `StandardReceiptId`, MIXED width (small for backfilled, large for recent) |
| `standardReceiptApplications` child (receipt ↔ transaction) | `AccountId` (URL path) | numeric — PRE-JOINED: carries `StandardReceiptId` AND `ReferenceTransactionId` on one row, so no second fetch is needed |
| `standardReceiptApplications` → a transaction | `ReferenceTransactionId` | numeric, SMALL — the `transactionPaymentSchedules` id space, NOT `/receivablesInvoices`' `CustomerTransactionId` |
| `/standardReceipts` (by site, prompt 13) | `CustomerAccountNumber` server-side, then `CustomerSite` client-side | string — `CustomerSite` is non-queryable on the child and unconfirmed on the top-level; also nullable |
| customer identity across AR objects | `CustomerId` / `AccountNumber` | numeric / string |

AR invoice and credit-memo detail fetch by `CustomerTransactionId` (numeric).
Invoice lines by the parent `CustomerTransactionId` in the path; tax lines need
invoice id + line id (deep nested, same pattern as PO distributions).

---

## 12. Verification session findings (2026-07-24)

Facts confirmed by curl during a full verification-and-fix session. Each
was checked against the pod before any code changed — the fixes that
stuck this session all started here, and the attempts that were reverted
all started from a theory instead.

### 12.1 `standardReceiptApplications` — status IS server-queryable

The account child at
`/receivablesCustomerAccountActivities/{AccountId}/child/standardReceiptApplications`
accepts `q=ApplicationStatus='...'` server-side. Confirmed live on
account 26360 (`AccountId=300000047368512`):

```bash
# Total, unfiltered
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" --compressed \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/receivablesCustomerAccountActivities/300000047368512/child/standardReceiptApplications?onlyData=true&totalResults=true&limit=5"
# -> totalResults 15636, hasMore true

# Applied only
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" --compressed \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/receivablesCustomerAccountActivities/300000047368512/child/standardReceiptApplications?q=ApplicationStatus='Applied'&orderBy=ApplicationDate:desc&onlyData=true&totalResults=true&limit=3"
# -> totalResults 7038

# Unapplied only
# -> totalResults 8598
```

**7,038 + 8,598 = 15,636.** The two statuses are exhaustive.

**Two consequences for tooling:**

1. No need to over-fetch and filter client-side. An earlier version
   pulled 500 raw rows and filtered in Python, which meant the reported
   "total" was the applied count WITHIN THAT PAGE — the answer stated
   "25 receipt applications" for an account with 7,038.
2. `orderBy=ApplicationDate:desc` IS honoured. **Without it this child
   returns OLDEST first** (2012 rows on this account), which is not what
   "recent applications" means.

**The unapplied rows are mostly reversals, not real unapplied cash.**
They carry `ReferenceTransactionNumber: null` — no transaction side at
all — and their amounts sign-mirror applied rows (`-2434.55` against
`+2434.55`, `-2208.30` against `+2208.30`). Including them makes any
total meaningless.

### 12.2 `/standardReceipts` — paging without `orderBy` is NOT stable

**This is an open issue, recorded here because it is a pod behaviour, not
a code bug.**

Two runs of the same receipt-method aggregation over account 26360, on
consecutive days, with identical code:

| | Run A | Run B |
|---|---|---|
| Total receipts | 1,386 | 1,386 |
| Total amount | 215,721,775.28 | 250,557,301.49 |
| Lockbox | 993 / 211,999,593.81 | 1,132 / 247,941,421.77 |
| Check (Directly/No Remit) | 393 / 3,722,181.47 | 254 / 2,615,879.72 |

Same row COUNT, and both splits sum correctly to 1,386 — but a 35M
difference in total. That is not reclassification; it is a **different
set of 1,386 rows**.

The endpoint has no documented default ordering. A paginated fetch that
walks `offset` without an `orderBy` can therefore see shifted or
overlapping pages between calls.

**Rule: any paginated fetch against `/standardReceipts` must specify a
deterministic `orderBy`.** Not yet confirmed by curl which sort keys are
accepted here — do that before relying on it.

### 12.3 Float precision — `TotalTransactionsDueForAccount`

Account 26370 returns `TotalTransactionsDueForAccount: 1179915.3225`.
Four decimal places, and the value does not terminate in IEEE-754: its
exact double representation is
`1179915.322500000120776891708374023437500`.

The synthesizer emitted that full expansion followed by trailing zeros
until it hit the output token cap (`finish_reason=MAX_TOKENS`,
`out=7983`). The summary line of the SAME response rendered it correctly
as `1179915.32`, so the problem is specific to structured-output float
emission.

**Sampling-dependent** — the same prompt succeeded at `out=3066` earlier
the same day and failed three times consecutively afterwards.

**Rounding at source was NOT sufficient.** With the tool returning
`1179915.32`, the model still emitted the unrounded expansion: it was
GENERATING those digits, not copying them. The fix required
post-processing the response after synthesis.

**Rule: monetary values from AR account endpoints carry more than two
decimal places and must be normalised. Do not assume currency values are
already 2dp.**

### 12.4 Anchor data confirmed

| Anchor | Value | Endpoint |
|---|---|---|
| Supplier 1252 (Lee Supplies) addresses | exactly 25, `hasMore: false` | `/suppliers?q=SupplierNumber='1252'&expand=addresses` |
| Supplier 1252 name-match | resolves to ONE supplier, `count: 1` | `/suppliers?q=SupplierNumber='1252'` |
| Account 26360 receipts | 1,386 | `/standardReceipts?q=CustomerAccountNumber='26360'` |
| Account 26360 applications | 15,636 (7,038 Applied) | account child |
| Account 26370 transactions | 25 shown; total unconfirmed | `transactionPaymentSchedules` child |
| AR invoice 1002 (TransactionNumber 5) | 4 lines, 8 tax lines (2 per line: STATE 6.5%, COUNTY 2.25%) | `/receivablesInvoices/1002` + children |
| Exposure ranking | 435 accounts; top Motique Gym (23129) at 165,428,563.24 | `/receivablesCustomerAccountActivities` |

Tax arithmetic on invoice 1002 verified line by line: line 1 taxable
10,592 → COUNTY 238.32 (2.25%) + STATE 688.48 (6.5%); line 3 taxable
210,470 → COUNTY 4,735.58 + STATE 13,680.55. All eight rows correct, and
each line's taxable amount equals its `LineAmount`.

### 12.5 Address labels are NOT supplier names

Worth recording because it caused a false bug report. Supplier 1252's
addresses carry `AddressName` values like `KFKA SUP`, `Lee DAVIDS`,
`Lee Supremo Energy US` — site nicknames on the supplier record, not
other suppliers. A result listing them under one supplier looks wrong at
a glance and is correct.

Confirmed by:

```bash
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" --compressed \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?q=SupplierNumber='1252'&expand=addresses&onlyData=true&fields=SupplierNumber,Supplier"
# -> count: 1, hasMore: false, one supplier: Lee Supplies
```

### 12.6 Method note

Five bugs this session were misdiagnosed at least once before a curl
settled them. In every case the wrong diagnosis came from reasoning about
symptom similarity — "this looks like the token-cap runaway we saw
before" — and the right one came from asking the pod.

Three specific traps:

- **A `totalResults` you did not request is not there.** Several
  "reported a sample as a total" bugs came from tools that never asked
  for `totalResults=true` and reported `len(items)` instead.
- **A round number is suspicious.** `500` receipts and `10000` purchase
  orders both turned out to be fetch caps presented as totals.
- **An identical count across two runs does not mean identical rows.**
  See 12.2.
