import json

import redis

from spire.planner.models import Intent
from spire.config import REDIS_CACHE_DURATION

redis_client = redis.Redis(
    host="localhost",
    port=6379,
    decode_responses=True,
)

def get_redis_cache_duration() -> int:
    value = REDIS_CACHE_DURATION.strip().lower()

    units = {
        "s": 1,
        "m": 60,
        "h": 60 * 60,
        "d": 24 * 60 * 60,
    }

    unit = value[-1]

    if unit not in units:
        raise ValueError(
            f"Invalid REDIS_CACHE_DURATION: {REDIS_CACHE_DURATION}. "
            f"Use values like 30s, 5m, 1h, or 2d."
        )

    try:
        amount = int(value[:-1])
    except ValueError:
        raise ValueError(
            f"Invalid REDIS_CACHE_DURATION: {REDIS_CACHE_DURATION}"
        )

    if amount <= 0:
        raise ValueError(
            f"Invalid REDIS_CACHE_DURATION: {REDIS_CACHE_DURATION}"
        )

    return amount * units[unit]

def save_intent(prompt: str, intent: Intent, duration: int | None = None) -> None:
    key = f"prompt_intent:{prompt}"

    intent_json = json.dumps(intent.__dict__)
    duration = get_redis_cache_duration()
    
    if duration is None:
        redis_client.set(key, intent_json)
    else:
        redis_client.set(key, intent_json, ex=duration)


def get_intent(prompt: str) -> Intent | None:
    key = f"prompt_intent:{prompt}"

    intent_json = redis_client.get(key)

    if intent_json is None:
        print("[REDIS cache] MISS")
        return None

    intent_data = json.loads(intent_json)
    intent = Intent(**intent_data)

    print("[REDIS cache] HIT")
    return intent


def delete_intent(prompt: str) -> None:
    key = f"prompt_intent:{prompt}"

    redis_client.delete(key)