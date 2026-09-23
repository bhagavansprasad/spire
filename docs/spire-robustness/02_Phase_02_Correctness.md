# SPIRE — Phase 2 — Correctness

**Session log for Phase 2** (Doc A §8).
**Index:** `00_Doc_B_Index.md` in this folder.
**Newest session at the top.** Append-only within the phase. When Phase 2
ends, this file is frozen and `03_Phase_03_Consistency.md` opens.

**Note on S-numbering and Phase 2's window labels.** Phase 2's work has
run across fifteen windows labelled `07_SPIRE_Phase2_BugFixing_01`
through `15_SPIRE_Phase2_BugFixing_14` — the label is the one written in
each fix file's header. Those window labels are separate from Doc B's
`S###` session IDs. The entry below is `S003` (the third Doc B session,
after `S002`); it sits after thirteen Phase 2 windows (01–13) whose
forensic record lives in `FIX_PLAN.md` §5 and the per-fix files under
`docs/phase-2/fixes/`, not in Doc B. That gap is deliberate, not a
backlog: those sessions' summaries were not written at the time, and
back-filling them now would produce entries nobody wrote. `FIX_PLAN.md`
§5 is the live Phase 2 ledger — it names every row, its state, and its
PR, and it is the resume reference for a new window.

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
