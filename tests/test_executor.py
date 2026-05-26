"""
Tests for the executor (A.1 scope).

Two layers:

1. Unit tests with mocked MCP sessions. Cover happy path, error paths,
   result-parsing edge cases, client-filter behavior. No infrastructure
   required.

2. One integration test against the live MCP server. Marked
   @pytest.mark.integration so it's skipped by default. Run with:
       pytest -m integration tests/test_executor.py

   Requires the MCP server running on http://127.0.0.1:3333/mcp/ and
   personas.yaml present.

A.2 will add tests for iteration, $iteration_value substitution, and
output_dedupe_by handling. A.1 explicitly verifies that iterating
steps raise NotImplementedError.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from spire.config import PERSONAS_FILE
from spire.executor.executor import (
    _apply_client_filters,
    _parse_tool_result,
    execute_plan,
)
from spire.planner.planner import Step


# ─────────────────────────────────────────────────────────────────────
# Helpers to fake MCP responses
# ─────────────────────────────────────────────────────────────────────


def _text_block(text: str) -> SimpleNamespace:
    """Build a minimal stand-in for an MCP TextContent block."""
    return SimpleNamespace(type="text", text=text)


def _call_tool_result(blocks: list | None) -> SimpleNamespace:
    """Build a minimal stand-in for an MCP CallToolResult."""
    return SimpleNamespace(content=blocks)


def _mock_session(payload: object) -> AsyncMock:
    """
    Build a mock MCP session whose call_tool returns the given payload
    as a single TextContent block. payload is JSON-serialized.
    """
    session = AsyncMock()
    session.call_tool.return_value = _call_tool_result(
        [_text_block(json.dumps(payload))]
    )
    return session


# ─────────────────────────────────────────────────────────────────────
# _parse_tool_result — unit tests
# ─────────────────────────────────────────────────────────────────────


def test_parse_tool_result_list_payload() -> None:
    """A list-of-dicts payload comes back as-is."""
    payload = [{"SupplierId": 1}, {"SupplierId": 2}]
    result = _parse_tool_result(_call_tool_result([_text_block(json.dumps(payload))]))
    assert result == payload


def test_parse_tool_result_dict_payload_wrapped_in_list() -> None:
    """A dict payload (e.g., get_buyer's single record) is wrapped in
    a single-element list so downstream code stays uniform."""
    payload = {"PersonId": 12345, "DisplayName": "Calvin Roth"}
    result = _parse_tool_result(_call_tool_result([_text_block(json.dumps(payload))]))
    assert result == [payload]


def test_parse_tool_result_null_payload_returns_empty_list() -> None:
    """JSON null (e.g., get_buyer returning None on miss) becomes []."""
    result = _parse_tool_result(_call_tool_result([_text_block("null")]))
    assert result == []


def test_parse_tool_result_empty_content_returns_empty_list() -> None:
    """No content blocks at all → empty list."""
    assert _parse_tool_result(_call_tool_result([])) == []
    assert _parse_tool_result(_call_tool_result(None)) == []


def test_parse_tool_result_multiple_blocks_raises() -> None:
    """We don't currently expect tools to return multiple content
    blocks. If it happens, fail loudly so we can investigate."""
    result = _call_tool_result(
        [_text_block("[]"), _text_block("[]")]
    )
    with pytest.raises(RuntimeError, match="exactly one content block"):
        _parse_tool_result(result)


def test_parse_tool_result_non_text_block_raises() -> None:
    """Non-text content blocks (e.g., image) shouldn't appear from
    Spire tools. If they do, fail loudly."""
    fake_image_block = SimpleNamespace(type="image")
    result = _call_tool_result([fake_image_block])
    with pytest.raises(RuntimeError, match="Expected TextContent"):
        _parse_tool_result(result)


def test_parse_tool_result_invalid_json_raises() -> None:
    """If the text block doesn't parse as JSON, raise RuntimeError."""
    result = _call_tool_result([_text_block("not json {{{")])
    with pytest.raises(RuntimeError, match="not valid JSON"):
        _parse_tool_result(result)


def test_parse_tool_result_scalar_payload_raises() -> None:
    """A JSON scalar (string, number, bool) is unexpected for our tools."""
    result = _call_tool_result([_text_block('"a string"')])
    with pytest.raises(RuntimeError, match="neither dict, list, nor null"):
        _parse_tool_result(result)


# ─────────────────────────────────────────────────────────────────────
# _apply_client_filters — unit tests
# ─────────────────────────────────────────────────────────────────────


def test_apply_client_filters_no_filters_returns_input_unchanged() -> None:
    items = [{"x": 1}, {"x": 2}]
    assert _apply_client_filters(items, []) == items


def test_apply_client_filters_equals_filters_to_matching() -> None:
    items = [
        {"StatusCode": "OPEN", "id": 1},
        {"StatusCode": "CLOSED", "id": 2},
        {"StatusCode": "OPEN", "id": 3},
    ]
    filters = [{"field": "StatusCode", "op": "equals", "value": "OPEN"}]
    result = _apply_client_filters(items, filters)
    assert result == [
        {"StatusCode": "OPEN", "id": 1},
        {"StatusCode": "OPEN", "id": 3},
    ]


def test_apply_client_filters_equals_is_case_sensitive() -> None:
    """Lower-case 'open' must NOT match 'OPEN'. Status codes in
    Fusion are case-sensitive."""
    items = [{"StatusCode": "OPEN"}]
    filters = [{"field": "StatusCode", "op": "equals", "value": "open"}]
    assert _apply_client_filters(items, filters) == []


def test_apply_client_filters_missing_field_excluded() -> None:
    """An item without the filtered field doesn't match (None != value)."""
    items = [{"id": 1}, {"id": 2, "StatusCode": "OPEN"}]
    filters = [{"field": "StatusCode", "op": "equals", "value": "OPEN"}]
    result = _apply_client_filters(items, filters)
    assert result == [{"id": 2, "StatusCode": "OPEN"}]


def test_apply_client_filters_multiple_filters_anded() -> None:
    """Two filters combine with AND semantics — both must match."""
    items = [
        {"StatusCode": "OPEN", "Country": "US"},
        {"StatusCode": "OPEN", "Country": "UK"},
        {"StatusCode": "CLOSED", "Country": "US"},
    ]
    filters = [
        {"field": "StatusCode", "op": "equals", "value": "OPEN"},
        {"field": "Country", "op": "equals", "value": "US"},
    ]
    result = _apply_client_filters(items, filters)
    assert result == [{"StatusCode": "OPEN", "Country": "US"}]


def test_apply_client_filters_unknown_op_raises() -> None:
    """v1 only supports 'equals'. Unknown ops must raise — silent
    ignores would mask planner bugs."""
    items = [{"x": 1}]
    filters = [{"field": "x", "op": "greater_than", "value": 0}]
    with pytest.raises(ValueError, match="Unsupported client-filter op"):
        _apply_client_filters(items, filters)


# ─────────────────────────────────────────────────────────────────────
# execute_plan — unit tests with mocked sessions
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_plan_single_step_no_filters_no_iteration() -> None:
    """Happy path: one non-iterating step, no client filters, mock session."""
    plan = [
        Step(
            step_id=1,
            tool_name="search_suppliers_by_country",
            tool_args={"country": "US"},
            iterate_over=None,
            client_filters=[],
            output_name="us_suppliers",
            output_dedupe_by=None,
        ),
    ]
    payload = [
        {"SupplierId": 100, "Supplier": "ACME"},
        {"SupplierId": 101, "Supplier": "Lee Supplies"},
    ]
    session = _mock_session(payload)

    outputs = await execute_plan(plan, session)

    assert outputs == {"us_suppliers": payload}
    session.call_tool.assert_awaited_once_with(
        "search_suppliers_by_country", {"country": "US"}
    )


@pytest.mark.asyncio
async def test_execute_plan_iterating_step_raises_not_implemented() -> None:
    """A.1 explicitly does not handle iteration. Make sure the
    NotImplementedError fires loudly."""
    plan = [
        Step(
            step_id=1,
            tool_name="search_purchase_orders",
            tool_args={"supplier_id": "$iteration_value"},
            iterate_over={"from_step": "us_suppliers", "field": "SupplierId"},
            client_filters=[],
            output_name="open_pos",
            output_dedupe_by=None,
        ),
    ]
    session = AsyncMock()
    with pytest.raises(NotImplementedError, match="A.2"):
        await execute_plan(plan, session)


@pytest.mark.asyncio
async def test_execute_plan_iteration_sentinel_in_non_iterating_step_raises() -> None:
    """Sanity check: a step marked non-iterating (iterate_over is None)
    that still carries $iteration_value in its args is a planner bug.
    The executor must catch this loudly, not silently send the
    sentinel to MCP."""
    plan = [
        Step(
            step_id=1,
            tool_name="search_suppliers_by_country",
            tool_args={"country": "$iteration_value"},  # planner bug shape
            iterate_over=None,
            client_filters=[],
            output_name="us_suppliers",
            output_dedupe_by=None,
        ),
    ]
    session = AsyncMock()
    with pytest.raises(RuntimeError, match="iteration sentinel"):
        await execute_plan(plan, session)


@pytest.mark.asyncio
async def test_execute_plan_propagates_tool_call_exception() -> None:
    """Fail-the-whole-plan policy: if call_tool raises, the exception
    propagates verbatim. No swallow, no partial result."""
    plan = [
        Step(
            step_id=1,
            tool_name="search_suppliers_by_country",
            tool_args={"country": "US"},
            iterate_over=None,
            client_filters=[],
            output_name="us_suppliers",
            output_dedupe_by=None,
        ),
    ]
    session = AsyncMock()
    session.call_tool.side_effect = RuntimeError("pod down")
    with pytest.raises(RuntimeError, match="pod down"):
        await execute_plan(plan, session)


@pytest.mark.asyncio
async def test_execute_plan_applies_client_filters_to_result() -> None:
    """The executor applies client_filters to the parsed tool result.
    Confirms the integration between _parse_tool_result and
    _apply_client_filters."""
    plan = [
        Step(
            step_id=1,
            tool_name="search_purchase_orders",
            tool_args={},
            iterate_over=None,
            client_filters=[
                {"field": "StatusCode", "op": "equals", "value": "OPEN"}
            ],
            output_name="open_pos",
            output_dedupe_by=None,
        ),
    ]
    payload = [
        {"POHeaderId": 1, "StatusCode": "OPEN"},
        {"POHeaderId": 2, "StatusCode": "CLOSED"},
        {"POHeaderId": 3, "StatusCode": "OPEN"},
    ]
    session = _mock_session(payload)

    outputs = await execute_plan(plan, session)

    assert outputs == {
        "open_pos": [
            {"POHeaderId": 1, "StatusCode": "OPEN"},
            {"POHeaderId": 3, "StatusCode": "OPEN"},
        ]
    }


@pytest.mark.asyncio
async def test_execute_plan_returns_empty_dict_for_empty_plan() -> None:
    """A zero-step plan returns an empty dict, not an error."""
    session = AsyncMock()
    outputs = await execute_plan([], session)
    assert outputs == {}
    session.call_tool.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────────
# Integration test — hits the live MCP server
#
# Requires:
# - MCP server running on http://127.0.0.1:3333/mcp/
# - personas.yaml present
# - Fusion pod reachable from the MCP server
#
# Marked @pytest.mark.integration; skipped by default. Run with:
#     pytest -m integration tests/test_executor.py
# ─────────────────────────────────────────────────────────────────────


pytestmark_integration = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not PERSONAS_FILE.exists(),
        reason="personas.yaml missing",
    ),
]


@pytest.mark.integration
@pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml missing",
)
@pytest.mark.asyncio
async def test_execute_plan_step1_against_live_mcp_server() -> None:
    """
    End-to-end: run the anchor plan's Step 1 against the live MCP server.

    This is the test that confirms our MCP-result-parsing assumptions
    (TextContent + JSON body) match what FastMCP actually sends.

    If this fails because of result-format mismatch, _parse_tool_result
    needs to adapt. That's the whole reason this test exists.
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    MCP_SERVER_URL = "http://127.0.0.1:3333/mcp/"

    plan = [
        Step(
            step_id=1,
            tool_name="search_suppliers_by_country",
            tool_args={"country": "US"},
            iterate_over=None,
            client_filters=[],
            output_name="us_suppliers",
            output_dedupe_by=None,
        ),
    ]

    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            outputs = await execute_plan(plan, session)

    # Should have exactly one output bucket.
    assert set(outputs.keys()) == {"us_suppliers"}
    suppliers = outputs["us_suppliers"]
    assert isinstance(suppliers, list)
    # We expect at least one US supplier on the demo pod.
    assert len(suppliers) > 0
    # Each item should at minimum carry SupplierId and Supplier (per
    # the search_suppliers_by_country projection).
    first = suppliers[0]
    assert "SupplierId" in first
    assert "Supplier" in first
    # And the MatchedCountry marker added by the tool.
    assert first.get("MatchedCountry") == "US"
