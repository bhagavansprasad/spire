-- sql/kg/v1/001_create_kg_entity.sql
--
-- Entity declarations. One row per concept the KG models.
-- v1: 5 rows (Supplier, Invoice, PurchaseOrder, Buyer, Address).
--
-- This is metadata about entity types, not instance data.
-- We never insert "supplier #1252" here; we insert "an entity
-- called Supplier exists, materialized by this endpoint."

CREATE TABLE kg_entity (
  entity_name           VARCHAR2(64)   NOT NULL,
  canonical_id_field    VARCHAR2(64)   NOT NULL,
  display_name_field    VARCHAR2(64),
  endpoint_path         VARCHAR2(512)  NOT NULL,
  description           VARCHAR2(2000),
  CONSTRAINT pk_kg_entity PRIMARY KEY (entity_name)
);

COMMENT ON TABLE  kg_entity                     IS 'KG entity declarations. One row per entity type, never per instance.';
COMMENT ON COLUMN kg_entity.entity_name         IS 'Canonical entity name, e.g. ''Supplier''. Primary key, stable across phases.';
COMMENT ON COLUMN kg_entity.canonical_id_field  IS 'Name of the field that uniquely identifies an instance, e.g. ''SupplierId''.';
COMMENT ON COLUMN kg_entity.display_name_field  IS 'Name of the field carrying the human-readable name, if any.';
COMMENT ON COLUMN kg_entity.endpoint_path       IS 'Relative path of the Fusion endpoint that materializes this entity.';
COMMENT ON COLUMN kg_entity.description         IS 'Prose description for the agent. Single-text-field by design.';
