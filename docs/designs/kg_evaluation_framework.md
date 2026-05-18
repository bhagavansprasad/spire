# KG Evaluation Framework

**Phase:** Dynamic Orchestration 03 — KG Population (framework doc)
**Status:** Design document — implementation lives in phases 08 and 09
**Purpose:** Define how Track B's success or failure will be measured, and how we will iterate if results are weak.

This document is locked in *before* phases 04–07 implement the agent-KG integration, so the test bar isn't moved to match the result. The discipline matters: if we write the rubric after seeing the score, the result means less.

Companion docs:
- `kg_schema_v1.md` — what the KG models
- `../phase_a5_baseline_report.md` — Track A baseline this is measured against
- `../spire_poc_log.md` — running log

---

## 1. Why This Framework Exists

The POC's central claim is that a Knowledge Graph helps an LLM agent reason about Fusion better than tool descriptions alone. That claim has to be testable, or it isn't a real claim.

Track A's baseline (`phase_a5_baseline_report.md`) measured 1/7 on the reference prompt across 5 runs. That's the comparison point. The question this framework answers: **how much better must Track B do, and how do we know the KG is what made it better — rather than incidental changes (different prompts, different model behavior, lucky day)?**

Three things must be true for Track B to count as validating the KG hypothesis:

1. Track B scores meaningfully higher than Track A on the same rubric.
2. The improvement is attributable to the KG (not to other changes).
3. The agent is actually using the KG (not ignoring it while still scoring well via other means).

Each gets its own tier below.

---

## 2. Tier 1 — Headline Measurement (Phase 08)

The headline number is "what score does Track B's agent get on the same reference prompt under the same rubric?"

### Protocol

Replicates the phase A.5 protocol exactly. Discipline matters more than ceremony.

- **Same reference prompt, unchanged:**
  > Show me suppliers in US with no invoices in 6 months but with open purchase orders, including the buyer assigned to each.
- **Same 7-step rubric**, scored ✅ / ⚠️ / ❌ per step
- **5 runs**, same prompt each time
- **No prompt engineering, no retries with corrections, no tool-description tweaks**
- **No mid-test fixes** — if a tool breaks, we record the failure and continue; we don't patch it between runs
- **Same scoring rules** — a run scores against the rubric as it actually ran, not as it could have run

### Bands of meaning

These bands are committed to *now*, before the runs. The point is to make the result interpretable without post-hoc rationalization.

| Aggregate score (best of 5 per rubric row) | What it means |
|---|---|
| **1/7 or 2/7** | KG didn't help. Track B failed to beat the baseline. Hypothesis as stated did not hold. Honest write-up required: what specifically didn't work, what we'd try differently, whether further investment is warranted. |
| **3/7 to 4/7** | Partial improvement. KG helped on some clauses, not others. Per-clause dissection required: which rubric rows improved and why, which didn't and why not. |
| **5/7 to 6/7** | Material improvement. Hypothesis validated at POC scale. Proceed to ablation (Tier 2) to confirm attribution. |
| **7/7 across 5 runs** | Strong validation, but suspicious. Inspect carefully for accidental help (system-prompt drift, tools modified mid-development, prompt loosened). If holds up, validated. |

### What "honest write-up" looks like for low scores

If Track B scores 1/7 or 2/7, the temptation will be to find reasons it "almost worked" or to claim "the agent would have done better if X." This temptation must be resisted in writing.

The phase 08 / phase 09 reports must:

- State the score plainly in the first paragraph
- Walk through each rubric row and what the agent actually did vs what was needed
- Identify the specific failure modes (mirroring how A.5 did this — premature termination, parameter confusion, error recovery)
- *Not* claim partial credit beyond what the rubric supports
- *Not* propose fixes-and-rerun until the honest read is captured

The honest read is the deliverable. The fixes can come after, on a different branch.

---

## 3. Tier 2 — Ablation (Phase 09)

The headline measurement answers "did Track B do better?" It doesn't answer "did the **KG** do it?"

### The ablation test

After the Tier 1 runs complete and the headline score is recorded, run a second batch of 5 runs with the **same Track B codebase but with KG-consultation disabled**.

Two ways to disable, depending on how phase 05 wired things in:
- **If KG queries are exposed as MCP tools the agent can choose**: remove them from the tool list passed to the LLM. Same code path, but the agent can't reach the KG.
- **If KG queries are baked into the planning step**: bypass that step; pass the raw prompt and tool list directly, the way Track A did.

Either way, the agent must lose access to the KG without other changes — same model, same tools (minus KG), same system prompt structure.

### Interpreting the ablation

| Tier 1 score | Ablation score | Interpretation |
|---|---|---|
| 5/7 | 5/7 | KG didn't matter. Improvement came from elsewhere (system prompt, tool descriptions, parameter unification, etc.). **The KG hypothesis fails even though Track B "won."** This is the most important honesty test. |
| 5/7 | 3/7 | KG helped meaningfully. The 2-point delta is the KG's contribution. |
| 5/7 | 1/7 | KG was the difference. The full Track B win is attributable to the KG. |
| 1/7 | 1/7 | KG didn't help; ablation confirms. Consistent failure. |
| 2/7 | 5/7 | KG made things *worse*. Possible if the KG misled the agent. Worth investigating; doesn't necessarily kill the architecture, but signals a v1.1 redesign. |

The ablation cost is one extra evaluation phase — maybe 30 minutes of run time plus an hour of write-up. It's the single cheapest insurance against shipping an overstated POC result.

### Confounders to be honest about

The ablation isn't perfect. Even with KG disabled, Track B's agent may have inherited:

- Better tool descriptions written during phase 04 work
- A more sophisticated system prompt
- Better parameter unification across tools
- Generally better engineering hygiene that accumulated through Track B's phases

If the ablation score is markedly better than A.5's 1/7, **those other improvements are doing real work** and should be named in the write-up. The KG's contribution is the *delta* between Tier 1 and Tier 2, not the absolute Tier 2 score.

---

## 4. Tier 3 — Failure-Mode Audit

A score isn't enough on its own. Three behavioral questions need affirmative answers for the result to be trustworthy.

### 4.1 Did the agent actually consult the KG?

Inspect the phase 08 trace files. For each run, count:
- Number of KG-related tool calls (or KG queries, depending on phase 05's design)
- At what step in the reasoning chain they occurred
- Whether their results influenced subsequent tool calls

**Pass condition:** every successful Tier 1 run made at least one KG consultation that demonstrably influenced a later Fusion call. Example: KG consulted, returned that "open PO" means `StatusCode='OPEN'`, agent then called `search_purchase_orders(status='OPEN')`.

**Failure mode caught here:** agent scores 5/7 but never consulted the KG. The headline number "validates" the KG architecture but in reality the LLM solved it from docstrings (somehow). Not a real validation.

### 4.2 Did the KG mislead the agent in any run?

For each KG consultation, verify the response was correct:
- Did the join key returned by the KG match what Fusion's endpoint actually expects?
- Did the vocabulary lookup map to a real Fusion code?
- Did the pattern definition's mechanics, if followed literally, produce a valid call?

**Pass condition:** zero misleading KG responses in the 5 runs. Or, if misleads occurred, they are catalogued and a v1.1 schema update is identified to fix each.

**Failure mode caught here:** the KG returned wrong/stale info, the agent dutifully followed it, the run failed. This is the most painful failure mode because the agent did the right thing and the KG was the bug. Documenting these is how the KG improves.

### 4.3 Did the KG cost more than it gained?

Compare Tier 1 traces against A.5 traces on three dimensions:
- **Tool call count** — how many calls did the agent make per run?
- **Token usage** — total tokens in/out (approximate from message lengths)
- **Wall-clock time** — from `agent_started` to `agent_finished` in the trace

**Pass condition:** Track B uses at most ~2x the Track A budget on any dimension for an equivalent answer. (Track B *should* use more — that's the point — but not 5x more for a 1-step improvement.)

**Failure mode caught here:** the "compounding intelligence" claim in `spire_design_alternatives.md` is weakened if every KG consultation adds three LLM turns. If Tier 1 takes 30 tool calls to pass 5 rubric rows where A.5 took 5 calls to pass 1, that's a different story than "KG made the agent smarter."

---

## 5. The Iteration Loop

If Tier 1 + Tier 2 + Tier 3 don't all pass, the POC isn't done. The framework is:

1. **Diagnose.** Which of the three tiers failed, and on which specific rubric row or behavioral question?
2. **Localize.** Is the gap in (a) the schema (v1.1 needs more), (b) the query tools (phase 04 missed something), or (c) the integration (phase 05 didn't wire the KG in well enough)?
3. **Smallest change that addresses the diagnosis.** Don't redesign everything.
4. **Re-run.** Both Tier 1 and Tier 2, with the same discipline.
5. **Time-box.** Allow at most three iteration cycles before declaring the POC's result whatever it is.

The time-box matters. Without it, the temptation is to iterate until results look good, which destroys the meaning of the measurement.

### What a v1.1 schema change might look like

If diagnosis says "the `cross_pillar_lookup` pattern was misleading — the agent confused source and target entities" — v1.1 might:
- Drop the pattern; expand the `ASSIGNED_TO` edge's `notes` field instead
- Or restructure the pattern's `parameters` JSON to make source/target unambiguous
- Or add a worked example to the `example` field

Whichever change is made, the schema doc gets updated (don't fork), the seed SQL gets a new revision (e.g. `sql/kg/v2/`), and the v1 schema is preserved as historical record.

### What a phase 04 change might look like

If diagnosis says "the query tools returned KG data in a format the LLM couldn't parse" — phase 04's tool surface gets revised. Same KG content, different tool shape.

### What a phase 05 change might look like

If diagnosis says "the agent had access to KG tools but never called them" — the integration is wrong. System prompt may need to direct attention to the KG, or KG tools may need to be called proactively at planning time before the agent decides what Fusion tools to use.

---

## 6. What This Framework Does NOT Promise

Honest scoping of the framework's limits:

- **It does not predict generalization.** Track B passing the reference prompt does not mean it would pass an arbitrary Fusion question. The POC is sized to one prompt deliberately.
- **It does not control for LLM variance.** Five runs sample the model's variability for one prompt; a different model or a different day might score differently. Documented but not eliminated.
- **It does not measure user satisfaction.** No human-rated quality scores. The rubric is mechanical.
- **It does not measure latency at production scale.** Tier 3's wall-clock dimension is informational, not a SLA test.
- **It does not validate the architecture for multi-tenant production.** That's a separate question; see `spire_design_alternatives.md` for the scope boundary.

---

## 7. Deliverables

What the evaluation phases must produce:

| Phase | Deliverable | Source of truth |
|---|---|---|
| 08 | `docs/phase_08_track_b_results.md` | 5 trace files + per-run rubric scoring |
| 09 | `docs/phase_09_comparative_results.md` | A.5 vs phase 08 (Tier 1) vs phase 08-ablation (Tier 2) side-by-side; Tier 3 audit results |
| 09 | Updated comparison table in `spire_design_alternatives.md` §6 — measured baselines for both tracks |
| 09 (if iteration occurred) | Iteration history: what changed, why, what the re-run showed |

Each deliverable cites trace files by path so the result is reproducible from the artifacts.

---

## 8. Summary

The KG is not assumed to work. It is required to:

1. Score meaningfully higher than 1/7 on the reference prompt (Tier 1)
2. Cause that improvement attributably (Tier 2 ablation)
3. Behave honestly along the way (Tier 3 audit)

If any tier fails, we iterate within a time-box. If iteration doesn't close the gap, the POC reports an honest negative result — and that is a successful POC outcome, not a failure. A POC that can't say "the architecture didn't work" can't say "the architecture worked" either.
