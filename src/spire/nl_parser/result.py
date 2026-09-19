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

    The flavors map to the points at which a prompt can fail to become an
    Intent. They are distinguished because the KG comparison already reveals
    which check tripped — so naming the flavor is nearly free and makes the
    eventual user message far more useful.

    - UNKNOWN_ENTITY: the target entity is not in kg_entity at all
      (e.g. Contract). "That kind of thing isn't in the system."
    - UNSUPPORTED_FILTER: the entity is known but a requested filter is not in
      the KG's filter set (e.g. amount_over on POs). Mirrors the planner's
      existing _validate_intent_filters check.
    - UNSUPPORTED_FIELD: the entity and any filters are fine; the prompt asks
      for a COLUMN the entity does not have (e.g. "credit rating" on
      Supplier, "created by" anywhere). Distinct from UNSUPPORTED_FILTER: a
      filter narrows WHICH records come back, a field decides WHAT IS SHOWN
      about them. Conflating the two produced the measured defect where a
      column request was refused with "not the way this question narrows
      them" and advice to narrow by country — filter guidance for a column
      problem.
    - UNSUPPORTED_OPERATION: the entity is known but the operation is not
      (e.g. aggregation / target_entity=Buyer). Mirrors the synthesizer's
      existing UnsupportedEntityError case.
    - MISSING_IDENTIFIER: the entity and the operation are both supported;
      the prompt simply never says WHICH record. Either it carries an
      unresolvable pronoun ("tax lines for that invoice line") or names no
      identifier at all ("verify a newly created AR invoice"). Spire is
      one-shot and has no conversation memory, so refusing is correct — but
      this is emphatically NOT the same as not supporting the record, and
      conflating the two is what made refusals read as breakage.
    - UNPARSEABLE: the prompt could not be turned into any structured Intent
      at all (e.g. "who's our best supplier?" — too vague to pin to an
      entity/metric). Distinct from the KG-mismatch flavors: here the
      LLM could not produce a candidate, rather than producing one the KG
      rejected.

    MISSING_IDENTIFIER was added in Phase 2 (UX-01). Before it, every one of
    these landed on UNKNOWN_ENTITY, so a supported record with a missing id
    was reported as a record type Spire "doesn't track yet" — while the
    capability sentence immediately above named that very type as supported.

    UNSUPPORTED_FIELD was added in Phase 2A (COL-03). Before it, the five
    kinds offered no home for a column problem, so the model picked the
    nearest fit — UNSUPPORTED_FILTER — and did so correctly, given the
    choices. The defect was the missing option, not the model's judgement.
    Measured 2026-07-31: `created by`, `audit columns`, `quantum flux`,
    `quantum fluxes` and `flurbles` all refused as UNSUPPORTED_FILTER, each
    carrying an accurate field-specific reason in ``detail`` that the
    message layer then discarded in favour of narrowing advice.
    """

    UNKNOWN_ENTITY = "unknown_entity"
    UNSUPPORTED_FILTER = "unsupported_filter"
    UNSUPPORTED_FIELD = "unsupported_field"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    MISSING_IDENTIFIER = "missing_identifier"
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
        offending_fields: Any COLUMNS the prompt requested that the entity
            does not have. Empty unless flavor is UNSUPPORTED_FIELD.

            Deliberately a structured list rather than leaving the message
            layer to mine ``detail`` for a column name. ``_reason_line``
            prefers structured facts over prose for a recorded reason: on the
            KG-validation path ``detail`` is a raw dump of every supported
            name, so a message built from it leaked internals to the user.
            Carrying the columns as data means the field branch can be built
            the same way as the filter branch, rather than making an
            exception for prose that is only trustworthy on one of the two
            paths that produce it.
    """

    flavor: RefusalFlavor
    detail: str
    offending_entity: Optional[str] = None
    offending_filters: list[str] = field(default_factory=list)
    offending_fields: list[str] = field(default_factory=list)


class RefusalError(Exception):
    """A planner guard declining a prompt, carrying a structured Refusal.

    The parser produces a Refusal and returns it (parse_node routes it into
    state["refusal"]). The planner guards, by contrast, run mid-plan and can
    only signal by raising — so historically they raised a bare ValueError
    whose string was printed verbatim, bypassing capability_message and its
    readable Reason/Solution/Example shape.

    RefusalError closes that gap: a guard raises RefusalError(refusal), and
    plan_node routes exc.refusal into the SAME state["refusal"] channel the
    parser uses, so the guard's decline renders identically to a parser
    decline — one refusal system, one message shape. The wrapped Refusal
    carries the flavor (MISSING_IDENTIFIER for the "which record?" guards)
    and the offending_entity; the words come from the KG-sourced guidance
    maps in capability.py, keyed on that entity, so no message text lives in
    the guard.

    Caught in plan_node BEFORE the (ValueError, NotImplementedError) catch,
    which remains for the guards not yet converted to this path.
    """

    def __init__(self, refusal: Refusal) -> None:
        self.refusal = refusal
        super().__init__(refusal.detail)


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
    # The classifier's module selection, when this ParseResult came
    # through the router (route_and_parse). The router surfaces it
    # here so downstream consumers — promptkit's diagnostic in
    # particular — can read the SAME classification that scoped
    # the parse, instead of re-running the classifier themselves
    # (which was a second LLM call per promptkit --run). None when
    # parse() was called directly without going through the router,
    # or when the router fell back to a full-context parse after a
    # ClassificationError.
    modules: Optional[list[str]] = None

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
        offending_fields: Optional[list[str]] = None,
    ) -> "ParseResult":
        """Construct a refusal result."""
        return cls(
            refusal=Refusal(
                flavor=flavor,
                detail=detail,
                offending_entity=offending_entity,
                offending_filters=list(offending_filters or []),
                offending_fields=list(offending_fields or []),
            )
        )


