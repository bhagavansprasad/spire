"""Customer accounts, standard receipts and DFF are built from the data.

WHY THIS FILE EXISTS

Three LLM calls have now been removed from three separate paths and the
suite reported 771 -> 771, 779 -> 779, 789 -> 789. Nothing mocked any of
them. A green suite says nothing about whether these paths work, and
would say nothing if a builder started writing zeros.

THE KEY NAMES ARE THE RISK

Four child buckets hang off a customer account and none of their key
names follows from the others:

    customer_transactions          TransactionId, TotalOriginalAmount
    account_credit_memos           CreditMemoId, TotalOriginalAmount
    account_receipts               StandardReceiptId, Amount
    account_receipt_applications   ApplicationId, ReferenceTransactionId

The applications bucket is the trap. Its transaction fields are
ReferenceTransactionId and ReferenceTransactionNumber, NOT
TransactionId. A builder copying the pattern from customer_transactions
reads two fields that do not exist and writes 0 and "" into every row —
a column of zeros that looks like data the pod does not hold, rather
than like a bug.

The DFF bucket is stranger still: its id is CustomerTrxId, and the
context fields carry a DOUBLE leading underscore. Read wrong, the DFF
block renders empty and looks like an invoice without flexfield values.

None of these were deduced. They came from --show-raw-output after it
stopped truncating rows at six fields.
"""

import pytest

from spire.synthesizer.ar import (
    build_customer_account_records,
    build_invoice_dff,
    build_standard_receipt_records,
    single_parent_shape,
)


_ACCOUNT_MARKERS = (
    "AccountId",
    "AccountNumber",
    "TotalOpenReceivablesForAccount",
)


@pytest.fixture
def account_row():
    """Account 26360. TotalTransactionsDueForAccount on the SIBLING
    account 26370 is 1179915.3225 — four decimals that do not terminate
    in IEEE-754, which once ran the synthesizer to its token cap."""
    return {
        "AccountId": 300000047368512,
        "AccountNumber": "26360",
        "CustomerName": "ABC Application Software",
        "CustomerId": 100000000395795,
        "TotalOpenReceivablesForAccount": 678923.69,
        "TotalTransactionsDueForAccount": 700386.75,
    }


def test_account_fields_reach_the_record(account_row):
    (record,) = build_customer_account_records([account_row], {})
    assert record.account_id == 300000047368512
    assert record.account_number == "26360"
    assert record.customer_name == "ABC Application Software"
    assert record.open_receivables == 678923.69
    assert record.transactions_due == 700386.75


def test_applications_read_the_reference_fields(account_row):
    """THE TRAP. Reference*, not Transaction*. Under the wrong key names
    this passes structurally — ten application rows, correct count — and
    every transaction id is 0."""
    apps = [
        {
            "ApplicationId": 808685,
            "StandardReceiptId": 533182,
            "ReceiptNumber": "498928",
            "ReceiptMethod": "Check (Directly/No Remit)",
            "ReferenceTransactionId": 1394826,
            "ReferenceTransactionNumber": "1391923",
            "ReferenceTransactionStatus": "Closed",
            "ApplicationAmount": 8052.94,
            "ApplicationDate": "2024-07-03",
            "EnteredCurrency": "USD",
        }
    ]
    (record,) = build_customer_account_records(
        [account_row], {"account_receipt_applications": apps}
    )
    (app,) = record.applications
    assert app.transaction_id == 1394826
    assert app.transaction_number == "1391923"
    assert app.transaction_status == "Closed"
    assert app.application_amount == 8052.94
    assert app.currency == "USD"
    assert app.receipt_number == "498928"


def test_transactions_map(account_row):
    txns = [
        {
            "TransactionId": 10464,
            "TransactionNumber": "1002215",
            "TransactionClass": "Invoice",
            "TransactionDate": "2012-03-21",
            "TotalOriginalAmount": 1591.28,
            "TotalBalanceAmount": 0,
            "InstallmentStatus": "Closed",
        }
    ]
    (record,) = build_customer_account_records(
        [account_row], {"customer_transactions": txns}
    )
    (t,) = record.transactions
    assert t.transaction_id == 10464
    assert t.transaction_number == "1002215"
    assert t.transaction_class == "Invoice"
    assert t.amount == 1591.28


def test_account_credit_memos_map(account_row):
    """Note these are NOT the same shape as the top-level credit memo
    list: CreditMemoId and TotalOriginalAmount here, against
    CustomerTransactionId and EnteredAmount there."""
    memos = [
        {
            "CreditMemoId": 1284799,
            "CreditMemoNumber": "1358582",
            "CreditMemoDate": "2023-07-15",
            "TotalOriginalAmount": -215.33,
            "TotalBalanceAmount": -215.33,
            "CreditMemoCurrency": "USD",
            "CreditMemoStatus": "Complete",
        }
    ]
    (record,) = build_customer_account_records(
        [account_row], {"account_credit_memos": memos}
    )
    (m,) = record.credit_memos
    assert m.credit_memo_id == 1284799
    assert m.credit_memo_number == "1358582"
    assert m.amount == -215.33
    assert m.currency == "USD"


def test_account_receipts_map(account_row):
    receipts = [
        {
            "StandardReceiptId": 300000313660599,
            "ReceiptNumber": "PA-2026-000145",
            "ReceiptDate": "2026-06-30",
            "Amount": 1347.42,
            "Currency": "USD",
            "ReceiptMethod": "Lockbox",
            "State": "Cleared",
            "UnappliedAmount": 0,
        }
    ]
    (record,) = build_customer_account_records(
        [account_row], {"account_receipts": receipts}
    )
    (r,) = record.receipts
    assert r.receipt_id == 300000313660599
    assert r.receipt_number == "PA-2026-000145"
    assert r.amount == 1347.42
    assert r.receipt_method == "Lockbox"


def test_an_account_with_no_children_is_fine(account_row):
    """The bare balance query fetches one bucket and nothing else."""
    (record,) = build_customer_account_records([account_row], {})
    assert record.transactions == []
    assert record.credit_memos == []
    assert record.receipts == []
    assert record.applications == []


def test_standard_receipts_carry_the_account_number():
    """CustomerAccountNumber is copied deliberately, not as redundancy.
    The endpoints reference records that the site "Santa Clara" spans
    accounts 26360 AND 26370 — a receipt list that does not resolve to
    an account number cannot be trusted."""
    rows = [
        {
            "StandardReceiptId": 300000309494188,
            "ReceiptNumber": "AA",
            "ReceiptDate": "2026-06-09",
            "Amount": 15000,
            "Currency": "USD",
            "ReceiptMethod": "Check (Directly/No Remit)",
            "Status": "Cleared",
            "CustomerName": "ABC Application Software",
            "CustomerAccountNumber": "26360",
            "CustomerSite": "Santa Clara",
            "RemittanceBankName": "Bank of America",
            "RemittanceBankBranch": "Main",
            "RemittanceBankAccountNumber": "1234",
        }
    ]
    (record,) = build_standard_receipt_records(rows)
    assert record.customer_account_number == "26360"
    assert record.customer_site == "Santa Clara"
    assert record.amount == 15000.0
    assert record.remittance_bank_name == "Bank of America"


def test_dff_reads_the_double_underscore_keys():
    """CustomerTrxId, and __FLEX_Context with TWO leading underscores.
    Read wrong this renders an empty DFF block, which looks like an
    invoice carrying no flexfield values."""
    dff = build_invoice_dff(
        [{"CustomerTrxId": 1002, "__FLEX_Context": "DOO",
          "__FLEX_Context_DisplayValue": None}]
    )
    assert dff is not None
    assert dff.context == "DOO"
    assert dff.context_display_value == ""


def test_no_dff_rows_gives_none():
    assert build_invoice_dff([]) is None


def test_the_account_shape_is_recognised(account_row):
    shape = single_parent_shape(
        {"customer_accounts": [account_row],
         "account_receipts": [{"StandardReceiptId": 1}]},
        _ACCOUNT_MARKERS,
    )
    assert shape is not None
    parent, children = shape
    assert parent == "customer_accounts"
    assert set(children) == {"account_receipts"}
