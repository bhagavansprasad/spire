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

**Update 2026-09-19 — scope expanded to two layers.**

Working the fix revealed the failure is not one layer but two. The Router:
line for every failing prompt shows `modules=['payables']` — the receivables
sysprompt blocks are never loaded. The classifier menu (generated from
`kg_vocabulary WHERE vocab_kind = 'entity_synonym'`) carries ZERO synonyms
for the three AR children:

    receivables:
      ReceivablesInvoiceLine               ← no aka
      ReceivablesInvoiceTransactionDFF     ← no aka
      ReceivablesTaxLine                   ← no aka

So the classifier sees only `invoice` (which maps to the payables `Invoice`)
and never routes to receivables. Even a perfect parser rule would never run.

Two layers, both required for the same user outcome:

1. **Router.** Add `entity_synonym` rows in `scripts/sql/kg_schema.sql` for
   `invoice line(s)`, `tax line(s)`, `DFF`, `flexfield`, `descriptive
   flexfield`, mapped to the correct receivables entities. Then
   `rebuild_kg.py` and `build_classifier_context.py`.
2. **Parser.** The three AR sysprompt edits (previously the whole of
   F-041's fix location).

The two layers are one fix; neither half alone solves the user's problem.

---

## F-044 — double-encoded `value_json` crashes the tool at schema validation (intermittent)

**Date:** 2026-09-22
**Status:** verified (PR #158, 2026-09-22)
**Cross-refs:** F-006 (same class — a value shape the tool's schema rejects), F-012 (the L2 run that surfaced it)

**Evidence.**

Surfaced during the L2 prompt-set run for F-012 + F-036
(`scripts/prompts/14_truncation_narration.txt`, prompt 3 of 14). Prompt:

    invoices for supplier 1252 above 50000

Failed intermittently with:

    ERROR: execute: 1 validation error for call[search_invoices]
    amount_min
      Input should be a valid number, unable to parse string as a number [type=float_parsing, input_value='{"min": 50000}', input_type=str]
        For further information visit https://errors.pydantic.dev/2.13/v/float_parsing

The value that reached the tool's `amount_min` was the JSON-string
`'{"min": 50000}'`, not the number `50000`. The tool correctly refused
a value it never should have received.

**Diagnostic run (2026-09-22 14:46, 9 prompts, captured to
`docs/phase-2/fixes/F-044-diag.txt`).** The failure is intermittent
and threshold-independent:

    A-RUN-1  "invoices for supplier 1252 above 50000"  PASS
    A-RUN-2  same                                        PASS
    B-20000  "invoices for supplier 1252 above 20000"  PASS
    B-30000  same                                        PASS
    B-40000  same                                        PASS
    B-60000  same                                        PASS
    B-100000 "invoices for supplier 1252 above 100000" FAIL  input_value='{"min":100000}'
    C-1      "suppliers with invoices over 50000"      PASS  (different filter, different code path)
    C-2      "suppliers with an invoice over 50000"    PASS

Eight of nine pass; two different thresholds failed in two different
sessions on the same phrasing. The failure rate on the affected
phrasing was approximately 1 in 6.

**Root cause — established.**

The chain, cited by `file:line`:

1. The model intermittently double-encodes an object-valued
   `value_json`: instead of emitting the object text
   `{"min": 50000}`, it emits a JSON-string whose content is that
   object text, i.e. `"{\"min\": 50000}"`.
2. `src/spire/nl_parser/draft.py::to_intent` line 400 —
   `value: Any = json.loads(f.value_json)`. Double-encoded input
   parses successfully at this call; it simply yields a **string**.
   The surrounding `try/except (json.JSONDecodeError, TypeError)`
   catches only unparseable input, and this case never hits it.
3. `src/spire/planner/plan_builders.py::_build_entity_fetcher_args`
   line 290 — `if isinstance(raw_value, dict):`. `raw_value` is a
   string, so this branch is skipped.
4. Same function, line 302 — `args[arg_name] = raw_value`. The
   string is passed through unchanged as `amount_min`.
5. The MCP boundary: `search_invoices(amount_min: float)` rejects
   the string at Pydantic input validation, before the tool body
   runs. Crash.

**S4 — alternatives disproved.** The only alternative worth naming
was "the planner stringifies a dict". Disproved by two observations:

- On the seven passing runs, `_build_entity_fetcher_args` produces
  `{'amount_min': 50000}` (an int) — it does not call `str()` on a
  dict; it passes `raw_value` through verbatim.
- The failed run's `input_value` is `'{"min": 50000}'` — a string
  whose content is JSON object text, exactly what one `json.loads`
  of a double-encoded value yields. A `str()`-of-dict would be
  `"{'min': 50000}"` (single quotes, Python repr spacing).
  Different shape; not what we see.

So the fault is upstream of the planner: the model double-encodes,
and `draft.py:400` decodes once when it should decode twice.

**Fix location (Phase 2 — shipped on
`phase-2-fix-F044-double-encoded-value`).**

`src/spire/nl_parser/draft.py::to_intent`, immediately after the
existing `json.loads`:

    if isinstance(value, str) and value[:1] == "{":
        try:
            inner = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            pass
        else:
            if isinstance(inner, dict):
                value = inner

The guard is a first-character test, so genuine string values
(`"US"`, `"50000"`, prose) are untouched, and strings that start
with `{` but do not parse leave the original value in place — the
same leniency as the outer try/except. A defensive re-parse in
`plan_builders.py:290` was considered and left out: there is no
second entry point to the planner that bypasses `to_intent`, so the
extra branch would have no reproducer.

**Verification.** See `docs/phase-2/fixes/F-044.md`. Key numbers:
8 unit tests (3 fail without the fix, 5 regression guards), full
suite 1062 passed, 20-run N>=20 on the reproducer shows 20/20 pass
with zero errors, and the same on the paraphrase. V0–V8 passed; V9
not applicable (no `.sysprompt` touched).

**Not checked.** Whether the same double-encoding affects other
JSON-shaped draft values on other filters. Whether a list-shaped
value has the same defect (current guard accepts only dicts).
Whether the double-encoding rate varies by prompt length or entity.
Whether a sysprompt-side change would further reduce the rate.

**Class note.** Same class as F-006 (a value shape the tool's input
schema rejects). F-006's was a wrapper type annotation; this is the
value's own encoding. Both would be caught by a two-layer regression:
the parser unit test plus the tool's Pydantic schema. Recorded here
because the F-012/F-036 L2 pass surfaced it and the finding went from
candidate to root-caused within the same session.

**Merged 2026-09-22 as PR #158** (`de5da26`). Full V0–V8 in
`docs/phase-2/fixes/F-044.md`. Suite at merge: 1062 passed, 22
deselected. No golden was affected.

---

## F-043 — Site and Classification includes refuse; both tools were reverse-only and a hardcoded Site gate blocked the include path

**Date:** 2026-09-19
**Status:** verified (PR #152, 2026-09-19)
**Cross-refs:** F-025 (sibling design decision — PO cannot reach Supplier children), F-042 (same branch)

**Evidence.**

Discovered during the same Phase 2 sweep as F-042. The prompts
`show sites for supplier EIP Inc` (and four variants) and
`show classifications for supplier EIP Inc` (and four variants) refuse
in `scripts/prompts/13_child_as_root.txt`.

    $ python scripts/promptkit.py --run --prompt "show sites for supplier EIP Inc"
    Reason:   Supplier sites aren't available as a standalone listing.
      (refusal: unsupported_operation — Supplier sites aren't available as a standalone listing.)

    $ python scripts/promptkit.py --run --prompt "show classifications for supplier EIP Inc"
    Reason:   Classification is not available as an include on Supplier.
      (refusal: unsupported_operation — Classification is not available as an include on Supplier.)

Two mechanisms, stacked:

1. `intent_validation.py` had a hardcoded refusal for any intent with
   `include=['Site']` — "Supplier sites aren't available as a standalone
   listing" — with `offending_entity='SupplierSiteListing'`.
2. `_NON_INCLUDABLE_ENTITIES = frozenset({"Site", "Classification"})`
   caused the general include gate to refuse Classification includes
   as well.

Both refusals were honest given the tools' shape:
`search_suppliers_by_site_bu` and `search_suppliers_by_classification`
took the BU / classification as a **required** argument, so the only way
to use them was as a reverse filter — "find suppliers BY a
site/classification". A forward include had no tool to call.

**Root cause.**

The two reverse-only tools were also the natural forward tools; they
just required the wrong argument shape. The Site gate and the
`_NON_INCLUDABLE_ENTITIES` entry were both downstream of that
constraint. Making the child filter argument optional (return all
children when omitted) turned both tools dual-purpose and made both
includes valid — no new tool, no new edge, no new KG row.

**Fix location (Phase 2 — shipped).**

Eleven files, one branch, one commit:

- `src/spire/mcp_server/server.py` — `business_unit` / `classification`
  optional on the two MCP tool wrappers.
- `src/spire/mcp_server/tools/supplier_sites.py` — optional filter;
  stamps `SupplierId` on each row so the synthesizer can join.
- `src/spire/mcp_server/tools/supplier_classifications.py` — same shape.
- `src/spire/nl_parser/intent_validation.py` — hardcoded Site gate
  deleted; `_NON_INCLUDABLE_ENTITIES` emptied; the general include gate
  now validates Site and Classification against the KG edge graph like
  any other include.
- `src/spire/nl_parser/vocabulary.py` — `Site` and `Classification`
  added to `_CHILD_INCLUDE_WHEN_PRESENT` with multi-word triggers
  (`"sites for"`, `"'s sites"`, etc.) so the include rule fires on the
  include phrasing and does not collide with the filter phrasing.
- `src/spire/nl_parser/context/supplier/b_classification.sysprompt`
  and `b_site_in_bu.sysprompt` — leading "X for supplier NAME" rules
  added.
- `src/spire/nl_parser/context_assembly.py` — the inline copies of
  those two rules extended.
- `src/spire/nl_parser/capability.py` — the dead `SupplierSiteListing`
  entries (fallback example, operation solution) retired; the
  internal-marker comment rewritten.
- `src/spire/synthesizer/p2p.py` — `SiteInfo` and `ClassificationInfo`
  models; `sites` and `classifications` fields on `SupplierRecord`;
  `_supplier_with_sites` / `_supplier_with_classifications` shape
  detectors; `build_suppliers_with_sites` /
  `build_suppliers_with_classifications` builders — parallel to the
  existing `_supplier_with_contacts` path.
- `src/spire/synthesizer/synthesizer.py` — the two local dispatch
  branches, before the LLM fallback.
- `src/spire/rendering/formatters.py` — the two indented sub-tables.
- `tests/test_bug2_include_gate.py` — the two tests that asserted Site
  and Classification includes were refused are flipped to assert
  they pass. Full suite 1028 passed.

**Verification.**

- All six F-043 prompts answer: 22 sites / 3 classifications per supplier.
- `pytest -q`: 1028 passed, 0 failed, 22 deselected.
- Full sweep `13_child_as_root.txt`: 64/64 clean; the 10 previously-
  refused prompts (4 address, 3 site, 3 classification) now answer.
- Site include renders the new `EIP Inc — sites:` sub-table.
- Classification include renders the new
  `EIP Inc — classifications:` sub-table.

**Not checked.**

- Whether the same dual-purpose pattern generalises to other
  reverse-only edges. `HAS_SITE` and `HAS_CLASSIFICATION` were the only
  two remaining in the KG's reverse-only set; the sweep found no
  others.
- Whether the parser prompt's token ceiling was approached by the two
  sysprompt additions. Sweep passed clean; a targeted `--validate` on
  the full 12-set corpus is warranted per the handoff's caveat but was
  not run this session.

---

## F-042 — supplier-address phrasings refuse; collapses into F-009 (block in wrong module, unreachable from a supplier-scoped parse)

**Date:** 2026-09-19
**Status:** closed-as-duplicate (F-009)
**Cross-refs:** F-009 (the same bug), F-041 (same fix pattern)

**Evidence.**

Filed during the Phase 2 child-as-root sweep. Four prompts were
observed to refuse in `scripts/prompts/13_child_as_root.txt`.
Initial hypothesis: a leading verb ("show", "list", "what") breaks the
parse. The probe below disproves that. All four phrasings refuse —
including bare `addresses for supplier 1252`, which the audit cited as
working. It is not.

    $ python scripts/promptkit.py --run --prompt "addresses for supplier 1252"
    Router: modules=['supplier']
    Reason:   Filtering suppliers by supplier number is not supported; only
              name-based filters are available.

    $ python scripts/promptkit.py --run --prompt "Addresses for supplier 1252"
    Router: modules=['supplier']
    Reason:   Supplier number is not supported as a filter.

    $ python scripts/promptkit.py --run --prompt "supplier 1252 addresses"
    Router: modules=['supplier']
    Reason:   A bare supplier number cannot be used to look up a supplier
              because there is no supplier-number filter available.

    $ python scripts/promptkit.py --run --prompt "show addresses for supplier 1252"
    Router: modules=['supplier']
    Reason:   Filtering a supplier by a bare supplier number is not supported;
              a supplier name is required to resolve the query.

Every phrasing routes correctly to `supplier` and every one refuses for
the same reason: the parser has no reachable rule that says
"addresses for supplier X" is a valid shape.

**Root cause — same as F-009.**

The rule that WOULD answer these prompts lives in
`src/spire/nl_parser/context/payables/b_addresses.sysprompt`. It lists
`'addresses for supplier X'` and `'supplier 1252 addresses'` as its first
worked examples. But the block lives under `payables/` in
`order.manifest`, and the classifier scopes every one of these prompts
to `['supplier']`. `assemble_subset(['supplier'], menu)` loads
`{core, refusals, supplier}` and never reaches the payables block.

F-009 documents exactly this — a block-folder/module mismatch. The rule
lives in a folder that IS valid, loaded for other prompts, just not for
this one.

**Closure.**

F-042 is a duplicate of F-009. Filed here (append-only) so the sweep's
observation is recorded, and closed with the fix attributed to F-009's
row in the ledger.

---

## F-041 — AR invoice children named first ("invoice lines for invoice X", "DFF for invoice X", "tax breakdown for invoice X") refuse or silently drop; three AR sysprompt blocks lack a leading-phrasing rule

**Date:** 2026-09-19
**Status:** verified (PR #151, 2026-09-19)
**Cross-refs:** B-22 (family — child-field scope), F-025 (reverse-only children excluded), F-033 (adjacent — same class of parser/prompt gap, message-layer)

**Evidence.**

Discovered during Phase 2's child-as-root sweep, not in Phase 1. A new prompt
set (`scripts/prompts/13_child_as_root.txt`, 64 prompts) exercises every child
entity with the phrasing "child-noun for parent-id" — child named as the
subject, parent id afterward. Full run captured to `t.txt`.

**64 prompts, 64 "ran cleanly," 16 wrong.** The cleanly/incorrect gap is the
point of the sweep: `run_prompt_set.py` counts a refusal as a successful exit.
Only reading the answers shows the failure.

**Fails — AR invoice children, 16 of 16 across three families:**

_Family 1 — invoice lines (10 prompts, all refuse):_

    show invoice lines for invoice 300000248096352
    show lines for invoice 300000248096352
    show line items for invoice 300000248096352
    show the lines on invoice 300000248096352
    show the lines of invoice 300000248096352
    list the lines on invoice 300000248096352
    what lines does invoice 300000248096352 have
    lines of invoice 300000248096352
    lines on invoice 300000248096352
    invoice 300000248096352's lines

All refuse with `unknown_entity — Invoice lines are not supported as a target
entity` and the same Reason/Solution/Example:

    Reason:   I can look up AR invoice lines, but only as part of the record they belong to.
    Solution: Ask for the invoice and its lines together.
    Example:  Get the AR invoice with CustomerTransactionId 300000248096352

_Family 2 — DFF / flexfield (3 prompts, all refuse):_

    show flexfield for invoice 1002
    show DFF for invoice 1002
    fetch descriptive flexfield values for invoice 1002

All refuse with `unknown_entity — needs ReceivablesInvoiceTransactionDFF`.

_Family 3 — tax phrasing variants (3 prompts, all refuse):_

    what tax was charged on invoice 1002
    show tax breakdown for invoice 1002
    show the tax on invoice 1002

**But `show tax lines for invoice 1002` works** — same entity, same intent,
one phrasing passes and three fail. The sysprompt has one working rule; the
others aren't taught.

**Two silent misses (same finding, different shape):**

Two prompts returned exit `ok` while silently dropping the child request and
printing a "column not available" note against the PARENT:

    supplier EIP Inc's classifications
      → 1 supplier row, note "column isn't available on Supplier: 'classifications'"

    what is the flexfield context on invoice 1002
      → 1 invoice row, note "column isn't available on ReceivablesInvoice: '__FLEX_Context'"

Both returned a row and reported success. The column exists — on the child.
The user is told the parent doesn't have it, when the correct behaviour is
to fetch the child and answer.

**Cross-checked — the data exists and the pipeline can reach it.**

Curl against the pod, direct:

    $ curl .../receivablesInvoices/300000248096352/child/receivablesInvoiceLines
    { "items": [ { "CustomerTransactionLineId": 300000248096353,
                   "LineNumber": 1, "Description": "Consultation",
                   "LineAmount": 39969, ... } ] }

And with a working phrasing — `Get tax lines for invoice 1002` — the
pipeline answers with 4 lines and 8 tax rows. Same entity, same pod, same
pipeline. The failure is phrasing-specific.

**What works (39 of 64).** Every PO child (lines, schedules, distributions
— 17 phrasings), every Supplier contact phrasing (5), every CustomerAccount
child (transactions, receipts, credit memos, applications — 13 phrasings),
and one AR tax-line phrasing. All these children have sysprompt rules that
teach the leading-noun shape. The three failing AR blocks do not.

**Root cause.** Three AR sysprompt blocks teach only the TRAILING phrasing
— "and its lines", "and its tax lines", "and its DFF values" — which appends
a child request to an already-rooted parent query. None teaches the LEADING
phrasing, which is what every failing prompt uses: the child noun appears
first, the parent id afterward, and the parser takes the leading noun as
`target_entity`. Since a child is not a valid query root, the parser refuses
(or, on two phrasings, silently drops the child request and roots on the
parent).

The sibling AR block `b_ar_tax_lines.sysprompt` teaches ONE leading phrasing
(`show tax lines for invoice X`); it works. The other two AR blocks have no
leading rule at all. The fix is to give them the same shape their sibling
already has.

**Fix location (for Phase 2).** Three sysprompt files, mirroring the
existing pattern:

1. `src/spire/nl_parser/context/receivables/b_ar_invoice_lines.sysprompt`
   — add leading-phrasing rule: "invoice lines for invoice X" / "lines of X"
   / "lines on X" / "X's lines" / "show line items for X" / "what lines does
   X have" → target_entity 'ReceivablesInvoice' with a 'by_id' filter, add
   'ReceivablesInvoiceLine' to include.

2. `src/spire/nl_parser/context/receivables/b_ar_dff.sysprompt`
   — add: "flexfield for invoice X" / "DFF for invoice X" / "descriptive
   flexfield values for invoice X" → target_entity 'ReceivablesInvoice'
   by_id, add 'ReceivablesInvoiceTransactionDFF' to include.

3. `src/spire/nl_parser/context/receivables/b_ar_tax_lines.sysprompt`
   — extend the existing "show tax lines for invoice X" rule to also cover:
   "what tax was charged on invoice X" / "tax breakdown for invoice X" /
   "the tax on invoice X" → same routing.

No parser-code change. No `draft.py` change. No `capability.py` change. The
map `_CHILD_INCLUDE_WHEN_PRESENT` in `vocabulary.py` already carries the
(child, parent, trigger-words) tuples; the parser just needs the sysprompt
to teach the shape.

**Token-ceiling caveat.** The parser prompt is at its ceiling per the Phase 1
handoff. These three edits are small (~4 lines each) but any sysprompt edit
risks degenerate generation on specific phrasings. A full 12-set `--validate`
re-run is mandatory after the fix.

**Regression test.** The 16 failing prompts from
`scripts/prompts/13_child_as_root.txt` must answer. The 39 passing prompts
must remain unchanged. The two silent-miss prompts must return actual child
data. The F-025 exclusions (Site, Classification) must still refuse.

**Not checked.**

- Whether other phrasings of the same shape exist that the 64-prompt sweep
  did not exercise. The sweep is wide; a broader pass would extend it.
- Whether the two silent-miss prompts need a display-layer fix in addition
  to the parser fix. Today the display prints "column not available on
  <parent>" for an unknown field. When the field is satisfiable by an
  include, the display could say so instead. Separate observation, not
  F-041's scope.
- Whether the fix reintroduces any of the parser runaways documented in
  `spire_expansion_plan.md` §G7 (phrasings with `out=7983` degenerate
  generation). The `--validate` re-run covers this; a specific probe against
  the previously-flaky phrasings is a follow-up.
- Whether the AR invoice lines / DFF / tax blocks share a common cause with
  the "show addresses for supplier 1252" refusal (also observed in the
  sweep). That refusal is a different shape — leading verb changes the parse
  — and is being opened as F-042.

---

## F-006 — alpha-prefixed PO OrderNumber crashes `get_purchase_order_by_id` before the tool can resolve it

**Date:** 2026-09-17
**Status:** verified (PR #154, 2026-09-22)
**Cross-refs:** B-01, A-13

**Evidence.**

Runtime — the crash, verbatim:

```
$ python scripts/promptkit.py --run --prompt "What is purchase order US164932 about? Show its lines." --show-stages
[llm] provider=gemini model=gemini-3.5-flash
[llm] stage=classify in=555 out=165 total=720
[llm] provider=gemini model=gemini-3.5-flash
[llm] stage=classify in=555 out=165 total=720
Router: modules=['procurement']
[llm] stage=parse in=3933 out=427 total=4360
[cache] HIT   cached=3915  fresh=18  total_in=3933
ERROR: execute: 1 validation error for call[get_purchase_order_by_id]
po_header_id
  Input should be a valid integer, unable to parse string as an integer [type=int_parsing, input_value='US164932', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/int_parsing
```

Static — the mechanism, three sites:

- `src/spire/nl_parser/context/procurement/b_po_by_id.sysprompt` names this exact prompt (`'what is PO US164932 about'`) as its worked example, and instructs: *"Pass the number through EXACTLY as given and do not try to work out which kind it is: an order number and a header id look identical in a question, and the tool resolves either."*
- `src/spire/planner/plan_builders.py::_build_entity_fetcher_args` — for the `by_id` filter, `vocab_kind` is None, so it falls through to `args[arg_name] = raw_value`, with no coercion. `_resolve_arg_name` passes `po_header_id` through unchanged because it is not in `_VALUE_SHAPE_ROUTED_ARGS`.
- `src/spire/planner/registries.py::_TOOL_PRIMARY_ARG["get_purchase_order_by_id"] = "po_header_id"` — the arg name is correct; the type is the problem.

The runtime error's `int_parsing` on `input_type=str` shows the tool's input model declares `po_header_id: int`.

Corroborating curl (from §B.1, **not** re-run this session): `q=OrderNumber='US164932'` returns `POHeaderId 560869`. Two distinct fields — the OrderNumber the user typed, and the integer id the tool needs.

Identity note. §B.1's B-01 row records the same prompt and the same crash signature (`execute: 1 validation error … po_header_id`); the audit's `Actual` cell is abbreviated with an ellipsis, so a byte-identical output cannot be proven from the audit alone. Taken as the same bug on the strength of identical prompt + identical error signature + live reproduction this session — the tie is stronger than most cross-refs in this log. No alternative explanation is constructible from a different prompt producing this exact `po_header_id / input_value='US164932'` error, and none was found.

**Root cause.** The `by_id` filter on `PurchaseOrder` carries a value the parser cannot type-guess — it may be a small integer `POHeaderId`, or a string `OrderNumber` like `US164932` — and the sysprompt explicitly tells the model not to type-guess. But the planner has no shape-routing for `by_id` (unlike `supplier`/`supplier_po`, which route on `isdigit()` via `_VALUE_SHAPE_ROUTED_ARGS`), and the tool's input model types the arg as `int`. A string-shaped OrderNumber reaches Pydantic unconverted and crashes before the tool body runs. The sysprompt's "the tool resolves either" is contradicted by the tool's own input type.

**Fix location (for Phase 2).** One of two; both first-class:

1. **Planner-side.** Extend the `_VALUE_SHAPE_ROUTED_ARGS` pattern to `by_id`, mirroring the `supplier`/`supplier_po` split on `isdigit()` — a non-numeric value routes to a distinct arg name (whatever the tool uses for OrderNumber lookup; needs the tool bundle to confirm the name).
2. **Tool-side.** Change `po_header_id` to accept `str | int` and dispatch on shape inside the body: numeric → POHeaderId path; non-numeric → OrderNumber query. This makes the sysprompt's claim true rather than working around it, and is the more honest fix.

**Note — the class.** Same shape as F-001: the codebase asserts a behaviour the code does not honour. F-001's is a comment in `planner.py:188` describing a flag nothing sets; F-006's is a sysprompt saying the tool resolves either, against a tool typed as `int`. Recorded as an observation-class cross-link, not an identity claim.

**Regression test.** Assert `get_purchase_order_by_id("US164932")` succeeds and returns POHeaderId 560869, and that `get_purchase_order_by_id(560869)` still works — or, for the planner-side fix, that an Intent with `filters=[{"type":"by_id","value":"US164932"}]` on `PurchaseOrder` does not produce a plan whose first step carries an alpha string in an `int`-typed arg.

**Not checked.** `src/spire/mcp_server/tools/purchase_order_by_id.py` — its input model and whether the body would dispatch on shape if the schema allowed. The executor between plan and tool call, for any coercion layer not visible in the paste. Whether other `by_id` filters (ReceivablesInvoice CustomerTransactionId) have the same latent shape problem — AR ids are all-digit so they may pass through as `int` without failing, but 18-digit integers can overflow int64 or lose precision in Pydantic; unverified. Whether `kg_entity_filter` has any type column for `tool_arg_name` — `_load_filter_defs`'s SELECT list does not carry one.

**Update 2026-09-22 — fixed on `phase-2-fix-F006-alpha-order-number`.**

The defect was one level up from the two options the finding named.
Neither the planner (`_VALUE_SHAPE_ROUTED_ARGS` extension) nor the
tool-side type relaxation applied as written: the planner never sees
the string in a type position — it forwards the by_id value unchanged
as a `tool_arg` — and the internal resolver in
`tools/purchase_order_by_id.py` was already correct. It tries
`q=OrderNumber='X'` first, then `/purchaseOrders/X`, per its own
docstring ("Resolves ONE purchase order from whatever number the user
gave"). The crash was at the MCP wrapper in `src/spire/mcp_server/`,
where the annotation `po_header_id: int` produced a FastMCP schema
that rejected the string before dispatch.

Fix: one word on the wrapper annotation, `int` -> `str | int`. Same
one-word contract, both identifier shapes now admitted.

Verification:

- Reproducer `What is purchase order US164932 about? Show its lines.`
  now answers — POHeaderId 560869, OrderNumber `US164932`, EIP Inc,
  2 lines. Pre-fix output was the exact `int_parsing` error in the
  finding's Evidence block.
- Paraphrase `What is purchase order US164932 about?` also answers.
- Three numeric-identifier siblings
  (`Show PO 2144 and its lines`, `What is purchase order 2144 about?`,
  `Show PO 2144 and its buyer`) behave identically — no regression on
  the pre-existing path.
- New file `tests/test_f006_alpha_order_number.py` — 2 tests. Both
  fail without the fix: test 1 (annotation) with `assert str in ()`,
  test 2 (MCP call) with the Pydantic `int_parsing` error. Reversion
  verified by `git stash push src/spire/mcp_server/server.py`.
- Full suite: 1036 passed, 22 deselected (baseline 1034 + 2).

Corpus gap, recorded for the record: no prompt set exercises an
alpha-prefixed OrderNumber. Every PO prompt across
`02_purchase_order.txt`, `08_lifecycle.txt`, `10_refusal_examples.txt`,
`12_po_supplier_include.txt`, and `13_child_as_root.txt` uses `2144` or
`162034`, both numeric. F-006 was found by a hand-written reproducer
in the findings log, not by any prompt set. The shape is now covered
by the two tests above but still uncovered in the corpus.

---

## F-007 — empty requested tax lines produce no acknowledgement; the user can't tell "none exist" from "fetch failed"

**Date:** 2026-09-18
**Status:** verified (PR #155, 2026-09-22)
**Cross-refs:** B-02, B-23 (adjacent), F-001 (same class)

**Evidence.**

Runtime, the failing prompt:

```
$ python scripts/promptkit.py --run --prompt "Get tax lines for invoice 300000248096352" --show-stages
Router: modules=['receivables']
Intent:
  target_entity: ReceivablesInvoice
  filters: [{'type': 'by_id', 'value': '300000248096352'}]
  include: ['ReceivablesInvoiceLine', 'ReceivablesTaxLine']
...
Outputs:
  receivables_invoices: 1 record(s)
  receivables_invoice_lines: 1 record(s)
  receivablestaxline: 0 record(s)

Answer:

AR Invoices:
  Transaction           : 61765
  ...
  Invoice 61765 — lines:
    Line        : 1
    Description : Consultation
    ...
Summary:
  Final raw output:     0 record(s) under 'receivablestaxline'
```

The step ran, returned 0 rows, and the answer never says a word about tax lines.

Counter-example, same shape, non-empty bucket:

```
$ python scripts/promptkit.py --run --prompt "Show the AR invoice with CustomerTransactionId 1002 and its tax lines" --show-stages
...
  receivablestaxline: 8 record(s)
...
Answer:
  ...
  Invoice 5, line 1 — tax:
    Tax    | Rate % | Tax Amount | Taxable
    -------+--------+------------+--------
    COUNTY |   2.25 |     238.32 | 10592.0
    STATE  |    6.5 |     688.48 | 10592.0
  ... (three more lines)
```

Same parser, same planner, same synthesizer branch, same schema. When the bucket is non-empty the answer describes it; when it is empty the answer says nothing.

Static:

- `src/spire/synthesizer/synthesizer.py` — `synthesize_response`'s signature does **not** accept the intent's `include` list. The ReceivablesInvoice branch (`if target_entity == "ReceivablesInvoice":`) builds its response from `outputs` alone.
- `src/spire/synthesizer/ar.py::build_receivables_invoice_records` — `tax_rows = children.get("receivablestaxline") or []`. Empty bucket → every line gets `tax_lines=[]`.
- `src/spire/synthesizer/response_validation.py::_validate_receivables_invoice` — `for tx in ln.tax_lines: …`. Empty list passes trivially.
- `src/spire/nl_parser/context/receivables/b_ar_tax_lines.sysprompt` — instructs the model: *"on an AR-invoice question → add BOTH 'ReceivablesInvoiceLine' AND 'ReceivablesTaxLine' to include."* The instruction is honoured; nothing downstream uses the result to gate a "no tax lines" statement.

Identity note. §B.1's B-02 row records this exact prompt and the omission; the audit's "Actual" cell reads "Tax lines silently omitted." Same prompt, same shape, live reproduction. Taken as the same bug on the same grounds as F-006: identical prompt + identical reproduction + no alternative mechanism constructible.

**Root cause.** The synthesizer cannot see the intent's `include` list, so it cannot know which children the user asked for. When a requested child bucket is empty, `build_receivables_invoice_records` correctly builds an empty `tax_lines` list on every line — data is right — and the response is returned without any statement about tax. The display layer (not in this bundle) renders a sub-table per line only when `tax_lines` is non-empty, so nothing appears. The user asked a specific question and got an answer to a different one, with no signal that the specific part was answered "none."

**Fix location (for Phase 2).** Two candidate sites; the phase picks:

1. **Synthesizer-side.** Thread the intent's `include` list (or a derived "requested children" set) into `synthesize_response`. In the ReceivablesInvoice branch, when a requested child bucket is empty, add a summary sentence: *"Invoice 61765 has no tax lines."* Cost: the signature changes, and every caller has to pass through the include list. Benefit: general — the same mechanism covers any empty requested child on any shape (PO lines, schedules, distributions, DFF, AR lines, AR tax, AR DFF).
2. **Display-side.** Have `src/spire/rendering/formatters.py` render an empty-state line per requested child when the response's sub-list is empty. The formatter already knows which sub-tables it renders (`Invoice N, line M — tax:`); an empty-bucket variant would be `Invoice N, line M — tax: (none)`. Cost: the formatter needs to know the user *asked* for tax, which the response doesn't currently encode. So (2) requires some of (1)'s plumbing anyway — the response model would need a per-child "requested?" flag.

The first is the more honest fix, because the answer's *summary* is where the user reads the completeness signal. The empty sub-table is a rendering artifact; the missing acknowledgement is a narration failure.

**Regression test (either fix).** Assert that running `Get tax lines for invoice 300000248096352` produces an answer that contains the word "tax"; and that running `Show the AR invoice with CustomerTransactionId 1002 and its tax lines` still produces the four per-line tax sub-tables. Both must pass.

**Not checked.** `src/spire/rendering/formatters.py` — the actual site where the tax sub-table is skipped on an empty list; not in the synthesizer bundle. Whether the same silence occurs for other empty requested children (AR DFF — `build_invoice_dff` returns `None` on empty rows; PO lines/schedules/distributions on an empty bucket; AR lines on an empty bucket). Whether the intent's `include` reaches the synthesizer through any other channel (graph state, `filtered_fields`, etc.). Whether the display formatter already has an empty-state helper used elsewhere that this path simply misses.

**Update 2026-09-22 — fixed on `phase-2-fix-F007-empty-child-ack`.**

The defect was local. The ReceivablesInvoice branch in
`synthesize_response` has been LLM-free since before this fix — it
uses `local_list_summary` for the prose and
`build_receivables_invoice_records` for the records — so the missing
acknowledgement was not a model failure. It was that
`local_list_summary` sees only the parent rows and has no notion of
requested children. The two cases the finding named — "user asked and
there were none" and "user never asked" — were indistinguishable in
the summary.

The signal was already in `children`: the executor emits a bucket for
every step the plan ran, and the plan runs a step for every child the
parser put in the include list. Empty-but-present bucket means asked;
absent bucket means not asked. The fix reads that distinction.

Scope: all three AR-invoice children in the ReceivablesInvoice branch
(`receivables_invoice_lines`, `receivablestaxline`,
`receivablesinvoicetransactiondff`), not just tax. Same branch, same
defect shape, same fix.

Verification:

- Reproducer `Get tax lines for invoice 300000248096352` now answers
  with `This invoice has no tax lines.` above the invoice table.
- Siblings unchanged: invoice 1002 (8 tax rows) still renders four
  tax sub-tables and no acknowledgement.
- Negative unchanged: a plain AR query with no tax include still
  produces a single-step plan and no tax mention.
- New file `tests/test_f007_empty_child_ack.py` — 5 tests. Three fail
  without the fix (one behavioural assertion, two ImportError on the
  helper the fix introduces); two are over-reach guards that pass on
  both states by design.
- Full suite: 1041 passed, 22 deselected (baseline 1036 + 5).

Deviation from the finding's suggested fix: none in outcome. The
entry recommended the synthesizer-side fix over the display-side; the
fix lands there. The mechanism the entry proposed (thread
`intent.include` through the synthesizer) is not what was needed —
the local branch already carries the signal in `children`. No
signature change, no LLM.

---

## F-008 — expired supplier classifications match; the classification's Status never reaches the answer

**Date:** 2026-09-18
**Status:** root-caused, not fixed
**Cross-refs:** B-03, B-15 (same family), F-001 (same class)

**Evidence.**

Runtime, the prompt:

```
$ python scripts/promptkit.py --run --prompt "suppliers with classification Minority Owned" --show-stages
Router: modules=['supplier']
Intent:
  target_entity: Supplier
  filters:
    - {'type': 'has_classification', 'value': 'Minority Owned'}

Plan:
  Step 1: search_suppliers
    output_name:    suppliers
  Step 2: search_suppliers_by_classification
    tool_args:      {'supplier_id': '$iteration_value', 'classification': 'Minority Owned'}
    iterate_over:   {'from_step': 'suppliers', 'field': 'SupplierId'}
    output_name:    suppliers_has_classification
    filter_source_when_nonempty: True

Outputs:
  suppliers: 25 record(s)
  suppliers_has_classification: 1 record(s)
    [1] {'SupplierId': 300000047837244, 'SupplierNumber': '1272',
         'Supplier': 'Consolidated Supplies', 'Status': 'ACTIVE',
         'BusinessRelationship': 'Spend Authorized', 'TaxpayerCountryCode': None}
        ... +4 more field(s): CreatedBy, CreationDate, LastUpdateDate, LastUpdatedBy

Answer:
Examined 25 of 593 suppliers. Of those 25, 1 match the filter.

Suppliers:
  Supplier       : Consolidated Supplies
  SupplierId     : 300000047837244
  SupplierNumber : 1272
```

Two observations on the row shape:

- `suppliers_has_classification` holds a **supplier** row, not a classification row. Its `Status: 'ACTIVE'` is the supplier's status, not the classification's.
- The classification's own `Status` field — which the fetch did retrieve — is not on this row and does not reach the synthesizer.

Corroborating curl (from §B.1, **not** re-run this session): supplier 1272's `Minority Owned` classification carries `"Status": "EXPIRED"`.

Static, two sites:

- `src/spire/mcp_server/tools/supplier_classifications.py` — the tool's own docstring names the match-side fault: *"the pod rejects composite q= (Classification AND Status in one clause silently returns empty), so this tool filters on Classification ONLY and does not constrain Status. A supplier with a lapsed classification still matches. 'Current only' would require a client-side Status pass; not done here (no prompt requires it yet)."* `_PROJECTED_FIELDS` includes `"Status"` — the tool fetches it; it just does not constrain on it.
- `src/spire/planner/registries.py::_FILTER_SOURCE_NONEMPTY_SUFFIX` — `"has_classification"` is listed alongside `has_invoice_over_amount` and `has_site_in_bu`. Per `src/spire/planner/models.py`'s `Step.filter_source_when_nonempty` docstring: *"the step's output is the SOURCE items whose per-iteration call returned SOMETHING."* The child rows are the FILTER; the output bucket holds the parent supplier rows. The child Status is discarded on the way.

Identity note. §B.1's B-03 row records this prompt and the missing EXPIRED warning; the audit's "Actual" cell reads "1 match, no EXPIRED warning" with a curl corroboration. Same prompt, same shape, live reproduction this session. Taken as the same bug on the same grounds as F-006 and F-007.

**Root cause.** Two mechanisms, either sufficient on its own to produce the symptom. (1) The classification tool matches on `Classification` only — `Status` is fetched but not constrained — so a supplier with a lapsed `Minority Owned` classification satisfies "has classification Minority Owned". (2) Even with the status fetched, the planner routes this filter through `filter_source_when_nonempty`, whose contract is to output the PARENT items, not the child rows. The child Status therefore never reaches the synthesizer, and nothing downstream can surface "the classification matched but is EXPIRED." Either fix (constrain at the tool, or attach the child at the executor) would change the visible answer; both applied would be the honest one.

**Fix location (for Phase 2).** Two sites, and both should land:

1. **Filter-side.** `src/spire/mcp_server/tools/supplier_classifications.py` — add a client-side `Status` pass over the returned items, keeping only `Status == "CURRENT"` (or whatever the pod's active value is — needs a curl to confirm; the tool's docstring uses `"CURRENT"` as an example). This makes "suppliers with classification X" mean "suppliers with a CURRENT classification X", which is what a reader assumes. If any prompt later wants lapsed classifications explicitly, that becomes a distinct filter type, not a default.

2. **Projection-side.** Attach the classification row (or at least its `Status`) to the surviving supplier row under a key the synthesizer can read — mirroring the way `get_supplier_contacts` stamps `SupplierId` onto each contact row. Whether this belongs in the executor (as a generic `filter_source_when_nonempty` enrichment) or in the tool (stamping the classification onto its parent on the way out) is the phase's call; the tool-side stamp is the smaller change.

The first fix alone resolves the audit row (the EXPIRED match disappears). The second alone would change the answer shape (still a match, now with a warning). The first is the more honest default; the second is worth having because the underlying question — "is this cert current?" — will keep arising.

**Regression test (either fix).**
- Filter-side: assert that supplier 1272 does **not** appear in the results of `suppliers with classification Minority Owned` until its classification's status is `CURRENT`; and that a supplier with a `CURRENT` `Minority Owned` classification still does.
- Projection-side: assert that when a classification match reaches the synthesizer, its `Status` is available on the supplier record and any narration naming the classification reports the status.

**Not checked.** `src/spire/executor/executor.py` — the actual implementation of `filter_source_when_nonempty`. Whether it discards the child rows entirely, or attaches them under a key the plan output above does not show. This is the load-bearing unread file for mechanism (2); the mechanism is inferred from the `Step` docstring plus the observed output shape. Whether supplier 1272's classification is still `EXPIRED` this session — the audit's curl is cited, not re-run. Whether `has_site_in_bu` has the analogous problem (an inactive site satisfying "has a site in BU") — same shape, unverified. Whether any prompt in the corpus wants lapsed classifications deliberately — grep not run.

---

## F-009 — addresses rule lives in `payables/` but parses for `Address` (a `supplier` entity); the rule is unreachable from the scoped parse

**Date:** 2026-09-18
**Status:** fixed (as F-042's branch, PR #152, 2026-09-19)
**Cross-refs:** B-05, F-003 (same class), B-13 / F-001 (same family)

**Evidence.**

Runtime, the failing prompt:

```
$ python scripts/promptkit.py --run --prompt "addresses for supplier 1252" --show-stages
[llm] stage=classify in=546 out=69 total=615
[llm] stage=classify in=546 out=69 total=615
Router: modules=['supplier']
[llm] stage=parse in=3335 out=1250 total=4585
Reason:   Filtering suppliers by supplier number is not supported; a supplier name is required.

Solution: Narrow by country, status or name instead.

Example:  active suppliers in US
  (refusal: unsupported_filter — Filtering suppliers by supplier number is not supported; a supplier name is required.)
```

Two readings of the refusal:

- The Reason text has no snake_case identifier, so `capability.py::_reason_line`'s UNSUPPORTED_FILTER second branch returns it verbatim. That branch fires only on the SELF-DECLARED path (KG-validation's `detail` is a raw dump).
- The Solution/Example are `capability.py::_FILTER_GUIDANCE["Supplier"]` — so `offending_entity = "Supplier"`.
- Neither `intent_validation.py`'s message shape (`"Unsupported filter type(s): …"`) nor `plan_builders.py::_validate_intent_filters`'s (`"{entity} cannot be filtered by …"`) matches. The refusal is parser self-declared, with the model's own wording as `unanswerable_reason`.

The Intent block is not printed on a refusal (`pipeline.parse_node` returns `{"refusal": ...}` with no `intent`, so `_stage_report` has nothing to show). The parser's raw draft was not visible in this run — the mechanism below is inferred from the refusal text plus the sysprompt scope analysis, and that limitation is stated rather than hidden.

Static, three sites:

- `src/spire/nl_parser/context/routing/classifier_menu.sysprompt` — `Address` is listed under `supplier`. The router's choice of `['supplier']` is consistent with the entity's declared module. `assemble_subset` correctly loads only `{core, refusals} ∪ {supplier}`.
- `src/spire/nl_parser/context/order.manifest` — the addresses parsing rule is prefixed `payables/b_addresses.sysprompt`. Its block-folder is `payables`, which is not in scope for a supplier-classified prompt.
- `src/spire/nl_parser/context/payables/b_addresses.sysprompt` — the rule that WOULD have answered this prompt is explicit and lists this exact phrasing as its first worked example:
  > `'addresses for supplier X'` / `'supplier 1252 addresses'` / `'US supplier addresses'` / `'addresses in the UK'` → target_entity 'Address' with a 'supplier' filter (the supplier reference as written) and/or a 'country' filter (canonical code). Address queries MUST include a supplier or a country.
- `src/spire/nl_parser/context/supplier/b_contacts.sysprompt` — the nearest supplier-scoped rule that mentions a bare supplier number, and the one whose advice the model paraphrased:
  > A bare supplier NUMBER (e.g. 'supplier 1262') cannot root a Supplier query — there is no supplier-number filter — so if only a number is given and no name, this is out of scope; do not emit a 'by_id' or other invented filter.

Identity note. §B.1's B-05 row records this prompt and the refusal; the audit's "Actual" cell reads "Refusal: no supplier-number filter." Same prompt, same refusal shape, live reproduction this session. Taken as the same bug on the same grounds as F-006 / F-007 / F-008.

**Root cause.** A block-folder/module mismatch. `b_addresses.sysprompt` parses for `Address`, which the KG (and the generated classifier menu) declare as a `supplier` module entity. But the rule lives under `payables/` in the manifest. When the classifier scopes this prompt to `['supplier']` — the correct module for the entity — `assemble_subset` loads `{core, refusals, supplier}` and never sees `payables/b_addresses.sysprompt`. The parser has only one supplier-scoped rule that discusses a bare supplier number (`b_contacts.sysprompt`, which correctly says a supplier number cannot root a Supplier query), and its nearest-fitting interpretation of "addresses for supplier 1252" is "out of scope — supplier number is not a supplier filter." The model writes that as a self-declared `unsupported_filter` on `Supplier`, the renderer surfaces it verbatim, and the user gets a refusal that names a filter constraint the rule that would have routed correctly never imposed.

**Fix location (for Phase 2).** One of two, both small; the phase picks:

1. **Move the block.** Rename `payables/b_addresses.sysprompt` → `supplier/b_addresses.sysprompt` and update `order.manifest`. Mechanical. Makes the folder match the entity's module, so a supplier-scoped parse loads the rule that parses for a supplier-module entity. Cost: any check that assumes `payables/` is where addresses live (tests, tools, doc links) needs updating — grep needed.

2. **Widen the router's scope.** Have `assemble_subset` also load blocks whose parsed entity is in the in-scope set, regardless of folder. This requires a per-block entity tag that does not exist today (the manifest carries a folder prefix only). Larger change; appropriate if more blocks are discovered in the wrong folder.

Option 1 is the smaller, more honest fix, and it aligns the two authoritative sources (folder structure vs `kg_entity.module`) that currently disagree by one block. Option 2 generalises; the phase's call is whether one observed mismatch justifies generalising.

**Regression test (either fix).** Assert that the prompt `addresses for supplier 1252` produces an intent with `target_entity == 'Address'` and a `supplier` filter, and does NOT refuse with `unsupported_filter`; and that `suppliers with their addresses` still routes to `Supplier` with an `Address` include (the sibling rule in `supplier/b_suppliers_addresses.sysprompt`, which is on the supplier module and unaffected either way).

**Not checked.** The raw parsed `Intent` for this prompt — not printed on the refusal path, so the "model paraphrased b_contacts" claim rests on the refusal wording plus sysprompt scope, not on a raw draft. Whether the other two examples in `b_addresses.sysprompt` (`'supplier 1252 addresses'`, `'US supplier addresses'`) fail identically under the same classification — not run. Whether `payables/b_addresses.sysprompt` is drift or intentional — no git archaeology done. Whether other blocks in `order.manifest` have the same folder/entity mismatch — not exhaustively audited; the class-level check (does every block's folder equal its parsed entity's module?) is a Phase-2 sweep, not a Phase-1 finding.

**Class note.** Same class as F-003 (a rule that would have answered the prompt lives in a module the router never loads), but a distinct flavour: F-003's unreachable module (`modes/`) is in neither `_TIER1` nor `KNOWN_MODULES` and so is never loaded for any parse; this finding is a block in the *wrong* module for its entity — a folder that IS valid, loaded for other prompts, just not for this one.

---

## F-010 — `count_only` on a filtered intent returns the unfiltered source total; the filtered bucket is ignored

**Date:** 2026-09-18
**Status:** root-caused, not fixed
**Cross-refs:** B-04, F-008, F-001 (same class)

**Evidence.**

Runtime, the failing prompt:

```
$ python scripts/promptkit.py --run --prompt "count of suppliers with classification Minority Owned" --show-stages
Router: modules=['supplier']
Intent:
  target_entity: Supplier
  filters:
    - {'type': 'has_classification', 'value': 'Minority Owned'}
  count_only: True

Plan:
  Step 1: search_suppliers
    output_name:    suppliers
  Step 2: search_suppliers_by_classification
    tool_args:      {'supplier_id': '$iteration_value', 'classification': 'Minority Owned'}
    iterate_over:   {'from_step': 'suppliers', 'field': 'SupplierId'}
    output_name:    suppliers_has_classification
    filter_source_when_nonempty: True

Outputs:
  suppliers: 25 record(s)
  suppliers_has_classification: 1 record(s)

Answer:
There are 593 suppliers.
```

The intent is correct — `count_only=True` with the classification filter the user asked for. The executor is correct — two buckets produced, the filtered set holds the one matching supplier. The answer is wrong: 593 is the pod-wide supplier count, the **unfiltered** number, presented as the answer to a **filtered** question.

Note on B-04's class: §B.1's B-04 row records a different wrong shape ("N match from 25 of ~455 examined"). The current behaviour is worse — no sample caveat, just the source total. The essence (filtered supplier counts are wrong) is unchanged; the shape is different enough that a fresh entry is warranted rather than a note on B-04.

Static, two sites:

- `src/spire/synthesizer/synthesizer.py::synthesize_response` — the first branch:
  ```python
  if count_only:
      return _build_count_response(outputs, target_entity, truncation_by_step)
  ```
  This runs before any of the local list-summary dispatch. For a plain `count of suppliers` the shape is right; for an edge-traversal filter it is not.
- `src/spire/synthesizer/aggregation.py::_build_count_response` — the code that produces the wrong answer:
  ```python
  # The count query runs one fetch → one output bucket.
  bucket = next(iter(outputs.values()), [])
  examined = len(bucket)

  total_available = None
  examined_note = examined
  if truncation_by_step:
      entry = next(iter(truncation_by_step.values()), {})
      total_available = entry.get("total_available")
  ```
  `next(iter(outputs.values()))` grabs the FIRST bucket — the source (`suppliers`), not the filtered set (`suppliers_has_classification`). `next(iter(truncation_by_step.values()))` does the same on the truncation side. The source bucket's `total_available` is 593 (the pod-wide count); that becomes the answer.

The comment `# The count query runs one fetch → one output bucket.` is the assumption that fails. It is true for a plain count, false when the filter is an edge traversal — which is exactly the class B-04 covers.

Identity note. §B.1's B-04 row records the class (filtered supplier counts wrong, ~35 prompts across seven files). This entry is one representative reproducer of that class, chosen because its mechanism is clean and its bucket shape unambiguous. It is not claimed to exhaust B-04; other reproducers in the class may route through different code (e.g. `has_site_in_bu`, `has_invoice_over_amount`) and are not covered by this entry's fix location.

**Root cause.** `_build_count_response` assumes a single-bucket shape. For an edge-traversal filter the executor produces two buckets — the sampled source (`{source}`) and the filtered set (`{source}_{suffix}`) — and the function reads the first bucket's truncation entry without distinguishing source from filtered. The source bucket's `total_available` is the pod-wide count for the SOURCE entity (593 suppliers); the filtered set's count is what the user asked for. The function's docstring even names the hazard — "the unfiltered totalResults count, or the exact filtered total" — but the implementation cannot tell which it has, because the shape-detection helper the list path uses (`p2p.py::_filtered_supplier_list`, which matches on the `{source}_{suffix}` naming) is not called here.

**Fix location (for Phase 2).** One site, in `_build_count_response`:

- Detect the two-bucket filtered shape using the same rule `_filtered_supplier_list` already implements (`{source}_{suffix}` naming), and choose the source-vs-filtered bucket accordingly. For the filtered case, the count is the size of the FILTERED bucket; the source's `total_available` becomes a sample caveat, not the answer, mirroring the honest-denominator wording the list path already produces.
- Alternatively, extract the shape-detection into a helper both paths call, so a future entity added to the count path cannot repeat this. The phase's call whether that generalisation is worth the churn; the immediate fix is a check on `_filtered_supplier_list(outputs)` before the single-bucket assumption runs.

Either way, both the answer and the truncation summary should reflect the filtered set: for this prompt, "1 of 25 examined" is honest; "593 suppliers" is not.

**Regression test (for either fix).** Assert that `count of suppliers with classification Minority Owned` produces an answer whose count is the size of `suppliers_has_classification` (1 in this pod's sample), not 593. Assert that the plain `count of suppliers` (no filter) still returns 593. Both must pass, so the fix does not break the unfiltered count.

**Not checked.** Whether the same count-only fault affects the other edge-traversal filters — `has_open_PO`, `has_no_recent_invoices`, `has_invoice_over_amount`, `has_site_in_bu` — the shape is the same (source + filtered), but the code paths differ by filter and are not run this session. Whether `truncation_by_step`'s insertion order is guaranteed to match `outputs`' insertion order — `_build_count_response` assumes it in the paired `next(iter(...))` calls; the executor was not read to confirm. Whether other entities (Invoice with `has_invoice_over_amount`, PurchaseOrder with `has_open_PO`) have the same fault or a different one — the shape this reproducer exhibits is entity-agnostic but the fix may need to be.

**Class note.** Same class as F-001 (a codebase assumption the code does not honour — here, the docstring's "one fetch → one output bucket"). Distinct from F-008 (which is about a child's field not reaching the answer); this is about which BUCKET the answer is read from.

---

## F-011 — KG says `created_before` exists for "stale POs / older than N months"; sysprompt refuses that class of question

**Date:** 2026-09-18
**Status:** root-caused, not fixed
**Cross-refs:** B-06, F-001 (same class), F-006 (mirror), F-009 (same class-level sweep)

**Evidence.**

Runtime, the failing prompt:

```
$ python scripts/promptkit.py --run --prompt "Purchase orders older than 6 months" --show-stages
Router: modules=['procurement']
...
Reason:   Relative PO date window filtering ('older than 6 months') is not supported yet.

Solution: Give me a PO number instead, or a date bound.

Example:  Show PO 2144 and its lines
  (refusal: unsupported_filter — Relative PO date window filtering ('older than 6 months') is not supported yet.)
```

The refusal is parser self-declared: the Reason has no snake_case token, so `capability.py::_reason_line` returns the model's prose verbatim; the Solution/Example come from `_FILTER_GUIDANCE["PurchaseOrder"]`.

Static — the two sources that disagree, both live:

- `scripts/sql/kg_schema.sql`, `kg_entity_filter` seed for `PurchaseOrder.created_before`:
  > `'POs created BEFORE a date — the bound a "stale POs / older than N months" question needs. Filters server-side. NOTE: CreationDate, not OrderDate — OrderDate is projectable but NOT queryable on this pod (HTTP 400). Two rows (created_before / created_since) rather than one range row: the KG shape is one row = one op, and the two are genuinely different questions.'`

  The row's note names the *relative* question — "stale POs / older than N months" — as the motivation for the filter's existence.

- `src/spire/nl_parser/context/procurement/b_po_created_date.sysprompt`:
  > `If it says something RELATIVE — 'older than 6 months', 'stale', 'in the last year' — do NOT compute the date yourself and do NOT set these filters; relative PO date windows are not supported yet, so set unanswerable.`

  The sysprompt names *the same three phrases* as the reason to refuse.

Both statements are in the codebase, both are read by the pipeline. The KG row asserts the capability the sysprompt denies.

Identity note. §B.1's B-06 row records this prompt and its refusal, with the audit's note already linking it to the KG comment. Same prompt, same refusal, live reproduction this session. Taken as the same bug on the same grounds as F-006 through F-010.

**Root cause.** Two artefacts, authored with different intents, that both mention the same question class with opposite meanings. The KG row's note describes the filter's purpose as answering "stale POs / older than N months" — the row exists specifically because that question class was in scope. The sysprompt instructs the model to refuse that same class with a self-declared `unsupported_filter` — because no filter *type* carries a relative window (`{"months": N}`), only absolute ISO dates. The sysprompt runs at parse time and wins; the KG row's claim about the filter's purpose is not honoured for the class it names. The refusal's own Solution — "or a date bound" — is what the sysprompt just told the model not to compute.

Mechanically: relative-date arithmetic for this pattern *does* exist in the codebase — `date_utils.py::_compute_date_n_months_ago` is present and used for `has_no_recent_invoices`. But no `PurchaseOrder` filter type carries a `months` value; `created_before` and `created_since` take ISO date strings only. So the sysprompt is technically correct today, and the KG note is aspirational/misleading.

**Fix location (for Phase 2).** Two sites, and the phase picks which to align:

1. **Reconcile the KG to today's reality (smallest change).** Reword the `created_before` / `created_since` notes in `scripts/sql/kg_schema.sql` to say they answer *absolute*-date PO questions only, and drop the "stale POs / older than N months" clause. Then rebuild the KG (`python scripts/rebuild_kg.py`). The sysprompt stays as-is. Cost: any future reader of the KG row loses the pointer to why the row exists in the first place.

2. **Reconcile the sysprompt to the KG's intent (the capability the KG was written for).** Introduce a relative PO date filter type — `PurchaseOrder.created_in_last_n_months` (or similar) taking `{"months": N}` — mirroring how `has_no_recent_invoices` is handled. The planner computes the cutoff via `_compute_date_n_months_ago` and emits `created_before` with the computed ISO date. The sysprompt's relative-date rule is updated from "set unanswerable" to "set this filter with the months value; the parser/planner computes the date." Cost: a new filter row in `kg_entity_filter`, a new branch in `plan_builders.py::_build_entity_fetcher_args` (or a new computed-arg path), and a sysprompt edit. Larger, but resolves the intent the KG was written to.

The first is the honest minimum; the second is what the KG note was suggesting. Which is correct depends on whether the "not supported *yet*" phrasing in the sysprompt represents a deferred plan or a dead aspiration — the file was written with the word "yet" on purpose, which reads as deferred. Worth confirming with the author before choosing.

**Regression test (either fix).**
- Option 1: assert `Purchase orders created before 2024-01-01` still succeeds (the absolute path is unaffected); assert the KG note no longer names "older than N months" / "stale" — a seed-content assertion.
- Option 2: assert that `Purchase orders older than 6 months` produces an intent with `created_before` set to the computed cutoff (today minus 6 months, ISO date), and no refusal; and that the absolute-date form still works.

**Not checked.** Whether the *absolute* form (`Purchase orders created before 2024-01-01`) succeeds today — the falsifier for the "tool can filter by date" part of S4, not run. Whether the sysprompt's "not supported yet" was written before or after the KG row — no git archaeology. Whether any other KG note names a question class as the reason a filter exists while a sysprompt refuses that same class — the class-level sweep flagged in F-009's not-checked section, not run here either.

**Class note.** Same class as F-001 (a claim in the codebase the code does not honour — the KG note claims a capability the sysprompt denies) and F-006 (a sysprompt asserting behaviour the tool lacks — here the direction is inverted: the sysprompt asserts *inability* while the KG asserts *existence*). Both F-006 and F-011 are the same shape of drift between two authoritative documents; the direction differs.

---

## F-012 — composite invoice filter hits the over-fetch cap, drops `total_available`; the answer reads as if 20 were the count

**Date:** 2026-09-18
**Status:** closed (PR #157, 2026-09-22)
**Cross-refs:** B-07, F-010 (same class), F-003 (unavailable capability)

**Evidence.**

Runtime, the failing prompt:

```
$ python scripts/promptkit.py --run --prompt "invoices for supplier 1252 over 10000" --show-stages
Router: modules=['payables', 'supplier']
Intent:
  target_entity: Invoice
  filters:
    - {'type': 'supplier', 'value': '1252'}
    - {'type': 'invoice_amount', 'value': {'min': 10000}}

Plan:
  Step 1: search_invoices
    tool_args:      {'supplier_number': '1252', 'amount_min': 10000}

Outputs:
  invoices: 20 record(s)

Answer:
All 20 have InvoiceCurrency USD.
All 20 have Supplier Lee Supplies.

Invoices:
  ...20 rows, all amount > 10000...

Truncation:
  - invoices: unknown total in source; 20 examined for filtering.
```

Two distinct problems visible in the same paste.

1. **No count line in the prose.** The Answer contains no sentence saying the result is a sample. `local_list_summary` emits "Showing N of M" only when `total_available is not None`; here it is `None`, so nothing is said. The 20 rows read as the answer.

2. **"20 examined" understates the examined count.** The tool examined 200 rows (see below) and filtered to 20. The truncation note says "20 examined for filtering", implying only 20 were looked at. `_local_truncation` sets `examined = len(rows)` where `rows` is the OUTPUT bucket — post-filter, post-limit — not the fetch size.

Static, four sites:

- `src/spire/mcp_server/tools/invoices.py::search_invoices` — the branch that fires here:
  ```python
  if needs_client_filter and len(items) >= OVERFETCH_LIMIT:
      return ToolResult(
          items=projected,
          total_available=None,
          limit_applied=limit,
          truncated=True,
      )
  ```
  `needs_client_filter=True` (two filters: `supplier_number` + `amount_min`); `fetch_limit=OVERFETCH_LIMIT=200`; the pod returned ~200 rows for `q=SupplierNumber='1252'&limit=200`; the client-side amount filter kept 20; the return sets `total_available=None`.
- `src/spire/executor/executor.py::execute_plan` — routes the truncation dict into `truncation_by_step[output_name]` only when `truncated=True`; also into `metadata_by_step[output_name]`. Both carry `total_available=None`.
- `src/spire/synthesizer/synthesizer.py::_local_truncation` — reads `total_available` from the truncation entry (None), falls back to metadata (also None), produces `total_text="unknown"`; sets `examined = len(rows)` where `rows = outputs[bucket]`, the OUTPUT bucket, not the fetch.
- `src/spire/synthesizer/local_summary.py::local_list_summary` — emits no count line when `total_available is None`, so the summary reads as complete.

Identity note. §B.1's B-07 row records the class ("5 prompts: composite filters on invoices/receipts", Actual "unknown total in source; N examined"). Same prompt shape, same note shape, live reproduction this session. Taken as the same bug on the same grounds as F-006 through F-011.

**Root cause.** The pod's single-clause `q=` rule forces `search_invoices` to pick one filter for the server and apply the rest client-side. When the server-side fetch hits the over-fetch cap (200) and the client filter drops the rest, the tool cannot know how many matching rows exist beyond the 200 examined — so it returns `total_available=None` honestly. But the synthesizer treats `None` as "no count available, say nothing", and the note's `examined` value is drawn from the OUTPUT bucket rather than the fetch size. The result is an answer whose prose reads as if 20 is the count, over a note that misstates how many rows were examined.

Whether `total_available=None` is *forced* or merely chosen depends on whether the pod accepts the composite clause. The tool does not attempt it; the code comments assert it fails on this pod. That premise is cited, not re-verified this session (see Not checked).

**Fix location (for Phase 2).** Three options, in increasing scope:

1. **Make the "examined" value truthful.** Thread the tool's fetch size (`len(items)` at the point of the cap check) through the ToolResult envelope as a new field — `examined` alongside `total_available`, `limit_applied`, `truncated` — and have `_local_truncation` read that field for the note's number. Costs one new field in `ToolResult` and a per-tool change where the cap fires. Fixes #2 above but not #1.

2. **Surface the sample in the prose.** Have `local_list_summary` emit a sentence when `truncated is True` and `total_available is None` — e.g. "Showing 20 invoices from an examined sample; the true matching count is not known." Requires `local_list_summary` to accept a `truncated` flag it currently does not see. Fixes #1, leaves the "examined" wording.

3. **Compute an honest total.** If the falsifier shows the pod accepts the composite `q=`, replace the over-fetch approach with a `total_results` call on the composite clause. If the pod refuses the composite, no honest total exists — options 1 and 2 are the ceiling.

Doing (1) and (2) together resolves both visible problems. (3) is the cleanest if available, but is gated on the pod's behaviour.

**Regression test (either fix).** Assert that `invoices for supplier 1252 over 10000` produces an answer whose summary mentions the sample, OR whose truncation note states the true examined count (200, not 20). Assert that a non-composite query (`invoices for supplier 1252`) is unaffected. Both must pass.

**Not checked.** Whether the pod accepts composite `q=` on `/invoices` — the falsifier, not run; the code comments and the audit both assert refusal, and that premise is cited rather than re-verified. Whether the same composite shape produces the same failure on the other tools with the same branch (`search_purchase_orders`, `search_addresses`, `search_suppliers_by_country`) — likely by code reading, unrun. Whether `display/formatters.py` (not in this bundle) renders the truncation block prominently enough that a reader reliably sees it — the display layer is the other half of the "answer reads as complete" problem. Whether `ToolResult` can gain an `examined` field without breaking the `to_dict` shape consumed by older tools — the dataclass is `@dataclass`, so adding a field with a default is additive; not tested. Whether the same "examined = len(output rows)" wording affects other truncation notes — the wording is emitted only in `_local_truncation`, but the divergence it produces is per-tool.

**Class note.** Same class as F-010 (a sampled result read as if it were the answer). F-010 was the count path where the wrong number was written into the answer; here the wrong thing is the absence of a number, which reads the same way to a user who does not scroll to the truncation block.

**Update 2026-09-18 — falsifier run.** The composite `q=` probe against `/invoices` returned `total: 0 items: 0`:

```
$ python - <<'PY'
... FusionClient.get('/fscmRestApi/resources/11.13.18.05/invoices',
      params={'q': "SupplierNumber='1252' AND InvoiceAmount >= 10000",
              'limit': 1, 'totalResults': 'true'})
PY
total: 0 items: 0
```

The pod accepts the clause syntax and silently returns nothing for it — the "composite clauses combine to empty result" behaviour the tool's docstring asserts is confirmed. Fix option 3 (compute an honest total via a composite `q=` call) is therefore unavailable; options 1 and 2 are the routes. `total_available=None` in the tool is honest, not a code gap.

**Update 2026-09-22 — fixed on `phase-2-fix-F012-F036-truncation-wording`.**

Fixed alongside F-036 (shared branch; same f-string in
`synthesizer/synthesizer.py::_local_truncation`).

The mechanism ended up narrower than the entry's two named options. The
signal needed — "the fetch was capped" — was already on
`truncation_by_step` / `metadata_by_step`, populated by the executor for
every step. It needed a reader, not a new field.

Fix, two files:

- `src/spire/synthesizer/local_summary.py` — `local_list_summary` gains
  a `truncated: bool = False` parameter. When `truncated` is True AND
  `total_available` is None, it emits
  `"Showing N <entity> from an examined sample; the true matching count
  is not known."` before the uniformity observations. With a known
  total the existing `"Showing N of M"` line fires instead; with
  neither, nothing is claimed. The branch only fires on BOTH
  conditions.
- `src/spire/synthesizer/synthesizer.py` — new `_bucket_truncated()`
  helper (a single-bucket view of `_truncated_steps`, F-015's helper),
  threaded as `truncated=` into the eight `local_list_summary` calls
  across the plain-list branches: Supplier, PurchaseOrder (plain),
  Invoice, PO-with-children, CreditMemo, ReceivablesInvoice,
  CustomerAccount, StandardReceipt.

Verification:

- Reproducer `invoices for supplier 1252 over 10000` now answers with
  `Showing 19 invoices from an examined sample; the true matching count
  is not known.` Pre-fix: no count line — 19 rows read as the count.
- Sibling unchanged: `invoices for supplier 1252` (non-composite,
  `total_available=1329`) still shows `Showing 25 of 1,329 invoices.`;
  the sample sentence does not fire.
- Negative unchanged: `invoices` still refuses with `missing_identifier`.
- New file `tests/test_f012_truncation_sample.py` — 4 tests. Two fail
  without the fix (reproducer + metadata-by-step variant); two are
  over-reach guards that pass on both trees by design.
- Full suite: 1054 passed, 22 deselected (baseline 1048 + 6 new tests
  across both findings).

Deviation from the entry: none in mechanism-shape (synthesizer-side, per
the entry's preference for option 1). The signal source is different —
the entry suggested threading the intent's `include`; the fix reads the
truncation metadata the executor already produces.

Falsifier-run note above remains accurate: the composite `q=` route for
a real total is unavailable; the sample sentence is the honest ceiling.

---

## F-013 — B-11 / D-07 no longer reproduce; PO `by_id` vs `lifecycle_status` routing and the 2144 lookup are both fixed in the code

**Date:** 2026-09-18
**Status:** closed-as-not-a-bug
**Cross-refs:** B-11, D-07

**Evidence.**

Runtime, B-11's own prompt:

```
$ python scripts/promptkit.py --run --prompt "How much of PO 2144 was received?" --show-stages
Router: modules=['procurement']
Intent:
  target_entity: PurchaseOrder
  filters:
    - {'type': 'lifecycle_status', 'value': '2144'}

Plan:
  Step 1: get_purchase_order_lifecycle_status
    tool_args:      {'po_number': '2144'}

Outputs:
  open_pos: 1 record(s)
    [1] {'shape': 'po_lifecycle_status', 'found': True, 'order_number': '162352', 'po_header_id': 2144, ...}

Answer:
PO 162352 — EIP Inc
  Received: yes · Invoiced: yes · Paid: cannot be determined
  ...
  Amounts (USD):
    Ordered       41,250.00
    Received      41,250.00
    Invoiced      41,250.00
    Paid                  —
  ...
Unresolved:
  - '2144' is a POHeaderId, not an order number; resolved to OrderNumber '162352'
```

Contrast with the audit's B-11 row:

> B-11 | wrong-answer (silent) | `How much of PO 2144 was received?` | Lifecycle for PO 2144 | `found: False`, "No purchase order found for '2144'." | User-supplied PO reference routed to wrong field.

`found: True` today; `found: False` per the audit. The parser routed to `lifecycle_status`; the audit implies it routed elsewhere. Both halves of B-11's claim fail to reproduce.

Static — the two fixes are visible and each names this prompt as its reason:

- `src/spire/mcp_server/tools/po_lifecycle.py::_try_header_id_lookup`:
  > *"Used only when the OrderNumber lookup misses: a bare 'PO 2144' is a POHeaderId (2144 -> OrderNumber 162352 on this pod), not an order number, so an OrderNumber-only lookup falsely reports not-found."*

  The fallback fires only when the OrderNumber lookup misses; the paste shows it firing and resolving. Pre-fallback, the tool would have returned `found: False` — exactly the audit's recorded symptom.

- `src/spire/nl_parser/context/procurement/m_po_lifecycle.sysprompt`:
  > *"A SINGLE LEG IS STILL THIS FILTER. A question naming one PO and asking about only ONE stage — 'how much of PO 2144 was received', ... — is this filter... Do NOT route it to 'by_id' with a schedule include."*

  The prompt is named as an example of the routing the sysprompt is meant to produce. The parser produced it.

Identity note. The audit's B-11 and D-07 rows both describe this prompt. Both are disproven by the same run: B-11's `found: False` and D-07's "routed to by_id" are mutually inconsistent with the observed `found: True` via `lifecycle_status`. Neither entry is being edited (append-only); this closure records the correction.

**Root cause of the (now-closed) prior claim.** Both mechanisms were real pre-fix states, described in the fix comments that retired them: the lifecycle tool's `_try_header_id_lookup` was added to catch the bare-number case, and the `m_po_lifecycle.sysprompt` block was authored to steer the parser toward `lifecycle_status` for single-leg questions. Either change alone would have resolved the observed `found: False`; both are present now. The audit rows were recorded before one or both landed.

**Fix location.** None — closed. If a future session re-opens B-11 or D-07, cite this entry and the two fix comments above before re-investigating.

**Regression test.** Already present in spirit in `po_lifecycle.py`'s docstring; a durable guard would assert that `get_purchase_order_lifecycle_status('2144')` returns `found=True` with `order_number='162352'` (the header-id fallback path) and that `get_purchase_order_lifecycle_status('162352')` also returns `found=True` (the OrderNumber path). Both must pass.

**Not checked.** Whether B-11 or D-07 reproduced *at the time the audit was written* — the audit rows may have been accurate observations of a pre-fix code state, in which case this is a fix-in-place closure rather than a mistaken entry. No git archaeology was done to establish which. Whether any other prompt in the corpus exercises the `by_id` vs `lifecycle_status` boundary and still misroutes — the audit's other rows on that boundary were not swept. Whether the audit's B-11 note "Cross-reference D-07" also implies a third row somewhere — the cross-references in the log were not exhaustively followed.

---

## F-014 — `fields` on an aggregate intent is applied to the wrapper record; the projection table renders the requested column as `—`

**Date:** 2026-09-18
**Status:** root-caused, not fixed
**Cross-refs:** B-17, F-010 (adjacent), F-003 (parent class)

**Evidence.**

Runtime, the audit's own reproducer:

```
$ python scripts/promptkit.py --run --prompt "Top 5 suppliers by invoice spend in 2022 with supplier name and total" --show-stages
Router: modules=['payables', 'supplier']
Intent:
  target_entity: Supplier
  fields: ['Supplier']
  aggregate: {'op': 'by_supplier', 'date_from': '2022-01-01', 'date_to': '2023-01-01', 'top_n': 5}

Plan:
  Step 1: aggregate_invoices_by_supplier
    tool_args:      {'date_from': '2022-01-01', 'date_to': '2023-01-01', 'top_n': 5}
    output_name:    aggregation

Outputs:
  aggregation: 1 record(s)
    [1] {'shape': 'supplier_spend_ranking', 'date_from': '2022-01-01',
         'date_to': '2023-01-01', 'total_suppliers': 50, 'returned': 5,
         'truncated': False}
        ... +3 more field(s): examined, rows, total_available

Answer:
Top 5 of 50 suppliers by spend.
EIP Inc leads with 141,171,590.98 — 3.3x the next.

Answer:
aggregation (1 record(s)) — columns: Supplier

  Supplier
  --------
  —
```

Two observations.

- The `aggregation` bucket holds **one** record — the ranking's shape wrapper. The five supplier rows live inside `rows[]`, one level deeper. The wrapper's keys (`shape`, `date_from`, `date_to`, `total_suppliers`, `returned`, `truncated`, `examined`, `rows`, `total_available`) do not include `Supplier`.
- Two `Answer:` blocks appear. The first is the synthesized response's summary and is correct: the local ranking summary reads `rows[].total_spend` and produces the right leader line. The second is the projected-outputs table, in which the requested `Supplier` column renders as `—`.

The MCP server log confirms the underlying fetch ran correctly (27 pages, 13,274 invoices examined). The defect is entirely downstream of the fetch.

Static:

- `src/spire/graph/pipeline.py::_project_outputs`:
  ```python
  def _project_outputs(outputs: dict, fields: list) -> dict:
      if not fields:
          return outputs
      wanted = list(fields)
      projected: dict = {}
      for name, records in outputs.items():
          new_records = []
          for rec in records:
              if not isinstance(rec, dict):
                  new_records.append(rec)
                  continue
              trimmed = {k: rec[k] for k in wanted if k in rec}
              new_records.append(trimmed if trimmed else rec)
          projected[name] = new_records
      return projected
  ```
  Called from `execute_node`:
  ```python
  fields = getattr(state.get("intent"), "fields", []) or []
  projected = _project_outputs(outputs, fields)
  ```
  Every bucket is projected the same way. For the aggregation bucket, the wrapper record has no `Supplier` key, `trimmed={}`, and the fallback preserves the original record. The downstream renderer then tries to display `Supplier` against a record whose keys are all wrapper metadata, and prints `—`.

Identity note. §B.1's B-17 row records this shape (`Em-dashes: — | —. Prose names the winner.`), narrowed twice in the audit to "specific to intents carrying explicit `fields` alongside `aggregate`". Same prompt, same shape, live reproduction this session. Taken as the same bug on the same grounds as F-006 through F-012.

**Root cause.** An aggregate intent's output is a shape wrapper, not a list of entity records. `_project_outputs` treats all buckets uniformly, so it applies the requested `fields` to the wrapper's own keys — none of which match a Supplier field name. The result is a projection table whose requested column is empty, while the actual figures are correctly present one level down in `rows[]` and correctly narrated in the summary above. The parser emitted `fields=['Supplier']` because the user said "with supplier name"; that is not itself wrong for a list query, but it is meaningless on an aggregate — the aggregation path's response schema (`SupplierSpendRow`) has fixed fields (`supplier_name`, `supplier_number`, `total_spend`, `invoice_count`) and no projection semantics.

Two adjacent facts from the same run, noted but not part of this finding:

- The parser dropped `total` from `fields` even though the user asked for it. Whether `total` should map to the aggregation's `total_spend` — or be dropped because the aggregate's schema already carries it — is a parser-side question.
- The `comparison` bucket has the same wrapper shape (its result is a single dict keyed by `shape` under `comparison`, per `synthesizer.aggregation._comparison_shape`), so it is likely to exhibit the same failure if any prompt emits `fields` alongside a `compare` block. Unrun.

**Fix location (for Phase 2).** Two sites; either resolves the visible defect, the phase picks:

1. **Pipeline-side (defense).** `src/spire/graph/pipeline.py::_project_outputs` — detect the shape-wrapper buckets (`aggregation`, `comparison`) and skip projection for them, or descend into their `rows[]` list where the actual records live. Skipping is the smaller change and mirrors the shape-detection the synthesizer already does (`_aggregation_shape`, `_comparison_shape`). Descending is more useful if a future prompt wants to project the rows themselves — but the aggregation schemas do not consume a projection, so descending would only affect display.

2. **Parser-side (prevention).** `src/spire/nl_parser/context/modes/m_aggregation.sysprompt` (or the schema description on `DraftIntent.aggregate`) — a rule stating that when `aggregate` is set, `fields` must be left empty: the aggregation's schema carries fixed columns, and the user's phrasing ("with supplier name and total") is already satisfied by that schema. Cost: a sysprompt edit, which has broad blast radius on the classifier and parser per the handoff's own warning about `_CLASSIFIER_INSTRUCTION` edits; a full `--validate` re-run is warranted.

Both is the honest fix: prevention at the parser, defense at the pipeline. The parser-side alone leaves the pipeline brittle to any future prompt that emits fields on an aggregate; the pipeline-side alone leaves the parser emitting a meaningless field that a future schema consumer might try to honor.

**Regression test (either fix).**
- Pipeline-side: assert that `_project_outputs` returns the aggregation bucket unchanged (or projects `rows[]`) when `fields=['Supplier']` and the bucket's single record is a shape wrapper. Assert that a normal entity bucket (`{'invoices': [{'InvoiceNumber': '...', 'SupplierNumber': '...'}]}`) still projects correctly.
- Parser-side: assert that `Top 5 suppliers by invoice spend in 2022 with supplier name and total` produces an intent whose `aggregate` block is set and whose `fields` list is empty.

**Not checked.** `src/spire/rendering/formatters.py` — the actual site rendering `—` for the missing key; not in the bundles read this session. Whether the `comparison` bucket exhibits the same failure when a `compare` intent carries `fields` (the wrapper shape suggests yes). Whether the parser should map "total" → `total_spend` on an aggregate (the user asked for it; the parser dropped it) — orthogonal to the em-dash. Whether the audit's own note "narrowed twice" was itself narrowed from a broader original claim — the audit rows do not preserve the prior states.

**Class note.** Adjacent to F-010 (both concern how the aggregation path's output is processed downstream) but distinct: F-010 produced the wrong number by reading the wrong bucket in the count path; this produces the wrong shape by applying projection to a bucket whose records are not entity rows. Both are consequences of treating an aggregate output like an entity-list output.

---

## F-015 — a truncated-to-zero result is narrated as a clean "not found"; the empty-bucket shortcut discards the truncation flag

**Date:** 2026-09-18
**Status:** verified (PR #156, 2026-09-22)
**Cross-refs:** B-19, F-012 (same family — sampling not disclosed)

**Evidence.**

Runtime, the audit's reproducer:

```
$ python scripts/promptkit.py --run --prompt "Show receipts for ABC Corporation Americas at Santa Clara" --show-stages
Router: modules=['receivables']
Intent:
  target_entity: StandardReceipt
  filters:
    - {'type': 'customer_name', 'value': 'ABC Corporation Americas'}
    - {'type': 'customer_site', 'value': 'Santa Clara'}

Plan:
  Step 1: search_standard_receipts
    tool_args:      {'customer_name': 'ABC Corporation Americas', 'customer_site': 'Santa Clara'}

Outputs:
  standard_receipts: 0 record(s)

Answer:
No receipts found matching the criteria.
No receipts found.
```

The probe that separates the three possible empty-result branches:

```
$ python - <<'PY'
... FusionClient.get('/receivablesCustomerAccountActivities',
      params={'q': "CustomerName='ABC Corporation Americas'", 'limit': 5})
... FusionClient.get('/standardReceipts',
      params={'q': f"CustomerAccountNumber=26370", 'limit': 500,
              'orderBy': 'ReceiptDate:desc', 'onlyData': 'true'})
PY
customer resolve: 1 row(s)
  AccountNumber='26370'  AccountId=300000047368527  CustomerName='ABC Corporation Americas'
receipts for account 26370: 500 row(s)
  CustomerSite=None: 500
```

The customer resolves; the tool fetches 500 rows (the overfetch cap); every fetched row has a null `CustomerSite`. The client-side site filter drops all 500. The tool returns `ToolResult(items=[], total_available=None, limit_applied=25, truncated=True)`.

Note on the audit's curl. §B.1's B-19 row cites a curl showing "500 records on the pod, all with `CustomerSite='Santa Clara'`". This session's probe shows the newest 500 for account 26370 with `CustomerSite=None` — a different slice of the same collection. The audit's curl is cited, not re-verified. Whichever slice is authoritative, the behaviour observed today is: fetch returns 500 rows, all with a null site, tool filters to zero, tool sets `truncated=True`, synthesizer discards it.

Static — two sites:

- `src/spire/mcp_server/tools/standard_receipts.py::search_standard_receipts` — the AI-7 note documents the site filter's cap, and the code that acts on it correctly sets `truncated=True`:
  ```python
  client_filtered = customer_site is not None
  fetch_capped = len(items) >= OVERFETCH_LIMIT
  truncated = client_filtered and fetch_capped
  if truncated:
      return ToolResult(
          items=capped,
          total_available=None,
          limit_applied=limit,
          truncated=True,
      )
  ```
  The tool did its job: it flagged that the result may be incomplete.
- `src/spire/synthesizer/synthesizer.py::synthesize_response` — the empty-bucket shortcut, which fires before any truncation logic and discards the flag:
  ```python
  if _all_buckets_empty(outputs) and target_entity in SYNTHESIS_SCHEMAS:
      empty_schema = SYNTHESIS_SCHEMAS[target_entity]
      label = _ENTITY_LABEL.get(target_entity, "records")
      return empty_schema(
          summary=f"No {label} found matching the criteria.",
          truncation_notes=[],   # ← truncation_by_step in scope, not consulted
      )
  ```
  `truncation_by_step` is a parameter of `synthesize_response`. On the empty-bucket path, it is not read.

Identity note. §B.1's B-19 row records this prompt and its "No receipts found matching the criteria." outcome; the audit's "Actual" cell is exactly that string. Same prompt, same rendered answer, live reproduction this session. Taken as the same bug on the same grounds as F-006 through F-014.

**Root cause.** Two mechanisms, stacked; the second is the load-bearing one.

1. The site filter is client-side over a fetch capped at `OVERFETCH_LIMIT=500`, and (today) the newest-500 window for this account has every row with a null `CustomerSite`. The AI-7 note documents the shape and the tool sets `truncated=True` to signal the possible incompleteness.
2. The synthesizer's `_all_buckets_empty` shortcut runs before any truncation handling and returns a fixed empty response with `truncation_notes=[]`. The truncation flag the tool set is discarded, and the answer reads as a clean "no results."

The user's question has three honest answers — "the customer has no Santa Clara receipts", "the customer has receipts but none in the newest 500 have a recorded site", or "there are receipts at Santa Clara beyond the examined window" — and the pipeline currently returns the first of them regardless of which is true.

**Fix location (for Phase 2).** Two sites; the phase picks, and (2) is the one that resolves the observed symptom:

1. **Synthesizer-side (primary).** `src/spire/synthesizer/synthesizer.py::synthesize_response` — on the `_all_buckets_empty` path, consult `truncation_by_step` and populate `truncation_notes` when any entry has `truncated=True`. The summary should say the search was capped: e.g. *"No receipts found in the examined sample. The search was capped at 500 rows; more may exist."* This is the minimal fix and it makes the tool's warning visible. Cost: a change to the empty-bucket branch; every zero-row entity target inherits the improvement.
2. **Tool-side (secondary).** `src/spire/mcp_server/tools/standard_receipts.py::search_standard_receipts` — the AI-7 path already sets `truncated=True`. Nothing to change in the tool for the warning mechanism to work; only if the fix wants a *more accurate* count than `None`. If the pod supports `totalResults` on the site-filtered query (composite `q=` is known to fail; a two-query approach — count receipts for the account, then subtract) would recover a partial total. Deferred.

If only one is fixed, the synthesizer-side is the one that changes the answer the user sees. The tool already does its part.

**Regression test (either fix).** Assert that `Show receipts for ABC Corporation Americas at Santa Clara` returns a response whose `truncation_notes` is non-empty and whose summary says the result was capped, not a clean "no receipts." Assert that a genuinely-empty entity query (e.g. `receipts for a customer with none`) still returns the clean "no receipts" summary with no truncation note. Both must pass.

**Not checked.** Whether the current slice of account 26370's receipts would include any `CustomerSite='Santa Clara'` rows if the fetch went past 500 — the audit's curl says yes; this session's probe on the newest 500 says no; both could be true of different slices. Whether the same empty-bucket-discards-truncation shape affects any other tool's zero-row path — the branch is generic over `SYNTHESIS_SCHEMAS`, so `Supplier`, `Invoice`, `PurchaseOrder`, `ReceivablesInvoice`, `CustomerAccount`, `CreditMemo`, `StandardReceipt`, `Address` all inherit it; the truncation flag has to be set by the upstream tool to matter, and only some tools set it. Whether the display formatter, given non-empty `truncation_notes`, renders them prominently enough that a skimming reader sees them — the display file is not in this bundle.

**Class note.** Same family as F-012 — a sampled or incomplete result presented as if it were the whole — with the opposite fault: F-012's answer read as if 20 were the count; this answer reads as if 0 were the total. Both come from the synthesizer treating an absent number as "say nothing."

**Update 2026-09-22 — fixed on `phase-2-fix-F015-empty-bucket-truncation`.**

The defect was in `synthesize_response`'s empty-bucket shortcut. It
fired before truncation was consulted and built the response with
`truncation_notes=[]` unconditionally. Both `truncation_by_step` and
`metadata_by_step` were parameters of the function and reachable from
the shortcut's scope; the flag existed, nothing read it. So a bucket
that came back empty because a fetch was capped narrated identically to
a genuinely empty source.

The shortcut is generic over `SYNTHESIS_SCHEMAS`, so this was never
StandardReceipt-specific — every zero-row entity target inherited the
same silence. The finding's title names receipts; the fix covers the
class.

Fix: a local helper `_truncated_steps(truncation_by_step,
metadata_by_step)` collects entries where `truncated is True` (exactly
`is True`, not truthiness — an entry explicitly saying False is not a
cap), reading both sources and deduping. When any step was capped, the
shortcut's summary names the sample and populates `truncation_notes`
from the same entries. No LLM: this path returns before any LLM setup
and the fix keeps it that way.

Verification:

- Reproducer `Show receipts for ABC Corporation Americas at Santa Clara`
  now answers with "No receipts found in the examined sample. The
  search was capped before examining all matching records, so more may
  exist beyond the examined window." and a non-empty Truncation block.
- Negative unchanged: `Get standardReceipts` still refuses at plan time
  with `missing_identifier — StandardReceipt root has no customer or
  site scope`.
- Sibling unchanged: `List recent credit memos` still answers with 25
  records and its own truncation note; the fix touches only the empty
  path.
- New file `tests/test_f015_empty_bucket_truncation.py` — 7 tests. Five
  fail without the fix (two behavioural assertions, three ImportError
  on the helper); two are over-reach guards (genuinely-empty unchanged,
  truncated=False ignored) that pass on both states by design.
- Full suite: 1048 passed, 22 deselected (baseline 1041 + 7).

Deviation from the entry: none in outcome. The entry named the
synthesizer-side option as primary; the fix lands there. Scope widened
from the entry's specific reproducer (StandardReceipt) to the generic
shortcut — same class, same fix site.

Observation, out of scope: the display's empty-table placeholder
("No receipts found.") sits one line below the fix's summary,
restating it. This duplication predates F-015 (the finding's own
Evidence block shows the same two-line shape) and belongs with the
display formatter, not this branch. §8.3.5, no scope creep.

---

## F-016 — no schema field carries a plain-list row cap; "top 5" on a list query is dropped and the tool returns its default 25

**Date:** 2026-09-18
**Status:** root-caused, not fixed
**Cross-refs:** B-26, F-001 (parallel), B-13

**Evidence.**

Runtime, the audit's reproducer:

```
$ python scripts/promptkit.py --run --prompt "List recent credit memos, top 5" --show-stages
Router: modules=['receivables']
Intent:
  target_entity: CreditMemo

Plan:
  Step 1: list_receivables_credit_memos
    tool_args:      {}

Outputs:
  credit_memos: 25 record(s)

Answer:
Showing 25 of 2,262 credit memos.
...25 rows...
```

Three places the "5" is missing:

- **Intent** — the parser produced `target_entity: CreditMemo` and nothing else. No `fields`, no `filters`, no `count_only`, no `aggregate`, no `invoice_limit`. Every other intent field is scoped to a specific shape (see below). There is no slot the "5" could be stored in even if the parser had recognized it.
- **Plan** — `tool_args: {}`. The tool's signature is `list_receivables_credit_memos(client, limit: int = 25)`. An empty args dict means the tool's default (25) applies.
- **Outputs** — 25 rows, matching the tool's default.

Static, two schemas:

- `src/spire/nl_parser/draft.py::DraftIntent` — the fields are `unanswerable`, `unanswerable_reason`, `unanswerable_kind`, `unanswerable_entity`, `target_entity`, `filters`, `include`, `fields`, `aggregate`, `compare`, `count_only`, `open_only`, `invoice_limit`, `balance_only`. Every numeric cap is scoped: `aggregate.top_n` only when `aggregate` is set; `invoice_limit` only on a CustomerAccount + by_customer_name + CustomerTransaction + open_only query. No field carries a plain-list cap.
- `src/spire/planner/models.py::Intent` — same gap. The dataclass has `target_entity`, `filters`, `include`, `fields`, `unresolved_fields`, `aggregate`, `compare`, `count_only`, `open_only`, `invoice_limit`, `balance_only`, `list_all`. No `list_limit` / `row_cap` / equivalent.
- `src/spire/planner/plan_builders.py::_build_entity_fetcher_args` — builds `tool_args` from `intent.filters` via `_filter_def_for(ftype, entity)`. It does not read any intent field for a row cap. Even with `Intent.list_limit` set, the current builder would not forward it.

Corroborating capability at the tool layer: `list_receivables_credit_memos` docstring says *"Applied SERVER-SIDE alongside the date sort, so this is a true 'N most recent'"* — the tool can do exactly what the user asked. Every sibling list tool has a `limit` parameter (`search_suppliers`, `search_purchase_orders`, `search_invoices`, `search_addresses`, `search_standard_receipts`). The capability exists at the tool; there is no channel above it to carry the number.

Contrast with §B.4's positive example. `Show account activity summary for top accounts` correctly extracts `top_n: 10` — because it routes through `DraftAggregate`, whose schema *has* a `top_n` field. The parser reads "top N" reliably; the list path simply has no schema slot to write into.

Identity note. §B.1's B-26 row records this prompt and the result ("25 records — the `top 5` was silently dropped from the intent"), and the audit's own note observes the asymmetry ("the parser handles `top_n` for aggregates, just not for list queries"). Same prompt, same 25-row result, live reproduction this session. Taken as the same bug on the same grounds as F-006 through F-015.

**Root cause.** A schema gap, not a parser error. `DraftIntent` (and the planner's `Intent`) has no field for a list-row cap, so the parser cannot record "top 5" even when it hears it; the planner's `_build_entity_fetcher_args` builds `tool_args` from filters only, so even a recorded cap would not reach the tool; and the tool defaults to 25 when `limit` is not passed. Every numeric field on the intent is scoped to a specific query shape, and none of them covers a plain list. The pipeline correctly does not hallucinate a "5" from thin air — the model had no field to write it into.

**Fix location (for Phase 2).** Two options, and the handoff's warning about the parser prompt's token ceiling bears directly on the choice:

1. **Add a schema field (`list_limit` or similar).** Requires:
   - A new field on `DraftIntent` (`list_limit: int | None = Field(default=None, description=...)`).
   - The same field on `Intent` (planner dataclass).
   - `DraftIntent.to_intent()` copies it.
   - `_build_entity_fetcher_args` injects `"limit": intent.list_limit` when set and the tool supports it.
   - A sysprompt instruction on `DraftIntent.fields`'s model — but this hits the token ceiling.

   The handoff (SPIRE_SESSION_HANDOFF.md) warns: *"the parser prompt is at its token ceiling and any added prompt/schema text tips specific phrasings into degenerate (MAX_TOKENS) generation."* Adding a new schema field plus its description is exactly what the warning describes. This option is available but has a known cost.

2. **Post-parse deterministic extraction (smaller, matches an existing pattern).** `parser.py` already has `_is_explicit_po_list(prompt)` — a pure-string regex pass that runs after the LLM, sets a flag on the intent, with zero LLM-visible text. A parallel `_extract_list_cap(prompt)` could:
   - Match phrases like "top N", "first N", "the N most recent", "N largest", "N oldest".
   - Return `int | None`.
   - Run after `to_intent()`, assign to `intent.list_limit`.
   - The planner's `_build_entity_fetcher_args` injects `limit` when set.

   Cost: regex maintenance for phrasing variants; the extraction may miss phrasings the model would have recognized. Benefit: no schema change, no sysprompt edit, no token-ceiling risk.

Either option leaves the tool-side untouched — `list_receivables_credit_memos` already accepts `limit`.

Option 2 is the smaller change and matches an established in-repo pattern; option 1 is the more general fix but risks the ceiling.

**Regression test (either fix).** Assert that `List recent credit memos, top 5` produces an intent carrying the cap and a plan whose `tool_args` includes `limit=5`, and that the answer shows 5 rows. Assert that `List recent credit memos` (no cap) still returns 25. Both must pass.

**Not checked.** Whether `planner/models.py::Intent` has a list-cap field missed on read — the bundle shows the complete dataclass, so unlikely; `grep -n "list_limit\|row_limit\|result_limit" src/spire/nl_parser/draft.py src/spire/planner/models.py` is the falsifier. Whether the sysprompt has a list-cap instruction overlooked — the sysprompts read this session (`m_topn_open_invoices`, `m_count`, `m_aggregation`) cover scoped shapes only; a full sweep of the parser_context bundle for "top N" not on the aggregate path was not run. Whether the fix should apply to every list tool or only CreditMemo — the schema-gap shape is uniform across list tools (`search_suppliers`, `search_purchase_orders`, `search_invoices`, `search_addresses`, `search_standard_receipts`, `list_receivables_credit_memos`), so a general fix is the more honest one, but the finding as written covers only the one reproducer. Whether the parser prompt is truly at its token ceiling (the handoff asserts it; not re-measured this session).

**Class note.** Parallel to F-001 in shape — both concern a signal that the parser needs to produce but currently cannot. F-001's is a flag declared and never written (`_is_explicit_po_list` has no caller); this is a signal with no field at all. Both leave the planner with a gap it cannot close from the intent alone, and both route to a deterministic post-parse helper as the smallest fix (the pattern `parser.py` already uses for `_is_explicit_po_list`, `expand_field_synonyms`, `correct_include_from_prompt`, `strip_po_supplier_include`).

---

## F-017 — `Description` on a PO-lines include is classified unresolved because the field-split checks only the target entity's column catalog

**Date:** 2026-09-18
**Status:** root-caused, not fixed
**Cross-refs:** B-22, F-014 (adjacent), B-15 (adjacent)

**Evidence.**

Runtime, the audit's reproducer:

```
$ python scripts/promptkit.py --run --prompt "Show PO 2144 and its lines with description" --show-stages
Router: modules=['procurement']
Intent:
  target_entity: PurchaseOrder
  filters:
    - {'type': 'by_id', 'value': '2144'}
  include: ['PurchaseOrderLine']

Plan:
  Step 1: get_purchase_order_by_id
  Step 2: get_purchase_order_lines

Outputs:
  po: 1 record(s)
  purchaseorderline: 2 record(s)
    [1] {'POLineId': 19782, ..., 'Description': 'Marketing Assistance'}
    [2] {'POLineId': 19783, ..., 'Description': 'Marketing Assistance'}

Answer:

Note: the following column isn't available on PurchaseOrder: 'Description'.
Available columns: BuyerId, CreatedBy, CreationDate, CurrencyCode, LastUpdateDate, LastUpdatedBy, OrderNumber, Ordered, POHeaderId, Status, StatusCode, SupplierId, Total, TotalTax.

(2 record(s) matched; no requested column was available.)
```

The `Description` value is present on both rows of the fetched line bucket. The answer announces it as unavailable, against the wrong entity's column list.

Direct parse, to resolve which layer inserted the "unresolved" classification:

```
$ python - <<'PY'
from spire.nl_parser.parser import parse
from spire.nl_parser.vocabulary import load_kg_menu
r = parse("Show PO 2144 and its lines with description", menu=load_kg_menu())
print("fields :", r.intent.fields)
print("unresolved_fields:", r.intent.unresolved_fields)
PY
fields : []
unresolved_fields: ['Description']
```

`fields=[]` after parse means the split ran (Step 4 only fires when `intent.fields` is truthy) and emptied the list. The parser had `Description` in `fields`; the split moved it.

Static:

- `src/spire/nl_parser/intent_validation.py::validate_intent`, Step 4:
  ```python
  if intent.fields:
      satisfied_by_include: set[str] = set()
      for inc in intent.include:
          satisfied_by_include |= _FIELDS_SATISFIED_BY_INCLUDE.get(inc, set())
      known: list[str] = []
      unresolved: list[str] = []
      for col in intent.fields:
          if col.lower() in satisfied_by_include:
              continue
          (known if menu.is_known_field(entity, col) else unresolved).append(col)
      intent.fields = known
      intent.unresolved_fields = unresolved
  ```
  `entity` is `intent.target_entity` (`PurchaseOrder`). `menu.is_known_field('PurchaseOrder', 'Description')` returns False — correct, `Description` is not a PO column — so the field moves to `unresolved_fields`.
- The `satisfied_by_include` escape hatch exists but `_FIELDS_SATISFIED_BY_INCLUDE` is a manually curated map with one entry, `{"Address": {...}}`. `PurchaseOrderLine` is not in it, so the include's own column catalog is never consulted. The map's comment explains why Address is there: for the case where a field the include renders (the supplier's country when Address is included) would otherwise be reported missing. The same reasoning applies to any included child, but only Address is handled.

Identity note. §B.1's B-22 row records the class ("7 prompts across `11_column_vocabulary.txt` asking for child-entity fields", Actual "Refusal listing target-entity columns") and the audit's note says "Projection validation runs against the **target entity**, not the included child." Same shape, same answer, live reproduction this session. Taken as the same bug on the same grounds as F-006 through F-016.

**Root cause.** The Step 4 field-split checks requested columns against the target entity's catalog only. It does not consult the catalogs of any included child entity. A field that exists solely on the child (`PurchaseOrderLine.Description`) is therefore classified as unresolved. The display then renders the miss against the target's column list, and the availability note reads as if the field were nowhere in the schema — while the answer's own child bucket carries it. The parser and planner did their jobs: the include was requested, the child rows were fetched, and the column is present in the output.

**Fix location (for Phase 2).** One of two, and (2) is the general fix:

1. **Extend the manual map.** Add each includeable child's field catalog to `_FIELDS_SATISFIED_BY_INCLUDE` in `intent_validation.py`. Mirrors the existing `Address` entry. Cost: a manually maintained table that has to stay in sync with `kg_entity_field`, and it must be extended for every new include added to the KG. This is the same pattern that has already drifted in the KG row-count bookkeeping.

2. **Consult the include's catalog.** Change the split to check the target entity's catalog AND, for each entity in `intent.include`, that entity's catalog (`menu.is_known_field(inc, col)`). A column that matches any included entity is treated as resolvable-to-child rather than unresolved. The `satisfied_by_include` map can then be retired (its Address entry falls out of the general rule for the same reason — the field is on an include). Cost: a small change to `validate_intent`, no schema change. Recommended over (1).

Option 2 is the honest fix because it retires a manual map rather than growing it, and because the same class of failure will recur for every future include if the split keeps checking one entity only.

**Regression test (either fix).** Assert that `Show PO 2144 and its lines with description` produces an intent whose `unresolved_fields` does NOT contain `Description` (it matches `PurchaseOrderLine.Description` via the include), and whose answer contains the line description column. Assert that a genuinely-unknown column (`quantum flux`) is still classified unresolved and surfaced in the note. Both must pass.

**Not checked.** Whether all 7 audit prompts in `11_column_vocabulary.txt` share the same shape — one reproducer run this session, the audit's "7 prompts" is the class claim. Whether the `_FIELDS_SATISFIED_BY_INCLUDE` map was intended to grow or was deliberately scoped to Address — no git archaeology. Whether the AR side has an analogous failure (`ReceivablesInvoiceLine.LineNumber` requested on a `ReceivablesInvoice` target, etc.) — same shape, unrun. Whether `menu.entity_columns` carries every includeable child's columns — the loader reads `kg_entity_field` generically, so likely yes; not exhaustively checked.

**Class note.** Adjacent to F-014 — both about a requested `fields` entry not reaching the answer. Different mechanisms: F-014's projection was applied to the wrong bucket (the aggregate wrapper); this one's classification was made against the wrong entity's catalog (the target instead of the include). Both produce an empty or unavailable column where the data was present.

---

## F-018 — user-supplied invoice number dropped; refusal claims they didn't say which invoice and offers a filter the pipeline can't accept

**Date:** 2026-09-18
**Status:** root-caused, not fixed
**Cross-refs:** B-24, F-001 / B-13 (parallel), F-006 (adjacent), F-011 (adjacent)

**Evidence.**

Runtime, the audit's reproducer:

```
$ python scripts/promptkit.py --run --prompt "show details for invoice number LEE-01-1006-111" --show-stages
Router: modules=['payables']
Reason:   I can look up supplier invoices, but this doesn't say which one.

Solution: Name the supplier, or give me the invoice number.

Example:  invoices for Lee Supplies
  (refusal: missing_identifier — Invoice root has no supplier reference)
```

The value `LEE-01-1006-111` is a real InvoiceNumber on this pod. From F-012's own evidence run, the same value appears as `LEE-01-1006-111 → InvoiceId 489503 → Lee Supplies → 2016-10-17, amount 11138.34 USD`. The user named a specific record.

Two things are false about the rendered refusal:

- *"this doesn't say which one"* — the user said which one, in the InvoiceNumber field.
- *"give me the invoice number"* — the pipeline cannot accept an invoice number at any layer (below).

Static — four sites, each necessary for the observed refusal:

- `src/spire/nl_parser/context/payables/b_invoices_for_supplier.sysprompt` — the only Invoice-by-identifier rule. It names `supplier` (name or number) and `purchase_order`. No rule for "invoice number N". The parser had no instruction to emit anything for `LEE-01-1006-111`.
- `scripts/sql/kg_schema.sql`, `kg_entity_filter` seed — Invoice has rows for `invoice_date`, `invoice_amount`, `supplier`, `purchase_order`. No `invoice_number` row, no `by_id` row.
- `src/spire/mcp_server/tools/invoices.py::search_invoices` — the argument list is `purchase_order`, `supplier_number`, `supplier_name`, `invoice_date_after`, `invoice_date_before`, `amount_min`, `amount_max`, `limit`. No `invoice_number`. `InvoiceNumber` is in `_PROJECTED_FIELDS` (fetched as output) but not in `matches()` and not a candidate for the server-side `q=` clause.
- `src/spire/planner/planner.py::generate_plan` — the Invoice guard:
  ```python
  if intent.target_entity == "Invoice":
      has_supplier = any(
          f.get("type") in ("supplier", "purchase_order") for f in intent.filters
      )
      if not has_supplier:
          raise RefusalError(
              Refusal(
                  flavor=RefusalFlavor.MISSING_IDENTIFIER,
                  detail="Invoice root has no supplier reference",
                  offending_entity="Invoice",
              )
          )
  ```
  The guard's rule is correct given the capability it protects; it fires on the intent it received.

The Solution/Example come from `capability.py::_IDENTIFIER_GUIDANCE["Invoice"]`:
```python
"Invoice": (
    "Name the supplier, or give me the invoice number.",
    "invoices for Lee Supplies",
),
```

Identity note. §B.1's B-24 row records this prompt, its "Invoice root has no supplier reference" refusal, and the audit's own observation ("the suggested fix is 'give me the invoice number,' **which the user already did**"). Same prompt, same refusal, live reproduction this session. The audit classifies it as "wrong-refusal (invoice number not recognised as an identifier)". Taken as the same bug on the same grounds as F-006 through F-017.

**Root cause.** Two mechanisms, and either alone would produce the observed wrong refusal:

1. **Missing capability.** The pipeline has no path at any layer for filtering invoices by InvoiceNumber. The parser sysprompt has no rule for the shape; the KG has no `invoice_number` filter; the tool has no argument to receive it. The parser therefore produced a filter-less Invoice intent (correctly, given what it had to work with), and the planner's guard fired on the shape it saw.
2. **Misleading refusal message.** `_IDENTIFIER_GUIDANCE["Invoice"]`'s Solution offers "give me the invoice number" as a valid path. It is not. The Solution was authored when the guard's reason was thought to be "no identifier named" — but the pipeline cannot service invoice-number lookup even when one is named. The message reads as an invitation to retry a query that will produce the identical refusal.

Combined, the user is told they didn't do something they did, and directed to do it again.

**Fix location (for Phase 2).** Three options, the phase picks:

1. **Close the capability gap (fullest fix).** Add `invoice_number` to `search_invoices`'s arguments and `matches()`, add the KG `invoice_number` filter row, add a parser sysprompt rule for "invoice number X" phrasing. Smallest gap-fill: `InvoiceNumber` is already in `_PROJECTED_FIELDS`; the tool only needs a server-side `q=InvoiceNumber='...'` clause and a client-side match. Cost: touches a sysprompt (token-ceiling risk per the handoff's warning) and a KG seed. Benefit: the user's question becomes answerable.

2. **Correct the message (smallest honest fix).** Change `_IDENTIFIER_GUIDANCE["Invoice"]`'s Solution to not offer a path that does not exist — e.g. *"Name the supplier, or the PO the invoice references."* The message becomes honest about what the pipeline can accept. Cost: the user still cannot ask their question. This is the honest minimum when the capability is not being added.

3. **Route via a lookup.** If the pod accepts `q=InvoiceNumber=...` on `/invoices` (unverified — the endpoint reference has no note), the tool could resolve the invoice number to an InvoiceId via a probe call, then return the single record. This is the fix that mirrors `get_purchase_order_by_id`'s dual-path resolver (OrderNumber first, then POHeaderId). More code than (1), no KG change needed if the resolver is internal to the tool.

Option 1 and option 3 both make the user's query answerable; option 2 makes the refusal honest without adding capability. Option 2 is the minimum if only one ships. Options 1 or 3 without option 2 leaves the message still pointing at a path that may fail — because even with `invoice_number` supported, the message offers it alongside `supplier` as if either worked in any context.

Honest sequencing: (2) first (small, correct the false claim), then (1) or (3) (larger, add the capability). Doing (1) alone leaves the "name the supplier, or give me the invoice number" wording, which now at least names a working path.

**Regression test (either fix).**
- For option 2: assert the Solution text no longer names "invoice number" as a path.
- For options 1 or 3: assert that `show details for invoice number LEE-01-1006-111` returns the record (InvoiceId 489503, supplier Lee Supplies) instead of refusing. Assert that `show details for invoice number NONEXISTENT-99` returns an honest "no such invoice" rather than the same guard refusal.

**Not checked.** Whether the pod accepts `q=InvoiceNumber='...'` on `/invoices` — the endpoint reference has no note; a single curl would settle it and would determine whether option 1 or option 3 is the simpler path. Whether the audit's B-22 class (`11_column_vocabulary.txt` prompts with child-entity fields) and this finding share a broader pattern — "identity columns that are projected but not filterable" — `InvoiceNumber` is projected but not filterable; sibling cases exist (AR invoice's `TransactionNumber`, AR line's `CustomerTransactionLineId`) but were not swept. Whether the parser sysprompt has any rule for "invoice N" phrasing that I overlooked — the parser_context bundle's payables blocks were read; the answer is no. Whether the refusion wording change in `_IDENTIFIER_GUIDANCE` has knock-on effects on other entities — the map is keyed by entity, and this finding touches only the Invoice entry.

**Class note.** Parallel to F-001 / B-13 in shape: a signal that needs wiring up in more than one place. F-001's was a flag declared but never set; this is an identifier a user provides that no layer can receive. Both leave the pipeline unable to service a question the user asked plainly, and both end in a refusal that does not reflect what the user said.

---

## F-019 — account number routed into `by_customer_name`; the empty-bucket shortcut narrates "no customer accounts found"

**Date:** 2026-09-18
**Status:** root-caused, not fixed
**Cross-refs:** B-25, D-13 (paired), F-018 (parallel), F-009 (adjacent)

**Evidence.**

Runtime, the audit's reproducer:

```
$ python scripts/promptkit.py --run --prompt "Trace receipt applications for account 25750" --show-stages
Router: modules=['receivables']
Intent:
  target_entity: CustomerAccount
  filters:
    - {'type': 'by_customer_name', 'value': '25750'}
  include: ['AccountReceiptApplication']

Plan:
  Step 1: get_customer_account_by_name
    tool_args:      {'customer_name': '25750'}
  Step 2: get_account_receipt_applications
    iterate_over:   {'from_step': 'customer_accounts', 'field': 'AccountId'}

Outputs:
  customer_accounts: 0 record(s)
  account_receipt_applications: 0 record(s)

Answer:
No customer accounts found matching the criteria.
No customer accounts found.
```

The filter type is `by_customer_name`. The value is `25750` — a number. Step 1 calls `get_customer_account_by_name(customer_name='25750')`, whose `q=` is `CustomerName='25750'`. No customer is named "25750". Zero rows. Step 2 iterates over the empty parent bucket; zero calls, zero rows. The empty-bucket shortcut narrates a clean "no customer accounts found".

Static — four sites, each necessary:

- `src/spire/nl_parser/context/receivables/b_receipt_applications.sysprompt` — the only rule for receipt-applications queries. It names `by_customer_name` as the required filter and gives only customer-name phrasings. No rule for "account N" as an account number.
- `src/spire/nl_parser/draft.py::DraftIntent` — no field on the CustomerAccount resolve path carries an account number. The only numeric channel is a filter, and the only resolve filter is `by_customer_name`.
- `src/spire/mcp_server/tools/customer_account_by_name.py::get_customer_account_by_name` — the function signature is `(client, customer_name: str, limit: int = 25)`, and its query is `q=CustomerName='...'`. No `account_number` argument, no `AccountNumber` clause.
- `src/spire/synthesizer/synthesizer.py::synthesize_response` — the `_all_buckets_empty` shortcut narrates "No customer accounts found matching the criteria." with no signal that the identifier was misrouted.

Corroborating asymmetry (from `mcp_server_tools` bundle, read earlier this session): `aggregate_standard_receipts_by_method(client, customer_name=None, account_number=None, limit=None)` accepts **both** a customer name and an account number. `get_customer_account_by_name` accepts only the name. Two paths on the same entity, only one of which can receive a numeric identifier.

Identity note. §B.1's B-25 row records this prompt, the `customer_name='25750'` misrouting, the 0-record outcome, and the audit's own cross-reference to D-13 ("same account produces silent-0 in one prompt, honest refusal in another"). Same prompt, same 0-row result, live reproduction this session. The sibling prompt in D-13 (`Get the most recent standard receipts for account 25750` producing an honest refusal) is cited from the audit, not re-run. Taken as the same bug on the same grounds as F-006 through F-018.

**Root cause.** Two mechanisms, stacked:

1. **Identifier-type mismatch.** The pipeline's CustomerAccount resolve path takes a customer name, not an account number. The parser had no filter to route a numeric account into — the schema has no account-number field, the sysprompt has no rule for the shape, and the tool takes a name only. So it routed the value into `by_customer_name`. The value is preserved; the type is dropped.
2. **Silent narration.** `_all_buckets_empty` narrates the empty result as if the user had asked about a customer name. The user's question was about an account; the message reframes it and answers the reframed one, with no signal that the identifier type was reinterpreted.

Either alone would be a lesser bug. Together, they produce a clean "no customer accounts found" over a query that never looked for accounts by number.

**Fix location (for Phase 2).** Three options:

1. **Add an account-number channel on the resolve path.** Give `get_customer_account_by_name` an `account_number` argument (mirroring `aggregate_standard_receipts_by_method`'s dual-argument shape), add a `by_account_number` filter row to `kg_entity_filter`, and add a sysprompt rule for "account N". The parser would emit `by_account_number='25750'` for this prompt. Cost: sysprompt edit (token-ceiling risk per the handoff's warning), KG seed change, tool-argument addition.
2. **Post-parse deterministic correction.** Extend `parser.py`'s post-parse step (the pattern already used for `_is_explicit_po_list`, `expand_field_synonyms`, `correct_include_from_prompt`, `strip_po_supplier_include`) to rewrite `by_customer_name='<all-digits>'` into an account-number filter, and have the planner route it to a tool that accepts it. Smaller if option 1's resolve-path tool is upgraded; the parser correction alone does nothing without a downstream destination for the filter.
3. **Correct the message (smallest honest fix).** Have the empty-bucket shortcut detect that the filter value is a digit-only string (an account number, not a name) and say so — e.g. *"No customer named '25750' found; account numbers cannot be searched on this path."* The user still cannot ask their question, but the answer stops being a clean false negative.

Options 1 and 3 are complementary; doing both makes the query answerable and the empty case honest. Option 2 without 1 is a no-op (there is no destination for the filter it would create).

The audit's D-13 sibling does the honest thing already — `search_standard_receipts` refuses rather than silently misrouting the account number, because its own guard fires first. The mechanism this finding names is not "the pipeline cannot look up account numbers"; it is "one path silently accepts a number into a name-shaped filter instead of refusing like the other path does."

**Regression test (either fix).** Assert that `Trace receipt applications for account 25750` either (a) resolves the account and returns its applications, or (b) refuses honestly, naming the account number as the identifier it cannot search by. Assert that a genuine customer-name query (`Trace receipt applications for customer ABC Application Software`) still resolves correctly. Both must pass.

**Not checked.** Whether account 25750 exists on this pod — the falsifier, not run; if it does not, the harm reduces to "the message should not have framed the search as a customer-name lookup", which is fix option 3. Whether the D-13 sibling prompt still produces the honest refusal — cited from the audit, not re-run. Whether the fix belongs at the tool, the KG, or a post-parse helper — the phase's call, not this entry's. Whether the same shape affects `b_account_receipts`, `b_customer_credit_memos`, `b_customer_invoices`, and `b_account_balance` — all key on `by_customer_name` with a customer name, all likely to misroute a numeric value identically; not run.

**Class note.** Parallel to F-018 (an identifier the pipeline cannot receive) and F-009 (a rule in the wrong module for the entity it parses). F-018's identifier is an invoice number the pipeline has no argument for; this one is an account number the pipeline has an argument for elsewhere but not here. Both leave the user with a refusal or a false negative that does not reflect what they typed.

---

## F-020 — supplier-contacts summary flattens 47 administrative names into one sentence, unattributed and unverifiable against the tables below

**Date:** 2026-09-18
**Status:** root-caused, not fixed
**Cross-refs:** B-27, F-015 (adjacent), F-010 (adjacent)

**Evidence.**

Runtime, the audit's reproducer:

```
$ python scripts/promptkit.py --run --prompt "Get Supplier contacts" --show-stages
Router: modules=['supplier']
Intent:
  target_entity: Supplier
  include: ['Contact']

Plan:
  Step 1: search_suppliers
  Step 2: get_supplier_contacts  (iterates 25 suppliers, 92 contacts)

Outputs:
  suppliers: 25 record(s)
  contact: 92 record(s)

Answer:
Showing 25 of 593 suppliers. These 25 suppliers have 92 contacts between them.
Lee, Ryan, Lee, Jason, Cross, Sara, Leaf, Jen, Jones, Adam, Bainer, Isla,
Zimmer, Denny, Simon, Eric, Bonnet, Alain, Roux, Patrick, Li, Wen, Goda,
Tetsu, Abate, Luca, Lisi, Gina, Johnson, Karen, Kennedy, Bob, Hickey, James,
Swensen, Lars, Ferrer, Elena, Simon, Rene, Ryan, Jamie, Gray, Jade, Hames,
Jim, Robin, Marie, Gill, Noah, Perez, Jose — administrative contacts.

Suppliers: ...25 rows...
[per-supplier contact tables below, name + email only, no admin marker]
```

47 names in a single comma-separated sentence. The count line (`25 of 593`, `92 contacts`) is correct. Every name is a real contact listed under a real supplier below.

Two harms in one shape:

- **Length.** 47 names is not a summary line. The sentence is unreadable as prose.
- **Attribution.** The sentence says these are "administrative contacts" without saying which supplier each belongs to, and the tables below never mark any contact as administrative. The reader cannot verify the property against the data shown.

Static — two lines in `src/spire/synthesizer/synthesizer.py::synthesize_response`, supplier-contacts branch:

```python
admin_names = [
    c.contact_name
    for r in records
    for c in r.contacts
    if c.is_administrative and c.contact_name
]
...
if admin_names:
    label = "administrative contact" if len(admin_names) == 1 else "administrative contacts"
    summary += f" {', '.join(admin_names)} — {label}."
```

The comprehension flattens across every supplier; the join is unconditional. `is_administrative` itself is read correctly from `AdministrativeContactFlag` in `build_suppliers_with_contacts` (`p2p.py` bundle), so the property is honest — it is the aggregation and rendering that lose the structure.

Identity note. §B.1's B-27 row records this prompt and calls it "run-on narration — new, cosmetic." Same prompt, same sentence shape, live reproduction this session. Taken as the same bug on the same grounds as F-006 through F-019, with one refinement (below).

**Refinement to the audit's classification.** The audit labels B-27 "cosmetic." The attribution half is not merely cosmetic: the sentence asserts `is_administrative=True` for 47 rows, and the reader has no way to check that property against the displayed tables (which show name and email only). The claim may be true — the flag is read from the pod — but it is unverifiable from the answer's own data. That is a small narration defect on its own, separate from the length.

**Root cause.** The supplier-contacts summary flattens the admin-flagged contacts of every fetched supplier into one list and joins them with no cap, no grouping by supplier, and no per-supplier attribution. The structured data carries the supplier↔contact association (each contact row carries a stamped `SupplierId`, per `get_supplier_contacts`'s docstring) and the admin flag (`AdministrativeContactFlag`), but neither is used in the sentence. The result is a 47-name run-on whose assertion the reader cannot check against the tables below.

**Fix location (for Phase 2).** Three options, in increasing effect:

1. **Cap and truncate.** `', '.join(admin_names[:5])` plus " and N more". Reduces the length. Cost: still unattributed; the reader still cannot tell which supplier each named contact belongs to.
2. **Group by supplier.** Compose a per-supplier list: *"Lee Supplies: Lee, Ryan; JGA: Cross, Sara; …"*. Attribution preserved. Cost: still long with 25 suppliers carrying an admin contact each; a cap per supplier or a total cap becomes necessary alongside.
3. **Move to the structured record, remove from the summary.** The `ContactInfo` model already carries `is_administrative` per contact, and the display layer could mark it inline in the contact tables. The summary then says only the count. This makes the property checkable (each contact row shows the flag) and eliminates the run-on entirely.

Option 3 is the more honest fix: the assertion belongs where the reader can check it, and the display format is the natural place. The summary should not carry a claim it cannot support. Options 1 and 2 improve the symptom; option 3 removes it.

Whichever ships, the two harms are addressed differently: length needs a cap; attribution needs either grouping or per-row marking. Only option 3 addresses both.

**Regression test (either fix).**
- For option 1: assert the sentence contains at most N names and "and M more" when admins exceed N.
- For option 2: assert each named contact is preceded by its supplier's name.
- For option 3: assert the contact tables include an administrative marker per row; assert the summary no longer lists individual names.

**Not checked.** Whether the flag `is_administrative` is set to True on many contacts on this pod or few — the sentence's 47 names suggest a majority of the 92; not verified against `AdministrativeContactFlag` in a curl. Whether the same shape affects other synthesizer branches that use `', '.join(...)` over a nested comprehension — the `open_pos` buyers list and possibly the account-child lists follow the same pattern; only this branch was exercised this session. Whether the display formatter could carry the per-contact flag (a rendering-layer change, not read in any bundle this session). Whether the audit's "cosmetic" label was itself intended to be temporary.

**Class note.** Adjacent to F-015 (both are synthesis-layer narration that doesn't reflect what the reader can see: F-015 narrated an incomplete result as complete; this narrates a property the reader cannot check) and F-010 (both concern the summary contradicting the underlying structured data — F-010's summary named an unfiltered count; this one asserts a property not present in the tables).

---

## F-021 — DFF child is fetched but never rendered; `fields` on the parent bucket trims the header, the child bucket does not reach the answer

**Date:** 2026-09-18
**Status:** root-caused (partial); display-side mechanism unresolved
**Cross-refs:** B-23, F-014 (adjacent), F-017 (adjacent), F-015 (adjacent)

**Evidence.**

Runtime, the audit's targeted reproducer (invoice 1002, which carries `__FLEX_Context='DOO'`):

```
$ python scripts/promptkit.py --run --prompt "Show the AR invoice with CustomerTransactionId 1002 with transaction number and flexfield" --show-stages
Router: modules=['receivables']
Intent:
  target_entity: ReceivablesInvoice
  filters: [{'type': 'by_id', 'value': '1002'}]
  include: ['ReceivablesInvoiceTransactionDFF']
  fields: ['TransactionNumber']

Plan:
  Step 1: get_receivables_invoice_by_id
  Step 2: get_receivables_invoice_transaction_dff

Outputs:
  receivables_invoices: 1 record(s)
    [1] {'TransactionNumber': '5'}
  receivablesinvoicetransactiondff: 1 record(s)
    [1] {'CustomerTrxId': 1002, '__FLEX_Context': 'DOO', '__FLEX_Context_DisplayValue': None}

Answer:
[blank]


Answer:
receivables_invoices (1 record(s)) — columns: TransactionNumber

  TransactionNumber
  -----------------
  5
```

Three observations.

- The parser split the request correctly: transaction number → `fields`, flexfield → `include`. Neither channel was empty.
- Both plan steps ran. The DFF bucket holds one row with `__FLEX_Context='DOO'`. The fetch is correct.
- The Answer shows only the transaction number. The DFF is not in the rendered output. The first (synthesized) Answer block is blank; the second (projection table) shows the trimmed header.

**Correction to the audit's framing.** §B.1's B-23 row titles the defect "include dropped by `fields`". The paste shows the include was not dropped — the plan ran both steps and the DFF bucket is non-empty. What is missing is the **rendering** of the DFF, not its fetch.

**Static — one site confirmed, one not located:**

- `src/spire/graph/pipeline.py::_project_outputs` — the header bucket was trimmed to the intent's `fields` (`['TransactionNumber']`), as the Outputs block shows (`{'TransactionNumber': '5'}`). This is the mechanism for the projection table showing only the transaction number.
- The display path that renders a `ReceivablesInvoiceResponse` — **not in any bundle read this session**. `src/spire/rendering/formatters.py` is the file, and I have not read it. Two candidate mechanisms live behind it:
  - If `synthesize_response` took the local-build branch (`single_parent_shape` matched and `build_receivables_invoice_records` ran), then `ReceivablesInvoiceRecord.dff` is populated from the DFF bucket, and the display simply does not print it.
  - If `synthesize_response` fell through to the LLM path (e.g. because `single_parent_shape` did not find its parent markers on the trimmed header row), then whether `dff` was populated depends on what the model did with the DFF bucket in its input. The paste's `Synthesized answer: 1 record(s)` does not distinguish the two.

Identity note. §B.1's B-23 row records this prompt and the outcome ("Only `TransactionNumber`; DFF child not rendered"), and the audit's note asks for "a targeted run on invoice 1002 (DFF 'DOO')". Invoice 1002 is that run. The reproducer strengthens from "DFF value is None in both cases" to "DFF value is 'DOO' at the source and the answer still omits it." Taken as the same bug on the same grounds as F-006 through F-020.

**Root cause (partial).** Two layers, one confirmed and one not:

1. `_project_outputs` trims the target bucket to `intent.fields`. The header row becomes `{'TransactionNumber': '5'}`. This is deliberate — projection is the feature — and is not itself the defect.
2. The answer's rendering surfaces only the projected header columns. The DFF bucket (`receivablesinvoicetransactiondff` with `__FLEX_Context='DOO'`) does not reach any visible output. Whether the DFF was built into the response and dropped at the display, or whether the response was built by the LLM path and never included the DFF, is unresolved.

**Fix location (for Phase 2).** Two candidates; the phase needs the display file to pick.

1. **Synthesizer-side.** `src/spire/synthesizer/synthesizer.py::synthesize_response`, the `ReceivablesInvoice` branch — ensure the local-build path runs even when the header bucket is trimmed (relax `single_parent_shape`'s parent markers to keys that survive projection, or pass the untrimmed bucket to the synthesizer regardless of `fields`). Then `build_receivables_invoice_records` populates `dff` from the DFF bucket, and the display has the data to render. Cost: a marker change or a state-plumbing change; local.
2. **Display-side.** `src/spire/rendering/formatters.py` — render the `ReceivablesInvoiceRecord.dff` field when it is populated. Requires reading the file. If `dff` is already populated and simply not rendered, this is the minimal fix.

Whichever resolves the observed symptom, both are warranted: the synthesizer path should still produce a complete record even with projection applied, and the display should render the DFF when it is present.

**Regression test (either fix).** Assert that `Show the AR invoice with CustomerTransactionId 1002 with transaction number and flexfield` returns an answer containing the DFF context (`DOO`). Assert that `Show the AR invoice with CustomerTransactionId 1002` (no `fields`, no include) still returns the standard invoice header. Both must pass.

**Not checked.** The `rendering` bundle — not read this session; the display-side mechanism is unresolved as stated. Whether `synthesize_response` took the local-build path or the LLM path for this intent — the paste is ambiguous; a trace with `--show-tracer` or an instrumented run would say. Whether `state["outputs"]` (read by `synthesize_node`) is trimmed or untrimmed — `execute_node` returns both `outputs` and `projected_outputs`, and the Outputs block shows the trimmed one, but I do not know which the printout surfaces. Whether the same defect affects a `fields` + include combination for PO lines, schedules, AR lines, AR tax lines — same shape, unrun. Whether the blank first Answer block has a separate mechanism — `local_list_summary` returns `[]` for a single-row set (its own documented behaviour: "One row generalises about nothing"), so the joined summary is empty; that is a characteristic of the single-row case, not the DFF omission, but it is what makes the summary block blank here.

**Class note.** Adjacent to F-014 (both are `fields` interacting with a target bucket that carries richer data than the projection preserves) and F-017 (both are `fields` interacting with a child include). F-014's was an aggregate wrapper; F-017's was a wrong-catalog classification; this is a fetched child that never reaches the answer. Three variations on the same theme: when `fields` and the response shape disagree about what the answer should contain, the shape loses.

---

## F-022 — `Show PO 2144 and its distributions` is deterministic at N=20; B-10's ~14% intermittent failure does not reproduce

**Date:** 2026-09-18
**Status:** closed-as-not-a-bug
**Cross-refs:** B-10

**Evidence.**

Twenty runs of the audit's own reproducer, five in one loop and fifteen in a second, all with `--show-stages`:

```
$ for i in 1 2 3 4 5; do
    echo "=== run $i ==="
    python scripts/promptkit.py --run --prompt "Show PO 2144 and its distributions" --show-stages 2>&1 \
      | grep -E "^  Records returned:|^  Final raw output:|No POs found|No purchase orders|found: False"
  done
=== run 1 ===
  Records returned:     5 (across all steps)
  Final raw output:     2 record(s) under 'podistribution'
...
=== run 5 ===
  Records returned:     5 (across all steps)
  Final raw output:     2 record(s) under 'podistribution'

$ for i in 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    ... same prompt ...
  done
=== run 6 ===
  Records returned:     5 (across all steps)
  Final raw output:     2 record(s) under 'podistribution'
...
=== run 20 ===
  Records returned:     5 (across all steps)
  Final raw output:     2 record(s) under 'podistribution'
```

All twenty runs produced `Records returned: 5` and `Final raw output: 2 record(s) under 'podistribution'`. No run produced `No POs found`, `No purchase orders`, or `found: False`. No run had an empty step.

Contrast with the audit's B-10 row:

> `Show PO 2144 and its distributions` is intermittent. 1 failure in 7 (~14%). Step 1 returns empty; downstream steps empty; synthesizer prints "No POs found." `cache_mode: None` confirms execution cache not involved. Needs N ≥ 20.

The audit set its own threshold for this row at N ≥ 20. Twenty runs met it; all were clean.

Statistical note. Under a 1-in-7 (≈14%) failure rate, P(zero failures in 20 runs) ≈ 0.857²⁰ ≈ 4.6%. The original observation is unlikely under the current behaviour. A rate as high as ~14% is not formally excluded by 20 clean runs (one-sided 95% upper bound at 0/20 is ~14%), but the point estimate is zero and the audit's specific failure shape has not recurred across the required sample.

**Root cause.** Not established — the failure did not reproduce. Candidate mechanisms were not investigated because there was nothing to investigate: no failing run to trace.

**Fix location.** None — closed.

**Re-open criteria.** Any of the following would justify reopening B-10:

- A future run of the prompt (or a close paraphrase) producing `Records returned: 0` or the "No POs found" text.
- A change to `purchase_order_distributions`'s fetch path, `purchase_orders`'s `page_all` use, or the executor's iteration for multi-field steps (`HAS_DISTRIBUTION`'s `iter_fields` branch).
- Evidence that the failure is time-of-day, load, or pod-state dependent, which a single N=20 window cannot rule out.

**Not checked.** Whether the pod changed between the audit's original observation and this session — no git archaeology and no pod-state comparison. Whether the failure is load-dependent (this session's twenty runs were sequential and unloaded) or time-of-day dependent. Whether the audit's original observation was made under different `promptkit.py` flags, a different pod, or a different MCP server build — the audit's row records `cache_mode: None`, which is the same invocation shape used here, but nothing about the other conditions. The two other prompts in the same nondeterminism class (B-21's supplier spend totals, B-c2's supplier count) — separate loops, not run this session.

**Class note.** This closes only B-10. The remaining nondeterminism rows (B-21, B-c2, B-c4) are independent reproducers; a clean result here does not imply they are clean. B-c4's own audit note ("Consider collapsing once mechanisms are understood") applies to B-21/B-c2, not to this closure — the mechanisms were never established because the symptom was not reproduced.

---

## F-023 — supplier spend ranking is stable across 20 same-phrasing runs and across the audit's cross-phrasing pair; B-21 does not reproduce

**Date:** 2026-09-18
**Status:** closed-as-not-a-bug
**Cross-refs:** B-21, F-022 (same class, same session)

**Evidence.**

Same-phrasing loop, 20 runs of the audit's first phrasing:

```
$ for i in 1 2 3 4 5; do
    python scripts/promptkit.py --run --prompt "Top 10 suppliers by spend in 2022" --show-stages 2>&1 \
      | grep -E "leads with|^  Records returned:|Top [0-9]+ of"
  done
=== run 1 ===
Top 10 of 50 suppliers by spend.
EIP Inc leads with 141,171,590.98 — 3.3x the next.
  Records returned:     1 (across all steps)
...
=== run 5 ===
Top 10 of 50 suppliers by spend.
EIP Inc leads with 141,171,590.98 — 3.3x the next.
  Records returned:     1 (across all steps)

$ for i in 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    ... same prompt ...
  done
=== run 6 ===
... (identical) ...
=== run 20 ===
Top 10 of 50 suppliers by spend.
EIP Inc leads with 141,171,590.98 — 3.3x the next.
  Records returned:     1 (across all steps)
```

All 20 runs: `Top 10 of 50 suppliers by spend.` / `EIP Inc leads with 141,171,590.98 — 3.3x the next.` / `Records returned: 1`. Byte-identical.

Cross-phrasing run, the audit's paired prompt:

```
$ python scripts/promptkit.py --run --prompt "Which suppliers did we spend the most with in 2022" --show-stages
Router: modules=['supplier']
Intent:
  target_entity: Supplier
  aggregate: {'op': 'by_supplier', 'date_from': '2022-01-01', 'date_to': '2023-01-01', 'top_n': 10}

Outputs:
  aggregation: 1 record(s)
    [1] {'shape': 'supplier_spend_ranking', ..., 'total_suppliers': 50, 'returned': 10, 'truncated': False}

Answer:
Top 10 of 50 suppliers by spend.
EIP Inc leads with 141,171,590.98 — 3.3x the next.

Top suppliers by spend:
  Rank | Supplier            | SupplierNumber |    Total Spend | Invoices
  -----+---------------------+----------------+----------------+---------
     1 | EIP Inc             | 1262           | 141,171,590.98 |      261
     2 | Staffing Services   | 1253           |  42,480,855.33 |      122
     3 | CDW                 | 1295           |  32,963,913.70 |       78
     4 | JGA                 | 1254           |  28,905,113.17 |      227
     5 | Advanced Corp PK    | 1263           |  18,624,046.35 |      169
     ...
```

Identical `aggregate` block (same op, same date range, same `top_n`), identical `total_suppliers` (50), identical leader (EIP Inc), identical leader total (141,171,590.98), identical ratio (3.3x).

Contrast with the audit's B-21 row:

> `Top 10 suppliers by spend in 2022` vs `Which suppliers did we spend the most with in 2022` | Same totals | Different totals and invoice counts | Same class as `/standardReceipts` ordering instability. Needs N ≥ 20.

Both halves of the claim fail to reproduce: same-phrasing variance is zero at the audit's own N=20 threshold, and the cross-phrasing pair produces identical outputs.

Corroborating detail. The two phrasings routed to different module sets — the first was `['procurement', 'supplier']` (from the F-004 evidence run), the second `['supplier']` — while producing identical intents. This matches the handoff's observation that the router's module set is a diagnostic breadcrumb and not a correctness signal (`docs/SPIRE_SESSION_HANDOFF.md`, "the module set does NOT affect the answer"). The two routers picked differently; the answers were byte-identical.

**Root cause.** Not established — the failure did not reproduce. The audit's named mechanism ("same class as `/standardReceipts` ordering instability") is a hypothesis about `page_all` pagination without an explicit `orderBy`; the code does omit an `orderBy` (`mcp_server/tools/pagination.py::page_all` sends only `limit`, `offset`, `onlyData`, `totalResults`, optional `q`, optional `fields`). The observation that motivated the ordering fix was made against `/standardReceipts`; this loop is the first empirical data on `/invoices`, and 20 same-phrasing runs plus one cross-phrasing run saw identical rows.

**Fix location.** None — closed.

**Re-open criteria.** Any of:

- A same-phrasing run of `Top 10 suppliers by spend in 2022` showing a different `total_suppliers`, different leader, or different leader total.
- A cross-phrasing run of the paired prompt diverging from the reference output above.
- A change to `mcp_server/tools/aggregate_invoices.py`, `mcp_server/tools/pagination.py`, or the pod's `/invoices` default ordering.
- A demonstrated `/invoices` default-ordering instability from an independent test (e.g. two `?limit=1` calls returning different rows under no clause).

**Not checked.** Whether `/invoices` has a stable default ordering at the API level — this loop shows the aggregation is stable *in practice*, not that the endpoint guarantees it; the `page_all` no-`orderBy` code path is still exposed if the pod's default ever changes. Whether `aggregate_standard_receipts_by_method`'s explicit `orderBy=StandardReceiptId` fix is necessary on the other paginated collections (`/purchaseOrders`, `/invoices`) — the fix was made where instability was observed; this loop shows no instability on `/invoices` under current conditions, which is different from proving the fix is unnecessary. The invoice counts across all 20 same-phrasing runs — the leader line does not print them; only the cross-phrasing run's table did, and it matched the ratio. Whether the observation window (same session, same pod, sequential, unloaded) is representative — a load or time-of-day effect would not have appeared here. The third nondeterminism row, B-c2 (supplier count varies across files) — a separate loop, not run.

**Class note.** Second of the session's three nondeterminism rows to close clean at N=20. F-022 closed B-10 (intermittent PO distributions) with the same result. The pattern across both: the audit's observations were real at the time they were made, but neither reproduces under the current code and pod. Whether B-c2 (supplier count variance) shares the outcome is the remaining test; its mechanism is more likely to be the insertion-order bias in the supplier scan than the pagination question here, so the two are not necessarily the same class.

---

## F-024 — `count of suppliers` is stable at 600 across 20 runs; B-c2's variance is cross-prompt plus pod growth, not same-prompt instability

**Date:** 2026-09-18
**Status:** closed-as-not-a-bug
**Cross-refs:** B-c2, B-c4, F-022, F-023 (same session, same class)

**Evidence.**

Twenty runs of the audit's simplest count prompt, same invocation:

```
$ for i in $(seq 1 20); do
    python scripts/promptkit.py --run --prompt "count of suppliers" --show-stages 2>&1 \
      | grep -E "^Answer:|^There are|^  Records returned:|^  Final raw output:"
  done
=== run 1 ===
Answer:
There are 600 suppliers.
  Records returned:     25 (across all steps)
  Final raw output:     25 record(s) under 'suppliers'
...
=== run 20 ===
Answer:
There are 600 suppliers.
  Records returned:     25 (across all steps)
  Final raw output:     25 record(s) under 'suppliers'
```

All 20 runs: `There are 600 suppliers.` / `Records returned: 25` / `Final raw output: 25 record(s)`. Byte-identical.

Contrast with the audit's B-c2 row:

> Supplier count across runs | 452 / 453 / 450 / 455 observed across the audit. Plausibly correct; belongs in §H until N-run evidence.

The audit's own note ("Some variation is legitimate (`status=ACTIVE` vs unfiltered); some may be pod growth during the audit") anticipates two explanations. This loop confirms the first — same-prompt count is stable — and corroborates the second.

Pod-growth corroboration. Three observations of the supplier count from different sessions:

| Source | Count | When |
|---|---|---|
| Audit §B.1 (B-c2 row) | 452 / 453 / 450 / 455 | During the audit |
| F-008's truncation note this session | 593 | Earlier today |
| This loop (N=20) | 600 | Now |

Monotone increase over the audit's lifetime, consistent with data being added between sessions. The cross-file variance the audit saw (452 vs 455) is compatible with the same growth over the audit's own multi-day run, not with same-prompt instability.

**Root cause.** Not a bug. The count `600` comes from the pod's own `totalResults` (read from the fetch's first page by `FusionClient.total_results` / `page_all`), not from `len(rows)` — the count is authoritative and the 25-row sample is what the pipeline fetched to obtain it. No same-prompt instability exists at N=20.

**Fix location.** None — closed.

**Re-open criteria.** Any of:

- A same-prompt run of `count of suppliers` producing a different count within a single session (same pod state).
- A demonstrated same-prompt count variance on `List active suppliers` or any other filtered variant of the count query — the loop above tested only the unfiltered form.
- Evidence that `totalResults` on `/suppliers` is unreliable (e.g. two `?limit=1&totalResults=true` calls returning different totals under identical clauses).

**Not checked.** Whether the *filtered* count queries (`count of active suppliers`, `count of suppliers in US`) are equally stable — one prompt tested, not the class. Whether `List active suppliers`'s answer count matches the count-query count for the same filter — the audit's 450 vs 455 pair came from different prompts, and the loop above did not compare them. Whether the pod growth is monotone at finer time resolution — three data points are not a growth curve; only enough to corroborate the audit's own hypothesis. Whether the count varies across the specific prompt-set files the audit sampled (450 in `01_supplier`, 453 in `01_supplier`, 455 in `qa_testcases`) — those were full-list prompts, not the count prompt, and their file-to-file difference is a separate question from same-prompt stability.

**Class note.** Third nondeterminism row closed clean this session, alongside F-022 (B-10, PO distributions) and F-023 (B-21, supplier spend ranking). The pattern is now: none of the three reproducers of the audit's nondeterminism class reproduce at N=20 under the current code and pod. B-c4 — the audit's own note, *"Consider collapsing once mechanisms are understood"* — now has a partial answer: the four sub-rows were examined (three closed clean, one being this one), and no mechanism was established because no symptom was reproduced. Collapsing is therefore the honest outcome, not because the mechanisms were unified, but because there was nothing to unify.

**Closure of B-c4 as a class note.** B-c4 is not a separate reproducer; it is the audit's own bookkeeping suggestion that B-10, B-12, B-19, B-21, B-25 be considered one class ("Same root as B-10, B-12, B-19, B-21, B-25"). Of those:

- **B-10** — closed clean (F-022).
- **B-12** — `How does invoiced compare to ordered for Lee Supplies?` returns "fully invoiced" over a zero-PO `po_count: 0`. Not looped, but the specific shape (vacuous zero-equals-zero) is a distinct mechanism from the sampling-instability class B-c4 was grouping under. Belongs with the compare-path findings, not with nondeterminism.
- **B-19** — closed with F-015 (the empty-bucket-discards-truncation mechanism).
- **B-21** — closed clean (F-023).
- **B-25** — closed with F-019 (account number misrouted into `by_customer_name`).

So B-c4's proposed grouping does not hold: the five rows collapsed into three different mechanisms (one cleanup of a truncation-flag discard, one identifier-misrouting, three nondeterminism rows that did not reproduce). B-c4 closes as an observation whose underlying hypothesis (a shared root) is disproven by the individual closures — not because the class was unified but because it split.

---

## F-025 — PO queries cannot reach the supplier's address or classifications by design; the honest refusal is not a bug

**Date:** 2026-09-18
**Status:** closed-as-not-a-bug
**Cross-refs:** B-15, F-017 (adjacent), F-009 (parallel)

**Evidence.**

Runtime, the most pointed of `12_po_supplier_include.txt`'s dangerous-end prompts:

```
$ python scripts/promptkit.py --run --prompt "PO 701337 including the supplier's address and classifications." --show-stages
Router: modules=['procurement', 'supplier']
Intent:
  target_entity: PurchaseOrder
  filters:
    - {'type': 'by_id', 'value': '701337'}

Plan:
  Step 1: get_purchase_order_by_id
    tool_args:      {'po_header_id': '701337'}

Outputs:
  po: 1 record(s)
    [1] {'POHeaderId': 300000081255594, 'OrderNumber': '701337', 'Status': 'Open',
         'Supplier': 'JGA', 'SupplierId': 300000047414635}
        ... +17 more field(s): ..., SupplierContactDisplayName, SupplierSite, Total, TotalTax

Answer:

Note: the following columns aren't available on PurchaseOrder: 'supplier_address', 'classifications'.
Available columns: BuyerId, CreatedBy, CreationDate, CurrencyCode, LastUpdateDate, LastUpdatedBy, OrderNumber, Ordered, POHeaderId, Status, StatusCode, SupplierId, Total, TotalTax.

(1 record(s) matched; no requested column was available.)
```

Three observations.

- The plan is `by_id` only. No traversal step. The PO header bucket is fetched; the answer's underlying data is correct.
- The Intent block shows no `fields` on the intent — but the Answer's "columns aren't available" note only prints when `unresolved_fields` is non-empty, which only populates when `validate_intent`'s Step 4 ran, which only fires when `intent.fields` was non-empty at entry. The parser set `fields` (something like `['supplier_address', 'classifications']`); the split moved both to `unresolved_fields`; the display reported them against `PurchaseOrder`'s column catalog.
- The refusal is honest. `supplier_address` and `classifications` are not columns on `PurchaseOrder`. The message is accurate.

Static — the design is coherent at every layer:

- `src/spire/nl_parser/context/procurement/b_po_supplier_details.sysprompt`:
  > *"'supplier details for PO X' / 'show the supplier on PO X' / 'who is the supplier on PO X' → target_entity 'PurchaseOrder' with a 'by_id' filter. **Do NOT add 'Supplier' to include**; the supplier name, number, site and contact are projected directly from the PO header by the by_id fetcher."*
- `src/spire/nl_parser/vocabulary.py::strip_po_supplier_include` — the deterministic defence. Removes `Supplier` from any PO intent's include list, gated on `menu.has_edge('PurchaseOrder', 'Supplier')` returning False.
- `scripts/sql/kg_schema.sql` — no `PurchaseOrder → Supplier` edge, no `PurchaseOrder → Address` edge, no `PurchaseOrder → Classification` edge. The children edges are all **from Supplier**: `HAS_ADDRESS`, `HAS_SITE`, `HAS_CLASSIFICATION`, `HAS_CONTACT`.
- `src/spire/planner/plan_builders.py::_build_entity_fetcher_args` — with no include, no traversal, only `by_id`. The tool fetches the header, which carries `Supplier`, `SupplierSite`, `SupplierContactDisplayName`.

Contrast with the audit's B-15 row:

> B-15 | missing-capability (include never fires) | 12 prompts across `12_po_supplier_include.txt` and `11_column_vocabulary.txt` | Traversal to the supplier (and children) from the PO | PO header inline fields only; no edge traversal fires | KG declares `HAS_SITE`, `HAS_CONTACT`, `HAS_CLASSIFICATION`, `HAS_ADDRESS`, **reachable from `PurchaseOrder.SupplierId`**.

The audit's "verify" column asserts a hop ("reachable from `PurchaseOrder.SupplierId`") that the KG does not declare. There is no `PurchaseOrder → Supplier` edge; there are edges from `Supplier` to the entities the audit names. The audit's phrasing glosses the missing hop.

**Root cause of the (now-closed) prior claim.** The behaviour the audit observed is real — no traversal fires — but is the design, not a defect. Three places state it: the sysprompt says "do NOT add 'Supplier'"; the strip function enforces the rule; the KG omits the edge. The PO header carries the supplier name, number, site, and contact person inline — the four items that would most commonly be asked about a PO's supplier. Anything beyond that (addresses, classifications, the full contact list) lives on the `Supplier` entity, which is not reachable from a PO in this design.

The parser's fallback — translating the deeper asks into `fields` that the field-split then reports as unresolvable — is the honest path. The alternatives would be either the S1 crash shape (include fires, planner KeyErrors) or a silent empty answer (include is stripped and the answer never mentions the ask). What actually happens is a refusal note naming the specific columns and listing what is available.

**Fix location.** None — closed as a design decision.

**Re-open criteria.** Any of:

- A PO prompt producing the S1 crash shape (include `Supplier` reaching the planner un-stripped).
- Evidence that the design decision is wrong — e.g. SME feedback that PO queries should reach supplier addresses/classifications. That would be a new capability request, not a bug fix.
- A change to `kg_edge` adding a `PurchaseOrder → Supplier` edge, which would retire `strip_po_supplier_include` (its own docstring notes it is self-retiring on that condition).

**Not checked.** Whether the parser set `fields=['supplier_address', 'classifications']` exactly, or something else that normalised to those strings — the direct parse (per F-017's method) would confirm; the Answer's note shape strongly implies it. Whether the middle band of the gradient file ("supplier details", "supplier information") behaves the same way — one prompt run this session, from the dangerous end; the file's band structure suggests the middle might produce a different shape (e.g. the strip firing silently with no unresolved-fields note). Whether the safe band (PO amounts, status, "who the supplier is") answers cleanly without a note — likely yes given the header inline fields, unrun. Whether any prompt in `11_column_vocabulary.txt` (also cited by the audit) produces a different shape than this one.

**Class note.** Parallel to F-009 (a rule whose existence, not location, matches the entity) and F-017 (the field-split's target-only check). F-009's rule was in the wrong module; F-017's split checked the wrong catalog; this is a design where the capability intentionally stops at the header. Three different shapes, all producing a surface-level symptom (something about the request isn't honoured); only two of them are bugs.

---

## F-026 — B-12's zero-PO "fully invoiced" answer does not reproduce; the mechanism remains a latent risk

**Date:** 2026-09-18
**Status:** closed-as-not-a-bug (with mechanism note)
**Cross-refs:** B-12, F-013 (same closure shape)

**Evidence.**

Runtime, B-12's own prompt:

```
$ python scripts/promptkit.py --run --prompt "How does invoiced compare to ordered for Lee Supplies?" --show-stages
Router: modules=['payables', 'procurement', 'supplier']
Intent:
  target_entity: PurchaseOrder
  compare: {'op': 'supplier_invoiced_vs_ordered', 'po_number': None,
            'supplier_name': 'Lee Supplies', 'top_n': 10, 'status': None}

Plan:
  Step 1: compare_supplier_orders_to_invoices
    tool_args:      {'supplier_name': 'Lee Supplies', 'top_n': 10}

Outputs:
  comparison: 1 record(s)
    [1] {'shape': 'supplier_invoiced_vs_ordered', 'found': True,
         'ambiguous': False, 'supplier': 'Lee Supplies',
         'supplier_id': 300000047414503, 'supplier_number': '1252'}
        ... +9 more field(s): invoice_count, po_count, returned, rows,
            total_difference, total_invoiced, total_ordered, truncated,
            unmatched_invoice_count

Answer:
Lee Supplies: across 390 purchase order(s), ordered 6,719,231.79 and PO-matched
invoiced 412,427.91 — under-invoiced by 6,306,803.88. 1,287 of this supplier's
invoices were not linked to a PO and are excluded from the comparison.
```

Contrast with the audit's B-12 row:

> B-12 | wrong-answer (vacuous) | `How does invoiced compare to ordered for Lee Supplies?` | "No POs found" | `po_count: 0` → "**fully invoiced**." | Zero-equals-zero read as satisfied.

Today's run: `po_count: 390`, real ordered/invoiced totals, "under-invoiced by 6,306,803.88". The specific wrong answer does not reproduce. Lee Supplies resolves to 390 POs on the current pod, not 0.

Static — the mechanism the audit named is still present in the code:

- `src/spire/synthesizer/aggregation.py::_direction_phrase`:
  ```python
  def _direction_phrase(difference: float) -> str:
      if difference > 0:
          return f"over-invoiced by {difference:,.2f}"
      if difference < 0:
          return f"under-invoiced by {abs(difference):,.2f}"
      return "fully invoiced (invoiced equals ordered)"
  ```
- `src/spire/synthesizer/aggregation.py::_summarize_supplier_comparison` builds the sentence:
  ```python
  parts = [
      f"{data.get('supplier')}: across {po_count} purchase order(s), "
      f"ordered {ordered:,.2f} and PO-matched invoiced {invoiced:,.2f} — "
      f"{_direction_phrase(diff)}."
  ]
  ```

If a supplier resolves with `po_count == 0`, then `ordered == invoiced == 0`, so `difference == 0` and `_direction_phrase(0.0)` returns the "fully invoiced" string. The result reads as a satisfied comparison over zero records — the audit's shape. The code path exists; the pod state today does not exercise it for this supplier.

Identity note. §B.1's B-12 row records this prompt and the "fully invoiced" shape at the time of the audit. Today's run produces the opposite. Taken as closed on the same grounds as F-013: the specific reproducer does not reproduce, and the mechanism may or may not still be reachable depending on pod state.

**Root cause of the (now-closed) prior claim.** Not established — the symptom did not reproduce. Two plausible explanations, neither testable from this run alone:

- **Pod changed.** The audit was done over several days; Lee Supplies may have had zero POs at the time (e.g. an early pod state, or a differently-named supplier that has since been populated). The current run shows 390 POs.
- **Compare tool changed.** `compare_orders_to_invoices.py`'s supplier resolution (`_resolve_supplier_number`, `compare_supplier_orders_to_invoices`) resolves by name and checks ambiguity — if the resolution path was tightened, a previously-zero result would now find the supplier's POs.

No git archaeology done; either explanation fits the evidence.

**Fix location.** None — closed at the current reproducer. The mechanism note below applies if a future supplier resolves with 0 POs.

**Mechanism note — latent risk.** `_direction_phrase(0.0)` returns "fully invoiced (invoiced equals ordered)". When `po_count == 0`, the sentence reads:

> "across 0 purchase order(s), ordered 0.00 and PO-matched invoiced 0.00 — fully invoiced (invoiced equals ordered)."

Every clause is true; the paragraph is vacuous. A reader sees "fully invoiced" and reasonably concludes the supplier's orders are settled — while the supplier has no orders at all.

A future fix would branch on `po_count == 0` before reaching `_direction_phrase`, and say plainly: "no purchase orders were found for this supplier; N invoices are not PO-linked." That change is out of scope for this closure; recorded here so the site is named if the shape resurfaces.

**Regression test (if a future session re-opens).** The test would need a supplier with 0 POs. Two candidates the pod may have: a newly-created supplier, or a name that resolves uniquely to a supplier with no orders. Not investigated this session.

**Not checked.** Whether the pod's Lee Supplies had zero POs at audit time — the audit's own note is the only evidence; not re-verified. Whether other suppliers on the current pod resolve with `po_count: 0` — one supplier checked; if one does, the mechanism fires and B-12 becomes confirmed at a different reproducer. Whether `compare_orders_to_invoices.py` changed since the audit — no git history inspected. Whether the AR-side comparison shapes have the same zero-record vacuity — same `_direction_phrase` function underlies all three comparison ops (`po_invoiced_vs_ordered`, `supplier_invoiced_vs_ordered`, `top_suppliers_invoiced_vs_ordered`); only the supplier-scoped one was checked.

**Class note.** Second closure this session of the same shape (F-013 was the first, B-11): the audit's recorded symptom does not reproduce at its own reproducer, but the mechanism may or may not persist. For B-11 the mechanism had been fixed and the fix's docstring named the prompt; for B-12 the mechanism persists and the pod state no longer triggers it.

---

## F-027 — parser routes "country" column request to the Address include; the display renders the full address blob

**Date:** 2026-09-18
**Status:** root-caused, not fixed
**Cross-refs:** B-14, F-017 (adjacent — same map, different defect)

**Evidence.**

Runtime, the audit's reproducer:

```
$ python scripts/promptkit.py --run --prompt "Supplier number and country for active suppliers" --show-stages
Router: modules=['supplier']
Intent:
  target_entity: Supplier
  filters:
    - {'type': 'status', 'value': 'active'}
  include: ['Address']
  fields: ['SupplierNumber']

Plan:
  Step 1: search_suppliers
    tool_args:      {'status': 'ACTIVE', 'include_addresses': True}

Outputs:
  suppliers: 25 record(s)
    [1] {'SupplierNumber': '1252'}
    [2] {'SupplierNumber': '1254'}
    ...

Answer:
All 25 have Status ACTIVE.

Truncation:
  - suppliers: unknown total in source; 25 examined for filtering.

Answer:
suppliers (25 record(s)) — columns: SupplierNumber, Address

  SupplierNumber | Address
  ---------------+--------------------------------------------------------------
  1252           | 6302 England St,HOUSTON, TX 77021 HARRIS
  1254           | 6500 Metropolis Dr,AUSTIN, TX 78744 TRAVIS
  ...
```

Three observations.

- The user asked for "supplier number and country" as columns. The intent has `fields: ['SupplierNumber']` only. "country" is nowhere on the intent — not in `filters`, not in `fields`, not in `unresolved_fields`.
- The parser routed "country" into `include: ['Address']` — the entity that carries it. `include_addresses: True` is on the tool args.
- The display renders the include as a single `Address` column containing the full formatted blob. The user asked for a country column and received an address column.

Static:

- `src/spire/nl_parser/context/supplier/b_country.sysprompt` teaches "country" only as a filter value: *"a country ('US', 'in the United Kingdom') -> a 'country' filter"*. There is no rule for "country" as a requested column.
- `src/spire/nl_parser/context/supplier/b_suppliers_addresses.sysprompt` teaches "addresses" as an include phrase: *"'suppliers with their addresses' / 'list suppliers with their address' / 'suppliers and their addresses' -> target_entity 'Supplier' (NOT Address) with 'Address' added to include."*
- `src/spire/nl_parser/intent_validation.py::_FIELDS_SATISFIED_BY_INCLUDE` has an entry for `"Address": {"address", "addresses", "country", "city", "state"}`. The mechanism is designed to recognise a field like `country` as satisfied by an active Address include: the split drops it from both `known` and `unresolved` (`if col.lower() in satisfied_by_include: continue`), on the reasoning that the include's column renders it. But this only fires when "country" is *in* `fields`, and here it was not.

Identity note. §B.1's B-14 row records this prompt, the wrong projection (`SupplierNumber, Address` instead of `SupplierNumber, CountryCode`), and the audit's own note ("Parser routed 'country' to `include: ['Address']`"). Same prompt, same output, live reproduction this session. Taken as the same bug on the same grounds as F-006 through F-026.

**Root cause.** Two sites, both necessary:

1. **Parser-side.** No `.sysprompt` rule teaches that a requested column whose value lives on a child entity should be added to `fields` (for projection) in addition to adding the child to `include` (for fetch). The parser reads "country" as a fragment and finds only the "suppliers with their addresses" include pattern, so it adds the include and drops the column.
2. **Validator/display-side.** `_FIELDS_SATISFIED_BY_INCLUDE` assumes that when a field is covered by an include, the include's column renders it. The display renders the include as its full blob, not as the requested field. So even if the parser had put "country" in `fields`, the display would still render `Address` — the whole formatted string — and no separate `country` column.

Either alone would produce the audit's symptom. Together they mean both paths have to change before the user gets a country column.

**Fix location (for Phase 2).** Three sites, in increasing scope:

1. **Parser sysprompt.** Add a rule to `b_country.sysprompt` (or a new block): when a prompt asks for a *column* named "country" (no value, as part of a "give me X and Y" list), it belongs in `fields`, not just as an Address include. Cost: a sysprompt edit (token-ceiling risk per the handoff's own warning about parser-prompt edits); a full `--validate` re-run would be warranted.

2. **`_FIELDS_SATISFIED_BY_INCLUDE` redesign.** Instead of dropping a field that an include satisfies, mark it as *resolved-via-include* and carry it forward so the display can render it. Cost: a new intent field (`resolved_via_include`) or reuse of `fields` with a flag. Touches `intent_validation.py` and every consumer of `intent.fields`.

3. **Display-side.** In `src/spire/rendering/formatters.py` (not read this session), when a requested field is satisfied by an include, extract that field from the include's child rows and render it as its own column. Cost: a display-layer change; requires the parser to have communicated which field of the include was requested — which it does not today.

Options 1 and 2 together make the pipeline capable of the user's request; option 3 alone would not, because the parser never marked "country" as the requested field of the include. If only one ships, option 1 is the smaller fix but leaves the display showing the full Address blob alongside a country column (if the parser gets it into `fields` and option 2 preserves it). Option 2 without option 3 leaves the display rendering the Address blob anyway. All three is the honest fix.

The audit's own note in `_FIELDS_SATISFIED_BY_INCLUDE`'s docstring (*"the include's column renders it"*) is the design assumption to revisit. The include's column does not, in fact, render a bare `country` — it renders the entire formatted address. So the map's assumption is only true if the display cooperates.

**Regression test (either fix).** Assert that `Supplier number and country for active suppliers` returns a projection with a `Country` (or `CountryCode`) column, and that the value shown per supplier is the country, not the full formatted address. Assert that `Suppliers with their addresses` (the include-phrase shape) still returns the address blob — the fix must not remove the existing behaviour for prompts that *ask* for the address.

**Not checked.** `src/spire/rendering/formatters.py` — not in any bundle read this session; the exact render path is unresolved. Whether `b_country.sysprompt` has any instruction for "country as a column" that the parser ignored — the grep is the falsifier. Whether the same shape affects other child-field column requests (`city`, `state`, `AddressLine1`, `line items`, `schedules`) — same mechanism, unrun. Whether the parser emitted `fields: ['SupplierNumber', 'country']` and `_FIELDS_SATISFIED_BY_INCLUDE` dropped "country", or the parser never put "country" in `fields` at all — the direct parse (per F-017's method) would distinguish the two, but the outcome is the same either way.

**Class note.** Adjacent to F-017 (same map, different defect — F-017 was the target-only catalog check dropping a child field as unresolved; here the map's "satisfied by include" branch drops the field and the display renders the wrong shape). Both revolve around `_FIELDS_SATISFIED_BY_INCLUDE` not doing what its docstring claims.

---

## F-028 — B-16 no longer reproduces; `supplier_name` and `supplier_number` resolve correctly on the snake_case phrasing

**Date:** 2026-09-18
**Status:** closed-as-not-a-bug
**Cross-refs:** B-16, F-013 (same closure shape), F-026 (same)

**Evidence.**

Runtime, the audit's snake_case reproducer:

```
$ python scripts/promptkit.py --run --prompt "List active suppliers with supplier_name and supplier_number" --show-stages
Router: modules=['supplier']
Intent:
  target_entity: Supplier
  filters:
    - {'type': 'status', 'value': 'active'}
  fields: ['Supplier', 'SupplierNumber']

Plan:
  Step 1: search_suppliers
    tool_args:      {'status': 'ACTIVE'}

Outputs:
  suppliers: 25 record(s)
    [1] {'Supplier': 'Lee Supplies', 'SupplierNumber': '1252'}
    [2] {'Supplier': 'JGA', 'SupplierNumber': '1254'}
    ...

Answer:
All 25 have Status ACTIVE.

Answer:
suppliers (25 record(s)) — columns: Supplier, SupplierNumber

  Supplier                                   | SupplierNumber
  -------------------------------------------+---------------
  Lee Supplies                               | 1252
  JGA                                        | 1254
  ...
```

Contrast with the audit's B-16 row:

> B-16 | missing-projection (NL field name not resolved) | `List active suppliers with supplier_name and supplier_number`, `List active suppliers with SupplierName and SupplierNumber` | `Supplier`, `SupplierNumber` | Refuses both | **Narrowed:** `field_synonym` vocabulary is honoured (`vendor name` → `Supplier`). B-16 is specifically names with no `field_synonym` row, even when the target field exists on the entity.

Today: the intent has `fields: ['Supplier', 'SupplierNumber']` — the parser resolved both names to real columns. The answer renders them. The audit's "Refuses both" does not reproduce on the snake_case phrasing.

Two explanations, neither testable from this run alone:

- **`field_synonym` vocabulary grew.** If `supplier_name → Supplier` and `supplier_number → SupplierNumber` rows were added to `kg_vocabulary` after the audit, `expand_field_synonyms` would resolve the terms deterministically. The KG seed I read this session has `vendor name` and `vendor number` but I did not see `supplier name` / `supplier_number` rows — though the seed I saw was at a specific commit, not necessarily current.
- **Parser learned the mapping.** The parse prompt's COLUMNS list (rendered from `kg_entity_field`) shows `Supplier` and `SupplierNumber` as real columns on Supplier. The model may be reading the prompt's own field list and mapping the user's underscore form to the pod's PascalCase form.

Both are plausible and would produce identical output. The mechanism does not matter for the closure — the specific reproducer is clean.

Identity note. §B.1's B-16 row records both phrasings as refusing. This run of the snake_case phrasing does not refuse; the PascalCase phrasing is unrun this session. Taken as closed on the snake_case reproducer on the same grounds as F-013 and F-026.

**Root cause.** Not established — the failure did not reproduce. The parser resolved both field names on the current code. The audit's narrowing ("specifically names with no `field_synonym` row") is not observable here because either (a) such rows now exist for these names, or (b) the parser is resolving by reading the entity's own column list rather than requiring a synonym.

**Fix location.** None — closed.

**Re-open criteria.** Any of:

- A run of the snake_case phrasing (`List active suppliers with supplier_name and supplier_number`) producing a refusal or an unresolved-fields note.
- A run of the PascalCase phrasing (`List active suppliers with SupplierName and SupplierNumber`) producing a refusal — the audit tested both, and only one was re-run this session.
- A test of a genuinely-absent field name (a name with no `field_synonym` row and no column match) showing the parser failing silently rather than refusing — different shape than B-16 records, but worth tracking.

**Not checked.** The PascalCase phrasing from the audit's same row — `List active suppliers with SupplierName and SupplierNumber` — not run this session; the audit tested both phrasings, and only one was re-verified. Whether `kg_vocabulary` now has `supplier_name` / `supplier_number` `field_synonym` rows that were absent at audit time — the KG seed I read this session shows only `vendor name` / `vendor number` on the field_synonym kind, but that is a snapshot, not necessarily current; a `spire-ops kg print --table kg_vocabulary` run would settle it. Whether the parser's resolution path is synonym-based or column-list-based — either produces the same output, and distinguishing them is not needed for the closure. Whether `Show PO 2144 and its lines with ordered and total` (§B.4's positive counter-example to B-22) has the same resolution path or a different one — noted as related but not investigated.

**Class note.** Third closure this session of the same shape (F-013 was B-11, F-026 was B-12, this is B-16): the audit's recorded symptom does not reproduce at its own reproducer. The pattern across the three: the audit's observations were real when made, and the code has moved — sometimes a documented fix (F-013's, where the fix comment names the prompt), sometimes silently (F-026's and this one). Recording the closure with the current evidence and the not-checked list is the honest outcome; the audit's row is preserved unchanged per the append-only discipline.

---

## F-029 — B-18's lag refusal is an honest "capability not present", not a regression; the lag tool is on a parked branch

**Date:** 2026-09-18
**Status:** closed-as-not-a-bug
**Cross-refs:** B-18, E-12 (the parked branch), F-013 / F-026 / F-028 (same closure family)

**Evidence.**

Runtime, the audit's reproducer:

```
$ python scripts/promptkit.py --run --prompt "Show lag between creation and last update for receipts of ABC Application Software" --show-stages
Router: modules=['receivables']
Reason:   Calculating the lag between creation and last update requires receipt
          creation and last update timestamps, which are not available on receipts.

Solution: Ask for the underlying records and I'll return them for you to total or average.

Example:  receipts for ABC Application Software
  (refusal: unsupported_operation — Calculating the lag between creation and last
   update requires receipt creation and last update timestamps, which are not
   available on receipts.)
```

A clean parser-declared refusal — no crash, no attempt to plan against a missing tool. The Reason text has no snake_case token, so `capability.py::_reason_line`'s UNSUPPORTED_OPERATION branch returns the model's prose verbatim. The Solution is `_FALLBACK[RefusalFlavor.UNSUPPORTED_OPERATION]`; the Example is `_OPERATION_EXAMPLES["StandardReceipt"]`.

Static cross-check — the model's claim about missing timestamps matches the tool projections:

- `src/spire/mcp_server/tools/account_receipts.py::_PROJECTED_FIELDS`: `StandardReceiptId, ReceiptNumber, ReceiptDate, Amount, Currency, ReceiptMethod, State, ProcessStatus, UnappliedAmount, CustomerSite, BusinessUnit`. No `CreationDate`, no `LastUpdateDate`.
- `src/spire/mcp_server/tools/standard_receipts.py::_PROJECTED_FIELDS`: `StandardReceiptId, ReceiptNumber, ReceiptDate, Amount, Currency, ReceiptMethod, Status, CustomerName, CustomerAccountNumber, CustomerSite, RemittanceBankName, RemittanceBankBranch, RemittanceBankAccountNumber`. Same absence.

The pipeline's tools do not fetch WHO columns on receipts. Whether the pod *exposes* them is unverified this session; the pipeline cannot compute the lag from the fields it has.

Contrast with the audit's B-18 row:

> B-18 | wrong-refusal (regression) | `Show lag between creation and last update for receipts of ABC Application Software` | Lag calculation | Refusal: "unsupported operation" | Endpoints reference documents lag as working twice.

The audit's "regression" framing does not hold against the current pipeline. The KG seed's own note (read earlier this session from the `graph_kg` bundle, `kg_entity_filter` seed area) documents the actual history:

> A lag_query filter and a `get_receipts_with_lag` entity tool were live in the KG database but in NEITHER the seed nor master: the code sits on `feature/ar-prompt-18-parking`. The KG was advertising a tool the running server does not have, so a lag query planned cleanly and then failed at dispatch. Those rows are gone; when prompt 18 lands it should bring them.

So the lag capability was planned (prompt 18), parked (branch `feature/ar-prompt-18-parking`), and its KG rows were removed to reconcile seed and database. It has never been on `hardening-master`. Today's pipeline honestly reports it as unsupported.

The audit's "endpoints reference documents lag as working twice" is true of the *pod* — a curl can fetch the timestamps — but not of the pipeline. The endpoint reference and the pipeline are different layers.

Identity note. §B.1's B-18 row records the prompt and the "unsupported operation" refusal. Same prompt, same refusal, live reproduction this session. Taken as the same bug on the same grounds as F-006 through F-028, with the classification corrected from "regression" to "capability absent by design".

**Root cause of the (now-closed) prior claim.** The capability was never on the current integration branch. `feature/ar-prompt-18-parking` holds the code; the KG rows that once advertised it were removed for seed/database reconciliation (per the seed comment). The audit's "regression" reading assumed the capability had once been live on the running pipeline; the KG seed's own note says otherwise.

**Fix location.** None — closed as designed-absent. If the capability is wanted, the fix is prompt 18's branch: land `get_receipts_with_lag` plus its KG rows (`kg_entity_tool`, `kg_entity_filter`, edge tool as needed) on `hardening-master`. That work belongs to Phase 2 or a dedicated phase, not to a bug-fix entry.

**Re-open criteria.** Any of:

- A run of this prompt producing a crash or a plan against a missing tool — would indicate the parked branch's rows have landed without the tool, or vice versa.
- A decision to land prompt 18's branch — would make this prompt answerable and reclassify it as a capability gain, not a bug fix.
- A change to `AccountReceipt` or `StandardReceipt` projections adding `CreationDate` / `LastUpdateDate` — would enable the lag without a dedicated tool, and the prompt's refusal would change shape.

**Not checked.** Whether the pod's `/standardReceipts` or its account-child exposes `CreationDate` / `LastUpdateDate` if they were added to `?fields=` — one curl would settle it; the tools do not fetch them today. Whether the parked branch `feature/ar-prompt-18-parking` still exists in the repo — §E.4's E-12 proposes the check but it was not run. Whether `feature/ar-prompt-18-parking` holds *only* the lag work or a broader prompt-18 change set. Whether the same "planned/parked" pattern affects any other B row — the KG seed's removal note (read earlier) names only the lag rows; a class-level sweep of parked-branch references in the KG was not run.

**Class note.** Fourth closure this session of the same "recorded symptom does not match current state" shape (F-013 was B-11, F-026 was B-12, F-028 was B-16, this is B-18). The four differ in *why* the state diverged: F-013's fix comment names the prompt; F-026 and F-028 drifted silently; this one was never a pipeline capability at all — the audit read "the endpoint reference documents it" as "the pipeline does it", and those are different layers.

Cross-ref §E.4's E-12, which records the parked branch. When §E's branch-state checks are run, E-12 and this entry close together — same underlying question.

---

## F-030 — B-c1's suspected risk-rating wrong-answer does not reproduce; the rating is computed, not fetched

**Date:** 2026-09-18
**Status:** closed-as-not-a-bug
**Cross-refs:** B-c1, F-013 (lifecycle path closure)

**Evidence.**

Runtime, the audit's candidate reproducer:

```
$ python scripts/promptkit.py --run --prompt "What is the risk rating on PO 701337 and why?" --show-stages
Router: modules=['procurement']
Intent:
  target_entity: PurchaseOrder
  filters:
    - {'type': 'lifecycle_status', 'value': '701337'}

Plan:
  Step 1: get_purchase_order_lifecycle_status
    tool_args:      {'po_number': '701337'}

Outputs:
  open_pos: 1 record(s)
    [1] {'shape': 'po_lifecycle_status', 'found': True, 'order_number': '701337', ...}
        ... +55 more field(s): ..., risk, risk_reasons, ...

Answer:
PO 701337 — JGA
  Received: no · Invoiced: no · Paid: cannot be determined
  Stage: Awaiting receipt  ·  Owner: Supplier / Receiving  ·  Risk: Medium

...
Risk (Medium):
  - the paid leg cannot be determined
  - not fully received
  - not fully invoiced
  - PO payment terms differ from the site default
```

The rating is `Medium`, with four named reasons. Compare against the audit's B-c1 row:

> B-c1 | wrong-answer (suspected) | `What is the risk rating on PO 701337 and why?` | Needs a curl against the lifecycle source fields.

The audit's note frames the rating as a fetched field in need of verification against a pod source. It is not: the rating is computed inside `src/spire/mcp_server/tools/po_lifecycle.py::_assess_risk`, deterministically from fields the tool has already fetched (`setup_blockers`, `hold_count`, `days_overdue`, `truncated`, `paid_state`, `fully_received`, `fully_invoiced`, `amount_disagreement`, `terms_mismatch`). A curl against "the lifecycle source fields" would return the raw amounts and setup booleans; it would not return a rating, because there is no rating field on the pod.

The `m_po_lifecycle.sysprompt` block already states this explicitly:

> RISK ON A PO IS SUPPORTED. Do NOT refuse on the grounds that the system does not track a risk rating for purchase orders. It does: this filter computes a rating with its reasons and a recommended action, and returns them on every lifecycle answer.

Today's run matches that: rating present, reasons present, recommended action present.

Identity note. §B.2's B-c1 row records the prompt, the suspected wrong-answer, and the "needs a curl" note. Same prompt, no wrong-answer observed this session. Taken as closed on the same grounds as F-013.

**Root cause of the (now-closed) prior suspicion.** Two parts:

1. The suspicion itself ("wrong-answer") does not reproduce — the answer is correct, reasoned, and complete.
2. The verification approach the audit proposed ("curl against the lifecycle source fields") is based on a false premise: there is no source field. The rating is a function of the record, not a field of it. Any future suspicion about a lifecycle computed field would need a different verification method — re-running the tool with known inputs and checking the reasoning against `_assess_risk`'s decision tree, or unit-testing `_assess_risk` directly.

**Fix location.** None — closed. The audit's "needs a curl" note is not a fix location; it is a verification plan that turned out to be unavailable.

**Re-open criteria.** Any of:

- A lifecycle run producing a risk rating without reasons, or with reasons the fetched record does not support.
- A change to `_assess_risk` or its call site in `po_lifecycle.py::get_purchase_order_lifecycle_status`.
- A unit test for `_assess_risk` producing a decision-tree result the audit can verify against a run.

**Not checked.** Whether `_assess_risk`'s ratings are correct as a *business* judgement — the pipeline returns `Medium` for "not fully received, not fully invoiced, payment terms differ"; whether those reasons *should* be Medium rather than High/Low is a domain question the audit did not raise and this closure does not answer. Whether other lifecycle prompts produce equivalently reasoned output — one prompt checked this session; F-013's sibling prompt (`How much of PO 2144 was received?`) produced a comparable shape (Risk: Medium, with reasons), so two lifecycle prompts agree. Whether the audit's "suspected" framing implied a specific concern that today's run doesn't exercise — the audit gives no further detail; the note is only "needs a curl against the lifecycle source fields."

**Class note.** Fifth closure this session of the same family (F-013 was B-11, F-026 was B-12, F-028 was B-16, F-029 was B-18, this is B-c1). This one differs in shape: the audit labelled it a *candidate* (not a confirmed bug), so the closure is a demonstration that the suspicion does not hold rather than a correction to a confirmed claim. F-029 (B-18) was also a candidate-class closure — a suspected regression that turned out to be a parked capability. The two are the only candidates in §B.2 that have been investigated; both closed clean.

---

## F-031 — B-c3 (`not inactive` → `active`) is an observation, not a bug; no harm when the pod has exactly two statuses

**Date:** 2026-09-18
**Status:** closed-as-not-a-bug (observation)
**Cross-refs:** B-c3

**Evidence.**

Runtime, the audit's candidate prompt:

```
$ python scripts/promptkit.py --run --prompt "suppliers that are not inactive" --show-stages
Router: modules=['supplier']
Intent:
  target_entity: Supplier
  filters:
    - {'type': 'status', 'value': 'active'}

Plan:
  Step 1: search_suppliers
    tool_args:      {'status': 'ACTIVE'}

Outputs:
  suppliers: 25 record(s)
    [1] {'SupplierId': 300000047414503, 'SupplierNumber': '1252',
         'Supplier': 'Lee Supplies', 'Status': 'ACTIVE', ...}
    ... (all rows show Status ACTIVE)

Answer:
All 25 have Status ACTIVE.
...25 suppliers...
```

The parser normalised "not inactive" to `status='active'`. The fetch returned ACTIVE suppliers. The answer is correct on this pod.

Static — the equivalence holds because the pod has exactly two supplier statuses:

- `kg_vocabulary` for `vocab_kind='supplier_status'` (per the `graph_kg` bundle, seed in `scripts/sql/kg_schema.sql`): exactly two rows.
  ```
  ('supplier_status', 'active',   'ACTIVE',   'Supplier is active.')
  ('supplier_status', 'inactive', 'INACTIVE', 'Supplier is inactive.')
  ```
- No third value seeded. No evidence in the read bundles of a third status on the pod.

If those are the only two statuses, then `{s : s.status ≠ INACTIVE}` = `{s : s.status = ACTIVE}`. The two filters produce identical result sets. No wrong answer, no missing row, no crash.

**Root cause — the harm S1 asks for is absent.** The claim under consideration was "the semantic rewrite might drop records." Under S1, that claim requires a harm — wrong data returned, wrong narration, crash, refusal, silent omission, cost regression, or path inconsistency. None is available:

- The fetch returned ACTIVE suppliers — the answer set for `status=ACTIVE`.
- If `{not INACTIVE} = {ACTIVE}`, the answer set for `{not INACTIVE}` is identical.
- No alternative status exists on the pod, so no record is wrongly filtered out.

The audit's own B-c3 note already anticipated this: *"Correct on this pod but semantically different."* The audit's classification of B-c3 as a §B.2 *candidate* rather than a confirmed bug (§B.1) was correct.

**Fix location.** None — closed as observation.

**Re-open criteria.** Any of:

- A third supplier status appearing on the pod — a `Status` value other than `ACTIVE` or `INACTIVE`. If it exists, `not inactive` and `active` diverge, and the parser's normalisation becomes a wrong-answer bug.
- A supplier count on the pod where `count of inactive suppliers` + `count of active suppliers` ≠ `count of suppliers` — this would prove a third state exists.
- A change to `kg_vocabulary`'s `supplier_status` kind adding a third value.

**Not checked.** Whether a supplier count check confirms `active + inactive = total` on this pod — the reasoning above rests on the KG vocabulary's two-value seed; a direct probe would confirm it. Whether other "not X" phrasings have the same normalisation shape (e.g. `not active`, `not closed for receiving`) — the pattern is general but only this one prompt was run. Whether the pod genuinely has no supplier with a status outside `{ACTIVE, INACTIVE}` — the KG's two-value seed is the evidence; a `q=Status=...` probe would be conclusive.

**Class note.** This is the only §B.2 candidate that closed as an *observation* rather than as a *not-a-bug after investigation*. B-c1 (F-030) was a wrong-answer suspicion disproven; B-c2 (F-024) was nondeterminism that didn't reproduce; B-c4 was folded into F-024 as a class note. B-c3 never rose to a bug claim — the audit itself recorded it as "correct on this pod", which is the S1-fails case. Recording it as a closure with its reasoning is what keeps §B.6's mapping complete without inflating an observation into a finding.

---

## F-032 — D-01's router-vs-refusal mismatch is diagnostic, not a bug

**Date:** 2026-09-18
**Status:** closed-as-not-a-bug (observation)
**Cross-refs:** D-01, F-023 (module set is diagnostic)

**Evidence.**

Runtime, the audit's reproducer:

```
$ python scripts/promptkit.py --run --prompt "Show invoice lines for invoice 300000248096352" --show-stages
Router: modules=['payables']
Reason:   I can look up AR invoice lines, but only as part of the record they belong to.

Solution: Ask for the invoice and its lines together.

Example:  Show invoice lines for invoice 300000248096352
  (refusal: unknown_entity — needs an Invoice Line entity, which is not supported as a target entity)
```

Two signals disagree: the router picked `payables`; the refusal names `ReceivablesInvoiceLine` (a `receivables` entity).

Static:

- The generated classifier menu binds `invoice` to `payables/Invoice`:
  ```
  payables:
    Invoice (aka: bill, invoice)
  ```
  The classifier sees "invoice" in the prompt, picks the module its menu binds the word to, and is internally consistent.
- The parser has `ReceivablesInvoiceLine` in the KG menu's "OTHER known entities" section regardless of module scope. It correctly identified the prompt's entity family and refused with `unknown_entity` naming the AR line entity.
- F-023 established that the module set is a diagnostic breadcrumb, not a correctness signal; nothing downstream reads it.

**Root cause — S1 fails.** Under S1's harm classes (wrong data, wrong narration, crash, refusal of an in-scope prompt, silent omission, cost regression, inconsistency between two paths), none is present:

- Not wrong data — no records returned; the answer is a refusal.
- Not wrong narration — the Reason and Solution are both accurate for the entity the parser identified. The router's module set never reaches the user.
- Not a crash.
- Not a refusal of an in-scope prompt — §B.3 records this prompt as a correct refusal (a child entity cannot be a query root).
- Not silent omission — the refusal states the shape.
- Not a cost regression — parse input is 2,815 tokens, in the low half of the session's range.
- Not an inconsistency between two paths — the router and the parser are two *stages* of the same path. They disagree at the diagnostic level and agree at the outcome level (a correct refusal).

The classifier's choice is not a systematic under-inclusion of `receivables` for AR prompts; the prompt carries no AR signal — it says "invoice lines", not "AR invoice lines" — so the classifier's binding of bare "invoice" to `payables` is the menu's design, not a defect.

**Fix location.** None — closed as observation.

**Re-open criteria.** Any of:

- A run of this prompt where the router's module choice changes the outcome (a correct intent under one scope, a refusal under another) — would establish the module is not merely diagnostic.
- A change to the classifier menu that alters the `invoice` binding.
- A decision to remove module-scoping entirely, making the disagreement moot.

**Not checked.** Whether the parser produces a different intent under `receivables` scope — the counterfactual was not run. Whether other overloaded-vocabulary prompts ("order" alone, "receipt" alone) produce analogous diagnostic mismatches — same shape, not swept. Whether §D.1's methodology (which accepts "error message inconsistent with code path" as a §D row without S1's harm requirement) should be reconciled with the findings-log's S0–S8 discipline — a §D-vs-§B methodology question, not this finding's.

**Class note.** Fourth "diagnostic disagreement" observation this session, following F-023's module-set finding, F-024's supplier-count cross-file variance, and §G's module-order diff. The consistent pattern: signals the pipeline treats as diagnostic can vary without changing the answer.

---

## F-033 — `ReceivablesInvoiceLine` refusal's Example is the failing prompt itself

**Date:** 2026-09-18
**Status:** confirmed
**Cross-refs:** D-01 (reproducer), F-009 (comparison for the correct shape)

**Evidence.**

From F-032's run of `Show invoice lines for invoice 300000248096352`:

```
Reason:   I can look up AR invoice lines, but only as part of the record they belong to.

Solution: Ask for the invoice and its lines together.

Example:  Show invoice lines for invoice 300000248096352
```

The Example is byte-identical to the prompt that just refused. The reader is told "ask for the invoice and its lines together" and shown the same failing prompt as the worked example.

Compare to F-009's refusal for `addresses for supplier 1252`, whose Example is a different, working prompt:

```
Reason:   Filtering suppliers by supplier number is not supported; a supplier name is required.

Solution: Narrow by country, status or name instead.

Example:  active suppliers in US
```

The Example's purpose is to be typeable — a prompt that will succeed and demonstrate the Solution. This one, by contrast, replays the input.

Static:

- `src/spire/nl_parser/capability.py::_NOT_A_ROOT_GUIDANCE["ReceivablesInvoiceLine"]`:
  ```python
  "ReceivablesInvoiceLine": (
      "Ask for the invoice and its lines together.",
      "Show invoice lines for invoice 300000248096352",
  ),
  ```
  The second string is the failing prompt verbatim. Compare to the sibling entry for `PurchaseOrderLine`, whose example is `"Show PO 2144 and its lines"` — a working prompt that matches the Solution's advice.

**Root cause.** The `_NOT_A_ROOT_GUIDANCE` entries pair a Solution ("ask for X and its Y together") with an Example intended to demonstrate that shape. For all the other entries the example is a working prompt; for `ReceivablesInvoiceLine` the example is the string that triggers the refusal itself. Likely chosen at authoring time for parallelism with the failing prompt, rather than as a working counter-example.

**Fix location (for Phase 2).** One-line edit in `src/spire/nl_parser/capability.py::_NOT_A_ROOT_GUIDANCE["ReceivablesInvoiceLine"]` — replace the second element with a working prompt, e.g. `"Show the AR invoice with CustomerTransactionId 1002 and its lines"` (mirroring the working tax-lines shape `"Show the AR invoice with CustomerTransactionId 1002 and its tax lines"` from §B.4's positive examples).

**Regression test.** Assert that the `ReceivablesInvoiceLine` example prompt produces an answered result, not the same refusal. Stronger form: assert every entry in `_NOT_A_ROOT_GUIDANCE` whose example is offered to the user names a prompt that actually succeeds, mirroring `tests/test_nl_parser_capability.py::test_every_promised_example_is_verifiable` (which already enforces this rule for `_FIELD_GUIDANCE`, per its docstring — this is the same class of guard applied to a different map).

**Not checked.** Whether `_NOT_A_ROOT_GUIDANCE["Site"]`'s example (`"supplier sites for Lee Supplies"`) works or refuses — §B.3 lists that prompt as a correct refusal, suggesting a second example of the same defect; not run this session. Whether the same defect exists in the other example-carrying dicts (`_FILTER_GUIDANCE`, `_IDENTIFIER_GUIDANCE`, `_OPERATION_EXAMPLES`, `_FALLBACK`, `_FIELD_GUIDANCE`) — a class-level sweep is a small script, not run. Whether the audit's D-01 row would have closed the same way had this Example defect not been present — independent of D-01's router claim.

**Class note.** First "new" bug the audit missed, surfaced by a §D reproducer. §D.1's rows are inconsistencies; a §D reproducer can surface a §B-class bug in the same run, which is the shape here.

---

## F-034 — D-02's "aggregation template applied to a field-availability refusal" does not reproduce

**Date:** 2026-09-18
**Status:** closed-as-not-a-bug (with one minor narration note)
**Cross-refs:** D-02

**Evidence.**

Runtime, the audit's reproducer:

```
$ python scripts/promptkit.py --run --prompt "suppliers with the highest quality score" --show-stages
Router: modules=['supplier']
Reason:   Filtering or ranking suppliers by a quality score is not supported.

Solution: Narrow by country, status or name instead.

Example:  active suppliers in US
  (refusal: unsupported_filter — Filtering or ranking suppliers by a quality score is not supported.)
```

Compare against the audit's D-02 row:

> D-02 | `suppliers with the highest quality score` refusal | Solution: "…total or average." | Aggregation template applied to a field-availability refusal.

Today's Solution is `_FILTER_GUIDANCE["Supplier"]` — "Narrow by country, status or name instead." The operation template the audit recorded (`_FALLBACK[RefusalFlavor.UNSUPPORTED_OPERATION]`: "Ask for the underlying records and I'll return them for you to total or average.") is not what renders.

Static — the pieces fit:

- The flavor tag is `unsupported_filter`, per the refusal's own closing parenthesis.
- `src/spire/nl_parser/capability.py::_reason_line`'s UNSUPPORTED_FILTER branch: the Reason text has no snake_case token, so the model's prose is returned verbatim. `"Filtering or ranking suppliers by a quality score is not supported."` is model prose.
- `src/spire/nl_parser/capability.py::_solution_and_example`: `flavor is UNSUPPORTED_FILTER and entity in _FILTER_GUIDANCE` → returns `_FILTER_GUIDANCE["Supplier"] = ("Narrow by country, status or name instead.", "active suppliers in US")`. Both lines match the paste.

Identity note. §D.1's D-02 row records this prompt and a Solution the pipeline does not produce today. The audit's specific claim is the aggregation template; today's answer uses filter guidance. The observable state has diverged from the audit's record. Taken as closed on the same grounds as the F-013/F-026/F-028/F-029 family: the recorded symptom does not reproduce.

**Root cause of the (now-closed) prior claim.** Not established — the symptom did not reproduce. Two non-exclusive explanations:

- **Parser behavior changed.** If the parser classified this prompt as `unsupported_operation` at audit time, the Solution would have been the operation template (matching the audit's record). Today it classifies as `unsupported_filter` and the Solution is filter guidance. A shift in the parser's field-vs-operation disambiguation would account for both records.
- **`capability.py` changed.** If the parser's flavor was `unsupported_filter` at audit time but `_solution_and_example` fell through to the operation fallback, a later fix to `_solution_and_example` would change the observable text. The current code has no such fall-through for `UNSUPPORTED_FILTER` when the entity is in `_FILTER_GUIDANCE`.

No git archaeology done; either explanation fits.

**Minor narration note — not a bug, recorded for completeness.** The Reason text ("Filtering or ranking suppliers by a quality score is not supported") mentions *ranking*, but the Solution offers *filter* guidance ("Narrow by country, status or name"). The user asked for "the highest quality score" — a ranking ask on a nonexistent field. The parser classified the shape as a filter with a missing filter value. The Solution is coherent for the flavor the pipeline chose; it just doesn't address the ranking word in the Reason. Not worth an F-NNN on its own; recorded here in case a future pass examines the field-vs-operation boundary.

**Fix location.** None — closed.

**Re-open criteria.** Any of:

- A run of this prompt producing a Solution that is the operation template ("total or average") — would re-establish the audit's D-02 shape.
- A run producing `unsupported_operation` flavor for this prompt — would indicate parse-side variance at the field-vs-operation boundary.
- A change to `capability.py::_solution_and_example` or `_FILTER_GUIDANCE` / `_FALLBACK`.

**Not checked.** Whether the parser produces a different flavor on repeated runs of this prompt — one run this session; the parse is deterministic for this shape in the sampled instances but the boundary case was not exercised at N>1. Whether the audit's D-02 observation was captured with a different parser prompt or a different pod state — no git archaeology. Whether similar "highest X field" prompts (ranking asks on nonexistent fields) produce the same filter-flavored refusal — same shape, not swept. Whether the parser's field-vs-operation disambiguation is stable across the three "nonexistent ranking field" prompts the audit lists under §B.3 (`quality score`, `risk score`, `credit rating`, `rating`) — four prompts in the same class, only one run.

**Class note.** Sixth "does not reproduce at the audit's reproducer" closure this session (F-013, F-026, F-028, F-029, F-030, this one). Same shape as the others: the audit's observation was accurate at capture time, the current state diverges, and no git history was inspected to determine which of the code or the pod moved. The findings log records the closure; the audit's D-02 row stays as written per the append-only discipline.

---

## F-035 — D-03's "factually wrong about `name_fragment`" does not reproduce; the observation reduces to model-prose variance

**Date:** 2026-09-18
**Status:** closed-as-not-a-bug (observation)
**Cross-refs:** D-03, §H.1 (parser-prose variance)

**Evidence.**

Runtime, both prompts:

```
$ for p in "Addresses for supplier 1252" "everything about supplier 1252"; do
    python scripts/promptkit.py --run --prompt "$p" --show-stages 2>&1 \
      | grep -E '^(Reason|Solution|Example|Router|  \(refusal)'
  done
=== Addresses for supplier 1252 ===
Router: modules=['supplier']
Reason:   A bare supplier number is not a supported filter for Supplier queries; a supplier name is required.
Solution: Narrow by country, status or name instead.
Example:  active suppliers in US
  (refusal: unsupported_filter — A bare supplier number is not a supported filter for Supplier queries; a supplier name is required.)

=== everything about supplier 1252 ===
Router: modules=['supplier']
Reason:   A bare supplier number is not queryable because there is no supplier number filter on the Supplier entity.
Solution: Narrow by country, status or name instead.
Example:  active suppliers in US
  (refusal: unsupported_filter — A bare supplier number is not queryable because there is no supplier number filter on the Supplier entity.)
```

What matches the audit's D-03 row:

- Two prompts, one root cause (a bare supplier number cannot root a Supplier query).
- Two differently-worded Reasons.

What does **not** match:

- The audit's specific claim ("the second is factually wrong about `name_fragment`"). The second Reason says nothing about `name_fragment`; it says "there is no supplier number filter on the Supplier entity." The KG seed confirms that claim is accurate — Supplier's `kg_entity_filter` rows are `country`, `status`, `business_relationship`, `name_fragment`, `created_date`, plus the edge filters. No `supplier_number`. The audit's premise is not observable today.

Static — the structured pieces are identical across both runs:

- Same flavor: `unsupported_filter`.
- Same entity: `Supplier`.
- Same `Solution` and `Example`: both from `capability.py::_FILTER_GUIDANCE["Supplier"]`:
  ```python
  "Supplier": (
      "Narrow by country, status or name instead.",
      "active suppliers in US",
  ),
  ```
- Same `Reason` source: model prose. Neither Reason has a snake_case token, so `capability.py::_reason_line`'s UNSUPPORTED_FILTER branch returns the model's own words verbatim. The two Reasons differ because the model wrote different prose for the same underlying refusal — not because the pipeline chose different paths.

Identity note. §D.1's D-03 row records these two prompts and a claim about `name_fragment`. Today's run preserves the observation (two Reasons for one root cause) but disproves the specific claim (the second Reason is wrong). Taken as closed on the same grounds as the F-013/F-026/F-028/F-029/F-030 family.

**Root cause.** Not a bug in the code — the pipeline's structured refusal output is identical across the two runs. The `Reason` line is model prose, and the two prompts produce different prose. That is wording variance, not path inconsistency.

Under S1's harm classes, none applies:

- Not wrong data — no records returned either way.
- Not wrong narration — both Reasons are accurate. The audit's record was of a *different* message text that is not produced today.
- Not a crash.
- Not a refusal of an in-scope prompt — a bare supplier number cannot root a Supplier query; §B.3 records this refusal as correct.
- Not silent omission.
- Not a cost regression.
- Not an inconsistency between two paths — the flavor, entity, Solution, and Example are all identical; only the model-authored Reason text varies.

**Fix location.** None — closed.

**Re-open criteria.** Any of:

- A run of either prompt producing a Reason that makes a factually false claim (e.g. "`name_fragment` is not available" — the filter does exist).
- A change to `capability.py::_FILTER_GUIDANCE` or `_reason_line` that makes the Reason text deterministic across runs.
- A decision to make Reasons canonical (templated from structured facts, not model prose) — would eliminate the wording variance class entirely.

**Not checked.** Whether the two prompts' Reasons are stable across repeated runs — one run each; the two-prompt comparison was not extended to N>1. Whether the audit's original observation was captured against a different model version or parse path — no git archaeology. Whether other "bare supplier number" prompts (`supplier 1252`, `supplier details for 1252`) produce a third wording — same class, not swept. Whether the Reason-line variance is worth a systematic fix or should simply be listed under §H.1 alongside the other parser-prose variance observation.

**Class note.** Seventh "does not reproduce" closure this session (F-013, F-026, F-028, F-029, F-030, F-034, this one). This one is the mildest — the audit row was a §D inconsistency observation, and the observation is preserved while the specific claim about *what the second message says* is not.

**§H.1 cross-reference.** This finding records the third instance this session of model-prose variance across runs (after §H.1's "parser output length varies" and F-032's module-set ordering diff). Whether §H.1 should be updated to note the pattern explicitly is a §H cleanup decision, not this finding's.

---

## F-036 — truncation note says "examined for filtering" on an unfiltered fetch

**Date:** 2026-09-18
**Status:** closed (PR #157, 2026-09-22)
**Cross-refs:** D-04, F-012 (adjacent — same note function)

**Evidence.**

Runtime, the audit's reproducer:

```
$ python scripts/promptkit.py --run --prompt "Suppliers with their addresses" --show-stages
Router: modules=['supplier']
Intent:
  target_entity: Supplier
  include: ['Address']

Plan:
  Step 1: search_suppliers
    tool_args:      {'include_addresses': True}
    client_filters: (none)

Outputs:
  suppliers: 25 record(s)

Answer:
Showing 25 of 656 suppliers.
...25 rows with addresses...

Truncation:
  - suppliers: 656 total in source; 25 examined for filtering.
```

No filter was applied — `tool_args` carries only `include_addresses`, no `status`, no `country`, no `name`. `client_filters` is empty. The 25 rows are the fetcher's default `limit`, not a filtered subset. The note nonetheless says the 25 were "examined for filtering."

Static — the phrase is hardcoded:

- `src/spire/synthesizer/synthesizer.py::_local_truncation`:
  ```python
  notes.append(
      f"{bucket}: {total_text} total in source; "
      f"{examined} examined for filtering."
  )
  ```
  `examined = len(rows)` where `rows = outputs[bucket]` — the fetched-and-returned count after the tool applied its `limit`. The function has no argument or state carrying whether a filter ran, so the phrase "for filtering" is unconditional.

- The function's own docstring (same module, same function) acknowledges wording looseness in the other direction — *"'total in source' is inherited and is loose on a filtered query — it reads as unfiltered when the fetch was scoped"* — and leaves it alone as a user-visible format change belonging to a dedicated counts-line pass. The same reasoning applies here, but the wording is affirmatively wrong rather than merely loose.

Identity note. §D.1's D-04 row records this prompt and the note shape. Same prompt, same truncation line, live reproduction this session. Taken as the same bug on the same grounds as F-006 through F-033.

**Root cause.** `_local_truncation` emits a hardcoded phrase that presupposes a filter was applied. The function's inputs (`rows`, `truncation_by_step`, `metadata_by_step`) do not carry a "was a filter applied?" flag, so even when the note fires on a filter-less fetch the wording is unchanged. The tool's own note does not distinguish "the fetch hit its cap before filtering" from "the fetch returned a sample of the collection and no filter was involved."

**Fix location (for Phase 2).** One of three, in increasing scope:

1. **Drop the phrase.** Change the f-string to `f"{examined} examined."` — smallest fix; the note no longer claims a filtering step that may or may not have happened. Cost: any filter-then-narrow case loses the word "filtering" that its note currently carries, but the numbers above still say how many were examined against the source total.

2. **Parameterise the suffix.** Add an argument `filtered: bool` to `_local_truncation`, and have each caller pass it. Verbose; needs every caller updated.

3. **Canonical wording that fits both cases.** *"25 of 656 examined"* or *"25 retrieved of 656"* — honest for both filtered and unfiltered fetches. Slightly more typing but no branching needed.

Option 3 is the smallest honest fix — the note becomes true in every case, and the reader who wants to know whether a filter was applied can see it in the `Intent:` block or the `Plan:` args. Option 1 is the smallest edit if the wording is not load-bearing.

The note is produced in one place (`_local_truncation`), so whichever option is chosen, the blast radius is bounded — but the phrase appears in the 05/07/08 prompt-set baselines (per the function's own docstring), so any change is user-visible across the corpus.

**Regression test.** Assert that `Suppliers with their addresses` produces a truncation note that does not contain the phrase "for filtering". Assert that a filtered prompt (e.g. `active suppliers in US`) also produces a note whose wording is consistent with the fix — either no "for filtering" (option 1/3) or the correct filtered phrasing (option 2). Both must pass.

**Not checked.** Whether the "for filtering" phrase appears in the same note across the other 05/07/08 baselines the docstring names — one prompt run this session; the class-level check is a small sweep, not run. Whether the code's own "total in source" looseness is worth fixing in the same pass — separate concern, deliberately deferred per the docstring. Whether the note is worth replacing entirely with a structured field (`examined`, `total_available`) that the display formats — a formatting-layer change, not read this session. Whether the note appears in golden files (`docs/audit/golden/`) that would need regenerating with the new wording — the three goldens seen this session carry the note in the two with a truncation; regenerating them is part of the fix, not this finding.

**Update 2026-09-22 — fixed on `phase-2-fix-F012-F036-truncation-wording`.**

Fixed alongside F-012 (shared branch; same f-string in
`synthesizer/synthesizer.py::_local_truncation`).

One-word change: `"{examined} examined for filtering."` ->
`"{examined} returned."` The count and source total stay; only the
false claim is removed. The entry's three options were (1) drop the
phrase, (2) parameterise on a `filtered: bool`, (3) canonical wording
that fits both cases. The landed wording is closer in spirit to (1),
but with a verb that reads as prose rather than as a truncated
sentence, and without the `"N of M"` duplication option (3) would have
introduced against the `total in source` count already in the same
line.

Verification:

- Reproducer `Suppliers with their addresses` now answers with
  `25 returned.` in the Truncation block. Pre-fix: `25 examined for
  filtering.`
- Paraphrase `List suppliers with their address` — same wording.
- Filtered sibling `active suppliers in US` — same wording (the fix
  does not distinguish filtered from unfiltered; the filter is visible
  in the Intent block above the answer, so no claim about it is needed
  in the note).
- Negative unchanged: `show me contract renewals` still refuses with
  `unknown_entity`.
- Golden `docs/audit/golden/suppliers_with_open_pos.txt` line 87
  updated in the same commit: `431 total in source; 25 examined for
  filtering.` -> `431 total in source; 25 returned.` (the `431` stays —
  pod-growth drift is not folded into the fix's diff; see §G of the
  audit).
- New file `tests/test_f036_truncation_wording.py` — 2 tests. Both fail
  without the fix.
- Full suite: 1054 passed, 22 deselected.

Deviation from the entry: minor (specific verb). See
`docs/phase-2/fixes/F-036.md` for the full reasoning.

**Class note.** Same note-producing function as F-012 (composite-filter over-fetch cap), different defect: F-012's note under-reports because `examined` was read from the output bucket rather than the fetch size; this finding's note over-claims because "for filtering" presupposes a filter. Both are the same f-string, and a single fix pass could address both — the phase's call whether to do so or treat them separately.

---

## F-037 — D-10's prompt duplicates confirmed; test-set hygiene, no user-visible harm

**Date:** 2026-09-18
**Status:** closed-as-not-a-bug (observation; cleanup item)
**Cross-refs:** D-10

**Evidence.**

```
$ echo "--- intra-file duplicates in 07_alacarte.txt ---"
  grep -v '^#' scripts/prompts/07_alacarte.txt | grep -v '^$' | sort | uniq -d
  echo "--- intra-file duplicates in 11_column_vocabulary.txt ---"
  grep -v '^#' scripts/prompts/11_column_vocabulary.txt | grep -v '^$' | sort | uniq -d
  echo "--- inter-file duplicates ---"
  comm -12 <(grep -v '^#' scripts/prompts/07_alacarte.txt | grep -v '^$' | sort -u) \
           <(grep -v '^#' scripts/prompts/11_column_vocabulary.txt | grep -v '^$' | sort -u)
--- intra-file duplicates in 07_alacarte.txt ---
List active suppliers with supplier name, supplier number, and address

--- intra-file duplicates in 11_column_vocabulary.txt ---
(no output)

--- inter-file duplicates ---
List active suppliers
List active suppliers with supplier name, supplier number, and address
List active suppliers with supplier name, supplier number, and status
Show PO 2144 and its lines
Show me invoices for EIP Inc with invoice number, PO number, and PO line number
Show supplier name and credit rating for active suppliers
Top 5 suppliers by invoice spend last year with supplier name and total
```

Summary of duplicates found:

- **1** exact duplicate within `07_alacarte.txt` (`List active suppliers with supplier name, supplier number, and address` — appears twice).
- **0** exact duplicates within `11_column_vocabulary.txt`.
- **7** prompts appearing verbatim in both files.

The audit's D-10 note ("Duplicated prompts within and between files") is confirmed for the specific pair it names, plus the intra-file instance it did not call out.

**Root cause.** Two prompt files cover overlapping vocabulary — `07_alacarte.txt` is a general "à la carte" set, `11_column_vocabulary.txt` is a projection/field set, and several column-centric prompts naturally belong to both. The exact-duplicate intra-file instance is a copy-paste artifact.

Under S1's harm classes, none applies:

- No wrong data, no wrong narration, no crash, no refusal of an in-scope prompt, no silent omission, no cost regression, no path inconsistency.
- The harm class §D.1 uses ("two prompts asking for different things produce identical answers") does not apply — these are the *same* prompt repeated, not different prompts that coincidentally agree.

The observation's value is bookkeeping: the prompt-set coverage count (12 files, ~200 prompts per the audit's own status line) double-counts by 8. Any audit that reports "we tested N prompts" should count distinct prompts, not file lines.

**Fix location.** None in code — the fix is in the prompt files themselves if the duplicate counting matters:

1. **Delete the intra-file duplicate** in `07_alacarte.txt`. Mechanical.
2. **For inter-file duplicates**, either leave as intentional redundancy (the files serve different purposes and reproducing a prompt in both is defensible if the audit wants each file to be self-contained) or move shared prompts to a common base. The latter is a redesign; not warranted by the finding.

Option 1 is a one-line edit and safe. Option 2 is a corpus design choice, not a bug fix.

**Regression test.** None needed — this is file hygiene, not code. If a test wants to guard against future duplicates, a small pytest asserting no prompt appears twice in the same file is possible; not proposed here.

**Not checked.** Whether the other 10 prompt files (`00`, `01`–`06`, `08`, `10`, `12`, `mini`, `qa_testcases`) have intra- or inter-file duplicates — only the two files the audit named were swept; the class is easy to extend but not run. Whether the intra-file duplicate in `07_alacarte.txt` is byte-identical to what a future version should be (trailing whitespace, smart-quote differences) — the `sort | uniq -d` comparison is byte-exact, so the duplicates are. Whether the audit's "~200 prompts" count in the Status paragraph is the one that should be corrected, or whether the audit tracks distinct prompts elsewhere — a methodology question.

**Class note.** First §D row this session that is genuinely test-hygiene rather than a code defect. §D.1 mixes two kinds of row: code inconsistencies (D-01, D-02, D-12, D-13) and test-set inconsistencies (D-10). The former warrant findings; the latter are bookkeeping. Recording this as an Observation distinguishes the two.

---

## F-038 — D-12's "two refusal messages for one input" does not reproduce; both JSON files record the same flavor

**Date:** 2026-09-18
**Status:** closed-as-not-a-bug (observation)
**Cross-refs:** D-12, F-032 (the D-01 run of the same prompt), F-035 (same closure class)

**Evidence.**

The prompt `Show invoice lines for invoice 300000248096352` appears in four files. The two JSON files carry recorded metadata; both record the same flavour:

```
$ sed -n '270,290p' scripts/prompts/11_column_vocabulary.json
  {
    "prompt": "Show invoice lines for invoice 300000248096352",
    "module": [
      "payables"
    ],
    "tool": "refuse",
    "note": "refuse:unknown_entity (parser)"
  },

$ sed -n '5,20p' scripts/prompts/qa_testcases.json
  {
    "prompt": "Show invoice lines for invoice 300000248096352",
    "module": [
      "payables"
    ],
    "tool": "refuse",
    "note": "refuse:unknown_entity (parser)"
  },
```

Both note the same flavour: `refuse:unknown_entity (parser)`. Neither records `unparseable`.

Live re-run (also this session, for D-01's F-032):

```
$ python scripts/promptkit.py --run --prompt "Show invoice lines for invoice 300000248096352" --show-stages
Router: modules=['payables']
Reason:   I can look up AR invoice lines, but only as part of the record they belong to.

Solution: Ask for the invoice and its lines together.

Example:  Show invoice lines for invoice 300000248096352
  (refusal: unknown_entity — needs an invoice line entity, which is not supported as a target entity)
```

The live run produces `unknown_entity`, agreeing with both JSON records.

Contrast with the audit's D-12 row:

> D-12 | `Show invoice lines for invoice 300000248096352` | Two different refusal messages in two files: `unknown_entity` vs `unparseable`. | Same input, different message.

Today: no `unparseable` variant is recorded anywhere in the corpus; both files carry `unknown_entity`; the live run produces `unknown_entity`.

Small note from the F-032 run earlier this session versus this run — the parenthetical wording differed (`needs an Invoice Line entity` vs `needs an invoice line entity`), and the `parse out=` token count differed (1169 vs 1142). Both are model-prose / model-output variance at the same deterministic flavor; not part of D-12's claim.

Under S1's harm classes, none applies:

- No wrong data — a refusal, no records.
- No wrong narration — the flavour and the Reason/Solution/Example all agree across the two files and the live run.
- No crash, no refusal of an in-scope prompt (correct refusal per §B.3), no silent omission, no cost regression.
- Not an inconsistency between two paths — the two files agree.

**Root cause of the (now-closed) prior claim.** Not established — the symptom did not reproduce. Two possibilities:

- The corpus JSON files were regenerated since the audit (via promptkit's `--generate`), overwriting the note with the current classifier's output.
- The audit's D-12 observation was captured against a differently-scoped parse (e.g. before some router change) and the current corpus was regenerated against the current code.

No git archaeology done; either fits.

**Fix location.** None — closed.

**Re-open criteria.** Any of:

- A run of this prompt producing a flavour other than `unknown_entity`.
- A change to `10_refusal_examples.txt`, `11_column_vocabulary.json`, or `qa_testcases.json` introducing an inconsistent note.
- Regeneration of the corpus JSON with `--generate`, which could overwrite the note if the classifier's output changes — a corpus-consistency guard (mentioned in the handoff as S3's fix direction) would catch that.

**Not checked.** Whether the audit's original `unparseable` observation was against the same pod, code version, or parser cache state — no git archaeology. Whether the corpus files in `10_refusal_examples.txt` (the third file listing the prompt) carry any per-prompt metadata or are plain text — only the two JSON files were read; the two text files were not. Whether the parenthetical wording variation (capitalised "Invoice Line" vs lowercase "invoice line") across two runs of the same prompt is worth tracking as a §H.1 observation — same class as F-035's Reason-prose variance, not this finding's.

**Class note.** Eighth "does not reproduce" closure this session (F-013, F-026, F-028, F-029, F-030, F-034, F-035, this one). This is the mildest form: the two artefacts the audit said disagreed now agree byte-for-byte, and the live run agrees with both. §D.1 has one remaining row without an F-NNN: D-05 (nondeterminism in `Purchase orders created before 2015` truncation metadata), which likely folds into §H.1's existing note about truncation metadata present/absent across runs.

---

## F-039 — "under-invoiced by 864M" for a comparison whose excluded-invoice set is 97.7%

**Date:** 2026-09-18
**Status:** confirmed, not fixed
**Cross-refs:** D-11, F-026 (adjacent — same function, zero-difference case), F-012 (adjacent — narration as authoritative)

**Evidence.**

Runtime, the audit's reproducer:

```
$ python scripts/promptkit.py --run --prompt "Compare ordered vs invoiced for our top 3 suppliers" --show-stages
Intent:
  compare: {'op': 'top_suppliers_invoiced_vs_ordered', ..., 'top_n': 3}

Answer:
Invoiced vs ordered for the top 3 supplier(s) by PO value:
- EIP Inc: ordered 865,110,358.23, PO-matched invoiced 710,712.31 — under-invoiced by 864,399,645.92 (3,210 non-PO invoices excluded).
- Staffing Services: ordered 328,054,713.10, PO-matched invoiced 31,312.91 — under-invoiced by 328,023,400.19 (2,423 non-PO invoices excluded).
- JGA: ordered 159,599,904.78, PO-matched invoiced 4,566,124.36 — under-invoiced by 155,033,780.42 (2,268 non-PO invoices excluded).
```

The excluded-invoice fractions are the substance:

| Supplier | Invoices total | Excluded | Included | Fraction excluded |
|---|---|---|---|---|
| EIP Inc | 3,287 | 3,210 | 77 | 97.7% |
| Staffing Services | 2,437 | 2,423 | 14 | 99.4% |
| JGA | 2,323 | 2,268 | 55 | 97.6% |

Every figure is arithmetically correct — the compare tool paged the full sets (per the MCP server log the user shared: EIP's PO side 2,024 rows / invoices 3,287 rows, Staffing 1,596 / 2,437, JGA 1,551 / 2,323), matched invoices by `PurchaseOrderNumber`, and computed the difference. The narration word "under-invoiced" is not what the arithmetic establishes.

Static:

- `src/spire/synthesizer/aggregation.py::_direction_phrase`:
  ```python
  def _direction_phrase(difference: float) -> str:
      """Neutral over/under/fully phrasing for a signed difference."""
      if difference > 0:
          return f"over-invoiced by {difference:,.2f}"
      if difference < 0:
          return f"under-invoiced by {abs(difference):,.2f}"
      return "fully invoiced (invoiced equals ordered)"
  ```
  The function is called by three summarizers — `_summarize_po_comparison`, `_summarize_supplier_comparison`, `_summarize_top_suppliers_comparison`. It has no knowledge of the excluded-invoice count and returns the same "under-invoiced" wording regardless.

- `src/spire/mcp_server/tools/compare_orders_to_invoices.py`'s own module docstring names the data shape:
  > on this pod most invoices are not PO-linked (debit memos, prepayments), so a supplier's PO-matched invoiced total is typically far below its total invoiced. `unmatched_invoice_count` reports the non-PO invoices; they are context, not folded into the comparison.

  The tool does the right thing (reports the count); the synthesiser's word is what over-claims.

Identity note. §D.1's D-11 row records this prompt and the "under-invoiced by 864,399,645.92" figure, with the audit's own note "accurate but invites misreading. ~1% of invoices are PO-linked on these pods." The ~1% figure is confirmed on today's data (2.3%, 0.6%, 2.4% for the three suppliers). The audit's framing is preserved; the finding classifies the misreading as a wrong-narration harm under S1.

**Root cause.** `_direction_phrase` produces a supplier-behaviour word — "under-invoiced" — for a comparison in which the excluded set is 97%+ of the invoices. The word asserts a billing state ("EIP was invoiced 864M less than ordered"); the arithmetic establishes a document-matching state ("97.7% of EIP's invoices have no PO number to match against"). The two are different claims; only the second is supported. The parenthetical `(3,210 non-PO invoices excluded)` discloses the excluded count but is subordinate to the headline number.

**Fix location (for Phase 2).** Two options, in increasing scope:

1. **Soften for the aggregate shapes.** `_direction_phrase` is called by three summarizers; the single-PO shape (`_summarize_po_comparison`) has a bounded excluded set and the word is fair there. The two aggregate shapes (`_summarize_supplier_comparison`, `_summarize_top_suppliers_comparison`) have the unmatched count available. A new phrasing for those callers — e.g. *"864,399,645.92 of ordered value has no PO-matched invoice"* — names the data state, not a supplier behaviour. Cost: local; the phrasing helper needs an unmatched-ratio parameter or the callers need to choose their own wording.

2. **Change `_direction_phrase` universally.** Replace "under-invoiced by X" with "ordered exceeds PO-matched invoiced by X" (and "over-invoiced" → "PO-matched invoiced exceeds ordered"). Cost: changes the single-PO case too, where the current wording is accurate; the phrasing loses a small amount of readability for a large amount of correctness.

Option 1 is the honest fix. Option 2 trades accuracy for uniformity. The reference points: the tool's docstring says *"Nothing here treats an over-invoice as an error... The tools report the numbers and the difference; judging them is the reader's job."* — "under-invoiced" is a judgement, not a report of a number. The fix is to make the wording report the state of the data.

**Regression test (either fix).** Assert that `Compare ordered vs invoiced for our top 3 suppliers` produces narration whose phrasing does not use the word "under-invoiced" (or "over-invoiced") when the excluded-invoice fraction exceeds a threshold (the threshold value is the phase's call, but the current data makes 90% a natural one). Assert that a single-PO comparison (`How does invoiced compare to ordered for PO 162034?`) still produces a comparison whose phrasing the reader can act on.

**Not checked.** Whether the single-PO comparison's "under-invoiced" wording is accurate — the falsifier was not run; the reasoning above presumes it is because the excluded set for a single PO is bounded. Whether the same over-claim affects the single-supplier (non-top-N) comparison — same caller class as top-N, likely yes, not run. Whether a threshold for the excluded-invoice fraction should live in the tool (which knows the counts), the summarizer (which composes the sentence), or the response schema (which could carry a `linkage_ratio` field) — a fix-location design question, not this finding's. Whether the `<1%` audit figure should be re-measured against the current pod — today's three suppliers give ~2%; the audit's number was pod-wide and may have been lower.

**Class note.** Fourth narrative-mischaracterisation finding this session, alongside F-014 (a `fields` request rendered as `—`), F-020 (a run-on that asserts an unverifiable property), F-026 (a zero-PO comparison narrated as "fully invoiced"). The pattern: the pipeline produces a number or shape correctly and then a word is chosen that asserts more than the number supports. All four fix sites are in the synthesis layer.

---

## F-040 — `Purchase orders created before 2015` truncation block is deterministic at N=20; D-05 / §H.1 do not reproduce

**Date:** 2026-09-18
**Status:** closed-as-not-a-bug
**Cross-refs:** D-05, §H.1 (matching observation), F-022 / F-023 / F-024 (same closure family)

**Evidence.**

Twenty runs of the audit's reproducer:

```
$ for i in $(seq 1 20); do
    echo "=== run $i ==="
    python scripts/promptkit.py --run --prompt "Purchase orders created before 2015" --show-stages 2>&1 \
      | grep -E "^Truncation:|^  - |^  Records returned:|^  Final raw output:|^There are|^Showing"
  done
=== run 1 ===
Showing 25 of 878 purchase orders.
Truncation:
  - open_pos: 878 total in source; 25 examined for filtering.
  Records returned:     25 (across all steps)
  Final raw output:     25 record(s) under 'open_pos'
=== run 2 ===
(identical)
...
=== run 20 ===
Showing 25 of 878 purchase orders.
Truncation:
  - open_pos: 878 total in source; 25 examined for filtering.
  Records returned:     25 (across all steps)
  Final raw output:     25 record(s) under 'open_pos'
```

All twenty runs: truncation block present, same counts (`878 total in source; 25 examined`), same fetch shape. No run was missing the block.

Contrast with the audit's D-05 row and §H.1's matching bullet:

> D-05 | `Purchase orders created before 2015` | Truncation block present in one run, absent in another. | Cross-reference §H.1.

> §H.1: **Truncation metadata is nondeterministic.** `Purchase orders created before 2015` — block present/absent across runs.

The observation does not reproduce at the audit's own threshold (N≥20, per §H.1's methodology).

**Root cause.** Not established — the failure did not reproduce. The likely historical explanation, from reading the code: the truncation block appears iff the tool's `ToolResult.truncated` flag is `True`, which depends on `total_available > len(items)`. If `total_available` (from the pod) or `len(items)` (from the tool's paginated fetch) fluctuated at audit time, the block would come and go. The pod's `/purchaseOrders` collection has grown during the audit (measured 15,839 on 2026-08-04; today the matching set for "created before 2015" is 878). Growth alone would not flip `truncated` for this prompt — the fetch is capped at 25 regardless — but a pod-side response shape change, or a historical tool change, could.

No git archaeology done; either fits.

**Fix location.** None — closed.

**Re-open criteria.** Any of:

- A same-prompt run producing a different truncation shape (absent block, or a different `total_available`).
- A change to `mcp_server/tools/purchase_orders.py`'s `ToolResult` construction, or to `synthesizer/synthesizer.py::_local_truncation`.
- A change to the pod's `/purchaseOrders` `totalResults` reporting.

**Not checked.** Whether the audit's observation was captured against a different pod, code state, or parse path — no git archaeology. Whether other date-bound PO prompts (`POs created since March 2024`, `POs created between Jan and Mar 2025`) share the same behaviour — one prompt run this session. Whether the "present/absent" observation was actually about the *synthesized summary* mentioning truncation vs the *Truncation:* footer block — the audit's wording is ambiguous; today's runs have both present.

**Class note.** Fourth nondeterminism closure this session (F-022, F-023, F-024, this one). All four audit-observed nondeterminism rows that named a specific prompt closed clean at N=20. The pattern holds: the audit's observations were real at capture; the current state is deterministic; the audit rows stay as written per append-only discipline.

**§H.1 cross-reference.** The matching bullet ("Truncation metadata is nondeterministic. `Purchase orders created before 2015` — block present/absent across runs.") is now closed. The one other §H.1 bullet still flagged as "material to Phase 6c" (parse-stage empty-draft retry) and the four remaining untested observations (relative date resolution, parser output length variance, insertion-order bias, largest-answer) remain open.

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
**Status:** verified (PR #153, 2026-09-22)
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

**Update 2026-09-22 — fixed on `phase-2-fix-F001-list-all-flag`.**

`parse()` now calls `_is_explicit_po_list(prompt)` on a
PurchaseOrder-rooted intent and assigns the result to `intent.list_all`,
placed immediately before the BUG-1 include-correction block. Same
post-parse, pure-Python, zero-prompt-text shape as the four helpers
already in the function. `planner/models.py` and `draft.py` needed no
change: the field was already declared, and the flag is deliberately not
an LLM concern (it is computed from the raw prompt, after the LLM).

Verification:

- Reproducer `list purchase orders` now answers — 25 of 17,524 POs, no
  refusal. Pre-fix output was
  `missing_identifier — PurchaseOrder root has no identifier and no
  explicit list request`.
- Boundary probes: `list all purchase orders` and `show all POs` list;
  `purchase orders` (bare noun, no verb) still refuses; `list the lines
  on PO 2144` correctly routes to `by_id` and returns 2 line records
  (the PO-number clause in the predicate holds).
- New file `tests/test_f001_list_all_flag.py` — 6 tests.
  `test_list_purchase_orders_sets_list_all_true` fails without the fix
  (`assert False is True`; reversion confirmed by `git stash push` of
  `parser.py`, running the file, and `git stash pop`).
- Full suite: 1034 passed, 22 deselected (baseline 1028 + 6 new).

Residual observation, out of scope. The answer's truncation line now
reads `25 examined for filtering` on an unfiltered fetch — that is
F-036's defect, pre-existing and outside F-001's scope. The note is
visible today only because the fetcher is reachable; before the fix no
answer was produced at all.

---

*End of findings log.*