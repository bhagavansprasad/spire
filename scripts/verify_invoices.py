#!/usr/bin/env python3
"""
verify_invoices.py — Compare what Spire's invoice tool returns against
ground truth from Fusion REST.

Each verification is a named function with a clear English-language purpose.
Pick one to run via --check, or run them all with --all.

Usage:
    # List available checks
    python scripts/verify_invoices.py --list

    # Count of invoices on/after a given date (REST totalResults)
    python scripts/verify_invoices.py count_after_date --date 2022-01-01

    # Compare tool return vs REST count for a date filter
    python scripts/verify_invoices.py tool_vs_rest_after_date --date 2022-01-01

    # What the MCP tool returns for a supplier name fragment
    python scripts/verify_invoices.py tool_for_supplier --supplier "Lee"

    # Inspect a single invoice's full record
    python scripts/verify_invoices.py inspect_one_invoice --invoice-id 300000244417567

    # Run every applicable check (uses sensible defaults where needed)
    python scripts/verify_invoices.py --all

Adding new checks:
    1. Write `def check_<name>(...)` that returns None and prints findings.
    2. Register it in CHECKS at the bottom of this file.
    3. Add any new CLI args to the argparse block.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Callable

from spire.config import load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.invoices import search_invoices


INVOICES_PATH = "/fscmRestApi/resources/11.13.18.05/invoices"


# ---------------------------------------------------------------------------
# Output helpers — keep verdicts visually consistent across checks.
# ---------------------------------------------------------------------------

def banner(title: str) -> None:
    bar = "=" * 72
    print(f"\n{bar}\n{title}\n{bar}")


def verdict(label: str, ok: bool, detail: str = "") -> None:
    mark = "OK  " if ok else "GAP "
    line = f"[{mark}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)


# ---------------------------------------------------------------------------
# Verification functions.
#
# Each takes a FusionClient and any args it needs, prints findings, returns
# None. Keep them small; one question per function.
# ---------------------------------------------------------------------------

async def count_after_date(client: FusionClient, date: str) -> None:
    """How many invoices does Fusion report on/after the given date?

    Uses totalResults=true with limit=1 — cheap and authoritative.
    """
    banner(f"REST totalResults for InvoiceDate >= '{date}'")

    params = {
        "q": f"InvoiceDate >= '{date}'",
        "limit": 1,
        "totalResults": "true",
        "onlyData": "true",
    }
    resp = await client.get(INVOICES_PATH, params=params)
    total = resp.get("totalResults")
    print(f"totalResults: {total}")
    if total is None:
        print("(no totalResults in response — pod may not support it on this endpoint)")


async def tool_vs_rest_after_date(client: FusionClient, date: str) -> None:
    """Compare MCP tool return count to REST ground-truth count.

    This is the headline gap check: agent says 'I found N'; we want
    to know what N actually is vs. what's really there.
    """
    banner(f"Tool vs REST for InvoiceDate >= '{date}'")

    # REST ground truth.
    rest_params = {
        "q": f"InvoiceDate >= '{date}'",
        "limit": 1,
        "totalResults": "true",
        "onlyData": "true",
    }
    rest_resp = await client.get(INVOICES_PATH, params=rest_params)
    rest_total = rest_resp.get("totalResults")

    # MCP tool return.
    tool_result = await search_invoices(client, invoice_date_after=date)
    tool_count = len(tool_result.items)
    
    print(f"REST totalResults: {rest_total}")
    print(f"Tool returned:     {tool_count}")

    if rest_total is None:
        verdict("count comparison", False,
                "REST did not report totalResults; can't compare")
        return

    if tool_count == rest_total:
        verdict("count comparison", True,
                "tool returned the full set")
    elif tool_count < rest_total:
        gap = rest_total - tool_count
        verdict("count comparison", False,
                f"tool returned {tool_count} of {rest_total} "
                f"(silently capped; {gap} missing)")
    else:
        verdict("count comparison", False,
                f"tool returned MORE than REST reports — investigate")


async def tool_for_supplier(client: FusionClient, supplier: str) -> None:
    """What does search_invoices return for a supplier name fragment?

    Shows raw tool output so you can sanity-check what the agent sees
    when it picks a supplier-name filter path.
    """
    banner(f"search_invoices(supplier_name='{supplier}')")

    result = await search_invoices(client, supplier_name=supplier)
    items = result.items
    print(f"Returned {len(items)} items.\n")

    for i, inv in enumerate(items[:10], 1):
        amt = inv.get("InvoiceAmount")
        amt_str = f"${amt:,.2f}" if isinstance(amt, (int, float)) else str(amt)
        print(f"  {i:>2}. {inv.get('Supplier', '?'):<30} "
              f"{inv.get('InvoiceNumber', '?'):<20} "
              f"{amt_str:>15}  "
              f"{inv.get('InvoiceDate', '?')}  "
              f"{inv.get('PaidStatus', '?')}")

    if len(items) > 10:
        print(f"  ... and {len(items) - 10} more")


async def inspect_one_invoice(client: FusionClient, invoice_id: str) -> None:
    """Fetch one invoice by ID and dump its full record.

    Useful when an agent answer references an invoice and you want to
    see every field the source actually has for it.
    """
    banner(f"GET /invoices/{invoice_id}")

    resp = await client.get(f"{INVOICES_PATH}/{invoice_id}")
    # Drop the noisy links array for readability.
    if isinstance(resp, dict):
        resp = {k: v for k, v in resp.items() if k != "links"}
    print(json.dumps(resp, indent=2, default=str))


# ---------------------------------------------------------------------------
# Registry and CLI.
# ---------------------------------------------------------------------------

# Map check name -> (function, required arg names from argparse).
# Required arg names must exist on the argparse Namespace.
CHECKS: dict[str, tuple[Callable, list[str]]] = {
    "count_after_date":       (count_after_date,       ["date"]),
    "tool_vs_rest_after_date": (tool_vs_rest_after_date, ["date"]),
    "tool_for_supplier":      (tool_for_supplier,      ["supplier"]),
    "inspect_one_invoice":    (inspect_one_invoice,    ["invoice_id"]),
}

# Defaults used when --all is passed (so each check has something to run with).
ALL_DEFAULTS = {
    "date": "2022-01-01",
    "supplier": "Lee",
    # inspect_one_invoice is skipped by --all because there's no safe
    # default ID across pods.
}

ALL_SKIP = {"inspect_one_invoice"}


async def run_check(client: FusionClient, name: str,
                    args: argparse.Namespace) -> None:
    func, required = CHECKS[name]
    kwargs = {}
    for arg_name in required:
        val = getattr(args, arg_name, None)
        if val is None:
            val = ALL_DEFAULTS.get(arg_name)
        if val is None:
            print(f"ERROR: check '{name}' requires --{arg_name.replace('_', '-')}",
                  file=sys.stderr)
            return
        kwargs[arg_name] = val
    await func(client, **kwargs)


async def main_async(args: argparse.Namespace) -> int:
    persona = load_persona("default_dev")

    targets: list[str]
    if args.all:
        targets = [n for n in CHECKS if n not in ALL_SKIP]
    elif args.check:
        if args.check not in CHECKS:
            print(f"ERROR: unknown check '{args.check}'", file=sys.stderr)
            print(f"Available: {', '.join(CHECKS)}", file=sys.stderr)
            return 1
        targets = [args.check]
    else:
        print("ERROR: pass a check name, --all, or --list", file=sys.stderr)
        return 1

    async with FusionClient(persona) as client:
        for name in targets:
            await run_check(client, name, args)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Spire invoice-tool output against Fusion REST.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "check",
        nargs="?",
        help="Name of the check to run. Use --list to see options.",
    )
    parser.add_argument("--list", action="store_true",
                        help="List available checks and exit.")
    parser.add_argument("--all", action="store_true",
                        help="Run all checks with sensible defaults.")
    parser.add_argument("--date", help="ISO date for date-based checks.")
    parser.add_argument("--supplier",
                        help="Supplier name fragment for supplier checks.")
    parser.add_argument("--invoice-id", dest="invoice_id",
                        help="Invoice ID for inspect_one_invoice.")
    args = parser.parse_args()

    if args.list:
        print("Available checks:\n")
        for name, (func, required) in CHECKS.items():
            doc = (func.__doc__ or "").strip().split("\n")[0]
            req = ", ".join(f"--{a.replace('_', '-')}" for a in required)
            print(f"  {name}")
            print(f"      {doc}")
            if req:
                print(f"      requires: {req}")
            print()
        return 0

    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())