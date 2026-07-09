#!/usr/bin/env python3
"""
score_parser_stress.py — Run the parser-correctness stress set and report
where routing breaks. INTENT-ONLY: this runs the pipeline but only inspects
the parsed intent (target_entity, filters, count, aggregate, refusal). It does
NOT wait on the slow per-supplier / aggregation execution — it reads the intent
the parser produced and moves on, so ~60 prompts run in a few minutes.

Usage:
    python scripts/score_parser_stress.py
    python scripts/score_parser_stress.py --file scripts/01_test_prompts_parser.txt

Reads EXPECT=... ||| prompt lines. For each, runs parse only (via the graph's
parse node path) and checks the intent against the expectation. Prints a table
and a summary of failures — the failures ARE the finding.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from spire.nl_parser.parser import parse as parse_prompt
from spire.nl_parser.vocabulary import load_kg_menu


DEFAULT_FILE = Path(__file__).with_name("01_test_prompts_parser.txt")


def load_cases(path: Path):
    cases = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|||" not in line:
            continue
        expect, prompt = line.split("|||", 1)
        expect = expect.strip()
        if expect.upper().startswith("EXPECT="):
            expect = expect[len("EXPECT="):].strip()
        cases.append((expect.strip(), prompt.strip()))
    return cases


def intent_summary(result):
    """Reduce a ParseResult to a comparable summary dict."""
    if result.is_refusal:
        return {"kind": "refuse", "detail": result.refusal.flavor.value}
    intent = result.intent
    ftypes = sorted(f.get("type") if isinstance(f, dict) else getattr(f, "type", None)
                    for f in (intent.filters or []))
    return {
        "kind": "intent",
        "target": getattr(intent, "target_entity", None),
        "filters": [f for f in ftypes if f],
        "count_only": getattr(intent, "count_only", False),
        "aggregate": getattr(intent, "aggregate", None) is not None,
    }


def check(expect: str, summ: dict) -> bool:
    """Return True if the parsed summary satisfies the expectation."""
    if expect == "refuse":
        return summ["kind"] == "refuse"
    if summ["kind"] == "refuse":
        return False  # expected something, got a refusal
    if expect == "count":
        return summ["count_only"]
    if expect == "aggregate":
        return summ["aggregate"]
    if expect.startswith("target:"):
        return summ["target"] == expect.split(":", 1)[1]
    if expect.startswith("filter:"):
        return expect.split(":", 1)[1] in summ["filters"]
    if expect.startswith("combo:"):
        wanted = expect.split(":", 1)[1].split("+")
        return all(w in summ["filters"] for w in wanted)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=Path, default=DEFAULT_FILE)
    args = ap.parse_args()

    cases = load_cases(args.file)
    print(f"Loaded {len(cases)} cases from {args.file.name}.\n")
    menu = load_kg_menu()

    passed, failed = 0, 0
    failures = []

    for i, (expect, prompt) in enumerate(cases, 1):
        try:
            result = parse_prompt(prompt, menu=menu)
            summ = intent_summary(result)
            ok = check(expect, summ)
        except Exception as exc:
            summ = {"kind": "error", "detail": str(exc)}
            ok = False

        mark = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
            got = (summ.get("filters") or summ.get("kind"))
            failures.append((prompt, expect, got, summ))
        print(f"[{mark}] {expect:<28} | {prompt[:55]}")

    print(f"\n{'='*70}\nSUMMARY: {passed}/{len(cases)} passed, {failed} failed\n{'='*70}")
    if failures:
        print("\nFAILURES (where routing broke) — this is the finding:\n")
        for prompt, expect, got, summ in failures:
            print(f"  PROMPT:   {prompt}")
            print(f"  EXPECTED: {expect}")
            print(f"  GOT:      {summ}")
            print()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
