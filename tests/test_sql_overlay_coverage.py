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
    # Two ways a tool can be covered:
    #   1. It has a mapping in tool_to_entity (the emitter produces a
    #      SELECT against a physical table).
    #   2. It is listed in not_expressible (the emitter produces an
    #      explicit "not expressible as one SELECT" comment).
    # Both satisfy the invariant, because in both cases the emitted
    # output is the honest, correct representation of the Plan step.
    covered = set(OVERLAY.tool_to_entity.keys()) | OVERLAY.not_expressible
    missing = sorted(tool_names - covered)

    if missing:
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
    # An overlay entry (in tool_to_entity) OR a not_expressible declaration
    # is a valid annotation; both must reference a live tool.
    annotated = set(OVERLAY.tool_to_entity.keys()) | OVERLAY.not_expressible
    orphans = sorted(annotated - tool_names)

    if orphans:
        lines = [f"{len(orphans)} overlay entry(ies) have no live MCP tool:"]
        for name in orphans:
            lines.append(f"  - {name}")
        pytest.fail("\n".join(lines))


@pytest.mark.asyncio
async def test_not_expressible_entries_are_real_tools():
    """The not_expressible set has the same reverse-direction guard.

    A not_expressible declaration for a tool that does not exist is
    dead state: it would make the coverage invariant lie, because the
    forward direction treats the entry as covered even though there is
    nothing to cover. Every entry in `OVERLAY.not_expressible` must
    name a live MCP tool.
    """
    from spire.mcp_server.server import mcp

    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    orphans = sorted(OVERLAY.not_expressible - tool_names)
    if orphans:
        lines = [f"{len(orphans)} not_expressible entry(ies) have no live MCP tool:"]
        for name in orphans:
            lines.append(f"  - {name}")
        pytest.fail("\n".join(lines))
