"""
Tests for local aggregation synthesis — the five shapes that
test_synthesizer_aggregation.py does not cover.

That file owns supplier_spend_ranking (it predates this work and its
fixtures were already there). This one covers the rest:

    supplier_po_value_ranking     ranking, supplier_id not supplier_number
    exposure_ranking              ranking, NO truncated key, two measures
    po_status_breakdown           distribution, carries a grand total
    receipt_method_distribution   distribution, total_amount means two things
    open_po_summary               no rows at all

WHY THESE FIVE NEEDED THEIR OWN TESTS
The six shapes were enumerated before the builders were written precisely
because they disagree, and every disagreement below is one a function
generalised from supplier_spend_ranking alone would have got wrong. A
test file that only exercised the spend ranking would pass while four
shapes were broken.

WHAT IS NOT TESTED HERE
Whether the summaries are the RIGHT things to say. These assert that the
figures are the bucket's own and that absent data produces no statement.
Whether "leads with X — 2.4x the next" is worth printing above a table is
a judgement, and the run output answers it, not pytest.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from spire.synthesizer.aggregation import (
    ExposureRankingResponse,
    OpenPOSummaryResponse,
    POStatusBreakdownResponse,
    ReceiptMethodDistributionResponse,
    SupplierPOValueRankingResponse,
    build_local_aggregation_response,
)
from spire.synthesizer.ranking_summary import local_aggregation_summary
from spire.synthesizer.synthesizer import (
    UnsupportedEntityError,
    synthesize_response,
)


def _forbidden_llm() -> MagicMock:
    """An LLM that fails the test if anything touches it. See
    test_synthesizer_aggregation._forbidden_llm for why raising matters."""
    llm = MagicMock()
    llm.with_structured_output.side_effect = AssertionError(
        "synthesize_response called the LLM on a local aggregation path"
    )
    return llm


def _wrap(bucket: dict) -> dict[str, list[dict]]:
    """Executor shape: the tool's dict inside a one-element list."""
    return {"aggregation": [bucket]}


# ─────────────────────────────────────────────────────────────────────
# Fixtures — one per shape, field names copied from the tools
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def po_value_bucket() -> dict:
    """supplier_po_value_ranking.

    supplier_ID, not supplier_number: a PO header carries SupplierId and
    Supplier only — asking /purchaseOrders for SupplierNumber returns
    HTTP 400. A builder copying the spend ranking would read an absent
    key and write an empty string.
    """
    return {
        "shape": "supplier_po_value_ranking",
        "status": "OPEN",
        "total_suppliers": 40,
        "returned": 2,
        "truncated": False,
        "rows": [
            {"supplier": "EIP Inc", "supplier_id": 300000047,
             "total_ordered": 800000.0, "po_count": 12},
            {"supplier": "JGA", "supplier_id": 300000048,
             "total_ordered": 200000.0, "po_count": 5},
        ],
    }


@pytest.fixture
def exposure_bucket() -> dict:
    """exposure_ranking.

    No truncated key at all — the endpoint has 435 rows and is fetched
    whole, so the tool has nothing to flag. Two measures per row, and the
    tool sorts on TotalOpenReceivablesForAccount only.
    """
    return {
        "shape": "exposure_ranking",
        "total_accounts": 435,
        "returned": 2,
        "rows": [
            {"account_id": 300000101, "account_number": "26360",
             "customer_name": "Santa Clara", "open_receivables": 90000.0,
             "transactions_due": 1200.0},
            {"account_id": 300000102, "account_number": "26370",
             "customer_name": "Vision Corp", "open_receivables": 30000.0,
             "transactions_due": 400.0},
        ],
    }


@pytest.fixture
def status_bucket() -> dict:
    """po_status_breakdown — a distribution, so it carries a grand total."""
    return {
        "shape": "po_status_breakdown",
        "total_pos": 3362,
        "total_ordered": 1000000.0,
        "truncated": False,
        "rows": [
            {"status": "CLOSED", "po_count": 2000, "total_ordered": 620000.0},
            {"status": "OPEN", "po_count": 1362, "total_ordered": 380000.0},
        ],
    }


@pytest.fixture
def receipt_bucket() -> dict:
    """receipt_method_distribution.

    total_amount appears at BOTH levels: per row it is the method's
    total, at the top level it is the grand total across methods. Reading
    the wrong one gives a share of itself — 100%, every time, silently.
    """
    return {
        "shape": "receipt_method_distribution",
        "total_receipts": 435,
        "total_amount": 500000.0,
        "truncated": False,
        "rows": [
            {"receipt_method": "Lockbox", "receipt_count": 300,
             "total_amount": 400000.0},
            {"receipt_method": "Check", "receipt_count": 135,
             "total_amount": 100000.0},
        ],
    }


@pytest.fixture
def open_po_bucket() -> dict:
    """open_po_summary — three scalars, no rows key at all."""
    return {
        "shape": "open_po_summary",
        "po_count": 201,
        "total_ordered": 45123456.78,
        "supplier_count": 37,
        "truncated": False,
    }


# ─────────────────────────────────────────────────────────────────────
# Every shape builds locally, and none of them reaches the LLM
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "fixture_name,expected_type",
    [
        ("po_value_bucket", SupplierPOValueRankingResponse),
        ("exposure_bucket", ExposureRankingResponse),
        ("status_bucket", POStatusBreakdownResponse),
        ("receipt_bucket", ReceiptMethodDistributionResponse),
        ("open_po_bucket", OpenPOSummaryResponse),
    ],
)
def test_every_shape_synthesizes_without_an_llm(
    request, fixture_name, expected_type
):
    bucket = request.getfixturevalue(fixture_name)
    llm = _forbidden_llm()
    result = synthesize_response(_wrap(bucket), target_entity="", llm=llm)
    assert isinstance(result, expected_type)
    llm.with_structured_output.assert_not_called()


# ─────────────────────────────────────────────────────────────────────
# Field mapping — the tools and the schemas spell things differently
# ─────────────────────────────────────────────────────────────────────


def test_po_value_maps_supplier_to_supplier_name_and_keeps_id(
    po_value_bucket,
):
    """`supplier` -> `supplier_name`, and supplier_id survives as an int.

    This mapping was previously inferred by the model on every call. An
    inference that succeeds ninety-nine times in a hundred is a silent
    wrong answer on the hundredth.
    """
    result = build_local_aggregation_response(po_value_bucket)
    assert [s.supplier_name for s in result.suppliers] == ["EIP Inc", "JGA"]
    assert [s.supplier_id for s in result.suppliers] == [300000047, 300000048]
    assert result.suppliers[0].total_ordered == 800000.0
    assert result.suppliers[0].po_count == 12


def test_exposure_keeps_both_measures(exposure_bucket):
    """Both measures survive even though only one is ranked on."""
    result = build_local_aggregation_response(exposure_bucket)
    assert result.accounts[0].customer_name == "Santa Clara"
    assert result.accounts[0].open_receivables == 90000.0
    assert result.accounts[0].transactions_due == 1200.0


def test_receipt_distribution_keeps_row_and_grand_totals_apart(
    receipt_bucket,
):
    """The row's total_amount and the bucket's total_amount are different
    numbers and must not be conflated."""
    result = build_local_aggregation_response(receipt_bucket)
    assert result.total_amount == 500000.0
    assert result.methods[0].total_amount == 400000.0
    assert result.total_receipts == 435


def test_status_breakdown_carries_grand_figures(status_bucket):
    result = build_local_aggregation_response(status_bucket)
    assert result.total_pos == 3362
    assert result.total_ordered == 1000000.0
    assert [s.status for s in result.statuses] == ["CLOSED", "OPEN"]


def test_open_po_summary_carries_figures_with_an_empty_summary(
    open_po_bucket,
):
    """The one shape with no table — and no summary either.

    This test asserted the opposite until 2026-08-04. It was written from
    the reasoning that a shape with no rows beneath it needs its figures
    in the summary, which sounded right and was wrong: the display
    formatter already renders po_count, total_ordered and supplier_count
    for this response. Measured against the pod, the two together read:

        1,085 open purchase orders worth 32,790,396.90, across 66 suppliers.
        Open PO count: 1085, total ordered: 32,790,396.90, suppliers: 66

    An empty summary is the correct answer here, and the response still
    carries every figure — which is what this now checks.
    """
    result = build_local_aggregation_response(open_po_bucket)
    assert result.po_count == 201
    assert result.total_ordered == 45123456.78
    assert result.supplier_count == 37
    assert result.summary == ""


def test_open_po_summary_states_truncation_because_the_formatter_cannot(
    open_po_bucket,
):
    """Truncation is the one thing the formatter line does not carry.

    So it is the one thing the summary keeps for this shape — the
    difference between "32,790,396.90 committed" and "at least
    32,790,396.90 committed" is not cosmetic.
    """
    open_po_bucket["truncated"] = True
    result = build_local_aggregation_response(open_po_bucket)
    assert "lower bounds" in result.summary
    # And still no restatement of the figures the formatter prints.
    assert "201" not in result.summary


def test_open_po_summary_says_zero_plainly(open_po_bucket):
    """Three zeroes from the formatter read as a malfunction, not an
    answer. This is the one case where a sentence beats the scalars."""
    open_po_bucket["po_count"] = 0
    open_po_bucket["total_ordered"] = 0.0
    open_po_bucket["supplier_count"] = 0
    result = build_local_aggregation_response(open_po_bucket)
    assert result.summary == "No open purchase orders."


# ─────────────────────────────────────────────────────────────────────
# Summary rules — what is said, and what is deliberately not
# ─────────────────────────────────────────────────────────────────────


def test_distribution_states_the_dominant_share(status_bucket):
    """A distribution carries its own grand total, so the share is real.

    620000 / 1000000 = 62%. This is the one place a percentage is
    honest — a RANKING cannot say it, because the tool discards the
    measure for everything below the top-N cut.
    """
    lines = local_aggregation_summary(status_bucket)
    joined = "\n".join(lines)
    assert "CLOSED is the largest" in joined
    assert "62%" in joined


def test_ranking_never_states_a_share(po_value_bucket):
    """No percentage on a ranking, ever.

    total_suppliers is a COUNT of distinct suppliers, not a sum of their
    value. Computing a share against the visible rows would print 100%
    every time — the arithmetic-over-a-sample defect this work removes.
    """
    joined = "\n".join(local_aggregation_summary(po_value_bucket))
    assert "%" not in joined


def test_absent_truncated_key_produces_no_truncation_sentence(
    exposure_bucket,
):
    """exposure_ranking has no truncated key. Absent must not read as
    False-with-a-note, and must not raise."""
    joined = "\n".join(local_aggregation_summary(exposure_bucket))
    assert "lower bound" not in joined
    assert "page cap" not in joined


def test_truncated_true_says_lower_bound(po_value_bucket):
    po_value_bucket["truncated"] = True
    joined = "\n".join(local_aggregation_summary(po_value_bucket))
    assert "lower bounds" in joined


def test_truncation_note_counts_the_SOURCE_rows_not_the_ranked_entity(
    po_value_bucket,
):
    """A ranking's truncation counts are fetched rows, not ranked ones.

    THE BUG THIS EXISTS TO CATCH, found while wiring the note and not by
    any test: the obvious label for the sentence is entity_label, which
    on a ranking is "suppliers". But total_available and examined count
    what was FETCHED — purchase orders here, invoices for the spend
    ranking — and the tool then GROUPS those into suppliers. Labelling
    the note with entity_label produces

        PARTIAL: 25,000 of 48,931 suppliers examined

    over a pod holding 117 suppliers. A wrong number, stated with total
    confidence, in the one sentence whose whole job is to tell the reader
    how much to trust the others.

    Same class as the two total_amount fields on the receipt
    distribution: a name that reads right in one place and means
    something else in another. Hence source_label, per shape.
    """
    po_value_bucket["truncated"] = True
    po_value_bucket["total_available"] = 15839
    po_value_bucket["examined"] = 10000

    joined = "\n".join(local_aggregation_summary(po_value_bucket))

    assert "10,000 of 15,839 purchase orders examined" in joined
    # The ranked entity must NOT be what the note counts.
    assert "15,839 suppliers" not in joined
    assert "of 15,839 suppliers" not in joined


def test_truncation_note_states_the_share_when_counts_are_present(
    po_value_bucket,
):
    """PARTIAL, with both numbers and a percentage.

    "Lower bound" alone does not tell a reader whether the shortfall is
    one row or half the collection, and that is the only thing they need
    in order to judge the figures below it. Measured on /invoices the
    same day: 25,000 of 48,931, which is 51% — a footnote that size is
    not a footnote.
    """
    po_value_bucket["truncated"] = True
    po_value_bucket["total_available"] = 15839
    po_value_bucket["examined"] = 10000

    lines = local_aggregation_summary(po_value_bucket)

    assert lines[0].startswith("PARTIAL:")
    assert "63%" in lines[0]
    assert "lower bounds" in lines[0]


def test_truncation_note_comes_first(po_value_bucket):
    """Before the figures, not after them.

    It sat last until 2026-08-04, which is where the model put it too:
    state the numbers, then hedge. If an answer covers 63% of the
    collection, that belongs above the numbers — it decides whether they
    are worth reading.
    """
    po_value_bucket["truncated"] = True
    po_value_bucket["total_available"] = 15839
    po_value_bucket["examined"] = 10000

    lines = local_aggregation_summary(po_value_bucket)

    assert lines[0].startswith("PARTIAL:")
    assert any("leads with" in line for line in lines[1:])


def test_truncation_note_falls_back_without_counts(po_value_bucket):
    """An older tool, or a pod that returned no count, still gets a note.

    total_results returns None when Fusion omits totalResults, and every
    behaviour that depends on it degrades rather than failing. Here that
    means the original sentence — everything that can honestly be said
    without a denominator.
    """
    po_value_bucket["truncated"] = True
    po_value_bucket.pop("total_available", None)
    po_value_bucket.pop("examined", None)

    joined = "\n".join(local_aggregation_summary(po_value_bucket))

    assert "PARTIAL" not in joined
    assert "page cap" in joined
    assert "lower bounds" in joined


def test_counts_line_omitted_when_nothing_is_hidden(po_value_bucket):
    """"Top 2 of 2" restates the table. The count line earns its place
    only when the total is a number the reader cannot see."""
    po_value_bucket["total_suppliers"] = 2
    joined = "\n".join(local_aggregation_summary(po_value_bucket))
    assert "Top 2 of" not in joined
    # The leader statement still stands — it is not a count.
    assert "EIP Inc leads" in joined


def test_gap_ratio_skipped_when_second_row_is_zero(po_value_bucket):
    """A zero divisor has no ratio. Say the leader without one rather
    than computing something unsayable."""
    po_value_bucket["rows"][1]["total_ordered"] = 0.0
    joined = "\n".join(local_aggregation_summary(po_value_bucket))
    assert "EIP Inc leads with 800,000.00." in joined
    assert "x the next" not in joined


def test_gap_ratio_skipped_when_measure_is_none(exposure_bucket):
    """Exposure measures are nullable — a null second row is not a zero."""
    exposure_bucket["rows"][1]["open_receivables"] = None
    joined = "\n".join(local_aggregation_summary(exposure_bucket))
    assert "Santa Clara leads with 90,000.00." in joined
    assert "x the next" not in joined


def test_zero_rows_is_an_answer_not_an_error(po_value_bucket):
    """Zero rows gets said plainly (OUT-01), not raised and not silent."""
    po_value_bucket["rows"] = []
    po_value_bucket["returned"] = 0
    po_value_bucket["total_suppliers"] = 0
    lines = local_aggregation_summary(po_value_bucket)
    assert lines == ["No suppliers matched."]


def test_single_row_states_the_leader_without_a_gap(po_value_bucket):
    po_value_bucket["rows"] = po_value_bucket["rows"][:1]
    po_value_bucket["returned"] = 1
    joined = "\n".join(local_aggregation_summary(po_value_bucket))
    assert "EIP Inc leads with 800,000.00." in joined
    assert "x the next" not in joined


# ─────────────────────────────────────────────────────────────────────
# Unknown shapes fall through — they must not be treated as empty
# ─────────────────────────────────────────────────────────────────────


def test_unknown_shape_returns_none_from_the_builder():
    """None means "no local builder", not "no answer".

    A seventh aggregation tool added later must keep working on the model
    path until someone writes its builder. If this returned an empty
    response instead, that tool would silently print nothing.
    """
    assert build_local_aggregation_response({"shape": "future_tool"}) is None
    assert local_aggregation_summary({"shape": "future_tool"}) is None


def test_unknown_shape_falls_through_to_the_schema_lookup():
    """And the fall-through reaches the existing error, unchanged."""
    llm = MagicMock()
    with pytest.raises(UnsupportedEntityError):
        synthesize_response(
            _wrap({"shape": "future_tool", "rows": []}),
            target_entity="",
            llm=llm,
        )
