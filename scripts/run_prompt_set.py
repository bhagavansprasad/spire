#!/usr/bin/env python3
"""
Run a fixed set of prompts through the live Spire pipeline, in-process.

No subprocesses. The harness imports the same pipeline pieces run_plan.py
uses (parser, planner, executor, synthesizer) and runs each prompt
sequentially in a single loop, reusing run_plan's own formatters so the
output matches a manual run. The MCP session is opened ONCE and shared
across all prompts.

The prompt set mixes aggregation, ordinary list, and refusal prompts so
one run exercises all three pipeline outcomes.

This is a convenience harness, not a regression test: it runs the
prompts and prints the output. Reading the results is left to you.

Prerequisites (same as a manual run_plan.py run):
  - MCP server running (python -m spire.mcp_server.server)
  - Fusion pod reachable; personas.yaml present
  - GEMINI_API_KEY set; KG reachable

Usage:
  python scripts/run_prompt_set.py
  python scripts/run_prompt_set.py --prompts "Top 5 suppliers by spend in 2022" "List US suppliers"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from fastmcp import Client

from spire.executor.executor import execute_plan
from spire.planner.planner import generate_plan
from spire.synthesizer.synthesizer import (
    UnsupportedEntityError,
    synthesize_response,
)
from spire.nl_parser.parser import parse as parse_prompt
from spire.nl_parser.vocabulary import load_kg_menu
from spire.nl_parser.capability import capability_message

# Reuse run_plan's formatters and server URL so output matches exactly.
from run_plan import (
    MCP_SERVER_URL,
    _format_intent,
    _format_outputs,
    _format_plan,
    _format_summary,
    _format_synthesized,
)


DEFAULT_PROMPTS: list[str] = [
    # — aggregation —
    "Top 10 suppliers by spend in 2022",
    "Top 5 suppliers by spend in 2022",
    "Which suppliers did we spend the most with in 2022",
    # — ordinary list —
    "Show me invoices for supplier 1252",
    "List US suppliers",
    # — refusal (out of scope) —
    "Show me contract renewals due next quarter",
]


async def _run_one(prompt: str, menu, client) -> str:
    """Run one prompt through parse -> plan -> execute -> synthesize on the
    shared fastmcp client. Returns a short status label for the roll-up."""
    banner = "=" * 78
    print(f"\n{banner}\nPROMPT: {prompt}\n{banner}", flush=True)

    # Parse (synchronous). A refusal short-circuits the rest.
    result = parse_prompt(prompt, menu=menu)
    if result.is_refusal:
        r = result.refusal
        print(capability_message(r, menu))
        print(f"  (refusal: {r.flavor.value} — {r.detail})")
        return "refused (expected for out-of-scope)"

    intent = result.intent
    print(_format_intent(intent))
    print()

    # Plan.
    try:
        plan = generate_plan(intent)
    except Exception as exc:
        print(f"ERROR generating plan: {exc}", file=sys.stderr)
        return f"plan error: {exc}"
    print(_format_plan(plan))
    print()

    # Execute on the shared client.
    print("Executing plan against MCP server ...")

    async def _on_progress(progress, total, message=None):
        shown = message or ""
        if total:
            print(f"  … progress {progress}/{total} {shown}", flush=True)
        else:
            print(f"  … progress {shown}", flush=True)

    try:
        outputs, truncation_by_step = await execute_plan(
            plan, client, progress_handler=_on_progress
        )
    except Exception as exc:
        print(f"ERROR executing plan: {exc}", file=sys.stderr)
        return f"execute error: {exc}"
    print(_format_outputs(outputs))
    print()

    # Synthesize.
    print("Synthesizing answer via LLM ...")
    try:
        response = synthesize_response(
            outputs,
            target_entity=intent.target_entity,
            truncation_by_step=truncation_by_step,
        )
    except UnsupportedEntityError as exc:
        print(f"ERROR: no synthesizer schema — {exc}", file=sys.stderr)
        return f"synth error: {exc}"
    print(_format_synthesized(response))
    print()
    print(_format_summary(plan, outputs, response))
    return "ok"


async def _run_all(prompts: list[str]) -> int:
    menu = load_kg_menu()
    results: list[tuple[str, str, float]] = []

    # One connection for the whole set.
    async with Client(MCP_SERVER_URL) as client:
        for prompt in prompts:
            start = time.monotonic()
            label = await _run_one(prompt, menu, client)
            elapsed = time.monotonic() - start
            print(f"\n[{label} — {elapsed:.1f}s]", flush=True)
            results.append((prompt, label, elapsed))

    banner = "=" * 78
    print(f"\n{banner}\nRUN SUMMARY\n{banner}")
    for prompt, label, elapsed in results:
        print(f"  [{label}] ({elapsed:.1f}s) {prompt}")

    failures = [
        p for p, lab, _ in results
        if lab != "ok" and not lab.startswith("refused")
    ]
    print(f"\n{len(results) - len(failures)}/{len(results)} ran cleanly.")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a set of prompts through the live Spire pipeline."
    )
    parser.add_argument(
        "--prompts",
        nargs="+",
        help="Override the default prompt set with your own prompts.",
    )
    args = parser.parse_args()
    prompts = args.prompts if args.prompts else DEFAULT_PROMPTS

    print(f"Running {len(prompts)} prompt(s) through the live pipeline.")
    print("(Requires the MCP server up, the pod reachable, and Gemini.)")
    return asyncio.run(_run_all(prompts))


if __name__ == "__main__":
    raise SystemExit(main())
