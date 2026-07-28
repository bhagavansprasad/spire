# Spire — Plan

**The single planning document for Spire.** Merges what used to live in
three files: `feature_roadmap.md` (the what/why), `spire_expansion_plan.md`
(the phase-by-phase how), and `spire_lifecycle_goal.md` (the next feature's
target). Those are superseded — keep updating this file only.

**Forward-looking by design.** Completed phases (PO P1–P6c, AR P1–P6) are
compressed to a status table; their full build detail lives in git history
and `spire_fusion_endpoints_reference.md`. This document is what remains to
be built and how.

Structure:
- **Scope** — the bar for "done".
- **Lifecycle goal** — the destination this plan builds toward.
- **Conventions & build sequence** — how every phase ships.
- **Cross-cutting reference** — pod quirks, architecture rules, the parser
  runaway saga. Read before building anything.
- **Live status** — every phase across every module, one table.
- **Feature backlog** — discrete features, done and open.
- **Future modules** — GL, AP stubs.
- **Endpoints catalog** — raw endpoint/prompt tables.
- **Component lifecycle & future tasks** — Track A removal, deferred work.

Companion references (NOT merged, kept separate):
- `spire_fusion_endpoints_reference.md` — pod behaviour authority.
- `SPIRE_SESSION_HANDOFF.md` — rewritten each session.

---


## Scope for v1

**Audience:** internal consultants and end users (procurement/finance).

**Bar for "done":** depth before breadth. Handle a focused set of
common prompts very well, with honest refusal on the rest. Broaden
coverage in a follow-up cut.

**Out of scope for v1:** production hygiene (caching, observability,
deployment), domains beyond procurement.

---


---

# The lifecycle goal — where this plan is heading

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


---

# Conventions & build sequence

**Branch convention:** `<module>-phase-N-description` (e.g.
`po-phase-6c-invoiced-vs-ordered`, `ar-phase-2-invoices`).

**Git discipline:**
- One branch per logical change, PR-based merges.
- Named files in `git add` — never `-A`.
- Heredoc commit messages (`git commit -F- <<'EOF'`).
- Docs-only changes may go straight to master.

**The proven build sequence** (every code phase follows it):
1. Live curl discovery — hit the pod, record every column (even ones not
   registered yet, so later expansion is additive).
2. Standalone tool — a plain async function, not coupled to FastMCP.
3. KG rows *or* op-registry entry — rebuilt from scratch (`rebuild_kg.py`),
   never incrementally. (Which one depends on the query kind — see Routing
   below.)
4. Planner edits.
5. Parser line / instruction block.
6. Server wrapper (`@mcp.tool()`).
7. Tripwires — bump expected counts in both `scripts/print_kg.py` and
   `tests/test_kg_metadata.py` when KG rows change.
8. Tests — pod-free unit tests + pod-gated integration tests.
9. Verify end-to-end (prompt set).
10. Git branch → PR → merge.

**Permission gates:** ask before generating code or significant content;
one command at a time; verify each step before the next.

**Pod:** `fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com`. Credentials
live in `personas.yaml` (single source; `load_persona('default_dev')`).
Base REST path for all resources: `/fscmRestApi/resources/11.13.18.05/`.

---

---

# Cross-cutting reference

### Pod quirks (confirmed)
- **Composite `q=` fails** — send one selective server clause, filter the
  rest client-side. Every tool does this.
- **`expand=` for child collections is silently ignored** — use per-parent
  child calls, not expansion.
- **`totalResults=true`** is required to get a real total count; without it
  `count` reflects only the returned page size.
- **Supplier.Status is unreliable server-side** — match client-side.
- **Country requires `expand=addresses`** (address records use
  `SupplierAddressId`, not `AddressId`).
- **Join-key asymmetry:** invoices reference suppliers by `SupplierNumber`
  (string) and POs by `SupplierId` (numeric); invoice↔PO joins use
  `PurchaseOrderNumber` (string), NOT POHeaderId. POs carry NO
  `SupplierNumber` (`SupplierNumber` in `?fields=` on `/purchaseOrders` is
  HTTP 400).
- **Flat `/purchaseOrderSchedules` exists** and accepts `q=POHeaderId=`
  server-side; there is NO flat `/purchaseOrderDistributions` (404) — those
  need the deep nested path with three ids.
- **OrderDate is NOT queryable** on POs; use `CreationDate` for date bounds.
- **PO OrderNumber vs POHeaderId** are different identifiers and look
  identical in a prompt (OrderNumber "162034" is POHeaderId 1). The PO
  lookup tool resolves either (tries OrderNumber first, then POHeaderId).
- **OWSM 401s** can appear right after a pod switch and self-resolve in
  ~30 min — a transient, not a credential problem.
- Keep `spire_fusion_endpoints_reference.md` updated after every discovery
  session — it's the authority on pod quirks.

### Architecture rules
- **Deterministic KG-driven pipeline** (Design 3): parse → plan → execute →
  synthesize. Tool selection is a lookup, not an LLM judgment. Not an agent
  architecture.
- **Grouping and measure are FIXED BY IDENTITY, never parameters.** A
  different grouping or measure is a different tool, never a flag. This is
  the line that keeps the aggregation/comparison layers a set of bounded
  tools rather than a generic engine. (From `aggregate_invoices.py`.)
- **The LLM never does arithmetic.** Tools compute every number; the
  synthesizer templates them. The LLM is unreliable at arithmetic (cf. the
  date-computation lesson). Aggregation and comparison synthesizer shapes
  are deterministic (no LLM) for exactly this reason.
- **Hallucination guard:** every structured id in a synthesized response is
  cross-referenced against the executor's output. A schema that permits
  detail without validating it is worse than one that says nothing.
- **Bounded windows:** page to `MAX_PAGES` and flag `truncated` at the cap;
  sums past the cap are lower bounds, and the synthesizer must say so.

### Reliability backlog (cross-cutting, not tied to a module)
- **Parser runaway defence** (post-AR-P2c, not started). A structured-output
  parse can hang for minutes if the LLM fails to converge and generates to
  its output-token ceiling. Observed in AR-P2c: a single cross-referencing
  sentence in the parser prompt (naming `has_open_PO` inside the
  customer-invoices instruction) sent Gemini flash to `out=65520` tokens,
  ~267s, on every run — deterministic, not flaky. Removing the sentence:
  `out=293`, ~8s. Detection signal already in logs: `[llm] out=` near the
  model's max (with `finish_reason=length`, not `stop`) means a runaway,
  not a real parse. Work: (a) cap `max_output_tokens` in `build_llm` so a
  runaway fails in ~2s not ~4min — highest-value, do first; (b) detect
  ceiling-hit / `finish_reason=length` and log a warning, optionally retry
  once; (c) wall-clock timeout on the parse call; (d) capture the failure
  mode (symptom + cause: cross-referencing an unrelated concept in a
  structured-output instruction can block convergence) in
  `spire_design_decisions.md`. Needs `config.py`.

  **UPDATE 2026-07-22 (AR-P5) — the mechanism is NOT truncation.** This
  item previously assumed the cap truncates an otherwise-converging parse.
  Tested directly and that is wrong. With `LLM_MAX_OUTPUT_TOKENS` patched
  to 32000 at runtime, the same prompt produced `out=31983` and STILL
  returned an empty Intent. So the model is not being cut off mid-answer —
  it generates without converging, and the ceiling only bounds how long
  the failure takes. Raising the cap costs tokens and buys nothing.
  Consequences for the planned work: (a) is still worth having as damage
  control but is NOT a fix; (b) becomes the priority, since detection is
  the only thing that turns this from a silent wrong answer into an
  honest failure.

  **What a runaway looks like, precisely** (three prompts, 2026-07-22):
  `target_entity` comes back CORRECT and every field after it is empty —
  filters `[]`, include `[]`, all flags at default. That ordering is the
  tell: the model emits the schema's early fields, then fails to
  terminate. A runaway is therefore NOT distinguishable from a legitimate
  bare-entity parse by looking at the Intent alone; only the token count
  separates them.

  **Rewriting the parser prompt does not fix it; rewording the question
  sometimes does.** AR-P5 prompt 6 took four separate prompt rewrites
  (removing an "empty include" instruction, making a filter REQUIRED,
  deleting an aggregation carve-out, then restoring it) with NO effect on
  the runaway — `out=7983` every time, to the token, across all versions.
  What changes the outcome is the QUESTION, not the rules: "What is the
  account balance for customer X?" runs away at 7983; "Show me the account
  balance for customer X" parses cleanly at `out=192`. Same intent, same
  rules, same input size. AR-P5 prompt 7 needed five phrasings before one
  parsed (`out=289`). So phrasing-hunting is the working workaround, but
  it is a workaround: it usually succeeds within a few tries and leaves
  behind prompts that break silently when reworded.

- **Parser observability + degenerate-parse defence** (new 2026-07-22, not
  started).

  **SCOPE WIDENED 2026-07-22 (AR-P5 prompt 8): this is not parser-only.**
  The synthesizer fails the same way. On prompt 8 the synthesize call
  returned `out=7985` and a response containing `"receipts": []` — an
  EMPTY array — while its prose summary correctly described all 25 rows
  ("There are 25 receipts... Two are unapplied... The remaining 23 are
  applied"). The JSON was VALID and COMPLETE (`truncation_notes: []`), so
  unlike the parser case nothing was cut off: the model read the data,
  described it accurately, and declined to populate the array. The SAME
  25-row fetch SUCCEEDED on a different account at `out=3657` with every
  row present — that account's receipts were near-identical to one another
  (same date, same amount, same method), while the failing account's were
  varied. **Payload ENTROPY predicts this, not row count.** Mitigated by
  capping `get_account_receipts` at 10 rows (`out=1596`, all rows
  present), which is a workaround, not a fix. So Spire has TWO LLM
  boundaries and BOTH produce structurally-valid, silently-wrong output
  under load. Any guard built here must cover the synthesize call as well
  as the parse call.

  The runaway above cost roughly fifteen probe runs to characterise and
  still is not root-caused, because there is essentially nothing to
  observe. Three concrete gaps, in priority order:

  1. **Silent failure — no detection.** A runaway returns a structurally
     VALID `ParseResult`; a degenerate synthesis returns a structurally
     VALID response. Nothing notices that `out=7983` against a cap of
     8000 is pathological, that an Intent carries a `target_entity` with
     no filters for a prompt that plainly named a customer, or that a
     child array came back empty when the executor bucket was NOT empty.
     The parse failure surfaces downstream as a planner error
     ("No entity tool for ('CustomerAccount', 'none')") that names the
     WRONG problem — it reads as a missing KG row. The synthesis failure
     surfaces as a plausible answer with no rows. In production the worse
     case is a runaway that happens to produce a routable Intent: Spire
     would then answer confidently from a wrong parse, with no error
     anywhere. Probable fix: a guard after each LLM call that flags (i)
     output tokens within ~95% of the cap, (ii) `finish_reason != 'stop'`,
     and (iii) an empty structured collection where the source bucket was
     non-empty — raising a typed error rather than returning the result.
     Cheap, mechanical, and converts a silent wrong answer into an honest
     failure.
  2. **No raw-output capture.** Nothing records what the model actually
     emitted during a runaway. Fifteen probes produced only token counts;
     the 32,000 generated tokens were never seen, which is exactly why the
     cause is still unknown. NOTE the trace ALREADY records
     `synthesis_completed` with the full PARSED response — that is how the
     empty-array finding was confirmed — so what is missing is the raw
     pre-parse text, and the parser-side equivalent entirely. Probable
     fix: when the guard in (1) fires, write the raw response text to the
     existing trace file. This is the single highest-value diagnostic
     change — one occurrence with captured output would likely explain
     more than every A/B test run so far.
  3. **No in-flight visibility.** `with_structured_output` buffers, so a
     30s+ generation prints nothing until it completes. There is no
     progress signal, no partial output, no way to tell a slow call from a
     hung one. Probable fix: a token-count callback or streaming wrapper so
     a long generation is visible while it happens; harder than (1) and
     (2) and worth deferring until those land.

  Sequencing note: (1) and (2) together are small and would have made
  today's debugging a single run instead of an afternoon. Do them before
  attempting a root-cause fix on the runaway itself — without (2) there is
  nothing to root-cause FROM.

  **STATUS UPDATE 2026-07-22 (end of session): the PARSER half may be
  RESOLVED; the SYNTHESIZER half is not.** All eleven documented runaway
  prompts now parse correctly at `out=190–465`. The fix came from a change
  to how `kg_entity_filter` rows are loaded and keyed, which altered the
  KG menu and therefore the parser prompt. The mechanism is NOT
  understood, so this is "appears fixed", not "fixed" — and an unexplained
  fix can regress silently, which is itself an argument for the detection
  guard below.

  The synthesizer half stands unchanged. Prompt 8 returned valid JSON with
  an EMPTY receipts array while narrating the rows correctly in prose, and
  nothing detected it. Any guard built here must cover the synthesize call
  regardless of what happened to the parser.

  Building was PAUSED mid-session pending this investigation and has since
  RESUMED (work on prompts 9, 10, 13, 17, 18 happened outside that
  window). The detection guard and raw-output capture remain unbuilt.
- **Open-invoices top-N limit** ✓ merged (`ar-invoice-limit-top-n`) — finishes
  AR-P2c prompt 1. Prompt 1 is "top 5 open invoices"; AR-P2c shipped open_only
  only (returned ALL open invoices). Resolved exactly as scoped: parser
  extracts "top N" → `invoice_limit` on the Intent (gated to the open-invoices
  shape) → planner Block 3 passes it as the fetcher's `limit` on the
  CustomerTransaction step, alongside open_only. Parser + planner only, no KG
  rows. Verified: pod returns the 5 highest-balance open rows.
- **Synthesizer does arithmetic (pre-existing, broader than AR-P2c).**
  The CustomerAccount narration sums invoice amounts and reports totals in
  prose (observed on prompt 1: a wrong "combined original amount", and the
  account's negative credit-balance field reported as the open-invoice
  total). Violates the no-arithmetic rule — tools must compute, the
  synthesizer only templates. Affects Shape B narration generally, not
  just open invoices. Fix belongs in the synthesizer, not this phase.

### Known issues — verification session (2026-07-24) — SUPERSEDES MUCH OF THE 07-21 LIST BELOW

A full verification session ran every prompt set end-to-end. **Nine bugs
found and fixed, all verified live.** Read this section before the
2026-07-21 list below, which is partly stale.

**Issue 6 in the list below was already fixed when it was written.**
`planner.py` unpacks the tuple key correctly at lines 351/361/371; the
error it describes (`Supported entity-level: []`) does not occur anywhere.
The three "broken" prompts were failing for three DIFFERENT reasons and
one was not broken at all. About an hour was lost chasing it. **Treat a
diagnosis carried between sessions as a claim, not a fact.**

#### Fixed and verified (2026-07-24)

| # | Bug | Layer |
|---|---|---|
| 1 | `tool_arg_name: 'supplier'` was a PLACEHOLDER — both KG rows document the routing ("all-digit → `supplier_number`, else `supplier_name`") and no code implemented it | planner |
| 2 | Invoice guard demanded a supplier and rejected `purchase_order`. The PO guard's own comment described the Invoice guard as already widened; it was not | planner |
| 3 | Synthesizer registry keyed `ExposureRanking` where the parser emits `exposure_ranking` — the lone PascalCase entry among five | synthesizer |
| 4 | `_build_aggregation_plan` never read `intent.filters`: customer scope silently dropped, tool ran pod-wide, answer named the customer. Plus a duplicate dict key shadowing `account_number` | planner |
| 5 | Server wrapper missing `customer_name` that the standalone tool had | server |
| 6 | Aggregation tool capped at 500 rows, no pagination — reported a sample of 1,386 as a total and hid an entire receipt method | tool |
| 7 | Receipt applications over-fetched 500 and filtered client-side; bucket name wrong in FOUR places | tool + synthesizer |
| 8 | `total_available` discarded by the executor unwrap — count reported page size (10) as account total (7,038). Fixed by threading `metadata_by_step` through `execute_plan` | executor |
| 9 | Synthesizer expanded `1179915.3225` to its full IEEE-754 binary form, then trailing zeros to the token cap | synthesizer |

**Three validators had never fired.** The empty-array guards in
`synthesize_response` checked bucket names that do not exist. All four
now match `_OUTPUT_NAME_BY_ENTITY`; one caught a real failure the moment
it was corrected. **Any new child bucket needs its guard name checked
against `_OUTPUT_NAME_BY_ENTITY`, not guessed.**

**Crash isolation added to `run_prompt_set.py`.** One `AttributeError`
in the DISPLAY layer killed the AR set after prompt 1 and 15 prompts
never ran. Each prompt now runs in a try/except.

#### Open, observed failing (2026-07-24)

**Issue A — receipt-method aggregate is not reproducible.** Two runs,
same account, same code, consecutive days: identical row count (1,386),
different totals (215.7M vs 250.6M) and different method splits (993/393
vs 1132/254). Same count, different rows. Hypothesis: `/standardReceipts`
has no default ordering and the paginated fetch walks `offset` without an
`orderBy`. Confirm by curl before fixing. See endpoints reference §12.2.

**Issue B — column selection is designed and inert.** `fields` parses
into the Intent correctly and nothing downstream uses it.
`_project_outputs(outputs, fields)` exists in `graph/pipeline.py`;
`run_plan.py` never calls it. Asking for ONE field and asking for TWO
produced byte-identical output. Separately, requesting `country` as a
FIELD triggers the address over-fetch used for country FILTERING —
synthesizer input 16,881 tokens vs 2,729, then MAX_TOKENS.

**Issue C — `open_only` may not filter.** "Show me open invoices for
customer X" returns 25 open invoices; the unfiltered prompt on the same
account says all 25 transactions are "currently closed with a balance of
0.00". Both cannot be true.

**Issue D — `count_only` parsed and ignored.** Intent carries
`count_only: True`; the plan fetches 25 rows. The stated answer (424) is
plausible but is not among the returned rows.

**Issue E — page size stated as total, at least five prompts.** The
truncation block reports the real number; the narration does not always
use it. Prompt 9 was fixed by threading metadata; the same pattern
applies to open invoices, credit memos and supplier lists.

**Issue F — creation-to-update lag prompt refuses** despite a
`lag_query` KG filter and a registered `get_receipts_with_lag` tool.

**Issue G — `Suppliers with their addresses` hits MAX_TOKENS.** Same root
as Issue B's country over-fetch.

**Issue H — PO totals disagree between prompts.** "Show PO 2144 and its
lines" reports 41,250.00 (`Ordered`, ex-tax); "What is purchase order
2144 about?" reports 45,168.75 (`Total`, inc-tax). Both defensible; a
user asking twice gets two numbers with no explanation.

**Issue I — PO status breakdown reports 10,000 POs** where the prompt set
says ~3,362, and the per-status counts do not sum to it either.

**Issue J — `pytest` has NOT been run since `execute_plan` changed from
2 return values to 3.** `test_executor.py` very likely asserts the old
shape. Highest-risk unknown in the repo.

#### Cross-cutting lessons (2026-07-24)

**Naming across un-typechecked boundaries is now the dominant bug
class** — five instances this session: KG→tool arg, parser→synthesizer
shape key, planner→wrapper parameter, synthesizer→executor bucket name
(×4), schema→display field. None type-check; all failed silently.

**The display layer runs behind the schema.** Three separate bugs: a
field the formatter read that did not exist, a field the formatter never
read, and a projection function never called. A generic formatter walking
the Pydantic model would have had none of them. **Worth doing.**

**Repair code placed before a check disables the check.** A structural
fallback populating an empty list ran before the validator testing for an
empty list. Removing it revealed the model had NEVER been populating that
list — the fallback was doing all the work, invisibly, on every run.

**A factual statement in the synthesis prompt can suppress row
emission.** "The total is 7038. The list below shows only the most recent
ones." — the second clause read as permission to skip the rows
(out≈793). Dropping it restored emission (out≈2148).

**Compute in the tool, not the prompt.** Every numeric bug fixed this
session was fixed this way. Where the tool computed the value it was
right first time; where the prompt asked the model, it took multiple
rounds.

#### Token profile (measured, ~15 runs)

| Stage | Input | Output |
|---|---|---|
| Parse | ~8,120 **constant** | 200–800 |
| Synthesize | 1,100–5,900 | 720–3,100 |

Parse input is fixed regardless of the question: the KG menu (22
entities, 25 filters, 97 vocabulary terms) is rebuilt and re-sent on
every call, and the actual question is 10–20 tokens of it. Parse:
synthesize runs about 1.5:1 overall, from 4:1 on a single-record answer
to 1.1:1 on a 25-row answer.

**Highest-leverage cost reduction: prompt caching on the parse call.**
The system prompt is byte-identical across every call and no behaviour
would change.

---

### Known issues — full prompt-set run (2026-07-21)

A full `run_prompt_set.py` run (38 prompts, all modules) after AR-P2c
surfaced these. The harness reported "38/38 ran cleanly" but that counts
refusals as ok — several of those refusals/parses are WRONG. Grouped by
root cause. None are AR-P2c regressions (all 3 AR prompts parsed and ran
correctly); these are pre-existing issues the run exposed, plus the
parser-runaway class the token cap made visible.

**Issue 1 — Parser runaway: the model generates without converging.**
**APPARENTLY RESOLVED 2026-07-22 — verify before deleting this entry.**
All eleven prompts listed below now parse correctly at `out=190–465`,
including "active US suppliers" (both filters recovered) and the four
PO 2144 prompts (which also pass end-to-end). The fix came from a change
to `kg_entity_filter` loading that altered the KG menu and therefore the
parser prompt; the mechanism is not understood. Keep this list until a
full prompt-set run confirms it across the suite — and note that
"parses correctly" is not "works": three of the prompts below now fail at
PLAN time instead (see Issue 6).
The `open_only` runaway (fixed by moving the instruction to its own
section) is NOT unique — several prompts drive Gemini structured-output to
the ceiling. The cap (config.py) makes them fail in ~13-40s instead of
hanging ~260s, and the resulting draft is degenerate: filters/includes
dropped, or a wrong refusal. All show `out=7983/7984` (or 6072) at parse.
This is the systemic core of the "parser runaway defence" backlog item,
now with evidence it spans PO, Supplier and AR prompts. Affected:
- "Show PO 2144 and its lines" — out=7984 → wrongly refused
- "Show PO 2144 and its schedules" — out=7984 → wrongly refused
- "Show PO 2144 and its distributions" — out=7984 → wrongly refused
- "How much of PO 2144 was received?" — out=7984 → wrongly refused
- "Which invoices were raised against PO 162034?" — out=6072 → wrongly refused
- "active US suppliers" — out=7983 → parsed as bare Supplier, BOTH filters dropped
- "Show supplier EIP Inc and its contacts" — out=7984 → bare Supplier, Contact include dropped
- "Invoices for supplier 1252 over 100000" — out=7984 → wrongly refused
- (AR-P5, 2026-07-22) "What is the account balance for customer ABC
  Application Software?" — out=7983 → CustomerAccount, filter AND
  balance_only both dropped. Worked around by rewording to "Show me the
  account balance for customer ABC Application Software" (out=192).
- (AR-P5, 2026-07-22) "Show me recent credit memos for customer ABC
  Application Software" — out=7983 → CustomerAccount, filter and include
  dropped. Took FOUR phrasings to find a working one; three failed
  identically at out=7983 ("Show me recent credit memos for customer X",
  "Show me credit memos for customer X", "List credit memos for customer
  X", "Show me the credit memos on customer X's account", "Show me
  account credit memos for customer X"). The one that works: "Show
  credit memos for ABC Application Software" (out=289, full correct
  parse). UNCONFIRMED OBSERVATION: the working phrasing is the only one
  tried that omits the word "customer" before the name — but prompt 6's
  working phrasing DOES contain "customer", so this is not a rule, just
  something to try first when hunting a phrasing.

**CORRECTION 2026-07-22: this is NOT truncation.** This section previously
implied the 8000 cap truncates an otherwise-good parse. Tested: patching
`LLM_MAX_OUTPUT_TOKENS` to 32000 at runtime gave `out=31983` and the SAME
empty Intent. The model does not converge at any ceiling; the cap only
bounds how long the failure takes. See the corrected backlog item above.

**Prompt rewrites do not move it; rewording the QUESTION sometimes does.**
AR-P5 prompt 6 absorbed four separate parser-prompt rewrites with zero
effect (`out=7983` to the token, every version). Editing the RULES did
nothing in either case. What works is rewording the question itself, but
it can take several attempts: prompt 6 needed two phrasings, prompt 7
needed five (four runaways, then a clean `out=289` parse). Treat
phrasing-hunting as the current workaround — cheap, usually succeeds
within a few tries, but it produces prompts that are fragile by
construction: the same question asked slightly differently silently
returns a degenerate parse. That fragility is the argument for the
observability work below, which phrasing-hunting does not address.

NOTE: these same prompts have KNOWN-GOOD phrasings elsewhere in the suite
that parse fine (e.g. "Show PO 2144 and its lines" is the canonical P2
prompt). The instability is phrasing-sensitive and intermittent-looking
but reproducible per-phrasing. Needs the detection + raw-output capture
from the observability backlog item BEFORE another root-cause attempt —
every investigation so far has been blind, with only token counts to go
on.

**Issue 2 — Filter silently dropped (parses to bare entity).** Distinct
from Issue 1 — LOW out counts, so NOT the runaway; the parser simply fails
to emit the filter. Returns the unfiltered entity (wrong result, no error):
- "Prospective suppliers" — out=103 → returns all 420; business_relationship filter not applied
- "Suppliers with invoice amount greater than 10000" — out=104 → returns all; filter dropped
  (note: this filter may not be a supported Supplier filter at all — if so
  the correct behavior is a refusal, not a bare-entity list; needs a
  decision, not just a parser fix)

**Issue 3 — Missing synthesizer shape for Address.** "Addresses for
supplier 1252" fetches 25 rows but the synthesizer prints "(Unrecognized
response shape.)" and shows 0 records. Address has no narration branch /
is not in the five synthesizer places. A synthesizer gap, pre-existing.

**Issue 4 — Synthesizer does arithmetic, wrongly (same as backlog item
above).** Confirmed live on "Show me open invoices for customer ABC
Corporation Americas": "combined original amount 981738.13" is wrong, and
"open receivables -206448.85" is the account's credit-balance field
mislabeled as the open-invoice total. The plain "AR invoices for..."
answer summed correctly by luck but uses the same fragile pattern. Cross-
reference the "Synthesizer does arithmetic" backlog entry.

**UPDATE 2026-07-22 (AR-P5): an EXPLICIT prohibition does not stop it.**
Prompts 7 and 8 both carry a per-bucket instruction in
`_SYSTEM_PROMPT_BY_ENTITY` spelling out "COPY every amount exactly; do
NOT total them, do NOT negate them, do NOT compute a net". The model
computed anyway, in three observed forms, each time producing a CORRECT
number by a forbidden route:
- prompt 7: "amounts ranging from -156.6 to -495.9" and "issued between
  2022-07-15 and 2023-07-15" — min/max scans over the rows.
- prompt 8: "Two receipts, totaling 16347.42 USD, are unapplied" — an
  actual sum (1347.42 + 15000).
- prompt 8 (earlier run): "The remaining 23 receipts are applied" — a
  subtraction (25 − 2).
The numbers being right is precisely the danger: nothing flags them, and
the same pattern on a larger or messier set would be wrong with equal
confidence. This is now evidence that prompt-level prohibition is not a
sufficient fix — the instruction is present, unambiguous, adjacent to the
data it governs, and still ignored. A structural fix (compute totals in
the TOOL and stamp them onto the rows, as AR-P4 does for `total_credit`;
or validate numeric claims in the summary against the fetched values) is
the direction, not another prompt rewrite. Note the parallel with the
parser runaway: in both cases editing the prompt text changed nothing.

**Issue 5 — Truncation wording misleading (minor).** "Invoices for Lee
Supplies in 2023" returned 11 rows but the truncation line reads "unknown
total in source; 25 examined for filtering" — the "25 examined" wording is
confusing when fewer are returned. Low priority; cosmetic.

**Issue 6 — Entity-level filter lookup is broken (NEW 2026-07-22, a
REGRESSION, and the first failure observed INSIDE the deterministic
layer).** Three prompts that previously worked now fail at plan time:

- "Which invoices were raised against PO 162034?" — `Invoice`/`purchase_order`
- "Show supplier EIP Inc and its contacts" — `Supplier`/`name_fragment`
- "Invoices for supplier 1252 over 100000" — `Invoice`/`supplier` +
  `invoice_amount`

The error reads `Intent contains filter types not supported for entity
'Invoice': ['purchase_order']. Supported entity-level: [].` — and that
EMPTY list is the tell, because `kg_entity_filter` holds 25 rows
including every one of these.

Cause: `_load_filter_defs()` returns a dict keyed by the TUPLE
`(filter_type, target_entity)` — confirmed live — while its consumers
(`_entity_level_filter_types`, `_validate_intent_filters`,
`_pick_entity_filter`, `_build_entity_fetcher_args`) still iterate
expecting a plain filter-type key. `ftype` therefore binds to the whole
tuple, the resulting set contains tuples, and a plain string like
`"supplier"` never matches. A change applied to the loader but not to its
callers.

Note every entity-level row currently shows `None` as its `target_entity`,
so the per-entity keying may never have been fully wired into the KG rows
either.

Two coherent directions, opposite to each other:
1. **Finish the revert** — key by `ftype` alone, matching the consumers.
   Smaller, but loses per-entity `by_id` resolution (`po_header_id` for
   PurchaseOrder vs `customer_transaction_id` for ReceivablesInvoice),
   which is presumably why the tuple keying was introduced.
2. **Finish the per-entity design** — unpack tuples in the consumers and
   populate `target_entity` on the entity-level KG rows.

Decide before touching it; check `git log` for which version was
committed. This is worth flagging against the architecture: it is NOT an
LLM failure. It is a lookup whose key shape changed under its callers —
ordinary code breakage, in the layer that had until now been reliable.

### Routing mechanisms — three kinds of query
The planner routes a parsed Intent one of three ways. Knowing which a new
prompt needs decides what you wire.

1. **Entity/filter queries** (list, detail, child traversal) → routed
   through the **KG tables** (`kg_entity`, `kg_entity_filter`, `kg_edge`,
   etc.). Adding one means KG rows + a rebuild + tripwire bumps.
2. **Aggregations** (rank, count, sum) → routed through the planner's
   **op-registry** (`_AGGREGATION_TOOLS` / `_AGGREGATION_PARAMS`), via a
   `aggregate` block on the Intent. NOT the KG. Adding one means a registry
   row pair + a parser instruction + a synthesizer shape.
3. **Comparisons** (invoiced-vs-ordered, two-source joins) → routed through
   the **comparison op-registry** (`_COMPARISON_TOOLS` / `_COMPARISON_PARAMS`),
   via a `compare` block on the Intent. NOT the KG. Same shape as
   aggregation. Added in P6c.

Aggregation and comparison both bypass the KG and both skip
`validate_intent` (their Intents carry no target_entity). The parser has a
"do NOT refuse" instruction block for each, and `validate_intent` exempts
each.

---

---

# Live status

Status vocab: `not started` · `in progress` · `blocked` · `merged`.

| Module | Phase | Goal | Branch | Status |
|---|---|---|---|---|
| PO | P1 | Dedupe + discovery scope | `po-phase-1-dedupe` | merged (docs-only) |
| PO | P2 | PO detail + lines + projection | `po-phase-2-po-lines` | merged |
| PO | P3 | PO schedules (flat endpoint) | `po-phase-3-schedules` | merged |
| PO | P3b | PO distributions (multi-field iteration) | `po-phase-3b-distributions` | merged |
| PO | P4 | Supplier contacts | `po-phase-4-supplier-contacts` | merged |
| PO | P5 | Received-vs-ordered + invoices-by-PO | `po-phase-5-received-invoices-by-po` | merged |
| PO | P5b | Synthesizer: narrate child entities | `po-phase-5b-synthesizer` | merged |
| PO | P6 | PO aggregates (by-supplier / by-status / open) | `po-phase-6-aggregates` | merged |
| PO | P6b | PO date filter (stale POs) | `po-phase-6b-po-dates` | merged |
| PO | P6c | Invoiced-vs-ordered comparison | `po-phase-6c2-invoiced-vs-ordered` | merged |
| **AR** | **P1** | **Dedupe + column capture + plan** | `ar-phase-1-dedupe` | **merged (docs-only)** |
| **AR** | **P2a** | **AR invoice by-id + lines (prompts 11, 12, 2)** | `ar-phase-2-invoices` | **merged** |
| **AR** | **P2b** | **Customer invoices via account (prompt 15)** | `ar-phase-2b-customer-invoices` | **merged** |
| AR | P2c | Open invoices for a customer (prompt 1, open_only) | `ar-phase-2c-open-invoices` | merged |
| AR | — | Top-5 open-invoices limit (finishes prompt 1) | `ar-invoice-limit-top-n` | merged |
| AR | P3 | Tax lines (prompt 3) | `ar-p3-tax-lines` | merged |
| AR | P3 | DFF (prompt 4) | `ar-p3-dff` | merged |
| AR | P4 | Credit memos (prompts 5, 14) | `ar-p4-credit-memos` | merged |
| AR | P5 | Account balance (prompt 6, `balance_only`) | `ar-phase-5-account-children` | merged |
| AR | P5 | A customer's credit memos (prompt 7, `AccountCreditMemo`) | `ar-phase-5-account-children` | merged |
| AR | P5 | A customer's receipts (prompt 8, `AccountReceipt`) | `ar-phase-5-account-receipts` | merged |
| AR | P5 | Receipt applications (9), site receipts (13) | `prompt9-metadata-threading` | **merged 2026-07-24** |
| AR | P6 | Exposure ranking (10), receipt-method distribution (17) | — | **fixed + verified 2026-07-24** |
| AR | P6 | Creation-to-update lag (18) | — | **refuses — see Issue F** |
| AR | P6 | Cash collection / DSO (16) | — | **not built — design pending** |
| **GL** | **P1** | **Dedupe + plan** | `gl-phase-1-dedupe` | **not started** |
| GL | P2+ | (defined at P1) | — | not started |
| **AP** | **P1** | **Dedupe + write-safety design + plan** | `ap-phase-1-dedupe` | **not started** |
| AP | P2+ | (defined at P1) | — | not started |

**Next up: VERIFY, then fix known breakage, then build.** The status of
the AR module is PARTLY UNVERIFIED as of 2026-07-22 — see the top of
`SPIRE_SESSION_HANDOFF.md`. A status summary produced outside the build
window reports 17 of 18 AR prompts merged (18 in progress, 16 pending
design), and the file evidence is consistent with it: tools exist for
prompts 9, 10, 13 and 17, and the KG stands at 22 entities / 194 fields /
17 edges / 16 edge-tools / 97 vocab. But none of those four prompts has
been observed RUNNING, and a complete tool with green unit tests is not
the same as a working prompt — prompt 8 had both while returning an empty
receipts array end-to-end.

Confirmed working end-to-end (observed 2026-07-22): account balance (6),
account credit memos (7), account receipts (8), customer invoices (15),
recent credit memos (5).

**Known breakage to clear BEFORE building:**
1. Three PO/Supplier prompts fail at plan time — `Invoice`/`supplier`,
   `Invoice`/`purchase_order`, `Supplier`/`name_fragment` — with
   `Supported entity-level: []`. Cause diagnosed: `_load_filter_defs()`
   now returns a dict keyed by the TUPLE `(filter_type, target_entity)`
   while its consumers still iterate expecting a plain filter-type key,
   so validation compares strings against tuples and never matches. Half
   an applied change. Decide whether to finish the revert (key by ftype
   alone, losing per-entity `by_id` resolution) or finish the per-entity
   design (unpack tuples in the consumers, populate `target_entity` on
   the entity-level rows).
2. KG tripwire drift: `kg_entity_tool` 10 vs expected 9,
   `kg_entity_filter` 25 vs expected 23. Bump both `scripts/print_kg.py`
   and `tests/test_kg_metadata.py`.

**The parser runaway class appears CLOSED.** All eleven documented bad
prompts now parse correctly at `out=190–465`, where they previously
produced `out=7983/7984` and degenerate empty Intents; four of the PO 2144
prompts now pass end-to-end. The cause is NOT understood — the fix
altered how `kg_entity_filter` is loaded, which changed the KG menu and
therefore the parser prompt (`in=` moved 7384 → 7415 → 8117). Whether
that is the mechanism or a side effect is unestablished, and an
unexplained fix can regress silently. See Issue 1 below, which is now
partly historical.

### Known test notes (not bugs)
- **Three supplier `truncated is False` assertions** fail on pods with more
  suppliers than `OVERFETCH_LIMIT` (500): `search_suppliers` over-fetches,
  examines 500, finds no match, honestly reports `truncated=True`. The code
  is correct; the tests encode a data-volume assumption. Do NOT "fix" by
  weakening the assertion or raising the cap — this is deferred
  test-portability work. (The assumption held on esll-dev37 and flipped on
  eqjz; with the pod back on esll-dev37 it may hold again.)
- **Distribution test anchors are pod-specific.** The integration test
  anchors on PO 2144's chain (POHeaderId 2144, POLineId 19782,
  LineLocationId 18954), valid on esll-dev37. A pod switch may require
  re-capturing them (find a PO with distributions, update the constants).

---

---

# Completed modules (compressed)

Full build detail is in git history and the endpoints catalog below. These
phases are DONE and verified; kept here only as a coverage record.

## Module 4: PO (Procurement) — COMPLETE (P1–P6c)

| Phase | Delivered |
|---|---|
| P1 | Dedupe + discovery scope |
| P2 | PO detail + lines + projection |
| P3 | PO schedules (flat `/purchaseOrderSchedules`) |
| P3b | PO distributions (deep nested path, three-id iteration) |
| P4 | Supplier contacts |
| P5 | Received-vs-ordered + invoices-by-PO |
| P5b | Synthesizer narrates child entities |
| P6 | PO aggregates (by-supplier / by-status / open-PO) |
| P6b | PO date filter (stale POs) |
| P6c | Invoiced-vs-ordered comparison |

PO is the reference module: every later module follows its build shape.

## Module 1: AR (Accounts Receivable) — 17 of 18 prompts (P1–P6)

| Phase | Delivered |
|---|---|
| P1 | Dedupe + column capture + plan |
| P2a | AR invoice by-id + lines |
| P2b | Customer invoices via account |
| P2c | Open invoices for a customer (`open_only`) |
| — | Top-5 open-invoices limit (`invoice_limit`) |
| P3 | Tax lines; DFF |
| P4 | Credit memos (list + total) |
| P5 | Account balance (`balance_only`); a customer's credit memos, receipts, receipt applications, site receipts |
| P6 | Exposure ranking; receipt-method distribution |

**AR remaining:** prompt 16 (DSO / cash-collection) — design pending, spans
`/standardReceipts` + AR balance. Prompt 18 (creation-to-update lag) —
refuses; tool registered but not reaching the parser menu (see open issues).

**AR discoveries worth carrying** (the load-bearing ones):
- `HAS_TAX_LINE` is a two-field `iter_fields` edge.
- AR invoice line rows don't echo `CustomerTransactionId` — needs the
  executor `_parent_stamp` with an opt-in `Step.stamp_parent_key` flag,
  set only by the planner on child steps feeding a further include.
- Single-clause `q=` filters server-side reliably on child resources;
  composite `q=` fails silently.
- `BillToCustomerName`/`BillToCustomerNumber` not queryable on
  `/receivablesInvoices`; `CustomerName` IS on
  `/receivablesCustomerAccountActivities`.
- `TransacationBusinessCategory` on AR invoice lines is misspelled by
  Oracle — request with the typo exactly.
- Pod gzips some responses; `curl --compressed` required.


---

# Future modules


# Module 2: GL (General Ledger) — LATER

Source: Oracle Fusion GL MCP Functional Capability Document (v1.0). 21 tools
(17 read, 4 write). Note: Oracle exposes NO create (POST) on journal resources
— journal creation is Import Journals, not REST. GL columns are complete in
the catalog (PDF source).

**Shape — different from PO/AR.** GL is not entity-list shaped. Its core is
**balances by account combination / period / currency** (a finder query,
`ledgerBalances`) and **journal batches → headers → lines** (a hierarchy).
Plus a stack of LOVs (ledgers, periods, sources, categories, chart of
accounts, currencies) — reference lists that are simple reads. The
balance-by-combination query is a new pattern Spire hasn't built.

**Writes (4).** Update / delete-draft / post / reverse journal batches. These
are PATCH/DELETE on `journalBatches`. Whether Spire does GL writes is the same
write-safety question as AP (see below) — deferrable; the 17 reads are the
bulk of the value and can ship first.

## GL P1 — Dedupe + plan (not started)

**Goal:** plan GL's 17 reads (and decide on the 4 writes). Columns are already
captured, so no column-capture step — but the balance-finder and journal
hierarchy shapes need discovery.

**Candidate phase shape (to confirm at P1):**
- GL-P2: LOVs — ledgers, periods, period statuses, sources, categories, COA,
  currencies (prompts 1, 2, 4, 5, 6, 14, 15, 16, 17). Simple reads; a natural
  first phase.
- GL-P3: ledger balances — the finder query by account/period/currency
  (prompt 3). The new pattern; needs its own discovery.
- GL-P4: journals — batches → headers → lines hierarchy (prompts 7–13).
- GL-P5 (optional): journal writes — update / delete-draft / post / reverse
  (prompts 18–21). Gated on the write-safety decision.

**Open questions for P1:**
- The `ledgerBalances` finder: what parameters does it require, and does it fit
  the entity/filter routing or need something closer to the aggregation shape?
- Read-only first, or include the 4 journal writes? (Recommend read-only P2–P4,
  writes as a separate gated phase.)

---


# Module 3: AP (Accounts Payable) — LAST

Source: Oracle Fusion AP MCP Functional Capability Document. **75 tools**
(`ap_<action>_<object>`), ~18 resources across invoice-to-pay. Columns
complete in the catalog (PDF; 23 representative tools shown of 75).

**Why AP last — and why it needs a design phase.** AP is the biggest module
(75 tools) AND the only one dominated by **writes and actions**: create /
update / delete invoices, put/release holds, create suppliers, create
payments, stop payments, validate / cancel / apply-prepayment actions. Spire
has NEVER done a write — everything to date is read-only. Starting AP means
solving "how does Spire perform mutations safely" (confirmation, idempotency,
dry-run, auth scope, audit) — a whole new capability class — on top of a large
surface. Doing it last means the read patterns are solid first and the write
design gets its own focused attention.

## AP P1 — Dedupe + write-safety design + plan (not started)

**Goal:** plan AP's reads, and DESIGN the write/action capability before any
mutation ships. Two distinct pieces of work.

**Read planning (buildable like the others):**
- AP invoices — list + filter + detail + lines + distributions + installments
  (prompts 1, 2, 3, 10; resources `invoices`, `invoiceLines`,
  `invoiceDistributions`, `invoiceInstallments`).
- AP suppliers — list + sites (prompts 13, 15) — likely overlaps Spire's
  existing supplier coverage; DEDUPE carefully.
- AP payments — list + batches (prompts 16, 19).
- Expense reports (prompt 20).
- LOVs — suppliers, payment terms, business units (prompts 21, 22, 23).

**Write/action design (the gate):** the big open question. Does Spire do AP
writes at all? If yes:
- **Confirmation model** — how a mutation is proposed and confirmed before it
  fires (create invoice, create payment, stop payment are consequential).
- **Dry-run / preview** — can Spire show what would happen without doing it?
- **Idempotency** — retries must not double-create payments.
- **Auth scope & audit** — which persona may mutate; how it's logged.
- **The architecture question** — writes don't fit the read pipeline (parse →
  plan → execute → synthesize). A mutation isn't a query. This likely needs a
  new routing kind alongside entity/aggregation/comparison, with a
  human-in-the-loop confirmation step.

**Recommendation:** AP splits into a read module (buildable now, like the
others) and a write module (needs the design phase first). Ship AP reads;
treat AP writes as their own project with the design gate above.

**Open questions for P1:**
- Read-only AP first — how much overlaps Spire's existing supplier/invoice
  coverage (dedupe)?
- Does the product actually want write operations, or is AP read-only
  sufficient for the demo/customer? (This decision scopes the whole module.)

---


---

# Endpoints catalog

The raw endpoint and prompt tables for all four modules, preserved from
`spire_expansion_endpoints.md`. Reference material for planning each module.

- **Type** — Read · Aggregate (computes over data) · Write (POST/PATCH/DELETE)
  · Action (Oracle `/action/`).
- **Columns returned** — "— to fill" = output was in a source image not yet
  captured; complete from the originals during that module's P1.
- Base REST path for all: `/fscmRestApi/resources/11.13.18.05/`.

## Column-capture status

| Module | Source | Columns |
|---|---|---|
| AR | docx (images) | #1–6 captured; #7–18 to fill |
| GL | PDF | complete |
| AP | PDF | complete (23 representative of 75 tools) |
| PO | docx (images) | #2, 4, 7, 9, 11, 16, 25 captured; rest to fill |

## AR — Endpoints

| Resource | Tool | REST endpoint | Purpose |
|---|---|---|---|
| Account Activities | `list_customer_account_activities` | `/receivablesCustomerAccountActivities` | Account headers — balances, open receivables, due |
| › credit memos | `get_account_credit_memos` | `…/{accountId}/child/creditMemos` | Credit memos for one account |
| › standard receipts | `get_account_standard_receipts` | `…/{accountId}/child/standardReceipts` | Cash receipts for one account |
| › receipt applications | `get_account_standard_receipt_applications` | `…/{accountId}/child/standardReceiptApplications` | Applied vs unapplied |
| Credit Memos | `list_receivables_credit_memos` ✓ | `/receivablesCreditMemos` | Recent credit memos + total value (AR-P4, merged). orderBy+limit server-side; total_credit stamped per row |
| › credit memo lines | `get_credit_memo_lines` | `/receivablesCreditMemos/{id}/child/receivablesCreditMemoLines` | Lines of one credit memo |
| Invoices | `get_invoice_lines` | `/receivablesInvoices` | AR invoices and billing lines |
| › invoice tax lines | `get_invoice_line_tax_lines` | `/receivablesInvoices/{id}/child/receivablesInvoiceLines/{lineId}/child/taxLines` | Tax per invoice line |
| › invoice DFF | `get_invoice_transaction_dff` | `/receivablesInvoices/{id}/child/invoiceDFF` | Flexfield segments |
| Customers | `receivables_customer` | `/receivablesCustomers` | Customer master |
| Transactions | `receivables_transaction` | `/receivablesTransactions` | AR billing transactions |
| Standard Receipts | `standard_receipt` | `/standardReceipts` | Cash receipts base object |
| › apply / unapply | `apply_receipt_to_invoice` / `unapply_receipt_application` | `/standardReceipts/{id}/child/receivableApplications` | Match cash to invoices |
| Misc Receipts | `misc_receipt` | `/miscReceipts` | Miscellaneous cash receipts |
| Receipt Methods | `receipt_method` | `/receiptMethods` | Receipt method config |

## AR — Prompts

| # | Prompt | Type | Endpoint (tool) | Columns returned |
|---|---|---|---|---|
| 1 | List all open invoices for the customer, top 5 | Read | `list_receivables_invoices` | Invoice #, Customer, Amount, Currency, Due Date, Status |
| 2 | Show invoice lines for invoice 300000248096352 | Read | `get_invoice_lines` | Line, Description, Quantity, Unit Price, Line Amount, Tax Handling |
| 3 | Get tax lines for that invoice line | Read | `get_invoice_line_tax_lines` | (0 tax lines found — none shown) |
| 4 | Fetch DFF values for this invoice | Read | `get_receivables_invoice_transaction_dff` ✓ merged | __FLEX_Context="DOO" on 1002 (TransactionDFF child; DFF child is null) |
| 5 | List recent credit memos, top 5 | Read | `list_receivables_credit_memos` ✓ merged | Memo #, Customer, Amount, Date, Status + total_credit |
| 6 | Show account activity summary for top accounts | Read | `list_customer_account_activities` | Account, Customer, Open Receivables, Total Due |
| 7 | Get all credit memos for account 300000047368512 | Read | `get_account_credit_memos` | — to fill |
| 8 | Get all standard receipts for this account | Read | `get_account_standard_receipts` | — to fill |
| 9 | Trace receipt applications for this account | Read | `get_account_standard_receipt_applications` | — to fill |
| 10 | Rank the top accounts by outstanding exposure | Read | `list_customer_account_activities` | — to fill |
| 11 | Get the AR invoice with CustomerTransactionId 300000248096352 | Read | `get_invoice` | — to fill |
| 12 | Retrieve invoice details for CustomerTransactionId 300000248096352 | Read | `get_invoice` | — to fill |
| 13 | Get recent standard receipts for Santa Clara site | Read | `get_account_standard_receipts` | — to fill |
| 14 | Show the 5 most recent credit memos and their total value | Read | `list_receivables_credit_memos` ✓ merged | 25 memos + total_credit (raw sum, -17232.52; routes to CreditMemo, not an aggregate) |
| 15 | Find invoices for ABC Corporation Americas | Read | `list_receivables_invoices` | — to fill |
| 16 | Identify cash collection trends, MoM, DSO, risks, improvements | Aggregate | `get_account_standard_receipts` | — to fill |
| 17 | Receipt method distribution — % of cash by method (Lockbox/ACH/Wire/Manual) | Aggregate | `get_account_standard_receipts` | — to fill |
| 18 | Lag between CreationDate and LastUpdateDate for each receipt | Aggregate | `get_account_standard_receipts` | — to fill |

## GL — Endpoints

| Resource | Methods | Purpose |
|---|---|---|
| `journalBatches` | GET / PATCH / DELETE | GL journal batch — read, update, delete drafts, post, reverse |
| `journalBatches/{id}/journalHeaders` | GET | Journals (headers) within a batch |
| `journalBatches/{id}/journalLines` | GET | Debit/credit lines within a journal |
| `ledgersLOV` | GET | Ledgers with currencies and IDs |
| `ledgerBalances` | GET | Account balances by combination/group, period, currency (finder) |
| `accountingPeriodsLOV` | GET | GL calendar periods — name, type, year |
| `accountingPeriodStatusLOV` | GET | Per-ledger period open/close status |
| `journalSourcesLOV` | GET | Valid journal source values |
| `journalCategoriesLOV` | GET | Valid journal category values |
| `chartOfAccountsLOV` | GET | Chart of accounts structures |
| `currenciesLOV` | GET | Enabled currencies and ISO codes |

## GL — Prompts

| # | Prompt | Type | Tool | Oracle API | Columns returned |
|---|---|---|---|---|---|
| 1 | Show all ledgers set up in our instance | Read | `gl_get_ledgers` | `ledgersLOV` | Ledger Name, Currency, Ledger ID |
| 2 | Get details for one ledger | Read | `gl_get_ledger_by_id` | `ledgersLOV/{id}` | Single ledger detail |
| 3 | Balance of account 101-10-1110 for Jun-26 in USD | Read | `gl_get_ledger_balances` | `ledgerBalances` | Account, Period, Currency, Balance amount |
| 4 | List accounting periods | Read | `gl_get_accounting_periods` | `accountingPeriodsLOV` | Period Name, Type, Year |
| 5 | Get one period by name | Read | `gl_get_accounting_period` | `accountingPeriodsLOV` | Single period row |
| 6 | Which periods are open for the US Primary Ledger? | Read | `gl_get_accounting_period_statuses` | `accountingPeriodStatusLOV` | Period Name, Status (Open/Closed) |
| 7 | List journal batches created this period | Read | `gl_get_journal_batches` | `journalBatches` | Batch Name, Status, Source, Period |
| 8 | Get one batch | Read | `gl_get_journal_batch_by_id` | `journalBatches/{id}` | Batch detail |
| 9 | Find all posted journals from the Manual source | Read | `gl_search_journals` | `journalBatches` | Filtered batch list |
| 10 | Show journals inside batch 100045 | Read | `gl_get_journals` | `…/journalHeaders` | Journal Name, Category, Currency |
| 11 | Get one journal | Read | `gl_get_journal_by_id` | `…/journalHeaders/{id}` | Journal header detail |
| 12 | Drill into the lines of that journal | Read | `gl_get_journal_lines` | `…/journalLines` | Account, Debit, Credit, Description |
| 13 | Get one line | Read | `gl_get_journal_line_by_id` | `…/journalLines/{id}` | Single line detail |
| 14 | What journal sources can we use? | Read | `gl_get_journal_sources` | `journalSourcesLOV` | Valid source values |
| 15 | What journal categories can we use? | Read | `gl_get_journal_categories` | `journalCategoriesLOV` | Valid category values |
| 16 | What chart of accounts structures do we have? | Read | `gl_get_chart_of_accounts` | `chartOfAccountsLOV` | COA structures with identifiers |
| 17 | List the currencies enabled | Read | `gl_get_currencies` | `currenciesLOV` | Currency codes & names |
| 18 | Update the completion status of batch 100045 | Write | `gl_update_journal_batch` | `journalBatches/{id}` PATCH | Updated batch confirmation |
| 19 | Delete draft batch 100060 | Write | `gl_delete_journal_batch` | `journalBatches/{id}` DELETE | Deletion confirmation |
| 20 | Post journal batch 100045 | Write | `gl_post_journal` | `journalBatches/{id}` PATCH `{Status:P}` | Posted batch confirmation |
| 21 | Reverse batch 100051 into Jul-26 | Write | `gl_reverse_journal` | `journalBatches/{id}` PATCH `{ReversalFlag:Y, ReversalPeriod}` | Reversal confirmation |

## AP — Endpoints

| Resource | Methods | Purpose |
|---|---|---|
| `invoices` | GET POST PATCH DELETE | Full lifecycle of AP invoices |
| `invoiceLines` | GET POST PATCH | Line-level detail within an invoice |
| `invoiceDistributions` | GET POST PATCH | How each line is charged to accounts |
| `invoiceInstallments` | GET PATCH | Payment schedules — due dates, amounts |
| `attachments` (invoice) | GET POST | Supporting files on invoices |
| `appliedPrepayments` / `availablePrepayments` | GET | Prepayments applied / available |
| `invoiceHolds` | GET POST PATCH | Place, review, release holds |
| `suppliers` | GET POST PATCH | Supplier master data |
| `suppliers/…/sites` | GET POST PATCH | Site-level purchasing and pay setup |
| `suppliers/…/addresses` | GET POST PATCH | Address records for a supplier |
| `suppliers/…/contacts` | GET POST PATCH | Contact people for a supplier |
| `payablesPayments` | GET POST PATCH | Create and manage supplier payments |
| `payablesPayments/…/relatedInvoices` | GET POST | Which invoices a payment settles |
| `paymentProcessRequests` | GET POST PATCH | Payment batches (PPR) |
| `expenseReports` | GET POST PATCH | Employee expense reports feeding AP |
| Invoice actions `/action/…` | POST | Validate, cancel, calculate tax, apply/unapply prepayment, generate/reverse distributions |
| Payment actions `/action/…` | POST | Stop payment, initiate escheatment |
| Reference lists (LOVs) | GET | Suppliers, payment terms, hold codes, business units, ledgers, legal entities, currencies |

## AP — Prompts

| # | Prompt | Type | Tool | Oracle API | Columns returned |
|---|---|---|---|---|---|
| 1 | Show all invoices created today | Read | `ap_list_invoices` | GET `invoices` | Invoice Number, Supplier, Amount, Currency, Status |
| 2 | List unpaid invoices over 10,000 for Vision Operations | Read | `ap_list_invoices` (filter) | GET `invoices?q=InvoiceStatus=Unpaid;InvoiceAmount>1000` | Invoice, Supplier, Amount, Due Date |
| 3 | Get details of invoice 300100123 | Read | `ap_get_invoice` | GET `invoices/{id}` | Full header: supplier, dates, amount, terms, status, business unit, description |
| 4 | Create an invoice | Write | `ap_create_invoice` | POST `invoices` | New invoice with its id |
| 5 | Update an invoice | Write | `ap_update_invoice` | PATCH `invoices/{id}` | Updated invoice fields |
| 6 | Delete an invoice | Write | `ap_delete_invoice` | DELETE `invoices/{id}` | Deletion confirmation |
| 7 | Validate invoice INV-1042 | Action | `ap_validate_invoice` | POST `…/validateInvoice` | Validation outcome |
| 8 | Cancel invoice INV-1099 | Action | `ap_cancel_invoice` | POST `…/cancelInvoice` | Cancellation result |
| 9 | Apply available prepayments to invoice 300100123 | Action | `ap_apply_prepayment` | POST `…/applyPrepayments` | Prepayment application result |
| 10 | Which invoices are on hold for Advanced Network Devices? | Read | `ap_list_invoice_holds` | GET `invoiceHolds` | Held invoices with hold name and reason |
| 11 | Put invoice 300100123 on hold | Write | `ap_create_invoice_hold` | POST `invoiceHolds` | New hold record with reference |
| 12 | Release the hold on invoice 300100123 | Write | `ap_update_invoice_hold` | PATCH `invoiceHolds/{id}` | Updated (released) hold |
| 13 | Show me 10 active suppliers | Read | `ap_list_suppliers` | GET `suppliers` | Supplier Name, Number, Type, Status |
| 14 | Create a new supplier called Globex Ltd | Write | `ap_create_supplier` | POST `suppliers` | New supplier number and id |
| 15 | What sites does supplier Acme have? | Read | `ap_list_supplier_sites` | GET `suppliers/…/sites` | Sites with procurement business unit and pay setup |
| 16 | List payments made this month | Read | `ap_list_payments` | GET `payablesPayments` | Payment Number, Supplier, Amount, Date, Status |
| 17 | Create a payment | Write | `ap_create_payment` | POST `payablesPayments` | New payment with its id |
| 18 | Stop payment on check 45012 | Action | `ap_stop_payment` | POST `…/initiateStopPayment` | Stop-payment confirmation |
| 19 | List payment batches | Read | `ap_list_payment_process_requests` | GET `paymentProcessRequests` | PPRs and status |
| 20 | List expense reports | Read | `ap_list_expense_reports` | GET `expenseReports` | Expense reports table |
| 21 | Supplier lookup | Read | `ap_lov_suppliers` | GET `suppliersLOV` | Matching suppliers with ids |
| 22 | What payment terms are available? | Read | `ap_lov_payment_terms` | GET `payablesPaymentTerms` | Payment terms (Net 30, Net 45) with ids |
| 23 | Business-unit lookup | Read | `ap_lov_business_units` | GET `finBusinessUnitsLOV` | Business units with ids |

_Full 75 AP tools follow `ap_<action>_<object>` across every resource above._

## PO — Endpoints & Prompts

The PO catalog is preserved here for completeness; the module is COMPLETE
(see Module 4 above).

| Resource | Endpoint |
|---|---|
| Purchase Orders | `/purchaseOrders` |
| PO Details | `/purchaseOrders/{POHeaderId}` |
| PO Lines | `/purchaseOrders/{POHeaderId}/child/lines` |
| PO Schedules | `/purchaseOrders/{POHeaderId}/child/lines/{POLineId}/child/schedules` (also flat `/purchaseOrderSchedules?q=POHeaderId=`) |
| PO Distributions | `…/schedules/{LineLocationId}/child/distributions` (nested only) |
| Suppliers | `/suppliers` |
| Supplier Sites | `/suppliers/{SupplierId}/child/sites` |
| Supplier Contacts | `/suppliers/{SupplierId}/child/contacts` |
| Invoices | `/invoices` |
| Receipt Requests | `/receivingReceiptRequests` |

PO prompts 1–25 and their build dispositions are captured in Module 4's P1
dedupe table above.


---

# Feature backlog


## Features

### 1. Natural-language entry to Design 3

**Status:** done (implemented + verified live). See
`docs/designs/feature_1_nl_parser_design.md`.

**What:** An LLM-driven layer that converts a natural-language prompt
into an Intent. The Intent is what the deterministic planner already
consumes today.

**Why:** Today every prompt shape requires a hand-built Intent in
`run_plan.py`. Doesn't scale. This is the single largest unlock —
removes the bottleneck on what prompts the system can handle.

**Bounded by:** the KG. The parser can only produce Intents using
entities, filters, and patterns the KG declares. Anything outside
that returns a clear "can't answer" Intent.

**Dependencies:** 5 (satisfied).

**Effort:** large.

---

### 2. Invoice date upper bound

**Status:** done. Closes G1.

---

### 3. Supplier status filter

**Status:** done. Closes G2.

---

### 4. Migrate remaining tools to ToolResult

**Status:** done (search_suppliers + search_purchase_orders; get_buyer
intentionally not migrated — single unique-key lookup). Closes G3.

---

### 5. Synthesizer schema generalization

**Status:** done. Three sibling per-entity schemas selected by
target_entity.

---

### 6. New entity: contracts

**What:** Add Contract to the KG (entity, fields, edges, vocabulary).
Build `search_contracts` tool.

**Why:** "Contract renewals due next quarter" fails today because
Contract isn't in the system. Adds a new data domain.

**Dependencies:** ideally after 1, 4, 5 — so contracts get NL-parsed
entry, truncation honesty, and flexible schema.

**Design:** pending a brainstorming session before work starts.

**Effort:** small to medium.

---

### 7. Aggregation tools

**What:** Tools that aggregate server-side, returning small structured
results. First: `aggregate_invoices_by_supplier` with date range and
top_n. More as prompts demand.

**Why:** Closes G4. "Top 10 suppliers by spend" etc. The LLM never does
math; the tool aggregates in Python.

**Note:** keep aggregation shapes bounded — specific tools per shape,
not a generic engine.

**Dependencies:** parser (1) should route aggregation prompts here.

**Design:** pending a brainstorming session before work starts.

**Effort:** medium per shape.

---

### 8. Graceful refusal for unsupported prompts

**Status:** done. Closes G5 in part.

**What:** Turns the parser's structured refusal into a polished,
capability-framed user message generated from the KG. New
`capability.py` module: `derive_flavor` re-derives the correct flavor
from the draft + KG menu (a self-declared refusal naming an unknown
entity is now UNKNOWN_ENTITY, aggregation is UNSUPPORTED_OPERATION,
genuinely vague prompts stay UNPARSEABLE); `capability_message` builds
the user-facing wording — what Spire can do (from the KG menu, so it
never goes stale) plus why the prompt is outside it. Wired into
`run_plan.py`'s refusal printer.

**Why:** Closed G5 in part. The feature-1 refusal was honest but blunt
and mislabeled self-declared refusals.

**Dependencies:** 1 (done).

**Effort:** small.

---

### 9. KG-to-tool determinism test framework

**What:** A test harness that traces a prompt through
`prompt -> KG context -> LLM -> Intent -> plan -> tool name` and asserts
the plan-to-tool segment is deterministic — a given Intent always
selects the same tools, byte-identical across runs. Includes a curated
prompt taxonomy and produces a prompt-to-tool table as living
documentation.

**Why:** Spire's core claim is that tool selection is deterministic
(planner lookup, not LLM judgment). Today that's asserted in design docs
and exercised only indirectly. This makes it a checked, regenerable
artifact — and the evidence behind the architecture explainer's
"why not an agent" argument.

**Bounded by:** the existing planner and KG bindings; this is a test
harness over existing components, not new runtime code.

**Dependencies:** 1 (parser), and the planner/binding tables (done).

**Design:** drafted early in
`docs/designs/feature_determinism_test_framework_design.md` — a
proposal, to be confirmed at feature start (per the roadmap convention
that designs are finalized when work begins).

**Effort:** small to medium.


## Execution order

### Phase one: foundation — DONE
**2 -> 3 -> 4 -> 5.** Closed known gaps, strengthened the tool layer.

### Phase two: architectural shift — DONE
**1 -> 8.** NL parser landed; graceful refusal wording landed.

### Phase three: capability expansion — NEXT
**6, 7 (parallel, as demand surfaces).** Demand-driven; don't build
preemptively. Design for each is settled in a brainstorming session
before work starts.

---

## Backlog summary

| # | Feature                                  | Effort  | Status | Closes |
|---|------------------------------------------|---------|--------|--------|
| 2 | Invoice date upper bound                 | small   | done   | G1     |
| 3 | Supplier status filter                   | small   | done   | G2     |
| 4 | Migrate remaining tools to ToolResult    | medium  | done   | G3     |
| 5 | Synthesizer schema generalization        | medium  | done   | —      |
| 1 | Natural-language entry                   | large   | done   | —      |
| 8 | Graceful refusal                         | small   | done   | G5     |
| 6 | New entity: contracts                    | small-medium | open | —    |
| 7 | Aggregation tools                        | medium  | open   | G4     |
| 9 | Determinism test framework               | small-medium | open | — |

Features 1–5 verified against the live Fusion pod. Feature 1 also
verified against live Gemini (parser integration suite green).

---


---

## Component lifecycle

### Track A agent — cleared for removal

The Track A agent (`ask.py` -> `runner.py`, the LLM-as-planner baseline)
is **not** part of the Design 3 runtime and is never invoked by the
Design 3 pipeline. It was kept as the evaluation baseline — the
comparison arm that would justify the Design 3 architecture.

**Decision: the baseline comparison will not be run.** Design 3 / Way 2
is the committed architecture; the agent's only remaining job was to
justify that choice, and the choice is made. So the agent is now
**cleared for removal** — its lifecycle no longer gates on a comparison
that won't happen.

Code to remove when the cleanup is done:
- `scripts/ask.py` (the agent entry point)
- `src/spire/agent/` (`runner.py`, `prompts.py`, `lg_utility.py`,
  `tracing.py` — confirm `tracing.py` isn't shared by `run_plan.py`
  before deleting it)
- `tests/test_agent_runner.py`, `tests/test_prompts.py`
- `inspect_trace.py` is agent-shaped and doesn't parse `run_plan`
  traces; remove or repoint as part of the same cleanup.

Not yet deleted — this is a tracked, deliberate cleanup step, not done
in passing.

### Design 3 (Way 2) is deliberately NOT an agent

Design 3 is not an agentic architecture and is not meant to become one.
The LLM is bounded to two single-shot roles — the interpreter (the
feature-1 parser) and the synthesizer — with a deterministic planner and
executor in between. There is no tool-calling loop, no
`assistant -> tools -> assistant` cycle, no LLM-driven control flow. This
is the property that makes the pipeline predictable and its failures
attributable to a specific stage, and it is the defining difference from
the Track A agent. Future features add bounded tools and schemas; they do
not reintroduce agent-style orchestration.

---


## Future tasks (tracked)

Follow-ups deferred during the LangGraph migration and provider work.
Recorded here so they aren't lost; none is started.

### F1. Retire Track A

Remove `scripts/ask.py` and `src/spire/agent/` now that `run_graph.py`
is the single entry point and Track A is no longer used. See the Track A
removal notes above for the exact file list. Deliberate cleanup commit,
not done in passing.

**Effort:** small.

### F2. Parallelize the aggregation fetch

`aggregate_invoices_by_supplier` paginates the full date range
sequentially (~43 calls for a year, ~185s per prompt). Fetch pages
concurrently (e.g. count first, then `asyncio.gather` the pages) to cut
wall time. Progress reporting already exists; this is a speed change
only, behavior unchanged.

**Effort:** small to medium.

### F3. Client-visible progress is done; extend if needed

Progress now threads tool -> server -> graph -> caller via
`report_progress` / `progress_handler`. No further work unless we want a
total/percentage (needs an upfront count query).

**Effort:** n/a unless extended.

### F4. Multi-provider — finish and harden

Gemini, OpenAI, and Anthropic are wired in `config.build_llm()` and
verified to route correctly (Gemini + OpenAI return live results).
Remaining: confirm Anthropic end-to-end with a valid model ID and funded
key, and sanity-check structured-output parity across providers on the
parser and synthesizer schemas (tool-calling vs Gemini schema mode can
differ).

**Effort:** small.

---

## Note: the pipeline is now a LangGraph graph

Design 3 is now expressed as a LangGraph custom graph
(`src/spire/graph/pipeline.py`, run via `scripts/run_graph.py`). This did
NOT make it an agent: the graph is bounded — fixed edges, the same
parse -> plan -> execute -> synthesize stages wrapping the existing
functions, no tool-calling loop and no LLM-driven control flow. The
"deliberately NOT an agent" property above still holds; only the
orchestration mechanism changed (imperative `run_plan.py` -> graph).
`run_plan.py` has been retired (2026-07-24); `run_graph.py` is the single
entry point, and shared formatters live in `scripts/display_formatters.py`.
