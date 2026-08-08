#!/usr/bin/env python3
"""
Run every prompt set listed in a YAML manifest, one after another, saving
each set's output to its own file. Built for an unattended overnight run:
the results are there to read in the morning.

Each set runs as a SEPARATE subprocess (the same command you would type by
hand: run_prompt_set.py --prompt-file scripts/prompts/<name>.txt). One set
crashing or timing out cannot stop the batch — the runner records what
happened and moves to the next.

WHY SUBPROCESS, NOT IMPORT: it reuses the exact pipeline wiring a manual
run uses, and it isolates failures. A hung prompt in one set is killed by
that set's timeout without taking the whole night down.

Manifest (overnight_sets.yaml) is just a list of set NAMES. Each name
resolves to scripts/prompts/<name>.txt. Comment a line out to skip it.

Usage:
    python scripts/run_overnight.py
    python scripts/run_overnight.py --manifest scripts/overnight_sets.yaml
    python scripts/run_overnight.py --outdir results/tonight
    python scripts/run_overnight.py --timeout 3600
    python scripts/run_overnight.py --prompts-dir scripts/prompts

Output (in <outdir>, default overnight_<YYYYMMDD>/):
    <name>.txt      full stdout+stderr of each set's run
    _run_log.txt    one line per set: start, end, duration, exit code
    _summary.txt    a compact table written at the end

EXIT CODES per set, recorded in the log:
    0     ran to completion (NOTE: not the same as "all answers correct" —
          run_prompt_set.py's own tally is not a verdict; read the answers)
    124   the set hit its timeout and was killed (partial output saved)
    other the set errored; see its output file
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def _load_set_names(manifest: Path) -> list[str]:
    """Read the ordered list of set names from the YAML manifest.

    Kept deliberately small: the manifest is a list under a top-level
    'sets:' key. PyYAML is already a project dependency (personas.yaml,
    context_bundles.yaml), but fail with a clear message if it isn't.
    """
    try:
        import yaml
    except ImportError:
        print(
            "ERROR: PyYAML is not installed. Install it (pip install pyyaml) "
            "or add the dependency.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    names = data.get("sets")
    if not names or not isinstance(names, list):
        print(
            f"ERROR: {manifest} has no 'sets:' list. Expected a top-level "
            "'sets:' key with a list of prompt-set names.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    # Strip stray whitespace; drop any empties.
    return [str(n).strip() for n in names if str(n).strip()]


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_all(
    manifest: Path,
    outdir: Path,
    prompts_dir: Path,
    timeout: int,
) -> int:
    names = _load_set_names(manifest)

    outdir.mkdir(parents=True, exist_ok=True)
    log_path = outdir / "_run_log.txt"
    summary_path = outdir / "_summary.txt"

    # Resolve each name to its prompt file up front, so a typo in the
    # manifest is caught before the long run starts, not at 2am.
    resolved: list[tuple[str, Path]] = []
    missing: list[str] = []
    for name in names:
        pf = prompts_dir / f"{name}.txt"
        if pf.is_file():
            resolved.append((name, pf))
        else:
            missing.append(name)

    def log(line: str) -> None:
        stamped = f"{line}"
        print(stamped, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(stamped + "\n")

    log(f"OVERNIGHT RUN STARTED at {_timestamp()}")
    log(f"Manifest: {manifest}")
    log(f"Output dir: {outdir}")
    log(f"Per-set timeout: {timeout}s")
    log(f"Sets to run: {len(resolved)}")
    if missing:
        # Not fatal — run what resolves, but make the misses loud.
        log(f"WARNING: {len(missing)} set(s) in the manifest have no "
            f"prompt file and will be SKIPPED: {', '.join(missing)}")

    results: list[tuple[str, int, float]] = []  # (name, exit_code, seconds)

    for name, pf in resolved:
        out_file = outdir / f"{name}.txt"
        log(f"=== START {name} at {_timestamp()} ===")
        start = time.monotonic()

        try:
            with out_file.open("w", encoding="utf-8") as fh:
                proc = subprocess.run(
                    [
                        sys.executable,
                        "scripts/run_prompt_set.py",
                        "--prompt-file",
                        str(pf),
                    ],
                    stdout=fh,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                )
            code = proc.returncode
        except subprocess.TimeoutExpired:
            # The child is killed by subprocess.run on timeout. Whatever it
            # had written to out_file so far is preserved. 124 mirrors the
            # shell `timeout` convention, so the log reads consistently.
            code = 124
            with out_file.open("a", encoding="utf-8") as fh:
                fh.write(
                    f"\n\n=== KILLED: exceeded {timeout}s timeout at "
                    f"{_timestamp()} ===\n"
                )
        except Exception as exc:  # pragma: no cover - defensive
            # The runner itself must never die on one set. Record and move on.
            code = -1
            with out_file.open("a", encoding="utf-8") as fh:
                fh.write(f"\n\n=== RUNNER ERROR: {type(exc).__name__}: {exc} ===\n")

        elapsed = time.monotonic() - start
        results.append((name, code, elapsed))

        note = ""
        if code == 124:
            note = "  <-- TIMED OUT"
        elif code != 0:
            note = f"  <-- nonzero exit ({code})"
        log(f"=== DONE  {name} at {_timestamp()}  "
            f"({elapsed:.0f}s, exit {code}){note} ===")

    log(f"ALL SETS COMPLETE at {_timestamp()}")

    # ---- Compact summary table, written once at the end ----
    lines = ["OVERNIGHT SUMMARY", f"Finished: {_timestamp()}", ""]
    name_w = max((len(n) for n, _, _ in results), default=4)
    lines.append(f"{'set'.ljust(name_w)}   {'exit':>4}   {'secs':>6}   status")
    lines.append("-" * (name_w + 26))
    for name, code, secs in results:
        if code == 0:
            status = "completed (read answers — tally is not a verdict)"
        elif code == 124:
            status = "TIMED OUT (partial output)"
        else:
            status = f"ERROR (exit {code})"
        lines.append(f"{name.ljust(name_w)}   {code:>4}   {secs:>6.0f}   {status}")
    if missing:
        lines.append("")
        lines.append(f"SKIPPED (no prompt file): {', '.join(missing)}")
    summary = "\n".join(lines)

    summary_path.write_text(summary + "\n", encoding="utf-8")
    print("\n" + summary, flush=True)

    # Exit nonzero if any set failed to complete, so an automated caller
    # can tell. A timeout counts as a failure to complete.
    any_incomplete = any(code != 0 for _, code, _ in results) or bool(missing)
    return 1 if any_incomplete else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run all prompt sets from a YAML manifest overnight, "
        "saving each set's output to its own file."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("scripts/overnight_sets.yaml"),
        help="YAML file with a 'sets:' list of prompt-set names "
        "(default: scripts/overnight_sets.yaml).",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=None,
        help="Directory for the result files "
        "(default: overnight_<YYYYMMDD>/).",
    )
    parser.add_argument(
        "--prompts-dir",
        type=Path,
        default=Path("scripts/prompts"),
        help="Directory holding the <name>.txt prompt sets "
        "(default: scripts/prompts).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=3600,
        help="Per-set timeout in seconds; a set exceeding it is killed and "
        "the batch moves on (default: 3600).",
    )
    args = parser.parse_args()

    if not args.manifest.is_file():
        print(f"ERROR: manifest not found: {args.manifest}", file=sys.stderr)
        return 2

    outdir = args.outdir or Path(f"overnight_{datetime.now():%Y%m%d}")

    return run_all(
        manifest=args.manifest,
        outdir=outdir,
        prompts_dir=args.prompts_dir,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
