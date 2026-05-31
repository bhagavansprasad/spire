"""
Tests for the response synthesizer.

Two layers:
1. Unit tests with mocked LLMs. No API key required.
2. Integration tests that hit live Gemini. Marked
   @pytest.mark.integration; skipped by default. Run with:
       pytest -m integration tests/test_synthesizer.py
   Requires GEMINI_API_KEY (or GOOGLE_API_KEY) in the environment.

Feature 5: synthesize_response now requires target_entity; three
sibling response schemas (Supplier/Invoice/PurchaseOrder) are selected
from it. SynthesizedResponse / SupplierSummary remain as aliases of the
supplier-rooted schema, so supplier-path tests are mostly unchanged
apart from passing target_entity="Supplier".
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from spire.synthesizer.synthesizer import (
    BuyerInfo,
    HallucinationError,
    InvoiceRecord,
    InvoiceResponse,
    PurchaseOrderRecord,
    PurchaseOrderResponse,
    SupplierRecord,
    SupplierResponse,
    SupplierSummary,
    SynthesizedResponse,
    UnsupportedEntityError,
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
    """Realistic executor output for the original Track A prompt."""
    return {
        "us_suppliers": [
            {"SupplierId": 100, "SupplierNumber": "S100", "Supplier": "Acme", "MatchedCountry": "US"},
            {"SupplierId": 200, "SupplierNumber": "S200", "Supplier": "Beta", "MatchedCountry": "US"},
            {"SupplierId": 300, "SupplierNumber": "S300", "Supplier": "Gamma", "MatchedCountry": "US"},
        ],
        "us_suppliers_no_recent_invoices": [
            {"SupplierId": 100, "SupplierNumber": "S100", "Supplier": "Acme", "MatchedCountry": "US"},
            {"SupplierId": 300, "SupplierNumber": "S300", "Supplier": "Gamma", "MatchedCountry": "US"},
        ],
        "open_pos": [
            {"POHeaderId": 1001, "StatusCode": "OPEN", "SupplierId": 100, "BuyerId": 555},
            {"POHeaderId": 1002, "StatusCode": "OPEN", "SupplierId": 100, "BuyerId": 555},
            {"POHeaderId": 1003, "StatusCode": "OPEN", "SupplierId": 300, "BuyerId": 777},
        ],
        "buyers": [
            {"PersonId": 555, "DisplayName": "Alice"},
            {"PersonId": 777, "DisplayName": "Bob"},
        ],
    }


@pytest.fixture
def invoice_outputs() -> dict[str, list[dict]]:
    """Executor output for an invoice-rooted query."""
    return {
        "invoices": [
            {
                "InvoiceId": 9001,
                "InvoiceNumber": "INV-9001",
                "InvoiceDate": "2022-01-10",
                "InvoiceAmount": 1500.0,
                "InvoiceCurrency": "USD",
                "Supplier": "Lee Supplies",
                "SupplierNumber": "1252",
            },
            {
                "InvoiceId": 9002,
                "InvoiceNumber": "INV-9002",
                "InvoiceDate": "2022-01-22",
                "InvoiceAmount": 800.0,
                "InvoiceCurrency": "USD",
                "Supplier": "Lee Supplies",
                "SupplierNumber": "1252",
            },
        ],
    }


@pytest.fixture
def po_outputs() -> dict[str, list[dict]]:
    """Executor output for a PO-rooted query."""
    return {
        "purchase_orders": [
            {"POHeaderId": 1001, "OrderNumber": "PO-1001", "StatusCode": "OPEN", "Supplier": "Acme", "SupplierId": 100, "BuyerId": 555},
            {"POHeaderId": 1002, "OrderNumber": "PO-1002", "StatusCode": "OPEN", "Supplier": "Gamma", "SupplierId": 300, "BuyerId": 777},
        ],
        "buyers": [
            {"PersonId": 555, "DisplayName": "Alice"},
            {"PersonId": 777, "DisplayName": "Bob"},
        ],
    }


@pytest.fixture
def well_formed_response() -> SynthesizedResponse:
    """A supplier response matching sample_outputs."""
    return SynthesizedResponse(
        summary=(
            "Two US suppliers had no invoices in the last 6 months and have "
            "open purchase orders. Acme has 2 open POs assigned to Alice; "
            "Gamma has 1 open PO assigned to Bob."
        ),
        suppliers=[
            SupplierSummary(
                supplier_id=100, supplier_number="S100", supplier_name="Acme",
                open_po_count=2,
                buyers=[BuyerInfo(person_id=555, display_name="Alice")],
            ),
            SupplierSummary(
                supplier_id=300, supplier_number="S300", supplier_name="Gamma",
                open_po_count=1,
                buyers=[BuyerInfo(person_id=777, display_name="Bob")],
            ),
        ],
    )


# ─────────────────────────────────────────────────────────────────────
# Schema sanity checks
# ─────────────────────────────────────────────────────────────────────


def test_synthesized_response_accepts_minimal_empty_result() -> None:
    r = SynthesizedResponse(summary="No suppliers matched.", suppliers=[])
    assert r.suppliers == []


def test_synthesized_response_rejects_missing_summary() -> None:
    with pytest.raises(ValidationError):
        SynthesizedResponse(suppliers=[])  # type: ignore[call-arg]


def test_supplier_summary_rejects_wrong_types() -> None:
    with pytest.raises(ValidationError):
        SupplierSummary(
            supplier_id="not-a-number",  # type: ignore[arg-type]
            supplier_number="S100", supplier_name="Acme", open_po_count=1, buyers=[],
        )


def test_buyer_info_requires_person_id_and_display_name() -> None:
    with pytest.raises(ValidationError):
        BuyerInfo(person_id=555)  # type: ignore[call-arg]


def test_supplier_summary_is_alias_of_supplier_record() -> None:
    """Feature 5 keeps the old names as aliases."""
    assert SupplierSummary is SupplierRecord
    assert SynthesizedResponse is SupplierResponse


# ─────────────────────────────────────────────────────────────────────
# _collect_valid_ids
# ─────────────────────────────────────────────────────────────────────


def test_collect_valid_ids_finds_all_ids_in_sample(sample_outputs) -> None:
    ids = _collect_valid_ids(sample_outputs)
    assert ids["supplier_ids"] == {100, 200, 300}
    assert ids["supplier_numbers"] == {"S100", "S200", "S300"}
    assert ids["person_ids"] == {555, 777}


def test_collect_valid_ids_handles_empty_outputs() -> None:
    """No buckets → empty sets. Feature 5 adds invoice_ids to the dict."""
    ids = _collect_valid_ids({})
    assert ids == {
        "supplier_ids": set(),
        "supplier_numbers": set(),
        "person_ids": set(),
        "invoice_ids": set(),
    }


def test_collect_valid_ids_skips_none_values() -> None:
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
    outputs = {"open_pos": [{"BuyerId": 555}], "buyers": [{"PersonId": 777}]}
    ids = _collect_valid_ids(outputs)
    assert ids["person_ids"] == {555, 777}


def test_collect_valid_ids_finds_invoice_ids(invoice_outputs) -> None:
    ids = _collect_valid_ids(invoice_outputs)
    assert ids["invoice_ids"] == {9001, 9002}
    assert ids["supplier_numbers"] == {"1252"}


# ─────────────────────────────────────────────────────────────────────
# _validate_no_hallucinated_ids — supplier
# ─────────────────────────────────────────────────────────────────────


def test_validate_passes_for_well_formed_response(well_formed_response, sample_outputs) -> None:
    _validate_no_hallucinated_ids(well_formed_response, sample_outputs)


def test_validate_passes_for_empty_supplier_list(sample_outputs) -> None:
    empty = SynthesizedResponse(summary="None matched.", suppliers=[])
    _validate_no_hallucinated_ids(empty, sample_outputs)


def test_validate_raises_on_hallucinated_supplier_id(sample_outputs) -> None:
    bad = SynthesizedResponse(
        summary="x",
        suppliers=[SupplierSummary(supplier_id=999999, supplier_number="S100", supplier_name="Acme", open_po_count=1, buyers=[])],
    )
    with pytest.raises(HallucinationError) as exc_info:
        _validate_no_hallucinated_ids(bad, sample_outputs)
    assert "999999" in str(exc_info.value)
    assert "supplier_ids" in str(exc_info.value)


def test_validate_raises_on_hallucinated_supplier_number(sample_outputs) -> None:
    bad = SynthesizedResponse(
        summary="x",
        suppliers=[SupplierSummary(supplier_id=100, supplier_number="S999", supplier_name="Acme", open_po_count=1, buyers=[])],
    )
    with pytest.raises(HallucinationError) as exc_info:
        _validate_no_hallucinated_ids(bad, sample_outputs)
    assert "S999" in str(exc_info.value)
    assert "supplier_numbers" in str(exc_info.value)


def test_validate_raises_on_hallucinated_person_id(sample_outputs) -> None:
    bad = SynthesizedResponse(
        summary="x",
        suppliers=[SupplierSummary(supplier_id=100, supplier_number="S100", supplier_name="Acme", open_po_count=1, buyers=[BuyerInfo(person_id=42, display_name="Nobody")])],
    )
    with pytest.raises(HallucinationError) as exc_info:
        _validate_no_hallucinated_ids(bad, sample_outputs)
    assert "42" in str(exc_info.value)
    assert "person_ids" in str(exc_info.value)


def test_validate_collects_all_offenders_before_raising(sample_outputs) -> None:
    bad = SynthesizedResponse(
        summary="x",
        suppliers=[SupplierSummary(supplier_id=999999, supplier_number="S888", supplier_name="Phantom", open_po_count=1, buyers=[BuyerInfo(person_id=42, display_name="Nobody")])],
    )
    with pytest.raises(HallucinationError) as exc_info:
        _validate_no_hallucinated_ids(bad, sample_outputs)
    msg = str(exc_info.value)
    assert "999999" in msg and "S888" in msg and "42" in msg


# ─────────────────────────────────────────────────────────────────────
# _validate_no_hallucinated_ids — invoice & PO
# ─────────────────────────────────────────────────────────────────────


def test_validate_invoice_passes_for_well_formed(invoice_outputs) -> None:
    good = InvoiceResponse(
        summary="Two invoices for Lee Supplies in Jan 2022.",
        invoices=[
            InvoiceRecord(invoice_id=9001, invoice_number="INV-9001", invoice_date="2022-01-10", invoice_amount=1500.0, invoice_currency="USD", supplier_name="Lee Supplies", supplier_number="1252"),
        ],
    )
    _validate_no_hallucinated_ids(good, invoice_outputs)


def test_validate_invoice_raises_on_bad_invoice_id(invoice_outputs) -> None:
    bad = InvoiceResponse(
        summary="x",
        invoices=[InvoiceRecord(invoice_id=123, invoice_number="INV-X", invoice_date="2022-01-10", invoice_amount=1.0, supplier_name="Lee Supplies", supplier_number="1252")],
    )
    with pytest.raises(HallucinationError) as exc_info:
        _validate_no_hallucinated_ids(bad, invoice_outputs)
    assert "123" in str(exc_info.value)
    assert "invoice_ids" in str(exc_info.value)


def test_validate_po_passes_for_well_formed(po_outputs) -> None:
    good = PurchaseOrderResponse(
        summary="Two open POs.",
        purchase_orders=[
            PurchaseOrderRecord(po_header_id=1001, order_number="PO-1001", status="OPEN", supplier_name="Acme", supplier_id=100, buyer=BuyerInfo(person_id=555, display_name="Alice")),
        ],
    )
    _validate_no_hallucinated_ids(good, po_outputs)


def test_validate_po_raises_on_bad_supplier_id(po_outputs) -> None:
    bad = PurchaseOrderResponse(
        summary="x",
        purchase_orders=[PurchaseOrderRecord(po_header_id=1001, order_number="PO-1001", status="OPEN", supplier_name="Ghost", supplier_id=999, buyer=None)],
    )
    with pytest.raises(HallucinationError) as exc_info:
        _validate_no_hallucinated_ids(bad, po_outputs)
    assert "999" in str(exc_info.value)


def test_validate_po_raises_on_bad_buyer(po_outputs) -> None:
    bad = PurchaseOrderResponse(
        summary="x",
        purchase_orders=[PurchaseOrderRecord(po_header_id=1001, order_number="PO-1001", status="OPEN", supplier_name="Acme", supplier_id=100, buyer=BuyerInfo(person_id=42, display_name="Nobody"))],
    )
    with pytest.raises(HallucinationError) as exc_info:
        _validate_no_hallucinated_ids(bad, po_outputs)
    assert "42" in str(exc_info.value)
    assert "person_ids" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────
# _build_synthesis_prompt
# ─────────────────────────────────────────────────────────────────────


def test_build_prompt_embeds_outputs_as_json(sample_outputs) -> None:
    prompt = _build_synthesis_prompt(sample_outputs)
    assert "```json" in prompt
    assert "us_suppliers" in prompt
    assert "open_pos" in prompt
    assert "S100" in prompt


def test_build_prompt_handles_non_json_native_types() -> None:
    from decimal import Decimal
    outputs = {"open_pos": [{"POHeaderId": 1, "Ordered": Decimal("100.50")}]}
    prompt = _build_synthesis_prompt(outputs)
    assert "100.50" in prompt


def test_build_prompt_instructs_no_invention(sample_outputs) -> None:
    prompt = _build_synthesis_prompt(sample_outputs)
    assert "do not invent" in prompt.lower()


# ─────────────────────────────────────────────────────────────────────
# synthesize_response — mocked LLM
# ─────────────────────────────────────────────────────────────────────


def _mock_llm(structured_output) -> MagicMock:
    llm = MagicMock()
    structured = MagicMock()
    structured.invoke.return_value = structured_output
    llm.with_structured_output.return_value = structured
    return llm


def test_synthesize_response_happy_path(sample_outputs, well_formed_response) -> None:
    llm = _mock_llm(well_formed_response)
    result = synthesize_response(sample_outputs, target_entity="Supplier", llm=llm)
    assert result == well_formed_response
    llm.with_structured_output.assert_called_once_with(SupplierResponse)


def test_synthesize_response_accepts_dict_from_llm(sample_outputs) -> None:
    response_dict = {
        "summary": "All good.",
        "suppliers": [{"supplier_id": 100, "supplier_number": "S100", "supplier_name": "Acme", "open_po_count": 2, "buyers": [{"person_id": 555, "display_name": "Alice"}]}],
    }
    llm = _mock_llm(response_dict)
    result = synthesize_response(sample_outputs, target_entity="Supplier", llm=llm)
    assert isinstance(result, SynthesizedResponse)
    assert result.suppliers[0].supplier_id == 100


def test_synthesize_response_raises_on_hallucinated_ids(sample_outputs) -> None:
    bad = SynthesizedResponse(
        summary="invented",
        suppliers=[SupplierSummary(supplier_id=999999, supplier_number="S100", supplier_name="Phantom", open_po_count=1, buyers=[])],
    )
    llm = _mock_llm(bad)
    with pytest.raises(HallucinationError):
        synthesize_response(sample_outputs, target_entity="Supplier", llm=llm)


def test_synthesize_response_propagates_llm_errors(sample_outputs) -> None:
    llm = MagicMock()
    structured = MagicMock()
    structured.invoke.side_effect = RuntimeError("gemini 503")
    llm.with_structured_output.return_value = structured
    with pytest.raises(RuntimeError, match="gemini 503"):
        synthesize_response(sample_outputs, target_entity="Supplier", llm=llm)


def test_synthesize_response_empty_suppliers_passes() -> None:
    empty_outputs = {"us_suppliers": [], "us_suppliers_no_recent_invoices": [], "open_pos": [], "buyers": []}
    response = SynthesizedResponse(summary="No suppliers matched.", suppliers=[])
    llm = _mock_llm(response)
    result = synthesize_response(empty_outputs, target_entity="Supplier", llm=llm)
    assert result.suppliers == []


def test_synthesize_response_invoice_entity_selects_invoice_schema(invoice_outputs) -> None:
    response = InvoiceResponse(
        summary="Two invoices.",
        invoices=[InvoiceRecord(invoice_id=9001, invoice_number="INV-9001", invoice_date="2022-01-10", invoice_amount=1500.0, invoice_currency="USD", supplier_name="Lee Supplies", supplier_number="1252")],
    )
    llm = _mock_llm(response)
    result = synthesize_response(invoice_outputs, target_entity="Invoice", llm=llm)
    assert isinstance(result, InvoiceResponse)
    llm.with_structured_output.assert_called_once_with(InvoiceResponse)
    assert result.invoices[0].invoice_id == 9001


def test_synthesize_response_po_entity_selects_po_schema(po_outputs) -> None:
    response = PurchaseOrderResponse(
        summary="Two POs.",
        purchase_orders=[PurchaseOrderRecord(po_header_id=1001, order_number="PO-1001", status="OPEN", supplier_name="Acme", supplier_id=100, buyer=BuyerInfo(person_id=555, display_name="Alice"))],
    )
    llm = _mock_llm(response)
    result = synthesize_response(po_outputs, target_entity="PurchaseOrder", llm=llm)
    assert isinstance(result, PurchaseOrderResponse)
    llm.with_structured_output.assert_called_once_with(PurchaseOrderResponse)


def test_synthesize_response_unsupported_entity_raises(sample_outputs) -> None:
    """Buyer aggregation / Contract have no schema → loud error, no LLM call."""
    llm = _mock_llm(None)
    with pytest.raises(UnsupportedEntityError) as exc_info:
        synthesize_response(sample_outputs, target_entity="Buyer", llm=llm)
    assert "Buyer" in str(exc_info.value)
    # LLM must NOT have been invoked for an unsupported entity.
    llm.with_structured_output.assert_not_called()


# ─────────────────────────────────────────────────────────────────────
# Integration — live Gemini (skipped by default)
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"),
    reason="GEMINI_API_KEY (or GOOGLE_API_KEY) not set",
)
def test_synthesize_response_against_live_gemini(sample_outputs) -> None:
    """End-to-end supplier synthesis against live Gemini. Asserts
    structured fields, not prose (T=0 is not strictly deterministic)."""
    response = synthesize_response(sample_outputs, target_entity="Supplier")
    assert isinstance(response, SynthesizedResponse)
    assert response.summary.strip()
    assert len(response.summary) > 20
    returned_ids = {s.supplier_id for s in response.suppliers}
    assert returned_ids <= {100, 300}
