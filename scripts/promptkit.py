#!/usr/bin/env python3
"""
promptkit.py — run Spire prompts end to end against Fusion.

Pick ONE source under --run:

    --run --prompt "a" "b" ...       Run one or more ad-hoc prompts. Replaces
                                     run_graph.py for single prompts.

    --run --prompt-file <f1> <f2> ... Run every prompt in one or more text
                                     files, one per line ('#'/blank skipped).
                                     Files run in order; within a file, prompts
                                     run in line order.

    --run --manifest <m1> <m2> ...   Batch mode: read one or more YAML 'sets:'
                                     lists and run every set as its own
                                     subprocess with a per-set --timeout, so
                                     one hung or crashed set cannot stop the
                                     batch. Writes per-set output plus
                                     _run_log.txt / _summary.log under --outdir.

    When --outdir is not given, batch output goes to
    overnights/<YYYYMMDD_HHMMSS>/ in the current directory. A single manifest
    writes straight into the output dir; multiple manifests each get a
    <stem>/ subfolder so set names can't collide.

The old --generate and --validate actions are no longer exposed on the CLI.
Their helpers remain in this file (unreachable) for reference.

Diagnostics reuse the same system as run_graph.py: the committed defaults in
pyproject.toml ([tool.spire.diagnostics]) apply, and --show-parser /
--show-planner / --show-raw-output / --show-synthesizer / --show-tokens /
--show-timings / --show-all override per run. In --manifest mode the parent's
diagnostic flags are forwarded to each child, so they land on the real runs.

Examples:
    python scripts/promptkit.py --run --prompt "show suppliers in US" --show-all
    python scripts/promptkit.py --run --prompt "List suppliers in India" \
                                            "Show open POs for supplier 2144"
    python scripts/promptkit.py --run --prompt-file prompts/supplier/supplier_smoke.txt
    python scripts/promptkit.py --run --prompt-file a.txt b.txt
    python scripts/promptkit.py --run --manifest scripts/manifests/promptkit_sets.yaml
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
# Defaults
# ==========================================================================

# Per-set timeout for --manifest batch mode, in seconds. 8 hours.
DEFAULT_SET_TIMEOUT = 28800


# ==========================================================================
# Corpus I/O
# ==========================================================================

def load_cases(path: Path):
    """Load a JSON corpus: list of {prompt, module: [...], tool, note}.
    Returns (module_str, tool, prompt) triples (module_str is comma-joined).

    Kept for backward compatibility with the old corpus mode; no longer
    reachable from the CLI.
    """
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
# Retained for the old --generate / --validate actions; unreachable now.
# ==========================================================================

def _selected_tool(plan) -> str | None:
    if not plan:
        return None
    return getattr(plan[0], "tool_name", None)


def validate_one(prompt: str, exp_module: str, exp_tool: str, menu):
    """Per-prompt check: classify -> route_and_parse -> generate_plan,
    comparing module and tool to the corpus. No execution."""
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
# Old --generate action: plain prompts -> JSON of the router's choices.
# Retained; unreachable from the CLI.
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
# Old --validate action: check each JSON's routing (no execution).
# Retained; unreachable from the CLI.
# ==========================================================================

def _classify_mark(m_ok: bool, t_ok: bool) -> tuple[str, bool, bool]:
    """Decide a validate row's mark and how it counts.

    Pass/fail is the TOOL's alone. A module mismatch on a tool-correct row is
    a WARNING, not a failure: the module set only scopes the parser's grounding
    and is discarded after the parse, so the selected tool is what determines
    the answer. A wrong tool is the only real failure.
    """
    if t_ok:
        if m_ok:
            return "OK", True, False
        return "OK*", True, True            # tool correct, module set differs
    return "TOOL\u2717", False, False        # wrong tool = real failure


def validate_file(path: Path, menu) -> tuple[int, int, int]:
    """Check each case's routing. Pass/fail is decided by the TOOL: a module
    mismatch on a tool-correct prompt is a WARNING, not a failure."""
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

    tool_fails = [row for row in rows if not row[2]]              # t_ok False
    mod_warns = [row for row in rows if row[2] and not row[1]]    # t_ok True, m_ok False

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
    # Exit is driven by TOOLS only; module warnings never fail the run.
    return 0 if total_ok == total_all else 1


# ==========================================================================
# --run : end to end against Fusion.
# ==========================================================================

def _stage_report(prompt, exp_module, exp_tool, state: dict) -> dict:
    """Read the graph STATE back and check each stage vs the corpus. Retained
    for the old corpus mode; no longer reachable from the CLI."""
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
    using the same loggers/answer(). Honors pyproject.toml + --show-*.

    The SQL projection block rides the ``spire.sql`` diagnostic; enable
    it with ``--show-sql`` (or the file / env layers). Print only, no
    execution.
    """
    from spire.diagnostics import answer, get_logger
    from spire.nl_parser.capability import capability_message
    from spire.rendering.formatters import (
        _format_intent, _format_outputs, _format_plan,
        _format_summary,
        render_cli_stdout,
    )

    _parser_log = get_logger("parser")
    _planner_log = get_logger("planner")
    _executor_log = get_logger("executor")
    _tokens_log = get_logger("tokens")
    _summary_log = get_logger("summary")
    _sql_log = get_logger("sql")

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

    # Emit through the same function the API hands to the UI, so
    # the CLI and the UI match by construction rather than by
    # convention. render_answer (still used by run_prompt_set and
    # run_graph) composes the identical text via the same
    # formatters; this route makes the shared text a property of
    # a single function rather than of three callers who happen
    # to agree.
    answer(render_cli_stdout(state, menu))

    _summary_log.info("%s", _format_summary(state["plan"], _outputs,
                                            state.get("response")))
    _block(_tokens_log, usage_report())


def _format_sql(plan):
    """Format the Fusion-DB SQL projection of a Plan as a text block.

    Print-only: no SQL is executed, no DB connection is opened. The
    emitter is a pure function of (plan, overlay); see
    src/spire/rendering/sql_emitter.py and docs/design/SQL_OVERLAY_POC.md.

    Returns a string; the caller passes it to ``_block(_sql_log, ...)``
    which is a no-op when the ``spire.sql`` diagnostic is off.
    """
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
    """Run one prompt through the graph; return the final state.

    The classifier's module selection is read from the graph state
    (`_modules_got`), written there by parse_node from the ParseResult the
    router produced. It is NOT re-classified here (F-002).
    """
    from spire.graph.pipeline import GRAPH
    try:
        state = await GRAPH.ainvoke({
            "prompt": prompt, "menu": menu, "session": client,
            "progress_handler": None, "cache_mode": None, "cache_slot": None,
        })
    except Exception as exc:  # noqa: BLE001
        state = {"error": f"pipeline crash: {type(exc).__name__}: {exc}"}
    return state


def _print_stage_breakdown(rpt):
    """Print the per-stage OK/FAIL/DIVERGE breakdown for one prompt.
    Retained for the old corpus mode; no longer reachable from the CLI."""
    for stage in ("module", "intent", "tool", "plan", "execute"):
        if stage in rpt["stages"]:
            status, detail = rpt["stages"][stage]
            d = f"  ({detail})" if detail else ""
            print(f"    {stage:<8} {status:<8}{d}")
    verdict = ("FAILED AT: " + rpt["failed_at"]) if rpt["failed_at"] else "PASS"
    print(f"    -> {verdict}")


async def _run_async(prompts: list[str]) -> int:
    from fastmcp import Client

    menu = load_kg_menu()
    show_header = len(prompts) > 1
    total = len(prompts)
    failed = 0

    url = mcp_server_url()
    try:
        async with Client(url) as client:
            for idx, prompt in enumerate(prompts, start=1):
                # Reset the token accumulator per prompt so each prompt's
                # usage_report() (printed inside _emit_run_graph_output)
                # reflects only that prompt.
                reset_usage()
                if show_header:
                    # Progress sits on its own line so the "PROMPT: <text>"
                    # line stays byte-identical for anything that parses it.
                    # flush so 'tail -f' on a batch log shows it immediately.
                    print(f"\n{'='*72}")
                    print(f"[{idx} of {total}]")
                    print(f"PROMPT: {prompt}")
                    print('='*72, flush=True)
                state = await _run_one(prompt, menu, client)
                _emit_run_graph_output(state, menu)
                # A refusal (parser or planner) is a valid outcome — only a
                # real pipeline error or execution failure counts against
                # the run.
                if state.get("error") and not state.get("plan_refusal"):
                    failed += 1
    except RuntimeError as exc:
        # The fastmcp Client raises RuntimeError with a long library
        # traceback when the MCP server is unreachable. The final line
        # ("Client failed to connect: All connection attempts failed")
        # names neither the URL nor the cause, and everything above it is
        # httpx/mcp/exceptiongroup internals. Replace it with the two
        # lines that answer the two questions a reader has.
        if "All connection attempts failed" in str(exc):
            print(f"Cannot reach the MCP server at {url}.", file=sys.stderr)
            print(
                "Start it first: 'spired' (dev) or './spire-host.sh --start dev'.",
                file=sys.stderr,
            )
            return 1
        raise

    return 0 if failed == 0 else 1


def do_run(prompts: list[str]) -> int:
    return asyncio.run(_run_async(prompts))


# ==========================================================================
# Batch mode (--run --manifest): run every set in a YAML 'sets:' list, each
# as its own promptkit subprocess with a per-set timeout.
# ==========================================================================

def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_set_names(manifest: Path) -> list[str]:
    """Read the ordered 'sets:' list of set names from the YAML manifest."""
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
    """Rebuild the parent's diagnostic flags as CLI args for a child
    promptkit subprocess. Tri-state: True -> --show-X, False -> --no-show-X,
    None -> not forwarded. Same flag names the diagnostics layer registers,
    so nothing here is hard-coded to a specific diagnostic."""
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
    """Run one prompt set as a subprocess of promptkit.py itself.
    Returns (exit_code, seconds); exit 124 on timeout."""
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
    """Write (overwrite) the top-level _summary.log and one
    <folder>_summary.log per folder represented in `results`. Returns the
    top-level summary text so the caller can print it once.

    Called after EACH set completes, so a mid-batch kill (Ctrl+C, pkill,
    host crash, parent exception) leaves valid partial summaries on disk
    for every set that finished before the interruption. The per-set .log
    files are written by _run_one_set on their own schedule; this helper
    is a separate sweep over whatever `results` currently holds.
    """
    # ---- top-level summary ----
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

    # ---- per-folder summaries ----
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
    # Freeze the manifest itself. The per-set .txt copies record what each
    # set ran; this records WHICH sets were requested, in what order, with
    # what timeout. Together they make the round self-describing: anyone
    # can reconstruct the batch from _manifest.yaml + the per-set .txt files.
    (outdir / "_manifest.yaml").write_bytes(manifest.read_bytes())
    log_path = outdir / "_run_log.txt"
    summary_path = outdir / "_summary.log"

    def log(line: str) -> None:
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    log(f"PROMPTKIT BATCH STARTED at {_timestamp()}")
    log(f"Manifest: {manifest}   Output: {outdir}   Timeout/set: {timeout}s")
    log(f"Sets: {len(names)}")

    # (name, exit_code, seconds)
    results: list[tuple[str, int, float]] = []

    for name in names:
        txt = prompts_dir / f"{name}.txt"
        if not txt.is_file():
            log(f"WARNING: {txt} missing — SKIPPING set {name}")
            continue
        log(f"=== START {name} at {_timestamp()} ===")
        # Freeze the exact input used for this set: copy it into the
        # output folder alongside its log. The .txt copy is the version
        # this run consumed; if prompts/<name>.txt is edited later, the
        # copy here still records what was actually run.
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

    # Final pass. The last per-set write above already wrote the same
    # content; this call returns the summary text so we can print it
    # once at the end of the batch.
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
                    help="run prompt(s) end to end against Fusion. "
                         "Pick one source: --prompt, --prompt-file, "
                         "or --manifest.")

    # Sources. nargs='+' => space-separated lists; no repeated-flag form.
    src = ap.add_mutually_exclusive_group(required=False)
    src.add_argument("--prompt", default=None, nargs="+", metavar="STR",
                     help="with --run: one or more prompt strings, "
                          "space-separated. Each is run in turn.")
    src.add_argument("--prompt-file", default=None, nargs="+", type=Path,
                     metavar="FILE",
                     help="with --run: one or more text files of prompts, "
                          "space-separated. Files run in order; within each "
                          "file, prompts run in line order.")
    src.add_argument("--manifest", default=None, nargs="+", type=Path,
                     metavar="YAML",
                     help="with --run: one or more YAML 'sets:' manifests, "
                          "space-separated. A single manifest writes into "
                          "--outdir; multiple manifests each get a <stem>/ "
                          "subfolder so set names can't collide.")

    # batch-mode knobs (only meaningful with --manifest)
    ap.add_argument("--outdir", type=Path, default=None,
                    help="with --manifest: results dir. Default "
                         "promptkit_<YYYYMMDD_HHMMSS>/ in the cwd.")
    ap.add_argument("--prompts-dir", type=Path,
                    default=Path("prompts"),
                    help="with --manifest: dir holding <name>.txt "
                         "(default prompts)")
    ap.add_argument("--timeout", type=int, default=DEFAULT_SET_TIMEOUT,
                    help=("with --manifest: per-set timeout seconds "
                          f"(default {DEFAULT_SET_TIMEOUT})"))

    from spire.diagnostics import add_diagnostic_arguments
    add_diagnostic_arguments(ap)

    args = ap.parse_args()

    # ---- batch mode: --run --manifest <yaml> [<yaml> ...] ----
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

        # Multiple manifests: one subfolder per manifest stem.
        rc = 0
        for m in args.manifest:
            sub = base / m.stem
            print(f"\n### manifest {m}  ->  {sub}")
            rc |= do_batch(m, sub, args.prompts_dir, args.timeout, diag)
        return rc

    # ---- single/file mode: --run --prompt | --prompt-file ----
    from spire.diagnostics import flags_from_args, setup_diagnostics
    setup_diagnostics(flags_from_args(args))

    if args.prompt is None and args.prompt_file is None:
        print("--run needs one of: --prompt \"...\" [...], "
              "--prompt-file <file> [...], or --manifest <yaml> [...].",
              file=sys.stderr)
        return 2

    if args.prompt is not None:
        return do_run(args.prompt)

    # --prompt-file: concatenate every file's prompts, in order.
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
    sys.exit(main())