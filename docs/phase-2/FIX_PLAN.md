# SPIRE — Phase 2 Fix Plan


**Phase:** 2 — Correctness
**Created:** 2026-09-19
**Status:** Open — no fixes started
**Scope:** Fix every confirmed bug the Phase 1 audit identified.
**Companion files (created lazily):** `docs/phase-2/fixes/F-NNN.md` —
one per fix, opened when its bug is started, frozen when its PR merges.

---

## 1. Purpose

The Phase 1 audit produced a list of confirmed bugs. This document is
the plan for turning that list into zero. It carries: the fix list, the
categorization, the fix order, the verification standard, the testing
strategy, the per-bug tracking ledger, and the multi-window protocol.

This is the *fix* record. The audit stays the *problem* record. Neither
duplicates the other.

---

## 2. Scope

**In scope — 24 items.**

- 23 confirmed bugs from the audit (§B.6 confirmed rows, plus three
  confirmed rows that surfaced in §D).
- 1 performance defect carried by the Phase 1 handoff (register #30).

**Out of scope.**

- Closed-as-not-a-bug items (B-10, B-11, B-12, B-15, B-16, B-18, B-21,
  B-c1, B-c2, B-c3) — already investigated and dismissed.
- Observations and test hygiene (F-031, F-037, F-038) — not bugs.
- New findings during Phase 2 — see §10.
- `src/spire/config.py` — CF-2, parked by user decision.

---

## 3. Fix clusters

Grouped by **fix site** (which file changes), not by symptom. Fix-site
is what determines whether two fixes collide in the same function.

| # | Cluster | Primary fix site | Items |
|---|---|---|---|
| 1 | Synthesizer narration | `synthesizer/synthesizer.py`, `aggregation.py`, `local_summary.py` | F-007, F-008, F-010, F-012, F-015, F-020, F-036, F-039 |
| 2 | Field projection | `nl_parser/intent_validation.py`, `graph/pipeline.py`, `rendering/formatters.py` | F-014, F-017, F-021, F-027 |
| 3 | Parser schema gaps | `nl_parser/draft.py`, `planner/models.py`, `nl_parser/parser.py` | F-001, F-016 |
| 4 | Parser routing / filters | parser `.sysprompt` files, `scripts/sql/kg_schema.sql`, tool arg lists | F-009, F-011, F-018, F-019 |
| 5 | Capability reachability | `nl_parser/context_assembly.py`, `nl_parser/draft.py` | F-003, F-004 |
| 6 | Planner arg routing | `planner/plan_builders.py` (+ possibly `purchase_order_by_id.py`) | F-006 |
| 7 | Refusal content | `nl_parser/capability.py` | F-033 |
| 8 | Tooling / perf | `scripts/promptkit.py`; compare path in `compare_orders_to_invoices.py` + `plan_builders.py` | F-002, Reg #30 |

**Why this axis.** Cluster 1 is 8 items that all touch the same three
synthesizer files. Doing them in one pass avoids re-reading the same
code eight times. Cluster 2's four items share
`_FIELDS_SATISFIED_BY_INCLUDE` and `_project_outputs`. Cluster 4's four
items each edit a `.sysprompt`, and each edit triggers a full
`--validate` re-run — batching them saves three re-runs.

---

## 4. Fix sequence

Order and rationale. Every fix gets its own branch and its own PR; the
order is a queue, not a batch.

| Order | Item | Rationale |
|---|---|---|
| 1 | F-002 | Cost baseline. Halves promptkit's per-prompt LLM calls; every subsequent verification run is cheaper. Do it first so all later cost comparisons are clean. |
| 2 | F-033 | Warm-up. One-line fix in a dict; exercises the branch → PR → verify loop end-to-end on something trivial. |
| 3 | F-006 | Crash. Highest severity single item. Independent of all clusters. |
| 4 | Cluster 1 (8) | Largest cluster. Within it: F-007 first (its signature change unblocks F-015), then F-015, then F-012 + F-036 (share the f-string), then F-010, F-008, F-020, F-039. |
| 5 | Cluster 2 (4) | F-017 / F-027 / F-014 landed 2026-09-23. F-021 reclassified to F-051 (caller-side gate, not the recorded synthesizer / formatter sites); Cluster 2 closes with three fixes and one reclassification. |
| 6 | Cluster 3 (2) | F-001 first (more urgent), F-016 second. Both use the post-parse-helper pattern. |
| 7 | Cluster 4 (4) | One `--validate` re-run covers all four sysprompt edits. Do them in sequence, run validate once after the last. |
| 8 | Cluster 5 (2) | Fix F-003; F-004 may fall out. If it does, close F-004 as a side-effect and note it in its fix file. |
| 9 | Reg #30 | Perf. Independent; can slip to Phase 6 if the fix turns out to be architectural. |
| 10 | F-044 | Crash, mechanism settled (double-encoded `value_json`, `draft.py::to_intent`). Closed as PR #158, ahead of F-010 — the deliberate §8.3.1 reorder is recorded in the fix file. |
| 11 | F-046, F-047, F-048 | Follow-ons from the F-011b sweep (findings-log 2026-09-23). F-046 first (cleanest mirror of F-011's split, no new tool arg). F-047 second (adds a LastUpdateDate column to `search_purchase_orders`). F-048 last (highest blast radius — parser default for vague adjectives; V9 mandatory). |

---

## 5. The ledger

**The single source of truth for progress.** 24 rows. One row per bug.
Never reused, never renumbered. Updated after each PR merges.

States: `not-started` → `in-progress` → `fixed` → `verified` → `closed`.

- **in-progress** — branch created, work happening.
- **fixed** — code committed, regression test written and shown to fail
  without the fix.
- **verified** — V-standard (§6) passed, PR merged.
- **closed** — audit row updated, ledger row frozen.

| ID | Kind | Cluster | Primary fix site | State | PR | Date |
|---|---|---|---|---|---|---|
| F-002 | cost | 8 | `scripts/promptkit.py`, `src/spire/config.py` | verified | #149 | 2026-09-19 |
| F-033 | wrong-narration | 7 | `nl_parser/capability.py` | verified | #150 | 2026-09-19 |
| F-006 | crash | 6 | `mcp_server/server.py` (annotation, not `plan_builders`) | verified | #154 | 2026-09-22 |
| F-007 | wrong-narration | 1 | `synthesizer/synthesizer.py` | verified | #155 | 2026-09-22 |
| F-015 | wrong-narration | 1 | `synthesizer/synthesizer.py` | verified | #156 | 2026-09-22 |
| F-012 | wrong-data | 1 | `synthesizer/synthesizer.py`, `local_summary.py` | closed | #157 | 2026-09-22 |
| F-036 | wrong-narration | 1 | `synthesizer/synthesizer.py` | closed | #157 | 2026-09-22 |
| F-010 | wrong-data | 1 | `synthesizer/aggregation.py` | verified | #159 | 2026-09-22 |
| F-008 | wrong-data | 1 | `mcp_server/tools/supplier_classifications.py` | verified | #160 | 2026-09-22 |
| F-020 | wrong-narration | 1 | `synthesizer/synthesizer.py`, `rendering/formatters.py` | verified | #161 | 2026-09-23 |
| F-039 | wrong-narration | 1 | `synthesizer/aggregation.py` | verified | #162 | 2026-09-23 |
| F-017 | missing-projection | 2 | `nl_parser/intent_validation.py` | fixed | — | 2026-09-23 |
| F-018 | wrong-refusal | 4 | `mcp_server/tools/invoices.py`, parser sysprompt, KG, `planner.py` | fixed | — | 2026-09-23 |
| F-027 | missing-projection | 2 | `nl_parser/parser.py` (post-parse), `rendering/formatters.py` | fixed | — | 2026-09-23 |
| F-014 | missing-projection | 2 | `graph/pipeline.py`, `nl_parser/parser.py` (post-parse) | fixed | — | 2026-09-23 |
| F-021 | missing-projection | 2 | reclassified to F-051 — no separate fix on this branch | closed-as-reclassified | — | 2026-09-23 |
| F-001 | missing-capability | 3 | `nl_parser/parser.py` | verified | #153 | 2026-09-22 |
| F-016 | missing-capability | 3 | `nl_parser/draft.py`, `planner/models.py`, `plan_builders.py` | not-started | — | — |
| F-009 | missing-capability | 4 | parser sysprompt, `order.manifest` | verified | #152 (via F-042) | 2026-09-19 |
| F-011 | missing-capability | 4 | `scripts/sql/kg_schema.sql`, parser sysprompt, `plan_builders.py` | fixed | — | 2026-09-23 |
| F-019 | wrong-data | 4 | `mcp_server/tools/customer_account_by_name.py`, parser sysprompt, KG, `parser.py` | fixed | — | 2026-09-23 |
| F-003 | missing-capability | 5 | `nl_parser/context_assembly.py`, `draft.py` | not-started | — | — |
| F-004 | wrong-data | 5 | (falls out of F-003) | not-started | — | — |
| Reg #30 | perf | 8 | `plan_builders.py`, `compare_orders_to_invoices.py` | not-started | — | — |
| F-041 | missing-capability | 9 (router + parser) | `scripts/sql/kg_schema.sql` (entity_synonym), `context/receivables/b_ar_invoice_lines.sysprompt`, `b_ar_dff.sysprompt`, `b_ar_tax_lines.sysprompt` | verified | #151 | 2026-09-19 |
| F-043 | missing-capability | (router + parser + synthesizer) | `vocabulary.py`, `intent_validation.py`, `supplier_sites.py`, `supplier_classifications.py`, `p2p.py`, `synthesizer.py`, `formatters.py` | verified | #152 | 2026-09-19 |
| F-042 | missing-capability | (F-009) | duplicate of F-009 — no separate fix on this branch | closed-as-duplicate | — | 2026-09-19 |
| F-045 | wrong-data | 1 | `mcp_server/tools/purchase_orders.py` (composite bound), `synthesizer/synthesizer.py` (capped-note wording) | not-started | — | — |
| F-046 | missing-capability | 4 | `scripts/sql/kg_schema.sql`, parser sysprompt, `planner.py`, `context_assembly.py` | verified | #164 | 2026-09-23 |
| F-047 | missing-capability | 4 | `mcp_server/tools/purchase_orders.py`, `mcp_server/server.py`, `plan_builders.py`, `scripts/sql/kg_schema.sql`, parser sysprompt, `context_assembly.py` | verified | #164 | 2026-09-23 |
| F-048 | missing-capability | 4 | parser sysprompt, `context_assembly.py` | verified | #164 | 2026-09-23 |
| F-049 | wrong-refusal | 4 | parser sysprompt, `context_assembly.py` | not-started | — | 2026-09-23 |
| F-050 | missing-capability | 5 | `nl_parser/context_assembly.py` (`_TIER1`) | not-started | — | 2026-09-23 |
| F-051 | missing-projection | 2 | `scripts/promptkit.py`, `scripts/run_prompt_set.py`, `scripts/run_graph.py` | not-started | — | 2026-09-23 |
| F-044 | crash | 3 | `nl_parser/draft.py` | closed | #158 | 2026-09-22 |

**Session log.** The window label for each fix is recorded in the
fix file's header as `**Session:** 07_SPIRE_Phase2_BugFixing_NN`.
This session (`_01`) closed F-002. The `NN` counts windows, not
fixes — F-033 and its neighbours in the same window share the label.

---

## 6. Verification standard V0–V9

Every fix walks this checklist. Not every step applies to every fix;
the fix file records which steps ran.

**V0 — State the fix in one sentence.** What changed and where. Written
into the fix file before any code is touched.

**V1 — Reproducer passes.** The exact prompt from the F-NNN entry, run
through `promptkit.py --run --show-stages`. Output pasted into the fix
file. The output must show the bug is gone.

**V2 — Paraphrase passes.** The same request reworded. Confirms the fix
isn't phrasing-specific.

**V3 — Sibling prompt does NOT change.** A prompt in the same class that
was already correct. Proves the fix didn't over-reach. Output pasted.

**V4 — Negative prompt still behaves as before.** A prompt that should
still refuse or still fail the same way. Proves no accidental
broadening.

**V5 — Golden files unchanged.** The three goldens in
`docs/audit/golden/`. If the bug was one of them, record the new output
and note the intentional change.

**V6 — Full pytest passes.** `pytest -q` shows the same pass count plus
the new regression test. Any regression is a blocker.

**V7 — Regression test is real.** The new test *fails* without the fix.
Verified by stashing the one-line change, running the test, seeing red,
restoring, seeing green. Not optional.

**V8 — N≥20 if the fix touches an LLM-adjacent path.** Parser,
classifier, synthesizer LLM path. Twenty runs, output distribution
recorded.

**V9 — Full `--validate` if the fix touches a `.sysprompt`.** All 12
prompt sets. Compare against the 236/240 baseline.

**Per-cluster V-step map.**

| Cluster | Required | Conditional |
|---|---|---|
| 1 (synthesizer) | V0–V7 | — |
| 2 (projection) | V0–V7 | — |
| 3 (schema) | V0–V7 | V8 if parser touched |
| 4 (sysprompt) | V0–V7, V9 | V8 |
| 5 (reachability) | V0–V7 | V8 |
| 6 (planner arg) | V0–V7 | — |
| 7 (refusal) | V0, V1, V3, V6, V7 | — |
| 8 (perf/cost) | V0–V7 | — |

---

## 7. Testing strategy — four layers

| Layer | Scope | When | Cost |
|---|---|---|---|
| **L1 — targeted** | 4–5 prompts: reproducer, paraphrase, sibling, negative, adjacent-class | Every fix, at fix time | ~1 min |
| **L2 — source corpus** | Re-run the source prompt file for that bug | Every fix, after L1 | ~2–5 min |
| **L3 — full validate** | All 12 sets, 240 prompts | Batched with `.sysprompt` edits | ~2 min |
| **L4 — pytest** | The new regression test, then full suite | Every fix, after L2 | ~5 min |

**On "one prompt isn't enough".** Every fix gets at least four probes:
the reproducer, a paraphrase, an already-correct sibling, and a
should-still-refuse negative. If any of the four behaves unexpectedly,
the fix is over- or under-scoped — fix before merging.

**Commands (exact invocation to confirm at first use).**

    python scripts/promptkit.py --run --prompt "<text>" --show-stages    # L1
    python scripts/promptkit.py --run --prompt-file scripts/prompts/<NN>_*.txt   # L2
    python scripts/promptkit.py --validate                                # L3 (flag TBC)
    pytest -q                                                             # L4

---

## 8. Per-fix workflow

One bug at a time. The order is §4.

1. **Open the fix file.** Create `docs/phase-2/fixes/F-NNN.md` from the
   template in §11. Read the F-NNN entry in the findings log.
2. **Branch.** `phase-2-fix-F-NNN-<slug>` off `hardening-master`.
3. **Write the test first.** It must fail. Commit the failing test.
4. **Write the fix.** Smallest change that makes the test pass.
5. **Run V0–V9.** Record each output in the fix file.
6. **Update the audit.** The B-row (and any §D row) becomes "fixed in
   PR #N". Rows close in place.
7. **Update the ledger.** State → `verified`. PR number, date.
8. **PR.** Use the template in §11. Merge.
9. **Freeze the fix file.** State → `closed`. Never edited after.

---

## 9. Multi-window protocol

Phase 2 will span multiple sessions. Each new window reads three
things, in order:

1. **`docs/phase-2/FIX_PLAN.md`** — this file. The ledger (§5) tells you
   what's done and what's next.
2. **The next F-NNN entry** in `docs/audit/findings-log.md`.
3. **`docs/audit/phase-1-audit.md` §B** for the corresponding audit row.

Nothing else. No other file is required to resume.

**Length handling.** The ledger (§5) is 24 rows — always pasteable. The
per-fix files (`fixes/F-NNN.md`) are opened one at a time and never
pasted wholesale; a new window reads only the fix file for the bug it
is about to work on.

**Resume command.** At session start:

    git log --oneline -3
    git status
    pytest -q

Then read §5 and pick the first `not-started` row in §4's order.

---

## 10. Handling new findings during Phase 2

If a fix reveals a new bug, or a bug turns out to be two bugs:

- **New bug.** Add a new F-NNN to the findings log. Add a new row to the
  ledger §5. Append to the sequence §4.
- **Split bug.** Keep the original F-NNN for the primary; add a new
  F-NNN for the sibling. Note the split in the original's fix file.
- **Won't fix.** Move the row to `deferred`; record why in the fix file.
  Deferred items carry forward to a future phase.

Never silently expand a fix's scope. If a fix touches a second bug, that
second bug gets its own row and its own PR.

---

## 11. Templates

Two templates. Both are indented text (not fenced) so this document
copies as one block. Copy from here when needed.

### 11.1 Fix file template

Saved as `docs/phase-2/fixes/F-NNN.md` when a bug is started.

    # F-NNN — <one-line title>

    **Branch:** `phase-2-fix-F-NNN-<slug>`
    **PR:** #
    **State:** in-progress | fixed | verified | closed

    ## V0 — Fix statement
    <one sentence: what changed and where>

    ## V1 — Reproducer

        <command>
        <output>

    ## V2 — Paraphrase

        <command>
        <output>

    ## V3 — Sibling (unchanged)

        <command>
        <output>

    ## V4 — Negative (still refuses)

        <command>
        <output>

    ## V5 — Goldens

    <diff or "unchanged">

    ## V6 — pytest

        <summary line>

    ## V7 — Test fails without the fix

    <stash + run + red; restore + run + green>

    ## V8 — N≥20 (if applicable)

    <distribution>

    ## V9 — --validate (if applicable)

    <pass count vs 236/240>

    ## Deviations from the F-NNN entry's suggested fix

    <what changed and why>

    ## Not checked

    <what a future session should look at>

### 11.2 PR template

Copied into the GitHub PR body when raising the PR. Not saved as a
separate file.

    ## Phase 2 — Fix F-NNN

    **Audit row:** B-NN / D-NN
    **Cluster:** N
    **Fix file:** docs/phase-2/fixes/F-NNN.md

    ### Change
    <one paragraph>

    ### V-standard applied
    <list of V-steps run>

    ### Test evidence
    - New regression test: tests/<file>::<test>
    - `pytest -q`: <pass count>
    - `--validate`: <pass count> (if V9)

    ### Rollback
    `git revert <sha>`.

    ### Deviations from the F-NNN entry
    <none / list>

---

## 12. Session start checklist

At the start of every Phase 2 window:

- [ ] `git log --oneline -3` — HEAD on `hardening-master`
- [ ] `git status` — clean tree
- [ ] `pytest -q` — 1011 passed / 22 deselected (or pod-down equivalent)
- [ ] Read §5 — pick the first `not-started` row in §4 order
- [ ] Read that F-NNN entry in the findings log
- [ ] Open the fix file from §11.1 template
- [ ] Branch off `hardening-master`

---

*End of Phase 2 Fix Plan.*
