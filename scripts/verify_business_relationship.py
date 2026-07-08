#!/usr/bin/env python3
"""
verify_business_relationship.py — Verify the search_suppliers
business_relationship filter against Fusion REST ground truth.

Standalone: exercises the tool directly, no MCP / KG / parser. Run this
after editing search_suppliers and before wiring the KG or server.

Usage:
    python scripts/verify_business_relationship.py --list
    python scripts/verify_business_relationship.py distinct_values
    python scripts/verify_business_relationship.py rest_count --value "Spend Authorized"
    python scripts/verify_business_relationship.py tool_for_value --value "Spend Authorized"
    python scripts/verify_business_relationship.py tool_vs_unfiltered --value "Prospective"
    python scripts/verify_business_relationship.py --all
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from typing import Callable

from spire.config import load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.suppliers import search_suppliers


SUPPLIERS_PATH = "/fscmRestApi/resources/11.13.18.05/suppliers"


def banner(title: str) -> None:
    bar = "=" * 72
    print(f"\n{bar}\n{title}\n{bar}")


def verdict(label: str, ok: bool, detail: str = "") -> None:
    mark = "OK  " if ok else "GAP "
    line = f"[{mark}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)


async def distinct_values(client: FusionClient) -> None:
    """List the distinct BusinessRelationship values on the pod.

    Confirms the canonical strings the filter must match. Fetches a
    wide page and tallies.
    """
    banner("Distinct BusinessRelationship values (first 500 suppliers)")

    params = {
        "fields": "SupplierId,Supplier,BusinessRelationship",
        "limit": 500,
        "onlyData": "true",
    }
    resp = await client.get(SUPPLIERS_PATH, params=params)
    items = resp.get("items", [])
    counts = Counter(str(i.get("BusinessRelationship")) for i in items)
    for value, n in sorted(counts.items()):
        print(f"  {value!r}: {n}")


async def rest_count(client: FusionClient, value: str) -> None:
    """Does the pod honor a server-side q= on BusinessRelationship?

    If totalResults comes back sane, q= works here. If it errors or
    returns 0/empty for a value we know exists, that confirms the field
    must be matched client-side (which the tool does).
    """
    banner(f"REST totalResults for BusinessRelationship = '{value}'")

    params = {
        "q": f"BusinessRelationship='{value}'",
        "limit": 1,
        "totalResults": "true",
        "onlyData": "true",
    }
    try:
        resp = await client.get(SUPPLIERS_PATH, params=params)
        total = resp.get("totalResults")
        print(f"totalResults (server q=): {total}")
        if total in (None, 0):
            print("(server q= unreliable here — client-side match is correct)")
    except Exception as exc:  # noqa: BLE001
        print(f"server q= failed: {exc}")
        print("(confirms client-side match is correct)")


async def tool_for_value(client: FusionClient, value: str) -> None:
    """What does search_suppliers return for a business_relationship value?"""
    banner(f"search_suppliers(business_relationship='{value}')")

    result = await search_suppliers(
        client, business_relationship=value, limit=25
    )
    items = result.items
    print(f"Returned {len(items)} items "
          f"(total_available={result.total_available}, "
          f"truncated={result.truncated}).\n")

    for i, sup in enumerate(items[:10], 1):
        print(f"  {i:>2}. {sup.get('Supplier', '?'):<32} "
              f"{sup.get('SupplierNumber', '?'):<12} "
              f"{sup.get('BusinessRelationship', '?')}")
    if len(items) > 10:
        print(f"  ... and {len(items) - 10} more")

    # Every returned row must actually carry the requested value.
    mismatches = [
        s for s in items
        if s.get("BusinessRelationship") != value
    ]
    verdict("all returned rows match the value", not mismatches,
            "clean" if not mismatches else f"{len(mismatches)} mismatched")


async def tool_vs_unfiltered(client: FusionClient, value: str) -> None:
    """Tool count for a value should equal that value's share of an
    unfiltered fetch.

    Fetches unfiltered, tallies the value client-side, and compares to
    what the filtered tool call returns (both capped at the same limit).
    """
    banner(f"Tool vs unfiltered tally for '{value}'")

    # Unfiltered fetch, wide, count the value ourselves.
    params = {
        "fields": "SupplierId,BusinessRelationship",
        "limit": 500,
        "onlyData": "true",
    }
    resp = await client.get(SUPPLIERS_PATH, params=params)
    items = resp.get("items", [])
    ground = sum(
        1 for i in items if i.get("BusinessRelationship") == value
    )

    # Tool with a high limit so it isn't the limiting factor.
    result = await search_suppliers(
        client, business_relationship=value, limit=500
    )
    tool_count = len(result.items)

    print(f"Unfiltered tally for '{value}': {ground}")
    print(f"Tool returned:                 {tool_count}")

    if tool_count == ground:
        verdict("count comparison", True, "tool matches unfiltered tally")
    else:
        verdict("count comparison", False,
                f"tool {tool_count} vs tally {ground}")


CHECKS: dict[str, tuple[Callable, list[str]]] = {
    "distinct_values":    (distinct_values,    []),
    "rest_count":         (rest_count,         ["value"]),
    "tool_for_value":     (tool_for_value,     ["value"]),
    "tool_vs_unfiltered": (tool_vs_unfiltered, ["value"]),
}

ALL_DEFAULTS = {"value": "Spend Authorized"}


async def run_check(client: FusionClient, name: str,
                    args: argparse.Namespace) -> None:
    func, required = CHECKS[name]
    kwargs = {}
    for arg_name in required:
        val = getattr(args, arg_name, None)
        if val is None:
            val = ALL_DEFAULTS.get(arg_name)
        if val is None:
            print(f"ERROR: check '{name}' requires --{arg_name}",
                  file=sys.stderr)
            return
        kwargs[arg_name] = val
    await func(client, **kwargs)


async def main_async(args: argparse.Namespace) -> int:
    persona = load_persona("default_dev")

    if args.all:
        targets = list(CHECKS)
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
        description="Verify the business_relationship supplier filter.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("check", nargs="?",
                        help="Name of the check. Use --list to see options.")
    parser.add_argument("--list", action="store_true",
                        help="List available checks and exit.")
    parser.add_argument("--all", action="store_true",
                        help="Run all checks with defaults.")
    parser.add_argument("--value",
                        help="BusinessRelationship value to test.")
    args = parser.parse_args()

    if args.list:
        print("Available checks:\n")
        for name, (func, required) in CHECKS.items():
            doc = (func.__doc__ or "").strip().split("\n")[0]
            print(f"  {name}")
            print(f"      {doc}")
            if required:
                print(f"      requires: {', '.join('--' + a for a in required)}")
            print()
        return 0

    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
