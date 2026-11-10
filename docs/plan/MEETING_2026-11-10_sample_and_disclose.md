# Meeting capture — 2026-11-10 — Sample-and-disclose feature

**Purpose.** A single record of the design discussion, the decisions
made, the options rejected, and the ordered steps to fix the issue
discussed with the SME. Not a handoff; the handoff is
`docs/plan/HANDOFF.md`. This file is what a session reads to understand
*why* the handoff says what it says.

**Participants.** SME (Fusion procurement/AR), Spire developer, AI
session (this window). The SME conversation is quoted in §1.

**Window.** Window 36. Zero commits merged. The design work happened;
the implementation did not, because the first attempt duplicated a
feature already on `master`.

---

## 1. The SME conversation, quoted

The SME's ask, verbatim (from the meeting):

> "get po with distribution details" — an SME would answer it. Spire
> refuses it. That is a defect.

> Usually what SMEs do is they upload into the Excel sheet and then
> they start filtering it. If it has some 20,000 records, they will
> upload or export 20,000 records to Excel and then they start filtering
> in Excel. That is a manual job. […] Instead of extracting all the
> views from the system and then doing it manually, why can't you ask
> the same filter […] based on the center, account, supplier, currency,
> RBU, or some kind of segments, based on some kind of date?"

> "The best thing would be this: we should make the user always be
> happy with the query that he is making. Let's just fire. […] Instead
> of getting all the POs from the system, print the first 25 and then
> say, 'Because you asked for both system POs, it doesn't make any
> sense to read all the POs. Instead you can apply some kind of filters
> so that I can give you the refined data that is more useful for
> you.'"

> "If Spire can print that kind of message along with the latest 25
> records, that makes more sense. The user might feel a good factor. At
> the same time he's getting data and a message to filter it out."

That is the ask: **fire the query anyway, bound the sample, disclose
the sample, tell the user how to narrow.** The SME's reasoning is
correct, and it is the frame all decisions below derive from.

---

## 2. The scope decision — not POs specifically

The SME's phrasing ("get po with distribution details") is one example
of a general shape:

> **"get all \<entity\>"** or **"get \<entity\> with \<child\>"** — where
> the prompt names a Spire-supported record type, no narrowing filter,
> and optionally a child.

The same shape recurs for every sampleable entity:

| Prompt | Entity | Sampleable? |
|---|---|---|
| `get all POs` | PurchaseOrder | yes |
| `get po with distribution details` | PurchaseOrder + PODistribution | yes |
| `get all invoices` | Invoice | yes |
| `get all AR invoices` | ReceivablesInvoice | yes |
| `get all customer accounts` | CustomerAccount | yes |
| `get all credit memos` | CreditMemo | already samples |
| `get all receipts` | StandardReceipt | yes |
| `get all suppliers` | Supplier | already samples |
| `get all addresses` | Address | **no** — see §4 |

**Seven entities in scope.** Address is out (§4).

---

## 3. What already exists on `master` — the narrowing tip

The central discovery of this window. The tip feature does **not** need
to be designed; it exists. Footprint, from the ground-truth grep:

| `file:line` | What |
|---|---|
| `p2p.py:317` | `narrowing_tip: str = Field(...)` on `SupplierResponse` |
| `p2p.py:1272` | `build_narrowing_tip(filter_types, total, entity_label='suppliers')` |
| `p2p.py:~1260` | `_SUPPLIER_FILTER_LABELS` — the label map |
| `synthesizer.py:160` | `from ...p2p import build_narrowing_tip` |
| `synthesizer.py:733, 813, 866` | three call sites, all `SupplierResponse` returns |
| `formatters.py:169` | render branch: `─── Tip ───` above the table |

**Signature already entity-agnostic.** The function takes
`filter_types: set[str]`, `total: int | None`, `entity_label: str =
"suppliers"`. It does not know which entity it serves.

**The one thing that limits it to Supplier.** Inside the function:

    labels = [
        _SUPPLIER_FILTER_LABELS.get(ft, ft)
        for ft in filter_types
        if ft in _SUPPLIER_FILTER_LABELS
    ]

The `if ft in _SUPPLIER_FILTER_LABELS` drops any filter type not in the
Supplier map. For `PurchaseOrder` (whose filters are `status`,
`supplier`, `created_before`, `created_since`, `updated_*`, `by_id`),
the tip would name only `status`. That is worse than no tip — it looks
complete and is not.

**The extension is small.** Roughly 150 lines across `p2p.py` and
`synthesizer.py`:

- One `narrowing_tip` field per response type on the six non-Supplier
  response types.
- One `labels_map: dict[str, str] | None = None` parameter on
  `build_narrowing_tip`, defaulting to `_SUPPLIER_FILTER_LABELS`
  (backwards-compatible; three existing Supplier call sites unchanged).
- One new `_*_FILTER_LABELS` dict per entity beside the Supplier one.
- One tip-computation block per entity's plain-list branch in
  `synthesize_response`.

**What the tip does not fix.** Extending the tip to `PurchaseOrder`
still leaves `get po with distribution details` refusing — the parser
does not set `list_all` for that prompt (§5). Tip and defect are two
separate small PRs.

---

## 4. Options considered and rejected

### 4.1 Refusing the prompt (the current behaviour)

**Rejected.** Rule 28: an SME could answer, so Spire must answer. The
current `missing_identifier` refusal is the defect, not the fix.

### 4.2 Full scan, no bound

**Rejected.** `fa-esll-saasfademo1` carries 3,367 POs; `fa-esll-dev37`
carries 15,839. A full scan of a large collection is slow, dumps
thousands of rows into one answer, and is not what the SME asked for.
The SME's own framing is "print the first 25 and tell the user how to
narrow."

### 4.3 Client-side filter — extend `Intent.filters` with a `sample` flag

**Rejected.** The parser already has `Intent.list_all: bool`. Adding a
parallel `sample` field would create two flags that mean nearly the
same thing and would force every consumer to check both. `list_all`
grows a meaning, not a name.

### 4.4 New `RefusalFlavor.SAMPLEABLE`

**Rejected.** The flavor vocabulary has six values and has been stable
for months. A sample request is not a refusal — the prompt is answered,
not declined. Conflating them would make `capability_message` need a
"you can answer this" branch, which contradicts the function's name.

### 4.5 Rename `_is_explicit_po_list`

**Rejected.** The rename churns a working file, changes zero behaviour,
and makes the function's name disagree with its docstring. Extension
is a sibling function, not a rename (§5).

### 4.6 `Address` in scope

**Rejected.** `get all addresses` cannot be honestly sampled: the
address is a child of Supplier, so a sample of "all addresses" is
really "addresses of the first 25 suppliers", which reads as 25
addresses but means ~625. The current refusal is correct. Improve
the refusal's wording if anything; do not add it to the sample set.

### 4.7 Per-run promptkit file

**Rejected.** `docs/plan/PROMPTKIT_2026-11-10_promptkit_run.md` was
proposed earlier in the window. It was not created, and it is not
needed. The promptkit analysis for this window is in `HANDOFF.md`
§5. A per-run file duplicates the handoff and drifts.

---

## 5. The actual defect, and its fix

### 5.1 Root cause

`src/spire/nl_parser/parser.py:121` — `_is_explicit_po_list` is the
only extractor that sets `intent.list_all`, and it fires only on
explicit list verbs ("list purchase orders", "show all POs"). It does
**not** fire on "get po with distribution details" — no "list" verb.

`src/spire/planner/planner.py:211` — the guard `not intent.filters and
not intent.list_all` refuses. Correct by design. The fix is to make the
parser set `list_all` for the child-entity shape; the guard stays.

### 5.2 The fix — sibling extractor

Add a sibling to `_is_explicit_po_list` in `parser.py`:

    def _is_sampleable_po_request(prompt: str) -> bool:
        """True when the prompt asks for a PO sample with a child,
        without naming a specific PO. Sibling to _is_explicit_po_list;
        that function detects explicit "list POs" verbs, this detects
        "get PO with <child>" / "all POs with <child>" shapes.
        """

Wire it in `parse()` alongside the existing call:

    if intent.target_entity == "PurchaseOrder":
        intent.list_all = (
            _is_explicit_po_list(prompt)
            or _is_sampleable_po_request(prompt)
        )
        if _is_sampleable_po_request(prompt):
            for child in ("PODistribution", "POSchedule", "PurchaseOrderLine", "Buyer"):
                if child in _detected_children(prompt) and child not in intent.include:
                    intent.include.append(child)

The child-detection helper `_detected_children` is a small substring
matcher over the known child words. It is the same shape as the
existing `_CHILD_INCLUDE_WHEN_PRESENT` logic in
`src/spire/nl_parser/vocabulary.py::add_child_include_from_prompt` —
that helper is the model to copy, not a new design.

### 5.3 Why sibling, not rename

`_is_explicit_po_list` is honest about what it detects. Conflating "the
prompt says 'list'" with "the prompt asks for a sample because no
filter was supplied" into one function makes the function's name wrong
for half its inputs and its docstring wrong for the other half. Two
functions, two names, two callers of a shared `intent.list_all = ...`
line. That is what the meeting concluded.

---

## 6. Work sequence — five by five, one PR per step

The user's direction: "we have decided to pass 5 by 5 and the testing
branch in everything to capture everything." Read literally, that is
seven entities in two batches. Read carefully, it is one PR per entity,
seven PRs, each independently reviewable. The meeting chose the second
reading, because:

- The two-entity batches would be two PRs of ~150 lines each; a single
  PR of one entity is ~30 lines and easy to review.
- Each PR is independently revertable.
- A bug in entity #4 does not block merge of entities #1–#3.
- The "capture everything" direction is satisfied by one evidence file
  per PR (see §7), not by batching.

The order, one PR per step, branch `Phase3-SampleAndDisclose-<entity>`
for each:

| # | Entity | Branch | Change | Verify |
|---|---|---|---|---|
| 1 | PurchaseOrder | `Phase3-PurchaseOrder-Sample` | Sibling extractor in `parser.py`; `narrowing_tip` field on `PurchaseOrderResponse`; `labels_map` parameter + `_PURCHASE_ORDER_FILTER_LABELS` in `p2p.py`; tip block in `synthesize_response`'s PO branch | Live run: `get all POs` and `get po with distribution details` both answer with 25 rows + tip |
| 2 | Supplier | `Phase3-Supplier-Sample` | Extend `_is_sampleable_supplier_request`; planner guard; `labels_map` reuse; tip block | `get all suppliers` answers with tip (was already sampling without tip) |
| 3 | Invoice | `Phase3-Invoice-Sample` | Extend extractor; `sample_all=True` arg on `search_invoices`; `narrowing_tip` on `InvoiceResponse`; tip block | `get all invoices` answers with 25 rows + tip |
| 4 | StandardReceipt | `Phase3-StandardReceipt-Sample` | Extend extractor; `sample_all=True` on `search_standard_receipts`; field on `StandardReceiptResponse`; tip block | `get all receipts` answers with 25 rows + tip |
| 5 | CreditMemo | `Phase3-CreditMemo-Sample` | Extend extractor; `narrowing_tip` field on `CreditMemoListResponse`; tip block (tool already samples) | `get all credit memos` answers with 25 rows + tip |
| 6 | ReceivablesInvoice | `Phase3-ReceivablesInvoice-Sample` | Extend extractor; **new tool** `search_receivables_invoices`; field on `ReceivablesInvoiceResponse`; tip block | `get all AR invoices` answers with 25 rows + tip |
| 7 | CustomerAccount | `Phase3-CustomerAccount-Sample` | Extend extractor; **new tool** `search_customer_accounts`; field on `CustomerAccountResponse`; tip block | `get all customer accounts` answers with 25 rows + tip |

The two `**new tool**` steps are the largest; everything else is
copy-paste-shaped work extending a pattern the first PR establishes.

**`Address` is not in the table.** Out of scope per §4.6.

**The order is by simplicity, not by entity importance.** PurchaseOrder
first because it is the SME's anchor; Supplier second because its guard
is already lenient; Invoice third; then Receipt/CreditMemo (both tools
already sample or nearly sample); then the two new-tool entities last,
so the pattern is proven five times before the two new tools are
written.

---

## 7. "The testing branch captures everything" — what that means

For each of the seven PRs:

1. **Branch off `master`.** `git checkout -b Phase3-<Entity>-Sample`.
2. **Open the evidence file first**, before any code:
   `docs/phase-3/sample_and_disclose/<entity>.md` from a template.
   V0 (the one-sentence fix statement) is committed before the fix
   lands. Same discipline as `FIX_PLAN.md` §8 step 1.
3. **Write the test first, commit it, run it, see it fail** on the
   current tree. The failing commit is the regression-test evidence
   base.
4. **Write the fix.** Smallest change that makes the test pass.
5. **Run V0–V9** (from `FIX_PLAN.md` §6). Record each output in the
   evidence file. V1–V7 required; V8 (N≥20) if the parser changes; V9
   (`--validate`) if a `.sysprompt` changes.
6. **Run the live prompt** twice — once on `fa-esll-saasfademo1` (the
   current pod), once against whichever pod the reference measures
   (`fa-esll-dev37`, when reachable). The two runs are the evidence
   that the fix is not pod-specific.
7. **PR.** Template in §11 of `FIX_PLAN.md`. The evidence file is
   linked from the PR body.
8. **Merge.** Freeze the evidence file (`State: closed`).

That is the "capture everything" the user asked for: **one evidence
file per PR, committed before the fix, closed after the merge, never
edited after.** Each PR is a self-contained record of what was claimed,
what was tested, what passed, and what merged. Seven PRs, seven
evidence files, seven merges.

The evidence files live under `docs/phase-3/sample_and_disclose/` —
one subdirectory per phase, one file per PR. They are not
`docs/audit/findings/` files, because there is no F-NNN to file (the
defect is a capability gap, per §5.1). They are the record of a
capability being added, not a bug being fixed.

---

## 8. Open questions — to resolve during implementation

1. **The sample size (25).** SME asked for "the first 25". `search_purchase_orders`
   defaults to `limit=25`. Whether to hardcode 25 in the extractor or
   derive it from the fetcher's default is a small choice — the
   meeting leaned toward *not* hardcoding it in the parser, so the
   sample size is a property of the fetcher.
2. **Deterministic ordering.** A sample must be reproducible
   run-to-run; otherwise two `get all POs` calls produce different
   rows. `PurchaseOrder/OrderNumber:asc` is confirmed. The five other
   `orderBy` fields were verified this window:
   `SupplierNumber:asc`, `InvoiceDate:desc`, `TransactionDate:desc`
   (AR invoice), `CustomerName:asc` (customer account),
   `ReceiptDate:desc` (standard receipt). All confirmed on
   `fa-esll-saasfademo1`. `PurchaseOrder/OrderNumber:asc` confirmed on
   `dev37` (reference §16.4).
3. **The tip on a *complete* sample.** On a pod with 12 credit memos,
   `get all credit memos` returns all 12 — not truncated. The tip's
   "narrow with a filter" line is noise there. Two template branches:
   the truncated variant (§3) and the complete variant ("You asked for
   all credit memos. Here are all 12."). The `build_narrowing_tip`
   function already returns "" when `total` is None; add a branch for
   `total <= row_count` in a follow-up if the noise shows up in
   practice.
4. **`labels_map` parameter vs `_*_FILTER_LABELS`-per-call.** The
   meeting leaned toward a `labels_map` parameter — one function, one
   caller decides the labels. That is the shape this document describes.
5. **Where the tip computation lives for the two new tools.** The
   existing three Supplier call sites are in `synthesize_response`
   branches. If the new tools' branches don't fit that shape, the tip
   may need to move into a `build_purchase_order_response()` helper.
   To be decided when the first new-tool PR is written.

---

## 9. What is not in scope, explicitly

- **Address sampling.** §4.6.
- **A `sample` flag parallel to `list_all`.** §4.3.
- **A new refusal flavor.** §4.4.
- **Renaming `_is_explicit_po_list`.** §4.5.
- **A per-run promptkit file.** §4.7.
- **The promptkit pod-identity line.** This is O-2 in the earlier
  promptkit run; it is a separate small PR after the seven sample PRs.
- **Any change to `mcp_server/server.py`** other than registering the
  two new tools (§6 rows 6 and 7).
- **Any change to `capability.py`.** The refusals for the non-sampleable
  entities (Address, truly under-specified prompts) stay as they are.

---

## 10. What the next window sees

Read `docs/plan/HANDOFF.md` §6. It names §6 of this file as the plan.
The next window's first command is:

    grep -rn 'narrowing_tip\|build_narrowing_tip\|_is_explicit_po_list' src/ --include='*.py' | grep -v __pycache__

If the output matches §3 of this document, `master` has not moved and
this plan is current. If it differs, this document is stale — correct
it before starting the seven PRs.

---

*End of meeting capture.*
