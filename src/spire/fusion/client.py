"""Async HTTP client for Oracle Fusion REST API.

Wraps httpx.AsyncClient with persona-driven auth and base URL.
GET only for now; other methods added when needed.

Usage:
    from spire.config import load_persona
    from spire.fusion.client import FusionClient

    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        data = await client.get(
            "/fscmRestApi/resources/11.13.18.05/suppliers",
            params={"limit": 5},
        )
"""

from typing import Any

import httpx

from spire.config import Persona


class FusionClient:
    def __init__(self, persona: Persona):
        if persona.auth_type != "basic":
            raise ValueError(
                f"Unsupported auth_type '{persona.auth_type}'. "
                "Only 'basic' is supported in the POC."
            )
        self._persona = persona
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "FusionClient":
        self._client = httpx.AsyncClient(
            base_url=self._persona.base_url,
            auth=httpx.BasicAuth(self._persona.username, self._persona.password),
            headers={"Accept": "application/json"},
            timeout=30.0,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        """GET a Fusion REST endpoint. Returns parsed JSON.

        Raises httpx.HTTPStatusError on non-2xx responses.
        """
        if self._client is None:
            raise RuntimeError("FusionClient must be used as an async context manager.")
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()
