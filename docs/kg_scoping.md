# Knowledge Graph POC — Scoping & Alignment

## Context

We're scoping a POC to evaluate Oracle 26ai's Knowledge Graph (PGQ) for an agent that queries Oracle Fusion via REST. Before building, we want to align on what KG can and cannot do given our inputs.

## Hard constraints (already established)

1. **Source of truth is Oracle Fusion REST.** The 26ai database never caches, copies, or syncs Fusion data.
2. **The KG holds metadata only** — entity types, edge declarations, query patterns, vocabulary. Never instance data.
3. **Fusion data is fetched only via REST tool calls at query time;** results are used and discarded.

## What we're trying to understand: what KG can do better than an LLM-only approach

For an agent that answers questions by calling Oracle Fusion REST, we want to identify where a metadata-only KG genuinely adds value over an LLM that has the endpoint catalog in its context. Candidate areas include:

1. **Deterministic multi-hop plan synthesis** — given a question requiring several REST calls with ID handoffs, PGQ can traverse the metadata graph and emit an ordered, executable plan. Same question, same plan, every time. No hallucinated endpoints, no wrong join order.
2. **Feasibility checking before execution** — PGQ can determine upfront whether a question is answerable with the available endpoints, and fail fast with a precise reason if not.
3. **Vocabulary grounding and disambiguation** — mapping user terms ("vendor," "bill") to canonical entities, and disambiguating overloaded terms based on context edges.
4. **Query pattern reuse** — common question shapes become named patterns in the graph; PGQ matches the question to a pattern and emits a proven plan instead of re-deriving it.
5. **Explainability and auditability** — every plan is traceable to graph edges, giving a real audit trail rather than an LLM chain-of-thought.
6. **Cost and latency optimization** — when multiple traversal paths exist, PGQ can prefer cheaper ones based on endpoint cost characteristics encoded in the graph.
7. **Schema evolution containment** — Fusion endpoint changes are updated once in the KG; every plan touching affected nodes picks up the new contract.

## What we have

- **(a)** Oracle 26ai with Knowledge Graph
- **(b)** Oracle Fusion REST endpoint signatures
- **(c)** Oracle Fusion table schemas (publicly available)

## Our current understanding — please confirm or correct

1. A KG is useful when built from tables, schemas, and their relationships (e.g., Oracle Fusion HCM or Finance modules).
2. A KG may not be useful if built from **only REST endpoint signatures**, without the underlying Fusion tables and their schema.

## Questions

- **Q1.** With only (a) and (b), can we build a KG?
- **Q2.** To build a KG, is having (a) and (c) mandatory?