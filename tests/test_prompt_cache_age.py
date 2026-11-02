import time
from datetime import datetime

from spire.graph.pipeline import parse_node


def run_prompt(prompt: str):
    state = {
        "prompt": prompt,
        "menu": None,
    }

    start = time.perf_counter()
    print(f"START TIME : {datetime.now().strftime('%H:%M:%S')}")

    result = parse_node(state)

    end = time.perf_counter()

    print(f"END TIME   : {datetime.now().strftime('%H:%M:%S')}")
    print(f"ELAPSED    : {end - start:.2f} seconds")

    print("\nRESULT:")
    print(result)


# ============================================================
# CASE 1
# First request
# Expected: MISS -> LLM -> SAVE
# ============================================================

print("\n" + "=" * 60)
print("CASE 1: FIRST REQUEST")
print("=" * 60)

prompt = "Show me all suppliers"

run_prompt(prompt)


# ============================================================
# CASE 2
# Same request immediately
# Expected: HIT
# ============================================================

print("\n" + "=" * 60)
print("CASE 2: SECOND REQUEST WITHIN 30 SECONDS")
print("=" * 60)

run_prompt(prompt)


# ============================================================
# CASE 3
# Wait 31 seconds
# Expected: EXPIRED -> LLM -> SAVE
# ============================================================

print("\n" + "=" * 60)
print("CASE 3: REQUEST AFTER EXPIRATION")
print("=" * 60)

print(f"WAIT START : {datetime.now().strftime('%H:%M:%S')}")

time.sleep(31)

print(f"WAIT END   : {datetime.now().strftime('%H:%M:%S')}")

run_prompt(prompt)


# ============================================================
# CASE 4
# NULL duration
# Expected: MISS -> LLM -> SAVE
# Then after 31 sec -> HIT
# ============================================================

print("\n" + "=" * 60)
print("CASE 4: NULL DURATION")
print("=" * 60)

null_prompt = "Show me all suppliers NULL"

print("\n--- FIRST NULL REQUEST ---")

run_prompt(null_prompt)

print("\nWaiting 31 seconds...")

print(f"WAIT START : {datetime.now().strftime('%H:%M:%S')}")

time.sleep(31)

print(f"WAIT END   : {datetime.now().strftime('%H:%M:%S')}")

print("\n--- SECOND NULL REQUEST ---")

run_prompt(null_prompt)