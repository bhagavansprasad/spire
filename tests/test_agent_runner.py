"""Integration test for spire.agent.runner.

Requires:
- The MCP server running on http://127.0.0.1:3333/mcp/
- personas.yaml present
- GEMINI_API_KEY environment variable set

Marked @pytest.mark.integration so it's skipped by default. Run with:
    pytest -m integration tests/test_agent_runner.py
"""

import os

import pytest

from spire.config import PERSONAS_FILE

# The LangGraph agent runner (spire.agent.runner) is legacy: it is imported
# by nothing in src/ except this integration test, and its dependency
# langchain-mcp-adapters requires mcp<2, which conflicts with the app's
# current mcp 2.x + fastmcp 4.x stack (no langchain-mcp-adapters release
# supports mcp>=2). Skip collection rather than fail the whole suite.
run_agent = pytest.importorskip(
    "spire.agent.runner",
    reason="langchain-mcp-adapters requires mcp<2; app is on mcp 2.x + fastmcp 4.x",
).run_agent


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not PERSONAS_FILE.exists() or not os.environ.get("GEMINI_API_KEY"),
        reason="personas.yaml or GEMINI_API_KEY missing",
    ),
]


@pytest.mark.asyncio
async def test_run_agent_finds_lee():
    answer = await run_agent("Find suppliers with 'Lee' in the name. Just list the names.")
    assert isinstance(answer, str)
    assert len(answer) > 0
    assert "Lee" in answer
