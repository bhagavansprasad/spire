"""
Executor for the KG-driven path (Architecture Option 3).

Consumes a Plan produced by spire.planner.planner.generate_plan and
runs each Step against the Spire MCP server. No LLM in the loop.

A.1 scope (this version):
- Executes non-iterating steps only (iterate_over is None).
- Applies client_filters (equals operator) — though the anchor plan's
  Step 1 has none, the code path is present for symmetry with A.2.
- Returns dict[output_name, list[dict]].

A.2 will add:
- Iteration over previous outputs with $iteration_value substitution
- output_dedupe_by handling

A.3 will add:
- scripts/run_plan.py end-to-end driver

Design decisions locked for v1:
- Sequential execution (no asyncio.gather parallelism)
- Fail-the-whole-plan on any tool error (no partial results)
- Raw MCP (session.call_tool), no LangChain
- Caller manages the ClientSession; we accept it as a parameter
"""

from __future__ import annotations

import json
from typing import Any

from mcp import ClientSession

from spire.planner.planner import Plan, Step


# Sentinel returned in step.tool_args when iteration is expected to
# substitute the value per-item. Reserved for A.2; A.1 only rejects
# iterating steps before getting here.
ITERATION_SENTINEL = "$iteration_value"


# ─────────────────────────────────────────────────────────────────────
# MCP result parsing
# ─────────────────────────────────────────────────────────────────────


def _parse_tool_result(call_tool_result: Any) -> list[dict]:
    """
    Extract the JSON payload from an MCP CallToolResult.

    The Spire MCP tools (search_suppliers, search_invoices, etc.) return
    Python list[dict] or dict from their underlying functions. FastMCP
    serializes those to JSON and wraps in a TextContent block. The
    CallToolResult.content is a list of content blocks.

    We expect exactly one TextContent block carrying the JSON.

    Returns:
        list[dict] — even for tools that return a single dict (e.g.,
        get_buyer), we normalize to a list with 0 or 1 elements so the
        executor's downstream iteration code is uniform.

    Raises:
        RuntimeError if the result is shaped unexpectedly (multiple
        blocks, non-text block, unparseable JSON). These indicate an
        MCP/server-side problem, not a user error.
    """
    content = getattr(call_tool_result, "content", None)
    if not content:
        # Some tools (notably get_buyer) can return None / null on
        # not-found. Treat empty content as an empty result list.
        return []

    if len(content) != 1:
        raise RuntimeError(
            f"Expected exactly one content block from MCP tool call; "
            f"got {len(content)}."
        )

    block = content[0]
    # FastMCP's TextContent has .type == "text" and .text == the payload.
    block_type = getattr(block, "type", None)
    if block_type != "text":
        raise RuntimeError(
            f"Expected TextContent block from MCP tool call; "
            f"got type={block_type!r}."
        )
    raw_text = getattr(block, "text", None)
    if raw_text is None:
        raise RuntimeError("TextContent block has no .text attribute.")

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"MCP tool result was not valid JSON: {exc}"
        ) from exc

    # Normalize to list[dict].
    if payload is None:
        return []
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return payload
    raise RuntimeError(
        f"MCP tool result JSON was neither dict, list, nor null; "
        f"got {type(payload).__name__}."
    )


# ─────────────────────────────────────────────────────────────────────
# Client-side filters
# ─────────────────────────────────────────────────────────────────────


def _apply_client_filters(
    items: list[dict], filters: list[dict[str, Any]]
) -> list[dict]:
    """
    Apply a list of client-side filters to a list of items.

    Each filter is a dict like:
        {"field": "StatusCode", "op": "equals", "value": "OPEN"}

    v1 supports only the 'equals' operator (case-sensitive exact match).
    Raises ValueError on any unknown operator — silent ignores would
    mask planner bugs.
    """
    if not filters:
        return items

    result = items
    for f in filters:
        op = f.get("op")
        field = f["field"]
        value = f["value"]
        if op == "equals":
            result = [item for item in result if item.get(field) == value]
        else:
            raise ValueError(
                f"Unsupported client-filter op {op!r}. "
                "v1 supports only 'equals'."
            )
    return result


# ─────────────────────────────────────────────────────────────────────
# Step execution
# ─────────────────────────────────────────────────────────────────────


async def _execute_non_iterating_step(
    step: Step, session: ClientSession
) -> list[dict]:
    """
    Execute a single step that does NOT iterate.

    The step's tool_args go to the MCP tool verbatim. Result is parsed
    and any client_filters applied.
    """
    # Sanity check: a non-iterating step should not contain the
    # iteration sentinel in its args. Catch a planner bug loudly.
    for k, v in step.tool_args.items():
        if v == ITERATION_SENTINEL:
            raise RuntimeError(
                f"Step {step.step_id} ({step.tool_name}) is non-iterating "
                f"but its tool_args contain the iteration sentinel for "
                f"key {k!r}. Planner bug."
            )

    call_result = await session.call_tool(step.tool_name, step.tool_args)
    items = _parse_tool_result(call_result)
    items = _apply_client_filters(items, step.client_filters)
    return items


# ─────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────


async def execute_plan(
    plan: Plan, session: ClientSession
) -> dict[str, list[dict]]:
    """
    Run a Plan against the MCP server. Returns the outputs of every
    step keyed by output_name.

    Args:
        plan: The list of Steps produced by spire.planner.generate_plan.
        session: An already-initialized MCP ClientSession. Caller is
            responsible for opening and closing it (same convention as
            runner.py).

    Returns:
        dict mapping each step's output_name to its result list.
        For tools that return a single record (e.g. get_buyer), the
        record is wrapped in a single-element list.

    Raises:
        NotImplementedError: if the plan contains iterating steps
            (iterate_over is not None). Iteration lands in A.2.
        RuntimeError: if MCP returns an unexpectedly shaped result.
        ValueError: if a client_filters operator is unknown.
        Any exception from session.call_tool propagates (fail-the-whole-
        plan policy).
    """
    outputs: dict[str, list[dict]] = {}

    for step in plan:
        if step.iterate_over is not None:
            raise NotImplementedError(
                f"Step {step.step_id} requires iteration; "
                "iteration lands in executor batch A.2."
            )

        items = await _execute_non_iterating_step(step, session)
        outputs[step.output_name] = items

    return outputs
