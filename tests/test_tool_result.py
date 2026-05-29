"""Tests for the ToolResult shared type."""

from spire.mcp_server.tools.tool_result import ToolResult

def test_build_marks_truncated_when_total_exceeds_items():
    result = ToolResult.build(
        items=[{"id": 1}, {"id": 2}],
        limit_applied=2,
        total_available=100,
    )
    assert result.truncated is True
    assert result.total_available == 100
    assert result.limit_applied == 2
    assert len(result.items) == 2


def test_build_marks_not_truncated_when_total_equals_items():
    result = ToolResult.build(
        items=[{"id": 1}, {"id": 2}],
        limit_applied=25,
        total_available=2,
    )
    assert result.truncated is False


def test_build_marks_not_truncated_when_total_unknown():
    result = ToolResult.build(
        items=[{"id": 1}],
        limit_applied=25,
        total_available=None,
    )
    assert result.truncated is False
    assert result.total_available is None


def test_build_handles_empty_items():
    result = ToolResult.build(
        items=[],
        limit_applied=25,
        total_available=0,
    )
    assert result.items == []
    assert result.truncated is False


def test_to_dict_serializes_all_fields():
    result = ToolResult.build(
        items=[{"a": 1}],
        limit_applied=25,
        total_available=8531,
    )
    d = result.to_dict()
    assert d == {
        "items": [{"a": 1}],
        "total_available": 8531,
        "limit_applied": 25,
        "truncated": True,
    }


def test_default_construction():
    """ToolResult can be constructed with all defaults."""
    result = ToolResult()
    assert result.items == []
    assert result.total_available is None
    assert result.limit_applied == 0
    assert result.truncated is False
