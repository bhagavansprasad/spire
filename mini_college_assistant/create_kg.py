import sqlite3

# Connect to our existing college database
conn = sqlite3.connect("college.db")
cursor = conn.cursor()

# Create the KG entity table
cursor.execute("""
CREATE TABLE IF NOT EXISTS kg_entity (
    entity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_name TEXT NOT NULL UNIQUE,
    description TEXT
)
""")

# Add our entity types
entities = [
    ("Student", "Represents a college student"),
    ("Course", "Represents a college course"),
    ("Payment", "Represents a student's fee payment")
]

cursor.executemany("""
INSERT OR IGNORE INTO kg_entity (entity_name, description)
VALUES (?, ?)
""", entities)



# Create the KG relationship table
cursor.execute("""
CREATE TABLE IF NOT EXISTS kg_relationship (
    relationship_id INTEGER PRIMARY KEY AUTOINCREMENT,
    relationship_name TEXT NOT NULL UNIQUE,
    source_entity_id INTEGER NOT NULL,
    target_entity_id INTEGER NOT NULL,
    description TEXT,
    source_field TEXT,
    target_field TEXT,
    FOREIGN KEY (source_entity_id)
        REFERENCES kg_entity(entity_id),
    FOREIGN KEY (target_entity_id)
        REFERENCES kg_entity(entity_id)
)
""")

# Add the new columns to an existing database if needed.
# CREATE TABLE IF NOT EXISTS does not update existing tables.
cursor.execute("PRAGMA table_info(kg_relationship)")
existing_columns = {
    row[1] for row in cursor.fetchall()
}

if "source_field" not in existing_columns:
    cursor.execute("""
        ALTER TABLE kg_relationship
        ADD COLUMN source_field TEXT
    """)

if "target_field" not in existing_columns:
    cursor.execute("""
        ALTER TABLE kg_relationship
        ADD COLUMN target_field TEXT
    """)

# Get the entity IDs
cursor.execute("""
    SELECT entity_id, entity_name
    FROM kg_entity
""")

entity_ids = {
    entity_name: entity_id
    for entity_id, entity_name in cursor.fetchall()
}



# Define relationships between entities
relationships = [
    (
        "enrolled_in",
        entity_ids["Student"],
        entity_ids["Course"],
        "A student is enrolled in a course",
        None,
        None
    ),
    (
        "has_payment",
        entity_ids["Student"],
        entity_ids["Payment"],
        "A student has a fee-payment record",
        "student_id",
        "student_id"
    )
]

# Insert relationships
cursor.executemany("""
INSERT OR IGNORE INTO kg_relationship
(
    relationship_name,
    source_entity_id,
    target_entity_id,
    description,
    source_field,
    target_field
)
VALUES (?, ?, ?, ?, ?, ?)
""", relationships)

# Update existing relationships with their connection fields.
# This also updates rows already present in college.db.
cursor.execute("""
UPDATE kg_relationship
SET source_field = ?, target_field = ?
WHERE relationship_name = ?
""", ("student_id", "student_id", "has_payment"))


# Create the KG field table
cursor.execute("""
CREATE TABLE IF NOT EXISTS kg_field (
    field_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL,
    field_name TEXT NOT NULL,
    description TEXT,
    FOREIGN KEY (entity_id)
        REFERENCES kg_entity(entity_id),
    UNIQUE (entity_id, field_name)
)
""")

# Define fields for each entity
fields = [
    # Student fields
    (entity_ids["Student"], "student_id", "Unique student identifier"),
    (entity_ids["Student"], "name", "Student's name"),
    (entity_ids["Student"], "email", "Student's email address"),

    # Course fields
    (entity_ids["Course"], "course_id", "Unique course identifier"),
    (entity_ids["Course"], "course_name", "Name of the course"),
    (entity_ids["Course"], "duration_years", "Duration of the course in years"),
    (entity_ids["Course"], "total_fee", "Total course fee"),

    # Payment fields
    (entity_ids["Payment"], "payment_id", "Unique payment record identifier"),
    (entity_ids["Payment"], "student_id", "ID of the student associated with the payment"),
    (entity_ids["Payment"], "amount_due", "Total amount the student must pay"),
    (entity_ids["Payment"], "amount_paid", "Amount the student has paid")
]

# Insert field descriptions
cursor.executemany("""
INSERT OR IGNORE INTO kg_field
    (entity_id, field_name, description)
VALUES (?, ?, ?)
""", fields)

# Insert field descriptions
cursor.executemany("""
INSERT OR IGNORE INTO kg_field
    (entity_id, field_name, description)
VALUES (?, ?, ?)
""", fields)

# Create the KG filter table
cursor.execute("""
CREATE TABLE IF NOT EXISTS kg_filter (
    filter_id INTEGER PRIMARY KEY AUTOINCREMENT,
    filter_name TEXT NOT NULL UNIQUE,
    entity_id INTEGER NOT NULL,
    description TEXT,
    left_field TEXT NOT NULL,
    operator TEXT NOT NULL,
    right_field TEXT NOT NULL,
    FOREIGN KEY (entity_id)
        REFERENCES kg_entity(entity_id)
)
""")

# Define KG filters
filters = [
    (
        "pending_fees",
        entity_ids["Payment"],
        "Find payments where the amount due is greater than the amount paid",
        "amount_due",
        ">",
        "amount_paid"
    ),
    (
        "fully_paid_fees",
        entity_ids["Payment"],
        "Students who have paid their full fees",
        "amount_due",
        "==",
        "amount_paid",
    ),
]

# Insert KG filters
cursor.executemany("""
INSERT OR IGNORE INTO kg_filter
(
    filter_name,
    entity_id,
    description,
    left_field,
    operator,
    right_field
)
VALUES (?, ?, ?, ?, ?, ?)
""", filters)

# Create the KG tool mapping table
cursor.execute("""
CREATE TABLE IF NOT EXISTS kg_tool_mapping (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL,
    tool_name TEXT NOT NULL,
    description TEXT,
    FOREIGN KEY (entity_id)
        REFERENCES kg_entity(entity_id),
    UNIQUE (entity_id, tool_name)
)
""")

# Define tool mappings
tool_mappings = [
    (
        entity_ids["Student"],
        "query_students",
        "Retrieves student information"
    ),
    (
        entity_ids["Course"],
        "query_courses",
        "Retrieves course information"
    ),
    (
        entity_ids["Payment"],
        "query_payments",
        "Retrieves payment information"
    )
]

# Insert tool mappings
cursor.executemany("""
INSERT OR IGNORE INTO kg_tool_mapping
    (entity_id, tool_name, description)
VALUES (?, ?, ?)
""", tool_mappings)


# Save changes
conn.commit()
conn.close()

print("Knowledge Graph setup completed successfully!")