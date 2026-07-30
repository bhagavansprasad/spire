"""KG entity, edge, pattern and vocabulary lookups.

Six read-only functions, each answering one question against the KG:
what tool and args does an entity or edge use, what pattern binds a
filter, what does a vocabulary term resolve to. All go through
_kg_cursor / _read_clob from kg_db.py; none of them build a Plan
themselves — that is plan_builders.py's job, one layer up.
"""

from __future__ import annotations

import json
from typing import Any

from spire.planner.kg_db import _kg_cursor, _read_clob


# ─────────────────────────────────────────────────────────────────────
# KG entity lookups
# ─────────────────────────────────────────────────────────────────────


def find_entity(entity_name: str) -> dict[str, Any]:
    """
    Look up an entity by name in ``kg_entity``.

    Returns a dict with keys:
        endpoint_path, canonical_id_field, display_name_field, description

    Raises ``KeyError`` if no row exists for the given entity_name.
    Match is case-sensitive (entity_name is a primary key).
    """
    with _kg_cursor() as cursor:
        cursor.execute(
            """
            SELECT endpoint_path, canonical_id_field,
                   display_name_field, description
            FROM kg_entity
            WHERE entity_name = :entity_name
            """,
            entity_name=entity_name,
        )
        row = cursor.fetchone()

    if row is None:
        raise KeyError(f"No entity in KG: {entity_name!r}")

    endpoint_path, canonical_id_field, display_name_field, description = row
    return {
        "endpoint_path": endpoint_path,
        "canonical_id_field": canonical_id_field,
        "display_name_field": display_name_field,
        "description": description,
    }


def find_entity_tool(entity_name: str, filter_type: str) -> str:
    """
    Find the MCP tool that fetches this entity with the given filter type.

    Queries ``kg_entity_tool``. Use ``filter_type='none'`` for the default
    (unfiltered) fetcher.

    Examples:
        find_entity_tool('Supplier', 'none')    -> 'search_suppliers'
        find_entity_tool('Supplier', 'country') -> 'search_suppliers_by_country'

    Returns the MCP tool name as a string.
    Raises ``KeyError`` if no row exists for the (entity_name, filter_type)
    pair.
    """
    with _kg_cursor() as cursor:
        cursor.execute(
            """
            SELECT mcp_tool_name
            FROM kg_entity_tool
            WHERE entity_name = :entity_name
              AND filter_type = :filter_type
            """,
            entity_name=entity_name,
            filter_type=filter_type,
        )
        row = cursor.fetchone()

    if row is None:
        raise KeyError(
            f"No entity tool for ({entity_name!r}, {filter_type!r})"
        )

    return row[0]


# ─────────────────────────────────────────────────────────────────────
# KG edge lookups
# ─────────────────────────────────────────────────────────────────────


def find_edge(from_entity: str, to_entity: str) -> dict[str, Any]:
    """
    Look up the edge connecting two entities in ``kg_edge``.

    Returns a dict with keys:
        edge_name, from_join_field, to_join_field,
        cardinality, server_filter_rule, traversal_hint, notes,
        iter_fields

    ``iter_fields`` is the parsed iter_fields_json column: a
    {tool_arg: parent_field} map for edges whose traversal needs SEVERAL
    parent fields per call (e.g. HAS_DISTRIBUTION needs POHeaderId,
    POLineId and LineLocationId). It is None for every single-field
    edge, which is all of them except HAS_DISTRIBUTION.

    Raises ``KeyError`` if no edge connects from_entity to to_entity.
    Note: edges are directional. find_edge('Supplier', 'PurchaseOrder')
    finds HAS_PURCHASE_ORDER; find_edge('PurchaseOrder', 'Supplier')
    will NOT find it (no reverse edge declared in v1).
    """
    with _kg_cursor() as cursor:
        cursor.execute(
            """
            SELECT edge_name, from_join_field, to_join_field,
                   cardinality, server_filter_rule, traversal_hint, notes,
                   iter_fields_json
            FROM kg_edge
            WHERE from_entity = :from_entity
              AND to_entity   = :to_entity
            """,
            from_entity=from_entity,
            to_entity=to_entity,
        )
        row = cursor.fetchone()

    if row is None:
        raise KeyError(
            f"No edge from {from_entity!r} to {to_entity!r}"
        )

    (
        edge_name,
        from_join_field,
        to_join_field,
        cardinality,
        server_filter_rule,
        traversal_hint,
        notes,
        iter_fields_json,
    ) = row
    return {
        "edge_name": edge_name,
        "from_join_field": from_join_field,
        "to_join_field": to_join_field,
        "cardinality": cardinality,
        "server_filter_rule": server_filter_rule,
        "traversal_hint": traversal_hint,
        "notes": notes,
        "iter_fields": json.loads(iter_fields_json) if iter_fields_json else None,
    }


def find_edge_tool(edge_name: str) -> str | None:
    """
    Find the MCP tool that traverses this edge in ``kg_edge_tool``.

    Returns the tool name string, or ``None`` if the edge has no row
    (e.g. ``HAS_ADDRESS`` is bundled with ``search_suppliers_by_country``
    via ``expand=addresses``; absence of a row is meaningful and signals
    the edge is not independently traversable).

    Examples:
        find_edge_tool('HAS_PURCHASE_ORDER') -> 'search_purchase_orders'
        find_edge_tool('ASSIGNED_TO')        -> 'get_buyer'
        find_edge_tool('HAS_ADDRESS')        -> None
    """
    with _kg_cursor() as cursor:
        cursor.execute(
            """
            SELECT mcp_tool_name
            FROM kg_edge_tool
            WHERE edge_name = :edge_name
            """,
            edge_name=edge_name,
        )
        row = cursor.fetchone()

    if row is None:
        return None

    return row[0]


# ─────────────────────────────────────────────────────────────────────
# KG pattern lookups
# ─────────────────────────────────────────────────────────────────────


def find_pattern_for_filter(
    entity_name: str, filter_type: str
) -> dict[str, Any]:
    """
    Find which pattern handles this filter type on this entity.

    Queries ``kg_pattern_binding``. Returns:
        {
          "pattern_name": <str>,
          "parameter_bindings": <dict parsed from JSON>,
        }

    ``parameter_bindings`` is stored as a JSON string in a CLOB and is
    parsed before return — callers receive a Python dict, not a string.

    Examples:
        find_pattern_for_filter('Supplier', 'country')
          -> {
               "pattern_name": "country_filter_via_address",
               "parameter_bindings": {
                   "parent": "Supplier",
                   "child_edge": "HAS_ADDRESS",
                   "country_term_param": "country",
                 },
             }

    Raises ``KeyError`` if no binding exists for the (entity_name,
    filter_type) pair.
    Raises ``json.JSONDecodeError`` if parameter_bindings is malformed
    (indicates seed-data corruption, not a user error).
    """
    with _kg_cursor() as cursor:
        cursor.execute(
            """
            SELECT pattern_name, parameter_bindings
            FROM kg_pattern_binding
            WHERE entity_name = :entity_name
              AND filter_type = :filter_type
            """,
            entity_name=entity_name,
            filter_type=filter_type,
        )
        row = cursor.fetchone()
        if row is None:
            raise KeyError(
                f"No pattern binding for ({entity_name!r}, {filter_type!r})"
            )
        # Read CLOB while the connection is still open. Sync oracledb's
        # LOB.read() is synchronous (unlike the async driver's AsyncLOB).
        pattern_name, parameter_bindings_raw = row
        parameter_bindings_str = _read_clob(parameter_bindings_raw)

    parameter_bindings = json.loads(parameter_bindings_str)
    return {
        "pattern_name": pattern_name,
        "parameter_bindings": parameter_bindings,
    }


# ─────────────────────────────────────────────────────────────────────
# KG vocabulary lookups
# ─────────────────────────────────────────────────────────────────────


def resolve_vocab(vocab_kind: str, term: str) -> str:
    """
    Resolve a business term to its canonical Fusion code.

    Queries ``kg_vocabulary``. Examples:
        resolve_vocab('country', 'US')        -> 'US'
        resolve_vocab('country', 'USA')       -> 'US'
        resolve_vocab('po_status', 'open')    -> 'OPEN'
        resolve_vocab('po_status', 'active')  -> 'OPEN'

    Raises ``KeyError`` if no matching row exists for the
    (vocab_kind, term) pair. Match is case-insensitive on the term.
    """
    with _kg_cursor() as cursor:
        cursor.execute(
            """
            SELECT canonical_value
            FROM kg_vocabulary
            WHERE vocab_kind = :vocab_kind AND LOWER(term) = LOWER(:term)
            """,
            vocab_kind=vocab_kind,
            term=term,
        )
        row = cursor.fetchone()

    if row is None:
        raise KeyError(f"No vocab for ({vocab_kind!r}, {term!r})")

    return row[0]
