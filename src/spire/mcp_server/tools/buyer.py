"""Buyer lookup tool.

In Oracle Fusion, buyers are stored as HCM workers, not as a separate
FSCM entity. The `/fscmRestApi/.../buyers` endpoint does not exist on
this pod. Buyer IDs from purchase orders (`BuyerId`) map directly to
`PersonId` on HCM's publicWorkers endpoint.

Returns a single dict (not a list) since buyer IDs are unique. Returns
None when no worker matches the given ID.
"""

from spire.fusion.client import FusionClient


PUBLIC_WORKERS_PATH = "/hcmRestApi/resources/11.13.18.05/publicWorkers"

_PROJECTED_FIELDS = [
    "PersonId",
    "PersonNumber",
    "DisplayName",
    "FirstName",
    "LastName",
    "WorkEmail",
    "Username",
]


async def get_buyer(client: FusionClient, buyer_id: int) -> dict | None:
    """Look up a buyer by ID.

    Buyer IDs come from purchase orders (the BuyerId field). They map
    to PersonId on HCM's publicWorkers endpoint.

    Args:
        buyer_id: The numeric buyer/person ID, e.g., 300000047340498.

    Returns:
        Dict with buyer details (name, email, username), or None if no
        worker with that ID exists.
    """
    params = {"q": f"PersonId={buyer_id}", "limit": 1}
    response = await client.get(PUBLIC_WORKERS_PATH, params=params)
    items = response.get("items", [])
    if not items:
        return None
    return {k: items[0].get(k) for k in _PROJECTED_FIELDS}
