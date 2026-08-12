SET ECHO ON
SET FEEDBACK ON
SET SERVEROUTPUT ON

-- ============================================================
-- STEP 1: Drop all KG tables (safe if they don't exist)
--
-- Drop order matters: children (with FKs) must be dropped
-- before parents. Order:
--   kg_edge_tool       (FK -> kg_edge)
--   kg_entity_tool     (FK -> kg_entity)
--   kg_pattern_binding (FK -> kg_entity, kg_pattern)
--   kg_entity_field    (FK -> kg_entity)
--   kg_edge            (FK -> kg_entity)
--   kg_pattern         (parent)
--   kg_vocabulary      (no FKs, can go anywhere)
--   kg_entity          (parent)
-- ============================================================

BEGIN
  EXECUTE IMMEDIATE 'DROP TABLE kg_entity_filter PURGE';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'DROP TABLE kg_edge_tool PURGE';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'DROP TABLE kg_entity_tool PURGE';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'DROP TABLE kg_pattern_binding PURGE';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'DROP TABLE kg_entity_field PURGE';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'DROP TABLE kg_edge PURGE';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'DROP TABLE kg_pattern PURGE';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'DROP TABLE kg_vocabulary PURGE';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'DROP TABLE kg_entity PURGE';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

PROMPT All KG tables dropped (or did not exist).

-- ============================================================
-- STEP 2: Create tables
-- ============================================================

CREATE TABLE kg_entity (
  entity_name           VARCHAR2(64)   NOT NULL,
  canonical_id_field    VARCHAR2(64)   NOT NULL,
  display_name_field    VARCHAR2(64),
  endpoint_path         VARCHAR2(512)  NOT NULL,
  description           VARCHAR2(2000),
  CONSTRAINT pk_kg_entity PRIMARY KEY (entity_name)
);

CREATE TABLE kg_entity_field (
  entity_name      VARCHAR2(64)  NOT NULL,
  field_name       VARCHAR2(64)  NOT NULL,
  field_role       VARCHAR2(32)  NOT NULL,
  data_type_hint   VARCHAR2(32),
  notes            VARCHAR2(1000),
  CONSTRAINT pk_kg_entity_field PRIMARY KEY (entity_name, field_name),
  CONSTRAINT fk_kg_entity_field_entity
    FOREIGN KEY (entity_name) REFERENCES kg_entity (entity_name),
  CONSTRAINT chk_kg_entity_field_role
    CHECK (field_role IN (
      'canonical_id', 'display_id', 'display_name', 'status',
      'date', 'amount', 'reference', 'projection'
    ))
);

CREATE TABLE kg_edge (
  edge_name           VARCHAR2(64)   NOT NULL,
  from_entity         VARCHAR2(64)   NOT NULL,
  to_entity           VARCHAR2(64)   NOT NULL,
  from_join_field     VARCHAR2(64)   NOT NULL,
  to_join_field       VARCHAR2(64)   NOT NULL,
  cardinality         VARCHAR2(32)   NOT NULL,
  server_filter_rule  VARCHAR2(32)   DEFAULT 'join_only' NOT NULL,
  traversal_hint      VARCHAR2(2000) NOT NULL,
  notes               VARCHAR2(2000),
  iter_fields_json    VARCHAR2(2000),
  CONSTRAINT pk_kg_edge PRIMARY KEY (edge_name),
  CONSTRAINT fk_kg_edge_from
    FOREIGN KEY (from_entity) REFERENCES kg_entity (entity_name),
  CONSTRAINT fk_kg_edge_to
    FOREIGN KEY (to_entity)   REFERENCES kg_entity (entity_name),
  CONSTRAINT chk_kg_edge_cardinality
    CHECK (cardinality IN ('one_to_one', 'one_to_many', 'many_to_one', 'many_to_many')),
  CONSTRAINT chk_kg_edge_server_filter_rule
    CHECK (server_filter_rule IN ('join_only', 'first_filter_only', 'all_supported'))
);

CREATE TABLE kg_pattern (
  pattern_name    VARCHAR2(64)   NOT NULL,
  shape           VARCHAR2(2000) NOT NULL,
  parameters      CLOB,
  mechanics       CLOB,
  example         VARCHAR2(2000),
  CONSTRAINT pk_kg_pattern PRIMARY KEY (pattern_name)
);

CREATE TABLE kg_vocabulary (
  vocab_kind        VARCHAR2(32)   NOT NULL,
  term              VARCHAR2(128)  NOT NULL,
  canonical_value   VARCHAR2(128)  NOT NULL,
  notes             VARCHAR2(1000),
  CONSTRAINT pk_kg_vocabulary PRIMARY KEY (vocab_kind, term),
  CONSTRAINT chk_kg_vocabulary_kind
    CHECK (vocab_kind IN ('country', 'po_status', 'supplier_status', 'supplier_business_relationship', 'supplier_site_bu', 'supplier_classification', 'entity_synonym', 'relationship_phrase', 'field_synonym'))
);

CREATE TABLE kg_pattern_binding (
  entity_name        VARCHAR2(64)  NOT NULL,
  filter_type        VARCHAR2(64)  NOT NULL,
  pattern_name       VARCHAR2(64)  NOT NULL,
  parameter_bindings CLOB          NOT NULL,
  CONSTRAINT pk_kg_pattern_binding PRIMARY KEY (entity_name, filter_type),
  CONSTRAINT fk_kg_pattern_binding_entity
    FOREIGN KEY (entity_name) REFERENCES kg_entity (entity_name),
  CONSTRAINT fk_kg_pattern_binding_pattern
    FOREIGN KEY (pattern_name) REFERENCES kg_pattern (pattern_name)
);

CREATE TABLE kg_entity_tool (
  entity_name     VARCHAR2(64)  NOT NULL,
  filter_type     VARCHAR2(64)  NOT NULL,
  mcp_tool_name   VARCHAR2(128) NOT NULL,
  notes           VARCHAR2(1000),
  CONSTRAINT pk_kg_entity_tool PRIMARY KEY (entity_name, filter_type),
  CONSTRAINT fk_kg_entity_tool_entity
    FOREIGN KEY (entity_name) REFERENCES kg_entity (entity_name)
);

CREATE TABLE kg_edge_tool (
  edge_name       VARCHAR2(64)  NOT NULL,
  mcp_tool_name   VARCHAR2(128) NOT NULL,
  notes           VARCHAR2(1000),
  CONSTRAINT pk_kg_edge_tool PRIMARY KEY (edge_name),
  CONSTRAINT fk_kg_edge_tool_edge
    FOREIGN KEY (edge_name) REFERENCES kg_edge (edge_name)
);

CREATE TABLE kg_entity_filter (
  entity_name          VARCHAR2(64)  NOT NULL,
  filter_type          VARCHAR2(64)  NOT NULL,
  mechanism            VARCHAR2(32)  NOT NULL,
  tool_arg_name        VARCHAR2(64),
  tool_arg_name_hi     VARCHAR2(64),
  vocab_kind           VARCHAR2(32),
  target_entity        VARCHAR2(64),
  kg_filter_type       VARCHAR2(64),
  implicit_vocab_kind  VARCHAR2(32),
  implicit_term        VARCHAR2(128),
  query_style          VARCHAR2(16),
  filter_field         VARCHAR2(64),
  filter_op            VARCHAR2(16),
  notes                VARCHAR2(1000),
  CONSTRAINT pk_kg_entity_filter PRIMARY KEY (entity_name, filter_type),
  CONSTRAINT fk_kg_entity_filter_entity
    FOREIGN KEY (entity_name) REFERENCES kg_entity (entity_name),
  CONSTRAINT chk_kg_entity_filter_mechanism
    CHECK (mechanism IN ('entity_level', 'edge_traversal')),
  CONSTRAINT chk_kg_entity_filter_query_style
    CHECK (query_style IS NULL OR query_style IN ('server_q', 'client_side'))
);

PROMPT Tables created.

-- ============================================================
-- STEP 3: Seed kg_entity
-- ============================================================

INSERT INTO kg_entity VALUES (
  'Supplier', 'SupplierId', 'Supplier',
  '/fscmRestApi/resources/11.13.18.05/suppliers',
  'A vendor or service provider in Fusion''s supplier master. SupplierId is the system primary key used for joins to POs; SupplierNumber is the human-readable identifier used for joins to invoices. Country is on the child Address resource, not on Supplier directly.'
);

INSERT INTO kg_entity VALUES (
  'Invoice', 'InvoiceId', 'InvoiceNumber',
  '/fscmRestApi/resources/11.13.18.05/invoices',
  'An accounts-payable invoice tied to a supplier. Note: this endpoint exposes SupplierNumber (string) for the supplier reference, not SupplierId. Date-window filters use InvoiceDate.'
);

INSERT INTO kg_entity VALUES (
  'PurchaseOrder', 'POHeaderId', 'OrderNumber',
  '/fscmRestApi/resources/11.13.18.05/purchaseOrders',
  'A purchase order issued to a supplier and assigned to a buyer. Exposes SupplierId (numeric) for the supplier reference and BuyerId for the buyer reference. StatusCode carries values like OPEN, CLOSED, INCOMPLETE, CANCELED.'
);

INSERT INTO kg_entity VALUES (
  'Buyer', 'PersonId', 'DisplayName',
  '/hcmRestApi/resources/11.13.18.05/publicWorkers',
  'The purchasing agent assigned to a PO. Buyers are HCM workers, not an FSCM entity. PersonId equals the BuyerId on PurchaseOrder. No /fscmRestApi/.../buyers endpoint exists on this pod.'
);

INSERT INTO kg_entity VALUES (
  'Address', 'AddressId', NULL,
  '/fscmRestApi/resources/11.13.18.05/suppliers?expand=addresses',
  'A supplier''s address. Modeled as a separate entity because a supplier can have addresses in multiple countries. Not exposed as a top-level resource; only accessible as a child of Supplier via expand=addresses.'
);

INSERT INTO kg_entity VALUES (
  'Site', 'SupplierSiteId', 'SupplierSite',
  '/fscmRestApi/resources/11.13.18.05/suppliers/{SupplierId}/child/sites',
  'A supplier site (assignment point). Modeled as a separate entity because a supplier can have many sites, each in a different ProcurementBU. Not a top-level resource; only accessible as a child of Supplier at /suppliers/{SupplierId}/child/sites. ProcurementBU on a site filters reliably server-side via q= (unlike Status on Supplier).'
);

INSERT INTO kg_entity VALUES (
  'Classification', 'ClassificationId', 'Classification',
  '/fscmRestApi/resources/11.13.18.05/suppliers/{SupplierId}/child/businessClassifications',
  'A supplier business classification (e.g. Small Business, Woman Owned, ISO 14001). Modeled as a separate entity because a supplier can hold many. Not a top-level resource; only accessible as a child of Supplier at /suppliers/{SupplierId}/child/businessClassifications. Classification (display) filters reliably server-side via single-clause q=. Status (CURRENT/expired) cannot be AND-combined with Classification in one q= (composite quirk), so Status is not constrained here.'
);

INSERT INTO kg_entity VALUES (
  'PurchaseOrderLine', 'POLineId', 'LineNumber',
  '/fscmRestApi/resources/11.13.18.05/purchaseOrders/{POHeaderId}/child/lines',
  'A line on a purchase order. Modeled as a separate entity because a PO has many lines. Not a top-level resource; only accessible as a child of PurchaseOrder at /purchaseOrders/{POHeaderId}/child/lines. Unlike the supplier children (sites/classifications), the line body carries the parent id (both POHeaderId and OrderNumber), so the join key is present in the body. Lines are fetched as a plain expansion (no server filter needed).'
);

INSERT INTO kg_entity VALUES (
  'POSchedule', 'LineLocationId', 'ScheduleNumber',
  '/fscmRestApi/resources/11.13.18.05/purchaseOrderSchedules',
  'A shipment schedule on a purchase order. Reachable as a FLAT top-level collection (/purchaseOrderSchedules?q=POHeaderId=<id>) on this pod, so it is a one-hop fetch by POHeaderId (unlike PO lines, which are a nested child). The schedule row carries the full parent id chain (POHeaderId, POLineId, LineLocationId), which a later distributions phase needs. Include-only: not a root query target.'
);

INSERT INTO kg_entity VALUES (
  'Contact', 'SupplierContactId', 'ContactName',
  '/fscmRestApi/resources/11.13.18.05/suppliers/{SupplierId}/child/contacts',
  'A contact person on a supplier. A child of the supplier record at /suppliers/{SupplierId}/child/contacts. Like the other supplier children (sites, businessClassifications), the contact body does NOT carry the parent SupplierId, so the join key is the URL path. Include-only: attached to a supplier via HAS_CONTACT; not a root query target and not a filter.'
);

INSERT INTO kg_entity VALUES (
  'PODistribution', 'PODistributionId', 'DistributionNumber',
  '/fscmRestApi/resources/11.13.18.05/purchaseOrders/{POHeaderId}/child/lines/{POLineId}/child/schedules/{LineLocationId}/child/distributions',
  'A distribution on a PO schedule: the charge/accrual/variance accounts the schedule amount is booked to. The deepest PO child. No flat endpoint; reachable only on the deep nested path needing three ids (POHeaderId, POLineId, LineLocationId), all carried on the parent POSchedule row. Include-only; reached via HAS_DISTRIBUTION from POSchedule.'
);


-- AR-P2
INSERT INTO kg_entity VALUES (
  'ReceivablesInvoice', 'CustomerTransactionId', 'TransactionNumber',
  '/fscmRestApi/resources/11.13.18.05/receivablesInvoices',
  'An accounts-receivable (sell-side) invoice raised against a customer. Distinct from Invoice, which is the accounts-payable (buy-side) invoice on /invoices. Canonical id is CustomerTransactionId (numeric, queryable via q=); TransactionNumber is the human number (e.g. ''61765''). BillToCustomerName and BillToCustomerNumber are NOT queryable on this endpoint (confirmed live) - a customer''s invoices are reached via the customer account-activity path, not by filtering this collection. 173,531 rows on the pod, so list access must go through the account path, never a bulk scan.'
);

-- AR-P2
INSERT INTO kg_entity VALUES (
  'ReceivablesInvoiceLine', 'CustomerTransactionLineId', 'LineNumber',
  '/fscmRestApi/resources/11.13.18.05/receivablesInvoices/{CustomerTransactionId}/child/receivablesInvoiceLines',
  'A line on an AR invoice. Modeled as a separate entity because an invoice has many lines. Not a top-level resource; only accessible as a child of ReceivablesInvoice at /receivablesInvoices/{CustomerTransactionId}/child/receivablesInvoiceLines. Fetched as a plain expansion (no server filter needed). Note the pod misspells one field as TransacationBusinessCategory (sic) - it must be requested with the typo or ?fields= drops it silently.'
);


-- AR-P3
INSERT INTO kg_entity VALUES (
  'ReceivablesTaxLine', 'CustomerTransactionLineId', 'TaxLineNumber',
  '/fscmRestApi/resources/11.13.18.05/receivablesInvoices/{CustomerTransactionId}/child/receivablesInvoiceLines/{LineId}/child/receivablesInvoiceLineTaxLines',
  'A tax line on an AR invoice line - the jurisdiction/rate/amount breakdown for one line (e.g. a STATE row and a COUNTY row). A grandchild of ReceivablesInvoice, reached three levels deep but keyed by only two ids (invoice CustomerTransactionId + parent line CustomerTransactionLineId, both in the URL path). Not a top-level resource. A single-parent expansion off ReceivablesInvoiceLine, unlike PO distributions (which need three sibling ids). NOTE: the tax-line row carries its OWN CustomerTransactionLineId (the tax line PK, e.g. 112) - a different value from the parent invoice-line id (e.g. 74).'
);


-- AR-P3 DFF
INSERT INTO kg_entity VALUES (
  'ReceivablesInvoiceTransactionDFF', 'CustomerTrxId', 'CustomerTrxId',
  '/fscmRestApi/resources/11.13.18.05/receivablesInvoices/{CustomerTransactionId}/child/receivablesInvoiceTransactionDFF',
  'The transaction descriptive flexfield (DFF) of an AR invoice - the __FLEX_Context and (when configured) its segment values. A single-parent child of ReceivablesInvoice, keyed by the parent invoice id carried in the URL path. NOTE: the child echoes the parent id as CustomerTrxId (short spelling), NOT the CustomerTransactionId used on the header and lines - match the pod exactly. AR invoices expose TWO DFF children (receivablesInvoiceDFF and receivablesInvoiceTransactionDFF); this is the TransactionDFF one, which is the populated child on this pod (invoice 1002 returns __FLEX_Context=''DOO''; the plain receivablesInvoiceDFF returns null). On this demo pod the context is set but carries no populated segment columns - only CustomerTrxId, __FLEX_Context, __FLEX_Context_DisplayValue.'
);


-- AR-P2b
INSERT INTO kg_entity VALUES (
  'CustomerAccount', 'AccountId', 'CustomerName',
  '/fscmRestApi/resources/11.13.18.05/receivablesCustomerAccountActivities',
  'A customer''s accounts-receivable account. The resolve point for customer-scoped AR queries: a customer name resolves here (q=CustomerName= is queryable on this endpoint, unlike the AR-invoice endpoint) to one or more accounts, each carrying an AccountId. Traverse HAS_CUSTOMER_TRANSACTION from an account to its transactions. Also carries the account balances (TotalOpenReceivablesForAccount, TotalTransactionsDueForAccount).'
);

-- AR-P2b
INSERT INTO kg_entity VALUES (
  'CustomerTransaction', 'TransactionId', 'TransactionNumber',
  '/fscmRestApi/resources/11.13.18.05/receivablesCustomerAccountActivities/{AccountId}/child/transactionPaymentSchedules',
  'A transaction (payment schedule / installment) on a customer account. Reached as a child of CustomerAccount. NOT the same object as ReceivablesInvoice: different id space (TransactionId, small ints, vs CustomerTransactionId) and different fields (TotalOriginalAmount/TotalBalanceAmount vs EnteredAmount/InvoiceBalanceAmount). The collection holds multiple classes; TransactionClass distinguishes invoices from credit memos etc. TransactionClass is NOT queryable, so class filtering is client-side.'
);
-- AR-P4 Credit Memo
INSERT INTO kg_entity VALUES (
  'CreditMemo', 'CustomerTransactionId', 'TransactionNumber',
  '/fscmRestApi/resources/11.13.18.05/receivablesCreditMemos',
  'An accounts-receivable (sell-side) credit memo raised against a customer. Same object model as ReceivablesInvoice but EnteredAmount is normally NEGATIVE (a credit) and the status field is CreditMemoStatus. Top-level resource: listable without a parent id. Recent-first ordering (orderBy=TransactionDate:desc) and limit are done server-side. NOTE: sign is not guaranteed - the demo pod has at least one POSITIVE, Incomplete memo, so never assume EnteredAmount < 0.'
);
-- AR-P5 Account Credit Memo (prompt 7)
INSERT INTO kg_entity VALUES (
  'AccountCreditMemo', 'CreditMemoId', 'CreditMemoNumber',
  '/fscmRestApi/resources/11.13.18.05/receivablesCustomerAccountActivities/{AccountId}/child/creditMemos',
  'A credit memo on a customer account, reached as a child of CustomerAccount. NOT the same as CreditMemo: different id space (CreditMemoId, small ints, vs CustomerTransactionId) and different fields (CreditMemoNumber/CreditMemoDate/TotalOriginalAmount/TotalBalanceAmount/AvailableAmount/InstallmentId vs TransactionNumber/TransactionDate/EnteredAmount). This is the installment/payment-schedule projection - a sibling of CustomerTransaction - whereas CreditMemo is the top-level transaction projection. The collection holds credit memos ONLY, so no class filtering is needed. Recent-first ordering (orderBy=CreditMemoDate:desc) and limit are done server-side; ?fields= projection also works here. Amounts are normally negative but sign is not guaranteed. The row does NOT echo AccountId - the join key is the URL path.'
);
-- AR-P5 Account Receipt (prompt 8)
INSERT INTO kg_entity VALUES (
  'AccountReceipt', 'StandardReceiptId', 'ReceiptNumber',
  '/fscmRestApi/resources/11.13.18.05/receivablesCustomerAccountActivities/{AccountId}/child/standardReceipts',
  'A standard receipt (cash received from a customer) on a customer account, reached as a child of CustomerAccount. Distinct from an AR invoice (money owed) and a credit memo (a credit issued). NOTE the SAME receipts are reachable via the TOP-LEVEL /standardReceipts resource, but with a DIFFERENT projection: this child has ProcessStatus and omits CustomerName/CustomerAccountNumber/bank fields, while the top-level has Status plus customer and remittance columns. Field names do NOT carry across - naming ProcessStatus in a fields= list against the top-level resource 500s it. The two also disagree on count (child 1559 vs top-level-by-account 1386 on the anchor); do not treat them as interchangeable. StandardReceiptId MIXES ID WIDTHS - backfilled rows are small ints (130), recent ones large (300000313660599); never infer anything from magnitude. Recent-first ordering (orderBy=ReceiptDate:desc) and limit are server-side; fields= works here. CustomerSite is present but NULLABLE. The row does NOT echo AccountId - the join key is the URL path.'
);

-- AR-P5 Prompt 9: Account Receipt Application
INSERT INTO kg_entity VALUES (
  'AccountReceiptApplication', 'ApplicationId', 'ReceiptNumber',
  '/fscmRestApi/resources/11.13.18.05/receivablesCustomerAccountActivities/{AccountId}/child/standardReceiptApplications',
  'A receipt application (cash-to-invoice matching) on a customer account. Reached as a child of CustomerAccount. PRE-JOINED: carries both the receipt side (StandardReceiptId, ReceiptNumber, ReceiptMethod) and the transaction side (ReferenceTransactionId, ReferenceTransactionNumber, ReferenceTransactionStatus) on one record. PK is ApplicationId, a sixth AR id space. TRAP: the newest rows are unapplied cash (ApplicationStatus=''Unapplied'') with all ReferenceTransaction fields null; Spire filters client-side for ApplicationStatus=''Applied''. orderBy=ApplicationDate:desc works server-side; no second fetch is needed. The row does NOT echo AccountId - the join key is the URL path.'
);

-- Prompt 13: Top-level StandardReceipt entity (cash receipts rootable via account number and site)
INSERT INTO kg_entity VALUES (
  'StandardReceipt', 'StandardReceiptId', 'ReceiptNumber',
  '/fscmRestApi/resources/11.13.18.05/standardReceipts',
  'A cash receipt (payment from a customer) at the top level. Rootable via CustomerAccountNumber (server-side filter) and CustomerSite (client-side filter). Distinct from AccountReceipt (the per-account child) – this projection includes CustomerName, CustomerAccountNumber, and bank fields. `fields=` is broken on this endpoint (500s), so fetch full rows and discard client-side.'
);

PROMPT Seeded kg_entity (22 rows).

-- ============================================================
-- STEP 4: Seed kg_entity_field
-- ============================================================

-- Supplier
INSERT INTO kg_entity_field VALUES ('Supplier', 'SupplierId',     'canonical_id', 'numeric', 'System primary key. Used to join to PurchaseOrder.SupplierId.');
INSERT INTO kg_entity_field VALUES ('Supplier', 'SupplierNumber', 'display_id',   'string',  'Human-readable identifier (e.g. ''1252''). Used to join to Invoice.SupplierNumber.');
INSERT INTO kg_entity_field VALUES ('Supplier', 'Supplier',       'display_name', 'string',  'Display name of the supplier.');
INSERT INTO kg_entity_field VALUES ('Supplier', 'Status',         'status',       'string',  'e.g. ACTIVE.');
-- COL-03 / layer 3: WHO columns. Curl-confirmed on /suppliers 2026-08-04 —
-- all four exist, return real values (CreatedBy e.g. ''CALVIN.ROTH''), and
-- survive fields= projection on this endpoint. Projectable, display-only:
-- the user asks to SEE these, not filter on them. (A creation-date FILTER
-- exists separately in kg_entity_filter; these are the projection side.)
INSERT INTO kg_entity_field VALUES ('Supplier', 'CreatedBy',      'projection', 'string',   'User who created the record (e.g. ''CALVIN.ROTH''). WHO column; projectable, display-only.');
INSERT INTO kg_entity_field VALUES ('Supplier', 'CreationDate',   'projection', 'iso_date', 'When the record was created. WHO column; projectable, display-only. Distinct from the creation-date FILTER.');
INSERT INTO kg_entity_field VALUES ('Supplier', 'LastUpdatedBy',  'projection', 'string',   'User who last updated the record. WHO column; projectable, display-only. May be an email or a login id.');
INSERT INTO kg_entity_field VALUES ('Supplier', 'LastUpdateDate', 'projection', 'iso_date', 'When the record was last updated. WHO column; projectable, display-only.');

-- Invoice
INSERT INTO kg_entity_field VALUES ('Invoice', 'InvoiceId',       'canonical_id', 'numeric', 'System primary key.');
INSERT INTO kg_entity_field VALUES ('Invoice', 'InvoiceNumber',   'display_id',   'string',  'Human-readable identifier.');
INSERT INTO kg_entity_field VALUES ('Invoice', 'InvoiceDate',     'date',         'iso_date','Used for date-window filters.');
INSERT INTO kg_entity_field VALUES ('Invoice', 'InvoiceAmount',   'amount',       'numeric', NULL);
INSERT INTO kg_entity_field VALUES ('Invoice', 'InvoiceCurrency', 'projection',   'string',  NULL);
INSERT INTO kg_entity_field VALUES ('Invoice', 'PaidStatus',      'status',       'string',  'Display string values like ''Paid'', ''Unpaid''.');
INSERT INTO kg_entity_field VALUES ('Invoice', 'ApprovalStatus',  'status',       'string',  'Display string values like ''Not required'', ''Approved''.');
INSERT INTO kg_entity_field VALUES ('Invoice', 'SupplierNumber',  'reference',    'string',  'Join key back to Supplier.SupplierNumber. Note: not SupplierId on this endpoint.');

-- PurchaseOrder
INSERT INTO kg_entity_field VALUES ('PurchaseOrder', 'POHeaderId',   'canonical_id', 'numeric', 'System primary key.');
INSERT INTO kg_entity_field VALUES ('PurchaseOrder', 'OrderNumber',  'display_id',   'string',  'Human-readable identifier.');
INSERT INTO kg_entity_field VALUES ('PurchaseOrder', 'StatusCode',   'status',       'string',  'Code values: OPEN, CLOSED, INCOMPLETE, CANCELED. Use for filtering.');
INSERT INTO kg_entity_field VALUES ('PurchaseOrder', 'Status',       'projection',   'string',  'Human-readable form of StatusCode. Display only; do not filter on this.');
INSERT INTO kg_entity_field VALUES ('PurchaseOrder', 'SupplierId',   'reference',    'numeric', 'Join key back to Supplier.SupplierId. Note: SupplierId on this endpoint, not SupplierNumber.');
INSERT INTO kg_entity_field VALUES ('PurchaseOrder', 'BuyerId',      'reference',    'numeric', 'Join key to Buyer.PersonId on /hcmRestApi/.../publicWorkers (cross-pillar).');
INSERT INTO kg_entity_field VALUES ('PurchaseOrder', 'Ordered',      'amount',       'numeric', 'PO total amount (excluding tax).');
INSERT INTO kg_entity_field VALUES ('PurchaseOrder', 'CurrencyCode', 'projection',   'string',  NULL);

-- Buyer
INSERT INTO kg_entity_field VALUES ('Buyer', 'PersonId',     'canonical_id', 'numeric', 'Same numeric value as PurchaseOrder.BuyerId.');
INSERT INTO kg_entity_field VALUES ('Buyer', 'DisplayName',  'display_name', 'string',  NULL);
INSERT INTO kg_entity_field VALUES ('Buyer', 'WorkEmail',    'projection',   'string',  NULL);
INSERT INTO kg_entity_field VALUES ('Buyer', 'Username',     'projection',   'string',  NULL);
INSERT INTO kg_entity_field VALUES ('Buyer', 'PersonNumber', 'display_id',   'string',  NULL);

-- Address
INSERT INTO kg_entity_field VALUES ('Address', 'CountryCode', 'projection', 'string', 'ISO-2 country code (e.g. ''US''). Match against vocab_kind=''country'' canonical_value.');
INSERT INTO kg_entity_field VALUES ('Address', 'Country',     'projection', 'string', 'Full country name (e.g. ''United States''). Match against vocab_kind=''country'' term forms.');

-- PurchaseOrder (P2: money projection fields)
INSERT INTO kg_entity_field VALUES ('PurchaseOrder', 'Total',    'projection', 'numeric', 'PO total amount including tax. Display/projection only.');
INSERT INTO kg_entity_field VALUES ('PurchaseOrder', 'TotalTax', 'projection', 'numeric', 'Tax portion of the PO total. Display/projection only.');

-- PurchaseOrderLine (P2)
INSERT INTO kg_entity_field VALUES ('PurchaseOrderLine', 'POLineId',    'canonical_id', 'numeric', 'System primary key for the line.');
INSERT INTO kg_entity_field VALUES ('PurchaseOrderLine', 'LineNumber',  'display_id',   'numeric', 'Human-readable line number within the PO (the "Line" column).');
INSERT INTO kg_entity_field VALUES ('PurchaseOrderLine', 'OrderNumber', 'reference',    'string',  'Parent PO OrderNumber; present in the line body. Join key back to PurchaseOrder.OrderNumber.');
INSERT INTO kg_entity_field VALUES ('PurchaseOrderLine', 'Description', 'projection',   'string',  'Line description.');
INSERT INTO kg_entity_field VALUES ('PurchaseOrderLine', 'Category',    'projection',   'string',  'Purchasing category display name (e.g. "Marketing General").');
INSERT INTO kg_entity_field VALUES ('PurchaseOrderLine', 'Quantity',    'projection',   'numeric', 'Ordered quantity for the line.');
INSERT INTO kg_entity_field VALUES ('PurchaseOrderLine', 'Price',       'projection',   'numeric', 'Unit price for the line.');
INSERT INTO kg_entity_field VALUES ('PurchaseOrderLine', 'Ordered',     'amount',       'numeric', 'Line extended amount (excluding tax).');
INSERT INTO kg_entity_field VALUES ('PurchaseOrderLine', 'TotalTax',    'amount',       'numeric', 'Tax on the line (the "Tax" column).');
INSERT INTO kg_entity_field VALUES ('PurchaseOrderLine', 'Total',       'amount',       'numeric', 'Line total including tax.');
INSERT INTO kg_entity_field VALUES ('PurchaseOrderLine', 'StatusCode',  'status',       'string',  'Code form of the line status (e.g. CLOSED).');
INSERT INTO kg_entity_field VALUES ('PurchaseOrderLine', 'Status',      'projection',   'string',  'Human-readable line status. Display only.');

-- POSchedule (P3). Flat-endpoint field names: ScheduleStatus (not Status),
-- Amount (not Ordered), ShipToLocation (not ShipToLocationCode).
INSERT INTO kg_entity_field VALUES ('POSchedule', 'LineLocationId',        'canonical_id', 'numeric', 'System primary key for the schedule (a.k.a. line-location).');
INSERT INTO kg_entity_field VALUES ('POSchedule', 'ScheduleNumber',        'display_id',   'numeric', 'Human-readable schedule number within the line.');
INSERT INTO kg_entity_field VALUES ('POSchedule', 'POHeaderId',            'reference',    'numeric', 'Parent PO id; present in the schedule body. Join key back to PurchaseOrder.POHeaderId.');
INSERT INTO kg_entity_field VALUES ('POSchedule', 'POLineId',              'reference',    'numeric', 'Parent PO line id; carried for the distributions phase (nested path needs it).');
INSERT INTO kg_entity_field VALUES ('POSchedule', 'OrderNumber',           'reference',    'string',  'Parent PO OrderNumber; present in the schedule body.');
INSERT INTO kg_entity_field VALUES ('POSchedule', 'LineNumber',            'projection',   'numeric', 'Parent line number (display).');
INSERT INTO kg_entity_field VALUES ('POSchedule', 'ShipToLocation',        'projection',   'string',  'Ship-to location name (e.g. "Seattle"). Flat-endpoint name.');
INSERT INTO kg_entity_field VALUES ('POSchedule', 'RequestedDeliveryDate', 'date',         'iso_date','Requested/need-by delivery date for the schedule.');
INSERT INTO kg_entity_field VALUES ('POSchedule', 'Quantity',              'projection',   'numeric', 'Scheduled quantity.');
INSERT INTO kg_entity_field VALUES ('POSchedule', 'UOM',                   'projection',   'string',  'Unit of measure.');
INSERT INTO kg_entity_field VALUES ('POSchedule', 'Amount',                'amount',       'numeric', 'Scheduled amount. Flat-endpoint name (nested view calls it Ordered).');
INSERT INTO kg_entity_field VALUES ('POSchedule', 'ScheduleStatus',        'status',       'string',  'Schedule status (e.g. Closed). Flat-endpoint name (nested view calls it Status).');

-- Contact (P4). Supplier contacts child. Phone/fax fields exist on the
-- endpoint but are empty on this pod's data; register the useful display
-- fields now (record-all, register-subset).
INSERT INTO kg_entity_field VALUES ('Contact', 'SupplierContactId',         'canonical_id', 'numeric', 'System primary key for the supplier contact.');
INSERT INTO kg_entity_field VALUES ('Contact', 'ContactName',               'display_name', 'string',  'Display name, last-first (e.g. "Kim, John").');
INSERT INTO kg_entity_field VALUES ('Contact', 'FirstName',                 'projection',   'string',  'Contact first name.');
INSERT INTO kg_entity_field VALUES ('Contact', 'LastName',                  'projection',   'string',  'Contact last name.');
INSERT INTO kg_entity_field VALUES ('Contact', 'Email',                     'projection',   'string',  'Contact email address.');
INSERT INTO kg_entity_field VALUES ('Contact', 'JobTitle',                  'projection',   'string',  'Contact job title (often null on this pod).');
INSERT INTO kg_entity_field VALUES ('Contact', 'Status',                    'status',       'string',  'Contact status (e.g. ACTIVE).');
INSERT INTO kg_entity_field VALUES ('Contact', 'AdministrativeContactFlag', 'projection',   'boolean', 'True marks the primary/administrative contact.');

-- PODistribution (P3b). Deepest PO child: distribution accounts.
INSERT INTO kg_entity_field VALUES ('PODistribution', 'PODistributionId',     'canonical_id', 'numeric', 'System primary key for the distribution.');
INSERT INTO kg_entity_field VALUES ('PODistribution', 'DistributionNumber',   'display_id',   'numeric', 'Distribution number within the schedule.');
INSERT INTO kg_entity_field VALUES ('PODistribution', 'POHeaderId',           'reference',    'numeric', 'Parent PO id (carried in the body).');
INSERT INTO kg_entity_field VALUES ('PODistribution', 'POLineId',             'reference',    'numeric', 'Parent PO line id (carried in the body).');
INSERT INTO kg_entity_field VALUES ('PODistribution', 'OrderNumber',          'reference',    'string',  'Parent PO OrderNumber (carried in the body).');
INSERT INTO kg_entity_field VALUES ('PODistribution', 'ScheduleNumber',       'projection',   'numeric', 'Parent schedule number.');
INSERT INTO kg_entity_field VALUES ('PODistribution', 'POChargeAccount',      'projection',   'string',  'Charge account code combination.');
INSERT INTO kg_entity_field VALUES ('PODistribution', 'POAccrualAccount',     'projection',   'string',  'Accrual account code combination.');
INSERT INTO kg_entity_field VALUES ('PODistribution', 'POVarianceAccount',    'projection',   'string',  'Variance account code combination.');
INSERT INTO kg_entity_field VALUES ('PODistribution', 'DeliverToLocationCode','projection',   'string',  'Deliver-to location (e.g. "Seattle").');
INSERT INTO kg_entity_field VALUES ('PODistribution', 'Percentage',           'projection',   'numeric', 'Percentage of the schedule allocated to this distribution.');
INSERT INTO kg_entity_field VALUES ('PODistribution', 'Quantity',             'projection',   'numeric', 'Distributed quantity.');
INSERT INTO kg_entity_field VALUES ('PODistribution', 'Ordered',              'amount',       'numeric', 'Distributed amount (excluding tax).');
INSERT INTO kg_entity_field VALUES ('PODistribution', 'Total',                'amount',       'numeric', 'Distributed total (including tax).');
INSERT INTO kg_entity_field VALUES ('PODistribution', 'Status',               'projection',   'string',  'Distribution status (e.g. Delivered).');
INSERT INTO kg_entity_field VALUES ('PODistribution', 'StatusCode',           'status',       'string',  'Code form of the distribution status.');

-- Invoice (P5). The PO number is on the invoice HEADER and filters
-- server-side; it is the join key to PurchaseOrder.OrderNumber (a string,
-- not POHeaderId) — consistent with invoices joining on SupplierNumber.
INSERT INTO kg_entity_field VALUES ('Invoice', 'PurchaseOrderNumber', 'reference', 'string', 'PO number the invoice was raised against (e.g. "162034"). Join key to PurchaseOrder.OrderNumber. Filters server-side via q=PurchaseOrderNumber.');

-- POSchedule (P5): received-vs-ordered. Fusion records what was actually
-- received/billed on the schedule row, alongside the ordered Quantity and
-- Amount. This is the source for "how much of PO X was received" — the
-- receipts resources are unusable here (receivingTransactions 403;
-- receivingReceipts needs a receipt number; receivingReceiptRequests is a
-- staging interface with no PO reference).
INSERT INTO kg_entity_field VALUES ('POSchedule', 'ReceivedQuantity', 'projection', 'numeric', 'Quantity actually received against the schedule. Compare with Quantity (ordered).');
INSERT INTO kg_entity_field VALUES ('POSchedule', 'BilledQuantity',   'projection', 'numeric', 'Quantity invoiced against the schedule.');
INSERT INTO kg_entity_field VALUES ('POSchedule', 'ShippedQuantity',  'projection', 'numeric', 'Quantity shipped against the schedule.');
INSERT INTO kg_entity_field VALUES ('POSchedule', 'AcceptedQuantity', 'projection', 'numeric', 'Quantity accepted against the schedule.');
INSERT INTO kg_entity_field VALUES ('POSchedule', 'ReceivedAmount',   'amount',     'numeric', 'Amount received against the schedule. Compare with Amount (ordered).');
INSERT INTO kg_entity_field VALUES ('POSchedule', 'BilledAmount',     'amount',     'numeric', 'Amount invoiced against the schedule.');


-- ReceivablesInvoice (AR-P2)
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoice', 'CustomerTransactionId', 'canonical_id', 'numeric', 'System primary key. Queryable via q=CustomerTransactionId=<id> (unquoted, numeric). The by_id fetcher relies on this.');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoice', 'TransactionNumber',    'display_id',   'string',  'Human-readable invoice number (e.g. ''61765'').');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoice', 'BillToCustomerName',   'projection',   'string',  'Bill-to customer display name. NOT queryable via q= on this endpoint (confirmed live). Display only.');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoice', 'BillToCustomerNumber', 'reference',    'string',  'Bill-to customer number. NOT queryable via q= here. Join key to CustomerAccount.AccountNumber for the account-activity path.');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoice', 'InvoiceCurrencyCode',  'projection',   'string',  'Invoice currency (e.g. ''GBP'').');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoice', 'EnteredAmount',        'amount',       'numeric', 'Invoice amount in entered currency.');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoice', 'InvoiceBalanceAmount', 'amount',       'numeric', 'Open balance remaining on the invoice; 0 means paid.');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoice', 'TransactionDate',      'date',         'iso_date','Invoice/transaction date.');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoice', 'DueDate',              'date',         'iso_date','Payment due date.');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoice', 'AccountingDate',       'date',         'iso_date','Accounting (GL) date.');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoice', 'InvoiceStatus',        'status',       'string',  'Display status (e.g. ''Complete''). Display only.');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoice', 'TransactionType',      'projection',   'string',  'Transaction type (e.g. ''Invoice''). Distinguishes invoice vs credit memo within receivablesTransactions.');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoice', 'TransactionSource',    'projection',   'string',  'Transaction source (e.g. ''Manual'', ''Receivables Import'').');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoice', 'BusinessUnit',         'projection',   'string',  'Owning business unit (e.g. ''UK Business Unit'').');

-- ReceivablesInvoiceLine (AR-P2)
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoiceLine', 'CustomerTransactionLineId',   'canonical_id', 'numeric', 'System primary key for the line.');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoiceLine', 'LineNumber',                  'display_id',   'numeric', 'Human-readable line number within the invoice.');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoiceLine', 'Description',                 'projection',   'string',  'Line description (e.g. ''Consultation'').');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoiceLine', 'Quantity',                    'projection',   'numeric', 'Line quantity.');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoiceLine', 'UnitSellingPrice',            'projection',   'numeric', 'Unit selling price for the line.');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoiceLine', 'LineAmount',                  'amount',       'numeric', 'Line extended amount.');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoiceLine', 'UnitOfMeasure',               'projection',   'string',  'Unit of measure (often null on this pod).');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoiceLine', 'ItemNumber',                  'projection',   'string',  'Item number (often null on this pod).');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoiceLine', 'TaxClassificationCode',       'projection',   'string',  'Tax classification code (often null).');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoiceLine', 'TaxExemptionHandling',        'projection',   'string',  'Tax exemption handling (e.g. ''Standard'').');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoiceLine', 'LineAmountIncludesTax',       'projection',   'string',  'Whether the line amount includes tax (e.g. ''Use Tax Rate Code'').');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoiceLine', 'AssessableValue',             'amount',       'numeric', 'Assessable value for tax.');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoiceLine', 'TransacationBusinessCategory','projection',   'string',  'Transaction business category (e.g. ''Sales Transaction''). NOTE: Oracle misspells this field as ''TransacationBusinessCategory'' (sic); must be requested with the typo exactly.');

-- AR-P3 DFF
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoiceTransactionDFF', 'CustomerTrxId',                'canonical_id', 'numeric', 'Parent invoice id echoed on the DFF child. Pod spells it CustomerTrxId (short form), not CustomerTransactionId.');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoiceTransactionDFF', '__FLEX_Context',              'projection',   'string',  'The descriptive-flexfield context name (e.g. ''DOO''). Set on this pod but with no populated segment columns behind it.');
INSERT INTO kg_entity_field VALUES ('ReceivablesInvoiceTransactionDFF', '__FLEX_Context_DisplayValue', 'projection',   'string',  'Display value of the DFF context (null on this pod).');


-- ReceivablesTaxLine (AR-P3)
INSERT INTO kg_entity_field VALUES ('ReceivablesTaxLine', 'CustomerTransactionLineId', 'canonical_id', 'numeric', 'System primary key for the TAX line (e.g. 112) - distinct from the parent invoice-line id.');
INSERT INTO kg_entity_field VALUES ('ReceivablesTaxLine', 'TaxLineNumber',             'display_id',   'numeric', 'Human-readable tax-line number within the invoice line (e.g. 1, 2).');
INSERT INTO kg_entity_field VALUES ('ReceivablesTaxLine', 'Tax',                       'projection',   'string',  'The tax type (e.g. ''STATE'', ''COUNTY'').');
INSERT INTO kg_entity_field VALUES ('ReceivablesTaxLine', 'TaxRate',                   'projection',   'numeric', 'The tax rate percentage (e.g. 6.5).');
INSERT INTO kg_entity_field VALUES ('ReceivablesTaxLine', 'TaxRateCode',               'projection',   'string',  'The tax rate code (e.g. ''STD'').');
INSERT INTO kg_entity_field VALUES ('ReceivablesTaxLine', 'TaxRegimeCode',             'projection',   'string',  'The tax regime (e.g. ''US SALES AND USE TAX'').');
INSERT INTO kg_entity_field VALUES ('ReceivablesTaxLine', 'TaxStatusCode',             'projection',   'string',  'The tax status (e.g. ''STANDARD'').');
INSERT INTO kg_entity_field VALUES ('ReceivablesTaxLine', 'TaxJurisdictionCode',       'projection',   'string',  'The tax jurisdiction code (e.g. ''CO-050850000'').');
INSERT INTO kg_entity_field VALUES ('ReceivablesTaxLine', 'TaxAmount',                 'amount',       'numeric', 'The tax amount charged for this tax line.');
INSERT INTO kg_entity_field VALUES ('ReceivablesTaxLine', 'TaxableAmount',             'amount',       'numeric', 'The amount the tax was computed on.');
INSERT INTO kg_entity_field VALUES ('ReceivablesTaxLine', 'TaxInclusiveIndicator',     'projection',   'string',  'Whether the line amount already includes this tax (''Yes''/''No'').');
INSERT INTO kg_entity_field VALUES ('ReceivablesTaxLine', 'TaxPointDate',              'projection',   'string',  'The tax point date (ISO date).');


-- CustomerAccount (AR-P2b)
INSERT INTO kg_entity_field VALUES ('CustomerAccount', 'AccountId',                      'canonical_id', 'numeric', 'System primary key for the account. The join key traversed to CustomerTransaction (carried in the child URL path).');
INSERT INTO kg_entity_field VALUES ('CustomerAccount', 'AccountNumber',                  'display_id',   'string',  'Human-readable account number (e.g. ''26370'').');
INSERT INTO kg_entity_field VALUES ('CustomerAccount', 'CustomerName',                   'display_name', 'string',  'Customer display name. Queryable via q=CustomerName= (exact) on this endpoint; the resolve point for customer-scoped queries.');
INSERT INTO kg_entity_field VALUES ('CustomerAccount', 'CustomerId',                     'reference',    'numeric', 'Customer party id.');
INSERT INTO kg_entity_field VALUES ('CustomerAccount', 'TotalOpenReceivablesForAccount', 'amount',       'numeric', 'Open receivables balance for the account (can be negative when the customer is in credit).');
INSERT INTO kg_entity_field VALUES ('CustomerAccount', 'TotalTransactionsDueForAccount', 'amount',       'numeric', 'Total transactions due for the account.');

-- CustomerTransaction (AR-P2b)
INSERT INTO kg_entity_field VALUES ('CustomerTransaction', 'TransactionId',          'canonical_id', 'numeric', 'System primary key for the transaction (small int; distinct from ReceivablesInvoice.CustomerTransactionId).');
INSERT INTO kg_entity_field VALUES ('CustomerTransaction', 'TransactionNumber',      'display_id',   'string',  'Human-readable transaction number.');
INSERT INTO kg_entity_field VALUES ('CustomerTransaction', 'TransactionClass',       'projection',   'string',  'Transaction class (e.g. ''Invoice''). NOT queryable server-side; filter client-side to keep invoices.');
INSERT INTO kg_entity_field VALUES ('CustomerTransaction', 'TransactionDate',        'date',         'iso_date','Transaction date.');
INSERT INTO kg_entity_field VALUES ('CustomerTransaction', 'PaymentScheduleDueDate', 'date',         'iso_date','Due date of the payment schedule.');
INSERT INTO kg_entity_field VALUES ('CustomerTransaction', 'TotalOriginalAmount',    'amount',       'numeric', 'Original transaction amount.');
INSERT INTO kg_entity_field VALUES ('CustomerTransaction', 'TotalBalanceAmount',     'amount',       'numeric', 'Open balance on the transaction; 0 is paid. A positive balance is an open invoice (used by the open-only filter, deferred to a later phase).');
INSERT INTO kg_entity_field VALUES ('CustomerTransaction', 'InstallmentStatus',      'status',       'string',  'Installment status (e.g. ''Closed'').');
-- AR-P4 Credit Memo
INSERT INTO kg_entity_field VALUES ('CreditMemo', 'CustomerTransactionId', 'canonical_id', 'numeric', 'System primary key for the credit memo.');
INSERT INTO kg_entity_field VALUES ('CreditMemo', 'TransactionNumber',     'display_id',   'string',  'Human-readable credit memo number (e.g. ''11001'').');
INSERT INTO kg_entity_field VALUES ('CreditMemo', 'TransactionDate',       'date',         'iso_date','Credit memo date. Server-side orderBy sorts on this for recent-first.');
INSERT INTO kg_entity_field VALUES ('CreditMemo', 'EnteredAmount',         'amount',       'numeric', 'Credit memo amount in entered currency. Normally NEGATIVE (a credit); sign is not guaranteed on this pod.');
INSERT INTO kg_entity_field VALUES ('CreditMemo', 'CreditMemoCurrency',    'projection',   'string',  'Credit memo currency (e.g. ''USD'').');
INSERT INTO kg_entity_field VALUES ('CreditMemo', 'CreditMemoStatus',      'status',       'string',  'Credit memo status (e.g. ''Complete'', ''Incomplete'').');
INSERT INTO kg_entity_field VALUES ('CreditMemo', 'BillToCustomerName',    'projection',   'string',  'Bill-to customer display name.');
INSERT INTO kg_entity_field VALUES ('CreditMemo', 'BillToCustomerNumber',  'reference',    'string',  'Bill-to customer number.');

-- AR-P5 AccountCreditMemo (prompt 7) — the per-account child projection.
-- Field names differ from CreditMemo throughout; see the entity note.
INSERT INTO kg_entity_field VALUES ('AccountCreditMemo', 'CreditMemoId',        'canonical_id', 'numeric', 'System primary key for the account credit memo. A SMALL int, and a DIFFERENT id space from CreditMemo.CustomerTransactionId - do not conflate.');
INSERT INTO kg_entity_field VALUES ('AccountCreditMemo', 'CreditMemoNumber',    'display_id',   'string',  'Human-readable credit memo number (e.g. ''1358582'').');
INSERT INTO kg_entity_field VALUES ('AccountCreditMemo', 'CreditMemoDate',      'date',         'iso_date','Credit memo date. Server-side orderBy sorts on this for recent-first.');
INSERT INTO kg_entity_field VALUES ('AccountCreditMemo', 'TransactionClass',    'projection',   'string',  'Memo class (e.g. ''On Account Credit Memo''). Informational only - the collection holds credit memos only, so no class filtering is needed.');
INSERT INTO kg_entity_field VALUES ('AccountCreditMemo', 'TotalOriginalAmount', 'amount',       'numeric', 'Original memo amount. Normally NEGATIVE (a credit); sign is not guaranteed.');
INSERT INTO kg_entity_field VALUES ('AccountCreditMemo', 'TotalBalanceAmount',  'amount',       'numeric', 'Remaining balance. Non-zero on Open memos, 0 on Closed ones.');
INSERT INTO kg_entity_field VALUES ('AccountCreditMemo', 'AvailableAmount',     'amount',       'numeric', 'Amount still available to apply.');
INSERT INTO kg_entity_field VALUES ('AccountCreditMemo', 'CreditMemoStatus',    'status',       'string',  'Memo status (''Open'' or ''Closed'').');
INSERT INTO kg_entity_field VALUES ('AccountCreditMemo', 'CreditMemoCurrency',  'projection',   'string',  'Memo currency (e.g. ''USD'').');
INSERT INTO kg_entity_field VALUES ('AccountCreditMemo', 'BillToSiteNumber',    'reference',    'string',  'Bill-to site. NOTE this carries a site NAME (e.g. ''Santa Clara''), not a number, despite the field name.');

-- AR-P5 AccountReceipt (prompt 8) — the per-account receipts child.
-- Field names differ from the top-level /standardReceipts; see the entity note.
INSERT INTO kg_entity_field VALUES ('AccountReceipt', 'StandardReceiptId', 'canonical_id', 'numeric', 'System primary key for the receipt. MIXES WIDTHS in one collection - small ints (130) for backfilled demo rows, large (300000313660599) for recent ones. Both valid; never infer anything from the magnitude.');
INSERT INTO kg_entity_field VALUES ('AccountReceipt', 'ReceiptNumber',     'display_id',   'string',  'Human-readable receipt number (e.g. ''498949'', or ''PA-2026-000145'' on recent rows).');
INSERT INTO kg_entity_field VALUES ('AccountReceipt', 'ReceiptDate',       'date',         'iso_date','Receipt date. Server-side orderBy sorts on this for recent-first.');
INSERT INTO kg_entity_field VALUES ('AccountReceipt', 'Amount',            'amount',       'numeric', 'Receipt amount (cash received). Positive.');
INSERT INTO kg_entity_field VALUES ('AccountReceipt', 'Currency',          'projection',   'string',  'Receipt currency (e.g. ''USD'').');
INSERT INTO kg_entity_field VALUES ('AccountReceipt', 'ReceiptMethod',     'projection',   'string',  'How the payment arrived (e.g. ''Lockbox'', ''Check (Directly/No Remit)'').');
INSERT INTO kg_entity_field VALUES ('AccountReceipt', 'State',             'status',       'string',  'Application state (''Applied'' or ''Unapplied''). Unapplied means cash received but not yet matched to an invoice - the newest rows on the demo pod are Unapplied, which is real cash, not an error.');
INSERT INTO kg_entity_field VALUES ('AccountReceipt', 'ProcessStatus',     'status',       'string',  'Processing status (''Open'' or ''Closed''). NOTE this field exists ONLY on the child - the top-level /standardReceipts calls its equivalent ''Status''. Do not name it in a fields= list against the top-level resource.');
INSERT INTO kg_entity_field VALUES ('AccountReceipt', 'UnappliedAmount',   'amount',       'numeric', 'Portion of the receipt not yet applied to a transaction. 0 on fully applied receipts.');
INSERT INTO kg_entity_field VALUES ('AccountReceipt', 'CustomerSite',      'reference',    'string',  'Bill-to site name (e.g. ''Santa Clara''). NULLABLE and sparsely populated - any grouping or filtering on it must handle nulls. NOT queryable on this child (400s).');
INSERT INTO kg_entity_field VALUES ('AccountReceipt', 'BusinessUnit',      'projection',   'string',  'Owning business unit (e.g. ''US1 Business Unit'').');

-- AR-P5 Prompt 9: Account Receipt Application fields
INSERT INTO kg_entity_field VALUES ('AccountReceiptApplication', 'ApplicationId',              'canonical_id', 'numeric', 'System primary key for the application. A sixth AR id space.');
INSERT INTO kg_entity_field VALUES ('AccountReceiptApplication', 'StandardReceiptId',          'reference',    'numeric', 'The receipt''s StandardReceiptId (numeric).');
INSERT INTO kg_entity_field VALUES ('AccountReceiptApplication', 'ReceiptNumber',              'display_id',   'string',  'Human-readable receipt number.');
INSERT INTO kg_entity_field VALUES ('AccountReceiptApplication', 'ReceiptMethod',              'projection',   'string',  'How the payment arrived (e.g. Lockbox).');
INSERT INTO kg_entity_field VALUES ('AccountReceiptApplication', 'ReferenceTransactionId',     'reference',    'numeric', 'The transaction''s ReferenceTransactionId (the payment schedule id, a small int). Null only when unapplied, but we filter those out.');
INSERT INTO kg_entity_field VALUES ('AccountReceiptApplication', 'ReferenceTransactionNumber', 'projection',   'string',  'The transaction number.');
INSERT INTO kg_entity_field VALUES ('AccountReceiptApplication', 'ReferenceTransactionStatus', 'projection',   'string',  'Transaction status (e.g. Open, Closed).');
INSERT INTO kg_entity_field VALUES ('AccountReceiptApplication', 'ApplicationAmount',          'amount',       'numeric', 'The amount applied to the transaction.');
INSERT INTO kg_entity_field VALUES ('AccountReceiptApplication', 'ApplicationDate',            'date',         'iso_date','Application date.');
INSERT INTO kg_entity_field VALUES ('AccountReceiptApplication', 'ApplicationStatus',          'status',       'string',  'Application status (''Applied'' or ''Unapplied''). We filter client-side to keep only ''Applied''.');
INSERT INTO kg_entity_field VALUES ('AccountReceiptApplication', 'EnteredCurrency',            'projection',   'string',  'Application currency.');
INSERT INTO kg_entity_field VALUES ('AccountReceiptApplication', 'CustomerSite',               'reference',    'string',  'Customer site (often null).');

-- Prompt 13: StandardReceipt fields (top-level /standardReceipts projection)
INSERT INTO kg_entity_field VALUES ('StandardReceipt', 'StandardReceiptId', 'canonical_id', 'numeric', 'System primary key for the receipt.');
INSERT INTO kg_entity_field VALUES ('StandardReceipt', 'ReceiptNumber',     'display_id',   'string',  'Human-readable receipt number.');
INSERT INTO kg_entity_field VALUES ('StandardReceipt', 'ReceiptDate',       'date',         'iso_date','Receipt date.');
INSERT INTO kg_entity_field VALUES ('StandardReceipt', 'Amount',            'amount',       'numeric', 'Receipt amount (cash received).');
INSERT INTO kg_entity_field VALUES ('StandardReceipt', 'Currency',          'projection',   'string',  'Receipt currency (e.g. USD).');
INSERT INTO kg_entity_field VALUES ('StandardReceipt', 'ReceiptMethod',     'projection',   'string',  'How the payment arrived (e.g. Lockbox).');
INSERT INTO kg_entity_field VALUES ('StandardReceipt', 'Status',            'status',       'string',  'Top-level status (Cleared, etc.).');
INSERT INTO kg_entity_field VALUES ('StandardReceipt', 'CustomerName',      'projection',   'string',  'Customer display name.');
INSERT INTO kg_entity_field VALUES ('StandardReceipt', 'CustomerAccountNumber', 'reference', 'string', 'Customer account number. Server-filterable via q=CustomerAccountNumber=.');
INSERT INTO kg_entity_field VALUES ('StandardReceipt', 'CustomerSite',      'reference',    'string',  'Customer site (e.g. Santa Clara). Client-side filter.');
INSERT INTO kg_entity_field VALUES ('StandardReceipt', 'RemittanceBankName', 'projection',  'string',  'Bank name for the remittance.');
INSERT INTO kg_entity_field VALUES ('StandardReceipt', 'RemittanceBankBranch', 'projection', 'string', 'Bank branch.');
INSERT INTO kg_entity_field VALUES ('StandardReceipt', 'RemittanceBankAccountNumber', 'projection', 'string', 'Bank account number.');

PROMPT Seeded kg_entity_field (198 rows).

-- ============================================================
-- STEP 5: Seed kg_edge
-- ============================================================

INSERT INTO kg_edge VALUES (
  'HAS_INVOICE', 'Supplier', 'Invoice', 'SupplierNumber', 'SupplierNumber', 'one_to_many',
  'join_only',
  'GET /fscmRestApi/.../invoices?q=SupplierNumber=''{supplier.SupplierNumber}'' (optionally with InvoiceDate filter).',
  'The invoices endpoint exposes SupplierNumber, not SupplierId. Use SupplierNumber here even though SupplierId is the canonical id on Supplier. Composite q= clauses are unreliable on this pod; apply additional filters client-side after over-fetch.',
  NULL
);

INSERT INTO kg_edge VALUES (
  'HAS_ADDRESS', 'Supplier', 'Address', 'SupplierId', 'SupplierId', 'one_to_many',
  'join_only',
  'GET /fscmRestApi/.../suppliers?expand=addresses. Address is a child resource; addresses come back inline as supplier.addresses[].',
  'There is no standalone Address endpoint. Always use expand=addresses on the supplier query. Country filtering is client-side: iterate supplier.addresses[] and match on CountryCode or Country.',
  NULL
);

INSERT INTO kg_edge VALUES (
  'HAS_PURCHASE_ORDER', 'Supplier', 'PurchaseOrder', 'SupplierId', 'SupplierId', 'one_to_many',
  'join_only',
  'GET /fscmRestApi/.../purchaseOrders?q=SupplierId={supplier.SupplierId} (optionally with status filter).',
  'Use SupplierId (numeric), not SupplierNumber, on this endpoint. This is the asymmetry with HAS_INVOICE. Composite q= clauses are unreliable; apply status filter client-side after over-fetch.',
  NULL
);

INSERT INTO kg_edge VALUES (
  'ASSIGNED_TO', 'PurchaseOrder', 'Buyer', 'BuyerId', 'PersonId', 'many_to_one',
  'join_only',
  'GET /hcmRestApi/.../publicWorkers?q=PersonId={po.BuyerId}',
  'CROSS-PILLAR: PO is in FSCM; Buyer is in HCM. There is no /fscmRestApi/.../buyers endpoint on this pod. BuyerId on a PO equals PersonId on publicWorkers.',
  NULL
);

INSERT INTO kg_edge VALUES (
  'HAS_SITE', 'Supplier', 'Site', 'SupplierId', 'SupplierId', 'one_to_many',
  'first_filter_only',
  'GET /fscmRestApi/.../suppliers/{supplier.SupplierId}/child/sites?q=ProcurementBU=''<value>''. The BU filter IS reliable server-side on this child (confirmed on pod: a matching value returns the site, a non-existent value returns empty).',
  'Per-supplier child call; there is no bulk expand=sites on this pod (silently ignored). One HTTP call per parent supplier, so the scan window is bounded (SITE_SCAN_LIMIT in the tool).',
  NULL
);

INSERT INTO kg_edge VALUES (
  'HAS_CLASSIFICATION', 'Supplier', 'Classification', 'SupplierId', 'SupplierId', 'one_to_many',
  'first_filter_only',
  'GET /fscmRestApi/.../suppliers/{supplier.SupplierId}/child/businessClassifications?q=Classification=''<value>''. The Classification filter IS reliable server-side on this child (confirmed on pod: a matching value returns the row, a non-existent value returns empty).',
  'Per-supplier child call; one HTTP call per parent supplier, so the scan window is bounded. Status cannot be AND-combined with Classification in one q= (composite quirk); Classification-only is sent server-side.',
  NULL
);

INSERT INTO kg_edge VALUES (
  'HAS_LINE', 'PurchaseOrder', 'PurchaseOrderLine', 'POHeaderId', 'POHeaderId', 'one_to_many',
  'join_only',
  'GET /fscmRestApi/.../purchaseOrders/{po.POHeaderId}/child/lines. A plain expansion: fetch all lines for the PO. No server filter needed; ?fields= projection works on the child.',
  'Per-PO child call, one HTTP call per PO. The line body carries POHeaderId and OrderNumber, so the parent id is present in each row (unlike the supplier children, which omit it). Expansion edge (join_only), not a keep-parent existence filter like HAS_SITE / HAS_CLASSIFICATION.',
  NULL
);

INSERT INTO kg_edge VALUES (
  'HAS_SCHEDULE', 'PurchaseOrder', 'POSchedule', 'POHeaderId', 'POHeaderId', 'one_to_many',
  'join_only',
  'GET /fscmRestApi/.../purchaseOrderSchedules?q=POHeaderId=<po.POHeaderId>. A plain expansion via the FLAT schedules collection: one server-side call per PO, single-clause q= on POHeaderId. ?fields= projection works.',
  'One call per PO against the flat purchaseOrderSchedules endpoint (not a nested child path). Expansion edge (join_only), same shape as HAS_LINE. The schedule row carries POHeaderId, POLineId and LineLocationId.',
  NULL
);

INSERT INTO kg_edge VALUES (
  'HAS_CONTACT', 'Supplier', 'Contact', 'SupplierId', 'SupplierId', 'one_to_many',
  'join_only',
  'GET /fscmRestApi/.../suppliers/{supplier.SupplierId}/child/contacts. A plain expansion: fetch all contacts for the supplier. One HTTP call per supplier; ?fields= projection works.',
  'Per-supplier child call, one HTTP call per supplier. The contact body omits the parent SupplierId (join key is the URL path), same as HAS_SITE / HAS_CLASSIFICATION. Expansion edge (join_only), include-only.',
  NULL
);

INSERT INTO kg_edge VALUES (
  'HAS_DISTRIBUTION', 'POSchedule', 'PODistribution', 'LineLocationId', 'LineLocationId', 'one_to_many',
  'join_only',
  'GET /purchaseOrders/{POHeaderId}/child/lines/{POLineId}/child/schedules/{LineLocationId}/child/distributions. Deepest nested path; needs three ids from the parent schedule row.',
  'Multi-field iteration edge: the distributions path needs POHeaderId, POLineId and LineLocationId, all carried on each POSchedule row. iter_fields_json maps the tool args to those parent fields. from_join_field stays LineLocationId (the primary id) so single-field readers still work.',
  '{"po_header_id": "POHeaderId", "po_line_id": "POLineId", "line_location_id": "LineLocationId"}'
);


-- AR-P2
INSERT INTO kg_edge VALUES (
  'HAS_AR_LINE', 'ReceivablesInvoice', 'ReceivablesInvoiceLine', 'CustomerTransactionId', 'CustomerTransactionId', 'one_to_many',
  'join_only',
  'GET /fscmRestApi/.../receivablesInvoices/{invoice.CustomerTransactionId}/child/receivablesInvoiceLines. A plain expansion: fetch all lines for the invoice. No server filter needed; ?fields= projection works on the child (mind the TransacationBusinessCategory misspelling).',
  'Per-invoice child call, one HTTP call per invoice. Same shape as the PO HAS_LINE edge (join_only expansion). The parent id is carried in the URL path, not required from the line body.',
  NULL
);


-- AR-P3
INSERT INTO kg_edge VALUES (
  'HAS_TAX_LINE', 'ReceivablesInvoiceLine', 'ReceivablesTaxLine', 'CustomerTransactionLineId', 'CustomerTransactionLineId', 'one_to_many',
  'join_only',
  'GET /fscmRestApi/.../receivablesInvoices/{invoice.CustomerTransactionId}/child/receivablesInvoiceLines/{line.CustomerTransactionLineId}/child/receivablesInvoiceLineTaxLines. The tax child needs TWO ids per call - the parent invoice id AND the parent line id - both carried on the line row (the line projection includes CustomerTransactionId for this reason). Same multi-field pattern as HAS_DISTRIBUTION, but two ids rather than three.',
  'Multi-field iteration edge: the tax-lines path needs CustomerTransactionId (invoice) and CustomerTransactionLineId (line), both on each line row. iter_fields_json maps the tool args to those parent fields. from_join_field stays CustomerTransactionLineId (the primary id) so single-field readers still work; dedupe is on that id.',
  '{"customer_transaction_id": "CustomerTransactionId", "line_id": "CustomerTransactionLineId"}'
);


-- AR-P3 DFF
INSERT INTO kg_edge VALUES (
  'HAS_TRANSACTION_DFF', 'ReceivablesInvoice', 'ReceivablesInvoiceTransactionDFF', 'CustomerTransactionId', 'CustomerTrxId', 'one_to_many',
  'join_only',
  'GET /fscmRestApi/.../receivablesInvoices/{invoice.CustomerTransactionId}/child/receivablesInvoiceTransactionDFF. A plain expansion: fetch the invoice''s TransactionDFF row. No server filter needed. The parent id is carried in the URL path, not required from the child body. Note the child echoes the parent id as CustomerTrxId (short spelling); the to_join_field records that reality, but the fetch is path-based so it is declarative only (same as HAS_AR_LINE).',
  'Per-invoice child call, one HTTP call per invoice. Same shape as HAS_AR_LINE (join_only expansion). Normally returns a single DFF row.',
  NULL
);


-- AR-P2b
INSERT INTO kg_edge VALUES (
  'HAS_CUSTOMER_TRANSACTION', 'CustomerAccount', 'CustomerTransaction', 'AccountId', 'AccountId', 'one_to_many',
  'join_only',
  'GET /fscmRestApi/.../receivablesCustomerAccountActivities/{account.AccountId}/child/transactionPaymentSchedules. Fetch the account''s transactions; keep TransactionClass=''Invoice'' client-side (not queryable). The parent AccountId is carried in the URL path.',
  'Per-account child call, one HTTP call per account. Same expansion shape as HAS_AR_LINE. Client-side Invoice-class filter in the tool; the open-balance filter (prompt 1) is deferred to a later phase.',
  NULL
);

-- AR-P5 (prompt 7)
INSERT INTO kg_edge VALUES (
  'HAS_ACCOUNT_CREDIT_MEMO', 'CustomerAccount', 'AccountCreditMemo', 'AccountId', 'AccountId', 'one_to_many',
  'join_only',
  'GET /fscmRestApi/.../receivablesCustomerAccountActivities/{account.AccountId}/child/creditMemos. Fetch the account''s credit memos, newest first (orderBy=CreditMemoDate:desc, server-side). The parent AccountId is carried in the URL path and is NOT echoed in the row body.',
  'Per-account child call, one HTTP call per account. Same expansion shape as HAS_CUSTOMER_TRANSACTION, but simpler: the collection holds credit memos only, so there is no client-side class filter and limit applies server-side as a true top-N.',
  NULL
);

-- AR-P5 (prompt 8)
INSERT INTO kg_edge VALUES (
  'HAS_ACCOUNT_RECEIPT', 'CustomerAccount', 'AccountReceipt', 'AccountId', 'AccountId', 'one_to_many',
  'join_only',
  'GET /fscmRestApi/.../receivablesCustomerAccountActivities/{account.AccountId}/child/standardReceipts. Fetch the account''s receipts, newest first (orderBy=ReceiptDate:desc, server-side). The parent AccountId is carried in the URL path and is NOT echoed in the row body.',
  'Per-account child call, one HTTP call per account. Same expansion shape as HAS_ACCOUNT_CREDIT_MEMO: the collection holds receipts only, so there is no client-side filter and limit applies server-side as a true top-N.',
  NULL
);

-- AR-P5 Prompt 9
INSERT INTO kg_edge VALUES (
  'HAS_RECEIPT_APPLICATION', 'CustomerAccount', 'AccountReceiptApplication', 'AccountId', 'AccountId', 'one_to_many',
  'join_only',
  'GET /fscmRestApi/.../receivablesCustomerAccountActivities/{account.AccountId}/child/standardReceiptApplications. Fetch the account''s receipt applications, newest first (orderBy=ApplicationDate:desc, server-side). The parent AccountId is carried in the URL path and is NOT echoed in the row body.',
  'Per-account child call, one HTTP call per account. Same expansion shape as HAS_ACCOUNT_RECEIPT, but with client-side filtering: keep only ApplicationStatus=''Applied'' (unapplied rows have null transaction side). The tool uses an over-fetch pattern (fetch_limit) because filtering discards unapplied rows.',
  NULL
);
PROMPT Seeded kg_edge (17 rows).

-- ============================================================
-- STEP 6: Seed kg_pattern (3 rows for v1.1 with F2 negation pattern)
-- ============================================================

INSERT INTO kg_pattern (pattern_name, shape, parameters, mechanics, example) VALUES (
  'status_filter',
  'Filter entities of type X to those whose status field matches a business-term-named status.',
  '[
    {"name":"X","type":"Entity","description":"The entity being filtered (e.g. PurchaseOrder)."},
    {"name":"status_field","type":"FieldName","description":"The status field on X (e.g. StatusCode)."},
    {"name":"status_term","type":"string","description":"The business term the user provided (e.g. ''open'')."}
   ]',
  '1. Look up status_term in kg_vocabulary where vocab_kind=''po_status'' to get the canonical Fusion code (e.g. ''open'' -> ''OPEN'').
2. Query X''s endpoint with q=status_field=''<canonical_value>''.
3. Note that status codes are case-sensitive in Fusion: ''OPEN'' is correct, ''Open'' is not.',
  'Open purchase orders: X=PurchaseOrder, status_field=StatusCode, status_term=''open'' -> StatusCode=''OPEN''.'
);

INSERT INTO kg_pattern (pattern_name, shape, parameters, mechanics, example) VALUES (
  'country_filter_via_address',
  'Filter parent entities by a country attribute that lives on a child resource.',
  '[
    {"name":"parent","type":"Entity","description":"The parent entity (e.g. Supplier)."},
    {"name":"child_edge","type":"Edge","description":"The edge to the child (e.g. HAS_ADDRESS)."},
    {"name":"country_term","type":"string","description":"The user''s country term (e.g. ''US'', ''United States'')."}
   ]',
  '1. Resolve country_term via kg_vocabulary where vocab_kind=''country'' to get the canonical ISO-2 code.
2. Fetch parents with the child resource expanded (e.g. GET /suppliers?expand=addresses).
3. Client-side: keep a parent if ANY child has CountryCode or Country matching the resolved value.
4. A parent with addresses in multiple countries can match multiple country filters; that is correct behavior.',
  'Suppliers in US: parent=Supplier, child_edge=HAS_ADDRESS, country_term=''US'' -> filter where any supplier.addresses[].CountryCode=''US''.'
);

INSERT INTO kg_pattern (pattern_name, shape, parameters, mechanics, example) VALUES (
  'no_child_in_N_months',
  'Filter parent entities to those with NO child of type C in the last N months on a given date field.',
  '[
    {"name":"parent","type":"Entity","description":"The parent entity (e.g. Supplier)."},
    {"name":"child_edge","type":"Edge","description":"The edge from parent to child (e.g. HAS_INVOICE)."},
    {"name":"date_field","type":"FieldName","description":"The date field on the child to compare against (e.g. InvoiceDate)."},
    {"name":"months_param","type":"int","description":"The lookback window in months (e.g. 6)."}
   ]',
  '1. Compute the cutoff date: today minus months_param months. Format as ISO YYYY-MM-DD.
2. For each parent, query the child endpoint with date_field >= cutoff.
3. A parent passes the filter if the child query returns ZERO results (negation by absence).
4. The result of this step is the FILTERED PARENT LIST, not the child list.
5. The executor implements this via Step.filter_source_when_empty=True.',
  'Suppliers with no invoices in 6 months: parent=Supplier, child_edge=HAS_INVOICE, date_field=InvoiceDate, months_param=6 -> keep suppliers where search_invoices(supplier, invoice_date_after=<6 months ago>) returns empty.'
);

PROMPT Seeded kg_pattern (3 rows).

-- ============================================================
-- STEP 7: Seed kg_vocabulary
-- ============================================================

-- country
INSERT INTO kg_vocabulary VALUES ('country', 'US', 'US', 'ISO-2 code; also the canonical value.');
INSERT INTO kg_vocabulary VALUES ('country', 'USA', 'US', '3-letter form; normalized to ISO-2.');
INSERT INTO kg_vocabulary VALUES ('country', 'United States', 'US', 'Full name.');
INSERT INTO kg_vocabulary VALUES ('country', 'United States of America', 'US', 'Full formal name.');
INSERT INTO kg_vocabulary VALUES ('country', 'UK', 'GB', 'Informal; ISO-2 is GB.');
INSERT INTO kg_vocabulary VALUES ('country', 'GB', 'GB', 'ISO-2 code.');
INSERT INTO kg_vocabulary VALUES ('country', 'United Kingdom', 'GB', 'Full name.');
INSERT INTO kg_vocabulary VALUES ('country', 'Britain', 'GB', 'Informal.');
INSERT INTO kg_vocabulary VALUES ('country', 'Great Britain', 'GB', 'Informal.');
INSERT INTO kg_vocabulary VALUES ('country', 'India', 'IN', 'Full name.');
INSERT INTO kg_vocabulary VALUES ('country', 'IN', 'IN', 'ISO-2 code.');
INSERT INTO kg_vocabulary VALUES ('country', 'Canada', 'CA', 'Full name.');
INSERT INTO kg_vocabulary VALUES ('country', 'CA', 'CA', 'ISO-2 code.');
INSERT INTO kg_vocabulary VALUES ('country', 'Australia', 'AU', 'Full name.');
INSERT INTO kg_vocabulary VALUES ('country', 'AU', 'AU', 'ISO-2 code.');
INSERT INTO kg_vocabulary VALUES ('country', 'AUS', 'AU', '3-letter form; normalized to ISO-2.');

-- field_synonym: a user term expands to one OR MORE real column names,
-- comma-joined. The parser's expand_field_synonyms splits on comma AFTER
-- the LLM, so the expansion is deterministic (COL-02 multi-field). The
-- target columns must exist on the entity as kg_entity_field rows, or
-- validate_intent will (correctly) report them as unresolved.
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'who columns', 'CreatedBy,CreationDate,LastUpdatedBy,LastUpdateDate', 'Audit/who columns -> the four who fields.');
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'who details', 'CreatedBy,CreationDate,LastUpdatedBy,LastUpdateDate', 'Synonym of who columns.');
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'audit columns', 'CreatedBy,CreationDate,LastUpdatedBy,LastUpdateDate', 'Synonym of who columns.');
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'audit fields', 'CreatedBy,CreationDate,LastUpdatedBy,LastUpdateDate', 'Synonym of who columns.');
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'creator details', 'CreatedBy,CreationDate', 'Creator subset -> who created and when.');
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'created details', 'CreatedBy,CreationDate', 'Synonym of creator details.');

-- field_synonym (single-field): legacy EBS vocabulary (COL-02, Group 2).
-- One term -> one real column (no comma). Only terms whose target is a
-- projectable kg_entity_field column and unambiguous across entities are
-- included; child-entity/filter/concept terms (vendor site, OU, shipment,
-- dist, req, party, SLA) are NOT field synonyms and are omitted.
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'vendor', 'Supplier', 'Legacy EBS: vendor -> Supplier.');
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'vendor name', 'Supplier', 'Legacy EBS: vendor name -> Supplier.');
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'vendor number', 'SupplierNumber', 'Legacy EBS: vendor number -> SupplierNumber.');
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'trx', 'TransactionNumber', 'Legacy EBS: trx -> TransactionNumber (AR).');
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'trx number', 'TransactionNumber', 'Legacy EBS: trx number -> TransactionNumber (AR).');

-- field_synonym (single-field): field-level synonyms (COL-02, Group 3).
-- Only globally-safe mappings (same column name across the entities that
-- carry them). Ambiguous terms are omitted: 'price' (Price on PO vs
-- UnitSellingPrice on AR), 'amount' (Ordered on PO vs LineAmount on AR),
-- and 'terms' (no PaymentTerms column in the KG). Those need entity-scoped
-- synonyms, a separate mechanism change.
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'creation date', 'CreationDate', 'Field synonym -> CreationDate.');
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'created date', 'CreationDate', 'Field synonym -> CreationDate.');
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'date created', 'CreationDate', 'Field synonym -> CreationDate.');
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'last updated', 'LastUpdateDate', 'Field synonym -> LastUpdateDate.');
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'modified', 'LastUpdateDate', 'Field synonym -> LastUpdateDate.');
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'changed on', 'LastUpdateDate', 'Field synonym -> LastUpdateDate.');
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'update date', 'LastUpdateDate', 'Field synonym -> LastUpdateDate.');
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'qty', 'Quantity', 'Field synonym -> Quantity (PO/AR lines).');
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'uom', 'UnitOfMeasure', 'Field synonym -> UnitOfMeasure (AR lines).');
INSERT INTO kg_vocabulary VALUES ('field_synonym', 'unit of measure', 'UnitOfMeasure', 'Field synonym -> UnitOfMeasure (AR lines).');

-- po_status
INSERT INTO kg_vocabulary VALUES ('po_status', 'open',      'OPEN',       'Default conversational synonym.');
INSERT INTO kg_vocabulary VALUES ('po_status', 'active',    'OPEN',       'Synonym for open.');
INSERT INTO kg_vocabulary VALUES ('po_status', 'closed',    'CLOSED',     NULL);
INSERT INTO kg_vocabulary VALUES ('po_status', 'completed', 'CLOSED',     'Synonym for closed.');
INSERT INTO kg_vocabulary VALUES ('po_status', 'incomplete','INCOMPLETE', NULL);
INSERT INTO kg_vocabulary VALUES ('po_status', 'draft',     'INCOMPLETE', 'Synonym for incomplete.');
INSERT INTO kg_vocabulary VALUES ('po_status', 'canceled',  'CANCELED',   NULL);
INSERT INTO kg_vocabulary VALUES ('po_status', 'cancelled', 'CANCELED',   'British spelling.');
-- P6: the remaining seven StatusCodes, found by running the status
-- breakdown over all 3,362 POs. The KG knew four of eleven, so "POs on
-- hold" / "rejected POs" / "POs pending approval" could not be asked at
-- all. Note the pod's values use SPACES, not underscores.
INSERT INTO kg_vocabulary VALUES ('po_status', 'rejected',   'REJECTED',   NULL);
INSERT INTO kg_vocabulary VALUES ('po_status', 'withdrawn',  'WITHDRAWN',  NULL);
INSERT INTO kg_vocabulary VALUES ('po_status', 'on hold',    'ON HOLD',    'Pod value has a space, not an underscore.');
INSERT INTO kg_vocabulary VALUES ('po_status', 'held',       'ON HOLD',    'Synonym for on hold.');
INSERT INTO kg_vocabulary VALUES ('po_status', 'pending approval',  'PENDING APPROVAL',  'Pod value has a space, not an underscore.');
INSERT INTO kg_vocabulary VALUES ('po_status', 'awaiting approval', 'PENDING APPROVAL',  'Synonym for pending approval.');
INSERT INTO kg_vocabulary VALUES ('po_status', 'unapproved',        'PENDING APPROVAL',  'Synonym for pending approval.');
INSERT INTO kg_vocabulary VALUES ('po_status', 'pending signature', 'PENDING SIGNATURE', 'Pod value has a space, not an underscore.');
-- The three closed-ish states are kept DISTINCT rather than collapsed
-- under 'closed'. They are genuinely different: CLOSED FOR RECEIVING
-- means no more receipts while invoicing may continue. Consequence:
-- "closed POs" resolves to CLOSED only (2,732 POs), NOT the 223 in the
-- other two states. Whether a procurement user means all three by
-- "closed" is a question for an SME — collapsing them here would decide
-- it silently.
INSERT INTO kg_vocabulary VALUES ('po_status', 'closed for receiving', 'CLOSED FOR RECEIVING', 'Distinct from CLOSED: no more receipts, invoicing may continue.');
INSERT INTO kg_vocabulary VALUES ('po_status', 'closed for invoicing', 'CLOSED FOR INVOICING', 'Distinct from CLOSED: no more invoicing, receiving may continue.');

-- supplier_status (distinct from po_status; Supplier.Status is ACTIVE/INACTIVE)
INSERT INTO kg_vocabulary VALUES ('supplier_status', 'active',   'ACTIVE',   'Supplier is active.');
INSERT INTO kg_vocabulary VALUES ('supplier_status', 'inactive', 'INACTIVE', 'Supplier is inactive.');

-- supplier_business_relationship (Supplier.BusinessRelationship; pod values
-- are the display strings 'Spend Authorized' / 'Prospective')
INSERT INTO kg_vocabulary VALUES ('supplier_business_relationship', 'spend authorized', 'Spend Authorized', 'Supplier is spend-authorized.');
INSERT INTO kg_vocabulary VALUES ('supplier_business_relationship', 'prospective',      'Prospective',      'Supplier is prospective.');

-- supplier_site_bu (ProcurementBU on supplier sites; pod values are the
-- display strings, e.g. 'US1 Business Unit'. Representative set seeded;
-- more exist on the pod and can be added when a prompt needs them.)
INSERT INTO kg_vocabulary VALUES ('supplier_site_bu', 'us1',           'US1 Business Unit',           'Procurement BU on supplier sites.');
INSERT INTO kg_vocabulary VALUES ('supplier_site_bu', 'uk',            'UK Business Unit',            'Procurement BU on supplier sites.');
INSERT INTO kg_vocabulary VALUES ('supplier_site_bu', 'france',        'France Business Unit',        'Procurement BU on supplier sites.');
INSERT INTO kg_vocabulary VALUES ('supplier_site_bu', 'germany',       'Germany Business Unit',       'Procurement BU on supplier sites.');
INSERT INTO kg_vocabulary VALUES ('supplier_site_bu', 'italy',         'Italy Business Unit',         'Procurement BU on supplier sites.');
INSERT INTO kg_vocabulary VALUES ('supplier_site_bu', 'china',         'China Business Unit',         'Procurement BU on supplier sites.');
INSERT INTO kg_vocabulary VALUES ('supplier_site_bu', 'japan',         'Japan Business Unit',         'Procurement BU on supplier sites.');
INSERT INTO kg_vocabulary VALUES ('supplier_site_bu', 'india',         'India Business Unit',         'Procurement BU on supplier sites.');
INSERT INTO kg_vocabulary VALUES ('supplier_site_bu', 'sweden',        'Sweden Business Unit',        'Procurement BU on supplier sites.');
INSERT INTO kg_vocabulary VALUES ('supplier_site_bu', 'healthcare us', 'Healthcare US Business Unit', 'Procurement BU on supplier sites.');

-- supplier_classification (Classification on supplier businessClassifications;
-- pod values are the display strings, e.g. 'Small Business'. All values seen
-- across the first 50 suppliers are seeded.)
INSERT INTO kg_vocabulary VALUES ('supplier_classification', 'small business',                 'Small Business',                  'Business classification on supplier.');
INSERT INTO kg_vocabulary VALUES ('supplier_classification', 'woman owned',                    'Woman Owned',                     'Business classification on supplier.');
INSERT INTO kg_vocabulary VALUES ('supplier_classification', 'minority owned',                 'Minority Owned',                  'Business classification on supplier.');
INSERT INTO kg_vocabulary VALUES ('supplier_classification', 'veteran owned',                  'Veteran Owned',                   'Business classification on supplier.');
INSERT INTO kg_vocabulary VALUES ('supplier_classification', 'hub zone',                       'Hub Zone',                        'Business classification on supplier.');
INSERT INTO kg_vocabulary VALUES ('supplier_classification', 'iso 14001',                      'ISO 14001',                       'Business classification on supplier.');
INSERT INTO kg_vocabulary VALUES ('supplier_classification', 'general liability insurance',    'General Liability Insurance',     'Business classification on supplier.');
INSERT INTO kg_vocabulary VALUES ('supplier_classification', 'workers compensation insurance', 'Workers'' Compensation Insurance', 'Business classification on supplier.');
INSERT INTO kg_vocabulary VALUES ('supplier_classification', 'kbis',                           'Kbis',                            'Business classification on supplier.');

-- entity_synonym
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'supplier',         'Supplier',      NULL);
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'vendor',           'Supplier',      'Synonym.');
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'invoice',          'Invoice',       NULL);
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'bill',             'Invoice',       'Synonym.');
-- AR-P2: AR-invoice synonyms. Explicit two-word phrases so they never shadow the
-- AP 'invoice'/'bill' mappings above. Bare 'AR' and bare 'invoice' deliberately omitted.
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'AR invoice',           'ReceivablesInvoice', 'Accounts-receivable (sell-side) invoice. Distinct from ''invoice''/''bill'' which map to the AP Invoice.');
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'receivables invoice',  'ReceivablesInvoice', 'AR invoice.');
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'AR invoices',          'ReceivablesInvoice', 'Plural form.');
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'receivables invoices', 'ReceivablesInvoice', 'Plural form.');
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'purchase order',   'PurchaseOrder', NULL);
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'PO',               'PurchaseOrder', 'Acronym.');
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'order',            'PurchaseOrder', 'Ambiguous; resolved to PO in this domain.');
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'buyer',            'Buyer',         NULL);
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'purchasing agent', 'Buyer',         'Synonym.');
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'agent',            'Buyer',         'Synonym (in purchasing context).');

-- relationship_phrase
INSERT INTO kg_vocabulary VALUES ('relationship_phrase', 'supplier has invoice',     'HAS_INVOICE',        NULL);
INSERT INTO kg_vocabulary VALUES ('relationship_phrase', 'invoice for supplier',     'HAS_INVOICE',        NULL);
INSERT INTO kg_vocabulary VALUES ('relationship_phrase', 'supplier in country',      'HAS_ADDRESS',        'Composite phrase.');
INSERT INTO kg_vocabulary VALUES ('relationship_phrase', 'country supplier',         'HAS_ADDRESS',        'Composite phrase.');
INSERT INTO kg_vocabulary VALUES ('relationship_phrase', 'supplier has PO',          'HAS_PURCHASE_ORDER', NULL);
INSERT INTO kg_vocabulary VALUES ('relationship_phrase', 'PO for supplier',          'HAS_PURCHASE_ORDER', NULL);
INSERT INTO kg_vocabulary VALUES ('relationship_phrase', 'buyer assigned to PO',     'ASSIGNED_TO',        NULL);
INSERT INTO kg_vocabulary VALUES ('relationship_phrase', 'PO buyer',                 'ASSIGNED_TO',        NULL);

COMMIT;

INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'schedule', 'POSchedule', 'PO shipment schedule.');
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'shipment schedule', 'POSchedule', 'PO shipment schedule.');

INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'contact', 'Contact', 'Supplier contact person.');
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'contacts', 'Contact', 'Supplier contact people.');

INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'distribution', 'PODistribution', 'PO distribution account line.');
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'distributions', 'PODistribution', 'PO distribution account lines.');

-- AR-P4 Credit Memo
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'credit memo',  'CreditMemo', 'AR credit memo (sell-side).');
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'credit memos', 'CreditMemo', 'Plural form.');


-- AR-P5 (prompt 7). NOTE the bare terms 'credit memo'/'credit memos' are
-- already bound to CreditMemo (AR-P4, the top-level recent-memos list).
-- These entries add only the ACCOUNT-SCOPED forms, so a prompt naming a
-- customer routes here while a bare 'list recent credit memos' still
-- routes to CreditMemo. The parser rule carries the actual disambiguation;
-- these are the vocabulary hooks for it.
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'account credit memo',  'AccountCreditMemo', 'A credit memo on a specific customer account (AR-P5), NOT the top-level CreditMemo list.');
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'account credit memos', 'AccountCreditMemo', 'Plural form.');
-- AR-P5 (prompt 8). No collision here: no existing vocab binds 'receipt'.
-- A receipt is CASH RECEIVED (sell-side, AR) - not an AP invoice/bill and
-- not a PO receipt/receiving transaction, neither of which Spire models.
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'receipt',          'AccountReceipt', 'A payment received from a customer, on a specific account (AR-P5).');
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'receipts',         'AccountReceipt', 'Plural form.');
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'account receipt',  'AccountReceipt', 'Account-scoped form.');
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'account receipts', 'AccountReceipt', 'Plural account-scoped form.');
-- AR-P5 Prompt 9: receipt applications
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'receipt application',  'AccountReceiptApplication', 'A cash-to-invoice matching on a specific customer account (AR-P5 prompt 9).');
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'receipt applications', 'AccountReceiptApplication', 'Plural form.');
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'account receipt application',  'AccountReceiptApplication', 'Account-scoped form.');
INSERT INTO kg_vocabulary VALUES ('entity_synonym', 'account receipt applications', 'AccountReceiptApplication', 'Plural account-scoped form.');

PROMPT Seeded kg_vocabulary.

-- ============================================================
-- STEP 8: Seed kg_pattern_binding (3 rows for v1.1 with F2)
-- ============================================================

INSERT INTO kg_pattern_binding (entity_name, filter_type, pattern_name, parameter_bindings) VALUES (
  'Supplier',
  'country',
  'country_filter_via_address',
  '{"parent": "Supplier", "child_edge": "HAS_ADDRESS", "country_term_param": "country"}'
);

INSERT INTO kg_pattern_binding (entity_name, filter_type, pattern_name, parameter_bindings) VALUES (
  'PurchaseOrder',
  'status',
  'status_filter',
  '{"X": "PurchaseOrder", "status_field": "StatusCode", "status_term_param": "status"}'
);

INSERT INTO kg_pattern_binding (entity_name, filter_type, pattern_name, parameter_bindings) VALUES (
  'Supplier',
  'no_recent_invoices',
  'no_child_in_N_months',
  '{"parent": "Supplier", "child_edge": "HAS_INVOICE", "date_field": "InvoiceDate", "months_param": "months"}'
);

COMMIT;

PROMPT Seeded kg_pattern_binding (3 rows).

-- ============================================================
-- STEP 9: Seed kg_entity_tool
--
-- Maps entities to the MCP tools that fetch them.
-- filter_type='none' is the default/unfiltered fetcher.
-- ============================================================

INSERT INTO kg_entity_tool (entity_name, filter_type, mcp_tool_name, notes) VALUES (
  'Supplier',
  'none',
  'search_suppliers',
  'Default fetcher for Supplier. Handles all entity-level supplier filters (name, status, country, created date) via combined tool args.'
);

INSERT INTO kg_entity_tool (entity_name, filter_type, mcp_tool_name, notes) VALUES (
  'Invoice',
  'none',
  'search_invoices',
  'Default fetcher for Invoice. Requires a supplier (number or name); refuses if none given.'
);

INSERT INTO kg_entity_tool (entity_name, filter_type, mcp_tool_name, notes) VALUES (
  'Address',
  'none',
  'search_addresses',
  'Default fetcher for Address. Flattens supplier.addresses[] via expand=addresses. Requires a supplier or country; refuses if none given.'
);

COMMIT;

INSERT INTO kg_entity_tool (entity_name, filter_type, mcp_tool_name, notes) VALUES (
  'PurchaseOrder',
  'by_id',
  'get_purchase_order_by_id',
  'Fetches ONE purchase order by POHeaderId (the single-record path). Distinct from search_purchase_orders (which filters a collection by supplier/status). Returns None on a 404 for an unknown id (prompt "DOES-NOT-EXIST" error case).'
);

INSERT INTO kg_entity_tool (entity_name, filter_type, mcp_tool_name, notes) VALUES (
  'PurchaseOrder',
  'none',
  'search_purchase_orders',
  'Default fetcher for PurchaseOrder — the collection search. Handles the entity-level filters that are not by_id (created_before, created_since, and any future PO list filter), stacking their args like the Supplier default fetcher does. P2 made PurchaseOrder rootable via its by_id fetcher alone and deferred this row; P6''s date filters made it necessary, because Block 1 falls back to (entity, ''none'') for any filter without its own dedicated tool and that fallback had nothing to find.'
);

INSERT INTO kg_entity_tool (entity_name, filter_type, mcp_tool_name, notes) VALUES (
  'PurchaseOrder',
  'lifecycle_status',
  'get_purchase_order_lifecycle_status',
  'Reconciles ONE purchase order end to end: ordered vs received vs invoiced vs paid, across six resources (PO header, schedules, invoices, invoice installments, supplier, supplier site). Returns a single po_lifecycle_status record - NOT a list. Distinct from get_purchase_order_by_id (header only) and from compare_orders_to_invoices (many POs, two legs). Takes po_number (OrderNumber, the number printed on the order), never POHeaderId. Computes lifecycle_stage, responsible_team, risk with risk_reasons, and recommended_action; the synthesizer must COPY these, never re-derive them. paid_state is TRI-STATE and can be ''unknown'' when billing exists with no matched AP invoice - in that case fully_paid and remaining_to_pay are BOTH null and must not be read as false or zero.'
);


INSERT INTO kg_entity_tool (entity_name, filter_type, mcp_tool_name, notes) VALUES (
  'ReceivablesInvoice',
  'by_id',
  'get_receivables_invoice_by_id',
  'Fetches ONE AR invoice by CustomerTransactionId via q= on the collection. Single-path (no TransactionNumber fallback - no P2 prompt needs it). Returns None when the id matches nothing.'
);


INSERT INTO kg_entity_tool (entity_name, filter_type, mcp_tool_name, notes) VALUES (
  'CustomerAccount',
  'by_customer_name',
  'get_customer_account_by_name',
  'Resolves a customer name to their account(s) via q=CustomerName= (exact) on receivablesCustomerAccountActivities. Returns all matching accounts as a list; the edge traversal iterates them.'
);
-- AR-P4 Credit Memo
INSERT INTO kg_entity_tool (entity_name, filter_type, mcp_tool_name, notes) VALUES (
  'CreditMemo',
  'none',
  'list_receivables_credit_memos',
  'Default fetcher for CreditMemo. Lists recent credit memos (orderBy=TransactionDate:desc, server-side) up to limit. No filters. The total credit value (raw sum of EnteredAmount) is layered on by the server wrapper.'
);

-- Prompt 13: StandardReceipt entity tool (default fetcher)
INSERT INTO kg_entity_tool (entity_name, filter_type, mcp_tool_name, notes) VALUES (
  'StandardReceipt',
  'none',
  'search_standard_receipts',
  'Default fetcher for StandardReceipt. Accepts customer_name (resolved to an account number inside the tool) and customer_site (client-side). REFUSES to run unscoped - the planner guards for this before dispatch.'
);
PROMPT Seeded kg_entity_tool (10 rows).

-- ============================================================
-- STEP 10: Seed kg_edge_tool
--
-- Maps edges to the MCP tools that traverse them.
-- HAS_ADDRESS deliberately has no row: address data is bundled
-- with search_suppliers_by_country (via expand=addresses).
-- Absence of a row signals to the planner that this edge is
-- not independently traversable.
-- ============================================================

INSERT INTO kg_edge_tool (edge_name, mcp_tool_name, notes) VALUES (
  'HAS_INVOICE',
  'search_invoices',
  'Takes supplier_number (or supplier_name) + optional invoice_date_after.'
);

INSERT INTO kg_edge_tool (edge_name, mcp_tool_name, notes) VALUES (
  'HAS_PURCHASE_ORDER',
  'search_purchase_orders',
  'Takes supplier_id (or supplier_name) + optional status.'
);

INSERT INTO kg_edge_tool (edge_name, mcp_tool_name, notes) VALUES (
  'ASSIGNED_TO',
  'get_buyer',
  'Takes buyer_id. Cross-pillar: maps BuyerId (FSCM) to PersonId (HCM).'
);

INSERT INTO kg_edge_tool (edge_name, mcp_tool_name, notes) VALUES (
  'HAS_SITE',
  'search_suppliers_by_site_bu',
  'Takes business_unit (exact ProcurementBU display string). Walks each parent supplier to its sites child, keeps the parent when a site in that BU exists (keep-parent-when-nonempty).'
);

INSERT INTO kg_edge_tool (edge_name, mcp_tool_name, notes) VALUES (
  'HAS_CLASSIFICATION',
  'search_suppliers_by_classification',
  'Takes classification (exact Classification display string). Walks each parent supplier to its businessClassifications child, keeps the parent when a matching classification exists (keep-parent-when-nonempty).'
);

COMMIT;

INSERT INTO kg_edge_tool (edge_name, mcp_tool_name, notes) VALUES (
  'HAS_LINE',
  'get_purchase_order_lines',
  'Takes po_header_id. Plain expansion: returns the PO''s lines as a ToolResult. No filter, no keep-parent logic.'
);

INSERT INTO kg_edge_tool (edge_name, mcp_tool_name, notes) VALUES (
  'HAS_SCHEDULE',
  'get_purchase_order_schedules',
  'Takes po_header_id. Plain expansion: returns the PO''s schedules as a ToolResult via the flat purchaseOrderSchedules endpoint. No filter, no keep-parent logic.'
);

INSERT INTO kg_edge_tool (edge_name, mcp_tool_name, notes) VALUES (
  'HAS_CONTACT',
  'get_supplier_contacts',
  'Takes supplier_id. Plain expansion: returns the supplier''s contacts as a ToolResult via the contacts child. No filter, no keep-parent logic.'
);

INSERT INTO kg_edge_tool (edge_name, mcp_tool_name, notes) VALUES (
  'HAS_DISTRIBUTION',
  'get_purchase_order_distributions',
  'Takes po_header_id, po_line_id, line_location_id (multi-field iteration). Returns the schedule''s distributions as a ToolResult.'
);


INSERT INTO kg_edge_tool (edge_name, mcp_tool_name, notes) VALUES (
  'HAS_AR_LINE',
  'get_receivables_invoice_lines',
  'Takes customer_transaction_id. Plain expansion: returns the invoice''s lines as a ToolResult. No filter, no keep-parent logic.'
);


INSERT INTO kg_edge_tool (edge_name, mcp_tool_name, notes) VALUES (
  'HAS_TAX_LINE',
  'get_receivables_invoice_tax_lines',
  'Takes customer_transaction_id and line_id. Plain single-parent expansion: returns the invoice line''s tax lines as a ToolResult. No filter, no keep-parent logic.'
);


-- AR-P3 DFF
INSERT INTO kg_edge_tool (edge_name, mcp_tool_name, notes) VALUES (
  'HAS_TRANSACTION_DFF',
  'get_receivables_invoice_transaction_dff',
  'Takes customer_transaction_id. Plain single-parent expansion: returns the invoice''s TransactionDFF row as a ToolResult. No filter, no keep-parent logic.'
);


INSERT INTO kg_edge_tool (edge_name, mcp_tool_name, notes) VALUES (
  'HAS_CUSTOMER_TRANSACTION',
  'get_customer_transactions',
  'Takes account_id. Fetches the account''s transactionPaymentSchedules, keeps TransactionClass=''Invoice'' client-side. Has an open_only flag (positive-balance filter) that is unused until the open-invoices phase.'
);

INSERT INTO kg_edge_tool (edge_name, mcp_tool_name, notes) VALUES (
  'HAS_ACCOUNT_CREDIT_MEMO',
  'get_account_credit_memos',
  'Takes account_id. Fetches the account''s creditMemos child, newest first. No client-side filter (the collection is credit memos only) and no over-fetch: orderBy and limit are both server-side, so limit is a true "N most recent".'
);

INSERT INTO kg_edge_tool (edge_name, mcp_tool_name, notes) VALUES (
  'HAS_ACCOUNT_RECEIPT',
  'get_account_receipts',
  'Takes account_id. Fetches the account''s standardReceipts child, newest first. No client-side filter (the collection is receipts only) and no over-fetch: orderBy and limit are both server-side, so limit is a true "N most recent". Returns receipts in every state - Unapplied rows are real cash, not noise.'
);

-- AR-P5 Prompt 9
INSERT INTO kg_edge_tool (edge_name, mcp_tool_name, notes) VALUES (
  'HAS_RECEIPT_APPLICATION',
  'get_account_receipt_applications',
  'Takes account_id. Fetches the account''s standardReceiptApplications child, newest first (orderBy=ApplicationDate:desc). Uses over-fetch (fetch_limit) and client-side filter to keep only ApplicationStatus=''Applied'' (unapplied rows have null transaction side).'
);

PROMPT Seeded kg_edge_tool (16 rows).

-- ============================================================
-- STEP 11: Seed kg_entity_filter
--
-- Filter definitions, formerly hardcoded in the planner.
-- mechanism='entity_level'   -> dedicated fetcher, uses tool_arg_name.
-- mechanism='edge_traversal' -> walks to target_entity via kg_filter_type.
--
-- For entity_level filters, query_style/filter_field/filter_op describe
-- HOW the fetcher applies the filter:
--   query_style='server_q'    -> send a single-clause q= to Fusion.
--   query_style='client_side' -> over-fetch, then match filter_field.
-- filter_op is LIKE, >=, or equals. Edge-traversal rows leave these null.
-- ============================================================

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'Supplier', 'country', 'entity_level', 'country', 'country', NULL, NULL, NULL, NULL, 'client_side', 'Country', 'equals',
  'Country lives on the addresses child; over-fetch with expand=addresses and match client-side.'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'Supplier', 'status', 'entity_level', 'status', 'supplier_status', NULL, NULL, NULL, NULL, 'client_side', 'Status', 'equals',
  'Supplier ACTIVE/INACTIVE. Server-side q= on Status is unreliable on this pod; over-fetch and match client-side.'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'Supplier', 'business_relationship', 'entity_level', 'business_relationship', 'supplier_business_relationship', NULL, NULL, NULL, NULL, 'client_side', 'BusinessRelationship', 'equals',
  'Supplier Spend Authorized/Prospective. Server-side q= works on this field, but applied client-side to keep it combinable (only one server q= clause is reliable per call).'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'Supplier', 'name_fragment', 'entity_level', 'supplier_name_contains', NULL, NULL, NULL, NULL, NULL, 'server_q', 'Supplier', 'LIKE',
  'Name substring match. Single-clause q=Supplier LIKE ''%value%'' is reliable server-side.'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, tool_arg_name_hi, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'Supplier', 'created_date', 'entity_level', 'created_from', 'created_to', NULL, NULL, NULL, NULL, NULL, 'server_q', 'CreationDate', '>=',
  'Creation-date range. Lower bound via q=CreationDate >= ''x'' server-side; upper bound filtered client-side (composite q= fails on this pod).'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, tool_arg_name_hi, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'Invoice', 'invoice_date', 'entity_level', 'invoice_date_after', 'invoice_date_before', NULL, NULL, NULL, NULL, NULL, 'server_q', 'InvoiceDate', '>=',
  'Invoice-date range. Lower bound via q=InvoiceDate >= ''x'' server-side; upper bound client-side.'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, tool_arg_name_hi, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'Invoice', 'invoice_amount', 'entity_level', 'amount_min', 'amount_max', NULL, NULL, NULL, NULL, NULL, 'client_side', 'InvoiceAmount', 'range',
  'Invoice-amount range. Both bounds filtered client-side against InvoiceAmount.'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'Supplier', 'has_open_PO', 'edge_traversal', NULL, NULL, 'PurchaseOrder', 'status', 'po_status', 'open', NULL, NULL, NULL,
  'Edge filter: supplier has an open PO. Implicit status=open resolved via po_status vocab.'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'Supplier', 'has_no_recent_invoices', 'edge_traversal', NULL, NULL, 'Invoice', 'no_recent_invoices', NULL, NULL, NULL, NULL, NULL,
  'Edge filter: supplier has no invoices in N months. Value is explicit ({months: N}).'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'Supplier', 'has_invoice_over_amount', 'edge_traversal', NULL, NULL, 'Invoice', 'has_invoice_over_amount', NULL, NULL, NULL, NULL, NULL,
  'Edge filter: supplier has at least one invoice at/over an amount. Value is the explicit numeric threshold; routed to the child invoice call as amount_min (keep-parent-when-nonempty).'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'Supplier', 'has_site_in_bu', 'edge_traversal', NULL, 'supplier_site_bu', 'Site', 'has_site_in_bu', NULL, NULL, NULL, NULL, NULL,
  'Edge filter: supplier has at least one site in a given ProcurementBU. Value is the canonical BU display string (resolved via supplier_site_bu vocab); routed to the child sites call as business_unit (keep-parent-when-nonempty). Mirror of has_invoice_over_amount, but the value is a vocab string, not a number.'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'Supplier', 'has_classification', 'edge_traversal', NULL, 'supplier_classification', 'Classification', 'has_classification', NULL, NULL, NULL, NULL, NULL,
  'Edge filter: supplier has at least one business classification matching a value. Value is the canonical Classification display string (resolved via supplier_classification vocab); routed to the child businessClassifications call as classification (keep-parent-when-nonempty). Mirror of has_site_in_bu.'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'Invoice', 'supplier', 'entity_level', 'supplier', NULL, NULL, NULL, NULL, NULL, 'server_q', 'SupplierNumber', 'equals',
  'Invoice-by-supplier. Value is a supplier reference; the planner routes an all-digit value to supplier_number, otherwise supplier_name. Required for Invoice queries.'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'Address', 'supplier', 'entity_level', 'supplier', NULL, NULL, NULL, NULL, NULL, 'server_q', 'SupplierNumber', 'equals',
  'Address-by-supplier. Value is a supplier reference; planner routes all-digit to supplier_number, else supplier_name. One of supplier/country required for Address queries.'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'Address', 'country', 'entity_level', 'country', 'country', NULL, NULL, NULL, NULL, 'client_side', 'Country', 'equals',
  'Address-by-country. Matched client-side against each address CountryCode/Country. One of supplier/country required for Address queries.'
);

COMMIT;

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'PurchaseOrder', 'by_id', 'entity_level', 'po_header_id', NULL, NULL, NULL, NULL, NULL, 'server_q', 'POHeaderId', 'equals',
  'Fetch one PO by POHeaderId via the single-record path /purchaseOrders/{id}. Dedicated fetcher get_purchase_order_by_id; returns None on 404.'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'PurchaseOrder', 'lifecycle_status', 'entity_level', 'po_number', NULL, NULL, NULL, NULL, NULL, 'server_q', 'OrderNumber', 'equals',
  'Full lifecycle reconciliation for ONE PO, selected by OrderNumber (not POHeaderId - by_id is the other filter and takes that). Choose this filter when the question asks whether a PO has been received, invoiced or paid; what stage it is at or who owns the next action; why it is still open or where it is blocked; or for a summary of a single PO covering supplier setup through payment. Choose by_id instead when only the header is wanted, and the default fetcher when several POs are being listed or filtered. Returns one record with the four amounts, three remainders, per-schedule detail, supplier and site setup, holds, risk and a recommended action.'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'Invoice', 'purchase_order', 'entity_level', 'purchase_order', NULL, NULL, NULL, NULL, NULL, 'server_q', 'PurchaseOrderNumber', 'equals',
  'Invoices raised against a PO. Value is the PO NUMBER (e.g. "162034"), not POHeaderId — invoices carry PurchaseOrderNumber on the header and it filters server-side (single clause). Most selective invoice filter, so it wins the server q= clause.'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'PurchaseOrder', 'created_before', 'entity_level', 'created_before', NULL, NULL, NULL, NULL, NULL, 'server_q', 'CreationDate', '<',
  'POs created BEFORE a date — the bound a "stale POs / older than N months" question needs. Filters server-side. NOTE: CreationDate, not OrderDate — OrderDate is projectable but NOT queryable on this pod (HTTP 400). Two rows (created_before / created_since) rather than one range row: the KG shape is one row = one op, and the two are genuinely different questions.'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'PurchaseOrder', 'created_since', 'entity_level', 'created_since', NULL, NULL, NULL, NULL, NULL, 'server_q', 'CreationDate', '>=',
  'POs created ON OR AFTER a date. Filters server-side. Both bounds work standalone on this pod but cannot be composited (single-clause rule), so one goes to the server and the other is filtered client-side.'
);


INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'ReceivablesInvoice', 'by_id', 'entity_level', 'customer_transaction_id', NULL, NULL, NULL, NULL, NULL, 'server_q', 'CustomerTransactionId', 'equals',
  'Fetch one AR invoice by CustomerTransactionId via q= on the collection (confirmed queryable). Dedicated fetcher get_receivables_invoice_by_id; returns None when the id matches nothing (collection returns empty items, not 404).'
);


INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'CustomerAccount', 'by_customer_name', 'entity_level', 'customer_name', NULL, NULL, NULL, NULL, NULL, 'server_q', 'CustomerName', 'equals',
  'Resolve a customer account by exact CustomerName via q= (queryable on this endpoint, unlike the AR-invoice customer fields). Dedicated fetcher get_customer_account_by_name; returns a list of matching accounts.'
);

-- Prompt 13: StandardReceipt filters
--
-- NO account_number FILTER. There used to be one, and it was a live
-- crash: search_standard_receipts takes (customer_name, customer_site,
-- limit) and has NO account_number parameter, so 'receipts for account
-- 26360' built a tool_arg the tool rejects --
--   TypeError: got an unexpected keyword argument 'account_number'
-- The tool moved to name-resolution (it resolves customer_name to an
-- account number itself) and this row was never retired with it. No
-- prompt set covered it, so nothing surfaced it.
--
-- NOTE the asymmetry: the sibling aggregate_standard_receipts_by_method
-- DOES still accept account_number. Two tools over one resource with
-- different interfaces is worth resolving deliberately, one way or the
-- other; it is not resolved here.

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'StandardReceipt', 'customer_site', 'entity_level', 'customer_site', NULL, NULL, NULL, NULL, NULL, 'client_side', 'CustomerSite', 'equals',
  'Filter receipts by customer site (e.g. Santa Clara). Applied client-side after over-fetch; handles nulls.'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'StandardReceipt', 'customer_name', 'entity_level', 'customer_name', NULL, NULL, NULL, NULL, NULL, 'client_side', 'CustomerName', 'equals',
  'Customer name; resolved to account number by the tool before the server call.'
);

PROMPT Seeded kg_entity_filter (24 rows).

-- ============================================================