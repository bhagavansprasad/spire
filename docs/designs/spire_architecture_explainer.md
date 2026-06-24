# Spire — Architecture Explainer

*A KG-driven, bounded pipeline that answers natural-language procurement
questions against live Oracle Fusion.*

Audience: Oracle HCM / OCI expert — as technical reviewer and as
integration partner. This document explains what Spire is, why it is
built the way it is, and what is needed to extend it into HCM.

---

## 1. The one-line story

Spire turns a natural-language question from a Fusion consultant into a
correct, structured answer against a live Oracle Fusion pod — by
confining the LLM to two narrow roles and doing all Fusion logic
deterministically.

---

## 2. The problem

Fusion's REST surface is large, quirky, and pod-specific. A single
consultant question maps to several endpoints across FSCM and HCM, with
join asymmetries and filters Fusion will not perform server-side.

Reference question:

> "Suppliers in the US with no invoices in the last 6 months but with
> open purchase orders, including the buyer."

Answering this correctly requires knowing things that are not obvious
from the API alone:

- Invoice references a supplier by `SupplierNumber`, but PurchaseOrder
  references the same supplier by `SupplierId`. Same supplier, two
  different keys.
- Buyer is not in FSCM at all. `BuyerId` on a PO equals `PersonId` on
  HCM `publicWorkers`. There is no `/buyers` endpoint on the pod.
- Composite `q=` filters are unreliable on this pod, so you must
  over-fetch and filter client-side.
- "No invoices in 6 months" is negation-by-absence — the answer is the
  *empty* result, which naive tool-calling routinely mishandles.

---

## 3. Why traditional tool-calling (an agent) is the wrong fit

An agent hands the LLM a pile of tools and lets it reason live about
which to call and in what order. On a surface like Fusion this fails in
predictable ways:

1. It guesses join keys it cannot know (the SupplierId vs SupplierNumber
   asymmetry).
2. It hunts for endpoints that do not exist (a FSCM `/buyers`).
3. It trusts the API and does not know pod quirks (composite `q=`).
4. It mishandles "absence is the signal" cases.
5. It loops, picks wrong tools, and fails *unattributably* — when the
   answer is wrong you cannot say which step broke.

This is not hypothetical. An agent baseline (Track A) was built
specifically as the comparison arm to test this. The bounded design was
then committed deliberately — an engineering decision backed by the
comparison, not an assumption.

---

## 4. The architecture: a bounded pipeline

```
NL prompt → 1·Parse (LLM) → 2·Plan (code) → 3·Execute (code) → 4·Synthesize (LLM) → answer or refusal
```

The LLM appears only at the two ends. The middle is deterministic. Each
stage:

**1 · Parse (LLM).** Reads the prompt and produces a structured Intent.
This is the only place language is interpreted. It is bounded by the KG:
it may only use entities and fields the KG defines, and it resolves the
user's words through the KG Vocabulary — mapping business terms to
canonical values ("vendor" → Supplier, "open" → "OPEN", "US" → the
country code).

**2 · Plan (deterministic).** Plain code turns the Intent into ordered
steps: which entity to fetch, which filters to apply, which joins to
follow. The same Intent always yields the same plan.

**3 · Execute (deterministic).** Plain code runs each step by calling
Fusion through MCP tools, applying filters client-side where the pod
requires it. This is the only stage that touches the network.

**4 · Synthesize (LLM).** Phrases the raw results into a readable answer.
A hallucination guard cross-validates every ID in the response against
the executor's source data; an invented ID raises `HallucinationError`.
Output is a Pydantic-typed structured response.

**Output.** A structured, verifiable answer — or an honest refusal if
the prompt falls outside the KG's scope. Refusal is a designed outcome,
not a failure.

---

## 5. What the Knowledge Graph does

The KG is metadata stored in Oracle tables. It is the institutional
knowledge a senior consultant holds in their head, made
machine-readable. It encodes:

- **Entities and fields** — the query targets and their attributes.
- **Edges** — how entities join, including the join keys and their
  asymmetries (SupplierNumber vs SupplierId), and the cross-pillar hop
  (PO → Buyer via BuyerId → PersonId on HCM).
- **Vocabulary** — business terms mapped to canonical Fusion codes.
- **Patterns** — reusable query shapes (e.g. "no child of type C in the
  last N months").
- **Tool bindings** — which MCP tool realizes each filter or traversal.

The LLM never improvises Fusion mechanics. It picks from what the KG
already knows to be true.

---

## 6. With KG vs without KG

**Without (agent / Track A).** The LLM sees a prompt plus a pile of
tools, reasons live, guesses keys, may loop, and fails silently. When
wrong, the failure is not attributable to any one place.

**With (Spire).** The LLM only *interprets* the prompt into a
KG-constrained Intent, and later *phrases* the guarded answer.
Deterministic code does the planning and the Fusion calls in between.
Every failure is attributable to a specific stage — parse, plan,
execute, or synthesize.

---

## 7. Input and output

- **Input:** a natural-language prompt.
- **Pipeline:** parse (LLM, bounded) → plan (code) → execute (Fusion via
  MCP) → synthesize (LLM, guarded).
- **Output:** a structured, verifiable answer — or an honest refusal.

---

## 8. Current scope (what works today)

- Query target: **Supplier** (Invoice/Contract-rooted prompts are
  refused by design).
- Pillars: **FSCM** confirmed end-to-end. **HCM** reachable in principle
  (Buyer via `publicWorkers`), but HCM access on the dev pod is not yet
  granted.
- Live pod: `esll-dev37`.

---

## 9. Extending into HCM — what is needed from you

Spire was originally built from endpoint signatures alone; the edges,
vocabulary, and patterns were derived from them plus a target question.
Adding a new HCM domain (for example, "retrieve paystubs per employee")
follows the same path, and needs three things from the integration
partner:

1. **HCM access on the dev pod.** A 401 was hit on HCM endpoints — the
   existing credentials cover FSCM scope but not HCM. This is a
   credential/scope grant, not a code change.
2. **Endpoint truth for the new domain.** Confirm the real join keys and
   filterable fields — e.g. whether a payslip keys on `PersonId` or
   `PayrollRelationshipId`. These asymmetries are the whole game.
3. **The security model.** Whether cross-employee payslip retrieval is
   reachable via REST at all, or gated to self-service. A couple of real
   target prompts will surface this quickly.

Given those, the KG additions (entities, edges, vocabulary, patterns,
tool bindings) and the matching MCP tools are mechanical to produce.

---

## 10. The line that matters for a reviewer

The bounded-beats-agent claim was not asserted — the agent was built as
a comparison arm, then the bounded design was committed. The LLM is
confined so that every failure is attributable to one stage. That is an
engineering argument, not a marketing one.
