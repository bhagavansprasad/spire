"""Integration tests for the AR invoice detail tools
(get_receivables_invoice_by_id and get_receivables_invoice_lines).

These hit the live pod, mirroring test_purchase_order_detail_tool.py, and
skip when personas.yaml is absent. CustomerTransactionId 300000248096352
(TransactionNumber 61765, ABC Corporation Americas, UK Business Unit, GBP
39,969) is a stable Complete AR invoice on the demo pod with one line
("Consultation").

Unlike the single-PO header path (which 404s for an unknown id), the AR
by-id tool queries the receivablesInvoices COLLECTION with
q=CustomerTransactionId=<id>, which returns an empty item set for an
unknown id — so the by-id unknown case asserts None via empty items, not a
404. The lines child path, by contrast, 404s for an unknown parent (like
the PO lines path), which the tool maps to an empty ToolResult.
"""

import pytest

from spire.config import PERSONAS_FILE, load_persona
from spire.fusion.client import FusionClient
from spire.mcp_server.tools.receivables_invoice_by_id import (
    get_receivables_invoice_by_id,
)
from spire.mcp_server.tools.receivables_invoice_lines import (
    get_receivables_invoice_lines,
)


pytestmark = pytest.mark.skipif(
    not PERSONAS_FILE.exists(),
    reason="personas.yaml not found — skipping integration tests",
)


# Known AR invoice on the demo pod: TransactionNumber 61765, ABC
# Corporation Americas, GBP 39,969, status Complete, one line.
KNOWN_CUSTOMER_TRANSACTION_ID = 300000248096352


@pytest.mark.asyncio
async def test_get_receivables_invoice_by_id_returns_known_invoice():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        inv = await get_receivables_invoice_by_id(
            client, customer_transaction_id=KNOWN_CUSTOMER_TRANSACTION_ID
        )
    assert inv is not None
    assert inv["CustomerTransactionId"] == KNOWN_CUSTOMER_TRANSACTION_ID
    assert inv["TransactionNumber"] == "61765"
    assert inv["BillToCustomerName"] == "ABC Corporation Americas"
    assert inv["InvoiceCurrencyCode"] == "GBP"
    # Both money fields are projected: EnteredAmount and the open balance.
    assert inv["EnteredAmount"] is not None
    assert inv["InvoiceBalanceAmount"] is not None


@pytest.mark.asyncio
async def test_get_receivables_invoice_by_id_returns_none_for_unknown_id():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        inv = await get_receivables_invoice_by_id(
            client, customer_transaction_id=999999999
        )
    # The collection query returns an empty item set (not a 404) for an
    # unknown id; the tool maps that to None rather than raising.
    assert inv is None


@pytest.mark.asyncio
async def test_get_receivables_invoice_lines_returns_lines():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await get_receivables_invoice_lines(
            client, customer_transaction_id=KNOWN_CUSTOMER_TRANSACTION_ID
        )
    assert len(result.items) == 1
    first = result.items[0]
    assert first["LineNumber"] == 1
    assert first["Description"] == "Consultation"
    # Oracle misspells this field as "TransacationBusinessCategory" (sic);
    # the tool must request it with the typo, so it resolves here.
    assert first["TransacationBusinessCategory"] == "Sales Transaction"


@pytest.mark.asyncio
async def test_get_receivables_invoice_lines_empty_for_unknown_id():
    persona = load_persona("default_dev")
    async with FusionClient(persona) as client:
        result = await get_receivables_invoice_lines(
            client, customer_transaction_id=999999999
        )
    # An unknown parent 404s on the child path; the tool maps that to an
    # empty ToolResult rather than raising.
    assert result.items == []
