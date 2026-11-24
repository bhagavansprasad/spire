
import sqlite3

# Connect to the new People & Organizations database
conn = sqlite3.connect("people_organization.db")
conn.execute("PRAGMA foreign_keys = ON")
cursor = conn.cursor()


# 1. KG ENTITY TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS kg_entity (
    entity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_name TEXT NOT NULL UNIQUE,
    description TEXT
)
""")

entities = [
    ("PERSON", "Represents an individual person"),
    ("ORGANIZATION", "Represents an organization")
]

cursor.executemany("""
INSERT OR IGNORE INTO kg_entity (entity_name, description)
VALUES (?, ?)
""", entities)


# Get entity IDs
cursor.execute("""
SELECT entity_id, entity_name FROM kg_entity
""")

entity_ids = {
    name: entity_id
    for entity_id, name in cursor.fetchall()
}


# 2. KG RELATIONSHIP TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS kg_relationship (
    relationship_id INTEGER PRIMARY KEY AUTOINCREMENT,
    relationship_name TEXT NOT NULL UNIQUE,
    source_entity_id INTEGER NOT NULL,
    target_entity_id INTEGER NOT NULL,
    description TEXT,
    source_field TEXT,
    target_field TEXT,
    FOREIGN KEY (source_entity_id) REFERENCES kg_entity(entity_id),
    FOREIGN KEY (target_entity_id) REFERENCES kg_entity(entity_id)
)
""")

relationships = [
    (
        "WORKS_FOR",
        entity_ids["PERSON"],
        entity_ids["ORGANIZATION"],
        "A person works for an organization",
        "PERSON_ID",
        "ORG_ID"
    ),
    (
        "KNOWS",
        entity_ids["PERSON"],
        entity_ids["PERSON"],
        "A person knows another person",
        "PERSON_ID",
        "KNOWS_PERSON_ID"
    )
]

cursor.executemany("""
INSERT OR IGNORE INTO kg_relationship (
    relationship_name,
    source_entity_id,
    target_entity_id,
    description,
    source_field,
    target_field
)
VALUES (?, ?, ?, ?, ?, ?)
""", relationships)


# 3. KG FIELD TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS kg_field (
    field_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL,
    field_name TEXT NOT NULL,
    description TEXT,
    FOREIGN KEY (entity_id) REFERENCES kg_entity(entity_id),
    UNIQUE (entity_id, field_name)
)
""")

fields = [
    (entity_ids["PERSON"], "PERSON_ID", "Unique person identifier"),
    (entity_ids["PERSON"], "NAME", "Name of the person"),
    (entity_ids["PERSON"], "CITY", "City where the person lives"),
    (entity_ids["PERSON"], "AGE", "Age of the person"),

    (entity_ids["ORGANIZATION"], "ORG_ID", "Unique organization identifier"),
    (entity_ids["ORGANIZATION"], "ORG_NAME", "Name of the organization"),
    (entity_ids["ORGANIZATION"], "INDUSTRY", "Industry of the organization")
]

cursor.executemany("""
INSERT OR IGNORE INTO kg_field (
    entity_id, field_name, description
)
VALUES (?, ?, ?)
""", fields)


# 4. KG FILTER TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS kg_filter (
    filter_id INTEGER PRIMARY KEY AUTOINCREMENT,
    filter_name TEXT NOT NULL UNIQUE,
    entity_id INTEGER NOT NULL,
    description TEXT,
    left_field TEXT NOT NULL,
    operator TEXT NOT NULL,
    right_field TEXT NOT NULL,
    FOREIGN KEY (entity_id) REFERENCES kg_entity(entity_id)
)
""")


# 5. KG TOOL MAPPING TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS kg_tool_mapping (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL,
    tool_name TEXT NOT NULL,
    description TEXT,
    FOREIGN KEY (entity_id) REFERENCES kg_entity(entity_id),
    UNIQUE (entity_id, tool_name)
)
""")
# Insert entity-to-tool mappings
cursor.executemany("""
    INSERT OR IGNORE INTO kg_tool_mapping
    (entity_id, tool_name)
    VALUES (?, ?)
""", [
    (1, "query_people"),
    (2, "query_organizations")
])


# 6. KG RELATIONSHIP FIELD TABLE

cursor.execute("""
CREATE TABLE IF NOT EXISTS kg_relationship_field (
    field_id INTEGER PRIMARY KEY AUTOINCREMENT,
    relationship_id INTEGER NOT NULL,
    field_name TEXT NOT NULL,
    description TEXT,
    FOREIGN KEY (relationship_id)
        REFERENCES kg_relationship(relationship_id),
    UNIQUE (relationship_id, field_name)
)
""")

# Get relationship IDs
cursor.execute("""
SELECT relationship_id, relationship_name
FROM kg_relationship
""")

relationship_ids = {
    name: relationship_id
    for relationship_id, name in cursor.fetchall()
}

relationship_fields = [
    (
        relationship_ids["WORKS_FOR"],
        "ROLE",
        "Role of the person in the organization"
    ),
    (
        relationship_ids["WORKS_FOR"],
        "SINCE",
        "Year the person started working for the organization"
    ),
    (
        relationship_ids["KNOWS"],
        "SINCE",
        "Year since the two people have known each other"
    )
]

cursor.executemany("""
INSERT OR IGNORE INTO kg_relationship_field (
    relationship_id,
    field_name,
    description
)
VALUES (?, ?, ?)
""", relationship_fields)

# Save changes
conn.commit()
conn.close()

print("People & Organizations KG created successfully!")
