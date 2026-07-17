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

# Page size per fetch. The endpoints reference documents ~200 as the
# pod's practical max before requests get slow, and a 500-row page does
# time out on a loaded pod. Page at 200 rather than grabbing one big
# page. (Note: aggregate_invoices sets 500 while its comment claims 200
# — a discrepancy worth reconciling separately.)
_PAGE_SIZE = 200

# Max pages before stopping. Bounds the work; hitting it flags the
# result truncated (sums become lower bounds). At 200/page, 50 pages =
# 10,000 POs.
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

        msg = f"page {page + 1}: +{len(page_items)} (total {len(items)})"
        print(
            f"[aggregate_purchase_orders_by_supplier] {msg}",
            file=sys.stderr,
            flush=True,
        )
        if report_progress is not None:
            await report_progress(page + 1, None, msg)

        has_more = response.get("hasMore")
        if has_more is False or (
            has_more is None and len(page_items) < _PAGE_SIZE
        ):
            break
    else:
        # Exhausted MAX_PAGES without the pod signalling the end — there
        # may be more matching POs than we fetched.
        hit_page_cap = True

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
        "rows": rows,
    }
