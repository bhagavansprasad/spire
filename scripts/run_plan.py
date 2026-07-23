#!/usr/bin/env python3
"""
Run the Design 3 pipeline imperatively.

This is the non‑graph version of the same pipeline as run_graph.py.
It expects the MCP server to be running on localhost:3333.

Usage:
    python scripts/run_plan.py --prompt "Show me suppliers in US"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from fastmcp import Client

from spire.config import reset_usage, usage_report
from spire.executor.executor import execute_plan
from spire.nl_parser.capability import capability_message
from spire.nl_parser.parser import parse
from spire.nl_parser.vocabulary import load_kg_menu
from spire.planner.planner import generate_plan
from spire.synthesizer.synthesizer import (
    SynthesizedResponse,
    SupplierResponse,
    InvoiceResponse,
    PurchaseOrderResponse,
    ReceivablesInvoiceResponse,
    CustomerAccountResponse,
    AddressResponse,
    CreditMemoListResponse,
    CountResponse,
    ComparisonResponse,
    SupplierSpendRankingResponse,
    SupplierPOValueRankingResponse,
    POStatusBreakdownResponse,
    OpenPOSummaryResponse,
    StandardReceiptResponse,
    ExposureRankingResponse,
    synthesize_response,
)

MCP_SERVER_URL = "http://127.0.0.1:3333/mcp"


def _format_intent(intent) -> str:
    lines = ["Intent:"]
    lines.append(f"  target_entity: {intent.target_entity}")
    if intent.filters:
        lines.append("  filters:")
        for f in intent.filters:
            lines.append(f"    - {f}")
    if intent.include:
        lines.append(f"  include: {intent.include}")
    if intent.fields:
        lines.append(f"  fields: {intent.fields}")
    if intent.aggregate:
        lines.append(f"  aggregate: {intent.aggregate}")
    if intent.compare:
        lines.append(f"  compare: {intent.compare}")
    if intent.count_only:
        lines.append("  count_only: True")
    if intent.open_only:
        lines.append("  open_only: True")
    if intent.invoice_limit is not None:
        lines.append(f"  invoice_limit: {intent.invoice_limit}")
    if intent.balance_only:
        lines.append("  balance_only: True")
    return "\n".join(lines)


def _format_plan(plan) -> str:
    lines = ["Plan:"]
    for step in plan:
        lines.append(f"  Step {step.step_id}: {step.tool_name}")
        lines.append(f"    tool_args:      {step.tool_args}")
        it = step.iterate_over
        if it is None:
            lines.append("    iterate_over:   (none — runs once)")
        else:
            lines.append(f"    iterate_over:   {it}")
        if step.client_filters:
            lines.append(f"    client_filters: {step.client_filters}")
        else:
            lines.append("    client_filters: (none)")
        lines.append(f"    dedupe_by:      {step.output_dedupe_by or '(none)'}")
        lines.append(f"    output_name:    {step.output_name}")
        if step.filter_source_when_empty:
            lines.append("    filter_source_when_empty: True")
        if step.filter_source_when_nonempty:
            lines.append("    filter_source_when_nonempty: True")
        if step.stamp_parent_key:
            lines.append("    stamp_parent_key: True")
    return "\n".join(lines)


def _format_outputs(outputs: dict[str, list[dict]]) -> str:
    if not outputs:
        return "Outputs: (none)"
    lines = ["Outputs:"]
    for name, items in outputs.items():
        lines.append(f"  {name}: {len(items)} record(s)")
        for i, item in enumerate(items[:5], 1):
            # Show a compact representation: first few fields.
            preview = {k: v for k, v in list(item.items())[:6]}
            lines.append(f"    [{i}] {preview}")
        if len(items) > 5:
            lines.append(f"    ... ({len(items) - 5} more)")
    return "\n".join(lines)


def _format_synthesized(response: Any) -> str:
    if response is None:
        return "Synthesized response: (none)"
    # If it's a plain dict, just print it.
    if isinstance(response, dict):
        return f"Synthesized response:\n{response}"

    lines = ["Answer:"]
    if isinstance(response, SynthesizedResponse) or isinstance(response, SupplierResponse):
        lines.append(response.summary)
        if response.suppliers:
            lines.append("\nSuppliers:")
            for s in response.suppliers:
                lines.append(f"  - {s.supplier_name} (SupplierId={s.supplier_id}, SupplierNumber={s.supplier_number})")
                if s.open_po_count is not None:
                    lines.append(f"    open POs: {s.open_po_count}")
                if s.buyers:
                    buyers = ", ".join(b.display_name for b in s.buyers)
                    lines.append(f"    buyers: {buyers}")
                if s.addresses:
                    for a in s.addresses:
                        addr = a.formatted_address or f"{a.city}, {a.country}"
                        lines.append(f"    address: {addr}")
                if s.contacts:
                    for c in s.contacts:
                        lines.append(f"    contact: {c.contact_name} ({c.email or 'no email'})")
        else:
            lines.append("No suppliers found.")
        if response.truncation_notes:
            lines.append("\nTruncation:")
            lines.extend(f"  - {note}" for note in response.truncation_notes)
        return "\n".join(lines)

    if isinstance(response, InvoiceResponse):
        lines.append(response.summary)
        if response.invoices:
            lines.append("\nInvoices:")
            for inv in response.invoices:
                lines.append(
                    f"  - {inv.invoice_number} ({inv.invoice_id}) — "
                    f"{inv.invoice_amount} {inv.invoice_currency} on {inv.invoice_date}; "
                    f"supplier: {inv.supplier_name}"
                )
        else:
            lines.append("No invoices found.")
        if response.truncation_notes:
            lines.append("\nTruncation:")
            lines.extend(f"  - {note}" for note in response.truncation_notes)
        return "\n".join(lines)

    if isinstance(response, PurchaseOrderResponse):
        lines.append(response.summary)
        if response.purchase_orders:
            lines.append("\nPurchase Orders:")
            for po in response.purchase_orders:
                lines.append(
                    f"  - {po.order_number} (POHeaderId={po.po_header_id}) — "
                    f"{po.status}; supplier: {po.supplier_name}"
                )
                if po.buyer:
                    lines.append(f"    buyer: {po.buyer.display_name}")
                if po.lines:
                    lines.append(f"    lines: {len(po.lines)}")
                if po.schedules:
                    lines.append(f"    schedules: {len(po.schedules)}")
                if po.distributions:
                    lines.append(f"    distributions: {len(po.distributions)}")
        else:
            lines.append("No purchase orders found.")
        if response.truncation_notes:
            lines.append("\nTruncation:")
            lines.extend(f"  - {note}" for note in response.truncation_notes)
        return "\n".join(lines)

    if isinstance(response, ReceivablesInvoiceResponse):
        lines.append(response.summary)
        if response.receivables_invoices:
            lines.append("\nAR Invoices:")
            for inv in response.receivables_invoices:
                lines.append(
                    f"  - {inv.transaction_number} (CustomerTransactionId={inv.customer_transaction_id}) — "
                    f"{inv.amount} {inv.currency} on {inv.transaction_date}; "
                    f"customer: {inv.bill_to_customer_name}; status: {inv.status}"
                )
                if inv.lines:
                    lines.append(f"    lines: {len(inv.lines)}")
                if inv.dff:
                    lines.append(f"    DFF context: {inv.dff.context}")
        else:
            lines.append("No AR invoices found.")
        if response.truncation_notes:
            lines.append("\nTruncation:")
            lines.extend(f"  - {note}" for note in response.truncation_notes)
        return "\n".join(lines)

    if isinstance(response, CustomerAccountResponse):
        lines.append(response.summary)
        if response.customer_accounts:
            lines.append("\nCustomer Accounts:")
            for acct in response.customer_accounts:
                lines.append(
                    f"  - {acct.customer_name} (AccountId={acct.account_id}, AccountNumber={acct.account_number}); "
                    f"open receivables {acct.open_receivables}, transactions due {acct.transactions_due}"
                )
                if acct.transactions:
                    lines.append(f"    transactions: {len(acct.transactions)}")
                if acct.credit_memos:
                    lines.append(f"    credit memos: {len(acct.credit_memos)}")
                if acct.receipts:
                    lines.append(f"    receipts: {len(acct.receipts)}")
                if hasattr(acct, "applications") and acct.applications:
                    lines.append(f"    applications: {len(acct.applications)}")
        else:
            lines.append("No customer accounts found.")
        if response.truncation_notes:
            lines.append("\nTruncation:")
            lines.extend(f"  - {note}" for note in response.truncation_notes)
        return "\n".join(lines)

    if isinstance(response, AddressResponse):
        lines.append(response.summary)
        if response.addresses:
            lines.append("\nAddresses:")
            for a in response.addresses:
                addr = a.formatted_address or f"{a.city}, {a.country}"
                lines.append(
                    f"  - {addr} (AddressId={a.address_id}) — supplier: {a.supplier_name} ({a.supplier_number})"
                )
        else:
            lines.append("No addresses found.")
        if response.truncation_notes:
            lines.append("\nTruncation:")
            lines.extend(f"  - {note}" for note in response.truncation_notes)
        return "\n".join(lines)

    if isinstance(response, CreditMemoListResponse):
        lines.append(response.summary)
        if response.credit_memos:
            lines.append("\nCredit Memos (newest first):")
            for cm in response.credit_memos:
                lines.append(
                    f"  - {cm.transaction_number} (CustomerTransactionId={cm.customer_transaction_id}) — "
                    f"{cm.entered_amount} {cm.currency} on {cm.transaction_date}; "
                    f"customer: {cm.customer_name}; status: {cm.status}"
                )
            lines.append(f"\nTotal credit value: {response.total_credit}")
        else:
            lines.append("No credit memos found.")
        if response.truncation_notes:
            lines.append("\nTruncation:")
            lines.extend(f"  - {note}" for note in response.truncation_notes)
        return "\n".join(lines)

    if isinstance(response, CountResponse):
        lines.append(response.summary)
        if not response.count_is_exact:
            lines.append(f"(count is a lower bound; true total may be higher)")
        return "\n".join(lines)

    if isinstance(response, ComparisonResponse):
        lines.append(response.summary)
        if response.truncation_notes:
            lines.append("\nTruncation:")
            lines.extend(f"  - {note}" for note in response.truncation_notes)
        return "\n".join(lines)

    if isinstance(response, SupplierSpendRankingResponse):
        lines.append(response.summary)
        if response.suppliers:
            lines.append("\nTop suppliers by spend:")
            for i, row in enumerate(response.suppliers, 1):
                lines.append(
                    f"  {i}. {row.supplier_name} ({row.supplier_number}) — "
                    f"${row.total_spend:,.2f} across {row.invoice_count} invoices"
                )
        else:
            lines.append("No suppliers found.")
        if response.truncation_notes:
            lines.append("\nTruncation:")
            lines.extend(f"  - {note}" for note in response.truncation_notes)
        return "\n".join(lines)

    if isinstance(response, SupplierPOValueRankingResponse):
        lines.append(response.summary)
        if response.suppliers:
            lines.append("\nTop suppliers by PO value:")
            for i, row in enumerate(response.suppliers, 1):
                lines.append(
                    f"  {i}. {row.supplier_name} (SupplierId={row.supplier_id}) — "
                    f"${row.total_ordered:,.2f} across {row.po_count} POs"
                )
        else:
            lines.append("No suppliers found.")
        if response.truncation_notes:
            lines.append("\nTruncation:")
            lines.extend(f"  - {note}" for note in response.truncation_notes)
        return "\n".join(lines)

    if isinstance(response, POStatusBreakdownResponse):
        lines.append(response.summary)
        lines.append(f"\nTotal POs: {response.total_pos}, total value: {response.total_ordered:,.2f}")
        if response.statuses:
            lines.append("\nBreakdown by status:")
            for row in response.statuses:
                lines.append(
                    f"  - {row.status}: {row.po_count} POs, total value {row.total_ordered:,.2f}"
                )
        if response.truncation_notes:
            lines.append("\nTruncation:")
            lines.extend(f"  - {note}" for note in response.truncation_notes)
        return "\n".join(lines)

    if isinstance(response, OpenPOSummaryResponse):
        lines.append(response.summary)
        lines.append(
            f"\nOpen PO count: {response.po_count}, total ordered: {response.total_ordered:,.2f}, "
            f"suppliers: {response.supplier_count}"
        )
        if response.truncation_notes:
            lines.append("\nTruncation:")
            lines.extend(f"  - {note}" for note in response.truncation_notes)
        return "\n".join(lines)

    # --- StandardReceiptResponse ---
    if isinstance(response, StandardReceiptResponse):
        lines.append(response.summary)
        receipts = getattr(response, 'standard_receipts', [])
        if receipts:
            lines.append("\nReceipts:")
            for r in receipts:
                lines.append(
                    f"  - {r.receipt_number} ({r.standard_receipt_id}) — "
                    f"{r.amount} {r.currency} on {r.receipt_date}; "
                    f"{r.receipt_method}; site: {r.customer_site or 'N/A'}; "
                    f"bank: {r.remittance_bank_name or 'N/A'}"
                )
        else:
            lines.append("No receipts found.")
        if response.truncation_notes:
            lines.append("\nTruncation:")
            lines.extend(f"  - {note}" for note in response.truncation_notes)
        return "\n".join(lines)

    # --- ExposureRankingResponse ---
    if isinstance(response, ExposureRankingResponse):
        lines.append(response.summary)
        if response.accounts:
            lines.append("\nTop accounts by outstanding exposure:")
            for i, row in enumerate(response.accounts, 1):
                lines.append(
                    f"  {i}. {row.customer_name} (Account {row.account_number}) — "
                    f"open receivables: {row.open_receivables:,.2f}"
                )
        else:
            lines.append("No accounts found.")
        if response.truncation_notes:
            lines.append("\nTruncation:")
            lines.extend(f"  - {note}" for note in response.truncation_notes)
        return "\n".join(lines)

    # Fallback for unrecognized shape.
    return f"(Unrecognized response shape.)\n{response}"


def _format_summary(plan, outputs, response) -> str:
    lines = ["Summary:"]
    lines.append(f"  Steps planned:        {len(plan)}")
    total_records = sum(len(v) for v in outputs.values()) if outputs else 0
    lines.append(f"  Records returned:     {total_records} (across all steps)")
    # Count final output records (the last bucket).
    final_bucket = list(outputs.values())[-1] if outputs else []
    if response:
        # Try to count structured records.
        if hasattr(response, "suppliers"):
            count = len(response.suppliers)
        elif hasattr(response, "invoices"):
            count = len(response.invoices)
        elif hasattr(response, "purchase_orders"):
            count = len(response.purchase_orders)
        elif hasattr(response, "receivables_invoices"):
            count = len(response.receivables_invoices)
        elif hasattr(response, "customer_accounts"):
            count = len(response.customer_accounts)
        elif hasattr(response, "addresses"):
            count = len(response.addresses)
        elif hasattr(response, "credit_memos"):
            count = len(response.credit_memos)
        elif hasattr(response, "standard_receipts"):
            count = len(response.standard_receipts)
        elif hasattr(response, "accounts"):
            count = len(response.accounts)
        else:
            count = len(final_bucket)
        lines.append(f"  Final raw output:     {len(final_bucket)} record(s) under '{list(outputs.keys())[-1] if outputs else '?'}'")
        lines.append(f"  Synthesized answer:   {count} record(s)")
    else:
        lines.append(f"  Final raw output:     {len(final_bucket)} record(s)")
    return "\n".join(lines)


async def _run(prompt: str) -> int:
    reset_usage()
    menu = load_kg_menu()

    # Parse.
    parse_result = parse(prompt, menu=menu)
    if parse_result.is_refusal:
        print(capability_message(parse_result.refusal, menu))
        print(f"  (refusal: {parse_result.refusal.flavor.value} — {parse_result.refusal.detail})")
        print()
        print(usage_report())
        return 4

    intent = parse_result.intent

    # Plan.
    plan = generate_plan(intent)

    # Execute.
    async with Client(MCP_SERVER_URL) as session:
        outputs, truncation_by_step = await execute_plan(plan, session)

    # Synthesize.
    response = synthesize_response(
        outputs,
        target_entity=intent.target_entity,
        truncation_by_step=truncation_by_step,
        count_only=intent.count_only,
    )

    # Print.
    print(_format_intent(intent))
    print()
    print(_format_plan(plan))
    print()
    print(_format_outputs(outputs))
    print()
    print(_format_synthesized(response))
    print()
    print(_format_summary(plan, outputs, response))
    print()
    print(usage_report())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Spire pipeline imperatively."
    )
    parser.add_argument("--prompt", required=True, help="Natural-language prompt.")
    args = parser.parse_args()
    return asyncio.run(_run(args.prompt))


if __name__ == "__main__":
    raise SystemExit(main())