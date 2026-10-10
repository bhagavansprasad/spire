import json
from datetime import datetime

import oracledb

from spire.config import PROMPT_CACHE_DURATION
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


def get_cache_duration() -> int:
    """
    Convert PROMPT_CACHE_DURATION from config into seconds.

    Supported values:
        "30s" -> 30 seconds
        "2d"  -> 172800 seconds
        "0"   -> cache forever
        "-1"  -> cache disabled
    """

    value = PROMPT_CACHE_DURATION.strip().lower()

    # Cache disabled
    if value == "-1":
        return -1

    # Cache forever
    if value == "0":
        return 0

    units = {
        "s": 1,
        "m": 60,
        "h": 60 * 60,
        "d": 24 * 60 * 60,
    }

    unit = value[-1]

    if unit not in units:
        raise ValueError(
            f"Invalid PROMPT_CACHE_DURATION: {PROMPT_CACHE_DURATION}. "
            f"Use values like 30s, 2d, 1h, 0, or -1."
        )

    try:
        amount = int(value[:-1])
    except ValueError:
        raise ValueError(
            f"Invalid PROMPT_CACHE_DURATION: {PROMPT_CACHE_DURATION}. "
            f"Use values like 30s, 2d, 1h, 0, or -1."
        )

    if amount <= 0:
        raise ValueError(
            f"Invalid PROMPT_CACHE_DURATION: {PROMPT_CACHE_DURATION}"
        )

    return amount * units[unit]


def get_intent(prompt: str) -> Intent | None:
    """
    Look up an Intent for a prompt.

    Returns:
        Intent -> valid cache hit
        None   -> cache miss or expired entry
    """

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT INTENT, CREATED_AT, DURATION
            FROM PROMPT_CACHE
            WHERE PROMPT = :p
            """,
            p=prompt,
        )

        row = cur.fetchone()

        if row is None:
            print("(local)[cache] MISS")
            return None

        intent_json, created_at, duration = row

        # DURATION = NULL means cache forever.
        if duration is not None:
            now = datetime.now()
            age = (now - created_at).total_seconds()

            #print(f"[CACHE] AGE = {age:.2f}s")
            #print(f"[CACHE] DURATION = {duration}s")

            if age > duration:
                #print("[CACHE] EXPIRED")

                cur.execute(
                    """
                    DELETE FROM PROMPT_CACHE
                    WHERE PROMPT = :p
                    """,
                    p=prompt,
                )

                conn.commit()

                return None

        intent_data = json.loads(intent_json)
        intent = Intent(**intent_data)

        print("(local)[cache] HIT")

        return intent

    finally:
        cur.close()
        conn.close()


def save_intent(
    prompt: str,
    intent: Intent,
    duration: int | None,
) -> None:
    """
    Save a successful Intent in the cache.

    duration:
        integer -> expiration in seconds
        None    -> cache forever
    """

    conn = get_conn()
    cur = conn.cursor()

    try:
        intent_json = json.dumps(intent.__dict__)
        created_at = datetime.now()

        cur.execute(
            """
            INSERT INTO PROMPT_CACHE (
                PROMPT,
                INTENT,
                CREATED_AT,
                DURATION
            )
            VALUES (
                :p,
                :i,
                :created_at,
                :d
            )
            """,
            p=prompt,
            i=intent_json,
            created_at=created_at,
            d=duration,
        )

        conn.commit()

        #print("[CACHE] SAVED")

    finally:
        cur.close()
        conn.close()
        