"""
Tests for the synthesizer's aggregation ranking branch (feature 7).

Mirrors test_synthesizer.py conventions: a MagicMock LLM whose
with_structured_output().invoke() returns a prebuilt structured response,
so no network/LLM is needed. Covers schema selection from data shape
(not target_entity), id harvesting from nested ranking rows, the
hallucination guard, and that the non-aggregation path is unchanged.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from spire.synthesizer.synthesizer import (
    HallucinationError,
    SupplierSpendRankingResponse,
    SupplierSpendRow,
    UnsupportedEntityError,
    _collect_valid_ids,
    _is_supplier_spend_ranking,
    synthesize_response,
)


def _mock_llm(structured_output) -> MagicMock:
    llm = MagicMock()
    structured = MagicMock()
    structured.invoke.return_value = structured_output
    llm.with_structured_output.return_value = structured
    return llm


@pytest.fixture
def ranking_outputs() -> dict[str, list[dict]]:
    """Executor output for an aggregation: one ranking object under the
    'aggregation' bucket (wrapped in a one-element list by the executor)."""
    return {
        "aggregation": [
            {
                "shape": "supplier_spend_ranking",
                "date_from": "2022-01-01",
                "date_to": "2023-01-01",
                "total_suppliers": 22,
                "returned": 2,
                "truncated": True,
                "rows": [
                    {"supplier": "Staffing Services", "supplier_number": "1253",
                     "total_spend": 119909.0, "invoice_count": 40},
                    {"supplier": "Acme", "supplier_number": "1001",
                     "total_spend": 50000.0, "invoice_count": 12},
                ],
            }
        ]
    }


@pytest.fixture
def well_formed_ranking() -> SupplierSpendRankingResponse:
    return SupplierSpendRankingResponse(
        summary="Top suppliers by spend, Jan-Dec 2022.",
        suppliers=[
            SupplierSpendRow(supplier_name="Staffing Services",
                             supplier_number="1253",
                             total_spend=119909.0, invoice_count=40),
            SupplierSpendRow(supplier_name="Acme", supplier_number="1001",
                             total_spend=50000.0, invoice_count=12),
        ],
        truncation_notes=["aggregation: based on a sample; may understate."],
    )


def test_shape_detection_true_for_ranking(ranking_outputs):
    assert _is_supplier_spend_ranking(ranking_outputs) is True


def test_shape_detection_false_for_entity_list():
    assert _is_supplier_spend_ranking(
        {"suppliers": [{"SupplierNumber": "S1"}]}
    ) is False


def test_collect_valid_ids_harvests_ranking_rows(ranking_outputs):
    valid = _collect_valid_ids(ranking_outputs)
    assert "1253" in valid["supplier_numbers"]
    assert "1001" in valid["supplier_numbers"]


def test_synthesize_routes_to_ranking_schema(
    ranking_outputs, well_formed_ranking
):
    # target_entity is "" for aggregation; selection must come from the
    # data shape, and the ranking schema must be the one bound.
    llm = _mock_llm(well_formed_ranking)
    result = synthesize_response(ranking_outputs, target_entity="", llm=llm)
    assert result is well_formed_ranking
    llm.with_structured_output.assert_called_once_with(
        SupplierSpendRankingResponse
    )
    assert [s.supplier_number for s in result.suppliers] == ["1253", "1001"]


def test_synthesize_ranking_catches_hallucinated_supplier(ranking_outputs):
    bad = SupplierSpendRankingResponse(
        summary="x",
        suppliers=[
            SupplierSpendRow(supplier_name="Ghost", supplier_number="9999",
                             total_spend=1.0, invoice_count=1),
        ],
        truncation_notes=[],
    )
    llm = _mock_llm(bad)
    with pytest.raises(HallucinationError):
        synthesize_response(ranking_outputs, target_entity="", llm=llm)


def test_non_ranking_empty_target_still_raises():
    # No aggregation shape and an empty target_entity -> unchanged
    # behavior: UnsupportedEntityError.
    llm = _mock_llm(None)
    with pytest.raises(UnsupportedEntityError):
        synthesize_response({"suppliers": []}, target_entity="", llm=llm)
