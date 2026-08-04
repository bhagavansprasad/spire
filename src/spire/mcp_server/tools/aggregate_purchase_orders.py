"""Purchase-order aggregation tool — committed value ranked by supplier.

Plain async function — not coupled to FastMCP. Registration happens in
spire.mcp_server.server, exactly like search_purchase_orders.

WHAT THIS IS
A *specific, bounded* aggregation tool, the PO-side twin of
aggregate_invoices_by_supplier. It groups purchase orders by supplier,
sums Ordered, ranks suppliers by total committed value descending, and
returns the top_n. Grouping (by supplier) and the measure (sum of
Ordered) are FIXED BY IDENTITY — they are not parameters. A different
grouping or measure is a different tool, never a flag on this one. That
line keeps the aggregation layer a set of bounded tools rather than a
generic engine.

The LLM never does the arithmetic. This Python tool does. The tool
returns a small structured result; the synthesizer phrases it.

DIFFERENCE FROM aggregate_invoices_by_supplier
Same shape, three real differences — none of them cosmetic:

1. GROUPING KEY. Invoices carry SupplierNumber (a string); purchase
   orders do NOT — the PO header has SupplierId (numeric) and Supplier
   only. Verified live: asking for SupplierNumber in ?fields= on
   /purchaseOrders returns HTTP 400. So this tool groups on
   (SupplierId, Supplier), and its rows carry supplier_id where the
   invoice ranking carries supplier_number. This is the same
   SupplierNumber-vs-SupplierId asymmetry documented in the endpoints
   reference, surfacing again in aggregation.
2. MEASURE. Ordered (the PO amount excluding tax), not InvoiceAmount.
   Ordered is the committed value — what was ordered, not what was
   billed.
3. SERVER FILTER. StatusCode IS queryable server-side on this pod
   (verified: q=StatusCode='OPEN' returns rows), so a status filter
   bounds the fetch at the server rather than paging everything. Note
   this contradicts the older reference note that PO status must be
   filtered client-side.

DATE FILTERING — NOT AVAILABLE HERE
`OrderDate` is NOT queryable on this pod (HTTP 400: "The attribute(s)
[OrderDate] are not queriable"), unlike InvoiceDate on /invoices. So
this tool does not offer a date range: it cannot bound the fetch by
date at the server, and a client-side date filter over a page-capped
fetch would silently understate the ranking. `CreationDate` IS queryable
and a later phase may use it — but "created" is not "ordered", and this
tool will not pretend otherwise.

BOUNDED WINDOW
Pages to MAX_PAGES. If the cap is hit there may be more matching POs
than we saw, so truncated=True and the sums are LOWER BOUNDS. The
synthesizer must say so — a "total committed value" that silently omits
POs is worse than one that admits its window.

DETERMINISM
Suppliers are ranked by total_ordered descending, then supplier name
ascending as a tiebreaker, so "the Nth supplier" is the same supplier on
every run and the top_n cut is deterministic rather than arbitrary.

EMPTY RESULT
Zero matching POs returns a well-formed empty ranking
(total_suppliers=0, returned=0, rows=[]), never an error.
"""

from __future__ import annotations

import sys

from spire.fusion.client import FusionClient


PURCHASE_ORDERS_PATH = "/fscmRestApi/resources/11.13.18.05/purchaseOrders"

# Page size per fetch. Raised from 200 to 500 on 2026-08-04.
#
# The endpoints reference documents ~200 as the pod's practical maximum
# before requests get slow, and this file honoured that. Two things
# argued against it:
#
#   1. aggregate_invoices.py has used 500 against /invoices all along and
#      works — 50 pages of 500 complete routinely. The reference note and
#      the shipped code have disagreed for as long as both existed, and
#      the disagreement was never resolved, only noted.
#   2. At 200, MAX_PAGES * _PAGE_SIZE = 10,000, and the collection is
#      larger than that (see below), so every unfiltered scan truncated.
#      A cap that fires on an ordinary query is set wrong.
#
# 500 against /purchaseOrders is NOT independently measured — it is
# inferred from /invoices. If runs slow badly or start erroring, the
# reference note is right and this goes back to 200 with MAX_PAGES raised
# instead.
_PAGE_SIZE = 500

# Max pages before stopping. Bounds the work; hitting it flags the
# result truncated (sums become lower bounds). At 500/page, 50 pages =
# 25,000 POs.
#
# THE COLLECTION IS 15,839 POs, not the 3,362 this comment claimed until
# 2026-08-04. Measured directly:
#
#   /purchaseOrders?limit=1&totalResults=true  ->  totalResults: 15839
#
# The old figure made the cap look comfortable when it was not: at 200 a
# full scan needs 80 pages, so every unfiltered breakdown stopped at
# 10,000 of 15,839 and reported lower bounds. Nothing was broken — the
# tool said truncated=True and the summary said so — but the answer
# covered 63% of the data and read like a full one.
#
# At 500/page the scan is 32 pages, inside this cap, so an unfiltered
# breakdown now completes and truncated comes back False.
#
# Worth noting how the wrong number survived: it was in a docstring,
# nobody re-measured it, and it was used as the reason a cap was safe.
# One curl settled it.
MAX_PAGES = 50

OVERFETCH_LIMIT = _PAGE_SIZE * MAX_PAGES

# Minimal projection: the supplier to group by, the amount to sum, the
# status to filter/report. NOTE: no SupplierNumber — POs don't have one.
_PROJECTED_FIELDS = [
    "SupplierId",
    "Supplier",
    "Ordered",
    "StatusCode",
]

# The shape tag the synthesizer branches on. Distinct from
# supplier_spend_ranking: the rows carry supplier_id, not
# supplier_number, so it needs its own schema and validator.
_SHAPE = "supplier_po_value_ranking"


async def _fetch_all_pages(
    client: FusionClient,
    server_clause: str | None,
    tool_label: str,
    report_progress=None,
) -> tuple[list[dict], bool, int | None]:
    """Page through /purchaseOrders, and say how much is being missed.

    All three tools in this module page identically — same path, same
    projection, same cap, same end condition. They had three copies of
    that loop, which is why the page size was wrong in one place and
    right in another for as long as it was. One loop, three callers.

    WHAT THE PROBE BUYS
    A count before any data is fetched (see FusionClient.total_results),
    which turns three guesses into measurements:

      - The progress line gets a DENOMINATOR. "page 12" says nothing
        about how much is left; "page 12/32, 6,000/15,839 (38%)" does.
      - The cap warning fires BEFORE the fetch instead of after. On
        /invoices the cap covers 51% of the collection, so a two-minute
        wait ends in a partial answer that could have been announced at
        second one.
      - truncated stops being inferred. It was "the loop used all its
        pages", a proxy; with a total it is fetched-vs-expected.

    A probe that returns None degrades all three back to the previous
    behaviour rather than failing. See the return note on
    total_results — Fusion omits the count on some resources, and this
    module worked without it for months.

    Returns:
        (items, hit_page_cap, total_available)
    """
    total_available = await client.total_results(
        PURCHASE_ORDERS_PATH, server_clause
    )

    # Up front, before a single page is fetched. Loud on purpose: a
    # footnote after the fact is what let a 10,000-of-15,839 answer read
    # as complete, with CLOSED understated by 860 million.
    if total_available is not None and total_available > OVERFETCH_LIMIT:
        print(
            f"[{tool_label}] "
            f"*** WARNING: {total_available:,} records match, and the page "
            f"cap stops at {OVERFETCH_LIMIT:,}. This answer will cover "
            f"{OVERFETCH_LIMIT / total_available:.0%} of the data. ***",
            file=sys.stderr,
            flush=True,
        )

    expected_pages: int | None = None
    if total_available is not None:
        expected_pages = min(
            MAX_PAGES, -(-total_available // _PAGE_SIZE)  # ceil division
        )

    items: list[dict] = []
    hit_page_cap = False
    for page in range(MAX_PAGES):
        params: dict[str, str | int] = {
            "limit": _PAGE_SIZE,
            "offset": page * _PAGE_SIZE,
            "onlyData": "true",
            "fields": ",".join(_PROJECTED_FIELDS),
        }
        if server_clause:
            params["q"] = server_clause

        response = await client.get(PURCHASE_ORDERS_PATH, params=params)
        page_items = response.get("items", [])
        items.extend(page_items)

        if expected_pages:
            pct = min(100, int(len(items) / min(total_available, OVERFETCH_LIMIT) * 100))
            bar_width = 20
            filled = int(bar_width * pct / 100)
            bar = "#" * filled + "." * (bar_width - filled)
            msg = (
                f"[{bar}] {pct:3d}%  page {page + 1}/{expected_pages}  "
                f"{len(items):,}/{min(total_available, OVERFETCH_LIMIT):,}"
            )
        else:
            # No total from the pod: the old line, which is all that can
            # honestly be said without a denominator.
            msg = f"page {page + 1}: +{len(page_items)} (total {len(items)})"

        # A bar that redraws in place is right for a terminal and wrong
        # for a file. Runs here are piped through tee as a matter of
        # habit, and a file full of carriage returns is one unreadable
        # line — the saved output is what gets re-read hours later, so it
        # is the case that must stay legible.
        #
        # isatty() distinguishes them: live bar on a terminal, one line
        # per page into a pipe. Same information either way.
        _last = (page + 1 == expected_pages) if expected_pages else False
        if sys.stderr.isatty():
            end = "\n" if _last else "\r"
            print(f"[{tool_label}] {msg}", end=end, file=sys.stderr, flush=True)
        else:
            print(f"[{tool_label}] {msg}", file=sys.stderr, flush=True)

        if report_progress is not None:
            await report_progress(page + 1, expected_pages, msg)

        has_more = response.get("hasMore")
        if has_more is False or (
            has_more is None and len(page_items) < _PAGE_SIZE
        ):
            break
    else:
        # Exhausted MAX_PAGES without the pod signalling the end — there
        # may be more matching POs than we fetched.
        hit_page_cap = True

    # The loop can leave the cursor mid-line: a \r-terminated bar, then
    # an early break because the pod said hasMore=false before the
    # expected page count. Without this the next thing printed lands on
    # top of the bar.
    if sys.stderr.isatty():
        print("", file=sys.stderr, flush=True)

    return items, hit_page_cap, total_available


def _aggregate_rows(
    purchase_orders: list[dict], top_n: int
) -> tuple[list[dict], int]:
    """Group POs by supplier, sum Ordered, rank, and cut to top_n.

    Pure function — no I/O — so it is unit-testable without a client.

    Grouping key is (SupplierId, Supplier). SupplierId is the stable
    identifier; Supplier is the display name. POs missing both are
    skipped (they cannot be attributed to a supplier). POs with a
    non-numeric or missing Ordered contribute 0 to the sum but still
    count toward po_count, so the count stays an honest "how many POs we
    saw for this supplier".

    Returns:
        (rows, total_suppliers) where rows is the top_n ranking and
        total_suppliers is the number of DISTINCT suppliers seen before
        the cut (so the caller can report "top N of M").
    """
    groups: dict[tuple, dict] = {}

    for po in purchase_orders:
        supplier_id = po.get("SupplierId")
        supplier_name = po.get("Supplier") or ""
        if supplier_id is None and not supplier_name:
            # Cannot attribute this PO to any supplier; skip it.
            continue

        key = (supplier_id, supplier_name)
        bucket = groups.get(key)
        if bucket is None:
            bucket = {
                "supplier": supplier_name,
                "supplier_id": supplier_id,
                "total_ordered": 0.0,
                "po_count": 0,
            }
            groups[key] = bucket

        amount = po.get("Ordered")
        if isinstance(amount, (int, float)):
            bucket["total_ordered"] += amount
        bucket["po_count"] += 1

    total_suppliers = len(groups)

    # Rank: value descending, then supplier name ascending (deterministic
    # tiebreaker).
    ranked = sorted(
        groups.values(),
        key=lambda r: (-r["total_ordered"], r["supplier"]),
    )

    rows = ranked[:top_n]
    return rows, total_suppliers


async def aggregate_purchase_orders_by_supplier(
    client: FusionClient,
    status: str | None = None,
    top_n: int = 10,
    report_progress=None,
) -> dict:
    """Rank suppliers by total committed PO value.

    Args:
        status: Optional StatusCode to restrict to, e.g. "OPEN". Sent to
            Fusion as the server clause, so it bounds the fetch. When
            omitted, every PO is aggregated (subject to the page cap).
        top_n: Number of suppliers to return (default 10).

    Returns:
        A dict with shape "supplier_po_value_ranking":
          {
            shape: "supplier_po_value_ranking",
            status,                        # echoed back (may be None)
            total_suppliers: int,          # distinct suppliers before cut
            returned: int,                 # rows actually returned
            truncated: bool,               # True iff we may not have seen
                                           # every matching PO
            rows: [
              {supplier, supplier_id, total_ordered, po_count},
              ...
            ],
          }

        No matching POs -> total_suppliers=0, returned=0, rows=[].
    """
    # StatusCode is queryable server-side on this pod, so a status filter
    # genuinely bounds the fetch (unlike a date, which is not queryable).
    server_clause: str | None = None
    if status:
        server_clause = f"StatusCode='{status}'"

    items, hit_page_cap, total_available = await _fetch_all_pages(
        client,
        server_clause,
        "aggregate_purchase_orders_by_supplier",
        report_progress,
    )

    rows, total_suppliers = _aggregate_rows(items, top_n)

    # Hitting the page cap is the only way this aggregate can be
    # incomplete: the status filter (when given) is applied server-side,
    # so there is no client-side filter that could cut in-range rows.
    truncated = hit_page_cap

    return {
        "shape": _SHAPE,
        "status": status,
        "total_suppliers": total_suppliers,
        "returned": len(rows),
        "truncated": truncated,
        # How many POs MATCHED, as opposed to how many were fetched.
        # Without this the synthesizer can say "the fetch stopped at the
        # cap" but not how much was missed, and the difference between
        # those two sentences is the difference between a footnote and a
        # warning. None when the pod gave no count.
        "total_available": total_available,
        "examined": len(items),
        "rows": rows,
    }


# ─────────────────────────────────────────────────────────────────────
# Tool 2: purchase orders grouped by status
# ─────────────────────────────────────────────────────────────────────

# A distinct grouping (StatusCode) and a distinct measure (count + sum),
# so per the module's rule this is a SEPARATE tool, not a flag on the
# ranking above.
_STATUS_SHAPE = "po_status_breakdown"


def _aggregate_by_status(purchase_orders: list[dict]) -> tuple[list[dict], int, float]:
    """Group POs by StatusCode; count them and sum Ordered per status.

    Pure function — no I/O — so it is unit-testable without a client.

    POs with no StatusCode are grouped under "(unknown)" rather than
    dropped: they are real POs and their value belongs in the total, so
    silently discarding them would understate it. POs with a non-numeric
    or missing Ordered contribute 0 to the sum but still count, keeping
    the count an honest "how many POs we saw".

    Returns:
        (rows, grand_count, grand_total) where rows is one entry per
        status ordered by total value descending, and the grand figures
        are across every status — so the caller can report both the
        breakdown and the whole.
    """
    groups: dict[str, dict] = {}
    grand_count = 0
    grand_total = 0.0

    for po in purchase_orders:
        status = po.get("StatusCode") or "(unknown)"
        bucket = groups.get(status)
        if bucket is None:
            bucket = {"status": status, "po_count": 0, "total_ordered": 0.0}
            groups[status] = bucket

        amount = po.get("Ordered")
        if isinstance(amount, (int, float)):
            bucket["total_ordered"] += amount
            grand_total += amount
        bucket["po_count"] += 1
        grand_count += 1

    # Order by value descending, then status ascending — deterministic.
    rows = sorted(
        groups.values(),
        key=lambda r: (-r["total_ordered"], r["status"]),
    )
    return rows, grand_count, grand_total


async def aggregate_purchase_orders_by_status(
    client: FusionClient,
    top_n: int | None = None,
    report_progress=None,
) -> dict:
    """Break purchase orders down by status: count and value per status.

    Answers "how many purchase orders are there and what are they worth,
    by status".

    NO SERVER CLAUSE. Grouping BY status means we need every status, so
    there is nothing selective to push to q= — this pages the whole PO
    collection. The pod has 15,839 POs (measured 2026-08-04 via
    totalResults; the ~3,362 this docstring claimed until then was wrong
    and was the reason the page cap looked safe). At 500/page that is 32
    requests. That is the honest cost of aggregating a full collection;
    progress is reported per page.

    Args:
        top_n: Unused for status breakdown — statuses are few (OPEN,
            CLOSED, CANCELED, INCOMPLETE...), so every one is returned.
            Accepted only to keep the aggregation tools' call shape
            uniform; passing it changes nothing.

    Returns:
        A dict with shape "po_status_breakdown":
          {
            shape: "po_status_breakdown",
            total_pos: int,            # grand count across all statuses
            total_ordered: float,      # grand sum across all statuses
            truncated: bool,           # True iff the page cap was hit
            rows: [
              {status, po_count, total_ordered},
              ...                      # value descending
            ],
          }

        No POs -> total_pos=0, rows=[].
    """
    items: list[dict] = []
    items, hit_page_cap, total_available = await _fetch_all_pages(
        client, None, "aggregate_purchase_orders_by_status", report_progress
    )

    rows, grand_count, grand_total = _aggregate_by_status(items)

    return {
        "shape": _STATUS_SHAPE,
        "total_pos": grand_count,
        "total_ordered": grand_total,
        "truncated": hit_page_cap,
        "total_available": total_available,
        "examined": len(items),
        "rows": rows,
    }


# ─────────────────────────────────────────────────────────────────────
# Tool 3: open-PO summary (committed spend + count)
# ─────────────────────────────────────────────────────────────────────

# Grouping: none. Measure: sum + count. Distinct from both tools above,
# so per the module's rule it is its own tool rather than a flag on
# aggregate_purchase_orders_by_status. It IS small — that is fine. The
# rule exists to stop tools growing flags that change what they mean.
_OPEN_SUMMARY_SHAPE = "open_po_summary"


def _summarize(purchase_orders: list[dict]) -> tuple[int, float, int]:
    """Count POs, sum Ordered, and count distinct suppliers.

    Pure function — no I/O — so it is unit-testable without a client.

    A PO with a non-numeric or missing Ordered contributes 0 to the sum
    but still counts, keeping the count an honest "how many POs we saw".

    Returns:
        (po_count, total_ordered, supplier_count)
    """
    po_count = 0
    total_ordered = 0.0
    suppliers: set = set()

    for po in purchase_orders:
        amount = po.get("Ordered")
        if isinstance(amount, (int, float)):
            total_ordered += amount
        po_count += 1
        sid = po.get("SupplierId")
        if sid is not None:
            suppliers.add(sid)

    return po_count, total_ordered, len(suppliers)


async def summarize_open_purchase_orders(
    client: FusionClient,
    report_progress=None,
) -> dict:
    """Committed spend and open-PO count.

    Answers "how much have we committed and across how many open POs".

    Open-only by identity, not by parameter: this tool is about the open
    commitment. A summary of some other status is a different question —
    use aggregate_purchase_orders_by_status for the full breakdown.

    StatusCode is queryable server-side on this pod, so the fetch is
    bounded at the server (~201 open POs, 2 pages) rather than scanning
    the whole collection.

    Returns:
        A dict with shape "open_po_summary":
          {
            shape: "open_po_summary",
            po_count: int,           # open POs seen
            total_ordered: float,    # committed value (excl. tax)
            supplier_count: int,     # distinct suppliers with an open PO
            truncated: bool,         # True iff the page cap was hit
          }

        No open POs -> po_count=0, total_ordered=0.0.
    """
    server_clause = "StatusCode='OPEN'"

    items, hit_page_cap, total_available = await _fetch_all_pages(
        client, server_clause, "summarize_open_purchase_orders", report_progress
    )

    po_count, total_ordered, supplier_count = _summarize(items)

    return {
        "shape": _OPEN_SUMMARY_SHAPE,
        "po_count": po_count,
        "total_ordered": total_ordered,
        "supplier_count": supplier_count,
        "truncated": hit_page_cap,
        "total_available": total_available,
        "examined": len(items),
    }
