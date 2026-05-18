-- sql/kg/v1/008_seed_kg_edge.sql
--
-- Populate kg_edge with the 4 v1 edges from kg_schema_v1.md §4.

INSERT INTO kg_edge (edge_name, from_entity, to_entity, from_join_field, to_join_field, cardinality, traversal_hint, notes) VALUES (
  'HAS_INVOICE',
  'Supplier', 'Invoice',
  'SupplierNumber', 'SupplierNumber',
  'one_to_many',
  'GET /fscmRestApi/.../invoices?q=SupplierNumber=''{supplier.SupplierNumber}'' (optionally with InvoiceDate filter).',
  'The invoices endpoint exposes SupplierNumber, not SupplierId. Use SupplierNumber here even though SupplierId is the canonical id on Supplier. Composite q= clauses are unreliable on this pod; apply additional filters client-side after over-fetch.'
);

INSERT INTO kg_edge (edge_name, from_entity, to_entity, from_join_field, to_join_field, cardinality, traversal_hint, notes) VALUES (
  'HAS_ADDRESS',
  'Supplier', 'Address',
  'SupplierId', 'SupplierId',
  'one_to_many',
  'GET /fscmRestApi/.../suppliers?expand=addresses. Address is a child resource; addresses come back inline as supplier.addresses[].',
  'There is no standalone Address endpoint. Always use expand=addresses on the supplier query. Country filtering is client-side: iterate supplier.addresses[] and match on CountryCode or Country.'
);

INSERT INTO kg_edge (edge_name, from_entity, to_entity, from_join_field, to_join_field, cardinality, traversal_hint, notes) VALUES (
  'HAS_PURCHASE_ORDER',
  'Supplier', 'PurchaseOrder',
  'SupplierId', 'SupplierId',
  'one_to_many',
  'GET /fscmRestApi/.../purchaseOrders?q=SupplierId={supplier.SupplierId} (optionally with status filter).',
  'Use SupplierId (numeric), not SupplierNumber, on this endpoint. This is the asymmetry with HAS_INVOICE. Composite q= clauses are unreliable; apply status filter client-side after over-fetch.'
);

INSERT INTO kg_edge (edge_name, from_entity, to_entity, from_join_field, to_join_field, cardinality, traversal_hint, notes) VALUES (
  'ASSIGNED_TO',
  'PurchaseOrder', 'Buyer',
  'BuyerId', 'PersonId',
  'many_to_one',
  'GET /hcmRestApi/.../publicWorkers?q=PersonId={po.BuyerId}',
  'CROSS-PILLAR: PO is in FSCM; Buyer is in HCM. There is no /fscmRestApi/.../buyers endpoint on this pod. BuyerId on a PO equals PersonId on publicWorkers. Most important relationship in the v1 KG to make explicit; Track A baseline never figured this out from tool docstrings.'
);

COMMIT;

PROMPT Seeded kg_edge (4 rows).
