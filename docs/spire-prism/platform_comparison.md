# Platform Comparison: PRISM vs. Spire

## PRISM

### Pros
- **Proven Corpus:** ~2,000 verified SQL queries encode how to ask the right questions against the Fusion schema.
- **Execution Engine:** Takes a written query, sends it to Fusion (via BIP or SQL), and returns results.
- **Fusion Schema Catalog:** Maintains a deep catalog of tables, columns, and meanings to support the corpus.
- **Analytical Power:** Supports complex joins and aggregations (GROUP BY, ORDER BY) required for business reporting.
- **Platform Ready:** Tenant isolation, user roles, and licensing models are already built.

### Cons
- **User Must Know SQL:** The corpus is a library without a librarian. Users arrive with requirements, but PRISM only accepts queries.
- **No Search or Discovery:** There is no way to browse the corpus or match an English requirement to a query.
- **No Intelligence Layer (LLM):** There is no system integrated to translate a prompt (English statement) into a query.
- **LLM is Not a Silver Bullet:** Even if an LLM is added, it is not full-proof until validated and verified across multiple iterations.

---

## Spire

### Pros
- **Natural Language Interface:** Users ask questions in plain English, eliminating the need to know SQL or the Fusion schema.
- **Intelligent Mapping (Knowledge DB):** Uses a deterministic relational Knowledge DB to map an English requirement to the correct entities, joins, and tools — *the step PRISM leaves to the user.*
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