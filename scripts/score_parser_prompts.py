#!/usr/bin/env python3
"""
score_parser_prompts.py — Run the parser-correctness stress set and report
where routing breaks. INTENT-ONLY: this runs the parser but only inspects the
parsed intent (target_entity, filters, count, aggregate, refusal). It does NOT
wait on slow per-supplier / aggregation execution — it reads the intent the
parser produced and moves on, so ~60 prompts run in a few minutes.

Usage:
    python scripts/score_parser_prompts.py
    python scripts/score_parser_prompts.py --file scripts/prompts/scorer/parser_stress.txt

Corpus format (per line):
    EXPECT=<what should happen> ||| <prompt>
    EXPECT=<what should happen> ||| MODULES=<subset> ||| <prompt>

MODULES selects which parser-context modules are assembled for that case:
    MODULES=procurement          -> Tier 1 (core + refusals) + procurement only
    MODULES=procurement,modes    -> Tier 1 + procurement + the modes concern
    MODULES absent               -> ALL blocks (the full-fidelity oracle)

FIDELITY CAVEAT (design §7.4): a MODULES=<subset> run DIAGNOSES which module
drives a behavior — a slim context can pass a case the full context fails.
Only the full assembly (MODULES absent) VERIFIES production-equivalent
behavior. Assert correctness on the full assembly; use subsets to bisect.

EXPECT values:
    target:<entity>     -> intent.target_entity == entity
    filter:<type>       -> intent carries this filter type
    combo:<a+b>         -> multiple filter types expected
    count               -> count_only=true
    aggregate           -> aggregate block set
    list_all            -> intent.list_all is true
    no_filters          -> intent has no filters (the dropped-id shape)
    refuse              -> an out-of-scope refusal (any flavor)
    refuse:<flavor>     -> a refusal with this specific flavor

The goal is to FIND FAILURES. Traps and refusals are the point, not noise.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from spire.nl_parser.parser import parse as parse_prompt
from spire.nl_parser.parser import _format_menu
from spire.nl_parser.vocabulary import load_kg_menu


DEFAULT_FILE = (
    Path(__file__).parent / "prompts" / "scorer" / "parser_stress.txt"
)

# The parser context lives next to parser.py. Tier 1 is always assembled.
_CONTEXT_DIR = (
    Path(__file__).resolve().parent.parent
    / "src" / "spire" / "nl_parser" / "context"
)
_TIER1 = ("core", "refusals")


# --- corpus parsing -------------------------------------------------------

def load_cases(path: Path):
    """Parse corpus lines into (expect, modules, prompt) tuples.

    A line has two or three '|||'-separated fields:
        EXPECT=... ||| prompt
        EXPECT=... ||| MODULES=a,b ||| prompt

    modules is a tuple of module names, or None when MODULES is absent
    (None => assemble everything, the fidelity oracle).
    """
    cases = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|||" not in line:
            continue

        parts = [p.strip() for p in line.split("|||")]
        expect = parts[0]
        if expect.upper().startswith("EXPECT="):
            expect = expect[len("EXPECT="):].strip()

        modules = None
        if len(parts) == 2:
            prompt = parts[1]
        elif len(parts) == 3:
            mid, prompt = parts[1], parts[2]
            if mid.upper().startswith("MODULES="):
                mods = mid[len("MODULES="):].strip()
                modules = tuple(
                    m.strip() for m in mods.split(",") if m.strip()
                )
            else:
                # middle field wasn't MODULES= — treat the whole tail as prompt
                prompt = "|||".join(parts[1:])
        else:
            # more than 3 fields: everything after the first is the prompt
            prompt = "|||".join(parts[1:])

        cases.append((expect, modules, prompt))
    return cases


# --- subset assembly (harness-only; production stays all-modules) ---------

def _manifest_blocks():
    """Ordered (module, relative_path) pairs from the context manifest."""
    manifest = _CONTEXT_DIR / "order.manifest"
    pairs = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        rel = line.strip()
        if rel:
            module = rel.split("/", 1)[0]  # first path component
            pairs.append((module, rel))
    return pairs


def assemble_subset(modules, menu) -> str | None:
    """Assemble a system prompt from Tier 1 + the named modules, + the menu.

    Returns None when modules is None, signalling the caller to let parse()
    build the full production preamble itself (the fidelity oracle path).

    The menu is appended exactly as production does it, so a subset differs
    from production ONLY in which preamble blocks are present.
    """
    if modules is None:
        return None

    wanted = set(_TIER1) | set(modules)
    parts = [
        (_CONTEXT_DIR / rel).read_text(encoding="utf-8")
        for module, rel in _manifest_blocks()
        if module in wanted
    ]
    return "".join(parts) + "\n" + _format_menu(menu)


# --- intent summarising + checking ----------------------------------------

def intent_summary(result):
    """Reduce a ParseResult to a comparable summary dict."""
    if result.is_refusal:
        return {"kind": "refuse", "detail": result.refusal.flavor.value}
    intent = result.intent
    ftypes = sorted(
        f.get("type") if isinstance(f, dict) else getattr(f, "type", None)
        for f in (intent.filters or [])
    )
    return {
        "kind": "intent",
        "target": getattr(intent, "target_entity", None),
        "filters": [f for f in ftypes if f],
        "count_only": getattr(intent, "count_only", False),
        "aggregate": getattr(intent, "aggregate", None) is not None,
        "list_all": getattr(intent, "list_all", False),
    }


def check(expect: str, summ: dict) -> bool:
    """Return True if the parsed summary satisfies the expectation."""
    # Refusal expectations first (they care about the refuse branch).
    if expect == "refuse":
        return summ["kind"] == "refuse"
    if expect.startswith("refuse:"):
        wanted_flavor = expect.split(":", 1)[1]
        return summ["kind"] == "refuse" and summ.get("detail") == wanted_flavor

    # Everything else expects a real intent; a refusal fails them.
    if summ["kind"] == "refuse":
        return False

    if expect == "count":
        return summ["count_only"]
    if expect == "aggregate":
        return summ["aggregate"]
    if expect == "list_all":
        return summ["list_all"]
    if expect == "no_filters":
        return not summ["filters"]
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

    for i, (expect, modules, prompt) in enumerate(cases, 1):
        try:
            system_prompt = assemble_subset(modules, menu)
            result = parse_prompt(
                prompt, menu=menu, system_prompt=system_prompt
            )
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
            failures.append((prompt, expect, modules, summ))

        mod_tag = "" if modules is None else f" [{','.join(modules)}]"
        print(f"[{mark}] {expect:<22}{mod_tag:<20} | {prompt[:50]}")

    print(f"\n{'='*70}\nSUMMARY: {passed}/{len(cases)} passed, "
          f"{failed} failed\n{'='*70}")
    if failures:
        print("\nFAILURES (where routing broke) — this is the finding:\n")
        for prompt, expect, modules, summ in failures:
            mod_tag = "all" if modules is None else ",".join(modules)
            print(f"  PROMPT:   {prompt}")
            print(f"  EXPECTED: {expect}   (modules: {mod_tag})")
            print(f"  GOT:      {summ}")
            print()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
