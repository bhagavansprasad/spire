-- sql/kg/v1/009_seed_kg_pattern.sql
--
-- Populate kg_pattern with the 4 v1 patterns from kg_schema_v1.md §6.
--
-- parameters: JSON list of {name, type, description}
-- mechanics:  prose, step-by-step

INSERT INTO kg_pattern (pattern_name, shape, parameters, mechanics, example) VALUES (
  'no_Y_in_N_months',
  'Filter a set of entities of type X to those that have NO related entity of type Y in the last N months.',
  '[
    {"name":"X","type":"Entity","description":"The entity being filtered (e.g. Supplier)."},
    {"name":"Y","type":"Entity","description":"The related entity whose absence is checked (e.g. Invoice)."},
    {"name":"edge","type":"Edge","description":"The edge from X to Y (e.g. HAS_INVOICE)."},
    {"name":"date_field","type":"FieldName","description":"The date field on Y to compare against the cutoff (e.g. InvoiceDate)."},
    {"name":"N","type":"integer","description":"Number of months in the look-back window."}
   ]',
  '1. Compute the cutoff date as today - N months in ISO format.
2. For each candidate X, traverse the edge to Y filtered by date_field >= cutoff.
3. Keep X if zero Y were found; drop X otherwise.
4. Be careful: composite q= clauses on Y''s endpoint may be unreliable. Apply the date filter via the most selective single q= clause and confirm client-side.',
  'Suppliers with no invoices in 6 months: X=Supplier, Y=Invoice, edge=HAS_INVOICE, date_field=InvoiceDate, N=6.'
);

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
  'cross_pillar_lookup',
  'Follow an ID from an entity in one Fusion pillar to its primary key in another pillar.',
  '[
    {"name":"source_entity","type":"Entity","description":"The entity carrying the ID (e.g. PurchaseOrder)."},
    {"name":"source_field","type":"FieldName","description":"The ID field on source (e.g. BuyerId)."},
    {"name":"target_entity","type":"Entity","description":"The entity to look up (e.g. Buyer)."},
    {"name":"target_endpoint","type":"string","description":"The endpoint that materializes target (e.g. /hcmRestApi/.../publicWorkers)."}
   ]',
  '1. Take the ID value from the source entity (e.g. po.BuyerId).
2. Query the target endpoint filtered by target.canonical_id_field=<value>.
3. Project the target''s display fields back onto the source result.
4. Tag of caution: this pattern has exactly one instance in v1 (PO -> Buyer). May be folded into ASSIGNED_TO in v1.1 if phase 04 finds it redundant.',
  'Buyer assigned to each PO: source=PurchaseOrder, source_field=BuyerId, target=Buyer (PersonId on publicWorkers).'
);

COMMIT;

PROMPT Seeded kg_pattern (4 rows).
