"""F-001 regression — the explicit-PO-list signal is now wired end to end.

F-001: ``Intent.list_all`` was declared (``planner/models.py:141``), read by
the planner guard (``planner/planner.py:199``), and never written by any
caller. ``parser._is_explicit_po_list`` existed with no caller. Every
filter-less PurchaseOrder intent therefore refused with
``missing_identifier — PurchaseOrder root has no identifier and no explicit
list request``, even when the user typed exactly "list purchase orders".

The fix wires the deterministic helper into ``parse()``: a
PurchaseOrder-rooted Intent gets
``intent.list_all = _is_explicit_po_list(prompt)`` before KG validation,
mirroring the other post-parse corrections in the same function
(``strip_po_supplier_include`` and the three helpers imported from
``vocabulary``).

Two layers are covered:

  * Parser wiring (tests 1–4) — with a mocked LLM and a hand-built KG
    menu, a "list purchase orders" prompt produces an Intent with
    ``list_all=True``; a prompt that names a specific PO leaves it
    ``False``. No pod, no LLM, no token cost.

  * Planner guard (tests 5–6) — a filter-less PurchaseOrder Intent with
    ``list_all=False`` still refuses with MISSING_IDENTIFIER; the same
    Intent with ``list_all=True`` produces a plan. Needs the KG (the
    planner resolves the entity's fetcher tool via ``find_entity_tool``).
"""
from __future__ import annotations

import pytest

from spire.nl_parser.draft import DraftIntent
from spire.nl_parser.parser import _is_explicit_po_list, parse
from spire.nl_parser.result import RefusalError, RefusalFlavor
from spire.nl_parser.vocabulary import KGMenu
from spire.planner.models import Intent
from spire.planner.planner import generate_plan


# ─────────────────────────────────────────────────────────────────────
# Test scaffolding
# ─────────────────────────────────────────────────────────────────────


class _CannedLLM:
    """Stand-in for a LangChain chat model that returns a canned
    DraftIntent. Mirrors the shape parse() calls:
    ``llm.with_structured_output(schema, include_raw=True).invoke(...)``.
    We return the draft directly (not the ``{"parsed", "raw"}`` envelope)
    so parse() takes the bare-draft branch and skips the log_usage call."""

    def __init__(self, draft: DraftIntent) -> None:
        self._draft = draft

    def with_structured_output(self, schema, include_raw: bool = False):
        return self

    def invoke(self, messages):
        return self._draft


def _minimal_menu(*entities: str) -> KGMenu:
    """Hand-built KGMenu with just enough to satisfy parse()'s validation
    for an intent rooted on one of ``entities``. No edges, so the include
    gate in validate_intent is a no-op; no filters, so no filter validation
    fires. Avoids any pod call."""
    return KGMenu(
        target_entities=set(entities),
        filter_types=set(),
        entity_descriptions={e: e for e in entities},
    )


# ─────────────────────────────────────────────────────────────────────
# Parser wiring — pod-free
# ─────────────────────────────────────────────────────────────────────


def test_list_purchase_orders_sets_list_all_true():
    """F-001's reproducer: 'list purchase orders' must not refuse and must
    carry list_all=True into the planner."""
    draft = DraftIntent(target_entity="PurchaseOrder")
    result = parse(
        "list purchase orders",
        llm=_CannedLLM(draft),
        menu=_minimal_menu("PurchaseOrder"),
        system_prompt="(test)",
    )
    assert not result.is_refusal, result.refusal
    assert result.intent.target_entity == "PurchaseOrder"
    assert result.intent.list_all is True


def test_named_po_leaves_list_all_false():
    """A prompt that names a specific PO must NOT set list_all, even when
    the resulting intent is filter-less. The predicate checks the raw
    prompt, so a PO number present there disqualifies it. This is the
    signal that keeps 'list the lines on PO 2144' from being read as a
    bare list request."""
    draft = DraftIntent(target_entity="PurchaseOrder")
    result = parse(
        "show me PO 2144",
        llm=_CannedLLM(draft),
        menu=_minimal_menu("PurchaseOrder"),
        system_prompt="(test)",
    )
    assert not result.is_refusal, result.refusal
    assert result.intent.list_all is False


def test_non_po_intent_unaffected():
    """The flag only fires on PurchaseOrder-rooted intents. A filter-less
    Supplier intent must leave list_all at its default (False)."""
    draft = DraftIntent(target_entity="Supplier")
    result = parse(
        "list suppliers",
        llm=_CannedLLM(draft),
        menu=_minimal_menu("Supplier"),
        system_prompt="(test)",
    )
    assert not result.is_refusal, result.refusal
    assert result.intent.list_all is False


def test_is_explicit_po_list_signals():
    """The predicate itself: yes on list phrasings, no on named-PO
    phrasings and non-PO questions. Documents the contract the wiring
    relies on."""
    # Explicit list phrasings.
    assert _is_explicit_po_list("list purchase orders")
    assert _is_explicit_po_list("List all purchase orders")
    assert _is_explicit_po_list("show all POs")
    # Names one PO — not a bare list.
    assert not _is_explicit_po_list("list the lines on PO 2144")
    assert not _is_explicit_po_list("show me PO 162034")
    # Not a PO question at all.
    assert not _is_explicit_po_list("list suppliers")


# ─────────────────────────────────────────────────────────────────────
# Planner guard — needs the KG (find_entity_tool hits the live menu)
# ─────────────────────────────────────────────────────────────────────


def test_planner_filter_less_po_without_list_all_refuses():
    """The guard F-001 names: a filter-less PurchaseOrder Intent with
    list_all=False refuses with MISSING_IDENTIFIER. This is the safety-net
    case — the parser dropped the identifier and the user did not ask for
    a list."""
    intent = Intent(target_entity="PurchaseOrder", filters=[], list_all=False)
    with pytest.raises(RefusalError) as exc_info:
        generate_plan(intent)
    assert exc_info.value.refusal.flavor is RefusalFlavor.MISSING_IDENTIFIER
    assert exc_info.value.refusal.offending_entity == "PurchaseOrder"


def test_planner_filter_less_po_with_list_all_produces_plan():
    """With list_all=True, the same filter-less Intent falls through to
    the (PurchaseOrder, 'none') fetcher instead of refusing. One step;
    tool_name non-empty."""
    intent = Intent(target_entity="PurchaseOrder", filters=[], list_all=True)
    plan = generate_plan(intent)
    assert len(plan) == 1
    assert plan[0].tool_name
