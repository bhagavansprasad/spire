# Spire — Enhancement Requirements Specification

| | |
|---|---|
| **Document** | Spire Enhancement Requirements, v1.0 |
| **Date** | 2026-07-30 |
| **Status** | Draft for review |
| **Author** | Bhagavan |
| **Supersedes** | Raw enhancement list (16 items, 2026-07-30) |
| **Related** | `docs/spire_plan.md`, `docs/spire_architecture.md`, `docs/spire_fusion_endpoints_reference.md` |

---

## At a glance

Five categories of work. They differ in kind, not just in content, and that
difference decides the order: defects before features, measurement before
optimisation, decisions before the work that depends on them.

| # | Category | What falls into it | Requirements | Priority | Phase |
|---|---|---|---|---|---|
| 1 | **Defects** — shipped behaviour that misleads the user | Unreadable refusals · no guidance on over-broad queries · silent 25-row truncation | UX-01 to UX-04 | P1–P2 | 2, 8 |
| 2 | **Plumbing** — infrastructure that makes later work possible | Quiet default output · per-component debug flags · per-stage instrumentation · test layers | UX-05, OBS-01 to OBS-05, TST-01 to TST-04 | P1–P2 | 1, 3, 4 |
| 3 | **Optimisation** — known cost, unproven remedy | Token cost · 20-second latency · code-built responses · caching · vocabulary in the KG | PRF-01 to PRF-08 | P1–P3 | 5, 6, 7, 8, 11 |
| 4 | **Open questions** — no right answer yet | LLM planner vs KG planner · single vs multi-agent · how to expose tools to copilots · multi-backend scope | DEC-01 to DEC-03 | Decision | — |
| 5 | **New surfaces** — new front doors onto the same engine | REST interface · copilot interface · configuration and query UI | API-01 to API-05 | P2–P3 | 9, 10, 12 |

**Totals:** 27 requirements and 3 decisions, sequenced across 12 phases.

**The one thing to take from this table.** Category 2 produces no new
capability and is where the first four phases go. It is the reason every
phase after it is faster and safer: without instrumentation no optimisation
can be proven to have helped, and without the test layers none can be shown
not to have broken something.

Full detail in sections 4 to 9. Sequence in section 10. Mapping back to the
original 16-item list in section 12.

---

## 1. Purpose and scope

### 1.1 Purpose

This document specifies enhancements to Spire, the deterministic
natural-language query system over Oracle Fusion Cloud. It converts a raw
list of 16 observations and ideas into numbered, testable requirements with
priorities, acceptance criteria and dependencies.

### 1.2 Scope

**In scope:** the presentation layer, observability, test infrastructure,
cost and latency optimisation, and new access interfaces (REST, copilot,
UI) for the existing Oracle Fusion P2P and AR modules.

**Out of scope for this document:**

- New business modules or catalog prompt coverage (tracked in
  `docs/spire_plan.md`)
- Support for backends other than Oracle Fusion (see DEC-03)
- Any change to the deterministic KG planner (see DEC-01)

### 1.3 Audience

Development, QA, and the Oracle SME reviewing user-facing behaviour.

---

## 2. Definitions

| Term | Meaning |
|---|---|
| **Pipeline** | parse → plan → execute → synthesize → render |
| **Parse** | LLM call converting a question into a structured intent |
| **Plan** | Deterministic KG lookup selecting tool and arguments. Not an LLM call. |
| **Execute** | Oracle Fusion REST calls performed by the selected tool |
| **Synthesize** | LLM call producing the prose summary |
| **Render** | Local formatting of the response object for display |
| **KG menu** | The entity, filter and vocabulary listing sent to the parser on every call |
| **Refusal** | A deliberate decline, distinct from an error or a crash |
| **End user** | A finance or procurement user asking business questions |
| **Operator** | A developer or QA engineer running or debugging the system |

### 2.1 Requirement conventions

- **shall** — mandatory
- **should** — recommended; deviation requires justification
- **may** — optional

**Priority:** `P1` required for the next release · `P2` required but
schedulable · `P3` desirable · `D` decision required before specification.

---

## 3. Current baseline

Measured 2026-07-29 on pod `fa-esll-dev37` across a 31-prompt run. These
figures are the justification for the requirements in section 7 and the
baseline against which improvement is measured.

| Metric | Measured |
|---|---|
| Mean wall-clock per answered prompt | 16.0 s (range 4.8–21.4 s) |
| Mean total tokens per prompt | 12,230 (median 12,288) |
| Parse input tokens per prompt | 8,667 mean |
| Synthesize input tokens per prompt | 2,418 mean |
| Synthesize output tokens per prompt | 880 mean |
| **Parse share of all input tokens** | **78%** |
| Question text as share of parse input | ~0.2% (10–20 tokens of 8,667) |
| Fusion REST calls per lifecycle prompt | 6, issued sequentially |
| LLM calls per answered prompt | 2 |

**Principal finding:** cost is dominated not by the work performed but by
the KG menu, rebuilt and retransmitted on every parse call.

---

## 4. User-facing output requirements

Rationale: the system is more often correct than it is legible. Each
requirement in this section addresses a case where Spire holds the right
information and communicates it poorly.

### UX-01 — Structured refusal messages · P1

Spire **shall** present every refusal in three distinct, visually separated
parts:

1. **What cannot be done** — one sentence in plain language.
2. **Why** — the specific reason, distinguishable from the surrounding text.
3. **What to try instead** — at least one example the user can type verbatim.

Spire **shall not** present a list of supported entities or filter types as
the primary content of a refusal.

**Rationale.** Refusals currently emit an entity and filter inventory with
the actual reason in a trailing parenthesis. The user is shown what the
system contains rather than what went wrong.

**Acceptance criteria**

- A refused prompt yields output in which the reason is identifiable
  without reading past the first three lines.
- Every refusal includes at least one runnable alternative example.
- No refusal output exceeds ten lines by default.
- All existing refusal classifications continue to be distinguishable
  programmatically, not by message text.

**Depends on:** none.

---

### UX-02 — Narrowing guidance for over-broad queries · P1

Where a query is refused **because its result set would be unbounded**,
Spire **shall** respond with a request to narrow the query rather than a
rejection, naming at least two applicable filter dimensions.

**Rationale.** A query such as *"get employee details"* is correctly
declined, but the user asked a reasonable question and is told only that it
is unsupported. The refusal is right; the response is unhelpful.

**Acceptance criteria**

- Unbounded-result refusals are classified separately from
  unsupported-capability refusals.
- The response names filter dimensions that are actually available for the
  target entity, sourced from the KG rather than hardcoded.
- A worked example is included.

**Depends on:** UX-01.

---

### UX-03 — Truncation disclosure · P1

Where a result set is truncated, Spire **shall** state the number of rows
returned and the total number available, and **shall** qualify any
aggregate computed over a truncated set as a lower bound.

Spire **shall not** present a truncated result as complete.

**Rationale.** A silently truncated result is not a limitation but a wrong
answer. This has already produced defects in production behaviour, where a
total computed over 25 of 1,343 rows was stated as fact.

**Acceptance criteria**

- Truncated results state both counts, e.g. "25 of 1,343".
- Any sum, count or average over a truncated set is labelled as a lower
  bound.
- Where the total is unavailable from the source, the output says the total
  is unknown rather than omitting the disclosure.

**Depends on:** none. **Note:** partially implemented for AR tools.

---

### UX-04 — Aggregate fallback in place of truncation · P2

Where a question is answerable by aggregation, Spire **should** compute the
aggregate over the complete result set rather than returning a truncated
sample of rows.

**Rationale.** UX-03 makes truncation honest; this requirement makes it
unnecessary for the class of question where a count or total is what was
actually wanted.

**Acceptance criteria**

- A countable question over a large set returns a count over the whole set.
- Row-listing questions that exceed the limit offer the aggregate as an
  alternative in the same response.

**Depends on:** UX-03.

---

### UX-05 — Quiet default output · P1

By default Spire **shall** emit only the answer to the user's question.
Banners, parsed intent, plan detail, executor output, token counts and
timing **shall** be suppressed unless explicitly enabled.

**Rationale.** All diagnostic output currently shares one stream with the
answer. This blocks every interface in section 8 and makes demonstration to
non-technical users impractical.

**Acceptance criteria**

- Default invocation prints the answer and nothing else.
- Diagnostic output is restorable in full via the flags in OBS-01.
- No diagnostic text is written to standard output when flags are off;
  diagnostics use a separate stream or logger.

**Depends on:** none. **Blocks:** OBS-01, API-01, API-04.

---

## 5. Observability requirements

### OBS-01 — Independent per-component verbosity flags · P1

Spire **shall** provide independently controllable diagnostic flags, at
minimum:

| Flag | Controls |
|---|---|
| `show_tokens` | per-stage token counts and run totals |
| `show_timings` | per-stage latency (OBS-03) |
| `show_parser` | parsed intent, KG menu size |
| `show_planner` | selected plan, tool, arguments, filters |
| `show_synthesizer` | response object prior to rendering |
| `show_raw_output` | executor output per step |

A single flag enabling all of the above **may** be provided as a
convenience, but **shall not** be the only control.

**Rationale.** One boolean is too coarse. Diagnosing a routing fault should
not require reading synthesizer internals.

**Acceptance criteria**

- Each flag is independently settable and has no effect on any other
  component's output.
- Enabling one flag produces output from that component only.
- Default state of every flag is off.

**Depends on:** UX-05.

---

### OBS-02 — Configuration precedence · P1

Diagnostic flags **shall** be settable in the configuration file and
**shall** be overridable per invocation on the command line, with
command-line taking precedence.

**Acceptance criteria**

- A flag set true in configuration can be disabled for a single run.
- Absent configuration, all flags default to off.
- Invalid flag names are reported rather than ignored silently.

**Depends on:** OBS-01.

---

### OBS-03 — Per-stage latency instrumentation · P1

Spire **shall** record and be able to report elapsed time for each pipeline
stage separately: parse, plan, execute, synthesize, render, and total
wall-clock.

**Rationale.** Optimisation without per-stage measurement is guesswork.
Section 7 contains hypotheses about where the 16 seconds is spent; none can
be confirmed today.

**Acceptance criteria**

- Every stage reports elapsed time with at least millisecond resolution.
- Stage times sum to within 5% of the reported total.
- Instrumentation adds no more than 1% to total runtime.
- Timing is captured whether or not it is displayed.

**Depends on:** none. **Blocks:** PRF-05, PRF-07.

---

### OBS-04 — Per-call Fusion timing · P1

Within the execute stage, Spire **shall** record elapsed time for each
individual Oracle Fusion REST call, identified by endpoint.

**Rationale.** The lifecycle tool issues six calls. A single aggregate
execute time does not identify which endpoint is slow, which is the
information required to act.

**Acceptance criteria**

- Each call is reported with endpoint, elapsed time and row count.
- Paged fetches report per-page timing.
- Child-resource fan-out reports each call, not a total.

**Depends on:** OBS-03.

---

### OBS-05 — Machine-readable run record · P2

Spire **should** be able to emit a structured record per run containing the
prompt, routing decision, per-stage timings, token counts, outcome and any
refusal classification.

**Rationale.** Comparing runs is how an optimisation is proven to have
worked. Parsing this from human-readable console output is fragile.

**Acceptance criteria**

- One machine-readable record per prompt, appendable across runs.
- Contains sufficient fields to compute all baseline metrics in section 3.
- Emission is independent of console verbosity.

**Depends on:** OBS-03, OBS-01.

---

## 6. Test infrastructure requirements

Rationale: current coverage is unit tests plus an end-to-end prompt runner.
The gap is the middle. When an answer is wrong there is no inexpensive way
to identify which stage produced the fault.

### TST-01 — Routing test suite · P1

A test suite **shall** assert, for a corpus of prompts, that parsing
produces the expected target entity and filter type. It **shall not**
execute tools or contact Oracle Fusion.

**Rationale.** Misrouting and unwarranted refusal have been the most
expensive failure class to date. A routing suite detects both immediately.

**Acceptance criteria**

- Each case declares prompt, expected entity, expected filter type.
- Unwarranted refusals fail the suite.
- Runs without pod access.
- Includes negative cases: prompts that must be refused, and prompts that
  must route elsewhere (regression against over-matching).

**Depends on:** none. **Note:** requires LLM access; excluded from
per-commit runs.

---

### TST-02 — Plan test suite · P1

A test suite **shall** assert that a given intent produces the expected
tool selection and arguments, without executing the tool.

**Rationale.** Planning is deterministic, so this suite needs neither an
LLM nor a pod and can therefore run on every commit — the cheapest
possible guard on the routing layer.

**Acceptance criteria**

- Runs with no network access and no LLM.
- Asserts tool name, argument names and argument values.
- Asserts refusals raised by planner guards.
- Completes in under five seconds.

**Depends on:** none.

---

### TST-03 — Synthesizer test suite · P1

A test suite **shall** assert that a fixed executor output produces the
expected rendered answer, without contacting Oracle Fusion.

**Rationale.** Rendering defects are a distinct class from data defects and
must be provable without a pod. The precedent: a null payment amount
rendered as `0.00`, which read as "nothing was paid" when the correct
statement was "cannot be determined".

**Acceptance criteria**

- Fixtures are static records; no pod access.
- Asserts that null values are never rendered as zero, blank, or false.
- Asserts that computed fields — risk, recommended action, stage,
  responsible team — appear verbatim and are not reworded.
- Where an LLM produces prose, the assertion targets the deterministic
  fields only.

**Depends on:** none.

---

### TST-04 — End-to-end suite · P2

The existing prompt-set runner **shall** be retained and **shall**
distinguish four outcomes: answered correctly, not a valid prompt, refused,
and failed.

**Rationale.** A pass count alone has previously masked wrong answers. The
dangerous outcome is a confident incorrect answer, which is the only one
that survives a cursory read.

**Acceptance criteria**

- Summary output does not describe a run as successful on the basis of
  absence of errors.
- Per-prompt outcome is recorded, not only the aggregate.

**Depends on:** OBS-05 for machine-readable output.

---

## 7. Performance and cost requirements

### PRF-01 — Deterministic response construction · P1

Every value in a response that can be derived from executor output
**shall** be constructed in code. The LLM **shall** be responsible only for
prose narration.

Numeric values, ratings, status labels, recommended actions, tables and
lists **shall not** be produced by the LLM.

**Rationale.** Proven: applying this to the PO lifecycle response reduced
synthesize output from 1,824 to 924 tokens and improved correctness, because
a value copied by code cannot be misreported. It also makes responses
reproducible — the same question ceases to yield subtly different answers on
different days.

**Acceptance criteria**

- For each response shape, deterministic fields are enumerated and built in
  code.
- Synthesize output tokens reduced by at least 40% against the section 3
  baseline.
- Identical input produces byte-identical deterministic fields across runs.

**Depends on:** none. **Verified by:** TST-03.

---

### PRF-02 — Prompt caching for the KG menu · P1

Spire **shall** cache the static portion of the parse prompt so that the KG
menu is not retransmitted in full on every call.

**Rationale.** The KG menu is 78% of all input tokens and is identical
across calls. The question itself is approximately 0.2% of the parse
payload.

**Acceptance criteria**

- Parse input tokens billed per call reduced by at least 60% against the
  section 3 baseline.
- Routing behaviour unchanged: TST-01 passes identically before and after.
- Cache invalidates when the KG is rebuilt.

**Depends on:** OBS-05 to demonstrate the reduction.

---

### PRF-03 — Exact-match intent cache · P2

Spire **should** cache parsed intents keyed on normalised prompt text and
reuse them without an LLM call on exact match.

**Acceptance criteria**

- Identical prompt text produces zero parse tokens on second invocation.
- Cache invalidates on KG rebuild.
- Cache hits are visible under `show_parser`.

**Depends on:** PRF-02.

---

### PRF-04 — Semantic intent cache · P3 · conditional

Spire **may** retrieve a semantically similar prior prompt and reuse its
intent, subject to all of the following:

- A similarity threshold below which the real parser is used.
- Provable fallback to the parser on low confidence.
- Demonstrated no regression in TST-01.

**Rationale and risk.** This is the "RAG" proposal. The risk is asymmetric:
a near-miss retrieval yields a *confidently incorrect intent*, which is
worse than a slow correct one. It is specified as conditional and
subordinate to PRF-02 and PRF-03, which address the same cost at lower
risk.

**Acceptance criteria**

- Zero routing regressions in TST-01.
- Every cache hit is attributable and auditable.
- Measured benefit beyond PRF-02 and PRF-03 is demonstrated before adoption.

**Depends on:** PRF-02, PRF-03, TST-01, OBS-05.

---

### PRF-05 — Concurrent Fusion calls · P1

Where a tool issues multiple independent Oracle Fusion REST calls, those
calls **shall** be issued concurrently.

**Rationale.** The lifecycle tool issues six largely independent calls
sequentially. This is the most probable single latency win and requires no
change to any LLM interaction.

**Acceptance criteria**

- Independent calls are concurrent; dependent calls remain ordered.
- Execute-stage elapsed time reduced by at least 40% for multi-call tools.
- Result contents byte-identical to the sequential implementation.
- Concurrency is bounded to avoid overwhelming the pod.

**Depends on:** OBS-04 to confirm the hypothesis and quantify the gain.

---

### PRF-06 — Vocabulary in the knowledge graph · P2

Phrasing and routing vocabulary **should** be held in the knowledge graph
and retrieved per question, rather than embedded in the parser prompt.

**Rationale.** Filter descriptions are currently hardcoded in the parser's
system prompt, so adding one KG filter requires a parser code change. Moving
this knowledge into the KG removes that coupling and permits sending only
relevant vocabulary — reducing menu size as a side effect.

This is the substantive form of the "graph RAG" proposal. Note that Spire's
planner is *already* a deterministic graph lookup; the non-deterministic
step is question-to-intent, which is where graph-held vocabulary applies.

**Acceptance criteria**

- Adding a KG filter requires no parser code change.
- Parse input tokens reduced relative to PRF-02 alone.
- TST-01 passes with no regression.

**Depends on:** PRF-02, TST-01.

---

### PRF-07 — Latency target · P2

Mean wall-clock time per answered prompt **shall** be reduced to under 8
seconds, from a baseline of 16.0 seconds.

**Acceptance criteria**

- Measured across the full prompt set, not a selected subset.
- Refusals reported separately from answered prompts, as they are faster and
  distort the mean.
- Median reported alongside mean.

**Depends on:** OBS-03, PRF-01, PRF-02, PRF-05.

---

### PRF-08 — Token target · P2

Mean total tokens per answered prompt **shall** be reduced to under 4,000,
from a baseline of 12,230.

**Acceptance criteria**

- Measured across the full prompt set.
- Reported split by stage and by direction.
- No regression in TST-01 or TST-03.

**Depends on:** PRF-01, PRF-02, PRF-03.

---

## 8. Interface requirements

All requirements in this section depend on UX-05. An engine that writes
diagnostics to standard output cannot serve an API or a UI.

### API-01 — REST interface · P2

Spire **shall** expose an HTTP interface accepting a natural-language
question and returning the structured response.

**Acceptance criteria**

- Accepts a question and optional diagnostic flags.
- Returns the structured response object, HTTP status, and any refusal
  classification.
- Refusals return a success status with a refusal payload, not an error
  status — a refusal is a valid outcome.
- Concurrent requests are supported.
- No diagnostic output on the response stream unless requested.

**Depends on:** UX-05, OBS-01.

---

### API-02 — Structured response contract · P2

The REST interface **shall** return the structured response object.
Presentation-formatted text **shall not** be the primary payload.

**Rationale.** Rendering is client-specific. Returning terminal-formatted
text imposes the console formatter's choices on every consumer, including
the UI.

**Acceptance criteria**

- Response schema is versioned and documented.
- Null values are transmitted as null, never coerced to zero, false or empty
  string.
- A rendered-text field may be included as a convenience, clearly secondary.

**Depends on:** API-01.

---

### API-03 — Spire as a single MCP tool · P2

Spire **shall** be exposable to external MCP clients as a single tool
accepting a natural-language question, with the full pipeline executed
internally.

**Rationale.** Exposing the underlying MCP tools directly would allow an
external client to select tools itself, bypassing the KG planner and with it
the deterministic routing, the refusal guards and the truncation
disclosures. Delegating the whole question preserves those properties. See
DEC-02.

**Acceptance criteria**

- One tool, one question argument, structured response.
- Refusals surface to the client as refusals, with reason.
- Underlying per-entity tools are not exposed externally by this route.

**Depends on:** API-01, DEC-02.

---

### API-04 — Connection configuration UI · P3

A user interface **should** permit management of connection settings for one
or more Oracle Fusion environments.

**Acceptance criteria**

- Multiple named environments, selectable per query.
- Credentials are never displayed after entry and never written to logs.
- Connectivity can be validated before use.

**Depends on:** UX-05, API-01. **Constrained by:** DEC-03.

---

### API-05 — Query console UI · P3

A user interface **should** permit entry of questions, display of answers,
and review of prior queries.

**Acceptance criteria**

- Renders the structured response, including truncation and null-value
  disclosures required by UX-03 and API-02.
- Diagnostic detail available but not shown by default.
- History is per user.

**Depends on:** API-01, API-02, API-04.

---

## 9. Decisions register

The following require a decision before they can be specified as
requirements. They are recorded here so they are settled deliberately
rather than drifted into.

### DEC-01 — Planner architecture

**Question.** Should the deterministic KG planner be supplemented or
replaced by an LLM planner, and if so, as a single agent with all tools or
as per-module agents under an orchestrator?

**What is at stake.** This is not an enhancement but a reversal of the
current architecture. Tool selection is presently a KG lookup specifically
so that routing is reproducible and auditable. Every numeric defect resolved
in this system to date was resolved by moving work *out* of the LLM.

**Gained:** flexibility; reduced KG authoring; coverage of unanticipated
questions.
**Lost:** reproducibility; the ability to explain why a tool was selected;
the guarantee that a question routes identically twice.

**Proposed resolution.** Retain the KG planner as the primary path and add
an LLM fallback for questions the KG cannot route — presently refused. The
fallback is a labelled best-effort answer, never the default. This is
additive rather than a rewrite and can be evaluated against real refusals.

**Required before:** any planner implementation work.

---

### DEC-02 — External tool exposure model

**Question.** How should Spire's capabilities be reached by external
copilots?

**Options.**

1. Expose the underlying MCP tools directly. Simplest; discards KG
   planning, refusal guards and truncation disclosure.
2. Expose Spire as one MCP tool running the full pipeline (API-03).
   Preserves all guarantees.
3. Expose the REST interface (API-01) and let clients call it as a service.

**Proposed resolution.** Option 2 as the default, option 3 for breadth.
Option 1 constitutes building a different product and should be a conscious
choice, not a shortcut.

**Required before:** API-03 implementation.

---

### DEC-03 — Multi-backend support

**Question.** Should Spire support systems other than Oracle Fusion?

**What is at stake.** Spire is presently specific to Oracle Fusion REST.
Every documented pod behaviour — silent composite-filter failures, absent
received amounts, holds located on installments rather than invoices — is
Fusion-specific and encoded in the tools and the KG.

**Note.** Supporting a second backend is a programme, not a configuration
screen. It must not be conflated with API-04, or the UI work will be blocked
behind it.

**Required before:** any commitment implying backend neutrality.

---

## 10. Implementation sequence

Sequenced by dependency, not by priority.

| Phase | Requirements | Rationale for position |
|---|---|---|
| **1** | UX-05, OBS-01, OBS-02 | Blocks every interface. Small, low risk. |
| **2** | UX-01, UX-02, UX-03 | User-visible defects. Cheap, immediate credibility gain. |
| **3** | OBS-03, OBS-04, OBS-05 | Must precede optimisation; nothing in phase 5+ is provable without it. |
| **4** | TST-02, TST-03, TST-01 | Makes later phases safe to attempt. TST-02 first: no LLM, no pod. |
| **5** | PRF-01 | Proven pattern, known gain, no new components. |
| **6** | PRF-02, PRF-03 | Largest token reduction at lowest risk. |
| **7** | PRF-05 | Probably the largest latency win. Confirm with phase 3 first. |
| **8** | UX-04, PRF-07, PRF-08 | Verification of phases 5–7 against targets. |
| **9** | API-01, API-02 | Unblocks copilot and UI. |
| **10** | API-03 | Requires DEC-02. |
| **11** | PRF-06, PRF-04 | Higher risk. Requires phases 4 and 6 to evaluate honestly. |
| **12** | API-04, API-05 | Requires phase 9. Constrained by DEC-03. |
| **—** | DEC-01 | Decision only. No phase assigned. |

**Phases 1 to 4 are infrastructure and defect work.** They produce no new
capability and are the reason every subsequent phase is faster and safer.
The temptation will be to begin at phase 5 or 6, where gains are visible.
The argument against: without phase 3 no optimisation can be proven to have
helped, and without phase 4 no optimisation can be shown not to have broken
something.

---

## 11. Assumptions and constraints

1. Oracle Fusion REST remains the sole data source for the duration of this
   specification. See DEC-03.
2. The deterministic KG planner is retained. See DEC-01.
3. Demonstration data on the development pod dates from 2013–2024.
   Age-based and overdue calculations cannot be validated on it and require
   production or synthetic data.
4. Available test purchase orders exercise partial and complete
   reconciliation but not partly paid invoices, invoices on hold, or
   supplier setup blockers. Those paths are covered by unit tests only.
5. LLM provider latency and pricing are outside Spire's control. Latency
   targets in PRF-07 assume the current provider.

---

## 12. Traceability

Every requirement in this document derives from the original 16-item list.

| Original item | Requirements |
|---|---|
| 1 — refusal message not readable | UX-01 |
| 2 — too much information for end user | UX-05, OBS-01, OBS-02 |
| 3 — separate debug flags per component | OBS-01, OBS-02 |
| 4 — parser, routing, synthesizer test scripts | TST-01, TST-02, TST-03, TST-04 |
| 5 — instrument per-stage timing | OBS-03, OBS-04, OBS-05 |
| 6 — RAG to reduce prompt size and tokens | PRF-02, PRF-03, PRF-04 |
| 7 — graph RAG as a more deterministic option | PRF-06, DEC-01 |
| 8 — over-broad query refusal unexplained | UX-02 |
| 9 — 25-row truncation behaviour | UX-03, UX-04 |
| 10 — synthesizer calls LLM to format output | PRF-01 |
| 11 — do more in static functions, less in LLM | PRF-01 |
| 12 — LLM planner, single vs multi-agent | DEC-01 |
| 13 — exposing tools to copilots | API-03, DEC-02 |
| 14 — 20 seconds per prompt | PRF-05, PRF-07, OBS-03 |
| 15 — REST and copilot interfaces | API-01, API-02, API-03 |
| 16 — UI with backend configuration | API-04, API-05, DEC-03 |
