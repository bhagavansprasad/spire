from scripts.validate_sql_coverage import validate


def test_sql_coverage_reports_unclassified_args_and_known_gaps():
    errors = validate()

    assert not any(error.startswith("Uncovered tool argument") for error in errors)
    assert any("F-080b" in error for error in errors)
    assert any("PurchaseOrder.BuyerName" in error for error in errors)
    assert any("PurchaseOrder.SupplierName" in error for error in errors)
