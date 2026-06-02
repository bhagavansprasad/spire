"""
Feature 8 — graceful, capability-framed refusal.

Two things feature 8 adds on top of feature 1's structured refusal:

1. derive_flavor: a self-declared ``unanswerable`` draft no longer collapses to
   UNPARSEABLE. The flavor is re-derived from the draft + KG menu —
   UNKNOWN_ENTITY for an entity the KG doesn't track (contracts),
   UNSUPPORTED_OPERATION for aggregation/ranking, UNPARSEABLE only as the
   honest fallback for genuinely vague prompts.

2. capability_message: the user-facing line leads with what Spire CAN do
   (sourced from the KG menu, so it never goes stale) and then says why this
   prompt is outside it.

These tests are pure unit tests over the menu fixture — no LLM, no DB.
"""

from __future__ import annotations

import pytest

from spire.nl_parser.capability import capability_message, derive_flavor
from spire.nl_parser.result import Refusal, RefusalFlavor
from spire.nl_parser.vocabulary import KGMenu


@pytest.fixture
def menu() -> KGMenu:
    """Mirrors the live KG (same shape as test_nl_parser.py's fixture)."""
    return KGMenu(
        target_entities={"Supplier"},
        filter_types={"country", "has_open_PO", "has_no_recent_invoices"},
        entity_descriptions={
            "Supplier": "A vendor or service provider.",
            "Invoice": "An accounts-payable invoice.",
            "PurchaseOrder": "A purchase order issued to a supplier.",
            "Buyer": "The purchasing agent assigned to a PO.",
            "Address": "A supplier's address.",
        },
        country_terms={"US": "US", "United Kingdom": "GB", "India": "IN"},
    )


# ─────────────────────────────────────────────────────────────────────
# derive_flavor — the self-declared-refusal flavor fix
# ─────────────────────────────────────────────────────────────────────


def test_explicit_target_entity_unknown_to_kg(menu):
    """A self-declared refusal that still left a target_entity the KG doesn't
    know is UNKNOWN_ENTITY (not UNPARSEABLE)."""
    assert (
        derive_flavor("needs a Contract entity", "Contract", menu)
        == RefusalFlavor.UNKNOWN_ENTITY
    )


def test_reason_names_unknown_entity(menu):
    """Even with an empty target_entity, an entity named in the reason that the
    KG doesn't know yields UNKNOWN_ENTITY."""
    assert (
        derive_flavor("needs a Contract entity, not supported", "", menu)
        == RefusalFlavor.UNKNOWN_ENTITY
    )


def test_aggregation_reason_is_unsupported_operation(menu):
    assert (
        derive_flavor("needs spend aggregation", "", menu)
        == RefusalFlavor.UNSUPPORTED_OPERATION
    )


def test_aggregation_wins_over_stray_capitalized_token(menu):
    """A reason like 'total open PO value by buyer' mentions the capitalized
    'PO' (unknown to the KG) but is fundamentally aggregation. The operation
    signal must win, so the flavor is UNSUPPORTED_OPERATION, not
    UNKNOWN_ENTITY."""
    assert (
        derive_flavor("total open PO value by buyer, top 5", "", menu)
        == RefusalFlavor.UNSUPPORTED_OPERATION
    )


def test_vague_reason_falls_back_to_unparseable(menu):
    assert (
        derive_flavor("too vague to pin to a specific entity", "", menu)
        == RefusalFlavor.UNPARSEABLE
    )


def test_known_entity_in_reason_does_not_trigger_unknown(menu):
    """A reason mentioning only KNOWN entities must not be misread as
    UNKNOWN_ENTITY — it falls through to UNPARSEABLE."""
    assert (
        derive_flavor("Supplier query but no clear filter", "", menu)
        == RefusalFlavor.UNPARSEABLE
    )


# ─────────────────────────────────────────────────────────────────────
# capability_message — what Spire CAN do, then why this prompt is outside
# ─────────────────────────────────────────────────────────────────────


def test_message_leads_with_capabilities_from_kg(menu):
    """The message names the KG's real target entities and filter types, so it
    tracks the KG rather than a hand-written list."""
    r = Refusal(flavor=RefusalFlavor.UNKNOWN_ENTITY, detail="x",
                offending_entity="Contract")
    msg = capability_message(r, menu)
    assert "Supplier" in msg
    assert "country" in msg
    # And it names what's missing.
    assert "Contract" in msg


def test_message_for_aggregation_mentions_aggregation(menu):
    r = Refusal(flavor=RefusalFlavor.UNSUPPORTED_OPERATION, detail="x")
    msg = capability_message(r, menu)
    assert "aggregation" in msg.lower() or "ranking" in msg.lower()


def test_message_for_unsupported_filter_names_the_filter(menu):
    r = Refusal(flavor=RefusalFlavor.UNSUPPORTED_FILTER, detail="x",
                offending_entity="PurchaseOrder",
                offending_filters=["amount_over"])
    msg = capability_message(r, menu)
    assert "amount_over" in msg


def test_message_tracks_kg_when_new_target_added(menu):
    """If the KG later declares a new target entity, the capability sentence
    reflects it with no code change — proves the message is KG-sourced."""
    menu.target_entities.add("Contract")
    menu.entity_descriptions["Contract"] = "A contract."
    r = Refusal(flavor=RefusalFlavor.UNPARSEABLE, detail="x")
    msg = capability_message(r, menu)
    assert "Contract" in msg
