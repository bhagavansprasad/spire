"""Planner entry point — generate_plan.

The orchestrator. Everything else in the package (registries, kg_db,
models, lookup, plan_builders) exists to serve this one function: read
an Intent, walk it against the KG, and return a Plan the executor can
run. No LLM in this module or anywhere in the package — planning is a
deterministic KG lookup, never a judgement call (Design 3).

This module re-exports every public and internal name the package used
to define as one file, so no import anywhere else in the repo changes.
Organisation only; no behavioural change is intended by this split.
"""

from __future__ import annotations

from datetime import date

from spire.planner.date_utils import (  # noqa: F401
    _compute_date_n_months_ago,
    _days_in_month,
    _one_day,
)
from spire.planner.kg_db import (  # noqa: F401
    _DEFAULT_DSN,
    _edge_filter_implicit_values,
    _edge_traversal_filters,
    _entity_level_filter_types,
    _filter_def_for,
    _FILTER_DEFS_CACHE,
    _kg_cursor,
    _load_filter_defs,
    _oracle_credentials,
    _read_clob,
)
from spire.planner.models import Intent, Plan, Step  # noqa: F401
from spire.planner.registries import (  # noqa: F401
    _AGGREGATION_PARAMS,
    _AGGREGATION_TOOLS,
    _COMPARISON_PARAMS,
    _COMPARISON_TOOLS,
    _ENTITY_EXAMPLE_PROMPT,
    _FILTER_SOURCE_NAME_SUFFIX,
    _FILTER_SOURCE_NONEMPTY_SUFFIX,
    _OUTPUT_NAME_BY_ENTITY,
    _TOOL_PRIMARY_ARG,
)
from spire.planner.lookup import (  # noqa: F401
    find_edge,
    find_edge_tool,
    find_entity,
    find_entity_tool,
    find_pattern_for_filter,
    resolve_vocab,
)
from spire.planner.plan_builders import (  # noqa: F401
    _arg_name_for_tool,
    _build_aggregation_plan,
    _build_comparison_plan,
    _build_entity_fetcher_args,
    _build_iteration_args_with_computed,
    _filter_target_entity,
    _filters_needing_edge_traversal,
    _make_filtered_source_output_name,
    _make_output_name,
    _pick_entity_filter,
    _previous_entity,
    _resolve_arg_name,
    _resolve_client_filters,
    _validate_intent_filters,
    _VALUE_SHAPE_ROUTED_ARGS,
)


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

    # Invoice queries require a supplier reference. Without it the fetch
    # would pull every invoice on the pod. Refuse loudly instead.
    if intent.target_entity == "Invoice":
        has_supplier = any(
            f.get("type") in ("supplier", "purchase_order") for f in intent.filters
        )
        if not has_supplier:
            # MISSING_IDENTIFIER: the record type is named but not scoped.
            # Structured raise -> plan_node -> state["refusal"] -> the same
            # readable shape a parser decline gets. Words come from
            # _IDENTIFIER_GUIDANCE["Invoice"] in capability.py.
            from spire.nl_parser.result import (
                Refusal,
                RefusalError,
                RefusalFlavor,
            )

            raise RefusalError(
                Refusal(
                    flavor=RefusalFlavor.MISSING_IDENTIFIER,
                    detail="Invoice root has no supplier reference",
                    offending_entity="Invoice",
                )
            )

    # Address queries require a supplier or a country. Without one the
    # fetch would flatten every supplier's addresses on the pod.
    if intent.target_entity == "Address":
        has_addr_filter = any(
            f.get("type") in ("supplier", "country") for f in intent.filters
        )
        if not has_addr_filter:
            # MISSING_IDENTIFIER: needs a supplier or a country to scope.
            # _IDENTIFIER_GUIDANCE["Address"] carries the two-option wording.
            from spire.nl_parser.result import (
                Refusal,
                RefusalError,
                RefusalFlavor,
            )

            raise RefusalError(
                Refusal(
                    flavor=RefusalFlavor.MISSING_IDENTIFIER,
                    detail="Address root has no supplier or country scope",
                    offending_entity="Address",
                )
            )

    # PurchaseOrder roots two ways. A FILTERED PO intent routes onward
    # exactly as before: the KG's PurchaseOrder root filters (by_id,
    # created_before, created_since, lifecycle_status) scope the fetch, and
    # any OTHER filter (status, supplier — not PO entity-level filters) is
    # refused one layer down by _validate_intent_filters with a structured
    # UNSUPPORTED_FILTER naming the rejected filters. This guard must NOT
    # intercept that case — an intent that HAS filters is not "missing an
    # identifier", it has the wrong ones, which is a different refusal.
    #
    # Only a truly FILTER-LESS PO intent is ambiguous, and two very
    # different requests land there identically (filters=[]): an explicit
    # "list purchase orders" (a valid bounded sample-and-disclose, #23) and
    # a PO query whose identifier was dropped ("Is PO N complete?" losing
    # the number, #32). intent.list_all separates them — the parser sets it
    # True (deterministically, from the raw prompt) ONLY for an explicit
    # list request.
    #
    # So: a filter-less PO intent falls through to the bounded
    # (PurchaseOrder,'none') fetcher ONLY when list_all is True. Otherwise
    # refuse MISSING_IDENTIFIER rather than dumping 25 of ~17k unrelated POs
    # (#32 fault b). This is the safety net: even when the parser drops the
    # id, the miss fails safe to a refusal, not a table dump. An explicit
    # list still lists; every filtered PO query still routes through.
    if intent.target_entity == "PurchaseOrder":
        if not intent.filters and not intent.list_all:
            # MISSING_IDENTIFIER: filter-less and not an explicit list.
            # Structured raise -> plan_node -> state["refusal"] -> the
            # readable Reason/Solution/Example shape. Words come from
            # _IDENTIFIER_GUIDANCE["PurchaseOrder"] in capability.py, keyed
            # on the entity below. Local import breaks a module-load cycle
            # (result.py imports Intent via planner.planner).
            from spire.nl_parser.result import (
                Refusal,
                RefusalError,
                RefusalFlavor,
            )

            raise RefusalError(
                Refusal(
                    flavor=RefusalFlavor.MISSING_IDENTIFIER,
                    detail=(
                        "PurchaseOrder root has no identifier and no "
                        "explicit list request"
                    ),
                    offending_entity="PurchaseOrder",
                )
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
            # A ReceivablesInvoice root with no id is a MISSING_IDENTIFIER
            # decline — the user named the record type but not WHICH one.
            # Raise it structured so plan_node routes it into state["refusal"]
            # and it renders through capability_message, the same readable
            # Reason/Solution/Example shape a parser decline gets. The words
            # come from _IDENTIFIER_GUIDANCE["ReceivablesInvoice"] in
            # capability.py (transaction number / CustomerTransactionId, with
            # a worked example), keyed on the entity below — so no message
            # string lives here. detail stays blunt for logs/tests.
            # Local import breaks a module-load cycle: result.py imports
            # Intent via planner.planner, so a top-level result import here
            # would import-cycle. By call time both modules are fully loaded.
            from spire.nl_parser.result import (
                Refusal,
                RefusalError,
                RefusalFlavor,
            )

            raise RefusalError(
                Refusal(
                    flavor=RefusalFlavor.MISSING_IDENTIFIER,
                    detail=(
                        "ReceivablesInvoice root has no identifier; "
                        "by_id on CustomerTransactionId is required"
                    ),
                    offending_entity="ReceivablesInvoice",
                )
            )


    # StandardReceipt has a (none) entity tool — search_standard_receipts —
    # but that tool REFUSES to run unscoped: its first statement raises
    # "At least one of customer_name or customer_site is required." So the
    # KG advertised a fetcher the tool would not honour, and "Get
    # standardReceipts" reached the executor before failing. The user saw
    # a raw tool exception; the planner had every means to say so first.
    #
    # A lag_query filter and a get_receipts_with_lag entity tool were
    # live in the KG database but in NEITHER the seed nor master: the
    # code sits on feature/ar-prompt-18-parking. The KG was advertising
    # a tool the running server does not have, so a lag query planned
    # cleanly and then failed at dispatch. Those rows are gone; when
    # prompt 18 lands it should bring them, and add "lag_query" to the
    # scope list below (it routes to its own tool with its own args).
    if intent.target_entity == "StandardReceipt":
        has_scope = any(
            f.get("type") in ("customer_name", "customer_site")
            for f in intent.filters
        )
        if not has_scope:
            # MISSING_IDENTIFIER: needs a customer or a site to scope.
            # _IDENTIFIER_GUIDANCE["StandardReceipt"] holds the wording.
            from spire.nl_parser.result import (
                Refusal,
                RefusalError,
                RefusalFlavor,
            )

            raise RefusalError(
                Refusal(
                    flavor=RefusalFlavor.MISSING_IDENTIFIER,
                    detail="StandardReceipt root has no customer or site scope",
                    offending_entity="StandardReceipt",
                )
            )

    # Validate AFTER the entity guards. Unknown filter types still raise
    # loudly rather than being silently dropped by
    # _filters_needing_edge_traversal — this runs before every plan block
    # below. But the guards above are better aimed for the cases they
    # cover, and an unsupported-filter intent is often a
    # missing-root-reference intent in disguise.
    _validate_intent_filters(intent.filters, intent.target_entity)

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

