# Spire — Consolidated Issue Register & Fix Plan

**Prepared:** 2026-08-13, after the overnight re-run of all 12 prompt sets
(`overnight_20260812/`). Cross-checked against `spire_overnight_findings.md`,
`spire_enhancement_status.md`, and `spire_enhancement_requirements.md`.

**Updated:** 2026-08-14, after a fresh sequential overnight (`overnight_20260814/`)
read prompt-by-prompt. New issues #26–#35 are grouped by fix-theme in the **NEW ISSUES**
section immediately below; status updates from this run were folded into #1, #5, #6, #7, #9;
full per-set evidence is in the **Appendix**. Synth calls: 56 → 5 (measured).

**Numbering:** one flat serial series (1, 2, 3, …). Open issues first, then
fixed/closed ones. The old identifiers (AI-nn, REC-nn, COL-nn) are kept only as
a "(was: …)" breadcrumb and in the mapping table below, so existing git commits,
docs, and test names stay traceable.

**Severity:** 🔴 real defect (wrong/missing data or wrong behaviour) · 🟠 defect,
lower blast radius · 🟡 minor / cosmetic · 🟢 note (efficiency or future work).

**Status:** `open` · `verified` (confirmed real, fix defined, not built) ·
`fixed` · `not-a-bug`.

> A note on rigour, carried from the findings doc: "confirmed" means curled or
> run, not inferred from code or logs. Several open items below are marked
> **suspected** — the run evidence is conclusive that the behaviour is wrong,
> but a pod curl is still owed to pin the exact data before the fix lands.

---

> **On `not-reproducible`:** this status means the issue's symptom could NOT be
> triggered in the prompts tested on current code — NOT that it is proven fixed.
> Several of these were resolved by intervening work; the register was stale.
> But #11 was a cautionary case: it was marked not-reproducible because the
> symptom wasn't triggered, then reproduced later via a prompt not initially
> tried ("purchase orders for supplier X") and turned out to be a live bug now
> fixed. So treat every not-reproducible as "not seen in testing" and re-open it
> if its symptom surfaces in an overnight run — that transcript is the repro.

## Mapping table (old ID → new number)

| New | Old ID | Status | One line |
|----:|--------|--------|----------|
| 1 | new + AI-3 | open | LLM still used for synthesis across the run (no-LLM-synth goal) |
| 2 | new | not-reproducible | Supplier count contradiction gone; curl-confirmed 338/336/2, both scopes labelled |
| 3 | new | fixed | Plain invoice lists built locally (build_invoice_records); no LLM, no drift |
| 4 | new | fixed | Lifecycle tool cross-tries POHeaderId when OrderNumber misses; PO 2144 resolves |
| 5 | new | open | "Not found"/empty answers are LLM-synthesized instead of a local template |
| 6 | new + AI-5 | fixed | unsupported_operation Solution rewritten constructively; verified live |
| 7 | new | verified | "Country" reported unavailable and silently replaced with Address column |
| 8 | new | fixed | Suppliers-with-open-POs built locally; count exact (43), no LLM |
| 9 | new | reclassified (feature) | No supplier-by-number lookup — refusal is correct; missing capability, not a bug |
| 10 | new | not-reproducible | Parser runs clean on PO 701337 (out=366, 5/5 runs); no token-ceiling runaway |
| 11 | new | fixed | CORRECTION (was not-reproducible): reproduced via "POs for supplier X"; _validate_intent_filters now raises structured RefusalError |
| 12 | new | fixed | "who details" now routes to WHO columns (fields), not a Contact join |
| 13 | AI-9 / COL-03 | not-reproducible | Wholesale refusal on wholly-unknown columns (G15) — could not be triggered on current code |
| 14 | AI-13 | not-reproducible | Two identical "list all suppliers" runs returned the same 25 rows (diff clean) |
| 15 | AI-1 | fixed | Child rows rendered as counts, not rows |
| 16 | AI-4 | fixed | Partial result stated as the total (wrong denominator) |
| 17 | AI-6 | fixed | Specific question answered with a generic summary |
| 18 | AI-7 | fixed | Self-contradiction "All 25 have Site X" then "No receipts found" (+ truncation disclosure) |
| 19 | AI-10 | fixed | "Supplier sites" returned addresses, not sites |
| 20 | AI-11 | fixed | "Supplier sites for suppliers" crashed (missing business_unit arg) |
| 21 | AI-12 | fixed | Schedules Received = 0.0 shown as fetched, contradicting prose |
| 22 | REC-1 | fixed | Completeness advisory (Tip block) |
| 23 | REC-2 | fixed | Unbounded PO-list refusal → sample-and-disclose |
| 24 | AI-2 / QA-08 | not-a-bug | `[debug] shape = None` was a show_all artifact |
| 25 | AI-8 | not-a-bug | Exposure ranking magnitudes are real pod data |
| 26 | new (2026-08-14) | open | Truncation note says "examined for filtering" when no client filter ran (cosmetic) |
| 27 | new (2026-08-14) | open 🔴 | Credit-memo "total value" sums 25 of 2,249, labelled as the full total |
| 28 | new (2026-08-14) | folded → #7 | country → Address substitution — same defect as #7; evidence merged into #7 |
| 29 | new (2026-08-14) | open | Refusal detail-text non-deterministic (parser-worded, varies across sets) |
| 30 | new (2026-08-14) | open | "Top N suppliers" compare fetches entire PO universe → pod timeout |
| 31 | new (2026-08-14) | open | Join-field projection renders em-dash ambiguously (null vs unresolved) |
| 32 | new (2026-08-14) | open 🔴 | Parser drops PO id on some phrasings; planner list-dumps all POs instead of refusing |
| 33 | new (2026-08-14) | open | Classification filter examines first 25 of N; true match count unknowable |
| 34 | new (2026-08-14) | open 🔴 | Projection on a multi-step plan targets wrong step-output → em-dash on a value that exists |
| 35 | new (2026-08-14) | open | `top N` selector ignored on the credit-memo list path |

---

## Theme map (similar issues combined — drives the fix plan)

- **Theme A — Eliminate LLM synthesis (make it all local):** 1, 3, 5, 8, 12(synth part). **2026-08-14: 56 → 5**; only Shape A (address-target) and Shape B (PO+buyer) remain.
- **Theme B — Refusal correctness & format:** 6 (AI-5 half re-opened), 9 (consistency), 11, 13, **29** (non-deterministic detail-text).
- **Theme C — Column / field resolution & PROJECTION SAFETY:** 7 (=28, country/state), 12(vocabulary part + projection guard), 13, **31** (null-vs-unresolved em-dash), **34** (wrong-step projection). *This is now the largest cluster — one resolver fix closes 7/12/31/34.*
- **Theme D — Parser robustness & PO reference resolution:** 4, 10, **32** (dropped-id → list-dump; incl. the fail-safe planner guard).
- **Theme E — Count / sample consistency & partial results:** 2, 14, **26** (filter-note wording), **27** (partial credit-memo total), **33** (classification sampling), **35** (top-N dropped), **30** (unbounded top-N compare fetch).

---

# ═══════════════════════════════════════════════════════════════════
# NEW ISSUES — 2026-08-14 overnight (grouped by fix-theme)
# ═══════════════════════════════════════════════════════════════════

**Prepared:** 2026-08-14, after a fresh sequential overnight of all 12 prompt sets
(`overnight_20260814/`), read prompt-by-prompt against three checks: refusal-format
consistency, synthesis local-vs-LLM, and prose-vs-rows discrepancy. Full per-set
evidence is preserved verbatim in the **Appendix** at the end of this document.

These issues are numbered #26–#35 continuing the existing serial series, and grouped
below by the theme that will fix them (so one fix closes several). Each also carries
its existing-theme tag (Theme A–E) to slot into the Fix Plan. **#28 is not listed
here — it proved to be the same defect as existing #7** (country → Address); its
2026-08-14 evidence was folded into #7. The three status updates surfaced this run
(#5, #6, #9) were folded into those existing register entries.

**Run headline:** LLM-synthesis calls dropped **56 → 5** across 254 prompts. The 5 are
two shapes only (Address-as-target list ×3; single-PO+column ×2). AR — the suspected
hiding place — showed **zero** synth. But the run surfaced defects more serious than the
residual synth: a **parser+planner list-dump** (#32) that answers a specific PO question
with 25 unrelated POs, and a **wrong-step projection** (#34) that renders a present value
as an em-dash. See the Fix Plan for sequencing.

---

## Group N1 — Projection layer (Theme C) — the biggest cluster

Three symptoms, one layer: the column-projection resolver mishandles any field that
isn't a plain top-level scalar. Fixing the resolver's step/scope binding and the
synonym map closes all three, plus existing #7 and #12's projection guard.

- **#34** (🔴) wrong-step binding — provable, no curl gate.
- **#31** (🟡) single-step null-vs-unresolved — curl owed to set null vs unread.
- **country/state** — folded into **#7** (TaxpayerCountryCode synonym; Address injection).

### 34 🔴 open — Column projection on a multi-step plan targets the wrong step-output → em-dash on a value that exists — (was: new, 2026-08-14; the proven mechanism behind shape B)

**Set:** 11_column_vocabulary, prompt "Show PO 2144 with order number and agent".

When a plan has multiple step-outputs (here `po` then `buyers`, from `include:['Buyer']` +
`fields:['OrderNumber']`), the projection renders against the LAST/wrong step-output. It built
"buyers (1 record) — columns: OrderNumber" and printed `—`, even though OrderNumber = "162352"
is present in the `po` step-output shown in the same response. The requested column exists and
was projected against a step that doesn't carry it.

**Expected:** projection resolves each requested column against the step-output that actually
holds it (the primary/target entity's output), not the last step. OrderNumber should render
162352; the `agent`/Buyer.DisplayName column should resolve from the `buyers` output (May Gee),
not be dropped. (The prose synth already has both correct — the structured table should match.)

**Verification:** read from run output — Intent (`include:['Buyer']`, `fields:['OrderNumber']`),
two Outputs (`po` with OrderNumber 162352, `buyers` with DisplayName May Gee), projected table
"buyers — columns: OrderNumber" showing `—`. **No pod curl needed** — both values are present in
the block; the fault is projection scoping, provable from the log.

**Root cause (candidate):** the projection field-resolver binds to a single step-output (the
last, or the one whose name it defaulted to — here `buyers`) instead of resolving per-column
across step-outputs, or instead of binding to the target-entity output.

**Fix:** bind projection to the target-entity step-output for target columns, and resolve
included-entity columns (agent→Buyer.DisplayName) from their own step-output — i.e. per-column
step resolution. This is the multi-step sibling of #31 (single-step null-vs-unresolved) and
shares the country/state mapping gap (#28) as the third face of a projection-layer theme.

**Status:** 🔴 open (2026-08-14). Correctness bug — a present value (OrderNumber 162352)
rendered as em-dash because projection read the wrong step. Proven from the log; this is the
mechanism behind the shape-B em-dash. Higher confidence than #31 (no curl gate).


### 31 🟡 open — Join-field projection renders em-dash ambiguously (no value vs unresolved) — (was: new, 2026-08-14; same class as shape B / #1)

**Set:** 07_alacarte, "Show me invoices for EIP Inc with invoice number, PO number, and PO
line number". Also the shape-B PO+column case (sets 10/11) under #1.

When a projected column is a cross-entity/join field, the projection renders `—` for every
row with no indication of WHY. Here `PurchaseOrderNumber` is listed as an available Invoice
column, is projected, and shows `—` on all 25 rows. The reader cannot tell whether the
invoices genuinely lack a PO link or the projection failed to resolve the field. The
compare path elsewhere shows many invoices ARE non-PO (Lee: 1,242 unlinked), so em-dash
MIGHT be correct here — but "might be correct" rendered identically to "silently broken" is
itself the bug.

**Expected:** distinguish the two cases. If the field is genuinely null for a row, render a
value that says so unambiguously and, where a whole column is empty, note it ("none of
these 25 invoices carry a PO number"). If the field is a join the projector can't resolve,
resolve it (as the PO-with-lines path resolves Buyer) rather than emitting em-dash. Never
let "no value" and "unresolved" collapse to the same glyph.

**Verification:** read from run output — `PurchaseOrderNumber` column all em-dash on
prompt 784; shape-B Buyer em-dash on prompts 10/11. **Curl owed**: fetch a few of these EIP
invoices and check whether PurchaseOrderNumber is populated on the pod (disambiguates
null-vs-unresolved and sets the fix).

**Root cause (candidate):** the projection field-resolver reads only top-level scalar keys;
join/derived fields (Buyer.DisplayName, a PO number that lives on a line/match, not the
invoice header) resolve to empty and print the em-dash placeholder, indistinguishable from
a true null.

**Fix:** (a) resolve join fields in projection the way the record-view paths do; (b) failing
that, mark unresolved-vs-null distinctly and disclose all-empty columns. Unifies with shape B
under #1 and the country-swap #28 — all three are the projection layer mishandling non-plain-
column fields.

**Status:** 🟡 open (2026-08-14). Correctness-of-display bug; curl owed to set null-vs-
unresolved. Same root as shape B (#1) and #28.


> **Also in this group (existing entries):** #7 (country → TaxpayerCountryCode; the
> 2026-08-14 `state` sibling and re-confirmation are folded into #7) and #12's
> projection guard against columns absent from the row. All four share the resolver fix.

---

## Group N2 — Partial results over capped fetches (Theme E)

Aggregates/filters computed over the default 25-row sample and presented as if complete.
The ranking paths already aggregate-before-capping correctly (exposure "of 500", spend
"of 41/66"), proving the machinery exists — these paths just don't use it.

- **#27** (🔴) credit-memo "total" sums 25 of 2,249, labelled as the total. Reproduced twice (03_ar, qa).
- **#35** (🟡) `top N` dropped on the credit-memo list path (adjacent to #27, same path).
- **#33** (🟡) classification filter examines 25 of 341; true match count unknowable (does disclose sampling).

### 27 🔴 open — Credit-memo "total value" is a truncated sample-sum labelled as the full total — (was: new, 2026-08-14)

**Set:** 03_ar, prompt "What is the total value of credit memos?"

A total/aggregate question is answered with a 25-row sample plus a line "Total credit
value: -232863.06" that sums only those 25 rows, while the same answer discloses
"Showing 25 of 2,249 credit memos." No qualifier marks the total as partial. Because
one sampled row is -220,000, the sample-sum is not even representative. The user reads
a partial figure as the population total.

**Expected:** either (a) compute the true total over all 2,249 credit memos server-side
(as the exposure-ranking path already ranks over all 500), or (b) if a full total isn't
feasible, state that explicitly and refuse to print a number that looks complete — e.g.
"I can't total all 2,249 from a 25-row sample; ask for a bounded set and I'll total it"
(the #6 unsupported-aggregate pattern). Do NOT print "Total credit value: X" computed
over a truncated sample.

**Verification:** read from run output — Answer discloses "25 of 2,249", prints "Total
credit value: -232863.06", Truncation note "2249 total in source; 25 examined for
filtering", Records returned 25. The -220,000 row is visible in the 25-row table.
**NOT yet pod-curled** — needs a curl to confirm whether `list_receivables_credit_memos`
can aggregate server-side (informs fix path (a) vs (b)). The DISPLAY bug (partial sum
labelled as total) is provable from the output alone.

**Root cause (candidate):** the credit-memo builder stamps `total_credit` over the
returned (capped) rows and the answer renders it as "Total credit value" unconditionally,
regardless of truncation. Contrast the exposure path, which aggregates before capping.

**Fix (design decision — needs owner):** aggregate-over-all vs honest-refusal. Same
class as #6 (unsupported aggregate) and the sample-and-disclose principle applied to
AGGREGATES, not just lists. Higher severity than the list case because a wrong total is
silently authoritative.

**Status:** 🔴 open (2026-08-14). Correctness bug — a partial aggregate presented as
complete. Pod curl owed to choose the fix path.


### 35 🟡 open — `top N` selector ignored on the credit-memo list path — (was: new, 2026-08-14)

**Set:** qa_testcases, prompt "List recent credit memos, top 5" (also "List recent credit
memos" variants).

A "top 5" / "top N" qualifier on a credit-memo list is dropped: the answer returns the default
25-of-2,249 sample instead of 5. The `top N` selector is honoured on other list paths (set 03
"Show me the top 5 open invoices for customer ABC" returns 5 correctly), so this is specific to
the credit-memo list path.

**Expected:** "top 5 credit memos" returns 5 rows (newest-first), consistent with the invoice
top-N path. If ordering for credit memos isn't reliably determinable (cf. the standardReceipts
no-default-ordering quirk), disclose that rather than silently returning 25.

**Verification:** read from run output — prompt says "top 5", answer says "Showing 25 of 2,249".
Contrast set 03 top-5 invoices (correct). Log-evidenced. **Curl not needed** for the display
bug; may need a curl to confirm credit-memo ordering support for the fix.

**Root cause (candidate):** the credit-memo list builder doesn't read the top_n selector from
Intent (or the parser doesn't populate it for this entity), so it falls to the default cap.

**Fix:** thread top_n into the credit-memo list path as it is on the invoice path. Group with
#27 (both live on the credit-memo list/total path) and the #33/#27 "partial results over capped
fetches" theme.

**Status:** 🟡 open (2026-08-14). Selector-dropped defect on the credit-memo path; adjacent to
#27 (same path). Curl optional.


### 33 🟡 open — Classification/attribute filter examines only the first 25 of N; true match count unknowable — (was: new, 2026-08-14)

**Set:** 10_refusal_examples, prompt "suppliers with classification Minority Owned".

The classification filter runs client-side over a capped fetch: "Examined 25 of 341
suppliers. Of those 25, 1 match the filter." Matches among the 316 unexamined suppliers are
never counted. For a "suppliers with classification X" query, the answer is really "1 among
the 25 sampled", not the population count. Unlike #27 the sampling IS disclosed, but the
result still under-represents.

**Expected:** either fetch/filter across all 341 (server-side if the classification is
filterable; else page all and filter), or, if a full scan is infeasible, state the match
count is a floor from a sample and offer to widen. Same class as #27 (aggregate/filter over
a truncated set) and the "determinism can worsen representativeness" principle.

**Verification:** read from run output — "Examined 25 of 341 suppliers. Of those 25, 1 match
the filter." **Curl owed** to check whether supplier classification is server-filterable on
this pod (composite `q=` fails here, so a single-clause classification filter may or may not
work) — determines whether the fix is server-filter or full-page-scan.

**Root cause (candidate):** classification is a client-side filter applied after the default
25-row cap, with no escalation to a full scan when matches are sparse.

**Fix:** server-side classification filter if supported; otherwise full-page scan for
attribute filters, or explicit floor-disclosure. Group with #27/#33 under a "partial results
over capped fetches" theme.

**Status:** 🟡 open (2026-08-14). Representativeness defect; discloses sampling (so below #27
in severity) but still can't answer the filter query correctly. Curl owed.


---

## Group N3 — Parser robustness & safe fallback (Theme D) — highest-impact

- **#32** (🔴) — **the top finding of this run.** Parser drops the PO identifier on some
  lifecycle phrasings ("Is PO 162034 complete?"), and the planner's fallback for a
  filter-less PurchaseOrder intent is *list-all* → 25 of 17,447 unrelated POs, silently,
  with no error. Two faults; fault (b) — the unsafe planner fallback — is the small
  fix-first safety net (fail to a refusal, not a dump). **Nuance for the guard:** an
  *explicit* "list purchase orders" is a valid filter-less intent (correct sample-and-
  disclose), so the guard must distinguish explicit-list from dropped-identifier.

### 32 🔴 open — Parser drops PO identifier on some lifecycle phrasings; planner then list-dumps all POs instead of refusing — (was: new, 2026-08-14)

**Set:** 08_lifecycle. Prompts "Is PO 162034 complete?", "Is anything blocking PO 162034?",
"Has PO 999999999 been fully received, fully invoiced, and fully paid?".

Two compounding faults produce a silent, authoritative-looking wrong answer:
1. **Parser non-determinism:** for these phrasings the parser emits a bare
   `target_entity: PurchaseOrder` intent — no filter, no lifecycle op (out≈103–113 tokens,
   vs the fuller Intent the working lifecycle prompts produce). The PO number and the
   received/invoiced/paid/complete/blocking operation are dropped. The SAME PO (162034)
   parses correctly under the phrasing "Has PO 162034 been fully received, fully invoiced,
   and fully paid?".
2. **Unsafe planner fallback:** a filter-less `PurchaseOrder` intent plans
   `search_purchase_orders {}` and returns "Showing 25 of 17,447 purchase orders" — an
   unbounded list of unrelated POs. So a parse miss becomes a 25-of-17,447 dump rather than
   a not-found or a refusal.

**Expected:** (a) parser reliably extracts the PO identifier + the lifecycle operation for
these phrasings (route to `get_purchase_order_lifecycle_status` like the working variants);
(b) INDEPENDENTLY, a `PurchaseOrder` intent with no filter and no explicit "list" request
must NOT fall through to list-all — it should refuse ("name a PO number or a filter") or
report not-found. Fault (b) is the safety net: even a perfect parser will miss sometimes,
and the miss must fail safe, not dump the table.

**Verification:** read from run output — three prompts, each showing bare intent
(out=103/113/…), `search_purchase_orders {}`, "Showing 25 of 17,447". 162034 shown correct
under the working phrasing at line 80. Log-evidenced; the parser miss is reproducible from
the Intent blocks. **Owed:** re-run these three phrasings to gauge how often the parser
drops the ID (non-determinism → may not repeat every time).

**Root cause (candidate):** (1) parser prompt under-specifies extraction for "Is PO N
complete?" / "Is anything blocking PO N?" — the lifecycle-op cue is weaker than the explicit
"received/invoiced/paid" template; instruction-placement may be involved (cf. the known
Gemini structured-output sensitivity to instruction placement). (2) planner treats an
op-less, filter-less PurchaseOrder intent as "list all" instead of "insufficient to act".

**Fix:** (a) strengthen the parser's lifecycle-intent extraction for these phrasings (a
labeled section / examples for "complete?", "blocking?", "outstanding?" mapping to the
lifecycle op); (b) add a planner guard: a PurchaseOrder intent with no filter AND no explicit
list request raises a structured refusal (missing_identifier / needs a PO number or filter)
rather than planning an unbounded search. Guard (b) is the higher priority — it fails safe
regardless of parser behaviour.

**Status:** 🔴 open (2026-08-14). Highest-impact finding of this run: a real PO lifecycle
question silently returns a wall of unrelated POs with no error. Curl not needed (pod data is
fine; the fault is parser + planner). Re-run owed to characterise the parser non-determinism.


---

## Group N4 — Refusal correctness & format (Theme B)

Refusal *structure* is uniform and correct run-wide (Reason/Solution/Example/`(refusal:
code — detail)`). Two content defects:

- **#29** (🟡) refusal *detail-text* is non-deterministic — the same prompt refuses with
  different wording across sets, because the parser LLM words the detail instead of a
  fixed capability lookup. Breaks reproducibility/testability of refusals.
- **AI-5 over-application** (folded into **#6**): `unsupported_filter` refusals for
  untracked attributes (ratings, payment terms) still emit "Narrow by country, status or
  name" — a narrowing that can't help. Re-opens the AI-5 half #6 had declared correct.

### 29 🟡 open — Refusal detail-text is non-deterministic (parser-worded, varies across sets) — (was: new, 2026-08-14)

**Set:** 05_refusals vs 00_dipstick — same prompt "show me contract renewals due next
quarter".

The `(refusal: <code> — <detail>)` DETAIL string differs between runs of the identical
prompt: "The system does not support 'Contract' as an entity." (05_refusals) vs "The
'Contract' entity is not supported." (00_dipstick). Same `unknown_entity` code, same
input, different words. The detail is being generated by the parser LLM rather than
pulled from a fixed, per-code capability string, so refusal text is not reproducible.

**Expected:** refusal detail-text is deterministic — a fixed string per (code, entity/
attribute), owned by capability.py, so the same refusal always renders identically.
This is a determinism requirement, same spirit as "tool selection is a KG lookup, never
an LLM judgement": the refusal *reason* may be classified by the parser, but the
*wording* should be a lookup.

**Verification:** read from run output — two different detail strings for the same prompt
across two sets in the SAME overnight. Log-evidenced.

**Root cause (candidate):** the detail portion of the refusal is taken from the parser's
free-text output instead of a capability_message lookup keyed on the refusal code +
offending entity/attribute.

**Fix:** source the detail string from a fixed table in nl_parser/capability.py keyed on
(code, entity/attribute); the parser supplies only the code + the offending token. Batch
with the #6 Solution-selection fix (both live in the refusal render path).

**Status:** 🟡 open (2026-08-14). Determinism defect in the refusal render path; no data
impact but breaks reproducibility and testability of refusals.


> **Also in this group (existing entries):** #6 (the AI-5 `unsupported_filter` half is
> **re-opened** per 2026-08-14 evidence — see its folded note) and #9 (supplier-by-number
> consistency; the address-list path resolves 1252 while the projection path refuses it —
> folded into #9).

---

## Group N5 — Wording / cosmetic (Theme E)

- **#26** (🟡) truncation note says "examined for filtering" when no client filter ran
  (server-filtered path). Correct wording appears elsewhere (block 9, set 07) when a real
  client filter runs — so it's a branch-on-filter fix.
- **empty-result double-negation** (folded into **#5**): "No suppliers found matching the
  criteria." + "No suppliers found." — the local empty-template emits two redundant
  sentences. #5's synthesis half is now **verified fixed** (empty results are local, no
  synth); only this wording remains.

### 26 🟡 open — Truncation note says "examined for filtering" when no client filter ran — (was: new, 2026-08-14)

**Set:** 00_dipstick, "Get list of active suppliers" (any server-filtered, capped list).

Server-side `status=ACTIVE`, `client_filters: (none)`, yet the note prints
"337 total in source; 25 examined for filtering." No client-side filter ran, so
"examined for filtering" mis-describes the operation. Count is correct; wording
is wrong.

**Expected:** wording reflects the actual operation — "337 total in source; showing
25" for a display/page cap with no client filter; reserve "examined for filtering"
for genuine client-side filtering over a capped fetch (the #18 case).

**Verification:** read from run output (Intent `client_filters: (none)`; note still
says "examined for filtering"). Log-evidenced, no pod curl.

**Root cause (candidate):** truncation-note builder emits one "examined for
filtering" string for any capped fetch, not distinguishing server- from
client-filtered paths.

**Fix:** branch the note wording on whether a client filter ran. Cosmetic, low blast
radius; batch with Theme E labelling (#2).

**Status:** open — cosmetic (2026-08-14). Minor wording; no data impact.

---


---

## Group N6 — Performance / unbounded fetch (Theme E-adjacent)

- **#30** (🟡) "top N suppliers" compare fetches the entire PO universe (17,447 rows) before
  narrowing → pod upstream timeout (the run's only errored prompt). The named/single compare
  is bounded and fine. Fix: select top-N suppliers first (cheap ranking), then fetch their POs.

### 30 🟡 open — "Top N suppliers" compare fetches the entire PO universe (unbounded) → pod timeout — (was: new, 2026-08-14)

**Set:** 06_slow, prompt "Compare ordered vs invoiced for our top 3 suppliers"
(errored: execute upstream timeout, 145.7s).

The `supplier_invoiced_vs_ordered` compare with a top_n selector but no named supplier
issues an unfiltered PO fetch — paged all 17,447 POs, then 2,000, then 3,256+ — before
narrowing to the top 3 client-side. On the shared demo pod this exceeds the upstream
timeout. The single-supplier / named variant is bounded and completes in ~26s (set 02,
Lee Supplies).

**Expected:** bound the fetch. Determine the top-N suppliers first (by spend/PO value,
as the spend-ranking path already does over 41 suppliers cheaply), THEN fetch POs only
for those N. Never page the whole PO table to answer a top-3 question.

**Verification:** read from run output — 35-page full-PO paging visible, then additional
2,000 + 3,256 paging, then "ERROR: execute: Upstream request timed out". The single/named
compare bound is evidenced in set 02 (26.2s). **NOT re-run** — a manual re-run of just
this prompt is owed to confirm it's purely load (it may still time out until bounded).

**Root cause (candidate):** the top-N compare planner fetches POs before selecting the
top-N suppliers, so the supplier filter that bounds the named-variant is absent.

**Fix:** select top-N suppliers first (cheap ranking), then fetch POs filtered to those
supplier IDs. Mirrors the spend-ranking path's select-then-detail order.

**Status:** 🟡 open (2026-08-14). Performance/scale defect — correctness of the compare
is fine when it completes; the unbounded fetch makes the top-N variant unusable on this
pod. Manual re-run owed.


---


# OPEN ISSUES

## 1 🔴 open — LLM still used for synthesis across the run (no-LLM-synth goal) — (was: new + AI-3)

**Set:** run-wide. **Evidence:** 56 of 254 prompts invoked `stage=synthesize`.

Per the stricter acceptance rule adopted this pass — **no LLM synthesis anywhere,
all synthesis deterministic and local** — every `stage=synthesize` call is a
finding. Per-set counts: 00(1) 01(7) 02(2) 03(1) 04(1) 05(0) 06(1) 07(4) 08(25)
10(5) 11(8) qa(1). Four shapes:

- **Invoice lists (~17)** — "invoices for X [with columns]". Largest, most tokens (out 3300–5951). Status doc records this path as not-yet-built (OUT-04).
- **Address lists (3)** — "addresses for supplier N" (out 3116). This is old AI-3.
- **Multi-bucket joins (4)** — supplier+contacts, suppliers-with-open-POs, PO+buyer.
- **PO lifecycle narration (25)** — facts computed in code, LLM only narrates. Lowest risk, convert last.

The named target list (all 56 prompts, grouped by shape, with token counts)
is retained separately as this issue's appendix.

**Expected:** all synthesis via local builders (the pattern that closed #21 —
`build_* + *_buckets + no-LLM branch`), zero `stage=synthesize` on any prompt.

**Verification:** `grep -c 'stage=synthesize' overnight_20260812_bundle.txt` = 56;
per-set breakdown reproducible. Log-evidenced, no pod curl.

**Root cause:** synthesizer falls through to the LLM for any shape without a
local builder. Builders exist for counts, filtered supplier lists, PO-with-
children, AR account+transactions; absent for invoice lists, address lists,
cross-bucket joins, and empty/not-found (see #5).

**Fix:** convert per shape, one branch/PR each, following the #21 template.
Order (cheapest-risk first): address lists → invoice lists → single cases →
joins → lifecycle. Each verified by re-running its set: zero synth calls,
unchanged answers.


**Measurement (2026-08-14, `overnight_20260814`, sequential, all 12 sets):** fresh
`grep -rh "stage=synthesize" | wc -l` = **5** (was 56). Per-set: 00(1) 01(1) 10(2) 11(1);
every other set **0** — including **03_ar = 0** (AR receivables/receipts/customer-accounts/
credit-memos are all local; the "AR most likely hides synth" concern did NOT materialise).
The 5 are only **two shapes**, each a repeated prompt across sets:
- **Shape A — "Addresses for supplier N"** (`target_entity=Address`), 3 calls @ in=4452
  out=3116 (00,01,10). NOT the already-local address path (that fires for
  `target=Supplier` with nested addresses); Address-as-target has no local builder → falls
  through. Convert with a `build_address_records` + dispatch branch (the #3/#21 template).
- **Shape B — "Show PO N and its buyer / with … agent"** (`target=PurchaseOrder` + include
  Buyer [+ fields]), 2 calls @ in=1393 out=541 (10,11). The output is already correct
  ("Show PO 2144 and its buyer" renders May Gee) — it just needs a local join+narration
  builder. NB the `+ fields` phrasing ("order number and agent") ALSO trips the projection
  bug #34; converting the synth and fixing #34 are separate.

Caveat: `06_slow` exited 1 on ONE pod-timeout prompt (#30, "compare top 3 suppliers" —
execute-stage upstream timeout, never reached synthesize); 14/15 ran, so **5 is trustworthy,
not a floor**.

**Status (updated 2026-08-14):** open — IN PROGRESS, near done. Count 56 → 5 measured. Two
narrow shapes remain (Shape A address-target list; Shape B single-PO+buyer). Absorbs old
AI-3. Umbrella goal (0 synth on a fresh overnight) not yet met — two builders away.

---

## 2 🟢 not-reproducible — Supplier count contradiction within one run (301 vs 299) — (was: new)

**Set:** 00_dipstick (and reinforced in 01_supplier, 04_columns).

"Count of suppliers" → **301**; "how many active suppliers" → **299**;
"Get list of active suppliers" → "Showing 25 of 299". Two totals for the
supplier population, seconds apart. Internal evidence across sets is consistent
with **301 = all suppliers, 299 = active** (a real 2-supplier gap), so the
likely defect is **scope labelling**, not a wrong number — the all-suppliers
answer doesn't say "total" and the active answer's wording lets 299 read as the
whole population.

**Expected:** either the totals match, or each answer names its scope
explicitly ("301 suppliers total" vs "299 active suppliers").

**Verification — pending curl:**
```
curl -s --compressed -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?onlyData=true&limit=1&totalResults=true" \
  | python -c "import sys,json;print('all =', json.load(sys.stdin)['totalResults'])"
curl -s --compressed -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?onlyData=true&limit=1&totalResults=true&q=Status='ACTIVE'" \
  | python -c "import sys,json;print('active =', json.load(sys.stdin)['totalResults'])"
```
(v1.7 census recorded 429 — population appears to have changed on the pod;
confirm the current figures rather than assuming any of 429/301/299.)

**Curl result (2026-08-13):** all = **333**, ACTIVE = **331**, INACTIVE = **2**
(333 total in one page; `Status` counted client-side over all 333 →
`{'ACTIVE': 331, 'INACTIVE': 2}`). NOTE the second curl above (`q=Status='ACTIVE'`)
does NOT work on this pod — `Status` is not server-filterable (returns 0). Method
used instead: fetch all with `fields=SupplierNumber,Status` and count client-side
(Spire's own definition); the 2 inactive also surface via `q=InactiveDate IS NOT
NULL` (which does work). The 2 INACTIVE and the 2 with InactiveDate are the same
rows — no future-dated-active noise. **Confirmed: numbers are consistent; this is
a labelling defect, not a wrong count.** The run's 301/299 is stale (population is
now 333/331).

**Root cause (candidate):** count path and list path derive the total from
different sources and/or apply the status filter differently, with wording that
hides the scope.

**Fix:** after the curl — if scopes differ, label both; if identical, unify the
total source. Confirmed path: label scopes explicitly ("333 suppliers total" vs
"331 active suppliers") — no number changes.

**Repro (2026-08-13) — contradiction NOT reproducible on current code.** "List all
suppliers" now says "Showing 25 of 338 suppliers" and "338 total in source" — the
count and list totals AGREE (the 301-vs-299 contradiction is gone). "List active
suppliers" says "Showing 25 of 336 suppliers. All 25 have Status ACTIVE" — and
336 is the correct active total (curl-confirmed 338 total − 2 inactive = 336
active). The two scopes are distinguishable and both totals are correct. Reading
search_suppliers confirmed why: branch 3 returns total_available=len(filtered),
the true filtered count.

**Status:** not-reproducible (2026-08-13). Curl-confirmed the numbers are correct
(338/336/2) and the intra-run contradiction is gone; active and all queries carry
distinct, correct totals. Population moved (301→338) since the run. Watch-item: a
re-appearing intra-run mismatch is the repro. Phase 5 / Theme E.

---

## 3 🟢 fixed — Plain invoice lists now built locally, not LLM-narrated — (was: new)

**Set:** 01_supplier (3 instances), confirmed again in 04_columns and 07_alacarte.

The invoice-list LLM synth adds specific, checkable claims to a correct table
that are unreliable and sometimes wrong:
- "another for -163.16 USD" — pairs a −163.16 credit (invoice `50430-61`) with a
  +163.16 invoice (`16027inv`) as if a highlighted example; misleading. Recurs
  on the supplier-1252 / Lee Supplies set in **three** sets.
- "returned 6 invoices … partial list … total unknown" — post-filter count and
  truncation disclosure contradict each other.
- "20 invoices … Eight at 0.00 … remaining twelve range 536.55–1204.50" —
  LLM-computed count breakdown asserted in prose, not derived from the rows.

Not every invoice synth drifts (three EIP synths in 07/10 are clean), which is
the point: the model latches onto salient outliers unpredictably, so no instance
can be trusted.

**Expected:** narration states only what is deterministically computed from the
displayed rows — fixed factual header + table, no cherry-picked highlights, no
min/max over a truncated window, no LLM-computed breakdowns.

**Verification:** read from the run output; discrepancies are internal to each
answer (prose vs its own rows). No pod curl.

**Root cause:** invoice lists are LLM-synthesized (see #1); free-form narration
is not constrained to the rows.

**Fix (applied 2026-08-13):** added `build_invoice_records` + `plain_invoice_bucket`
in synthesizer/p2p.py and a synthesizer branch before the LLM fallthrough. A
single invoice bucket is now built locally; the summary comes from
`local_list_summary` (fixed count line + honest truncation), NOT LLM prose — so no
cherry-picked highlights, no min/max over a truncated window, no LLM-computed
breakdowns. Multi-bucket invoice shapes (lines/tax/DFF) return None from the
detector and are unaffected.

**Verified live (2026-08-13):** "invoices for supplier US Gas and Electric" — no
`stage=synthesize` (was out=3825, ~10k tokens; now parse-only 9.4k), 25-invoice
table intact, summary "Showing 25 of 183 invoices" + honest truncation. Updated
the invoice schema-selection test (single-bucket list is now local → asserts no
LLM call). Full suite green (863).

**Status:** fixed (2026-08-13, Theme A). The invoice-list shape of #1 is now local.

---

## 4 🟢 fixed — PO reference resolves as POHeaderId in one path, OrderNumber in another (false "not found") — (was: new)

**Set:** 02_purchase_order.

`Show PO 2144 and its lines` treats **2144 as POHeaderId** → resolves
(OrderNumber 162352, EIP Inc). `How much of PO 2144 was received?` treats
**2144 as OrderNumber** → "no purchase order with OrderNumber '2144' found." PO
2144 exists; the receive question returns a false negative purely from id-type
mismatch (the lifecycle tool keys on `po_number`/OrderNumber; the by-id tool on
`po_header_id`). Related to the deferred piece of old #17 (POHeaderId→OrderNumber
resolution).

**Expected:** a PO reference resolves consistently; on an OrderNumber miss,
retry as POHeaderId (or resolve to a canonical id once at parse/plan time).

**Verification — pending curl:**
```
curl -s --compressed -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/purchaseOrders/2144?onlyData=true&fields=POHeaderId,OrderNumber,Supplier" | python -m json.tool
curl -s --compressed -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/purchaseOrders?q=OrderNumber='2144'&onlyData=true&totalResults=true&limit=1" | python -c "import sys,json;print('OrderNumber=2144 total =', json.load(sys.stdin)['totalResults'])"
```

**Curl result (2026-08-13):** POHeaderId **2144 exists** → OrderNumber **162352**,
Supplier **EIP Inc** (matches the resolving path). `q=OrderNumber='2144'` →
**totalResults = 0**. So 2144 is a valid POHeaderId but NOT a valid OrderNumber;
the lifecycle tool (keyed on OrderNumber) returns a false "not found." No
ambiguity — nothing else owns OrderNumber 2144 — so a cross-try fallback is safe.

**Fix (applied 2026-08-13):** added a local `_try_header_id_lookup` in
po_lifecycle.py; on an OrderNumber miss it cross-tries the number as a POHeaderId,
and if that resolves, adopts the real OrderNumber (schedules/invoices/payments all
key on it) and discloses the resolution in a note. A genuinely unknown number
still returns found=False (the 999999 test still passes). Requires MCP restart
(mcp_server/ file).

**Verified live (2026-08-13):** "How much of PO 2144 was received?" now resolves —
found=True, order_number 162352 (EIP Inc), full lifecycle, with the note "'2144'
is a POHeaderId, not an order number; resolved to OrderNumber '162352'". Lifecycle
tests green (92); full suite green (863).

**Status:** fixed (2026-08-13, Theme D). Real reproducible bug, verified end-to-end.

---

## 5 🟡 open (split) — Empty/not-found: synthesis half FIXED (now local); double-negation wording open — (was: new)

**Set:** 02_purchase_order, 03_ar, 08_lifecycle.

Not-found and zero-record answers go through `stage=synthesize`:
`How much of PO 2144 was received?` (not found), `Has PO 999999999 … paid?` and
`Has PO DOES-NOT-EXIST been paid?` (08), `Show receipts … at Santa Clara`
(03_ar, 0 records). The executor already returns a structured `found: False` /
empty list; narrating a fixed sentence from it needs no model. The AR empty case
also double-negates ("No standard receipts were found… No receipts found.").

**Expected:** a deterministic local template keyed on `found: False` and empty
lists, no LLM call, fixed wording.

**Verification:** `stage=synthesize` present on these despite structured empty
records. Log-evidenced.

**Root cause:** no early local branch for empty/not-found; falls through to LLM.

**Fix:** add the branch before any LLM path. Cheap, independent of the invoice-
list conversion. A clean subset of #1 worth doing first.

**Status:** open — UNVERIFIED. We did not confirm this reproduces on current code:
attempts to find an empty-result prompt hit refusals (→ #11) or non-empty results
instead. It may already be handled locally, or may be live. Deferred to the
**follow-up branch** with #1; first step there is to find a genuinely-empty result
and check whether it still calls `stage=synthesize`.

**Verified update (2026-08-14):** **Repro (2026-08-14, overnight_20260814/01_supplier) — SPLIT RESULT.** "Suppliers
created between Jan and Mar 2025" returns 0 records and is now built LOCALLY —
**no `stage=synthesize`** (parse-only), confirming the synthesis half is fixed
(`_all_buckets_empty` short-circuit). HOWEVER the emitted text double-negates:
"No suppliers found matching the criteria." followed by "No suppliers found." — the
exact doubling this issue predicted, now confirmed live in the LOCAL template (not
the LLM). 03_ar was clean this run (no empty-result synth there either).

**Status:** synthesis half **fixed** (empty results built locally, 2026-08-14);
double-negation wording **open (cosmetic)** — the local empty-template emits two
redundant sentences; collapse to one. Downgraded from 🟡 to a cosmetic wording fix.
Batch with Theme E / #2 / #26 wording pass.

---

## 6 🟠 fixed / part re-opened — Refusal Solution: unsupported_operation fixed; AI-5 unsupported_filter over-application re-opened (2026-08-14) — (was: new + AI-5)

**Set:** 05_refusals (2), 03_ar (1), 08_lifecycle (2) — the `unsupported_operation`
class, run-wide (5 instances); plus the old AI-5 "narrow by country/status/name"
misdirection on non-filter refusals.

Two related template defects:
1. **Dismissive Solution.** `unsupported_operation` refusals (quality-score
   ranking, "who should we stop buying from", lag-between-dates, "have all POs
   been paid", "compare two POs' lifecycle") all emit
   *"Ask me for the records themselves and do the rest your side"* — no
   capability, offloads work onto the user. Contrast: the Site-gate refusal
   (also `unsupported_operation`) has a *good* Solution, so the defect is
   specific message branches, not the whole code.
2. **Misdirection (old AI-5, PARTIAL).** The generic "narrow by country/status/
   name" Solution is over-applied to refusals that aren't narrowing problems
   (payment terms, non-existent ratings, "everything about X").

**Expected:** every Solution names a real capability or a concrete alternative
query, in the reference-template voice.

**Verification:** read from the run; all share code + Solution string. Inspect
the `unsupported_operation` / `unsupported_filter` branches in
`nl_parser/capability.py`. No pod curl.

**Root cause:** per-class Solution text authored generically for these two
refusal flavours, diverging from the per-case capability Solutions others use.

**Fix:** rewrite the `unsupported_operation` Solution (optionally per sub-case:
computed-metric vs ranking vs judgment) and finish the AI-5 `unsupported_filter`
correction. Re-run 05_refusals + the 03_ar/08_lifecycle instances; confirm
in-template. Guard the `10_refusal_examples` promises don't regress.

**Related capability gap (not a separate issue):** "Compare the lifecycle of PO
X and Y" is refused as unsupported, but both POs' lifecycle records are
individually retrievable — a side-by-side compare could be built; at minimum the
Solution should point to asking per-PO.

**Fix (applied 2026-08-13):** rewrote the `UNSUPPORTED_OPERATION` fallback Solution
in capability.py from "Ask me for the records themselves and do the rest your
side" to "Ask for the underlying records and I'll return them for you to total or
average" — same honest meaning (Spire can't compute these; it can return the
records), constructive tone, on-template. All ~5 instances inherit this one shared
fallback, so one change fixes them.

**Verified live (2026-08-13):** "What is the average invoice amount per supplier?"
now shows the new constructive Solution + a correct entity-matched Example. Full
suite green (863).

**Status:** fixed (2026-08-13, Theme B). NOTE the AI-5 `unsupported_filter`
"narrow by…" half was assessed separately and reads correctly on current code
(the unsupported_filter refusals now carry sensible per-entity guidance via
_FILTER_GUIDANCE — see #11); the dismissive-Solution defect this issue centred on
is fixed. The "compare two POs' lifecycle" capability gap remains a separate
question for the owner (not a bug).

**Re-opened in part (2026-08-14):** **Repro (2026-08-14, overnight_20260814/05_refusals) — the `unsupported_operation`
Solution fix HOLDS, but AI-5 over-application persists on `unsupported_filter`.**
"quality score" / "stop buying from" correctly give "Ask for the underlying records
and I'll return them…". However "which suppliers have the best rating" and "suppliers
with net 30 payment terms" (both `unsupported_filter`) still emit the generic "Narrow
by country, status or name instead" — a narrowing that cannot surface an untracked
attribute. The Solution should name the missing attribute. Over-application of the
generic filter-Solution is live.

**Status:** `unsupported_operation` half fixed & holding; `unsupported_filter` generic-
Solution over-application still open.

---

## 7 🟠 verified — "Country" reported unavailable and silently replaced with a full Address column — (was: new)

**Set:** 04_columns.

"Supplier number and **country**" and "…name, number, status and **country**"
both (a) declare "'Country' isn't available", then (b) show an unrequested full
**Address** column. Country data *is* present — every record carries
`TaxpayerCountryCode` ('US', …) and the country is inside the address string. So
"unavailable" is inaccurate, and an Address column the user never asked for is
injected (parser expands "country" → `include: ['Address']`). Contrast: "credit
rating" (genuinely absent) drops cleanly with no injection — the correct
behaviour.

**Expected:** map "country" → `TaxpayerCountryCode` and show it; or, if country
is truly not projectable, show only the remaining valid requested columns — never
an unrequested Address.

**Verification — pending curl:**
```
curl -s --compressed -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?onlyData=true&limit=5&fields=SupplierNumber,Supplier,TaxpayerCountryCode&q=Status='ACTIVE'" | python -m json.tool
```
(The raw run records already show `TaxpayerCountryCode: 'US'`, so the field is
present in-pipeline regardless.)

**Curl result (2026-08-13):** `TaxpayerCountryCode` is **real and populated** —
across 5 rows: 1252 Lee Supplies 'US', 1254 JGA 'US', 1253 Staffing Services 'US',
1255 Dell Inc. 'US', **1256 US Gas and Electric `None`**. So the field is present
and carries country, but it is **nullable** — the builder must render null cleanly
(not an em-dash, not "unavailable"). Confirms "'Country' isn't available" is false.
(The curl above was run WITHOUT `q=Status='ACTIVE'` — that clause returns 0 on this
pod; `Status` is not server-filterable.)

**Root cause:** no "country" → `TaxpayerCountryCode` synonym, so country is
judged unavailable; separately, "country" → `include: ['Address']` injects an
Address column that survives even after Country is declared unavailable. The two
paths aren't reconciled.

**Fix:** add the field-synonym (deterministic expander, the COL-02 mechanism);
ensure an unavailable requested column never triggers a substitute include. Part
of Theme C. Re-run both prompts. Handle the null case (1256) explicitly.

**Status:** verified (curled 2026-08-13 — field real, populated, nullable). Phase 1 / Theme C.

**Re-confirmed live (2026-08-14, `overnight_20260814`) — this is the same defect logged separately as #28; merged here.** country → Address substitution reproduced on 04_columns ("Supplier number and country", "…name, number, status and country"). Raw supplier records this run show `TaxpayerCountryCode: 'US'` on the body, re-confirming the field is present and country is NOT unavailable. **New sibling:** `state` behaves identically (11_column_vocabulary, "supplier name and state" → "'state' isn't available"); `state`/`city` live in the nested Address, so the same synonym/derivation gap covers them. This is one face of the Group-N1 projection cluster (with #34 wrong-step and #31 null-vs-unresolved). #28 retired into this entry — do not double-count.

---

## 8 🟢 fixed — Suppliers-with-open-POs now built locally; count exact — (was: new)

**Set:** 06_slow, prompt "suppliers with open purchase orders" (LLM synth out=5190).

Prose: "14 suppliers have open purchase orders, totaling 54." The table below
lists **15** suppliers with Open POs > 0, summing to **62**. Both summary numbers
wrong; the table is correct. The sharpest evidence for Theme A: the model cannot
reliably count the rows it is rendering. (The same join at out=7986 recurs in
08_lifecycle — same shape/bug.)

**Expected:** summary equals the table — "15 suppliers … totaling 62" — computed
by a local builder from the rows.

**Verification:** counted directly from the table in the run output; discrepancy
is internal (prose vs its own rows). No pod curl. (Run Summary reports 66 raw
`open_pos` records pre-dedupe, consistent with a total well above 54.)

**Root cause:** join is LLM-synthesized; the summary is free text, not computed.

**Fix (applied 2026-08-13):** added `_supplier_with_open_pos` (detector) +
`build_suppliers_with_open_pos` (builder) in synthesizer/p2p.py and a synthesizer
branch before the LLM fallthrough. The builder groups the open-PO bucket by
SupplierId, sets open_po_count=len(group) and distinct buyers per supplier; the
summary total is sum(open_po_count), so the count is exact by construction. The
denominator is honest (across the examined suppliers, not pod-wide), mirroring
_filtered_supplier_list.

**Verified live (2026-08-13):** "suppliers with open purchase orders" — no
`stage=synthesize` (was out=7488, ~30k tokens; now parse-only 9.4k), total now
**43** (per-supplier counts sum to 43 exactly), per-supplier Open POs + Buyers
render correctly. The LLM's old 42 was an undercount (Consolidated Supplies was 11,
correctly 12). Synthesizer tests green (62); full suite green (863).

**Status:** fixed (2026-08-13, Theme A). The join shape of #1; count exact.

---

## 9 🟡 reclassified (feature) — No supplier-by-number lookup; refusal is correct, capability is missing — (was: new)

**Set:** 07_alacarte.

`Show supplier 1252 with supplier name, number, and address` refuses with
*"the Supplier entity cannot be filtered by a numeric ID alone."* False —
supplier 1252 is resolved by numeric ID in many prompts the same run (addresses,
invoices, invoice-numbers for 1252). The refusal fires only for the
single-supplier-with-columns shape; the user is told an untrue limitation and
denied a valid request.

**Expected:** resolve 1252 (Lee Supplies) and show the requested columns — the
same resolution the invoice-for-1252 path uses — not a refusal.

**Verification:** the run both resolves 1252 and declares it un-resolvable —
conclusive internally. (Optional confirm SupplierNumber 1252 exists via curl.)

**Curl result (2026-08-13):** SupplierNumber **1252 = Lee Supplies**, returned by
the pod (surfaced in the #7 curl). So 1252 is a real supplier — but see below: it
does NOT follow that Supplier can be *rooted* by a number.

**Repro (2026-08-13) — refusal is CORRECT, not false.** `Show supplier 1252 with
supplier name, number, and address` returns a well-formed structured refusal:
  (refusal: unsupported_filter — There is no filter to query a supplier by its
  number. Suppliers can only be queried by name fragment.)
KG confirms: the only id-type filter is `by_id`, and it is PurchaseOrder/AR-invoice
ONLY (Supplier's filter set excludes by_id; planner code ~line 5414). So there is
genuinely no supplier-by-number path to "route to" — the original premise
(falsely refused, re-route to a by-id lookup) is **wrong**.

The premise confusion: 1252 DOES resolve elsewhere, but only as a *filter value*
on Invoice/Address ("invoices for supplier 1252"), never as a Supplier ROOT.
"Appears as a filter value" ≠ "Supplier can be rooted by number." The original
finding conflated the two.

**Reclassified:** this is a FEATURE request (add a supplier-by-number lookup), not
a bug. The refusal is honest and correctly formatted. There IS a real
user-visible inconsistency (Invoice accepts 1252 as a supplier ref, Supplier does
not) — that is the case FOR building it — but building it needs: a KG by-number
filter + fetcher on Supplier, a planner path, a parser-prompt allowance, count
bumps (print_kg + test_kg_metadata), and — if a new MCP tool — an MCP restart. A
scope decision for the requirements owner / Venu. **Batch with #7** (tax-vs-address
country), also a scope call.

Smaller alternative if the feature is declined: enrich the refusal to name the
resolved supplier ("this looks like Lee Supplies — try that name").

**Status:** reclassified (feature) — pending owner decision; batched with #7. The
original routing premise was incorrect: no supplier-by-number lookup exists to
route to, and the refusal is correct.

**Consistency bug surfaced (2026-08-14):** **Repro (2026-08-14, overnight_20260814) — supplier-by-number is INCONSISTENT across
paths.** "Show supplier 1252 with supplier name, number, and address" (07_alacarte) is
REFUSED `unsupported_filter — Supplier queries cannot be rooted by a supplier number`,
while "Addresses for supplier 1252" (shape A, sets 00/01/10) RESOLVES 1252 and proceeds
to synthesis. Same supplier number, different verdict. Whatever the owner decides for #9,
the two paths must agree — either both resolve a bare supplier number or both refuse it.

**Status:** owner decision (unchanged) PLUS a consistency bug surfaced 2026-08-14 — the
address-list path resolves supplier-by-number but the projected-columns path refuses it.

---

## 10 🟢 not-reproducible — Parser runs to token ceiling on "What is outstanding on PO 701337?" (degenerate parse, false refusal) — (was: new)

**Set:** 08_lifecycle.

Parse emitted **7,984** output tokens (siblings: ~200–860), hit `MAX_TOKENS`,
and refused as `unparseable`. But 701337's lifecycle record has
`remaining_to_receive` / `remaining_to_invoice` / `remaining_to_pay` (837.00
remaining) — the question is answerable. This is the known runaway-generation
failure mode (documented before: instruction placement causing Gemini
structured-output to generate to its ceiling), triggered by this phrasing;
misclassified as out-of-scope.

**Expected:** return the outstanding amounts for 701337, like the other
single-PO lifecycle prompts; the parser must not run to its ceiling.

**Verification:** `out=7984` / `finish_reason=MAX_TOKENS` in the parse line;
every other 701337 prompt parses in a few hundred tokens. Reproduce with
`--show-parser`. No pod curl.

**Root cause (candidate):** a parser-instruction/schema interaction causes
unbounded generation for "what is outstanding on"; compare against a working
sibling ("Why is PO 701337 still open?").

**Fix:** reproduce, locate the trigger (likely a standalone-labeled-section fix
as in the prior incident) and/or add a "what is outstanding" → outstanding-
amounts mapping; add a parse-time cap that degrades to a narrowing prompt rather
than a hard refusal. Re-run; 701337 outstanding amounts returned.

**Repro (2026-08-13) — did NOT reproduce; runaway is gone.** "What is outstanding
on PO 701337?" now parses at **out=366** and resolves to the correct lifecycle
answer (837.00 remaining to receive/invoice, awaiting receipt). Run 5× to check
for intermittency: **5/5 runs identical at out=366**, no MAX_TOKENS, no false
refusal. The degenerate generation the issue describes does not fire — likely
resolved by intervening parser-prompt restructuring (the instruction-placement fix
class).

**Status:** not-reproducible (2026-08-13, 5 clean runs). Stronger evidence than a
single pass — the parse is deterministic at out=366. NOT marked fixed: runaway
generation is probabilistic and no code change addressed it here; if it recurs on
a different phrasing that transcript is the repro.

---

## 11 🟢 fixed — Planner unsupported-filter refusal rendered as a dense string, not Reason/Solution/Example — (was: new; CORRECTED from not-reproducible)

**Set:** 08_lifecycle, prompt "Open POs for supplier JGA."

Refuses with a single dense line prefixed `REFUSED (planner guard): plan: Spire
can't filter PurchaseOrder by 'supplier', 'status'. …` — not the structured
format. The "readable planner-guard refusals" work converted four entity guards;
this PurchaseOrder-filter guard still emits the raw string (missed or regressed).

**Expected:** the same Reason / Solution / Example / `(refusal: code — detail)`
format every other refusal uses.

**Verification:** the `REFUSED (planner guard):` prefix is the pre-conversion
shape. Cross-check `planner.py` guards and `nl_parser/capability.py`. No pod curl.

**⚠️ CORRECTION (2026-08-13).** This issue was briefly marked `not-reproducible`
after two unsupported-filter prompts ("POs over 5000", "customer accounts with
account number 1234") both refused cleanly at `stage=parse` — the parser
self-declared them, so they never reached the planner validator, and it looked
like the dense path was shadowed/dormant. **That conclusion was wrong.** It was an
artefact of the specific prompts tried: the parser catches SOME unsupported
filters but not all. **"purchase orders for supplier Staples" reaches
`_validate_intent_filters` and reproduced the dense string exactly:**
`REFUSED (planner guard): plan: Spire can't filter PurchaseOrder by 'supplier'. …`.
Lesson recorded in the top caveat: "not-reproducible" means "not triggered in the
prompts tested", not "fixed".

**Root cause (confirmed):** `_validate_intent_filters` (plan_builders.py) raised a
bare `NotImplementedError` with a pre-built dense string; `plan_node`'s
`(ValueError, NotImplementedError)` branch dumps that flat as `plan: {exc}`,
bypassing `capability_message`. The parser shadows it for the filters it catches
first, but any filter that parses through to the planner (e.g. `supplier` on a
PurchaseOrder root) hits it.

**Fix (applied 2026-08-13):** converted `_validate_intent_filters` to raise
`RefusalError(Refusal(flavor=UNSUPPORTED_FILTER, offending_entity=target_entity,
offending_filters=[...]))` like the four sibling entity guards. `plan_node`'s
existing `RefusalError` branch routes it into `state["refusal"]`, so it renders
through `capability_message` (wording from `_FILTER_GUIDANCE`, which covers all 7
entities). Only `plan_node` caught the type; the aggregation-op
`NotImplementedError`s elsewhere are untouched. Removed the now-dead
`_ENTITY_EXAMPLE_PROMPT` import. Updated 8 planner tests to assert the structured
refusal (flavor/offending_entity/offending_filters); the user-facing wording
guarantee is covered by test_nl_parser_capability.py.

**Verified live (2026-08-13):** "purchase orders for supplier Staples" now renders
Reason ("I can look up purchase orders, but not by supplier.") / Solution / Example
+ `(refusal: unsupported_filter — PurchaseOrder cannot be filtered by 'supplier')`.
Planner/pipeline/aggregation tests green (136); full suite green (863).

**Status:** fixed (2026-08-13, Theme B). Was mislabeled not-reproducible; a prompt
not initially tried reproduced it as a live bug, now fixed structurally (the dense
emitter is gone, not merely shadowed).

**Separate note (not this issue):** whether "POs for supplier X" should *refuse at
all* — other supplier-scoped queries (invoices for supplier X) work via edge
traversal, so PO-by-supplier could route through the supplier→PO edge instead of
refusing. That is a capability/routing question for the owner (like #7/#9), not
part of the refusal-rendering fix.

---

## 12 🟢 fixed — "who details" now routes to WHO columns (fields), not a Contact join — (was: new)

**Set:** 11_column_vocabulary, prompt "List active suppliers with supplier name and who details."

Four compounding defects: (1) "who details" (WHO audit columns) misparsed as
`include: ['Contact']`, launching a 93-record contact fetch; (2) final table
`contact — columns: Supplier` renders a column of em-dashes (contacts have no
Supplier field); (3) prose "68 contacts" contradicts the 93-record set, and
"Lee, Ryan identified as an administrative contact" is fabricated (JobTitle null
throughout); (4) 21,032 tokens for a broken answer.

**Expected:** "who details" → [CreatedBy, CreationDate, LastUpdatedBy,
LastUpdateDate] on Supplier, rendered as columns — no Contact join, no em-dashes,
no LLM-authored count.

**Verification:** Intent shows `include: ['Contact']` + `fields: ['Supplier']`;
93 records + em-dash column; "68" vs 93 and null JobTitle all internal to the
answer. No pod curl.

**Root cause:** (a) no "who details" → WHO-columns synonym, so "who" → Contact
include; (b) projection emits a column absent from the rows (em-dash); (c)
LLM-synthesized, so the count and attribute are invented (#8 class).

**Fix:** add the "who"/"who details"/"who columns" → WHO-columns synonym (Theme
C, same expander as #7); guard the projection against columns absent from rows;
convert supplier-list-with-columns synthesis to local (Theme A). Re-run; four
columns render, no join, no em-dashes, no synth.

**Fix (applied 2026-08-13):** added an explicit parser-prompt rule steering "who
details" / "who columns" / "audit columns" / "audit fields" / "creator details" /
"created details" to `fields` (not a Contact include); the existing COL-02 synonym
then expands them to the four WHO columns. Only "who are the contacts for X" still
means a Contact include. File: `src/spire/nl_parser/parser.py` (prompt) — no MCP
restart (parser is not under mcp_server/).

**Verified live (2026-08-13):** "List active suppliers with supplier name and who
details." now parses to `fields=[Supplier, CreatedBy, CreationDate, LastUpdateDate,
LastUpdatedBy]`, **no include**, **no synth** — four columns render, no Contact
fetch, no em-dash, no fabricated count. 9637 tokens (was ~21032). Regression guard:
"Get supplier contacts for Lee Supplies." still routes to `include: ['Contact']`
and returns 18 contacts — the genuine Contact path is unchanged. Parser tests green
(127). Root cause was corrected: the synonym already existed and expanded to four
real Supplier fields; the bug was the prompt capturing "who" as a Contact include
before the fields-path expander could run.

**Status:** fixed (2026-08-13, Theme C). The em-dash (b) and fabricated-count (c)
sub-defects were downstream of the phantom Contact projection and are resolved by
the routing fix — no separate projection-guard needed for this case. The general
Theme A goal (convert supplier+contacts *join* synthesis to local) remains separate
and is tracked under #1/#8.

---

## 13 🟢 not-reproducible — Wholesale refusal on wholly-unknown columns; partial-column note inconsistent — (was: AI-9 / COL-03)

**Set:** originally 03_ar/04_columns; a standing G15 limitation.

Mixed valid+invalid column requests are sometimes refused wholesale (losing the
valid columns), e.g. "supplier name and credit rating". The COL-03 honest note
*works* for many unknown columns, but fails when a wholly-unknown column trips
the model's upstream unanswerable flag before an Intent is built. Note the newer
#7 (country) and #12 (who details) are the same family — a missing synonym makes
a real column look unknown.

**Expected:** partial fulfilment — project the valid columns, name the unknown
one and menu the available columns — never a wholesale refusal.

**Verification:** documented in the findings doc (G15); reproduced by the
specific phrasings. No pod curl.

**Repro attempt (2026-08-13) — did NOT reproduce.** Both cited phrasings ran
cleanly on current code (after the #12 parser fix), COL-03 handling them exactly
as Expected:
- "List suppliers with supplier name and credit rating." → Intent built (target
  Supplier, fields=['Supplier']); query ran; note: "credit rating isn't available
  on Supplier" + the eight real columns offered. Valid column preserved, no
  wholesale refusal, no synth (9670 tokens).
- "List suppliers with their credit rating." (unknown column ONLY, nothing valid
  to anchor) → Intent still built; ran; same honest note + "(25 matched; no
  requested column was available.)". No unanswerable flag.

The upstream-unanswerable-flag path this issue describes did not fire in either
run. COL-03 covers the cited cases.

**Root cause:** the model refuses on an unknown column before the Intent exists;
making the column real in the KG (a synonym or field row) stops the refusal
deterministically — the COL-01/COL-02 approach.

**Fix:** continue the COL-01/COL-02 direction — add field rows/synonyms so
intended columns resolve (closes the common cases via #7, #12); for genuinely
absent columns, ensure the note path is reached rather than the upstream refusal.
Part of Theme C. (Conditional — only if the failure resurfaces; see Status.)

**Status:** not-reproducible (2026-08-13). The intermittent wholesale-refusal path
could not be triggered on current code; COL-03 handles the cited phrasings. NOT
marked `fixed` — the failure is probabilistic (LLM generation), and two clean runs
can't prove an always-clean path. Watch-item: if a wholesale refusal on unknown
columns resurfaces in an overnight run, that transcript is the repro to fix
against. Old AI-9/COL-03.

---

## 14 🟢 not-reproducible — Supplier list returns a different 25-row sample between identical runs — (was: AI-13)

The supplier list returns a different 25-row sample across identical runs. Pod
curl (prior session) confirmed the pod is stable; the variance is Spire-side
(client filter/sample ordering). Related to the determinism-vs-representativeness
note (adding `orderBy` to a capped fetch changed which rows appear).

**Expected:** a stable, reproducible sample for identical input (or an explicit,
documented sampling rule).

**Verification:** prior pod curl confirmed stability; Spire-side root cause not
yet pinned.

**Root cause (candidate):** unordered/late-ordered capped fetch yields a
different page per run.

**Fix:** define a deterministic sample (stable order key on the bounded fetch),
mindful of the representativeness trade-off. Confirm identical output across
repeated runs.

**Repro (2026-08-13) — did NOT reproduce.** Ran "List all suppliers" twice
back-to-back and diffed the 25 returned rows: **identical** (same suppliers, same
order: 1252, 1254, 1256, 1253, 1255, …). The run-to-run sample variance the issue
describes did not manifest.

**Status:** not-reproducible (2026-08-13, two identical runs). NOT marked fixed:
two consecutive runs isn't proof of always-deterministic (the fetch has no explicit
orderBy; the pod could reorder under different load), and per the representativeness
trade-off noted below, forcing an order isn't obviously desirable. If a differing
sample appears in an overnight run, that is the repro. The candidate fix
(deterministic sample key) is retained below for that case.

---

# FIXED / CLOSED (retained for traceability)

## 15 ✅ fixed — Child rows rendered as counts, not rows — (was: AI-1) — commit 8ad9b39
PO lines/schedules/distributions and AR invoice lines now render as sub-tables. Contacts/tax lines were already correct.

## 16 ✅ fixed — Partial result stated as the total (wrong denominator) — (was: AI-4) — commit 8ad9b39
Deterministic honest-denominator branch ("Examined 25 of 432; of those 25, 2 match"), no LLM. Covered the pervasive edge-traversal-filter and credit-memo variants.

## 17 ✅ fixed — Specific question answered with a generic summary — (was: AI-6) — commit eb2fd72
Single-leg PO questions route to the lifecycle tool. Deferred piece (POHeaderId→OrderNumber) is now tracked as #4.

## 18 ✅ fixed — Self-contradiction "All 25 have Site X" then "No receipts found" — (was: AI-7) — commit 8ad9b39 + 2026-08-12
Field-name mismatch fixed; second facet (client-side site filter over a capped fetch) now discloses "unknown total in source; N examined". xfail marker removed.

## 19 ✅ fixed — "Supplier sites" returned addresses, not sites — (was: AI-10) — 2026-08-12
site/sites entity_synonyms + deterministic include correction; reaches the readable Site gate instead of returning addresses.

## 20 ✅ fixed — "Supplier sites for suppliers" crashed — (was: AI-11) — commit 37522b1
validate_intent refuses a Site include at parse time; no crash.

## 21 ✅ fixed — Schedules Received = 0.0 shown as fetched, contradicting prose — (was: AI-12) — 2026-08-12
PO-with-children synthesizes locally; Received is derived (Amount × ReceivedQuantity / Quantity). The template Theme A follows.

## 22 ✅ fixed — Completeness advisory (Tip block) — (was: REC-1) — commit 8ad9b39
Ruled Tip block; filters from kg_entity_filter; states why a full scan is slow.

## 23 ✅ fixed — Unbounded PO-list refusal → sample-and-disclose — (was: REC-2) — 2026-08-12
"list all purchase orders" returns a bounded ordered 25-row sample + honest total; records built locally.

## 24 ⚪ not-a-bug — `[debug] shape = None` — (was: AI-2 / QA-08)
A show_all artifact, not user-facing in normal runs.

## 25 ⚪ not-a-bug — Exposure ranking magnitudes are real pod data — (was: AI-8)
Curl-verified. Do not re-investigate.

---

# FIX PLAN (phased, keyed to the new numbers)

Sequenced by: shared root cause (fix once, close many), user-facing harm, and
cheapest-risk-first. Each phase ends green (`pytest -q`) with work committed
before the next, one branch/PR per logical change.

## Phase 0 — Curl the suspected items (no code)
Settle the four **suspected** issues before writing fixes, per "confirmed = curled":
- **#2** supplier all/active totals · **#4** PO 2144 id-type · **#7** TaxpayerCountryCode · **#9** SupplierNumber 1252.
- **#31** whether EIP invoices carry `PurchaseOrderNumber` on the pod (null-vs-unread). · **#27** whether credit memos aggregate server-side. · **#33** whether supplier classification is server-filterable (composite `q=` fails on this pod, so single-clause only).
One short curl session; promotes each to `verified` or reclassifies it.

## Phase 1 — Theme C: field-synonyms & projection safety (small, deterministic, high payoff)
Closes real column bugs and de-risks the model's unknown-column refusals.
- **#7** "country" → `TaxpayerCountryCode`; stop the Address injection.
- **#12** "who details" → WHO columns; guard projection against columns absent from rows (kills the em-dash).
- **#13** advance COL-01/COL-02 so intended columns resolve; ensure the note path (not the upstream refusal) is reached for genuinely-absent columns.
Mechanism is the existing COL-02 expander (KG lookup, not model judgement). One PR per synonym group + one for the projection guard.
- **#34** (🔴, no curl gate) bind projection per-column to the step-output that holds it (target-entity output for target columns; included-entity output for join columns) — this alone fixes the shape-B em-dash where the value exists.
- **#31** (🟡, curl owed) distinguish a genuinely-null field from an unresolved join field; disclose all-empty columns. Curl a few EIP invoices to confirm whether PurchaseOrderNumber is populated (null-vs-unread).
- **#7/#28** add "country" → `TaxpayerCountryCode` and "state"/"city" → nested-Address synonyms; render null cleanly; never inject an unrequested Address.
This projection cluster (#7, #12-guard, #31, #34) is the single highest-payoff fix of the 2026-08-14 set — one resolver change closes four.

## Phase 2 — Theme B: refusal correctness & format (small, user-visible)
- **#6** rewrite `unsupported_operation` Solutions (per sub-case) + finish the AI-5 `unsupported_filter` correction.
- **#11** route the PO-filter planner guard through `RefusalError` → `capability_message`; audit remaining guards.
- **#9** re-route single-supplier-by-id-with-columns to the by-id lookup; correct the false refusal text.
- **#29** source the refusal *detail-text* from a fixed capability table keyed on (code, entity/attribute) so the same refusal renders identically every run; the parser supplies only the code + offending token.
- **#6** the AI-5 `unsupported_filter` "narrow by…" half is **re-opened** — name the missing attribute instead of suggesting a narrowing that can't help.
Verify against `05_refusals` and `10_refusal_examples` (promised examples must still answer).

## Phase 3 — Theme D: parser robustness & PO reference
- **#10** fix the degenerate-parse trigger for "what is outstanding"; add a parse-time cap that degrades gracefully.
- **#4** cross-try POHeaderId/OrderNumber (or resolve once to canonical id).
- **#32** (🔴, highest-impact) — do BOTH, guard first: (b) add a planner guard so a filter-less PurchaseOrder intent with no explicit "list" request raises a structured refusal instead of `search_purchase_orders {}` (distinguish an explicit "list purchase orders" — valid sample-and-disclose — from a dropped-identifier query); then (a) strengthen parser extraction for "Is PO N complete?" / "…blocking?" / "…outstanding?" to route to the lifecycle tool. Guard (b) fails safe regardless of parser behaviour and is small.
Both need `--show-parser` reproduction first; MCP server restart if `mcp_server/` changes.

## Phase 4 — Theme A: eliminate LLM synthesis (the largest, staged)
The no-LLM-synth goal (#1), harms #3 and #8, and #12's synth half. Convert one
shape per branch/PR using the #21 template, cheapest-risk first:
1. **Empty / not-found (#5)** — smallest, independent, removes a whole class.
2. **Address lists** (old AI-3, folded into #1).
3. **Invoice lists (#3)** — largest payoff; kills the "-163.16" drift.
4. **Single cases** — created-between, everything-about-X, PO+buyer, etc.
5. **Joins (#8)** — suppliers-with-open-POs, supplier+contacts; derive counts from rows.
6. **Lifecycle narration** — last; facts already deterministic, lowest risk.
Each conversion re-runs its set: zero `stage=synthesize`, unchanged answers. When
all shapes are done, a full overnight re-run should show 0 synth calls.

**2026-08-14 status — only two shapes left (measured, 56 → 5):**
- **Shape A — address-target list** ("addresses for supplier N", `target=Address`, 3 calls):
  add `build_address_records` + a dispatch branch. Distinct from the already-local
  Supplier-with-addresses path.
- **Shape B — single PO + buyer** ("Show PO N and its buyer", 2 calls): output already
  correct; add a local join+narration builder. (The "with … agent" phrasing also hits
  projection bug #34 — fix separately in Phase 1.)
Both are small, single-shape conversions; after them, re-measure for 0.

## Phase 5 — Theme E: count/sample consistency
- **#2** label scopes (after Phase 0 curl).
- **#14** deterministic sample order on the bounded fetch (watch the representativeness trade-off).
- **#27** (🔴) credit-memo "total value": aggregate over ALL credit memos (as the exposure path aggregates over all 500), or refuse to print a total computed over a truncated sample. Curl whether `list_receivables_credit_memos` aggregates server-side.
- **#35** thread `top_n` into the credit-memo list path (works on the invoice path already).
- **#33** classification/attribute filter: server-side filter if supported, else full-page scan, else disclose the match count is a floor.
- **#26** branch the truncation-note wording on whether a client filter actually ran ("showing 25" vs "examined for filtering").
- **#30** top-N compare: select the top-N suppliers first (cheap ranking), then fetch only their POs — never page the whole PO table.
- **empty-result double-negation (#5)** collapse the two redundant "No X found" sentences to one.

## After each phase
Full `pytest -q` green; commit; update `spire_overnight_findings.md` (mark the
issue `fixed` with commit ref) and `spire_enhancement_status.md`. A closed issue
is not revisited. When Phase 4 completes, run a fresh overnight to confirm the
synth count is zero and no regressions surfaced.

---

## Cross-reference to the requirements/status workstreams
- Theme C (#7, #12, #13) **is** the P0 COL-01/COL-02/CSV-01 column workstream (status §2A) — these issues are concrete instances; closing them advances that requirement. CSV-01 (export) remains the companion once list rendering is deterministic.
- Theme A (#1, #3, #5, #8) **is** OUT-04 (local synthesis) completion — the status doc records invoice lists and PO lists as the remaining unbuilt read paths; this plan finishes them and extends to joins/empty/lifecycle.
- Theme B (#6) completes the PARTIAL AI-5 (UX-01 refusal-message family) and the readable-planner-refusals work (#11).
- #10, #4 (Theme D) are parser-robustness items not previously tracked as requirements.
- OUT-06 (fetch-completeness disclosure) is built in code but **not yet agreed with the SME** — orthogonal to these issues; flagged so it isn't assumed closed.


# ═══════════════════════════════════════════════════════════════════
# APPENDIX — 2026-08-14 per-set evidence (verbatim, snapshot; not maintained)
# ═══════════════════════════════════════════════════════════════════

> This is the raw prompt-by-prompt reading that produced issues #26–#35 and the
> #1/#5/#6/#7/#9 updates. Kept for traceability; treat as a dated snapshot, not a
> living section. Each block already fed the numbered issues above — do not re-derive.

## Set 00_dipstick — 6 prompts, exit 0

**Refusal format:** 1 refusal — "contract renewals due next quarter". On-template:
Reason / Solution / Example / `(refusal: unknown_entity — The 'Contract' entity is
not supported.)`. ✓ consistent.

**Synthesis (local vs LLM):** 1 LLM synth — "Addresses for supplier 1252" (Shape A).
Other 5 prompts LOCAL: "Count of suppliers" ("There are 339 suppliers"); "Get list
of active suppliers" (table); "Show PO 2144 and its lines" (#21 PO-with-children
path, Buyer renders correctly as "Gee, May"); "Show me AR invoices for customer ABC
Corporation Americas" (CustomerAccount + CustomerTransaction, 26 records, account
header + transaction sub-table, no synth — confirms AR account+transactions is
already local).

**Discrepancies:**
- **#2 (labelling) LIVE again**: "Count of suppliers" → "There are 339 suppliers"
  (no "total" scope word); "Get list of active suppliers" → "Showing 25 of 337
  suppliers. All 25 have Status ACTIVE." 337 is the ACTIVE count but labelled plain
  "suppliers", still readable as the whole population. The intra-run CONTRADICTION
  is still gone (339 all − 337 active = 2-gap, plausible), but the labelling half of
  #2 resurfaced. Scope-labelling fix ("339 suppliers total" vs "337 active
  suppliers") still owed. Population drift 338→339/337 is the known pod fluctuation,
  not a bug.
- **New cosmetic → #26**: active-list Truncation note reads "337 total in source; 25
  examined for filtering" while `client_filters: (none)` — no client filter ran, so
  "examined for filtering" mis-describes a server-filtered path. Count (25 of 337) is
  correct; only wording is wrong.

**Contrast worth keeping:** Buyer renders correctly ("Gee, May") on the local
PO-with-lines path, but drops to an em-dash on Shape B ("PO 2144 with order number
and agent") which projects agent→Buyer.DisplayName through the LLM path. Same PO,
same buyer, two code paths — one local+correct, one synth+broken.

## Set 01_supplier — 40 prompts, exit 0

**Refusal format:** 1 refusal — "everything about supplier 1252". On-template:
Reason / Solution / Example / `(refusal: unsupported_filter — There is no filter
to identify a supplier by a numeric ID.)`. ✓ Minor content note: Solution is the
generic "Narrow by country, status or name instead" (AI-5 over-application, tracked
under #6) — an odd fit for an "everything about X" request that wasn't a narrowing
problem.

**Synthesis (local vs LLM):** 1 LLM synth — "Addresses for supplier 1252" (Shape A,
the run's only repeated synth). Other 38 prompts LOCAL. Notably **invoice lists are
local**: "Show me invoices for supplier 1252", "Invoices for supplier 1252 over
100000", "Invoices for Lee Supplies in 2023" all render the deterministic
`local_list_summary` ("All N have InvoiceCurrency USD / All N have Supplier Lee
Supplies") — the #3 LLM-drift signatures ("another for -163.16", min/max over a
truncated window, "Eight at 0.00") are ABSENT. **#3 fix confirmed holding.**

**Discrepancies:**
- **#5 (empty-result) double-negation REPRODUCED, and it is LOCAL.** "Suppliers
  created between Jan and Mar 2025" → 0 records, **parse-only (no stage=synthesize)**,
  but the answer prints TWO lines: "No suppliers found matching the criteria." then
  "No suppliers found." So #5's synthesis half is FIXED (empty results now built
  locally via `_all_buckets_empty`, no LLM), but the doubled wording is live — the
  local empty-template emits both a criteria-line and a bare-line. Split #5: synth →
  fixed; double-negation → open (cosmetic).
- No AI-7 / #18 contradiction: every "All 25 have Status ACTIVE" line pairs correctly
  with its own table.

## Set 02_purchase_order — 10 prompts, exit 0

**Refusal format:** no refusals in set.

**Synthesis (local vs LLM):** **ZERO LLM synth** — every prompt local. PO-with-
children (#21 path), lifecycle (`build_lifecycle_summary`), and both compare shapes
(`po_invoiced_vs_ordered`, `supplier_invoiced_vs_ordered`) all run parse-only.

**Discrepancies:** none. Three fixed issues re-verified holding on current code:
- **#4 (PO 2144 id-type) CONFIRMED holding.** "How much of PO 2144 was received?"
  now resolves — found=True, order_number 162352, full local lifecycle; Unresolved
  section discloses "'2144' is a POHeaderId, not an order number; resolved to
  OrderNumber '162352'". No synth. Quality is high: paid leg reads "not yet
  determined" (not 0), remaining legs shown, honest "cannot be determined" reasoning
  — the PR #131 lifecycle-local fix working well.
- **#23 (unbounded PO list) holding.** "List all purchase orders" → "Showing 25 of
  17,447 purchase orders." Sample-and-disclose, honest total.
- **Compare shape honest + local.** "How does invoiced compare to ordered for Lee
  Supplies?" → discloses "1,242 of this supplier's invoices were not linked to a PO
  and are excluded from the comparison." The 06_slow timeout on "compare top 3
  suppliers" was a pod-side execute timeout (multi-supplier fan-out), NOT a code
  fault — these single/named compares prove the path is sound.

## Set 03_ar — 17 prompts, exit 0

**Refusal format:** no refusals in set.

**Synthesis (local vs LLM):** **ZERO LLM synth** across all 17 AR prompts — invoices,
credit memos, receipts, receipt applications, account balances, exposure ranking,
receipt-method distribution, and lag are all LOCAL. **The handoff's "AR is the most
likely place remaining synth hides" concern did NOT materialise.** AR is clean.

**Discrepancies — one real correctness bug (new #27):**
- **Credit-memo TOTAL is a sample-sum mislabelled as the full total.** "What is the
  total value of credit memos?" → "Showing 25 of 2,249 credit memos. … Total credit
  value: -232863.06." The -232,863.06 is the sum of the 25 SHOWN rows only (dominated
  by a single -220,000 row), printed as "Total credit value" with no "partial" / "of
  the 25 shown" qualifier. The user asked for the total and will read this as the
  total of all 2,249 — but 2,224 rows are excluded from the sum. Truncation note says
  "2249 total in source; 25 examined for filtering" (the #26 wording) — here it masks
  the partial-total rather than merely being cosmetic.
- **Contrast proves AR aggregation CAN be complete:** "Rank top accounts by outstanding
  exposure" → "Top 10 of 500 accounts by open receivables", Monster Fitness 136,795,153.23
  — a genuine top-N ranked over ALL 500 server-side with honest "of 500" disclosure. So
  the credit-memo total path is a specific bug, not a general limit.

## Set 04_columns — 8 prompts, exit 0

**Refusal format:** no refusals in set.

**Synthesis (local vs LLM):** zero LLM synth — all 8 local. Column projection runs
without the LLM.

**Discrepancies — projection-layer issues:**
- **country → Address SILENT SUBSTITUTION (new #28; ties to owner-parked #7).**
  "Supplier number and country for active suppliers" (and the 4-field "Supplier name,
  number, status and country") emit: Note: 'Country' isn't available on Supplier — then
  substitute a full **Address** column relabelled, e.g. "6302 England St,HOUSTON, TX
  77021 Harris". Country IS derivable (from that very address, or CountryCode), so the
  "isn't available" note is misleading and swapping in Address without saying "showing
  Address as the nearest available field" is a silent substitution. Valid columns
  (Supplier, SupplierNumber, Status) render fine alongside it.
- **credit rating handled CORRECTLY** (566): a genuinely nonexistent field → correct
  "isn't available" note + clean fallback to Supplier name, no fabrication. ✓ This is
  the right behaviour; #28 is that `country` is treated as nonexistent when it is
  actually derivable.
- **Double "Answer:" header** in every column-projection block — the sample-disclose
  summary prints under one "Answer:", then the projected table under a SECOND "Answer:".
  Structural render oddity; fold into #28 or a Theme-E wording note.
- **#26 wording recurs** ("337 total in source; 25 examined for filtering", client
  filter = none).

**Relation to shape B (#26/#1):** shape B projects `agent`→Buyer.DisplayName (a JOIN
field) and the projection can't resolve it → **em-dash**. `country` maps to no direct
column → **Address-swap + note**. Two different symptoms, same root: the projection
layer mishandles fields that aren't plain columns (joins, or derivable-from-nested).

## Set 05_refusals — 8 prompts, all refuse, 0 synth

**Refusal format:** STRUCTURE uniform across all 8 — Reason / Solution / Example /
`(refusal: <code> — <detail>)`. ✓ Two CONTENT defects:
- **Detail-text is NON-DETERMINISTIC across sets (new #29).** "show me contract
  renewals due next quarter" refuses here as `unknown_entity — The system does not
  support 'Contract' as an entity.` but in 00_dipstick as `unknown_entity — The
  'Contract' entity is not supported.` Same prompt, same code, DIFFERENT detail wording
  → the parser LLM is generating the detail string, not emitting a fixed capability
  string. Five refusals here use the dense "The system does not support/track …"
  phrasing.
- **AI-5 "Narrow by country, status or name" Solution MIS-APPLIED (ties to #6).**
  "which suppliers have the best rating" and "suppliers with net 30 payment terms" get
  Reason "not the way this question narrows them" + Solution "Narrow by country, status
  or name instead" — but narrowing won't surface ratings or payment-terms (neither is
  tracked/filterable). The Solution should state the attribute isn't supported, not
  suggest a narrowing that can't help.

**Synthesis (local vs LLM):** zero — all 8 parse-only.

**Discrepancies:** the two above. **Correct behaviour re-verified:** #6
`unsupported_operation` Solution ("Ask for the underlying records and I'll return them
for you to total or average.") holds on "quality score" and "stop buying from" ✓;
entity/identifier/relative-date refusals (PO line items, recent invoices, POs older
than 6 months) have well-matched Reason/Solution/Example ✓.

## Set 06_slow — 15 prompts, 14 clean + 1 pod-timeout, 0 synth

**Refusal format:** no refusals in set.

**Synthesis (local vs LLM):** zero across the 14 completed prompts. Heavy aggregates
(spend ranking, PO-worth-by-status) run LOCAL over full fetches.

**Discrepancies:**
- **exit-1 is a POD TIMEOUT, not a code bug.** "Compare ordered vs invoiced for our top
  3 suppliers" parsed fine, then in EXECUTE paged all 17,447 POs (35 pages) + 2,000 +
  into a 3,256 set before the pod returned "Upstream request timed out" at 145.7s. Never
  reached synthesize. Confirms the run-wide count of 5 is not depressed by an incomplete
  set — 14/15 ran; 5 is trustworthy.
- **New #30 — top-N compare fetches the ENTIRE PO universe.** Single/named compare is
  bounded (Lee Supplies 26.2s in set 02), but the "top N suppliers" variant issues no
  supplier filter on the initial fetch and pulls all 17,447 POs, then narrows client-
  side → pod timeout. Unbounded-fetch class (same family as the sample-and-disclose /
  REC-2 concerns, but on the compare path).
- **Aggregates CORRECT & COMPLETE here:** "Top 10 suppliers by spend in 2022" →
  "Top 10 of 41 suppliers by spend", ranked over all 41 ✓; "How many purchase orders are
  there and what are they worth?" → "Total POs: 17447, total value: 1,932,476,973.53"
  with a full status breakdown that sums to the total ✓. This CORROBORATES #27: total-
  over-all works on the PO path in the same set, so the credit-memo partial-total is a
  specific broken path, not a platform limit.

## Set 07_alacarte — 12 prompts, 0 synth, 1 refusal

**Refusal format:** 1 refusal — "Show supplier 1252 with supplier name, number, and
address" → `unsupported_filter — Supplier queries cannot be rooted by a supplier number`.
On-template ✓, but Solution is the AI-5 "Narrow by country, status or name" mismatch (#6).
**Internal inconsistency (ties #9 + shape A):** "Addresses for supplier 1252" RESOLVES
1252 and synthesizes (shape A), while "Show supplier 1252 with … address" REFUSES 1252 as
unrootable. Two supplier-1252 paths disagree on whether a bare supplier number is usable.

**Synthesis (local vs LLM):** zero — all 12 local. Column projection and aggregates run
without the LLM.

**Discrepancies:**
- **Em-dash in JOIN projection (#31) — shape-B symptom on real data.** "Show me invoices
  for EIP Inc with invoice number, PO number, and PO line number": 'PO line number'
  correctly noted unavailable; but `PurchaseOrderNumber` (a LISTED available column) is
  projected and shows `—` for EVERY row ("EIP  2012119 | —"). Output cannot distinguish
  "these invoices have no PO" from "projection failed to read PurchaseOrderNumber" — the
  AMBIGUITY is the defect. Same class as shape B (agent→Buyer.DisplayName → em-dash).
  **Curl owed** to determine whether these EIP invoices carry PurchaseOrderNumber on the
  pod.
- **Address projection CORRECT when requested directly** (331, "active suppliers with …
  address"): Address column renders full nested address, no note, no swap — confirms #28
  is `country`-specific (derivable-but-unmapped), not an address-render bug.
- **#26 contrast (correct usage):** invoice block 9 ("EIP over 100000") shows "unknown
  total in source; 25 examined for filtering" — here a REAL client-side filter ran, so
  "examined for filtering" is CORRECT. Sharpens #26: the wording is right when a client
  filter runs, wrong (as in 00/04) when only a server filter ran.
- **Aggregate complete:** "Top 5 suppliers by invoice spend last year" → "Top 5 of 66",
  ranked over all 66 ✓ — again corroborating #27.

## Set 08_lifecycle — 31 prompts, 0 synth, 2 refusals

**Refusal format:** 2 refusals — "Have all purchase orders been fully received and paid?"
and "Compare the lifecycle of PO 701337 and PO 162034.", both `unsupported_operation`,
on-template ✓, both correct (lifecycle is single-PO-only).

**Synthesis (local vs LLM):** **ZERO** across all 31. `build_lifecycle_summary` (PR #131)
holds across all 28 answered lifecycle variants and every phrasing (received/paid, blocking,
executive summary, risk, stage, responsible team, end-to-end). No LLM narration anywhere.
Strong confirmation the lifecycle-local fix is solid.

**Discrepancies — one MAJOR (new #32, 🔴):**
- **Parser drops the PO identifier on certain phrasings → planner falls through to a 25-of-
  17,447 LIST-DUMP.** THREE prompts hit it: "Is PO 162034 complete?" (210), "Is anything
  blocking PO 162034?" (496), "Has PO 999999999 been fully received…?" (1470). Each parsed
  to a BARE intent — `target_entity: PurchaseOrder`, no filter, no lifecycle op, out≈103–113
  tokens — which planned `search_purchase_orders {}` and dumped 25 of 17,447 arbitrary POs.
  **162034 is a REAL PO** — "Has PO 162034 been fully received, fully invoiced, and fully
  paid?" (80) and the compare (1592) both handle it correctly. So this is phrasing-dependent
  parser fragility, NOT a fake-PO issue.
- **Contrast — DOES-NOT-EXIST handled correctly** (1543): non-numeric miss → "No purchase
  order found for 'DOES-NOT-EXIST'." The not-found path works WHEN the parser routes to the
  lifecycle tool; #32 is the parser failing to route there at all.

## Set 10_refusal_examples — 20 prompts, 2 synth, 1 refusal

**Refusal format:** 1 refusal — "supplier sites for Lee Supplies" →
`unsupported_operation — Supplier sites aren't available as a standalone listing.`,
on-template ✓. Sub-note: its Example is "addresses for supplier 1252" — which is shape A,
a SYNTH-triggering prompt. Refusal examples should steer to clean local paths, not to a
prompt with an open defect.

**Synthesis (local vs LLM):** the run's 2 remaining tracked calls both live here —
shape A "addresses for supplier 1252" (target=Address, in=4452 out=3116 total=7568) and
shape B "Show PO 2144 and its buyer" (in=1393 out=541 total=1934).
**CORRECTION to earlier shape-B note:** THIS block renders CORRECTLY — a clean 2-step join
(get_purchase_order_by_id → get_buyer on BuyerId), output "Buyer : May Gee", no em-dash. It
is a pure synth-elimination candidate (LLM-narrated a record that's already fully copied),
NOT an em-dash case. The em-dash belongs to the DIFFERENT phrasing "Show PO 2144 with order
number and agent" (set 11, projection-with-`fields` path) and to PurchaseOrderNumber in set
07 (#31). Reconcile the two shape-B phrasings at set 11.

**Discrepancies:**
- **Classification filter under-counts (new #33).** "suppliers with classification Minority
  Owned" → "Examined 25 of 341 suppliers. Of those 25, 1 match the filter." Only the first
  25 of 341 were examined client-side; matches among the other 316 are unknown. It DOES
  disclose the sampling (better than #27's silent partial total), but a filter query is
  effectively answered from a 25-row sample — the true match count is unknowable from this
  output.
- **Scoped credit-memos CORRECT & LOCAL** (917, "credit memos for ABC Application Software"):
  CustomerAccount + transactions, no synth. Sharpens #27 — only the UNSCOPED "total value of
  credit memos" has the partial-total bug; scoped credit-memo queries are fine.

## Set 11_column_vocabulary — 53 prompts, 1 synth, 4 refusals

**Refusal format:** 4 refusals — 3× "supplier sites/vendor site/…" →
`unsupported_operation — Supplier sites aren't available as a standalone listing.`, 1×
"business unit" → `unknown_entity — Cannot include 'Business Unit' as it is not a supported
related entity.` All on-template ✓.

**Synthesis (local vs LLM):** 1 — shape B "Show PO 2144 with order number and agent" (1934).
**Shape-B split now RESOLVED** — see #34. This is the em-dash phrasing; "Show PO 2144 and its
buyer" (set 10) is the clean-but-synthesized phrasing.

**Discrepancies:**
- **#34 (new) — WRONG-STEP PROJECTION is shape B's real root.** "order number and agent"
  parses to `include:['Buyer']` + `fields:['OrderNumber']` → a TWO-step plan (po → buyers).
  The projection then builds "buyers (1 record) — columns: OrderNumber" and prints `—`,
  because it projected OrderNumber against the **buyers** step-output. But OrderNumber IS
  present — "162352" — in the `po` step-output in the SAME block. The value exists and was
  projected against the wrong step. Also notes "'Buyer.DisplayName' isn't available on
  PurchaseOrder" (agent→Buyer.DisplayName dropped). **No curl needed** — the mislocation is
  provable from the block. Distinct from #31 (which is single-step null-vs-unresolved).
- **#31 confirmed** on "invoices for EIP Inc with … PO number, and PO line number" (2779):
  single `invoices` output, PurchaseOrderNumber listed available, all 25 rows em-dash. Curl
  still owed (ERS-* invoice numbers suggest self-billing/no-PO, but 45083 lacks the prefix
  and is also em-dash).
- **#28 BROADENED**: "supplier name and state" (1048) treats `state` as unavailable, same as
  `country`. Raw supplier records in THIS set show `TaxpayerCountryCode: 'US'` on the body —
  so country IS available (as TaxpayerCountryCode), merely unmapped in projection vocabulary.
  Directly ties #28 to the #7 country-semantics decision (TaxpayerCountryCode vs
  Address.CountryCode). state/city are the Address-nested variants.
- **Fixes HOLDING:** #12 who/audit → `fields` (who details, audit columns, "created by",
  creation date, last updated all expand correctly) ✓; nonexistent fields (quantum flux,
  credit rating, risk score, payment terms) → note + clean fallback, no fabrication, no dump
  ✓; synonym/casing coverage (supplier_name, SupplierName, SUPPLIER NAME, vendor name/number,
  invoice-number, invoice value) all resolve ✓.

## Set qa_testcases — 34 prompts, 0 synth, 23 refusals

**Refusal format:** 23 refusals, ALL on-template ✓, codes well-matched: `missing_identifier`
(pronoun/underspecified — "that invoice line", "this invoice", "that PO", "this account",
"get account receivables transactions"), `unsupported_filter` (account-number, business-unit,
InvoiceNumber-direct), `unsupported_operation` (receipt volume/trend/monthly aggregation,
supplier sites), `unparseable` ("get transaction number"). Strong refusal discipline across a
deliberately underspecified set.

**Synthesis (local vs LLM):** zero — all prompts local or refused.

**Discrepancies:**
- **#27 REPRODUCES** (110, "List recent credit memos, top 5"): "Showing 25 of 2,249 credit
  memos. Total credit value: -232863.06" — the same partial-sum-over-25-rows labelled as the
  total. Second confirmation of #27, now on a different phrasing.
- **New #35 — `top N` IGNORED on the credit-memo list path.** "List recent credit memos,
  top 5" returned 25 of 2,249, not 5. Contrast set 03 "top 5 open invoices for ABC" which
  correctly returns 5. The credit-memo list path drops the top_n selector.
- **Contextual pronoun prompts FAIL SAFE** — "For that PO…", "…that invoice line", "…this
  invoice", "…this account" all refuse `missing_identifier` rather than dumping. #32's list-
  dump does NOT occur for pronoun prompts. (Cross-prompt context is not resolved — each prompt
  runs stateless in the overnight harness; expected, and it fails safe.)
- **"list purchase orders" (601) is LEGIT sample-and-disclose** ("Showing 25 of 17,447"), NOT
  a #32 dump — the user explicitly asked for a list with no identifier. **Nuance for the #32
  fix:** the planner guard (fault b) must distinguish an EXPLICIT list request ("list purchase
  orders" → list is correct) from a DROPPED-IDENTIFIER specific query ("Is PO 162034 complete?"
  → must refuse, not list). The two produce the same filter-less PurchaseOrder intent but need
  opposite handling.
- **Ranking paths correct** ("Show account activity summary for top accounts" → "Top 10 of 500
  accounts by open receivables") ✓. Consistent with every other ranking path this run — only
  the credit-memo list/total path is broken.
