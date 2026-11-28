"""F-076 — emitted SQL must match the dataset REST can actually see.

The recorded finding said "REST returns only the session's business unit".
That was **wrong**, and the fix shape it implied (bind one BU via ORG_ID)
would have been worse than the bug. This file pins what was actually
measured and the scope mechanism that follows from it.

Measured on dev49 (2026-11-27), every row accounted for:

    REST /standardReceipts total ........ 63,065
    France Business Unit (hidden) .......  9,316
    UK Business Unit (hidden) ...........  7,352
    TYPE='MISC' (1 row, hidden) .........      1
    ------------------------------------------------
    pod AR_CASH_RECEIPTS_ALL total ...... 79,734   <- exact

Per-business-unit agreement, 9 of 9 probed by name via
``q=BusinessUnit='...'``:

    US1 50004 = 50004   Supremo 12261 = 12261   University 628 = 628
    Healthcare 117 = 117 Progress 33 = 33      India 4 = 4
    Germany 2 = 2       France 0 (pod 9316)    UK 0 (pod 7352)

So REST sees 14 of the 16 AR orgs, not one BU. The boundary is the
integration user's *security profile*, which no column encodes — hence the
persona-configured visible set rather than an ORG_ID constant.

Two rules are needed, and they are independent:

  1. ``TYPE = 'CASH'`` — /standardReceipts does not expose miscellaneous
     receipts. Static: it is a property of the endpoint, not of the pod.
  2. the visible-business-unit filter — from the persona, because it is an
     access fact.

The same filter must NOT be applied to other AR entities: ``/receivablesInvoices``
returns UK invoices (its first row is ``BusinessUnit='UK Business Unit'``)
even though it hides UK receipts, and ``BusinessUnit`` is not even queryable
there (HTTP 400). Applying the receipts rule globally would delete 47,838
real AR invoices.

Finally: **AP is unaffected.** ``/invoices`` = 53,163 = pod 53,163 exactly,
which is what makes this an AR-only finding.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from spire.kg.sql_overlay import OVERLAY
from spire.planner.models import Step
from spire.rendering import sql_emitter

REPO = Path(__file__).resolve().parents[1]
EXAMPLE_PERSONA = REPO / "personas.example.yaml"

# The verified decomposition. Kept as constants so the record and the test
# cannot drift apart silently.
REST_TOTAL = 63065
POD_TOTAL = 79734
FRANCE = 9316
UK = 7352
MISC = 1


def _step(tool: str, args: dict | None = None) -> Step:
    return Step(
        step_id=1,
        tool_name=tool,
        tool_args=args or {},
        iterate_over=None,
        client_filters=(),
        output_name="out1",
        output_dedupe_by=None,
    )


def _receipt_sql(overlay=None) -> str:
    return sql_emitter.emit_sql(
        [_step("search_standard_receipts")], overlay=overlay
    )[0]


# ── The arithmetic the whole finding rests on ─────────────────────────


def test_the_decomposition_is_exact():
    """Every pod receipt is either REST-visible, France, UK, or the MISC row.

    If this ever stops balancing, one of the three rules changed and the
    scope in the overlay is no longer justified.
    """
    assert REST_TOTAL + FRANCE + UK + MISC == POD_TOTAL


# ── Rule 1: the endpoint's own semantics ──────────────────────────────


def test_cash_type_rule_is_declared_on_the_entity():
    spec = OVERLAY.entities["StandardReceipt"]
    assert "{alias}.TYPE = 'CASH'" in spec.scope_predicates


def test_cash_type_rule_carries_an_assumption():
    spec = OVERLAY.entities["StandardReceipt"]
    assert spec.scope_assumption in OVERLAY.assumptions


def test_cash_type_rule_is_in_the_emitted_sql():
    assert "R.TYPE = 'CASH'" in _receipt_sql()


# ── Rule 2: the persona-driven business-unit filter ───────────────────


class _StubPersona:
    def __init__(self, names):
        self.scope = (
            dataclasses.make_dataclass("S", ["visible_business_units"])(names)
            if names is not None
            else None
        )


def _overlay_with(monkeypatch, names):
    """Emit with a stub persona, bypassing the KG cache."""
    monkeypatch.setattr(sql_emitter, "_visible_business_units", lambda: names or [])
    entities = {
        k: dataclasses.replace(v, scope_predicates=list(v.scope_predicates))
        for k, v in OVERLAY.entities.items()
    }
    sql_emitter._apply_data_scope(entities)
    return sql_emitter.Overlay(
        tool_to_entity=OVERLAY.tool_to_entity,
        entities=entities,
        filters=OVERLAY.filters,
        joins=OVERLAY.joins,
        literals=OVERLAY.literals,
        assumptions=OVERLAY.assumptions,
        aggregations=OVERLAY.aggregations,
        not_expressible=OVERLAY.not_expressible,
        sql_control_args=OVERLAY.sql_control_args,
        sql_disabled_args=OVERLAY.sql_disabled_args,
    )


def test_visible_bus_are_injected_when_configured(monkeypatch):
    overlay = _overlay_with(monkeypatch, ["US1 Business Unit", "UK Business Unit"])
    sql = _receipt_sql(overlay)
    assert "R.ORG_ID IN (SELECT U.ORGANIZATION_ID" in sql
    assert "HR_OPERATING_UNITS" in sql
    assert "'US1 Business Unit'" in sql
    assert "'UK Business Unit'" in sql


def test_no_filter_when_unconfigured(monkeypatch):
    """An unconfigured persona keeps the previous superset behaviour."""
    sql = _receipt_sql(_overlay_with(monkeypatch, None))
    assert "ORG_ID IN (SELECT" not in sql
    assert "R.TYPE = 'CASH'" in sql, "the endpoint rule is unconditional"


def test_empty_list_is_treated_as_unconfigured(monkeypatch):
    sql = _receipt_sql(_overlay_with(monkeypatch, []))
    assert "ORG_ID IN (SELECT" not in sql


def test_bu_names_are_quote_escaped(monkeypatch):
    """A name with an apostrophe must not break out of the literal."""
    overlay = _overlay_with(monkeypatch, ["O'Brien BU"])
    sql = _receipt_sql(overlay)
    assert "'O''Brien BU'" in sql
    assert "'O'Brien BU'" not in sql


def test_ids_are_resolved_by_name_not_hardcoded(monkeypatch):
    """ORG_ID values are pod-specific; the predicate must look them up."""
    sql = _receipt_sql(_overlay_with(monkeypatch, ["US1 Business Unit"]))
    assert "300000046987012" not in sql, (
        "a hardcoded ORG_ID would rot on the next pod provisioning run"
    )
    assert "U.NAME IN (" in sql


# ── The scope must not leak to other entities ────────────────────────


@pytest.mark.parametrize(
    "tool",
    [
        "search_receivables_invoices",
        "get_receivables_invoice_by_id",
        "search_invoices",
        "search_suppliers",
        "search_purchase_orders",
    ],
)
def test_other_entities_are_not_bu_scoped(monkeypatch, tool):
    """AR invoices return UK rows even though receipts hide them.

    A global business-unit filter would delete 47,838 real invoices, so
    the scope has to stay on the one entity where it was measured.
    """
    overlay = _overlay_with(monkeypatch, ["US1 Business Unit"])
    sql = sql_emitter.emit_sql([_step(tool)], overlay=overlay)[0]
    assert "ORG_ID IN (SELECT" not in sql
    assert "HR_OPERATING_UNITS" not in sql


def test_only_receipts_are_listed_as_bu_scoped():
    assert sql_emitter._BU_SCOPED_COLUMNS == {"StandardReceipt": "ORG_ID"}


# ── The persona config ───────────────────────────────────────────────


def test_example_persona_documents_the_scope_block():
    text = EXAMPLE_PERSONA.read_text()
    assert "scope:" in text
    assert "visible_business_units:" in text
    # The doc must say what happens when it is omitted, or the default is
    # a surprise.
    assert "superset" in text.lower()


def test_persona_scope_is_optional():
    from spire.config import DataScope, Persona

    assert DataScope().visible_business_units is None
    persona = Persona(
        fusion={
            "base_url": "https://x",
            "username": "u",
            "password": "p",
            "auth_type": "basic",
        }
    )
    assert persona.scope is None


def test_configured_persona_scope_is_loaded():
    """The dev persona declares the 14 measured business units."""
    from spire.config import load_persona

    try:
        persona = load_persona("default_dev")
    except Exception:  # pragma: no cover - no personas.yaml in CI
        pytest.skip("no personas.yaml")
    if persona.scope is None:
        pytest.skip("default_dev declares no scope")
    names = persona.scope.visible_business_units
    assert names, "an empty visible set would silently scope everything out"
    # The two measured-hidden units must not be in the visible set.
    assert "France Business Unit" not in names
    assert "UK Business Unit" not in names
