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




def synthesize_response(
    outputs: dict[str, list[dict]],
    target_entity: str,
    llm: Any | None = None,
    truncation_by_step: dict[str, dict] | None = None,
    count_only: bool = False,
    metadata_by_step: dict[str, dict] | None = None,
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

    # Plain supplier list: build the records here and ask the LLM only for
    # the summary. See build_supplier_records for why. Placed with the
    # other pre-LLM short-circuits (count_only, comparison, aggregation)
    # because it is the same idea: when the data already determines the
    # answer, do not pay a language model to restate it.
    supplier_bucket = (
        plain_supplier_bucket(outputs) if target_entity == "Supplier" else None
    )
    if supplier_bucket is not None:
        if llm is None:
            from spire.config import build_llm

            llm = build_llm(_TEMPERATURE)
        # include_raw so the call lands in the token log like every
        # other stage. Without it this call is invisible in the usage
        # totals — and those totals are the evidence base for the
        # parse-cost work ("parse is 65% of consumption"). A synthesize
        # call missing from the ledger would quietly flatter it.
        summary_llm = llm.with_structured_output(
            SupplierSummaryResponse, include_raw=True
        )
        result = summary_llm.invoke(
            [
                ("system", _build_system_prompt("SupplierSummaryOnly")),
                (
                    "human",
                    _build_synthesis_prompt(
                        outputs, truncation_by_step, metadata_by_step
                    ),
                ),
            ]
        )
        # Real LLM returns {"raw", "parsed", ...}; unit-test mocks return
        # the bare model or a dict. Handle both, as the main path does.
        if isinstance(result, dict) and "parsed" in result:
            from spire.config import log_usage

            log_usage(result.get("raw"), stage="synthesize")
            summary = result["parsed"]
        else:
            summary = result
        if isinstance(summary, dict):
            summary = SupplierSummaryResponse(**summary)
        return SupplierResponse(
            summary=summary.summary,
            suppliers=build_supplier_records(outputs[supplier_bucket]),
            truncation_notes=summary.truncation_notes,
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

