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
    route_and_parse,
    _classifier_system_prompt,
)
import spire.nl_parser.router as router_mod


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


# --- route_and_parse wiring (step 4) --------------------------------------
# These test the WIRING in isolation: classify_modules, assemble_subset,
# parse, and load_kg_menu are patched, so we assert the call flow — the menu
# is loaded once and shared, the classified modules reach assemble_subset, and
# the scoped prompt reaches parse — without a real LLM, DB, or Intent. Fidelity
# (that route_and_parse produces the SAME Intent as a full parse) is step 5.


class _Recorder:
    """Captures the arguments each patched collaborator was called with."""

    def __init__(self):
        self.menu_loads = 0
        self.classify_prompt = None
        self.assemble_args = None
        self.parse_kwargs = None


def _install_patches(monkeypatch, rec, modules=("payables",),
                     scoped="SCOPED_PROMPT", parse_ret="PARSE_RESULT",
                     classify_exc=None):
    sentinel_menu = object()  # identity check: same menu passed to both

    def fake_load_kg_menu():
        rec.menu_loads += 1
        return sentinel_menu

    def fake_classify(prompt, llm=None, menu_text=None):
        rec.classify_prompt = prompt
        if classify_exc is not None:
            raise classify_exc
        return list(modules)

    def fake_assemble_subset(mods, menu):
        rec.assemble_args = (mods, menu)
        return scoped

    def fake_parse(prompt, llm=None, menu=None, system_prompt=None):
        rec.parse_kwargs = {
            "prompt": prompt, "llm": llm, "menu": menu,
            "system_prompt": system_prompt,
        }
        return parse_ret

    monkeypatch.setattr(router_mod, "load_kg_menu", fake_load_kg_menu)
    monkeypatch.setattr(router_mod, "classify_modules", fake_classify)
    monkeypatch.setattr(router_mod, "assemble_subset", fake_assemble_subset)
    monkeypatch.setattr(router_mod, "parse", fake_parse)
    return sentinel_menu


def test_route_and_parse_happy_flow(monkeypatch):
    rec = _Recorder()
    menu = _install_patches(monkeypatch, rec)
    out = route_and_parse("show unpaid bills")

    assert out == "PARSE_RESULT"
    # menu loaded exactly once
    assert rec.menu_loads == 1
    # classified modules reached assemble_subset, with the shared menu
    assert rec.assemble_args == (["payables"], menu)
    # scoped prompt + shared menu reached parse
    assert rec.parse_kwargs["system_prompt"] == "SCOPED_PROMPT"
    assert rec.parse_kwargs["menu"] is menu
    assert rec.parse_kwargs["prompt"] == "show unpaid bills"


def test_route_and_parse_menu_loaded_once_and_shared(monkeypatch):
    """The SAME menu object must go to both assemble_subset and parse."""
    rec = _Recorder()
    menu = _install_patches(monkeypatch, rec)
    route_and_parse("q")
    assert rec.assemble_args[1] is menu
    assert rec.parse_kwargs["menu"] is menu
    assert rec.menu_loads == 1


def test_route_and_parse_passes_provided_menu(monkeypatch):
    """A caller-provided menu is used and load_kg_menu is NOT called."""
    rec = _Recorder()
    _install_patches(monkeypatch, rec)
    my_menu = object()
    route_and_parse("q", menu=my_menu)
    assert rec.menu_loads == 0
    assert rec.assemble_args[1] is my_menu
    assert rec.parse_kwargs["menu"] is my_menu


def test_route_and_parse_passes_llm_to_both(monkeypatch):
    """An injected llm reaches the parse call (and the classify call)."""
    rec = _Recorder()
    _install_patches(monkeypatch, rec)
    my_llm = object()
    route_and_parse("q", llm=my_llm)
    assert rec.parse_kwargs["llm"] is my_llm


def test_route_and_parse_propagates_classification_error(monkeypatch):
    """3-i: a ClassificationError from classify_modules propagates; parse is
    never reached."""
    rec = _Recorder()
    _install_patches(
        monkeypatch, rec,
        classify_exc=ClassificationError("no modules"),
    )
    with pytest.raises(ClassificationError):
        route_and_parse("garbled")
    # parse must not have been called
    assert rec.parse_kwargs is None
