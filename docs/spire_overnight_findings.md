# Spire — Consolidated Issue Register & Fix Plan

**Prepared:** 2026-08-13, after the overnight re-run of all 12 prompt sets
(`overnight_20260812/`). Cross-checked against `spire_overnight_findings.md`,
`spire_enhancement_status.md`, and `spire_enhancement_requirements.md`.

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

---

## Theme map (similar issues combined — drives the fix plan)

- **Theme A — Eliminate LLM synthesis (make it all local):** 1, 3, 5, 8, 12(synth part). Supersedes 15/21's precedent (both were closed by going local).
- **Theme B — Refusal correctness & format:** 6, 9, 11, 13.
- **Theme C — Column / field resolution:** 7, 12(vocabulary part), 13. Extends the P0 COL-01/COL-02/CSV-01 workstream in the status doc.
- **Theme D — Parser robustness & PO reference resolution:** 4, 10.
- **Theme E — Count / sample consistency:** 2, 14.

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

**Progress (2026-08-13):** two shapes converted to local this pass — the
supplier+open-PO **join** (#8) and plain **invoice lists** (#3) — each verified
live with no `stage=synthesize` and exact/correct output. Remaining shapes still
LLM-synthesized: address lists, other multi-bucket joins (e.g. supplier+contacts),
lifecycle narration, and empty/not-found (#5, unverified). A fresh overnight is
needed to recount `stage=synthesize` and enumerate exactly what is left.

**Status:** open — IN PROGRESS. Absorbs old AI-3 (address-list sub-case). Two
shapes done (#3, #8); the rest deferred to a **follow-up branch** after this PR
merges. Umbrella goal (0 synth calls on a fresh overnight) not yet met.

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

## 5 🟡 open — "Not found" / empty answers are LLM-synthesized instead of a local template — (was: new)

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

---

## 6 🟢 fixed — Refusal "Solution" line off-template — (was: new + AI-5)

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
One short curl session; promotes each to `verified` or reclassifies it.

## Phase 1 — Theme C: field-synonyms & projection safety (small, deterministic, high payoff)
Closes real column bugs and de-risks the model's unknown-column refusals.
- **#7** "country" → `TaxpayerCountryCode`; stop the Address injection.
- **#12** "who details" → WHO columns; guard projection against columns absent from rows (kills the em-dash).
- **#13** advance COL-01/COL-02 so intended columns resolve; ensure the note path (not the upstream refusal) is reached for genuinely-absent columns.
Mechanism is the existing COL-02 expander (KG lookup, not model judgement). One PR per synonym group + one for the projection guard.

## Phase 2 — Theme B: refusal correctness & format (small, user-visible)
- **#6** rewrite `unsupported_operation` Solutions (per sub-case) + finish the AI-5 `unsupported_filter` correction.
- **#11** route the PO-filter planner guard through `RefusalError` → `capability_message`; audit remaining guards.
- **#9** re-route single-supplier-by-id-with-columns to the by-id lookup; correct the false refusal text.
Verify against `05_refusals` and `10_refusal_examples` (promised examples must still answer).

## Phase 3 — Theme D: parser robustness & PO reference
- **#10** fix the degenerate-parse trigger for "what is outstanding"; add a parse-time cap that degrades gracefully.
- **#4** cross-try POHeaderId/OrderNumber (or resolve once to canonical id).
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

## Phase 5 — Theme E: count/sample consistency
- **#2** label scopes (after Phase 0 curl).
- **#14** deterministic sample order on the bounded fetch (watch the representativeness trade-off).

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
