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

### S4 🔴 open — PurchaseOrder cannot be filtered by supplier/status as a ROOT query — a natural, common request refuses; supporting it is a small feature, not a one-row fix (PRIORITY)

**Trigger prompt:** "list open purchase orders for supplier Dell" (and the corpus
shape "Open POs for supplier JGA."). Both refuse with
`unsupported_filter — PurchaseOrder cannot be filtered by 'supplier', 'status'`.

**Why this matters (the real concern behind it):** this is a bread-and-butter
business question. A user reasonably expects it to work. Today it gets a flat
refusal. The refusal is *truthful* (see root cause) but the capability boundary
is narrower than what users will naturally ask — and every such gap currently
costs a multi-file expansion. This finding is both the specific fix AND a
concrete data point for the scalability question (how cheap is it to add a
capability?).

--- WHAT WAS VERIFIED (not inferred) ---

1. **The Spire tool already supports it.** `search_purchase_orders`
   (src/spire/mcp_server/tools/purchase_orders.py) signature accepts
   `supplier_name` (substring on Supplier), `supplier_id` (exact SupplierId),
   and `status` (exact StatusCode). Its docstring states the strategy: "send a
   single clause via q=, filter remaining clauses in Python." So the tool is
   built for this.

2. **Fusion supports each clause ALONE, server-side (curled on pod eqjz).**
   - `q=StatusCode='OPEN'` -> `totalResults: 1112`, HTTP 200.
   - `q=SupplierId=300000047507499` (EIP Inc) -> `totalResults: 2023`, HTTP 200.

3. **Fusion's COMPOSITE q= fails SILENTLY (curled, the dangerous quirk).**
   - `q=StatusCode='OPEN' AND SupplierId=300000047507499` -> `totalResults: 0`,
     HTTP 200 — despite each clause having thousands of matches and a non-empty
     true intersection. This is the composite-q= silent-zero quirk the endpoints
     reference documents for /invoices, /suppliers, /standardReceipts (lines 22,
     68) — now confirmed on /purchaseOrders too. A tool that composited these
     server-side would report "no open POs for this supplier" — a plausible,
     wholly WRONG answer with no error. This is why the fix must filter one
     clause client-side, and why it must not be rushed.

4. **The `po_status` vocab already maps the values** (kg_vocabulary, 18 rows):
   open->OPEN, active->OPEN, closed->CLOSED, completed->CLOSED, canceled->CANCELED,
   incomplete->INCOMPLETE, etc. StatusCode is case-sensitive (OPEN, not Open).

--- ROOT CAUSE (corrected — this is a DESIGN BOUNDARY, not a bug) ---

The refusal is raised by `_validate_intent_filters` (planner.py): every intent
filter is checked against `_entity_level_filter_types()` (from `kg_entity_filter`
via `_load_filter_defs`). PurchaseOrder's registered entity-level filters are
ONLY: `by_id`, `created_before`, `created_since`, `lifecycle_status`. `supplier`
and `status` are absent, so they are rejected as UNSUPPORTED_FILTER.

Crucially, this is DELIBERATE, documented in generate_plan itself
(planner.py, the PurchaseOrder root branch): "the KG's PurchaseOrder root filters
(by_id, created_before, created_since, lifecycle_status) scope the fetch, and any
OTHER filter (status, supplier — not PO entity-level filters) is refused one layer
down ... it has the wrong ones." supplier/status on POs were intentionally scoped
to the EDGE-TRAVERSAL direction only (`has_open_PO` = "suppliers that HAVE an open
PO", supplier-rooted, routes to search_purchase_orders with supplier_id+status) —
NOT as PO-rooted root filters.

So the earlier read ("coverage gap / bug") was wrong. It is a deliberately narrow
capability boundary. The tool params exist because the EDGE path uses them, not
because PO-root filtering was built.

--- WHY IT IS NOT A 2-ROW FIX ---

`_resolve_client_filters` (planner.py) — the only code that splits a filter into
"server clause + client-side remainder" — is written ONLY for edge-traversal
filters (it raises KeyError for non-edge types) and only implements the
`status_filter` pattern for the `has_open_PO` case. There is NO general mechanism
to take TWO client-side entity-level root filters and send one server-side while
applying the other in Python. That mechanism must be built.

--- ROADMAP (priority; do it right, not fast — silent-wrong-answer risk) ---

Step 0 — Design the root combined-client-filter mechanism BEFORE writing rows.
   Decide how a PO root query with {supplier, status} builds a single fetch:
   the more selective clause (usually SupplierId, 2023 vs pod-wide) goes to the
   tool as a server arg; the other (status) becomes a client_filter applied
   after. Confirm search_purchase_orders is reachable on the entity-level root
   path (not only the edge path) and that two client-side filters compose. This
   is the load-bearing step — get the server/client split wrong and you ship
   silent-zero answers.

Step 1 — Planner code. Extend the root entity-level plan builder to:
   (a) route `supplier` -> supplier_id (all-digit) / supplier_name (else),
       mirroring Invoice's supplier filter digit-vs-name routing;
   (b) emit status as a client_filter {field: StatusCode, op: equals,
       value: resolve_vocab('po_status', term)} rather than a server clause when
       combined with supplier;
   (c) when supplier is absent, status alone MAY go server-side (q=StatusCode)
       since it works alone (1112) — but the simplest correct rule is
       "one clause server, rest client", matching the tool's own contract.
   Generalise `_resolve_client_filters` (or add a root sibling) so it is not
   edge-only. Ships with an isolated harness proving the server/client split for
   the {supplier, status}, {supplier}, {status} cases.

Step 2 — KG rows (kg_entity_filter), query_style='client_side' (VERIFIED correct
   by the composite-fails curl). Draft rows already prepared this session:
     PurchaseOrder | supplier | entity_level | tool_arg 'supplier' | client_side | Supplier | LIKE
     PurchaseOrder | status   | entity_level | tool_arg 'status' | vocab po_status | client_side | StatusCode | equals
   Do NOT use server_q — the composite silent-zero makes that a wrong-answer trap.

Step 3 — Remove the deliberate refusal for these two on PurchaseOrder
   (_validate_intent_filters will pass once the rows exist; confirm the
   generate_plan root branch comment/guard is updated so intent is honoured, not
   refused).

Step 4 — KG ceremony: rebuild (`python scripts/rebuild_kg.py`); bump the
   kg_entity_filter row-count tripwires in scripts/print_kg.py AND
   tests/test_kg_metadata.py together (+2).

Step 5 — Corpus. "Open POs for supplier JGA." in 08_lifecycle.json currently
   expects `refuse:unsupported_filter (planner)`. After the fix it routes to
   search_purchase_orders — update the expected tool (this is the S3 pattern: a
   corpus entry that enshrined the old refusal). Curate from a verified
   end-to-end run, not a guess.

Step 6 — VERIFY END-TO-END, curl-cross-checked. Run "open POs for supplier
   EIP Inc" (a supplier known to have POs) and confirm the returned set matches
   an independent curl (supplier server-side + status client-side). A
   non-refusing answer is NOT enough — the COUNT must be right, because the whole
   risk here is a plausible wrong number. Full pytest -q before commit.

--- ANALYSIS: what this says about scalability (the user's larger question) ---

The KG-deterministic design is working AS DESIGNED here: faced with a query it
was not built for, it refused cleanly and truthfully rather than hallucinating or
returning garbage. That is the design succeeding, not failing — for ERP data, a
clean refusal beats a confident wrong number.

The real issue the user identified is relocated, and it is legitimate: the set of
SUPPORTED capabilities is narrower than what users naturally ask, and EXPANDING it
is manual, multi-file work each time (KG rows + new planner logic + tool routing +
corpus + tests). This one natural request costs a small feature. That is the
genuine scalability cost.

Two systemic follow-ups worth their own findings/design (do NOT build reactively):
  (a) A CAPABILITY-COVERAGE AUDIT: cross-reference each tool's accepted params /
      the documented Fusion filters against the KG's registered entity_filter
      rows, and report every gap. Converts "discover an unsupported capability by
      a user hitting it" into a known, closeable list — answers "how many more of
      these are there" with a number instead of a surprise.
  (b) Reduce per-capability cost: much of the manual work is the client/server
      split logic and tool-arg routing. A more general root-filter mechanism
      (this finding's Step 1, done well) is reusable — every future
      entity+filter then becomes closer to "just KG rows" rather than new code.

--- Status: 🔴 open (2026-09-11). PRIORITY. Not a bug in the sense of "wrong
    code" — a deliberately narrow capability boundary that should be widened,
    carefully, because the underlying Fusion composite-q= quirk makes the naive
    implementation return silent-wrong answers.

# CARRY-FORWARD

- **Main register verification pass** — re-run the ~14 open/verified issues in
  `docs/spire_overnight_findings.md` against current code; mark what still
  reproduces vs what has been resolved incidentally. The register was last
  updated 2026-08-14 and predates several changes.
