"""
Result type for the NL parser.

A parse produces exactly one of two outcomes:

- a valid ``Intent`` the deterministic planner can consume, or
- a ``Refusal`` describing why the prompt is out of scope.

Design decisions this encodes (see
docs/designs/feature_1_nl_parser_design.md):

- Q3: out-of-scope prompts yield a STRUCTURED refusal naming the flavor and
  the raw facts. The user-facing capability wording is feature 8's job; this
  type carries only the structured facts (flavor + which entity/filter was the
  problem), not polished prose.
- Q5: refusal is a CHECKED RESULT, never a raised exception. The run pipeline
  gates on ``ParseResult.is_refusal`` and stops before planning when it is set.
  Raising would reintroduce the loud-failure UX that feature 8 exists to fix.

The parser never mutates or subclasses ``Intent`` — ``ParseResult`` wraps it.
This keeps the planner's input contract (``Intent``) untouched: code that
already builds Intents by hand (run_plan.py) is unaffected, and only the new
run path needs to know about ``ParseResult``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from spire.planner.planner import Intent


class RefusalFlavor(str, Enum):
    """Why a prompt could not be turned into a valid Intent.

    The three flavors map to the three points at which KG validation can fail
    (Q3). They are distinguished because the KG comparison already reveals
    which check tripped — so naming the flavor is nearly free and makes the
    eventual user message far more useful.

    - UNKNOWN_ENTITY: the target entity is not in kg_entity at all
      (e.g. Contract). "That kind of thing isn't in the system."
    - UNSUPPORTED_FILTER: the entity is known but a requested filter is not in
      the KG's filter set (e.g. amount_over on POs). Mirrors the planner's
      existing _validate_intent_filters check.
    - UNSUPPORTED_OPERATION: the entity is known but the operation is not
      (e.g. aggregation / target_entity=Buyer). Mirrors the synthesizer's
      existing UnsupportedEntityError case.
    - UNPARSEABLE: the prompt could not be turned into any structured Intent
      at all (e.g. "who's our best supplier?" — too vague to pin to an
      entity/metric). Distinct from the three KG-mismatch flavors: here the
      LLM could not produce a candidate, rather than producing one the KG
      rejected.
    """

    UNKNOWN_ENTITY = "unknown_entity"
    UNSUPPORTED_FILTER = "unsupported_filter"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    UNPARSEABLE = "unparseable"


@dataclass
class Refusal:
    """Structured description of why a prompt is out of scope.

    Carries the FACTS, not the final prose. Feature 8 turns these facts into a
    capability-framed user message, sourced from the KG. Until then, the
    blunt ``detail`` is enough to verify the parser's logic and to show a
    developer (or a basic message) what went wrong.

    Fields:
        flavor: Which class of out-of-scope this is.
        detail: Short factual reason, e.g. "target_entity 'Contract' is not a
            known KG entity" or "filter 'amount_over' is not supported on
            PurchaseOrder". Blunt by design in feature 1.
        offending_entity: The entity the prompt referenced, if one was
            identified (None when the prompt was wholly unparseable).
        offending_filters: Any filter types the prompt referenced that the KG
            does not declare. Empty unless flavor is UNSUPPORTED_FILTER.
    """

    flavor: RefusalFlavor
    detail: str
    offending_entity: Optional[str] = None
    offending_filters: list[str] = field(default_factory=list)


@dataclass
class ParseResult:
    """The outcome of parsing one prompt: an Intent XOR a Refusal.

    Exactly one of ``intent`` / ``refusal`` is set. Use the ``is_refusal``
    property at the pipeline gate (Q5):

        result = parse(prompt)
        if result.is_refusal:
            ...        # show capability message; do NOT plan/execute/synthesize
        else:
            plan = generate_plan(result.intent)
            ...
    """

    intent: Optional[Intent] = None
    refusal: Optional[Refusal] = None

    def __post_init__(self) -> None:
        # Enforce the XOR invariant loudly. This is a developer-facing guard
        # (a parser bug if it trips), distinct from the user-facing refusal
        # path — consistent with the layered-defense principle in Q5.
        if (self.intent is None) == (self.refusal is None):
            raise ValueError(
                "ParseResult must carry exactly one of intent / refusal; "
                f"got intent={self.intent!r}, refusal={self.refusal!r}."
            )

    @property
    def is_refusal(self) -> bool:
        return self.refusal is not None

    @classmethod
    def ok(cls, intent: Intent) -> "ParseResult":
        """Construct a successful result wrapping a valid Intent."""
        return cls(intent=intent)

    @classmethod
    def refuse(
        cls,
        flavor: RefusalFlavor,
        detail: str,
        offending_entity: Optional[str] = None,
        offending_filters: Optional[list[str]] = None,
    ) -> "ParseResult":
        """Construct a refusal result."""
        return cls(
            refusal=Refusal(
                flavor=flavor,
                detail=detail,
                offending_entity=offending_entity,
                offending_filters=list(offending_filters or []),
            )
        )
