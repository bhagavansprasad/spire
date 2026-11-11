"""Phase 3, PR #1 — sample-and-disclose for PurchaseOrder.

THE DEFECT (meeting capture §1)
    get po with distribution details
refuses with `missing_identifier`. An SME would answer it (asks "which
PO?", or produces a 25-row sample and says so). Rule 28 defect.

WHAT THESE TESTS PIN
Four layers of the fix, one test each. All four go RED on the pre-fix
tree, which is the branch's first commit and the V7 evidence base.

  1. The parser sets `intent.list_all=True` for the child-entity sample
     shape, via the new sibling extractor `_is_sampleable_po_request`.
  2. The planner's existing guard then permits a plan.
  3. `PurchaseOrderResponse` gains a `narrowing_tip` field.
  4. `build_narrowing_tip` accepts a `labels_map` and, with
     `_PURCHASE_ORDER_FILTER_LABELS`, names every PurchaseOrder filter
     type — not just `status`.

Design decision recorded in the evidence file
(docs/phase-3/sample_and_disclose/purchase_order.md): code-only, no
sysprompt rule on this PR. Matches `_is_explicit_po_list`, which is
also pure-Python and has no prompt rule. Avoids V9.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from spire.nl_parser.draft import DraftIntent
from spire.nl_parser.parser import (
    _is_explicit_po_list,
    _is_sampleable_po_request,
    parse,
)
from spire.nl_parser.vocabulary import KGMenu
from spire.planner.planner import generate_plan
from spire.synthesizer.p2p import (
    PurchaseOrderResponse,
    _PURCHASE_ORDER_FILTER_LABELS,
    build_narrowing_tip,
)


# ── Test doubles ────────────────────────────────────────────────────


class _CannedLLM:
    """LLM stand-in: with_structured_output(...).invoke(...) returns the
    draft directly. Matches what parse() reads; no log_usage call."""

    def __init__(self, draft):
        self._draft = draft

    def with_structured_output(self, schema, include_raw=False):
        return self

    def invoke(self, messages):
        return self._draft


def _menu() -> KGMenu:
    """Minimal KGMenu sufficient for validate_intent to accept a
    PurchaseOrder-rooted, filter-less intent (a `list_all` intent).

    No edges: the include gate is a no-op. No filters: no filter
    validation. `PODistribution` is present as a known entity so the
    include list is not rejected for naming an unknown name."""
    return KGMenu(
        target_entities={"PurchaseOrder"},
        filter_types=set(),
        entity_descriptions={
            "PurchaseOrder": "a purchase order",
            "PODistribution": "a PO distribution",
            "POSchedule": "a PO schedule",
            "PurchaseOrderLine": "a PO line",
            "Buyer": "a buyer",
        },
    )


# ── 1. The extractor ────────────────────────────────────────────────


def test_extractor_fires_on_the_sme_prompt():
    """The SME's own phrasing. A sibling to `_is_explicit_po_list`,
    not a rename: `_is_explicit_po_list` stays scoped to explicit list
    verbs, and this fires on the child-entity shape that a "list verb"
    check misses."""
    assert _is_sampleable_po_request("get po with distribution details")
    assert _is_sampleable_po_request("get po with distribution details")


def test_extractor_does_not_fire_on_specific_po():
    """A prompt naming one PO is not a sample request; it is a
    by-id fetch. Guards against the extractor swallowing the shapes
    `_is_explicit_po_list` also correctly declines."""
    assert not _is_sampleable_po_request("show me PO 2144")
    assert not _is_sampleable_po_request("list the lines on PO 2144")


def test_extractor_does_not_fire_without_a_child():
    """`get all POs` (no child) is not the child-entity shape; the
    extractor targets prompts that name a child. The no-child case is
    already handled by `_is_explicit_po_list`."""
    assert not _is_sampleable_po_request("get all purchase orders")


def test_extractor_is_orthogonal_to_explicit_list():
    """`_is_explicit_po_list` and `_is_sampleable_po_request` are
    siblings, not the same function under two names. The SME prompt
    fires one and not the other; a bare "list all POs" fires the other
    and not this one."""
    p = "get po with distribution details"
    assert _is_sampleable_po_request(p) is True
    assert _is_explicit_po_list(p) is False

    q = "list all purchase orders"
    assert _is_explicit_po_list(q) is True
    assert _is_sampleable_po_request(q) is False


# ── 2. The parser sets list_all via the extractor ───────────────────


def test_parse_sets_list_all_on_child_entity_shape():
    """End-to-end through parse(). The mock returns an empty draft —
    no filters, no include — which is what the model produces today
    for this prompt; the extractor is what fixes it."""
    draft = DraftIntent(target_entity="PurchaseOrder")
    result = parse(
        "get po with distribution details",
        llm=_CannedLLM(draft),
        menu=_menu(),
        system_prompt="(test)",
    )
    assert not result.is_refusal, (
        f"parse refused: {getattr(result, 'refusal', None)!r}"
    )
    assert result.intent.target_entity == "PurchaseOrder"
    assert result.intent.list_all is True
    # The child named in the prompt lands in include.
    assert "PODistribution" in result.intent.include


def test_parse_still_sets_list_all_via_explicit_list():
    """Regression guard: `_is_explicit_po_list`'s job is not
    duplicated by the new extractor and not lost to it."""
    draft = DraftIntent(target_entity="PurchaseOrder")
    result = parse(
        "list all purchase orders",
        llm=_CannedLLM(draft),
        menu=_menu(),
        system_prompt="(test)",
    )
    assert not result.is_refusal
    assert result.intent.list_all is True


# ── 3. The planner permits the plan ─────────────────────────────────


def test_planner_produces_a_plan_for_a_list_all_po_intent():
    """The planner's guard (`planner.py:211`) already permits this when
    `intent.list_all` is True. This pins that wiring survives.
    Requires the live KG (find_entity_tool resolves the fetcher)."""
    from spire.planner.models import Intent

    intent = Intent(
        target_entity="PurchaseOrder", filters=[], list_all=True,
    )
    plan = generate_plan(intent)
    assert len(plan) == 1
    assert plan[0].tool_name == "search_purchase_orders"


# ── 4. The tip: field, parameter, labels ────────────────────────────


def test_purchase_order_response_has_a_narrowing_tip_field():
    """The response type must carry the field; the display renderer
    (`formatters.py:169`) reads it via getattr and would silently print
    no tip without the field existing."""
    fields = PurchaseOrderResponse.model_fields
    assert "narrowing_tip" in fields, (
        "PurchaseOrderResponse lacks `narrowing_tip`; the render branch "
        "will have nothing to display."
    )


def test_purchase_order_filter_labels_covers_all_types():
    """The labels map must name every PurchaseOrder filter type the
    KG declares for the entity. The Supplier map
    (`_SUPPLIER_FILTER_LABELS`) drops any filter not on its list, so
    a PO tip built from that map would name a subset and silently
    under-report the filters. This test derives the expected set from
    the same KG accessor `synthesize_response` reads — not from a
    hand-written literal, which is what this test's first version did
    and which rotted on first run (it missed the two relative-date
    filters that are genuinely PurchaseOrder entity-level filters:
    `older_than_n_months` and `created_in_last_n_months`). Deriving
    from the KG makes the assertion stronger: it catches map drift
    whenever the KG gains or loses a filter type."""
    from spire.planner.kg_db import _entity_level_filter_types
    expected = _entity_level_filter_types().get("PurchaseOrder", set())
    # A sanity floor: the KG genuinely has PurchaseOrder entity-level
    # filters, and status + supplier are two of them. If the KG is
    # unreachable this assertion surfaces a clear error rather than
    # passing on an empty set.
    assert {"status", "supplier"} <= expected, (
        f"KG accessor returned an unexpected PurchaseOrder filter "
        f"set: {sorted(expected)}"
    )
    assert set(_PURCHASE_ORDER_FILTER_LABELS) == expected, (
        f"labels map keys {sorted(_PURCHASE_ORDER_FILTER_LABELS)} do "
        f"not match KG PurchaseOrder entity-level filters "
        f"{sorted(expected)}"
    )


def test_build_narrowing_tip_accepts_a_labels_map():
    """The `labels_map` parameter is the extension the meeting capture
    §3 names. Without it, the tip for a PurchaseOrder filter set
    (`status`, `supplier`, `created_before`) names only `status`."""
    tip = build_narrowing_tip(
        {"status", "supplier", "created_before"},
        total=3367,
        entity_label="purchase orders",
        labels_map=_PURCHASE_ORDER_FILTER_LABELS,
    )
    assert "purchase orders" in tip
    assert "3,367" in tip
    for word in ("status", "supplier", "creation date"):
        assert word in tip.lower(), (
            f"expected {word!r} in tip: {tip!r}"
        )


def test_build_narrowing_tip_dedupes_shared_labels():
    """Four PurchaseOrder filters share the label "creation date";
    two share "last-updated date". The tip must name each once, not
    once per filter type. V1 caught this: the tip came out
    "creation date, creation date, creation date, creation date,
    last-updated date, last-updated date, lifecycle, status,
    supplier"."""
    tip = build_narrowing_tip(
        {
            "created_before", "created_since",
            "older_than_n_months", "created_in_last_n_months",
            "updated_older_than_n_months",
            "updated_in_last_n_months",
            "status", "supplier",
        },
        total=17620,
        entity_label="purchase orders",
        labels_map=_PURCHASE_ORDER_FILTER_LABELS,
    )
    assert tip.count("creation date") == 1, (
        f"'creation date' appears more than once in tip: {tip!r}"
    )
    assert tip.count("last-updated date") == 1, (
        f"'last-updated date' appears more than once in tip: {tip!r}"
    )
    for word in ("status", "supplier"):
        assert word in tip.lower(), (
            f"expected {word!r} in tip: {tip!r}"
        )


def test_synthesize_response_po_tip_excludes_lifecycle_status():
    """`lifecycle_status` must not appear in the PO sample tip.

    The exclusion is done by the CALLER — `synthesize_response`'s
    two PO branches build the filter set as
    `{ft for ft in po_filters if ft not in {"by_id",
    "lifecycle_status"}}` — not by `build_narrowing_tip` itself.
    So the test must be at the `synthesize_response` level, where
    the caller-side exclusion lives. An earlier version of this
    test called `build_narrowing_tip` with a set that already had
    lifecycle_status removed, which was a tautology: it stayed
    green when the caller-side exclusion was missing (V1 caught
    exactly that: the live tip still named 'lifecycle' after a
    green test run)."""
    from spire.synthesizer.synthesizer import synthesize_response

    # A minimal PO sample: 1 row, matching the executor's actual
    # shape. The local plain-PO path builds the response and the
    # tip without an LLM.
    outputs = {
        "open_pos": [
            {
                "POHeaderId": 300000347075721,
                "OrderNumber": "1",
                "Status": "Closed",
                "StatusCode": "CLOSED",
                "Supplier": "CAB USA Supplier-1",
                "SupplierId": 300000345317223,
                "Buyer": "Someone",
                "BuyerId": 300000345000001,
            }
        ]
    }
    truncation = {
        "open_pos": {
            "total_available": 17620,
            "truncated": True,
            "limit_applied": 25,
        }
    }
    response = synthesize_response(
        outputs,
        target_entity="PurchaseOrder",
        llm=None,
        truncation_by_step=truncation,
    )
    tip = response.narrowing_tip
    # The excluded filters must not appear.
    assert "lifecycle" not in tip.lower(), (
        f"lifecycle_status must not appear in the tip: {tip!r}"
    )
    assert "po number" not in tip.lower(), (
        f"by_id (PO number) must not appear in the tip: {tip!r}"
    )
    # Sibling filters still named — proves the tip is populated,
    # so the exclusion assertions are not passing on an empty tip.
    assert "status" in tip.lower()
    assert "supplier" in tip.lower()
