-- sql/kg/v1/005_create_kg_vocabulary.sql
--
-- Vocabulary lookups. One table for all four kinds, distinguished
-- by vocab_kind. v1: ~45-50 rows total.
--
-- vocab_kind values:
--   'country'              "US" -> "US"      (ISO-2 code)
--   'po_status'            "open" -> "OPEN"  (Fusion StatusCode)
--   'entity_synonym'       "vendor" -> "Supplier"
--   'relationship_phrase'  "<X> for <Y>" -> edge name

CREATE TABLE kg_vocabulary (
  vocab_kind        VARCHAR2(32)   NOT NULL,
  term              VARCHAR2(128)  NOT NULL,
  canonical_value   VARCHAR2(128)  NOT NULL,
  notes             VARCHAR2(1000),
  CONSTRAINT pk_kg_vocabulary PRIMARY KEY (vocab_kind, term),
  CONSTRAINT chk_kg_vocabulary_kind
    CHECK (vocab_kind IN (
      'country',
      'po_status',
      'entity_synonym',
      'relationship_phrase'
    ))
);

COMMENT ON TABLE  kg_vocabulary                 IS 'Business-term-to-Fusion-code lookups. Four kinds; one table.';
COMMENT ON COLUMN kg_vocabulary.vocab_kind      IS 'Which kind of vocabulary this row belongs to. Controlled vocabulary.';
COMMENT ON COLUMN kg_vocabulary.term            IS 'The business word/phrase the user might say.';
COMMENT ON COLUMN kg_vocabulary.canonical_value IS 'The Fusion code or canonical name the term maps to.';
COMMENT ON COLUMN kg_vocabulary.notes           IS 'Optional commentary (synonyms, gotchas, source notes).';
