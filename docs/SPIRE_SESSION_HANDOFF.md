# SPIRE — Session Handoff, 2026-09-19

**This file supersedes the 2026-09-18 handoff.** The Phase 1 audit is
**complete**. Every section (§A through §H) is closed. The findings log
runs F-001 through F-040. This handoff is the launch pad for Phase 2 —
correctness work — not a document to maintain.

**Read this first.** Then read `docs/audit/phase-1-audit.md` (the audit)
and `docs/audit/findings-log.md` (the log). This handoff is a launch
pad, not a document to maintain.

---

## What is closed

**Phase 1 — Audit & Baseline — complete.**

- **§A — Registry drift map.** Closed. Every §A.1 and §A.2 row has a
  state. A-16 (po_status untaught, relationship_phrase dead KG rows) and
  A-20 (aggregate tools registered in code, not KG) are `disagree`, with
  A-16 probed clean.
- **§B — Bug inventory.** Closed. §B.6 is the audit-row-to-finding map.
  Every §B row and candidate carries an F-NNN or a documented closure.
- **§C — Dead code inventory.** Closed. C.1 confirmed orphans; C.2
  candidates; C.3 swept 2026-09-18 with C-13 through C-16 added. C-11's
  Confirm corrected. §C.5 lists what was not checked — one item
  (`personas.example.yaml` drift) closed 2026-09-18 with a no-schema-
  drift finding.
- **§D — Inconsistency inventory.** Closed. D-01 through D-15 all
  resolved.
- **§E — In-flight work inventory.** E.4 closed — all four rows
  resolved (E-11 merge path confirmed, E-12 branch found on origin,
  E-13 both merged, E-14 both merged). E.5 accurate.
- **§F — Baseline metrics.** F.1 measured. F.2 token table measured
  (three cells `—`, deliberately deferred). F.3 lists what was not
  measured.
- **§G — Behavioural byte-diffs.** Closed. Two goldens pod-drift only;
  one byte-identical.
- **§H — Probabilistic-behaviour map.** Four nondeterminism closures
  landed (F-022, F-023, F-024, F-040). Remaining observations are map
  content, not action items.

**Findings-log range:** F-001 through F-040. All closed or classified.

**Merged:** PR #148, `Phase1-Audit-and-Baseline` → `hardening-master`,
2026-09-19. `hardening-master` is now at `7165f84`. Phase 2 spawns from
here.

---

## Baseline metrics — measured 2026-09-18/19

- **Test suite:** `1011 passed, 22 deselected in 3:43`. Supersedes the
  prior handoff's cited 913/18; the suite grew ~95 tests since that
  snapshot. Confirmed by two runs: `957 passed + 54 failed` with the pod
  down (all 503s), then `1011 passed` after pod recovery. The two
  reconcile exactly.
- **Test-suite design note for Phase 4b.** The 54 pod-dependent tests
  are NOT `@pytest.mark.integration` — they only `skipif(not
  PERSONAS_FILE.exists())`. With `personas.yaml` present and the pod
  down they fail rather than skip. The 22 deselected are the genuinely-
  marked integration tests. `pytest -q` is therefore not a pod-
  independent gate today.
- **`--validate`:** cited from the prior handoff at 236/240
  (`gemini-3.5-flash`); not re-run this session. The `gemini-3.1-flash-
  lite` figure of 205/240 is also cited, and is CF-2's motivation.
- **KG tables matching seed:** 9 / 9 (measured A-17).
- **Golden files:** 1 / 3 byte-identical; 2 / 3 pod-drift only (§G).

---

## Carry-forward status

- **CF-1 — closed 2026-09-18.** The unsatisfiable-include / raw-KeyError
  shape. Seven shapes probed directly through `generate_plan`. Six
  refuse with `RefusalError` (flavor `UNSUPPORTED_OPERATION`, offending
  element named): PO + `['Supplier']`, PO + `['POSchedule','Supplier']`,
  PO + `['BogusEntityXYZ']`, Supplier + `['Buyer']` (no edge), Invoice +
  `['Supplier']`, CustomerAccount + `['Supplier']`. One plans — Supplier
  + `['Classification']` — because `HAS_CLASSIFICATION` exists; its
  reverse-only tool makes it unsatisfiable downstream, but
  `validate_intent` gates it before `generate_plan` runs
  (`test_bug2_include_gate.py::test_classification_include_refused`). No
  raw `KeyError` path remains.

- **CF-2 — OPEN, parked by user decision.** `GEMINI_MODEL` silent
  dependency. The swap from `gemini-3.5-flash` to `gemini-3.1-flash-lite`
  measurably degrades routing (236/240 → 205/240) with no warning.
  **Do not action.** User asked not to change `config.py` at this time.
  The shape was decided (warn-not-raise at import, Gemini-only whitelist
  `{"gemini-3.5-flash"}`), documented in this session's conversation, and
  available if the decision reverses. Re-open only if the user asks.

- **CF-3 — closed 2026-09-18.** Corpus-consistency guard. New file
  `tests/test_corpus_consistency.py`, 116 lines, 3 tests passing. Asserts
  byte-identical and case-normalized prompt groups carry identical module
  sets. Baseline: 19 byte-identical groups, 2 case-normalized, zero drift
  at both layers. Paraphrases are deliberately not checked — Phase 3f's
  deterministic classifier makes the module set a function of entity
  synonyms, not a model's one-shot judgement.

- **CF-4 — closed 2026-09-18.** Register cross-index. The register at
  `docs/archive/pre-plan/spire_overnight_findings.md` (handoff pointer
  was to a nonexistent path; correct path recorded here). Cross-walk of
  its 35 items against the F-NNN log: 6 covered directly (register #7 →
  F-027, #26 → F-036, #29 → F-035, #32 → F-001, #33 → F-010/B-04, #35 →
  F-016), 4 by class (#6 → F-034, #27 → F-012, #31 → F-014/F-021, #34 →
  F-014), 4 uncovered — disposed of as: register #9 retired (stale —
  corpora show all three 1252 prompts refusing identically); register #5
  folded into F-015 (same mechanism, same shape); register #1 → Phase 4
  (LLM-synthesis theme, not a §B finding); register #30 → Phase 2
  (genuine perf defect — top-N compare fetches the entire 17,447-PO
  universe before narrowing and times out; fix direction: select top-N
  suppliers first, then fetch only their POs).

---

## The register's #30 — Phase 2 pickup

Not in §B.1 because §B was scoped to prompt failures, not performance
defects. It is a real defect with a named fix. Phase 2 opens it directly
from the register; no F-NNN needed.

`Compare ordered vs invoiced for our top 3 suppliers` issues an
unfiltered PO fetch — pages all 17,447 POs before narrowing client-side.
Exceeds the pod's upstream timeout (145.7s on the 06_slow run; the run's
only errored prompt). The single/named compare is bounded and completes
in ~26s. Fix: rank top-N suppliers first (cheap), then fetch only their
POs — mirroring the spend-ranking path's select-then-detail order.

---

## Pod-state observations to carry forward

- **Pod growth is real and ongoing.** Supplier count: 431 (golden
  capture) → 450–455 (audit) → 593 → 600 → 620 → 656 → 1011 tests
  passed on the current pod. Golden files and pod-dependent counts will
  keep drifting.
- **Module-set ordering varies run-to-run** without affecting the
  answer. Confirmed in F-023, F-032, and §G's diff. The module set is a
  diagnostic, not a correctness signal.
- **Model-prose variance** in `Reason:` lines is real (F-035, F-038).
  Same flavor, same Solution, different Reason text. Not a bug — a
  §H.1-class observation.
- **The parser prompt is at its token ceiling.** Any sysprompt edit
  risks degenerate generation. A parser-prompt fix needs a full 12-set
  `--validate` re-run.
- **The pod (eqjz) is the current demo pod.** `personas.yaml` holds
  credentials; Spire reads `personas.yaml` ONLY. A wrong pod usually
  means the MCP server is stale — restart after any change under
  `src/spire/mcp_server/`.

---

## `personas.yaml` — status

Tracked, modified, and (per the user) carried into a recent commit. It
contains live credentials including several commented-out alternates.
§7.3.1's untrack-and-rotate task and E-05's deferred-untrack item both
apply; E-05 remains deferred per plan. **E-05's next-session entry must
record that the file rode into a commit** — the values are in the
current tree's history, not just an old branch.

Do not add `personas.yaml` to any future commit. Named `git add`, never
`-A`.

---

## Working process — unchanged

The S0–S8 evidence standard, the one-command-at-a-time rule, the
anchor-block-verify loop, the nested-fence rule, the three update
disciplines — all unchanged from the 2026-09-18 handoff. Read
`docs/spire-robustness/WORKING_STYLE.md` before any finding work.

**For batch audit-file edits**, a python-heredoc script that reads the
file, applies a list of `(label, old, new)` string replacements, asserts
each anchor's count is exactly 1, and writes only on success — is faster
and safer than sed, and was the pattern used for the last three batches
this session. The script is atomic: one bad anchor and nothing is
written.

**For findings-log inserts**, the anchor-block-verify loop remains the
pattern — the anchor IS the thing that must survive (append-only
discipline).

---

## Context bundles — how to request code

Code is shared as **bundles**, not individual files. `context_bundles.yaml`
at the repo root defines them; `build_context.py` builds them into
`context_out/context_<name>.md`. The bundles that matter for audit work:

- **`graph_kg`** — KG schema, loader, rebuild scripts, executor, fusion client.
- **`parser_planner`** — draft, parser, router, context_assembly, vocabulary, planner, plan_builders, lookup, registries, cached_llm, prompt_cache.
- **`parser_context`** — every `.sysprompt` block plus `order.manifest` and `classifier_menu.sysprompt`.
- **`mcp_server_tools`** — the 34 MCP tools and the server.
- **`synthesizer`** — synthesizer, ar, p2p, aggregation, response_validation, local_summary, ranking_summary, prompts, pipeline.
- **`scripts`**, **`tests`**, **`prompts`**, **`corpora`** — used in the C.3 sweep.

To build all:

    python build_context.py --all

To build one:

    python build_context.py parser_planner

Output lands in `context_out/`. A full explainer lives in
`docs/developer/context_bundles.md`.

---

## What to read first, in order

1. This file.
2. `docs/audit/phase-1-audit.md` — top paragraph for state, then §B.6
   (the audit-row-to-finding map).
3. `docs/audit/findings-log.md` — skim F-001 through F-040.
4. `docs/spire-robustness/WORKING_STYLE.md` — the evidence standard.
5. `docs/archive/pre-plan/spire_overnight_findings.md` — the register;
   CF-4's cross-index is in this handoff, not in that file.

---

## Phase 2 — the next window's work

Phase 2 is Correctness. The audit produced the bug list; Phase 2 turns
it into zero. Doc A §8 defines the design. The register's theme map
(`docs/archive/pre-plan/spire_overnight_findings.md`) is a defensible
ordering and the audit does not contradict it:

- **Theme C — field synonyms & projection safety.** Largest cluster,
  highest payoff. Fixes #7, #12, #31, #34 in the register; closes F-027,
  F-014, F-021, and F-017 by class in the audit.
- **Theme B — refusal correctness & format.** #6, #11, #29 in the
  register; F-034, F-035, and the refusal-rendering fixes in the audit.
- **Theme D — parser robustness & PO reference.** #4, #10, #32 in the
  register; F-001, F-006, F-013 in the audit.
- **Theme A — local synthesis (LLM elimination).** Register #1; the
  umbrella. Measured at 56 → 5 synth calls; two shapes remain (address-
  target list, single PO + buyer).
- **Theme E — count / sample consistency.** Register #2, #14, #26, #27,
  #33, #35, #30; audit F-010, F-012, F-016, F-036.

Phase 2 opens with the register's own Phase 0 — curl the four suspected
items (#2, #4, #7, #9) to promote them to verified, then begin Theme C.

Phase 2 is **fixing**, one bug per branch/PR, with a regression test each.
Not investigative. Do not bundle bugs.

---

## First steps in the new window

1. **Confirm ground truth.**
   - `git log --oneline -3` (should show Phase 1's merge on
     `hardening-master` at `7165f84`; Phase 2 spawns its own branch from
     here).
   - `pytest -q` (expect 1011 passed / 22 deselected — but only if the
     pod is up; otherwise expect 957 passed / 54 failed, all 503).
   - MCP server up; `personas.yaml` resolves to pod `eqjz`.

2. **Read the five files listed above.** Confirm the summary in this
   handoff matches what the audit and log actually say.

3. **Open Phase 2.** Per Doc A §8. Start with the register's Phase 0
   curls, then Theme C.

4. **Do not touch `config.py` (CF-2) unless the user asks.** It is
   parked.

---

*End of handoff.*