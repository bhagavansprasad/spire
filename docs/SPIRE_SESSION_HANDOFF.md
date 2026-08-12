# Paste this into the new window

You are continuing work on **Spire** — an AI-native natural-language query
system over Oracle Fusion Cloud (P2P + AR). Deterministic KG pipeline: parse →
plan → execute → synthesize. The two LLM boundaries are the parser (words →
Intent) and the synthesizer (records → prose); everything between is a KG
lookup, never a model judgement. Repo `github.com/bhagavansprasad/spire`,
working dir `~/pocs/spire`, pod `fa-esll-dev37-saasfademo1`, creds in the shell
env.

---

## MY FOCUS LAST SESSION: COL-02 field synonyms (SHIPPED to a branch)

Built the field-synonym feature end to end, on branch
`col-02-multi-field-expansions` (NOT yet pushed / PR'd). Four groups, all
committed, suite green (862 passed, 1 xfailed).

### What shipped (on the branch, not master)

- **Mechanism:** new `field_synonym` vocab_kind in `kg_vocabulary`.
  `expand_field_synonyms` in the parser runs AFTER the LLM produces the Intent
  and BEFORE `validate_intent` — the model passes the term through, code does
  the expansion (splits the comma-joined value, dedupes, preserves order). This
  is the whole point: a KG lookup, not a model judgement.
- **Group 1** — multi-field expansions: who columns / who details / audit
  columns / audit fields → the four who-columns; creator details / created
  details → CreatedBy, CreationDate.
- **Groups 2+3** — legacy EBS (vendor / vendor name → Supplier, vendor number →
  SupplierNumber, trx / trx number → TransactionNumber) and field-level
  (creation/created/date-created → CreationDate; last-updated/modified/changed-
  on/update-date → LastUpdateDate; qty → Quantity; uom / unit of measure →
  UnitOfMeasure).
- **Group 4** — who-columns extended to PurchaseOrder, Invoice,
  ReceivablesInvoice: 12 `kg_entity_field` rows PLUS a projection fix in three
  fetchers (`purchase_order_by_id.py`, `invoices.py`,
  `receivables_invoice_by_id.py`). The KG row alone was NOT enough — the
  synonym resolved but the fetchers projected a fixed field list that omitted
  the columns, rendering them empty (em-dashes) until `_PROJECTED_FIELDS` was
  extended.
- **Test fix** (separate commit) — dropped stale hardcoded live-pod balances
  from `test_customer_invoices_tool.py` (they drift with pod data).

Counts now: `kg_vocabulary` 118, `kg_entity_field` 210.

### Determinism — proven, not assumed

The diagnostics do NOT show a pre-expansion draft (there is no such print;
`show_parser` shows the final Intent). So determinism was proven behaviorally:
a throwaway synonym `'zztest' → CreatedBy,Supplier` — a string the model has no
basis to expand — expanded correctly, so the expansion is code, not the LLM.
(zztest row was removed after.)

### Deferred WITH evidence (do not re-attempt blindly)

- **Ambiguous terms — price, amount, terms.** 'price' is Price on
  PurchaseOrder but UnitSellingPrice on ReceivablesInvoice; 'amount' is Ordered
  vs LineAmount; 'terms' has no PaymentTerms column in the KG. Global synonyms
  can't map one term to different columns per entity. Would need ENTITY-SCOPED
  synonyms — a mechanism change (schema + expander), its own task.
- **DFF/KFF.** Curl-confirmed on two invoices: the DFF children carry only
  `__FLEX_Context` (null or a bare label), no populated segment columns. Nothing
  to map. Pod configuration, not a Spire limitation.

### Outstanding on COL-02 (small — to fully close the requirement)

Two acceptance criteria NOT yet met:
1. **Parse-input tokens** measured before/after — the requirement says measure
   and report; not done. (The number is already printed: `in=NNNN` on the parse
   line — just capture before vs after a synonym expansion.)
2. **`06_slow` / `08_lifecycle` regression re-run** in isolation — full suite
   passes, but those two sets were not run specifically.

Until those two are done, COL-02 is "substantially delivered", not fully.

---

## Likely NEXT (pick with the human)

1. **Close COL-02 fully** — do the two outstanding measurements above (small),
   then it's genuinely done, not "with asterisks".
2. **Push the branch + raise PR** — it's at a natural boundary; merge COL-02.
3. **Entity-scoped synonyms** — the mechanism change that unlocks price/amount/
   terms. Design work.
4. **REC-2 (logged this session)** — replace the unbounded PO-list refusal with
   the sample-and-disclose pattern (show 25 + honest total), consistent with how
   supplier lists already behave. Sampling must be over a BOUNDED fetch, never
   the full ~15k. Relates to OUT-06 + CSV-01. Its own branch.
5. **Other roadmap** — the two P2P read-path conversions (invoice lists, PO
   lists — "still on the model" per status §G12.6), or the GL/AP future modules
   (planned in `spire_plan.md`, not started).

Recommendation: **1 then 2** — close the two small COL-02 gaps, then PR the
whole feature.

---

## New findings logged this session (in spire_overnight_findings.md)

- **AI-12** 🔴 — schedules sub-table shows raw `ReceivedAmount` (0.0, 0/null
  pod-wide) as a fetched column while prose narrates `ReceivedQuantity` ("1 of 1
  received"). The lifecycle tool derives+labels this correctly; the QA-01
  schedules renderer does not. Display-path fix.
- **AI-13** 🟡 — supplier list returns a different 25-row sample between
  identical runs. Raw `/suppliers` curl-confirmed STABLE (limit=25 and 200,
  identical order); variance is Spire-side client-filter/sample, not the pod or
  parser.
- **REC-2** 🟢 — PO-list-as-sample proposal (see NEXT #4).

---

## Working style (STRICT — the human relies on this)

1. **Short, interactive, ONE step at a time.** Brief statements, short
   sentences. One command at a time; verify before proceeding. Do not
   batch-generate. Do not throw 100+ lines to read.
2. **Ask permission before generating code or significant content.**
3. **Plain-text numbered options with a recommendation, and say why.** No
   widgets for choices.
4. **Re-share the current full file before editing it** — files drift; ask for
   the current version, don't trust an earlier upload. When a file changes,
   deliver the COMPLETE updated file, never a patch/diff. (This session: the
   human preferred me to patch and share whole files directly — worked well.)
5. **Output to `t.txt`** — pipe through `tee` so it shows live AND saves
   (`command | tee t.txt`). `>` overwrite, `>>` append. Never a bare `> t.txt`.
6. **Git discipline:** one branch per logical change, PR-based merges, named
   files in `git add` (never `-A`), heredoc commit messages
   (`git commit -F- <<'EOF'`). Docs-only may go straight to master.
7. **Curl the pod before writing code** for any endpoint/field, and read
   `docs/spire_fusion_endpoints_reference.md` BEFORE curling. Update that doc
   when a new pod quirk is found. Creds are in the shell env.
8. **"Confirmed/verified" means actually curled/run.** A claim from reading
   code or logs is NOT a finding — say "appears correct from logs" until
   verified. Measurement over argument.
9. **pytest:** always `-q`. Full suite before any commit touching source;
   targeted tests during work.
10. **KG rebuild:** `python scripts/rebuild_kg.py` (never the .sh). When adding
    KG rows, bump expected counts in `scripts/print_kg.py` AND
    `tests/test_kg_metadata.py` AND the seed banner inside `kg_schema.sql`
    together — the count lives in FOUR places.
11. **Restart the MCP server after ANY change under `src/spire/mcp_server/`** —
    it holds the old module until restarted. (KG-only changes do NOT need a
    restart.)

---

## Reference

- Feature branch: `col-02-multi-field-expansions` (unpushed).
- Synonym rows: `scripts/sql/kg_schema.sql` (search `field_synonym`).
- Expander: `expand_field_synonyms` in `src/spire/nl_parser/vocabulary.py`;
  called in `src/spire/nl_parser/parser.py` after the compare early-return,
  before `validate_intent`.
- Requirement: COL-02 in `docs/spire_enhancement_requirements.md`; delivery
  note appended there.
- Findings: `docs/spire_overnight_findings.md` (AI-12, AI-13, REC-2).
- Canonical living docs: this handoff, `spire_enhancement_requirements.md`,
  `spire_enhancement_status.md`, `docs/spire_plan.md`.
