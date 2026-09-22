"""Aggregation, count and comparison response schemas.

These three families are selected by a SHAPE TAG the tool stamps on its
result, not by target_entity — an aggregation or comparison Intent
carries no target entity at all, only an aggregate or comparison block.
CountResponse and ComparisonResponse are built deterministically from the
tool's own numbers with no LLM involved; the ranking schemas are the ones
an LLM actually narrates.

As of 2026-08-04 that last sentence is being retired. The six aggregation
shapes now have local builders at the foot of this module — see
"Local aggregation response builders" — and the model is no longer asked
to retype a ranking it did not compute.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from spire.synthesizer.errors import UnsupportedEntityError
from spire.synthesizer.models_common import _SUMMARY_FIELD, _TRUNCATION_FIELD
from spire.synthesizer.ranking_summary import local_aggregation_summary


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


class InvoiceAmountRow(BaseModel):
    """One invoice in an amount ranking (top-N invoices by InvoiceAmount).

    Unlike the supplier rankings, each row is an individual INVOICE, not a
    grouped total — there is no per-row count. Validated against the ranking
    the executor produced; the LLM must not invent or reorder invoices."""

    invoice_number: str = Field(
        description="The invoice's human-readable InvoiceNumber, copied from "
        "the ranking data."
    )
    supplier: str = Field(
        description="The supplier's display name, copied from the data."
    )
    supplier_number: str = Field(
        description="The supplier's SupplierNumber, copied from the data."
    )
    invoice_amount: float = Field(
        description="The invoice's InvoiceAmount, copied exactly from the "
        "ranking data. Never recompute."
    )
    invoice_date: str = Field(
        default="",
        description="The invoice's InvoiceDate (ISO), copied from the data.",
    )


class InvoiceAmountRankingResponse(BaseModel):
    """Aggregation response: individual invoices ranked by amount, highest
    first (server-side orderBy=InvoiceAmount:desc)."""

    summary: str = _SUMMARY_FIELD
    invoices: list[InvoiceAmountRow] = Field(
        default_factory=list,
        description="Invoices in ranked order (highest amount first), copied "
        "from the ranking data. Do not reorder, add, or drop invoices.",
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
    the difference. There is nothing left to synthesize: the summary is
    templated from the tool's own numbers; the structured fields carry
    those numbers through unchanged."""

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


def _filtered_bucket_pair(
    outputs: dict[str, list[dict]],
) -> tuple[str, str] | None:
    """Return (source_bucket, matched_bucket) for a source+filtered pair.

    An edge-traversal filter (has_classification, has_open_PO,
    has_site_in_bu, has_invoice_over_amount, has_no_recent_invoices,
    ...) runs as two steps: fetch the SOURCE rows, then keep the ones
    that match, via filter_source_when_nonempty. The executor names
    the matched bucket ``{source}_{suffix}`` — the source bucket's
    name is a strict prefix followed by an underscore. Crucially, the
    matched bucket carries SOURCE rows (the step's contract is to emit
    the source items whose per-iteration call returned something), so
    both buckets share the source entity's identifier field.

    Both conditions matter. The name check alone would match
    ``po`` + ``po_lines`` (a parent and a child — different entity
    types with different id fields). The shared-key check alone would
    match any two buckets of the same entity type that are NOT a
    filtered pair. Requiring both is what makes the guess safe.

    Returns None for any other shape, in the same conservative spirit
    as p2p._filtered_supplier_list: a wrong guess here would route a
    non-filtered count through the filtered branch and report a wrong
    number, which is the class this helper exists to close.
    """
    if len(outputs) != 2:
        return None
    names = list(outputs.keys())
    a, b = names
    if b.startswith(a + "_"):
        source, matched = a, b
    elif a.startswith(b + "_"):
        source, matched = b, a
    else:
        return None

    src_rows = outputs[source]
    mch_rows = outputs[matched]
    if not src_rows or not isinstance(src_rows[0], dict):
        return None
    src_id_keys = {k for k in src_rows[0] if k.endswith("Id")}
    if not src_id_keys:
        return None
    # The matched bucket may be EMPTY — a valid "0 matches" answer.
    # Only require the id-key overlap when it has rows to check.
    if mch_rows:
        if not isinstance(mch_rows[0], dict):
            return None
        if not (src_id_keys & set(mch_rows[0].keys())):
            return None
    return source, matched


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
    # F-010: a filtered count has two buckets, not one. The source
    # bucket (e.g. "suppliers") is the sampled SOURCE the edge-traversal
    # step iterated over; the matched bucket (e.g.
    # "suppliers_has_classification") is what the filter actually kept.
    # The count the user asked for is the size of the MATCHED bucket.
    #
    # Before this branch, the function read next(iter(outputs.values()))
    # — the source bucket — and reported its total_available (the pod-wide
    # count) as the filtered answer. "count of suppliers with
    # classification Minority Owned" answered "There are 593 suppliers."
    # over a filter that kept exactly 1. That is the wrong number stated
    # with confidence, which is the failure class this count path exists
    # to remove.
    filtered = _filtered_bucket_pair(outputs)
    if filtered is not None:
        source_bucket, matched_bucket = filtered
        matched_count = len(outputs[matched_bucket])
        examined = len(outputs[source_bucket])

        # Source total comes from the SOURCE bucket's truncation entry,
        # which the executor populated for the sampled fetch.
        source_total: int | None = None
        if truncation_by_step:
            source_entry = truncation_by_step.get(source_bucket) or {}
            source_total = source_entry.get("total_available")

        singular = target_entity.lower()
        plural = singular + "s"
        word = singular if matched_count == 1 else plural

        if source_total is not None and source_total > examined:
            # Source was capped: the matched count is of the examined
            # sample, and the source total is CONTEXT, not the answer.
            exact = False
            summary = (
                f"{matched_count} {word} match the filter "
                f"(examined {examined} of {source_total:,})."
            )
        elif source_total is None and truncation_by_step:
            # Source total unknown (composite filter cap). The matched
            # count is exact only over what was examined.
            exact = False
            summary = (
                f"{matched_count} {word} match the filter "
                f"(the source fetch was capped; the true matching "
                f"count may be higher)."
            )
        else:
            # Source was complete: the matched set IS the answer.
            exact = True
            summary = f"{matched_count} {word} match the filter."

        return CountResponse(
            summary=summary,
            entity=target_entity,
            count=matched_count,
            count_is_exact=exact,
        )

    # Unfiltered count: the query runs one fetch → one output bucket.
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


# ─────────────────────────────────────────────────────────────────────
# Local aggregation response builders — deterministic, no LLM
# ─────────────────────────────────────────────────────────────────────
#
# Same rule as the count and comparison builders above, applied to the
# six aggregation shapes: the tool has already done the grouping, the
# summing and the sort, so there is nothing left to synthesize. Until
# 2026-08-04 these shapes were the exception — the ranking was handed to
# the model and the model retyped it field by field into the schema.
#
# Measured cost of that, on "top 5 suppliers by spend":
#
#     synthesize   in=1004  out=1880
#
# 1,880 output tokens to reproduce five rows the executor already held,
# plus six sentences of prose of which two restated the table heading and
# one announced that date_from and date_to were null.
#
# WHY THE FIELD NAMES DO NOT LINE UP
# The tools and these schemas were written at different times and by
# different hands. The tool emits `supplier`; SupplierSpendRow declares
# `supplier_name`. Same value, two spellings — which is precisely why the
# mapping belongs in code and not in a prompt: the model was inferring
# this correspondence on every single call, and an inference that
# succeeds 99 times in 100 is a silent wrong answer on the hundredth.
#
# WHERE THE SUMMARY COMES FROM
# ranking_summary.local_aggregation_summary. Kept in its own module
# because summary rules and record mapping are different jobs; these
# builders are the only caller.
#
# TRUNCATION NOTES ARE DELIBERATELY EMPTY
# The truncation sentence is part of the summary text, not the
# truncation_notes list, so it prints exactly once. The LLM path fills
# both and the display formatter prints both, so filling both here would
# duplicate the sentence. Verify this on the first end-to-end run — if
# the formatter turns out to print truncation_notes somewhere the summary
# does not reach, move the sentence rather than duplicating it.


def _f(value: object, default: float = 0.0) -> float:
    """Coerce a measure to float, defaulting when absent or non-numeric.

    The tools already guard their arithmetic this way (a non-numeric
    Ordered contributes 0 but still counts), so this mirrors a rule that
    is already established rather than inventing a new one.
    """
    return float(value) if isinstance(value, (int, float)) else default


def _i(value: object, default: int = 0) -> int:
    """Coerce a count to int, defaulting when absent or non-numeric."""
    return int(value) if isinstance(value, (int, float)) else default


def _s(value: object, default: str = "") -> str:
    """Coerce a label to str, defaulting when absent."""
    return str(value) if value not in (None, "") else default


def _summary_text(bucket: dict) -> str:
    """The local summary, joined for the response's single summary field.

    An empty list joins to an empty string, which is correct: a summary
    with nothing truthful to say prints nothing rather than padding.
    """
    return "\n".join(local_aggregation_summary(bucket) or [])


def build_supplier_spend_ranking(bucket: dict) -> SupplierSpendRankingResponse:
    """supplier_spend_ranking -> response, no LLM."""
    return SupplierSpendRankingResponse(
        summary=_summary_text(bucket),
        suppliers=[
            SupplierSpendRow(
                supplier_name=_s(r.get("supplier")),
                supplier_number=_s(r.get("supplier_number")),
                total_spend=_f(r.get("total_spend")),
                invoice_count=_i(r.get("invoice_count")),
            )
            for r in bucket.get("rows") or []
        ],
        truncation_notes=[],
    )


def build_invoice_amount_ranking(bucket: dict) -> InvoiceAmountRankingResponse:
    """invoice_amount_ranking -> response, no LLM.

    Rows are individual invoice dicts (the tool's projected fields), so the
    row keys are the raw invoice field names (InvoiceNumber, InvoiceAmount,
    ...), not the snake_case group keys the supplier rankings use.
    """
    return InvoiceAmountRankingResponse(
        summary=_summary_text(bucket),
        invoices=[
            InvoiceAmountRow(
                invoice_number=_s(r.get("InvoiceNumber")),
                supplier=_s(r.get("Supplier")),
                supplier_number=_s(r.get("SupplierNumber")),
                invoice_amount=_f(r.get("InvoiceAmount")),
                invoice_date=_s(r.get("InvoiceDate")),
            )
            for r in bucket.get("rows") or []
        ],
        truncation_notes=[],
    )


def build_supplier_po_value_ranking(
    bucket: dict,
) -> SupplierPOValueRankingResponse:
    """supplier_po_value_ranking -> response, no LLM.

    supplier_id, not supplier_number: a PO header carries SupplierId only.
    """
    return SupplierPOValueRankingResponse(
        summary=_summary_text(bucket),
        suppliers=[
            SupplierPOValueRow(
                supplier_name=_s(r.get("supplier")),
                supplier_id=_i(r.get("supplier_id")),
                total_ordered=_f(r.get("total_ordered")),
                po_count=_i(r.get("po_count")),
            )
            for r in bucket.get("rows") or []
        ],
        truncation_notes=[],
    )


def build_po_status_breakdown(bucket: dict) -> POStatusBreakdownResponse:
    """po_status_breakdown -> response, no LLM."""
    return POStatusBreakdownResponse(
        summary=_summary_text(bucket),
        total_pos=_i(bucket.get("total_pos")),
        total_ordered=_f(bucket.get("total_ordered")),
        statuses=[
            POStatusRow(
                status=_s(r.get("status"), "(unknown)"),
                po_count=_i(r.get("po_count")),
                total_ordered=_f(r.get("total_ordered")),
            )
            for r in bucket.get("rows") or []
        ],
        truncation_notes=[],
    )


def build_open_po_summary(bucket: dict) -> OpenPOSummaryResponse:
    """open_po_summary -> response, no LLM.

    The only shape with no rows. Its three scalars ARE the answer, so
    unlike every other shape there is no table beneath the summary to
    carry the figures.
    """
    return OpenPOSummaryResponse(
        summary=_summary_text(bucket),
        po_count=_i(bucket.get("po_count")),
        total_ordered=_f(bucket.get("total_ordered")),
        supplier_count=_i(bucket.get("supplier_count")),
        truncation_notes=[],
    )


def build_exposure_ranking(bucket: dict) -> ExposureRankingResponse:
    """exposure_ranking -> response, no LLM.

    open_receivables and transactions_due stay None when the pod omits
    them — the row model allows null for both, and a null exposure is a
    fact about the account rather than a zero. account_id, account_number
    and customer_name do NOT allow null, so a row missing any of them
    raises here.

    That is deliberate and is a behaviour change worth watching: on the
    LLM path the model would fill an absent value with something
    plausible and the response would validate. Loud is better, but the
    first time this raises it will look like a regression, and it is not
    one — it is a pod row that was always malformed becoming visible.
    """
    return ExposureRankingResponse(
        summary=_summary_text(bucket),
        accounts=[
            ExposureRankingRow(
                account_id=r.get("account_id"),
                account_number=_s(r.get("account_number")),
                customer_name=_s(r.get("customer_name")),
                open_receivables=r.get("open_receivables"),
                transactions_due=r.get("transactions_due"),
            )
            for r in bucket.get("rows") or []
        ],
        truncation_notes=[],
    )


def build_receipt_method_distribution(
    bucket: dict,
) -> ReceiptMethodDistributionResponse:
    """receipt_method_distribution -> response, no LLM.

    total_amount appears twice with different meanings — once per row (the
    method's total) and once at the top level (the grand total across all
    methods). Reading the wrong one gives a share of itself.
    """
    return ReceiptMethodDistributionResponse(
        summary=_summary_text(bucket),
        total_receipts=_i(bucket.get("total_receipts")),
        total_amount=_f(bucket.get("total_amount")),
        methods=[
            ReceiptMethodDistributionRow(
                receipt_method=_s(r.get("receipt_method"), "(unknown)"),
                receipt_count=_i(r.get("receipt_count")),
                total_amount=_f(r.get("total_amount")),
            )
            for r in bucket.get("rows") or []
        ],
        truncation_notes=[],
    )


# shape tag -> builder. Same one-row-per-shape discipline as
# _COMPARISON_BUILDERS and AGGREGATION_SCHEMAS: a seventh aggregation tool
# is a new row here, not another branch in the routing.
_LOCAL_AGGREGATION_BUILDERS = {
    "supplier_spend_ranking": build_supplier_spend_ranking,
    "supplier_po_value_ranking": build_supplier_po_value_ranking,
    "po_status_breakdown": build_po_status_breakdown,
    "open_po_summary": build_open_po_summary,
    "exposure_ranking": build_exposure_ranking,
    "receipt_method_distribution": build_receipt_method_distribution,
    "invoice_amount_ranking": build_invoice_amount_ranking,
}


def build_local_aggregation_response(bucket: dict) -> BaseModel | None:
    """Build a complete aggregation response locally, or None.

    Args:
        bucket: The single dict the aggregation tool returned, as the
            executor holds it under the "aggregation" output.

    Returns:
        The populated response, or None when the shape has no local
        builder — in which case the caller must fall through to the model
        rather than treating None as an empty answer. Returning None for
        an unknown shape (instead of raising) is what keeps a newly added
        seventh aggregation tool working on the LLM path until someone
        adds its row above.
    """
    if not isinstance(bucket, dict):
        return None
    shape = bucket.get("shape")
    builder = _LOCAL_AGGREGATION_BUILDERS.get(shape) if isinstance(shape, str) else None
    return builder(bucket) if builder is not None else None
