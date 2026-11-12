# SPIRE — window-36 handoff

**Window type:** design + investigation + one reverted attempt.
**Zero feature commits merged in this window.** `master` has moved
since this window's open: PR #203 merged at `2a23906`, PR #204
merged at `850feb5`, and two docs commits followed (`05d7978`
froze supplier.md; `983a7fb` handed STATUS.md off to PR #3).
Current tip `983a7fb`.

**Working tree at close:**

    $ git status --porcelain
     M docs/plan/HANDOFF.md

One file modified: this handoff. Nothing else. The trial branch
`Phase3-SampleAndDisclose` was created and deleted (zero commits);
the files touched on it (`parser.py`, `planner.py`, `narrowing.py`)
were reverted before any commit. `git status` is the evidence.

**Predecessor:** the window-35 handoff (Invoice status filters, PR
#192). That window's work is intact on `master`; nothing in it is
touched by this one.
**master tip:** `983a7fb` (two PR merges and two docs commits ahead of
this window's open)
**Successor:** the next window's handoff.

---

## 0. What this window did

Nothing was merged. Two activities, both recorded in this document
because there is no separate artifact:

1. **A promptkit run analysis.** Three prompts against
   `fa-esll-saasfademo1` (`get po with distribution details`,
   `end-to-end summary of PO 701337`, `Is PO 162034 complete?`).
   Four candidates walked through S0–S11, three closed as
   not-a-bug, one pass, zero bugs. The full walk is in §5 below,
   not in a separate file — a `docs/plan/PROMPTKIT_2026-11-10_promptkit_run.md`
   was proposed earlier in this window and **was not created**.
   The next window that wants the analysis reads §5.

2. **A reverted attempt at the sample-and-disclose feature.** The
   window's design work produced a branch, a new module, and edits
   to `parser.py` and `planner.py`. All were reverted when a grep
   showed the narrowing-tip portion of the feature already exists
   on `master`. See §2 and §4 below. Nothing survives on disk.

---

## 1. The defect this window leaves open

`get po with distribution details` refuses. It is a Rule 28 defect.

- An SME reading the prompt answers it (asks "which PO?", produces a
  sample).
- Spire refuses with `missing_identifier`.
- That refusal is not the right answer.

**Root cause (`file:line`):**

- `src/spire/nl_parser/parser.py:121` — `_is_explicit_po_list` is the
  only extractor that sets `intent.list_all`, and it fires only on
  explicit list verbs ("list purchase orders", "show all POs"). It
  does **not** fire on "get po with distribution details" because
  there is no "list" verb. That is why the prompt refuses.
- `src/spire/planner/planner.py:211` — the `not intent.filters and
  not intent.list_all` guard. Correct by design; the fix is to make
  the parser set `list_all` for the child-entity shape, not to change
  the guard.

**Do not confuse this with the narrowing tip.** The tip already exists
(see §2). It is inactive for `get po with distribution details` because
that prompt never produces a `PurchaseOrderResponse` — it refuses before
the synthesizer runs. The tip and the defect are orthogonal: the tip
makes a sample legible; the defect prevents a sample being produced at
all.

---

## 2. What already exists on `master` — the narrowing tip

The window's central discovery: **the QA-12 narrowing tip is already
implemented on `master`.** It is Supplier-only today. The exact
footprint, from
`grep -rn 'narrowing_tip\|build_narrowing_tip' src/ --include='*.py'`:

| File:line | What |
|---|---|
| `p2p.py:317` | `narrowing_tip: str = Field(...)` on `SupplierResponse` |
| `p2p.py:1272` | `build_narrowing_tip(filter_types, total, entity_label='suppliers')` |
| `p2p.py:~1260` | `_SUPPLIER_FILTER_LABELS` — the label map |
| `synthesizer.py:160` | `from ...p2p import build_narrowing_tip` |
| `synthesizer.py:733, 813, 866` | three call sites, all `SupplierResponse` returns |
| `formatters.py:169` | render branch: `─── Tip ───` above the table |

**Signature already entity-agnostic:** `filter_types: set[str]`,
`total: int | None`, `entity_label: str = "suppliers"`.

**The one thing that limits it to Supplier:** inside the function,
`labels = [_SUPPLIER_FILTER_LABELS.get(ft, ft) for ft in filter_types
if ft in _SUPPLIER_FILTER_LABELS]`. The `if ft in
_SUPPLIER_FILTER_LABELS` drops any filter type not in the Supplier
map. For a `PurchaseOrder` filter set like `{status, supplier,
created_before}`, the tip would name only `status`.

**What the extension requires:**

- One field per response type on the six non-Supplier response types.
- One `labels_map: dict[str, str] | None = None` parameter on
  `build_narrowing_tip`, defaulting to `_SUPPLIER_FILTER_LABELS`
  (backwards-compatible; three existing Supplier call sites unchanged).
- One new `_*_FILTER_LABELS` dict per entity beside the Supplier one.
- One tip-computation block in each entity's plain-list branch of
  `synthesize_response`.

That is roughly 150 lines of copy-paste-shaped work across
`p2p.py` and `synthesizer.py`. Not a design.

**What the tip does not fix.** Extending it to `PurchaseOrder` still
leaves `get po with distribution details` refusing — the parser does
not set `list_all` for that prompt (§1). Tip and defect are two
separate, small PRs.

---

## 3. The design decision for the next window

**How does the parser recognize the child-entity sample shape?**

Two shapes for the parser-side fix, both small:

- **Extend `_is_explicit_po_list`** — add the "all" trigger and a
  child-entity pattern to the existing function. One function, one
  call site. The name becomes inaccurate.
- **Add a sibling** — `_is_sampleable_po_request` alongside
  `_is_explicit_po_list`. Two functions, both called from `parse()`.
  `_is_explicit_po_list` stays honest; the sibling detects the new
  shape.

**Recommended: sibling.** The two shapes are conceptually different
("explicit list" vs "sample request because no filter was supplied")
and conflating them makes both names wrong.

**The pattern generalizes.** Same shape recurs for `Invoice`,
`ReceivablesInvoice`, `CustomerAccount`, `StandardReceipt`, and
`CreditMemo` (this last one already works — `list_receivables_credit_memos`
samples by design). For each entity: one new parser extractor (or a
table entry plus a loop), one `and not intent.list_all` in the
entity's planner guard.

**`Address` is out of scope.** `get all addresses` is not honestly
sampleable — the address is a child of Supplier, and a sample would
describe itself as "25 addresses" while meaning "addresses of the
first 25 suppliers". The current refusal for `get all addresses` is
correct.

---

## 4. What this window attempted and reverted — historical record

The next window needs to know what was tried, so it does not re-try it.

**Files created and deleted:**

- `src/spire/nl_parser/narrowing.py` — a parallel
  `build_narrowing_tip` + `_NARROWING_BY_ENTITY`. **Deleted.** Do not
  recreate. `p2p.py::build_narrowing_tip` already exists and is
  better (it formats totals with `{total:,}`; the parallel version
  did not).

**Files modified and reverted:**

- `src/spire/nl_parser/parser.py` — renamed `_is_explicit_po_list` to
  `_is_sampleable_entity_request`, added `_SAMPLEABLE_ENTITIES`, added
  a new extractor, updated six stale comments. **Reverted.** The
  rename churned a working file; the net behaviour change was zero.
  If the next window extends the parser, add a sibling rather than
  rename.
- `src/spire/planner/planner.py` — `SAMPLE_SIZE_FOR_LIST_ALL = 25`
  and a `setdefault("limit", 25)` / `setdefault("orderBy",
  "OrderNumber:asc")` branch. **Reverted.** The existing `list_all`
  path already produces a bounded fetch through whatever
  `_build_entity_fetcher_args` and `search_purchase_orders` do on
  `master`, and duplicating the bound risks shadowing it.

**Branch created and deleted:** `Phase3-SampleAndDisclose`. Zero
commits. Its SHA at delete time was `fa57bc2`, which is `master`'s
SHA. `git status` after the branch was deleted showed one modified
file (`docs/plan/HANDOFF.md`); nothing else.

**The process lesson** (worth the next window's muscle memory): run
`grep -rn '<feature-symbol>' src/` **before** designing the feature.
A thirty-second grep would have shown the tip already existed and the
whole design discussion would have started from the actual feature.

---

## 5. The promptkit run analysis (C-001 … C-004)

Run against `fa-esll-saasfademo1`. Three prompts, three outcomes:

| # | Prompt | Outcome |
|---|---|---|
| 1 | `get po with distribution details` | refused — MISSING_IDENTIFIER |
| 2 | `Give me an end-to-end summary of PO 701337 from supplier setup through payment.` | answered — `found: False` |
| 3 | `Is PO 162034 complete?` | answered — full lifecycle |

Three candidates raised, three closed by direct command or by reading
the existing implementation. **Zero bugs.**

**C-001 — "get po with distribution details" refuses.**

- S1: refusal of an in-scope prompt — **passes S1** (SME could answer).
- S3: mechanism — `parser.py:121` `_is_explicit_po_list` does not
  fire on this shape; `planner.py:211` guard refuses.
- S7: **not a bug in the sense of "wrong behaviour given the current
  code"** — the refusal is the correct behaviour of `_is_explicit_po_list`
  + the guard. It is a **capability gap** per Rule 28. The finding is
  that `_is_explicit_po_list` should be extended or a sibling added;
  the defect is the missing sample path, not a bug in an existing path.

**C-002 — "end-to-end summary of PO 701337" returns `found: False`.**

- S1: wrong data — *iff* PO exists. Disproved by curl.
- S6: falsifier — `q=OrderNumber='701337'` on `fa-esll-saasfademo1`
  returns `totalResults: 0`.
- S7: **closed, not-a-bug.** Shape: audit-time observation diverged.
  Pod data drift, not a code bug.

**C-003 — "Is PO 162034 complete?" passes.**

- S1: no harm. **Observation, not a candidate.**
- S6: cross-checked against
  `tests/test_po_lifecycle_tool.py::test_162034_end_to_end_is_complete_and_settled`,
  which pins the exact figures. `q=OrderNumber='162034'` on
  `fa-esll-saasfademo1` returns the record with `POHeaderId: 1`,
  `Ordered: 758.00` — matches. **Pass.**

**C-004 — the refusal Example `What is the risk rating on PO 701337 and why?`.**

- S1: refusal of an in-scope prompt — *iff* the Example refuses.
- S3: `capability.py:_IDENTIFIER_GUIDANCE["PurchaseOrder"]` — the
  Example is correct against `dev37` (reference §13.4) and correctly
  resolves to "PO not found" on `fa-esll-saasfademo1` where PO
  701337 does not exist.
- S7: **closed, not-a-bug.** Same pod drift as C-002.

**Observations.**

- **O-1** — `capability.py::_IDENTIFIER_GUIDANCE` Examples are
  "promised" but `test_every_promised_example_is_verifiable` checks
  presence, not runnability. Accurate — not a code bug, a doc-accuracy
  question.
- **O-2** — prompt-set anchors are pod-specific; the sweep does not
  disclose which pod it ran against. A future promptkit sweep should
  add a pod-identity line to its summary.
- **O-3** — `fa-esll-saasfademo1` is a fourth pod (neither `dev37`
  nor `euth-dev20` nor `etaj`). Row counts and anchor census
  recorded here for reference: `/purchaseOrders` `totalResults: 3367`;
  `701337` absent; `162034` present; `162352` present; `2144` is a
  `POHeaderId` on this pod, not an `OrderNumber`, so
  `q=OrderNumber='2144'` returns 0 (category error, not a missing
  anchor).

---

## 6. Next window's picks

In order:

1. **Run the ground-truth grep** before designing anything:

       grep -rn 'narrowing_tip\|build_narrowing_tip\|_is_explicit_po_list' src/ --include='*.py' | grep -v __pycache__

   If the output matches §2, `master` has not moved and this handoff
   is current. If it differs, correct this handoff before proceeding.

2. **Decide the parser-side shape (§3).** Extend or sibling.
   Recommendation: sibling.

3. **Fix C-001 as a small PR.** One new sibling extractor in
   `parser.py`, one `and not intent.list_all` in `planner.py`,
   one new test. Three files, ~40 lines, one test. That closes the
   actual defect.

4. **Extend the narrowing tip to `PurchaseOrder`** as a second small
   PR (§2). Field on `PurchaseOrderResponse`, `labels_map` parameter,
   tip block in the `PurchaseOrder` branch of `synthesize_response`.
   ~40 lines across two files.

5. **Extend tip and sample to the other five entities** as follow-up
   PRs, one entity per PR. Same shape each time.

   The plan for that extension is in `docs/plan/MEETING_2026-11-10_sample_and_disclose.md` §6 — seven PRs, one per entity, with the five-by-five review discipline and the evidence-file-per-PR requirement.
6. **Add a pod-identity line to `promptkit.py`** (O-2). One line in
   the summary output naming the pod and its `/purchaseOrders` row
   count. A promptkit sweep against `dev37` and one against
   `fa-esll-saasfademo1` currently produce indistinguishable "N/N
   passed" summaries.

---

## 7. Files and prior reading

**Anchor docs:**

- `docs/design/INVOICE_STATUS_ACCEPTANCE.md` — the Rule 28 acceptance
  criterion and design shape from window 35.
- `docs/plan/WORKING_STYLE.md` — §15.3 (patch delivery), §1 (bundles),
  Rule 28 (SME test). All three were tested this window; §1 was
  violated repeatedly (individual files requested one at a time
  instead of bundles). The handoff records that so the next window
  does not repeat it.

**Key code paths:**

- `src/spire/nl_parser/parser.py:121` — `_is_explicit_po_list`.
- `src/spire/nl_parser/parser.py:807` — the wiring that sets
  `intent.list_all`.
- `src/spire/planner/planner.py:211` — the PurchaseOrder guard.
- `src/spire/synthesizer/p2p.py:317` — `SupplierResponse.narrowing_tip`.
- `src/spire/synthesizer/p2p.py:1272` — `build_narrowing_tip`.
- `src/spire/synthesizer/synthesizer.py:733/813/866` — the three
  Supplier tip call sites.
- `src/spire/rendering/formatters.py:169` — the render branch.

**Evidence files (untracked, repo root or `docs/plan/`):**

- `docs/plan/t_c002_701337.json` — the curl that closed C-002.
- `docs/plan/t_o3_162034.json` — the curl that confirmed 162034 is on
  this pod.
- `docs/plan/t_pod_identity.json` — the pod identity check.

(These are the three files named in the window's earlier verification
session. Verify they exist before relying on them.)

---

## 8. What this window did NOT do

- **No code merged to `master`.** The tip extension was designed and
  reverted.
- **No branch left open.** `Phase3-SampleAndDisclose` is deleted
  (zero commits).
- **C-001 is still open.**
- **The narrowing tip is not extended.** `PurchaseOrderResponse` and
  the other five response types still lack `narrowing_tip`.
- **No pod-identity line in `promptkit.py`.** O-2 is unresolved.
- **The promptkit run analysis file was not created.** An earlier
  proposal in this window named
  `docs/plan/PROMPTKIT_2026-11-10_promptkit_run.md` as an artifact;
  it was not written. The analysis lives in §5 above. If the next
  window wants it as a standalone file, that is a first task — one
  cell 1 (write), one cell 2 (verify), one commit.
- **The five `orderBy` fields were verified but not acted on.**
  `SupplierNumber:asc`, `InvoiceDate:desc`, `TransactionDate:desc`
  (AR invoice), `CustomerName:asc` (customer account), and
  `ReceiptDate:desc` (standard receipt) all sort server-side on
  `fa-esll-saasfademo1`. `PurchaseOrder/OrderNumber:asc` is confirmed
  on `dev37`. The `orderBy` table for the tip extension is fully
  determined.

---

*End of window-36 handoff.*