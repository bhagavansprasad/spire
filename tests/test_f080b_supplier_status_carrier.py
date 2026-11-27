"""F-080b — supplier status must not use the `ENABLED_FLAG` stub.

The defect: `search_suppliers.status` rendered
`{alias}.ENABLED_FLAG = {value}` with `{'ACTIVE': "'Y'", 'INACTIVE': "'N'"}`.
`POZ_SUPPLIERS.ENABLED_FLAG` is `'Y'` on **all 334** suppliers on this pod,
so "inactive suppliers" returned 0 rows while REST reports 2. The failure
mode is a clean-looking "none found" — indistinguishable from a true
negative.

The carrier, measured on dev49 in one session:

    POZ_SUPPLIERS: 334 rows, ENABLED_FLAG 'Y' on 334/334
                   END_DATE_ACTIVE populated on 2 rows (both 2022-11-19)
    REST:          334 suppliers, Status ACTIVE 332 / INACTIVE 2
                   InactiveDate populated on 2, both 2022-11-19
    identity check per SupplierNumber: InactiveDate == END_DATE_ACTIVE
                   334 matched, 0 mismatches

There is no `INACTIVE_DATE` column on `POZ_SUPPLIERS`, so REST's
`InactiveDate` *is* `END_DATE_ACTIVE`.

FIX_PLAN §6 F-080b.
"""

from __future__ import annotations

import pytest

from spire.kg.sql_overlay import OVERLAY
from spire.planner.models import Step
from spire.rendering.sql_emitter import emit_sql

STATUS_SPEC = ("search_suppliers", "status")


def _step(status: str) -> Step:
    return Step(
        step_id=1,
        tool_name="search_suppliers",
        tool_args={"status": status},
        iterate_over=None,
        client_filters=(),
        output_name="out1",
        output_dedupe_by=None,
    )


def _emitted(status: str) -> str:
    return emit_sql([_step(status)])[0]


# ── The spec ──────────────────────────────────────────────────────────


def test_status_predicate_does_not_use_the_enabled_flag_stub():
    predicate = OVERLAY.filters[STATUS_SPEC].predicate_template
    assert "ENABLED_FLAG" not in predicate


def test_status_predicate_uses_end_date_active():
    predicate = OVERLAY.filters[STATUS_SPEC].predicate_template
    assert "END_DATE_ACTIVE" in predicate


def test_status_assumption_is_registered_with_the_evidence():
    name = OVERLAY.filters[STATUS_SPEC].assumption
    assert name == "status_maps_to_end_date_active"
    assert name in OVERLAY.assumptions
    text = OVERLAY.assumptions[name]
    # The text has to name the reason, or the next reader re-derives it.
    assert "ENABLED_FLAG" in text
    assert "END_DATE_ACTIVE" in text


# ── The emitted SQL ───────────────────────────────────────────────────


def _where_clause(sql: str) -> str:
    """The predicate part of an emitted statement."""
    body = "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    )
    idx = body.find("WHERE ")
    return body[idx:] if idx >= 0 else ""


def test_emitted_inactive_sql_filters_on_the_end_date():
    sql = _emitted("INACTIVE")
    where = _where_clause(sql)
    assert "END_DATE_ACTIVE" in where
    assert "ENABLED_FLAG" not in where
    # ENABLED_FLAG is still in the SELECT list, but that is a DIFFERENT
    # defect: the KG binds Supplier.Enabled to the same stub, so the
    # projected column reads 'Y' where REST reads ACTIVE/INACTIVE. It
    # needs a kg_schema seed change + KG rebuild, so it is recorded
    # separately as F-084 rather than smuggled into this fix.
    assert "P.ENABLED_FLAG" in sql, "F-084 record expects this; update it if fixed"


def test_emitted_active_sql_is_the_complement():
    """ACTIVE must be the negation of INACTIVE, not a second guess."""
    inactive = _emitted("INACTIVE")
    active = _emitted("ACTIVE")
    assert "END_DATE_ACTIVE" in active
    assert "IS NULL" in active  # no end date == still active
    assert inactive != active


def test_unknown_status_raises_instead_of_returning_suppliers():
    """F-078's fail-loud rule: an unmapped status must not silently pass.

    `value_map` lists only ACTIVE/INACTIVE, so anything else resolves to no
    literal and the emitter raises rather than emitting a predicate that
    would quietly match every supplier.
    """
    with pytest.raises(ValueError, match="unresolved literal"):
        _emitted("ON_HOLD")


# ── The validator rule that prevents recurrence ───────────────────────


def test_validator_reports_no_stub_column_errors_now():
    from scripts.validate_sql_coverage import validate

    errors = validate()
    stub_errors = [e for e in errors if "stub column" in e]
    assert stub_errors == [], stub_errors


def test_validator_flags_any_spec_that_uses_a_stub_column(monkeypatch):
    """The rule is general, not a hardcoded mention of one tool.

    Re-introduces the old ENABLED_FLAG predicate under a new (tool, arg)
    pair and asserts the validator notices — that is what stops the next
    spec from reusing a stub it was never told about.
    """
    from spire.kg.sql_overlay import FilterSpec
    import scripts.validate_sql_coverage as coverage

    monkeypatch.setitem(
        coverage.OVERLAY.filters,
        ("get_buyer", "regression_probe"),
        FilterSpec(
            tool_name="get_buyer",
            arg_name="regression_probe",
            predicate_template="{alias}.ENABLED_FLAG = {value}",
        ),
    )

    errors = coverage.validate()
    assert any(
        "get_buyer.regression_probe" in e and "ENABLED_FLAG" in e
        for e in errors
    ), errors


def test_stub_column_list_cites_its_measurement():
    """Every stub entry must carry the number that makes it a stub."""
    from scripts.validate_sql_coverage import STUB_COLUMNS

    assert STUB_COLUMNS, "the stub list is empty"
    for column, evidence in STUB_COLUMNS.items():
        assert any(ch.isdigit() for ch in evidence), (
            f"{column} has no measurement in its evidence: {evidence!r}"
        )
