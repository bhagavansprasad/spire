# KG learning session — corrected start (graph structures first)

**Why this version supersedes the earlier one.** The earlier doc put
interview FAQs first. That was wrong for your background. You know
linked lists, BSTs, searching, sorting. The right first move is to
*rebuild Spire's KG as a data structure you can reason about*, then use
the understanding to answer questions. Not the other way round.

**What Oracle 26ai actually offers.** Before anything else, one fact
that changes how you should think about Spire's choice:

- Oracle 26ai has a **native property graph feature**. You can
  `CREATE PROPERTY GRAPH` over existing tables, query it with
  `GRAPH_TABLE (graph MATCH (a)-[e]->(b) COLUMNS (...))`, and run
  PageRank/Bellman-Ford/WCC inside the database via `DBMS_OGA`
  [citation:1][citation:3][citation:5].
- The graph is **a view over relational tables, not a separate store**
  [citation:4][citation:7]. `DROP PROPERTY GRAPH` leaves the tables
  alone. The data is always relational.
- **Spire did not use this feature.** It hand-rolled nine ordinary
  tables and wrote Python to traverse them. That is a design choice,
  and understanding *why* is part of understanding the KG.

So the question you are really studying is: **"How do you implement
graph traversal over plain relational tables, and when is that better
than using the database's own graph feature?"** That is a data-structures
question, not an FAQ question.

---

## The structure-first sequence

Four exercises. Each produces something you can point at.

### Exercise 1 — build the adjacency list by hand (30 min)

Write down, on paper, what Spire's KG is as a data structure. Not the
schema — the *shape*.

- **Nodes:** 22 rows in `kg_entity`. Each has a name and a table.
- **Edges:** 17 rows in `kg_edge`. Each is directed, with a from-field
  and a to-field.
- **Adjacency:** the `kg_edge` table *is* the adjacency list. A row
  `(Supplier, Invoice, SupplierNumber, SupplierNumber)` means "from
  Supplier, follow `SupplierNumber` to reach Invoice."

Now answer, on paper, without looking at code:

1. How do you find all neighbours of `Supplier`?
   (`SELECT to_entity FROM kg_edge WHERE from_entity = 'Supplier'`)
2. How do you find a *path* from `Supplier` to `Buyer`?
   (Two hops: `Supplier → PurchaseOrder → Buyer`. In a generic graph
   you would BFS. In Spire, you would do two SQL joins, or two
   `find_edge` calls.)
3. Why is the graph *directed*? What breaks if you treat it as
   undirected? (Answer: the join field differs by direction —
   `Supplier → Invoice` joins on `SupplierNumber`, but `PurchaseOrder →
   Supplier` does not exist at all. Direction is the join contract.)

That third question is the one an interviewer will push on. Have the
answer ready.

### Exercise 2 — implement a tiny graph in Python (90 min)

Build it, do not read about it. Target: 80 lines.

```python
class Node:
    def __init__(self, name, table):
        self.name = name
        self.table = table

class Edge:
    def __init__(self, from_node, to_node, from_field, to_field):
        self.from_node = from_node
        self.to_node = to_node
        self.from_field = from_field
        self.to_field = to_field

class KG:
    def __init__(self):
        self.nodes = {}
        self.edges = []

    def add_node(self, name, table): ...
    def add_edge(self, from_, to, from_field, to_field): ...
    def neighbours(self, name): ...
    def find_edge(self, from_, to): ...
    def path(self, start, end):
        # BFS over self.edges; return a list of Edge objects
        ...
```

Then:

- Add three Spire rows: `Supplier → Invoice` (SupplierNumber),
  `Supplier → PurchaseOrder` (SupplierId), `PurchaseOrder → Buyer`
  (BuyerId → PersonId).
- Assert `kg.path('Supplier', 'Buyer')` returns the two-edge path.
- Assert `kg.find_edge('Invoice', 'Supplier')` returns `None` (no
  reverse edge).

This exercise is where the KG stops being words. You will *feel* the
difference between "a table with FKs" and "an adjacency list", and you
will see why Spire's `find_edge` is a one-line SQL query rather than a
BFS.

### Exercise 3 — compare with Oracle's native feature (45 min)

Now that you have built the toy graph, read what Oracle's
`CREATE PROPERTY GRAPH` does differently. The points to notice:

- Oracle's version lets you query a *pattern*, not a single edge:
  `MATCH (a)-[e]->{1,3}(b)` means "one to three hops" [citation:4].
  Spire's version has no concept of variable-length paths — every
  traversal is a fixed one-hop edge lookup.
- Oracle's version can run PageRank over the graph in-database
  [citation:5]. Spire's KG has no algorithms at all — the only
  "algorithm" is "follow one edge to a tool".
- Oracle's version is declarative: you write `MATCH`, the database
  decides how to execute it. Spire's version is imperative: the planner
  walks the filters in order and appends steps.

The comparison is the interview answer. **Spire's KG is a routing table
with graph semantics; Oracle's native feature is a queryable graph
engine.** Spire chose the former because its traversals are fixed
(three or four plan shapes) and its "graph" has 17 edges. Oracle's
feature would be the choice if the traversals became ad-hoc.

### Exercise 4 — the failure-mode table (30 min)

The question "what breaks if a row is wrong" is a data-structures
question, not a project question. Fill this in yourself, from what you
have read:

| Table | Wrong row means | Fails loud or quiet? |
|---|---|---|
| `kg_entity` | | |
| `kg_entity_field` | | |
| `kg_edge` (join field) | | |
| `kg_vocabulary` (canonical value) | | |

The correct answers are: entity → planner cannot find a fetcher → loud;
field → column reported unavailable that is actually available → quiet;
edge join field → executor sends wrong arg → loud but cause is two
layers away; vocabulary → term resolves to a value the pod does not
store → silent empty result. The "loud vs quiet" column is the one
worth memorising, because it is the one with real engineering content.

---

## What to share with the new window

Same as before, but with one addition:

1. **`graph_kg` bundle** — the schema, the loader, the planner's
   `find_edge` / `find_entity_tool`, the seed script.
2. **`parser_planner` bundle** — needed at Exercise 2's end, to trace
   one real prompt's KG reads.
3. **Oracle's property-graph docs** — the two most useful pages are
   `Key Property Graph Features in Oracle AI Database 26ai`
   (https://docs.oracle.com/en/database/oracle/property-graph/26.3/spgdg/key-property-graph-features-oracle-ai-database-26ai.html)
   and the Oracle Base walkthrough
   (https://oracle-base.com/articles/23/sql-property-graphs-and-sql-pgq-23).
   Both are short; read them at Exercise 3, not before.
4. **`WORKING_STYLE.md`** — Rules 2 and 15.1 still apply.

**Do not paste:** the endpoints reference, the synthesizer, the MCP
server tools. They are not the data structure.

---

## The one interview answer this builds

After the four exercises, you can say:

> "Spire's KG is an adjacency list implemented as a relational table.
> `kg_entity` is the node table, `kg_edge` is the edge table with
> directional join fields. The planner does one-hop lookups — `SELECT
> to_entity, to_field FROM kg_edge WHERE from_entity = ? AND to_entity
> = ?` — rather than BFS, because every plan shape is a fixed chain of
> two or three known hops. Oracle 26ai has a native property-graph
> feature that would let us write `MATCH (a)-[]->{1,3}(b)` and run
> PageRank in-database, but with 17 edges and fixed traversals, the
> adjacency-list-as-table is simpler and has fewer moving parts. The
> trade-off is explicit: we give up arbitrary-depth traversal and
> in-database graph algorithms in exchange for not needing a second
> query engine."

That answer is true, it names the Oracle feature, it explains the
trade-off, and every clause of it comes from an exercise you did
yourself. It is not a rehearsed FAQ.

---

*End of corrected start doc.*