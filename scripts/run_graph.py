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

from run_plan import (  # reuse the existing formatters + URL
    MCP_SERVER_URL,
    _format_intent,
    _format_outputs,
    _format_plan,
    _format_summary,
    _format_synthesized,
)


def _format_projected_table(outputs: dict[str, list[dict]], fields: list[str]) -> str:
    """Print the final output bucket as a table of exactly the requested
    columns, in the order named.

    Used when the intent carries ``fields`` — an explicit column request.
    Reads the projected rows the executor already produced and prints those
    columns directly, rather than routing through the typed synthesizer
    response (whose fixed attributes cannot carry arbitrary requested
    columns). A missing key on a row prints as an em dash so an absent value
    is visibly distinct from an empty string.

    Address flattening (self-gating): when the rows carry a nested
    ``addresses`` list (from include_addresses=True), each supplier's first
    address is flattened to a one-line string under an ``Address`` column,
    and ``Address`` is appended to the printed columns. This fires only when
    address data is actually present, so it never misfires, needs no parser
    change, and keeps the whole address tree out of the synthesizer.
    """
    if not outputs:
        return "Answer:\nNo records found."

    bucket_name = list(outputs.keys())[-1]
    rows = outputs[bucket_name]

    # Self-gating address flatten: only if some row carries an addresses list.
    cols = list(fields)
    has_addresses = any(
        isinstance(r, dict) and r.get("addresses") for r in rows
    )
    if has_addresses:
        rows = [dict(r) if isinstance(r, dict) else r for r in rows]
        for r in rows:
            if not isinstance(r, dict):
                continue
            addrs = r.get("addresses") or []
            if addrs:
                a = addrs[0]
                r["Address"] = (
                    a.get("formatted_address")
                    or ", ".join(
                        str(a[k]) for k in ("city", "state", "country")
                        if a.get(k)
                    )
                    or None
                )
            else:
                r["Address"] = None
        if "Address" not in cols:
            cols.append("Address")

    lines = [
        "Answer:",
        f"\n{bucket_name} ({len(rows)} record(s)) — "
        f"columns: {', '.join(cols)}\n",
    ]

    if not rows:
        lines.append("  (no rows)")
        return "\n".join(lines)

    # Compute a width per column so the table aligns.
    widths = {}
    for f in cols:
        cell_lens = [
            len(str(r.get(f))) if isinstance(r, dict) and r.get(f) is not None else 1
            for r in rows
        ]
        widths[f] = max([len(f)] + cell_lens)

    header = "  " + " | ".join(f.ljust(widths[f]) for f in cols)
    rule = "  " + "-+-".join("-" * widths[f] for f in cols)
    lines.append(header)
    lines.append(rule)
    for r in rows:
        cells = []
        for f in cols:
            v = r.get(f) if isinstance(r, dict) else None
            cells.append(("—" if v is None else str(v)).ljust(widths[f]))
        lines.append("  " + " | ".join(cells))
    return "\n".join(lines)


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
