#!/usr/bin/env python3
"""
BUG-2 verification — does validate_intent gate an include with no edge?

Read-only probe. Calls validate_intent on a curated set of (target, filters,
includes) shapes and prints what comes back.

Does NOT modify files, DB rows, or KG state. Safe to run repeatedly.

Usage:
    python scripts/verify_bug2.py 2>&1 | tee verify_bug2.txt
"""

from __future__ import annotations

from spire.nl_parser.intent_validation import validate_intent
from spire.nl_parser.vocabulary import load_kg_menu
from spire.planner.planner import Intent


# Load the KG menu once, at module level, before any show() call.
MENU = load_kg_menu()


def show(label: str, target: str, include: list, filters: list | None = None) -> None:
    """Build the intent, validate it, and print a one-line verdict."""
    filters = filters or []
    intent = Intent(target_entity=target, filters=filters, include=include)
    try:
        refusal = validate_intent(intent, MENU)
    except Exception as exc:  # noqa: BLE001 — report, never crash the probe
        print(f"  {label:<58}  EXCEPTION {type(exc).__name__}: {exc}")
        return

    if refusal is None:
        print(f"  {label:<58}  PASSED    (validate_intent returned None)")
        return

    flavor = getattr(refusal.flavor, "value", refusal.flavor)
    offending = getattr(refusal, "offending_entity", None) or "-"
    print(f"  {label:<58}  REFUSED   flavor={flavor}  offending={offending}")


def main() -> None:
    print("=== BUG-2 verification — validate_intent include-gate behaviour ===\n")

    print("[1] The S1 case — the actual bug")
    print("    Expectation: PASSED (bug) — validator lets include=['Supplier'] through")
    show(
        "PurchaseOrder + by_id + include=['Supplier']",
        "PurchaseOrder",
        ["Supplier"],
        [{"type": "by_id", "value": "701337"}],
    )

    print("\n[2] PurchaseOrder with VALID includes — control")
    print("    Expectation: all PASSED — validator must not over-refuse")
    show(
        "PurchaseOrder + include=['Buyer']                (ASSIGNED_TO)",
        "PurchaseOrder",
        ["Buyer"],
        [{"type": "by_id", "value": "701337"}],
    )
    show(
        "PurchaseOrder + include=['POSchedule']           (HAS_SCHEDULE)",
        "PurchaseOrder",
        ["POSchedule"],
        [{"type": "by_id", "value": "701337"}],
    )
    show(
        "PurchaseOrder + include=['PurchaseOrderLine']    (HAS_LINE)",
        "PurchaseOrder",
        ["PurchaseOrderLine"],
        [{"type": "by_id", "value": "701337"}],
    )
    show(
        "PurchaseOrder + include=['POSchedule','PODistribution'] (chain)",
        "PurchaseOrder",
        ["POSchedule", "PODistribution"],
        [{"type": "by_id", "value": "701337"}],
    )

    print("\n[3] The existing hardcoded Site gate — must keep working")
    print("    Expectation: REFUSED — this gate exists today")
    show(
        "Supplier + include=['Site']",
        "Supplier",
        ["Site"],
        [{"type": "name_fragment", "value": "Lee"}],
    )

    print("\n[4] Supplier with other includes — probes breadth of the defect")
    print("    Contact has HAS_CONTACT (forward tool); Address is the expand special case;")
    print("    Classification has HAS_CLASSIFICATION, but its only tool is REVERSE.")
    show(
        "Supplier + include=['Contact']                   (HAS_CONTACT)",
        "Supplier",
        ["Contact"],
        [{"type": "name_fragment", "value": "Lee"}],
    )
    show(
        "Supplier + include=['Address']                   (expand path)",
        "Supplier",
        ["Address"],
        [{"type": "name_fragment", "value": "Lee"}],
    )
    show(
        "Supplier + include=['Classification']            (edge exists, tool is REVERSE)",
        "Supplier",
        ["Classification"],
        [{"type": "name_fragment", "value": "Lee"}],
    )

    print("\n[5] Mixed valid + invalid — does the gate inspect every element?")
    print("    Expectation: REFUSED (bug if PASSED) — the bad element is not first")
    show(
        "PurchaseOrder + include=['POSchedule','Supplier']",
        "PurchaseOrder",
        ["POSchedule", "Supplier"],
        [{"type": "by_id", "value": "701337"}],
    )
    show(
        "PurchaseOrder + include=['Supplier','POSchedule']",
        "PurchaseOrder",
        ["Supplier", "POSchedule"],
        [{"type": "by_id", "value": "701337"}],
    )

    print("\n[6] AR children — control, should all PASS")
    show(
        "ReceivablesInvoice + include=['ReceivablesInvoiceLine']",
        "ReceivablesInvoice",
        ["ReceivablesInvoiceLine"],
        [{"type": "by_id", "value": "300000248096352"}],
    )
    show(
        "ReceivablesInvoice + include=['ReceivablesInvoiceTransactionDFF']",
        "ReceivablesInvoice",
        ["ReceivablesInvoiceTransactionDFF"],
        [{"type": "by_id", "value": "300000248096352"}],
    )
    show(
        "CustomerAccount + include=['AccountReceipt']",
        "CustomerAccount",
        ["AccountReceipt"],
        [{"type": "by_customer_name", "value": "ABC Application Software"}],
    )

    print("\n=== done ===")


if __name__ == "__main__":
    main()