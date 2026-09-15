# SPIRE — Tester Introduction

**What you're testing:** an early build of SPIRE, a system that turns a
plain-English question about your Oracle Fusion pod into a real answer
pulled live from Fusion.

**What it is not:** a chatbot, an assistant, a co-pilot. It is a
question-answer tool with a deliberately narrow scope. It only answers
questions about the Fusion modules and record types listed below. Out-
of-scope questions get a polite refusal, not a guess.

---

## How to access

- **URL:** _<your ngrok URL here — update per session>_

Open the URL in any browser. No login. The page shows a green
**Connected** badge when it can reach the backend. If it's red, wait a
moment and refresh.

The URL changes each time the tunnel is restarted. If a link stops
working, ask for the new one.

**Please do not share this URL further.** It reaches a live demo pod
with query limits.

---

## How to ask a question

Type your question in plain English. Press Submit.

- **Good:** "Show suppliers in the US with no invoices in 6 months."
- **Good:** "Top 5 suppliers by spend this year."
- **Good:** "Show PO 2144 and its lines."
- **Not useful:** "What can you do?" — SPIRE does not converse.
- **Not useful:** "Write me a summary of the supplier contract." — not
  a data question, out of scope.

---

## What SPIRE supports

### Fusion modules

Four. Questions about other modules (GL, HCM, SCM, projects, etc.) will
be refused.

| Module | What's in scope |
|---|---|
| **Supplier** | Supplier master, addresses, sites, contacts, business classifications |
| **Procurement** | Purchase orders, PO lines, PO schedules, PO distributions, buyers |
| **Payables** | Accounts-payable invoices |
| **Receivables** | AR invoices, AR invoice lines, AR invoice tax lines, AR invoice flexfields, customer accounts, customer transactions, credit memos, receipts, receipt applications |

### Common things you can ask for

**Suppliers**
- List suppliers by status (active/inactive)
- Find suppliers by country, name fragment, business relationship
- Suppliers with a site in a specific business unit
- Suppliers with a specific business classification
- Suppliers with open purchase orders
- Suppliers with no recent invoices
- Suppliers with an invoice over a specific amount

**Purchase orders**
- Show a specific PO by number, including its lines, schedules, and
  distributions
- POs by supplier, by status (open, closed, cancelled, etc.)
- POs created before or after a date
- Top suppliers by committed PO value
- PO status breakdown

**Payables invoices**
- Invoices for a supplier (by name or number)
- Invoices in a date range, in an amount range
- Invoices raised against a specific PO

**Receivables**
- AR invoices by invoice number
- AR invoices with their lines and tax lines
- Customer accounts by customer name, with balance and activity
- Customer transactions for an account
- Credit memos (list, or per-account)
- Receipts (list, or per-account, filtered by customer or site)
- Receipt applications

**Aggregations**
- Count of suppliers / invoices / POs
- Top N suppliers by spend, by PO value
- Receipts grouped by method
- Customer accounts ranked by open exposure

### What it will refuse

- Anything outside the four modules above
- Questions requiring a data source other than Oracle Fusion REST APIs
- Compound questions that need data the pods do not expose
- Vague questions without a clear entity or filter

The refusal message will tell you **why** and give you an example of
what to ask instead. Please share those with us — they're often the
signal we need.

---

## What to look for while testing

Three things, in priority order.

**1. Wrong answers.** The pipeline cross-checks every ID in the answer
against the source data, so an invented ID should be impossible. If
you see one anyway, that's the most valuable bug you can report.

**2. Empty answers that shouldn't be empty.** "No suppliers found" when
you know suppliers exist. The pipeline is honest about emptiness — but
the filters might be too narrow.

**3. Refusals on questions that should work.** SPIRE tries to answer
honestly rather than guess; a refusal on a question you think is in
scope is useful feedback.

---

## Known limits (not bugs)

- **Truncation.** Aggregate questions scan a page-capped slice of the
  pod. The answer says so plainly when it happened — look for
  "Showing N of M" in the answer text. Not a defect.
- **No history.** Each question is independent. The page does not
  remember previous questions.
- **No follow-ups.** "Show me the same but for the UK" will not work.
  Ask the full question each time.
- **Latency varies.** Some questions scan a lot of pod data and take
  30–60 seconds. The UI shows a spinner.
- **The pod is a demo instance.** Some data may be incomplete or
  synthetic. If something looks suspicious but is internally
  consistent, tell us; don't assume.

---

## How to report feedback

For each item please include:

1. **The exact question you asked** (copy-paste)
2. **What you saw** (screenshot or copied answer text)
3. **What you expected** (one sentence)
4. **When** (roughly — the pod data changes)

Send to: _<your contact>_

Short feedback is fine. "Asked X, got Y, expected Z" is enough.