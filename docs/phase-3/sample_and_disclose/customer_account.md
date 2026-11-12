# Phase 3 — Sample-and-disclose: CustomerAccount

**Branch:** `Phase3-CustomerAccount-Sample`
**PR:** — (filled when the PR is opened, per FIX_PLAN.md §8 step 8)
**State:** open
**Finding:** MEETING_2026-11-10 §6 row 7 — the seventh and last entity
in the seven-PR sample-and-disclose sequence. CustomerAccount's
**plain-list path does NOT exist on `master` at `bb86b8a`.** The entity
has one resolver (`get_customer_account_by_name`), reached by
`by_customer_name` or `by_account_number`; both require an identifier.
The KG's entity-level filter set is `['by_account_number',
'by_customer_name']` — both fetch-one. The parser teaches no filter-less
shape (all ten CustomerAccount-rooted sysprompt rules are either
customer-scoped or balance-only). The planner has **no entity guard**
for CustomerAccount, so a filter-less intent reaches Block 1 directly
and `find_entity_tool('CustomerAccount', 'none')` finds no row —
`No entity tool for ('CustomerAccount', 'none')` — which is the
failure the three live prompts in §V1 show. PR #7 is therefore a
**real wiring PR** — the third in the sequence after PRs #1 and #6 —
and V9 is required (the second `.sysprompt` change in the sequence).

## V0 — Fix statement

PR #7 adds a filter-less CustomerAccount fetcher
`search_customer_accounts` (new file
`src/spire/mcp_server/tools/search_customer_accounts.py`, registered
in `server.py`), inserts a `kg_entity_tool` row for
`(CustomerAccount, 'none')` — the **second KG touch in the sequence**
after PR #6's ReceivablesInvoice row — so the entity advertises a
filter-less fetch the planner will honour; adds a new parser helper
`_is_filter_less_customer_account_request(prompt, intent)` in
`parser.py` that sets `intent.list_all=True` when the model has
already produced a filter-less `CustomerAccount` intent and the raw
prompt does not carry an account-number-shaped numeric token (a
number that plausibly binds to `by_account_number`). **The helper does
not enumerate list verbs.** The shape the sequence samples is
`filters=[]` on a target the model has already judged in-scope; the
phrasing the user typed is not the signal, and a verb whitelist would
miss `get all customer accounts` (the brief's own canonical prompt)
as readily as it would miss any other phrasing a user invented. The
helper's disqualifier — an account-number-shaped number in the prompt
— is the ONLY prompt-level check it performs; adds a new sysprompt
block `b_customer_accounts.sysprompt` teaching the filter-less shape
(with an `order.manifest` entry after the appropriate neighbour) and
runs the V9-scoped sweep against a chosen six-prompt subset (V9-full,
a 240-prompt `--validate` sweep, is deferred — the flag does not
exist on this branch, per PR #6 §V9); adds a `narrowing_tip` field to
`CustomerAccountResponse` and a **new plain-list branch** in
`synthesizer.py` — the branch is added **before** the existing
`single_parent_shape` block (which requires exactly one parent row
and cannot fire on a 25-row sample), mirroring PR #5's CreditMemo
and PR #6's ReceivablesInvoice branch positions; the branch threads
`filtered_fields=filtered_fields` into `local_list_summary` (the
`_filtered_fields(intent)` argument `pipeline.py` supplies) so a
prompt's filter is describable in the summary; the branch carries a
guarded `narrowing_tip=` kwarg — **the tip ships empty by construction
on this pod** because the entity-level filter set is
`['by_account_number', 'by_customer_name']`, both fetch-one, so
`build_narrowing_tip(set(), ...)` returns `""`; adds an
`entity_synonym` seed row for `customer account` / `customer accounts`
to `kg_schema.sql` and regenerates
`src/spire/nl_parser/context/routing/classifier_menu.sysprompt` via
`scripts/build_classifier_context.py` — the menu currently carries
`CustomerAccount` as a bare class name with no colloquial synonyms,
which is why `list all customers` (the brief's third failing prompt)
classifies only by the substring and `show me customer accounts`
leaves the classifier with no synonym to match; adds the three new
files to `context_bundles.yaml` (bundle `mcp_server_tools`,
`parser_context`, `tests`) to keep `tests/test_bundle_manifest.py`
green; and locks the shape with a red-then-green test at
`tests/test_sample_and_disclose_customer_account.py`. The change
spans **fourteen files plus one live DB row** — four more than the
brief's inventory suggested, because the plain-list branch, the
classifier-menu regeneration, and the bundle manifest had to be
written rather than wired: see §V0-history. The tip field exists
for contract uniformity with the six prior entities (Supplier,
PurchaseOrder, Invoice, StandardReceipt, CreditMemo, ReceivablesInvoice)
and seeds the future KG-filter-set PR that will add a real narrowing
filter.

## V0 — history

The original V0 would have been the meeting §6 row-7 prescription
above, corrected on reading `master` at `bb86b8a`. Preserved here per
the `supplier.md` §V0-history precedent so the branch's own record of
what it first claimed is not lost:

> The parser will set `intent.list_all=True` for a CustomerAccount
> intent that names no narrowing filter, via a sibling extractor beside
> `_is_explicit_po_list` and `_is_filter_less_receivables_invoice_request`;
> the planner's existing CustomerAccount path will then permit a
> bounded 25-row sample; `CustomerAccountResponse` will gain a
> `narrowing_tip` field so the sample discloses itself and tells the
> user how to narrow.

**Why it was wrong.** Read from `master` at `bb86b8a`:

- The parser has **no filter-less CustomerAccount shape** to extend.
  The ten rules that mention CustomerAccount are all customer-scoped
  (`b_customer_invoices.sysprompt`, `b_account_receipts.sysprompt`,
  `b_customer_credit_memos.sysprompt`, `b_account_balance.sysprompt`,
  `b_receipt_applications.sysprompt`) or balance/open-invoices
  modifiers (`m_account_balance.sysprompt`, `m_open_invoices.sysprompt`,
  `m_aggregation.sysprompt` account-balance EXCEPTION). None teaches a
  filter-less plain-list shape.
- `CustomerAccountResponse` (`ar.py:440`) carries `summary`,
  `customer_accounts`, `truncation_notes` — no `narrowing_tip` — and
  the tip will be **empty by construction** on this pod, because the
  KG entity-level filter set for `CustomerAccount` is
  `['by_account_number', 'by_customer_name']` (confirmed by
  `_entity_level_filter_types().get('CustomerAccount', set())` at
  `bb86b8a`), both fetch-one, so `set()` is what is passed and
  `build_narrowing_tip(set(), ...)` returns `""` by its own
  `if not labels: return ""` guard. The field exists for contract
  uniformity with the six prior entities and seeds the future
  KG-filter-set PR; it will not fire on this pod.
- There is **no filter-less CustomerAccount fetcher** on master.
  `customer_account_by_name.py` is a resolver requiring `customer_name`
  or `account_number`; every other `receivablesCustomerAccountActivities`
  child fetcher (`customer_transactions.py`, `account_credit_memos.py`,
  `account_receipts.py`, `account_receipt_applications.py`) is a
  **child** fetcher keyed on the resolver's `AccountId`, not a
  filter-less parent fetcher.
- There is **no `kg_entity_tool` row** for `(CustomerAccount, 'none')`.
  The KG advertises only `(CustomerAccount, 'by_customer_name')` and
  `(CustomerAccount, 'by_account_number')`, both to
  `get_customer_account_by_name`.
- The real work is therefore a **new fetcher** plus a **new KG row**
  plus a **new sysprompt block** plus a **plain-list synthesizer
  branch** — not an extension of an existing path. The tip field is a
  contract-uniformity addition on top.

**The correction is the finding.** The meeting row named the **new
tool** correctly (`search_customer_accounts`) — and named the parser
extension and tip block as if they would fire. On this pod they will
not: the parser has no shape to extend, and the tip is empty by
construction. The wiring is the fetcher plus the KG row plus the
sysprompt block plus the branch.

**Second correction, from the synthesizer bundle read.** The first
correction above named the wiring; it did not name one file the
wiring needs. The `CustomerAccount` synthesizer branch that exists on
master is `single_parent_shape(outputs, ("AccountId", "AccountNumber",
"TotalOpenReceivablesForAccount"))`, which requires **exactly one
parent row** and attaches child buckets (transactions, credit memos,
receipts, applications). A 25-row plain CustomerAccount list has no
parent-plus-children shape — it falls through that branch entirely
and reaches the LLM at the bottom of `synthesize_response`.

Evidence: `receivables_invoice.md` §V0-history's "Second correction"
records the same defect for PR #6's AR-invoice plain-list, and the
red log there proves the shape: `AssertionError: synthesize_response
called the LLM on a plain AR-invoice list`. The CustomerAccount shape
is the same defect one entity over — the plain-list path exists on
the pod but has no synthesizer branch to build it, so the answer
falls through to the LLM.

The fix is therefore **four synthesizer changes, not one**: a
`plain_customer_account_bucket` detector (mirror of
`plain_receivables_invoice_bucket` / `plain_credit_memo_bucket` /
`plain_invoice_bucket` — one bucket, any row count, rows carry
`AccountId` and `AccountNumber`), a `build_customer_account_plain_records`
builder, a `narrowing_tip` field on `CustomerAccountResponse`, and a
**new plain-list branch** in `synthesize_response` placed **before**
`single_parent_shape`, mirroring where PR #5's CreditMemo branch and
PR #6's ReceivablesInvoice branch sit. The `single_parent_shape` branch
stays for the one-account-plus-children shape (AR-P2b, AR-P5).

**Third correction, from the `local_list_summary` docstring.** The
second correction added the plain-list branch. Reading
`local_list_summary`'s own docstring showed the branch needs one more
argument threaded through: `filtered_fields=filtered_fields`. The
docstring is unambiguous — a field may be described in the summary
only if the reader can SEE it (via `displayed_fields`, matching what
`formatters.py` renders) or has ASKED for it (via `filtered_fields`,
the argument `pipeline.py::_filtered_fields(intent)` supplies). PR
#5's CreditMemo branch and PR #6's ReceivablesInvoice branch both
pass `filtered_fields=`; PR #7 must too. Without it, a "list customer
accounts" prompt whose filter happens to be `name_fragment` or
`status` cannot describe that filter in the summary — the answer
degenerates to the count line.

**Fourth correction, from the parser bundle read.** The second
correction added the plain-list branch in `synthesizer.py`. Reading
the parser bundle showed the branch is only half the mechanism:
`intent.list_all` is a `planner.models.Intent` field, not a
`draft.DraftIntent` field, so the model cannot set it. The three
canonical prompts already produce the filter-less intent (the brief's
"WHAT IS KNOWN" is live-verified); the missing piece is the parser
setting `list_all=True` from the raw prompt, exactly as PR #6's
`_is_filter_less_receivables_invoice_request` does for
ReceivablesInvoice. The sysprompt block teaches the model which
phrasings are answerable (so the intent is produced without a
`missing_identifier` refusal, for paraphrases the model has not seen);
the new helper converts that filter-less intent into a list. **Both
are load-bearing.** The helper exists for uniformity with PR #6 and
for paraphrase protection — the three canonical prompts already work
at the intent level, but `list_all` is not set and the plan fails on
the KG lookup, not on the parser.

**Fifth correction, at the same V0 stage — the helper is a shape
check, not a verb whitelist.** The fourth correction recorded that
the parser needs a helper to set `intent.list_all`, and named it a
sibling of `_is_explicit_po_list`. That naming carried an implication
PR #1's pattern had already made: that the helper is a list of English
list-verbs the prompt must match. **It is not, and PR #6's fourth
correction established why.** The SME's design (MEETING §1) is fire
the query, bound the sample, disclose it, tell the user how to narrow
— for *any* phrasing of a filter-less request, because the user's
wording is not the signal. A verb whitelist would miss
`get all customer accounts` (the brief's own canonical prompt) unless
`get all` happened to be on the list, and would require extending the
list each time a phrasing the author did not anticipate appears.

The helper's real question is: **is this a filter-less
`CustomerAccount` intent that came from a genuine question about the
collection, and not from a prompt whose identifier the model
dropped?** Two conditions answer it. (a) The intent already targets
`CustomerAccount` with `filters=[]` and `include=[]` — the model's
judgement, already made. (b) The prompt does not carry an
account-number-shaped numeric token — the one shape that binds to
`by_account_number` and could therefore be a dropped identifier
rather than a collection request. If both, `list_all=True`.

The name carries the correction. `_is_filter_less_customer_account_
request(prompt, intent)` says what the function checks. The function
takes `(prompt, intent)` — not `prompt` alone — because one of its two
inputs is the model's already-produced intent, and the check is about
that intent's shape.

**Sixth correction, from the classifier-menu read.** The parser's
`_is_filter_less_customer_account_request` assumes the classifier has
already routed the prompt to `receivables`. That assumption is only
sound if the classifier's menu contains the phrase
`customer account(s)`. At `bb86b8a`,
`src/spire/nl_parser/context/routing/classifier_menu.sysprompt:24`
carries `CustomerAccount` as a bare class name — no `(aka: customer
account, customer accounts, ...)` synonyms — while sibling entities
(`ReceivablesInvoice`, `CreditMemo`, `AccountReceipt`, etc.) carry
several. `kg_schema.sql` has no `entity_synonym` row mapping
"customer account" / "customer accounts" to `CustomerAccount`; the
grep at `bb86b8a` finds only `entity_synonym` rows for
`AccountCreditMemo` and `AccountReceiptApplication`. That is why the
brief's third failing prompt — `list all customers` — relies on the
classifier matching the substring `customers` against the entity
descriptions rather than against a synonym; and it is why
`show me customer accounts` (a paraphrase of the brief's own second
prompt) is classified less reliably than the exact entity name.

The fix is a KG `entity_synonym` seed insert for
`customer account` / `customer accounts` and a run of
`scripts/build_classifier_context.py` to regenerate
`classifier_menu.sysprompt`. The generated menu then carries the
synonyms, and the classifier matches the phrase — not the substring —
for both canonical prompts and paraphrases.

**Seventh correction, from the bundle-manifest read.**
`tests/test_bundle_manifest.py:77` (test_every_tracked_file_is_in_a_bundle)
iterates tracked files, subtracts excluded/allowlisted paths, and
asserts every remaining file is in `context_bundles.yaml`. The four
new tracked files PR #7 adds (`search_customer_accounts.py`,
`b_customer_accounts.sysprompt`,
`test_sample_and_disclose_customer_account.py`, `customer_account.md`)
trip that test unless the yaml is updated. The evidence file
(`customer_account.md`) follows the six sibling evidence files
(`credit_memo.md`, `invoice.md`, `purchase_order.md`,
`receivables_invoice.md`, `standard_receipt.md`, `supplier.md`), which
`test_bundle_manifest.py` accepts — either they are excluded or they
are in a bundle. Whichever the pattern, `customer_account.md` follows
it. The three code files land in bundles `mcp_server_tools`,
`parser_context`, `tests` respectively. **The yaml edit is an eleventh
file.**

**Eighth correction, at V0 close — the file count is fourteen, not
ten.** The brief's "ten files" counts the four NEW, six PATCH, and
three ALSO files. What the four corrections above add: the classifier
menu regeneration (a NEW file at
`src/spire/nl_parser/context/routing/classifier_menu.sysprompt`),
`context_bundles.yaml` (a PATCH), and — folded into the `kg_schema.sql`
PATCH already counted — the `entity_synonym` seed row. Summed:

- 4 NEW (brief)
- 5 files PATCH (brief's six PATCH minus `kg_entity_tool` which is
  KG data, not a file)
- 3 ALSO files (brief: `kg_schema.sql`, `test_kg_metadata.py`,
  `print_kg.py`)
- 1 `context_bundles.yaml` PATCH
- 1 `classifier_menu.sysprompt` regeneration
= **fourteen files**

Plus one live DB action: `INSERT INTO kg_entity_tool VALUES
('CustomerAccount', 'none', 'search_customer_accounts', ...)`.
The `kg_entity_tool` count moves 12 → 13 in **four places**: the test
dict (`tests/test_kg_metadata.py`), `scripts/print_kg.py`'s
`expected_rows`, the `PROMPT Seeded kg_entity_tool (12 rows)` banner
in `scripts/sql/kg_schema.sql`, and the live DB row.

**Ninth correction, at the same V0 stage — V4 is the mechanism, not
a sibling check.** HANDOFF.md's §"Resume state" records:
"Proper-noun customer names are disambiguated by the sysprompt's
customer-scoped rule, not the helper." That claim is the load-bearing
one for PR #7's shape-check design: the helper can trust "the model
already produced filter-less intent" only if some other piece of the
pipeline routes customer-scoped prompts away from the filter-less
shape. That other piece is the sysprompt's customer-scoped rules
(`b_account_balance.sysprompt`, `b_customer_invoices.sysprompt`, etc.),
and the live proof is V4. Without V4 green, the helper is unsound: a
customer-scoped prompt that mis-routes to `filters=[]` would pass the
helper's checks and be treated as a filter-less list. V4 is therefore
load-bearing, not a regression check — a stronger role than PR #6's
V4, where the sibling check was a net rather than the mechanism.

**Tenth correction, at V0 close — the meeting's §8.5 open question is
closed by precedent.** `MEETING_2026-11-10_sample_and_disclose.md`
§8 asks "Where the tip computation lives for the two new tools," with
the note "the tip may need to move into a
`build_purchase_order_response()` helper." PR #6 settled that
question by precedent: the tip sits at the call-site kwarg
(`narrowing_tip=build_narrowing_tip(...)` on the plain-list return),
with no helper. PR #7 follows — the same call-site pattern, in the
plain-list branch that lands before `single_parent_shape`.

This is the **sixth** such correction in seven PRs. The pattern
established across PRs #1–#6 holds: the meeting's row describes a
wiring change, and master's code is nearly always either "already
samples locally, add one small shape, and one structural caveat"
(PRs #2–#5) or, as here and at PRs #1 and #6, "the tool the row names
does not exist yet — the row named it correctly, and mis-described
the rest." PR #1 needed no correction because it was a genuine wiring
PR whose meeting row matched master's gap on every axis. PR #6 was
the second such PR, with the PR #5 tip-caveat layered on top. PR #7
is the third, with the classifier-menu and bundle-manifest
corrections on top.

## V1 — Reproducer (live)

TBD — populated when the V-walk runs.

Three prompts at the brief's `WHAT IS KNOWN` section, all expected
green after the fix:

- `show me all customer accounts`
- `get all customer accounts`
- `list all customers`

Each expected to produce:
- Intent: `target_entity: CustomerAccount`, no filters, no include
- Plan: one step, `search_customer_accounts`, `tool_args: {}`
- Answer: `Showing 25 of N customer accounts.` (N = live pod total)
- No `─── Tip ───` block (empty by construction, per §V0-history)

## V2 — Paraphrase

TBD.

Expected: a paraphrase that exercises the same shape. Candidate:
`show me recent customer accounts`. The helper's design makes this
expected: it does not inspect the prompt for verbs, so a phrasing it
has never seen fires the same way as one it has.

## V3 — Siblings (unchanged)

The PR #7 change touches `ar.py` (field + detector + builder),
`synthesizer.py` (branch), `parser.py` (helper), `server.py`
(registration), `kg_schema.sql` + live DB (one row),
`classifier_menu.sysprompt` (regenerated), `context_bundles.yaml`
(three new lines), and the new sysprompt + manifest. None of these
reach the Supplier, PurchaseOrder, Invoice, StandardReceipt,
CreditMemo, or ReceivablesInvoice tip call sites. The sibling paths
are unchanged by construction.

V3 confirmed by the four-file synth blast-radius run at V6
(expected `97 passed, 1 deselected`, matching PRs #2, #4, #5, #6).

## V4 — Negative (customer-scoped routes away from the plain-list branch)

TBD.

Two live V4 controls from the brief:

- `account balance for ABC Application Software` — must route to
  `get_customer_account_by_name`, not to `search_customer_accounts`
- `AR invoices for ABC Corporation Americas` — must route to
  `get_customer_account_by_name` → `get_customer_transactions`, not
  to `search_customer_accounts`

Both currently work; PR #7 must not regress either. This is the
mechanism correction (§V0-history correction 9): the sysprompt's
customer-scoped rules are what tells the helper "this prompt is not
a filter-less list."

Plus the correctly-refused prompt:

- `show me all customer accounts balance` — must stay refused with
  `missing_identifier`. The balance-only shape requires a customer
  name; the refusal is correct.

Plus the unchanged-refusal control:

- `show me contract renewals due next quarter` — must stay refused
  with `Reason: Contract isn't something I know about.`

## V5 — Goldens (Intent-only)

TBD.

Same scope PRs #1–#6 used: compare each golden's `Intent:` block to
the current pipeline's. Three goldens expected MATCH:

| Golden | Prompt | Expected |
|---|---|---|
| `count_suppliers.txt` | `Count of suppliers` | `Supplier`, `count_only: True` |
| `po_2144_and_lines.txt` | `Show PO 2144 and its lines` | `PurchaseOrder`, `by_id: 2144`, `include: ['PurchaseOrderLine']` |
| `suppliers_with_open_pos.txt` | `Which suppliers have open purchase orders?` | `Supplier`, `has_open_PO: True` |

None route to CustomerAccount, so PR #7's changes do not reach them.

## V6 — pytest (scoped + synth blast-radius; full deferred)

**V6-full cannot run to completion on this environment.** Same class
as PRs #1–#6: the `mcp 2.x` / `langchain-mcp-adapters 0.3.1` conflict
breaks `tests/test_agent_runner.py` collection. Deferred to the MCP
migration PR.

V6 will be run in the two scoped forms:

| Layer | Command | Expected |
|---|---|---|
| scoped | `pytest -q tests/test_sample_and_disclose_customer_account.py` | `6 passed` |
| synth blast-radius | four files: `test_synthesizer`, `test_synthesizer_supplier_records`, `test_synthesizer_truncation_narration`, `test_synthesizer_aggregation` | `97 passed, 1 deselected` |

The `97 passed, 1 deselected` count matches PRs #2, #4, #5, #6
exactly for the same four-file set.

## V7 — Test fails without the fix

TBD — populated as the six red-then-green commits land:

- red: `docs(phase-3): customer_account.md — correct V0` + failing test
- green 1: fetcher module + `ar.py` field + `synthesizer.py` branch +
  KG seed row + KG count files + live DB row
- green 2 (parser): helper + wiring
- green 3 (sysprompt): `b_customer_accounts.sysprompt` + manifest entry
- green 4 (server): registration + any `print_kg.py` repair
- green 5 (classifier): `entity_synonym` seed + regenerated
  `classifier_menu.sysprompt`
- green 6 (bundle): `context_bundles.yaml` three new entries

## V8 — N-run reproducibility (deferred)

Deferred alongside V6. A 20-run sweep of the three canonical prompts
would test whether the parser's model produces the filter-less intent
deterministically (it is a stochastic LLM call per run) and whether
the helper's disqualifier fires the same way across phrasing
variations the model produces from an identical prompt. The single V1
and V2 runs are each green; the N≥20 sweep is deferred to the same
window that lands the MCP migration.

## V9 — --validate (REQUIRED; the mechanism does not exist on this branch)

**V9 is required for PR #7 — the second `.sysprompt` change in the
sequence.** The brief's V9 step names `python scripts/promptkit.py
--validate` against all 240 prompts.

**`--validate` does not exist on this branch.** Verified at PR #6
§V9 (two ways: `python scripts/promptkit.py --help` lists every option
it accepts and `--validate` is not among them;
`grep -rln 'validate' scripts/` finds no implementation). PR #7
inherits that finding and uses the V9-scoped pattern.

### V9-scoped (TBD)

Six prompts run end to end with `--show-parser --show-planner`, chosen
to cover the changed path and its neighbours:

- `get all customer accounts` — expected green (V1 reproducer)
- `show me recent customer accounts` — expected green (V2 paraphrase)
- `account balance for ABC Application Software` — expected unchanged
  (V4 control)
- `AR invoices for ABC Corporation Americas` — expected unchanged
  (V4 control)
- `show me all customer accounts balance` — expected unchanged
  refusal
- `show me contract renewals due next quarter` — expected unchanged
  refusal

Saved transcripts to `/tmp/pr7_v9_scoped/*.txt` when run.

### V9-full (deferred — the tool does not exist)

The 240-prompt `--validate` sweep is deferred to the MCP migration PR,
because the tool it invokes is absent from `promptkit.py`. A queue
item records this (STATUS.md queue item 7). Building `--validate`
proper is its own tooling PR.

## Deviations

*(Populated as the V-walk runs. Empty at V0 commit.)*

## V-walk state

| V | Status | Note |
|---|---|---|
| V0 | **done** | opened with the meeting row's prescription; corrected on reading `master` at `bb86b8a` (ten corrections — synthesizer is four changes, filtered_fields threading, parser helper as shape-check-not-verb-whitelist, parser helper load-bearing with sysprompt, classifier menu is stale for customer account(s), context_bundles.yaml must list three new files, file count fourteen not ten, V4 is the mechanism, meeting §8.5 closed by precedent) |
| V1 | **pending** | three canonical prompts; expected green with plan `search_customer_accounts` and `Showing 25 of N` |
| V2 | **pending** | paraphrase; expected green |
| V3 | **pending** | sibling paths unchanged; expected 97/1 blast-radius |
| V4 | **pending** | two controls + two refusals; expected unchanged |
| V5 | **pending** | three golden Intents; expected MATCH |
| V6 | **pending** | branch tests 6/6; synth blast-radius 97/1; full-suite blocked by MCP conflict |
| V7 | **pending** | six red-then-green commits documented |
| V8 | **deferred** | N≥20 sweep deferred to MCP migration PR |
| V9 | **pending** | scoped six-prompt sweep; `--validate` does not exist on this branch |

## Not checked

TBD

## S11 — Coverage expansion

TBD
