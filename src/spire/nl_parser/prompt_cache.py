"""Content-addressed Gemini context caches for the scoped parser prompt.

The scoped parser system prompt (assembled by router.assemble_subset for
the classified modules) is byte-identical across every parse call that
shares a scope, and it is the single largest input token cost in the
pipeline. Measured on the overnight run: 3,322-4,976 input tokens per
call, every call. Gemini's explicit context caching stores it once and
bills subsequent calls at a reduced rate.

WHY THE PROMPT HASH IS THE WHOLE KEY
    Two different scopes produce two different byte sequences; the same
    scope always produces the same bytes. So sha256(system_prompt) IS the
    cache identity. No registry, no version constant, no scope parameter.
    Rebuilding a .sysprompt block changes the bytes, changes the hash, a
    new cache is created, the old one expires on its own TTL.

WHY list() NOT create() ON THE FIRST LOOKUP
    Google assigns the cache id (cachedContents/<random>); display_name is
    only a label. So we cannot create a cache "at" a known name — we can
    only look for one by label. Doing list()-and-match on first lookup per
    process makes a concurrent run (MCP server + promptkit) reuse the cache
    the other one created instead of forking a duplicate. Subsequent calls
    in the same process read _memo and skip the list().

WHY system_instruction, NOT contents
    The parser prompt is INSTRUCTIONS (rules, examples, do-not-do-this
    clauses), not reference material. Putting instruction text in
    `contents` makes the model read it as prior conversation — and the
    model then answered with an empty target_entity and a bare refusal.
    The demo documents this split (see the caching examples: the
    instruction goes in system_instruction, the reference document in
    contents). For the parser there is no reference material: the whole
    prompt IS the instruction.

    The Gemini API forbids per-request system_instruction when
    cached_content is set; the instruction therefore lives IN the cache,
    not in each call. That is what makes the cached call legal.

WHY forget() EXISTS
    The memo is process-local and never re-checked once written, so a
    cache that dies before its TTL would be retried forever: the next
    call reads the same dead name from _memo, invoke_structured raises
    again, and the cache is silently off for the rest of the process.
    parser.py calls forget(cache_name) on every invoke failure, so the
    NEXT call re-lists and re-creates if needed. One failed call still
    falls through to LangChain — the forget only affects the call after.

WHAT A FAILURE MEANS
    get_or_create returns None when the content is below the model's
    minimum token count, the model has no caching, or quota/auth fails.
    Callers must treat None as "use the uncached path" — never as an
    error. The cost of a missed cache is what we already pay; the cost of
    a hard error is a broken pipeline.

STORAGE COST
    Gemini bills storage per token per hour for as long as the cache
    exists. TTL is 1 hour, chosen so a full overnight run reuses one cache
    and no cache lingers into the next day. release_all() deletes what this
    process created; it is not currently called — caches expire on their
    own TTL, so this is a storage optimisation, not a correctness
    requirement.
"""
from __future__ import annotations

import hashlib

from google import genai

from spire.config import GEMINI_MODEL


# Sourced from the same config the parser reads (GEMINI_MODEL), so a
# model change in one place moves the cache with it. Hardcoding this was
# a correctness bug waiting for a model swap: the cache would be created
# against one model and the parse call issued against another.
MODEL_NAME = GEMINI_MODEL

# 1 hour. Long enough for an overnight run's many prompts to share one
# cache, short enough that nothing lingers into the next day.
_CACHE_TTL = "3600s"

# The Google SDK may reject `contents=[]`; a placeholder that adds a
# token or two of context is invisible against 3-5k tokens of instruction.
# The cache KEY is a hash of system_prompt alone, so this placeholder
# does not affect cache identity or reuse.
_CONTENTS_PLACEHOLDER = "(see system_instruction)"


# Per-process memo: display_name -> full cache.name (cachedContents/<id>).
_memo: dict[str, str] = {}

# Caches THIS process created. Only these are released on shutdown.
_created: set[str] = set()


def _display_name(system_prompt: str) -> str:
    """Deterministic, human-readable label for a given prompt."""
    h = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()[:16]
    return f"spire-parser-{h}"


def _find_by_display_name(client, display_name: str) -> str | None:
    """Return the full cache.name whose display_name matches, or None."""
    try:
        for c in client.caches.list():
            if getattr(c, "display_name", None) == display_name:
                return c.name
    except Exception:
        return None
    return None


def get_or_create(system_prompt: str) -> str | None:
    """Return a cache name for this parser prompt, or None on failure.

    None means "use the uncached path" — the caller must not raise.
    """
    display_name = _display_name(system_prompt)

    if display_name in _memo:
        return _memo[display_name]

    try:
        client = genai.Client()
    except Exception:
        return None

    existing = _find_by_display_name(client, display_name)
    if existing is not None:
        _memo[display_name] = existing
        return existing

    try:
        cache = client.caches.create(
            model=MODEL_NAME,
            config={
                "display_name": display_name,
                # The prompt is INSTRUCTIONS. It goes here, not in
                # contents. The earlier attempt put it in contents and
                # the model produced an empty target_entity — a wrong
                # answer that looked like a legitimate refusal.
                "system_instruction": system_prompt,
                # Google may reject an empty list; a placeholder keeps
                # the request valid without affecting cache identity.
                "contents": [_CONTENTS_PLACEHOLDER],
                "ttl": _CACHE_TTL,
            },
        )
    except Exception:
        return None

    _memo[display_name] = cache.name
    _created.add(cache.name)
    return cache.name


def forget(cache_name: str) -> None:
    """Drop a dead cache name from the memo.

    Called by parser.parse() when invoke_structured raises against a name
    this process memoized. Without this, a cache that dies before its TTL
    is retried forever within the process: the next get_or_create returns
    the same dead name from _memo, invoke_structured raises again, and
    the cache is silently off for the rest of the process.

    Reverse-lookup by name rather than display_name-keyed, so the caller
    only has to know the name it just tried — not reconstruct the prompt
    hash that produced the memo entry.

    _created is left alone: the server-side cache may still exist, and
    release_all's delete is already safe against nonexistent names. The
    entry costs one dict slot and one swallowed exception at shutdown;
    removing it would orphan a live cache until its TTL.
    """
    dead = [d for d, n in _memo.items() if n == cache_name]
    for d in dead:
        del _memo[d]


def release_all() -> None:
    """Delete every cache this process created.

    Not currently wired into any call site. Caches expire on their own
    TTL, so this is a storage-cost optimisation, not a correctness
    requirement — safe to leave uncalled. Wire it into the MCP server's
    shutdown if the cache inventory ever grows large enough to matter.
    """
    if not _created:
        return
    try:
        client = genai.Client()
    except Exception:
        return
    for name in list(_created):
        try:
            client.caches.delete(name=name)
        except Exception:
            pass
    _created.clear()