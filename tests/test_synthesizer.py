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
    AccountCreditMemoInfo,
    AccountReceiptInfo,
    BuyerInfo,
    CreditMemoListResponse,
    CreditMemoRecord,
    CustomerAccountRecord,
    CustomerAccountResponse,
    HallucinationError,
    InvoiceRecord,
    InvoiceResponse,
    PurchaseOrderRecord,
    PurchaseOrderResponse,
    ReceivablesInvoiceLineInfo,
    ReceivablesInvoiceRecord,
    ReceivablesInvoiceResponse,
    ReceivablesInvoiceTransactionDFFInfo,
    ReceivablesTaxLineInfo,
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
    """No buckets → empty sets. Feature 5 adds invoice_ids; Phase 6 adds
    address_ids; P5b adds the PO child ids and contact_ids; AR-P5 adds
    account_credit_memo_ids (the account's credit memos) and
    account_receipt_ids (its receipts) — each a separate id space from
    the AR-invoice CustomerTransactionId and from each other. The
    standard-receipts work adds standard_receipt_ids and
    application_ids (receipt-to-transaction applications)."""
    ids = _collect_valid_ids({})
    assert ids == {
        "supplier_ids": set(),
        "supplier_numbers": set(),
        "person_ids": set(),
        "invoice_ids": set(),
        "address_ids": set(),
        "po_line_ids": set(),
        "line_location_ids": set(),
        "po_distribution_ids": set(),
        "contact_ids": set(),
        "customer_transaction_ids": set(),
        "customer_transaction_line_ids": set(),
        "customer_account_ids": set(),
        "customer_account_transaction_ids": set(),
        "account_credit_memo_ids": set(),
        "account_receipt_ids": set(),
        "application_ids": set(),
        "standard_receipt_ids": set(),
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
    # Decimal is coerced to float for JSON, so the trailing zero is
    # dropped: Decimal("100.50") serialises as 100.5. The VALUE is
    # preserved — only the string form differs.
    assert "100.5" in prompt


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
    llm.with_structured_output.assert_called_once_with(SupplierResponse, include_raw=True)


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
    llm.with_structured_output.assert_called_once_with(InvoiceResponse, include_raw=True)
    assert result.invoices[0].invoice_id == 9001


def test_synthesize_response_po_entity_selects_po_schema(po_outputs) -> None:
    response = PurchaseOrderResponse(
        summary="Two POs.",
        purchase_orders=[PurchaseOrderRecord(po_header_id=1001, order_number="PO-1001", status="OPEN", supplier_name="Acme", supplier_id=100, buyer=BuyerInfo(person_id=555, display_name="Alice"))],
    )
    llm = _mock_llm(response)
    result = synthesize_response(po_outputs, target_entity="PurchaseOrder", llm=llm)
    assert isinstance(result, PurchaseOrderResponse)
    llm.with_structured_output.assert_called_once_with(PurchaseOrderResponse, include_raw=True)


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



# ─────────────────────────────────────────────────────────────────────
# _validate_no_hallucinated_ids — AR-P3 nested tax lines
# Tax lines nest under invoice lines. Their id (the TAX line PK) validates
# against the same customer_transaction_line_ids bucket the harvest fills
# from every output row (parent line ids AND tax-line PKs both land there).
# ─────────────────────────────────────────────────────────────────────


def _tax_outputs() -> dict[str, list[dict]]:
    """Executor output for 'AR invoice 1002 and its tax lines': the invoice,
    one line (id 74), and two tax lines whose OWN ids are 112/113."""
    return {
        "receivables_invoices": [
            {"CustomerTransactionId": 1002, "TransactionNumber": "5"},
        ],
        "receivables_invoice_lines": [
            {"CustomerTransactionLineId": 74, "CustomerTransactionId": 1002},
        ],
        "receivablestaxline": [
            {
                "CustomerTransactionLineId": 112,
                "ParentCustomerTransactionLineId": 74,
                "TaxLineNumber": 1,
            },
            {
                "CustomerTransactionLineId": 113,
                "ParentCustomerTransactionLineId": 74,
                "TaxLineNumber": 2,
            },
        ],
    }


def _tax_response(tax_id_1: int, tax_id_2: int) -> ReceivablesInvoiceResponse:
    """Build an AR-invoice response with two tax lines nested under line 74,
    using the given tax-line ids (so a test can inject a bad one)."""
    return ReceivablesInvoiceResponse(
        summary="One invoice with tax.",
        receivables_invoices=[
            ReceivablesInvoiceRecord(
                customer_transaction_id=1002,
                transaction_number="5",
                lines=[
                    ReceivablesInvoiceLineInfo(
                        customer_transaction_line_id=74,
                        line_number=1,
                        tax_lines=[
                            ReceivablesTaxLineInfo(
                                customer_transaction_line_id=tax_id_1,
                                tax_line_number=1,
                                tax="STATE",
                            ),
                            ReceivablesTaxLineInfo(
                                customer_transaction_line_id=tax_id_2,
                                tax_line_number=2,
                                tax="COUNTY",
                            ),
                        ],
                    )
                ],
            )
        ],
    )


def test_validate_passes_for_nested_tax_lines() -> None:
    """Valid tax-line ids (112, 113 — both in the output) pass validation."""
    _validate_no_hallucinated_ids(_tax_response(112, 113), _tax_outputs())


def test_validate_raises_on_hallucinated_tax_line_id() -> None:
    """A tax-line id not in the output (999) is caught, even though its
    parent line and invoice ids are valid."""
    with pytest.raises(HallucinationError) as exc_info:
        _validate_no_hallucinated_ids(_tax_response(112, 999), _tax_outputs())
    assert "999" in str(exc_info.value)


def test_collect_valid_ids_harvests_tax_line_pks() -> None:
    """The harvest collects the tax rows' OWN CustomerTransactionLineId
    (112, 113) into the line-id bucket, alongside the parent line id (74)."""
    ids = _collect_valid_ids(_tax_outputs())
    assert {74, 112, 113} <= ids["customer_transaction_line_ids"]


# ─────────────────────────────────────────────────────────────────────
# AR-P3 DFF — invoice TransactionDFF nested under the invoice
# The DFF hangs directly off the invoice (not under a line). It carries
# only a context string and no id of its own (CustomerTrxId echoes the
# parent), so there is nothing to hallucination-check: the test confirms
# the schema accepts a 'dff' object and it passes validation cleanly.
# ─────────────────────────────────────────────────────────────────────


def _dff_outputs() -> dict[str, list[dict]]:
    """Executor output for 'AR invoice 1002 and its DFF values': the
    invoice plus its TransactionDFF row (context 'DOO')."""
    return {
        "receivables_invoices": [
            {"CustomerTransactionId": 1002, "TransactionNumber": "5"},
        ],
        "receivablesinvoicetransactiondff": [
            {
                "CustomerTrxId": 1002,
                "__FLEX_Context": "DOO",
                "__FLEX_Context_DisplayValue": None,
            },
        ],
    }


def _dff_response(context: str) -> ReceivablesInvoiceResponse:
    """Build an AR-invoice response with a DFF nested under the invoice,
    using the given context value."""
    return ReceivablesInvoiceResponse(
        summary="One invoice with a DFF context.",
        receivables_invoices=[
            ReceivablesInvoiceRecord(
                customer_transaction_id=1002,
                transaction_number="5",
                dff=ReceivablesInvoiceTransactionDFFInfo(
                    context=context,
                    context_display_value="",
                ),
            )
        ],
    )


def test_validate_passes_for_nested_dff() -> None:
    """A DFF nested under the invoice passes validation — it has no id to
    check, so any context value is accepted as long as the invoice id is
    valid."""
    _validate_no_hallucinated_ids(_dff_response("DOO"), _dff_outputs())


def test_validate_passes_for_empty_dff_context() -> None:
    """An empty DFF context still validates — the DFF carries no id, so an
    absent context is not a hallucination."""
    _validate_no_hallucinated_ids(_dff_response(""), _dff_outputs())


def test_dff_response_still_guards_the_invoice_id() -> None:
    """The invoice id is still validated even on a DFF-bearing response: a
    bad invoice id (999) is caught, DFF notwithstanding."""
    bad = _dff_response("DOO")
    bad.receivables_invoices[0].customer_transaction_id = 999
    with pytest.raises(HallucinationError) as exc_info:
        _validate_no_hallucinated_ids(bad, _dff_outputs())
    assert "999" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────
# AR-P4 credit memos — rooted list with a total.
# CreditMemo shares the CustomerTransactionId id space with AR invoices,
# so its ids are harvested into customer_transaction_ids (no separate set).
# The validator cross-checks each listed memo's id; total_credit is a
# copied scalar, not an id, so it is not cross-checked.
# ─────────────────────────────────────────────────────────────────────


def _credit_memo_outputs() -> dict[str, list[dict]]:
    """Executor output for 'list recent credit memos': the credit_memos
    bucket. The wrapper stamps total_credit onto EACH row (so it survives
    the executor's items-only unwrap), so every memo carries the same
    total_credit — the raw sum of EnteredAmount (a positive memo nets
    against the negatives). The bucket is a list of dicts; there is NO
    top-level total_credit key (the executor discards non-items keys)."""
    total = 9850  # -150 + 10000
    return {
        "credit_memos": [
            {
                "CustomerTransactionId": 300000313072555,
                "TransactionNumber": "11001",
                "TransactionDate": "2026-07-09",
                "EnteredAmount": -150,
                "CreditMemoCurrency": "USD",
                "CreditMemoStatus": "Complete",
                "BillToCustomerName": "DMART",
                "BillToCustomerNumber": "26360",
                "total_credit": total,
            },
            {
                "CustomerTransactionId": 300000308625094,
                "TransactionNumber": "1001",
                "TransactionDate": "2026-04-26",
                "EnteredAmount": 10000,
                "CreditMemoCurrency": "USD",
                "CreditMemoStatus": "Incomplete",
                "BillToCustomerName": "Digital Customer 1",
                "BillToCustomerNumber": "10001",
                "total_credit": total,
            },
        ],
    }


def _credit_memo_response(total: float) -> CreditMemoListResponse:
    """Build a credit-memo response listing the two memos above, with the
    given total_credit."""
    return CreditMemoListResponse(
        summary="Two credit memos, netting to the given total.",
        credit_memos=[
            CreditMemoRecord(
                customer_transaction_id=300000313072555,
                transaction_number="11001",
                transaction_date="2026-07-09",
                entered_amount=-150,
                currency="USD",
                status="Complete",
                customer_name="DMART",
                customer_number="26360",
            ),
            CreditMemoRecord(
                customer_transaction_id=300000308625094,
                transaction_number="1001",
                transaction_date="2026-04-26",
                entered_amount=10000,
                currency="USD",
                status="Incomplete",
                customer_name="Digital Customer 1",
                customer_number="10001",
            ),
        ],
        total_credit=total,
    )


def test_validate_passes_for_well_formed_credit_memos():
    """A credit-memo list whose ids all appear in the executor output
    passes validation."""
    _validate_no_hallucinated_ids(
        _credit_memo_response(9850), _credit_memo_outputs()
    )


def test_validate_passes_for_empty_credit_memo_list():
    """An empty credit-memo list is valid — no ids to check. total_credit
    of 0 is still carried."""
    empty = CreditMemoListResponse(
        summary="No credit memos.", credit_memos=[], total_credit=0
    )
    _validate_no_hallucinated_ids(empty, _credit_memo_outputs())


def test_validate_catches_hallucinated_credit_memo_id():
    """A credit memo whose CustomerTransactionId is not in the executor
    output is caught."""
    bad = _credit_memo_response(9850)
    bad.credit_memos[0].customer_transaction_id = 999999999
    with pytest.raises(HallucinationError) as exc_info:
        _validate_no_hallucinated_ids(bad, _credit_memo_outputs())
    assert "999999999" in str(exc_info.value)


def test_credit_memo_ids_harvested_into_customer_transaction_ids():
    """Credit memos share the AR-invoice id space: their
    CustomerTransactionId values land in customer_transaction_ids, so the
    validator has a set to check against."""
    valid = _collect_valid_ids(_credit_memo_outputs())
    assert 300000313072555 in valid["customer_transaction_ids"]
    assert 300000308625094 in valid["customer_transaction_ids"]


# ─────────────────────────────────────────────────────────────────────
# AR-P5 prompt 6 — the BALANCE-ONLY CustomerAccount shape.
# A balance question resolves the customer to their account and reports
# the two figures that ride on the account record itself; NO transaction
# fetch runs, so there is no 'customertransaction' bucket and the
# record's `transactions` list stays empty. CustomerAccount is NOT a new
# entity (AR-P2b rooted on it), so this was a two-place synthesizer
# change: the transactions_due field and the prompt. These tests pin the
# part that AR-P4 proved is easy to get wrong — that a response with an
# empty child list still passes id-harvest and validation rather than
# blowing up on the absent bucket.
# ─────────────────────────────────────────────────────────────────────


def _balance_only_outputs() -> dict[str, list[dict]]:
    """Executor output for 'show me the account balance for customer X'.

    ONE bucket only. The plan is a single step (the planner skips Block 3
    when balance_only is set), so there is deliberately no
    'customer_transactions' bucket here — that absence is the whole point
    of the shape. Figures are the live pod values for AccountId
    300000047368512; note the two do NOT reconcile, which is correct — they
    are independent fields, not a balance and its breakdown.
    """
    return {
        "customer_accounts": [
            {
                "AccountId": 300000047368512,
                "AccountNumber": "26360",
                "CustomerName": "ABC Application Software",
                "CustomerId": 100000000395795,
                "TotalOpenReceivablesForAccount": 678923.69,
                "TotalTransactionsDueForAccount": 699039.33,
            }
        ]
    }


def _balance_only_response() -> CustomerAccountResponse:
    """The two-sentence balance answer, with `transactions` left empty."""
    return CustomerAccountResponse(
        summary=(
            "The customer ABC Application Software (account 26360) has open "
            "receivables totaling 678923.69. The total amount of "
            "transactions due for this account is 699039.33."
        ),
        customer_accounts=[
            CustomerAccountRecord(
                account_id=300000047368512,
                account_number="26360",
                customer_name="ABC Application Software",
                open_receivables=678923.69,
                transactions_due=699039.33,
            )
        ],
    )


def test_balance_only_response_leaves_transactions_empty():
    """The record defaults `transactions` to [] when none were fetched.

    Guards the shape itself: a balance answer must be constructible
    WITHOUT supplying transactions, since no transaction step ran.
    """
    response = _balance_only_response()
    assert response.customer_accounts[0].transactions == []
    assert response.customer_accounts[0].transactions_due == 699039.33


def test_validate_passes_for_balance_only_shape():
    """An empty child list must not trip the validator.

    AR-P4's bug surfaced when a fixture crashed _collect_valid_ids, not by
    inspection — so this asserts the balance-only shape survives the real
    validator against real executor output.
    """
    _validate_no_hallucinated_ids(
        _balance_only_response(), _balance_only_outputs()
    )


def test_validate_catches_hallucinated_account_id_in_balance_shape():
    """The account id is still cross-checked when transactions are absent.

    Dropping the child bucket must not weaken validation of the parent.
    """
    bad = _balance_only_response()
    bad.customer_accounts[0].account_id = 999999999
    with pytest.raises(HallucinationError) as exc_info:
        _validate_no_hallucinated_ids(bad, _balance_only_outputs())
    assert "999999999" in str(exc_info.value)


def test_balance_only_outputs_harvest_account_id_and_no_transaction_ids():
    """Id-harvest over a single-bucket output.

    account_id lands in customer_account_ids; the transaction set stays
    empty because no transaction bucket exists. The empty set matters —
    it is what the validator checks the (absent) transactions against.
    """
    valid = _collect_valid_ids(_balance_only_outputs())
    assert 300000047368512 in valid["customer_account_ids"]
    assert valid["customer_account_transaction_ids"] == set()


def test_transactions_due_is_optional_for_pre_ar_p5_records():
    """Back-compat: the AR-P2b shape omitted transactions_due entirely.

    The field is defaulted, so an older-style record still constructs —
    this is what keeps the existing customer-invoices path unchanged.
    """
    record = CustomerAccountRecord(
        account_id=300000047368512,
        account_number="26360",
        customer_name="ABC Application Software",
        open_receivables=678923.69,
    )
    assert record.transactions_due is None


# ─────────────────────────────────────────────────────────────────────
# AR-P5 prompt 7 — the account's CREDIT MEMOS, nested under the account.
# A customer-scoped memo question resolves the customer to their account
# and traverses to that account's creditMemos child. This is a FOUR-place
# synthesizer change, not five: AccountCreditMemo is reached by traversal
# and nests under CustomerAccountRecord, so the registry and validator
# dispatch already cover the response type.
# The id space is the thing to get right — CreditMemoId is NOT the
# CustomerTransactionId that AR-P4's top-level CreditMemo uses, so it
# gets its own harvest set and the validator checks against that set
# specifically. These tests pin exactly that.
# ─────────────────────────────────────────────────────────────────────


def _account_memos_outputs() -> dict[str, list[dict]]:
    """Executor output for 'show credit memos for ABC Application Software'.

    Two buckets: the resolved account, then its memos. Values are live pod
    rows for AccountId 300000047368512 (newest first, as the tool returns
    them). Amounts are negative, which is normal for a credit memo.
    """
    return {
        "customer_accounts": [
            {
                "AccountId": 300000047368512,
                "AccountNumber": "26360",
                "CustomerName": "ABC Application Software",
                "CustomerId": 100000000395795,
                "TotalOpenReceivablesForAccount": 678923.69,
                "TotalTransactionsDueForAccount": 699039.33,
            }
        ],
        "account_credit_memos": [
            {
                "CreditMemoId": 1284799,
                "CreditMemoNumber": "1358582",
                "CreditMemoDate": "2023-07-15",
                "TotalOriginalAmount": -215.33,
                "TotalBalanceAmount": -215.33,
                "CreditMemoStatus": "Open",
                "CreditMemoCurrency": "USD",
            },
            {
                "CreditMemoId": 1284797,
                "CreditMemoNumber": "1358552",
                "CreditMemoDate": "2023-07-13",
                "TotalOriginalAmount": -441.53,
                "TotalBalanceAmount": -441.53,
                "CreditMemoStatus": "Open",
                "CreditMemoCurrency": "USD",
            },
        ],
    }


def _account_memos_response() -> CustomerAccountResponse:
    """The account with its two memos nested underneath."""
    return CustomerAccountResponse(
        summary=(
            "ABC Application Software (account 26360) has 2 recent credit "
            "memos: 1358582 for -215.33 and 1358552 for -441.53, both open."
        ),
        customer_accounts=[
            CustomerAccountRecord(
                account_id=300000047368512,
                account_number="26360",
                customer_name="ABC Application Software",
                open_receivables=678923.69,
                transactions_due=699039.33,
                credit_memos=[
                    AccountCreditMemoInfo(
                        credit_memo_id=1284799,
                        credit_memo_number="1358582",
                        credit_memo_date="2023-07-15",
                        amount=-215.33,
                        balance=-215.33,
                        status="Open",
                        currency="USD",
                    ),
                    AccountCreditMemoInfo(
                        credit_memo_id=1284797,
                        credit_memo_number="1358552",
                        credit_memo_date="2023-07-13",
                        amount=-441.53,
                        balance=-441.53,
                        status="Open",
                        currency="USD",
                    ),
                ],
            )
        ],
    )


def test_collect_valid_ids_harvests_credit_memo_ids_separately():
    """CreditMemoId lands in its OWN set, not the transaction one.

    The whole point of the separate set: AR-P4's CreditMemo keys on
    CustomerTransactionId, this keys on CreditMemoId, and a memo id must
    never validate against the wrong entity's ids.
    """
    valid = _collect_valid_ids(_account_memos_outputs())
    assert valid["account_credit_memo_ids"] == {1284799, 1284797}
    assert 300000047368512 in valid["customer_account_ids"]
    # The memo ids must NOT leak into the AR-invoice id space.
    assert valid["customer_transaction_ids"] == set()


def test_validate_passes_for_account_with_credit_memos():
    """The nested-memo shape survives the real validator."""
    _validate_no_hallucinated_ids(
        _account_memos_response(), _account_memos_outputs()
    )


def test_validate_catches_hallucinated_account_credit_memo_id():
    """An invented memo id is caught, and named in the error.

    NOTE the name is deliberately distinct from AR-P4's
    test_validate_catches_hallucinated_credit_memo_id, which covers the
    TOP-LEVEL CreditMemo entity. Two module-level functions with the same
    name silently shadow each other — the second definition wins and the
    first never runs — so the entity has to be in the name.
    """
    bad = _account_memos_response()
    bad.customer_accounts[0].credit_memos[0].credit_memo_id = 999999
    with pytest.raises(HallucinationError) as exc_info:
        _validate_no_hallucinated_ids(bad, _account_memos_outputs())
    message = str(exc_info.value)
    assert "999999" in message
    assert "account_credit_memo_ids" in message


def test_credit_memo_id_is_not_validated_against_transaction_ids():
    """A real AR-invoice id must NOT satisfy the memo check.

    Guards the id-space confusion directly: 300000248096352 is a genuine
    CustomerTransactionId from the AR anchors, but it is not a
    CreditMemoId, so using it as one must still fail.
    """
    outputs = _account_memos_outputs()
    outputs["receivables_invoices"] = [
        {"CustomerTransactionId": 300000248096352}
    ]
    bad = _account_memos_response()
    bad.customer_accounts[0].credit_memos[0].credit_memo_id = 300000248096352
    with pytest.raises(HallucinationError):
        _validate_no_hallucinated_ids(bad, outputs)


def test_credit_memos_default_empty_for_non_memo_queries():
    """An account fetched without the memo bucket has no memos.

    Keeps AR-P2b/P2c and prompt 6 unchanged: the field is defaulted, so
    every existing CustomerAccount shape still constructs.
    """
    record = CustomerAccountRecord(
        account_id=300000047368512,
        account_number="26360",
        customer_name="ABC Application Software",
        open_receivables=678923.69,
    )
    assert record.credit_memos == []


# ─────────────────────────────────────────────────────────────────────
# AR-P5 prompt 8 — the account's RECEIPTS, nested under the account.
# Same traversal shape as prompt 7's credit memos, so again a four-place
# change rather than five. The distinguishing risk here is the id space:
# StandardReceiptId is a FIFTH AR id space and, uniquely, it MIXES
# WIDTHS within one collection — backfilled rows carry small ints, recent
# rows large ones. Nothing may infer anything from an id's magnitude, and
# a receipt id must never validate against another entity's ids.
# ─────────────────────────────────────────────────────────────────────


def _account_receipts_outputs() -> dict[str, list[dict]]:
    """Executor output for 'show receipts for ABC Application Software'.

    Live pod rows for AccountId 300000047368512, newest first. The two
    newest are Unapplied cash (received, not yet matched to an invoice),
    which is normal; the third is an older Applied row carrying a SMALL
    id — the width mix is deliberate and load-bearing for these tests.
    """
    return {
        "customer_accounts": [
            {
                "AccountId": 300000047368512,
                "AccountNumber": "26360",
                "CustomerName": "ABC Application Software",
                "CustomerId": 100000000395795,
                "TotalOpenReceivablesForAccount": 678923.69,
                "TotalTransactionsDueForAccount": 699039.33,
            }
        ],
        "account_receipts": [
            {
                "StandardReceiptId": 300000313660599,
                "ReceiptNumber": "PA-2026-000145",
                "ReceiptDate": "2026-06-30",
                "Amount": 1347.42,
                "Currency": "USD",
                "ReceiptMethod": "Lockbox",
                "State": "Unapplied",
                "ProcessStatus": "Open",
                "UnappliedAmount": 1347.42,
                "CustomerSite": None,
            },
            {
                "StandardReceiptId": 534534,
                "ReceiptNumber": "498949",
                "ReceiptDate": "2024-07-03",
                "Amount": 1515.98,
                "Currency": "USD",
                "ReceiptMethod": "Check (Directly/No Remit)",
                "State": "Applied",
                "ProcessStatus": "Closed",
                "UnappliedAmount": 0,
                "CustomerSite": None,
            },
        ],
    }


def _account_receipts_response() -> CustomerAccountResponse:
    """The account with its two receipts nested underneath."""
    return CustomerAccountResponse(
        summary=(
            "ABC Application Software (account 26360) has 2 recent "
            "receipts: PA-2026-000145 for 1347.42 USD, still unapplied, "
            "and 498949 for 1515.98 USD, applied."
        ),
        customer_accounts=[
            CustomerAccountRecord(
                account_id=300000047368512,
                account_number="26360",
                customer_name="ABC Application Software",
                open_receivables=678923.69,
                transactions_due=699039.33,
                receipts=[
                    AccountReceiptInfo(
                        receipt_id=300000313660599,
                        receipt_number="PA-2026-000145",
                        receipt_date="2026-06-30",
                        amount=1347.42,
                        currency="USD",
                        receipt_method="Lockbox",
                        state="Unapplied",
                        unapplied_amount=1347.42,
                    ),
                    AccountReceiptInfo(
                        receipt_id=534534,
                        receipt_number="498949",
                        receipt_date="2024-07-03",
                        amount=1515.98,
                        currency="USD",
                        receipt_method="Check (Directly/No Remit)",
                        state="Applied",
                        unapplied_amount=0,
                    ),
                ],
            )
        ],
    )


def test_collect_valid_ids_harvests_receipt_ids_separately():
    """StandardReceiptId lands in its OWN set, at both widths.

    The width mix is the point: a small id (534534) and a large one
    (300000313660599) must BOTH be harvested, so nothing downstream can
    treat magnitude as a signal.
    """
    valid = _collect_valid_ids(_account_receipts_outputs())
    assert valid["account_receipt_ids"] == {300000313660599, 534534}
    assert 300000047368512 in valid["customer_account_ids"]
    # Receipts must not leak into the memo or AR-invoice id spaces.
    assert valid["account_credit_memo_ids"] == set()
    assert valid["customer_transaction_ids"] == set()


def test_validate_passes_for_account_with_receipts():
    """The nested-receipt shape survives the real validator."""
    _validate_no_hallucinated_ids(
        _account_receipts_response(), _account_receipts_outputs()
    )


def test_validate_catches_hallucinated_account_receipt_id():
    """An invented receipt id is caught, and named in the error."""
    bad = _account_receipts_response()
    bad.customer_accounts[0].receipts[0].receipt_id = 999999999
    with pytest.raises(HallucinationError) as exc_info:
        _validate_no_hallucinated_ids(bad, _account_receipts_outputs())
    message = str(exc_info.value)
    assert "999999999" in message
    assert "account_receipt_ids" in message


def test_receipt_id_is_not_validated_against_credit_memo_ids():
    """A real CreditMemoId must NOT satisfy the receipt check.

    Both are AR account children reached the same way, so conflating
    their id sets is the plausible mistake. 1284799 is a genuine
    CreditMemoId from the anchor account — valid, but not a receipt.
    """
    outputs = _account_receipts_outputs()
    outputs["account_credit_memos"] = [{"CreditMemoId": 1284799}]
    bad = _account_receipts_response()
    bad.customer_accounts[0].receipts[0].receipt_id = 1284799
    with pytest.raises(HallucinationError):
        _validate_no_hallucinated_ids(bad, outputs)


def test_account_can_carry_receipts_and_memos_together():
    """Both children can nest under one account without interfering.

    Nothing routes both today, but the record allows it and the
    validator must check each against its own set rather than merging
    them.
    """
    outputs = _account_receipts_outputs()
    outputs["account_credit_memos"] = [
        {
            "CreditMemoId": 1284799,
            "CreditMemoNumber": "1358582",
            "CreditMemoDate": "2023-07-15",
            "TotalOriginalAmount": -215.33,
        }
    ]
    response = _account_receipts_response()
    response.customer_accounts[0].credit_memos = [
        AccountCreditMemoInfo(
            credit_memo_id=1284799,
            credit_memo_number="1358582",
            credit_memo_date="2023-07-15",
            amount=-215.33,
        )
    ]
    _validate_no_hallucinated_ids(response, outputs)


def test_receipts_default_empty_for_non_receipt_queries():
    """An account fetched without the receipts bucket has no receipts.

    Keeps prompts 6 and 7 unchanged: the field is defaulted, so every
    existing CustomerAccount shape still constructs.
    """
    record = CustomerAccountRecord(
        account_id=300000047368512,
        account_number="26360",
        customer_name="ABC Application Software",
        open_receivables=678923.69,
    )
    assert record.receipts == []

