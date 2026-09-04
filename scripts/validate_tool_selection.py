#!/usr/bin/env python3
"""
validate_tool_selection.py — Validate the full router + tool-selection path,
deterministically, without executing any tool.

This is the standing correctness check for the prompt-to-intent router
(docs/features/prompt_to_intent_framework.md §2.2 / §4). For each prompt it runs
the FULL router path and validates two boundaries:

    prompt
      -> route_and_parse         (classify -> scoped parse)   -> Intent
      -> generate_plan           (the planner's KG lookup)     -> selected tool

  1. MODULE — did the classifier route the prompt to the expected module?
  2. TOOL   — did the planner select the expected tool? (generate_plan's first
              step's tool_name) — WITHOUT executing it.

WHY generate_plan AND NOT a raw KG table lookup: generate_plan IS the planner's
real, deterministic tool-selection — including its entity guards (Invoice needs
a supplier ref, PurchaseOrder-filterless needs list_all, ReceivablesInvoice
needs by_id, ...) which a bare kg_entity_tool read would miss. It builds a Plan
(a list of Steps) but does NOT run it — the executor does that, separately. So
this validates "which tool WOULD be called" with no MCP call, no pod, no
results. This is the deterministic oracle the retired comparison-fidelity check
lacked (§7.1): the KG lookup does not flake.

CAVEAT — the parse feeding generate_plan can flake. generate_plan itself is
deterministic, but the Intent it receives comes from route_and_parse, whose
scoped parse can vary run-to-run near the token ceiling (§7.1). So a prompt may
validate on one run and not another because the UPSTREAM PARSE differed, not
because tool-selection did. Run this a few times; treat run-to-run variance on a
prompt as a parser-stability signal, not a tool-selection failure. The
"list open purchase orders" probe is deliberately included to surface this.

Usage:
    python scripts/validate_tool_selection.py 2>&1 | tee t.txt
    python scripts/validate_tool_selection.py --file <other_corpus.txt>

Corpus format (per line):
    MODULE=<module> ||| TOOL=<tool_name> ||| <prompt>
    MODULE=<module> ||| TOOL=refuse      ||| <prompt>

TOOL=refuse expects the planner to REFUSE this Intent (generate_plan raises).
TOOL=any    expects the planner to serve SOME tool (exploratory — the run
            reports which tool was selected; passes as long as it did not
            refuse).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from spire.nl_parser.router import (
    ClassificationError,
    classify_modules,
    route_and_parse,
)
from spire.nl_parser.result import RefusalError
from spire.nl_parser.vocabulary import load_kg_menu
from spire.planner.planner import generate_plan
from spire.config import reset_usage, usage_report


DEFAULT_FILE = (
    Path(__file__).parent / "prompts" / "scorer" / "tool_selection.txt"
)


# --- corpus parsing -------------------------------------------------------

def load_cases(path: Path):
    """Parse 'MODULE=x ||| TOOL=y ||| prompt' lines into (module, tool, prompt).

    Blank lines and lines starting with '#' are skipped. A malformed line
    (missing MODULE= or TOOL=) is reported and skipped, not silently dropped.
    """
    cases = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|||")]
        if len(parts) < 3:
            print(f"  [skip] line {lineno}: expected "
                  f"'MODULE=x ||| TOOL=y ||| prompt', got: {line!r}")
            continue
        mod_field, tool_field, prompt = parts[0], parts[1], "|||".join(parts[2:])
        if not mod_field.upper().startswith("MODULE="):
            print(f"  [skip] line {lineno}: first field is not MODULE=: {line!r}")
            continue
        if not tool_field.upper().startswith("TOOL="):
            print(f"  [skip] line {lineno}: second field is not TOOL=: {line!r}")
            continue
        module = mod_field[len("MODULE="):].strip()
        tool = tool_field[len("TOOL="):].strip()
        cases.append((module, tool, prompt))
    return cases


# --- the two-boundary check for one prompt --------------------------------

def _selected_tool(plan) -> str | None:
    """The tool the planner would call first (the target fetch). None if the
    plan is empty (should not happen for a serviceable Intent)."""
    if not plan:
        return None
    first = plan[0]
    return getattr(first, "tool_name", None)


def validate_one(prompt: str, exp_module: str, exp_tool: str, menu):
    """Run the router path + generate_plan for one prompt.

    Returns a dict describing what happened and whether each boundary matched:
        {
          "module_got": [...] | "<error>",
          "module_ok": bool,
          "tool_got": "<tool>" | "refuse:<flavor>" | "<error>",
          "tool_ok": bool,
        }
    """
    result = {
        "module_got": None, "module_ok": False,
        "tool_got": None, "tool_ok": False,
    }

    # --- Boundary 1: classification (module) ---
    # Call the classifier directly so we can report the module even if the
    # downstream parse or plan later refuses. route_and_parse below re-runs it
    # (two small classify calls); acceptable for a validation harness.
    #
    # exp_module may be comma-joined for genuinely cross-module prompts
    # ("payables,supplier"). Compare as SETS — the classifier's module ORDER is
    # not meaningful, so ["supplier","payables"] and ["payables","supplier"]
    # both satisfy an expectation of payables,supplier.
    expected_modules = {m.strip() for m in exp_module.split(",") if m.strip()}
    try:
        modules = classify_modules(prompt, menu_text=None)
        result["module_got"] = modules
        result["module_ok"] = (set(modules) == expected_modules)
    except ClassificationError as exc:
        result["module_got"] = f"<classify-error: {exc}>"
        result["module_ok"] = False
        # Can't route without a module; tool boundary is moot.
        result["tool_got"] = "<no-parse: classify failed>"
        return result

    # --- Boundary 2: parse -> generate_plan (tool selection) ---
    try:
        parse_result = route_and_parse(prompt, menu=menu)
    except Exception as exc:  # noqa: BLE001 - report, don't traceback
        result["tool_got"] = f"<route_and_parse error: "\
                             f"{type(exc).__name__}: {exc}>"
        return result

    # The parser itself may have refused (before the planner even runs).
    if parse_result.is_refusal:
        flavor = getattr(parse_result.refusal.flavor, "value",
                         parse_result.refusal.flavor)
        result["tool_got"] = f"refuse:{flavor} (parser)"
        result["tool_ok"] = (exp_tool == "refuse")
        return result

    # Run the planner's deterministic tool-selection (no execution).
    try:
        plan = generate_plan(parse_result.intent)
    except RefusalError as exc:
        flavor = getattr(exc.refusal.flavor, "value", exc.refusal.flavor) \
            if getattr(exc, "refusal", None) is not None else "refuse"
        result["tool_got"] = f"refuse:{flavor} (planner)"
        result["tool_ok"] = (exp_tool == "refuse")
        return result
    except NotImplementedError as exc:
        result["tool_got"] = f"refuse:not_implemented ({exc})"
        result["tool_ok"] = (exp_tool == "refuse")
        return result
    except Exception as exc:  # noqa: BLE001
        result["tool_got"] = f"<generate_plan error: "\
                             f"{type(exc).__name__}: {exc}>"
        return result

    tool = _selected_tool(plan)
    result["tool_got"] = tool
    # TOOL=any -> pass if the planner served ANY tool (didn't refuse). Used for
    # exploratory prompts (e.g. aggregations) where we want to LEARN which tool
    # is selected rather than assert a specific one.
    if exp_tool == "any":
        result["tool_ok"] = (tool is not None)
    else:
        result["tool_ok"] = (tool == exp_tool)
    return result


# --- main ------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Validate router classification + planner tool-selection "
                    "on a labeled corpus, without executing tools."
    )
    ap.add_argument("--file", type=Path, default=DEFAULT_FILE)
    args = ap.parse_args()

    cases = load_cases(args.file)
    print(f"Loaded {len(cases)} prompts from {args.file.name}.\n")

    menu = load_kg_menu()
    reset_usage()

    both_ok, module_only, tool_only, neither = 0, 0, 0, 0
    rows = []

    for module_exp, tool_exp, prompt in cases:
        r = validate_one(prompt, module_exp, tool_exp, menu)
        m_ok, t_ok = r["module_ok"], r["tool_ok"]
        if m_ok and t_ok:
            both_ok += 1
            mark = "OK"
        elif m_ok and not t_ok:
            tool_only += 1  # module right, tool wrong
            mark = "TOOL✗"
        elif t_ok and not m_ok:
            module_only += 1  # tool right, module wrong
            mark = "MOD✗"
        else:
            neither += 1
            mark = "BOTH✗"

        rows.append((mark, prompt, module_exp, tool_exp, r))
        print(f"[{mark:<5}] {prompt[:48]:<48} "
              f"mod={str(r['module_got']):<18} tool={r['tool_got']}")

    print(f"\n{'='*72}")
    print(f"RESULT: {both_ok}/{len(cases)} fully OK  "
          f"(module+tool both correct)")
    if tool_only or module_only or neither:
        print(f"        {tool_only} module-ok/tool-wrong, "
              f"{module_only} tool-ok/module-wrong, "
              f"{neither} both-wrong")
    print('='*72)

    # Detail on anything not fully OK.
    problems = [row for row in rows if row[0] != "OK"]
    if problems:
        print("\nMISMATCHES:\n")
        for mark, prompt, module_exp, tool_exp, r in problems:
            print(f"  [{mark}] {prompt}")
            print(f"      module: expected [{module_exp}]  got {r['module_got']}")
            print(f"      tool:   expected {tool_exp}  got {r['tool_got']}")
            print()

    print(usage_report())

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
