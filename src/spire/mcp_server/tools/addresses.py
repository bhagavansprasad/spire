"""Supplier-address search tool.

Addresses are a child of the supplier record; there is no standalone
Address endpoint. This tool fetches suppliers with expand=addresses,
then flattens each supplier's addresses into flat address records,
tagging each with its parent SupplierNumber and Supplier name.

A filter is required — either a supplier (number or name) or a country —
so the fetch stays bounded rather than pulling every address on the pod.

Filters:
- supplier_number / supplier_name: narrow to one supplier's addresses.
- country: ISO-2 code or full name, matched against CountryCode/Country
  (case-insensitive), same rule as search_suppliers.
"""

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


SUPPLIERS_PATH = "/fscmRestApi/resources/11.13.18.05/suppliers"

# Over-fetch cap for the supplier scan when filtering by country.
OVERFETCH_LIMIT = 500

# Fields copied from each address child into the flat record, plus the
# parent identity (SupplierNumber, Supplier) added during flattening.
_ADDRESS_FIELDS = [
    "SupplierAddressId",
    "AddressName",
    "Country",
    "CountryCode",
    "AddressLine1",
    "City",
    "State",
    "PostalCode",
    "FormattedAddress",
]


def _address_matches_country(address: dict, country: str) -> bool:
    code = (address.get("CountryCode") or "").upper()
    name = (address.get("Country") or "").lower()
    q = country.strip()
    return code == q.upper() or name == q.lower()


async def search_addresses(
    client: FusionClient,
    supplier_number: str | None = None,
    supplier_name: str | None = None,
    country: str | None = None,
    limit: int = 25,
) -> ToolResult:
    """Fetch supplier addresses as flat records.

    Requires at least one of supplier_number, supplier_name, or country.

    Args:
        supplier_number: Exact SupplierNumber, e.g. "1252".
        supplier_name: Substring match on Supplier name.
        country: ISO-2 code (e.g. "US") or full name (e.g. "United
            States"), matched against each address client-side.
        limit: Max address records to return.

    Returns:
        ToolResult whose items are flat address dicts, each tagged with
        SupplierNumber and Supplier.
    """
    if not (supplier_number or supplier_name or country):
        raise ValueError(
            "search_addresses requires a filter: a supplier "
            "(number or name) or a country."
        )

    # Narrow server-side when we can: a supplier reference is the most
    # selective single q= clause. Country is matched client-side (it
    # lives on the address child).
    server_clause: str | None = None
    if supplier_number:
        server_clause = f"SupplierNumber='{supplier_number}'"
    elif supplier_name:
        server_clause = f"Supplier LIKE '%{supplier_name}%'"

    fetch_limit = limit if server_clause else OVERFETCH_LIMIT
    params: dict[str, str | int] = {"limit": fetch_limit, "expand": "addresses"}
    if server_clause:
        params["q"] = server_clause

    response = await client.get(SUPPLIERS_PATH, params=params)
    suppliers = response.get("items", [])
    overfetch_capped = not server_clause and len(suppliers) >= OVERFETCH_LIMIT

    records: list[dict] = []
    match_count = 0
    for supplier in suppliers:
        addresses = supplier.get("addresses") or []
        for addr in addresses:
            if country is not None and not _address_matches_country(addr, country):
                continue
            match_count += 1
            if len(records) < limit:
                row = {k: addr.get(k) for k in _ADDRESS_FIELDS}
                row["SupplierNumber"] = supplier.get("SupplierNumber")
                row["Supplier"] = supplier.get("Supplier")
                records.append(row)

    if overfetch_capped:
        return ToolResult(
            items=records,
            total_available=None,
            limit_applied=limit,
            truncated=True,
        )

    return ToolResult.build(
        items=records,
        limit_applied=limit,
        total_available=match_count,
    )
