# SME prompt set — fix plan

The open-issue queue for the 40-prompt SME Module A set, grouped by **root
cause** rather than by prompt. One defect usually fails several prompts
because the prompt set deliberately tests the same capability in different
phrasings.

**Cycle:** run → issues → fix plan → fixed → next run → … Update the
*Status* column and add a `runNN` reference when a fix lands; do not delete
a closed row, so the history stays readable.

| | |
|---|---|
| Current run | `run02_2026-11-28_results.md` |
| Comparison | `COMPARISON.md` |
| Defect register (F-0xx) | `docs/fixes/FIX_PLAN.md` |

## Status summary

| ID | Issue | Prompts | Owner | Status |
|---|---|---:|---|---|
| SP-001 | No `supplier_number` filter on `search_suppliers` | 6 | Spire | **Open — highest value** |
| SP-002 | No creation-date filter on the AR invoice fetcher | 1 | Spire | **Open — cheap** |
| SP-003 | `/purchaseOrders` returns 0 rows (HTTP 200) | 6 | Environment | **Open — blocks 6** |
| SP-004 | `/receivablesCustomerAccountActivities` → 403 | 4 | Environment | **Open — not code** |
| SP-005 | `get_invoice_lines` silently truncates (184 → 50) | 1 | Spire | **Open — correctness** |
| SP-006 | Genuine filter/parser gaps (9 sub-items) | 9 | Spire | Open — triage first |

Code defects: **SP-001, SP-002, SP-006**. **SP-005 is closed** (PR #231 data +
PR #233 delivery; p13 states 184 on a restarted stack) and **AP-1 is closed**
(Invoice `DueDate`, `Supplier`, `PaidStatus`, `ApprovalStatus` all render).
Environment: **SP-003, SP-004** — not fixable in this repo.

---

## SP-001 — `search_suppliers` has no `supplier_number` parameter

**Status: Open. Highest value of any open item: 6 prompts, one parameter.**

**Symptom.** Every supplier question that identifies the supplier by *number*
refuses:

```
unsupported_filter — Searching or filtering suppliers by supplier number is not supported.
```

**Prompts blocked (6):** 32, 33, 34, 35, 38, 40.

Note these are not six distinct capabilities. They are:
- 32 / 35 — details vs contacts for supplier 1262
- 33 / 34 — active vs inactive sites for supplier 1262
- 38 / 40 — site assignments vs comparison for supplier 1262

One filter unblocks all six.

**Evidence the capability exists.** Verified against dev49:

```
REST  GET /suppliers?q=SupplierNumber='1262'   ->  1 row
Pod   SELECT COUNT(*) FROM POZ_SUPPLIERS WHERE SEGMENT1='1262'  ->  1
```

**Root cause.** `src/spire/mcp_server/tools/suppliers.py::search_suppliers`
takes `supplier_name_contains`, `status`, `business_relationship`, `country`,
`created_from`, `created_to` — no number parameter. The KG has no
`supplier_number` filter either, so the capability is missing at three
layers, not just the tool:

| Layer | Change |
|---|---|
| `mcp_server/tools/suppliers.py` | add `supplier_number: str \| None`, sent as the single server-side `q=SupplierNumber='…'` clause |
| `kg/sql_overlay.py` | `("search_suppliers","supplier_number")` → `{alias}.SEGMENT1 = {value}` |
| `kg_schema.sql` | `kg_entity_filter` row so the parser offers the filter |
| `nl_parser/context/supplier/*.sysprompt` | teach "supplier 1262" → `supplier_number` |
| `scripts/validate_sql_coverage.py` | will enforce the arg/spec pairing once added |

**Assumption to state in the code:** `SupplierNumber` maps to
`POZ_SUPPLIERS.SEGMENT1` — already established for the Invoice supplier
filter (`invoice_supplier_maps_to_segment1`), so this reuses a verified
mapping rather than asserting a new one.

**Effort:** S–M. **Verify with:** run03 prompts 32–35, 38, 40.

---

## SP-002 — no creation-date filter on the AR invoice fetcher

**Status: Open. Cheapest win: 1 prompt, REST already answers it.**

**Prompt:** 21 — *"Show all AR invoices created in the last 30 days…"*

**Symptom.** `unsupported_filter — Filtering AR invoices by a creation date
relative range in days (last 30 days) is not supported.`

**Evidence the capability exists:**

```
REST  /receivablesInvoices?q=CreationDate>'2026-10-29'  ->  18 rows
```

**Root cause.** `search_receivables_invoices(client, limit=25)` is the
filter-less sample-and-disclose fetcher by design — it takes no filters at
all. The refusal is therefore *honest about the tool*, but the tool is the
wrong shape for a filtered question. Either:

- **(a)** add `created_since` / `created_before` to the fetcher, mirroring
  `search_purchase_orders`; or
- **(b)** leave the fetcher alone and add a separate filtered AR-invoice tool.

Prefer **(a)** — the PO equivalent already exists and is the established
shape, and `CreationDate` is already in the tool's `_PROJECTED_FIELDS`.

**Effort:** S. **Verify with:** run03 prompt 21 (expect 18-ish rows).

---

## SP-003 — `/purchaseOrders` returns 0 rows with HTTP 200

**Status: Open. Environment. Blocks 6 prompts and silently produces wrong
answers.**

**Prompts affected (6):** 1, 2, 3, 4, 5, 6. All five PO children
(lines, schedules, distributions, buyer) hang off the header fetch, so a
single empty collection fails the whole procurement module.

**Symptom.** No error, no warning — the answer is *"No purchase orders found
matching the criteria."* and the count is 0.

**Evidence it is the endpoint, not the query:**

```
REST  /fscmRestApi/resources/11.13.18.05/purchaseOrders  ->  0 rows  (HTTP 200)
Pod   SELECT COUNT(*) FROM PO_HEADERS_ALL                ->  18,389
REST  /fcmRestApi/.../purchaseOrders?q=POHeaderId=67     ->  0   (id exists on pod)
REST  /suppliers                                         ->  338
REST  /invoices                                          ->  53,175
```

The same credentials return data from every other collection, so this is
not an auth failure — it is scoped visibility on `purchaseOrders`
specifically.

**Why it matters more than a normal outage.** A 0-row response is
indistinguishable from "this supplier has no POs". Someone reading an answer
today would conclude there are no purchase orders in the system. That is
worse than an error.

**Action.** Not fixable in code. Requires the Fusion user's procurement
access to be restored on dev49, or a different persona. **Mitigation worth
building regardless:** the tools should treat a collection that returns 0
while its partition is known-non-empty as suspicious. At minimum, surface
`total_available=0` distinctly from `total_available=None` so the
synthesizer stops asserting "none exist".

**Verify with:** `/purchaseOrders` returning >0, then re-run prompts 1–6.

---

## SP-004 — `/receivablesCustomerAccountActivities` returns 403

**Status: Open. Environment. Not code.**

**Prompts affected (4):** 24, 25, 28, 30 — all die inside
`get_customer_account_by_name`.

**Symptom.**

```
403 Forbidden for /fscmRestApi/resources/11.13.18.05/receivablesCustomerAccountActivities
```

**Evidence it is environmental.** The same session, same credentials:

| Endpoint | Result |
|---|---|
| `/receivablesCustomerAccountActivities` | **403** |
| `/receivablesInvoices` | 200 |
| `/standardReceipts` | 200 |
| `/invoices` | 200 |
| `/receivablesCreditMemos` | 200 |

**Regression note.** p25 and p28 returned 11 and 26 rows in run01. This is
the only *downward* movement between the two runs, and it is entirely
access — the plans are unchanged and correct.

**Action.** Restore the grant on dev49, or point the persona at a user that
has it. **Verify with:** re-run prompts 24, 25, 28, 30.

---

## SP-005 — `get_invoice_lines` reports a capped count as the total

**Status: REOPENED (2026-11-28). The data layer is fixed and merged; the
answer is still wrong.** PR #231 (`SP-005-line-count`, merge `e4bf061`) made
`total_available` truthful — it now reports 184 — but a manual re-run on the
merged code, after `./spire-host.sh --restart dev`, still prints:

```
invoiceline: 50 record(s)
Final raw output:     50 record(s) under 'invoiceline'
```

Two causes were left undone, and both are visible in the code:

1. **`src/spire/mcp_server/server.py:607`** — the MCP wrapper still declares
   `async def get_invoice_lines(invoice_id: int, limit: int = 50)`. The *tool*
   default was raised to 200; the executor calls the **wrapper**, and the plan
   passes no `limit` (`tool_args: {'invoice_id': '$iteration_value'}`), so 50
   is what reaches the tool. The fix was applied to the layer that is not
   called.
2. **The count sentence is model prose, not a template.** Two runs of the
   same prompt worded it differently — one said "contains 50 associated line
   items", the next mentioned no line count at all while the summary still
   read 50. Generated text is the signature. `local_list_summary`
   (`local_summary.py:205-222`) has the truthful sentences and this path does
   not call it.

Full walk with both reproductions and the corrected classification: **F-086**
in `docs/fixes/FIX_PLAN.md`. The earlier `Fixed` label is left visible in that
file rather than rewritten.

**Prompt:** 13 (scored `OK`, because a prompt returning rows scores `OK`
regardless of the sentence above them).

**Symptom.** The answer states *"50 line items"* for invoice `1601397`, which
has **184**.

**Evidence, before the fix.**

```
REST  /invoices/1601397/child/invoiceLines?limit=50
        items returned = 50
        count          = 50      <- capped, not the true total
        hasMore        = true
Pod   SELECT COUNT(*) FROM AP_INVOICE_LINES_ALL WHERE INVOICE_ID=1601397  -> 184
```

**Root cause.** `total_available=len(projected)`. Because REST reports
`count` as the *page* size on this child resource, the tool always claimed
"this is everything". `truncated` then computed False, so no disclosure was
emitted. The same three lines were copied into four sibling child tools.

**What the probe found, and why the fix is better than planned.** The
original plan was to read `hasMore` and leave the total unknown — an
"at least 184" answer. `totalResults` turns out to be honoured on this child
resource, so the total is knowable exactly. Measured on dev49, same invoice:

```
limit=50    count=50  hasMore=True   totalResults=184   items=50
limit=100   count=58  hasMore=False  totalResults=58    items=58
```

`count` is `min(total, limit)` and carries no information the caller cannot
already see. `totalResults` is the true total. The AR invoice-lines child
honours it too (`receivablesInvoices/1002/child/receivablesInvoiceLines`
→ `totalResults: 4`). The PO lines child could not be probed: PO `2144`
404s and `/purchaseOrders` returns 0 rows (SP-003).

**Fix, as landed — the data layer only.**
1. New `child_page_count(response, items)` in `tools/tool_result.py`, shared
   by all five tools — one implementation, because five copies is how the
   bug spread. Returns `(total_available, capped)`: `totalResults` when
   present, else `capped=True` with an unknown total when `hasMore`, else
   the page is complete and its own size is the total.
2. `ToolResult.build(..., capped=False)`. Without it, `total_available=None`
   also forces `truncated=False`, so "unknown" would render as "complete" —
   the same defect in quieter clothes.
3. All five child tools send `totalResults=true`:
   `get_invoice_lines`, `get_purchase_order_lines`,
   `get_receivables_invoice_lines`, `get_receivables_invoice_tax_lines`,
   `get_receivables_invoice_transaction_dff`. The last two were found by
   grep, not by the original report.
4. `get_invoice_lines` default limit 50 → 200, so an ordinary invoice
   returns in full instead of being capped at a round number. Pagination is
   deferred: no invoice on dev49 exceeds 200.
5. `tests/test_line_counts.py` — 23 tests: the helper's three cases,
   `ToolResult.build`'s combinations, and all five tools parametrised ×3
   (capped with a total, complete, and a pod that omits `totalResults`).

**Not verifiable live, and said so rather than glossed.** The PO half cannot
be exercised (`/purchaseOrders` 0 rows, SP-003); the AR customer-account
endpoint 403s (SP-004). Unit tests are their only proof. The AP half is
verified against the pod — at tool level. **Not at answer level, which is why
this row is open.**

**Still to do.**
1. Raise the wrapper default at `server.py:607` to 200.
2. Make the child-lines answer quote `total_available` instead of leaving the
   count to the model.
3. Check whether other wrappers in `server.py` carry the same divergence
   between wrapper default and tool default — only this one was inspected.

**Effort:** S for the wrapper, M for the prose. **Verify with:** p13 on the
merged fix — it must state **184** (or "50 of at least 184"), and two runs
must word the count the same way.

---

## SP-006 — genuine filter/parser gaps

**Status: Open. Triage before building anything — three of these may be
legitimate refusals.**

Nine prompts refuse because a filter does not exist. They are grouped here
because each needs its own decision, not because they share a fix.

| # | Prompt asks for | Refusal | Assessment |
|---:|---|---|---|
| 7 | POs by buyer | no buyer filter | **Unverified** — p8's 0-row issue prevents testing; buyer is on the header |
| 8 | POs pending approval | `cannot be filtered by 'pending'` | Likely buildable — `DOCUMENT_STATUS` exists |
| 9 | POs with overdue shipments | no schedule status predicate | Buildable — schedules carry `SCHEDULE_STATUS` |
| 10 | PO amount by supplier, current month | no date range on this aggregation | Buildable — the aggregation exists, only the date bound is missing |
| 15 | Invoices on hold | no hold-status filter | Likely buildable — `HOLD_FLAG` / `APPROVAL_STATUS` on `AP_INVOICES_ALL` |
| 23 | Customer accounts by status | `CustomerAccount cannot be filtered by 'status'` | **Blocked by SP-004** — endpoint is 403 |
| 26 | Receipt application details | `unparseable` — no `target_entity` | Parser gap; `get_account_receipt_applications` exists |
| 27 | Unapplied / partially applied receipts | no receipt-status filter | Buildable — applications carry `ApplicationStatus` |
| 29 | Credit memo by id | `CreditMemo cannot be filtered by 'by_id'` | **Possibly legitimate** — a `CreditMemoId` REST filter returned an error when probed |

**Not a gap:** p19 (duplicate invoices) refuses with `unsupported_operation`
because duplicate detection genuinely needs cross-record logic. That refusal
is correct and should stay.

**Action.** For each of the nine, first probe the pod/REST for the carrier
column. Only then decide build vs document-as-unsupported. Do not batch-fix
them — p29 may turn out to be correct as-is, and the pattern this folder was
created to catch is exactly "an SME-answerable refusal recorded as a
coverage gap".

---

## Closed

| ID | Was | Closed by | Evidence |
|---|---|---|---|
| F-077 | AP invoice lines refused as "not in the API schema" | PR #225 | p13 refusal → 51 records (run02) |
| F-078 | Tool args with no `FilterSpec` emitted `-- unmapped` SQL | PR #220 | 10 `BADSQL` → 0 (run02) |
| F-082 | AR invoice *number* bound to `CUSTOMER_TRX_ID` | PR #221 | p22 0 → 1 row (run02) |
| SP-005 | A child's page size stated as the collection total | PR #231 (data) + PR #233 (delivery) | p13 says **184** twice on a restarted stack |
| AP-1 | Invoice's KG vocabulary was narrower than the tool projection | this branch | p12, p11, p14 all render `DueDate` / `Supplier` / statuses live |

Full records for these are in `docs/fixes/FIX_PLAN.md`.

## SP-005 and AP-1 — what the two closures actually changed

Both were the same shape: a value the pipeline **already held** was not
shown, so the refusal described a boundary that did not exist.

**SP-005 needed two PRs, and the first one was recorded as fixed when it was
not.** PR #231 made `total_available` truthful — 184 instead of 50 — and the
answer still said "50 line items", because an iterating step's truncation
metadata reached `metadata_by_step` and never `truncation_by_step`, which is
the map the model's prompt is built from. PR #233 closed it. The lesson is in
F-086's S8: the run scores by row count, so it has no slot for narration —
which is why a rule already in `WORKING_STYLE.md` ("a page count is not a
total") did not prevent five tools from doing it.

**AP-1 needed three layers, and each one alone would have looked like a fix:**
the KG had to accept the name (2 `kg_entity_field` rows + the `supplier name`
synonym), `InvoiceRecord` had to carry the value (`due_date`, `paid_status`,
`approval_status`), and the renderer had to print a column when one exists.
Adding only the KG rows would have moved the refusal from the parser to the
record; adding only the record would have left the parser refusing.

Live evidence, dev49, 2026-11-28, after `./spire-host.sh --restart dev`:

```
p12  fields: ['Supplier','InvoiceDate','DueDate','InvoiceAmount',
             'InvoiceCurrency','PaidStatus']
     table: Supplier | InvoiceDate | DueDate | InvoiceAmount |
            InvoiceCurrency | PaidStatus
     only 'BusinessUnit' still refused

p11  table: InvoiceNumber | Supplier | InvoiceDate | InvoiceAmount |
            ApprovalStatus | PaidStatus
     "supplier name" and "status" both resolve now

p14  table: InvoiceNumber | InvoiceDate | DueDate | InvoiceAmount
     only 'remaining balance' still refused — that is AP-2, not AP-1
```

`Available columns` now lists 15 Invoice fields, including `DueDate` and
`Supplier`, so a refusal at least hands the reader a real menu.

## Recommended order

1. **SP-003** — investigate first; it blocks the entire procurement module
   and makes every PO answer silently wrong. Not a code fix, but until it is
   resolved the procurement prompts cannot be scored at all.
2. **SP-001** — 6 prompts for one parameter; highest ratio of prompts
   unblocked to work.
3. **SP-005** — the only *incorrect* answer still being produced. Everything
   else on this list is a refusal, which is at least honest.
4. **SP-002** — 1 prompt, REST already answers it.
5. **SP-006** — triage the nine individually; expect at least one to be a
   correct refusal.
6. **SP-004** — environment; cannot be fixed here.
