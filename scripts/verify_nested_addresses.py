#!/usr/bin/env python3
"""
verify_nested_addresses.py — Verify search_suppliers(include_addresses=True)
nests each supplier's addresses under an 'addresses' key.

Standalone: exercises the tool directly, no MCP / KG / parser. Run after
editing search_suppliers and before wiring planner/parser/synthesizer.

Usage:
    python scripts/verify_nested_addresses.py --list
    python scripts/verify_nested_addresses.py tool_nests_addresses
    python scripts/verify_nested_addresses.py tool_vs_bulk --supplier 1252
    python scripts/verify_nested_addresses.py --all
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Callable

from spire.config import load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.suppliers import search_suppliers


SUPPLIERS_PATH = "/fscmRestApi/resources/11.13.18.05/suppliers"

_ADDRESS_KEYS = {
    "SupplierAddressId", "AddressName", "Country", "CountryCode",
    "City", "State", "FormattedAddress",
}


def banner(title: str) -> None:
    bar = "=" * 72
    print(f"\n{bar}\n{title}\n{bar}")


def verdict(label: str, ok: bool, detail: str = "") -> None:
    mark = "OK  " if ok else "GAP "
    line = f"[{mark}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)


async def tool_nests_addresses(client: FusionClient) -> None:
    """search_suppliers(include_addresses=True) returns rows each with a
    nested 'addresses' list of flattened address dicts."""
    banner("search_suppliers(include_addresses=True) — nested shape")

    result = await search_suppliers(client, include_addresses=True, limit=10)
    items = result.items
    print(f"Returned {len(items)} supplier row(s).\n")

    with_addr = 0
    shape_ok = True
    for sup in items:
        addrs = sup.get("addresses")
        has_key = "addresses" in sup
        n = len(addrs) if isinstance(addrs, list) else 0
        if n:
            with_addr += 1
            # Check the first address has only the expected keys.
            extra = set(addrs[0]) - _ADDRESS_KEYS
            if extra:
                shape_ok = False
        print(f"  {sup.get('Supplier', '?'):<32} "
              f"addresses key={has_key}  count={n}")

    verdict("every row carries an 'addresses' key",
            all("addresses" in s for s in items),
            "present on all rows")
    verdict("at least one supplier has nested addresses",
            with_addr > 0, f"{with_addr}/{len(items)} rows had >=1 address")
    verdict("nested address fields match the expected shape",
            shape_ok, "flattened to the AddressRecord fields")


async def tool_vs_bulk(client: FusionClient, supplier: str) -> None:
    """The tool's nested address count for one supplier matches the same
    supplier's addresses in a bulk expand fetch.

    NOTE: a single-supplier q= expand can return FEWER addresses than the
    bulk expand on this pod (observed 25 vs 30 for 1252, all ACTIVE) — the
    two query shapes are not equivalent, so we compare bulk-to-bulk. The
    tool uses the bulk path, so this is the correct baseline.
    """
    banner(f"Tool nested-address count vs bulk expand for supplier {supplier}")

    # Ground truth: the SAME bulk fetch shape the tool uses.
    params = {
        "expand": "addresses",
        "onlyData": "true",
        "limit": 500,
    }
    resp = await client.get(SUPPLIERS_PATH, params=params)
    match_raw = next(
        (i for i in resp.get("items", [])
         if i.get("SupplierNumber") == supplier), None
    )
    ground = len(match_raw.get("addresses") or []) if match_raw else -1

    # Tool.
    result = await search_suppliers(
        client, include_addresses=True, limit=500
    )
    match = next(
        (s for s in result.items if s.get("SupplierNumber") == supplier), None
    )
    tool_count = len(match.get("addresses") or []) if match else -1

    print(f"Bulk expand addresses for {supplier}: {ground}")
    print(f"Tool nested addresses for {supplier}: {tool_count}")

    if match is None or match_raw is None:
        verdict("supplier present in both", False,
                f"{supplier} not found in first 500 rows")
        return
    verdict("nested count matches bulk expand", tool_count == ground,
            f"tool {tool_count} vs bulk {ground}")


CHECKS: dict[str, tuple[Callable, list[str]]] = {
    "tool_nests_addresses": (tool_nests_addresses, []),
    "tool_vs_bulk":         (tool_vs_bulk,         ["supplier"]),
}

ALL_DEFAULTS = {"supplier": "1252"}
ALL_SKIP: set[str] = set()


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
        description="Verify the include_addresses nested-address behavior.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("check", nargs="?",
                        help="Name of the check. Use --list to see options.")
    parser.add_argument("--list", action="store_true",
                        help="List available checks and exit.")
    parser.add_argument("--all", action="store_true",
                        help="Run all checks with defaults.")
    parser.add_argument("--supplier",
                        help="Supplier number for the curl comparison.")
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
