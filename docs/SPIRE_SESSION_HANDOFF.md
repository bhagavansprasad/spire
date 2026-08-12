# Paste this into the new window

You are continuing work on **Spire** — an AI-native natural-language query
system over Oracle Fusion Cloud (P2P + AR). Deterministic KG pipeline: parse →
plan → execute → synthesize. The two LLM boundaries are the parser (words →
Intent) and the synthesizer (records → prose); everything between is a KG
lookup, never a model judgement. Repo `github.com/bhagavansprasad/spire`,
working dir `~/pocs/spire`, pod `fa-esll-dev37-saasfademo1`, creds in the shell
env.

---

## LAST SESSION (2026-08-12): all P0 census bugs closed + REC-2 + readable refusals

Every P0 defect from the v1.7 overnight census (AI-1…AI-12) is now closed —
either fixed-and-committed this session or confirmed already-fixed by prior
work. Verified live on the pod at each step; full suite green (**863 passed,
18 deselected**).

### Shipped and committed this session

- **REC-2** (branch `rec-2-po-list-sample`) — "list all purchase orders" no
  longer refuses. The planner's no-filter PO guard is gone; the unfiltered
  path falls through to the (PurchaseOrder,'none') fetcher, which returns a
  bounded, ordered 25-row sample (`orderBy=OrderNumber:asc`, curl-confirmed
  server-side) plus the honest total via `totalResults` (17,408). Records built
  locally (`build_purchase_order_records`) — no LLM. Two follow-on bugs fixed
  in the same effort: a supplierless PO (Incomplete OrderNumber "1", SupplierId
  null→0) was mis-flagged as a hallucinated id (0 is now the "no supplier"
  sentinel, skipped in `response_validation.py`); and the LLM emitted only 15 of
  25 rows (plain-PO path now deterministic).

- **Readable planner-guard refusals** (branch `readable-planner-refusals`) —
  the four entity guards (ReceivablesInvoice, Invoice, Address, StandardReceipt)
  raised dense ValueError strings. Each now raises a structured
  `RefusalError(Refusal(MISSING_IDENTIFIER, entity))`; `plan_node` routes it into
  the same `state["refusal"]` channel the parser uses, so it renders through
  `capability_message` as Reason/Solution/Example (blank-line separated). A lazy
  import inside each guard breaks a planner→result→planner module-load cycle.
  `RefusalError` lives in `nl_parser/result.py`.

- **AI-12** — PO-with-children ("show PO X and its lines/schedules/
  distributions") now synthesizes LOCALLY (`build_po_with_children` +
  `po_with_children_buckets` in `p2p.py`, plus a branch in `synthesizer.py`),
  removing the LLM that copied the pod's raw `ReceivedAmount` (0/null pod-wide).
  Schedule Received is now DERIVED: `Amount * (ReceivedQuantity / Quantity)`,
  guarded. Distribution amount uses ex-tax `Ordered`.

- **AI-10** — "supplier sites for X" used to silently return addresses.
  `site`/`sites` are now `entity_synonym`s for Site (`kg_vocabulary` 118→120),
  and `correct_include_from_prompt` (`vocabulary.py`, run after the LLM, before
  `validate_intent`) deterministically replaces the mis-mapped Address include
  with Site when the raw prompt contains "site(s)". Site has no standalone-list
  fetcher, so it hits the Site gate (`intent_validation.py`) and refuses
  readably — short reason + tailored Solution/Example keyed on a distinct
  `SupplierSiteListing` marker (`capability.py`).

- **AI-7 (second facet)** — the receipts site filter runs client-side over a
  fetch capped at `OVERFETCH_LIMIT`; when the account holds more than the window
  (account 26360: 1,386; Santa Clara: 1,737) the few matches in the newest page
  were reported as complete. True account+site total is unobtainable (composite
  `q=` fails silently here), so `standard_receipts.py` now returns
  `truncated=True` / `total_available=None` — constructed DIRECTLY, since
  `ToolResult.build` can't express truncated-with-unknown-total — and the
  synthesizer discloses "unknown total in source; N examined". An xfail(strict)
  test documenting the bug now passes; marker removed.

- **Docs** — findings/status/requirements all updated (summary table cells,
  detail Status lines, §G19, requirements v1.9).

### Confirmed already-fixed (finding predated the fix — no code change)

- **AI-1** child-as-rows: PO lines/schedules/distributions, AR invoice lines,
  supplier contacts — all render as rows.
- **AI-4** honest edge-traversal denominators ("Examined 25 of 301; of those
  25, N match") on has_invoice_over_amount and has_no_recent_invoices.
- **AI-9** partial-column note (returns valid column, names invalid, lists
  available) — no wholesale refusal.
- **AI-11** Site gate refuses a Site include at parse time.

### NOT committed / branch hygiene note

All work this session was committed, but several commits landed on branch
`readable-planner-refusals` rather than dedicated branches, and two earlier
branches ended up merged to master directly. **Check `git branch` and the log
before pushing** — the human will want the branches/PRs sorted. REC-2's tool
work is committed (`d1779ec` era); the readable-refusals + AI-12 + AI-10 + AI-7
+ docs commits are on `readable-planner-refusals`.

---

## Likely NEXT (pick with the human)

1. **Branch/PR hygiene** — sort out what's on `readable-planner-refusals` vs
   master, push, raise PRs. Do this before more feature work.
2. **"Only local synthesizing" goal** — the human wants NO LLM in the
   synthesizer. Still on the LLM: **supplier+contacts** (confirmed this session,
   `synthesize out=2032`), and other multi-bucket shapes. AI-12's
   PO-with-children work is the exact template (a `build_*` + a
   `*_buckets` detector + a no-LLM branch before the fall-through).
3. **P0 FEATURES still unbuilt** (distinct from the P0 bugs, which are done):
   **COL-01** (projectable field coverage), **CSV-01** (export full result to a
   file — REC-2 makes this the natural companion: small→show all, large→sample,
   "all"→export). The SME's original column ask. §2A in the requirements doc.
4. **Entity-scoped synonyms** — unlocks price/amount/terms (COL-02 deferred
   these). Schema + expander change. Design work.
5. **GL / AP modules** — planned in `spire_plan.md`, not started.

Recommendation: **1 then 2** — clean up the branches, then start converting the
next LLM synthesizer path (supplier+contacts) to local, since the human asked
for all-local and the template is fresh.

---

## Still open (NOT P0 bugs)

- **AI-3** 🟢 — address-list synthesis token-heavy. Local-synthesis candidate
  (folds into the goal above).
- **AI-13** 🟡 — supplier list returns a different 25-row sample between
  identical runs. Pod curl-confirmed STABLE; variance is Spire-side
  client-filter/sample.
- **REC-1** ⭐ — completeness advisory; builds on AI-4 (already done).
- **COL-02** two acceptance criteria never closed: parse-input-token
  before/after measurement, and 06_slow/08_lifecycle isolated re-run.

---

## Reference

- REC-2: `planner.py` (guard removed), `purchase_orders.py` (orderBy),
  `p2p.py` + `synthesizer.py` (local build), `response_validation.py`
  (supplier_id 0 sentinel).
- Refusals: `RefusalError` in `nl_parser/result.py`; guards in `planner.py`;
  catch in `graph/pipeline.py` `plan_node`; render in `nl_parser/capability.py`
  (`capability_message`, `_IDENTIFIER_GUIDANCE`, `_OPERATION_SOLUTIONS`).
- AI-10: `correct_include_from_prompt` + `entity_synonyms` in
  `nl_parser/vocabulary.py`, called in `nl_parser/parser.py`; Site gate in
  `nl_parser/intent_validation.py`.
- AI-12: `build_po_with_children`, `po_with_children_buckets`,
  `_derived_received_amount` in `synthesizer/p2p.py`.
- AI-7: `standard_receipts.py` (direct ToolResult construction).
- Endpoints reference: `docs/spire_fusion_endpoints_reference.md` — updated
  2026-08-12 with `orderBy=OrderNumber:asc` server-side + totalResults 17,406.
- Canonical living docs: this handoff, `spire_enhancement_requirements.md`,
  `spire_enhancement_status.md`, `docs/spire_overnight_findings.md`,
  `docs/spire_plan.md`.

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
   upload. (The human prefers you to patch and hand back whole files directly.)
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
   with a debug print and read the runtime values before theorizing.
9. **pytest:** always `-q`. Full suite before any commit touching source;
   targeted tests during work.
10. **KG rebuild:** `python scripts/rebuild_kg.py` (never the .sh). When adding
    KG rows, bump expected counts in `scripts/print_kg.py` AND
    `tests/test_kg_metadata.py` together.
11. **Restart the MCP server after ANY change under `src/spire/mcp_server/`** —
    it holds the old module until restarted. (KG-only and other src changes do
    NOT need a restart.)
