# SPIRE — window handoff

**Window close:** 2026-11-12 (PR #6 open; merge pending).
**Tip:** `master` at `2327fd0` (docs commit that opened PR #6's V0).
The PR #6 branch `Phase3-ReceivablesInvoice-Sample` is **10 commits
ahead of `master`** at tip `2215cd0`, **open** as PR #6 against
`master`.
**Branch:** `Phase3-ReceivablesInvoice-Sample` (working tree clean;
`personas.yaml` local-only, never staged).

This file is the resume surface. Per `WORKING_STYLE.md` §1, read it
before any other file when opening a new window.

---

## What is live

Phase 3 (sample-and-disclose) sequence from
`docs/plan/MEETING_2026-11-10_sample_and_disclose.md` §6. The first
five PRs are merged:

| PR | Merge commit | Entity | Evidence file (frozen, `State: closed`) |
|---|---|---|---|
| #203 | `2a23906` | PurchaseOrder (anchor) | `purchase_order.md` |
| #204 | `850feb5` | Supplier | `supplier.md` |
| #205 | `3f3ff11` | Invoice | `invoice.md` |
| #206 | `5eadf7b` | StandardReceipt | `standard_receipt.md` |
| #207 | `4d301c4` | CreditMemo | `credit_memo.md` |
| #6 (this branch) | `TBD — merge pending` | ReceivablesInvoice | `receivables_invoice.md` |

Post-merge docs commits on `master`: `05d7978` (freeze
`supplier.md`), `983a7fb` (handoff to PR #3), `9724282` (resume
docs correction), `5f9b554` (freeze `invoice.md`), `e7d31b2` (freeze
`standard_receipt.md`), `0c9f3ec` (PR #4 `STATUS.md` advance),
`7e786c7` (PR #4 `HANDOFF.md` advance), `341b9f9` (PR #5 extended
prompt set findings), `5ef278c` (freeze `credit_memo.md`),
`d2a689b` (PR #5 `STATUS.md` advance), and this commit (PR #5
`HANDOFF.md` advance).

---

## Resume state — what is next

The next window starts **PR #7** (the seventh entity, CustomerAccount,
from `MEETING_2026-11-10_sample_and_disclose.md` §6 row 7) on a fresh
branch off `master`.

The V0 for PR #7 must be based on a **read of `master`**, not on the
meeting's row. PR #2's V0 correction (`7b7bb51`), PR #3's
`invoice.md` V0, PR #4's `standard_receipt.md` V0 (the unscoped
`get all receipts` case is refused by design), PR #5's
`credit_memo.md` V0 (the tip ships empty by construction because the
KG has no CreditMemo entity-level filters), and PR #6's
`receivables_invoice.md` V0 (three corrections — plain-list branch,
empty-by-construction tip, parser helper as shape-check-not-verb-
whitelist) all proved that lesson. **Read `receivables_invoice.md`
§V0-history before opening PR #7's V0.**

### PR #7 scope — CustomerAccount

PR #7 is a **real wiring PR** — the third in the sequence after PRs
#1 and #6 — and larger than PRs #2–#5.

**What exists on `master`:**

- `get_customer_account_by_name` — a **resolver** (`q=CustomerName=` or
  `q=AccountNumber=`), returning a **list** of matching accounts, each
  carrying the account's balances. Not a filter-less fetcher: it
  requires one of the two identifiers.
- The child fetchers, iterated off the resolver's `AccountId`:
  `get_customer_transactions`, `get_account_credit_memos`,
  `get_account_receipts`, `get_account_receipt_applications`.
- The synthesizer branch (`synthesizer.py`) uses `single_parent_shape`
  (markers `AccountId`, `AccountNumber`,
  `TotalOpenReceivablesForAccount`). **`single_parent_shape` requires
  exactly one parent row**; a 25-row plain account list does not match
  it and falls through to the LLM path.
- The KG's `kg_entity_tool` has `(CustomerAccount, 'by_customer_name')`
  and `(CustomerAccount, 'by_account_number')`, both to
  `get_customer_account_by_name`. There is **no**
  `(CustomerAccount, 'none')` row.

**What does not exist:**

- A **filter-less CustomerAccount fetcher** — `search_customer_accounts`
  — that returns the newest N accounts with the pod's `totalResults`
  on `total_available`.
- The **KG row** `(CustomerAccount, 'none')`.
- A filter-less sysprompt block for the plain-list shape.
- A parser shape check for a filter-less CustomerAccount intent.
- A plain-list synthesizer branch and a `narrowing_tip` field on
  `CustomerAccountResponse`.

**The parser helper is a shape check, not a verb whitelist.** This is
the design correction PR #6 established, recorded in
`receivables_invoice.md` §V0-history ("Fourth correction, at the same
V0 stage"). PR #7's helper:

- Takes `(prompt, intent)`.
- Returns `True` when the intent already targets `CustomerAccount` with
  `filters=[]` and `include=[]`, **and** the raw prompt carries no
  account-number-shaped token. If both, `list_all=True`.
- Does **not** inspect the prompt for a list verb. The user's wording
  is not the signal; the shape of the intent is. A verb whitelist
  would miss `get all customer accounts` unless `get all` happened to
  be on the list, and would need extending each time a phrasing the
  author did not anticipate appears — a refusal waiting for the next
  user.
- The disqualifier is an account-number-shaped token (a 3+ digit run
  that is not a plausible year). **Proper-noun customer names are
  disambiguated by the sysprompt's customer-scoped rule, not the
  helper** — a name like `ABC Application Software` in the prompt
  routes to the resolver path via the sysprompt's customer-scoped
  teaching, and the helper never sees it as a filter-less intent. The
  helper is the last check; the sysprompt does the routing.

The name is `_is_filter_less_customer_account_request(prompt, intent)`.
The parallel to PR #6's `_is_filter_less_receivables_invoice_request`
is deliberate; the two are the same check on different entities. See
`receivables_invoice.md` §V0-history for the reasoning that produces
the shape.

**Planner guard:** CustomerAccount has **no** entity guard today. Unlike
PRs #3–#6, PR #7 does not relax a guard; there is no `raise
RefusalError` standing in front of the plain-list path, because there
is no guard on this entity. `_build_entity_fetcher_args` in
`planner.py` runs its filter set through `_pick_entity_filter` — a
filter-less intent's `filter_type` is `'none'`, and
`find_entity_tool('CustomerAccount', 'none')` will look up the new KG
row.

**KG touch:** one row in `kg_entity_tool` — `(CustomerAccount, 'none')`
→ `search_customer_accounts`. The `kg_entity_tool` count moves 12 → 13;
`tests/test_kg_metadata.py` and `scripts/print_kg.py` need updating in
the same commit. **The three-layer pattern PR #6 established applies:**
the seed row in `scripts/sql/kg_schema.sql`, the count updates in the
two files, the live DB row via the same one-shot INSERT script. All in
the same commit, all verified by the same cell.

**Synthesizer changes:** a new `plain_customer_account_bucket(outputs)`
detector in `ar.py` (mirror of `plain_receivables_invoice_bucket`), a
new `build_customer_account_plain_records()` builder, a
`narrowing_tip: str = Field(default="", …)` on
`CustomerAccountResponse`, and a new branch in `synthesize_response`
placed **before** the `single_parent_shape` block (same position as PR
#6's plain-list branch). The branch's summary reads from
`local_list_summary` with `displayed_fields` = exactly what
`formatters.py` renders for a `CustomerAccountResponse`, and the
`narrowing_tip` is `build_narrowing_tip(set(), total_available,
entity_label="customer accounts")` under a sample-only guard — the
same shape as PR #6's ReceivablesInvoice branch. **The tip ships empty
by construction**: `_entity_level_filter_types()` returns nothing for
`CustomerAccount`, so `set()` is what is passed and the tip is `""` by
the helper's own `if not labels: return ""` guard.

**Server registration:** `search_customer_accounts` in `server.py`,
matching the existing wrapper shape. **The three-file trio lands
together, before any V9 run** — module + `server.py` registration + KG
row. PR #6's V9-scoped sweep caught this omission with `Unknown tool`;
PR #7 must not repeat the order.

**V9:** `--validate` **still does not exist** on this branch. PR #7
inherits PR #6's decision: V9-scoped (six-prompt sweep with
`--show-parser --show-planner`, covering the changed path plus four
neighbours) is what PRs that require V9 do until a tooling PR builds
the flag. The queue item recording `--validate`'s absence (STATUS.md
item 7) is the pointer; the reasoning is in `receivables_invoice.md`
§V9.

### Three carry-forward notes (updated through PR #6)

- **`personas.yaml`.** Local credential edit. Confirm `git status`
  is clean before staging anything. It does not go into any PR.
- **V-walk will surface defects the unit tests do not catch.** PR
  #1 found three (Fix A/B/C in `purchase_order.md` §Deviations).
  PR #2 found three (Fix D-a/D-b/E in `supplier.md` §Deviations).
  PR #3 found one (V3c in `invoice.md` §V3 and §Deviations). PR #4
  found one (Fix P in `standard_receipt.md` §Deviations — the
  empty-truncated summary narrating the cap as the cause). PR #5
  found zero in-scope defects (the tip is empty by construction and
  never fires), but the extended prompt set surfaced two out-of-scope
  findings in `credit_memo.md` (the `capability.py`
  `_FILTER_GUIDANCE["CreditMemo"]` entry and the `aggregation.py`
  count-path pluralisation). PR #6 found one wiring defect
  (`server.py` registration omitted; the V9-scoped sweep surfaced
  `Unknown tool: 'search_receivables_invoices'`), which is why the
  third note below exists. Expect at least one per PR. The tests
  you write at step 4 are the tests PR #N **starts** with, not the
  tests it needs.
- **For a wiring PR, the module + registration + KG row land
  together, before V9.** A new MCP tool needs three files in lockstep
  — the module, the `server.py` registration, and (for a KG-advertised
  tool) the `kg_entity_tool` row. Landing the module and KG row
  without the registration leaves the executor calling a tool the
  server does not expose; the failure shows up as `Unknown tool` from
  the executor, mid-plan, after the parser and planner have both
  succeeded. PR #6's V9-scoped sweep caught it. A `.py` patch's verify
  also includes `ast.parse` + `import` — the four §15.4 postconditions
  are necessary, not sufficient, for a `.py` file. (PR #6's
  `print_kg.py` patch broke Python syntax while satisfying all four
  postconditions; the compile check is what would have caught it.)

---

## Open queue (non-blocking)

Surfaced during PRs #1 through PR #5, not yet scheduled:

1. **Parser: AP-invoice-lines include.** PR #3's V3a refused
   `show invoices for supplier 1252 and their lines` with
   `Invoice lines for AP invoices are not supported`. A parser-
   sysprompt window can add the include; multi-bucket Invoice
   coverage depends on it.
2. **SQL overlay: Invoice FilterSpecs.** `invoice_date_before`,
   `unpaid` (and likely `overdue`, `pending`) absent from
   `kg_sql_filter`. Same class as the multi-field-iteration
   finding; belongs with the SQL emitter fix window.
3. **MCP migration PR.** V6/V8 of PRs #1, #2, #3, #4, #5 all deferred
   to it. Still unscheduled.
4. **PR #6 onward** — ReceivablesInvoice, the next entity from the
   seven-PR sequence.

**Two additional items recorded by PR #5's extended prompt set:**

5. **`capability.py` `_FILTER_GUIDANCE["CreditMemo"]` live
   finding.** The refusal for a date-scoped CreditMemo prompt advises
   narrowing by a customer-name filter that does not exist on the
   CreditMemo entity; following the advice routes to `CustomerAccount`.
   Recorded in `credit_memo.md` §Deviations. Separate `capability.py`
   branch.
6. **`aggregation.py` count-path pluralisation.** `how many credit
   memos are there` answers `There are 2261 creditmemos.` — no space,
   no thousands separator. `_build_count_response`'s template is
   `f"...{target_entity.lower()}s."`; correct for `suppliers` /
   `invoices`, wrong for `CreditMemo`. Recorded in `credit_memo.md`
   §Deviations. Separate `aggregation.py` branch.

No `FIX_PLAN.md` rows are touched by any of the above.

---

## Working style pointers

- `docs/plan/WORKING_STYLE.md` — the standing rules. §1 (context
  bundles), §2 (one command at a time), §15.3 (Python script + shell
  verification), §27 (queue report after every closure), Rule 28
  (SME test).
- `docs/fixes/FIX_PLAN.md` §6 (V0–V9 standard) and §8 (per-fix
  workflow: file first, then branch, then failing test, then fix).
- `docs/phase-3/sample_and_disclose/STATUS.md` — the resume surface
  for Phase 3.
- The five evidence files (`purchase_order.md`, `supplier.md`,
  `invoice.md`, `standard_receipt.md`, `credit_memo.md`) — the durable
  record per merged PR.

---

## What this handoff does not carry

Anything before PR #203 is in `master`'s history and in the audit
records (`docs/audit/`, `docs/fixes/`, `docs/phase-2/`). This file
exists to tell a new window where it is now, not where everything
has ever been.

