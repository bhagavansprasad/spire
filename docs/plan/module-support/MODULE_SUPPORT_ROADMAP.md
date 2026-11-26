# Fusion module support roadmap and playbook

**Status:** Parked; planning baseline captured, with AP prompts still pending.
No module implementation has started.
**Reviewed:** 2026-11-26
**Planning branch:** `ModuleSupport-Roadmap`
**Scope:** Establish a repeatable, REST-first process for adding one Fusion
module at a time. SQL generation and SQL editor work are later phases.

## 1. Decisions and working assumptions

1. The first delivery goal is **prompt → Fusion REST → verified results**.
2. Plan and deliver one module per implementation branch. This branch is for
   the roadmap and module playbook only.
3. Start litmus-prompt collection with **Financials**, as agreed with the
   Product Owner. **AP/Payables is confirmed** as the first detailed module
   because it is first in the Financials list and already has partial Spire
   support; confirm the implementation scope against Venu's prompts.
4. The Product Owner confirmed that the module list is complete and the first
   three listed areas in each family are priorities. The lower-priority
   sequence in §3 is provisional; confirm demand, SME availability, pod access,
   and endpoint feasibility before committing to delivery.
5. AP, AR, and PO are **partially supported today**, not complete module
   implementations. Their remaining capability gaps are a separate
   capability-expansion backlog.
6. SQL is deliberately out of the first module's acceptance criteria. Record
   physical schema and SQL mapping evidence when useful, but do not build the
   SQL projection/editor as a gate for REST-backed results.
7. Prefer common abstractions only after the first module demonstrates that a pattern
   is shared. Do not generalize a one-module assumption prematurely.

Meeting decisions and action items are recorded in
[MODULE_SUPPORT_MEETING_MINUTES.md](MODULE_SUPPORT_MEETING_MINUTES.md).

## 2. Scope inventory

The requested portfolio contains **18 named areas** across three Fusion
families. Three overlap with current Spire support; the other 15 are candidates
for net-new support.

| Family | Requested areas | Current Spire position |
|---|---|---|
| Financials | AP, AR, GL, CM, FA, SLA | AP/Payables and AR/Receivables have partial support. GL, CM, FA, and SLA are candidates. |
| SCM | PO, OM, INV, WIP, BOM, Cost Management | PO/Procurement has partial support. OM, INV, WIP, BOM, and Cost Management are candidates. |
| HCM | Global HR, Payroll, Absence, Benefits, OTL, ORC | HCM is not a top-level routed module today, although Buyer-related worker data is used by Procurement; all six listed areas are candidates. |

**Naming note:** This plan interprets Financials `CM` as **Cash Management**.
Confirm this with the product owner before using it as a module identifier.
Supplier is existing shared master data, not an additional item in the 18-area
count.

Current routing recognizes `payables`, `procurement`, `receivables`, and
`supplier` in [context_assembly.py](../../../src/spire/nl_parser/context_assembly.py)
and the KG's module constraint is defined in
[kg_schema.sql](../../../scripts/sql/kg_schema.sql). The existing REST discovery
method in [SCHEMA_DISCOVERY_METHOD.md](../SCHEMA_DISCOVERY_METHOD.md) is
primarily about physical SQL schema discovery; it is useful later, but it does not
replace the REST-first discovery in this playbook.

## 3. Agreed priority and provisional order

The first three entries in each family are the Product Owner's priority set.
Prompt collection starts with Financials. The order among items beyond those
priority sets is a planning recommendation, not a delivery-date promise or a
claim that the Fusion products have these exact technical dependencies.

| Priority | Family | Areas |
|---:|---|---|
| First three — priority | Financials | AP, AR, GL |
| First three — priority | SCM | PO, OM, INV |
| First three — priority | HCM | Global HR, Payroll, Absence |
| Later — proposed sequence | Financials | CM, FA, SLA |
| Later — proposed sequence | SCM | WIP, BOM, Cost Management |
| Later — proposed sequence | HCM | Benefits, OTL, ORC |

AP, AR, and PO remain partial capabilities even though they are in the
priority sets. Assess their gaps rather than treating them as either complete
or wholly new. AP is confirmed as the first detailed module; its final scope
depends on the incoming litmus prompts and endpoint-behavior verification.
HCM privacy and authorization are hard gates, not reasons to weaken access
controls.

## 4. Repeatable module-support activities

Each module implementation branch should use these gates. A gate is complete
only when its evidence and decision are recorded.

| Gate | Activities | Required output / exit condition |
|---|---|---|
| 0. Module brief | Confirm business owner, users, use cases, module boundary, terminology, priority, and out-of-scope requests. Resolve acronym ambiguity. | Approved module brief and named SME/contact. |
| 1. REST feasibility | Confirm authorized pod, base path/resource family, authentication, user roles, read permissions, rate/record limits, pagination, sorting, count semantics, filtering syntax, expansions, and error behavior. Test representative calls read-only. | Endpoint inventory with captured requests/responses, constraints, and access decision. No credentials in docs or logs. |
| 2. User task discovery | Interview an SME; collect real questions, expected columns, filters, parent-child paths, synonyms, negative cases, and known business rules. Use verified record identifiers from the pod. | Prioritized prompt set with expected answer shape and source evidence. |
| 3. MVP boundary | Select a small number of root entities and workflows. Define supported fields, filters, includes, result caps, count disclosure, and explicit refusal boundaries. Identify sensitive fields and row-level access rules. | Versioned capability matrix; every in-scope prompt maps to a feasible REST path. |
| 4. Data and workflow model | Map each prompt to endpoint(s), parameters, parent/child traversal, stable identifiers, data normalization, and join assumptions. Verify with multiple records and edge cases. | REST workflow diagrams/tables and field dictionary; unresolved assumptions listed. |
| 5. Spire design | Decide entity/module names, synonyms, root eligibility, tool contracts, pagination/truncation representation, KG entities/edges/filters/fields, parser context, classifier vocabulary, and response model. Reuse shared pipeline helpers where evidence supports it. | Reviewed design and implementation checklist; no unsupported assumptions hidden in prompts. |
| 6. Core implementation | Implement only the agreed REST path: tool(s), KG seed/metadata, parser/routing context, planner/executor integration, typed result synthesis, and API/CLI exposure as required. Keep tool errors explicit. | End-to-end prompt-to-results path on the authorized pod. |
| 7. Verification | Unit-test mapping, filters, pagination, and failures; integration-test against the pod; compare representative records to direct REST responses; run SME prompts; test empty, capped, unauthorized, malformed, and multi-page cases. | Passing targeted tests and an evidence-backed acceptance report. Counts and partial-result warnings must be truthful. |
| 8. Release and learn | Update runbooks, module inventory, prompt sets, and docs; record known limits; review security and operational impact; release through PR. | Merged module branch, known-gap list, and retrospective input for the shared playbook. |

## 5. First detailed module — Payables (AP)

AP is the confirmed first detailed module because it is first in the
Product Owner's Financials list and has partial support in Spire. Treat this
as a **capability expansion**, not a claim that AP is unsupported or complete.
The final MVP must be checked against the litmus prompts Venu supplies and the
endpoint behavior on the target pod.

### 5.1 Why AP is first

- It follows the agreed Financials-first prompt-collection order.
- Existing AP invoice support provides a baseline for distinguishing working
  behavior from gaps and prevents a false “new module” framing.
- A module-by-module litmus set can turn the Product Owner's “must not fail”
  requirement into measurable acceptance criteria.

Initial read-only checks used the previous pod configuration. After the
configuration was updated, bounded read-only requests to the AP invoices
endpoint and the Supplier control endpoint succeeded on 2026-11-26. The AP
response shape and field names were inspected without inspecting invoice
values. This confirms endpoint access, not end-to-end prompt coverage or field
semantics.

### 5.2 Discovery questions to answer before implementation

1. Which 10–20 AP prompts are most common and must not fail? What result does
   the SME expect for each?
2. Which prompts are already covered by Spire's AP invoice path, and which
   expose a real gap? Record pass/partial/gap with evidence.
3. Which REST resources and user roles are available on the target pod?
4. What are the endpoint's filtering, sorting, pagination, count, and
   result-limit semantics?
5. Which identifiers, fields, and parent-child paths are needed for each
   approved prompt? Which values are display labels versus internal codes?
6. Which fields or records are sensitive, and what access boundaries apply?
7. Which representative records, empty cases, and negative cases can the SME
   verify?

### 5.3 AP implementation scope

Do not assume every AP workflow belongs in the first increment. Reconcile
Venu's prompt set with current support, then agree the smallest useful
implementation boundary. For each prompt, document:

- user prompt and intended interpretation;
- current Spire behavior: pass, partial, gap, or out of scope;
- root entity and REST endpoint path;
- request parameters, server-side filters, sort order, and paging;
- fields returned and any normalization;
- expected count/truncation behavior;
- access boundary and refusal behavior;
- pod record(s) and SME-verified expected result;
- unit and integration test names.

### 5.4 AP acceptance

The AP increment is complete when:

- at least one approved, representative prompt works end-to-end through Spire
  to the authorized Fusion REST resource;
- every approved AP litmus prompt in the committed release set passes its
  agreed expected-result criteria, or has an explicitly accepted disposition;
- the returned values and identifiers are traceable to REST source records;
- filters, sorting, pagination, and total-count claims match observed endpoint
  behavior or clearly disclose limitations;
- empty results, unsupported requests, permission failures, and partial/capped
  results do not look like successful complete answers;
- tests cover the supported request shapes and key edge cases;
- docs describe the exact supported scope and known gaps;
- no SQL emitter or SQL editor work is required for acceptance.

## 6. After the first module

Before starting the next module:

1. Hold a short retrospective against the eight gates: effort, surprises,
   failed assumptions, test gaps, endpoint quirks, and SME review time.
2. Mark each playbook step as reusable, pilot-specific, or missing; update this
   document with evidence rather than generalizing from one example.
3. Promote only demonstrated shared functionality into common Spire helpers.
   Keep module-specific rules and permissions isolated.
4. Re-score the remaining modules and confirm the next priority with the
   product owner.
5. Start a **new module-specific branch from the updated integration branch**
   for the next implementation. Do not combine two module implementations in
   one branch.
6. Schedule SQL parity only after the REST behavior and canonical result shape
   are stable. Compare semantically equivalent result sets under matching
   filters, scope, and paging; do not assume byte-for-byte equality.

## 7. Related cross-cutting features

- **CSV/Excel export:** not a blocker for the first REST path. Once structured
  results are stable, CSV export of the exact displayed records is a generic
  UI/API enhancement that can be delivered once for all modules. Exporting all
  matching rows requires a separate pagination, progress, and failure design.
  Excel can follow CSV if needed.
- **SQL generation/editor:** deferred. Keep SQL metadata and physical-schema
  evidence for a later parity phase, but do not let the SQL overlay or editor
  delay core prompt-to-results support.
- **Counts and truncation:** core correctness, not a cosmetic enhancement. A
  capped result must distinguish records returned from records matching and
  must not imply that the sample is the complete set.

## 8. Branch and document discipline

- This roadmap branch contains planning documentation only; do not add module
  runtime behavior here.
- Name the all-module planning branch `ModuleSupport-Roadmap`.
- Name each module-specific investigation/implementation branch
  `ModuleSupport-<Family>-<Module>`, for example
  `ModuleSupport-Financials-AP`, `ModuleSupport-SCM-INV`, and
  `ModuleSupport-HCM-Global-HR`. Use this initiative-specific convention
  instead of the general phase prefix for module-support work.
- After this plan is reviewed and merged, start each module branch from the
  updated `master` and deliver it through the repository's PR flow.
- Each module branch updates its own prompt set, tests, module capability
  notes, and this roadmap's status after the implementation is verified.
- Mark an area “supported” only with a documented, tested capability boundary;
  avoid a binary label that hides partial support.

## 9. Open decisions

- Confirm `CM` means Cash Management.
- Receive Venu's first Financials/AP litmus prompts and expected results.
- Reconcile the REST `DueDate` field and the AP synthesized output with the
  older SQL-oriented SME note; verify which date "created" prompts should use.
- Define the intended result-count disclosure and user-facing pagination
  behavior for the first module.
- Decide the delivery timing for generic CSV export after the core response
  contract is stable.
