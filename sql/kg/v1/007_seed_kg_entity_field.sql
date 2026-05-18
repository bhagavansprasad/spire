-- sql/kg/v1/007_seed_kg_entity_field.sql
--
-- Populate kg_entity_field with the projection contracts from
-- kg_schema_v1.md §3.

-- ---------- Supplier ----------
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('Supplier', 'SupplierId',     'canonical_id', 'numeric', 'System primary key. Used to join to PurchaseOrder.SupplierId.');
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('Supplier', 'SupplierNumber', 'display_id',   'string',  'Human-readable identifier (e.g. ''1252''). Used to join to Invoice.SupplierNumber.');
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('Supplier', 'Supplier',       'display_name', 'string',  'Display name of the supplier.');
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('Supplier', 'Status',         'status',       'string',  'e.g. ACTIVE.');

-- ---------- Invoice ----------
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('Invoice', 'InvoiceId',       'canonical_id', 'numeric', 'System primary key.');
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('Invoice', 'InvoiceNumber',   'display_id',   'string',  'Human-readable identifier.');
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('Invoice', 'InvoiceDate',     'date',         'iso_date','Used for date-window filters (e.g. no_Y_in_N_months pattern).');
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('Invoice', 'InvoiceAmount',   'amount',       'numeric', NULL);
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('Invoice', 'InvoiceCurrency', 'projection',   'string',  NULL);
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('Invoice', 'PaidStatus',      'status',       'string',  NULL);
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('Invoice', 'ApprovalStatus',  'status',       'string',  NULL);
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('Invoice', 'SupplierNumber',  'reference',    'string',  'Join key back to Supplier.SupplierNumber. Note: not SupplierId on this endpoint.');

-- ---------- PurchaseOrder ----------
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('PurchaseOrder', 'POHeaderId',   'canonical_id', 'numeric', 'System primary key.');
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('PurchaseOrder', 'OrderNumber',  'display_id',   'string',  'Human-readable identifier.');
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('PurchaseOrder', 'StatusCode',   'status',       'string',  'Code values: OPEN, CLOSED, INCOMPLETE, CANCELED. Use for filtering.');
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('PurchaseOrder', 'Status',       'projection',   'string',  'Human-readable form of StatusCode. Display only; do not filter on this.');
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('PurchaseOrder', 'SupplierId',   'reference',    'numeric', 'Join key back to Supplier.SupplierId. Note: SupplierId on this endpoint, not SupplierNumber.');
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('PurchaseOrder', 'BuyerId',      'reference',    'numeric', 'Join key to Buyer.PersonId on /hcmRestApi/.../publicWorkers (cross-pillar).');
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('PurchaseOrder', 'Ordered',      'amount',       'numeric', NULL);
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('PurchaseOrder', 'CurrencyCode', 'projection',   'string',  NULL);

-- ---------- Buyer ----------
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('Buyer', 'PersonId',     'canonical_id', 'numeric', 'Same numeric value as PurchaseOrder.BuyerId.');
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('Buyer', 'DisplayName',  'display_name', 'string',  NULL);
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('Buyer', 'WorkEmail',    'projection',   'string',  NULL);
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('Buyer', 'Username',     'projection',   'string',  NULL);
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('Buyer', 'PersonNumber', 'display_id',   'string',  NULL);

-- ---------- Address ----------
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('Address', 'CountryCode', 'projection', 'string', 'ISO-2 country code (e.g. ''US''). Match against vocab_kind=''country'' canonical_value.');
INSERT INTO kg_entity_field (entity_name, field_name, field_role, data_type_hint, notes) VALUES
  ('Address', 'Country',     'projection', 'string', 'Full country name (e.g. ''United States''). Match against vocab_kind=''country'' term forms.');

COMMIT;

PROMPT Seeded kg_entity_field (27 rows).
