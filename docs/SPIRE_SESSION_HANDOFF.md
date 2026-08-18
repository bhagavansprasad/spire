# Paste this into the new window

You are continuing work on **Spire** — an AI-native natural-language query
system over Oracle Fusion Cloud (P2P + AR). Deterministic KG pipeline: parse →
plan → execute → synthesize. The two LLM boundaries are the parser (words →
Intent) and the synthesizer (records → prose); everything between is a KG
lookup, never a model judgement. Repo `github.com/bhagavansprasad/spire`,
working dir `~/pocs/spire`, pod `fa-esll-dev37-saasfademo1`, creds in the shell
env.

---

## WHERE WE ARE (2026-08-14): overnight ran, was analyzed prompt-by-prompt, findings doc merged. NEXT = fix the issues.

The measurement overnight is **done and analyzed**. Do NOT re-run it — analyze
was the task, and it's complete. Results:

- **Synth calls 56 → 5** across 254 prompts (`overnight_20260814/`,
  `grep -rh "stage=synthesize" | wc -l`). Per-set: 00(1) 01(1) 10(2) 11(1); every
  other set 0. **03_ar = 0** — AR (the suspected hiding place) is fully local.
- The **5** are two shapes only: **Shape A** address-as-target lists ("addresses
  for supplier N", `target=Address`, 3 calls) and **Shape B** single PO + buyer
  ("Show PO N and its buyer", 2 calls, output already correct). Both are small
  single-shape conversions.
- Count is **trustworthy, not a floor**: `06_slow` exited 1 on ONE pod-timeout
  prompt (register #30), 14/15 ran, not a synth path.

**The findings doc is already merged and complete:** `docs/spire_overnight_findings.md`
now holds the full register (1–35), with the 10 new issues (#26–#35) **grouped by
fix-theme at the top**, the 2026-08-14 status folded into #1/#5/#6/#7/#9, and a
verbatim per-set evidence appendix. `spire_enhancement_status.md` §OVN and the six
touched requirements (OUT-04, OUT-06, COL-02, COL-03, UX-01, UX-03) are updated too.
Read the register before starting — it has the full Expected/Verification/Fix/Status
for each issue.

### The 10 new issues, and what re-verified

**Fixes holding across the full set:** #3 (invoice lists local), #4 (PO 2144
id-type), #6 (unsupported_operation Solution — but AI-5 half re-opened, see below),
#12 (who/audit → fields), #21 (PO-with-children), #23 (sample-and-disclose),
lifecycle `build_lifecycle_summary` (zero synth across 28 variants).

**New issues, grouped by the fix that closes them:**

- **Projection layer (COL-02) — biggest cluster, one resolver fix closes four:**
  **#34 🔴** projection on a multi-step plan binds the wrong step-output → em-dash
  on a value that provably exists (OrderNumber 162352 shown as "—"; no curl gate).
  **#31 🟡** single-step join field (invoice PurchaseOrderNumber) em-dash is
  ambiguous, null-vs-unresolved (curl owed). **#7/#28 🟠** `country`→Address
  substitution re-confirmed + new `state`/`city` siblings (`TaxpayerCountryCode` on
  body, nullable). Plus #12's projection guard.
- **Partial results over capped fetches (OUT-06):** **#27 🔴** credit-memo "total
  value" sums 25 of 2,249, labelled as the total (twice) — silently wrong aggregate.
  **#35 🟡** `top N` dropped on the credit-memo list path. **#33 🟡** classification
  filter examines 25 of 341 (discloses sampling, still can't answer). **#26 🟡**
  truncation note says "examined for filtering" when no client filter ran.
- **Parser robustness (new):** **#32 🔴 — TOP FINDING.** Parser drops the PO
  identifier on some lifecycle phrasings ("Is PO 162034 complete?"); the planner's
  fallback for a filter-less PurchaseOrder intent is *list-all* → 25 of 17,447
  unrelated POs, silent, no error. 162034 is real; other phrasings answer it fine.
- **Refusal (UX-01):** **#29 🟡** refusal detail-text is non-deterministic (parser
  words it, not a fixed lookup). **#6** AI-5 `unsupported_filter` "narrow by…"
  re-opened (emitted for untracked attributes where narrowing can't help).
- **Performance:** **#30 🟡** "top N suppliers" compare fetches the whole PO
  universe (17,447) → pod timeout; named/single compare is bounded and fine.

---

## NEXT STEP: fix the issues, harm-first and cheap-first

Recommended order (rationale: stop silent-wrong-answers first, then the cluster
that closes the most, then the rest). One branch per logical change, PR-based;
docs-only straight to master.

1. **#32 fault (b) — planner fail-safe guard.** SMALLEST high-impact fix. A
   filter-less PurchaseOrder intent with no explicit "list" request must raise a
   structured refusal, NOT `search_purchase_orders {}`. It must distinguish an
   explicit "list purchase orders" (valid sample-and-disclose) from a
   dropped-identifier query. This alone stops the 25-of-17,447 dump regardless of
   the parser. Then (a) strengthen parser extraction for "Is PO N complete?" /
   "…blocking?" / "…outstanding?" to route to the lifecycle tool.
2. **Projection cluster (COL-02):** #34 first (no curl gate — bind projection
   per-column to the step-output that holds it), then #7/#28 synonyms
   (`country`/`state`/`city` → TaxpayerCountryCode / nested Address, render null
   cleanly, no Address injection), then #31 after its curl. One resolver change
   closes #34/#31/#7/#12-guard.
3. **Partial results:** #27 (aggregate over ALL credit memos like the exposure
   path does over 500, OR refuse to print a total over a truncated sample) + #35
   (thread top_n into the credit-memo list path) + #33.
4. **Refusal determinism:** #29 (source detail-text from a fixed capability table
   keyed on (code, entity/attribute)) + #6 AI-5 re-open (name the missing
   attribute instead of "narrow by…").
5. **Theme A last two shapes:** #1 Shape A (`build_address_records` + dispatch),
   Shape B (local join+narration). Re-measure for 0.
6. **#30** bounded top-N compare (select top-N first, then fetch their POs);
   **#26** branch note wording; **#5** collapse the double-negation.

### Curls owed BEFORE coding the gated items (Phase-0 style, read the endpoints doc first)
- **#31** do EIP invoices carry `PurchaseOrderNumber` on the pod (null vs unread)?
- **#27** does `list_receivables_credit_memos` aggregate server-side?
- **#33** is supplier classification server-filterable (composite `q=` fails here)?

### Acceptance rules (unchanged)
1. **No LLM synthesis anywhere** — every `stage=synthesize` is a finding.
2. **Refusal format** — Reason / Solution / Example then `(refusal: <code> — <detail>)`,
   and now (per #29) the detail-text must be a fixed lookup, not parser free-text.
3. **"Confirmed" = curled or run**, never inferred from code/logs. Re-run the
   affected set after each fix: zero new synth, unchanged answers, the specific
   discrepancy gone.

### Owed (smaller)
- **Regression tests** locking `build_lifecycle_summary`, the contacts builder, and
  #5 (empty-result) are still not written — additive, worth adding as you touch
  each path.
- When a fix lands, update `docs/spire_overnight_findings.md` (flip the issue to
  fixed with commit ref) and `spire_enhancement_status.md` §OVN.

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
