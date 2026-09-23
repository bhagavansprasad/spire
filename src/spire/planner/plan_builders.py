"""Plan-building helpers — everything generate_plan delegates to.

generate_plan (in planner.py) is the orchestrator; every function here
does one piece of the work it needs done: building the aggregation or
comparison sub-plan, validating an Intent's filters, resolving which
argument name a tool expects, working out iteration args (including the
computed date filters), and naming a step's output bucket. Kept together
because they are called only from generate_plan and only make sense in
that context — none of them is a public entry point on its own.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from spire.planner.date_utils import (  # noqa: F401
    _compute_date_n_months_ago,
    _days_in_month,
    _one_day,
)
from spire.planner.kg_db import (
    _edge_filter_implicit_values,
    _edge_traversal_filters,
    _entity_level_filter_types,
    _filter_def_for,
)
from spire.planner.lookup import find_pattern_for_filter, resolve_vocab
from spire.planner.models import Plan, Step
from spire.planner.registries import (
    _AGGREGATION_PARAMS,
    _AGGREGATION_TOOLS,
    _SCOPE_FILTER_TO_PARAM,
    _COMPARISON_PARAMS,
    _COMPARISON_TOOLS,
    _FILTER_SOURCE_NAME_SUFFIX,
    _FILTER_SOURCE_NONEMPTY_SUFFIX,
    _OUTPUT_NAME_BY_ENTITY,
    _TOOL_PRIMARY_ARG,
)


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

    # Second pass: merge scoping filters the op's tool accepts. The scope
    # arrives as an intent filter named by_<param> (by_customer_name),
    # while the tool's kwarg is <param> (customer_name), so translate the
    # filter type through _SCOPE_FILTER_TO_PARAM before whitelisting it
    # against `accepted`; a type with no mapping passes through unchanged
    # (identity). Without the translation the by_-prefixed type never
    # matched and the scope was silently dropped — the tool ran pod-wide
    # while the answer still named the customer (finding #7). The aggregate
    # block wins on conflict — it is the more specific statement of intent.
    for f in filters or []:
        ftype = f.get("type")
        param = _SCOPE_FILTER_TO_PARAM.get(ftype, ftype)
        if param in accepted and param not in tool_args:
            value = f.get("value")
            if value is not None:
                tool_args[param] = value

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
    """Verify every filter in the intent has a known handler for the target entity.

    Raises RefusalError(UNSUPPORTED_FILTER) naming the entity and the
    unsupported filter type(s). plan_node routes the wrapped Refusal into
    state["refusal"], so it renders through capability_message — the same
    Reason/Solution/Example shape every other refusal uses — instead of the
    legacy dense "plan: Spire can't filter ..." dump. The user-facing
    wording (the supported filters, an example) comes from
    _FILTER_GUIDANCE[entity] in capability.py; `detail` stays blunt for
    logs and tests, and `offending_filters` carries the rejected types.

    (Previously this raised NotImplementedError with a pre-built dense
    string. plan_node's NotImplementedError branch dumped that string flat,
    bypassing capability_message — the #11 defect. The only caller that
    distinguished the type was plan_node, whose RefusalError branch already
    handles the structured path; the aggregation-op NotImplementedError
    raises elsewhere are unaffected.)

    Called AFTER the entity guards in generate_plan. Those guards give a
    better-aimed message for the cases they cover, and several
    unsupported-filter intents are really missing-root-reference intents
    wearing a different hat: 'show details for invoice number X' parses
    to Invoice + by_id, but what the user needs to hear is "name the
    supplier". Validating first meant the raw filter dump always won.
    This still runs before any plan block, so an unknown filter type can
    never be silently dropped.
    """
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
    if not unknown:
        return

    named = ", ".join(repr(u) for u in unknown)
    # UNSUPPORTED_FILTER: the entity is valid but one of its filters is not.
    # Raise structured so plan_node routes it into state["refusal"] and it
    # renders through capability_message (Reason/Solution/Example, sourced
    # from _FILTER_GUIDANCE[entity]) — the readable shape every other
    # refusal gets, not the legacy dense dump. detail stays blunt for
    # logs/tests; offending_filters names the rejected types. Local import
    # mirrors the entity guards in planner.py and avoids a module-load
    # cycle (result.py imports Intent via planner.planner).
    from spire.nl_parser.result import Refusal, RefusalError, RefusalFlavor

    raise RefusalError(
        Refusal(
            flavor=RefusalFlavor.UNSUPPORTED_FILTER,
            detail=f"{target_entity} cannot be filtered by {named}",
            offending_entity=target_entity,
            offending_filters=[str(u) for u in unknown],
        )
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
    # PurchaseOrder supplier filter. POs expose SupplierId (numeric), NOT
    # SupplierNumber (HTTP 400 if projected) -- so an all-digit value routes
    # to search_purchase_orders' supplier_id, unlike the Invoice/Address
    # 'supplier' placeholder above which routes to supplier_number. Same
    # digit-vs-name shape test, different target args; hence a distinct
    # placeholder token in the PurchaseOrder/supplier KG row (supplier_po).
    "supplier_po": ("supplier_id", "supplier_name"),
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


def _build_entity_fetcher_args(
    filters: list[dict[str, Any]],
    entity: str,
    reference_date: date | None = None,
) -> dict[str, Any]:
    """Build tool_args for the entity fetcher.

    reference_date is threaded in for the two entity-level filters
    whose value is a RELATIVE window (older_than_n_months,
    created_in_last_n_months): the planner computes the ISO cutoff
    via the same _compute_date_n_months_ago helper
    has_no_recent_invoices uses, so tests can pin "today" without
    monkeypatching datetime. Every other filter is unaffected.
    """
    if reference_date is None:
        reference_date = date.today()
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

        # F-011: relative PO-date window. Value is {"months": N};
        # compute the ISO cutoff locally (never the LLM's job) and
        # forward it under the tool arg the KG row names
        # (created_before). Runs BEFORE the generic dict handler,
        # which would otherwise read the wrong keys.
        if ftype in ("older_than_n_months", "created_in_last_n_months"):
            months = (
                raw_value.get("months")
                if isinstance(raw_value, dict) else raw_value
            )
            if (
                not isinstance(months, int)
                or isinstance(months, bool)
                or months <= 0
            ):
                raise ValueError(
                    f"{ftype} requires value="
                    "{'months': <positive int>}; got "
                    f"{raw_value!r}."
                )
            cutoff = _compute_date_n_months_ago(months, reference_date)
            args[arg_name] = cutoff.isoformat()
            continue

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
