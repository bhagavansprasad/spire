"""FastMCP server for Spire.

Loads the 'default_dev' persona at startup and exposes Fusion-backed
tools over HTTP. Run with:

    fastmcp run src/spire/mcp_server/server.py --transport http --port 3333

Or from Python directly (entry-point at bottom).
"""

from fastmcp import FastMCP

from spire.config import load_persona
from spire.fusion.client import FusionClient
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


if __name__ == "__main__":
    mcp.run(transport="http", host=DEFAULT_HOST, port=DEFAULT_PORT)
