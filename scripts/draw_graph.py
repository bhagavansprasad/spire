"""One-shot agent graph visualization.

Requires the MCP server to be running. Produces docs/agent_graph.png.

Usage:
    python scripts/draw_graph.py
"""

import asyncio
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from spire.agent.lg_utility import save_graph_as_png
from spire.agent.runner import MCP_SERVER_URL, _build_graph
from spire.agent.tracing import make_trace_logger


OUTPUT_PATH = Path("docs") / "agent_graph.png"


async def main():
    logger, _ = make_trace_logger()
    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            graph = await _build_graph(session, logger)
            OUTPUT_PATH.parent.mkdir(exist_ok=True)
            save_graph_as_png(graph, OUTPUT_PATH)
            print(f"Graph saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
