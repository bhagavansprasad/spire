# Prompt Coverage

What kinds of natural-language prompts Spire can answer today, what it
can't, and the work to expand coverage.

This doc is a living backlog — each gap is something we've actually hit
during prompt testing, not speculation. Status values: `open`,
`in-progress`, `done`.

---

## How to read this doc

A "prompt class" is a family of related queries that share a shape
(e.g., "all X by date range," "X grouped by Y"). For each class:

- **Example prompts** — actual prompts tested.
- **Status today** — what currently happens when you run them.
- **Gap** — what's missing and why.
- **Fix** — proposed change, with rough effort.

Effort labels:
- `small` — single tool/file, ~30 min
- `medium` — touches 2-3 files, half a day
- `large` — architectural, 1+ days

---

## Currently supported (works well)

These prompt shapes have working tools and produce honest output.

### Single-filter entity lookup
**Examples:**
- `"Find open purchase orders for EIP"`
- `"Find suppliers with 'Lee' in the name"`
- `"Show invoices for Lee Supplies"`

**Status:** Works. Tool returns up to 25 records; truncation disclosed
when the source has more (post the truncation-honesty work,
2026-05-30).

### Composite filter on a single entity
**Examples:**
- `"Pull all invoices after 2022-01-01"`
- `"Show purchase orders for Office Depot with status OPEN"`

**Status:** Works for the filters the tool supports. Truncation
disclosed when present.

### Multi-step entity traversal (Design 3 path only)
**Examples:**
- `"US suppliers with no recent invoices and open POs, plus the buyer"`
  (via `run_plan.py --intent original`)

**Status:** Works on the hand-built intent. Track A (`ask.py`) can also
attempt this prompt but scores poorly.

---

## Gaps discovered during testing

### G1. Date range upper bound on invoices  `[open]  [small]`

**Example prompts:**
- `"Pull all 2022 Jan Invoices"`
- `"Pull all 2022 Jan Invoices for Lee Supplies"`
- `"spend details by supplier for Lee Supplies in Jan 2022"`

**Status today:** Agent recognizes the gap and asks the user to manually
filter, or pulls everything after the lower bound. Honest but
incomplete.

**Gap:** `search_invoices` accepts `invoice_date_after` but not
`invoice_date_before`. No way to express a closed date range.

**Fix:** Add `invoice_date_before: str | None = None` parameter to
`search_invoices`. Apply as a client-side filter (same pattern as
`invoice_date_after`). Update the tool's MCP wrapper. Add a test case
for the range filter.

**Evidence:**

*Prompt 1:* `"Pull all 2022 Jan Invoices"`
- Agent: *"I can pull invoices after a specified date, but I don't have
  a way to filter by an end date. So, I will pull all invoices after
  January 1, 2022, and you'll have to manually filter for just January
  2022. Is that acceptable?"*
- Ground truth (curl, 2026-05-30): 212 invoices in Jan 2022.

*Prompt 2:* `"Pull all 2022 Jan Invoices for Lee Supplies"`
- Agent: *"I can only filter invoices after a specified date. Do you
  want to see all invoices for Lee Supplies after Jan 1, 2022?"*
- Ground truth (curl, 2026-05-30): 0 invoices for Lee Supplies (supplier
  1252) in Jan 2022. Records examined span 2012-01-01 to 2024-08-23, so
  the 0 is real.

---

### G2. Supplier status filter  `[open]  [small]`

**Example prompts:**
- `"Please find out inactive suppliers for Lee Supplies in Jan 2022"`
- `"List all active suppliers"`

**Status today:** Agent honestly declines because no tool filter
matches.

**Gap:** Suppliers carry a `Status` field (`ACTIVE`, `INACTIVE`, etc.)
on every record, but `search_suppliers` has no parameter to filter by
it.

**Fusion quirk discovered 2026-05-30:** Even with single-clause syntax,
`q=Status='INACTIVE'` against `/suppliers` returns HTTP 400. `Status`
is response-only on this endpoint, not queryable. The fix must filter
client-side.

**Fix:** Add `status: str | None = None` parameter to
`search_suppliers`. Over-fetch (similar to `search_suppliers_by_country`'s
OVERFETCH_LIMIT=500) and filter client-side. Migrate to `ToolResult`
while we're in there (covers part of G3).

**Note:** The original prompt was logically tangled ("inactive *for*
Lee Supplies"). The fix supports the underlying capability — querying
suppliers by status — independent of the prompt confusion (G5).

**Evidence:**

*Prompt 4:* `"Please find out inactive suppliers for Lee Supplies in Jan 2022"`
- Agent: *"I cannot fulfill this request. The available tools do not
  have a concept of 'inactive suppliers' or a way to query for
  supplier activity in a specific past time frame."*
- Curl proof of quirk: `q=Status='INACTIVE'` returns HTTP 400.
- Curl proof status exists: in first 200 suppliers, distribution is
  ACTIVE: 198, INACTIVE: 2. Client-side filtering is viable.

---

### G3. Truncation honesty for unmigrated tools  `[open]  [medium]`

**Example prompts:**
- Any broad query against suppliers, purchase orders, or buyers.

**Status today:** Only `search_invoices` and `search_suppliers_by_country`
report truncation. The other three tools — `search_suppliers`,
`search_purchase_orders`, `get_buyer` — still return bare `list[dict]`
and can silently cap at 25.

**Gap:** Inconsistent honesty. A user asking "find suppliers with 'a'
in the name" might get 25 of hundreds and never know.

**Fix:** Migrate the remaining three tools to return `ToolResult`. Same
pattern as the migrated two. Each migration is ~30 lines + tests.
`get_buyer` is single-record so the migration is trivial
(`total_available` is always 0 or 1).

---

### G4. Aggregation queries  `[open]  [large]`

**Example prompts:**
- `"spend details by each supplier"`
- `"top 10 suppliers by spend for Lee Supplies in Jan 2022"`
- `"What's the total open PO value by buyer?"` (the `--intent prompt-5`
  case)

**Status today:** Track A asks a clarifying question; Design 3 fails
loudly with F1.

**Observation 2026-05-30:** Track A's behavior on aggregation prompts
is *better* than Design 3's. The LLM recognizes the request shape and
asks for narrowing. Design 3's planner just raises. Worth a follow-up:
the Design 3 planner should detect "this looks like aggregation" and
return a helpful error rather than F1.

**Gap:** No tool supports GROUP BY-style operations. Fusion REST itself
doesn't expose aggregation endpoints; the work would be client-side.

**Fix options (pick later):**

(a) **Add bounded aggregation tools.** E.g.,
`aggregate_invoices_by_supplier(date_range, top_n)` — explicit shape,
constrained inputs, returns ranked totals. Concrete, but each new
aggregation shape needs a new tool.

(b) **Generic aggregation tool.** Takes an entity, a group-by field, an
aggregate field, and an aggregation op. More flexible but a much
larger surface area to validate and constrain.

(c) **Defer with a clear "this is not what we do" framing.**
Aggregations are reporting-tool work; Spire focuses on
investigative/exploratory queries. The agent's current honest refusal
is consistent with this framing.

**Recommendation:** Option (a) — add specific aggregation tools as
real prompts demand them, rather than pre-building infrastructure.
Start with "spend by supplier in date range" since multiple prompts
hit that shape.

**Evidence:**

*Prompt 5:* `"spend details by each supplier"`
- Agent: *"I can provide spend details for a supplier, including
  invoices and purchase orders. What suppliers would you like me to
  search for?"*
- Honest narrowing question.

*Prompt 6:* `"top 10 suppliers by spend for Lee Supplies in Jan 2022"`
- Agent: *"I can't rank suppliers by spend. The available tools don't
  support that kind of aggregation."* Plus called out the logical
  confusion in the prompt itself.

---

### G5. Prompt-shape validation upstream of tool selection  `[open]  [medium]`

**Example prompts:**
- `"top 10 suppliers by spend for Lee Supplies in Jan 2022"` — "top
  suppliers *for* a specific supplier" is logically confused.
- `"Please find out inactive suppliers for Lee Supplies"` — "inactive
  *for* Lee" doesn't compose either.

**Status today:** The agent (Track A) catches this surprisingly well —
it called out the logical confusion explicitly. Design 3 has no such
check because intents are hand-built and don't pass through an intent
parser.

**Gap:** When the intent parser lands (the broader Phase C work in the
roadmap), it should validate prompt shape before constructing an
Intent — catch contradictions, missing entities, or relationships that
don't make sense.

**Fix:** Part of the eventual intent parser. Not a standalone change.
Flagged here so it's not forgotten when that work begins.

---

## Cross-prompt observations (2026-05-30 testing)

Across the six-prompt walkthrough, Track A behaved better than the 1/7
baseline suggests. No hallucinations, no fabricated answers, multiple
instances of catching prompt confusion and asking for narrowing. Worth
keeping in mind:

1. **The "1/7 baseline" was measured on one rubric.** Track A is
   reliably bad at *complete answers* on hard prompts. It's reliably
   good at *not making things up* on out-of-scope prompts.

2. **The agent's improvements likely come from two places**: the
   Step 4 system-prompt update (truncation disclosure) seems to also
   nudge it toward general honesty about tool limits, and Gemini 2.0
   Flash itself is conservative on aggregation refusals.

3. **Design 3 has a parallel weakness:** the planner refuses
   aggregation queries with F1 (loud error) instead of a helpful
   message. Track A handles these prompts more gracefully today. The
   eventual intent parser (Phase C) should match Track A's graceful
   refusal.

---

## Backlog summary

| ID | Gap                                      | Effort  | Status |
|----|------------------------------------------|---------|--------|
| G1 | Invoice date upper bound                 | small   | open   |
| G2 | Supplier status filter (client-side)     | small   | open   |
| G3 | Truncation for remaining 3 tools         | medium  | open   |
| G4 | Aggregation tools                        | large   | open   |
| G5 | Prompt-shape validation                  | medium  | open   |

Add new gaps to this list when they surface during prompt testing.
Move to `done` when the fix lands; don't delete — the history is
useful.
