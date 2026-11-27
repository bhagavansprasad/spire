"""F-077 — AP invoice lines: the tool, the KG entity, and the wiring.

The defect: `Show all invoice lines for invoice ERS-53004-755598` was
REFUSED with "AP invoice lines are not supported as the InvoiceLine entity
is not available in the API schema." That sentence was false —
`/invoices/{id}/child/invoiceLines` returns every field the prompt names.
The refusal happened because no AP line entity existed in the KG, and the
prompt was additionally misrouted to `receivables`.

This file pins the entity-end wiring. The ROUTING half is deliberately not
asserted here: `invoice line(s)` still resolves to the AR entity (F-041),
and disambiguating an AP number from an AR number needs a lookup the
synchronous router does not have. See docs/fixes/FIX_PLAN.md F-077.

Verified live on dev49 (2026-11-27), invoice 1601397:

    SQL  184 rows   REST 184 rows
    only-in-SQL 0   only-in-REST 0
    field mismatches 0 across LineNumber, Description, Quantity,
    UnitPrice, LineAmount, LineType
"""

from __future__ import annotations

import ast
from pathlib import Path

import httpx
import pytest

from spire.kg.sql_overlay import OVERLAY
from spire.planner.models import Step
from spire.planner.registries import _TOOL_PRIMARY_ARG
from spire.rendering.sql_emitter import emit_sql

REPO = Path(__file__).resolve().parents[1]
SEED = REPO / "scripts" / "sql" / "kg_schema.sql"
CONTEXT = REPO / "src" / "spire" / "nl_parser" / "context"
MANIFEST = CONTEXT / "order.manifest"
SERVER = REPO / "src" / "spire" / "mcp_server" / "server.py"

# The six fields the F-077 prompt asks for, in its own words, mapped to the
# REST field names the child payload actually uses.
REQUESTED = {
    "line number": "LineNumber",
    "description": "Description",
    "quantity": "Quantity",
    "unit price": "UnitPrice",
    "amount": "LineAmount",
    "line type": "LineType",
}


def _line_sql(invoice_id: int = 1601397) -> str:
    step = Step(
        step_id=1,
        tool_name="get_invoice_lines",
        tool_args={"invoice_id": invoice_id},
        iterate_over=None,
        client_filters=(),
        output_name="out1",
        output_dedupe_by=None,
    )
    return emit_sql([step])[0]


# ── The tool ──────────────────────────────────────────────────────────


def test_tool_projects_every_field_the_prompt_asks_for():
    """The six named fields are all in the tool's projection."""
    from spire.mcp_server.tools.invoice_lines import _PROJECTED_FIELDS

    for rest_name in REQUESTED.values():
        assert rest_name in _PROJECTED_FIELDS, (
            f"{rest_name} is requested by the F-077 prompt but the tool "
            "does not project it"
        )


def test_tool_uses_the_invoiceLines_child_segment():
    """`child/lines` 404s on this pod; `child/invoiceLines` is the only
    correct segment."""
    from spire.mcp_server.tools.invoice_lines import (
        INVOICE_LINES_PATH_TEMPLATE,
    )

    assert "/child/invoiceLines" in INVOICE_LINES_PATH_TEMPLATE
    assert "/child/lines" not in INVOICE_LINES_PATH_TEMPLATE
    assert "{invoice_id}" in INVOICE_LINES_PATH_TEMPLATE


class _FakeClient:
    """Returns canned items, recording the path and params it was asked."""

    def __init__(self, items=None, status_code: int = 200):
        self._items = items or []
        self._status_code = status_code
        self.calls: list[tuple[str, dict]] = []

    async def get(self, path, params=None):
        self.calls.append((path, params or {}))
        if self._status_code != 200:
            raise httpx.HTTPStatusError(
                "boom",
                request=httpx.Request("GET", "https://x"),
                response=httpx.Response(self._status_code),
            )
        return {"items": self._items}


@pytest.mark.asyncio
async def test_tool_returns_projected_items():
    from spire.mcp_server.tools.invoice_lines import get_invoice_lines

    client = _FakeClient([
        {**{v: i for v in REQUESTED.values()}, "UOM": "Each", "Ignored": 1}
        for i in (1, 2)
    ])
    result = await get_invoice_lines(client, invoice_id=1601397, limit=50)

    assert len(result.items) == 2
    assert "Ignored" not in result.items[0], "projection must drop extras"
    assert result.limit_applied == 50
    path, params = client.calls[0]
    assert path.endswith("/invoices/1601397/child/invoiceLines")
    assert params["onlyData"] == "true"


@pytest.mark.asyncio
async def test_tool_returns_empty_on_404():
    """An unknown InvoiceId 404s on the child path — that is 'no lines'."""
    from spire.mcp_server.tools.invoice_lines import get_invoice_lines

    result = await get_invoice_lines(
        _FakeClient(status_code=404), invoice_id=999999999
    )

    assert result.items == []
    assert result.total_available == 0


@pytest.mark.asyncio
async def test_tool_reraises_non_404_errors():
    from spire.mcp_server.tools.invoice_lines import get_invoice_lines

    with pytest.raises(httpx.HTTPStatusError):
        await get_invoice_lines(_FakeClient(status_code=500), invoice_id=1)


# ── The SQL overlay ───────────────────────────────────────────────────


def test_overlay_declares_the_entity():
    spec = OVERLAY.entities["InvoiceLine"]
    assert spec.fusion_table == "AP_INVOICE_LINES_ALL"
    assert spec.pk_column == "LINE_NUMBER", (
        "AP_INVOICE_LINES_ALL has no INVOICE_LINE_ID on this pod; the pk "
        "role has to sit on LINE_NUMBER"
    )


def test_overlay_maps_the_tool_to_the_entity():
    assert OVERLAY.tool_to_entity["get_invoice_lines"] == "InvoiceLine"


def test_overlay_declares_the_id_filter():
    spec = OVERLAY.filters[("get_invoice_lines", "invoice_id")]
    assert spec.predicate_template == "{alias}.INVOICE_ID = {value}"
    assert spec.assumption in OVERLAY.assumptions


def test_emitted_sql_targets_the_ap_line_table():
    sql = _line_sql()
    assert "FROM AP_INVOICE_LINES_ALL L" in sql
    assert "L.INVOICE_ID = '1601397'" in sql


def test_emitted_sql_projects_the_six_requested_columns():
    sql = _line_sql()
    for column in (
        "L.LINE_NUMBER",
        "L.DESCRIPTION",
        "L.QUANTITY_INVOICED",
        "L.UNIT_PRICE",
        "L.AMOUNT",
        "L.LINE_TYPE_LOOKUP_CODE",
    ):
        assert column in sql, f"{column} missing from the emitted projection"


def test_emitted_sql_never_touches_the_ar_tables():
    """The whole point of F-077: this must not drift onto the AR path."""
    sql = _line_sql()
    assert "RA_CUSTOMER_TRX_LINES_ALL" not in sql
    assert "CUSTOMER_TRX_ID" not in sql


# ── Planner wiring ────────────────────────────────────────────────────


def test_registries_know_the_primary_arg():
    assert _TOOL_PRIMARY_ARG["get_invoice_lines"] == "invoice_id"


def test_server_registers_the_tool():
    source = SERVER.read_text()
    assert "from spire.mcp_server.tools.invoice_lines import" in source
    assert "async def get_invoice_lines(" in source


# ── The KG seed ───────────────────────────────────────────────────────


def test_seed_declares_the_entity_in_payables():
    text = SEED.read_text()
    assert "'InvoiceLine', 'LineNumber', 'LineNumber'," in text
    assert "/invoices/{InvoiceId}/child/invoiceLines" in text
    # The entity's module is the last positional before the closing paren.
    assert "'payables'\n);" in text


def test_seed_declares_the_sql_carrier():
    text = SEED.read_text()
    assert (
        "('InvoiceLine', 'AP_INVOICE_LINES_ALL', 'LINE_NUMBER')" in text
    )


def test_seed_binds_the_six_requested_fields_to_populated_columns():
    text = SEED.read_text()
    expected = {
        "LineNumber": "LINE_NUMBER",
        "Description": "DESCRIPTION",
        "Quantity": "QUANTITY_INVOICED",
        "UnitPrice": "UNIT_PRICE",
        "LineAmount": "AMOUNT",
        "LineType": "LINE_TYPE_LOOKUP_CODE",
    }
    for field, column in expected.items():
        assert (
            f"'InvoiceLine', '{field}', 'AP_INVOICE_LINES_ALL', "
            f"'{column}'" in text
        ), f"{field} is not bound to {column}"


def test_seed_declares_the_edge_and_its_tool():
    text = SEED.read_text()
    assert "'HAS_AP_LINE', 'Invoice', 'InvoiceLine'" in text
    assert "'HAS_AP_LINE',\n  'get_invoice_lines'," in text


def test_edge_name_does_not_collide_with_the_po_edge():
    """edge_name is the primary key, and PurchaseOrder already owns
    'HAS_LINE'."""
    text = SEED.read_text()
    assert "'HAS_LINE', 'Invoice'" not in text


def test_seed_adds_only_unambiguous_ap_synonyms():
    """Plain 'invoice line(s)' stays with the AR entity (F-041). Seeding it
    for the AP entity too would make the classifier menu ambiguous, which
    is a routing decision, not a seed decision."""
    text = SEED.read_text()
    assert "'entity_synonym', 'AP invoice lines',      'InvoiceLine'" in text
    assert (
        "'entity_synonym', 'invoice lines',         'ReceivablesInvoiceLine'"
        in text
    )


# ── Parser context ────────────────────────────────────────────────────


def test_manifest_includes_the_block():
    lines = [ln.strip() for ln in MANIFEST.read_text().splitlines() if ln.strip()]
    assert "payables/b_invoice_lines.sysprompt" in lines


def test_manifest_block_exists_and_teaches_the_ap_phrasing():
    block = CONTEXT / "payables" / "b_invoice_lines.sysprompt"
    assert block.is_file()
    body = block.read_text()
    assert "invoice lines for invoice X" in body
    assert "InvoiceLine" in body
    assert "invoice_number" in body


def test_manifest_block_parses_as_plain_text_not_code():
    """A sysprompt block is prose; guard against an accidental .py paste."""
    block = CONTEXT / "payables" / "b_invoice_lines.sysprompt"
    with pytest.raises(SyntaxError):
        ast.parse(block.read_text())
