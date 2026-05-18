-- sql/kg/v1/002_create_kg_entity_field.sql
--
-- Per-entity projection contract. Lists the fields the agent should
-- expect when fetching an entity, and what role each field plays.
--
-- Roughly 5-8 rows per entity (~30-35 total in v1).

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
      'canonical_id',     -- e.g. SupplierId on Supplier
      'display_id',       -- e.g. SupplierNumber on Supplier
      'display_name',     -- e.g. Supplier (the name field) on Supplier
      'status',           -- e.g. StatusCode on PurchaseOrder
      'date',             -- e.g. InvoiceDate on Invoice
      'amount',           -- e.g. InvoiceAmount on Invoice
      'reference',        -- e.g. BuyerId on PurchaseOrder (points to another entity)
      'projection'        -- generic projection field (no special role)
    ))
);

COMMENT ON TABLE  kg_entity_field                IS 'Projection contract: fields the agent should expect per entity.';
COMMENT ON COLUMN kg_entity_field.entity_name    IS 'Owning entity (FK to kg_entity).';
COMMENT ON COLUMN kg_entity_field.field_name     IS 'Field name on the Fusion endpoint, e.g. ''SupplierId''.';
COMMENT ON COLUMN kg_entity_field.field_role     IS 'Categorized role of this field. Controlled vocabulary.';
COMMENT ON COLUMN kg_entity_field.data_type_hint IS 'Coarse type hint (numeric/string/iso_date/etc).';
COMMENT ON COLUMN kg_entity_field.notes          IS 'Optional commentary for the agent.';
