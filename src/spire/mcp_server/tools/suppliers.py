"""Supplier search tool.

Plain async function — not coupled to FastMCP. Registration happens
in spire.mcp_server.server. This lets us test the tool directly.

Filters supported:
- supplier_name_contains: LIKE match on Supplier field
- limit: max records returned (default 25, Fusion's default)

Country-code filtering requires the 'addresses' child resource and is
deferred to Phase 4's search_suppliers_by_country tool.
"""

from spire.fusion.client import FusionClient


SUPPLIERS_PATH = "/fscmRestApi/resources/11.13.18.05/suppliers"


async def search_suppliers(
    client: FusionClient,
    supplier_name_contains: str | None = None,
    limit: int = 25,
) -> list[dict]:
    """Search Oracle Fusion suppliers. Returns the items list."""
    params: dict[str, str | int] = {"limit": limit}
    if supplier_name_contains:
        params["q"] = f"Supplier LIKE '%{supplier_name_contains}%'"

    response = await client.get(SUPPLIERS_PATH, params=params)
    return response.get("items", [])
