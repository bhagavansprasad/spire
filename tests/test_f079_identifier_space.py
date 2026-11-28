"""F-079 / F-082 — an entity number is not its internal id.

The defect: a prompt saying "PO 55040" or "AR invoice 112390" supplies the
number a user reads off the document, but the SQL layer bound it to the
internal id column, so the statement returned **0 rows** for a record that
exists:

    PO 55040   -> SEGMENT1='55040', PO_HEADER_ID=67
    AR 112390  -> TRX_NUMBER='112390', CUSTOMER_TRX_ID=1533822

A clean zero is the most dangerous wrong answer: it is indistinguishable
from "no such record", so the narrative says the record does not exist.

Why the args were NOT split (`po_number` vs `po_header_id`): the parser
cannot tell which space a bare number is in — that ambiguity is the whole
reason these tools resolve instead of fetch. Splitting the arg would only
move the guess into the parser and produce the same silent zero. The
resolution is a runtime fact, so the SQL mirrors it:

    OrderNumber / TransactionNumber first, id only when no row claims
    that number.

These tests assert the predicate shape, the precedence, that the child
filters are untouched (they receive the already-resolved id), and that the
AR tool resolves both spaces.

FIX_PLAN §6 F-079, F-082.
"""

from __future__ import annotations

import pytest

from spire.kg.sql_overlay import OVERLAY
from spire.planner.models import Step
from spire.rendering.sql_emitter import emit_sql

PO_SPEC = ("get_purchase_order_by_id", "po_header_id")
AR_SPEC = ("get_receivables_invoice_by_id", "customer_transaction_id")


def _emit(tool: str, args: dict) -> str:
    step = Step(
        step_id=1,
        tool_name=tool,
        tool_args=args,
        iterate_over=None,
        client_filters=(),
        output_name="out1",
        output_dedupe_by=None,
    )
    return "\n".join(emit_sql([step]))


# ── Predicate shape ───────────────────────────────────────────────────


def test_po_by_id_predicate_covers_both_identifier_spaces():
    predicate = OVERLAY.filters[PO_SPEC].predicate_template
    assert "SEGMENT1" in predicate, "the printed OrderNumber space is missing"
    assert "PO_HEADER_ID" in predicate, "the internal id space is missing"


def test_ar_by_id_predicate_covers_both_identifier_spaces():
    predicate = OVERLAY.filters[AR_SPEC].predicate_template
    assert "TRX_NUMBER" in predicate, "the printed TransactionNumber is missing"
    assert "CUSTOMER_TRX_ID" in predicate, "the internal id space is missing"


def test_po_number_wins_over_the_id():
    """OrderNumber is tried first, matching the tool's precedence.

    Compared on the two resolution subqueries, not the whole predicate:
    the left-hand `PO_HEADER_ID` column appears before both of them and
    would match first in a naive `str.index`.
    """
    predicate = OVERLAY.filters[PO_SPEC].predicate_template
    assert predicate.index("WHERE H.SEGMENT1") < predicate.index(
        "WHERE H.PO_HEADER_ID"
    )


def test_ar_number_wins_over_the_id():
    predicate = OVERLAY.filters[AR_SPEC].predicate_template
    assert predicate.index("WHERE T.TRX_NUMBER") < predicate.index(
        "WHERE T.CUSTOMER_TRX_ID"
    )


def test_both_predicates_resolve_to_a_single_id():
    """COALESCE keeps the result one row, so SQL cannot return more than REST.

    A plain `SEGMENT1 = :v OR PO_HEADER_ID = :v` would return two POs when
    a number and an id happen to collide, which REST (one lookup per space)
    never does.
    """
    for key in (PO_SPEC, AR_SPEC):
        predicate = OVERLAY.filters[key].predicate_template
        assert "COALESCE" in predicate, key


# ── Emitted SQL ───────────────────────────────────────────────────────


def test_emitted_po_sql_resolves_the_number():
    sql = _emit("get_purchase_order_by_id", {"po_header_id": "55040"})
    assert "SEGMENT1 = '55040'" in sql
    assert "COALESCE" in sql


def test_emitted_ar_sql_resolves_the_number():
    sql = _emit("get_receivables_invoice_by_id",
                {"customer_transaction_id": "112390"})
    assert "TRX_NUMBER = '112390'" in sql
    assert "COALESCE" in sql


def test_child_filters_still_bind_the_resolved_id_directly():
    """Child steps receive a real id from the previous step's record.

    `get_purchase_order_lines` is fed `$iteration_value` from step 1's
    POHeaderId, so it must NOT re-resolve — a second resolution there
    would be wrong and would cost a subquery per row.
    """
    predicate = OVERLAY.filters[
        ("get_purchase_order_lines", "po_header_id")
    ].predicate_template
    assert "COALESCE" not in predicate
    assert "SEGMENT1" not in predicate
    assert predicate == "{alias}.PO_HEADER_ID = {value}"


# ── Assumptions documented ────────────────────────────────────────────


@pytest.mark.parametrize("key", [PO_SPEC, AR_SPEC])
def test_assumption_text_is_registered(key):
    """An unregistered assumption silently prints its bare key."""
    name = OVERLAY.filters[key].assumption
    assert name in OVERLAY.assumptions, f"{name} has no registered text"


# ── The AR tool resolves both spaces (F-082) ──────────────────────────


class _FakeClient:
    """Returns canned rows per `q=` clause, recording what was asked."""

    def __init__(self, rows_by_clause: dict[str, list[dict]]):
        self.rows_by_clause = rows_by_clause
        self.questions: list[str] = []

    async def get(self, path, params=None):
        clause = (params or {}).get("q", "")
        self.questions.append(clause)
        return {"items": self.rows_by_clause.get(clause, [])}


_INVOICE = {
    "CustomerTransactionId": 1533822,
    "TransactionNumber": "112390",
    "InvoiceStatus": "Complete",
    "EnteredAmount": 3949.1,
}


async def test_ar_tool_resolves_a_number():
    from spire.mcp_server.tools.receivables_invoice_by_id import (
        get_receivables_invoice_by_id,
    )

    client = _FakeClient({"TransactionNumber='112390'": [_INVOICE]})
    result = await get_receivables_invoice_by_id(client, "112390")

    assert result is not None
    assert result["CustomerTransactionId"] == 1533822
    # The number space was tried first, and the id space was not needed.
    assert client.questions == ["TransactionNumber='112390'"]


async def test_ar_tool_still_resolves_an_id():
    from spire.mcp_server.tools.receivables_invoice_by_id import (
        get_receivables_invoice_by_id,
    )

    client = _FakeClient({"CustomerTransactionId='1533822'": [_INVOICE]})
    result = await get_receivables_invoice_by_id(client, "1533822")

    assert result is not None
    assert result["TransactionNumber"] == "112390"
    assert client.questions == [
        "TransactionNumber='1533822'",
        "CustomerTransactionId='1533822'",
    ]


async def test_ar_tool_prefers_the_number_when_both_match():
    from spire.mcp_server.tools.receivables_invoice_by_id import (
        get_receivables_invoice_by_id,
    )

    by_number = dict(_INVOICE, CustomerTransactionId=111)
    by_id = dict(_INVOICE, CustomerTransactionId=222)
    client = _FakeClient(
        {
            "TransactionNumber='5'": [by_number],
            "CustomerTransactionId='5'": [by_id],
        }
    )
    result = await get_receivables_invoice_by_id(client, "5")

    assert result["CustomerTransactionId"] == 111
    assert client.questions == ["TransactionNumber='5'"]


async def test_ar_tool_returns_none_when_neither_space_matches():
    from spire.mcp_server.tools.receivables_invoice_by_id import (
        get_receivables_invoice_by_id,
    )

    client = _FakeClient({})
    assert await get_receivables_invoice_by_id(client, "999999999") is None
    assert client.questions == [
        "TransactionNumber='999999999'",
        "CustomerTransactionId='999999999'",
    ]
