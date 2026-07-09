

"""Integration tests for the KG metadata tables in Oracle.

These verify that the v1 KG, populated by scripts/rebuild_kg.sh,
is readable from Spire code via OracleClient. They are not unit tests —
they hit the real Oracle 26ai container and assume the seed scripts
have run.

If a test here fails, the most likely cause is that the SPIRE schema
is empty or stale. To repopulate:

    ./scripts/rebuild_kg.sh

Skipped if personas.yaml is missing — same gate as the other
integration tests.

Note on CLOB columns:
oracledb's async driver returns CLOB values as AsyncLOB *handles*,
not as strings. Reading them goes back over the wire, which means
the read must happen INSIDE the `async with OracleClient(...)` block,
before the connection closes. Tests below follow this discipline.
"""

import json

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.oracle.client import OracleClient


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)


async def _read_clob(value) -> str:
    """Coerce a possibly-CLOB column value to a Python str.

    MUST be called while the OracleClient connection is still open
    (i.e. inside the `async with` block that produced `value`).
    AsyncLOB.read() is a network round-trip; closing the connection
    first will raise DPY-1001 ("not connected to database").
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return await value.read()


# ----- Counts and basic existence ------------------------------------


@pytest.mark.asyncio
async def test_kg_entity_has_seven_rows():
    """Entities: Supplier, Invoice, PurchaseOrder, Buyer, Address, Site,
    Classification.

    Phase 12 added Site (supplier sites child). Phase 13 added
    Classification (supplier businessClassifications child), used by the
    has_classification edge filter.
    """
    persona = load_persona("default_dev")
    async with OracleClient(persona) as oc:
        rows = await oc.fetch_all(
            "SELECT entity_name FROM kg_entity ORDER BY entity_name"
        )
    names = [row[0] for row in rows]
    assert names == [
        "Address", "Buyer", "Classification", "Invoice", "PurchaseOrder",
        "Site", "Supplier"
    ]


@pytest.mark.asyncio
async def test_kg_table_row_counts_match_v1_1():
    """All 9 KG tables match the current row counts.

    v1.0 had 5 tables; v1.1 added 3 more (kg_pattern_binding,
    kg_entity_tool, kg_edge_tool) for the planner.
    The KG-expansion work added a 9th (kg_entity_filter) to hold filter
    definitions formerly hardcoded in the planner.
    v1.0 had 2 patterns (status_filter, country_filter_via_address);
    F2 added a 3rd (no_child_in_N_months) for the negation-by-absence
    semantic.
    kg_entity_tool is now 3 (Supplier default, Invoice default, Address
    default). The country filter has no dedicated tool; it routes through
    the default supplier fetcher with combined args.
    Phase 8 added the supplier business_relationship filter: +1 filter row
    (kg_entity_filter 11->12) and +2 vocab rows (kg_vocabulary 44->46).
    Phase 11 added the has_invoice_over_amount edge filter: +1 filter row
    (kg_entity_filter 12->13).
    Phase 12 added the has_site_in_bu edge filter (suppliers by site
    ProcurementBU): +1 entity (Site, 5->6), +1 edge (HAS_SITE, 4->5),
    +1 edge tool (HAS_SITE, 3->4), +1 filter row (kg_entity_filter
    13->14), and +10 vocab rows (supplier_site_bu, 46->56).
    Phase 13 added the has_classification edge filter (suppliers by
    business classification): +1 entity (Classification, 6->7), +1 edge
    (HAS_CLASSIFICATION, 5->6), +1 edge tool (HAS_CLASSIFICATION, 4->5),
    +1 filter row (kg_entity_filter 14->15), and +9 vocab rows
    (supplier_classification, 56->65).
    """
    persona = load_persona("default_dev")
    expected = {
        "kg_entity": 7,
        "kg_entity_field": 27,
        "kg_edge": 6,
        "kg_pattern": 3,
        "kg_vocabulary": 65,
        "kg_pattern_binding": 3,
        "kg_entity_tool": 3,
        "kg_entity_filter": 15,
        "kg_edge_tool": 5,
    }
    async with OracleClient(persona) as oc:
        for table, expected_count in expected.items():
            row = await oc.fetch_one(f"SELECT COUNT(*) FROM {table}")
            assert row is not None
            assert row[0] == expected_count, f"{table}: expected {expected_count}, got {row[0]}"


# ----- The asymmetry that crashed Track A ----------------------------


@pytest.mark.asyncio
async def test_edge_join_field_asymmetry_supplier_number_vs_supplier_id():
    """The SupplierNumber-vs-SupplierId asymmetry is encoded correctly.

    Track A's baseline runs 4 and 5 crashed because the agent passed
    supplier_number to a tool that expects supplier_id (and vice versa).
    The KG records the right join field per edge so phase 04+ tools
    can read it instead of guessing.
    """
    persona = load_persona("default_dev")
    async with OracleClient(persona) as oc:
        rows = await oc.fetch_all(
            "SELECT edge_name, from_join_field, to_join_field "
            "FROM kg_edge "
            "WHERE edge_name IN ('HAS_INVOICE', 'HAS_PURCHASE_ORDER') "
            "ORDER BY edge_name"
        )
    edges = {row[0]: (row[1], row[2]) for row in rows}
    # HAS_INVOICE joins via SupplierNumber (the invoices endpoint exposes that, not SupplierId).
    assert edges["HAS_INVOICE"] == ("SupplierNumber", "SupplierNumber")
    # HAS_PURCHASE_ORDER joins via SupplierId (the PO endpoint exposes that, not SupplierNumber).
    assert edges["HAS_PURCHASE_ORDER"] == ("SupplierId", "SupplierId")


@pytest.mark.asyncio
async def test_assigned_to_edge_crosses_pillars():
    """ASSIGNED_TO encodes the FSCM->HCM cross-pillar lookup."""
    persona = load_persona("default_dev")
    async with OracleClient(persona) as oc:
        row = await oc.fetch_one(
            "SELECT from_entity, to_entity, from_join_field, to_join_field, notes "
            "FROM kg_edge WHERE edge_name = 'ASSIGNED_TO'"
        )
        assert row is not None
        from_entity, to_entity, from_field, to_field, notes = row
        # Read CLOB-able fields inside the `async with` block.
        notes_str = await _read_clob(notes)
    # Plain assertions can happen after close — these are normal Python values.
    assert from_entity == "PurchaseOrder"
    assert to_entity == "Buyer"
    assert from_field == "BuyerId"
    assert to_field == "PersonId"
    # The notes field must explicitly mention cross-pillar so the agent sees it.
    assert "CROSS-PILLAR" in notes_str.upper()


# ----- FK relationships -----------------------------------------------


@pytest.mark.asyncio
async def test_supplier_has_four_projection_fields():
    """FK from kg_entity_field to kg_entity works; Supplier has its
    four declared projection fields (SupplierId, SupplierNumber,
    Supplier, Status)."""
    persona = load_persona("default_dev")
    async with OracleClient(persona) as oc:
        rows = await oc.fetch_all(
            "SELECT field_name FROM kg_entity_field "
            "WHERE entity_name = 'Supplier' "
            "ORDER BY field_name"
        )
    field_names = [row[0] for row in rows]
    assert field_names == ["Status", "Supplier", "SupplierId", "SupplierNumber"]


# ----- Vocabulary lookups --------------------------------------------


@pytest.mark.asyncio
async def test_country_vocabulary_resolves_us_aliases():
    """All four US-aliasing terms resolve to canonical 'US'."""
    persona = load_persona("default_dev")
    async with OracleClient(persona) as oc:
        rows = await oc.fetch_all(
            "SELECT term, canonical_value FROM kg_vocabulary "
            "WHERE vocab_kind = 'country' AND canonical_value = 'US' "
            "ORDER BY term"
        )
    terms = [row[0] for row in rows]
    # Sort order: 'US' < 'USA' < 'United States' < 'United States of America' lexicographically.
    assert terms == [
        "US",
        "USA",
        "United States",
        "United States of America",
    ]
    # Every row maps to canonical 'US'.
    assert all(row[1] == "US" for row in rows)


@pytest.mark.asyncio
async def test_po_status_open_synonyms():
    """Both 'open' and 'active' map to StatusCode 'OPEN'."""
    persona = load_persona("default_dev")
    async with OracleClient(persona) as oc:
        rows = await oc.fetch_all(
            "SELECT term, canonical_value FROM kg_vocabulary "
            "WHERE vocab_kind = 'po_status' AND canonical_value = 'OPEN' "
            "ORDER BY term"
        )
    by_term = {row[0]: row[1] for row in rows}
    assert by_term == {"active": "OPEN", "open": "OPEN"}


# ----- Patterns (parameters parse as JSON) ----------------------------


@pytest.mark.asyncio
async def test_no_child_in_n_months_pattern_has_parseable_parameters():
    """kg_pattern.parameters is stored as a JSON string. It must parse,
    and the no_child_in_N_months pattern (added in F2 for negation-by-
    absence) must declare parent, child_edge, date_field, and months_param.

    This pattern is the KG side of the 'has_no_recent_invoices' filter:
    keep parent entities whose per-iteration call returned empty.
    """
    persona = load_persona("default_dev")
    async with OracleClient(persona) as oc:
        row = await oc.fetch_one(
            "SELECT parameters FROM kg_pattern "
            "WHERE pattern_name = 'no_child_in_N_months'"
        )
        assert row is not None
        # Read CLOB inside the `async with` block; the connection must
        # still be open when AsyncLOB.read() runs.
        params_str = await _read_clob(row[0])
    params = json.loads(params_str)
    param_names = {p["name"] for p in params}
    assert param_names == {"parent", "child_edge", "date_field", "months_param"}




