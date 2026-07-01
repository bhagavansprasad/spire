# Spire — SME Validation Checklist

Black-box validation of the Spire framework with an Oracle
procurement / HCM subject-matter expert (SME).

**Purpose.** Validate the framework *as it stands today* — as a black
box, without reading code — against what a domain expert knows to be
true in Oracle Fusion. If the framework proves correct on the current
endpoint set, that result is the basis for widening scope by integrating
more endpoints.

**Current scope under test.** The KG is built over four entities:
Supplier, Invoice, PurchaseOrder, and Buyer (cross-pillar, from HCM
`publicWorkers`). Supplier is the only valid query target. This
checklist tests exactly that surface — not future domains.

**How to use.** Work top to bottom. For each item, record Pass / Fail /
Partial and a note. The goal is to find where the framework is wrong,
not to confirm it is right — a failed item found now is worth more than
a passed demo.

---

## What Spire is (context for the reviewer)

Spire turns a plain-English procurement question — e.g. "suppliers in
the US with open purchase orders and no invoices in six months" — into a
correct, structured answer from a live Oracle Fusion pod. It is aimed at
consultants and procurement/finance users who shouldn't have to
hand-write REST queries across FSCM and HCM.

The design is deliberately bounded: an LLM is used only to interpret the
question and phrase the answer; the steps in between — which endpoints to
call and which business rules to apply — are deterministic code, so the
same question always yields the same result.

The framework's central choice is *who plans the query*. In traditional
function-tool calling the LLM is the planner — it picks which tools to
call — and this degrades as the tool catalog grows: more tools mean more
misrouting and hallucination. Spire moves planning to the KG: the LLM
only interprets the question, and tool selection becomes a deterministic
KG lookup rather than an LLM judgment. Validating that this KG-driven
planning stays correct — and stays correct as scope grows — is what this
exercise tests.

What makes this work is the **Knowledge Graph (KG)**: a small authored
model of the procurement domain — the entities (Supplier, Invoice,
PurchaseOrder, Buyer), how they join, which endpoint serves each, and a
**vocabulary** mapping business language to Fusion codes ("vendor" →
Supplier, "open" → the PO status code). Validating whether that domain
model is *correct* is the heart of this exercise.

**Tech stack.** LangGraph (pipeline) · KG in Oracle tables · MCP for
Fusion calls · provider-swappable LLM (Gemini / OpenAI / Anthropic) ·
live Oracle Fusion Cloud pod (FSCM + HCM REST).

---

## 1. Answer correctness (the core black-box test)

Give prompts; check outputs against ground truth the SME confirms
independently in Fusion (UI or direct REST). Every number should be
reconcilable — do not eyeball for plausibility.

| # | Item | Method | Result | Note |
|---|------|--------|--------|------|
| 1.1 | Supplier data accuracy — returned suppliers match Fusion | Run a country prompt; SME pulls the same set in Fusion; compare | | |
| 1.2 | Counts match | Compare record counts (returned vs Fusion) | | |
| 1.3 | Filter correctness — country filter returns the right suppliers | Inspect whether filter matches business meaning, not just a code | | |
| 1.4 | Join correctness — buyer attached to a PO is the correct buyer | Trace one PO → buyer across FSCM→HCM; SME confirms identity | | |
| 1.5 | Negation correctness — "no invoices in N months" truly means absence | SME verifies a flagged supplier genuinely has no invoices in range | | |
| 1.6 | Aggregation correctness — "top N by spend" totals reconcile | Compare rankings + totals against Fusion's own figures | | |

---

## 2. Domain semantics (where the SME is irreplaceable)

The KG encodes a translation from business language to Fusion codes.
Only an SME can confirm that translation is faithful. Validate these
from the KG vocabulary/status tables directly — no run needed.

| # | Item | Method | Result | Note |
|---|------|--------|--------|------|
| 2.1 | Business-term mapping — "vendor/supplier", "spend authorized", "active" mean what the KG says | Review vocabulary table with SME | | |
| 2.2 | Status/code fidelity — "open PO" maps to the correct StatusCode(s) | Confirm the mapping is complete (Fusion has more states than OPEN/CLOSED) | | |
| 2.3 | Country semantics — the country filter uses the business-correct field | Clarify MatchedCountry vs TaxpayerCountryCode: which is "a supplier in X"? | | |
| 2.4 | Edge-case entities — tax authorities, one-time/intercompany suppliers | Ask whether these should be counted as "suppliers" in results | | |

*2.3 note:* current output shows suppliers with MatchedCountry=IN but
TaxpayerCountryCode=US. The SME should rule on whether that is correct
for "suppliers in India" — it is exactly the kind of semantic ambiguity
only a domain expert settles.

---

## 3. Scope and refusal behavior

| # | Item | Method | Result | Note |
|---|------|--------|--------|------|
| 3.1 | Refusal correctness — the right prompts are refused | Feed out-of-scope prompts; SME confirms each is genuinely out of scope | | |
| 3.2 | No wrongful refusal — in-scope prompts are not rejected | Feed valid but oddly-phrased prompts | | |
| 3.3 | Silent wrongness — confident answers that are subtly wrong | SME actively hunts for these; the most dangerous failure mode | | |
| 3.4 | Coverage gaps — common procurement questions the framework can't handle | SME lists real questions a consultant would ask; feeds roadmap | | |

---

## 4. Trust and honesty

| # | Item | Method | Result | Note |
|---|------|--------|--------|------|
| 4.1 | Truncation honesty — partial examination is disclosed | Confirm "N of M examined" appears when source is truncated | | |
| 4.2 | Hallucination guard — cannot invent a supplier or ID | Try to induce a fabricated entity; confirm it refuses/errors | | |
| 4.3 | Determinism — same prompt yields the same answer across runs | Run one prompt 2–3 times; compare | | |

---

## 5. Fitness for real use

| # | Item | Method | Result | Note |
|---|------|--------|--------|------|
| 5.1 | Prompt naturalness — works on how consultants really phrase questions | SME writes prompts in their own words, unprompted by examples | | |
| 5.2 | Answer usefulness — output is in a form a consultant would actually use | SME judges the report/answer format | | |
| 5.3 | Explanation legibility — a consultant can tell what the system did | Review the intent/plan/answer trace for clarity | | |

---

## 6. Forward-looking: readiness to widen scope

Only relevant *if* sections A–E pass. This is the "what next" the SME
helps shape — not part of the current framework, but the plan it unlocks.

| # | Item | Method | Result | Note |
|---|------|--------|--------|------|
| 6.1 | Endpoint priority — which new Fusion endpoints add the most value next | SME ranks candidate domains by real consultant demand | | |
| 6.2 | Endpoint truth — for each new endpoint, the real join keys and filterable fields | SME confirms the field/key facts before KG authoring | | |
| 6.3 | Access/security model — what a new endpoint requires (scope grants, self-service vs admin) | SME describes how that data is governed in practice | | |
| 6.4 | Semantic pitfalls — known asymmetries or quirks in candidate endpoints | SME flags the "SupplierId vs SupplierNumber"-style traps in advance | | |

---

## Materials to give the SME

1. **A prompt-to-output test set** — the prompts you will run, so the SME
   can check answers against Fusion ground truth.
2. **The KG vocabulary + status mappings as a plain table** — so the SME
   can validate semantics (section B) directly, without running anything.
3. **The architecture explainer** — one read so they understand what the
   black box claims to do before probing it.

---

## The one rule for the "report" validation

A report that *looks* right can still be built on wrong data. Every
figure in the report must be independently reconcilable against Fusion —
the SME pulls the same query in Fusion and compares. Plausibility is not
validation. (This is the Phase-A lesson: a misread was only caught by a
direct call against the API, not by inspection.)

---

## Appendix — Validation prompt set

A representative set to run during validation, grouped by expected
outcome. The right-hand column links each prompt to the check item(s) it
exercises. A prompt that behaves outside its group (e.g. a refusal that
returns data) is an immediate fail.

### Supported — must return data

| Prompt | Exercises |
|--------|-----------|
| List all suppliers in India | 1.1, 1.2, 2.3 |
| Show me suppliers in the United Kingdom | 1.1, 1.3 |
| Find suppliers in US | 1.3, 2.3 |
| List active suppliers in the US | 1.3, 2.1 |
| US suppliers with no invoices in the last 6 months | 1.5 |
| Suppliers in the US with open purchase orders and no invoices in 6 months, include the buyer | 1.4, 1.5, 2.2 |
| Which US vendors have open POs? Show the purchasing agent. | 1.4, 2.1, 2.2 |

### Aggregation — must return rankings

| Prompt | Exercises |
|--------|-----------|
| Top 10 suppliers by spend in 2022 | 1.6 |
| Which suppliers did we spend the most with in 2022 | 1.6 |
| Show me the top 5 suppliers by total invoice amount in 2022 | 1.6 |

### Refusals — must be declined (out of scope)

| Prompt | Exercises |
|--------|-----------|
| Show me invoices for supplier 1252 | 3.1 |
| Show me contract renewals due next quarter | 3.1 |
| Top 10 suppliers by total spend (no date range) | 3.1 |
| Who is our best supplier? | 3.1 |

### Suggested SME-authored prompts

Ask the SME to add 3–5 prompts in their own words, unprompted by the
examples above — this tests prompt naturalness (5.1) and surfaces
coverage gaps (3.4). Record each with its outcome and whether it was
correct.

| SME prompt | Expected | Outcome | Correct? |
|------------|----------|---------|----------|
| | | | |
| | | | |
| | | | |
