"""Cached KG-SQL carrier loader for the SQL emitter.

Reads kg_entity_sql / kg_sql_column / kg_derived_projection once and
caches the result for the process lifetime — the same lazy pattern the
planner uses for kg_entity_filter
(planner/kg_db.py::_load_filter_defs). The SQL emitter consumes this to
build select_columns for the drafted entities instead of hand-authored
literals.

The KG is constant during a run (rebuilt only by a deliberate
`rebuild_kg.py`), so loading once at startup and caching is deterministic
— same (plan) → same SQL, because the DB does not change mid-run.
"""

from __future__ import annotations

from typing import Any

from spire.planner.kg_db import _kg_cursor

_cache: dict[str, dict[str, Any]] | None = None


def load_sql_carriers() -> dict[str, dict[str, Any]]:
    """Return ``{entity_name: {fusion_table, pk_column, columns, derived}}``.

    - ``fusion_table`` / ``pk_column`` come from ``kg_entity_sql``.
    - ``columns`` is ``[(physical_table, column_name)]`` for
      ``is_default_projection='Y'``, ordered by ``field_name``.
    - ``derived`` is ``[expression]`` for ``is_default_projection='Y'``,
      ordered by ``field_name`` (correlated scalar subqueries, emitted
      verbatim).
    """
    global _cache
    if _cache is not None:
        return _cache

    carriers: dict[str, dict[str, Any]] = {}
    with _kg_cursor() as cursor:
        cursor.execute(
            "SELECT entity_name, fusion_table, pk_column FROM kg_entity_sql"
        )
        for entity_name, fusion_table, pk_column in cursor.fetchall():
            carriers[entity_name] = {
                "fusion_table": fusion_table,
                "pk_column": pk_column,
                "columns": [],
                "derived": [],
            }

        cursor.execute(
            "SELECT entity_name, physical_table, column_name "
            "FROM kg_sql_column "
            "WHERE is_default_projection = 'Y' "
            "ORDER BY entity_name, field_name"
        )
        for entity_name, physical_table, column_name in cursor.fetchall():
            carriers.setdefault(entity_name, {
                "fusion_table": None,
                "pk_column": None,
                "columns": [],
                "derived": [],
            })["columns"].append((physical_table, column_name))

        cursor.execute(
            "SELECT entity_name, expression "
            "FROM kg_derived_projection "
            "WHERE is_default_projection = 'Y' "
            "ORDER BY entity_name, field_name"
        )
        for entity_name, expression in cursor.fetchall():
            carriers.setdefault(entity_name, {
                "fusion_table": None,
                "pk_column": None,
                "columns": [],
                "derived": [],
            })["derived"].append(expression)

    _cache = carriers
    return carriers
