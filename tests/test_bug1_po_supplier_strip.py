"""
Regression tests for BUG-1 — strip the un-wireable 'Supplier' include
from a PurchaseOrder intent.

BACKGROUND

"Show supplier details for PO 701337." parses to
PurchaseOrder + include=['Supplier']. There is no PurchaseOrder ->
Supplier edge in the KG (verified), and none is needed: the supplier
name, number, site and contact ride on the PO header itself and are
projected by the by_id fetcher (curl-verified; see docs/four_bugs.md
§2.1).

Before the fix, the shape reached validate_intent where BUG-2's gate
refused it — no crash, but no answer either. The user saw "Supplier is
not a valid include on PurchaseOrder" instead of JGA / JGA Progress US.

The fix adds strip_po_supplier_include to vocabulary.py, called from
parse() after the other include-correction passes and before
validate_intent. It is deterministic, KG-gated, and self-retiring: if a
future KG change declares the edge, the strip becomes a no-op and the
include is left alone.

These tests exercise strip_po_supplier_include directly (the primitive)
and parse() end-to-end via a mock LLM (the integration). They hit the
live KG via load_kg_menu, so they are skipped when personas.yaml is
absent, matching the pattern used by test_bug2_include_gate.py and
test_bug3_planner_include.py.
"""

from __future__ import annotations

import contextlib
import io

import pytest

from spire.config import PERSONAS_FILE
from spire.nl_parser.draft import DraftFilter, DraftIntent
from spire.nl_parser.parser import parse
from spire.nl_parser.vocabulary import (
    KGMenu,
    load_kg_menu,
    strip_po_supplier_include,
)


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping KG-backed integration tests",
)


@pytest.fixture(scope="module")
def menu() -> KGMenu:
    return load_kg_menu()


class MockLLM:
    """Returns a canned DraftIntent from with_structured_output().invoke()."""

    def __init__(self, draft: DraftIntent) -> None:
        self._draft = draft

    def with_structured_output(self, schema, include_raw: bool = False):
        return self

    def invoke(self, messages):
        return self._draft


def _po_draft(include: list[str]) -> DraftIntent:
    return DraftIntent(
        target_entity="PurchaseOrder",
        filters=[DraftFilter(type="by_id", value_json='"701337"')],
        include=include,
    )


def _parse_quiet(prompt: str, draft: DraftIntent, menu: KGMenu):
    """Call parse() with stderr suppressed, so the S1 debug instrumentation
    in parser.py / router.py does not clutter test output."""
    with contextlib.redirect_stderr(io.StringIO()):
        return parse(prompt, llm=MockLLM(draft), menu=menu)


# ── The primitive: strip_po_supplier_include ───────────────────────────


def test_strip_supplier_only(menu: KGMenu) -> None:
    """The S1 case: ['Supplier'] -> []."""
    result = strip_po_supplier_include("PurchaseOrder", ["Supplier"], menu)
    assert result == []


def test_strip_supplier_first(menu: KGMenu) -> None:
    """['Supplier', 'POSchedule'] -> ['POSchedule']."""
    result = strip_po_supplier_include(
        "PurchaseOrder", ["Supplier", "POSchedule"], menu
    )
    assert result == ["POSchedule"]


def test_strip_supplier_last_order_preserved(menu: KGMenu) -> None:
    """['POSchedule', 'Supplier'] -> ['POSchedule'] — survivors keep order."""
    result = strip_po_supplier_include(
        "PurchaseOrder", ["POSchedule", "Supplier"], menu
    )
    assert result == ["POSchedule"]


def test_strip_does_not_touch_other_includes(menu: KGMenu) -> None:
    """A list without Supplier is returned unchanged."""
    original = ["POSchedule", "PODistribution"]
    result = strip_po_supplier_include("PurchaseOrder", original, menu)
    assert result == original


def test_strip_does_not_touch_other_targets(menu: KGMenu) -> None:
    """Supplier is only stripped on a PurchaseOrder target."""
    original = ["Supplier", "Buyer"]
    result = strip_po_supplier_include("Supplier", original, menu)
    assert result == original


def test_strip_no_op_on_empty_include(menu: KGMenu) -> None:
    result = strip_po_supplier_include("PurchaseOrder", [], menu)
    assert result == []


def test_strip_self_retires_when_edge_is_declared() -> None:
    """If the KG ever declares PurchaseOrder -> Supplier, the strip must
    become a no-op — the include is legitimate then. Uses a synthetic
    KGMenu with the edge added, so the test does not depend on the live
    KG's current state."""
    synthetic = KGMenu(
        edge_pairs={("PurchaseOrder", "Supplier")},
    )
    result = strip_po_supplier_include(
        "PurchaseOrder", ["Supplier"], synthetic
    )
    assert result == ["Supplier"]


# ── End-to-end: parse() with the strip applied ─────────────────────────


def test_parse_s1_shape_ok_with_empty_include(menu: KGMenu) -> None:
    """The whole point of BUG-1: 'Show supplier details for PO 701337.'
    with a bad LLM draft now parses OK (no refusal), with Supplier
    stripped from the include list."""
    result = _parse_quiet(
        "Show supplier details for PO 701337.",
        _po_draft(["Supplier"]),
        menu,
    )
    assert not result.is_refusal, (
        f"expected OK, got refusal: {result.refusal.flavor.value}"
    )
    assert result.intent.target_entity == "PurchaseOrder"
    assert result.intent.include == []


def test_parse_strip_keeps_valid_sibling(menu: KGMenu) -> None:
    """When the LLM emits ['Supplier', 'POSchedule'], the strip leaves
    POSchedule intact so the answer still includes the schedules."""
    result = _parse_quiet(
        "Show supplier details and schedules for PO 701337.",
        _po_draft(["Supplier", "POSchedule"]),
        menu,
    )
    assert not result.is_refusal
    assert result.intent.include == ["POSchedule"]


def test_parse_buyer_include_untouched(menu: KGMenu) -> None:
    """A valid Buyer include is not affected by the strip — the control
    that proves the fix does not over-reach."""
    result = _parse_quiet(
        "Show PO 701337 and the buyer.",
        _po_draft(["Buyer"]),
        menu,
    )
    assert not result.is_refusal
    assert result.intent.include == ["Buyer"]


def test_parse_chain_include_untouched(menu: KGMenu) -> None:
    """The POSchedule + PODistribution chain the parser prompt explicitly
    emits is not affected."""
    result = _parse_quiet(
        "Show PO 701337 and its distributions.",
        _po_draft(["POSchedule", "PODistribution"]),
        menu,
    )
    assert not result.is_refusal
    assert result.intent.include == ["POSchedule", "PODistribution"]


def test_parse_supplier_target_untouched(menu: KGMenu) -> None:
    """A Supplier-rooted intent with a Buyer include (via has_open_PO)
    is not affected — the strip only touches PurchaseOrder targets."""
    draft = DraftIntent(
        target_entity="Supplier",
        filters=[DraftFilter(type="has_open_PO", value_json="true")],
        include=["Buyer"],
    )
    result = _parse_quiet(
        "suppliers with open purchase orders, include the buyer",
        draft,
        menu,
    )
    assert not result.is_refusal
    assert result.intent.include == ["Buyer"]


def test_parse_ar_target_untouched(menu: KGMenu) -> None:
    """A CustomerAccount intent with an AR child include is not affected."""
    draft = DraftIntent(
        target_entity="CustomerAccount",
        filters=[
            DraftFilter(
                type="by_customer_name",
                value_json='"ABC Application Software"',
            )
        ],
        include=["AccountReceipt"],
    )
    result = _parse_quiet(
        "Show receipts for ABC Application Software.",
        draft,
        menu,
    )
    assert not result.is_refusal
    assert result.intent.include == ["AccountReceipt"]