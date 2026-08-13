# Paste this into the new window

You are continuing work on **Spire** — an AI-native natural-language query
system over Oracle Fusion Cloud (P2P + AR). Deterministic KG pipeline: parse →
plan → execute → synthesize. The two LLM boundaries are the parser (words →
Intent) and the synthesizer (records → prose); everything between is a KG
lookup, never a model judgement. Repo `github.com/bhagavansprasad/spire`,
working dir `~/pocs/spire`, pod `fa-esll-dev37-saasfademo1`, creds in the shell
env.

---

## LAST SESSION (2026-08-13): overnight re-run analyzed, all 12 sets triaged, consolidated issue register + fix plan produced

Ran a full overnight batch of all 12 prompt sets and read them line-by-line
against two acceptance rules the human set this pass:

1. **No LLM synthesis anywhere** — synthesis must be deterministic/local; every
   `stage=synthesize` call is a finding to convert.
2. **Refusal format** — every refusal must render as Reason / Solution / Example
   (blank-line separated) then `(refusal: <code> — <detail>)`. Any deviation is
   a finding.

### The overnight run (clean mechanically)
- `run_overnight.py --timeout 5400`, output in `overnight_20260812/`. All 12
  sets exit 0, ~67 min, no crashes/timeouts. **254 prompts, 56 `stage=synthesize`
  calls.** Exit 0 = ran, NOT correct — the value was in reading the answers.
- Bundle for analysis: concatenated to `overnight_20260812_bundle.txt`.

### What the read found — 14 OPEN issues, flat-numbered
All findings (this run + the still-open prior ones) were consolidated into ONE
flat serial series (1..25), open first then fixed, in
**`docs/spire_consolidated_issues_and_plan.md`** (NEW — the working register and
plan). Old AI-nn/REC-nn IDs kept only as "(was: …)" breadcrumbs + a mapping
table. The per-finding detail for the 12 new ones is also being written into
`docs/spire_overnight_findings.md` in that doc's block format.

Open issues 1–14, grouped into 5 themes (the fix plan is keyed to these):
- **Theme A — eliminate LLM synthesis (make it local):** #1 (run-wide, 56 calls,
  absorbs old AI-3), #3 (invoice-list narration drift — the "-163.16" mispairing,
  3 sets), #5 (empty/not-found answers go to the LLM), #8 (join summary miscounts
  its own table — "14 vs 15 suppliers, 54 vs 62 POs"), #12 synth half.
- **Theme B — refusal correctness & format:** #6 (dismissive "do the rest your
  side" Solution on `unsupported_operation`, 5 instances; absorbs old AI-5
  misdirection), #9 (single supplier by numeric ID FALSELY refused when columns
  requested — it resolves everywhere else), #11 (PO-filter planner guard still
  emits the OLD dense string, not the structured format), #13 (old AI-9/COL-03
  wholesale-refusal limitation).
- **Theme C — column/field resolution (this IS the P0 COL-01/02 workstream):**
  #7 ("country" reported unavailable + silently swapped for an Address column —
  TaxpayerCountryCode exists), #12 ("who details" misparsed → Contact join →
  em-dash projection + fabricated miscount, 21k tokens, worst answer in the run),
  #13.
- **Theme D — parser robustness & PO reference:** #4 (PO 2144 resolves as
  POHeaderId in one path, OrderNumber in another → false "not found"), #10
  ("What is outstanding on PO 701337?" blows the parser token ceiling,
  out=7984/MAX_TOKENS → false unparseable refusal — the known runaway-generation
  mode).
- **Theme E — count/sample consistency:** #2 (301 vs 299 supplier count — likely
  scope-labelling, all=301/active=299), #14 (old AI-13 sample variance).

Fixed/closed and retained for traceability as #15–#25 (old AI-1,4,6,7,10,11,12,
REC-1,REC-2 fixed; AI-2/AI-8 not-a-bug).

### 4 issues are SUSPECTED, not verified — curls owed (Phase 0)
Per "confirmed = curled", these have conclusive run evidence but need a pod curl
to pin the data before fixing: **#2** (all/active supplier totals), **#4** (PO
2144 id-type), **#7** (TaxpayerCountryCode populated), **#9** (SupplierNumber
1252 exists). Curl commands are in each issue block in the consolidated doc.

### Not done yet
- **`qa_testcases` (34 prompts) not triaged** — confirmed it RAN (1 synth, 34
  parses) but not read answer-by-answer. If it surfaces anything it's issue 26+.
- A stray **`ReadTimeout` on `get_purchase_order_by_id`** appeared on a
  *different* box (`/home/uday/venv/…`, 13:24 interactive, NOT the overnight
  run). Almost certainly transient pod lag; reproduce the PO-by-id prompt once
  before deciding if it's a real timeout-handling gap (would be Theme D).

---

## NEXT STEP: fix the reported issues (start Phase 1)

Fix plan (in `docs/spire_consolidated_issues_and_plan.md`), sequenced
cheapest-risk-first, one branch/PR per logical change, suite green before each:

- **Phase 0 — curls only** (no code): settle the 4 suspected issues (#2,#4,#7,#9).
- **Phase 1 — Theme C field-synonyms & projection safety:** #7 country→
  TaxpayerCountryCode + stop the Address injection; #12 "who details"→WHO columns
  + guard projection against columns absent from rows (kills the em-dash); #13
  advance COL-01/02. Mechanism = the existing COL-02 expander (KG lookup, not
  model judgement). **Smallest, most deterministic, high payoff — start here.**
- **Phase 2 — Theme B refusals:** #6 rewrite `unsupported_operation` Solutions +
  finish AI-5; #11 route the PO-filter guard through RefusalError; #9 re-route
  single-supplier-by-id-with-columns to the by-id lookup.
- **Phase 3 — Theme D parser/PO:** #10 degenerate-parse trigger + parse cap; #4
  cross-try POHeaderId/OrderNumber. (`--show-parser` repro first.)
- **Phase 4 — Theme A eliminate LLM synthesis (largest, staged):** convert one
  shape per PR using the #21 (AI-12) template — empty/not-found (#5) → address
  lists → invoice lists (#3) → single cases → joins (#8) → lifecycle last. Goal:
  0 `stage=synthesize` on a fresh overnight.
- **Phase 5 — Theme E:** #2 label scopes; #14 deterministic sample order.

**Recommendation: Phase 0 then Phase 1.** Curl the 4 suspected items first
(quick, unblocks them, honours "confirmed = curled"), then start Theme C
synonyms — small deterministic wins that also advance the P0 COL workstream, and
the expander mechanism is proven.

---

## Reference

- **Consolidated register + plan (USE THIS):** `docs/spire_consolidated_issues_and_plan.md`
  — flat 1..25 numbering, mapping table, theme map, phased plan, per-issue curl
  commands.
- Findings detail (house block format): `docs/spire_overnight_findings.md`.
- COL-02 expander (the mechanism Theme C reuses): `field_synonym` vocab_kind +
  synonym rows; expander runs AFTER the LLM, BEFORE validate_intent — a KG
  lookup. `expand_field_synonyms` / vocabulary in `nl_parser/vocabulary.py`.
- Local-synthesis template (Theme A): `build_po_with_children` +
  `po_with_children_buckets` in `synthesizer/p2p.py`, branch in `synthesizer.py`
  (this is how #21/AI-12 was closed).
- Refusals: `RefusalError` in `nl_parser/result.py`; guards in `planner.py`;
  catch in `graph/pipeline.py` `plan_node`; render in `nl_parser/capability.py`
  (`capability_message`, `_IDENTIFIER_GUIDANCE`, `_OPERATION_SOLUTIONS`).
- Endpoints/pod quirks authority: `docs/spire_fusion_endpoints_reference.md`
  (read BEFORE curling; update when a new quirk is found).
- Overnight tooling: `scripts/run_overnight.py` + `scripts/overnight_sets.yaml`
  (12 sets); `scripts/run_prompt_set.py` for a single set.
- Canonical living docs: this handoff, `spire_enhancement_requirements.md`,
  `spire_enhancement_status.md`, `docs/spire_overnight_findings.md`,
  `docs/spire_consolidated_issues_and_plan.md`, `docs/spire_plan.md`.

### Pod quirks to keep in mind (from prior sessions)
- Composite `q=` fails silently (HTTP 200, totalResults 0) — single-clause `q=`
  only.
- `expand=sites` silently ignored on bulk fetches.
- `/standardReceipts` has no default ordering (paginated fetches non-reproducible).
- The KG always rebuilds from scratch (`python scripts/rebuild_kg.py`).

---

## Working style (STRICT — the human relies on this)

1. **Short, interactive, ONE step at a time.** Brief statements, short
   sentences. One command at a time; verify before proceeding. Do not
   batch-generate. Do not throw 100+ lines to read.
2. **Ask permission before generating code or significant content.**
3. **Plain-text numbered options with a recommendation, and say why.** No
   widgets for choices.
4. **Deliver the COMPLETE updated file, never a patch/diff.** Re-share/re-read
   the current full file before editing — files drift; don't trust an earlier
   upload.
5. **Output to `t.txt`** — pipe through `tee` so it shows live AND saves
   (`command | tee t.txt`). `>` overwrite, `>>` append. Never a bare `> t.txt`.
6. **Git discipline:** one branch per logical change, PR-based merges, named
   files in `git add` (never `-A`), heredoc commit messages
   (`git commit -F- <<'EOF'`). Docs-only may go straight to master. CHECK you
   are on the intended branch before committing.
7. **Curl the pod before writing code** for any endpoint/field, and read
   `docs/spire_fusion_endpoints_reference.md` BEFORE curling. Update that doc
   when a new pod quirk is found. Creds are in the shell env.
8. **"Confirmed/verified" means actually curled/run.** A claim from reading
   code or logs is NOT a finding — say "appears correct from logs" until
   verified. Measurement over argument — when a fix isn't visible, instrument
   with a debug print and read runtime values before theorizing.
9. **pytest:** always `-q`. Full suite before any commit touching source;
   targeted tests during work.
10. **KG rebuild:** `python scripts/rebuild_kg.py` (never the .sh). When adding
    KG rows, bump expected counts in `scripts/print_kg.py` AND
    `tests/test_kg_metadata.py` together.
11. **Restart the MCP server after ANY change under `src/spire/mcp_server/`** —
    it holds the old module until restarted. (KG-only and other src changes do
    NOT need a restart.)
