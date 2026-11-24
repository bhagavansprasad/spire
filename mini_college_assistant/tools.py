
import sqlite3

DB_PATH = "people_organization.db"


def query_people():
    """Retrieve all people."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT PERSON_ID, NAME, CITY, AGE
            FROM PERSON
        """).fetchall()

        return [dict(row) for row in rows]


def query_organizations():
    """Retrieve all organizations."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT ORG_ID, ORG_NAME, INDUSTRY
            FROM ORGANIZATION
        """).fetchall()

        return [dict(row) for row in rows]


def query_works_for():
    """Retrieve people and the organizations they work for."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT
                P.PERSON_ID,
                P.NAME,
                P.CITY,
                P.AGE,
                O.ORG_ID,
                O.ORG_NAME,
                O.INDUSTRY,
                R.ROLE,
                R.SINCE
            FROM PERSON P
            JOIN ROLE_ASSIGNMENT R
                ON P.PERSON_ID = R.PERSON_ID
            JOIN ORGANIZATION O
                ON R.ORG_ID = O.ORG_ID
        """).fetchall()

        return [dict(row) for row in rows]


def query_knows():
    """Retrieve people and the people they know."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT
                P1.PERSON_ID,
                P1.NAME AS PERSON_NAME,
                P1.CITY AS PERSON_CITY,
                P1.AGE AS PERSON_AGE,
                P2.PERSON_ID AS KNOWS_PERSON_ID,
                P2.NAME AS KNOWS_PERSON_NAME,
                K.SINCE
            FROM KNOWS K
            JOIN PERSON P1
                ON K.PERSON_ID = P1.PERSON_ID
            JOIN PERSON P2
                ON K.KNOWS_PERSON_ID = P2.PERSON_ID
        """).fetchall()

        return [dict(row) for row in rows]
