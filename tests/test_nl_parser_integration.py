"""
Live integration tests for the NL parser (Q4).

These call REAL Gemini and read the REAL KG. A failure here means the MODEL
(or the prompt) regressed — drift, an unparseable response, or a prompt that
stopped steering the model correctly — NOT that our code is broken. The
mock-LLM tests in test_nl_parser.py cover our code.

Per the feature-1 design (Q4), these:
- are marked @pytest.mark.integration so they are separable, but are intended
  to run as part of REGULAR verification (not deselected-and-forgotten), so
  LLM regressions surface early;
- assert PROPERTIES, not exact equality. LLM output is non-deterministic, so
  exact-match would flake and get ignored. We check the shape is sane:
  the right target_entity, the expected filter types present, country
  normalized, an out-of-scope prompt refused.

Requirements to run:
    - GEMINI_API_KEY in the environment
    - the KG database reachable (load_kg_menu reads it)

Run just these:
    pytest -m integration tests/test_nl_parser_integration.py -v
"""

from __future__ import annotations

import os

import pytest

from spire.nl_parser.parser import parse
from spire.nl_parser.result import RefusalFlavor

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("GEMINI_API_KEY"),
        reason="GEMINI_API_KEY not set; live parser tests require it.",
    ),
]


def _filter_types(intent) -> set[str]:
    return {f.get("type") for f in intent.filters}


def _filter_value(intent, ftype):
    for f in intent.filters:
        if f.get("type") == ftype:
            return f.get("value")
    return None


# ─────────────────────────────────────────────────────────────────────
# In-scope prompts — should produce sane Intents (property assertions)
# ─────────────────────────────────────────────────────────────────────


def test_live_simple_country():
    """'US suppliers' -> Supplier rooted, country filter resolved to US."""
    result = parse("List all US suppliers")

    assert not result.is_refusal
    assert result.intent.target_entity == "Supplier"
    assert "country" in _filter_types(result.intent)
    assert _filter_value(result.intent, "country") == "US"


def test_live_country_synonym_normalized():
    """A country synonym ('United Kingdom') normalizes to the canonical
    code (GB) via the KG vocabulary."""
    result = parse("Show me suppliers in the United Kingdom")

    assert not result.is_refusal
    assert result.intent.target_entity == "Supplier"
    assert _filter_value(result.intent, "country") == "GB"


def test_live_open_po_with_buyer_include():
    """The original-style prompt -> Supplier + country + has_open_PO, buyer
    included."""
    result = parse(
        "List US suppliers with open purchase orders, include the buyer"
    )

    assert not result.is_refusal
    assert result.intent.target_entity == "Supplier"
    types = _filter_types(result.intent)
    assert "country" in types
    assert "has_open_PO" in types
    assert "Buyer" in result.intent.include


def test_live_no_recent_invoices_filter():
    """A negation-by-time prompt -> has_no_recent_invoices with a months
    value."""
    result = parse(
        "US suppliers with no invoices in the last 6 months"
    )

    assert not result.is_refusal
    assert result.intent.target_entity == "Supplier"
    assert "has_no_recent_invoices" in _filter_types(result.intent)
    value = _filter_value(result.intent, "has_no_recent_invoices")
    # The value should carry a months window; we don't pin the exact shape
    # beyond it referencing 6 months.
    assert value == {"months": 6} or value == 6 or "6" in str(value)


# ─────────────────────────────────────────────────────────────────────
# Out-of-scope prompts — should refuse, not salvage (the bug we fixed)
# ─────────────────────────────────────────────────────────────────────


def test_live_contract_refused_not_salvaged():
    """The regression case: 'contract renewals' must REFUSE, not silently
    become a bare supplier listing."""
    result = parse("Show me contract renewals due next quarter")

    assert result.is_refusal
    # We don't pin the exact flavor (the model self-declares via the
    # unanswerable path, which maps to UNPARSEABLE today); we DO require that
    # it refused rather than producing a Supplier Intent.
    assert result.refusal is not None


def test_live_aggregation_refused():
    """Aggregation / ranking is out of scope -> refusal, not a guessed
    Intent."""
    result = parse("What's the total open PO value by buyer? Top 5 buyers.")

    assert result.is_refusal


def test_live_vague_prompt_refused():
    """A prompt too vague to pin to an entity+filters -> refusal."""
    result = parse("Who's our best supplier?")

    assert result.is_refusal


def test_live_unsupported_amount_filter_refused():
    """A known entity with an unsupported (amount) filter -> refusal,
    whether caught by the unanswerable path or KG validation."""
    result = parse("Show suppliers with open POs over $100,000")

    assert result.is_refusal
