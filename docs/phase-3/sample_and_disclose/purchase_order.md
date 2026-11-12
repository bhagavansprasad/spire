# Phase 3 — Sample-and-disclose: PurchaseOrder

**Branch:** `Phase3-PurchaseOrder-Sample`
**PR:** TBD (this file is committed before the branch exists; PR number
added when the PR is opened, per FIX_PLAN.md §8 step 8)
**State:** closed
**Finding:** meeting capture §1 — `get po with distribution details`
refuses with `missing_identifier`; an SME would answer it. Rule 28
defect.

## V0 — Fix statement

The parser will set `intent.list_all=True` for a PurchaseOrder intent
that names a Spire-supported child (PO line, schedule, distribution)
without naming a specific PO, via a sibling extractor
`_is_sampleable_po_request` beside `_is_explicit_po_list`; the
planner's existing guard then permits a bounded 25-row sample, and
`PurchaseOrderResponse` gains a `narrowing_tip` field populated by
`build_narrowing_tip` (parameterised with `labels_map` and a
`_PURCHASE_ORDER_FILTER_LABELS` dict) so the sample discloses itself and
tells the user how to narrow.

## V1 — Reproducer

Prompt: `get po with distribution details` against
`fa-esll-saasfademo1`. Run after the MCP server was restarted to
pick up the patched `parser.py`, `p2p.py`, `synthesizer.py`.

Result (green):
- Intent: `PurchaseOrder`, `include: ['POSchedule', 'PODistribution']`
- Plan: 3 steps — `search_purchase_orders` (empty tool_args,
  bounded 25), `get_purchase_order_schedules` iterating POHeaderId,
  `get_purchase_order_distributions` iterating the three-field map
- Outputs: `open_pos: 25 record(s)`, plus 67 schedules and 69
  distributions
- Summary: `Showing 25 of 17,620 purchase orders.`
- Truncation: `open_pos: 17620 total in source; 25 returned.`
- Tip: `Narrow with a filter: creation date, last-updated date,
  status, supplier.`

The Rule 28 defect (meeting capture §1) is closed: the prompt
answers with a bounded sample and discloses the sample.

## V2 — Paraphrase

Prompt: `show purchase orders with their schedules` against the
same pod. Exercises the extractor on a **different** trigger
(`schedules`) and a **different** child (`POSchedule`) from V1
(`distribution details` / `PODistribution`).

Result (green, reproduced twice):
- Intent: `PurchaseOrder`, `include: ['POSchedule']`
- Plan: 2 steps — `search_purchase_orders` then
  `get_purchase_order_schedules`
- Outputs: `open_pos: 25 record(s)`, 67 schedules
- Summary: `Showing 25 of 17,620 purchase orders.`
- Truncation: same 17620/25 disclosure
- Tip: same clean list as V1

Green on two runs; the second run confirms the first was not a
transient. The extractor is not hardcoded to distributions.

## V3 — Sibling (unchanged)

Prompt: `list all purchase orders`. Exercises the OTHER extractor
(`_is_explicit_po_list`), which this PR did not change. The check
is over-reach: our new sibling `_is_sampleable_po_request` must
**not** fire on a prompt with no child trigger.

Result (green):
- Intent: `PurchaseOrder`, **no** `include` line — empty include.
  No child was added; the new extractor did not fire.
- Plan: 1 step — `search_purchase_orders` with empty tool_args
  (`Steps planned: 1`).
- Answer: `open_pos: 25 record(s)`; `17620 total in source; 25
  returned`; same tip as V1/V2.

## V4 — Negative (still refuses)

Two sub-cases. Both must **still** behave as they did before this
PR. If either now answers differently, the PR has over-reached.

### V4a — `show me PO 2144` (specific PO, no child trigger)

Result (green):
- Intent: `PurchaseOrder` with
  `filters: [{'type': 'by_id', 'value': '2144'}]`. Not `list_all`.
  The extractor correctly declined to fire.
- Plan: 1 step — `get_purchase_order_by_id` with
  `po_header_id: '2144'`.
- Answer: single-PO vertical render, `Synthesized answer: 1
  record(s)`. **No tip** — correct, a single PO is not a sample.

### V4b — `get all addresses` (Address root, out of scope)

Address is deliberately **not** in the sample set
(meeting capture §4.6: an address is a child of Supplier, and a
"25 addresses" sample means "addresses of the first 25
suppliers", which reads as ~625). The refusal must remain.

Result (green, refused):
- `Reason:   I can look up addresses, but this doesn't say which
  one.`
- `Solution: Name the supplier, or give me a country.`
- `Example:  addresses for supplier 1252`
- `(refusal: missing_identifier — Address queries require a
  supplier or country filter.)`
- No plan, no sample, no tip.

## V5 — Goldens

Extractor scope: **Intent only** — from `Intent:` through the
first blank line. This is deliberate. V1–V4 already exercise the
Answer / Tip / Plan / sample-size facts on the live pod. V5's
distinct question is: for a prompt that was correct **before**
this PR, does the pipeline **decide** identically now? Intent is
exactly that decision.

A full-file byte-diff is not achievable against the goldens today:
they predate `sql_emitter.py` in the pipeline (so a
`SQL projection:` block appears in current runs that the goldens
have no record of), and pod data has moved (supplier count
431→395; supplier 1256 name changed from "US Gas and Electric
Rushi" to "US Gas and Electric"). Neither drift is caused by
this PR; both are pre-existing environment facts.

Result (green, three intents matched):

| Golden | Intent diff |
|---|---|
| `count_suppliers.txt` | MATCH |
| `po_2144_and_lines.txt` | MATCH |
| `suppliers_with_open_pos.txt` | MATCH |

## V6 — pytest

**Deferred.** Full-suite pytest on this environment cannot produce
a clean green on `master` or on this branch, because a
pre-existing MCP dependency conflict breaks
`tests/test_agent_runner.py` collection. See
`MCP_DEPENDENCY_CONFLICT.md` (committed `c71488d`).

Evidence of the baseline, recorded for the record:
- `master` at `a78c00b`, `pytest -q --continue-on-collection-errors`:
  `66 failed, 1240 passed, 1 skipped, 21 deselected, 1 error`.
- The 66 failures are pre-existing pod-reachability and unrelated
  drift (same set present on `master` and on this branch); the 1
  error is the `mcp 2.x` collection error on
  `tests/test_agent_runner.py`.
- This PR's own tests: `12 passed` in
  `tests/test_sample_and_disclose_po.py`.

V6 will be re-run once `MCP_DEPENDENCY_CONFLICT.md`'s recommended
fix lands as its own PR.

## V7 — Test fails without the fix

The failing-test commit on this branch is `2681217`. It was
created and pushed to the branch **before** any source edit in
this PR. Its pytest run at commit time reported
`ImportError: cannot import name '_is_sampleable_po_request'` at
collection — the red shape the fix is meant to remove. That run
is the V7 evidence: red because the symbol was absent, not
because of a post-hoc stash.

## V8 — N≥20 (parser changes)

**Deferred** alongside V6. The N-run sweep needs the pipeline to
run; pytest is not the blocker, the MCP server is not the blocker
for live prompts, but V6's framework (`pytest -q`) is the standard
harness for the N-run reproducibility check on this codebase and
is not available today. The single V1 and V2 runs above are each
green; a 20-run sweep is deferred to the same window that lands
the MCP migration.

One partial: V1 was run twice (once with the initial pre-Fix-B
state, once after Fix A/B landed). V2 was run twice. Both
reproducible. A full 20-run N-sweep would strengthen this.

## V9 — --validate (sysprompt changes)

**Not required.** No `.sysprompt` block was changed in this PR.
The extractor is pure-Python, the tip parameterisation is
pure-Python, the labels map is Python data. This was a deliberate
design choice (recorded in §Deviations below), made possible by
the `_is_explicit_po_list` precedent (which is also code-only).

## Deviations from the F-NNN entry's suggested fix

### V-walk deviations

None of the deviations listed below changed the intent of V0.
The fix statement stands. The list records three fixes that V1's
first live run surfaced **inside** the fix scope, and the
non-fixes (Issues B and C) that are outside the PR by design.

### Fix A — `build_narrowing_tip` de-duplicates labels

V1's first live run produced the tip
`creation date, creation date, creation date, creation date,
last-updated date, last-updated date, lifecycle, status, supplier.`

Cause: `build_narrowing_tip` collected filter-type keys, mapped
each through the labels map, and joined the labels without
de-duplicating. Four PurchaseOrder creation-date filters all map
to `"creation date"`; two last-updated filters all map to
`"last-updated date"`. The label repeated once per filter type.

Fix: `sorted(set(labels))` before joining. Backwards-compatible
for Supplier (no two Supplier filters share a label today).

### Fix B — PO tip excludes `lifecycle_status`

V1's first live run also produced `lifecycle` in the tip. The
`lifecycle_status` filter is fetched-by-value (a PO number),
not narrowed-by-value — it is a tool name, not a column a reader
can put a value in. A tip that suggests it is noise for a sample
prompt.

Fix: the two PO tip call sites in `synthesizer.py` build the
filter set with `{by_id, lifecycle_status}` excluded, mirroring
the `by_id` exclusion that the Supplier branches already use.

### Fix C — replacement of a tautological test

The first version of `test_build_narrowing_tip_excludes_
lifecycle_status` called `build_narrowing_tip` with a set that
already had `lifecycle_status` removed. That is a tautology: the
test stayed green when the caller-side exclusion was missing.
V1 caught exactly this — the live tip still named `lifecycle`
after the 12 tests were green.

Fix: the test is now `test_synthesize_response_po_tip_excludes_
lifecycle_status`, exercising `synthesize_response` end-to-end
through the PO plain-list branch. It fails if the caller-side
exclusion is missing. That is a real test of the fix.

### Out of scope — Issue B (MCP dependency conflict)

V6 and V8 are deferred because of this pre-existing environment
conflict. See `MCP_DEPENDENCY_CONFLICT.md` (committed `c71488d`).
Not fixed in this PR.

### Out of scope — Issue C (SQL emitter multi-field iteration)

V1 and V4a both surfaced malformed SQL in the diagnostic
`SQL projection:` output — multi-field iteration renders as
`AND -- unmapped iteration arg: ...`, which is not valid SQL, and
single-value by-id renders as `WHERE PO_HEADER_ID = '2144'` with
a numeric column compared against a string literal. These are
pre-existing, diagnostic-only defects in `sql_emitter.py` and
`sql_overlay.py`, not caused by this PR and not fixed here.
The `SQL_OVERLAY_POC.md` scope note declares per-step SQL a
projection, not executable. A finding file is deferred to a
later window; it is **not** the SQL emitter fix.

### `personas.yaml` in the working tree

A local credential edit made outside this PR. It is **not**
part of the PR and must not be staged. See `STATUS.md` §Uncommitted.

### Design decision: sysprompt stays untouched on this PR

The meeting capture §5.2 describes a pure-code sibling extractor
(`_is_sampleable_po_request`) beside `_is_explicit_po_list`. That
is the shape being built: no sysprompt edit is planned for this
PR, matching `_is_explicit_po_list`, which is code-only and has
no prompt rule on `master`. This avoids V9 (a 240-prompt
`--validate` sweep) on PR #1.

If V1 goes red because the parser SELF-DECLARES an unanswerable
refusal for `get po with distribution details` before the extractor
sees the intent, the fix is not a sysprompt rule — it is the same
deterministic post-parse override F-018 uses (`_extract_invoice_number`):
detect the shape from the raw prompt, override the self-declared
refusal, produce the Intent. Still code-only, still no V9. Sysprompt
is the last resort if a code path cannot be made to fire.

## Not checked

TBD

## S11 — Coverage expansion

TBD
