#!/usr/bin/env python3
"""
promptkit.py — one tool for Spire prompt sets. JSON is the single format.

Pick ONE action:

    --generate <file.txt> ...    Run each plain prompt file through the router
                                 and write a .json next to it (each entry:
                                 prompt, module, tool, note). The labels are the
                                 router's ACTUAL choices — review, then trust.

    --validate <file.json> ...   Check each JSON: does every prompt still route
                                 to its recorded module + tool? A mismatch is a
                                 regression. NO execution — fast.

    --run <file.json> ...        Execute each prompt end to end against Fusion
                                 AND re-check routing against the corpus,
                                 reporting WHICH STAGE fails (module / intent /
                                 tool / plan / execute). Needs the MCP server up.

    --run --prompt "..."         Run ONE ad-hoc prompt end to end (no corpus).
                                 Replaces run_graph.py for single prompts.

Diagnostics (with --run) reuse the same system as run_graph.py: the committed
defaults in pyproject.toml ([tool.spire.diagnostics]) apply, and --show-parser
/ --show-planner / --show-raw-output / --show-synthesizer / --show-tokens /
--show-timings / --show-all override per run. So end-to-end output matches
run_graph.py exactly.

Examples:
    python scripts/promptkit.py --generate scripts/prompts/01_supplier.txt
    python scripts/promptkit.py --validate scripts/prompts/*.json
    python scripts/promptkit.py --run scripts/prompts/01_supplier.json
    python scripts/promptkit.py --run --prompt "show suppliers in US" --show-all
"""

from __future__ import annotations

import argparse
import asyncio
import json
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


# ==========================================================================
# Corpus I/O
# ==========================================================================

def load_cases(path: Path):
    """Load a JSON corpus: list of {prompt, module: [...], tool, note}.
    Returns (module_str, tool, prompt) triples (module_str is comma-joined)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = []
    for e in data:
        module = e.get("module") or []
        mod = ",".join(module) if isinstance(module, list) else str(module)
        cases.append((mod, e.get("tool", ""), e.get("prompt", "")))
    return cases


def load_plain_prompts(path: Path) -> list[str]:
    """Read a plain prompt file (one prompt per line; '#'/blank skipped)."""
    prompts = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        prompts.append(line)
    return prompts


# ==========================================================================
# Shared stage checks (module -> intent -> tool/plan), NO execution.
# ==========================================================================

def _selected_tool(plan) -> str | None:
    if not plan:
        return None
    return getattr(plan[0], "tool_name", None)


def validate_one(prompt: str, exp_module: str, exp_tool: str, menu):
    """--validate's per-prompt check: classify -> route_and_parse ->
    generate_plan, comparing module and tool to the corpus. No execution."""
    result = {"module_got": None, "module_ok": False,
              "tool_got": None, "tool_ok": False}
    expected_modules = {m.strip() for m in exp_module.split(",") if m.strip()}

    try:
        modules = classify_modules(prompt, menu_text=None)
        result["module_got"] = modules
        result["module_ok"] = (set(modules) == expected_modules)
    except ClassificationError as exc:
        result["module_got"] = f"<classify-error: {exc}>"
        result["tool_got"] = "<no-parse: classify failed>"
        return result

    try:
        parse_result = route_and_parse(prompt, menu=menu)
    except Exception as exc:  # noqa: BLE001
        result["tool_got"] = f"<route_and_parse error: {type(exc).__name__}: {exc}>"
        return result

    if parse_result.is_refusal:
        flavor = getattr(parse_result.refusal.flavor, "value",
                         parse_result.refusal.flavor)
        result["tool_got"] = f"refuse:{flavor} (parser)"
        result["tool_ok"] = (exp_tool == "refuse")
        return result

    try:
        plan = generate_plan(parse_result.intent)
    except RefusalError as exc:
        flavor = (getattr(exc.refusal.flavor, "value", exc.refusal.flavor)
                  if getattr(exc, "refusal", None) is not None else "refuse")
        result["tool_got"] = f"refuse:{flavor} (planner)"
        result["tool_ok"] = (exp_tool == "refuse")
        return result
    except NotImplementedError as exc:
        result["tool_got"] = f"refuse:not_implemented ({exc})"
        result["tool_ok"] = (exp_tool == "refuse")
        return result
    except Exception as exc:  # noqa: BLE001
        result["tool_got"] = f"<generate_plan error: {type(exc).__name__}: {exc}>"
        return result

    tool = _selected_tool(plan)
    result["tool_got"] = tool
    if exp_tool == "any":
        result["tool_ok"] = (tool is not None)
    else:
        result["tool_ok"] = (tool == exp_tool)
    return result


# ==========================================================================
# --generate : plain prompts -> JSON of the router's choices
# ==========================================================================

def _note_marker(module_got, tool_got) -> str:
    if isinstance(module_got, str) and "error" in module_got:
        return "ERR"
    if isinstance(tool_got, str) and tool_got.startswith("refuse"):
        return "REF"
    if isinstance(tool_got, str) and tool_got.startswith("<"):
        return "ERR"
    if isinstance(module_got, list) and len(module_got) > 1:
        return "MUL"
    return "ok"


def _corpus_entry(module_got, tool_got, prompt) -> dict:
    """One JSON entry: prompt, module (list), tool (name|refuse|error), note
    (always present; empty on success)."""
    module = list(module_got) if isinstance(module_got, list) else []
    entry: dict = {"prompt": prompt, "module": module}
    if isinstance(tool_got, str) and tool_got.startswith("refuse"):
        entry["tool"], entry["note"] = "refuse", tool_got
    elif isinstance(tool_got, str) and tool_got.startswith("<"):
        entry["tool"], entry["note"] = "error", tool_got
    elif isinstance(module_got, str) and "error" in module_got:
        entry["tool"], entry["note"] = "error", module_got
    else:
        entry["tool"], entry["note"] = tool_got, ""
    return entry


def generate_file(txt_path: Path, menu) -> int:
    out = txt_path.with_suffix(".json")
    prompts = load_plain_prompts(txt_path)
    print(f"\n### generate {txt_path}  ->  {out}   ({len(prompts)} prompts)")
    entries = []
    for prompt in prompts:
        r = validate_one(prompt, "", "", menu)  # dummy expectations; read got
        m, t = r["module_got"], r["tool_got"]
        entries.append(_corpus_entry(m, t, prompt))
        print(f"  [{_note_marker(m, t):<3}] {prompt[:52]:<52} "
              f"mod={m} tool={t}")
    out.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"  wrote {len(entries)} entries to {out}")
    return 0


def do_generate(files: list[Path]) -> int:
    menu = load_kg_menu()
    rc = 0
    for f in files:
        if not f.is_file():
            print(f"  [skip] not found: {f}")
            rc = 1
            continue
        generate_file(f, menu)
    return rc


# ==========================================================================
# --validate : check each JSON's routing (no execution)
# ==========================================================================

def validate_file(path: Path, menu) -> tuple[int, int]:
    cases = load_cases(path)
    print(f"\n### validate {path.name} — {len(cases)} prompts")
    both_ok = 0
    rows = []
    for module_exp, tool_exp, prompt in cases:
        r = validate_one(prompt, module_exp, tool_exp, menu)
        m_ok, t_ok = r["module_ok"], r["tool_ok"]
        mark = ("OK" if m_ok and t_ok else
                "TOOL\u2717" if m_ok else "MOD\u2717" if t_ok else "BOTH\u2717")
        if m_ok and t_ok:
            both_ok += 1
        rows.append((mark, prompt, module_exp, tool_exp, r))
        print(f"[{mark:<5}] {prompt[:48]:<48} "
              f"mod={str(r['module_got']):<18} tool={r['tool_got']}")
    problems = [row for row in rows if row[0] != "OK"]
    print(f"  {both_ok}/{len(cases)} OK" +
          (f"  ({len(problems)} mismatch)" if problems else ""))
    for mark, prompt, module_exp, tool_exp, r in problems:
        print(f"    [{mark}] {prompt}")
        print(f"        module: expected [{module_exp}]  got {r['module_got']}")
        print(f"        tool:   expected {tool_exp}  got {r['tool_got']}")
    return both_ok, len(cases)


def do_validate(files: list[Path]) -> int:
    menu = load_kg_menu()
    reset_usage()
    total_ok = total_all = 0
    for f in files:
        if not f.is_file():
            print(f"  [skip] not found: {f}")
            continue
        ok, n = validate_file(f, menu)
        total_ok += ok
        total_all += n
    print(f"\n{'='*72}")
    print(f"TOTAL: {total_ok}/{total_all} OK across {len(files)} file(s)")
    print('='*72)
    print(usage_report())
    return 0 if total_ok == total_all else 1


# ==========================================================================
# --run : end to end against Fusion + staged corpus check.
# ==========================================================================

def _stage_report(prompt, exp_module, exp_tool, state: dict) -> dict:
    """Read the graph STATE back and check each stage vs the corpus. Reports
    which stage FAILED (module/intent/tool/plan/execute) and any DIVERGENCE."""
    exp_modules = {m.strip() for m in exp_module.split(",") if m.strip()}
    rpt: dict = {"prompt": prompt, "stages": {}, "failed_at": None,
                 "diverged": [], "result": ("PASS", "")}

    def mark(stage, status, detail=""):
        rpt["stages"][stage] = (status, detail)

    modules_got = state.get("_modules_got")
    if isinstance(modules_got, str):
        mark("module", "FAIL", modules_got)
        rpt["failed_at"] = "module"
        rpt["result"] = ("FAIL", "classify error")
        return rpt
    if set(modules_got or []) == exp_modules:
        mark("module", "OK", str(modules_got))
    else:
        mark("module", "DIVERGE",
             f"expected {sorted(exp_modules)}, got {modules_got}")
        rpt["diverged"].append("module")

    if state.get("refusal") is not None:
        flavor = getattr(state["refusal"].flavor, "value", state["refusal"].flavor)
        if exp_tool == "refuse":
            mark("intent", "OK", f"refused as expected ({flavor})")
            rpt["result"] = ("PASS", f"refused ({flavor})")
            return rpt
        mark("intent", "FAIL", f"refused ({flavor}); corpus expected {exp_tool}")
        rpt["failed_at"] = "intent (refused)"
        rpt["result"] = ("FAIL", f"refused ({flavor})")
        return rpt
    if state.get("intent") is None:
        mark("intent", "FAIL", "no intent produced")
        rpt["failed_at"] = "intent"
        rpt["result"] = ("FAIL", "no intent")
        return rpt
    mark("intent", "OK", getattr(state["intent"], "target_entity", "?"))

    if state.get("error") and state.get("plan_refusal"):
        if exp_tool == "refuse":
            mark("plan", "OK", "planner refused as expected")
            rpt["result"] = ("PASS", "refused (planner)")
            return rpt
        mark("plan", "FAIL", f"planner refused: {state['error']}")
        rpt["failed_at"] = "planning (refused)"
        rpt["result"] = ("FAIL", "planner refused")
        return rpt
    if state.get("error") and state.get("plan") is None:
        mark("plan", "FAIL", f"planning error: {state['error']}")
        rpt["failed_at"] = "planning"
        rpt["result"] = ("FAIL", "planning error")
        return rpt
    plan = state.get("plan")
    if not plan:
        mark("plan", "FAIL", "no plan produced")
        rpt["failed_at"] = "planning"
        rpt["result"] = ("FAIL", "no plan")
        return rpt
    tool_got = getattr(plan[0], "tool_name", None)
    if tool_got == exp_tool:
        mark("tool", "OK", tool_got)
    else:
        mark("tool", "DIVERGE", f"expected {exp_tool}, got {tool_got}")
        rpt["diverged"].append("tool")
    mark("plan", "OK", f"{len(plan)} step(s)")

    if state.get("error"):
        mark("execute", "FAIL", f"execution error: {state['error']}")
        rpt["failed_at"] = "execution (Fusion)"
        rpt["result"] = ("FAIL", "execution error")
        return rpt
    outputs = state.get("outputs") or {}
    total = sum(len(v) for v in outputs.values() if isinstance(v, list))
    mark("execute", "OK", f"{total} record(s)")
    rpt["result"] = ("PASS", f"{total} record(s)")
    return rpt


def _emit_run_graph_output(state, menu):
    """Emit the end-to-end answer + gated diagnostics exactly as run_graph.py,
    using the same loggers/answer(). Honors pyproject.toml + --show-*."""
    from spire.diagnostics import answer, get_logger
    from spire.nl_parser.capability import capability_message
    from display_formatters import (
        _format_intent, _format_outputs, _format_plan,
        _format_projected_table, _format_summary, _format_synthesized,
    )

    _parser_log = get_logger("parser")
    _planner_log = get_logger("planner")
    _executor_log = get_logger("executor")
    _tokens_log = get_logger("tokens")
    _summary_log = get_logger("summary")

    def _block(log, text):
        log.debug("%s\n", text)

    if state.get("refusal"):
        r = state["refusal"]
        answer(capability_message(r, menu))
        _parser_log.debug("  (refusal: %s — %s)", r.flavor.value, r.detail)
        _block(_tokens_log, usage_report())
        return
    if state.get("error") and state.get("plan_refusal"):
        answer(f"REFUSED (planner guard): {state['error']}")
        _block(_tokens_log, usage_report())
        return
    if state.get("error"):
        print(f"ERROR: {state['error']}", file=sys.stderr)
        return

    _block(_parser_log, _format_intent(state["intent"]))
    _block(_planner_log, _format_plan(state["plan"]))
    _outputs = state.get("outputs") or {}
    _display = state.get("projected_outputs") or _outputs
    _block(_executor_log, _format_outputs(_display))

    _fields = state["intent"].fields
    _unresolved = state["intent"].unresolved_fields
    _synth_failed = state.get("synth_failed")
    if _fields or _unresolved:
        _entity = state["intent"].target_entity
        _available = menu.available_columns(_entity)
        if not _fields:
            pass
        elif _synth_failed:
            answer("Answer summary: (skipped — too large to summarize)")
            answer("")
        else:
            answer(_format_synthesized(state.get("response"), summary_only=True))
            answer("")
        answer(_format_projected_table(_outputs, _fields, _unresolved,
                                       _available, _entity))
    else:
        answer(_format_synthesized(state.get("response")))

    _summary_log.info("%s", _format_summary(state["plan"], _outputs,
                                            state.get("response")))
    _block(_tokens_log, usage_report())


async def _run_one(prompt, exp_module, exp_tool, menu, client):
    """Run one prompt through the graph; return (state, stage_report)."""
    from spire.graph.pipeline import GRAPH
    try:
        modules_got = classify_modules(prompt, menu_text=None)
    except ClassificationError as exc:
        modules_got = f"<classify-error: {exc}>"
    try:
        state = await GRAPH.ainvoke({
            "prompt": prompt, "menu": menu, "session": client,
            "progress_handler": None, "cache_mode": None, "cache_slot": None,
        })
    except Exception as exc:  # noqa: BLE001
        state = {"error": f"pipeline crash: {type(exc).__name__}: {exc}"}
    state["_modules_got"] = modules_got
    rpt = _stage_report(prompt, exp_module, exp_tool, state)
    return state, rpt


def _print_stage_breakdown(rpt):
    """Print the per-stage OK/FAIL/DIVERGE breakdown for one prompt."""
    for stage in ("module", "intent", "tool", "plan", "execute"):
        if stage in rpt["stages"]:
            status, detail = rpt["stages"][stage]
            d = f"  ({detail})" if detail else ""
            print(f"    {stage:<8} {status:<8}{d}")
    verdict = ("FAILED AT: " + rpt["failed_at"]) if rpt["failed_at"] else "PASS"
    print(f"    -> {verdict}")


async def _run_async(files, single_prompt, show_stages) -> int:
    from fastmcp import Client
    from display_formatters import MCP_SERVER_URL

    menu = load_kg_menu()

    if single_prompt is not None:
        work = [("", "", single_prompt, None)]
    else:
        work = []
        for f in files:
            if not f.is_file():
                print(f"  [skip] not found: {f}")
                continue
            for mod, tool, prompt in load_cases(f):
                work.append((mod, tool, prompt, f.name))

    passed = failed = 0
    failures = []

    async with Client(MCP_SERVER_URL) as client:
        current_file = object()
        for exp_module, exp_tool, prompt, fname in work:
            # Reset the token accumulator per prompt so each prompt's
            # usage_report() (printed inside _emit_run_graph_output)
            # reflects only that prompt. Previously reset_usage() ran once
            # before the loop, so _USAGE_LOG accumulated across every
            # prompt and each block printed the running total — the last
            # prompt appeared to cost the whole run. The single-prompt path
            # runs this loop once, so it still gets exactly one reset before
            # its one prompt.
            reset_usage()
            if fname != current_file:
                current_file = fname
                if fname:
                    print(f"\n### run {fname} (end to end)\n")

            state, rpt = await _run_one(prompt, exp_module, exp_tool,
                                        menu, client)

            if single_prompt is not None:
                _emit_run_graph_output(state, menu)
                return 0 if not rpt["failed_at"] else 1

            # Per-prompt, interleaved, exactly like run_graph: a header, the
            # full output (intent/plan/answer, gated by the diagnostics flags),
            # then the staged corpus verdict. No accumulation.
            div = (f"  DIVERGED: {','.join(rpt['diverged'])}"
                   if rpt["diverged"] else "")
            status, tail = rpt["result"]
            print(f"\n{'-'*72}")
            print(f"PROMPT: {prompt}")
            print('-'*72)

            _emit_run_graph_output(state, menu)

            # The staged corpus check (what a plain run_graph does NOT do).
            if rpt["failed_at"]:
                failed += 1
                failures.append(rpt)
            else:
                passed += 1
            print()
            _print_stage_breakdown(rpt)
            verdict = ("FAIL" if rpt["failed_at"] else "PASS")
            print(f"  => {verdict}: {tail}{div}")

    print(f"\n{'='*72}")
    print(f"RUN: {passed} passed, {failed} failed")
    print('='*72)
    if failures:
        print("\nFAILURES — where each broke:\n")
        for rpt in failures:
            print(f"  {rpt['prompt']}")
            _print_stage_breakdown(rpt)
            print()
    return 0 if failed == 0 else 1


def do_run(files, single_prompt, show_stages) -> int:
    return asyncio.run(_run_async(files, single_prompt, show_stages))


# ==========================================================================
# CLI
# ==========================================================================

def main() -> int:
    ap = argparse.ArgumentParser(
        description="promptkit — generate / validate / run Spire prompt sets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    action = ap.add_mutually_exclusive_group(required=True)
    action.add_argument("--generate", action="store_true",
                        help="plain prompt .txt -> .json (router's choices)")
    action.add_argument("--validate", action="store_true",
                        help="check each .json's routing (no execution)")
    action.add_argument("--run", action="store_true",
                        help="end to end against Fusion + staged corpus check")

    ap.add_argument("files", nargs="*", type=Path,
                    help="input files (.txt for --generate, .json otherwise)")
    ap.add_argument("--prompt", default=None,
                    help="with --run: one ad-hoc prompt instead of a file "
                         "(full run_graph-style output).")
    ap.add_argument("--show-stages", action="store_true",
                    help="with --run on a corpus: print the per-stage "
                         "breakdown (module/intent/tool/plan/execute) per "
                         "prompt, not just the one-line verdict.")

    from spire.diagnostics import add_diagnostic_arguments
    add_diagnostic_arguments(ap)

    args = ap.parse_args()

    if args.generate:
        return do_generate(args.files)
    if args.validate:
        return do_validate(args.files)
    if args.run:
        from spire.diagnostics import flags_from_args, setup_diagnostics
        setup_diagnostics(flags_from_args(args))
        if args.prompt is None and not args.files:
            print("--run needs .json file(s) or --prompt \"...\"",
                  file=sys.stderr)
            return 2
        return do_run(args.files, args.prompt, args.show_stages)
    return 2


if __name__ == "__main__":
    sys.exit(main())
