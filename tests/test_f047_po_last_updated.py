"""F-047 regression tests — PO last-updated-date filters.

Seven sites close the same user outcome. Tests that touch the KG or the
planner are gated on personas.yaml (matching tests/test_kg_metadata.py's
discipline). Tests that read sysprompt files or introspect signatures
run anywhere.

Pre-fix these tests fail:
  - The sysprompt tests fail on missing routing rules / present
    "set unanswerable" text.
  - The KG/planner tests fail on the missing (PurchaseOrder,
    updated_older_than_n_months) and (PurchaseOrder,
    updated_in_last_n_months) rows — the planner raises RefusalError
    on unsupported filters.
  - The tool-signature test fails on the missing args.
"""

from datetime import date
from inspect import signature
from pathlib import Path

import pytest

from spire.config import PERSONAS_FILE
from spire.nl_parser.result import RefusalError
from spire.planner.models import Intent
from spire.planner.plan_builders import _build_entity_fetcher_args
from spire.planner.planner import generate_plan


_PROCUREMENT_DIR = (
    Path(__file__).resolve().parents[1]
    / "src" / "spire" / "nl_parser" / "context" / "procurement"
)

_needs_personas = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping KG/planner tests",
)


# ── Sysprompt content (no DB) ────────────────────────────────────────


def test_po_created_date_sysprompt_teaches_updated_older_than_n_months():
    """The date rule teaches the new last-updated older-than filter.

    F-047 site 2. Pre-fix the sysprompt says "Set unanswerable=true" for
    these phrasings; the fix replaces that with a routing rule.
    """
    text = (_PROCUREMENT_DIR / "b_po_created_date.sysprompt").read_text()
    assert "updated_older_than_n_months" in text, (
        "b_po_created_date.sysprompt does not teach the updated-older "
        "filter type. See F-047 site 2."
    )


def test_po_created_date_sysprompt_teaches_updated_in_last_n_months():
    """Same file teaches the recent-window direction too."""
    text = (_PROCUREMENT_DIR / "b_po_created_date.sysprompt").read_text()
    assert "updated_in_last_n_months" in text, (
        "b_po_created_date.sysprompt does not teach the updated-recent "
        "filter type. See F-047 site 2."
    )


def test_po_created_date_sysprompt_drops_set_unanswerable_rule():
    """The old "set unanswerable=true" carve-out is removed.

    F-047 site 2. Pre-fix that instruction makes the model self-declare
    an unsupported_filter refusal for last-updated phrasings; post-fix
    the model routes them to the new filters instead.
    """
    text = (_PROCUREMENT_DIR / "b_po_created_date.sysprompt").read_text()
    assert "Set unanswerable=true with a reason naming the update-date filter" not in text, (
        "b_po_created_date.sysprompt still contains the 'set unanswerable' "
        "carve-out for last-modified phrasings. See F-047 site 2."
    )


# ── KG / planner tests (require personas.yaml) ───────────────────────


@_needs_personas
def test_po_updated_older_than_n_months_emits_last_updated_before():
    """The updated-older filter routes to `last_updated_before` on the tool.

    F-047 sites 1 & 4. Pre-fix the KG has no (PurchaseOrder,
    updated_older_than_n_months) row, `_filter_def_for` raises, and the
    args dict is empty. Post-fix the KG names `last_updated_before` and
    the widened plan_builders branch computes the cutoff.
    """
    ref = date(2026, 9, 23)
    args = _build_entity_fetcher_args(
        [{"type": "updated_older_than_n_months", "value": {"months": 12}}],
        "PurchaseOrder",
        ref,
    )
    assert args.get("last_updated_before") == "2025-09-23", (
        f"Expected last_updated_before='2025-09-23'; got {args!r}. See "
        "F-047 sites 1 and 4."
    )


@_needs_personas
def test_po_updated_in_last_n_months_emits_last_updated_after():
    """The updated-recent filter routes to `last_updated_after`."""
    ref = date(2026, 9, 23)
    args = _build_entity_fetcher_args(
        [{"type": "updated_in_last_n_months", "value": {"months": 3}}],
        "PurchaseOrder",
        ref,
    )
    assert args.get("last_updated_after") == "2026-06-23", (
        f"Expected last_updated_after='2026-06-23'; got {args!r}. See "
        "F-047 sites 1 and 4."
    )


@_needs_personas
def test_po_guard_accepts_updated_older_than_filter():
    """A last-updated-only PurchaseOrder intent is not refused.

    F-047 sites 1, 2, 4 combined. Pre-fix `_validate_intent_filters`
    raises UNSUPPORTED_FILTER for the unrecognised ftype.
    """
    intent = Intent(
        target_entity="PurchaseOrder",
        filters=[
            {"type": "updated_older_than_n_months", "value": {"months": 12}}
        ],
    )
    try:
        generate_plan(intent)
    except RefusalError as exc:
        pytest.fail(
            f"PurchaseOrder planner refused a valid updated-older intent: "
            f"{exc.refusal.detail}. See F-047 sites 1, 2, 4."
        )


@_needs_personas
def test_po_guard_accepts_updated_recent_filter():
    """The recent direction is accepted too."""
    intent = Intent(
        target_entity="PurchaseOrder",
        filters=[
            {"type": "updated_in_last_n_months", "value": {"months": 3}}
        ],
    )
    try:
        generate_plan(intent)
    except RefusalError as exc:
        pytest.fail(
            f"PurchaseOrder planner refused a valid updated-recent intent: "
            f"{exc.refusal.detail}. See F-047 sites 1, 2, 4."
        )


# ── Tool signature (no DB) ───────────────────────────────────────────


def test_tool_signature_accepts_last_updated_args():
    """search_purchase_orders exposes the two new keyword arguments.

    F-047 site 5. Pre-fix the signature has neither arg, and any call
    that passes one raises TypeError.
    """
    from spire.mcp_server.tools.purchase_orders import search_purchase_orders

    params = signature(search_purchase_orders).parameters
    assert "last_updated_before" in params, (
        "search_purchase_orders lacks last_updated_before. See F-047 site 5."
    )
    assert "last_updated_after" in params, (
        "search_purchase_orders lacks last_updated_after. See F-047 site 5."
    )


def test_server_wrapper_signature_accepts_last_updated_args():
    """The MCP server wrapper exposes the same two args.

    F-047 site 6. Pre-fix the wrapper at mcp_server/server.py does not
    forward them.
    """
    import inspect as _inspect
    from spire.mcp_server import server as srv

    # FastMCP's @mcp.tool decorator wraps the function; the underlying
    # callable is available as .fn on the FunctionTool instance.
    wrapper = getattr(srv.search_purchase_orders, "fn", srv.search_purchase_orders)
    params = _inspect.signature(wrapper).parameters
    assert "last_updated_before" in params, (
        "server.search_purchase_orders lacks last_updated_before. "
        "See F-047 site 6."
    )
    assert "last_updated_after" in params, (
        "server.search_purchase_orders lacks last_updated_after. "
        "See F-047 site 6."
    )
