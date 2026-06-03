"""FastMCP server for Spire.

Loads the 'default_dev' persona at startup and exposes Fusion-backed
tools over HTTP. Run with:

    python -m spire.mcp_server.server

Tools currently exposed:
- search_suppliers
- search_suppliers_by_country
- search_invoices
- search_purchase_orders
- get_buyer
"""

from fastmcp import Context, FastMCP

from spire.config import load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.aggregate_invoices import (
    aggregate_invoices_by_supplier as _aggregate_invoices_by_supplier,
)
from spire.mcp_server.tools.buyer import get_buyer as _get_buyer
from spire.mcp_server.tools.invoices import search_invoices as _search_invoices
from spire.mcp_server.tools.purchase_orders import (
    search_purchase_orders as _search_purchase_orders,
)
from spire.mcp_server.tools.suppliers import search_suppliers as _search_suppliers
from spire.mcp_server.tools.suppliers_by_country import (
    search_suppliers_by_country as _search_suppliers_by_country,
)


PERSONA_NAME = "default_dev"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3333

mcp = FastMCP("spire")
_persona = load_persona(PERSONA_NAME)


@mcp.tool()
async def search_suppliers(
    supplier_name_contains: str | None = None,
    status: str | None = None,
    limit: int = 25,
) -> dict:
    """Search Oracle Fusion suppliers by name fragment and/or status.

    Args:
        supplier_name_contains: Optional substring to match in supplier name.
        status: Exact Status match (e.g., "ACTIVE", "INACTIVE"). Applied
            client-side. Use for "active suppliers" / "inactive suppliers".
        limit: Max records to return (default 25).
    """
    async with FusionClient(_persona) as client:
        result = await _search_suppliers(
            client,
            supplier_name_contains=supplier_name_contains,
            status=status,
            limit=limit,
        )
        return result.to_dict()


@mcp.tool()
async def search_suppliers_by_country(
    country: str,
    limit: int = 25,
) -> dict:
    """Find suppliers with at least one address in the given country.

    Use this when the user asks about suppliers in a specific country
    (e.g., "US suppliers", "suppliers in the UK"). Country is not a
    field on the supplier record directly — it's matched against the
    addresses child resource.

    Args:
        country: ISO-2 code (e.g., "US", "GB") or full name (e.g.,
            "United States"). Three-letter codes like "USA" are not
            supported — use "US" instead.
        limit: Max records to return.
    """
    async with FusionClient(_persona) as client:
        result = await _search_suppliers_by_country(
            client,
            country=country,
            limit=limit,
        )
        return result.to_dict()

@mcp.tool()
async def search_invoices(
    supplier_number: str | None = None,
    supplier_name: str | None = None,
    invoice_date_after: str | None = None,
    invoice_date_before: str | None = None,
    limit: int = 25,
) -> dict:
    """Search Oracle Fusion invoices.

    Use this to find invoices for a specific supplier, optionally filtered
    by date. For the question "are there invoices for supplier X in the
    last N months?" pass the supplier's number plus an invoice_date_after
    of (today - N months) and check whether the result is empty.

    For a calendar month, combine the bounds: Jan 2022 is
    invoice_date_after="2022-01-01" and invoice_date_before="2022-02-01".

    Args:
        supplier_number: Exact SupplierNumber, e.g., "1252". Get this from
            search_suppliers first.
        supplier_name: Substring match on Supplier name. Use when the
            supplier_number is unknown.
        invoice_date_after: ISO date "YYYY-MM-DD". Returns invoices on
            or after this date (inclusive).
        invoice_date_before: ISO date "YYYY-MM-DD". Returns invoices
            strictly before this date (exclusive).
        limit: Max records to return.
    """
    async with FusionClient(_persona) as client:
        result = await _search_invoices(
            client,
            supplier_number=supplier_number,
            supplier_name=supplier_name,
            invoice_date_after=invoice_date_after,
            invoice_date_before=invoice_date_before,
            limit=limit,
        )
        return result.to_dict()

@mcp.tool()
async def search_purchase_orders(
    supplier_name: str | None = None,
    supplier_id: int | None = None,
    status: str | None = None,
    limit: int = 25,
) -> dict:
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
        result = await _search_purchase_orders(
            client,
            supplier_name=supplier_name,
            supplier_id=supplier_id,
            status=status,
            limit=limit,
        )
        return result.to_dict()


@mcp.tool()
async def aggregate_invoices_by_supplier(
    ctx: Context,
    date_from: str | None = None,
    date_to: str | None = None,
    top_n: int = 10,
) -> dict:
    """Rank suppliers by total invoice spend over a date range.

    Use this for ranking/total questions like "top 10 suppliers by
    spend" or "which suppliers did we spend the most with in Q1". The
    tool groups invoices by supplier, sums InvoiceAmount, and returns the
    top_n suppliers by total spend. Grouping (supplier) and measure (sum
    of spend) are fixed — this is a bounded aggregation, not a general
    engine.

    Args:
        date_from: ISO "YYYY-MM-DD". Inclusive lower bound on InvoiceDate.
        date_to: ISO "YYYY-MM-DD". Exclusive upper bound on InvoiceDate.
            For Q1 2026: date_from="2026-01-01", date_to="2026-04-01".
        top_n: Number of suppliers to return (default 10).

    Returns:
        A "supplier_spend_ranking" dict: ranked rows of
        {supplier, supplier_number, total_spend, invoice_count} plus
        total_suppliers, returned, truncated, and the echoed date range.
    """
    async with FusionClient(_persona) as client:
        return await _aggregate_invoices_by_supplier(
            client,
            date_from=date_from,
            date_to=date_to,
            top_n=top_n,
            report_progress=ctx.report_progress,
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

