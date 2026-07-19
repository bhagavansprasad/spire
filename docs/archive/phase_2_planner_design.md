# Phase 2 Planner Design

> **Status:** Design only. Implementation pending.
> **Purpose:** Capture the verified design decisions from Phase 2 step 0 (2a, 2b, 2c) before writing the planner code.
> **Companion file:** `src/spire/planner/planner.py` — Python stubs that mirror this design.

---

## Context

The Spire POC tests whether a Knowledge Graph (KG) can drive deterministic tool selection for an agent that queries Oracle Fusion via MCP-wrapped REST endpoints. The architecture is **Option 3** (locked in earlier):

```
Prompt
  → LLM (Intent Parser)
  → Knowledge Graph (Planner)         ← this phase's work
  → MCP (Executor)                    ← Phase 3
  → Tools → Fusion Endpoints → Data
  → LLM (Response Synthesizer)
  → Output
```

The planner sits between the LLM's intent parsing and the MCP executor. It reads only from the KG (Items 1–8 already in master) and emits a structured plan. **No LLM in the planning step.** No prose-reading for decisions.

---

## Verified design decisions (Phase 2 step 0)

| Decision | Choice | Verified by |
|---|---|---|
| Language | Python (oracledb 4.0.0) | 2a — connection test against the KG |
| Plan representation | Structured Python data (list of dataclasses / dicts) | 2b — full plan for the anchor question expressed with zero prose |
| Code organization | Composed small functions, one per KG concept; thin orchestrator | 2c — orchestrator traces cleanly through the anchor question |

---

## The anchor question

All design choices were validated against:

> *"Show me suppliers in US with open purchase orders, including the buyer assigned to each."*

The LLM parses this into structured intent:

```python
Intent(
    target_entity="Supplier",
    filters=[
        {"type": "country", "value": "US"},
        {"type": "has_open_PO", "value": True},
    ],
    include=["Buyer"],
)
```

---

## Plan data structure (2b)

A plan is a **list of Steps**. Each Step is a dataclass with these fields:

| Field | Type | Purpose |
|---|---|---|
| `step_id` | `int` | Execution order |
| `tool_name` | `str` | Which MCP tool to invoke (resolved from `kg_entity_tool` or `kg_edge_tool`) |
| `tool_args` | `dict` | Arguments for the tool; values are either literals or the special token `"$iteration_value"` |
| `iterate_over` | `dict \| None` | `{"from_step": <output_name>, "field": <field_name>}` when the step iterates over previous output; `None` otherwise |
| `client_filters` | `list[dict]` | Python-side filters applied to results (`server_filter_rule = 'join_only'` for all current edges, so non-join filters go here) |
| `output_name` | `str` | Stable name for this step's output, referenced by later steps |
| `output_dedupe_by` | `str \| None` | Field to deduplicate output items on; `None` = no dedup |

### Cross-step references

Iteration sources use a dict:

```python
{"from_step": "us_suppliers", "field": "SupplierId"}
```

Within `tool_args`, the literal string `"$iteration_value"` means *"substitute the current iteration's value here."* This avoids the redundancy of repeating the source reference inside `tool_args`.

### Client filter shape

```python
{"field": "StatusCode", "op": "equals", "value": "OPEN"}
```

Operators supported in v1: `equals`, `any_child_equals` (for `expand=addresses` style nested matching).

### Worked example — the anchor question

```python
plan = [
    Step(
        step_id=1,
        tool_name="search_suppliers_by_country",
        tool_args={"country": "US"},
        iterate_over=None,
        client_filters=[],
        output_name="us_suppliers",
        output_dedupe_by=None,
    ),
    Step(
        step_id=2,
        tool_name="search_purchase_orders",
        tool_args={"supplier_id": "$iteration_value"},
        iterate_over={"from_step": "us_suppliers", "field": "SupplierId"},
        client_filters=[
            {"field": "StatusCode", "op": "equals", "value": "OPEN"},
        ],
        output_name="open_pos",
        output_dedupe_by=None,
    ),
    Step(
        step_id=3,
        tool_name="get_buyer",
        tool_args={"buyer_id": "$iteration_value"},
        iterate_over={"from_step": "open_pos", "field": "BuyerId"},
        client_filters=[],
        output_name="buyers",
        output_dedupe_by="BuyerId",
    ),
]
```

### Kill-point check for 2b

Every decision the executor needs is encoded as data:
- ✅ Tool to call (`tool_name`)
- ✅ Arguments (`tool_args`)
- ✅ Iteration source (`iterate_over`)
- ✅ Filters applied after each call (`client_filters`)
- ✅ Result naming and deduplication (`output_name`, `output_dedupe_by`)

No prose. No "and obviously the executor would just know…"

---

## Function organization (2c)

The planner is organized as **small functions, one per KG concept**, with a thin orchestrator. Each function performs one KG query and returns parsed structured data.

### Small functions — one per KG lookup

| Function | KG table queried | Returns |
|---|---|---|
| `find_entity(entity_name)` | `kg_entity` | endpoint_path, canonical_id_field, display_name_field |
| `find_entity_tool(entity_name, filter_type)` | `kg_entity_tool` | MCP tool name |
| `find_edge(from_entity, to_entity)` | `kg_edge` | edge_name, join fields, server_filter_rule |
| `find_edge_tool(edge_name)` | `kg_edge_tool` | MCP tool name, or `None` if not independently traversable |
| `find_pattern_for_filter(entity_name, filter_type)` | `kg_pattern_binding` | pattern_name, parameter_bindings |
| `resolve_vocab(vocab_kind, term)` | `kg_vocabulary` | canonical Fusion code |

Each is independently testable — mock the DB connection, supply a fixture row, assert the parsed result.

### The orchestrator

```python
def generate_plan(intent: Intent) -> Plan:
    plan = []
    step_counter = 1

    # Step 1: Fetch the target entity (with any entity-level filter
    #         that has a dedicated fetcher tool)
    entity_filter = _pick_entity_filter(intent.filters)
    fetcher_tool = find_entity_tool(intent.target_entity, entity_filter)
    fetcher_args = _build_fetcher_args(entity_filter, intent.filters)
    plan.append(Step(step_id=step_counter, tool_name=fetcher_tool, ...))
    previous_output = plan[-1].output_name
    step_counter += 1

    # Steps 2..N: For each filter that needs an edge traversal,
    #             add an iterating step
    for filter_spec in _filters_needing_edge_traversal(intent.filters):
        target = _filter_target_entity(filter_spec)
        edge = find_edge(intent.target_entity, target)
        tool = find_edge_tool(edge["edge_name"])
        client_filters = _resolve_client_filters(filter_spec, target)
        plan.append(Step(
            step_id=step_counter,
            tool_name=tool,
            tool_args={_arg_name_for_tool(tool): "$iteration_value"},
            iterate_over={"from_step": previous_output, "field": edge["from_join_field"]},
            client_filters=client_filters,
            ...
        ))
        previous_output = plan[-1].output_name
        step_counter += 1

    # Steps N+1..: For each include, add a lookup step
    for include_entity in intent.include:
        edge = find_edge(_previous_entity(plan), include_entity)
        tool = find_edge_tool(edge["edge_name"])
        plan.append(Step(
            step_id=step_counter,
            tool_name=tool,
            tool_args={_arg_name_for_tool(tool): "$iteration_value"},
            iterate_over={"from_step": previous_output, "field": edge["from_join_field"]},
            output_dedupe_by=edge["from_join_field"],
            ...
        ))
        step_counter += 1

    return plan
```

### Helper functions (private)

These absorb the non-trivial logic that would otherwise clutter the orchestrator:

| Helper | Job |
|---|---|
| `_pick_entity_filter(filters)` | Decide which filter (if any) has a dedicated entity-level fetcher tool |
| `_build_fetcher_args(filter_type, filters)` | Resolve vocab values into tool arguments |
| `_filters_needing_edge_traversal(filters)` | Identify filters that require an edge hop (not handled by the entity-level fetcher) |
| `_filter_target_entity(filter_spec)` | Which entity does this filter constrain? |
| `_resolve_client_filters(filter_spec, target)` | Look up pattern + bindings, resolve vocab, build filter list |
| `_arg_name_for_tool(tool_name)` | What argument name does the MCP tool expect? |
| `_make_output_name(entity_name)` | Stable, readable output name for a step |
| `_previous_entity(plan)` | What entity did the previous step's output represent? |

### Kill-point check for 2c

- ✅ Orchestrator reads top-to-bottom; three clear blocks (entity fetch, filter loops, include loops); deepest nesting is one `for` loop
- ✅ Each KG concept = one function call in the orchestrator
- ✅ Tracing the anchor question through the orchestrator produces the 2b plan
- ✅ `_resolve_client_filters` accepted as a clean abstraction (orchestrator doesn't need to see how client filters are built)

---

## Known limitations of this design (v1)

Worth being explicit about, so future-you doesn't assume they're handled:

1. **Three-block orchestrator generalizes for the anchor question's *shape*, but not all shapes.** Questions with no filters but multiple includes, or filters needing multi-edge traversals, would require additional orchestrator logic. Acceptable for v1 (the POC's goal is to prove the mechanism, not to cover every question shape).

2. **No conditional steps** (e.g., "if step N returns empty, skip step N+1"). Anchor question doesn't need them.

3. **No parallelism.** Step execution is sequential. The executor in Phase 3 could parallelize iteration calls, but the plan doesn't mandate or describe that.

4. **No error / retry / fallback in the plan.** These are executor concerns.

5. **Operator set in `client_filters` is minimal** — `equals`, `any_child_equals`. Sufficient for the anchor question.

---

## What this design does NOT include

To preempt confusion when implementing:

- **The LLM intent parser** — produces `Intent`. Out of scope for this phase.
- **The MCP executor** — consumes a `Plan` and runs it. Phase 3 work.
- **The response synthesizer** — converts step outputs into a natural-language answer. Out of scope.
- **Connection pooling, retries, transaction management** — implementation concerns not visible in the design.

---

## Implementation order (next phase)

1. Implement the six small KG-query functions, each with unit tests against fixtures
2. Implement the helpers
3. Implement the orchestrator
4. Test end-to-end against the anchor question; compare emitted plan against the worked example above
5. Hand off the plan to Phase 3's executor
