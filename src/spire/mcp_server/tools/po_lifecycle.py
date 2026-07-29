"""PO lifecycle status — the ordered/received/invoiced/paid reconciliation.

Plain async functions — not coupled to FastMCP. Registration happens in
spire.mcp_server.server.

WHAT THIS IS
One BOUNDED lifecycle tool. It assembles a single purchase order across
six endpoints — PO header, schedules, invoices, invoice installments,
supplier, supplier site — reconciles the four amounts against each other,
and names the stage the order sits at, who owns the next action, the risk
and the recommended action. Scope is fixed by identity: one PO, always.
Module 5 (PO Lifecycle, cross-module).

It backs five catalog prompts (A.2, A.3, A.4, A.7, A.10) through three
output shapes — status matrix, executive summary, diagnostic. One tool,
three renderings. Everything the shapes display is computed HERE; the
synthesizer copies and never derives.

WHY RECEIVED IS DERIVED, NOT FETCHED
ReceivedAmount is 0 or null on EVERY schedule row on this pod — ~4,500
rows checked 2026-07-28, re-verified on PO 701337 2026-07-29. The
received leg exists only as a QUANTITY, so the amount is derived:

    received = Amount * (ReceivedQuantity / Quantity)

Oracle's own arithmetic agrees: PO 701337 line 1 is Amount 1116,
Quantity 4, ReceivedQuantity 1 — and the pod's BilledAmount for that line
is 279, exactly 1116 * 1/4. Flagged `received_is_derived: True` so the
synthesizer says so rather than presenting it as a fetched field.

WHERE EACH NUMBER COMES FROM
The rule is: MONEY FROM INVOICE HEADERS, CONTEXT FROM INSTALLMENTS.

    ordered                purchaseOrders.Ordered (header)
    received               DERIVED from schedule quantities
    invoiced               sum of schedule BilledAmount
    matched_invoice_total  sum of invoices.InvoiceAmount
    paid                   sum of invoices.AmountPaid
    holds, due dates       invoiceInstallments
    setup, hold flags      suppliers/{id} and suppliers/{id}/child/sites/{id}

Installments are fetched one call per matched invoice and are therefore
CAPPED (MAX_INSTALLMENT_INVOICES). Sourcing money from a capped fetch
would produce a silently short total, so no money comes from there.
`UnpaidAmount` is used only as a CROSS-CHECK: a disagreement with the
header arithmetic lands in `notes`. A bitten cap costs hold visibility,
never a number.

WHY PAID USES AmountPaid, NOT PaidStatus
An earlier draft summed InvoiceAmount for invoices whose PaidStatus was
"Paid". A partially paid invoice is not in Paid status, so it contributed
ZERO — the `partial` state could never fire from real data. AmountPaid
carries the actual figure. Cancelled invoices (CanceledFlag) are excluded
from both totals and reported separately.

WHAT "PAID" CAN AND CANNOT SEE
Payment is visible only through /invoices filtered by PurchaseOrderNumber.
A PO can carry BilledAmount on its schedules with NO invoice bearing its
number — PO 701337 does exactly this, re-verified 2026-07-29 with a
control query against PO 162034 proving the filter itself works.

When that happens the paid leg is UNKNOWN, not zero. This tool used to
compute `remaining_to_pay = invoiced - paid` and report 398.00 owed on
701337 — asserting a debt when the truth is "the AP document cannot be
found". It now reports:

    paid_state: "unknown"     fully_paid: None     remaining_to_pay: None

`paid_state` is the field downstream code must branch on. `fully_paid` is
kept for symmetry with fully_received / fully_invoiced (prompt A.4 asks
for the three literally) but it is TRI-STATE: True / False / None. None
serializes to JSON null and `if fully_paid:` reads null as False — the
exact bug this removes. Branch on the string, not the bool.

    nothing_due  no AP invoice and nothing billed on the schedules —
                 the payment question has not arisen
    unknown      schedules record billing but no AP invoice carries this
                 PO number; the chain breaks before payment
    unpaid       matched invoices exist, nothing paid against them
    partial      matched invoices exist, part paid
    paid         matched invoices exist and are settled

WHY RISK AND RECOMMENDED ACTION ARE COMPUTED HERE
Prompt A.10 asks for a risk rating and a recommended action. Both are
DETERMINISTIC functions of fields already fetched — see _assess_risk and
_recommend_action. They are not the synthesizer's to invent.

The architecture has exactly two LLM boundaries and neither may reason
about the data. Letting an LLM decide that a PO is "Medium risk" makes
the rating unreproducible and unauditable, and every numeric defect this
project has fixed was fixed by moving the computation into the tool. Risk
carries `risk_reasons` so the rating can always be explained.

WHAT OVER-INVOICING MEANS
Nothing here treats invoiced > ordered as an error, matching
compare_orders_to_invoices: PO 162034 is 758.00 ordered against 830.01
invoiced, and that is real data. Tax, freight and price variance all
legitimately push an invoice above the order. Note the PO header reports
TotalTax 0, so PO-side tax does NOT explain 162034's 72.01 — that remains
unexplained and is reported as a difference, never diagnosed.

ON DATES ON THIS POD
The demo data is old: PO 701337 was created 2014-08-12, invoice 162034inv
is dated 2013-12-16. Any age or overdue figure is therefore ~12 years and
useless as a business signal. `days_overdue` is computed only where an
UNPAID balance exists, so settled invoices do not produce absurd ages,
and callers should treat a large value as an artefact of demo data.

POD QUIRKS THIS RELIES ON (all curl-verified 2026-07-29)
  - /purchaseOrders          q=OrderNumber='<n>'         filters server-side
  - /purchaseOrderSchedules  q=OrderNumber='<n>'         filters server-side
  - /invoices                q=PurchaseOrderNumber='<n>' filters server-side
  - totalResults=true is honoured by both collections. A totalResults you
    did not request is not there, so every paged fetch asks for it.
  - Invoice holds are NOT on the invoice header and there is no `holds`
    child. They live on invoiceInstallments: HoldFlag, HoldReason,
    HoldType, HeldBy, HoldDate.
  - There is NO payment document anywhere on this path — no payment
    number, no payment date, on either the invoice or the installment.
    "Which payment settled this" is unanswerable on this pod.
  - Supplier Status must NOT be matched server-side. Fetching by
    SupplierId (which the PO header carries) sidesteps that entirely.
  - `expand=sites` is ignored on BULK supplier fetches but WORKS on a
    single-resource GET. It returned 22 sites for JGA, so it is used only
    as a fallback: suppliers/{id}/child/sites/{siteId} returns the one
    site needed and accepts fields=.
  - Composite q= clauses fail silently here. Every query below uses a
    SINGLE clause. Never AND them.
"""

from __future__ import annotations

import sys
from datetime import date, datetime

from spire.fusion.client import FusionClient


PURCHASE_ORDERS_PATH = "/fscmRestApi/resources/11.13.18.05/purchaseOrders"
PURCHASE_ORDER_SCHEDULES_PATH = (
    "/fscmRestApi/resources/11.13.18.05/purchaseOrderSchedules"
)
INVOICES_PATH = "/fscmRestApi/resources/11.13.18.05/invoices"
SUPPLIERS_PATH = "/fscmRestApi/resources/11.13.18.05/suppliers"

# The reference documents ~200 as the pod's practical page size.
_PAGE_SIZE = 200

# Bounds the paged fetches. Both are server-filtered to one PO, so this is
# a safety net rather than a real limit: the widest PO seen on this pod is
# 46 schedule lines, well inside one page.
MAX_PAGES = 50

# Bounds the installment fan-out. Installments are a CHILD resource — one
# HTTP call per matched invoice, the only N+1 in this tool. Both test POs
# need 0 or 1 calls. The cap turns a pathological PO into a note rather
# than a hang, and costs only hold visibility, because no money is
# sourced from installments.
MAX_INSTALLMENT_INVOICES = 25

# Amount comparisons. Guards float noise from the received derivation
# (a division), not real gaps — below one cent of any currency here.
TOLERANCE = 0.01

# The paid-leg states. Exported so the synthesizer and display formatter
# assert against the set rather than hardcoding strings in three places.
PAID_STATE_NOTHING_DUE = "nothing_due"
PAID_STATE_UNKNOWN = "unknown"
PAID_STATE_UNPAID = "unpaid"
PAID_STATE_PARTIAL = "partial"
PAID_STATE_PAID = "paid"

PAID_STATES = (
    PAID_STATE_NOTHING_DUE,
    PAID_STATE_UNKNOWN,
    PAID_STATE_UNPAID,
    PAID_STATE_PARTIAL,
    PAID_STATE_PAID,
)

RISK_LOW = "Low"
RISK_MEDIUM = "Medium"
RISK_HIGH = "High"
RISK_LEVELS = (RISK_LOW, RISK_MEDIUM, RISK_HIGH)

_PO_FIELDS = [
    "POHeaderId", "OrderNumber", "Status", "StatusCode", "SupplierId",
    "Supplier", "SupplierSiteId", "SupplierSite",
    "SupplierContactDisplayName", "Buyer", "BuyerDisplayName",
    "CurrencyCode", "Ordered", "TotalTax", "PaymentTerms", "ProcurementBU",
    "PayOnReceiptFlag", "FundsStatus", "OrderDate", "CreationDate",
    "RequiredAcknowledgment", "AcknowledgmentDueDate",
    "SupplierCommunicationMethod", "PendingResponseRole", "Revision",
    "Requisition", "ShipToLocationCode",
]

_SCHEDULE_FIELDS = [
    "POHeaderId", "OrderNumber", "LineNumber", "ScheduleNumber", "Quantity",
    "Amount", "ReceivedQuantity", "ReceivedAmount", "BilledQuantity",
    "BilledAmount", "ScheduleStatus",
]

_INVOICE_FIELDS = [
    "InvoiceId", "InvoiceNumber", "Supplier", "SupplierNumber",
    "InvoiceAmount", "AmountPaid", "InvoiceCurrency", "InvoiceDate",
    "PaidStatus", "ApprovalStatus", "ValidationStatus", "CanceledFlag",
    "PaymentMethod", "PurchaseOrderNumber",
]

_INSTALLMENT_FIELDS = [
    "InstallmentNumber", "GrossAmount", "UnpaidAmount", "DueDate",
    "HoldFlag", "HoldReason", "HoldType", "HeldBy", "HoldDate",
    "PaymentMethod", "PaymentPriority",
]

_SUPPLIER_FIELDS = [
    "SupplierId", "Supplier", "SupplierNumber", "Status", "InactiveDate",
    "BusinessRelationship", "BusinessRelationshipCode", "SupplierType",
    "TaxOrganizationType", "OnOFACListFlag", "UseWithholdingTaxFlag",
    "WithholdingTaxGroup", "ParentSupplier", "OneTimeSupplierFlag",
]

_SITE_FIELDS = [
    "SupplierSiteId", "SupplierSite", "ProcurementBU", "Status",
    "InactiveDate", "SitePurposePurchasingFlag", "SitePurposePayFlag",
    "HoldAllNewPurchasingDocumentsFlag", "PurchasingHoldReason",
    "HoldAllInvoicesFlag", "HoldUnvalidatedInvoicesFlag", "PaymentHoldDate",
    "PaymentHoldReason", "MatchApprovalLevel", "InvoiceMatchOption",
    "PaymentTerms",
]

_SHAPE = "po_lifecycle_status"


async def _page_all(
    client: FusionClient,
    path: str,
    server_clause: str,
    fields: list[str],
    label: str,
    report_progress=None,
) -> tuple[list[dict], bool, int | None]:
    """Page a server-filtered collection to exhaustion or the cap.

    Returns (items, hit_page_cap, total_available). The clause is
    mandatory: this tool never scans an unfiltered collection.

    `totalResults=true` is requested on every page. Without it the pod
    returns `count`, which is the PAGE size, not the total — easy to
    misread, and it made truncation unreportable. The value is taken from
    the FIRST page: it describes the whole filtered set, so later pages
    add nothing, and reading it from the last page would lose it entirely
    when the cap is hit.

    total_available is None when the endpoint omits totalResults — an
    honest "unknown", not a zero. Callers must not treat it as a count.
    """
    items: list[dict] = []
    total_available: int | None = None

    for page in range(MAX_PAGES):
        params: dict[str, str | int] = {
            "limit": _PAGE_SIZE,
            "offset": page * _PAGE_SIZE,
            "onlyData": "true",
            "totalResults": "true",
            "q": server_clause,
            "fields": ",".join(fields),
        }
        response = await client.get(path, params=params)
        page_items = response.get("items", [])
        items.extend(page_items)

        if page == 0:
            reported = response.get("totalResults")
            if isinstance(reported, int):
                total_available = reported

        msg = f"{label} page {page + 1}: +{len(page_items)} (total {len(items)})"
        print(f"[po_lifecycle] {msg}", file=sys.stderr, flush=True)
        if report_progress is not None:
            await report_progress(page + 1, total_available, msg)

        has_more = response.get("hasMore")
        if has_more is False or (
            has_more is None and len(page_items) < _PAGE_SIZE
        ):
            return items, False, total_available

    return items, True, total_available


def _num(value) -> float:
    """Coerce a possibly-null amount to float.

    BilledAmount is null (not 0) on unbilled schedule rows, ReceivedAmount
    on unreceived ones, and AmountPaid on unpaid invoices. All must read
    as zero, or the sums raise instead of reporting an honest 0.00.
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


def _parse_date(value) -> date | None:
    """Parse a pod date or timestamp to a date, or None.

    The pod mixes plain dates (DueDate: "2014-01-15") with offset-aware
    timestamps (CreationDate: "2013-12-16T22:16:47.001+00:00"). Returns
    None on anything unparseable rather than raising — a missing date is a
    reportable gap, not a crash.
    """
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    try:
        if "T" in text:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


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
        ordered quantity — nothing to prorate against.
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


def _schedule_rows(schedules: list[dict]) -> list[dict]:
    """Per-schedule detail, with the derivation applied per row.

    Pure function. The aggregates alone cannot answer prompt A.7 — "why is
    this still open" needs to say WHICH line is short, not just that the
    total is. The data is already fetched; this stops it being discarded.
    """
    rows: list[dict] = []

    for row in schedules:
        amount = _num(row.get("Amount"))
        quantity = _num(row.get("Quantity"))
        received_quantity = _num(row.get("ReceivedQuantity"))
        billed = _num(row.get("BilledAmount"))

        if quantity > 0:
            received_amount = round(amount * (received_quantity / quantity), 2)
        else:
            received_amount = 0.0

        rows.append({
            "line_number": row.get("LineNumber"),
            "schedule_number": row.get("ScheduleNumber"),
            "status": row.get("ScheduleStatus"),
            "quantity": quantity,
            "received_quantity": received_quantity,
            "billed_quantity": _num(row.get("BilledQuantity")),
            "amount": round(amount, 2),
            "received_amount": received_amount,
            "billed_amount": round(billed, 2),
            "outstanding_amount": round(max(amount - received_amount, 0.0), 2),
            "fully_received": _is_complete(received_amount, amount),
        })

    return rows


def _summarise_invoices(
    invoices: list[dict],
) -> tuple[float, float, int, int, list[dict]]:
    """Sum paid and matched totals from invoice HEADERS.

    Pure function. Headers are the money source because they are never
    capped — see the module docstring.

    `paid` sums AmountPaid, not InvoiceAmount gated on PaidStatus: a
    partly paid invoice is not in Paid status and would otherwise
    contribute zero. Cancelled invoices are excluded from both totals and
    counted separately.

    Returns:
        (paid, matched_total, unpaid_count, canceled_count, live_invoices)
    """
    paid = 0.0
    matched_total = 0.0
    unpaid_count = 0
    canceled_count = 0
    live: list[dict] = []

    for invoice in invoices:
        if invoice.get("CanceledFlag"):
            canceled_count += 1
            continue

        amount = _num(invoice.get("InvoiceAmount"))
        amount_paid = _num(invoice.get("AmountPaid"))

        matched_total += amount
        paid += amount_paid
        if amount_paid < amount - TOLERANCE:
            unpaid_count += 1
        live.append(invoice)

    return paid, matched_total, unpaid_count, canceled_count, live


async def _fetch_installments(
    client: FusionClient, invoice: dict
) -> tuple[list[dict], str | None]:
    """Fetch one invoice's installments. Best effort.

    Returns (rows, error). A failure here must NOT fail the lifecycle
    answer: installments carry context (holds, due dates), never money, so
    losing them degrades the answer rather than invalidating it. The error
    string is surfaced as a note, so a silent degradation is impossible.
    """
    invoice_id = invoice.get("InvoiceId")
    if invoice_id is None:
        return [], "an invoice row carried no InvoiceId"

    path = f"{INVOICES_PATH}/{invoice_id}/child/invoiceInstallments"
    params = {
        "onlyData": "true",
        "limit": _PAGE_SIZE,
        "fields": ",".join(_INSTALLMENT_FIELDS),
    }
    try:
        response = await client.get(path, params=params)
    except Exception as exc:  # noqa: BLE001 - degrade, never fail the answer
        number = invoice.get("InvoiceNumber") or invoice_id
        return [], f"installments for invoice {number} could not be read ({exc})"

    return response.get("items", []), None


async def _fetch_supplier(
    client: FusionClient, supplier_id
) -> tuple[dict | None, str | None]:
    """Fetch the supplier master record by ID. Best effort.

    By ID, not by name: Supplier.Status cannot be matched server-side on
    this pod, and the PO header already carries SupplierId — so there is
    no lookup to get wrong and no client-side filtering to do.

    Setup is context, not money. A failure degrades the answer (the
    supplier row reads "could not be read") rather than invalidating it.
    """
    if supplier_id is None:
        return None, "the PO header carried no SupplierId"

    params = {"onlyData": "true", "fields": ",".join(_SUPPLIER_FIELDS)}
    try:
        return await client.get(
            f"{SUPPLIERS_PATH}/{supplier_id}", params=params
        ), None
    except Exception as exc:  # noqa: BLE001 - degrade, never fail the answer
        return None, f"supplier {supplier_id} could not be read ({exc})"


async def _fetch_supplier_site(
    client: FusionClient, supplier_id, site_id
) -> tuple[dict | None, str | None]:
    """Fetch the ONE supplier site on this PO by ID. Best effort.

    Uses the child path rather than expand=sites. Both work on a single
    supplier GET, but expand returns every site — 22 of them for JGA, at
    ~100 fields each — when exactly one is needed. The child path accepts
    fields= (verified 2026-07-29; not a given, since /standardReceipts
    rejects fields= with a 500).
    """
    if supplier_id is None or site_id is None:
        return None, "the PO header carried no SupplierSiteId"

    path = f"{SUPPLIERS_PATH}/{supplier_id}/child/sites/{site_id}"
    params = {"onlyData": "true", "fields": ",".join(_SITE_FIELDS)}
    try:
        return await client.get(path, params=params), None
    except Exception as exc:  # noqa: BLE001 - degrade, never fail the answer
        return None, f"supplier site {site_id} could not be read ({exc})"


def _summarise_installments(
    installments_by_invoice: list[tuple[dict, list[dict]]],
    today: date | None = None,
) -> tuple[list[dict], str | None, float, int | None]:
    """Extract holds, the earliest due date, and the unpaid cross-check.

    Pure function. Installments are the ONLY place invoice holds live on
    this pod — there is no `holds` child on /invoices and no hold field on
    the invoice header.

    `days_overdue` is computed only where an unpaid balance actually
    exists. The demo data is ~12 years old, so an unconditional age would
    label every settled invoice tens of thousands of days overdue.

    Returns:
        (holds, earliest_due_date_iso, unpaid_total, days_overdue).
    """
    today = today or date.today()
    holds: list[dict] = []
    unpaid_total = 0.0
    earliest_unpaid_due: date | None = None
    earliest_due: date | None = None

    for invoice, rows in installments_by_invoice:
        number = invoice.get("InvoiceNumber")
        for row in rows:
            unpaid = _num(row.get("UnpaidAmount"))
            unpaid_total += unpaid
            due = _parse_date(row.get("DueDate"))

            if due is not None:
                if earliest_due is None or due < earliest_due:
                    earliest_due = due
                if unpaid > TOLERANCE and (
                    earliest_unpaid_due is None or due < earliest_unpaid_due
                ):
                    earliest_unpaid_due = due

            if row.get("HoldFlag"):
                holds.append({
                    "invoice_number": number,
                    "installment_number": row.get("InstallmentNumber"),
                    "hold_type": row.get("HoldType"),
                    "hold_reason": row.get("HoldReason"),
                    "held_by": row.get("HeldBy"),
                    "hold_date": row.get("HoldDate"),
                    "amount_held": round(unpaid, 2),
                })

    days_overdue: int | None = None
    if earliest_unpaid_due is not None and earliest_unpaid_due < today:
        days_overdue = (today - earliest_unpaid_due).days

    earliest_iso = earliest_due.isoformat() if earliest_due else None
    return holds, earliest_iso, round(unpaid_total, 2), days_overdue


def _summarise_setup(
    supplier: dict | None, site: dict | None
) -> tuple[dict, list[str]]:
    """Flatten supplier and site setup into one block, with its blockers.

    Pure function. Returns (setup, blockers) where blockers are the
    conditions that would stop a transaction proceeding — an inactive
    supplier, a site hold, sanctions. They feed the risk assessment and
    are phrased as findings, not judgements.

    A missing supplier or site is reported as None throughout rather than
    defaulted to "ACTIVE": absent setup is unknown setup, and claiming a
    supplier is active on the strength of a failed fetch is exactly the
    class of assertion this tool exists to avoid.
    """
    supplier = supplier or {}
    site = site or {}
    blockers: list[str] = []

    supplier_status = supplier.get("Status")
    site_status = site.get("Status")

    setup = {
        "supplier_number": supplier.get("SupplierNumber"),
        "supplier_status": supplier_status,
        "supplier_inactive_date": supplier.get("InactiveDate"),
        "business_relationship": supplier.get("BusinessRelationship"),
        "spend_authorized": (
            supplier.get("BusinessRelationshipCode") == "SPEND_AUTHORIZED"
            if supplier.get("BusinessRelationshipCode") is not None else None
        ),
        "on_ofac_list": supplier.get("OnOFACListFlag"),
        "withholding_tax": bool(supplier.get("UseWithholdingTaxFlag")),
        "withholding_tax_group": supplier.get("WithholdingTaxGroup"),
        "parent_supplier": supplier.get("ParentSupplier"),

        "site_status": site_status,
        "site_inactive_date": site.get("InactiveDate"),
        "site_purchasing_enabled": site.get("SitePurposePurchasingFlag"),
        "site_pay_enabled": site.get("SitePurposePayFlag"),
        "site_payment_terms": site.get("PaymentTerms"),
        "match_approval_level": site.get("MatchApprovalLevel"),
        "invoice_match_option": site.get("InvoiceMatchOption"),

        "purchasing_hold": bool(
            site.get("HoldAllNewPurchasingDocumentsFlag")
        ),
        "purchasing_hold_reason": site.get("PurchasingHoldReason"),
        "invoice_hold_all": bool(site.get("HoldAllInvoicesFlag")),
        "invoice_hold_unvalidated": bool(
            site.get("HoldUnvalidatedInvoicesFlag")
        ),
        "payment_hold_date": site.get("PaymentHoldDate"),
        "payment_hold_reason": site.get("PaymentHoldReason"),

        "supplier_read": bool(supplier),
        "site_read": bool(site),
    }

    if supplier.get("OnOFACListFlag"):
        blockers.append(
            "supplier is flagged on the OFAC sanctions list"
        )
    if supplier_status and supplier_status.upper() != "ACTIVE":
        blockers.append(f"supplier status is {supplier_status}")
    if setup["spend_authorized"] is False:
        blockers.append(
            f"supplier is not spend authorized "
            f"({supplier.get('BusinessRelationship')})"
        )
    if site_status and site_status.upper() != "ACTIVE":
        blockers.append(f"supplier site status is {site_status}")
    if setup["purchasing_hold"]:
        reason = setup["purchasing_hold_reason"] or "no reason recorded"
        blockers.append(f"site holds all new purchasing documents ({reason})")
    if setup["invoice_hold_all"]:
        blockers.append("site holds all invoices")
    if setup["payment_hold_date"]:
        reason = setup["payment_hold_reason"] or "no reason recorded"
        blockers.append(
            f"site is on payment hold since {setup['payment_hold_date']} "
            f"({reason})"
        )
    if site and setup["site_pay_enabled"] is False:
        blockers.append("supplier site is not enabled for payment")

    return setup, blockers


def _classify_paid_leg(
    schedule_invoiced: float,
    matched_invoice_count: int,
    matched_invoice_total: float,
    paid: float,
) -> tuple[str, bool | None, float | None]:
    """Decide the paid state, the tri-state bool, and what remains.

    Pure function. The one place the unknown state is produced — so it is
    the function to read when asking "why did this PO report unknown".

    The unknown gate comes FIRST and overrides the arithmetic. Reaching
    the comparison below with no matched invoices would compute 0 paid of
    0 billed and conclude "settled", which is how the naive fix produced
    `fully_paid: True` on a PO where nothing was paid.

    Returns:
        (paid_state, fully_paid, remaining_to_pay). Both fully_paid and
        remaining_to_pay are None in the unknown state — callers must not
        substitute 0.0 or False for either.
    """
    if schedule_invoiced > TOLERANCE and matched_invoice_count == 0:
        # Billing exists on the PO but AP holds no document carrying its
        # number. The chain breaks here; payment is not knowable.
        return PAID_STATE_UNKNOWN, None, None

    if matched_invoice_total <= TOLERANCE:
        # Nothing billed anywhere. Not a gap — the payment question has
        # not arisen. `_is_complete`'s zero rule agrees: nothing was due.
        return PAID_STATE_NOTHING_DUE, True, 0.0

    outstanding = round(max(matched_invoice_total - paid, 0.0), 2)

    if paid >= matched_invoice_total - TOLERANCE:
        return PAID_STATE_PAID, True, 0.0
    if paid <= TOLERANCE:
        return PAID_STATE_UNPAID, False, outstanding
    return PAID_STATE_PARTIAL, False, outstanding


def _lifecycle_stage(
    fully_received: bool,
    fully_invoiced: bool,
    paid_state: str,
    hold_count: int = 0,
) -> str:
    """The earliest incomplete leg names the stage the PO sits at.

    Takes `paid_state` rather than a third boolean so the unknown case can
    name itself. A tri-state bool arriving here as None would take a
    `not fully_paid` branch and report "Awaiting payment" — asserting a
    payment is due when the tool has just established it cannot tell.

    A hold overrides only the payment branch, not the leg ordering: a hold
    on a PO still awaiting receipt is real, but it is not what the order
    is waiting on. Holds are always reported in `holds` regardless.
    """
    if not fully_received:
        return "Awaiting receipt"
    if not fully_invoiced:
        return "Awaiting invoicing"
    if paid_state == PAID_STATE_UNKNOWN:
        return "Payment status unknown — AP invoice not matched"
    if paid_state in (PAID_STATE_UNPAID, PAID_STATE_PARTIAL):
        if hold_count:
            return "Invoice on hold"
        return "Awaiting payment"
    return "Complete"


def _responsible_team(
    fully_received: bool,
    fully_invoiced: bool,
    paid_state: str,
    hold_count: int = 0,
    open_findings: bool = False,
) -> str:
    """Who owns the next action.

    Derived from the stage, NOT from an approval-chain lookup: approvals
    and the three receiving resources are unconfirmed or failing on this
    pod. This is ownership by lifecycle position — honest but shallow. It
    names the function, not the person.

    The unknown state routes to Accounts Payable, not Payments. Payments
    cannot act on an invoice that does not exist; the missing document is
    AP's to find. Routing it to Payments — which the boolean version did
    once the earlier legs were complete — sends the reader to a team with
    nothing to do.

    `open_findings` covers the completed-but-unreconciled case. PO 162034
    is closed, received, invoiced and paid, yet its invoice exceeds the
    order by 72.01 with no recorded cause. Reporting "no action
    outstanding" beside a recommended action for AP is a contradiction the
    reader has to resolve; the honest owner is AP, retrospectively. A
    finding nobody owns is a finding nobody closes.
    """
    if not fully_received:
        return "Supplier / Receiving"
    if not fully_invoiced:
        return "Accounts Payable"
    if paid_state == PAID_STATE_UNKNOWN:
        return "Accounts Payable — AP invoice not matched to this PO"
    if paid_state in (PAID_STATE_UNPAID, PAID_STATE_PARTIAL):
        if hold_count:
            return "Accounts Payable — release the hold"
        return "Payments"
    if open_findings:
        return "Accounts Payable — review the unexplained difference"
    return "None — no action outstanding"


def _assess_risk(
    setup_blockers: list[str],
    hold_count: int,
    days_overdue: int | None,
    truncated: bool,
    paid_state: str,
    fully_received: bool,
    fully_invoiced: bool,
    amount_disagreement: bool,
    terms_mismatch: bool,
) -> tuple[str, list[str]]:
    """Rate the PO's risk deterministically, and say why.

    Pure function. Prompt A.10 asks for a risk rating; this is where it
    comes from. Never the synthesizer — a rating an LLM invents is
    unreproducible and cannot be audited, and the same input must always
    produce the same rating.

    HIGH is reserved for things that BLOCK or ENDANGER: sanctions and
    setup holds (nothing can proceed), invoice holds (payment stopped),
    an overdue unpaid balance (money is late), truncation (the answer
    itself may be wrong, which is the most dangerous case of all).

    MEDIUM covers incomplete or unreconciled: an unknown paid leg, a leg
    still open, totals that disagree, terms overridden.

    Returns (risk, reasons). The reasons list is not decoration — a rating
    without its cause is an opinion.
    """
    reasons: list[str] = []
    high = False

    if setup_blockers:
        high = True
        reasons.extend(setup_blockers)
    if hold_count:
        high = True
        reasons.append(f"{hold_count} invoice installment(s) on hold")
    if days_overdue is not None:
        high = True
        reasons.append(f"unpaid balance {days_overdue:,} days past due")
    if truncated:
        high = True
        reasons.append(
            "the fetch was truncated, so the amounts are lower bounds"
        )

    if high:
        return RISK_HIGH, reasons

    if paid_state == PAID_STATE_UNKNOWN:
        reasons.append("the paid leg cannot be determined")
    if not fully_received:
        reasons.append("not fully received")
    if not fully_invoiced:
        reasons.append("not fully invoiced")
    if paid_state in (PAID_STATE_UNPAID, PAID_STATE_PARTIAL):
        reasons.append("an invoiced balance is outstanding")
    if amount_disagreement:
        reasons.append("matched invoices disagree with the schedules")
    if terms_mismatch:
        reasons.append("PO payment terms differ from the site default")

    if reasons:
        return RISK_MEDIUM, reasons

    return RISK_LOW, ["all legs complete and reconciled"]


def _recommend_action(
    setup_blockers: list[str],
    hold_count: int,
    paid_state: str,
    fully_received: bool,
    fully_invoiced: bool,
    remaining_to_receive: float,
    remaining_to_pay: float | None,
    amount_disagreement: bool,
    currency: str | None,
) -> str:
    """The single next action, in priority order.

    Pure function, and deliberately ONE action rather than a list: prompt
    A.10 asks what to do next, and a reader given six equal items has been
    told nothing. Ordered by what blocks what — setup blocks everything,
    a hold blocks payment, a missing invoice blocks the whole question.
    """
    money = currency or ""

    if setup_blockers:
        return (
            "Resolve the supplier setup blocker before transacting: "
            f"{setup_blockers[0]}."
        )
    if hold_count:
        return (
            "Accounts Payable: review and release the invoice hold — "
            "payment cannot proceed until it clears."
        )
    if paid_state == PAID_STATE_UNKNOWN:
        return (
            "Accounts Payable: locate the AP invoice for this PO, or "
            "confirm none exists. Until then the payment question has no "
            "answer."
        )
    if not fully_received:
        return (
            f"Receiving: chase or cancel the outstanding "
            f"{remaining_to_receive:,.2f} {money}".strip() + "."
        )
    if not fully_invoiced:
        return "Accounts Payable: obtain the supplier invoice for the balance."
    if paid_state in (PAID_STATE_UNPAID, PAID_STATE_PARTIAL):
        outstanding = remaining_to_pay if remaining_to_pay is not None else 0.0
        return (
            f"Payments: settle the outstanding {outstanding:,.2f} "
            f"{money}".strip() + "."
        )
    if amount_disagreement:
        return (
            "Accounts Payable: confirm the difference between the invoiced "
            "and billed amounts was intended. No payment action outstanding."
        )
    return "None — the order is complete and reconciled."


async def get_purchase_order_lifecycle_status(
    client: FusionClient,
    po_number: str,
    report_progress=None,
) -> dict:
    """Assemble and reconcile one PO's lifecycle across six endpoints.

    Generic over any PO number: nothing about a particular order is baked
    in. Missing legs are reported, not crashed on — a PO with no invoices,
    null BilledAmount, zero Quantity, or an unreadable supplier all
    produce an honest result.

    Args:
        po_number: The PO's OrderNumber (e.g. "701337") — the number
            printed on the order, which is also the key invoices carry.
            NOT the POHeaderId.

    Returns:
        A "po_lifecycle_status" dict: the header identity block, supplier
        and site setup, the four amounts (received flagged as derived),
        the three remainders, the completion flags, per-schedule detail,
        lifecycle_stage, responsible_team, risk with reasons,
        recommended_action, holds, counts, and a notes list carrying every
        gap found. found=False when no such PO exists.

        TWO FIELDS CAN BE None AND MUST NOT BE COERCED TO 0 OR False:
        `fully_paid` and `remaining_to_pay`, both null in the unknown
        paid state. Branch on `paid_state` instead.
    """
    po_number = str(po_number).strip()
    notes: list[str] = []

    po_params = {
        "onlyData": "true",
        "q": f"OrderNumber='{po_number}'",
        "fields": ",".join(_PO_FIELDS),
        "limit": 2,  # 2, not 1: detects a duplicate rather than hiding it
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

    schedules, schedules_hit_cap, schedule_total = await _page_all(
        client, PURCHASE_ORDER_SCHEDULES_PATH, f"OrderNumber='{po_number}'",
        _SCHEDULE_FIELDS, "schedules", report_progress,
    )
    if not schedules:
        notes.append("no schedules returned for this PO")

    invoices, invoices_hit_cap, invoice_total = await _page_all(
        client, INVOICES_PATH, f"PurchaseOrderNumber='{po_number}'",
        _INVOICE_FIELDS, "invoices", report_progress,
    )

    # Setup: two single-record fetches, both by ID from the PO header.
    supplier, supplier_error = await _fetch_supplier(client, po.get("SupplierId"))
    if supplier_error:
        notes.append(supplier_error)
    site, site_error = await _fetch_supplier_site(
        client, po.get("SupplierId"), po.get("SupplierSiteId")
    )
    if site_error:
        notes.append(site_error)

    setup, setup_blockers = _summarise_setup(supplier, site)

    schedule_ordered, received, invoiced, undivisible = _summarise_schedules(
        schedules
    )
    paid, matched_total, unpaid_count, canceled_count, live_invoices = (
        _summarise_invoices(invoices)
    )

    # Installments: context only, never money. One call per live invoice,
    # hard-capped — see MAX_INSTALLMENT_INVOICES.
    installments_by_invoice: list[tuple[dict, list[dict]]] = []
    installments_capped = len(live_invoices) > MAX_INSTALLMENT_INVOICES
    for invoice in live_invoices[:MAX_INSTALLMENT_INVOICES]:
        rows, error = await _fetch_installments(client, invoice)
        if error:
            notes.append(error)
        installments_by_invoice.append((invoice, rows))

    holds, earliest_due, installments_unpaid, days_overdue = (
        _summarise_installments(installments_by_invoice)
    )

    if undivisible:
        notes.append(
            "received amount could not be derived for line(s) "
            f"{undivisible}: ordered quantity is zero"
        )
    if canceled_count:
        notes.append(
            f"{canceled_count} cancelled invoice(s) excluded from all totals"
        )
    if unpaid_count:
        notes.append(f"{unpaid_count} matched invoice(s) not fully paid")
    if holds:
        notes.append(
            f"{len(holds)} invoice installment(s) on hold — payment cannot "
            "proceed until released"
        )
    for blocker in setup_blockers:
        notes.append(f"setup: {blocker}")
    if installments_capped:
        notes.append(
            f"only the first {MAX_INSTALLMENT_INVOICES} of "
            f"{len(live_invoices):,} invoices were checked for holds and due "
            "dates; amounts are unaffected"
        )

    # Truncation is provable rather than suspected: the page cap says "we
    # stopped", the pod's own count says how much was left behind.
    if schedules_hit_cap:
        known = (
            schedule_total if schedule_total is not None
            else "an unknown number of"
        )
        notes.append(
            f"schedule fetch stopped at the {MAX_PAGES}-page cap; "
            f"{len(schedules):,} of {known} rows were read, so every amount "
            "below is a lower bound"
        )
    if invoices_hit_cap:
        known = (
            invoice_total if invoice_total is not None
            else "an unknown number of"
        )
        notes.append(
            f"invoice fetch stopped at the {MAX_PAGES}-page cap; "
            f"{len(invoices):,} of {known} rows were read, so the paid "
            "figure is a lower bound"
        )

    # Header Ordered is Oracle's own total; the schedule sum cross-checks it.
    ordered = _num(po.get("Ordered"))
    if abs(ordered - schedule_ordered) > TOLERANCE:
        notes.append(
            f"header Ordered ({ordered:,.2f}) disagrees with the sum of "
            f"schedule amounts ({schedule_ordered:,.2f})"
        )

    # The PO may override the site's default payment terms. Not an error —
    # a documented difference prompt A.2 asks about.
    po_terms = po.get("PaymentTerms")
    site_terms = setup.get("site_payment_terms")
    terms_mismatch = bool(po_terms and site_terms and po_terms != site_terms)
    if terms_mismatch:
        notes.append(
            f"PO payment terms ({po_terms}) differ from the supplier site "
            f"default ({site_terms})"
        )

    if invoiced > TOLERANCE and not live_invoices:
        notes.append(
            f"schedules record {invoiced:,.2f} billed but no invoice carries "
            "this PO number; the AP document could not be matched, so the "
            "paid leg is unknown rather than zero"
        )
        if po.get("PayOnReceiptFlag"):
            notes.append(
                "PayOnReceiptFlag is set on this PO — self-billing may "
                "explain the unmatched billing (unconfirmed)"
            )

    amount_disagreement = bool(
        live_invoices and abs(matched_total - invoiced) > TOLERANCE
    )
    if amount_disagreement:
        notes.append(
            f"matched invoices total {matched_total:,.2f} against "
            f"{invoiced:,.2f} billed on the schedules "
            f"(difference {matched_total - invoiced:,.2f})"
        )

    fully_received = _is_complete(received, ordered)
    fully_invoiced = _is_complete(invoiced, ordered)
    paid_state, fully_paid, remaining_to_pay = _classify_paid_leg(
        invoiced, len(live_invoices), matched_total, paid
    )

    # Cross-check only: the pod's own unpaid figure against ours. A
    # disagreement is reported, never silently resolved — and never used,
    # because installments are capped and headers are not.
    if (
        installments_by_invoice
        and not installments_capped
        and remaining_to_pay is not None
        and abs(installments_unpaid - remaining_to_pay) > TOLERANCE
    ):
        notes.append(
            f"installments report {installments_unpaid:,.2f} unpaid against "
            f"{remaining_to_pay:,.2f} derived from invoice headers"
        )

    truncated = schedules_hit_cap or invoices_hit_cap
    remaining_to_receive = round(max(ordered - received, 0.0), 2)

    risk, risk_reasons = _assess_risk(
        setup_blockers, len(holds), days_overdue, truncated, paid_state,
        fully_received, fully_invoiced, amount_disagreement, terms_mismatch,
    )
    recommended_action = _recommend_action(
        setup_blockers, len(holds), paid_state, fully_received,
        fully_invoiced, remaining_to_receive, remaining_to_pay,
        amount_disagreement, po.get("CurrencyCode"),
    )

    return {
        "shape": _SHAPE,
        "found": True,

        "order_number": po.get("OrderNumber"),
        "po_header_id": po.get("POHeaderId"),
        "status": po.get("Status"),
        "status_code": po.get("StatusCode"),
        "revision": po.get("Revision"),
        "order_date": po.get("OrderDate"),
        "supplier": po.get("Supplier"),
        "supplier_id": po.get("SupplierId"),
        "supplier_site": po.get("SupplierSite"),
        "supplier_site_id": po.get("SupplierSiteId"),
        "supplier_contact": po.get("SupplierContactDisplayName"),
        "buyer": po.get("BuyerDisplayName") or po.get("Buyer"),
        "business_unit": po.get("ProcurementBU"),
        "payment_terms": po_terms,
        "currency": po.get("CurrencyCode"),
        "funds_status": po.get("FundsStatus"),
        "pay_on_receipt": bool(po.get("PayOnReceiptFlag")),
        "requisition": po.get("Requisition"),
        "ship_to_location": po.get("ShipToLocationCode"),
        "po_tax": _num(po.get("TotalTax")),

        # Supplier communication — real fields, often "None" on this pod.
        "acknowledgment_required": po.get("RequiredAcknowledgment"),
        "acknowledgment_due_date": po.get("AcknowledgmentDueDate"),
        "communication_method": po.get("SupplierCommunicationMethod"),
        "pending_response_role": po.get("PendingResponseRole"),

        # Supplier and site setup (prompts A.2, A.3).
        "setup": setup,
        "setup_blockers": setup_blockers,
        "payment_terms_overridden": terms_mismatch,

        "ordered": round(ordered, 2),
        "received": round(received, 2),
        "received_is_derived": True,
        "invoiced": round(invoiced, 2),
        "paid": round(paid, 2),
        "matched_invoice_total": round(matched_total, 2),

        "remaining_to_receive": remaining_to_receive,
        "remaining_to_invoice": round(max(ordered - invoiced, 0.0), 2),
        # None when paid_state is "unknown". Not zero.
        "remaining_to_pay": remaining_to_pay,

        "fully_received": fully_received,
        "fully_invoiced": fully_invoiced,
        # TRI-STATE: True / False / None. Branch on paid_state instead.
        "fully_paid": fully_paid,
        "paid_state": paid_state,

        "lifecycle_stage": _lifecycle_stage(
            fully_received, fully_invoiced, paid_state, len(holds)
        ),
        "responsible_team": _responsible_team(
            fully_received, fully_invoiced, paid_state, len(holds),
            amount_disagreement,
        ),
        "risk": risk,
        "risk_reasons": risk_reasons,
        "recommended_action": recommended_action,

        # Per-schedule detail — prompt A.7 needs to name the short line,
        # not just report that the total is short.
        "schedules": _schedule_rows(schedules),

        "holds": holds,
        "hold_count": len(holds),
        "earliest_due_date": earliest_due,
        # None unless an UNPAID balance is genuinely past due. Demo data
        # here is ~12 years old, so a non-null value will be very large.
        "days_overdue": days_overdue,
        "installments_unpaid_total": installments_unpaid,

        "schedule_count": len(schedules),
        "invoice_count": len(live_invoices),
        "canceled_invoice_count": canceled_count,
        "schedule_total_available": schedule_total,
        "invoice_total_available": invoice_total,
        "installments_capped": installments_capped,
        "truncated": truncated,
        "notes": notes,
    }
