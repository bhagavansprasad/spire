# SPIRE — Session Handoff, 2026-09-20

**This file supersedes the 2026-09-19 handoff.** Phase 1 is closed; Phase 2
has begun. Three findings from the Phase 2 sweep are already shipped:
F-041 (AR invoice child phrasings, PR #151), F-042 (address phrasings,
PR #152), and F-043 (Site/Classification includes, PR #152).

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
- F-006 — alpha-prefixed OrderNumber accepted at the MCP boundary — `verified`,
  PR #154
- F-007 — requested-and-empty AR-invoice children now acknowledged — `fixed`
  (2026-09-22), branch `phase-2-fix-F007-empty-child-ack`, commits
  `779cd12` + `09ab128`, PR #155

Confirmed (S0–S8 walked) — none outstanding (F-001 shipped 2026-09-22,
PR #153 merged):
- **F-001** (fixed) — `list_all` is declared (`models.py:141`), read by the
  planner's guard (`planner.py:199`), and never written. `parser.py:120`
  defines `_is_explicit_po_list(prompt: str) -> bool`; the only other
  reference is a comment at `router.py:216` naming it as a "deterministic
  code" step that should run post-parse. No source file calls it. So
  `intent.list_all` stays `False` on every parse, and any filter-less
  PurchaseOrder intent refuses with `missing_identifier` — "no explicit
  list request" — even when the user typed exactly that. Reproducer:
  `python scripts/promptkit.py --run --prompt "list purchase orders"`.
  S0–S8 all pass; the harm (S1) is refusal of an in-scope prompt; the
  falsifier (S5) is any caller setting `list_all=True`.

---

## First steps in the new window

1. **Confirm ground truth.**
   - `git log --oneline -5`
   - `git status`
   - `pytest -q` (expect the same count as the last green run;
     if the pod is down, expect `957 passed, 54 failed` — the 54 are
     pod-dependent, per the 2026-09-19 handoff's design note)

2. **Read the playbook first.** `docs/AUDIT_AND_FIX.md`. It has:
   - where everything lives,
   - what to work on (open `docs/phase-2/FIX_PLAN.md`, take the top
     `not-started` row),
   - how to reproduce / classify / fix / verify / track,
   - the recovery path if context is lost.

3. **Open F-015.** It is the next task — F-007 shipped 2026-09-22 (see
   the Shipped list above). Cluster 1 (synthesizer narration); per
   `docs/phase-2/FIX_PLAN.md` §4 order, F-015 goes next: a truncated-
   to-zero result narrated as a clean "not found".

   Reproducer:
   `python scripts/promptkit.py --run --prompt "Show receipts for ABC Corporation Americas at Santa Clara" --show-stages`

   The finding lives in `docs/audit/findings-log.md`. Read it and its
   `docs/phase-2/FIX_PLAN.md` §5 row, then follow Phase 2 §8.3:
   - Severity: wrong-narration (a sampled/incomplete result presented
     as complete).
   - Deterministic: single-run test suffices.
   - Branch: `phase-2-fix-F015-empty-bucket-truncation`.
   - Regression test: the prompt returns truncation_notes non-empty
     and a summary that names the cap, not a clean "no receipts"; a
     genuinely empty entity query still returns the clean "no
     receipts" summary with no truncation note.
   - Byte-diff: the prompt is not one of the three goldens; no golden
     update expected.
   - Mechanism (already in the finding): the synthesizer's
     `_all_buckets_empty` shortcut fires before truncation is
     consulted, so an empty bucket that arrived via a truncated fetch
     is narrated as "nothing found" rather than "examined a capped
     sample". The fix likely lives in that early return.

4. **Do not touch `config.py` (CF-2).** Parked by user decision.

---

## Ledger reconciliation done this session

Invariants in `AUDIT_AND_FIX.md` were broken before this session:

- F-041's findings-log status said `root-caused, not fixed` while its
  FIX_PLAN row said `verified`. Both now `verified`.
- F-009's FIX_PLAN row said `not-started` while its fix had shipped as
  F-042's branch. Both findings-log and FIX_PLAN now record it as
  fixed via F-042 / PR #152.
- F-043 was missing from both documents. Both now carry it.

If you find another invariant violation in the next window, fix it as
part of the first commit of that session.

---

## Open work beyond F-001

Ordered by §8.3.1 severity. Reference for planning the window after
the next one.

**Missing-capability:**
- F-003 — three PO aggregation ops unreachable from a scoped parse;
  `modes/` folder in neither `_TIER1` nor `KNOWN_MODULES`. F-004 falls
  out of this.
- F-004 — PO-value ranking misroutes to a comparison op.
- F-006 — alpha-prefixed `OrderNumber` crashes `get_purchase_order_by_id`.
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
- F-015 — truncated-to-zero result narrated as clean "not found".
- F-017 — `Description` on a PO-lines include classified unresolved.
- F-019 — account number routed into `by_customer_name`.
- F-020 — supplier-contacts summary flattens 47 names into one sentence.
- F-039 — "under-invoiced" over-claim where 97% of invoices are excluded.

**Cosmetic / hygiene / cost:**
- F-002 — `promptkit.py` calls `classify_modules` twice per prompt.
- F-033 — `ReceivablesInvoiceLine` refusal's Example is the failing prompt itself.
- F-036 — truncation note says "examined for filtering" on an unfiltered fetch.
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
4. The topmost open finding in `docs/audit/findings-log.md` — F-001.

That is the complete list. The audit's §B.6 map is a lookup when you
need it, not required reading.

---

*End of handoff.*
