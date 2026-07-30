#!/usr/bin/env python3
"""
Shared display formatters for the Spire pipeline runners.

Extracted from the former run_plan.py so that run_graph.py and
run_prompt_set.py have one home for output formatting and no dependency on
run_plan.py (which is deprecated and slated for deletion).

Everything here is presentation only: it turns the pipeline's Intent,
Plan, outputs dict and synthesized response into printable text. No
pipeline logic lives here.

_format_projected_table is the column-output formatter: when an intent
carries `fields`, the runner prints an aligned table of exactly those
columns instead of the typed per-entity block. Nested addresses flatten to
an Address column. See run_graph.py / run_prompt_set.py for the branch that
chooses it.
"""

from __future__ import annotations

from typing import Any

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
    ReceiptMethodDistributionResponse,
    POLifecycleResponse,
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


def _format_synthesized(response: Any, summary_only: bool = False) -> str:
    """Render a synthesized response.

    summary_only=True prints the summary paragraph and the truncation
    notes, and STOPS — no typed record block.

    That mode exists for column queries. When the user names the
    columns they want, _format_projected_table prints exactly those, and
    this module's own docstring says the table goes "instead of the
    typed per-entity block". Printing both repeats every value twice.

    It was harmless-looking until the address case: "List active
    suppliers with supplier name, supplier number, and address" emits 25
    suppliers with up to 25 addresses EACH — about 200 lines of
    "address: ..." — and then the same data again, one line per
    supplier, in the table below. The rule was previously honoured by
    accident: synthesis overran on that query and failed, so only the
    table printed. Once synthesis started succeeding, nothing enforced
    it.
    """
    if response is None:
        return "Synthesized response: (none)"
    # If it's a plain dict, just print it.
    if isinstance(response, dict):
        return f"Synthesized response:\n{response}"

    if summary_only:
        summary = getattr(response, "summary", None)
        if summary is None:
            # Not a summary-bearing shape; fall through to the full
            # render rather than printing nothing.
            return _format_synthesized(response)
        out = ["Answer:", summary]
        notes = getattr(response, "truncation_notes", None)
        if notes:
            out.append("\nTruncation:")
            out.extend(f"  - {n}" for n in notes)
        return "\n".join(out)

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
                    # Tax lines nest under each invoice line. Without this
                    # loop the synthesizer populates them correctly and the
                    # display silently drops them: the tax-line prompt
                    # printed "lines: 4" and no tax at all, while the
                    # executor had fetched 8 tax rows and the narration
                    # described them. `ln` rather than `line` — `lines` is
                    # the output buffer being appended to.
                    for ln in inv.lines:
                        if ln.tax_lines:
                            lines.append(
                                f"      line {ln.line_number} — "
                                f"{len(ln.tax_lines)} tax line(s):"
                            )
                            for tx in ln.tax_lines:
                                lines.append(
                                    f"        {tx.tax} {tx.tax_rate}% — "
                                    f"tax {tx.tax_amount} on {tx.taxable_amount}"
                                )
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
            # Exactly one of total_credit / total_credit_note is set. A
            # null total means the memos span several currencies: show
            # the reason, never "None" and never a number.
            if response.total_credit is None:
                lines.append(
                    "\n"
                    + (
                        response.total_credit_note
                        or "Total not shown: these memos span several "
                        "currencies."
                    )
                )
            else:
                lines.append(
                    f"\nTotal credit value: {response.total_credit}"
                )
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

    if isinstance(response, ReceiptMethodDistributionResponse):
        lines.append(response.summary)
        lines.append(
            f"\nTotal receipts: {response.total_receipts}, total amount: {response.total_amount:,.2f}"
        )
        if response.methods:
            lines.append("\nDistribution by method:")
            for row in response.methods:
                lines.append(
                    f"  - {row.receipt_method}: {row.receipt_count} receipts, "
                    f"total {row.total_amount:,.2f}"
                )
        else:
            lines.append("\nNo receipts found.")
        if response.truncation_notes:
            lines.append("\nTruncation:")
            lines.extend(f"  - {note}" for note in response.truncation_notes)
        return "\n".join(lines)

    # Fallback for unrecognized shape.
    # --- POLifecycleResponse (Module 5) ---
    #
    # A verdict first, then the evidence. Catalog prompt A.4 asks three
    # yes/no questions in one sentence; a reader should get all three
    # answers before any table.
    #
    # THE PAID ROW IS WHY THIS RENDERER IS CAREFUL. When the paid leg is
    # unknown its amount is None, and an empty cell in a money column
    # reads as zero — which is the assertion the whole tri-state exists
    # to prevent. Null amounts print as an em dash with the reason
    # alongside, never as blank and never as 0.00.
    if isinstance(response, POLifecycleResponse):
        def _verdict(leg) -> str:
            if leg.complete is None:
                return "cannot be determined"
            return "yes" if leg.complete else "no"

        def _money(value) -> str:
            return "—" if value is None else f"{value:,.2f}"

        by_name = {leg.name: leg for leg in response.legs}
        head = f"PO {response.order_number}"
        if response.supplier:
            head += f" — {response.supplier}"
        lines.append(head)

        # Phase 0 defect 2: no legs means the PO was not found. Print the
        # header, the summary and whatever the tool said — and nothing
        # else. Everything below asserts something about an order that
        # does not exist: the verdict row reads "cannot be determined",
        # implying the PO exists and is unknowable, and the stage line
        # prints an empty owner and an empty risk as though they were
        # values. Emptiness is the signal, not the stage string — a found
        # record always carries all four legs.
        # The tool's note stays on the response for API-02 consumers, but
        # printing it here just repeats the summary sentence to a human —
        # and an unlabelled bullet under a sentence reads as a second,
        # separate finding rather than the same one twice.
        if not response.legs:
            lines.append("")
            lines.append(response.summary)
            return "\n".join(lines)

        verdicts = []
        for name in ("Received", "Invoiced", "Paid"):
            leg = by_name.get(name)
            if leg is not None:
                verdicts.append(f"{name}: {_verdict(leg)}")
        if verdicts:
            lines.append("  " + " · ".join(verdicts))
        lines.append(
            f"  Stage: {response.lifecycle_stage}"
            f"  ·  Owner: {response.responsible_team}"
            f"  ·  Risk: {response.risk}"
        )

        lines.append("")
        lines.append(response.summary)

        currency = f" ({response.currency})" if response.currency else ""
        lines.append(f"\nAmounts{currency}:")
        lines.append(f"  {'Leg':<10} {'Amount':>12} {'Remaining':>12}")
        for leg in response.legs:
            lines.append(
                f"  {leg.name:<10} {_money(leg.amount):>12} "
                f"{_money(leg.remaining):>12}"
            )
        for leg in response.legs:
            if leg.note:
                lines.append(f"    {leg.name}: {leg.note}")

        if response.risk_reasons:
            lines.append(f"\nRisk ({response.risk}):")
            lines.extend(f"  - {reason}" for reason in response.risk_reasons)

        if response.recommended_action:
            lines.append(f"\nRecommended action:\n  {response.recommended_action}")

        if response.setup_notes:
            lines.append("\nSupplier setup:")
            lines.extend(f"  - {note}" for note in response.setup_notes)

        # Only when a line is actually short: on a fully received PO the
        # table repeats what the amounts block already said.
        short_lines = [
            row for row in response.schedules
            if (row.outstanding_amount or 0) > 0
        ]
        if short_lines:
            lines.append("\nOutstanding lines:")
            lines.append(
                f"  {'Line':>5} {'Status':<9} {'Amount':>11} "
                f"{'Received':>11} {'Outstanding':>12}"
            )
            for row in short_lines:
                lines.append(
                    f"  {str(row.line_number or '-'):>5} "
                    f"{str(row.status or '-'):<9} "
                    f"{_money(row.amount):>11} "
                    f"{_money(row.received_amount):>11} "
                    f"{_money(row.outstanding_amount):>12}"
                )

        if response.exceptions:
            lines.append("\nUnresolved:")
            lines.extend(f"  - {item}" for item in response.exceptions)

        if response.truncation_notes:
            lines.append("\nTruncation:")
            lines.extend(f"  - {note}" for note in response.truncation_notes)

        return "\n".join(lines)
    
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
        elif hasattr(response, "methods"):
            count = len(response.methods)
        else:
            count = len(final_bucket)
        lines.append(f"  Final raw output:     {len(final_bucket)} record(s) under '{list(outputs.keys())[-1] if outputs else '?'}'")
        lines.append(f"  Synthesized answer:   {count} record(s)")
    else:
        lines.append(f"  Final raw output:     {len(final_bucket)} record(s)")
    return "\n".join(lines)


def _format_projected_table(outputs: dict[str, list[dict]], fields: list[str]) -> str:
    """Print the final output bucket as a table of exactly the requested
    columns, in the order named.

    Used when the intent carries ``fields`` — an explicit column request.
    Reads the projected rows the executor already produced and prints those
    columns directly, rather than routing through the typed synthesizer
    response (whose fixed attributes cannot carry arbitrary requested
    columns). A missing key on a row prints as an em dash so an absent value
    is visibly distinct from an empty string.

    Address flattening (self-gating): when the rows carry a nested
    ``addresses`` list (from include_addresses=True), each supplier's first
    address is flattened to a one-line string under an ``Address`` column,
    and ``Address`` is appended to the printed columns. This fires only when
    address data is actually present, so it never misfires and needs no
    parser change. Keys match the tool's flattened shape (FormattedAddress,
    City, State, Country).
    """
    if not outputs:
        return "Answer:\nNo records found."

    bucket_name = list(outputs.keys())[-1]
    rows = outputs[bucket_name]

    # Self-gating address flatten: only if some row carries an addresses list.
    cols = list(fields)
    has_addresses = any(
        isinstance(r, dict) and r.get("addresses") for r in rows
    )
    if has_addresses:
        rows = [dict(r) if isinstance(r, dict) else r for r in rows]
        for r in rows:
            if not isinstance(r, dict):
                continue
            addrs = r.get("addresses") or []
            if addrs:
                a = addrs[0]
                r["Address"] = (
                    a.get("FormattedAddress")
                    or ", ".join(
                        str(a[k]) for k in ("City", "State", "Country")
                        if a.get(k)
                    )
                    or None
                )
            else:
                r["Address"] = None
        if "Address" not in cols:
            cols.append("Address")

    lines = [
        "Answer:",
        f"\n{bucket_name} ({len(rows)} record(s)) — "
        f"columns: {', '.join(cols)}\n",
    ]

    if not rows:
        lines.append("  (no rows)")
        return "\n".join(lines)

    widths = {}
    for f in cols:
        cell_lens = [
            len(str(r.get(f))) if isinstance(r, dict) and r.get(f) is not None else 1
            for r in rows
        ]
        widths[f] = max([len(f)] + cell_lens)

    header = "  " + " | ".join(f.ljust(widths[f]) for f in cols)
    rule = "  " + "-+-".join("-" * widths[f] for f in cols)
    lines.append(header)
    lines.append(rule)
    for r in rows:
        cells = []
        for f in cols:
            v = r.get(f) if isinstance(r, dict) else None
            cells.append(("—" if v is None else str(v)).ljust(widths[f]))
        lines.append("  " + " | ".join(cells))
    return "\n".join(lines)
