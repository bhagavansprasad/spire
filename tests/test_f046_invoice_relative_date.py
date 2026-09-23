"""F-046 regression tests — Invoice relative-date filters.

Three sites close the same user outcome:
  1. KG rows (Invoice, older_than_n_months) and
     (Invoice, created_in_last_n_months).
  2. Sysprompt edits — b_invoice_date.sysprompt (new rules),
     b_invoices_for_supplier.sysprompt (drop "MUST include supplier"),
     context_assembly.py's _SYSTEM_PROMPT_PREAMBLE (byte-equality mirror).
  3. Invoice guard in `generate_plan` accepting date filters as root refs.

Tests that touch the KG are gated on personas.yaml (matching
tests/test_kg_metadata.py's discipline: skipif(not PERSONAS_FILE.exists())).
Tests that read sysprompt files run anywhere.

Pre-fix these tests fail:
  - The KG tests fail on the missing (Invoice, older_than_n_months) and
    (Invoice, created_in_last_n_months) rows.
  - The guard tests fail with RefusalError raised pre-fix.
  - The sysprompt tests fail on the missing rules / present supplier clause.

Post-fix (after `python scripts/rebuild_kg.py` and the sysprompt edits)
all pass.
"""

from datetime import date
from pathlib import Path

import pytest

from spire.config import PERSONAS_FILE
from spire.nl_parser.result import RefusalError
from spire.planner.models import Intent
from spire.planner.plan_builders import _build_entity_fetcher_args
from spire.planner.planner import generate_plan


# Sysprompt files — read directly. No DB, no LLM.
_PAYABLES_DIR = (
    Path(__file__).resolve().parents[1]
    / "src" / "spire" / "nl_parser" / "context" / "payables"
)

_needs_personas = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping KG/planner tests",
)


# ── Sysprompt content tests (no DB) ──────────────────────────────────


def test_invoice_date_sysprompt_teaches_older_than_n_months():
    """The Invoice date rule teaches the relative-older filter type.

    F-046 site 2a. Pre-fix this test fails because
    b_invoice_date.sysprompt only covers absolute-date examples; the
    parser then self-declares `unsupported_filter` for `older than 6
    months` (probe 2026-09-23).
    """
    text = (_PAYABLES_DIR / "b_invoice_date.sysprompt").read_text()
    assert "older_than_n_months" in text, (
        "b_invoice_date.sysprompt does not teach 'older_than_n_months'. "
        "See F-046 site 2a."
    )


def test_invoice_date_sysprompt_teaches_created_in_last_n_months():
    """The Invoice date rule teaches the relative-recent filter type.

    F-046 site 2a. Same probe shape as the older-than case.
    """
    text = (_PAYABLES_DIR / "b_invoice_date.sysprompt").read_text()
    assert "created_in_last_n_months" in text, (
        "b_invoice_date.sysprompt does not teach 'created_in_last_n_months'. "
        "See F-046 site 2a."
    )


def test_invoice_for_supplier_sysprompt_drops_absolute_supplier_clause():
    """The supplier-required clause is replaced with a scope-inclusive one.

    F-046 site 2b. Pre-fix the file says "Invoice queries MUST include
    this supplier filter", which blocks a date-only Invoice query; the
    parser self-declares `missing_identifier` for `invoices in the last
    30 days` (probe 2026-09-23). Post-fix the clause is gone.
    """
    text = (_PAYABLES_DIR / "b_invoices_for_supplier.sysprompt").read_text()
    assert "MUST include this supplier filter" not in text, (
        "b_invoices_for_supplier.sysprompt still says 'MUST include this "
        "supplier filter', which blocks date-only Invoice queries. "
        "See F-046 site 2b."
    )


# ── KG / planner tests (require personas.yaml) ───────────────────────


@_needs_personas
def test_invoice_older_than_n_months_emits_invoice_date_before():
    """`_build_entity_fetcher_args` routes the Invoice relative-older filter.

    F-046 sites 1 & 2a. Pre-fix the KG has no (Invoice,
    older_than_n_months) row, `_filter_def_for` raises KeyError, the
    function catches and continues, and the args dict is empty. Post-fix
    the KG row names `invoice_date_before` and the existing plan_builders
    branch (matching on ftype name, entity-agnostic) computes the cutoff.
    """
    ref = date(2026, 9, 23)
    args = _build_entity_fetcher_args(
        [{"type": "older_than_n_months", "value": {"months": 6}}],
        "Invoice",
        ref,
    )
    assert args.get("invoice_date_before") == "2026-03-23", (
        f"Expected invoice_date_before='2026-03-23'; got {args!r}. "
        "Check the KG row (scripts/sql/kg_schema.sql) and the "
        "plan_builders tuple. See F-046 sites 1 & 2a."
    )


@_needs_personas
def test_invoice_created_in_last_n_months_emits_invoice_date_after():
    """The recent-window direction routes to `invoice_date_after`.

    F-046 sites 1 & 2a. Same shape as the older-than test, opposite
    direction.
    """
    ref = date(2026, 9, 23)
    args = _build_entity_fetcher_args(
        [{"type": "created_in_last_n_months", "value": {"months": 6}}],
        "Invoice",
        ref,
    )
    assert args.get("invoice_date_after") == "2026-03-23", (
        f"Expected invoice_date_after='2026-03-23'; got {args!r}. "
        "Check the KG row (scripts/sql/kg_schema.sql) and the "
        "plan_builders tuple. See F-046 sites 1 & 2a."
    )


@_needs_personas
def test_invoice_guard_accepts_absolute_date_filter():
    """A date-only Invoice intent is not refused at the guard.

    F-046 site 3. Pre-fix the guard only accepts supplier/purchase_order/
    invoice_number, so `invoices in 2024` refuses with missing_identifier.
    Post-fix the guard accepts invoice_date as a root ref.
    """
    intent = Intent(
        target_entity="Invoice",
        filters=[{"type": "invoice_date", "value": {"from": "2024-01-01"}}],
    )
    try:
        generate_plan(intent)
    except RefusalError as exc:
        pytest.fail(
            f"Invoice guard refused a valid date-only intent: "
            f"{exc.refusal.detail}. See F-046 site 3 (guard widening)."
        )


@_needs_personas
def test_invoice_guard_accepts_relative_older_than_filter():
    """A relative-date-only Invoice intent is not refused at the guard.

    F-046 site 3. Same shape as the absolute case, for the new filter
    type this branch adds.
    """
    intent = Intent(
        target_entity="Invoice",
        filters=[{"type": "older_than_n_months", "value": {"months": 6}}],
    )
    try:
        generate_plan(intent)
    except RefusalError as exc:
        pytest.fail(
            f"Invoice guard refused a valid relative-date intent: "
            f"{exc.refusal.detail}. See F-046 site 3 (guard widening)."
        )


@_needs_personas
def test_invoice_guard_accepts_relative_recent_filter():
    """The recent-window direction is also accepted by the guard."""
    intent = Intent(
        target_entity="Invoice",
        filters=[
            {"type": "created_in_last_n_months", "value": {"months": 6}}
        ],
    )
    try:
        generate_plan(intent)
    except RefusalError as exc:
        pytest.fail(
            f"Invoice guard refused a valid relative-recent intent: "
            f"{exc.refusal.detail}. See F-046 site 3 (guard widening)."
        )


@_needs_personas
def test_invoice_guard_still_refuses_filterless():
    """A filter-less Invoice intent still refuses — no runaway paging.

    Regression guard for site 3: the widening must not go so far that a
    completely unscoped Invoice query answers (which would try to page
    the 49,000+ invoice collection).
    """
    intent = Intent(target_entity="Invoice", filters=[])
    with pytest.raises(RefusalError):
        generate_plan(intent)
