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

I'm attaching `SPIRE_SESSION_HANDOFF.md`, `spire_overnight_findings.md`,
`spire_enhancement_requirements.md`, and `spire_enhancement_status.md`. Read
the handoff first, then the findings doc — it is the bug list this session
works from. `spire_fusion_endpoints_reference.md` is the authority on pod
behaviour — read it BEFORE curling, not after.

---

## MY FOCUS THIS SESSION: fix the bugs, build the features

The previous session ran an overnight QA campaign — the full prompt-set
suite twice, analyzed set-by-set with pod curls — and produced a verified
bug list. That analysis is DONE. This session is the FIX phase: work through
the confirmed defects (QA-01…QA-09 in the requirements doc, = findings
AI-1…AI-11) and the feature (QA-12 = REC-1), in priority order, one at a
time, each verified before moving on.

The full detail for every item — prompt, actual vs expected, curl proof,
root cause, fix direction — is in `docs/spire_overnight_findings.md`. The
requirements doc §6C lists them as committed work with priorities;
`spire_enhancement_status.md` §G16 is the narrative.

### The fix queue, in priority order

**Start here — clearest single bug:**
- **QA-01 / AI-1 — child rows render as COUNTS, not rows.** "Show PO 2144
  and its lines" prints "Lines: 2" instead of the two lines. Rows ARE
  fetched; the table collapses them with `len()`. Root:
  `scripts/display_formatters.py` ~531/533/535 (PO lines/schedules/
  distributions) and ~562 (AR invoice lines). Also affects AR tax lines and
  supplier contacts. Does NOT affect single related records (a PO's buyer
  renders fine — so the fix is list-children only). One root cause, one fix
  (render child rows), wide impact. The synthesizer prose often already
  carries the detail, so the fix also removes a prose/table inconsistency.

**Highest value — the pair (do together, QA-02 is the floor, QA-12 the ceiling):**
- **QA-02 / AI-4 — partial stated as the total.** Edge-traversal filters
  report "2 of 429" where 2 is of the 25 examined, not of 429. Must read
  "examined 25 of 429; 2 of those 25 …". Pervasive across EVERY
  edge-traversal filter (all classifications, business-unit/site,
  invoice-amount, open-POs, no-recent-invoices). Also the slowest prompts
  (29-113s), same root cause (per-supplier child walk over the 25 fetched).
- **QA-12 / REC-1 — completeness advisory (feature).** When a query samples
  a capped set: deliver results found, state honest denominators (QA-02),
  AND recommend narrowing filters read from `kg_entity_filter` so a complete
  answer is cheap. Never refuse, never inflate — the query SUCCEEDED, the
  advisory is metadata on it (no third "refused" outcome). The compare tools
  already do this ("1,226 invoices not linked to a PO and excluded") —
  generalize that. Do NOT "just walk all 429" — ~7-8 min, unusable.

**The rest of the big four:**
- **QA-03 / AI-7 — false-empty contradiction.** "Receipts … at Santa Clara":
  prose says "All 25 have Site Santa Clara" then answer says "No receipts
  found" — 25 real receipts fetched. Client-side site filter drops rows or
  mis-sets the empty flag.
- **QA-04 / AI-10 + AI-11 — supplier sites broken two ways.** One phrasing
  silently returns ADDRESSES not sites (wrong-resource, no note); another
  CRASHES on missing `business_unit` arg (the sole exit-1). Root: Site has
  no proper standalone KG fetcher (long-known gap). Also: validate
  required args at PLAN time (graceful refusal), not execute time (crash).

**Refusal-quality:**
- **QA-05 / AI-5 — misdirected refusal messages.** "Narrow by country/status/
  name" template over-applied to non-narrowing refusals (payment terms,
  ratings, "everything about supplier X"). Real reason is in the parenthetical
  but not surfaced. FIX MODEL: the planner-guard refusals (05_refusals P7/P8,
  08_lifecycle P25/P26) are accurate with concrete examples — make parser
  refusals read like those.
- **QA-06 / AI-9 — mixed valid+invalid columns refused wholesale.** "supplier
  name and credit rating" refuses everything, loses "name". INCONSISTENT:
  COL-03's note WORKS for many unknown columns (07_alacarte P2), fails only
  when phrasings trip the model's upstream `unanswerable` before the split
  runs (the G15 limitation). Fix = stop the upstream refusal so the built,
  correct split is always reached.
- **QA-07 / AI-6 — specific question, generic answer.** "How much of PO 2144
  was received?" buries the figure in a generic PO summary. Wants a direct
  received-vs-ordered line (a dedicated "received" shape like the compare
  tool). Data is correct; relevance issue.

**Cleanup:**
- **QA-08 / AI-2 — `[debug] shape = None` leaks to user output.** Trivial;
  remove or gate.
- **QA-09 / AI-3 — address-list synthesis token-heavy** (out≈3133). Local-
  synthesis candidate; not wrong.

### Do NOT re-investigate (verified correct by curl last session)

Supplier count 429; ABC Corp Americas open receivables −206,448.85; the
165M exposure ranking with open=due for every account; the run-1
`01_supplier` exit-1 (transient Gemini rate-limit); negative/zero invoice
amounts. All real pod data or infrastructure — curl-confirmed. Details in
findings doc "Verified correct" table.

---

## What last session (2026-08-05) did

Two things: shipped the who-column feature, then ran + analyzed the overnight
QA campaign.

**1. COL-03 who-columns shipped (committed `833d8b6` on master).** Added
CreatedBy/CreationDate/LastUpdatedBy/LastUpdateDate to Supplier as
projectable KG fields (curl-confirmed on `/suppliers`), + the supplier
fetcher's `_PROJECTED_FIELDS`. The model resolves them with no prompt change
because the KG now says they exist. `kg_entity_field` 194→198 (bumped in
`print_kg.py`, `test_kg_metadata.py`, and the seed banner). Suite green (859
passed, 2 expected tripwires fixed). Detail: status doc §G15.
- Key pivot: layer 1 (the honest note) is built and tested but UNREACHABLE
  for a wholly-unknown column — the model sets `unanswerable=true` and emits
  an empty draft BEFORE the deterministic split runs. Making the column real
  in the KG (layer 3) is what fixed the who-columns. This is why QA-06 is
  "stop the upstream refusal," not "build the note" — the note already works.
- Side effect: layer 3 delivered much of layer 2 (synonyms) for free — the
  model maps "created by", "audit columns", "date created" to the real KG
  columns once they exist.

**2. Overnight QA campaign (analysis DONE, fixes NOT started).** Built
`scripts/run_overnight.py` + `scripts/overnight_sets.yaml` (batch runner,
isolated subprocess per set, per-set timeout, per-set output + run log +
summary). Ran the 12-set suite twice — run 1 diagnostics-off, run 2
`show_all` (tokens/Intent/plan/raw output; run 2 is primary). Analyzed all
12 sets set-by-set, curl-verifying suspected numbers. Produced
`docs/spire_overnight_findings.md` (11 bugs + 1 feature, full per-finding
detail) and recorded them in the requirements doc (§6C, v1.7) and status doc
(§G16).

---

## Working style (STRICT — the human relies on this)

1. **Short, interactive, ONE step at a time.** One command at a time; verify
   before proceeding. Do not batch-generate.
2. **Ask permission before generating code or significant content.**
3. **Plain-text numbered options with a recommendation, and say why.** No
   widgets for choices.
4. **Re-share the current full file before editing it** — files drift; ask
   for the current version, don't trust an earlier upload. When a file
   changes, deliver the COMPLETE updated file, never a patch/diff.
5. **Output to `t.txt`** — pipe through `tee` so it shows live AND saves
   (`command | tee t.txt`). Never bare `> t.txt` that hides output.
6. **Git discipline:** one branch per logical change, PR-based merges, named
   files in `git add` (never `-A`), heredoc commit messages
   (`git commit -F- <<'EOF'`). Docs-only may go straight to master.
7. **Curl the pod before writing code** for any endpoint/field, and read
   `docs/spire_fusion_endpoints_reference.md` BEFORE curling. Update that doc
   when a new pod quirk is found.
8. **"Confirmed/verified" means actually curled/run.** A claim from reading
   code or logs is NOT a finding — say "appears correct from logs" until
   verified. Measurement over argument.
9. **KG rebuild:** `python scripts/rebuild_kg.py` (never the .sh). KG always
   rebuilds from scratch. When adding KG rows, bump expected counts in
   `scripts/print_kg.py` AND `tests/test_kg_metadata.py` AND the seed banner
   together.
10. **Test discipline:** full suite before any commit touching source;
    targeted tests during work. `cmp` is shadowed by a `.bashrc` function —
    use `command cmp` or `diff -q`.
11. **Restart the MCP server after ANY change under `src/spire/mcp_server/`**
    — it holds the old module until restarted (this bit twice).

---

## Fix-phase method (proposed)

Per item, in priority order: (1) re-read the findings-doc entry; (2) if it
touches fetched data, curl to confirm the current pod behaviour; (3) ask for
the current full source file(s); (4) propose the fix as numbered options
with a recommendation; (5) on approval, make the change, deliver the complete
file; (6) verify — targeted test + a live re-run of the specific prompt(s)
from the findings doc that exhibited the bug; (7) full suite before commit;
(8) one branch, PR. Then close the item and move to the next. Do not fix
several at once — one bug, verified, before the next.

Suggested first target: **QA-01 (child rows as counts)** — clearest,
self-contained, one file (`display_formatters.py`), wide impact. Then
**QA-02 + QA-12** together (highest value). But confirm the human's choice
before starting — they may want a different order.

---

## Reference

- **Bug list (work from this):** `docs/spire_overnight_findings.md` — rollup
  table at top, per-set detail below, "verified correct" table (don't
  re-open those), "what's working well" (don't break those).
- **Requirements §6C (v1.7):** QA-01…QA-09 + QA-12, priorities.
- **Status §G16:** the overnight-campaign narrative.
- **Pod quirks:** `docs/spire_fusion_endpoints_reference.md` — read before
  curling. Key ones: composite `q=` fails silently (single-clause only);
  `fields=` 500s on `/standardReceipts`; classification/site are per-supplier
  child walks (no bulk filter); `q=` with spaces/quotes needs `+`/`%27` +
  `--compressed`, redirect to a file (not `python -m json.tool`).
- **Runners:** `scripts/run_graph.py` (single prompt), `run_prompt_set.py`
  (named set), `run_overnight.py` + `overnight_sets.yaml` (batch). The
  overnight run output folders are the analyzed evidence.
- **Measured pod totals:** 429 suppliers (426 active), 2,111 credit memos,
  ~15,841 POs, ~48,931 invoices.
- **What's working (preserve):** PO lifecycle tool (near-perfect consistency
  across phrasings), compare/aggregation tools (full-set, honest exclusion
  notes), currency-refusal, column projection + who-column synonyms,
  planner-guard refusals. The bugs cluster in the DISPLAY layer (QA-01) and
  the edge-traversal/message layer (QA-02/05/06); the computed core is clean.
