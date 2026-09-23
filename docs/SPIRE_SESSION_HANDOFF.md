# SPIRE — Session Handoff, 2026-09-23

**This file supersedes the 2026-09-22 handoff.** Phase 2 is well underway;
19 findings shipped (plus one closed as duplicate). This window closed F-018, F-011 (plus F-011b/c), and
F-019 on one branch, and filed four new findings (F-045 through F-048).

**Read this first.** Then `docs/AUDIT_AND_FIX.md` — the playbook — which
points to everything else. The audit (`docs/audit/phase-1-audit.md`) and
the findings log (`docs/audit/findings-log.md`) are the two
source-of-truth documents.

---

## Where we are

**Branch:** `hardening-master`.

**Phase 2 — Correctness — in progress.**

Shipped (all merged to `hardening-master`):

- F-002 — `promptkit.py` double-classify — PR #149
- F-033 — `ReceivablesInvoiceLine` refusal's Example — PR #150
- F-041 — AR invoice children named first — PR #151
- F-042 — supplier-address phrasings refuse — closed-as-duplicate (F-009), PR #152
- F-043 — Site and Classification includes refuse — PR #152
- F-009 — addresses rule lives in `payables/` — PR #152
- F-001 — filter-less PO lists now answer — PR #153
- F-006 — alpha-prefixed OrderNumber accepted — PR #154
- F-007 — requested-and-empty AR-invoice children acknowledged — PR #155
- F-015 — empty result from a capped fetch says so — PR #156
- F-012 — capped fetch with no source total narrates the sample — PR #157
- F-036 — truncation note no longer claims "for filtering" — PR #157
- F-044 — double-encoded `value_json` no longer crashes — PR #158
- F-010 — filtered count returns the filtered bucket — PR #159
- F-008 — expired supplier classifications no longer match — PR #160
- F-020 — supplier-contacts run-on removed; Admin column added — PR #161
- F-039 — aggregate comparison phrase honest when excluded > 75% — PR #162
- F-018 — invoice number is a first-class Invoice filter — PR #163 (`7e1c127`)
- F-011 — PO relative-date filter — PR #163 (`773a885`)
- F-019 — account number resolves as an identifier, not a name — PR #163 (`0c9fe34`)
- F-011b/c — direction split + backslash-escape decode + last-modified guard — PR #163 (`d3b6232`)

Current test baseline: **1135 passed, 22 deselected**.

Filed this session, not fixed (four findings; F-045 filed mid-sweep as a
side observation):

- F-045 / B-28 — composite `created_since AND created_before` on `/purchaseOrders`
  returns 0 with a misleading "capped" note. Suspected pod-side composite-clause
  issue (parallels F-012's `/invoices` falsifier).
- F-046 / B-29 — Invoice has no relative-date filter; `invoices older than 6 months`
  refuses on missing supplier. Mirror of F-011. `search_invoices` already accepts
  `invoice_date_before` / `invoice_date_after`.
- F-047 / B-30 — PO last-updated-date filter missing; `not touched in the last year`
  has no honest answer. F-011c's sysprompt guard produces a correct refusal, but
  the right fix is to add a `LastUpdateDate` filter to `search_purchase_orders`.
- F-048 / B-31 — vague relative adjectives (`recent`, `new`) refuse instead of
  defaulting to a window. Policy finding; V9 mandatory when it lands.

---

## First steps in the new window

1. **Confirm ground truth.**
   - `git log --oneline -5`
   - `git status`
   - `pytest -q` (expect `1135 passed, 22 deselected` with the pod up.
     If the pod is down, the pod-dependent tests fail rather than skip —
     see the audit's §F.3 note. Compare against the last green count,
     not a stale figure.)

2. **Read the playbook.** `docs/AUDIT_AND_FIX.md`. It has: where everything
   lives, what to work on (open `docs/phase-2/FIX_PLAN.md`, take the top
   `not-started` row in §4 order), how to reproduce / classify / fix /
   verify / track, and the recovery path if context is lost.

3. **Pick the next task.** The two candidates the last window left on
   the table:

   **Option A — F-046 / F-047 / F-048 cluster (recommended).**
   These are the direct follow-ons from the F-011b sweep. One branch,
   three commits, one per finding. The three touch overlapping files
   (`kg_schema.sql`, `b_po_created_date.sysprompt`, `context_assembly.py`,
   `test_kg_metadata.py`, `print_kg.py`), so a single branch avoids merge
   collisions at the shared files.

   Branch name: `phase-2-fix-F046-F047-F048-date-filters`.
   Order within the branch: F-046 first (mirror of F-011, no new tool arg),
   F-047 second (adds a `LastUpdateDate` column to `search_purchase_orders`),
   F-048 last (V9 mandatory — highest blast radius, changes parser defaults).

   **Option B — projection cluster.** F-017, F-027, F-014, F-021. All
   share `_FIELDS_SATISFIED_BY_INCLUDE` / `_project_outputs`. One branch,
   four commits. Branch name: `phase-2-fix-projection-cluster`.

   **Option C — single small fix.** F-016 (list-row cap schema gap) or
   F-037 (test-set hygiene). Small warm-up.

4. **Do not touch `config.py` (CF-2).** Parked by user decision.

5. **V9 is deferred but outstanding.** Three sysprompt edits landed on
   `hardening-master` via PR #163 (`b_invoices_for_supplier`,
   `b_po_created_date` — two revisions). A full `--validate` corpus run
   has not been executed on the current code. Two paths:
   - Run V9 now (single manifest run — `python scripts/promptkit.py --run
     --manifest scripts/promptkit_sets.yaml`; slow sets 06_slow and
     08_lifecycle can be skipped for a fast pass).
   - Or batch V9 with the next sysprompt edits (F-046/47/48 touch
     `b_po_created_date` and add Invoice phrasings, so V9 after F-048
     would cover both sessions' edits in one pass).

   **Recommendation:** batch with F-046/47/48. One V9 at the end of the
   next branch covers all five sysprompt edits from the two sessions.

---

## Lockstep invariant — where it drifts

The four-place lockstep (`AUDIT_AND_FIX.md` §How to track) is per fix.
One invariant drifts most: "every F-NNN status line matches its FIX_PLAN
row." A merge landing between a lockstep commit and window close leaves
the handoff one bump behind. This window ended clean — the PR body,
findings-log, audit §B.6, and FIX_PLAN rows were all updated before
the merge.

If you find an invariant violation in the next window, fix it as part of
the first commit of that session.

---

## Session-shape observation — 2026-09-23 window

This window was the inverse of the 2026-09-22 window's shape. Where that
one closed three findings one at a time, this one shipped four on a single
branch (PR #163): F-018 + F-011 + F-019 + F-011b/c. The decision to batch
was deliberate — three of the four were Cluster 4 (parser sysprompt +
KG + planner guard), sharing files, so separate branches would have
collided at merge.

Cost: a long window. The F-011b sweep (23 prompts) and its direction-split
fix ran after F-011 was already committed, because the first F-011 commit
had an inversion defect that only became visible under a broader prompt
set. F-011c then added a decode-loop hardening and a sysprompt guard for
last-modified phrasings — two residual defects from F-011b's own first
pass.

Benefit: all four fixes shipped together, tests are green (1135), and
the four follow-on findings (F-045 through F-048) are filed and tracked
in FIX_PLAN. The window closed one full cluster's worth of relative-date
work with the remaining three findings queued and primed.

Recommendation for the next window: keep the batch-of-three pattern for
F-046/47/48. But — bias toward running the sweep BEFORE the commit for
new sysprompt rules, not after. The F-011b/c inversion cost real time
because it was caught by post-commit sweep instead of pre-commit.

---

## Open work

Ordered by §8.3.1 severity.

**Missing-capability:**
- F-003 — three PO aggregation ops unreachable from a scoped parse;
  `modes/` folder in neither `_TIER1` nor `KNOWN_MODULES`. F-004 falls
  out of this.
- F-004 — PO-value ranking misroutes to a comparison op.
- F-016 — no schema field for a plain-list row cap; `top 5` on a list
  query is dropped.
- F-021 — DFF child fetched but never rendered.
- F-027 — "country" column request routed to Address include; display
  renders full blob.
- F-046 — Invoice has no relative-date filter (mirror of F-011).
- F-047 — PO has no last-updated-date filter.
- F-048 — vague relative adjectives should default to a window.

**Wrong-data / wrong-narration:**
- F-014 — `fields` on an aggregate intent applied to the wrapper record.
- F-017 — `Description` on a PO-lines include classified unresolved.
- F-045 — composite date clause on `/purchaseOrders` returns 0 with a
  misleading "capped" note.

**Cosmetic / hygiene / cost:**
- F-037 — duplicated prompts across files.

**Register #30 (perf, from handoff, not in FIX_PLAN):**
- `Compare ordered vs invoiced for our top 3 suppliers` pages all
  17,447 POs before narrowing. Fix shape: rank top-N first (cheap),
  then fetch only their POs.

**Closed-as-not-a-bug (do not re-open without cause):** F-005, F-013,
F-022, F-023, F-024, F-025, F-026, F-028 through F-032, F-034, F-035,
F-038, F-040, F-042.

---

## Pod-state observations carried forward

- Pod growth is real and ongoing. Supplier count has moved 431 → 620 →
  656 → current. Golden files and pod-dependent counts will keep
  drifting; regenerate when the diff is only pod data, note when it is
  not.
- Module-set ordering varies run-to-run. Diagnostic, not correctness.
- Model-prose variance in `Reason:` lines is real. Same flavor, same
  Solution, different prose.
- The parser prompt is at its token ceiling. Any sysprompt edit needs
  a full `--validate` re-run (V9). This is why F-048's rule edit is the
  highest-risk of the three new findings.
- The pod is eqjz. `personas.yaml` holds credentials and is tracked
  (task 1.1 deferred per plan). Do not commit `personas.yaml`. Named
  `git add`, never `-A`. Restart the MCP server after any change under
  `src/spire/mcp_server/`.
- The F-011b/c sweep artefacts live at repo root: `15_po_relative_date_*`
  `.txt` files and `scripts/prompts/15_po_relative_date_filters.txt`.
  These are evidence, not scratch — they document the direction-inversion
  fix and are the re-runnable check if the sysprompt rule drifts later.

---

## Working process

`docs/spire-robustness/WORKING_STYLE.md` is the standard.
`docs/AUDIT_AND_FIX.md` is the activity playbook.
`docs/spire-robustness/SESSION_STARTUP_CHECKLIST.md` is the open/close
procedure.

**One command at a time.** Anchor-block-verify for every paste. Complete
files, never fragments. Nested fences use `~~~`.

**Batch edits** use the atomic python-heredoc pattern: read file, apply
list of (label, old, new) replacements, assert each anchor's count is
exactly 1, write only on success. Aborts on the first mismatch. This
window's F-011b and F-019 patches are examples of the pattern.

**Doc disciplines:**
- Plan (`SPIRE_ROBUSTNESS_EXTENSIBILITY_v3.2.md`) — frozen.
- Forensic record (`..._Status.md`) — append-only.
- Audit (`phase-1-audit.md`) — working; rows close in place.
- Findings log (`findings-log.md`) — append-only; newest at top.
- FIX_PLAN (`FIX_PLAN.md`) — working; status column mirrors findings log.

---

## Context bundles — how to request code

Code shared as bundles, not individual files. `context_bundles.yaml`
defines them; `build_context.py --all` writes to `context_out/`.

Phase 2 bundles that matter: `parser_planner`, `parser_context`,
`mcp_server_tools`, `synthesizer`, `graph_kg`.

**Not in any bundle:** `personas.yaml`, `docs/archive/*`. Paste directly
if needed.

**Individual-file requests are fine for narrow reads** — this window
requested single-function greps (`grep -n -A15 "def …"`) multiple times
and that worked well. Bundles are for wide context, not for one anchor.

---

## What to read first, in order

1. This file.
2. `docs/AUDIT_AND_FIX.md` — the playbook.
3. `docs/phase-2/FIX_PLAN.md` — the queue, §5 ledger and §4 sequence.
4. The F-046 entry in `docs/audit/findings-log.md` — the recommended
   next task, if Option A is chosen.

That is the complete list. The audit's §B.6 map is a lookup when you
need it, not required reading.

---

*End of handoff.*
