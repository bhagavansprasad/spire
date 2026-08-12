# Spire Overnight Analysis — Findings & Action Items

**Run analyzed:** overnight run 1 (2026-08-04, 23:57 → 01:35), 12 prompt
sets, `run_prompt_set.py` with diagnostics OFF. A second run with
`show_all` (tokens + full diagnostics) was captured separately for
cross-checking.

**Method.** One set at a time: read every prompt's answer, verify each
suspected bug with a curl against the pod (and/or a code trace), confirm
correct-vs-broken, derive action items, then CLOSE the set. A closed set is
not revisited. "Ran cleanly" in the runner's tally is NOT a verdict — every
answer is read against intent.

**How to read an entry.** Each action item records: the **set** it came
from, the **exact prompt**, the **actual** output, the **expected** output,
the **verification** (curl command + output, or code trace), the **root
cause**, the **fix**, a **severity**, and a **status**.

Severity: 🔴 real defect (wrong/missing data or wrong behaviour) · 🟡 minor
(cosmetic / noise) · 🟢 note (not wrong; efficiency or future work).

Status: `open` · `verified` (confirmed real, fix defined, not yet built) ·
`fixed` · `not-a-bug` (looked wrong, verified correct).

---

**Analysis complete: all 12 sets closed.** 11 distinct action items (AI-1
through AI-11) + 1 feature proposal (REC-1). Below, grouped by theme and
ordered by priority.

**FIX PHASE COMPLETE (2026-08-06 — merged to master).** 8 fixes + 1 feature
shipped across 5 commits, each verified live and against the full suite (862
passed, 1 xfailed):
- ✅ QA-01/AI-1 (child rows), QA-02/AI-4 (honest denominators), QA-12/REC-1
  (completeness advisory), QA-03/AI-7 (receipts field-name mismatch) —
  commit `8ad9b39`
- ✅ QA-04/AI-11 (site-listing crash), ⚠️ QA-05/AI-5 (refusal message — the
  message half only) — commit `37522b1`
- ✅ QA-06/AI-9 (mixed valid+invalid columns) — commit `b85eed1`
- ✅ QA-07/AI-6 (single-leg PO routing) — commit `eb2fd72`
- ⚪ QA-08/AI-2 — closed as not-a-bug (show_all artifact)
- Refactor: the two `validation.py` files renamed (`intent_validation.py`,
  `response_validation.py`) — commit `4360035`

**Deferred (documented, not yet done):** AI-10 (sites → addresses, a parser-
mapping bug — the AI-11 crash sibling); the "everything about X" refusal
mis-routing (parser); POHeaderId → OrderNumber resolution for the lifecycle
tool. Per-finding status lines below carry the detail.

### Root-cause clusters (verified 2026-08-06 — fix by cluster, not by finding)

The 11 findings share roots. Verified against source, they collapse to 4
clusters + 4 singletons. Fix by cluster.

**Cluster A — child-as-count display (QA-01 / AI-1).** One file
(`display_formatters.py`). VERIFIED SCOPE: 4 sites in 2 parent blocks —
PO lines/schedules/distributions (531/533/535) and AR invoice lines (562).
Supplier contacts and AR tax lines were reported here too but are ALREADY
FIXED in code (indented sub-tables, 474–487 and 585–605) — the fix template
already exists in-file. One fix, closes AI-1 across sets 00/02/03/07/08/10.

**Cluster B — edge-traversal engine (QA-02/AI-4 + QA-12/REC-1 + the set-06
slowness).** One mechanism: fetch 25 suppliers, walk each one's children
client-side. Produces the lying denominator (AI-4), the 29–113s latency, and
is the base REC-1's advisory sits on. FLOOR→CEILING: AI-4 (message must not
lie) is prerequisite; REC-1 (honest message + narrowing rec) builds on it.
Order is fixed: AI-4 then REC-1.

**Cluster C — refusal-message template (QA-05/AI-5 + the MESSAGE half of
QA-06/AI-9).** The parser's `unsupported_filter` flavor emits a generic
"narrow by country/status/name" string regardless of the real reason.
Misapplied to payment terms, ratings, "everything about X", and (3rd variant)
the aggregation "needs a total/ranking/trend" template on a column problem.
One message-routing fix. NB: QA-06 is split — its MESSAGE is Cluster C; its
BEHAVIOUR (wholesale refusal) is the G15 upstream-`unanswerable` parser
limitation, a separate harder fix.

**Cluster D — Site KG gap (QA-04 = AI-10 + AI-11).** Already merged. Site has
no standalone KG fetcher: one phrasing degrades to addresses (AI-10), another
crashes on missing `business_unit` (AI-11). One root, one fix (give Site a
fetcher, or refuse at plan time + validate required args at plan not execute).

**Singletons (do not merge):**
- **QA-03 / AI-7** — false-empty. VERIFIED standalone in code (see AI-7): an
  exact-string-match site filter in `standard_receipts.py`, NOT Cluster B's
  engine.
- **QA-07 / AI-6** — no dedicated "received" tool.
- **QA-08 / AI-2** — debug leak. Trivial.
- **QA-09 / AI-3** — token-heavy synthesis. Efficiency.

**Feature-vs-bug question (settled):** building REC-1 does NOT fix bugs for
free. It is the ceiling of Cluster B only; AI-4 (the floor) is its
prerequisite, and it touches no other cluster. The only place "feature helps
bugs" is real is inside Cluster B, and only in the order AI-4→REC-1.

**Proposed cluster order:** A (pure win, no deps) → B as a unit (AI-4 then
REC-1) → C (one template fix) → D → singletons → the harder QA-06 behaviour.


### The big four (fix first — real wrong/missing/crashing output)

| ID | Sev | Status | Summary | Scope |
|----|-----|--------|---------|-------|
| AI-1 | 🔴 | verified | Child rows rendered as COUNTS, not rows ("Lines: 2" for "show PO and its lines"). Data is fetched; the table collapses it to a count. Prose often carries the detail, but the table (what users scan) lies. | PO lines, schedules, distributions; AR invoice lines, tax lines; supplier contacts. (NOT single records like buyer.) |
| AI-4 | 🔴 | verified | Edge-traversal filters state the partial as the total ("2 of 429" when 2 is of the 25 examined). Wrong denominator — misleading count. Also the slowest prompts (29-113s), same root cause. | EVERY edge-traversal filter: classification (small/woman/veteran/minority owned), business-unit/site, invoice-amount, open-POs, no-recent-invoices. Pervasive. |
| AI-7 | 🔴 | verified (logs) | Self-contradiction: "All 25 have Site Santa Clara" then "No receipts found" — 25 real receipts fetched, then reported as none. | AR receipts with a client-side site filter. |
| AI-10 + AI-11 | 🔴 | verified (logs) | "Supplier sites" is broken two ways: one phrasing silently returns ADDRESSES (wrong resource, AI-10); another CRASHES on a missing business_unit arg (AI-11, the sole exit-1). | Supplier sites listing. Root: Site has no proper KG fetcher. |
| AI-12 | 🔴 | verified | Schedules sub-table "Received" column shows raw `ReceivedAmount` (0.0, which is 0/null pod-wide) as a fetched value, contradicting the prose's `ReceivedQuantity` ("1 of 1 received"). The lifecycle tool derives+labels this correctly; the QA-01 schedules renderer does not. | PO schedules sub-table (display path). New — post-fix verification read, 2026-08-08. |

### Refusal-quality bugs (message is wrong/misdirected)

| ID | Sev | Status | Summary |
|----|-----|--------|---------|
| AI-5 | 🟡 | verified | "Narrow by country/status/name" template over-applied to refusals that aren't narrowing problems (payment terms, ratings that don't exist, "everything about supplier X"). Real reason is in the parenthetical but not surfaced. 3 wrong-template variants seen. Fix: model parser messages on the accurate planner-guard style. |
| AI-9 | 🔴 | verified | Mixed valid+invalid column requests refused WHOLESALE (loses the valid columns), e.g. "supplier name and credit rating". BUT inconsistent — COL-03's honest note WORKS for many unknown columns (07_alacarte P2); it fails only when specific phrasings trip the model's upstream unanswerable flag (G15 limitation). |
| AI-6 | 🟡 | verified | Specific question ("how much of PO 2144 was received?") answered with a generic PO summary; the answer is buried in prose, not stated directly. No dedicated "received" tool. |

### Minor / cleanup

| ID | Sev | Status | Summary |
|----|-----|--------|---------|
| AI-2 | 🟡 | verified | `[debug] shape = None` leaks into user-facing output. Trivial. |
| AI-3 | 🟢 | open | Address-list synthesis token-heavy (out≈3133). Local-synthesis candidate. |

### Feature proposal

| ID | Sev | Status | Summary |
|----|-----|--------|---------|
| REC-1 | ⭐ | proposed | **Completeness advisory.** When a query samples a capped set: deliver the results found, state honest denominators (AI-4's fix), AND recommend narrowing filters (read from the KG) so a complete answer is cheap. Never refuse, never inflate. Generalizes to any capped-fetch query. AI-4 is the floor (message must not lie); REC-1 is the ceiling (honest message + narrowing rec). REC-1 depends on AI-4. |

### Verified correct (checked, NOT bugs — do not re-investigate)

| Set | Item | Looked like | Verified |
|-----|------|-------------|----------|
| 00_dipstick | "Count of suppliers" → 429 | page-size-as-total | curl: pod `totalResults`=429. Correct. |
| 00_dipstick | AR open receivables −206,448.85 | sign error | curl: pod reports −206,448.85. Real AR credit balance. |
| 03_ar | Exposure ranking 165M, open=due (AI-8) | inflated/duplicated | curl: pod returns 165,428,563.24 for both fields. Real demo data. Ranking correct. |
| 01_supplier | run-1 exit-1 crash | code bug | Transient Gemini 429 rate-limit; ran clean in run 2. Infrastructure, not code. |
| Negative/zero invoice amounts (multiple) | data error | Faithful to pod (credits/adjustments/cancelled). Correct. |

### What's working well (preserve — not defects)

- **PO lifecycle tool (set 08):** ~20 phrasings of the same PO return IDENTICAL facts (stage, risk, amounts, team). Facts computed in code, LLM only narrates. The strongest component. Honest tri-state paid status ("cannot be determined").
- **Compare/aggregation tools (02, 03, 06):** invoiced-vs-ordered, exposure ranking, receipt-method distribution, spend rankings — correct, full-set (`truncated:False`), with honest exclusion notes ("1,226 invoices not linked to a PO, excluded"). The REC-1 principle already lives here.
- **Currency-refusal (03 P8):** refuses to sum across currencies, explains why. Keep.
- **Column projection (04, 11):** requested columns projected exactly. WHO-column synonyms ("created by", "audit columns", "date created") all resolve — layer 3 delivered much of layer 2 for free.
- **Good refusals (05, 08):** planner-guard messages are accurate with concrete examples — the model for fixing AI-5.

### Test-suite organization notes (for a later pass, not now)

- `07_alacarte` → rename to `07_column_selection` (the name is vague; it's a column-projection depth test). Do NOT merge with `00_dipstick` — dipstick is a breadth smoke-test, à la carte is feature-depth; the distinction is valuable (à la carte is where the COL-03 note-works nuance surfaced).
- Edge-traversal prompts are duplicated across `01_supplier` and `06_slow` — genuine overlap; consider consolidating.
- `10_refusal_examples` is misnamed (all 19 ran ok — it's a success-path regression set, not refusals).

---

## Set 00_dipstick — CLOSED

6 prompts. 3 action items (1 real defect, 1 minor, 1 note); 2 items looked
suspicious and verified correct; the refusal is exemplary. Nothing traces to
the who-column work.

Per-prompt verdict:

| # | Prompt | Verdict |
|---|--------|---------|
| 1 | Count of suppliers | ✅ correct (429 verified) |
| 2 | Get list of active suppliers | ✅ correct |
| 3 | Addresses for supplier 1252 | ✅ correct (token-heavy — AI-3) |
| 4 | Show PO 2144 and its lines | 🔴 BUG — AI-1 |
| 5 | Show me AR invoices for customer ABC Corporation Americas | ✅ correct (−206448.85 verified) |
| 6 | Show me contract renewals due next quarter | ✅ correct refusal |

---

### AI-1 🔴 verified — Child rows rendered as counts

**Set:** 00_dipstick
**Prompt:** `Show PO 2144 and its lines`

**Actual output:**
```
Purchase Orders:
  Order      : 162352
  POHeaderId : 2144
  Status     : Closed
  Supplier   : EIP Inc
  Buyer      : Gee, May
  Lines      : 2
```
The user asked to see the lines; the output shows the *number* of lines (2),
not the lines themselves.

**Expected output** (the line detail — data confirmed present on the pod):
```
Lines:
  Line | Description          | Qty | Price | Ordered
  -----+----------------------+-----+-------+---------
  1    | Marketing Assistance |   1 | 33000 | 33000.00
  2    | Marketing Assistance |   1 |  8250 |  8250.00
```

**Verification — curl (pod has 2 real lines with full detail):**
```
curl -s --compressed -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/purchaseOrders/2144/child/lines?fields=LineNumber,Description,Quantity,Price,Ordered&limit=25"
```
Output (trimmed): `count: 2, hasMore: false`; Line 1 Qty 1 Price 33000
Ordered 33000.00; Line 2 Qty 1 Price 8250 Ordered 8250.00.

**Verification — show_all raw output (the lines ARE fetched into Spire):**
```
purchaseorderline: 2 record(s)
  [1] {'POLineId': 19782, 'LineNumber': 1, 'Description': 'Marketing Assistance', ... +9: Quantity, Price, Total, UOM, ...}
  [2] {'POLineId': 19783, 'LineNumber': 2, ...}
```
So the data is fetched and complete — the loss is purely at display.

**Root cause:** `scripts/display_formatters.py`
- line 531: `row["Lines"] = len(po.lines)` — renders the count, not the rows.
- lines 533/535: same for `Schedules` and `Distributions`.
- line 562: same for AR invoice `Lines` (`row["Lines"] = len(inv.lines)`).

The code carries an explicit comment acknowledging this: *"That 'lines: 2'
is a COUNT where the user asked for the lines is a real defect, carried
forward and NOT fixed here: this change is layout only."* So it is a KNOWN,
deliberately-deferred defect — deferred to avoid hiding a behaviour change
inside a formatting diff. Good discipline; now due.

**Scope (verified in code 2026-08-06):** 4 collapse sites in 2 parent blocks
— PO lines/schedules/distributions (`display_formatters.py` 531/533/535) and
AR invoice lines (562). CORRECTION to earlier addenda: supplier contacts
(474–487) and AR tax lines (585–605) are ALREADY rendered as proper indented
sub-tables — NOT collapsed — so they are NOT part of this defect. The working
contacts/tax-lines pattern (`_indent` + `_render_records`) is the exact fix
template for the 4 broken sites; no new render primitive is needed.

**Fix (defined, not built):** render a child sub-table (Line/Description/
Qty/Price/… for PO lines; the analogous set for schedules, distributions,
AR invoice lines) instead of `len()`. Needs a child-row layout in the
formatter. A real feature fix in its own right — should be done once across
all four child cases (and any more found in later sets), not piecemeal.
**Recommend grouping with any related child-rendering findings from other
sets before building.**

**Status:** ✅ FIXED (commit 8ad9b39). Child sub-tables now render for PO lines/schedules/distributions and AR invoice lines. Scope was narrower than reported: contacts and tax lines were already correct.
method).

---

### AI-2 / QA-08 ⚪ CLOSED — not a bug (verified 2026-08-06)

**Reported:** `[debug] shape = None` leaks to user output.

**Verified in code — NOT a leak.** `diagnostics.py` gates the
`spire.synthesizer` logger correctly: DEBUG when `show_synthesizer` is on,
WARNING (silent) when off. The `_log.debug("[debug] shape = %s", shape)` line
in `synthesizer.py` only prints when `--show-synthesizer` is set. It appeared
in overnight run 2 and in re-tests because BOTH were run with `show_all = true`
(which `_expand_show_all` turns into every gated flag on, `show_synthesizer`
included). With `show_all`/`--show-synthesizer` off, the line is silent — as
designed. The finding mistook a `show_all` diagnostic artifact for a leak.

**Action:** none required. The behaviour is correct. OPTIONAL future tidy:
the line prints "shape = None" on every non-aggregation answer (shape is None
unless the result is an aggregation), which is noisy even when synthesizer
output is requested — could log only when shape is not None. Not a defect;
low priority. NB: `flag_matrix.sh` greps for the literal string "[debug] shape"
as its `--show-synthesizer` proof marker, so the line must not simply be
deleted without updating that harness.

**Status:** CLOSED — no code change. Doc corrected.
---

### AI-3 🟢 open — Address-list synthesis is token-heavy

**Set:** 00_dipstick
**Prompt:** `Addresses for supplier 1252`

**Observation:** synthesis ran (`stage=synthesize in=4359 out=3133`) and the
LLM re-narrated every country and city in prose above the table. Output is
correct — just expensive: ~3133 output tokens to summarize a list the table
already shows.

**Expected/desired:** a shorter summary, or local (non-LLM) synthesis for
address lists (the OUT-04 pattern already applied to aggregations and being
extended to lists). Not wrong, so not urgent.

**Fix:** candidate for local list-synthesis; or cap/trim the address
summary. Defer.

**Status:** open (efficiency note, not a defect).

---

## Set 01_supplier — CLOSED

40 prompts (39 ok, 1 refused). The filter/parse layer is SOLID across status,
country, name, business-relationship, date-range, and amount filters (all
parse correctly, counts match). Produced AI-4 (bug) + REC-1 (feature) from
the edge-traversal prompts, an AI-1 addendum (supplier contacts), and AI-5
("everything about X"). Counts and invoice filters (supplier/amount/date)
all correct.

Note: in run 1 this set was exit-1 from a transient Gemini 429 rate-limit on
one prompt — NOT a code bug; it ran clean in run 2. (Logged as verified-correct.)

---

### AI-4 🔴 verified (BUG) — Partial result stated as if it were the total

**Set:** 01_supplier
**Prompt:** `small business suppliers`
(same defect on: `woman owned suppliers in the US`, `suppliers in the US1
business unit`)

**Actual output:**
```
Two suppliers were found: Lee Supplies (1252) and JGA (1254).
These results are partial, showing 2 of 429 available suppliers due to truncation.
```
The phrase "2 of 429" implies 2 is the count of Small Business suppliers
across all 429. It is NOT. It is 2 out of the **25 that were examined**. The
denominator is wrong — the message states a sampled count as a pod-wide
total.

**Expected output** (honest denominators — facts only):
```
Examined 25 of 429 suppliers. Of those 25, 2 are Small Business:
Lee Supplies (1252), JGA (1254).
```
The count is always "N of [examined]", never "N of [total]". The total is
stated as separate context, not as the denominator of the found count.

**Why it happens (plan):**
```
Step 1: search_suppliers {}          → fetches first 25 of 429 (capped)
Step 2: iterate those 25, check has_classification='Small Business' → 2 match
```
The edge-traversal filter runs over a capped 25-row fetch. So "2" is
correct for the 25 examined, but the message frames it against 429.

**Verification:** reference doc §(businessClassifications) records **3**
Small Business across the first **50** suppliers; Spire found **2** across
the first **25**. The count rises with the sample size — proving it is a
function of how many were examined, i.e. a sample, not a total. (A full
429-walk to get the exact number was deemed moot — see REC-1: the answer is
not to walk all 429, but to advise narrowing.)

**Scope:** every edge-traversal filter — classification (`Small Business`,
`Woman Owned`), business-unit (`has_site_in_bu`). Any filter whose
`mechanism = edge_traversal` in `kg_entity_filter`.

**Fix (bug only — the message):** frame the count against the examined set,
not the total. State examined/total as context. This is a message/synthesis
correction, independent of REC-1. Even without the advisory feature, the
message must stop stating a partial as a total.

**Status:** ✅ FIXED (commit 8ad9b39). Deterministic filtered-supplier branch: "Examined 25 of 432; of those 25, 2 match." No LLM.

---

### REC-1 ⭐ proposed (FEATURE) — Completeness advisory

**Set:** 01_supplier (realized here; applies system-wide)
**Trigger prompt:** `small business suppliers` and any query whose plan
samples a capped fetch (examined < total).

**The principle (SME-aligned — two outcomes only, never "refused"):**
When a query can only be answered over a *sample* of the full set, Spire
does three things at once, and none of them is a refusal:

1. **Deliver the results found** — the 2 Small Business in the 25 examined
   are shown. Nothing is withheld.
2. **State the fact honestly** — "examined 25 of 429; 2 of those 25
   qualify." Correct denominators (this is AI-4's fix, which REC-1 builds
   on).
3. **Recommend narrowing** — suggest concrete filters that shrink the set
   so a *complete* answer is cheap: "to check all suppliers, narrow by
   country, status, business relationship, or name."

The query SUCCEEDED — it returned real data. The advisory is metadata on a
successful answer, not an alternative to answering. There is no third
"refused" outcome.

**Why not just walk all 429?** Because it is slow (~7-8 min in testing) and
the user won't wait. Walking the full set trades a fast-but-mislabeled
answer for a correct-but-unusable one. The advisory gives the user the fast
partial AND a path to completeness — their choice.

**Where the recommendation comes from (deterministic, no LLM):** the KG
already holds every filter available per entity (`kg_entity_filter`). Spire
reads that list and offers the real entity-level filters — it does not guess.
For Supplier: country, status, business relationship, name.

**Generalization:** this is not classification-specific. It applies to ANY
query where the plan iterates/filters over a capped fetch — every
edge-traversal filter now, and any future one for free. A general
"examined < total → advise narrowing" rule.

**Design questions (for deliberate design later, after full analysis):**
- Threshold: when does the advisory fire? (examined < total is the clear
  case; is there a lower bound below which it's not worth mentioning?)
- Message shape: exact wording of the advisory.
- Which filters to surface per entity (read from `kg_entity_filter`;
  possibly rank by selectivity).

**History:** this mechanism was proposed in a prior session and passed over.
It is now escalated — it fixes a whole CLASS of misleading-count situations,
not one prompt, and it is the headline recommendation of the analysis so
far.

**Status:** ✅ SHIPPED (commit 8ad9b39). Ruled Tip block, filters read from kg_entity_filter, states why the full scan is slow.
(so the threshold and scope are informed by all the evidence).

**Relationship to AI-4:** AI-4 (bug) is the *floor* — the message must not
lie, and that fix is needed regardless. REC-1 (feature) is the *ceiling* —
honest message PLUS a narrowing recommendation. AI-4 can ship without
REC-1; REC-1 depends on AI-4's honest denominators.

---

### AI-5 🟡 verified (BUG) — Misleading refusal reason on "everything about X"

**Set:** 01_supplier
**Prompt:** `everything about supplier 1252`

**Actual output:**
Reason:   I can look up suppliers, but not the way this question narrows them.
Solution: Narrow by country, status or name instead.
[refused]

**Problem:** the prompt names a SPECIFIC supplier (1252) — it is not a
narrowing problem. The refusal reason ("narrow by country, status or name")
is misdirected: telling a user who asked about supplier 1252 to "narrow by
country" is nonsensical. The vague term is "everything" (which fields?
which children?), not the supplier identity.

**Expected:** either (a) resolve it to a sensible default (the supplier
record + its available children), or (b) refuse with an ACCURATE reason —
e.g. "‘everything’ is ambiguous; ask for specific fields or children like
addresses, contacts, or invoices for supplier 1252." The refusal reason
must match the actual problem.

**Root cause (likely):** the parser routed the ambiguity to the
unsupported_filter refusal flavor (the "narrows them" message), the same
mis-routing pattern seen elsewhere — a non-filter problem landing on the
filter-refusal message.

**Severity:** 🟡 — it correctly declines rather than inventing data, but the
reason misleads. Related to AI-4 (both are wrong-message bugs).

**Status:** ⚠️ PARTIAL (commit 37522b1). The message half is fixed — UNSUPPORTED_OPERATION now surfaces refusal.detail. The "everything about X" mis-routing to UNSUPPORTED_FILTER is a separate parser fix, deferred.

---

### AI-1 (addendum) 🔴 verified (BUG) — Child-as-count confirmed for PO schedules & distributions; prose/table inconsistency

**Set:** 02_purchase_order
**Prompts:** `Show PO 2144 and its schedules` · `Show PO 2144 and its distributions` · `Show PO 2144 and its lines`

**Actual output** (schedules example):
Table: `Schedules  : 2`
Prose: "It includes two schedules, both shipping to Seattle with a requested delivery date of 2014-12-01. For the first schedule, 1 of 1 item was received and 33000.00 of 33000.00 was billed. For the second schedule, 1 of 1 item was received and 8250.00 of 8250.00 was billed."

**Problem:** confirms AI-1 reproduces for PO lines, schedules, AND distributions — all collapse to a count (`Schedules: 2`) in the table. New nuance: the synthesizer PROSE often DOES carry the child detail, while the TABLE shows only the count. So the data is not fully hidden (it leaks out in prose), but two problems remain — (1) the structured table, which is what a user scans, still shows a bare count; (2) prose and table are INCONSISTENT (prose detailed, table a number), which is confusing.

**Expected:** the table renders the child rows (e.g. schedule rows with ship-to, delivery date, received, billed), not `Schedules: 2`. This also resolves the prose/table mismatch.

**Root cause:** same as AI-1 — `display_formatters.py` renders `len(po.schedules)` / `len(po.distributions)` (lines ~533/535) instead of the child rows.

**Severity:** 🔴 — but slightly lower than first assessed, since the data does reach the user via prose. The table defect and prose/table inconsistency are still real.

**Status:** ✅ FIXED (commit 8ad9b39). Covered by the AI-1 fix.

---

### AI-6 🟡 verified (BUG) — Specific question answered with a generic summary

**Set:** 02_purchase_order
**Prompt:** `How much of PO 2144 was received?`

**Actual output:**
"Purchase Order 162352 from EIP Inc is Closed. The buyer is Gee, May. It includes two schedules, both shipping to Seattle with a requested delivery date of 2014-12-01. For the first schedule, 1 of 1 item was received and 33000.00 of 33000.00 was billed. For the second schedule, 1 of 1 item was received and 8250.00 of 8250.00 was billed."
Table: `Schedules: 2`

**Problem:** the user asked a SPECIFIC question — "how much was received?" — but the response is a generic PO+schedules summary with the received figures buried in prose. There is no direct headline answer (e.g. "PO 2144: 2 of 2 items received; 41,250.00 of 41,250.00 received"). Contrast prompt 7 ("how does invoiced compare to ordered") which routes to a dedicated compare tool and answers directly. "How much received" has no such dedicated shape, so it falls back to the generic PO display.

**Expected:** a direct answer to the received question — a received-vs-ordered summary line — rather than a full PO description the user must mine. Ideally a dedicated "received" shape mirroring the invoiced-vs-ordered compare tool.

**Root cause:** no dedicated "received" reconciliation tool; the query routes to the generic PO+schedules display, which also carries AI-1 (Schedules: 2).

**Severity:** 🟡 — data is present and correct (in prose); the defect is relevance/focus, not wrong numbers. The question isn't directly answered.

**Status:** ✅ FIXED (commit eb2fd72). Single-leg PO questions now route to the lifecycle tool (direct received-vs-ordered answer). Deferred: POHeaderId input (e.g. "PO 2144") isn't resolved to OrderNumber.

---

## Set 02_purchase_order — CLOSED

9 prompts, all ran. No NEW defects; confirms AI-1 and surfaces two positive
patterns worth emulating.

| # | Prompt | Verdict |
|---|--------|---------|
| 1 | Show PO 2144 and its lines | 🔴 AI-1 (child-as-count) |
| 2 | What is purchase order 2144 about? | ✅ correct |
| 3 | Show PO 2144 and its schedules | 🔴 AI-1 (+ prose/table nuance) |
| 4 | Show PO 2144 and its distributions | 🔴 AI-1 |
| 5 | How much of PO 2144 was received? | 🟡 AI-6 — doesn't directly answer the specific question |
| 6 | Which invoices were raised against PO 162034? | ✅ correct |
| 7 | How does invoiced compare to ordered for PO 162034? | ✅ excellent (direct, local synth) |
| 8 | How does invoiced compare to ordered for Lee Supplies? | ✅ excellent (+ honest exclusion note — REC-1 done right) |
| 9 | Purchase orders created before 2015 | ✅ correct |

**Positive patterns to emulate (not defects):**
- Prompts 7 & 8 use dedicated compare tools with LOCAL synthesis: direct,
  correct, fast, numbers computed in code not re-derived by the LLM.
- Prompt 8 already implements the REC-1 principle: it discloses "1,226
  invoices not linked to a PO and excluded" — an honest completeness note.
  This is the model for REC-1 elsewhere.

---

### AI-7 🔴 verified (BUG) — Self-contradiction: "All 25 have Site X" then "No receipts found"

**Set:** 03_ar
**Prompt:** `Show receipts for ABC Application Software at Santa Clara`

**Actual output:**
Prose: "All 25 have Site Santa Clara."
Answer: "No receipts found."
(raw output: standard_receipts: 25 record(s) — 25 real receipts fetched)

**Problem:** the response flatly contradicts itself. It fetched 25 receipts, the prose confirms all 25 match the Santa Clara site, and then the final answer declares "No receipts found." The data is present and matches the filter, yet the answer says none exist. A user is told both that 25 matched and that none were found.

**Expected:** show the 25 matching receipts (or an honest partial/advisory), not "No receipts found." The final answer must not contradict the data it just fetched and described.

**Root cause (CONFIRMED in code 2026-08-06):** `standard_receipts.py` applies
the site filter as exact string equality — `if site != customer_site:
continue`. The prompt passes `customer_site="Santa Clara"`; the pod's
`CustomerSite` value does not match that string exactly (casing/suffix), so
every row fails `!=`, `filtered` empties, and the tool returns `items=[]` →
"No receipts found." The synthesizer narrated the 25 rows from BEFORE this
drop (hence "All 25 have Site Santa Clara"); the render reports empty AFTER
it — that is the contradiction. NOT Cluster B's capped-fetch engine; a
standalone matching bug in this one tool.

**Fix:** normalize the comparison (case-insensitive; likely substring or
suffix-tolerant). MUST curl the pod first for the actual `CustomerSite` value
to choose the exact rule — the mismatch reason is inferred from code; the
value itself is not yet curl-confirmed.

**Status:** verified in code. Fix direction defined; exact matching rule
pending a pod curl. Not yet fixed. Singleton — not merged into AI-4/Cluster B.

**Severity:** 🔴 — a contradictory/false-empty answer. The user is told no receipts exist when 25 do.

**Status:** ✅ FIXED (commit 8ad9b39). Root cause confirmed in code: a field-name mismatch (receipts= vs standard_receipts=) silently dropped the records via Pydantic. Not the client-side filter machinery.

---

### AI-1 (addendum) 🔴 verified (BUG) — Child-as-count confirmed for AR invoice lines

**Set:** 03_ar
**Prompt:** `Show the AR invoice with CustomerTransactionId 300000248096352 and its lines`

**Actual output:**
Table: `Lines                 : 1`
(raw output: receivables_invoice_lines: 1 record(s) — line fetched with full detail: Description "Consultation", Quantity 1, UnitSellingPrice 39969, LineAmount 39969)

**Problem:** confirms AI-1 also covers AR invoice lines. The user asked to see the invoice's lines; the line was fetched with full detail but rendered as a count (`Lines: 1`), not as the line itself.

**Expected:** the table renders the line row (Line, Description, Quantity, UnitSellingPrice, LineAmount), not `Lines: 1`.

**Root cause:** same as AI-1 — `display_formatters.py` renders `len(inv.lines)` (line ~562) instead of the line rows.

**Severity:** 🔴 — folds into the AI-1 fix.

**Status:** ✅ FIXED (commit 8ad9b39). Covered by the AI-1 fix.

---

### AI-4 (addendum) 🔴 verified (BUG) — Partial-as-total also affects "total value of credit memos"

**Set:** 03_ar
**Prompt:** `What is the total value of credit memos?`

**Actual output:**
"Showing 25 of 2,111 credit memos. Currency: 16 USD, 4 CAD, 4 GBP, 1 EUR. Status: 21 Complete, 4 Incomplete."
Truncation: "credit_memos: 2111 total in source; 25 examined for filtering."

**Problem:** the currency and status breakdowns ("16 USD, 4 CAD...") describe only the FIRST 25 of 2,111 credit memos, but are presented as characterizing the credit memos generally. Same AI-4 defect: a sample described as if representative of the whole.

**Note — the currency-sum handling is EXCELLENT (not a defect):** the response correctly REFUSES to sum across currencies — "Not totalled: these memos span 4 currencies... A single sum across them would be a figure in no currency at all." This is exactly right and should be preserved. The defect is only that the breakdown is over 25, not 2,111.

**Expected:** the honest currency-refusal, but with breakdowns computed over the full set (or an honest "of the 25 examined" framing per AI-4 / REC-1).

**Severity:** 🔴 — folds into AI-4 (denominator honesty).

**Status:** ✅ FIXED (commit 8ad9b39). Same deterministic honest-denominator branch.

---

### AI-8 ✅ not-a-bug (verified) — Exposure ranking numbers are real pod data

**Set:** 03_ar
**Prompt:** `Rank top accounts by outstanding exposure`

**Looked like:** implausible magnitudes (165M for a gym) and open_receivables exactly equal to transactions_due for all 10 accounts — suspected aggregation error (field duplicated/fanned-out).

**Verified:** curl on the top account (Motique Gym, account 23129) returns TotalOpenReceivablesForAccount = 165,428,563.24 and TotalTransactionsDueForAccount = 165,428,563.24 — both fields, matching Spire's ranking exactly. The pod itself reports these values, including the exact equality. So the numbers are genuine demo-data values, not an aggregation defect.

**Conclusion:** Spire's exposure ranking is CORRECT — it aggregates and ranks faithfully. The huge, equal numbers are a property of the demo dataset, not a bug. No action needed.

**Status:** not-a-bug (curl-verified). Do not re-investigate.

---

## Set 03_ar — CLOSED

16 prompts (15 ok, 1 correctly refused). AR filtering, aggregates, and
compare tools are largely strong. Confirms AI-1 and AI-4; one new bug (AI-7);
one false alarm cleared (AI-8). Several exemplary behaviors.

| # | Prompt | Verdict |
|---|--------|---------|
| 1 | AR invoice + lines | 🔴 AI-1 (child-as-count) |
| 2 | AR invoices for ABC Corp Americas | ✅ correct |
| 3 | Open invoices for ABC Corp Americas | ✅ correct |
| 4 | Top 5 open invoices | ✅ correct (limit applied) |
| 5 | AR invoice + tax lines | 🔴 AI-1 (lines + tax lines as counts) |
| 6 | AR invoice + DFF values | (not deeply read — likely AI-1) |
| 7 | List recent credit memos | ✅ correct |
| 8 | Total value of credit memos | 🔴 AI-4 (sample) + ✅ excellent currency-refusal |
| 9 | Account balance for ABC App Software | ✅ correct |
| 10 | Credit memos for ABC App Software | (not deeply read) |
| 11 | Receipts for ABC App Software | ✅ correct (AccountReceipt) |
| 12 | Receipt applications for ABC App Software | (not deeply read) |
| 13 | Receipts for ABC App Software at Santa Clara | 🔴 AI-7 (contradiction, false-empty) |
| 14 | Rank top accounts by exposure | ✅ correct (AI-8 cleared by curl) |
| 15 | Receipt method distribution | ✅ excellent (full-set aggregate, local synth) |
| 16 | Lag between creation and last update | ✅ correct refusal (well-worded) |

**Exemplary behaviors to preserve (not defects):**
- Prompt 8: refuses to sum across 4 currencies, explains why. Keep.
- Prompt 15: full-set aggregate (truncated: False), local synthesis, direct.
- Prompt 16: honest, accurate refusal for an unsupported date-lag calculation, with a constructive alternative — the MODEL for how refusals should read (contrast AI-5).
- Prompt 14: correct exposure ranking (numbers curl-verified as real).

**Receipts-entity inconsistency noted:** prompt 11 → AccountReceipt; prompt 13 → StandardReceipt (both from "receipts"). Tracked under AI-7 for now; promote to its own item if it recurs in later sets.

---

### AI-9 🔴 verified (BUG) — Mixed valid+invalid columns refused wholesale (COL-03 not reached)

**Set:** 04_columns
**Prompt:** `Show supplier name and credit rating for active suppliers`

**Actual output:**
Reason:   I can look up suppliers, but not the way this question narrows them.
Solution: Narrow by country, status or name instead.
(refusal: unsupported_filter — The 'credit rating' field is not supported for the Supplier entity.)
[refused]

**Problem:** two defects in one.
(1) WHOLESALE REFUSAL of a partial-column request. "supplier name" is a valid column; "credit rating" is not. Per COL-03, this should return the valid column (name) plus an honest note that "credit rating" is unavailable — NOT refuse the entire query. The valid column is lost.
(2) WRONG REFUSAL REASON (same as AI-5). The message says "narrow by country, status or name" — but this is a missing-COLUMN problem, not a narrowing problem. The parenthetical shows the real reason ("'credit rating' field is not supported"), but the user sees misdirected advice and is NOT told which columns ARE available.

**Expected (COL-03 behavior):**
"suppliers (25) — columns: Supplier
Note: 'credit rating' is not available for suppliers. Available columns: Supplier, Status, SupplierId, SupplierNumber, CreatedBy, CreationDate, LastUpdatedBy, LastUpdateDate."
Show the valid column, name the unavailable one, list what IS available.

**Root cause (known, documented in status doc G15):** the model sets unanswerable=true on the unknown column BEFORE the deterministic COL-03 split (validation Step 4) runs, so it never reaches the honest-note path. The model refuses upstream, discarding the valid column. This is the exact limitation G15 records: COL-03's note is built and correct but unreachable when the model refuses first. Confirmed here in the overnight data.

**Severity:** 🔴 — the SME's actual P0 case (partial columns) still fails for genuinely-absent columns. Note: for columns that EXIST (e.g. the who-columns), this works — see 04_columns prompt 1, which correctly projects. The failure is specific to unknown columns triggering wholesale refusal.

**Status:** verified. Known limitation (G15). Fix requires stopping the model's upstream refusal on unknown columns — the harder, still-open piece of COL-03.

## Set 04_columns — CLOSED

8 prompts (7 ok, 1 refused). This set directly tests COL-03 column
projection. Result: projection is SOLID — every prompt rendered exactly the
requested columns. One real bug (AI-9, mixed valid+invalid refused
wholesale); AI-4 recurs on the woman-owned edge-traversal prompt.

| # | Prompt | Rendered columns | Verdict |
|---|--------|------------------|---------|
| 1 | name and status, active | Supplier, Status | ✅ correct projection |
| 2 | just the names, active | Supplier | ✅ correct |
| 3 | number and country, active | (requested cols) | ✅ correct |
| 4 | name, number, status, country | (requested cols) | ✅ correct |
| 5 | invoice number, amount, date | InvoiceNumber, InvoiceAmount, InvoiceDate | ✅ correct |
| 6 | names of woman owned | Supplier | ✅ projection; 🔴 AI-4 (partial-as-total) |
| 7 | order number and status, POs <2015 | OrderNumber, Status | ✅ correct |
| 8 | name and credit rating, active | — | 🔴 AI-9 (wholesale refusal of partial columns) |

**Regression result (positive):** the COL-03 column-projection path works
correctly — requested columns are projected exactly, extra fetched fields
are trimmed. The who-column work did not break projection.

**AI-4 recurrence:** prompt 6 (woman owned names) — "4 of 429 available, 25
examined" — the edge-traversal partial-as-total again. Folds into AI-4.

**Note:** prompts 5 & 7 have correct but token-heavy LLM prose summaries
(P7 enumerates every buyer/status in prose) — mild AI-3 flavor, not logged
separately.

---

### AI-5 (addendum) 🟡 verified (BUG) — "Narrow by country/status/name" misdirection recurs on non-filter refusals

**Set:** 05_refusals
**Prompts:** `suppliers with net 30 payment terms` (P2) · `which suppliers have the best rating` (P3)

**Actual output (both):**
Reason:   I can look up suppliers, but not the way this question narrows them.
Solution: Narrow by country, status or name instead.
(P2 parenthetical: "Filtering suppliers by payment terms is not supported.")
(P3 parenthetical: "The system does not track supplier ratings.")

**Problem:** confirms the AI-5 pattern. When a supplier query references a concept that isn't a supported filter (payment terms) or doesn't exist at all (ratings), the refusal gives the generic "narrow by country, status or name" advice. This misdirects: for P3, ratings simply don't exist — telling the user to "narrow" implies re-filtering will help, when nothing will. The accurate reason is in the parenthetical but not surfaced to the user.

**Expected:** the user-facing message should state the real reason — e.g. P3: "Supplier ratings aren't tracked in this system"; P2: "Payment terms isn't a filter I can apply to suppliers." Not generic narrowing advice.

**Contrast — the GOOD refusals in this set (preserve these):**
- P1 (contract renewals): "Contract isn't something I know about. What I do have: [lists all entities]." Accurate + helpful.
- P5 (who should we stop buying from): correctly identifies it needs qualitative judgment; offers to return records.
- P6 (PO line items): "only as part of the record they belong to. Ask for the PO and its lines together." Accurate + exact fix.
- P9 (older than 6 months): "Relative date filters not supported... use absolute dates like 'before 2015-01-01'." Precise + actionable.

**Severity:** 🟡 — refusals are correctly triggered; only P2/P3 wording misdirects. Pattern (not one-off) now confirmed across AI-5 (everything about X), AI-9 (credit rating), and here (payment terms, ratings): the "narrow by country/status/name" message is over-applied to non-filter/missing-concept refusals.

**Status:** verified. Root cause: the unsupported_filter refusal flavor's generic template is used for cases that aren't really filter-narrowing problems.

## Set 05_refusals — CLOSED

9 prompts, all refused (as designed). The key test: are refusals accurately
worded? Result: 7 of 9 are accurate and helpful; 2 (P2, P3) show the AI-5
misdirection. No wrong refusals (nothing refused that should have answered).

| # | Prompt | Refusal quality |
|---|--------|-----------------|
| 1 | contract renewals due next quarter | ✅ excellent (names all available entities) |
| 2 | suppliers with net 30 payment terms | 🟡 AI-5 (generic "narrow" advice) |
| 3 | which suppliers have the best rating | 🟡 AI-5 (ratings don't exist; misdirected) |
| 4 | suppliers with highest quality score | ✅ good (unsupported ranking) |
| 5 | who should we stop buying from | ✅ excellent (qualitative judgment) |
| 6 | show me purchase order line items | ✅ excellent (entity-vs-child, exact fix) |
| 7 | recent invoices | ✅ excellent (planner guard: requires supplier + examples) |
| 8 | List all purchase orders | ✅ excellent (planner guard: requires id/number/date + examples) |
| 9 | purchase orders older than 6 months | ✅ excellent (relative vs absolute dates) |

**Key insight for the AI-5 fix:** the PLANNER-GUARD refusals (P7, P8) are
hand-crafted, accurate, and give concrete examples — the gold standard. The
PARSER's unsupported_filter template (P2, P3) is the generic "narrow by
country/status/name" that misdirects. Fixing AI-5 = making the parser's
unsupported_filter messages as specific as the planner-guard ones (state
the real reason, don't default to narrowing advice).

**No new distinct items** — P2/P3 fold into AI-5 (addendum logged). All
refusals correctly triggered; only wording is the issue on 2 of 9.

---

### AI-4 (addendum) 🔴 verified (BUG) — Partial-as-total is pervasive across ALL edge-traversal filters + is the source of severe slowness

**Set:** 06_slow
**Prompts (all exhibit AI-4):** `Suppliers with invoice amount greater than 10000` (P1, 113s) · `which suppliers invoiced more than 50000` (P2, 84s) · `suppliers with open purchase orders` (P3, 82s) · `suppliers with no invoices in the last 6 months` (P4, 87s) · `List suppliers with a site in the US1 business unit` (P5, 55s) · `suppliers with a site in the France business unit` (P6, 34s) · `List suppliers that are small business` (P7, 32s) · `woman owned suppliers` (P8, 31s) · `which suppliers are veteran owned` (P9, 29s)

**Actual output (P1 example):**
"There are 23 suppliers with invoices over the specified amount. This is a partial result, as 25 suppliers were examined from a total of 429 available."

**Problem:** confirms AI-4 affects EVERY edge-traversal filter type — invoice-amount thresholds, classifications (small business, woman owned, veteran owned), site/business-unit, open-POs, no-recent-invoices. All report "N of 429" where N is actually of the 25 examined. AI-4 is not classification-specific; it is a property of the entire edge-traversal mechanism.

**New dimension — SLOWNESS:** these are also the slowest prompts in the entire test suite (29-113s). The slowness and the mislabeling share ONE cause: the plan fetches 25 suppliers then walks each one's child resource (invoices, classifications, sites) via a separate per-supplier pod call. 25 sequential child calls = tens of seconds; and because only 25 are walked, the count is a sample.

**This is the strongest evidence for REC-1.** These queries are simultaneously slow AND mislabeled. REC-1 (deliver the partial honestly + recommend narrowing) fixes both: the user gets an honest "25 of 429 examined" AND a suggestion to narrow (by country/status) so a COMPLETE answer needs walking far fewer suppliers — faster AND correct.

**Severity:** 🔴 — pervasive across all edge-traversal filters; compounded by 30-113s latency.

**Status:** verified. Folds into AI-4 (message fix) + REC-1 (advisory + narrowing to avoid the slow full-class walk).

## Set 06_slow — CLOSED

15 prompts, all ran, but the SLOWEST set (29-172s each). Two clear halves:
edge-traversal prompts (1-9) all exhibit AI-4 and are slow; aggregation
prompts (10-15) are correct (full-set, truncated:False) but also slow.

| # | Prompt | Time | Verdict |
|---|--------|------|---------|
| 1 | invoice amount > 10000 | 113s | 🔴 AI-4 |
| 2 | invoiced more than 50000 | 84s | 🔴 AI-4 |
| 3 | suppliers with open POs | 82s | 🔴 AI-4 |
| 4 | no invoices in last 6 months | 87s | 🔴 AI-4 |
| 5 | site in US1 business unit | 55s | 🔴 AI-4 |
| 6 | site in France business unit | 34s | 🔴 AI-4 |
| 7 | small business | 32s | 🔴 AI-4 |
| 8 | woman owned | 31s | 🔴 AI-4 |
| 9 | veteran owned | 29s | 🔴 AI-4 |
| 10 | top 10 by spend 2022 | 162s | ✅ correct (full-set aggregate) |
| 11 | spend most with 2022 | 172s | ✅ correct |
| 12 | top 5 by PO value | 99s | ✅ correct |
| 13 | how many POs + worth | 83s | ✅ correct (not deeply read) |
| 14 | committed in open POs | 13s | ✅ correct (fast — direct aggregate) |
| 15 | compare ordered vs invoiced top 3 | 145s | ✅ correct + honest exclusion notes |

**Two takeaways:**
1. AI-4 confirmed pervasive across ALL edge-traversal filters (see AI-4
   addendum). This set is the strongest evidence: 9/9 edge-traversal prompts
   mislabeled, and they're 29-113s slow — same root cause (per-supplier
   child walk over 25).
2. Aggregations (10-15) are CORRECT (truncated:False, full-set) — the
   dedicated aggregation shapes work well, just slowly.

**Performance note (for REC-1 / future optimization):** the whole set is
slow because edge-traversal and aggregation both do many sequential pod
calls. REC-1 addresses the edge-traversal half (narrow → fewer walks). The
aggregation slowness (100-170s) is a separate optimization opportunity —
the aggregate shapes fetch large sets before computing.

**Light note (not a bug):** P15's "under-invoiced by 651M" for EIP Inc is
correct but could mislead a skimming user — the 651M gap is almost entirely
2,803 non-PO-matched invoices, which IS disclosed. Framing could be
clearer; not logged as a defect.

---

### AI-9 (addendum) 🔴 verified — COL-03 note WORKS for some unknown columns but not others; wholesale refusal is inconsistent

**Set:** 07_alacarte

**CRITICAL POSITIVE (P2):** `Show me invoices for EIP Inc over 100000 with invoice number, amount, date, supplier name, supplier number, and currency`
Output CORRECTLY implements COL-03:
"Note: the following column isn't available on Invoice: 'Supplier'. Available columns: ApprovalStatus, InvoiceAmount, InvoiceCurrency, InvoiceDate, InvoiceId, InvoiceNumber, PaidStatus, PurchaseOrderNumber, SupplierNumber.
columns: InvoiceNumber, InvoiceAmount, InvoiceDate, SupplierNumber, InvoiceCurrency"
→ showed the 5 valid columns, named the invalid one ('Supplier'), listed available columns. This is EXACTLY AI-9's expected behavior — and it WORKS here.

**So AI-9 is INCONSISTENT, not uniform:** the deterministic COL-03 note fires when the model emits an Intent with the columns (P2). It FAILS only when a specific unknown column ('credit rating', P11) trips the model's upstream unanswerable flag before the split runs. So the fix scope narrows: it's not "COL-03 is broken" — it's "certain unknown column phrasings make the model refuse upstream instead of emitting the Intent." Some unknown columns (Supplier-on-Invoice) sail through to the note; others (credit rating) trigger refusal.

**NEGATIVE (P12):** `Show me invoices for EIP Inc with invoice number, PO number, and PO line number`
Refused wholesale. "PO number" is VALID on Invoice (PurchaseOrderNumber — appears in P2's available list). Only "PO line number" is invalid. Per COL-03 should show invoice number + PO number, note "PO line number unavailable." Instead refused everything (AI-9). AND the refusal reason is the WRONG template — "This needs a total, a ranking, a trend" (aggregation refusal) when the real issue (parenthetical) is "Cannot retrieve PO line number... from Invoice" — a column problem. This is AI-5 misdirection with yet a THIRD wrong template.

**Severity:** 🔴 — the SME's partial-column P0 works inconsistently: fine for some unknown columns, wholesale-refuses for others, with misdirected reasons.

**Status:** verified. Refines AI-9: the COL-03 note path works; the defect is specifically the model's upstream unanswerable-refusal on certain unknown-column phrasings (documented limitation, G15), plus AI-5-style wrong refusal templates.

## Set 07_alacarte — CLOSED

12 prompts (9 ok, 3 refused). Tests column selection + filters combined. The
KEY set for understanding COL-03 behavior: it revealed the honest-column
note WORKS (P2), refining AI-9 from "broken" to "inconsistent."

| # | Prompt | Verdict |
|---|--------|---------|
| 1 | EIP invoices >100k, 3 cols | ✅ correct projection |
| 2 | EIP invoices >100k, 6 cols (incl invalid 'supplier name') | ✅ COL-03 note WORKS — shows valid 5, names invalid, lists available |
| 3 | active suppliers name+number+status | ✅ clean projection |
| 4 | just invoice numbers, supplier 1252 | ✅ correct |
| 5 | active suppliers name+number+address | ✅ address projects as column |
| 6 | supplier 1252 name+number+address | 🔴 refused (AI-9 — but P5/P7 same shape work; inconsistent) |
| 7 | active suppliers name+number+address | ✅ works (dup of P5) |
| 8 | active suppliers | ✅ correct |
| 9 | top 5 by spend last year + cols | ✅ correct (aggregation + date + cols) |
| 10 | PO 2144 and its lines | 🔴 AI-1 (child-as-count) |
| 11 | name + credit rating | 🔴 AI-9 (wholesale refusal, unknown column) |
| 12 | EIP invoices: invoice#, PO#, PO line# | 🔴 AI-9 + AI-5 (partial refused; wrong template) |

**MAJOR insight (P2): COL-03's honest-column note WORKS.** For "supplier
name" (invalid on Invoice), it correctly showed the 5 valid columns, named
the invalid one, and listed available columns. This is exactly the designed
behavior. So AI-9 is INCONSISTENT, not uniform:
- Works: unknown columns that still let the model emit an Intent (P2's
  'Supplier' on Invoice).
- Fails: unknown columns that trip the model's upstream unanswerable flag
  (P11 'credit rating'), causing wholesale refusal before the split runs.
The COL-03 note machinery is sound; the gap is specifically the model
refusing upstream on certain phrasings (G15 limitation).

**P6 vs P5/P7 inconsistency:** P5 and P7 (identical: "active suppliers with
name, number, address") both WORK; P6 ("supplier 1252 with name, number,
address" — single supplier by id) REFUSED. Same columns, different refusal
based on single-vs-list shape. Another facet of the inconsistent upstream
refusal.

**P12:** wrong refusal template (aggregation "needs a total/ranking/trend"
for what is actually a missing-column problem) — AI-5, third variant.

---

## Set 08_lifecycle — CLOSED

31 prompts (28 ok, 3 refused). Tests the PO lifecycle/reconciliation tool
extensively — mostly the SAME two POs (701337, 162034) asked ~20 different
ways. This set is a STANDOUT for correctness and consistency. No new bugs.

**HEADLINE RESULT — perfect consistency (the architecture working):**
All ~20 differently-phrased prompts about PO 701337 return the IDENTICAL
facts: stage "Awaiting receipt", risk Medium, total 1235.00, received
398.00, invoiced 398.00, remaining 837.00, team Supplier/Receiving, paid
status "cannot be determined." Every "Risk (" line across all prompts =
"Risk (Medium)". Phrasings tested: "has it been paid?", "why still open?",
"executive summary", "what stage?", "risk rating?", "trace end-to-end",
"what's blocking?" — all converge. This is because the lifecycle tool
computes facts ONCE in code (get_purchase_order_lifecycle_status) and the
synthesizer only renders them — rephrasing can't change the numbers. Direct
evidence of the "compute in code, don't let the LLM derive" principle
working.

**Quality of the lifecycle output (exemplary):**
- Honest tri-state paid status: "the paid leg cannot be determined" (not
  falsely claiming paid/unpaid).
- Careful non-fabrication: "schedules record 398.00 billed but no invoice
  carries this PO number... paid leg is unknown rather than zero."
- Structured: risk + reasons, recommended action, supplier setup,
  outstanding lines with amounts, unresolved exceptions.

**Edge cases handled well:**
- P23 (non-existent PO 999999999): found:False, "No purchase order... was
  found." Clean, no fabrication. ✅
- P24 (DOES-NOT-EXIST): refused/handled. ✅
- P25 (all POs), P26 (compare two): correctly refused — genuinely
  unsupported (single-PO tool). Here the "needs a total/ranking/two records
  side by side" template ACTUALLY FITS (P26 is a comparison, P25 an
  aggregation) — so NOT an AI-5 misfire. ✅

**Other prompts:**
- P27 (PO 162034 and its lines): 🔴 AI-1 (child-as-count) — folds in.
- P28 (invoices against PO): ✅ correct.
- P29 (open POs for JGA): ✅. P30 (which suppliers have open POs): 🔴 AI-4
  (edge-traversal, 108s). P31 (POs before 2015): ✅.

**Net new defects: NONE.** AI-1 (P27) and AI-4 (P30) recur; both fold in.
This set is the strongest evidence that the dedicated computed tools
(lifecycle, compare) are the system's best-working component.

---

### AI-10 🔴 verified (BUG) — "Supplier sites" returns addresses, not sites (silent wrong-resource)

**Set:** 10_refusal_examples
**Prompt:** `supplier sites for Lee Supplies`

**Actual output:**
"Suppliers:
  Supplier       : Lee Supplies
  SupplierId     : 300000047414503
  SupplierNumber : 1252
  Address        : 5000 CARTER DR.,LOS ANGELES, CA 90032 LOS ANGELES (+24 more)"

**Problem:** the user asked for supplier SITES; the output shows the supplier's ADDRESSES instead. Sites and addresses are distinct Oracle resources — a site is a purchasing/pay location (e.g. "JGA Progress US", with purchasing-enabled/pay-enabled flags), an address is a physical address. The query silently returned the wrong resource. No note, no refusal — the user is shown addresses labeled as a supplier record when they asked about sites, and would reasonably believe these ARE the sites.

**Expected:** either return the supplier's site child resource (the actual sites with their BU/enabled flags), or — if sites aren't supported as a target — refuse honestly ("supplier sites aren't available as a standalone query; I can show the supplier's addresses or its business-unit sites"). Not a silent substitution of addresses for sites.

**Root cause (likely — known backlog item):** the Site resource has no proper KG representation ("Site has ZERO field rows in the KG" per prior handoff; "supplier sites mis-parses"). So "supplier sites" doesn't resolve to a site fetcher and falls back to the supplier+addresses fetch. Related to the has_site_in_bu edge-traversal (which DOES work for BU filtering) — but "show me the sites" as a listing has no home and degrades to addresses.

**Severity:** 🔴 — silent wrong-resource substitution. The user asked for X and got Y with no indication. This is exactly the "no substitution" principle (from COL-03) being violated at the resource level.

**Status:** ⏸️ DEFERRED. The AI-11 crash (sibling) is fixed (commit 37522b1); AI-10's silent sites→addresses substitution is a parser-mapping bug needing a separate parser change.

## Set 10_refusal_examples — CLOSED

19 prompts, all ran ok (none refused — despite the set name, these are
success-path prompts, largely overlapping earlier sets). Mostly confirms
known findings; one NEW bug (AI-10, supplier sites).

| # | Prompt | Verdict |
|---|--------|---------|
| 1 | active suppliers name+number+status | ✅ correct projection |
| 2 | supplier contacts for Lee | 🔴 AI-1 (contacts as count) |
| 3 | tax lines for invoice | 🔴 AI-1 |
| 4 | AR invoice by id | ✅ correct |
| 5 | PO 2144 and its buyer | ✅ correct (buyer = single record, renders fine — scopes AI-1) |
| 6 | PO 2144 and its distributions | 🔴 AI-1 |
| 7 | PO 2144 and its lines | 🔴 AI-1 |
| 8 | PO 2144 and its schedules | 🔴 AI-1 |
| 9 | invoice lines for invoice | 🔴 AI-1 |
| 10 | suppliers with their addresses | ✅ correct (addresses render) |
| 11 | risk rating PO 701337 | ✅ correct (lifecycle, consistent w/ set 08) |
| 12 | account balance ABC Corp Americas | ✅ correct |
| 13 | active suppliers in US | ✅ correct |
| 14 | credit memos for ABC App Software | ✅ correct |
| 15 | invoices for Lee Supplies | ✅ correct |
| 16 | open invoices for ABC Corp Americas | ✅ correct |
| 17 | receipts for ABC App Software | ✅ correct |
| 18 | supplier sites for Lee Supplies | 🔴 AI-10 (returns addresses, not sites) |
| 19 | suppliers with classification Minority Owned | 🔴 AI-4 (partial-as-total) |

**Useful scoping insight (P5):** "PO and its buyer" renders the buyer
correctly ("Buyer: May Gee") — NOT collapsed to a count. So AI-1 is
specifically about LIST children (lines, schedules, distributions,
contacts, tax lines), not single related records (buyer). Sharpens the
AI-1 fix scope.

**Net new: AI-10** (supplier sites → addresses, silent wrong-resource).
AI-1 (P2,3,6,7,8,9) and AI-4 (P19) recur; fold in.

---

## Set 11_column_vocabulary — CLOSED

53 prompts (44 ok, 9 refused). The most COL-03-relevant set. Result: column
vocabulary handling is STRONGER than expected — the who-column work resolves
a wide range of phrasings, including synonyms thought to be deferred.

**MAJOR POSITIVE — vocabulary/synonym resolution works broadly:**
- Case/format variants all resolve: `supplier_name`, `SupplierName`,
  `SUPPLIER NAME`, `invoice-number`, `invoice numbers` → all ok.
- Synonyms resolve: `vendor name`/`vendor number` → supplier name/number;
  `value` → amount.
- WHO-COLUMN synonyms all resolve (this is the big one):
  - `who columns`, `who details`, `audit columns` → expand to the full
    who-column set (CreatedBy, CreationDate, LastUpdateDate, LastUpdatedBy).
  - `'created by'` (natural phrasing, space) → CreatedBy ✅
  - `creation date`, `date created` → CreationDate ✅
  - `last updated` → LastUpdatedBy ✅

**KEY INSIGHT — layer 3 delivered layer 2 for free:** in the COL-03 build
session, "created by" REFUSED. Now it RESOLVES. Because the KG now holds the
who-columns as real fields, the model maps natural phrasings ("created by",
"audit columns", "date created") to the real columns. Adding the columns to
the KG (layer 3) also enabled their synonyms (layer 2) as a side effect —
the model does the phrasing→column mapping once the target columns are real
in the KG. Synonyms are more "done" than the G15 status implied.

**Refusals split into two groups:**
- Correctly refused (genuinely absent): `risk score`, `payment terms`,
  `quantum flux`, `credit rating`. Refusing is right (AI-5 wording issues
  still apply).
- Arguable gaps (refused, might reasonably resolve): `state` (P15 — in
  address data but refused; reason accurately worded this time), `business
  unit`/`operating unit` (P28/29 — relate to sites, no home; connects to
  AI-10 Site gap), `PO line number` (P42 — AI-9, partial refused wholesale).

**COL-03 mixed valid+invalid (AI-9 recurrence):**
- P46 `supplier name, credit rating, risk score, payment terms` → refused
  wholesale (only 'name' valid, lost). AI-9 — the multi-invalid-column case
  still triggers upstream refusal.
- Contrast: valid + resolvable-synonym cases (who columns) all work.

**Net new: NONE.** Strong positive for COL-03/who-columns. AI-9 recurs
(multi-invalid columns); AI-5 wording recurs on absent-column refusals; the
Site-related refusals connect to AI-10.

---

### AI-11 🔴 verified (BUG) — "Get supplier sites for suppliers" crashes (missing business_unit arg)

**Set:** qa_testcases
**Prompt:** `Get supplier sites for suppliers`

**Actual output:**
ERROR: execute: 1 validation error for call[search_suppliers_by_site_bu]
business_unit
  Missing required argument [input_value={'supplier_id': 300000047414503}]
[error — 7.5s]  (this is the exit-1 cause for the set)

**Problem:** the planner routed "supplier sites" to the search_suppliers_by_site_bu tool, but that tool REQUIRES a business_unit argument, and the prompt specifies none. The executor called it with only {supplier_id}, triggering a Pydantic missing-argument validation crash. A hard crash, not a graceful refusal.

**Relationship to AI-10:** "supplier sites" is doubly broken depending on phrasing —
- AI-10 (set 10): "supplier sites for Lee Supplies" → silently returns ADDRESSES (wrong resource, no error).
- AI-11 (here): "Get supplier sites for suppliers" → CRASHES (site-BU tool needs a business_unit that wasn't given).
Same root cause: the Site resource has no proper standalone fetcher (known KG gap — "Site has ZERO field rows in the KG"). One phrasing degrades to addresses, another routes to the BU-filter tool which then crashes on the missing required arg.

**Expected:** either a proper supplier-sites fetcher, or an honest refusal ("listing supplier sites isn't supported; I can filter suppliers by business unit if you name one"). Never a crash.

**Root cause:** search_suppliers_by_site_bu has a required business_unit arg; the planner routes bare "supplier sites" to it without one. Also the tool arg validation happens at execute time (crash) rather than plan time (which could refuse gracefully).

**Severity:** 🔴 — a user-facing crash. Also the sole exit-1 cause for the set.

**Status:** ✅ FIXED (commit 37522b1). validate_intent refuses a Site include at parse time — no crash. (AI-10, the sibling, remains deferred.)

---

### AI-12 🔴 verified (BUG) — Schedules sub-table shows raw ReceivedAmount (0.0) as fetched, contradicting the prose's ReceivedQuantity ("1 of 1 received")

**Set:** 02_purchase_order (post-fix overnight run, 2026-08-08)
**Prompt:** `Show PO 2144 and its schedules`
(also visible on `Show PO 2144 and its distributions`, which re-renders the same schedules sub-table)

**Actual output:**
Prose: "…For the first schedule, 1 of 1 Ea was received and 1 of 1 Ea was billed…"
Table:

    PO 162352 — schedules:
      Schedule | Ship To | Need-By    | Ordered | Received | Billed
      ---------+---------+------------+---------+----------+--------
      1        | Seattle | 2014-12-01 | 33000.0 |      0.0 | 33000.0
      1        | Seattle | 2014-12-01 |  8250.0 |      0.0 | 8250.0

(raw output: poschedule: 2 record(s) — each carries both ReceivedQuantity and ReceivedAmount as distinct fields)

**Problem:** the prose and the table contradict each other on the received leg. The prose says "1 of 1 received" (reading ReceivedQuantity); the table's Received column shows 0.0 (reading ReceivedAmount). A user scanning the table sees a PO received in full per the prose but showing 0.0 received in the table. This is the QA-01 child-row renderer — the sub-table itself is correct (QA-01 HELD: it renders rows, not "Schedules: 2"), but one column populates from the wrong measure.

**Expected:** the Received column must not present a raw ReceivedAmount that is structurally always 0 on this pod. Either (a) derive the received amount — Amount × ReceivedQuantity / Quantity — and label it derived, matching the lifecycle tool; or (b) show ReceivedQuantity in the column under a quantity label. Prose and table must agree.

**Verification — endpoints reference (pod-wide measurement, 2026-07-28 entries):**
- /purchaseOrderSchedules — "ReceivedAmount is 0 or null on EVERY row on this pod — checked across ~4,500 rows (offsets 0–4500). The received leg exists only as a QUANTITY. Any reconciliation reporting a received AMOUNT must DERIVE it: Amount * (ReceivedQuantity / Quantity)… Label derived figures; do not present them as fetched fields."
- /purchaseOrderSchedules — confirms the schedule row carries ReceivedQuantity, ReceivedAmount, BilledQuantity, BilledAmount alongside ordered Quantity/Amount.
So ReceivedAmount=0 is real and pod-wide; ReceivedQuantity=1 is the real received signal. The table is showing a fetched-but-meaningless zero. (Documented pod rule, not a single-row curl — the doc's own measurement supersedes a one-off curl here.)

**Cross-check — the lifecycle tool already does this correctly.** QA-07 output for the same received leg reads: "Received 398.00 (derived from quantity)" with an explicit "Received: derived from quantity — the pod carries no received amount" note. The derive-and-label rule is already implemented on the lifecycle path; the QA-01 schedules renderer is the one place it was missed.

**Root cause:** the schedules sub-table renderer in the display/synthesizer path emits the raw ReceivedAmount field as the "Received" column value. Because ReceivedAmount is 0/null pod-wide, the column is always 0 while the prose (correctly derived/quantity-based) says otherwise. Not a fetch defect — both fields are fetched correctly; a display-layer field-choice/labelling defect. Distinct from AI-1 (child-as-count); this is wrong-field-in-a-rendered-row.

**Fix (defined, not built):** in the schedules sub-table renderer, replace the raw ReceivedAmount column with either the derived received amount (Amount × ReceivedQuantity/Quantity, labelled "Received (derived)") or ReceivedQuantity (labelled "Received (qty)"). Reuse the lifecycle tool's existing derivation so the two paths agree. Confirm/add a display-formatter test for the schedules sub-table. Display-path only; no KG or tool change.

**Severity:** 🔴 — a prose/table contradiction on a money-adjacent figure. Lower blast radius than AI-1 (one column, one child type, prose carries the correct signal), but a user scanning the table is actively misled.

**Status:** verified against the endpoints reference (pod-wide measurement). Fix direction defined, not yet built. New — surfaced by the post-fix verification read; not part of the original AI-1…AI-11 census. Working label during the read: N-1.

## Set qa_testcases — CLOSED

34 prompts (12 ok, 20 refused, 1 error). QA edge-case set — heavy on
under-specified, contextual-reference, and unsupported-operation prompts.
Result: 1 real crash (AI-11), refusals broadly appropriate, no other new
bugs.

**The one crash (AI-11):** "Get supplier sites for suppliers" → Pydantic
validation crash (search_suppliers_by_site_bu missing business_unit). Sole
exit-1 cause. Connects to AI-10 (Site KG gap). Logged above.

**Refusals (20) — broadly appropriate:**
- Contextual references with no antecedent ("that invoice line", "this
  invoice", "that PO", "this account") — correctly unresolvable (no
  conversation memory). ✅
- Unsupported time-series aggregations ("cash collection trends", "receipt
  volume by month", "month-over-month movement"). ✅
- Under-specified ("Show invoices", "list purchase orders") — planner
  guard. ✅
- "Verify a newly created AR invoice" (not a query). ✅

**Possible minor gaps (refused, arguably resolvable):**
- "show details for invoice number LEE-01-1006-111" — specific invoice
  number; might reasonably resolve. Edge case.
- "invoices for US1 Business Unit" — connects to Site/BU gap.

**Note:** "Summarise receipt volume by month" appears 4× (repeated in the
set) — all correctly refused (monthly aggregation unsupported). Not an
error despite initial appearance.

**Net new: AI-11** (supplier-sites crash). Refusals otherwise sound.

---

### AI-13 🟡 verified — Supplier list returns a different 25-row sample between identical runs

**Set:** (not from the overnight run — surfaced during COL-02 multi-field-expansions verification, 2026-08-12)
**Prompt:** `List active suppliers with supplier name and audit columns`
(any active-supplier list prompt; the synonym is incidental)

**Actual output:** two identical runs of the same prompt returned DIFFERENT
supplier samples. First three rows identical (Lee Supplies, JGA, US Gas and
Electric), then diverging:

    Run 1: ...Allied Manufacturing, Midtown Computer Supplies, Consolidated...
    Run 2: ...Staffing Services, Dell Inc., InterChina, Howell Engineering...

Both report "Showing 25 of 284 suppliers", both HTTP 200, both a valid 25-row
table. The parse was byte-identical (out=401 both runs) and the Intent
identical, so the divergence is downstream of parse.

**Expected:** identical prompt → identical rows, or an explicit statement that
the sample is arbitrary. A user comparing two runs sees a different supplier
set with no indication why.

**Verification (curl, 2026-08-12):** the raw `/suppliers` endpoint is STABLE —
the pod is NOT the source of variance.

    # Two identical calls, limit=25, no q=
    curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
      "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/suppliers?limit=25&fields=Supplier" \
      -w "\nHTTP %{http_code}\n"
    # -> HTTP 200, 25 suppliers, first = Lee Supplies
    # diff of the two supplier lists: IDENTICAL ORDER

    # Repeated at limit=200:
    # -> HTTP 200, 200 suppliers, diff: 200-ROW ORDER IDENTICAL

So the raw endpoint returns a stable order at both limit=25 and limit=200,
across repeated calls. The variance is therefore NOT the pod ordering (unlike
`/standardReceipts`, which the reference documents as unordered — this endpoint
differs) and NOT the parser/expander (identical Intents).

**Root cause (suspected, not yet code-traced):** isolated to Spire's
client-side supplier handling between fetch and render. The supplier path
applies `Status='ACTIVE'` client-side (the pod's `q=Status` is unreliable — see
endpoints reference 2026-05-22) over an over-fetch, then samples/truncates to
25. A sample or truncation step that is not order-stable would produce a
different 25 each run even though the underlying fetch is stable. Needs a code
trace of the supplier fetch/filter/truncate path to confirm the exact step.

**Fix (direction, not built):** make the supplier sample deterministic — apply
a stable sort key (e.g. SupplierId) before the client-side ACTIVE-filter and
the 25-row cut, so the same prompt yields the same rows. Relates to OUT-06's
caution that a capped fetch must be ordered to be reproducible. Confirm against
the fetch path first; do not assume the truncation step is the culprit without
a trace.

**Severity:** 🟡 — not wrong data (every row returned is a real active
supplier), but a reproducibility defect: identical input gives different
output with no disclosure. Affects EVERY supplier list, not just synonym
queries. Pre-existing; not introduced by COL-02.

**Status:** verified (pod stability curl-confirmed; Spire-side root cause
suspected, code trace pending). New — surfaced during COL-02 verification, not
part of the AI-1…AI-11 overnight census. Working label during the session:
N-2.