
"""Receivables credit memos tool: recent AR credit memos (top-level list).

Credit memos are a top-level resource at /receivablesCreditMemos — unlike
AR invoice lines, there is NO parent id in the path. Each memo carries its
own identity (CustomerTransactionId, TransactionNumber), a date, the entered
amount, the bill-to customer, currency, and status.

Same object model as ReceivablesInvoice, with two differences that matter:
- EnteredAmount is normally NEGATIVE (a credit). Do NOT assume the sign —
  the demo pod has at least one POSITIVE, Incomplete memo mixed in.
- The status field is CreditMemoStatus (e.g. 'Complete', 'Incomplete').

"Recent" ordering is done SERVER-SIDE via orderBy=TransactionDate:desc
(confirmed working on this pod), so the newest memos come first and `limit`
gives a clean top-N. The total credit value is computed by
compute_total_credit() below and layered on by the server wrapper. It is a
raw ledger sum WITHIN ONE CURRENCY — a positive outlier offsets the
negatives — and is withheld entirely when the rows span several
currencies, because there is no meaningful number to give.

Returns a ToolResult (like the other AR tools) so callers can tell a
complete result from a capped subset. The total is layered on by the wrapper.
"""

import httpx

from spire.fusion.client import FusionClient
from spire.mcp_server.tools.tool_result import ToolResult


# Top-level credit-memos resource — no parent id in the path.
RECEIVABLES_CREDIT_MEMOS_PATH = (
    "/fscmRestApi/resources/11.13.18.05/receivablesCreditMemos"
)

_PROJECTED_FIELDS = [
    "CustomerTransactionId",
    "TransactionNumber",
    "TransactionDate",
    "EnteredAmount",
    "CreditMemoCurrency",
    "CreditMemoStatus",
    "BillToCustomerName",
    "BillToCustomerNumber",
]


async def list_receivables_credit_memos(
    client: FusionClient,
    limit: int = 25,
) -> ToolResult:
    """List recent AR credit memos, newest first.

    Args:
        limit: Max credit-memo records to return. Ordered by TransactionDate
            descending server-side, so this is a true top-N of the most
            recent memos. Default 25.

    Returns:
        ToolResult whose items are the projected credit-memo dicts, newest
        first. Empty items means no credit memos exist on the pod.
        total_available is the pod's count of credit memos (from
        totalResults), NOT the number returned — so a caller can honestly
        say "25 of 1,343" rather than "25 credit memos".
    """
    params = {
        "onlyData": "true",
        "orderBy": "TransactionDate:desc",
        "limit": limit,
        "totalResults": "true",
        "fields": ",".join(_PROJECTED_FIELDS),
    }
    try:
        response = await client.get(RECEIVABLES_CREDIT_MEMOS_PATH, params=params)
    except httpx.HTTPStatusError as exc:
        # A 404 on a top-level list is unexpected, but treat it as "no memos"
        # (empty ToolResult) rather than crashing. Any other status is a real
        # error — re-raise it.
        if exc.response.status_code == 404:
            return ToolResult.build(
                items=[], limit_applied=limit, total_available=0
            )
        raise

    items = response.get("items", [])
    projected = [{k: item.get(k) for k in _PROJECTED_FIELDS} for item in items]

    # The pod's own count for this collection. Without it, total_available
    # equals the returned row count, ToolResult.build computes
    # `total_available > len(items)` as false, and the result claims nothing
    # was truncated — so a capped slice is indistinguishable from a complete
    # answer. Falls back to the row count when the endpoint omits
    # totalResults: an honest floor, not an invented total.
    total_available = response.get("totalResults")
    if not isinstance(total_available, int):
        total_available = len(projected)

    return ToolResult.build(
        items=projected,
        limit_applied=limit,
        total_available=total_available,
    )


def compute_total_credit(
    items: list[dict],
    total_available: int | None = None,
) -> tuple[float | None, str | None]:
    """Total the credit memos — but ONLY within a single currency, and ONLY
    when the rows are the whole population, not a truncated sample.

    Returns (total, note). Exactly one is None.

    WHY THIS IS NOT A PLAIN SUM
    The earlier version summed EnteredAmount across every returned row
    regardless of currency. On this pod that produced

        Total credit value: -17232.52

    over 25 memos denominated in USD, CAD, GBP and EUR. The arithmetic
    was right and the number was meaningless — it is a figure in no
    currency at all, and nothing in the output said so. A reader has no
    way to tell it apart from a real total.

    So: when the rows span more than one currency there is no total to
    give, and this returns None plus a note saying why. Callers must
    render the note instead of the number, not alongside it.

    WHY TRUNCATION ALSO WITHHOLDS THE TOTAL (#27)
    ``items`` is the capped page the fetch returned (default 25), NOT the
    whole collection. Summing it and presenting the figure as "the total
    value of credit memos" is a partial sum labelled as complete — the
    #27 defect ("Total credit value: X" over 25 of 2,244). ``total_available``
    is the pod's own count (totalResults); when it exceeds the rows in
    hand, the sample is truncated and there is no honest population total
    to give from these rows alone. Return None plus a note that says so and
    points at a bounded alternative, exactly as the currency case does.
    A single sampled outlier (one -220,000 memo) makes the sample-sum not
    even representative, so this is withheld, not estimated.

    Checked AFTER currency: a multi-currency sample is disqualified by the
    currency note regardless of truncation, which keeps that (already-live)
    path unchanged. ``total_available=None`` disables the truncation guard
    (an unknown count is treated as "not known to be truncated"), so
    callers that cannot supply a count keep the prior single-currency
    behavior.

    THE SIGN IS DELIBERATE, AND STAYS
    EnteredAmount is normally negative (a credit), but the pod carries at
    least one POSITIVE, Incomplete memo. The single-currency total is the
    raw ledger sum, so a positive memo offsets the negatives. That is the
    ledger figure and it is the intended reading — not a defect. Whether
    an Incomplete memo belongs in the total at all is a domain question,
    unanswered here.

    Args:
        items: Credit-memo rows as projected by
            list_receivables_credit_memos.
        total_available: the pod's count for the whole collection
            (totalResults). When it exceeds len(items) the rows are a
            truncated sample and no total is given. None disables the
            truncation guard.

    Returns:
        (total, None)  when every row shares one currency AND the rows are
                       the whole set (or there are no rows: the total is
                       0.0).
        (None, note)   when the rows span two or more currencies, OR the
                       rows are a truncated sample of a larger collection.
    """
    currencies = {
        item.get("CreditMemoCurrency")
        for item in items
        if item.get("CreditMemoCurrency")
    }
    if len(currencies) > 1:
        listed = ", ".join(sorted(currencies))
        return None, (
            f"Not totalled: these memos span {len(currencies)} currencies "
            f"({listed}). A single sum across them would be a figure in no "
            "currency at all."
        )
    if total_available is not None and total_available > len(items):
        return None, (
            f"Not totalled: these are the {len(items)} most recent of "
            f"{total_available} credit memos. A sum over only the sampled "
            "rows would misstate the full set — ask for a bounded set "
            "(e.g. a date range or a single customer) and I'll total that."
        )
    total = sum((item.get("EnteredAmount") or 0) for item in items)
    return float(total), None



