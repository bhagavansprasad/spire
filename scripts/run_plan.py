"""End-to-end driver for the KG-driven path (Architecture Option 3).

Builds a structured Intent, generates a Plan from KG data via the
planner, runs the Plan against the Spire MCP server via the executor,
and prints a human-readable summary of what happened at each layer.

This is the script that demonstrates the Design 3 architecture end to
end with zero LLM in the planning step.

Usage:
    # Terminal 1:
    python -m spire.mcp_server.server

    # Terminal 2:
    python scripts/run_plan.py

The Intent is hardcoded to the POC's anchor question:
    "Show me suppliers in US with open purchase orders, including
     the buyer assigned to each."

Per-run JSON trace lands in traces/<timestamp>.jsonl alongside the
agent-based runner's traces, so KG-driven runs can be compared with
Track A's runs using the same inspector tooling (scripts/inspect_trace.py).
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from spire.agent.tracing import make_trace_logger
from spire.executor.executor import execute_plan
from spire.planner.planner import Intent, Plan, generate_plan


MCP_SERVER_URL = "http://127.0.0.1:3333/mcp/"


# ─────────────────────────────────────────────────────────────────────
# The anchor intent (hardcoded for v1)
#
# CLI args for arbitrary intents are out of scope; the goal of A.3 is
# a runnable end-to-end demo of the KG-driven path, not a general CLI.
# ─────────────────────────────────────────────────────────────────────


ANCHOR_INTENT = Intent(
    target_entity="Supplier",
    filters=[
        {"type": "country", "value": "US"},
        {"type": "has_open_PO", "value": True},
    ],
    include=["Buyer"],
)


# ─────────────────────────────────────────────────────────────────────
# Pretty-printers
# ─────────────────────────────────────────────────────────────────────


def _format_intent(intent: Intent) -> str:
    """Render an Intent in a single readable block."""
    lines = ["Intent:"]
    lines.append(f"  target_entity: {intent.target_entity}")
    lines.append("  filters:")
    for f in intent.filters:
        lines.append(f"    - {f}")
    lines.append(f"  include: {intent.include}")
    return "\n".join(lines)


def _format_plan(plan: Plan) -> str:
    """Render a Plan as a numbered list of steps with the fields that
    matter at a glance. Full Step dataclass content would be noisy."""
    lines = ["Plan:"]
    for step in plan:
        lines.append(f"  Step {step.step_id}: {step.tool_name}")
        lines.append(f"    tool_args:      {step.tool_args}")
        if step.iterate_over is None:
            lines.append("    iterate_over:   (none — runs once)")
        else:
            lines.append(
                f"    iterate_over:   {step.iterate_over['from_step']}"
                f".{step.iterate_over['field']}"
            )
        if step.client_filters:
            lines.append(f"    client_filters: {step.client_filters}")
        else:
            lines.append("    client_filters: (none)")
        dedupe = step.output_dedupe_by or "(none)"
        lines.append(f"    dedupe_by:      {dedupe}")
        lines.append(f"    output_name:    {step.output_name}")
    return "\n".join(lines)


def _format_outputs(
    outputs: dict[str, list[dict]], sample_size: int = 3
) -> str:
    """Render outputs as: per-step count + first-N sample records."""
    lines = ["Outputs:"]
    for name, items in outputs.items():
        lines.append(f"  {name}: {len(items)} record(s)")
        sample = items[:sample_size]
        for i, record in enumerate(sample, start=1):
            # Trim large records to a single line each.
            rendered = json.dumps(record, default=str)
            if len(rendered) > 240:
                rendered = rendered[:237] + "..."
            lines.append(f"    [{i}] {rendered}")
        if len(items) > sample_size:
            lines.append(f"    ... ({len(items) - sample_size} more)")
    return "\n".join(lines)


def _format_summary(plan: Plan, outputs: dict[str, list[dict]]) -> str:
    """One-screen end-of-run summary."""
    lines = ["Summary:"]
    lines.append(f"  Steps planned:    {len(plan)}")
    total_records = sum(len(v) for v in outputs.values())
    lines.append(f"  Records returned: {total_records} (across all steps)")
    last_step = plan[-1] if plan else None
    if last_step is not None and last_step.output_name in outputs:
        final_count = len(outputs[last_step.output_name])
        lines.append(
            f"  Final output:     {final_count} record(s) under "
            f"'{last_step.output_name}'"
        )
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────


async def _run(intent: Intent) -> int:
    """Build a plan from the intent, execute it, print the result.

    Returns a shell-style exit code: 0 success, non-zero failure.
    """
    logger, trace_path = make_trace_logger()
    logger.info("run_plan_started", intent=asdict(intent))

    # ── Step 1: plan (no LLM, no network for Fusion — KG only) ────
    print(_format_intent(intent))
    print()
    try:
        plan = generate_plan(intent)
    except Exception as exc:
        logger.error("plan_generation_failed", error=str(exc))
        print(f"ERROR generating plan: {exc}", file=sys.stderr)
        return 1
    logger.info(
        "plan_generated",
        step_count=len(plan),
        steps=[
            {
                "step_id": s.step_id,
                "tool_name": s.tool_name,
                "output_name": s.output_name,
            }
            for s in plan
        ],
    )
    print(_format_plan(plan))
    print()

    # ── Step 2: execute (MCP -> Fusion) ───────────────────────────
    print("Executing plan against MCP server ...")
    print()
    try:
        async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                logger.info("mcp_session_initialized", url=MCP_SERVER_URL)
                outputs = await execute_plan(plan, session)
    except Exception as exc:
        logger.error("plan_execution_failed", error=str(exc))
        print(f"ERROR executing plan: {exc}", file=sys.stderr)
        return 1
    logger.info(
        "plan_executed",
        output_record_counts={k: len(v) for k, v in outputs.items()},
    )

    # ── Step 3: present ───────────────────────────────────────────
    print(_format_outputs(outputs))
    print()
    print(_format_summary(plan, outputs))
    print()
    print(f"Trace: {trace_path}")
    logger.info("run_plan_finished")
    return 0


def main() -> int:
    return asyncio.run(_run(ANCHOR_INTENT))


if __name__ == "__main__":
    sys.exit(main())
