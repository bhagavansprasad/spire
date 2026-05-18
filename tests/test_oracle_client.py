"""Integration tests for spire.oracle.client.

These hit the real Oracle 26ai container running locally. Skipped
if personas.yaml is missing.
"""

import pytest
from pydantic import BaseModel

from spire.config import (
    FusionCredentials,
    PERSONAS_FILE,
    Persona,
    load_persona,
)
from spire.oracle.client import OracleClient


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)


@pytest.mark.asyncio
async def test_oracle_client_smoke_select_user_and_pdb():
    """Connect as SPIRE, confirm we get back the right user and PDB.

    This is the end-to-end wiring check: persona load -> OracleClient
    construction -> async connect -> SELECT -> close. If this passes,
    the codebase is wired to the database.
    """
    persona = load_persona("default_dev")
    async with OracleClient(persona) as oc:
        row = await oc.fetch_one(
            "SELECT USER, SYS_CONTEXT('USERENV', 'CON_NAME') FROM DUAL"
        )
    assert row is not None
    connected_as, pdb_name = row
    assert connected_as == "SPIRE"
    assert pdb_name == "FREEPDB1"


@pytest.mark.asyncio
async def test_oracle_client_fetch_all_returns_list():
    """fetch_all returns a list; trivial multi-row query."""
    persona = load_persona("default_dev")
    async with OracleClient(persona) as oc:
        rows = await oc.fetch_all(
            "SELECT level FROM dual CONNECT BY level <= 3"
        )
    assert isinstance(rows, list)
    assert len(rows) == 3
    assert rows == [(1,), (2,), (3,)]


def test_oracle_client_rejects_persona_without_oracle_block():
    """Constructing OracleClient with a Fusion-only persona raises."""
    fusion_only = Persona(
        fusion=FusionCredentials(
            base_url="https://example.com",
            username="u",
            password="p",
            auth_type="basic",
        ),
        oracle=None,
    )
    with pytest.raises(RuntimeError, match="no oracle credentials"):
        OracleClient(fusion_only)
