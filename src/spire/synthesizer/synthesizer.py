"""
Response synthesizer for the KG-driven path (Architecture Option 3).

Takes the executor's output (dict[output_name, list[dict]]) and
produces a structured, validated answer for the user.

Architecture decisions locked for v1:
- LLM: Gemini 2.0 Flash via langchain-google-genai (same as runner.py)
- Output: Pydantic-typed JSON via with_structured_output, NOT free-form
  prose. Variance is bounded by the schema; row 7 of the rubric becomes
  mechanically verifiable.
- Hallucination guard: every supplier_id / supplier_number / person_id /
  invoice identifier in the response is cross-referenced against the
  executor's source data. Invented IDs raise HallucinationError loudly —
  no auto-retry, no silent acceptance.

Feature 5 (schema generalization):
- The response schema is no longer fixed to the supplier-rooted shape.
  Three sibling top-level schemas exist — one per target entity that has
  an entity-level fetcher today (Supplier, Invoice, PurchaseOrder). The
  schema is selected from intent.target_entity at synthesis time and
  bound to with_structured_output. Each schema carries its own typed
  record list and its own hallucination validator.
- A target_entity with no schema (e.g. Buyer aggregation, Contract)
  raises UnsupportedEntityError loudly. Graceful messaging for that case
  is feature 8's job, not the synthesizer's.

Companion design refs: docs/feature_roadmap.md (feature 5);
docs/design3_measurement_report.md (row 7 = no synthesizer).
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from spire.config import LLM_MAX_OUTPUT_TOKENS
from spire.diagnostics import get_logger

# Re-exported so that every existing import of these names from
# spire.synthesizer.synthesizer keeps working unchanged. Five test
# modules and spire.rendering.formatters import from this path; a
# split that moved them would turn a refactor into a diff across the
# test suite.
from spire.synthesizer.constants import (  # noqa: F401
    LIFECYCLE_SHAPE,
    _MODEL_NAME,
    _TEMPERATURE,
)
from spire.synthesizer.errors import (  # noqa: F401
    DegenerateOutputError,
    HallucinationError,
    UnsupportedEntityError,
)
from spire.synthesizer.models_common import (  # noqa: F401
    AddressInfo,
    BuyerInfo,
    _SUMMARY_FIELD,
    _TRUNCATION_FIELD,
)
from spire.synthesizer.lifecycle import (  # noqa: F401
    LIFECYCLE_SYSTEM_PROMPT,
    POLifecycleLeg,
    POLifecycleResponse,
    POLifecycleScheduleRow,
    POLifecycleSummaryResponse,
    _build_lifecycle_setup_notes,
    _lifecycle_shape,
    _validate_po_lifecycle,
    build_lifecycle_response,
    build_lifecycle_summary,
)
from spire.synthesizer.p2p import (  # noqa: F401
    AddressRecord,
    AddressResponse,
    ContactInfo,
    DistributionInfo,
    InvoiceRecord,
    InvoiceResponse,
    LineInfo,
    PurchaseOrderRecord,
    PurchaseOrderResponse,
    ScheduleInfo,
    SupplierRecord,
    SupplierResponse,
    SupplierSummaryResponse,
)
from spire.synthesizer.ar import (  # noqa: F401
    AccountCreditMemoInfo,
    AccountReceiptApplicationInfo,
    AccountReceiptInfo,
    CreditMemoListResponse,
    CreditMemoRecord,
    CustomerAccountRecord,
    CustomerAccountResponse,
    CustomerAccountTransactionInfo,
    ReceivablesInvoiceLineInfo,
    ReceivablesInvoiceRecord,
    ReceivablesInvoiceResponse,
    ReceivablesInvoiceTransactionDFFInfo,
    ReceivablesTaxLineInfo,
    StandardReceiptRecord,
    StandardReceiptResponse,
)
from spire.synthesizer.aggregation import (  # noqa: F401
    ComparisonResponse,
    CountResponse,
    ExposureRankingResponse,
    ExposureRankingRow,
    InvoiceAmountRankingResponse,
    InvoiceAmountRow,
    OpenPOSummaryResponse,
    POStatusBreakdownResponse,
    POStatusRow,
    ReceiptMethodDistributionResponse,
    ReceiptMethodDistributionRow,
    SupplierPOValueRankingResponse,
    SupplierPOValueRow,
    SupplierSpendRankingResponse,
    SupplierSpendRow,
    _build_comparison_response,
    _build_count_response,
    _direction_phrase,
    build_local_aggregation_response,
)
from spire.synthesizer.ar import (  # noqa: F401
    build_credit_memo_records,
    build_customer_account_records,
    build_invoice_dff,
    build_receivables_invoice_records,
    build_standard_receipt_records,
    plain_credit_memo_bucket,
    single_parent_shape,
)
from spire.synthesizer.local_summary import local_list_summary
from spire.planner.kg_db import _entity_level_filter_types
from spire.synthesizer.p2p import (  # noqa: F401
    build_supplier_records,
    plain_supplier_bucket,
    build_purchase_order_records,
    plain_po_bucket,
    build_invoice_records,
    plain_invoice_bucket,
    build_po_with_children,
    po_with_children_buckets,
    _filtered_supplier_list,
    _supplier_with_open_pos,
    build_suppliers_with_open_pos,
    _supplier_with_contacts,
    build_suppliers_with_contacts,
    _supplier_with_sites,
    build_suppliers_with_sites,
    _supplier_with_classifications,
    build_suppliers_with_classifications,
    build_narrowing_tip,
)
from spire.synthesizer.prompts import (  # noqa: F401
    _SYSTEM_PROMPT_BY_ENTITY,
    _SYSTEM_PROMPT_PREAMBLE,
    _build_synthesis_prompt,
    _build_system_prompt,
    _round_floats,
)
from spire.synthesizer.response_validation import (
    _collect_valid_ids,
    _is_supplier_spend_ranking,
    _raise_if_bad,
    _validate_address,
    _validate_credit_memo,
    _validate_customer_account,
    _validate_exposure_ranking,
    _validate_invoice,
    _validate_no_hallucinated_ids,
    _validate_no_ids,
    _validate_purchase_order,
    _validate_receipt_method_distribution,
    _validate_receivables_invoice,
    _validate_standard_receipt,
    _validate_supplier,
    _validate_supplier_po_value_ranking,
    _validate_supplier_spend_ranking,
    _VALIDATORS,
)


# Shape detection is the one diagnostic this module emits. It answers
# "which schema did the router pick?", which is the first question when
# a synthesized answer looks wrong. Gated by --show-synthesizer.
_log = get_logger("synthesizer")


# SynthesizedResponse. Keeping the name means supplier-path code and
# tests that import SynthesizedResponse / SupplierSummary still work.
SynthesizedResponse = SupplierResponse
SupplierSummary = SupplierRecord


# entity name -> (response schema). Only entities with a real fetcher.
SYNTHESIS_SCHEMAS: dict[str, type[BaseModel]] = {
    "Supplier": SupplierResponse,
    "Invoice": InvoiceResponse,
    "Address": AddressResponse,
    "PurchaseOrder": PurchaseOrderResponse,
    "ReceivablesInvoice": ReceivablesInvoiceResponse,
    "CustomerAccount": CustomerAccountResponse,
    "CreditMemo": CreditMemoListResponse,
    "StandardReceipt": StandardReceiptResponse,
}


# Human labels for the empty-result summary, matching the entity_label
# strings the local list branches already use ("suppliers", "purchase
# orders", …). Keeps "No <label> found" consistent with the non-empty
# wording for the same entity.
_ENTITY_LABEL: dict[str, str] = {
    "Supplier": "suppliers",
    "Invoice": "invoices",
    "Address": "addresses",
    "PurchaseOrder": "purchase orders",
    "ReceivablesInvoice": "AR invoices",
    "CustomerAccount": "customer accounts",
    "CreditMemo": "credit memos",
    "StandardReceipt": "receipts",
}


def _all_buckets_empty(outputs: dict[str, list[dict]]) -> bool:
    """True when the executor produced no rows in any bucket.

    A genuinely empty result — every bucket is an empty list, or there are
    no buckets. Used to short-circuit the "nothing found" case to a local
    response instead of paying an LLM to write "no rows found" over zero
    rows (#5).
    """
    if not outputs:
        return True
    return all(not rows for rows in outputs.values())


# F-007: AR-invoice children whose empty result deserves an acknowledgement.
#
# Each entry maps a child bucket the executor produces to the human
# phrase naming it. Populated buckets render their own content — lines
# and tax lines as indented sub-tables, DFF as a header field — so this
# only fires on an empty-but-present bucket. That is the case where the
# user asked and the answer would otherwise stay silent.
_AR_INVOICE_CHILD_PHRASES: dict[str, str] = {
    "receivables_invoice_lines": "line items",
    "receivablestaxline": "tax lines",
    "receivablesinvoicetransactiondff": "flexfield values",
}


def _empty_ar_invoice_child_notes(
    children: dict[str, list[dict]],
) -> list[str]:
    """One sentence per requested AR-invoice child that returned no rows.

    Presence of the bucket is the signal. The executor emits a bucket
    for every step the plan ran, and the plan runs a step for every
    child the parser put in the intent's include list. An empty bucket
    therefore means the user asked and there were none; an ABSENT bucket
    means the user never asked. Silence is only honest for the second
    case.

    Before this, both cases read identically: a prompt asking for tax
    lines on an untaxed invoice got an answer that never mentioned tax,
    and a prompt that never asked for tax got the same silence. The
    user could not tell "no tax lines exist" from "I didn't look".
    """
    return [
        f"This invoice has no {phrase}."
        for bucket, phrase in _AR_INVOICE_CHILD_PHRASES.items()
        if bucket in children and not children[bucket]
    ]


# F-015: buckets whose fetch was capped, for the empty-result path.
#
# The empty-bucket shortcut fires before truncation is consulted, so a
# bucket that came back empty because the fetch hit a cap narrated as
# "nothing exists" — indistinguishable from a genuinely empty source.
# The reader is told "no receipts found" when the truth is "no receipts
# found in the examined sample". This collects the capped steps so the
# shortcut can say which one it is.
def _truncated_steps(
    truncation_by_step: dict[str, dict] | None,
    metadata_by_step: dict[str, dict] | None,
) -> list[tuple[str, dict]]:
    """(output_name, entry) pairs for every step whose fetch was capped.

    Reads both sources the executor produces: `truncation_by_step` for
    the iterating and capped steps, `metadata_by_step` for the
    non-iterating ones. A bucket present in both is taken once, from the
    first source that carries `truncated=True` — the two agree in
    practice, and disagreeing is a defect this function should not
    invent a preference for.

    Returns [] when nothing was capped, which is the honest answer for a
    genuinely empty source and the branch the caller falls back to the
    plain "No {label} found" wording on.
    """
    out: list[tuple[str, dict]] = []
    seen: set[str] = set()
    for source in (truncation_by_step, metadata_by_step):
        for name, entry in (source or {}).items():
            if not isinstance(entry, dict):
                continue
            if entry.get("truncated") is not True:
                continue
            if name in seen:
                continue
            seen.add(name)
            out.append((name, entry))
    return out


def _bucket_truncated(
    bucket: str,
    truncation_by_step: dict[str, dict] | None,
    metadata_by_step: dict[str, dict] | None,
) -> bool:
    """True when THIS bucket's fetch was capped. F-012.

    A single-bucket view of _truncated_steps: same sources, same
    definition of capped (truncated is True), scoped to one output_name.
    The plain-list branches pass the result to local_list_summary so a
    capped fetch with no known total is narrated as a sample rather than
    presented as the complete answer.
    """
    return any(
        name == bucket
        for name, _ in _truncated_steps(truncation_by_step, metadata_by_step)
    )


# Aggregation responses are selected by the SHAPE TAG the tool stamps on
# its result, not by target_entity (an aggregation Intent carries an
# aggregate block instead of a target entity). The executor puts that
# result under the "aggregation" bucket. Mirrors SYNTHESIS_SCHEMAS above:
# one entry per shape, so a new aggregation tool is a new row here rather
# than another branch in the routing.

AGGREGATION_SCHEMAS: dict[str, tuple[type[BaseModel], str]] = {
    "supplier_spend_ranking": (
        SupplierSpendRankingResponse,
        "SupplierSpendRanking",
    ),
    "supplier_po_value_ranking": (
        SupplierPOValueRankingResponse,
        "SupplierPOValueRanking",
    ),
    "po_status_breakdown": (POStatusBreakdownResponse, "POStatusBreakdown"),
    "open_po_summary": (OpenPOSummaryResponse, "OpenPOSummary"),
    "exposure_ranking": (ExposureRankingResponse, "ExposureRanking"),
    "receipt_method_distribution": (ReceiptMethodDistributionResponse, "ReceiptMethodDistribution"),
    "invoice_amount_ranking": (InvoiceAmountRankingResponse, "InvoiceAmountRanking"),
}


def _aggregation_shape(outputs: dict[str, list[dict]]) -> str | None:
    """Return the shape tag of an aggregation result, or None if the
    outputs are an entity list rather than an aggregation.

    The aggregation tools each stamp their result with a 'shape'; the
    executor wraps it in a one-element list under 'aggregation'."""
    bucket = outputs.get("aggregation")
    if not bucket:
        return None
    first = bucket[0]
    if not isinstance(first, dict):
        return None
    shape = first.get("shape")
    return shape if isinstance(shape, str) else None


def _comparison_shape(outputs: dict[str, list[dict]]) -> str | None:
    """Return the shape tag of a comparison result, or None if the outputs
    are not a comparison.

    The comparison tools each stamp their result with a 'shape'; the
    executor wraps it in a one-element list under 'comparison' (the step's
    output_name). Mirrors _aggregation_shape."""
    bucket = outputs.get("comparison")
    if not bucket:
        return None
    first = bucket[0]
    if not isinstance(first, dict):
        return None
    shape = first.get("shape")
    return shape if isinstance(shape, str) else None


# ─────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────




def _local_truncation(
    bucket: str,
    rows: list[dict],
    truncation_by_step: dict[str, dict] | None,
    metadata_by_step: dict[str, dict] | None,
) -> tuple[int | None, list[str]]:
    """The authoritative total and the truncation note, from the data.

    Same source and same order of preference as _build_count_response,
    which has done this since Phase 10: the truncation entry's
    total_available is the pod's own count and is authoritative;
    metadata's total_available covers the non-iterating steps.

    Until now the entity-list path took a different route to the same
    numbers — the model read the truncation block and wrote a sentence
    about it. That is why one query announced "Showing 20" while 25 rows
    printed underneath: nothing counted anything, a model described a
    block it had been shown. Here the count is the count.

    "examined" is len(rows), not a field on the truncation entry. The
    entry carries total_available, limit_applied and truncated and
    nothing else — the first draft of this function read entry["examined"]
    and printed "None examined for filtering" to the screen. The key was
    inferred from _build_count_response's ``entry.get("examined", examined)``
    without checking the executor; the DEFAULT in that call was the clue
    that it is not always there, and it was read as evidence that it
    usually is.

    The note wording is copied from what the model was instructed to
    produce, so existing readers and the 05/07/08 prompt-set baselines
    see the same shape. "total in source" is inherited and is loose on a
    filtered query — it reads as unfiltered when the fetch was scoped.
    F-036 revised one word of that wording: "examined for filtering"
    claimed a filter had run on a fetch that applied none, which is false
    rather than merely loose. The verb is now "returned", true on both.
    The remaining "total in source" looseness is still left alone.

    Returns:
        (total_available or None, notes list)
    """
    total_available: int | None = None
    examined = len(rows)

    entry = (truncation_by_step or {}).get(bucket)
    if entry:
        total_available = entry.get("total_available")

    if total_available is None:
        meta = (metadata_by_step or {}).get(bucket) or {}
        total_available = meta.get("total_available")

    notes: list[str] = []
    if entry:
        total_text = (
            f"{total_available}" if total_available is not None else "unknown"
        )
        notes.append(
            f"{bucket}: {total_text} total in source; "
            f"{examined} returned."
        )

    return (
        int(total_available) if total_available is not None else None,
        notes,
    )


def synthesize_response(
    outputs: dict[str, list[dict]],
    target_entity: str,
    llm: Any | None = None,
    truncation_by_step: dict[str, dict] | None = None,
    count_only: bool = False,
    metadata_by_step: dict[str, dict] | None = None,
    filtered_fields: list[str] | None = None,
) -> BaseModel:
    """Turn the executor's output into a validated structured response,
    using the schema for the Intent's target_entity.

    Args:
        outputs: The dict returned by spire.executor.execute_plan.
        target_entity: The Intent's target_entity ("Supplier", "Invoice",
            or "PurchaseOrder"). Selects the response schema.
        llm: Optional pre-built LangChain LLM. Tests inject a mock;
            production passes None and a fresh ChatGoogleGenerativeAI is
            built (reads GEMINI_API_KEY from the environment).
        truncation_by_step: Optional dict from execute_plan keyed by
            output_name. When present, the LLM populates truncation_notes.
        metadata_by_step: Optional dict from execute_plan containing
            ToolResult metadata (e.g. total_available) for non-iterating
            steps. Used to provide exact totals to the LLM.
        filtered_fields: Field names the user filtered on, from the
            Intent. A local summary may describe these even when they
            are not rendered, because the reader supplied them — see
            local_list_summary.

    Returns:
        A Pydantic model — SupplierResponse, InvoiceResponse, or
        PurchaseOrderResponse depending on target_entity.

    Raises:
        UnsupportedEntityError if target_entity has no schema.
        HallucinationError if any structured ID isn't in the executor data.
        Pydantic ValidationError if the LLM output doesn't fit the schema.
        DegenerateOutputError if the LLM output is degenerate (runaway tokens, empty arrays).
        Anything raised by the LLM call propagates.
    """
    # Phase 10: a count query needs no LLM — the count is already in the
    # executor output / truncation block. Build it deterministically.
    if count_only:
        return _build_count_response(outputs, target_entity, truncation_by_step)

    # P6c: a comparison produces an invoiced-vs-ordered result, not an
    # entity list. Like aggregation it has no target_entity (the Intent
    # carried a compare block); select by the shape the tool stamped under
    # the "comparison" bucket. Built deterministically — the tool already
    # computed every number — so this returns before any LLM setup.
    comparison_shape = _comparison_shape(outputs)
    if comparison_shape is not None:
        return _build_comparison_response(outputs, comparison_shape)

    # Empty result: nothing found -> local "no results", no LLM (#5).
    #
    # Count and comparison have returned above; aggregation and lifecycle
    # below always carry a row (a ranking object, a reconciliation record),
    # so _all_buckets_empty is False for them and this does not steal their
    # path. For a plain entity target with zero rows in every bucket there
    # is nothing to synthesize — an LLM call to write "no suppliers found"
    # over an empty list is pure waste (measured out=125 on "suppliers named
    # Zzzqqx"). Build the empty response of the right type with a local
    # summary that matches the non-empty wording for the entity.
    if _all_buckets_empty(outputs) and target_entity in SYNTHESIS_SCHEMAS:
        empty_schema = SYNTHESIS_SCHEMAS[target_entity]
        label = _ENTITY_LABEL.get(target_entity, "records")

        # F-015: the empty-bucket shortcut used to fire before truncation
        # was consulted. A bucket that came back empty because the fetch
        # was capped narrated as "nothing exists" — indistinguishable to
        # the reader from a genuinely empty source. The distinction
        # matters: "no receipts found" is wrong when the truth is "no
        # receipts found in the examined sample, and the sample was
        # capped before examining all matching records".
        #
        # Local, no LLM. The signal already exists on the executor's
        # truncation / metadata maps; this reads it and says so.
        truncated = _truncated_steps(truncation_by_step, metadata_by_step)
        if truncated:
            notes: list[str] = []
            for name, entry in truncated:
                total = entry.get("total_available")
                total_text = (
                    f"{total:,}" if isinstance(total, int)
                    else "an unknown number of"
                )
                notes.append(
                    f"{name}: {total_text} total in source; the fetch was "
                    f"capped before examining all of them, so the result "
                    f"is a sample, not the whole."
                )
            # Name the source total in the summary only when the tool
            # reported one. The standard_receipts tool returns
            # total_available=None when its client-side site filter
            # exceeded the overfetch cap, so the common case is unknown;
            # say that plainly rather than inventing a figure.
            first_total = truncated[0][1].get("total_available")
            if isinstance(first_total, int):
                summary = (
                    f"No {label} found in the examined sample. The source "
                    f"holds {first_total:,} record(s); the search was "
                    f"capped before examining all of them, so more may "
                    f"match the filter."
                )
            else:
                summary = (
                    f"No {label} found in the examined sample. The search "
                    f"was capped before examining all matching records, so "
                    f"more may exist beyond the examined window."
                )
            return empty_schema(summary=summary, truncation_notes=notes)

        return empty_schema(
            summary=f"No {label} found matching the criteria.",
            truncation_notes=[],
        )

    # Feature 7: an aggregation produces a ranking, not an entity list.
    # It has no target_entity (the Intent carried an aggregate block
    # instead), so select the schema from the data shape. The executor
    # places the ranking under "aggregation" as a single object whose
    # "shape" identifies it.
    # Module 5: a PO lifecycle result is a single reconciliation record,
    # not an entity list. It roots on PurchaseOrder, which already has a
    # schema and a prompt, so it CANNOT be selected by target_entity —
    # select on the shape the tool stamped, as aggregation and comparison
    # do. Without this the record falls through to the PO-LIST schema and
    # the model quotes ids that schema never harvested, which the
    # hallucination guard then reports as invented data.
    lifecycle_record = _lifecycle_shape(outputs)

    shape = _aggregation_shape(outputs)
    _log.debug("[debug] shape = %s", shape)
    if lifecycle_record is not None:
        # No LLM: the tool already computed every value (ordered/received/
        # invoiced/paid, stage, risk, reasons, recommended_action), and the
        # response model copies them verbatim — the model's only job was the
        # summary prose. build_lifecycle_summary composes that prose locally
        # from the same fields, so the answer is reproducible and cannot
        # drift from the structured fields. Measured before this: synthesize
        # in=1654 out=737 just to restate computed values. The trade is one
        # consistent framing instead of emphasis-shifted prose; all data
        # remains in the POLifecycleResponse fields below.
        summary = build_lifecycle_summary(lifecycle_record)
        return build_lifecycle_response(lifecycle_record, summary, [])

    if shape is not None:
        # Local first: the aggregation tools have already done the
        # grouping, the summing and the sort, so for the six known shapes
        # there is nothing left to synthesize. Returns before any LLM
        # setup, exactly as the count and comparison paths do above.
        #
        # Measured on "top 5 suppliers by spend" before this branch
        # existed: synthesize in=1004 out=1880. The 1,880 output tokens
        # were the model retyping five rows the executor already held,
        # plus prose that announced date_from and date_to were null.
        #
        # None means "no local builder for this shape", NOT "no answer" —
        # a seventh aggregation tool added later falls through to the
        # schema lookup below and keeps working on the model path until
        # someone gives it a builder. Distinguishing None from an empty
        # response is the whole reason the builder returns None rather
        # than an empty model.
        local = build_local_aggregation_response(outputs["aggregation"][0])
        if local is not None:
            return local

        entry = AGGREGATION_SCHEMAS.get(shape)
        if entry is None:
            raise UnsupportedEntityError(
                f"No synthesizer schema for aggregation shape {shape!r}. "
                f"Supported: {sorted(AGGREGATION_SCHEMAS)}."
            )
        schema: type[BaseModel] = entry[0]
        prompt_key = entry[1]
    else:
        schema = SYNTHESIS_SCHEMAS.get(target_entity)
        if schema is None:
            raise UnsupportedEntityError(
                f"No synthesizer schema for target_entity={target_entity!r}. "
                f"Supported: {sorted(SYNTHESIS_SCHEMAS)}."
            )
        prompt_key = target_entity

    # Plain supplier list: no LLM at all.
    #
    # This branch used to build the records here and call the model for
    # the prose. It now builds both. The comment that stood here said the
    # right thing already — "when the data already determines the answer,
    # do not pay a language model to restate it" — and then paid one to
    # restate it, because the prose felt like the model's job.
    #
    # It was not. Measured 2026-08-02 over eight prompts, three runs each,
    # byte identical every run:
    #
    #   "Showing 20 of 426 suppliers"  while 25 rows printed below it
    #   "Some suppliers have a Taxpayer Country Code"  a column not shown
    #
    # Both are arithmetic and inventory, and len() cannot get either
    # wrong. The second is the more instructive: the model sees the whole
    # record and has no way to know which fields the renderer prints, so
    # instructing it to describe only displayed fields cannot work. It
    # failed four times. Handing the builder a field list makes the rule
    # structural — it cannot describe what it was not given.
    #
    # What is lost is real and should not be glossed. The model wrote
    # "All invoices are from EIP Inc" — a genuine observation this code
    # would only make if a supplier column happened to be uniform. The
    # local rules are cruder: uniformity, splits, counts. That trade is
    # deliberate, on the grounds that a crude true statement beats a
    # fluent one the reader cannot verify against the rows in front of
    # them.
    #
    # Filtered supplier list (edge-traversal): honest denominators, no LLM.
    #
    # QA-02. A filter like has_classification runs as two steps — fetch the
    # source suppliers (capped, e.g. 25) then keep the ones that match
    # (e.g. 2), via filter_source_when_nonempty. That leaves TWO buckets:
    # the source (examined) and the matched (`{source}_{suffix}`, shown).
    # Because there are two buckets, plain_supplier_bucket returns None and
    # the answer used to fall to the model below — which wrote "showing 2
    # of 432", framing the 2 MATCHED against the 432 pod-wide total. That
    # denominator is wrong: 2 is of the 25 EXAMINED, not of 432.
    #
    # The _local_truncation note already states the honest split ("432
    # total in source; 25 examined for filtering") — the numbers exist and
    # are correct. The defect is only that a model sentence contradicts it.
    # So build the summary here, deterministically, from the two bucket
    # sizes plus the source total: "Examined 25 of 432 suppliers. Of those
    # 25, 2 match." The count is always N-of-examined; the pod total is
    # stated as context, never as the denominator of the matched count.
    #
    # Generalises to every edge-traversal filter, since the shape (a source
    # bucket plus a `{source}_{suffix}` matched bucket) is the same for all
    # of them. Field-generic wording for now (names no classification
    # value) — the value is not threaded into this function; QA-12 layers
    # the narrowing advisory on top of this same honest sentence.
    filtered = _filtered_supplier_list(outputs) if target_entity == "Supplier" else None
    if filtered is not None:
        source_bucket, matched_bucket = filtered
        matched_rows = outputs[matched_bucket]
        examined = len(outputs[source_bucket])
        # Source total from the SOURCE bucket's truncation entry — the pod
        # count the fetch was capped against (432), not the matched count.
        source_total, notes = _local_truncation(
            source_bucket, outputs[source_bucket], truncation_by_step, metadata_by_step
        )
        shown = len(matched_rows)
        total_text = f"{source_total:,}" if source_total is not None else "an unknown number of"
        summary = (
            f"Examined {examined} of {total_text} suppliers. "
            f"Of those {examined}, {shown} match the filter."
        )
        # QA-12: this answer is a SAMPLE (examined < total), so add the
        # completeness advisory — the entity-level filters that would let
        # the reader get a full answer without the slow whole-set walk.
        # Names come from the KG (kg_entity_filter, entity_level), minus
        # by_id which is a fetch-one, not a narrowing filter.
        supplier_filters = _entity_level_filter_types().get("Supplier", set())
        tip = build_narrowing_tip(
            {ft for ft in supplier_filters if ft != "by_id"},
            source_total,
            entity_label="suppliers",
        )
        return SupplierResponse(
            summary=summary,
            suppliers=build_supplier_records(matched_rows),
            truncation_notes=notes,
            narrowing_tip=tip,
        )

    # This fires ONLY where plain_supplier_bucket returns a bucket — one
    # bucket, supplier rows, nothing to join. Anything needing a join
    # still goes to the model below, which is the "otherwise go to the
    # LLM if required" half of the rule.
    supplier_bucket = (
        plain_supplier_bucket(outputs) if target_entity == "Supplier" else None
    )
    if supplier_bucket is not None:
        rows = outputs[supplier_bucket]
        total_available, notes = _local_truncation(
            supplier_bucket, rows, truncation_by_step, metadata_by_step
        )
        return SupplierResponse(
            summary="\n".join(
                local_list_summary(
                    rows,
                    entity_label="suppliers",
                    # Exactly what build_supplier_records renders. Not
                    # the row keys: the rows carry Status,
                    # BusinessRelationship and TaxpayerCountryCode, none
                    # of which reach the screen on this path.
                    displayed_fields=["Supplier", "SupplierNumber"],
                    filtered_fields=filtered_fields,
                    total_available=total_available,
                    truncated=_bucket_truncated(
                        supplier_bucket, truncation_by_step, metadata_by_step
                    ),
                )
            ),
            suppliers=build_supplier_records(rows),
            truncation_notes=notes,
        )

    # Suppliers with their open POs (join): no LLM.
    #
    # #8. "suppliers with open purchase orders" fetches a supplier bucket and
    # a joined open-PO bucket, then shows each supplier's open-PO count and
    # buyers. plain_supplier_bucket returns None on the two-bucket shape, so
    # this used to fall to the model — which re-typed the whole table and
    # miscounted its own total (prose said 42 open POs over a table summing
    # to 43). build_suppliers_with_open_pos does the join here: every count
    # is len(group), and the total is the sum of those counts, so the number
    # is exact by construction. The denominator is honest — the open-PO
    # figure is across the EXAMINED suppliers (the sample), not the pod-wide
    # supplier total, mirroring _filtered_supplier_list.
    supplier_open_pos = (
        _supplier_with_open_pos(outputs) if target_entity == "Supplier" else None
    )
    if supplier_open_pos is not None:
        supplier_bucket, po_bucket = supplier_open_pos
        supplier_rows = outputs[supplier_bucket]
        po_rows = outputs[po_bucket]
        records = build_suppliers_with_open_pos(supplier_rows, po_rows)
        total_available, notes = _local_truncation(
            supplier_bucket, supplier_rows, truncation_by_step, metadata_by_step
        )
        examined = len(supplier_rows)
        total_open = sum(r.open_po_count or 0 for r in records)
        total_text = (
            f"{total_available:,}" if total_available is not None
            else "an unknown number of"
        )
        po_word = "open purchase order" if total_open == 1 else "open purchase orders"
        summary = (
            f"Showing {examined} of {total_text} suppliers. "
            f"These {examined} suppliers have {total_open} {po_word} between them."
        )
        supplier_filters = _entity_level_filter_types().get("Supplier", set())
        tip = build_narrowing_tip(
            {ft for ft in supplier_filters if ft != "by_id"},
            total_available,
            entity_label="suppliers",
        )
        return SupplierResponse(
            summary=summary,
            suppliers=records,
            truncation_notes=notes,
            narrowing_tip=tip,
        )

    # Suppliers with their contacts (join): no LLM.
    #
    # "contacts for Lee Supplies" (one supplier) and "contacts for suppliers
    # in US" (many) both produce a supplier bucket + a contact bucket. This
    # used to fall to the model — the multi-supplier case cost ~22k tokens
    # and the model asserted which contacts were administrative in free text.
    # Contacts now carry a stamped SupplierId (supplier_contacts tool), so
    # build_suppliers_with_contacts groups them here and reads the admin flag
    # deterministically. The summary states the contact count and names the
    # administrative contacts computed from the flag, not model prose.
    supplier_contacts = (
        _supplier_with_contacts(outputs) if target_entity == "Supplier" else None
    )
    if supplier_contacts is not None:
        supplier_bucket, contact_bucket = supplier_contacts
        supplier_rows = outputs[supplier_bucket]
        contact_rows = outputs[contact_bucket]
        records = build_suppliers_with_contacts(supplier_rows, contact_rows)
        total_available, notes = _local_truncation(
            supplier_bucket, supplier_rows, truncation_by_step, metadata_by_step
        )
        examined = len(supplier_rows)
        total_contacts = sum(len(r.contacts) for r in records)
        total_text = (
            f"{total_available:,}" if total_available is not None
            else "an unknown number of"
        )
        contact_word = "contact" if total_contacts == 1 else "contacts"
        if examined == 1:
            summary = f"{records[0].supplier_name} has {total_contacts} {contact_word}."
        else:
            summary = (
                f"Showing {examined} of {total_text} suppliers. "
                f"These {examined} suppliers have {total_contacts} {contact_word} "
                "between them."
            )
        # F-020: the administrative-contact list used to be comma-joined
        # onto this summary — a 27-name run-on today (47 when the finding
        # was recorded) that asserted `is_administrative=True` for each
        # named contact, with no way for the reader to check the claim
        # against the tables below. The flag itself is honest —
        # build_suppliers_with_contacts reads it from the pod's
        # AdministrativeContactFlag — but it was only ever shown HERE.
        #
        # It now rides on each contact row instead: formatters.py renders
        # an "Admin" column when at least one contact in the response is
        # flagged, so the property is visible where the reader can verify
        # it. The summary states only what the counts line already
        # states, and stops.
        return SupplierResponse(
            summary=summary,
            suppliers=records,
            truncation_notes=notes,
        )

    # Suppliers with their sites (join): no LLM. F-043.
    supplier_sites = (
        _supplier_with_sites(outputs) if target_entity == "Supplier" else None
    )
    if supplier_sites is not None:
        supplier_bucket, site_bucket = supplier_sites
        supplier_rows = outputs[supplier_bucket]
        site_rows = outputs[site_bucket]
        records = build_suppliers_with_sites(supplier_rows, site_rows)
        total_available, notes = _local_truncation(
            supplier_bucket, supplier_rows, truncation_by_step, metadata_by_step
        )
        examined = len(supplier_rows)
        total_sites = sum(len(r.sites) for r in records)
        total_text = (
            f"{total_available:,}" if total_available is not None
            else "an unknown number of"
        )
        site_word = "site" if total_sites == 1 else "sites"
        if examined == 1:
            summary = f"{records[0].supplier_name} has {total_sites} {site_word}."
        else:
            summary = (
                f"Showing {examined} of {total_text} suppliers. "
                f"These {examined} suppliers have {total_sites} {site_word} "
                "between them."
            )
        return SupplierResponse(
            summary=summary,
            suppliers=records,
            truncation_notes=notes,
        )

    # Suppliers with their classifications (join): no LLM. F-043.
    supplier_classifications = (
        _supplier_with_classifications(outputs)
        if target_entity == "Supplier"
        else None
    )
    if supplier_classifications is not None:
        supplier_bucket, classification_bucket = supplier_classifications
        supplier_rows = outputs[supplier_bucket]
        classification_rows = outputs[classification_bucket]
        records = build_suppliers_with_classifications(
            supplier_rows, classification_rows
        )
        total_available, notes = _local_truncation(
            supplier_bucket, supplier_rows, truncation_by_step, metadata_by_step
        )
        examined = len(supplier_rows)
        total_classifications = sum(len(r.classifications) for r in records)
        total_text = (
            f"{total_available:,}" if total_available is not None
            else "an unknown number of"
        )
        c_word = (
            "classification" if total_classifications == 1 else "classifications"
        )
        if examined == 1:
            summary = (
                f"{records[0].supplier_name} has "
                f"{total_classifications} {c_word}."
            )
        else:
            summary = (
                f"Showing {examined} of {total_text} suppliers. "
                f"These {examined} suppliers have {total_classifications} "
                f"{c_word} between them."
            )
        return SupplierResponse(
            summary=summary,
            suppliers=records,
            truncation_notes=notes,
        )

    # Plain PO list: no LLM (REC-2).
    #
    # The mirror of the plain-supplier branch above, and the reason "list
    # all purchase orders" now samples instead of refusing. Before this,
    # PurchaseOrder had no deterministic list path at all — every PO answer
    # went through the LLM, which was fine when a PO query returned one or a
    # handful of id-fetched rows, but a 25-row sample exposed two failures
    # of letting the model emit the rows: it re-typed only 15 of the 25 it
    # was handed, and its opening sentence then under-reported the match as
    # "15 of 17,408". The records are data, not judgement — so build them
    # here, and hand the summary to local_list_summary, exactly as the
    # supplier path does. No model call, so the row count cannot drift and a
    # supplierless PO cannot be mistaken for a hallucinated id.
    #
    # One bucket only (plain_po_bucket returns None otherwise): a PO query
    # that also fetched lines / schedules / distributions still needs the
    # hierarchy join and stays on the LLM path below.
    po_bucket = (
        plain_po_bucket(outputs) if target_entity == "PurchaseOrder" else None
    )
    if po_bucket is not None:
        rows = outputs[po_bucket]
        total_available, notes = _local_truncation(
            po_bucket, rows, truncation_by_step, metadata_by_step
        )
        return PurchaseOrderResponse(
            summary="\n".join(
                local_list_summary(
                    rows,
                    entity_label="purchase orders",
                    # Exactly the columns build_purchase_order_records
                    # renders on this path. The rows also carry StatusCode,
                    # SupplierId, Ordered and the WHO columns, none of which
                    # are described here unless displayed.
                    displayed_fields=["OrderNumber", "Status", "Supplier", "Buyer"],
                    filtered_fields=filtered_fields,
                    total_available=total_available,
                    truncated=_bucket_truncated(
                        po_bucket, truncation_by_step, metadata_by_step
                    ),
                )
            ),
            purchase_orders=build_purchase_order_records(rows),
            truncation_notes=notes,
        )

    # Plain invoice list: no LLM (#3).
    #
    # "invoices for supplier X" produces a single invoice bucket. It used to
    # go to the model, which re-typed all 25 rows field by field (dropping a
    # field silently was possible) plus a date-range/amount-range summary —
    # ~4k output tokens for a flat list. plain_invoice_bucket returns None on
    # any multi-bucket invoice shape (invoice + lines / tax / DFF), so those
    # are unaffected; a plain list is built here by build_invoice_records and
    # summarised by local_list_summary, consistent with the supplier and PO
    # plain-list branches. No range prose — the table carries the amounts and
    # dates, and a locally computed range is surface the sibling paths don't
    # add.
    invoice_bucket = (
        plain_invoice_bucket(outputs) if target_entity == "Invoice" else None
    )
    if invoice_bucket is not None:
        rows = outputs[invoice_bucket]
        total_available, notes = _local_truncation(
            invoice_bucket, rows, truncation_by_step, metadata_by_step
        )
        return InvoiceResponse(
            summary="\n".join(
                local_list_summary(
                    rows,
                    entity_label="invoices",
                    # Exactly the columns build_invoice_records renders. The
                    # rows also carry ApprovalStatus, PaidStatus,
                    # PurchaseOrderNumber and the WHO columns, none described
                    # here unless displayed.
                    displayed_fields=[
                        "InvoiceNumber", "InvoiceAmount", "InvoiceCurrency",
                        "InvoiceDate", "Supplier",
                    ],
                    filtered_fields=filtered_fields,
                    total_available=total_available,
                    truncated=_bucket_truncated(
                        invoice_bucket, truncation_by_step, metadata_by_step
                    ),
                )
            ),
            invoices=build_invoice_records(rows),
            truncation_notes=notes,
        )

    # PO with its children: no LLM.
    #
    # "Show PO 2144 and its lines / schedules / distributions" produces a PO
    # header bucket plus one or more child buckets. That multi-bucket shape
    # used to fall through to the LLM (plain_po_bucket handles only the single
    # bucket), which re-emitted every child row field by field and, for
    # schedules, copied the pod's raw ReceivedAmount — 0 on every row — into a
    # column beside prose that said "1 of 1 received" (AI-12). Building the
    # nested record here removes both the tokens and the contradiction: the
    # received amount is DERIVED from quantity in _build_schedule, and every
    # child id comes straight from an executor row, so the response
    # validator's child-id checks pass by construction.
    #
    # po_with_children_buckets returns None unless there is a PO header bucket
    # AND at least one child bucket, so a plain PO list (handled above) and
    # non-PO shapes are unaffected. There is no LLM summary here — the record
    # tables and the truncation notes carry the answer, consistent with the
    # other local branches.
    po_child_buckets = (
        po_with_children_buckets(outputs)
        if target_entity == "PurchaseOrder"
        else None
    )
    if po_child_buckets is not None:
        po_rows = outputs[po_child_buckets["po"]]
        total_available, notes = _local_truncation(
            po_child_buckets["po"], po_rows, truncation_by_step, metadata_by_step
        )
        return PurchaseOrderResponse(
            summary="\n".join(
                local_list_summary(
                    po_rows,
                    entity_label="purchase orders",
                    displayed_fields=["OrderNumber", "Status", "Supplier", "Buyer"],
                    filtered_fields=filtered_fields,
                    total_available=total_available,
                    truncated=_bucket_truncated(
                        po_child_buckets["po"], truncation_by_step,
                        metadata_by_step,
                    ),
                )
            ),
            purchase_orders=build_po_with_children(outputs, po_child_buckets),
            truncation_notes=notes,
        )

    # Plain credit-memo list: no LLM, same reasoning as the supplier
    # branch above, with one difference worth stating.
    #
    # On the supplier path the model was only ever writing prose —
    # build_supplier_records already existed. Here it was building the
    # RECORDS too: 25 rows re-emitted field by field from data it had
    # been handed. That is the expensive half and the one that can go
    # wrong quietly, since a record the model retypes can lose a field
    # and nothing downstream knows.
    #
    # compute_total_credit is already deterministic and already refuses
    # to sum across currencies. Its note is copied, never recomputed.
    memo_bucket = (
        plain_credit_memo_bucket(outputs) if target_entity == "CreditMemo" else None
    )
    if memo_bucket is not None:
        rows = outputs[memo_bucket]
        total_available, notes = _local_truncation(
            memo_bucket, rows, truncation_by_step, metadata_by_step
        )
        # The tool STAMPS total_credit and total_credit_note onto every
        # row, so the wrapper's scalar survives the executor unwrap.
        # Read it; do not recompute it.
        #
        # Recomputing would give the same answer today and would be a
        # second implementation of a rule that has already been got
        # wrong once — the first version summed USD, CAD, GBP and EUR
        # into "-17232.52", a figure in no currency at all. Two copies
        # is how one of them ends up weakened.
        #
        # These two fields were invisible until --show-raw-output
        # stopped truncating at six columns, in the same session. The
        # first draft of this branch recomputed for no better reason
        # than not knowing they were there.
        first = rows[0] if rows else {}
        total_credit = first.get("total_credit")
        total_note = first.get("total_credit_note")
        return CreditMemoListResponse(
            summary="\n".join(
                local_list_summary(
                    rows,
                    entity_label="credit memos",
                    # Exactly what the display renders for a memo.
                    displayed_fields=[
                        "TransactionNumber", "EnteredAmount",
                        "CreditMemoCurrency", "TransactionDate",
                        "BillToCustomerName", "CreditMemoStatus",
                    ],
                    filtered_fields=filtered_fields,
                    total_available=total_available,
                    truncated=_bucket_truncated(
                        memo_bucket, truncation_by_step, metadata_by_step
                    ),
                    # The table headers, so the summary names a column
                    # the way the column names itself one line below.
                    labels={
                        "TransactionNumber": "Transaction",
                        "EnteredAmount": "Amount",
                        "CreditMemoCurrency": "Currency",
                        "TransactionDate": "Date",
                        "BillToCustomerName": "Customer",
                        "CreditMemoStatus": "Status",
                    },
                )
            ),
            credit_memos=build_credit_memo_records(rows),
            total_credit=total_credit,
            total_credit_note=total_note,
            truncation_notes=notes,
        )

    # AR invoice with its lines: no LLM.
    #
    # First use of the single-parent shape — one parent row, any number
    # of child buckets. See single_parent_shape for why one row is what
    # makes attaching children safe, and why the marker list is three
    # fields rather than one (an AR invoice row and a credit memo row
    # both carry CustomerTransactionId).
    #
    # Lines, tax lines and DFF values are all handled. Any OTHER child
    # bucket still falls through to the model: the guard is an allowlist
    # of buckets whose key names have been observed, not a blanket
    # accept. A builder reading invented keys is how "None examined"
    # reached a user's screen.
    if target_entity == "ReceivablesInvoice":
        shape = single_parent_shape(
            outputs,
            ("CustomerTransactionId", "TransactionNumber", "InvoiceCurrencyCode"),
        )
        if shape is not None:
            parent, children = shape
            unhandled = set(children) - {
                "receivables_invoice_lines",
                "receivablestaxline",
                "receivablesinvoicetransactiondff",
            }
            if not unhandled:
                rows = outputs[parent]
                total_available, notes = _local_truncation(
                    parent, rows, truncation_by_step, metadata_by_step
                )
                return ReceivablesInvoiceResponse(
                    summary="\n".join(
                        local_list_summary(
                            rows,
                            entity_label="AR invoices",
                            displayed_fields=[
                                "TransactionNumber", "EnteredAmount",
                                "InvoiceCurrencyCode", "TransactionDate",
                                "BillToCustomerName", "InvoiceStatus",
                            ],
                            filtered_fields=filtered_fields,
                            total_available=total_available,
                            truncated=_bucket_truncated(
                                parent, truncation_by_step, metadata_by_step
                            ),
                            labels={
                                "TransactionNumber": "Transaction",
                                "EnteredAmount": "Amount",
                                "InvoiceCurrencyCode": "Currency",
                                "TransactionDate": "Date",
                                "BillToCustomerName": "Customer",
                                "InvoiceStatus": "Status",
                            },
                        )
                        # F-007: acknowledge a requested child that came
                        # back empty. Silent when nothing was asked (an
                        # absent bucket), loud when the user asked and
                        # there were none (a present, empty bucket).
                        + _empty_ar_invoice_child_notes(children)
                    ),
                    receivables_invoices=build_receivables_invoice_records(
                        rows, children
                    ),
                    truncation_notes=notes,
                )

    # Customer account, with whichever children were fetched.
    #
    # One parent row always — every customer_accounts bucket across the
    # sixteen AR prompts holds exactly one. Four possible children and
    # the query decides which arrive: transactions, credit memos,
    # receipts, applications.
    #
    # Each child bucket has its own key names and none follows from the
    # others. The applications bucket is the trap: its transaction
    # fields are ReferenceTransactionId / ReferenceTransactionNumber,
    # not TransactionId, so a builder copying the transactions pattern
    # reads two absent fields and silently writes zeroes.
    if target_entity == "CustomerAccount":
        shape = single_parent_shape(
            outputs,
            ("AccountId", "AccountNumber", "TotalOpenReceivablesForAccount"),
        )
        if shape is not None:
            parent, children = shape
            unhandled = set(children) - {
                "customer_transactions",
                "account_credit_memos",
                "account_receipts",
                "account_receipt_applications",
            }
            if not unhandled:
                rows = outputs[parent]
                total_available, notes = _local_truncation(
                    parent, rows, truncation_by_step, metadata_by_step
                )
                # Per-child authoritative totals for the inline "Showing N
                # of M" line under each child table. The tool computed each
                # child's total_available; it sits in truncation_by_step /
                # metadata_by_step keyed by the child BUCKET name, but the
                # renderer keys child tables by their display LABEL. Map
                # bucket -> label here, in one place, so the builder and
                # formatter never have to translate. Only the total is
                # taken; the child's truncation NOTE is deliberately not
                # added to truncation_notes — the inline line is the single
                # statement, and duplicating it in the footer would report
                # the same split twice. A child whose total is None (source
                # gave no count) is omitted, so nothing is claimed.
                _CHILD_BUCKET_LABELS = {
                    "customer_transactions": "transactions",
                    "account_credit_memos": "credit memos",
                    "account_receipts": "receipts",
                    "account_receipt_applications": "applications",
                }
                child_totals: dict[str, int | None] = {}
                for bucket, label in _CHILD_BUCKET_LABELS.items():
                    child_rows = children.get(bucket)
                    if not child_rows:
                        continue
                    child_total, _child_notes = _local_truncation(
                        bucket, child_rows, truncation_by_step,
                        metadata_by_step,
                    )
                    if child_total is not None:
                        child_totals[label] = child_total
                return CustomerAccountResponse(
                    summary="\n".join(
                        local_list_summary(
                            rows,
                            entity_label="customer accounts",
                            displayed_fields=[
                                "CustomerName", "AccountNumber",
                                "TotalOpenReceivablesForAccount",
                                "TotalTransactionsDueForAccount",
                            ],
                            filtered_fields=filtered_fields,
                            total_available=total_available,
                            truncated=_bucket_truncated(
                                parent, truncation_by_step, metadata_by_step
                            ),
                            labels={
                                "CustomerName": "Customer",
                                "AccountNumber": "AccountNumber",
                                "TotalOpenReceivablesForAccount":
                                    "Open Receivables",
                                "TotalTransactionsDueForAccount":
                                    "Transactions Due",
                            },
                        )
                    ),
                    customer_accounts=build_customer_account_records(
                        rows, children, child_totals
                    ),
                    truncation_notes=notes,
                )

    # Standard receipts: a top-level list, not an account child.
    #
    # Distinct from account_receipts despite sharing StandardReceiptId —
    # these rows carry CustomerName, CustomerAccountNumber and the
    # remittance bank fields, and lack State and UnappliedAmount.
    #
    # CustomerAccountNumber is displayed deliberately. The endpoints
    # reference records that "Santa Clara" spans accounts 26360 AND
    # 26370, so a receipt list that does not resolve to an account
    # number cannot be trusted.
    if target_entity == "StandardReceipt" and len(outputs) == 1:
        name, rows = next(iter(outputs.items()))
        if rows and isinstance(rows[0], dict) and "StandardReceiptId" in rows[0] \
                and "CustomerAccountNumber" in rows[0]:
            total_available, notes = _local_truncation(
                name, rows, truncation_by_step, metadata_by_step
            )
            return StandardReceiptResponse(
                summary="\n".join(
                    local_list_summary(
                        rows,
                        entity_label="receipts",
                        displayed_fields=[
                            "ReceiptNumber", "Amount", "Currency",
                            "ReceiptDate", "ReceiptMethod", "CustomerSite",
                            "CustomerAccountNumber", "Status",
                        ],
                        filtered_fields=filtered_fields,
                        total_available=total_available,
                        truncated=_bucket_truncated(
                            name, truncation_by_step, metadata_by_step
                        ),
                        labels={
                            "ReceiptNumber": "Receipt",
                            "ReceiptDate": "Date",
                            "ReceiptMethod": "Method",
                            "CustomerSite": "Site",
                            "CustomerAccountNumber": "Account",
                        },
                    )
                ),
                standard_receipts=build_standard_receipt_records(rows),
                truncation_notes=notes,
            )

    if llm is None:
        from spire.config import build_llm

        llm = build_llm(_TEMPERATURE)

    structured_llm = llm.with_structured_output(schema, include_raw=True)
    system_prompt = _build_system_prompt(prompt_key)
    # Pass metadata_by_step to the prompt builder
    user_message = _build_synthesis_prompt(outputs, truncation_by_step, metadata_by_step)

    result = structured_llm.invoke(
        [("system", system_prompt), ("human", user_message)]
    )

    # With include_raw=True the real LLM returns
    # {"raw": AIMessage, "parsed": schema, "parsing_error": ...}. Unit
    # tests inject a mock returning the bare model (or a dict); handle
    # both so token logging never breaks the mock path.
    if isinstance(result, dict) and "parsed" in result:
        from spire.config import log_usage
        from pathlib import Path
        import time

        log_usage(result.get("raw"), stage="synthesize")

        # --- Guard: degenerate synthesis (runaway / non-stop) ---
        raw = result.get("raw")
        if raw is not None:
            usage = getattr(raw, "usage_metadata", {})
            out_tokens = usage.get("output_tokens", 0)
            finish_reason = getattr(raw, "response_metadata", {}).get("finish_reason")
            if out_tokens >= int(LLM_MAX_OUTPUT_TOKENS * 0.95) and finish_reason != "stop":
                raw_text = getattr(raw, "content", "")
                ts = time.strftime("%Y%m%d_%H%M%S")
                Path("traces").mkdir(exist_ok=True)
                with open(f"traces/degenerate_synthesize_{ts}.txt", "w", encoding="utf-8") as f:
                    f.write(f"target_entity: {target_entity}\nfinish_reason: {finish_reason}\nout_tokens: {out_tokens}\n--- raw response ---\n{raw_text}\n")
                raise DegenerateOutputError(
                    f"Degenerate synthesis (finish_reason={finish_reason}, out_tokens={out_tokens})"
                )

        response = result["parsed"]
    else:
        response = result

    if isinstance(response, dict):
        response = schema(**response)

    # --- Additional check: empty child arrays despite source data ---
    # For CustomerAccount responses, check child arrays (transactions, credit_memos, receipts, applications).
    # This catches cases where the LLM generates a summary but leaves arrays empty.
    if isinstance(response, CustomerAccountResponse):
        for account in response.customer_accounts:
            # Check each child array
            if hasattr(account, "transactions") and not account.transactions:
                if outputs.get("customer_transactions"):
                    raise DegenerateOutputError(
                        f"Account {account.account_id} has non-empty 'customertransaction' bucket but 'transactions' list is empty."
                    )
            if hasattr(account, "credit_memos") and not account.credit_memos:
                if outputs.get("account_credit_memos"):
                    raise DegenerateOutputError(
                        f"Account {account.account_id} has non-empty 'accountcreditmemo' bucket but 'credit_memos' list is empty."
                    )
            if hasattr(account, "receipts") and not account.receipts:
                if outputs.get("account_receipts"):
                    raise DegenerateOutputError(
                        f"Account {account.account_id} has non-empty 'accountreceipt' bucket but 'receipts' list is empty."
                    )
            # Check applications – corrected bucket name
            if hasattr(account, "applications") and not account.applications:
                if outputs.get("account_receipt_applications"):   # was "accountreceiptapplication"
                    raise DegenerateOutputError(
                        f"Account {account.account_id} has non-empty 'account_receipt_applications' bucket but 'applications' list is empty."
                    )

    _validate_no_hallucinated_ids(response, outputs)

    # --- Post-process: round any float values in the response (defend against LLM-generated long decimals) ---
    # The LLM sometimes generates many decimal places even when the input is rounded.
    response_dict = response.model_dump()
    rounded_dict = _round_floats(response_dict)
    response = response.__class__(**rounded_dict)

    return response




