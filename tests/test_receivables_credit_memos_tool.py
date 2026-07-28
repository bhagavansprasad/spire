"""Tests for the credit-memo total.

compute_total_credit is pure — no client, no pod — because the bug it
fixes was arithmetic that nothing checked. The tool that produced it ran
green for weeks while emitting a number in no currency at all.
"""

from spire.mcp_server.tools.receivables_credit_memos import compute_total_credit


def _memo(amount, currency, status="Complete"):
    return {
        "CustomerTransactionId": 1,
        "EnteredAmount": amount,
        "CreditMemoCurrency": currency,
        "CreditMemoStatus": status,
    }


def test_single_currency_totals():
    """One currency: a plain ledger sum, and no note."""
    total, note = compute_total_credit(
        [_memo(-150, "USD"), _memo(-300, "USD"), _memo(-750, "USD")]
    )
    assert total == -1200.0
    assert note is None


def test_positive_memo_offsets_the_negatives():
    """A positive memo nets against the credits. This is DELIBERATE — the
    ledger reading — and the pod really does carry one (an Incomplete
    +10,000 among the negatives). Whether an Incomplete memo belongs in a
    total is a domain question; the arithmetic here is not the issue."""
    total, note = compute_total_credit(
        [_memo(-2000, "USD"), _memo(10000, "USD", status="Incomplete")]
    )
    assert total == 8000.0
    assert note is None


def test_mixed_currencies_withhold_the_total():
    """THE BUG. These four rows previously summed to a single float and
    were printed as 'Total credit value: -17232.52' — arithmetically
    correct, semantically nothing. No total is now given."""
    total, note = compute_total_credit(
        [
            _memo(-150, "USD"),
            _memo(-23.72, "CAD"),
            _memo(-2583, "GBP"),
            _memo(-546, "EUR"),
        ]
    )
    assert total is None
    assert note is not None
    assert "4 currencies" in note
    # The note must NAME them: "spans several currencies" leaves the reader
    # unable to act. Knowing which four means knowing what to ask next.
    for code in ("CAD", "EUR", "GBP", "USD"):
        assert code in note


def test_two_currencies_is_already_mixed():
    """The boundary is TWO, not some threshold. USD + CAD has no total."""
    total, note = compute_total_credit([_memo(-100, "USD"), _memo(-100, "CAD")])
    assert total is None
    assert "2 currencies" in note


def test_empty_list_totals_zero():
    """No memos is a real answer, not a missing one: zero credit, not
    'cannot be totalled'."""
    total, note = compute_total_credit([])
    assert total == 0.0
    assert note is None


def test_null_amounts_count_as_zero():
    """A null EnteredAmount must not blow up the sum."""
    total, note = compute_total_credit(
        [_memo(-150, "USD"), _memo(None, "USD")]
    )
    assert total == -150.0
    assert note is None


def test_rows_without_a_currency_do_not_trigger_the_guard():
    """A missing CreditMemoCurrency is unknown, not a second currency.
    Treating null as its own currency would withhold totals from
    single-currency results that happen to have a gappy row."""
    total, note = compute_total_credit(
        [_memo(-150, "USD"), _memo(-50, None)]
    )
    assert total == -200.0
    assert note is None


def test_all_rows_missing_currency_still_totals():
    """No currency information at all: nothing proves a mix, so the
    ledger sum stands."""
    total, note = compute_total_credit([_memo(-150, None), _memo(-50, None)])
    assert total == -200.0
    assert note is None


def test_total_and_note_are_mutually_exclusive():
    """The contract every caller relies on: exactly one is set. The
    display renders one OR the other — a caller that got both would have
    to choose, and would choose wrong."""
    cases = [
        [_memo(-150, "USD")],
        [_memo(-150, "USD"), _memo(-150, "GBP")],
        [],
    ]
    for items in cases:
        total, note = compute_total_credit(items)
        assert (total is None) != (note is None), items
