from scripts.validate_sql_coverage import validate


def test_sql_coverage_reports_unclassified_args_and_known_gaps():
    errors = validate()

    assert not any(error.startswith("Uncovered tool argument") for error in errors)
    assert any("F-080b" in error for error in errors)


def test_supplier_and_buyer_name_are_no_longer_reported_as_alias_gaps():
    """F-081: the projection aliases these, so the validator must not flag them.

    Before the alias map existed, `validate()` reported
    `PurchaseOrder.SupplierName` / `BuyerName` as having "no payload alias"
    for both PO tools. Those columns now resolve through
    `spire.graph.pipeline._FIELD_ALIASES`, and a validator that kept
    reporting them would train the reader to ignore its output.
    """
    errors = validate()

    alias_gaps = [error for error in errors if "no payload alias" in error]
    assert alias_gaps == [], alias_gaps


def test_alias_gap_check_still_fires_for_an_unfillable_name_field(monkeypatch):
    """The check must stay live rather than being neutered by the F-081 fix.

    Drops the alias entry and asserts the validator notices again, so the
    rule still catches a *new* display-name/payload mismatch.
    """
    import scripts.validate_sql_coverage as coverage

    monkeypatch.setattr(
        coverage, "_FIELD_ALIASES", {}, raising=True
    )
    errors = coverage.validate()

    assert any("PurchaseOrder.SupplierName" in error for error in errors)
    assert any("PurchaseOrder.BuyerName" in error for error in errors)

