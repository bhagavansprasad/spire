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
        if persona.fusion.auth_type != "basic":
            raise ValueError(
                f"Unsupported auth_type '{persona.fusion.auth_type}'. "
                "Only 'basic' is supported in the POC."
            )
        self._persona = persona
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "FusionClient":
        self._client = httpx.AsyncClient(
            base_url=self._persona.fusion.base_url,
            auth=httpx.BasicAuth(
                self._persona.fusion.username,
                self._persona.fusion.password,
            ),
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

    async def total_results(
        self, path: str, server_clause: str | None = None
    ) -> int | None:
        """How many records match, before fetching any of them.

        One cheap request — limit=1 with totalResults=true — asking the
        pod for a count rather than data.

        WHY THIS EXISTS
        The aggregation tools page until the pod says hasMore is false or
        a page cap stops them, and until 2026-08-04 none of them knew how
        many records existed. Three consequences, all measured that day:

          - A cap could truncate a normal query and nobody knew by how
            much. The PO status breakdown reported 10,000 records with a
            one-line footnote; the real collection is 15,839, and CLOSED
            was understated by 860 million.
          - truncated=True was INFERRED from "the loop used all its
            pages", which is a proxy. With a total it becomes a
            comparison: fetched vs expected.
          - Progress could only count pages done, never pages remaining.

        Measured support, all three endpoints the aggregation tools use:

            /purchaseOrders     15,839
            /invoices           48,931
            /standardReceipts   37,338

        Those numbers also say why the probe was worth the request. Only
        the PO scan completes at current caps: invoices reach 51% of the
        collection and standard receipts 13%.

        Args:
            path: The resource path, e.g. INVOICES_PATH.
            server_clause: Optional q= clause. Pass the SAME clause the
                fetch will use, or the count describes a different set
                than the one about to be fetched — a filtered fetch
                measured against an unfiltered total would report itself
                truncated forever.

        Returns:
            The count, or None when the pod does not return one.

            None is not an error and callers must not treat it as zero.
            Fusion omits totalResults on some resources and some
            parameter combinations, and a caller that cannot get a total
            should degrade — no progress denominator, no up-front cap
            warning — rather than refuse to run. The tools worked without
            this for months; it improves them, it is not load-bearing.
        """
        params: dict[str, Any] = {
            "limit": 1,
            "totalResults": "true",
            "onlyData": "true",
        }
        if server_clause:
            params["q"] = server_clause

        response = await self.get(path, params=params)
        total = response.get("totalResults")
        return total if isinstance(total, int) else None
