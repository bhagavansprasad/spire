"""Guardrail: every MCP tool must have a SQL overlay entry.

THE INVARIANT
Every prompt Spire accepts and executes against Fusion must produce
equivalent executable SQL in the same response. Every prompt Spire
refuses produces no SQL. There is no third state.

This test enforces the first half of that invariant at the tool level:
every tool the MCP server registers must have a corresponding entry in
OVERLAY.tool_to_entity, or the emitter cannot produce SQL for a Plan
that uses it.

WHAT A FAILURE MEANS
A failure is not a bug in the test; it is the current backlog. The
assertion reports the exact list of unmapped tools, which is the roadmap
of Phases 2-4 of docs/design/SQL_OVERLAY_COMPLETENESS.md. Each phase
closes a chunk of the list, and the test turns green when the list is
empty.

WHY list_tools() AND NOT A SOURCE PARSE
The MCP server registers tools via decorators on a live FastMCP
instance. Parsing source for `@mcp.tool()` would work but couples the
test to a syntactic pattern that could change (decorator arguments,
conditional registration, etc.). Asking the running app is
authoritative: whatever tool the executor could actually call, the test
sees it.
"""

from __future__ import annotations

import pytest

from spire.kg.sql_overlay import OVERLAY


@pytest.mark.asyncio
async def test_every_mcp_tool_has_an_overlay_entry():
    from spire.mcp_server.server import mcp

    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    mapped_names = set(OVERLAY.tool_to_entity.keys())
    missing = sorted(tool_names - mapped_names)

    if missing:
        # Produce a readable multi-line message rather than a single
        # comma-joined string. A maintainer opening the failing test
        # should be able to read the list in one glance and compare it
        # to docs/design/SQL_OVERLAY_COMPLETENESS.md.
        lines = [f"{len(missing)} MCP tool(s) lack a SQL overlay entry:"]
        for name in missing:
            lines.append(f"  - {name}")
        lines.append("")
        lines.append(
            "See docs/design/SQL_OVERLAY_COMPLETENESS.md for the phase "
            "plan that closes this backlog."
        )
        pytest.fail("\n".join(lines))


@pytest.mark.asyncio
async def test_every_overlay_entry_corresponds_to_a_live_tool():
    """The inverse check.

    An overlay entry with no live tool is dead mapping. It can be
    left behind when a tool is retired, or added speculatively before a
    tool lands. Both are worth surfacing: the first is drift, the
    second is a test that already claims coverage the system does not
    have.
    """
    from spire.mcp_server.server import mcp

    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    mapped_names = set(OVERLAY.tool_to_entity.keys())
    orphans = sorted(mapped_names - tool_names)

    if orphans:
        lines = [f"{len(orphans)} overlay entry(ies) have no live MCP tool:"]
        for name in orphans:
            lines.append(f"  - {name}")
        pytest.fail("\n".join(lines))
