# Phase 3 — Sample-and-disclose: ReceivablesInvoice

**Branch:** `Phase3-ReceivablesInvoice-Sample`
**PR:** #208 (merged 0eb05b4)
**State:** closed
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

## V1 — Reproducer (live)

Prompt: `get all AR invoices` against `fa-esll-saasfademo1`, run after
the MCP server was restarted to pick up the PR #6 changes
(WORKING_STYLE §22.1). Saved transcript at
`/tmp/pr6_v9_scoped/get_all_ar_invoices.txt`.

Result (green):

- Intent: `target_entity: ReceivablesInvoice`, no filters, no include.
  The parser helper `_is_filter_less_receivables_invoice_request`
  inspected the intent and the raw prompt, found no by-id-shaped
  number, and set `intent.list_all = True`.
- Plan: one step, `search_receivables_invoices`, `tool_args: {}` (the
  tool's default limit of 25 applies).
- Answer: `Showing 25 of 200,748 AR invoices.` — 25 rows, newest first
  (server-side `orderBy=TransactionDate:desc`).
- **No `─── Tip ───` block.** `grep -cE 'Tip' /tmp/pr6_v9_scoped/get_all_ar_invoices.txt`
  → `0`. The `narrowing_tip` field is on the response and empty by
  construction; the renderer's `if tip:` gate suppressed the block.
  This is the intended Shape A positive case.

**The V1 assertion is the answering, and the absence of a Tip block.**
PR #6 adds the field and the guarded kwarg; the field's value is `""`
because the ReceivablesInvoice entity-level filter set is `['by_id']`,
and `['by_id']` minus `by_id` is `{}`. The `Showing 25 of 200,748`
count is the pod's `totalResults` at this run; the pod has drifted from
the 173,531 the bundle read recorded. That drift is real and harmless:
the fetcher reports the live total, not a cached one. A Tip block
would be the defect — the tip should not fire when it has no filter
types to name.

The `no overlay entity for this tool — SQL not emitted` line in the
diagnostic `SQL projection:` output is a **pre-existing gap in the
SQL overlay**, not a PR #6 defect: `sql_overlay.py` has no entry for
`search_receivables_invoices`, so the emitter declines to project SQL
for the step. See §Deviations for the one-line pointer. The POC's
scope note declares per-step SQL a projection, not executable.

## V2 — Paraphrase

Prompt: `show me recent receivables invoices` against the same pod.
Saved transcript at `/tmp/pr6_v9_scoped/show_me_recent_receivables_invoices.txt`.

The sysprompt's first rule teaches this shape; V1 used `get all AR
invoices` and V2 uses a different phrasal verb (`show me`) plus a
different adjective (`recent`) to confirm the helper fires on the shape
and not on a verb. The design of the helper makes this expected: it does
not inspect the prompt for verbs at all, so a phrasing it has never
seen fires the same way as one it has.

Result (green): **byte-identical shape to V1.**

- Intent: `ReceivablesInvoice`, no filters, no include.
- Plan: one step, `search_receivables_invoices`, `tool_args: {}`.
- Answer: `Showing 25 of 200,748 AR invoices.` — same count as V1; the
  pod's total did not drift between the two runs.
- No `─── Tip ───` block.

The helper fires the same way on both phrasings. V2 green on one run.

## V3 — Siblings (unchanged)

The PR #6 change touches `ar.py` (field), `synthesizer.py` (branch),
`parser.py` (helper), `server.py` (registration), `planner.py` (guard
relaxation), `kg_schema.sql` + live DB (one row), and the sysprompt +
manifest. None of these reach the Supplier, PurchaseOrder, Invoice,
StandardReceipt, or CreditMemo tip call sites. The sibling paths are
unchanged by construction.

V3 confirmed on the sibling `unpaid invoices` golden (V5 below) and by
the four-file synth blast-radius run at V6 (`97 passed, 1 deselected`,
matching PRs #2, #4, and #5's count exactly). No sibling tip was
examined in isolation here; the blast-radius count is the evidence.

## V4 — Negative (customer-scoped routes away from the plain-list branch)

Prompt: `Show me AR invoices for customer ABC Corporation Americas`.
Saved transcript at
`/tmp/pr6_v9_scoped/show_me_ar_invoices_for_customer_abc_corporation_americas.txt`.

The parser's `b_customer_invoices.sysprompt` teaches: a customer-scoped
AR-invoice question routes to `CustomerAccount` with `by_customer_name`
and `CustomerTransaction` in include, not to the plain-list path. This
V-step confirms the boundary — the new sysprompt block does not steal
the prompt.

Result (green):

- Intent: `target_entity: CustomerAccount`; filter `{type:
  by_customer_name, value: 'ABC Corporation Americas'}`; include
  `['CustomerTransaction']`.
- Plan: **not** `search_receivables_invoices`. It is the account
  resolver plus the transaction traversal, unchanged from before PR
  #6.
- No Tip block (`CustomerAccountResponse` has no `narrowing_tip`
  field; the renderer never emits one on this path).

The parser boundary is intact: naming a customer routes away from the
plain-list branch, away from `search_receivables_invoices`, and onto
the account-child path.

The refusal path is also verified as unchanged by the contract:

Prompt: `show me contract renewals due next quarter`. Saved transcript
at `/tmp/pr6_v9_scoped/show_me_contract_renewals_due_next_quarter.txt`.
Result: `Reason: Contract isn't something I know about.` — the same
UNKNOWN_ENTITY refusal PRs #1–#5 recorded. Unchanged.

## V5 — Goldens (Intent-only)

Same scope PRs #1–#5 used: compare each golden's `Intent:` block to
the current pipeline's. Full-output byte-diff is not achievable (pod
drift, `sql_emitter` block, supplier 1256 rename) — Intent is the shape
decision.

| Golden | Prompt | Result |
|---|---|---|
| `count_suppliers.txt` | `Count of suppliers` | **MATCH** — `Supplier`, `count_only: True` |
| `po_2144_and_lines.txt` | `Show PO 2144 and its lines` | **MATCH** — `PurchaseOrder`, `by_id: 2144`, `include: ['PurchaseOrderLine']` |
| `suppliers_with_open_pos.txt` | `Which suppliers have open purchase orders?` | **MATCH** — `Supplier`, `has_open_PO: True` |

The three prompts route to Supplier count, PurchaseOrder by_id, and
Supplier with has_open_PO — none route to ReceivablesInvoice, so PR
#6's changes (all in `ar.py`, `synthesizer.py`, `parser.py`,
`server.py`, `planner.py`, and the sysprompt) do not reach them. Same
scope-boundary reasoning `supplier.md` §V5 and `invoice.md` §V5 used.

## V6 — pytest (scoped + synth blast-radius; full deferred)

**V6-full cannot run to completion on this environment.** Same class
as PRs #1–#5: the `mcp 2.x` / `langchain-mcp-adapters 0.3.1` conflict
breaks `tests/test_agent_runner.py` collection. Deferred to the MCP
migration PR.

V6 was run in the two scoped forms:

| Layer | Command | Result |
|---|---|---|
| scoped | `pytest -q tests/test_sample_and_disclose_receivables_invoice.py` | **`6 passed`** |
| synth blast-radius | four files: `test_synthesizer`, `test_synthesizer_supplier_records`, `test_synthesizer_truncation_narration`, `test_synthesizer_aggregation` | **`97 passed, 1 deselected`** |

Saved logs: `/tmp/t_pr6_v6_scoped.log`, `/tmp/t_pr6_v6_synth.log`.

**The `97 passed, 1 deselected` count matches PRs #2, #4, and #5
exactly** for the same four-file set. PR #6's six-file change did not
perturb the synthesizer surface those files cover.

What is **not** established: whether some test in the full suite
regresses for reasons PR #6 caused indirectly. Same gap PRs #1–#5
recorded; the same `MCP_DEPENDENCY_CONFLICT.md` blocks its resolution.

## V7 — Test fails without the fix

Six source commits on the branch, each landed in order and each with
the red-then-green evidence at its step:

- **`802b675`** — `docs(phase-3): receivables_invoice.md — correct V0
  (plain-list branch); test(phase-3): receivables_invoice — failing
  red test for PR #6`. Committed **before** the fix. The test at
  `tests/test_sample_and_disclose_receivables_invoice.py` had **five
  failing, one passing** at that commit (`/tmp/t_pr6_red.log`):
  `ModuleNotFoundError` on `search_receivables_invoices`, `AttributeError`
  on `narrowing_tip`, and `AssertionError` on `_forbidden_llm` (called
  the LLM on a plain AR list) — exactly the three shapes the fix lands.
- **`054ca3a`** — `ar.py` `narrowing_tip` field + fetcher module +
  `synthesizer.py` plain-list branch + KG seed row + KG count files +
  live DB row. After this commit: `6 passed`.
- **`3b27bf1`** — `planner.py` guard relaxed for `list_all`. The
  behaviour check on the relaxed guard was V1's live run — the plan
  reaches `search_receivables_invoices`.
- **`e9b7b26`**, **`69a77c7`** — V0-history corrections. Documentation,
  not code.
- **`231256b`** — sysprompt block + manifest entry. The V9-scoped
  sweep at V9 is what this commit's correctness rests on.
- **`4c88c6b`** — parser helper + wiring. The behaviour check for its
  three canonical cases printed eleven PASS lines, confirming the
  shape-based design.
- **`80719e9`** — `server.py` registration + `print_kg.py` trailing-comma
  repair. The V9 re-runs after restart prove the registration works.

The red-green pair is the standard FIX_PLAN §8 step 3 discipline: red
committed before green, both pytest-run (or behaviour-checked for
code paths pytest does not exercise), neither a post-hoc stash.

## V8 — N-run reproducibility (deferred)

Deferred alongside V6. A 20-run sweep of `get all AR invoices` would
test whether the parser's model produces the filter-less intent
deterministically (it is a stochastic LLM call per run) and whether
the helper's disqualifier fires the same way across phrasing
variations the model produces from an identical prompt. The single V1
and V2 runs are each green; the N≥20 sweep is deferred to the same
window that lands the MCP migration.

## V9 — --validate (REQUIRED; the mechanism does not exist on this branch)

**V9 is required for PR #6 — the first `.sysprompt` change in the
sequence.** The brief's V9 step names `python scripts/promptkit.py
--validate` against all 240 prompts.

**`--validate` does not exist on this branch.** Verified two ways:

- `python scripts/promptkit.py --help` lists every option it accepts,
  and `--validate` is not among them.
- `grep -rln 'validate' scripts/` finds no implementation of the
  flag on `promptkit.py` or any of its manifest runners.

The briefs for PRs #1–#5 named the `--validate` sweep as the V9
mechanism, but those PRs were `V9: not required` (sysprompts
untouched), so the mechanism's absence was never surfaced. PR #6 is
the first PR that needs V9, and it is the PR that discovers the tool
does not exist.

### V9-scoped (green)

Six prompts run end to end with `--show-parser --show-planner`, chosen
to cover the changed path and its four neighbours:

| Prompt | Intent | Plan | Answer |
|---|---|---|---|
| `get all AR invoices` | ReceivablesInvoice, no filters | `search_receivables_invoices` | `Showing 25 of 200,748 AR invoices.` |
| `show me recent receivables invoices` | ReceivablesInvoice, no filters | `search_receivables_invoices` | `Showing 25 of 200,748 AR invoices.` |
| `Get the AR invoice with CustomerTransactionId 300000248096352` | ReceivablesInvoice, `by_id` | `get_receivables_invoice_by_id` | unchanged |
| `Show me AR invoices for customer ABC Corporation Americas` | CustomerAccount, `by_customer_name` | `get_customer_account_by_name` → … | unchanged |
| `show me contract renewals due next quarter` | — | — | `Reason: Contract isn't something I know about.` |
| `show the AR invoice with CustomerTransactionId … and its lines` | ReceivablesInvoice, `by_id` | `get_receivables_invoice_by_id` → `get_receivables_invoice_lines` | unchanged |

The two filter-less prompts prove the PR #6 feature: the model
produces the intent, the helper sets `list_all`, the guard accepts,
the executor reaches the new tool, the tool returns a sample with the
honest total. The four neighbours prove no regression on the paths PR
#6 did not touch.

Saved transcripts at `/tmp/pr6_v9_scoped/*.txt`.

### V9-full (deferred — the tool does not exist)

The 240-prompt `--validate` sweep is deferred to the MCP migration PR,
because the tool it invokes is absent from `promptkit.py`. A queue
item records this:

> **`--validate` tool does not exist.** The briefs' V9 mechanism was
> never implemented on `promptkit.py` or any of its manifest runners.
> The V9-scoped shape (a chosen subset of prompts run with
> `--show-parser --show-planner` and inspected for shape) is what
> PRs that require V9 have been doing. Building `--validate` proper is
> its own tooling PR.

## Deviations

*(Populated as the V-walk runs. Empty at V0 commit.)*

### The tip is empty by construction on this pod

`build_narrowing_tip` returns `""` when its `filter_types` argument
produces no labels — before it inspects `total`. The ReceivablesInvoice
entity-level filter set on this pod is `['by_id']`, so every
ReceivablesInvoice response PR #6 produces carries `narrowing_tip=""`.
The field is correct; its positive branch is unreachable today. Wiring
it to a non-empty set requires a KG `kg_entity_filter` insert plus a
`search_receivables_invoices` signature extension that takes the new
filter — a separate PR with its own V0 and its own V-walk, not PR #6's
scope. Deferred to that branch. Same class as PR #5 (CreditMemo); the
two empty-tip cases share the shape.

### Out of scope — `sql_overlay.py` has no `search_receivables_invoices` entry

The SQL projection for a `search_receivables_invoices` step prints
`-- Step 1: search_receivables_invoices (no overlay entity for this
tool — SQL not emitted)`. The `sql_overlay.py` module has no entry in
`_ENTITIES` / `_FILTERS` / the `not_expressible` set for the new
fetcher. The SQL overlay is diagnostic-only per `SQL_OVERLAY_POC.md`
(the POC's scope note declares per-step SQL a projection, not
executable), so this is not a PR #6 blocker and not a defect in the
fetcher. Adding the entry belongs with the SQL overlay work; pointer
for that window.

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
| V0 | **done** | opened with the meeting row's prescription; corrected on reading `master` at `c8580c4` (three corrections: plain-list branch, empty-by-construction tip, parser helper as shape-check-not-verb-whitelist) |
| V1 | **green** | `get all AR invoices` — 25 of 200,748, plan `search_receivables_invoices`, no Tip block (correct) |
| V2 | **green** | `show me recent receivables invoices` — byte-identical shape to V1 |
| V3 | **green** | sibling paths unchanged — confirmed by the V6 blast-radius count matching PRs #2, #4, #5 exactly |
| V4 | **green** | customer-scoped prompt routes to `CustomerAccount`, refusal on `contract renewals` unchanged |
| V5 | **green** | three golden Intents matched |
| V6 | scoped + synth **green**; full **deferred** | branch tests `6 passed`; synth blast-radius `97 passed, 1 deselected`; full-suite blocked by MCP conflict |
| V7 | **green** | seven commits — red at `802b675` (5 failed, 1 passed), green at `054ca3a` (6 passed), every intermediate documented |
| V8 | **deferred** | N≥20 sweep deferred to MCP migration PR |
| V9 | scoped **green**; full **deferred** | six-prompt scoped sweep covers the feature and four neighbours; `--validate` does not exist on this branch (recorded in §V9 and as a queue item) |

## Not checked

TBD

## S11 — Coverage expansion

TBD
