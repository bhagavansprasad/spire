# SPIRE — Session Handoff, 2026-09-19

**This file supersedes the 2026-09-18 handoff.** The Phase 1 audit is
**complete**. Every section (§A through §H) is closed. The findings log
runs F-001 through F-040. This handoff is the launch pad for Phase 2 —
correctness work — and it is **self-contained**: no other file needs to
travel with it.

**Read this first.** Then read `docs/audit/phase-1-audit.md` (the audit)
and `docs/audit/findings-log.md` (the log).

---

## What is closed

**Phase 1 — Audit & Baseline — complete.**

- **§A — Registry drift map.** Closed. Every §A.1 and §A.2 row has a
  state. A-16 (`po_status` untaught, `relationship_phrase` dead KG rows)
  and A-20 (aggregate tools registered in code, not KG) are `disagree`,
  with A-16 probed clean.
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
2026-09-19. The merge commit is `7165f84`; the handoff commit on top of
it is `21c99d8`. Phase 2 spawns its own branch from here.

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
  `{"gemini-3.5-flash"}`) and is available if the decision reverses.
  Re-open only if the user asks.

- **CF-3 — closed 2026-09-18.** Corpus-consistency guard. New file
  `tests/test_corpus_consistency.py`, 116 lines, 3 tests passing.
  Asserts byte-identical and case-normalized prompt groups carry
  identical module sets. Baseline: 19 byte-identical groups, 2
  case-normalized, zero drift at both layers. Paraphrases are
  deliberately not checked — Phase 3f's deterministic classifier makes
  the module set a function of entity synonyms, not a model's one-shot
  judgement.

- **CF-4 — closed 2026-09-18.** Register cross-index. The register at
  `docs/archive/pre-plan/spire_overnight_findings.md` (one commit,
  content frozen 2026-08-14, now correctly archived). Cross-walk of its
  35 items against the F-NNN log:
  - **6 covered directly:** register #7 → F-027, #26 → F-036, #29 →
    F-035, #32 → F-001, #33 → F-010/B-04, #35 → F-016.
  - **4 by class:** register #6 → F-034, #27 → F-012, #31 →
    F-014/F-021, #34 → F-014.
  - **4 uncovered, disposed of:** register #9 retired (stale — corpora
    show all three 1252 prompts refusing identically); register #5
    folded into F-015 (same mechanism, same shape); register #1 → Phase
    4 (LLM-synthesis theme, not a §B finding); register #30 → Phase 2
    (perf defect, below).

**The register is NOT required reading for Phase 2.** Its Phase 0 curl
commands are transcribed below; its cross-index is the CF-4 section
above; its register #30 detail is below. The file stays as a dated
artifact and should not be attached to future windows.

---

## The register's #30 — Phase 2 pickup

Not in §B.1 because §B was scoped to prompt failures, not performance
defects. It is a real defect with a named fix. Phase 2 opens it directly
from this handoff; no F-NNN needed.

`Compare ordered vs invoiced for our top 3 suppliers` issues an
unfiltered PO fetch — pages all 17,447 POs before narrowing client-side.
Exceeds the pod's upstream timeout (145.7s on the 06_slow run; the run's
only errored prompt). The single/named compare is bounded and completes
in ~26s. Fix: rank top-N suppliers first (cheap), then fetch only their
POs — mirroring the spend-ranking path's select-then-detail order.

---

## Phase 2 — Phase 0 curls

Run against pod `eqjz`. `IKS_*` env vars are already exported. All
read-only; no state change. Transcribed from the archived register so
the register need not travel.

**#2 — supplier all / active totals**

```
curl -s --compressed -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?onlyData=true&limit=1&totalResults=true" \
  | python -c "import sys,json;print('all =', json.load(sys.stdin)['totalResults'])"
```

NOTE: `q=Status='ACTIVE'` does NOT work on this pod (returns 0). Count
active client-side instead:

```
curl -s --compressed -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?onlyData=true&limit=1000&fields=SupplierNumber,Status" \
  | python -c "import sys,json;from collections import Counter;print(Counter(r['Status'] for r in json.load(sys.stdin)['items']))"
```

**#4 — PO 2144 id-type**

```
curl -s --compressed -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/purchaseOrders/2144?onlyData=true&fields=POHeaderId,OrderNumber,Supplier" | python -m json.tool
```

```
curl -s --compressed -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/purchaseOrders?q=OrderNumber='2144'&onlyData=true&totalResults=true&limit=1" | python -c "import sys,json;print('OrderNumber=2144 total =', json.load(sys.stdin)['totalResults'])"
```

Expected: `2144` is a valid POHeaderId (→ OrderNumber `162352`, EIP Inc);
as an OrderNumber it returns 0. This is F-013's shape.

**#7 — TaxpayerCountryCode**

```
curl -s --compressed -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?onlyData=true&limit=5&fields=SupplierNumber,Supplier,TaxpayerCountryCode" | python -m json.tool
```

Expected: field is real and populated, but nullable (register noted one
supplier with `None`). Register #7 → audit F-027.

**#9 — supplier 1252**

No separate curl. Uses #2's output — check whether 1252 is present and
its `Status`. Register #9 is retired (see CF-4).

---

## Pod-state observations to carry forward

- **Pod growth is real and ongoing.** Supplier count: 431 (golden
  capture) → 450–455 (audit) → 593 → 600 → 620 → 656 → current.
  Golden files and pod-dependent counts will keep drifting.
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

Tracked, modified, and carried into a recent commit. It contains live
credentials including several commented-out alternates. §7.3.1's
untrack-and-rotate task and E-05's deferred-untrack item both apply;
E-05 remains deferred per plan. The values are in the current tree's
history, not just an old branch.

Do not add `personas.yaml` to any future commit. Named `git add`, never
`-A`.

---

## Working process — unchanged

The S0–S8 evidence standard, the one-command-at-a-time rule, the
anchor-block-verify loop, the nested-fence rule, the three update
disciplines — all unchanged from the 2026-09-18 handoff. Read
`docs/spire-robustness/WORKING_STYLE.md` before any finding work.

**Batch audit-file edits** use a python-heredoc script that reads the
file, applies a list of `(label, old, new)` string replacements, asserts
each anchor's count is exactly 1, and writes only on success. Faster and
safer than sed; the script is atomic — one bad anchor and nothing is
written. Used for the last several batches.

**Findings-log inserts** keep the anchor-block-verify loop: single-line
anchor + `~~~`-fenced block (outer `~~~` if content contains ```) +
verification commands. The anchor IS the thing that must survive
(append-only discipline).

---

## Context bundles — how to request code

Code is shared as **bundles**, not individual files. `context_bundles.yaml`
at the repo root defines them; `build_context.py` builds them into
`context_out/context_<name>.md`.

Bundles that matter for Phase 2 work:

- **`graph_kg`** — KG schema, loader, rebuild scripts, executor, fusion client.
- **`parser_planner`** — draft, parser, router, context_assembly, vocabulary, planner, plan_builders, lookup, registries, cached_llm, prompt_cache.
- **`parser_context`** — every `.sysprompt` block plus `order.manifest` and `classifier_menu.sysprompt`.
- **`mcp_server_tools`** — the 34 MCP tools and the server.
- **`synthesizer`** — synthesizer, ar, p2p, aggregation, response_validation, local_summary, ranking_summary, prompts, pipeline.

To build all:

    python build_context.py --all

To build one:

    python build_context.py parser_planner

Output lands in `context_out/`. A full explainer lives in
`docs/developer/context_bundles.md`.

**NOT in any bundle:** `personas.yaml` (credentials, excluded), and
`docs/archive/*` (excluded by rule). Anything from those paths must be
pasted directly.

---

## What to read first, in order

1. This file.
2. `docs/audit/phase-1-audit.md` — top paragraph for state, then §B.6
   (the audit-row-to-finding map).
3. `docs/audit/findings-log.md` — skim F-001 through F-040.
4. `docs/spire-robustness/WORKING_STYLE.md` — the evidence standard.

**That is the complete list.** No register, no bundle, no Doc A. Doc A
(§8) is needed only when a specific Phase 2 fix needs the design
contract, requested then.

---

## Phase 2 — the next window's work

Phase 2 is Correctness. The audit produced the bug list; Phase 2 turns
it into zero. Doc A §8 defines the design. Theme order:

- **Theme C — field synonyms & projection safety.** Largest cluster,
  highest payoff. Register #7, #12, #31, #34; audit F-014, F-017,
  F-021, F-027.
- **Theme B — refusal correctness & format.** Register #6, #11, #29;
  audit F-034, F-035.
- **Theme D — parser robustness & PO reference.** Register #4, #10,
  #32; audit F-001, F-006, F-013.
- **Theme A — local synthesis (LLM elimination).** Register #1; the
  umbrella. Measured 56 → 5 synth calls; two shapes remain
  (address-target list, single PO + buyer).
- **Theme E — count / sample consistency.** Register #2, #14, #26,
  #27, #33, #35, #30; audit F-010, F-012, F-016, F-036.

Phase 2 opens with the register's own Phase 0 curls (above), then
Theme C.

Phase 2 is **fixing**, one bug per branch/PR, one regression test each,
no bundling. Not investigative. Do not bundle bugs.

---

## First steps in the new window

1. **Confirm ground truth.**
   - `git log --oneline -3` (should show Phase 1's merge on
     `hardening-master` at `7165f84`, handoff commit at `21c99d8`;
     Phase 2 spawns its own branch from here).
   - `pytest -q` (expect 1011 passed / 22 deselected — but only if the
     pod is up; otherwise expect 957 passed / 54 failed, all 503).
   - MCP server up; `personas.yaml` resolves to pod `eqjz`.

2. **Read the four files listed above.** Confirm the summary in this
   handoff matches what the audit and log actually say.

3. **Run Phase 2's Phase 0 curls** — the four blocks above. Promotes
   register #2, #4, #7, #9 from suspected to verified.

4. **Open Phase 2.** Per Doc A §8. Start with Theme C.

5. **Do not touch `config.py` (CF-2) unless the user asks.** It is
   parked.

---

*End of handoff.*