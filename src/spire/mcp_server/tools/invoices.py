
"""Invoice search tool.

Plain async function — not coupled to FastMCP. Registration happens
in spire.mcp_server.server.

Composite filter note:
Fusion REST's q= parameter on /invoices does not reliably AND-combine
clauses on this pod (clauses combine to empty result). Workaround: send
the most selective single clause via q=, filter remaining clauses in
Python. Over-fetch is capped at OVERFETCH_LIMIT.

Filters supported:
- invoice_number: exact match on InvoiceNumber (e.g. "LEE-01-1006-111"). Most selective filter, so it wins the single server q= clause when present.
- purchase_order: exact match on PurchaseOrderNumber (the PO NUMBER, e.g.
  "162034" — not POHeaderId). Invoices carry the PO number on the header
  and it filters server-side. Most selective filter, so it wins the single
  server q= clause when present.
- supplier_number: exact match on SupplierNumber
- supplier_name: substring match (LIKE) on Supplier
- invoice_date_after: ISO date string; matches invoices on or after this date
- invoice_date_before: ISO date string; matches invoices strictly before
  this date (exclusive). Client-side only — never sent as the server q=
  clause, so a lone invoice_date_before with no other filter over-fetches
  up to `limit` unfiltered and may miss older records beyond the fetch
  window. Pair it with invoice_date_after for a bounded range.
- unpaid: When True, restrict to invoices not yet fully paid. Server
  clause PaidStatus='Unpaid' plus a second single-clause call for
  PaidStatus='Partially paid' (composite q= is unreliable here).
  See docs/design/INVOICE_STATUS_ACCEPTANCE.md §4.2.
- overdue: When True, restrict to Unpaid invoices whose DueDate is
  before today. Server clause PaidStatus='Unpaid'; the DueDate test
  runs client-side. Partially paid rows are outside this reading —
  see §4.3.
- pending: When True, restrict to ApprovalStatus='Required' — the
  default reading of "pending" in AP. See §4.1.
- limit: max records returned after client-side filtering (default 25)
"""

from datetime import date

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.pagination import page_all
from spire.mcp_server.tools.tool_result import ToolResult


INVOICES_PATH = "/fscmRestApi/resources/11.13.18.05/invoices"

# Upper bound on the server-side fetch so client-side filtering has
# enough to work with. Tunable; higher means more network, lower
# means we may miss matches.
OVERFETCH_LIMIT = 200

_PROJECTED_FIELDS = [
    "InvoiceId",
    "InvoiceNumber",
    "InvoiceDate",
    "DueDate",
    "InvoiceAmount",
    "InvoiceCurrency",
    "Supplier",
    "SupplierNumber",
    "PaidStatus",
    "ApprovalStatus",
    "PurchaseOrderNumber",
    "CreatedBy",
    "CreationDate",
    "LastUpdatedBy",
    "LastUpdateDate",
]


# The totalResults probe lives on FusionClient — client.total_results.
# This module had its own _fetch_total_for_clause, and so did
# purchase_orders.py and suppliers.py:
# three copies of one function, differing only in which path constant
# they closed over, plus a fourth in aggregate_invoices.py that was
# already orphaned. FusionClient.total_results is the same function with
# the path as a parameter, and it existed unused because page_all stopped
# calling it when the count moved onto the fetch page.
#
# Four copies of a helper is how this codebase came to page at 200 in one
# file and 500 in another. One caller-visible behaviour, one definition.


async def search_invoices(
    client: FusionClient,
    invoice_number: str | None = None,
    purchase_order: str | None = None,
    supplier_number: str | None = None,
    supplier_name: str | None = None,
    invoice_date_after: str | None = None,
    invoice_date_before: str | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    unpaid: bool = False,
    overdue: bool = False,
    pending: bool = False,
    limit: int = 25,
) -> ToolResult:
    """Search Oracle Fusion invoices.

    Args:
        purchase_order: Exact PurchaseOrderNumber, e.g. "162034". This is
            the PO NUMBER (as shown on the PO), not POHeaderId.
        supplier_number: Exact SupplierNumber, e.g., "1252".
        supplier_name: Substring match on Supplier name.
        invoice_date_after: ISO date "YYYY-MM-DD". Matches invoices on
            or after this date (inclusive).
        invoice_date_before: ISO date "YYYY-MM-DD". Matches invoices
            strictly before this date (exclusive). Applied client-side
            only. For a calendar month, pair with invoice_date_after:
            e.g. Jan 2022 -> after="2022-01-01", before="2022-02-01".
        amount_min: Lower bound on InvoiceAmount (inclusive). Client-side.
        amount_max: Upper bound on InvoiceAmount (inclusive). Client-side.
        unpaid: When True, restrict to invoices not yet fully paid.
            See the module docstring for the two-call mechanism.
        overdue: When True, restrict to Unpaid invoices whose DueDate
            is before today.
        pending: When True, restrict to ApprovalStatus='Required'.
        limit: Max records to return AFTER client-side filtering.

    Returns:
        ToolResult with:
          - items: projected invoice dicts (up to `limit`)
          - total_available: true source count when computable, else None
          - limit_applied: the limit value used
          - truncated: True iff we know more records match than returned
    """
    # Pick the most selective filter to send to Fusion via q=.
    # Priority: purchase_order (one PO) > supplier_number (exact) > LIKE
    # > date lower bound.
    # invoice_date_before is intentionally never the server clause; it
    # stays a pure client-side filter to keep the truncation logic intact.
    server_clause: str | None = None
    if invoice_number:
        server_clause = f"InvoiceNumber='{invoice_number}'"
    elif purchase_order:
        server_clause = f"PurchaseOrderNumber='{purchase_order}'"
    elif supplier_number:
        server_clause = f"SupplierNumber='{supplier_number}'"
    elif supplier_name:
        server_clause = f"Supplier LIKE '%{supplier_name}%'"
    elif overdue:
        # Compound predicate: server clause is PaidStatus='Unpaid',
        # the DueDate < today test runs client-side below.
        server_clause = "PaidStatus='Unpaid'"
    elif unpaid:
        server_clause = "PaidStatus='Unpaid'"
    elif pending:
        server_clause = "ApprovalStatus='Required'"
    elif invoice_date_after:
        server_clause = f"InvoiceDate >= '{invoice_date_after}'"

    # Over-fetch if we'll be filtering further; otherwise use limit directly.
    # 'overdue' is a compound predicate whose date half runs client-side,
    # so the fetch MUST over-fetch — a single-clause 'not needs_client_filter'
    # path would report the unfiltered PaidStatus='Unpaid' count as if it
    # were the overdue count. Force the overfetch path when overdue is set.
    needs_client_filter = overdue or sum(
        bool(x)
        for x in (
            invoice_number,
            purchase_order,
            supplier_number,
            supplier_name,
            invoice_date_after,
            invoice_date_before,
            amount_min is not None,
            amount_max is not None,
            unpaid,
            overdue,
            pending,
        )
    ) > 1
    fetch_limit = OVERFETCH_LIMIT if needs_client_filter else limit

    params: dict[str, str | int] = {"limit": fetch_limit}
    if server_clause:
        params["q"] = server_clause

    # When any client-side filtering runs on top of the server clause,
    # the tool needs the FULL server-clause set to report an honest
    # count for the filtered result. A single-page overfetch sees at
    # most OVERFETCH_LIMIT rows and can miss matches beyond that
    # window (this is the 'pending for a long time' case, whose total
    # was previously reported as 'unknown'). Page the server clause
    # to exhaustion when the server clause is available; the plain
    # overfetch is the fallback for the no-server-clause case
    # (amount-only filters).
    fetch_truncated = False
    if needs_client_filter and server_clause:
        items, hit_page_cap, _ = await page_all(
            client,
            INVOICES_PATH,
            "search_invoices",
            server_clause=server_clause,
            page_size=500,
            max_pages=30,
        )
        fetch_truncated = hit_page_cap
    else:
        response = await client.get(INVOICES_PATH, params=params)
        items = list(response.get("items", []))
        if needs_client_filter:
            fetch_truncated = len(items) >= OVERFETCH_LIMIT

    # 'unpaid' alone: the semantic is the union of Unpaid + Partially
    # paid. Composite q= is unreliable on this pod, so the two
    # statuses ride as two single-clause calls and their rows merge.
    # Composed cases (unpaid + supplier) take the paged path above;
    # the paged fetch already carries that supplier's partials, so
    # this second call is scoped to the 'unpaid alone' case.
    if unpaid and not overdue and not needs_client_filter:
        partial_params = {
            "limit": OVERFETCH_LIMIT,
            "q": "PaidStatus='Partially paid'",
            "onlyData": "true",
        }
        partial_response = await client.get(
            INVOICES_PATH, params=partial_params
        )
        items.extend(partial_response.get("items", []))

    # Apply remaining filters in Python.
    def matches(item: dict) -> bool:
        if invoice_number and item.get("InvoiceNumber") != invoice_number:
            return False
        if purchase_order and item.get("PurchaseOrderNumber") != purchase_order:
            return False
        if supplier_number and item.get("SupplierNumber") != supplier_number:
            return False
        if supplier_name and supplier_name.lower() not in (item.get("Supplier") or "").lower():
            return False
        if invoice_date_after and (item.get("InvoiceDate") or "") < invoice_date_after:
            return False
        if invoice_date_before and (item.get("InvoiceDate") or "") >= invoice_date_before:
            return False
        if amount_min is not None or amount_max is not None:
            amt = item.get("InvoiceAmount")
            if amt is None:
                return False
            if amount_min is not None and amt < amount_min:
                return False
            if amount_max is not None and amt > amount_max:
                return False
        if unpaid and item.get("PaidStatus") not in ("Unpaid", "Partially paid"):
            return False
        if overdue:
            if item.get("PaidStatus") == "Paid":
                return False
            due = item.get("DueDate") or ""
            if due >= date.today().isoformat():
                return False
        if pending and item.get("ApprovalStatus") != "Required":
            return False
        return True

    filtered = [item for item in items if matches(item)]
    final_items = filtered[:limit]
    projected = [{k: item.get(k) for k in _PROJECTED_FIELDS} for item in final_items]

    # 'unpaid' is the union of Unpaid + Partially paid, fetched as two
    # single-clause calls and merged above. The server-clause total
    # alone underreports the union (it counts only Unpaid), so sum both
    # clauses' totals — the answer's headline count must include the
    # partials the rows already carry. Only fires when the partials
    # merge actually ran (server clause is the Unpaid clause).
    if unpaid and not overdue and not needs_client_filter:
        t_unpaid = await client.total_results(
            INVOICES_PATH, "PaidStatus='Unpaid'"
        )
        t_partial = await client.total_results(
            INVOICES_PATH, "PaidStatus='Partially paid'"
        )
        if t_unpaid is not None and t_partial is not None:
            return ToolResult.build(
                items=projected,
                limit_applied=limit,
                total_available=t_unpaid + t_partial,
            )

    # ---- Determine total_available and truncated ----
    #
    # Two paths:
    #
    # 1. Client-side filtering ran. The fetch was paged (above) to
    #    exhaustion or the page cap, so len(filtered) is the honest
    #    count of the fully-filtered set — unless the page cap fired,
    #    in which case the answer says 'unknown' rather than a
    #    plausible-looking wrong number.
    #
    # 2. No client-side filtering. Single server clause; a cheap
    #    totalResults call gives the authoritative count.

    if needs_client_filter:
        if fetch_truncated:
            return ToolResult(
                items=projected,
                total_available=None,
                limit_applied=limit,
                truncated=True,
            )
        return ToolResult.build(
            items=projected,
            limit_applied=limit,
            total_available=len(filtered),
        )

    if len(final_items) >= limit:
        total = await client.total_results(INVOICES_PATH, server_clause)
        return ToolResult.build(
            items=projected,
            limit_applied=limit,
            total_available=total,
        )

    return ToolResult.build(
        items=projected,
        limit_applied=limit,
        total_available=len(filtered),
    )


