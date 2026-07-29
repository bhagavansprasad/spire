"""Run the PO lifecycle tool directly against the pod. No MCP, no KG, no LLM.

This is the "standalone tool, pod-proven" step of the build sequence. The
tool is a plain async function taking a FusionClient, so nothing here
touches FastMCP, the planner, the parser or the synthesizer — a failure
is the tool's or the pod's, and cannot be anything else.

Usage:
    python test_tools/try_po_lifecycle.py 701337
    python test_tools/try_po_lifecycle.py 701337 162034
    python test_tools/try_po_lifecycle.py 701337 --raw

    --raw   print the unabridged result dict instead of the summary

Beyond printing, this asserts the tool's CONTRACT and exits non-zero when
it is violated — see _check_contract. That makes a flattened tri-state or
an invented risk rating fail here, at the tool boundary, rather than
surfacing as a wrong sentence three phases downstream.

No server restart is needed: this does not import the MCP server.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from spire.config import load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.po_lifecycle import (
    PAID_STATE_UNKNOWN,
    PAID_STATES,
    RISK_LEVELS,
    get_purchase_order_lifecycle_status,
)


PERSONA_NAME = "default_dev"

# Fields that must never be silently coerced. A None here is meaningful:
# it is the unknown paid state, and printing it as 0 or False would hide
# exactly what the contract exists to expose.
_TRISTATE_FIELDS = ("fully_paid", "remaining_to_pay")


def _fmt(value) -> str:
    """Render a value so None is visibly None, not an empty cell."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def _print_setup(result: dict) -> None:
    """Supplier and site setup — prompts A.2 and A.3."""
    setup = result.get("setup") or {}
    print("  -- setup --")
    if not setup.get("supplier_read"):
        print("  supplier         COULD NOT BE READ")
    else:
        print(f"  supplier         {_fmt(result.get('supplier'))}"
              f"  #{_fmt(setup.get('supplier_number'))}"
              f"  status={_fmt(setup.get('supplier_status'))}")
        print(f"  relationship     {_fmt(setup.get('business_relationship'))}"
              f"   spend_authorized={_fmt(setup.get('spend_authorized'))}"
              f"   ofac={_fmt(setup.get('on_ofac_list'))}")
        print(f"  withholding tax  {_fmt(setup.get('withholding_tax'))}"
              f"   {_fmt(setup.get('withholding_tax_group'))}")

    if not setup.get("site_read"):
        print("  site             COULD NOT BE READ")
    else:
        print(f"  site             {_fmt(result.get('supplier_site'))}"
              f"  status={_fmt(setup.get('site_status'))}"
              f"  purchasing={_fmt(setup.get('site_purchasing_enabled'))}"
              f"  pay={_fmt(setup.get('site_pay_enabled'))}")
        print(f"  matching         {_fmt(setup.get('match_approval_level'))}"
              f"   against {_fmt(setup.get('invoice_match_option'))}")
        print(f"  terms            PO={_fmt(result.get('payment_terms'))}"
              f"   site={_fmt(setup.get('site_payment_terms'))}"
              f"   overridden={_fmt(result.get('payment_terms_overridden'))}")
        print(f"  site holds       purchasing={_fmt(setup.get('purchasing_hold'))}"
              f"  all_invoices={_fmt(setup.get('invoice_hold_all'))}"
              f"  unvalidated={_fmt(setup.get('invoice_hold_unvalidated'))}"
              f"  payment_hold={_fmt(setup.get('payment_hold_date'))}")

    for blocker in result.get("setup_blockers", []):
        print(f"    ** BLOCKER: {blocker}")


def _print_summary(result: dict) -> None:
    """Print the fields that decide whether the answer is right.

    Deliberately not a pretty report — that is the display formatter's job
    later in the build sequence. This prints what a reviewer must check.
    """
    if not result.get("found"):
        print(f"  NOT FOUND: {result.get('order_number')}")
        for note in result.get("notes", []):
            print(f"    note: {note}")
        return

    print(f"  buyer / BU       {_fmt(result.get('buyer'))}"
          f"  / {_fmt(result.get('business_unit'))}")
    print(f"  status           {_fmt(result.get('status'))}"
          f"  funds={_fmt(result.get('funds_status'))}"
          f"  rev={_fmt(result.get('revision'))}")
    print(f"  communication    ack={_fmt(result.get('acknowledgment_required'))}"
          f"  method={_fmt(result.get('communication_method'))}"
          f"  pending={_fmt(result.get('pending_response_role'))}")
    print()

    _print_setup(result)
    print()

    print("  -- amounts --")
    print(f"  ordered          {_fmt(result.get('ordered'))} "
          f"{_fmt(result.get('currency'))}")
    print(f"  received         {_fmt(result.get('received'))}"
          f"   (derived={result.get('received_is_derived')})"
          f"   remaining {_fmt(result.get('remaining_to_receive'))}")
    print(f"  invoiced         {_fmt(result.get('invoiced'))}"
          f"   remaining {_fmt(result.get('remaining_to_invoice'))}")
    print(f"  matched in AP    {_fmt(result.get('matched_invoice_total'))}")
    print(f"  paid             {_fmt(result.get('paid'))}"
          f"   remaining {_fmt(result.get('remaining_to_pay'))}")
    print()

    print(f"  fully_received   {_fmt(result.get('fully_received'))}")
    print(f"  fully_invoiced   {_fmt(result.get('fully_invoiced'))}")
    print(f"  fully_paid       {_fmt(result.get('fully_paid'))}"
          f"   <- tri-state; branch on paid_state")
    print(f"  paid_state       {_fmt(result.get('paid_state'))}")
    print()

    print(f"  stage            {_fmt(result.get('lifecycle_stage'))}")
    print(f"  responsible      {_fmt(result.get('responsible_team'))}")
    print(f"  risk             {_fmt(result.get('risk'))}")
    for reason in result.get("risk_reasons", []):
        print(f"                     - {reason}")
    print(f"  action           {_fmt(result.get('recommended_action'))}")
    print()

    schedules = result.get("schedules", [])
    if schedules:
        print(f"  -- schedules ({len(schedules)}) --")
        print("   line sch status    amount   received  outstanding  full")
        for row in schedules:
            print(f"   {_fmt(row.get('line_number')):>4}"
                  f" {_fmt(row.get('schedule_number')):>3}"
                  f" {str(row.get('status') or '-'):<9}"
                  f" {row.get('amount', 0):>9,.2f}"
                  f" {row.get('received_amount', 0):>10,.2f}"
                  f" {row.get('outstanding_amount', 0):>12,.2f}"
                  f"  {row.get('fully_received')}")
        print()

    print(f"  schedules        {_fmt(result.get('schedule_count'))}"
          f" of {_fmt(result.get('schedule_total_available'))} available")
    print(f"  invoices         {_fmt(result.get('invoice_count'))}"
          f" of {_fmt(result.get('invoice_total_available'))} available"
          f"   cancelled={_fmt(result.get('canceled_invoice_count'))}")
    print(f"  holds            {_fmt(result.get('hold_count'))}"
          f"   installments_capped={result.get('installments_capped')}")
    print(f"  earliest due     {_fmt(result.get('earliest_due_date'))}"
          f"   days_overdue={_fmt(result.get('days_overdue'))}")
    print(f"  truncated        {result.get('truncated')}")

    for hold in result.get("holds", []):
        print(f"    HOLD {_fmt(hold.get('invoice_number'))}"
              f" type={_fmt(hold.get('hold_type'))}"
              f" reason={_fmt(hold.get('hold_reason'))}"
              f" by={_fmt(hold.get('held_by'))}"
              f" amount={_fmt(hold.get('amount_held'))}")

    notes = result.get("notes", [])
    print(f"\n  notes ({len(notes)}):")
    for note in notes:
        print(f"    - {note}")


def _check_contract(result: dict) -> list[str]:
    """Assert the invariants the rest of the pipeline will rely on.

    These are not style checks. Each one corresponds to a defect that has
    actually shipped in this codebase or was one edit away from doing so:

      tri-state flattening   `if fully_paid:` reads null as False, so the
                             unknown state silently becomes "not paid"
      unknown-state coercion 0.0 substituted for None re-asserts a debt
                             the tool has just said it cannot see
      free-text enums        a paid_state or risk outside the known set
                             means something downstream will not match
      unexplained risk       a rating with no reasons is an opinion
      defaulted setup        an unread supplier reported as ACTIVE turns
                             a failed fetch into a clean bill of health
    """
    warnings: list[str] = []
    if not result.get("found"):
        return warnings

    paid_state = result.get("paid_state")
    if paid_state not in PAID_STATES:
        warnings.append(f"paid_state {paid_state!r} is outside {PAID_STATES}")

    if paid_state == PAID_STATE_UNKNOWN:
        for field in _TRISTATE_FIELDS:
            if result.get(field) is not None:
                warnings.append(
                    f"paid_state is 'unknown' but {field} is "
                    f"{result.get(field)!r} — expected None"
                )
    elif result.get("fully_paid") is None:
        warnings.append(
            f"fully_paid is None but paid_state is {paid_state!r} — "
            "None is only valid for 'unknown'"
        )

    risk = result.get("risk")
    if risk not in RISK_LEVELS:
        warnings.append(f"risk {risk!r} is outside {RISK_LEVELS}")
    if not result.get("risk_reasons"):
        warnings.append("risk carries no reasons — a rating must be explicable")
    if not result.get("recommended_action"):
        warnings.append("recommended_action is empty")

    setup = result.get("setup") or {}
    if not setup.get("supplier_read") and setup.get("supplier_status"):
        warnings.append(
            "supplier was not read but supplier_status is populated"
        )
    if not setup.get("site_read") and setup.get("site_status"):
        warnings.append("site was not read but site_status is populated")

    return warnings


async def _run(po_numbers: list[str], raw: bool) -> int:
    persona = load_persona(PERSONA_NAME)
    exit_code = 0

    async with FusionClient(persona) as client:
        for po_number in po_numbers:
            print(f"\n{'=' * 68}")
            print(f"PO {po_number}")
            print("=" * 68)

            try:
                result = await get_purchase_order_lifecycle_status(
                    client, po_number
                )
            except Exception as exc:  # noqa: BLE001 - report, don't traceback
                print(f"  FAILED: {type(exc).__name__}: {exc}")
                exit_code = 1
                continue

            if raw:
                print(json.dumps(result, indent=2, default=str))
            else:
                _print_summary(result)

            for warning in _check_contract(result):
                print(f"\n  ** CONTRACT WARNING: {warning}")
                exit_code = 1

    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the PO lifecycle tool directly against the pod."
    )
    parser.add_argument(
        "po_numbers", nargs="+",
        help="One or more PO OrderNumbers, e.g. 701337 162034",
    )
    parser.add_argument(
        "--raw", action="store_true",
        help="Print the full result dict as JSON instead of the summary",
    )
    args = parser.parse_args()
    return asyncio.run(_run(args.po_numbers, args.raw))


if __name__ == "__main__":
    sys.exit(main())
