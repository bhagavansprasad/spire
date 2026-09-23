"""Planner data types: Intent, Step, and the Plan alias.

Intent is the parser's output and the planner's input. Step is the
planner's output, one per fetch/iterate/filter action the executor will
perform; Plan is just list[Step]. Pure dataclasses, no dependency on any
other planner module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    # COL-03 (partial column resolution): columns the user named that the
    # entity does NOT have. Populated by validate_intent (Step 4), which
    # splits the parser's raw column list — valid names stay in `fields`,
    # unknown ones move here — instead of refusing the whole query. The
    # planner and executor IGNORE this field entirely; it rides through to
    # display, which prints a note naming these columns and offering the
    # entity's available columns, above the projected table. Empty means
    # every requested column resolved (or none were requested).
    #
    # WHY A SEPARATE LIST AND NOT AN em-dash COLUMN: an absent field
    # printed as a dashed column cannot be told apart from a real field
    # that is simply null on every row. Carrying the unresolved names as
    # data lets display disclose them explicitly — the silent-drop defect
    # (a clean table with a requested column quietly missing) is exactly
    # what COL-03 exists to remove. Substitution is NOT performed: a
    # near-match is never guessed in place of an unknown column.
    unresolved_fields: list[str] = field(default_factory=list)
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

    # #32 fault (b): True only when the user explicitly asked to LIST/show
    # all purchase orders ("list purchase orders", "show all POs") — a
    # genuine bounded sample-and-disclose (#23). The parser sets it ONLY on
    # that wording. generate_plan uses it to tell an explicit PO list apart
    # from a PO query whose identifier the parser dropped ("Is PO N
    # complete?" losing the number): both arrive as a filter-less
    # PurchaseOrder intent, but only the explicit list should list — the
    # dropped-identifier case must refuse, not dump 25 of ~17k unrelated
    # POs. Defaults False so the SAFE direction (refuse when unscoped and
    # not an explicit list) is the default. Consumed only in generate_plan.
    list_all: bool = False

    # F-016: a plain-list row cap extracted from the raw prompt ("top 5
    # recent credit memos", "first 10 suppliers"). Distinct from
    # `invoice_limit` (open-invoices only) and `aggregate['top_n']`
    # (aggregation only). The parser computes it deterministically
    # post-LLM (see parser.py::_extract_list_cap) and the planner injects
    # `limit=N` into the entity fetcher's tool_args — but ONLY for the
    # fetchers whose signatures accept a `limit` argument (the set lives
    # in registries._LIMIT_CAPABLE_TOOLS). Tools that take no limit are
    # unaffected, so an intent carrying a cap for a non-list fetch is a
    # no-op at plan time rather than a crash. Default None (no cap) so
    # every existing intent behaves unchanged.
    list_limit: int | None = None


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
