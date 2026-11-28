# Adding a Fusion module to Spire — REST-first playbook

**Status:** Reusable method document. Grounded in the code on `master` at
`a1364e4` (2026-11-27). No module has been delivered through it yet, so it
is a *proposed* procedure with verified inputs — not a proven one. Update it
after the first module (AP) finishes, using evidence rather than tidying.

**Companion to:** [`MODULE_SUPPORT_ROADMAP.md`](./MODULE_SUPPORT_ROADMAP.md).

**How the two divide:**

| Document | Owns |
|---|---|
| `MODULE_SUPPORT_ROADMAP.md` | *Why* and *in what order*: portfolio, priority, the eight business gates, open product decisions. |
| This playbook | *How*, in Spire's actual code: which files change, which tool shape to copy, which commands prove it works. |

The roadmap's Gate 4 ("Data and workflow model") and Gate 5 ("Spire design")
are one paragraph each there; this document is what those paragraphs expand
to. Where the two disagree, the roadmap owns intent and this document owns
mechanics — record the conflict rather than silently preferring one.

---

## 0. When to use this document

Use it when Spire must answer questions about a Fusion module it does not
currently serve, or must deepen partial support for one it does.

**Do not use it to:**

- Build the SQL overlay or KG schema corpus. That work has its own reusable
  procedure — [`../SCHEMA_DISCOVERY_METHOD.md`](../SCHEMA_DISCOVERY_METHOD.md)
  — and is deferred here (§8).
- Add a new filter to an existing entity. That is a smaller change; see the
  overlay's `docs/design/sql_overlay/EXTENDING.md` for the SQL side, and §6.5
  here for the planner side.
- Add an aggregation or comparison shape. Those have a one-op-one-tool rule
  (§5.3); a new shape is a new tool, not a module.

**The unit of work is one module, one branch.** Two modules in one branch
cannot be verified independently — the prompt set for module B passes or fails
against a tree that already contains module A's changes.

---

## 1. Prerequisites

### 1.1 Branch

- Planning happens on `ModuleSupport-Roadmap`. The roadmap must be reviewed
  and **merged to `master`** before an implementation branch starts (roadmap
  §8).
- Then branch from the updated `master`:

  ```
  git checkout master && git pull
  git checkout -b ModuleSupport-<Family>-<Module>    # e.g. ModuleSupport-Financials-AP
  ```

- Do not carry unrelated pod/config commits onto the module branch. If
  `personas.yaml` shows as modified before you start, stop and resolve it
  first — that file holds pod configuration and must not ride along in a
  module commit.

### 1.2 Access and credentials

- A working pod configuration, verified by a bounded read-only call (§3.2).
- The persona is resolved in `src/spire/mcp_server/server.py`
  (`PERSONA_NAME = "default_dev"`, module-level `_persona = load_persona(...)`).
  A module that needs different credentials changes that one constant — do not
  add a per-tool persona argument.
- **No credentials in docs, logs, or tickets.** Capture commands, never values.

### 1.3 The two inputs you cannot synthesize

1. **The SME prompt set.** 10–20 real questions with expected answers per
   module, supplied module by module (roadmap §1.5; minutes action item).
   Without it, "supported" has no definition and the acceptance gate cannot
   close.
2. **Confirmation of the module boundary.** What is in scope, what is
   explicitly refused. The roadmap's Gate 0 owns this.

Everything else — endpoints, fields, counts, quirks — you discover yourself.

---

## 2. Two tracks, one gate

| Track | Deliverable | Blocks acceptance? |
|---|---|---|
| **A. REST** (this document, §3–§7) | prompt → Fusion REST → verified answer | **Yes** |
| **B. SQL/schema capture** (§8) | tables, columns, join evidence for later SQL parity | No |

The rule, stated once and repeated only where it is load-bearing: **a module
is supported when the prompts answer correctly from REST.** SQL generation,
the SQL overlay, and the SQL editor are a later phase. Recording schema facts
as you go is cheap and worth doing; *building* SQL support is not a condition
of release.

This is not a preference — it is what the failures of 2026-11-21 taught. The
SME litmus run scored 24/40 against REST-backed answers while only 1 of 22
emitted SQL statements agreed with REST (`docs/fixes/FIX_PLAN.md`, F-078…F-082).
Gating REST delivery on SQL would have blocked working answers behind broken
ones.

---

## 3. Track A, step 1 — REST feasibility inventory

**Goal:** an endpoint inventory with captured requests and responses, so that
every later decision rests on observed behaviour rather than documentation.

This is the step Spire had no method for. `SCHEMA_DISCOVERY_METHOD.md` is
entirely about Oracle catalogs (`ALL_TABLES`, `ALL_TAB_COLUMNS`, joins) and
says nothing about the REST surface. The REST facts live today only in tool
docstrings and a stale POC reference
(`docs/reference/spire_fusion_endpoints_reference.md` — pod and auth details
out of date). Treat those as leads, not evidence.

### 3.1 What to collect

For each candidate root resource and each child you expect to traverse:

| Fact | Why it matters | Where it lands |
|---|---|---|
| Base path / resource family | The `_PATH` constant in the tool | `tools/<module>.py` |
| Auth model | `FusionClient` supports **basic only**; anything else raises | §1.2 |
| Which fields the payload actually carries | Projection list and synthesizer model | `_PROJECTED_FIELDS`, §6.6 |
| Which fields are filterable server-side via `q=` | Determines the server clause | §3.3 |
| Which fields need client-side filtering | Over-fetch + Python predicate | tool body |
| `expand=` paths for children | Avoids a second round trip, or proves you need one | tool body |
| Pagination: page size, `hasMore`, `limit` cap | `page_all` parameters | §3.4 |
| Count semantics: `totalResults` present or omitted | Honest `total_available` | §5.4 |
| Sort support (`orderBy`) | "top N by amount" without a full scan | §5.3 |
| Role/permission requirements | Refusal vs error behaviour | §3.5 |
| Error shapes: 400/401/403/404/500 | Explicit tool errors | §5.1 |

### 3.2 The probe procedure

Probe through the same client the tools use, so the transport is not a
variable:

```
PYTHONPATH=src python - <<'PY'   # or a scratch script under scripts/
import asyncio
from spire.config import load_persona
from spire.fusion.client import FusionClient

async def main():
    p = load_persona("default_dev")
    async with FusionClient(p) as c:
        r = await c.get("/fscmRestApi/resources/11.13.18.05/<resource>",
                        params={"limit": 1, "onlyData": "true"})
        print(sorted(r.keys()))
        print(r.get("count"), r.get("hasMore"))
        items = r.get("items") or []
        print(sorted(items[0].keys()) if items else "NO ITEMS")

asyncio.run(main())
PY
```

Rules that are not negotiable:

- **`limit=1` for shape probes.** You are reading field names, not data.
- **Shape before values.** Confirm `items[0].keys()` contains what you expect
  before anyone writes a projection list. A projection naming a field the
  endpoint does not return yields silent nulls, not an error (§9.2).
- **Capture the full response to a file** before filtering it, exactly as
  `SCHEMA_DISCOVERY_METHOD.md` §10 requires for SQL captures. Grep the file,
  do not re-run with a different pipe.
- **Probe children only after the parent works.** A failed child on an
  unknown parent id proves nothing.

### 3.3 The single-clause rule (the quirk that shapes every tool)

On this pod, **composite `q=` clauses do not reliably AND-combine** — two
clauses that are each selective can return an empty set. Every list tool in
the repository is built around this:

```
pick the ONE most selective clause
  → send it as q=
  → over-fetch
  → apply the remaining predicates in Python
```

See `tools/invoices.py` for the canonical statement of the rule and the
selection order (exact identifier → supplier number → `LIKE` name → date lower
bound). Two consequences worth internalising:

- **A date range is half server, half client.** The lower bound can ride in
  `q=`; the upper bound is applied in Python. Sending both is the failure the
  rule exists to avoid.
- **When client-side filtering runs, the fetch must page to exhaustion** (or
  to a declared cap) before the tool claims a total. A single page of 200
  cannot report an honest count of a filtered set (§5.4).

Verify the rule on the new module's endpoints rather than assuming it
transfers. If a module's resource does AND-combine correctly, that is a
*material finding* — record it, because the tool shape can then be simpler.

### 3.4 Counts and paging

Two mechanisms exist; use the cheaper one that answers the question.

- **`FusionClient.total_results(path, server_clause)`** — a `limit=1` +
  `totalResults=true` + `onlyData=true` probe. Returns `int | None`. `None`
  means the pod did not report a count; **never treat it as zero**, and never
  fail a query because of it.
- **`page_all(client, path, label, server_clause, fields, page_size,
  max_pages, report_progress)`** — the shared paging loop, returning
  `(items, hit_page_cap, total)`. It reads `totalResults` from the **first**
  page, so the count describes the same filtered set being fetched, and the
  cap warning fires after page 1 rather than after the last page.

Do not write a private paging loop. Five tools did once and drifted — one
paged at 200 and another at 500 while citing the same note, and one silently
truncated every unfiltered scan at 10,000 rows for months. The shared helper
exists because of that.

### 3.5 Access and refusal behaviour

Establish, per endpoint: what an unauthenticated call returns, what a
permitted-but-unauthorized call returns, and what a missing record returns.
These decide whether the tool raises (a break) or refuses (an answer). Spire
distinguishes the two deliberately — `plan_refusal` in `graph/pipeline.py`
exists so a decline is never counted as a crash.

### 3.6 Output artifact

Commit nothing for this step, but write the inventory into the module
branch's notes (or a section of the module's eventual handover) as a table:

| Resource | Path | Server-filterable | Client-side | Children (`expand`) | Count | Roles | Notes |
|---|---|---|---|---|---|---|---|

Every row must cite a command that produced it. "It should support `q=` on
`X`" is not a row; "`q=X='…'` returned 3 of 48,931, captured in `t_…`" is.

---

## 4. Track A, step 2 — the prompt set

The SME supplies the questions; you owe them a file the harness can run and a
ledger that says what "correct" means for each.

### 4.1 Shape

Follow `prompts/sme_module_a/sme_module_a_litmus.txt`:

- One prompt per line; `#` comments and blank lines ignored.
- Header comments state tier, source, capture date, and **the fill-value
  rule**: every record identifier substituted into a prompt must be queried
  on the pod first, with its child counts recorded. A prompt naming a record
  with no children returns an empty list, and an empty list is
  indistinguishable from a broken pipeline.
- **Prompt wording is the test.** Substitute `{PLACEHOLDER}` values only.

### 4.2 Expected-disposition ledger

Each prompt carries exactly one expected disposition, recorded beside the
expected answer (`prompts/sme_module_a/sme_module_a_expected.md` is the model):

| Disposition | PASS means |
|---|---|
| `PASS-EXPECTED` | Answer is correct and complete. |
| `PARTIAL-EXPECTED` | Clean answer that omits an unmodelled field. Inventing the field is a FAIL. |
| `GAP-EXPECTED` | A clean refusal naming the missing capability. Do not score this as a regression, and do not delete the prompt to "fix" the file — the gap is the record. |

A module whose ledger has no `PASS-EXPECTED` rows has not been specified.

### 4.3 Cross-run scoring

Keep one row per prompt and one column per run. A single run cannot answer
"did that fix work?" — a score can fall because the pod changed, and the
run-level total hides it. The working model is
[`../sme_prompts_status/COMPARISON.md`](../sme_prompts_status/COMPARISON.md):

- per-prompt status code (`OK(n)`, `ZERO`, `REFUSED`, `ERR403`, `BADSQL`),
  with `→` for a change and `=` for none;
- a **blocked-by** column naming the defect or environment cause;
- a summary that separates **code movement** from **environment movement**,
  and states the comparable denominator.

That separation is what stopped a real regression being invented from a pod
outage: run02 read 13 `OK` against run01's 11, but 10 prompts were
simultaneously blocked by two access defects, so the comparable set answered
and refused in exactly the same proportions. Report both numbers.

---

## 5. Track A, step 3 — implement the tools

Copy the shape of an existing tool rather than inventing one. The three shapes
in the repository cover nearly every module need.

### 5.1 List tool — copy `src/spire/mcp_server/tools/invoices.py`

Its anatomy, in order, is the recipe:

1. **Module docstring states the quirks.** For invoices it records the
   single-clause workaround, the two-call `unpaid` union, and the exact
   meaning of each date bound. Write the module's quirks here or they will be
   rediscovered by the next session.
2. **`<RESOURCE>_PATH` constant.** One place, no inline paths.
3. **`_PROJECTED_FIELDS`** — exactly the fields the synthesizer needs, plus
   the identifiers used for joins. Nothing more; payload width is real.
4. **`OVERFETCH_LIMIT`** when client-side filtering exists.
5. **Server-clause selection** — most selective first, one clause only (§3.3).
6. **`needs_client_filter`** — true when more than one predicate applies, or
   when any predicate is compound (half server, half client). This flag
   decides over-fetch versus direct fetch, and therefore decides whether the
   count is honest.
7. **Paged fetch via `page_all`** when client-filtering and a server clause
   exist; plain `get` otherwise.
8. **Python `matches()` predicate** — mirror of the server clause plus the
   client-side halves. Keep it total: a `None` value fails the predicate
   rather than raising.
9. **Projection** after filtering, not before — filtering on a field you
   dropped is the classic self-inflicted bug.
10. **Count resolution** — `ToolResult.build(...)` when the total is known and
    provable; `total_available=None, truncated=True` when the page cap fired.
11. **Docstring `Args`/`Returns`** describing behaviour, not implementation.

The wrapper in `src/spire/mcp_server/server.py` is deliberately thin: an
`@mcp.tool()`-decorated `async def` with a flat, typed signature, a
docstring written **for the planner** (it names the natural-language shapes
the tool serves), then `async with FusionClient(_persona) as client:` and
`return result.to_dict()`. Put logic in `tools/`, never in `server.py`.

### 5.2 Single-record tool — copy `tools/purchase_order_by_id.py`

- Resolve one record by its identifier via `q=`, not by scanning.
- **Return `None` for a not-found record**, not an exception — the by-id path
  treats a 404 as a legitimate "no such record" answer.
- Decide explicitly which identifier the tool accepts. The repository has
  been burned by confusing an internal numeric key with the human-facing
  number (F-079: a number bound to the internal id returned zero rows).
  Document the identifier in the docstring, in the tool name if needed, and
  in the KG note.

### 5.3 Aggregation / comparison tool — copy `tools/aggregate_purchase_orders.py`

- **One op, one tool.** Never a flag on an existing tool; a new grouping or
  measure is a new tool and a new registry row.
- Return a **shape wrapper** (`shape`, `rows`, …) rather than a bare list.
  The pipeline detects `shape` in the first record and skips field projection,
  because a wrapper's keys are not entity columns (`_project_outputs` in
  `graph/pipeline.py`).
- Prefer server-side `orderBy` + `limit` for top-N over a full scan.
- If the tool derives a rating, stage, or recommendation, the synthesizer
  **copies** it and never re-derives it.

### 5.4 Result honesty

`tools/tool_result.py` defines the contract: `items`, `total_available`,
`limit_applied`, `truncated`. The rules that make it worth having:

- `truncated` is true **only** when the total is known and exceeds the items
  returned. Unknown count is not truncation.
- A filtered count must describe the filtered set. Counting an unfiltered
  server clause and reporting it beside filtered rows is a wrong answer that
  looks authoritative.
- Several upstream totals understate the truth — receipts, for example, report
  a second identical collection under a different name. Where a source's count
  is known to under-report, say so in the docstring.

Counts and truncation are correctness, not cosmetics: a capped result that
reads like a complete set is the worst failure mode Spire has, because nothing
in the output invites the reader to doubt it.

### 5.5 Naming

- Tool names are long and explicit: `search_invoices`,
  `get_purchase_order_lifecycle_status`, `aggregate_standard_receipts_by_method`.
  Verb first, resource second, qualifier last.
- The name is used as a key in the planner registries (§6.5) and appears in
  logs and progress lines. Renaming a registered tool is a multi-file change.

---

## 6. Track A, step 4 — wire it into Spire

A tool that works in isolation answers nothing. This section is the complete
set of places a module touches, and **§6.0 is the canonical work order**. The
subsections after it are reference detail, deliberately not in execution
order — consult them from the table.

The scope is wider than a tool plus some KG rows. Adding a module touches the
REST layer, the intent knowledge graph, the SQL seed, the parser, the planner,
the synthesizer, the renderer, the validators, the tests, and the docs. Any one
of them omitted produces a module that either does not route, does not execute,
or answers wrongly — and several fail silently.

### 6.0 The complete touchpoint inventory

Twenty-nine touchpoints. Work them top to bottom. The **Gate** column says
whether it blocks REST delivery: `REST` = required for prompt→results,
`SQL` = deferred (Track B, §8), `both` = needed either way.

| # | Stage | File / location | What to add | Gate | Detail |
|---:|---|---|---|---|---|
| 1 | Discovery | pod + Fusion REST | endpoint inventory: path, filterable fields, `expand`, paging, count, roles | REST | §3 |
| 2 | Discovery | pod Oracle catalogs | physical table/view and columns behind each resource; population counts | SQL | §6.10 |
| 3 | Tool | `src/spire/mcp_server/tools/<module>.py` | the tool module — copy a shape from §5 | REST | §5 |
| 4 | Tool | `src/spire/mcp_server/server.py` | import + thin `@mcp.tool()` wrapper, persona-scoped client | REST | §5.1 |
| 5 | Intent KG | `scripts/sql/kg_schema.sql` STEP 3 | `kg_entity` row(s): id field, display field, `endpoint_path`, description, **`module`** | REST | §6.3 |
| 6 | Intent KG | `…kg_schema.sql` STEP 4 | `kg_entity_field` — one row per projectable field, with `field_role` | REST | §6.3 |
| 7 | Intent KG | `…kg_schema.sql` STEP 9 | `kg_entity_tool` — the fetcher per filter type (`none`, `by_id`, …) | REST | §6.3 |
| 8 | Intent KG | `…kg_schema.sql` STEP 11 | `kg_entity_filter` — one row per supported filter: mechanism, tool arg, `query_style`, `filter_field`/`filter_op` | REST | §6.3 |
| 9 | Intent KG | `…kg_schema.sql` STEP 5 + 10 | `kg_edge` + `kg_edge_tool` — one row per traversal, with `iter_fields_json` | REST | §6.3 |
| 10 | Intent KG | `…kg_schema.sql` STEP 7 | `kg_vocabulary` — `entity_synonym`, `field_synonym`, controlled values | REST | §6.3 |
| 11 | Intent KG | `…kg_schema.sql` STEP 6 + 8 | `kg_pattern` + `kg_pattern_binding` — **only** if reusing a named pattern | REST | §6.3 |
| 12 | Intent KG | `…kg_schema.sql` STEP 12 | `kg_entity_sql`, `kg_sql_column`, `kg_derived_projection` | SQL | §6.3, §6.11 |
| 13 | KG runtime | `scripts/rebuild_kg.py` | rebuild after any seed change | REST | §6.4 |
| 14 | KG runtime | `scripts/build_classifier_context.py` | regenerate `routing/classifier_menu.sysprompt` | REST | §6.4 |
| 15 | Parser | `src/spire/nl_parser/context/<module>/` | one `b_*.sysprompt` per filter/teaching block | REST | §6.4 |
| 16 | Parser | `src/spire/nl_parser/context/order.manifest` | append every new block — unlisted blocks are never sent | REST | §6.4 |
| 17 | Parser | `src/spire/nl_parser/context_assembly.py` | `KNOWN_MODULES` | REST | §6.1 |
| 18 | Parser | `src/spire/nl_parser/router.py` | `ModuleChoice` description **and** `_CLASSIFIER_INSTRUCTION` | REST | §6.1 |
| 19 | Planner | `src/spire/planner/registries.py` | the seven registries (§6.5) | REST | §6.5 |
| 20 | Planner | `src/spire/planner/planner.py` | prose entity guard (required reference / supported filters) | REST | §6.13 |
| 21 | Planner | `src/spire/planner/plan_builders.py` | only if the module introduces a new arg shape or iteration | REST | §6.5 |
| 22 | Synthesizer | `src/spire/synthesizer/p2p.py` | record model + `build_*_records` | REST | §6.6 |
| 23 | Synthesizer | `src/spire/synthesizer/synthesizer.py` | `target_entity` dispatch branch | REST | §6.6 |
| 24 | Refusals | `src/spire/nl_parser/capability.py` | message text for any new unanswerable kind | REST | §6.14 |
| 25 | Rendering | `src/spire/rendering/formatters.py` | the entity's block; `_render_records` itself is generic | REST | §6.14 |
| 26 | SQL overlay | `src/spire/kg/sql_overlay.py` | `_ENTITIES`, `_FILTERS`, `_JOINS`, `_LITERALS`, `aggregations`, `not_expressible` | SQL | §6.11 |
| 27 | Validation | `scripts/validate_kg_schema.py`, `scripts/validate_sql_coverage.py` | must pass; they catch seed/overlay drift | both | §6.12 |
| 28 | Tests | `tests/test_kg_metadata.py`, `tests/test_router.py`, new tests | bump count tripwires; add behaviour tests | both | §6.2 |
| 29 | Docs | `docs/README.md`, `context_bundles.yaml` | index row + bundle membership | both | §6.8 |

Run it in this order because later steps read earlier ones: the classifier
menu is generated *from* the KG, the parser menu is assembled *from* the KG at
import, and the SQL overlay's coverage validator compares *both* against the
tool signatures.

### 6.1 The module list is hardcoded in six places

Adding a module (or renaming one) means editing all six. Each has its own
reason; none reads the others.

| # | File | What to change |
|---|---|---|
| 1 | `src/spire/nl_parser/context_assembly.py` | `KNOWN_MODULES` tuple |
| 2 | `src/spire/nl_parser/router.py` | `ModuleChoice` field description **and** `_CLASSIFIER_INSTRUCTION` ("Choose from exactly these four modules…") |
| 3 | `scripts/sql/kg_schema.sql` | `kg_entity` `CHECK (module IN (...))` |
| 4 | `scripts/add_entity_module.py` | `_VALID_MODULES` and the CHECK inside `_TABLE_NEW` |
| 5 | `scripts/build_classifier_context.py` | `KNOWN_MODULES` list |
| 6 | `tests/test_router.py` | the module loop in the router test |

`build_classifier_context.py` also warns when a module in `KNOWN_MODULES` has
no entities — that warning is the cheap detector for "I edited five of six."

### 6.2 Entity-count tripwires

Row counts are deliberately pinned, so growth must be acknowledged rather than
absorbed. **The count is 23 as of `InvoiceLine` (F-077); it was 22 before.**

- `scripts/print_kg.py` — `expected_rows: 23` for `kg_entity` and for its
  satellite
- `tests/test_kg_metadata.py` — `"kg_entity": 23`, `"kg_entity_sql": 23`
- `scripts/add_entity_module.py` — `patched != 23` assertion (the script still
  carries its own hardcoded count, so re-read it rather than trusting this line)

A new entity increments each. A tripwire that fires is doing its job; silence
would mean the count is no longer being checked.

### 6.3 The intent knowledge graph

`scripts/sql/kg_schema.sql`, seeded by step. This is the module's **intent
graph**: the runtime does not hardcode what a module can answer — it reads it
from these tables. Getting the rows right is what makes a new module
answerable; the Python changes mostly teach the pipeline that the module
exists.

**Which KG table drives which stage.** This mapping is why the KG cannot be
half-filled: each table feeds a different consumer, and a gap in one produces a
failure in a different layer.

| KG table | Read by | Effect when missing |
|---|---|---|
| `kg_entity` | parser menu, classifier menu, planner | entity unknown; prompts never route |
| `kg_entity_field` | parser `COLUMNS` menu, projection | requested columns refused (see AP-1 in the AP assessment) |
| `kg_entity_tool` | planner, executor | entity is known but has no fetcher, so cannot be a root |
| `kg_entity_filter` | parser menu, planner arg construction | filter unrecognised, or recognised but unbuildable |
| `kg_edge` / `kg_edge_tool` | planner includes, executor iteration | `include` silently does nothing |
| `kg_vocabulary` | parser normalisation, classifier menu | synonyms and coded values do not resolve |
| `kg_pattern_binding` | planner | a reused pattern has no mechanics |
| `kg_entity_sql` / `kg_sql_column` / `kg_derived_projection` | SQL emitter only | REST unaffected; SQL projection incomplete |

What a module typically adds:

| Table | Add |
|---|---|
| `kg_entity` | one row per entity: `entity_name`, `canonical_id_field`, `display_name_field`, `endpoint_path`, `description`, **`module`** |
| `kg_entity_field` | one row per projectable field, with `field_role` from the CHECK list (`canonical_id`, `display_id`, `display_name`, `status`, `date`, `amount`, `reference`, `projection`) |
| `kg_entity_tool` | the fetcher: `(entity, filter_type='none')` for the list/default path; a dedicated row per special filter (`by_id`, `lifecycle_status`) |
| `kg_entity_filter` | one row per supported filter: `mechanism` = `entity_level` (dedicated fetcher arg) or `edge_traversal` (walk to `target_entity`), plus `query_style` (`server_q` / `client_side`) and `filter_field`/`filter_op` |
| `kg_edge` + `kg_edge_tool` | one row per traversal: join fields on both sides, cardinality, `server_filter_rule`, `traversal_hint`, and the tool that walks it |
| `kg_vocabulary` | terms for any controlled value the parser must canonicalise (`entity_synonym`, `country`, statuses, …) |
| `kg_pattern_binding` | only if the filter reuses a named pattern; a bespoke filter needs none |

Three traps:

- `kg_vocabulary.vocab_kind` has its own CHECK list. A new vocabulary kind is
  a schema change, not a data change.
- Entity **descriptions are read by the parser and the classifier menu**. Keep
  them behavioural ("note: this endpoint exposes SupplierNumber, not
  SupplierId") — they are prompt text, not documentation for humans.
- **`kg_entity_field` must be at least as wide as the tool's projection.** The
  AP assessment's AP-1 is exactly this: the tool projects `DueDate` and
  `Supplier`, the KG declares neither, and every answer asking for them is
  refused as an unavailable column — while the value sits in the row. Diff
  `_PROJECTED_FIELDS` against the seed before declaring an entity done.

### 6.4 Parser context blocks

The parser preamble is assembled from `.sysprompt` blocks listed in
`src/spire/nl_parser/context/order.manifest`; a block's module is the first
path component of its manifest entry.

- Add a module folder (`context/<module>/`) with one `b_*.sysprompt` per
  supported filter/teaching, plus `m_*` for modes if the module introduces one.
- **Append every new block to `order.manifest`.** A block that exists but is
  not in the manifest is never sent to the model — silently.
- Tier 1 (`core`, `refusals`, `modes`, `columns`) is always assembled; do not
  restate core rules in a module block.
- A missing listed block raises at import. That is intentional: a partial
  preamble must never be sent silently.

### 6.5 Planner registries — `src/spire/planner/registries.py`

| Registry | Add when |
|---|---|
| `_TOOL_PRIMARY_ARG` | the tool is iterated per parent record (the arg that receives `$iteration_value`) |
| `_LIMIT_CAPABLE_TOOLS` | the tool's wrapper accepts `limit` — sending `limit` to a wrapper that does not declare it raises at the MCP boundary |
| `_OUTPUT_NAME_BY_ENTITY` | always, for a new entity: the bucket name the synthesizer reads |
| `_AGGREGATION_TOOLS` + `_AGGREGATION_PARAMS` | a new aggregation op — **both** rows, or the plan forwards a kwarg the tool lacks |
| `_COMPARISON_TOOLS` + `_COMPARISON_PARAMS` | a new comparison op, same both-rows rule |
| `_ENTITY_EXAMPLE_PROMPT` | always: the example shown when a user asks for an unsupported filter on the entity |
| `_FILTER_SOURCE_NAME_SUFFIX` / `_FILTER_SOURCE_NONEMPTY_SUFFIX` | the filter keeps or drops the parent based on child results |

`_OUTPUT_NAME_BY_ENTITY` deserves a warning: two entities over different id
spaces must not share a bucket name. One would overwrite the other and make
the synthesizer's id-harvest ambiguous.

### 6.6 Synthesizer record model

`synthesize_response(outputs, target_entity, ...)` selects a schema by
`target_entity`. A new entity needs:

- a record model beside the others (`synthesizer/p2p.py` holds
  `InvoiceRecord`, `PurchaseOrderRecord`, …) with only fields the pipeline
  actually has;
- a builder (`build_invoice_records`) that maps executed rows to that model;
- a `target_entity` branch in `synthesizer/synthesizer.py`;
- an `UnsupportedEntityError` path that stays reachable — an entity with no
  schema must raise, not degrade.

**Field parity check, and a live example of getting it wrong:** `/invoices`
returns `DueDate`, `tools/invoices.py` projects it, and `InvoiceRecord` has no
`due_date` field — the value is fetched and discarded, so no answer can show
it. Grep the model for each field in `_PROJECTED_FIELDS` before declaring the
entity complete. This is the cheapest gap in the whole procedure to fix and
the easiest to miss.

### 6.7 Exposure

- MCP tools: `server.py` import block + `@mcp.tool()` wrapper.
- API/CLI: `src/spire/api/` and `scripts/` if the module must be reachable
  outside the MCP session. Most modules need nothing here.

### 6.8 Documentation wiring

Any new document is also wired in two places, and there is a test that fails
if it is not:

1. **`docs/README.md`** — add a row to the relevant table. It is the
   workspace-wide inventory, not decoration.
2. **`context_bundles.yaml`** — every tracked file must belong to a bundle or
   be excluded, enforced by `tests/test_bundle_manifest.py`
   (`test_every_tracked_file_is_in_a_bundle`). Use the bundles' own rule:
   *does a resuming window need this to know where it is and what to do
   next?* Yes → `plan`; consulted on demand → `reference`; a past record →
   `history`.

Run that test after adding or moving docs. It was added to the repository
after this playbook was first drafted, and the first merge that brought the
two together failed on exactly this — the module-support folder existed,
linked correctly from the README, and was in no bundle.

### 6.9 Restart the stack before believing a run

The MCP server reads tool definitions and KG carriers at **startup**. After
changing `src/spire/mcp_server/`, `src/spire/kg/`, or the KG seed, restart it
(`./spire-host.sh --stop && ./spire-host.sh --start dev`) or the run executes
the previous code and the result describes a tree that no longer exists.

### 6.10 Discovery — the physical tables and columns behind the endpoints

This is the investigation the REST work cannot supply and the SQL work depends
on. Do it while the module is already open, because it is cheap now and
expensive to reconstruct later.

For each resource and child in the endpoint inventory (§3.1), record:

| Fact | How | Why it is recorded |
|---|---|---|
| Physical table or view | objects under the prefix: `ALL_TABLES` ∪ `ALL_VIEWS` ∪ `ALL_SYNONYMS` | Fusion usually exposes views; the REST resource name is not the object name |
| Columns, in physical order | `ALL_TAB_COLUMNS … ORDER BY COLUMN_ID` | the role map and `kg_sql_column` need it |
| Which columns are **populated** | `SELECT COUNT(*), COUNT(<col>) FROM <table>` | existence is not evidence; a stub column binds a role to nulls |
| Identity when the pod exposes no PK | `COUNT(DISTINCT …)` on candidate keys | AP invoice lines have no `INVOICE_LINE_ID`, so `(INVOICE_ID, LINE_NUMBER)` is the identity |
| Join keys and their nullability | Both sides, plus `NULLABLE` | a nullable join key silently drops rows under an inner join |
| REST field → column mapping | Field-by-field, where not obvious | the emitter projects physical columns, not REST names |

The full procedure, its six failure modes and its cell templates are in
[`../SCHEMA_DISCOVERY_METHOD.md`](../SCHEMA_DISCOVERY_METHOD.md) — use it
rather than improvising queries, and note that it does **not** cover the REST
side in §3.

Where this record lives: the module's acceptance note or a handover section,
not a new file per module. `docs/plan/KG_ROLE_MAPS.md` is the existing
append-only home for role maps.

### 6.11 SQL overlay — the second place a module is declared

**Deferred for delivery, still a real touchpoint.** `src/spire/kg/sql_overlay.py`
is a hand-authored overlay beside the KG, not derived from it, so a new entity
can be fully wired for REST and still have no SQL. That is acceptable while SQL
is deferred — but it must not be mistaken for "nothing to do", because
`scripts/validate_sql_coverage.py` checks the overlay against tool signatures
and will report the gap.

What lives there:

| Registry | Contents |
|---|---|
| `tool_to_entity` | MCP tool name → entity; the emitter's entry point |
| `_ENTITIES` | `EntitySpec` per entity: `fusion_table`, `select_columns`, `base_joins`, `pk_column`, `alias` |
| `_FILTERS` | `FilterSpec` per `(entity, filter_type)`: the predicate template |
| `_JOINS` | `JoinSpec` per traversal |
| `_LITERALS` | pod-specific literal values |
| `_ASSUMPTIONS` | stated assumptions, emitted as comments in the SQL |
| `aggregations` | `AggregationSpec` per aggregation tool |
| `not_expressible` | tools that are not one SELECT — declared, not faked |
| `sql_control_args`, `sql_disabled_args` | args that must not reach the emitter, and why |

Two rules that matter:

- **A tool absent from `tool_to_entity` emits no SQL and is not an error** —
  the emitter prints an explicit comment rather than inventing a SELECT. A tool
  that *is* present but has a missing column is a different, louder failure.
- **`not_expressible` is the honest answer for multi-resource reconciliations**
  (lifecycle, comparisons). Do not fabricate a single SELECT to silence a
  coverage warning; that is how wrong rows get produced.

### 6.12 Validators — run them, in this order

Both read the live KG, and the first also reads the pod.

| Order | Script | Checks | Run after |
|---:|---|---|---|
| 1 | `python scripts/validate_kg_schema.py` | resolves every `kg_derived_projection` expression to a physical table and classifies each referenced column as validated / on-pod / **missing** | any seed or role-map change |
| 2 | `python scripts/validate_sql_coverage.py` | overlay coverage against tool signatures, the KG vocabulary, and a measured list of columns that exist but never carry data | any tool or overlay change |
| 3 | `python scripts/build_classifier_context.py` | regenerates the classifier menu, and **warns when a known module has no entities** | any KG change |

Validator 3's warning is the cheapest detector for an incomplete module: it
fires when `KNOWN_MODULES` contains a module the KG does not populate, which is
what "I edited five of six places" looks like from the KG's side.

### 6.13 Planner entity guards

`src/spire/planner/planner.py` carries **prose** guards, one per entity shape,
that decide the refusal a user sees when a query is under-specified. They are
not in the KG and not derived from it, so a new entity without one fails in a
generic way.

The existing set to mirror:

- *"Invoice queries require a supplier reference…"* — a root requirement
- *"Address queries require a supplier or a country…"* — a disjunction
- *"CustomerAccount cannot be filtered by …"* — an unsupported-filter refusal,
  which routes through `capability.py` so it reads as an answer

Write one only if the module has a genuine root requirement or a filter that
must be refused rather than ignored. A guard that refuses too eagerly converts
an answerable question into a refusal — the failure mode the SME litmus set
exists to catch.

### 6.14 Refusal text and rendering

Two small surfaces, both user-visible:

- **`src/spire/nl_parser/capability.py`** — refusal messages are structured
  answers (Reason / Solution / Example), not error strings. A new unanswerable
  kind needs text here or the refusal reads as breakage. Its module docstring
  records why: an earlier version classified nearly every refusal as an unknown
  entity by scanning for capitalised words.
- **`src/spire/rendering/formatters.py`** — `_render_records` is generic (title,
  rows, columns, empty text), so most entities need only a block that chooses
  the columns. Do not add a second table renderer; the per-entity bullet blocks
  were removed for that reason.

---

## 7. Track A, step 5 — verify

Verification answers three different questions. Passing one does not imply the
others.

| Level | Question | How |
|---|---|---|
| **1. Tool** | Does the tool hit the right endpoint with the right arguments, and return honest metadata? | unit tests against a mocked client + one live call |
| **2. Pipeline** | Does the prompt route to that tool and synthesise a correct answer? | `scripts/promptkit.py` over the prompt set |
| **3. Agreement** | Does Spire's answer equal a direct REST answer for the same record? | field-by-field comparison against a captured payload |

### 7.1 Commands

**Check the endpoints are alive before scoring anything.** An empty collection
returning HTTP 200 is indistinguishable from a correct empty answer, and will
make a whole module look broken:

```
PYTHONPATH=src python -c "
import asyncio
from spire.config import load_persona
from spire.fusion.client import FusionClient
async def m():
    p = load_persona('default_dev')
    async with FusionClient(p) as c:
        for path in ['/invoices', '/suppliers', '/purchaseOrders']:
            print(path, await c.total_results('/fscmRestApi/resources/11.13.18.05' + path, ''))
asyncio.run(m())"
```

Compare the counts against a direct SQL count of the backing table before
trusting a `ZERO` result. On 2026-11-28 `/purchaseOrders` returned 0 while
`PO_HEADERS_ALL` held 18,389 rows.

Single prompt through the whole graph:

```
PYTHONPATH=src python scripts/run_graph.py --prompt "<a prompt from the set>"
```

A set, with results written to a directory:

```
PYTHONPATH=src python scripts/promptkit.py --run \
  --prompt-file prompts/sme_module_a/sme_module_a_litmus.txt \
  --outdir t_<module>_run 2>&1 | tee t_<module>_run.txt
```

`run_graph.py` also supports `--save-cache SLOT` / `--use-cache SLOT`, which
persist the **executor output** and replay it while still running parse and
plan live. Use it when iterating on the synthesizer: the pod fetch is the slow
part, and a replay announces itself on stderr so a cached run is never
mistaken for a live one.

### 7.2 What counts as passing

- Every `PASS-EXPECTED` prompt answers correctly.
- Every `PARTIAL-EXPECTED` prompt answers cleanly **without inventing** the
  unmodelled field.
- Every `GAP-EXPECTED` prompt refuses cleanly and names what is missing.
- Empty, capped, unauthorized, malformed, and multi-page cases are covered —
  and a capped result never reads as complete.
- Counts in the answer match a `total_results` probe for the same clause.

Sample the *values*, not just the shape. A run in which every amount is null
and every list is empty is a passing shape with a broken projection (§9.2).

### 7.3 Recording it

Capture full stdout/stderr to a file, grep the file, and put the file name in
the module's acceptance note. A result without a capture cannot be re-checked
after the next code change.

---

## 8. Track B — defer SQL, capture the facts

Do not build SQL support now. Do not skip the capture either: it is cheap
during discovery and expensive to reconstruct.

### 8.1 Record while you are already in the module

- **Physical table/view names** behind each REST resource (they are usually
  not the resource name).
- **Key columns** for identity and join, and which side is nullable — a
  nullable join key silently drops rows under an inner join.
- **Population, not existence.** A column can exist and be null on ~100% of
  rows; `SELECT COUNT(*), COUNT(<col>) FROM <table>` before anyone binds a
  role to it. `PO_LINES_ALL.AMOUNT` is present and null on 99.96% of rows —
  binding to it produced SQL returning NULL where REST returned the true
  amount (F-060).
- **Which REST field maps to which column**, when the mapping is not obvious.
- **Identity columns that the pod does not expose.** AP invoice lines carry no
  `INVOICE_LINE_ID` on this pod, so `(INVOICE_ID, LINE_NUMBER)` is the identity.
  Record this kind of finding — it decides what the KG can key a child entity
  on, and it is invisible from the REST shape alone.

### 8.2 Hand off, do not duplicate

When schema depth is genuinely needed, use
[`../SCHEMA_DISCOVERY_METHOD.md`](../SCHEMA_DISCOVERY_METHOD.md). It is the
authoritative procedure for `ALL_TABLES`/`ALL_VIEWS`/`ALL_SYNONYMS`,
`ALL_TAB_COLUMNS`, join verification, and role maps. Note its scope: it is
about Oracle catalogs, so it cannot substitute for §3 here.

### 8.3 The later SQL phase

When REST answers are stable, SQL parity compares **semantically equivalent
result sets** under matching filters, scope, and paging — not byte equality.
Expect the current gaps to reproduce until fixed: unmapped arguments producing
invalid SQL (F-078), numbers bound to internal ids returning zero rows (F-079),
and predicates that produce false zeros (F-080).

---

## 9. Failure modes

Each is observed in this repository, not hypothetical.

**9.1 Composite `q=` assumed to work.** Two selective clauses return empty.
Keep one clause server-side; document the clause priority in the tool.

**9.2 Projection naming a field the endpoint does not return.** No error —
silent nulls, or a column that never appears. Probe keys with `limit=1`
first (§3.2), then diff `_PROJECTED_FIELDS` against the synthesizer model
(§6.6).

**9.3 A filter that runs client-side but never over-fetches.** The tool
returns the first page and reports it as the filtered set. The
`needs_client_filter` flag exists to prevent exactly this.

**9.4 Counting an unfiltered set beside filtered rows.** The number is real
and belongs to a different question.

**9.5 Trusting the internal id for a user-facing number.** Zero rows, no
error. Decide and document which identifier each tool accepts.

**9.6 An endpoint that answers 200 with zero rows.** The single most
expensive failure in this repository. `/purchaseOrders` returned 0 rows while
the backing table held 18,389, and the synthesizer reported *"No purchase
orders found matching the criteria."* with no error anywhere — every
procurement prompt scored `ZERO` and the code was never at fault (SP-003). An
empty collection is never evidence that a filter works. Probe
`total_results()` and compare against a SQL count before debugging a prompt,
and always record which prompts are environment-blocked (§4.3).

**9.7 A context block not listed in `order.manifest`.** The file exists, the
tests pass, and the model never sees it.

**9.8 Editing five of six module lists.** The classifier menu regeneration
warns; the router raises on an unknown module. Run both before believing the
wiring is done.

**9.9 Deleting a `GAP-EXPECTED` prompt to make the set green.** The gap is
the specification of what is not yet supported.

**9.10 Treating an `--use-cache` run as a live result.** Replays announce
themselves on stderr for this reason. A cached run cannot detect that a tool's
return shape changed.

**9.11 Declaring a module complete because the tools exist.** Completeness is
the prompt ledger (§4.2) plus §7.2, not the file list.

---

## 10. Definition of done

- [ ] Branch `ModuleSupport-<Family>-<Module>` off updated `master`.
- [ ] Endpoint inventory with captured evidence (§3.6).
- [ ] Physical tables, columns, population and join keys recorded (§6.10).
- [ ] Prompt set with dispositions; every fill value pod-verified (§4).
- [ ] Tools implemented in the right shape; quirks documented in their
      docstrings (§5).
- [ ] `ToolResult` metadata honest; capped ≠ complete (§5.4).
- [ ] Intent KG seeded: `kg_entity`, `kg_entity_field`, `kg_entity_tool`,
      `kg_entity_filter`, edges, vocabulary (§6.3).
- [ ] `kg_entity_field` at least as wide as the tool's `_PROJECTED_FIELDS`
      — no fetched-then-refused column (§6.3, AP-1).
- [ ] `rebuild_kg.py` run; classifier menu regenerated (§6.4).
- [ ] Context blocks added **and** `order.manifest` updated (§6.5).
- [ ] All six module lists consistent (§6.1); entity-count tripwires bumped
      (§6.2).
- [ ] Planner registries complete (§6.5) and an entity guard written if the
      module has a root requirement (§6.13).
- [ ] Synthesizer model and builder; no projected field silently dropped
      (§6.6); renderer block added (§6.14).
- [ ] `validate_kg_schema.py` and `validate_sql_coverage.py` pass (§6.12).
- [ ] SQL overlay entries added or the gap explicitly deferred (§6.11).
- [ ] Stack restarted after the last MCP/KG change (§6.9).
- [ ] Docs added to `docs/README.md` and to a `context_bundles.yaml` bundle;
      `tests/test_bundle_manifest.py` green (§6.8).
- [ ] `PASS`/`PARTIAL`/`GAP` results match the ledger; counts match
      `total_results` (§7).
- [ ] Acceptance note cites capture files.
- [ ] No SQL work required for acceptance (§2).
- [ ] Roadmap updated: capability matrix, known gaps, status (§6.1 of roadmap's
      release gate).

---

## 11. Appendix

### 11.1 File map

| Path | Role |
|---|---|
| `src/spire/fusion/client.py` | REST transport; basic auth; `get`, `total_results` |
| `src/spire/mcp_server/server.py` | persona, `@mcp.tool()` wrappers |
| `src/spire/mcp_server/tools/` | one module per tool; the real logic |
| `src/spire/mcp_server/tools/pagination.py` | `page_all` — the only paging loop |
| `src/spire/mcp_server/tools/tool_result.py` | `ToolResult` completeness contract |
| `src/spire/planner/registries.py` | tool/op/entity mapping tables |
| `src/spire/planner/plan_builders.py` | filter → tool arg construction |
| `src/spire/executor/executor.py` | `session.call_tool`, iteration |
| `src/spire/synthesizer/synthesizer.py` | response selection by `target_entity` |
| `src/spire/synthesizer/p2p.py` | entity record models and builders |
| `src/spire/nl_parser/context_assembly.py` | `KNOWN_MODULES`, manifest assembly |
| `src/spire/nl_parser/router.py` | module classifier |
| `src/spire/nl_parser/context/` | parser preamble blocks + manifest |
| `scripts/sql/kg_schema.sql` | KG DDL and seed |
| `scripts/rebuild_kg.py` | rebuild after seed changes |
| `scripts/build_classifier_context.py` | regenerate classifier menu |
| `scripts/promptkit.py`, `scripts/run_graph.py` | run prompts end to end |
| `prompts/sme_module_a/` | litmus set and expected ledger (the 40-prompt SME set; run results under `docs/plan/sme_prompts_status/`) |
| `context_bundles.yaml`, `tests/test_bundle_manifest.py` | bundle membership and the drift guard that enforces it |

### 11.2 Known documentation drift

- `docs/design/FEATURES.md` is referenced by several documents (including
  `docs/README.md` rule 4) and does not exist on `master`.
- `kg_entity_tool`'s Invoice note says a supplier is always required;
  `tools/invoices.py` accepts an `InvoiceNumber` lookup on its own. The note
  is stale — trust the tool, then fix the note.
- `docs/reference/spire_fusion_endpoints_reference.md` is POC-era: pod,
  endpoint, and authentication details are stale. Useful for quirks, not as
  current fact.

### 11.3 When to update this document

After each module, against the eight roadmap gates:

- a step that was missing → add it with the example that exposed it;
- a step that was wrong → correct it and keep the original claim visible;
- a step that was pilot-specific → mark it so, rather than generalising from
  one module.

This document carries the **method**. Per-module findings belong in the
module's acceptance note or handover.
