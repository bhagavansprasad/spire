"""
The NL parser — natural-language prompt to ``Intent`` (feature 1).

This is the interpreter stage of the Design 3 pipeline:

    Prompt -> [parser: LLM] -> Intent -> planner -> executor -> synthesizer

The parser is modeled on the
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

PROMPT CACHING (default on):
The scoped system prompt is byte-identical across every parse call that
shares a scope and is the largest input cost in the pipeline. It is stored
in a Gemini context cache once and served from it on every subsequent call
— measured at ~99% of input tokens cached. The pipeline attempts the
cached path on every ``parse()`` call where no LLM was injected.

    SPIRE_PROMPT_CACHE_DISABLE=1   skip the cache path entirely — for cost
                                   measurement, stale-cache debugging, or
                                   a model without caching support.

The ``llm is None`` guard keeps tests on the LangChain path regardless of
the flag, because they always inject a MockLLM. Any failure in the cached
path (below the minimum token count, quota, network, TTL expiry) falls
through to the LangChain call, so a cache miss costs a slow call, never a
broken pipeline. On failure the cache name is FORGOTTEN (prompt_cache.
forget), so the NEXT call re-lists and re-creates rather than serving the
same dead name to every subsequent call in the process.

Diagnostics: ``[cache] HIT / MISS`` and ``[cache] unavailable`` are emitted
on the ``spire.parser`` logger, opened by ``--show-parser`` (or
``SPIRE_SHOW_PARSER=1``, or ``[tool.spire.diagnostics] show_parser = true``).
They fire only when the cached path was actually attempted, so a default
run with the flag unset and the cache working stays quiet in the logs
beyond the single ``[cache]`` line.
"""

from __future__ import annotations

import os
from typing import Any

from spire.config import GEMINI_MODEL, GEMINI_TEMPERATURE, LLM_MAX_OUTPUT_TOKENS
from spire.diagnostics import get_logger
from spire.nl_parser.capability import derive_flavor
from spire.nl_parser.draft import DraftIntent
from spire.nl_parser.result import ParseResult, RefusalFlavor
from spire.nl_parser.intent_validation import validate_intent
from spire.nl_parser.vocabulary import (
    expand_field_synonyms,
    correct_include_from_prompt,
    add_child_include_from_prompt,
    strip_po_supplier_include,
)
from spire.nl_parser.vocabulary import KGMenu, load_kg_menu

from spire.nl_parser.context_assembly import _build_system_prompt

from pathlib import Path


# Model and determinism come from spire.config (single source of truth).
_MODEL_NAME = GEMINI_MODEL
_TEMPERATURE = GEMINI_TEMPERATURE


# Parser component logger. Silent unless --show-parser (or
# SPIRE_SHOW_PARSER=1, or [tool.spire.diagnostics] show_parser = true).
# Every [cache] diagnostic in this module routes through it.
_parser_log = get_logger("parser")


import re
from datetime import date

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


def _is_all_digit_customer_value(value: Any) -> bool:
    """True when a by_customer_name value is actually an account number.

    F-019. The parser sometimes routes a bare account number into
    by_customer_name; the resulting query (`q=CustomerName='25750'`)
    returns zero rows, and the synthesizer narrates the empty bucket as
    "no customer accounts found" — a silent false negative. A
    digit-only string is an account number, not a customer name; the
    post-parse correction below rewrites the filter type. Same class as
    the F-018 invoice-number override: deterministic, post-LLM, no
    prompt-text change.
    """
    return (
        isinstance(value, str)
        and bool(value.strip())
        and value.strip().isdigit()
    )


_INVOICE_NUMBER_QUERY_RE = re.compile(
    r"\binvoice\b(?:\s+(?:number|numbered|no\.?|#))?\s+"
    r"([A-Za-z0-9][A-Za-z0-9_./-]{3,})",
    re.IGNORECASE,
)


def _extract_invoice_number(prompt: str) -> str | None:
    """Return the invoice number if the prompt names one directly, else None.

    F-018. The sysprompt teaches the shape (b_invoices_for_supplier.sysprompt)
    but the LLM has a strong prior against treating an alphanumeric token as
    an identifier — measured 2026-09-23, the model refuses even when the rule
    quotes the prompt verbatim. This is a deterministic, post-LLM helper of
    the same class as _is_explicit_po_list: pure Python, runs after the
    model, corrects the shape the model gets wrong.

    Returns the token exactly as it appeared (trailing sentence punctuation
    stripped). Returns None when the prompt names no direct invoice number.

    The two guards keep the extraction from being too loose:

      - The token must contain at least one digit. Excludes the "invoice
        created before 2015" case (token would be "created").

      - A pure-digit token is accepted only when the literal word "number"
        (or "numbered" / "no." / "#") is present. Otherwise "invoice 162034"
        is treated as ambiguous — the pod's PO and invoice id spaces overlap
        in shape, and the model's own prior is the safer read on the bare
        form.
    """
    m = _INVOICE_NUMBER_QUERY_RE.search(prompt)
    if not m:
        return None
    token = m.group(1).rstrip(".,;:!?")
    if len(token) < 4 or not any(c.isdigit() for c in token):
        return None
    has_number_word = bool(re.search(
        r"\binvoice\s+(?:number|numbered|no\.?|#)", prompt, re.IGNORECASE
    ))
    has_non_digit = any(not c.isdigit() for c in token)
    if not has_number_word and not has_non_digit:
        return None
    return token


# F-027. A country COLUMN request ("supplier number and country") versus
# a country FILTER value ("suppliers in US", "US suppliers"). The parser
# emits two different wrong shapes on the column request — 16/20 with
# include=['Address'] and country dropped from fields; 4/20 with no
# include and country landing in unresolved_fields. The sysprompt rule
# that teaches the shape lives under columns/, which the router never
# loads (F-050). This correction makes the intent deterministic
# regardless of which shape arrived: pure Python, runs after the LLM.
# Same pattern as _extract_invoice_number (F-018) and
# _is_all_digit_customer_value (F-019).
_COUNTRY_COLUMN_RE = re.compile(r"\bcountr(?:y|ies)\b", re.IGNORECASE)


def _has_country_column_phrasing(prompt: str, intent: Any) -> bool:
    """True when the prompt requests a country COLUMN on a Supplier query.

    Distinguishes a column request ("Supplier number and country",
    "name, number, and country") from a filter value ("active suppliers
    in US", "suppliers in the UK"): a filter carries a specific country
    the parser routes to a `country` filter; a column request has the
    word "country" with no value. The presence of a `country` filter on
    the intent is the discriminator.

    Scoped to Supplier targets — country on Supplier is a projection of
    the child Address resource, and the correction only applies to that
    shape. Other entities with a country projection (TaxpayerCountryCode)
    are handled separately if at all.
    """
    if intent.target_entity != "Supplier":
        return False
    if any(f.get("type") == "country" for f in intent.filters):
        return False
    return bool(_COUNTRY_COLUMN_RE.search(prompt))


# F-016: a plain-list row cap — "top 5 credit memos", "first 10
# suppliers", "the 5 biggest invoices". The parser has no field to
# record a cap (DraftIntent has no list_limit), and the LLM has a strong
# prior against treating a bare integer as a cap on an otherwise ordinary
# list question — measured 2026-09-23, the model emits a filter-less
# intent and the "5" is lost. This is a deterministic, post-LLM extractor
# of the same class as _is_explicit_po_list and _extract_invoice_number:
# pure Python, runs after the model, corrects the shape the model drops.
#
# Two shapes, both anchored on a cap word so a bare integer is never a
# cap (amounts, dates, and IDs are all bare integers in prompts — see
# the two negative tests).
#
#   Leading:  "top 5 ..." / "first 10 ..." / "last 3 ..."
#   Trailing: "... 5 biggest" / "... 10 largest" / "... 3 most recent"
#
# The upper bound is 200 because nothing we serve needs a larger plain-
# list cap, and a larger number in a prompt is more likely to be a date,
# an amount, or an ID than a row cap. Out-of-range values return None
# rather than a bound integer.
_LIST_CAP_LEADING_RE = re.compile(
    r"\b(?:top|first|last)\s+(\d{1,4})\b",
    re.IGNORECASE,
)
_LIST_CAP_TRAILING_RE = re.compile(
    r"\b(\d{1,4})\s+"
    r"(?:biggest|largest|smallest|oldest|newest|"
    r"most\s+recent|least\s+recent)\b",
    re.IGNORECASE,
)

# A time window uses the same words as a cap: "in the last 5 months",
# "from the last 12 months". The LEADING regex would match "last 5" in
# that phrasing and record 5 as a row cap on a prompt that never asked
# for one. Suppressing the match when a unit word follows the integer
# keeps the two shapes apart without a second regex pass.
_TIME_UNIT_AFTER_INTEGER_RE = re.compile(
    r"^\s*(?:months?|years?|weeks?|days?|hours?|minutes?)\b",
    re.IGNORECASE,
)

_LIST_CAP_MAX = 200


def _extract_list_cap(prompt: str) -> int | None:
    """Return the plain-list row cap named in the prompt, or None.

    F-016. Fires on "top N" / "first N" / "last N" (leading) and on
    "N biggest" / "N largest" / "N most recent" (trailing). Returns None
    when no cap is named, when N is outside 1..200, or when the leading
    match is followed by a time unit ("last 5 months" is a window, not a
    row cap).

    Scoped by the caller to plain-list intents — a prompt carrying an
    aggregate block, a compare block, or count_only is not routed here,
    because those shapes have their own cap mechanism (aggregate.top_n)
    or produce a single number (count_only).
    """
    text = prompt.strip()

    # Leading shape first; suppressed when a time unit follows the N.
    for m in _LIST_CAP_LEADING_RE.finditer(text):
        n = int(m.group(1))
        if not (1 <= n <= _LIST_CAP_MAX):
            continue
        tail = text[m.end():]
        if _TIME_UNIT_AFTER_INTEGER_RE.match(tail):
            continue
        return n

    # Trailing shape. No time-unit suppression: no phrasing pairs a
    # size adjective with a time unit ("5 biggest months" is not
    # something a prompt says), so the shape is unambiguous.
    m = _LIST_CAP_TRAILING_RE.search(text)
    if m is not None:
        n = int(m.group(1))
        if 1 <= n <= _LIST_CAP_MAX:
            return n

    return None


# F-058. A period-anchored phrase names a CALENDAR boundary ("this year",
# "last quarter"). A rolling window ("in the last 6 months") names a
# DISTANCE FROM TODAY and belongs to F-046/F-048/F-055 — the same
# RELATIVE OLDER / RELATIVE RECENT distinction those rules draw. The
# pattern matches the four period phrases only; the rolling shapes are
# left for their own rules.
_PERIOD_ANCHORED_RE = re.compile(
    r"\b(this|last)\s+(year|quarter|month)\b",
    re.IGNORECASE,
)


def _extract_period_bounds(prompt: str) -> tuple[str, str] | None:
    """F-058. Calendar bounds for a period-anchored phrase, or None.

    Fires on `this year` / `last year` / `this quarter` / `this month`.
    Returns (date_from, date_to) as ISO date strings, half-open like
    every other date range in the pipeline: date_from inclusive,
    date_to exclusive. `this year` on 2026-09-29 produces
    ("2026-01-01", "2027-01-01").

    The op guard lives at the call site, not here — this stays a pure
    text-to-bounds function so it can be unit-tested without building
    an Intent.

    Same class as _extract_invoice_number / _extract_list_cap /
    _has_country_column_phrasing: pure Python, runs after the LLM,
    overrides the shape the model gets wrong.
    """
    m = _PERIOD_ANCHORED_RE.search(prompt)
    if m is None:
        return None
    which, unit = m.group(1).lower(), m.group(2).lower()
    today = date.today()

    if unit == "year":
        year = today.year if which == "this" else today.year - 1
        return f"{year}-01-01", f"{year + 1}-01-01"

    if unit == "quarter":
        # Quarter index 0..3 (Q1=Jan-Mar, Q2=Apr-Jun, Q3=Jul-Sep, Q4=Oct-Dec).
        q = (today.month - 1) // 3
        year = today.year
        if which == "last":
            q -= 1
            if q < 0:
                q = 3
                year -= 1
        start_month = q * 3 + 1
        end_year = year if start_month + 3 <= 12 else year + 1
        end_month = (start_month + 2) % 12 + 1
        return (
            f"{year}-{start_month:02d}-01",
            f"{end_year}-{end_month:02d}-01",
        )

    # month
    year, month = today.year, today.month
    if which == "last":
        month -= 1
        if month < 1:
            month = 12
            year -= 1
    if month == 12:
        return f"{year}-12-01", f"{year + 1}-01-01"
    return f"{year}-{month:02d}-01", f"{year}-{month + 1:02d}-01"


def _is_empty_draft(parsed: Any) -> bool:
    """A shape-valid draft with nothing to plan against.

    The model produced structured output that deserializes, isn't
    unanswerable, and has no aggregate or compare block — and no
    target_entity. This is JSON mode's schema-as-hint behaviour, not a
    schema violation, so it slips past the model's own validity check.
    See the retry in parse() for why it cannot be configured away.
    """
    return (
        not getattr(parsed, "unanswerable", False)
        and not getattr(parsed, "target_entity", None)
        and not getattr(parsed, "aggregate", None)
        and not getattr(parsed, "compare", None)
    )


def _retry_draft_once(
    prompt: str,
    schema: Any,
    system_prompt: str,
    llm: Any,
    cache_name: str | None,
) -> Any | None:
    """Re-issue the structured-output call once. Returns the new draft,
    or None if the retry also failed.

    Uses the same path the first call used when possible — the cached
    call if a cache name is given, otherwise LangChain. Never raises:
    a failed retry means "fall back to the first call's refusal", not
    "crash the parser".
    """
    def _coerce(x: Any) -> Any | None:
        if isinstance(x, dict):
            try:
                x = schema.model_validate(x)
            except Exception:
                return None
        return x if isinstance(x, schema) else None

    if cache_name is not None:
        try:
            from spire.nl_parser.cached_llm import invoke_structured
            r = invoke_structured(prompt, schema, cache_name)
            p = r.get("parsed") if isinstance(r, dict) else r
            p = _coerce(p)
            if p is not None:
                return p
        except Exception:
            pass

    try:
        if llm is None:
            from spire.config import build_llm
            llm = build_llm(_TEMPERATURE)
        r = llm.with_structured_output(schema, include_raw=True).invoke(
            [("system", system_prompt), ("human", prompt)]
        )
        p = r.get("parsed") if isinstance(r, dict) else r
        return _coerce(p)
    except Exception:
        return None


def parse(
    prompt: str,
    llm: Any = None,
    menu: Any = None,
    system_prompt: str | None = None,
) -> ParseResult:
    """Parse a natural-language prompt into a structured Intent."""
    if menu is None:
        menu = load_kg_menu()

    # Resolve the system prompt first — both the cached and uncached paths
    # need it, and the cache key is a hash of its bytes.
    if system_prompt is None:
        system_prompt = _build_system_prompt(menu)

    # Cached path: ON by default for production calls. The `llm is None`
    # half of the condition is what keeps every test on the mocked path.
    result: Any = None
    cache_used = False
    cache_requested = (
        llm is None
        and os.environ.get("SPIRE_PROMPT_CACHE_DISABLE") != "1"
    )

    if cache_requested:
        from spire.nl_parser.prompt_cache import forget, get_or_create
        from spire.nl_parser.cached_llm import invoke_structured

        cache_name = get_or_create(system_prompt)
        if cache_name is None:
            _parser_log.debug(
                "[cache] unavailable — no cache created; using LangChain"
            )
        else:
            try:
                result = invoke_structured(prompt, DraftIntent, cache_name)
                cache_used = True
            except Exception as exc:
                # Expired mid-run, quota revoked, network — treat as a
                # miss and FORGET the name. Without the forget, _memo
                # would serve the same dead cache name to every
                # subsequent call in this process. THIS call still falls
                # through to LangChain; the NEXT call re-lists.
                forget(cache_name)
                _parser_log.debug(
                    "[cache] invoke raised %s: %s; using LangChain",
                    type(exc).__name__, exc,
                )
                result = None

    if result is None:
        if llm is None:
            from spire.config import build_llm
            llm = build_llm(_TEMPERATURE)

        structured_llm = llm.with_structured_output(DraftIntent, include_raw=True)
        result = structured_llm.invoke(
            [("system", system_prompt), ("human", prompt)]
        )

    # --- Diagnostics + degenerate-parse guard (only for the include_raw
    # envelope shape) ---
    if isinstance(result, dict) and "parsed" in result:
        from spire.config import log_usage

        log_usage(result.get("raw"), stage="parse")

        if cache_used:
            _raw_diag = result.get("raw")
            if _raw_diag is not None:
                _um = getattr(_raw_diag, "usage_metadata", {}) or {}
                _details = _um.get("input_token_details") or {}
                _cached = _details.get("cache_read", 0) or 0
                _total_in = _um.get("input_tokens", 0) or 0
                _fresh = _total_in - _cached
                _parser_log.debug(
                    "[cache] %s  cached=%d  fresh=%d  total_in=%d",
                    "HIT " if _cached > 0 else "MISS",
                    _cached, _fresh, _total_in,
                )

        raw = result.get("raw")
        if raw is not None:
            finish = (
                getattr(raw, "response_metadata", {}) or {}
            ).get("finish_reason")
            if finish and "stop" not in str(finish).lower():
                return ParseResult.refuse(
                    RefusalFlavor.UNPARSEABLE,
                    detail=(
                        f"the model did not stop normally "
                        f"(finish_reason={finish!r})"
                    ),
                )

    # --- Extract the draft from whatever shape the LLM (or mock) returned ---
    if result is None:
        return ParseResult.refuse(
            RefusalFlavor.UNPARSEABLE,
            detail="the model produced nothing",
        )

    if isinstance(result, dict) and "parsed" in result:
        parsed = result.get("parsed")
        parsing_error = result.get("parsing_error")
        if parsed is None:
            detail = "the model produced no parseable intent"
            if parsing_error:
                detail += f" ({parsing_error})"
            return ParseResult.refuse(
                RefusalFlavor.UNPARSEABLE, detail=detail
            )
    else:
        # A bare DraftIntent, or a raw dict shaped like one.
        parsed = result

    # Coerce a raw dict into a DraftIntent via model_validate, so Pydantic
    # handles nested coercion (filters as dicts → DraftFilter) in one pass.
    # The prior hand-rolled DraftFilter(**f) comprehension could silently
    # produce a partial object; letting Pydantic own it removes that risk.
    if isinstance(parsed, dict):
        try:
            parsed = DraftIntent.model_validate(parsed)
        except Exception as exc:
            return ParseResult.refuse(
                RefusalFlavor.UNPARSEABLE,
                detail=f"the model produced a malformed draft: {exc}",
            )

    if not isinstance(parsed, DraftIntent):
        return ParseResult.refuse(
            RefusalFlavor.UNPARSEABLE,
            detail=f"unexpected draft type: {type(parsed).__name__}",
        )

    # --- Explicit unanswerable takes precedence over everything else ---
    if getattr(parsed, "unanswerable", False):
        # F-018: an Invoice-shape refusal on a prompt that names an
        # invoice number directly. The sysprompt teaches the shape; the
        # LLM still refuses (measured 2026-09-23, the rule is quoted in
        # the prompt and the model ignores it). Deterministic override,
        # same class as _is_explicit_po_list. Fires ONLY when the refusal
        # is about the Invoice entity AND the raw prompt contains a
        # code-shaped token after "invoice".
        if (
            (getattr(parsed, "unanswerable_entity", None) or "")
            .strip()
            .lower() == "invoice"
        ):
            inv_number = _extract_invoice_number(prompt)
            if inv_number is not None:
                return ParseResult.ok(
                    Intent(
                        target_entity="Invoice",
                        filters=[
                            {"type": "invoice_number", "value": inv_number}
                        ],
                    )
                )

        from spire.nl_parser.capability import derive_flavor

        kind = getattr(parsed, "unanswerable_kind", None)
        entity = getattr(parsed, "unanswerable_entity", None)
        reason = getattr(parsed, "unanswerable_reason", "") or ""
        flavor = derive_flavor(
            reason, entity or "", menu,
            draft_kind=kind, draft_entity=entity,
        )
        return ParseResult.refuse(
            flavor,
            detail=reason,
            offending_entity=entity,
        )

    # --- Empty-draft retry ---
    #
    # The cached path (response_schema JSON mode) occasionally returns a
    # shape-valid draft with no target_entity, no aggregate, no compare,
    # and no unanswerable flag: the model wrote structured output with
    # nothing to plan against. Measured 5% on one prompt (1/20 loop),
    # ~3.2% over 155 prompts across 5 runs; the uncached path has not
    # shown the mode (0/155). Cause: JSON mode treats the schema as a
    # hint, not a contract. Tool-calling would enforce it, but the API
    # forbids tools alongside cached_content, so the mode is not
    # configurable away.
    #
    # One retry converts the ~3% to ~0.15% (single-call failure is
    # stochastic; the retry is an independent trial). The retry fires
    # only on the ~3% of runs that produce an empty draft, so a healthy
    # run pays nothing for it.
    if _is_empty_draft(parsed):
        _parser_log.debug(
            "[parse] empty draft (no target_entity, not unanswerable); "
            "retrying once"
        )
        retry = _retry_draft_once(
            prompt, DraftIntent, system_prompt,
            llm, cache_name if cache_used else None,
        )
        if retry is not None:
            parsed = retry

    # --- Shape check: nothing to plan against ---
    if not getattr(parsed, "target_entity", None):
        if not (
            getattr(parsed, "aggregate", None)
            or getattr(parsed, "compare", None)
        ):
            return ParseResult.refuse(
                RefusalFlavor.UNPARSEABLE,
                detail="the model produced a draft with no target_entity",
            )

    # --- Convert the DraftIntent into the planner's Intent ---
    #
    # to_intent() owns the filter value decoding (value_json -> value),
    # the aggregate/compare block conversion, and — importantly — the
    # COLUMN SPLIT: requested fields go to intent.fields (known) or
    # intent.unresolved_fields (unknown) against the KG field catalog.
    # parse() must NOT re-split that; it only applies the
    # include-dependent correction below.
    try:
        intent = parsed.to_intent()
    except Exception as exc:
        return ParseResult.refuse(
            RefusalFlavor.UNPARSEABLE,
            detail=f"could not convert draft to intent: {exc}",
        )

    # --- F-014: aggregate / compare intents carry no projected fields ---
    #
    # An aggregate or compare block names its own fixed projection — the
    # aggregation tool has already produced the columns the response
    # schema consumes (SupplierSpendRow.supplier_name, etc.), and the
    # pipeline's `_project_outputs` would otherwise apply entity fields
    # to the WRAPPER record. The wrapper's keys are `shape`,
    # `date_from`, ... and `rows[]`; none of them is an entity column,
    # so the requested fields render as em dashes beside an empty
    # projection. Clearing `fields` here is the deterministic
    # correction: the model emits fields alongside aggregate on the
    # reproducer regardless of the sysprompt rule (same behaviour F-018
    # records), so this must run after the LLM and cannot be a
    # prompt-text change.
    #
    # Also covers the compare block, which exhibits the same shape: its
    # wrapper carries `shape` and `suppliers[]`; projecting entity
    # columns onto it is equally meaningless.
    if intent.aggregate is not None or intent.compare is not None:
        intent.fields = []

    # --- F-058: period-anchored phrases on the by_supplier aggregate ---
    #
    # The sysprompt's by_supplier rule asks the model to compute ISO
    # bounds itself, and it names no period-anchored phrasing. The model
    # also has no reliable "today" — the endpoints reference says so
    # directly ("the LLM does NOT have a reliable sense of 'today'").
    # F-058's reproduction shows three runs producing three different
    # values (None, '2025-01-01', and once the correct year), which is
    # what guessing looks like. This correction reads the raw prompt and
    # sets the window from date.today().
    #
    # Scope: only `by_supplier` accepts a date range per
    # _AGGREGATION_PARAMS. The other aggregate ops (po_value_by_supplier,
    # po_count_by_status, open_po_summary, exposure_ranking,
    # receipt_method_distribution, top_invoices_by_amount) take no dates
    # and are untouched.
    #
    # Same class as the other post-parse corrections in this function:
    # pure Python, runs after the LLM, overrides the shape the model
    # gets wrong.
    if (
        intent.aggregate is not None
        and intent.aggregate.get("op") == "by_supplier"
    ):
        bounds = _extract_period_bounds(prompt)
        if bounds is not None:
            intent.aggregate["date_from"], intent.aggregate["date_to"] = bounds

    # --- F-016: plain-list row cap from the raw prompt ---
    #
    # The LLM has no slot for a "top N" cap on an ordinary list question
    # (DraftIntent carries no list_limit), and its prior is against
    # treating a bare integer as a cap — measured 2026-09-23, the model
    # produces a filter-less intent and the "5" is lost. Extract it
    # deterministically from the prompt, same class as
    # _is_explicit_po_list / _extract_invoice_number / the all-digit
    # CustomerAccount rewrite.
    #
    # Fires only on a PLAIN LIST intent: aggregate and compare carry their
    # own cap (aggregate.top_n), count_only produces a single number, and
    # a balance_only intent returns the account's own figures with no
    # child fetch to cap. Setting list_limit on an intent the planner
    # routes elsewhere is harmless — the injection only fires when the
    # fetcher is one of _LIMIT_CAPABLE_TOOLS — but suppressing the
    # extraction here keeps the diagnostic output clean and the
    # post-parse intent minimal.
    if (
        intent.aggregate is None
        and intent.compare is None
        and not intent.count_only
        and not intent.balance_only
    ):
        cap = _extract_list_cap(prompt)
        if cap is not None:
            intent.list_limit = cap

    # --- Explicit PO list signal (#32 fault b) ---
    #
    # #32 fault (b) needs the parser to tell two intents apart that are
    # byte-identical from the LLM's point of view — an explicit "list
    # purchase orders" (a valid bounded sample-and-disclose, #23) and a
    # PO query whose identifier the model dropped ("Is PO N complete?"
    # losing the number). Both arrive as a filter-less PurchaseOrder
    # intent, and the planner's guard refuses both unless intent.list_all
    # is True. Only an explicit list should list; the dropped-identifier
    # case must refuse, not dump 25 of ~17k unrelated POs.
    #
    # The signal is computed HERE, deterministically from the RAW PROMPT,
    # AFTER the LLM and BEFORE KG validation — the same shape as the
    # other post-parse corrections in this function
    # (strip_po_supplier_include below, plus the three helpers imported
    # from vocabulary). `_is_explicit_po_list` (defined above) is
    # pure-Python and adds NO prompt/schema text, so it does not risk
    # the parser prompt's token ceiling. Setting the flag on a non-PO
    # intent is a no-op (the planner guard is scoped to PurchaseOrder);
    # setting it on a PO intent that carries filters is also a no-op
    # (the guard short-circuits on `intent.filters` first).
    if intent.target_entity == "PurchaseOrder":
        intent.list_all = _is_explicit_po_list(prompt)

    # --- Include correction (BUG-1) ---
    from spire.nl_parser.vocabulary import strip_po_supplier_include

    if intent.include:
        intent.include = strip_po_supplier_include(
            intent.target_entity, intent.include, menu
        )

    # --- F-018: Invoice identifier from the raw prompt ---
    #
    # The model reliably produces a filter-less Invoice intent for a
    # prompt that names an invoice number directly ("show details for
    # invoice number LEE-01-1006-111"), because it treats the alphanumeric
    # token as an unknown entity reference rather than an identifier.
    # Measured 2026-09-23 — the sysprompt rule is in the prompt and the
    # model ignores it. Deterministic correction, same class as
    # _is_explicit_po_list: pure Python, runs after the LLM, injects the
    # filter the model dropped. Fires ONLY when target_entity is Invoice
    # AND no identifier of any kind is present AND the prompt contains a
    # code-shaped token after "invoice".
    if intent.target_entity == "Invoice":
        has_identifier = any(
            f.get("type") in ("supplier", "purchase_order", "invoice_number")
            for f in intent.filters
        )
        if not has_identifier:
            inv_number = _extract_invoice_number(prompt)
            if inv_number is not None:
                intent.filters.append(
                    {"type": "invoice_number", "value": inv_number}
                )

    # --- F-019: numeric CustomerAccount identifier ---
    #
    # A bare number after "account" is the account NUMBER, not a name.
    # The parser sometimes routes it into by_customer_name anyway,
    # producing a q=CustomerName='<digits>' query that returns zero rows;
    # the empty-bucket shortcut then narrates "no customer accounts
    # found." Rewrite the filter type so the tool takes the
    # AccountNumber path. Fires ONLY when target_entity is CustomerAccount
    # AND the value is a digit-only string, so genuine name queries are
    # untouched.
    if intent.target_entity == "CustomerAccount":
        rewritten = []
        for f in intent.filters:
            if (
                f.get("type") == "by_customer_name"
                and _is_all_digit_customer_value(f.get("value"))
            ):
                rewritten.append(
                    {"type": "by_account_number", "value": f["value"]}
                )
            else:
                rewritten.append(f)
        intent.filters = rewritten

    # --- KG validation ---
    #
    # Aggregate / compare intents have no target_entity on purpose; the
    # planner validates the op. Everything else goes through
    # validate_intent for entity, filter-type, and include-edge checks.
    if not (intent.aggregate or intent.compare):
        from spire.nl_parser.intent_validation import validate_intent

        refusal = validate_intent(intent, menu)
        if refusal is not None:
            return ParseResult.refuse(
                refusal.flavor,
                detail=refusal.detail,
                offending_entity=refusal.offending_entity,
                offending_filters=refusal.offending_filters,
            )

    # --- F-027: Supplier "country" column request ---
    #
    # Runs AFTER validate_intent on purpose. The field-split inside
    # validate_intent drops a field satisfied by an active include (see
    # F-017's include-catalogue branch), so `country` added before that
    # check would be dropped from both fields and unresolved_fields and
    # never reach the display. Adding it here — after KG validation, in
    # the same class of post-parse correction as _extract_invoice_number
    # and the all-digit CustomerAccount rewrite — means the field survives
    # and the display renders it.
    #
    # Scoped to Supplier roots: "country" as a projectable column is an
    # Address-include feature. The discriminator (no existing country
    # filter + the bare word "country" in the prompt) keeps a genuine
    # country FILTER request — "active suppliers in US" — untouched; the
    # filter path is preserved verbatim.
    if _has_country_column_phrasing(prompt, intent):
        if "Address" not in intent.include:
            intent.include.append("Address")
        if not any(
            str(f).lower() in ("country", "countrycode")
            for f in intent.fields
        ):
            intent.fields.append("country")

    # --- Address-satisfied column cleanup ---
    #
    # to_intent() already split the requested columns into known fields
    # and unknown unresolved_fields. This is the ONLY correction parse()
    # needs to make, because it depends on the include list, which
    # to_intent() does not see: a field that an ACTIVE include already
    # renders is neither a base column nor unavailable — the include
    # provides it. 'country' with include=['Address'] is the case that
    # motivated this: reporting it as unavailable contradicted the
    # Address column printed beside it.
    #
    # Applied to unresolved_fields only; nothing is moved from fields.
    # This is a SUBTRACTION from the unknowns, not a re-split — the
    # previous version's mistake was re-splitting, which reset
    # unresolved_fields to [] and silently lost every unknown column
    # that to_intent() had correctly identified.
    intent.unresolved_fields = list(
        getattr(intent, "unresolved_fields", None) or []
    )
    if "Address" in (intent.include or []):
        _ADDRESS_SATISFIED_FIELDS = {
            "country", "address", "city", "state",
            "formatted_address", "address_id",
        }
        intent.unresolved_fields = [
            f for f in intent.unresolved_fields
            if str(f).lower() not in _ADDRESS_SATISFIED_FIELDS
        ]

    return ParseResult.ok(intent)