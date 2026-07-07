# Spire — Context Handoff

For a new chat window. Captures where Spire stands after the KG-expansion
work, so the next session can continue without re-deriving everything.

---

## What Spire is

An AI-native query system for Oracle Fusion Cloud procurement. It turns a
natural-language prompt into a structured answer against live Fusion REST
endpoints. Described as "SQL Connect without UI."

Core principle: the planner is driven by a Knowledge Graph, not by LLM
judgment. Tool selection is a deterministic KG lookup, which avoids
hallucination and misrouting as the tool catalogue grows. Pipeline is
parse -> plan -> execute -> synthesize ("Design 3"). Not an agent.

Repo: `github.com/bhagavansprasad/spire`. Working dir `~/pocs/spire`.

---

## Pipeline and key files

- `scripts/run_graph.py` — single-prompt entry point.
- `scripts/run_prompt_set.py` — routes a fixed prompt set through the graph.
- `src/spire/graph/pipeline.py` — the LangGraph pipeline (parse, plan,
  execute, synthesize nodes).
- `src/spire/nl_parser/` — parser.py (prompt building), draft.py
  (DraftIntent + to_intent), vocabulary.py (load_kg_menu).
- `src/spire/planner/planner.py` — Intent dataclass, KG lookups, plan
  generation. Filter definitions load lazily from the KG.
- `src/spire/mcp_server/` — server.py (tool registrations) and
  tools/ (search_suppliers, search_invoices, search_addresses,
  search_purchase_orders, buyer, aggregate_invoices).
- `src/spire/synthesizer/synthesizer.py` — per-entity Pydantic response
  shapes, id-hallucination validation.
- `scripts/sql/kg_schema.sql` — the full KG, rebuilt from scratch.
- `scripts/rebuild_kg.py` / `print_kg.py` — rebuild and inspect the KG.
- `kg_expansion_phases.md` — phase tracker (all nine phases done).
- `spire_sme_followup_plan.md` — plan for the remaining SME items.

---

## The KG (9 tables)

kg_entity, kg_entity_field, kg_edge, kg_pattern, kg_vocabulary,
kg_pattern_binding, kg_entity_tool, kg_edge_tool, and kg_entity_filter.

`kg_entity_filter` (added during expansion) holds every filter
definition — mechanism (entity_level / edge_traversal), the tool arg
names (including tool_arg_name_hi for range filters), vocab kind,
query_style (server_q / client_side), filter_field, filter_op, and the
edge-traversal target. The planner reads all filters from this table; no
filter is hardcoded.

Current counts: 5 entities, 27 fields, 4 edges, 3 patterns, 44 vocab,
3 pattern bindings, 3 entity_tool, 11 entity_filter, 3 edge_tool.

---

## What works today

Queryable target entities: Supplier, Invoice, Address.

Supplier filters (all combinable): country, status (ACTIVE/INACTIVE),
name fragment, created-date range, plus edge filters has_open_PO and
has_no_recent_invoices.

Invoice: rooted by supplier (number or name; required), filtered by
amount range and date range.

Address: rooted by supplier or country (one required); flattened from
supplier.addresses[] via expand.

Aggregation: supplier spend ranking (top-N, date window).

Column projection: when a prompt names columns, the raw output is trimmed
to those fields, across all entities. The LLM picks exact column names
from a per-entity list the menu reads from kg_entity_field. Synthesized
prose and id-validation use full records.

---

## Key facts and quirks (verified on the pod)

- Composite `q=` fails on this pod. Send the most selective single clause
  server-side; filter the rest client-side.
- Country lives on the address child, not the supplier — needs
  expand=addresses, matched client-side.
- Server-side `q=` on Supplier.Status is unreliable; status is matched
  client-side.
- Supplier "inactive" is Status='INACTIVE', not InactiveDate-based.
- Invoice joins supplier by SupplierNumber (string); PO by SupplierId
  (numeric); Buyer by PersonId = PO.BuyerId. Same supplier, three ids.
- No FSCM /buyers endpoint; buyers are HCM publicWorkers.
- resolve_vocab is case-insensitive on the term.
- Aggregate invoices page size is 500.
- Credentials: env prefix `IKS_` (IKS_FUSION_BASE_URL / _USERNAME /
  _PASSWORD), set in .bashrc; the test path reads personas.yaml. Pod
  password rotates weekly; test instance.

---

## Working style (important)

- Short paragraphs, short sentences. No widgets when offering choices.
  Options as plain text, kept interactive. Concise. Ask permission before
  generating files or significant content. Be interactive.
- Git: one branch per logical change -> PR -> merge to master; never
  commit directly to master (a few slips happened, but that's the rule);
  `git commit -F- <<'EOF'` heredoc for messages; add files by name, not -A.
- Phases: build one piece, verify against the live pod, run the full
  suite, then commit. Update the tracker only after a phase is merged.
- KG is authored metadata, rebuilt from scratch — never incrementally
  inserted. Don't over-generalise; handle the concrete case, generalise
  when a second case demands it.
- New endpoints follow the onboarding process: share endpoints + prompts
  -> Claude suggests curls -> run and share JSON -> build KG rows together
  -> output SQL for the rebuild. Data discovery precedes KG authoring.

---

## Test / verification loop

- Full suite: `pytest` (currently 317 passed, 0 skipped).
- Live behaviour: `python scripts/run_prompt_set.py` (server up, pod
  reachable, Gemini). The set covers aggregation, supplier filters,
  invoice filters, an address prompt, a projection prompt, and a refusal.
- Counts: `python scripts/print_kg.py --counts-only`.

---

## What's next

The remaining SME comments are planned in `spire_sme_followup_plan.md`.
Six phases, quick wins first:

A. Business relationship filter (small, mirrors status).
B. Nested addresses on a supplier query — "suppliers with their
   addresses" (medium; closes Test 3/5).
C. Supplier count / simple aggregation (medium).
D. Suppliers filtered by invoice amount — cross-entity value filter
   (medium-large).
E. Supplier sites endpoint (large; needs curl discovery first).
F. Business classifications endpoint (large; needs curl discovery first).

Also open from earlier sessions: credential rotation (live passwords in
old git history), deleting the now-dead suppliers_by_country.py,
expanding Address fields (City/State) in the KG, and an SME validation
session with Venu before widening endpoint scope.
