"""
Tests for the shared paged-fetch helper (tools/pagination.py).

MOVED, NOT WRITTEN. These six tests lived in test_po_lifecycle_tool.py
and exercised that module's private _page_all. When four tools' paging
loops collapsed into one shared helper on 2026-08-04, the tests followed
the code: they were never about lifecycle reconciliation, they were about
paging, and leaving them behind would have meant one tool's test file
owning behaviour every tool now depends on.

They also caught the removal. Deleting po_lifecycle._page_all broke this
file's import immediately — a reminder that "enumerate every caller
before extracting" means tests/ as well as src/, which was skipped on
that file and not on the one before it.

WHAT CHANGED IN THE MOVE
Only the call shape. _PAGE_SIZE and MAX_PAGES were module constants that
tests monkeypatched; page_all takes them as arguments, so the tests pass
values instead of patching. Every assertion is unchanged.

THE FAKE
FakeClient here is a trimmed copy of the one in test_po_lifecycle_tool.py
— routing by path fragment, recording every call, and serving a LIST of
responses per fragment. That last part is what makes it possible to
assert totalResults is read from the FIRST page and not re-read later,
which is the behaviour page_all took from po_lifecycle in the first
place.
"""

from __future__ import annotations

import pytest

from spire.mcp_server.tools.pagination import (
    DEFAULT_MAX_PAGES,
    DEFAULT_PAGE_SIZE,
    page_all,
)


INVOICES_PATH = "/fscmRestApi/resources/11.13.18.05/invoices"
SCHEDULES_PATH = (
    "/fscmRestApi/resources/11.13.18.05/purchaseOrderSchedules"
)


class FakeClient:
    """Stub FusionClient. Routes by path substring; records every call.

    `pages` maps a path fragment to a LIST of responses returned in
    order. A single-response list is reused for every page, so a test
    that does not care about page-to-page differences need not spell out
    each page.
    """

    _ORDER = ("purchaseOrderSchedules", "invoices")

    def __init__(self, pages: dict[str, list[dict]]):
        self.pages = {k: list(v) for k, v in pages.items()}
        self.calls: list[tuple[str, dict]] = []

    async def get(self, path: str, params: dict | None = None) -> dict:
        self.calls.append((path, dict(params or {})))
        for fragment in self._ORDER:
            if fragment in path and fragment in self.pages:
                responses = self.pages[fragment]
                if not responses:
                    return {"items": [], "hasMore": False}
                # Keep the last response once the list runs out, so a
                # one-element list serves every page.
                return responses.pop(0) if len(responses) > 1 else responses[0]
        return {"items": [], "hasMore": False}


def _page(items, has_more=False, total=None):
    body = {"items": items, "hasMore": has_more}
    if total is not None:
        body["totalResults"] = total
    return body


_SCHEDULES = [{"Amount": 10.0}, {"Amount": 20.0}]


# ─────────────────────────────────────────────────────────────────────
# Asking for the count
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_page_all_requests_total_results_on_every_page():
    # A totalResults you did not request is not there. Without it the pod
    # returns `count`, which is the PAGE size, not the total.
    client = FakeClient(
        {"purchaseOrderSchedules": [_page(_SCHEDULES, has_more=False, total=2)]}
    )
    await page_all(
        client, SCHEDULES_PATH, "schedules",
        server_clause="OrderNumber='701337'", fields=["Amount"],
    )
    _, params = client.calls[0]
    assert params["totalResults"] == "true"


@pytest.mark.asyncio
async def test_page_all_returns_the_pods_own_total():
    client = FakeClient(
        {"purchaseOrderSchedules": [_page(_SCHEDULES, has_more=False, total=2)]}
    )
    items, hit_cap, total = await page_all(
        client, SCHEDULES_PATH, "schedules",
        server_clause="OrderNumber='701337'", fields=["Amount"],
    )
    assert len(items) == 2
    assert hit_cap is False
    assert total == 2


@pytest.mark.asyncio
async def test_page_all_reads_total_from_the_first_page_only():
    """Reading it from the LAST page loses it exactly when it is needed.

    The run that hits the cap is the run whose count matters most, and
    that run's last page is the one the loop stops on — so a count read
    at the end is a count that vanishes under truncation.
    """
    client = FakeClient({"invoices": [
        _page([{"a": 1}, {"a": 2}], has_more=True, total=3),
        _page([{"a": 3}], has_more=False),  # no totalResults on page 2
    ]})
    items, hit_cap, total = await page_all(
        client, INVOICES_PATH, "invoices",
        server_clause="PurchaseOrderNumber='X'", fields=["InvoiceId"],
        page_size=2,
    )
    assert len(items) == 3
    assert hit_cap is False
    assert total == 3


@pytest.mark.asyncio
async def test_page_all_total_is_none_when_pod_omits_it():
    # An honest unknown, not a zero. Callers must not treat it as a
    # count — every behaviour that depends on it degrades instead.
    client = FakeClient({"invoices": [{"items": [], "hasMore": False}]})
    _, _, total = await page_all(
        client, INVOICES_PATH, "invoices",
        server_clause="PurchaseOrderNumber='X'", fields=["InvoiceId"],
    )
    assert total is None


# ─────────────────────────────────────────────────────────────────────
# The cap
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_page_all_reports_the_cap():
    client = FakeClient({"invoices": [_page([{"a": 1}], has_more=True, total=99)]})
    items, hit_cap, total = await page_all(
        client, INVOICES_PATH, "invoices",
        server_clause="PurchaseOrderNumber='X'", fields=["InvoiceId"],
        page_size=1, max_pages=3,
    )
    assert hit_cap is True
    assert len(items) == 3
    assert total == 99, "the count must survive so truncation is quantifiable"


@pytest.mark.asyncio
async def test_page_all_warns_before_finishing_when_the_cap_will_bite(capsys):
    """The warning fires off page one, not after the last page.

    Measured on /invoices: 48,931 records against a 25,000 cap. Reported
    at the end, that is a footnote under an answer already read; reported
    off page one, it is a chance to stop waiting.
    """
    client = FakeClient({"invoices": [_page([{"a": 1}], has_more=True, total=99)]})
    await page_all(
        client, INVOICES_PATH, "invoices",
        server_clause="PurchaseOrderNumber='X'", fields=["InvoiceId"],
        page_size=1, max_pages=3,
    )
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "99" in err


@pytest.mark.asyncio
async def test_page_all_does_not_warn_when_the_fetch_completes():
    client = FakeClient(
        {"purchaseOrderSchedules": [_page(_SCHEDULES, has_more=False, total=2)]}
    )
    _, hit_cap, _ = await page_all(
        client, SCHEDULES_PATH, "schedules",
        server_clause="OrderNumber='701337'", fields=["Amount"],
    )
    assert hit_cap is False


# ─────────────────────────────────────────────────────────────────────
# Query shape
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_page_all_sends_a_single_clause():
    # Composite q= fails silently on this pod: HTTP 200, totalResults 0.
    client = FakeClient({"invoices": [_page([], total=0)]})
    await page_all(
        client, INVOICES_PATH, "invoices",
        server_clause="PurchaseOrderNumber='X'", fields=["InvoiceId"],
    )
    _, params = client.calls[0]
    assert " AND " not in params["q"]
    assert params["q"].count("=") == 1


@pytest.mark.asyncio
async def test_page_all_omits_fields_entirely_when_not_projecting():
    """An absent projection must not become an empty one.

    /standardReceipts returns HTTP 500 for a fields= parameter it does
    not like, and an empty projection is the kind of thing that trips it.
    aggregate_invoices deliberately fetches whole bodies, so this is a
    live path, not a defensive one.
    """
    client = FakeClient({"invoices": [_page([], total=0)]})
    await page_all(
        client, INVOICES_PATH, "invoices",
        server_clause="PurchaseOrderNumber='X'",
    )
    _, params = client.calls[0]
    assert "fields" not in params


@pytest.mark.asyncio
async def test_page_all_omits_the_clause_when_scanning_a_collection():
    """No q= at all is a legitimate call, not a missing argument.

    Grouping BY status needs every status, so there is nothing selective
    to push to the server. Sending an empty q= instead would be a filter
    matching nothing.
    """
    client = FakeClient({"invoices": [_page([], total=0)]})
    await page_all(client, INVOICES_PATH, "invoices")
    _, params = client.calls[0]
    assert "q" not in params


@pytest.mark.asyncio
async def test_defaults_are_the_measured_values():
    """The defaults are a decision, not an accident.

    500 per page was proven against /purchaseOrders on 2026-08-04 (32
    pages, no slowdown) despite the endpoints reference documenting ~200.
    50 pages bounds runaway work at 25,000 rows. Both are asserted here
    so that changing either is a deliberate act with a failing test
    attached, rather than a nudge that quietly retunes four tools.
    """
    assert DEFAULT_PAGE_SIZE == 500
    assert DEFAULT_MAX_PAGES == 50
