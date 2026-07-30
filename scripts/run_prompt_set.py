#!/usr/bin/env python3
"""
Run one or more sets of prompts through the live Spire pipeline, in-process.

No subprocesses. The harness imports the same pipeline pieces run_plan.py
uses (parser, planner, executor, synthesizer) and runs each prompt
sequentially in a single loop, reusing run_plan's own formatters so the
output matches a manual run. The MCP session is opened ONCE and shared
across every prompt in every set.

--prompt-file takes SEVERAL paths, so a whole batch runs under one MCP
connection and produces one grouped summary:

    python scripts/run_prompt_set.py --prompt-file scripts/prompts/0*.txt

This replaces the bash for-loop that used to wrap the script. The loop
worked, but it opened a fresh connection per set and produced seven
disconnected summaries with no indication of which set a failure came
from.

CRASH ISOLATION. Each prompt runs inside a try/except so one failure
cannot abort the set. This was not always so: on 2026-07-24 an
AttributeError in the DISPLAY layer — run_plan._format_synthesized
reading a schema field that did not exist — killed the process after the
FIRST prompt of the AR set, and the remaining 15 never ran. The pipeline
itself had worked. A harness that loses a module's coverage to a
formatter typo is worse than no harness, because the run looks like it
happened.

Prerequisites (same as a manual run_plan.py run):
  - MCP server running (python -m spire.mcp_server.server)
  - Fusion pod reachable; personas.yaml present
  - GEMINI_API_KEY set; KG reachable

Usage:
  python scripts/run_prompt_set.py --prompt-file scripts/prompts/03_ar.txt
  python scripts/run_prompt_set.py --prompt-file scripts/prompts/0*.txt
  python scripts/run_prompt_set.py --prompt-file a.txt b.txt c.txt
  python scripts/run_prompt_set.py --prompts "List US suppliers" "Show PO 2144 and its lines"
  python scripts/run_prompt_set.py --all      # every prompt_set_*.txt in scripts/
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import traceback
from pathlib import Path

from fastmcp import Client

from spire.diagnostics import setup_diagnostics
from spire.graph.pipeline import GRAPH
from spire.nl_parser.vocabulary import load_kg_menu
from spire.nl_parser.capability import capability_message

# Formatters live in display_formatters (run_plan.py is deprecated).
from display_formatters import (
    MCP_SERVER_URL,
    _format_intent,
    _format_outputs,
    _format_plan,
    _format_projected_table,
    _format_summary,
    _format_synthesized,
)


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


def load_all_module_prompts(scripts_dir: Path) -> list[tuple[str, list[str]]]:
    """Load every legacy per-module prompt file (prompt_set_*.txt) in
    scripts_dir, sorted by filename for stable order.

    Returns (set_name, prompts) pairs so the roll-up can group by set.
    Fast/slow ordering is preserved WITHIN each file.
    """
    module_files = sorted(scripts_dir.glob("prompt_set_*.txt"))
    if not module_files:
        raise SystemExit(
            f"No prompt_set_*.txt files found in {scripts_dir}."
        )
    return [(p.stem, load_prompts(p)) for p in module_files]


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
        # A planner guard rejecting an under-specified or unsupported
        # query is a REFUSAL, not a failure: the system correctly
        # declining, and the message names what is missing plus an
        # example to type. Counted as expected, like a parser refusal.
        #
        # This used to match the message text — `"require" in err` —
        # which tied the tally to wording nobody thought of as an
        # interface. It broke exactly that way: a planner message
        # reworded to name the supported filters ("Spire can't filter
        # CustomerAccount by 'account_number' ...") stopped matching,
        # and a good refusal was reported as a crash. plan_node now
        # sets plan_refusal from the exception type instead.
        if state.get("plan_refusal"):
            print(f"REFUSED (planner guard): {err}")
            return "refused (expected — planner guard)"
        print(f"ERROR: {err}", file=sys.stderr)
        return f"error: {err}"

    _outputs = state.get("outputs") or {}
    print(_format_intent(state["intent"]))
    print()
    print(_format_plan(state["plan"]))
    print()
    print(_format_outputs(_outputs))
    print()
    _fields = state["intent"].fields
    _synth_failed = state.get("synth_failed")
    if _fields:
        # Column query: summary on top (when it succeeded), table below.
        # SUMMARY ONLY — not the typed record block. The table below
        # prints the columns the user asked for; printing the records
        # too repeats every value, and on an address query that is ~200
        # lines of "address: ..." followed by the same data in the
        # table.
        # The table reads RAW outputs (it trims to the requested columns
        # itself and flattens nested addresses).
        if _synth_failed:
            print(
                "Answer summary: (skipped — result too large to summarize; "
                "showing the table only)"
            )
        else:
            print(_format_synthesized(state.get("response"), summary_only=True))
        print()
        print(_format_projected_table(_outputs, _fields))
    else:
        print(_format_synthesized(state.get("response")))
    print()
    print(_format_summary(state["plan"], _outputs, state.get("response")))
    return "ok"


async def _run_all(sets: list[tuple[str, list[str]]]) -> int:
    """Run every prompt in every set under ONE MCP connection.

    `sets` is a list of (set_name, prompts) pairs. Results are grouped by
    set in the roll-up: with a hundred-odd prompts across seven files, a
    flat summary makes it needlessly hard to see which module a failure
    belongs to.
    """
    menu = load_kg_menu()
    # (set_name, prompt, label, elapsed)
    results: list[tuple[str, str, str, float]] = []

    total_prompts = sum(len(p) for _, p in sets)
    print(f"Running {total_prompts} prompt(s) across {len(sets)} set(s).")
    print("(Requires the MCP server up, the pod reachable, and Gemini.)")

    # One connection for the whole batch.
    async with Client(MCP_SERVER_URL) as client:
        for set_name, prompts in sets:
            header = "#" * 78
            print(
                f"\n{header}\n########## {set_name}  ({len(prompts)} prompts)\n{header}",
                flush=True,
            )
            for prompt in prompts:
                start = time.monotonic()
                try:
                    label = await _run_one(prompt, menu, client)
                except Exception as exc:
                    # A crash in ONE prompt must not abort the set. See the
                    # CRASH ISOLATION note in the module docstring: an
                    # AttributeError in the display layer once cost 15 AR
                    # prompts that had never been observed running.
                    #
                    # The traceback goes to stderr so it lands in the log
                    # next to the prompt that caused it, and the label
                    # carries the exception into the RUN SUMMARY so a crash
                    # is visible in the roll-up, not only in the body.
                    print(
                        f"CRASH: {type(exc).__name__}: {exc}",
                        file=sys.stderr,
                        flush=True,
                    )
                    traceback.print_exc(file=sys.stderr)
                    label = f"crash: {type(exc).__name__}: {exc}"
                elapsed = time.monotonic() - start
                print(f"\n[{label} — {elapsed:.1f}s]", flush=True)
                results.append((set_name, prompt, label, elapsed))

    banner = "=" * 78
    print(f"\n{banner}\nRUN SUMMARY\n{banner}")

    def _is_failure(label: str) -> bool:
        # A crash counts as a failure: its label starts with "crash:",
        # which is neither "ok" nor a "refused" prefix.
        return label != "ok" and not label.startswith("refused")

    all_failures: list[tuple[str, str]] = []
    for set_name, _ in sets:
        rows = [r for r in results if r[0] == set_name]
        if not rows:
            continue
        fails = [r for r in rows if _is_failure(r[2])]
        elapsed_total = sum(r[3] for r in rows)
        print(
            f"\n--- {set_name}: {len(rows) - len(fails)}/{len(rows)} clean, "
            f"{elapsed_total:.0f}s ---"
        )
        for _, prompt, label, elapsed in rows:
            print(f"  [{label}] ({elapsed:.1f}s) {prompt}")
        all_failures.extend((set_name, r[1]) for r in fails)

    print(f"\n{banner}")
    clean = len(results) - len(all_failures)
    print(f"TOTAL: {clean}/{len(results)} ran cleanly.")
    if all_failures:
        print(f"{len(all_failures)} did not:")
        for set_name, prompt in all_failures:
            print(f"  [{set_name}] {prompt}")

    # The tally is NOT a verdict. A prompt can run cleanly and still give a
    # wrong answer — a page size stated as a total, a claim about a field
    # absent from the output, an empty child array behind confident prose.
    # Read the answers.
    print("\nNOTE: 'ran cleanly' means it did not error. It does NOT mean")
    print("the answer is correct. Read the answers, not this tally.")
    return 1 if all_failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one or more prompt sets through the live Spire pipeline."
    )
    parser.add_argument(
        "--prompts",
        nargs="+",
        help="Override the prompt set with your own prompts (inline).",
    )
    parser.add_argument(
        "--prompt-file",
        type=Path,
        nargs="+",
        default=None,
        metavar="FILE",
        help=(
            "One or more prompt files to run, in the order given. Shell "
            "globs work: scripts/prompts/0*.txt"
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "Run every legacy per-module prompt file (prompt_set_*.txt) in "
            "the scripts dir. Mutually exclusive with --prompt-file."
        ),
    )
    args = parser.parse_args()

    # This harness is deliberately NOT quieted by UX-05 — its output is
    # its whole purpose, and its own prints are untouched. The call is
    # here for one reason: without it nothing installs a handler on the
    # `spire.*` loggers, so the always-on progress lines would vanish
    # and a slow 31-prompt run would look like a hang.
    #
    # No flags: progress and summary come through, per-component
    # diagnostics stay off. The per-call `[llm] stage=...` token echo
    # that used to appear here is gone by design; the end-of-run totals
    # are unaffected.
    setup_diagnostics()

    if args.all and args.prompt_file is not None:
        parser.error("--all and --prompt-file are mutually exclusive.")

    scripts_dir = Path(__file__).parent

    if args.prompts:
        sets = [("inline", args.prompts)]
    elif args.prompt_file:
        missing = [p for p in args.prompt_file if not p.is_file()]
        if missing:
            parser.error(
                "prompt file(s) not found: " + ", ".join(str(p) for p in missing)
            )
        sets = [(p.stem, load_prompts(p)) for p in args.prompt_file]
        empty = [name for name, prompts in sets if not prompts]
        if empty:
            print(
                f"WARNING: no prompts found in {', '.join(empty)} "
                "(all lines blank or commented?)",
                file=sys.stderr,
            )
    elif args.all:
        sets = load_all_module_prompts(scripts_dir)
    else:
        parser.error(
            "nothing to run: pass --prompt-file FILE [FILE ...], --prompts, or --all."
        )

    return asyncio.run(_run_all(sets))


if __name__ == "__main__":
    raise SystemExit(main())

