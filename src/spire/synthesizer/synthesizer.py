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
from typing import Any

from pydantic import BaseModel, Field

from spire.config import GEMINI_MODEL, GEMINI_TEMPERATURE


# ─────────────────────────────────────────────────────────────────────
# LLM configuration
# ─────────────────────────────────────────────────────────────────────

# Model and determinism come from spire.config (single source of truth).
_MODEL_NAME = GEMINI_MODEL
_TEMPERATURE = GEMINI_TEMPERATURE


# ─────────────────────────────────────────────────────────────────────
# Shared sub-models
# ─────────────────────────────────────────────────────────────────────


class BuyerInfo(BaseModel):
    """One buyer mentioned in the synthesized response.

    person_id is validated against the executor's buyers output after
    synthesis — it MUST appear there."""

    person_id: int = Field(description="The buyer's PersonId (HCM key).")
    display_name: str = Field(description="The buyer's display name.")


# ─────────────────────────────────────────────────────────────────────
# Per-entity record models
# ─────────────────────────────────────────────────────────────────────


class SupplierRecord(BaseModel):
    """One supplier in a supplier-rooted response.

    supplier_id and supplier_number are both validated against the
    executor's output. The LLM must not invent either."""

    supplier_id: int = Field(description="The supplier's SupplierId (numeric PK).")
    supplier_number: str = Field(
        description="The supplier's SupplierNumber (human-readable id)."
    )
    supplier_name: str = Field(description="The supplier's display name.")
    open_po_count: int = Field(
        description="Number of open purchase orders for this supplier "
        "in the executor's open_pos output. 0 if none."
    )
    buyers: list[BuyerInfo] = Field(
        default_factory=list,
        description="Buyers assigned to this supplier's open POs. Each "
        "buyer's person_id must appear in the executor's buyers output.",
    )


class InvoiceRecord(BaseModel):
    """One invoice in an invoice-rooted response.

    supplier_number / supplier_id are validated against the executor's
    output when present. invoice_number is free text from the source."""

    invoice_id: int = Field(description="The invoice's InvoiceId (numeric PK).")
    invoice_number: str = Field(description="The invoice's InvoiceNumber.")
    invoice_date: str = Field(description="The invoice date (ISO string).")
    invoice_amount: float = Field(description="The invoice amount.")
    invoice_currency: str = Field(
        default="", description="The invoice currency code, if present."
    )
    supplier_name: str = Field(description="The supplier's display name.")
    supplier_number: str = Field(
        description="The supplier's SupplierNumber. Must appear in the data."
    )


class PurchaseOrderRecord(BaseModel):
    """One purchase order in a PO-rooted response.

    supplier_id and buyer.person_id are validated against the executor's
    output when present."""

    po_header_id: int = Field(description="The PO's POHeaderId (numeric PK).")
    order_number: str = Field(description="The PO's OrderNumber.")
    status: str = Field(description="The PO status (e.g. OPEN, CLOSED).")
    supplier_name: str = Field(description="The supplier's display name.")
    supplier_id: int = Field(
        description="The supplier's SupplierId. Must appear in the data."
    )
    buyer: BuyerInfo | None = Field(
        default=None,
        description="The buyer assigned to this PO, if one is in the data. "
        "person_id must appear in the executor's buyers output.",
    )


# ─────────────────────────────────────────────────────────────────────
# Per-entity top-level response models
#
# Three siblings, one per target entity with an entity-level fetcher.
# Each carries summary + typed records + truncation_notes. The schema
# bound to with_structured_output is selected by target_entity.
#
# SynthesizedResponse is kept as an alias of the supplier-rooted schema
# so existing supplier-path callers/tests are unaffected.
# ─────────────────────────────────────────────────────────────────────


_TRUNCATION_FIELD = Field(
    default_factory=list,
    description="One short note per truncated step. Each note states the "
    "step's output_name, the total_available count if known, and how many "
    "records were examined. Empty when no step was truncated. Populate ONLY "
    "from the truncation block in the executor output; never invent counts.",
)

_SUMMARY_FIELD = Field(
    description="One-paragraph natural-language summary (3-5 sentences). "
    "Do not invent specifics not in the data."
)


class SupplierResponse(BaseModel):
    """Supplier-rooted synthesized response."""

    summary: str = _SUMMARY_FIELD
    suppliers: list[SupplierRecord] = Field(
        default_factory=list,
        description="One entry per supplier in the final filtered set. "
        "Empty if none passed the filters.",
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD


class InvoiceResponse(BaseModel):
    """Invoice-rooted synthesized response."""

    summary: str = _SUMMARY_FIELD
    invoices: list[InvoiceRecord] = Field(
        default_factory=list,
        description="One entry per invoice in the final set. Empty if none.",
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD


class PurchaseOrderResponse(BaseModel):
    """PurchaseOrder-rooted synthesized response."""

    summary: str = _SUMMARY_FIELD
    purchase_orders: list[PurchaseOrderRecord] = Field(
        default_factory=list,
        description="One entry per purchase order in the final set. "
        "Empty if none.",
    )
    truncation_notes: list[str] = _TRUNCATION_FIELD


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


# Backward-compatible alias: the supplier schema was the original
# SynthesizedResponse. Keeping the name means supplier-path code and
# tests that import SynthesizedResponse / SupplierSummary still work.
SynthesizedResponse = SupplierResponse
SupplierSummary = SupplierRecord


# entity name -> (response schema). Only entities with a real fetcher.
SYNTHESIS_SCHEMAS: dict[str, type[BaseModel]] = {
    "Supplier": SupplierResponse,
    "Invoice": InvoiceResponse,
    "PurchaseOrder": PurchaseOrderResponse,
}


# ─────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────


class HallucinationError(RuntimeError):
    """The LLM produced structured output containing IDs that don't
    appear in the executor's source data. The message names the
    offending IDs so the gap is actionable."""


class UnsupportedEntityError(RuntimeError):
    """The Intent's target_entity has no synthesizer schema. Loud by
    design — graceful user-facing messaging is feature 8's job."""


# ─────────────────────────────────────────────────────────────────────
# Source-data fingerprint (prompt building + validation)
# ─────────────────────────────────────────────────────────────────────


def _is_supplier_spend_ranking(outputs: dict[str, list[dict]]) -> bool:
    """True if the executor output is an aggregation ranking rather than
    an entity list. The aggregation tool returns a single object tagged
    shape='supplier_spend_ranking', which the executor places (wrapped in
    a one-element list) under the 'aggregation' bucket."""
    bucket = outputs.get("aggregation")
    if not bucket:
        return False
    first = bucket[0]
    return isinstance(first, dict) and first.get("shape") == "supplier_spend_ranking"


def _collect_valid_ids(outputs: dict[str, list[dict]]) -> dict[str, set]:
    """Walk the executor outputs and collect the IDs the response is
    allowed to mention. Bucket order doesn't matter — every bucket is
    scanned for every id field."""
    supplier_ids: set = set()
    supplier_numbers: set = set()
    person_ids: set = set()
    invoice_ids: set = set()

    for bucket in outputs.values():
        for item in bucket:
            if (sid := item.get("SupplierId")) is not None:
                supplier_ids.add(sid)
            if (snum := item.get("SupplierNumber")) is not None:
                supplier_numbers.add(snum)
            if (pid := item.get("PersonId")) is not None:
                person_ids.add(pid)
            # BuyerId on a PO equals PersonId on a Buyer record.
            if (bid := item.get("BuyerId")) is not None:
                person_ids.add(bid)
            if (iid := item.get("InvoiceId")) is not None:
                invoice_ids.add(iid)
            # Feature 7: an aggregation ranking carries its suppliers
            # nested under "rows", each with a lowercase "supplier_number".
            if isinstance(item.get("rows"), list):
                for row in item["rows"]:
                    if (rn := row.get("supplier_number")) is not None:
                        supplier_numbers.add(rn)

    return {
        "supplier_ids": supplier_ids,
        "supplier_numbers": supplier_numbers,
        "person_ids": person_ids,
        "invoice_ids": invoice_ids,
    }


# ─────────────────────────────────────────────────────────────────────
# Prompt building
# ─────────────────────────────────────────────────────────────────────


_SYSTEM_PROMPT_PREAMBLE = (
    "You are a response synthesizer for an Oracle Fusion Cloud query "
    "assistant. You are given the structured output of a deterministic "
    "data-fetch pipeline (a dict of named result buckets). Produce a "
    "clear, concise answer of what the data shows.\n\n"
    "Rules you MUST follow for every response:\n"
    "- Only reference IDs (SupplierId, SupplierNumber, PersonId/BuyerId, "
    "InvoiceId) that appear in the data given to you. Do NOT invent IDs.\n"
    "- Do not add details not in the data (invented addresses, amounts, "
    "dates, emails).\n"
    "- Keep the summary to 3-5 sentences. Plain English. No marketing "
    "language.\n"
    "- If the final set is empty, say so plainly and return an empty "
    "records list.\n"
    "- If the input includes a 'truncation' block, populate "
    "truncation_notes with one note per entry: the step's output_name, "
    "the total_available count (or 'unknown' if null), and how many "
    "records were examined. Example: 'us_suppliers: 137 total in source; "
    "25 examined for filtering.' Copy numbers from the truncation block; "
    "never invent them. If no truncation block, return an empty list.\n\n"
)

# Per-entity instruction block, appended to the preamble.
_SYSTEM_PROMPT_BY_ENTITY: dict[str, str] = {
    "Supplier": (
        "This is a SUPPLIER-rooted query. For each supplier in the final "
        "filtered set, emit one entry under 'suppliers'. Group purchase "
        "orders by supplier: open_po_count is the exact count of that "
        "supplier's POs in the open_pos bucket. List each unique buyer "
        "assigned to that supplier's POs; each buyer's person_id must "
        "appear in the buyers bucket."
    ),
    "Invoice": (
        "This is an INVOICE-rooted query. For each invoice in the final "
        "set, emit one entry under 'invoices' with its id, number, date, "
        "amount, currency, and the supplier name/number. supplier_number "
        "must appear in the data. Do not group or aggregate; list the "
        "invoices as returned."
    ),
    "PurchaseOrder": (
        "This is a PURCHASE-ORDER-rooted query. For each PO in the final "
        "set, emit one entry under 'purchase_orders' with its header id, "
        "order number, status, and supplier name/id. supplier_id must "
        "appear in the data. If a buyer is present for the PO, include it; "
        "the buyer's person_id must appear in the buyers bucket."
    ),
    "SupplierSpendRanking": (
        "This is a SUPPLIER SPEND RANKING (an aggregation). The data has a "
        "single 'aggregation' bucket containing one ranking object with a "
        "'rows' list, already sorted by total spend (highest first). For "
        "each row, emit one entry under 'suppliers' in the SAME order, "
        "copying supplier_name, supplier_number, total_spend, and "
        "invoice_count EXACTLY. Do not reorder, recompute, add, or drop "
        "suppliers, and do not do any arithmetic — the totals are already "
        "computed. In the summary, state the date range (from date_from/"
        "date_to), how many suppliers were ranked (total_suppliers), and "
        "name the top one or two with their totals. If 'truncated' is true, "
        "say plainly that the totals are based on a sample of invoices and "
        "may understate actual spend."
    ),
}


def _build_system_prompt(target_entity: str) -> str:
    """Preamble + the per-entity instruction block."""
    block = _SYSTEM_PROMPT_BY_ENTITY[target_entity]
    return _SYSTEM_PROMPT_PREAMBLE + block


def _build_synthesis_prompt(
    outputs: dict[str, list[dict]],
    truncation_by_step: dict[str, dict] | None = None,
) -> str:
    """Build the user-message portion of the prompt: outputs as JSON,
    plus an optional truncation block."""
    rendered = json.dumps(outputs, default=str, indent=2)
    parts = [
        "Here is the executor's output. Each top-level key is the "
        "output_name of a step; each value is a list of records returned "
        f"by that step.\n\n```json\n{rendered}\n```\n"
    ]
    if truncation_by_step:
        truncation_rendered = json.dumps(truncation_by_step, default=str, indent=2)
        parts.append(
            "\nThe following steps were truncated. Each entry tells you how "
            "many records actually match in the source vs. how many were "
            "examined. Populate truncation_notes from this block; do NOT "
            f"invent counts.\n\n```json\n{truncation_rendered}\n```\n"
        )
    parts.append(
        "\nProduce the structured response per the schema. Remember: only "
        "reference IDs present in the data above; do not invent."
    )
    return "".join(parts)


# ─────────────────────────────────────────────────────────────────────
# Hallucination validation — dispatched per response type
# ─────────────────────────────────────────────────────────────────────


def _raise_if_bad(parts: list[str]) -> None:
    if parts:
        raise HallucinationError(
            "Synthesizer produced IDs that do not appear in the executor "
            "output: " + "; ".join(parts)
        )


def _validate_supplier(response: SupplierResponse, valid: dict[str, set]) -> None:
    bad_sid: list[int] = []
    bad_snum: list[str] = []
    bad_pid: list[int] = []
    for s in response.suppliers:
        if s.supplier_id not in valid["supplier_ids"]:
            bad_sid.append(s.supplier_id)
        if s.supplier_number not in valid["supplier_numbers"]:
            bad_snum.append(s.supplier_number)
        for b in s.buyers:
            if b.person_id not in valid["person_ids"]:
                bad_pid.append(b.person_id)
    parts = []
    if bad_sid:
        parts.append(f"supplier_ids={bad_sid}")
    if bad_snum:
        parts.append(f"supplier_numbers={bad_snum}")
    if bad_pid:
        parts.append(f"person_ids={bad_pid}")
    _raise_if_bad(parts)


def _validate_invoice(response: InvoiceResponse, valid: dict[str, set]) -> None:
    bad_iid: list[int] = []
    bad_snum: list[str] = []
    for inv in response.invoices:
        if inv.invoice_id not in valid["invoice_ids"]:
            bad_iid.append(inv.invoice_id)
        if inv.supplier_number not in valid["supplier_numbers"]:
            bad_snum.append(inv.supplier_number)
    parts = []
    if bad_iid:
        parts.append(f"invoice_ids={bad_iid}")
    if bad_snum:
        parts.append(f"supplier_numbers={bad_snum}")
    _raise_if_bad(parts)


def _validate_purchase_order(
    response: PurchaseOrderResponse, valid: dict[str, set]
) -> None:
    bad_sid: list[int] = []
    bad_pid: list[int] = []
    for po in response.purchase_orders:
        if po.supplier_id not in valid["supplier_ids"]:
            bad_sid.append(po.supplier_id)
        if po.buyer is not None and po.buyer.person_id not in valid["person_ids"]:
            bad_pid.append(po.buyer.person_id)
    parts = []
    if bad_sid:
        parts.append(f"supplier_ids={bad_sid}")
    if bad_pid:
        parts.append(f"person_ids={bad_pid}")
    _raise_if_bad(parts)


def _validate_supplier_spend_ranking(
    response: SupplierSpendRankingResponse, valid: dict[str, set]
) -> None:
    bad_snum: list[str] = []
    for row in response.suppliers:
        if row.supplier_number not in valid["supplier_numbers"]:
            bad_snum.append(row.supplier_number)
    parts = []
    if bad_snum:
        parts.append(f"supplier_numbers={bad_snum}")
    _raise_if_bad(parts)


_VALIDATORS = {
    SupplierResponse: _validate_supplier,
    InvoiceResponse: _validate_invoice,
    PurchaseOrderResponse: _validate_purchase_order,
    SupplierSpendRankingResponse: _validate_supplier_spend_ranking,
}


def _validate_no_hallucinated_ids(
    response: BaseModel, outputs: dict[str, list[dict]]
) -> None:
    """Dispatch to the validator for the response's concrete type.
    An empty record list is always valid."""
    valid = _collect_valid_ids(outputs)
    validator = _VALIDATORS.get(type(response))
    if validator is None:
        # Unknown response type — should never happen given schema
        # selection, but fail loud rather than skip validation silently.
        raise UnsupportedEntityError(
            f"No hallucination validator for response type "
            f"{type(response).__name__}."
        )
    validator(response, valid)


# ─────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────


def synthesize_response(
    outputs: dict[str, list[dict]],
    target_entity: str,
    llm: Any | None = None,
    truncation_by_step: dict[str, dict] | None = None,
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

    Returns:
        A Pydantic model — SupplierResponse, InvoiceResponse, or
        PurchaseOrderResponse depending on target_entity.

    Raises:
        UnsupportedEntityError if target_entity has no schema.
        HallucinationError if any structured ID isn't in the executor data.
        Pydantic ValidationError if the LLM output doesn't fit the schema.
        Anything raised by the LLM call propagates.
    """
    # Feature 7: an aggregation produces a ranking, not an entity list.
    # It has no target_entity (the Intent carried an aggregate block
    # instead), so select the schema from the data shape. The executor
    # places the ranking under "aggregation" as a single object whose
    # "shape" identifies it.
    if _is_supplier_spend_ranking(outputs):
        schema: type[BaseModel] = SupplierSpendRankingResponse
        prompt_key = "SupplierSpendRanking"
    else:
        schema = SYNTHESIS_SCHEMAS.get(target_entity)
        if schema is None:
            raise UnsupportedEntityError(
                f"No synthesizer schema for target_entity={target_entity!r}. "
                f"Supported: {sorted(SYNTHESIS_SCHEMAS)}."
            )
        prompt_key = target_entity

    if llm is None:
        from spire.config import build_llm

        llm = build_llm(_TEMPERATURE)

    structured_llm = llm.with_structured_output(schema, include_raw=True)
    system_prompt = _build_system_prompt(prompt_key)
    user_message = _build_synthesis_prompt(outputs, truncation_by_step)

    result = structured_llm.invoke(
        [("system", system_prompt), ("human", user_message)]
    )

    # With include_raw=True the real LLM returns
    # {"raw": AIMessage, "parsed": schema, "parsing_error": ...}. Unit
    # tests inject a mock returning the bare model (or a dict); handle
    # both so token logging never breaks the mock path.
    if isinstance(result, dict) and "parsed" in result:
        from spire.config import log_usage

        log_usage(result.get("raw"), stage="synthesize")
        response = result["parsed"]
    else:
        response = result

    if isinstance(response, dict):
        response = schema(**response)

    _validate_no_hallucinated_ids(response, outputs)
    return response

