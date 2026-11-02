import sqlite3

# Connect to the existing database
conn = sqlite3.connect("college.db")

cursor = conn.cursor()

# Insert student records
students = [
    ("S1", "Moksha", "moksha@example.com"),
    ("S2", "Navya", "navya@example.com"),
    ("S3", "nishi", "nishi@example.com"),
    ("S4", "ammu", "ammu@example.com"),
    ("S5", "yagni", "yagni@example.com"),
]

cursor.executemany("""
INSERT OR IGNORE INTO students
(student_id, name, email)
VALUES (?, ?, ?)
""", students)


# Insert course records
courses = [
    ("C1", "ECE", 4, 50000),
    ("C2", "CSE", 4, 60000),
]

cursor.executemany("""
INSERT OR IGNORE INTO courses
(course_id, course_name, duration_years, total_fee)
VALUES (?, ?, ?, ?)
""", courses)


# Insert payment records
payments = [
    ("P1", "S1", 50000, 50000),
    ("P2", "S2", 60000, 40000),
    ("P3", "S3", 50000, 30000),
    ("P4", "S4", 60000, 60000),
    ("P5", "S5", 50000, 20000),
]

cursor.executemany("""
INSERT OR IGNORE INTO payments
(payment_id, student_id, amount_due, amount_paid)
VALUES (?, ?, ?, ?)
""", payments)


# Save all changes
conn.commit()

conn.close()

print("Sample data inserted successfully!")