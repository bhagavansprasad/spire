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


def _with_truncation(lines: list[str], response: Any) -> str:
    """Append the truncation block, if any, and join.

    Extracted 2026-08-02. This block appeared SIXTEEN times, byte for
    byte, once per response shape in ``_format_synthesized``:

        if response.truncation_notes:
            lines.append("\\nTruncation:")
            lines.extend(f"  - {note}" for note in response.truncation_notes)
        return "\\n".join(lines)

    Sixteen copies is sixteen chances to miss one when the format
    changes — and the output contract (OUT-02) changes exactly this
    shape. A missed copy would render one entity type differently from
    the other fifteen, which is a silent inconsistency: the answer still
    prints, so nothing fails, and only a reader comparing two entity
    types would notice.

    ``getattr`` rather than attribute access, so the one caller that
    reaches here without a typed response (the summary_only path) can
    use it too.

    This extraction changed no output. Verified by byte-diffing eight
    prompts — four of them carrying truncation notes — before and after.
    """
    notes = getattr(response, "truncation_notes", None)
    if notes:
        lines.append("\nTruncation:")
        lines.extend(f"  - {note}" for note in notes)
    return "\n".join(lines)


# Column names that hold QUANTITIES — numbers worth comparing down a
# column. The test was originally the other way round: right-align
# anything numeric, minus a list of id-ish names. That list was
# open-ended and grew wrong immediately. "Transaction" carries no id
# marker, so a transaction NUMBER right-aligned as though it were an
# amount, while "AccountNumber" did not — the same kind of value
# rendered two ways depending on whether its name happened to contain a
# marker word.
#
# Inverted, the list is short and closed: the things that are genuinely
# quantities are amounts, totals, counts and ordinals, and that set does
# not really grow. It also fails in the safe direction. An unrecognised
# numeric column stays left-aligned, which is the old behaviour and
# never looks wrong; a mis-right-aligned identifier looks like a number
# being compared to the ones above it.
#
# Matched as substrings, so Total Spend, Open Receivables, Tax Amount,
# invoice_count and Rate % are all covered.
# The last four are COUNTS whose names carry no quantity word — the
# predicted miss of an allowlist, seen on the first run: a ranking's
# "Invoices" column (261, 122, 78) and a PO's "Lines" (4) are numbers
# worth comparing and were left-aligned with the text.
#
# Added by hand rather than by inferring "integer means count", because
# an identifier is an integer too and that inference is how the previous
# version right-aligned transaction numbers. Curated and extended when a
# miss is SEEN is the honest description of this list; it is not
# expected to be complete.
_QUANTITY_MARKERS = (
    "amount", "total", "spend", "balance", "due", "value", "price",
    "qty", "quantity", "count", "rate", "ordered", "received",
    "invoiced", "paid", "receivables", "rank",
    "invoices", "lines", "pos", "schedules",
)


def _is_quantity(column: str, values: list[Any]) -> bool:
    """True when a column holds quantities worth right-aligning.

    Right-aligned numbers line up by magnitude, so a column of amounts
    can be read down at a glance — 165,428,563 above 143,551,790 above
    43,959,648 shows its own shape. Left-aligned they start at the same
    x and the reader parses each one.

    BOTH tests must pass: the NAME must look like a quantity, and every
    VALUE must actually be a number. The name alone would right-align an
    empty or textual column called "Total"; the values alone right-align
    every identifier in the system, which is the bug this replaced.
    """
    low = column.lower()
    if not any(m in low for m in _QUANTITY_MARKERS):
        return False
    present = [v for v in values if v not in (None, "")]
    if not present:
        return False
    for v in present:
        if isinstance(v, bool):
            return False
        if isinstance(v, (int, float)):
            continue
        try:
            float(str(v).replace(",", ""))
        except (TypeError, ValueError):
            return False
    return True


def _indent(lines: list[str], by: str = "  ") -> list[str]:
    """Indent a rendered block, so a nested table sits under its parent.

    Child records — a supplier's contacts, an invoice line's tax rows —
    are records too, and get the same table treatment as their parent.
    They are indented so the nesting is visible; without it a contacts
    table and a suppliers table sit at the same depth and read as two
    unrelated results.

    Blank lines stay blank rather than becoming two spaces, so the
    separator between blocks survives.

    The title line arrives as "\nContacts:" — a leading newline, not a
    separate blank entry — so indenting it needs the prefix inserted
    AFTER the newline rather than before it. A naive prefix put the
    title at column 0 while its rows sat indented under it, which read
    as a new top-level result rather than a child of the row above.
    """
    out: list[str] = []
    for ln in lines:
        if not ln.strip():
            out.append(ln)
        elif ln.startswith("\n"):
            out.append("\n" + by + ln[1:])
        else:
            out.append(by + ln)
    return out


def _render_records(
    title: str,
    rows: list[dict],
    columns: list[str],
    empty_text: str,
) -> list[str]:
    """Render typed records as a table, or vertically when there is one.

    Replaces the per-entity bullet blocks. Those printed one line per
    record with the field names repeated inline:

        - Lee Supplies (SupplierId=300000047414503, SupplierNumber=1252)
        - Distributori Automatici Roma Miglior Caffe (SupplierId=3000...)

    which cannot be scanned down a column, repeats every label on every
    row, and runs off the screen on long values. Column queries have
    printed a table since the projection feature shipped; there was
    never a reason for the same data to render two ways depending on
    which code path produced it.

    TWO SHAPES, CHOSEN BY THE DATA

    Many records -> a table, columns aligned.

    One record -> vertical, field per line. A one-row table is as wide
    as its widest value and forces the reader across the screen to read
    a single thing; the vertical form puts the fields under each other,
    which is how anyone reads a single record.

    The shape follows the data, never the code path. That is the whole
    point: an answer should not look different because of which branch
    of a formatter built it.

    Columns come from the caller and match what the typed record used to
    print — this is a LAYOUT change and nothing else. A branch that
    starts choosing different columns as well makes any difference in
    output impossible to attribute.

    Nested values (a supplier's addresses, a PO's lines) flatten to one
    cell, as the column path already does. That loses the one thing
    bullets could do and tables cannot: nest. Accepted deliberately —
    twenty-five suppliers with twenty-five addresses each is two hundred
    lines of nesting, which was the original argument for summary_only
    on the column path.

    Missing values print as an em dash, so absent is visibly different
    from empty.
    """
    if not rows:
        return [empty_text]

    out = [f"\n{title}:"]

    if len(rows) == 1:
        row = rows[0]
        label_w = max(len(c) for c in columns)
        for c in columns:
            v = row.get(c)
            out.append(f"  {c.ljust(label_w)} : {'—' if v in (None, '') else v}")
        return out

    widths = {}
    for c in columns:
        cell_lens = [
            len(str(r.get(c))) if r.get(c) not in (None, "") else 1 for r in rows
        ]
        widths[c] = max([len(c)] + cell_lens)

    numeric = {c: _is_quantity(c, [r.get(c) for r in rows]) for c in columns}

    def _cell(text: str, col: str) -> str:
        return text.rjust(widths[col]) if numeric[col] else text.ljust(widths[col])

    out.append("  " + " | ".join(_cell(c, c) for c in columns))
    out.append("  " + "-+-".join("-" * widths[c] for c in columns))
    for r in rows:
        cells = []
        for c in columns:
            v = r.get(c)
            cells.append(_cell("—" if v in (None, "") else str(v), c))
        out.append("  " + " | ".join(cells))
    return out


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
        return _with_truncation(["Answer:", summary], response)

    lines = ["Answer:"]
    if isinstance(response, SynthesizedResponse) or isinstance(response, SupplierResponse):
        # An empty summary is now a legitimate answer: with records in a
        # table below, there is often nothing to say that the table does
        # not already show. Appending "" anyway left a blank line under
        # "Answer:" and another under that, which reads as something
        # having gone missing.
        if response.summary:
            lines.append(response.summary)
        rows = []
        for s in response.suppliers:
            row = {
                "Supplier": s.supplier_name,
                "SupplierId": s.supplier_id,
                "SupplierNumber": s.supplier_number,
            }
            if s.open_po_count is not None:
                row["Open POs"] = s.open_po_count
            if s.buyers:
                row["Buyers"] = ", ".join(b.display_name for b in s.buyers)
            if s.addresses:
                # First address only, as the column path does. A
                # supplier with 25 addresses would otherwise own 25 rows
                # of a table that is meant to have one row per supplier.
                a = s.addresses[0]
                row["Address"] = a.formatted_address or f"{a.city}, {a.country}"
                if len(s.addresses) > 1:
                    row["Address"] += f" (+{len(s.addresses) - 1} more)"
            rows.append(row)
        cols = ["Supplier", "SupplierId", "SupplierNumber"]
        for extra in ("Open POs", "Buyers", "Address"):
            if any(extra in r for r in rows):
                cols.append(extra)
        lines.extend(
            _render_records("Suppliers", rows, cols, "No suppliers found.")
        )
        # Contacts stay OUT of the table, below it, one per line.
        #
        # They were briefly a table cell, joined with commas, and the
        # result was unreadable for a reason worth recording: the values
        # themselves contain commas. Ten contacts rendered as
        #   Kim, John, Rossier, Bruce, Romo, Gabi, ...
        # where "Kim, John" is ONE person in "Last, First" form. The
        # separator collided with the data and produced a line no reader
        # can parse — strictly worse than the bullets this replaced.
        #
        # The general rule, the same one the AR tax lines follow: a
        # one-to-many relationship belongs below the table, not squeezed
        # into a cell. A table row is one record; contacts are their own
        # records.
        for s in response.suppliers:
            if s.contacts:
                lines.extend(
                    _indent(
                        _render_records(
                            f"{s.supplier_name} — contacts",
                            [
                                {"Contact": c.contact_name, "Email": c.email}
                                for c in s.contacts
                            ],
                            ["Contact", "Email"],
                            "",
                        )
                    )
                )
        return _with_truncation(lines, response)

    if isinstance(response, InvoiceResponse):
        lines.append(response.summary)
        rows = [
            {
                "Invoice": inv.invoice_number,
                "InvoiceId": inv.invoice_id,
                "Amount": inv.invoice_amount,
                "Currency": inv.invoice_currency,
                "Date": inv.invoice_date,
                "Supplier": inv.supplier_name,
            }
            for inv in response.invoices
        ]
        lines.extend(
            _render_records(
                "Invoices",
                rows,
                ["Invoice", "InvoiceId", "Amount", "Currency", "Date", "Supplier"],
                "No invoices found.",
            )
        )
        return _with_truncation(lines, response)

    if isinstance(response, PurchaseOrderResponse):
        lines.append(response.summary)
        rows = []
        for po in response.purchase_orders:
            row = {
                "Order": po.order_number,
                "POHeaderId": po.po_header_id,
                "Status": po.status,
                "Supplier": po.supplier_name,
            }
            if po.buyer:
                row["Buyer"] = po.buyer.display_name
            # Counts, not the child rows themselves — the same thing the
            # bullets showed. That "lines: 2" is a COUNT where the user
            # asked for the lines is a real defect, carried forward and
            # NOT fixed here: this change is layout only, and fixing it
            # inside a formatting change would hide it in the diff.
            if po.lines:
                row["Lines"] = len(po.lines)
            if po.schedules:
                row["Schedules"] = len(po.schedules)
            if po.distributions:
                row["Distributions"] = len(po.distributions)
            rows.append(row)
        cols = ["Order", "POHeaderId", "Status", "Supplier"]
        for extra in ("Buyer", "Lines", "Schedules", "Distributions"):
            if any(extra in r for r in rows):
                cols.append(extra)
        lines.extend(
            _render_records(
                "Purchase Orders", rows, cols, "No purchase orders found."
            )
        )
        return _with_truncation(lines, response)

    if isinstance(response, ReceivablesInvoiceResponse):
        lines.append(response.summary)
        rows = []
        for inv in response.receivables_invoices:
            row = {
                "Transaction": inv.transaction_number,
                "CustomerTransactionId": inv.customer_transaction_id,
                "Amount": inv.amount,
                "Currency": inv.currency,
                "Date": inv.transaction_date,
                "Customer": inv.bill_to_customer_name,
                "Status": inv.status,
            }
            if inv.lines:
                row["Lines"] = len(inv.lines)
            if inv.dff:
                row["DFF"] = inv.dff.context
            rows.append(row)
        cols = [
            "Transaction", "CustomerTransactionId", "Amount", "Currency",
            "Date", "Customer", "Status",
        ]
        for extra in ("Lines", "DFF"):
            if any(extra in r for r in rows):
                cols.append(extra)
        lines.extend(
            _render_records("AR Invoices", rows, cols, "No AR invoices found.")
        )
        # Tax lines nest two deep — line, then tax rows under it — which
        # a table cannot hold. Kept as a block BELOW the table rather
        # than flattened to a count.
        #
        # This detail was silently dropped once already: the tax-line
        # prompt printed "lines: 4" and no tax at all while the executor
        # had fetched 8 tax rows and the narration described them. It is
        # here for that reason and must not be reduced to a number.
        # `ln`, not `line` — `lines` is the output buffer.
        for inv in response.receivables_invoices:
            for ln in inv.lines or []:
                if ln.tax_lines:
                    lines.extend(
                        _indent(
                            _render_records(
                                f"Invoice {inv.transaction_number}, line "
                                f"{ln.line_number} — tax",
                                [
                                    {
                                        "Tax": tx.tax,
                                        "Rate %": tx.tax_rate,
                                        "Tax Amount": tx.tax_amount,
                                        "Taxable": tx.taxable_amount,
                                    }
                                    for tx in ln.tax_lines
                                ],
                                ["Tax", "Rate %", "Tax Amount", "Taxable"],
                                "",
                            )
                        )
                    )
        return _with_truncation(lines, response)

    if isinstance(response, CustomerAccountResponse):
        lines.append(response.summary)
        rows = []
        for acct in response.customer_accounts:
            row = {
                "Customer": acct.customer_name,
                "AccountId": acct.account_id,
                "AccountNumber": acct.account_number,
                "Open Receivables": acct.open_receivables,
                "Transactions Due": acct.transactions_due,
            }
            if acct.transactions:
                row["Transactions"] = len(acct.transactions)
            if acct.credit_memos:
                row["Credit Memos"] = len(acct.credit_memos)
            if acct.receipts:
                row["Receipts"] = len(acct.receipts)
            if getattr(acct, "applications", None):
                row["Applications"] = len(acct.applications)
            rows.append(row)
        cols = [
            "Customer", "AccountId", "AccountNumber",
            "Open Receivables", "Transactions Due",
        ]
        for extra in ("Transactions", "Credit Memos", "Receipts", "Applications"):
            if any(extra in r for r in rows):
                cols.append(extra)
        lines.extend(
            _render_records(
                "Customer Accounts", rows, cols, "No customer accounts found."
            )
        )
        return _with_truncation(lines, response)

    if isinstance(response, AddressResponse):
        lines.append(response.summary)
        rows = [
            {
                "Address": a.formatted_address or f"{a.city}, {a.country}",
                "AddressId": a.address_id,
                "Supplier": a.supplier_name,
                "SupplierNumber": a.supplier_number,
            }
            for a in response.addresses
        ]
        lines.extend(
            _render_records(
                "Addresses",
                rows,
                ["Address", "AddressId", "Supplier", "SupplierNumber"],
                "No addresses found.",
            )
        )
        return _with_truncation(lines, response)

    if isinstance(response, CreditMemoListResponse):
        lines.append(response.summary)
        if response.credit_memos:
            rows = [
                {
                    "Transaction": cm.transaction_number,
                    "CustomerTransactionId": cm.customer_transaction_id,
                    "Amount": cm.entered_amount,
                    "Currency": cm.currency,
                    "Date": cm.transaction_date,
                    "Customer": cm.customer_name,
                    "Status": cm.status,
                }
                for cm in response.credit_memos
            ]
            lines.extend(
                _render_records(
                    "Credit Memos (newest first)",
                    rows,
                    [
                        "Transaction", "CustomerTransactionId", "Amount",
                        "Currency", "Date", "Customer", "Status",
                    ],
                    "No credit memos found.",
                )
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
        return _with_truncation(lines, response)

    if isinstance(response, CountResponse):
        lines.append(response.summary)
        if not response.count_is_exact:
            lines.append(f"(count is a lower bound; true total may be higher)")
        return "\n".join(lines)

    if isinstance(response, ComparisonResponse):
        lines.append(response.summary)
        return _with_truncation(lines, response)

    if isinstance(response, SupplierSpendRankingResponse):
        lines.append(response.summary)
        lines.extend(
            _render_records(
                "Top suppliers by spend",
                [
                    {
                        "Rank": i,
                        "Supplier": row.supplier_name,
                        "SupplierNumber": row.supplier_number,
                        "Total Spend": f"{row.total_spend:,.2f}",
                        "Invoices": row.invoice_count,
                    }
                    for i, row in enumerate(response.suppliers, 1)
                ],
                ["Rank", "Supplier", "SupplierNumber", "Total Spend", "Invoices"],
                "No suppliers found.",
            )
        )
        return _with_truncation(lines, response)

    if isinstance(response, SupplierPOValueRankingResponse):
        lines.append(response.summary)
        lines.extend(
            _render_records(
                "Top suppliers by PO value",
                [
                    {
                        "Rank": i,
                        "Supplier": row.supplier_name,
                        "SupplierId": row.supplier_id,
                        "Total Ordered": f"{row.total_ordered:,.2f}",
                        "POs": row.po_count,
                    }
                    for i, row in enumerate(response.suppliers, 1)
                ],
                ["Rank", "Supplier", "SupplierId", "Total Ordered", "POs"],
                "No suppliers found.",
            )
        )
        return _with_truncation(lines, response)

    if isinstance(response, POStatusBreakdownResponse):
        lines.append(response.summary)
        lines.append(f"\nTotal POs: {response.total_pos}, total value: {response.total_ordered:,.2f}")
        lines.extend(
            _render_records(
                "Breakdown by status",
                [
                    {
                        "Status": row.status,
                        "POs": row.po_count,
                        "Total Ordered": f"{row.total_ordered:,.2f}",
                    }
                    for row in response.statuses
                ],
                ["Status", "POs", "Total Ordered"],
                "",
            )
        )
        return _with_truncation(lines, response)

    if isinstance(response, OpenPOSummaryResponse):
        lines.append(response.summary)
        lines.append(
            f"\nOpen PO count: {response.po_count}, total ordered: {response.total_ordered:,.2f}, "
            f"suppliers: {response.supplier_count}"
        )
        return _with_truncation(lines, response)

    # --- StandardReceiptResponse ---
    if isinstance(response, StandardReceiptResponse):
        lines.append(response.summary)
        receipts = getattr(response, 'standard_receipts', [])
        rows = [
            {
                "Receipt": r.receipt_number,
                "ReceiptId": r.standard_receipt_id,
                "Amount": r.amount,
                "Currency": r.currency,
                "Date": r.receipt_date,
                "Method": r.receipt_method,
                "Site": r.customer_site,
                "Bank": r.remittance_bank_name,
            }
            for r in receipts
        ]
        lines.extend(
            _render_records(
                "Receipts",
                rows,
                [
                    "Receipt", "ReceiptId", "Amount", "Currency", "Date",
                    "Method", "Site", "Bank",
                ],
                "No receipts found.",
            )
        )
        return _with_truncation(lines, response)

    # --- ExposureRankingResponse ---
    if isinstance(response, ExposureRankingResponse):
        lines.append(response.summary)
        lines.extend(
            _render_records(
                "Top accounts by outstanding exposure",
                [
                    {
                        "Rank": i,
                        "Customer": row.customer_name,
                        "AccountNumber": row.account_number,
                        "Open Receivables": f"{row.open_receivables:,.2f}",
                    }
                    for i, row in enumerate(response.accounts, 1)
                ],
                ["Rank", "Customer", "AccountNumber", "Open Receivables"],
                "No accounts found.",
            )
        )
        return _with_truncation(lines, response)

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
        return _with_truncation(lines, response)

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

        return _with_truncation(lines, response)
    
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
