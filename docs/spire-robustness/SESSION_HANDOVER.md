# SPIRE — Session Handover

**Written:** 2026-09-17
**Phase:** Phase 1 — Audit & Baseline (still open)
**Branch:** `Phase1-Audit-and-Baseline`
**Mode:** Investigative. We are FINDING and ISOLATING bugs, not fixing them.
Fixes happen in Phase 2, later, as a separate pass.

---

## Read these first, in this order

1. `docs/spire-robustness/WORKING_STYLE.md` — especially the section
   "Evidence standard for findings (S0–S8)". Every new finding must walk
   S0–S8 in order. If a step fails, the claim stops at that step.
2. `docs/audit/findings-log.md` — F-001 through F-005. This is the
   lab notebook. Newest entry at the top.
3. `docs/audit/phase-1-audit.md` — the work queue. §B has 25+ bugs.
   Several have no F-NNN yet; those are what we investigate next.

---

## Current state

**Repo**
- Branch `Phase1-Audit-and-Baseline`, up to date with origin, working tree
  clean, 2 commits ahead of `origin/Phase1-Audit-and-Baseline` (unpushed).
- Integration branch is `hardening-master`. `master` frozen.
- Runtime tree at `~/pocs/spire-runtime` — still has the OLD `run-all.sh`
  and `run-server.sh`. Do NOT touch it without a deliberate plan.

**Ports (new, working)**
- Dev:     MCP 4001 / API 4002 / UI 4003
- Runtime: MCP 3001 / API 3002 / UI 3003
- Single source of truth: `SPIRE-PORTS.env` at repo root.
- `run-all.sh --dev | --runtime` — mode is required, no default.
  `--status` and `--stop` are scoped to the current mode.
- `run-server.sh` reads `SPIRE_MCP_PORT`; fails loudly if unset.
- Shell functions `spire()` / `spirer()` in `~/.bashrc` export
  `SPIRE_MODE`, `SPIRE_MCP_URL`, `SPIRE_API_URL` and echo the port set.
- `.spire-dev.env` is retired. The script warns if it is still present.

**Test count:** 1008 passed / 22 deselected (before this session's changes;
not re-run since — re-run before trusting).

---

## What was done this session

1. Read three big code bundles (`parser_planner`, `parser_context`,
   `mcp_server_tools`) plus `graph_kg` and `scripts`. Closed six pending
   §A rows (A-12, A-13, A-14, A-15, A-16, A-17, A-20).

2. Rewrote the port scheme. Committed.

3. Wrote the S0–S8 evidence standard into `WORKING_STYLE.md`. Committed
   (pending; see below).

4. Found and root-caused F-001 through F-005. Written into the findings
   log.

---

## The findings, one line each

- **F-001** — `_is_explicit_po_list` is defined in `parser.py` but never
  called, so `Intent.list_all` is always False, so every filter-less PO
  query refuses. Bug B-13.
- **F-002** — `promptkit.py --run` calls `classify_modules` twice per
  prompt. Confirmed live: two distinct completions from the same input.
  Bug B-09. Cost regression plus a diagnostic-fidelity problem (the
  diagnostic checks a different classifier call than the pipeline used).
- **F-003** — three PO aggregation ops (`po_value_by_supplier`,
  `po_count_by_status`, `open_po_summary`) live only in
  `modes/m_aggregation.sysprompt`, which never reaches a scoped parse.
  Every prompt that needs one fails. Bug B-20.
- **F-004** — same root as F-003, from the other side: when a near-match
  op exists in `draft.py`'s schema, the model picks it and answers a
  superset of the question. The dangerous class. Silent wrong answer.
- **F-005** — `orderBy=Ordered:desc` silently ignored on
  `/purchaseOrders`. Informational, no fix needed, doc-only.

---

## What is NOT yet committed

Two files:
- `docs/audit/findings-log.md`
- `docs/spire-robustness/WORKING_STYLE.md`

Commit them together, one commit:
```
git add docs/audit/findings-log.md docs/spire-robustness/WORKING_STYLE.md
git commit -m "phase1: evidence standard (S0-S8); findings log F-001..F-005"
```

Then push:
```
git push
```

---

## What is pending, at three levels

**Within Phase 1, near-term (investigative):**
- §B bugs without an F-NNN: B-04, B-11, B-15, B-02, B-03, B-05, B-06,
  B-07, B-10, B-12, B-14, B-16, B-17, B-18, B-19, B-21, B-22, B-23,
  B-24, B-25, B-26, B-27. Several have curl-verified evidence already;
  those are the fastest to convert into F-NNN entries.
- §A.2 still has A-12/A-13/A-14/A-15/A-16/A-17/A-20 rows marked
  "pending" — those were closed by this session's bundle reads but the
  audit file itself was not updated. Either update it or leave a note.

**Within Phase 1, larger:**
- §C (dead code inventory) — not started.
- §E (in-flight work inventory) — not started.
- §F (baseline metrics) — not started.
- §H N≥20 runs on the nondeterministic cases — not started.
- B-23 targeted run on invoice 1002 — not started.

**Phase 2 (fixing) — explicitly out of scope for the next session:**
- Fix F-001 through F-005, one at a time, with regression tests.
- §8.3.7 of Doc A — partial execution + gap reporting in `execute_plan`.

---

## Next session should

**Investigative mode. Not fixing. One bug at a time. S0–S8 applied.**

Pick ONE bug from §B that does not yet have an F-NNN entry. Three
candidates, easiest first:

1. **B-11** — `How much of PO 2144 was received?` returns "No purchase
   order found for '2144'". Narrow, single prompt, likely one mechanism.
   Fastest to close.
2. **B-15** — "include never fires" on 12 prompts (`12_po_supplier_include.txt`).
   Mechanism suspected: parser stops at the anchor entity. Falsifiable
   in a couple of probes.
3. **B-04** — supplier-child filters scan only the first 25 of ~455.
   The biggest class (~35 prompts). Deserves its own investigation plan.
   Save for last.

For whichever is chosen:
- Name the harm (S1).
- Paste evidence, tier 2 or better (S2).
- Name the mechanism, cited by `file:line` (S3).
- Disprove an alternative (S4).
- Name the falsifier (S5).
- Only then write the F-NNN entry.

Do not fix. Do not batch. If the investigation uncovers a second bug on
the way, write it up separately.

---

## Working style reminders that have bitten us this session

- **One command at a time.** Wait for output. Then next.
- **Complete files, never fragments.** The findings log gets rewritten
  whole each time — no splicing.
- **Do not call a hunch a bug.** F-006 was written up as a bug before S1
  (harm) was checked. It was never a bug. Every claim now walks S0–S8.
- **The audit is the report; the findings log is the notebook.** Update
  the notebook freely. Update the report in batches.
- **`--stop` requires a mode.** `./run-all.sh --dev --stop` or
  `./run-all.sh --runtime --stop`. Running `./run-all.sh --stop` with no
  mode errors out on purpose. Stopping one mode never touches the other.
- **Curl against Fusion uses `IKS_*` env vars** (already exported).
  `SPIRE_MCP_URL` is for promptkit only, not curl.
- **`SPIRE_MODE` is set by `spire()` / `spirer()`.** If it is empty in a
  shell, run one of those functions before any `run-all.sh` command.

---

*End of handover.*