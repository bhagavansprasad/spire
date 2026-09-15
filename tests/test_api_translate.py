"""Unit tests for spire.api.translate (Doc B §5.1.3).

Pure: fabricate a GraphState and assert what translate() produces.
No FastAPI, no MCP, no server. Runs anywhere.

The routing rules these tests pin are the load-bearing part of the API.
A wrong translation is a wrong answer, and it would be silent — hence
every branch of §5.1.3 is tested here, not just the happy path.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from spire.api.models import (
    ErrorAnswer,
    RefusalAnswer,
    TextAnswer,
)
from spire.api.translate import translate


def _response(**kwargs):
    """Stand-in for a synthesizer response object. Includes .summary and
    .truncation_notes, which translate() reads via getattr."""
    defaults = {
        "summary": "",
        "truncation_notes": [],
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _call(state: dict):
    return translate(state, request_id="req-1", stages=[], latency_ms=42)


# ── Refusal ──────────────────────────────────────────────────────────


def test_structured_refusal_maps_to_kind_refusal():
    refusal = SimpleNamespace(
        reason="This prompt is out of scope.",
        solution="Try asking about suppliers or invoices.",
        example="Show me suppliers in the US.",
    )
    env = _call({"refusal": refusal})
    assert env.kind == "refusal"
    assert isinstance(env.answer, RefusalAnswer)
    assert env.answer.refusal.reason == "This prompt is out of scope."
    assert env.answer.refusal.solution == "Try asking about suppliers or invoices."
    assert env.answer.refusal.example == "Show me suppliers in the US."


def test_refusal_with_missing_fields_falls_back():
    refusal = SimpleNamespace(reason=None, solution=None, example=None)
    env = _call({"refusal": refusal})
    assert env.kind == "refusal"
    assert env.answer.refusal.reason            # some non-empty string
    assert env.answer.refusal.solution is None
    assert env.answer.refusal.example is None


def test_planner_refusal_maps_to_kind_refusal_with_text_reason():
    env = _call({
        "error": "plan: Invoice queries require a supplier.",
        "plan_refusal": True,
    })
    assert env.kind == "refusal"
    assert isinstance(env.answer, RefusalAnswer)
    assert "Invoice queries require a supplier" in env.answer.refusal.reason
    assert env.answer.refusal.solution is None
    assert env.answer.refusal.example is None


# ── Error ────────────────────────────────────────────────────────────


def test_error_alone_maps_to_kind_error_with_stage_from_prefix():
    env = _call({"error": "execute: connection refused"})
    assert env.kind == "error"
    assert isinstance(env.answer, ErrorAnswer)
    assert env.answer.error.stage == "execute"
    assert env.answer.error.retryable is True       # execute is retryable


def test_error_from_parse_is_not_retryable():
    env = _call({"error": "parse: unexpected token"})
    assert env.kind == "error"
    assert env.answer.error.stage == "parse"
    assert env.answer.error.retryable is False


def test_error_without_node_prefix_falls_back_to_pipeline_stage():
    env = _call({"error": "something broke"})
    assert env.kind == "error"
    assert env.answer.error.stage == "pipeline"
    assert env.answer.error.retryable is False


# ── synth_failed ─────────────────────────────────────────────────────


def test_synth_failed_keeps_records_as_table_with_note():
    env = _call({
        "synth_failed": "degenerate output: out_tokens=8000",
        "outputs": {"suppliers": [{"SupplierId": 1, "Supplier": "X"}]},
    })
    assert env.kind == "table"
    assert isinstance(env.answer, TextAnswer)
    assert env.answer.records == [{"SupplierId": 1, "Supplier": "X"}]
    assert "degenerate output" in (env.answer.truncation_note or "")


def test_synth_failed_with_no_records_is_text():
    env = _call({"synth_failed": "runaway"})
    assert env.kind == "text"
    assert env.answer.records == []


# ── Normal response ──────────────────────────────────────────────────


def test_response_with_no_records_renders_as_text():
    env = _call({"response": _response(summary="There are 431 suppliers.")})
    assert env.kind == "text"
    assert env.answer.text == "There are 431 suppliers."
    assert env.answer.records == []


def test_response_with_truncation_notes_sets_truncated_flag():
    env = _call({
        "response": _response(
            summary="Showing 25 of 431 suppliers.",
            truncation_notes=["suppliers: 431 total in source; 25 examined"],
        )
    })
    assert env.kind == "text"
    assert env.answer.truncated is True
    assert "431 total in source" in (env.answer.truncation_note or "")


# ── Defensive ────────────────────────────────────────────────────────


def test_empty_state_is_defensive_error():
    env = _call({})
    assert env.kind == "error"
    assert env.answer.error.stage == "pipeline"


# ── Metadata passthrough ─────────────────────────────────────────────


def test_metadata_is_passed_through():
    env = _call({"response": _response(summary="hi")})
    assert env.metadata.latency_ms == 42
    assert env.metadata.llm_calls == 0
    assert env.metadata.kg_version is None