# KG FIELD TRANSLATION — drafted SQL roles to `kg_entity_field` names

**Purpose:** the option-(A) translation pass. Every SQL role drafted in `KG_ROLE_MAPS.md` (and Phase 2 §3) is mapped to a `kg_entity_field.field_name`. Where no field exists, the role is listed as a **gap**. Where a field exists but no SQL role names it, the field is listed as **field-only**.

**Decision of record:** option (A) — one vocabulary. `kg_sql_column` and `kg_derived_projection` key on `(entity_name, field_name)` from `kg_entity_field`, not on snake_case role names.

**What a gap means:** a drafted SQL role with no matching `kg_entity_field` row. The role cannot be bound until either (a) the field is added to `kg_entity_field` (option C), or (b) the role is accepted as unbound. This document does **not** decide that; it surfaces the gaps so the decision is made once, with all of them visible.

**What field-only means:** a `kg_entity_field` row that no drafted SQL role uses. Not an error — the REST layer carries fields the SQL projection does not. It means the field has no `kg_sql_column` row; if a future prompt needs it as a SQL column, a role is added then.

---

## Summary (11 entities)

| Entity | SQL roles | mapped | SQL-role gap | field-only |
|---|---|---|---|---|
| Supplier | 4 | 3 | 1 | 5 |
| Invoice | 7 | 7 | 0 | 6 |
| PurchaseOrder | 6 | 4 | 2 | 10 |
| Buyer | 4 | 4 | 0 | 1 |
| Address | 6 | 1 | 5 | 1 |
| Classification | 4 | 0 | 4 | 0 |
| Site | 3 | 0 | 3 | 0 |
| Contact | 3 | 1 | 2 | 7 |
| PurchaseOrderLine | 10 | 10 | 0 | 2 |
| POSchedule | 9 | 9 | 0 | 9 |
| PODistribution | 5 | 5 | 0 | 11 |
| **Total** | **61** | **44** | **17** | **52** |

96 field rows total: 44 mapped, 52 field-only. 61 SQL roles: 44 mapped, 17 gap.

---

## Per entity

### Supplier

| SQL role | field_name | physical | note |
|---|---|---|---|
| supplier_id | SupplierId | POZ_SUPPLIERS.VENDOR_ID | canonical_id |
| supplier_number | SupplierNumber | POZ_SUPPLIERS.SEGMENT1 | display_id |
| supplier_name | Supplier | HZ_PARTIES.PARTY_NAME | display_name |
| enabled | — | POZ_SUPPLIERS.ENABLED_FLAG | **GAP** — no field. Nearest field is `Status` (ACTIVE/INACTIVE), semantically different from ENABLED_FLAG Y/N. |

Field-only: Status, CreatedBy, CreationDate, LastUpdatedBy, LastUpdateDate (5).

### Invoice

| SQL role | field_name | physical | note |
|---|---|---|---|
| invoice_id | InvoiceId | AP_INVOICES_ALL.INVOICE_ID | canonical_id |
| invoice_num | InvoiceNumber | AP_INVOICES_ALL.INVOICE_NUM | display_id |
| invoice_amount | InvoiceAmount | AP_INVOICES_ALL.INVOICE_AMOUNT | amount |
| invoice_date | InvoiceDate | AP_INVOICES_ALL.INVOICE_DATE | date |
| invoice_currency_code | InvoiceCurrency | AP_INVOICES_ALL.INVOICE_CURRENCY_CODE | projection |
| supplier_number | SupplierNumber | POZ_SUPPLIERS.SEGMENT1 | reference |
| payment_status_flag | PaidStatus | AP_INVOICES_ALL.PAYMENT_STATUS_FLAG | status |

Field-only: ApprovalStatus, PurchaseOrderNumber, CreatedBy, CreationDate, LastUpdatedBy, LastUpdateDate (6).

### PurchaseOrder

| SQL role | field_name | physical | note |
|---|---|---|---|
| po_header_id | POHeaderId | PO_HEADERS_ALL.PO_HEADER_ID | canonical_id |
| po_number | OrderNumber | PO_HEADERS_ALL.SEGMENT1 | display_id |
| status | StatusCode | PO_HEADERS_ALL.DOCUMENT_STATUS | status — DOCUMENT_STATUS is a code; maps to StatusCode, not Status (Status is the human-readable projection). |
| amount | Ordered | derived: SUM(PO_LINES_ALL.AMOUNT) | amount — REST calls the excluding-tax total `Ordered`; the derived expression produces it. |
| supplier_name | — | HZ_PARTIES.PARTY_NAME | **GAP** — joined name, no REST field. PurchaseOrder carries `SupplierId`, not a name. |
| buyer_name | — | PER_PERSON_NAMES_F.DISPLAY_NAME | **GAP** — joined name, no REST field. PurchaseOrder carries `BuyerId`, not a name. |

Field-only: Status, SupplierId, BuyerId, CurrencyCode, Total, TotalTax, CreatedBy, CreationDate, LastUpdatedBy, LastUpdateDate (10). Note: `Total`/`TotalTax` are fields with no drafted SQL role — the SQL map derives `amount` only; if a consumer needs tax-inclusive total on the SQL path, that is a new derived role, not a translation of an existing one.

### Buyer

| SQL role | field_name | physical | note |
|---|---|---|---|
| buyer_id | PersonId | PER_ALL_PEOPLE_F.PERSON_ID | canonical_id |
| employee_number | PersonNumber | PER_ALL_PEOPLE_F.PERSON_NUMBER | display_id |
| display_name | DisplayName | PER_PERSON_NAMES_F.DISPLAY_NAME | display_name |
| email_address | WorkEmail | PER_EMAIL_ADDRESSES.EMAIL_ADDRESS | projection |

Field-only: Username (1) — a field with no SQL carrier in the draft.

### Address

| SQL role | field_name | physical | note |
|---|---|---|---|
| country | Country | HZ_LOCATIONS.COUNTRY | projection |
| party_site_id | — | HZ_PARTY_SITES.PARTY_SITE_ID | **GAP** |
| party_id | — | HZ_PARTY_SITES.PARTY_ID | **GAP** |
| address1 | — | HZ_LOCATIONS.ADDRESS1 | **GAP** |
| city | — | HZ_LOCATIONS.CITY | **GAP** |
| state | — | HZ_LOCATIONS.STATE | **GAP** |

Field-only: CountryCode (1). **Address is the widest misalignment in the corpus:** 6 SQL roles, 1 REST field (Country + CountryCode). The address lines and site keys have no REST vocabulary at all.

### Classification

**Entire entity gap.** 4 SQL roles (classification_id, supplier_id, lookup_code, status), **0 field rows**. No REST vocabulary exists for Classification on this pod.

### Site

**Entire entity gap.** 3 SQL roles (site_id, site_code, procurement_bu_id), **0 field rows**. No REST vocabulary exists for Site.

### Contact

| SQL role | field_name | physical | note |
|---|---|---|---|
| contact_id | SupplierContactId | POZ_SUPPLIER_CONTACTS.VENDOR_CONTACT_ID | canonical_id |
| supplier_id | — | POZ_SUPPLIER_SITES_ALL_M.VENDOR_ID | **GAP** — joined supplier id, no REST field. |
| party_site_id | — | POZ_SUPPLIER_CONTACTS.PARTY_SITE_ID | **GAP** |

Field-only: ContactName, FirstName, LastName, Email, JobTitle, Status, AdministrativeContactFlag (7).

### PurchaseOrderLine

| SQL role | field_name | physical | note |
|---|---|---|---|
| po_line_id | POLineId | PO_LINES_ALL.PO_LINE_ID | canonical_id |
| line_number | LineNumber | PO_LINES_ALL.LINE_NUM | display_id |
| description | Description | PO_LINES_ALL.ITEM_DESCRIPTION | projection |
| category_id | Category | PO_LINES_ALL.CATEGORY_ID | **semantic mismatch** — field is the display name (e.g. Marketing General), SQL is CATEGORY_ID (numeric). Flagged for revisit. |
| quantity | Quantity | PO_LINES_ALL.QUANTITY | projection |
| unit_price | Price | PO_LINES_ALL.UNIT_PRICE | projection |
| amount | Ordered | PO_LINES_ALL.AMOUNT | amount |
| status | StatusCode | PO_LINES_ALL.LINE_STATUS | status — LINE_STATUS is a code; maps to StatusCode. |
| total_tax | TotalTax | derived: SUM(PO_LINE_LOCATIONS_ALL.ESTIMATED_TAX_AMOUNT) | amount |
| total | Total | derived: L.AMOUNT + tax subquery | amount |

Field-only: OrderNumber, Status (2).

### POSchedule

| SQL role | field_name | physical | note |
|---|---|---|---|
| line_location_id | LineLocationId | PO_LINE_LOCATIONS_ALL.LINE_LOCATION_ID | canonical_id |
| schedule_number | ScheduleNumber | PO_LINE_LOCATIONS_ALL.SHIPMENT_NUM | display_id |
| ship_to_location_id | ShipToLocation | PO_LINE_LOCATIONS_ALL.SHIP_TO_LOCATION_ID | **semantic mismatch** — field is the location name (e.g. Seattle), SQL is SHIP_TO_LOCATION_ID (numeric). |
| requested_delivery_date | RequestedDeliveryDate | PO_LINE_LOCATIONS_ALL.NEED_BY_DATE | date |
| quantity | Quantity | PO_LINE_LOCATIONS_ALL.QUANTITY | projection |
| amount | Amount | PO_LINE_LOCATIONS_ALL.AMOUNT | amount |
| status | ScheduleStatus | PO_LINE_LOCATIONS_ALL.SCHEDULE_STATUS | status |
| received_quantity | ReceivedQuantity | PO_LINE_LOCATIONS_ALL.QUANTITY_RECEIVED | projection |
| billed_quantity | BilledQuantity | PO_LINE_LOCATIONS_ALL.QUANTITY_BILLED | projection |

Field-only: POHeaderId, POLineId, OrderNumber, LineNumber, UOM, ShippedQuantity, AcceptedQuantity, ReceivedAmount, BilledAmount (9).

### PODistribution

| SQL role | field_name | physical | note |
|---|---|---|---|
| po_distribution_id | PODistributionId | PO_DISTRIBUTIONS_ALL.PO_DISTRIBUTION_ID | canonical_id |
| distribution_num | DistributionNumber | PO_DISTRIBUTIONS_ALL.DISTRIBUTION_NUM | display_id |
| charge_account_id | POChargeAccount | PO_DISTRIBUTIONS_ALL.DEST_CHARGE_ACCOUNT_ID | **semantic mismatch** — field is the account code combination (string), SQL is the id (numeric). |
| amount_ordered | Ordered | PO_DISTRIBUTIONS_ALL.AMOUNT_ORDERED | amount |
| status | StatusCode | derived: PO_LINES_ALL.LINE_STATUS | status |

Field-only: POHeaderId, POLineId, OrderNumber, ScheduleNumber, POAccrualAccount, POVarianceAccount, DeliverToLocationCode, Percentage, Quantity, Total, Status (11). **`Percentage` is the notable one:** the field exists, the SQL role was dropped (no carrier on PO_DISTRIBUTIONS_ALL). This is the correct shape — field exists at REST layer, no `kg_sql_column` row. Not a contradiction.

---

## The gap register (17 roles)

| Group | Entity | Roles | Resolution needed |
|---|---|---|---|
| Whole entity | Classification | classification_id, supplier_id, lookup_code, status | No REST vocabulary at all. Add fields (C) or accept unbound. |
| Whole entity | Site | site_id, site_code, procurement_bu_id | No REST vocabulary at all. Add fields (C) or accept unbound. |
| Joined names | PurchaseOrder | supplier_name, buyer_name | REST carries ids, not names. Add fields or accept unbound. |
| Address lines | Address | party_site_id, party_id, address1, city, state | Address has only Country/CountryCode as fields. Add fields or accept unbound. |
| Joined keys | Contact | supplier_id, party_site_id | Joined keys, no REST field. Add or accept unbound. |
| Flag | Supplier | enabled | Nearest field Status is semantically different. Add `Enabled` or accept unbound. |

**17 of 61 drafted SQL roles (28%) have no matching REST field.** Seven of the 17 are the two whole-entity gaps (Site, Classification); the other ten are joined values, address lines, and one flag.

---

## What this means for the DDL

1. **`kg_sql_column` keys `(entity_name, field_name)`** → FK to `kg_entity_field(entity_name, field_name)`. A field with no SQL carrier simply has no row here. Presence in `kg_sql_column` is the signal that a field is SQL-projectable.
2. **`kg_derived_projection` keys `(entity_name, field_name)`** → same FK. `PO.Ordered`, `POLine.TotalTax`, `POLine.Total`, `PODistribution.StatusCode` are derived rows.
3. **The 17 gaps are unbound** — no row in either satellite, because there is no field to key on. They remain documented in `KG_ROLE_MAPS.md` (the SQL side) but are not in the KG until a field is added or the role is dropped.
4. **`pk_column` on `kg_entity`** (Q1 resolved) — adjacent to `canonical_id_field`, per the earlier decision.
5. **Semantic mismatches (Category, ShipToLocation, POChargeAccount)** are mapped but flagged. They bind id-to-name; a consumer expecting the field's display string from the SQL path gets an id. This is a display concern, not a build failure, but it must be recorded so it is not mistaken for a correct translation.

---

## Decision — accept unbound (2026-11-18)

The 17 gap roles are accepted as **unbound**. They do not enter `kg_sql_column` or `kg_derived_projection`. They remain documented in `KG_ROLE_MAPS.md` (the SQL side) and in the gap register above. No fields are added to `kg_entity_field`.

**Consequences:**

- `kg_entity_field` stays the REST vocabulary. It is not widened with SQL-only fields (address lines, joined names, Site/Classification).
- **Site and Classification have no KG SQL projection path.** They have zero REST fields and now zero bound SQL roles. If the SQL emitter is expected to produce them, that is a separate decision (add fields, or accept they are unreachable via KG SQL). Flagged, not resolved.
- The 10 non-whole-entity gaps (PurchaseOrder `supplier_name`/`buyer_name`, Address lines, Contact keys, Supplier `enabled`) are SQL-side projections with no REST counterpart. They can be re-added to the KG the day a field is added, without re-deriving the role map.
- This is option (A) + accept-unbound: one vocabulary, partially bound. 44 of 61 roles bound; 17 unbound and documented.

---

*End of translation map.*
