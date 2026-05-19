"""Unit tests for scripts/inspect_trace.py.

Pure unit tests. No live agent, no DB, no MCP. Each test writes a
synthetic JSONL trace to a tmp directory and exercises the parser
against it.

The script is at scripts/inspect_trace.py. We import it via a
sys.path hack because scripts/ is not part of the spire package.
"""

import json
import sys
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import inspect_trace  # noqa: E402  (must follow sys.path manipulation)


# ----- Trace fixtures --------------------------------------------------


def _make_event(event_name: str, **kw) -> str:
    """Build one JSONL event line."""
    base = {"event": event_name, "level": "info"}
    base.update(kw)
    return json.dumps(base)


def _write_trace(tmp_path: Path, name: str, events: list[str]) -> Path:
    """Write a list of JSONL event strings to a trace file."""
    path = tmp_path / f"{name}.jsonl"
    path.write_text("\n".join(events) + "\n")
    return path


def _full_trace_events() -> list[str]:
    """A complete healthy trace mirroring what runner.py emits."""
    return [
        _make_event(
            "agent_started",
            run_id="2026-05-19T00-00-00-000000",
            prompt="Find suppliers in US.",
            model="gemini-2.0-flash",
            kg_enabled=True,
            timestamp="2026-05-19T00:00:00.000000Z",
        ),
        _make_event("kg_context_loaded", chars=12480),
        _make_event("system_prompt_built", chars=13140),
        _make_event(
            "tools_loaded",
            tools=["search_suppliers", "search_suppliers_by_country", "get_buyer"],
        ),
        _make_event("graph_built"),
        _make_event(
            "message",
            index=1,
            type="AIMessage",
            content_preview=None,
            tool_calls=[{"name": "search_suppliers_by_country", "args": {"country": "US"}}],
        ),
        _make_event(
            "message",
            index=3,
            type="AIMessage",
            content_preview="Calling buyer lookups",
            tool_calls=[
                {"name": "get_buyer", "args": {"buyer_id": 111}},
                {"name": "get_buyer", "args": {"buyer_id": 222}},
            ],
        ),
        _make_event(
            "agent_finished",
            answer_preview="Found 25 US suppliers including Lee Supplies and ACME.",
            timestamp="2026-05-19T00:00:34.200000Z",
        ),
    ]


# ----- Parsing tests --------------------------------------------------


def test_parses_prompt_model_and_kg_state(tmp_path):
    path = _write_trace(tmp_path, "happy", _full_trace_events())
    s = inspect_trace.parse_trace(path)
    assert s.prompt == "Find suppliers in US."
    assert s.model == "gemini-2.0-flash"
    assert s.kg_enabled is True
    assert s.kg_chars == 12480
    assert s.system_prompt_chars == 13140


def test_parses_tools_available(tmp_path):
    path = _write_trace(tmp_path, "happy", _full_trace_events())
    s = inspect_trace.parse_trace(path)
    assert s.tools_available == [
        "search_suppliers", "search_suppliers_by_country", "get_buyer"
    ]


def test_groups_tool_calls_by_turn(tmp_path):
    path = _write_trace(tmp_path, "happy", _full_trace_events())
    s = inspect_trace.parse_trace(path)
    # Two turns: one with a single call, one with two parallel calls.
    assert len(s.turns) == 2
    assert len(s.turns[0]) == 1
    assert s.turns[0][0].name == "search_suppliers_by_country"
    assert len(s.turns[1]) == 2
    assert {tc.name for tc in s.turns[1]} == {"get_buyer"}
    assert s.total_tool_calls == 3


def test_computes_duration(tmp_path):
    path = _write_trace(tmp_path, "happy", _full_trace_events())
    s = inspect_trace.parse_trace(path)
    assert s.duration_seconds == pytest.approx(34.2, abs=0.01)


def test_captures_final_answer(tmp_path):
    path = _write_trace(tmp_path, "happy", _full_trace_events())
    s = inspect_trace.parse_trace(path)
    assert "Lee Supplies" in s.final_answer


# ----- Termination heuristics ----------------------------------------


def test_termination_normal_completion(tmp_path):
    path = _write_trace(tmp_path, "happy", _full_trace_events())
    s = inspect_trace.parse_trace(path)
    assert s.completed_normally is True
    assert s.termination_note == "completed normally"


def test_termination_premature(tmp_path):
    """One tool call + empty answer = premature termination."""
    events = [
        _make_event("agent_started", prompt="x", model="m", kg_enabled=False),
        _make_event(
            "message",
            tool_calls=[{"name": "search_suppliers", "args": {}}],
        ),
        _make_event("agent_finished", answer_preview=""),
    ]
    path = _write_trace(tmp_path, "premature", events)
    s = inspect_trace.parse_trace(path)
    assert s.completed_normally is True
    assert "premature termination" in s.termination_note


def test_termination_crashed(tmp_path):
    """No agent_finished event = crashed."""
    events = [
        _make_event("agent_started", prompt="x", model="m", kg_enabled=True),
        _make_event(
            "message",
            tool_calls=[{"name": "search_suppliers", "args": {}}],
        ),
        # No agent_finished.
    ]
    path = _write_trace(tmp_path, "crashed", events)
    s = inspect_trace.parse_trace(path)
    assert s.completed_normally is False
    assert "crashed" in s.termination_note


def test_termination_completed_no_answer(tmp_path):
    """Multiple tool calls, agent_finished, but empty answer."""
    events = [
        _make_event("agent_started", prompt="x", model="m", kg_enabled=True),
        _make_event(
            "message",
            tool_calls=[{"name": "a", "args": {}}, {"name": "b", "args": {}}],
        ),
        _make_event(
            "message",
            tool_calls=[{"name": "c", "args": {}}],
        ),
        _make_event("agent_finished", answer_preview=""),
    ]
    path = _write_trace(tmp_path, "noanswer", events)
    s = inspect_trace.parse_trace(path)
    assert s.completed_normally is True
    assert s.termination_note == "completed but produced no answer"


# ----- Output formatters --------------------------------------------


def test_text_output_contains_all_sections(tmp_path):
    path = _write_trace(tmp_path, "happy", _full_trace_events())
    s = inspect_trace.parse_trace(path)
    out = inspect_trace.format_text(s, full_answer=False)
    assert "Prompt:" in out
    assert "KG enabled:" in out
    assert "Tool call sequence" in out
    assert "Final answer" in out
    assert "Termination" in out


def test_text_output_truncates_long_answers(tmp_path):
    """Final answers > 500 chars are truncated by default."""
    long_answer = "X" * 600
    events = [
        _make_event("agent_started", prompt="x", model="m", kg_enabled=False),
        _make_event("agent_finished", answer_preview=long_answer),
    ]
    path = _write_trace(tmp_path, "long", events)
    s = inspect_trace.parse_trace(path)
    out = inspect_trace.format_text(s, full_answer=False)
    assert "truncated" in out


def test_text_output_respects_full_flag(tmp_path):
    long_answer = "Y" * 600
    events = [
        _make_event("agent_started", prompt="x", model="m", kg_enabled=False),
        _make_event("agent_finished", answer_preview=long_answer),
    ]
    path = _write_trace(tmp_path, "long", events)
    s = inspect_trace.parse_trace(path)
    out = inspect_trace.format_text(s, full_answer=True)
    assert "truncated" not in out
    assert "Y" * 600 in out


def test_json_output_is_valid_json(tmp_path):
    path = _write_trace(tmp_path, "happy", _full_trace_events())
    s = inspect_trace.parse_trace(path)
    out = inspect_trace.format_json(s, full_answer=False)
    data = json.loads(out)
    assert data["prompt"] == "Find suppliers in US."
    assert data["kg_enabled"] is True
    assert data["total_tool_calls"] == 3
    assert len(data["turns"]) == 2
    assert data["completed_normally"] is True


def test_args_formatter_sorts_keys(tmp_path):
    """Tool-call args should render with sorted keys for deterministic output."""
    out_a = inspect_trace._format_args({"b": 2, "a": 1})
    out_b = inspect_trace._format_args({"a": 1, "b": 2})
    assert out_a == out_b == "a=1, b=2"


# ----- CLI integration -----------------------------------------------


def test_main_errors_on_missing_file(tmp_path, capsys):
    rc = inspect_trace.main([str(tmp_path / "nonexistent.jsonl")])
    assert rc == 1
    captured = capsys.readouterr()
    assert "not found" in captured.err.lower()


def test_main_text_output_succeeds(tmp_path, capsys):
    path = _write_trace(tmp_path, "happy", _full_trace_events())
    rc = inspect_trace.main([str(path)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Find suppliers in US." in captured.out
    assert "Termination" in captured.out


def test_main_json_output_succeeds(tmp_path, capsys):
    path = _write_trace(tmp_path, "happy", _full_trace_events())
    rc = inspect_trace.main([str(path), "--json"])
    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["kg_enabled"] is True
