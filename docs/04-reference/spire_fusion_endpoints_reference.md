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
| 2026-07-28 | /purchaseOrderSchedules | **A FLAT top-level collection, and the only place all three PO reconciliation legs sit on one row.** Carries `Quantity`/`Amount` (ordered), `ReceivedQuantity`/`ReceivedAmount`, `BilledQuantity`/`BilledAmount`, plus `POHeaderId`, `OrderNumber`, `LineNumber`, `ScheduleNumber`, `ScheduleStatus`. **`q=OrderNumber='<n>'` filters server-side** — previously only `POHeaderId` was documented for this resource. Scannable with `limit`+`offset` for cross-PO discovery. |
| 2026-07-28 | /purchaseOrderSchedules | **`ReceivedAmount` is 0 or null on EVERY row on this pod** — checked across ~4,500 rows (offsets 0–4500). The received leg exists only as a QUANTITY. Any reconciliation reporting a received AMOUNT must DERIVE it: `Amount * (ReceivedQuantity / Quantity)`. This is not a guess — Oracle's own `BilledAmount` follows the same proration (see 13.2). Label derived figures; do not present them as fetched fields. |
| 2026-07-28 | /invoices | **`q=PurchaseOrderNumber='<n>'` filters server-side and works** — but the link is sparse. PO 162034 returns one Paid invoice of 830.01; PO 701337 returns ZERO despite its schedules recording 398.00 billed. A PO can carry `BilledAmount` with no invoice bearing its number, so an empty result is NOT proof that nothing was billed. |
| 2026-07-28 | /purchaseOrders | **`q=OrderNumber='<n>'` filters server-side.** Header carries `Ordered` (Oracle's own total, ex-tax), `Total` (inc-tax), `Supplier`, `SupplierSite`, `Buyer`/`BuyerDisplayName`, `CurrencyCode`, `PaymentTerms`, `ProcurementBU`, `Status`, `FundsStatus`, `PayOnReceiptFlag`. Header `Ordered` matched the sum of schedule `Amount` exactly on both test POs — use the header as authoritative and the schedule sum as a cross-check. |
| 2026-08-12 | /purchaseOrders | **`orderBy=OrderNumber:asc` sorts server-side** (confirmed for REC-2 sample-and-disclose). Rows return in lexical OrderNumber order — string field, so `"1"` precedes `"162026"`; not numeric, but stable and reproducible. **`totalResults=true` now returns 17,406** (up from the ~15,839 recorded 2026-07-19 — pod grew). A bounded ordered page (`limit=25`) is cheap and fast; the guard protects the unbounded full fetch, not one page. |
| 2026-09-24 | /purchaseOrders | **Composite `q=` on /purchaseOrders returns HTTP 400, NOT silent-zero.** `q=CreationDate >= '2023-01-01' AND CreationDate < '2024-01-01'` returns a 400. Different failure mode from F-012's `/invoices` falsifier (which returned 200 with `totalResults: 0`). Same family — composite `q=` unusable — but the loud mode means a mis-built composite fails visibly rather than producing a plausible empty result. |
| 2026-09-24 | /purchaseOrders | **The default physical scan order on this collection is NOT stable across query shapes.** `q=CreationDate >= '2023-01-01'&limit=200` (no projection, no orderBy) returned 200 rows beginning **2024-07-01** — outside the range's lower edge, and in a window entirely above the range under test. The same clause with `fields=OrderNumber,CreationDate` OR with `orderBy=CreationDate:asc` returned rows beginning **2023-01-11**. The default scan is not the same as sorting by any field, and cannot be relied on when a bounded range is being filtered client-side. |
| 2026-09-24 | /purchaseOrders | **`orderBy=CreationDate:asc` composes with `q=`.** Two identical calls with the same clause and the same `orderBy` returned identical rows starting 2023-01-11. This is the stable sort key for a date-bounded fetch on this collection. Contrast: `LastUpdateDate >= <cutoff>` does NOT need the orderBy — the pod's default scan for that field already starts at the range's lower edge (`q=LastUpdateDate >= '2026-06-23'&limit=200` returned rows beginning 2026-06-24, unchanged with `orderBy=LastUpdateDate:asc`). Sort key stability is therefore **field-specific, not collection-wide**; verify per field. |
| 2026-09-02 | /invoices | **`orderBy=InvoiceAmount:desc` works server-side — a TRUE top-N by amount.** Confirmed against supplier 1252 (Lee Supplies): `q=SupplierNumber='1252'&orderBy=InvoiceAmount:desc&limit=10` returns the actual 10 highest-amount invoices across all `totalResults=1316`, strictly descending (3944699.18, 1204500, 927000, ...), NOT a page slice. So "top N invoices by amount" is a real server-side top-N (same model as CreditMemo recent-first), not a client-side partial. `hasMore=true` and `totalResults` give the honest full count. Combine with `q=SupplierNumber` for per-supplier ranking. This is the capability the parser currently over-cautiously refuses. |
| 2026-07-29 | (AR list endpoints) | **`totalResults=true` works on `/receivablesCreditMemos` and both account children** (`creditMemos`, `standardReceipts`). Three tools were setting `total_available` to the RETURNED row count instead, so every capped result claimed to be complete. Requesting the pod's own count is the fix; fall back to the row count when the endpoint omits it. |
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

**Cheap inactive COUNT (2026-08-13).** Add `totalResults=true&limit=1` to the
same `q=InactiveDate IS NOT NULL` query to get the inactive total in one call
without over-fetching:

```bash
curl -s --compressed -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" --get \
  --data-urlencode "q=InactiveDate IS NOT NULL" \
  --data-urlencode "onlyData=true" --data-urlencode "limit=1" \
  --data-urlencode "totalResults=true" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers"
# → totalResults = 2 on 2026-08-13
```

Then `active = all − inactive`. On 2026-08-13 this gave 333 − 2 = 331, which
matched a full client-side `Status` count exactly (`{'ACTIVE': 331,
'INACTIVE': 2}`). **Caveat (from the definition above): some ACTIVE suppliers
can carry a FUTURE InactiveDate**, so on another pod `InactiveDate IS NOT NULL`
may over-count inactives and this subtraction would understate active — here the
two methods agreed, but when the number matters, cross-check with the
client-side `Status` count rather than trusting the subtraction alone.

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

**RESOLVED 2026-08-04 (sort key confirmed; see the end of this section).
Kept in full because the failure is the useful part.**

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
deterministic `orderBy`.**

**RESOLVED 2026-08-04 — the sort key is `StandardReceiptId`.** Confirmed
by curl, not inferred: page 1 at `limit=3` returned ids 1, 2, 3; page 2 at
`offset=3` returned 4, 21, 22. Contiguous across the page boundary and
ascending, so the parameter is APPLIED and not merely accepted (this pod
silently ignores `expand=sites` on bulk fetches, so "no error" is not
evidence on its own). Ids are not contiguous — the 4 → 21 gap is real
data, and ascending order is all pagination needs.

Use the PK, **not `ReceiptNumber`**: an ordered fetch on `ReceiptNumber`
returned two rows both numbered `"1"`, so it is not unique here and gives
no deterministic tiebreak — rows sharing a sort value can still swap
between calls.

`aggregate_standard_receipts_by_method` sends it on every page as of the
same date, and two full 37,338-row runs now produce byte-identical
output. Note `fields=` is still unusable on this endpoint (§7 above);
`orderBy` and `totalResults=true` are both fine.

**A second measurement, and a caution.** Ordering FIXES reproducibility
and can WORSEN representativeness. A PK-ascending fetch stopped by a page
cap returns the OLDEST rows, not an arbitrary sample. Measured pod-wide
at a 5,000-row cap:

| | Unordered (random 5,000) | Ordered (oldest 5,000) | Complete (37,338) |
|---|---|---|---|
| Methods seen | 4 | 3 | 22 |
| Lockbox | 4,754 | 4,998 | 18,661 |
| Check (Directly/No Remit) | 179 | **absent** | 18,480 |

Check is 49.5% of all receipts — within a percent of Lockbox by count —
and the ordered-but-capped answer reported it as not existing. So an
`orderBy` added to a capped fetch buys a repeatable answer that may be
more systematically wrong than the random one it replaced. **Add the
ordering and raise the cap together, or state the skew.**

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

---

## 13. PO lifecycle exploration (2026-07-28)

Curl discovery for the lifecycle PoC — "Has PO X been fully received,
fully invoiced, and fully paid?" Every finding below was observed against
the live pod before any code was written. Two test POs came out of it,
and one design decision (deriving the received amount) rests entirely on
13.2.

### 13.1 `/purchaseOrderSchedules` is flat, and carries all three legs

The reconciliation needs ordered, received and invoiced amounts. All
three sit on one schedule row, and the resource is a flat top-level
collection — no drilling through `purchaseOrders/{id}/child/lines/{id}/child/schedules`.

```bash
curl -sS --compressed -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" -G \
  --data-urlencode "fields=POHeaderId,OrderNumber,LineNumber,ScheduleNumber,Quantity,Amount,ReceivedQuantity,ReceivedAmount,BilledQuantity,BilledAmount,ScheduleStatus" \
  --data-urlencode "limit=500" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/purchaseOrderSchedules"
```

Deliberately no `q=` — composite clauses fail silently on this pod
(quirk 1) and an amount-comparison filter is unproven here, so the scan
over-fetches and filters client-side.

**`q=OrderNumber='<n>'` also filters server-side on this resource.** Only
`POHeaderId` was documented before; both work.

### 13.2 `ReceivedAmount` is empty on this pod — the received leg is a QUANTITY

Every row returned by the scan above had `ReceivedAmount: 0` while
`ReceivedQuantity` was populated. Checked across offsets 0–4500 (~4,500
rows): no exceptions.

So a received AMOUNT does not exist on this pod and must be derived:

```
received = Amount * (ReceivedQuantity / Quantity)
```

**Oracle's own arithmetic confirms the proration.** PO 701337 line 1:

```json
{ "Quantity": 4, "Amount": 1116,
  "ReceivedQuantity": 1, "ReceivedAmount": 0,
  "BilledQuantity": 1, "BilledAmount": 279 }
```

`1116 × ¼ = 279`, exactly the `BilledAmount` the pod reports for one unit
of four. The derivation matches how Fusion itself prorates a partial
line. Flag it as derived in any output — the underlying field is empty,
and a reader should know the number was computed.

### 13.3 Finding a PO with a partial chain

Most POs on this pod are fully closed — ordered, received and billed all
equal — which makes them useless as a reconciliation test: every
remaining is zero, so a correct answer and a broken one look identical.

Partials are found by scanning and filtering client-side:

```bash
for off in 500 1000 1500 2000 2500 3000 3500 4000; do
  curl -sS --compressed -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" -G \
    --data-urlencode "fields=POHeaderId,OrderNumber,Quantity,Amount,ReceivedQuantity,ReceivedAmount,BilledQuantity,BilledAmount,ScheduleStatus" \
    --data-urlencode "limit=500" \
    --data-urlencode "offset=$off" \
    "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/purchaseOrderSchedules" \
  | jq -c '.items[] | select(.BilledQuantity != .Quantity or .ReceivedQuantity != .Quantity or .BilledAmount != .Amount)'
done
```

### 13.4 Test PO 701337 — the partial chain

`POHeaderId=300000081255594`, supplier JGA, Status **Open**,
`FundsStatus: "Partially Liquidated"`, `PayOnReceiptFlag: true`.

```bash
curl -sS --compressed -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" -G \
  --data-urlencode "q=POHeaderId=300000081255594" \
  --data-urlencode "limit=100" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/purchaseOrderSchedules"
```

| Line | Qty | Amount | RecdQty | BilledQty | BilledAmt | Status |
|---|---|---|---|---|---|---|
| 1 | 4 | 1116 | 1 | 1 | 279 | Open |
| 2 | 1 | 119 | 1 | 1 | 119 | Closed |

Rollup: ordered **1235.00**, derived received **398.00** (2 of 5 units),
invoiced **398.00**, remaining to receive/invoice **837.00**. Header
`Ordered` is 1235.00 — matching the schedule sum exactly.

Useful because it mixes line statuses (one Open, one Closed) and forces
the header rollup to handle both.

### 13.5 The billed-but-uninvoiced gap

PO 701337's schedules record 398.00 billed, but no invoice carries its
number:

```bash
curl -sS --compressed -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" -G \
  --data-urlencode "q=PurchaseOrderNumber='701337'" \
  --data-urlencode "limit=50" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/invoices"
# -> "items": [], "count": 0
```

**Verified this is data, not a broken filter** — the same query against
PO 162034 returns a row (13.6). Concluding "no invoices exist" from a
single empty response would have been a theory; one extra curl made it a
fact.

`PayOnReceiptFlag: true` on this PO makes self-billing a plausible
explanation — pay-on-receipt invoices may not carry the PO number on the
header. **UNCONFIRMED.**

**Consequence for any lifecycle answer:** an empty invoice result is not
proof of an unpaid balance. It means the AP document could not be
matched, and the paid leg is unknown rather than zero.

### 13.6 Test PO 162034 — the complete chain, with an exception

```bash
curl -sS --compressed -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" -G \
  --data-urlencode "q=OrderNumber='162034'" \
  --data-urlencode "limit=100" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/purchaseOrderSchedules"
# -> 1 row: POHeaderId 1, Qty 2, Amount 758, RecdQty 2, BilledQty 2,
#    BilledAmount 758, ScheduleStatus "Closed"
```

```bash
curl -sS --compressed -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" -G \
  --data-urlencode "q=PurchaseOrderNumber='162034'" \
  --data-urlencode "limit=50" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/invoices"
# -> 1 invoice, 830.01, PaidStatus "Paid"
```

Fully matched on the PO side — but the invoice is **72.01 ABOVE** the
758.00 ordered. Probably tax; **unconfirmed**. Recorded because it is a
genuine exception case, and because `compare_orders_to_invoices` already
documents this same PO as its example of legitimate over-invoicing: tax,
freight and price variances all push an invoice above the order. Do not
treat invoiced > ordered as an error.

### 13.7 Together the two POs cover all four legs

| PO | Ordered | Received | Invoiced | Paid |
|---|---|---|---|---|
| 701337 | 1235.00 | partial (2 of 5 units) | 398.00 | none matched |
| 162034 | 758.00 | full | 758.00 | 830.01 ✓ |

Neither alone exercises everything. 701337 proves partial reconciliation
and mixed line statuses; 162034 proves the invoice join and carries the
over-invoice exception.

### 13.8 Method notes

**Two curls settled what a theory would have got wrong.** The empty
invoice result for 701337 read like a broken filter; checking a
known-good PO proved the filter works and the data is genuinely absent.
Without that, the design would have "fixed" a filter that was fine.

**A fully-closed PO is a weak test case.** Every remaining is zero, so a
correct reconciliation and a broken one produce the same output. Choose
anchors where the numbers disagree.

**Field names come from an unprojected fetch.** The PO header was
curled with no `fields=` specifically to see what it actually carries
under its real names — `Buyer` vs `BuyerDisplayName`, `Ordered` vs
`Total` — rather than guessing and debugging later.

---

## 14. PO lifecycle discovery — AP, holds and supplier setup (2026-07-29)

Extends section 13. Everything below was curled against `fa-esll-dev37`
on 2026-07-29 before any code was written, and backs Module 5 phases 3
and 4 (`lifecycle-phase-3-4-tool-layer`).

Two anchors throughout: **PO 701337** (JGA, Open, partially received, no
matched AP invoice) and **PO 162034** (Lee Supplies, Closed, settled).

### 14.0 Rows to add to the quirk table

Paste these into the dated quirk table at the top of this file.

| 2026-07-29 | /purchaseOrderSchedules, /invoices | **`totalResults=true` is honoured on both.** Re-verified under a single-clause `q=`: schedules for PO 701337 returned `totalResults: 2`, invoices for PO 162034 returned `totalResults: 1`, invoices for 701337 returned `totalResults: 0` on an empty set. Read it from the FIRST page — reading it from the last loses it entirely when a page cap is hit, which is the case the count is needed for. |
| 2026-07-29 | /invoices | **`AmountPaid` is on the invoice HEADER, and it is the only usable paid figure.** Summing `InvoiceAmount` gated on `PaidStatus == "Paid"` silently drops partial payments: a partly paid invoice is not in Paid status, so it contributes ZERO and a "partially paid" state can never be detected. Also on the header: `CanceledFlag` (exclude from totals — counting cancelled invoices inflates what appears owed), `ValidationStatus` ("Validated"), `ApprovalStatus` ("Not required"), `InvoiceDate`, `TermsDate`, `SupplierNumber`, `PaymentMethod`, `BankAccount`. |
| 2026-07-29 | /invoices/{id} | **Children are `appliedPrepayments`, `attachments`, `availablePrepayments`, `invoiceDff`, `invoiceGdf`, `invoiceInstallments`, `invoiceLines`. There is NO `holds` child and NO `payments` child.** Listing `.links[]` on the single-record fetch is the cheap way to settle "does resource X have child Y" instead of guessing paths. |
| 2026-07-29 | /invoices/{id}/child/invoiceInstallments | **This is where invoice HOLDS live** — not on the invoice header, which carries no hold field at all. Fields: `HoldFlag`, `HoldReason`, `HoldType`, `HeldBy`, `HoldDate`, plus `DueDate` (a real due date, not a derivation), `UnpaidAmount` (the pod's own remaining balance), `GrossAmount`, `InstallmentNumber`, `PaymentMethod`, `PaymentPriority`. `fields=` is accepted. One call per invoice — an N+1, so cap it. |
| 2026-07-29 | (AP payment documents) | **There is NO payment document anywhere on the AP path.** No payment number, no payment date, on either the invoice header or `invoiceInstallments`, and no payments child. What exists is payment STATUS (`PaidStatus`), AMOUNT (`AmountPaid`), METHOD (`PaymentMethod`, `BankAccount`) and DUE DATE. "Which payment settled this invoice" is unanswerable on this pod — this is an absence, not an undiscovered endpoint. |
| 2026-07-29 | /suppliers/{id} | **Fetch the supplier by ID, never by name+status.** `Supplier.Status` must be matched client-side on the collection (quirk documented earlier), but the PO header carries `SupplierId`, so a single-record fetch sidesteps the problem entirely. Setup fields: `Status` ("ACTIVE"), `InactiveDate`, `BusinessRelationship`/`BusinessRelationshipCode` ("SPEND_AUTHORIZED"), `SupplierNumber`, `OnOFACListFlag` (sanctions screening — **null, which is NOT False**), `UseWithholdingTaxFlag` + `WithholdingTaxGroup`, `ParentSupplier`, `TaxOrganizationType`. |
| 2026-07-29 | /suppliers/{id}?expand=sites | **`expand=sites` WORKS on a single-record supplier GET.** The existing quirk — that `expand=sites` is silently ignored — applies to BULK fetches only and should be read as such. It returned all 22 sites for JGA at ~100 fields each, so it is the wrong tool when one site is wanted. |
| 2026-07-29 | /suppliers/{id}/child/sites/{siteId} | **Returns the one site, and ACCEPTS `fields=`** (not a given — `/standardReceipts` 500s on `fields=`). This is the right path when the PO header already carries `SupplierSiteId`. Fields: `Status`, `InactiveDate`, `SitePurposePurchasingFlag`, `SitePurposePayFlag`, `MatchApprovalLevel` ("3 Way"), `InvoiceMatchOption` ("Receipt"), `PaymentTerms`, and FIVE hold fields — `HoldAllNewPurchasingDocumentsFlag`, `PurchasingHoldReason`, `HoldAllInvoicesFlag`, `HoldUnvalidatedInvoicesFlag`, `PaymentHoldDate`/`PaymentHoldReason`. |
| 2026-07-29 | /purchaseOrders | **Supplier-communication fields exist on the header** (prompt A.3): `RequiredAcknowledgment` ("None" on 701337, "Document" on 162034), `AcknowledgmentDueDate`, `AcknowledgeWithinDays`, `SupplierCommunicationMethod`, `PendingResponseRole`. **But there is NO approval date and no approver on the header** — only `Status` and `Revision`. A lifecycle timeline cannot show "approved on DATE" from this resource. |
| 2026-07-29 | /purchaseOrders | **`TotalTax` is 0 on PO 701337, and `FundsStatus` is null on the CLOSED PO 162034** (it is "Partially Liquidated" on the open one — closed POs release their reservation). The zero tax matters: it rules out PO-side tax as the explanation for 162034's 72.01 over-invoice, which section 13.6 had guessed. Also on the header: `Requisition` (the requisition number, so the requisition leg needs no extra call), `ShipToLocationCode`, `SupplierContactDisplayName`. |
| 2026-07-29 | (demo data age) | **Every date on this pod is 2013–2024.** PO 701337 was created 2014-08-12; invoice 162034inv is dated 2013-12-16 and fell due 2014-01-15. Any age or overdue figure computed against today is ~4,500 days and useless as a business signal. Compute overdue ONLY where an unpaid balance genuinely exists, so settled documents produce no absurd age — and treat any non-null value as a demo-data artefact. |

### 14.1 `totalResults` on the two lifecycle collections

```bash
# Schedules for PO 701337 — the D2 check and the D1 re-check in one call
curl -sS --compressed -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" -G \
  --data-urlencode "q=OrderNumber='701337'" \
  --data-urlencode "fields=LineNumber,ScheduleNumber,Quantity,Amount,ReceivedQuantity,ReceivedAmount,BilledQuantity,BilledAmount,ScheduleStatus" \
  --data-urlencode "onlyData=true" \
  --data-urlencode "totalResults=true" \
  --data-urlencode "limit=50" \
  ".../purchaseOrderSchedules"
# -> totalResults: 2
#    line 2: Qty 1, Amount 119,  RecdQty 1, RecdAmount 0, BilledAmount 119, Closed
#    line 1: Qty 4, Amount 1116, RecdQty 1, RecdAmount 0, BilledAmount 279, Open
```

Three things confirmed at once: `totalResults` is honoured; `ReceivedAmount`
is still 0 on every row (13.2 holds); and the derivation still reconciles —
1116 × ¼ + 119 × 1 = **398.00**, matching the billed sum exactly.

### 14.2 The empty invoice result is DATA, not a broken filter

```bash
# 701337 -> {"items": [], "totalResults": 0}
# 162034 -> {"items": [{...830.01, PaidStatus "Paid"...}], "totalResults": 1}
```

The control against 162034 is what makes the 701337 zero trustworthy. A
zero alone cannot distinguish "no data" from quirk 1's silent-composite
failure. **Run the control before believing an empty result.**

Consequence for reconciliation: a PO can carry `BilledAmount` on its
schedules with no AP invoice bearing its number, so the paid leg is
**unknown, not zero**. Reporting `remaining_to_pay = invoiced − paid`
asserts a debt that may not exist.

### 14.3 Asking the invoice what children it has

```bash
curl -sS --compressed -u "..." ".../invoices/300000049373131" \
  | jq -r '.links[] | "\(.rel)\t\(.name)"'
# child  appliedPrepayments      child  invoiceDff
# child  attachments             child  invoiceGdf
# child  availablePrepayments    child  invoiceInstallments
#                                child  invoiceLines
```

No `holds`, no `payments`. **This is the cheap way to settle a "does X
have child Y" question** — one call, and it replaces a series of guessed
paths that would each 404.

A caution against reading too fast: the absence of a `holds` child was
briefly taken to mean holds are unavailable. They are not — they are one
level down, on `invoiceInstallments` (14.4). An absent child rules out a
PATH, not a capability.

### 14.4 `invoiceInstallments` — holds, due dates, unpaid balance

```bash
curl -sS --compressed -u "..." \
  ".../invoices/300000049373131/child/invoiceInstallments?onlyData=true"
# InstallmentNumber 1   GrossAmount 830.01   UnpaidAmount 0
# DueDate 2014-01-15    HoldFlag false       HoldReason/HoldType/HeldBy null
# PaymentMethod Electronic   PaymentPriority 99   BankAccount XXX831252
```

Three finds:

- **`HoldFlag` and friends live here.** Nowhere else on the AP path.
- **`DueDate` is real**, and matches `TermsDate` + `Net 30` exactly
  (2013-12-16 + 30 = 2014-01-15). Use the field; drop the derivation.
- **`UnpaidAmount` is the pod's own remaining balance** per installment.

**But do not source money from here.** Installments are one call per
invoice — the only N+1 in a lifecycle assembly — and must therefore be
capped. Invoice headers are never capped. Rule adopted: **money from
headers, context from installments**, with `UnpaidAmount` used only as a
cross-check that lands in a note. A bitten cap then costs hold
visibility, never a number.

### 14.5 The PO header, unprojected

Beyond what 13.4 records:

| Field | 701337 | 162034 | Use |
|---|---|---|---|
| `RequiredAcknowledgment` | None | Document | A.3 communication status |
| `SupplierCommunicationMethod` | None | None | A.3 |
| `PendingResponseRole` | null | null | A.3 — ambiguous, see below |
| `TotalTax` | 0 | 0 | rules out PO-side tax |
| `FundsStatus` | Partially Liquidated | null | closed POs release |
| `Requisition` | 914032 | — | A.6 requisition leg, free |
| `SupplierId` | 300000047414635 | — | the setup join key |
| `SupplierSiteId` | 300000076246906 | — | the site join key |

**No approval date, no approver, anywhere on the header.** `Status` and
`Revision` are all there is. The "approved on DATE" line in the Shape C
mockup is not buildable from this resource.

**`PendingResponseRole: null` is ambiguous** — it may mean acknowledged,
or it may mean not tracked. Unconfirmed. Do not let a prompt turn it into
a claim.

### 14.6 Supplier setup, by ID

```bash
curl -sS --compressed -u "..." ".../suppliers/300000047414635"
# Status ACTIVE   BusinessRelationshipCode SPEND_AUTHORIZED
# SupplierNumber 1254   InactiveDate null   OnOFACListFlag null
# UseWithholdingTaxFlag true   WithholdingTaxGroup 1099-PRG-10-PCT
```

Fetching by ID sidesteps the documented `Supplier.Status` client-side
matching problem entirely: there is nothing to filter.

**`OnOFACListFlag: null` is not `False`.** Sanctions screening null means
"not screened", which is a different state from "screened clean". Treat
null as not-a-blocker, but do not report it as a clean screen.

**`UseWithholdingTaxFlag: true` with a 1099 group** is a legitimate
reason a payment can differ from an invoice — worth knowing before
diagnosing a variance.

### 14.7 `expand=sites` — narrowing an existing quirk

`expand=sites` **works on a single-record supplier GET** and returned all
22 JGA sites. The existing quirk that it is "silently ignored" is about
BULK fetches and should be read as scoped to those.

It is still the wrong tool when one site is wanted: 22 sites × ~100
fields for a lifecycle answer that needs one.

### 14.8 The site child path, by ID

```bash
curl -sS --compressed -u "..." -G \
  --data-urlencode "onlyData=true" \
  --data-urlencode "fields=SupplierSiteId,SupplierSite,ProcurementBU,Status,InactiveDate,SitePurposePurchasingFlag,SitePurposePayFlag,HoldAllNewPurchasingDocumentsFlag,PurchasingHoldReason,HoldAllInvoicesFlag,HoldUnvalidatedInvoicesFlag,PaymentHoldDate,PaymentHoldReason,MatchApprovalLevel,InvoiceMatchOption,PaymentTerms" \
  ".../suppliers/300000047414635/child/sites/300000076246906"
# Status ACTIVE   purchasing true   pay true
# MatchApprovalLevel "3 Way"   InvoiceMatchOption "Receipt"
# PaymentTerms "2/10 Net 30"   all five hold fields false/null
```

**`fields=` is accepted here** — worth verifying rather than assuming,
since `/standardReceipts` 500s on any projection.

Two things this gives that nothing else does:

- **Five site-level hold flags.** A site on payment hold or holding all
  new purchasing documents blocks transactions regardless of how healthy
  the PO looks. First-class risk signal.
- **`MatchApprovalLevel` and `InvoiceMatchOption`** — the CONFIGURED
  matching rule. Prompt A.3 can say "3-way match required against
  receipt". It still cannot say "1 of 3 invoices failed match": no
  per-invoice match RESULT exists on this pod.

**Site terms can differ from PO terms.** 701337 is `Net 30` against a
site default of `2/10 Net 30`. Not an error — the order overrode the
default — but it is exactly what prompt A.2 ("supplier setup through
payment") is asking about, so report it.

### 14.9 What does NOT exist — checked, not merely unfound

Recorded so nobody spends a session looking again.

| Wanted | Status |
|---|---|
| Payment number / payment date | **Absent.** Not on the invoice header, not on `invoiceInstallments`, no payments child |
| Per-invoice match RESULT | **Absent.** Only the configured `MatchApprovalLevel` |
| PO approval date / approver | **Absent** from `/purchaseOrders` |
| Receipt documents | Still blocked — see the 2026-07-17 rows on the three receiving resources |

The first is the one to be careful about in a demo: payment STATUS and
AMOUNT are fully answerable, so "has it been paid" works. "Which payment
paid it" does not.

### 14.10 Method notes

**A `.links[]` listing beats guessing paths.** One call named every child
of `/invoices` and ruled out two guesses at once.

**An absent child rules out a path, not a capability.** Holds were
briefly written off on the strength of no `holds` child; they were one
level down. Check the children of the children before declaring absence.

**Verify `fields=` per endpoint.** `/standardReceipts` 500s on any
projection; the supplier-site child accepts it. Neither is inferable from
the other.

**A control curl is what makes an empty result trustworthy.** 701337's
zero invoices only became a finding once 162034 proved the filter works.
This is the second time in two sessions that a control has changed the
diagnosis (see 13.8).

**An unprojected fetch first, every time.** Both the invoice header and
the supplier record were curled with no `fields=` specifically to see
what they carry under their real names. `AmountPaid`, `CanceledFlag` and
`OnOFACListFlag` were all found that way — none of them was on the list
of fields anyone had thought to ask for.
---

## 15. Local-synthesis field discovery (2026-08-02 / 08-03)

Field names collected while replacing LLM-built records with
deterministic builders. Every row below was OBSERVED in executor output
or a curl, not inferred from a model's field description. Three of them
would have been guessed wrong, and two of those fail silently.

| Date | Endpoint / bucket | Finding |
|---|---|---|
| 2026-08-03 | `/receivablesCreditMemos` | **`fields=` is accepted (HTTP 200).** Unlike `/standardReceipts`, which 500s on it. Projected fields: `CustomerTransactionId`, `TransactionNumber`, `TransactionDate`, `EnteredAmount`, `CreditMemoCurrency`, `CreditMemoStatus`, `BillToCustomerName`, `BillToCustomerNumber`. |
| 2026-08-03 | `/receivablesCreditMemos` | **WHO columns are present** — `CreatedBy`, `CreationDate`, `LastUpdatedBy`, `LastUpdateDate`, confirmed by curl. Direct evidence for COL-01, which lists them as absent from the KG. Also on the header: `BusinessUnit`, `TransactionType`, `TransactionSource`, `AccountingDate`, `LegalEntityIdentifier`, `BillToSite`, `CreditReason`, `CrossReference`, `DefaultTaxationCountry`, `ShipToCustomerName`. |
| 2026-08-03 | `account_receipt_applications` | **Transaction fields are `ReferenceTransactionId` / `ReferenceTransactionNumber` / `ReferenceTransactionStatus`, NOT `TransactionId`.** A builder copying the pattern from `customer_transactions` reads two absent fields and writes 0 and "" into every row — a column of zeros that reads as data the pod does not hold rather than as a bug. Other fields: `ApplicationId`, `StandardReceiptId`, `ReceiptNumber`, `ReceiptMethod`, `ApplicationAmount`, `ApplicationDate`, `ApplicationStatus`, `CustomerSite`, `EnteredCurrency`. |
| 2026-08-03 | `receivablesinvoicetransactiondff` | **The id is `CustomerTrxId`, not `CustomerTransactionId`, and the context fields carry a DOUBLE leading underscore: `__FLEX_Context`, `__FLEX_Context_DisplayValue`.** Unlike every other AR bucket. Read wrong, the DFF block renders empty and looks like an invoice carrying no flexfield values. |
| 2026-08-03 | `account_credit_memos` vs `credit_memos` | **The same business object in two shapes.** The account child uses `CreditMemoId` + `TotalOriginalAmount` + `TotalBalanceAmount`; the top-level list uses `CustomerTransactionId` + `EnteredAmount`. Easy to conflate, and conflating them yields zeros. The account child also carries `TransactionClass` ("On Account Credit Memo"), `AvailableAmount`, `BillToSiteNumber`. |
| 2026-08-03 | `standard_receipts` vs `account_receipts` | **Also two shapes.** Both carry `StandardReceiptId`, `ReceiptNumber`, `ReceiptDate`, `Amount`, `Currency`, `ReceiptMethod`. Only the top-level list carries `CustomerName`, `CustomerAccountNumber`, `Status` and the three `RemittanceBank*` fields; only the account child carries `State`, `UnappliedAmount`, `ProcessStatus`, `BusinessUnit`. |
| 2026-08-03 | `customer_transactions` | `TransactionId`, `TransactionNumber`, `TransactionClass`, `TransactionDate`, `PaymentScheduleDueDate`, `TotalOriginalAmount`, `TotalBalanceAmount`, `InstallmentStatus`. |
| 2026-08-02 | `/suppliers` vs `/invoices` — **ordering stability** | **`/suppliers` returns the same rows across runs. `/invoices` does not.** Byte-diffing the same eight prompts twice, minutes apart: seven outputs identical, the invoice one returned entirely different rows — same structure, same count, different data (2013–2016 dates on one run, 2023–2024 on the next). This confirms on a SECOND endpoint the ordering hypothesis previously open for `/standardReceipts`. Consequence: an aggregate computed over a 25-row sample is not merely wrong, it is DIFFERENTLY wrong on each run, and the same question answered twice gives two answers with no error either time. |
| 2026-08-03 | `receivablesInvoiceLineTaxLines` | Endpoint name confirmed. It is NOT `receivablesTaxLines` — a curl against that path returns empty. Reinforces the CAUTION in section 9: the tax row's own `CustomerTransactionLineId` is the TAX line's PK; the join key to its invoice line is **`ParentCustomerTransactionLineId`**. |
| 2026-08-13 | /suppliers | **Population now 333** — 331 ACTIVE, 2 INACTIVE (was 429 in the v1.7 census, 301 in the 2026-08-12 overnight run; the population moves, so confirm rather than assume). Counted client-side by `Status` over a full `fields=SupplierNumber,Status&limit=500` fetch (`{'ACTIVE': 331, 'INACTIVE': 2}`) — `q=Status='ACTIVE'` still returns 0 (see §6.1). The 2 inactive also surface via `q=InactiveDate IS NOT NULL&totalResults=true` (= 2), matching the client-side count exactly. Also confirmed: `TaxpayerCountryCode` is on the default supplier body, populated but **nullable** (4/5 sampled = 'US', supplier 1256 US Gas and Electric = null). |

**Method note.** These were found only after `--show-raw-output` stopped
truncating each row at six fields. It had been capping silently, and on
2026-08-03 that cost two turns and a wrong conclusion: a credit-memo row
displayed six fields, the table showed a populated Customer column, and
the obvious reading was that the model had invented customer names. It
had not — `BillToCustomerName` sits at position seven and the tool had
been fetching it all along. The flag now names what it holds back, and
the two stamped fields `total_credit` / `total_credit_note` surfaced on
its first run afterwards.

---

## 16. Collection sizes, page size and ordering (2026-08-04)

Everything below was measured against `fa-esll-dev37` on 2026-08-04. Two
entries CONTRADICT earlier sections of this document; both are marked.

### 16.1 How big the collections actually are

None of these numbers was known to the code. Each was obtained with one
call — `limit=1&totalResults=true&onlyData=true`, no projection.

| Endpoint | `totalResults` | Previously recorded |
|---|---|---|
| `/purchaseOrders` | **15,839** | ~3,362, in a tool docstring |
| `/invoices` | **48,931** | not recorded |
| `/standardReceipts` | **37,338** | 37,335 (§9), then 37,337 (§12) |
| `/receivablesCustomerAccountActivities` | 435 | 435 — unchanged |

**The 3,362 mattered.** It lived in `aggregate_purchase_orders.py` and
was used as the reason a 50-page cap was safe. At 200 rows per page a
full PO scan needs 80 pages, so every unfiltered breakdown stopped at
10,000 of 15,839 and reported lower bounds — with one status understated
by 860 million. A wrong number in a docstring, used to justify a bound,
survives for as long as nobody re-measures.

`/standardReceipts` has now been recorded three times as three different
numbers (37,335 / 37,337 / 37,338). The collection is presumably growing;
treat any recorded count here as an order of magnitude, not a constant,
and re-probe when the exact figure matters.

### 16.2 `limit=500` works — the "~200 practical max" is too conservative

**Contradicts §7 quirk 5**, which says "max practical limit before things
get slow: ~200".

`aggregate_invoices.py` had been paging `/invoices` at 500 for as long as
both it and that note existed, without incident. Measured on 2026-08-04
against `/purchaseOrders`: **32 pages of 500, no slowdown, complete
15,839-row scan.** Also 75 pages of 500 against `/standardReceipts`,
37,338 rows, twice.

Both aggregation paths now use 500. `compare_orders_to_invoices` and
`po_lifecycle` still use 200 — deliberately unchanged, because raising
them at the same time as extracting their shared paging loop would have
made the extraction unverifiable as a no-op.

The ~200 note is either stale or endpoint-specific. It has not been
disproved for every resource, so it stays in §7 rather than being
deleted; if a fetch starts erroring or slowing, it is the first thing to
re-read.

### 16.3 `orderBy=StandardReceiptId` — see §12.2

Recorded in full at §12.2, which is now resolved. The short version: the
sort key is the PK, it is genuinely applied across page boundaries, and
`ReceiptNumber` is NOT unique on this pod so it cannot serve as one.

**The caution is worth repeating here.** Adding `orderBy` to a fetch that
is still CAPPED buys reproducibility and can cost representativeness — a
PK-ascending cap returns the oldest rows rather than arbitrary ones. Add
the ordering and raise the cap together, or state the skew.

### 16.4 A single-field `fields=` returned 200 on `/standardReceipts`

**Apparently contradicts §7 quirk 7 and the two §2 entries** which state
that `fields=` is unusable on this endpoint — that it 500s even when
every named field is valid, confirmed twice, at a cost of six
misdiagnosed calls.

On 2026-08-04, this returned HTTP 200 with two rows:

```
/standardReceipts?limit=2&orderBy=ReceiptNumber&onlyData=true&fields=ReceiptNumber
```

A three-field projection in the same session returned an empty body
(`fields=ReceiptId,ReceiptNumber,Amount`) — but that call ALSO carried an
invalid field name, `ReceiptId`, so it is not a clean test of the
projection.

**Not treated as a correction.** One observation against two confirmed
ones, with a plausible confounder (single field versus several, or
`orderBy` present), and no clean isolation was run. Recorded so the next
person knows the rule may be narrower than "any projection 500s" —
possibly "more than one field", possibly something else.

**The operational advice does not change: do not project on
`/standardReceipts`.** Fetch full rows and discard client-side. The cost
of being wrong here is a 500 that reads as a dead endpoint, which has
already been misdiagnosed twice.

### 16.5 The complete receipt-method distribution

Worth recording because every previously observed version of this was a
sample, and the samples were badly unrepresentative.

Full scan, 37,338 receipts, 22 methods. Top of the distribution:

| Method | Receipts | Total |
|---|---|---|
| Lockbox | 18,661 | 8,400,099,630.76 |
| Check (Directly/No Remit) | 18,480 | 2,143,250,945.29 |
| EFT (Automatic) | 29 | 2,006,690.95 |
| Credit Card (No Confirmation) | 80 | 608,796.28 |

Grand total 10,546,439,259.11. The remaining 18 methods are single- and
double-digit counts.

**Lockbox and Check are within 1% of each other by count.** Every capped
version of this answer got that badly wrong — a 5,000-row unordered
sample showed 4,754 Lockbox against 179 Check; the ordered sample showed
Check as absent entirely.

`ReceiptMethod` values are free text and messier than the four above
suggest: `BO_EPAY`, `MD_CHECK`, `DDHC Automatic Receipt Method`,
`BFTC Receipt Method wo Remit`, `ERPONE RECEIPT METHOD`. Anything
matching on this field client-side should not assume a small closed set.

### 16.6 `CANCELED` POs — unexplained

Across the complete 15,839-row scan: **1,496 POs with status `CANCELED`,
totalling 4,000.00** — under three units each, against an overall average
in the tens of thousands.

It survived a full fetch, so it is real data rather than a sampling
artefact. Either cancelled orders zero out their `Ordered` amount on this
pod, or the demo data is shaped oddly. Not investigated. Worth knowing
before anyone builds a metric that includes cancelled orders.
