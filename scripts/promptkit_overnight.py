#!/usr/bin/env python3
"""
promptkit_overnight.py — run promptkit over every set in a manifest, one after
another, unattended. For each set it does all three phases in order:

    1. generate   scripts/prompts/<name>.txt  -> scripts/prompts/<name>.json
    2. validate   scripts/prompts/<name>.json  (routing check, no pod)
    3. run        scripts/prompts/<name>.json  (end to end against Fusion)

Each set runs as a SEPARATE subprocess with a per-set timeout, so one hung or
crashing set cannot stop the batch — the runner records what happened and moves
on. Modeled on run_overnight.py; the difference is it drives promptkit.py
(generate/validate/run) instead of run_prompt_set.py.

The MCP server must be up for the --run phase (Fusion is hit for real). If it is
in a foreground terminal you plan to close, background it.

Manifest (promptkit_sets.yaml) is a top-level 'sets:' list of set NAMES. Each
name resolves to scripts/prompts/<name>.txt and <name>.json. Comment a line out
to skip it.

Usage:
    python scripts/promptkit_overnight.py
    python scripts/promptkit_overnight.py --manifest scripts/promptkit_sets.yaml
    python scripts/promptkit_overnight.py --outdir results/tonight
    python scripts/promptkit_overnight.py --timeout 3600
    python scripts/promptkit_overnight.py --skip-run        # generate+validate only
    python scripts/promptkit_overnight.py --skip-generate   # reuse existing .json

Output (in <outdir>, default promptkit_<YYYYMMDD>/):
    <name>.txt      full output of that set's generate + validate + run
    _run_log.txt    one line per set/phase: start, end, duration, exit code
    _summary.txt    a compact table written at the end

EXIT CODES per phase, recorded in the log:
    0     ran to completion (a green tally is NOT a verdict — read the answers)
    124   the phase hit its timeout and was killed (partial output saved)
    other the phase errored; see its output file
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


PROMPTKIT = "scripts/promptkit.py"


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


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _run_phase(cmd: list[str], out_fh, timeout: int) -> int:
    """Run one promptkit phase as a subprocess, appending to out_fh.
    Returns the exit code (124 on timeout)."""
    out_fh.write(f"\n\n===== $ {' '.join(cmd)} =====\n")
    out_fh.flush()
    try:
        proc = subprocess.run(
            cmd, stdout=out_fh, stderr=subprocess.STDOUT, timeout=timeout,
        )
        return proc.returncode
    except subprocess.TimeoutExpired:
        out_fh.write(f"\n=== KILLED: exceeded {timeout}s at {_timestamp()} ===\n")
        return 124
    except Exception as exc:  # pragma: no cover - defensive
        out_fh.write(f"\n=== RUNNER ERROR: {type(exc).__name__}: {exc} ===\n")
        return -1


def run_all(
    manifest: Path,
    outdir: Path,
    prompts_dir: Path,
    timeout: int,
    skip_generate: bool,
    skip_validate: bool,
    skip_run: bool,
) -> int:
    names = _load_set_names(manifest)
    outdir.mkdir(parents=True, exist_ok=True)
    log_path = outdir / "_run_log.txt"
    summary_path = outdir / "_summary.txt"

    def log(line: str) -> None:
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    log(f"PROMPTKIT OVERNIGHT STARTED at {_timestamp()}")
    log(f"Manifest: {manifest}   Output: {outdir}   Timeout/phase: {timeout}s")
    phases = [p for p, skip in
              (("generate", skip_generate), ("validate", skip_validate),
               ("run", skip_run)) if not skip]
    log(f"Phases: {', '.join(phases)}")
    log(f"Sets: {len(names)}")

    # (name, phase, exit_code, seconds)
    results: list[tuple[str, str, int, float]] = []

    for name in names:
        txt = prompts_dir / f"{name}.txt"
        js = prompts_dir / f"{name}.json"
        out_file = outdir / f"{name}.txt"

        if not txt.is_file():
            log(f"WARNING: {txt} missing — SKIPPING set {name}")
            continue

        log(f"=== START {name} at {_timestamp()} ===")
        with out_file.open("w", encoding="utf-8") as fh:
            fh.write(f"# promptkit overnight — set {name} — {_timestamp()}\n")

            # Phase 1: generate (.txt -> .json)
            if not skip_generate:
                start = time.monotonic()
                code = _run_phase(
                    [sys.executable, PROMPTKIT, "--generate", str(txt)],
                    fh, timeout)
                secs = time.monotonic() - start
                results.append((name, "generate", code, secs))
                log(f"    generate  exit {code}  ({secs:.0f}s)")
                if code != 0:
                    log(f"    !! generate failed for {name}; skipping its "
                        f"validate/run")
                    continue

            # Phase 2: validate (.json)
            if not skip_validate:
                if not js.is_file():
                    fh.write(f"\n=== no {js}; cannot validate ===\n")
                    log(f"    validate  SKIPPED (no {js.name})")
                else:
                    start = time.monotonic()
                    code = _run_phase(
                        [sys.executable, PROMPTKIT, "--validate", str(js)],
                        fh, timeout)
                    secs = time.monotonic() - start
                    results.append((name, "validate", code, secs))
                    log(f"    validate  exit {code}  ({secs:.0f}s)")

            # Phase 3: run (.json, end to end)
            if not skip_run:
                if not js.is_file():
                    fh.write(f"\n=== no {js}; cannot run ===\n")
                    log(f"    run       SKIPPED (no {js.name})")
                else:
                    start = time.monotonic()
                    code = _run_phase(
                        [sys.executable, PROMPTKIT, "--run", str(js)],
                        fh, timeout)
                    secs = time.monotonic() - start
                    results.append((name, "run", code, secs))
                    note = ("  <-- TIMED OUT" if code == 124
                            else f"  <-- exit {code}" if code != 0 else "")
                    log(f"    run       exit {code}  ({secs:.0f}s){note}")

        log(f"=== DONE  {name} at {_timestamp()} ===")

    log(f"ALL SETS COMPLETE at {_timestamp()}")

    # ---- summary ----
    lines = ["PROMPTKIT OVERNIGHT SUMMARY", f"Finished: {_timestamp()}", ""]
    name_w = max((len(n) for n, _, _, _ in results), default=8)
    lines.append(f"{'set'.ljust(name_w)}   {'phase':<9} {'exit':>4}  {'secs':>6}"
                 f"   status")
    lines.append("-" * (name_w + 34))
    for name, phase, code, secs in results:
        if code == 0:
            status = "ok (tally is not a verdict — read answers)"
        elif code == 124:
            status = "TIMED OUT (partial)"
        else:
            status = f"ERROR (exit {code})"
        lines.append(f"{name.ljust(name_w)}   {phase:<9} {code:>4}  "
                     f"{secs:>6.0f}   {status}")
    summary = "\n".join(lines)
    summary_path.write_text(summary + "\n", encoding="utf-8")
    print("\n" + summary, flush=True)

    any_incomplete = any(code != 0 for _, _, code, _ in results)
    return 1 if any_incomplete else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run promptkit generate+validate+run over a manifest of "
                    "prompt sets, unattended."
    )
    ap.add_argument("--manifest", type=Path,
                    default=Path("scripts/promptkit_sets.yaml"),
                    help="YAML 'sets:' list (default scripts/promptkit_sets.yaml)")
    ap.add_argument("--outdir", type=Path, default=None,
                    help="results dir (default promptkit_<YYYYMMDD>/)")
    ap.add_argument("--prompts-dir", type=Path,
                    default=Path("scripts/prompts"),
                    help="dir holding <name>.txt / <name>.json")
    ap.add_argument("--timeout", type=int, default=3600,
                    help="per-phase timeout seconds (default 3600)")
    ap.add_argument("--skip-generate", action="store_true",
                    help="reuse existing .json; don't regenerate")
    ap.add_argument("--skip-validate", action="store_true",
                    help="skip the validate phase")
    ap.add_argument("--skip-run", action="store_true",
                    help="generate/validate only; no end-to-end Fusion run")
    args = ap.parse_args()

    if not args.manifest.is_file():
        print(f"ERROR: manifest not found: {args.manifest}", file=sys.stderr)
        return 2

    outdir = args.outdir or Path(f"promptkit_{datetime.now():%Y%m%d}")
    return run_all(
        manifest=args.manifest,
        outdir=outdir,
        prompts_dir=args.prompts_dir,
        timeout=args.timeout,
        skip_generate=args.skip_generate,
        skip_validate=args.skip_validate,
        skip_run=args.skip_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
