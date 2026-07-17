



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
    CHECK (vocab_kind IN ('country', 'po_status', 'supplier_status', 'supplier_business_relationship', 'supplier_site_bu', 'supplier_classification', 'entity_synonym', 'relationship_phrase'))
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

PROMPT Seeded kg_entity (11 rows).

-- ============================================================
-- STEP 4: Seed kg_entity_field
-- ============================================================

-- Supplier
INSERT INTO kg_entity_field VALUES ('Supplier', 'SupplierId',     'canonical_id', 'numeric', 'System primary key. Used to join to PurchaseOrder.SupplierId.');
INSERT INTO kg_entity_field VALUES ('Supplier', 'SupplierNumber', 'display_id',   'string',  'Human-readable identifier (e.g. ''1252''). Used to join to Invoice.SupplierNumber.');
INSERT INTO kg_entity_field VALUES ('Supplier', 'Supplier',       'display_name', 'string',  'Display name of the supplier.');
INSERT INTO kg_entity_field VALUES ('Supplier', 'Status',         'status',       'string',  'e.g. ACTIVE.');

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

PROMPT Seeded kg_entity_field (84 rows).

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

PROMPT Seeded kg_edge (10 rows).

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

PROMPT Seeded kg_entity_tool (4 rows).

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

PROMPT Seeded kg_edge_tool (9 rows).

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
  'Invoice', 'purchase_order', 'entity_level', 'purchase_order', NULL, NULL, NULL, NULL, NULL, 'server_q', 'PurchaseOrderNumber', 'equals',
  'Invoices raised against a PO. Value is the PO NUMBER (e.g. "162034"), not POHeaderId — invoices carry PurchaseOrderNumber on the header and it filters server-side (single clause). Most selective invoice filter, so it wins the server q= clause.'
);

PROMPT Seeded kg_entity_filter (17 rows).

-- ============================================================










