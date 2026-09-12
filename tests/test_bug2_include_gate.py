"""
Regression tests for BUG-2 — the include gate in validate_intent.

BACKGROUND

The S1 bug: 'Show supplier details for PO 701337.' produces
PurchaseOrder + include=['Supplier']. There is no PurchaseOrder -> Supplier
edge, so the planner's Block 3 raised a raw KeyError at plan time and
run_graph printed it as a hard failure. validate_intent let the bad include
through because its only include check was a hardcoded string test for
'Site'.

The fix (this change) generalises the gate to check every include against
the KG's edge graph, and to also refuse includes whose edge exists but has
only a REVERSE tool (the Classification case). The chain is simulated so
two-hop includes (PurchaseOrder + ['POSchedule','PODistribution']) are not
falsely refused, and the planner's Block 2 is simulated so
edge-traversal-then-include intents (Supplier + has_open_PO + ['Buyer']) are
not falsely refused either.

These tests pin the behaviour. They are integration tests — they hit the
live KG via load_kg_menu — so they are skipped when personas.yaml is
absent, matching the pattern used by the other KG-backed tests in this
suite.
"""

from __future__ import annotations

import pytest

from spire.config import PERSONAS_FILE
from spire.nl_parser.intent_validation import validate_intent
from spire.nl_parser.vocabulary import KGMenu, load_kg_menu
from spire.planner.planner import Intent


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping KG-backed integration tests",
)


# Module-scoped fixture so the KG is read once for the whole file. Each test
# does not need its own live connection.
@pytest.fixture(scope="module")
def menu() -> KGMenu:
    return load_kg_menu()


# ── The S1 case and its direct variants ────────────────────────────────


def test_s1_case_refused(menu: KGMenu) -> None:
    """The exact S1 shape: PurchaseOrder + by_id + include=['Supplier'].

    Before the fix this returned None (validation passed), and the planner
    crashed with a raw KeyError. After the fix, it must refuse cleanly with
    UNSUPPORTED_OPERATION and offending_entity='Supplier'.
    """
    intent = Intent(
        target_entity="PurchaseOrder",
        filters=[{"type": "by_id", "value": "701337"}],
        include=["Supplier"],
    )
    refusal = validate_intent(intent, menu)
    assert refusal is not None, "S1 include should be refused"
    assert refusal.flavor.name == "UNSUPPORTED_OPERATION"
    assert refusal.offending_entity == "Supplier"


def test_supplier_before_valid_include_still_refused(menu: KGMenu) -> None:
    """A bad include at position 0 is caught regardless of what follows."""
    intent = Intent(
        target_entity="PurchaseOrder",
        filters=[{"type": "by_id", "value": "701337"}],
        include=["Supplier", "POSchedule"],
    )
    refusal = validate_intent(intent, menu)
    assert refusal is not None
    assert refusal.offending_entity == "Supplier"


def test_supplier_after_valid_include_still_refused(menu: KGMenu) -> None:
    """A bad include at position 1 is caught — the validator iterates the
    whole list, not just the first element. This was the defect the [5]
    probe in verify_bug2.py exposed."""
    intent = Intent(
        target_entity="PurchaseOrder",
        filters=[{"type": "by_id", "value": "701337"}],
        include=["POSchedule", "Supplier"],
    )
    refusal = validate_intent(intent, menu)
    assert refusal is not None
    assert refusal.offending_entity == "Supplier"


# ── Valid includes must not be refused ─────────────────────────────────


def test_buyer_include_passes(menu: KGMenu) -> None:
    """ASSIGNED_TO (PurchaseOrder -> Buyer) exists; this is the pattern the
    parser prompt explicitly steers 'include the buyer' to. Must pass."""
    intent = Intent(
        target_entity="PurchaseOrder",
        filters=[{"type": "by_id", "value": "701337"}],
        include=["Buyer"],
    )
    assert validate_intent(intent, menu) is None


def test_po_schedule_include_passes(menu: KGMenu) -> None:
    """HAS_SCHEDULE (PurchaseOrder -> POSchedule) exists."""
    intent = Intent(
        target_entity="PurchaseOrder",
        filters=[{"type": "by_id", "value": "701337"}],
        include=["POSchedule"],
    )
    assert validate_intent(intent, menu) is None


def test_po_lines_include_passes(menu: KGMenu) -> None:
    """HAS_LINE (PurchaseOrder -> PurchaseOrderLine) exists."""
    intent = Intent(
        target_entity="PurchaseOrder",
        filters=[{"type": "by_id", "value": "701337"}],
        include=["PurchaseOrderLine"],
    )
    assert validate_intent(intent, menu) is None


def test_two_hop_chain_passes(menu: KGMenu) -> None:
    """The parser prompt explicitly emits include=['POSchedule',
    'PODistribution'] for 'show PO and its distributions'. The validator
    must simulate the chain (POSchedule -> PODistribution) so the second
    hop is not falsely refused against PurchaseOrder."""
    intent = Intent(
        target_entity="PurchaseOrder",
        filters=[{"type": "by_id", "value": "701337"}],
        include=["POSchedule", "PODistribution"],
    )
    assert validate_intent(intent, menu) is None


# ── Site preservation ──────────────────────────────────────────────────


def test_site_gate_message_preserved(menu: KGMenu) -> None:
    """The Site refusal's wording and offending_entity are load-bearing for
    capability.py (the Solution/Example are keyed on
    offending_entity='SupplierSiteListing'). Must survive the general
    include gate unchanged."""
    intent = Intent(
        target_entity="Supplier",
        filters=[{"type": "name_fragment", "value": "Lee"}],
        include=["Site"],
    )
    refusal = validate_intent(intent, menu)
    assert refusal is not None
    assert refusal.flavor.name == "UNSUPPORTED_OPERATION"
    assert refusal.offending_entity == "SupplierSiteListing"


# ── The Classification case (second defect caught by this gate) ────────


def test_classification_include_refused(menu: KGMenu) -> None:
    """HAS_CLASSIFICATION (Supplier -> Classification) exists in the KG,
    but its only tool is a REVERSE filter that needs a 'classification'
    argument the executor will not supply. Planning succeeds, execution
    crashes. The gate refuses it cleanly instead."""
    intent = Intent(
        target_entity="Supplier",
        filters=[{"type": "name_fragment", "value": "Lee"}],
        include=["Classification"],
    )
    refusal = validate_intent(intent, menu)
    assert refusal is not None
    assert refusal.flavor.name == "UNSUPPORTED_OPERATION"
    assert refusal.offending_entity == "Classification"


# ── Valid includes that must not regress ───────────────────────────────


def test_contact_include_passes(menu: KGMenu) -> None:
    """HAS_CONTACT (Supplier -> Contact) has a forward tool; must pass."""
    intent = Intent(
        target_entity="Supplier",
        filters=[{"type": "name_fragment", "value": "Lee"}],
        include=["Contact"],
    )
    assert validate_intent(intent, menu) is None


def test_address_include_on_supplier_passes(menu: KGMenu) -> None:
    """Address on a Supplier target uses the expand-path special case; must
    pass and must NOT become the previous entity for a subsequent include."""
    intent = Intent(
        target_entity="Supplier",
        filters=[{"type": "name_fragment", "value": "Lee"}],
        include=["Address"],
    )
    assert validate_intent(intent, menu) is None


def test_address_then_contact_passes(menu: KGMenu) -> None:
    """Address must not chain — 'suppliers with their addresses and
    contacts' should validate. Address is the expand path; Contact chains
    from Supplier, not from Address."""
    intent = Intent(
        target_entity="Supplier",
        filters=[{"type": "name_fragment", "value": "Lee"}],
        include=["Address", "Contact"],
    )
    assert validate_intent(intent, menu) is None


# ── AR paths (control) ─────────────────────────────────────────────────


def test_ar_invoice_lines_include_passes(menu: KGMenu) -> None:
    """HAS_AR_LINE (ReceivablesInvoice -> ReceivablesInvoiceLine) exists."""
    intent = Intent(
        target_entity="ReceivablesInvoice",
        filters=[{"type": "by_id", "value": "300000248096352"}],
        include=["ReceivablesInvoiceLine"],
    )
    assert validate_intent(intent, menu) is None


def test_ar_dff_include_passes(menu: KGMenu) -> None:
    """HAS_TRANSACTION_DFF exists."""
    intent = Intent(
        target_entity="ReceivablesInvoice",
        filters=[{"type": "by_id", "value": "300000248096352"}],
        include=["ReceivablesInvoiceTransactionDFF"],
    )
    assert validate_intent(intent, menu) is None


def test_account_receipt_include_passes(menu: KGMenu) -> None:
    """HAS_ACCOUNT_RECEIPT (CustomerAccount -> AccountReceipt) exists."""
    intent = Intent(
        target_entity="CustomerAccount",
        filters=[{"type": "by_customer_name", "value": "ABC Application Software"}],
        include=["AccountReceipt"],
    )
    assert validate_intent(intent, menu) is None


# ── Block-2 simulation (edge-traversal filter then include) ────────────


def test_edge_filter_then_include_passes(menu: KGMenu) -> None:
    """Supplier + has_open_PO + include=['Buyer'].

    The planner's Block 2 walks the intent to PurchaseOrder (the target of
    has_open_PO), and Block 3 chains the Buyer include from there. The
    validator must simulate this or it will falsely refuse the include
    (Supplier -> Buyer has no edge).

    This test guards against over-refusal — the opposite failure mode from
    the S1 bug, and the one a naive per-element check would introduce.
    """
    intent = Intent(
        target_entity="Supplier",
        filters=[{"type": "has_open_PO", "value": True}],
        include=["Buyer"],
    )
    assert validate_intent(intent, menu) is None


# ── Empty include list (no-op) ─────────────────────────────────────────


def test_no_include_passes(menu: KGMenu) -> None:
    """An intent with no includes must not be affected by the new gate."""
    intent = Intent(
        target_entity="Supplier",
        filters=[{"type": "status", "value": "active"}],
        include=[],
    )
    assert validate_intent(intent, menu) is None