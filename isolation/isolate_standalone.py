#!/usr/bin/env python3
"""
FULLY STANDALONE S1 isolation — NO spire imports.

Reproduces the two Gemini round-trips Spire makes for one prompt, but with
ZERO dependency on the spire package. The two system prompts are read from
plain text files next to this script:

    classify_system.txt   — ROUND 1 system prompt (router/classifier)
    parse_system.txt      — ROUND 2 system prompt (parser, scoped to
                            [procurement, supplier]) — frozen verbatim

The two structured-output schemas (ModuleChoice, DraftIntent) are defined
INLINE here, copied field-for-field from spire so with_structured_output
behaves identically. Nothing else from spire is needed.

Only external deps: langchain_google_genai + pydantic (to talk to Gemini).
Auth: whatever the Gemini client already uses in your environment
(GOOGLE_API_KEY / Vertex ADC). Same as Spire.

USAGE
    # single prompt, prints both round-trips
    python isolate_standalone.py "Show supplier details for PO 701337."

    # dump the full parse context too
    python isolate_standalone.py "PROMPT" --dump-context

    # run N times and tally crash-vs-refuse (the 30/70 flip)
    python isolate_standalone.py "PROMPT" --n 10

    # read prompts from a file, one per line (# comments allowed), each --n times
    python isolate_standalone.py --prompts-file prompts.txt --n 5

    # point at different model / prompt files
    python isolate_standalone.py "PROMPT" --model gemini-3.5-flash \
        --classify-file classify_system.txt --parse-file parse_system.txt

Everything prints to stdout — tee it:
    python isolate_standalone.py "PROMPT" --dump-context 2>&1 | tee out.txt
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, Field

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    sys.exit(
        "Missing dep: pip install langchain-google-genai\n"
        "(this is the only thing needed to reach Gemini; no spire required)."
    )


# ---------------------------------------------------------------------------
# Config — mirrors spire/config.py values, inline (no import).
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "gemini-3.5-flash"
TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 8000

HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# ROUND 1 schema — copied verbatim from spire/nl_parser/router.py ModuleChoice
# ---------------------------------------------------------------------------
class ModuleChoice(BaseModel):
    """The classifier's structured output: which Fusion module(s) a prompt
    targets. A list even for one module."""

    modules: list[str] = Field(
        description=(
            "The Fusion module(s) this question targets, chosen from: "
            "payables, procurement, receivables, supplier. Return the single "
            "best module for a question about one area; the value is a list "
            "for forward-compatibility. Choose the module whose entities or "
            "their synonyms the question names."
        )
    )


# ---------------------------------------------------------------------------
# ROUND 2 schema — copied from spire/nl_parser/draft.py (DraftFilter +
# DraftIntent). Aggregate/compare blocks are simplified to dicts here since
# they are irrelevant to the supplier-include reproduction; every field the
# parser fills on this path is present and named identically.
# ---------------------------------------------------------------------------
class DraftFilter(BaseModel):
    type: str = Field(description="The filter type, e.g. 'country'.")
    value_json: str = Field(
        description=(
            "The filter's value, encoded as a JSON string. Use a JSON string "
            'for text (e.g. "\\"US\\""), a JSON bool for presence flags '
            '(e.g. "true"), or a JSON object for parameterized filters '
            '(e.g. "{\\"months\\": 6}").'
        )
    )


class DraftIntent(BaseModel):
    """Mirror of spire's DraftIntent — the fields the parser fills."""

    unanswerable: bool = Field(
        default=False,
        description=(
            "Set true when the question needs an entity or filter that is "
            "not supported, or is too vague to pin down. When true, do NOT "
            "guess a target_entity or map the request to the closest listed "
            "entity; leave the other fields at their defaults and explain in "
            "unanswerable_reason. If the entity and filters are supported but "
            "the question also asks for columns that are not listed, the "
            "question IS answerable: set unanswerable=false, fill "
            "target_entity and filters normally, and put ALL requested "
            "columns in `fields`."
        ),
    )
    unanswerable_reason: str = Field(
        default="",
        description=(
            "When unanswerable is true, a brief plain statement of what the "
            "system cannot do. Empty string when unanswerable is false."
        ),
    )
    unanswerable_kind: str = Field(
        default="",
        description=(
            "When unanswerable is true, WHICH KIND of unanswerable. Exactly "
            "one of: unknown_entity, unsupported_filter, unsupported_field, "
            "unsupported_operation, missing_identifier, unparseable."
        ),
    )
    unanswerable_entity: str = Field(
        default="",
        description=(
            "When unanswerable is true, the record type the question is "
            "about, if identifiable. Descriptive only; does NOT change "
            "target_entity (which stays empty when unanswerable is true)."
        ),
    )
    target_entity: str = Field(
        default="",
        description=(
            "The ONE entity the question is rooted on. Empty when "
            "unanswerable is true."
        ),
    )
    filters: list[DraftFilter] = Field(
        default_factory=list,
        description="Zero or more filters constraining the target entity.",
    )
    include: list[str] = Field(
        default_factory=list,
        description="Related entities to fetch alongside (e.g. 'Buyer').",
    )
    fields: list[str] = Field(
        default_factory=list,
        description="Specific columns the question asks to see.",
    )
    # Present so the schema matches; irrelevant to this reproduction.
    count_only: bool = Field(default=False, description="Count instead of list.")
    open_only: bool = Field(default=False, description="Only open records.")
    balance_only: bool = Field(default=False, description="Balance only.")


SEP = "=" * 78


def banner(title: str) -> None:
    print(f"\n{SEP}\n{title}\n{SEP}")


def build_llm(model: str) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=model, temperature=TEMPERATURE, max_output_tokens=MAX_OUTPUT_TOKENS
    )


def read_prompt_file(path: Path) -> str:
    if not path.is_file():
        sys.exit(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def classify(prompt: str, system_text: str, llm, show: bool) -> list[str]:
    if show:
        banner("ROUND 1 — CLASSIFY :: SYSTEM PROMPT (from classify_system.txt)")
        print(system_text)
        banner("ROUND 1 — CLASSIFY :: HUMAN PROMPT")
        print(prompt)
        banner("ROUND 1 — CLASSIFY :: EXPECTED SHAPE")
        print('ModuleChoice: {"modules": [subset of payables/procurement/'
              'receivables/supplier]}')

    structured = llm.with_structured_output(ModuleChoice, include_raw=True)
    result = structured.invoke([("system", system_text), ("human", prompt)])
    parsed = result.get("parsed") if isinstance(result, dict) else result
    raw = result.get("raw") if isinstance(result, dict) else None
    modules = list(getattr(parsed, "modules", []) or []) if parsed else []

    if show:
        banner("ROUND 1 — CLASSIFY :: ACTUAL REPLY")
        print(f"modules = {modules}")
        if raw is not None:
            um = getattr(raw, "usage_metadata", {}) or {}
            print(f"(tokens in={um.get('input_tokens')} out={um.get('output_tokens')})")
    return modules


def parse(prompt: str, system_text: str, llm, show: bool, dump_context: bool):
    if show:
        banner("ROUND 2 — PARSE :: SYSTEM PROMPT (from parse_system.txt)")
        print(f"[{len(system_text):,} chars]")
        if dump_context:
            print("-" * 78)
            print(system_text)
        else:
            print("(re-run with --dump-context to print it in full)")
        banner("ROUND 2 — PARSE :: HUMAN PROMPT")
        print(prompt)
        banner("ROUND 2 — PARSE :: EXPECTED SHAPE")
        print("DraftIntent — target_entity, filters[], include[], fields[], "
              "or unanswerable=True with reason/kind.")

    structured = llm.with_structured_output(DraftIntent, include_raw=True)
    result = structured.invoke([("system", system_text), ("human", prompt)])
    parsed = result.get("parsed") if isinstance(result, dict) else result
    raw = result.get("raw") if isinstance(result, dict) else None
    if isinstance(parsed, dict):
        parsed = DraftIntent(**parsed)

    if show:
        banner("ROUND 2 — PARSE :: ACTUAL REPLY (DraftIntent)")
        if parsed is None:
            print("parsed = None (degenerate / no structured intent)")
        else:
            print(f"target_entity     = {parsed.target_entity!r}")
            print(f"include           = {parsed.include!r}")
            print(f"filters           = {[ (f.type, f.value_json) for f in parsed.filters ]!r}")
            print(f"fields            = {parsed.fields!r}")
            print(f"unanswerable      = {parsed.unanswerable!r}")
            print(f"unanswerable_kind = {parsed.unanswerable_kind!r}")
            print(f"unanswerable_reason = {parsed.unanswerable_reason!r}")
        if raw is not None:
            um = getattr(raw, "usage_metadata", {}) or {}
            fr = getattr(raw, "response_metadata", {}).get("finish_reason")
            print(f"(tokens in={um.get('input_tokens')} out={um.get('output_tokens')} "
                  f"finish={fr})")
    return parsed


def bucket(parsed) -> str:
    if parsed is None:
        return "NONE (degenerate)"
    tgt, inc = parsed.target_entity, list(parsed.include or [])
    if tgt == "PurchaseOrder" and "Supplier" in inc:
        return "PO_ROOT+include:Supplier (CRASH path)"
    if parsed.unanswerable:
        return f"unanswerable ({parsed.unanswerable_kind or '?'}) — clean refuse"
    return f"OTHER (target={tgt!r}, include={inc})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt", nargs="?", help="the question (or use --prompts-file)")
    ap.add_argument("--prompts-file", help="text file of prompts, one per line")
    ap.add_argument("--classify-file", default="classify_system.txt")
    ap.add_argument("--parse-file", default="parse_system.txt")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--dump-context", action="store_true")
    ap.add_argument("--n", type=int, default=1, help="runs per prompt")
    args = ap.parse_args()

    classify_text = read_prompt_file(HERE / args.classify_file)
    parse_text = read_prompt_file(HERE / args.parse_file)
    llm = build_llm(args.model)

    # Collect prompts.
    prompts: list[str] = []
    if args.prompts_file:
        for line in read_prompt_file(Path(args.prompts_file)).splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                prompts.append(s)
    elif args.prompt:
        prompts = [args.prompt]
    else:
        sys.exit("Give a PROMPT argument or --prompts-file.")

    for prompt in prompts:
        if args.n == 1 and len(prompts) == 1:
            # Verbose single run: show both round-trips in full.
            mods = classify(prompt, classify_text, llm, show=True)
            if not mods:
                print("\n[stop] classifier returned nothing.")
                return 0
            parsed = parse(prompt, parse_text, llm, show=True,
                           dump_context=args.dump_context)
            banner("OUTCOME")
            print(f"modules={mods} -> {bucket(parsed)}")
        else:
            # Distribution mode: quiet, tally per prompt.
            banner(f"PROMPT: {prompt!r}  (n={args.n})")
            tally: Counter[str] = Counter()
            for i in range(1, args.n + 1):
                mods = classify(prompt, classify_text, llm, show=False)
                parsed = parse(prompt, parse_text, llm, show=False,
                               dump_context=False) if mods else None
                b = bucket(parsed)
                tally[b] += 1
                print(f"  run {i:>2}: modules={mods} -> {b}")
            print("  --- tally ---")
            for k, v in tally.most_common():
                print(f"    {v:>3}/{args.n}  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
