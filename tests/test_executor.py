"""
Tests for the executor (A.1 + A.2 + F2b scope).

Two layers:

1. Unit tests with mocked MCP sessions. Cover happy path, error paths,
   result-parsing edge cases, client-filter behavior, iteration logic,
   and the F2b filter_source_when_empty semantic. No infrastructure
   required.

2. Integration tests against the live MCP server. Marked
   @pytest.mark.integration so they're skipped by default. Run with:
       pytest -m integration tests/test_executor.py

   Requires the MCP server running on http://127.0.0.1:3333/mcp/ and
   personas.yaml present.
"""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from spire.config import PERSONAS_FILE
from spire.executor.executor import (
    _apply_client_filters,
    _collect_iteration_values,
    _execute_filter_source_step,
    _find_substitution_key,
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


def _mock_session_sequence(payloads: list[object]) -> AsyncMock:
    """
    Build a mock MCP session that returns a different payload on each
    successive call_tool invocation. Used to simulate iteration where
    each iterated call returns different data.
    """
    session = AsyncMock()
    session.call_tool.side_effect = [
        _call_tool_result([_text_block(json.dumps(p))]) for p in payloads
    ]
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

def test_parse_tool_result_unwraps_tool_result_envelope() -> None:
    """A ToolResult-shaped dict is unwrapped to its items list.

    This is the new return shape introduced for search_invoices.
    Truncation metadata is dropped at this layer (handled separately
    in a later step).
    """
    payload = {
        "items": [{"InvoiceId": 1}, {"InvoiceId": 2}],
        "total_available": 8531,
        "limit_applied": 25,
        "truncated": True,
    }
    result = _parse_tool_result(
        _call_tool_result([_text_block(json.dumps(payload))])
    )
    assert result == [{"InvoiceId": 1}, {"InvoiceId": 2}]


def test_parse_tool_result_unwraps_empty_tool_result_envelope() -> None:
    """A ToolResult with empty items returns an empty list.

    Critical for filter_source_when_empty steps: the iteration must
    see [] for empty results, not [envelope_dict].
    """
    payload = {
        "items": [],
        "total_available": 0,
        "limit_applied": 25,
        "truncated": False,
    }
    result = _parse_tool_result(
        _call_tool_result([_text_block(json.dumps(payload))])
    )
    assert result == []


def test_parse_tool_result_dict_without_truncated_key_not_unwrapped() -> None:
    """A dict that lacks the 'truncated' marker is treated as a normal
    single-record return (e.g., get_buyer), not a ToolResult envelope.
    """
    payload = {"items": ["not a tool result"], "BuyerId": 123}
    result = _parse_tool_result(
        _call_tool_result([_text_block(json.dumps(payload))])
    )
    # Falls through to the generic "wrap dict in list" branch.
    assert result == [payload]

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
# _find_substitution_key — unit tests
# ─────────────────────────────────────────────────────────────────────


def test_find_substitution_key_single_sentinel() -> None:
    args = {"supplier_id": "$iteration_value"}
    assert _find_substitution_key(args) == "supplier_id"


def test_find_substitution_key_sentinel_among_other_args() -> None:
    """The sentinel can coexist with literal-valued args; only the
    sentinel key is the substitution target."""
    args = {"supplier_id": "$iteration_value", "status": "OPEN"}
    assert _find_substitution_key(args) == "supplier_id"


def test_find_substitution_key_no_sentinel_raises() -> None:
    """An iterating step with no sentinel anywhere is a planner bug."""
    args = {"supplier_id": 12345}
    with pytest.raises(RuntimeError, match="no .* sentinel"):
        _find_substitution_key(args)


def test_find_substitution_key_multiple_sentinels_raises() -> None:
    """v1 supports exactly one substitution key per iterating step."""
    args = {"a": "$iteration_value", "b": "$iteration_value"}
    with pytest.raises(RuntimeError, match="multiple"):
        _find_substitution_key(args)


# ─────────────────────────────────────────────────────────────────────
# _collect_iteration_values — unit tests
# ─────────────────────────────────────────────────────────────────────


def test_collect_iteration_values_simple() -> None:
    outputs = {
        "us_suppliers": [
            {"SupplierId": 100, "Supplier": "ACME"},
            {"SupplierId": 101, "Supplier": "Lee"},
        ]
    }
    values = _collect_iteration_values(
        outputs,
        {"from_step": "us_suppliers", "field": "SupplierId"},
        dedupe=False,
    )
    assert values == [100, 101]


def test_collect_iteration_values_dedupe_preserves_order() -> None:
    """When dedupe=True, duplicates are removed but first-occurrence
    order is preserved."""
    outputs = {
        "open_pos": [
            {"BuyerId": 555},
            {"BuyerId": 777},
            {"BuyerId": 555},  # duplicate
            {"BuyerId": 999},
        ]
    }
    values = _collect_iteration_values(
        outputs,
        {"from_step": "open_pos", "field": "BuyerId"},
        dedupe=True,
    )
    assert values == [555, 777, 999]


def test_collect_iteration_values_dedupe_false_keeps_duplicates() -> None:
    """Without dedupe, duplicates are kept (each PO generates a buyer
    lookup even if it's the same buyer — pre-A.2 behavior)."""
    outputs = {"open_pos": [{"BuyerId": 555}, {"BuyerId": 555}]}
    values = _collect_iteration_values(
        outputs,
        {"from_step": "open_pos", "field": "BuyerId"},
        dedupe=False,
    )
    assert values == [555, 555]


def test_collect_iteration_values_drops_none() -> None:
    """Items where the field is missing or None are silently dropped.
    This is real data — Fusion responses can be sparse."""
    outputs = {
        "open_pos": [
            {"BuyerId": 100},
            {"BuyerId": None},
            {},  # field missing entirely
            {"BuyerId": 200},
        ]
    }
    values = _collect_iteration_values(
        outputs,
        {"from_step": "open_pos", "field": "BuyerId"},
        dedupe=False,
    )
    assert values == [100, 200]


def test_collect_iteration_values_unknown_from_step_raises() -> None:
    outputs = {"us_suppliers": [{"SupplierId": 1}]}
    with pytest.raises(RuntimeError, match="unknown output"):
        _collect_iteration_values(
            outputs,
            {"from_step": "wrong_name", "field": "SupplierId"},
            dedupe=False,
        )


def test_collect_iteration_values_empty_source_returns_empty() -> None:
    outputs = {"us_suppliers": []}
    values = _collect_iteration_values(
        outputs,
        {"from_step": "us_suppliers", "field": "SupplierId"},
        dedupe=False,
    )
    assert values == []


# ─────────────────────────────────────────────────────────────────────
# execute_plan — single-step unit tests (mocked)
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_plan_single_step_no_filters_no_iteration() -> None:
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

    outputs, _ = await execute_plan(plan, session)

    assert outputs == {"us_suppliers": payload}
    session.call_tool.assert_awaited_once_with(
        "search_suppliers_by_country", {"country": "US"}, progress_handler=None
    )

@pytest.mark.asyncio
async def test_execute_plan_iteration_sentinel_in_non_iterating_step_raises() -> None:
    """A step with iterate_over=None must not carry the sentinel."""
    plan = [
        Step(
            step_id=1,
            tool_name="search_suppliers_by_country",
            tool_args={"country": "$iteration_value"},
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

    outputs, _ = await execute_plan(plan, session)

    assert outputs == {
        "open_pos": [
            {"POHeaderId": 1, "StatusCode": "OPEN"},
            {"POHeaderId": 3, "StatusCode": "OPEN"},
        ]
    }


@pytest.mark.asyncio
async def test_execute_plan_returns_empty_dict_for_empty_plan() -> None:
    session = AsyncMock()
    outputs, _ = await execute_plan([], session)
    assert outputs == {}
    session.call_tool.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────────
# execute_plan — iteration unit tests (mocked)
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_plan_two_step_with_iteration_aggregates_results() -> None:
    """Step 1 returns 2 suppliers; Step 2 iterates SupplierId and
    returns POs per supplier. The executor must call Step 2's tool
    twice (once per supplier) and concatenate the results."""
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
        Step(
            step_id=2,
            tool_name="search_purchase_orders",
            tool_args={"supplier_id": "$iteration_value"},
            iterate_over={"from_step": "us_suppliers", "field": "SupplierId"},
            client_filters=[],
            output_name="open_pos",
            output_dedupe_by=None,
        ),
    ]
    session = _mock_session_sequence([
        # Step 1 result.
        [{"SupplierId": 100}, {"SupplierId": 200}],
        # Step 2, iteration 1 (supplier 100).
        [{"POHeaderId": "p1", "SupplierId": 100}],
        # Step 2, iteration 2 (supplier 200).
        [
            {"POHeaderId": "p2", "SupplierId": 200},
            {"POHeaderId": "p3", "SupplierId": 200},
        ],
    ])

    outputs, _ = await execute_plan(plan, session)

    assert outputs["us_suppliers"] == [
        {"SupplierId": 100}, {"SupplierId": 200}
    ]
    # Iteration results are flattened/concatenated.
    assert outputs["open_pos"] == [
        {"POHeaderId": "p1", "SupplierId": 100},
        {"POHeaderId": "p2", "SupplierId": 200},
        {"POHeaderId": "p3", "SupplierId": 200},
    ]
    # Verify the iteration substitution worked.
    calls = session.call_tool.await_args_list
    assert calls[1].args == ("search_purchase_orders", {"supplier_id": 100})
    assert calls[2].args == ("search_purchase_orders", {"supplier_id": 200})


@pytest.mark.asyncio
async def test_execute_plan_iteration_applies_client_filters_per_call() -> None:
    """client_filters are applied to each iteration's result. The
    anchor plan's Step 2 has client_filter StatusCode=='OPEN' — only
    OPEN POs should make it into the aggregated output."""
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
        Step(
            step_id=2,
            tool_name="search_purchase_orders",
            tool_args={"supplier_id": "$iteration_value"},
            iterate_over={"from_step": "us_suppliers", "field": "SupplierId"},
            client_filters=[
                {"field": "StatusCode", "op": "equals", "value": "OPEN"}
            ],
            output_name="open_pos",
            output_dedupe_by=None,
        ),
    ]
    session = _mock_session_sequence([
        [{"SupplierId": 100}, {"SupplierId": 200}],
        # Supplier 100: mix of OPEN and CLOSED — only OPEN survives.
        [
            {"POHeaderId": "p1", "StatusCode": "OPEN"},
            {"POHeaderId": "p2", "StatusCode": "CLOSED"},
        ],
        # Supplier 200: all CLOSED — nothing survives.
        [{"POHeaderId": "p3", "StatusCode": "CLOSED"}],
    ])

    outputs, _ = await execute_plan(plan, session)

    assert outputs["open_pos"] == [
        {"POHeaderId": "p1", "StatusCode": "OPEN"}
    ]


@pytest.mark.asyncio
async def test_execute_plan_iteration_dedupes_when_dedupe_set() -> None:
    """Step 3 in the anchor plan dedupes BuyerId so get_buyer isn't
    called twice for the same buyer."""
    plan = [
        Step(
            step_id=1,
            tool_name="search_purchase_orders",
            tool_args={},
            iterate_over=None,
            client_filters=[],
            output_name="open_pos",
            output_dedupe_by=None,
        ),
        Step(
            step_id=2,
            tool_name="get_buyer",
            tool_args={"buyer_id": "$iteration_value"},
            iterate_over={"from_step": "open_pos", "field": "BuyerId"},
            client_filters=[],
            output_name="buyers",
            output_dedupe_by="BuyerId",
        ),
    ]
    session = _mock_session_sequence([
        # Step 1: 3 POs, but two share BuyerId=555.
        [
            {"POHeaderId": "p1", "BuyerId": 555},
            {"POHeaderId": "p2", "BuyerId": 777},
            {"POHeaderId": "p3", "BuyerId": 555},
        ],
        # Step 2: only TWO calls expected (one per unique buyer).
        {"PersonId": 555, "DisplayName": "Alice"},
        {"PersonId": 777, "DisplayName": "Bob"},
    ])

    outputs, _ = await execute_plan(plan, session)

    # Two buyer records, in first-occurrence order.
    assert outputs["buyers"] == [
        {"PersonId": 555, "DisplayName": "Alice"},
        {"PersonId": 777, "DisplayName": "Bob"},
    ]
    # And the tool was called exactly twice, not three times.
    buyer_calls = [
        c for c in session.call_tool.await_args_list
        if c.args[0] == "get_buyer"
    ]
    assert len(buyer_calls) == 2


@pytest.mark.asyncio
async def test_execute_plan_iteration_no_dedupe_calls_per_item() -> None:
    """Without output_dedupe_by, every iterated value gets a call —
    even if duplicates appear (proves the dedup is opt-in)."""
    plan = [
        Step(
            step_id=1,
            tool_name="search_purchase_orders",
            tool_args={},
            iterate_over=None,
            client_filters=[],
            output_name="open_pos",
            output_dedupe_by=None,
        ),
        Step(
            step_id=2,
            tool_name="get_buyer",
            tool_args={"buyer_id": "$iteration_value"},
            iterate_over={"from_step": "open_pos", "field": "BuyerId"},
            client_filters=[],
            output_name="buyers",
            output_dedupe_by=None,  # explicit opt-out
        ),
    ]
    session = _mock_session_sequence([
        [{"BuyerId": 555}, {"BuyerId": 555}],
        {"PersonId": 555, "DisplayName": "Alice"},
        {"PersonId": 555, "DisplayName": "Alice"},
    ])

    outputs, _ = await execute_plan(plan, session)

    # Two iterations, two results — duplicates included.
    assert len(outputs["buyers"]) == 2
    buyer_calls = [
        c for c in session.call_tool.await_args_list
        if c.args[0] == "get_buyer"
    ]
    assert len(buyer_calls) == 2


@pytest.mark.asyncio
async def test_execute_plan_iteration_empty_source_skips_tool_call() -> None:
    """If the source step produced 0 items, the iterating step makes
    0 tool calls and produces an empty output. Don't crash."""
    plan = [
        Step(
            step_id=1,
            tool_name="search_suppliers_by_country",
            tool_args={"country": "ZZ"},
            iterate_over=None,
            client_filters=[],
            output_name="zz_suppliers",
            output_dedupe_by=None,
        ),
        Step(
            step_id=2,
            tool_name="search_purchase_orders",
            tool_args={"supplier_id": "$iteration_value"},
            iterate_over={"from_step": "zz_suppliers", "field": "SupplierId"},
            client_filters=[],
            output_name="open_pos",
            output_dedupe_by=None,
        ),
    ]
    session = _mock_session([])  # Step 1 returns empty
    outputs, _ = await execute_plan(plan, session)
    assert outputs == {"zz_suppliers": [], "open_pos": []}
    # Step 2's tool must not be called.
    po_calls = [
        c for c in session.call_tool.await_args_list
        if c.args[0] == "search_purchase_orders"
    ]
    assert po_calls == []


@pytest.mark.asyncio
async def test_execute_plan_iteration_unknown_from_step_raises() -> None:
    """A step's iterate_over.from_step must reference a previous
    step's output. Otherwise it's a planner bug."""
    plan = [
        Step(
            step_id=1,
            tool_name="search_purchase_orders",
            tool_args={"supplier_id": "$iteration_value"},
            iterate_over={"from_step": "does_not_exist", "field": "SupplierId"},
            client_filters=[],
            output_name="open_pos",
            output_dedupe_by=None,
        ),
    ]
    session = AsyncMock()
    with pytest.raises(RuntimeError, match="unknown output"):
        await execute_plan(plan, session)


@pytest.mark.asyncio
async def test_execute_plan_iteration_propagates_per_call_exception() -> None:
    """If any single iterated call raises, the plan fails — no partial
    aggregation. (Fail-the-whole-plan policy.)"""
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
        Step(
            step_id=2,
            tool_name="search_purchase_orders",
            tool_args={"supplier_id": "$iteration_value"},
            iterate_over={"from_step": "us_suppliers", "field": "SupplierId"},
            client_filters=[],
            output_name="open_pos",
            output_dedupe_by=None,
        ),
    ]
    session = AsyncMock()
    # First call (Step 1) succeeds; second (first iteration of Step 2) fails.
    session.call_tool.side_effect = [
        _call_tool_result(
            [_text_block(json.dumps([{"SupplierId": 100}, {"SupplierId": 200}]))]
        ),
        RuntimeError("fusion 500"),
    ]
    with pytest.raises(RuntimeError, match="fusion 500"):
        await execute_plan(plan, session)


# ─────────────────────────────────────────────────────────────────────
# Anchor plan — end-to-end with mocked session
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_plan_anchor_plan_with_mocked_session() -> None:
    """
    Run the full 3-step anchor plan against a mocked session that
    returns realistic-shaped data. Verifies the executor handles the
    full Block 1 → Block 2 → Block 3 flow including iteration, client
    filtering, and dedup — without needing live Fusion.
    """
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
        Step(
            step_id=2,
            tool_name="search_purchase_orders",
            tool_args={"supplier_id": "$iteration_value"},
            iterate_over={"from_step": "us_suppliers", "field": "SupplierId"},
            client_filters=[
                {"field": "StatusCode", "op": "equals", "value": "OPEN"}
            ],
            output_name="open_pos",
            output_dedupe_by=None,
        ),
        Step(
            step_id=3,
            tool_name="get_buyer",
            tool_args={"buyer_id": "$iteration_value"},
            iterate_over={"from_step": "open_pos", "field": "BuyerId"},
            client_filters=[],
            output_name="buyers",
            output_dedupe_by="BuyerId",
        ),
    ]
    # Step 1: 2 US suppliers.
    # Step 2 (×2): supplier 100 has 1 OPEN PO with BuyerId 555.
    #              supplier 200 has 1 OPEN and 1 CLOSED PO with BuyerIds 555 and 999.
    # Step 3 (×2 after dedup): 2 unique buyers.
    session = _mock_session_sequence([
        [{"SupplierId": 100}, {"SupplierId": 200}],
        [{"POHeaderId": "p1", "StatusCode": "OPEN", "BuyerId": 555}],
        [
            {"POHeaderId": "p2", "StatusCode": "OPEN", "BuyerId": 555},
            {"POHeaderId": "p3", "StatusCode": "CLOSED", "BuyerId": 999},
        ],
        {"PersonId": 555, "DisplayName": "Alice"},
    ])

    outputs, _ = await execute_plan(plan, session)

    assert outputs["us_suppliers"] == [
        {"SupplierId": 100}, {"SupplierId": 200}
    ]
    # Only OPEN POs across both suppliers (2 total).
    assert outputs["open_pos"] == [
        {"POHeaderId": "p1", "StatusCode": "OPEN", "BuyerId": 555},
        {"POHeaderId": "p2", "StatusCode": "OPEN", "BuyerId": 555},
    ]
    # Both OPEN POs have BuyerId=555, deduped to one — so only one
    # get_buyer call and one buyer record.
    assert outputs["buyers"] == [
        {"PersonId": 555, "DisplayName": "Alice"}
    ]
    buyer_calls = [
        c for c in session.call_tool.await_args_list
        if c.args[0] == "get_buyer"
    ]
    assert len(buyer_calls) == 1


# ─────────────────────────────────────────────────────────────────────
# F2b — filter_source_when_empty unit tests (mocked)
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_filter_source_step_keeps_items_with_empty_iteration() -> None:
    """The headline F2b behavior: a source item is KEPT if its
    per-iteration call returns an empty list."""
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
        Step(
            step_id=2,
            tool_name="search_invoices",
            tool_args={
                "supplier_number": "$iteration_value",
                "invoice_date_after": "2025-11-26",
            },
            iterate_over={
                "from_step": "us_suppliers", "field": "SupplierNumber"
            },
            client_filters=[],
            output_name="us_suppliers_no_recent_invoices",
            output_dedupe_by=None,
            filter_source_when_empty=True,
        ),
    ]
    session = _mock_session_sequence([
        # Step 1: 3 suppliers.
        [
            {"SupplierId": 100, "SupplierNumber": "S100", "Supplier": "Acme"},
            {"SupplierId": 200, "SupplierNumber": "S200", "Supplier": "Beta"},
            {"SupplierId": 300, "SupplierNumber": "S300", "Supplier": "Gamma"},
        ],
        # Step 2 iter 1 (S100): no recent invoices → KEEP supplier 100.
        [],
        # Step 2 iter 2 (S200): one invoice → DROP supplier 200.
        [{"InvoiceId": 9001, "SupplierNumber": "S200"}],
        # Step 2 iter 3 (S300): no recent invoices → KEEP supplier 300.
        [],
    ])

    outputs, _ = await execute_plan(plan, session)

    assert outputs["us_suppliers_no_recent_invoices"] == [
        {"SupplierId": 100, "SupplierNumber": "S100", "Supplier": "Acme"},
        {"SupplierId": 300, "SupplierNumber": "S300", "Supplier": "Gamma"},
    ]
    # Three iterated calls were made (one per supplier).
    invoice_calls = [
        c for c in session.call_tool.await_args_list
        if c.args[0] == "search_invoices"
    ]
    assert len(invoice_calls) == 3


@pytest.mark.asyncio
async def test_filter_source_step_no_items_survive() -> None:
    """If every source item's iteration returns non-empty, the output
    is empty."""
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
        Step(
            step_id=2,
            tool_name="search_invoices",
            tool_args={
                "supplier_number": "$iteration_value",
                "invoice_date_after": "2025-11-26",
            },
            iterate_over={
                "from_step": "us_suppliers", "field": "SupplierNumber"
            },
            client_filters=[],
            output_name="us_suppliers_no_recent_invoices",
            output_dedupe_by=None,
            filter_source_when_empty=True,
        ),
    ]
    session = _mock_session_sequence([
        [
            {"SupplierId": 100, "SupplierNumber": "S100"},
            {"SupplierId": 200, "SupplierNumber": "S200"},
        ],
        [{"InvoiceId": 1}],
        [{"InvoiceId": 2}],
    ])

    outputs, _ = await execute_plan(plan, session)

    assert outputs["us_suppliers_no_recent_invoices"] == []


@pytest.mark.asyncio
async def test_filter_source_step_all_items_survive() -> None:
    """If every source item's iteration returns empty, the output is
    the full source list (in original order)."""
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
        Step(
            step_id=2,
            tool_name="search_invoices",
            tool_args={
                "supplier_number": "$iteration_value",
                "invoice_date_after": "2025-11-26",
            },
            iterate_over={
                "from_step": "us_suppliers", "field": "SupplierNumber"
            },
            client_filters=[],
            output_name="us_suppliers_no_recent_invoices",
            output_dedupe_by=None,
            filter_source_when_empty=True,
        ),
    ]
    source = [
        {"SupplierId": 100, "SupplierNumber": "S100"},
        {"SupplierId": 200, "SupplierNumber": "S200"},
    ]
    session = _mock_session_sequence([source, [], []])

    outputs, _ = await execute_plan(plan, session)

    assert outputs["us_suppliers_no_recent_invoices"] == source


@pytest.mark.asyncio
async def test_filter_source_step_empty_source_makes_no_calls() -> None:
    """If the source produced 0 items, no iteration calls fire and the
    output is empty."""
    plan = [
        Step(
            step_id=1,
            tool_name="search_suppliers_by_country",
            tool_args={"country": "ZZ"},
            iterate_over=None,
            client_filters=[],
            output_name="zz_suppliers",
            output_dedupe_by=None,
        ),
        Step(
            step_id=2,
            tool_name="search_invoices",
            tool_args={
                "supplier_number": "$iteration_value",
                "invoice_date_after": "2025-11-26",
            },
            iterate_over={
                "from_step": "zz_suppliers", "field": "SupplierNumber"
            },
            client_filters=[],
            output_name="zz_suppliers_no_recent_invoices",
            output_dedupe_by=None,
            filter_source_when_empty=True,
        ),
    ]
    session = _mock_session([])

    outputs, _ = await execute_plan(plan, session)

    assert outputs["zz_suppliers_no_recent_invoices"] == []
    invoice_calls = [
        c for c in session.call_tool.await_args_list
        if c.args[0] == "search_invoices"
    ]
    assert invoice_calls == []


@pytest.mark.asyncio
async def test_filter_source_step_skips_items_with_none_iteration_field() -> None:
    """Source items where the iteration field is None are NOT included
    in the output and NOT iterated. v1 design choice documented in
    the executor docstring."""
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
        Step(
            step_id=2,
            tool_name="search_invoices",
            tool_args={
                "supplier_number": "$iteration_value",
                "invoice_date_after": "2025-11-26",
            },
            iterate_over={
                "from_step": "us_suppliers", "field": "SupplierNumber"
            },
            client_filters=[],
            output_name="us_suppliers_no_recent_invoices",
            output_dedupe_by=None,
            filter_source_when_empty=True,
        ),
    ]
    session = _mock_session_sequence([
        [
            {"SupplierId": 100, "SupplierNumber": "S100"},
            {"SupplierId": 200, "SupplierNumber": None},  # skip
            {"SupplierId": 300},  # field missing entirely; skip
            {"SupplierId": 400, "SupplierNumber": "S400"},
        ],
        # Only 2 iteration calls (for S100 and S400).
        [],     # S100: empty → keep
        [],     # S400: empty → keep
    ])

    outputs, _ = await execute_plan(plan, session)

    assert outputs["us_suppliers_no_recent_invoices"] == [
        {"SupplierId": 100, "SupplierNumber": "S100"},
        {"SupplierId": 400, "SupplierNumber": "S400"},
    ]
    invoice_calls = [
        c for c in session.call_tool.await_args_list
        if c.args[0] == "search_invoices"
    ]
    assert len(invoice_calls) == 2


@pytest.mark.asyncio
async def test_filter_source_step_unknown_from_step_raises() -> None:
    """If from_step doesn't exist in outputs, it's a planner bug —
    raise loudly."""
    plan = [
        Step(
            step_id=1,
            tool_name="search_invoices",
            tool_args={
                "supplier_number": "$iteration_value",
                "invoice_date_after": "2025-11-26",
            },
            iterate_over={
                "from_step": "missing_step", "field": "SupplierNumber"
            },
            client_filters=[],
            output_name="filtered",
            output_dedupe_by=None,
            filter_source_when_empty=True,
        ),
    ]
    session = AsyncMock()
    with pytest.raises(RuntimeError, match="unknown output"):
        await execute_plan(plan, session)


@pytest.mark.asyncio
async def test_filter_source_step_with_iterate_over_none_raises() -> None:
    """filter_source_when_empty=True is incompatible with
    iterate_over=None. Catches a planner bug at execution time."""
    plan = [
        Step(
            step_id=1,
            tool_name="search_invoices",
            tool_args={"supplier_number": "X"},
            iterate_over=None,
            client_filters=[],
            output_name="oops",
            output_dedupe_by=None,
            filter_source_when_empty=True,
        ),
    ]
    session = AsyncMock()
    with pytest.raises(RuntimeError, match="coupled"):
        await execute_plan(plan, session)


@pytest.mark.asyncio
async def test_execute_plan_anchor_unaffected_by_filter_source_branch() -> None:
    """Regression guard: the F2b branch must NOT change anchor-plan
    behavior. Run the 3-step anchor with mocked data and verify the
    same outputs as the existing anchor test."""
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
        Step(
            step_id=2,
            tool_name="search_purchase_orders",
            tool_args={"supplier_id": "$iteration_value"},
            iterate_over={"from_step": "us_suppliers", "field": "SupplierId"},
            client_filters=[
                {"field": "StatusCode", "op": "equals", "value": "OPEN"}
            ],
            output_name="open_pos",
            output_dedupe_by=None,
        ),
    ]
    session = _mock_session_sequence([
        [{"SupplierId": 100}, {"SupplierId": 200}],
        [{"POHeaderId": "p1", "StatusCode": "OPEN"}],
        [{"POHeaderId": "p2", "StatusCode": "OPEN"}],
    ])
    outputs, _ = await execute_plan(plan, session)
    assert outputs["open_pos"] == [
        {"POHeaderId": "p1", "StatusCode": "OPEN"},
        {"POHeaderId": "p2", "StatusCode": "OPEN"},
    ]


# ─────────────────────────────────────────────────────────────────────
# Integration tests — hit the live MCP server
#
# Requires:
# - MCP server running on http://127.0.0.1:3333/mcp/
# - personas.yaml present
# - Fusion pod reachable from the MCP server
#
# Marked @pytest.mark.integration; skipped by default. Run with:
#     pytest -m integration tests/test_executor.py
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml missing",
)
@pytest.mark.asyncio
async def test_execute_plan_step1_against_live_mcp_server() -> None:
    """End-to-end: run the anchor plan's Step 1 against the live MCP
    server. Confirms FastMCP wire-format assumptions."""
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
            outputs, _ = await execute_plan(plan, session)

    assert set(outputs.keys()) == {"us_suppliers"}
    suppliers = outputs["us_suppliers"]
    assert isinstance(suppliers, list)
    assert len(suppliers) > 0
    first = suppliers[0]
    assert "SupplierId" in first
    assert "Supplier" in first
    assert first.get("MatchedCountry") == "US"


@pytest.mark.integration
@pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml missing",
)
@pytest.mark.asyncio
async def test_execute_plan_two_step_with_iteration_against_live_mcp_server() -> None:
    """
    End-to-end iteration: Step 1 fetches US suppliers; Step 2 iterates
    SupplierId calling search_purchase_orders with the OPEN client filter.

    Validates that iteration + $iteration_value substitution + per-call
    client filtering all work against the live MCP server with real
    Fusion data.

    Cost note: this hits Fusion once per US supplier (~25 calls). Slow
    by design. Worth it for the end-to-end confirmation.
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
        Step(
            step_id=2,
            tool_name="search_purchase_orders",
            tool_args={"supplier_id": "$iteration_value"},
            iterate_over={"from_step": "us_suppliers", "field": "SupplierId"},
            client_filters=[
                {"field": "StatusCode", "op": "equals", "value": "OPEN"}
            ],
            output_name="open_pos",
            output_dedupe_by=None,
        ),
    ]

    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            outputs, _ = await execute_plan(plan, session)

    assert set(outputs.keys()) == {"us_suppliers", "open_pos"}
    assert isinstance(outputs["us_suppliers"], list)
    assert isinstance(outputs["open_pos"], list)
    # The demo pod has at least some open POs for US suppliers.
    # Don't assert an exact count (data may shift); just confirm the
    # aggregated list shape is right and the client filter worked.
    for po in outputs["open_pos"]:
        assert po.get("StatusCode") == "OPEN"


@pytest.mark.integration
@pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml missing",
)
@pytest.mark.asyncio
async def test_execute_plan_filter_source_when_empty_against_live_mcp_server() -> None:
    """
    F2b end-to-end: against live MCP server, run a 2-step plan that
    fetches US suppliers then filters them to those with no invoices
    in the last 6 months.

    Verifies:
    - Step 2 iterates per US supplier, calling search_invoices with
      supplier_number + invoice_date_after.
    - For each supplier where the call returns empty, the supplier is
      KEPT in the output. For those where it returns non-empty, the
      supplier is DROPPED.
    - Output items are Supplier dicts (full source items), not Invoice
      records.

    Cost note: hits Fusion ~25 times for invoices (one per US supplier).
    Slow by design. Plus the 25 + 25 calls in the other integration
    test; running -m integration may take 2-3 minutes.

    Honest framing: we don't assert specific counts because real
    Fusion data drifts. We assert: output is a list of Supplier-shaped
    dicts, and each one has the SupplierNumber field (which the planner
    used as the iteration key).
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    MCP_SERVER_URL = "http://127.0.0.1:3333/mcp/"

    # Use a fixed date so the test isn't time-bombed by demo-pod drift
    # over months. The cutoff date matters for the assertion that
    # search_invoices was called with this exact value.
    cutoff = "2025-11-26"

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
        Step(
            step_id=2,
            tool_name="search_invoices",
            tool_args={
                "supplier_number": "$iteration_value",
                "invoice_date_after": cutoff,
            },
            iterate_over={
                "from_step": "us_suppliers", "field": "SupplierNumber"
            },
            client_filters=[],
            output_name="us_suppliers_no_recent_invoices",
            output_dedupe_by=None,
            filter_source_when_empty=True,
        ),
    ]

    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            outputs, _ = await execute_plan(plan, session)

    assert set(outputs.keys()) == {
        "us_suppliers", "us_suppliers_no_recent_invoices"
    }
    # We got SOME US suppliers.
    assert len(outputs["us_suppliers"]) > 0
    # The filter MUST be a subset of the source.
    source_ids = {s.get("SupplierId") for s in outputs["us_suppliers"]}
    filtered_ids = {
        s.get("SupplierId")
        for s in outputs["us_suppliers_no_recent_invoices"]
    }
    assert filtered_ids.issubset(source_ids), (
        "Filtered output must be a subset of the source items"
    )
    # Each filtered item is a Supplier-shaped record, not an Invoice.
    for item in outputs["us_suppliers_no_recent_invoices"]:
        assert "SupplierId" in item
        assert "SupplierNumber" in item
        # Invoice records would have InvoiceId / InvoiceNumber instead.
        assert "InvoiceId" not in item

def test_extract_truncation_meta_returns_none_for_legacy_list() -> None:
    """Legacy list[dict] payloads (un-migrated tools) yield no metadata."""
    from spire.executor.executor import _extract_truncation_meta
    payload = [{"SupplierId": 1}, {"SupplierId": 2}]
    result = _extract_truncation_meta(
        _call_tool_result([_text_block(json.dumps(payload))])
    )
    assert result is None


def test_extract_truncation_meta_extracts_from_envelope() -> None:
    """ToolResult envelopes yield their three metadata fields."""
    from spire.executor.executor import _extract_truncation_meta
    payload = {
        "items": [{"a": 1}],
        "total_available": 137,
        "limit_applied": 25,
        "truncated": True,
    }
    result = _extract_truncation_meta(
        _call_tool_result([_text_block(json.dumps(payload))])
    )
    assert result == {
        "total_available": 137,
        "limit_applied": 25,
        "truncated": True,
    }