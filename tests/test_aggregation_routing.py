"""
Tests for feature 7 aggregation routing through the pipeline.

Covers the wiring added to take an aggregation Intent from parser output
through the planner to an executable single-step plan, and through the
executor as a passed-through ranking. The aggregation TOOL itself is
tested in test_aggregate_invoices_tool.py; this file tests ROUTING.

Layers (mirrors test_executor.py):
1. Planner unit tests — Intent -> Plan. No DB (the aggregation branch
   never opens a KG cursor).
2. Draft conversion unit tests — DraftIntent -> Intent.
3. Executor unit test — Plan -> outputs, with a mocked MCP session.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from spire.executor.executor import execute_plan
from spire.nl_parser.draft import DraftAggregate, DraftFilter, DraftIntent
from spire.planner.planner import Intent, generate_plan


# ── Planner: Intent -> Plan ───────────────────────────────────────────


def test_aggregation_intent_builds_single_tool_step():
    intent = Intent(
        target_entity="",
        aggregate={
            "op": "by_supplier",
            "date_from": "2026-01-01",
            "date_to": "2026-04-01",
            "top_n": 10,
        },
    )
    plan = generate_plan(intent)
    assert len(plan) == 1
    step = plan[0]
    assert step.tool_name == "aggregate_invoices_by_supplier"
    assert step.tool_args == {
        "date_from": "2026-01-01",
        "date_to": "2026-04-01",
        "top_n": 10,
    }
    assert step.iterate_over is None
    assert step.output_name == "aggregation"


def test_aggregation_empty_params_drop_to_tool_defaults():
    plan = generate_plan(
        Intent(target_entity="", aggregate={"op": "by_supplier"})
    )
    # None/absent params are dropped so the tool's own defaults apply.
    assert plan[0].tool_args == {}


def test_unsupported_aggregation_op_raises():
    with pytest.raises(NotImplementedError):
        generate_plan(Intent(target_entity="", aggregate={"op": "by_buyer"}))


# ── Draft conversion: DraftIntent -> Intent ───────────────────────────


def test_draft_with_aggregate_converts():
    d = DraftIntent(
        aggregate=DraftAggregate(
            op="by_supplier",
            date_from="2026-01-01",
            date_to="2026-04-01",
            top_n=10,
        )
    )
    intent = d.to_intent()
    assert intent.aggregate == {
        "op": "by_supplier",
        "date_from": "2026-01-01",
        "date_to": "2026-04-01",
        "top_n": 10,
    }


def test_draft_without_aggregate_is_none():
    d = DraftIntent(
        target_entity="Supplier",
        filters=[DraftFilter(type="country", value_json='"US"')],
    )
    intent = d.to_intent()
    assert intent.aggregate is None
    assert intent.filters == [{"type": "country", "value": "US"}]


def test_draft_empty_dates_become_none():
    d = DraftIntent(aggregate=DraftAggregate(op="by_supplier"))
    intent = d.to_intent()
    assert intent.aggregate == {
        "op": "by_supplier",
        "date_from": None,
        "date_to": None,
        "top_n": 10,
    }


# ── Executor: Plan -> outputs ─────────────────────────────────────────


def _mock_session(payload: object) -> AsyncMock:
    """An MCP session whose call_tool returns one TextContent block
    carrying the JSON payload (mirrors test_executor.py's _mock_session)."""
    block = type("Block", (), {"type": "text", "text": json.dumps(payload)})()
    result = type("Result", (), {"content": [block]})()
    session = AsyncMock()
    session.call_tool.return_value = result
    return session


@pytest.mark.asyncio
async def test_aggregation_ranking_passes_through_executor():
    ranking = {
        "shape": "supplier_spend_ranking",
        "date_from": "2026-01-01",
        "date_to": "2026-04-01",
        "total_suppliers": 47,
        "returned": 2,
        "truncated": False,
        "rows": [
            {"supplier": "Globex", "supplier_number": "2",
             "total_spend": 500, "invoice_count": 3},
            {"supplier": "Acme", "supplier_number": "1",
             "total_spend": 300, "invoice_count": 2},
        ],
    }
    plan = generate_plan(
        Intent(
            target_entity="",
            aggregate={"op": "by_supplier", "date_from": "2026-01-01",
                       "date_to": "2026-04-01", "top_n": 10},
        )
    )
    session = _mock_session(ranking)
    outputs, _, _ = await execute_plan(plan, session)

    # The ranking is not items-shaped, so the executor wraps the dict in a
    # single-element list. The synthesizer reads outputs["aggregation"][0].
    agg = outputs["aggregation"]
    assert isinstance(agg, list) and len(agg) == 1
    assert agg[0]["shape"] == "supplier_spend_ranking"
    assert agg[0]["rows"][0]["supplier"] == "Globex"
    assert agg[0]["total_suppliers"] == 47


# ── Integration: live MCP server + live pod ───────────────────────────
#
# End-to-end routing: an aggregation Intent -> plan -> execute_plan
# against the running MCP server, which calls the real aggregation tool
# against the live Fusion pod. Confirms the tool is registered and the
# ranking comes back over the wire intact.
#
# Requires:
#   - The MCP server running on http://127.0.0.1:3333/mcp/
#     (python -m spire.mcp_server.server)
#   - personas.yaml present and the pod reachable
#
# Marked @pytest.mark.integration; skipped by default. Run with:
#     pytest -m integration tests/test_aggregation_routing.py


@pytest.mark.integration
@pytest.mark.asyncio
async def test_aggregation_plan_against_live_mcp_server() -> None:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    MCP_SERVER_URL = "http://127.0.0.1:3333/mcp/"

    plan = generate_plan(
        Intent(
            target_entity="",
            aggregate={
                "op": "by_supplier",
                "date_from": "2022-01-01",
                "date_to": "2023-01-01",
                "top_n": 10,
            },
        )
    )

    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            outputs, _, _ = await execute_plan(plan, session)

    assert set(outputs.keys()) == {"aggregation"}
    agg = outputs["aggregation"]
    assert isinstance(agg, list) and len(agg) == 1
    result = agg[0]
    assert result["shape"] == "supplier_spend_ranking"
    assert result["returned"] <= 10
    assert result["returned"] <= result["total_suppliers"]
    # Ranking is spend-descending.
    spends = [r["total_spend"] for r in result["rows"]]
    assert spends == sorted(spends, reverse=True)
