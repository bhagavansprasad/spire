"""R1b — an included child collection must reach the answer.

p13 asks for the 184 lines of invoice `ERS-53004-755598`. The executor
fetches them — the run log records `invoiceline: 184 record(s)` and
`Final raw output: 184 record(s) under 'invoiceline'` — and the answer
showed the invoice header alone.

Two things conspired:

1. Every requested column ("line number, description, quantity, unit price,
   amount, line type") is an `InvoiceLine` column, so intent_validation
   classified them as **satisfied by the include** and removed them from
   `fields`. The render turn then had `fields == []` and `unresolved == []`
   — the branch that renders the typed response, not a projected table.
2. The typed response for an Invoice root is `InvoiceResponse`, which has no
   child collection. The rows had nowhere to land.

So the data was fetched, correctly counted, sent to the prompt, and then
discarded at the last step. `_format_included_tables` renders them from the
executor output, which is where they demonstrably still are.
"""

from __future__ import annotations

from spire.rendering.formatters import _format_included_tables


class _Menu:
    """Minimal stand-in for KGMenu — only available_columns is used."""

    def __init__(self, catalog: dict[str, list[str]] | None = None):
        self._catalog = catalog or {}

    def available_columns(self, entity: str) -> list[str]:
        return list(self._catalog.get(entity, []))


_INVOICE_LINE_CATALOG = [
    "AccountingDate",
    "AssessableValue",
    "Description",
    "ItemDescription",
    "LineAmount",
    "LineNumber",
    "LineType",
    "Quantity",
    "UOM",
    "UnitPrice",
]


def _line(number: int) -> dict:
    return {
        "LineNumber": number,
        "Description": "Services",
        "Quantity": 1,
        "UnitPrice": 1997,
        "LineAmount": 1997,
        "LineType": "Item",
    }


def test_the_184_lines_reach_the_answer():
    """The p13 shape: bucket named after the include, six columns of rows."""
    outputs = {
        "invoices": [{"InvoiceNumber": "ERS-53004-755598"}],
        "invoiceline": [_line(i) for i in range(1, 185)],
    }
    menu = _Menu({"InvoiceLine": _INVOICE_LINE_CATALOG})

    out = _format_included_tables(outputs, ["InvoiceLine"], menu)

    assert "184 record(s)" in out
    assert "LineNumber" in out
    assert "LineType" in out
    # Spot-check the first and last row actually rendered.
    assert "Item" in out


def test_columns_follow_the_catalog_not_dict_order():
    """The table must read like the entity, not like a Python dict."""
    outputs = {"invoiceline": [_line(1)]}
    menu = _Menu({"InvoiceLine": _INVOICE_LINE_CATALOG})

    out = _format_included_tables(outputs, ["InvoiceLine"], menu)
    header = next(line for line in out.splitlines() if "|" in line)

    # Catalog order is alphabetical here; the point is that it is the
    # catalog's order and not the row dict's insertion order.
    assert header.index("Description") < header.index("LineNumber")
    assert header.index("LineNumber") < header.index("UnitPrice")


def test_row_keys_outside_the_catalog_are_not_hidden():
    """A tool that returns an extra field must not have it silently dropped."""
    row = _line(1)
    row["SomeToolOnlyField"] = "keep me"
    outputs = {"invoiceline": [row]}
    menu = _Menu({"InvoiceLine": _INVOICE_LINE_CATALOG})

    assert "SomeToolOnlyField" in _format_included_tables(
        outputs, ["InvoiceLine"], menu
    )


def test_bucket_match_is_case_insensitive():
    """The planner lowercases the entity name; the include does not."""
    outputs = {"invoiceline": [_line(1)]}
    menu = _Menu({"InvoiceLine": _INVOICE_LINE_CATALOG})

    assert "LineNumber" in _format_included_tables(
        outputs, ["InvoiceLine"], menu
    )


def test_empty_child_output_renders_nothing():
    """An include that returned no rows is not an error and not a table."""
    outputs = {"invoices": [{"InvoiceNumber": "X"}], "invoiceline": []}
    menu = _Menu({"InvoiceLine": _INVOICE_LINE_CATALOG})

    assert _format_included_tables(outputs, ["InvoiceLine"], menu) == ""


def test_missing_bucket_renders_nothing():
    outputs = {"invoices": [{"InvoiceNumber": "X"}]}
    menu = _Menu({"InvoiceLine": _INVOICE_LINE_CATALOG})

    assert _format_included_tables(outputs, ["InvoiceLine"], menu) == ""


def test_no_include_renders_nothing():
    outputs = {"invoices": [{"InvoiceNumber": "X"}]}
    menu = _Menu()

    assert _format_included_tables(outputs, [], menu) == ""
    assert _format_included_tables(outputs, None, menu) == ""


def test_no_outputs_renders_nothing():
    assert _format_included_tables({}, ["InvoiceLine"], _Menu()) == ""


def test_parent_bucket_is_not_rendered_as_a_child():
    """Only the include's own bucket; the invoice list is not a child table."""
    outputs = {
        "invoices": [{"InvoiceNumber": "ERS-53004-755598"}],
        "invoiceline": [_line(1)],
    }
    menu = _Menu({"InvoiceLine": _INVOICE_LINE_CATALOG})

    out = _format_included_tables(outputs, ["InvoiceLine"], menu)

    assert "ERS-53004-755598" not in out


def test_multiple_includes_each_get_a_table():
    outputs = {
        "invoiceline": [_line(1)],
        "invoicedistribution": [{"DistributionNumber": 1, "Amount": 10}],
    }
    menu = _Menu(
        {
            "InvoiceLine": _INVOICE_LINE_CATALOG,
            "InvoiceDistribution": ["DistributionNumber", "Amount"],
        }
    )

    out = _format_included_tables(
        outputs, ["InvoiceLine", "InvoiceDistribution"], menu
    )

    assert "LineNumber" in out
    assert "DistributionNumber" in out


def test_child_table_carries_no_competing_answer_heading():
    """It follows the parent's answer; a second "Answer:" would be F-088."""
    outputs = {"invoiceline": [_line(1)]}
    menu = _Menu({"InvoiceLine": _INVOICE_LINE_CATALOG})

    out = _format_included_tables(outputs, ["InvoiceLine"], menu)

    assert "Answer:" not in out
