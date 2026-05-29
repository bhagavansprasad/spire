"""
Response synthesizer for the KG-driven path (Architecture Option 3).

Takes the executor's output (dict[output_name, list[dict]]) and
produces a structured, validated answer for the user.

Architecture decisions locked for v1:
- LLM: Gemini 2.0 Flash via langchain-google-genai (same as runner.py)
- Output: Pydantic-typed JSON via with_structured_output, NOT free-form
  prose. Variance is bounded by the schema; row 7 of the rubric becomes
  mechanically verifiable.
- Hallucination guard: every supplier_id and person_id in the response
  is cross-referenced against the executor's source data. Invented IDs
  raise HallucinationError loudly — no auto-retry, no silent acceptance.
- Schema is currently specific to the original Track A prompt's output
  shape (suppliers + buyers + PO counts + one free-form summary string).
  Generalizing to arbitrary output shapes is a v1.1 candidate.

Scope (F3a):
- Schema definitions, synthesizer entry point, hallucination validation.
- No CLI integration yet. F3b wires this into scripts/run_plan.py.

Companion design refs: docs/design3_measurement_report.md (defect:
row 7 = no synthesizer); the F1/F2/F3 fix plan in the working log.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────
# LLM configuration
# ─────────────────────────────────────────────────────────────────────

# Same model the agent runner uses. Cheap, capable enough for structured
# extraction from a few hundred lines of JSON context.
_MODEL_NAME = "gemini-2.0-flash"
# Deterministic-as-possible: temperature 0 for synthesis. Gemini isn't
# strictly deterministic at T=0 but variance is minimized.
_TEMPERATURE = 0.0


# ─────────────────────────────────────────────────────────────────────
# Output schema
#
# Specific to the original Track A prompt's answer shape. Each field is
# typed; the LLM is forced into this shape by langchain's
# with_structured_output. v1.1 candidate: generalize per-intent.
# ─────────────────────────────────────────────────────────────────────


class BuyerInfo(BaseModel):
    """One buyer mentioned in the synthesized response.

    Both fields are validated against the executor's `buyers` output
    after synthesis — person_id MUST appear in that list."""

    person_id: int = Field(description="The buyer's PersonId (HCM key).")
    display_name: str = Field(description="The buyer's display name.")


class SupplierSummary(BaseModel):
    """One supplier in the synthesized response.

    supplier_id and supplier_number are both validated against the
    executor's output (e.g. us_suppliers_no_recent_invoices). The LLM
    must not invent either."""

    supplier_id: int = Field(
        description="The supplier's SupplierId (numeric primary key)."
    )
    supplier_number: str = Field(
        description="The supplier's SupplierNumber (human-readable id)."
    )
    supplier_name: str = Field(description="The supplier's display name.")
    open_po_count: int = Field(
        description="Number of open purchase orders for this supplier "
        "in the executor's open_pos output."
    )
    buyers: list[BuyerInfo] = Field(
        description="Buyers assigned to this supplier's open POs. "
        "Each buyer's person_id must appear in the executor's "
        "buyers output."
    )


class SynthesizedResponse(BaseModel):
    """The top-level synthesized response.

    summary is the only free-form field. Everything else is typed and
    validatable. The response is rejected (HallucinationError) if any
    structured ID doesn't match the source data."""

    summary: str = Field(
        description="One-paragraph natural-language summary of the result. "
        "Keep to 3-5 sentences. Do not invent specifics not in the data."
    )
    suppliers: list[SupplierSummary] = Field(
        description="One entry per supplier in the final filtered set. "
        "Empty list if no suppliers passed the filters."
    )
    truncation_notes: list[str] = Field(
        default_factory=list,
        description="One short note per truncated step. Each note states "
        "the step's output_name, the total_available count if known, and "
        "how many records were examined. Empty list when no step was "
        "truncated. Populate ONLY from the truncation block in the "
        "executor output; never invent counts.",
    )

# ─────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────


class HallucinationError(RuntimeError):
    """The LLM produced structured output containing IDs that don't
    appear in the executor's source data.

    The exception message names the offending IDs so the gap is
    actionable rather than a generic 'something's wrong'."""


# ─────────────────────────────────────────────────────────────────────
# Source-data fingerprint (used both for prompt building and validation)
# ─────────────────────────────────────────────────────────────────────


def _collect_valid_ids(outputs: dict[str, list[dict]]) -> dict[str, set]:
    """
    Walk the executor outputs and collect the IDs the response is
    allowed to mention.

    Returns a dict like:
        {
          "supplier_ids":     {300000047414503, ...},
          "supplier_numbers": {"1252", ...},
          "person_ids":       {300000047340498, ...},
        }

    The validator uses this to detect hallucinated IDs. The prompt
    builder uses the same data so the LLM sees exactly the universe
    it's allowed to reference.

    Walks every output bucket and extracts the relevant fields wherever
    they appear, so order of buckets in `outputs` doesn't matter.
    """
    supplier_ids: set = set()
    supplier_numbers: set = set()
    person_ids: set = set()

    for bucket in outputs.values():
        for item in bucket:
            sid = item.get("SupplierId")
            if sid is not None:
                supplier_ids.add(sid)
            snum = item.get("SupplierNumber")
            if snum is not None:
                supplier_numbers.add(snum)
            pid = item.get("PersonId")
            if pid is not None:
                person_ids.add(pid)
            # BuyerId on a PO equals PersonId on a Buyer record — treat
            # both as the same id space for validation purposes.
            bid = item.get("BuyerId")
            if bid is not None:
                person_ids.add(bid)

    return {
        "supplier_ids": supplier_ids,
        "supplier_numbers": supplier_numbers,
        "person_ids": person_ids,
    }


# ─────────────────────────────────────────────────────────────────────
# Prompt building
# ─────────────────────────────────────────────────────────────────────


_SYSTEM_PROMPT = (
    "You are a response synthesizer for an Oracle Fusion Cloud query "
    "assistant. You will be given the structured output of a deterministic "
    "data-fetch pipeline (a dict of named result buckets). Your job is to "
    "produce a clear, concise summary of what the data shows.\n\n"
    "Rules you MUST follow:\n"
    "1. Only reference IDs (SupplierId, SupplierNumber, PersonId/BuyerId) "
    "that appear in the data given to you. Do NOT invent IDs.\n"
    "2. Do not add details that are not in the data (e.g. invented "
    "addresses, amounts, dates, buyer email).\n"
    "3. If the final filtered set is empty, say so plainly in the summary "
    "and return an empty suppliers list.\n"
    "4. Group purchase orders by supplier. Report open_po_count as the "
    "exact count of POs in the open_pos bucket for each supplier.\n"
    "5. List each unique buyer assigned to that supplier's POs. Each "
    "buyer's person_id must appear in the buyers bucket.\n"
    "6. Keep the summary to 3-5 sentences. Plain English. No marketing "
    "language.\n"
    "7. If the input includes a 'truncation' block, populate "
    "truncation_notes with one note per entry. Each note must state the "
    "step's output_name, the total_available count (or 'unknown' if "
    "null), and how many records were examined. Example: "
    "'us_suppliers: 137 total in source; 25 examined for filtering.' "
    "Do NOT invent numbers; copy them from the truncation block. If no "
    "truncation block is present, return an empty truncation_notes list."
)

def _build_synthesis_prompt(
    outputs: dict[str, list[dict]],
    truncation_by_step: dict[str, dict] | None = None,
) -> str:
    """
    Build the user-message portion of the prompt.

    Includes the full outputs dict as pretty-printed JSON, plus an
    optional truncation block when any step was truncated.
    """
    rendered = json.dumps(outputs, default=str, indent=2)
    parts = [
        "Here is the executor's output. Each top-level key is the "
        "output_name of a step; each value is a list of records returned "
        "by that step.\n\n"
        f"```json\n{rendered}\n```\n"
    ]

    if truncation_by_step:
        truncation_rendered = json.dumps(
            truncation_by_step, default=str, indent=2
        )
        parts.append(
            "\nThe following steps were truncated. Each entry tells you "
            "how many records actually match the step's filters in the "
            "source, vs. how many were examined by the executor. "
            "Populate truncation_notes from this block; do NOT invent "
            "counts.\n\n"
            f"```json\n{truncation_rendered}\n```\n"
        )

    parts.append(
        "\nProduce the structured response per the schema. Remember: "
        "only reference IDs present in the data above; do not invent."
    )
    return "".join(parts)


# ─────────────────────────────────────────────────────────────────────
# Hallucination validation
# ─────────────────────────────────────────────────────────────────────


def _validate_no_hallucinated_ids(
    response: SynthesizedResponse, outputs: dict[str, list[dict]]
) -> None:
    """
    Raise HallucinationError if any ID in the response doesn't match
    the executor's source data.

    Collects ALL offending IDs across the whole response before raising,
    so the caller sees the full extent of the hallucination instead of
    fixing one at a time.

    An empty response (no suppliers) is always valid.
    """
    valid = _collect_valid_ids(outputs)
    bad_supplier_ids: list[int] = []
    bad_supplier_numbers: list[str] = []
    bad_person_ids: list[int] = []

    for supplier in response.suppliers:
        if supplier.supplier_id not in valid["supplier_ids"]:
            bad_supplier_ids.append(supplier.supplier_id)
        if supplier.supplier_number not in valid["supplier_numbers"]:
            bad_supplier_numbers.append(supplier.supplier_number)
        for buyer in supplier.buyers:
            if buyer.person_id not in valid["person_ids"]:
                bad_person_ids.append(buyer.person_id)

    if not (bad_supplier_ids or bad_supplier_numbers or bad_person_ids):
        return

    parts = []
    if bad_supplier_ids:
        parts.append(f"supplier_ids={bad_supplier_ids}")
    if bad_supplier_numbers:
        parts.append(f"supplier_numbers={bad_supplier_numbers}")
    if bad_person_ids:
        parts.append(f"person_ids={bad_person_ids}")
    raise HallucinationError(
        "Synthesizer produced IDs that do not appear in the executor "
        "output: " + "; ".join(parts)
    )


# ─────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────


def synthesize_response(
    outputs: dict[str, list[dict]],
    llm: Any | None = None,
    truncation_by_step: dict[str, dict] | None = None,
) -> SynthesizedResponse:
    """
    Turn the executor's output dict into a validated structured response.

    Args:
        outputs: The dict returned by spire.executor.execute_plan.
        llm: Optional pre-built LangChain LLM. Tests inject a mock here;
            production passes None and a fresh ChatGoogleGenerativeAI is
            constructed. Reads GEMINI_API_KEY from the environment.
        truncation_by_step: Optional dict from execute_plan keyed by
            output_name, with each value being {total_available,
            limit_applied, truncated}. When present, the LLM is
            instructed to populate truncation_notes from it.

    Returns:
        SynthesizedResponse — a Pydantic model. response.summary is the
        one-paragraph prose; response.suppliers is the structured list;
        response.truncation_notes lists any truncated steps.

    Raises:
        HallucinationError if any structured ID doesn't match the
        executor's data.
        Pydantic ValidationError if the LLM somehow produces output
        that doesn't fit the schema.
        Anything raised by the LLM call propagates.
    """
    if llm is None:
        llm = ChatGoogleGenerativeAI(
            model=_MODEL_NAME, temperature=_TEMPERATURE
        )

    structured_llm = llm.with_structured_output(SynthesizedResponse)
    user_message = _build_synthesis_prompt(outputs, truncation_by_step)

    response = structured_llm.invoke(
        [
            ("system", _SYSTEM_PROMPT),
            ("human", user_message),
        ]
    )

    if isinstance(response, dict):
        response = SynthesizedResponse(**response)

    _validate_no_hallucinated_ids(response, outputs)
    return response