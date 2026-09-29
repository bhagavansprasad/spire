#!/usr/bin/env python3
"""
log_analysis.py - mechanical helpers for analyzing a promptkit run.

PURPOSE
=======
A starting assistant, not a bug-finder. It surfaces the material a
developer needs to begin and continue an investigation - errors,
exceptions, refusals, signatures, exit codes, per-prompt heads -
and hands it over. Its output is not expected to be identical
across rounds, even on the same tier: two smoke rounds with
different failures should read differently, because the logs
differ. It is not expected to find every bug; it is expected to
point at where the investigation should start.

WHAT THIS SCRIPT IS FOR
=======================
Reading a run's raw logs is repetitive: inventory the round, triage exit
codes, grep signatures, extract per-prompt blocks. The judgement work
(deciding pass/fail, naming harms, walking R + S0-S11) stays with the
analyst. This script only does the mechanical extraction, so the analyst
sees consistent output every time and does not need to remember exact
grep patterns.

TIER DERIVATION
===============
Every promptkit run declares its sets in a frozen _manifest.yaml at the
round root. Each set name is "<folder>/<tier>". The tier is the basename
- smoke, verify, or exhaust. This script reads that manifest and derives
the tier; it does not hardcode any tier name. The three per-set files
are:

    <tier>.log              the raw run log
    <tier>.txt              the input copy that this run consumed
    <folder>_summary.log    the per-folder summary

All three are named after the manifest entry, not after the script's
assumptions.

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

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

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


def _die(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


def _load_manifest_sets(root: Path) -> list[str]:
    """Read the frozen _manifest.yaml at the round root, return its sets."""
    mpath = root / "_manifest.yaml"
    if not mpath.is_file():
        _die(f"no _manifest.yaml in {root}")
    text = mpath.read_text(encoding="utf-8")
    if yaml is not None:
        doc = yaml.safe_load(text)
        if not isinstance(doc, dict) or "sets" not in doc:
            _die(f"_manifest.yaml in {root} has no 'sets:' key")
        sets = doc["sets"]
        if not isinstance(sets, list) or not sets:
            _die(f"_manifest.yaml in {root} has an empty 'sets:' list")
        return [str(s) for s in sets]
    # PyYAML absent: the manifest shape is fixed and simple, parse it by hand.
    names = re.findall(r"^\s*-\s*(\S+)\s*$", text, re.MULTILINE)
    if not names:
        _die(f"could not parse 'sets:' from {mpath} (PyYAML unavailable)")
    return names


def _tier_from_sets(names: list[str]) -> str:
    """Derive the single tier from the set basenames. Fail if mixed or empty."""
    basenames = set()
    for n in names:
        basenames.add(n.rsplit("/", 1)[1] if "/" in n else n)
    if not basenames:
        _die("no sets in manifest; cannot derive a tier")
    if len(basenames) != 1:
        _die(
            "cannot derive a single tier from the manifest; "
            f"set basenames are {sorted(basenames)}"
        )
    return basenames.pop()


def _round_context(run_id: str) -> tuple[Path, list[str], str]:
    """Return (round_root, set_names, tier). Single source for every subcommand."""
    root = OVERNIGHTS / run_id
    if not root.is_dir():
        _die(f"round not found: {root}")
    names = _load_manifest_sets(root)
    tier = _tier_from_sets(names)
    return root, names, tier


def _folder_for(set_name: str) -> str:
    return set_name.rsplit("/", 1)[0] if "/" in set_name else set_name


def _summary_name_for(set_name: str) -> str:
    return f"{Path(_folder_for(set_name)).name}_summary.log"


def cmd_verify_round(args) -> None:
    root, names, tier = _round_context(args.run_id)
    top = ["_manifest.yaml", "_run_log.txt", "_summary.log"]
    print(f"# Round {args.run_id}   (tier: {tier})")
    print()
    print("## Top-level files")
    for f in top:
        p = root / f
        mark = "ok" if p.is_file() else "MISSING"
        print(f"  {f:24} {mark}")
    print()
    print("## Sets")
    print(f"  count (manifest): {len(names)}")
    manifest_folders = sorted({_folder_for(n) for n in names})
    on_disk = sorted(d.name for d in root.iterdir() if d.is_dir())
    if on_disk != manifest_folders:
        print("  WARNING: on-disk folders differ from manifest")
        print(f"    manifest: {manifest_folders}")
        print(f"    on-disk:  {on_disk}")
    print()
    log_col = f"{tier}.log"
    txt_col = f"{tier}.txt"
    print(f"  {'set':32}  {log_col:12}  {txt_col:12}  summary.log")
    for name in names:
        d = root / _folder_for(name)
        row = []
        for f in (log_col, txt_col, _summary_name_for(name)):
            row.append("ok " if (d / f).is_file() else "MISS")
        print(f"  {name:32}  {row[0]:12}  {row[1]:12}  {row[2]}")


def cmd_exit_codes(args) -> None:
    root, _names, _tier = _round_context(args.run_id)
    summary = root / "_summary.log"
    if not summary.is_file():
        _die(f"no _summary.log in {root}")
    text = summary.read_text(errors="replace")
    # _write_summaries in promptkit.py writes bare columns:
    #     <set>   <exit>   <secs>   <status>
    # Match: name, then an integer, then an integer, then whitespace.
    rx = re.compile(r"^\s*(\S+)\s+(\d+)\s+(\d+)\s+", re.MULTILINE)
    print(f"# Exit codes - {args.run_id}")
    print()
    print(f"  {'set':32}  exit  secs")
    found = 0
    for line in text.splitlines():
        m = rx.match(line)
        if m:
            found += 1
            print(f"  {m.group(1):32}  {m.group(2):>4}  {m.group(3):>4}")
    if not found:
        print("  (no exit rows matched; dumping _summary.log raw)")
        print()
        print(text)


def cmd_signatures(args) -> None:
    root, _names, tier = _round_context(args.run_id)
    log = root / args.set / f"{tier}.log"
    if not log.is_file():
        _die(f"no {tier}.log in {root / args.set}")
    text = log.read_text(errors="replace")
    print(f"# Signatures - {args.run_id}/{args.set}   (tier: {tier})")
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
    root, _names, tier = _round_context(args.run_id)
    log = root / args.set / f"{tier}.log"
    if not log.is_file():
        _die(f"no {tier}.log in {root / args.set}")
    lines = log.read_text(errors="replace").splitlines()
    print(f"# Per-prompt header - {args.run_id}/{args.set}   (tier: {tier})")
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
