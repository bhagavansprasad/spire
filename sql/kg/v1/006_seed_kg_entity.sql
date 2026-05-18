-- sql/kg/v1/006_seed_kg_entity.sql
--
-- Populate kg_entity with the 5 v1 entities from kg_schema_v1.md §3.

INSERT INTO kg_entity (entity_name, canonical_id_field, display_name_field, endpoint_path, description) VALUES (
  'Supplier',
  'SupplierId',
  'Supplier',
  '/fscmRestApi/resources/11.13.18.05/suppliers',
  'A vendor or service provider in Fusion''s supplier master. SupplierId is the system primary key used for joins to POs; SupplierNumber is the human-readable identifier used for joins to invoices. Country is on the child Address resource, not on Supplier directly.'
);

INSERT INTO kg_entity (entity_name, canonical_id_field, display_name_field, endpoint_path, description) VALUES (
  'Invoice',
  'InvoiceId',
  'InvoiceNumber',
  '/fscmRestApi/resources/11.13.18.05/invoices',
  'An accounts-payable invoice tied to a supplier. Note: this endpoint exposes SupplierNumber (string) for the supplier reference, not SupplierId. Date-window filters use InvoiceDate.'
);

INSERT INTO kg_entity (entity_name, canonical_id_field, display_name_field, endpoint_path, description) VALUES (
  'PurchaseOrder',
  'POHeaderId',
  'OrderNumber',
  '/fscmRestApi/resources/11.13.18.05/purchaseOrders',
  'A purchase order issued to a supplier and assigned to a buyer. Exposes SupplierId (numeric) for the supplier reference and BuyerId for the buyer reference. StatusCode carries values like OPEN, CLOSED, INCOMPLETE, CANCELED.'
);

INSERT INTO kg_entity (entity_name, canonical_id_field, display_name_field, endpoint_path, description) VALUES (
  'Buyer',
  'PersonId',
  'DisplayName',
  '/hcmRestApi/resources/11.13.18.05/publicWorkers',
  'The purchasing agent assigned to a PO. Buyers are HCM workers, not an FSCM entity. PersonId equals the BuyerId on PurchaseOrder. No /fscmRestApi/.../buyers endpoint exists on this pod.'
);

INSERT INTO kg_entity (entity_name, canonical_id_field, display_name_field, endpoint_path, description) VALUES (
  'Address',
  'AddressId',
  NULL,
  '/fscmRestApi/resources/11.13.18.05/suppliers?expand=addresses',
  'A supplier''s address. Modeled as a separate entity because a supplier can have addresses in multiple countries. Not exposed as a top-level resource; only accessible as a child of Supplier via expand=addresses.'
);

COMMIT;

PROMPT Seeded kg_entity (5 rows).
