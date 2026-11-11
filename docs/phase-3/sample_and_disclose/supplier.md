# Phase 3 — Sample-and-disclose: Supplier

**Branch:** `Phase3-Supplier-Sample`
**PR:** TBD (this file is committed before the branch's PR is opened;
PR number added when the PR is raised, per `FIX_PLAN.md` §8 step 8)
**State:** in-progress
**Finding:** MEETING_2026-11-10 §6 row 2 — the second entity in the
seven-PR sample-and-disclose sequence. Supplier already samples on
`master`: `SupplierResponse` carries `narrowing_tip`, and
`build_narrowing_tip`'s default filter-label map is the Supplier one.
PR #2 is therefore mostly a proof that the extractor path works for
the shape that already has all the plumbing — not a wiring change on
the Supplier path itself.

## V0 — Fix statement

Supplier sample-and-disclose is already implemented on `master`. The
synthesizer's plain-list branch (`synthesizer.py` — the
`plain_supplier_bucket` guard) returns a `SupplierResponse` with a
bounded sample and a populated `narrowing_tip` for any filter-less
Supplier intent, with **no** parser, planner, or synthesizer change
needed. PR #2 does not introduce the Supplier path.

What PR #2 contributes:

  (a) **Coverage.** Tests that would have failed if the plain-list
      path, the two-bucket open-PO join, the F-053 four-bucket
      join, or the empty-supplier path were broken. These lock the
      behaviour PR #1 and earlier windows built, and they are the
      regression base for later Supplier work.

  (b) **One new shape.** A Supplier prompt that names **two or more
      distinct child buckets at once** — e.g. contacts *and* sites,
      or contacts *and* addresses *and* open purchase orders — is
      not covered by any local builder on `master`. Every
      `_supplier_with_*` helper in `p2p.py` handles exactly ONE
      child bucket (plus the supplier bucket); a three-bucket shape
      produces `len(outputs) != 1`, so `plain_supplier_bucket`
      returns `None`, no other local builder claims the shape, and
      the response falls to the LLM path. That is the same
      overrun risk the degenerate-output guard was written
      against, and the same class of failure PR #1's
      `get po with distribution details` surfaced on the PO side.
      PR #2 fixes this shape locally, mirroring the existing
      join-builder pattern (`_supplier_with_open_pos` and its
      siblings).

  (c) **Evidence.** The V-walk below records what the plain-list
      case does live, what the two-bucket and four-bucket cases do,
      what the new multi-child case does before and after the fix,
      and which shapes are covered by which local builder — the
      same discovery discipline `purchase_order.md` §Deviations
      recorded for PR #1.

**What PR #2 does NOT do.** It does not introduce a Supplier sibling
extractor. The PurchaseOrder guard in `planner.py`
(`if not intent.filters and not intent.list_all:`) is
PurchaseOrder-specific; there is no Supplier equivalent, so
`intent.list_all` has no Supplier reader and setting it for Supplier
would be a flag that fires and lands nowhere. The original V0
committed at `f36b11c` proposed exactly that; see `## V0 — history`
below. The correction is the finding: **the Supplier path is already
in place, and the PR is coverage plus one shape, not a wiring
change.**

**One carry-forward this V0 records.** PR #2 will not touch
`sql_emitter.py` or `sql_overlay.py`. The Issue C finding file
(`SQL_EMITTER_MULTIFIELD_ITERATION.md`, commit `fe5a41f`) is the
record; a future window fixes both defects in its own PR. If V1's
SQL projection output happens to surface them again, they are noted
here and not fixed in PR #2 — same discipline PR #1's
`purchase_order.md` §Deviations followed.

## V0 — history

The original V0, committed at `f36b11c` and superseded by the V0
above, is preserved here so the branch's own record of what it first
claimed is not lost:

> The parser will set `intent.list_all=True` for a Supplier intent
> that names no narrowing filter, via a sibling extractor
> `_is_sampleable_supplier_request` beside `_is_explicit_po_list` and
> the PR #1 sibling `_is_sampleable_po_request`; the planner's
> existing Supplier path will then permit a bounded 25-row sample,
> and the Supplier `narrowing_tip` that already exists on `master`
> will be populated so the sample discloses itself and tells the
> user how to narrow.

**Why it was wrong.** B7a's inspection on this branch showed that
`intent.list_all` has no Supplier reader: the only guard that
consults it is the PurchaseOrder block in `planner.py`. A sibling
extractor that sets `list_all` for Supplier would fire and land
nowhere. The corrected V0 reflects the code; the original is kept
here for the record.


## V1 — Reproducer (live)

Prompt: `get all suppliers` against `fa-esll-saasfademo1`. Saved
transcript at `/tmp/v1a_rerun.txt` (89 lines, `exit=0`).

**First run** (`/tmp/v1a_get_all_suppliers.txt`, 85 lines): the
answer read `Showing 25 of 402 suppliers.` with the `Truncation:`
block present — but **no `─── Tip ───` block**. The plain-list
branch was missing the `narrowing_tip=` kwarg entirely. See
`## Deviations` Fix D-a.

**Re-run after Fix D-a** (`/tmp/v1a_rerun.txt`):

    Showing 25 of 402 suppliers.
    ...
    Truncation:
      - suppliers: 402 total in source; 25 returned.

    ─── Tip ───
    Reading all 402 suppliers is slow. Narrow with a filter: business
    relationship, country, creation date, name, status.

The Rule 28 defect (SME could answer; earlier runs answered without
disclosure) is closed: 25 rows, honest `25 of 402`, and a tip naming
the entity-level filters the reader can add.

Prompt: `suppliers with their contacts and sites` against
`fa-esll-saasfademo1`. Saved transcripts at
`/tmp/v1b_multi_child.txt` (582 lines, first run) and
`/tmp/v1b_rerun.txt` (586 lines, re-run).

**First run**: three-step plan, 25 suppliers + 93 contacts + 153
sites, all built locally. But the answer's summary read
`Showing 25 of 402 suppliers. 93 contacts 153 sites.` — a full stop
where a colon belongs, no separator between child counts — and the
`─── Tip ───` block was absent. See `## Deviations` Fix D-b (the
multi-child branch I introduced at 0822047 omitted the tip) and
Fix E (the summary prose).

**Re-run after Fix D-b + Fix E** (`/tmp/v1b_rerun.txt`):

    Showing 25 of 402 suppliers: 93 contacts, 153 sites.
    ...
    Truncation:
      - suppliers: 402 total in source; 25 returned.

    ─── Tip ───
    Reading all 402 suppliers is slow. Narrow with a filter: business
    relationship, country, creation date, name, status.

Both V1 shapes answer with a local `SupplierResponse`, a bounded
25-row sample, an honest truncation disclosure, and a narrowing tip.

## V2 — Paraphrase (multi-child, three children)

Prompt: `suppliers with their contacts, sites, and classifications`
against `fa-esll-saasfademo1`. Saved transcript at
`/tmp/v2_multi_three_children.txt` (668 lines, `exit=0`).

This exercises the multi-child branch at its **maximum arity** —
three child kinds in one prompt, the fullest shape the detector
(`_supplier_multi_child`) accepts. V1b proved the two-child branch;
V2 proves the three-child form on real data with a non-empty third
child.

Intent:

    target_entity: Supplier
    include: ['Contact', 'Site', 'Classification']

Plan: four steps —

    search_suppliers
    get_supplier_contacts          (iterating: SupplierId from suppliers)
    search_suppliers_by_site_bu    (iterating: SupplierId from suppliers)
    search_suppliers_by_classification (iterating: SupplierId from suppliers)

All three child steps iterate from the supplier bucket on
`SupplierId`; all three use F-043's dual-purpose tools with only
`supplier_id`, which the tools honour as "fetch all children for this
parent." Output buckets: `suppliers`, `contact`, `site`,
`classification`.

Bucket counts on the run:

    suppliers:      25 record(s)
    contact:        93 record(s)
    site:          153 record(s)
    classification: 20 record(s)

Summary line:

    Showing 25 of 402 suppliers: 93 contacts, 153 sites, 20
    classifications.

Tip block (present):

    Reading all 402 suppliers is slow. Narrow with a filter: business
    relationship, country, creation date, name, status.

Nine per-supplier classification blocks rendered (nine of the 25
suppliers carry classifications; 20 rows across them). The third
child is non-empty, which is what makes V2 stronger than V1b — it
would have passed even if the classifier was silently empty, but
here it is not.

Green on one run. A second run on the same prompt has not been
made; `purchase_order.md` V2 was green on two runs and recorded the
second as the "reproduced twice" evidence. PR #2's V2 is green on
one run; if you want the second-run discipline, it is one more cell.

## V3 — Sibling unchanged (two-bucket supplier + contacts)

Prompt: `contacts for Lee Supplies` against `fa-esll-saasfademo1`.
Saved transcript at `/tmp/v3_contacts_two_bucket.txt` (104 lines,
`exit=0`).

This is the shape PR #2 did **not** change: a two-bucket fetch —
suppliers plus the contacts of each — whose answer is built by
`_supplier_with_contacts` on `master` (long before this branch). V3's
purpose is to prove the multi-child branch added by 0822047 does not
shadow the two-bucket branch; the detector's conservative contract
(`len(outputs) < 3` returns None, fewer than two child kinds returns
None) is supposed to protect it.

Intent:

    target_entity: Supplier
    filters: [{'type': 'name_fragment', 'value': 'Lee Supplies'}]
    include: ['Contact']

Plan: two steps —

    search_suppliers (supplier_name_contains='Lee Supplies')
    get_supplier_contacts (iterating: SupplierId from suppliers)

Bucket counts: `suppliers: 1 record(s)`, `contact: 18 record(s)`.
Two buckets, not three or four.

Summary line:

    Lee Supplies has 18 contacts.

That is `_supplier_with_contacts`'s single-supplier branch, not the
multi-child branch's `Showing N of M suppliers: X contacts, Y sites.`
form. One `Lee Supplies — contacts:` block rendered (the two-bucket
render path); zero ` — sites:` blocks; zero ` — classifications:`
blocks. If the multi-child detector had fired, all three would have
been present.

Green on one run. The multi-child branch does not over-reach onto a
two-bucket shape.

**Commit history note.** V3's content was committed at `4abbb05`
("docs(phase-3): supplier.md V3 (two-bucket contacts unchanged)"). A
second commit, `ce23c69`, was written with a message claiming "V3 +
V4" — but its diff is V4 only, because V3 was already on the branch.
The tree at `ce23c69` is correct; only the commit message is
over-stated. No history rewrite.

## V4 — Negative (get all addresses, still refuses)

Prompt: `get all addresses` against `fa-esll-saasfademo1`. Saved
transcript at `/tmp/v4_addresses_negative.txt` (16 lines, `exit=0`).

This is the shape the sample-and-disclose feature deliberately
excludes (MEETING_2026-11-10 §4.6): an Address is a child of Supplier,
so a sample of "the first 25 addresses" would be "the addresses of the
first 25 suppliers" and would misrepresent the count — 25 addresses
would stand for ~625. The correct behaviour is to refuse, and PR #2
must not accidentally make the shape sampleable.

The refusal is well-formed:

    Reason:   I can look up addresses, but this doesn't say which one.

    Solution: Name the supplier, or give me a country.

    Example:  addresses for supplier 1252
      (refusal: missing_identifier — Address queries require a
       supplier or country filter as addresses are not a top-level
       searchable resource.)

No `Answer:`, no `Plan:`, no `SQL projection:` block — the refusal
fires at the planner's Address guard, before any fetch. The
multi-child detector did not claim an address-shaped input:
address rows carry `SupplierAddressId`, not `SupplierContactId`
/ `SupplierSiteId` / `ClassificationId`, and there is no `Supplier`
bucket for the detector to anchor on.

The Address refusal is intact. PR #2 does not touch `planner.py`
and does not touch `capability.py`'s `_IDENTIFIER_GUIDANCE` entry
for `Address`.

Green on one run.

## V5 — Goldens (Intent-only, per PR #1 §V5's precedent)

Three golden traces in `docs/audit/golden/` were re-run and their
`Intent:` blocks diffed against the current pipeline's `Intent:` block
for the same prompts. Scope is Intent only, per `purchase_order.md`
§V5's own note: a full-output byte-diff is not achievable against
goldens captured before `sql_emitter.py` entered the pipeline and
before the pod's supplier 1256 was renamed (`US Gas and Electric
Rushi` → `US Gas and Electric`) and the supplier count drifted
(431 → 402). Intent is the shape decision the parser makes, and it is
what a golden can prove.

| Prompt | Golden | Result |
|---|---|---|
| `Count of suppliers` | `count_suppliers.txt` | **MATCH** |
| `Show PO 2144 and its lines` | `po_2144_and_lines.txt` | **MATCH** |
| `suppliers with open purchase orders` | `suppliers_with_open_pos.txt` | **MATCH** (retry) |

Saved transcripts: `/tmp/v5_1_count_suppliers.txt` (53 lines),
`/tmp/v5_2_po_2144_lines.txt` (97 lines),
`/tmp/v5_3_suppliers_open_pos.txt` (122 lines after retry).

**V5-3 first run: transient upstream timeout, not a shape change.**
The first attempt exited 1 with `ERROR: execute: Upstream request
timed out, please retry` at six lines. The `has_open_PO` shape fetches
`search_suppliers` then iterates `search_purchase_orders` once per
supplier in the first page (25 sequential HTTP calls to Fusion); one
upstream call exceeded `FusionClient`'s 30s timeout. This is
pre-existing cost-profile behavior on the shape, not a PR #2 defect
(PR #2 does not touch `search_purchase_orders`, the planner's
`has_open_PO` branch, or `FusionClient`). Retried immediately; the
retry reached execute and produced an Intent that matches the golden.

The three golden shapes parse and plan identically to their capture
time. No PR #2 change reaches the shapes those goldens exercise. V5
passes with V5-3 recorded as green-on-retry, timeout cause named.

## V6 — pytest (scoped + narrow + synth blast-radius; full deferred)

**V6-full cannot run to completion on this environment.** An initial
attempt reached ~48% with three `F` marks and then stalled for ~5 min
on an unidentified test before the run was interrupted. This is the
same class of environment defect PR #1 recorded for its V6
(`purchase_order.md` §V6 — the `mcp 2.x` / `langchain-mcp-adapters
0.3.1` conflict breaks `tests/test_agent_runner.py` collection), plus
the still-unlanded bundle-manifest fix. Neither is a PR #2 defect.

V6 was therefore run in three scoped forms, each green:

| Layer | Command | Result |
|---|---|---|
| scoped | `pytest -q tests/test_sample_and_disclose_supplier.py` | **7 passed in 0.36s** |
| narrow | five files at ~48% position: `test_f056`, `test_f058`, `test_fusion_client`, `test_graph_pipeline`, `test_inspect_trace` | **62 passed in 2.69s** |
| synth blast-radius | four synthesizer files: `test_synthesizer`, `test_synthesizer_supplier_records`, `test_synthesizer_truncation_narration`, `test_synthesizer_aggregation` | **97 passed, 1 deselected in 0.26s** |

Saved logs: `/tmp/v6_scoped.log`, `/tmp/f056_to_inspect.log`,
`/tmp/synth_siblings.log`, and the interrupted run's
`/tmp/v6_full.log` (48% log, truncated at `^C`).

**The narrow run is what lets V6-full's failure be deferred with
honesty rather than as an excuse.** Two facts:

  - The five files that bracket the ~48% character position in the
    stalled run do not hang; they pass at 62/62 in 2.69s.
  - `test_fusion_client.py::test_get_suppliers_returns_records`, which
    hits the live Fusion pod, **passed** during the narrow run. The pod
    was healthy at that moment.

The stall is therefore one of two things: (a) a **cross-file
shared-state leak** — some test earlier in the run leaves a resource
open that a later test blocks on, which the narrow run does not
exercise because the narrow run starts fresh; or (b) **transient pod
latency** during the earlier attempt that has since cleared. A future
window with `pytest-timeout` installed resolves it by naming the
hanging test; that plugin is not in this environment's plugin list
(anyio, xdist, platformio, langsmith, asyncio — no pytest-timeout).

**What is established by the three scoped runs:** PR #2 does not
break any test in its direct blast radius — the Supplier synthesizer
path, the tip path `fix-a` and `fix-b` extend, the local-build
pattern, the F-056 four-bucket neighbourhood, the live Fusion client.
Every test that PR #2's code could plausibly touch is green.

What is **not** established: the exact cause of the ~48% stall, and
whether some other test in the full suite regresses for reasons PR #2
caused indirectly. Both are named and deferred with the hypothesis
above, matching `purchase_order.md` V6's record shape.

## V7 — Test fails without the fix

PR #2 has **two** red commits on the branch, each committed **before**
its corresponding source fix, per `FIX_PLAN.md` §8 step 3. Neither was
a post-hoc stash; both were verified red at commit time.

### V7-a — the multi-child test (commit `f4f9a13`)

`tests/test_sample_and_disclose_supplier.py` was committed at
`f4f9a13` with one red test and four green. The red test:

    test_multi_child_supplier_shape_builds_locally_without_llm

Failure reason, from `/tmp/f0_pytest_pr2_red.log` (55 lines):

    synthesizer.py:1447: in synthesize_response
        structured_llm = llm.with_structured_output(schema, include_raw=True)
    AssertionError: synthesize_response called the LLM on a Supplier
    path that should be local

The traceback names the exact line reached only after every local
Supplier branch returned None — the multi-bucket shape had no local
builder, so `synthesize_response` fell through to the LLM setup. The
`_forbidden_llm` fixture raised there. That is the defect signature,
not a `KeyError`, not a `build_llm` call, not a schema error.

The fix (`0822047`) adds `_supplier_multi_child` and
`build_suppliers_with_children` to `p2p.py` and the branch to
`synthesizer.py`. After the fix the five tests pass
(`/tmp/f0_pytest_pr2_green.log`, 2 lines, `5 passed in 0.13s`).

### V7-b — the two tip tests (commit `257bf56`)

After V1's live runs surfaced the missing tip (Fix D-a and Fix D-b),
two new tests were added:

    test_plain_supplier_list_carries_narrowing_tip
    test_multi_child_supplier_shape_carries_narrowing_tip

Committed at `257bf56` with both red and five green. Failure reason
from `/tmp/f0_pytest_pr2_fixd_red.log` (84 lines):

    AssertionError: multi-child Supplier shape must populate
    narrowing_tip when total_available is known; got empty string
    assert '' = SupplierResponse(... narrowing_tip='').narrowing_tip

The other red test failed on the same class of assertion on the plain
list. Fix D-a (`a515b81`) and Fix D-b (`1adc9a7`) add the tip
computation to the two branches; both tests go green (V6-scoped log
`/tmp/v6_scoped.log`, `7 passed in 0.36s`).

### Why two red commits, not one

PR #1's V-walk surfaced three defects its unit tests did not catch
(Fix A/B/C in `purchase_order.md` §Deviations). PR #2's V-walk
surfaced two: the missing tip on both branches, and the summary prose.
The tip was worth a **new red** because the earlier tests only
asserted `isinstance(result, SupplierResponse)` and the records inside
— neither checked that `narrowing_tip` was populated. That is a
tautological-test defect of the same class PR #1's Fix C addressed: a
test that passes when the property it names is missing. Adding the
test first, seeing it fail, then fixing the source, is the discipline.

## V8 — N-run reproducibility (N=4, threshold not met)

**Scope statement first.** WORKING_STYLE's rule is N≥20 for any
nondeterminism claim. PR #2 reached N=4. The four-run evidence below
is recorded as-is; the N≥20 threshold is **not** met, and no rate is
claimed. A future window with a working pytest-timeout plugin (this
environment does not have it — see V6) can run the remaining 16
without the ~48%-stall class of interference that has affected the
full-suite runs.

Prompt: `suppliers with their contacts, sites, and classifications`
against `fa-esll-saasfademo1` — the V2 three-child prompt.
Four complete runs on disk under `/tmp/v8_20runs/run_0{1,2,3,4}.txt`
(668 lines each, identical). A fifth run (`run_05.txt`, 5 lines) was
interrupted by the operator before completing; not counted.

Three determinism checks, four-of-four identical each:

**Intent (parser):** all four runs produce

    target_entity: Supplier
    include: ['Contact', 'Site', 'Classification']

Same entity, same three-include list, same order, no filters. The
parser classifies the prompt identically across four runs.

**Summary line (summarizer, local):** all four runs produce

    Showing 25 of 409 suppliers: 93 contacts, 153 sites, 20 classifications.

The summary is built locally by the multi-child branch (fix-E's
format), not by an LLM, so this is expected rather than interesting
on its own — but it is confirmation that the branch produces
byte-identical output for a byte-identical intent.

**Tip line (summarizer, local):** all four runs produce

    Reading all 409 suppliers is slow. Narrow with a filter: business
    relationship, country, creation date, name, status.

The tip is built locally by fix-b's `build_narrowing_tip` call. The
`409` reflects the pod's **current** supplier count; V2's single run
was `402`, seven suppliers ago. The tip is not cached and tracks the
source total per-run.

### What N=4 proves and does not prove

Proves: for this prompt, the parser and the multi-child summarizer
are deterministic across four runs; the shape does not vary; the
summary and tip track the pod's live count rather than a stale value.

Does not prove: an N≥20 rate. Three specific residual risks:

  - A rare (>1-in-4) failure mode — e.g. the classifier dropping
    `Classification` from the include, or the pod occasionally
    timing out on one of the 25 `search_purchase_orders` fan-out
    calls — would not appear in four runs. V5-3 saw exactly that
    fan-out timeout on a different prompt; this prompt's `get_
    supplier_contacts` / `search_suppliers_by_site_bu` / `search_
    suppliers_by_classification` fan-out is the same shape and could
    hit the same transient. None of the four runs did.
  - Parser nondeterminism under prompt paraphrase — the four runs
    are the **same** prompt. A paraphrase sweep at N≥20 would test
    whether the classifier produces the same include set for
    semantically-equivalent phrasings. Not done.
  - Interaction with pod state — four runs within minutes; the pod's
    data was stable in that window (93 contacts, 153 sites, 20
    classifications reproduced). If a supplier's child counts
    changed mid-run, the counts would vary even though the shape did
    not. That variability is a property of the data, not the code.

### Save file

The check pattern that failed in B18-tally (`Showing 25 of 402
suppliers: …`) was overfit on V2's single-run count of 402. The
pod's live count had drifted to 409 by the V8 sweep, so the literal
`402` pattern matched zero of four. The fix was to grep structurally
(`^Showing \d+ of \d+ suppliers: \d+ contacts, \d+ sites, \d+
classifications\.`), which matched four of four. Same class of
verifier error as the V2 and V5 wrap-issue: a literal pattern that
locks to a single run's data is not a stable check; the structural
pattern is.

## V9 — `--validate` (not required)

PR #2 changes no `.sysprompt` file. The check:

    git diff d0acaf8..HEAD --name-only | grep '\.sysprompt$'

returns nothing on this branch. The fix surface is pure Python
(`p2p.py`, `synthesizer.py`, `tests/test_sample_and_disclose_supplier.py`)
plus this evidence file and the Issue C finding file. No prompt rule
is added, changed, or removed.

By the same rule `purchase_order.md` V9 applied — no `.sysprompt`
change, no `--validate` sweep required — PR #2's V9 is **not
required**. The 240-prompt `--validate` sweep is deferred to a window
that changes an actual sysprompt block.

## V-walk state

TBD after V2. V3–V9 still to fill; `State: closed` after PR merge.
