"""End-to-end driver for the KG-driven path (Architecture Option 3).

Builds a structured Intent, generates a Plan from KG data via the
planner, runs the Plan against the Spire MCP server via the executor,
synthesizes a coherent answer via an LLM with structured output and
hallucination validation, and prints everything along the way.

This is the script that demonstrates the Design 3 architecture end to
end. The planner and executor contain no LLM. The synthesizer is the
ONLY LLM in the pipeline and produces a Pydantic-typed answer that's
cross-validated against the executor's source data to catch invented IDs.

Usage:
    # Terminal 1:
    python -m spire.mcp_server.server

    # Terminal 2 (default: original Track A prompt with negation):
    python scripts/run_plan.py

    # Or explicitly:
    python scripts/run_plan.py --intent original
    python scripts/run_plan.py --intent anchor

Intent options:
    original — "Show me suppliers in US with no invoices in 6 months
                but with open purchase orders, including the buyer
                assigned to each." (The original Track A prompt;
                requires F2's no_invoices_in_N_months pattern.)
    anchor   — "Show me suppliers in US with open purchase orders,
                including the buyer assigned to each." (The v1 anchor;
                negation clause dropped.)

Per-run JSON trace lands in traces/<timestamp>.jsonl alongside the
agent-based runner's traces.

Exit codes:
    0 — success (plan generated, executed, synthesized)
    1 — plan generation failed
    2 — plan execution failed
    3 — synthesis failed (including hallucination)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from spire.agent.tracing import make_trace_logger
from spire.executor.executor import execute_plan
from spire.planner.planner import Intent, Plan, generate_plan
from spire.synthesizer.synthesizer import (
    HallucinationError,
    SynthesizedResponse,
    synthesize_response,
)


MCP_SERVER_URL = "http://127.0.0.1:3333/mcp/"


# ─────────────────────────────────────────────────────────────────────
# The two hardcoded intents
#
# CLI arg --intent selects between them. v1 still hardcodes Intent
# construction (no LLM intent parser yet); --intent is a thin convenience
# for testing both shapes without editing the script.
# ─────────────────────────────────────────────────────────────────────


ANCHOR_INTENT = Intent(
    target_entity="Supplier",
    filters=[
        {"type": "country", "value": "US"},
        {"type": "has_open_PO", "value": True},
    ],
    include=["Buyer"],
)


# Original Track A prompt:
# "Show me suppliers in US with no invoices in 6 months but with open
#  purchase orders, including the buyer assigned to each."
ORIGINAL_INTENT = Intent(
    target_entity="Supplier",
    filters=[
        {"type": "country", "value": "US"},
        {"type": "has_no_recent_invoices", "value": {"months": 6}},
        {"type": "has_open_PO", "value": True},
    ],
    include=["Buyer"],
)


INTENT_CHOICES: dict[str, Intent] = {
    "anchor": ANCHOR_INTENT,
    "original": ORIGINAL_INTENT,
}


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
        if step.filter_source_when_empty:
            lines.append(
                "    filter_source:  YES (keeps source items whose "
                "iteration returned empty)"
            )
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
            rendered = json.dumps(record, default=str)
            if len(rendered) > 240:
                rendered = rendered[:237] + "..."
            lines.append(f"    [{i}] {rendered}")
        if len(items) > sample_size:
            lines.append(f"    ... ({len(items) - sample_size} more)")
    return "\n".join(lines)


def _format_synthesized(response: SynthesizedResponse) -> str:
    """Render the synthesized response: prose summary + structured
    supplier list."""
    lines = ["Answer:", "", response.summary, ""]
    if not response.suppliers:
        lines.append("(No suppliers in the structured result.)")
        return "\n".join(lines)
    lines.append("Suppliers:")
    for s in response.suppliers:
        buyer_str = ", ".join(
            f"{b.display_name} (id={b.person_id})" for b in s.buyers
        ) or "(no buyer)"
        lines.append(
            f"  - {s.supplier_name} "
            f"(SupplierId={s.supplier_id}, SupplierNumber={s.supplier_number}) "
            f"— {s.open_po_count} open PO(s); buyer(s): {buyer_str}"
        )
    return "\n".join(lines)


def _format_summary(
    plan: Plan,
    outputs: dict[str, list[dict]],
    response: SynthesizedResponse,
) -> str:
    """One-screen end-of-run summary."""
    lines = ["Summary:"]
    lines.append(f"  Steps planned:        {len(plan)}")
    total_records = sum(len(v) for v in outputs.values())
    lines.append(f"  Records returned:     {total_records} (across all steps)")
    last_step = plan[-1] if plan else None
    if last_step is not None and last_step.output_name in outputs:
        final_count = len(outputs[last_step.output_name])
        lines.append(
            f"  Final raw output:     {final_count} record(s) under "
            f"'{last_step.output_name}'"
        )
    lines.append(f"  Synthesized answer:   {len(response.suppliers)} supplier(s)")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────


async def _run(intent: Intent, intent_name: str) -> int:
    """Build a plan from the intent, execute it, synthesize an answer,
    print everything. Returns a shell-style exit code."""
    logger, trace_path = make_trace_logger()
    logger.info(
        "run_plan_started",
        intent_name=intent_name,
        intent=asdict(intent),
    )

    # ── Step 1: plan (KG only) ────────────────────────────────────
    print(f"Intent ({intent_name}):")
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
                "filter_source_when_empty": s.filter_source_when_empty,
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
        return 2
    logger.info(
        "plan_executed",
        output_record_counts={k: len(v) for k, v in outputs.items()},
    )
    print(_format_outputs(outputs))
    print()

    # ── Step 3: synthesize (LLM with structured output) ───────────
    print("Synthesizing answer via LLM ...")
    print()
    try:
        response = synthesize_response(outputs)
    except HallucinationError as exc:
        logger.error("synthesis_hallucination", error=str(exc))
        print(
            "ERROR: synthesizer produced output that doesn't match the "
            "executor's data.",
            file=sys.stderr,
        )
        print(f"Details: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        logger.error("synthesis_failed", error=str(exc))
        print(f"ERROR during synthesis: {exc}", file=sys.stderr)
        return 3
    logger.info(
        "synthesis_completed",
        supplier_count=len(response.suppliers),
        summary_length=len(response.summary),
        response=response.model_dump(),
    )

    # ── Present ───────────────────────────────────────────────────
    print(_format_synthesized(response))
    print()
    print(_format_summary(plan, outputs, response))
    print()
    print(f"Trace: {trace_path}")
    logger.info("run_plan_finished")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a KG-driven plan end-to-end."
    )
    parser.add_argument(
        "--intent",
        choices=sorted(INTENT_CHOICES.keys()),
        default="original",
        help=(
            "Which hardcoded Intent to run. 'original' (default) is the "
            "original Track A prompt with the negation clause; 'anchor' "
            "is the v1 simplified prompt without negation."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    intent = INTENT_CHOICES[args.intent]
    return asyncio.run(_run(intent, args.intent))


if __name__ == "__main__":
    sys.exit(main())
