
import sqlite3

DB_PATH = "people_organization.db"


def get_tool_for_entity(conn, entity_name):
    """Find the retrieval tool for an entity from the KG."""

    cur = conn.cursor()

    cur.execute("""
        SELECT ktm.tool_name
        FROM kg_tool_mapping ktm
        JOIN kg_entity ke
            ON ktm.entity_id = ke.entity_id
        WHERE ke.entity_name = ?
    """, (entity_name,))

    row = cur.fetchone()

    if row is None:
        raise ValueError(f"No tool found for entity: {entity_name}")

    return row[0]



def get_relationship(conn, source_entity, target_entity):
    """Find relationship details and its execution tool from the KG."""

    cur = conn.cursor()

    cur.execute("""
        SELECT
            kr.relationship_name,
            kr.source_field,
            kr.target_field
        FROM kg_relationship kr
        JOIN kg_entity source
            ON kr.source_entity_id = source.entity_id
        JOIN kg_entity target
            ON kr.target_entity_id = target.entity_id
        WHERE source.entity_name = ?
          AND target.entity_name = ?
    """, (source_entity, target_entity))

    row = cur.fetchone()

    if row is None:
        raise ValueError(
            f"No relationship found between "
            f"{source_entity} and {target_entity}"
        )

    relationship_tools = {
        "WORKS_FOR": "query_works_for",
        "KNOWS": "query_knows",
    }

    tool_name = relationship_tools.get(row[0])

    if not tool_name:
        raise ValueError(
            f"No execution tool mapped to relationship: {row[0]}"
        )

    return {
        "name": row[0],
        "source_field": row[1],
        "target_field": row[2],
        "tool_name": tool_name,
    }



def generate_plan(intent):
    """Convert an Intent into execution steps."""

    conn = sqlite3.connect(DB_PATH)

    try:
        entity = intent["entity"]
        related_entity = intent.get("related_entity")

        # Case 1: Relationship-based question.
        if related_entity:
            relationship = get_relationship(
                conn,
                entity,
                related_entity
            )

            tool_name = relationship["tool_name"]

            return [
                {
                    "step_id": 1,
                    "tool_name": tool_name,
                    "purpose": (
                        f"Retrieve records for "
                        f"{relationship['name']}"
                    ),
                    "relationship": relationship,
                }
            ]

        # Case 2: Single-entity question.
        tool_name = get_tool_for_entity(conn, entity)

        return [
            {
                "step_id": 1,
                "tool_name": tool_name,
                "purpose": f"Retrieve {entity} records",
            }
        ]

    finally:
        conn.close()
