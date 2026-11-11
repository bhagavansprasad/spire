"""Supplier sample-and-disclose — the Supplier surface, tested locally.

WHY THIS FILE EXISTS

Supplier sample-and-disclose is already implemented on `master`: the
synthesizer's plain-list branch (`plain_supplier_bucket` plus
`local_list_summary` plus `build_narrowing_tip`) returns a
`SupplierResponse` with a bounded sample and a populated narrowing
tip, with no parser, planner, or synthesizer change. PR #2 does not
introduce that path. See `docs/phase-3/sample_and_disclose/supplier.md`
V0 (commit `7b7bb51`) for the corrected scope.

What PR #2 contributes here:

  * Four PROVING tests, green on `master`, that lock the four
    existing local Supplier paths (plain list, two-bucket open-PO
    join, F-053 four-bucket join, empty). Each fails if the path
    it covers stops returning a locally-built `SupplierResponse`.

  * One FAILING test on `master`, red for the right reason (an
    `AssertionError` from `_forbidden_llm`, not a missing API key
    or a schema failure): a Supplier prompt naming TWO OR MORE
    distinct child buckets at once. No local Supplier builder
    claims that shape today. Every `_supplier_with_*` helper in
    `p2p.py` handles exactly one child bucket plus the supplier
    bucket; a three-bucket shape produces `len(outputs) != 1`, so
    `plain_supplier_bucket` returns None, no other local builder
    claims the shape, and the response falls to the LLM path.

The one failing test is the branch's V7 evidence base: it is
committed BEFORE any source edit, so its red is the absence of the
fix, not a post-hoc stash. The source edit that turns it green is
PR #2's B8. See `docs/phase-3/sample_and_disclose/supplier.md` for
the V-walk cells that follow.

FIXTURES AND THE FORBIDDEN LLM

Every fixture is a hand-built dict matching the executor's output
shape, not a fetch. The `_forbidden_llm` fixture is a MagicMock
whose `with_structured_output` raises `AssertionError` on contact —
that is how "no LLM call" becomes a tested property rather than an
unobserved implementation detail. Three separate LLM-call removals
in earlier windows left the suite's pass count unchanged because
nothing asserted the absence of a call. See the module docstrings of
`test_synthesizer_aggregation.py` and `test_f056_supplier_pos_buyers.py`
for the same pattern.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from spire.synthesizer.synthesizer import (
    SupplierResponse,
    synthesize_response,
)


def _forbidden_llm() -> MagicMock:
    """An LLM that fails the test if anything touches it.

    Not a recording mock: three windows' worth of LLM-call removals
    passed the suite because a mock that only records calls was
    never checked. Raising on contact is what turns "no LLM call"
    into a red-on-regression property.
    """
    llm = MagicMock()
    llm.with_structured_output.side_effect = AssertionError(
        "synthesize_response called the LLM on a Supplier path that "
        "should be local"
    )
    return llm


# ─────────────────────────────────────────────────────────────────────
# Fixtures — one bucket per shape the local Supplier builders accept,
# built to match the executor's output shape exactly.
# ─────────────────────────────────────────────────────────────────────


def _supplier_row(sid: int, name: str) -> dict:
    return {
        "SupplierId": sid,
        "SupplierNumber": str(1252 + sid),
        "Supplier": name,
        "Status": "ACTIVE",
    }


def _contact_row(cid: int, sid: int, name: str) -> dict:
    return {
        "SupplierContactId": cid,
        "SupplierId": sid,
        "ContactName": name,
        "Email": f"contact-{cid}@example.test",
        "JobTitle": "",
        "AdministrativeContactFlag": False,
    }


def _site_row(site_id: int, sid: int, name: str) -> dict:
    return {
        "SupplierSiteId": site_id,
        "SupplierId": sid,
        "SupplierSite": name,
        "ProcurementBU": "US1 Business Unit",
        "ProcurementBUId": 300000046987012,
    }


def _classification_row(cid: int, sid: int, name: str) -> dict:
    return {
        "ClassificationId": cid,
        "SupplierId": sid,
        "Classification": name,
        "ClassificationCode": name.upper().replace(" ", "_"),
        "Status": "CURRENT",
        "CertifyingAgency": "",
    }


def _po_row(ph_id: int, sid: int, buyer_id: int, buyer: str) -> dict:
    return {
        "POHeaderId": ph_id,
        "OrderNumber": f"PO-{ph_id}",
        "StatusCode": "OPEN",
        "SupplierId": sid,
        "BuyerId": buyer_id,
        "Buyer": buyer,
    }


def _buyer_row(pid: int, name: str) -> dict:
    return {"PersonId": pid, "DisplayName": name}


# ─────────────────────────────────────────────────────────────────────
# PROVING TEST 1 — plain list (single bucket)
# ─────────────────────────────────────────────────────────────────────


def test_plain_supplier_list_builds_locally_without_llm():
    """The base case. One supplier bucket, no child buckets. The
    plain_supplier_bucket branch claims the shape and returns a
    SupplierResponse with the records built from the executor rows.
    Green on master today — proves the path exists."""
    outputs = {
        "suppliers": [
            _supplier_row(100, "Lee Supplies"),
            _supplier_row(200, "JGA"),
        ],
    }
    result = synthesize_response(
        outputs, target_entity="Supplier", llm=_forbidden_llm()
    )
    assert isinstance(result, SupplierResponse)
    assert [s.supplier_id for s in result.suppliers] == [100, 200]
    assert [s.supplier_name for s in result.suppliers] == [
        "Lee Supplies", "JGA"
    ]


# ─────────────────────────────────────────────────────────────────────
# PROVING TEST 2 — two-bucket open-PO join
# ─────────────────────────────────────────────────────────────────────


def test_supplier_open_po_join_builds_locally_without_llm():
    """The two-bucket shape that F-010 / F-053's `_supplier_with_open_pos`
    helper was written for. Green on master. Proves the join path
    still exists and still returns local records."""
    outputs = {
        "suppliers": [
            _supplier_row(100, "Lee Supplies"),
            _supplier_row(200, "JGA"),
        ],
        "open_pos": [
            _po_row(1, 100, 555, "Calvin Roth"),
            _po_row(2, 100, 555, "Calvin Roth"),
            _po_row(3, 200, 777, "May Gee"),
        ],
    }
    result = synthesize_response(
        outputs, target_entity="Supplier", llm=_forbidden_llm()
    )
    assert isinstance(result, SupplierResponse)
    by_id = {s.supplier_id: s for s in result.suppliers}
    assert by_id[100].open_po_count == 2
    assert by_id[200].open_po_count == 1
    assert [b.person_id for b in by_id[100].buyers] == [555]
    assert [b.person_id for b in by_id[200].buyers] == [777]


# ─────────────────────────────────────────────────────────────────────
# PROVING TEST 3 — F-053 four-bucket shape
# ─────────────────────────────────────────────────────────────────────


def test_supplier_f053_four_bucket_shape_builds_locally_without_llm():
    """The four-bucket F-056/F-053 shape: source + filtered +
    refetched POs + buyers. `_supplier_pos_buyers` claims it and
    builds locally. Green on master. Same shape PR #1's anchor
    prompt produces on the Supplier side."""
    outputs = {
        "us_suppliers": [
            _supplier_row(100, "Lee Supplies"),
            _supplier_row(200, "JGA"),
            _supplier_row(300, "US Gas"),
        ],
        "us_suppliers_has_open_PO": [
            _supplier_row(100, "Lee Supplies"),
            _supplier_row(200, "JGA"),
        ],
        "open_pos": [
            _po_row(1, 100, 555, "Calvin Roth"),
            _po_row(2, 200, 777, "May Gee"),
        ],
        "buyers": [
            _buyer_row(555, "Calvin Roth"),
            _buyer_row(777, "May Gee"),
        ],
    }
    result = synthesize_response(
        outputs, target_entity="Supplier", llm=_forbidden_llm()
    )
    assert isinstance(result, SupplierResponse)
    assert [s.supplier_id for s in result.suppliers] == [100, 200]
    assert result.suppliers[0].open_po_count == 1
    assert result.suppliers[1].open_po_count == 1


# ─────────────────────────────────────────────────────────────────────
# PROVING TEST 4 — empty result
# ─────────────────────────────────────────────────────────────────────


def test_empty_supplier_result_builds_locally_without_llm():
    """A query whose source bucket came back empty must still take
    the local path. Green on master. This is the OUT-01 shape:
    zero rows is an answer, not an error, and it must not be routed
    through an LLM to say so."""
    outputs = {"suppliers": []}
    result = synthesize_response(
        outputs, target_entity="Supplier", llm=_forbidden_llm()
    )
    assert isinstance(result, SupplierResponse)
    assert result.suppliers == []
    assert "No suppliers" in result.summary or result.summary == ""


# ─────────────────────────────────────────────────────────────────────
# FAILING TEST — the multi-child shape PR #2 fixes
#
# On master today, this test fails with an AssertionError raised by
# _forbidden_llm's with_structured_output — i.e. the multi-bucket shape
# reaches the LLM path, because no local Supplier builder claims it.
# The source edit at B8 adds a builder that claims the shape, and this
# test goes green.
#
# The failing reason is deliberately the LLM call, NOT an import error
# and NOT a schema validation error: both of those would be red for
# any test, and neither would establish that the multi-child shape is
# the one that has no local builder. The red must be the specific
# "no local builder exists for this shape, so the response falls
# through to the LLM" defect.
# ─────────────────────────────────────────────────────────────────────


def test_multi_child_supplier_shape_builds_locally_without_llm():
    """A Supplier prompt naming two or more distinct child buckets at
    once — e.g. contacts AND sites, or contacts AND classifications —
    is not covered by any local builder on master. The shape reaches
    the LLM path; _forbidden_llm turns that into a specific red.

    The fix (PR #2's B8) adds a local multi-child builder that
    claims this shape. After the fix, this test asserts the response
    carries all three child collections, populated from the executor
    rows, with no LLM call.
    """
    outputs = {
        "suppliers": [_supplier_row(100, "Lee Supplies")],
        "contact": [_contact_row(10, 100, "Kim, John")],
        "site": [_site_row(20, 100, "Lee US1")],
    }
    result = synthesize_response(
        outputs, target_entity="Supplier", llm=_forbidden_llm()
    )
    assert isinstance(result, SupplierResponse)
    assert len(result.suppliers) == 1
    supplier = result.suppliers[0]
    assert len(supplier.contacts) == 1
    assert supplier.contacts[0].contact_name == "Kim, John"
    assert len(supplier.sites) == 1
    assert supplier.sites[0].supplier_site == "Lee US1"


# ─────────────────────────────────────────────────────────────────────
# V-walk Fix D — the narrowing tip must be present on both Supplier
# local paths.
#
# V1 on fa-esll-saasfademo1 (the live run that opened PR #2's V-walk)
# surfaced two omissions the earlier unit tests did not catch:
#
#   - plain_supplier_bucket's return statement (synthesizer.py:760)
#     omits narrowing_tip= entirely, so a plain `get all suppliers`
#     answer prints "Showing 25 of 402 suppliers." and no "Tip" block.
#
#   - The multi-child branch added in B10c (synthesizer.py:1201) also
#     omits narrowing_tip=, so `suppliers with their contacts and
#     sites` prints the child tables but no tip.
#
# Both omissions predate or ship with this PR; both are fixed by a
# one-line narrowing_tip=<expr> addition on each return. These tests
# assert the tip is non-empty on both paths, which is exactly the
# property V1's live prompt expects and the earlier tests did not
# check.
# ─────────────────────────────────────────────────────────────────────


def test_plain_supplier_list_carries_narrowing_tip():
    """A plain Supplier list must populate narrowing_tip from the
    total_available the executor reports.

    On the current tree this test FAILS: the plain_supplier_bucket
    branch does not pass narrowing_tip, so the response's tip is "".
    After Fix D-a, the response carries the same tip the filtered
    Supplier branches already produce.
    """
    outputs = {
        "suppliers": [
            _supplier_row(100, "Lee Supplies"),
            _supplier_row(200, "JGA"),
        ],
    }
    truncation = {
        "suppliers": {
            "total_available": 402,
            "truncated": True,
            "limit_applied": 25,
        }
    }
    result = synthesize_response(
        outputs,
        target_entity="Supplier",
        llm=_forbidden_llm(),
        truncation_by_step=truncation,
    )
    assert isinstance(result, SupplierResponse)
    assert result.narrowing_tip, (
        "plain Supplier list must populate narrowing_tip when "
        "total_available is known; got empty string"
    )
    assert "402" in result.narrowing_tip, (
        f"narrowing_tip should name the source total (402); got "
        f"{result.narrowing_tip!r}"
    )


def test_multi_child_supplier_shape_carries_narrowing_tip():
    """The multi-child Supplier shape must populate narrowing_tip too.

    On the current tree this test FAILS: the multi-child branch added
    in B10c does not pass narrowing_tip. After Fix D-b, it does, and
    a live `suppliers with their contacts and sites` prompt renders
    the same "Tip" block the filtered Supplier branches produce.
    """
    outputs = {
        "suppliers": [_supplier_row(100, "Lee Supplies")],
        "contact": [_contact_row(10, 100, "Kim, John")],
        "site": [_site_row(20, 100, "Lee US1")],
    }
    truncation = {
        "suppliers": {
            "total_available": 402,
            "truncated": True,
            "limit_applied": 25,
        }
    }
    result = synthesize_response(
        outputs,
        target_entity="Supplier",
        llm=_forbidden_llm(),
        truncation_by_step=truncation,
    )
    assert isinstance(result, SupplierResponse)
    assert result.narrowing_tip, (
        "multi-child Supplier shape must populate narrowing_tip when "
        "total_available is known; got empty string"
    )
    assert "402" in result.narrowing_tip, (
        f"narrowing_tip should name the source total (402); got "
        f"{result.narrowing_tip!r}"
    )
