"""Unit tests for the module-scoping router's classifier (Phase 2, step 3).

These test ``classify_modules`` in isolation with a mock LLM — no DB, no API
key, no real model. The mock mirrors the LangChain structured-output surface
``parse()`` also uses: ``with_structured_output(Schema, include_raw=True)``
returns an object whose ``invoke(messages)`` yields either a dict with
``"parsed"``/``"raw"`` keys (the real include_raw shape) or a bare model.

Coverage:
- the happy path returns the classified module as a list (D1);
- an empty or unknown classification RAISES (decision 3a — no fallback yet);
- both the dict-with-"parsed" and bare-model return shapes are handled;
- duplicate module names are de-duplicated;
- the grounding menu is injected into the system prompt (the classify seam).
"""

from __future__ import annotations

import pytest

from spire.nl_parser.router import (
    ModuleChoice,
    ClassificationError,
    classify_modules,
    _classifier_system_prompt,
)


# --- mock LLM mirroring the with_structured_output(...).invoke(...) surface --

class _StructuredStub:
    """Stands in for the object with_structured_output returns. Its invoke
    records the messages it was called with and returns a preset result."""

    def __init__(self, result, recorder):
        self._result = result
        self._recorder = recorder

    def invoke(self, messages):
        self._recorder["messages"] = messages
        return self._result


class _FakeLLM:
    """A stand-in LLM. with_structured_output returns a _StructuredStub whose
    invoke yields ``result`` (a dict-with-parsed, a bare ModuleChoice, or a
    dict). ``schema`` and ``include_raw`` are accepted and ignored."""

    def __init__(self, result):
        self._result = result
        self.calls: dict = {}

    def with_structured_output(self, schema, include_raw=False):
        self.calls["schema"] = schema
        self.calls["include_raw"] = include_raw
        return _StructuredStub(self._result, self.calls)


def _raw_shape(modules):
    """The real include_raw=True return: a dict with parsed + raw. raw carries
    no usage_metadata here; log_usage tolerates that (records zeros)."""
    return {"parsed": ModuleChoice(modules=modules), "raw": None,
            "parsing_error": None}


_MENU = (
    "payables:\n  Invoice (aka: bill)\n"
    "procurement:\n  PurchaseOrder (aka: PO)\n"
    "receivables:\n  ReceivablesInvoice (aka: AR invoice)\n"
    "supplier:\n  Supplier (aka: vendor)\n"
)


# --- happy path ------------------------------------------------------------

def test_single_module_returns_list():
    """A cleanly single-module classification returns exactly that module,
    as a list (D1)."""
    llm = _FakeLLM(_raw_shape(["payables"]))
    out = classify_modules("show unpaid bills", llm=llm, menu_text=_MENU)
    assert out == ["payables"]


def test_each_known_module_passes():
    for m in ("payables", "procurement", "receivables", "supplier"):
        llm = _FakeLLM(_raw_shape([m]))
        assert classify_modules("q", llm=llm, menu_text=_MENU) == [m]


# --- return-shape handling -------------------------------------------------

def test_bare_model_return_shape():
    """A mock that returns a bare ModuleChoice (not the include_raw dict) is
    handled — the parser tests use this convenience too."""
    llm = _FakeLLM(ModuleChoice(modules=["procurement"]))
    out = classify_modules("open POs", llm=llm, menu_text=_MENU)
    assert out == ["procurement"]


def test_bare_dict_return_shape():
    """A mock returning a plain dict with a 'modules' key is handled."""
    llm = _FakeLLM({"modules": ["supplier"]})
    out = classify_modules("vendors in the US", llm=llm, menu_text=_MENU)
    assert out == ["supplier"]


# --- dedup -----------------------------------------------------------------

def test_duplicate_modules_deduped():
    llm = _FakeLLM(_raw_shape(["payables", "payables"]))
    out = classify_modules("bills and more bills", llm=llm, menu_text=_MENU)
    assert out == ["payables"]


# --- 3a: raise on empty / unknown -----------------------------------------

def test_empty_classification_raises():
    llm = _FakeLLM(_raw_shape([]))
    with pytest.raises(ClassificationError):
        classify_modules("???", llm=llm, menu_text=_MENU)


def test_unknown_module_raises():
    llm = _FakeLLM(_raw_shape(["inventory"]))
    with pytest.raises(ClassificationError):
        classify_modules("stock levels", llm=llm, menu_text=_MENU)


def test_none_parsed_raises():
    """The real LLM can return {'parsed': None} on a failed parse — raise."""
    llm = _FakeLLM({"parsed": None, "raw": None, "parsing_error": "boom"})
    with pytest.raises(ClassificationError):
        classify_modules("garbled", llm=llm, menu_text=_MENU)


def test_mixed_known_and_unknown_raises():
    """Any unknown name in the set fails the whole classification (3a)."""
    llm = _FakeLLM(_raw_shape(["payables", "inventory"]))
    with pytest.raises(ClassificationError):
        classify_modules("q", llm=llm, menu_text=_MENU)


# --- the classify seam: menu is injected ----------------------------------

def test_menu_injected_into_system_prompt():
    """The grounding menu reaches the system prompt the LLM is invoked with."""
    llm = _FakeLLM(_raw_shape(["payables"]))
    classify_modules("show bills", llm=llm, menu_text=_MENU)
    system_msg = llm.calls["messages"][0]
    # messages are [("system", <prompt>), ("human", <prompt>)]
    assert system_msg[0] == "system"
    assert _MENU in system_msg[1]
    assert "payables" in system_msg[1]


def test_system_prompt_contains_instruction_and_menu():
    prompt = _classifier_system_prompt(_MENU)
    assert "four modules" in prompt or "payables, procurement" in prompt
    assert _MENU in prompt


def test_structured_output_requested_with_schema():
    """The classifier binds ModuleChoice with include_raw=True."""
    llm = _FakeLLM(_raw_shape(["payables"]))
    classify_modules("show bills", llm=llm, menu_text=_MENU)
    assert llm.calls["schema"] is ModuleChoice
    assert llm.calls["include_raw"] is True
