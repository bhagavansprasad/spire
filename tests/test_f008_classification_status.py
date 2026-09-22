"""F-008 - expired supplier classifications must not match.

The bug: `suppliers with classification Minority Owned` returned supplier
1272 (Consolidated Supplies) whose Minority Owned classification is
Status="EXPIRED". The filter is naturally read as "currently certified
Minority Owned"; returning a lapsed cert asserts a currency the data
does not support.

The fix applies a client-side Status pass on the FILTER path only. The
INCLUDE path (no classification value) is deliberately unchanged: the
user asked to see the supplier's classifications, and each row's own
Status is information they asked for.

Statuses observed on this pod: "CURRENT" and "EXPIRED". A row whose
Status is missing is treated as not-current, not as current.
"""

import pytest

from spire.mcp_server.tools.supplier_classifications import (
    _filter_to_current,
    search_suppliers_by_classification,
)


class _FakeClient:
    """Minimal async stand-in for FusionClient.get."""

    def __init__(self, response):
        self._response = response

    async def get(self, path, params=None):
        return self._response


def _row(cid, name, status, code="", agency=""):
    return {
        "ClassificationId": cid,
        "Classification": name,
        "ClassificationCode": code,
        "Status": status,
        "CertifyingAgency": agency,
    }


# ---------------------------------------------------------------------
# The pure helper
# ---------------------------------------------------------------------


def test_filter_drops_expired():
    rows = [_row(1, "Minority Owned", "EXPIRED")]
    assert _filter_to_current(rows) == []


def test_filter_keeps_current():
    rows = [_row(1, "Minority Owned", "CURRENT")]
    assert _filter_to_current(rows) == rows


def test_filter_drops_missing_status():
    """A row with no Status is not CURRENT. The pod always returns
    Status on this child; a missing one is malformed and treating it
    as current re-opens the F-008 defect."""
    assert _filter_to_current([{"ClassificationId": 1}]) == []


def test_filter_drops_unknown_status():
    """Any value that is not CURRENT is excluded - including a
    hypothetical third state. The predicate is exact, not a
    current-versus-expired dichotomy."""
    assert _filter_to_current([_row(1, "X", "PENDING")]) == []


def test_filter_preserves_order():
    rows = [
        _row(1, "A", "CURRENT"),
        _row(2, "B", "CURRENT"),
        _row(3, "C", "CURRENT"),
    ]
    assert [r["Classification"] for r in _filter_to_current(rows)] == [
        "A", "B", "C",
    ]


def test_filter_empty():
    assert _filter_to_current([]) == []


def test_filter_mixed():
    rows = [
        _row(1, "Small Business", "CURRENT"),
        _row(2, "Hub Zone", "EXPIRED"),
        _row(3, "Veteran Owned", "EXPIRED"),
        _row(4, "Woman Owned", "CURRENT"),
    ]
    kept = _filter_to_current(rows)
    assert [r["Classification"] for r in kept] == [
        "Small Business", "Woman Owned",
    ]


# ---------------------------------------------------------------------
# The tool: FILTER path applies the currency filter
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_path_excludes_expired():
    """F-008 reproducer, reduced. A pod response whose only matching
    row is EXPIRED must produce an empty result on the filter path."""
    fake = _FakeClient(
        {"items": [_row(300000079220552, "Minority Owned", "EXPIRED",
                        code="MINORITY_OWNED", agency="Other")]}
    )
    result = await search_suppliers_by_classification(
        fake, supplier_id=300000047837244, classification="Minority Owned"
    )
    assert result.items == []


@pytest.mark.asyncio
async def test_filter_path_keeps_current():
    fake = _FakeClient(
        {"items": [_row(1, "Minority Owned", "CURRENT")]}
    )
    result = await search_suppliers_by_classification(
        fake, supplier_id=1, classification="Minority Owned"
    )
    assert len(result.items) == 1
    assert result.items[0]["Status"] == "CURRENT"


@pytest.mark.asyncio
async def test_filter_path_mixed_only_current_survives():
    fake = _FakeClient(
        {"items": [
            _row(1, "Minority Owned", "EXPIRED"),
            _row(2, "Minority Owned", "CURRENT"),
        ]}
    )
    result = await search_suppliers_by_classification(
        fake, supplier_id=1, classification="Minority Owned"
    )
    assert len(result.items) == 1
    assert result.items[0]["ClassificationId"] == 2


@pytest.mark.asyncio
async def test_filter_result_carries_status():
    """The surviving row still carries its Status field, so a caller
    can render "Minority Owned (CURRENT)" without a second fetch."""
    fake = _FakeClient(
        {"items": [_row(1, "Minority Owned", "CURRENT")]}
    )
    result = await search_suppliers_by_classification(
        fake, supplier_id=1, classification="Minority Owned"
    )
    assert result.items[0]["Status"] == "CURRENT"


# ---------------------------------------------------------------------
# The tool: INCLUDE path is unchanged (returns every status)
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_include_path_returns_all_statuses():
    """F-043 include path. No classification value given; the user
    asked to see classifications. Expired rows stay in the answer -
    each row's Status is information they asked for."""
    fake = _FakeClient(
        {"items": [
            _row(1, "Minority Owned", "EXPIRED"),
            _row(2, "Small Business", "CURRENT"),
        ]}
    )
    result = await search_suppliers_by_classification(
        fake, supplier_id=1
    )
    assert len(result.items) == 2
    assert {i["Status"] for i in result.items} == {"EXPIRED", "CURRENT"}


@pytest.mark.asyncio
async def test_include_path_carries_all_projected_fields():
    """Include-path result keeps the projection shape (Classification,
    ClassificationCode, Status, CertifyingAgency) plus the stamped
    SupplierId - unchanged by F-008."""
    fake = _FakeClient(
        {"items": [_row(1, "Small Business", "CURRENT",
                        code="SMALL_BUSINESS", agency="SBA")]}
    )
    result = await search_suppliers_by_classification(
        fake, supplier_id=300000047572113
    )
    assert len(result.items) == 1
    row = result.items[0]
    assert row["Classification"] == "Small Business"
    assert row["ClassificationCode"] == "SMALL_BUSINESS"
    assert row["Status"] == "CURRENT"
    assert row["CertifyingAgency"] == "SBA"
    assert row["SupplierId"] == 300000047572113
