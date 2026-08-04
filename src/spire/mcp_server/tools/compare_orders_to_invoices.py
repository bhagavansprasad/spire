"""Invoiced-vs-ordered comparison — the PO/invoice join.

Plain async functions — not coupled to FastMCP. Registration happens in
spire.mcp_server.server.

WHAT THIS IS
Three BOUNDED comparison tools. Each fetches purchase orders and invoices,
matches them on PurchaseOrderNumber, and reports what was ordered against
what was invoiced. Following the aggregation layer's rule, the scope is
fixed by identity — one PO, one supplier, or the top-N suppliers by PO
value — never a flag.

WHY THERE IS NO "ACROSS EVERYTHING" VERSION
The pod has 3,362 POs but 53,260 invoices. At 200/page that is 267 pages
of invoices — far past any sane page cap. A truncated ranking merely
understates; a truncated COMPARISON lies: with only a fraction of the
invoices, every PO looks under-invoiced. So an unbounded invoiced-vs-
ordered question has no honest answer here and is not offered. Every tool
below bounds BOTH sides at the server, so both sides are exact.

THE JOIN KEY
PurchaseOrderNumber — a STRING on the invoice header (e.g. "162034"), not
POHeaderId. This is the same string-vs-numeric asymmetry that runs through
the whole pod: invoices reference suppliers by SupplierNumber, POs by
SupplierId. It bites hardest here, because a supplier-scoped comparison
needs BOTH supplier identifiers to filter the two sources — which is why
the supplier-scoped tools resolve the supplier first.

WHY THE TOP-N TOOL LOOKS UP A NUMBER PER SUPPLIER
aggregate_purchase_orders_by_supplier ranks suppliers by PO value and
returns supplier_id on each row — but NOT supplier_number, because POs
carry no SupplierNumber (verified live: SupplierNumber in ?fields= on
/purchaseOrders is HTTP 400). Invoices are filtered by SupplierNumber, so
the top-N tool resolves each ranked supplier's number from its id (one
cheap /suppliers lookup per supplier) before it can compare. The name-
based tool and the top-N tool therefore both converge on the same core:
_compare_resolved_supplier, which takes id + number already resolved.

WHAT "INVOICED > ORDERED" MEANS
Nothing here treats an over-invoice as an error. PO 162034 is 758.00
ordered against 830.01 invoiced, and that is real data. Tax, freight and
price variances all legitimately push an invoice above the order line.
The tools report the numbers and the difference; judging them is the
reader's job, not this code's. Concentration risk (which supplier we
lean on) is likewise the synthesizer's phrasing of these numbers, not a
figure this code computes.
"""

from __future__ import annotations

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.pagination import page_all
from spire.mcp_server.tools.aggregate_purchase_orders import (
    aggregate_purchase_orders_by_supplier,
)


PURCHASE_ORDERS_PATH = "/fscmRestApi/resources/11.13.18.05/purchaseOrders"
INVOICES_PATH = "/fscmRestApi/resources/11.13.18.05/invoices"
SUPPLIERS_PATH = "/fscmRestApi/resources/11.13.18.05/suppliers"

# The reference documents ~200 as the pod's practical page size.
_PAGE_SIZE = 200

# Bounds the work. Both sides are server-filtered to one PO or one
# supplier, so this is a safety net rather than the usual limit: Lee
# Supplies, the biggest supplier here, is 203 POs and 1,379 invoices —
# 2 and 7 pages. Hitting the cap flags the result truncated.
MAX_PAGES = 50

# How many PO rows each per-supplier comparison returns. Separate from the
# top-N tool's own top_n (the number of SUPPLIERS). The totals always
# cover ALL the supplier's POs; this only caps the row detail shown.
_INNER_PO_ROWS = 5

_PO_FIELDS = ["POHeaderId", "OrderNumber", "Supplier", "SupplierId",
              "Ordered", "StatusCode"]
_INVOICE_FIELDS = ["InvoiceId", "InvoiceNumber", "Supplier",
                   "SupplierNumber", "PurchaseOrderNumber", "InvoiceAmount"]

_PO_SHAPE = "po_invoiced_vs_ordered"
_SUPPLIER_SHAPE = "supplier_invoiced_vs_ordered"
_TOP_SUPPLIERS_SHAPE = "top_suppliers_invoiced_vs_ordered"


# Paging lives in tools/pagination.py — page_all. This module had its
# own _page_all, and so did po_lifecycle, and so did
# aggregate_purchase_orders: three private helpers with the same job.
# The shared one took ITS signature from this file and po_lifecycle,
# which had arrived at path/fields/clause/label independently — two
# implementations agreeing was the argument for that shape over the
# hardcoded one.
#
# _PAGE_SIZE stays at 200 here and is passed in. Raising it to 500,
# as the aggregation tools now use, is a change to how this tool
# behaves and belongs in its own commit — an extraction that also
# retunes the thing it extracts cannot be verified as a no-op.


def _sum_invoice_amounts(invoices: list[dict]) -> float:
    """Sum InvoiceAmount, skipping non-numeric values.

    Pure function — unit-testable without a client."""
    total = 0.0
    for inv in invoices:
        amount = inv.get("InvoiceAmount")
        if isinstance(amount, (int, float)):
            total += amount
    return total


def _compare_by_po(
    purchase_orders: list[dict], invoices: list[dict]
) -> tuple[list[dict], float, float]:
    """Match invoices to POs on PurchaseOrderNumber / OrderNumber.

    Pure function — no I/O — so the join logic is unit-testable without a
    pod. This is the arithmetic the synthesizer's guard cannot check, so
    it is where a bug would be invisible downstream.

    A PO with no invoices appears with invoiced=0.0 and invoice_count=0 —
    that is a real and interesting answer ("ordered but never billed"),
    not an absence to be filtered out.

    Invoices whose PurchaseOrderNumber matches no fetched PO are counted
    separately by the caller if it cares; they are not silently dropped
    into some PO's total.

    Returns:
        (rows, total_ordered, total_invoiced) with rows ordered by the
        absolute difference descending — the biggest mismatches first,
        since those are what the question is about.
    """
    by_number: dict[str, list[dict]] = {}
    for inv in invoices:
        num = inv.get("PurchaseOrderNumber")
        if num is None:
            continue
        by_number.setdefault(str(num), []).append(inv)

    rows: list[dict] = []
    total_ordered = 0.0
    total_invoiced = 0.0

    for po in purchase_orders:
        order_number = po.get("OrderNumber")
        ordered = po.get("Ordered")
        ordered_val = ordered if isinstance(ordered, (int, float)) else 0.0

        matched = by_number.get(str(order_number), [])
        invoiced_val = _sum_invoice_amounts(matched)

        total_ordered += ordered_val
        total_invoiced += invoiced_val

        rows.append({
            "order_number": order_number,
            "po_header_id": po.get("POHeaderId"),
            "status": po.get("StatusCode"),
            "ordered": ordered_val,
            "invoiced": invoiced_val,
            "difference": round(invoiced_val - ordered_val, 2),
            "invoice_count": len(matched),
        })

    rows.sort(key=lambda r: (-abs(r["difference"]), str(r["order_number"])))
    return rows, total_ordered, total_invoiced


async def compare_purchase_order_to_invoices(
    client: FusionClient,
    po_number: str,
    report_progress=None,
) -> dict:
    """Compare what one PO ordered against what was invoiced against it.

    Both sides are exact: the PO is a single record, and its invoices are
    server-filtered by PurchaseOrderNumber.

    Args:
        po_number: The PO's OrderNumber (e.g. "162034") — the number
            printed on the order, which is also the key invoices carry.
            NOT POHeaderId.

    Returns:
        A "po_invoiced_vs_ordered" dict: order_number, po_header_id,
        supplier, status, ordered, invoiced, difference, invoice_count,
        and the matching invoices. found=False when no such PO exists.
    """
    po_params = {
        "onlyData": "true",
        "q": f"OrderNumber='{po_number}'",
        "fields": ",".join(_PO_FIELDS),
        "limit": 1,
    }
    po_response = await client.get(PURCHASE_ORDERS_PATH, params=po_params)
    po_items = po_response.get("items", [])
    if not po_items:
        return {
            "shape": _PO_SHAPE,
            "found": False,
            "order_number": po_number,
        }
    po = po_items[0]

    invoices, hit_cap, _ = await page_all(
        client,
        INVOICES_PATH,
        "compare_orders_to_invoices: invoices",
        server_clause=f"PurchaseOrderNumber='{po_number}'",
        fields=_INVOICE_FIELDS,
        page_size=_PAGE_SIZE,
        max_pages=MAX_PAGES,
        report_progress=report_progress,
    )

    ordered = po.get("Ordered")
    ordered_val = ordered if isinstance(ordered, (int, float)) else 0.0
    invoiced_val = _sum_invoice_amounts(invoices)

    return {
        "shape": _PO_SHAPE,
        "found": True,
        "order_number": po.get("OrderNumber"),
        "po_header_id": po.get("POHeaderId"),
        "supplier": po.get("Supplier"),
        "status": po.get("StatusCode"),
        "ordered": ordered_val,
        "invoiced": invoiced_val,
        "difference": round(invoiced_val - ordered_val, 2),
        "invoice_count": len(invoices),
        "truncated": hit_cap,
        "invoices": [
            {
                "invoice_number": i.get("InvoiceNumber"),
                "invoice_id": i.get("InvoiceId"),
                "amount": i.get("InvoiceAmount"),
            }
            for i in invoices
        ],
    }


async def _compare_resolved_supplier(
    client: FusionClient,
    supplier_id,
    supplier_number,
    supplier_name,
    top_n: int = _INNER_PO_ROWS,
    report_progress=None,
) -> dict:
    """Compare ordered vs invoiced for a supplier whose ids are already known.

    The shared core of both supplier-scoped tools. It takes the supplier
    ALREADY RESOLVED — SupplierId (numeric, for POs), SupplierNumber
    (string, for invoices), and the display name — and does the two paged
    fetches, the join, and the totals. No name resolution here: the
    caller has done it (by name lookup, or from a value ranking).

    Both sides are server-filtered to this one supplier, so both totals
    are exact unless a page cap is hit (then truncated=True).

    Args:
        supplier_id: SupplierId (numeric). Filters the PO side.
        supplier_number: SupplierNumber (string). Filters the invoice side.
        supplier_name: Display name, echoed in the result.
        top_n: How many PO rows to return, biggest absolute difference
            first. The totals always cover ALL the supplier's POs.

    Returns:
        A "supplier_invoiced_vs_ordered" dict: supplier, supplier_id,
        supplier_number, po_count, invoice_count, total_ordered,
        total_invoiced, total_difference, unmatched_invoice_count,
        returned, truncated, and the top_n rows.
    """
    purchase_orders, po_cap, _ = await page_all(
        client,
        PURCHASE_ORDERS_PATH,
        "compare_orders_to_invoices: POs",
        server_clause=f"SupplierId={supplier_id}",
        fields=_PO_FIELDS,
        page_size=_PAGE_SIZE,
        max_pages=MAX_PAGES,
        report_progress=report_progress,
    )
    invoices, inv_cap, _ = await page_all(
        client,
        INVOICES_PATH,
        "compare_orders_to_invoices: invoices",
        server_clause=f"SupplierNumber='{supplier_number}'",
        fields=_INVOICE_FIELDS,
        page_size=_PAGE_SIZE,
        max_pages=MAX_PAGES,
        report_progress=report_progress,
    )

    rows, total_ordered, total_invoiced = _compare_by_po(
        purchase_orders, invoices
    )

    # Invoices for this supplier that reference no PO we fetched — either
    # non-PO invoices (the pod has many) or POs outside our window.
    # Reported, not hidden: they are why the two totals may not reconcile.
    po_numbers = {str(po.get("OrderNumber")) for po in purchase_orders}
    unmatched = [
        i for i in invoices
        if str(i.get("PurchaseOrderNumber")) not in po_numbers
    ]

    return {
        "shape": _SUPPLIER_SHAPE,
        "found": True,
        "ambiguous": False,
        "supplier": supplier_name,
        "supplier_id": supplier_id,
        "supplier_number": supplier_number,
        "po_count": len(purchase_orders),
        "invoice_count": len(invoices),
        "total_ordered": total_ordered,
        "total_invoiced": total_invoiced,
        "total_difference": round(total_invoiced - total_ordered, 2),
        "unmatched_invoice_count": len(unmatched),
        "returned": min(top_n, len(rows)),
        "truncated": po_cap or inv_cap,
        "rows": rows[:top_n],
    }


async def compare_supplier_orders_to_invoices(
    client: FusionClient,
    supplier_name: str,
    top_n: int = 10,
    report_progress=None,
) -> dict:
    """Compare ordered against invoiced across one supplier's POs.

    Resolves the supplier BY NAME first, because the two sources use
    DIFFERENT supplier identifiers: POs filter by SupplierId (numeric),
    invoices by SupplierNumber (string). One cheap lookup gets both, so
    the caller only needs a name. Resolution done, it delegates to
    _compare_resolved_supplier.

    Args:
        supplier_name: Substring of the supplier's name (e.g. "Lee
            Supplies"). Must match exactly one supplier.
        top_n: How many PO rows to return, ordered by the biggest
            absolute difference first. The totals always cover ALL the
            supplier's POs, not just the returned rows.

    Returns:
        A "supplier_invoiced_vs_ordered" dict (see
        _compare_resolved_supplier). found=False when the name matches no
        supplier; ambiguous=True when it matches several.
    """
    sup_params = {
        "onlyData": "true",
        "q": f"Supplier LIKE '%{supplier_name}%'",
        "fields": "SupplierId,SupplierNumber,Supplier",
        "limit": 5,
    }
    sup_response = await client.get(SUPPLIERS_PATH, params=sup_params)
    suppliers = sup_response.get("items", [])
    if not suppliers:
        return {
            "shape": _SUPPLIER_SHAPE,
            "found": False,
            "supplier_name": supplier_name,
        }
    if len(suppliers) > 1:
        # Refuse rather than pick one: comparing the wrong supplier's
        # books is worse than asking again.
        return {
            "shape": _SUPPLIER_SHAPE,
            "found": True,
            "ambiguous": True,
            "supplier_name": supplier_name,
            "candidates": [s.get("Supplier") for s in suppliers],
        }

    supplier = suppliers[0]
    return await _compare_resolved_supplier(
        client,
        supplier_id=supplier.get("SupplierId"),
        supplier_number=supplier.get("SupplierNumber"),
        supplier_name=supplier.get("Supplier"),
        top_n=top_n,
        report_progress=report_progress,
    )


async def _resolve_supplier_number(client: FusionClient, supplier_id) -> str | None:
    """Look up a supplier's SupplierNumber from its SupplierId.

    POs carry SupplierId but no SupplierNumber (verified: SupplierNumber
    in ?fields= on /purchaseOrders is HTTP 400), while invoices are
    filtered by SupplierNumber — so a value ranking (which is PO-derived,
    id-only) must resolve the number before it can compare. One cheap
    single-clause /suppliers lookup.

    Returns the number, or None if the id resolves to no supplier (which
    the caller treats as "skip this ranked supplier", not an error).
    """
    params = {
        "onlyData": "true",
        "q": f"SupplierId={supplier_id}",
        "fields": "SupplierId,SupplierNumber,Supplier",
        "limit": 1,
    }
    response = await client.get(SUPPLIERS_PATH, params=params)
    items = response.get("items", [])
    if not items:
        return None
    return items[0].get("SupplierNumber")


async def compare_top_suppliers_orders_to_invoices(
    client: FusionClient,
    top_n: int = 5,
    status: str | None = None,
    report_progress=None,
) -> dict:
    """Compare ordered vs invoiced for the top-N suppliers by PO value.

    The composed tool behind "how does invoiced compare to ordered for
    our biggest suppliers" and concentration-risk questions. Its identity
    is fixed — the top-N suppliers by committed PO value — so it is a
    bounded tool, not a generic engine: "top-N by PO value" is as much an
    identity as "one PO" or "one supplier".

    HOW IT COMPOSES (no new plan machinery — Shape B)
      1. aggregate_purchase_orders_by_supplier ranks suppliers by PO value
         and returns supplier_id per row (POs have no SupplierNumber).
      2. For each ranked supplier: resolve its SupplierNumber from its id
         (one /suppliers lookup), then compare via the shared core.
    Each comparison bounds both sides at the server, so every supplier's
    totals are exact; the tool's truncated flag is True if the ranking OR
    any comparison hit a page cap.

    It does NOT compute a concentration figure. It reports each supplier's
    ordered/invoiced/difference; "we lean too hard on supplier X" is the
    synthesizer's phrasing of these numbers, not arithmetic this tool
    bakes in — the same discipline the aggregation layer follows.

    Args:
        top_n: How many suppliers to compare (default 5). Ranked by
            committed PO value descending, deterministic.
        status: Optional StatusCode (e.g. "OPEN") passed to the ranking
            to bound which POs count toward "biggest supplier". Omit to
            rank across all POs.

    Returns:
        A dict with shape "top_suppliers_invoiced_vs_ordered":
          {
            shape: "top_suppliers_invoiced_vs_ordered",
            status,               # echoed (may be None)
            total_suppliers: int, # distinct suppliers the ranking saw
            returned: int,        # comparisons actually run
            truncated: bool,      # ranking or any comparison capped
            suppliers: [
              <supplier_invoiced_vs_ordered dict>,
              ...                 # ranking order (biggest PO value first)
            ],
          }

        No POs -> total_suppliers=0, returned=0, suppliers=[].
    """
    ranking = await aggregate_purchase_orders_by_supplier(
        client,
        status=status,
        top_n=top_n,
        report_progress=report_progress,
    )

    ranked_rows = ranking.get("rows", [])
    truncated = bool(ranking.get("truncated"))

    comparisons: list[dict] = []
    for row in ranked_rows:
        supplier_id = row.get("supplier_id")
        supplier_name = row.get("supplier")
        if supplier_id is None:
            # No id to resolve a number from; cannot compare. Skip.
            continue

        supplier_number = await _resolve_supplier_number(client, supplier_id)
        if supplier_number is None:
            # Ranked from POs but not found in /suppliers — skip rather
            # than crash the whole tool. Rare, but real data is messy.
            continue

        comparison = await _compare_resolved_supplier(
            client,
            supplier_id=supplier_id,
            supplier_number=supplier_number,
            supplier_name=supplier_name,
            top_n=_INNER_PO_ROWS,
            report_progress=report_progress,
        )
        truncated = truncated or bool(comparison.get("truncated"))
        comparisons.append(comparison)

    return {
        "shape": _TOP_SUPPLIERS_SHAPE,
        "status": status,
        "total_suppliers": ranking.get("total_suppliers", 0),
        "returned": len(comparisons),
        "truncated": truncated,
        "suppliers": comparisons,
    }
