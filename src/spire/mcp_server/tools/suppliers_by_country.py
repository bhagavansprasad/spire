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
"""

from spire.fusion.client import FusionClient


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
) -> list[dict]:
    """Find suppliers with at least one address in the given country.

    Args:
        country: ISO-2 country code (e.g., "US", "GB") OR full country
            name (e.g., "United States"). Three-letter codes like "USA"
            are not supported — use "US" instead.
        limit: Max records to return.

    Returns:
        List of supplier dicts with the matched country code added as
        MatchedCountry.
    """
    params = {"limit": OVERFETCH_LIMIT, "expand": "addresses"}
    response = await client.get(SUPPLIERS_PATH, params=params)
    suppliers = response.get("items", [])

    matched: list[dict] = []
    for supplier in suppliers:
        addresses = supplier.get("addresses") or []
        if not any(_address_matches_country(a, country) for a in addresses):
            continue
        projected = {k: supplier.get(k) for k in _PROJECTED_FIELDS}
        projected["MatchedCountry"] = country
        matched.append(projected)
        if len(matched) >= limit:
            break

    return matched
