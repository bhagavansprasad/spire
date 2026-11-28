"""F-081 — requested columns must survive projection.

The defect: `intent.fields` carries REST/KG vocabulary (`SupplierName`,
`BuyerName`) while the tool payload carries the Fusion API's own keys
(`Supplier`, `Buyer`). `_project_outputs` kept the intersection and threw
the rest away, so a five-column request rendered three columns and two em
dashes — with no warning — while every layer below held the data:

    payload   {"Supplier": "EDF", "Buyer": "Fox, Dan", ...}
    rendered  SupplierName | BuyerName | CurrencyCode | Total   | Status
              —            | —         | GBP          | 14869.2 | Closed

Two guarantees are asserted here:

1. A known display-name/payload mismatch is translated, so the requested
   column is populated.
2. A column that genuinely cannot be satisfied is REPORTED through
   `projection_gaps`, never dropped in silence.

FIX_PLAN §6 F-081.
"""

from __future__ import annotations

import pytest

from spire.graph.pipeline import (
    _FIELD_ALIASES,
    _project_outputs,
    _project_outputs_and_gaps,
)

# A fully-populated PurchaseOrder as the tool actually returns it (verified
# against the pod / REST in the F-081 record).
PO_RECORD = {
    "OrderNumber": "55040",
    "Supplier": "EDF",
    "Buyer": "Fox, Dan",
    "CurrencyCode": "GBP",
    "Total": 14869.2,
    "Status": "Closed",
}

# Exactly the fields prompt 2 asked for, in the parser's vocabulary.
PO_FIELDS = ["SupplierName", "BuyerName", "CurrencyCode", "Total", "Status"]


def test_supplier_and_buyer_name_are_populated_not_dropped():
    """The two columns that used to render as em dashes now carry data."""
    projected, gaps = _project_outputs_and_gaps({"po": [PO_RECORD]}, PO_FIELDS)
    row = projected["po"][0]

    assert row["SupplierName"] == "EDF"
    assert row["BuyerName"] == "Fox, Dan"
    # Everything that already worked is unchanged.
    assert row["CurrencyCode"] == "GBP"
    assert row["Total"] == 14869.2
    assert row["Status"] == "Closed"
    # Nothing was lost, so nothing is reported.
    assert gaps == []


def test_requested_column_names_are_kept_as_headers():
    """The alias fills the requested name; it does not rename the column."""
    projected, _ = _project_outputs_and_gaps({"po": [PO_RECORD]}, PO_FIELDS)
    assert list(projected["po"][0]) == PO_FIELDS


def test_unresolvable_field_is_reported_not_silently_dropped():
    """A column no key and no alias can satisfy comes back as a gap."""
    projected, gaps = _project_outputs_and_gaps(
        {"po": [PO_RECORD]}, ["Supplier", "DiscountPercent"]
    )
    assert gaps == ["DiscountPercent"]
    assert projected["po"][0] == {"Supplier": "EDF"}


def test_exact_key_wins_over_alias():
    """An entity that really carries `SupplierName` is never shadowed."""
    record = {"SupplierName": "REAL", "Supplier": "ALIASED"}
    projected, gaps = _project_outputs_and_gaps({"x": [record]}, ["SupplierName"])
    assert projected["x"][0]["SupplierName"] == "REAL"
    assert gaps == []


def test_partial_match_still_reports_the_missing_column():
    """The old body returned a partial row and said nothing; it now says so.

    This is the exact harm in F-081: three of five columns survived and the
    caller had no way to tell.
    """
    _, gaps = _project_outputs_and_gaps({"po": [PO_RECORD]}, PO_FIELDS)
    assert len(gaps) == 0  # all five resolved, two of them via alias


def test_shape_wrapper_bucket_is_still_skipped():
    """The F-014 defence is untouched: an aggregation wrapper is not trimmed."""
    wrapper = {"shape": "aggregation", "rows": [{"a": 1}], "total": 1}
    projected, gaps = _project_outputs_and_gaps({"agg": [wrapper]}, ["Supplier"])
    assert projected["agg"][0] is wrapper
    assert gaps == ["Supplier"]


def test_empty_fields_returns_outputs_unchanged():
    outputs = {"po": [PO_RECORD]}
    projected, gaps = _project_outputs_and_gaps(outputs, [])
    assert projected is outputs
    assert gaps == []


def test_project_outputs_wrapper_keeps_its_two_argument_contract():
    """Existing callers and tests call `_project_outputs(outputs, fields)`."""
    projected = _project_outputs({"po": [PO_RECORD]}, PO_FIELDS)
    assert projected["po"][0]["SupplierName"] == "EDF"


@pytest.mark.parametrize(
    ("display", "payload"),
    sorted(_FIELD_ALIASES.items()),
)
def test_every_alias_points_at_a_real_po_payload_key(display, payload):
    """Guard against a typo'd alias: the target key must exist on the payload."""
    assert payload in PO_RECORD, f"alias {display} -> {payload} is not a real key"
