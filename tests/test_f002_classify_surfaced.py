"""F-002 regression — the classifier's module list is surfaced on
ParseResult and written into the graph state, so promptkit (and any
future consumer) can read the pipeline's classification instead of
re-running the classifier for itself.

Without this fix, three things are false:

  - ParseResult does not declare `modules` as a field, so any consumer
    reaching for it gets AttributeError;
  - route_and_parse does not set .modules on the ParseResult it returns,
    even though the field would exist;
  - parse_node does not write _modules_got into the graph state, so the
    value never reaches a caller of GRAPH.ainvoke().

Each test below fails if the corresponding half of the fix is reverted.
"""

from __future__ import annotations

import dataclasses
from unittest.mock import patch

from spire.graph.pipeline import parse_node
from spire.nl_parser.result import ParseResult, RefusalFlavor
from spire.nl_parser.router import route_and_parse
from spire.nl_parser.vocabulary import KGMenu
from spire.planner.planner import Intent


def _canned_intent() -> Intent:
    return Intent(target_entity="Supplier", filters=[], include=[])


# ── The field exists ──────────────────────────────────────────────────


def test_parseresult_declares_modules_field():
    """ParseResult's declared schema includes `modules`.

    A plain dataclass accepts arbitrary attribute assignment, so a
    missing field would let `result.modules = [...]` succeed while
    silently breaking any consumer that introspects the schema (or
    serialises the result). Asserting the declared field set pins the
    interface, not just the runtime behaviour.
    """
    field_names = {f.name for f in dataclasses.fields(ParseResult)}
    assert "modules" in field_names, (
        "ParseResult does not declare `modules`; downstream consumers "
        "(promptkit's diagnostic) cannot read the classifier's choice "
        "from the result object."
    )


# ── route_and_parse attaches the classification ───────────────────────


def test_route_and_parse_attaches_modules_to_result():
    """route_and_parse sets .modules on the ParseResult it returns."""
    with patch(
        "spire.nl_parser.router.classify_modules", return_value=["supplier"]
    ) as mock_cls, patch(
        "spire.nl_parser.router.parse",
        return_value=ParseResult.ok(_canned_intent()),
    ):
        result = route_and_parse("count of suppliers", menu=KGMenu())

    assert result.modules == ["supplier"]
    mock_cls.assert_called_once()


def test_route_and_parse_multi_module_classification_preserved():
    """A multi-module classification is attached verbatim, not collapsed.

    The router's contract (D1) is a list of module names. A single-module
    result must not be silently reduced to a string.
    """
    with patch(
        "spire.nl_parser.router.classify_modules",
        return_value=["payables", "supplier"],
    ), patch(
        "spire.nl_parser.router.parse",
        return_value=ParseResult.ok(_canned_intent()),
    ):
        result = route_and_parse(
            "invoices for supplier 1252", menu=KGMenu()
        )

    assert result.modules == ["payables", "supplier"]


# ── parse_node surfaces it into graph state ───────────────────────────


def test_parse_node_writes_modules_into_state():
    """parse_node returns _modules_got on the non-refusal path."""
    canned = ParseResult.ok(_canned_intent())
    canned.modules = ["supplier"]

    with patch("spire.graph.pipeline.parse_prompt", return_value=canned):
        out = parse_node(
            {"prompt": "count of suppliers", "menu": KGMenu()}
        )

    assert out.get("_modules_got") == ["supplier"]
    assert "intent" in out
    assert "refusal" not in out


def test_parse_node_writes_modules_on_refusal_path():
    """A parser refusal also carries _modules_got — the classification ran.

    A refusal is an ANSWER: the router still classified the prompt before
    the parser declined. Promptkit's diagnostic should be able to report
    what module the router selected even when the parse refused.
    """
    canned = ParseResult.refuse(RefusalFlavor.UNPARSEABLE, detail="test")
    canned.modules = ["payables"]

    with patch("spire.graph.pipeline.parse_prompt", return_value=canned):
        out = parse_node({"prompt": "test", "menu": KGMenu()})

    assert out.get("_modules_got") == ["payables"]
    assert "refusal" in out
    assert "intent" not in out