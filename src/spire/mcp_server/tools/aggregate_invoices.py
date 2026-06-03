"""Invoice aggregation tool — spend ranked by supplier.

Plain async function — not coupled to FastMCP. Registration happens
in spire.mcp_server.server, exactly like search_invoices.

WHAT THIS IS
A *specific, bounded* aggregation tool (feature 7). It groups invoices
by supplier, sums InvoiceAmount, ranks suppliers by total spend
descending, and returns the top_n. Grouping (by supplier) and the
measure (sum of InvoiceAmount) are FIXED BY IDENTITY — they are not
parameters. A different grouping or measure is a different tool, never
a flag on this one. This is the line that keeps the aggregation layer a
set of bounded tools rather than a generic engine.

The LLM never does the arithmetic. This Python tool does. The tool
returns a small structured result; the synthesizer phrases it.

RELATIONSHIP TO search_invoices
Same underlying data (the Fusion /invoices resource), same fetch
discipline (push the most selective clause to q=, cap the fetch),
different operation: search_invoices returns rows, this returns a
ranking computed over rows.

COMPOSITE FILTER / DATE NOTE (inherited from search_invoices)
Fusion REST's q= on /invoices does not reliably AND-combine clauses on
this pod. We send the date LOWER bound (InvoiceDate >= date_from) as the
single server clause and apply the UPPER bound (date_to, exclusive)
client-side. date_from is therefore the selective server clause; if a
caller passes only date_to, we cannot bound the fetch at the server and
fall back to capping at OVERFETCH_LIMIT (and report the result as
truncated, since we can't prove we saw every matching invoice).

RANGE SEMANTICS
- date_from: inclusive lower bound (InvoiceDate >= date_from). Sent to
  the server.
- date_to: exclusive upper bound (InvoiceDate < date_to). Client-side.
  For a calendar quarter Q1 2026: date_from="2026-01-01",
  date_to="2026-04-01".

DETERMINISM
Suppliers are ranked by total_spend descending, then supplier name
ascending as a tiebreaker, so "the Nth supplier" is the same supplier
on every run and the top_n cut is deterministic rather than arbitrary.

EMPTY RESULT
Zero matching invoices returns a well-formed empty ranking
(total_suppliers=0, returned=0, rows=[]), never an error. The
synthesizer phrases "no invoices in that range" from that shape.
"""

from __future__ import annotations

import sys

from spire.fusion.client import FusionClient


INVOICES_PATH = "/fscmRestApi/resources/11.13.18.05/invoices"

# Page size per fetch. The pod's practical max before things slow is ~200
# (see the endpoints reference), so we page at 200 rather than grabbing
# one big page.
_PAGE_SIZE = 200

# Max pages to fetch before stopping. Bounds the work on very large
# ranges: at _PAGE_SIZE=200, 50 pages = 10,000 invoices. If a range has
# more matching invoices than this, aggregation runs over the first
# MAX_PAGES pages and the result is flagged truncated (sums are then
# lower bounds). Tunable: raise to cover larger ranges at the cost of
# more sequential calls.
MAX_PAGES = 50

# Convenience: the total invoice ceiling implied by the page cap.
OVERFETCH_LIMIT = _PAGE_SIZE * MAX_PAGES

# Fields we need off each invoice to aggregate. Deliberately minimal:
# the supplier to group by, the amount to sum, the date to range-filter.
_PROJECTED_FIELDS = [
    "Supplier",
    "SupplierNumber",
    "InvoiceAmount",
    "InvoiceDate",
]

# The shape tag the synthesizer branches on (parallel to feature 5's
# per-entity schema selection). Identifies this ranking's structure.
_SHAPE = "supplier_spend_ranking"


def _aggregate_rows(
    invoices: list[dict], top_n: int
) -> tuple[list[dict], int]:
    """Group invoices by supplier, sum spend, rank, and cut to top_n.

    Pure function — no I/O — so it is unit-testable without a client.

    Grouping key is the supplier. We key on (SupplierNumber, Supplier):
    SupplierNumber is the stable identifier, Supplier is the display
    name. Invoices missing both are skipped (they cannot be attributed
    to a supplier). Invoices with a non-numeric or missing InvoiceAmount
    contribute 0 to the sum but still count toward invoice_count, so the
    count stays an honest "how many invoices we saw for this supplier".

    Returns:
        (rows, total_suppliers) where rows is the top_n ranking and
        total_suppliers is the number of DISTINCT suppliers seen before
        the cut (so the caller can report "top N of M").
    """
    # supplier_key -> {supplier, supplier_number, total_spend, invoice_count}
    groups: dict[tuple[str, str], dict] = {}

    for inv in invoices:
        supplier_number = inv.get("SupplierNumber") or ""
        supplier_name = inv.get("Supplier") or ""
        if not supplier_number and not supplier_name:
            # Cannot attribute this invoice to any supplier; skip it.
            continue

        key = (supplier_number, supplier_name)
        bucket = groups.get(key)
        if bucket is None:
            bucket = {
                "supplier": supplier_name,
                "supplier_number": supplier_number,
                "total_spend": 0.0,
                "invoice_count": 0,
            }
            groups[key] = bucket

        amount = inv.get("InvoiceAmount")
        if isinstance(amount, (int, float)):
            bucket["total_spend"] += amount
        bucket["invoice_count"] += 1

    total_suppliers = len(groups)

    # Rank: spend descending, then supplier name ascending (deterministic
    # tiebreaker). Sorting by (-spend, name) gives exactly that ordering.
    ranked = sorted(
        groups.values(),
        key=lambda r: (-r["total_spend"], r["supplier"]),
    )

    rows = ranked[:top_n]
    return rows, total_suppliers


async def _fetch_total_for_clause(
    client: FusionClient, server_clause: str | None
) -> int | None:
    """Cheaply ask Fusion how many records match the server clause.

    Mirrors search_invoices._fetch_total_for_clause: limit=1 +
    totalResults=true for minimum bandwidth. Returns None if the
    response doesn't carry totalResults.
    """
    params: dict[str, str | int] = {
        "limit": 1,
        "totalResults": "true",
        "onlyData": "true",
    }
    if server_clause:
        params["q"] = server_clause
    response = await client.get(INVOICES_PATH, params=params)
    total = response.get("totalResults")
    return total if isinstance(total, int) else None


async def aggregate_invoices_by_supplier(
    client: FusionClient,
    date_from: str | None = None,
    date_to: str | None = None,
    top_n: int = 10,
    report_progress=None,
) -> dict:
    """Rank suppliers by total invoice spend over a date range.

    Args:
        date_from: ISO date "YYYY-MM-DD". Inclusive lower bound
            (InvoiceDate >= date_from). Sent to Fusion as the server
            clause, so it bounds the fetch.
        date_to: ISO date "YYYY-MM-DD". Exclusive upper bound
            (InvoiceDate < date_to). Applied client-side. Passing only
            date_to cannot bound the server fetch — see module docstring.
        top_n: Number of suppliers to return (default 10). The result
            holds at most this many rows.

    Returns:
        A dict with shape "supplier_spend_ranking":
          {
            shape: "supplier_spend_ranking",
            date_from, date_to,            # echoed back (may be None)
            total_suppliers: int,          # distinct suppliers before cut
            returned: int,                 # rows actually returned
            truncated: bool,               # True iff we may not have seen
                                           # every in-range invoice
            rows: [
              {supplier, supplier_number, total_spend, invoice_count},
              ...
            ],
          }

        Empty range -> total_suppliers=0, returned=0, rows=[].
    """
    # Date lower bound is the selective server clause. The upper bound is
    # client-side only (mirrors search_invoices, which never sends the
    # upper bound to q=).
    server_clause: str | None = None
    if date_from:
        server_clause = f"InvoiceDate >= '{date_from}'"

    # Page through matching invoices. Aggregation needs every in-range
    # invoice for correct sums, so we walk pages until the pod says there
    # are no more (hasMore=false) or we hit MAX_PAGES. The page cap bounds
    # the work on very large ranges; hitting it sets truncated=True.
    items: list[dict] = []
    hit_page_cap = False
    for page in range(MAX_PAGES):
        params: dict[str, str | int] = {
            "limit": _PAGE_SIZE,
            "offset": page * _PAGE_SIZE,
        }
        if server_clause:
            params["q"] = server_clause

        response = await client.get(INVOICES_PATH, params=params)
        page_items = response.get("items", [])
        items.extend(page_items)

        # Progress: report to the caller via the callback when one is
        # provided (client sees it mid-call), and always echo to stderr
        # as a server-side liveness fallback.
        msg = (
            f"page {page + 1}: +{len(page_items)} (total {len(items)})"
        )
        print(
            f"[aggregate_invoices_by_supplier] {msg}",
            file=sys.stderr,
            flush=True,
        )
        if report_progress is not None:
            # progress = pages done; total unknown until the pod stops,
            # so report the running page count without a fixed total.
            await report_progress(page + 1, None, msg)

        # Stop when the pod reports no further pages. Fall back to a short
        # page as the end signal if hasMore is absent.
        has_more = response.get("hasMore")
        if has_more is False or (has_more is None and len(page_items) < _PAGE_SIZE):
            break
    else:
        # Loop exhausted MAX_PAGES without the pod signalling the end —
        # there may be more matching invoices than we fetched.
        hit_page_cap = True

    # Apply the client-side upper bound (and, defensively, the lower
    # bound too — cheap and keeps the math correct even if the server
    # clause was dropped).
    def in_range(item: dict) -> bool:
        d = item.get("InvoiceDate") or ""
        if date_from and d < date_from:
            return False
        if date_to and d >= date_to:
            return False
        return True

    in_range_items = [it for it in items if in_range(it)]
    projected = [
        {k: it.get(k) for k in _PROJECTED_FIELDS} for it in in_range_items
    ]

    rows, total_suppliers = _aggregate_rows(projected, top_n)

    # ---- Truncation ----
    # Two ways the aggregate can be incomplete:
    #  1. We hit the page cap (there may be more matching the server
    #     clause than MAX_PAGES * _PAGE_SIZE).
    #  2. A client-side upper bound (date_to) without a server lower bound
    #     means we couldn't bound the fetch at the server at all, so the
    #     page cap may have cut off in-range rows.
    # In either case the sums are lower bounds. Otherwise the pod returned
    # every matching invoice and the aggregate is exact.
    truncated = hit_page_cap or (date_to is not None and server_clause is None)

    return {
        "shape": _SHAPE,
        "date_from": date_from,
        "date_to": date_to,
        "total_suppliers": total_suppliers,
        "returned": len(rows),
        "truncated": truncated,
        "rows": rows,
    }
