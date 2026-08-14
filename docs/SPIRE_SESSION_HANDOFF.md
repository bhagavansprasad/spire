# Paste this into the new window

You are continuing work on **Spire** — an AI-native natural-language query
system over Oracle Fusion Cloud (P2P + AR). Deterministic KG pipeline: parse →
plan → execute → synthesize. The two LLM boundaries are the parser (words →
Intent) and the synthesizer (records → prose); everything between is a KG
lookup, never a model judgement. Repo `github.com/bhagavansprasad/spire`,
working dir `~/pocs/spire`, pod `fa-esll-dev37-saasfademo1`, creds in the shell
env.

---

## LAST SESSION (2026-08-14): worked the 14 overnight issues — 8 fixed, 4 verified not-reproducible, 2 owner-parked; Theme A (local synthesis) converted for every KNOWN shape. NOT yet measured end-to-end.

Two acceptance rules drove the pass:
1. **No LLM synthesis anywhere** — every `stage=synthesize` call is a finding to
   convert to a local/deterministic builder.
2. **Refusal format** — Reason / Solution / Example then `(refusal: <code> —
   <detail>)`.

### What landed on master (two PRs, both merged)

**PR #130 (branch fix-12-who-details-routing) — merged (cf38f1a):**
- **#12 FIXED** — "who details" was misrouted to a Contact join (em-dash
  projection, fabricated miscount, 21k tokens). Parser rule routes who/audit
  columns to `fields`. Verified: fields=[Supplier,CreatedBy,CreationDate,
  LastUpdateDate,LastUpdatedBy], no synth, 9.6k tokens.
- **#4 FIXED** — PO 2144 resolved as POHeaderId in one path, OrderNumber in
  another → false "not found". Lifecycle tool now cross-tries POHeaderId on an
  OrderNumber miss, adopts the real OrderNumber, discloses it. 999999 still
  found=False. (mcp_server change — needed MCP restart.)
- **#6 FIXED** — dismissive `unsupported_operation` Solution ("do the rest your
  side") → "Ask for the underlying records and I'll return them for you to total
  or average." One shared fallback string in capability.py.
- **#8 FIXED** — suppliers-with-open-POs join was LLM-synthesized and miscounted
  its own table (said 42, table summed to 43). Local `_supplier_with_open_pos` +
  `build_suppliers_with_open_pos`; count now exact (43). No synth.
- **#3 FIXED** — plain invoice lists were LLM-narrated. Local
  `build_invoice_records` + `plain_invoice_bucket`. No synth. Updated the invoice
  schema-selection test to assert the local path.
- **#11 FIXED (CORRECTED from not-reproducible)** — planner unsupported-filter
  refusal emitted the OLD dense "REFUSED (planner guard): plan: ..." string. I
  first mislabeled this not-reproducible (the parser shadows it for the filters
  it catches). Then "purchase orders for supplier Staples" reproduced it — it
  reaches `_validate_intent_filters`. Converted that to raise
  `RefusalError(UNSUPPORTED_FILTER, offending_entity, offending_filters)`;
  plan_node routes it through capability_message. Removed dead
  `_ENTITY_EXAMPLE_PROMPT` import. Updated 8 planner tests to assert the
  structured refusal.
- **Doc pass** — spire_overnight_findings.md updated with all statuses + a top
  caveat that "not-reproducible" means "not triggered in the prompts tested",
  NOT "proven fixed".

**PR #131 (branch theme-a-contacts-join) — merged (cc68f7a):**
- **Contacts join FIXED (local)** — "contacts for Lee Supplies" (single) and
  "contacts for suppliers in US" (multi) were LLM-synthesized (~2k / ~22k
  tokens). THREE layers: (1) supplier_contacts TOOL now stamps parent SupplierId
  onto each contact row (the child body lacks it; the executor unwrap dropped the
  path key) — mcp_server change, MCP restart; (2) `_supplier_with_contacts` +
  `build_suppliers_with_contacts` in p2p.py group by SupplierId, read
  is_administrative from the flag; (3) synthesizer dispatch branch. Verified live:
  single + multi group correctly, no synth.
- **#5 FIXED (local)** — empty/not-found results were sent to the LLM (out=125 on
  "suppliers named Zzzqqx"). Added `_all_buckets_empty` + `_ENTITY_LABEL` map +
  a short-circuit after count/comparison, before the entity cascade → local "No
  <entity> found matching the criteria." No synth.
- **Lifecycle narration FIXED (local)** — single-PO lifecycle was LLM-synthesized
  (summary-only; the response model already copies every value verbatim). Added
  `build_lifecycle_summary(record)` + `_fmt_money` in lifecycle.py; synthesizer
  swaps the LLM call for the local summary. paid reads "not yet determined" when
  paid_state is unknown (never 0); outstanding lines omitted when a leg is
  complete. Verified across 3 cases: partial (701337), not-found (999999),
  fully-received (2144→162352) — all parse-only.
- **Address lists** — probed "suppliers with their addresses": ALREADY LOCAL
  (build_supplier_records handles nested addresses; plain_supplier_bucket fires).
  No work needed.

### Issues NOT fixed (correctly, not neglect)
- **#2, #10, #13, #14 — not-reproducible.** #2 curl-confirmed 338/336/2 and the
  intra-run contradiction is gone. #10 parser runs clean 5/5 at out=366 (no
  runaway). #13/#14 didn't reproduce. CAVEAT: "not-reproducible" = "not triggered
  in prompts tested", not proven fixed. #11 is the cautionary tale (was
  mislabeled, then reproduced).
- **#7 — OWNER DECISION.** country: TaxpayerCountryCode (on supplier body,
  nullable) vs Address.CountryCode. Verified real; the fix is a semantics choice
  for the requirements owner (Venu), not code we can decide.
- **#9 — OWNER DECISION (feature).** supplier-by-number lookup doesn't exist; the
  refusal is CORRECT. Building it is a scope call, not a bug fix.

---

## THE OPEN QUESTION — measure whether Theme A is actually DONE

Theme A (#1) = **0 `stage=synthesize` across all 254 prompts.** Starting point
was 56. We converted every shape NAMED in the findings doc (invoice lists, the
open-PO join, contacts join, empty results, lifecycle) plus confirmed address
lists already-local. **BUT the current count is UNMEASURED** — we converted
shape-by-shape from the doc, not from a fresh measurement. The doc's shape list
was never proven exhaustive.

**Most likely place remaining synth hides (NOT probed this session):** AR shapes
— receivables invoices, standard receipts, customer accounts — and credit-memo
narration. If the count isn't 0, start there.

### NEXT STEP (what the human wants): run a fresh overnight to VERIFY the fixes and MEASURE the synth count

This is the ONE justified overnight — its purpose is measurement, not new
findings. Run it SEQUENTIALLY (the human explicitly chose sequential over
parallel: the shared demo pod makes parallel results noisy, and this run needs a
trustworthy count).

```
python scripts/run_overnight.py --timeout 5400
```

~90 min, output in overnight_<YYYYMMDD>/. Then:

```
# per-set — which sets still synthesize
grep -rc "stage=synthesize" overnight_$(date +%Y%m%d)/ | grep -v ":0"
# total — THE answer to "how many prompts still use LLM synthesis"
grep -rh "stage=synthesize" overnight_$(date +%Y%m%d)/ | wc -l
```

Also check `_summary.txt` for any TIMED OUT / ERROR sets — an incomplete set
means those prompts didn't run and the count is a floor, not final.

**Interpreting the total:**
- **0** → local synthesis fully achieved; Theme A / #1 DONE. Also spot-check a
  few refusals still render Reason/Solution/Example. Then it's finished.
- **N > 0** → N prompts still synthesize. Find the shapes:
  `grep -rB8 "stage=synthesize" overnight_$(date +%Y%m%d)/ | grep -iE "prompt:|Intent:|target_entity"`
  Convert each on a FRESH branch off master (same pattern: detector +
  local builder in p2p.py/ar.py + synthesizer dispatch branch; the tool-stamp
  trick if a join key is missing). Re-measure.

Beyond the count, this overnight also re-verifies the 8 fixes hold across the
full set and that nothing regressed.

### Also owed (smaller)
- **Doc updates after the measurement:** spire_overnight_findings.md — flip #5
  → fixed, update #1 with all conversions + the final measured count; note
  contacts/lifecycle as done. (Only mark #1 fixed once the count is actually 0.)
- **No regression test** locks in `build_lifecycle_summary`, the contacts
  builder, or #5 — additive, worth adding.
- **qa_testcases (34 prompts)** was never triaged answer-by-answer (prior
  session). If the overnight surfaces anything there it's a new issue.

---

## Reference

- Findings register (house block format): `docs/spire_overnight_findings.md` —
  updated this session; has the not-reproducible caveat and #11 correction.
- Local-synthesis templates (Theme A, all now on master): supplier joins =
  `_supplier_with_open_pos`/`build_suppliers_with_open_pos` and
  `_supplier_with_contacts`/`build_suppliers_with_contacts` in `synthesizer/p2p.py`;
  plain lists = `build_invoice_records`/`plain_invoice_bucket`; empty =
  `_all_buckets_empty` + `_ENTITY_LABEL` in `synthesizer/synthesizer.py`;
  lifecycle = `build_lifecycle_summary` in `synthesizer/lifecycle.py`. Dispatch
  branches live before the LLM fallthrough in `synthesize_response`.
- Refusals: `RefusalError` in `nl_parser/result.py`; `_validate_intent_filters`
  in `planner/plan_builders.py` now raises structured UNSUPPORTED_FILTER; catch
  in `graph/pipeline.py` plan_node; render in `nl_parser/capability.py`
  (`capability_message`, `_FILTER_GUIDANCE`, `_OPERATION_SOLUTIONS`).
- Overnight tooling: `scripts/run_overnight.py` + `scripts/overnight_sets.yaml`
  (12 sets, SEQUENTIAL); `scripts/run_prompt_set.py` for a single set.
- Endpoints/pod quirks authority: `docs/spire_fusion_endpoints_reference.md`
  (read BEFORE curling; update when a new quirk is found).

### Pod quirks to keep in mind
- Composite `q=` fails silently (HTTP 200, totalResults 0) — single-clause only.
- `q=Status='ACTIVE'` returns 0 on suppliers — count Status client-side.
- Supplier population FLUCTUATES on this demo pod (333→338 within one session;
  ~336 ACTIVE / 2 INACTIVE). Don't treat a count drift as a bug.
- Contact rows do NOT carry parent SupplierId from Fusion — the tool now stamps
  it (see contacts fix). Same for sites/classifications (join key is the path).
- `expand=sites` silently ignored on bulk fetches.
- `/standardReceipts` has no default ordering (paginated fetches non-reproducible).
- The KG always rebuilds from scratch (`python scripts/rebuild_kg.py`).
- Executor unwraps ToolResult to an items list and DISCARDS top-level keys —
  scalars must be stamped onto each row to survive (the contacts SupplierId fix).

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
