# SPIRE — Invoice status investigation, window-34 handoff

**Window type:** investigation only. No code was changed, no branch was
created, no KG row was added, no prompt set was run.
**Purpose:** understand why Spire refuses five ordinary AP-invoice
questions, and gather the facts a design would need.
**Predecessor:** the window-33 handoff (SQL Overlay POC). Its content
lives on in `docs/design/SQL_OVERLAY_POC.md` and
`docs/design/sql_overlay/*`; this document supersedes it as the
current anchor.
**master tip:** `f2bb6a1` (unchanged from window 33)
**Successor:** the next window's handoff. Nothing was filed this
window — no F-NNN, no FIX_PLAN row, no code changed.

---

## 0. The rule that frames everything below

The user framed the rule during this window, in these terms:

> If a Fusion SME — given this prompt and read access to Fusion — could
> produce an answer, then the prompt is answerable and Spire must be
> able to answer it. A refusal on an answerable prompt is a DEFECT in
> Spire. It is never a valid narrowing of scope, never a coverage gap,
> never an observation, never "the user asked the wrong thing."

This is the frame the new window should carry. **Applied this window** — `docs/plan/WORKING_STYLE.md` now carries
**Rule 28** (the SME test) and a one-line gloss at S1 ("in-scope"
means an SME could answer it).

The rule's purpose is to stop the pattern of the last several windows,
where a refusal on an SME-answerable prompt was classified as a
"coverage note" rather than a defect. Coverage IS capability. Calling it
a note softens a defect into a neutral fact.

---

## 1. The problem

Five prompts:

1. Which invoices are yet to be paid?
2. Which supplier invoices are currently outstanding?
3. Which invoices are still unpaid?
4. Are any supplier invoices overdue and requiring attention?
5. Which invoices have been pending for a long time?

All five refused. Every one is an ordinary finance question a Fusion
SME could answer in minutes.

**Reproduction log:** `run_20261008_223735.log` (pasted in this window).
Two refusal shapes appeared:

| # | Prompt | Refusal | Router modules |
|---|---|---|---|
| 1 | Which invoices are yet to be paid? | `missing_identifier` | `['payables']` |
| 2 | Which supplier invoices are currently outstanding? | `unsupported_filter` | `['payables','supplier']` |
| 3 | Which invoices are still unpaid? | `missing_identifier` | `['payables']` |
| 4 | Are any supplier invoices overdue and requiring attention? | `unsupported_filter` | `['payables','supplier']` |
| 5 | Which invoices have been pending for a long time? | `unsupported_filter` | `['payables']` |

Prompts 2 and 3 are the same shape ("supplier invoices, unpaid") but
refused differently, because the router classified them differently. This
is worth noting but was not investigated further.

---

## 2. Investigation 1 — the code

Five bundles were read: `parser_context`, `parser_planner`,
`graph_kg`, `synthesizer`, and (partially) `mcp_server_tools`. The
finding is that the gap is not one layer deep — it is four, and all four
have to move for a payables invoice-status filter to work end to end.

### 2.1 Layer 1 — Parser vocabulary (`src/spire/nl_parser/context/`)

The payables `.sysprompt` blocks define these Invoice filters:

- `b_invoice_amount.sysprompt` → `invoice_amount`
- `b_invoice_date.sysprompt` → `invoice_date`, `older_than_n_months`,
  `created_in_last_n_months`
- `b_invoices_for_po.sysprompt` → `purchase_order`
- `b_invoices_for_supplier.sysprompt` → `supplier`, `invoice_number`
- `b_no_recent_invoices.sysprompt` → `has_no_recent_invoices` (supplier-side)

**No status filter.** No `b_invoice_status.sysprompt` exists. The word
"unpaid" appears only once in the payables blocks, and then in the AR
context (see 2.1.1).

### 2.1.1 The AR/AP collision (important)

`modes/m_open_invoices.sysprompt` defines `open_only=true` — but its
text is explicitly scoped to AR:

> "If a **customer-invoices** question (the CustomerAccount +
> by_customer_name + CustomerTransaction shape above) asks for only the
> OPEN, OUTSTANDING, or UNPAID invoices — e.g. 'open invoices for
> [name]' — set open_only=true."

The `by_customer_name` filter is described as **REQUIRED**. There is no
AP equivalent. This is why prompt 2 refused as `unsupported_filter` and
prompt 3 refused as `missing_identifier`: prompt 2 named "supplier",
prompt 3 didn't, and the model's route through the sysprompts diverged.

### 2.2 Layer 2 — MCP tool (`src/spire/mcp_server/tools/invoices.py`)

`search_invoices` accepts:

```
invoice_number, purchase_order, supplier_number, supplier_name,
invoice_date_after, invoice_date_before, amount_min, amount_max, limit
```

**No status parameter.** Even if the parser emitted one, the tool would
reject the kwarg at the Pydantic boundary.

Note: `PaidStatus`, `ApprovalStatus` are in `_PROJECTED_FIELDS` (the
data IS fetched). They are simply not filterable. **`DueDate` is NOT
in `_PROJECTED_FIELDS`** — the tool has no way to return it today,
which means any client-side "overdue" filter is impossible inside the
tool without adding the field.

### 2.3 Layer 3 — KG filter registry (`scripts/sql/kg_schema.sql`)

`kg_entity_filter` has 34 rows. Seven are Invoice filters:
`invoice_date`, `older_than_n_months`, `created_in_last_n_months`,
`invoice_amount`, `supplier`, `purchase_order`, `invoice_number`.

**No invoice-status row.** The KG has no concept of payment status as
a filter dimension.

### 2.4 Layer 4 — Synthesizer schema and display

- `InvoiceRecord` in `src/spire/synthesizer/p2p.py` declares:
  `invoice_id, invoice_number, invoice_date, invoice_amount,
  invoice_currency, supplier_name, supplier_number`. **No `paid_status`,
  no `due_date`.**
- The InvoiceResponse branch in `src/spire/rendering/formatters.py`
  renders columns: Invoice, InvoiceId, Amount, Currency, Date, Supplier.
  **No status column, no due-date column.**

### 2.5 The two refusal paths, confirmed from code

**`missing_identifier`** comes from `generate_plan` in
`src/spire/planner/planner.py`. It has a guard: a filterless Invoice
intent raises `RefusalError(MISSING_IDENTIFIER)`. The wording comes from
`_IDENTIFIER_GUIDANCE["Invoice"]` in `capability.py`:
*"Name the supplier, or give me the invoice number."*

**`unsupported_filter`** comes from `validate_intent` Step 3 in
`src/spire/nl_parser/intent_validation.py`. It collects every filter type
the KG does not know and refuses with UNSUPPORTED_FILTER. The wording
comes from `_FILTER_GUIDANCE["Invoice"]`:
*"Narrow by supplier or date instead."*

Both are correct given the vocabulary. Neither names the actual gap.

### 2.6 Code conclusion

The concept "invoice payment status" does not exist anywhere in the
chain. The parser has no word, the tool has no parameter, the KG has no
row, the schema has no field, the display has no column. Fixing the
first layer in isolation exposes the next, then the next. Every one is
small; every one is required.

---

## 3. Investigation 2 — the live pod data

All `curl` commands below were run in this window. **The pod they hit was
`fa-euth-dev20-saasfademo1.ds-fa.oraclepdemos.com`**, which is NOT the
same pod named in the persona file (`fa-etaj-saasfademo1`). See Section
6 for why this matters.

### 3.1 All raw evidence files on disk

```
t_invoices_status_sample.txt    5 invoices, first page
t_invoices_unpaid_count.txt     q=PaidStatus='Unpaid'
t_invoice_full_row.txt          1 full invoice, all ~100 fields
t_partially_paid.txt            q=PaidStatus='Partially Paid'  (0)
t_unpaid_and_supplier.txt       composite q=  (0)
t_invoice_total.txt             no clause
t_paid_count.txt                q=PaidStatus='Paid'
t_approval_notreq.txt           q=ApprovalStatus='Not required'
t_duedate_before.txt            q=DueDate<'2025-01-01'
t_approval_pending.txt          q=ApprovalStatus='Pending'      (0)
t_approval_approved.txt         q=ApprovalStatus='Approved'     (0)
t_paidstatus_onhold.txt         q=PaidStatus='On Hold'          (0)
t_invoice_status_batch.txt      500 invoices, no clause  (biased)
t_unpaid_batch.txt              500 invoices, q='Unpaid', desc
t_paid_recent_batch.txt         500 invoices, q='Paid', desc
t_required_recent.txt           500 invoices, q='Required', desc
t_allstate_recent.txt           500 invoices, no clause, desc
t_repo_status_search.txt        grep of docs/prompts/tests
t_ref_status_context.txt        endpoints reference — status hits
t_fixes_status.txt              FIXES.md — status hits
t_prompts_status.txt            prompts/ — status hits
```

All paths are repo-root relative.

### 3.2 Headline counts (this pod)

| Query | Count |
|---|---|
| Total invoices (no filter) | **53,198** |
| `PaidStatus='Paid'` | 43,637 |
| `PaidStatus='Unpaid'` | **9,552** |
| `PaidStatus='Partially paid'` | 9 |
| `ApprovalStatus='Not required'` | 44,673 |
| `DueDate<'2025-01-01'` | 48,598 |

**Paid + Unpaid = 53,189. Total = 53,198. Nine unaccounted.** These
are rows where `PaidStatus` is neither; likely null or blank. Two probes
(`'Partially Paid'` with capital P, `'On Hold'`) returned 0. A 500-row
batch found exactly 9 rows of `'Partially paid'` (lowercase p). So the
9 are `Partially paid`, and casing matters (see 3.4).

### 3.3 Field-value enumeration (the discovery that matters most)

Five state fields live on the invoice header, not one. A 500-row
newest-first sample gave:

| Field | Values observed (count in 500) |
|---|---|
| **`PaidStatus`** | `Paid` 208, `Unpaid` 283, `Partially paid` 9 |
| **`ApprovalStatus`** | `Not required` 425, `Required` 64, `Manually approved` 7, `Workflow approved` 2, `Initiated` 2 |
| **`InvoiceStatus`** | `Completed` 298, `Pending control check` 127, `Pending approval` 24, `Canceled` 18, `Available` 12, `Policy violations` 11, `Fully applied` 7, `Permanent prepayment` 3 |
| **`ValidationStatus`** | `Validated` 322, `Not validated` 127, `Canceled` 18, `Available` 12, `Needs revalidation` 11, `Fully applied` 7, `Permanent prepayment` 3 |
| **`FundsStatus`** | null 476, `Reserved` 9, `Not required` 8, `Reserved with warning` 4, `Not attempted` 2, `Not applicable` 1 |

**"Pending" is not one word on this pod — it is at least five.**
`InvoiceStatus='Pending control check'` (127),
`InvoiceStatus='Pending approval'` (24),
`ApprovalStatus='Required'` (64, unauthorised but not yet started),
`ApprovalStatus='Initiated'` (2, in motion), and `PaidStatus='Unpaid'`
(283, cleared but not paid). An SME listening to "pending invoices"
picks one of these by context.

### 3.4 Case sensitivity

Fusion `q=` matches exactly on the display string. `'Partially Paid'`
returns 0; `'Partially paid'` returns 9. The parser will need the exact
strings, not a normalized form.

### 3.5 Composite q= — confirmed failing again

`q=PaidStatus='Unpaid' AND SupplierNumber='1255'` returned **0** — even
though supplier 1255 (Dell) provably has unpaid invoices (InvoiceId
744103 was returned earlier by a single-clause query). This is the
third independent confirmation of the single-clause quirk already
documented in the endpoints reference.

**Design consequence:** any compound filter (e.g. "unpaid AND
overdue") must send ONE clause to the pod and filter the rest
client-side.

### 3.6 "Long time" — a live backlog, not a demo artifact

500 newest `ApprovalStatus='Required'` invoices, by age:

| Age | Count |
|---|---|
| < 30 days | 9 |
| 30–90 days | 115 |
| 90–180 days | 220 |
| > 180 days | **156** |

**376 of 500 are over 90 days old.** This is not 2012 demo data. This is
a live backlog of stuck approvals. Whatever "pending for a long time"
means, this is the population it would draw from.

### 3.7 Overdue is a compound predicate, not a value

The pod has `PaidStatus` and it has `DueDate`. It has **no `overdue`
field and no `overdue` query clause.** An SME computes "overdue" as
`PaidStatus != 'Paid' AND DueDate < today`. That is a shape of filter
Spire has no representation for — it is not a name to add.

### 3.8 DueDate is a real second dimension

Full invoice row shows both `InvoiceDate` and `DueDate` present. Sampled:

- Unpaid batch: `DueDate == InvoiceDate` on **213/500**
- Required batch: `DueDate == InvoiceDate` on **82/500**

So for roughly half of invoices the due date is the invoice date, for
the other half it is genuinely later. "Overdue" (`DueDate < today`) and
"old" (`InvoiceDate < cutoff`) are different questions.

### 3.9 Full field list — worth keeping

One row, all fields (from `t_invoice_full_row.txt`):
AccountCodingStatus, AccountingDate, AccountingStatus, AmountPaid,
ApplyAfterDate, ApprovalStatus, BankAccount, BankChargeBearer,
BaseAmount, BudgetDate, BusinessUnit, CanceledBy, CanceledDate,
CanceledFlag, ControlAmount, ConversionDate, ConversionRate,
ConversionRateType, CreatedBy, CreationDate, DeliveryChannel,
DeliveryChannelCode, Description, DigitalPaymentAccount,
DocumentCategory, DocumentFiscalClassificationCodePath, DocumentName,
DocumentSequence, DueDate, Exception, ExceptionCode,
ExternalBankAccountId, FirstPartyTaxRegistrationId,
FirstPartyTaxRegistrationNumber, FundsStatus, GoodsReceivedDate,
ImageDocumentNumber, InvoiceAmount, InvoiceCurrency, InvoiceDate,
InvoiceGroup, InvoiceId, InvoiceNumber, InvoiceReceivedDate,
InvoiceSource, InvoiceSourceCode, InvoiceStatus, InvoiceStatusCode,
InvoiceType, LastUpdateDate, LastUpdateLogin, LastUpdatedBy,
LegalEntity, LegalEntityIdentifier, LiabilityDistribution, PaidStatus,
Party, PartySite, PayAloneFlag, PayGroup, PaymentCurrency,
PaymentMethod, PaymentMethodCode, PaymentReason, PaymentReasonCode,
PaymentReasonComments, PaymentTerms, ProcurementBU, ProductTable,
PurchaseOrderNumber, ReferenceKeyFive, ReferenceKeyFour,
ReferenceKeyOne, ReferenceKeyThree, ReferenceKeyTwo,
RemittanceMessageOne, RemittanceMessageThree, RemittanceMessageTwo,
Requester, RequesterId, RoutingAttribute1..5, SettlementPriority,
Stream, StreamDefinitionCode, StreamDetailId, Supplier, SupplierIBAN,
SupplierNumber, SupplierSite, SupplierTaxRegistrationNumber,
TaxationCountry, TermsDate, UniqueRemittanceIdentifier,
UniqueRemittanceIdentifierCheckDigit, ValidationStatus, VoucherNumber.

Three of these are new discoveries relative to what `search_invoices`
projects today: `AmountPaid`, `InvoiceStatus`, `InvoiceStatusCode`.
Any of them could be what "pending" means.

---

## 4. Investigation 3 — the repo docs and prompt corpus

### 4.1 The endpoints reference already prescribes the pattern

`docs/reference/spire_fusion_endpoints_reference.md` line 321, dated
2026-05-20:

> "If you ever build invoice-status vocabulary in the KG, mirror the
> existing `po_status` pattern but map to these display strings
> (`"unpaid"` → `"Unpaid"`)."

This is the house directive. It is unambiguously prescriptive: use
`kg_vocabulary`, mirror `po_status`, map to display strings. It names
the exact example.

Three other endpoints-reference facts that constrain a design:

- Line 1583 (2026-07-29): **`AmountPaid` is on the header, and it is the
  only usable paid figure.** Summing `InvoiceAmount` gated on
  `PaidStatus == "Paid"` silently drops partial payments.
- Line 325: composite `q=` workaround already prescribed — one clause
  to the pod, rest client-side.
- Line 1812 (2026-08-02): **`/invoices` ordering is NOT stable.**
  Byte-diffing the same eight prompts twice, minutes apart, gave
  entirely different rows. Any paginated fetch on this collection MUST
  specify `orderBy`, or two runs of the same query return different
  answers with no error either time.

### 4.2 SURFACE.md — no prior position

`docs/prompts/SURFACE.md` (the capability inventory) was read in full.

- The `payables` module declares exactly one entity, one rootable
  target: `Invoice`.
- Combinations table names exactly three cross-module capabilities.
  None concerns invoice status.
- §8 ("Unmapped — capabilities the KG declares with no prompt coverage
  today") lists four candidates. AP invoice status is not one — it is
  not declared at all.
- §10.2 (the payables tier plan) lists what its prompt files *should*
  cover: supplier number, name, amount bound, date bound, refusal,
  projection, `purchase_order`, `invoice_number`. **No status filter
  anywhere in the plan.**

### 4.3 refusals/exhaust.txt — no blessing

`prompts/refusals/exhaust.txt` (the refusal contract file) was read in
full. It lists what Spire is *supposed* to refuse. Five flavor sections
(`unknown_entity`, `unsupported_filter`, `unsupported_operation`,
`missing_identifier`, `unparseable`).

**"Which invoices are yet to be paid" is not in this contract file.**
The refusals seen in this window were emergent, not designed.

### 4.4 The prompts corpus — a collision, not a gap

A `grep` across all of `prompts/` for the four terms found:

- **"unpaid" and "outstanding" appear only as AR prompts, always with a
  named customer.** e.g. `unpaid invoices for ABC Corporation
  Worldwide`, `outstanding invoices for ABC Application Software`.
  These map today to `CustomerAccount + by_customer_name +
  CustomerTransaction + open_only`, and they work.
- **"pending" appears only in PO prompts.** `purchase orders pending
  approval`, `purchase orders pending signature`, `suppliers that have
  pending POs`. Not one invoice prompt says "pending".
- **`prompts/payables/` produced zero hits.** The AP prompt files do not
  exercise these words at all.

**The corpus has taught Spire to read "unpaid"/"outstanding" as AR,
customer-scoped, and "pending" as PO-scoped. It has never taught the
AP-invoice reading.** Same English words, settled meaning elsewhere,
no seat for the AP sense.

### 4.5 The one piece of prior art

`prompts/retest/prompts.txt` line ~85 references a past run where a
prompt returned *"only 2 columns (SupplierNumber, PaidStatus)"*, and
under it sits an actual prompt:

> `For Lee Supplies, show invoice number, invoice date, invoice amount, and payment status for their invoices.`

**AP-invoice, supplier-scoped, asks for payment status — and works**
because it asks for `PaidStatus` as a *projected column*, not as a
*filter*. `PaidStatus` has been surfaced to users before. It has never
been used to narrow a query.

### 4.6 FIXES.md — no F-NNN touches this

Seventeen hits, all `(pending)` PR markers or an unrelated aggregation
test. Nothing in the fixes log has ever addressed invoice status.

---

## 5. The consolidated finding

**The gap is a vocabulary gap, not a scale gap.**

You hypothesized, at the start of the investigation, that "all unpaid"
would require a loop over every vendor, whereas a single-vendor query
would not. The pod disproves this: **`q=PaidStatus='Unpaid'` returns
9,552 invoices across all vendors in one call.** No loop, no per-vendor
scan. Every dimension the SME would use is filterable server-side, one
clause each:

| Dimension | Clause | Returns |
|---|---|---|
| Unpaid | `q=PaidStatus='Unpaid'` | 9,552 |
| Paid | `q=PaidStatus='Paid'` | 43,637 |
| Overdue (bare) | `q=DueDate<'2025-01-01'` | 48,598 |
| Approval state | `q=ApprovalStatus='Not required'` | 44,673 |

Composite clauses fail (single-clause rule). Every compound filter
("unpaid AND overdue") is one clause to the pod plus client-side
filtering on a small result set. That is a design pattern the reference
already prescribes.

**Why the five prompts fail, in one sentence:** the words "unpaid",
"outstanding", "overdue", "pending" have no representation as AP-invoice
*filters* anywhere in Spire's chain. They are taught as AR concepts
(`open_only`) and PO concepts (`po_status`). The AP reading was never
entered. This is why the same English word routes to a working answer
for customers and to a refusal for suppliers.

**The pattern is already prescribed.** Endpoints reference line 321
names the shape: `kg_vocabulary`, mirror `po_status`, map to display
strings. The design does not have to invent a pattern.

---

## 6. The pod discrepancy — MUST be resolved before the next window's data work

**Every measurement in this investigation came from
`fa-euth-dev20-saasfademo1.ds-fa.oraclepdemos.com`.**

The persona file and `.bashrc` read earlier in the session both said
`fa-etaj-saasfademo1.ds-fa.oraclepdemos.com`.

The endpoints reference itself, line 44, says the "active pod" for that
document is **`fa-esll-dev37`**. Three different pods are named across
the repo and the environment.

Total invoice count here is **53,198**. The repo's aggregation comments
cite **48,931**. Different pod, different count.

**This does not invalidate the REST-surface findings.** The values
(`'Paid'`, `'Unpaid'`, `'Partially paid'`, etc.) and the single-clause
quirk are product behavior, not pod-specific data — they will be the
same on every pod. But every concrete count in this document is
pod-specific and cannot be reconciled against repo numbers until the
pod question is settled.

**Next window action:** establish which pod is live before running any
new query that compares to a repo figure. One command settles it:

```
curl -s -u "$IKS_FUSION_USERNAME:$IKS_FUSION_PASSWORD" \
  "$IKS_FUSION_BASE_URL/fscmRestApi/resources/11.13.18.05/invoices?limit=1&totalResults=true" \
  | python -m json.tool | grep -E 'totalResults'
```

53,198 → `fa-euth-dev20`. 48,931 → `fa-esll-dev37` or one of the
persona alternates.

---

## 7. Open design questions — the next window's starting point

The investigation answered "is this answerable?" (yes) and "is the
pattern known?" (yes). It did not answer these four:

### 7.1 Which status field does each word map to?

The pod has five state fields. Every user word ("unpaid", "pending",
"overdue") maps to one or more of them. The mapping is a product
decision, not a data fact.

| Word | Candidate mappings |
|---|---|
| unpaid | `PaidStatus='Unpaid'` (9,552) — or `PaidStatus IN ('Unpaid','Partially paid')` (9,561) |
| outstanding | Same as unpaid? Or its own concept? |
| overdue | Compound: `PaidStatus != 'Paid' AND DueDate < today`. Not a value. |
| pending | Any of: `ApprovalStatus='Required'`, `ApprovalStatus='Initiated'`, `InvoiceStatus='Pending approval'`, `InvoiceStatus='Pending control check'`, `PaidStatus='Unpaid'` — five readings |

### 7.2 Does "unpaid" include partially paid?

Nine rows on this pod. Small, but the endpoints reference already
warned that summing by `PaidStatus='Paid'` silently drops partials
(line 1583). The same warning applies here in reverse — treating
"unpaid" as only `'Unpaid'` silently drops partials.

### 7.3 How does "overdue" get expressed?

Not a filter name. A filter shape: one clause to the pod
(`PaidStatus='Unpaid'`), then `DueDate < today` client-side. Spire's
chain has no representation for this shape today. Does it need one? Or
does the parser get taught a synthetic filter type that the planner
translates?

### 7.4 What is "a long time"?

No threshold exists in the user's prompt. Options:

- A default the chain supplies. 90 days is defensible (376/500 in the
  Required batch are over 90 days old).
- A value the user must state. `pending for more than 90 days`.
- A clarification the chain asks for. This is what the SME does.

None was decided.

---

## 8. What was NOT investigated

- **The `po_status` pattern itself.** Read as a form (vocabulary kind,
  display strings), never read as a precedent for how a new vocab kind
  is registered, tested, or wired into the parser. The next window
  should read `po_status` before designing `invoice_status`, because
  whatever we build should look like it.
- **`modes/m_open_invoices.sysprompt` and the AR `open_only` path.**
  This is the closest existing analogue — a "show me unpaid things"
  filter that works on the AR side. Reading how it was built is the
  single highest-value next step.
- **Any comparison against an SME's actual answer.** We confirmed Spire
  cannot answer; we did not confirm what the SME's answer would look
  like for each of the five prompts. That is worth capturing before
  design, because it becomes the acceptance criterion.
- **The `pytest -q` baseline** (which was green at 1290 passed) was
  captured but never used — this window made no code changes, so no
  regression check was needed.
- **POC-2.** The SQL overlay work was paused when this thread opened.
  The `all_tables` DB-reachability check for `localhost:1521/FREEPDB1`
  was never run. If POC-2 resumes in the next window, that check is
  still the gate.

---

## 9. Suggested next steps for the new window

In order:

1. **Resolve the pod.** One curl, one grep (Section 6). Cheap, and every
   comparison downstream depends on it.
2. **Read `modes/m_open_invoices.sysprompt` and the AR `open_only` code
   path.** This is the existing pattern for "show unpaid things." What
   Spire builds for AP should look like what already works for AR.
3. **Read the `po_status` vocabulary rows and their parser wiring.**
   Endpoints reference line 321 said mirror `po_status`; read it first.
4. **Capture the SME's answer to each of the five prompts.** Not by
   asking an SME — by writing, in one paragraph per prompt, what the
   correct answer would say. That becomes the acceptance criterion.
5. **Only then** answer the four open design questions in Section 7.
6. **Add Rule 28 to `WORKING_STYLE.md`** (and the S1 gloss) if the new
   window agrees with the framing in Section 0. Both edits were
   discussed and drafted but not made.

---

## 10. Files and prior reading

**This investigation's raw evidence:** all `t_*.txt` files in the repo
root (Section 3.1), plus `run_20261008_223735.log` in the repo root or
wherever it was placed by the caller.

**Bundles read this window:**
`parser_context`, `parser_planner`, `graph_kg`, `synthesizer`,
`mcp_server_tools` (partial).

**Key code paths to revisit:**
- `src/spire/nl_parser/context/payables/*.sysprompt`
- `src/spire/nl_parser/context/modes/m_open_invoices.sysprompt`
- `src/spire/mcp_server/tools/invoices.py` (`search_invoices`)
- `src/spire/planner/planner.py` (Invoice guard)
- `src/spire/nl_parser/intent_validation.py` (Step 3)
- `src/spire/nl_parser/capability.py` (`_FILTER_GUIDANCE`,
  `_IDENTIFIER_GUIDANCE`)
- `src/spire/synthesizer/p2p.py` (`InvoiceRecord`)
- `src/spire/rendering/formatters.py` (InvoiceResponse branch)
- `scripts/sql/kg_schema.sql` (`kg_entity_filter`, `kg_vocabulary`)

**Key docs to revisit:**
- `docs/reference/spire_fusion_endpoints_reference.md` (esp. lines
  44, 321, 325, 1583, 1812)
- `docs/prompts/SURFACE.md` (esp. §§2, 8, 10.2)
- `prompts/refusals/exhaust.txt`
- `prompts/retest/prompts.txt` (line ~85, the prior art)
- `docs/plan/WORKING_STYLE.md` (pending Rule 28)

---

*End of handoff.*