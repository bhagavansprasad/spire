# SPIRE — Invoice status: SME acceptance criterion and design shape

**Window 35 (Invoice Status Investigation).** Companion to
`docs/plan/HANDOFF.md` (window-34 anchor). Window 34 was investigation
only; this file states what a correct answer to each of the five
prompts looks like, and what shape a fix would take. No code was
changed to produce it.

Live pod for every measurement cited here:
`fa-euth-dev20-saasfademo1.ds-fa.oraclepdemos.com`. Confirmed against
the pod during this window (`totalResults: 53198` for /invoices). See
HANDOFF.md §6 for the pod discrepancy that window 34 left open.

---

## 1. The rule this criterion is written under

WORKING_STYLE.md **Rule 28** (the SME test): if a Fusion SME, given a
prompt and read access to Fusion, could produce an answer, the prompt
is answerable, and Spire's refusal is a **defect** — not a coverage
gap, not a narrowing of scope, not an observation. All five prompts in
HANDOFF.md §1 pass the SME test. The criterion below is the standard
their answers must meet.

---

## 2. What the SME would answer — one paragraph per prompt

Each paragraph is the *shape* of a correct answer: the columns, the
scope, the verdict, the disclosure. Representative counts come from
window 34's measurements on the same pod.

### 2.1 Prompt 1 — "Which invoices are yet to be paid?"

The SME reads "yet to be paid" as the AP ledger's not-yet-settled set
and produces the full list, not a page: Supplier, InvoiceNumber,
InvoiceDate, DueDate, InvoiceAmount, InvoiceCurrency, PaidStatus —
sorted by InvoiceDate or DueDate, with the true row count as the
opening line ("9,552 invoices, plus 9 partly paid, on this pod"). On
Fusion's data model that is `PaidStatus='Unpaid'`, optionally extended
to `IN ('Unpaid','Partially paid')`; the phrase does not resolve to a
single value, and the answer must say which reading it used. **No
supplier filter**: "supplier" is a category, not a constraint — the
whole ledger is supplier invoices. The one wrong answer is a capped
sample presented as the whole; a real SME says "9,552" before showing
any rows.

### 2.2 Prompt 2 — "Which supplier invoices are currently outstanding?"

Same set as prompt 1, same columns, same count. "Outstanding" in AP
means "not settled" — the ledger's `PaidStatus` field is exactly that.
The word "supplier" is again redundant. The SME gives the same answer
as prompt 1 and notes that if the user meant "past due," that is
prompt 4 and a different question.

### 2.3 Prompt 3 — "Which invoices are still unpaid?"

Same set again. "Yet to be paid," "outstanding," and "unpaid" name the
same ledger state in AP parlance. The three prompts are three
spellings of one query, and the correct answer is identical: the
`PaidStatus IN ('Unpaid','Partially paid')` invoices with their
identifying columns, and the true count. An SME does not treat these
as three questions.

### 2.4 Prompt 4 — "Are any supplier invoices overdue and requiring attention?"

A different question, and the SME treats it as such. There is **no
`Overdue` field on the pod and no `Overdue` query clause** — "overdue"
is a compound predicate: `PaidStatus != 'Paid' AND DueDate < today`.
Nearly all of the pod's unpaid invoices satisfy it (the data spans
2012–2026 and today is October 2026), so the answer is **not a list
but a verdict plus a ranked list**: "Yes — N invoices totalling X are
past due. The oldest is INV-… (DATE); the largest is INV-… (AMOUNT)."
"Requiring attention" resolves to "the ones an AP manager would work
this week" — largest by amount, oldest by days past due — with the
true total disclosed. Dumping every overdue row and calling it a day
is not what an SME does.

### 2.5 Prompt 5 — "Which invoices have been pending for a long time?"

The one prompt an SME would ask to have clarified. **"Pending" is not
one thing on this pod** — `ApprovalStatus='Required'` (not started),
`ApprovalStatus='Initiated'` (in motion), `InvoiceStatus='Pending
approval'`, `InvoiceStatus='Pending control check'`, and under a
looser reading `PaidStatus='Unpaid'`. An SME picks the dominant
reading (in AP, "pending" usually means "pending approval"), **states
it explicitly**, and answers: `ApprovalStatus='Required'` with a
90-day age threshold (the pod's 500-newest sample has 376 over 90 days
old — a live backlog, not demo artefacts), sorted oldest-first, with
the count. The answer names the reading and offers the alternative
("if you meant pending payment, that is a different set") so the user
can correct in one turn. Guessing silently, or refusing because
"pending" is ambiguous, are both wrong.

---

## 3. The consolidated reading

| # | Prompt | Ledger reading | Correct answer shape |
|---|---|---|---|
| 1 | yet to be paid | `PaidStatus IN ('Unpaid','Partially paid')` | full list; columns + count |
| 2 | currently outstanding | same | same set, same columns, same count |
| 3 | still unpaid | same | same |
| 4 | overdue, requiring attention | `PaidStatus != 'Paid' AND DueDate < today` | verdict + ranked list (largest, oldest); true total disclosed |
| 5 | pending for a long time | `ApprovalStatus='Required'` (default, disclosed) | oldest-first, count, alternative reading named |

**Three collapse; two differ.** Prompts 1, 2, 3 are one query in three
phrasings. Prompt 4 adds a second dimension (`DueDate`) that the
ledger carries but no filter exposes. Prompt 5 is genuinely ambiguous
on the pod — the correct shape is "state the reading, answer, offer
the other."

---

## 4. The four open questions from HANDOFF §7, answered

### 4.1 Which status field does each word map to?

| Word | Filter reading |
|---|---|
| unpaid | `PaidStatus IN ('Unpaid','Partially paid')` |
| outstanding | same as unpaid — a synonym in AP parlance |
| still unpaid | same as unpaid |
| overdue | no field; a **compound predicate** `PaidStatus != 'Paid' AND DueDate < today` |
| pending | `ApprovalStatus='Required'` **by default**, with the alternatives named in the answer |
| paid / partially paid | the positive readings; no prompt names them |

### 4.2 Does "unpaid" include "partially paid"?

Yes. Nine rows on this pod, but the argument is not the count. The
endpoints reference (2026-07-29, line 1583) already warns that
treating `PaidStatus == 'Paid'` as the whole of "settled" silently
drops partials. The same argument runs in reverse: treating "unpaid"
as only `'Unpaid'` silently drops the 9 partials, which are by
definition not-yet-fully-paid. The answer discloses the split
("9,552 unpaid at all, plus 9 partly paid") rather than collapsing it
into one number.

### 4.3 How is "overdue" expressed?

As a **new entity-level boolean filter** `overdue` on `Invoice`,
registered in `kg_entity_filter` with `tool_arg_name='overdue'`.
`search_invoices` gains `overdue: bool = False`. The tool sends the
**single server clause** `PaidStatus='Unpaid'` (composite `q=` is
forbidden on this pod — HANDOFF §3.5) and applies `DueDate < today`
client-side. **`DueDate` must be added to `search_invoices`'s
`_PROJECTED_FIELDS`** — it is not there today, and without it the
tool cannot return the field the client-side test needs.

The 9 `Partially paid` rows are lost in this reading because they
cannot ride the same server clause; the answer discloses this as a
stated limitation of "overdue" as defined here.

**Why not a client-filter shape.** The executor's `client_filters`
support `equals` only (executor.py, `_apply_client_filters`). A
`< today` test and a `!= 'Paid'` test would both need operators the
executor does not have. Extending the executor's operators is a larger
change than adding one tool arg, and the tool is where the arithmetic
belongs — the executor's contract is join-key substitution, not
predicate evaluation.

### 4.4 What is "a long time"?

**Default 90 days (three months), disclosed in the answer.** This
matches the existing precedent for vague relative windows: the
`b_po_created_date.sysprompt` teaches `created_in_last_n_months =
{"months": 3}` for "recent purchase orders" with no explicit N. The
same discipline applies. The parser computes the ISO cutoff via the
existing `_compute_date_n_months_ago` helper; the LLM never does.

Spire is one-shot — no clarification turn. The default plus an
explicit note ("reading 'long time' as more than 90 days; say a
different threshold to change it") is the only honest shape. If the
user names a threshold, the parser picks it up as it does for any
relative phrase.

---

## 5. The design shape the `po_status` mirror implies

The endpoints reference (line 321) prescribes: "mirror the existing
`po_status` pattern but map to these display strings
(`"unpaid"` → `"Unpaid"`)." Reading `po_status` (window 34 §3, and this
window's `graph_kg` bundle) shows what the mirror actually requires —
and, just as importantly, what it does **not**.

**The `po_status` pattern is three pieces, not four:**

1. A `kg_entity_filter` row:
   `('PurchaseOrder','status','entity_level', tool_arg_name='status',
   vocab_kind='po_status', query_style='client_side',
   filter_field='StatusCode', filter_op='equals')`.
2. A `kg_vocabulary` kind `po_status` — term → canonical code.
3. A `search_purchase_orders(status=...)` parameter that filters
   client-side against `StatusCode`.

**The sysprompt adds no block.** `load_kg_menu()` reads `filter_types`
from `kg_entity_filter`; adding a row makes the filter type appear in
the parser's menu automatically. No `procurement/b_po_status.sysprompt`
exists.

**Mirroring `po_status` therefore means: three `kg_entity_filter`
rows, three new `search_invoices` args, and one new projection field —
not five.**

The three rows:

| entity_name | filter_type | mechanism | tool_arg_name | query_style | filter_field | filter_op | notes |
|---|---|---|---|---|---|---|---|
| Invoice | unpaid | entity_level | unpaid | server_q | PaidStatus | equals | Server clause: `PaidStatus='Unpaid'`. Client-side over-fetch also keeps `'Partially paid'` — see §4.2. |
| Invoice | overdue | entity_level | overdue | server_q | PaidStatus | equals | Server clause `PaidStatus='Unpaid'`; DueDate < today client-side. `query_style='server_q'` is the closest fit — the value applies the primary server clause and completes the predicate in the tool. A future `query_style` extension (`server_q_then_client`) would record the mixed nature more precisely; today it does not exist. |
| Invoice | pending | entity_level | pending | server_q | ApprovalStatus | equals | Server clause `ApprovalStatus='Required'` — the default reading per §4.1; the tool's answer discloses the reading. |

**No `kg_vocabulary` kind is added.** The `po_status` kind exists
because the term is a value translation ("open" → "OPEN"). For the
three Invoice-status filters the term IS the filter type — the user
types "unpaid" and the parser emits `filter_type='unpaid'`, with no
vocabulary lookup in between. Adding rows to `kg_vocabulary` would
require editing the CHECK constraint in `scripts/sql/kg_schema.sql`
and moving the four count-tracking sites the KG test names
(`tests/test_kg_metadata.py::test_kg_table_row_counts_match_v1_1`,
`scripts/print_kg.py`'s `expected_rows`, and the two `PROMPT Seeded
... (N rows)` banners in the seed file). None of that is needed.

**No `kg/loader.py` edit is needed.** `_format_vocabulary` renders only
four vocab kinds — but we add no kind, so nothing is dropped.

**`search_invoices` gains three boolean args** (`unpaid`, `overdue`,
`pending`), each adding its clause to the single-clause selection
logic. They are mutually exclusive in practice — "overdue" already
implies "unpaid," so a prompt naming both routes to `overdue`. The
single-clause discipline is not a limitation for the five prompts.

**`DueDate` is added to `_PROJECTED_FIELDS`.** This is the one change
that is required for the criterion (§4.3) but is easy to overlook,
because `DueDate` is a header field the pod already returns and the
tool's projection currently drops. It also allows the display to
render a due-date column that was never surfaced before.

**`AmountPaid` is not projected, and is not needed.** The five prompts
ask "which invoices," not "which payment." The endpoints reference
(2026-07-29) is already explicit that no payment document exists on
the AP path — that is a separate, already-documented gap.

---

## 6. What this file does NOT decide

- **Whether `paid` and `partially paid` also get filter rows.** They
  are the positive readings; no prompt in scope names them.
- **What "requiring attention" means beyond "largest by amount, oldest
  by days past due."** §2.4 commits to *a ranked list*; the specific
  ordering heuristic is a product decision.
- **Whether the `PaidStatus`-based `overdue` reading is the right one
  for a business whose invoices have `DueDate == InvoiceDate` on ~43%
  of rows.** The criterion says "verdict plus ranked list"; a future
  prompt set may want a different definition.
- **Whether a `payables/b_invoice_status.sysprompt` block is needed.**
  The `po_status` precedent needed none — the filter-type menu is
  generated from `kg_entity_filter` — but "likely" is not "verified,"
  and a next window should test the three new filter types against
  the parser before adding a block.
- **The pod discrepancy itself** (HANDOFF §6). Settled for this window
  only: the live pod is `fa-euth-dev20`, not the reference doc's
  `fa-esll-dev37` nor the persona's `fa-etaj`.

---

## 7. Cross-references

- `docs/plan/HANDOFF.md` — §1 the five prompts, §2 the code
  investigation, §3 the pod data, §7 the four open questions this file
  answers.
- `docs/plan/WORKING_STYLE.md` — Rule 28 (the SME test).
- `docs/reference/spire_fusion_endpoints_reference.md` — line 321 (the
  mirror-`po_status` directive), line 1583 (partials), line 1812
  (ordering), and the 2026-10-09 discovery block (this window's
  findings).
- `scripts/sql/kg_schema.sql` — `kg_entity_filter`, `kg_vocabulary`,
  and the `query_style` CHECK constraint referenced in §5.

---

*End of acceptance criterion.*
