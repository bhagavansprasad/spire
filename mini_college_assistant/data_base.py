import sqlite3

# Create a database file
connection = sqlite3.connect("college.db")

# Create a cursor to execute SQL commands
cursor = connection.cursor()

# Table 1: Students
cursor.execute("""
CREATE TABLE IF NOT EXISTS students (
    student_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE
)
""")

# Table 2: Courses
cursor.execute("""
CREATE TABLE IF NOT EXISTS courses (
    course_id TEXT PRIMARY KEY,
    course_name TEXT NOT NULL,
    duration_years INTEGER,
    total_fee REAL NOT NULL
)
""")

# Table 3: Payments
cursor.execute("""
CREATE TABLE IF NOT EXISTS payments (
    payment_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    amount_due REAL NOT NULL,
    amount_paid REAL NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(student_id)
)
""")

# Save the changes
connection.commit()

# Close the database connection
connection.close()

print("College database and tables created successfully!")