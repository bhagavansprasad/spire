

"""FastMCP server for Spire.

Loads the 'default_dev' persona at startup and exposes Fusion-backed
tools over HTTP. Run with:

    python -m spire.mcp_server.server

Tools currently exposed:
- search_suppliers
- search_invoices
- search_addresses
- search_purchase_orders
- search_suppliers_by_site_bu
- search_suppliers_by_classification
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
from spire.mcp_server.tools.addresses import search_addresses as _search_addresses
from spire.mcp_server.tools.supplier_sites import (
    search_suppliers_by_site_bu as _search_suppliers_by_site_bu,
)
from spire.mcp_server.tools.supplier_classifications import (
    search_suppliers_by_classification as _search_suppliers_by_classification,
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
    business_relationship: str | None = None,
    country: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    include_addresses: bool = False,
    limit: int = 25,
) -> dict:
    """Search Oracle Fusion suppliers by any combination of filters.

    Use for supplier questions with any mix of: a name fragment, a
    status, a country, and a creation-date range. Filters stack
    (e.g. "active US suppliers named Lee").

    Args:
        supplier_name_contains: Optional substring to match in supplier name.
        status: Exact Status match (e.g., "ACTIVE", "INACTIVE"). Applied
            client-side. Use for "active suppliers" / "inactive suppliers".
        business_relationship: Exact BusinessRelationship match (e.g.,
            "Spend Authorized", "Prospective"). Applied client-side. Use
            for "spend authorized suppliers" / "prospective suppliers".
        country: ISO-2 code (e.g., "US", "GB") or full name (e.g.,
            "United States"). Matched against the addresses child
            resource. Three-letter codes like "USA" are not supported.
        created_from: Lower bound on CreationDate ("YYYY-MM-DD").
        created_to: Upper bound on CreationDate ("YYYY-MM-DD").
        include_addresses: When True, nest each supplier's addresses under
            an 'addresses' key (via expand=addresses). Use for "suppliers
            with their addresses".
        limit: Max records to return (default 25).
    """
    async with FusionClient(_persona) as client:
        result = await _search_suppliers(
            client,
            supplier_name_contains=supplier_name_contains,
            status=status,
            business_relationship=business_relationship,
            country=country,
            created_from=created_from,
            created_to=created_to,
            include_addresses=include_addresses,
            limit=limit,
        )
        return result.to_dict()


@mcp.tool()
async def search_invoices(
    supplier_number: str | None = None,
    supplier_name: str | None = None,
    invoice_date_after: str | None = None,
    invoice_date_before: str | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    limit: int = 25,
) -> dict:
    """Search Oracle Fusion invoices.

    Use this to find invoices for a specific supplier, optionally filtered
    by date and/or amount. For the question "are there invoices for
    supplier X in the last N months?" pass the supplier's number plus an
    invoice_date_after of (today - N months) and check whether the result
    is empty.

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
        amount_min: Lower bound on InvoiceAmount (inclusive).
        amount_max: Upper bound on InvoiceAmount (inclusive).
        limit: Max records to return.
    """
    async with FusionClient(_persona) as client:
        result = await _search_invoices(
            client,
            supplier_number=supplier_number,
            supplier_name=supplier_name,
            invoice_date_after=invoice_date_after,
            invoice_date_before=invoice_date_before,
            amount_min=amount_min,
            amount_max=amount_max,
            limit=limit,
        )
        return result.to_dict()


@mcp.tool()
async def search_addresses(
    supplier_number: str | None = None,
    supplier_name: str | None = None,
    country: str | None = None,
    limit: int = 25,
) -> dict:
    """Fetch supplier addresses as flat records.

    Use for address questions. Requires at least one of supplier_number,
    supplier_name, or country — addresses are a child of the supplier
    record, so an unfiltered fetch would pull every address on the pod.

    Args:
        supplier_number: Exact SupplierNumber, e.g. "1252".
        supplier_name: Substring match on Supplier name.
        country: ISO-2 code (e.g. "US") or full name (e.g. "United
            States"), matched against each address.
        limit: Max address records to return.
    """
    async with FusionClient(_persona) as client:
        result = await _search_addresses(
            client,
            supplier_number=supplier_number,
            supplier_name=supplier_name,
            country=country,
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
async def search_suppliers_by_site_bu(
    supplier_id: int,
    business_unit: str,
    limit: int = 25,
) -> dict:
    """Check whether one supplier has a site in a given business unit.

    Edge tool: called once per supplier to filter suppliers by their
    sites' ProcurementBU. For "suppliers with a site in business unit X",
    the executor calls this per supplier and keeps those whose result is
    non-empty. ProcurementBU filters server-side on the sites child.

    Args:
        supplier_id: The SupplierId of the supplier to check. Get this
            from search_suppliers.
        business_unit: Exact ProcurementBU display string, e.g.
            "US1 Business Unit".
        limit: Max site records to return.

    Returns:
        A ToolResult dict whose items are the supplier's matching sites.
        Empty items means the supplier has no site in that BU.
    """
    async with FusionClient(_persona) as client:
        result = await _search_suppliers_by_site_bu(
            client,
            supplier_id=supplier_id,
            business_unit=business_unit,
            limit=limit,
        )
        return result.to_dict()


@mcp.tool()
async def search_suppliers_by_classification(
    supplier_id: int,
    classification: str,
    limit: int = 25,
) -> dict:
    """Check whether one supplier has a given business classification.

    Edge tool: called once per supplier to filter suppliers by their
    business classifications. For "suppliers that are small business /
    woman owned / minority owned", the executor calls this per supplier
    and keeps those whose result is non-empty. Classification filters
    server-side on the businessClassifications child.

    Args:
        supplier_id: The SupplierId of the supplier to check. Get this
            from search_suppliers.
        classification: Exact Classification display string, e.g.
            "Small Business".
        limit: Max classification records to return.

    Returns:
        A ToolResult dict whose items are the supplier's matching
        classifications. Empty items means no match.
    """
    async with FusionClient(_persona) as client:
        result = await _search_suppliers_by_classification(
            client,
            supplier_id=supplier_id,
            classification=classification,
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





