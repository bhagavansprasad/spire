-- sql/kg/v1/009_seed_kg_pattern.sql
--
-- Populate kg_pattern with the v1 patterns from kg_schema_v1.md §6.
--
-- parameters: JSON list of {name, type, description}
-- mechanics:  prose, step-by-step

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

COMMIT;

PROMPT Seeded kg_pattern (3 rows).