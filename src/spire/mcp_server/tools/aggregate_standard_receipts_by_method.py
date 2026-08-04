"""Aggregate standard receipts by receipt method (Prompt 17).

Groups top-level /standardReceipts by ReceiptMethod, counts them, and sums
Amount per method. Optionally filter by customer name (resolved to account number)
or direct account_number. Returns groups sorted by total amount descending.

This is a bounded aggregation tool: grouping by ReceiptMethod and measure
(sum of amount) are fixed by identity.

PAGINATION. An earlier version issued ONE call with limit=500 and reported
whatever came back as the total. Account 26360 has 1,386 receipts, so the
result was a 500-row sample presented as a distribution — and because this
endpoint has NO DEFAULT ORDERING, two identical calls sampled different
rows and produced totals differing by ~32M. Nothing flagged it. This
version pages to exhaustion when scoped to an account, and caps with an
explicit truncated flag when unscoped (the pod-wide set is unbounded).

ORDERING (2026-08-04). Paging to exhaustion fixed the scoped case but not
the unscoped one: capped at 10 pages of 500, a pod-wide run still sampled
5,000 of 37,338 receipts, and without an orderBy it sampled a DIFFERENT
5,000 each time — two runs minutes apart differed by 102M. Every fetch
now sends orderBy=StandardReceiptId, so the sample is at least the same
sample. See _ORDER_BY.

Ordering alone would have been a poor trade. A PK-ascending cap takes the
OLDEST rows rather than arbitrary ones, so the capped distribution went
from a rough sample (4,754 Lockbox, 179 Check) to a skewed one (4,998
Lockbox, no Check at all) — repeatable, and less representative. The cap
was raised in the same change so the pod-wide case completes instead of
sampling. See MAX_UNSCOPED_PAGES.
"""

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.customer_account_by_name import get_customer_account_by_name

STANDARD_RECEIPTS_PATH = "/fscmRestApi/resources/11.13.18.05/standardReceipts"

# Rows per request. The endpoint accepts larger, but 500 keeps each
# response a reasonable size — fields= 500s here, so every row comes back
# full-width and there is no way to project it down.
PAGE_SIZE = 500

# Page ceiling for the UNSCOPED (pod-wide) case only. The scoped case pages
# to exhaustion: an account's receipt count is bounded and knowable
# (1,386 on the largest demo account). Pod-wide has no such bound, so it
# stops here and says so rather than paging indefinitely.
#
# RAISED FROM 10 TO 100 on 2026-08-04. At 500 rows per page, 10 pages was
# 5,000 of the 37,338 receipts on this pod — 13%, reported with a
# one-line footnote.
#
# The ordering fix below made that worse before it made it better.
# Unordered, the cap took an arbitrary 5,000 and the method split was at
# least a rough sample: 4,754 Lockbox and 179 Check on one run. Ordered by
# PK ascending it takes the OLDEST 5,000 — ids 1 upward — and the split
# became 4,998 Lockbox with Check gone from the results entirely. A stable
# answer that is systematically skewed towards 2012 data.
#
# So ordering alone would have shipped a repeatable wrong answer. 100
# pages is 50,000 rows, which clears the collection with headroom for
# growth, and the unscoped case now completes rather than sampling.
#
# This is a decision about how long one question may take: 75 sequential
# requests, at roughly the cost of the PO status breakdown's 32. If the
# collection outgrows 50,000 the cap fires again and the truncation note
# says so — which is the point of having a cap rather than looping until
# the pod stops.
MAX_UNSCOPED_PAGES = 100

# Sort key for every paginated fetch here. NOT optional.
#
# This endpoint has no default ordering, so walking `offset` without an
# `orderBy` can see shifted or overlapping pages between calls — the same
# question answered twice returns a different set of rows, with no error
# either time. Measured on this tool:
#
#   2026-07-22, account 26360, consecutive days, identical code:
#       both runs 1,386 receipts; totals 215,721,775.28 vs 250,557,301.49
#   2026-08-04, pod-wide, minutes apart:
#       both runs 5,000 receipts; totals 874,836,787.64 vs 977,327,230.90
#       and Lockbox moving 4,754 -> 4,934
#
# The endpoints reference recorded the rule ("any paginated fetch against
# /standardReceipts must specify a deterministic orderBy") with the sort
# key unconfirmed. Confirmed 2026-08-04: page 1 at limit=3 returned
# StandardReceiptIds 1, 2, 3; page 2 at offset=3 returned 4, 21, 22 —
# contiguous across the page boundary and ascending, so the parameter is
# applied rather than merely accepted.
#
# The PK, not ReceiptNumber: two rows both numbered "1" came back from an
# ordered fetch, so ReceiptNumber is not unique here and gives no
# deterministic tiebreak.
_ORDER_BY = "StandardReceiptId"


async def aggregate_standard_receipts_by_method(
    client: FusionClient,
    customer_name: str | None = None,
    account_number: str | None = None,
    limit: int | None = None,
) -> dict:
    """Aggregate receipts by receipt method.

    Args:
        customer_name: Customer name to filter receipts (resolved to account number).
        account_number: Direct CustomerAccountNumber (if customer_name not provided).
        limit: If provided, return only the top N groups by total amount
            (descending). Omit to return all groups.

    Returns:
        A dict with shape "receipt_method_distribution":
            shape: "receipt_method_distribution",
            total_receipts: int,
            total_amount: float,
            returned: int,
            truncated: bool,
            rows: [
                {
                    "receipt_method": str,
                    "receipt_count": int,
                    "total_amount": float,
                },
                ...
            ]

    Raises:
        ValueError: if customer_name is given but resolves to no account.
            Falling through to an unfiltered fetch would silently turn a
            customer-scoped question into a pod-wide one and answer it
            with the customer's name attached.
    """
    # Resolve customer_name to account_number if given.
    resolved_account = account_number
    if customer_name:
        accounts = await get_customer_account_by_name(client, customer_name, limit=1)
        if not accounts:
            raise ValueError(
                f"No customer account found for {customer_name!r}. "
                "Refusing to aggregate pod-wide receipts for a "
                "customer-scoped question."
            )
        resolved_account = accounts[0].get("AccountNumber")
        if not resolved_account:
            raise ValueError(
                f"Customer {customer_name!r} resolved to an account with no "
                "AccountNumber; cannot scope the receipt aggregation."
            )

    scoped = resolved_account is not None

    # Group as we page, so only the aggregate is held in memory.
    groups: dict[str, dict] = {}
    total_receipts = 0
    total_amount = 0.0
    truncated = False

    offset = 0
    pages = 0
    while True:
        params: dict[str, str | int] = {
            "limit": PAGE_SIZE,
            "offset": offset,
            "onlyData": "true",
            # Every page, not just the first: offset paging is only
            # meaningful against a stable order.
            "orderBy": _ORDER_BY,
        }
        if scoped:
            params["q"] = f"CustomerAccountNumber='{resolved_account}'"

        response = await client.get(STANDARD_RECEIPTS_PATH, params=params)
        items = response.get("items", [])

        for item in items:
            method = item.get("ReceiptMethod") or "(unknown)"
            if method not in groups:
                groups[method] = {
                    "receipt_method": method,
                    "receipt_count": 0,
                    "total_amount": 0.0,
                }
            groups[method]["receipt_count"] += 1
            amount = item.get("Amount")
            if isinstance(amount, (int, float)):
                groups[method]["total_amount"] += amount
                total_amount += amount
            total_receipts += 1

        pages += 1

        if not response.get("hasMore"):
            break
        if not items:
            # Defensive: hasMore true with an empty page would loop forever.
            break
        if not scoped and pages >= MAX_UNSCOPED_PAGES:
            truncated = True
            break

        offset += len(items)

    # Sort by total_amount descending
    sorted_rows = sorted(groups.values(), key=lambda x: x["total_amount"], reverse=True)
    if limit is not None:
        sorted_rows = sorted_rows[:limit]

    return {
        "shape": "receipt_method_distribution",
        "total_receipts": total_receipts,
        "total_amount": total_amount,
        "returned": len(sorted_rows),
        "truncated": truncated,
        "rows": sorted_rows,
    }
