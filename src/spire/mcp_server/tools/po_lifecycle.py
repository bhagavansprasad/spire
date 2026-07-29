"""PO lifecycle status — the ordered/received/invoiced/paid reconciliation.

Plain async functions — not coupled to FastMCP. Registration happens in
spire.mcp_server.server.

WHAT THIS IS
One BOUNDED lifecycle tool. It assembles a single purchase order across
three endpoints — header, schedules, invoices — reconciles the four
amounts against each other, and names the stage the order is sitting at
and who owns the next action. Scope is fixed by identity: one PO, always.
This is the Shape C ("status matrix") lifecycle PoC.

WHY RECEIVED IS DERIVED, NOT FETCHED
ReceivedAmount is 0 or null on EVERY schedule row on this pod — verified
across ~4,500 rows on 2026-07-28. The received leg exists only as a
QUANTITY. So the received amount is derived:

    received = Amount * (ReceivedQuantity / Quantity)

This is not a guess. Oracle's own arithmetic agrees: PO 701337 line 1 is
Amount 1116, Quantity 4, ReceivedQuantity 1, BilledQuantity 1 — and the
pod's BilledAmount for that line is 279, exactly 1116 * 1/4. The derived
figure is flagged `received_is_derived: True` in the result so the
synthesizer can say so rather than presenting it as a fetched field.

WHY ORDERED COMES FROM THE HEADER
The header's `Ordered` is Oracle's own total. The sum of schedule Amounts
is computed anyway and compared: a disagreement between the two is a real
defect — either a missed schedule page or a pod inconsistency — and lands
in `notes` rather than being silently resolved in favour of one side.

WHAT "PAID" CAN AND CANNOT SEE
Payment is visible only through /invoices filtered by PurchaseOrderNumber.
A PO can carry BilledAmount on its schedules with NO invoice bearing its
number — PO 701337 does exactly this. That is reported as an unmatched
billing note, not silently treated as unpaid debt. PayOnReceiptFlag is
surfaced when set, since self-billing is a plausible (UNCONFIRMED)
explanation for the gap.

WHAT OVER-INVOICING MEANS
Nothing here treats invoiced > ordered as an error, matching
compare_orders_to_invoices: PO 162034 is 758.00 ordered against 830.01
invoiced, and that is real data. Tax, freight and price variances all
legitimately push an invoice above the order. The numbers and the
difference are reported; judging them is the reader's job.

POD QUIRKS THIS RELIES ON (all curl-verified 2026-07-28)
  - /purchaseOrders          q=OrderNumber='<n>'         filters server-side
  - /purchaseOrderSchedules  q=OrderNumber='<n>'         filters server-side
    (previously only POHeaderId was documented for this resource)
  - /invoices                q=PurchaseOrderNumber='<n>' filters server-side
  - Composite q= clauses fail silently here. Every query below uses a
    SINGLE clause. Never AND them.
"""

from __future__ import annotations

import sys

from spire.fusion.client import FusionClient


PURCHASE_ORDERS_PATH = "/fscmRestApi/resources/11.13.18.05/purchaseOrders"
PURCHASE_ORDER_SCHEDULES_PATH = (
    "/fscmRestApi/resources/11.13.18.05/purchaseOrderSchedules"
)
INVOICES_PATH = "/fscmRestApi/resources/11.13.18.05/invoices"

# The reference documents ~200 as the pod's practical page size.
_PAGE_SIZE = 200

# Bounds the work. Both child fetches are server-filtered to one PO, so
# this is a safety net rather than a real limit: the widest PO seen on
# this pod is 46 schedule lines, well inside one page. Hitting the cap
# flags the result truncated.
MAX_PAGES = 50

# Amount comparisons. Guards float noise from the received derivation
# (a division), not real gaps — 0.01 is below one cent of any currency
# on this pod.
TOLERANCE = 0.01

_PO_FIELDS = [
    "POHeaderId", "OrderNumber", "Status", "StatusCode", "Supplier",
    "SupplierSite", "Buyer", "BuyerDisplayName", "CurrencyCode", "Ordered",
    "PaymentTerms", "ProcurementBU", "PayOnReceiptFlag", "FundsStatus",
]

_SCHEDULE_FIELDS = [
    "POHeaderId", "OrderNumber", "LineNumber", "ScheduleNumber", "Quantity",
    "Amount", "ReceivedQuantity", "ReceivedAmount", "BilledQuantity",
    "BilledAmount", "ScheduleStatus",
]

_INVOICE_FIELDS = [
    "InvoiceId", "InvoiceNumber", "Supplier", "InvoiceAmount",
    "InvoiceCurrency", "PaidStatus", "ApprovalStatus", "PurchaseOrderNumber",
]

_SHAPE = "po_lifecycle_status"


async def _page_all(
    client: FusionClient,
    path: str,
    server_clause: str,
    fields: list[str],
    label: str,
    report_progress=None,
) -> tuple[list[dict], bool]:
    """Page a server-filtered collection to exhaustion or the cap.

    Returns (items, hit_page_cap). The clause is mandatory: this tool
    never scans an unfiltered collection.
    """
    items: list[dict] = []
    for page in range(MAX_PAGES):
        params: dict[str, str | int] = {
            "limit": _PAGE_SIZE,
            "offset": page * _PAGE_SIZE,
            "onlyData": "true",
            "q": server_clause,
            "fields": ",".join(fields),
        }
        response = await client.get(path, params=params)
        page_items = response.get("items", [])
        items.extend(page_items)

        msg = f"{label} page {page + 1}: +{len(page_items)} (total {len(items)})"
        print(f"[po_lifecycle] {msg}", file=sys.stderr, flush=True)
        if report_progress is not None:
            await report_progress(page + 1, None, msg)

        has_more = response.get("hasMore")
        if has_more is False or (
            has_more is None and len(page_items) < _PAGE_SIZE
        ):
            return items, False
    return items, True


def _num(value) -> float:
    """Coerce a possibly-null amount to float.

    BilledAmount is null (not 0) on unbilled schedule rows and
    ReceivedAmount is null on unreceived ones. Both must read as zero, or
    the sums raise instead of reporting an honest 0.00.
    """
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _is_complete(actual: float, expected: float) -> bool:
    """True when actual has reached expected, within tolerance.

    An expected of zero counts as complete: nothing was due. Without this,
    a zero-amount PO would report "not received" forever.
    """
    if expected <= TOLERANCE:
        return True
    return actual >= expected - TOLERANCE


def _summarise_schedules(
    schedules: list[dict],
) -> tuple[float, float, float, list]:
    """Sum ordered / derived-received / invoiced across schedule rows.

    Pure function — no I/O — so the derivation is unit-testable without a
    pod. This is the arithmetic no downstream guard can check, so it is
    where a bug would be invisible.

    Returns:
        (ordered, received, invoiced, undivisible_lines) where
        undivisible_lines are line numbers with received quantity but zero
        ordered quantity — nothing to prorate against, so no amount can be
        derived for them.
    """
    ordered = 0.0
    received = 0.0
    invoiced = 0.0
    undivisible_lines: list = []

    for row in schedules:
        amount = _num(row.get("Amount"))
        quantity = _num(row.get("Quantity"))
        received_quantity = _num(row.get("ReceivedQuantity"))

        ordered += amount
        invoiced += _num(row.get("BilledAmount"))

        if quantity > 0:
            received += amount * (received_quantity / quantity)
        elif received_quantity > 0:
            undivisible_lines.append(row.get("LineNumber"))

    return ordered, received, invoiced, undivisible_lines


def _summarise_invoices(invoices: list[dict]) -> tuple[float, float, int]:
    """Sum paid and total matched-invoice amounts.

    Pure function. Returns (paid, billed_in_ap, unpaid_count). Only
    invoices in Paid status count toward paid; everything matched counts
    toward billed_in_ap.
    """
    paid = 0.0
    billed_in_ap = 0.0
    unpaid_count = 0

    for invoice in invoices:
        amount = _num(invoice.get("InvoiceAmount"))
        billed_in_ap += amount
        if (invoice.get("PaidStatus") or "").strip().lower() == "paid":
            paid += amount
        else:
            unpaid_count += 1

    return paid, billed_in_ap, unpaid_count


def _lifecycle_stage(
    fully_received: bool, fully_invoiced: bool, fully_paid: bool
) -> str:
    """The earliest incomplete leg names the stage the PO sits at."""
    if not fully_received:
        return "Awaiting receipt"
    if not fully_invoiced:
        return "Awaiting invoicing"
    if not fully_paid:
        return "Awaiting payment"
    return "Complete"


def _responsible_team(
    fully_received: bool, fully_invoiced: bool, fully_paid: bool
) -> str:
    """Who owns the next action.

    Derived from the stage, NOT from an approval-chain lookup: holds,
    approvals and the three receiving resources are all unconfirmed or
    failing on this pod. This is ownership by lifecycle position, which is
    honest but shallow — it names the function, not the person.
    """
    if not fully_received:
        return "Supplier / Receiving"
    if not fully_invoiced:
        return "Accounts Payable"
    if not fully_paid:
        return "Payments"
    return "None — no action outstanding"


async def get_purchase_order_lifecycle_status(
    client: FusionClient,
    po_number: str,
    report_progress=None,
) -> dict:
    """Assemble and reconcile one PO's lifecycle across three endpoints.

    Generic over any PO number: nothing about a particular order is baked
    in. Missing legs are reported, not crashed on — a PO with no invoices,
    null BilledAmount, or zero Quantity all produce an honest result.

    Args:
        po_number: The PO's OrderNumber (e.g. "701337") — the number
            printed on the order, which is also the key invoices carry.
            NOT the POHeaderId.

    Returns:
        A "po_lifecycle_status" dict: the header identity block, the four
        amounts (received flagged as derived), the three remainders, the
        three completion booleans, lifecycle_stage, responsible_team,
        counts, and a notes list carrying every gap and inconsistency
        found. found=False when no such PO exists.
    """
    po_number = str(po_number).strip()
    notes: list[str] = []

    po_params = {
        "onlyData": "true",
        "q": f"OrderNumber='{po_number}'",
        "fields": ",".join(_PO_FIELDS),
        "limit": 2,  # 2, not 1: lets us detect a duplicate rather than hide it
    }
    po_response = await client.get(PURCHASE_ORDERS_PATH, params=po_params)
    po_items = po_response.get("items", [])

    if not po_items:
        return {
            "shape": _SHAPE,
            "found": False,
            "order_number": po_number,
            "notes": [
                f"no purchase order found with OrderNumber '{po_number}'"
            ],
        }

    if len(po_items) > 1:
        notes.append(
            "more than one header returned for this order number; "
            "using the first"
        )

    po = po_items[0]

    schedules, schedules_hit_cap = await _page_all(
        client, PURCHASE_ORDER_SCHEDULES_PATH, f"OrderNumber='{po_number}'",
        _SCHEDULE_FIELDS, "schedules", report_progress,
    )
    if not schedules:
        notes.append("no schedules returned for this PO")

    invoices, invoices_hit_cap = await _page_all(
        client, INVOICES_PATH, f"PurchaseOrderNumber='{po_number}'",
        _INVOICE_FIELDS, "invoices", report_progress,
    )

    schedule_ordered, received, invoiced, undivisible = _summarise_schedules(
        schedules
    )
    paid, billed_in_ap, unpaid_count = _summarise_invoices(invoices)

    if undivisible:
        notes.append(
            "received amount could not be derived for line(s) "
            f"{undivisible}: ordered quantity is zero"
        )
    if unpaid_count:
        notes.append(f"{unpaid_count} matched invoice(s) not in Paid status")

    # Header Ordered is Oracle's own total; the schedule sum cross-checks it.
    ordered = _num(po.get("Ordered"))
    if abs(ordered - schedule_ordered) > TOLERANCE:
        notes.append(
            f"header Ordered ({ordered:,.2f}) disagrees with the sum of "
            f"schedule amounts ({schedule_ordered:,.2f})"
        )

    if invoiced > TOLERANCE and not invoices:
        notes.append(
            f"schedules record {invoiced:,.2f} billed but no invoice carries "
            "this PO number; the AP document could not be matched"
        )
        if po.get("PayOnReceiptFlag"):
            notes.append(
                "PayOnReceiptFlag is set on this PO — self-billing may "
                "explain the unmatched billing (unconfirmed)"
            )

    if abs(billed_in_ap - invoiced) > TOLERANCE:
        notes.append(
            f"matched invoices total {billed_in_ap:,.2f} against "
            f"{invoiced:,.2f} billed on the schedules "
            f"(difference {billed_in_ap - invoiced:,.2f})"
        )

    fully_received = _is_complete(received, ordered)
    fully_invoiced = _is_complete(invoiced, ordered)
    fully_paid = _is_complete(paid, invoiced)

    return {
        "shape": _SHAPE,
        "found": True,

        "order_number": po.get("OrderNumber"),
        "po_header_id": po.get("POHeaderId"),
        "status": po.get("Status"),
        "status_code": po.get("StatusCode"),
        "supplier": po.get("Supplier"),
        "supplier_site": po.get("SupplierSite"),
        "buyer": po.get("BuyerDisplayName") or po.get("Buyer"),
        "business_unit": po.get("ProcurementBU"),
        "payment_terms": po.get("PaymentTerms"),
        "currency": po.get("CurrencyCode"),
        "funds_status": po.get("FundsStatus"),

        "ordered": round(ordered, 2),
        "received": round(received, 2),
        "received_is_derived": True,
        "invoiced": round(invoiced, 2),
        "paid": round(paid, 2),
        "matched_invoice_total": round(billed_in_ap, 2),

        "remaining_to_receive": round(max(ordered - received, 0.0), 2),
        "remaining_to_invoice": round(max(ordered - invoiced, 0.0), 2),
        "remaining_to_pay": round(max(invoiced - paid, 0.0), 2),

        "fully_received": fully_received,
        "fully_invoiced": fully_invoiced,
        "fully_paid": fully_paid,

        "lifecycle_stage": _lifecycle_stage(
            fully_received, fully_invoiced, fully_paid
        ),
        "responsible_team": _responsible_team(
            fully_received, fully_invoiced, fully_paid
        ),

        "schedule_count": len(schedules),
        "invoice_count": len(invoices),
        "truncated": schedules_hit_cap or invoices_hit_cap,
        "notes": notes,
    }
