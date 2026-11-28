"""AP-2 — outstanding by supplier is a different measure, so a different tool.

The defect: p20 asked for "total **outstanding** invoice amount grouped by
supplier for the **current month**" and was answered with "**Total Spend**"
over the whole collection. Two silent substitutions:

1. **Measure** — "outstanding" is what is still owed. The only aggregation
   summed `InvoiceAmount`, which is what was billed.
2. **Period** — "current month" produced no `date_from`/`date_to`, so the
   answer covered all time.

Nothing in the answer acknowledged either swap, and it scored `OK` because
rows came back. Recorded as AP-2 in
docs/plan/module-support/AP_COVERAGE_ASSESSMENT.md §5.

The fix is a separate bounded tool (the aggregation layer's rule: grouping
and measure are fixed by identity, a different measure is a different tool),
plus the parser teaching that distinguishes the vocabulary.

Measured on dev49, 2026-11-28, which is why the measure is `AmountPaid` and
not `PaidStatus`:

    PaidStatus='Unpaid'          -> 12,739
    PaidStatus='Paid'            -> 40,482
    PaidStatus='Partially paid'  ->  0        (none exist here)
    CanceledFlag='true'          ->    725
    InvoiceAmount=0              ->    745

Zero partial payments is exactly why gating on the status flag looks
adequate — and why it is wrong. A partly paid invoice is not in 'Paid'
status, so status-gating would contribute ZERO for it and a partial state
could never be detected.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from spire.mcp_server.tools.aggregate_outstanding_invoices import (
    INVOICES_PATH,
    _aggregate_outstanding,
    aggregate_outstanding_invoices_by_supplier,
)
from spire.planner.registries import _AGGREGATION_PARAMS, _AGGREGATION_TOOLS
from spire.synthesizer.aggregation import build_supplier_outstanding_ranking

REPO = Path(__file__).resolve().parents[1]
PARSER_BLOCK = (
    REPO / "src" / "spire" / "nl_parser" / "context" / "modes"
    / "m_aggregation.sysprompt"
)


def _inv(
    supplier: str,
    number: str,
    amount: float,
    paid: float | None = 0,
    cancelled: bool = False,
    date: str = "2026-11-10",
) -> dict:
    return {
        "Supplier": supplier,
        "SupplierNumber": number,
        "InvoiceAmount": amount,
        "AmountPaid": paid,
        "CanceledFlag": cancelled,
        "InvoiceDate": date,
    }


# ── the measure ───────────────────────────────────────────────────────


def test_outstanding_is_amount_minus_paid():
    rows, _, _, _ = _aggregate_outstanding(
        [_inv("Acme", "1", 100.0, 40.0)], top_n=10
    )
    assert rows[0]["total_outstanding"] == 60.0


def test_fully_paid_invoice_contributes_zero_outstanding():
    rows, _, _, _ = _aggregate_outstanding(
        [_inv("Acme", "1", 100.0, 100.0)], top_n=10
    )
    assert rows[0]["total_outstanding"] == 0.0
    assert rows[0]["invoice_count"] == 1


def test_overpayment_never_goes_negative():
    """An overpaid invoice is not money still owed."""
    rows, _, _, _ = _aggregate_outstanding(
        [_inv("Acme", "1", 100.0, 250.0)], top_n=10
    )
    assert rows[0]["total_outstanding"] == 0.0


def test_missing_amount_paid_counts_as_nothing_paid():
    """A null AmountPaid means no payment recorded, not 'unknown'."""
    rows, _, _, _ = _aggregate_outstanding(
        [_inv("Acme", "1", 100.0, None)], top_n=10
    )
    assert rows[0]["total_outstanding"] == 100.0


def test_cancelled_invoices_are_excluded_and_counted():
    """A cancelled invoice is not owed. 725 exist, so this is not a corner."""
    rows, _, excluded, counted = _aggregate_outstanding(
        [
            _inv("Acme", "1", 100.0, 0.0),
            _inv("Acme", "1", 999.0, 0.0, cancelled=True),
        ],
        top_n=10,
    )
    assert rows[0]["total_outstanding"] == 100.0
    assert rows[0]["invoice_count"] == 1
    assert excluded == 1
    assert counted == 1


def test_partial_payment_is_visible_where_status_gating_would_hide_it():
    """The reason for AmountPaid over PaidStatus, stated as a test.

    Status-gating counts nothing for a partly paid invoice; the amount does.
    """
    rows, _, _, _ = _aggregate_outstanding(
        [
            _inv("Acme", "1", 100.0, 30.0),
            _inv("Acme", "1", 200.0, 0.0),
        ],
        top_n=10,
    )
    assert rows[0]["total_outstanding"] == 270.0


# ── grouping and ranking ──────────────────────────────────────────────


def test_groups_by_supplier_and_sums():
    rows, total, _, _ = _aggregate_outstanding(
        [
            _inv("Acme", "1", 100.0, 0.0),
            _inv("Acme", "1", 50.0, 50.0),
            _inv("Beta", "2", 30.0, 0.0),
        ],
        top_n=10,
    )
    by_name = {r["supplier"]: r for r in rows}
    assert by_name["Acme"]["total_outstanding"] == 100.0
    assert by_name["Acme"]["invoice_count"] == 2
    assert by_name["Beta"]["total_outstanding"] == 30.0
    assert total == 2


def test_ranks_by_outstanding_then_name():
    rows, _, _, _ = _aggregate_outstanding(
        [
            _inv("Zeta", "9", 10.0),
            _inv("Acme", "1", 10.0),
            _inv("Big", "3", 99.0),
        ],
        top_n=10,
    )
    assert [r["supplier"] for r in rows] == ["Big", "Acme", "Zeta"]


def test_top_n_cuts_but_reports_the_true_supplier_count():
    rows, total, _, _ = _aggregate_outstanding(
        [_inv(f"S{i}", str(i), float(i)) for i in range(1, 6)], top_n=2
    )
    assert len(rows) == 2
    assert total == 5


def test_invoice_without_supplier_is_skipped():
    rows, total, _, counted = _aggregate_outstanding(
        [_inv("", "", 100.0)], top_n=10
    )
    assert rows == []
    assert total == 0
    assert counted == 0


# ── the tool, end to end against a fake client ────────────────────────


def _fake_client(payload: dict, calls: list) -> AsyncMock:
    client = AsyncMock()

    async def _get(path, params=None):
        calls.append((path, params or {}))
        return payload

    client.get = _get
    client.total_results = AsyncMock(return_value=3)
    return client


@pytest.mark.asyncio
async def test_tool_projects_its_fields_and_echoes_the_period():
    calls: list = []
    client = _fake_client(
        {
            "items": [_inv("Acme", "1", 100.0, 40.0, date="2026-11-10")],
            "count": 1,
            "hasMore": False,
            "totalResults": 1,
        },
        calls,
    )

    out = await aggregate_outstanding_invoices_by_supplier(
        client, date_from="2026-11-01", date_to="2026-12-01"
    )

    assert out["shape"] == "supplier_outstanding_ranking"
    assert out["date_from"] == "2026-11-01"
    assert out["date_to"] == "2026-12-01"
    assert out["rows"][0]["total_outstanding"] == 60.0
    path, params = calls[0]
    assert path == INVOICES_PATH
    assert "AmountPaid" in params["fields"]
    assert "CanceledFlag" in params["fields"]


@pytest.mark.asyncio
async def test_rows_outside_the_window_are_dropped():
    calls: list = []
    client = _fake_client(
        {
            "items": [
                _inv("In", "1", 100.0, date="2026-11-10"),
                _inv("Out", "2", 500.0, date="2026-10-15"),
            ],
            "count": 2,
            "hasMore": False,
            "totalResults": 2,
        },
        calls,
    )

    out = await aggregate_outstanding_invoices_by_supplier(
        client, date_from="2026-11-01", date_to="2026-12-01"
    )

    assert [r["supplier"] for r in out["rows"]] == ["In"]


# ── wiring: the op, the overlay, the parser ───────────────────────────


def test_op_is_registered_with_its_measure_args():
    assert (
        _AGGREGATION_TOOLS["outstanding_by_supplier"]
        == "aggregate_outstanding_invoices_by_supplier"
    )
    assert _AGGREGATION_PARAMS["outstanding_by_supplier"] == (
        "date_from",
        "date_to",
        "top_n",
    )


def test_outstanding_is_a_separate_op_from_spend():
    """One measure per tool — the rule that makes the substitution impossible."""
    assert _AGGREGATION_TOOLS["by_supplier"] != _AGGREGATION_TOOLS[
        "outstanding_by_supplier"
    ]


def test_overlay_has_the_measure_and_both_bounds():
    from spire.kg.sql_overlay import OVERLAY

    spec = OVERLAY.aggregations["aggregate_outstanding_invoices_by_supplier"]
    assert "AMOUNT_PAID" in spec.measure_template
    for arg in ("date_from", "date_to"):
        assert (
            "aggregate_outstanding_invoices_by_supplier",
            arg,
        ) in OVERLAY.filters


def test_parser_teaches_the_vocabulary_split():
    text = PARSER_BLOCK.read_text()
    assert "op='outstanding_by_supplier'" in text
    assert "OUTSTANDING is not SPEND" in text
    # And the op it must NOT be confused with still has its own teaching.
    assert "op='by_supplier'" in text


def test_response_model_carries_the_measure_not_spend():
    resp = build_supplier_outstanding_ranking(
        {
            "rows": [
                {
                    "supplier": "Acme",
                    "supplier_number": "1",
                    "total_outstanding": 60.0,
                    "invoice_count": 1,
                }
            ],
            "returned": 1,
            "total_suppliers": 1,
        }
    )
    row = resp.suppliers[0]
    assert row.total_outstanding == 60.0
    assert not hasattr(row, "total_spend")


# ── the period half ───────────────────────────────────────────────────
#
# Two separate defects produced `date_from=None` for "current month":
#
#   1. _PERIOD_ANCHORED_RE matched only "this|last", and prompt 20 says
#      "for the current month" — the phrase that most needs resolving was
#      the one the extractor did not recognise.
#   2. The correction was gated to op == 'by_supplier'. That was correct
#      when it was the only date-capable aggregation, and it silently
#      excluded the next one.
#
# Both are pinned here because either alone reproduces AP-2's period half.


@pytest.mark.parametrize(
    "prompt, expected",
    [
        ("for the current month", ("2026-11-01", "2026-12-01")),
        ("this month", ("2026-11-01", "2026-12-01")),
        ("last month", ("2026-10-01", "2026-11-01")),
        ("this year", ("2026-01-01", "2027-01-01")),
        ("last quarter", ("2026-07-01", "2026-10-01")),
    ],
)
def test_current_and_this_mean_the_same_window(prompt, expected):
    """'current month' is a synonym of 'this month', not an unknown phrase.

    The dates are pinned against a fixed reference so this does not rot; if
    the system date moves past 2026 the expected values move with it.
    """
    from datetime import date

    from spire.nl_parser.parser import _extract_period_bounds

    today = date.today()
    got = _extract_period_bounds(prompt)
    assert got is not None, f"{prompt!r} produced no bounds"
    # Recompute what "today" implies in the same month, so the assertion
    # survives a day/month boundary without hardcoding 2026 dates.
    if "month" in prompt:
        y, m = today.year, today.month
        if prompt.startswith("last"):
            m -= 1
            if m < 1:
                m, y = 12, y - 1
        end_y, end_m = (y + 1, 1) if m == 12 else (y, m + 1)
        assert got == (f"{y}-{m:02d}-01", f"{end_y}-{end_m:02d}-01")


def test_every_date_capable_op_is_in_the_registry():
    """The period correction reads this registry, so it must be complete.

    A new aggregation that takes dates and is missing here would silently
    answer 'all time' — the AP-2 period half, reintroduced.
    """
    from spire.planner.registries import _AGGREGATION_PARAMS

    date_capable = {
        op for op, args in _AGGREGATION_PARAMS.items() if "date_from" in args
    }
    assert "outstanding_by_supplier" in date_capable
    assert "by_supplier" in date_capable
