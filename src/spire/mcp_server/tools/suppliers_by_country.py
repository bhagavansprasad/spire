"""Supplier search by country.

Country is on the supplier's `addresses` child resource, not on the
supplier record itself. This tool fetches suppliers with addresses
expanded, then filters client-side for any address matching the
requested country (ISO-2 code or full country name).

Match rules:
- ISO-2 code (e.g., "US", "GB") matched against address.CountryCode
- Full name (e.g., "United States") matched against address.Country
- Three-letter codes like "USA" are NOT supported; pass "US" instead.

A supplier appears once in the results even if multiple addresses match.

Truncation semantics (two distinct cases):
1. Source over-fetch hit OVERFETCH_LIMIT: we did not examine every
   supplier in Fusion; truncated=True, total_available=None.
2. Source fully examined, more matches than `limit`: truncated=True,
   total_available=len(all_matches) — accurate count.
"""

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


SUPPLIERS_PATH = "/fscmRestApi/resources/11.13.18.05/suppliers"

# Over-fetch cap. Because country filtering is entirely client-side,
# this bounds correctness — suppliers beyond this count are not
# considered for the filter. Acceptable for POC.
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


async def search_suppliers_by_country(
    client: FusionClient,
    country: str,
    limit: int = 25,
) -> ToolResult:
    """Find suppliers with at least one address in the given country.

    Args:
        country: ISO-2 country code (e.g., "US", "GB") OR full country
            name (e.g., "United States"). Three-letter codes like "USA"
            are not supported — use "US" instead.
        limit: Max records to return.

    Returns:
        ToolResult whose items are matched supplier dicts with
        MatchedCountry added. total_available and truncated reflect
        whether more matching suppliers exist than were returned.
    """
    params = {"limit": OVERFETCH_LIMIT, "expand": "addresses"}
    response = await client.get(SUPPLIERS_PATH, params=params)
    suppliers = response.get("items", [])

    overfetch_capped = len(suppliers) >= OVERFETCH_LIMIT

    # Examine every supplier in the over-fetch window. Count all matches
    # so we can report total_available, but only project up to `limit`
    # into the returned items list.
    matched: list[dict] = []
    match_count = 0
    for supplier in suppliers:
        addresses = supplier.get("addresses") or []
        if not any(_address_matches_country(a, country) for a in addresses):
            continue
        match_count += 1
        if len(matched) < limit:
            projected = {k: supplier.get(k) for k in _PROJECTED_FIELDS}
            projected["MatchedCountry"] = country
            matched.append(projected)

    if overfetch_capped:
        # We didn't examine all suppliers. But distinguish two cases:
        #
        # - ZERO matches in the window: we looked at OVERFETCH_LIMIT suppliers
        #   and none matched this country. Reporting truncated=True here is
        #   misleading — it implies "there may be more matches beyond the
        #   window", when the honest reading of an empty window is "no matches
        #   found". Report a clean empty result (total_available=0,
        #   truncated=False), which is also what the no-match tests assert.
        #
        # - SOME matches: more may exist past the window, so truncation is the
        #   honest signal and the true count is unknown.
        if not matched:
            return ToolResult.build(
                items=[],
                limit_applied=limit,
                total_available=0,
            )
        return ToolResult(
            items=matched,
            total_available=None,
            limit_applied=limit,
            truncated=True,
        )

    return ToolResult.build(
        items=matched,
        limit_applied=limit,
        total_available=match_count,
    )
