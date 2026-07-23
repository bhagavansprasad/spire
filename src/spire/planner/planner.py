"""
Planner for the KG-driven path (Architecture Option 3).

This module is the contract between the LLM intent-parsing step and the
MCP executor. It reads only from the KG (see scripts/rebuild_kg.sh) and emits a
structured plan. No LLM in the planning step. No prose-reading for
decisions.

Status: KG-lookup layer, helpers, orchestrator, intent validation,
and the F2 'no_invoices_in_N_months' negation pattern all
implemented. v1.1 covers the anchor question + the original Track A
prompt's negation clause. See design doc for known limitations.

Companion design doc: docs/designs/phase_2_planner_design.md
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterator

import oracledb


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


# ─────────────────────────────────────────────────────────────────────
# KG connection
# ─────────────────────────────────────────────────────────────────────

# Oracle KG credentials resolve in this order, per field:
#   1. Environment variable (SPIRE_DB_USER / _PASSWORD / _DSN) — for CI
#      and ad-hoc overrides.
#   2. The persona's `oracle` block in personas.yaml — the normal source
#      and the single place to configure DB credentials.
# There is no hardcoded credential fallback: if neither source supplies a
# value, _oracle_credentials raises. (The DSN, being a non-secret local
# address, keeps a default; user and password must be configured.)

_DEFAULT_DSN = "localhost:1521/FREEPDB1"


def _oracle_credentials() -> tuple[str, str, str]:
    """Resolve (user, password, dsn) for the KG connection.

    Env vars win, then the persona's oracle block. No credential is
    hardcoded: if neither source provides a username/password, raise a
    clear error rather than silently using a baked-in default. The DSN
    falls back to the local address (not a secret) if unspecified."""
    persona_oracle = None
    try:
        from spire.config import load_persona

        persona_name = os.environ.get("SPIRE_PERSONA", "default_dev")
        persona_oracle = load_persona(persona_name).oracle
    except Exception:
        # No personas.yaml, unknown persona, or no oracle block — env
        # vars may still supply the credentials.
        persona_oracle = None

    user = os.environ.get("SPIRE_DB_USER") or (
        persona_oracle.username if persona_oracle else None
    )
    password = os.environ.get("SPIRE_DB_PASSWORD") or (
        persona_oracle.password if persona_oracle else None
    )
    dsn = os.environ.get("SPIRE_DB_DSN") or (
        persona_oracle.dsn if persona_oracle else None
    ) or _DEFAULT_DSN

    if not user or not password:
        raise RuntimeError(
            "No Oracle DB credentials. Set the oracle block in "
            "personas.yaml (username + password), or export "
            "SPIRE_DB_USER / SPIRE_DB_PASSWORD."
        )
    return user, password, dsn


@contextmanager
def _kg_cursor() -> Iterator[oracledb.Cursor]:
    """
    Yield a cursor against the KG database. Closes connection on exit.

    Every KG-lookup function opens a fresh connection; pooling can be
    added later if profiling shows it matters.
    """
    user, password, dsn = _oracle_credentials()
    connection = oracledb.connect(user=user, password=password, dsn=dsn)
    try:
        with connection.cursor() as cursor:
            yield cursor
    finally:
        connection.close()


def _read_clob(value: Any) -> str:
    """
    Coerce a possibly-CLOB column value to a Python str.

    Sync oracledb sometimes returns CLOB values as oracledb.LOB objects
    (which have a sync .read() method), and sometimes — depending on
    driver version and column size — as plain strings. Handle both.

    Returns empty string for None.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    # Sync oracledb.LOB: .read() is synchronous (unlike AsyncLOB).
    return value.read()


# ─────────────────────────────────────────────────────────────────────
# Filter definitions — loaded from kg_entity_filter (lazy, cached).
#
# Replaces the hardcoded filter dicts. Read once on first use, cached
# for the process lifetime. Mirrors the lazy-read style of the other
# KG lookups in this module.
# ─────────────────────────────────────────────────────────────────────

_FILTER_DEFS_CACHE: dict[tuple[str, str], dict[str, Any]] | None = None


def _load_filter_defs() -> dict[tuple[str, str], dict[str, Any]]:
    """Read kg_entity_filter once; cache by (filter_type, entity_name)."""
    global _FILTER_DEFS_CACHE
    if _FILTER_DEFS_CACHE is not None:
        return _FILTER_DEFS_CACHE

    defs: dict[tuple[str, str], dict[str, Any]] = {}
    with _kg_cursor() as cursor:
        cursor.execute(
            "SELECT filter_type, mechanism, tool_arg_name, tool_arg_name_hi, "
            "vocab_kind, target_entity, kg_filter_type, implicit_vocab_kind, "
            "implicit_term, entity_name FROM kg_entity_filter"
        )
        for row in cursor.fetchall():
            (ftype, mechanism, tool_arg, tool_arg_hi, vocab_kind, target,
             kg_filter_type, imp_vocab, imp_term, entity) = row
            key = (ftype, entity)
            defs[key] = {
                "mechanism": mechanism,
                "tool_arg_name": tool_arg,
                "tool_arg_name_hi": tool_arg_hi,
                "vocab_kind": vocab_kind,
                "target_entity": target,
                "kg_filter_type": kg_filter_type,
                "implicit_vocab_kind": imp_vocab,
                "implicit_term": imp_term,
            }
    _FILTER_DEFS_CACHE = defs
    return defs


def _filter_def_for(ftype: str, entity: str) -> dict[str, Any]:
    """Return the filter definition for (filter_type, source_entity)."""
    defs = _load_filter_defs()
    key = (ftype, entity)
    if key not in defs:
        raise KeyError(f"No filter definition for ({ftype!r}, {entity!r})")
    return defs[key]


def _entity_level_filter_types() -> dict[str, set[str]]:
    """Filter types with a dedicated entity-level fetcher, grouped by source entity."""
    defs = _load_filter_defs()
    result: dict[str, set[str]] = {}
    for (ftype, entity), d in defs.items():
        if d["mechanism"] == "entity_level":
            result.setdefault(entity, set()).add(ftype)
    return result


def _edge_traversal_filters() -> dict[str, tuple[str, str]]:
    """Edge-traversal filters: type -> (target_entity, kg_filter_type)."""
    defs = _load_filter_defs()
    result: dict[str, tuple[str, str]] = {}
    for (ftype, entity), d in defs.items():
        if d["mechanism"] == "edge_traversal":
            result[ftype] = (d["target_entity"], d["kg_filter_type"])
    return result


def _edge_filter_implicit_values() -> dict[str, tuple[str, str]]:
    """Edge filters with an implicit value: type -> (vocab_kind, term)."""
    defs = _load_filter_defs()
    result: dict[str, tuple[str, str]] = {}
    for (ftype, entity), d in defs.items():
        if d["implicit_vocab_kind"] is not None:
            result[ftype] = (d["implicit_vocab_kind"], d["implicit_term"])
    return result


# ─────────────────────────────────────────────────────────────────────
# Types
# ─────────────────────────────────────────────────────────────────────


@dataclass
class Intent:
    """
    Output of the LLM intent-parsing step.
    Input to ``generate_plan``.

    Example (for the original Track A prompt
    'suppliers in US with no invoices in 6 months but with open POs,
    including the buyer assigned to each'):

        Intent(
            target_entity="Supplier",
            filters=[
                {"type": "country", "value": "US"},
                {"type": "has_no_recent_invoices", "value": {"months": 6}},
                {"type": "has_open_PO", "value": True},
            ],
            include=["Buyer"],
        )
    """

    target_entity: str
    filters: list[dict[str, Any]] = field(default_factory=list)
    include: list[str] = field(default_factory=list)
    # Phase 7: when the prompt names specific columns, the LLM fills this
    # with exact column names (from kg_entity_field). Empty means "return
    # the default field set". Projection trims the raw output records to
    # these columns; the synthesized prose answer is unaffected.
    fields: list[str] = field(default_factory=list)
    # Feature 7: when set, the question is an aggregation, not a list.
    # The LLM parser fills this when it detects aggregation/ranking
    # wording; it is None for ordinary list queries (the default), so
    # all existing behavior is unchanged. Shape:
    #   {"op": "by_supplier", "date_from": "...", "date_to": "...",
    #    "top_n": 10}
    # The planner maps a populated aggregate to a single tool step; the
    # op names the bounded aggregation tool (one op per tool, by design).
    aggregate: dict[str, Any] | None = None

    # P6c: when set, the question is a comparison of invoiced vs ordered,
    # not a list, ranking, or total. The LLM parser fills this when it
    # detects invoiced-vs-ordered wording; None for everything else (the
    # default), so all existing behavior is unchanged. Shape:
    #   {"op": "po_invoiced_vs_ordered", "po_number": "162034",
    #    "supplier_name": None, "top_n": 5, "status": None}
    # The planner maps a populated compare to a single tool step; the op
    # names the bounded comparison tool (one op per tool, like aggregate).
    # Checked AFTER aggregate in generate_plan, so if a confused parse
    # sets both, aggregate wins and compare is ignored (mirrors the
    # aggregate/count_only precedence).
    compare: dict[str, Any] | None = None

    # Phase 10: when True, the question asks "how many X" — report the
    # count, not a record list. The normal fetch still runs (its
    # total_available carries the count); the synthesizer emits a count
    # summary. Kept separate from aggregate (which routes to bounded
    # aggregation tools) — count reuses the entity's default fetcher.
    count_only: bool = False

    # AR-P2c: when True on a customer-invoices query (CustomerAccount +
    # by_customer_name + CustomerTransaction in include), the
    # CustomerTransaction include step passes open_only=True to its tool,
    # restricting the listed transactions to those with a positive open
    # balance. Consumed entirely in Block 3; the fetcher applies the
    # balance filter (and returns rows balance-desc). Defaults False so
    # ordinary customer-invoice listings (prompt 15) are unchanged.
    open_only: bool = False

    # Top-N open invoices: when set alongside open_only on a customer-
    # invoices query, cap the listed transactions to the N highest-balance
    # open rows. Rides as a literal `limit` tool_arg on the same
    # CustomerTransaction include step (the fetcher returns balance-desc,
    # so limit keeps the top N). Consumed entirely in Block 3. Defaults
    # None (no cap) so plain open-invoice listings are unchanged.
    invoice_limit: int | None = None

    # AR-P5 (prompt 6): when True, the question asks for a customer's
    # ACCOUNT BALANCE / activity summary rather than their transactions —
    # "what is the account balance for customer X". Same root as the
    # customer-invoices shape (CustomerAccount + by_customer_name), but
    # the parser emits an EMPTY include, so Block 3 never runs and no
    # transaction fetch happens: the balance fields
    # (TotalOpenReceivablesForAccount, TotalTransactionsDueForAccount)
    # already ride on the account record Block 1 fetches.
    #
    # WHY A FLAG AND NOT JUST THE EMPTY INCLUDE: the empty include is what
    # makes the plan correct, but it is not a reliable SIGNAL — a future
    # prompt could legitimately root on CustomerAccount with no include and
    # mean something else. The synthesizer and run_plan.py dispatch on this
    # flag rather than inferring shape from an absence. Consumed
    # downstream of the planner only; generate_plan needs no branch for it
    # (an empty include already produces the right plan).
    balance_only: bool = False


@dataclass
class Step:
    """
    One step in a Plan. The executor reads these top-to-bottom.

    - ``tool_args`` values may be literals or the sentinel string
      ``"$iteration_value"`` (substituted by the executor when iterating).
    - ``iterate_over`` is ``None`` when the step runs once; otherwise
      ``{"from_step": <output_name>, "field": <field_name>}``.
    - ``client_filters`` are applied in Python after each tool call.
      All v1 edges have ``server_filter_rule = 'join_only'``, so any
      filter beyond the join key lives here.
    - ``filter_source_when_empty`` (F2): when True, the step's output
      is the SOURCE step's items, filtered to those whose per-iteration
      tool call returned an empty list. Used for "negation by absence"
      filters like "suppliers with NO invoices in the last 6 months".
      The executor honors this flag; it defaults to False so existing
      steps behave unchanged.
    - ``filter_source_when_nonempty`` (Phase 11): the mirror — the
      step's output is the SOURCE items whose per-iteration call returned
      SOMETHING (after any value filter in tool_args, e.g. amount_min).
      Used for "X that HAS a Y matching a condition" — e.g. "suppliers
      with an invoice over 10000". Defaults to False.
    """

    step_id: int
    tool_name: str
    tool_args: dict[str, Any]
    iterate_over: dict[str, str] | None
    client_filters: list[dict[str, Any]]
    output_name: str
    output_dedupe_by: str | None
    filter_source_when_empty: bool = False
    filter_source_when_nonempty: bool = False
    # AR-P3: when True, the executor stamps this iterating step's parent
    # field(s) onto each child row it returns, so a FOLLOWING grandchild
    # step can iterate on a parent id the child body doesn't natively
    # carry (AR invoice lines don't echo CustomerTransactionId). Off by
    # default so every other iterating step's output is byte-for-byte
    # unchanged. The planner sets it only on a child step that feeds a
    # further include.
    stamp_parent_key: bool = False


Plan = list[Step]


# ─────────────────────────────────────────────────────────────────────
# KG entity lookups
# ─────────────────────────────────────────────────────────────────────


def find_entity(entity_name: str) -> dict[str, Any]:
    """
    Look up an entity by name in ``kg_entity``.

    Returns a dict with keys:
        endpoint_path, canonical_id_field, display_name_field, description

    Raises ``KeyError`` if no row exists for the given entity_name.
    Match is case-sensitive (entity_name is a primary key).
    """
    with _kg_cursor() as cursor:
        cursor.execute(
            """
            SELECT endpoint_path, canonical_id_field,
                   display_name_field, description
            FROM kg_entity
            WHERE entity_name = :entity_name
            """,
            entity_name=entity_name,
        )
        row = cursor.fetchone()

    if row is None:
        raise KeyError(f"No entity in KG: {entity_name!r}")

    endpoint_path, canonical_id_field, display_name_field, description = row
    return {
        "endpoint_path": endpoint_path,
        "canonical_id_field": canonical_id_field,
        "display_name_field": display_name_field,
        "description": description,
    }


def find_entity_tool(entity_name: str, filter_type: str) -> str:
    """
    Find the MCP tool that fetches this entity with the given filter type.

    Queries ``kg_entity_tool``. Use ``filter_type='none'`` for the default
    (unfiltered) fetcher.

    Examples:
        find_entity_tool('Supplier', 'none')    -> 'search_suppliers'
        find_entity_tool('Supplier', 'country') -> 'search_suppliers_by_country'

    Returns the MCP tool name as a string.
    Raises ``KeyError`` if no row exists for the (entity_name, filter_type)
    pair.
    """
    with _kg_cursor() as cursor:
        cursor.execute(
            """
            SELECT mcp_tool_name
            FROM kg_entity_tool
            WHERE entity_name = :entity_name
              AND filter_type = :filter_type
            """,
            entity_name=entity_name,
            filter_type=filter_type,
        )
        row = cursor.fetchone()

    if row is None:
        raise KeyError(
            f"No entity tool for ({entity_name!r}, {filter_type!r})"
        )

    return row[0]


# ─────────────────────────────────────────────────────────────────────
# KG edge lookups
# ─────────────────────────────────────────────────────────────────────


def find_edge(from_entity: str, to_entity: str) -> dict[str, Any]:
    """
    Look up the edge connecting two entities in ``kg_edge``.

    Returns a dict with keys:
        edge_name, from_join_field, to_join_field,
        cardinality, server_filter_rule, traversal_hint, notes,
        iter_fields

    ``iter_fields`` is the parsed iter_fields_json column: a
    {tool_arg: parent_field} map for edges whose traversal needs SEVERAL
    parent fields per call (e.g. HAS_DISTRIBUTION needs POHeaderId,
    POLineId and LineLocationId). It is None for every single-field
    edge, which is all of them except HAS_DISTRIBUTION.

    Raises ``KeyError`` if no edge connects from_entity to to_entity.
    Note: edges are directional. find_edge('Supplier', 'PurchaseOrder')
    finds HAS_PURCHASE_ORDER; find_edge('PurchaseOrder', 'Supplier')
    will NOT find it (no reverse edge declared in v1).
    """
    with _kg_cursor() as cursor:
        cursor.execute(
            """
            SELECT edge_name, from_join_field, to_join_field,
                   cardinality, server_filter_rule, traversal_hint, notes,
                   iter_fields_json
            FROM kg_edge
            WHERE from_entity = :from_entity
              AND to_entity   = :to_entity
            """,
            from_entity=from_entity,
            to_entity=to_entity,
        )
        row = cursor.fetchone()

    if row is None:
        raise KeyError(
            f"No edge from {from_entity!r} to {to_entity!r}"
        )

    (
        edge_name,
        from_join_field,
        to_join_field,
        cardinality,
        server_filter_rule,
        traversal_hint,
        notes,
        iter_fields_json,
    ) = row
    return {
        "edge_name": edge_name,
        "from_join_field": from_join_field,
        "to_join_field": to_join_field,
        "cardinality": cardinality,
        "server_filter_rule": server_filter_rule,
        "traversal_hint": traversal_hint,
        "notes": notes,
        "iter_fields": json.loads(iter_fields_json) if iter_fields_json else None,
    }


def find_edge_tool(edge_name: str) -> str | None:
    """
    Find the MCP tool that traverses this edge in ``kg_edge_tool``.

    Returns the tool name string, or ``None`` if the edge has no row
    (e.g. ``HAS_ADDRESS`` is bundled with ``search_suppliers_by_country``
    via ``expand=addresses``; absence of a row is meaningful and signals
    the edge is not independently traversable).

    Examples:
        find_edge_tool('HAS_PURCHASE_ORDER') -> 'search_purchase_orders'
        find_edge_tool('ASSIGNED_TO')        -> 'get_buyer'
        find_edge_tool('HAS_ADDRESS')        -> None
    """
    with _kg_cursor() as cursor:
        cursor.execute(
            """
            SELECT mcp_tool_name
            FROM kg_edge_tool
            WHERE edge_name = :edge_name
            """,
            edge_name=edge_name,
        )
        row = cursor.fetchone()

    if row is None:
        return None

    return row[0]


# ─────────────────────────────────────────────────────────────────────
# KG pattern lookups
# ─────────────────────────────────────────────────────────────────────


def find_pattern_for_filter(
    entity_name: str, filter_type: str
) -> dict[str, Any]:
    """
    Find which pattern handles this filter type on this entity.

    Queries ``kg_pattern_binding``. Returns:
        {
          "pattern_name": <str>,
          "parameter_bindings": <dict parsed from JSON>,
        }

    ``parameter_bindings`` is stored as a JSON string in a CLOB and is
    parsed before return — callers receive a Python dict, not a string.

    Examples:
        find_pattern_for_filter('Supplier', 'country')
          -> {
               "pattern_name": "country_filter_via_address",
               "parameter_bindings": {
                   "parent": "Supplier",
                   "child_edge": "HAS_ADDRESS",
                   "country_term_param": "country",
                 },
             }

    Raises ``KeyError`` if no binding exists for the (entity_name,
    filter_type) pair.
    Raises ``json.JSONDecodeError`` if parameter_bindings is malformed
    (indicates seed-data corruption, not a user error).
    """
    with _kg_cursor() as cursor:
        cursor.execute(
            """
            SELECT pattern_name, parameter_bindings
            FROM kg_pattern_binding
            WHERE entity_name = :entity_name
              AND filter_type = :filter_type
            """,
            entity_name=entity_name,
            filter_type=filter_type,
        )
        row = cursor.fetchone()
        if row is None:
            raise KeyError(
                f"No pattern binding for ({entity_name!r}, {filter_type!r})"
            )
        # Read CLOB while the connection is still open. Sync oracledb's
        # LOB.read() is synchronous (unlike the async driver's AsyncLOB).
        pattern_name, parameter_bindings_raw = row
        parameter_bindings_str = _read_clob(parameter_bindings_raw)

    parameter_bindings = json.loads(parameter_bindings_str)
    return {
        "pattern_name": pattern_name,
        "parameter_bindings": parameter_bindings,
    }


# ─────────────────────────────────────────────────────────────────────
# KG vocabulary lookups
# ─────────────────────────────────────────────────────────────────────


def resolve_vocab(vocab_kind: str, term: str) -> str:
    """
    Resolve a business term to its canonical Fusion code.

    Queries ``kg_vocabulary``. Examples:
        resolve_vocab('country', 'US')        -> 'US'
        resolve_vocab('country', 'USA')       -> 'US'
        resolve_vocab('po_status', 'open')    -> 'OPEN'
        resolve_vocab('po_status', 'active')  -> 'OPEN'

    Raises ``KeyError`` if no matching row exists for the
    (vocab_kind, term) pair. Match is case-insensitive on the term.
    """
    with _kg_cursor() as cursor:
        cursor.execute(
            """
            SELECT canonical_value
            FROM kg_vocabulary
            WHERE vocab_kind = :vocab_kind AND LOWER(term) = LOWER(:term)
            """,
            vocab_kind=vocab_kind,
            term=term,
        )
        row = cursor.fetchone()

    if row is None:
        raise KeyError(f"No vocab for ({vocab_kind!r}, {term!r})")

    return row[0]


# ─────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────


def generate_plan(
    intent: Intent, reference_date: date | None = None
) -> Plan:
    """
    Produce an ordered, executable plan from a structured intent.

    Uses only KG lookups. No LLM. No prose interpretation.

    Three-block flow:

    1. Fetch target entity (with entity-level filter if applicable).
    2. For each filter needing an edge traversal, add an iterating step.
       Some filters (negation-by-absence, e.g. has_no_recent_invoices)
       emit a step whose output is the FILTERED PARENT list, not the
       child list. Such steps carry filter_source_when_empty=True for
       the executor.
    3. For each include, add a lookup step (with dedup on the join field).

    Args:
        intent: The structured intent (validated; unknown filter types
            raise NotImplementedError before any plan work happens).
        reference_date: For testability of date-computing filters
            (e.g. has_no_recent_invoices computes today - N months).
            Defaults to date.today() in production.

    Raises NotImplementedError if any filter in ``intent.filters`` has
    a ``type`` not supported in v1 (silent-drop defect fix — F1).
    """
    # ── Feature 7: aggregation short-circuit ──────────────────────
    # When the intent carries an aggregate block, the question is a
    # ranking/total, not a list. Emit a single non-iterating step that
    # calls the bounded aggregation tool. This bypasses the entity-fetch
    # / edge-traversal / include flow entirely — aggregation owns its
    # own fetch+filter+math inside the tool.
    if intent.aggregate is not None:
        return _build_aggregation_plan(intent.aggregate, intent.filters)
    # ── P6c: comparison short-circuit ─────────────────────────────
    # When the intent carries a compare block, the question is an
    # invoiced-vs-ordered comparison, not a list. Emit a single
    # non-iterating step calling the bounded comparison tool, which owns
    # its own two fetches + join + arithmetic. Checked AFTER aggregate so
    # that if a confused parse sets both, aggregate wins (mirrors the
    # aggregate/count_only precedence).
    if intent.compare is not None:
        return _build_comparison_plan(intent.compare)

    # Validate up front so unknown filter types raise loudly instead
    # of being silently dropped by _filters_needing_edge_traversal.
    _validate_intent_filters(intent.filters, intent.target_entity)

    # Invoice queries require a supplier reference. Without it the fetch
    # would pull every invoice on the pod. Refuse loudly instead.
    if intent.target_entity == "Invoice":
        has_supplier = any(
            f.get("type") in ("supplier", "purchase_order") for f in intent.filters
        )
        if not has_supplier:
            raise ValueError(
                "Invoice queries require a supplier. Name the supplier by "
                "number (e.g. 'invoices for supplier 1252') or by name "
                "(e.g. 'invoices for Lee Supplies')."
            )

    # Address queries require a supplier or a country. Without one the
    # fetch would flatten every supplier's addresses on the pod.
    if intent.target_entity == "Address":
        has_addr_filter = any(
            f.get("type") in ("supplier", "country") for f in intent.filters
        )
        if not has_addr_filter:
            raise ValueError(
                "Address queries require a supplier or a country. For "
                "example 'addresses for supplier 1252' or 'US supplier "
                "addresses'."
            )

    # PurchaseOrder is a valid root only for a single-PO fetch (by_id).
    # It has no unfiltered default fetcher (no (PurchaseOrder,'none') row),
    # so a PO-rooted query without a PO id has nothing to fetch. Refuse
    # cleanly rather than crash. General PO listing is reached via the
    # supplier->PO edge today (and PO aggregates arrive in a later phase).
    if intent.target_entity == "PurchaseOrder":
        # A PO-rooted query needs SOMETHING selective, or the fetch pulls
        # every PO on the pod. A PO id is one such thing; so is a date
        # bound (P6: "POs created before 2015" is bounded and answerable).
        # Same widening as the Invoice guard, which accepts a supplier OR
        # a purchase order.
        has_root_ref = any(
            f.get("type") in ("by_id", "created_before", "created_since")
            for f in intent.filters
        )
        if not has_root_ref:
            raise ValueError(
                "Purchase-order queries require a PO id or a date bound. "
                "For example 'show PO 2144 and its lines', or 'POs created "
                "before 2015'. To list a supplier's POs, ask about the "
                "supplier (e.g. 'open POs for supplier EIP Inc')."
            )

    # ReceivablesInvoice is a valid root only for a single-invoice fetch
    # (by_id on CustomerTransactionId). Like PurchaseOrder it has no
    # unfiltered default fetcher (no (ReceivablesInvoice,'none') row), and
    # the collection holds 173k invoices — a root without an id would scan
    # the whole pod. AR's only root ref is by_id: unlike PO there is no
    # date-bound list filter on this endpoint (BillToCustomerName/Number
    # are not queryable, so customer listing goes via the account path, not
    # here). Refuse cleanly and point at the account path for listing.
    if intent.target_entity == "ReceivablesInvoice":
        has_root_ref = any(
            f.get("type") == "by_id" for f in intent.filters
        )
        if not has_root_ref:
            raise ValueError(
                "AR-invoice queries require a CustomerTransactionId. For "
                "example 'show the AR invoice with CustomerTransactionId "
                "300000248096352 and its lines'. To list a customer's "
                "invoices, ask about the customer account."
            )

    ref_date = reference_date if reference_date is not None else date.today()

    plan: Plan = []
    step_id = 1

    # ── Block 1: entity fetch ─────────────────────────────────────
    # All entity-level filters go to the entity's single default
    # fetcher (kg_entity_tool filter_type='none'), combined into one
    # tool_args dict. This lets filters stack (e.g. active US suppliers
    # named Lee) instead of each needing its own fetcher tool.
    entity_filter_type = _pick_entity_filter(intent.filters, intent.target_entity)
    # Most entity-level filters (status, country, name) deliberately share
    # the ONE default fetcher (filter_type='none') so they can stack. A few
    # filters instead have their OWN dedicated fetcher registered in the KG
    # as a distinct (entity, filter_type) row in kg_entity_tool — e.g.
    # (PurchaseOrder, by_id) -> get_purchase_order_by_id. Prefer that
    # dedicated fetcher when the KG declares one; otherwise use the shared
    # default. This keeps routing KG-driven rather than hardcoded.
    try:
        fetcher_tool = find_entity_tool(
            intent.target_entity, entity_filter_type
        )
    except KeyError:
        fetcher_tool = find_entity_tool(intent.target_entity, "none")
    fetcher_args = _build_entity_fetcher_args(intent.filters, intent.target_entity)

    # Address include on a supplier-rooted query is satisfied by expanding
    # the addresses child on the supplier fetch itself (Path B), NOT by a
    # separate edge-traversal step. Flag it here; Block 3 skips Address so
    # it isn't also fetched as an edge. Concrete Supplier+Address case
    # only — not a general expand mechanism.
    if intent.target_entity == "Supplier" and "Address" in intent.include:
        fetcher_args["include_addresses"] = True

    plan.append(
        Step(
            step_id=step_id,
            tool_name=fetcher_tool,
            tool_args=fetcher_args,
            iterate_over=None,
            client_filters=[],
            output_name=_make_output_name(
                intent.target_entity, entity_filter_type, intent.filters
            ),
            output_dedupe_by=None,
        )
    )
    previous_entity = intent.target_entity
    previous_output_name = plan[-1].output_name
    step_id += 1

    # ── Block 2: edge-traversal filters ───────────────────────────
    for filter_spec in _filters_needing_edge_traversal(intent.filters):
        filter_type = filter_spec["type"]
        target_entity = _filter_target_entity(filter_spec)
        edge = find_edge(previous_entity, target_entity)
        tool = find_edge_tool(edge["edge_name"])
        if tool is None:
            # v1 invariant: any edge used for traversal must have a tool.
            # HAS_ADDRESS doesn't, but no filter type targets Address in v1.
            raise RuntimeError(
                f"Edge {edge['edge_name']!r} has no tool binding; "
                "cannot traverse independently."
            )

        # Decide step shape based on the filter type:
        #
        # - status-style filters (has_open_PO): per-iteration client
        #   filter on the child results; output is the child list.
        #
        # - negation-by-absence filters (has_no_recent_invoices): no
        #   client filter; output is the PARENT items whose per-iteration
        #   call returned empty. filter_source_when_empty=True.
        #
        # - presence-with-value filters (has_invoice_over_amount, Phase
        #   11): the child call carries a value filter (e.g. amount_min);
        #   output is the PARENT items whose per-iteration call returned
        #   something. filter_source_when_nonempty=True.
        filter_source_when_empty = filter_type in _FILTER_SOURCE_NAME_SUFFIX
        filter_source_when_nonempty = (
            filter_type in _FILTER_SOURCE_NONEMPTY_SUFFIX
        )

        if filter_source_when_empty or filter_source_when_nonempty:
            # Build args including computed / value args (e.g.
            # invoice_date_after, amount_min).
            tool_args = _build_iteration_args_with_computed(
                filter_spec, tool, ref_date
            )
            client_filters: list[dict[str, Any]] = []
            output_name = _make_filtered_source_output_name(
                previous_output_name, filter_type
            )
            # Output is parent items, so previous_entity stays as parent.
            new_previous_entity = previous_entity
        else:
            tool_args = {_arg_name_for_tool(tool): "$iteration_value"}
            client_filters = _resolve_client_filters(
                filter_spec, target_entity
            )
            output_name = _make_output_name(target_entity, None, [])
            new_previous_entity = target_entity

        plan.append(
            Step(
                step_id=step_id,
                tool_name=tool,
                tool_args=tool_args,
                iterate_over={
                    "from_step": previous_output_name,
                    "field": edge["from_join_field"],
                },
                client_filters=client_filters,
                output_name=output_name,
                output_dedupe_by=None,
                filter_source_when_empty=filter_source_when_empty,
                filter_source_when_nonempty=filter_source_when_nonempty,
            )
        )
        previous_entity = new_previous_entity
        previous_output_name = plan[-1].output_name
        step_id += 1

    # ── Block 3: includes ─────────────────────────────────────────
    # AR-P5 (prompt 6): a balance-only question wants the account record's
    # own figures, so no child traversal runs — the balance fields ride on
    # the row Block 1 already fetched. The FLAG decides this, not an empty
    # include list: asking the parser to emit an empty include proved
    # unreliable (the LLM dropped the by_customer_name filter along with
    # the include, producing an unroutable filterless intent). Skipping
    # here makes the shape robust to whatever the parser puts in include.
    includes = [] if intent.balance_only else intent.include
    for include_pos, include_entity in enumerate(includes):
        # Address on a supplier query is already handled by expand in
        # Block 1 (include_addresses on the supplier fetch); don't also
        # fetch it as an edge step. There is no HAS_ADDRESS edge tool
        # binding anyway, so this would otherwise raise.
        if intent.target_entity == "Supplier" and include_entity == "Address":
            continue
        edge = find_edge(previous_entity, include_entity)
        tool = find_edge_tool(edge["edge_name"])
        if tool is None:
            raise RuntimeError(
                f"Edge {edge['edge_name']!r} has no tool binding; "
                "cannot satisfy include."
            )
        # Most edges traverse on ONE parent field -> one tool arg. A few
        # need SEVERAL parent fields per call (e.g. HAS_DISTRIBUTION: the
        # nested distributions path needs POHeaderId, POLineId and
        # LineLocationId, all carried on the parent schedule row). Those
        # edges declare an iter_fields map in the KG; emit the multi-field
        # step shape for them. Every other edge (iter_fields is None) emits
        # the original single-field shape unchanged.
        iter_fields = edge.get("iter_fields")
        if iter_fields:
            step_tool_args = {arg: "$iteration_value" for arg in iter_fields}
            step_iterate_over = {
                "from_step": previous_output_name,
                "fields": iter_fields,
            }
        else:
            step_tool_args = {_arg_name_for_tool(tool): "$iteration_value"}
            step_iterate_over = {
                "from_step": previous_output_name,
                "field": edge["from_join_field"],
            }
        # AR-P2c: the CustomerTransaction include supports an open_only
        # modifier — restrict the listed transactions to those with a
        # positive open balance. It rides as a literal tool_arg (the
        # fetcher's native open_only), not a client_filter: the balance
        # test is `> 0`, which the executor's equals-only client filters
        # can't express. Scoped to this entity because open_only is not a
        # universal include arg (cf. the Supplier/Address special-case
        # above).
        if include_entity == "CustomerTransaction" and intent.open_only:
            step_tool_args["open_only"] = True
            # Top-N: cap to the N highest-balance open rows. Gated on
            # open_only too (invoice_limit is only meaningful for the open
            # set, which the fetcher returns balance-desc). Rides as the
            # fetcher's native `limit` arg on this same step.
            if intent.invoice_limit is not None:
                step_tool_args["limit"] = intent.invoice_limit
        # AR-P3: if a FURTHER include follows this one, it will iterate on
        # this step's output — and may need a parent id the child body
        # doesn't carry (tax lines need the invoice's CustomerTransactionId,
        # absent from the line row). Flag this step so the executor stamps
        # its parent field(s) onto each child row. Only when a next include
        # exists, so leaf includes (the common case) are unaffected.
        has_following_include = include_pos < len(includes) - 1
        plan.append(
            Step(
                step_id=step_id,
                tool_name=tool,
                tool_args=step_tool_args,
                iterate_over=step_iterate_over,
                client_filters=[],
                output_name=_make_output_name(include_entity, None, []),
                output_dedupe_by=edge["from_join_field"],
                stamp_parent_key=has_following_include,
            )
        )
        previous_entity = include_entity
        previous_output_name = plan[-1].output_name
        step_id += 1

    return plan


# ─────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────

def _build_aggregation_plan(
    aggregate: dict[str, Any],
    filters: list[dict[str, Any]] | None = None,
) -> Plan:
    """
    Build a single-step plan for an aggregation intent (feature 7).

    The aggregate block names an op (which maps to a bounded aggregation
    tool) plus the tool's parameters (date_from, date_to, top_n). The
    result is one non-iterating Step; the tool does the fetch + math and
    returns a structured ranking, which the executor passes through to
    the synthesizer.

    SCOPED aggregations also take a scope (e.g. "receipt method
    distribution for customer X"), and the parser puts that scope in
    intent.filters, NOT in the aggregate block. So this reads both:
    the aggregate block first, then any filter whose type the op's tool
    accepts. Without the second pass the filter is silently dropped and
    the tool runs pod-wide while the answer still names the customer.

    Raises NotImplementedError if the op has no registered tool — the
    aggregation analog of _validate_intent_filters' unknown-type guard,
    so an unsupported aggregation fails loudly rather than silently.
    """
    op = aggregate.get("op")
    tool = _AGGREGATION_TOOLS.get(op)
    if tool is None:
        raise NotImplementedError(
            f"Aggregation op {op!r} is not supported in v1. "
            f"Supported ops: {sorted(_AGGREGATION_TOOLS)}."
        )

    # Pass through only the recognized tool params, dropping None so the
    # tool's own defaults (e.g. top_n=10) apply when unspecified.
    # Pass through only the params THIS op's tool accepts. Relying on the
    # parser to omit irrelevant params doesn't work: it helpfully sets
    # top_n=10 by default, which then reaches a tool that takes no top_n
    # and raises. The accepted set is per-op because the tools genuinely
    # differ — a status breakdown takes no filter, an open summary takes
    # no top_n.
    accepted = _AGGREGATION_PARAMS.get(op, ())
    tool_args: dict[str, Any] = {}
    for key in accepted:
        if aggregate.get(key) is not None:
            tool_args[key] = aggregate[key]

    # Second pass: merge scoping filters the op's tool accepts. Filter
    # types are named to match the tool's parameter (customer_name,
    # account_number), so the accepted tuple is the whitelist for both
    # sources. The aggregate block wins on conflict — it is the more
    # specific statement of intent.
    for f in filters or []:
        ftype = f.get("type")
        if ftype in accepted and ftype not in tool_args:
            value = f.get("value")
            if value is not None:
                tool_args[ftype] = value

    return [
        Step(
            step_id=1,
            tool_name=tool,
            tool_args=tool_args,
            iterate_over=None,
            client_filters=[],
            output_name="aggregation",
            output_dedupe_by=None,
        )
    ]
    
def _build_comparison_plan(compare: dict[str, Any]) -> Plan:
    """
    Build a single-step plan for a comparison intent (P6c).

    The compare block names an op (which maps to a bounded comparison
    tool) plus the tool's parameters (po_number, or supplier_name+top_n,
    or top_n+status). The result is one non-iterating Step; the tool does
    the two fetches, the join, and the arithmetic, and returns a
    structured comparison the executor passes through to the synthesizer.

    Mirrors _build_aggregation_plan exactly — same one-op-per-tool
    dispatch, same "forward only accepted params" discipline. Raises
    NotImplementedError if the op has no registered tool, so an
    unsupported comparison fails loudly rather than silently.
    """
    op = compare.get("op")
    tool = _COMPARISON_TOOLS.get(op)
    if tool is None:
        raise NotImplementedError(
            f"Comparison op {op!r} is not supported in v1. "
            f"Supported ops: {sorted(_COMPARISON_TOOLS)}."
        )

    # Forward only the params THIS op's tool accepts, dropping None so the
    # tool's own defaults apply. Per-op because the tools genuinely differ
    # — a PO comparison takes a po_number and no top_n; a top-suppliers
    # comparison takes top_n and status and no po_number.
    accepted = _COMPARISON_PARAMS.get(op, ())
    tool_args: dict[str, Any] = {}
    for key in accepted:
        if compare.get(key) is not None:
            tool_args[key] = compare[key]

    return [
        Step(
            step_id=1,
            tool_name=tool,
            tool_args=tool_args,
            iterate_over=None,
            client_filters=[],
            output_name="comparison",
            output_dedupe_by=None,
        )
    ]


def _validate_intent_filters(filters: list[dict[str, Any]], target_entity: str) -> None:
    """Verify every filter in the intent has a known handler for the target entity."""
    entity_level = _entity_level_filter_types().get(target_entity, set())
    edge_filters = _edge_traversal_filters()
    unknown = []
    for f in filters:
        ftype = f.get("type")
        if ftype in entity_level or ftype in edge_filters:
            continue
        # Allow by_id for PurchaseOrder and ReceivablesInvoice even if not in entity_level
        if ftype == "by_id" and target_entity in ("PurchaseOrder", "ReceivablesInvoice"):
            continue
        unknown.append(ftype)
    if unknown:
        raise NotImplementedError(
            f"Intent contains filter types not supported for entity {target_entity!r}: {unknown}. "
            f"Supported entity-level: {sorted(entity_level)}. "
            f"Supported edge-traversal: {sorted(edge_filters)}."
        )


def _pick_entity_filter(filters: list[dict[str, Any]], entity: str) -> str:
    """Return the first entity-level filter type, or 'none'."""
    entity_level = _entity_level_filter_types().get(entity, set())
    for f in filters:
        ftype = f.get("type")
        if ftype in entity_level:
            return ftype
    return "none"

# Filter types whose KG tool_arg_name is a PLACEHOLDER, not a literal arg
# name: the concrete argument depends on the SHAPE of the value. Both the
# Invoice/supplier and Address/supplier KG rows document this routing in
# their notes ("planner routes an all-digit value to supplier_number,
# otherwise supplier_name") but nothing implemented it, so the placeholder
# reached the tool verbatim and Pydantic rejected it.
# v1.2 candidate: make this declarative — a tool_arg_name_alt column on
# kg_entity_filter — rather than a hardcoded special case here. Same note
# as _TOOL_PRIMARY_ARG above.
_VALUE_SHAPE_ROUTED_ARGS: dict[str, tuple[str, str]] = {
    # placeholder -> (arg when all-digit, arg otherwise)
    "supplier": ("supplier_number", "supplier_name"),
}


def _resolve_arg_name(arg_name: str, raw_value: Any) -> str:
    """Resolve a placeholder tool_arg_name against the value's shape.

    Most KG rows name the tool argument literally. A few name a
    placeholder because one filter type maps to two different tool
    arguments depending on whether the user gave an id or a name —
    'invoices for supplier 1252' vs 'invoices for Lee Supplies'.
    Non-placeholder names pass through unchanged.
    """
    routed = _VALUE_SHAPE_ROUTED_ARGS.get(arg_name)
    if routed is None:
        return arg_name
    numeric_arg, name_arg = routed
    return numeric_arg if str(raw_value).strip().isdigit() else name_arg


def _build_entity_fetcher_args(filters: list[dict[str, Any]], entity: str) -> dict[str, Any]:
    """Build tool_args for the entity fetcher."""
    args = {}
    for f in filters:
        ftype = f.get("type")
        try:
            defn = _filter_def_for(ftype, entity)
        except KeyError:
            continue  # not an entity-level filter for this entity
        if defn["mechanism"] != "entity_level":
            continue
        raw_value = f.get("value")
        arg_name = _resolve_arg_name(defn["tool_arg_name"], raw_value)
        arg_name_hi = defn.get("tool_arg_name_hi")
        if isinstance(raw_value, dict):
            low = raw_value.get("from", raw_value.get("min"))
            high = raw_value.get("to", raw_value.get("max"))
            if low is not None:
                args[arg_name] = low
            if high is not None and arg_name_hi:
                args[arg_name_hi] = high
            continue
        vocab_kind = defn.get("vocab_kind")
        if vocab_kind is not None:
            args[arg_name] = resolve_vocab(vocab_kind, raw_value)
        else:
            args[arg_name] = raw_value
    return args


def _filters_needing_edge_traversal(
    filters: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Return the subset of filters not handled by the entity-level fetcher
    and therefore needing a separate edge traversal step.

    Returns filters whose type is an edge-traversal filter (from the KG).
    Entity-level filters (already consumed by Block 1) and unknown
    filter types are excluded.

    Note: this function used to silently drop unknown filter types
    (the v1 defect surfaced in the Design 3 measurement report).
    _validate_intent_filters is now called from generate_plan before
    this function runs, so unknown types raise before reaching here.
    """
    edge_filters = _edge_traversal_filters()
    return [f for f in filters if f.get("type") in edge_filters]


def _filter_target_entity(filter_spec: dict[str, Any]) -> str:
    """
    Given a filter spec, return the entity it constrains.

    Example: {"type": "has_open_PO", ...} -> "PurchaseOrder"

    Raises KeyError if the filter type is unknown to v1.
    """
    filter_type = filter_spec.get("type")
    edge_filters = _edge_traversal_filters()
    if filter_type not in edge_filters:
        raise KeyError(
            f"Filter type {filter_type!r} has no edge-traversal target "
            "in the KG filter table."
        )
    target_entity, _kg_filter_type = edge_filters[filter_type]
    return target_entity


def _resolve_client_filters(
    filter_spec: dict[str, Any], target_entity: str
) -> list[dict[str, Any]]:
    """
    Translate a filter spec into the list of client-side filters to apply
    after the tool call.

    Internally calls ``find_pattern_for_filter``, parses the pattern's
    ``parameter_bindings``, resolves vocab values, and constructs the
    filter list in the ``{field, op, value}`` shape.

    v1 only implements ``status_filter`` here. country_filter_via_address
    is handled by the entity-level fetcher in Block 1.
    no_child_in_N_months is handled via filter_source_when_empty in the
    orchestrator, not via client filters.

    Example: {"type": "has_open_PO", ...} on PurchaseOrder
        -> [{"field": "StatusCode", "op": "equals", "value": "OPEN"}]
    """
    intent_filter_type = filter_spec.get("type")
    edge_filters = _edge_traversal_filters()
    if intent_filter_type not in edge_filters:
        raise KeyError(
            f"Filter type {intent_filter_type!r} is not an edge-traversal "
            "filter and has no client-filter mapping."
        )
    _target_entity, kg_filter_type = edge_filters[intent_filter_type]

    binding = find_pattern_for_filter(target_entity, kg_filter_type)
    pattern_name = binding["pattern_name"]
    bindings = binding["parameter_bindings"]

    if pattern_name == "status_filter":
        # bindings carry: X (entity), status_field, status_term_param.
        field_name = bindings["status_field"]
        vocab_kind, implicit_term = _edge_filter_implicit_values()[intent_filter_type]
        canonical = resolve_vocab(vocab_kind, implicit_term)
        return [{"field": field_name, "op": "equals", "value": canonical}]

    # Other patterns (e.g., country_filter_via_address, no_child_in_N_months)
    # are NOT handled here in v1.1 — they're handled elsewhere in the
    # orchestrator (Block 1 entity fetcher, or filter_source_when_empty
    # respectively). If we get here, the planner is being asked
    # something v1 doesn't cover.
    raise NotImplementedError(
        f"Client-filter construction for pattern {pattern_name!r} "
        "is not implemented in v1."
    )


def _build_iteration_args_with_computed(
    filter_spec: dict[str, Any],
    tool_name: str,
    reference_date: date,
) -> dict[str, Any]:
    """
    Build tool_args for an iterating step whose args include a
    computed value (e.g. invoice_date_after = today - N months).

    The primary iteration key is always set to the iteration sentinel.
    Additional computed args are added based on the filter type.

    For has_no_recent_invoices with value {"months": 6}, returns:
        {"supplier_number": "$iteration_value",
         "invoice_date_after": "2025-11-26"}
    where the date is reference_date minus 6 months.

    v1.1 only handles has_no_recent_invoices. Other computed-arg
    filter types would extend this function.
    """
    intent_filter_type = filter_spec["type"]
    primary_arg = _arg_name_for_tool(tool_name)
    args: dict[str, Any] = {primary_arg: "$iteration_value"}

    if intent_filter_type == "has_no_recent_invoices":
        value = filter_spec.get("value") or {}
        months = value.get("months")
        if not isinstance(months, int) or months <= 0:
            raise ValueError(
                f"has_no_recent_invoices requires value={{'months': <positive int>}}; "
                f"got {filter_spec.get('value')!r}."
            )
        cutoff = _compute_date_n_months_ago(months, reference_date)
        args["invoice_date_after"] = cutoff.isoformat()
        return args

    if intent_filter_type == "has_invoice_over_amount":
        # The threshold rides in as a plain number; route it to the
        # child invoice call's amount_min (Phase 5 filter). A non-empty
        # result means the supplier has an invoice at/over the amount.
        value = filter_spec.get("value")
        amount = value.get("amount") if isinstance(value, dict) else value
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            raise ValueError(
                f"has_invoice_over_amount requires a numeric value "
                f"(the amount threshold); got {filter_spec.get('value')!r}."
            )
        args["amount_min"] = amount
        return args

    if intent_filter_type == "has_site_in_bu":
        # The BU value rides in as the canonical display string (already
        # resolved from supplier_site_bu vocab by the parser). Route it to
        # the child sites call's business_unit arg. A non-empty child
        # result means the supplier has a site in that BU.
        value = filter_spec.get("value")
        bu = value.get("business_unit") if isinstance(value, dict) else value
        if not isinstance(bu, str) or not bu.strip():
            raise ValueError(
                f"has_site_in_bu requires a business-unit string; "
                f"got {filter_spec.get('value')!r}."
            )
        args["business_unit"] = bu
        return args

    if intent_filter_type == "has_classification":
        # The classification value rides in as the canonical display
        # string (already resolved from supplier_classification vocab by
        # the parser). Route it to the child businessClassifications
        # call's classification arg. A non-empty child result means the
        # supplier has a matching classification.
        value = filter_spec.get("value")
        cls = value.get("classification") if isinstance(value, dict) else value
        if not isinstance(cls, str) or not cls.strip():
            raise ValueError(
                f"has_classification requires a classification string; "
                f"got {filter_spec.get('value')!r}."
            )
        args["classification"] = cls
        return args

    # Other filter types with computed args would dispatch here.
    raise NotImplementedError(
        f"Computed iteration args not implemented for filter type "
        f"{intent_filter_type!r}."
    )


def _compute_date_n_months_ago(months: int, reference_date: date) -> date:
    """
    Return reference_date minus ``months`` months.

    Naive month arithmetic — handles month rollover with day clamping.
    Example: 2026-03-31 minus 1 month -> 2026-02-28 (not 2026-02-31).

    Pure function for testability; reference_date defaulting happens
    in the orchestrator, not here.
    """
    year = reference_date.year
    month = reference_date.month - months
    while month <= 0:
        month += 12
        year -= 1
    # Clamp day to last day of target month.
    day = min(reference_date.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    """Return the number of days in the given (year, month)."""
    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    last_day = (next_month_first - _one_day()).day
    return last_day


def _one_day():
    """Return a one-day timedelta. Helper to avoid a top-level import
    when most of this module doesn't need timedelta."""
    from datetime import timedelta
    return timedelta(days=1)


def _arg_name_for_tool(tool_name: str) -> str:
    """
    Return the argument name the given MCP tool expects for its primary
    input.

    Examples:
        search_purchase_orders -> 'supplier_id'
        get_buyer              -> 'buyer_id'
        search_invoices        -> 'supplier_number'

    v1: static dict (_TOOL_PRIMARY_ARG). v2 may want this in the KG.
    Raises KeyError if the tool is not in the table.
    """
    if tool_name not in _TOOL_PRIMARY_ARG:
        raise KeyError(
            f"No primary-arg mapping for tool {tool_name!r}. "
            "Add it to _TOOL_PRIMARY_ARG."
        )
    return _TOOL_PRIMARY_ARG[tool_name]


def _make_output_name(
    entity_name: str,
    filter_type: str | None = None,
    filters: list[dict[str, Any]] | None = None,
) -> str:
    """
    Stable, readable output name for a step's results.

    Examples:
        _make_output_name('Supplier', 'country', [{"type":"country","value":"US"}])
          -> 'us_suppliers'
        _make_output_name('PurchaseOrder')
          -> 'open_pos'    (v1 special-cases PO since the only PO-producing
                            step in the anchor plan is the open-PO traversal)
        _make_output_name('Buyer')
          -> 'buyers'

    Implementation note: the executor doesn't interpret these; pure
    convention. The 'open_pos' special-case matches the anchor-plan
    fixture; v1.1 can derive the prefix from filter context.
    """
    base = _OUTPUT_NAME_BY_ENTITY.get(entity_name, entity_name.lower())

    # Country-filtered entity fetch: prefix with the country code.
    # We need the entity name to look up the vocab kind, but we can just
    # resolve the country value directly – the vocab_kind is always 'country'
    # for this filter, and the value is already normalized by the parser.
    if filter_type == "country" and filters:
        matching = next((f for f in filters if f.get("type") == "country"), None)
        if matching is not None:
            country_value = matching["value"]
            try:
                # Try to canonicalize it if it's not already a code.
                country_value = resolve_vocab('country', country_value)
            except KeyError:
                pass  # Fall back to the raw value.
            return f"{country_value.lower()}_{base}"

    # PurchaseOrder output naming. The anchor plan's PO step always carries
    # the open-PO filter, so its canonical output name is 'open_pos'. P2's
    # single-PO fetch (by_id) is a different shape — name it 'po' so a
    # by-id fetch isn't mislabeled as a list of open POs. Additive: only
    # the by_id path changes; every existing PO plan still yields
    # 'open_pos'.
    if entity_name == "PurchaseOrder":
        if filter_type == "by_id":
            return "po"
        return "open_pos"

    return base


def _make_filtered_source_output_name(
    source_output_name: str, filter_type: str
) -> str:
    """
    Compose the output name for a step that filters its source items by
    iteration-emptiness (filter_source_when_empty) or by iteration
    non-emptiness (filter_source_when_nonempty, Phase 11).

    Example: source='us_suppliers', filter='has_no_recent_invoices'
        -> 'us_suppliers_no_recent_invoices'
    Example: source='suppliers', filter='has_invoice_over_amount'
        -> 'suppliers_has_invoice_over_amount'

    Raises KeyError if filter_type has no suffix in either
    _FILTER_SOURCE_NAME_SUFFIX or _FILTER_SOURCE_NONEMPTY_SUFFIX.
    """
    suffix = _FILTER_SOURCE_NAME_SUFFIX.get(
        filter_type
    ) or _FILTER_SOURCE_NONEMPTY_SUFFIX.get(filter_type)
    if suffix is None:
        raise KeyError(
            f"No filter-source name suffix for {filter_type!r}. Add it to "
            "_FILTER_SOURCE_NAME_SUFFIX or _FILTER_SOURCE_NONEMPTY_SUFFIX."
        )
    return f"{source_output_name}_{suffix}"


def _previous_entity(plan: Plan) -> str:
    """
    Return the entity name that the previous step's output represents.

    NOTE: v1 does NOT use this helper; the orchestrator tracks the
    previous entity as a local variable instead, because Step doesn't
    carry the entity name and reverse-deriving it from output_name is
    brittle. Kept here as a stub so the design-doc contract is visible.

    v1.1 candidate: add an `entity` field to Step and derive this from
    plan[-1].entity.
    """
    raise NotImplementedError(
        "v1 tracks previous entity inline in generate_plan. "
        "This helper exists for design symmetry; do not call it."
    )