# KG role maps

Per-entity contribution to `kg_sql_column` and `kg_derived_projection`. Append-only.

**Header rules.**

- Each `### <Entity>` section carries: `kg_entity` row, `base_joins`, the `kg_sql_column` table (`is_default_projection='Y'`), the `kg_derived_projection` table where present, bugs fixed, join-key verification, entity-specific observations.
- **Never trust the sweep.** Every projected column and every join key is verified against `t_task2_all.txt` per `SCHEMA_DISCOVERY_METHOD.md` §6–§7. The sweep's named first failure is a hint, not the count. Confirmed ×4 by Contact, Buyer, PurchaseOrder, PurchaseOrderLine — each named one, each had 3–5 real absences.
- **Never re-derive a verified map.** Once a section is here, it is transcribed into `kg_schema.sql` at build, not re-derived. Corrections are new sections referencing the old, not edits.
- **Substitutions and derived roles cite evidence.** A substituted column names the physical column, its data type and nullability; a derived role names the expression and the alias-resolution rule.
- **Null-returning roles are flagged.** A role that returns NULL, not 0, on the empty case says so in observations.

**Mechanisms referenced below.**

- `kg_sql_column` — direct columns. PK `(entity_name, physical_table, column_name)`. Phase 2 §5 Q3.
- `kg_derived_projection` — correlated scalar subqueries where no direct column carries the role. Phase 2 §5 Q6.
- Nullable join keys — every nullable key in any `base_joins` gets a §3.4 build self-check counting NULLs, requiring zero. Phase 2 §5 Q4.

---

## Procurement

### PurchaseOrder (`PO_HEADERS_ALL`)

`kg_entity`: `(PurchaseOrder, PO_HEADERS_ALL, PO_HEADER_ID)`

`base_joins`:

```
JOIN POZ_SUPPLIERS S ON S.VENDOR_ID = P.VENDOR_ID
JOIN HZ_PARTIES HP ON HP.PARTY_ID = S.PARTY_ID
JOIN PER_ALL_PEOPLE_F BP ON BP.PERSON_ID = P.AGENT_ID AND SYSDATE BETWEEN BP.EFFECTIVE_START_DATE AND BP.EFFECTIVE_END_DATE
JOIN PER_PERSON_NAMES_F PN ON PN.PERSON_ID = BP.PERSON_ID AND PN.NAME_TYPE = 'GLOBAL' AND SYSDATE BETWEEN PN.EFFECTIVE_START_DATE AND PN.EFFECTIVE_END_DATE
```

`kg_sql_column`, `is_default_projection='Y'`:

| role | table | column |
|---|---|---|
| `po_header_id` | `PO_HEADERS_ALL` | `PO_HEADER_ID` |
| `po_number` | `PO_HEADERS_ALL` | `SEGMENT1` |
| `supplier_name` | `HZ_PARTIES` | `PARTY_NAME` |
| `buyer_name` | `PER_PERSON_NAMES_F` | `DISPLAY_NAME` |
| `status` | `PO_HEADERS_ALL` | `DOCUMENT_STATUS` |

`kg_derived_projection`, `is_default_projection='Y'`:

| role | expression |
|---|---|
| `amount` | `(SELECT SUM(L.AMOUNT) FROM PO_LINES_ALL L WHERE L.PO_HEADER_ID = P.PO_HEADER_ID)` |

**Bugs fixed (3 of 6 projected columns absent).**

- `P.AUTHORIZATION_STATUS` → `PO_HEADERS_ALL.DOCUMENT_STATUS` (col 31, `VARCHAR2(100)`, N). Propagates to the `("search_purchase_orders","status")` filter's `predicate_template` — one fix covers both sites.
- `BP.DISPLAY_NAME` → `PER_PERSON_NAMES_F.DISPLAY_NAME` (col 18, `VARCHAR2(960)`). R-4 repeat.
- `P.AMOUNT` → derived projection. No header-level carrier on this pod (R-7).

**Join keys, verified both sides.** Non-nullable: `POZ_SUPPLIERS.VENDOR_ID` (1, N), `POZ_SUPPLIERS.PARTY_ID` (5, N), `HZ_PARTIES.PARTY_ID` (1, N), `PER_ALL_PEOPLE_F.PERSON_ID` (1, N), `PER_ALL_PEOPLE_F.EFFECTIVE_START_DATE` (2, N), `PER_ALL_PEOPLE_F.EFFECTIVE_END_DATE` (3, N), `PO_HEADERS_ALL.AGENT_ID` (36, N), `PER_PERSON_NAMES_F.PERSON_ID` (4, N), `PER_PERSON_NAMES_F.EFFECTIVE_START_DATE` (2, N), `PER_PERSON_NAMES_F.EFFECTIVE_END_DATE` (3, N).

**Nullable — Q4 self-check required.** `PO_HEADERS_ALL.VENDOR_ID` (col 51, Y). Count NULLs on `PO_HEADERS_ALL.VENDOR_ID`; require zero; non-zero fails the §3.4 build.

**Observations.** `supplier_id` filter's subquery reaches `POZ_SUPPLIERS` directly, bypassing the `S` join — two references to one table per emitted query, not a bug. `amount` returns NULL, not 0, for a PO with no lines. `PO_HEADERS_ALL` is a stub view (R-7).

### PurchaseOrderLine (`PO_LINES_ALL`)

`kg_entity`: `(PurchaseOrderLine, PO_LINES_ALL, PO_LINE_ID)`

`base_joins`: `[]` — none. Both derived subqueries are self-contained.

`kg_sql_column`, `is_default_projection='Y'`:

| role | table | column |
|---|---|---|
| `po_line_id` | `PO_LINES_ALL` | `PO_LINE_ID` |
| `line_number` | `PO_LINES_ALL` | `LINE_NUM` |
| `description` | `PO_LINES_ALL` | `ITEM_DESCRIPTION` |
| `category_id` | `PO_LINES_ALL` | `CATEGORY_ID` |
| `quantity` | `PO_LINES_ALL` | `QUANTITY` |
| `unit_price` | `PO_LINES_ALL` | `UNIT_PRICE` |
| `amount` | `PO_LINES_ALL` | `AMOUNT` |
| `status` | `PO_LINES_ALL` | `LINE_STATUS` |

`kg_derived_projection`, `is_default_projection='Y'`:

| role | expression |
|---|---|
| `total_tax` | `(SELECT SUM(LL.ESTIMATED_TAX_AMOUNT) FROM PO_LINE_LOCATIONS_ALL LL WHERE LL.PO_LINE_ID = L.PO_LINE_ID)` |
| `total` | `L.AMOUNT + (SELECT SUM(LL.ESTIMATED_TAX_AMOUNT) FROM PO_LINE_LOCATIONS_ALL LL WHERE LL.PO_LINE_ID = L.PO_LINE_ID)` |

`total` reuses the `total_tax` subquery verbatim. One estimator, two roles.

**Bugs fixed (5 of 10 projected columns absent).**

- `DESCRIPTION` → `PO_LINES_ALL.ITEM_DESCRIPTION` (col 84, `VARCHAR2(960)`, Y). Only description-shaped column.
- `PRICE` → `PO_LINES_ALL.UNIT_PRICE` (col 91, `NUMBER`, Y). Adjacent variants (`LIST_PRICE`, `BASE_UNIT_PRICE`, `MARKET_PRICE`, `TAX_EXCLUSIVE_PRICE`) are not the ordered price.
- `TOTAL_TAX` → derived. No line-level tax amount; the tax value lives at schedule level (`PO_LINE_LOCATIONS_ALL.ESTIMATED_TAX_AMOUNT`, col 58), reached via `PO_LINE_ID`.
- `TOTAL` → derived. Line amount plus estimated tax.
- `STATUS_LOOKUP_CODE` → `PO_LINES_ALL.LINE_STATUS` (col 72, `VARCHAR2(100)`, Y). The sweep's named failure; `FUNDS_STATUS` and `FIRM_STATUS_LOOKUP_CODE` are sub-statuses.

**Join keys, verified both sides.** Base entity has no joins. Inside the Q6 subquery: `PO_LINES_ALL.PO_LINE_ID` (col 1, N) = `PO_LINE_LOCATIONS_ALL.PO_LINE_ID` (col 34, N). Both NOT NULL — no Q4 self-check needed.

**Filter.** `("get_purchase_order_lines","po_header_id")` → `{alias}.PO_HEADER_ID = {value}` on alias `L` → `PO_LINES_ALL.PO_HEADER_ID` (col 75, N). Clean.

**Observations.** `ESTIMATED_TAX_AMOUNT` is an estimate; post-invoice actual tax lives as `RECOVERABLE_TAX` (col 152) + `NONRECOVERABLE_TAX` (col 153) on `PO_DISTRIBUTIONS_ALL`. If `actual_tax` is ever a distinct role, the path is `PO_LINES_ALL` → `PO_LINE_LOCATIONS_ALL.LINE_LOCATION_ID` → `PO_DISTRIBUTIONS_ALL.LINE_LOCATION_ID` — a second derived projection, not a substitution of the first. Not drafted today. `total` and `total_tax` return NULL, not 0, for a line with no schedules. `PO_LINES_ALL` carries `AMOUNT` and `UNIT_PRICE` but no `TOTAL`/`TOTAL_TAX` — this is the Fusion shape, not a stub; totals and tax are computed at schedule/distribution level.
