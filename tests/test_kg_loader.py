"""Integration tests for spire.kg.loader.

These verify the v1 KG can be loaded from Oracle as a markdown bundle.
They hit the real Oracle 26ai container and assume the seed scripts
have run (scripts/rebuild_kg.sh).

Skipped if personas.yaml is missing.
"""

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.kg.loader import load_kg_context


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)


@pytest.mark.asyncio
async def test_load_kg_context_returns_non_empty_markdown():
    persona = load_persona("default_dev")
    bundle = await load_kg_context(persona)
    assert isinstance(bundle, str)
    assert len(bundle) > 500  # Even a thin v1 should produce a substantial bundle.


@pytest.mark.asyncio
async def test_kg_context_contains_all_top_level_sections():
    persona = load_persona("default_dev")
    bundle = await load_kg_context(persona)
    # All four top-level sections must be present.
    assert "## Entities" in bundle
    assert "## Edges (Relationships)" in bundle
    assert "## Query Patterns" in bundle
    assert "## Vocabulary" in bundle


@pytest.mark.asyncio
async def test_kg_context_lists_all_five_entities():
    persona = load_persona("default_dev")
    bundle = await load_kg_context(persona)
    for entity in ("Supplier", "Invoice", "PurchaseOrder", "Buyer", "Address"):
        assert entity in bundle, f"Entity {entity} missing from bundle"


@pytest.mark.asyncio
async def test_kg_context_encodes_supplier_id_vs_supplier_number_asymmetry():
    """The whole point of the KG is to make this asymmetry visible to the LLM.

    HAS_INVOICE joins via SupplierNumber.
    HAS_PURCHASE_ORDER joins via SupplierId.
    Both must appear in the bundle.
    """
    persona = load_persona("default_dev")
    bundle = await load_kg_context(persona)
    # Both edge names must appear.
    assert "HAS_INVOICE" in bundle
    assert "HAS_PURCHASE_ORDER" in bundle
    # The asymmetry must be visible somewhere.
    assert "SupplierNumber" in bundle
    assert "SupplierId" in bundle


@pytest.mark.asyncio
async def test_kg_context_includes_cross_pillar_note_on_assigned_to():
    persona = load_persona("default_dev")
    bundle = await load_kg_context(persona)
    assert "ASSIGNED_TO" in bundle
    # The notes field for ASSIGNED_TO should carry the cross-pillar marker.
    assert "CROSS-PILLAR" in bundle.upper()


@pytest.mark.asyncio
async def test_kg_context_includes_us_country_vocabulary():
    persona = load_persona("default_dev")
    bundle = await load_kg_context(persona)
    # The vocabulary section should map several US-aliasing terms to 'US'.
    assert "United States" in bundle
    # The canonical value (also "US") should appear at least twice
    # (once as a term, once as a canonical value).
    assert bundle.count("US") >= 2


@pytest.mark.asyncio
async def test_kg_context_includes_all_three_patterns():
    """v1.0 had 2 patterns; F2 added a 3rd (no_child_in_N_months) for
    the negation-by-absence semantic. All three must appear in the
    loaded bundle.

    Note: cross_pillar_lookup was in the original v1 plan but was
    dropped before implementation (the cross-pillar edge ASSIGNED_TO
    carries its own notes; no separate pattern needed). no_Y_in_N_months
    was renamed to no_child_in_N_months for clarity (parent/child terms
    match the binding's vocabulary).
    """
    persona = load_persona("default_dev")
    bundle = await load_kg_context(persona)
    for pattern in (
        "status_filter",
        "country_filter_via_address",
        "no_child_in_N_months",
    ):
        assert pattern in bundle, f"Pattern {pattern} missing from bundle"


@pytest.mark.asyncio
async def test_kg_context_pattern_mechanics_included():
    """The mechanics field (CLOB) must come through readable in the bundle."""
    persona = load_persona("default_dev")
    bundle = await load_kg_context(persona)
    # Look for distinctive content from the no_child_in_N_months mechanics step
    # ("Compute the cutoff date: today minus months_param months.")
    assert "cutoff" in bundle.lower()
