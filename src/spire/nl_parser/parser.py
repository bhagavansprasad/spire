"""
The NL parser — natural-language prompt to ``Intent`` (feature 1).

This is the interpreter stage of the Design 3 pipeline:

    Prompt -> [parser: LLM] -> Intent -> planner -> executor -> synthesizer

See docs/designs/feature_1_nl_parser_design.md. The parser is modeled on the
synthesizer: a single bounded LLM call with structured output, plus
validation. It owns its KG access via the planner's synchronous path.

CHECKPOINT SCOPE:
This module covers prompt-building, the LLM call, draft production, and the
two-way KG validation of the draft (Q2 direction 2). The LLM emits a
``DraftIntent`` (Pydantic), which is converted to the planner's ``Intent`` and
then validated against the KG menu: out-of-scope entities/filters become typed
refusals (UNKNOWN_ENTITY / UNSUPPORTED_OPERATION / UNSUPPORTED_FILTER); wholly
unparseable output becomes UNPARSEABLE. The pipeline gate (Q5: stop before
planning on a refusal) is the remaining integration step.

LLM INJECTION (Q4):
``parse`` takes an optional ``llm``. Tests inject a mock that returns a canned
``DraftIntent``; production passes None and a real Gemini client is built —
same convention as the synthesizer.
"""

from __future__ import annotations

from typing import Any

from spire.config import GEMINI_MODEL, GEMINI_TEMPERATURE, LLM_MAX_OUTPUT_TOKENS
from spire.nl_parser.capability import derive_flavor
from spire.nl_parser.draft import DraftIntent
from spire.nl_parser.result import ParseResult, RefusalFlavor
from spire.nl_parser.intent_validation import validate_intent
from spire.nl_parser.vocabulary import (
    expand_field_synonyms,
    correct_include_from_prompt,
)
from spire.nl_parser.vocabulary import KGMenu, load_kg_menu

from spire.nl_parser.context_assembly import _build_system_prompt

from pathlib import Path


# Model and determinism come from spire.config (single source of truth).
_MODEL_NAME = GEMINI_MODEL
_TEMPERATURE = GEMINI_TEMPERATURE


import re

# #32 fault (b): the signal that tells an explicit "list purchase orders"
# request (a valid bounded sample-and-disclose, #23) apart from a PO query
# whose identifier the parser dropped ("Is PO N complete?" losing the
# number, #32). Both produce a filter-less PurchaseOrder intent, but only
# the explicit list should list; the dropped-identifier case must refuse.
#
# This is computed DETERMINISTICALLY in Python from the raw prompt, AFTER
# the LLM parse and with ZERO LLM-visible text — the parser prompt is at
# its token ceiling and any added prompt/schema text tips specific
# phrasings into degenerate (MAX_TOKENS) generation. A post-parse string
# check sidesteps that entirely. Same code-side, prompt-untouched pattern
# as expand_field_synonyms / correct_include_from_prompt in parse().

# A PO number token: a run of digits, optionally with a letter prefix like
# "US164932". Used to DISQUALIFY a "list" phrasing that actually names one
# PO ("list the lines on PO 2144") — that is not a bare list-all request.
_PO_NUMBER_RE = re.compile(r"\bpo\s*[#:]?\s*[a-z]*\d+\b", re.IGNORECASE)
# A bare number that isn't obviously a year — a weak signal a specific
# record is named. Kept conservative: only digit runs of 3+.
_BARE_NUMBER_RE = re.compile(r"\b\d{3,}\b")

_LIST_VERBS = (
    "list ",
    "show all",
    "show me all",
    "all purchase orders",
    "every purchase order",
)


def _is_explicit_po_list(prompt: str) -> bool:
    """True when the prompt is an explicit "list all purchase orders" request.

    Deterministic, raw-prompt-string only — no LLM, no prompt/schema text.
    Requires BOTH a generic purchase-order mention AND a list/show-all verb,
    AND that the prompt does NOT name a specific PO. The last clause is what
    keeps "list the lines on PO 2144" (names one PO) from counting as a
    list-all request. Scoped by the caller to PurchaseOrder-rooted intents.
    """
    p = prompt.lower().strip()

    # Must mention purchase orders generically ("purchase order(s)" or a
    # standalone "pos"/"po"). A bare "po" only counts as a word, so
    # "deposit" or "position" don't trip it.
    tokens = p.replace("?", " ").replace(",", " ").split()
    mentions_pos = (
        "purchase order" in p
        or "purchase orders" in p
        or "pos" in tokens
        or "po" in tokens
    )
    if not mentions_pos:
        return False

    # Must carry a list/show-all verb.
    has_list_verb = any(v in p for v in _LIST_VERBS)
    if not has_list_verb:
        return False

    # Must NOT name a specific PO. If a PO number is present, this is a
    # question about one order, not a bare list — even if it says "list".
    if _PO_NUMBER_RE.search(p):
        return False
    # A stray 3+ digit run that isn't a plausible year (2000–2099) is also
    # a specific-record signal; be conservative and disqualify.
    for m in _BARE_NUMBER_RE.finditer(p):
        n = m.group()
        if not (len(n) == 4 and n.startswith("20")):
            return False

    return True


def parse(
    prompt: str,
    llm: Any | None = None,
    menu: KGMenu | None = None,
    system_prompt: str | None = None,
) -> ParseResult:
    """Parse a natural-language prompt into a ParseResult.

    Args:
        prompt: The user's natural-language question.
        llm: Optional pre-built LangChain LLM. Tests inject a mock whose
            ``with_structured_output(DraftIntent).invoke(...)`` returns a
            canned DraftIntent (or dict). Production passes None and a fresh
            ChatGoogleGenerativeAI is built (reads GEMINI_API_KEY).
        menu: Optional pre-loaded KGMenu. Tests pass a fixture to avoid a DB
            hit; production passes None and the menu is read synchronously
            from the KG via load_kg_menu().

    Returns:
        ParseResult — ``ok`` wrapping an Intent when the LLM produced a
        shape-valid draft, or a ``refuse`` with flavor UNPARSEABLE when the
        LLM produced nothing usable or a malformed value.

        NOTE (checkpoint 2): a shape-valid draft is NOT yet validated against
        the KG. Entity/filter KG-checks (and their UNKNOWN_ENTITY /
        UNSUPPORTED_FILTER / UNSUPPORTED_OPERATION refusals) arrive in
        checkpoint 3.
    """
    if menu is None:
        menu = load_kg_menu()

    if llm is None:
        # Imported lazily so unit tests (which inject a mock) don't require
        # an LLM dep or API key to import this module. build_llm picks the
        # configured provider (gemini today).
        from spire.config import build_llm

        llm = build_llm(_TEMPERATURE)

    structured_llm = llm.with_structured_output(DraftIntent, include_raw=True)
    if system_prompt is None:
        system_prompt = _build_system_prompt(menu)

    result = structured_llm.invoke(
        [("system", system_prompt), ("human", prompt)]
    )

    # With include_raw=True the real LLM returns
    # {"raw": AIMessage, "parsed": DraftIntent|None, "parsing_error": ...}.
    # Unit tests inject a mock that returns the bare model (or a dict);
    # handle both so token logging never breaks the mock path.
    if isinstance(result, dict) and "parsed" in result:
        from spire.config import log_usage
        from pathlib import Path
        import time

        log_usage(result.get("raw"), stage="parse")

        # --- Guard: degenerate parse (runaway / non-stop) ---
        raw = result.get("raw")
        if raw is not None:
            usage = getattr(raw, "usage_metadata", {})
            out_tokens = usage.get("output_tokens", 0)
            finish_reason = getattr(raw, "response_metadata", {}).get("finish_reason")
            if out_tokens >= int(LLM_MAX_OUTPUT_TOKENS * 0.95) and finish_reason != "stop":
                raw_text = getattr(raw, "content", "")
                ts = time.strftime("%Y%m%d_%H%M%S")
                Path("traces").mkdir(exist_ok=True)
                with open(f"traces/degenerate_parse_{ts}.txt", "w", encoding="utf-8") as f:
                    f.write(f"prompt: {prompt}\nfinish_reason: {finish_reason}\nout_tokens: {out_tokens}\n--- raw response ---\n{raw_text}\n")
                return ParseResult.refuse(
                    flavor=RefusalFlavor.UNPARSEABLE,
                    detail=f"Degenerate parse (finish_reason={finish_reason}, out_tokens={out_tokens})",
                )

        response = result["parsed"]
    else:
        response = result

    # Normalize to a DraftIntent (the synthesizer guards the same way: some
    # backends return a dict rather than the model instance).
    if isinstance(response, dict):
        response = DraftIntent(**response)

    if response is None:
        return ParseResult.refuse(
            flavor=RefusalFlavor.UNPARSEABLE,
            detail="The model did not produce a structured Intent for this prompt.",
        )

    # Additional degenerate guard: if unanswerable is false but unanswerable_reason is long,
    # it's likely a repetition loop.
    if response.unanswerable is False and response.unanswerable_reason and len(response.unanswerable_reason) > 1000:
        return ParseResult.refuse(
            flavor=RefusalFlavor.UNPARSEABLE,
            detail=f"Degenerate parse: unanswerable_reason is too long ({len(response.unanswerable_reason)} chars) while unanswerable is false.",
        )

    # The model explicitly declared the prompt out of scope (the structural
    # half of the silent-rewrite fix).
    #
    # Phase 2 (UX-01) changed WHO decides the kind. Feature 1 tagged every
    # self-declared refusal UNPARSEABLE; feature 8 re-derived the flavor by
    # scanning the model's reason prose for capitalized words, which matched
    # "To", "ID", "Filtering" and "Receipt" and so returned UNKNOWN_ENTITY
    # for four of four measured refusals. The model now states the kind
    # outright in `unanswerable_kind`, and derive_flavor trusts it — see
    # capability.derive_flavor for the order of trust and why the prose scan
    # is gone rather than repaired.
    if response.unanswerable:
        reason = response.unanswerable_reason or "The prompt is out of scope."
        flavor = derive_flavor(
            reason,
            response.target_entity,
            menu,
            draft_kind=response.unanswerable_kind,
            draft_entity=response.unanswerable_entity,
        )
        # Carry the entity through for EVERY flavor, not just
        # UNKNOWN_ENTITY. The renderer needs it to say "I can look up AR
        # invoices, but this doesn't say which one" rather than falling back
        # to "I'm not sure which record you mean". It means different things
        # per flavor — the missing type for UNKNOWN_ENTITY, the supported
        # type everywhere else — which is fine: the renderer branches on
        # flavor anyway, and validate_intent has always populated it this way.
        #
        # `unanswerable_entity` first: `target_entity` is required to stay
        # EMPTY on a self-declared refusal (the instruction that stops the
        # model mangling an out-of-scope prompt into the nearest supported
        # entity — the silent-rewrite fix). So a second, purely descriptive
        # field carries the record type for wording, leaving that guard
        # untouched. target_entity remains the fallback for the paths where
        # it is legitimately set.
        return ParseResult.refuse(
            flavor=flavor,
            detail=reason,
            offending_entity=(
                response.unanswerable_entity or response.target_entity or None
            ),
        )

    # Shape-level conversion. A malformed filter value (non-JSON) is an
    # unparseable result, not a crash.
    try:
        intent = response.to_intent()
    except ValueError as exc:
        return ParseResult.refuse(
            flavor=RefusalFlavor.UNPARSEABLE,
            detail=f"The model's Intent was malformed: {exc}",
        )

    # #32 fault (b): set list_all deterministically from the raw prompt,
    # code-side (no LLM-visible text — the prompt is at its token ceiling).
    # Scoped to PurchaseOrder-rooted intents so nothing else is affected.
    # The planner uses this to allow an explicit PO list (list_all=True) to
    # sample-and-disclose, while a filter-less PO intent WITHOUT it (a
    # dropped-identifier query) refuses instead of dumping the table.
    if intent.target_entity == "PurchaseOrder":
        intent.list_all = _is_explicit_po_list(prompt)

    # Feature 7: an aggregation intent is validated by the planner's
    # aggregation-op registry, not by the entity/filter KG menu (its
    # target_entity/filters are unused). Skip validate_intent, which
    # would reject it for not having a KG-valid target entity.
    if intent.aggregate is not None:
        return ParseResult.ok(intent)

    # P6c: a comparison intent is validated by the planner's comparison-op
    # registry, not the entity/filter KG menu (its target_entity/filters
    # are unused). Skip validate_intent, same as aggregate — otherwise it
    # refuses the empty target_entity at Gate 1.
    if intent.compare is not None:
        return ParseResult.ok(intent)

    # COL-02: expand field synonyms ('who columns' -> the four who fields)
    # deterministically, AFTER the LLM and BEFORE validation, so the model
    # never decides the expansion and validate_intent sees only real column
    # names. A term with no synonym row (including a genuinely-unknown column)
    # passes through unchanged and is reported by validate_intent (COL-03).
    intent.fields = expand_field_synonyms(intent.fields, menu)

    # AI-10: correct an include the LLM mis-mapped from the raw prompt.
    # 'supplier sites for X' comes back as include=['Address'] because the
    # prompt steers supplier-location phrasing to Address; if the user said
    # 'site(s)', that must be Site instead — which then reaches the Site
    # gate and refuses honestly rather than returning addresses. Runs after
    # the LLM, before validate_intent, deterministically from the KG.
    intent.include = correct_include_from_prompt(prompt, intent.include, menu)

    # Q2 direction 2: validate the draft back against the KG. Out-of-scope
    # entities/filters become typed refusals (checkpoint 3).
    refusal = validate_intent(intent, menu)
    
    if refusal is not None:
        return ParseResult(refusal=refusal)

    return ParseResult.ok(intent)




