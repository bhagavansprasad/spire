#!/usr/bin/env python3
"""
Run the Design 3 pipeline via the LangGraph graph.

Prerequisites: MCP server up, pod reachable, Gemini configured.

Output contract (Phase 1, UX-05):

    stdout carries the answer.  stderr carries everything else.

Redirect stdout and you get the answer alone, with nothing to strip::

    python scripts/run_graph.py --prompt "..." 2>/dev/null

Diagnostics are off by default and switched on per component::

    python scripts/run_graph.py --prompt "..." --show-planner
    python scripts/run_graph.py --prompt "..." --show-all
    python scripts/run_graph.py --prompt "..." --show-all --no-show-raw-output

Two things are never gated, because a ~16 second run needs them:
progress lines while a tool pages through the pod, and the counts
footer at the end. Both go to stderr, so stdout is unaffected.

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
from spire.diagnostics import (
    add_diagnostic_arguments,
    answer,
    flags_from_args,
    get_logger,
    setup_diagnostics,
)
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


# One logger per component, matching the flag that controls it. Every
# one of these is silent unless its flag is set — except `progress` and
# `summary`, which are always on.
_parser_log = get_logger("parser")
_planner_log = get_logger("planner")
_executor_log = get_logger("executor")
_tokens_log = get_logger("tokens")
_progress_log = get_logger("progress")
_summary_log = get_logger("summary")


def _block(log, text: str) -> None:
    """Log a pre-formatted block, followed by a blank line.

    The formatters return aligned multi-line tables. The trailing
    newline reproduces the blank-line spacing the old unconditional
    prints had, without each caller having to remember it.
    """
    log.debug("%s\n", text)


async def _run(prompt: str) -> int:
    reset_usage()
    menu = load_kg_menu()

    async with Client(MCP_SERVER_URL) as client:

        async def _on_progress(progress, total, message=None):
            shown = message or ""
            if total:
                _progress_log.info("  … progress %s/%s %s", progress, total, shown)
            else:
                _progress_log.info("  … progress %s", shown)

        state = await GRAPH.ainvoke(
            {
                "prompt": prompt,
                "menu": menu,
                "session": client,
                "progress_handler": _on_progress,
            }
        )

    # Refusal short-circuit. The capability message IS the answer — it
    # names what Spire can do instead — so it goes to stdout. The
    # flavor/detail pair beside it is parser internals, not an answer.
    if state.get("refusal"):
        r = state["refusal"]
        answer(capability_message(r, menu))
        _parser_log.debug("  (refusal: %s — %s)", r.flavor.value, r.detail)
        _block(_tokens_log, usage_report())
        return 4

    # A planner REFUSAL is Spire declining, not Spire breaking: the
    # message names what is missing and gives an example to type.
    # Printing it as "ERROR:" on stderr made a good answer look like a
    # crash — and made this runner disagree with run_prompt_set.py
    # about the very same prompt. Exit 4, the same code as a parser
    # refusal, because it is the same kind of outcome. It is an answer,
    # so it belongs on stdout.
    if state.get("error") and state.get("plan_refusal"):
        answer(f"REFUSED (planner guard): {state['error']}")
        _block(_tokens_log, usage_report())
        return 4

    # A genuine failure produces no answer, so stdout stays empty.
    if state.get("error"):
        print(f"ERROR: {state['error']}", file=sys.stderr)
        return 2

    _block(_parser_log, _format_intent(state["intent"]))
    _block(_planner_log, _format_plan(state["plan"]))

    _outputs = state.get("outputs") or {}
    _display_outputs = state.get("projected_outputs") or _outputs
    _block(_executor_log, _format_outputs(_display_outputs))

    _fields = state["intent"].fields
    _synth_failed = state.get("synth_failed")

    if _fields:
        # Column query: summary on top (when it succeeded), table below.
        # SUMMARY ONLY — not the typed record block. The table below
        # prints the columns the user asked for; printing the records too
        # repeats every value, and on an address query that is ~200 lines
        # of "address: ..." followed by the same data in the table.
        # The table trims to the requested columns itself and flattens any
        # nested addresses, so it takes the RAW outputs (projected_outputs
        # has already stripped the addresses key).
        if _synth_failed:
            answer(
                "Answer summary: (skipped — result too large to summarize; "
                "showing the table only)"
            )
        else:
            answer(_format_synthesized(state.get("response"), summary_only=True))
        answer("")
        answer(_format_projected_table(_outputs, _fields))
    else:
        answer(_format_synthesized(state.get("response")))

    _summary_log.info(
        "%s", _format_summary(state["plan"], _outputs, state.get("response"))
    )
    _block(_tokens_log, usage_report())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Spire pipeline via the LangGraph graph.",
    )
    parser.add_argument("--prompt", required=True, help="Natural-language prompt.")
    add_diagnostic_arguments(parser)
    args = parser.parse_args()

    # Before anything else runs. Module-level get_logger() calls only
    # fetch logger objects; nothing can emit until the handler and
    # levels are in place here.
    setup_diagnostics(flags_from_args(args))

    return asyncio.run(_run(args.prompt))


if __name__ == "__main__":
    raise SystemExit(main())
