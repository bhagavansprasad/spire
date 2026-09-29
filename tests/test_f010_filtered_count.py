"""F-010 — filtered count uses the matched bucket, not the source total.

The bug: "count of suppliers with classification Minority Owned" ran two
steps (fetch source suppliers, then keep the ones with that
classification) and answered "There are 593 suppliers." — the pod-wide
UNFILTERED total — over a filter that had kept exactly 1.

The fix reads the matched bucket's size as the count and reports the
source as a sample caveat, mirroring the wording the entity-list path
already uses ("Examined 25 of 593 suppliers. Of those 25, 1 match.").
"""

from spire.synthesizer.aggregation import (
    _build_count_response,
    _filtered_bucket_pair,
)


def _row(sid: int, name: str = "S") -> dict:
    return {"SupplierId": sid, "Supplier": f"{name}{sid}",
            "SupplierNumber": str(sid)}


# ─────────────────────────────────────────────────────────────────────
# Helper: shape detection
# ─────────────────────────────────────────────────────────────────────


def test_filtered_pair_detected_by_name_prefix():
    outputs = {
        "suppliers": [_row(i) for i in range(25)],
        "suppliers_has_classification": [_row(1)],
    }
    assert _filtered_bucket_pair(outputs) == (
        "suppliers",
        "suppliers_has_classification",
    )


def test_filtered_pair_order_independent():
    outputs = {
        "suppliers_has_classification": [_row(1)],
        "suppliers": [_row(i) for i in range(25)],
    }
    assert _filtered_bucket_pair(outputs) == (
        "suppliers",
        "suppliers_has_classification",
    )


def test_single_bucket_is_not_a_filtered_pair():
    outputs = {"suppliers": [_row(i) for i in range(25)]}
    assert _filtered_bucket_pair(outputs) is None


def test_three_buckets_are_not_a_filtered_pair():
    outputs = {
        "suppliers": [_row(i) for i in range(25)],
        "suppliers_has_classification": [_row(1)],
        "buyers": [{"PersonId": 7}],
    }
    assert _filtered_bucket_pair(outputs) is None


def test_unsuffixed_two_buckets_are_not_a_filtered_pair():
    outputs = {
        "suppliers": [_row(i) for i in range(25)],
        "buyers": [{"PersonId": 7}],
    }
    assert _filtered_bucket_pair(outputs) is None


def test_shared_id_key_required():
    """Name prefix alone must not suffice; both buckets must carry the
    source entity's id key."""
    outputs = {
        "suppliers": [_row(i) for i in range(25)],
        "suppliers_extra": [{"OtherKey": 1}],
    }
    assert _filtered_bucket_pair(outputs) is None


# ─────────────────────────────────────────────────────────────────────
# _build_count_response: the actual defect
# ─────────────────────────────────────────────────────────────────────


def test_filtered_count_uses_matched_bucket():
    """The F-010 reproducer. Pre-fix this returned 593."""
    outputs = {
        "suppliers": [_row(i) for i in range(25)],
        "suppliers_has_classification": [_row(1)],
    }
    truncation = {
        "suppliers": {"total_available": 593, "truncated": True},
    }
    resp = _build_count_response(outputs, "Supplier", truncation)

    assert resp.count == 1, (
        f"F-010: expected count=1 (the matched bucket), got {resp.count}"
    )
    assert resp.count_is_exact is False
    assert "1 supplier" in resp.summary
    assert "25 of 593" in resp.summary


def test_filtered_count_zero_matches():
    """An empty matched bucket is a valid answer — 0, not the source total."""
    outputs = {
        "suppliers": [_row(i) for i in range(25)],
        "suppliers_has_classification": [],
    }
    truncation = {
        "suppliers": {"total_available": 593, "truncated": True},
    }
    resp = _build_count_response(outputs, "Supplier", truncation)

    assert resp.count == 0
    assert resp.count_is_exact is False
    assert "0 suppliers" in resp.summary


def test_filtered_count_plural_for_multiple():
    outputs = {
        "suppliers": [_row(i) for i in range(25)],
        "suppliers_has_classification": [_row(1), _row(2), _row(3)],
    }
    truncation = {
        "suppliers": {"total_available": 593, "truncated": True},
    }
    resp = _build_count_response(outputs, "Supplier", truncation)

    assert resp.count == 3
    assert "3 suppliers" in resp.summary


def test_filtered_count_no_source_total():
    """Source fetch capped with unknown total (composite filter). The
    matched count stands but is not exact."""
    outputs = {
        "suppliers": [_row(i) for i in range(25)],
        "suppliers_has_classification": [_row(1)],
    }
    truncation = {
        "suppliers": {"total_available": None, "truncated": True},
    }
    resp = _build_count_response(outputs, "Supplier", truncation)

    assert resp.count == 1
    assert resp.count_is_exact is False
    assert "capped" in resp.summary


def test_filtered_count_source_complete():
    """Source fetch complete (no truncation): the matched set IS the
    exact answer."""
    outputs = {
        "suppliers": [_row(1), _row(2), _row(3)],
        "suppliers_has_classification": [_row(1)],
    }
    resp = _build_count_response(outputs, "Supplier", None)

    assert resp.count == 1
    assert resp.count_is_exact is True
    assert resp.summary == "1 supplier match the filter."


# ─────────────────────────────────────────────────────────────────────
# Regression guard: the unfiltered path is unchanged
# ─────────────────────────────────────────────────────────────────────


def test_plain_count_unchanged():
    """`count of suppliers` — one bucket, one total, exact."""
    outputs = {"suppliers": [_row(i) for i in range(25)]}
    truncation = {
        "suppliers": {"total_available": 593, "truncated": True},
    }
    resp = _build_count_response(outputs, "Supplier", truncation)

    assert resp.count == 593
    assert resp.count_is_exact is True
    assert resp.summary == "There are 593 suppliers."


def test_plain_count_without_truncation_is_exact():
    """Small set, no cap: len(bucket) is the exact count."""
    outputs = {"suppliers": [_row(i) for i in range(3)]}
    resp = _build_count_response(outputs, "Supplier", None)

    assert resp.count == 3
    assert resp.count_is_exact is True
