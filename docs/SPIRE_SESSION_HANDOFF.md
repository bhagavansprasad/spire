# SPIRE — Session Handoff, 2026-09-24 (window 18)

**This file supersedes the window-17 handoff.** Window 18 closed the
last two Phase 2 rows: F-045 (PR #170, `f77a093`) and Reg #30 (closed
as not-a-bug). The Phase 2 ledger is now 24/24 — every row `verified`,
`closed`, or `closed-as-not-a-bug`. Phase 3a opens next window.

**Read this first.** Then `docs/AUDIT_AND_FIX.md` (the playbook), which
points to everything else. The `plan` context bundle (once regenerated)
carries this file plus everything referenced below.

---

## Where we are

**Branch:** `hardening-master` at `018f31a`.

**Test suite:** 1229 passed, 1 skipped, 22 deselected (measured
2026-09-24, post-F-045; verify at window open).

**Pod:** `dabpqy`.

**Ledger state — FIX_PLAN §5:** every row closed. The last two:

- `verified | #170 | 2026-09-24`: F-045.
- `closed-as-not-a-bug | — | 2026-09-24`: Reg #30.

Everything before window 18 shipped under earlier windows. Full ledger
in FIX_PLAN §5; the F-045 and Reg #30 closure narratives are in §4.1
and §5 respectively.

---

## What shipped in window 18

- **PR #170** (`f77a093`) — F-045. Two parts, both in
  `src/spire/mcp_server/tools/purchase_orders.py`:
  1. **Priority reorder** — `created_since` above `created_before`
     in the server-clause chain. With both bounds set, the chain had
     been picking `created_before` (the wrong bound for a range query).
  2. **`orderBy=CreationDate:asc`** on the `created_since` branch.
     Picking the right clause was not sufficient — the pod's default
     physical scan on `/purchaseOrders` starts at the far end of the
     collection, so `q=CreationDate >= '2023-01-01'&limit=200` returned
     rows beginning **2024-07-01** without an orderBy. Pinning the
     order puts the window at the range's lower edge.
  New regression test `tests/test_f045_created_since_priority.py`
  (13 tests; 3 red pre-fix, 10 both-trees-pass guards). Full V-standard
  in `docs/phase-2/fixes/F-045.md`; prompt-kit capture in
  `docs/phase-2/fixes/F-045-v1v4.txt`.

- **Reg #30 — closed as not-a-bug.** The entry's specific claim
  (top-N compare fetches the entire PO universe → pod timeout at
  145.7s) does not reproduce. Reproducer completes in **5m19s** with
  exit 0, returns a correct three-supplier comparison, and the
  per-supplier fetches are bounded. Residual 5m19s latency is real
  (~104 sequential HTTP calls) but is a Phase 6 subject — see
  FIX_PLAN §4.1 for the closure and the Phase 6 anchor-case note.
  Evidence: `docs/phase-2/fixes/Reg-30-v1-repro.txt`.

- **`docs/spire_fusion_endpoints_reference.md`** — three new
  `/purchaseOrders` discovery rows added during the F-045 probe (see
  "Two pod facts to know" below). Commit `2573e3c`.

- **Post-merge bookkeeping** — `6d5f76a` (F-045 → verified), `97bed63`
  (Reg #30 closure), `4b3737c` (Reg #30 evidence), `8012b1b` (Doc B
  index snapshot), `88a07c6` (Doc B index pointer row), `e887795`
  (handover rewrite), `018f31a` (context_bundles additions).

- **`WORKING_STYLE.md` unchanged** — no rule additions this window. One
  clarification worth carrying forward, recorded in the V7 procedure
  below: `git stash` does NOT stash a committed change; a V7 against a
  committed fix needs `git checkout HEAD~1 -- <path>` and
  `git checkout HEAD -- <path>`.

---

## Two pod facts to know before touching a date-bounded fetch

Both discovered by the F-045 probe (2026-09-24, `dabpqy`), both now in
the endpoints reference:

1. **Composite `q=` on `/purchaseOrders` returns HTTP 400, not
   silent-zero.** Different family member from F-012's `/invoices`
   falsifier (which returned 200 with `totalResults: 0`). The tool
   never sends a composite; this is documented so a future debugger
   does not assume the silent-zero shape applies here.

2. **The default physical scan order is not stable across query
   shapes.** `q=CreationDate >= '2023-01-01'&limit=200` returned rows
   beginning 2024-07-01. The same clause with `fields=` OR with
   `orderBy=CreationDate:asc` returned rows beginning 2023-01-11.
   **`orderBy=CreationDate:asc` composes with `q=` and is the stable
   sort key for a date-bounded fetch on that field.** Sort-key
   stability is **field-specific**: `LastUpdateDate >=` does NOT need
   it (the default scan for that field already starts at the range's
   lower edge). Verify per field.

---

## Next action — Phase 3a opens

**Phase 3a — Prompt coverage validation** (Doc A §9.3.1).

> **Objective.** Add a test that fails when the KG declares an entity,
> filter, or field that the parser prompt does not cover.

> **Design.** New test reads `kg_entity` (and `kg_entity_filter`,
> `kg_entity_field`) via `load_kg_menu()`, then asserts every entity
> name appears in the assembled parser prompt; then similar for
> filters and fields.

> **Acceptance.** The test passes today. If it fails, the gap is real
> — fix the prompt before proceeding.

**Before writing any test**, read Doc A §9.3.1 in full. The design
section names `_ASSEMBLED_PREAMBLE` — that name may not match what
`context_assembly.py` exposes after Phase 2's changes; find the
equivalent surface first. The `parser_context` context bundle carries
every `.sysprompt` file plus the manifest, so a fresh window can read
the assembled prompt's inputs directly.

Do not open Phase 3b (prompt generation) until 3a passes. 3a's purpose
is to establish that the current prompt covers what the KG declares;
3b's generator is only meaningful against that baseline.

---

## The one rule

**Reproduce before you plan.** A finding whose reproducer no longer
fires is `closed-as-not-a-bug`; a finding whose reproducer still fires
is the next fix. Guessing which costs more than running the command.

**This window's instance, worth remembering.** The F-045 entry named
two fix shapes; a single pod probe showed the mechanism was neither.
Had the fix been written from the entry's description, it would have
shipped silent — the wrong-clause fix alone returns 25 rows on the
entry's own reproducer and 0 on any range below the pod's physical
scan window. The actual cause was only visible by running the probe.

---

## Working-style reminders that keep biting

- **One command at a time.** Wait for output. Then next.
- **Complete files, never fragments.** Whole file, one block.
- **`~~~` for any outer fence whose content contains ` ``` `.** Rule 4.
- **Full-output capture (rule 15.1).** Redirect long runs to a file,
  then grep from the file. Never pipe the run itself through a filter.
- **Name a slow command's cost (rule 15.2)** before handing it over.
  Reg #30's reproducer was 5m19s; F-045's V1–V4 sweep was ~50s.
- **Every file edit is two cells (rule 15.3).** Cell 1: Python script
  that reads the file, checks the anchor, replaces, writes, exits.
  Cell 2: shell commands that read the file back from disk. The two
  do not blend.
- **Ledger reconciliation on open (rule 16).**
      gh pr list --state merged --limit 20 --json number,title,mergedAt \
        --jq '.[] | "\(.number)\t\(.mergedAt)\t\(.title)"'
      grep -nE '^\| F-0[0-9]+ .*\| fixed \| — \|' docs/phase-2/FIX_PLAN.md
  Both should come back clean. Last merged PR is **#170**.
- **The audit is the report; the findings log is the notebook.** Audit
  rows close in place. Findings-log corrections are new dated update
  blocks appended inside the entry — never edits to the original text.
- **`git stash` does not stash committed changes.** V7 against a
  committed fix uses `git checkout HEAD~1 -- <path>` /
  `git checkout HEAD -- <path>`. Window 18 got this wrong once;
  corrected in `F-045.md`'s V7 section.

---

## Commits on `hardening-master`, window 18 (newest first)

    018f31a  context_bundles: add five files landed but not bundled
    88a07c6  Doc B index: pointer row for window 18
    e887795  handover: rewrite for window 19 (Phase 3a opens)
    8012b1b  Doc B index: §1 snapshot refresh for window 18
    4b3737c  Reg #30: evidence capture for the closure
    97bed63  Reg #30: closed as not-a-bug; residual latency deferred
             to Phase 6
    2573e3c  endpoints ref: /purchaseOrders scan-order facts from F-045
    6d5f76a  F-045: verified | #170
    f77a093  Phase 2 — Fix F-045: created_since beats created_before;
             date fetch gets an orderBy (#170)

### Window 17 for reference

    f35deb9  post-merge bookkeeping: F-051 -> verified | #169
    da68989  Merge pull request #169 (F-051 summary gate)
    7dcc91c  F-051: fix file and V-standard evidence
    5e08a77  post-merge bookkeeping: F-049 -> verified | #168
    ac06469  Merge pull request #168 (F-049 invoice created dates)
    4d1ba1a  F-049: fix file and V-standard evidence
    1c3892e  F-049: add 18_invoice_created_dates prompt set

---

## Known doc-drift, recorded not fixed

- **`docs/spire-robustness/SESSION_HANDOVER.md`** — deprecated in this
  window. Its content (a Phase 3a handover written mid-session before
  the canonical question was settled) is superseded by this file. The
  file is retained as a three-line pointer at this one to prevent the
  next window from re-discovering the split. See the deprecation
  commit for the exact text.
- **`source-tree.txt` at repo root** — stale (the tree has moved on;
  the file is not tracked and is `.gitignore`d, but it appears in
  `source-tree.txt` output because that file lists itself). Not a
  blocker. Reconciliation is a follow-up, not scheduled.
- **Doc B's `02_Phase_02_Correctness.md`** carries entries for S003
  and S004 only. Windows 17 and 18 ran without Doc B session entries —
  consistent with that file's header convention. The forensic record
  for window 18 lives in FIX_PLAN §4.1, §5, the fix files, and the
  pointer row in `00_Doc_B_Index.md` §4.
- **`context_bundles.yaml`** — its comment block now correctly names
  this file as the plan bundle's entry point (updated in the same
  commit as this rewrite). Previous versions named the wrong file in
  both comment and bundle content.

---

*End of handover.*
