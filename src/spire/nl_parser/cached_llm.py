"""Raw google-genai invocation with cached_content.

WHY THIS IS NOT LANGCHAIN

The Gemini API forbids combining cached_content with a per-request
system_instruction, tools, or tool_config::

    400 INVALID_ARGUMENT
    CachedContent can not be used with GenerateContent request setting
    system_instruction, tools or tool_config.

LangChain's ChatGoogleGenerativeAI.with_structured_output sends a system
message and, depending on configuration, tools. That combination is
exactly what the API refuses. Measured against gemini-3.5-flash: the
same request through the raw SDK succeeds with 99.8% of the prompt
served from cache; through LangChain it fails at the API.

So this module talks to the SDK directly, in JSON mode
(response_schema=...) rather than tool-calling, which is the one legal
combination alongside cached_content. It returns a dict shaped like
LangChain's with_structured_output(include_raw=True) return value, so
parser.parse() does not branch on which path ran.

THINKING TOKENS AND output_tokens

LangChain's AIMessage.usage_metadata["output_tokens"] is candidates plus
thoughts. The raw SDK exposes them as two separate fields
(candidates_token_count, thoughts_token_count). _RawResponse must sum
them to match, or the two paths report different quantities under the
same key and any cached-vs-uncached comparison is meaningless — which
is exactly what happened: an apparent "80% output drop" on the cached
path was the two paths logging different things, not the model
producing less.

gemini-3.5-flash thinks by default; no thinking_config is needed on the
cached path. A thinking_budget=1024 alongside cached_content is NOT a
fix and must not be added — the API accepts the parameter but silently
collapses thoughts_token_count to None, i.e. disables thinking. If a
future change ever wants to tune the budget for the cached path, the
only value that works is -1 (dynamic).
"""
from __future__ import annotations

from typing import Any

from google import genai
from google.genai import types

from spire.nl_parser.prompt_cache import MODEL_NAME


class _RawResponse:
    """Adapter that makes a google-genai response look like the LangChain
    AIMessage parse() already reads.

    parse() reads two things off `raw`:

      * ``raw.usage_metadata`` — dict-like, consumed by log_usage() and by
        the degenerate-parse guard
      * ``raw.response_metadata.finish_reason`` — consumed by the same guard
      * ``raw.content`` — read only on the degenerate-parse path

    google-genai exposes the same information under different names on
    different objects; the mapping here is deliberately narrow. Anything
    LangChain's normalized shape does not provide is left at a safe
    default (0 / None) rather than invented.
    """

    def __init__(self, resp: Any) -> None:
        self._resp = resp

        um = getattr(resp, "usage_metadata", None)

        # LangChain reports output_tokens as candidates + thoughts. The
        # raw SDK splits them. Sum here so the two paths log the same
        # quantity — see the module docstring.
        candidates = getattr(um, "candidates_token_count", 0) or 0
        thoughts = getattr(um, "thoughts_token_count", 0) or 0

        self.usage_metadata = {
            "input_tokens": getattr(um, "prompt_token_count", 0) or 0,
            "output_tokens": candidates + thoughts,
            "total_tokens": getattr(um, "total_token_count", 0) or 0,
            "input_token_details": {
                # This is the field that makes caching observable in the
                # logs. It mirrors LangChain's normalized cache_read.
                "cache_read": getattr(um, "cached_content_token_count", 0) or 0,
            },
        }

        fr = None
        candidates_list = getattr(resp, "candidates", None) or []
        if candidates_list:
            fr = getattr(candidates_list[0], "finish_reason", None)
            # google-genai returns a FinishReason enum; LangChain's
            # normalized form is a lowercase string ("stop"). Match that.
            if fr is not None and hasattr(fr, "name"):
                fr = fr.name
            if fr is not None:
                fr = str(fr).lower()
        self.response_metadata = {"finish_reason": fr}

    @property
    def content(self) -> str:
        # Only read on the degenerate-parse path, which writes the raw
        # text to traces/. Any failure here is that path's failure, so
        # return "" rather than raising.
        try:
            return self._resp.text or ""
        except Exception:
            return ""


def invoke_structured(prompt: str, schema: Any, cached_content: str) -> dict:
    """One structured-output call against a cached prompt.

    Args:
        prompt: The user's natural-language question (the VARIABLE part).
        schema: The Pydantic model to return (DraftIntent for the parser).
        cached_content: A cache name from prompt_cache.get_or_create().

    Returns:
        ``{"parsed": <schema instance | None>, "raw": <_RawResponse>}`` —
        the same shape LangChain's with_structured_output(include_raw=True)
        returns, so parser.parse() is identical for both paths.

    Raises:
        Anything the SDK raises. The caller in parser.py catches Exception
        and falls back to the uncached LangChain path; a broken cache
        (expired mid-run, quota revoked) costs a slow call, not a broken
        pipeline.

    No system_instruction is sent — it lives inside cached_content. The
    response_schema route is JSON mode rather than tool-calling, which is
    what makes the request legal alongside cached_content.

    No thinking_config is sent either. gemini-3.5-flash thinks by
    default, and setting thinking_budget=1024 alongside cached_content
    would silently disable thinking. See the module docstring.
    """
    client = genai.Client()
    resp = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            cached_content=cached_content,
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )

    parsed = getattr(resp, "parsed", None)
    if parsed is None:
        # The current SDK populates .parsed when response_schema is set,
        # but be defensive — if a version stops doing so, parse the text
        # ourselves rather than silently returning None.
        try:
            import json

            text = resp.text or ""
            parsed = (
                schema.model_validate(json.loads(text)) if text.strip() else None
            )
        except Exception:
            parsed = None

    return {"parsed": parsed, "raw": _RawResponse(resp)}