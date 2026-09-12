#!/usr/bin/env python3
"""
BUG-4 verification — does the Reason line use the parser's specific
detail for an unsupported_filter refusal, or the generic narrowing
sentence?

Read-only. Constructs hand-built Refusals, calls capability_message,
and prints the Reason line (the first paragraph of the message).

The expected outcomes are documented inline. Sections [1] and [4] are
the ones we care about: [1] should currently show the generic sentence
(BUG-4), and after the fix should show the specific detail.

Usage:
    python scripts/verify_bug4.py 2>&1 | tee verify_bug4.txt
"""

from __future__ import annotations

from spire.nl_parser.capability import capability_message
from spire.nl_parser.result import Refusal, RefusalFlavor
from spire.nl_parser.vocabulary import load_kg_menu


MENU = load_kg_menu()


def show(label: str, refusal: Refusal, expected: str) -> None:
    """Print the Reason line of the capability message for one refusal."""
    msg = capability_message(refusal, MENU)
    reason = msg.split("\n\n")[0]
    # reason is "Reason:   <text>"; strip the label to compare.
    reason_text = reason.replace("Reason:", "").strip()
    print(f"  {label}")
    print(f"    EXPECTED: {expected}")
    print(f"    ACTUAL:   {reason_text}")
    print()


def main() -> None:
    print("=== BUG-4 verification — capability message Reason line ===\n")

    # ── [1] The S1 self-declared shape ─────────────────────────────────
    # Flavor UNSUPPORTED_FILTER, no offending_filters (that's what the
    # self-declared path produces), specific detail. Currently renders
    # the generic "not the way this question narrows them". After the
    # fix, should render the specific detail verbatim.
    print("[1] UNSUPPORTED_FILTER + empty offending_filters + specific detail")
    show(
        "The S1 self-declared refusal shape",
        Refusal(
            flavor=RefusalFlavor.UNSUPPORTED_FILTER,
            detail=(
                "Cannot retrieve supplier details for a specific purchase "
                "order because Supplier is not an allowed include on "
                "PurchaseOrder."
            ),
            offending_entity="Supplier",
        ),
        "After fix: the specific detail verbatim; before fix: the generic "
        "narrowing sentence.",
    )

    # ── [2] Control: KG-validation path WITH offending_filters ─────────
    # The raw-dump style. offending_filters is populated, so the
    # structured rendering fires — the detail is NEVER shown here. Must
    # be unchanged by the fix.
    print("[2] UNSUPPORTED_FILTER + offending_filters (control)")
    show(
        "The KG-validation path shape (structured filters present)",
        Refusal(
            flavor=RefusalFlavor.UNSUPPORTED_FILTER,
            detail="raw dump that must never reach a user",
            offending_entity="Supplier",
            offending_filters=["net_30_terms"],
        ),
        "'I can look up suppliers, but not by net 30 terms.' — unchanged "
        "by the fix.",
    )

    # ── [3] Control: UNSUPPORTED_OPERATION + detail ────────────────────
    # Already reads detail first (per the docstring). Confirms the
    # existing behaviour the fix mirrors.
    print("[3] UNSUPPORTED_OPERATION + detail (control — already works)")
    show(
        "The gate-refused S1 shape (UNSUPPORTED_OPERATION)",
        Refusal(
            flavor=RefusalFlavor.UNSUPPORTED_OPERATION,
            detail="Supplier is not a valid include on PurchaseOrder.",
            offending_entity="Supplier",
        ),
        "The detail verbatim — unchanged by the fix.",
    )

    # ── [4] Edge case: UNSUPPORTED_FILTER, no filters, no detail ───────
    # The fix must not break the fallback. With no detail, the generic
    # sentence still fires.
    print("[4] UNSUPPORTED_FILTER + empty filters + empty detail (edge)")
    show(
        "No detail — falls back to the generic sentence",
        Refusal(
            flavor=RefusalFlavor.UNSUPPORTED_FILTER,
            detail="",
            offending_entity="Supplier",
        ),
        "'I can look up suppliers, but not the way this question narrows "
        "them.' — unchanged by the fix.",
    )

    print("=== done ===")


if __name__ == "__main__":
    main()