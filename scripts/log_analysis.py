#!/usr/bin/env python3
"""
log_analysis.py - mechanical helpers for analyzing a promptkit run.

WHAT THIS SCRIPT IS FOR
=======================
Reading a run's raw logs is repetitive: inventory the round, triage exit
codes, grep signatures, extract per-prompt blocks. The judgement work
(deciding pass/fail, naming harms, walking R + S0-S11) stays with the
analyst. This script only does the mechanical extraction, so the analyst
sees consistent output every time and does not need to remember exact
grep patterns.

WHY IT EXISTS
=============
The process document (docs/audit/log_analysis/_plan.md) used to embed
the raw bash. This script replaces those blocks with named subcommands:
the doc points here, and this file is the single place where the grep
patterns live. When a new signature is discovered, it is added here
once, and every future run picks it up.

READ-ONLY BY DEFAULT
====================
Every subcommand reads files and prints to stdout. `walk-stub` is the
one exception - it creates a new findings/F-NNN.md from the README
template, and refuses if the file already exists.

USAGE
=====
    python scripts/log_analysis.py verify-round  20260925_150333
    python scripts/log_analysis.py exit-codes    20260925_150333
    python scripts/log_analysis.py signatures    20260925_150333 procurement_supplier
    python scripts/log_analysis.py classify      20260925_150333 procurement_supplier
    python scripts/log_analysis.py candidate-status 20260925_150333
    python scripts/log_analysis.py walk-stub     F-056
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path.cwd()
OVERNIGHTS = REPO / "overnights"
ANALYSIS = REPO / "docs/audit/log_analysis"
FINDINGS = REPO / "docs/audit/findings"

SIGNATURE_PATTERNS = [
    r"^ERROR:",
    r"^Reason:",
    r"Refusal",
    r"Traceback",
    r"KeyError",
    r"no plan",
    r"HDFE",
    r"finite",
    r"REFUSED \(planner guard\)",
    r"\[parse\] empty draft",
    r"'months': [0-9]*\.[0-9]+",
    r"'months': 0(?!\d)",
]

SET_TRIAD = ["smoke.log", "smoke.txt", "smoke_summary.log"]


def _die(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


def _round_root(run_id: str) -> Path:
    r = OVERNIGHTS / run_id
    if not r.is_dir():
        _die(f"round not found: {r}")
    return r


def cmd_verify_round(args) -> None:
    root = _round_root(args.run_id)
    top = ["_manifest.yaml", "_run_log.txt", "_summary.log"]
    print(f"# Round {args.run_id}")
    print()
    print("## Top-level files")
    for f in top:
        p = root / f
        mark = "ok" if p.is_file() else "MISSING"
        print(f"  {f:24} {mark}")
    print()
    print("## Sets")
    set_dirs = sorted(d for d in root.iterdir() if d.is_dir())
    print(f"  count: {len(set_dirs)}")
    print()
    print(f"  {'set':32}  smoke.log  smoke.txt  summary.log")
    for d in set_dirs:
        row = []
        for f in SET_TRIAD:
            p = d / f
            row.append("ok " if p.is_file() else "MISS")
        print(f"  {d.name:32}  {row[0]:9}  {row[1]:9}  {row[2]}")


def cmd_exit_codes(args) -> None:
    root = _round_root(args.run_id)
    summary = root / "_summary.log"
    if not summary.is_file():
        _die(f"no _summary.log in {root}")
    text = summary.read_text(errors="replace")
    rx = re.compile(r"(\S+)\s+.*exit=(\d+).*?(\d+)s?", re.IGNORECASE)
    print(f"# Exit codes - {args.run_id}")
    print()
    print(f"  {'set':32}  exit  secs")
    found = 0
    for line in text.splitlines():
        m = rx.search(line)
        if m:
            found += 1
            print(f"  {m.group(1):32}  {m.group(2):>4}  {m.group(3):>4}")
    if not found:
        print("  (no exit=N lines matched; dumping _summary.log raw)")
        print()
        print(text)


def cmd_signatures(args) -> None:
    root = _round_root(args.run_id)
    log = root / args.set / "smoke.log"
    if not log.is_file():
        _die(f"no smoke.log in {root / args.set}")
    text = log.read_text(errors="replace")
    print(f"# Signatures - {args.run_id}/{args.set}")
    print()
    print(f"  {'count':>5}  pattern")
    any_hit = False
    for pat in SIGNATURE_PATTERNS:
        n = len(re.findall(pat, text, re.MULTILINE))
        if n:
            any_hit = True
            print(f"  {n:>5}  {pat}")
    if not any_hit:
        print("  (no signature matched)")
    print()


def cmd_classify(args) -> None:
    root = _round_root(args.run_id)
    log = root / args.set / "smoke.log"
    if not log.is_file():
        _die(f"no smoke.log in {root / args.set}")
    lines = log.read_text(errors="replace").splitlines()
    print(f"# Per-prompt header - {args.run_id}/{args.set}")
    print()
    n = len(lines)
    i = 0
    while i < n:
        if lines[i].startswith("PROMPT: "):
            print("---")
            print(lines[i])
            for j in range(i + 1, min(i + 90, n)):
                l = lines[j]
                if l.startswith("Answer:"):
                    print(l)
                    if j + 1 < n:
                        nxt = lines[j + 1]
                        if not nxt.startswith(("PROMPT:", "Summary:", "===", "Truncation:")):
                            print(nxt[:200])
                    break
                if l.startswith("Reason:"):
                    print(l)
                    break
        i += 1


def cmd_candidate_status(args) -> None:
    root = ANALYSIS / args.run_id
    cand = root / "_candidates.md"
    if not cand.is_file():
        _die(f"no _candidates.md in {root}")
    text = cand.read_text()
    ids = re.findall(r"^## (C-\d+)", text, re.MULTILINE)
    statuses = re.findall(r"^- status:\s*(.+)$", text, re.MULTILINE)
    print(f"# Candidates - {args.run_id}")
    print(f"  count: {len(ids)}")
    print()
    for cid, status in zip(ids, statuses):
        print(f"  {cid}: {status.strip()[:90]}")


def cmd_walk_stub(args) -> None:
    fid = args.fid
    target = FINDINGS / f"{fid}.md"
    if target.exists():
        _die(f"{target} already exists")
    readme = FINDINGS / "README.md"
    if not readme.is_file():
        _die(f"no {readme}")
    text = readme.read_text()
    m = re.search(r"~~~markdown\n(.*?)\n~~~", text, re.DOTALL)
    if not m:
        _die("no ~~~markdown template block found in findings/README.md")
    body = m.group(1).replace("## F-NNN - {one-line title}",
                              f"## {fid} - {{one-line title}}")
    target.write_text(body + "\n", encoding="utf-8")
    print(f"wrote {target}")


def main() -> None:
    p = argparse.ArgumentParser(description="log analysis helpers")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("verify-round");       a.add_argument("run_id");                a.set_defaults(fn=cmd_verify_round)
    a = sub.add_parser("exit-codes");         a.add_argument("run_id");                a.set_defaults(fn=cmd_exit_codes)
    a = sub.add_parser("signatures");         a.add_argument("run_id"); a.add_argument("set"); a.set_defaults(fn=cmd_signatures)
    a = sub.add_parser("classify");           a.add_argument("run_id"); a.add_argument("set"); a.set_defaults(fn=cmd_classify)
    a = sub.add_parser("candidate-status");   a.add_argument("run_id");                a.set_defaults(fn=cmd_candidate_status)
    a = sub.add_parser("walk-stub");          a.add_argument("fid");                   a.set_defaults(fn=cmd_walk_stub)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
