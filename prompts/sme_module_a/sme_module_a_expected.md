# sme_modules — expected answers and fill values

**Source.** Module A's SME prompt list, 4 modules × 10 prompts, captured
2026-11-21. Saved here as Spire's module-level litmus test.

**Companion file.** `sme_module_a_litmus.txt` is the runnable set — one
prompt per line, `#` comments carrying status, expected content and
evidence. This file holds the reasoning: the fill-value table, the
readiness ledger, and the traps that make an answer look wrong when the
data is fine (or look right when the query is wrong).

**Session record.** `PROMPT_SHEET_2026-11-21.md` (same folder) is the same
analysis in a one-page, per-prompt ✅/⚠️/❌ form — easier to skim, and the
version to hand to a non-technical reader. If the two disagree, this file
wins.

---

## 1. Why the placeholder values are the whole problem

Every one of the 40 prompts carries a `{PO_NUMBER}`-style placeholder. A
placeholder pointing at a record with **no children** returns an empty
list from Fusion — and an empty list is indistinguishable from Spire
being broken. Worse, it is indistinguishable from Spire being *right*.

So each value below was queried on the pod first, and its child counts
recorded. A prompt is only in this set with a value proved to return rows.

**Evidence** (all `runsql.sh`, all exit 0):

| File | What it proves |
|---|---|
| `t_f078_verify.csv` | 19 counts: PO children, window sizes, line/tax/app counts |
| `t_f078_verify2.csv` | buyer effective-dating, contact path, classification lookups |
| `t_f079_verify.csv` | Calvin Roth true count, receipts by account number, supplier addresses |
| `t_f078_q1..q13` (`.sql` + `.csv`) | the candidate-selection queries |
| `t_f078_cols*.csv` | column existence (three prompt-named columns do not exist) |
| `t_f078_kg.txt` | the 22 entities / 13 tools / 37 filters Spire actually has |

---

## 2. Fill values — verified populated

| Value | Use for | Verified content |
|---|---|---|
| PO **`55040`** (header `67`) | PO details, lines, schedules, distributions | 52 / 52 / 52, CLOSED |
| PO **`55250`** (header `1829`) | Pending approval | PENDING APPROVAL, 52 lines |
| PO **`UK555867`** (header `625877`) | Overdue shipments (gap prompt) | OPEN, 52 overdue schedules, 52 qty outstanding |
| Buyer **`Eleanor White`** (`300000076218768`) | POs by buyer (gap prompt) | **3,773** POs |
| Buyer **`Calvin Roth`** (`300000047340498`) | POs by buyer (alt) | **2,601** POs |
| Supplier **`Dell Inc.`** (`300000047414679`) | POs for supplier | 32 sites |
| AP invoice **`ERS-53004-755598`** (`1601397`) | Invoice details | 184 lines, 138,864.62, Staffing Services |
| AP invoice **`ERS-52987-751583`** (`1598382`) | Invoice details (alt) | 184 lines, 296,073.77, JGA |
| AR invoice **`112390`** (`1533822`) | AR details | 240 lines, 180 tax lines, Sykes Gym |
| AR invoice **`61765`** (`300000248096352`) | AR details (demoed) | 1 line |
| Customer **`ABC Application Software`** (`26360`) | Receipts | **2,329** receipts (pod-wide) |
| Receipt **`Brad-234`** (`300000347746566`) | Applications | 579 applications |
| Receipt **`2001`** | Partially applied | 100,000 amount, 10,000 unapplied |
| Receipt **`558877`** | Partially applied (alt) | 50,000 / 25,500 unapplied |
| Credit memo **`29822`** (`300000183145265`) | CM details | 24 lines, Bradshaw Hotels |
| Credit memo **`1457709_CM1`** (`1617974`) | CM details (alt) | 20 lines, Motique Gym |
| Supplier **`1262`** (EIP Inc, `300000047507499`) | Supplier master, all children | 22 sites, 45 contacts, 22 addresses, 3 classifications |
| Supplier **`1252`** (Lee Supplies, `300000047414503`) | Supplier master (alt) | 35 sites, 34 contacts, 4 classifications |
| Classification **`SMALL_BUSINESS`** | Suppliers by classification | 13 suppliers (of 11 lookup codes) |
| Classification **`HUB_ZONE`** | Suppliers by classification (alt) | 18 suppliers |

Window sizes used by the "last 30 days" prompts: **171** POs, **781** AP
invoices, **107** AR invoices (`TRX_CLASS = 'INV'`).

---

## 3. Readiness ledger

Legend: **PASS** = tool + filter exist, expect a correct answer.
**PARTIAL** = tool exists, a requested field does not. **GAP** = no
entity or filter; the prompt is unanswerable as written.

| Module | PASS | PARTIAL | GAP |
|---|---:|---:|---:|
| 1 Procurement | 6 | 2 | 2 |
| 2 Payables | 2 | 5 | 3 |
| 3 Receivables | 6 | 2 | 2 |
| 4 Supplier | 6 | 4 | 0 |
| **Total** | **20** | **13** | **7** |

### Module 1 — Procurement

| # | Prompt subject | Status | How to score it |
|---|---|---|---|
| 1 | POs last 30 days | PASS | 171 in window; totals derived per row |
| 2 | PO `55040` details | PARTIAL | pass if it uses `DOCUMENT_STATUS`; fail if it invents an approval-status field |
| 3 | PO `55040` lines | PASS | 52 |
| 4 | PO `55040` schedules | PASS | 52 |
| 5 | PO `55040` distributions | PASS | 52 |
| 6 | POs for `Dell Inc.` | PASS | supplier filter |
| 7 | POs by buyer `Eleanor White` | GAP | clean refusal naming "no buyer filter" = pass |
| 8 | Pending approval | PASS | 64 exist; `55250` is one |
| 9 | Overdue shipments | GAP | refusal = pass; `UK555867` holds the 52 rows |
| 10 | PO total by supplier, this month | PARTIAL | no by-supplier aggregate |

### Module 2 — Payables

| # | Prompt subject | Status | How to score it |
|---|---|---|---|
| 1 | AP invoices last 30 days | PASS | 781 |
| 2 | Invoice `ERS-53004-755598` | PARTIAL | pass if it says due date is unavailable; fail if it fabricates one |
| 3 | Invoice lines | GAP | no InvoiceLine entity |
| 4 | Unpaid for `Staffing Services` | PARTIAL | count is real (12,347 pod-wide) but includes zero-amount rows |
| 5 | Invoices on hold | GAP | not modelled |
| 6 | Overdue invoices | PARTIAL | filter exists, `DUE_DATE` absent → no "overdue days" |
| 7 | Payment details | GAP | no Payment entity |
| 8 | Validation/accounting status | PARTIAL | only `PAYMENT_STATUS_FLAG` |
| 9 | Duplicates | PARTIAL | listing for comparison is a pass; an asserted duplicate count is not |
| 10 | Outstanding by supplier | PASS | REST count is per-page — a page size stated as a total fails |

### Module 3 — Receivables

| # | Prompt subject | Status | How to score it |
|---|---|---|---|
| 1 | AR invoices last 30 days | GAP | `ReceivablesInvoice` has only `by_id` |
| 2 | AR invoice `112390` | PASS | 240 lines, 180 tax lines |
| 3 | Active customer accounts | PASS | sample-and-disclose list |
| 4 | Account `26360` | PARTIAL | 1 site; site list/profile not projected |
| 5 | Receipts for `ABC Application Software` | PASS | 2,329 pod-wide |
| 6 | Receipt `Brad-234` applications | PASS | 579; unapplied from the PMT schedule |
| 7 | Unapplied / partially applied | PASS | `2001`, `558877` |
| 8 | Credit memos for `Bradshaw Hotels` | PASS | account-scoped, not the top-level list |
| 9 | Credit memo `29822` | PARTIAL | 24 lines; invoice reference and reason not modelled |
| 10 | Overdue AR invoices | GAP | no overdue filter on AR |

### Module 4 — Supplier

| # | Prompt subject | Status | How to score it |
|---|---|---|---|
| 1 | Suppliers matching `Dell` | PASS | `name_fragment` |
| 2 | Supplier `1262` details | PARTIAL | 1262 is a supplier NUMBER, tool wants SupplierId or a name |
| 3 | Active sites for `1262` | PASS | 22 |
| 4 | Inactive sites | PARTIAL | inactive filtering is client-side at best |
| 5 | Contacts for `1262` | PASS | 45 |
| 6 | Addresses for `1262` | PASS | 22 |
| 7 | Classification `SMALL_BUSINESS` | PASS | 13 suppliers |
| 8 | Site assignments / payment terms | PARTIAL | payment method/terms may not be projected |
| 9 | Inactive suppliers | PARTIAL | 8 exist; carrier is `END_DATE_ACTIVE`, not `INACTIVE_FLAG` |
| 10 | Compare `1262` across 4 children | PASS | 22 / 45 / 22 / 3 — check all four counts |

---

## 4. Scoring

Same standard as the release gate: **the summary line proves nothing.**
Read the answers.

- **pass** — right rows, right claims.
- **fail** — errored, or refused a prompt marked PASS/PARTIAL.
- **wrong but did not error** — the bucket that matters. Check for:
  - an empty data array behind confident prose
  - a page size stated as a total ("25 suppliers" where 450 exist)
  - a total computed over a truncated sample and stated as fact
  - claims about fields that are not in the displayed projection
  - a field invented where the pod has no such column (see §5)
  - a generalisation true of the first rows but not the set

For the 7 GAP prompts: **a clean refusal naming the missing capability is
the pass.** Do not delete a GAP prompt when it keeps refusing — the
refusal is the ledger entry.

---

## 5. Traps found while verifying — read before calling an answer wrong

1. **Buyer counts double.** `PER_PERSON_NAMES_F` holds **2 rows** per
   `PERSON_ID` (effective dating). A naive join reports 7,546 for Eleanor
   White's **3,773** POs, and 5,202 for Calvin Roth's **2,601**
   (`t_f078_verify2.csv`, `t_f079_verify.csv`). One `PERSON_ID` can also
   carry two display names (`Camille Procurement` / `Camille Fredricks`).
2. **Supplier contacts do not join by `VENDOR_ID`.**
   `POZ_SUPPLIER_CONTACTS` has no `VENDOR_ID` column; the path is contact
   → `PARTY_SITE_ID` → `POZ_SUPPLIER_SITES_ALL_M.PARTY_SITE_ID`. The
   obvious join returns **0 contacts for every supplier**, which would
   make Module 4 #5 look like an empty supplier set.
3. **"Partially applied" is not `AMOUNT > SUM(applications)`.** Ordering
   by the applications sum returns only NSF/REV receipts with
   `applied = 0`. The carrier is the PMT schedule,
   `AMOUNT_DUE_REMAINING <> 0` — the F-075 lesson.
4. **Unpaid AP invoices default to zero amount.** The highest-line-count
   unpaid invoices are all `INVOICE_AMOUNT = 0` with 184 lines. Without an
   `INVOICE_AMOUNT > 0` guard, Module 2 #4 shows a screen of zeroes.
5. **Three columns named in the prompts do not exist on the pod.** Each
   confirmed by `ORA-00904`, not by assumption:

   | Prompt assumes | Reality | Use instead |
   |---|---|---|
   | `PO_HEADERS_ALL.AUTHORIZATION_STATUS` | absent | `DOCUMENT_STATUS` (F-064) |
   | `AP_INVOICES_ALL.DUE_DATE` | absent | no substitute — due date is unanswerable |
   | `POZ_SUPPLIERS.INACTIVE_FLAG` | absent | `END_DATE_ACTIVE` |

6. **F-076 touches every count.** All row counts here are pod-wide, across
   business units; REST returns the session BU only. A Spire count below
   these numbers is not "wrong" until the BU decision is made. Account
   26370 alone lives in three orgs (1,692 + 605 + 544).
7. **Effective-dated tables bite twice.** The buyer name table (§5.1) and
   `PER_ALL_PEOPLE_F` (which carries only `PERSON_ID`) both surprise: the
   name lives in `PER_PERSON_NAMES_F`, not the people table.

---

## 6. The short list — 8 prompts that would prove Spire works

Run these first when time is short. Each one fails a "call one endpoint
and echo it" implementation, so passing them is evidence of an actual
execution layer rather than a proxy.

| # | From | Prompt (fill value) | Why this one |
|---|---|---|---|
| 1 | 1.1 | POs last 30 days with total amount (171) | derived totals on every row, no stored column |
| 2 | 1.5 | Distributions for PO `55040` | 4-level chain; a wrong join returns plausible numbers |
| 3 | 3.6 | Applications for receipt `Brad-234` (579) | unapplied must come from the schedule, not the subtraction |
| 4 | 3.7 | Partially applied receipts (`2001`) | filter on a derived value no endpoint offers |
| 5 | 4.10 | Supplier `1262` across sites/contacts/addresses/classes | pure graph traversal, four edges, no single endpoint |
| 6 | 1.8 | POs pending approval (`55250`) | vocabulary mapping: "Pending Approval" → `DOCUMENT_STATUS` |
| 7 | 3.8 | Credit memos for `Bradshaw Hotels` | account-scoped traversal + derived amounts |
| 8 | 2.10 | Outstanding invoice by supplier, this month | aggregation where REST's count is per-page |

---

## 7. Running it

The MCP server must be up.

```
export PATH="/home/bhagavan/virtenv/spire/bin:$PATH"

# the whole set
python scripts/promptkit.py --run --prompt-file \
    prompts/sme_module_a/sme_module_a_litmus.txt
```

Not yet registered in `scripts/manifests/promptkit_sets.yaml`, so a full
`--manifest` run does not pick it up. Add the set name there when the
first baseline is recorded.

**No baseline yet.** Record wall-clock and the pass/partial/gap tally on
the first full run, then add it here.
