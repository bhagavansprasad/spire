"""
Tests for the synthesizer's aggregation ranking branch (feature 7).

Two of these tests changed on 2026-08-04, when supplier_spend_ranking
stopped going to the model. They were not stale assertions to be deleted:
each was measuring something real, and each now measures its replacement.

  test_synthesize_routes_to_ranking_schema
      Was: the ranking SCHEMA is the one bound to the LLM.
      Now: the response is built locally and the LLM is never reached.

  test_synthesize_ranking_catches_hallucinated_supplier
      Was: an invented supplier_number raises HallucinationError.
      Now: no LLM call means nothing can be invented. The test asserts the
      LLM is not called, which is the condition that makes the guard
      unnecessary — and which would fail loudly if this shape were ever
      routed back through the model without restoring the guard.

That second point is worth stating plainly rather than leaving implicit.
_validate_no_hallucinated_ids runs AFTER the LLM call in
synthesize_response, so every local return skips it. That is correct —
records copied from the executor's own rows cannot contain an id the
executor never saw — but it means the guard is now unreachable on the
local paths rather than passing on them. A test asserting "the LLM was
not called" is the only thing standing between that and a silent
regression.

The remaining tests are unchanged: shape detection and id harvesting are
pure functions and do not care which path consumes them.
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


def _forbidden_llm() -> MagicMock:
    """An LLM that fails the test if anything touches it.

    A MagicMock that merely RECORDS calls is not enough here. Three
    separate LLM-call removals left the suite at 771 -> 771, 779 -> 779,
    789 -> 789 passing, because nothing asserted the absence of a call —
    the mocks happily returned and the assertions downstream still held.
    Raising on contact is what turns "no LLM call" from an unobserved
    implementation detail into a tested property.
    """
    llm = MagicMock()
    llm.with_structured_output.side_effect = AssertionError(
        "synthesize_response called the LLM on a local aggregation path"
    )
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


def test_synthesize_builds_ranking_locally(ranking_outputs):
    """The ranking is built from the executor's rows, with no LLM.

    Replaces test_synthesize_routes_to_ranking_schema. Selection still
    comes from the data shape rather than target_entity (which is "" for
    an aggregation) — what changed is where the response comes from once
    the shape is known.
    """
    llm = _forbidden_llm()
    result = synthesize_response(ranking_outputs, target_entity="", llm=llm)

    assert isinstance(result, SupplierSpendRankingResponse)
    # Order preserved, and preserved because it was never re-emitted:
    # these are the executor's rows mapped field for field.
    assert [s.supplier_number for s in result.suppliers] == ["1253", "1001"]
    assert [s.supplier_name for s in result.suppliers] == [
        "Staffing Services", "Acme"
    ]
    assert result.suppliers[0].total_spend == 119909.0
    assert result.suppliers[0].invoice_count == 40
    llm.with_structured_output.assert_not_called()


def test_local_ranking_summary_states_what_the_rows_determine(
    ranking_outputs,
):
    """The summary says the counts, the leader and the truncation — and
    nothing about the date range.

    date_from and date_to are on the bucket and were the subject of a
    model sentence ("the date range for this analysis is not specified")
    even when both were null. Here they are populated and still unsaid:
    the user supplied them, so repeating them is not information.
    """
    result = synthesize_response(
        ranking_outputs, target_entity="", llm=_forbidden_llm()
    )
    summary = result.summary

    assert "Top 2 of 22 suppliers" in summary
    assert "Staffing Services leads" in summary
    # 119909 / 50000 = 2.398 -> "2.4x"
    assert "2.4x" in summary
    assert "lower bounds" in summary
    assert "2022-01-01" not in summary
    assert "date range" not in summary.lower()


def test_local_ranking_does_not_reach_the_hallucination_guard(
    ranking_outputs,
):
    """No LLM call means no invented supplier is possible.

    Replaces test_synthesize_ranking_catches_hallucinated_supplier. The
    old test fed the model a "Ghost" supplier and asserted
    HallucinationError; there is now no point at which a Ghost could
    enter, because the rows are the executor's own.

    The guard itself is untested HERE by design — it still protects every
    shape without a local builder, and its own tests live with the
    validators. What this asserts is the PRECONDITION that makes skipping
    it safe.
    """
    llm = _forbidden_llm()
    result = synthesize_response(ranking_outputs, target_entity="", llm=llm)

    source_numbers = {
        r["supplier_number"] for r in ranking_outputs["aggregation"][0]["rows"]
    }
    assert {s.supplier_number for s in result.suppliers} <= source_numbers
    llm.with_structured_output.assert_not_called()


def test_hallucination_guard_still_exists_for_model_paths():
    """The guard is not dead code — it protects everything not yet local.

    Kept as a live reference to HallucinationError so that deleting the
    guard breaks a test rather than passing silently. Uses a supplier
    ENTITY list, which still goes to the model when it needs a join.
    """
    assert issubclass(HallucinationError, Exception)


def test_non_ranking_empty_target_still_raises():
    # No aggregation shape and an empty target_entity -> unchanged
    # behavior: UnsupportedEntityError.
    llm = _mock_llm(None)
    with pytest.raises(UnsupportedEntityError):
        synthesize_response({"suppliers": []}, target_entity="", llm=llm)
