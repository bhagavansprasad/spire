
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


def query_exam_results():
    """Retrieve examination results with student names and pass/fail status."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """
            SELECT
                s.name AS student_name,
                e.exam_name,
                er.marks_obtained,
                e.pass_marks,
                e.max_marks,
                CASE
                    WHEN er.marks_obtained >= e.pass_marks
                    THEN 'PASS'
                    ELSE 'FAIL'
                END AS result
            FROM exam_results er
            JOIN exams e
                ON er.exam_id = e.exam_id
            JOIN students s
                ON er.student_id = s.student_id
            """
        ).fetchall()

        return [dict(row) for row in rows]
