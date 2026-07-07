
"""
Synchronous KG vocabulary read for the NL parser.

This is Q2, direction 1 (see docs/designs/feature_1_nl_parser_design.md): the
parser reads the allowed vocabulary from the KG BEFORE the LLM call and embeds
it in the prompt as the menu the model may order from.

SYNCHRONOUS BY DESIGN. This module uses the planner's synchronous KG path
(plain ``oracledb`` via spire.planner.planner._kg_cursor), NOT the agent's
async ``load_kg_context``. The parser calls, blocks, and waits inline.

WHAT THE MENU IS — AND WHY IT IS NOT JUST "READ THE KG TABLES":
An Intent is only useful if the PLANNER can execute it. So the menu must
reflect what the planner can ACTUALLY do, not merely what the KG declares:

- Valid ``target_entity`` values = entities that have an entity-level fetcher,
  i.e. an (entity, 'none') row in kg_entity_tool. Today that is Supplier
  and Invoice.
- Valid filter types = the planner's own supported set, now read from the
  KG table kg_entity_filter via the planner's accessor functions
  (_entity_level_filter_types / _edge_traversal_filters). We call them
  through the planner so there is a single source of truth — if we
  re-declared them here they could drift from what _validate_intent_filters
  actually accepts, and the two-way validation (Q2 direction 2) would then
  pass Intents the planner later crashes on.

Entity/vocabulary DETAIL (descriptions, country synonyms, etc.) is read from
the KG to enrich the prompt — that part is genuinely declarative.

When filters move into the KG (planner v1.2), the only change here is to read
the filter set from the KG instead of importing the planner constants; the
shape of the menu is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from spire.planner.planner import (
    _entity_level_filter_types,
    _edge_traversal_filters,
    _kg_cursor,
)


@dataclass
class KGMenu:
    """The allowed vocabulary the parser advertises to the LLM and validates
    against (Q2).

    Fields:
        target_entities: Entity names that may appear as an Intent's
            target_entity (those with an entity-level fetcher).
        filter_types: Filter ``type`` strings the planner supports. The union
            of entity-level and edge-traversal filters.
        entity_descriptions: entity_name -> human description, from kg_entity.
            Used to make the prompt's entity list legible to the LLM. Includes
            ALL known entities (even ones not valid as target_entity), so the
            LLM can recognize and correctly REFUSE an out-of-scope entity
            rather than hallucinate a fetcher for it.
        country_terms: Accepted country vocabulary (term -> canonical), from
            kg_vocabulary. Lets the LLM map "United States" / "USA" -> US.
    """

    target_entities: set[str] = field(default_factory=set)
    filter_types: set[str] = field(default_factory=set)
    entity_descriptions: dict[str, str] = field(default_factory=dict)
    country_terms: dict[str, str] = field(default_factory=dict)

    def is_known_entity(self, entity_name: str) -> bool:
        """True if the entity exists in the KG at all (valid or not as a
        target). Distinguishes UNKNOWN_ENTITY (not in KG) from
        UNSUPPORTED_OPERATION (in KG but not a valid target)."""
        return entity_name in self.entity_descriptions

    def is_valid_target(self, entity_name: str) -> bool:
        """True if the entity can be an Intent's target_entity (has a
        fetcher)."""
        return entity_name in self.target_entities

    def is_known_filter(self, filter_type: str) -> bool:
        return filter_type in self.filter_types


def _read_clob(value) -> str:
    """Coerce a possibly-CLOB column value to str. Mirrors the planner's sync
    _read_clob; duplicated here to avoid importing a private helper that may
    change. Sync oracledb LOB.read() is synchronous."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.read()


def load_kg_menu() -> KGMenu:
    """Read the allowed vocabulary from the KG, synchronously.

    Uses the planner's sync cursor. All reads happen inside the cursor's
    context so any CLOB reads complete before the connection closes.

    Returns:
        A KGMenu describing valid target entities, supported filter types,
        entity descriptions, and country vocabulary.

    Raises:
        Anything oracledb raises (connection failure, etc.) propagates — same
        convention as the planner's KG lookups.
    """
    # Filter set comes from the planner's KG-backed filter definitions
    # (kg_entity_filter). A fresh set so callers can't mutate anything.
    filter_types: set[str] = (
        _entity_level_filter_types() | set(_edge_traversal_filters())
    )

    entity_descriptions: dict[str, str] = {}
    target_entities: set[str] = set()
    country_terms: dict[str, str] = {}

    with _kg_cursor() as cursor:
        # All known entities + descriptions.
        cursor.execute(
            "SELECT entity_name, description FROM kg_entity ORDER BY entity_name"
        )
        for entity_name, description in cursor.fetchall():
            entity_descriptions[entity_name] = _read_clob(description)

        # Valid target entities = those with an entity-level fetcher, i.e. a
        # (entity, 'none') row in kg_entity_tool.
        cursor.execute(
            "SELECT entity_name FROM kg_entity_tool WHERE filter_type = 'none'"
        )
        for (entity_name,) in cursor.fetchall():
            target_entities.add(entity_name)

        # Country vocabulary (term -> canonical) so the LLM can normalize.
        cursor.execute(
            "SELECT term, canonical_value FROM kg_vocabulary "
            "WHERE vocab_kind = 'country' ORDER BY term"
        )
        for term, canonical in cursor.fetchall():
            country_terms[term] = canonical

    return KGMenu(
        target_entities=target_entities,
        filter_types=filter_types,
        entity_descriptions=entity_descriptions,
        country_terms=country_terms,
    )


