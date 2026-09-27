# SPIRE — Phase 2 — Correctness

**Session log for Phase 2** (Doc A §8).
**Index:** `00_Doc_B_Index.md` in this folder.
**Newest session at the top.** Append-only within the phase. When Phase 2
ends, this file is frozen and `03_Phase_03_Consistency.md` opens.

**Note on S-numbering and Phase 2's window labels.** Phase 2's work has
run across sixteen windows labelled `07_SPIRE_Phase2_BugFixing_01`
through `16_SPIRE_Phase2_BugFixing_15` — the label is the one written in
each fix file's header. Those window labels are separate from Doc B's
`S###` session IDs. The entries below are `S004` and `S003` (the fourth
and third Doc B sessions); `S003` sits after thirteen Phase 2 windows
(01–13) whose forensic record lives in `FIX_PLAN.md` §5 and the per-fix
files under `docs/phase-2/fixes/`, not in Doc B. That gap is deliberate, not a
backlog: those sessions' summaries were not written at the time, and
back-filling them now would produce entries nobody wrote. `FIX_PLAN.md`
§5 is the live Phase 2 ledger — it names every row, its state, and its
PR, and it is the resume reference for a new window.

---

### S004 — 2026-09-24 — Phase 2: F-003 / F-050 / F-004 (`_TIER1` reaches `modes/` + `columns/`)

**Window label:** `16_SPIRE_Phase2_BugFixing_15`
**Phase:** Phase 2 — Correctness (Doc A §8)
**Branch:** `phase-2-fix-F003-modes-reachable`
**Session goal:** Close F-003 (`modes/` unreachable from a router-scoped
parse). F-050 and F-004 landed on the same line; the session became a
three-finding close on one edit.
**Outcome:** completed.

**Inputs received this session:**
- `plan` context bundle (audit, findings log, FIX_PLAN, fix files, goldens,
  WORKING_STYLE, SESSION_HANDOVER).
- `parser_planner` context bundle.
- `parser_context` context bundle (manifest, `modes/`, `columns/` blocks).
- `WORKING_STYLE.md`.

**Outputs:**
- `_TIER1` extended in `src/spire/nl_parser/context_assembly.py`:
  `("core", "refusals", "modes", "columns")`.
- The two op registries brought back into sync both directions:
  `modes/m_aggregation.sysprompt` gains `top_invoices_by_amount`;
  `draft.py`'s `DraftAggregate.op` description gains the three PO ops.
- `_SYSTEM_PROMPT_PREAMBLE` byte-equality oracle extended to match.
- `tests/test_f003_modes_reachable.py` — 4 assertions.
- Three findings closed: F-003, F-050, F-004.
- `WORKING_STYLE.md`: rule 15.3 added; rule 15.1 tightened.
- `scripts/prompts/*.json` deleted (13 files) — recorded metadata stale
  by construction after a scoped-parse change.
- Doc B refresh (this entry; index §1 snapshot; index §4 pointer).

---

#### Work items

##### WI-S004-01 — F-003: `modes/` reachable from a router-scoped parse

| Field | Value |
|---|---|
| Type | missing-capability |
| Test kind(s) | unit, manual probe |
| Doc A reference | §8.3 |
| Bug ID | — |
| Investigation ID | — |
| State | fixed |

**Objective.** `_TIER1` named only `("core", "refusals")`.
`assemble_subset` loads `set(_TIER1) | set(modules)`, so `modes/` and
`columns/` were unreachable from every router-scoped parse. Three PO
aggregation ops (`po_value_by_supplier`, `po_count_by_status`,
`open_po_summary`) lived only in `modes/m_aggregation.sysprompt`; the
parser either refused or reached for the nearest visible op in a
different block.

**Fix.** Four source files, one test file.

- `src/spire/nl_parser/context_assembly.py` — `_TIER1` gains `"modes"`
  and `"columns"`. `_SYSTEM_PROMPT_PREAMBLE` oracle literal gains the
  `top_invoices_by_amount` bullet to match the modes edit.
- `src/spire/nl_parser/context/modes/m_aggregation.sysprompt` — gains
  the `top_invoices_by_amount` bullet.
- `src/spire/nl_parser/draft.py` — `DraftAggregate.op` description
  gains the three PO ops.
- `tests/test_f003_modes_reachable.py` — 4 tests (reachability × 2,
  op-set equality, `_TIER1` content).

**Verification.** Full V-standard in `docs/phase-2/fixes/F-003.md`.
Key results: V1 sweep (`F-003-v1-sweep.txt`, 10 prompts) — three
reproducers and two paraphrases route to the intended ops. V3 sibling
`top 10 suppliers by spend in 2022` unchanged (`by_supplier`). V4
negative `suppliers with net 30 payment terms` still refuses
`unsupported_filter`. V6 `pytest -q` 1214 passed. V7 red (4 failed)
pre-fix, green (4 passed) post-fix. V8 single-pass `F-003-v8-sweep.txt`
— 3 prompts, correct op each, 0 refusals, 0 compare fallbacks.

**Files touched.**
- `src/spire/nl_parser/context_assembly.py`
- `src/spire/nl_parser/context/modes/m_aggregation.sysprompt`
- `src/spire/nl_parser/draft.py`
- `tests/test_f003_modes_reachable.py`
- `docs/phase-2/fixes/F-003.md`
- `docs/phase-2/fixes/F-003-v1-sweep.txt`
- `docs/phase-2/fixes/F-003-v8-sweep.txt`

**Commits.**
- `98bd6d9` — F-003 / F-050 / F-004: load `modes/` and `columns/` from a
  router-scoped parse

**Cross-references.** Audit row B-20; findings-log F-003; FIX_PLAN §5.

---

##### WI-S004-02 — F-050: `columns/` reachable from a router-scoped parse

| Field | Value |
|---|---|
| Type | missing-capability |
| Test kind(s) | unit |
| Doc A reference | §8.3 |
| Bug ID | — |
| Investigation ID | — |
| State | fixed |

**Objective.** The same `_TIER1` gap kept both `columns/` blocks
unreachable — `b_who_columns.sysprompt` and `b_column_fields.sysprompt`.
A column request like "supplier name and country" was not recognised
as one.

**Fix.** Same edit as WI-S004-01 — `"columns"` is the second name added
to `_TIER1`. No separate code change.

**Verification.** `tests/test_f003_modes_reachable.py::
test_scoped_parse_loads_columns_content` — red pre-fix, green post-fix.
Byte-equality oracle (5 passed) confirms the `_SYSTEM_PROMPT_PREAMBLE`
literal still matches the assembled preamble.

**Cross-references.** Findings-log F-050; FIX_PLAN §5.

---

##### WI-S004-03 — F-004: PO-value ranking routes to the aggregation op

| Field | Value |
|---|---|
| Type | wrong-data |
| Test kind(s) | manual probe |
| Doc A reference | §8.3 |
| Bug ID | — |
| Investigation ID | — |
| State | fixed (side-effect) |

**Objective.** `top 5 suppliers by purchase order value` misrouted to
the comparison op `top_suppliers_invoiced_vs_ordered` — a superset of
the question, because the correct aggregation op was invisible.

**Fix.** Same edit as WI-S004-01 — with `modes/` loaded, the model sees
`po_value_by_supplier` and picks it. No separate code change.

**Verification.** V1 sweep shows `aggregate.op = 'po_value_by_supplier'`;
V8 sweep shows 0 compare-block fallbacks across three prompts.

**Cross-references.** Findings-log F-004; FIX_PLAN §5.

---

#### Phase status update

- FIX_PLAN §5: F-003 → `fixed | — | 2026-09-24`;
  F-004 → `fixed | — | 2026-09-24`;
  F-050 → `fixed | — | 2026-09-24`.
- Audit §B.6: `B-20 | F-003 / F-004` → `verified 2026-09-24`.
- Fix file `F-003.md`: State → `fixed`.
- Doc B index §1 snapshot refreshed; §4 pointer added.

#### Blockers / open questions

- **`--validate` not run this session.** The fix intentionally changes
  what a scoped parse sees, so a full `--validate` against pre-fix
  metadata would false-positive on every aggregation prompt. The
  `scripts/prompts/*.json` corpora were deleted on the same branch for
  the same reason. Regeneration is a separate task.
- **The runtime clone needs a deliberate update.** `_TIER1` change
  affects routed parses, so the tester runtime at
  `~/pocs/spire-runtime` will not see the fix until it pulls
  `hardening-master` after this PR merges.
- **Cost of the fix.** Every routed parse now carries both `modes/` and
  `columns/` blocks. On the S003 snapshot, `count of suppliers` parsed
  at `in=3330`; on this session's V6 goldens, the same prompt parses at
  `in=5751`. Roughly +2.4k tokens per routed parse. Not measured
  per-prompt against the parser's token ceiling.

#### Next session should

- Read `FIX_PLAN.md` §5 — the live ledger — not this file.
- Take **F-049** (Cluster 4b, absolute-date Invoice phrasings
  `created before/since X` refuse). Sysprompt-only, mirrors F-046's
  split; V9 deferred until the corpora are regenerated.

#### Commits on branch

- `98bd6d9` — F-003 / F-050 / F-004: load `modes/` and `columns/` from a
  router-scoped parse
- `a672398` — working style: rules 15.1 tightened and 15.3 added
- `4c09ae6` — scripts/prompts: delete recorded-metadata `.json` corpora
- `9d1bfe0` — tracking: close F-003 / F-004 / F-050 in FIX_PLAN,
  findings log, audit

---

### S003 — 2026-09-24 — Phase 2: F-016 (plain-list row cap)


**Window label:** `15_SPIRE_Phase2_BugFixing_14`
**Phase:** Phase 2 — Correctness (Doc A §8)
**Branch:** `phase-2-fix-F016-list-cap` (merged via PR #166)
**Session goal:** Close F-016 — the plain-list row cap ("top 5 recent
credit memos") was dropped at parse and the fetcher's default 25 applied.
**Outcome:** completed.

**Preceded by — ledger drift closed.** The first work of this window was
not F-016 but a ledger reconciliation. PR #163 (F-011 / F-018 / F-019)
had merged 2026-09-23, but three `FIX_PLAN` §5 rows still read
`fixed | —`, and following the flip eight more rows in the audit's §B.6
map (B-01, B-02, B-03, B-04, B-05, B-19, B-27, and the three named)
were still at bare `fixed` from PRs #149–#161. Closed as `1efef7f` with
two permanent anti-drift rules: `WORKING_STYLE.md` rule 16 ("every
window opens with a ledger reconciliation") and the `fixed` /
`verified` split in `AUDIT_AND_FIX.md`'s "How to track" table.

**Inputs received this session:**
- `plan` context bundle (audit, findings log, FIX_PLAN, fix files, goldens).
- `parser_planner` context bundle.
- `mcp_server_tools` context bundle.
- `WORKING_STYLE.md`.

**Outputs:**
- Ledger drift closed (`1efef7f`), pushed.
- F-016 fixed, verified, merged as PR #166 (`1803485`).
- `docs/phase-2/fixes/F-016.md` written and frozen at `closed`.
- Doc B refresh (this file; index §1 snapshot; index §4 pointer) —
  the fourth tracking place, whose absence the ledger-drift commit did
  not itself close.

---

#### Work items

##### WI-S003-01 — F-016: plain-list row cap reaches the fetcher

| Field | Value |
|---|---|
| Type | feature (missing-capability) |
| Test kind(s) | unit, manual probe |
| Doc A reference | §8.3 |
| Bug ID | — |
| Investigation ID | — |
| State | verified |

**Objective.** The parser had no slot for a plain-list row cap —
`DraftIntent` carries none, `Intent` carries none — so a prompt like
`List recent credit memos, top 5` produced a filter-less `CreditMemo`
intent and `list_receivables_credit_memos`'s default `limit=25` applied.
The `5` never left the prompt.

**Reproducer (pre-fix).** Command and output are in
`docs/phase-2/fixes/F-016.md` §V1. Summary: `tool_args: {}`, 25 records,
`Showing 25 of 2,247`.

**Investigation.** The F-016 entry named two candidate fixes. Read
against the two context bundles:

1. Add a `DraftIntent.list_limit` field plus a sysprompt rule. Works,
   but hits the parser prompt's token ceiling (F-018's fix file
   records the ceiling as measured). Rejected.
2. Post-parse deterministic extraction in `parser.py` — the established
   pattern (`_is_explicit_po_list`, `_extract_invoice_number`,
   `_is_all_digit_customer_value`, `_has_country_column_phrasing`).
   Adopted.
3. A refinement the entry left open: the injection must be guarded.
   A `limit` sent to a fetcher whose MCP signature lacks one raises at
   the boundary (FastMCP/Pydantic rejects the unknown kwarg). A set
   (`_LIMIT_CAPABLE_TOOLS`) lives in `registries.py`, beside the
   existing `_TOOL_PRIMARY_ARG`.

**Fix.** Five source files, one test file.

- `src/spire/planner/models.py` — `Intent.list_limit: int | None = None`.
- `src/spire/nl_parser/parser.py` — `_extract_list_cap(prompt)`, two
  anchored regexes (`top|first|last N`; `N biggest|largest|most recent`),
  a time-unit guard so `in the last 5 months` is not a cap, and a call
  site in `parse()` gated on `aggregate is None and compare is None and
  not count_only and not balance_only`.
- `src/spire/planner/registries.py` — `_LIMIT_CAPABLE_TOOLS` (frozenset
  of six entity-level list fetchers whose signatures accept `limit`).
- `src/spire/planner/plan_builders.py` — `_apply_list_limit` helper.
- `src/spire/planner/planner.py` — Block 1 call site.
- `tests/test_f016_list_cap.py` — 29 tests.

**Verification.** Full V-standard in `docs/phase-2/fixes/F-016.md`.
Key results: V1 `tool_args: {'limit': 5}` / 5 records; V3 sibling
unchanged at `{}` / 25 records; V4 aggregate negative carries `top_n`
with no `limit`; V5 goldens empty; V6 1210 passed / 22 deselected
(baseline 1181 + 29 new); V7 collection `ImportError` pre-fix.

**Files touched.**
- `src/spire/planner/models.py`, `src/spire/planner/registries.py`,
  `src/spire/nl_parser/parser.py`, `src/spire/planner/plan_builders.py`,
  `src/spire/planner/planner.py`
- `tests/test_f016_list_cap.py`
- `docs/phase-2/fixes/F-016.md`

**Commits.**
- `d5112ec` — F-016: plain-list row cap ("top 5") reaches the fetcher
- PR #166 → squash `1803485` on `hardening-master`

**Cross-references.** Audit row B-26; findings-log F-016; FIX_PLAN §5.

---

#### Phase status update

- FIX_PLAN §5: F-016 → `verified | #166`.
- Audit §B.6: `B-26 | F-016` → `verified 2026-09-24 (#166)`.
- Fix file `F-016.md`: State → `closed`.
- Doc B index §1 snapshot refreshed; §4 pointer added for sessions 3–13.

#### Blockers / open questions

- **Doc B had been stale since S002.** The index snapshot read
  `2026-09-15 / S002 / Phase 1` until this commit — nine days and
  fifteen windows behind. Refreshed here.
- **The handover is stale.** `docs/spire-robustness/SESSION_HANDOVER.md`
  is dated `2026-09-17`, still frames Phase 1 as open, and names the
  findings log as "F-001 through F-005" (it now reaches F-051). Refresh
  is a separate task, not part of this commit — the handover carries
  more than a snapshot and its refresh should be deliberate.
- **Path discrepancy to reconcile.** The session-start instruction names
  `docs/SPIRE_SESSION_HANDOFF.md`; the file that exists is
  `docs/spire-robustness/SESSION_HANDOVER.md`. Same class of drift the
  audit exists to enumerate.

#### Next session should

- Read `FIX_PLAN.md` §5 — the live ledger — not this file.
- Take **F-003** (Cluster 5, `modes/` folder unreachable from a
  router-scoped parse). F-004 may fall out of the same fix; §4 records
  the dependency.

#### Commits on branch

- `d5112ec` — F-016: plain-list row cap ("top 5") reaches the fetcher
- PR #166 merged; branch deleted.

---

*End of Phase 2 file.*
