#!/usr/bin/env python3
"""
Run the Design 3 pipeline via the LangGraph graph (parallel to
scripts/run_plan.py, which runs the same pipeline imperatively).

Kept alongside run_plan.py during the transition so the two can be
compared on the same prompts. Same prerequisites: MCP server up, pod
reachable, Gemini configured.

Usage:
    python scripts/run_graph.py --prompt "Show me suppliers in US"
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from fastmcp import Client

from spire.graph.pipeline import GRAPH
from spire.config import reset_usage, usage_report
from spire.nl_parser.capability import capability_message
from spire.nl_parser.vocabulary import load_kg_menu

from display_formatters import (
    MCP_SERVER_URL,
    _format_intent,
    _format_outputs,
    _format_plan,
    _format_projected_table,
    _format_summary,
    _format_synthesized,
)

async def _run(prompt: str) -> int:
    reset_usage()
    menu = load_kg_menu()

    async with Client(MCP_SERVER_URL) as client:

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

    # Refusal short-circuit.
    if state.get("refusal"):
        r = state["refusal"]
        print(capability_message(r, menu))
        print(f"  (refusal: {r.flavor.value} — {r.detail})")
        print()
        print(usage_report())
        return 4

    # Error in any node.
    if state.get("error"):
        print(f"ERROR: {state['error']}", file=sys.stderr)
        return 2

    print(_format_intent(state["intent"]))
    print()
    print(_format_plan(state["plan"]))
    print()
    _outputs = state.get("outputs") or {}
    _display_outputs = state.get("projected_outputs") or _outputs
    print(_format_outputs(_display_outputs))
    print()
    _fields = state["intent"].fields
    _synth_failed = state.get("synth_failed")
    if _fields:
        # Column query: summary on top (when it succeeded), table below.
        # The table trims to the requested columns itself and flattens any
        # nested addresses, so it takes the RAW outputs (projected_outputs
        # has already stripped the addresses key).
        if _synth_failed:
            print(
                "Answer summary: (skipped — result too large to summarize; "
                "showing the table only)"
            )
        else:
            print(_format_synthesized(state.get("response")))
        print()
        print(_format_projected_table(_outputs, _fields))
    else:
        print(_format_synthesized(state.get("response")))
    print()
    print(_format_summary(state["plan"], _outputs, state.get("response")))
    print()
    print(usage_report())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Spire pipeline via the LangGraph graph."
    )
    parser.add_argument("--prompt", required=True, help="Natural-language prompt.")
    args = parser.parse_args()
    return asyncio.run(_run(args.prompt))


if __name__ == "__main__":
    raise SystemExit(main())
