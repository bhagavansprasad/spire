#!/usr/bin/env python3
"""
BUG-1 verification — does parse() strip a bad Supplier include on a PO?

BUG-1 is the parser coverage gap: "Show supplier details for PO X" parses
to PurchaseOrder + include=['Supplier']. No PurchaseOrder -> Supplier edge
exists, and none is needed — the supplier name, number, site and contact
all ride on the PO header itself (curl-verified against /purchaseOrders).

CURRENT state (before the fix):
  parse() lets the bad include through. BUG-2's validate_intent gate then
  refuses it. So the S1 prompt is now a clean refusal, not a crash, but
  it still does not ANSWER.

TARGET state (after the fix):
  parse() strips 'Supplier' from the include list BEFORE validate_intent
  runs, so the intent proceeds with include=[] (or the remaining valid
  includes, minus Supplier). The base by_id fetch then answers.

This script injects a canned DraftIntent via a mock LLM, so it exercises
the parse path deterministically regardless of the real LLM's behaviour.

Read-only. Does not modify files, DB rows, or KG state.

Usage:
    python scripts/verify_bug1.py 2>&1 | tee verify_bug1.txt
"""

from __future__ import annotations

import contextlib
import io

from spire.nl_parser.draft import DraftFilter, DraftIntent
from spire.nl_parser.parser import parse
from spire.nl_parser.vocabulary import load_kg_menu


MENU = load_kg_menu()


class MockLLM:
    """Returns a canned DraftIntent from with_structured_output().invoke()."""

    def __init__(self, draft: DraftIntent) -> None:
        self._draft = draft

    def with_structured_output(self, schema, include_raw: bool = False):
        return self

    def invoke(self, messages):
        return self._draft


def attempt(label: str, prompt: str, draft: DraftIntent) -> None:
    """Run parse() on the mock; print the outcome. stderr is silenced so
    the parser/router debug prints don't interleave with this script's
    own output."""
    with contextlib.redirect_stderr(io.StringIO()):
        result = parse(prompt, llm=MockLLM(draft), menu=MENU)

    print(f"  {label}")
    if result.is_refusal:
        fl = result.refusal.flavor.value
        off = result.refusal.offending_entity or "-"
        print(f"    REFUSED  flavor={fl}  offending={off}")
    else:
        intent = result.intent
        print(
            f"    OK       target={intent.target_entity!r}  "
            f"include={intent.include!r}"
        )


def _po_draft(include: list[str]) -> DraftIntent:
    return DraftIntent(
        target_entity="PurchaseOrder",
        filters=[DraftFilter(type="by_id", value_json='"701337"')],
        include=include,
    )


def main() -> None:
    print("=== BUG-1 verification — PO + Supplier include strip ===\n")
    print("Each case injects a canned DraftIntent via a mock LLM, so the")
    print("outcome is deterministic and does not depend on the real LLM.")
    print()

    print("[1] The S1 shape — strip target")
    print("    BEFORE FIX: REFUSED (unsupported_operation, offending=Supplier)")
    print("    AFTER FIX:  OK with include=[]")
    attempt(
        "PurchaseOrder + by_id + ['Supplier']",
        "Show supplier details for PO 701337.",
        _po_draft(["Supplier"]),
    )

    print("\n[2] Supplier first, then a valid include — strip one, keep one")
    print("    BEFORE FIX: REFUSED")
    print("    AFTER FIX:  OK with include=['POSchedule']")
    attempt(
        "PurchaseOrder + by_id + ['Supplier', 'POSchedule']",
        "Show supplier details and schedules for PO 701337.",
        _po_draft(["Supplier", "POSchedule"]),
    )

    print("\n[3] Same, reversed order — order preservation of survivors")
    print("    BEFORE FIX: REFUSED")
    print("    AFTER FIX:  OK with include=['POSchedule']")
    attempt(
        "PurchaseOrder + by_id + ['POSchedule', 'Supplier']",
        "Show schedules and supplier details for PO 701337.",
        _po_draft(["POSchedule", "Supplier"]),
    )

    print("\n[4] Control — valid Buyer include, must NOT be touched")
    attempt(
        "PurchaseOrder + by_id + ['Buyer']",
        "Show PO 701337 and the buyer.",
        _po_draft(["Buyer"]),
    )

    print("\n[5] Control — chain include, must NOT be touched")
    attempt(
        "PurchaseOrder + by_id + ['POSchedule', 'PODistribution']",
        "Show PO 701337 and its distributions.",
        _po_draft(["POSchedule", "PODistribution"]),
    )

    print("\n[6] Control — Supplier target with a valid Buyer include")
    print("    (via has_open_PO — the Block-2 sim case)")
    attempt(
        "Supplier + has_open_PO + ['Buyer']",
        "suppliers with open purchase orders, include the buyer",
        DraftIntent(
            target_entity="Supplier",
            filters=[DraftFilter(type="has_open_PO", value_json="true")],
            include=["Buyer"],
        ),
    )

    print("\n[7] Control — AR target, must NOT be touched")
    attempt(
        "CustomerAccount + by_customer_name + ['AccountReceipt']",
        "Show receipts for ABC Application Software.",
        DraftIntent(
            target_entity="CustomerAccount",
            filters=[
                DraftFilter(
                    type="by_customer_name",
                    value_json='"ABC Application Software"',
                )
            ],
            include=["AccountReceipt"],
        ),
    )

    print("\n[8] Control — empty include, must be unchanged")
    attempt(
        "PurchaseOrder + by_id + []",
        "Show PO 701337.",
        _po_draft([]),
    )

    print("\n=== done ===")


if __name__ == "__main__":
    main()