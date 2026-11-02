
import sqlite3


DB_PATH = "college.db"


def query_students():
    """Retrieve all student records."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """
            SELECT student_id, name, email
            FROM students
            """
        ).fetchall()

        return [dict(row) for row in rows]


def query_courses():
    """Retrieve all course records."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """
            SELECT course_id, course_name, duration_years, total_fee
            FROM courses
            """
        ).fetchall()

        return [dict(row) for row in rows]


def query_payments():
    """Retrieve all payment records."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """
            SELECT payment_id, student_id, amount_due, amount_paid
            FROM payments
            """
        ).fetchall()

        return [dict(row) for row in rows]
