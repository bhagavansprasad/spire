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
    CHECK (vocab_kind IN ('country', 'po_status', 'supplier_status', 'entity_synonym', 'relationship_phrase'))
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

PROMPT Seeded kg_entity (5 rows).

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

PROMPT Seeded kg_entity_field (27 rows).

-- ============================================================
-- STEP 5: Seed kg_edge
-- ============================================================

INSERT INTO kg_edge VALUES (
  'HAS_INVOICE', 'Supplier', 'Invoice', 'SupplierNumber', 'SupplierNumber', 'one_to_many',
  'join_only',
  'GET /fscmRestApi/.../invoices?q=SupplierNumber=''{supplier.SupplierNumber}'' (optionally with InvoiceDate filter).',
  'The invoices endpoint exposes SupplierNumber, not SupplierId. Use SupplierNumber here even though SupplierId is the canonical id on Supplier. Composite q= clauses are unreliable on this pod; apply additional filters client-side after over-fetch.'
);

INSERT INTO kg_edge VALUES (
  'HAS_ADDRESS', 'Supplier', 'Address', 'SupplierId', 'SupplierId', 'one_to_many',
  'join_only',
  'GET /fscmRestApi/.../suppliers?expand=addresses. Address is a child resource; addresses come back inline as supplier.addresses[].',
  'There is no standalone Address endpoint. Always use expand=addresses on the supplier query. Country filtering is client-side: iterate supplier.addresses[] and match on CountryCode or Country.'
);

INSERT INTO kg_edge VALUES (
  'HAS_PURCHASE_ORDER', 'Supplier', 'PurchaseOrder', 'SupplierId', 'SupplierId', 'one_to_many',
  'join_only',
  'GET /fscmRestApi/.../purchaseOrders?q=SupplierId={supplier.SupplierId} (optionally with status filter).',
  'Use SupplierId (numeric), not SupplierNumber, on this endpoint. This is the asymmetry with HAS_INVOICE. Composite q= clauses are unreliable; apply status filter client-side after over-fetch.'
);

INSERT INTO kg_edge VALUES (
  'ASSIGNED_TO', 'PurchaseOrder', 'Buyer', 'BuyerId', 'PersonId', 'many_to_one',
  'join_only',
  'GET /hcmRestApi/.../publicWorkers?q=PersonId={po.BuyerId}',
  'CROSS-PILLAR: PO is in FSCM; Buyer is in HCM. There is no /fscmRestApi/.../buyers endpoint on this pod. BuyerId on a PO equals PersonId on publicWorkers.'
);

PROMPT Seeded kg_edge (4 rows).

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

-- supplier_status (distinct from po_status; Supplier.Status is ACTIVE/INACTIVE)
INSERT INTO kg_vocabulary VALUES ('supplier_status', 'active',   'ACTIVE',   'Supplier is active.');
INSERT INTO kg_vocabulary VALUES ('supplier_status', 'inactive', 'INACTIVE', 'Supplier is inactive.');

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

COMMIT;

PROMPT Seeded kg_entity_tool (2 rows).

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

COMMIT;

PROMPT Seeded kg_edge_tool (3 rows).

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
  'Supplier', 'name_fragment', 'entity_level', 'supplier_name_contains', NULL, NULL, NULL, NULL, NULL, 'server_q', 'Supplier', 'LIKE',
  'Name substring match. Single-clause q=Supplier LIKE ''%value%'' is reliable server-side.'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'Supplier', 'created_date', 'entity_level', 'created_from', NULL, NULL, NULL, NULL, NULL, 'server_q', 'CreationDate', '>=',
  'Creation-date range. Lower bound via q=CreationDate >= ''x'' server-side; upper bound filtered client-side (composite q= fails on this pod).'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'Supplier', 'has_open_PO', 'edge_traversal', NULL, NULL, 'PurchaseOrder', 'status', 'po_status', 'open', NULL, NULL, NULL,
  'Edge filter: supplier has an open PO. Implicit status=open resolved via po_status vocab.'
);

INSERT INTO kg_entity_filter (entity_name, filter_type, mechanism, tool_arg_name, vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, implicit_term, query_style, filter_field, filter_op, notes) VALUES (
  'Supplier', 'has_no_recent_invoices', 'edge_traversal', NULL, NULL, 'Invoice', 'no_recent_invoices', NULL, NULL, NULL, NULL, NULL,
  'Edge filter: supplier has no invoices in N months. Value is explicit ({months: N}).'
);

COMMIT;

PROMPT Seeded kg_entity_filter (6 rows).

-- ============================================================
