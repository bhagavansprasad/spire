# Handoff — Spire (overnight triage complete; multi-module router is next)

Paste this into the new window to continue. This supersedes the prior handoff:
the overnight triage it recommended is DONE — 8 findings fixed and shipped, 4
resolved without code. The open work is the **multi-module router** (below).

---

## What Spire is

AI-native NL query over Oracle Fusion Cloud (P2P + AR). Deterministic KG
pipeline: **route → parse → plan → execute → synthesize**. Two LLM boundaries —
the module **classifier** and the **parser** (words → Intent); planning,
execution, and synthesis are deterministic (no LLM synthesis call). The KG is
the deterministic oracle: plans are COMPUTED from KG edges/filters/tools, not
chosen by a model. This is the core design bet and it is sound — keep it.

- Repo: `github.com/bhagavansprasad/spire`, working dir `~/pocs/spire`
- Current pod: `eqjz` (user `Axel.Grant`), creds in `personas.yaml`. **Spire
  reads `personas.yaml` ONLY** — the `IKS_FUSION_*` shell env vars are for curl
  scripts, NOT Spire. A wrong pod usually means the MCP server is stale (it
  loads the persona once at startup) — restart it.
- LLM: Gemini `gemini-3.5-flash` via Vertex AI, `GEMINI_TEMPERATURE = 0.0`,
  `LLM_MAX_OUTPUT_TOKENS = 8000` in `src/spire/config.py`.
- master is green: **905 passed, 18 deselected**. Everything below is merged.

---

## Architecture note (asked and answered, repeatedly — recorded so it stays settled)

The user periodically asks whether the KG is the source of Spire's bugs and
whether a multi-agent orchestration (orchestrator → per-module agent → LLM picks
tool) would be better. **Answer, consistently: no — keep the KG.**

Evidence from this session: nearly every bug lived in the CODE THAT READS the KG
(planner traversal, parser include-handling, synthesizer metadata threading,
router scoping, a tool's orderBy), NOT in the KG data. The KG was repeatedly the
ORACLE used to verify fixes ("no such edge exists → the planner is wrong"). A
correct KG kept catching incorrect code. Replacing it with LLM-driven tool
selection would move the determinism INTO the LLM and multiply exactly the
silent-failure + non-determinism problems this session eliminated (wrong numbers
stated confidently, wandering multi-hop joins) — minus the deterministic oracle
that made them findable. For a read-only NL-query system over ERP data with
multi-hop joins and zero tolerance for wrong figures, KG-deterministic is the
MORE scalable and MORE correct choice.

What actually costs the user: (a) KG COVERAGE being unfinished (new capability =
new KG rows + rebuild + tripwires), and (b) KG-change ERGONOMICS being heavy.
Both improvable WITHIN the KG approach; neither is a reason to abandon it.

---

## What shipped THIS session (branch fix/overnight-20260904 → PR #138; fix/overnight-batch2 → PR #139; both merged to master)

The overnight promptkit run (2026-09-04, `promptkit_overnight.py` over 9 sets)
was triaged by READING ANSWERS, not tallies. 8 findings fixed, each diagnosed
from evidence → fixed → tested → verified live on eqjz → committed atomically.

**Fixed & shipped:**
1. **#2 — ARApplication planner crash + receipt-include bleed.** "Show receipt
   applications for customer X" raised `KeyError: No edge from
   'AccountReceiptApplication' to 'AccountReceipt'`. TWO defects: (a) planner
   Block 3 (`planner.py`) assumed every include chains off the PREVIOUS include;
   two children of one root are SIBLINGS with no edge between them → fixed with
   chain-first / sibling-fallback edge resolution off the captured root; (b)
   parser (`vocabulary.py add_child_include_from_prompt`) added `AccountReceipt`
   because the bare trigger "receipt" matched inside "receipt applications" →
   fixed with a subsumption guard (suppress a single-word trigger when every
   occurrence is inside a longer sibling phrase that is present).
2. **#5b — AR nested child tables presented a page as the whole set.** Account
   with 2,319 receipts showed 10 with no total. The tools already compute
   `total_available`; the synthesizer's CustomerAccount branch only threaded the
   PARENT's truncation, not the children's. Fixed across `ar.py` (child_totals
   map on CustomerAccountRecord), `synthesizer.py` (compute per-child totals,
   bucket→label map), `display_formatters.py` ("showing N of M" in each child
   header). Flat-list narration was already correct and untouched.
3. **token-fix (promptkit).** Per-prompt "Token usage" printed the RUNNING total
   across all prompts (reset_usage() ran once before the loop). Moved
   reset_usage() into the per-prompt loop.
4. **#3 — exposure ranking refused** and **#4 — receipt-method distribution
   refused.** Both tools + planner + synthesizer + display were FULLY WIRED, but
   the parser refused `unsupported_operation`. Root cause: the router's
   module-scoped context DROPS `modes/m_aggregation.sysprompt` (its manifest
   module is "modes", not in Tier 1, not a classified module), so the only op
   teaching the scoped LLM saw was the `DraftAggregate.op` FIELD description,
   which listed only two ops. Fixed by extending that field description (the
   scoping-independent channel) to include `exposure_ranking` and
   `receipt_method_distribution` (`draft.py`). NOTE: this is the same
   "scoping drops mode files" issue logged as finding #6 below.
5. **#7 — receipt-method ran POD-WIDE + hung.** After #4, "receipt method
   distribution for customer X" returned ~50,000 receipts / $13.3B pod-wide
   (not the customer) and hung on the unbounded paging path. Root cause: the
   parser emits the scope as filter type `by_customer_name`, but
   `_build_aggregation_plan` whitelisted filter types against the tool's
   accepted params where the arg is `customer_name` — the `by_` prefix never
   matched, so the scope was dropped. Fixed with `_SCOPE_FILTER_TO_PARAM`
   (`registries.py`) mapping `by_customer_name → customer_name`, applied in
   `plan_builders.py` (identity fallback for unmapped types). Now returns the
   customer's own distribution, fast.
6. **#9 — Supplier "country"/"address" column request produced a
   SELF-CONTRADICTING answer.** Parser routed the location word to an Address
   include AND the display rendered the Address column, but ALSO printed "column
   'Country' isn't available" above it. Cause: `validate_intent` Step 4 (COL-03,
   `intent_validation.py`) split requested fields against the KG column catalog
   with no include-awareness. Fixed: `_FIELDS_SATISFIED_BY_INCLUDE`
   (Address → address/addresses/country/city/state); when that include is
   active those fields are skipped in the split (neither projected nor
   unresolved). Guard fires only when the covering include is present.
   CAVEAT (deferred, "AI-10"): "country" still MAPS to an Address include rather
   than a discrete Country column — the fix removes the CONTRADICTION, not the
   mapping. The codebase already flags AI-10 as a separate deferred parser-
   mapping issue in `intent_validation.py` Step 3b.
7. **5d — unfiltered "AR invoices for X" led with 2012 closed rows.**
   `get_customer_transactions` set `orderBy=TotalBalanceAmount:desc` only for
   `open_only`; the all-invoices path sent no order → pod default (oldest-
   first). Fixed: `orderBy=TransactionDate:desc` on the else branch (confirmed
   server-side in the endpoints reference). open_only keeps its balance-desc
   sort. Now leads with recent invoices.

**Resolved WITHOUT code (documented decisions):**
- **5c — "total value of credit memos"** — NOT a bug. Already refuses to total a
  truncated set honestly ("Showing 25 of 2,247... not totalled..."). Verified by
  reading the answer.
- **#6 — router scoping drops all `modes/*.sysprompt`** — DISMISSED as narrow.
  The scoping does drop mode files, but the only real impact was the two
  aggregation ops (#3/#4, now fixed via the field-description channel). Every
  other mode-dependent behavior (comparison, count, open-invoices, account-
  balance, top-N-open) works in production because its triggering rides on
  signals that survive scoping (field descriptions, filter types, flags).
  Verified: those five behaviors all produced correct answers under the router.
  (This is the SAME mechanism now relevant to the multi-module work below.)
- **#1 — "addresses for supplier X" refuses** — DISMISSED. By NAME it WORKS:
  "addresses for Lee Supplies" routes to `search_addresses` and returns 25
  addresses end-to-end. Only the by-NUMBER form ("addresses for supplier 1252")
  fails, and that is finding #8, not an Address problem. The handoff that raised
  #1 predates `search_addresses` / used a number example that tripped #8.
- **#8 — numeric-ID scoping** — WON'T DO (explicit user decision). "supplier
  1252" / "account 25750" cannot be scoped by number. Current behavior is
  honest (supplier refuses clearly; account returns empty — no wrong data). The
  KG catalog HAS the mechanism (Address/Invoice have a `supplier` filter doing
  `q=SupplierNumber=`), the endpoint supports `q=SupplierNumber=` and
  `q=AccountNumber=` (partially — account-activities `q=AccountNumber=` is
  UNVERIFIED), but Supplier/CustomerAccount lack the filter rows and the tools
  lack the args. Building it = tool arg + KG filter row + KG rebuild + tripwires
  + parser-emit + tests, per entity. Declined for now; recorded in case it's
  revived.

Suite went 886 → 905 (+19 tests), no regressions.

---

## Fresh overnight baseline (2026-09-09) — all 11 sets exercised, CLEAN

Re-ran the full overnight against the shipped code, into
`/home/bhagavan/pocs/spire/overnights/run_2026-09-09_1519/` (the user wants ONE
FOLDER PER RUN under `overnights/`; the runner takes `--outdir` and mkdirs it).

- All 9 routine sets GREEN. 03_ar and qa_testcases (which had the #2 crash on
  09-04) now PASS — the fix confirmed in a full run.
- 00_dipstick + 01_supplier initially exit-1 on the first pass — ALL failures
  were Fusion timeouts ("Upstream request timed out, please retry"),
  ENVIRONMENTAL, not code. Re-ran just those two (`--skip-generate
  --skip-validate`) on a responsive pod → both green (dipstick 6/6, supplier
  40/40). Confirmed environmental, not regression.
- 06_slow and 08_lifecycle are COMMENTED OUT of `promptkit_sets.yaml` (slow —
  minutes each), so their `.json` corpora never existed. Generated + ran them
  this session: **06_slow clean (all 3 phases)**; **08_lifecycle generate ✅,
  validate ❌ exit 1, run ✅ (20/20)** — the validate failure is the multi-module
  problem below, NOT a bug.

Housekeeping not yet done: the overnight regenerated `scripts/prompts/*.json`
(they show as modified on master's working tree) and created new untracked
`06_slow.json` / `08_lifecycle.json`. Decide whether to commit ("regenerate
corpora post-batch2") or discard. NOT urgent. The lifecycle corpus specifically
should NOT gate CI (its module classification flips — see below).

---

## Key facts / lessons (apply to all work)

- **The parser is non-deterministic near its ~8,000-token ceiling** — identical
  input can parse or refuse across runs. The KG is the deterministic oracle. The
  router (module scoping) exists to remove the ceiling as a constraint.
- **Teach the LLM via a SCOPING-INDEPENDENT channel where it must survive
  scoping.** The `modes/*.sysprompt` blocks are DROPPED by module scoping (only
  Tier 1 = core + refusals + the classified module's blocks are assembled). The
  `DraftAggregate.op` / `DraftFilter` FIELD descriptions are always seen. #3/#4
  were fixed by moving op-teaching to the field description for this reason.
- **Add deterministic signals in CODE post-parse** where possible, not in the
  prompt (respect the token ceiling). `add_child_include_from_prompt`,
  `_SCOPE_FILTER_TO_PARAM`, the #9 include-satisfied guard are the pattern.
- **"has a fetcher" ≠ "listable bare"** — Invoice/StandardReceipt/
  ReceivablesInvoice need scoping; refusing unscoped is correct.
- **Confirmed = actually run/curled**, never inferred from code.
- **Restart the MCP server after any change under `src/spire/mcp_server/`.**
- **KG rebuild:** `python scripts/rebuild_kg.py` (never the `.sh`); when adding
  KG rows/fields bump tripwires in `scripts/print_kg.py` AND
  `tests/test_kg_metadata.py` together. The classifier menu is generated by
  `scripts/build_classifier_context.py` from `kg_entity` + `kg_vocabulary`
  (entity synonyms) → `context/routing/classifier_menu.sysprompt`.
- **git state:** `personas.yaml` is tracked and on GitHub — if it holds live
  creds, rotate + `git rm --cached` (standing hygiene, not code). A
  `*:Zone.Identifier` gitignore line was added to stop Windows-copy junk.

---

## WORKING STYLE (STRICT — copy-paste into the new window)

1. Short, interactive, ONE step at a time. One command at a time; verify before
   proceeding. No batch-generating, no 100+ line dumps to read.
2. Ask permission before generating code or significant content.
3. Offer choices as plain-text numbered options with a recommendation and the
   reason. No widgets.
4. Deliver the COMPLETE updated file, never a patch/diff. Read the current full
   file (from the bundle/upload I provide) before editing — files drift.
5. Output via tee to t.txt (`cmd 2>&1 | tee t.txt`); `>` overwrite, `>>` append.
6. Git: one branch per logical change, PR-based merges, named files in `git add`
   (never `-A`), heredoc commit messages. Docs-only may go straight to master.
   Check the branch before committing.
7. Curl the pod before writing code for any endpoint/field; read
   `docs/spire_fusion_endpoints_reference.md` FIRST.
8. "Confirmed/verified" means actually run, never inferred from code/logs.
9. pytest always `-q`; full suite before any source commit; targeted during work.
10. KG rebuild: `python scripts/rebuild_kg.py` (never the `.sh`); bump tripwires
    in `scripts/print_kg.py` AND `tests/test_kg_metadata.py` together.
11. Restart the MCP server after any change under `src/spire/mcp_server/`.
12. Prefer deterministic signals in CODE post-parse; teach the LLM via the
    prompt/field-description only where it needs judgment (respect the ceiling).
13. I'm always in `~/pocs/spire` (no `cd` needed).

===============================================================================
## NEXT WORK — THE MULTI-MODULE ROUTER (design first, then build)
===============================================================================

### The trigger

Generating + running `08_lifecycle` this session exposed it. **08_lifecycle:
generate ✅, validate ❌ (exit 1), run ✅ (all 20 prompts PASS).** The validate
failures are ONLY these, and the TOOL is identical in every one:

    module: expected [procurement]            got [procurement, payables]
    tool:   get_purchase_order_lifecycle_status  (SAME both sides)
    module: expected [procurement, payables]  got [procurement]
    tool:   get_purchase_order_lifecycle_status  (SAME both sides)

i.e. the module CLASSIFICATION flips between `[procurement]` and
`[procurement, payables]` for the same lifecycle prompt across two LLM passes
(generate recorded one; validate got the other). The tool routing is stable, so
`run` passes; only the recorded-vs-observed module SET differs, so `validate`
fails.

### Root cause (confirmed, from reading router.py + classifier_menu.sysprompt)

The classifier is grounded ONLY by `classifier_menu.sysprompt`, which maps
ENTITY SYNONYMS → module. Its payables entry is:

    payables:
      Invoice (aka: bill, invoice)

So the classifier keys `payables` on the words "invoice"/"invoiced"/"bill".
EVERY lifecycle prompt says "invoiced" ("has PO 701337 been received, invoiced,
and paid"). So the classifier legitimately sees a procurement signal (PO) AND a
payables signal ("invoiced") and inconsistently includes payables. The classifier
NEVER sees `m_po_lifecycle.sysprompt` (that is a PARSER context, injected AFTER
routing) — it has no "lifecycle is one procurement query" awareness. This is the
SAME "scoping / grounding" family as finding #6.

Why `run` still passes both ways: `m_po_lifecycle.sysprompt` lives in the
PROCUREMENT blocks, which are assembled whenever procurement is in the module
set (both classifications include procurement). The extra payables blocks (when
present) are unused noise. So today the flip is FUNCTIONALLY COSMETIC but (a)
breaks validate determinism and (b) wastes tokens assembling payables context.

### THE DESIGN CONSTRAINT (user-stated, MUST honor)

**Cross-module prompts are a REAL, EXPECTED, FIRST-CLASS case — not an edge case
to suppress.** A prompt that genuinely spans payables + procurement +
receivables MUST be allowed to classify to MULTIPLE modules and be planned
across them. Do NOT "fix" the lifecycle flip by hard-collapsing to a single
module — that trains the classifier to UNDER-REPORT modules and fights the
cross-module future. Any change must leave the multi-module path intact and
working, and generalize beyond lifecycle.

### Why this is bigger than a lifecycle patch

`router.py`'s own docstring says the router is **INCREMENT 1 — the single-module
happy path**. Increment 2 (cross-module UNION + an "unsure" all-modules
fallback) is DEFERRED and NOT BUILT. `classify_modules` already RETURNS A LIST
and `assemble_subset` already TAKES A LIST of modules — so the plumbing is
partly scaffolded — but the behavior (consistent multi-module classification,
multi-module context assembly, planning that spans modules, and validate
comparing module SETS) is not finished. **The lifecycle flip is the first prompt
exposing the missing increment-2 multi-module handling.** Treat it as that, not
as a lifecycle special-case.

### Open design questions to resolve FIRST (do not code before deciding)

1. **What is the CORRECT module set for a lifecycle prompt** — `[procurement]`
   (the tool is procurement-rooted and reconciles payables internally) or
   `[procurement, payables]` (the prompt genuinely spans both)? This is the
   crux. Given the user's constraint (honor multi-module reality), leaning
   toward NOT forcing single-module — but the lifecycle TOOL being procurement-
   rooted means payables context would be assembled-but-unused, which argues the
   classifier should learn that lifecycle is a procurement query. Resolve this
   explicitly; it drives everything.
2. **Consistency mechanism.** The real problem is INCONSISTENCY, not "payables
   appears". Options (respect the constraint — none may hard-collapse
   multi-module in general):
   a. Ground the CLASSIFIER (via `_CLASSIFIER_INSTRUCTION` in `router.py`, the
      classifier's own prompt — NOT the auto-generated menu, which is
      regenerated) with a rule that makes multi-module classification
      deterministic for genuinely-multi-module prompts, and pins lifecycle to
      its correct set. Blast radius: affects EVERY prompt's classification —
      needs the full routing test suite.
   b. Deterministic post-classify normalization in CODE (`classify_modules`) —
      canonicalize the module set (e.g. stable ordering + a rule set), but
      "detecting lifecycle in code" duplicates signal.
   c. Make `--validate` compare module SETS order-insensitively and tolerate
      known-equivalent sets — fixes the validate symptom but leaves token waste
      and the underlying non-determinism. WEAKEST; does not honor the deeper
      "build multi-module properly" intent.
   Recommendation to weigh: build increment-2 multi-module handling PROPERLY
   (2a-style grounding + real multi-module assembly + validate set-comparison),
   with lifecycle as the first test case — rather than any lifecycle-specific
   patch.
3. **Multi-module context assembly.** When the set is genuinely multi-module,
   `assemble_subset` unions the blocks. Confirm token budget is acceptable
   (multiple modules' blocks vs the ~8k ceiling the router exists to relieve) —
   this is the tension: multi-module scoping partially reintroduces the ceiling.
   May need a policy (e.g. cap modules, or a relevance order).
4. **Validate semantics.** `promptkit --validate` currently compares the
   recorded module list to the observed one and fails on ANY difference. For
   multi-module it must compare SETS (order-insensitive) at minimum. Decide
   whether the corpus records a canonical set and validate normalizes both
   sides.

### First steps in the new window (for this work)

1. Read this handoff, `docs/features/prompt_to_intent_framework.md` (esp. §2.1
   D-router and the increment-2 notes), and `src/spire/nl_parser/router.py` +
   `src/spire/nl_parser/context_assembly.py` (`assemble_subset`, `KNOWN_MODULES`,
   `_CLASSIFIER_MENU`).
2. Confirm ground truth: `git log --oneline -8`, `python -m pytest -q` (expect
   905-ish), MCP server up on eqjz.
3. Resolve design question 1 (correct module set for lifecycle) with the user
   BEFORE coding. Then decide the consistency mechanism (Q2) — recommend
   building increment-2 multi-module handling properly, not a lifecycle patch.
4. Get `tests/test_router.py` to see how classification is tested; any change to
   classification is high-blast-radius (affects every prompt) and MUST keep the
   routing suite green + add multi-module tests.
5. Reproduce the flip deterministically to have a before/after:
   `python -c "from spire.nl_parser.router import classify_modules;
   [print(classify_modules('Has PO 701337 been fully received, fully invoiced,
   and fully paid?')) for _ in range(6)]" 2>&1 | tee t.txt`
   (temp is 0.0, so if it flips across identical calls, capture that — it is the
   core evidence and the thing the fix must stabilize.)

### Files this work will likely touch

- `src/spire/nl_parser/router.py` — `_CLASSIFIER_INSTRUCTION` and/or
  `classify_modules` (consistency mechanism). CORE — high blast radius.
- `src/spire/nl_parser/context_assembly.py` — `assemble_subset` multi-module
  union / any module policy.
- `scripts/promptkit.py` — `--validate` set-comparison semantics.
- `tests/test_router.py` — multi-module + lifecycle classification tests.
- Possibly `context/routing/classifier_menu.sysprompt` grounding — but that file
  is GENERATED by `build_classifier_context.py`; hand-editing is overwritten on
  regeneration, so classifier rules belong in `_CLASSIFIER_INSTRUCTION`, not the
  menu.
- NOT the KG unless the design concludes module ownership itself is mis-modeled
  (unlikely — this is a classifier grounding gap, not a KG data defect).

### Do NOT

- Do NOT hard-collapse multi-module classifications to single-module (violates
  the user's constraint).
- Do NOT hand-edit the generated `classifier_menu.sysprompt` (regeneration
  overwrites it).
- Do NOT gate CI on `08_lifecycle`'s validate until the classification is made
  consistent.
- Do NOT treat this as a lifecycle-only fix — it is the general increment-2
  multi-module router work, with lifecycle as the first exposing case.
