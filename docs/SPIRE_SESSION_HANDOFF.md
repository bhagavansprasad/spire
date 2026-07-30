# Spire — Session Handoff (2026-07-30, evening)

Paste the companion text into the new window to continue. Supersedes the
2026-07-30 morning handoff.

---

## Who / what

Continuing **Spire** — AI-native NL query over Oracle Fusion Cloud (P2P +
AR). Deterministic KG pipeline: parse → plan → execute → synthesize, two
LLM boundaries only (parser, synthesizer). Tool selection is a KG lookup,
not an LLM judgement. Not an agent architecture.

Repo `github.com/bhagavansprasad/spire`, working dir `~/pocs/spire`, pod
`fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com`, creds in
`personas.yaml` (gitignored).

**On `master`, clean, 607 tests passing.** Three branches merged this
session (details below); all three deleted locally after merge.

---

## What this session did

Two separate strands of work: the four Phase 0 defects the previous
handoff carried forward, and a maintainability refactor of the two
largest source files that was not part of any requirements phase —
initiated mid-session as its own goal, and treated with the same rigor
as feature work.

### Strand 1 — Phase 0: the four open defects, cleared

All four found by reading actual output last session; none produced a
wrong number.

| # | Defect | Fix |
|---|---|---|
| 1 | Risk-only question refused | One line + a standalone `RISK ON A PO IS SUPPORTED` block in the parser's PO LIFECYCLE section, mirroring the existing payment block |
| 2 | Non-existent PO rendered "cannot be determined" per leg | `build_lifecycle_response` branches on `found=False`: no legs, no setup notes, no stage. Display branches on empty `legs`, not on a stage string |
| 3 | Internal `SupplierId` leaked into prose | `NO INTERNAL IDENTIFIERS IN THE SUMMARY` standalone block added to the synthesizer's POLifecycle prompt |
| 4 | Terms note printed "differ from the site default (None)" | Gated on `setup.site_read`; an honest alternative sentence when the site couldn't be read |

Defects 2 and 4 are the same species — a null rendered as a statement —
and were fixed together in one branch, `phase-0-lifecycle-defects`.

**Five new tests**, all deterministic (no LLM, no pod): the `found=True`
case is tested alongside `found=False`, guarding the D1 tri-state trap
where branching on a leg's truthiness (rather than on `found`) would
silently empty a valid answer.

**Verified live, 31-prompt lifecycle set: 31/31, up from 30/31.** No
regressions on neighbouring routes or the three expected refusals.

**The stale-KG diagnostic baseline moved.** Defect 1 added ~140 tokens to
every lifecycle parse call. Old baseline ~8,671. **New baseline is a
range, ~8,805–8,819**, varying with question length — treat it as a
range, not a constant.

Merged to master as commit `b160104`'s successor (see `git log`).

### Strand 2 — maintainability refactor (not a requirements phase)

Initiated by explicit request mid-session: "any file beyond 600 lines,
split into two" — corrected during the work from a hard line-count rule
to a maintainability goal once it became clear a single file could need
five or six splits, not two. Two files done this session; two more
identified and parked.

**`synthesizer.py`: 3,056 → 491 lines**, split into nine sibling files,
branch `refactor-synthesizer-modules`:

| File | Lines | Contents |
|---|---|---|
| `constants.py` | 30 | `LIFECYCLE_SHAPE`, model config |
| `errors.py` | 31 | the three error types |
| `models_common.py` | 84 | shared sub-models, the two shared Field defs |
| `p2p.py` | 402 | Supplier/Invoice/PurchaseOrder/Address schemas + supplier-record builders |
| `ar.py` | 497 | ReceivablesInvoice/CustomerAccount/CreditMemo/StandardReceipt schemas |
| `aggregation.py` | 422 | ranking/count/comparison schemas + their deterministic builders |
| `prompts.py` | 418 | system-prompt preamble, per-entity blocks, prompt assembly |
| `validation.py` | 554 | `_collect_valid_ids` (the id fingerprint) + every validator + dispatch |
| `lifecycle.py` | 451 | Module 5 whole — models, builders, shape detector, validator, prompt text, all in one file |

`synthesizer.py` itself now holds only the two registries, two backward-
compat aliases, the two shared shape detectors, and `synthesize_response`.

**`planner.py`: 1,764 → 439 lines**, split into six sibling files,
branch `refactor-planner-modules`:

| File | Lines | Contents |
|---|---|---|
| `registries.py` | 222 | the nine v1 mapping tables |
| `kg_db.py` | 187 | Oracle connection + lazy-loaded, cached filter definitions |
| `models.py` | 159 | `Intent`, `Step`, the `Plan` alias |
| `lookup.py` | 288 | `find_entity`, `find_edge`, `find_pattern_for_filter`, `resolve_vocab` |
| `date_utils.py` | 50 | `_compute_date_n_months_ago` and its two helpers |
| `plan_builders.py` | 577 | everything `generate_plan` delegates to |

`planner.py` itself now holds only `generate_plan` and re-exports.

**Both refactors are organisation only — no behavioural change.**
Verified by:
- Byte-diffing extracted content (prompt text, registries, schema field
  sets) against the pre-refactor file.
- Real import tests against actual sibling modules, not stubs.
- Full test suite after each move: 607 passed both times.
- Live pod runs before and after each refactor, same prompt
  (`"What is the risk rating on PO 701337 and why?"`) — **token counts
  and the rendered answer were byte-identical** across both refactors.
  The refactor moved zero tokens.
- The synthesizer split additionally verified with the 31-prompt
  lifecycle set: 31/31, matching the post-Phase-0 baseline, Phase 0's
  fixes (no leaked ids, no "site default (None)") spot-checked intact.
- The planner split additionally re-ran the same 31-prompt set after
  merge: 31/31 again, including the planner-guard refusal on "Open POs
  for supplier JGA" — the exact case a prior session found as a hard
  blocker in this code, still routing correctly.

**Two near-misses during the synthesizer split, both caught by pytest,
not by inspection:**
1. `_direction_phrase` — used directly by `tests/test_compare_orders_to_invoices.py`
   but missed by a grep that only covered uploaded files, not the whole
   repo. Fixed by re-running the grep against the actual `tests/` tree.
2. `validation.py` used `LIFECYCLE_SHAPE` inside `_collect_valid_ids`
   without importing it. The standalone import test exercised that
   function with a supplier-shaped record only, never a lifecycle-shaped
   one — so the module imported cleanly and still failed at runtime on a
   branch nobody had hit. Caught by the full pytest run.

**Lesson applied successfully on the very next split (planner):**
enumerated the complete external contract *before* extracting anything —
grepped `from spire.planner.planner import` across `tests/`, `src/`, and
`scripts/`, then paged through every multi-name import block by hand
(`test_planner.py` alone names 21 distinct symbols). Zero import failures
resulted. Direct cause-and-effect from the synthesizer near-misses.

### Not started this session

**`src/spire/mcp_server/tools/po_lifecycle.py`** (993 code lines) —
mapped into four layers (constants, async I/O fetchers, pure
data-shaping/reconciliation functions, judgement functions for
stage/team/risk/action) plus the orchestrator. The full external contract
was gathered (`tests/test_po_lifecycle_tool.py` and
`test_tools/try_po_lifecycle.py` between them import 25 names). Not yet
extracted — parked when the session's priority shifted.

**`src/spire/mcp_server/server.py`** (1,052 code lines) — mapped: 33
registered `@mcp.tool()` wrappers (its own module docstring is stale and
only lists 19 — a small, unfixed documentation gap, noted not chased).
They group cleanly into the same P2P/AR/aggregation/comparison/lifecycle
lines `synthesizer.py` already split on (12/11/6/3/1). **This one is not
a pure file-move**: every tool is registered against one shared
`mcp = FastMCP("spire")` instance created in this file. Splitting
registration into domain files requires pulling `mcp` and `_persona` into
a small `core.py`, then having each domain file import it and register
its own tools — `server.py` then imports every domain file *for the side
effect of registration*, nothing calls them directly. Proposed layout
(`core.py`, `register_p2p.py`, `register_ar.py`, `register_aggregation.py`,
`register_comparison.py`, `register_lifecycle.py`, slimmed `server.py`)
was presented and not yet approved. **Needs a decision on the
registration pattern before any code is written**, not just a mechanical
split.

---

## Numbers to carry forward

| Metric | Before this session | After this session |
|---|---|---|
| Tests passing | 602 | **607** |
| Lifecycle 31-prompt set | 30/31 | **31/31** |
| Parse tokens (lifecycle path) | ~8,671 | **~8,805–8,819** (range, from Phase 0 defect 1 only — unaffected by either refactor) |
| `synthesizer.py` | 3,056 lines | **491 lines** (+ 9 sibling files) |
| `planner.py` | 1,764 lines | **439 lines** (+ 6 sibling files) |

The requirements document's §3 baseline table (16.0s mean wall-clock,
12,230 mean tokens, measured 2026-07-29) is **unchanged by anything in
this session** — both refactors were proven token-identical, and Phase 0
only moved the parse-side figure, not the measured performance baseline
PRF-07/PRF-08 target against. No re-derivation needed yet.

---

## Status against `docs/spire_enhancement_requirements.md`

**Phase 0 (the four defects, not in the requirements doc): done, merged.**

**Phase 1 (UX-05, OBS-01, OBS-02— quiet default output, per-component
debug flags, config precedence): NOT STARTED.** This is the actual next
step in the governing plan. Nothing this session touched it.

**Phases 2–12: not started**, unchanged from the plan's own sequencing.

**The synthesizer and planner refactors are orthogonal to this document**
— not a requirement, not a phase, and should not be read as partial
progress on any specific item. Worth naming one adjacency directly:
**PRF-01 ("deterministic response construction across all shapes")**
will now be easier to implement precisely because response-building code
already lives in per-domain modules (`p2p.py`, `ar.py`, `aggregation.py`,
`lifecycle.py`) rather than scattered across one 2,452-line file. That is
a side effect, not a claim that PRF-01 is underway.

**DEC-01, DEC-02, DEC-03 — untouched, no new information.**

**One new pending decision, same shape as DEC-01–03:** how `server.py`'s
tool registration should be organised (see "Not started this session"
above). Proposed resolution: `core.py` + domain-grouped `register_*.py`
files, imported by `server.py` for side effect. Not yet decided.

---

## Carried forward — still open

Unchanged from the previous handoff unless noted.

**Can put a wrong number in front of someone**

- **Invoice total over a sample.** "invoices for Lee Supplies" states a
  total summed over 25 of 1,343 rows as fact.
- **"Country" returns a full address.**
- **Only the FIRST address is shown**, silently, for suppliers with many.
- **`StandardReceipt` and `AccountReceipt` model the same receipts** with
  disagreeing counts, and both are routable.

**Pinned bugs**

- **`search_standard_receipts` can never report `truncated=True`.**
- **W7 — "supplier sites" mis-parses as addresses.**

**Housekeeping**

- **17 tests are DESELECTED** by a marker filter nobody has examined.
- Address flattening exists twice. (Note: `_address_info` moved from
  `synthesizer.py` to `p2p.py` this session — same duplication, new
  location, not fixed.)
- **Remote branch prune still pending.** Three feature branches were
  deleted *locally* after merging this session
  (`phase-0-lifecycle-defects`, `refactor-synthesizer-modules`,
  `refactor-planner-modules`); the remote copies on GitHub have not been
  deleted. ~31 remote branches total, most merged — worth a prune pass.

---

## Hard-won lessons (carried + new)

**Curl before code.** Unchanged, not exercised this session (no pod-side
work).

**A grep across uploaded files is not a grep across the repo.** Both
synthesizer near-misses came from checking only the files that had been
shared, not the actual `tests/` directory. The fix each time was running
the grep against the real tree and reading every multi-name import block
in full — not summarising it.

**Enumerate the full external contract before extracting, not after.**
Confirmed as a working practice on the planner split: zero import
failures, versus two on the synthesizer split where this step was done
incompletely.

**A module importing cleanly does not mean every branch inside it is
correct.** The `LIFECYCLE_SHAPE` miss survived a real (non-stub) import
test because that test happened to exercise `_collect_valid_ids` with a
supplier-shaped record, never a lifecycle-shaped one. The generalised
version of "a claim from inspection is not a finding": a claim from *one
successful import* is not a finding either, if the code path that matters
wasn't the one exercised.

**Byte-diff extracted content, don't just re-import it.** Applied to
prompt text, registries, and schema field-sets on both refactors. Found
nothing wrong this time, but is now the standard bar for any future
split — an import test proves the names resolve; a byte-diff proves the
content wasn't altered in transcription.

**A stated rule should be corrected the moment it stops fitting, in the
open.** "Split any file over 600 lines into two" was corrected mid-session
to "split for maintainability, aiming under ~600" once `synthesizer.py`
turned out to need five splits, not two. Said so directly rather than
quietly doing five splits under a rule that promised two.

---

## Reference

- KG rebuild: `python scripts/rebuild_kg.py` — always from scratch.
- **Restart the MCP server after ANY change under `src/spire/mcp_server/`.**
  This applies with extra force to a future `server.py` split, which
  touches the whole directory's shape.
- Standalone tool runner: `python test_tools/try_po_lifecycle.py 701337
  162034`.
- Full suite: `python -m pytest -q` — 607 passed, 17 deselected, 1
  xfailed is the current clean baseline.
- Lifecycle regression: `python scripts/run_prompt_set.py --prompt-file
  scripts/prompts/08_lifecycle.txt` — 31/31 is the current clean baseline.
- Pod quirks: see `docs/spire_fusion_endpoints_reference.md` — nothing
  new added this session.

**Files to share when starting the next task:** this handoff,
`docs/spire_enhancement_requirements.md` (the governing plan — Phase 1 is
next), plus the code files the task touches. If resuming the `server.py`
question specifically, share `src/spire/mcp_server/server.py` fresh
rather than working from anything pasted earlier in a prior session —
every file in this project drifts between sessions and re-sharing is the
standing rule, not an exception.
