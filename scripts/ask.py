"""Standalone driver for the agent.

Requires the MCP server to be running on http://127.0.0.1:3333/mcp/.

Usage:
    # Terminal 1:
    python -m spire.mcp_server.server

    # Terminal 2:
    python scripts/ask.py "Find suppliers with 'Lee' in the name"
"""

import asyncio
import sys

from spire.agent.runner import run_agent


def main() -> int:
    if len(sys.argv) < 2:
        print('Usage: python scripts/ask.py "<prompt>"', file=sys.stderr)
        return 1
    prompt = " ".join(sys.argv[1:])
    answer = asyncio.run(run_agent(prompt))
    print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
