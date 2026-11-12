# Phase 3 — Sample-and-disclose: ReceivablesInvoice

**Branch:** `Phase3-ReceivablesInvoice-Sample`
**PR:** TBD (this file is committed before the branch exists; PR number
added when the PR is opened, per FIX_PLAN.md §8 step 8)
**State:** open
**Finding:** MEETING_2026-11-10 §6 row 6 — the sixth entity in the
seven-PR sample-and-disclose sequence. ReceivablesInvoice's
**plain-list path does NOT exist on `master` at `c8580c4`.** The entity
has one fetcher (`get_receivables_invoice_by_id`), reached only by
`by_id`; the KG's entity-level filter set is `['by_id']`; the parser
teaches no filter-less shape (every ReceivablesInvoice-rooted sysprompt
rule names `by_id`, every customer-scoped rule routes to
`CustomerAccount`); the planner guard refuses a filter-less
ReceivablesInvoice intent before Block 1; and no `kg_entity_tool` row
exists for `(ReceivablesInvoice, 'none')`. PR #6 is therefore a **real
wiring PR** — the second in the sequence after PR #1 — and V9 is
required (the first `.sysprompt` change in the sequence).

## V0 — Fix statement

PR #6 adds a filter-less AR-invoice fetcher
`search_receivables_invoices` (new file
`src/spire/mcp_server/tools/search_receivables_invoices.py`, registered
in `server.py`), inserts a `kg_entity_tool` row for
`(ReceivablesInvoice, 'none')` — the **first KG touch in the
sequence** — so the entity advertises a filter-less fetch the planner
will honour; relaxes the ReceivablesInvoice planner guard so a
filter-less intent reaches the new tool; adds a new parser helper
`_is_filter_less_receivables_invoice_request(prompt, intent)` in
`parser.py` that sets `intent.list_all=True` when the model has
already produced a filter-less `ReceivablesInvoice` intent and the
raw prompt does not carry a by-id-shaped numeric token (a number
that plausibly binds to `by_id`). **The helper does not enumerate
list verbs.** The shape the sequence samples is `filters=[]` on a
target the model has already judged in-scope; the phrasing the
user typed is not the signal, and a verb whitelist would miss
`get all AR invoices` (the brief's own canonical prompt) as
readily as it would miss any other phrasing a user invented. The
helper's disqualifier — a by-id-shaped number in the prompt — is
the ONLY prompt-level check it performs; adds a new sysprompt block
`b_ar_invoices.sysprompt` teaching the filter-less shape (with an
`order.manifest` entry after `b_ar_invoice_by_id`) and runs the V9
`--validate` sweep against all 240 prompts; adds a `narrowing_tip`
field to `ReceivablesInvoiceResponse` and a **new plain-list branch**
in `synthesizer.py` — the branch is added **before** the existing
`single_parent_shape` block (which requires exactly one parent row
and cannot fire on a 25-row sample), mirroring PR #5's CreditMemo
branch position; the branch carries a guarded `narrowing_tip=`
kwarg — **the tip ships empty by construction on this pod**
because the entity-level filter set is `['by_id']` and
`['by_id']` minus `by_id` is `{}`, so `build_narrowing_tip(set(), ...)`
returns `""`; and locks the shape with a red-then-green test at
`tests/test_sample_and_disclose_receivables_invoice.py`. The change
spans **ten source and evidence files** — one more than the
meeting row's inventory suggested, because the plain-list branch had
to be written rather than wired: see §V0-history. The field
exists for contract uniformity with the five prior entities (Supplier,
PurchaseOrder, Invoice, StandardReceipt, CreditMemo) and seeds the
future KG-filter-set PR that will add a real narrowing filter.

## V0 — history

The original V0 would have been the meeting §6 row-6 prescription
above, corrected on reading `master` at `c8580c4`. Preserved here per
the `supplier.md` §V0-history precedent so the branch's own record of
what it first claimed is not lost:

> The parser will set `intent.list_all=True` for a ReceivablesInvoice
> intent that names no narrowing filter, via a sibling extractor beside
> `_is_explicit_po_list` and `_is_sampleable_po_request`; the planner's
> existing ReceivablesInvoice path will then permit a bounded 25-row
> sample; `ReceivablesInvoiceResponse` will gain a `narrowing_tip`
> field so the sample discloses itself and tells the user how to
> narrow.

**Why it was wrong.** Read from `master` at `c8580c4`:

- The parser has **no filter-less ReceivablesInvoice shape** to extend.
  Every sysprompt rule that targets `ReceivablesInvoice` names `by_id`
  (`b_ar_invoice_by_id.sysprompt`, `b_ar_invoice_lines.sysprompt`,
  `b_ar_tax_lines.sysprompt`, `b_ar_dff.sysprompt`); every
  customer-scoped rule (`b_customer_invoices.sysprompt`,
  `b_account_receipts.sysprompt`) routes to `CustomerAccount`. There is
  nothing for a sibling extractor to detect — the parser already declines
  to produce a filter-less ReceivablesInvoice intent.
- `ReceivablesInvoiceResponse` (`ar.py:140`) carries `summary`,
  `receivables_invoices`, `truncation_notes` — no `narrowing_tip` — and
  the tip will be **empty by construction** on this pod, because the KG
  entity-level filter set for `ReceivablesInvoice` is `['by_id']`
  (confirmed by `_entity_level_filter_types().get('ReceivablesInvoice',
  set())` at `c8580c4`), so `['by_id']` minus `by_id` is `{}`.
  `build_narrowing_tip` returns `""` on an empty filter set before it
  ever inspects `total`. The field exists for contract uniformity with
  the five prior entities and seeds the future KG-filter-set PR; it will
  not fire on this pod.
- There is **no filter-less AR-invoice fetcher** on master.
  `receivables_invoice_by_id.py` is the only fetcher reached by the
  entity, and it is reached only by `by_id`. Every other
  `receivablesInvoices`-path file (`receivables_invoice_lines.py`,
  `receivables_invoice_tax_lines.py`,
  `receivables_invoice_transaction_dff.py`) is a **child** fetcher, not
  a filter-less parent fetcher.
- There is **no `kg_entity_tool` row** for `(ReceivablesInvoice,
  'none')`. The KG does not advertise a filter-less fetch the planner
  could honour, and the planner guard on `ReceivablesInvoice` refuses a
  filter-less intent before Block 1 — so even if the parser produced
  one, the plan would not be built.
- The real work is therefore a **new fetcher** plus a **new KG row**
  plus a **new sysprompt block** plus a **relaxed planner guard** — not
  an extension of an existing path. The tip field is a contract-
  uniformity addition on top.

**The correction is the finding.** The meeting row named the **new
tool** correctly (`search_receivables_invoices`) — and named the parser
extension and tip block as if they would fire. On this pod they will
not: the parser has no shape to extend, and the tip is empty by
construction. The wiring is the fetcher plus the KG row plus the
sysprompt block plus the guard.

**Second correction, from the code-bundle read + the red log.** The
first correction above named the wiring; it did not name one file
the wiring needs. The `ReceivablesInvoice` synthesizer branch that
exists on master is `single_parent_shape(outputs, (...))`, which
requires **exactly one parent row** and attaches child buckets
(lines, tax lines, DFF). A 25-row plain AR-invoice list has no
parent-plus-children shape — it falls through that branch entirely
and reaches the LLM at the bottom of `synthesize_response`.

Evidence: the red test at
`tests/test_sample_and_disclose_receivables_invoice.py::test_plain_receivables_invoice_list_builds_locally_no_llm`
fails on master with `AssertionError: synthesize_response called the
LLM on a plain AR-invoice list` — the mock LLM is reached for a
25-row bucket with no children. The failure is not a missing field;
it is a missing branch.

The fix is therefore **two synthesizer changes, not one**: a new
plain-list branch (positioned **before** the existing
`single_parent_shape` block, mirroring where PR #5's CreditMemo
branch sits relative to the CustomerAccount branch) plus the
`narrowing_tip` field the first correction already named. The
`plain_receivables_invoice_bucket` detector follows the same shape
as `plain_credit_memo_bucket` / `plain_invoice_bucket`: one bucket,
any row count, rows carry `CustomerTransactionId`. The existing
`single_parent_shape` branch stays for the one-invoice-plus-children
shape (AR-P2).

**Third correction, from the parser bundle read at V0 stage.** The
second correction added the plain-list branch in `synthesizer.py`.
Reading the parser bundle showed the branch is only half the
mechanism: `intent.list_all` is a `planner.models.Intent` field, not
a `draft.DraftIntent` field, so the model cannot set it. The
planner guard's relaxed condition — `not has_root_ref and not
intent.list_all` — therefore depends on the parser setting the flag
from the raw prompt, exactly as `PurchaseOrder`'s guard already
does (see `_is_explicit_po_list` in `parser.py`).

The sysprompt block teaches the model which phrasings are
answerable (so it produces `target_entity=ReceivablesInvoice`,
`filters=[]` instead of a `missing_identifier` refusal). The new
helper converts that filter-less intent into a list by setting
`list_all=True`. Without the block, the model refuses the canonical
prompt. Without the helper, the intent is produced but the guard
refuses it. **Both are load-bearing.** PR #6's file inventory is
therefore **eleven**, not ten: `parser.py` joins the source files.

**Fourth correction, at the same V0 stage — the helper is a
shape check, not a verb whitelist.** The third correction recorded
that the parser needs a helper to set `intent.list_all`, and named
it a sibling of `_is_explicit_po_list`. That naming carried an
implication PR #1's pattern had already made: that the helper is a
list of English list-verbs the prompt must match. **It is not, and
the sequence is worse for it.** The SME's design (`MEETING §1`) is
fire the query, bound the sample, disclose it, tell the user how to
narrow — for *any* phrasing of a filter-less request, because the
user's wording is not the signal. A verb whitelist would miss
`get all AR invoices` (the brief's own canonical prompt) unless
`get all` happened to be on the list, and would require extending
the list each time a phrasing the author did not anticipate
appears. That is a refusal waiting for the next user, which is the
class of defect Phase 3 exists to remove.

The helper's real question is: **is this a filter-less
`ReceivablesInvoice` intent that came from a genuine question about
the collection, and not from a prompt whose identifier the model
dropped?** Two conditions answer it. (a) The intent already
targets `ReceivablesInvoice` with `filters=[]` and `include=[]`.
That is the model's judgement, already made. (b) The prompt does
not carry a by-id-shaped numeric token — the one shape that binds
to `by_id` and could therefore be a dropped identifier rather than
a collection request. If both, `list_all=True`.

The name carries the correction. `_is_filter_less_receivables_
invoice_request(prompt, intent)` says what the function checks. A
sibling name like `_is_explicit_receivables_invoice_list` would
look like `_is_explicit_po_list` on the page, and the next reader
would re-read the same verb-list assumption back into it. The
function takes `(prompt, intent)` — not `prompt` alone — because
one of its two inputs is the model's already-produced intent, and
the check is about that intent's shape.

The `_is_explicit_po_list` helper has the same latent gap (`get
all POs` is not in its `_LIST_VERBS`), and that is recorded as an
out-of-scope pointer in §Deviations. Fixing it is not PR #6's to
own — it is a `parser.py` change to a `PurchaseOrder` path PR #1
V-walked without exercising, and it belongs in the queue.

This is the **fifth** such correction in six PRs. The pattern
established across PRs #2–#5 holds: the meeting's row describes a
wiring change, and master's code is nearly always either "already
samples locally, add one small shape, and one structural caveat"
(PRs #2–#5) or, as here and at PR #1, "the tool the row names does not
exist yet — the row named it correctly, and mis-described the rest."
PR #1 needed no correction because it was a genuine wiring PR whose
meeting row matched master's gap on every axis. PR #6 is the second
such PR, but with the PR #5 tip-caveat layered on top.

## Deviations

*(Populated as the V-walk runs. Empty at V0 commit.)*

### Out of scope — `_is_explicit_po_list` verb-set gap (`get all POs`)

`_is_explicit_po_list` (`parser.py`, added by PR #1) enumerates its
list verbs: `list `, `show all`, `show me all`, `all purchase
orders`, `every purchase order`. `get all` is not on the list, so a
prompt of the brief's own shape — `get all POs` — will not set
`intent.list_all=True`, and the PurchaseOrder guard will refuse it
as a dropped identifier. That is the same class of refusal PR #6's
helper exists to avoid for ReceivablesInvoice. Fixing it is a
parser.py change to a PO path PR #1 V-walked without exercising;
belongs in the queue alongside the other parser items. Not fixed
here.

### `personas.yaml` in the working tree

Local credential edit, never staged, not part of any PR.

## V-walk state

| V | Status | Note |
|---|---|---|
| V0 | **done** | opened with the meeting row's prescription; corrected on reading `master` at `c8580c4` to reflect the absent plain-list path, the empty-by-construction tip, and the new-tool shape |
| V1 | pending | reproducer — `get all AR invoices` and the `get all receivables invoices` paraphrase |
| V2 | pending | paraphrase — different trigger wording |
| V3 | pending | siblings unchanged (Supplier / PO / Invoice / StandardReceipt / CreditMemo tips) |
| V4 | pending | negative — customer-scoped AR-invoice routes to `CustomerAccount`, unscoped refusal boundary |
| V5 | pending | goldens (Intent-only) |
| V6 | pending | pytest scoped + synth blast-radius; full deferred to MCP migration PR |
| V7 | pending | red-then-green test pair |
| V8 | pending | N≥20 — parser changes, deferred alongside V6 per PRs #1–#5 |
| V9 | **required** | first `.sysprompt` change in the sequence — `--validate` against all 240 prompts |

## Not checked

TBD

## S11 — Coverage expansion

TBD
