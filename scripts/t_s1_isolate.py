#!/usr/bin/env python3
"""
S1 isolation harness — the TWO LLM round-trips, laid bare.

This reproduces exactly what Spire sends to Gemini for a single prompt,
using Spire's OWN functions (no reconstruction), and prints every piece:

  ROUND 1 (classify): system prompt + human prompt -> ModuleChoice
  ROUND 2 (parse):    scoped system prompt + human prompt -> DraftIntent/Intent

It bypasses the executor, synthesizer, and pipeline — just the two model
calls — so you can see the raw inputs/outputs and loop it to watch the
non-deterministic parse flip (PurchaseOrder+include:Supplier -> crash vs
Supplier-rooted -> clean refuse).

Usage:
    python scripts/t_s1_isolate.py "Show supplier details for PO 701337."
    python scripts/t_s1_isolate.py "Show supplier details for PO 701337." --dump-context
    python scripts/t_s1_isolate.py "PROMPT" --n 10          # loop N times, bucket outcomes

Everything prints to stdout; tee it:
    python scripts/t_s1_isolate.py "PROMPT" --dump-context 2>&1 | tee t.txt

Throwaway diagnostic — not committed.
"""
from __future__ import annotations

import argparse
import sys

# --- Spire's real building blocks (the exact ones parse()/classify use) ---
from spire.config import build_llm
from spire.nl_parser.context_assembly import (
    KNOWN_MODULES,
    _CLASSIFIER_MENU,
    assemble_subset,
)
from spire.nl_parser.router import (
    ModuleChoice,
    _classifier_system_prompt,
    classify_modules,
)
from spire.nl_parser.draft import DraftIntent
from spire.nl_parser.vocabulary import load_kg_menu


SEP = "=" * 78


def banner(title: str) -> None:
    print(f"\n{SEP}\n{title}\n{SEP}")


def round1_classify(prompt: str, menu_text: str, llm) -> list[str]:
    """ROUND 1: the classify call, shown fully.

    Answers your Q1/Q2/Q3:
      Q1 what we send  = system (instruction+menu) + human (prompt)
      Q2 what we get   = a ModuleChoice (list of modules)
      Q3 what expected = 1+ names drawn from KNOWN_MODULES
    """
    system_prompt = _classifier_system_prompt(menu_text)

    banner("ROUND 1 — CLASSIFY :: SYSTEM PROMPT (context sent to LLM)")
    print(system_prompt)

    banner("ROUND 1 — CLASSIFY :: HUMAN PROMPT (your question, verbatim)")
    print(prompt)

    banner("ROUND 1 — CLASSIFY :: EXPECTED OUTPUT SHAPE")
    print("A ModuleChoice: {\"modules\": [<subset of "
          f"{list(KNOWN_MODULES)}>]}}")

    # Call exactly as classify_modules does (structured output).
    structured = llm.with_structured_output(ModuleChoice, include_raw=True)
    result = structured.invoke(
        [("system", system_prompt), ("human", prompt)]
    )
    parsed = result.get("parsed") if isinstance(result, dict) else result
    raw = result.get("raw") if isinstance(result, dict) else None

    banner("ROUND 1 — CLASSIFY :: ACTUAL REPLY")
    if parsed is None:
        print("parsed = None (model produced no parseable ModuleChoice)")
        modules: list[str] = []
    else:
        modules = list(getattr(parsed, "modules", []) or [])
        print(f"ModuleChoice.modules = {modules}")
    if raw is not None:
        um = getattr(raw, "usage_metadata", {}) or {}
        print(f"(tokens: in={um.get('input_tokens')} out={um.get('output_tokens')})")

    return modules


def round2_parse(prompt: str, modules: list[str], menu, llm,
                 dump_context: bool):
    """ROUND 2: the parse call, shown fully.

    Answers your Q4/Q5/Q6/Q7/Q8:
      Q4/Q7 which bucket -> what prompt = scoped context for `modules`
      Q5    context sent = assemble_subset(modules, menu)  (the real bytes)
      Q6/Q8 expected     = a DraftIntent (target_entity, filters, include, ...)
    """
    # This is EXACTLY what route_and_parse builds for the parse call:
    # the scoped subset for the classified modules (Tier1 core + those
    # modules' blocks + the KG menu).
    scoped = assemble_subset(modules, menu)

    banner(f"ROUND 2 — PARSE :: SCOPED CONTEXT for modules={modules}")
    if scoped is None:
        print("(assemble_subset returned None -> full preamble would be used)")
    else:
        print(f"[scoped system prompt is {len(scoped):,} chars]")
        if dump_context:
            print("-" * 78)
            print(scoped)
        else:
            print("(re-run with --dump-context to print the full scoped prompt)")

    banner("ROUND 2 — PARSE :: HUMAN PROMPT (your question, verbatim)")
    print(prompt)

    banner("ROUND 2 — PARSE :: EXPECTED OUTPUT SHAPE")
    print("A DraftIntent — target_entity, filters[], include[], fields[], "
          "aggregate/compare/flags, or unanswerable=True with a reason.")

    structured = llm.with_structured_output(DraftIntent, include_raw=True)
    result = structured.invoke(
        [("system", scoped), ("human", prompt)]
    )
    parsed = result.get("parsed") if isinstance(result, dict) else result
    raw = result.get("raw") if isinstance(result, dict) else None

    banner("ROUND 2 — PARSE :: ACTUAL REPLY (the DraftIntent)")
    if parsed is None:
        print("parsed = None (degenerate / no structured intent)")
    else:
        if isinstance(parsed, dict):
            parsed = DraftIntent(**parsed)
        # Print the fields that decide the crash: target_entity + include.
        print(f"target_entity     = {getattr(parsed, 'target_entity', None)!r}")
        print(f"include           = {getattr(parsed, 'include', None)!r}")
        print(f"filters           = {getattr(parsed, 'filters', None)!r}")
        print(f"fields            = {getattr(parsed, 'fields', None)!r}")
        print(f"unanswerable      = {getattr(parsed, 'unanswerable', None)!r}")
        print(f"unanswerable_kind = {getattr(parsed, 'unanswerable_kind', None)!r}")
        print("\n--- full DraftIntent ---")
        print(parsed)
    if raw is not None:
        um = getattr(raw, "usage_metadata", {}) or {}
        fr = getattr(raw, "response_metadata", {}).get("finish_reason")
        print(f"\n(tokens: in={um.get('input_tokens')} out={um.get('output_tokens')}"
              f"  finish_reason={fr})")

    return parsed


def one_pass(prompt: str, menu, llm, dump_context: bool):
    modules = round1_classify(prompt, _CLASSIFIER_MENU, llm)
    if not modules:
        print("\n[stop] classifier returned nothing; not proceeding to parse.")
        return "NO_MODULES", modules, None
    parsed = round2_parse(prompt, modules, menu, llm, dump_context)
    # Bucket the outcome by the crash-deciding fields.
    tgt = getattr(parsed, "target_entity", None) if parsed else None
    inc = list(getattr(parsed, "include", []) or []) if parsed else []
    unans = getattr(parsed, "unanswerable", None) if parsed else None
    if tgt == "PurchaseOrder" and any(i == "Supplier" for i in inc):
        outcome = "PO_ROOT_INCLUDE_SUPPLIER (would crash today)"
    elif unans:
        outcome = "UNANSWERABLE (clean refuse)"
    else:
        outcome = f"OTHER (target={tgt!r}, include={inc})"
    return outcome, modules, parsed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt", help="the natural-language question")
    ap.add_argument("--dump-context", action="store_true",
                    help="print the FULL scoped parse context (large)")
    ap.add_argument("--n", type=int, default=1,
                    help="run N times and bucket outcomes (default 1)")
    args = ap.parse_args()

    menu = load_kg_menu()
    llm = build_llm()

    if args.n == 1:
        outcome, modules, _ = one_pass(args.prompt, menu, llm, args.dump_context)
        banner("OUTCOME")
        print(f"modules={modules}  ->  {outcome}")
        return 0

    # N-run distribution mode: quiet per-run, tally at the end.
    banner(f"DISTRIBUTION over {args.n} runs — prompt: {args.prompt!r}")
    from collections import Counter
    tally: Counter[str] = Counter()
    for i in range(1, args.n + 1):
        modules = classify_modules(args.prompt, menu_text=_CLASSIFIER_MENU)
        scoped = assemble_subset(modules, menu)
        structured = llm.with_structured_output(DraftIntent, include_raw=True)
        result = structured.invoke([("system", scoped), ("human", args.prompt)])
        parsed = result.get("parsed") if isinstance(result, dict) else result
        if isinstance(parsed, dict):
            parsed = DraftIntent(**parsed)
        tgt = getattr(parsed, "target_entity", None) if parsed else None
        inc = list(getattr(parsed, "include", []) or []) if parsed else []
        unans = getattr(parsed, "unanswerable", None) if parsed else None
        if tgt == "PurchaseOrder" and "Supplier" in inc:
            key = "PO_ROOT+include:Supplier (CRASH)"
        elif unans:
            key = "unanswerable (clean refuse)"
        else:
            key = f"OTHER target={tgt}"
        tally[key] += 1
        print(f"  run {i:>2}: modules={modules} -> {key}")
    banner("TALLY")
    for k, v in tally.most_common():
        print(f"  {v:>3}/{args.n}  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
