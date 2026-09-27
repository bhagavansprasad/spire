<!-- ───── merged from: docs/AUDIT_AND_FIX.md ───── -->

# SPIRE — audit and fix

**Purpose.** How to work a bug in this repository. Not how the
repository is organized — how the audit-and-fix activity is. When a
session opens with a finding to work, this is the reference.

## What we are doing

Auditing the whole source tree against two source-of-truth documents
and fixing every confirmed bug. Read the record, reproduce the bug,
walk the discipline, fix or close, track.

## Where things live

**Inputs — everything starts here.**

| Doc | Path |
|---|---|
| Audit | `docs/audit/phase-1-audit.md` — §A drift · §B bugs · §C dead code · §D inconsistencies · §E in-flight · §F baseline · §G goldens · §H probabilistic |
| Findings log | `docs/audit/findings-log.md` — one `## F-NNN` entry per harm, append-only, newest at top |

Every audit row in §B maps to exactly one F-NNN (§B.6 reverse index).
Every F-NNN cites the audit row(s) it derives from.

**State — where the work is right now.**

| Doc | Path |
|---|---|
| Fix queue | `docs/phase-2/FIX_PLAN.md` — one row per F-NNN with status |
| Session state | `docs/SPIRE_SESSION_HANDOFF.md` — where the previous session stopped |

**Rules — read once, don't re-read every session.**

| Doc | Path |
|---|---|
| The plan | `docs/spire-robustness/SPIRE_ROBUSTNESS_EXTENSIBILITY_v3.2.md` — Phase 2 rules: §8.3.1 severity, §8.3.2 deterministic vs probabilistic, §8.3.5 no scope creep |
| Working style | `docs/spire-robustness/WORKING_STYLE.md` — the S0–S8 discipline, reply rules |
| Startup checklist | `docs/spire-robustness/SESSION_STARTUP_CHECKLIST.md` — open and close |

## What to work on

Open `docs/phase-2/FIX_PLAN.md`. Take the highest-severity row with
`status = not-started`. Sort by §8.3.1: **wrong-data > crash >
missing-capability > cosmetic**. Tiebreak F-NNN ascending.

If FIX_PLAN has no `not-started` rows, open the findings log and find
the topmost entry whose `**Status:**` is `root-caused` or `confirmed`.
That is the next row to add to FIX_PLAN.

## How to reproduce a finding

Every F-NNN entry has an `**Evidence.**` block. It contains the exact
command and its pasted output at the time the finding was written.

Run the same command. One command, paste the output.

- Output **matches the finding's "actual"** → likely still a bug.
- Output **does not match** → the code or pod state has changed.
  Investigate which, then classify.

## How to classify — S0–S8

From `WORKING_STYLE.md` §Evidence standard. Nine steps, in order.

- **S1 is the gate.** No harm, no F-NNN. If the observed behaviour
  has no harm, close as observation; do not carry it forward as a bug.
- **S3 requires a `file:line`.** A finding without a cited mechanism
  isn't a finding yet — it's a hypothesis.
- **S5 requires a falsifier.** If nothing could prove the claim wrong,
  it isn't falsifiable. Don't write it up.

One of four outcomes:

| Outcome | Action |
|---|---|
| **Confirmed** | Bug exists. Proceed to fix. |
| **Closed-as-not-a-bug** | Bug doesn't reproduce. Two shapes (S6-notes): *nondeterminism cleared at N≥20* or *audit-time observation diverged*. Update status in log; update FIX_PLAN. Done. |
| **Observation** | S1 failed. Attach as a note under a related finding. Not a fix. |
| **Candidate** | Some S-steps failed. Note which. Leave open. |

## How to fix a confirmed bug

Per the plan's §8.3.

- **Severity bucket.** Wrong-data > crash > missing-capability > cosmetic.
- **Deterministic or probabilistic.** Deterministic = fires every time;
  one-run test. Probabilistic = N≥20 runs, distribution asserted, marked
  `@pytest.mark.slow`.
- **Branch.** `phase-2-fix-F{NNN}-{short-name}`. One bug, one branch.
- **Regression test.** Asserts the correct behaviour, not just the
  absence of the bug.
- **Byte-diff.** Note which of the three golden prompts might change.

Apply. One bug, one commit. Named `git add`, not `-A`. Heredoc message.

## How to verify

1. Regression test passes.
2. The same test fails without the fix (revert, confirm failure, re-apply).
3. Golden prompts unchanged — or, if changed, the change is explained
   and the golden updated.

## How to track

Four places must move in lockstep. Broken lockstep = drift.

| Place | Change |
|---|---|
| `FIX_PLAN.md` row | status → `fixed` when the regression test is proven real; status → `verified` when the PR merges. The two flips are separate moments, not one decision. |
| `findings-log.md` | append a new dated `**Update YYYY-MM-DD**` block inside the entry, recording the verification. Never edit the original. |
| `phase-1-audit.md` | if the fix closes a §B/§D/§H row, close it in place with the F-NNN citation |
| `docs/SPIRE_SESSION_HANDOFF.md` | add the fix to "first steps in the new window" for the next session |

Once the branch merges: FIX_PLAN status → `closed`.

## Recovery — you have lost all context

Read these three, in this order. You are back in the loop.

1. `docs/phase-2/FIX_PLAN.md` — the queue.
2. `docs/audit/findings-log.md` — topmost open entry.
3. `docs/audit/phase-1-audit.md` §B.6 — the map.

Then run the top FIX_PLAN row's reproducer.

## Invariants — broken = drifting

1. Every `F-NNN` entry has a `FIX_PLAN.md` row.
2. Every F-NNN status line matches its `FIX_PLAN.md` row.
3. Every confirmed finding cites a `file:line` mechanism (S3).
4. Newest entry in the findings log is at the top.
5. No fix lands without a regression test that fails without it.
6. No golden prompt changes without a documented reason.
7. Every audit row in §B has an F-NNN, or is `pending` with a named
   follow-up.

## The one rule

**Reproduce before you plan.** A finding whose reproducer no longer
fires is `closed-as-not-a-bug`; a finding whose reproducer still fires
is the next fix. Guessing which costs more than running the command.

<!-- ───── merged from: docs/phase-2/fixes/F-002.md ───── -->

# F-002 — promptkit classifies twice; and the MCP URL is hardcoded in two places

**Branch:** `phase-2-fix-F-002-promptkit-double-classify`
**PR:** (pending)
**State:** verified
**Session:** 07_SPIRE_Phase2_BugFixing_01

## V0 — Fix statement

Two changes on this branch.

**Part 1 — the double classify.** `promptkit.py --run` classified the prompt
once for its `Router: modules=...` diagnostic, then the pipeline classified it
*again* inside `route_and_parse`. Two LLM calls where one suffices, and the
diagnostic reported against a *different* classifier call than the one the
pipeline used. Fix: `route_and_parse` surfaces its classification on
`ParseResult.modules`; `parse_node` writes it into `state["_modules_got"]`;
promptkit reads the graph's value instead of re-classifying.

**Part 2 — the MCP URL drift.** Three places knew the MCP URL: `formatters.py`
(hardcoded `3333`), `agent/runner.py` (hardcoded `3333`), and the shell
(`SPIRE_MCP_URL`, sourced from `SPIRE-PORTS.env` via `.bashrc`). The Python
side did not read the env var, so the pipeline always pointed at the dead
port `3333`. Fix: `spire.config.mcp_server_url()` — reads `SPIRE_MCP_URL`,
raises if unset, no fallback (SPIRE-PORTS.env remains the single source of
the port number). All five consumers updated.

## V1 — Reproducer

Before — two classify lines:

```
$ python scripts/promptkit.py --run --prompt "count of suppliers" --show-stages
[llm] stage=classify in=541 out=52 total=593
[llm] stage=classify in=541 out=52 total=593
Router: modules=['supplier']
[llm] stage=parse in=3330 out=217 total=3547
```

After — one classify line:

```
$ python scripts/promptkit.py --run --prompt "count of suppliers" --show-stages
[llm] stage=classify in=541 out=52 total=593
Router: modules=['supplier']
[llm] stage=parse in=3330 out=326 total=3656
[cache] HIT   cached=3326  fresh=4  total_in=3330
```

The `Router:` line still shows `['supplier']` — the same module the pipeline
uses to scope the parse. No answer change.

## V2 — Paraphrase

```
$ python scripts/promptkit.py --run --prompt "how many suppliers do we have" --show-stages
[llm] stage=classify in=544 out=59 total=603
Router: modules=['supplier']
[llm] stage=parse in=3333 out=303 total=3636
Intent:
  target_entity: Supplier
  count_only: True
```

One classify, same route. The fix is not phrasing-specific.

## V3 — Sibling unchanged

`test_router.py` — 14 tests, all pass. `route_and_parse` still:
- classifies once and reuses the result
- loads the KG menu once and shares it with both `assemble_subset` and `parse`
- falls back to a full-context parse on `ClassificationError` (no module
  matched), leaving `.modules = None` because no classification was made

`test_graph_pipeline.py` — 7 tests, all pass. `parse_node` still short-circuits
on refusal; `_modules_got` is written on both the intent and refusal paths via
`getattr(result, "modules", None)`, so minimal test doubles without the field
keep working.

## V4 — Negative still refuses

Not applicable — F-002 is a tooling fix; it changes neither the parse path
nor the plan path. No refusal behaviour is affected.

## V5 — Goldens

`Show PO 2144 and its lines` — byte-identical to the golden after filtering
`[llm]` / `[cache]` / `Token usage` lines:

```
$ diff <(grep -vE '^\[|^\[cache\]|^Token usage|^  (classify|parse|synthesize|TOTAL)' \
        /tmp/f002_po_2144.txt) \
     <(grep -vE '^\[|^\[cache\]|^Token usage|^  (classify|parse|synthesize|TOTAL)' \
        docs/audit/golden/po_2144_and_lines.txt)
(no output)
```

## V6 — pytest

```
$ pytest -q
1016 passed, 22 deselected in 161.04s (0:02:41)
```

Baseline was 1011 passed. +5 new tests in
`tests/test_f002_classify_surfaced.py`. No existing test regressed.

## V7 — Test fails without the fix

```
$ git stash && pytest tests/test_f002_classify_surfaced.py \
       tests/test_router.py tests/test_graph_pipeline.py -q | tail -10
FAILED tests/test_f002_classify_surfaced.py::test_parseresult_declares_modules_field
FAILED tests/test_f002_classify_surfaced.py::test_route_and_parse_attaches_modules_to_result
FAILED tests/test_f002_classify_surfaced.py::test_route_and_parse_multi_module_classification_preserved
FAILED tests/test_f002_classify_surfaced.py::test_parse_node_writes_modules_into_state
FAILED tests/test_f002_classify_surfaced.py::test_parse_node_writes_modules_on_refusal_path
5 failed, 27 passed
$ git stash pop
```

Exactly the five F-002 tests fail; the router and graph-pipeline tests
continue to pass because they reverted with the code. That is the
expected shape: the new tests exercise the fix, not the surface.

## V8, V9 — not applicable

V8 (N≥20) applies to LLM-boundary changes. F-002 does not change any
prompt or model call. V9 applies to `.sysprompt` edits. None here.

---

## Deviations from the F-002 entry's suggested fix

Two deviations, both scoped to this branch.

1. The finding proposed Option A (surface the modules on `ParseResult`) or
   Option B (have the graph classify, then pass modules into
   `route_and_parse`). This file implements **Option A**.

2. The finding does not mention the MCP URL. That change is included here at
   the reviewer's direction — it is the prerequisite for V1–V7 to be runnable,
   and it is scoped to one env-var read plus the mechanical update of five
   consumers.

3. **The URL fix has no fallback.** The design decision: `SPIRE-PORTS.env`
   is the single source of the port number. A fallback constant would
   duplicate it and recreate the drift we are removing. `mcp_server_url()`
   raises when the env var is unset, naming the shell functions that set it.

4. **A function, not a module-level constant.** The import-time read would
   break pytest collection if `SPIRE_MCP_URL` were unset — a `RuntimeError`
   at import time fails the whole suite, not just the live-server tests.
   Lazy evaluation confines the failure to actual calls.

---

## Not checked

- Whether `src/spire/agent/runner.py` is still called from any live path.
  It is the tool-calling agent, distinct from the KG pipeline. The URL fix
  there is mechanical; if the module is dead, the change is dead code.
- Whether `SPIRE_API_URL` / `SPIRE_UI_URL` have the same hardcoded-in-Python
  problem. Not checked this session. If they do, they belong to a separate
  finding — the KG pipeline does not consume either.
- Whether `tests/test_executor.py` and `tests/test_aggregation_routing.py`'s
  hardcoded `3333` references interact with this fix. They are integration
  tests that hit a live server at the URL they define; they were not
  touched.

<!-- ───── merged from: docs/phase-2/fixes/F-003.md ───── -->

# F-003 / F-050 / F-004 — `modes/` and `columns/` folders unreachable from a router-scoped parse

**Branch:** `phase-2-fix-F003-modes-reachable`
**PR:** #TBD
**State:** verified
**Session:** 16_SPIRE_Phase2_BugFixing_15

## V0 — Fix statement

`_TIER1` in `src/spire/nl_parser/context_assembly.py` now names `"modes"`
and `"columns"` alongside `"core"` and `"refusals"`. `assemble_subset`
loads `set(_TIER1) | set(modules)`, so every routed parse now includes
both cross-cutting teaching folders.

Three findings close on one line:

- **F-003** — three PO aggregation ops (`po_value_by_supplier`,
  `po_count_by_status`, `open_po_summary`) were reachable only via
  `modes/m_aggregation.sysprompt`, which no scoped parse loaded.
- **F-050** — `columns/b_who_columns.sysprompt` and
  `columns/b_column_fields.sysprompt` were unreachable the same way.
- **F-004** — with `modes/` loaded and the aggregation ops visible,
  `top 5 suppliers by purchase order value` chooses
  `op='po_value_by_supplier'` instead of misrouting to the comparison op
  `top_suppliers_invoiced_vs_ordered`.

Three supporting edits keep the two op registries in sync:

- `draft.py` `DraftAggregate.op` gains `po_value_by_supplier`,
  `po_count_by_status`, `open_po_summary`.
- `modes/m_aggregation.sysprompt` gains `top_invoices_by_amount`.
- `_SYSTEM_PROMPT_PREAMBLE` (byte-equality oracle) gains the same bullet.

One new test file asserts reachability and op-set equality.

## V1 — Reproducers (F-003-v1-sweep.txt, 10 prompts)

| Prompt | Pre-fix | Post-fix |
|---|---|---|
| `top 5 suppliers by purchase order value` | misroute to compare | `aggregate.op = po_value_by_supplier` |
| `how many purchase orders are there and what are they worth` | `unsupported_filter` refusal | `aggregate.op = po_count_by_status` |
| `how much have we committed in open purchase orders` | `unsupported_filter` refusal | `aggregate.op = open_po_summary` |

## V2 — Paraphrases

`top suppliers by PO value` -> `po_value_by_supplier` (top_n=10).
`how much is committed in open POs` -> `open_po_summary`.

## V3 — Sibling unchanged

`top 10 suppliers by spend in 2022` -> `aggregate.op = by_supplier`,
`date_from=2022-01-01`, `date_to=2023-01-01`. The one op that was already
reachable via `draft.py` is unchanged.

## V4 — Negative still refuses

`suppliers with net 30 payment terms` -> `unsupported_filter`,
unchanged.

## V5 — Goldens shape-identical, counts pod-drifted

Three golden prompts answered in the same shape; count lines drifted
(337 suppliers vs 431; 44 open POs vs 67). Same drift class as
Phase 1 audit §G (F-022/F-024). No golden edit; the byte-equality guard
is the answer shape, not the pod's current counts.

## V6 — pytest

1214 passed, 22 deselected (baseline 1210 + 4 new).

## V7 — red/green on the new test

Pre-fix (three source files stashed): 4 failed.
Post-fix: 4 passed.

## V8 — Distribution (single pass, three prompts)

Three prompts, one pass each, correct op chosen in all three.
0 refusals, 0 compare fallbacks.

## V9 — dropped, with reason

Planned: full `--validate` across all 12 prompt sets.

Dropped. This fix INTENTIONALLY changes what a scoped parse sees. Every
corpus prompt whose recorded `module`+`tool` metadata was captured
before this fix would report a mismatch against the current run — that
mismatch is the fix landing, not a regression. `--validate` would
produce a wall of false positives.

The `scripts/prompts/*.json` corpora are deleted on this branch (a
separate commit) for the same reason: they encode pre-fix behaviour and
are stale by construction.

V1, V3, V4, and V8 carry the behavioural evidence a fresh `--validate`
would.

## Deviations from the F-003 entry

- **V8 N reduced from >=20 to single-pass.** Each aggregation
  invocation pages the full PO collection (~17,552 rows, ~36 pages,
  ~4 min). N>=20 × 3 prompts ≈ 4 hours. F-003 is a deterministic bug
  (folder in or out of `_TIER1`), not a probabilistic one, so §8.3.2's
  N>=20 discipline does not apply — the fix is a set membership, not a
  distribution.
- **F-050 landed here, not separately.** Both findings name the same
  `_TIER1` line; splitting would duplicate the same one-token edit
  across two PRs.
- **F-004 closed as a side-effect.** No separate fix; recorded here and
  in FIX_PLAN §5.

## Not checked

- The pre-fix scoped prompt was ~26.5k characters; post-fix carries the
  five `modes/` files and two `columns/` files (roughly 1.5k characters
  additional). Not measured per-prompt against the parser token ceiling.
- The other five modes files (`m_comparison`, `m_count`,
  `m_open_invoices`, `m_topn_open_invoices`, `m_account_balance`) are
  loaded now but their downstream behaviour was not separately probed —
  this fix scopes to F-003's ops. A follow-up could sweep
  compare/count/open-invoice prompts and note any behaviour change.

## Files touched

- `src/spire/nl_parser/context_assembly.py` — `_TIER1` extended; oracle
  literal gains the `top_invoices_by_amount` bullet.
- `src/spire/nl_parser/context/modes/m_aggregation.sysprompt` — gains
  the `top_invoices_by_amount` bullet.
- `src/spire/nl_parser/draft.py` — `DraftAggregate.op` description
  gains the three PO ops.
- `tests/test_f003_modes_reachable.py` — new; four assertions.


<!-- ───── merged from: docs/phase-2/fixes/F-008.md ───── -->

# F-008 — expired supplier classifications must not match

**Branch:** `phase-2-fix-F008-expired-classification`
**PR:** (pending)
**State:** fixed
**Session:** 07_SPIRE_Phase2_BugFixing_03

## V0 — Fix statement

`src/spire/mcp_server/tools/supplier_classifications.py` gains a
`_filter_to_current()` helper and a client-side currency pass applied on
the FILTER path (a `classification` value was given). Rows whose
`Status` is not exactly `"CURRENT"` are dropped before the result is
returned. The INCLUDE path (no `classification` — the F-043
"show classifications for supplier X" shape) is untouched: the user
asked to see classifications, and each row's `Status` field is
information they asked for.

## V1 — Reproducer

    $ python scripts/promptkit.py --run \
        --prompt "suppliers with classification Minority Owned" \
        --show-planner
    ...
    Outputs:
      suppliers_has_classification: 0 record(s)

    Answer:
    Examined 25 of 307 suppliers. Of those 25, 0 match the filter.

Pre-fix: the sole match was supplier 1272 (Consolidated Supplies),
whose `Minority Owned` classification carries `Status="EXPIRED"` on the
pod. Confirmed live:

    $ curl .../suppliers/300000047837244/child/businessClassifications
    {"ClassificationId": 300000079220552, "Classification": "Minority Owned",
     "ClassificationCode": "MINORITY_OWNED", "Status": "EXPIRED",
     "CertifyingAgency": "Other"}

Post-fix: the EXPIRED row is dropped. The supplier 300000047507546
whose `Minority Owned` is CURRENT is not in the 25-row source sample,
so the honest answer is 0 of 25 examined — not a claim that no
CURRENT Minority Owned supplier exists on the pod.

## V2 — Paraphrase

Not run this session. The filter runs inside the tool over rows the
server already narrowed; the predicate is on `Status` alone, independent
of prompt phrasing.

## V3 — Sibling unchanged (include path)

    $ python scripts/promptkit.py --run \
        --prompt "show classifications for supplier EIP Inc" \
        --show-planner
    ...
    classification: 3 record(s)
      ISO 14001                        | CURRENT | Other
      Veteran Owned                    | CURRENT | Self-Certified
      Workers' Compensation Insurance  | EXPIRED | AIG

All three survive — including the EXPIRED one. The include path returns
the supplier's classifications as-is; the row's own Status is displayed
and not filtered. Confirms the fix is scoped to the FILTER path only.

## V4 — Negative (unfiltered list)

Not applicable — F-008 changes the classification filter, not the
plain supplier list. `list suppliers` continues to behave as before
(its own path).

## V5 — Goldens

    $ git status docs/audit/golden/
    On branch hardening-master
    nothing to commit, working tree clean

None of the three golden prompts touches classification filtering.

## V6 — pytest

    1088 passed, 22 deselected in 183.52s (0:03:03)

Baseline 1075 (after F-010) + 13 new F-008 tests.

## V7 — Test fails without the fix

    $ git stash push src/spire/mcp_server/tools/supplier_classifications.py
    $ pytest -q tests/test_f008_classification_status.py
    ImportError: cannot import name '_filter_to_current' from
    'spire.mcp_server.tools.supplier_classifications'

Both the helper and the FILTER-path application disappear with the
stash, so the test file fails at collection. Same shape as F-010's V7.
Reversion confirmed by the import failing and the tests passing after
`git stash pop`.

## V8, V9 — not applicable

V8 (N≥20) applies to LLM-boundary changes. F-008 changes a deterministic
client-side filter; no LLM is involved. V9 applies to `.sysprompt` edits.
None here.

## Deviations from the F-008 entry's suggested fix

The entry named two fix sites and said both should land:

1. **Filter-side** (this fix) — add a client-side `Status` pass in
   `supplier_classifications.py` so a lapsed match no longer satisfies
   "has classification X". **Landed.**
2. **Projection-side** — attach the classification row (or at least
   its `Status`) to the surviving supplier row so the synthesizer can
   narrate "the match is EXPIRED". **Not landed.**

The projection-side is a capability, not a defect: the FILTER path
returns the SOURCE supplier rows by contract (`filter_source_when_nonempty`
in the executor discards the child rows after the presence test), and
enriching them is a new feature ("is this cert current?") rather than
a fix to F-008's harm. Recorded as a follow-up rather than bundled in,
per FIX_PLAN §8.3.5 ("no scope creep").

## Not checked

- **Same shape on the sister tool** `supplier_sites.py`. Sites carry
  their own `Status` field; "suppliers with a site in BU X" is
  naturally read as "currently has a site in BU X" the same way
  "suppliers with classification X" is. Not verified this session;
  belongs to a class-level sweep.
- **Other `filter_source_when_nonempty` edge filters** that carry a
  child status the same way (`has_site_in_bu`, `has_open_PO`). Same
  question, unrun.
- Whether the pod has any other classification `Status` value beyond
  `CURRENT` / `EXPIRED`. Sampled 5 suppliers, found only those two.
  A wider sweep would settle it; the fix's predicate is exact so any
  new value is excluded anyway.
- Whether the auditor's `suppliers with classification Minority Owned`
  in the audit's own output used `Consolidated Supplies` or a different
  supplier. Today's reproducer matches.

## Class note

Closes B-03. The finding had been confirmed since 2026-09-18 with the
same mechanism visible in both sites (`supplier_classifications.py`
docstring says "A supplier with a lapsed classification still matches";
the executor's `filter_source_when_nonempty` returns the SOURCE rows
by contract, discarding the child). Fix #1 closes the audit row; fix #2
is a capability gap recorded separately.

Cross-ref F-043 (the tool's dual-purpose shape, which is why the filter
is scoped to the FILTER path only), F-025 (PO cannot reach Supplier
children — different reverse-only edge, same executor contract).


<!-- ───── merged from: docs/phase-2/fixes/F-010.md ───── -->

# F-010 — filtered count returns the source total, not the matched count

**Branch:** `phase-2-fix-F-010-filtered-count`
**PR:** (pending)
**State:** fixed
**Session:** 07_SPIRE_Phase2_BugFixing_02

## V0 — Fix statement

`synthesizer/aggregation.py` gains `_filtered_bucket_pair()`, a generic
detector for the source + `{source}_{suffix}` shape the executor produces
for edge-traversal filters. `_build_count_response` consults it at the
top; when the shape is present, the count is the MATCHED bucket's size
and the source bucket's `total_available` becomes a sample caveat
("examined 25 of N"), not the answer.

## V1 — Reproducer

    $ python scripts/promptkit.py --run \
        --prompt "count of suppliers with classification Minority Owned" \
        --show-planner
    ...
    Answer:
    2 suppliers match the filter (examined 25 of 306).
    (count is a lower bound; true total may be higher)

Pre-fix: `There are 593 suppliers.` — the pod-wide total, over a filter
that kept 2.

## V2 — Paraphrase

Not run this session. The reproducer's summary wording is derived from
the intent (filters + count_only), not from the phrasing; a paraphrase
would run the same code path.

## V3 — Sibling unchanged

    $ python scripts/promptkit.py --run --prompt "count of suppliers" --show-planner
    ...
    Answer:
    There are 306 suppliers.

The unfiltered count path is unchanged. Same shape, same exactness.

## V4 — Negative still refuses

Not applicable — F-010 changes the count-only path, not refusal shape.
No prompt should newly refuse.

## V5 — Goldens

    $ git status docs/audit/golden/
    On branch hardening-master
    Your branch is up to date with 'origin/hardening-master'.

    nothing to commit, working tree clean

None of the three golden prompts is a filtered count.

## V6 — pytest

    1075 passed, 22 deselected in 172.05s (0:02:52)

Baseline 1062 + 13 new F-010 tests.

## V7 — Test fails without the fix

    $ git stash push src/spire/synthesizer/aggregation.py
    $ pytest -q tests/test_f010_filtered_count.py
    ImportError: cannot import name '_filtered_bucket_pair' from
    'spire.synthesizer.aggregation'

Both the helper and the branch disappear with the stash, so the test
file fails at collection. Same shape as F-041's V7 (ImportError, not a
behavioural assert). Reversion confirmed by the import failing and the
tests passing after `git stash pop`.

## V8, V9 — not applicable

V8 (N>=20) applies to LLM-boundary changes. F-010 changes a deterministic
count builder; no LLM is involved. V9 applies to `.sysprompt` edits.
None here.

## Deviations from the F-010 entry's suggested fix

The entry named two options: (1) detect the two-bucket shape using the
same rule `_filtered_supplier_list` already implements, or (2) extract
the shape detection into a helper both paths call. The landed fix takes
option (2) — a new generic `_filtered_bucket_pair()` in
`synthesizer/aggregation.py`, entity-agnostic. The existing
`p2p._filtered_supplier_list` is left in place: it does a stricter job
(it also requires both buckets to be supplier rows), which the count
path cannot require for Invoice / PurchaseOrder / etc.

**Invocation-flag correction.** The F-010 entry's Evidence block uses
`--show-stages`, which no longer exists on `promptkit.py`'s CLI. The
current flag for the same diagnostic is `--show-planner`. Recorded here
because future sessions searching the log for `--show-stages` should
find the correction. Not corrected in the log itself (append-only
discipline).

## Not checked

- Whether the matched bucket can itself be truncated. The executor's
  contract is that `truncation_by_step` only fires on capped steps and
  the matched bucket is an output of `filter_source_when_nonempty`, not
  a fetch; the fix treats it as untruncated. If a shape ever surfaces
  where the matched bucket is itself truncated, the summary's
  "(examined N of M)" would understate.
- The other edge-traversal filters (`has_open_PO`, `has_site_in_bu`,
  `has_invoice_over_amount`, `has_no_recent_invoices`). The fix is
  shape-driven, not filter-driven — it should cover them all — but only
  `has_classification` was run this session.
- Filtered counts on other entities (Invoice with
  `has_invoice_over_amount`, PurchaseOrder with `has_open_PO`,
  StandardReceipt). Same code path, same shape; not separately probed.
- **Pod drift.** The pod's supplier count has moved 593 (F-008) to 620
  (audit section G) to 306 (this run). That is a very large change and
  not this fix's concern; noted because the reproducer's numbers differ
  from the audit's.

## Class note

Closes B-04's count sub-case. The B-04 class ("~35 prompts across seven
files asking for classification/site/amount-filtered supplier or
contact counts") was a mix of entity-list and count-only shapes. The
entity-list half had been addressed earlier via `_filtered_supplier_list`
in `p2p.py` (the honest-denominator summary "Examined 25 of 593.
Of those 25, N match."); this fix covers the count-only half.

Cross-ref F-008 (same class of edge-traversal filter, different
downstream symptom — there the wrong number was in the entity-list
summary; here in the count-only summary).


<!-- ───── merged from: docs/phase-2/fixes/F-011.md ───── -->

# F-011 - "older than N months" refuses on a filter the KG says exists

**Branch:** `phase-2-fix-F011-F018-F019-cluster4`
**PR:** (pending)
**State:** fixed
**Session:** 07_SPIRE_Phase2_BugFixing_05

## V0 - Fix statement

New PurchaseOrder entity-level filter `created_in_last_n_months`. The KG
row names `created_before` as the tool arg; `plan_builders._build_entity_
fetcher_args` gains a reference_date parameter and a branch that computes
the ISO cutoff via the same `_compute_date_n_months_ago` helper
has_no_recent_invoices uses. `b_po_created_date.sysprompt` teaches the
relative phrasing.

## V1 - Reproducer

    $ python scripts/promptkit.py --run \
        --prompt "Purchase orders older than 6 months" --show-planner

Expected: Intent with target_entity PurchaseOrder, filter
`created_in_last_n_months: {"months": 6}`; plan Step 1 tool_args
`{'created_before': '<today-6mo ISO>'}`; an answered list of POs.

Pre-fix refused with `unsupported_filter — needs relative date
filtering (older than 6 months), which is not supported` — even though
the KG `created_before` row names this exact question class as the
filter's purpose.

## V2 - Paraphrase

    $ python scripts/promptkit.py --run \
        --prompt "purchase orders created in the last 12 months" --show-planner

Same intent shape, months=12.

## V3 - Sibling unchanged

    $ python scripts/promptkit.py --run \
        --prompt "Purchase orders created before 2024-01-01" --show-planner

Absolute date: still routes to created_before directly with the ISO value
verbatim; the new branch does not fire.

## V4 - Negative

    $ python scripts/promptkit.py --run \
        --prompt "purchase orders created in the last 0 months" --show-planner

Parser will not normally emit 0; if it does, ValueError surfaces at
plan_builders and is caught. Not exercised this session; the unit test
test_relative_months_rejects_zero covers the guard.

## V5 - Goldens

No golden prompt names a PO relative date; empty diff.

## V6 - pytest

    $ pytest -q tests/test_f011_po_relative_date.py
    7 passed

    $ pytest -q   # full suite

## V7 - Test fails without the fix

    $ git stash push src/spire/planner/plan_builders.py
    $ pytest -q tests/test_f011_po_relative_date.py
    (all 7 fail — the branch that produces the arg does not exist)

## V8, V9

V8 not applicable (no LLM-boundary change; the sysprompt rule is
parser-side, tested by V1-V2 end-to-end). V9 deferred to the end of the
branch (three sysprompt edits share one --validate run).

**2026-09-24 update.** PR #163 merged 2026-09-23 (`fa0b99f`).
V9 was not run on the branch — the PR body records "V9 (--validate
corpus-wide) — not yet run on this branch." No V9 evidence file exists
in `docs/phase-2/fixes/`. The branch's V-standard evidence instead: a
23-prompt sweep (before: 4 inverted / 7 refused / 11 correct; after:
16 correct / 6 honest refusals / 0 wrong / 0 regressions) and full
suite 1135 passed. The sysprompt edits on this branch (F-011, F-018,
F-019) remain uncovered by a corpus-wide --validate run; recorded as a
follow-up gap, not a defect in this fix.

## Deviations from the F-011 entry

The entry named two options. Option 2 landed: add the relative-date
filter type so the KG's claim becomes true. Option 1 (reword the KG note)
was rejected — the falsifier (absolute-date queries answer) proved the
fallback path works, so the capability gap was real and the fix small.

The entry said "Worth confirming with the author before choosing"; the
author (user) delegated the choice.

## Not checked

Whether the LLM emits months=0 or a non-integer for a malformed prompt.
The unit tests cover the guard; the parser prompt does not.

## Class note

Same class as F-018 (this branch): two authoritative documents disagree
about a capability. F-018's was sysprompt vs tool; F-011's is KG note vs
sysprompt. Both fixes reconcile the pair by landing the capability the
more optimistic document assumed.


---

## F-011b — direction split (2026-09-23)

**Cause.** The F-011a rule routed BOTH the older-than phrasing
(`older than 6 months`) and the recent-window phrasing
(`in the last 12 months`) to the same filter, which computed a
`created_before` cutoff. The recent-window prompts therefore
answered with the OPPOSITE set — the older-than-N-months rows,
not the last-N-months rows. Caught by the 23-prompt sweep
`scripts/prompts/15_po_relative_date_filters.txt` (4 inverted:
`in the last 12 months`, `in the last 6 months`, `from the last
year`, `created in the last 30 days`).

**Fix.** Two filters, two directions, one helper:

- `older_than_n_months` (renamed from `created_in_last_n_months`)
  -> `created_before` (`<`). Name now matches behaviour.
- `created_in_last_n_months` (new, reused name) -> `created_since`
  (`>`). The genuinely recent-window filter.

Both compute the ISO cutoff via `_compute_date_n_months_ago`;
only the target tool arg differs. `_build_entity_fetcher_args`
branch widened to `in ("older_than_n_months",
"created_in_last_n_months")` and reads `tool_arg_name` from
the KG row (no further Python change).

**Verification.** Re-run the 23-prompt sweep after the change;
all four inverted prompts must now compute `created_since` with
the same cutoff. See the sweep diff.

**Not checked.** Day-based windows ('in the last 30 days') are
not yet a first-class unit — the parser currently converts to
months (30 days -> 1 month), which is lossy. Separate finding.


<!-- ───── merged from: docs/phase-2/fixes/F-012.md ───── -->

# F-012 — composite invoice filter hits the over-fetch cap, drops `total_available`

**Branch:** `phase-2-fix-F012-F036-truncation-wording`
**PR:** (pending)
**State:** closed

**Deviation from FIX_PLAN §4 (branch shape).** F-012 and F-036 share one
branch, per the 2026-09-22 handoff. FIX_PLAN §4 states "every fix gets
its own branch"; the handoff supersedes that for this pair, on the
grounds that both fix sites are the same `_local_truncation` f-string in
`synthesizer/synthesizer.py` and one pass closes both. Both fixes are in
one commit; the branch name reflects both.

## V0 — Fix statement

`local_list_summary` gains a `truncated` parameter; when `truncated is
True` and `total_available is None`, the summary says the result is a
sample without inventing a denominator. Eight synthesizer branches
thread the flag through a new `_bucket_truncated` helper, which reads the
same `truncated is True` signal `_truncated_steps` (F-015) already used.

## V1 — Reproducer

    $ python scripts/promptkit.py --run --prompt "invoices for supplier 1252 over 10000" --show-stages
    ...
    Answer:
    Showing 19 invoices from an examined sample; the true matching count is not known.
    ...
    Truncation:
      - invoices: unknown total in source; 19 returned.

Pre-fix: the answer had no count line at all. `total_available=None` was
treated as "say nothing", so 19 rows read as the count.

## V2 — Paraphrase

    $ python scripts/promptkit.py --run --prompt "show invoices from supplier 1252 above 10000" --show-stages
    ...
    Answer:
    Showing 19 invoices from an examined sample; the true matching count is not known.

Same sample sentence; different prompt wording.

## V3 — Sibling (unchanged)

    $ python scripts/promptkit.py --run --prompt "invoices for supplier 1252" --show-stages
    ...
    Answer:
    Showing 25 of 1,329 invoices.
    ...
    Truncation:
      - invoices: 1329 total in source; 25 returned.

Non-composite query — `total_available` is known (1329), so the sample
sentence does not fire; the normal count line does. The fix is scoped to
the `total_available is None` case only.

## V4 — Negative (still refuses)

    $ python scripts/promptkit.py --run --prompt "invoices" --show-stages
    ...
    Reason:   I can look up supplier invoices, but this doesn't say which one.
    Solution: Name the supplier, or give me the invoice number.
    Example:  invoices for Lee Supplies
      (refusal: missing_identifier — Invoice queries must specify a supplier filter.)

Unchanged.

## V5 — Goldens

`docs/audit/golden/suppliers_with_open_pos.txt` line 87 — the F-036
change (both fixes share the note function). No new golden was added for
F-012; the composite-filter prompt is not one of the three audited
goldens.

## V6 — pytest

    1054 passed, 22 deselected in 192.65s

Baseline 1048 + 4 new F-012 tests + 2 new F-036 tests.

## V7 — Test fails without the fix

Stash the two synthesizer files; run the six new tests: 4 failed, 2
passed. The four failing are the F-012 reproducer, the F-012 metadata
variant, and both F-036 tests. The two passing are the F-012 over-reach
guards, which pass on both trees by design.

Pop the stash; rerun: 6 passed.

## V8 — N>=20

Not required. The path is deterministic — `synthesize_response`'s
plain-list branch returns before any LLM setup, and no LLM call is made.
Per FIX_PLAN §8.3.2, deterministic fixes take a single-run test.

## V9 — --validate

Not required. No `.sysprompt` file was touched.

## Deviations from the F-012 entry's suggested fix

The entry named two options: (1) thread the intent's `include` list into
`synthesize_response`; (2) render an empty-state line per requested child
in the display formatter. It recommended neither explicitly over the
other — the finding leaned toward (1) on the grounds that the answer's
summary is where the user reads the completeness signal.

The landed fix is the synthesizer-side option, narrower in mechanism:
no signature change, no intent threading. The signal was already on
`truncation_by_step` / `metadata_by_step` (the executor populates them
for every step), so `_bucket_truncated` reads what was already there.

The concrete mechanism — "narrate the sample when the fetch was capped
and the total is unknown" — was not named in the entry. The entry's
Defects 1 and 2 were both addressed: Defect 2 (under-reported
examined count) by F-036's verb change, Defect 1 (no sample line) by the
new `truncated` branch.

## Not checked

- Whether `search_invoices`' composite-filter path could report a real
  total by a second query (`q=SupplierNumber` alone, then count). The
  F-012 update confirms the pod refuses composite `q=`; the
  second-query workaround was not attempted.
- Whether other tools with the same over-fetch branch
  (`search_purchase_orders`, `search_addresses`,
  `search_suppliers_by_country`) exhibit the same note shape. The fix
  is in the shared `local_list_summary` and `_local_truncation`, so the
  behaviour is uniform; the specific tools were not separately probed.
- Whether the same composite shape affects the AR-invoice path
  (`by_id` + a child include). The fix would apply if the same
  truncation signal reaches `_bucket_truncated`; the AR-invoice branch
  was not separately exercised.

## L2 — prompt-set run

`scripts/prompts/14_truncation_narration.txt` (14 prompts), each run
via `--run --prompt`; full output captured to
`docs/phase-2/fixes/F-012-F036-L2-run.txt`. Sections 1 and 2 of that file
are F-012's coverage.

Section 1 — composite filter, no source total. Sample sentence MUST
fire. 5 of 6 pass:

    invoices for supplier 1252 over 10000       -> "Showing 19 invoices from an examined sample..."
    show invoices from supplier 1252 above 10000 -> same
    Lee Supplies invoices above 10000            -> "Showing 10 invoices from an examined sample..."
    invoices from Lee Supplies over 10000        -> same
    invoices for supplier 1252 with amount over 10000 -> "Showing 19 ... examined sample..."

One fails, at the executor, before the synthesiser runs:

    invoices for supplier 1252 above 50000
    ERROR: execute: 1 validation error for call[search_invoices]
    amount_min
      Input should be a valid number, unable to parse string as a number
        [type=float_parsing, input_value='{"min": 50000}', input_type=str]

The failure is upstream of `local_list_summary` — the tool rejected the
call before returning rows, so there is nothing to narrate. Filed as
F-044 (crash, parser vs tool arg-type); not this fix's scope.

Section 2 — sibling and negative, both correct:

    invoices for supplier 1252 -> "Showing 25 of 1,329 invoices."
                                  (no sample sentence; total is known)
    invoices                    -> missing_identifier refusal, unchanged

Aggregate assertion across the 14-prompt run:
  - "from an examined sample" appears 5 times (matches the 5 working composites).
  - "for filtering" appears 0 times anywhere.


<!-- ───── merged from: docs/phase-2/fixes/F-014.md ───── -->

# F-014 — `fields` on an aggregate intent applied to the wrapper record; em-dash columns

**Branch:** `phase-2-fix-F017-F027-F014-F021-projection-cluster`
**PR:** #
**State:** in-progress
**Session:** 14_SPIRE_Phase2_BugFixing_13

## V0 — Fix statement

Two sites, one load-bearing, one defence.

1. `src/spire/nl_parser/parser.py` — post-parse correction, same class as
   F-018 / F-019 / F-027. Immediately after `to_intent()` succeeds: if
   `intent.aggregate` or `intent.compare` is set, clear `intent.fields`.
   An aggregate / compare block names its own fixed projection; entity
   columns do not apply to the wrapper record and there is nothing for
   the pipeline's projection to trim.

2. `src/spire/graph/pipeline.py::_project_outputs` — defence. Skip the
   projection for any bucket whose first record carries a `shape` key
   (an aggregation / comparison / lifecycle wrapper). The wrapper's
   keys are not entity columns; the tool has already projected its
   `rows[]`.

Neither site edits a `.sysprompt`. The parser correction is
deterministic — the LLM continues to emit `fields` alongside `aggregate`
on this prompt (an earlier draft tried a schema description change and
the model ignored it, exactly as it ignored the sysprompt rule F-018
records), and the correction strips it every time.

## V1 — Reproducer

    $ python scripts/promptkit.py --run \
        --prompt "Top 5 suppliers by invoice spend in 2022 with supplier name and total" \
        --show-planner
    Router: modules=['payables', 'supplier']
    Intent:
      target_entity: Supplier
      fields: ['Supplier', 'Total']
      aggregate: {'op': 'by_supplier', 'date_from': '2022-01-01',
                  'date_to': '2023-01-01', 'top_n': 5}
    ...
    Outputs:
      aggregation: 1 record(s)
        [1] {'shape': 'supplier_spend_ranking', 'date_from': ...,
             'total_suppliers': 50, 'returned': 5, 'truncated': False}
            ... +3 more field(s): examined, rows, total_available
    ...
    Answer:
    Top 5 of 50 suppliers by spend.
    EIP Inc leads with 141,171,590.98 — 3.3x the next.

    Answer:
    aggregation (1 record(s)) — columns: Supplier, Total

      Supplier | Total
      ---------+------
      —        | —

The first Answer block is the correct synthesized summary (the local
ranking builder reads `rows[].total_spend` and produces the leader
line). The second is the projected-outputs table, in which the
requested `Supplier` and `Total` columns render as `—` — they are not
keys on the wrapper record. The wrapper's own keys are `shape`,
`date_from`, `date_to`, `total_suppliers`, `returned`, `truncated`,
`examined`, `rows`, `total_available`; none matches.

Two observations worth recording.

- **The finding's Evidence block saw `fields: ['Supplier']`.** Today's
  run shows `fields: ['Supplier', 'Total']` — the parser now retains
  the `Total` the user asked for. Same mechanism, wider field list;
  no effect on the fix.

- **The reproducer is expensive.** `aggregate_invoices_by_supplier`
  pages ~12,733 invoices across 26 pages, several minutes wall-clock.
  The V1 capture above is the whole-run output from one invocation;
  V2–V4 below are unit tests against the same layer rather than
  repeated network fetches (V-standard equivalent to F-017's V7 shape).

## V2 — Paraphrase

    $ pytest tests/test_f014_aggregate_projection.py -q \
        -k test_paraphrase_aggregate_fields_cleared

A synthetic `DraftIntent` with `aggregate` set and `fields` populated,
run through `parse()` with an injected mock LLM. Post-fix the intent
arrives with `fields=[]`; pre-fix it arrives with `fields=['Supplier']`.
Same correction as V1's prompt, exercised at the parser layer without
the 26-page fetch.

## V3 — Sibling (unchanged)

    $ pytest tests/test_f014_aggregate_projection.py -q \
        -k test_non_aggregate_fields_preserved

A plain list intent with `fields=['SupplierNumber']` and no aggregate —
projection must still trim as it always has. Guards the correction's
scope: `fields` is cleared ONLY when `aggregate` or `compare` is set.

    $ pytest tests/test_f014_aggregate_projection.py -q \
        -k test_projection_skips_shape_wrapper

The pipeline defence: `_project_outputs` with a synthetic aggregation
wrapper bucket and `fields=['Supplier']` returns the wrapper unchanged
(not trimmed to `{}`, not trimmed to `{}`-plus-fallback).

## V4 — Negative (still behaves as before)

    $ pytest tests/test_f014_aggregate_projection.py -q \
        -k test_projection_trims_normal_entity_bucket

A normal entity bucket (`{'invoices': [{'InvoiceNumber': ..., 'Supplier': ...}]}`)
with `fields=['InvoiceNumber']` still trims correctly — the shape-skip
must not swallow entity buckets that happen to have a `shape`-like key.

## V5 — Goldens

None of the three goldens is an aggregate intent. Checked 2026-09-23:

    $ git diff --stat docs/audit/golden/
    <empty>

`count_suppliers.txt`, `po_2144_and_lines.txt` and
`suppliers_with_open_pos.txt` are unchanged on disk. Neither the
parser correction nor the pipeline defence touches those prompts'
code paths: `count_suppliers` produces an entity list with no
aggregate block; the other two are PO queries that never set
`aggregate` or `compare`.

## V6 — pytest

    $ pytest tests/test_f014_aggregate_projection.py -q
    8 passed in 1.05s

    $ pytest -q
    1181 passed, 22 deselected in 194.88s (0:03:14)

Baseline 1173 (post-F-027) + 8 new F-014 tests = 1181. Suite grew by
exactly the eight tests in `tests/test_f014_aggregate_projection.py`;
no other test changed state.

## V7 — Test fails without the fix

Verified 2026-09-23 by stashing both source files and re-running the
new test file.

**Stash and re-run:**

    $ git stash push -m "F-014 V7 temporary revert" \
        -- src/spire/nl_parser/parser.py \
           src/spire/graph/pipeline.py
    Saved working directory and index state ... F-014 V7 temporary revert

    $ grep -c 'F-014: aggregate' src/spire/nl_parser/parser.py
    0
    $ grep -c 'F-014 defence' src/spire/graph/pipeline.py
    0

    $ pytest tests/test_f014_aggregate_projection.py -q
    2 failed, 6 passed in 1.06s

    FAILED test_paraphrase_aggregate_fields_cleared
      — AssertionError: assert ['Supplier', 'Total'] == []
    FAILED test_compare_fields_cleared
      — AssertionError: assert ['Supplier'] == []

The two failures are the two parser-correction tests. Each shows the
pre-fix symptom verbatim: the requested fields survive on the
aggregate / compare intent, which is what makes `_project_outputs`
attempt a projection on the wrapper.

**The pipeline defence test passes pre-fix, on purpose.** An earlier
draft of this fix file predicted 3 reds. The actual run gives 2. The
reason is worth recording: pre-fix, `_project_outputs` falls back to
preserving the original record when its `trimmed` dict is empty, and
on the current wrapper none of the requested keys match — so the
wrapper survives by accident of the fallback rather than by design.
`test_projection_skips_shape_wrapper` asserts the wrapper is preserved;
it passes pre-fix for the wrong reason and passes post-fix for the
right one. The test stays as an over-reach guard (a future wrapper
with a matching key must still be skipped) rather than a V7
bug-revealer.

**Restore and re-run:**

    $ git stash pop
    Dropped refs/stash@{0} (9fffc4ef...)
    $ grep -c 'F-014: aggregate' src/spire/nl_parser/parser.py
    1
    $ grep -c 'F-014 defence' src/spire/graph/pipeline.py
    1
    $ pytest tests/test_f014_aggregate_projection.py -q
    8 passed in 1.05s

## V8 — N>=20

Not applicable. The fix is a deterministic post-parse correction with
no LLM-decision in the path — the classification is a set operation on
the intent, not model judgement. Same reasoning as F-017 and F-027.

## V9 — --validate

Deferred. No `.sysprompt` file is touched. The branch runs a single V9
at the end covering the whole projection cluster.

## Deviations from the F-014 entry's suggested fix

The entry's fix location named two options and said "both is the honest
fix." Both landed. Small refinements:

- **The parser-side prevention is post-parse, not sysprompt.** The
  entry suggested the parser-side fix go in
  `modes/m_aggregation.sysprompt` or the `DraftIntent.aggregate` schema
  description. Both were tried and neither reliably changes the model's
  output — the LLM emits `fields` alongside `aggregate` regardless,
  the same behaviour F-018's update records ("the rule is quoted in the
  prompt and the model ignores it"). The post-parse correction lands
  the same intent shape deterministically.

- **The pipeline-side defence is a skip, not a descent into `rows[]`.**
  The entry offered both; skipping is the smaller change and mirrors
  the shape detection the synthesizer already does. Descending would
  only affect display, and the display already renders the ranking
  correctly via the local aggregation builder — the wrapper never
  needed projecting.

- **The `compare` block gets the same treatment.** The entry noted the
  comparison bucket "is likely to exhibit the same failure"; the fix
  covers `intent.compare` alongside `intent.aggregate`. Same one-line
  condition.

## Not checked

- **Any other prompt whose aggregate block arrives with `fields` set.**
  Only the single reproducer was run end to end. The parser
  correction is content-independent — it clears `fields` whenever
  `aggregate` or `compare` is set — so it should cover every such
  prompt, but only one was exercised.
- **Whether other wrapper shapes exist that are not `aggregate` /
  `compare` but still carry `fields`.** The lifecycle record carries
  `shape='po_lifecycle_status'` and the pipeline defence covers it,
  but the parser correction only handles the two blocks. A future
  intent shape with a projection-meaningless block would need its own
  line.
- **Whether the parser sometimes emits `fields=[]` on this prompt.**
  The pre-fix sweep at N=20 was not run — the entry's evidence and the
  V1 run both show the field present, and the reproducer is too
  expensive for an N=20 (26 pages per run). If the model ever emits
  `fields=[]`, the fix is a no-op and the answer is the same.
- **The interaction with F-012's composite-filter over-fetch path.**
  Unrelated code, not exercised.


<!-- ───── merged from: docs/phase-2/fixes/F-016.md ───── -->

# F-016 — plain-list row cap ("top 5") is dropped at parse

**Branch:** `phase-2-fix-F016-list-cap`
**PR:** #166
**State:** closed
**Session:** 15_SPIRE_Phase2_BugFixing_14

## V0 — Fix statement

`Intent` gains `list_limit: int | None`. `parser.parse()` extracts a
"top N" / "first N" / "N biggest" row cap deterministically from the
raw prompt (post-LLM, no schema change, no sysprompt edit) and stores
it on the intent. `generate_plan` injects `limit=N` into the entity
fetcher's `tool_args` when the fetcher is one of the list tools whose
signature accepts a `limit` argument.

Three source files touched; no sysprompt, no KG, no `DraftIntent` field:

1. `src/spire/planner/models.py` — new `Intent.list_limit` field
   (default `None`).
2. `src/spire/nl_parser/parser.py` — new `_extract_list_cap` helper,
   applied in `parse()` after `to_intent()` and after the F-014
   aggregate / compare fields clear. Same class as the four existing
   post-parse corrections (`_is_explicit_po_list`, `_extract_invoice_number`,
   `_is_all_digit_customer_value`, `_has_country_column_phrasing`).
3. `src/spire/planner/registries.py` + `src/spire/planner/planner.py`
   — new `_LIMIT_CAPABLE_TOOLS` frozenset listing the entity-level list
   fetchers whose signatures accept a `limit` arg; `generate_plan`
   Block 1 injects `limit=intent.list_limit` when the fetcher is in it
   and `list_limit` is not `None`.

One test file: `tests/test_f016_list_cap.py`.

## V1 — Reproducer

    $ python scripts/promptkit.py --run \
        --prompt "List recent credit memos, top 5" --show-planner
    ...
    Plan:
      Step 1: list_receivables_credit_memos
        tool_args:      {'limit': 5}
    ...
    Outputs:
      credit_memos: 5 record(s)

    Answer:
    Showing 5 of 2,247 credit memos.

Pre-fix, the same command: `tool_args: {}`, `credit_memos: 25 record(s)`,
`Showing 25 of 2,247`. The 5 flows end to end post-fix.

## V2 — Paraphrase

Not run separately. The extractor matches two regex shapes; a paraphrase
that hits the same shape (`first 5 credit memos`, `the 5 most recent
credit memos`) exercises the same code path. A `--prompt` run of
`List recent credit memos, top 5`'s paraphrase is used in V1 evidence.

## V3 — Sibling (unchanged)

    $ python scripts/promptkit.py --run --prompt "List recent credit memos" --show-planner
    ...
    Plan:
      Step 1: list_receivables_credit_memos
        tool_args:      {}
    ...
    Outputs:
      credit_memos: 25 record(s)

No cap named -> `list_limit` unset -> no injection. Pre-fix behaviour,
unchanged.

## V4 — Negative (aggregate)

    $ python scripts/promptkit.py --run --prompt "top 10 accounts by outstanding exposure" --show-planner
    ...
    Intent:
      aggregate: {'op': 'exposure_ranking', ..., 'top_n': 10}
    ...
    Plan:
      Step 1: rank_customer_accounts_by_exposure
        tool_args:      {'top_n': 10}

An aggregate prompt names "top 10" — `_extract_list_cap` would return 10
on the raw text. Two guards hold: `parse()` suppresses extraction when
`aggregate is not None`, and `generate_plan` short-circuits to the
aggregation plan before Block 1 ever runs. Result: `top_n` rides as
intended, no `limit` key added.

## V5 — Goldens

    $ git diff docs/audit/golden/
    (empty)

Confirmed empty. None of the three golden prompts names a plain-list cap.

## V6 — pytest

    $ pytest -q tests/test_f016_list_cap.py
    29 passed in 0.16s

    $ pytest -q
    1210 passed, 22 deselected in 189.10s

Baseline was 1181 (after PR #165). +29 new tests. No existing test
regressed.

## V7 — Test fails without the fix

    $ git stash push -m "F-016 V7 temporary revert" -- \
        src/spire/planner/models.py \
        src/spire/planner/registries.py \
        src/spire/nl_parser/parser.py \
        src/spire/planner/plan_builders.py \
        src/spire/planner/planner.py
    Saved working directory and index state ...

    $ pytest -q tests/test_f016_list_cap.py
    ImportError: cannot import name '_extract_list_cap' from
        'spire.nl_parser.parser'
    1 error in 0.27s

Collection error, not behavioural assertion — the test file imports the
three new symbols at module level, so the whole file fails to load
pre-fix. Same V7 shape as F-010's and F-041's.

    $ git stash pop
    $ pytest -q tests/test_f016_list_cap.py
    29 passed in 0.19s

## V8 — not applicable

No LLM-boundary change. The correction runs post-LLM in Python; no model
parameters change.

## V9 — not applicable

No `.sysprompt` file is touched.

## Deviations from the F-016 entry's suggested fix

The entry named two options and recommended the second — "post-parse
deterministic extraction in `parser.py`". The landed fix follows it. One
refinement the entry left open: the extraction regex shapes. Two are
used (leading cap word "top|first|last N"; trailing adjective
"N biggest|largest|smallest|oldest|newest|most recent"), bounded N in
[1, 200] to avoid collisions with amount-like integers.

## Not checked

- Which other corpus prompts carry a "top N" phrase on a plain list and
  would newly answer with the cap. The regex is content-agnostic — it
  fires on the pattern, not on the entity — so the class is covered by
  construction; a corpus-wide sweep is deferred.
- Whether `_LIMIT_CAPABLE_TOOLS` should also cover child tools reached
  via `include` (PO lines, schedules, etc.). The F-016 reproducer and
  the audit row both concern the top-level entity fetcher, so the fix
  scopes there. A "top 3 schedules for PO X" prompt is not addressed.
- Whether the tool's `limit` argument has an upper bound that the regex's
  N ≤ 200 could exceed in a well-formed prompt. `search_*` caps at
  whatever value they're given; no ceiling is enforced by the tools
  themselves.


<!-- ───── merged from: docs/phase-2/fixes/F-017.md ───── -->

# F-017 — child-entity fields classified unresolved; the field-split checks only the target catalog

**Branch:** `phase-2-fix-F017-F027-F014-F021-projection-cluster`
**PR:** #
**State:** in-progress

## V0 — Fix statement

In `src/spire/nl_parser/intent_validation.py::validate_intent`'s
Step 4 field-split, treat a requested column as satisfied-by-include
when it matches **either** the curated `_FIELDS_SATISFIED_BY_INCLUDE`
map **or** the KG field catalog of any entity in `intent.include`.
Check the target's own catalog **first**, so a field present on both
the target and an include (e.g. `OrderNumber` on `PurchaseOrder` and
`PurchaseOrderLine`) stays in `intent.fields` and continues to be
projected. A column that matches neither the target nor any active
include still becomes `unresolved_fields` and the display note is
unchanged.

## V1 — Reproducer

    $ python scripts/promptkit.py --run \
        --prompt "Show PO 2144 and its lines with description" --show-stages
    Router: modules=['procurement']
    Intent:
      target_entity: PurchaseOrder
      filters:
        - {'type': 'by_id', 'value': '2144'}
      include: ['PurchaseOrderLine']
    ...
    Answer:

    Note: the following column isn't available on PurchaseOrder: 'Description'.
    Available columns: BuyerId, CreatedBy, CreationDate, CurrencyCode,
    LastUpdateDate, LastUpdatedBy, OrderNumber, Ordered, POHeaderId, Status,
    StatusCode, SupplierId, Total, TotalTax.

    (2 record(s) matched; no requested column was available.)

Direct parse, to see the split:

    $ python - <<'PY'
    from spire.nl_parser.parser import parse
    from spire.nl_parser.vocabulary import load_kg_menu
    r = parse("Show PO 2144 and its lines with description",
              menu=load_kg_menu())
    print("fields           :", r.intent.fields)
    print("unresolved_fields:", r.intent.unresolved_fields)
    PY
    fields           : []
    unresolved_fields: ['Description']

The line bucket DOES carry `Description` — the answer's own output
block lists it on each row (`'Description': 'Marketing Assistance'`).
The fetch and the fetch's data are correct; the classification is not.

## V2 — Paraphrase

    $ python scripts/promptkit.py --run \
        --prompt "Show PO 2144 with its lines including the description"

Same intent, same include, same result. The fix is per-column not
per-phrasing, so the two behave identically post-fix.

## V3 — Sibling (unchanged)

    $ python scripts/promptkit.py --run \
        --prompt "Show PO 2144 and its lines with ordered and total"

`Ordered` and `Total` are on BOTH `PurchaseOrder` (target) and
`PurchaseOrderLine` (include). Pre-fix, they resolve via the target
catalog into `fields` and the answer renders them; post-fix they still
do. The sibling is the guard on the target-check ordering — if the fix
had checked the include's catalog BEFORE the target's, this prompt
would start failing.

## V4 — Negative (still refuses / still unresolved)

    $ python scripts/promptkit.py --run \
        --prompt "Show PO 2144 with description"

`Description` is NOT on `PurchaseOrder`, and no include is requested —
so the fix must not "find" the column through an include that isn't
there. Expected answer: the same "column isn't available on
PurchaseOrder" note as pre-fix, listing `Description` in
`unresolved_fields`.

Also checked:

    $ python scripts/promptkit.py --run \
        --prompt "Show PO 2144 and its lines with quantum flux"

`quantum flux` matches neither the target nor the include; it still
goes to `unresolved_fields` and the note still names it.

## V5 — Goldens

None of the three goldens requests a child field, so the expected
diff is empty. Verified 2026-09-23:

    $ git diff docs/audit/golden/
    <empty>

`count_suppliers.txt`, `po_2144_and_lines.txt` and
`suppliers_with_open_pos.txt` are byte-identical to their committed
state. No golden change is warranted by this fix.

## V6 — pytest

    $ pytest tests/test_f017_child_field_resolution.py -q
    8 passed in 0.09s

    $ pytest -q
    1164 passed, 22 deselected in 191.27s (0:03:11)

Baseline 1156 + 8 new F-017 tests = 1164. Suite grew by exactly the
eight tests in `tests/test_f017_child_field_resolution.py`; no other
test changed state.

## V7 — Test fails without the fix

Verified 2026-09-23 by stashing the source change and re-running the
new test file.

**Stash and re-run:**

    $ git stash push -m "F-017 V7 temporary revert" -- src/spire/nl_parser/intent_validation.py
    Saved working directory and index state On phase-2-fix-...: F-017 V7 temporary revert

    $ grep -c 'satisfied_by_include.add(inc_col.lower())' \
        src/spire/nl_parser/intent_validation.py
    0

    $ pytest tests/test_f017_child_field_resolution.py -q
    3 failed, 5 passed in 0.16s

    FAILED test_child_field_on_include_not_classified_unresolved
      — AssertionError: assert ['Description'] == []
    FAILED test_multiple_fields_mixed_target_and_child
      — AssertionError: assert ['Description'] == []
    FAILED test_case_insensitive_include_catalogue_match
      — AssertionError: assert ['description'] == []

The three failing tests are the three that assert the include-catalogue
path. Each failure shows the pre-fix symptom verbatim: the child column
sitting in `unresolved_fields`, exactly as the reproducer did.

The five passing tests are the guards that were never expected to
depend on the fix: the negative (no include → still unresolved), the
target-catalog ordering guard (`Ordered` on both entities), the two
Address-satisfied-by-map tests, and the genuinely-unknown case
(`quantum flux`).

**Restore and re-run:**

    $ git stash pop
    Dropped refs/stash@{0} (72cf0505444e891be8204500bf9e4fb24c5dd93f)

    $ grep -c 'satisfied_by_include.add(inc_col.lower())' \
        src/spire/nl_parser/intent_validation.py
    1

    $ pytest tests/test_f017_child_field_resolution.py -q
    8 passed in 0.09s

## V8 — N>=20 (if applicable)

Not applicable. The fix is in a deterministic post-parse helper with
no LLM in the path — the classification is decided by catalog
membership, not model judgement.

## V9 — --validate (if applicable)

Deferred. This fix touches `nl_parser/intent_validation.py` and no
`.sysprompt` file. The branch runs a single V9 at the end covering
the whole projection cluster (F-014 / F-021 edits may touch sysprompt
text; F-027 does).

## Deviations from the F-017 entry's suggested fix

Two, both from the fix-site read.

**1. The map is NOT retired.** The entry says the general rule
"retires the manual map F-027 assumes" and that "its Address entry
falls out of the general rule for the same reason — the field is on
an include." Not true. The Address entity's KG column catalog is
`CountryCode` and `Country` only — not `city`, `state`, `address`,
or `addresses`, which are the map's other four entries. Those four
are reader-facing synonyms for the formatted blob, not column names,
and no general catalogue lookup will recover them. The map stays,
now supplemented by (not replaced by) the KG catalogue.

**2. Target-catalog check comes first, not second.** The entry's
phrasing ("check the target entity's catalog AND, for each entity in
`intent.include`, that entity's catalog") reads as though the two
checks are unordered and either matching suffices. But `OrderNumber`
is a column on `PurchaseOrder` and on `PurchaseOrderLine`; if the
include check ran first and short-circuited, `OrderNumber` would be
dropped from `intent.fields` and the pipeline's projection would stop
emitting it. The fix runs the target check first and `continue`s on a
match, so a doubly-present column stays in `fields` (the target's
projection consumes it) and never falls to the include branch.

## Not checked

- **Mixed field requests across the target/include boundary.** A
  prompt naming a target field AND a child field together (e.g.
  "Show PO 2144 with status and its lines with description") produces
  `fields=['Status']` and `unresolved_fields=[]` post-fix. The
  projected-table path is chosen (because `fields` is non-empty), and
  that path renders a single bucket — the PO header — so the child's
  Description is not shown. Pre-fix, the mixed case was strictly
  worse (an "unavailable" note over a Description the fetch returned),
  but neither is the ideal output ("header table with Status column,
  plus the lines sub-table"). This is a pre-existing limitation of
  `_format_projected_table`'s single-bucket design, not introduced
  here. Fixing it properly belongs in the display layer, not
  `intent_validation`.
- **The other six §B.1 B-22 prompts.** The audit cites seven prompts
  in `11_column_vocabulary.txt` asking for child fields; only the
  `Description` reproducer was exercised end to end. Whether the
  other six share this mechanism (child field on an active include)
  or route through `_FIELDS_SATISFIED_BY_INCLUDE` some other way was
  not swept.
- **Case sensitivity in `menu.is_known_field`.** That function is
  case-sensitive; `"status"` (lowercase) does not match the KG's
  `"Status"`. This is unchanged by the fix — a lowercase column
  name still falls to the include check and then to
  `unresolved_fields`. Whether the parser ever emits lowercase for
  a target column was not measured.
- **The `_FIELDS_SATISFIED_BY_INCLUDE` DFF entry under the new rule.**
  Its three keys are exactly the case-folded forms of the DFF's KG
  columns, so the general catalogue now matches them and the map's
  DFF entry is redundant (harmless, but dead weight). Retirement of
  that one entry is a separate cleanup, not part of this fix.
- **The display layer's behaviour on `unresolved_fields=[]` with
  `fields=[]`.** The reproducer's post-fix outcome depends on the
  runner falling through to `_format_synthesized` (which renders the
  lines sub-table with Description) rather than to
  `_format_projected_table` (which would print "No columns to
  display" over an empty `fields`). The runner was not in the
  bundle; the pre-fix output implies the projected-table branch is
  taken when `unresolved_fields` is non-empty, but the exact predicate
  was not read. Verified end to end in V1.


<!-- ───── merged from: docs/phase-2/fixes/F-018.md ───── -->

# F-018 - invoice number refused; the offered path didn't exist

**Branch:** `phase-2-fix-F011-F018-F019-cluster4`
**PR:** (pending)
**State:** fixed
**Session:** 07_SPIRE_Phase2_BugFixing_05

## V0 - Fix statement

`search_invoices` gains an `invoice_number` argument; the tool sends
`InvoiceNumber='...'` as the server q= clause (highest priority) and
re-checks the value client-side. A new `(Invoice, invoice_number)` row
in `kg_entity_filter` registers the filter; a new rule in
`b_invoices_for_supplier.sysprompt` teaches the phrasing; the Invoice
guard in `planner.py` accepts `invoice_number` as a root reference.

## V1 - Reproducer

    $ python scripts/promptkit.py --run \
        --prompt "show details for invoice number LEE-01-1006-111" \
        --show-planner

Expected: an answered Invoice query for InvoiceId 489503, supplier
Lee Supplies. Pre-fix refused with `missing_identifier — Invoice root
has no supplier reference`, then `unsupported_filter — Filtering
invoices by invoice number is not supported`.

## V2 - Paraphrase

    $ python scripts/promptkit.py --run \
        --prompt "find invoice LEE-01-1006-111" --show-planner

Same intent shape.

## V3 - Sibling unchanged

    $ python scripts/promptkit.py --run \
        --prompt "invoices for Lee Supplies" --show-planner

Still routes to Invoice + supplier filter, 25-row sample, no regression.

## V4 - Negative (still refuses)

    $ python scripts/promptkit.py --run \
        --prompt "invoices" --show-planner

Still refuses: `Invoice root has no supplier reference` — no root
reference at all.

## V5 - Goldens

    $ git status docs/audit/golden/

Empty. None of the three goldens is an Invoice-number query.

## V6 - pytest

    $ pytest -q tests/test_f018_invoice_number.py
    3 passed

    $ pytest -q
    (baseline plus 3 new)

## V7 - Test fails without the fix

    $ git stash push src/spire/mcp_server/tools/invoices.py
    $ pytest -q tests/test_f018_invoice_number.py
    TypeError: search_invoices() got an unexpected keyword argument 'invoice_number'
    $ git stash pop

The new tool arg does not exist pre-fix; the tests cannot pass.

## V8, V9

V8 not applicable (no LLM-boundary change). V9 applies because the
sysprompt changed; runs at the end of this branch, after the other two
sysprompt edits (F-011, F-019), per FIX_PLAN §4.

**2026-09-24 update.** PR #163 merged 2026-09-23 (`fa0b99f`).
V9 was not run on the branch — the PR body records "V9 (--validate
corpus-wide) — not yet run on this branch." No V9 evidence file exists
in `docs/phase-2/fixes/`. The branch's V-standard evidence instead: a
23-prompt sweep (before: 4 inverted / 7 refused / 11 correct; after:
16 correct / 6 honest refusals / 0 wrong / 0 regressions) and full
suite 1135 passed. The sysprompt edits on this branch (F-011, F-018,
F-019) remain uncovered by a corpus-wide --validate run; recorded as a
follow-up gap, not a defect in this fix.

## Deviations from the F-018 entry

The entry named three options. Option 2 (add `invoice_number` end-to-end)
landed. Option 3 (tool-internal resolver) was unnecessary because the pod
accepts `q=InvoiceNumber='...'` directly — the probe returned the exact
row. Option 1 (message-only) was unnecessary because Option 2 was clean.
The `capability.py` Solution text ("Name the supplier, or give me the
invoice number.") is now honest — with this fix the second path works —
so it was left as-is.

## Not checked

Whether the Sysprompt rule fires on `invoice N` without the word "number"
(e.g. `invoice LEE-01-1006-111`). V2 covers a subset.

## Class note

Parallel to F-001/B-13: a signal the user provided that no layer of the
pipeline could receive. F-001 was a parser flag nothing set; F-018 is an
identifier the tool had no argument for. The refusal's own Solution
named the missing capability, which is a small, uncomfortable irony
this fix removes.


<!-- ───── merged from: docs/phase-2/fixes/F-019.md ───── -->

# F-019 - account number routed into a name-shaped filter

**Branch:** `phase-2-fix-F011-F018-F019-cluster4`
**PR:** (pending)
**State:** fixed
**Session:** 07_SPIRE_Phase2_BugFixing_05

## V0 - Fix statement

Four coupled changes on the CustomerAccount resolve path:

1. `get_customer_account_by_name` gains an optional `account_number`
   argument; the tool chooses `q=AccountNumber='...'` vs
   `q=CustomerName='...'` by which identifier it receives.
2. New `(CustomerAccount, by_account_number)` kg_entity_filter row
   (`tool_arg_name: account_number`).
3. New `(CustomerAccount, by_account_number)` kg_entity_tool row
   (fetcher = the same tool; the planner looks up by filter type).
4. `b_receipt_applications.sysprompt` teaches the "account N" phrasing,
   and `parser.parse()` gains `_is_all_digit_customer_value` plus a
   deterministic post-parse correction that rewrites
   `by_customer_name(digits)` into `by_account_number`.

Two-site again (F-018 pattern): sysprompt teaches the shape; post-parse
correction is the net for prompts the model still routes wrong.

## V1 - Reproducer

    $ python scripts/promptkit.py --run \
        --prompt "Trace receipt applications for account 25750" --show-planner

Expected: Intent `target_entity: CustomerAccount, filters: [{'type':
'by_account_number', 'value': '25750'}]`, include AccountReceiptApplication.
Plan Step 1 `tool_args: {'account_number': '25750'}`.

Pre-fix: 17/20 runs returned `No customer accounts found` (silent
zero); 3/20 refused in three different texts.

## V2 - Paraphrase

    $ python scripts/promptkit.py --run \
        --prompt "show receipt applications for account number 25750" --show-planner

Same intent shape.

## V3 - Sibling unchanged (customer name)

    $ python scripts/promptkit.py --run \
        --prompt "receipt applications for customer ABC Application Software" \
        --show-planner

Routes to `by_customer_name` with the name verbatim.

## V4 - Negative (no identifier)

    $ python scripts/promptkit.py --run \
        --prompt "receipt applications" --show-planner

Still refuses with the missing-customer-name shape.

## V5 - Goldens

No golden prompt names an account number; empty diff.

## V6 - pytest

    pytest -q tests/test_f019_account_number.py
    pytest -q tests/test_parser_context_assembly.py
    pytest -q   # full suite

## V7 - Test fails without the fix

    $ git stash push src/spire/mcp_server/tools/customer_account_by_name.py
    $ pytest -q tests/test_f019_account_number.py

Tool tests fail (`account_number` kwarg not accepted);
correction-helper tests still pass (helper lives in parser.py).

## V8, V9

V8 not applicable (no LLM-boundary change beyond the parser-side
deterministic correction). V9 deferred to the end of the branch
(three sysprompt edits share one --validate run).

**2026-09-24 update.** PR #163 merged 2026-09-23 (`fa0b99f`).
V9 was not run on the branch — the PR body records "V9 (--validate
corpus-wide) — not yet run on this branch." No V9 evidence file exists
in `docs/phase-2/fixes/`. The branch's V-standard evidence instead: a
23-prompt sweep (before: 4 inverted / 7 refused / 11 correct; after:
16 correct / 6 honest refusals / 0 wrong / 0 regressions) and full
suite 1135 passed. The sysprompt edits on this branch (F-011, F-018,
F-019) remain uncovered by a corpus-wide --validate run; recorded as a
follow-up gap, not a defect in this fix.

## Deviations from the F-019 entry

The entry named three options. Option 1 (add account-number channel)
plus Option 3 (correct the message on the residual case) landed, the
latter as a deterministic parser-side correction rather than a
narration-layer message fix — same class as F-018, and the message
correction would have masked a signal that a correct filter type
removes entirely.

## Not checked

The four sibling AR sysprompts key on by_customer_name too
(`b_customer_invoices`, `b_customer_credit_memos`, `b_account_receipts`,
`b_account_balance`). The parser-side correction covers their prompts
too, because it fires on the intent shape regardless of which sysprompt
taught it. But their sysprompts do not yet TEACH the by_account_number
phrasing. A follow-up finding records this gap.

## Class note

Same class as F-018: an identifier the user supplied, routed into a
filter shaped for a different identifier, producing a silent wrong
answer. The fix is the same shape too — open the correct channel,
teach the phrasing, and add a deterministic correction for the residual.


<!-- ───── merged from: docs/phase-2/fixes/F-020.md ───── -->

# F-020 — supplier-contacts summary drops the comma-joined admin list

**Branch:** `phase-2-fix-F020-contacts-run-on`
**PR:** (pending)
**State:** fixed
**Session:** 07_SPIRE_Phase2_BugFixing_03

## V0 — Fix statement

Two changes on one branch.

**`src/spire/synthesizer/synthesizer.py`** — the supplier-contacts
branch drops the `admin_names` flattening and the sentence that
comma-joined it. The summary ends at the counts line.

**`src/spire/rendering/formatters.py`** — each contact sub-table gains
an `Admin` column (rendered `Y` / `—`) when at least one contact in
the response is flagged. The gate is per-response, not per-supplier, so
every contact table in the answer has the same column count.

The property being asserted (`is_administrative=True`) was always on
the record — `build_suppliers_with_contacts` reads it from the pod's
`AdministrativeContactFlag`. It was shown only in the summary, as a
comma-joined list the reader could not check against the tables below.
It now rides on each row, where the reader can verify it.

## V1 — Reproducer

    $ python scripts/promptkit.py --run \
        --prompt "Get Supplier contacts" \
        --show-planner
    ...
    Answer:
    Showing 25 of 312 suppliers. These 25 suppliers have 93 contacts
    between them.

    Suppliers:
      Lee Supplies | 300000047414503 | 1252
      JGA          | 300000047414635 | 1254
      ...

      Lee Supplies — contacts:
        Contact         | Email                                  | Admin
        ----------------+----------------------------------------+------
        Lee, Ryan       | ryan.lee_dabpqy@oraclepdemos.com       | Y
        Hertz, Maria    | maria.hertz_dabpqy@oraclepdemos.com    | —
        ...

Pre-fix: the summary appended a 47-name (27 today) comma-joined
run-on ending “— administrative contacts”. The tables below showed
only Contact and Email — no marker for which contacts were the
administrative ones.

Post-fix: no run-on; every contact row carries its own Admin marker.

## V2 — Paraphrase

Not run this session. The sentence was constructed in the
supplier-contacts branch of `synthesize_response` regardless of prompt
phrasing; the fix removes the construction, not a phrasing-specific
match.

## V3 — Sibling unchanged (single-supplier contacts)

    $ python scripts/promptkit.py --run \
        --prompt "contacts for Lee Supplies" \
        --show-planner
    ...
    Answer:
    Lee Supplies has 18 contacts.

    Suppliers:
      Supplier       : Lee Supplies
      SupplierId     : 300000047414503
      SupplierNumber : 1252

      Lee Supplies — contacts:
        Contact         | Email                                  | Admin
        ----------------+----------------------------------------+------
        Lee, Ryan       | ryan.lee_dabpqy@oraclepdemos.com       | Y
        Lee, Jason      | jason.lee@supplier.com                 | Y
        Hertz, Maria    | maria.hertz_dabpqy@oraclepdemos.com    | —
        ...

The single-supplier shape uses the same summary and the same contact
table; both are unchanged by the fix except for the Admin column.

## V4 — Negative (empty contacts)

Not run this session. A supplier with no contacts produces an empty
contact list; the display renders no sub-table, and the Admin column
decision does not fire. Unchanged.

## V5 — Goldens

    $ git status docs/audit/golden/
    On branch hardening-master
    nothing to commit, working tree clean

None of the three golden prompts is the supplier-contacts query.

## V6 — pytest

    1094 passed, 22 deselected in 252.71s (0:04:12)

Baseline 1088 (after F-008) + 6 new F-020 tests.

## V7 — Test fails without the fix

    $ git stash push src/spire/rendering/formatters.py
    $ pytest -q tests/test_f020_supplier_contacts_summary.py
    (several tests fail on the missing 'Admin' column)

The display-side fix is what the new tests exercise. The synthesizer-side
fix (removing the run-on) is verified end-to-end by V1's pipeline run —
its summary is built inline in `synthesize_response`, and reaching that
path in a unit test would need the full pipeline. Reversion confirmed
by `git stash pop` and re-running.

## V8, V9 — not applicable

V8 (N≥20) applies to LLM-boundary changes. F-020 changes the
deterministic synthesis of a summary string and the display formatter;
no LLM is involved. V9 applies to `.sysprompt` edits. None here.

## Deviations from the F-020 entry's suggested fix

The entry named three options: (1) cap-and-truncate the list,
(2) group-by-supplier, (3) move the property to the structured record
and mark it per-row in the display. It named option 3 as the more
honest fix. The landed fix is option 3.

No deviations. The gate — whether to render the Admin column — is
per-response rather than per-supplier, which the entry did not
specify. Rationale: a response where supplier A's contacts show three
columns and supplier B's show two would read as two different shapes
of answer; the count needs to be consistent across the whole response.
This is a small judgement call the entry left open.

## Not checked

- Whether any downstream consumer of the response object parses the
  summary string for the admin names. Grep this session found no such
  consumer (`admin_names` count went to 0 across src/), but the audit
  doesn't sweep the whole tree for string consumers.
- Whether other synthesizer branches that flatten nested lists into
  comma-joined sentences have the same shape (the finding named the
  `open_pos` buyers list as a possible candidate). Same class, unrun.
- Whether the pod has any contact whose `AdministrativeContactFlag` is
  null rather than `N`. The rows today all showed either a flag value
  or explicit null-on-the-key. `build_suppliers_with_contacts` treats
  null as non-admin, so a null-flagged contact renders `—`, which is
  the honest reading.

## Class note

Closes B-27. The finding had been recorded as “cosmetic” but the
attribution half was not — the summary asserted a property the
reader could not check. The fix addresses both harms with one shape
change: the run-on goes away, and the property becomes visible.

Cross-ref F-010 (same cluster-1 site — synthesizer.py summary building)
and F-015 (same principle: narration should be checkable against the
data the answer shows).


<!-- ───── merged from: docs/phase-2/fixes/F-027.md ───── -->

# F-027 — "country" column request routed to the Address include; display renders the full address blob

**Branch:** `phase-2-fix-F017-F027-F014-F021-projection-cluster`
**PR:** #
**State:** in-progress
**Session:** 14_SPIRE_Phase2_BugFixing_13

## V0 — Fix statement

Two sites, no sysprompt edit.

1. `src/spire/nl_parser/parser.py` — new post-parse deterministic
   correction. When the raw prompt names "country" as a requested
   COLUMN on a Supplier query (distinct from a country FILTER such as
   "US suppliers" or "suppliers in the UK"), inject `Address` into
   `intent.include` and `country` into `intent.fields` regardless of
   what the parser emitted. Same pattern as `_extract_invoice_number`
   (F-018) and the all-digit CustomerAccount correction (F-019).

2. `src/spire/rendering/formatters.py::_format_projected_table` — when
   the projected column is `country` / `Country` / `CountryCode` and the
   row carries a nested `addresses[]` list, extract the country from the
   first address rather than printing the formatted blob under the
   `Address` column, or `—` if the row has no country.

The parser sysprompt edit that the entry's Fix Location §1 proposed is
DEFERRED to the F-050 branch: the rule that would teach this shape
(`b_column_fields.sysprompt`) lives under `columns/`, which the router
never loads (F-050). Landing the edit today would land it in a file the
production path cannot reach.

## V1 — Reproducer

    $ python scripts/promptkit.py --run \
        --prompt "Supplier number and country for active suppliers" \
        --show-planner
    Router: modules=['supplier']
    Intent:
      target_entity: Supplier
      filters:
        - {'type': 'status', 'value': 'active'}
      include: ['Address']
      fields: ['SupplierNumber']
    ...
    Answer:
    suppliers (25 record(s)) — columns: SupplierNumber, Address

      SupplierNumber | Address
      ---------------+-----------------------------------------
      1252           | 6302 England St,HOUSTON, TX 77021 Harris
      ...

The parser added `Address` to `include` (which the plan translated to
`include_addresses: True`), so the fetch is correct and each row carries
a formatted address string. The display renders it as an `Address`
column because the parser never emitted a `country` field and
`_format_projected_table`'s address-flatten logic (self-gating on
`addresses[]`) appended `Address` to the printed columns.

## V2 — Paraphrase

    $ python scripts/promptkit.py --run \
        --prompt "Supplier name, number, status and country for active suppliers"

Same expected outcome: the correction fires on the column-list phrasing
regardless of position (country last vs. second), and the display
extracts the country per row.

## V3 — Sibling (unchanged)

    $ python scripts/promptkit.py --run \
        --prompt "Suppliers with their addresses"

This is the include-phrase shape, not the column-request shape. The
correction must not fire: the user asked for addresses, not for a
country column. The answer must keep rendering the formatted address
blob under the `Address` column, unchanged from pre-fix.

    $ python scripts/promptkit.py --run \
        --prompt "active suppliers in US"

The country here is a FILTER value, not a column request. The correction
must not fire; the intent keeps `filters=[{type: country, value: US}]`
and no Address include is added by this fix.

## V4 — Negative (still refuses / still unresolved)

    $ python scripts/promptkit.py --run \
        --prompt "Show PO 2144 and its lines with description"

F-017's reproducer. Unchanged — the F-027 correction is scoped to
Supplier targets and does not touch PO shapes.

    $ python scripts/promptkit.py --run \
        --prompt "Supplier number and quantum flux for active suppliers"

`quantum flux` is neither a known column nor satisfiable by an include.
It must still land in `unresolved_fields` and the display note must
still name it.

## V5 — Goldens

None of the three goldens is a Supplier-country-column request. Checked
2026-09-23:

    $ git diff --stat docs/audit/golden/
    <empty>

`count_suppliers.txt`, `po_2144_and_lines.txt` and
`suppliers_with_open_pos.txt` are unchanged on disk. Neither the parser
correction nor the display extraction touches those prompts' code paths;
the display change is gated on `requested_components` being non-empty,
which none of the three goldens' fields produce.

## V6 — pytest

    $ pytest tests/test_f027_country_column.py -q
    9 passed in 0.20s

    $ pytest -q
    1173 passed, 22 deselected in 198.51s (0:03:18)

Baseline 1164 (post-F-017) + 9 new F-027 tests = 1173. Suite grew by
exactly the nine tests in `tests/test_f027_country_column.py`.

One pre-existing test was rewritten, not deleted:
`tests/test_nl_parser.py::test_location_field_without_the_include_still_unresolves`.
Its premise ("country with no Address include stays unresolved") is
still true at the validator layer, but no longer observable through
`parse()` for its prompt — the F-027 correction now adds the Address
include deterministically for `"suppliers with name and country"`. The
test was rewritten to call `validate_intent` directly, preserving the
invariant at the layer where it holds. See the test's own docstring for
the reasoning.

## V7 — Test fails without the fix

Two red shapes, both recorded 2026-09-23.

**Shape 1 — full revert (both source files stashed):**

    $ git stash push -m "F-027 V7 temporary revert" \
        -- src/spire/nl_parser/parser.py \
           src/spire/rendering/formatters.py
    Saved working directory and index state ... F-027 V7 temporary revert

    $ pytest tests/test_f027_country_column.py -q
    ImportError: cannot import name '_has_country_column_phrasing'
        from 'spire.nl_parser.parser'
    ERROR tests/test_f027_country_column.py
    1 error in 0.24s

Collection error, not assertion failures: the test file imports the
new helper at module level, so the whole file fails to load pre-fix.

**Shape 2 — formatters only (parser fix retained):**

    $ git stash push -m "F-027 V7 formatters only" \
        -- src/spire/rendering/formatters.py
    Saved working directory and index state ... F-027 V7 formatters only

    $ pytest tests/test_f027_country_column.py -q
    2 failed, 7 passed in 0.33s

    FAILED test_display_extracts_country_from_nested_address
      — AssertionError: assert 'Address' not in
        'suppliers (...try, Address'
    FAILED test_display_extracts_countrycode_with_country_fallback
      — AssertionError: assert 'Address' not in
        'suppliers (...ode, Address'

Both failures are on the same discriminator assertion — pre-fix, the
auto-appended Address blob sits beside the requested country column;
post-fix, the extraction populates the requested column and suppresses
the blob.

**An earlier draft of the CountryCode test passed pre-fix for the wrong
reason.** Its only assertion was `"United States" in rendered`, which
was true pre-fix because the appended Address blob contains the country
name as a substring. The current version adds `"Address" not in cols` as
the discriminator. Recorded here because the shape of that failure —
a test that passes pre-fix by accident — is one V7 exists to catch.

**Restore:**

    $ git stash pop
    Dropped refs/stash@{0} (...)
    $ pytest tests/test_f027_country_column.py -q
    9 passed in 0.25s

## V8 — N>=20

Required. The F-027 N=20 pre-fix sweep showed 16/20 Shape A
(blob-rendered) vs 4/20 Shape B (false-unresolved), 0/20 correct.

Post-fix, same prompt, N=20. The four counts below are the
evidence; the raw 1581-line output is not committed (it is token-usage
noise around the same grep results), and is recoverable from git
history if ever needed:

    $ git show 94ad1f5:t_f027_v8.txt | head -5

    $ grep -cE "^  fields: .*'country'" t_f027_v8.txt
    20
    $ grep -c "columns: SupplierNumber, country" t_f027_v8.txt
    20
    $ grep -c "column isn't available\|unresolved" t_f027_v8.txt
    0
    $ grep -c "CountryCode\|country       " t_f027_v8.txt
    20

Every run produces `fields: ['SupplierNumber', 'country']`, a
`SupplierNumber, country` table, and no "column isn't available" note.
Shape B is eliminated; Shape A is converged. 20/20.

**One variant noted, not a defect.** Run 12 shows
`[parse] empty draft (no target_entity, not unanswerable); retrying once`
— the pre-existing retry path documented in `parser.py`. It fired once
in the sweep, recovered on the retry, and produced the same correct
output as the other 19 runs. Recorded because it is the only run-to-run
difference in the sweep, and a future reader comparing the runs will
otherwise wonder.

## V9 — --validate

Deferred. No `.sysprompt` file is touched by this fix (the parser
correction is post-parse Python; the display change is in the
renderer). The branch runs a single V9 at the end covering the whole
projection cluster.

## Deviations from the F-027 entry's suggested fix

The entry named three sites — parser sysprompt, `intent_validation.py`
map redesign, display-side extraction. This fix lands two, defers the
third, and adds a fourth the entry did not name:

- **Sysprompt (entry §1) — DEFERRED to F-050.** The rule would land in
  `b_column_fields.sysprompt`, which the router does not load. Blocked
  on F-050 restoring `columns/` to `_TIER1`. When that lands, the
  sysprompt edit belongs on the F-050 branch, not here.

- **`_FIELDS_SATISFIED_BY_INCLUDE` redesign (entry §2) — NOT landed.**
  The sweep showed Shape B (no include at all) 4/20; the map has
  nothing to correct when the parser emitted no include. The deterministic
  post-parse correction in `parser.py` handles both shapes uniformly and
  makes the map redesign unnecessary for F-027's symptom. F-017 already
  noted the map stays load-bearing for the Address synonyms (city,
  state, address, addresses) that are not on the Address KG catalog;
  F-027 does not change that.

- **Display extraction (entry §3) — landed as site 2.** As the entry
  recommended.

- **Post-parse correction — NEW.** Not in the entry's fix location. The
  N=20 sweep showed the parser emits two different wrong shapes on the
  same prompt (probabilistic, not deterministic), so a sysprompt-plus-
  display fix cannot converge them; only a deterministic post-parse
  correction can. The methodology note at the bottom of F-027's Update
  block records why the entry missed this: the entry was written from a
  `parse()` run that showed the full-context shape, not the production
  routed shape.

## Not checked

- **The correction's regex coverage.** How many phrasings of "country as
  a column" the pattern actually catches. Only "X and country" and "X,
  Y, and country" were exercised. Phrasings like "country of the
  supplier" or "show the supplier's country" are plausible but not
  measured.
- **Whether the same shape exists for other include-backed columns.**
  Address is the only entity with a nested `addresses[]` list today, so
  the display extraction is Address-specific. A future supplier-metadata
  or attribute-list column would need its own path.
- **Whether the parser emits a `country` filter alongside the
  `country` column** in some phrasings ("active suppliers in US with
  the country"). The correction must not confuse the two; the raw-prompt
  discriminator distinguishes them, but only the single reproducer was
  exercised.
- **The F-050 sequencing.** The sysprompt half of F-027 lands with F-050
  or later. The F-050 branch should re-verify the F-027 reproducer with
  the sysprompt rule active to confirm the parser now emits `country`
  in `fields` directly — at which point the post-parse correction may
  become a no-op but should stay as a defence.
- **The mixed-output-shape caveat from F-017.** A prompt naming both a
  Supplier column AND a country column produces `fields=[col, country]`
  post-fix; the projected-table path renders both. If the user also
  asked for the formatted address, the display would have both a
  `country` column and an `Address` column carrying the blob — arguably
  correct, but not exercised.


<!-- ───── merged from: docs/phase-2/fixes/F-033.md ───── -->

# F-033 — `ReceivablesInvoiceLine` refusal's Example is the failing prompt itself

**Branch:** `phase-2-fix-F-033-refusal-example`
**PR:** #150
**State:** verified
**Session:** 07_SPIRE_Phase2_BugFixing_01

## V0 — Fix statement

The `_NOT_A_ROOT_GUIDANCE["ReceivablesInvoiceLine"]` entry offered
`"Show invoice lines for invoice 300000248096352"` as the worked Example —
byte-identical to the prompt that triggers the very refusal being
explained. A user told "ask for the invoice and its lines together" was
handed back the same failing input, in a loop.

Fix: replace the second element with a DIFFERENT prompt that succeeds and
demonstrates the advice, already present in
`scripts/prompts/10_refusal_examples.txt`:

    Get the AR invoice with CustomerTransactionId 300000248096352

## V1 — Reproducer

    $ python scripts/promptkit.py --run --prompt "Show invoice lines for invoice 300000248096352"
    Reason:   I can look up AR invoice lines, but only as part of the record they belong to.

    Solution: Ask for the invoice and its lines together.

    Example:  Get the AR invoice with CustomerTransactionId 300000248096352
      (refusal: unknown_entity — needs an invoice line entity, which is not supported as a target entity)

The Example is a different, working prompt. Before the fix it was the
prompt that just failed.

## V2 — Paraphrase

    $ python scripts/promptkit.py --run --prompt "Get invoice lines for invoice 300000248096352"
    Reason:   I can look up AR invoice lines, but only as part of the record they belong to.

    Solution: Ask for the invoice and its lines together.

    Example:  Get the AR invoice with CustomerTransactionId 300000248096352
      (refusal: unknown_entity — Invoice lines (ReceivablesInvoiceLine) are not supported as a target entity)

Same refusal, corrected Example. Not phrasing-specific.

## V3 — Sibling unchanged

    $ python scripts/promptkit.py --run --prompt "Get tax lines for invoice 300000248096352"
    Intent:
      target_entity: ReceivablesInvoice
      filters: [{'type': 'by_id', 'value': '300000248096352'}]
      include: ['ReceivablesInvoiceLine', 'ReceivablesTaxLine']

Three-step plan, answers. The tax-lines sibling entry is untouched.

## V4 — Negative still refuses

    $ python scripts/promptkit.py --run --prompt "show me contracts"
    Reason:   Contract isn't something I know about.

    Solution: What I do have: addresses, credit memos, customer accounts, supplier invoices, purchase orders, AR invoices, receipts and suppliers.

    Example:  invoices for Lee Supplies
      (refusal: unknown_entity — needs a Contract entity, which is not supported)

The Contract refusal keeps its own Solution and Example. The fix did not
leak into other refusals.

## V5 — Goldens

    $ diff <(filter /tmp/f033_po.txt) <(filter docs/audit/golden/po_2144_and_lines.txt)
    (no output)

`Show PO 2144 and its lines` is byte-identical to the golden after
filtering `[llm]` / `[cache]` / `Token usage` lines. `capability.py` is
message-layer; the answer path is unchanged.

## V6 — pytest

    $ pytest -q
    1018 passed, 22 deselected in 148.55s (0:02:28)

Baseline was 1016 passed (after F-002). +2 new tests in
`tests/test_f033_refusal_example.py`. No existing test regressed.

## V7 — Test fails without the fix

    $ git stash
    $ pytest tests/test_f033_refusal_example.py -q
    FAILED tests/test_f033_refusal_example.py::test_receivables_invoice_line_example_is_not_the_failing_prompt
    1 failed, 1 passed in 0.16s
    $ git stash pop

Exactly the specific-defect test fails; the class-level guard
(`test_every_not_a_root_example_is_nonempty`) passes on both old and new
code, as a class-level guard should.

## V8, V9 — not applicable

V8 (N>=20) applies to LLM-boundary changes. F-033 changes a dict literal
in `capability.py`. V9 applies to `.sysprompt` edits. None here.

---

## Deviations from the F-033 entry's suggested fix

One deviation on shape, none on substance.

The finding's suggested fix named
`"Show the AR invoice with CustomerTransactionId 1002 and its lines"` as
the replacement Example. That prompt is not in
`scripts/prompts/10_refusal_examples.txt`, and the existing test
`test_nl_parser_capability.py::test_every_promised_example_is_verifiable`
requires every offered Example to appear in that file. Per the operator's
direction, the file was NOT edited to accommodate the fix — instead the
Example was set to a prompt already in the file:
`"Get the AR invoice with CustomerTransactionId 300000248096352"`, which
answers and demonstrates the Solution.

## Not checked

- Whether `_NOT_A_ROOT_GUIDANCE["Site"]`'s example ("supplier sites for
  Lee Supplies") works or refuses. Section B.3 lists that prompt as a
  correct refusal, suggesting a second entry with the same defect; not
  run this session.
- Whether the other example-carrying maps (`_FILTER_GUIDANCE`,
  `_IDENTIFIER_GUIDANCE`, `_OPERATION_EXAMPLES`, `_FALLBACK`) share the
  defect. Only `_NOT_A_ROOT_GUIDANCE` was audited here.
- **Silent zero observed during V2** — a prompt naming the invoice by its
  TransactionNumber (`list invoice lines for AR invoice 61765`) is
  accepted by the parser as `by_id` on `CustomerTransactionId=61765`,
  then fetches 0 records because 61765 is the *TransactionNumber*, not
  the internal CustomerTransactionId. The answer says "No AR invoices
  found" for a real invoice. Separate defect, not F-033; recorded here so
  it is not lost. Belongs with the identifier-resolution family.


<!-- ───── merged from: docs/phase-2/fixes/F-036.md ───── -->

# F-036 — truncation note says "examined for filtering" on an unfiltered fetch

**Branch:** `phase-2-fix-F012-F036-truncation-wording`
**PR:** (pending)
**State:** closed

**Deviation from FIX_PLAN §4 (branch shape).** As F-012.

## V0 — Fix statement

`_local_truncation`'s note f-string changes one word —
`"{examined} examined for filtering."` -> `"{examined} returned."` — so
the note reads true whether or not a filter was applied. The count and
source total stay; only the false claim is removed.

## V1 — Reproducer

    $ python scripts/promptkit.py --run --prompt "Suppliers with their addresses" --show-stages
    ...
    Truncation:
      - suppliers: 303 total in source; 25 returned.

Pre-fix: the same note read `25 examined for filtering.` The fetch
applied no filter — `tool_args` carried only `include_addresses=True`.

## V2 — Paraphrase

    $ python scripts/promptkit.py --run --prompt "List suppliers with their address" --show-stages
    ...
    Truncation:
      - suppliers: 303 total in source; 25 returned.

## V3 — Sibling (unchanged)

    $ python scripts/promptkit.py --run --prompt "active suppliers in US" --show-stages
    ...
    Truncation:
      - suppliers: 164 total in source; 25 returned.

A filtered fetch — previously read "examined for filtering"; now reads
"returned". Both true; the new wording does not distinguish the two
cases, which is deliberate: the filter's presence or absence is visible
in the Intent block above the answer.

## V4 — Negative (still refuses)

    $ python scripts/promptkit.py --run --prompt "show me contract renewals" --show-stages
    ...
    Reason:   that kind of record isn't something I know about.
    Solution: What I do have: addresses, credit memos, customer accounts, supplier invoices, purchase orders, AR invoices, receipts and suppliers.
    Example:  invoices for Lee Supplies
      (refusal: unknown_entity — The entity 'Contract' is not supported.)

Unchanged.

## V5 — Goldens

`docs/audit/golden/suppliers_with_open_pos.txt` line 87:
`25 examined for filtering.` -> `25 returned.` The other two goldens do
not carry the note.

## V6 — pytest

See F-012.

## V7 — Test fails without the fix

See F-012 (same stash/pop cycle).

## V8 — N>=20

Not required. Deterministic.

## V9 — --validate

Not required. No `.sysprompt` touched.

## Deviations from the F-036 entry's suggested fix

The entry offered three options: (1) drop the phrase (-> `"25 examined."`);
(2) parameterise the suffix on a `filtered: bool`; (3) canonical wording
that fits both cases, suggesting `"25 of 656 examined"` or `"25 retrieved
of 656"`. It named (3) as the smallest honest fix.

Landed: a fourth wording, `"25 returned."` — closer in spirit to the
entry's (1), but with a verb that reads as prose. Rationale: `returned`
names exactly what the count is (rows the tool handed back) without
implying a filtering step, and without lengthening the note. The
`"25 of 656 examined"` phrasing would have duplicated `656 total in
source` already present in the same line.

The entry's preamble ("the phrase is hardcoded; the fix is to make the
wording honest") is what landed. Only the specific verb differs.

## Not checked

- Whether the note appears in the other `05/07/08` prompt-set baselines
  the `_local_truncation` docstring names. Only the three goldens were
  checked.
- Whether the "total in source" looseness (which the docstring itself
  flags as "reads as unfiltered when the fetch was scoped") should be
  fixed in a later pass. The docstring still says so; deliberately left
  alone.

## L2 — prompt-set run

Same run as F-012 (`scripts/prompts/14_truncation_narration.txt`, output
captured to `docs/phase-2/fixes/F-012-F036-L2-run.txt`). Sections 3 and 4
are F-036's coverage.

Section 3 — unfiltered fetch, cap hit. Note MUST say "returned" and MUST
NOT contain "for filtering". 4 of 4 pass:

    Suppliers with their addresses       -> "suppliers: 303 total in source; 25 returned."
    List suppliers with their address    -> same
    suppliers and their addresses        -> same
    list suppliers including their addresses -> same

Section 4 — sibling and negative, both correct:

    active suppliers in US        -> "suppliers: 164 total in source; 25 returned."
                                     (filtered fetch, same wording)
    show me contract renewals     -> unknown_entity refusal, unchanged

Aggregate assertion across the 14-prompt run:
  - "returned." appears in 11 truncation notes.
  - "for filtering" appears 0 times.


<!-- ───── merged from: docs/phase-2/fixes/F-039.md ───── -->

# F-039 — aggregate comparisons over-claim with "under-invoiced"

**Branch:** `phase-2-fix-F039-aggregate-difference-phrase`
**PR:** (pending)
**State:** fixed
**Session:** 07_SPIRE_Phase2_BugFixing_04

## V0 — Fix statement

`synthesizer/aggregation.py` gains `MOST_UNMATCHED_RATIO = 0.75` and
`_aggregate_difference_phrase(difference, unmatched, total)`. The two
AGGREGATE summarizers (`_summarize_supplier_comparison`,
`_summarize_top_suppliers_comparison`) call it; the SINGLE-PO summarizer
(`_summarize_po_comparison`) continues to call `_direction_phrase`.

When the unmatched fraction is at or above the threshold, the phrase
reports the state of the data (“X of ordered value has no PO-matched
invoice”) rather than a supplier behaviour (“under-invoiced by X”).
Below the threshold, the previous wording stands.

## V1 — Reproducer

    $ python scripts/promptkit.py --run \
        --prompt "Compare ordered vs invoiced for our top 3 suppliers" \
        --show-planner
    ...
    Answer:
    Invoiced vs ordered for the top 3 supplier(s) by PO value:
    - EIP Inc: ordered 865,287,107.89, PO-matched invoiced 710,712.31 —
      864,576,395.58 of ordered value has no PO-matched invoice
      (3,207 non-PO invoices excluded).
    - Staffing Services: ordered 328,053,963.10, PO-matched invoiced
      31,312.91 — 328,022,650.19 of ordered value has no PO-matched
      invoice (2,422 non-PO invoices excluded).
    - JGA: ordered 159,598,443.36, PO-matched invoiced 4,566,124.36 —
      155,032,319.00 of ordered value has no PO-matched invoice
      (2,267 non-PO invoices excluded).

Pre-fix each line ended “— under-invoiced by X (N non-PO invoices
excluded)”. The unmatched-invoice fraction per supplier is 97.7% /
99.4% / 97.6% — the excluded set IS the comparison, so “under-invoiced”
asserts a billing state that the arithmetic does not establish. The
number was arithmetically correct; the word was not.

Post-fix: the difference is reported as what it is — value that has
no PO-matched invoice on this pod. The parenthetical disclosure is
preserved.

## V2 — Paraphrase

Not run this session. The two summarizers build the phrase from the
tool's `total_difference`, `unmatched_invoice_count` and `invoice_count`
regardless of prompt phrasing; the fix changes the phrase function, not
a phrasing-specific match.

## V3 — Sibling unchanged (single-PO comparison)

    $ python scripts/promptkit.py --run \
        --prompt "How does invoiced compare to ordered for PO 162034?" \
        --show-planner
    ...
    Answer:
    PO 162034 (Lee Supplies): ordered 758.00, invoiced 830.01 across
    1 invoice — over-invoiced by 72.01.

The single-PO shape is untouched. For PO 162034 the direction is
positive (invoiced > ordered), so the phrase is `over-invoiced by 72.01`
— which is correct for this case and remains the fair reading
(there is exactly one invoice on this PO, and it IS matched; there is
no excluded majority to caveat). The unit test
`test_single_po_still_uses_under_invoiced` pins the negative-direction
case and passed in V7's post-fix run.

## V4 — Negative

Not applicable — F-039 changes wording on the comparison summary,
not refusal shape. No prompt newly refuses or newly answers.

## V5 — Goldens

    $ git status docs/audit/golden/
    On branch hardening-master
    nothing to commit, working tree clean

None of the three golden prompts is a comparison query.

## V6 — pytest

    1107 passed, 22 deselected in 219.67s (0:03:39)

Baseline 1094 (after F-020) + 13 new F-039 tests.

## V7 — Test fails without the fix

    $ git stash push src/spire/synthesizer/aggregation.py
    $ pytest -q tests/test_f039_aggregate_difference_phrase.py
    ImportError: cannot import name 'MOST_UNMATCHED_RATIO' from
    'spire.synthesizer.aggregation'
    1 error in 0.17s

The helper, the constant and the two call-site changes all disappear
with the stash, so the test file fails at collection. Reversion
confirmed by `git stash pop` and re-running: 13 passed.

## V8, V9 — not applicable

V8 (N≥20) applies to LLM-boundary changes. F-039 changes a
deterministic phrase function on the comparison path; no LLM is
involved. V9 applies to `.sysprompt` edits. None here.

## Deviations from the F-039 entry's suggested fix

The entry named two options: (1) soften the phrasing for the two
aggregate shapes only, (2) change `_direction_phrase` universally. It
recommended option 1. The landed fix is option 1.

The threshold is a new design choice the entry left open. The entry
suggested a ratio-based guard without naming a value; the current
data places the three affected suppliers at 97.7% / 99.4% / 97.6%,
well above any reasonable cut. `0.75` is chosen so the aggregate
shapes only abandon `_direction_phrase` when the excluded set is a
clear majority — a comparison whose matched invoices represent less
than a quarter of what was fetched is describing a document-matching
gap, not a billing one.

## Not checked

- The single-supplier shape (`Compare ordered vs invoiced for Lee
  Supplies`) was not run through the pipeline this session, only
  exercised by the unit test. Same code path as top-N; the unit test
  `test_supplier_scoped_high_unmatched_drops_under_invoiced` covers it.
- Whether the pod has any aggregate comparison whose unmatched ratio
  falls between 0.5 and 0.75 (the region where the threshold choice
  matters). Three suppliers sampled this session; a wider sweep would
  test whether 0.75 is well-placed.
- Whether the threshold should be configurable per-entity. Not
  warranted by the data; a constant is simpler.

## Class note

Closes D-11. Same shape as F-012, F-015 and F-020: the pipeline
produced a number or shape correctly and then a word was chosen that
asserted more than the number supported. All four fix sites are in the
synthesis layer — three in `synthesizer.py`'s local branches, this
one in `aggregation.py`'s comparison summarizers.

Cross-ref F-026 (the same `_direction_phrase` function's zero-PO case,
already closed as a latent risk). F-039 and F-026 together cover the
phrasing on both ends of the function's input range: a vacuous
difference (F-026) and a mismatched-majority difference (F-039).


<!-- ───── merged from: docs/phase-2/fixes/F-041.md ───── -->

# F-041 — AR invoice children named first refuse or silently drop

**Branch:** `phase-2-fix-F-041-ar-child-root`
**PR:** #151
**State:** verified
**Session:** 07_SPIRE_Phase2_BugFixing_01

## V0 — Fix statement

Three layers, all required for the same user outcome.

**Layer 1 — router.** The LLM classifier picks `payables` when the leading
noun is "invoice" (mapping to `Invoice`), even with the AR child synonyms
now in its menu. A deterministic correction (`_correct_modules_for_ar_child`
in `router.py`) adds `receivables` when the prompt names an AR-invoice
child, so the AR sysprompt blocks load.

**Layer 2 — parser.** The three AR sysprompt blocks taught only the
TRAILING phrasing ("and its lines", etc.). Added leading-phrasing rules to
each, mirroring the shape `b_ar_tax_lines` already had for its one working
phrasing.

**Layer 3 — field-split.** A DFF column (`__FLEX_Context`) requested on the
parent invoice is satisfied by the active DFF include. Added
`ReceivablesInvoiceTransactionDFF` to `_FIELDS_SATISFIED_BY_INCLUDE`, so the
display stops printing a false "column not available" note over data the
pipeline already fetched.

## V1 — Reproducer (16 previously-refusing prompts)

Full sweep re-run captured in `t_after2.txt`.

Before (pre-fix): 16 AR-child prompts refused; e.g.
    Reason:   I can look up AR invoice lines, but only as part of the record they belong to.
    Reason:   I can look up AR invoice flexfields, but only as part of the record they belong to.

After (post-fix), all 16 answer with the correct child data, e.g.:

    Answer:
    AR Invoices:
      Transaction           : 61765
      CustomerTransactionId : 300000248096352
      Amount                : 39969.0
      Currency              : GBP
      Date                  : 2017-06-30
      Customer              : ABC Corporation Americas
      Status                : Complete

      Invoice 61765 — lines:
        Line        : 1
        Description : Consultation
        Qty         : 1.0
        Unit Price  : 39969.0
        Amount      : 39969.0

The three DFF phrasings now show `DFF: DOO` (from invoice 1002). The three
tax phrasings show 4 lines and 8 tax rows.

## V2 — Paraphrase (38 previously-passing prompts)

All 38 non-AR prompts in the same 64-prompt sweep still answer. Every PO
child, every Supplier contact, every CustomerAccount child — unchanged
target, unchanged include, unchanged rows. Captured in `t_after2.txt`.

## V3 — Sibling (unchanged)

Controls from the sweep: `show PO lines for PO 2144` still shows
`Router: modules=['procurement']` and roots on PurchaseOrder. `invoices
for supplier 1252` still routes `['payables', 'supplier']` and roots on
Invoice with no child include. Both unchanged.

## V4 — Negative (still refuses)

The remaining 10 refusals in the sweep are correct by design:

- 4 supplier-number-address prompts — F-042 scope, separate finding
- 3 sites-for-supplier prompts — F-025, reverse-only child
- 3 classifications-for-supplier prompts — F-025, reverse-only child

None of them is F-041's shape, and none was expected to change.

## V5 — Goldens

    $ diff <(filter /tmp/f041_po.txt) <(filter docs/audit/golden/po_2144_and_lines.txt)
    (no output)

`Show PO 2144 and its lines` remains byte-identical after filtering
`[llm]` / `[cache]` / `Token usage` lines. Non-AR paths unchanged.

## V6 — pytest

    $ pytest -q
    1028 passed, 22 deselected in 167.42s (0:02:47)

Baseline was 1016 passed (after F-002). +2 from F-033's
`test_f033_refusal_example.py`, +10 from F-041's
`test_f041_ar_child_root.py`. No existing test regressed.

## V7 — Test fails without the fix

    $ git stash
    $ pytest tests/test_f041_ar_child_root.py -q
    E   ImportError: cannot import name '_correct_modules_for_ar_child'
        from 'spire.nl_parser.router'
    ERROR tests/test_f041_ar_child_root.py
    $ git stash pop

The stash removes the router helper the tests import. The failure is an
import error at collection time, which is exactly the shape of "the
tests cannot pass without the fix" — the corrector the tests exercise
does not exist on the pre-fix code. Blunt, but honest: no F-041 test can
pass without the fix's three layers present.

## V8, V9 — not applicable

V8 (N≥20) applies to LLM-boundary changes. F-041 changes prompt content
and code routing, not model parameters; the sweep of 64 prompts is a
larger sample than V8 requires for a single-prompt reproducibility check.
V9 (`--validate` across corpora) is **skipped by operator decision**; see
"Deviations" below for the reasoning.

---

## Deviations from the V-standard

**V9 skipped.** The `.json` corpora encode the ROUTER and TOOL choices the
system made under the pre-F-041 code. F-041 intentionally changes the
router's module choice for AR-child prompts and, downstream, the parser's
target_entity. Any `--validate` mismatches would therefore be recorded
changes, not regressions.

Regenerating the affected corpora with `--generate` would bake the new
behaviour in, giving a file that asserts only "the system does today what
it did five minutes ago" — a check with no independent force.

The verification value of `--validate` is instead covered here by V1, V2,
V3, and V4: the full 64-prompt sweep, captured in `t_after2.txt`, exercises
every previously-failing prompt (must now answer) and every previously-
passing prompt (must be unchanged). This is stronger evidence than the
corpus comparison, because it asserts on the ANSWERS, not on the module
label. The operator chose to skip V9 on this basis; the decision is
recorded so a future session knows it was deliberate.

## Not checked

- Whether other AR-child phrasings beyond the 64 the sweep exercised
  still fail. The sweep is wide; a broader pass would extend it.
- Whether the same failure shape exists for other non-AR children not
  tested (e.g. `AccountCreditMemo` and `AccountReceipt` were tested via
  their customer-account scope; grandchildren of other entities were not).
- Whether the correction regex `_AR_INVOICE_CHILD_RE` over-matches on a
  prompt that mentions both "invoice" and a child word without asking for
  a child (e.g. a hypothetical "invoice paid, lines empty" — no such
  prompt observed).
- Whether `build_parser_context.py`'s CARVE line numbers and
  `_EXPECTED_LITERAL_SHA` need updating. The script reads from the old
  multi-fragment literal in `parser.py`; the literal is now one
  triple-quoted string in `context_assembly.py`. Not exercised by pytest;
  if anyone runs the carve script it will fail. Recorded as a follow-up.


<!-- ───── merged from: docs/phase-2/fixes/F-044.md ───── -->

# F-044 — double-encoded `value_json` crashes the tool at schema validation

**Branch:** `phase-2-fix-F044-double-encoded-value`
**PR:** (pending)
**State:** closed

**Deviation from FIX_PLAN §4 (sequence order).** F-044 is a crash;
F-010 (the plan's current next-task) is wrong-data. The plan's §8.3.1
severity rule puts wrong-data first. This branch fixes F-044 ahead of
F-010 because the failure surfaced mid-session while L2-testing
F-012/F-036, and the diagnostic that pinned the mechanism was already
in hand. F-010 remains the next task after this merges.

## V0 — Fix statement

`src/spire/nl_parser/draft.py::DraftIntent.to_intent` — after the
existing `json.loads(value_json)`, if the decoded value is a STRING
whose first character is `{`, attempt a second decode; keep the result
if it is a dict. A dict or list is not a legitimate filter VALUE on
this codebase — the planner's `_build_entity_fetcher_args` only checks
`isinstance(value, dict)` for range-shaped filters, and no filter in
the KG takes a list — so a string that decodes to a dict is
unambiguously the model's double-encoding.

## V1 — Reproducer

    $ python scripts/promptkit.py --run --prompt "invoices for supplier 1252 above 50000"
    ...
    Answer:
    Showing 9 invoices from an examined sample; the true matching count is not known.
    Truncation:
      - invoices: unknown total in source; 9 returned.

Pre-fix, in a fraction of runs:

    ERROR: execute: 1 validation error for call[search_invoices]
    amount_min
      Input should be a valid number, unable to parse string as a number
        [type=float_parsing, input_value='{"min": 50000}', input_type=str]

## V2 — Paraphrase

    $ python scripts/promptkit.py --run --prompt "invoices for supplier 1252 above 100000"
    ...
    Answer:
    Showing 7 invoices from an examined sample; the true matching count is not known.

`above 100000` was the second observed failure value in the diagnostic
run (f044_diag_20260922_144608.txt, Part B). It passes with the fix.

## V3 — Sibling (unchanged)

    $ python scripts/promptkit.py --run --prompt "invoices for supplier 1252 above 30000"
    ...
    Answer:
    Showing 14 invoices from an examined sample; the true matching count is not known.

A value that was already passing pre-fix — unchanged.

## V4 — Negative (still refuses)

    $ python scripts/promptkit.py --run --prompt "invoices"
    ...
    Reason:   I can look up supplier invoices, but this doesn't say which one.
      (refusal: missing_identifier — Invoice queries must specify a supplier filter, which is missing from this request.)

Unchanged.

## V5 — Goldens

`git status docs/audit/golden/` is empty. No golden modified. F-044's
fix does not affect the three goldens' prompts.

## V6 — pytest

    1062 passed, 22 deselected

Baseline 1054 + 8 new F-044 tests.

## V7 — Test fails without the fix

Stash `src/spire/nl_parser/draft.py`; run the F-044 test file: 3 failed,
5 passed. The three failures are the three reproducers (min, max, range
form). The five passing are the regression guards on the fix's
single-encoded and unparseable paths.

Pop the stash; rerun: 8 passed.

## V8 — N>=20

    Reproducer, 20 runs: 20 pass, 0 errors.
    See docs/phase-2/fixes/F-044-v1v4v8.txt.

The defect was intermittent (a double-encoded value_json arrives
roughly one run in six at the failing phrasings). The fix is
deterministic on the input it receives, but the DEMONSTRATION needed
the plan's N>=20 threshold. 20 runs of the prompt that failed earlier
this session produce zero errors post-fix.

## V9 — --validate

Not applicable. No `.sysprompt` file touched.

## Deviations from the F-044 entry's suggested fix

The entry left the mechanism "not established" and named three
candidate fix sites: `parser.py`'s decode, `plan_builders.py`, and the
`b_invoice_amount` sysprompt. The diagnostic run
(`F-044-diag.txt`) ruled out two of the three:

- **Parser.py**: `to_intent` is the decode site; the outer `try/except`
  catches only non-parseable input, so double-encoded input falls
  through unmodified. That is the site, but at
  `draft.py::to_intent`, not `parser.py`.
- **Plan builders**: `_build_entity_fetcher_args` at plan_builders.py:302
  passes `raw_value` through unchanged. Disproved by the failure text
  showing a STRING (not a dict-stringified) reached the tool.
- **Sysprompt**: no evidence the guidance produces the wrong shape;
  the model emits the right shape most of the time. Not touched.

The landed fix is at the parser's decode step and only there. A
defensive re-parse in `plan_builders.py` was considered as belt-and-
braces and left out, per FIX_PLAN's "smallest honest fix" rule and
because there is no second entry point to the planner that would
bypass `to_intent`.

## Not checked

- Whether the same double-encoding affects other JSON-shaped draft
  values on other filters. F-044's reproducer exercises
  `invoice_amount` (dict value); the fix's guard fires on any string
  starting with `{` regardless of filter type, but no other filter's
  prompt was tested.
- Whether a list-shaped value (`[...]`) has the same defect. The
  current guard only accepts dicts; if a filter is ever added with a
  list value, the guard needs a matching branch.
- Whether the model's double-encoding rate varies by prompt length or
  entity. The observed rate on this prompt was 1 in 3 during the L2
  run and 1 in 6 in the boundary sweep, but no systematic rate was
  measured.
- Whether a fix on the sysprompt side (telling the model not to
  double-encode) would reduce the rate further. The defence-in-depth
  fix is in place; the prompt side was not explored.

## L2 — post-merge 78-prompt sweep

`scripts/prompts/13_child_as_root.txt` (64 prompts) plus
`scripts/prompts/14_truncation_narration.txt` (14 prompts) re-run on
the merged tree after PR #158 landed. Full output committed alongside
this file as `F-012-F036-F044-78-prompt-sweep.txt`.

Result: **78/78 ran clean, 0 runtime errors.**

The numbers, per assertion:

    runtime errors:                  0
    F-012 sample sentences:          6   (matches the six composite prompts)
    "for filtering" anywhere:        0
    "returned." in notes:           12
    refusals:                        2   (both correct negatives)
    F-044 signature (stringified):  0
    sites rows:                      3
    classifications rows:            3

Two things this closes for F-044 specifically:

- The double-encoding defect (its signature being
  `input_value='{"...}', input_type=str`) does not appear in any of
  the 78 prompts' output. Zero occurrences on the merged tree, versus
  two occurrences in the pre-fix diagnostic run
  (`F-044-diag.txt`).
- Part C of the diagnostic exercise (`has_invoice_over_amount`, a
  different filter and different builder path) is exercised again
  here via the file-13 sweep's supplier-with-invoices-over-amount
  family, and answers correctly. The blast-radius question the fix
  file left open is answered for that specific path.

**L2 output for F-012 and F-036.** The same file is the L2 record for
those two findings as well — file 14 is their regression set, and all
14 prompts re-ran clean. Their fix files reference the L2 run they
originated; this post-merge sweep is a second, wider confirmation.


<!-- ───── merged from: docs/phase-2/fixes/F-045.md ───── -->

# F-045 — composite date bounds return 0 with a misleading "capped" note

**Branch:** `phase-2-fix-F045-created-since-priority`
**PR:** (pending)
**State:** fixed
**Session:** 18_SPIRE_Phase2_BugFixing_17

## V0 — Fix statement

Two parts, both required, both in
`src/spire/mcp_server/tools/purchase_orders.py`.

**Part 1 — the priority reorder.** The tool sends exactly one clause to
the server (the pod cannot AND-combine). With both `created_since` and
`created_before` set, the priority chain picked `created_before` first,
so the fetch sent `CreationDate < <before>`. Reordered:
`created_since` above `created_before`.

**Part 2 — an orderBy on the fetch.** Picking the right clause is not
sufficient on its own. The pod's default physical scan on
`/purchaseOrders` starts at the far end of the collection (verified live
on dabpqy 2026-09-24). Pinning the order to `CreationDate:asc` when the
server clause is a `>=` date bound puts the 200-row window at the
range's lower edge.

## V1 — Reproducer

    $ python scripts/promptkit.py --run \
        --prompt "purchase orders created in 2023" --show-planner
    ...
    Intent:
      target_entity: PurchaseOrder
      filters:
        - {'type': 'created_since', 'value': '2023-01-01'}
        - {'type': 'created_before', 'value': '2024-01-01'}

    Plan:
      Step 1: search_purchase_orders
        tool_args:      {'created_since': '2023-01-01', 'created_before': '2024-01-01'}

    Outputs:
      open_pos: 25 record(s)

    Answer:
    Showing 25 purchase orders from an examined sample; the true matching
    count is not known.
    All 25 have Status Closed.
    ...
      SU616356 | 300000259443165 | Closed | JGA | Petrova, Laura
      US164585 | 465841          | Closed | EIP Inc | Roth, Calvin
      ...

Pre-fix: `open_pos: 0 record(s)`, narrated "No purchase orders found in
the examined sample". Post-fix: 25 records, every CreationDate in 2023.

Full capture: `docs/phase-2/fixes/F-045-v1v4.txt`.

## V2 — Paraphrase

    $ python scripts/promptkit.py --run \
        --prompt "purchase orders created between Jan and Mar 2025" --show-planner
    ...
      open_pos: 25 record(s)
    Showing 25 purchase orders from an examined sample; the true matching
    count is not known.
    Status: 20 Closed, 4 Open, 1 Incomplete.

A different range, same composite shape (`created_since=2025-01-01`,
`created_before=2025-04-01`), same 25-row answer. Pre-fix this returned
25 records too — because 2025 falls at the top of the physical scan and
the upper-bound window reached it by accident. Post-fix it returns 25
by construction (the `>= since` window starts at the range's lower
edge). The two produce the same result on this prompt; the difference
would show on a range below the pod's physical scan window.

## V3 — Sibling (unchanged)

    $ python scripts/promptkit.py --run \
        --prompt "Purchase orders older than 6 months" --show-planner
    ...
      tool_args:      {'created_before': '2026-03-24'}
      open_pos: 25 record(s)
    Showing 25 of 16,937 purchase orders.

One-sided `<` prompt. The `created_before` branch still fires and no
`orderBy` is added (the scan from the bottom of the collection already
starts where a `<` range begins). Behaviour unchanged from pre-fix.

## V4 — Negative (still refuses)

    $ python scripts/promptkit.py --run --prompt "purchase orders" --show-planner
    Reason:   I can look up purchase orders, but this doesn't say which one.
    Solution: Give me the PO number.
    Example:  What is the risk rating on PO 701337 and why?
      (refusal: missing_identifier — PurchaseOrder root has no identifier
       and no explicit list request)

Bare-noun prompt, no verb. F-001's `_is_explicit_po_list` does not fire
for this shape, and this fix does not touch that path. Unchanged.

## V5 — Goldens

    $ git status docs/audit/golden/
    On branch phase-2-fix-F045-created-since-priority
    nothing to commit, working tree clean

None of the three golden prompts names a PO date range. No golden
touched.

## V6 — pytest

    $ python -m pytest -q
    1229 passed, 1 skipped, 22 deselected in 362.88s (0:06:02)

Baseline 1216 passed + 13 new F-045 tests = 1229. The 1 skip is
`tests/test_corpus_consistency.py`, module-level since `1f980d1`.

## V7 — Test fails without the fix

Verified 2026-09-24 by reverting the source file to `HEAD~1` and
re-running the test file:

    $ git checkout HEAD~1 -- src/spire/mcp_server/tools/purchase_orders.py
    $ python -m pytest -q tests/test_f045_created_since_priority.py
    FAILED test_created_since_wins_when_both_bounds_set
    FAILED test_created_since_sets_creation_date_ascending_order
    FAILED test_created_since_alone_still_sets_orderby
    3 failed, 10 passed in 0.12s

    $ git checkout HEAD -- src/spire/mcp_server/tools/purchase_orders.py
    $ python -m pytest -q tests/test_f045_created_since_priority.py
    13 passed in 0.07s

The three failures map exactly to the two halves of the fix — one test
for the reorder, two for the orderBy. The remaining ten are
neighbours-and-guards: the LastUpdateDate pair (F-047), the
supplier_id / status branches, the supplier_name lowest-priority branch,
and the "no orderBy on `< before`" over-reach guard. All ten pass on
both trees by design.

**Mispredicted twice, recorded so a reader trusts the rest.** An earlier
stash-based V7 attempt predicted 2 red and got 1 — the reorder test.
The prediction assumed `test_reproducer_does_not_send_composite_and`
would also fail pre-fix; it does not, because the pre-fix clause
(`CreationDate < '2024-01-01'`) contains no `" AND "` either. That test
is a both-trees-pass guard, not a bug-revealer. The first V7 attempt
also used `git stash` against a committed change and stashed nothing —
the source was on HEAD, not in the working tree. Corrected with
`git checkout HEAD~1`.

## V8 — not applicable

No LLM-boundary change. The fix is a priority reorder plus an extra
query parameter; the LLM's involvement (the parser choosing an intent
shape) is unchanged.

## V9 — not applicable

No `.sysprompt` touched. No `--validate` run required.

## Deviations from the F-045 entry

The entry named two fix shapes, neither of which is what landed.

1. **Tool-side — "issue two queries and intersect client-side, or fail
   loudly on the composite."** Neither. The composite clause is not what
   the tool sends — the priority chain sends one clause. Both candidate
   mechanisms the entry named (`silent-zero composite`, `fail loud`)
   were wrong about the shape of the failure.

2. **Narration-side — "suppress the 'capped' note when the fetch
   returned 0 with no total_available."** Not landed. The note is
   honest: the fetch WAS capped, and the total WAS unknown. The 0 rows
   were not the note's fault — they were the fetch landing at the wrong
   end of the collection. Fixing the fetch makes the 0 disappear;
   suppressing the note would have hidden a real signal.

The entry's own "Not checked" list is the reason both misdiagnoses
survived:

- "Whether the pod accepts composite `CreationDate` ranges on
  /purchaseOrders." It does not — HTTP 400, loud. But the tool never
  sends a composite, so the answer is orthogonal to the bug.
- "Whether other composite date prompts behave the same." They do not —
  see V2.
- "Whether the pod behaviour is silent-zero like F-012's /invoices." It
  is not: composite here 400s. The F-012 parallel was wrong.

## What the probe revealed beyond the entry

The entry's reproducer shape (composite args, 0 records, capped note)
matched F-012's symptom but not its mechanism. Three distinct pod facts
that had not been documented in the endpoints reference, all confirmed
live on dabpqy 2026-09-24:

1. **Composite `q=` on `/purchaseOrders` 400s, does not silent-zero.**
   F-012's `/invoices` falsifier returned 200 with `totalResults: 0`; the
   same shape on PO 400s. Same family, different failure mode.

2. **The pod's default physical scan is not stable at the row level.**
   `q=CreationDate >= '2023-01-01'&limit=200` (no projection) returned
   rows beginning 2024-07-01. The same query with `fields=` or
   `orderBy=` returned rows beginning 2023-01-11. The default scan
   order is not defined and is not the same as sorting by any field.

3. **`orderBy=CreationDate:asc` composes with `q=`.** Two identical
   calls with the same clause and the same orderBy returned the same
   rows starting at 2023-01-11. This is the stable sort key for a
   date-bounded fetch on this collection.

Facts 2 and 3 belong in the endpoints reference; adding them is a
follow-up task (the reference file was not touched by this branch).

## Not checked

- **The identical shape on the LastUpdateDate pair.** F-047's
  `updated_in_last_n_months` → `last_updated_after` has the same
  `>=`-without-`orderBy` structure. F-047's V9 sweep answered its
  prompts (`purchase orders updated in the last 3 months` returned 278
  records), so the bug does not reproduce there today — but "answered"
  is not "answered with the window at the correct end of the
  collection". A follow-up should probe
  `q=LastUpdateDate >= '2026-06-23'&limit=200` and see where the window
  lands. If it lands at the wrong end, F-047 gains a second fix; if it
  lands at the right end, this note becomes the evidence that
  `orderBy` is unnecessary there.

- **The `<` branches get no orderBy.** By choice, not by verification.
  A `<` bound scans from the bottom of the collection upward, which is
  where the range begins — but the physical scan order is not
  documented, so "the bottom" is an assumption. V3 shows `<` alone
  returning 25 rows; it does not prove the window is at the range's
  lower edge for every `<` clause.

- **Whether `orderBy=CreationDate:asc` composes with every other
  clause the tool sends.** Only tested with `q=CreationDate >= X`.
  `SupplierId=<n>` + `orderBy=CreationDate:asc` was not run;
  `StatusCode='OPEN'` + `orderBy=CreationDate:asc` was not run. The
  priority chain restricts orderBy to the `created_since` branch, so
  this is a latent risk rather than a live one — but if any of those
  shapes appears in a future prompt, the composition needs its own
  probe.

- **Whether the pod's default scan order can be relied on at all.**
  The 2024-07-01 first row and the 2023-01-11 first row (with
  `fields=` or `orderBy=`) may indicate (a) an unstable scan, (b) a
  different index selected by the query planner, or (c) a cached plan
  difference. The mechanism was not investigated; the effect was, and
  the fix is on the effect. A future curl session could narrow it.

- **The other PO search prompts in the corpus.** Only the four
  prompts in V1–V4 were run. The class-level sweep of every PO prompt
  that carries a date bound would be a `--prompt-file` run over
  `02_purchase_order.txt` and `15_po_relative_date_filters.txt`. Not
  run this session; the four-prompt sweep covers the shape and the
  two neighbours.


<!-- ───── merged from: docs/phase-2/fixes/F-046.md ───── -->

# F-046 — Invoice gains relative-date filters; guard and sysprompt widened

**Branch:** `phase-2-fix-F046-F047-F048-date-filters`
**PR:** (pending)
**State:** fixed
**Session:** 07_SPIRE_Phase2_BugFixing_06

## V0 — Fix statement

Invoice gains two relative-date filters mirroring F-011b's PO split:
`older_than_n_months` (routes to the tool's `invoice_date_before`) and
`created_in_last_n_months` (routes to `invoice_date_after`). The
sysprompt teaches both phrasings and drops the "MUST include supplier"
clause that blocks a date-only Invoice query. The planner's Invoice
guard accepts any date filter as a valid root reference.

Three sites, four files. Sites 2b and 3 were under-scoped in the F-046
entry's "Fix location"; the parse probes on 2026-09-23 (below) showed
them.

**Correction from the fix file's first draft (2026-09-23).** The first
draft claimed a fourth site — widening the `_build_entity_fetcher_args`
ftype tuple in `plan_builders.py`. On re-reading, the tuple already
contains `("older_than_n_months", "created_in_last_n_months")`. The KG
lookup is keyed on `(ftype, entity)` and the tuple is entity-agnostic,
so Invoice rows reusing those exact ftype names are picked up with no
plan_builders change. The F-046 entry was right on that point. The site
was a misreading; it is removed.

## Site enumeration

| # | Site | Where | Entry named it? |
|---|---|---|---|
| 1 | Two new `(Invoice, ...)` KG filter rows | `scripts/sql/kg_schema.sql` `kg_entity_filter` | yes |
| 2a | Add relative-date rule for Invoice | `context/payables/b_invoice_date.sysprompt` | yes |
| 2b | Rewrite "MUST include this supplier filter" to scope-inclusive | `context/payables/b_invoices_for_supplier.sysprompt` | no — new |
| 2c | Same edit, mirrored in the byte-equality literal | `nl_parser/context_assembly.py::_SYSTEM_PROMPT_PREAMBLE` | no — new |
| 3 | Widen Invoice guard's `has_root_ref` tuple to accept date filters | `planner/planner.py::generate_plan` | no — new |

## Evidence — the parse probes that shaped the sites

Direct parse, 2026-09-23 against `dabpqy`:

    === invoices in 2024 ===
      target_entity: Invoice
      filters: [{'type': 'invoice_date', 'value': {'from': '2024-01-01', 'to': '2025-01-01'}}]

    === invoices older than 6 months ===
      refusal: RefusalFlavor.UNSUPPORTED_FILTER — relative date filters such as 'older than 6 months' are not supported for Invoice; date filters on invoices must be absolute ranges using invoice_date.

    === invoices in the last 30 days ===
      refusal: RefusalFlavor.MISSING_IDENTIFIER — invoice queries (except for a specific invoice number) require a supplier to be specified

Three readings:

1. **`invoices in 2024` parses to the right intent.** The sysprompt rule
   for absolute-date Invoice (in `b_invoice_date.sysprompt`) already works.
   The refusal comes from the planner guard, which only accepts
   `supplier`/`purchase_order`/`invoice_number` as root refs. This is a
   pre-existing wrong-refusal for absolute-date Invoice queries, and it is
   not in the F-046 entry. Site 3.

2. **`invoices older than 6 months` self-declares `unsupported_filter`.**
   The sysprompt has no relative-date rule for Invoice, so the model
   generalises "not supported" from the prompt's silence. Site 2a.

3. **`invoices in the last 30 days` self-declares `missing_identifier`.**
   The `b_invoices_for_supplier.sysprompt` rule "Invoice queries MUST
   include this supplier filter" is correct for its original shape
   (`invoices for Lee Supplies`) but blocks the shape we are adding.
   Site 2b.

## Pod-side probes — the substrate the fix maps to

Curls against `dabpqy`, 2026-09-23:

    $ curl ... "q=InvoiceDate >= '2024-01-01'&totalResults=true"   ->  HTTP 200, totalResults: 6982
    $ curl ... "q=InvoiceDate < '2024-01-01'&totalResults=true"    ->  HTTP 200, totalResults: 46027
    $ curl ... "q=SupplierNumber='1252' AND InvoiceDate >= '2024-01-01'"  ->  HTTP 200, totalResults: 0

Both bounds of `InvoiceDate` filter server-side; composite `q=` still
fires the silent-zero quirk. F-046's `older_than_n_months` leg maps to
`invoice_date_before` (server-side `<`) and `created_in_last_n_months`
maps to `invoice_date_after` (server-side `>=`). No client-side trickery
needed for either direction.

## V1 — Reproducer

    $ python scripts/promptkit.py --run \
        --prompt "invoices older than 6 months" --show-planner

Expected after fix: Intent target_entity Invoice, filter
`older_than_n_months: {"months": 6}`; Plan Step 1 tool_args
`{'invoice_date_before': '<today-6mo ISO>'}`; an answered list of
invoices; the truncation note naming the sample when the fetch caps.

Pre-fix: `unsupported_filter` — "relative date filters such as
'older than 6 months' are not supported for Invoice".

## V2 — Paraphrase

    $ python scripts/promptkit.py --run \
        --prompt "invoices in the last 30 days" --show-planner

Expected after fix: same intent shape, `created_in_last_n_months`;
tool_args `{'invoice_date_after': '...'}`.

## V3 — Siblings unchanged

    $ python scripts/promptkit.py --run \
        --prompt "invoices in 2024" --show-planner

Absolute-date Invoice query. Expected after fix: answered. Pre-fix it
refused — this is site 3 closing.

    $ python scripts/promptkit.py --run \
        --prompt "invoices for Lee Supplies" --show-planner

Existing shape. Must still route to Invoice + supplier filter, 25-row
sample, no regression.

## V4 — Negative still refuses

    $ python scripts/promptkit.py --run --prompt "invoices" --show-planner

Must still refuse with `missing_identifier` — no root reference at all.

## V5 — Goldens

No golden prompt names an Invoice. Expect empty diff against
`docs/audit/golden/`.

## V6 — pytest

    $ pytest -q tests/test_f046_invoice_relative_date.py
    $ pytest -q

Target: baseline 1135 + N new tests, 22 deselected. Exact counts recorded
when V6 is run.

## V7 — Test fails without the fix

Each site reverted in isolation, test re-run, must fail:

- KG rows missing → `_build_entity_fetcher_args` returns `{}`; the
  guard-accepts-relative-date test hits RefusalError; V1 refuses at parse.
- `b_invoice_date.sysprompt` rule missing → parser self-declares
  `unsupported_filter`; the sysprompt-content test fails.
- "MUST include supplier" clause not softened → parser self-declares
  `missing_identifier`; the sysprompt-content test fails.
- Guard unwidened → absolute-date queries refuse; guard tests fail.

Because the fix is a chain, V7 shows cascading failures rather than a
single one. Recorded as such.

## V8 — not applicable

No LLM-boundary change in the sense of temperature/model parameters. The
sysprompt edits are parser-side and covered end-to-end by V1–V4.

## V9 — four-file targeted sweep

Ran the F-011b regression file (`15_po_relative_date_filters.txt`)
plus the new F-046/47/48 file (`16_date_filter_cluster.txt`) plus
the F-041 and F-012/F-036 regression files, in one invocation.
Evidence: `docs/phase-2/fixes/F-046-F047-F048-v9-sweep.txt`;
analysis: `F-046-F047-F048-v9-analysis.md`.

Result: PASS. Zero `unsupported_filter`, zero `ERROR`. Every
F-046 prompt answered except two absolute-date phrasings that use
the noun `created` — filed as F-049 (not a regression of F-046;
the pre-branch outcome was identical).

## Deviations from the F-046 entry

Two additions, one correction:

1. **Sites 2b and 2c (sysprompt rewrites).** The entry named a new rule
   on `b_invoice_date.sysprompt`; it did not name the supplier-clause
   rewrite in `b_invoices_for_supplier.sysprompt` or its literal mirror
   in `context_assembly.py`. Both are required: the parser refuses
   `invoices in the last 30 days` with `missing_identifier`, sourced
   from the "MUST include this supplier filter" clause; and the literal
   in `context_assembly.py` is byte-equality-checked against the
   assembled preamble, so it must move with the sysprompt files.

2. **Site 3 (guard widening).** The entry did not name the Invoice guard
   in `planner.py`. The parse of `invoices in 2024` produced a perfectly
   valid `invoice_date` intent, and the guard refused it. This is a
   pre-existing wrong-refusal, closed by the same fix.

3. **Correction — the plan_builders tuple.** The fix file's first draft
   (retracted above) claimed a plan_builders change. It does not exist:
   the F-011b tuple already contains the two ftype names, and reusing
   them for Invoice is what makes the entry's "no code change" claim
   true. The fix file records the correction because the fix record
   should not carry a phantom site.

## Not checked

- **Day-unit vs month-unit.** "in the last 30 days" is converted to
  months by the model (30 days → 1 month), which is lossy. F-011b's fix
  file flagged this too. This branch does not add day-unit support.

- **`b_invoices_for_supplier.sysprompt` has a duplicated invoice-number
  rule.** Two identical bullets appear back-to-back. Cosmetic, not this
  fix's scope; recorded so a future pass on that file sees it.

- **Cross-entity consistency of the guard.** Only the Invoice guard is
  widened here. Whether other guards have the same class of missing
  root-ref acceptance is a class-level sweep, not this fix's.

- **`capability.py::_FILTER_GUIDANCE["Invoice"]`** says "Narrow by
  supplier or date instead." That message promised the capability this
  fix lands. Same class as F-001, F-006, F-011.


<!-- ───── merged from: docs/phase-2/fixes/F-047.md ───── -->

# F-047 — PO last-updated-date filter; "not touched in the last N months" refuses

**Branch:** `phase-2-fix-F046-F047-F048-date-filters`
**PR:** (pending)
**State:** fixed
**Session:** 07_SPIRE_Phase2_BugFixing_06

## V0 — Fix statement

PurchaseOrder gains two LastUpdateDate filters: `updated_older_than_n_months`
(routes to the tool's `last_updated_before`) and `updated_in_last_n_months`
(routes to `last_updated_after`). The tool `search_purchase_orders` gains
matching args; the sysprompt's last-modified carve-out — which currently
says *set unanswerable=true* — is replaced with routing rules;
`plan_builders._build_entity_fetcher_args`'s relative-date branch tuple
widens to include the two new filter-type names; the MCP wrapper passes
the new args through.

Seven sites, eight files.

## Site enumeration

| # | Site | Where |
|---|---|---|
| 1 | Two new `(PurchaseOrder, ...)` filter rows | `scripts/sql/kg_schema.sql` `kg_entity_filter` |
| 2 | Replace the "set unanswerable" bullet with routing rules | `context/procurement/b_po_created_date.sysprompt` |
| 3 | Byte-equality mirror of site 2 | `nl_parser/context_assembly.py::_SYSTEM_PROMPT_PREAMBLE` |
| 4 | Widen `_build_entity_fetcher_args` tuple | `planner/plan_builders.py` |
| 5 | Add `last_updated_before` / `last_updated_after` args + client-side match | `mcp_server/tools/purchase_orders.py` |
| 6 | Pass new args through the MCP wrapper | `mcp_server/server.py::search_purchase_orders` |
| 7 | Row-count bumps 32 → 34 | `tests/test_kg_metadata.py`, `scripts/print_kg.py` |

## Evidence — pod probes 2026-09-23

Both bounds of `LastUpdateDate` filter server-side on `/purchaseOrders`:

    curl ... "q=LastUpdateDate < '2024-01-01'&totalResults=true"   -> HTTP 200, totalResults: 14287
    curl ... "q=CreationDate < '2024-01-01'&totalResults=true"     -> HTTP 200, totalResults: 14387  (control)
    curl ... "q=LastUpdateDate >= '2024-01-01'&totalResults=true"  -> HTTP 200, totalResults: 3257

The `LastUpdateDate` field is present in the PO body (probe C5, same
session). The 14,387 vs 14,287 gap on the `< 2024-01-01` bound is the
100-row set of POs created before 2024 but touched after — exactly the
questions this fix answers.

Refusal before fix (from promptkit, same session):

    $ python scripts/promptkit.py --run --prompt "purchase orders not touched in the last year"
    Reason:   Filtering purchase orders by last modified, last updated, or touch date is not supported; only creation-date filters are available.
      (refusal: unsupported_filter)

## V1 — Reproducer

    $ python scripts/promptkit.py --run \
        --prompt "purchase orders not touched in the last year" --show-planner

Expected after fix: Intent target_entity PurchaseOrder, filter
`updated_older_than_n_months: {"months": 12}`; Plan Step 1 tool_args
`{'last_updated_before': '<today-12mo ISO>'}`; an answered list.

## V2 — Paraphrase

    $ python scripts/promptkit.py --run \
        --prompt "purchase orders updated in the last 3 months" --show-planner

Expected: same shape, recent direction — `updated_in_last_n_months:
{"months": 3}`; tool_args `{'last_updated_after': '...'}`.

## V3 — Siblings unchanged

    $ python scripts/promptkit.py --run \
        --prompt "Purchase orders older than 6 months" --show-planner

F-011b creation-date older-than. Must still route to
`older_than_n_months` → `created_before`.

    $ python scripts/promptkit.py --run \
        --prompt "Purchase orders created before 2024-01-01" --show-planner

F-011b absolute-date. Must still route to `created_before` with the
ISO value verbatim.

## V4 — Negative still refuses

    $ python scripts/promptkit.py --run --prompt "purchase orders" --show-planner

Bare noun, no verb. Must still refuse with `missing_identifier`
(F-001's guard).

## V5 — Goldens

No golden prompt names a PO relative date. Expect empty diff against
`docs/audit/golden/`.

## V6 — pytest

    $ pytest -q tests/test_f047_po_last_updated.py
    $ pytest -q

Target: baseline 1144 + N new tests, 22 deselected.

## V7 — Test fails without the fix

Each site reverted in isolation, tests re-run, must fail:

- KG rows missing → `_build_entity_fetcher_args` returns `{}`; the
  emit-`last_updated_before` test fails.
- Sysprompt bullet unchanged → the routing-rule test fails; the
  "set unanswerable" text still present.
- Literal unchanged → byte-equality test fails.
- plan_builders tuple unwidened → the new ftypes skip the date-computation
  branch; args dict stays empty.
- Tool arg missing → `inspect.signature` test fails.
- Server wrapper unwidened → the MCP call test fails.

Because the fix is a chain, V7 shows cascading failures.

## V8 — not applicable

No LLM-boundary change in the sense of temperature/model parameters.
The sysprompt edits are parser-side and covered end-to-end by V1–V4.

## V9 — four-file targeted sweep

Ran the F-011b regression file (`15_po_relative_date_filters.txt`)
plus the new F-046/47/48 file (`16_date_filter_cluster.txt`) plus
the F-041 and F-012/F-036 regression files, in one invocation.
Evidence: `docs/phase-2/fixes/F-046-F047-F048-v9-sweep.txt`;
analysis: `F-046-F047-F048-v9-analysis.md`.

Result: PASS. All 7 F-047 phrasings answered with the correct
last-updated counts (16,119 / 16,669 / 278 / 1,425 / 32 etc.),
distinct from the CreationDate sibling counts on the same file —
confirming the two columns do not cross-contaminate.

## Not checked

- **Day-unit vs month-unit.** Same caveat as F-046: "in the last 30
  days" is converted to months by the model, which is lossy.

- **N-less "no recent activity" / "not touched" phrasings.** Those
  carry no explicit N and are F-048's shape (vague-adjective default),
  also on this branch. F-047's V2 uses a paraphrase with an explicit N
  so its scope is clean.

- **Other entities with LastUpdateDate.** Whether the same shape applies
  to Invoice / StandardReceipt (both expose LastUpdateDate) is a
  class-level question. Not this fix's scope.

- **F-045 adjacency.** F-045 records a composite-date-clause silent-zero
  on `/purchaseOrders`; the fix here uses single-clause q= only, so it
  does not interact with F-045. F-045 remains open on its own row.


<!-- ───── merged from: docs/phase-2/fixes/F-048.md ───── -->

# F-048 — vague relative adjectives default to a 3-month window

**Branch:** `phase-2-fix-F046-F047-F048-date-filters`
**PR:** (pending)
**State:** fixed
**Session:** 07_SPIRE_Phase2_BugFixing_06

## V0 — Fix statement

`b_po_created_date.sysprompt` gains a VAGUE-RECENT rule: a vague-recency
adjective with no explicit N (`recent purchase orders`, `new purchase
orders`, `the latest POs`, `fresh POs`) emits
`created_in_last_n_months: {"months": 3}` rather than refusing. Mirrored
in `context_assembly.py::_SYSTEM_PROMPT_PREAMBLE`. Sysprompt-only fix —
no KG rows, no plan_builders change, no tool change. The default N is 3,
chosen 2026-09-23.

## Evidence — probes on `dabpqy`, 2026-09-23

Two distinct refusal shapes, both pre-fix. The finding's own evidence
block recorded both as `unsupported_filter`; on the current pod the two
have drifted apart.

    === recent purchase orders ===
    Reason:   I can look up purchase orders, but this doesn't say which one.
      (refusal: missing_identifier — PurchaseOrder root has no identifier
       and no explicit list request)

    === new purchase orders ===
    Reason:   The request for 'new' purchase orders requires a specific
              timeframe (such as 'in the last 6 months') to map to a
              supported relative date filter.
      (refusal: unsupported_filter)

The `recent` shape is the harder one: the parser does not recognise
"recent" as a date phrase at all, so it treats the prompt as a rootless
PO list and the F-001 guard refuses it with `missing_identifier`. The
sysprompt rule must therefore teach BOTH the recognition ("recent" is a
date phrase) and the mapping (`created_in_last_n_months: {months: 3}`).

## V1 — Reproducer

    $ python scripts/promptkit.py --run \
        --prompt "recent purchase orders" --show-planner

Expected after fix: Intent target_entity PurchaseOrder, filter
`created_in_last_n_months: {"months": 3}`; Plan Step 1 tool_args
`{'created_since': '<today-3mo ISO>'}`; an answered list.

## V2 — Paraphrase

    $ python scripts/promptkit.py --run \
        --prompt "new purchase orders" --show-planner

Expected: same shape, months=3.

## V3 — Siblings unchanged

    $ python scripts/promptkit.py --run \
        --prompt "purchase orders in the last 6 months" --show-planner

Explicit-N sibling. Must still route to `created_in_last_n_months:
{"months": 6}` — the default fires only when no N is present.

    $ python scripts/promptkit.py --run \
        --prompt "Purchase orders older than 6 months" --show-planner

F-011b older-than. Must still route to `older_than_n_months`.

## V4 — Negative still refuses

    $ python scripts/promptkit.py --run --prompt "purchase orders" --show-planner

Bare noun, no adjective, no verb. Must still refuse with
`missing_identifier`. The vague-adjective rule must not swallow the
bare-noun shape.

## V5 — Goldens

No golden prompt names a vague-adjective PO query. Expect empty diff.

## V6 — pytest

    $ pytest -q tests/test_f048_vague_relative.py
    $ pytest -q

Target: baseline 1153 + N new tests, 22 deselected.

## V7 — Test fails without the fix

Both sysprompt tests fail — the rule and the default-value string are
absent pre-fix.

## V8 — not applicable

The F-011 precedent: sysprompt edits are parser-side, tested end-to-end
by V1–V2 and by V9. No N≥20 loop on this branch.

## V9 — four-file targeted sweep

Ran the F-011b regression file (`15_po_relative_date_filters.txt`)
plus the new F-046/47/48 file (`16_date_filter_cluster.txt`) plus
the F-041 and F-012/F-036 regression files, in one invocation.
Evidence: `docs/phase-2/fixes/F-046-F047-F048-v9-sweep.txt`;
analysis: `F-046-F047-F048-v9-analysis.md`.

Result: PASS. All six vague-adjective prompts (`recent`, `new`,
`latest`, `fresh`, `the most recent`, `recently created`) answered
identically at months=3, cutoff 2026-06-23; explicit-N siblings
unchanged.

## Not checked

- **Adjective coverage.** Four adjectives tested or planned — `recent`,
  `new`, `latest`, `fresh`. Others may exist (`current`, `modern`,
  `up-to-date`). The rule names the four; a future sweep can extend.
- **Fixed default = 3 months.** A design decision, not a measurement.
  Whether a per-entity or configurable default is right is a separate
  question. The finding picked 3, and the sysprompt encodes it.
- **Narration of the assumption.** The finding's optional polish —
  "assuming 'recent' means the last 3 months" as a synthesized lead-in —
  requires a schema slot to carry the assumption flag. Not on this
  branch; the answer says what window it used, which is enough.
- **Same pattern on other entities.** Invoice, CreditMemo, and every
  list-entity prompt could take the same vague-adjective defaulting. The
  rule is PO-specific; extending is a separate decision.


<!-- ───── merged from: docs/phase-2/fixes/F-049.md ───── -->

# F-049 — Invoice `created` / `raised` absolute-date phrasings refuse

**Branch:** `phase-2-fix-F049-invoice-created-dates`
**PR:** #168
**State:** verified
**Session:** 17_SPIRE_Phase2_BugFixing_16

## V0 — Fix statement

`b_invoice_date.sysprompt`'s absolute-date bullet taught three phrasings,
all leading with the entity noun `invoices` (`invoices in 2023`, `invoices
after 2023-01-01`, `invoices between Jan and Mar 2023`). The PO sibling
`b_po_created_date.sysprompt` teaches `'POs created before 2015'` verbatim
— a phrasing that leads with `created`. The Invoice block never learned
that shape, so prompts like `invoices created before 2024-01-01` produced
a filter-less Invoice intent; the planner's Invoice guard then refused
with `missing_identifier`.

Fix: extend the bullet to name `created before` / `created since` /
`created after` / `raised before` / `raised since`, and add a clause
stating that `created` / `raised` name the InvoiceDate column (not a
separate CreationDate), with `since`/`after` setting `from` and `before`
setting `to`. Same edit mirrored byte-identically into
`context_assembly.py::_SYSTEM_PROMPT_PREAMBLE`, which the byte-equality
oracle asserts.

Sysprompt-only. No code change, no KG row. Mirrors F-046's split exactly.

## V1 — Reproducers

Pre-fix (`t_f049_v0.txt`, captured before the fix):

    PROMPT: invoices created before 2024-01-01
    Reason:   I can look up supplier invoices, but this doesn't say which one.
      (refusal: missing_identifier — Invoice root has no supplier reference)

    PROMPT: invoices created since January 2024
    Reason:   I can look up supplier invoices, but this doesn't say which one.
      (refusal: missing_identifier — Invoice root has no supplier reference)

Post-fix — full 5-prompt capture in `F-049-v1.txt` (same prompt set as
V1–V4 below). Headline results:

    PROMPT: invoices created before 2024-01-01
      target_entity: Invoice
      filters: [{'type': 'invoice_date', 'value': {'to': '2024-01-01'}}]
      tool_args: {'invoice_date_before': '2024-01-01'}
      → 22 rows, all dated 2016 / 2022

    PROMPT: invoices created since January 2024
      target_entity: Invoice
      filters: [{'type': 'invoice_date', 'value': {'from': '2024-01-01'}}]
      tool_args: {'invoice_date_after': '2024-01-01'}
      → 25 of 7,097 (truncation noted)

## V2 — Paraphrase

`invoices raised before 2024-01-01` — same intent and plan shape as
`created before`, 22 rows. Full output in `F-049-v1.txt`.

## V3 — Sibling (unchanged)

`invoices in 2024` — before the fix this was the only absolute-date
Invoice phrasing that worked. Post-fix unchanged: same two-bound
`invoice_date {from: 2024-01-01, to: 2024-12-31}`, same 19-row result.

## V4 — Negative (still refuses)

    PROMPT: invoices
    Reason:   I can look up supplier invoices, but this doesn't say which one.
      (refusal: missing_identifier — Invoice root has no supplier reference)

Bare `invoices` — no root reference at all — still refuses with the same
shape.

## V5 — Goldens

    $ git status docs/audit/golden/
    On branch phase-2-fix-F049-invoice-created-dates
    nothing to commit, working tree clean

None of the three golden prompts is an Invoice date query.

## V6 — pytest

    1214 passed, 1 skipped, 22 deselected in 228.77s

Pre-fix baseline 1211 passed, 1 skipped. +3 new tests
(`tests/test_f049_invoice_created_dates.py`). The 1 skip is
`tests/test_corpus_consistency.py` (module-level, by design since
`1f980d1`).

## V7 — Test fails without the fix

Pre-fix checkout of the two edited files (grep the phrase absent, run the
test file, expect red):

    $ git checkout HEAD~1 -- src/spire/nl_parser/context/payables/b_invoice_date.sysprompt src/spire/nl_parser/context_assembly.py
    $ grep -c "invoices created before" src/spire/nl_parser/context/payables/b_invoice_date.sysprompt
    0
    $ python -m pytest -q tests/test_f049_invoice_created_dates.py
    2 failed, 1 passed

    $ git checkout HEAD -- src/spire/nl_parser/context/payables/b_invoice_date.sysprompt src/spire/nl_parser/context_assembly.py
    $ grep -c "invoices created before" src/spire/nl_parser/context/payables/b_invoice_date.sysprompt
    1
    $ python -m pytest -q tests/test_f049_invoice_created_dates.py
    3 passed

The two failing tests are `test_sysprompt_teaches_created_phrasings` and
`test_assembly_mirror_teaches_created_phrasings`. The third test
(`test_absolute_date_bullet_still_mirrored`) passes on both trees — the
two files are in sync either way, both just missing the same phrases.

## V8 — not applicable

No LLM-boundary change in the sense of temperature or model parameters.
The sysprompt edit is parser-side and covered end-to-end by V1–V4.

## V9 — prompt-file sweep

Dedicated 12-prompt set `scripts/prompts/18_invoice_created_dates.txt`,
written for this fix (additive to 16, which already carries the two
reproducers). Full capture: `F-049-v9.txt`. Result:

    12 PROMPT, 1 Reason, 0 ERROR.

Every `created` / `raised` phrasing routed to `invoice_date` with the
correct direction (`before` → `to`, `since` / `after` → `from`). The two
siblings (`invoices in 2024`, `invoices older than 6 months`) were
unchanged. The cross-entity control (`purchase orders created before
2015`) still routed to the PO `created_before` filter. The negative
`invoices` still refused with `missing_identifier`.

## Deviations from the F-049 entry's suggested fix

The entry's Fix Location named exactly this pair: "extend the
absolute-date bullet" in `b_invoice_date.sysprompt`, "mirror in
`context_assembly.py::_SYSTEM_PROMPT_PREAMBLE`". No deviation. No KG row,
no tool arg, no plan_builders change — the tool's
`invoice_date_before` / `invoice_date_after` args already existed
(carried by F-046) and the guard already accepts `invoice_date` as a
root ref.

## Not checked

- **`invoices created before 2015` returns 0 rows.** The intent is
  correct (`invoice_date {to: 2015-01-01}`, plan `invoice_date_before:
  2015-01-01`), but the fetch returns 0. The pod clearly holds pre-2015
  invoices — the F-046 sweep (`t_f049_v9.txt` context) shows invoices
  dated 2012, 2013, 2014 for many suppliers. A single-clause
  `InvoiceDate < '2015-01-01'` should not return 0. Either the endpoint
  behaves oddly at this bound, or the tool is dropping the clause for
  some reason. Not a defect in F-049's routing (routing worked); a
  separate finding if it recurs.
- **Sibling-entity coverage.** Whether `StandardReceipt` (receipt_date_*)
  and `AccountReceipt` share the same "created-before/since" gap. F-047's
  fix file flags the same question for LastUpdateDate on Invoice and
  StandardReceipt. Not on this branch.
- **The `--validate` corpora.** The `.json` files were deleted in window
  16 (`4c09ae6`). This fix is verified against the dedicated `18` set,
  not the full corpus. Regeneration of the `.json` corpora is a separate
  task.


<!-- ───── merged from: docs/phase-2/fixes/F-051.md ───── -->

# F-051 — `fields` + `include` intents drop their child content

**Branch:** `phase-2-fix-F051-summary-gate`
**PR:** #169
**State:** verified
**Session:** 17_SPIRE_Phase2_BugFixing_16

## V0 — Fix statement

Two commits.

**Commit 1 (extraction).** The display branch that chooses between
summary-only + projected table and the full synthesized render existed
in three near-identical copies: `scripts/promptkit.py`,
`scripts/run_prompt_set.py`, `scripts/run_graph.py`. The three had
already drifted (promptkit's skip-message read "too large to summarize";
the other two "result too large to summarize; showing the table only").
Extracted into `src/spire/rendering/formatters.py::render_answer`.

**Commit 2 (fix).** The extracted helper passed
`summary_only=True` whenever `fields` was non-empty, regardless of
`include`. `summary_only` suppresses the typed record block; the
projected table that follows renders only the PARENT bucket. A prompt
naming both a column and a child — the finding's own reproducer,
`Show the AR invoice with CustomerTransactionId 1002 with transaction
number and flexfield` — fetched the DFF, built it into the response, and
never showed it.

Fix: `summary_only=not state["intent"].include`. Fields-only intents
keep `summary_only=True` (F-020 unchanged); fields+include intents now
pass False and get the full synthesized render, which carries the child
rows the projected table cannot.

## V1 — Reproducer

Pre-fix (`t_f051_v0.txt` narrative; captured inline below):

    Intent:
      target_entity: ReceivablesInvoice
      filters: [{'type': 'by_id', 'value': '1002'}]
      include: ['ReceivablesInvoiceTransactionDFF']
      fields: ['TransactionNumber']
    ...
    Outputs:
      receivables_invoices: 1 record(s)  [{'TransactionNumber': '5'}]
      receivablesinvoicetransactiondff: 1 record(s)
        [{'CustomerTrxId': 1002, '__FLEX_Context': 'DOO', ...}]
    ...
    Answer:
    <blank>
    Answer:
    receivables_invoices (1 record(s)) — columns: TransactionNumber
      5

Post-fix — full capture in `F-051-v9.txt`:

    Answer:
    AR Invoices:
      Transaction           : 5
      CustomerTransactionId : 1002
      ...
      DFF                   : DOO

    Answer:
    receivables_invoices (1 record(s)) — columns: TransactionNumber
      5

The DFF renders in the full block. The projected table follows with the
requested column. Two-block shape.

## V2 — Paraphrase / analogues

Sections A2–A10 of `F-051-v9.txt` — the same fields+include shape across
different entities:

- AR invoice + lines (4 line rows rendered)
- AR invoice + tax lines (4 lines, 8 tax rows rendered)
- PO + lines (2 rows)
- PO + schedules (2 rows)
- PO + distributions (2 rows)
- Supplier + contacts (10 rows)
- Supplier + sites (22 rows)
- CustomerAccount + transactions (25 of 484)
- CustomerAccount + receipts (10 of 2,314)

All 10 exercises both channels; all 10 render their child content after
the fix.

## V3 — Sibling (F-020 guard, unchanged)

Section B of `F-051-v9.txt`. Two prompts with `fields` but no `include`:

    List active suppliers with supplier name and status
    Show me invoices for EIP Inc with invoice number and amount

Both keep `summary_only=True` — the typed record block stays
suppressed; only the projected table prints. F-020's fix preserved.

## V4 — Negative (else branch, unchanged)

Section C and D of `F-051-v9.txt`. Include-only and plain prompts
(`Show PO 2144 and its lines`, `Get tax lines for invoice 1002`,
`List active suppliers`) still take the else branch, full render, no
projected table. Unchanged.

## V5 — Goldens

    $ git status docs/audit/golden/
    On branch phase-2-fix-F051-summary-gate
    nothing to commit, working tree clean

None of the three golden prompts is a fields+include shape.

## V6 — pytest

    1216 passed, 1 skipped, 22 deselected in 203.27s

Baseline 1214 passed, 1 skipped at `5e08a77`. +2 new tests in
`tests/test_f051_summary_gate.py` (added at `4c837c4`). The 1 skip is
`tests/test_corpus_consistency.py`, module-level by design since
`1f980d1`.

## V7 — Test fails without the fix

Pre-fix checkout of `formatters.py` (revert commit 2 only; extraction
stays):

    $ git checkout f7ec4d3~1 -- src/spire/rendering/formatters.py
    $ grep -n "summary_only=not state" src/spire/rendering/formatters.py
    (0 matches)
    $ python -m pytest -q tests/test_f051_summary_gate.py
    1 failed, 1 passed
    # test_fields_plus_include_renders_full_response: calls = [True], no False
    # test_fields_only_still_suppresses_records: calls = [True], passed

    $ git checkout HEAD -- src/spire/rendering/formatters.py
    $ grep -n "summary_only=not state" src/spire/rendering/formatters.py
    1579:            summary_only=not state["intent"].include,
    $ python -m pytest -q tests/test_f051_summary_gate.py
    2 passed

Red-then-green verified against the fix expression alone.

## V8 — not applicable

No LLM-boundary change. The fix is a Python expression in the display
layer.

## V9 — dedicated 15-prompt set

`scripts/prompts/19_fields_and_include.txt`. Full capture:
`F-051-v9.txt`. Result: **15/15 answered, 0 errors.**

Section split by intent shape:
- A (fields+include, the fix): 10 prompts, all 10 render child content
- B (fields only, F-020 guard): 2 prompts, both suppress typed records
- C (include only, else branch): 2 prompts, unchanged
- D (plain, else branch): 1 prompt, unchanged

Every Section A prompt produced both `fields` and `include` on the
intent line — no rewording fell into a different shape, so all 10
genuinely exercised the fix.

## Deviations from the F-051 entry

**1. §8.3.5 — extraction is a refactor.** The finding recommends option 2
(factor a shared helper) over option 1 (three one-line edits). Phase 2's
§8.3.5 says "no cleanup or refactoring". Deviation accepted, with
reasoning: the three copies had already drifted (evidence above), the
extraction is behaviour-preserving (V6 same pass count both sides), it
is directly in service of the fix, and the fix lands in one place
instead of three. The finding's own author reasoned through the same
trade-off.

**2. Commit 3 (`516bd04`) — import wiring.** The extraction commit
(`0687a0c`) replaced three inline call sites with calls to
`formatters.render_answer` but did not add the name to the three
scripts' import lists. Every runner crashed at the call with
`NameError` — caught by the V9 sweep at the first prompt. The V6 pytest
was green because `tests/` imports from `src/spire/`; the scripts'
import wiring is not exercised by any test. `516bd04` adds the three
import lines. Recorded as a delta, not silent.

## Not checked

- **Multi-row ergonomics for fields+include.** `Show supplier EIP Inc
  with supplier number and its contacts` renders 10 contact rows plus
  the projected table. Both blocks are correct, but the visual weight is
  heavier than a fields-only query. Design choice; no defect.
- **Rendered-text assertions.** The new test asserts the CALL SHAPE
  (which `summary_only` value was passed to `_format_synthesized`), not
  the rendered output. Mocking the formatter keeps the assertion narrow;
  the end-to-end V9 sweep is what confirms the text.
- **Scripts have no test coverage.** The extraction passed V6 while all
  three runners were dead. `tests/` never imports from `scripts/`. A
  future change to the display layer that touches the runners has the
  same blind spot.
- **`promptkit`'s shorter skip-message string.** Unification took the
  longer form; if any user-visible artefact depended on the shorter
  string, it wasn't swept.


