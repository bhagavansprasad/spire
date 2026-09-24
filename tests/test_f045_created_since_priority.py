"""F-045 — composite `created_since AND created_before` on /purchaseOrders.

The tool can send only ONE clause to the server (the pod cannot
AND-combine). When both bounds are set, one wins the server slot and
the other is applied client-side. WHICH one wins is not cosmetic.

The pod returns rows unordered across the fetch window. A `< before`
clause starts the window at the BOTTOM of the collection; a
`>= since` clause starts it at the range's lower edge. For a recent
range — the finding's own reproducer, "purchase orders created in
2023" — the upper-bound fetch starts in 2013 and never reaches 2023
within 200 rows, the client-side filter keeps nothing, and the answer
is 0 records over a range that holds 4,546.

Verified on dabpqy 2026-09-24:

    q=CreationDate >= '2023-01-01'    -> totalResults 4546, first row
                                         2023-01-11
    q=CreationDate <  '2024-01-01'    -> 200 rows, 2013-12-11 ->
                                         2014-02-12, zero in 2023
    q=composite (both)                -> HTTP 400 (loud rejection,
                                         not silent-zero like
                                         /invoices)

The fix is a two-line reorder in the server-clause priority chain:
`created_since` beats `created_before`. These tests exercise the chain
directly — no pod, no LLM. The decision happens before any I/O, so a
recording fake is enough.
"""

import asyncio

from spire.mcp_server.tools.purchase_orders import search_purchase_orders


class _RecordingClient:
    """Minimal FusionClient stand-in: records each .get() call and
    returns an empty item set. The tool's choice of server clause is
    visible in the recorded params, which is all these tests need."""

    def __init__(self, items=None):
        self.calls = []
        self._items = list(items or [])

    async def get(self, path, params=None):
        self.calls.append({"path": path, "params": dict(params or {})})
        return {"items": list(self._items), "totalResults": len(self._items)}

    async def total_results(self, path, clause):
        return len(self._items)


def _q(**kwargs):
    """Run the tool once with the given args, return the q= clause it
    chose (or None when it sent none)."""
    client = _RecordingClient()
    asyncio.run(search_purchase_orders(client, **kwargs))
    assert client.calls, "tool made no .get() call"
    return client.calls[0]["params"].get("q")


# ---- the fix -----------------------------------------------------------

def test_created_since_wins_when_both_bounds_set():
    """The core assertion. Before this fix, the tool sent the
    `created_before` clause and returned 0 records for a range with
    thousands — the 200-row window started in 2013."""
    q = _q(created_since="2023-01-01", created_before="2024-01-01")
    assert q == "CreationDate >= '2023-01-01'", q


def test_reproducer_does_not_send_composite_and():
    """The tool never sends a composite clause — the pod 400s on it.
    Guard against a future 'fix' that tries to push both bounds."""
    q = _q(created_since="2023-01-01", created_before="2024-01-01")
    assert " AND " not in q.upper(), q


# ---- siblings must be unchanged ----------------------------------------

def test_created_before_alone_still_uses_less_than():
    """One-sided `before` prompt: the tool must still send `<`."""
    q = _q(created_before="2024-01-01")
    assert q == "CreationDate < '2024-01-01'", q


def test_created_since_alone_still_uses_greater_equal():
    """One-sided `since` prompt: unchanged."""
    q = _q(created_since="2023-01-01")
    assert q == "CreationDate >= '2023-01-01'", q


# ---- over-reach guards -------------------------------------------------
#
# This fix reorders two branches. Every other branch in the chain is a
# candidate for accidental movement. These tests pin the neighbours.

def test_status_still_wins_over_creation_dates():
    """Status sits above the CreationDate pair. Reordering that pair
    must not lift them above status."""
    q = _q(status="OPEN", created_since="2023-01-01", created_before="2024-01-01")
    assert q == "StatusCode='OPEN'", q


def test_supplier_id_still_wins_over_status():
    """supplier_id is the top of the chain."""
    q = _q(supplier_id=42, status="OPEN", created_since="2023-01-01")
    assert q == "SupplierId=42", q


def test_last_updated_branches_above_creation_date_branches():
    """F-047's LastUpdateDate branches sit above the CreationDate pair.
    The reorder must leave that relationship intact."""
    q = _q(last_updated_before="2025-09-23", created_since="2023-01-01")
    assert q == "LastUpdateDate < '2025-09-23'", q


def test_last_updated_after_above_creation_since():
    """Same guard, the other LastUpdateDate branch."""
    q = _q(last_updated_after="2025-09-23", created_since="2023-01-01")
    assert q == "LastUpdateDate >= '2025-09-23'", q


def test_supplier_name_still_below_creation_dates():
    """supplier_name is the lowest-priority branch. When both a name
    fragment and a date bound are set, the date must win — that was the
    existing behaviour before this fix and it stays."""
    q = _q(supplier_name="Lee", created_since="2023-01-01")
    assert q == "CreationDate >= '2023-01-01'", q


# ---- orderBy is part of the fix, not a separate concern ----------------
#
# Picking `>= since` as the server clause is not sufficient on its own:
# the pod's default physical scan on /purchaseOrders starts at the far
# end of the collection, so a 200-row window of `CreationDate >=
# '2023-01-01'` on dabpqy 2026-09-24 began at 2024-07-01. The client-side
# filter then dropped all 200. Pinning the order to CreationDate
# ascending puts the window at the range's lower edge.
#
# Both halves are tested. The first red pre-fix; the second is a
# both-trees-pass guard — removing the orderBy entirely would still
# leave the reorder test green, so the guard pins the orderBy
# specifically.

def _params(**kwargs):
    """Run the tool once, return the FULL params dict of the first call."""
    client = _RecordingClient()
    asyncio.run(search_purchase_orders(client, **kwargs))
    assert client.calls, "tool made no .get() call"
    return client.calls[0]["params"]


def test_created_since_sets_creation_date_ascending_order():
    """The core assertion for the orderBy half of the fix."""
    p = _params(created_since="2023-01-01")
    assert p.get("orderBy") == "CreationDate:asc", p


def test_created_since_alone_still_sets_orderby():
    """Even with only one bound, the range's lower edge is not the pod's
    default starting point. `>= since` alone landed on 2024-07-01
    without this."""
    p = _params(created_since="2023-01-01")
    assert "q" in p and p["q"] == "CreationDate >= '2023-01-01'"
    assert p.get("orderBy") == "CreationDate:asc"


def test_created_before_alone_does_not_add_orderby():
    """`< before` scans from the bottom of the collection upward, which
    is already where the range starts. Adding an orderBy here would be
    untested behaviour, not a fix, so it stays off."""
    p = _params(created_before="2024-01-01")
    assert p.get("q") == "CreationDate < '2024-01-01'", p
    assert "orderBy" not in p, p


def test_orderby_not_leaked_when_supplier_id_drives_the_clause():
    """The new orderBy variable must not attach to clauses it does not
    belong to. With supplier_id set, the CreationDate branch never
    runs — assert the orderBy stays absent."""
    p = _params(supplier_id=42, created_since="2023-01-01")
    assert p.get("q") == "SupplierId=42", p
    assert "orderBy" not in p, p
