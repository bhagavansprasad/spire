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

from spire.graph.pipeline import GRAPH
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
    # — supplier filters (Phase 3) —
    "Get list of active suppliers",
    "Suppliers named Lee",
    "active US suppliers",
    "Suppliers created between Jan and Mar 2025",
    # — refusal (out of scope) —
    "Show me contract renewals due next quarter",
]


async def _run_one(prompt: str, menu, client) -> str:
    """Run one prompt through the LangGraph pipeline on the shared fastmcp
    client. Returns a short status label for the roll-up."""
    banner = "=" * 78
    print(f"\n{banner}\nPROMPT: {prompt}\n{banner}", flush=True)

    async def _on_progress(progress, total, message=None):
        shown = message or ""
        if total:
            print(f"  … progress {progress}/{total} {shown}", flush=True)
        else:
            print(f"  … progress {shown}", flush=True)

    state = await GRAPH.ainvoke(
        {
            "prompt": prompt,
            "menu": menu,
            "session": client,
            "progress_handler": _on_progress,
        }
    )

    if state.get("refusal"):
        r = state["refusal"]
        print(capability_message(r, menu))
        print(f"  (refusal: {r.flavor.value} — {r.detail})")
        return "refused (expected for out-of-scope)"

    if state.get("error"):
        print(f"ERROR: {state['error']}", file=sys.stderr)
        return f"error: {state['error']}"

    print(_format_intent(state["intent"]))
    print()
    print(_format_plan(state["plan"]))
    print()
    print(_format_outputs(state["outputs"]))
    print()
    print(_format_synthesized(state["response"]))
    print()
    print(_format_summary(state["plan"], state["outputs"], state["response"]))
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
