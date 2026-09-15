"""Integration tests for the SPIRE API endpoints.

Requires:
  - KG loaded and reachable from this process
  - MCP server at 127.0.0.1:3333 (or SPIRE_MCP_URL)
  - personas.yaml present

Marked @pytest.mark.integration — the project's default pytest run
deselects these. Run them with:

    python -m pytest -q -m integration tests/test_api_endpoints.py

These are the API's end-to-end proof: the lifespan hook loads the menu
and opens the MCP session, /status reports readiness, and /prompt
returns a well-formed envelope. Any of the three failing means the API
is not deployable, regardless of what the unit tests say.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    """A TestClient with lifespan run. The lifespan hook loads the KG
    menu and opens an MCP session; if either fails, /status reports 503
    and the first assertion catches it."""
    from fastapi.testclient import TestClient
    from spire.api.server import app

    with TestClient(app) as c:
        yield c


def test_status_reports_ready(client):
    r = client.get("/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["pipeline_ready"] is True
    assert body["service"] == "spire-api"
    assert body["kg_version"] is None       # None until Phase 3g


def test_prompt_count_returns_text(client):
    r = client.post("/prompt", json={"prompt": "Count of suppliers"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "text"
    assert "suppliers" in body["answer"]["text"].lower()
    assert body["metadata"]["latency_ms"] > 0
    stages = body["metadata"]["stages"]
    names = {s["name"] for s in stages}
    assert "parse" in names
    assert "plan" in names


def test_prompt_malformed_request_returns_422(client):
    r = client.post("/prompt", json={})     # missing required "prompt"
    assert r.status_code == 422


def test_prompt_po_with_children_returns_table(client):
    r = client.post("/prompt", json={"prompt": "Show PO 2144 and its lines"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "table"
    records = body["answer"]["records"]
    assert len(records) == 1
    row = records[0]
    assert row.get("order_number") == "162352"
    assert isinstance(row.get("lines"), list)