

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

from spire.config import GEMINI_MODEL, GEMINI_TEMPERATURE
from spire.nl_parser.capability import derive_flavor
from spire.nl_parser.draft import DraftIntent
from spire.nl_parser.result import ParseResult, RefusalFlavor
from spire.nl_parser.validation import validate_intent
from spire.nl_parser.vocabulary import KGMenu, load_kg_menu


# Model and determinism come from spire.config (single source of truth).
_MODEL_NAME = GEMINI_MODEL
_TEMPERATURE = GEMINI_TEMPERATURE


_SYSTEM_PROMPT_PREAMBLE = (
    "You convert a natural-language question about Oracle Fusion procurement "
    "data into a single structured Intent. You do NOT answer the question, "
    "fetch data, or call tools. You only produce the Intent.\n\n"
    "An Intent has:\n"
    "- target_entity: the ONE entity the question is rooted on.\n"
    "- filters: zero or more constraints, each a type plus a JSON-encoded "
    "value.\n"
    "- include: related entities to fetch alongside (e.g. the buyer on a PO).\n\n"
    "You may ONLY use the entities and filter types listed below.\n\n"
    "COMPLETENESS — extract EVERY in-scope detail:\n"
    "When the question maps onto the allowed vocabulary, you MUST capture "
    "ALL of its constraints and relationships — do not omit any. Map natural "
    "language to the allowed filters/includes, for example:\n"
    "- a country ('US', 'in the United Kingdom') -> a 'country' filter, with "
    "the value normalized to the canonical code from the COUNTRY list below.\n"
    "- 'with open POs' / 'has open purchase orders' -> a 'has_open_PO' "
    "filter with value true.\n"
    "- 'no invoices in the last N months' / 'without recent invoices' / "
    "'no recent invoices' / 'haven't invoiced in N months' -> a "
    "'has_no_recent_invoices' filter with value {\"months\": N}. This clause "
    "is easy to miss — whenever the prompt mentions an absence of invoices "
    "over a time window, you MUST emit this filter.\n"
    "- 'active suppliers' / 'inactive suppliers' -> a 'status' filter with "
    "value 'active' or 'inactive'.\n"
    "- 'suppliers named X' / 'called X' / 'with X in the name' -> a "
    "'name_fragment' filter with value the substring X.\n"
    "- 'created after X' / 'created between X and Y' / 'created in <period>' "
    "-> a 'created_date' filter with value {\"from\": \"YYYY-MM-DD\", "
    "\"to\": \"YYYY-MM-DD\"}. Include only the bounds the prompt gives; omit "
    "the other key. Convert every date to YYYY-MM-DD (e.g. 'Jan 2025' -> "
    "from '2025-01-01'; 'March 2025' as an end -> to '2025-04-01').\n"
    "- 'invoices for supplier X' / 'invoices for supplier 1252' / 'invoices "
    "for Lee Supplies' -> target_entity 'Invoice' with a 'supplier' filter "
    "whose value is the supplier reference as written (a number like '1252' "
    "or a name like 'Lee Supplies'). Invoice queries MUST include this "
    "supplier filter.\n"
    "- 'invoices in 2023' / 'invoices after 2023-01-01' / 'invoices "
    "between Jan and Mar 2023' -> an 'invoice_date' filter with value "
    "{\"from\": \"YYYY-MM-DD\", \"to\": \"YYYY-MM-DD\"}. Include only the "
    "bounds given; omit the other key. Convert dates to YYYY-MM-DD.\n"
    "- 'invoices over 10000' / 'invoices above 10000' / 'invoices between "
    "1000 and 5000' -> an 'invoice_amount' filter with value "
    "{\"min\": N, \"max\": N} (numbers, not strings). Include only the "
    "bounds given; omit the other key.\n"
    "- 'addresses for supplier X' / 'supplier 1252 addresses' / 'US "
    "supplier addresses' / 'addresses in the UK' -> target_entity "
    "'Address' with a 'supplier' filter (the supplier reference as "
    "written) and/or a 'country' filter (canonical code). Address queries "
    "MUST include a supplier or a country.\n"
    "- 'include the buyer' / 'with the buyer' / 'show the buyer assigned' -> "
    "add 'Buyer' to include.\n"
    "If a prompt mentions several of these, emit ALL of them. A common error "
    "is dropping a constraint (e.g. forgetting the country, or omitting the "
    "buyer include) — do not do this.\n\n"
    "OUT OF SCOPE — refuse, do not salvage:\n"
    "If the question needs ANY entity or filter that is not in the lists "
    "below, or is too vague to pin to a specific entity and filters, you "
    "MUST set unanswerable=true and briefly say why in unanswerable_reason. "
    "In that case do NOT guess a target_entity and do NOT map the request to "
    "the closest listed entity. It is WRONG to turn an unanswerable question "
    "into a broad in-scope query (for example, answering 'contract renewals' "
    "by listing all suppliers). Refusing is correct; salvaging is not.\n\n"
    "AGGREGATION — use the aggregate block, do NOT refuse:\n"
    "If the question asks for a RANKING or TOTAL rather than a list — e.g. "
    "'top 10 suppliers by spend', 'which suppliers did we spend the most "
    "with last quarter', 'total invoiced by supplier in 2025' — set the "
    "aggregate block instead of producing a list. Use op='by_supplier' for "
    "supplier spend rankings, fill date_from/date_to from any time window in "
    "the prompt (as 'YYYY-MM-DD'), and top_n from any 'top N' wording "
    "(default 10). Do NOT set unanswerable for these — aggregation by "
    "supplier IS supported.\n\n"
    "So: capture everything when in scope; refuse cleanly when out of scope. "
    "Only produce a normal Intent (unanswerable=false) when the question maps "
    "cleanly onto the allowed entities and filters.\n"
)


def _format_menu(menu: KGMenu) -> str:
    """Render the KG menu as the allowed-vocabulary block of the prompt."""
    lines: list[str] = []

    lines.append("ALLOWED target_entity values (these have a fetcher):")
    for e in sorted(menu.target_entities):
        desc = menu.entity_descriptions.get(e, "")
        lines.append(f"  - {e}: {desc}")
    lines.append("")

    lines.append(
        "OTHER known entities (recognized, but NOT valid as target_entity — "
        "a query rooted on these is out of scope):"
    )
    others = sorted(set(menu.entity_descriptions) - set(menu.target_entities))
    for e in others:
        lines.append(f"  - {e}")
    lines.append("")

    lines.append("ALLOWED filter types:")
    for ft in sorted(menu.filter_types):
        lines.append(f"  - {ft}")
    lines.append("")

    lines.append(
        "COUNTRY values accepted (map any of these terms to the canonical "
        "code on the right when building a 'country' filter):"
    )
    for term, canonical in sorted(menu.country_terms.items()):
        lines.append(f"  - {term} -> {canonical}")

    return "\n".join(lines)


def _build_system_prompt(menu: KGMenu) -> str:
    return _SYSTEM_PROMPT_PREAMBLE + "\n" + _format_menu(menu)


def parse(
    prompt: str,
    llm: Any | None = None,
    menu: KGMenu | None = None,
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

        log_usage(result.get("raw"), stage="parse")
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

    # The model explicitly declared the prompt out of scope (the structural
    # half of the silent-rewrite fix). Trust the REFUSAL, but don't trust the
    # model to know WHICH kind of refusal it is — feature 1 tagged every
    # self-declared refusal UNPARSEABLE. Feature 8 re-derives the flavor from
    # the draft + KG menu (UNKNOWN_ENTITY for contracts, UNSUPPORTED_OPERATION
    # for aggregation), falling back to UNPARSEABLE only when nothing more
    # specific fits.
    if response.unanswerable:
        reason = response.unanswerable_reason or "The prompt is out of scope."
        flavor = derive_flavor(reason, response.target_entity, menu)
        offending = (
            response.target_entity
            if flavor is RefusalFlavor.UNKNOWN_ENTITY and response.target_entity
            else None
        )
        return ParseResult.refuse(
            flavor=flavor,
            detail=reason,
            offending_entity=offending,
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

    # Feature 7: an aggregation intent is validated by the planner's
    # aggregation-op registry, not by the entity/filter KG menu (its
    # target_entity/filters are unused). Skip validate_intent, which
    # would reject it for not having a KG-valid target entity.
    if intent.aggregate is not None:
        return ParseResult.ok(intent)

    # Q2 direction 2: validate the draft back against the KG. Out-of-scope
    # entities/filters become typed refusals (checkpoint 3).
    refusal = validate_intent(intent, menu)
    if refusal is not None:
        return ParseResult(refusal=refusal)

    return ParseResult.ok(intent)







