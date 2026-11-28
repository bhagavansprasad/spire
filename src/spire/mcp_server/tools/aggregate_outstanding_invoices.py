"""Invoice aggregation tool — outstanding (unpaid) amount by supplier.

Plain async function — not coupled to FastMCP. Registration happens in
spire.mcp_server.server, exactly like aggregate_invoices_by_supplier.

WHY THIS IS A SEPARATE TOOL AND NOT A FLAG
The aggregation layer's rule: grouping AND measure are fixed by identity. A
different measure is a different tool. aggregate_invoices_by_supplier sums
INVOICE_AMOUNT — what was billed. This sums what is still OWED. They answer
different questions over the same rows, and conflating them is how prompt 20
came to answer "total spend, all time" to a question about outstanding for the
current month (AP-2 in docs/plan/module-support/AP_COVERAGE_ASSESSMENT.md).
The substitution was silent; a separate tool makes it impossible.

THE MEASURE, AND WHY NOT PaidStatus
outstanding = SUM(MAX(InvoiceAmount - AmountPaid, 0)) over non-cancelled
invoices.

AmountPaid is the only usable paid figure, and it is on the invoice HEADER.
Gating on PaidStatus instead loses partial payments entirely: a partly paid
invoice is not in 'Paid' status, so it would contribute ZERO and a partial
state could never be detected. Measured on dev49 (2026-11-28):

    PaidStatus='Unpaid'        -> 12,739
    PaidStatus='Paid'          -> 40,482
    PaidStatus='Partially paid'-> 0        (none exist on this pod)
    /invoices?fields=InvoiceAmount,AmountPaid  -> both present, real values

There is no 'Partially paid' population today, which is precisely why the
status flag looks adequate — and why the amount is used anyway. The data can
change; the derivation stays correct.

CANCELLED INVOICES ARE EXCLUDED, AND THE EXCLUSION IS REPORTED
A cancelled invoice is not owed. It is also not rare: 725 invoices carry
CanceledFlag=true, and the first page of `PaidStatus='Unpaid'` on this pod is
almost entirely cancelled zero-amount rows. Counting them inflates what
appears owed and makes every "unpaid" list look like garbage — the same
mechanism behind AP-4 on the overdue filter. The count of what was excluded
rides back in the result so the answer can say so rather than quietly
dropping rows.

RANGE SEMANTICS (identical to aggregate_invoices_by_supplier)
- date_from: inclusive lower bound (InvoiceDate >= date_from). Server clause.
- date_to: exclusive upper bound (InvoiceDate < date_to). Client-side.
Fusion's q= does not reliably AND-combine clauses on this pod, so exactly one
clause goes to the server; the rest is applied here.

A PERIOD IS REQUIRED BY THE CALLER, NOT BY THIS TOOL
"for the current month" is the parser's job to turn into date_from/date_to.
The tool accepts None for both and will then scan everything, which is the
honest behaviour for "outstanding, all time" — but a prompt that names a period
and gets an all-time answer is the AP-2 defect, not a tool bug. Both bounds
are echoed back in the result so the answer can state the window it used.

TRUNCATION
Paging stops at MAX_PAGES, so on a large range the sums are LOWER BOUNDS. The
result carries truncated / total_available / examined so the synthesizer can
say so. A total stated over a partial scan without that disclosure would be a
confident wrong answer — the failure shape this codebase has removed before.

DETERMINISM
Ranked by outstanding descending, then supplier name ascending, so "the Nth
supplier" is the same on every run.
"""

from __future__ import annotations

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.pagination import page_all


INVOICES_PATH = "/fscmRestApi/resources/11.13.18.05/invoices"

# Same paging discipline as aggregate_invoices_by_supplier: 500 per page,
# 50 pages, so at most 25,000 invoices are examined per call and a larger
# range is disclosed as truncated rather than silently summed.
_PAGE_SIZE = 500
MAX_PAGES = 50
OVERFETCH_LIMIT = _PAGE_SIZE * MAX_PAGES

# Projected, so the pod sends six fields instead of the whole body. page_all
# supports fields= and this tool needs nothing else.
_PROJECTED_FIELDS = [
    "Supplier",
    "SupplierNumber",
    "InvoiceAmount",
    "AmountPaid",
    "CanceledFlag",
    "InvoiceDate",
]

# The shape tag the synthesizer branches on. Distinct from
# 'supplier_spend_ranking' on purpose: the response carries a different
# measure, and a shared tag would let a spend row be read as an owed one.
_SHAPE = "supplier_outstanding_ranking"


def _money(value: object) -> float:
    """Coerce a pod amount to float; anything non-numeric contributes 0.0."""
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _aggregate_outstanding(
    invoices: list[dict], top_n: int
) -> tuple[list[dict], int, int, int]:
    """Group non-cancelled invoices by supplier, sum what is still owed.

    Pure function — no I/O — so it is unit-testable without a client.

    Grouping key is (SupplierNumber, Supplier): the number is the stable
    identifier, the name is the display label. Invoices carrying neither are
    skipped — they cannot be attributed to a supplier.

    Returns:
        (rows, total_suppliers, cancelled_excluded, invoices_counted)
        rows is the top_n ranking; total_suppliers is the number of DISTINCT
        suppliers before the cut, so the caller can say "top N of M".
    """
    groups: dict[tuple[str, str], dict] = {}
    cancelled_excluded = 0
    invoices_counted = 0

    for inv in invoices:
        if inv.get("CanceledFlag") is True:
            cancelled_excluded += 1
            continue

        supplier_number = inv.get("SupplierNumber") or ""
        supplier_name = inv.get("Supplier") or ""
        if not supplier_number and not supplier_name:
            continue

        invoiced = _money(inv.get("InvoiceAmount"))
        paid = _money(inv.get("AmountPaid"))
        # Never negative: an overpayment is not money still owed.
        outstanding = invoiced - paid
        if outstanding < 0:
            outstanding = 0.0

        invoices_counted += 1

        key = (supplier_number, supplier_name)
        bucket = groups.get(key)
        if bucket is None:
            bucket = {
                "supplier": supplier_name,
                "supplier_number": supplier_number,
                "total_outstanding": 0.0,
                "total_invoiced": 0.0,
                "total_paid": 0.0,
                "invoice_count": 0,
            }
            groups[key] = bucket

        bucket["total_outstanding"] = round(
            bucket["total_outstanding"] + outstanding, 2
        )
        bucket["total_invoiced"] = round(bucket["total_invoiced"] + invoiced, 2)
        bucket["total_paid"] = round(bucket["total_paid"] + paid, 2)
        bucket["invoice_count"] += 1

    total_suppliers = len(groups)

    # Outstanding descending, then supplier name ascending as a deterministic
    # tiebreaker: with thousands of suppliers at 0.00 the tiebreak is
    # load-bearing, not cosmetic.
    ranked = sorted(
        groups.values(),
        key=lambda r: (-r["total_outstanding"], r["supplier"]),
    )

    return ranked[:top_n], total_suppliers, cancelled_excluded, invoices_counted


async def aggregate_outstanding_invoices_by_supplier(
    client: FusionClient,
    date_from: str | None = None,
    date_to: str | None = None,
    top_n: int = 10,
    report_progress=None,
) -> dict:
    """Rank suppliers by total OUTSTANDING (unpaid) invoice amount.

    Args:
        date_from: ISO date "YYYY-MM-DD". Inclusive lower bound on
            InvoiceDate, sent to Fusion as the server clause.
        date_to: ISO date "YYYY-MM-DD". Exclusive upper bound on
            InvoiceDate, applied client-side. Passing only date_to cannot
            bound the server fetch.
        top_n: Number of suppliers to return (default 10).
        report_progress: Optional async progress callback, forwarded to
            page_all so a long scan reports pages.

    Returns:
        A dict with shape "supplier_outstanding_ranking":
          {
            shape: "supplier_outstanding_ranking",
            date_from, date_to,           # echoed; None means all time
            total_suppliers: int,         # distinct suppliers before the cut
            returned: int,
            truncated: bool,              # True iff the scan may be partial
            total_available: int | None,  # pod's count, None when withheld
            examined: int,                # invoices fetched
            invoices_counted: int,        # non-cancelled, attributed invoices
            cancelled_excluded: int,      # cancelled rows left out
            rows: [
              {supplier, supplier_number, total_outstanding,
               total_invoiced, total_paid, invoice_count},
              ...
            ],
          }

        Empty range -> total_suppliers=0, returned=0, rows=[].
    """
    # The lower bound is the selective server clause; the upper bound is
    # client-side. Same split as aggregate_invoices_by_supplier, and for the
    # same measured reason (composite q= does not AND-combine here).
    server_clause: str | None = None
    if date_from:
        server_clause = f"InvoiceDate >= '{date_from}'"

    items, hit_page_cap, total_available = await page_all(
        client,
        INVOICES_PATH,
        "aggregate_outstanding_invoices_by_supplier",
        server_clause=server_clause,
        fields=_PROJECTED_FIELDS,
        page_size=_PAGE_SIZE,
        max_pages=MAX_PAGES,
        report_progress=report_progress,
    )

    def in_range(item: dict) -> bool:
        d = item.get("InvoiceDate") or ""
        if date_from and d < date_from:
            return False
        if date_to and d >= date_to:
            return False
        return True

    in_range_items = [it for it in items if in_range(it)]

    rows, total_suppliers, cancelled_excluded, invoices_counted = (
        _aggregate_outstanding(in_range_items, top_n)
    )

    # Two ways the sums can be incomplete, same as the spend tool: the page
    # cap was hit, or a client-side upper bound was applied without a server
    # lower bound so the fetch was never bounded at the server.
    truncated = hit_page_cap or (date_to is not None and server_clause is None)

    return {
        "shape": _SHAPE,
        "date_from": date_from,
        "date_to": date_to,
        "total_suppliers": total_suppliers,
        "returned": len(rows),
        "truncated": truncated,
        "total_available": total_available,
        "examined": len(items),
        "invoices_counted": invoices_counted,
        "cancelled_excluded": cancelled_excluded,
        "rows": rows,
    }
