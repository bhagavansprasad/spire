"""Async Oracle Database client for Spire.

Wraps oracledb's async API with persona-driven connection details.
Used as an async context manager; mirrors the FusionClient shape so
the codebase stays consistent.

Surface (intentionally minimal — grows as later phases need it):
- execute(sql, params=None)        — DDL / DML; returns nothing
- fetch_all(sql, params=None)      — SELECT; returns list of tuples
- fetch_one(sql, params=None)      — SELECT; returns first tuple or None

Usage:
    from spire.config import load_persona
    from spire.oracle.client import OracleClient

    persona = load_persona("default_dev")
    async with OracleClient(persona) as oc:
        rows = await oc.fetch_all(
            "SELECT USER, SYS_CONTEXT('USERENV', 'CON_NAME') FROM DUAL"
        )

Notes:
- Uses oracledb thin mode (pure Python, no Instant Client required).
- Raises RuntimeError if persona.oracle is None (the persona is
  Fusion-only and doesn't carry DB credentials).
- Exceptions from oracledb bubble naturally — no custom exception
  classes, same convention as FusionClient.
"""

from typing import Any

import oracledb

from spire.config import Persona


class OracleClient:
    def __init__(self, persona: Persona):
        if persona.oracle is None:
            raise RuntimeError(
                "Persona has no oracle credentials. "
                "Add an 'oracle:' block to this persona in personas.yaml."
            )
        self._persona = persona
        self._conn: oracledb.AsyncConnection | None = None

    async def __aenter__(self) -> "OracleClient":
        assert self._persona.oracle is not None  # narrowed by __init__
        self._conn = await oracledb.connect_async(
            user=self._persona.oracle.username,
            password=self._persona.oracle.password,
            dsn=self._persona.oracle.dsn,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def execute(
        self,
        sql: str,
        params: dict[str, Any] | list[Any] | None = None,
    ) -> None:
        """Execute a DDL or DML statement. No result returned."""
        if self._conn is None:
            raise RuntimeError("OracleClient must be used as an async context manager.")
        async with self._conn.cursor() as cur:
            await cur.execute(sql, params or [])

    async def fetch_all(
        self,
        sql: str,
        params: dict[str, Any] | list[Any] | None = None,
    ) -> list[tuple]:
        """Execute a SELECT and return all rows as a list of tuples."""
        if self._conn is None:
            raise RuntimeError("OracleClient must be used as an async context manager.")
        async with self._conn.cursor() as cur:
            await cur.execute(sql, params or [])
            return await cur.fetchall()

    async def fetch_one(
        self,
        sql: str,
        params: dict[str, Any] | list[Any] | None = None,
    ) -> tuple | None:
        """Execute a SELECT and return the first row, or None if no rows."""
        if self._conn is None:
            raise RuntimeError("OracleClient must be used as an async context manager.")
        async with self._conn.cursor() as cur:
            await cur.execute(sql, params or [])
            return await cur.fetchone()
