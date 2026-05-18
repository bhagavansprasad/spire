-- sql/kg/v1/010_seed_kg_vocabulary.sql
--
-- Populate kg_vocabulary with the v1 lookups from kg_schema_v1.md §5.
-- One row per (vocab_kind, term). Multiple terms can map to the same
-- canonical_value.

-- ============================================================
-- vocab_kind = 'country'
-- ============================================================
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('country', 'US', 'US', 'ISO-2 code; also the canonical value.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('country', 'USA', 'US', '3-letter form; normalized to ISO-2.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('country', 'United States', 'US', 'Full name.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('country', 'United States of America', 'US', 'Full formal name.');

INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('country', 'UK', 'GB', 'Informal; ISO-2 is GB.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('country', 'GB', 'GB', 'ISO-2 code.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('country', 'United Kingdom', 'GB', 'Full name.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('country', 'Britain', 'GB', 'Informal.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('country', 'Great Britain', 'GB', 'Informal.');

INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('country', 'India', 'IN', 'Full name.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('country', 'IN', 'IN', 'ISO-2 code.');

INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('country', 'Canada', 'CA', 'Full name.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('country', 'CA', 'CA', 'ISO-2 code.');

INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('country', 'Australia', 'AU', 'Full name.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('country', 'AU', 'AU', 'ISO-2 code.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('country', 'AUS', 'AU', '3-letter form; normalized to ISO-2.');

-- ============================================================
-- vocab_kind = 'po_status'
-- ============================================================
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('po_status', 'open',      'OPEN',       'Default conversational synonym.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('po_status', 'active',    'OPEN',       'Synonym for open.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('po_status', 'closed',    'CLOSED',     NULL);
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('po_status', 'completed', 'CLOSED',     'Synonym for closed.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('po_status', 'incomplete','INCOMPLETE', NULL);
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('po_status', 'draft',     'INCOMPLETE', 'Synonym for incomplete.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('po_status', 'canceled',  'CANCELED',   NULL);
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('po_status', 'cancelled', 'CANCELED',   'British spelling.');

-- ============================================================
-- vocab_kind = 'entity_synonym'
-- ============================================================
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('entity_synonym', 'supplier',         'Supplier',      NULL);
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('entity_synonym', 'vendor',           'Supplier',      'Synonym.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('entity_synonym', 'invoice',          'Invoice',       NULL);
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('entity_synonym', 'bill',             'Invoice',       'Synonym.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('entity_synonym', 'purchase order',   'PurchaseOrder', NULL);
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('entity_synonym', 'PO',               'PurchaseOrder', 'Acronym.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('entity_synonym', 'order',            'PurchaseOrder', 'Ambiguous (could mean sales order); resolved to PO in this domain.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('entity_synonym', 'buyer',            'Buyer',         NULL);
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('entity_synonym', 'purchasing agent', 'Buyer',         'Synonym.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('entity_synonym', 'agent',            'Buyer',         'Synonym (in purchasing context).');

-- ============================================================
-- vocab_kind = 'relationship_phrase'
-- ============================================================
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('relationship_phrase', 'supplier has invoice',     'HAS_INVOICE',        NULL);
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('relationship_phrase', 'invoice for supplier',     'HAS_INVOICE',        NULL);
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('relationship_phrase', 'supplier in country',      'HAS_ADDRESS',        'Composite phrase; resolves via HAS_ADDRESS + country vocabulary.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('relationship_phrase', 'country supplier',         'HAS_ADDRESS',        'Composite phrase; resolves via HAS_ADDRESS + country vocabulary.');
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('relationship_phrase', 'supplier has PO',          'HAS_PURCHASE_ORDER', NULL);
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('relationship_phrase', 'PO for supplier',          'HAS_PURCHASE_ORDER', NULL);
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('relationship_phrase', 'buyer assigned to PO',     'ASSIGNED_TO',        NULL);
INSERT INTO kg_vocabulary (vocab_kind, term, canonical_value, notes) VALUES ('relationship_phrase', 'PO buyer',                 'ASSIGNED_TO',        NULL);

COMMIT;

PROMPT Seeded kg_vocabulary.
