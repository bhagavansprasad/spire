"""
Pydantic mirror of the planner's ``Intent`` dataclass, for the LLM's
structured output.

WHY A MIRROR (see docs/designs/feature_1_nl_parser_design.md, Q1):
The planner's ``Intent`` is a plain dataclass with a loosely typed
``filters: list[dict]``. ``with_structured_output`` needs a Pydantic schema to
lock the model onto, and the synthesizer already proves this pattern works.
So the parser emits a ``DraftIntent`` (Pydantic), then converts it to the real
``Intent`` dataclass before returning. The planner's input contract is
untouched.

WHY THE FILTER VALUE IS A STRING:
A filter's ``value`` is polymorphic across the planner's filter types — a
string ("US"), a bool (True), or a dict ({"months": 6}). A Pydantic Union of
those types behaves badly with Gemini ``with_structured_output`` (same problem
feature 5 hit with a union ``records`` field — see the 2026-06-01 handoff).
To keep the schema union-free, the LLM emits ``value_json``: a JSON-encoded
string. Conversion to ``Intent`` decodes it. This trades a tiny bit of
prompt instruction for a schema Gemini handles reliably.

DRAFT, NOT VALIDATED:
A ``DraftIntent`` is whatever the LLM produced. It is NOT yet checked against
the KG — that is Q2 direction 2 (checkpoint 3). Conversion here only handles
SHAPE (decode value_json, build the dataclass); it does not judge whether the
entity/filters are KG-valid.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from spire.planner.planner import Intent


class DraftFilter(BaseModel):
    """One filter as the LLM emits it.

    ``type`` is the filter type (e.g. "country", "has_open_PO",
    "has_no_recent_invoices"). ``value_json`` is the filter's value encoded as
    a JSON string, because the value's Python type varies by filter and a
    union schema is unreliable with Gemini. Examples of value_json the LLM
    should produce:
        country               -> "\\"US\\""        (a JSON string)
        has_open_PO           -> "true"            (a JSON bool)
        has_no_recent_invoices-> "{\\"months\\": 6}" (a JSON object)
    """

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
    """Pydantic mirror of ``Intent`` for structured LLM output.

    Mirrors the dataclass fields (``target_entity``, ``filters``, ``include``),
    plus an explicit refusal slot (``unanswerable`` / ``unanswerable_reason``).

    THE REFUSAL SLOT (the structural half of the silent-rewrite fix):
    Without a way to say "I can't", a model instructed not to salvage an
    out-of-scope prompt has nowhere to put that — and may force a wrong but
    valid-looking Intent (e.g. rewriting "contract renewals" as a bare
    Supplier query). Giving the model an explicit ``unanswerable`` flag lets
    it CHOOSE refusal rather than mangle the request. When set, the parser
    turns it into a Refusal directly, without consulting target_entity/filters.
    """

    unanswerable: bool = Field(
        default=False,
        description=(
            "Set true if the question cannot be expressed using ONLY the "
            "allowed entities and filter types — e.g. it needs an entity or "
            "filter that is not listed, an aggregation, or is too vague to "
            "pin down. When true, do NOT guess a target_entity or map the "
            "request to the closest listed entity; leave the other fields at "
            "their defaults and explain in unanswerable_reason."
        ),
    )
    unanswerable_reason: str = Field(
        default="",
        description=(
            "When unanswerable is true, a brief plain statement of what the "
            "question needs that is not available (e.g. 'needs a Contract "
            "entity, which is not supported' or 'needs spend aggregation')."
        ),
    )
    target_entity: str = Field(
        default="",
        description=(
            "The single entity the query is rooted on, e.g. 'Supplier'. Leave "
            "empty when unanswerable is true."
        ),
    )
    filters: list[DraftFilter] = Field(
        default_factory=list,
        description="Zero or more filters constraining the target entity.",
    )
    include: list[str] = Field(
        default_factory=list,
        description=(
            "Related entities to fetch alongside, e.g. ['Buyer']. Empty if none."
        ),
    )

    def to_intent(self) -> Intent:
        """Convert to the planner's ``Intent`` dataclass.

        Decodes each filter's ``value_json`` into its native Python type and
        assembles the ``{"type": ..., "value": ...}`` dicts the planner
        expects.

        LENIENT DECODING:
        ``value_json`` is meant to be JSON ("\\"US\\"", "true", "{\\"months\\":
        6}"). But models do not reliably JSON-quote bare strings — they often
        emit ``GB`` instead of ``\\"GB\\"``. Rather than refuse such values
        (which made every string-valued filter fragile), we fall back to
        treating an unparseable ``value_json`` as a plain string. So:
            "\\"US\\""        -> "US"   (JSON string)
            "true"            -> True   (JSON bool)
            "{\\"months\\":6}" -> {...}  (JSON object)
            "GB"              -> "GB"   (not JSON -> taken as the string "GB")
        The planner still validates values downstream, so leniency here costs
        nothing and removes a whole class of flaky failures.
        """
        decoded_filters: list[dict[str, Any]] = []
        for f in self.filters:
            try:
                value: Any = json.loads(f.value_json)
            except (json.JSONDecodeError, TypeError):
                # Not valid JSON — treat the raw text as a plain string value.
                value = f.value_json
            decoded_filters.append({"type": f.type, "value": value})

        return Intent(
            target_entity=self.target_entity,
            filters=decoded_filters,
            include=list(self.include),
        )
