# SPIRE — Findings Log

**Purpose.** Append-only notebook. One entry per finding, as we make it.
This is the lab notebook, not the report. The formal audit —
`phase-1-audit.md` — is updated separately, in batches, when we have
enough to consolidate.

**Finding ID:** `F-NNN`, monotonic. Never reused. Never renumbered.
**Newest at the top.** Append below the header; correct by adding a new
entry, never by editing an old one.

**Entry format** (keep it short — this is a notebook, not prose):

```
## F-NNN — {one-line title}

**Date:** YYYY-MM-DD
**Status:** open · root-caused · fix-in-progress · fixed · closed-as-not-a-bug
**Cross-refs:** bug IDs from phase-1-audit.md

**Evidence.** Commands run and what they printed. Copy-paste, not paraphrase.

**Root cause.** One paragraph. The mechanism, not the symptom.

**Fix location (for Phase 2).** Where the change goes, not the change itself.
The fix is Phase 2's job; this log records where.
```

---

## F-005 — `orderBy=Ordered:desc` silently ignored on `/purchaseOrders`

**Date:** 2026-09-17
**Status:** informational; no fix needed
**Cross-refs:** endpoints reference

**Evidence.**

```
$ curl ... --data-urlencode "orderBy=Ordered:desc" \
    --data-urlencode "fields=OrderNumber,Supplier,Ordered" \
    --data-urlencode "limit=10"
{ "items" : [
  { "OrderNumber" : "162353", "Ordered" : 109999.00 }, ...
```

Returned ascending by OrderNumber, not descending by Ordered. The pod
accepted `orderBy` and ignored it. Same class as the composite-`q=`
silent-fail documented in the endpoints reference.

**Root cause.** Unknown. Not investigated. The pipeline does not use
`orderBy=Ordered`; nothing in SPIRE is affected.

**Fix location.** Documentation only. Add a line to
`docs/spire_fusion_endpoints_reference.md` noting that `orderBy=Ordered:desc`
is not honoured on `/purchaseOrders`, alongside the composite-`q=` note.

---

## F-004 — PO-value ranking misroutes to a comparison; the model answers a superset of the question

**Date:** 2026-09-17
**Status:** root-caused, not fixed
**Cross-refs:** B-20, F-003

**Evidence.**

The prompt:

```
$ python scripts/promptkit.py --run --prompt "top 5 suppliers by purchase order value" --show-stages
Router: modules=['procurement', 'supplier']
Intent:
  target_entity: Supplier
  compare: {'op': 'top_suppliers_invoiced_vs_ordered', 'top_n': 5, ...}
Answer:
  Invoiced vs ordered for the top 5 supplier(s) by PO value:
  - EIP Inc: ordered 865,110,358.23, PO-matched invoiced 710,712.31 —
    under-invoiced by 864,399,645.92 ...
```

The user asked for a ranking of suppliers by PO value. The parser chose a
COMPARISON op (`top_suppliers_invoiced_vs_ordered`), which ranks suppliers
by PO value AND compares each one's ordered against invoiced. A superset
of the question. Every number is correct; the shape of the answer is not.

Numeric verification — the pipeline's EIP Inc total, against curl:

```
$ for off in 0 500 1000 1500 2000; do
    curl ... --data-urlencode "q=SupplierId=300000047507499" \
      --data-urlencode "offset=$off" --data-urlencode "fields=Ordered" \
      | jq '[.items[].Ordered] | add'
  done | paste -sd+ | bc
865110358.2300001
```

Pipeline: 865,110,358.23. Curl: 865,110,358.2300001. Same.

**Root cause.** Same root as F-003, seen from a different angle. The model
had no aggregation op named `po_value_by_supplier` available — that op
lives only in `modes/m_aggregation.sysprompt`, which is dead to a scoped
parse. So it reached for the closest visible thing: `top_suppliers_invoiced_vs_ordered`,
an op in the `DraftCompare` schema. That op does rank suppliers by PO value,
so the answer begins with the number the user wanted — but then extends
into a comparison the user did not ask for.

**Fix location (for Phase 2).** Same edit as F-003:
  - If F-003 is fixed by adding the missing ops to `draft.py`'s
    `DraftAggregate.op`, the model will find `po_value_by_supplier` and
    pick it. The compare block stops being the nearest available thing.
  - Regression test: assert the prompt "top 5 suppliers by purchase order
    value" produces an intent with `aggregate.op == 'po_value_by_supplier'`,
    not a `compare` block.

**Why this is the dangerous class.** B-20 (F-003's other symptom) refused
loudly. F-004 answered confidently with correct numbers for the wrong
question. The audit's "silent wrong answers" class (~5 prompts) is exactly
this. A user who doesn't know the difference between "ranked by PO value"
and "ranked and compared" would accept the answer.

---

## F-003 — three PO aggregation ops unreachable from a scoped parse; the two op registries also disagree

**Date:** 2026-09-17 (revised same day after probe series)
**Status:** root-caused, not fixed
**Cross-refs:** B-20, B-13 (adjacent), F-004

**Evidence — Part 1: structure.**

```
$ grep -n "modes\|_TIER1\|KNOWN_MODULES" src/spire/nl_parser/context_assembly.py
538: _TIER1 = ("core", "refusals")
545: KNOWN_MODULES = ("payables", "procurement", "receivables", "supplier")
656: wanted = set(_TIER1) | set(modules)
```

`modes` is in neither `_TIER1` nor `KNOWN_MODULES`. A scoped parse
(`wanted = {core, refusals, <one of the four Fusion modules>}`) can never
include any `modes/` block. The router can only route to a name in
`KNOWN_MODULES`.

**Evidence — Part 2: probe series.** Five prompts run via promptkit,
`--show-stages`. Two categories.

Category A — rule lives in `draft.py`, the KG menu, or a `DraftIntent`
field (all of which reach the model regardless of scoping). **All four
succeeded:**

| Prompt | Rule needed | Where else the rule lives | Result |
|---|---|---|---|
| `top 10 suppliers by spend in 2022` | `by_supplier` | `draft.py::DraftAggregate.op` | ✓ |
| `count of suppliers` | `count_only` | `DraftIntent` field | ✓ |
| `has PO 701337 been fully received` | `lifecycle_status` | KG filter table | ✓ |
| `account balance for customer ABC Application Software` | `balance_only` | `DraftIntent` field | ✓ |

Category B — rule lives ONLY in `modes/m_aggregation.sysprompt`.
**All three failed:**

| Prompt | Rule needed | Result |
|---|---|---|
| `top 5 suppliers by purchase order value` | `po_value_by_supplier` | misrouted to compare op (F-004) |
| `how many purchase orders are there and what are they worth` | `po_count_by_status` | refused "sum aggregation not supported" |
| `how much have we committed in open purchase orders` | `open_po_summary` | refused "sum aggregation not supported" |

Three of three in Category B. Zero counter-examples.

**Evidence — Part 3: the two registries disagree in both directions.**

| Op | in `draft.py`? | in `modes/m_aggregation`? | Reaches model? |
|---|---|---|---|
| `by_supplier` | ✓ | ✓ | ✓ |
| `exposure_ranking` | ✓ | ✓ | ✓ |
| `receipt_method_distribution` | ✓ | ✓ | ✓ |
| `top_invoices_by_amount` | ✓ | ✗ | ✓ (schema only) |
| `po_value_by_supplier` | ✗ | ✓ | ✗ |
| `po_count_by_status` | ✗ | ✓ | ✗ |
| `open_po_summary` | ✗ | ✓ | ✗ |

The three that are only in `modes/` are the three that fail (Part 2). The
one that is only in `draft.py` — `top_invoices_by_amount` — was probed and
works (Schema only is enough). This is a reverse-drift observation, not a
bug: it is recorded here because it is the same disagreement, and any fix
must close both directions or the next op added to `modes/` alone will
reintroduce F-004.

**Root cause.** The manifest groups `.sysprompt` blocks by folder name.
Blocks under `modes/` have folder `modes`, which is not a Fusion module
name in `KNOWN_MODULES`, so the router never includes them. The model
reads only the KG menu plus `draft.py`'s schema descriptions. Any rule
that lives exclusively in a `modes/*.sysprompt` block is invisible.

This is much narrower than a first-pass reading suggested. Most rules
needed by scoped parses are ALSO declared in the KG or in `draft.py`,
so the modes block's absence is masked. The three that fail are exactly
the ones that need a modes block and have no alternative source.

**Fix location (for Phase 2).** Two design choices; the phase picks one.

  1. Add `modes` (and `columns`) to `_TIER1`, so every scoped parse
     includes them. Then `modes/*` becomes the source of truth for
     aggregation ops, and `draft.py`'s op description is either
     regenerated from it or kept in sync by a test. Cost: every scoped
     parse grows. The modes blocks are small (~2k tokens total).
  2. Leave the router as-is and regenerate `draft.py`'s `DraftAggregate.op`
     and `DraftCompare.op` descriptions from `modes/*.sysprompt`. Then
     `modes/` remains a design document for a full-context fallback, and
     `draft.py` becomes the one live source. Smaller parse input, but
     `modes/` and `draft.py` remain two files that must move together.

**Either way**, both directions of the disagreement must be closed. The
two registries must contain the same set of ops.

**Regression test (for either fix).** Assert every op listed in
`modes/m_aggregation.sysprompt` appears in `draft.py`'s
`DraftAggregate.op` description, and vice versa. The two lists must be
identical.

---

## F-002 — `promptkit.py --run` calls `classify_modules` twice per prompt

**Date:** 2026-09-17 (confirmed same day)
**Status:** confirmed, not fixed
**Cross-refs:** B-09

**Evidence.**

**Runtime — the two calls are visible, and produce different outputs.**

Every `promptkit.py --run --prompt "..."` invocation this session printed
two classify lines before the parse:

```
[llm] provider=gemini model=gemini-3.5-flash
[llm] stage=classify in=545 out=195 total=740
[llm] provider=gemini model=gemini-3.5-flash
[llm] stage=classify in=545 out=93  total=638
Router: modules=['payables']
[llm] stage=parse in=2801 out=309 total=3110
```

Same input (545 tokens), different outputs (195 vs 93). A display
artefact cannot produce different completions from identical input —
these are two real LLM calls.

**Static — two call sites for one prompt.**

`scripts/promptkit.py::_run_one` calls the classifier once, standalone:

```
100:    try:
101:        modules_got = classify_modules(prompt, menu_text=None)
102:    except ClassificationError as exc:
103:        modules_got = f"<classify-error: {exc}>"
```

Then it calls the pipeline:

```
104:    try:
105:        state = await GRAPH.ainvoke({...})
```

And the pipeline's `parse_node` → `route_and_parse` calls the classifier
again:

```
router.py:245:        modules = classify_modules(prompt, llm=llm)
```

`run_graph.py` does **not** have this duplicate. It goes straight to
`GRAPH.ainvoke` with no standalone classify call.

**Root cause.** `promptkit.py` calls `classify_modules` standalone at
line 101 purely to populate the diagnostic `modules_got` field, which
`_stage_report` reads to print which module the classifier chose. The
pipeline then runs its own classification inside `route_and_parse`. One
prompt, two full LLM classify calls.

**Alternatives disproven.**

- *Display artefact.* The two calls produced different outputs (195 vs
  93 tokens) — impossible if one LLM call were being logged twice.
- *Pipeline calls the classifier twice.* `grep` found exactly one call
  site inside the pipeline (`router.py:245`). `run_graph.py` produces
  one classify line per prompt.
- *`run_graph.py` affected too.* It is not — this is unique to
  promptkit.

**Fix location (for Phase 2).** `scripts/promptkit.py::_run_one`. The
standalone `classify_modules` call at line 101 exists only for the
diagnostic. Two ways to remove the duplicate; the choice depends on
whether `_stage_report`'s `modules_got` value is consumed anywhere
besides promptkit's own print — **not investigated.**

  A. Have the pipeline write the classifier's choice into graph state
     (`router.py::route_and_parse` sets a `_modules_got` field, mirroring
     what `_run_one` currently overwrites after the fact), and have
     promptkit read it from there. Touches production code for a
     diagnostic concern.
  B. Remove the standalone call and have promptkit derive the module set
     from the state's `intent` (target_entity) or `refusal` flavor. No
     pipeline change. The derived value is approximate — the intent can
     be correct even when the classifier picked a superset — so the
     diagnostic's fidelity drops.

The fix is a Phase 2 decision, not this log's.

**Why this matters.** Two costs, not one. The obvious one: ~500 input
tokens and ~50–200 output tokens per prompt wasted on the duplicate.
The hidden one: the two calls are non-deterministic and produce different
module sets, so the `_stage_report` module check — the diagnostic
promptkit exists to provide — reports against a *different* classifier
call than the one the pipeline actually used. When the diagnostic says
"module OK", it is checking the standalone call, not the one that
produced the intent.

---

## F-001 — `list_all` is declared, read, and never written; every filter-less PO query refuses

**Date:** 2026-09-17
**Status:** root-caused, not fixed
**Cross-refs:** B-13, D-07

**Evidence.**

Static — three greps:

```
$ grep -rn "list_all" src/spire/
src/spire/planner/models.py:141:    list_all: bool = False
src/spire/planner/planner.py:188:    # the number, #32). intent.list_all separates them — the parser sets it
src/spire/planner/planner.py:193:    # (PurchaseOrder,'none') fetcher ONLY when list_all is True. Otherwise
src/spire/planner/planner.py:199:        if not intent.filters and not intent.list_all:
```

```
$ grep -n "_is_explicit_po_list" src/spire/nl_parser/parser.py
120:def _is_explicit_po_list(prompt: str) -> bool:
```

The only hit is the `def`. No caller anywhere.

Runtime — two prompts, both should answer:

```
$ python scripts/promptkit.py --run --prompt "list purchase orders" --show-stages
Reason:   I can look up purchase orders, but this doesn't say which one.
Solution: Give me the PO number.
(refusal: missing_identifier — PurchaseOrder root has no identifier and no explicit list request)

$ python scripts/promptkit.py --run --prompt "list all purchase orders" --show-stages
Reason:   I can look up purchase orders, but this doesn't say which one.
Solution: Give me the PO number.
(refusal: missing_identifier — PurchaseOrder root has no identifier and no explicit list request)
```

The refusal's own reason string says "no explicit list request" — while the
user has explicitly requested a list. The signal that would set the flag
exists; nothing calls it.

**Root cause.** A three-part design that landed two parts.

`models.py::Intent.list_all` was added as the flag that distinguishes an
explicit "list POs" request (a valid bounded sample-and-disclose, fix #23)
from a PO query whose identifier the parser dropped (`Is PO N complete?`
losing the number, fix #32 fault b). `planner.py::generate_plan` reads it
and refuses when the flag is False on a filter-less PO intent.
`parser.py::_is_explicit_po_list(prompt)` is the deterministic function
that computes the flag from the raw prompt — its own comment describes the
exact bug it exists to fix. It has no caller. So `list_all` is always
False, and the planner's guard always fires.

Every filter-less PO prompt refuses. Not just the two tested — any
phrasing that would have produced a filter-less PurchaseOrder intent.

**Fix location (for Phase 2).** Two places:
  - `src/spire/nl_parser/parser.py::parse()` — after the draft is
    converted to an Intent, call `_is_explicit_po_list(prompt)` and assign
    the result to `intent.list_all`. This is the deterministic
    post-parse pattern already used for `expand_field_synonyms`,
    `correct_include_from_prompt`, and `strip_po_supplier_include`.
  - `src/spire/nl_parser/draft.py::DraftIntent.to_intent()` — no change
    required; the flag is not an LLM concern.
  - Regression test: assert `_is_explicit_po_list` is called from
    `parse()`; assert a filter-less PO intent with a list phrasing reaches
    the planner with `list_all=True`; assert the planner's refusal does
    *not* fire.

**Note.** Same failure class as A-01 (Doc A said "4 imports", there were
8) and D-12 (two messages for one input): **a claim written into the
codebase that the code does not honour.** The comment in `planner.py:188`
is the strongest example in the audit so far. Reading it, you would
believe the fix is live.

---

*End of findings log.*