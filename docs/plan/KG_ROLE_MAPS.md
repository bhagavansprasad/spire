# KG role maps

Per-entity contribution to `kg_sql_column` and `kg_derived_projection`. Append-only.

**Header rules.**

- Each `### <Entity>` section carries: `kg_entity` row, `base_joins`, the `kg_sql_column` table (`is_default_projection='Y'`), the `kg_derived_projection` table where present, bugs fixed, join-key verification, entity-specific observations.
- **Never trust the sweep.** Every projected column and every join key is verified against `t_task2_all.txt` per `SCHEMA_DISCOVERY_METHOD.md` §6–§7. The sweep's named first failure is a hint, not the count. Confirmed ×4 by Contact, Buyer, PurchaseOrder, PurchaseOrderLine — each named one, each had 3–5 real absences.
- **Never re-derive a verified map.** Once a section is here, it is transcribed into `kg_schema.sql` at build, not re-derived. Corrections are new sections referencing the old, not edits.
- **Substitutions and derived roles cite evidence.** A substituted column names the physical column, its data type and nullability; a derived role names the expression and the alias-resolution rule.
- **Null-returning roles are flagged.** A role that returns NULL, not 0, on the empty case says so in observations.

**Mechanisms referenced below.**

- `kg_sql_column` — direct columns. PK `(entity_name, physical_table, column_name)`. Phase 2 §5 Q3.
- `kg_derived_projection` — correlated scalar subqueries where no direct column carries the role. Phase 2 §5 Q6.
- Nullable join keys — every nullable key in any `base_joins` gets a §3.4 build self-check counting NULLs, requiring zero. Phase 2 §5 Q4.

---

## Procurement

### PurchaseOrder (`PO_HEADERS_ALL`)

`kg_entity`: `(PurchaseOrder, PO_HEADERS_ALL, PO_HEADER_ID)`

`base_joins`:

```
JOIN POZ_SUPPLIERS S ON S.VENDOR_ID = P.VENDOR_ID
JOIN HZ_PARTIES HP ON HP.PARTY_ID = S.PARTY_ID
JOIN PER_ALL_PEOPLE_F BP ON BP.PERSON_ID = P.AGENT_ID AND SYSDATE BETWEEN BP.EFFECTIVE_START_DATE AND BP.EFFECTIVE_END_DATE
JOIN PER_PERSON_NAMES_F PN ON PN.PERSON_ID = BP.PERSON_ID AND PN.NAME_TYPE = 'GLOBAL' AND SYSDATE BETWEEN PN.EFFECTIVE_START_DATE AND PN.EFFECTIVE_END_DATE
```

`kg_sql_column`, `is_default_projection='Y'`:

| role | table | column |
|---|---|---|
| `po_header_id` | `PO_HEADERS_ALL` | `PO_HEADER_ID` |
| `po_number` | `PO_HEADERS_ALL` | `SEGMENT1` |
| `supplier_name` | `HZ_PARTIES` | `PARTY_NAME` |
| `buyer_name` | `PER_PERSON_NAMES_F` | `DISPLAY_NAME` |
| `status` | `PO_HEADERS_ALL` | `DOCUMENT_STATUS` |

`kg_derived_projection`, `is_default_projection='Y'`:

| role | expression |
|---|---|
| `amount` | `(SELECT SUM(L.AMOUNT) FROM PO_LINES_ALL L WHERE L.PO_HEADER_ID = P.PO_HEADER_ID)` |

**Bugs fixed (3 of 6 projected columns absent).**

- `P.AUTHORIZATION_STATUS` → `PO_HEADERS_ALL.DOCUMENT_STATUS` (col 31, `VARCHAR2(100)`, N). Propagates to the `("search_purchase_orders","status")` filter's `predicate_template` — one fix covers both sites.
- `BP.DISPLAY_NAME` → `PER_PERSON_NAMES_F.DISPLAY_NAME` (col 18, `VARCHAR2(960)`). R-4 repeat.
- `P.AMOUNT` → derived projection. No header-level carrier on this pod (R-7).

**Join keys, verified both sides.** Non-nullable: `POZ_SUPPLIERS.VENDOR_ID` (1, N), `POZ_SUPPLIERS.PARTY_ID` (5, N), `HZ_PARTIES.PARTY_ID` (1, N), `PER_ALL_PEOPLE_F.PERSON_ID` (1, N), `PER_ALL_PEOPLE_F.EFFECTIVE_START_DATE` (2, N), `PER_ALL_PEOPLE_F.EFFECTIVE_END_DATE` (3, N), `PO_HEADERS_ALL.AGENT_ID` (36, N), `PER_PERSON_NAMES_F.PERSON_ID` (4, N), `PER_PERSON_NAMES_F.EFFECTIVE_START_DATE` (2, N), `PER_PERSON_NAMES_F.EFFECTIVE_END_DATE` (3, N).

**Nullable — Q4 self-check required.** `PO_HEADERS_ALL.VENDOR_ID` (col 51, Y). Count NULLs on `PO_HEADERS_ALL.VENDOR_ID`; require zero; non-zero fails the §3.4 build.

**Observations.** `supplier_id` filter's subquery reaches `POZ_SUPPLIERS` directly, bypassing the `S` join — two references to one table per emitted query, not a bug. `amount` returns NULL, not 0, for a PO with no lines. `PO_HEADERS_ALL` is a stub view (R-7).

### PurchaseOrderLine (`PO_LINES_ALL`)

`kg_entity`: `(PurchaseOrderLine, PO_LINES_ALL, PO_LINE_ID)`

`base_joins`: `[]` — none. Both derived subqueries are self-contained.

`kg_sql_column`, `is_default_projection='Y'`:

| role | table | column |
|---|---|---|
| `po_line_id` | `PO_LINES_ALL` | `PO_LINE_ID` |
| `line_number` | `PO_LINES_ALL` | `LINE_NUM` |
| `description` | `PO_LINES_ALL` | `ITEM_DESCRIPTION` |
| `category_id` | `PO_LINES_ALL` | `CATEGORY_ID` |
| `quantity` | `PO_LINES_ALL` | `QUANTITY` |
| `unit_price` | `PO_LINES_ALL` | `UNIT_PRICE` |
| `amount` | `PO_LINES_ALL` | `AMOUNT` |
| `status` | `PO_LINES_ALL` | `LINE_STATUS` |

`kg_derived_projection`, `is_default_projection='Y'`:

| role | expression |
|---|---|
| `total_tax` | `(SELECT SUM(LL.ESTIMATED_TAX_AMOUNT) FROM PO_LINE_LOCATIONS_ALL LL WHERE LL.PO_LINE_ID = L.PO_LINE_ID)` |
| `total` | `L.AMOUNT + (SELECT SUM(LL.ESTIMATED_TAX_AMOUNT) FROM PO_LINE_LOCATIONS_ALL LL WHERE LL.PO_LINE_ID = L.PO_LINE_ID)` |

`total` reuses the `total_tax` subquery verbatim. One estimator, two roles.

**Bugs fixed (5 of 10 projected columns absent).**

- `DESCRIPTION` → `PO_LINES_ALL.ITEM_DESCRIPTION` (col 84, `VARCHAR2(960)`, Y). Only description-shaped column.
- `PRICE` → `PO_LINES_ALL.UNIT_PRICE` (col 91, `NUMBER`, Y). Adjacent variants (`LIST_PRICE`, `BASE_UNIT_PRICE`, `MARKET_PRICE`, `TAX_EXCLUSIVE_PRICE`) are not the ordered price.
- `TOTAL_TAX` → derived. No line-level tax amount; the tax value lives at schedule level (`PO_LINE_LOCATIONS_ALL.ESTIMATED_TAX_AMOUNT`, col 58), reached via `PO_LINE_ID`.
- `TOTAL` → derived. Line amount plus estimated tax.
- `STATUS_LOOKUP_CODE` → `PO_LINES_ALL.LINE_STATUS` (col 72, `VARCHAR2(100)`, Y). The sweep's named failure; `FUNDS_STATUS` and `FIRM_STATUS_LOOKUP_CODE` are sub-statuses.

**Join keys, verified both sides.** Base entity has no joins. Inside the Q6 subquery: `PO_LINES_ALL.PO_LINE_ID` (col 1, N) = `PO_LINE_LOCATIONS_ALL.PO_LINE_ID` (col 34, N). Both NOT NULL — no Q4 self-check needed.

**Filter.** `("get_purchase_order_lines","po_header_id")` → `{alias}.PO_HEADER_ID = {value}` on alias `L` → `PO_LINES_ALL.PO_HEADER_ID` (col 75, N). Clean.

**Observations.** `ESTIMATED_TAX_AMOUNT` is an estimate; post-invoice actual tax lives as `RECOVERABLE_TAX` (col 152) + `NONRECOVERABLE_TAX` (col 153) on `PO_DISTRIBUTIONS_ALL`. If `actual_tax` is ever a distinct role, the path is `PO_LINES_ALL` → `PO_LINE_LOCATIONS_ALL.LINE_LOCATION_ID` → `PO_DISTRIBUTIONS_ALL.LINE_LOCATION_ID` — a second derived projection, not a substitution of the first. Not drafted today. `total` and `total_tax` return NULL, not 0, for a line with no schedules. `PO_LINES_ALL` carries `AMOUNT` and `UNIT_PRICE` but no `TOTAL`/`TOTAL_TAX` — this is the Fusion shape, not a stub; totals and tax are computed at schedule/distribution level.

**F-060 correction (2026-11-19).** The `amount → PO_LINES_ALL.AMOUNT` row
above was **wrong**: `AMOUNT` is a stub (NULL on 315,857 / 315,970 rows,
99.96%), so `Ordered` emitted NULL where REST returned the line amount.
`TAX_EXCLUSIVE_PRICE` was ruled out as the substitute — it is a *unit*
price (equals `UNIT_PRICE`), populated on only 14.9% of rows, not the
extended amount. The corrected carrier is a derived projection:

| role | expression |
|---|---|
| `amount` (`Ordered`) | `L.UNIT_PRICE * L.QUANTITY` |

Two dependent expressions that read the stub `L.AMOUNT` were fixed in the
same pass: `PurchaseOrder.Ordered` → `SUM(L.UNIT_PRICE * L.QUANTITY)`, and
`PurchaseOrderLine.total` → `(L.UNIT_PRICE * L.QUANTITY) + (tax subquery)`.
The table above is left as the historical (wrong) draft; the seed in
`scripts/sql/kg_schema.sql` carries the fix. Full record:
`docs/fixes/FIX_PLAN.md` F-060.

### POSchedule (`PO_LINE_LOCATIONS_ALL`)

`kg_entity`: `(POSchedule, PO_LINE_LOCATIONS_ALL, LINE_LOCATION_ID)`

`base_joins`: `[]` — none. The filter reaches `PO_HEADER_ID` directly on this table; no join needed.

`kg_sql_column`, `is_default_projection='Y'`:

| role | table | column |
|---|---|---|
| `line_location_id` | `PO_LINE_LOCATIONS_ALL` | `LINE_LOCATION_ID` |
| `schedule_number` | `PO_LINE_LOCATIONS_ALL` | `SHIPMENT_NUM` |
| `ship_to_location_id` | `PO_LINE_LOCATIONS_ALL` | `SHIP_TO_LOCATION_ID` |
| `requested_delivery_date` | `PO_LINE_LOCATIONS_ALL` | `NEED_BY_DATE` |
| `quantity` | `PO_LINE_LOCATIONS_ALL` | `QUANTITY` |
| `amount` | `PO_LINE_LOCATIONS_ALL` | `AMOUNT` |
| `status` | `PO_LINE_LOCATIONS_ALL` | `SCHEDULE_STATUS` |
| `received_quantity` | `PO_LINE_LOCATIONS_ALL` | `QUANTITY_RECEIVED` |
| `billed_quantity` | `PO_LINE_LOCATIONS_ALL` | `QUANTITY_BILLED` |

**Bugs fixed (4 of 9 projected columns absent).**

- `SCHEDULE_NUM` → `PO_LINE_LOCATIONS_ALL.SHIPMENT_NUM` (col 140, `NUMBER`, N). In Fusion's physical model, a "schedule" **is** a "shipment" — `PO_LINE_LOCATIONS_ALL` is the shipments table, and `SHIPMENT_NUM` is the internal sequence. `CUSTOMER_PO_SCHEDULE_NUMBER` (col 246) and `SALES_ORDER_SCHEDULE_NUMBER` (col 251) are external reference numbers, not the sequence. **Type change recorded:** role returns `NUMBER`, not a string.
- `REQUESTED_DELIVERY_DATE` → `PO_LINE_LOCATIONS_ALL.NEED_BY_DATE` (col 47, `DATE`, Y). Semantic ambiguity — see observations.
- `RECEIVED_QUANTITY` → `PO_LINE_LOCATIONS_ALL.QUANTITY_RECEIVED` (col 39, `NUMBER`, Y). Pure column-name reversal; semantics unchanged.
- `BILLED_QUANTITY` → `PO_LINE_LOCATIONS_ALL.QUANTITY_BILLED` (col 42, `NUMBER`, Y). Same reversal. The sweep's named failure — fixed by this substitution.

**Join keys.** Base entity has no joins; nothing to verify on the entity's own `base_joins`. No Q4 self-check needed.

**Filter.** `("get_purchase_order_schedules","po_header_id")` → `{alias}.PO_HEADER_ID = {value}` on alias `S` → `PO_LINE_LOCATIONS_ALL.PO_HEADER_ID` (col 33, N). Verified present directly on the table — **no subquery, no join change.** The `"po_schedule_columns_from_reference"` assumption held on the filter side; first filter in the corpus whose column was not pre-verified from another entity, and the only clean case.

**Observations.** `requested_delivery_date` is semantically ambiguous: the pod carries `REQUESTED_SHIP_DATE` (10), `PROMISED_SHIP_DATE` (11), `NEED_BY_DATE` (47), `PROMISED_DATE` (48). `NEED_BY_DATE` chosen — arrival-side, matches "delivery." If the overlay intended the buyer-requested ship side, `REQUESTED_SHIP_DATE` is correct; revisit if downstream consumer clarifies. `schedule_number` returns `NUMBER` where a caller may format as text. Additional quantities exist if later roles need them: `QUANTITY_SHIPPED` (155), `QUANTITY_ACCEPTED` (40), `QUANTITY_REJECTED` (41), `QUANTITY_CANCELLED` (43), `SHIPPING_UOM_QUANTITY` (274). `ESTIMATED_TAX_AMOUNT` (58) — same column used by PurchaseOrderLine's `total_tax` — is available at schedule level if a schedule-tax role is ever wanted. `PO_LINE_ID` (34, N) present, enabling downstream traversal to lines without a `base_joins` change.

### PODistribution (`PO_DISTRIBUTIONS_ALL`)

`kg_entity`: `(PODistribution, PO_DISTRIBUTIONS_ALL, PO_DISTRIBUTION_ID)`

`base_joins`: `[]` — none. The `status` role is a correlated scalar subquery, self-contained.

`kg_sql_column`, `is_default_projection='Y'`:

| role | table | column |
|---|---|---|
| `po_distribution_id` | `PO_DISTRIBUTIONS_ALL` | `PO_DISTRIBUTION_ID` |
| `distribution_num` | `PO_DISTRIBUTIONS_ALL` | `DISTRIBUTION_NUM` |
| `charge_account_id` | `PO_DISTRIBUTIONS_ALL` | `DEST_CHARGE_ACCOUNT_ID` |
| `amount_ordered` | `PO_DISTRIBUTIONS_ALL` | `AMOUNT_ORDERED` |

`kg_derived_projection`, `is_default_projection='Y'`:

| role | expression |
|---|---|
| `status` | `(SELECT L.LINE_STATUS FROM PO_LINES_ALL L WHERE L.PO_LINE_ID = D.PO_LINE_ID)` |

**Bugs fixed (3 of 6 projected columns absent).**

- `PO_CHARGE_ACCOUNT_ID` -> `PO_DISTRIBUTIONS_ALL.DEST_CHARGE_ACCOUNT_ID` (col 166, `NUMBER(18,0)`, Y). Substitution. The five `*_ACCOUNT_ID` siblings (`BUDGET_ACCOUNT_ID` 132, `ACCRUAL_ACCOUNT_ID` 133, `VARIANCE_ACCOUNT_ID` 134, `DEST_CHARGE_ACCOUNT_ID` 166, `DEST_VARIANCE_ACCOUNT_ID` 167) are all nullable; `DEST_CHARGE_ACCOUNT_ID` is the distribution's expense landing point. **Semantic choice, not a name-reversal** — flagged for revisit if a consumer distinguishes budget/accrual/variance accounts.
- `STATUS` -> derived from `PO_LINES_ALL.LINE_STATUS` (col 72, `VARCHAR2(100)`, Y) via `PO_LINE_ID`. The sweep's named failure. `PO_DISTRIBUTIONS_ALL.FUNDS_STATUS` (col 5, `VARCHAR2(100)`, Y) is a sub-status, not the status — same reasoning as PurchaseOrderLine's `FUNDS_STATUS`/`FIRM_STATUS_LOOKUP_CODE`. No `STATUS` column exists anywhere in the `PO_DISTRIB%` family (9 objects: `_ALL`, `_ALL_SEC`, `_ARCHIVE_ALL`, `_ARCHIVE_ALL_SEC`, `_DRAFT_ALL`, `_DRAFT_ALL_SEC`, `_AP_V`, `_GT`, `_INTERFACE`), so no on-family substitute exists. Derived from parent line.
- `PERCENTAGE` -> **no carrier, not in default projection.** No percent-shaped column exists on `PO_DISTRIBUTIONS_ALL` or anywhere in the `PO_DISTRIB%` family (comprehensive `LIKE 'PO_DISTRIB%'` scan for `COLUMN_NAME IN ('STATUS','PERCENTAGE')` returned zero rows). Deriving it as `AMOUNT_ORDERED / line_amount` would manufacture a semantic the pod does not state; rejected. The role is absent from `kg_sql_column` and `kg_derived_projection` until a consumer requires it, at which point the semantic (percent-of-line vs percent-of-header) is a named decision.

**Join keys, verified both sides.** Base entity has no `base_joins`. Inside the Q6 subquery: `PO_DISTRIBUTIONS_ALL.PO_LINE_ID` (col 12, N) = `PO_LINES_ALL.PO_LINE_ID` (col 1, N). Both NOT NULL — no Q4 self-check needed.

**Nullable projection — flagged, not a join key.** `DEST_CHARGE_ACCOUNT_ID` is Y; `charge_account_id` returns NULL where the destination charge account is unset. `LINE_STATUS` is Y; `status` returns NULL for a distribution whose parent line has a null status. No `base_joins` nullable keys, so no §3.4 build self-check entry from this entity.

**Observations.** PODistribution's six projected columns collapse to four direct + one derived + one dropped — a 3-of-6 absence, the widest understatement of the sweep yet (sweep named one, real count three, plus one no-carrier role). This is R-8's fifth confirmation and its first case where a projected role has **no carrier at all** — the R-7 stub-view pattern extended from a missing derived value to a missing direct role. The `PO_DISTRIB%` family is a sibling cluster like `PO_HEADERS%` (R-7): nine objects, none carrying `STATUS` or `PERCENTAGE`. `PO_DISTRIBUTIONS` (the bare name, no suffix) is a SYNONYM to `PO_DISTRIBUTIONS_ALL`, not a distinct object. Expect the same sibling-cluster stub shape on `AP_INVOICES_ALL` and `RA_CUSTOMER_TRX_ALL`.

### Invoice (`AP_INVOICES_ALL`)

`kg_entity`: `(Invoice, AP_INVOICES_ALL, INVOICE_ID)`

`base_joins`:
`JOIN POZ_SUPPLIERS S ON S.VENDOR_ID = P.VENDOR_ID`

`kg_sql_column`, `is_default_projection='Y'`:

| role | table | column |
|---|---|---|
| `invoice_id` | `AP_INVOICES_ALL` | `INVOICE_ID` |
| `invoice_num` | `AP_INVOICES_ALL` | `INVOICE_NUM` |
| `invoice_amount` | `AP_INVOICES_ALL` | `INVOICE_AMOUNT` |
| `invoice_date` | `AP_INVOICES_ALL` | `INVOICE_DATE` |
| `invoice_currency_code` | `AP_INVOICES_ALL` | `INVOICE_CURRENCY_CODE` |
| `supplier_number` | `POZ_SUPPLIERS` | `SEGMENT1` |
| `payment_status_flag` | `AP_INVOICES_ALL` | `PAYMENT_STATUS_FLAG` |

`kg_derived_projection`: none.

**Bugs fixed: none (0 of 7 projected columns absent).** Every projected column verified present on the pod. `POZ_SUPPLIERS.SEGMENT1` (col 4, `VARCHAR2(120)`, N) is the supplier number, reused from Supplier's `supplier_number` role — same physical column, same semantics.

**Sweep flag stale — R-3 recurrence.** The Phase 1 sweep named `P.ENTERED_AMOUNT` as Invoice's first failing column. `ENTERED_AMOUNT` is **not in the current `select_columns`** — the projection has changed since the sweep ran, or the sweep ran against a different spec. The current seven columns are all valid. Same branch-divergence shape R-3 recorded for Buyer; recorded here so a future window does not re-chase a column the overlay no longer projects.

**Join keys, verified both sides.** `POZ_SUPPLIERS.VENDOR_ID` (col 1, N) = `AP_INVOICES_ALL.VENDOR_ID` (col 4, Y). Right side NOT NULL; **left side nullable**.

**Nullable — Q4 self-check required.** `AP_INVOICES_ALL.VENDOR_ID` (col 4, Y). Count NULLs on `AP_INVOICES_ALL.VENDOR_ID`; require zero; non-zero fails the §3.4 build. An inner join on a NULL `VENDOR_ID` silently drops those invoices. Third known nullable join key in the corpus, after `POZ_SUPPLIER_SITES_ALL_M.PARTY_SITE_ID` (Contact) and `PO_HEADERS_ALL.VENDOR_ID` (PurchaseOrder).

**Observations.** Invoice is the first entity in the corpus with a clean projection (0 absent) and the first whose sweep flag is stale rather than understated. `INVOICE_AMOUNT` (col 10, Y), `INVOICE_DATE` (col 14, Y), `PAYMENT_STATUS_FLAG` (col 25, Y) are nullable — the corresponding roles return NULL where unset. `PAYMENT_STATUS_FLAG` is `VARCHAR2(4)` — a short flag, not a descriptive status; if a consumer needs a status label, a lookup table join is a separate role, not a substitute for this one. No derived projection: `AP_INVOICES_ALL` carries `INVOICE_AMOUNT` directly, unlike `PO_HEADERS_ALL` (R-7) — the stub-view pattern does **not** recur here for the amount role. The R-7 prediction ("expect the same stub shape on AP_INVOICES_ALL") holds only for any header-total role not carried directly; the amount role is carried, so no derivation needed.

---

## Receivables

### CustomerTransaction (`AR_PAYMENT_SCHEDULES_ALL`)

`kg_entity`: `(CustomerTransaction, AR_PAYMENT_SCHEDULES_ALL, CUSTOMER_TRX_ID)`

`base_joins`: `[]` — none. The filter reaches `CUSTOMER_ID` directly.

`kg_sql_column`, `is_default_projection='Y'`:

| field | table | column |
|---|---|---|
| `TransactionId` | `AR_PAYMENT_SCHEDULES_ALL` | `CUSTOMER_TRX_ID` |
| `TransactionNumber` | `AR_PAYMENT_SCHEDULES_ALL` | `TRX_NUMBER` |
| `TransactionClass` | `AR_PAYMENT_SCHEDULES_ALL` | `CLASS` |
| `TransactionDate` | `AR_PAYMENT_SCHEDULES_ALL` | `TRX_DATE` |
| `PaymentScheduleDueDate` | `AR_PAYMENT_SCHEDULES_ALL` | `DUE_DATE` |
| `TotalOriginalAmount` | `AR_PAYMENT_SCHEDULES_ALL` | `AMOUNT_DUE_ORIGINAL` |
| `TotalBalanceAmount` | `AR_PAYMENT_SCHEDULES_ALL` | `AMOUNT_DUE_REMAINING` |
| `InstallmentStatus` | `AR_PAYMENT_SCHEDULES_ALL` | `STATUS` |

`kg_derived_projection`: none.

**Bugs fixed (F-066).** `TransactionId` → `CUSTOMER_TRX_ID` (col 21, `NUMBER(22)`, Y), not `PAYMENT_SCHEDULE_ID` (col 1). REST `TransactionId`=1624374 == `CUSTOMER_TRX_ID`, while `PAYMENT_SCHEDULE_ID`=1398398 on the same row (`TRX_NUMBER`='1471201'). The old map projected `PAYMENT_SCHEDULE_ID` as "InstallmentId" — a REST field that does not exist. Full record: `docs/fixes/FIX_PLAN.md` F-066.

**Verified (all 8).** `TRX_NUMBER` (col 69, `VARCHAR2(120)`, Y), `CLASS` (col 18, `VARCHAR2(80)`, N), `TRX_DATE` (col 70, `DATE`, Y), `DUE_DATE` (col 12, `DATE`, N), `AMOUNT_DUE_ORIGINAL` (col 13, `NUMBER`, N), `AMOUNT_DUE_REMAINING` (col 14, `NUMBER`, N), `STATUS` (col 16, `VARCHAR2(120)`, N). Value agreement confirmed against REST on one row: amount 693.83, balance 0, status `CL`/`Closed`, dates 2026-07-28.

**Filter.** `("get_customer_transactions","account_id")` → `{alias}.CUSTOMER_ID = {value}` → `AR_PAYMENT_SCHEDULES_ALL.CUSTOMER_ID` (col 19, Y). Holds the account's `CUST_ACCOUNT_ID` — account 300000047368527 returns 486 rows, matching REST.

**Observations.** `CUSTOMER_TRX_ID` is nullable (Y) — schedule rows for on-account/receipt items may carry NULL; the tool filters `CLASS='Invoice'` client-side, and those always carry a `CUSTOMER_TRX_ID`. `CLASS` distinguishes Invoice vs credit memo and is **not** queryable server-side (client-side filter). `TransactionId` (`CUSTOMER_TRX_ID`) is the AR transaction id, a different id space from ReceivablesInvoice's `CustomerTransactionId` (`RA_CUSTOMER_TRX_ALL.CUSTOMER_TRX_ID`).

### ReceivablesInvoice (`RA_CUSTOMER_TRX_ALL`)

`kg_entity`: `(ReceivablesInvoice, RA_CUSTOMER_TRX_ALL, CUSTOMER_TRX_ID)`

`base_joins`:

```
JOIN HZ_CUST_ACCOUNTS CA ON CA.CUST_ACCOUNT_ID = P.BILL_TO_CUSTOMER_ID
JOIN HZ_PARTIES HP ON HP.PARTY_ID = CA.PARTY_ID
```

`kg_sql_column`, `is_default_projection='Y'`:

| field | table | column |
|---|---|---|
| `CustomerTransactionId` | `RA_CUSTOMER_TRX_ALL` | `CUSTOMER_TRX_ID` |
| `TransactionNumber` | `RA_CUSTOMER_TRX_ALL` | `TRX_NUMBER` |
| `BillToCustomerName` | `HZ_PARTIES` | `PARTY_NAME` |
| `BillToCustomerNumber` | `HZ_CUST_ACCOUNTS` | `ACCOUNT_NUMBER` |
| `InvoiceCurrencyCode` | `RA_CUSTOMER_TRX_ALL` | `INVOICE_CURRENCY_CODE` |
| `TransactionDate` | `RA_CUSTOMER_TRX_ALL` | `TRX_DATE` |
| `InvoiceStatus` | `RA_CUSTOMER_TRX_ALL` | `COMPLETE_FLAG` |

`kg_derived_projection`, `is_default_projection='Y'`:

| field | expression |
|---|---|
| `EnteredAmount` | `(SELECT SUM(S.AMOUNT_DUE_ORIGINAL) FROM AR_PAYMENT_SCHEDULES_ALL S WHERE S.CUSTOMER_TRX_ID = P.CUSTOMER_TRX_ID)` |
| `InvoiceBalanceAmount` | `(SELECT SUM(S.AMOUNT_DUE_REMAINING) FROM AR_PAYMENT_SCHEDULES_ALL S WHERE S.CUSTOMER_TRX_ID = P.CUSTOMER_TRX_ID)` |

**Bugs fixed (3 of 7).**

- `ENTERED_AMOUNT` → derived. `RA_CUSTOMER_TRX_ALL` has no amount column (the R-7 stub-view shape at header level); the invoice amount lives on `AR_PAYMENT_SCHEDULES_ALL.AMOUNT_DUE_ORIGINAL` (sum over the invoice's schedules). Verified: invoice 300000248096352 → `SUM(AMOUNT_DUE_ORIGINAL)`=39969 = REST `EnteredAmount` (also equals `SUM(RA_CUSTOMER_TRX_LINES_ALL.EXTENDED_AMOUNT)`=39969 — schedules chosen because they also carry the balance).
- `STATUS_TRX` → `COMPLETE_FLAG`. `STATUS_TRX` (col 109) only ever holds `'OP'` (206,653 rows) or NULL — a stub. REST `InvoiceStatus`='Complete' ↔ `COMPLETE_FLAG`='Y' (col 70, `VARCHAR2(4)`, N; Y/N/P). The Y→Complete display mapping is F-061-class (cosmetic), not a data bug.
- `BillToCustomerNumber` → `HZ_CUST_ACCOUNTS.ACCOUNT_NUMBER` (col 4, `VARCHAR2(120)`, N) — added; the join already carries it, and REST projects it.

**Join keys, verified both sides.** `HZ_CUST_ACCOUNTS.CUST_ACCOUNT_ID` (col 1, N) = `RA_CUSTOMER_TRX_ALL.BILL_TO_CUSTOMER_ID` (col 20, Y). `HZ_CUST_ACCOUNTS.PARTY_ID` (col 2, N) = `HZ_PARTIES.PARTY_ID`. **Left side `BILL_TO_CUSTOMER_ID` is nullable (Y)** — Q4 self-check required (4th nullable join key in the corpus).

**Observations.** `RA_CUSTOMER_TRX_ALL` is the R-7 stub shape at the header level: no amount column, no due date, and a stub status. `InvoiceStatus` displays "Complete" while the SQL emits `COMPLETE_FLAG`='Y' (F-061 class). `DueDate`/`AccountingDate` also live off-header (`AR_PAYMENT_SCHEDULES_ALL`/GL) and are not projected here — a later role can add them as derived projections if a consumer needs them.

### ReceivablesInvoiceLine (`RA_CUSTOMER_TRX_LINES_ALL`)

`kg_entity`: `(ReceivablesInvoiceLine, RA_CUSTOMER_TRX_LINES_ALL, CUSTOMER_TRX_LINE_ID)`

`base_joins`: `[]` — none.

`kg_sql_column`, `is_default_projection='Y'`:

| field | table | column |
|---|---|---|
| `CustomerTransactionLineId` | `RA_CUSTOMER_TRX_LINES_ALL` | `CUSTOMER_TRX_LINE_ID` |
| `LineNumber` | `RA_CUSTOMER_TRX_LINES_ALL` | `LINE_NUMBER` |
| `Description` | `RA_CUSTOMER_TRX_LINES_ALL` | `DESCRIPTION` |
| `Quantity` | `RA_CUSTOMER_TRX_LINES_ALL` | `QUANTITY_INVOICED` |
| `UnitSellingPrice` | `RA_CUSTOMER_TRX_LINES_ALL` | `UNIT_SELLING_PRICE` |
| `LineAmount` | `RA_CUSTOMER_TRX_LINES_ALL` | `EXTENDED_AMOUNT` |

`kg_derived_projection`: none.

**Bugs fixed (0 of 6 absent).** Every hand-authored column already named the correct physical column (`QUANTITY_INVOICED`, `UNIT_SELLING_PRICE`, `EXTENDED_AMOUNT`). Verified present: `CUSTOMER_TRX_LINE_ID` (1, NUMBER, N), `LINE_NUMBER` (8, NUMBER, N), `DESCRIPTION` (12, VARCHAR2 960, Y), `QUANTITY_INVOICED` (17, NUMBER, Y), `UNIT_SELLING_PRICE` (19, NUMBER, Y), `EXTENDED_AMOUNT` (55, NUMBER, N). Value agreement confirmed on invoice 300000248096352 line 1: `LineNumber`=1, `Description`='Consultation', `Quantity`=1, `UnitSellingPrice`=39969, `LineAmount`=39969 — all equal REST.

**Join keys.** No `base_joins`; nothing to verify.

**Filter.** `("get_receivables_invoice_lines","customer_transaction_id")` → `{alias}.CUSTOMER_TRX_ID = {value}` → `RA_CUSTOMER_TRX_LINES_ALL.CUSTOMER_TRX_ID` (col 7, NUMBER, N). Clean.

**Observations.** `LineAmount` maps to `EXTENDED_AMOUNT` (NOT NULL), not a stub — the R-7 shape does **not** recur for the line amount. `UOM_CODE` (69), `INVENTORY_ITEM_ID` (11), `TAX_CLASSIFICATION_CODE` (141) are the carriers for `UnitOfMeasure`/`ItemNumber`/`TaxClassificationCode` but are NULL on this pod's rows and are not projected.

### CreditMemo (`RA_CUSTOMER_TRX_ALL`)

`kg_entity`: `(CreditMemo, RA_CUSTOMER_TRX_ALL, CUSTOMER_TRX_ID)`

`base_joins`:

```
JOIN HZ_CUST_ACCOUNTS CA ON CA.CUST_ACCOUNT_ID = C.BILL_TO_CUSTOMER_ID
JOIN HZ_PARTIES HP ON HP.PARTY_ID = CA.PARTY_ID
```

`kg_sql_column`, `is_default_projection='Y'`:

| field | table | column |
|---|---|---|
| `CustomerTransactionId` | `RA_CUSTOMER_TRX_ALL` | `CUSTOMER_TRX_ID` |
| `TransactionNumber` | `RA_CUSTOMER_TRX_ALL` | `TRX_NUMBER` |
| `TransactionDate` | `RA_CUSTOMER_TRX_ALL` | `TRX_DATE` |
| `CreditMemoCurrency` | `RA_CUSTOMER_TRX_ALL` | `INVOICE_CURRENCY_CODE` |
| `CreditMemoStatus` | `RA_CUSTOMER_TRX_ALL` | `COMPLETE_FLAG` |
| `BillToCustomerName` | `HZ_PARTIES` | `PARTY_NAME` |
| `BillToCustomerNumber` | `HZ_CUST_ACCOUNTS` | `ACCOUNT_NUMBER` |

`kg_derived_projection`, `is_default_projection='Y'`:

| field | expression |
|---|---|
| `EnteredAmount` | `(SELECT SUM(L.EXTENDED_AMOUNT) FROM RA_CUSTOMER_TRX_LINES_ALL L WHERE L.CUSTOMER_TRX_ID = C.CUSTOMER_TRX_ID)` |

**Bugs fixed (3 of 8).** Mirrors ReceivablesInvoice.

- `ENTERED_AMOUNT` → derived from **lines**, not schedules. The top-level `/receivablesCreditMemos` returns `EnteredAmount` even for **Incomplete** memos, which have no `AR_PAYMENT_SCHEDULES_ALL` rows yet (verified: memo 300000351645727 has 0 schedule rows but REST `EnteredAmount`=-1000). The line sum `SUM(EXTENDED_AMOUNT)`=-1000 matches exactly. The sign is carried by the data (credit lines are negative); no flip.
- `STATUS_TRX` → `COMPLETE_FLAG` (col 70, `VARCHAR2(4)`, N). REST `CreditMemoStatus`='Incomplete' ↔ `COMPLETE_FLAG`='N'; 'Complete' ↔ 'Y'. The Y→Complete display mapping is F-061 class.
- `BillToCustomerNumber` → `HZ_CUST_ACCOUNTS.ACCOUNT_NUMBER` — added (join-carried, REST projects it). Same as ReceivablesInvoice.

**Join keys, verified both sides.** `HZ_CUST_ACCOUNTS.CUST_ACCOUNT_ID` (1, N) = `RA_CUSTOMER_TRX_ALL.BILL_TO_CUSTOMER_ID` (20, Y). **Left side nullable** — the 5th nullable join key in the corpus (same physical column as ReceivablesInvoice; the two entities share one Q4 self-check entry).

**Observations.** The credit-memo amount lives on the **lines**, not the schedules — unlike ReceivablesInvoice (whose schedules also carry the balance). This is because Incomplete memos have no schedules. `TRX_CLASS` (216) is `'ONACC'` on the anchor memo; the top-level list is keyed by the `receivablesCreditMemos` resource, not a SQL `TRX_CLASS` filter.

### StandardReceipt (`AR_CASH_RECEIPTS_ALL`)

`kg_entity`: `(StandardReceipt, AR_CASH_RECEIPTS_ALL, CASH_RECEIPT_ID)`

`base_joins`:

```
JOIN HZ_CUST_ACCOUNTS CA ON CA.CUST_ACCOUNT_ID = R.PAY_FROM_CUSTOMER
JOIN HZ_PARTIES HP ON HP.PARTY_ID = CA.PARTY_ID
```

`kg_sql_column`, `is_default_projection='Y'`:

| field | table | column |
|---|---|---|
| `StandardReceiptId` | `AR_CASH_RECEIPTS_ALL` | `CASH_RECEIPT_ID` |
| `ReceiptNumber` | `AR_CASH_RECEIPTS_ALL` | `RECEIPT_NUMBER` |
| `ReceiptDate` | `AR_CASH_RECEIPTS_ALL` | `RECEIPT_DATE` |
| `Amount` | `AR_CASH_RECEIPTS_ALL` | `AMOUNT` |
| `Currency` | `AR_CASH_RECEIPTS_ALL` | `CURRENCY_CODE` |
| `Status` | `AR_CASH_RECEIPTS_ALL` | `STATUS` |
| `CustomerName` | `HZ_PARTIES` | `PARTY_NAME` |
| `CustomerAccountNumber` | `HZ_CUST_ACCOUNTS` | `ACCOUNT_NUMBER` |

`kg_derived_projection`: none.

**Bugs fixed (0 of 8 absent).** All eight direct columns present: `CASH_RECEIPT_ID` (1, NUMBER, N), `RECEIPT_NUMBER` (20, VARCHAR2 120, Y), `RECEIPT_DATE` (21, DATE, N), `AMOUNT` (12, NUMBER, N), `CURRENCY_CODE` (15, VARCHAR2 60, N), `STATUS` (18, VARCHAR2 120, Y), `HZ_PARTIES.PARTY_NAME`, `HZ_CUST_ACCOUNTS.ACCOUNT_NUMBER`. `CustomerAccountNumber` added (join-carried; REST projects it).

**Join keys, verified both sides.** `HZ_CUST_ACCOUNTS.CUST_ACCOUNT_ID` (1, N) = `AR_CASH_RECEIPTS_ALL.PAY_FROM_CUSTOMER` (17, Y). **Left side nullable** — 6th nullable join key in the corpus.

**Observations.** `ReceiptMethod` is deliberately absent: `RECEIPT_METHOD_ID` (56, NUMBER, N) is a numeric FK; REST returns the display string (e.g. 'Check (Directly/No Remit)') which lives on `AR_RECEIPT_METHODS` (join not mapped). `Status` (`STATUS`='APP') is the top-level status code; REST `Status`='Cleared' is a bank-clearance state with no clean single column — F-061-class display divergence, flagged not fixed. `CustomerSite`, `RemittanceBank*` are not projected (sparse / no mapped join). `customer_site` filter references `{alias}.CUSTOMER_SITE`, which does not exist on `AR_CASH_RECEIPTS_ALL` (only `CUSTOMER_SITE_USE_ID`, 51, NUMBER) — see FIX_PLAN backlog.

### AccountReceipt (`AR_CASH_RECEIPTS_ALL`)

`kg_entity`: `(AccountReceipt, AR_CASH_RECEIPTS_ALL, CASH_RECEIPT_ID)`

`base_joins`: `[]` — none; the `UnappliedAmount` subquery is self-contained.

`kg_sql_column`, `is_default_projection='Y'`:

| field | table | column |
|---|---|---|
| `StandardReceiptId` | `AR_CASH_RECEIPTS_ALL` | `CASH_RECEIPT_ID` |
| `ReceiptNumber` | `AR_CASH_RECEIPTS_ALL` | `RECEIPT_NUMBER` |
| `ReceiptDate` | `AR_CASH_RECEIPTS_ALL` | `RECEIPT_DATE` |
| `Amount` | `AR_CASH_RECEIPTS_ALL` | `AMOUNT` |
| `Currency` | `AR_CASH_RECEIPTS_ALL` | `CURRENCY_CODE` |

`kg_derived_projection`, `is_default_projection='Y'`:

| field | expression |
|---|---|
| `UnappliedAmount` | `R.AMOUNT - (SELECT SUM(A.AMOUNT_APPLIED) FROM AR_RECEIVABLE_APPLICATIONS_ALL A WHERE A.CASH_RECEIPT_ID = R.CASH_RECEIPT_ID)` |

**Bugs fixed (2 of 7).** The hand-authored spec had two defects:

- `AMOUNT_APPLIED` → **no such column** on `AR_CASH_RECEIPTS_ALL` (ORA-00904). `UnappliedAmount` is derived: `AMOUNT - SUM(applied)`. Verified on receipt 621469: `AMOUNT`=2021.67, `SUM(AMOUNT_APPLIED)`=2021.67 → `UnappliedAmount`=0 = REST.
- `STATUS` → `State`. **Wrong carrier.** `STATUS`='APP' (approval), not 'Applied'. REST `State` ('Applied'/'Unapplied') is the application state, computed by comparing `AMOUNT` to the applied sum — no single column carries it. `State` is dropped from the projection (see observations).

**Join keys.** No `base_joins`. Inside the Q6 subquery: `AR_RECEIVABLE_APPLICATIONS_ALL.CASH_RECEIPT_ID` (21, Y) = `AR_CASH_RECEIPTS_ALL.CASH_RECEIPT_ID` (1, N). The left side of the subquery is the base table; no Q4 self-check needed (the subquery is a correlated SUM, dropping nothing from the outer row).

**Observations.** Dropped (no clean carrier, documented): `ReceiptMethod` (numeric FK → display on `AR_RECEIPT_METHODS`), `State` (derived application state), `ProcessStatus` ('Open'/'Closed' — no column on this table), `CustomerSite` (`CUSTOMER_SITE_USE_ID` is numeric, REST is a site name, sparse), `BusinessUnit` (`ORG_ID` is a numeric FK, REST is a name). `AMOUNT` (12, NUMBER, N) is a real populated carrier, not a stub.

### CustomerAccount (`HZ_CUST_ACCOUNTS`)

`kg_entity`: `(CustomerAccount, HZ_CUST_ACCOUNTS, CUST_ACCOUNT_ID)`

`base_joins`:

```
JOIN HZ_PARTIES HP ON HP.PARTY_ID = CA.PARTY_ID
```

`kg_sql_column`, `is_default_projection='Y'`:

| field | table | column |
|---|---|---|
| `AccountId` | `HZ_CUST_ACCOUNTS` | `CUST_ACCOUNT_ID` |
| `AccountNumber` | `HZ_CUST_ACCOUNTS` | `ACCOUNT_NUMBER` |
| `CustomerName` | `HZ_PARTIES` | `PARTY_NAME` |
| `CustomerId` | `HZ_CUST_ACCOUNTS` | `PARTY_ID` |

`kg_derived_projection`: none.

**Bugs fixed (0 of 4 absent).** Identity verified: `CUST_ACCOUNT_ID` (1, NUMBER, N)=300000047368527, `ACCOUNT_NUMBER` (4, VARCHAR2 120, N)='26370', `PARTY_ID` (2, NUMBER, N)=100000000395797, `HZ_PARTIES.PARTY_NAME`='ABC Corporation Americas' — all equal REST.

**Join keys, verified both sides.** `HZ_CUST_ACCOUNTS.PARTY_ID` (2, N) = `HZ_PARTIES.PARTY_ID` (1, N). Both NOT NULL — no Q4 self-check.

**Observations — balances have NO clean carrier (R-7 at the account level).** `TotalOpenReceivablesForAccount` (14418895.83) and `TotalTransactionsDueForAccount` (15872395) live on the `/receivablesCustomerAccountActivities` service, not on `HZ_CUST_ACCOUNTS`. They are computed aggregates over `AR_PAYMENT_SCHEDULES_ALL`: `TotalTransactionsDueForAccount` = `SUM(AMOUNT_DUE_REMAINING) WHERE CLASS='INV'` (verified **exact**: 15872395), but `TotalOpenReceivablesForAccount` does **not** reduce to a clean single SUM — all-class remaining = 14418344 and INV+DM+CM remaining = 14419844, both off the REST value 14418895.83 by ~550–950. Binding a wrong SUM would violate the SQL-agrees-with-REST bar, so both balance roles are **dropped** (no carrier) until the exact aggregation is pinned. Recorded in FIX_PLAN.

### AccountCreditMemo (`AR_PAYMENT_SCHEDULES_ALL`)

`kg_entity`: `(AccountCreditMemo, AR_PAYMENT_SCHEDULES_ALL, CUSTOMER_TRX_ID)`

`base_joins`: `[]` — none.

`kg_sql_column`, `is_default_projection='Y'`:

| field | table | column |
|---|---|---|
| `CreditMemoId` | `AR_PAYMENT_SCHEDULES_ALL` | `CUSTOMER_TRX_ID` |
| `CreditMemoNumber` | `AR_PAYMENT_SCHEDULES_ALL` | `TRX_NUMBER` |
| `CreditMemoDate` | `AR_PAYMENT_SCHEDULES_ALL` | `TRX_DATE` |
| `TransactionClass` | `AR_PAYMENT_SCHEDULES_ALL` | `CLASS` |
| `TotalOriginalAmount` | `AR_PAYMENT_SCHEDULES_ALL` | `AMOUNT_DUE_ORIGINAL` |
| `TotalBalanceAmount` | `AR_PAYMENT_SCHEDULES_ALL` | `AMOUNT_DUE_REMAINING` |
| `CreditMemoStatus` | `AR_PAYMENT_SCHEDULES_ALL` | `STATUS` |
| `CreditMemoCurrency` | `AR_PAYMENT_SCHEDULES_ALL` | `INVOICE_CURRENCY_CODE` |

`kg_derived_projection`: none.

**Bugs fixed (1 of 8).** The hand-authored `PAYMENT_SCHEDULE_ID` → `CreditMemoId` was wrong (F-066-class). REST `CreditMemoId`=1581292 == `CUSTOMER_TRX_ID` (21, NUMBER, Y), **not** `PAYMENT_SCHEDULE_ID` (1)=1343229 on the same row. The id is "small" only because backfilled demo rows use small ids; it is still the `CUSTOMER_TRX_ID` space. All eight columns present: `CUSTOMER_TRX_ID` (21, NUMBER, Y), `TRX_NUMBER` (69, VARCHAR2 120, Y), `TRX_DATE` (70, DATE, Y), `CLASS` (18, VARCHAR2 80, N), `AMOUNT_DUE_ORIGINAL` (13, NUMBER, N), `AMOUNT_DUE_REMAINING` (14, NUMBER, N), `STATUS` (16, VARCHAR2 120, N), `INVOICE_CURRENCY_CODE` (17, VARCHAR2 60, N). Value agreement confirmed on memo 1581292: amounts -4971, status 'OP'→'Open', class 'CM'→'On Account Credit Memo' — all equal REST.

**Filter.** `("get_account_credit_memos","account_id")` → `{alias}.CUSTOMER_ID = {value} AND {alias}.CLASS = 'CM'` → `AR_PAYMENT_SCHEDULES_ALL.CUSTOMER_ID` (19, Y) + `CLASS`='CM'. Clean (the child holds credit memos only).

**Observations.** `AvailableAmount` (REST -4971) equals `AMOUNT_DUE_REMAINING` on this pod (both the unapplied credit) — no distinct column exists, so it is not projected separately. `BillToSiteNumber` carries a site **name** ('Santa Clara') not a number; no clean carrier on the schedule row (needs a site-use join) — dropped. `CreditMemoStatus` is the schedule `STATUS` ('Open'/'Closed'), a real populated carrier (unlike `RA_CUSTOMER_TRX_ALL.STATUS_TRX`).

### AccountReceiptApplication (`AR_RECEIVABLE_APPLICATIONS_ALL`)

`kg_entity`: `(AccountReceiptApplication, AR_RECEIVABLE_APPLICATIONS_ALL, RECEIVABLE_APPLICATION_ID)`

`base_joins`: `[]` — none. The REST row is "pre-joined" (receipt + transaction sides); the joined fields are not projected.

`kg_sql_column`, `is_default_projection='Y'`:

| field | table | column |
|---|---|---|
| `ApplicationId` | `AR_RECEIVABLE_APPLICATIONS_ALL` | `RECEIVABLE_APPLICATION_ID` |
| `ApplicationDate` | `AR_RECEIVABLE_APPLICATIONS_ALL` | `APPLY_DATE` |
| `ApplicationAmount` | `AR_RECEIVABLE_APPLICATIONS_ALL` | `AMOUNT_APPLIED` |
| `ApplicationStatus` | `AR_RECEIVABLE_APPLICATIONS_ALL` | `STATUS` |
| `StandardReceiptId` | `AR_RECEIVABLE_APPLICATIONS_ALL` | `CASH_RECEIPT_ID` |
| `ReferenceTransactionId` | `AR_RECEIVABLE_APPLICATIONS_ALL` | `APPLIED_CUSTOMER_TRX_ID` |

`kg_derived_projection`: none.

**Bugs fixed (1 of 6).** The hand-authored `PAYMENT_SCHEDULE_ID` → "ReferenceInstallmentId" (a REST field that does not exist) was wrong. REST `ReferenceTransactionId`=1624341 == `APPLIED_CUSTOMER_TRX_ID` (22, NUMBER, Y), **not** `PAYMENT_SCHEDULE_ID` (19)=1411372 (the receipt's own schedule). Same shape as F-066. Verified: `RECEIVABLE_APPLICATION_ID` (1, NUMBER, N)=994531, `AMOUNT_APPLIED` (7, NUMBER, N)=487.2, `STATUS` (18, VARCHAR2 120, N)='APP', `APPLY_DATE` (16, DATE, N), `CASH_RECEIPT_ID` (21, Y)=621464 — all equal REST (ApplicationAmount 487.2, ApplicationStatus 'Applied').

**Filter — fixed (F-068-class).** The prior `{alias}.CUSTOMER_TRX_ID IN (SELECT TRX_ID FROM RA_CUSTOMER_TRX_ALL …)` was wrong twice: `TRX_ID` does not exist (it is `CUSTOMER_TRX_ID`), and the receipt's own `CUSTOMER_TRX_ID` is the on-account transaction, not the applied one. Applications are children of receipts, so the account link is the receipt path: `{alias}.CASH_RECEIPT_ID IN (SELECT CASH_RECEIPT_ID FROM AR_CASH_RECEIPTS_ALL WHERE PAY_FROM_CUSTOMER = {value})`.

**Observations.** `ReceiptNumber`, `ReceiptMethod`, `ReferenceTransactionNumber`, `ReferenceTransactionStatus`, `EnteredCurrency`, `CustomerSite` are join-carried (receipt side via `CASH_RECEIPT_ID` → `AR_CASH_RECEIPTS_ALL`; transaction side via `APPLIED_CUSTOMER_TRX_ID` → `RA_CUSTOMER_TRX_ALL`, and its schedule status via `APPLIED_PAYMENT_SCHEDULE_ID` → `AR_PAYMENT_SCHEDULES_ALL`) and are not projected here — a later role can add them. `ApplicationStatus` (`STATUS`='APP') ↔ REST 'Applied' is a code-vs-display mapping (F-061 class).

### ReceivablesTaxLine (`ZX_LINES`)

`kg_entity`: `(ReceivablesTaxLine, ZX_LINES, TAX_LINE_ID)`

`base_joins`: `[]` — none; the filter keys the AR transaction/line directly.

`kg_sql_column`, `is_default_projection='Y'`:

| field | table | column |
|---|---|---|
| `CustomerTransactionLineId` | `ZX_LINES` | `TAX_LINE_ID` |
| `TaxLineNumber` | `ZX_LINES` | `TAX_LINE_NUMBER` |
| `TaxJurisdictionCode` | `ZX_LINES` | `TAX_JURISDICTION_CODE` |
| `TaxRate` | `ZX_LINES` | `TAX_RATE` |
| `TaxRateCode` | `ZX_LINES` | `TAX_RATE_CODE` |
| `TaxRegimeCode` | `ZX_LINES` | `TAX_REGIME_CODE` |
| `TaxStatusCode` | `ZX_LINES` | `TAX_STATUS_CODE` |
| `Tax` | `ZX_LINES` | `TAX` |
| `TaxAmount` | `ZX_LINES` | `TAX_AMT` |
| `TaxableAmount` | `ZX_LINES` | `TAXABLE_AMT` |
| `TaxPointDate` | `ZX_LINES` | `TAX_POINT_DATE` |

`kg_derived_projection`: none.

**Bugs fixed (9 of 11 absent — the largest understatement of the Receivables cluster).** The hand-authored spec pointed at `RA_CUST_TRX_LINE_GL_DIST_ALL` and projected `TAX_LINE_NUMBER`, `TAX_JURISDICTION_CODE`, `TAX_RATE`, `TAX_RATE_CODE`, `TAX_REGIME_CODE`, `TAX`, `TAXABLE_AMOUNT` — **none of which exist** on that table (it has only `AMOUNT`, `PERCENT`, `ACCOUNT_CLASS`, `ACCTD_AMOUNT`). On this pod line 74 has **no** `ACCOUNT_CLASS='TAX'` row (only a `REV` row). The real source is `ZX_LINES` (the tax engine), joined `TRX_ID`=`CUSTOMER_TRX_ID` and `TRX_LINE_ID`=`CUSTOMER_TRX_LINE_ID`, `ENTITY_CODE`='TRANSACTIONS'. Verified on invoice 1002 line 74: two rows (`TAX_LINE_ID` 9040/9039) whose `TAX`/`TAX_RATE`/`TAX_RATE_CODE`/`TAX_REGIME_CODE`/`TAX_STATUS_CODE`/`TAX_JURISDICTION_CODE`/`TAX_AMT`/`TAXABLE_AMT`/`TAX_POINT_DATE` all equal REST.

**Filter — fixed.** Prior `{alias}.CUSTOMER_TRX_ID = {value} AND {alias}.CUST_TRX_LINE_ID = :line_id AND {alias}.ACCOUNT_CLASS = 'TAX'` (wrong table + wrong column name) → `{alias}.TRX_ID = {value} AND {alias}.TRX_LINE_ID = :line_id AND {alias}.ENTITY_CODE = 'TRANSACTIONS'`.

**Observations — canonical-id discrepancy (open).** REST `CustomerTransactionLineId` on the tax line is 112/113 — the GL-dist `RA_CUST_TRX_LINE_GL_DIST_ALL.CUSTOMER_TRX_LINE_ID`, a **different** id space from `ZX_LINES.TAX_LINE_ID` (9039/9040). The role map binds the canonical id to `TAX_LINE_ID` (the tax engine's real PK) and records the REST-vs-physical id mismatch in FIX_PLAN. `TaxInclusiveIndicator` ('No') maps to `TAX_AMT_INCLUDED_FLAG` (code) and is not projected (F-061-class code-vs-display).

### ReceivablesInvoiceTransactionDFF (`RA_CUSTOMER_TRX_ALL`)

`kg_entity`: `(ReceivablesInvoiceTransactionDFF, RA_CUSTOMER_TRX_ALL, CUSTOMER_TRX_ID)`

`base_joins`: `[]` — none.

`kg_sql_column`, `is_default_projection='Y'`:

| field | table | column |
|---|---|---|
| `CustomerTrxId` | `RA_CUSTOMER_TRX_ALL` | `CUSTOMER_TRX_ID` |
| `__FLEX_Context` | `RA_CUSTOMER_TRX_ALL` | `ATTRIBUTE_CATEGORY` |

`kg_derived_projection`: none.

**Bugs fixed (1 of 2).** The hand-authored third column `ATTRIBUTE1` ("first DFF segment") was dropped: REST does not project a segment (only `CustomerTrxId`, `__FLEX_Context`, `__FLEX_Context_DisplayValue`), and the DFF child has no populated segment columns on this pod. `__FLEX_Context` → `ATTRIBUTE_CATEGORY` (52, VARCHAR2 120, Y)='DOO' on invoice 1002 = REST. `CustomerTrxId` → `CUSTOMER_TRX_ID` (1, NUMBER, N)=1002 = REST.

**Join keys.** No `base_joins`; nothing to verify.

**Observations.** `__FLEX_Context_DisplayValue` is NULL on this pod (REST returns null); no physical column carries a non-null display value here — dropped. The `ar_dff_columns_uncertain` assumption is now resolved: the context is `ATTRIBUTE_CATEGORY`, and there are no populated `ATTRIBUTE<n>` segments behind it on this pod.
