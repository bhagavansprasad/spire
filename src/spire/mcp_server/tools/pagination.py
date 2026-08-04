"""Paged fetching against Fusion collections — one loop, several tools.

WHY THIS IS SHARED
Five tools paged independently before this existed, and the drift showed:
aggregate_purchase_orders used 200 per page while aggregate_invoices used
500, both citing the same reference note. One of them truncated every
unfiltered scan at 10,000 rows for months, and nothing connected the two
facts because the loops were in different files.

WHY THIS SIGNATURE
Not designed from one example. compare_orders_to_invoices and po_lifecycle
had each already written a private paged-fetch helper taking path and
fields as parameters — independently, and arriving at the same shape.
This takes that shape and adds what aggregate_purchase_orders learned:
a count probe before the loop.

Two implementations agreeing is a stronger argument than one, which is
why the parameterised signature won over the hardcoded one it replaced.

WHAT THE PROBE BUYS
A count before any data is fetched (FusionClient.total_results), turning
three guesses into measurements:

  - Progress gets a DENOMINATOR. "page 12" says nothing about how much
    remains; "page 12/32, 6,000/15,839" does.
  - The cap warning fires BEFORE the fetch rather than after. On
    /invoices the cap reaches 51% of the collection, so a two-minute wait
    ends in a partial answer that could have been announced at second
    one.
  - truncated stops being inferred. It was "the loop used all its pages",
    a proxy; with a total it is fetched against expected.

Measured 2026-08-04:

    /purchaseOrders     15,839   completes at 500 x 50
    /invoices           48,931   51% of the collection
    /standardReceipts   37,338   13%, and see below

WHAT THIS DELIBERATELY DOES NOT COVER
aggregate_standard_receipts_by_method. Its cap applies ONLY when the
query is unscoped (MAX_UNSCOPED_PAGES=10 versus no bound at all for an
account-scoped fetch), and it advances by len(items) rather than
page * size. That is a different rule, not a different constant, and
forcing it in here would mean a predicate parameter existing for one
caller. It keeps its own loop.
"""

from __future__ import annotations

import sys

from spire.fusion.client import FusionClient


# Defaults. Callers pass their own when they differ; these are the
# values proven against the pod on 2026-08-04.
#
# 500 per page: the endpoints reference documents ~200 as the practical
# maximum, and aggregate_invoices had been using 500 against /invoices
# successfully for as long as both existed. Measured on /purchaseOrders
# the same day — 32 pages of 500, no slowdown. The reference note is
# either stale or endpoint-specific; if a fetch starts erroring, that
# note is the first thing to re-read.
DEFAULT_PAGE_SIZE = 500

# 50 pages. A bound on runaway work, not a truncation point: at 500 that
# is 25,000 rows, which clears /purchaseOrders and does not clear
# /invoices. Raising it is a decision about how long a single question
# may take, and should be made deliberately rather than by nudging this
# number when one query truncates.
DEFAULT_MAX_PAGES = 50


def _render_bar(fetched: int, target: int, page: int, pages: int) -> str:
    """A 20-character bar, a percentage, and both raw counts.

    The raw counts stay even though the bar and the percentage both
    encode them: a bar is a feel for progress, and the number is what
    someone reads back off a saved log hours later.
    """
    pct = min(100, int(fetched / target * 100)) if target else 0
    filled = int(20 * pct / 100)
    bar = "#" * filled + "." * (20 - filled)
    return f"[{bar}] {pct:3d}%  page {page}/{pages}  {fetched:,}/{target:,}"


async def page_all(
    client: FusionClient,
    path: str,
    label: str,
    server_clause: str | None = None,
    fields: list[str] | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int = DEFAULT_MAX_PAGES,
    report_progress=None,
) -> tuple[list[dict], bool, int | None]:
    """Page a Fusion collection to exhaustion or the cap.

    Args:
        client: An open FusionClient.
        path: The resource path.
        label: Prefix for progress lines — the calling tool's name, so a
            log with several tools in it says which one is fetching.
        server_clause: Optional q= clause. Optional because two callers
            legitimately scan a whole collection: a status breakdown
            needs every status, so there is nothing selective to push to
            the server. Passed to the probe as well as the fetch, so the
            count describes the same set — a filtered fetch measured
            against an unfiltered total would report itself truncated
            forever.
        fields: Optional projection. Omitted entirely when None rather
            than sent empty; /standardReceipts returns HTTP 500 for a
            fields= parameter it does not like, and an empty projection
            is the kind of thing that trips it.
        page_size: Rows per request.
        max_pages: Bound on requests.
        report_progress: Optional async (progress, total, message).

    Returns:
        (items, hit_page_cap, total_available)

        total_available is None when the pod returned no count. Callers
        must not read that as zero — it means "unknown", and every
        behaviour that depends on it degrades to what this loop did
        before the probe existed.
    """
    total_available = await client.total_results(path, server_clause)
    overfetch_limit = page_size * max_pages

    # Before a single page is fetched, and loud. A footnote after the
    # fact is what let a 10,000-of-15,839 answer read as complete, with
    # one status understated by 860 million.
    #
    # SENT TWICE, ON PURPOSE. The print goes to the SERVER's stderr,
    # which on a normal run is a different terminal from the one the
    # question was asked in — measured 2026-08-04: the warning appeared
    # in the server log while the client watched a progress bar with no
    # indication it would stop at half the data. report_progress is the
    # channel that reaches the caller, so the warning goes down it too.
    #
    # This does not replace saying it in the ANSWER. Progress output is
    # transient and goes to stderr; a reader who redirects stdout keeps
    # the answer and loses this entirely. total_available rides on the
    # returned bucket for that reason.
    if total_available is not None and total_available > overfetch_limit:
        warning = (
            f"*** WARNING: {total_available:,} records match, and the page "
            f"cap stops at {overfetch_limit:,}. This answer will cover "
            f"{overfetch_limit / total_available:.0%} of the data. ***"
        )
        print(f"[{label}] {warning}", file=sys.stderr, flush=True)
        if report_progress is not None:
            # progress=0: nothing fetched yet. The message is the point.
            await report_progress(0, None, warning)

    expected_pages: int | None = None
    target: int | None = None
    if total_available is not None:
        target = min(total_available, overfetch_limit)
        expected_pages = min(max_pages, -(-total_available // page_size))

    items: list[dict] = []
    hit_page_cap = False

    for page in range(max_pages):
        params: dict[str, str | int] = {
            "limit": page_size,
            "offset": page * page_size,
            "onlyData": "true",
        }
        if server_clause:
            params["q"] = server_clause
        if fields:
            params["fields"] = ",".join(fields)

        response = await client.get(path, params=params)
        page_items = response.get("items", [])
        items.extend(page_items)

        if expected_pages and target:
            msg = _render_bar(len(items), target, page + 1, expected_pages)
        else:
            # No count from the pod: the old line, which is everything
            # that can honestly be said without a denominator.
            msg = f"page {page + 1}: +{len(page_items)} (total {len(items)})"

        # A bar that redraws in place is right for a terminal and wrong
        # for a file. Runs get piped through tee as a matter of habit,
        # and \r in a file collapses the whole fetch into one unreadable
        # line — and the saved output is what gets re-read later, so it
        # is the case that must stay legible.
        if sys.stderr.isatty():
            print(f"[{label}] {msg}", end="\r", file=sys.stderr, flush=True)
        else:
            print(f"[{label}] {msg}", file=sys.stderr, flush=True)

        if report_progress is not None:
            await report_progress(page + 1, expected_pages, msg)

        has_more = response.get("hasMore")
        if has_more is False or (
            has_more is None and len(page_items) < page_size
        ):
            break
    else:
        # Ran out of pages without the pod signalling the end.
        hit_page_cap = True

    # The loop can leave the cursor mid-line: a \r-terminated bar, then
    # an early break because the pod said hasMore=false before the
    # expected page count. Without this the next thing printed lands on
    # top of the bar.
    if sys.stderr.isatty():
        print("", file=sys.stderr, flush=True)

    return items, hit_page_cap, total_available
