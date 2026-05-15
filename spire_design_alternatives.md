# Spire — Design Alternatives & Comparison

**Purpose:** This document captures the architectural designs that have been considered for Spire's agent layer. Each design is described in its own terms, with an honest assessment of its strengths and limitations. The goal is to support side-by-side comparison — for the SME, for the engineering team, and for the decision-maker.

**Companion document:** `spire_poc_master_plan.md` covers the POC plan that tests selected designs against a representative prompt.

---

## Table of Contents

1. [Comparison Reference Prompt](#1-comparison-reference-prompt)
2. [Design 1 — LLM + Tools (Single Pass)](#2-design-1--llm--tools-single-pass)
3. [Design 2 — LLM + Reference Query Library + Validation + Tool](#3-design-2--llm--reference-query-library--validation--tool)
4. [Design 3 — Direct Tool Orchestration (Agent Loop)](#4-design-3--direct-tool-orchestration-agent-loop)
5. [Design 4 — Graph-Guided Orchestration](#5-design-4--graph-guided-orchestration)
6. [Design 5 — Dynamic Orchestration](#6-design-5--dynamic-orchestration)
7. [Side-by-Side Comparison](#7-side-by-side-comparison)
8. [Natural Evolution Path](#8-natural-evolution-path)
9. [Recommendation Framework](#9-recommendation-framework)

---

## 1. Comparison Reference Prompt

All designs in this document are evaluated against the same representative prompt:

> *Show me suppliers in US with no invoices in 6 months but with open purchase orders, including the buyer assigned to each.*

This prompt is realistic enough that a CFO or procurement lead might actually ask it. It deliberately stresses:

- Multiple entities (Supplier, Invoice, PurchaseOrder, Buyer, Address, Country)
- Negation logic (no invoices in 6 months)
- Status semantics (open POs)
- Multi-hop relationships (Supplier → PO → Buyer)
- Organizational scoping (US, resolved via address)

When each design's strengths and weaknesses are discussed below, this prompt is the lens.

---

## 2. Design 1 — LLM + Tools (Single Pass)

**Origin:** The original mental model you sketched when questioning whether embeddings are needed.

### Architecture

```
User
  ↓
Prompt + Tools (in LLM context)
  ↓
LLM
  ↓
Invoke Tool(s) via MCP
  ↓
Tool(s) → Fusion REST Endpoint
  ↓
Response
  ↓
User
```

### Key characteristics

- LLM is given the prompt and the available tools in one context
- LLM picks tools and parameters based on tool descriptions alone
- MCP serves as the protocol between LLM and tools
- Tools call Fusion REST endpoints
- **Single pass** — the LLM produces tool calls; results return; LLM composes the answer; done
- No knowledge graph, no embeddings, no reference query library

### Pros

- **Simplest architecture that actually works.** Tools provide the execution layer that bare-LLM lacks. MCP provides a clean protocol.
- **Fast to build.** Once tools are wrapped, the LLM does the heavy lifting.
- **Easy to explain to stakeholders.** The flow is linear and intuitive.
- **Tool descriptions are a real knowledge surface.** A well-written docstring on a tool ("Search Oracle Fusion suppliers; status='ACTIVE' means END_DATE_ACTIVE IS NULL") encodes meaningful Fusion knowledge.
- **Endpoint-based access is built in.** No need to reinvent how SQL gets to Fusion — REST endpoints are the native interface.
- **Naturally auditable.** Every tool call is a logged event.

### Cons

- **No retry on failure.** If a tool returns an error, the LLM doesn't get a second chance to fix its approach. The single pass is over.
- **Limited multi-step reasoning.** For multi-hop problems (like the reference prompt), the LLM has to produce *all* tool calls in one shot. Some LLMs handle parallel/sequential tool calls in a single response, but complex orchestration suffers.
- **No place for non-tool knowledge.** If you discover that "open PO" in your customer's pod uses an unusual status combination, there's no clean place to encode this except in the tool's docstring — which means updating tools constantly.
- **Tool catalog scales poorly.** As more endpoints are added, all tool descriptions sit in the LLM's context. At a few dozen tools, the context bloats and tool-selection accuracy drops.
- **No compounding improvement.** The system doesn't learn from past successful queries. Every prompt is a fresh start.
- **No per-tenant customization layer.** Customer-specific DFF meanings, custom value sets, and tenant-specific business rules have no home.

### When this design is sufficient

- Tool catalog is small (5–15 tools) and stable
- Questions are mostly single-step or two-step
- Customers have minimal Fusion customizations
- You're building a focused product for a narrow use case, not a general assistant

### When this design breaks down

- Multi-step reasoning is needed (the reference prompt is right at the edge)
- The tool catalog needs to grow toward "all of Fusion"
- Different customers need different behaviors
- Error recovery matters

---

## 3. Design 2 — LLM + Reference Query Library + Validation + Tool

**Origin:** The SME's design — a more thoughtful version of "LLM generates the query, tool executes it."

### Architecture

```
1. User prompt
       ↓
2. LLM #1: generate query from prompt
       ↓
3. LLM #2: validate query against locally-stored reference queries
   (syntactic check only — no execution)
       ↓
4. Validated query
       ↓
5. Tool: execute the validated query
       ↓
6. Data returned to user
```

### Key characteristics

- LLM generates a query (typically SQL, but could be other formats)
- A second LLM pass validates the query, with reference queries injected as context
- Validation is **syntactic** — checking the query "looks right" — not by executing it
- Tool's role is narrow: just execution
- Reference query library is the knowledge source; sits as a static file or local store
- Single pass through the system (no agent loop, but two LLM calls in sequence)

### Pros

- **Conceptually simple.** Easy to explain: write query, check query, run query.
- **Reference query library is a real asset.** A curated set of "queries we know work" carries genuine production value. The same idea underlies few-shot RAG patterns used widely in industry.
- **Validation catches the most obvious LLM hallucinations.** If the validator LLM sees real reference queries, it can flag "you invented a column that doesn't exist in our reference queries."
- **Modest infrastructure.** No graph database, no vector store, no agent framework.
- **Familiar to anyone who's worked with text-to-SQL systems.** Many open-source projects use this pattern.
- **The reference library is human-readable.** Subject-matter experts can author, review, and curate queries directly — they don't need to learn a graph query language.

### Cons

- **Reference retrieval is the hidden problem.** Step 3 says "validated against valid queries." But *which* references? Sending all of them every time fails as the library grows. Keyword matching is brittle ("vendors" ≠ "suppliers"). The only scalable solution is embedding-based retrieval — which the design implicitly avoids.
- **Syntactic validation is weak.** `SELECT * FROM POZ_SUPPLIERS WHERE COUNTRY_CODE = 'US'` is syntactically correct. It also fails because `COUNTRY_CODE` isn't on `POZ_SUPPLIERS` (it's on the child address resource). Syntactic checks miss semantic errors.
- **SQL-shaped blind spot.** The architecture assumes the answer is a query (typically SQL). But many Fusion questions are best answered by REST endpoint calls, not SQL. The design has no place for endpoint-vs-SQL routing.
- **No multi-step reasoning.** The reference prompt requires roughly 5 steps. A single generated query would have to be one massive SQL statement — which Fusion's BIP guardrails would likely reject for size or timeout.
- **No error recovery path.** If the executed query fails, what happens? Returning the error to the user feels wrong; sending back to the LLM for retry would require an agent loop (which contradicts the single-pass design).
- **No per-tenant customization layer.** Global reference library means same behavior for all customers. Per-tenant libraries quickly become a maintenance burden.
- **Reference library is a KG in disguise.** A well-curated query library implicitly encodes the same patterns and traversals a KG makes explicit. The KG version is queryable and compositional; the library version is implicit and copy-paste.

### When this design is sufficient

- Question patterns are bounded and well-known (perhaps 30–50 common queries cover 90% of usage)
- Single-tenant or very homogeneous customer base
- SQL-based access is acceptable (BIP-as-SQL-engine works for the queries in scope)
- Errors are tolerable to surface raw to users

### When this design breaks down

- Reference library grows past what fits in context (forcing embedding retrieval)
- Customer customizations need accommodation
- Multi-step orchestration is required
- The product needs error recovery and graceful degradation

### A note on its honest position

This is not a naive design. It is a real architecture, used in production text-to-SQL systems. The SME's instinct toward this design reflects sound engineering caution — *start simple, don't over-build*. The question for Spire isn't whether this design is wrong; it's whether Spire's product goals exceed what this design can sustain. The natural evolution of this design under production pressures converges with Designs 3, 4, and 5.

---

## 4. Design 3 — Direct Tool Orchestration (Agent Loop)

**Origin:** Spire's "Version A" in the POC master plan — the baseline against which Graph-Guided Orchestration is measured.

### Architecture

```
User
  ↓
LLM with tools in context (system prompt)
  ↓
LangGraph agent loop:
   • LLM produces tool calls or final answer
   • If tool calls → tool executor runs them
   • Results return to LLM
   • LLM decides: call more tools or finalize
   • Loop until final answer
  ↓
MCP Client → MCP Server (FastMCP)
  ↓
Tools (one per Fusion resource family)
  ↓
Oracle Fusion REST Endpoints
  ↓
Results flow back up
  ↓
LLM composes natural-language answer
  ↓
User
```

### Key characteristics

- Same execution layer as Design 1 (MCP tools, Fusion REST endpoints)
- **Critical addition: an agent loop.** The LLM is invoked iteratively, not once.
- Each iteration: LLM sees the prompt, the tool descriptions, and the history of tool calls made so far. It decides what to call next, or whether to finalize.
- Multi-step reasoning is native — the LLM can plan, execute, observe, replan.
- Tool descriptions are still the only knowledge surface — no KG, no embeddings, no reference library.

### Pros

- **Multi-step reasoning works natively.** The agent loop handles "find X, then for each, look up Y" patterns without contortion.
- **Error recovery is built in.** If a tool call fails, the LLM sees the error in the next iteration and can adapt — pick a different tool, change parameters, ask the user for clarification.
- **Tool descriptions accumulate signal across calls.** As the agent makes tool calls, the context grows with real evidence of what works; subsequent tool selection improves.
- **Standard, well-supported architecture.** This is the agent pattern that Cursor, Devin, and most production AI tools use. Plenty of infrastructure exists.
- **Naturally auditable.** Every loop iteration, every tool call, every result is a traceable step. Excellent for enterprise compliance.
- **Endpoint-aware.** Tools are explicit about which endpoint they call. The agent picks tools based on what they do, not based on what SQL would do.
- **Honest baseline.** This is what a "good agent with good tools" looks like, with no extra magic. Tests whether anything more is needed.

### Cons

- **Still no formal knowledge representation.** All Fusion knowledge lives in tool docstrings. As the catalog grows, docstrings become a maintenance burden and a knowledge silo.
- **Tool selection accuracy degrades with catalog size.** With 5 tools, the LLM picks well. With 50, accuracy drops noticeably. With 500, it's unreliable.
- **No place for query patterns.** Common reasoning patterns ("no Y in N months", "find canonical entity for term X") have to be re-derived by the LLM each time. No reuse.
- **No place for per-tenant knowledge.** Same limitation as Design 1.
- **Compounding improvement is limited.** Without a structured place to store "what worked last time," the agent doesn't get smarter with use.
- **Higher infrastructure cost than Designs 1 and 2.** Agent framework (LangGraph), MCP infrastructure, trace logging — more moving parts.
- **Loop iterations cost tokens.** Each loop iteration is another LLM call. For complex prompts, this adds up.

### When this design is sufficient

- Tool catalog is moderate (5–30 tools) and growing slowly
- Multi-step reasoning is needed but patterns are recurring (the LLM can re-derive them per call without serious accuracy loss)
- Single-tenant or homogeneous customer base
- The team prefers operational simplicity over compounding intelligence

### When this design breaks down

- Tool catalog needs to scale toward "all of Fusion" (forces dynamic tool retrieval — Design 5)
- Customer customizations need accommodation (forces structured knowledge — Design 4)
- Common patterns are wasted re-derivation effort (forces patterns library — Design 4)
- Production trust requires verifiable, explainable reasoning (KG provides citation-able sources)

---

## 5. Design 4 — Graph-Guided Orchestration

**Origin:** Spire's "Version B" in the POC master plan — the design that tests whether structured knowledge meaningfully outperforms tool descriptions alone.

### Architecture

```
User
  ↓
LLM with KG tools + Fusion tools in context
  ↓
LangGraph agent loop:
   1. Agent consults KG tools:
      • "What's canonical for X?"
      • "How does X relate to Y?"
      • "What pattern handles 'no Y in N months'?"
      • "What does 'open PO' mean?"
   2. Agent plans tool calls based on KG guidance
   3. Agent calls Fusion tools (same tools as Design 3)
   4. Loop continues until final answer
  ↓
Fusion REST Endpoints (unchanged)
  ↓
Results back; LLM composes answer with KG context
  ↓
User
```

### What's in the Knowledge Graph

Stored in Oracle 26ai as a SQL Property Graph plus supporting relational tables:

- **Entities** — canonical Fusion entities (Supplier, Invoice, PurchaseOrder, Buyer, Address, Country) with their canonical tables, endpoints, and identifiers
- **Relationships** — typed edges between entities with join semantics and endpoint traversal hints
- **Query patterns** — reusable logical patterns ("no Y in N months", "open PO status filter", "country lookup via address child")
- **Lookups** — explicit business-term-to-Oracle-code mappings ("US" → 'US', "open PO" → composite status condition)

### Key characteristics

- Same Fusion execution layer as Designs 1 and 3 (MCP tools, REST endpoints)
- Same agent loop as Design 3
- **Critical addition: a Knowledge Graph that the agent consults via dedicated tools**
- The KG holds structured knowledge that doesn't fit cleanly in tool docstrings
- Per-tenant overlays are possible (customer-specific DFFs, custom value sets) — though not exercised in the POC

### Pros

- **Solves the precise traversal problem.** When the agent needs to know "how do I get from Supplier to Buyer?" the KG returns a precise answer (Supplier → PO → Buyer, with the join keys). Tool descriptions can't carry this kind of structured relationship knowledge cleanly.
- **Patterns are reusable.** "No Y in N months" is encoded once in the KG and used for invoices, payments, orders, anything. The LLM doesn't re-derive it every time.
- **Per-tenant customization has a home.** Customer-specific DFF meanings, custom value sets, custom business rules — all live in the KG as tenant-scoped data.
- **Negation and complex logic improve dramatically.** The hardest LLM failure modes (NOT EXISTS patterns, multi-hop joins) become tractable when the KG provides the structural template.
- **Explainable.** The agent can cite the KG: "I joined Supplier to PO via VENDOR_ID because the KG defines this as the canonical relationship." Consultants trust output they can verify.
- **Compounding improvement is natural.** Every correction, every successful pattern, every tenant overlay enriches the KG. The product gets smarter in a structured way.
- **Cross-agent knowledge sharing.** Future agents (BIP Agent, OIC Agent, FBDI Agent) all use the same KG. Knowledge encoded once is reused everywhere.
- **Reduces LLM cognitive load.** The LLM does less reasoning from scratch because the KG provides structured priors. Fewer mistakes, faster responses, lower token cost per query.

### Cons

- **Significant upfront investment.** Designing the KG model, populating it, and maintaining it requires ongoing curation effort. The "right" graph for Fusion is a project, not a feature.
- **Cold-start problem.** An empty KG provides zero value; the value compounds as content is added. Early in the product's life, the KG underperforms its potential.
- **New operational surface.** Another database to design schema for, version, backup, and monitor (mitigated significantly by using Oracle 26ai, which holds the graph alongside relational data).
- **Agent integration is non-trivial.** Getting the LLM to consult the KG appropriately (and not over-consult, not under-consult) requires careful prompt design and iteration.
- **Risk of over-engineering.** It's easy to keep modeling more entities and patterns than the product actually uses. Discipline is required.
- **KG can become a bottleneck if poorly maintained.** A stale or incorrect KG actively misleads the agent. The KG is only as good as its curation.

### When this design is sufficient

- The product is targeting real-world Fusion work (not toy questions)
- Common patterns recur across customers and use cases
- Per-tenant customization is a known requirement
- Explainability and trust are valued
- The team is willing to invest in knowledge curation as an ongoing discipline

### When this design breaks down (or is overkill)

- The use case is genuinely narrow (a few question types, a few tools)
- Per-tenant variation doesn't exist
- The team can't sustain ongoing KG curation
- Time-to-first-demo dominates other concerns

---

## 6. Design 5 — Dynamic Orchestration

**Origin:** Spire's "Version C" in the master plan — the production-target architecture, addressing the SME's stated requirement that the system handle new endpoints dynamically at runtime.

### Architecture

```
User
  ↓
Pre-LLM step:
   • Embed user prompt
   • Vector search over endpoint/tool catalog
   • Retrieve top-N most relevant tools (e.g., N=15–20)
  ↓
LLM with:
   • KG tools (always available)
   • Top-N Fusion tools (dynamically selected)
  ↓
LangGraph agent loop (same as Graph-Guided Orchestration):
   1. Consult KG
   2. Plan tool calls
   3. Execute Fusion tools
   4. Loop until final answer
  ↓
Fusion REST Endpoints (unchanged)
  ↓
Results back; LLM composes answer
  ↓
User
```

### What's added on top of Design 4

- **Embedding-based tool retrieval.** The full catalog of Fusion endpoints/tools is embedded and stored in Oracle 26ai's VECTOR data type. For each user prompt, only the most relevant tools enter the LLM's context.
- **Endpoints can be added at runtime.** Adding a new endpoint means adding a new embedded record — no code changes, no redeploys, no LLM retraining.
- **Pattern matching upgraded to embeddings.** Design 4's `find_pattern` tool (which uses substring matching) becomes an embedding-based similarity match in Design 5, handling paraphrases gracefully.
- **Past successful queries can be embedded** for few-shot retrieval — adding compounding improvement at the prompt-similarity level.

### Pros

- **Scales to thousands of endpoints.** Fusion has thousands of REST endpoints across modules; only the relevant 15–20 surface to the LLM per query.
- **Dynamic endpoint addition.** Directly answers the SME's stated requirement — new endpoints don't require code changes.
- **Better pattern matching.** Embeddings handle synonymy and paraphrase that substring matching misses.
- **Compounding intelligence at the retrieval layer.** Past successful queries become future few-shot examples.
- **Same operational footprint as Design 4 thanks to Oracle 26ai.** The vector store is the same database — no new infrastructure.
- **Production-realistic.** This is the architecture for a deployed multi-tenant Spire.

### Cons

- **Most complex of all five designs.** Vector store, retrieval logic, embedding refresh pipelines, retrieval quality monitoring all add up.
- **Retrieval quality is a new failure mode.** If the embedding model misses the right tool, the LLM never sees it. Garbage retrieval → garbage agent.
- **Cold start is more severe.** Both the KG and the embedded tool catalog need to be populated for the design to perform.
- **Embedding model choice matters significantly.** Different models produce different retrieval quality. Choosing wrong is expensive to migrate from later.
- **Hardest to demo.** Live demos of dynamic retrieval are less visceral than KG demos because the retrieval happens silently.
- **Per-tenant isolation in the vector store** is non-trivial — tenant A's tool catalog should not surface tools from tenant B's customizations.

### When this design is sufficient

- The product must scale to "all of Fusion" (or a major subset)
- Customers want to add custom endpoints/tools without engineering involvement
- Multi-tenant deployment is in scope
- Production-grade operations are feasible

### When this design is overkill

- POC stage with bounded tool catalog
- Single-customer or single-pod deployment
- Tool catalog is small and stable
- Time-to-first-demo dominates

### Strategic note

Dynamic Orchestration is intentionally *not* part of the POC. The POC validates whether the KG investment pays off; Dynamic Orchestration is the natural production destination if the answer is yes. Building it before validating the KG would invert the risk order.

---

## 7. Side-by-Side Comparison

| Capability | Design 1: LLM + Tools (Single Pass) | Design 2: Reference Library + Validation | Design 3: Direct Tool Orchestration | Design 4: Graph-Guided | Design 5: Dynamic |
|---|---|---|---|---|---|
| Tools (execution) | ✅ Yes | ✅ Yes (narrow role) | ✅ Yes | ✅ Yes | ✅ Yes |
| Agent loop (multi-step) | ❌ No | ❌ No | ✅ Yes | ✅ Yes | ✅ Yes |
| Error recovery | ❌ No | ❌ No | ✅ Built in | ✅ Built in | ✅ Built in |
| Reference query library | ❌ No | ✅ Static file | ⚠️ Could be added | ⚠️ Could be added | ⚠️ Could be added |
| Validation step | ❌ No | ✅ Syntactic only | ⚠️ Implicit via tool errors | ⚠️ Implicit + KG-informed | ⚠️ Implicit + KG-informed |
| Knowledge Graph | ❌ No | ❌ No | ❌ No | ✅ Yes | ✅ Yes |
| Per-tenant customization | ❌ No | ❌ No | ❌ No | ✅ Yes (KG overlays) | ✅ Yes (KG overlays) |
| Embeddings for retrieval | ❌ No | ❌ No | ❌ No | ❌ No | ✅ Yes |
| Tool catalog growth | ❌ Bloats LLM context | ❌ Library bloats validation | ⚠️ Degrades at ~30+ tools | ⚠️ Same as Design 3 | ✅ Scales to thousands |
| Dynamic endpoint addition | ❌ No (redeploy) | ❌ No (redeploy) | ❌ No (redeploy) | ❌ No (redeploy) | ✅ Yes |
| Multi-step reasoning | ❌ Single pass | ❌ Single pass | ✅ Native | ✅ Native | ✅ Native |
| Complex logic (negation, joins) | ⚠️ LLM-derived per call | ⚠️ Library-dependent | ⚠️ LLM-derived per call | ✅ Pattern library | ✅ Pattern library |
| Compounding improvement | ❌ None | ⚠️ Manual library curation | ❌ None | ✅ KG enrichment | ✅ KG + past-query embeddings |
| Auditability | ✅ Tool-level | ⚠️ Tool-level only | ✅ Full trace | ✅ Full trace + KG citations | ✅ Full trace + KG citations |
| Explainability | ⚠️ Tool descriptions | ⚠️ Reference queries | ⚠️ Tool descriptions | ✅ KG-cited reasoning | ✅ KG-cited reasoning |
| Time to first demo | ✅ Fastest | ✅ Fast | ⚠️ Moderate | ⚠️ Slower | ❌ Slowest |
| Production-readiness ceiling | ⚠️ Low | ⚠️ Moderate | ⚠️ Moderate-high | ✅ High | ✅ Highest |
| Operational complexity | ✅ Lowest | ✅ Low | ⚠️ Moderate | ⚠️ Higher | ❌ Highest |

Legend: ✅ Strong, ⚠️ Conditional/partial, ❌ Absent or weak

---

## 8. Natural Evolution Path

A useful framing: each design naturally evolves toward the next under real production pressures.

**From Design 1 to Design 3 (single pass → agent loop):** Pressure: errors happen, multi-step problems exist. Response: add a loop so the LLM can retry and chain steps. Result: Design 3.

**From Design 2 to Design 3 (reference library → agent loop):** Pressure: how do you handle queries that the reference library doesn't cover, or that need multiple steps? Response: let the LLM iterate, generate multiple queries, refine on failure. Result: an agent loop. Result: Design 3.

**From Design 3 to Design 4 (tools alone → tools + KG):** Pressure: tool descriptions can't carry all the structured knowledge consultants need (relationships, patterns, lookups, tenant overlays). Response: extract that knowledge into a queryable graph. Result: Design 4.

**From Design 4 to Design 5 (fixed tool catalog → dynamic retrieval):** Pressure: the tool catalog needs to grow toward "all of Fusion" without bloating LLM context. Response: embed tools and retrieve only relevant ones per prompt. Result: Design 5.

**Key insight:** No design is "wrong." Each is the right answer for a particular set of constraints. The question is which constraints apply to Spire.

---

## 9. Recommendation Framework

Rather than declaring one design the winner, here are the questions whose answers determine the right choice:

### Question 1: How large will the tool/endpoint catalog become?

- < 15 tools → Designs 1, 2, 3, or 4 all work
- 15–50 tools → Designs 3 or 4 (agent loop helps; reference library/static context get awkward)
- 50+ tools → Design 5 (dynamic retrieval becomes necessary)

### Question 2: Will questions require multi-step reasoning?

- Mostly single-step → Designs 1 or 2 are sufficient
- Multi-step common → Design 3 or higher

### Question 3: Will customers customize Fusion (DFFs, value sets, custom rules)?

- No → Designs 1, 2, or 3 work
- Yes → Design 4 or 5 (KG provides the customization layer)

### Question 4: Is error recovery and graceful degradation important?

- Errors can be surfaced raw → Designs 1 or 2 work
- Errors should be handled and retried → Design 3 or higher

### Question 5: How important is explainability and audit-grade trust?

- Tool-level logging is enough → any design works
- Citation-able reasoning required for enterprise customers → Design 4 or 5

### Question 6: Is the system meant to improve over time without retraining?

- No → Designs 1, 2, or 3 are fine
- Yes → Design 4 or 5 (KG and embeddings both compound)

### Question 7: How much operational complexity can the team sustain?

- Minimal → Designs 1 or 2
- Moderate → Design 3 or 4
- Full production-grade ops → Design 5

### A practical recommendation for Spire specifically

Based on the conversation so far:

- The SME's stated requirement (dynamic endpoint addition) implies Design 5 is the production destination
- The POC's stated goal (validate the KG investment) implies Design 4 is the critical test
- The build path (incremental, smaller-better-than-larger) implies starting with Design 3 as the baseline, then layering Design 4, then Design 5

This is exactly what the POC master plan proposes. The conversation hasn't surfaced reasons to deviate. The role of this document is to make the alternatives visible — including the SME's Design 2, which the master plan doesn't directly test — and to provide vocabulary for the decision conversation.

If the team wanted to be conservative and test the SME's design first, the master plan could be reframed to include a Design 2 baseline alongside Design 3. This would lengthen the POC but provide more evidence-based decision support. Whether to do so is a product/team decision, not a technical one.

---

## Document End

This is a living document. As the POC progresses, real measurements should be added to the comparison table (replacing qualitative ✅/⚠️/❌ with quantitative data). Updates should be tracked in version control alongside `spire_poc_master_plan.md`.

**Last updated:** Document generation date (see git history)
