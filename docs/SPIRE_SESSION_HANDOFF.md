# Paste this into the new window

Continuing **Spire** — AI-native NL query over Oracle Fusion Cloud (P2P +
AR). Deterministic KG pipeline: parse → plan → execute → synthesize. Tool
selection is a KG lookup, not an LLM judgement — the same Intent always
selects the same tool (a table join on `kg_entity_tool`/`kg_entity_filter`,
no scoring, no model). Not an agent architecture. Two LLM boundaries only:
the parser (words → Intent) and the synthesizer (records → prose).

Repo `github.com/bhagavansprasad/spire`, working dir `~/pocs/spire`, pod
`fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com`, creds in `personas.yaml`.
LLM = Gemini 2.5 Flash via Vertex. Colleagues: Siva, Venu (Oracle SME),
Pramod.

I'm attaching the post-fix overnight run bundle
(`overnight_postfix_bundle.txt` — the 12 set outputs + `_summary.txt` +
`_run_log.txt`, concatenated with `===== FILE: <name> =====` separators),
plus `spire_overnight_findings.md`, `spire_enhancement_requirements.md`, and
`spire_enhancement_status.md`. `spire_fusion_endpoints_reference.md` is the
authority on pod behaviour — read it BEFORE curling, not after.

---

## MY FOCUS THIS SESSION: verify the post-fix overnight run

Last session fixed the overnight-QA bugs and shipped them. **This session
reads the post-fix overnight output to confirm the fixes actually behaved and
nothing regressed** — then decides what (if anything) needs another pass.

The run completed cleanly: **all 12 sets exit 0, no timeouts, no crashes**
(~74 min total). That is necessary but NOT sufficient — the runner's own note
says it: **exit 0 means "ran to completion", NOT "answers are correct".** The
tally `run_prompt_set.py` prints is not a verdict. The work is reading the
answers, the same way the census was done: set by set, curl-verifying any
number that looks wrong.

### What shipped last session (what this run is testing)

Merged to master across 5 commits (`8ad9b39`, `37522b1`, `4360035`,
`b85eed1`, `eb2fd72`), then a docs commit (`2a84232`). 8 fixes + 1 feature +
1 refactor. Full suite 862 passed, 1 xfailed.

**Verify each fix behaved in the overnight output — check the specific
prompt, do not trust exit 0:**

- **QA-01 (child rows).** `02_purchase_order`, `03_ar` — "Show PO 2144 and
  its lines", AR invoice + lines. EXPECT: an indented child sub-table
  (`PO 162352 — lines:` with rows), NOT `Lines: 2`. Also PO schedules /
  distributions, AR invoice lines.

- **QA-02 (honest denominators).** `01_supplier`, `06_slow` — any
  edge-traversal filter ("small business suppliers", classifications,
  business-unit/site, invoice-amount, open-POs). EXPECT: "Examined 25 of
  432 suppliers. Of those 25, N match." — NEVER "N of 432" framing the
  matched count against the total.

- **QA-12 (completeness advisory).** Same prompts as QA-02. EXPECT a
  visually separated block:
  `─── Tip ───` / "Reading all 432 suppliers is slow. Narrow with a filter:
  business relationship, country, creation date, name, status." Filters come
  from `kg_entity_filter` (entity_level), never guessed. Only appears when
  the answer is a SAMPLE (examined < total).

- **QA-03 (receipts).** `03_ar` — "receipts for ABC Application Software at
  Santa Clara". EXPECT: the 25 receipts render in a table, prose and table
  agree. NOT "No receipts found". Root cause last time was a field-name
  mismatch (`receipts=` vs `standard_receipts=`), one word — NOT the site
  filter.

- **QA-04 / AI-11 (site-listing crash).** `01_supplier` / `05_refusals` —
  "Get supplier sites for suppliers". EXPECT: an honest refusal
  ("Supplier sites aren't available as a standalone listing…"), NO crash /
  exit-1. This was the ONLY exit-1 in the census; its absence from
  `_run_log.txt` is the first confirmation.

- **QA-05 (refusal message).** The Site refusal above, and any
  `UNSUPPORTED_OPERATION` refusal carrying a specific reason. EXPECT: the
  Reason line shows the SPECIFIC message, not the generic "a total, a
  ranking, a trend". NB the Solution line may still read generically — that
  was accepted as harmless.

- **QA-06 (mixed valid+invalid columns).** `04_columns`,
  `11_column_vocabulary` — "supplier name and credit rating for active
  suppliers". EXPECT: the valid column (Supplier) renders WITH an honest
  note ("the following column isn't available… credit rating. Available
  columns: …"). NOT a wholesale refusal that loses the valid column. This
  was a parser-prompt fix (non-deterministic) — the overnight run is exactly
  how to check it holds across phrasings, not just the one test prompt.

- **QA-07 (single-leg PO routing).** `08_lifecycle` — "How much of PO … was
  received?". EXPECT: routes to the lifecycle tool, a direct
  received/invoiced/paid headline + an ordered-vs-received amounts table,
  received "derived from quantity". NOT a generic PO description with the
  figure buried. Also a parser-prompt fix — check it holds across phrasings.
  NOTE: it needs the ORDER NUMBER (e.g. 162352), not the POHeaderId (2144) —
  a header-id input is a KNOWN DEFERRED gap, not a regression.

- **QA-08 — closed as not-a-bug.** `[debug] shape = None` under `show_all` is
  a diagnostic artifact, correctly gated. If you see it in the output, that
  is EXPECTED (this run is `show_all`), not a leak.

### The method (same as the census — measurement, not argument)

Read every prompt in every set. For anything that looks wrong, **curl the pod
to confirm before calling it a bug** — a claim from reading the log is not a
finding. Distinguish three things:
1. A fix that behaved (confirm and move on).
2. A NEW regression (a prompt that worked before now broken) — the important
   catch.
3. A pre-existing issue that was never in scope (note, don't conflate).

The census's own lesson repeated four times last session: **the reported root
cause was often wrong while the symptom was right.** Read the code / run the
prompt; don't trust the description.

### Known-deferred (NOT regressions — do not re-flag as new bugs)

- **AI-10** — "supplier sites for X" silently returns ADDRESSES (a
  parser-mapping bug). The crash sibling (AI-11) is fixed; this one is
  deferred. If a sites-for-a-named-supplier prompt shows addresses, that is
  the known gap.
- **"everything about X"** — refusal mis-routes to `UNSUPPORTED_FILTER`. The
  QA-05 message fix improved rendering, not the routing. Deferred.
- **POHeaderId → OrderNumber for lifecycle** — "PO 2144" not found by the
  lifecycle tool (keys on OrderNumber). Deferred.

### Do NOT re-investigate (curl-confirmed correct in the census)

Supplier count 429–432 (fluctuates slightly run to run — real, not a bug);
ABC Corp Americas open receivables −206,448.85; the 165M exposure ranking
with open=due for every account; negative/zero invoice amounts. All real pod
data. Details in the findings doc "Verified correct" table.

---

## What last session did (2026-08-06)

Worked the overnight-QA bug queue in cluster order, one item at a time, each
verified live on the exact prompt that exhibited it + full suite before
commit. Shipped 8 fixes + the QA-12 feature + a refactor (the two
`validation.py` files renamed to `intent_validation.py` /
`response_validation.py`). QA-08 closed as not-a-bug. Three items deferred
with documented reasons.

Notable: **four of the census's root causes were wrong on inspection** and
were corrected — QA-03 (field-name mismatch, not the site filter), QA-01
(narrower scope; contacts/tax-lines already correct), QA-04 (two different
parser mis-mappings, not one gap), QA-07 (a routing fix, not a new tool).
Full narrative in status doc **§G17**. Findings doc statuses all updated to
FIXED/PARTIAL/DEFERRED/CLOSED. Requirements §6C carries per-item status +
commit.

Two of the fixes (QA-06, QA-07) were parser-prompt changes — the lever G15
warned against — and both held on the first try, because they were
permissions/clarifications on top of structure that already existed (the
column split, the lifecycle tool), not new behaviours forced into the prompt.
That is why the overnight run matters: it's the check that they hold across
phrasings, not just the single test prompt.

---

## Working style (STRICT — the human relies on this)

1. **Short, interactive, ONE step at a time.** Brief statements, short
   sentences. One command at a time; verify before proceeding. Do not
   batch-generate. Do not throw 100+ lines to read.
2. **Ask permission before generating code or significant content.**
3. **Plain-text numbered options with a recommendation, and say why.** No
   widgets for choices. Options as plain text, kept interactive.
4. **Re-share the current full file before editing it** — files drift; ask
   for the current version, don't trust an earlier upload (this bit us mid-
   session: a bundle predated the validation.py rename and broke an import).
   When a file changes, deliver the COMPLETE updated file, never a
   patch/diff.
5. **Output to `t.txt`** — pipe through `tee` so it shows live AND saves
   (`command | tee t.txt`). `>` overwrite, `>>` append. Never a bare
   `> t.txt` that hides output.
6. **Git discipline:** one branch per logical change, PR-based merges, named
   files in `git add` (never `-A`), heredoc commit messages
   (`git commit -F- <<'EOF'`). Docs-only may go straight to master.
7. **Curl the pod before writing code** for any endpoint/field, and read
   `docs/spire_fusion_endpoints_reference.md` BEFORE curling. Update that doc
   when a new pod quirk is found. Creds are already in the shell environment.
8. **"Confirmed/verified" means actually curled/run.** A claim from reading
   code or logs is NOT a finding — say "appears correct from logs" until
   verified. Measurement over argument.
9. **pytest:** always run with `-q`. Full suite before any commit touching
   source; targeted tests during work. `cmp` is shadowed by a `.bashrc`
   function — use `command cmp` or `diff -q`.
10. **KG rebuild:** `python scripts/rebuild_kg.py` (never the .sh). When
    adding KG rows, bump expected counts in `scripts/print_kg.py` AND
    `tests/test_kg_metadata.py` AND the seed banner together.
11. **Restart the MCP server after ANY change under
    `src/spire/mcp_server/`** — it holds the old module until restarted.

---

## Suggested method for THIS session

1. Start with `_summary.txt` and `_run_log.txt` — confirm all 12 exit 0, no
   timeouts (already true). The absence of an exit-1 is the first QA-04
   confirmation.
2. Go set by set in the bundle. For each of the 8 fixes, find its prompt(s)
   and confirm the EXPECTED behaviour above. One fix at a time; say what you
   checked and what you found, briefly.
3. For anything that looks wrong, curl the pod to confirm before calling it a
   regression. Separate: fix-behaved / new-regression / known-deferred /
   pre-existing-out-of-scope.
4. Produce a short verdict per fix (held / regressed / needs another pass),
   and a list of any NEW findings worth a follow-up branch.
5. Only after the read: decide whether anything needs re-fixing this session,
   and if so, work it one item at a time with the fix-phase discipline
   (curl → full file → numbered options → change → verify → suite → branch).

Do NOT open a new fix before the read is done. The point of this session is
the verdict on the shipped fixes, not new work.

---

## Reference

- **Post-fix run bundle (the evidence for this session):**
  `overnight_postfix_bundle.txt` — 12 sets + summary + run log.
- **Bug list (now all marked fixed/deferred):**
  `docs/spire_overnight_findings.md` — rollup + per-finding detail + the
  shipped banner at top + "verified correct" table (don't re-open those).
- **Requirements §6C:** QA-01…QA-09 + QA-12, each with status + commit.
- **Status §G17:** the fix-phase narrative (and the 4 corrected root causes).
  §G16 is the earlier census.
- **Pod quirks:** `docs/spire_fusion_endpoints_reference.md` — read before
  curling. Key ones: composite `q=` fails silently (single-clause only);
  `fields=` 500s on `/standardReceipts`; `CustomerSite` on receipts is sparse
  and numeric (IDs, not names — the QA-03 discovery); classification/site are
  per-supplier child walks (no bulk filter); `q=` with spaces/quotes needs
  `+`/`%27` + `--compressed`, redirect to a file (not `python -m json.tool`).
- **Runners:** `scripts/run_graph.py` (single prompt, use
  `--show-planner`/`--show-synthesizer`/`--show-raw-output` to see routing
  and records), `run_prompt_set.py` (named set), `run_overnight.py` +
  `overnight_sets.yaml` (batch).
- **Measured pod totals:** ~429–432 suppliers (fluctuates), 2,111 credit
  memos, ~15,841 POs, ~48,931 invoices.
- **What's working (preserve):** PO lifecycle tool (now also the target for
  single-leg received/invoiced/paid questions), compare/aggregation tools
  (full-set, honest exclusion notes), currency-refusal, column projection +
  who-column synonyms + the new unknown-column note, planner-guard refusals,
  the QA-02 honest denominators + QA-12 advisory, QA-01 child sub-tables.
