"""Extended cache probe: try three LangChain passthrough variants and one
raw google-genai control.

The first probe confirmed `bind(cached_content=...)` is a silent no-op.
This probe tries:

  A) ChatGoogleGenerativeAI(model=..., cached_content=...)  [constructor param]
  B) ChatGoogleGenerativeAI(model=..., model_kwargs={"cached_content": ...})
  C) raw google-genai client with cached_content + response_schema

C is the control. If A and B both fail but C succeeds, Option 2 is confirmed
as the only path. If A or B succeeds, Option 1 lives.
"""
from __future__ import annotations

import sys
import traceback
from importlib.metadata import version, PackageNotFoundError

MODEL_NAME = "gemini-3.5-flash"


def _print_versions():
    print("[0] versions")
    for pkg in ("langchain", "langchain-google-genai", "google-genai",
                "langchain-core", "pydantic"):
        try:
            print(f"    {pkg:30} {version(pkg)}")
        except PackageNotFoundError:
            print(f"    {pkg:30} (not installed)")


def _create_caches():
    from google import genai
    from spire.nl_parser.context_assembly import assemble_subset
    from spire.nl_parser.vocabulary import load_kg_menu

    menu = load_kg_menu()
    client = genai.Client()
    scopes = [["supplier"], ["procurement", "supplier"]]
    prompts, caches = {}, {}
    for scope in scopes:
        sp = assemble_subset(scope, menu)
        key = tuple(scope)
        prompts[key] = sp
        try:
            cache = client.caches.create(
                model=MODEL_NAME,
                config={"display_name": f"probe-{'_'.join(scope)}",
                        "contents": [sp], "ttl": "300s"},
            )
            caches[key] = cache.name
            print(f"    cache created for {key}: {cache.name}")
        except Exception as e:
            print(f"    cache create FAILED for {key}: {e}")
    return client, prompts, caches


def _report(label: str, raw) -> None:
    um = getattr(raw, "usage_metadata", None) or {}
    cached = (
        um.get("cached_content_token_count")
        or um.get("cached_tokens")
        or (um.get("input_token_details") or {}).get("cache_read")
        or 0
    )
    verdict = "HIT" if int(cached or 0) > 0 else "MISS"
    print(f"    [{label}] {verdict}  cached={cached}  input_tokens={um.get('input_tokens')}")


def _try_A(prompts, caches):
    print("\n[A] ChatGoogleGenerativeAI(model=..., cached_content=...)")
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from spire.nl_parser.draft import DraftIntent
    except Exception as e:
        print(f"    import failed: {e}")
        return

    for key, cache_name in caches.items():
        try:
            llm = ChatGoogleGenerativeAI(model=MODEL_NAME, cached_content=cache_name)
            structured = llm.with_structured_output(DraftIntent, include_raw=True)
            result = structured.invoke([("system", prompts[key]),
                                        ("human", "Show suppliers in US")])
            raw = result.get("raw") if isinstance(result, dict) else None
            _report(f"A scope={key}", raw)
        except Exception as e:
            print(f"    A scope={key} FAILED: {type(e).__name__}: {e}")


def _try_B(prompts, caches):
    print("\n[B] ChatGoogleGenerativeAI(model=..., model_kwargs={'cached_content': ...})")
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from spire.nl_parser.draft import DraftIntent
    except Exception as e:
        print(f"    import failed: {e}")
        return

    for key, cache_name in caches.items():
        try:
            llm = ChatGoogleGenerativeAI(
                model=MODEL_NAME,
                model_kwargs={"cached_content": cache_name},
            )
            structured = llm.with_structured_output(DraftIntent, include_raw=True)
            result = structured.invoke([("system", prompts[key]),
                                        ("human", "Show suppliers in US")])
            raw = result.get("raw") if isinstance(result, dict) else None
            _report(f"B scope={key}", raw)
        except Exception as e:
            print(f"    B scope={key} FAILED: {type(e).__name__}: {e}")


def _try_C(prompts, caches):
    """Control: raw google-genai, mirrors the demo scripts."""
    print("\n[C] raw google-genai client (control)")
    try:
        from google import genai
        from google.genai import types
        from spire.nl_parser.draft import DraftIntent
    except Exception as e:
        print(f"    import failed: {e}")
        return

    client = genai.Client()
    for key, cache_name in caches.items():
        try:
            resp = client.models.generate_content(
                model=MODEL_NAME,
                contents="Show suppliers in US",
                config=types.GenerateContentConfig(
                    cached_content=cache_name,
                    response_mime_type="application/json",
                    response_schema=DraftIntent,
                ),
            )
            um = getattr(resp, "usage_metadata", None)
            cached = getattr(um, "cached_content_token_count", None) or 0
            verdict = "HIT" if int(cached) > 0 else "MISS"
            print(f"    [C scope={key}] {verdict}  cached={cached}  "
                  f"input={getattr(um, 'prompt_token_count', '?')}")
        except Exception as e:
            print(f"    C scope={key} FAILED: {type(e).__name__}: {e}")


def main() -> int:
    _print_versions()

    print("\n[1] building scoped parser prompts + creating caches")
    try:
        client, prompts, caches = _create_caches()
    except Exception:
        traceback.print_exc()
        return 1
    if not caches:
        print("\nNo caches to test against. Exiting.")
        return 1

    _try_A(prompts, caches)
    _try_B(prompts, caches)
    _try_C(prompts, caches)

    print("\n[cleanup] deleting caches")
    for name in caches.values():
        try:
            client.caches.delete(name=name)
            print(f"    deleted {name}")
        except Exception as e:
            print(f"    delete failed {name}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())