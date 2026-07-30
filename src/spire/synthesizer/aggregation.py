"""Aggregation, count and comparison response schemas.

These three families are selected by a SHAPE TAG the tool stamps on its
result, not by target_entity — an aggregation or comparison Intent
carries no target entity at all, only an aggregate or comparison block.
CountResponse and ComparisonResponse are built deterministically from the
tool's own numbers with no LLM involved; the ranking schemas are the ones
an LLM actually narrates.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from spire.synthesizer.models_common import _SUMMARY_FIELD, _TRUNCATION_FIELD


class SupplierSpendRow(BaseModel):
    """One supplier in a spend ranking (feature 7 aggregation).

    supplier_number is validated against the ranking the executor
    produced — the LLM must not invent or reorder suppliers."""

    supplier_name: str = Field(description="The supplier's display name.")
    supplier_number: str = Field(
        description="The supplier's SupplierNumber (human-readable id)."
    )
    total_spend: float = Field(
        description="Total invoiced amount for this supplier over the range, "
        "copied exactly from the ranking data. Never recompute."
    )
    invoice_count: int = Field(
        description="Number of invoices for this supplier, copied from the "
        "ranking data."
    )


class SupplierSpendRankingResponse(BaseModel):
    """Aggregation response: suppliers ranked by total spend (feature 7)."""

    summary: str = _SUMMARY_FIELD
    suppliers: list[SupplierSpendRow] = Field(
        default_factory=list,
        description="Suppliers in ranked order (highest spend first), copied "
        "from the ranking data. Do not reorder, add, or drop suppliers.",
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD


class SupplierPOValueRow(BaseModel):
    """One supplier in a PO-value ranking (P6 aggregation).

    Note supplier_ID, not supplier_number: purchase orders do not carry a
    SupplierNumber (the PO header has SupplierId and Supplier only), so
    this ranking cannot reuse SupplierSpendRow. Validated against the
    ranking the executor produced — the LLM must not invent or reorder
    suppliers."""

    supplier_name: str = Field(description="The supplier's display name.")
    supplier_id: int = Field(
        description="The supplier's SupplierId (numeric key). Must appear "
        "in the ranking data."
    )
    total_ordered: float = Field(
        description="Total committed PO value for this supplier, copied "
        "exactly from the ranking data. Never recompute."
    )
    po_count: int = Field(
        description="Number of purchase orders for this supplier, copied "
        "from the ranking data."
    )


class SupplierPOValueRankingResponse(BaseModel):
    """Aggregation response: suppliers ranked by committed PO value."""

    summary: str = _SUMMARY_FIELD
    suppliers: list[SupplierPOValueRow] = Field(
        default_factory=list,
        description="Suppliers in ranked order (highest committed value "
        "first), copied from the ranking data. Do not reorder, add, or "
        "drop suppliers.",
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD


class POStatusRow(BaseModel):
    """One status bucket in a PO status breakdown (P6 aggregation)."""

    status: str = Field(
        description="The StatusCode, copied exactly (e.g. 'OPEN', "
        "'CLOSED FOR RECEIVING'). Note the pod uses spaces, not "
        "underscores."
    )
    po_count: int = Field(
        description="Number of POs in this status, copied from the data."
    )
    total_ordered: float = Field(
        description="Total committed value in this status, copied exactly. "
        "Never recompute."
    )


class POStatusBreakdownResponse(BaseModel):
    """Aggregation response: PO count and value broken down by status."""

    summary: str = _SUMMARY_FIELD
    total_pos: int = Field(
        description="Grand count across all statuses, copied from the data."
    )
    total_ordered: float = Field(
        description="Grand total value across all statuses, copied exactly."
    )
    statuses: list[POStatusRow] = Field(
        default_factory=list,
        description="One row per status, value descending, copied from the "
        "data. Do not reorder, add, drop, or merge statuses.",
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD


class OpenPOSummaryResponse(BaseModel):
    """Aggregation response: committed spend and open-PO count (P6)."""

    summary: str = _SUMMARY_FIELD
    po_count: int = Field(
        description="Number of open POs, copied from the data."
    )
    total_ordered: float = Field(
        description="Total committed value across the open POs, copied "
        "exactly. Never recompute."
    )
    supplier_count: int = Field(
        description="Number of distinct suppliers with an open PO, copied "
        "from the data."
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD

class ExposureRankingRow(BaseModel):
    """One account in an exposure ranking."""

    account_id: int = Field(description="The account's AccountId.")
    account_number: str = Field(description="The account's AccountNumber.")
    customer_name: str = Field(description="The customer's display name.")
    open_receivables: float | None = Field(default=None, description="Total open receivables for the account.")
    transactions_due: float | None = Field(default=None, description="Total transactions due for the account.")


class ExposureRankingResponse(BaseModel):
    """Aggregation response: customer accounts ranked by outstanding exposure."""

    summary: str = _SUMMARY_FIELD
    accounts: list[ExposureRankingRow] = Field(
        default_factory=list,
        description="Accounts in ranked order (highest exposure first), copied "
        "from the ranking data. Do not reorder, add, or drop.",
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD

class ReceiptMethodDistributionRow(BaseModel):
    """One receipt method bucket in a distribution."""

    receipt_method: str = Field(description="The receipt method (e.g. Lockbox, Check).")
    receipt_count: int = Field(description="Number of receipts using this method.")
    total_amount: float = Field(description="Total amount for this method.")


class ReceiptMethodDistributionResponse(BaseModel):
    """Aggregation response: receipts grouped by receipt method."""

    summary: str = _SUMMARY_FIELD
    total_receipts: int = Field(description="Total number of receipts examined.")
    total_amount: float = Field(description="Total amount across all receipts.")
    methods: list[ReceiptMethodDistributionRow] = Field(
        default_factory=list,
        description="One row per method, sorted by total_amount descending.",
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD
       
class CountResponse(BaseModel):
    """Count response: the size of a (possibly filtered) entity set.

    Built deterministically, without the LLM — the count is already in the
    executor output / truncation block, so there is nothing to synthesize
    and no risk of an invented number. Phase 10."""

    summary: str = Field(
        description="One-sentence statement of the count."
    )
    entity: str = Field(description="The entity counted, e.g. 'Supplier'.")
    count: int | None = Field(
        description="The exact count, or null when the true total is not "
        "known (a client-side filter exceeded the examine cap)."
    )
    count_is_exact: bool = Field(
        description="True when count is the exact total; False when it is a "
        "lower bound (the true total was not fully retrieved)."
    )
    truncation_notes: list[str] = Field(
        default_factory=list,
        description="Unused for counts (the count itself carries the total); "
        "present for formatter compatibility with other responses.",
    )


class ComparisonResponse(BaseModel):
    """Comparison response: invoiced vs ordered (P6c).

    Built deterministically, without the LLM — the comparison tool has
    already fetched both sides, joined them, and computed the totals and
    the difference. There is nothing to synthesize and no risk of an
    invented number, so this mirrors CountResponse rather than the
    LLM-driven aggregation path. The 'summary' is templated from the
    tool's own numbers; the structured fields carry those numbers through
    unchanged."""

    summary: str = Field(
        description="Plain-language statement of the comparison."
    )
    shape: str = Field(
        description="The comparison shape tag, e.g. 'po_invoiced_vs_ordered'."
    )
    truncation_notes: list[str] = Field(
        default_factory=list,
        description="Any truncation note carried from the tool.",
    )


# ─────────────────────────────────────────────────────────────────────
# Count and comparison response builders
#
# Both are deterministic — no LLM. The count query and the comparison
# tool have already produced the number(s); these functions template
# them into prose and never recompute a figure. Kept with their response
# schemas above rather than in the orchestrator, same as the lifecycle
# and supplier builders live with theirs.
# ─────────────────────────────────────────────────────────────────────


def _build_count_response(
    outputs: dict[str, list[dict]],
    target_entity: str,
    truncation_by_step: dict[str, dict] | None,
) -> CountResponse:
    """Build a count response deterministically — no LLM (Phase 10).

    Count source, in order of preference:
      1. A truncation entry's total_available (authoritative; e.g. the
         unfiltered totalResults count, or the exact filtered total).
      2. If truncation says total_available is null, the true count is not
         known — a client-side filter exceeded the examine cap. Report the
         examined count as a lower bound.
      3. No truncation block: every matching record was returned, so the
         length of the single output bucket is the exact count.
    """
    # The count query runs one fetch → one output bucket.
    bucket = next(iter(outputs.values()), [])
    examined = len(bucket)

    total_available = None
    examined_note = examined
    if truncation_by_step:
        entry = next(iter(truncation_by_step.values()), {})
        total_available = entry.get("total_available")
        examined_note = entry.get("examined", examined)

    if total_available is not None:
        count = int(total_available)
        exact = True
        summary = f"There are {count} {target_entity.lower()}s."
    elif truncation_by_step:
        # total known-unknown: filter exceeded the cap. Lower bound only.
        count = int(examined_note)
        exact = False
        summary = (
            f"There are more than {count} {target_entity.lower()}s — the "
            f"exact total was not retrieved (more than the examine cap "
            f"matched)."
        )
    else:
        # No truncation: complete set returned.
        count = examined
        exact = True
        summary = f"There are {count} {target_entity.lower()}s."

    return CountResponse(
        summary=summary,
        entity=target_entity,
        count=count,
        count_is_exact=exact,
    )


# ─────────────────────────────────────────────────────────────────────
# Comparison responses (P6c) — deterministic, no LLM
# ─────────────────────────────────────────────────────────────────────
#
# The comparison tool has already done the fetch, join, and arithmetic.
# These builders template its numbers into prose; they never recompute a
# figure. Mirrors _build_count_response. The over/under-invoiced phrasing
# is neutral and factual (an over-invoice is real data — tax, freight,
# variance — not an error), matching the tool's own stance.


def _direction_phrase(difference: float) -> str:
    """Neutral over/under/fully phrasing for a signed difference."""
    if difference > 0:
        return f"over-invoiced by {difference:,.2f}"
    if difference < 0:
        return f"under-invoiced by {abs(difference):,.2f}"
    return "fully invoiced (invoiced equals ordered)"


def _summarize_po_comparison(data: dict) -> str:
    if not data.get("found"):
        return (
            f"No purchase order {data.get('order_number')!r} was found, so "
            f"there is nothing to compare."
        )
    ordered = data.get("ordered", 0.0)
    invoiced = data.get("invoiced", 0.0)
    diff = data.get("difference", 0.0)
    n = data.get("invoice_count", 0)
    supplier = data.get("supplier")
    inv_word = "invoice" if n == 1 else "invoices"
    return (
        f"PO {data.get('order_number')} ({supplier}): ordered {ordered:,.2f}, "
        f"invoiced {invoiced:,.2f} across {n} {inv_word} — "
        f"{_direction_phrase(diff)}."
    )


def _summarize_supplier_comparison(data: dict) -> str:
    if not data.get("found"):
        return (
            f"No supplier matching {data.get('supplier_name')!r} was found, "
            f"so there is nothing to compare."
        )
    if data.get("ambiguous"):
        candidates = data.get("candidates", [])
        shown = ", ".join(str(c) for c in candidates)
        return (
            f"{data.get('supplier_name')!r} matches several suppliers "
            f"({shown}). Name one exactly to compare its orders to invoices."
        )
    ordered = data.get("total_ordered", 0.0)
    invoiced = data.get("total_invoiced", 0.0)
    diff = data.get("total_difference", 0.0)
    po_count = data.get("po_count", 0)
    unmatched = data.get("unmatched_invoice_count", 0)
    parts = [
        f"{data.get('supplier')}: across {po_count} purchase order(s), "
        f"ordered {ordered:,.2f} and PO-matched invoiced {invoiced:,.2f} — "
        f"{_direction_phrase(diff)}."
    ]
    if unmatched:
        parts.append(
            f"{unmatched:,} of this supplier's invoices were not linked to a "
            f"PO and are excluded from the comparison."
        )
    return " ".join(parts)


def _summarize_top_suppliers_comparison(data: dict) -> str:
    suppliers = data.get("suppliers", [])
    returned = data.get("returned", len(suppliers))
    if not suppliers:
        return "No suppliers were found to compare."
    lines = [
        f"Invoiced vs ordered for the top {returned} supplier(s) by PO value:"
    ]
    for s in suppliers:
        ordered = s.get("total_ordered", 0.0)
        invoiced = s.get("total_invoiced", 0.0)
        diff = s.get("total_difference", 0.0)
        unmatched = s.get("unmatched_invoice_count", 0)
        line = (
            f"- {s.get('supplier')}: ordered {ordered:,.2f}, PO-matched "
            f"invoiced {invoiced:,.2f} — {_direction_phrase(diff)}"
        )
        if unmatched:
            line += f" ({unmatched:,} non-PO invoices excluded)"
        line += "."
        lines.append(line)
    return "\n".join(lines)


# shape tag -> builder. One row per shape, like AGGREGATION_SCHEMAS: a new
# comparison tool is a new row here, not another branch in the routing.
_COMPARISON_BUILDERS = {
    "po_invoiced_vs_ordered": _summarize_po_comparison,
    "supplier_invoiced_vs_ordered": _summarize_supplier_comparison,
    "top_suppliers_invoiced_vs_ordered": _summarize_top_suppliers_comparison,
}


def _build_comparison_response(
    outputs: dict[str, list[dict]], shape: str
) -> ComparisonResponse:
    """Build a comparison response deterministically from the tool's data.

    The comparison tool result sits under the 'comparison' bucket as a
    single object. The builder for its shape templates the summary; no LLM
    and no recomputation.
    """
    data = outputs["comparison"][0]
    builder = _COMPARISON_BUILDERS.get(shape)
    if builder is None:
        raise UnsupportedEntityError(
            f"No synthesizer builder for comparison shape {shape!r}. "
            f"Supported: {sorted(_COMPARISON_BUILDERS)}."
        )
    truncation_notes = (
        ["Some results were truncated at the page cap."]
        if data.get("truncated")
        else []
    )
    return ComparisonResponse(
        summary=builder(data),
        shape=shape,
        truncation_notes=truncation_notes,
    )
