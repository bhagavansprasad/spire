"""Standalone driver for the agent.

Requires the MCP server to be running on http://127.0.0.1:3333/mcp/.

Usage:
    # Terminal 1:
    python -m spire.mcp_server.server

    # Terminal 2:
    python scripts/ask.py "Find suppliers with 'Lee' in the name"

    # KG-disabled (ablation) mode:
    python scripts/ask.py --no-kg "Find suppliers with 'Lee' in the name"
"""

import argparse
import asyncio
import sys

from spire.agent.runner import run_agent


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Spire agent on a prompt.")
    parser.add_argument(
        "--no-kg",
        action="store_true",
        help="Disable KG context in the system prompt (for Tier 2 ablation).",
    )
    parser.add_argument(
        "prompt",
        nargs=argparse.REMAINDER,
        help="The user prompt. Quote it or pass as remainder args.",
    )
    args = parser.parse_args()

    if not args.prompt:
        parser.print_usage(sys.stderr)
        print('Error: a prompt is required.', file=sys.stderr)
        return 1

    prompt_text = " ".join(args.prompt)
    answer = asyncio.run(run_agent(prompt_text, kg_enabled=not args.no_kg))
    print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
