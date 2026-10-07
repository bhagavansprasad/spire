# Extending the SQL overlay

Maintainer-facing guide for the overlay described in `../SQL_OVERLAY_POC.md`.
Read that first; this document assumes its vocabulary.

## Where things live

| File | What it holds |
|---|---|
| `src/spire/kg/sql_overlay.py` | The overlay — six conceptual tables as Python dataclasses |
| `src/spire/rendering/sql_emitter.py` | `emit_sql(plan, overlay) -> list[str]` |
| `tests/test_sql_emitter.py` | One test per plan shape |
| `docs/design/sql_overlay/acceptance/` | Captured output from a live run |
| `docs/design/sql_overlay/supplier_schema.csv` | 12 supplier-module tables, column names only |

## Add a filter (predicate) for an existing entity

Most extensions. Example: a new `business_relationship` filter for
`search_suppliers`.

1. Add the `FilterSpec` in `_FILTERS`:

   ```python
   ("search_suppliers", "business_relationship"): FilterSpec(
       tool_name="search_suppliers",
       arg_name="business_relationship",
       predicate_template="{alias}.BUSINESS_RELATIONSHIP = {value}",
       value_map={
           "Spend Authorized": "'SPEND_AUTHORIZED'",
           "Prospective": "'PROSPECTIVE'",
       },
       assumption="business_relationship_mapping",
   ),
   ```

2. If the predicate names an alias you do not own, set `requires_join`
   to the `(from, to)` pair whose join clause must appear first. The
   emitter pulls it in automatically. See the country filter for an
   example.

3. If the value comes from a lookup rather than a fixed map, set
   `vocab_kind` and add the entries to `_LITERALS`.

4. If the mapping is an assumption, add a row to `_ASSUMPTIONS`.

5. Add a test in `tests/test_sql_emitter.py` asserting the SQL contains
   the expected predicate and the expected assumption key.

6. Run `pytest tests/test_sql_emitter.py -q`.

## Add a literal (pod-specific value)

Example: a BU name not yet in `_LITERALS`.

1. Curl the pod for the numeric ID:

   ```bash
   curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" --get \
     --data-urlencode "onlyData=true" \
     --data-urlencode "fields=ProcurementBU,ProcurementBUId" \
     "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers/<id>/child/sites"
   ```

2. Add a row to `_LITERALS`:

   ```python
   ("supplier_site_bu", "UK Business Unit"): "300000048716584",
   ```

3. Pod-specific. If the pod changes, this must be reseeded. Do not
   assume the numeric IDs carry across pods.

## Add an entity

Rarer. Example: a new `Invoice` entity so a Plan step that fetches
invoices can emit SQL.

1. Add to `_ENTITIES` — fusion table, alias, PK column, default
   projection, base joins.
2. Add to `OVERLAY.tool_to_entity` — the MCP tool name that fetches it.
3. Add any filters the entity's tools accept.
4. Add any joins the entity participates in.
5. Add a plan shape test — construct a Step and assert the SQL.

## Add an assumption

Every `-- ASSUMPTION:` comment corresponds to a row in `_ASSUMPTIONS`.
The emitter cites the assumption by key; the map supplies the text.

Naming convention: `snake_case`, describes the choice, not the outcome.
Good: `bu_literal_from_overlay`. Bad: `bu_ok`.

## What NOT to change

- **The nine existing KG tables.** The overlay is parallel; the KG is
  unchanged. If a filter needs a new KG row, that is a POC-2 conversation.
- **The Plan.** The emitter reads `Step` objects; it does not produce
  them. Changing Plan shape is a planner change, out of scope.
- **The pipeline.** `--show-sql` is additive; no existing behavior
  changes when the flag is off.

## Testing discipline

- **One test per plan shape.** A new predicate or entity needs a test
  that constructs the Step and asserts the SQL. Grep-friendly.
- **Terminator check.** Every emitted statement must end with `;` on the
  SQL body, not glued to a comment. `test_semicolon_not_glued_to_comment`
  guards this; extend it if a new format introduces new failure modes.
- **Determinism.** `emit_sql` is pure. Two calls on the same Plan
  return byte-identical SQL. Do not add stateful lookups or LLM calls
  to the emitter.

## Run a single prompt end-to-end with SQL

```bash
python scripts/promptkit.py --run \
  --prompt "Your prompt here" \
  --show-sql --show-planner
```

The SQL block appears between `--- SQL projection ---` and
`--- end SQL projection ---`. Everything else is normal pipeline output.
