# AP (Payables) coverage assessment

**Purpose:** turn the 40-prompt SME run into an evidence-backed answer to
roadmap §5.2 question 2 — *which AP prompts are already covered, and which
expose a real gap?* This is the input to Gates 3 (MVP boundary) and 4 (data
and workflow model) for the first module.

**Evidence base:** [run02 results](../sme_prompts_status/run02_2026-11-28_results.md),
its raw log [evidence/t_f076_litmus_run.txt](../../../evidence/t_f076_litmus_run.txt),
the per-prompt dispositions in
[sme_module_a_litmus.txt](../../../prompts/sme_module_a/sme_module_a_litmus.txt),
the cross-run table [COMPARISON.md](../sme_prompts_status/COMPARISON.md), and
the open-defect records in [FIX_PLAN.md](../sme_prompts_status/FIX_PLAN.md).

**Code under test:** `master` @ `f1a528a` (F-076 and F-077 merged).
**Pod at run time:** dev49. **Written:** 2026-11-28.

---

## 1. Read the status codes as row counts, not verdicts

`run02` scores each prompt by what came back: `OK(n)`, `ZERO`, `REFUSED`,
`ERR403`, `BADSQL`. That code says **whether rows came back**, not whether the
answer is right, complete, or the question asked.

The gap is not hypothetical. AP scored **8 `OK` of 10**, and two of those eight
answers state a number that is wrong. So:

> `OK` ≠ pass. The verdict column below is mine, derived from the answer text
> in the run log against the prompt's declared disposition.

Three dispositions are in play (§ rules in the playbook, §4.2):

| Disposition | PASS means |
|---|---|
| `PASS-EXPECTED` | Correct and complete. |
| `PARTIAL-EXPECTED` | Clean answer that omits an unmodelled field. **Inventing it is a FAIL.** |
| `GAP-EXPECTED` | Clean refusal naming the missing capability. |

---

## 2. Headline

**AP is the strongest module in the set and the only one whose score is not
distorted by the pod**, because it does not use either broken endpoint
(SP-003 `/purchaseOrders` returns 0; SP-004 `/receivablesCustomerAccountActivities`
returns 403).

**8 of 10 prompts meet their declared disposition. 2 produce wrong numbers.**
That is a materially better result than the module had on 2026-11-21, when
five of these ten emitted invalid SQL.

But the 8 passes rest on a narrower base than the count suggests: four of them
pass *by declining* a column, and one of those declined columns is fetched by
the tool already — so the refusal is a defect, not a coverage boundary (§5,
AP-1).

---

## 3. Per-prompt verdicts

Evidence quoted from `evidence/t_f076_litmus_run.txt`.

| # | Prompt (short) | Expected | run02 | Verdict | Evidence |
|---:|---|---|---|---|---|
| 11 | Supplier invoices, last 30 days | PASS | `OK` 25 | **PASS**, with AP-1 | "Showing 25 of 157" — honest truncation. Refused `supplier name` and `status`, both present on the row. |
| 12 | Invoice details incl. due date | PARTIAL | `OK` 1 | **PASS** (no fabrication) | "*columns aren't available on Invoice: 'DueDate', 'BusinessUnit'*". Declines cleanly. AP-1. |
| 13 | Invoice lines for one invoice | GAP (stale) | `OK` 51 | **FAIL** | "The invoice contains **50** line items"; truth is **184** (SP-005). A confident false total. |
| 14 | Unpaid invoices for a supplier | PARTIAL | `OK` 25 | **PASS**, with AP-1 | "Showing 25 of 1,174"; "All 25 have Supplier Staffing Services". Declines due date and remaining balance. |
| 15 | Invoices currently on hold | GAP | `REFUSED` | **PASS** (correct gap) | `unsupported_filter` — no hold-status filter. Names the missing capability. |
| 16 | Overdue supplier invoices | PARTIAL | `OK` 25 | **PASS**, with AP-4 | "Showing 25 of 12,638"; declines due date and days-overdue; discloses "All 25 have InvoiceAmount 0". |
| 17 | Payment details | GAP | `OK` 1 | **PASS** (correct gap) | "(1 record(s) matched; no requested column was available.)" — no payment fields invented. |
| 18 | Validation / accounting status | PARTIAL | `OK` 1 | **PASS** (correct gap) | Same disclosure shape as p17. |
| 19 | Duplicate invoices | PARTIAL / gap | `REFUSED` | **PASS** (correct refusal) | `unsupported_operation`. See AP-5 — the two ledgers disagree on how to label this. |
| 20 | Outstanding by supplier, current month | PASS | `OK` 1 | **FAIL** | Answers a different question — see AP-2. Caveat done right: "PARTIAL: 25,000 of 53,170 invoices examined (47%). These totals are lower bounds." |

**Tally:** 8 pass, 2 fail. Of the 8 passes, 4 are *pass-by-disclosure*
(p12, p14, p16, p17/18) and 1 is a refusal (p15) — only p11 and p20 were
asked to answer outright, and p20 failed.

---

## 4. What the module can honestly promise today

| Capability | State | Basis |
|---|---|---|
| List invoices by supplier | Works | p14 |
| List invoices in a date window | Works, truncated honestly | p11 |
| Find one invoice by invoice number | Works | p12, p17, p18 |
| Invoice-level amount, currency, date, paid/approval status | Works | p11, p12, p14 |
| Invoice lines for one invoice | Works, **count is wrong** | p13 |
| Unpaid filter | Works | p14 |
| Overdue filter | Works, dominated by zero-amount invoices | p16 |
| Outstanding amount by supplier (aggregation) | Works, **measure and period mismatch** | p20 |
| Invoice due date | **Refused though fetchable** | p12, AP-1 |
| Supplier *name* as a requested column | **Refused though present** | p11, AP-1 |
| Invoices on hold | Refused (real gap) | p15 |
| Payment details | Refused (real gap) | p17 |
| Validation / accounting status | Refused (real gap) | p18 |
| Duplicate detection | Refused (correct by design) | p19 |

---

## 5. Defects found

### AP-1 — Invoice's KG field vocabulary is narrower than the tool's projection

**Severity: high. This is the difference between "we don't model it" and "we
fetch it and refuse to show it".**

`tools/invoices.py` projects 15 fields, including `DueDate` and `Supplier`.
`kg_entity_field` declares 13 for `Invoice` and omits both.

Evidence, same run, same invoice:

- p17's executor row contains **`'DueDate': '2026-12-04'`**.
- p12 asks for the due date and is told *"the following columns aren't
  available on Invoice: 'DueDate'"*.
- p11 asks for "supplier name" and is told `'supplier name'` is unavailable,
  while `build_invoice_records` renders `supplier_name` from `Supplier` and the
  row carries it.

Two follow-on gaps make this worse:

- `kg_vocabulary` has `field_synonym` `'vendor name' -> Supplier` but not
  `'supplier name'`. The legacy EBS synonym is mapped; the everyday phrase is
  not.
- `InvoiceRecord` (`synthesizer/p2p.py`) has no `due_date`, so even once the KG
  accepts the request the deterministic list path cannot render it. This is the
  same gap recorded in playbook §6.6, now with a user-visible symptom.

**By the repository's own standard this is a defect, not a coverage gap:** an
SME-answerable question ("what is the due date") is refused.

**Fix:** add `kg_entity_field` rows for `Invoice.DueDate` (`date`) and
`Invoice.Supplier` (`display_name`); add `field_synonym` `'supplier name' ->
Supplier`; add `due_date` to `InvoiceRecord` and its builder; rebuild the KG
and regenerate the classifier menu. Then re-run p11, p12, p14, p16.

**Effort:** S. **Risk:** low — additive, no query semantics change.

### AP-2 — p20 answers a different question, confidently

The prompt: *"total **outstanding** invoice amount grouped by supplier for the
**current month**"*. The answer: *"**Total Spend**"* over **53,170** invoices
— the whole collection — with no month filter.

Two silent substitutions:

1. **Measure.** "Outstanding" is unpaid balance. The `by_supplier` op ranks by
   invoiced spend (`aggregate_invoices_by_supplier`). Nothing in the answer
   says spend was substituted for outstanding.
2. **Period.** "Current month" produced no `date_from`/`date_to`. The tool
   accepts both; the plan did not set them.

The 47%-sampling caveat is exemplary — that part is exactly what §5.4 of the
playbook asks for. The failure is that a true caveat is attached to the wrong
measure.

**Fix:** two decisions, not one. (a) Teach the parser to emit the period for
this phrasing (tool already supports it). (b) Decide whether "outstanding by
supplier" is a new op — one-op-one-tool means a new tool, not a flag. Until
(b) is settled, the honest behaviour is to disclose the substitution in the
answer, which the current text does not do.

**Effort:** S for the period; M for the new measure. **Risk:** the second one
sets precedent for the aggregation registry.

### AP-3 — the invoice-line total is fabricated (SP-005, restated)

p13 states 50 lines; the invoice has 184. The child resource reports `count` as
the page size, the tool sets `total_available=len(projected)`, and `truncated`
therefore computes False — so no warning is emitted and the number reads as a
complete count.

The same construction is in `get_purchase_order_lines` and
`get_receivables_invoice_lines`, copied from one another. Fix all three
together or the identical bug survives in two modules (`FIX_PLAN.md` SP-005).

**Severity: highest.** Every other failure here is a refusal, which is honest.
This is the only AP answer that is *incorrectly confident*.

### AP-4 — the overdue set is dominated by zero-amount invoices

p16 reports 12,638 overdue invoices and then discloses "All 25 have
InvoiceAmount 0". The litmus predicted this on 2026-11-21: the unpaid filter
admits zero-amount rows, so an amount-ranked list of them looks broken.

The disclosure saves it from being a wrong answer, but the answer is still not
useful. Decide whether overdue should exclude zero-amount invoices by default —
and if so, say so in the answer rather than only in the caveat.

### AP-5 — the two ledgers disagree, and one is stale

| Prompt | `sme_module_a_litmus.txt` says | `COMPARISON.md` says |
|---:|---|---|
| 13 | `GAP-EXPECTED` — "No InvoiceLine entity or tool" | `OK(51)` after **F-077** |
| 19 | `PARTIAL-EXPECTED` — "list the invoices and let the reader compare" | "correct refusal" |
| 12, 14, 16 | "an answer that invents a due date fails" (because `AP_INVOICES_ALL.DUE_DATE` does not exist — `ORA-00904`) | — |

The due-date annotation is **SQL-specific and now misleading**. REST returns
`DueDate`; the column's absence from `AP_INVOICES_ALL` does not mean the field
is unavailable. That is exactly the conflation `STATUS.md` warned about, and it
is why p12 declines a field the pod actually returned.

Re-annotate the litmus file, or the prompt set will keep asserting a gap that
was closed and a SQL fact that does not govern REST. **Do not** delete or
rewrite the prompts themselves — only the disposition comments.

### AP-6 — "created" is read as invoice date, silently

p11's intent is `created_in_last_n_months`, which the planner forwards as
`invoice_date_after`. That substitution is deliberate and documented in the
parser context ("'Created' and 'raised' name the InvoiceDate column"), and on
this pod it barely matters — a live check on 2026-11-28 gave 162 invoices by
`InvoiceDate` and 170 by `CreationDate` in the same window.

But the answer never says which date it used, so a reader asking about creation
is silently given invoice dates. Low severity; disclose it, and keep the
roadmap's open question on SME intent.

*(The litmus's "781 invoices in the 30-day window" does not reproduce — the
live pod shows ~162. That is pod drift since 2026-11-21, not a code defect, and
it is a reminder to re-verify fill values before each run.)*

---

## 6. Recommended order

1. **AP-3 / SP-005** — the only incorrect-but-confident answer in the module,
   and the fix is shared with two other entities.
2. **AP-1** — cheapest ratio of prompts unblocked to effort (p11, p12, p14,
   p16, plus every future due-date question), and it removes a refusal that
   contradicts data the pipeline already holds.
3. **AP-2 period half** — the tool already accepts the dates; only the parser
   is silent.
4. **AP-5 re-annotation** — no code, but until it is done the prompt set and
   the ledger describe different systems.
5. **AP-4** — a product decision before a code change.
6. **AP-2 measure half** — needs the aggregation-registry precedent settled.
7. **AP-6** — disclosure only.

---

## 7. Effect on the roadmap gates

| Gate | State after this assessment |
|---|---|
| 1. REST feasibility | **Closed for AP.** Endpoints, fields, quirks and counts are captured in playbook §3 and the run logs. |
| 2. User task discovery | **Partly closed.** The 40-prompt set exists and is scored twice; SME confirmation of expectations is still owed, and the litmus annotations need AP-5's correction. |
| 3. MVP boundary | **Ready to decide.** §4 of this document is the capability matrix; §6 is the order. |
| 4. Data and workflow model | **In progress.** Prompt→endpoint mapping exists per prompt; AP-1 and AP-2 are the open modelling questions. |
| 5–8 | Not started; no module branch exists yet. |

---

## 8. What this assessment does not establish

- **It is not a claim that AP is complete.** Two prompts fail and four gaps are
  real refusals. The correct label is "partially supported with a measured
  boundary", which is what roadmap §5.1 asked for and what §4 now supplies.
- **It is not a regression report.** No AP prompt regressed in run02; the two
  failures are pre-existing shapes that survived F-077/F-078.
- **It does not cover a pod change.** The endpoints AP uses were healthy at run
  time. If `/invoices` degrades the way `/purchaseOrders` did, every AP number
  here needs re-taking before it is quoted.
- **It says nothing about SQL.** Due-date evidence above is REST evidence;
  the SQL column's absence is recorded in `../SCHEMA_DISCOVERY_METHOD.md`'s
  terms and remains a Track B question.
