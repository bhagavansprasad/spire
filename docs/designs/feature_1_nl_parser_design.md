# Feature 1 — Natural-Language Parser: Design

**Status:** IMPLEMENTED and verified (live Gemini + full suite green).
**Date:** 2026-06-01.
**Module:** `src/spire/nl_parser/` — `result.py`, `vocabulary.py`, `draft.py`,
`validation.py`, `parser.py`. Tests: `tests/test_nl_parser.py` (mock, 14) and
`tests/test_nl_parser_integration.py` (live Gemini, 8).
**Companion docs:** `docs/feature_roadmap.md` (feature 1, the *what/why*);
the 2026-06-01 handoff (section 4, the design questions this doc answers);
`docs/designs/phase_2_planner_design.md` (the `Intent` / `Plan` contract the
parser feeds).

This document records the feature 1 design discussion AND its implementation
outcome. The five design questions and their decisions are in section 2;
what was actually built (including two fixes that only surfaced under the live
model) is in section 6.

---

## 1. What feature 1 is

An LLM-driven layer that converts a natural-language prompt into an `Intent` —
the structured object the deterministic planner (`generate_plan`) already
consumes. Today every prompt shape requires a hand-built `Intent` in
`run_plan.py`; the parser removes that bottleneck.

It is the **interpreter** stage of the Design 3 pipeline:

```
Prompt -> LLM (interpreter / parser) -> KG (planner) -> MCP (executor)
       -> Tools -> Fusion -> Data -> LLM (formatter / synthesizer) -> Output
```

Two LLMs sit in the pipeline, doing opposite jobs:
- the **interpreter** (this feature) constrains its *input* against the KG;
- the **formatter** (the existing synthesizer) validates its *output* against
  the fetched data.

Everything between the Intent and the answer — planner, executor, MCP tools,
synthesizer — is unchanged. Feature 5 (synthesizer schema generalization, now
merged) was the prerequisite that lets the synthesizer accept whatever Intent
shapes the parser produces.

---

## 2. The five design questions — decisions

### Q1 — Where does the parser live?

**Decision: a new module beside the planner (e.g. `src/spire/nl_parser/`),
modeled on the synthesizer, using the planner's synchronous KG path.**

Rejected alternatives:
- **Modify the Track A agent (`runner.py`).** The agent's architecture is
  built for multi-step tool-calling (`bind_tools`, the
  `assistant -> tools -> assistant` LangGraph loop, an MCP session). The
  parser makes a single LLM call and emits a single structured Intent — it
  needs none of that machinery. Reusing the agent means threading a one-shot
  path through a module whose whole shape assumes a tool loop, and inheriting
  its async execution model (which conflicts with the Q2 sync decision).
- **Fold parsing into the planner (`planner.py`).** The planner's defining
  property is that it contains **no LLM**. Putting an LLM call inside it
  contaminates the one deterministic module. Do not.

The correct reuse target is the **synthesizer**, not the agent: the
synthesizer is already the parser's mirror image — one bounded LLM call with
structured output and post-validation. The parser copies that pattern into its
own module.

### Q2 — How is the parser constrained to KG-valid Intents only?

**Decision: synchronous, two-way communication between the parser and the KG.**

- **Direction 1 (KG -> parser), before the LLM call:** the parser reads the
  allowed vocabulary (entities, filters, patterns) from the KG and embeds it in
  the LLM prompt as the menu the model may order from.
- **Direction 2 (parser -> KG), after the LLM call:** the parser validates the
  draft Intent back against the KG and rejects anything the model invented
  (an undeclared entity or filter).

Both directions are **synchronous** — the parser calls, blocks, and waits
inline. This is achieved by routing through the **planner's** synchronous KG
path (`oracledb.connect()` cursor, the existing `find_*` / `resolve_vocab` /
`_validate_intent_filters` functions), **not** the agent's async
`load_kg_context()`. The validation step reuses the planner's existing
`_validate_intent_filters` rather than reimplementing it.

The synchronous parser runs *before* the async planner/executor section; the
handoff from a sync parser to the async pipeline is a clean sequential
boundary, not a conflict. (Confirm at implementation time.)

### Q3 — How are out-of-scope prompts handled?

**Decision: the parser emits a structured "can't answer" result that names the
flavor and the raw facts. The user-facing message is framed in terms of what
Spire *can* do, sourced from the KG. Detection is built in feature 1; polished
wording is feature 8.**

When a prompt is out of scope, the user is told **what Spire's capabilities
are** and that their prompt falls outside them — not a bare "I can't answer,"
and not a low-level reason. The capability statement is generated from the KG
(the same source the parser already reads), so it never goes stale: when
contracts are added (feature 6), the message updates itself.

Three flavors are distinguished, because the KG comparison already reveals
which check failed — so distinguishing them is nearly free:
1. **Unknown entity** — the target entity isn't in `kg_entity` at all
   (e.g. `Contract`, prompt-6).
2. **Unsupported filter** — the entity is known but the filter isn't in the
   KG's filter set (e.g. `amount_over` on POs, prompt-2). This is the check
   `_validate_intent_filters` already performs.
3. **Unsupported operation** — the entity is known but the operation isn't
   (e.g. aggregation / `target_entity=Buyer`, prompt-5). This is what the
   synthesizer's `UnsupportedEntityError` already rejects.

Implementation note: messaging uses **one template filled from the KG**, not
three hand-written paragraphs. The flavor only changes the "what's missing"
slot.

Division with feature 8:
- **Feature 1 (now):** detect out-of-scope, identify the flavor, emit a
  structured "can't answer" result carrying the flavor tag and raw facts. This
  is intrinsic to feature 1 — the parser cannot emit a knowingly-broken Intent,
  so it must detect un-answerability to function.
- **Feature 8 (later):** turn the structured refusal into polished,
  capability-framed user-facing wording.
- **Test for the line:** feature 1's output should be *correct and structured*
  but may be bluntly worded; feature 8 makes it *gracious*.

### Q4 — Testing without flaky or hidden LLM failures

**Decision: keep both mock unit tests and live LLM tests. Run the live tests as
part of regular verification (not deselected-and-forgotten), so LLM regressions
surface early. Keep the two split so a failure points at the culprit.**

- **Mock unit tests** (fast, deterministic, always run): inject a mock LLM that
  returns canned output. These hold the LLM constant and test the parser's own
  logic — KG vocabulary loading, draft-Intent validation, refusal-flavor
  detection, clean pass-through of valid Intents. They assert **exact** Intent
  output. A mock failure means **our code** is wrong.
- **Live tests** (real Gemini, run regularly): send real prompts to the model
  and check the parser produces a sane result. A live failure means **the
  model** is the problem — drift, a broken prompt, unparseable output. Because
  LLM output is non-deterministic, live tests assert **properties**
  (`target_entity == "Supplier"`, the country filter resolved to `US`, this
  out-of-scope prompt produced a refusal), **not** exact equality — otherwise
  they flake and get ignored.

Follows the synthesizer's existing pattern (optional injected `llm`,
`@pytest.mark.integration` for live), with the difference that the live tests
are treated as first-class regular verification, not a rare opt-in.

Fixture shape: a `(prompt, expected_intent_or_refusal)` case table, reusing the
existing gap-analysis prompts from `run_plan.py` (anchor, original, prompt-1
through prompt-6), which have known expected outcomes. The table doubles as
documentation of what the parser is supposed to handle.

### Q5 — Relationship to the synthesizer's `UnsupportedEntityError`

**Decision (Option 1): the parser is the user-facing gatekeeper; the
synthesizer's check is retained as a loud developer-facing backstop.**

The parser owns *user-facing* refusal (gracious, capability-framed, for real
prompts). The synthesizer's `UnsupportedEntityError` stays as a
*developer-facing* invariant (loud, for "this should be impossible" cases).
Same error class, two audiences, two jobs — layered defense, not conflict.

How "stop" is signaled: the parser does **not** raise an exception for
out-of-scope prompts (that would reintroduce the loud-failure problem feature 8
fixes). It returns a **checked refusal result**, and the pipeline gates on it:

```
result = parse(prompt)
if result is a refusal:
    show the capability message          # stop — never plan/execute/synthesize
else:
    plan -> execute -> synthesize        # only valid Intents flow downstream
```

So in normal flow an out-of-scope request never reaches the synthesizer — which
is exactly why the synthesizer's check should essentially never fire. If it
*does* fire, it means something bypassed the gate: a hand-built Intent from
`run_plan.py`, or a parser regression. That is the case the backstop exists for.

**Option 2 (delete the synthesizer's check) is explicitly rejected:** hand-built
intents in `run_plan.py` bypass the parser entirely, so the synthesizer's check
is the only thing protecting that path. As long as the hand-built path exists
(it does, for testing), the check must stay.

---

## 3. New components, and what is untouched

**New (feature 1):**
- The NL parser module (own folder, beside the planner; bounded single LLM
  call inside).
- The KG-vocabulary read it performs (sync, via the planner's KG path) and the
  draft-Intent validation it performs back against the KG.
- A structured "can't answer" result type carrying a flavor tag + raw facts.
  *(Touches the `Intent` contract — adds a way to represent "no Intent, here's
  why," e.g. a sibling type or a refusal field. Confirm nothing downstream
  assumes every parser output is a plannable Intent.)*

**Unchanged:** planner, executor, MCP tools, Fusion client, synthesizer. The
`Intent` object the planner consumes is the same — only its *source* changes
(was hand-written in `run_plan.py`, now generated by the parser).

---

## 4. Component lifecycle — the Track A agent

The Track A agent (`ask.py` -> `runner.py`, the LLM-as-planner baseline) is
**not** part of the Design 3 runtime and is never invoked by the Design 3
pipeline. It is kept solely as the **evaluation baseline** — the comparison arm
that justifies the Design 3 architecture.

- **Keep until** Design 3 consistently produces valid results — specifically,
  until the feature-1 parser-driven path has been run against the agent
  baseline and the before/after comparison is recorded.
- **Then** the agent has served its purpose and should be deleted.
- **Do not** remove the agent mid-feature-1: doing so destroys the ability to
  demonstrate the before/after that justifies feature 1. Removal is a
  deliberate later step gated on the final baseline comparison — not a cleanup
  to do now.
- **Rationale:** the repo is still a POC; in the "prove the architecture" phase
  the baseline earns its keep. Feature 1 is built identically whether or not
  the agent is later removed, so this is a tracked lifecycle policy, not a
  blocker.

*(This section is also intended for `docs/feature_roadmap.md` as a "Component
lifecycle" section.)*

---

## 5. Implementation record

Built in checkpoints, each run against the live KG / model before the next:

1. Result type + sync KG vocabulary read.
2. LLM call + draft production (mock unit tests).
3. Two-way KG validation, B1 ordering.
4. Pipeline gate in `run_plan.py` (`--prompt`, exit 4 on refusal).
5. Live integration tests, run as regular verification.

### Two fixes that only surfaced under the live model

1. **Silent rewrite (serious).** The first prompt iteration told the model to
   "emit the closest Intent" for out-of-scope prompts and rely on later
   validation. The model instead silently rewrote "contract renewals" as a
   bare Supplier query — validation never fired because nothing INVALID was
   emitted. Fix: (a) the prompt now forbids salvaging and instructs explicit
   refusal; (b) `DraftIntent` gained an `unanswerable` + `unanswerable_reason`
   slot so the model can *choose* to refuse. This is the structural defense —
   the model self-declares un-answerability.

2. **Fragile value encoding.** `value_json` required JSON-quoted strings, but
   the model unreliably emitted bare `GB` instead of `"GB"`, causing
   intermittent malformed-value refusals. Fix: `to_intent()` decodes leniently
   — a non-JSON `value_json` is taken as a plain string; bools/objects still
   decode as JSON. Safe because the planner validates values downstream.

Also tightened: a "completeness" block in the prompt (extract EVERY in-scope
constraint, with concrete NL->filter mappings) after the live tests caught the
model dropping the country, buyer-include, and no-recent-invoices clauses.

### Test outcome
- Full suite: 277 passed, 13 deselected (was 263 + 5; +22 parser tests).
- Live integration suite: 8/8 green across repeated runs (stable, not lucky).

### Known follow-ups (not blockers)
- The model self-declared refusal maps to flavor `UNPARSEABLE` today even when
  the truer flavor is `UNKNOWN_ENTITY` (e.g. contracts). Honest but coarse;
  feature 8's capability-framed wording refines this.
- The parser imports the planner's private filter constants so its menu can't
  drift from `_validate_intent_filters`. When filters move into the KG
  (planner v1.2), read them from the KG instead.
- Refusal wording is blunt (feature 1 scope); capability-framed wording is
  feature 8.
