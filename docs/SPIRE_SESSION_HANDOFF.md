# Handoff — Spire (classifier flip fixed; planner robustness is next)

Paste this into the new window to continue. This SUPERSEDES the prior handoff:
the **multi-module router / lifecycle-flip** work it teed up is DONE and merged.
It resolved differently than that handoff anticipated — see "How the router work
actually resolved" below. The open work is now **planner robustness (S1)** and a
few smaller items.

---

## What Spire is

AI-native NL query over Oracle Fusion Cloud (P2P + AR). Deterministic KG
pipeline: **route → parse → plan → execute → synthesize**. Two LLM boundaries —
the module **classifier** and the **parser** (words → Intent); planning,
execution, and synthesis are deterministic (no LLM synthesis call). The KG is
the deterministic oracle: plans are COMPUTED from KG edges/filters/tools, not
chosen by a model. This is the core design bet and it is sound — keep it.

- Repo: `github.com/bhagavansprasad/spire`, working dir `~/pocs/spire`
- Current pod: `eqjz` (creds in `personas.yaml`). **Spire reads `personas.yaml`
  ONLY** — the `IKS_FUSION_*` shell env vars are for curl scripts, NOT Spire. A
  wrong pod usually means the MCP server is stale (loads the persona once at
  startup) — restart it. Restart the MCP server after ANY change under
  `src/spire/mcp_server/`.
- LLM: Gemini `gemini-3.5-flash` via Vertex AI, `GEMINI_TEMPERATURE = 0.0`,
  `LLM_MAX_OUTPUT_TOKENS = 8000` in `src/spire/config.py`. **The model is set by
  `GEMINI_MODEL` in config.py — this matters, see S2 below.** All this session's
  verification was on `gemini-3.5-flash`; `gemini-3.1-flash-lite` measurably
  degrades routing.
- master is green: **913 passed, 18 deselected**. Everything below is merged.

---

## Architecture note (keep the KG — asked and answered repeatedly)

The user periodically asks whether the KG is the source of Spire's bugs and
whether multi-agent orchestration (orchestrator → per-module agent → LLM picks
tool) would be better. **Answer, consistently: no — keep the KG.** Nearly every
bug lives in the CODE THAT READS the KG (planner traversal, parser
include-handling, router scoping), NOT in the KG data; the KG is repeatedly the
ORACLE that catches the incorrect code. Moving determinism into an LLM would
multiply the silent-failure + non-determinism problems the KG design avoids. For
a read-only NL-query system over ERP data with zero tolerance for wrong figures,
KG-deterministic is the more scalable and more correct choice. What actually
costs the user: KG COVERAGE (new capability = new rows + rebuild + tripwires) and
KG-change ERGONOMICS — both improvable WITHIN the approach.

---

## How the router / lifecycle-flip work actually resolved (THIS session)

The prior handoff framed the lifecycle flip as "build increment-2 multi-module
routing properly." The work uncovered a simpler, more important truth that
changed the whole approach. Recorded here so it stays settled.

### The key discovery: the module set does NOT affect the answer

The classifier's module set (the "bucket" list) ONLY selects which
`.sysprompt` grounding blocks the parser sees. It is **discarded after the
parse** — `route_and_parse` uses it to scope, then returns only the
ParseResult; the pipeline (`graph/pipeline.py parse_node`) keeps only
`result.intent`. **Nothing downstream reads the module set.** The TOOL is chosen
from the Intent by the planner, not from the buckets.

Consequence, verified repeatedly: across every lifecycle prompt, the module set
varied run-to-run but the **tool stayed constant** and the **answer was
identical**. The original flip (`[procurement]` vs `[procurement, payables]`)
produced the same tool and same answer both ways. So the module set is NOT a
correctness signal — it is (a) a token-cost signal (more buckets = more grounding
sent = more tokens) and (b) a DIAGNOSTIC breadcrumb for backtracing a wrong
result ("which grounding was loaded when this broke").

This reframed the whole task: it is NOT about making the module set "correct"
(there is no single correct set — extra buckets are harmless surplus). It is
about (1) killing the non-determinism where cheap, and (2) grading validation by
the thing that matters (the tool).

### What shipped (all merged to master; branch feat/router-show-parser-diagnostic)

1. **Router diagnostic** (`router.py`) — `route_and_parse` logs
   `Router: modules=[...]` (success) and
   `Router: no module matched -> full-context parse` (fallback) on the
   `spire.parser` logger, gated by the existing `show_parser` flag (NO new
   flag). Makes the classifier's choice visible under `--show-parser` for
   backtracing. Commit `34044d8`.

2. **Classifier lifecycle flip fixed** (`router.py`) — a MINIMAL grounding rule
   added to `_CLASSIFIER_INSTRUCTION` (the classifier's own hand-authored prompt
   — NOT the generated `classifier_menu.sysprompt`): a status question about ONE
   named PO is procurement even when it says invoiced/paid; "Do NOT add payables
   for such a question." It deliberately says NOTHING about supplier or
   invoices-as-subject. The prompt that flipped 4x/2x is now **20/20
   deterministic `[procurement]`** on `gemini-3.5-flash`; genuine cross-bucket
   prompts (invoices-for-supplier, etc.) are UNAFFECTED. Commit `16a22f6`.

   IMPORTANT LESSON: a FIRST, broader version of this rule ("drop payables AND
   supplier" + a cross-bucket counter-example) caused 11 regressions — it taught
   the classifier to UNDER-include supplier on invoice prompts across several
   sets. A classifier-prompt edit has wide blast radius; the minimal, narrowly
   scoped rule is what worked. If you touch `_CLASSIFIER_INSTRUCTION`, re-run the
   FULL 12-set `--validate`, not just lifecycle.

3. **Routing corpus curated** (`08_lifecycle.json`, `02_purchase_order.json`) —
   corpus module values set to routing verified BY EVIDENCE: a correct
   end-to-end run (right tool + right answer) plus a stable 10x classify on the
   target model. Method matters — do NOT curate the corpus by copying one
   classifier run (that froze the original contradiction, see S3) or by
   reasoning about what the tool "should" need. Lifecycle entries that flipped →
   `[procurement]`; genuinely multi-bucket phrasings ("with supplier details",
   "supplier setup through payment") KEEP their multi-bucket sets; compare-PO and
   compare-supplier → `[procurement]` (each is one self-reconciling tool).
   Commit `16a22f6`.

4. **`--validate` philosophy changed** (`promptkit.py`) — pass/fail is now
   decided by the TOOL alone. A module-set mismatch on a tool-correct row is
   marked `OK*`, counted as a PASS, and listed under a "MODULE WARNINGS" section
   — visible for backtracing but non-failing. Exit code is driven by tools only.
   The decision is a pure `_classify_mark(m_ok, t_ok)` helper with unit tests
   (`tests/test_promptkit.py`). This is the correct model: the tool is
   correctness; the module set is a diagnostic. Commit `b0cb73e`.

Full suite green at 913 before merge.

---

## OPEN WORK (next session) — see docs/spire_findings_2026-09-11.md for detail

### S1 🔴 — planner throws a raw KeyError instead of degrading/refusing (HIGHEST)

`generate_plan` raises an UNHANDLED `KeyError: "No edge to include 'Supplier':
..."` when the parsed Intent carries an include the KG can't wire up (here
`include: Supplier` off `PurchaseOrder`). The user gets an exception, not an
answer or a clean refusal.

- **Contrast:** the planner ALREADY refuses cleanly for unsupported *filters*
  (`refuse:unsupported_filter (planner)`). The unsupported-*include* path lacks
  the same graceful handling. Fix: make it degrade (drop the include, plan the
  rest) or refuse cleanly, matching the filter path.
- **Model-agnostic / latent on any model.** Surfaced on `gemini-3.1-flash-lite`
  (which classified `[procurement]`, dropping supplier, so the parser's
  supplier-include had no grounding and the planner couldn't satisfy it). On
  `gemini-3.5-flash` this specific prompt classifies `[procurement, supplier]`
  and does NOT crash — but the crash PATH exists regardless of model. Any Intent
  with an unsatisfiable include hits it.
- **Related:** main-register #32 (parser drops PO id → planner list-dumps) is the
  same theme (planner robustness / safe fallback), distinct mechanism. Worth a
  single "planner NEVER throws raw; always degrades or refuses" pass covering
  both.
- Ships with a test. Needs a small harness proving the unsatisfiable-include
  path now refuses/degrades instead of raising.

### S2 🟠 — the LLM model is a silent dependency

Switching `GEMINI_MODEL` `3.5-flash` → `3.1-flash-lite` (config only) dropped a
full 12-set `--validate` from 236/240 to 205/240 and triggered S1. The weaker
model systematically UNDER-classifies cross-bucket prompts (drops the 2nd
bucket). Nothing warns that the model changed. Consider pinning/enforcing the
validated model in production so a downstream change can't silently degrade
routing. (S1's planner hardening reduces the blast radius either way.) The new
`--validate` design partially defends this — model-induced bucket drift shows up
as visible `OK*` warnings, not silently — but does NOT cover the S1 crash.

### S3 🟡 — `--generate` freezes classifier flakiness into the corpus

`--generate` runs each prompt through the non-deterministic classifier ONCE and
writes that as the corpus `module` value; a flip gets frozen as ground truth.
This is how the original lifecycle corpus got a self-contradiction (two identical
prompts, differing only in PO number, with different expected sets). Fix
direction: a corpus-consistency guard (generate-time or a test) — "structurally
identical prompts must have identical expected module sets." The underlying
lifecycle flip is now fixed, so this is for the general/future case.

### Carry-forward — main register verification pass

`docs/spire_overnight_findings.md` (last updated 2026-08-14) still lists ~14
issues as open/verified (11 open + 3 verified), NOT re-verified against current
code. Some may already be resolved incidentally. A pass to re-run them and mark
what still reproduces is owed. Highest-value real defects in that register:
#27/#35 (credit-memo truncated-sum labelled as total; top-N dropped on that
path), #32 (dropped-id list-dump — pair with S1), #34/#31 (projection binds to
wrong step-output → em-dash on a present value).

---

## Working style the user relies on (STRICT)

One step at a time; ONE command per turn, verify before proceeding. Ask before
generating code — diagnose first, propose, wait for go-ahead. Deliver COMPLETE
files, never patches; read the CURRENT file (they share bundles) before editing —
files drift. "Verified" means actually RUN, not inferred from reading — a green
tally is NOT a verdict; read the actual output. Every fix ships with its test;
`pytest -q` always; FULL suite before any SOURCE commit. One branch per logical
change; named files in `git add` (NEVER `-A` — there are always scratch `.txt`
files around); heredoc commit messages. They share files as BUNDLES (see
`context_bundles.yaml`) — ask for the bundle, not individual files. Correct your
own wrong diagnoses out loud rather than defending them.

The user is thoughtful and will challenge framing — often correctly. This
session's biggest course-corrections came from them (the model confound, the
tool-vs-bucket distinction, "who's wrong, LLM or corpus", verify-don't-guess on
corpus edits). When they push on "does this actually matter / is this the right
thing to check", take it seriously — twice it collapsed an over-engineered plan
to a simpler correct one.

## First steps in the new window

1. Read this handoff and `docs/spire_findings_2026-09-11.md`.
2. Confirm ground truth: `git log --oneline -8`, `python -m pytest -q` (expect
   913), MCP server up on eqjz, and CONFIRM the model is `gemini-3.5-flash`
   (`python -c "from spire.config import build_llm; print(build_llm().model)"`
   or check `GEMINI_MODEL` in config.py — S2).
3. If tackling S1: reproduce the crash first. On `3.5-flash` the supplier-details
   lifecycle prompt won't crash (it classifies `[procurement, supplier]`), so
   reproduce via an Intent that carries an unsatisfiable include directly, or by
   temporarily forcing the classifier to drop supplier — then read the actual
   `generate_plan` traceback, find where the edge lookup raises, and design the
   degrade-or-refuse there. Diagnose before proposing.

## Do NOT

- Do NOT hard-collapse multi-module classifications to single-module — genuine
  cross-module prompts are first-class. (The lifecycle fix does NOT do this; it
  only stops payables attaching to single-PO status prompts.)
- Do NOT hand-edit the generated `classifier_menu.sysprompt` (regeneration
  overwrites it). Classifier rules go in `_CLASSIFIER_INSTRUCTION`.
- Do NOT curate the corpus by copying one classifier run or by reasoning about
  what a tool "should" need — curate from a correct end-to-end run + stable
  repeat classify on the target model (S3).
- Do NOT treat a module-set mismatch as a correctness failure — the tool is
  correctness; the module set is a diagnostic (that is now baked into
  `--validate`).
- Do NOT change `_CLASSIFIER_INSTRUCTION` without re-running the FULL 12-set
  `--validate` — it has wide blast radius (11 regressions from an over-broad
  version this session).
