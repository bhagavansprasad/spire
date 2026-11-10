# Platform Comparison: PRISM vs. Spire

## PRISM (Target Audience: Fusion Developers)

### Pros
- **Unified Developer Workspace:** Collapses multiple disconnected Fusion screens (querying, data model creation, reporting) into a single environment.
- **Accelerated Iteration:** Lets developers write, test, and validate SQL queries in one place before exporting them to create the Fusion Data Model.
- **Frictionless Publishing:** Automates the creation of the Data Model and the Report, removing the need to manually click through Fusion setup screens.
- **Complex Query Power:** Supports the full analytical power of SQL, including complex joins and aggregations, giving developers complete control.
- **Built-in Schema Catalog:** Maintains a deep catalog of Fusion tables and columns so developers don't have to guess the underlying schema.

### Cons
- **The "Discovery" Problem (No Semantic Search):** The ~2,000 query corpus is a flat document with no semantic search. If a developer gets a new business request, there is no way to ask the system, "Which of these 2,000 queries do I start with?" They cannot easily find the 5-10 variant queries needed to build a new one.
- **Requires SQL Expertise:** As a developer tool, it requires the user to understand SQL and the Fusion schema. It is not a natural-language tool for business users.
- **Manual Requirement Mapping:** The developer must translate the business user's English requirement into the SQL query manually; PRISM does not generate the initial query from a prompt.
- **Validation is Manual:** The developer must test the query and validate the data output themselves. The system does not automatically guarantee the data is "correct."

---

## Spire (Target Audience: Business Users / SMEs / Fusion Developers)

### Pros
- **Natural Language Interface:** Users ask questions in plain English, eliminating the need to know SQL or the Fusion schema.
- **Intelligent Mapping (Knowledge DB):** Uses a deterministic relational Knowledge DB to map an English requirement to the correct entities, joins, and tools — *the step PRISM leaves to the developer.*
- **Association & Context:** Maintains the association between the user's intent, the SQL generated, and the data fetched, providing a continuous context across the pipeline.
- **Deterministic Execution:** The planner and executor run without an LLM, ensuring predictable and auditable data fetching.
- **Built-in SQL Overlay:** Generates equivalent, executable SQL alongside the data, providing total transparency on how the answer was derived.

### Cons
- **Bounded Tool Surface:** It can only answer questions for which an MCP tool (and SQL overlay) has been explicitly mapped and built.
- **Missing Edge Cases:** Complex analytical queries (like multi-table comparisons or whole-collection scans) often fall outside its current tool set.
- **Requires Heavy Maintenance:** Adding a new capability requires code changes across the parser, planner, tools, and SQL overlay.
- **Performance Limits:** Relies on paginated REST calls; queries spanning tens of thousands of rows can take minutes and time out.
- **No Corpus Fallback:** Unlike PRISM, Spire cannot fall back on a massive library of pre-written queries if its hardcoded logic misses an edge case.

---

## Spire: Features to Implement (SME Feedback)

- **Performance Optimization:** End-to-end response time is too slow for interactive use; it must be reduced significantly.[^1]
- **Conversational Context:** Support follow-up questions where the user builds on a previous result, rather than treating each prompt in isolation.
- **Schema Change Resilience:** Minimize the manual impact when the backend SQL schema changes.
- **Broader Column Support:** Handle arbitrary columns and combinations an SME might ask for, beyond what is currently mapped.
- **Complex Query Proof:** Demonstrate that Spire can support the complex, multi-table analytical queries that PRISM's corpus already covers.

---

### Notes

[^1]: **Architectural Context (Performance Optimization)**
    
    **The Current Bottleneck:** The Fusion REST API is the single most time-consuming step in the Spire pipeline. It dominates execution time. There is huge scope for improvements.

    **The Available Paths:** Because Spire already generates equivalent SQL via the SQL Overlay, it has two available ways to fetch data:
    1. **REST APIs** (Current) — Handled by the MCP tool surface.
    2. **SQL Execution** (Fast Path) — The generated SQL is executed directly against Fusion.