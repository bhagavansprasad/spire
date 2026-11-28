"""F-089 — the alias must qualify columns, never function names.

The emitted SQL for `aggregate_outstanding_invoices_by_supplier` read:

    SUM(P.GREATEST(NVL(INVOICE_AMOUNT, 0) - NVL(AMOUNT_PAID, 0), 0))

and Oracle rejected it with `ORA-00904: "P"."GREATEST": invalid identifier`,
because the alias was prefixed onto the whole inner expression rather than
onto the column references inside it.

What makes this worth a dedicated file: the *answer* was correct. The tool
computes `GREATEST(invoiced - paid, 0)` in Python and its top-10 matched the
equivalent SQL row for row. Every other check passed as well —
`validate_sql_coverage.py`, the AP-2 unit tests, and the live REST answer.
Only executing the emitted statement caught it, so these tests assert on the
documented failure mode (`<alias>.<FUNCTION>(`) rather than on the query's
meaning.
"""

from __future__ import annotations

import re

import pytest

from spire.kg.sql_overlay import OVERLAY
from spire.rendering.sql_emitter import _qualify_measure

# The actual template that produced the defect, kept verbatim.
_OUTSTANDING = "SUM(GREATEST(NVL(INVOICE_AMOUNT, 0) - NVL(AMOUNT_PAID, 0), 0))"

# `<alias>.<IDENT>(` is the signature of the bug: an alias applied to a
# function call. It is what Oracle reads as a column named after a function.
_ALIAS_ON_CALL = re.compile(r"\b[a-z]\.\w+\s*\(", re.IGNORECASE)


def test_composite_measure_qualifies_columns_not_functions():
    out = _qualify_measure(_OUTSTANDING, "P")

    assert out == (
        "SUM(GREATEST(NVL(P.INVOICE_AMOUNT, 0) - NVL(P.AMOUNT_PAID, 0), 0))"
    )
    # The defect in one assertion: no alias before a function call.
    assert "P.GREATEST" not in out
    assert "P.NVL" not in out
    assert _ALIAS_ON_CALL.search(out) is None


@pytest.mark.parametrize(
    "template, alias, expected",
    [
        ("SUM(AMOUNT)", "T", "SUM(T.AMOUNT)"),
        ("SUM(INVOICE_AMOUNT)", "P", "SUM(P.INVOICE_AMOUNT)"),
        ("COUNT(DISTINCT VENDOR_ID)", "P", "COUNT(DISTINCT P.VENDOR_ID)"),
        # A CASE expression: the comparison column and the value column are
        # both real references; the keyword and the literal are not.
        (
            "SUM(CASE WHEN STATUS = 'OPEN' THEN AMOUNT ELSE 0 END)",
            "T",
            "SUM(CASE WHEN T.STATUS = 'OPEN' THEN T.AMOUNT ELSE 0 END)",
        ),
    ],
)
def test_single_column_and_keyword_forms(template, alias, expected):
    assert _qualify_measure(template, alias) == expected


def test_correlated_subquery_is_returned_unchanged():
    """It carries its own aliases; prefixing them would corrupt the query."""
    template = (
        "SUM((SELECT SUM(L.UNIT_PRICE * L.QUANTITY) "
        "FROM PO_LINES_ALL L "
        "WHERE L.PO_HEADER_ID = P.PO_HEADER_ID))"
    )
    assert _qualify_measure(template, "P") == template


def test_string_literal_contents_are_never_qualified():
    """A column-shaped word inside quotes is data, not a reference."""
    out = _qualify_measure("SUM(CASE WHEN FLAG = 'AMOUNT' THEN 1 ELSE 0 END)", "T")
    assert "'AMOUNT'" in out
    assert "'T.AMOUNT'" not in out


def test_already_qualified_columns_are_left_alone():
    out = _qualify_measure("SUM(L.UNIT_PRICE)", "P")
    assert out == "SUM(L.UNIT_PRICE)"


def test_every_overlay_measure_template_qualifies_cleanly():
    """No aggregation may emit an alias onto a function name.

    This walks the real overlay rather than a fixture, so a future
    composite template cannot reintroduce the defect unnoticed.
    """
    specs = [
        spec
        for spec in OVERLAY.aggregations.values()
        if getattr(spec, "measure_template", None)
    ]
    assert specs, "expected aggregation specs in the overlay"

    offenders = []
    for spec in specs:
        emitted = _qualify_measure(spec.measure_template, "P")
        if _ALIAS_ON_CALL.search(emitted):
            offenders.append((spec.tool_name, emitted))
    assert offenders == [], f"alias applied to a function call: {offenders}"
