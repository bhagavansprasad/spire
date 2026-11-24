
import sqlite3

# Connect to the new database
conn = sqlite3.connect("people_organization.db")

# Enable foreign key checking
conn.execute("PRAGMA foreign_keys = ON")

cursor = conn.cursor()

try:
    # 1. Insert PERSON records
    people = [
        (1, "Arjun", "Bangalore", 32),
        (2, "Priya", "Mumbai", 28),
        (3, "Ravi", "Chennai", 35),
        (4, "Sneha", "Hyderabad", 40),
        (5, "Vikram", "Pune", 27),
        (6, "Meena", "Delhi", 31),
        (7, "Kiran", "Kolkata", 29),
        (8, "Suresh", "Ahmedabad", 38),
    ]

    cursor.executemany("""
        INSERT OR IGNORE INTO PERSON
        (PERSON_ID, NAME, CITY, AGE)
        VALUES (?, ?, ?, ?)
    """, people)


    # 2. Insert ORGANIZATION records
    organizations = [
        (1, "Infosys", "Technology"),
        (2, "TCS", "Consulting"),
        (3, "Wipro", "Cloud"),
    ]

    cursor.executemany("""
        INSERT OR IGNORE INTO ORGANIZATION
        (ORG_ID, ORG_NAME, INDUSTRY)
        VALUES (?, ?, ?)
    """, organizations)


    # 3. Insert ROLE_ASSIGNMENT records
    role_assignments = [
        (1, 1, "Engineer", 2019),
        (2, 1, "Manager", 2020),
        (3, 2, "Analyst", 2021),
        (4, 3, "Architect", 2018),
        (5, 1, "Developer", 2022),
        (6, 2, "Engineer", 2020),
        (7, 3, "Designer", 2021),
        (8, 2, "Consultant", 2019),
    ]

    cursor.executemany("""
        INSERT OR IGNORE INTO ROLE_ASSIGNMENT
        (PERSON_ID, ORG_ID, ROLE, SINCE)
        VALUES (?, ?, ?, ?)
    """, role_assignments)


    # 4. Insert KNOWS relationships
    knows = [
        (1, 2, 2018),
        (2, 3, 2019),
        (3, 4, 2020),
        (1, 5, 2017),
        (5, 6, 2018),
        (6, 7, 2019),
        (7, 8, 2020),
        (4, 8, 2021),
    ]

    cursor.executemany("""
        INSERT OR IGNORE INTO KNOWS
        (PERSON_ID, KNOWS_PERSON_ID, SINCE)
        VALUES (?, ?, ?)
    """, knows)


    # Save all changes
    conn.commit()

    print("People & Organizations data inserted successfully!")

except sqlite3.Error:
    conn.rollback()
    raise

finally:
    conn.close()
