"""Knowledge Graph loader.

Queries the v1 KG metadata tables (kg_entity, kg_entity_field,
kg_edge, kg_pattern, kg_vocabulary) and formats them as a markdown
bundle suitable for inclusion in the agent's system prompt.

This is the B-lite integration: KG content is loaded once per
run_agent() call, embedded in the system prompt, and the LLM
sees it whether it asks for it or not.

Usage:
    from spire.config import load_persona
    from spire.kg.loader import load_kg_context

    persona = load_persona("default_dev")
    markdown = await load_kg_context(persona)
    # markdown is a string suitable for inclusion in the system prompt

The function is async because it uses OracleClient. CLOB fields are
read inside the OracleClient async-with block (see the
test_kg_metadata.py module docstring for the rule).
"""

from spire.config import Persona
from spire.oracle.client import OracleClient


# ---- SQL queries ----

_SQL_ENTITIES = """
SELECT entity_name, canonical_id_field, display_name_field,
       endpoint_path, description
  FROM kg_entity
 ORDER BY entity_name
"""

_SQL_ENTITY_FIELDS = """
SELECT entity_name, field_name, field_role, data_type_hint, notes
  FROM kg_entity_field
 ORDER BY entity_name, field_name
"""

_SQL_EDGES = """
SELECT edge_name, from_entity, to_entity,
       from_join_field, to_join_field,
       cardinality, traversal_hint, notes
  FROM kg_edge
 ORDER BY edge_name
"""

_SQL_PATTERNS = """
SELECT pattern_name, shape, parameters, mechanics, example
  FROM kg_pattern
 ORDER BY pattern_name
"""

_SQL_VOCABULARY = """
SELECT vocab_kind, term, canonical_value, notes
  FROM kg_vocabulary
 ORDER BY vocab_kind, term
"""


# ---- CLOB helper ----

async def _read_clob(value) -> str:
    """Coerce a possibly-CLOB column value to a Python str.

    MUST be called while the OracleClient connection is still open
    (inside the async with that produced `value`). AsyncLOB.read()
    is a network round-trip; closing the connection first will raise
    DPY-1001.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return await value.read()


# ---- Bundle formatters ----

def _format_entities(entities: list[tuple], fields_by_entity: dict[str, list[tuple]]) -> str:
    """Render the entities section as a markdown table + per-entity field lists."""
    lines = ["## Entities", ""]
    lines.append("| Name | Canonical ID | Display Name Field | Endpoint |")
    lines.append("|---|---|---|---|")
    for row in entities:
        entity_name, canonical_id, display_name, endpoint, _desc = row
        display_name = display_name or "—"
        lines.append(f"| {entity_name} | `{canonical_id}` | `{display_name}` | `{endpoint}` |")
    lines.append("")

    lines.append("### Entity field details")
    lines.append("")
    for row in entities:
        entity_name = row[0]
        description = row[4] or ""
        lines.append(f"**{entity_name}** — {description}")
        lines.append("")
        fields = fields_by_entity.get(entity_name, [])
        if fields:
            lines.append("| Field | Role | Type | Notes |")
            lines.append("|---|---|---|---|")
            for fname, frole, ftype, fnotes in fields:
                ftype = ftype or "—"
                fnotes = fnotes or ""
                lines.append(f"| `{fname}` | {frole} | {ftype} | {fnotes} |")
            lines.append("")
    return "\n".join(lines)


def _format_edges(edges: list[tuple]) -> str:
    """Render the edges section as a markdown table + per-edge details."""
    lines = ["## Edges (Relationships)", ""]
    lines.append("Edges declare how entities relate. Read the `from_join_field` and `to_join_field` carefully — they may differ from the canonical IDs (this is the SupplierNumber-vs-SupplierId asymmetry that crashed Track A).")
    lines.append("")
    lines.append("| Edge | From → To | Join (from → to) | Cardinality |")
    lines.append("|---|---|---|---|")
    for row in edges:
        edge_name, from_entity, to_entity, from_field, to_field, cardinality, _hint, _notes = row
        lines.append(
            f"| `{edge_name}` | {from_entity} → {to_entity} "
            f"| `{from_field}` → `{to_field}` | {cardinality} |"
        )
    lines.append("")

    lines.append("### Edge details")
    lines.append("")
    for row in edges:
        edge_name, from_entity, to_entity, from_field, to_field, _card, hint, notes = row
        lines.append(f"**{edge_name}** ({from_entity} → {to_entity})")
        lines.append("")
        lines.append(f"- Traversal: {hint}")
        if notes:
            lines.append(f"- Notes: {notes}")
        lines.append("")
    return "\n".join(lines)


def _format_patterns(patterns: list[tuple]) -> str:
    """Render the patterns section as prose blocks (patterns are too rich for tables)."""
    lines = ["## Query Patterns", ""]
    lines.append("Reusable logical shapes. When the user's prompt matches one of these patterns, follow the mechanics rather than re-deriving from scratch.")
    lines.append("")
    for row in patterns:
        pattern_name, shape, parameters, mechanics, example = row
        lines.append(f"### `{pattern_name}`")
        lines.append("")
        lines.append(f"**Shape:** {shape}")
        lines.append("")
        if parameters:
            lines.append("**Parameters (JSON):**")
            lines.append("```json")
            lines.append(parameters.strip())
            lines.append("```")
            lines.append("")
        if mechanics:
            lines.append("**Mechanics:**")
            lines.append("")
            lines.append(mechanics.strip())
            lines.append("")
        if example:
            lines.append(f"**Example:** {example}")
            lines.append("")
    return "\n".join(lines)


def _format_vocabulary(vocab: list[tuple]) -> str:
    """Render the vocabulary section, grouped by vocab_kind, as tables."""
    lines = ["## Vocabulary", ""]
    lines.append("Translate business terms in the user's prompt to Fusion codes using these lookups.")
    lines.append("")

    # Group by vocab_kind.
    by_kind: dict[str, list[tuple]] = {}
    for row in vocab:
        kind = row[0]
        by_kind.setdefault(kind, []).append(row)

    # Stable order: country, po_status, entity_synonym, relationship_phrase.
    kind_order = ["country", "po_status", "entity_synonym", "relationship_phrase"]
    kind_titles = {
        "country": "Countries",
        "po_status": "Purchase Order Status",
        "entity_synonym": "Entity Synonyms",
        "relationship_phrase": "Relationship Phrases",
    }

    for kind in kind_order:
        if kind not in by_kind:
            continue
        lines.append(f"### {kind_titles[kind]}")
        lines.append("")
        lines.append("| Term | Canonical Value |")
        lines.append("|---|---|")
        for _kind, term, canonical, _notes in by_kind[kind]:
            lines.append(f"| `{term}` | `{canonical}` |")
        lines.append("")
    return "\n".join(lines)


# ---- Public entry point ----

async def load_kg_context(persona: Persona) -> str:
    """Load the full v1 KG and return it as a markdown bundle.

    Performs all DB reads inside a single OracleClient async-with block
    so that CLOB reads complete before the connection closes.

    Returns the bundle as a string. Caller is responsible for placing
    it into the system prompt.

    Raises RuntimeError if persona.oracle is None.
    """
    async with OracleClient(persona) as oc:
        entity_rows_raw = await oc.fetch_all(_SQL_ENTITIES)
        # Read CLOB description column for each entity inside the with block.
        entities: list[tuple] = []
        for entity_name, canonical_id, display_name, endpoint, description in entity_rows_raw:
            desc_str = await _read_clob(description)
            entities.append((entity_name, canonical_id, display_name, endpoint, desc_str))

        field_rows = await oc.fetch_all(_SQL_ENTITY_FIELDS)
        # field_rows: (entity_name, field_name, field_role, data_type_hint, notes)
        # No CLOBs here — notes is VARCHAR2.

        edge_rows_raw = await oc.fetch_all(_SQL_EDGES)
        edges: list[tuple] = []
        for edge_name, from_e, to_e, from_f, to_f, card, hint, notes in edge_rows_raw:
            hint_str = await _read_clob(hint)
            notes_str = await _read_clob(notes)
            edges.append((edge_name, from_e, to_e, from_f, to_f, card, hint_str, notes_str))

        pattern_rows_raw = await oc.fetch_all(_SQL_PATTERNS)
        patterns: list[tuple] = []
        for name, shape, parameters, mechanics, example in pattern_rows_raw:
            params_str = await _read_clob(parameters)
            mechanics_str = await _read_clob(mechanics)
            patterns.append((name, shape, params_str, mechanics_str, example))

        vocab_rows = await oc.fetch_all(_SQL_VOCABULARY)
        # No CLOBs here.

    # Group fields by entity_name for the formatter.
    fields_by_entity: dict[str, list[tuple]] = {}
    for entity_name, field_name, field_role, data_type_hint, notes in field_rows:
        fields_by_entity.setdefault(entity_name, []).append(
            (field_name, field_role, data_type_hint, notes)
        )

    sections = [
        "# Oracle Fusion Knowledge Graph (v1)",
        "",
        "The following knowledge describes the structure of Oracle Fusion endpoints, the relationships between entities, and known business-term mappings. Consult it when planning multi-step queries — especially for join keys, status codes, and country lookups.",
        "",
        _format_entities(entities, fields_by_entity),
        _format_edges(edges),
        _format_patterns(patterns),
        _format_vocabulary(vocab_rows),
    ]
    return "\n".join(sections).rstrip() + "\n"
