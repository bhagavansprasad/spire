-- sql/kg/v1/004_create_kg_pattern.sql
--
-- Query pattern declarations. One row per reusable logical pattern
-- (no_Y_in_N_months, status_filter, country_filter_via_address,
-- cross_pillar_lookup).
--
-- parameters is JSON; mechanics is prose. Both CLOB because they
-- may grow longer than VARCHAR2 comfortably handles.

CREATE TABLE kg_pattern (
  pattern_name    VARCHAR2(64)   NOT NULL,
  shape           VARCHAR2(2000) NOT NULL,
  parameters      CLOB,
  mechanics       CLOB,
  example         VARCHAR2(2000),
  CONSTRAINT pk_kg_pattern PRIMARY KEY (pattern_name)
);

COMMENT ON TABLE  kg_pattern              IS 'KG query patterns. Reusable logical shapes the agent looks up rather than re-derives.';
COMMENT ON COLUMN kg_pattern.pattern_name IS 'Canonical pattern name, e.g. ''no_Y_in_N_months''.';
COMMENT ON COLUMN kg_pattern.shape        IS 'One-line abstract description of the pattern.';
COMMENT ON COLUMN kg_pattern.parameters   IS 'JSON: list of {name, type, description}. Parseable by the agent.';
COMMENT ON COLUMN kg_pattern.mechanics    IS 'Prose: step-by-step execution. Read by the agent during planning.';
COMMENT ON COLUMN kg_pattern.example      IS 'A concrete instantiation example to ground the agent.';
