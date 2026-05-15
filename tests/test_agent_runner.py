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

from spire.agent.runner import run_agent
from spire.config import PERSONAS_FILE


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
