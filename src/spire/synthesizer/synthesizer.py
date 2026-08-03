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
# modules and scripts/display_formatters.py import from this path; a
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
from spire.synthesizer.p2p import (  # noqa: F401
    build_supplier_records,
    plain_supplier_bucket,
)
from spire.synthesizer.prompts import (  # noqa: F401
    _SYSTEM_PROMPT_BY_ENTITY,
    _SYSTEM_PROMPT_PREAMBLE,
    _build_synthesis_prompt,
    _build_system_prompt,
    _round_floats,
)
from spire.synthesizer.validation import (  # noqa: F401
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
    Left alone deliberately: changing it is a user-visible format change
    and belongs with the counts-line work, not smuggled in here.

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
            f"{examined} examined for filtering."
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
        # Summary-only, like the supplier-record path: the model writes
        # the prose and code assembles every value. See
        # POLifecycleSummaryResponse for why.
        if llm is None:
            from spire.config import build_llm

            llm = build_llm(_TEMPERATURE)
        summary_llm = llm.with_structured_output(
            POLifecycleSummaryResponse, include_raw=True
        )
        result = summary_llm.invoke(
            [
                ("system", _build_system_prompt("POLifecycle")),
                (
                    "human",
                    _build_synthesis_prompt(
                        outputs, truncation_by_step, metadata_by_step
                    ),
                ),
            ]
        )
        if isinstance(result, dict) and "parsed" in result:
            from spire.config import log_usage

            log_usage(result.get("raw"), stage="synthesize")
            parsed = result["parsed"]
        else:
            parsed = result
        if isinstance(parsed, dict):
            parsed = POLifecycleSummaryResponse(**parsed)
        return build_lifecycle_response(
            lifecycle_record, parsed.summary, parsed.truncation_notes
        )

    if shape is not None:
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
                )
            ),
            suppliers=build_supplier_records(rows),
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
                            labels={
                                "TransactionNumber": "Transaction",
                                "EnteredAmount": "Amount",
                                "InvoiceCurrencyCode": "Currency",
                                "TransactionDate": "Date",
                                "BillToCustomerName": "Customer",
                                "InvoiceStatus": "Status",
                            },
                        )
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
                        rows, children
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
                        labels={
                            "ReceiptNumber": "Receipt",
                            "ReceiptDate": "Date",
                            "ReceiptMethod": "Method",
                            "CustomerSite": "Site",
                            "CustomerAccountNumber": "Account",
                        },
                    )
                ),
                receipts=build_standard_receipt_records(rows),
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

