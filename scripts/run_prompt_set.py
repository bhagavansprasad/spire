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
  python scripts/run_prompt_set.py                 # all modules
  python scripts/run_prompt_set.py --all           # all modules (explicit)
  python scripts/run_prompt_set.py --prompt-file scripts/prompt_set_po.txt
  python scripts/run_prompt_set.py --prompts "List US suppliers" "Show PO 2144 and its lines"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

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


# Prompts live in per-module files alongside this script
# (prompt_set_<module>.txt): one prompt per line, blank lines and '#'
# comment lines ignored, slow prompts ordered last within each file.
# With no args, every module file is run (equivalent to --all).


def load_prompts(path: Path) -> list[str]:
    """Read prompts from a text file: one per line, skipping blank lines
    and '#' comment lines."""
    prompts: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        prompts.append(line)
    return prompts


def load_all_module_prompts(scripts_dir: Path) -> list[str]:
    """Load and concatenate every per-module prompt file
    (prompt_set_*.txt) in scripts_dir, sorted by filename for stable
    order. Fast/slow ordering is preserved WITHIN each module file; the
    files themselves run in alphabetical order (po before supplier, etc.).
    """
    module_files = sorted(scripts_dir.glob("prompt_set_*.txt"))
    if not module_files:
        raise SystemExit(
            f"No prompt_set_*.txt files found in {scripts_dir}."
        )
    prompts: list[str] = []
    for path in module_files:
        prompts.extend(load_prompts(path))
    return prompts


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
        err = str(state["error"])
        # A planner guard rejecting an under-specified query is a REFUSAL,
        # not a failure: "Invoice queries require a supplier or a purchase
        # order", "Purchase-order queries require a PO id", "Address
        # queries require a supplier or a country". These are the system
        # correctly declining, so the prompt set should count them as
        # expected — same as a parser refusal.
        if err.startswith("plan: ") and "require" in err:
            print(f"REFUSED (planner guard): {err}")
            return "refused (expected — planner guard)"
        print(f"ERROR: {err}", file=sys.stderr)
        return f"error: {err}"

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
        help="Override the prompt set with your own prompts (inline).",
    )
    parser.add_argument(
        "--prompt-file",
        type=Path,
        default=None,
        help=(
            "Run a single prompt file instead of all modules. With no "
            "flags, every prompt_set_*.txt module file is run."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "Run every per-module prompt file (prompt_set_*.txt) in the "
            "scripts dir, concatenated. Mutually exclusive with "
            "--prompt-file."
        ),
    )
    args = parser.parse_args()

    if args.all and args.prompt_file is not None:
        parser.error("--all and --prompt-file are mutually exclusive.")

    scripts_dir = Path(__file__).parent
    if args.prompts:
        prompts = args.prompts
    elif args.all:
        prompts = load_all_module_prompts(scripts_dir)
    elif args.prompt_file is not None:
        prompts = load_prompts(args.prompt_file)
    else:
        # No flags: run every module file.
        prompts = load_all_module_prompts(scripts_dir)

    print(f"Running {len(prompts)} prompt(s) through the live pipeline.")
    print("(Requires the MCP server up, the pod reachable, and Gemini.)")
    return asyncio.run(_run_all(prompts))


if __name__ == "__main__":
    raise SystemExit(main())