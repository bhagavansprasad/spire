"""The AR invoice list is built from the data, not by the model.

WHY THIS FILE EXISTS

The suite went 779 -> 779 when the AR-invoice synthesize call was
removed. Nothing mocked it, so nothing noticed it had gone — and
nothing would notice if a builder started attaching tax rows to the
wrong lines.

THE JOIN IS THE POINT

Tax rows join to invoice lines on ParentCustomerTransactionLineId, NOT
on their own CustomerTransactionLineId. A tax row carries both, and its
own is the TAX line's primary key — 112, say — while the invoice line
it belongs to is 74.

Joining on the obvious-looking field matches nothing, or matches the
wrong line. The failure would not look like a failure: every line would
show two tax rows, the totals would look plausible, and the taxable
amounts would sit under the wrong lines.

That caution is written down in docs/spire_fusion_endpoints_reference.md
and was found only after two wrong guesses — including a curl against
an endpoint that does not exist. The reference doc is the authority on
pod behaviour; these tests pin what it says so the next reader does not
have to find it the same way.
"""

import pytest

from spire.synthesizer.ar import (
    build_receivables_invoice_records,
    single_parent_shape,
)


# Invoice 1002 (TransactionNumber 5): 4 lines, 2 tax rows each. Anchor
# from the endpoints reference. Line 74 -> 10,592; line 84 -> 26,480.
_MARKERS = ("CustomerTransactionId", "TransactionNumber", "InvoiceCurrencyCode")


@pytest.fixture
def invoice_row():
    return {
        "CustomerTransactionId": 1002,
        "TransactionNumber": "5",
        "TransactionDate": "2013-12-20",
        "BillToCustomerName": "Business World",
        "BillToCustomerNumber": "16080",
        "InvoiceCurrencyCode": "USD",
        "EnteredAmount": 297998.93,
        "InvoiceBalanceAmount": 0,
        "InvoiceStatus": "Complete",
    }


@pytest.fixture
def line_rows():
    return [
        {
            "CustomerTransactionLineId": 74,
            "LineNumber": 1,
            "Description": "Green Server 1000",
            "Quantity": 2,
            "UnitSellingPrice": 5296,
            "LineAmount": 10592,
        },
        {
            "CustomerTransactionLineId": 84,
            "LineNumber": 2,
            "Description": "Green Server 1000",
            "Quantity": 5,
            "UnitSellingPrice": 5296,
            "LineAmount": 26480,
        },
    ]


@pytest.fixture
def tax_rows():
    """Two per line. Note each row's OWN CustomerTransactionLineId is the
    tax line's PK and is deliberately different from the parent id — a
    builder joining on it would match nothing here, which is the whole
    point of the fixture."""
    return [
        {
            "CustomerTransactionLineId": 112,
            "ParentCustomerTransactionLineId": 74,
            "TaxLineNumber": 1,
            "Tax": "STATE",
            "TaxRate": 6.5,
            "TaxAmount": 688.48,
            "TaxableAmount": 10592.0,
            "TaxJurisdictionCode": "ST-050000000",
        },
        {
            "CustomerTransactionLineId": 113,
            "ParentCustomerTransactionLineId": 74,
            "TaxLineNumber": 2,
            "Tax": "COUNTY",
            "TaxRate": 2.25,
            "TaxAmount": 238.32,
            "TaxableAmount": 10592.0,
            "TaxJurisdictionCode": "CO-050850000",
        },
        {
            "CustomerTransactionLineId": 122,
            "ParentCustomerTransactionLineId": 84,
            "TaxLineNumber": 1,
            "Tax": "STATE",
            "TaxRate": 6.5,
            "TaxAmount": 1721.2,
            "TaxableAmount": 26480.0,
            "TaxJurisdictionCode": "ST-050000000",
        },
        {
            "CustomerTransactionLineId": 123,
            "ParentCustomerTransactionLineId": 84,
            "TaxLineNumber": 2,
            "Tax": "COUNTY",
            "TaxRate": 2.25,
            "TaxAmount": 595.8,
            "TaxableAmount": 26480.0,
            "TaxJurisdictionCode": "CO-050850000",
        },
    ]


def test_tax_rows_land_on_their_own_line(invoice_row, line_rows, tax_rows):
    """The join. Each line gets ITS two tax rows, and the taxable amount
    on each matches that line's own amount — which is what catches a
    join that ran on the wrong key. Under a wrong join every line still
    shows two tax rows and the output still looks plausible; only the
    pairing is wrong."""
    (record,) = build_receivables_invoice_records(
        [invoice_row],
        {"receivables_invoice_lines": line_rows, "receivablestaxline": tax_rows},
    )

    line1, line2 = record.lines
    assert line1.amount == 10592.0
    assert [t.taxable_amount for t in line1.tax_lines] == [10592.0, 10592.0]
    assert sorted(t.tax for t in line1.tax_lines) == ["COUNTY", "STATE"]
    assert sorted(t.tax_amount for t in line1.tax_lines) == [238.32, 688.48]

    assert line2.amount == 26480.0
    assert [t.taxable_amount for t in line2.tax_lines] == [26480.0, 26480.0]
    assert sorted(t.tax_amount for t in line2.tax_lines) == [595.8, 1721.2]


def test_a_tax_row_without_a_parent_id_is_dropped(
    invoice_row, line_rows, tax_rows
):
    """Dropped, not attached to an arbitrary line. A tax figure under the
    wrong line is worse than one not shown: the reader cannot tell."""
    tax_rows[0].pop("ParentCustomerTransactionLineId")
    (record,) = build_receivables_invoice_records(
        [invoice_row],
        {"receivables_invoice_lines": line_rows, "receivablestaxline": tax_rows},
    )
    line1, line2 = record.lines
    assert len(line1.tax_lines) == 1
    assert len(line2.tax_lines) == 2


def test_lines_without_tax_rows_are_fine(invoice_row, line_rows):
    """An untaxed invoice is normal — anchor 61765 has none."""
    (record,) = build_receivables_invoice_records(
        [invoice_row], {"receivables_invoice_lines": line_rows}
    )
    assert all(ln.tax_lines == [] for ln in record.lines)


def test_invoice_fields_reach_the_record(invoice_row, line_rows):
    (record,) = build_receivables_invoice_records(
        [invoice_row], {"receivables_invoice_lines": line_rows}
    )
    assert record.customer_transaction_id == 1002
    assert record.transaction_number == "5"
    assert record.transaction_date == "2013-12-20"
    assert record.bill_to_customer_name == "Business World"
    assert record.currency == "USD"
    assert record.amount == 297998.93
    assert record.status == "Complete"


def test_the_shape_is_recognised(invoice_row, line_rows):
    shape = single_parent_shape(
        {"receivables_invoices": [invoice_row],
         "receivables_invoice_lines": line_rows},
        _MARKERS,
    )
    assert shape is not None
    parent, children = shape
    assert parent == "receivables_invoices"
    assert set(children) == {"receivables_invoice_lines"}


def test_several_child_buckets_are_allowed(invoice_row, line_rows, tax_rows):
    """The rule is one parent row and ANY number of children. Derived
    from all sixteen prompts in 03_ar.txt, not the first three looked
    at — the rule those three suggested was one parent, ONE child, and
    this case has two."""
    shape = single_parent_shape(
        {
            "receivables_invoices": [invoice_row],
            "receivables_invoice_lines": line_rows,
            "receivablestaxline": tax_rows,
        },
        _MARKERS,
    )
    assert shape is not None
    _, children = shape
    assert set(children) == {"receivables_invoice_lines", "receivablestaxline"}


def test_a_multi_row_parent_is_rejected(invoice_row, line_rows):
    """ONE parent row is what makes attaching children safe. With several,
    which child belongs to which parent is real work and stays with the
    model."""
    second = dict(invoice_row, CustomerTransactionId=1003)
    assert (
        single_parent_shape(
            {"receivables_invoices": [invoice_row, second],
             "receivables_invoice_lines": line_rows},
            _MARKERS,
        )
        is None
    )


def test_two_matching_buckets_are_ambiguous(invoice_row):
    """If two buckets both look like the parent, there is no basis for
    picking one. Ambiguous goes to the model."""
    assert (
        single_parent_shape(
            {"a": [invoice_row], "b": [dict(invoice_row)]}, _MARKERS
        )
        is None
    )


def test_a_bucket_missing_one_marker_is_not_claimed(invoice_row):
    """ALL markers must be present. A credit memo row carries
    CustomerTransactionId too — one marker would claim the wrong bucket,
    and a wrong bucket returns wrong data confidently."""
    memo_like = {"CustomerTransactionId": 300000313072555,
                 "TransactionNumber": "11001"}
    assert single_parent_shape({"credit_memos": [memo_like]}, _MARKERS) is None


def test_no_outputs_is_not_a_shape():
    assert single_parent_shape({}, _MARKERS) is None
