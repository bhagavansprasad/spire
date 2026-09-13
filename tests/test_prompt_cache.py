"""The parser's Gemini cache path — default-on, opt-out.

Three things verified here:

  1. cache module mechanics: reuse by display_name, per-process memo,
     failure returns None (never raises), forget() clears the memo so
     the next call re-lists;
  2. the parse() gate: an injected LLM always goes through LangChain
     (this is what keeps every test in the suite on the mocked path);
  3. the parse() gate: with llm=None, the cached path is attempted by
     default; setting SPIRE_PROMPT_CACHE_DISABLE=1 skips it; any failure
     in the cached path falls back to LangChain AND clears the memo so
     the next call is not silently served a dead cache name.

What this file does NOT test: the actual Gemini API. The real hit rate
(~99% on a scoped parser prompt) was measured once; the module tests
below use a fake client, and the gate tests monkeypatch the two
imports parse() performs lazily.
"""
from __future__ import annotations

import pytest

from spire.nl_parser import parser as parser_mod


# ---- module-level state reset --------------------------------------------


@pytest.fixture(autouse=True)
def _reset_cache_module_state():
    """Clear the prompt_cache module's in-process memo between tests."""
    from spire.nl_parser import prompt_cache as pc

    pc._memo.clear()
    pc._created.clear()
    yield
    pc._memo.clear()
    pc._created.clear()


@pytest.fixture(autouse=True)
def _clear_cache_env(monkeypatch):
    """Cut every test off from the developer's environment.

    Both vars matter: SPIRE_PROMPT_CACHE is a legacy name from when the
    path was opt-in (kept clear so a stray value cannot change behaviour),
    and SPIRE_PROMPT_CACHE_DISABLE is the current opt-out. Tests that
    want to exercise the disabled path set the latter explicitly.
    """
    monkeypatch.delenv("SPIRE_PROMPT_CACHE", raising=False)
    monkeypatch.delenv("SPIRE_PROMPT_CACHE_DISABLE", raising=False)


# ---- fake google-genai client --------------------------------------------


class _FakeCache:
    def __init__(self, name: str, display_name: str) -> None:
        self.name = name
        self.display_name = display_name


class _FakeCaches:
    def __init__(self) -> None:
        self.stored: list[_FakeCache] = []
        self.list_calls = 0
        self.create_calls = 0
        self.delete_calls = 0
        self.fail_create = False

    def list(self):
        self.list_calls += 1
        return list(self.stored)

    def create(self, *, model, config):
        self.create_calls += 1
        if self.fail_create:
            raise RuntimeError("simulated create failure")
        c = _FakeCache(
            f"cachedContents/test-{self.create_calls}",
            config["display_name"],
        )
        self.stored.append(c)
        return c

    def delete(self, *, name):
        self.delete_calls += 1
        self.stored = [c for c in self.stored if c.name != name]


class _FakeClient:
    def __init__(self, caches: _FakeCaches) -> None:
        self.caches = caches


@pytest.fixture
def fake_genai(monkeypatch):
    """Patch spire.nl_parser.prompt_cache.genai.Client to a fake."""
    from spire.nl_parser import prompt_cache as pc

    fake_caches = _FakeCaches()
    fake_client = _FakeClient(fake_caches)
    monkeypatch.setattr(pc.genai, "Client", lambda: fake_client)
    return fake_caches


# ---- prompt_cache unit tests ---------------------------------------------


def test_get_or_create_returns_none_when_create_fails(fake_genai):
    from spire.nl_parser.prompt_cache import get_or_create

    fake_genai.fail_create = True
    assert get_or_create("some prompt text") is None


def test_get_or_create_creates_and_memoizes(fake_genai):
    from spire.nl_parser.prompt_cache import get_or_create

    name1 = get_or_create("prompt A")
    name2 = get_or_create("prompt A")

    assert name1 is not None
    assert name1 == name2
    # Second call for the same prompt hits the memo, not list/create.
    assert fake_genai.list_calls == 1
    assert fake_genai.create_calls == 1


def test_get_or_create_reuses_existing_by_display_name(fake_genai):
    """A cache created by a previous process is found via list()."""
    from spire.nl_parser.prompt_cache import get_or_create, _display_name

    display = _display_name("prompt B")
    fake_genai.stored.append(_FakeCache("cachedContents/preexisting", display))

    name = get_or_create("prompt B")

    assert name == "cachedContents/preexisting"
    assert fake_genai.create_calls == 0


def test_get_or_create_distinct_prompts_distinct_caches(fake_genai):
    from spire.nl_parser.prompt_cache import get_or_create

    a = get_or_create("prompt A")
    b = get_or_create("prompt B")

    assert a != b
    assert fake_genai.create_calls == 2


def test_release_all_deletes_created_caches(fake_genai):
    from spire.nl_parser.prompt_cache import get_or_create, release_all

    get_or_create("prompt A")
    get_or_create("prompt B")
    release_all()

    assert fake_genai.delete_calls == 2
    assert fake_genai.stored == []


def test_release_all_is_a_noop_when_nothing_created(fake_genai):
    from spire.nl_parser.prompt_cache import release_all

    release_all()
    assert fake_genai.delete_calls == 0


# ---- forget() — the memo-invalidation fix --------------------------------


def test_forget_removes_memo_entry(fake_genai):
    """forget() clears the memo so the NEXT get_or_create re-lists.

    The bug this fixes: after the TTL expired in a long-running process,
    _memo kept serving the dead name and invoke_structured raised on
    every call. The cache was silently off after the first hour.
    """
    from spire.nl_parser.prompt_cache import get_or_create, forget, _memo

    name = get_or_create("prompt A")
    assert _memo, "precondition: memo populated"

    forget(name)
    assert not _memo, "forget must clear the entry"

    get_or_create("prompt A")
    assert fake_genai.list_calls == 2, "next call must re-list, not reuse memo"


def test_forget_unknown_name_is_a_noop(fake_genai):
    from spire.nl_parser.prompt_cache import get_or_create, forget, _memo

    get_or_create("prompt A")
    before = dict(_memo)
    forget("cachedContents/does-not-exist")
    assert _memo == before


# ---- parser.py gate tests ------------------------------------------------


class _StubLLM:
    """Minimal LLM whose with_structured_output().invoke() returns a sentinel.

    We only care that the LangChain path is taken; the return value is
    ignored beyond proving the branch was entered.
    """

    def __init__(self) -> None:
        self.called = False

    def with_structured_output(self, schema, **kwargs):
        return self

    def invoke(self, messages):
        self.called = True
        return {"parsed": None, "raw": None, "parsing_error": "stub"}


def test_injected_llm_uses_langchain(monkeypatch):
    """The `llm is None` guard keeps every mocked-LLM test on LangChain.

    This is the single most important invariant of the cache path: the
    979 tests that inject a MockLLM must never be routed at the network
    by the cache, no matter what the environment says. Two env states
    exercised here: default (no flag), and disable-flag set. Both must
    run the injected LLM.
    """
    llm = _StubLLM()
    result = parser_mod.parse("test prompt", llm=llm, menu=_stub_menu())
    assert llm.called is True
    # _StubLLM returns parsed=None, so parse refuses.
    assert result.is_refusal


def test_injected_llm_ignores_disable_flag(monkeypatch):
    """Disable-flag set + injected LLM → still LangChain."""
    monkeypatch.setenv("SPIRE_PROMPT_CACHE_DISABLE", "1")
    llm = _StubLLM()
    parser_mod.parse("test prompt", llm=llm, menu=_stub_menu())
    assert llm.called is True


def test_cache_is_attempted_by_default(monkeypatch):
    """No env var set + no LLM injected → cache path is attempted.

    Forces get_or_create to return a name and invoke_structured to
    succeed with a sentinel dict; the LangChain path must NOT run.
    """
    from spire.nl_parser import prompt_cache, cached_llm

    called = {"cache": False}

    def fake_get_or_create(sp):
        called["cache"] = True
        return "cachedContents/fake"

    monkeypatch.setattr(prompt_cache, "get_or_create", fake_get_or_create)
    monkeypatch.setattr(
        cached_llm, "invoke_structured",
        lambda prompt, schema, cache: {"parsed": None, "raw": None},
    )

    fallback = _StubLLM()
    monkeypatch.setattr("spire.config.build_llm", lambda *a, **kw: fallback)

    parser_mod.parse("test prompt", llm=None, menu=_stub_menu())

    assert called["cache"] is True
    assert fallback.called is False, "LangChain path should be skipped"


def test_cache_disable_flag_skips_the_cache(monkeypatch):
    """SPIRE_PROMPT_CACHE_DISABLE=1 → LangChain only.

    Forces the disable flag; get_or_create must not be called, and the
    LangChain path must run.
    """
    monkeypatch.setenv("SPIRE_PROMPT_CACHE_DISABLE", "1")

    from spire.nl_parser import prompt_cache

    called = {"cache": False}

    def fake_get_or_create(sp):
        called["cache"] = True
        return "cachedContents/fake"

    monkeypatch.setattr(prompt_cache, "get_or_create", fake_get_or_create)

    fallback = _StubLLM()
    monkeypatch.setattr("spire.config.build_llm", lambda *a, **kw: fallback)

    parser_mod.parse("test prompt", llm=None, menu=_stub_menu())

    assert called["cache"] is False
    assert fallback.called is True


def test_cache_failure_falls_back_to_langchain(monkeypatch):
    """A None from get_or_create → LangChain.

    That is the documented failure contract: get_or_create returns None
    when it cannot produce a cache (below minimum tokens, quota, network)
    and the caller treats None as "use the uncached path", never as an
    error.
    """
    from spire.nl_parser import prompt_cache

    monkeypatch.setattr(prompt_cache, "get_or_create", lambda sp: None)

    fallback = _StubLLM()
    monkeypatch.setattr("spire.config.build_llm", lambda *a, **kw: fallback)

    result = parser_mod.parse("test prompt", llm=None, menu=_stub_menu())
    assert fallback.called is True
    assert result.is_refusal  # _StubLLM returned parsed=None


def test_cache_invoke_failure_calls_forget(monkeypatch):
    """parser.parse() must call forget() when invoke_structured raises.

    Tested at the parser level (not the module level) because the fix
    spans both — the module offers forget(), the parser calls it. A
    module-only test would pass even if parser.py forgot to wire it up.
    """
    from spire.nl_parser import prompt_cache, cached_llm

    forgotten: list[str] = []

    monkeypatch.setattr(
        prompt_cache, "get_or_create", lambda sp: "cachedContents/dead"
    )
    monkeypatch.setattr(
        prompt_cache, "forget", lambda name: forgotten.append(name)
    )

    def fake_invoke(prompt, schema, cache_name):
        raise RuntimeError("simulated expiry")

    monkeypatch.setattr(cached_llm, "invoke_structured", fake_invoke)

    fallback = _StubLLM()
    monkeypatch.setattr("spire.config.build_llm", lambda *a, **kw: fallback)

    parser_mod.parse("test prompt", llm=None, menu=_stub_menu())

    assert forgotten == ["cachedContents/dead"]
    assert fallback.called is True, "this call must still fall through"


def test_dead_cache_is_not_retried(monkeypatch, fake_genai):
    """End-to-end regression: after invoke raises, the NEXT parse re-lists.

    Uses the real prompt_cache (backed by the fake genai client) so the
    memo is the real one, not a mock. Without the fix, list_calls would
    stay at 1 across both parses and the dead name would be reused.
    """
    from spire.nl_parser import cached_llm

    should_raise = {"value": True}

    def fake_invoke(prompt, schema, cache_name):
        if should_raise["value"]:
            raise RuntimeError("simulated expiry")
        return {"parsed": None, "raw": None}

    monkeypatch.setattr(cached_llm, "invoke_structured", fake_invoke)

    fallback = _StubLLM()
    monkeypatch.setattr("spire.config.build_llm", lambda *a, **kw: fallback)

    # First parse: create succeeds, invoke fails, forget fires.
    parser_mod.parse("test prompt", llm=None, menu=_stub_menu())
    assert fake_genai.create_calls == 1
    assert fake_genai.list_calls == 1

    # Second parse: memo was cleared, so get_or_create lists again.
    should_raise["value"] = False
    parser_mod.parse("test prompt", llm=None, menu=_stub_menu())

    assert fake_genai.list_calls == 2, (
        "second parse must re-list; if it stays at 1, the memo was not "
        "cleared and the cache is silently off for the rest of the process"
    )


# ---- _RawResponse shape contract ----------------------------------------


def test_raw_response_shape():
    """Pin the three fields parser.py reads off the raw SDK response.

    parser.py reads raw.usage_metadata (for log_usage and the cache
    diagnostic), raw.response_metadata['finish_reason'] (the
    degenerate-parse guard), and raw.content (only on that guard's
    failure path). An SDK rename would break this at runtime, silently
    and rarely. Pinning it here makes the next SDK bump a failing test,
    not a wrong answer.
    """
    from spire.nl_parser.cached_llm import _RawResponse

    class _UM:
        prompt_token_count = 100
        candidates_token_count = 50
        total_token_count = 150
        cached_content_token_count = 80

    class _FR:
        name = "STOP"

    class _Cand:
        finish_reason = _FR()

    class _Resp:
        usage_metadata = _UM()
        candidates = [_Cand()]
        text = "the answer"

    raw = _RawResponse(_Resp())

    assert raw.usage_metadata == {
        "input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 150,
        "input_token_details": {"cache_read": 80},
    }
    assert raw.response_metadata == {"finish_reason": "stop"}
    assert raw.content == "the answer"


def test_raw_response_handles_missing_usage():
    """Defensive: a response with no usage_metadata must not crash the
    adapter. parse() reads these fields unconditionally on the cached
    path, so a None here is a broken answer, not a caught exception."""
    from spire.nl_parser.cached_llm import _RawResponse

    class _Resp:
        usage_metadata = None
        candidates = []
        text = ""

    raw = _RawResponse(_Resp())

    assert raw.usage_metadata["input_tokens"] == 0
    assert raw.usage_metadata["input_token_details"]["cache_read"] == 0
    assert raw.response_metadata["finish_reason"] is None
    assert raw.content == ""


# ---- minimal KGMenu fixture ----------------------------------------------


def _stub_menu():
    """A KGMenu whose lookup methods all answer 'yes' to reach the LLM step.

    The gate tests do not exercise entity/filter validation; they only
    need parse() to get past the menu load and into the LLM call.
    """
    from spire.nl_parser.vocabulary import KGMenu

    return KGMenu(
        target_entities={"Supplier"},
        filter_types={"country"},
        entity_descriptions={"Supplier": "A vendor."},
        country_terms={"US": "US"},
    )