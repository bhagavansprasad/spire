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
to `kg_schema.sql` [see §V0-history correction 13 — the seed row was
already present at `bb86b8a`; the missing side was the live DB, and
this window applied the rows there before regenerating] and regenerates
`src/spire/nl_parser/context/routing/classifier_menu.sysprompt` via
`scripts/build_classifier_context.py` — the menu currently carries
`CustomerAccount` as a bare class name with no colloquial synonyms,
which is why `list all customers` (the brief's third failing prompt)
classifies only by the substring and `show me customer accounts`
leaves the classifier with no synonym to match; adds the three new
files to `context_bundles.yaml` (bundle `mcp_server_tools`,
`parser_context`, `tests`) to keep `tests/test_bundle_manifest.py`
green [see §V0-history correction 11 — `context_bundles.yaml` was NOT
touched; `test_bundle_manifest.py` is red on `bb86b8a` for pre-existing
reasons PR #7 does not repair]; and locks the shape with a red-then-green test at
`tests/test_sample_and_disclose_customer_account.py`. The change
spans **fourteen files plus one live DB row** — four more than the
brief's inventory suggested, because the plain-list branch, the
classifier-menu regeneration, and the bundle manifest had to be
written rather than wired: see §V0-history [correction 12 below
corrects the count: **thirteen files plus one live DB action**, because
`context_bundles.yaml` was not touched]. The tip field exists
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

**Sixth correction, from the classifier-menu read — AMENDED at the
V-walk (correction 13).** The parser's
`_is_filter_less_customer_account_request` assumes the classifier has
already routed the prompt to `receivables`. That assumption is only
sound if the classifier's menu contains the phrase
`customer account(s)`. At `bb86b8a`,
`src/spire/nl_parser/context/routing/classifier_menu.sysprompt:24`
carries `CustomerAccount` as a bare class name — no `(aka: customer
account, customer accounts, ...)` synonyms — while sibling entities
(`ReceivablesInvoice`, `CreditMemo`, `AccountReceipt`, etc.) carry
several.

**The original correction claimed the seed carried no
`entity_synonym` rows for `CustomerAccount`. That was wrong.** At
the V-walk (correction 13) the seed was read directly and the two
rows were **already present** at `kg_schema.sql:1075-1076`:
`('entity_synonym', 'customer account', 'CustomerAccount', ...)` and
`('entity_synonym', 'customer accounts', 'CustomerAccount', ...)`.
The gap was on the **live DB** side — the two rows were in the seed
but had never been applied to the live DB at `bb86b8a`'s state, and
`build_classifier_context.py` had not been run since. The menu
carried a bare class name because the live DB's `entity_synonym`
rows for `CustomerAccount` were 0.

The fix is therefore not a seed edit. It is: apply the two seed rows
to the live DB (idempotent, pre-checked — PR #7's commit-6 Cell B),
then run `scripts/build_classifier_context.py` (PR #7's commit-6
Cell C). The generated menu carries the synonyms, and the classifier
matches the phrase — not the substring — for both canonical prompts
and paraphrases. **Verified at the V-walk: `classifier_menu.sysprompt:24`
now reads `CustomerAccount (aka: customer account, customer accounts)`,
committed at `80c7bf0`.**

**Seventh correction, from the bundle-manifest read — REPLACED at the
V-walk (correction 11).** The original correction claimed PR #7 must
add three entries to `context_bundles.yaml` or
`test_bundle_manifest.py` fails. **That was wrong, and the correction
is retracted.**

`tests/test_bundle_manifest.py:77`
(`test_every_tracked_file_is_in_a_bundle`) does iterate `git ls-files`
and assert every tracked non-excluded non-allowlisted file is in some
bundle. But the test is **red on `bb86b8a` before PR #7** — the
missing-files list runs to dozens of entries that predate Phase 3:
`.dockerignore`, `.env.example`, `Dockerfile`, `Quick_how_to_run.md`,
`docker-compose.dev.yml`, `docker-compose.yml`, `spire-docker.sh`,
`spire-host.sh`, `docs/runbooks/rotate-fusion-password.md`, the four
`docs/spire-prism/*.md` files, `prompts/PROMPT_COUNTS.md`,
`prompts/rerun/rerun_01_failed.txt`, PR #6's
`search_receivables_invoices.py` and `b_ar_invoices.sysprompt`, all six
`test_sample_and_disclose_*.py` files, `test_sql_overlay_coverage.py`,
and more. PR #7's three new tracked files
(`search_customer_accounts.py`, `b_customer_accounts.sysprompt`,
`test_sample_and_disclose_customer_account.py`) would join that list;
they do not cause it.

**PR #7 does not touch `context_bundles.yaml`.** Bundling them is a
separate PR's work — the same repair the pre-existing red needs for
every other unbundled file. §Deviations records the fact as one line,
per §14.1. The original correction's "the yaml edit is an eleventh
file" is retracted; there is no yaml edit.

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
= **fourteen files** [AMENDED at the V-walk — correction 12: thirteen
files, because `context_bundles.yaml` is not touched]

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

**Eleventh correction, at the V-walk — `context_bundles.yaml` is not
touched.** The original seventh correction claimed the yaml must list
PR #7's three new files. That claim is retracted; see the replacement
text of correction 7 above. `test_bundle_manifest.py` is red on
`bb86b8a` before PR #7 for dozens of pre-existing unbundled files;
PR #7's three new files would join that list, not cause it. Repairing
the manifest is a separate PR's work.

**Twelfth correction, at the V-walk — the file count is thirteen, not
fourteen.** The original eighth correction added `context_bundles.yaml`
to the count. With correction 11 removing it, the count is:

- 4 NEW (brief)
- 5 files PATCH (brief's six PATCH minus `kg_entity_tool`, KG data)
- 3 ALSO files (brief: `kg_schema.sql`, `test_kg_metadata.py`,
  `print_kg.py`)
- 1 `classifier_menu.sysprompt` regeneration
= **thirteen files**

Plus one live DB action (`(CustomerAccount, 'none')` row), plus the two
`entity_synonym` rows applied to the live DB during commit 6 (neither a
git file).

**Thirteenth correction, at the V-walk — the `entity_synonym` seed
rows were already present.** Correction 6's original claim that the
seed carried no rows for `CustomerAccount` was wrong; the rows sit at
`kg_schema.sql:1075-1076`. The live DB at `bb86b8a`'s state carried
zero `entity_synonym` rows for `CustomerAccount`, which is why the
classifier menu was stale. Commit 6 applied the two rows to the live
DB and regenerated the menu (committed at `80c7bf0`); the seed was
untouched by PR #7.

**Fourteenth correction, at the V-walk — the `kg_vocabulary` count
drift was commit 3's seed edit.** Commit 3's Cell 5 added the two
`entity_synonym` rows to `kg_schema.sql`, moving the seed's
`kg_vocabulary` row count from 129 to 131. The two count files
(`tests/test_kg_metadata.py`, `scripts/print_kg.py`) still expected
129. The drift was latent until the KG rebuild (this window) applied
the 131-row seed to the live DB, at which point `print_kg.py --count`
reported `!! drift (129)` and `test_kg_table_row_counts_match_v1_1`
would have failed. Fixed at `c87c55e` — both count files moved
129 → 131. **Caught by inspection (the rebuild's count report),
not by a committed red test — §V7 records this honestly.**

This is the **sixth** such correction in seven PRs. The pattern
established across PRs #1–#6 holds: the meeting's row describes a
wiring change, and master's code is nearly always either "already
samples locally, add one small shape, and one structural caveat"
(PRs #2–#5) or, as here and at PRs #1 and #6, "the tool the row names
does not exist yet — the row named it correctly, and mis-described
the rest." PR #1 needed no correction because it was a genuine wiring
PR whose meeting row matched master's gap on every axis. PR #6 was
the second such PR, with the PR #5 tip-caveat layered on top. PR #7
is the third — and the first in seven where the V-walk corrected the
V0-history's own corrections (6, 7, 8 amended in place; 11–14
appended). Correction 7's retraction is a new shape: a correction
that was itself wrong and was replaced, not merely supplemented.

## V1 — Reproducer (live)

Three prompts run against `fa-esll-saasfademo1` after the dev MCP
server was restarted at PID `114560` (WORKING_STYLE §22.1). Transcripts
saved to `/tmp/pr7_v1_{all,get,list}.txt`. All three green,
byte-identical shape:

- Intent `CustomerAccount`, no filters, no include.
- Plan `Step 1: search_customer_accounts`, `tool_args: {}`.
- Answer `Showing 25 of 571 customer accounts.`
- No `─── Tip ───` block. `Truncation:` block present at line 62, of
  the standard `_local_truncation` shape
  (`customer_accounts: 571 total in source; 25 returned.`) — the
  shape PR #1–#6 produce on a plain-list 25-row sample.

The three verb forms (`show me all`, `get all`, `list all`) produced
the same shape, because the helper inspects the intent, not the
wording — the design property §V0-history's fifth correction
established. **571** is the live pod count at run time; PR #6's read
recorded 435, and the fetcher reports the live `totalResults`, not a
cached one.

## V2 — Paraphrase

Prompt `show me recent customer accounts`. Transcript at
`/tmp/pr7_v2_paraphrase.txt`. Green, byte-identical to V1:
`CustomerAccount` no filters; `search_customer_accounts`;
`Showing 25 of 571 customer accounts.`; `Truncation:` block;
no Tip.

`recent` is a recency adjective with no explicit N. The sysprompt's
first rule (`b_customer_accounts.sysprompt`) names this phrasing as
a trigger, and the helper fires on the resulting filter-less intent.

## V3 — Siblings (unchanged)

The PR #7 change touches `ar.py` (field + detector + builder),
`synthesizer.py` (branch), `parser.py` (helper), `server.py`
(registration), the live DB (two `entity_synonym` rows applied, one
`(CustomerAccount, 'none')` row — the seed was already correct on
both sides, §V0-history corrections 13 and 14), the regenerated
`classifier_menu.sysprompt`, and the two count files. It does not
touch `context_bundles.yaml` (§V0-history correction 11). None of
these reach the Supplier, PurchaseOrder, Invoice, StandardReceipt,
CreditMemo or ReceivablesInvoice tip call sites. The sibling paths
are unchanged by construction.

V3 confirmed by the V6 blast-radius: four synthesizer files,
`97 passed, 1 deselected in 0.30s`, matching PRs #2, #4, #5, #6
exactly. See §V6.

## V4 — Negative (customer-scoped routes away from the plain-list branch)

Two V4 controls plus two refusals. Transcripts at
`/tmp/pr7_v4_{balance,ar_inv,balance_only,contract}.txt`. All four
green:

- **`account balance for ABC Application Software`** — Intent
  `CustomerAccount`, `by_customer_name` filter, `balance_only: True`.
  Plan `Step 1: get_customer_account_by_name` (the resolver, **not**
  `search_customer_accounts`). Answer the balance figures. No Tip.
  `b_account_balance.sysprompt` is what routes this away from the
  filter-less shape.
- **`AR invoices for ABC Corporation Americas`** — Intent
  `CustomerAccount`, `by_customer_name`, `include: ['CustomerTransaction']`.
  Plan `Step 1: get_customer_account_by_name` → `Step 2:
  get_customer_transactions`. No Tip. `b_customer_invoices.sysprompt`
  routes it away.
- **`show me all customer accounts balance`** — correctly refused
  `missing_identifier`. `Reason:   I can look up customer accounts,
  but this doesn't say which one.` Solution and Example are the
  `_FALLBACK[MISSING_IDENTIFIER]` lines (§Deviations one-liner).
- **`show me contract renewals due next quarter`** — unchanged
  `UNKNOWN_ENTITY` refusal, same flavor as PRs #1–#6. §V9 records
  a wording variance across runs.

**Why the two controls are the mechanism, not a regression net.**
The helper sets `list_all=True` on any intent targeting
`CustomerAccount` with `filters=[]` and `include=[]` and no
account-number-shaped token. Its correctness depends on **nothing
else** producing that shape for a customer-scoped prompt — because
if anything did, the helper would treat a customer-scoped prompt as
a filter-less list and answer by listing every customer. The
sysprompt's customer-scoped rules (`b_account_balance`,
`b_customer_invoices`, `b_customer_credit_memos`,
`b_account_receipts`, `b_receipt_applications`) are what make it
safe. Both controls green is the mechanism proof. §V0-history
correction 9 records the reasoning.

## V5 — Goldens (Intent-only)

Three goldens compared at `/tmp/pr7_v5_*.txt`. All **MATCH**
byte-for-byte on the Intent block, filters and includes included:

| Golden | Golden Intent | Current Intent | Result |
|---|---|---|---|
| `count_suppliers.txt` | `Supplier`, `count_only: True` | same | **MATCH** |
| `po_2144_and_lines.txt` | `PurchaseOrder`, `by_id: '2144'`, `include: ['PurchaseOrderLine']` | same | **MATCH** |
| `suppliers_with_open_pos.txt` | `Supplier`, `has_open_PO: True` | same | **MATCH** |

None route to CustomerAccount, so PR #7's changes do not reach them.
Same scope-boundary reasoning `supplier.md` §V5, `invoice.md` §V5,
`standard_receipt.md` §V5 and `receivables_invoice.md` §V5 used.

## V6 — pytest (scoped + synth blast-radius; full deferred)

**V6-full cannot run to completion on this environment.** Same class
as PRs #1–#6: the `mcp 2.x` / `langchain-mcp-adapters 0.3.1` conflict
breaks `tests/test_agent_runner.py` collection. Deferred to the MCP
migration PR.

V6 was run in the two scoped forms:

| Layer | Command | Result |
|---|---|---|
| scoped | `pytest -q tests/test_sample_and_disclose_customer_account.py` | **`6 passed in 0.17s`** |
| synth blast-radius | four files: `test_synthesizer`, `test_synthesizer_supplier_records`, `test_synthesizer_truncation_narration`, `test_synthesizer_aggregation` | **`97 passed, 1 deselected in 0.30s`** |

Saved logs: `/tmp/t_pr7_v6_scoped.log`, `/tmp/t_pr7_v6_synth.log`.

**The `97 passed, 1 deselected` count matches PRs #2, #4, #5, #6
exactly** for the same four-file set. PR #7's two synthesizer files
did not perturb the synthesizer surface those four files cover.

## V7 — Test fails without the fix

Standard FIX_PLAN §8 step 3 discipline: red first, green after,
neither a post-hoc stash. The actual commit sequence on the branch:

**Red.** `392b6d4` — `test(phase-3): customer_account — failing red
test for PR #7`. `tests/test_sample_and_disclose_customer_account.py`
had **`6 failed in 0.48s`** at that commit (`/tmp/t_pr7_red.log`):
`AttributeError: 'CustomerAccountResponse' object has no attribute
'narrowing_tip'` on four of the six; `AssertionError:
synthesize_response called the LLM on a plain customer-account list`
on the reproducer; `AssertionError` on the customer-scoped routing
test. Exactly the three shapes the fix lands.

**Green 1.** `dbc6117` — `feat(phase-3): customer_account —
fetcher, KG row, plain-list branch (green 1)`. Seven files: fetcher
module, `server.py` registration, `ar.py` field + detector +
builder, `synthesizer.py` plain-list branch, `kg_schema.sql` seed row
and `PROMPT Seeded kg_entity_tool (12 rows) → (13 rows)` banner,
`tests/test_kg_metadata.py` and `scripts/print_kg.py` count files,
plus the live DB `(CustomerAccount, 'none')` INSERT. After this
commit: **`6 passed in 0.12s`** (`/tmp/t_pr7_green1.log`). The
three-file trio (module + registration + KG row) landed together,
satisfying §15.3.1 carry-forward rule #2. The synthesizer's four
changes (field + detector + builder + branch before
`single_parent_shape`) landed here, so the six tests pass.

**Green 2.** `eedf499` — `feat(phase-3): customer_account — parser
helper and wiring (green 2)`. One file: `parser.py`'s
`_CUSTOMER_ACCOUNT_DISQUALIFIERS` tuple, the
`_is_filter_less_customer_account_request` helper, and the wiring
block in `parse()`. The six unit tests still pass here (they do not
depend on `parser.py`); green 2's load-bearing proof is V1's three
live prompts.

**Green 3.** `cd84df9` — `feat(phase-3): customer_account —
filter-less sysprompt block and manifest entry (green 3)`. Two
files: `b_customer_accounts.sysprompt`, `order.manifest`.

**Green 4.** `80c7bf0` — `feat(phase-3): customer_account —
regenerate classifier menu (green 4)`. One file: the regenerated
`classifier_menu.sysprompt`. The two `entity_synonym` rows were
applied to the live DB (idempotent, verified) before the
`scripts/build_classifier_context.py` run; the seed was already
correct (§V0-history correction 13).

**V-walk-surfaced defect fix.** `c87c55e` — `fix(phase-3):
customer_account — kg_vocabulary count 129→131 (V-walk surfaced)`.
The `kg_vocabulary` count drift was commit 3's seed edit
(§V0-history correction 14); caught by `print_kg.py --count`
reporting `!! drift (129)` after the KG rebuild applied the 131-row
seed to the live DB. The fix moves both count files 129 → 131.
**The red is the `!! drift` transcript line, not a committed failing
test** — the count check was run *after* the fix, not before. This
is the first PR in the sequence where a V-walk defect's red is
inferred from inspection rather than a committed failing test.
Recorded honestly rather than retrofitted with a synthetic commit.

**Rulebook capture.** `72e6f7c` — `docs(working-style): capture
§15.3.1 multi-file loop and §15.4.1 worked example`. Not a
defect-fix commit; captures the discipline this PR executed under.
Rides the branch, lands with the PR.

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

### V9-scoped (green)

Six prompts run end to end with `--show-parser --show-planner`,
covering the changed path and its five neighbours. Saved transcripts
at `/tmp/pr7_v9_scoped/*.txt`.

| Prompt | Intent | Plan | Answer |
|---|---|---|---|
| `get all customer accounts` | CustomerAccount, no filters | `search_customer_accounts` | `Showing 25 of 571 customer accounts.` |
| `show me recent customer accounts` | CustomerAccount, no filters | `search_customer_accounts` | `Showing 25 of 571 customer accounts.` |
| `account balance for ABC Application Software` | CustomerAccount, `by_customer_name`, `balance_only: True` | `get_customer_account_by_name` | unchanged |
| `AR invoices for ABC Corporation Americas` | CustomerAccount, `by_customer_name`, `include: ['CustomerTransaction']` | `get_customer_account_by_name` → `get_customer_transactions` | unchanged |
| `show me all customer accounts balance` | — | — | `Reason:   I can look up customer accounts, but this doesn't say which one.` |
| `show me contract renewals due next quarter` | — | — | `Reason:   that kind of record isn't something I know about.` |

The two filter-less prompts prove the feature end to end. The two
V4 controls prove the customer-scoped boundary holds. The two
refusals prove the parse gate holds.

**Wording variance on the contract-renewals refusal, one run.**
V4's transcript says `Contract isn't something I know about.`;
V9-scoped's says `that kind of record isn't something I know about.`
Same flavor (`UNKNOWN_ENTITY`); the wording differs by whether the
model populated `unanswerable_entity` on its self-declared refusal.
`capability.py` drives the wording; PR #7 does not touch
`capability.py` and is not responsible for the variance. Recorded
here so a future window sees it as PR #7 saw it.

### V9-full (deferred — the tool does not exist)

The 240-prompt `--validate` sweep is deferred to the MCP migration PR,
because the tool it invokes is absent from `promptkit.py`. A queue
item records this (STATUS.md queue item 7). Building `--validate`
proper is its own tooling PR.

## Deviations

### Out of scope — `capability.py` has no `_IDENTIFIER_GUIDANCE['CustomerAccount']` entry

The correctly-refused `show me all customer accounts balance`
returns `missing_identifier` with the generic
`_FALLBACK[MISSING_IDENTIFIER]` Solution and Example lines, because
`capability.py` has no entity-specific entry for `CustomerAccount`.
Adding one belongs with the existing capability.py queue item
(item 4, `_FILTER_GUIDANCE['CreditMemo']` live). Not a PR #7 fix.

### Out of scope — `test_bundle_manifest.py` is red on master (pre-existing)

`test_bundle_manifest.py::test_every_tracked_file_is_in_a_bundle`
fails on `bb86b8a` for dozens of tracked files that predate PR #7
(`Dockerfile`, `spire-docker.sh`, PR #6's
`search_receivables_invoices.py` and `b_ar_invoices.sysprompt`, all
six `test_sample_and_disclose_*.py`, `test_sql_overlay_coverage.py`,
and more). PR #7's three new files join the same list; they do not
cause it. PR #7 does not touch `context_bundles.yaml`. Repairing the
manifest comprehensively is a separate PR. See §V0-history
correction 11.

### Out of scope — `_is_explicit_po_list` verb-set gap (`get all POs`)

Same finding as PR #6 §Deviations. Queue item 9. Not fixed here.

### KG rebuilt from seed during PR #7's window

`python scripts/rebuild_kg.py` was run once during V-walk
preparation. It dropped and re-created every KG table from
`kg_schema.sql`, so the live DB is now the seed by construction.
Any prior live-only drift (per `test_kg_metadata.py`'s own
docstring, the KG has had live-only rows before) is gone. Seed and
live DB agree. Recorded here so a future window knows the state.

### `personas.yaml` in the working tree

Local credential edit, never staged, not part of any PR.

## V-walk state

| V | Status | Note |
|---|---|---|
| V0 | **done** | ten corrections at V0; four more amended/replaced/appended at the V-walk — see §V0-history corrections 6, 7, 8, and 11–14 |
| V1 | **green** | three canonical prompts, `Showing 25 of 571 customer accounts.`, plan `search_customer_accounts`, no Tip, `Truncation:` block |
| V2 | **green** | `show me recent customer accounts` — byte-identical to V1 |
| V3 | **green** (folded into V6) | sibling paths unchanged; V6 blast-radius is V3's evidence |
| V4 | **green** | two controls hold (resolver path, not `search_customer_accounts`); balance-only correctly refused; `contract renewals` unchanged refusal |
| V5 | **green** | three golden Intents matched byte-identically |
| V6 | scoped + synth **green**; full **deferred** | scoped `6 passed in 0.17s`; blast-radius `97 passed, 1 deselected in 0.30s` |
| V7 | **green** | red at `392b6d4` (`6 failed`) → green 1 at `dbc6117` (`6 passed`); greens 2–4 at `eedf499`, `cd84df9`, `80c7bf0`; V-walk defect fix at `c87c55e` (red inferred from `print_kg.py --count`, not committed); rulebook capture at `72e6f7c` |
| V8 | **deferred** | N≥20 sweep deferred to MCP migration PR |
| V9 | scoped **green**; full **deferred** | six-prompt sweep; `--validate` does not exist on this branch |

## Not checked

- **V6-full** — `pytest -q` against the full suite — deferred to the
  MCP migration PR, same class as PRs #1–#6. The `mcp 2.x` /
  `langchain-mcp-adapters 0.3.1` conflict breaks
  `tests/test_agent_runner.py` collection.
- **V8** — the N≥20 reproducibility sweep — deferred alongside
  V6-full. The single V1 and V2 runs are each green; the sweep would
  test whether the parser's model produces the filter-less intent
  deterministically and whether the helper's disqualifier fires the
  same way across phrasing variations.
- **V9-full** — the 240-prompt `--validate` sweep — deferred;
  `--validate` does not exist on this branch (PR #6 §V9; queue item
  7). V9-scoped is the substitute.
- **The full `test_bundle_manifest.py` repair** — red before PR #7
  (see §Deviations); PR #7 does not repair it.
- **The `capability.py` `_IDENTIFIER_GUIDANCE['CustomerAccount']`
  entry** — §Deviations, not a PR #7 fix.
- **The `contract renewals` refusal wording variance** — noted in
  §V9-scoped; not investigated to a root cause.

## S11 — Coverage expansion

The three V1/V2 filter-less prompts plus the two V4 controls are the
shape this PR samples. The same prompts are in the V9-scoped set
above. A future prompt-set window can add "show me all <entity>"
across every sampleable entity from MEETING §2, but that is the
seven-PR sequence's coverage, not PR #7's.
