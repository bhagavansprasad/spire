#!/usr/bin/env python3
"""
promptkit.py — run Spire prompts end to end against Fusion.

Pick ONE source under --run:

    --run --prompt "a" "b" ...       Run one or more ad-hoc prompts.
    --run --prompt-file <f1> <f2> ... Run every prompt in one or more text files.
    --run --manifest <m1> <m2> ...   Batch mode: one subprocess per set.

Diagnostics reuse the same system as run_graph.py. In --manifest mode the
parent's diagnostic flags are forwarded to each child.

Examples:
    python scripts/promptkit.py --run --prompt "show suppliers in US" --show-all
    python scripts/promptkit.py --run --manifest smoke.yaml full.yaml \
        --outdir results/tonight --show-planner
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from spire.nl_parser.router import (
    ClassificationError,
    classify_modules,
    route_and_parse,
)
from spire.nl_parser.result import RefusalError
from spire.nl_parser.vocabulary import load_kg_menu
from spire.planner.planner import generate_plan
from spire.config import mcp_server_url, reset_usage, usage_report


# ==========================================================================
# DIAG instrumentation — monkey-patches + helpers
# ==========================================================================
import spire.nl_parser.router  as _router_mod
import spire.planner.planner   as _planner_mod
from diag.timer import (
    timer   as _diag_timer,
    atimer  as _diag_atimer,
    enable  as _diag_enable,
    reset   as _diag_reset,
    summary as _diag_summary,
)

# ---- llm layer: classify_modules + route_and_parse (both LLM calls) ----
_orig_classify = _router_mod.classify_modules
_orig_route    = _router_mod.route_and_parse

def _timed_classify(*a, **kw):
    with _diag_timer("llm", "classify"):
        return _orig_classify(*a, **kw)

def _timed_route(*a, **kw):
    with _diag_timer("llm", "parse"):
        return _orig_route(*a, **kw)

_router_mod.classify_modules = _timed_classify
_router_mod.route_and_parse  = _timed_route

# ---- planner layer: generate_plan ----
_orig_plan = _planner_mod.generate_plan

def _timed_plan(*a, **kw):
    with _diag_timer("planner", "generate_plan"):
        return _orig_plan(*a, **kw)

_planner_mod.generate_plan = _timed_plan

# ---- fusion layer: executor + tool (patched at Client() open in _run_async) ----

# ==========================================================================
# Defaults
# ==========================================================================
DEFAULT_SET_TIMEOUT = 28800


# ==========================================================================
# Corpus I/O
# ==========================================================================
def load_cases(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = []
    for e in data:
        module = e.get("module") or []
        mod = ",".join(module) if isinstance(module, list) else str(module)
        cases.append((mod, e.get("tool", ""), e.get("prompt", "")))
    return cases


def load_plain_prompts(path: Path) -> list[str]:
    prompts = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        prompts.append(line)
    return prompts


# ==========================================================================
# Shared stage checks (unreachable from CLI; kept for reference)
# ==========================================================================
def _selected_tool(plan) -> str | None:
    if not plan:
        return None
    return getattr(plan[0], "tool_name", None)


def validate_one(prompt: str, exp_module: str, exp_tool: str, menu):
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
        r = validate_one(prompt, "", "", menu)
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


def _classify_mark(m_ok: bool, t_ok: bool) -> tuple[str, bool, bool]:
    if t_ok:
        if m_ok:
            return "OK", True, False
        return "OK*", True, True
    return "TOOL\u2717", False, False


def validate_file(path: Path, menu) -> tuple[int, int, int]:
    cases = load_cases(path)
    print(f"\n### validate {path.name} — {len(cases)} prompts")
    tool_ok_count = 0
    mod_warn_count = 0
    rows = []
    for module_exp, tool_exp, prompt in cases:
        r = validate_one(prompt, module_exp, tool_exp, menu)
        m_ok, t_ok = r["module_ok"], r["tool_ok"]
        mark, is_pass, is_warn = _classify_mark(m_ok, t_ok)
        if is_pass:
            tool_ok_count += 1
        if is_warn:
            mod_warn_count += 1
        rows.append((mark, m_ok, t_ok, prompt, module_exp, tool_exp, r))
        print(f"[{mark:<6}] {prompt[:48]:<48} "
              f"mod={str(r['module_got']):<18} tool={r['tool_got']}")
    tool_fails = [row for row in rows if not row[2]]
    mod_warns = [row for row in rows if row[2] and not row[1]]
    summary = f"  {tool_ok_count}/{len(cases)} tools OK"
    if mod_warn_count:
        summary += (f"  ({mod_warn_count} module "
                    f"warning{'s' if mod_warn_count != 1 else ''})")
    print(summary)
    if tool_fails:
        print("  TOOL FAILURES:")
        for mark, m_ok, t_ok, prompt, module_exp, tool_exp, r in tool_fails:
            print(f"    [{mark}] {prompt}")
            print(f"        tool:   expected {tool_exp}  got {r['tool_got']}")
            print(f"        module: expected [{module_exp}]  got {r['module_got']}")
    if mod_warns:
        print("  MODULE WARNINGS (tool correct, module set differs):")
        for mark, m_ok, t_ok, prompt, module_exp, tool_exp, r in mod_warns:
            print(f"    [{mark}] {prompt}")
            print(f"        module: expected [{module_exp}]  got {r['module_got']}")
    return tool_ok_count, len(cases), mod_warn_count


def do_validate(files: list[Path]) -> int:
    menu = load_kg_menu()
    reset_usage()
    total_ok = total_all = total_warn = 0
    for f in files:
        if not f.is_file():
            print(f"  [skip] not found: {f}")
            continue
        ok, n, warn = validate_file(f, menu)
        total_ok += ok
        total_all += n
        total_warn += warn
    print(f"\n{'='*72}")
    print(f"TOTAL: {total_ok}/{total_all} tools OK across {len(files)} file(s)"
          + (f"  ({total_warn} module warning{'s' if total_warn != 1 else ''})"
             if total_warn else ""))
    print('='*72)
    print(usage_report())
    return 0 if total_ok == total_all else 1


# ==========================================================================
# --run : end to end against Fusion.
# ==========================================================================
def _stage_report(prompt, exp_module, exp_tool, state: dict) -> dict:
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
    """Emit answer + gated diagnostics. Synthesizer is timed here."""
    from spire.diagnostics import answer, get_logger
    from spire.nl_parser.capability import capability_message
    from spire.rendering.formatters import (
        _format_intent, _format_outputs, _format_plan,
        _format_summary,
        render_cli_stdout,
    )

    _parser_log  = get_logger("parser")
    _planner_log = get_logger("planner")
    _executor_log = get_logger("executor")
    _tokens_log  = get_logger("tokens")
    _summary_log = get_logger("summary")
    _sql_log     = get_logger("sql")

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
    _block(_sql_log, _format_sql(state["plan"]))

    _outputs = state.get("outputs") or {}
    _display = state.get("projected_outputs") or _outputs
    _block(_executor_log, _format_outputs(_display))

    # synthesizer layer: compose the human-readable text + emit to CLI.
    # One span wraps both, so the two steps are reported as a single
    # synthesizer elapsed — matches the grouping you asked for.
    with _diag_timer("synthesizer", "answer"):
        answer(render_cli_stdout(state, menu))

    _summary_log.info("%s", _format_summary(state["plan"], _outputs,
                                            state.get("response")))
    _block(_tokens_log, usage_report())


def _format_sql(plan):
    try:
        from spire.rendering.sql_emitter import emit_sql as _emit_sql
    except Exception as exc:  # noqa: BLE001
        return f"[show-sql] emitter unavailable: {exc}"
    if not plan:
        return "SQL projection: (empty plan)"
    statements = _emit_sql(plan)
    parts = ["SQL projection:"]
    for i, stmt in enumerate(statements, start=1):
        if len(statements) > 1:
            parts.append(f"\n[statement {i} of {len(statements)}]")
        parts.append(stmt)
    return "\n".join(parts)


async def _run_one(prompt, menu, client):
    """Run one prompt through the graph; fusion.executor is timed here."""
    from spire.graph.pipeline import GRAPH
    try:
        async with _diag_atimer("fusion", "executor"):
            state = await GRAPH.ainvoke({
                "prompt": prompt, "menu": menu, "session": client,
                "progress_handler": None, "cache_mode": None, "cache_slot": None,
            })
    except Exception as exc:  # noqa: BLE001
        state = {"error": f"pipeline crash: {type(exc).__name__}: {exc}"}
    return state


def _print_stage_breakdown(rpt):
    for stage in ("module", "intent", "tool", "plan", "execute"):
        if stage in rpt["stages"]:
            status, detail = rpt["stages"][stage]
            d = f"  ({detail})" if detail else ""
            print(f"    {stage:<8} {status:<8}{d}")
    verdict = ("FAILED AT: " + rpt["failed_at"]) if rpt["failed_at"] else "PASS"
    print(f"    -> {verdict}")


async def _run_async(prompts: list[str]) -> int:
    from fastmcp import Client

    _diag_enable()
    _diag_reset()

    menu = load_kg_menu()
    show_header = len(prompts) > 1
    total = len(prompts)
    failed = 0

    url = mcp_server_url()
    try:
        async with Client(url) as client:
            # fusion layer: every MCP tool call timed under fusion.<tool_name>.
            _orig_call_tool = client.call_tool

            async def _timed_call_tool(name, args=None, **kw):
                short = str(name).rsplit(".", 1)[-1] if name else "call_tool"
                async with _diag_atimer("fusion", short):
                    return await _orig_call_tool(name, args, **kw)

            client.call_tool = _timed_call_tool

            for idx, prompt in enumerate(prompts, start=1):
                reset_usage()
                if show_header:
                    print(f"\n{'='*72}")
                    print(f"[{idx} of {total}]")
                    print(f"PROMPT: {prompt}")
                    print('='*72, flush=True)
                async with _diag_atimer("prompt", "total"):
                    state = await _run_one(prompt, menu, client)
                    _emit_run_graph_output(state, menu)
                if state.get("error") and not state.get("plan_refusal"):
                    failed += 1
    except RuntimeError as exc:
        if "All connection attempts failed" in str(exc):
            print(f"Cannot reach the MCP server at {url}.", file=sys.stderr)
            print(
                "Start it first: 'spired' (dev) or './spire-host.sh --start dev'.",
                file=sys.stderr,
            )
            print(_diag_summary(), flush=True)
            return 1
        raise

    print(_diag_summary(), flush=True)
    return 0 if failed == 0 else 1


def do_run(prompts: list[str]) -> int:
    return asyncio.run(_run_async(prompts))


# ==========================================================================
# Batch mode
# ==========================================================================
def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_set_names(manifest: Path) -> list[str]:
    try:
        import yaml
    except ImportError:
        print("ERROR: PyYAML is not installed (pip install pyyaml).",
              file=sys.stderr)
        raise SystemExit(2)
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    names = data.get("sets")
    if not names or not isinstance(names, list):
        print(f"ERROR: {manifest} has no 'sets:' list.", file=sys.stderr)
        raise SystemExit(2)
    return [str(n).strip() for n in names if str(n).strip()]


def _forward_diagnostics(args) -> list[str]:
    out: list[str] = []
    for key, val in vars(args).items():
        if not key.startswith("show_") or val is None:
            continue
        if key == "show_all":
            if val:
                out.append("--show-all")
            continue
        flag = "--" + key.replace("_", "-")
        out.append(flag if val else "--no-" + key.replace("_", "-"))
    return out


def _run_one_set(txt: Path, out_file: Path,
                 timeout: int, diag_args: list[str]) -> tuple[int, float]:
    cmd = [sys.executable, str(Path(__file__).resolve()),
           "--run", "--prompt-file", str(txt), *diag_args]
    start = time.monotonic()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", encoding="utf-8") as fh:
        fh.write(f"# promptkit batch — {_timestamp()}\n")
        fh.write(f"# $ {' '.join(cmd)}\n\n")
        fh.flush()
        try:
            proc = subprocess.run(
                cmd, stdout=fh, stderr=subprocess.STDOUT, timeout=timeout,
            )
            code = proc.returncode
        except subprocess.TimeoutExpired:
            fh.write(f"\n=== KILLED: exceeded {timeout}s at {_timestamp()} ===\n")
            code = 124
        except Exception as exc:  # pragma: no cover - defensive
            fh.write(f"\n=== RUNNER ERROR: {type(exc).__name__}: {exc} ===\n")
            code = -1
    return code, time.monotonic() - start


def _write_summaries(
    outdir: Path, results: list[tuple[str, int, float]]
) -> str:
    name_w = max((len(n) for n, _, _ in results), default=8)
    lines = ["PROMPTKIT BATCH SUMMARY", f"As of: {_timestamp()}", ""]
    lines.append(f"{'set'.ljust(name_w)}   {'exit':>4}  {'secs':>6}   status")
    lines.append("-" * (name_w + 28))
    for name, code, secs in results:
        if code == 0:
            status = "ok (read the answers, not the tally)"
        elif code == 124:
            status = "TIMED OUT (partial)"
        else:
            status = f"ERROR (exit {code})"
        lines.append(
            f"{name.ljust(name_w)}   {code:>4}  {secs:>6.0f}   {status}"
        )
    summary = "\n".join(lines)
    (outdir / "_summary.log").write_text(summary + "\n", encoding="utf-8")

    by_folder: dict[str, list[tuple[str, int, float]]] = {}
    for name, code, secs in results:
        folder = name.rsplit("/", 1)[0] if "/" in name else ""
        by_folder.setdefault(folder, []).append((name, code, secs))

    for folder, rows in by_folder.items():
        if not folder:
            continue
        folder_dir = outdir / folder
        folder_dir.mkdir(parents=True, exist_ok=True)
        folder_basename = Path(folder).name
        folder_summary_path = folder_dir / f"{folder_basename}_summary.log"
        f_lines = [
            f"PROMPTKIT FOLDER SUMMARY: {folder}",
            f"As of: {_timestamp()}",
            "",
        ]
        short_rows = [
            (n[len(folder) + 1:] if n.startswith(folder + "/") else n, c, s)
            for n, c, s in rows
        ]
        f_name_w = max((len(n) for n, _, _ in short_rows), default=8)
        f_lines.append(
            f"{'set'.ljust(f_name_w)}   {'exit':>4}  {'secs':>6}   status"
        )
        f_lines.append("-" * (f_name_w + 28))
        for short, code, secs in short_rows:
            if code == 0:
                f_status = "ok (read the answers, not the tally)"
            elif code == 124:
                f_status = "TIMED OUT (partial)"
            else:
                f_status = f"ERROR (exit {code})"
            f_lines.append(
                f"{short.ljust(f_name_w)}   {code:>4}  {secs:>6.0f}   {f_status}"
            )
        folder_summary_path.write_text(
            "\n".join(f_lines) + "\n", encoding="utf-8"
        )
    return summary


def do_batch(manifest: Path, outdir: Path, prompts_dir: Path,
             timeout: int, diag_args: list[str]) -> int:
    names = _load_set_names(manifest)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "_manifest.yaml").write_bytes(manifest.read_bytes())
    log_path = outdir / "_run_log.txt"

    def log(line: str) -> None:
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    log(f"PROMPTKIT BATCH STARTED at {_timestamp()}")
    log(f"Manifest: {manifest}   Output: {outdir}   Timeout/set: {timeout}s")
    log(f"Sets: {len(names)}")

    results: list[tuple[str, int, float]] = []
    for name in names:
        txt = prompts_dir / f"{name}.txt"
        if not txt.is_file():
            log(f"WARNING: {txt} missing — SKIPPING set {name}")
            continue
        log(f"=== START {name} at {_timestamp()} ===")
        inp_copy = outdir / f"{name}.txt"
        inp_copy.parent.mkdir(parents=True, exist_ok=True)
        inp_copy.write_bytes(txt.read_bytes())
        code, secs = _run_one_set(txt, outdir / f"{name}.log",
                                  timeout, diag_args)
        note = ("  <-- TIMED OUT" if code == 124
                else f"  <-- exit {code}" if code != 0 else "")
        log(f"    run       exit {code}  ({secs:.0f}s){note}")
        log(f"=== DONE  {name} at {_timestamp()} ===")
        results.append((name, code, secs))
        _write_summaries(outdir, results)

    log(f"ALL SETS COMPLETE at {_timestamp()}")
    final_summary = _write_summaries(outdir, results)
    print("\n" + final_summary, flush=True)
    return 1 if any(code != 0 for _, code, _ in results) else 0


# ==========================================================================
# CLI
# ==========================================================================
def main() -> int:
    ap = argparse.ArgumentParser(
        description="promptkit — run Spire prompts end to end against Fusion.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--run", action="store_true", required=True,
                    help="run prompt(s) end to end against Fusion.")

    src = ap.add_mutually_exclusive_group(required=False)
    src.add_argument("--prompt", default=None, nargs="+", metavar="STR",
                     help="with --run: one or more prompt strings.")
    src.add_argument("--prompt-file", default=None, nargs="+", type=Path,
                     metavar="FILE",
                     help="with --run: one or more text files of prompts.")
    src.add_argument("--manifest", default=None, nargs="+", type=Path,
                     metavar="YAML",
                     help="with --run: one or more YAML 'sets:' manifests.")

    ap.add_argument("--outdir", type=Path, default=None,
                    help="with --manifest: results dir.")
    ap.add_argument("--prompts-dir", type=Path,
                    default=Path("prompts"),
                    help="with --manifest: dir holding <name>.txt")
    ap.add_argument("--timeout", type=int, default=DEFAULT_SET_TIMEOUT,
                    help=f"with --manifest: per-set timeout seconds "
                         f"(default {DEFAULT_SET_TIMEOUT})")

    from spire.diagnostics import add_diagnostic_arguments
    add_diagnostic_arguments(ap)

    args = ap.parse_args()

    if args.manifest is not None:
        if args.prompt is not None or args.prompt_file is not None:
            print("--manifest cannot be combined with --prompt / "
                  "--prompt-file.", file=sys.stderr)
            return 2
        for m in args.manifest:
            if not m.is_file():
                print(f"manifest not found: {m}", file=sys.stderr)
                return 2
        base = (args.outdir
                or Path(f"overnights/{datetime.now():%Y%m%d_%H%M%S}"))
        diag = _forward_diagnostics(args)
        if len(args.manifest) == 1:
            return do_batch(args.manifest[0], base, args.prompts_dir,
                            args.timeout, diag)
        rc = 0
        for m in args.manifest:
            sub = base / m.stem
            print(f"\n### manifest {m}  ->  {sub}")
            rc |= do_batch(m, sub, args.prompts_dir, args.timeout, diag)
        return rc

    from spire.diagnostics import flags_from_args, setup_diagnostics
    setup_diagnostics(flags_from_args(args))

    if args.prompt is None and args.prompt_file is None:
        print("--run needs one of: --prompt \"...\" [...], "
              "--prompt-file <file> [...], or --manifest <yaml> [...].",
              file=sys.stderr)
        return 2

    if args.prompt is not None:
        return do_run(args.prompt)

    prompts: list[str] = []
    for f in args.prompt_file:
        if not f.is_file():
            print(f"--prompt-file not found: {f}", file=sys.stderr)
            return 2
        got = load_plain_prompts(f)
        if not got:
            print(f"--prompt-file {f} contained no prompts.", file=sys.stderr)
            return 2
        prompts.extend(got)
    return do_run(prompts)


if __name__ == "__main__":
    print()
    # sys.argv = [
    #     "promptkit",
    #     "--run",
    #     "--prompt", "Show me AR invoices for customer ABC Corporation Americas",
    # ]
    sys.exit(main())