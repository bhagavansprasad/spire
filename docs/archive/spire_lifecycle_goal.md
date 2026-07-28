# Spire — Lifecycle Goal

**Date:** 2026-07-24
**Status:** statement of destination, not a build plan
**Audience:** internal — Bhagavan, Siva, future sessions

> **This document is capability-blind by design.** It describes what
> Spire must eventually answer. It deliberately does not consider what
> Spire can do today, which endpoints exist, or what would be difficult.
> Those questions belong in the expansion plan. Constraining the goal to
> present capability would produce a smaller goal, not a truer one.

---

## 1. The goal

**Spire answers questions about the state of a business object across its
full lifecycle** — not by fetching rows, but by assembling every document
that touches it, reconciling the amounts between them, detecting where
they disagree, and naming who must act next.

**The unit of answer is a business object in a lifecycle, not a query
result.**

PO 2144 is not a row in `/purchaseOrders`. It is a supplier, an approval,
four schedules, three receipts, three invoices, one hold, one payment,
and four unresolved exceptions. A system that returns the header row has
not answered the question.

### What this is not

| Not this | But this |
|---|---|
| Retrieve rows matching a filter | Assemble a lifecycle across systems |
| Describe what was returned | Reconcile what the documents say to each other |
| Report status fields | Detect where the documents disagree |
| List records | Name who must act, and how long they've had it |

---

## 2. Three capabilities this requires

None of these are retrieval. All three are new in kind, not degree.

| Capability | Meaning |
|---|---|
| **Reconciliation** | Ordered vs received vs invoiced vs paid, computed and shown to balance. Every figure traceable to rows |
| **Exception detection** | Rules that fire against assembled data — an invoice billing undelivered goods is not a field on any record |
| **Ownership attribution** | Each exception carries a responsible party and an age. A finding without an owner is not actionable |

**Reconciliation is the hardest of the three** and the one most likely to
be underestimated. It requires that four measures sourced from four
different resources agree, and that any gap between them is itself
reportable content rather than an error.

---

## 3. Ownership model

A finance user asking "why is this stuck" needs to know who to contact.
Roles alone do not get them there; invented names are worse than none.

**Three tiers, by what is sourceable:**

| Tier | Named? | Source |
|---|---|---|
| Buyer | Yes | PO header |
| Approver | Yes | Approval history |
| Requester | Yes | Requisition |
| Everything else | Role + team | No source for the individual |

**Team resolution:** derived from business unit where possible;
otherwise from a Spire-side configuration mapping.

**Configuration-sourced values must be marked as Spire-side.** They are
not ERP truth and must never be presented as such. A second source of
truth that drifts from the ERP produces answers that are confidently
wrong about who owns a problem.

**Worked example of the intended output:**

> Buyer Calvin Roth must decide the price variance. Once decided, AP
> Shared Services releases the hold.

One name where the ERP gives it. A team where it does not.

---

## 4. Exception rules

Six rules. Tolerances are **read from Fusion**, never held in Spire — a
second copy of a tolerance is a second copy of the truth.

| # | Rule | Fires when |
|---|---|---|
| 1 | Price variance | Invoice unit price exceeds PO beyond tolerance |
| 2 | Quantity variance | Invoice quantity exceeds PO or receipt |
| 3 | Billed ahead of receipt | Invoiced amount exceeds received amount |
| 4 | Overdue delivery | Promised date passed, quantity outstanding |
| 5 | Approved unpaid | Invoice approved, due date passed, no payment |
| 6 | Unmatched invoice | Invoice references a PO but fails match |

Every exception carries an **owner** and an **age**. Both are part of the
finding, not decoration.

---

## 5. Scope

**P2P is the first instance, not the only one.**

The same shape applies to order-to-cash: customer, invoice, receipt,
application, dispute, write-off. The design must not harden around
purchase orders.

| Lifecycle | Object | Chain |
|---|---|---|
| Procure-to-pay | Purchase order | Supplier → PO → receipt → invoice → payment |
| Order-to-cash | Customer transaction | Customer → invoice → receipt → application → adjustment |

---

## 6. Target output — the five shapes

Ten representative prompts collapse into five output shapes. What differs
is not the topic but what the reader does with the answer.

| Prompts | Shape | Reader's question |
|---|---|---|
| 1, 5, 6 | Full lifecycle | Show me everything |
| 2, 10 | Executive summary | Should I care? |
| 3, 4 | Status matrix | Is it done? |
| 7 | Diagnostic | Why is it stuck? |
| 8, 9 | Timeline | How long, and where slow? |

> **Everything below is a DESIGN MOCKUP. All data is invented.**
> No value was observed on any pod. These define what good output looks
> like. They are not results.

---

### Shape A — Full lifecycle

*"Show the complete procure-to-pay lifecycle for PO 2144, including
supplier profile, site, header, lines, schedules, distributions, ordered
amount, receipts, matched invoices, holds, approval status, payments,
outstanding amount, exceptions, and the next action required."*

---

#### Purchase Order 2144 — Complete P2P Lifecycle

**Status: Partially received, partially invoiced, payment blocked.**
Ordered 45,168.75 USD. Paid 12,400.00. Outstanding 32,768.75.
One invoice on hold pending price variance approval.

**Supplier**

| Field | Value |
|---|---|
| Supplier | Advanced Network Devices |
| Supplier number | 1287 |
| Status | Active |
| Business relationship | Spend Authorized |
| Site | ADV-SANJOSE-01 |
| Business unit | US1 Business Unit |
| Payment terms | Net 45 |
| Site status | Active, purchasing enabled |

**PO header**

| Field | Value |
|---|---|
| PO number | 2144 |
| Buyer | Calvin Roth |
| Business unit | US1 Business Unit |
| Creation date | 2025-11-03 |
| Approval status | Approved, 2025-11-05 |
| Supplier communication | Sent 2025-11-05, acknowledged 2025-11-06 |
| Ordered (ex-tax) | 41,250.00 USD |
| Total (inc-tax) | 45,168.75 USD |

> Two figures are correct and mean different things. `Ordered` excludes
> tax; `Total` includes it. Both are shown so the same question does not
> return different numbers on different days.

**Lines**

| Line | Item | Qty | Unit price | Line total | Schedules | Distributions |
|---|---|---|---|---|---|---|
| 1 | Network switch, 48-port | 15 | 1,850.00 | 27,750.00 | 2 | 2 |
| 2 | Rack mount kit | 15 | 120.00 | 1,800.00 | 1 | 1 |
| 3 | Installation service | 1 | 11,700.00 | 11,700.00 | 1 | 3 |

**Schedules**

| Line | Sched | Ship-to | Promised | Qty ordered | Qty received |
|---|---|---|---|---|---|
| 1 | 1 | San Jose DC | 2025-11-20 | 10 | 10 |
| 1 | 2 | Austin DC | 2025-12-15 | 5 | 0 |
| 2 | 1 | San Jose DC | 2025-11-20 | 15 | 15 |
| 3 | 1 | San Jose DC | 2025-12-01 | 1 | 1 |

**Distributions**

| Line | Sched | Dist | Charge account | Amount |
|---|---|---|---|---|
| 1 | 1 | 1 | 101-4200-6510 | 18,500.00 |
| 1 | 2 | 1 | 101-4300-6510 | 9,250.00 |
| 2 | 1 | 1 | 101-4200-6510 | 1,800.00 |
| 3 | 1 | 1 | 101-4200-7100 | 5,850.00 |
| 3 | 1 | 2 | 101-4300-7100 | 3,510.00 |
| 3 | 1 | 3 | 101-4400-7100 | 2,340.00 |

**Receipts**

| Receipt | Date | Line | Qty | Value | Status |
|---|---|---|---|---|---|
| RCV-88301 | 2025-11-19 | 1 | 10 | 18,500.00 | Delivered |
| RCV-88301 | 2025-11-19 | 2 | 15 | 1,800.00 | Delivered |
| RCV-88455 | 2025-12-02 | 3 | 1 | 11,700.00 | Delivered |

**Not yet received:** Line 1, schedule 2 — 5 units, 9,250.00, promised
2025-12-15, now 41 days overdue.

**Matched AP invoices**

| Invoice | Date | Amount | Matched to | Match status | Approval | Hold |
|---|---|---|---|---|---|---|
| ADV-2025-4471 | 2025-11-25 | 20,300.00 | Lines 1, 2 | 2-way matched | Approved | — |
| ADV-2025-4712 | 2025-12-08 | 12,400.00 | Line 3 | 3-way matched | Approved | — |
| ADV-2026-0119 | 2026-01-14 | 9,895.00 | Line 1 sched 2 | **Failed** | Not approved | **Price variance** |

**Holds**

| Invoice | Hold | Placed | Reason | Released |
|---|---|---|---|---|
| ADV-2026-0119 | Price | 2026-01-14 | Invoice unit price 1,979.00 vs PO 1,850.00 — 6.97% over tolerance of 5% | No |

**Payments**

| Payment | Date | Method | Amount | Invoices |
|---|---|---|---|---|
| PMT-33914 | 2026-01-09 | EFT | 12,400.00 | ADV-2025-4712 |

**Unpaid, approved:** ADV-2025-4471 — 20,300.00, due 2026-01-09,
**15 days overdue**.

**Amount reconciliation**

| Measure | Amount | % of ordered |
|---|---|---|
| Ordered (inc-tax) | 45,168.75 | 100% |
| Received | 32,000.00 | 71% |
| Invoiced | 42,595.00 | 94% |
| Approved for payment | 32,700.00 | 72% |
| Paid | 12,400.00 | 27% |
| **Outstanding** | **32,768.75** | **73%** |

> Invoiced exceeds received because ADV-2026-0119 bills goods not yet
> delivered. That gap is itself an exception, listed below.

**Exceptions**

| # | Exception | Owner | Age |
|---|---|---|---|
| 1 | Invoice ADV-2026-0119 on price hold — 6.97% over tolerance | Buyer (Calvin Roth) / AP Shared Services | 10 days |
| 2 | Invoice billed ahead of receipt — line 1 schedule 2 undelivered | Receiving / Supplier | 10 days |
| 3 | Approved invoice ADV-2025-4471 unpaid past due | Payments team | 15 days |
| 4 | Line 1 schedule 2 overdue — 5 units, promised 2025-12-15 | Supplier | 41 days |

**Next action required**

**Buyer Calvin Roth:** decide the price variance. Either accept the 6.97%
increase and amend the PO, or reject and request a corrected invoice.
This unblocks 9,895.00 and is the oldest unresolved decision.

**Payments team:** release ADV-2025-4471 — 20,300.00, approved and 15
days past due, with no blocker recorded.

---

### Shape B — Executive summary

*"Provide an end-to-end business summary for PO 2144 from supplier setup
through invoice payment, and identify the current lifecycle stage and
responsible team."*

---

#### PO 2144 — Executive Summary

**Lifecycle stage: Invoice exception.**
**Responsible team: AP Shared Services, with buyer decision required.**

| | |
|---|---|
| Supplier | Advanced Network Devices (1287) |
| Business unit | US1 Business Unit |
| Buyer | Calvin Roth |
| PO value | 45,168.75 USD |
| Delivery | 71% received; 5 units 41 days overdue |
| Invoicing | 94% invoiced; one invoice on price hold |
| Payment | 27% paid; 20,300.00 approved but overdue |
| Risk | **Medium** |

**Where it stands.** The order was approved and acknowledged within three
days and the bulk of it delivered on time. It has since stalled in two
places. An invoice for the undelivered portion arrived priced 6.97% above
the PO and sits on hold. Separately, an invoice that cleared matching and
approval has not been paid, 15 days past due.

**Why it matters.** Neither blockage is a supplier-quality problem. Both
are internal process: one needs a buyer decision, one needs a payment
run. The supplier is 20,300.00 out of pocket on goods delivered in
November.

**Risk.** Medium and rising. The overdue payment is the component that
matters — the supplier carries three other open POs worth 118,400.00, and
a payment dispute here affects those.

**Recommended action.** Release the approved payment this week; it has no
blocker. Then convene buyer and AP on the price variance — accepting it
costs 645.00 against the delay cost of an already-overdue delivery.

---

### Shape C — Status matrix

*"Has PO 2144 been fully received, fully invoiced, and fully paid? Show
ordered, received, invoiced, paid, and remaining amounts."*

---

#### PO 2144 — Status Check

**Short answer: no to all three.**
Received 71%, invoiced 94%, paid 27%.

| Stage | Status | Detail |
|---|---|---|
| Supplier | Clear | Active, Spend Authorized, site enabled |
| PO approval | Clear | Approved 2025-11-05 |
| Supplier communication | Clear | Acknowledged 2025-11-06 |
| Receipt | Partial | 3 of 4 schedules received |
| Invoice matching | Failed | 1 of 3 invoices failed match |
| Invoice approval | Partial | 2 approved, 1 blocked |
| Payment | Partial | 1 of 2 approved invoices paid |

**Amounts**

| Measure | Amount | Remaining |
|---|---|---|
| Ordered | 45,168.75 | — |
| Received | 32,000.00 | 13,168.75 |
| Invoiced | 42,595.00 | 2,573.75 |
| Paid | 12,400.00 | 32,768.75 |

**Unresolved exceptions**

| Exception | Owner | Age |
|---|---|---|
| Price hold on ADV-2026-0119 | Buyer / AP Shared Services | 10 days |
| Approved invoice unpaid past due | Payments team | 15 days |
| Schedule 1-2 undelivered | Supplier | 41 days |

---

### Shape D — Diagnostic

*"Explain in plain English why PO 2144 is still open and identify whether
the blockage is with the supplier, buyer, receiver, AP analyst, approver,
or payment team."*

---

#### Why PO 2144 Is Still Open

**Two things are holding it, and neither is the supplier's fault.**

**First, a price disagreement nobody has decided.** Advanced Network
Devices invoiced five network switches at 1,979.00 each. The PO says
1,850.00 — 6.97% over, against a tolerance of 5%. The system placed a
hold and stopped. It has sat there ten days. Someone must either accept
the new price or reject the invoice; the system will not decide this.

**Second, an approved invoice that has simply not been paid.** Invoice
ADV-2025-4471, 20,300.00, cleared matching and approval in November. Due
2026-01-09. Now 15 days overdue with no hold, no dispute, no recorded
reason.

**A third item, less urgent.** Five switches promised 2025-12-15 have not
arrived — 41 days late. The supplier has already invoiced for them, which
is why the price hold and the missing delivery are the same underlying
event.

**Where the blockage sits**

| Party | Blocked? | What they owe |
|---|---|---|
| Supplier | Partly | Deliver 5 switches, or credit the invoice |
| Buyer (Calvin Roth) | **Yes** | Decide the price variance |
| Receiver | No | Nothing outstanding on delivered lines |
| AP Shared Services | **Yes** | Cannot release the hold without the buyer |
| Approver | No | Approved everything presented |
| Payments team | **Yes** | Pay an approved, overdue invoice |

**The critical path runs through the buyer.** AP cannot move until the
price decision is made. The payments item is independent and could clear
today.

---

### Shape E — Timeline

*"Show the timeline for PO 2144 from creation through payment. Calculate
total cycle time and identify which stage took the longest."*

---

#### PO 2144 — Timeline

**Total elapsed: 82 days, still open.**
**Longest stage: invoice exception, 10 days and running.**

| Date | Day | Event | Elapsed |
|---|---|---|---|
| 2025-11-03 | 0 | PO created by Calvin Roth | — |
| 2025-11-05 | 2 | PO approved | 2 days |
| 2025-11-05 | 2 | Sent to supplier | same day |
| 2025-11-06 | 3 | Supplier acknowledged | 1 day |
| 2025-11-19 | 16 | Receipt RCV-88301 — lines 1, 2 | 13 days |
| 2025-11-25 | 22 | Invoice ADV-2025-4471 received | 6 days |
| 2025-11-27 | 24 | Invoice matched and approved | 2 days |
| 2025-12-02 | 29 | Receipt RCV-88455 — line 3 | 5 days |
| 2025-12-08 | 35 | Invoice ADV-2025-4712 received | 6 days |
| 2025-12-11 | 38 | Invoice matched and approved | 3 days |
| 2025-12-15 | 42 | **Line 1 sched 2 promised — not delivered** | — |
| 2026-01-09 | 67 | Payment PMT-33914 — 12,400.00 | 29 days |
| 2026-01-09 | 67 | **ADV-2025-4471 due — not paid** | — |
| 2026-01-14 | 72 | Invoice ADV-2026-0119 — price hold | 5 days |
| 2026-01-24 | 82 | **Open, unresolved** | 10 days |

**Cycle time by stage**

| Stage | Days | Note |
|---|---|---|
| Creation → approval | 2 | Fast |
| Approval → acknowledgement | 1 | Fast |
| Acknowledgement → first receipt | 13 | Normal |
| Receipt → invoice | 6 | Normal |
| Invoice → approval | 2–3 | Fast |
| Approval → payment | 29 | **Slow** |
| Exception unresolved | 10 | **Running** |

**The finding.** Procurement and receiving performed well — approved in
two days, first delivery in thirteen. The delay is entirely downstream.
Approval-to-payment took 29 days on the one invoice that was paid,
against Net 45 terms that should have allowed comfortable processing. The
price hold has been open ten days with no recorded action.

**If this PO closed today**, total cycle time would be 82 days against a
Net 45 expectation.

---

## 7. Format rules derived from the shapes

These are requirements, not style preferences. Each exists because its
absence has produced a wrong answer.

| # | Rule | Why |
|---|---|---|
| 1 | Every narrative number appears in a table | Prose citing figures absent from rows is the dominant defect class |
| 2 | Ambiguous measures are shown twice, labelled | Ordered vs Total returned different numbers for the same PO on different days |
| 3 | Absences are stated, not omitted | "Not yet received" is content; a missing row is indistinguishable from an error |
| 4 | Exceptions carry an owner and an age | A finding without a responsible party is not actionable |
| 5 | Percentages show their base | 71% received is meaningless without 45,168.75 beside it |
| 6 | The lead is the answer | Every shape opens with the conclusion, not with setup |
| 7 | A stated total is the true total, never the page size | Page-size-as-total appeared in eight prompts of the 2026-07-24 run |

---

## 8. What this document does not decide

- **Which endpoints supply this data.** Several — holds, payments,
  approvals, requisitions — are not in Spire's current set. That is an
  expansion-plan question.
- **Build order or phasing.** Deliberately absent.
- **Feasibility.** No claim is made that any shape is buildable as
  described.

The goal is fixed here so that everything else can be measured against
it.
