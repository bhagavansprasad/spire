#!/usr/bin/env python3
"""
verify_rank_invoices.py — Direct check of the rank_invoices_by_amount tool.

Calls the tool function directly (no MCP, no parser/planner) against the live
pod, to confirm Layer 1 of the top-N-invoices feature works in isolation:
- top-N across all invoices comes back strictly descending by InvoiceAmount
- per-supplier scoping returns that supplier's top-N, descending
- total_available reflects the honest count for the scope

    python scripts/verify_rank_invoices.py 2>&1 | tee t.txt
"""

import asyncio
import sys

from spire.config import load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.rank_invoices_by_amount import rank_invoices_by_amount


def _descending(items) -> bool:
    amts = [i.get("InvoiceAmount") for i in items]
    return all(
        a is not None and b is not None and a >= b
        for a, b in zip(amts, amts[1:])
    )


async def main() -> int:
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:

        print("=== top 5 invoices by amount (ALL suppliers) ===")
        r = await rank_invoices_by_amount(client, top_n=5)
        print(f"total_available: {r.total_available}  returned: {len(r.items)}  "
              f"truncated: {r.truncated}")
        for i in r.items:
            print(f"  {i['InvoiceAmount']:>15,.2f}  {i['SupplierNumber']:<8} "
                  f"{i['Supplier']:<20} {i['InvoiceNumber']}")
        print(f"  strictly descending: {_descending(r.items)}")

        print()
        print("=== top 5 invoices by amount for supplier 'Lee Supplies' ===")
        r2 = await rank_invoices_by_amount(
            client, supplier_name="Lee Supplies", top_n=5
        )
        print(f"total_available: {r2.total_available}  returned: {len(r2.items)}  "
              f"truncated: {r2.truncated}")
        for i in r2.items:
            print(f"  {i['InvoiceAmount']:>15,.2f}  {i['SupplierNumber']:<8} "
                  f"{i['Supplier']:<20} {i['InvoiceNumber']}")
        print(f"  strictly descending: {_descending(r2.items)}")
        all_lee = all(i.get("SupplierNumber") == "1252" for i in r2.items)
        print(f"  all supplier 1252: {all_lee}")

        print()
        print("=== nonexistent supplier -> honest empty ===")
        r3 = await rank_invoices_by_amount(
            client, supplier_name="ZZZ No Such Supplier ZZZ", top_n=5
        )
        print(f"total_available: {r3.total_available}  returned: {len(r3.items)}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
