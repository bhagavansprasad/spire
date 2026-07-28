
"""
Tests for the LangGraph pipeline graph (spire.graph.pipeline).

Tests WIRING, not the wrapped functions (those have their own tests):
the graph runs parse -> plan -> execute -> synthesize in order, refusals
short-circuit to END before planning, and a node error ends the run
before later nodes. The four wrapped functions are monkeypatched so no
LLM/MCP/DB is needed.
"""

from __future__ import annotations

import pytest

import spire.graph.pipeline as pipeline


class _FakeIntent:
    target_entity = "Supplier"


class _FakeRefusal:
    flavor = type("F", (), {"value": "UNKNOWN_ENTITY"})()
    detail = "out of scope"


class _ParseOK:
    is_refusal = False
    intent = _FakeIntent()


class _ParseRefused:
    is_refusal = True
    refusal = _FakeRefusal()


@pytest.fixture
def patch_nodes(monkeypatch):
    """Patch the four wrapped functions in the pipeline namespace."""
    async def fake_execute(plan, session, progress_handler=None):
        # execute_plan returns three values:
        # (outputs, truncation_by_step, metadata_by_step)
        return ({"out": [{"id": 1}]}, {}, {})
    
    monkeypatch.setattr(pipeline, "generate_plan", lambda intent: ["step1"])
    monkeypatch.setattr(pipeline, "execute_plan", fake_execute)
    monkeypatch.setattr(
        pipeline, "synthesize_response",
        lambda outputs, target_entity, truncation_by_step=None,
        count_only=False, metadata_by_step=None: "ANSWER",
    )
    return monkeypatch


@pytest.mark.asyncio
async def test_happy_path_runs_all_nodes(patch_nodes):
    patch_nodes.setattr(pipeline, "parse_prompt", lambda p, menu=None: _ParseOK())
    graph = pipeline.build_graph()
    state = await graph.ainvoke(
        {"prompt": "suppliers in US", "menu": {}, "session": None}
    )
    assert state["plan"] == ["step1"]
    assert state["outputs"] == {"out": [{"id": 1}]}
    assert state["response"] == "ANSWER"
    assert "error" not in state or state["error"] is None


@pytest.mark.asyncio
async def test_refusal_short_circuits(patch_nodes):
    patch_nodes.setattr(
        pipeline, "parse_prompt", lambda p, menu=None: _ParseRefused()
    )
    graph = pipeline.build_graph()
    state = await graph.ainvoke(
        {"prompt": "contract renewals", "menu": {}, "session": None}
    )
    assert state.get("refusal") is not None
    # never planned/executed/synthesized
    assert state.get("plan") is None
    assert state.get("outputs") is None
    assert state.get("response") is None


@pytest.mark.asyncio
async def test_plan_error_short_circuits(patch_nodes):
    patch_nodes.setattr(pipeline, "parse_prompt", lambda p, menu=None: _ParseOK())

    def boom(intent):
        raise NotImplementedError("unsupported aggregation op")

    patch_nodes.setattr(pipeline, "generate_plan", boom)
    graph = pipeline.build_graph()
    state = await graph.ainvoke(
        {"prompt": "x", "menu": {}, "session": None}
    )
    assert state.get("error", "").startswith("plan:")
    assert state.get("outputs") is None
    assert state.get("response") is None



