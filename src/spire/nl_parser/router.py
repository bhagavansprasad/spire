"""
The module-scoping router — classify a prompt to its Fusion module(s).

Phase 2 of the prompt-to-intent framework
(docs/features/prompt_to_intent_framework.md §2.1, D-router). The router is a
layer AROUND ``parse``: it decides which module context to assemble, then calls
the unchanged ``parse(prompt, system_prompt=scoped)``. This module holds
both the classifier (``classify_modules``) and the wiring (``route_and_parse``).

WHY A CLASSIFIER: the parser's full preamble is at its ~8,000-token ceiling
(§1.1). A prompt about invoices does not need supplier, procurement, and
receivables guidance. Classifying to the one relevant module lets the parser
receive only that module's blocks (via assemble_subset), which removes the
ceiling as a constraint. The classify call is small and cheap — its grounding
is the ~1.4k-char generated menu, not the whole preamble.

THE CONTRACT (D1): ``classify_modules`` returns a LIST of module names, even in
the single-module case (``["payables"]``). Increment 1 classifies cleanly
single-module prompts to exactly one module; the list keeps the contract stable
for increment 2, which will union multiple modules and add an all-modules
fallback for the unsure case.

INCREMENT 1 FAILURE MODE (decision 3a): a classification that is empty or names
a module outside KNOWN_MODULES RAISES. Increment 1 is the single-module happy
path; it does not yet have the graceful all-modules fallback (that is increment
2's job). Raising surfaces a misroute loudly instead of silently parsing
against the wrong — or an empty — context.

LLM INJECTION: same convention as the parser. ``classify_modules`` takes an
optional ``llm``; tests inject a mock whose
``with_structured_output(ModuleChoice).invoke(...)`` returns a canned
``ModuleChoice``, and production passes None so a real client is built via
``build_llm`` (provider-agnostic — gemini today).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from spire.nl_parser.context_assembly import (
    KNOWN_MODULES,
    _CLASSIFIER_MENU,
    assemble_subset,
)
from spire.nl_parser.parser import parse
from spire.nl_parser.result import ParseResult
from spire.nl_parser.vocabulary import load_kg_menu
from spire.diagnostics import get_logger


# --- structured-output contract -------------------------------------------

class ModuleChoice(BaseModel):
    """The classifier's structured output: which Fusion module(s) a prompt
    targets. A list even for one module (D1)."""

    modules: list[str] = Field(
        description=(
            "The Fusion module(s) this question targets, chosen from: "
            "payables, procurement, receivables, supplier. Return the single "
            "best module for a question about one area; the value is a list "
            "for forward-compatibility. Choose the module whose entities or "
            "their synonyms the question names."
        )
    )


# --- classifier prompt -----------------------------------------------------
# Small and self-contained: a short instruction plus the generated menu (which
# lists, per module, its entities and their colloquial synonyms). Nowhere near
# the parser's token ceiling — the menu is ~1.4k chars.

_CLASSIFIER_INSTRUCTION = (
    "You route a natural-language question about Oracle Fusion data to the "
    "Fusion module it targets. You do NOT answer the question, parse it, or "
    "produce anything but the module choice.\n\n"
    "Choose from exactly these four modules: payables, procurement, "
    "receivables, supplier. Pick the module whose entities — or their listed "
    "synonyms — the question names. For a question that clearly concerns one "
    "area, return that single module.\n\n"
    "A caution on one shared word. A question about the status or progress "
    "of ONE named purchase order — whether PO N has been received, "
    "invoiced, or paid; its lifecycle stage; what is blocking it; a "
    "summary of it — is a PROCUREMENT question, even though it says "
    "\"invoiced\" or \"paid.\" Those are stages of that purchase order's "
    "lifecycle, reported from the order itself; they do not make it a "
    "payables question. Do NOT add payables for such a question.\n\n"
    "Module menu (each module, its entities, and colloquial synonyms):\n\n"
)


def _classifier_system_prompt(menu_text: str) -> str:
    """Assemble the classifier's system prompt from the instruction + menu."""
    return _CLASSIFIER_INSTRUCTION + menu_text


# --- the classifier --------------------------------------------------------

class ClassificationError(RuntimeError):
    """The classifier produced an empty or unknown module set. Increment 1
    raises rather than falling back (decision 3a); increment 2 will replace
    this with an all-modules fallback for the unsure case."""


def classify_modules(
    prompt: str,
    llm: Any | None = None,
    menu_text: str | None = None,
) -> list[str]:
    """Classify a prompt to its Fusion module(s).

    Args:
        prompt: The user's natural-language question.
        llm: Optional pre-built LangChain LLM. Tests inject a mock whose
            ``with_structured_output(ModuleChoice).invoke(...)`` returns a
            canned ``ModuleChoice`` (or dict). Production passes None and a
            fresh client is built via ``build_llm`` (reads provider config).
        menu_text: Optional grounding menu override. Defaults to the module
            menu cached at import (``_CLASSIFIER_MENU``). Tests pass a fixture
            to avoid coupling to the committed file.

    Returns:
        A list of module names, each in KNOWN_MODULES. Increment 1 returns
        exactly one for a cleanly single-module prompt.

    Raises:
        ClassificationError: if the LLM returns no modules, or any name is
            outside KNOWN_MODULES (decision 3a — no fallback in increment 1).
    """
    if menu_text is None:
        menu_text = _CLASSIFIER_MENU

    if llm is None:
        # Lazy import so unit tests (which inject a mock) don't require an LLM
        # dep or API key to import this module — same pattern as parse().
        from spire.config import build_llm

        llm = build_llm()

    structured_llm = llm.with_structured_output(ModuleChoice, include_raw=True)
    system_prompt = _classifier_system_prompt(menu_text)

    result = structured_llm.invoke(
        [("system", system_prompt), ("human", prompt)]
    )

    # With include_raw=True the real LLM returns
    # {"raw": AIMessage, "parsed": ModuleChoice|None, "parsing_error": ...}.
    # A mock may return the bare ModuleChoice (or a dict). Handle both, and
    # log token usage under a distinct stage so --show-tokens attributes the
    # classify call separately from the parse call.
    parsed: ModuleChoice | dict | None
    if isinstance(result, dict) and "parsed" in result:
        from spire.config import log_usage

        log_usage(result.get("raw"), stage="classify")
        parsed = result.get("parsed")
    else:
        parsed = result

    if parsed is None:
        raise ClassificationError(
            f"classifier produced no parseable choice for prompt: {prompt!r}"
        )

    # Accept either a ModuleChoice model or a bare dict (mock convenience).
    if isinstance(parsed, ModuleChoice):
        modules = list(parsed.modules or [])
    elif isinstance(parsed, dict):
        modules = list(parsed.get("modules") or [])
    else:
        modules = list(getattr(parsed, "modules", None) or [])

    # Normalize and validate against the known module set (3a).
    modules = [m.strip() for m in modules if isinstance(m, str) and m.strip()]
    if not modules:
        raise ClassificationError(
            f"classifier returned no modules for prompt: {prompt!r}"
        )
    unknown = [m for m in modules if m not in KNOWN_MODULES]
    if unknown:
        raise ClassificationError(
            f"classifier returned unknown module(s) {unknown} "
            f"(known: {list(KNOWN_MODULES)}) for prompt: {prompt!r}"
        )

    # De-duplicate while preserving order (a model could name one twice).
    seen: set[str] = set()
    deduped = [m for m in modules if not (m in seen or seen.add(m))]
    return deduped


# --- the router: route_and_parse ------------------------------------------
# The two-request flow (D-router): classify the prompt to its module(s),
# assemble ONLY that module's context, and parse against it. This is a layer
# AROUND parse — parse itself is unchanged (it just receives a scoped
# system_prompt instead of building the full one).


def route_and_parse(
    prompt: str,
    llm: Any | None = None,
    menu: Any | None = None,
) -> ParseResult:
    """Classify a prompt to its module(s), then parse against scoped context.

    The production replacement for a bare ``parse(prompt)`` at the pipeline
    seam. Instead of sending the full all-modules preamble, it classifies the
    prompt to its Fusion module(s) and sends only Tier 1 (core + refusals) plus
    that module's blocks — removing the parser's token ceiling as a constraint
    (§1.1).

    The KG menu is loaded ONCE here and shared by both assemble_subset (which
    renders it into the scoped prompt) and parse (which uses it for KG
    validation). Loading once guarantees the scoped prompt and the parse see
    the SAME menu — the only thing that differs from a full parse is which
    preamble blocks are present, which is exactly what the increment-1 fidelity
    check requires (routing changes the token cost, not the Intent).

    Args:
        prompt: The user's natural-language question.
        llm: Optional LangChain LLM, passed to BOTH the classify call and the
            parse call. Production passes None; each builds its own via
            build_llm. (A test injecting one mock must satisfy both the
            ModuleChoice and DraftIntent structured-output calls; unit tests of
            the wiring patch classify_modules/parse instead.)
        menu: Optional pre-loaded KGMenu. Defaults to load_kg_menu().

    Returns:
        ParseResult — whatever parse() returns for the scoped context.

    Out-of-scope handling:
        If classify_modules finds NO module (raises ClassificationError), this
        falls back to a full-context parse rather than propagating the error —
        so a definitively out-of-scope prompt gets a clean parser refusal, not
        an exception (never worse than the pre-router baseline, design §4).
        The "unsure between several modules" case remains increment-2 work.
    """
    if menu is None:
        menu = load_kg_menu()

    try:
        modules = classify_modules(prompt, llm=llm)
    except ClassificationError:
        # No module matched — the prompt is definitively out of scope (e.g.
        # "what is the weather today", which names no Fusion entity). Fall back
        # to a FULL-context parse, which refuses cleanly with a structured
        # Reason/Solution/Example, instead of surfacing a raw
        # ClassificationError. This keeps the router "never worse than today"
        # (design §4): without the fallback, an out-of-scope prompt that the
        # full parser handles gracefully would instead throw. This is the
        # increment-2 all-modules fallback, applied to the no-module case;
        # the "unsure between modules" case (classifier returns several) is
        # still deferred to increment 2.
        get_logger("parser").debug(
            "Router: no module matched \u2192 full-context parse"
        )
        return parse(prompt, llm=llm, menu=menu)  # system_prompt=None -> full

    get_logger("parser").debug("Router: modules=%s", modules)
    scoped = assemble_subset(modules, menu)
    return parse(prompt, llm=llm, menu=menu, system_prompt=scoped)
