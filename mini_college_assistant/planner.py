import sqlite3


DB_PATH = "college.db"


def get_tool_for_entity(conn, entity_name):
    """
    Find the tool associated with an entity in the KG.
    """
    cur = conn.cursor()

    cur.execute(
        """
        SELECT kg_tool_mapping.tool_name
        FROM kg_tool_mapping
        JOIN kg_entity
            ON kg_tool_mapping.entity_id = kg_entity.entity_id
        WHERE kg_entity.entity_name = ?
        """,
        (entity_name,),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(f"No tool found for entity: {entity_name}")

    return row[0]



def get_relationship(conn, source_entity, target_entity):
    """
    Find the relationship and its connection fields from the KG.
    """
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            kg_relationship.relationship_name,
            kg_relationship.source_field,
            kg_relationship.target_field
        FROM kg_relationship
        JOIN kg_entity AS source
            ON kg_relationship.source_entity_id = source.entity_id
        JOIN kg_entity AS target
            ON kg_relationship.target_entity_id = target.entity_id
        WHERE source.entity_name = ?
          AND target.entity_name = ?
        """,
        (source_entity, target_entity),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(
            f"No relationship found between "
            f"{source_entity} and {target_entity}"
        )

    if row[1] is None or row[2] is None:
        raise ValueError(
            f"Relationship between {source_entity} and "
            f"{target_entity} has no connection fields defined in the KG"
        )

    return {
        "name": row[0],
        "source_field": row[1],
        "target_field": row[2],
    }



def get_filter_definition(conn, filter_name):
    """
    Retrieve the filter rule from the KG.
    """
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            kg_filter.entity_id,
            kg_filter.left_field,
            kg_filter.operator,
            kg_filter.right_field
        FROM kg_filter
        WHERE kg_filter.filter_name = ?
        """,
        (filter_name,),
    )

    row = cur.fetchone()

    if row is None:
        raise ValueError(f"Filter not found: {filter_name}")

    return {
        "entity_id": row[0],
        "left_field": row[1],
        "operator": row[2],
        "right_field": row[3],
    }


def generate_plan(intent):
    """
    Convert an Intent into a list of execution steps.
    """
    conn = sqlite3.connect(DB_PATH)

    try:
        entity = intent["entity"]
        related_entity = intent.get("related_entity")
        filter_name = intent.get("filter")
        requested_fields = intent.get("requested_fields", [])

        # Step 1: Find the tool for the main entity.
        main_tool = get_tool_for_entity(conn, entity)

        plan = [
            {
                "step_id": 1,
                "tool_name": main_tool,
                "purpose": f"Retrieve {entity} records",
                "arguments": {},
            }
        ]

        # Step 2: If another entity is involved,
        # find its tool and the relationship between entities.
        if related_entity:
            related_tool = get_tool_for_entity(conn, related_entity)

            relationship = get_relationship(
                conn,
                entity,
                related_entity,
            )

            plan.append(
                {
                    "step_id": 2,
                    "tool_name": related_tool,
                    "purpose": f"Retrieve related {related_entity} records",
                    "relationship": relationship,
                    "arguments": {},
                }
            )

        # Step 3: Retrieve the KG definition of the filter.
        if filter_name:
            filter_definition = get_filter_definition(
                conn,
                filter_name,
            )

            plan.append(
                {
                    "step_id": len(plan) + 1,
                    "action": "apply_filter",
                    "filter_name": filter_name,
                    "filter_definition": filter_definition,
                }
            )

        # Step 4: Record the fields requested by the user.
        plan.append(
            {
                "step_id": len(plan) + 1,
                "action": "select_fields",
                "fields": requested_fields,
            }
        )

        return plan

    finally:
        conn.close()
