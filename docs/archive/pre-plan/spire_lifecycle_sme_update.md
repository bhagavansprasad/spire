# Spire — PO Lifecycle Status

**Prompts and results, 2026-07-29**
Pod `fa-esll-dev37` · every result below is verbatim output, not a mock-up

---

## What this covers

Section 4.A of the P2P prompt catalog — *Complete PO-to-Payment Lifecycle*.

Five of its ten prompts now answer end to end: **A.2, A.3, A.4, A.7 and A.10.**
They ask different questions of the same underlying reconciliation, which
assembles one purchase order across six Fusion resources — PO header,
schedules, AP invoices, invoice installments, supplier, and supplier site.

Two purchase orders are used throughout, chosen because between them they
exercise every state:

| PO | Supplier | Status | Why it was chosen |
|---|---|---|---|
| **701337** | JGA | Open | Partly received, mixed line statuses, and no AP invoice can be matched |
| **162034** | Lee Supplies | Closed | Fully received, invoiced and paid — but carries an unexplained 72.01 |

---

## The three worth reading first

### 1. A.4 — "Has PO 701337 been fully received, fully invoiced, and fully paid?"

```
PO 701337 — JGA
  Received: no · Invoiced: no · Paid: cannot be determined
  Stage: Awaiting receipt  ·  Owner: Supplier / Receiving  ·  Risk: Medium

Amounts (USD):
  Leg              Amount    Remaining
  Ordered        1,235.00            —
  Received         398.00       837.00
  Invoiced         398.00       837.00
  Paid                  —            —
    Received: derived from quantity — the pod carries no received amount
    Paid: cannot be determined: the schedules record billing but no AP
          invoice carries this PO number

Outstanding lines:
   Line Status         Amount    Received  Outstanding
      1 Open         1,116.00      279.00       837.00
```

**The point of this one is the Paid row.**

The PO's schedules record 398.00 as billed. No invoice in Accounts Payable
carries this PO number. An earlier version reported *"398.00 remaining to
pay"* — asserting a debt when the truth is that the bill cannot be found.
Those are different statements, and only one of them is true.

It now says so, and routes the question to Accounts Payable rather than to
Payments. Payments cannot act on an invoice that does not exist.

The received figure carries a similar caution. `ReceivedAmount` is empty on
every schedule row on this pod, so the received amount is **derived** from
the received quantity. The answer says it is derived rather than presenting
it as a fetched figure.

---

### 2. A.7 — "Why is PO 701337 still open?"

Same underlying data, different emphasis. This one leads with the blockage.

```
Risk (Medium):
  - the paid leg cannot be determined
  - not fully received
  - not fully invoiced
  - PO payment terms differ from the site default

Recommended action:
  Accounts Payable: locate the AP invoice for this PO, or confirm none
  exists. Until then the payment question has no answer.

Supplier setup:
  - Supplier JGA (1254) is ACTIVE and Spend Authorized.
  - Site JGA Progress US is ACTIVE, purchasing enabled, pay enabled.
  - Invoice matching is 3 Way against Receipt.
  - PO payment terms (Net 30) differ from the site default (2/10 Net 30).

Unresolved:
  - schedules record 398.00 billed but no invoice carries this PO number
  - PayOnReceiptFlag is set on this PO — self-billing may explain the
    unmatched billing (unconfirmed)
```

Two things worth noting.

**The risk rating and the recommended action are computed, not written by a
language model.** The same question always produces the same rating, and the
reasons are always listed. A rating without its cause is an opinion.

**"Unconfirmed" stays unconfirmed.** `PayOnReceiptFlag` is set on this order,
which *may* mean Fusion is self-billing. That is offered as a hypothesis and
labelled as one. It is never promoted to a cause.

---

### 3. A.10 — "Executive summary for PO 162034 — value, delivery, invoice and payment status, risk, and what to do next."

```
PO 162034 — Lee Supplies
  Received: yes · Invoiced: yes · Paid: yes
  Stage: Complete  ·  Owner: Accounts Payable — review the unexplained
                            difference  ·  Risk: Medium

Amounts (USD):
  Leg              Amount    Remaining
  Ordered          758.00            —
  Received         758.00         0.00
  Invoiced         758.00         0.00
  Paid             830.01         0.00

Risk (Medium):
  - matched invoices disagree with the schedules

Recommended action:
  Accounts Payable: confirm the difference between the invoiced and billed
  amounts was intended. No payment action outstanding.

Unresolved:
  - matched invoices total 830.01 against 758.00 billed on the schedules
    (difference 72.01)
```

**This one is complete and still rated Medium**, and that is deliberate.

The invoice is 72.01 above the order. The PO header carries zero tax, so
PO-side tax does not explain it. Freight, an invoice-level tax or a price
variance could — none is recorded. The system reports the difference and
declines to guess the cause.

Over-invoicing is not treated as an error: tax, freight and price variance
all legitimately push an invoice above its order. But a closed, settled PO
carrying an unexplained 72.01 is not something a summary should wave through
as low risk.

---

## All 31 prompts and their results

Run 2026-07-29 against `fa-esll-dev37`. Every row below is from that run.
The full transcript is `scripts/prompts/08_lifecycle.txt`.

Read as: **✓** answered correctly · **✗** should have answered but did not ·
**—** refused, and refusing is the right answer.

### A.4 — status matrix

| | Prompt | Result | Time |
|---|---|---|---|
| ✓ | Has PO 701337 been fully received, fully invoiced, and fully paid? | Received: no · Invoiced: no · Paid: cannot be determined | 21.4s |
| ✓ | Has PO 162034 been fully received, fully invoiced, and fully paid? | Received: yes · Invoiced: yes · Paid: yes | 14.6s |
| ✓ | Show ordered, received, invoiced and paid amounts for PO 701337 with supplier details. | 1,235.00 / 398.00 / 398.00 / cannot be determined | 17.8s |
| ✓ | Is PO 162034 complete? | Yes — Complete, fully settled | 14.6s |

### A.7 — diagnostic

| | Prompt | Result | Time |
|---|---|---|---|
| ✓ | Why is PO 701337 still open? | Awaiting receipt · 837.00 outstanding on line 1 · Supplier/Receiving | 16.0s |
| ✓ | What is blocking PO 701337, and which team owns the next action? | Same, with the blockage and owner named | 16.5s |
| ✓ | Why has PO 701337 not been paid? | Paid leg unknown — no AP invoice carries this PO number | 16.8s |
| ✓ | Is anything blocking PO 162034? | Nothing outstanding; one unexplained 72.01 for AP to review | 14.8s |

### A.2 — end-to-end summary

| | Prompt | Result | Time |
|---|---|---|---|
| ✓ | Give me an end-to-end summary of PO 701337 from supplier setup through payment. | Setup, four legs, stage, owner | 16.9s |
| ✓ | Trace PO 162034 from supplier setup through to payment and tell me the current stage. | Complete | 14.5s |
| ✓ | Summarise PO 701337 and identify the current lifecycle stage and responsible team. | Awaiting receipt · Supplier/Receiving | 17.6s |

### A.10 — executive summary

| | Prompt | Result | Time |
|---|---|---|---|
| ✓ | Give me an executive summary of PO 701337 including risk and recommended action. | Medium risk, 4 reasons, one action | 18.0s |
| ✓ | Executive summary for PO 162034 — value, delivery, invoice and payment status, risk, and what to do next. | Complete, Medium risk on the 72.01 | 13.2s |
| **✗** | **What is the risk rating on PO 701337 and why?** | **Refused — see Gap 1 below** | 4.8s |

### A.3 — per-module status

| | Prompt | Result | Time |
|---|---|---|---|
| ✓ | What is the supplier status, approval status, receipt status, invoice matching status and payment status of PO 701337? | Supplier ACTIVE / Spend Authorized, 3-way match, paid unknown | 17.0s |
| ✓ | For PO 162034, show the supplier status, invoice approval status and payment status, plus any unresolved exceptions. | ACTIVE, paid, 72.01 exception | 14.0s |

### Rephrasing — the same question, six ways

All six route correctly. This matters: a user will not phrase it the way the
catalog does.

| | Prompt | Result | Time |
|---|---|---|---|
| ✓ | Has purchase order 701337 been received and paid? | Received: no · Paid: cannot be determined | 16.9s |
| ✓ | PO 701337 — received, invoiced, paid? | Same | 16.6s |
| ✓ | Tell me the lifecycle status of purchase order 701337. | Same | 16.7s |
| ✓ | What stage is PO 162034 at? | Complete | 14.5s |
| ✓ | Who is responsible for the next action on PO 701337? | Supplier / Receiving | 15.7s |
| ✓ | What is outstanding on PO 701337? | 837.00 on line 1 | 16.1s |

### Negative cases

| | Prompt | Result | Time |
|---|---|---|---|
| ~ | Has PO 999999999 been fully received, fully invoiced, and fully paid? | "No purchase order found" — correct, but worded poorly. See Gap 2 | 10.3s |
| ~ | Has PO DOES-NOT-EXIST been paid? | Same | 9.9s |
| — | Have all purchase orders been fully received and paid? | Refused — correctly | 5.5s |
| — | Compare the lifecycle of PO 701337 and PO 162034. | Refused — correctly | 5.0s |

### Existing routes — must not regress

These share vocabulary with the lifecycle prompts but belong to other
features. All five still behave exactly as they did before this work.

| | Prompt | Routed to | Time |
|---|---|---|---|
| ✓ | Show PO 162034 and its lines. | PO header + lines (unchanged) | 15.6s |
| ✓ | Show the invoices raised against PO 162034. | Invoice list (unchanged) | 12.2s |
| ✓ | Open POs for supplier JGA. | Existing guard — points at the supplier route | 4.8s |
| ✓ | Which suppliers have open purchase orders? | Supplier list (unchanged) | 92.7s |
| ✓ | Purchase orders created before 2015. | PO date filter (unchanged) | 30.8s |

---

## The refusals, explained

Four prompts were refused. **Three of those refusals are correct.** One is a
genuine gap.

### ✗ "What is the risk rating on PO 701337 and why?" — a real gap

> *The system does not track 'risk rating' for purchase orders.*

**This is wrong and is being fixed.** Risk *is* computed, and it appears with
its full reasoning whenever a broader question is asked — the executive
summary two rows above returns *Medium* with four reasons. The system simply
has not been told that risk asked **on its own** is in scope.

Nothing is missing from the data. It is one line of instruction to the
question-parser. **Ask for an executive summary and you get the risk today.**

### — "Have all purchase orders been fully received and paid?" — correct

> *The system can only check the lifecycle status of a single purchase order.*

The reconciliation resolves exactly one PO: it fetches that order's
schedules, its invoices, its installments, its supplier and its site — six
calls. Running that across every PO on the pod is a different feature
(a portfolio scan), not this one.

Refusing is the right behaviour. The dangerous alternative would be to
quietly answer for one PO, or to scan thousands and time out.

### — "Compare the lifecycle of PO 701337 and PO 162034." — correct

> *The 'lifecycle_status' filter only supports a single purchase order.*

Same reason. A two-PO comparison is a reasonable thing to want and is worth
logging as a feature request — but silently answering for only the first PO
would be worse than declining.

### — "Open POs for supplier JGA." — correct, and pre-existing

Refused by a guard that predates this work, and the refusal names the right
alternative: ask about the **supplier**, not the PO. Included here only to
confirm the new lifecycle route has not disturbed it.

### ~ The two non-existent POs — answered, but worded poorly

Asking about PO 999999999 correctly reports that no such order exists. The
sentence is right; the headline above it reads *"cannot be determined"* on
all three legs, which implies the order exists and cannot be assessed.

The data is correct. The wording is not. See Gap 2 below.

---

## Known limitations — please read before testing

Stated up front so they are not discovered mid-demo.

**Gap 1 — risk asked on its own is refused.**
Covered above. One line of parser instruction; the data is already there.

**Gap 2 — a non-existent PO answers awkwardly.**
Covered above. The verdict line should say "no such purchase order" rather
than "cannot be determined", which is reserved for a real order whose status
genuinely cannot be established.

**3. Payment documents are not available on this pod.**
"Has it been paid", "how much", "when was it due" and "is it on hold" are all
answerable. **"Which payment settled this invoice" is not** — no payment
number or payment date exists anywhere on the AP path in Fusion REST. This is
an absence in the API, not something still to be built.

**4. Invoice matching reports the rule, not the result.**
The answer can say *"3-way match required against receipt"* because that is
configured on the supplier site. It cannot say *"one of three invoices failed
matching"* — no per-invoice match result is exposed.

**5. Dates on this pod are 2013–2024.**
PO 701337 was raised in 2014. Any "days overdue" figure would be roughly
4,500 days, so ageing is deliberately suppressed unless an unpaid balance
genuinely exists. On production data this would work normally.

---

## Still to come from section 4.A

Five of the ten prompts are not yet delivered, and they share two causes:

- **A.1, A.5, A.6** need receiving documents and payment documents. Receipt
  numbers are the blocker.
- **A.8, A.9** need approval and receipt **dates** for a cycle-time timeline.
  Order, invoice and due dates exist; approval and receipt dates do not
  appear on the resources checked so far.

Neither has had a dedicated discovery pass yet.

---

## What would help most

1. **Two or three more purchase orders** to test against. The two above do not
   cover a *partly paid* invoice or an invoice *on hold* — both are handled in
   code but neither has been seen on real data.
2. **Your read on the 72.01 on PO 162034.** Freight? Invoice tax? If there is
   a business rule that explains it, it should be encoded rather than reported
   as an exception.
3. **Which of the five prompts matters most for the demo**, so the remaining
   polish goes to the right one.
