import json
import oracledb

from spire.planner.models import Intent


DB_USER = "spire"
DB_PASS = "jnjnuh"
DB_DSN = "localhost:1521/FREEPDB1"


def get_conn():
    return oracledb.connect(
        user=DB_USER,
        password=DB_PASS,
        dsn=DB_DSN,
    )


def get_intent(prompt: str) -> Intent | None:
    """
    Look for the prompt in PROMPT_CACHE.

    Returns:
        Intent -> cache HIT
        None   -> cache MISS
    """

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT INTENT
            FROM PROMPT_CACHE
            WHERE PROMPT = :p
            """,
            p=prompt,
        )

        row = cur.fetchone()

        if row is None:
            print("[CACHE] MISS")
            return None

        intent_json = row[0]

        data = json.loads(intent_json) #converts the json string to a dictionary

        intent = Intent(**data) # ** means take the dict keys and  pass them as keyword arguments
        print("[CACHE] HIT")

        return intent

    finally:
        cur.close()
        conn.close()


def save_intent(prompt: str, intent: Intent) -> None:
    """
    Store a prompt and its Intent in PROMPT_CACHE.
    """

    conn = get_conn()
    cur = conn.cursor()

    try:
        intent_json = json.dumps(intent.__dict__)

        cur.execute(
            """
            INSERT INTO PROMPT_CACHE (PROMPT, INTENT)
            VALUES (:p, :i)
            """,
            p=prompt,
            i=intent_json,
        )

        conn.commit()

        print("[CACHE] SAVED")

    finally:
        cur.close()
        conn.close()
