"""
Executor for the KG-driven path (Architecture Option 3).

Consumes a Plan produced by spire.planner.planner.generate_plan and
runs each Step against the Spire MCP server. No LLM in the loop.

Scope (current):
- Non-iterating steps (A.1)
- Iterating steps with $iteration_value substitution and
  output_dedupe_by handling (A.2)
- Negation-by-absence steps (filter_source_when_empty=True): for each
  source item, call the tool; KEEP the source item iff the call
  returns an empty list. Output is the FILTERED source items, not
  the iteration results. (F2b)
- client_filters with 'equals' operator
- Returns dict[output_name, list[dict]]

Design decisions locked for v1:
- Sequential execution (no asyncio.gather parallelism)
- Fail-the-whole-plan on any tool error (no partial results)
- Raw MCP (session.call_tool), no LangChain
- Caller manages the ClientSession; we accept it as a parameter
- Source items with None for the iteration field are SKIPPED entirely
  in filter_source_when_empty mode (they don't appear in the output).
"""

from __future__ import annotations

import json
from typing import Any

from mcp import ClientSession

from spire.planner.planner import Plan, Step


# Sentinel value in step.tool_args; the executor substitutes the current
# iteration value for any key whose value equals this string.
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
# Iteration helpers
# ─────────────────────────────────────────────────────────────────────


def _find_substitution_key(tool_args: dict[str, Any]) -> str:
    """
    Find the single key in tool_args whose value is the iteration
    sentinel.

    v1 contract: exactly one such key per iterating step. Zero or two
    or more are planner bugs and raise RuntimeError loudly. The exec
    loop calls this once per iterating step, not once per iteration
    value, so the cost is bounded.
    """
    keys = [k for k, v in tool_args.items() if v == ITERATION_SENTINEL]
    if len(keys) == 0:
        raise RuntimeError(
            f"Iterating step's tool_args contain no {ITERATION_SENTINEL!r} "
            "sentinel; planner bug. tool_args=" + repr(tool_args)
        )
    if len(keys) > 1:
        raise RuntimeError(
            f"Iterating step's tool_args contain multiple "
            f"{ITERATION_SENTINEL!r} sentinels (keys: {keys}); "
            "v1 supports exactly one substitution key per step."
        )
    return keys[0]


def _collect_iteration_values(
    outputs: dict[str, list[dict]],
    iterate_over: dict[str, str],
    dedupe: bool,
) -> list[Any]:
    """
    Extract the values to iterate over from a previous step's output.

    Pulls iterate_over.field from each item in
    outputs[iterate_over.from_step]. Drops None values. If dedupe is
    True, dedupes while preserving order of first occurrence.

    Raises:
        RuntimeError if from_step is not in outputs (planner bug).
    """
    from_step = iterate_over["from_step"]
    field = iterate_over["field"]
    if from_step not in outputs:
        raise RuntimeError(
            f"Iterating step references unknown output {from_step!r}. "
            "Planner bug: a step's iterate_over.from_step must name a "
            "previous step's output_name."
        )

    source_items = outputs[from_step]
    raw_values = [item.get(field) for item in source_items]
    # Drop None: an item that didn't carry the field shouldn't be
    # iterated. This is a real condition (Fusion responses can be
    # sparse) and shouldn't crash the plan.
    values = [v for v in raw_values if v is not None]

    if not dedupe:
        return values

    seen: set[Any] = set()
    deduped: list[Any] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            deduped.append(v)
    return deduped


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


async def _execute_iterating_step(
    step: Step,
    session: ClientSession,
    outputs: dict[str, list[dict]],
) -> list[dict]:
    """
    Execute a single step that iterates over a previous step's output.

    For each value pulled from outputs[step.iterate_over.from_step]
    by step.iterate_over.field:
    - Build per-iteration tool_args by replacing the sentinel-valued
      key with the current value
    - Call the MCP tool
    - Parse the result and apply client_filters
    - Concatenate into a single flat list

    Note on output_dedupe_by semantics: the field name suggests
    deduping the OUTPUT, but the planner uses it to control whether
    iteration values are deduped before calling the tool (avoiding
    redundant calls like get_buyer with the same buyer_id twice).
    v1 implements iteration-value dedup; v1.1 could distinguish if
    output-item dedup ever becomes a separate need.
    """
    if step.iterate_over is None:
        # Should never reach here; execute_plan dispatches based on
        # iterate_over. But guard anyway.
        raise RuntimeError(
            f"Step {step.step_id} marked as iterating but iterate_over "
            "is None."
        )

    substitution_key = _find_substitution_key(step.tool_args)
    dedupe = step.output_dedupe_by is not None
    values = _collect_iteration_values(outputs, step.iterate_over, dedupe)

    aggregated: list[dict] = []
    for value in values:
        per_iter_args = dict(step.tool_args)  # shallow copy is enough
        per_iter_args[substitution_key] = value

        call_result = await session.call_tool(step.tool_name, per_iter_args)
        items = _parse_tool_result(call_result)
        items = _apply_client_filters(items, step.client_filters)
        aggregated.extend(items)

    return aggregated


async def _execute_filter_source_step(
    step: Step,
    session: ClientSession,
    outputs: dict[str, list[dict]],
) -> list[dict]:
    """
    Execute a step whose semantic is "filter the source by per-iteration
    emptiness" (F2: negation by absence).

    For each item in the source step's output:
      - Read the iteration field's value (e.g. SupplierNumber).
      - If that value is None: SKIP the item entirely (do NOT include
        in output). v1 design choice. Documented in module docstring.
      - Otherwise: call the tool with the value substituted in.
        Apply client_filters.
        If the result is empty -> KEEP the source item (full original dict).
        If the result is non-empty -> DROP the source item.

    Returns the kept source items in their original order. Output items
    are full source dicts (e.g. Supplier records), NOT the iteration
    results.

    The point of this step shape: handle "X with NO Y" queries — e.g.
    "suppliers with no invoices in the last 6 months". The iterating
    tool finds Ys per X; emptiness means the negation holds.
    """
    if step.iterate_over is None:
        raise RuntimeError(
            f"Step {step.step_id} has filter_source_when_empty=True but "
            "iterate_over is None. Planner bug: these fields are coupled."
        )

    substitution_key = _find_substitution_key(step.tool_args)
    from_step = step.iterate_over["from_step"]
    iter_field = step.iterate_over["field"]

    if from_step not in outputs:
        raise RuntimeError(
            f"filter_source_when_empty step references unknown output "
            f"{from_step!r}. Planner bug."
        )
    source_items = outputs[from_step]

    kept: list[dict] = []
    for source_item in source_items:
        iteration_value = source_item.get(iter_field)
        if iteration_value is None:
            # Skip: no join key, can't iterate. Documented v1 behavior.
            continue

        per_iter_args = dict(step.tool_args)
        per_iter_args[substitution_key] = iteration_value

        call_result = await session.call_tool(step.tool_name, per_iter_args)
        items = _parse_tool_result(call_result)
        items = _apply_client_filters(items, step.client_filters)

        # Negation by absence: empty result means the source item
        # passes the filter.
        if not items:
            kept.append(source_item)

    return kept


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
        For iterating steps, results across iterations are concatenated
        into one flat list.
        For filter_source_when_empty steps, the output is the source
        items kept by negation-by-absence (i.e. those whose iteration
        returned empty).

    Raises:
        RuntimeError: if MCP returns an unexpectedly shaped result,
            or if a step's iterate_over references an output that
            doesn't exist (planner bug), or if a non-iterating step
            carries the iteration sentinel (planner bug), or if an
            iterating step carries zero / multiple sentinels.
        ValueError: if a client_filters operator is unknown.
        Any exception from session.call_tool propagates (fail-the-whole-
        plan policy).
    """
    outputs: dict[str, list[dict]] = {}

    for step in plan:
        if step.iterate_over is None:
            if step.filter_source_when_empty:
                raise RuntimeError(
                    f"Step {step.step_id} has filter_source_when_empty=True "
                    "but iterate_over is None. Planner bug: these fields "
                    "are coupled."
                )
            items = await _execute_non_iterating_step(step, session)
        elif step.filter_source_when_empty:
            items = await _execute_filter_source_step(step, session, outputs)
        else:
            items = await _execute_iterating_step(step, session, outputs)
        outputs[step.output_name] = items

    return outputs
