"""Planner registries — the v1 mapping tables.

Intent filter types come from the LLM parser, which uses domain-friendly
names ('country', 'has_open_PO', 'has_no_recent_invoices'). The KG uses
normalized names. These tables bridge the two. Pure data, no logic, no
dependency on any other planner module — this is the bottom of the
planner's dependency graph, same role constants.py plays for the
synthesizer.

v1.2 candidate: move these into the KG itself so the planner is fully
data-driven. For v1.1 they are hardcoded so the planner stays small and
the KG schema stays simple.
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────
# v1 mapping tables (intent vocabulary -> KG vocabulary)
#
# Intent filter types come from the LLM parser, which uses
# domain-friendly names ('country', 'has_open_PO',
# 'has_no_recent_invoices'). The KG uses normalized names
# ('country' as kg_entity_tool.filter_type, 'status' as
# kg_pattern_binding.filter_type). These tables bridge the two.
#
# v1.2 candidate: move these into the KG itself so the planner is
# fully data-driven. For v1.1 they're hardcoded so the planner stays
# small and the KG schema stays simple.
# ─────────────────────────────────────────────────────────────────────

# Filter definitions (entity-level vs edge-traversal, vocab kinds,
# implicit values) are no longer hardcoded here. They live in the KG
# table kg_entity_filter and are read lazily by _load_filter_defs()
# below. See the "Filter definitions" section further down.

# Map MCP tool name -> primary argument name (the one the executor
# substitutes $iteration_value into when iterating).
# v1.2 candidate: store this in the KG (e.g., kg_edge_tool.arg_name).
_TOOL_PRIMARY_ARG: dict[str, str] = {
    "search_invoices": "supplier_number",
    "search_purchase_orders": "supplier_id",
    "get_buyer": "buyer_id",
    "search_suppliers_by_site_bu": "supplier_id",
    "search_suppliers_by_classification": "supplier_id",
    # P2: single-PO fetch and its lines child. Both key off POHeaderId.
    "get_purchase_order_by_id": "po_header_id",
    # Module 5: the lifecycle reconciliation. Keys off the PO NUMBER
    # (OrderNumber), not POHeaderId — the only PO tool that does. Rooted
    # and single-fetch, so nothing iterates on it today; registered for
    # any single-arg reader, as the distributions and tax-line tools are.
    "get_purchase_order_lifecycle_status": "po_number",
    "get_purchase_order_lines": "po_header_id",
    # P3: PO schedules (flat endpoint), one-hop expansion by POHeaderId.
    "get_purchase_order_schedules": "po_header_id",
    # P4: supplier contacts, per-supplier child expansion by SupplierId.
    "get_supplier_contacts": "supplier_id",
    # P3b: PO distributions. Multi-field iteration (needs three ids), so
    # Block 3 builds its args from the edge's iter_fields map rather than
    # this table. Registered anyway for any single-arg reader; the primary
    # id is the schedule's LineLocationId.
    "get_purchase_order_distributions": "line_location_id",
    # AR-P2: single AR-invoice fetch and its lines child. Both key off
    # CustomerTransactionId.
    "get_receivables_invoice_by_id": "customer_transaction_id",
    "get_receivables_invoice_lines": "customer_transaction_id",
    # AR-P3: tax lines. Multi-field iteration (needs two ids: invoice +
    # line), so Block 3 builds its args from the edge's iter_fields map,
    # not this table. Registered anyway for any single-arg reader; the
    # primary id is the parent line's CustomerTransactionLineId, which
    # the tool receives as line_id.
    "get_receivables_invoice_tax_lines": "line_id",
    # AR-P2b: customer's transactions via the account traversal. The edge
    # tool iterates on the account's AccountId. (The resolver
    # get_customer_account_by_name is the entity fetcher, not an iterated
    # tool, so it takes its arg from the by_customer_name filter, not here.)
    "get_customer_transactions": "account_id",
    # AR-P3 DFF: invoice TransactionDFF child. Plain single-parent
    # expansion (iter_fields is NULL), so Block 3 reads the primary arg
    # from this table. The tool takes customer_transaction_id.
    "get_receivables_invoice_transaction_dff": "customer_transaction_id",
    # AR-P5 prompt 7: the account's credit memos. Plain single-parent
    # expansion iterating on the account's AccountId, same shape as
    # get_customer_transactions above.
    "get_account_credit_memos": "account_id",
    # AR-P5 prompt 8: the account's receipts. Same shape again — a plain
    # single-parent expansion on AccountId.
    "get_account_receipts": "account_id",
    # AR-P5 prompt 9: receipt applications.
    "get_account_receipt_applications": "account_id",
}

# Map aggregation op -> (mcp_tool_name, arg names it accepts). One op
# per tool, by design (feature 7 boundedness rule): a new aggregation
# shape is a new op + new tool, never a parameter on an existing one.
_AGGREGATION_TOOLS: dict[str, str] = {
    # Each op names ONE bounded aggregation tool. Per the aggregation
    # layer's rule, a different grouping or measure is a different tool —
    # and so a different op — never a flag on an existing one.
    #
    # NOTE: 'by_supplier' names only the grouping, not the source or
    # measure. That was unambiguous when it was the only aggregation; it
    # isn't now that two rankings group by supplier (invoice spend vs PO
    # value). Left as-is rather than renamed to spend_by_supplier: the
    # rename would break the parser instruction and any test asserting the
    # op string, for tidiness only. The P6 ops below carry the fuller
    # source+measure+grouping naming, so the pattern is set going forward.
    "by_supplier": "aggregate_invoices_by_supplier",
    "po_value_by_supplier": "aggregate_purchase_orders_by_supplier",
    "po_count_by_status": "aggregate_purchase_orders_by_status",
    "open_po_summary": "summarize_open_purchase_orders",
    "exposure_ranking": "rank_customer_accounts_by_exposure",
    "receipt_method_distribution": "aggregate_standard_receipts_by_method",
}


# Which aggregate-block params each op's tool actually accepts. The
# parser sets what the question implies (and defaults top_n=10), so the
# planner must not forward a param the tool has no parameter for — it
# raises. Kept beside the op registry so adding a tool means adding both
# rows, and forgetting one fails loudly at plan time rather than in the
# tool call.
_AGGREGATION_PARAMS: dict[str, tuple[str, ...]] = {
    "by_supplier": ("date_from", "date_to", "top_n"),
    "po_value_by_supplier": ("status", "top_n"),  # no date: PO dates aren't filterable
    "po_count_by_status": (),                     # groups by status; takes nothing
    "open_po_summary": (),                        # open by identity; takes nothing
    "exposure_ranking": ("top_n",),
    # Scoped aggregate: the scope arrives as an intent FILTER, not in the
    # aggregate block, so _build_aggregation_plan reads both.
    "receipt_method_distribution": ("customer_name", "account_number", "limit"),
}


# P6c: map comparison op -> tool. Same one-op-per-tool discipline as the
# aggregation registry: a different comparison shape is a different op and
# a different tool, never a flag. Comparison is its own block (not an
# aggregate op) because it joins two sources and reports a difference
# rather than grouping and totalling one.
_COMPARISON_TOOLS: dict[str, str] = {
    "po_invoiced_vs_ordered": "compare_purchase_order_to_invoices",
    "supplier_invoiced_vs_ordered": "compare_supplier_orders_to_invoices",
    "top_suppliers_invoiced_vs_ordered": "compare_top_suppliers_orders_to_invoices",
}

# Which compare-block params each op's tool accepts. Same rationale as
# _AGGREGATION_PARAMS: the parser sets what the question implies (and
# defaults top_n), so the planner forwards only the params THIS op's tool
# takes — forwarding an unknown one raises in the tool call. Adding a
# comparison tool means adding both this row and the _COMPARISON_TOOLS
# row; forgetting one fails loudly at plan time.
_COMPARISON_PARAMS: dict[str, tuple[str, ...]] = {
    "po_invoiced_vs_ordered": ("po_number",),
    "supplier_invoiced_vs_ordered": ("supplier_name", "top_n"),
    "top_suppliers_invoiced_vs_ordered": ("top_n", "status"),
}

# Friendly output-name prefixes per entity. Pure naming convention;
# the executor doesn't interpret these.
_OUTPUT_NAME_BY_ENTITY: dict[str, str] = {
    "Supplier": "suppliers",
    "Invoice": "invoices",
    "PurchaseOrder": "pos",
    "Buyer": "buyers",
    "Address": "addresses",
    "ReceivablesInvoice": "receivables_invoices",
    "ReceivablesInvoiceLine": "receivables_invoice_lines",
    "CustomerAccount": "customer_accounts",
    "CustomerTransaction": "customer_transactions",
    "CreditMemo": "credit_memos",
    # AR-P5 prompt 7. Deliberately NOT "credit_memos" — that name belongs
    # to AR-P4's top-level CreditMemo, and the two are different entities
    # over different id spaces. Sharing a bucket name would let one
    # overwrite the other and would make the synthesizer's id-harvest
    # ambiguous about which set a row belongs to.
    "AccountCreditMemo": "account_credit_memos",
    # AR-P5 prompt 8. Its own bucket, like the memos above — the
    # synthesizer nests receipts and memos separately under the account.
    "AccountReceipt": "account_receipts",
    # AR-P5 prompt 9.
    "AccountReceiptApplication": "account_receipt_applications",
    "StandardReceipt": "standard_receipts",
}

# Filter-type -> short suffix used when the step's output is the
# filtered parent list (i.e. filter_source_when_empty=True).
# Composed with the source output name as
# "{source_output_name}_{suffix}". v1.2 candidate: move into the KG.
_FILTER_SOURCE_NAME_SUFFIX: dict[str, str] = {
    "has_no_recent_invoices": "no_recent_invoices",
}

# Phase 11: edge-traversal filters that keep the PARENT when the child
# call returns something (after a value filter carried in tool_args) —
# the mirror of _FILTER_SOURCE_NAME_SUFFIX. Maps type -> output suffix.
_FILTER_SOURCE_NONEMPTY_SUFFIX: dict[str, str] = {
    "has_invoice_over_amount": "has_invoice_over_amount",
    "has_site_in_bu": "has_site_in_bu",
    "has_classification": "has_classification",
}


# W1 (refusal quality): a worked example per entity, used when an intent
# names a filter type the entity does not support. Without one the user
# got a raw dump of internal filter names and had to guess what to type
# instead. This mirrors what the entity guards in generate_plan already
# do inline — those cover Invoice, Address, PurchaseOrder and
# ReceivablesInvoice; this covers everything else, and any entity added
# later. An entity absent from this map degrades to the supported-filter
# list alone: the old behaviour minus the internal jargon.
_ENTITY_EXAMPLE_PROMPT: dict[str, str] = {
    "Supplier": "active suppliers in US",
    "Invoice": "invoices for Lee Supplies",
    "Address": "addresses for supplier 1252",
    "PurchaseOrder": "show PO 2144 and its lines",
    "ReceivablesInvoice": (
        "show the AR invoice with CustomerTransactionId 300000248096352"
    ),
    "CustomerAccount": "account balance for ABC Application Software",
    "CreditMemo": "list recent credit memos",
    "StandardReceipt": "receipts for ABC Application Software",
}
