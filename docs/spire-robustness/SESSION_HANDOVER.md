# SPIRE — Session Handover

**Written:** 2026-09-24
**Phase:** Phase 2 — Correctness (open)
**Branch:** `hardening-master`
**Mode:** Fixing. One bug at a time, per FIX_PLAN §4. The audit is
frozen; new findings get a new F-NNN and their own ledger row.

---

## Read these first, in this order

1. `docs/phase-2/FIX_PLAN.md` §5 (the ledger) and §4 (the sequence).
   This is the live source of truth. Every open row, its state, and
   its PR lives here.
2. The next F-NNN entry in `docs/audit/findings-log.md`.
3. `docs/audit/phase-1-audit.md` §B.6 — the audit-row-to-finding map.
4. `docs/spire-robustness/WORKING_STYLE.md` — S0–S8 (evidence
   standard), rules 15.1 / 15.2 (full-output capture; name the cost of
   a slow command), rule 16 (open every window with a ledger
   reconciliation).
5. `docs/AUDIT_AND_FIX.md` — the playbook.

---

## Current state

**Repo**
- Branch `hardening-master`, HEAD `f3db9cc`. Clean.
- Integration branch: `hardening-master`. `master` frozen at `14dce82`.
- Phase branches spawn off `hardening-master` and merge back via PR.
  Nothing merges to `master` without explicit instruction.
- Test count: **1210 passed / 22 deselected** (measured 2026-09-24).

**Runtime**
- Dev tree:  `~/pocs/spire`, MCP 4444 / API 9000 / UI 9999.
- Runtime:   `~/pocs/spire-runtime`, MCP 3333 / API 8000 / UI 8888,
  ngrok-exposed. Do not disturb without a deliberate plan.
- Ports come from `SPIRE-PORTS.env`; `.spire-dev.env` (gitignored, in
  the dev tree only) overrides them for dev.

---

## Ledger state

**Closed:** 28 rows (F-001…F-044, F-046…F-048, F-041, F-043, plus
reclassified F-021 and F-042).

**Open — 7 rows, none in progress:**

| Cluster | Row | One line |
|---|---|---|
| 4b | F-049 | "invoices created before/since X" refuses — sysprompt only |
| 5 | F-003 | `modes/` folder unreachable from a router-scoped parse |
| 5 | F-004 | PO-value ranking misroutes to a comparison — may fall out of F-003 |
| 8 | Reg #30 | Compare-path perf, carried from Phase 1 |
| — | F-045 | Composite PO date clause returns 0 with a "capped" note |
| — | F-050 | `columns/` folder unreachable — blocks F-027's deferred sysprompt half |
| — | F-051 | fields+include caller-side gate, three sites |

Full detail in `FIX_PLAN.md` §5.

---

## Next action

**F-003** — `modes/` folder unreachable from a router-scoped parse.
Fix site: `_TIER1` in `src/spire/nl_parser/context_assembly.py`. The
tuple `("core", "refusals")` does not include `modes`, and
`KNOWN_MODULES` does not either, so `assemble_subset` never loads a
`modes/` block. F-004 may fall out of the same change; FIX_PLAN §4
records the dependency.

Reproducer is a `promptkit --run` on
`how many purchase orders are there and what are they worth` — expects
`unsupported_filter` (F-003) where a count + total should be. Cost
~10–15s per run; not a long-fetch concern, but worth naming before
handing it over.

---

## The one rule

**Reproduce before you plan.** A finding whose reproducer no longer
fires is `closed-as-not-a-bug`; a finding whose reproducer still fires
is the next fix. Guessing which costs more than running the command.

---

## Known doc-drift, recorded not fixed

- `docs/spire-robustness/SESSION_HANDOVER.md` — this file. Rewritten
  2026-09-24; prior version dated 2026-09-17 and framed for Phase 1.
- The session-start instruction named a path that does not exist
  (`docs/SPIRE_SESSION_HANDOFF.md`). The file is at
  `docs/spire-robustness/SESSION_HANDOVER.md`. `AUDIT_AND_FIX.md` was
  corrected in the same commit.
- Doc B's `02_Phase_02_Correctness.md` has an entry for `S003` only.
  Sessions S-nothing between S002 and S003 have their forensic record
  in FIX_PLAN §5 and the per-fix files, not in Doc B. Deliberate; the
  backfill would produce prose nobody wrote.

---

## Working-style reminders that have bitten us

- **One command at a time.** Wait for output. Then next.
- **Complete files, never fragments.** Whole file, one block.
- **`~~~` for any outer fence whose content contains ` ``` `.** Rule 4.
- **Full-output capture (rule 15.1).** Redirect long runs to a file,
  then grep from the file. Never pipe the run itself through a filter.
- **Name a slow command's cost (rule 15.2)** before handing it over.
- **Ledger reconciliation on open (rule 16).**
      gh pr list --state merged --limit 20 --json number,title,mergedAt \
        --jq '.[] | "\(.number)\t\(.mergedAt)\t\(.title)"'
      grep -nE '^\| F-0[0-9]+ .*\| fixed \| — \|' docs/phase-2/FIX_PLAN.md
- **The audit is the report; the findings log is the notebook.**
  Audit rows close in place. Findings-log corrections are new dated
  update blocks appended inside the entry — never edits to the
  original text.

---

*End of handover.*
