# SPIRE — Session Handoff, 2026-09-22

**This file supersedes the 2026-09-20 handoff.** Phase 1 is closed; Phase 2
has begun. Eight findings from the Phase 2 sweep are shipped.

**Read this first.** Then `docs/AUDIT_AND_FIX.md` — the playbook — which
points to everything else. The audit (`docs/audit/phase-1-audit.md`) and
the findings log (`docs/audit/findings-log.md`) are the two
source-of-truth documents.

---

## Where we are

**Branch:** `hardening-master`.

**Phase 2 — Correctness — in progress.**

Shipped:

- F-041 — AR invoice children named first — `verified`, PR #151
- F-042 — supplier-address phrasings refuse — `closed-as-duplicate (F-009)`, PR #152
- F-043 — Site and Classification includes refuse — `verified`, PR #152
- F-009 — its fix landed as F-042's branch — `verified`, PR #152
- F-001 — filter-less PO lists now answer — `verified`, PR #153
- F-006 — alpha-prefixed OrderNumber accepted at the MCP boundary — `verified`, PR #154
- F-007 — requested-and-empty AR-invoice children now acknowledged — `verified`, PR #155
- F-015 — an empty result from a capped fetch now says so — `verified`, PR #156
- F-012 — a capped fetch with no source total now narrates the sample — `verified`, PR pending
- F-036 — the truncation note no longer claims "for filtering" on an unfiltered fetch — `verified`, PR pending

Confirmed (S0–S8 walked) — none outstanding.

---

## First steps in the new window

1. **Confirm ground truth.**
   - `git log --oneline -5`
   - `git status`
   - `pytest -q` (expect `1048 passed, 22 deselected` with the pod up;
     if the pod is down, the pod-dependent tests fail rather than skip
     — see the audit's §F.3 note for the reconciliation. Compare
     against the last green count, not a stale figure.)

2. **Read the playbook first.** `docs/AUDIT_AND_FIX.md`. It has:
   - where everything lives,
   - what to work on (open `docs/phase-2/FIX_PLAN.md`, take the top
     `not-started` row),
   - how to reproduce / classify / fix / verify / track,
   - the recovery path if context is lost.

3. **Open F-012 + F-036.** They are the next task per
   `docs/phase-2/FIX_PLAN.md` §4 order. Cluster 1 (synthesizer
   narration); the plan places them together because they share the
   `_local_truncation` f-string in `synthesizer/synthesizer.py` — one
   fix pass closes both.

   F-012 reproducer:
   `python scripts/promptkit.py --run --prompt "invoices for supplier 1252 over 10000" --show-stages`

   F-036 reproducer:
   `python scripts/promptkit.py --run --prompt "Suppliers with their addresses" --show-stages`

   Read both findings in `docs/audit/findings-log.md` and their
   `docs/phase-2/FIX_PLAN.md` §5 rows, then follow Phase 2 §8.3:
   - F-012 severity: wrong-data (a sampled result read as the whole).
   - F-036 severity: wrong-narration (a filter-less fetch says
     "examined for filtering").
   - Deterministic: single-run test suffices for each.
   - Branch: one branch, both fixes —
     `phase-2-fix-F012-F036-truncation-wording`.
   - Regression tests: F-012 — the composite-filter prompt produces a
     summary that mentions the sample, OR a truncation note that states
     the true examined count, not `20`; a non-composite query is
     unaffected. F-036 — the unfiltered prompt's truncation note no
     longer contains the phrase "for filtering"; a filtered prompt's
     note stays consistent with whichever wording the fix picks.
   - Byte-diff: the note is user-visible and appears in the 05/07/08
     prompt-set baselines. Regenerate any golden that carries the note.

4. **Do not touch `config.py` (CF-2).** Parked by user decision.

---

## Lockstep invariant — where it drifts

The four-place lockstep (`AUDIT_AND_FIX.md` §How to track) is per fix,
and this session ran it four times (F-001, F-006, F-007, F-015). One
invariant drifts most: "every F-NNN status line matches its FIX_PLAN
row." A merge landing between a lockstep commit and window close leaves
the handoff one bump behind — F-015 arrived this session with exactly
that shape (`fixed` in the handoff, `verified` everywhere else).

If you find another invariant violation in the next window, fix it as
part of the first commit of that session.

---

## Open work

Ordered by §8.3.1 severity.

**Missing-capability:**
- F-003 — three PO aggregation ops unreachable from a scoped parse;
  `modes/` folder in neither `_TIER1` nor `KNOWN_MODULES`. F-004 falls
  out of this.
- F-004 — PO-value ranking misroutes to a comparison op.
- F-008 — expired supplier classifications still match.
- F-011 — KG says `created_before` answers "stale POs"; sysprompt refuses the class.
- F-016 — no schema field for a plain-list row cap; `top 5` on a list query is dropped.
- F-018 — invoice number dropped; refusal offers a filter the pipeline can't accept.
- F-021 — DFF child fetched but never rendered.
- F-027 — "country" column request routed to Address include; display renders full blob.

**Wrong-data / wrong-narration:**
- F-010 — `count_only` on a filtered intent returns the unfiltered source total.
- F-012 — composite filter hits the over-fetch cap, drops `total_available`.
- F-014 — `fields` on an aggregate intent applied to the wrapper record.
- F-017 — `Description` on a PO-lines include classified unresolved.
- F-019 — account number routed into `by_customer_name`.
- F-020 — supplier-contacts summary flattens 47 names into one sentence.
- F-036 — truncation note says "examined for filtering" on an unfiltered fetch.
- F-039 — "under-invoiced" over-claim where 97% of invoices are excluded.

**Cosmetic / hygiene / cost:**
- F-002 — `promptkit.py` calls `classify_modules` twice per prompt.
- F-033 — `ReceivablesInvoiceLine` refusal's Example is the failing prompt itself.
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

- Pod growth is real and ongoing. Supplier count: 431 → 450 → 593 →
  600 → 620 → 656 → current. Golden files and pod-dependent counts will
  keep drifting; regenerate when the diff is only pod data, note when
  it is not.
- Module-set ordering varies run-to-run. Diagnostic, not correctness.
- Model-prose variance in `Reason:` lines is real. Same flavor, same
  Solution, different prose.
- The parser prompt is at its token ceiling. Any sysprompt edit needs
  a full `--validate` re-run.
- The pod is eqjz. `personas.yaml` holds credentials and is tracked
  (task 1.1 deferred per plan). Do not commit `personas.yaml`. Named
  `git add`, never `-A`. Restart the MCP server after any change under
  `src/spire/mcp_server/`.

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
exactly 1, write only on success. Aborts on the first mismatch.

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

---

## What to read first, in order

1. This file.
2. `docs/AUDIT_AND_FIX.md` — the playbook.
3. `docs/phase-2/FIX_PLAN.md` — the queue.
4. The topmost open finding in `docs/audit/findings-log.md` — F-012.

That is the complete list. The audit's §B.6 map is a lookup when you
need it, not required reading.

---

*End of handoff.*
