#!/usr/bin/env python3
"""
BUG-3 verification — does the planner raise a raw KeyError for an
unsatisfiable include, and does plan_node swallow it correctly?

Read-only probe. Calls generate_plan and plan_node directly with
hand-built Intents, and prints what comes back.

Two questions it answers:
  1. Does generate_plan raise KeyError (bug) or RefusalError (correct)
     when an include has no declared edge?
  2. Does plan_node route that exception into {"refusal": ...} (correct),
     or into {"error": ..., "plan_refusal": True} (correct), or into
     {"error": ...} with NO plan_refusal flag (BUG-3)?

Does NOT modify files, DB rows, or KG state. Safe to run repeatedly.

Usage:
    python scripts/verify_bug3.py 2>&1 | tee verify_bug3.txt
"""

from __future__ import annotations

from spire.planner.planner import Intent, generate_plan
from spire.nl_parser.result import RefusalError


def show_generate_plan(label: str, intent: Intent) -> None:
    """Call generate_plan and describe what comes back."""
    print(f"  {label}")
    try:
        plan = generate_plan(intent)
    except RefusalError as exc:
        fl = getattr(exc.refusal.flavor, "value", exc.refusal.flavor)
        print(f"      RESULT: RefusalError (CORRECT)")
        print(f"        flavor={fl}  offending={exc.refusal.offending_entity}")
        return
    except KeyError as exc:
        print(f"      RESULT: KeyError (BUG-3)")
        print(f"        {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        print(f"      RESULT: {type(exc).__name__} (unexpected)")
        print(f"        {exc}")
        return

    print(f"      RESULT: Plan with {len(plan)} step(s)")
    for step in plan:
        print(f"        Step {step.step_id}: {step.tool_name}  args={step.tool_args}")


def show_plan_node(label: str, intent: Intent) -> None:
    """Call plan_node with a synthetic state and describe the dict it returns."""
    from spire.graph.pipeline import plan_node

    print(f"  {label}")
    state = {"intent": intent}
    try:
        result = plan_node(state)
    except Exception as exc:  # noqa: BLE001
        print(f"      plan_node RAISED {type(exc).__name__}: {exc}")
        return

    if "refusal" in result:
        r = result["refusal"]
        fl = getattr(r.flavor, "value", r.flavor)
        print(f"      RESULT: {{'refusal': Refusal}}  (CORRECT — routes to "
              f"the refusal channel)")
        print(f"        flavor={fl}  offending={r.offending_entity}")
    elif "error" in result:
        pr = result.get("plan_refusal", "<MISSING>")
        err = result["error"]
        print(f"      RESULT: {{'error': ...}}")
        print(f"        error[:100] = {err[:100]!r}")
        print(f"        plan_refusal = {pr}")
        if pr is True:
            print(f"        -> run_graph treats as REFUSAL (correct)")
        else:
            print(f"        -> run_graph treats as HARD FAILURE (BUG-3)")
    else:
        print(f"      RESULT: unexpected keys: {sorted(result.keys())}")


def main() -> None:
    print("=== BUG-3 verification — planner include handling ===\n")

    # ── 1. The S1 shape, called directly ──
    print("[1] generate_plan — the S1 shape (PO + ['Supplier'])")
    print("    Expectation: KeyError today; RefusalError after the fix")
    show_generate_plan(
        "generate_plan(Intent(PurchaseOrder, by_id 701337, include=['Supplier']))",
        Intent(
            target_entity="PurchaseOrder",
            filters=[{"type": "by_id", "value": "701337"}],
            include=["Supplier"],
        ),
    )

    # ── 2. Control: a valid PurchaseOrder include ──
    print("\n[2] generate_plan — valid PurchaseOrder + ['Buyer'] (control)")
    print("    Expectation: returns a Plan, no exception")
    show_generate_plan(
        "generate_plan(Intent(PurchaseOrder, by_id 701337, include=['Buyer']))",
        Intent(
            target_entity="PurchaseOrder",
            filters=[{"type": "by_id", "value": "701337"}],
            include=["Buyer"],
        ),
    )

    # ── 3. Bad include not first in the list ──
    print("\n[3] generate_plan — bad include at position 1, valid at position 0")
    print("    Expectation: KeyError naming the bad element ('Supplier')")
    show_generate_plan(
        "generate_plan(Intent(PurchaseOrder, by_id 701337, "
        "include=['POSchedule','Supplier']))",
        Intent(
            target_entity="PurchaseOrder",
            filters=[{"type": "by_id", "value": "701337"}],
            include=["POSchedule", "Supplier"],
        ),
    )

    # ── 4. plan_node wrapping of the S1 shape ──
    print("\n[4] plan_node — the S1 shape")
    print("    Expectation (BUG-3): {'error': ...} with plan_refusal MISSING or False")
    show_plan_node(
        "plan_node({'intent': Intent(PurchaseOrder, by_id 701337, "
        "include=['Supplier'])})",
        Intent(
            target_entity="PurchaseOrder",
            filters=[{"type": "by_id", "value": "701337"}],
            include=["Supplier"],
        ),
    )

    # ── 5. Contrast: a path that already routes correctly ──
    print("\n[5] plan_node — Invoice with no supplier (a known RefusalError path)")
    print("    Expectation: {'refusal': Refusal} — routes cleanly, no 'error' key")
    show_plan_node(
        "plan_node({'intent': Intent(Invoice, filters=[], include=[])})",
        Intent(target_entity="Invoice", filters=[], include=[]),
    )

    print("\n=== done ===")


if __name__ == "__main__":
    main()