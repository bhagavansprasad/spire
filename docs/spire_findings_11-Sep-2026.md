# Spire — Session Findings, 2026-09-11

**Prepared:** 2026-09-11, after the module-router / classifier-flip session.

**Scope:** New findings surfaced while fixing the lifecycle classifier flip,
curating the routing corpus, and changing `--validate` to grade the tool
rather than the module set. Numbered locally (S1, S2, S3) to avoid colliding
with the main register's serial series.

**Severity:** 🔴 real defect (wrong/missing data, crash, or wrong behaviour) ·
🟠 defect or risk with real production impact · 🟡 minor / cosmetic / tooling.

**Status:** `open` (confirmed real, not built) · `verified` (reproduced) ·
`fixed`.

**Note on the main register:** `docs/spire_overnight_findings.md` (prepared
2026-08-14) still lists ~14 issues as open/verified (11 open + 3 verified).
Those were NOT re-verified against current code this session — code has changed
since, so some may already be resolved. A verification pass over that register
is owed.

---

## Shipped this session (context for the findings below)

- **Router diagnostic** — `route_and_parse` now logs `Router: modules=[...]`
  (success) and `Router: no module matched -> full-context parse` (fallback) on
  the `spire.parser` logger, visible under `--show-parser`. Commit `34044d8`.
- **Classifier lifecycle flip fixed** — a minimal grounding rule in
  `_CLASSIFIER_INSTRUCTION`: a status question about ONE named PO is
  procurement even when it says invoiced/paid; do NOT add payables. Says
  nothing about supplier or invoices-as-subject, so genuine cross-bucket
  prompts are untouched. The prompt that flipped 4x/2x is now 20/20
  `[procurement]` on `gemini-3.5-flash`. Commit `16a22f6`.
- **Routing corpus curated** — lifecycle + compare entries set to routing
  verified by a correct end-to-end run plus a stable 10x classify. Commit
  `16a22f6`.
- **`--validate` philosophy changed** — pass/fail is decided by the TOOL; a
  module-set mismatch on a tool-correct row is an `OK*` warning (visible,
  counted, non-failing), not a failure. The module set only scopes the
  parser's grounding and is discarded after parse, so it is a diagnostic and
  token-cost signal, not a correctness gate. Commit `b0cb73e`.

All on branch `feat/router-show-parser-diagnostic`; full suite green (913).

---

# OPEN ISSUES

### S1 🔴 open — `generate_plan` raises an unhandled `KeyError` on an unsatisfiable include (should degrade or refuse)

**Set:** 08_lifecycle, prompt "Show ordered, received, invoiced and paid amounts
for PO 701337 with supplier details."

**Trigger:** surfaced when the classifier returned `['procurement']` (dropped
supplier) — observed on `gemini-3.1-flash-lite`.

**Symptom:** `--validate` reports a TOOL failure with a raw exception:
`generate_plan error: KeyError: "No edge to include 'Supplier': it is neither a
child of 'PurchaseOrder' (chain) nor of 'PurchaseOrder' (sibling under the
root)."` The user gets an exception, not an answer or a clean refusal.

**Mechanism:** the parser emitted an intent carrying `include: Supplier` that
the KG cannot wire up off `PurchaseOrder` in that scope; `generate_plan` throws
instead of degrading.

**Contrast (why this is a hole, not a one-off):** the planner ALREADY refuses
cleanly for unsupported *filters* — e.g. "Open POs for supplier JGA." ->
`refuse:unsupported_filter (planner)`. The unsupported-*include* path lacks the
same graceful handling. Same class of "planner can't satisfy the intent," two
different behaviours: filter = clean refusal, include = raw crash.

**Fix direction:** an unsatisfiable include should degrade (drop the include and
plan the rest) or refuse cleanly with a structured Reason/Solution/Example,
matching the filter path. Model-agnostic — the crash path exists on any model;
flash-lite merely produced the intent that exposes it.

**Verification:** read from `--validate` output (the TOOL✗ line). NOT reproduced
on `gemini-3.5-flash` this session — there the same prompt classified
`[procurement, supplier]`, loaded supplier grounding, and planned without error.
The crash path is latent regardless of model.

**Related:** #32 in the main register (parser drops PO identifier -> planner
list-dumps) is the same theme (parser robustness / safe planner fallback) but a
distinct mechanism (dropped identifier -> list-dump, vs unsatisfiable include ->
KeyError). Worth fixing together under a single "planner never throws raw;
always degrades or refuses" pass.

**Status:** 🔴 open (2026-09-11). Not caused by this session's changes.

---

### S2 🟠 open — The LLM model is a silent dependency; a downstream switch degrades routing and can trigger S1

**Observed:** switching `GEMINI_MODEL` from `gemini-3.5-flash` to
`gemini-3.1-flash-lite` (config change only, no code change) dropped a full
12-set `--validate` sweep from 236/240 to 205/240, and triggered the S1 planner
crash.

**Mechanism:** the weaker model systematically UNDER-classifies genuine
cross-bucket prompts — it drops the second bucket. Examples on flash-lite:
"invoices for supplier 1252" -> `[payables]` (lost supplier); "Open POs for
supplier JGA" -> `[procurement]` (lost supplier); "which suppliers invoiced
more than 50000" -> `[payables]` (lost supplier). On `3.5-flash` these classify
with both buckets.

**Why it matters:** all of this session's verification (the 20/20 flip fix, the
corpus curation, the 41/41 clean sweep) was done on `3.5-flash`. If production
runs — or someone later switches to — a different/weaker model, routing
degrades silently and S1 can fire. Nothing warns that the model changed.

**Mitigation (design decision — needs owner):** pin/enforce the validated model
for production builds so a downstream config change cannot silently alter
routing behaviour. Independently, S1's planner hardening reduces the blast
radius of a weaker model (degrade instead of crash).

**Note:** the new `--validate` design partially defends against this — a
model-induced *bucket* drift shows up as visible `OK*` module warnings rather
than silently. It does NOT cover the S1 crash, which is a planner-robustness
gap, not a validation gap.

**Status:** 🟠 open (2026-09-11).

---

### S3 🟡 open — `--generate` freezes the classifier's per-run output as corpus ground truth, so classifier flakiness becomes corpus contradictions

**Origin:** the corpus contradiction fixed this session — two structurally
identical lifecycle prompts ("Has PO 701337 been fully received, fully invoiced,
and fully paid?" vs the PO 999999999 variant) carried DIFFERENT expected module
sets (`[procurement]` vs `[procurement, payables]`). No rule classifies the same
sentence two ways by PO number; one expectation was simply wrong.

**Mechanism:** `--generate` runs each prompt through the (non-deterministic)
classifier once and writes that output as the corpus `module` value. When the
classifier flips, `--generate` freezes whichever side it happened to produce.
The human-curation step is supposed to catch this, but a per-prompt flip is easy
to miss across dozens of entries. Result: the corpus inherited the flip as a
self-contradiction.

**Fix direction:** a corpus-consistency guard, runnable at generate time or as a
test — e.g. "structurally identical prompts (same shape, differing only in an
identifier value) must have identical expected module sets." Would catch this
class mechanically instead of relying on eyeballing.

**Note:** the underlying classifier flip for lifecycle prompts is now fixed
(S-context above), so regenerating the lifecycle set today would no longer
produce THIS contradiction. The guard is for the general case / future prompt
types.

**Status:** 🟡 open (2026-09-11). Tooling / process.

---

# CARRY-FORWARD

- **Main register verification pass** — re-run the ~14 open/verified issues in
  `docs/spire_overnight_findings.md` against current code; mark what still
  reproduces vs what has been resolved incidentally. The register was last
  updated 2026-08-14 and predates several changes.
