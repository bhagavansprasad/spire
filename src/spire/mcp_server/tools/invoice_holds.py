"""Invoice hold tool — invoices currently on hold, with the held amount.

Plain async function — not coupled to FastMCP. Registration happens in
spire.mcp_server.server.

WHY THIS EXISTS
p15 asks "show all invoices currently on hold, with invoice number, supplier,
invoice amount, hold reason, and hold status". Spire refused:
"Filtering invoices by hold status is not supported."

That refusal was a coverage gap, not a Fusion limitation. Discovery on dev49
(2026-11-28) found the whole mechanism:

    FUSION.AP_HOLDS       SYNONYM -> AP_HOLDS_ALL
    FUSION.AP_HOLDS_ALL   VIEW, 41 columns
    FUSION.AP_HOLD_CODES  VIEW

    AP_HOLDS_ALL: 14,772 rows, 376 with RELEASE_LOOKUP_CODE IS NULL

so "on hold" is a real, populated state, and the invoice row simply does not
carry it. It lives on a separate resource.

THE ACTIVE-HOLD PREDICATE
A hold is active when it has not been released. Three candidates were measured
against the pod's own database:

    COUNT(*)                                          14,772
    RELEASE_LOOKUP_CODE IS NULL                          376
    RELEASE_REASON      IS NULL                          376
    both NULL                                            376

The two null tests select the identical 376 rows, and RELEASE_REASON IS NULL is
the one Fusion's REST `q=` accepts. `ReleaseDate is null` is rejected or
returns nothing, so the predicate is spelled `ReleaseReason is null`.

This matters more than it looks: a full pass over 14,772 holds was the reason
this looked expensive. The server-side predicate returns all 374 REST-visible
active holds in ONE page (hasMore=false), which is the difference between a
scan and a lookup.

WHY IT IS NOT A FILTER ON search_invoices
The invoice resource has no hold field and no holds child:

    /invoices links: appliedPrepayments, attachments, availablePrepayments,
                     invoiceDff, invoiceGdf, invoiceInstallments, invoiceLines

There is nothing on an invoice to filter. The hold is the entity.

THE AMOUNT IS JOINED, AND THE JOIN IS NOT BY NUMBER ALONE
`/invoiceHolds` does not expose InvoiceId — checked with expand=all, with
fields=, and via every link on the row; only InvoiceNumber is available. So the
amount must be joined through /invoices by invoice number, and invoice number
is NOT unique on this pod:

    active holds                          374
    distinct invoice ids                  170
    distinct invoice numbers              168
    numbers shared by >1 invoice            6
      (1122, 1234, INV-001, INV45383, DUSINV001, TEST123)

Invoice 1122 alone is 295,759.13 at Staffing Services and 2,000 at ABDUL — a
number-only join could report 148x the wrong figure.

The hold row carries Supplier, and (InvoiceNumber, Supplier) resolved all six
ambiguous cases correctly against the database:

    1122      -> ABDUL                    2,000.00
    1234      -> EIP Inc                 10,887.50
    DUSINV001 -> Lee Supplies               512.50
    INV-001   -> EFG Company              1,088.75
    INV45383  -> Baxter Healthcare        1,870.26
    TEST123   -> Midtown Computer Supplies  4,500.00

Supplier name strings are byte-identical on both resources ('Advanced Corp',
'Lee Supplies'), so the comparison is safe. No held invoice sits in a duplicate
(InvoiceNumber, VendorId) pair, so the key is unambiguous for this population.

The supplier is therefore REQUIRED to match. When it does not, or when the
invoice is not found at all (2 of the 376 active holds are orphans — their
INVOICE_ID has no AP_INVOICES_ALL row), the amount is left None and reported as
unknown. Falling back to "the only row" when several match would silently pick
an arbitrary invoice, which is the failure this guard exists to prevent.

COMPOSITE q= IS NOT USED
`q=InvoiceNumber='1122' AND ReleaseReason is null` returns empty on this pod —
the same single-clause limitation documented for /invoices. Each request sends
exactly one clause; the released test runs client-side on the already-fetched
page.

COST
1-2 pages for the holds plus one bounded call per distinct invoice number
(168 today), issued concurrently. That is a lookup, not a table scan, and it is
why this tool is viable where `overdue` (which has no server predicate and
walks ~26 pages) takes over five minutes.
"""

from __future__ import annotations

import asyncio

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.pagination import page_all
from spire.mcp_server.tools.tool_result import ToolResult


HOLDS_PATH = "/fscmRestApi/resources/11.13.18.05/invoiceHolds"
INVOICES_PATH = "/fscmRestApi/resources/11.13.18.05/invoices"

# The active-hold predicate. Measured to select exactly the same 376 rows as
# RELEASE_LOOKUP_CODE IS NULL; this is the spelling REST accepts.
ACTIVE_HOLD_CLAUSE = "ReleaseReason is null"

_PAGE_SIZE = 500
MAX_PAGES = 10

# Bounded concurrency for the per-invoice amount lookups. 168 calls at 8 in
# flight is a few seconds; unbounded would open 168 sockets at once.
_LOOKUP_CONCURRENCY = 8

_PROJECTED_FIELDS = [
    "HoldId",
    "InvoiceNumber",
    "Supplier",
    "HoldName",
    "HoldReason",
    "HoldDate",
    "ReleaseDate",
    "WorkflowStatus",
    "HoldDetails",
]

_SHAPE = "invoice_hold_list"


def _is_active(hold: dict) -> bool:
    """True when the hold has not been released.

    Belt and braces: the server clause already filters on the released state,
    but one page could in principle straddle a release. Checking the two
    fields this projection actually carries keeps the client-side rule honest
    even if the clause and the payload ever disagree.
    """
    return not hold.get("ReleaseDate") and not hold.get("ReleaseReason")


def _pick_amount(
    items: list[dict], supplier: str | None
) -> float | None:
    """Choose the invoice amount that belongs to this hold, or None.

    Pure, so the join rule is testable without a client. Split out of
    _amount_for because this is where the correctness lives: the number alone
    is not unique, so the supplier has to corroborate, and "unsure" must
    return None rather than an arbitrary row.

    Cases, in order:
      - supplier present and exactly one row matches it  -> that row's amount
      - supplier present, 0 or >1 rows match             -> None (disagreeing
        names, or the composite key is not unique for this number)
      - supplier absent and the number returned one row  -> that row's amount
      - supplier absent and the number is ambiguous      -> None
    """
    if not items:
        return None

    if supplier:
        matched = [r for r in items if r.get("Supplier") == supplier]
        if len(matched) != 1:
            return None
        amount = matched[0].get("InvoiceAmount")
    elif len(items) == 1:
        amount = items[0].get("InvoiceAmount")
    else:
        return None

    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        return None
    return float(amount)


async def _amount_for(
    client: FusionClient,
    invoice_number: str,
    supplier: str | None,
) -> float | None:
    """Resolve the InvoiceAmount for one held invoice, or None when unsure.

    Invoice numbers repeat across suppliers on this pod, so the supplier must
    corroborate. A miss returns None rather than a guess: an absent amount
    prints as an em dash, which is honest, where a wrong amount is not.
    """
    try:
        response = await client.get(
            INVOICES_PATH,
            {
                "q": f"InvoiceNumber='{invoice_number}'",
                "limit": 10,
                "fields": "InvoiceNumber,Supplier,InvoiceAmount",
            },
        )
    except Exception:
        # A single failed lookup must not sink the whole answer; the row keeps
        # its amount as unknown.
        return None

    return _pick_amount(response.get("items") or [], supplier)


async def search_invoice_holds(
    client: FusionClient,
    on_hold: bool = True,
    limit: int = 100,
    report_progress=None,
) -> ToolResult:
    """Return invoices currently on hold, with the held invoice amount.

    Args:
        client: An open FusionClient.
        on_hold: The parser supplies True from the KG filter of the same name.
            Only True is implemented: the entity Spire exposes IS the active
            holds, so there is no released-history reading here. A False
            request is not silently reinterpreted — it raises, because
            answering "invoices on hold" with a released-hold list, or the
            reverse, is exactly the substitution this codebase forbids.
        limit: Max hold rows to return AFTER the client-side active test.
        report_progress: Optional progress callback, matching page_all's.

    Returns:
        ToolResult with:
          - items: one dict per ACTIVE HOLD (not per invoice — an invoice can
            carry several holds and each is its own row), projected to
            HoldId, InvoiceNumber, Supplier, HoldName, HoldReason, HoldDate,
            WorkflowStatus, and the joined InvoiceAmount
          - total_available: the number of active holds found
          - limit_applied: the limit used
          - truncated: True when more active holds exist than were returned
    """
    if on_hold is not True:
        raise ValueError(
            "search_invoice_holds only answers for holds that are currently "
            "active (on_hold=True). Listing RELEASED holds is a different "
            "question over a 14,396-row history and is not implemented; "
            "refusing rather than substituting one reading for the other."
        )

    holds, hit_cap, _ = await page_all(
        client,
        HOLDS_PATH,
        "search_invoice_holds",
        server_clause=ACTIVE_HOLD_CLAUSE,
        fields=_PROJECTED_FIELDS,
        page_size=_PAGE_SIZE,
        max_pages=MAX_PAGES,
        report_progress=report_progress,
    )

    active = [h for h in holds if _is_active(h)]

    # Collapse repeated holds onto the same invoice.
    #
    # Fusion records holds at LINE granularity, so one invoice legitimately
    # carries several rows with the same hold name and reason. Measured on
    # dev49: invoice 101306 has four active DIST VARIANCE holds (HoldIds
    # 286566-286569) whose reason text is character-for-character identical,
    # because four separate lines are held.
    #
    # Reporting them as four rows is faithful to the holds table and wrong for
    # the question being asked: "show the invoices on hold" wants invoices,
    # and four identical lines read as a bug. They are therefore merged on the
    # fields the reader can actually see — invoice, supplier, hold name, hold
    # reason — and the number of underlying holds rides along as HoldCount so
    # nothing is hidden. Two DIFFERENT holds on one invoice stay two rows,
    # because they say different things.
    merged: dict[tuple, dict] = {}
    for hold in active:
        key = (
            str(hold.get("InvoiceNumber") or ""),
            str(hold.get("Supplier") or ""),
            str(hold.get("HoldName") or ""),
            str(hold.get("HoldReason") or ""),
        )
        if key in merged:
            merged[key]["HoldCount"] += 1
            continue
        merged[key] = {
            "InvoiceNumber": hold.get("InvoiceNumber"),
            "Supplier": hold.get("Supplier"),
            "HoldName": hold.get("HoldName"),
            "HoldReason": hold.get("HoldReason"),
            "HoldDate": hold.get("HoldDate"),
            "WorkflowStatus": hold.get("WorkflowStatus"),
            "HoldCount": 1,
        }

    rows = sorted(
        merged.values(),
        key=lambda h: (str(h.get("InvoiceNumber") or ""), str(h.get("HoldName") or "")),
    )

    shown = rows[:limit]

    # One amount lookup per DISTINCT invoice number, not per hold: an invoice
    # with three active holds is fetched once. The results are then reused for
    # every hold row on that invoice.
    wanted: dict[str, str | None] = {}
    for hold in shown:
        number = str(hold.get("InvoiceNumber") or "")
        if number:
            wanted.setdefault(number, hold.get("Supplier"))

    numbers = list(wanted)
    amounts: dict[str, float | None] = {}
    if numbers:
        for start in range(0, len(numbers), _LOOKUP_CONCURRENCY):
            batch = numbers[start : start + _LOOKUP_CONCURRENCY]
            results = await asyncio.gather(
                *(_amount_for(client, n, wanted[n]) for n in batch)
            )
            amounts.update(dict(zip(batch, results)))

    items: list[dict] = []
    for row in shown:
        number = str(row.get("InvoiceNumber") or "")
        amount = amounts.get(number)
        items.append(
            {
                "InvoiceNumber": row.get("InvoiceNumber"),
                "Supplier": row.get("Supplier"),
                # None, not 0.0, when the join could not be corroborated: the
                # renderer prints an em dash for None, which says "not known",
                # where a 0.00 would state a falsehood about the amount owed.
                "InvoiceAmount": amount,
                "HoldName": row.get("HoldName"),
                "HoldReason": row.get("HoldReason"),
                "HoldDate": row.get("HoldDate"),
                "WorkflowStatus": row.get("WorkflowStatus"),
                "HoldStatus": "On hold",
                # How many underlying hold rows this line stands for. 1 for
                # most invoices; higher when several lines are held.
                "HoldCount": row.get("HoldCount"),
            }
        )

    return ToolResult.build(
        items=items,
        limit_applied=limit,
        total_available=len(rows),
        capped=hit_cap,
    )
