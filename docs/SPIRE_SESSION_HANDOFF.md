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

- F-041 — AR invoice children named first — `closed`, PR #151
- F-042 — supplier-address phrasings refuse — `closed-as-duplicate (F-009)`, PR #152
- F-043 — Site and Classification includes refuse — `closed`, PR #152
- F-009 — its fix landed as F-042's branch — `closed`, PR #152
- F-001 — filter-less PO lists now answer — `closed`, PR #153
- F-006 — alpha-prefixed OrderNumber accepted at the MCP boundary — `closed`, PR #154
- F-007 — requested-and-empty AR-invoice children now acknowledged — `closed`, PR #155
- F-015 — an empty result from a capped fetch now says so — `closed`, PR #156
- F-012 — a capped fetch with no source total now narrates the sample — `closed`, PR #157
- F-036 — the truncation note no longer claims "for filtering" on an unfiltered fetch — `closed`, PR #157
- F-044 — double-encoded `value_json` no longer crashes the tool at schema validation — `closed`, PR #158

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

3. **Open F-010.** It is the next task per
   `docs/phase-2/FIX_PLAN.md` §4 order. Cluster 1 (synthesizer
   narration); the finding's own text and the plan's §5 row both name
   `synthesizer/aggregation.py` as the fix site.

   F-010 reproducer:
   `python scripts/promptkit.py --run --prompt "count of suppliers with classification Minority Owned" --show-stages`

   Read the F-010 entry in `docs/audit/findings-log.md` and its
   `docs/phase-2/FIX_PLAN.md` §5 row, then follow Phase 2 §8.3:
   - F-010 severity: wrong-data — a filtered count returns the
     unfiltered source total. Mechanism (from the finding entry):
     `_build_count_response` does `next(iter(outputs.values()))` and
     reads the SOURCE bucket, not the filtered `{source}_{suffix}`
     bucket the executor also produced.
   - Deterministic: single-run test suffices.
   - Branch: `phase-2-fix-F010-count-filtered`.
   - Regression test: the composite-filter prompt returns the size of
     the filtered bucket; the plain `count of suppliers` still returns
     the pod-wide figure.
   - Byte-diff: no golden carries this prompt.

   Two carry-forwards from the 2026-09-22 session, for whoever picks
   up the next task:

   - **F-044** (crash, filed this session by F-012/F-036's L2 pass).
     Sits in FIX_PLAN §4 as row 10. Not the next task per §4 — F-010
     comes first — but a crash, so the phase's severity rule
     (wrong-data > crash > missing-capability > cosmetic) may reorder
     it once its mechanism is settled.
   - **`promptkit.py` `.txt` support — shipped, not deferred.** The
     rewrite landed mid-session as commit `2f9daf7`, which added
     `--prompt-file` (`.txt` prompts, no `.json` companion needed)
     and `--manifest` (multi-set runs), and deleted
     `promptkit_overnight.py`. The 78-prompt sweep in this session
     (see `docs/phase-2/fixes/F-012-F036-F044-78-prompt-sweep.txt`)
     ran on the new CLI. `scripts/prompts/README.md` is the current
     inventory; FIX_PLAN §7's `--set` reference is stale.

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

## Session-shape observation — 2026-09-22 window

This window closed three findings: F-012, F-036, and F-044. FIX_PLAN
§4 schedules one per window, so three is a departure. The first two
were the handoff's named next task; F-044 surfaced mid-session during
their L2 prompt-set run and was fixed while the failure was live and
the mechanism could be pinned with one diagnostic pass.

Cost: the session ran ~4 hours, spanning fix → merge → L2 discovery →
fix → merge again. The two fixes themselves were each small (~30
lines of code, ~200 lines of tests). The time went to verification —
prompt probes, N>=20 variance runs, lockstep doc updates — not to
code.

Benefit: F-044's reproducer was right there, and the S0–S8 walk that
would have been needed to promote it from candidate to root-caused
was done in-window rather than deferred. A future session picking it
up cold from the findings log would have had to reconstruct the
diagnostic.

Recommendation for the next window: hold to one finding, unless the
same "surface mid-session with the mechanism already in hand" pattern
recurs. The plan's one-per-window default is still the right shape for
findings found in the audit or filed earlier.

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
