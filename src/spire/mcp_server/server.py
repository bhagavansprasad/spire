"""FastMCP server for Spire.

Loads the 'default_dev' persona at startup and exposes Fusion-backed
tools over HTTP. Run with:

    python -m spire.mcp_server.server

Tools currently exposed:
- search_suppliers
- search_invoices
- search_purchase_orders
- get_buyer
"""

from fastmcp import FastMCP

from spire.config import load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.buyer import get_buyer as _get_buyer
from spire.mcp_server.tools.invoices import search_invoices as _search_invoices
from spire.mcp_server.tools.purchase_orders import (
    search_purchase_orders as _search_purchase_orders,
)
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


@mcp.tool()
async def search_purchase_orders(
    supplier_name: str | None = None,
    supplier_id: int | None = None,
    status: str | None = None,
    limit: int = 25,
) -> list[dict]:
    """Search Oracle Fusion purchase orders.

    Use this to find POs for a specific supplier, optionally filtered by
    status. For "find open POs for supplier X" pass supplier_name or
    supplier_id along with status="OPEN".

    Args:
        supplier_name: Substring match on Supplier name (LIKE). Use when
            you have the supplier name as a string.
        supplier_id: Exact SupplierId match (numeric). Get this from
            search_suppliers if available.
        status: Exact StatusCode match. Common values: "OPEN", "CLOSED",
            "INCOMPLETE", "CANCELED".
        limit: Max records to return.
    """
    async with FusionClient(_persona) as client:
        return await _search_purchase_orders(
            client,
            supplier_name=supplier_name,
            supplier_id=supplier_id,
            status=status,
            limit=limit,
        )


@mcp.tool()
async def get_buyer(buyer_id: int) -> dict | None:
    """Look up a buyer (purchasing agent) by ID.

    Buyer IDs come from purchase orders (the BuyerId field returned by
    search_purchase_orders). This tool returns the buyer's name, email,
    and username from the HCM workers system.

    Args:
        buyer_id: The numeric BuyerId from a purchase order.

    Returns:
        A dict with PersonId, DisplayName, FirstName, LastName, WorkEmail,
        Username, and PersonNumber. Returns null if no buyer matches.
    """
    async with FusionClient(_persona) as client:
        return await _get_buyer(client, buyer_id=buyer_id)


if __name__ == "__main__":
    mcp.run(transport="http", host=DEFAULT_HOST, port=DEFAULT_PORT)
