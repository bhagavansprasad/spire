"""F-056 — the F-053 four-bucket shape gets a local synthesizer builder.

F-056: the anchor prompt `List US suppliers with open purchase orders,
include the buyer` returned `Synthesized response: (none)`. The F-053
plan produces FOUR buckets (source suppliers + filtered suppliers +
refetched POs + buyers); every existing local builder is two-bucket, so
the shape fell through to the LLM, which was asked to transcribe 183
records and hit its output-token cap.

The fix adds a fourth detector (`_supplier_pos_buyers`) plus a builder
(`build_suppliers_with_open_pos_and_buyers`), and a routing branch in
`synthesize_response`. These tests cover:

  * the detector's accept and reject shapes (unambiguous role
    signature, exactly-one-of-each role, source/filtered pair
    identified by name suffix);
  * the builder's record mapping (PO count, buyers deduped by
    PersonId, display-name fallback from buyer row to PO row);
  * the routing branch (four-bucket Supplier output does not reach the
    LLM; two-bucket output still takes the F-010/F-053 path).

No LLM, no pod — every fixture is a hand-built dict.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from spire.synthesizer.p2p import (
    _supplier_pos_buyers,
    build_suppliers_with_open_pos_and_buyers,
)
from spire.synthesizer.synthesizer import (
    SupplierResponse,
    synthesize_response,
)


def _forbidden_llm() -> MagicMock:
    """An LLM that fails the test if anything touches it.

    Same pattern as test_f010_filtered_count.py / test_local_aggregation.py.
    A MagicMock that merely records calls is not enough: three separate
    LLM-call removals left the suite's pass count unchanged because
    nothing asserted the absence of a call.
    """
    llm = MagicMock()
    llm.with_structured_output.side_effect = AssertionError(
        "synthesize_response called the LLM on the F-056 four-bucket path"
    )
    return llm


# ─────────────────────────────────────────────────────────────────────
# Fixtures — a realistic four-bucket payload for the anchor prompt.
# ─────────────────────────────────────────────────────────────────────


def _source_suppliers() -> list[dict]:
    """The unfiltered US-supplier bucket: 3 suppliers, all examined."""
    return [
        {"SupplierId": 100, "SupplierNumber": "1252", "Supplier": "Lee Supplies",
         "Status": "ACTIVE"},
        {"SupplierId": 200, "SupplierNumber": "1254", "Supplier": "JGA",
         "Status": "ACTIVE"},
        {"SupplierId": 300, "SupplierNumber": "1256", "Supplier": "US Gas",
         "Status": "ACTIVE"},
    ]


def _filtered_suppliers() -> list[dict]:
    """The parent-filtered subset: suppliers 100 and 200 have open POs;
    300 does not."""
    return [
        {"SupplierId": 100, "SupplierNumber": "1252", "Supplier": "Lee Supplies",
         "Status": "ACTIVE"},
        {"SupplierId": 200, "SupplierNumber": "1254", "Supplier": "JGA",
         "Status": "ACTIVE"},
    ]


def _open_pos() -> list[dict]:
    """The refetched PO bucket: 4 open POs across the two survivors,
    with three distinct BuyerIds (555, 777, 999)."""
    return [
        {"POHeaderId": 1, "OrderNumber": "162300", "StatusCode": "OPEN",
         "SupplierId": 100, "BuyerId": 555, "Buyer": "Calvin Roth"},
        {"POHeaderId": 2, "OrderNumber": "162301", "StatusCode": "OPEN",
         "SupplierId": 100, "BuyerId": 555, "Buyer": "Calvin Roth"},
        {"POHeaderId": 3, "OrderNumber": "162302", "StatusCode": "OPEN",
         "SupplierId": 100, "BuyerId": 777, "Buyer": "May Gee"},
        {"POHeaderId": 4, "OrderNumber": "162303", "StatusCode": "OPEN",
         "SupplierId": 200, "BuyerId": 999, "Buyer": "Eleanor White"},
    ]


def _buyers() -> list[dict]:
    """The buyer lookup bucket: 3 records, one per unique BuyerId."""
    return [
        {"PersonId": 555, "DisplayName": "Calvin Roth"},
        {"PersonId": 777, "DisplayName": "May Gee"},
        {"PersonId": 999, "DisplayName": "Eleanor White"},
    ]


def _four_bucket_outputs() -> dict:
    return {
        "us_suppliers": _source_suppliers(),
        "us_suppliers_has_open_PO": _filtered_suppliers(),
        "open_pos": _open_pos(),
        "buyers": _buyers(),
    }


# ─────────────────────────────────────────────────────────────────────
# Detector — accept
# ─────────────────────────────────────────────────────────────────────


def test_detector_accepts_the_four_bucket_shape():
    """The F-053 anchor-prompt shape is recognized; source bucket is the
    name that does not carry the suffix."""
    result = _supplier_pos_buyers(_four_bucket_outputs())
    assert result is not None
    source, filtered, po, buyer = result
    assert source == "us_suppliers"
    assert filtered == "us_suppliers_has_open_PO"
    assert po == "open_pos"
    assert buyer == "buyers"


def test_detector_is_bucket_name_agnostic():
    """Any names work as long as the roles are unambiguous — the shape is
    identified by content, not by the executor's output_name."""
    outputs = {
        "src": _source_suppliers(),
        "src_has_open_PO": _filtered_suppliers(),
        "any_po_bucket": _open_pos(),
        "any_buyer_bucket": _buyers(),
    }
    result = _supplier_pos_buyers(outputs)
    assert result is not None
    assert result[0] == "src"
    assert result[1] == "src_has_open_PO"


# ─────────────────────────────────────────────────────────────────────
# Detector — reject
# ─────────────────────────────────────────────────────────────────────


def test_detector_rejects_two_bucket_shape():
    """The F-010/F-053 subset (`_supplier_with_open_pos`) is two buckets,
    not four. This detector must not claim it — the upstream two-bucket
    branch must keep handling it."""
    outputs = {
        "us_suppliers": _source_suppliers(),
        "open_pos": _open_pos(),
    }
    assert _supplier_pos_buyers(outputs) is None


def test_detector_rejects_three_bucket_shape():
    """Source + filtered + PO, no buyers. Ambiguous — could be a valid
    three-bucket shape this detector does not own. Rejected."""
    outputs = {
        "us_suppliers": _source_suppliers(),
        "us_suppliers_has_open_PO": _filtered_suppliers(),
        "open_pos": _open_pos(),
    }
    assert _supplier_pos_buyers(outputs) is None


def test_detector_rejects_single_bucket():
    assert _supplier_pos_buyers({"us_suppliers": _source_suppliers()}) is None


def test_detector_rejects_empty_bucket_dict():
    assert _supplier_pos_buyers({}) is None


def test_detector_rejects_two_supplier_buckets_without_name_suffix():
    """Two supplier buckets whose names do NOT follow the source/suffix
    convention are ambiguous — the detector must not guess which is
    which."""
    outputs = {
        "us_suppliers": _source_suppliers(),
        "filtered_suppliers": _filtered_suppliers(),
        "open_pos": _open_pos(),
        "buyers": _buyers(),
    }
    assert _supplier_pos_buyers(outputs) is None


def test_detector_rejects_two_po_buckets():
    """Two PO buckets = ambiguous. Rejected."""
    outputs = {
        "us_suppliers": _source_suppliers(),
        "us_suppliers_has_open_PO": _filtered_suppliers(),
        "open_pos": _open_pos(),
        "open_pos_again": _open_pos(),
        "buyers": _buyers(),
    }
    assert _supplier_pos_buyers(outputs) is None


def test_detector_ignores_empty_buckets():
    """An empty bucket is skipped, not counted as a role. A payload
    with an empty buyer bucket, for example, is not the four-bucket
    shape."""
    outputs = _four_bucket_outputs()
    outputs["buyers"] = []
    assert _supplier_pos_buyers(outputs) is None


# ─────────────────────────────────────────────────────────────────────
# Builder — record mapping
# ─────────────────────────────────────────────────────────────────────


def test_builder_attaches_open_po_counts():
    records = build_suppliers_with_open_pos_and_buyers(
        _filtered_suppliers(), _open_pos(), _buyers()
    )
    assert [r.supplier_id for r in records] == [100, 200]
    assert records[0].open_po_count == 3
    assert records[1].open_po_count == 1


def test_builder_attaches_buyers_per_supplier():
    records = build_suppliers_with_open_pos_and_buyers(
        _filtered_suppliers(), _open_pos(), _buyers()
    )
    lee_buyers = {b.person_id for b in records[0].buyers}
    jga_buyers = {b.person_id for b in records[1].buyers}
    assert lee_buyers == {555, 777}
    assert jga_buyers == {999}


def test_builder_dedupes_buyers_by_person_id():
    """Supplier 100's three POs have BuyerId 555 twice. Only one buyer
    record on that supplier."""
    records = build_suppliers_with_open_pos_and_buyers(
        _filtered_suppliers(), _open_pos(), _buyers()
    )
    lee_buyers = records[0].buyers
    assert len(lee_buyers) == 2
    assert [b.person_id for b in lee_buyers] == [555, 777]


def test_builder_display_name_prefers_buyer_bucket():
    """The buyer row's DisplayName wins over the PO row's Buyer field.
    The buyer fetch (Step 4 of the F-053 plan) is authoritative."""
    po_rows = [
        {"POHeaderId": 1, "SupplierId": 100, "BuyerId": 555,
         "Buyer": "PODisplayNameShouldLose"}
    ]
    buyer_rows = [{"PersonId": 555, "DisplayName": "BuyerBucketWins"}]
    [record] = build_suppliers_with_open_pos_and_buyers(
        _filtered_suppliers()[:1], po_rows, buyer_rows
    )
    assert record.buyers[0].display_name == "BuyerBucketWins"


def test_builder_display_name_falls_back_to_po_row():
    """If the buyer bucket is missing the id, the PO's Buyer field is
    used. A missing buyer record is not a reason to drop the buyer --
    the PO still names them."""
    po_rows = [
        {"POHeaderId": 1, "SupplierId": 100, "BuyerId": 555,
         "Buyer": "FromPORow"}
    ]
    [record] = build_suppliers_with_open_pos_and_buyers(
        _filtered_suppliers()[:1], po_rows, []
    )
    assert record.buyers[0].display_name == "FromPORow"


def test_builder_display_name_falls_back_to_empty_string():
    """No buyer row, no Buyer field — the record still emits, with an
    empty display name. Dropping the buyer would hide a PO's assignment."""
    po_rows = [{"POHeaderId": 1, "SupplierId": 100, "BuyerId": 555}]
    [record] = build_suppliers_with_open_pos_and_buyers(
        _filtered_suppliers()[:1], po_rows, []
    )
    assert record.buyers[0].person_id == 555
    assert record.buyers[0].display_name == ""


def test_builder_empty_po_bucket_gives_zero_counts():
    records = build_suppliers_with_open_pos_and_buyers(
        _filtered_suppliers(), [], _buyers()
    )
    assert all(r.open_po_count == 0 for r in records)
    assert all(r.buyers == [] for r in records)


def test_builder_skips_pos_with_null_supplier_id():
    po_rows = _open_pos() + [
        {"POHeaderId": 99, "SupplierId": None, "BuyerId": 555}
    ]
    records = build_suppliers_with_open_pos_and_buyers(
        _filtered_suppliers(), po_rows, _buyers()
    )
    # The null-SupplierId PO did not inflate anyone's count.
    assert records[0].open_po_count == 3
    assert records[1].open_po_count == 1


def test_builder_skips_pos_with_null_buyer_id():
    po_rows = [
        {"POHeaderId": 1, "SupplierId": 100, "BuyerId": None},
        {"POHeaderId": 2, "SupplierId": 100, "BuyerId": 555, "Buyer": "X"},
    ]
    [record] = build_suppliers_with_open_pos_and_buyers(
        _filtered_suppliers()[:1], po_rows, _buyers()
    )
    assert record.open_po_count == 2
    assert [b.person_id for b in record.buyers] == [555]


# ─────────────────────────────────────────────────────────────────────
# Routing — the fix in synthesize_response
# ─────────────────────────────────────────────────────────────────────


def test_four_bucket_shape_builds_locally_without_llm():
    """The F-056 fix. The four-bucket Supplier shape must produce a
    SupplierResponse with no LLM call, so the overrun cannot occur."""
    llm = _forbidden_llm()
    result = synthesize_response(
        _four_bucket_outputs(), target_entity="Supplier", llm=llm
    )
    assert isinstance(result, SupplierResponse)
    assert len(result.suppliers) == 2
    assert result.suppliers[0].supplier_name == "Lee Supplies"
    llm.with_structured_output.assert_not_called()


def test_four_bucket_summary_states_examined_versus_matched():
    """The summary distinguishes the source total (examined) from the
    filtered subset (shown) and names the aggregated open-PO count."""
    result = synthesize_response(
        _four_bucket_outputs(), target_entity="Supplier",
        llm=_forbidden_llm(),
    )
    assert "Examined 3 of" in result.summary
    assert "2 have open purchase orders" in result.summary
    assert "4 open purchase orders" in result.summary


def test_four_bucket_narrowing_tip_present_when_source_total_known():
    """With truncation metadata carrying a source total, the QA-12 tip
    fires (the answer is a sample)."""
    truncation = {
        "us_suppliers": {
            "total_available": 620, "truncated": True, "limit_applied": 25,
        }
    }
    result = synthesize_response(
        _four_bucket_outputs(),
        target_entity="Supplier",
        llm=_forbidden_llm(),
        truncation_by_step=truncation,
    )
    assert "620" in result.summary
    assert "Narrow with a filter" in result.narrowing_tip


def test_two_bucket_shape_still_takes_the_open_pos_branch():
    """Over-reach guard: the F-010/F-053 two-bucket subset is unchanged.
    `_supplier_with_open_pos` handles it; the new four-bucket branch is
    not reached."""
    outputs = {
        "us_suppliers": _source_suppliers(),
        "open_pos": _open_pos(),
    }
    result = synthesize_response(
        outputs, target_entity="Supplier", llm=_forbidden_llm()
    )
    assert isinstance(result, SupplierResponse)
    # The two-bucket summary wording differs from the four-bucket one.
    assert "These 3 suppliers have" in result.summary


def test_plain_supplier_list_unaffected():
    """A single supplier bucket still takes the plain-list path."""
    outputs = {"suppliers": _source_suppliers()}
    result = synthesize_response(
        outputs, target_entity="Supplier", llm=_forbidden_llm()
    )
    assert isinstance(result, SupplierResponse)
    assert len(result.suppliers) == 3
