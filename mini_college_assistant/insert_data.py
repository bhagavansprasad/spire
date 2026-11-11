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



# Insert examination data
cursor.executemany("""
INSERT OR IGNORE INTO exams
(exam_id, course_id, exam_name, pass_marks, max_marks)
VALUES (?, ?, ?, ?, ?)
""", [
    ("E1", "C1", "Embedded Systems", 40, 100),
    ("E2", "C1", "Digital Electronics", 40, 100),
    ("E3", "C2", "Python Programming", 35, 100),
    ("E4", "C2", "Database Management", 35, 100)
])


# Insert examination results
cursor.executemany("""
INSERT OR IGNORE INTO exam_results
(result_id, exam_id, student_id, marks_obtained)
VALUES (?, ?, ?, ?)
""", [
    ("R1", "E1", "S1", 85),
    ("R2", "E2", "S1", 32),

    ("R3", "E1", "S2", 30),
    ("R4", "E2", "S2", 75),

    ("R5", "E1", "S3", 65),
    ("R6", "E2", "S3", 55),

    ("R7", "E3", "S4", 90),
    ("R8", "E4", "S4", 25),

    ("R9", "E3", "S5", 20),
    ("R10", "E4", "S5", 80)
])



# Save all changes
conn.commit()

conn.close()

print("Sample data inserted successfully!")