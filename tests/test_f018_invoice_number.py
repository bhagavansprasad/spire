"""F-018 - invoice_number is a first-class filter on search_invoices.

Reproducer:
    show details for invoice number LEE-01-1006-111

Pre-fix this refused with `missing_identifier — Invoice root has no supplier
reference` and a Solution that offered "give me the invoice number" while
no layer of the pipeline accepted one. The pod probe confirmed the resource
supports `q=InvoiceNumber='LEE-01-1006-111'` (totalResults=1).

Two unit tests cover the tool directly; end-to-end coverage lives in the
V1 run recorded in the fix file.
"""

import pytest

from spire.mcp_server.tools.invoices import search_invoices


class _FakeClient:
    def __init__(self, response):
        self._response = response
        self.calls = []

    async def get(self, path, params=None):
        self.calls.append(params or {})
        return self._response

    async def total_results(self, path, server_clause=None):
        return None


def _row(num, sid, sup="Lee Supplies"):
    return {
        "InvoiceId": sid,
        "InvoiceNumber": num,
        "InvoiceDate": "2016-10-17",
        "InvoiceAmount": 11138.34,
        "InvoiceCurrency": "USD",
        "Supplier": sup,
        "SupplierNumber": "1252",
        "PaidStatus": "Paid",
        "ApprovalStatus": "Approved",
        "PurchaseOrderNumber": None,
        "CreatedBy": "x", "CreationDate": "2016-10-17",
        "LastUpdatedBy": "x", "LastUpdateDate": "2016-10-17",
    }


@pytest.mark.asyncio
async def test_invoice_number_uses_server_clause():
    """The tool sends InvoiceNumber='...' as the server q= clause."""
    fake = _FakeClient({"items": [_row("LEE-01-1006-111", 489503)]})
    result = await search_invoices(fake, invoice_number="LEE-01-1006-111")
    assert fake.calls, "tool did not call the pod"
    params = fake.calls[0]
    assert params.get("q") == "InvoiceNumber='LEE-01-1006-111'", params
    assert len(result.items) == 1
    assert result.items[0]["InvoiceNumber"] == "LEE-01-1006-111"


@pytest.mark.asyncio
async def test_invoice_number_matches_client_side():
    """A wrong-number row that slipped the server clause is filtered out."""
    fake = _FakeClient({"items": [
        _row("LEE-01-1006-111", 489503),
        _row("LEE-01-9999-999", 999999),
    ]})
    result = await search_invoices(fake, invoice_number="LEE-01-1006-111")
    assert len(result.items) == 1
    assert result.items[0]["InvoiceNumber"] == "LEE-01-1006-111"


@pytest.mark.asyncio
async def test_no_invoice_number_uses_no_invoice_clause():
    """Passing only a supplier does not add an InvoiceNumber clause."""
    fake = _FakeClient({"items": [_row("X", 1)]})
    await search_invoices(fake, supplier_number="1252")
    q = fake.calls[0].get("q", "")
    assert "InvoiceNumber" not in q


# ---------------------------------------------------------------------
# _extract_invoice_number: the deterministic parser-side helper
# ---------------------------------------------------------------------

from spire.nl_parser.parser import _extract_invoice_number


def test_extract_invoice_number_accepts_number_word():
    assert _extract_invoice_number(
        "show details for invoice number LEE-01-1006-111"
    ) == "LEE-01-1006-111"


def test_extract_invoice_number_accepts_short_form():
    assert _extract_invoice_number(
        "invoice LEE-01-1006-111"
    ) == "LEE-01-1006-111"


def test_extract_invoice_number_accepts_numbered():
    assert _extract_invoice_number(
        "the invoice numbered PCS10027_0825"
    ) == "PCS10027_0825"


def test_extract_invoice_number_rejects_no_number():
    assert _extract_invoice_number("count of invoices") is None


def test_extract_invoice_number_rejects_bare_digit_only_token():
    """A pure-digit token without the "number" word is ambiguous with a
    PO number; the helper declines."""
    assert _extract_invoice_number("invoice 162034") is None


def test_extract_invoice_number_accepts_digit_with_number_word():
    assert _extract_invoice_number(
        "invoice number 162034"
    ) == "162034"


def test_extract_invoice_number_rejects_created_word():
    """A word-shaped token with no digit is not an invoice number."""
    assert _extract_invoice_number(
        "invoices created before 2015-01-01"
    ) is None


def test_extract_invoice_number_rejects_for_supplier():
    assert _extract_invoice_number(
        "invoices for Lee Supplies"
    ) is None
