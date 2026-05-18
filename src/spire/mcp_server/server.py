"""FastMCP server for Spire.

Loads the 'default_dev' persona at startup and exposes Fusion-backed
tools over HTTP. Run with:

    python -m spire.mcp_server.server

Tools currently exposed:
- search_suppliers
- search_invoices
"""

from fastmcp import FastMCP

from spire.config import load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.invoices import search_invoices as _search_invoices
from spire.mcp_server.tools.suppliers import search_suppliers as _search_suppliers


PERSONA_NAME = "default_dev"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3333

mcp = FastMCP("spire")
_persona = load_persona(PERSONA_NAME)


@mcp.tool()
async def search_suppliers(
    supplier_name_contains: str | None = None,
    limit: int = 25,
) -> list[dict]:
    """Search Oracle Fusion suppliers by name fragment.

    Args:
        supplier_name_contains: Optional substring to match in supplier name.
        limit: Max records to return (default 25).
    """
    async with FusionClient(_persona) as client:
        return await _search_suppliers(
            client,
            supplier_name_contains=supplier_name_contains,
            limit=limit,
        )


@mcp.tool()
async def search_invoices(
    supplier_number: str | None = None,
    supplier_name: str | None = None,
    invoice_date_after: str | None = None,
    limit: int = 25,
) -> list[dict]:
    """Search Oracle Fusion invoices.

    Use this to find invoices for a specific supplier, optionally filtered
    by date. For the question "are there invoices for supplier X in the
    last N months?" pass the supplier's number plus an invoice_date_after
    of (today - N months) and check whether the result is empty.

    Args:
        supplier_number: Exact SupplierNumber, e.g., "1252". Get this from
            search_suppliers first.
        supplier_name: Substring match on Supplier name. Use when the
            supplier_number is unknown.
        invoice_date_after: ISO date "YYYY-MM-DD". Returns invoices on
            or after this date.
        limit: Max records to return.
    """
    async with FusionClient(_persona) as client:
        return await _search_invoices(
            client,
            supplier_number=supplier_number,
            supplier_name=supplier_name,
            invoice_date_after=invoice_date_after,
            limit=limit,
        )


if __name__ == "__main__":
    mcp.run(transport="http", host=DEFAULT_HOST, port=DEFAULT_PORT)
