"""Supplier search tool.

Plain async function — not coupled to FastMCP. Registration happens
in spire.mcp_server.server. This lets us test the tool directly.

This is the single per-entity supplier fetcher. All supplier-level
filters live here and combine freely (e.g. "active US suppliers named
Lee"). It supersedes the old search_suppliers_by_country tool.

Filters supported:
- supplier_name_contains: LIKE match on Supplier (server-side q=)
- created_from: CreationDate >= 'YYYY-MM-DD' (server-side q=)
- created_to:   CreationDate <  'YYYY-MM-DD' (client-side upper bound)
- status: exact match on Status, e.g. ACTIVE/INACTIVE (client-side;
  Fusion REST rejects q=Status='...' on this endpoint)
- business_relationship: exact match on BusinessRelationship, e.g.
  "Spend Authorized" / "Prospective" (client-side)
- country: ISO-2 code or full name, matched against the addresses
  child resource (client-side; requires expand=addresses)
- limit: max records returned after client-side filtering (default 25)

Only one server-side q= clause is reliable on this pod (composite q=
fails), so the tool sends at most one clause via q= and applies every
other filter client-side. Precedence for the single server clause:
name fragment, else created_from. Everything else is client-side.

Returns a ToolResult so callers can distinguish "this is everything"
from "this is a capped subset."
"""

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


SUPPLIERS_PATH = "/fscmRestApi/resources/11.13.18.05/suppliers"

# Over-fetch cap for when any client-side filtering happens, so the
# filter has enough records to work with.
OVERFETCH_LIMIT = 500

_PROJECTED_FIELDS = [
    "SupplierId",
    "SupplierNumber",
    "Supplier",
    "Status",
    "BusinessRelationship",
    "TaxpayerCountryCode",
]


def _address_matches_country(address: dict, country: str) -> bool:
    code = (address.get("CountryCode") or "").upper()
    name = (address.get("Country") or "").lower()
    q = country.strip()
    return code == q.upper() or name == q.lower()


async def _fetch_total_for_clause(
    client: FusionClient, server_clause: str | None
) -> int | None:
    """Cheaply ask Fusion how many records match the server clause."""
    params: dict[str, str | int] = {
        "limit": 1,
        "totalResults": "true",
        "onlyData": "true",
    }
    if server_clause:
        params["q"] = server_clause
    response = await client.get(SUPPLIERS_PATH, params=params)
    total = response.get("totalResults")
    return total if isinstance(total, int) else None


async def search_suppliers(
    client: FusionClient,
    supplier_name_contains: str | None = None,
    status: str | None = None,
    business_relationship: str | None = None,
    country: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    limit: int = 25,
) -> ToolResult:
    """Search Oracle Fusion suppliers by any combination of filters.

    Args:
        supplier_name_contains: Substring match on Supplier name (LIKE),
            sent server-side via q=.
        status: Exact match on Status (e.g., "ACTIVE", "INACTIVE"),
            applied client-side.
        business_relationship: Exact match on BusinessRelationship
            (e.g., "Spend Authorized", "Prospective"), applied
            client-side.
        country: ISO-2 code (e.g., "US") or full name (e.g., "United
            States"), matched against the addresses child resource.
            Requires expand=addresses; applied client-side.
        created_from: Lower bound on CreationDate ('YYYY-MM-DD'), sent
            server-side via q= when no name fragment is present.
        created_to: Upper bound on CreationDate ('YYYY-MM-DD'), applied
            client-side (composite q= is unreliable on this pod).
        limit: Max records to return AFTER client-side filtering.

    Returns:
        ToolResult with items (projected supplier dicts up to `limit`),
        total_available, limit_applied, and truncated.
    """
    # At most one server-side q= clause is reliable. Prefer the name
    # fragment; otherwise use created_from. Any remaining filters run
    # client-side.
    server_clause: str | None = None
    created_from_client = created_from
    if supplier_name_contains:
        server_clause = f"Supplier LIKE '%{supplier_name_contains}%'"
    elif created_from:
        server_clause = f"CreationDate >= '{created_from}'"
        created_from_client = None  # handled server-side

    # Country needs the addresses child resource.
    needs_expand = country is not None

    # We must filter client-side if any non-server filter is in play.
    needs_client_filter = (
        status is not None
        or business_relationship is not None
        or country is not None
        or created_to is not None
        or created_from_client is not None
    )

    fetch_limit = OVERFETCH_LIMIT if needs_client_filter else limit

    params: dict[str, str | int] = {"limit": fetch_limit}
    if server_clause:
        params["q"] = server_clause
    if needs_expand:
        params["expand"] = "addresses"

    response = await client.get(SUPPLIERS_PATH, params=params)
    items = response.get("items", [])

    def matches(item: dict) -> bool:
        if status is not None and item.get("Status") != status:
            return False
        if (
            business_relationship is not None
            and item.get("BusinessRelationship") != business_relationship
        ):
            return False
        if created_from_client is not None:
            cd = item.get("CreationDate") or ""
            if cd < created_from_client:
                return False
        if created_to is not None:
            cd = item.get("CreationDate") or ""
            if cd >= created_to:
                return False
        if country is not None:
            addresses = item.get("addresses") or []
            if not any(_address_matches_country(a, country) for a in addresses):
                return False
        return True

    filtered = [item for item in items if matches(item)]
    final_items = filtered[:limit]

    projected = []
    for item in final_items:
        row = {k: item.get(k) for k in _PROJECTED_FIELDS}
        if country is not None:
            row["MatchedCountry"] = country
        projected.append(row)

    # ---- total_available / truncated ----
    # 1. Client-side filtering hit the over-fetch cap: not every supplier
    #    was examined; truncation occurred but the true count is unknown.
    # 2. No client-side filtering and result is full at limit: a cheap
    #    totalResults call gives the authoritative count.
    # 3. Otherwise: we have every matching record.

    if needs_client_filter and len(items) >= OVERFETCH_LIMIT:
        return ToolResult(
            items=projected,
            total_available=None,
            limit_applied=limit,
            truncated=True,
        )

    if not needs_client_filter and len(final_items) >= limit:
        total = await _fetch_total_for_clause(client, server_clause)
        return ToolResult.build(
            items=projected,
            limit_applied=limit,
            total_available=total,
        )

    return ToolResult.build(
        items=projected,
        limit_applied=limit,
        total_available=len(filtered),
    )

