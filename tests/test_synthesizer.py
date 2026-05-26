"""
Tests for the response synthesizer (F3a + F3b scope).

Two layers:
1. Unit tests with mocked LLMs. No API key required.
2. One integration test that hits live Gemini. Marked
   @pytest.mark.integration; skipped by default. Run with:
       pytest -m integration tests/test_synthesizer.py
   Requires GEMINI_API_KEY in the environment.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from spire.synthesizer.synthesizer import (
    BuyerInfo,
    HallucinationError,
    SupplierSummary,
    SynthesizedResponse,
    _build_synthesis_prompt,
    _collect_valid_ids,
    _validate_no_hallucinated_ids,
    synthesize_response,
)


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_outputs() -> dict[str, list[dict]]:
    """A realistic executor output for the original Track A prompt:
    2 US suppliers with no recent invoices, 3 open POs across them,
    2 unique buyers."""
    return {
        "us_suppliers": [
            {
                "SupplierId": 100,
                "SupplierNumber": "S100",
                "Supplier": "Acme",
                "MatchedCountry": "US",
            },
            {
                "SupplierId": 200,
                "SupplierNumber": "S200",
                "Supplier": "Beta",
                "MatchedCountry": "US",
            },
            {
                "SupplierId": 300,
                "SupplierNumber": "S300",
                "Supplier": "Gamma",
                "MatchedCountry": "US",
            },
        ],
        "us_suppliers_no_recent_invoices": [
            # Acme and Gamma passed the filter; Beta dropped.
            {
                "SupplierId": 100,
                "SupplierNumber": "S100",
                "Supplier": "Acme",
                "MatchedCountry": "US",
            },
            {
                "SupplierId": 300,
                "SupplierNumber": "S300",
                "Supplier": "Gamma",
                "MatchedCountry": "US",
            },
        ],
        "open_pos": [
            {
                "POHeaderId": 1001,
                "StatusCode": "OPEN",
                "SupplierId": 100,
                "BuyerId": 555,
            },
            {
                "POHeaderId": 1002,
                "StatusCode": "OPEN",
                "SupplierId": 100,
                "BuyerId": 555,
            },
            {
                "POHeaderId": 1003,
                "StatusCode": "OPEN",
                "SupplierId": 300,
                "BuyerId": 777,
            },
        ],
        "buyers": [
            {"PersonId": 555, "DisplayName": "Alice"},
            {"PersonId": 777, "DisplayName": "Bob"},
        ],
    }


@pytest.fixture
def well_formed_response() -> SynthesizedResponse:
    """A response that matches the sample_outputs fixture and should
    pass the hallucination validator."""
    return SynthesizedResponse(
        summary=(
            "Two US suppliers had no invoices in the last 6 months and "
            "have open purchase orders. Acme has 2 open POs assigned to "
            "Alice; Gamma has 1 open PO assigned to Bob."
        ),
        suppliers=[
            SupplierSummary(
                supplier_id=100,
                supplier_number="S100",
                supplier_name="Acme",
                open_po_count=2,
                buyers=[BuyerInfo(person_id=555, display_name="Alice")],
            ),
            SupplierSummary(
                supplier_id=300,
                supplier_number="S300",
                supplier_name="Gamma",
                open_po_count=1,
                buyers=[BuyerInfo(person_id=777, display_name="Bob")],
            ),
        ],
    )


# ─────────────────────────────────────────────────────────────────────
# Schema sanity checks (Pydantic)
# ─────────────────────────────────────────────────────────────────────


def test_synthesized_response_accepts_minimal_empty_result() -> None:
    """An empty supplier list is valid (no matches is a real answer)."""
    r = SynthesizedResponse(
        summary="No suppliers matched the filters.",
        suppliers=[],
    )
    assert r.suppliers == []


def test_synthesized_response_rejects_missing_summary() -> None:
    """summary is required."""
    with pytest.raises(ValidationError):
        SynthesizedResponse(suppliers=[])  # type: ignore[call-arg]


def test_supplier_summary_rejects_wrong_types() -> None:
    """supplier_id must be int, not str."""
    with pytest.raises(ValidationError):
        SupplierSummary(
            supplier_id="not-a-number",  # type: ignore[arg-type]
            supplier_number="S100",
            supplier_name="Acme",
            open_po_count=1,
            buyers=[],
        )


def test_buyer_info_requires_person_id_and_display_name() -> None:
    """Both fields required."""
    with pytest.raises(ValidationError):
        BuyerInfo(person_id=555)  # type: ignore[call-arg]


# ─────────────────────────────────────────────────────────────────────
# _collect_valid_ids
# ─────────────────────────────────────────────────────────────────────


def test_collect_valid_ids_finds_all_ids_in_sample(
    sample_outputs: dict[str, list[dict]],
) -> None:
    """All SupplierIds, SupplierNumbers, and PersonIds (incl. BuyerIds)
    in the sample are collected."""
    ids = _collect_valid_ids(sample_outputs)
    assert ids["supplier_ids"] == {100, 200, 300}
    assert ids["supplier_numbers"] == {"S100", "S200", "S300"}
    # BuyerIds (555, 777) and PersonIds (555, 777) merge into one set.
    assert ids["person_ids"] == {555, 777}


def test_collect_valid_ids_handles_empty_outputs() -> None:
    """No buckets → empty sets, not crashes."""
    ids = _collect_valid_ids({})
    assert ids == {
        "supplier_ids": set(),
        "supplier_numbers": set(),
        "person_ids": set(),
    }


def test_collect_valid_ids_skips_none_values() -> None:
    """Items with None for a field don't contribute to the valid set."""
    outputs = {
        "us_suppliers": [
            {"SupplierId": 100, "SupplierNumber": None},
            {"SupplierId": None, "SupplierNumber": "S200"},
        ]
    }
    ids = _collect_valid_ids(outputs)
    assert ids["supplier_ids"] == {100}
    assert ids["supplier_numbers"] == {"S200"}


def test_collect_valid_ids_merges_buyer_id_and_person_id() -> None:
    """A BuyerId on a PO equals a PersonId on a Buyer — both populate
    the same valid set."""
    outputs = {
        "open_pos": [{"BuyerId": 555}],
        "buyers": [{"PersonId": 777}],
    }
    ids = _collect_valid_ids(outputs)
    assert ids["person_ids"] == {555, 777}


# ─────────────────────────────────────────────────────────────────────
# _validate_no_hallucinated_ids
# ─────────────────────────────────────────────────────────────────────


def test_validate_passes_for_well_formed_response(
    well_formed_response: SynthesizedResponse,
    sample_outputs: dict[str, list[dict]],
) -> None:
    """The well_formed_response uses only IDs from sample_outputs;
    validation should pass silently."""
    _validate_no_hallucinated_ids(well_formed_response, sample_outputs)


def test_validate_passes_for_empty_supplier_list(
    sample_outputs: dict[str, list[dict]],
) -> None:
    """An empty response is always valid (no IDs to check)."""
    empty = SynthesizedResponse(summary="None matched.", suppliers=[])
    _validate_no_hallucinated_ids(empty, sample_outputs)


def test_validate_raises_on_hallucinated_supplier_id(
    sample_outputs: dict[str, list[dict]],
) -> None:
    """An invented supplier_id raises HallucinationError naming the ID."""
    bad = SynthesizedResponse(
        summary="x",
        suppliers=[
            SupplierSummary(
                supplier_id=999999,  # NOT in sample_outputs
                supplier_number="S100",
                supplier_name="Acme",
                open_po_count=1,
                buyers=[],
            ),
        ],
    )
    with pytest.raises(HallucinationError) as exc_info:
        _validate_no_hallucinated_ids(bad, sample_outputs)
    assert "999999" in str(exc_info.value)
    assert "supplier_ids" in str(exc_info.value)


def test_validate_raises_on_hallucinated_supplier_number(
    sample_outputs: dict[str, list[dict]],
) -> None:
    """An invented supplier_number raises HallucinationError."""
    bad = SynthesizedResponse(
        summary="x",
        suppliers=[
            SupplierSummary(
                supplier_id=100,
                supplier_number="S999",  # NOT in sample_outputs
                supplier_name="Acme",
                open_po_count=1,
                buyers=[],
            ),
        ],
    )
    with pytest.raises(HallucinationError) as exc_info:
        _validate_no_hallucinated_ids(bad, sample_outputs)
    assert "S999" in str(exc_info.value)
    assert "supplier_numbers" in str(exc_info.value)


def test_validate_raises_on_hallucinated_person_id(
    sample_outputs: dict[str, list[dict]],
) -> None:
    """An invented buyer person_id raises HallucinationError."""
    bad = SynthesizedResponse(
        summary="x",
        suppliers=[
            SupplierSummary(
                supplier_id=100,
                supplier_number="S100",
                supplier_name="Acme",
                open_po_count=1,
                buyers=[
                    BuyerInfo(person_id=42, display_name="Nobody"),
                ],
            ),
        ],
    )
    with pytest.raises(HallucinationError) as exc_info:
        _validate_no_hallucinated_ids(bad, sample_outputs)
    assert "42" in str(exc_info.value)
    assert "person_ids" in str(exc_info.value)


def test_validate_collects_all_offenders_before_raising(
    sample_outputs: dict[str, list[dict]],
) -> None:
    """If a response has multiple kinds of hallucinated IDs, the error
    lists ALL of them — the caller shouldn't have to fix one at a time."""
    bad = SynthesizedResponse(
        summary="x",
        suppliers=[
            SupplierSummary(
                supplier_id=999999,
                supplier_number="S888",
                supplier_name="Phantom",
                open_po_count=1,
                buyers=[
                    BuyerInfo(person_id=42, display_name="Nobody"),
                ],
            ),
        ],
    )
    with pytest.raises(HallucinationError) as exc_info:
        _validate_no_hallucinated_ids(bad, sample_outputs)
    msg = str(exc_info.value)
    assert "999999" in msg
    assert "S888" in msg
    assert "42" in msg


# ─────────────────────────────────────────────────────────────────────
# _build_synthesis_prompt
# ─────────────────────────────────────────────────────────────────────


def test_build_prompt_embeds_outputs_as_json(
    sample_outputs: dict[str, list[dict]],
) -> None:
    """The prompt includes the full outputs dict as JSON (full-context
    approach, locked in design)."""
    prompt = _build_synthesis_prompt(sample_outputs)
    assert "```json" in prompt
    assert "us_suppliers" in prompt
    assert "us_suppliers_no_recent_invoices" in prompt
    assert "open_pos" in prompt
    assert "buyers" in prompt
    # A specific ID from the sample should be visible.
    assert "S100" in prompt


def test_build_prompt_handles_non_json_native_types() -> None:
    """default=str in json.dumps prevents crashes on Decimal, datetime,
    etc. Sanity test: an outputs dict with a non-trivial type still
    serializes."""
    from decimal import Decimal
    outputs = {
        "open_pos": [{"POHeaderId": 1, "Ordered": Decimal("100.50")}]
    }
    prompt = _build_synthesis_prompt(outputs)
    # The Decimal renders as a string in the prompt; we just need
    # the build to not raise.
    assert "100.50" in prompt


def test_build_prompt_instructs_no_invention(
    sample_outputs: dict[str, list[dict]],
) -> None:
    """The user-message portion of the prompt repeats the no-invention
    instruction. Belt-and-suspenders with the system prompt."""
    prompt = _build_synthesis_prompt(sample_outputs)
    assert "do not invent" in prompt.lower()


# ─────────────────────────────────────────────────────────────────────
# synthesize_response — end-to-end with mocked LLM
# ─────────────────────────────────────────────────────────────────────


def _mock_llm(structured_output: SynthesizedResponse | dict) -> MagicMock:
    """Build a mock LLM that returns the given response from
    .with_structured_output(...).invoke(...)."""
    llm = MagicMock()
    structured = MagicMock()
    structured.invoke.return_value = structured_output
    llm.with_structured_output.return_value = structured
    return llm


def test_synthesize_response_happy_path(
    sample_outputs: dict[str, list[dict]],
    well_formed_response: SynthesizedResponse,
) -> None:
    """The LLM returns a clean response; synthesize_response returns it."""
    llm = _mock_llm(well_formed_response)
    result = synthesize_response(sample_outputs, llm=llm)
    assert result == well_formed_response
    # Confirm the LLM was actually called via the structured-output path.
    llm.with_structured_output.assert_called_once_with(SynthesizedResponse)


def test_synthesize_response_accepts_dict_from_llm(
    sample_outputs: dict[str, list[dict]],
) -> None:
    """Some langchain versions return a dict instead of the Pydantic
    model. synthesize_response should coerce it."""
    response_dict = {
        "summary": "All good.",
        "suppliers": [
            {
                "supplier_id": 100,
                "supplier_number": "S100",
                "supplier_name": "Acme",
                "open_po_count": 2,
                "buyers": [{"person_id": 555, "display_name": "Alice"}],
            }
        ],
    }
    llm = _mock_llm(response_dict)
    result = synthesize_response(sample_outputs, llm=llm)
    assert isinstance(result, SynthesizedResponse)
    assert result.suppliers[0].supplier_id == 100


def test_synthesize_response_raises_on_hallucinated_ids(
    sample_outputs: dict[str, list[dict]],
) -> None:
    """If the mocked LLM invents an ID, synthesize_response raises
    HallucinationError. No auto-retry, no silent acceptance."""
    bad = SynthesizedResponse(
        summary="invented",
        suppliers=[
            SupplierSummary(
                supplier_id=999999,
                supplier_number="S100",
                supplier_name="Phantom",
                open_po_count=1,
                buyers=[],
            ),
        ],
    )
    llm = _mock_llm(bad)
    with pytest.raises(HallucinationError):
        synthesize_response(sample_outputs, llm=llm)


def test_synthesize_response_propagates_llm_errors(
    sample_outputs: dict[str, list[dict]],
) -> None:
    """Network / auth / rate-limit errors from the LLM call propagate
    verbatim. We don't silently swallow them."""
    llm = MagicMock()
    structured = MagicMock()
    structured.invoke.side_effect = RuntimeError("gemini 503")
    llm.with_structured_output.return_value = structured
    with pytest.raises(RuntimeError, match="gemini 503"):
        synthesize_response(sample_outputs, llm=llm)


def test_synthesize_response_empty_suppliers_passes() -> None:
    """If the executor's output has no surviving suppliers, the synth
    returns a clean empty response — no hallucination error, no crash."""
    empty_outputs = {
        "us_suppliers": [],
        "us_suppliers_no_recent_invoices": [],
        "open_pos": [],
        "buyers": [],
    }
    response = SynthesizedResponse(
        summary="No suppliers matched.",
        suppliers=[],
    )
    llm = _mock_llm(response)
    result = synthesize_response(empty_outputs, llm=llm)
    assert result.suppliers == []


# ─────────────────────────────────────────────────────────────────────
# Integration test — live Gemini
#
# Marked @pytest.mark.integration; skipped by default. Run with:
#     pytest -m integration tests/test_synthesizer.py
#
# Requires GEMINI_API_KEY in the environment. Skipped automatically
# if it's missing so the suite stays runnable everywhere.
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"),
    reason="GEMINI_API_KEY (or GOOGLE_API_KEY) not set",
)
def test_synthesize_response_against_live_gemini(
    sample_outputs: dict[str, list[dict]],
) -> None:
    """
    End-to-end synthesis against live Gemini 2.0 Flash. Verifies:
    - The LLM call succeeds.
    - The response parses against the SynthesizedResponse schema.
    - The hallucination validator does NOT fire (every ID in the
      response is in sample_outputs).
    - The summary is non-empty prose.
    - The suppliers list contains the two we expect (id 100 + 300),
      since those are the only ones in us_suppliers_no_recent_invoices.

    Honest framing: Gemini at T=0 is NOT strictly deterministic. The
    exact wording of the summary will vary run-to-run. We assert the
    structured fields, not the prose. If the hallucination validator
    fires here (LLM invented an ID despite the system prompt), that's
    a real signal — not test flakiness — and we should investigate.

    Cost: one LLM call (~2-5s).
    """
    response = synthesize_response(sample_outputs)

    # Schema is enforced by Pydantic; if we got here, structure is OK.
    assert isinstance(response, SynthesizedResponse)

    # Summary is non-empty prose.
    assert response.summary.strip()
    assert len(response.summary) > 20

    # Suppliers list reflects the FILTERED set, not the raw us_suppliers.
    # sample_outputs has 2 items in us_suppliers_no_recent_invoices
    # (ids 100 and 300). Beta (200) is in us_suppliers but NOT in the
    # filtered bucket; it must NOT appear here.
    supplier_ids = {s.supplier_id for s in response.suppliers}
    # Belt-and-suspenders: hallucination validation already ran inside
    # synthesize_response, but re-check the expected subset semantics.
    assert supplier_ids.issubset({100, 300}), (
        f"Synth output should only reference filtered suppliers "
        f"(100, 300). Got: {supplier_ids}"
    )
    # And the synthesizer should have picked up SOME of the filtered set
    # (we shouldn't get an empty list when 2 valid suppliers exist).
    assert len(response.suppliers) > 0
