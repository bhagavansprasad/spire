"""One-shot probe: does Gemini context caching work through LangChain
for the scoped parser prompt?

Answers three questions at once:

  1. Does client.caches.create() work on this model for a scoped parser
     prompt (i.e. is the content above the minimum token floor)?
  2. Does llm.bind(cached_content=cache) survive with_structured_output?
  3. Does the response actually carry a cached-token count > 0?

Run from repo root with the venv active:

    python scripts/probe_cache.py
"""
from __future__ import annotations

import sys
import traceback

MODEL_NAME = "gemini-3.5-flash"


def main() -> int:
    # ---- step 0: imports ----
    print("[0] imports")
    try:
        from google import genai
        from spire.config import build_llm
        from spire.nl_parser.context_assembly import assemble_subset
        from spire.nl_parser.vocabulary import load_kg_menu
        from spire.nl_parser.draft import DraftIntent
        print("    ok")
    except Exception:
        print("    FAILED:")
        traceback.print_exc()
        return 1

    # ---- step 1: build scoped parser prompts ----
    print("\n[1] build scoped parser prompts")
    try:
        menu = load_kg_menu()
        scopes = [["supplier"], ["procurement", "supplier"]]
        system_prompts: dict[tuple, str] = {}
        for scope in scopes:
            sp = assemble_subset(scope, menu)
            system_prompts[tuple(scope)] = sp
            # chars / 4 is the standard rough token heuristic
            print(f"    scope={scope!r:40}  chars={len(sp):>6,}  ~tokens≈{len(sp)//4:>6,}")
    except Exception:
        print("    FAILED:")
        traceback.print_exc()
        return 1

    # ---- step 2: create one cache per scope ----
    print("\n[2] create one cache per scope")
    client = genai.Client()
    caches: dict[tuple, str] = {}
    for scope, sp in system_prompts.items():
        name = f"spire-probe-{'_'.join(scope)}"
        try:
            cache = client.caches.create(
                model=MODEL_NAME,
                config={
                    "display_name": name,
                    "contents": [sp],
                    "ttl": "300s",
                },
            )
            caches[scope] = cache.name
            print(f"    {scope!r} -> created")
            print(f"        cache.name = {cache.name}")
        except Exception as e:
            print(f"    {scope!r} -> create FAILED: {type(e).__name__}: {e}")

    if not caches:
        print("\nNo caches created. Nothing else to probe. Exiting.")
        return 1

    # ---- step 3: llm.bind + with_structured_output ----
    print("\n[3] llm.bind(cached_content=...) + with_structured_output")
    try:
        llm = build_llm()
    except TypeError:
        # Some versions take a temperature positional.
        try:
            llm = build_llm(0.0)
        except Exception:
            print("    build_llm() FAILED:")
            traceback.print_exc()
            return 1

    for scope, cache_name in caches.items():
        print(f"\n    --- scope={scope!r} ---")

        # 3a: bind
        try:
            llm_cached = llm.bind(cached_content=cache_name)
            print("    bind(cached_content=...)          ok")
        except Exception:
            print("    bind(cached_content=...)          FAILED:")
            traceback.print_exc()
            continue

        # 3b: with_structured_output
        try:
            structured = llm_cached.with_structured_output(DraftIntent, include_raw=True)
            print("    with_structured_output           ok")
        except Exception:
            print("    with_structured_output           FAILED:")
            traceback.print_exc()
            continue

        # 3c: invoke
        try:
            result = structured.invoke([
                ("system", system_prompts[scope]),
                ("human", "Show suppliers in US"),
            ])
            print("    invoke                            ok")
        except Exception:
            print("    invoke                            FAILED:")
            traceback.print_exc()
            continue

        # 3d: inspect usage
        if isinstance(result, dict):
            raw = result.get("raw")
            parsed = result.get("parsed")
        else:
            raw = None
            parsed = result
        print(f"    parsed intent: {parsed}")

        if raw is None:
            print("    no raw AIMessage — cannot read usage_metadata")
            continue

        um = getattr(raw, "usage_metadata", None) or {}
        print(f"    usage_metadata = {um}")

        # google-genai reports 'cached_content_token_count'; LangChain may
        # normalize to 'input_token_details' / 'cache_read'. Print whatever
        # is there so we can see the shape.
        cached = (
            um.get("cached_content_token_count")
            or um.get("cached_tokens")
            or (um.get("input_token_details") or {}).get("cache_read")
            or 0
        )
        verdict = "CACHE HIT" if cached and int(cached) > 0 else "NO CACHE HIT"
        print(f"    >>> {verdict} (cached = {cached})")

    # ---- step 4: cleanup ----
    print("\n[4] delete caches")
    for cache_name in caches.values():
        try:
            client.caches.delete(name=cache_name)
            print(f"    {cache_name}  deleted")
        except Exception as e:
            print(f"    {cache_name}  delete FAILED: {e}")

    print("\ndone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())