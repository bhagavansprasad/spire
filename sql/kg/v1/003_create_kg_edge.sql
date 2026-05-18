-- sql/kg/v1/003_create_kg_edge.sql
--
-- Relationship (edge) declarations. One row per typed edge between
-- entities. v1: 4 rows (HAS_INVOICE, HAS_ADDRESS, HAS_PURCHASE_ORDER,
-- ASSIGNED_TO).
--
-- Edges are KG declarations, not instance edges. We do not store
-- "supplier #1252 HAS_PURCHASE_ORDER PO #9999" — that's instance data.
-- We store "the edge HAS_PURCHASE_ORDER exists between Supplier and
-- PurchaseOrder; here's how to traverse it."

CREATE TABLE kg_edge (
  edge_name          VARCHAR2(64)   NOT NULL,
  from_entity        VARCHAR2(64)   NOT NULL,
  to_entity          VARCHAR2(64)   NOT NULL,
  from_join_field    VARCHAR2(64)   NOT NULL,
  to_join_field      VARCHAR2(64)   NOT NULL,
  cardinality        VARCHAR2(32)   NOT NULL,
  traversal_hint     VARCHAR2(2000) NOT NULL,
  notes              VARCHAR2(2000),
  CONSTRAINT pk_kg_edge PRIMARY KEY (edge_name),
  CONSTRAINT fk_kg_edge_from
    FOREIGN KEY (from_entity) REFERENCES kg_entity (entity_name),
  CONSTRAINT fk_kg_edge_to
    FOREIGN KEY (to_entity)   REFERENCES kg_entity (entity_name),
  CONSTRAINT chk_kg_edge_cardinality
    CHECK (cardinality IN (
      'one_to_one',
      'one_to_many',
      'many_to_one',
      'many_to_many'
    ))
);

COMMENT ON TABLE  kg_edge                  IS 'KG edge declarations. One row per typed edge between entities.';
COMMENT ON COLUMN kg_edge.edge_name        IS 'Canonical edge name, e.g. ''HAS_PURCHASE_ORDER''.';
COMMENT ON COLUMN kg_edge.from_entity      IS 'Source entity (FK to kg_entity).';
COMMENT ON COLUMN kg_edge.to_entity        IS 'Target entity (FK to kg_entity).';
COMMENT ON COLUMN kg_edge.from_join_field  IS 'Field on FROM entity that holds the join value (e.g. ''SupplierId'').';
COMMENT ON COLUMN kg_edge.to_join_field    IS 'Field on TO entity the join value matches against. May differ from from_join_field (the SupplierNumber vs SupplierId asymmetry).';
COMMENT ON COLUMN kg_edge.cardinality      IS 'Cardinality of the edge. Documented for the agent; not enforced (we are read-only).';
COMMENT ON COLUMN kg_edge.traversal_hint   IS 'Prose hint: how to call Fusion to traverse this edge. e.g. GET /purchaseOrders?q=SupplierId={value}';
COMMENT ON COLUMN kg_edge.notes            IS 'Caveats: composite-q= unreliability, expand=addresses requirement, cross-pillar nature, etc.';
