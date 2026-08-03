"""The credit-memo list is built from the data, not by the model.

WHY THIS FILE EXISTS

The supplier and credit-memo list paths stopped calling the LLM, and the
full suite did not move: 771 before, 771 after. Nothing mocked those
calls, so nothing noticed they were gone — and nothing would notice if
they came back, or if a builder silently dropped a field.

Every defect in that work was found by running a prompt and reading the
screen. "1 suppliers", a doubled blank line, a truncation note reading
"None examined", a contacts column joined with commas where the names
themselves contain commas. None was found by reading code, and the
suite was green throughout.

These are pure functions with no I/O, which makes them cheap to pin.
The list paths that are NOT pinned are the ones to worry about.

THE FIELD-COUNT TEST IS THE POINT

build_credit_memo_records maps eight fields. The obvious failure is not
a crash — it is one field quietly not mapped, which shows up as an empty
column that looks like missing data rather than a bug. A row that
carried a customer name and rendered without one is exactly what this
session spent two turns misreading.
"""

import pytest

from spire.synthesizer.ar import (
    build_credit_memo_records,
    plain_credit_memo_bucket,
)


@pytest.fixture
def memo_row():
    """One credit-memo row exactly as the tool projects it.

    All eight projected fields, plus the two the server wrapper stamps
    onto every row (total_credit, total_credit_note) so the scalar
    survives the executor's unwrap. Those two are not part of the
    record and must not end up in it.
    """
    return {
        "CustomerTransactionId": 300000313072555,
        "TransactionNumber": "11001",
        "TransactionDate": "2026-07-09",
        "EnteredAmount": -150,
        "CreditMemoCurrency": "USD",
        "CreditMemoStatus": "Complete",
        "BillToCustomerName": "DMART",
        "BillToCustomerNumber": "26360",
        "total_credit": None,
        "total_credit_note": "Not totalled: these memos span 4 currencies.",
    }


def test_every_projected_field_reaches_the_record(memo_row):
    """All eight, by value. A field that silently fails to map renders
    as an empty column, which reads as missing DATA rather than a bug."""
    (record,) = build_credit_memo_records([memo_row])

    assert record.customer_transaction_id == 300000313072555
    assert record.transaction_number == "11001"
    assert record.transaction_date == "2026-07-09"
    assert record.entered_amount == -150.0
    assert record.currency == "USD"
    assert record.status == "Complete"
    assert record.customer_name == "DMART"
    assert record.customer_number == "26360"


def test_a_positive_amount_is_copied_not_corrected(memo_row):
    """EnteredAmount is NORMALLY negative and the pod carries at least
    one positive, Incomplete memo. "Normally negative" is an observation
    about the data, not a rule the builder may enforce."""
    memo_row["EnteredAmount"] = 10000
    memo_row["CreditMemoStatus"] = "Incomplete"
    (record,) = build_credit_memo_records([memo_row])
    assert record.entered_amount == 10000.0


def test_a_missing_field_does_not_crash(memo_row):
    """Defensive. A row short of a field should render an empty value,
    not take the whole answer down."""
    del memo_row["BillToCustomerName"]
    (record,) = build_credit_memo_records([memo_row])
    assert record.customer_name == ""
    assert record.transaction_number == "11001"


def test_no_rows_gives_no_records():
    assert build_credit_memo_records([]) == []


def test_the_bucket_is_recognised(memo_row):
    assert plain_credit_memo_bucket({"credit_memos": [memo_row]}) == "credit_memos"


def test_two_buckets_are_not_plain(memo_row):
    """Anything needing a join across buckets stays with the model.
    Returning None too often costs tokens; returning a wrong bucket
    costs correctness."""
    assert (
        plain_credit_memo_bucket(
            {"credit_memos": [memo_row], "customers": [{"CustomerId": 1}]}
        )
        is None
    )


def test_a_non_memo_bucket_is_not_claimed():
    assert (
        plain_credit_memo_bucket(
            {"suppliers": [{"SupplierId": 1, "Supplier": "Lee Supplies"}]}
        )
        is None
    )


def test_an_empty_bucket_is_not_claimed():
    assert plain_credit_memo_bucket({"credit_memos": []}) is None
