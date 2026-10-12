# SPIRE — window-35 handoff

**Window type:** implementation. Eight commits + one merge landed on the
round-one integration branch `hardening-master-v3`. No new F-NNN was
filed; two residuals are recorded below as follow-ups, not as findings.
**Predecessor:** the window-34 handoff (Invoice status investigation).
Its findings live on in `docs/design/INVOICE_STATUS_ACCEPTANCE.md` and the
endpoints reference's 2026-10-09 rows; this document supersedes it as the
current anchor.
**Branch arrangement:**
- `master` is **frozen at `00a5176`** for the duration of round one.
- `hardening-master-v3` is the **round-one integration branch**. Feature
  branches fork from it and PR into it.
- When round one completes, `hardening-master-v3` merges to `master`
  once, via PR.
**master tip:** `00a5176` (unchanged since before this window opened)
**hardening-master-v3 tip:** `2494911` (merge of PR #192)
**Successor:** the next window's handoff.

---

## 0. The rule that framed this window

WORKING_STYLE.md **Rule 28** (the SME test). If a Fusion SME could answer
a prompt with read access to Fusion, Spire must answer it; a refusal is a
defect. This window began from that frame and ended with all five of the
prompts in window-34 HANDOFF §1 answering.

---

## 1. The Rule 28 defect and its fix

The five prompts (window-34 HANDOFF §1, unchanged):

1. Which invoices are yet to be paid?
2. Which supplier invoices are currently outstanding?
3. Which invoices are still unpaid?
4. Are any supplier invoices overdue and requiring attention?
5. Which invoices have been pending for a long time?

Window 34 recorded all five refusing. Window 35 made all five answer:

| # | Intent emitted | Rows on `fa-euth-dev20` |
|---|---|---|
| 1 | `unpaid` | 9,563 |
| 2 | `unpaid` | 9,563 |
| 3 | `unpaid` | 9,563 |
| 4 | `overdue` | 9,503 |
| 5 | `pending` + `older_than_n_months={months:3}` | 6,789 |

**Zero refusals.**

The acceptance criterion — what a correct answer to each prompt must say —
lives in `docs/design/INVOICE_STATUS_ACCEPTANCE.md`.

---

## 2. What the fix required, layer by layer

Window 34's §2 named four layers; each one moved.

**Layer 1 — Parser vocabulary.** Three new filter types appear in the
parser's menu: `unpaid`, `overdue`, `pending`. They ride on the existing
`kg_entity_filter` mechanism; the parser's menu is generated from that
table, so no dedicated sysprompt block was needed for the filter *types*
themselves. A new block **was** needed to teach defaults — see Layer 4.

**Layer 2 — MCP tool.** `search_invoices` gained three boolean args
(`unpaid`, `overdue`, `pending`) and `DueDate` was added to its
`_PROJECTED_FIELDS`. Compound-filter paths (`unpaid + supplier`, `overdue`,
`pending + date`) page the server clause to exhaustion via the shared
`page_all` helper. `matches()` now checks `PaidStatus` and `ApprovalStatus`
client-side — the earlier version leaked Paid rows into `unpaid` answers
when a supplier clause took the server slot.

**Layer 3 — KG registry.** Three `kg_entity_filter` rows
(`Invoice/unpaid`, `Invoice/overdue`, `Invoice/pending`). No `kg_vocabulary`
kind was added — the term IS the filter type, and a vocab kind would have
meant editing the CHECK constraint in `scripts/sql/kg_schema.sql` plus the
four count-tracking sites the KG test names.

**Layer 4 — Parser context.** New block
`src/spire/nl_parser/context/payables/b_invoice_status.sysprompt`, added to
the manifest and (by the Phase 1 byte-equality invariant) mirrored into
`_SYSTEM_PROMPT_PREAMBLE`. It teaches:

- "pending" / "pending approval" -> `pending` alone.
- "pending for a long time" with no explicit N -> `pending` +
  `older_than_n_months={months:3}` (the default).
- "pending for over N months/days/weeks/years" -> `pending` +
  `older_than_n_months={months:N}`.
- "pending in the last N months" -> `pending` +
  `created_in_last_n_months={months:N}`.
- **A guard**: adjectives like "requiring attention", "urgent", "needing
  review" are NOT pending signals. This guard is load-bearing: without it
  the model added `pending` to prompt 4 ("overdue and requiring
  attention"), narrowing the answer silently.

The block count moved from 49 to 50; `_EXPECTED_BLOCK_COUNT` in
`tests/test_parser_context_assembly.py` moved with it.

**Layer 5 — Display.** No change. `DueDate` now reaches the projection, but
the formatter still renders Invoice / InvoiceId / Amount / Currency / Date
/ Supplier; the due-date column is available for a future prompt that asks
for it.

---

## 3. Where the changes live

Branch `feat/invoice-status-filters`, merged to `hardening-master-v3` as
PR #192 (merge commit `2494911`):

```
d2b8fa1 docs: register acceptance doc + invoice-status block in context bundles
00dac8c mcp(invoices): fix unpaid/overdue client filters; honest compound totals
712d82a nl_parser: narrow 'pending' triggers — adjectives are not approval signals
eaadc1c mcp(invoices): honest totals for unpaid (union) and overdue (unknown)
ba6a955 nl_parser: teach invoice-status defaults (pending for a long time)
a76eeec planner: accept unpaid/overdue/pending as Invoice roots
2a54747 test(invoices): add cases for unpaid/overdue/pending + DueDate projection
90158b2 mcp(invoices): add unpaid/overdue/pending filters + DueDate projection
e9846fb kg: register invoice_status filters (unpaid, overdue, pending)
```

Files changed:
- `scripts/sql/kg_schema.sql` — three rows, banner 34->37
- `scripts/print_kg.py`, `tests/test_kg_metadata.py` — count moves 34->37
- `src/spire/mcp_server/tools/invoices.py` — the tool
- `src/spire/mcp_server/server.py` — the MCP wrapper
- `src/spire/planner/planner.py` — the Invoice root guard
- `src/spire/nl_parser/context/payables/b_invoice_status.sysprompt` — new block
- `src/spire/nl_parser/context/order.manifest` — the new block, 49->50
- `src/spire/nl_parser/context_assembly.py` — the literal mirrored, block count
- `tests/test_parser_context_assembly.py` — block count 49->50
- `tests/test_invoices_tool.py`, `tests/test_planner.py` — new cases
- `context_bundles.yaml` — acceptance doc into `plan`, block into `parser_context`

---

## 4. Costs and disclosures the next window should know

**Paged-fetch cost.** Compound-filter queries now page the server clause to
exhaustion. On `fa-euth-dev20` this means:

- `overdue` alone: ~9,503 rows, ~20 pages, ~3-4 minutes.
- `pending + older_than_n_months`: ~6,789 rows, ~14 pages, ~3-4 minutes.
- `unpaid + supplier`: ~1,300 rows, 3 pages, seconds.

This is not a bug — an SME would take the same time to count 9,503 overdue
invoices — but it is a new UX cost on two of the five prompts. A future
window may want ">= N, exact count unavailable" as an alternative when a
caller would rather have a fast approximate answer. Not chosen here.

**Pod drift.** `unpaid` moved 9,551 -> 9,563 -> 9,564 -> 9,565 -> 9,563 across
sweeps in this window (~10s between calls). The pod's data moves; the
number is honest, not a defect. Do not read the variance as an
inconsistency.

**Truncation footer wording.** "N total in source" is the filtered total,
not the source total. Cosmetic; recorded as a follow-up, not filed.

**Prompt 4's narration.** The response is a plain table, not the verdict +
ranked list that `INVOICE_STATUS_ACCEPTANCE.md` §2.4 asks for. The query
answers (the Rule 28 bar), but the narration does not yet meet §2.4's
shape. Deferred.

**The two residual items above are not filed as F-NNNs.** The disposition
from this window: findings get filed when a fix window picks them up. A
future window that wants to work on either should file it as part of
picking it up.

---

## 5. What this window did NOT do

- **`paid` and `partially paid` filter rows.** Not named by any prompt.
  Deferred.
- **A block rule for "overdue" as a keyword.** §4.3's compound predicate is
  documented in `b_invoice_status.sysprompt`, but the block does not carry
  a dedicated "past due" / "behind on payment" rule. In practice the model
  routes it correctly (see §1's table). If a future phrasing refuses, the
  block is where the rule would go.
- **Fixing the "Show me the details of a supplier invoice" refusal.**
  Confirmed in this window as a legitimate refusal (Rule 28 does not apply;
  the prompt names no set). Not a defect.
- **The `open_only` / AR path.** Untouched. The KG row that said the flag
  was "unused" is stale — window 35's investigation found it wired. A
  future KG tidy-up should correct that row.
- **POC-2.** Still paused. The `all_tables` DB-reachability check for
  `localhost:1521/FREEPDB1` was never run.

---

## 6. Next window's picks

In order of what a resuming window would most likely want:

1. **The HANDOFF update itself.** This document is what a next window
   reads to know where it is. If it says the wrong thing, everything
   downstream is wrong. Check it against `git log hardening-master-v3`
   before starting new work.
2. **The two residuals (§4)** — decide whether to file them or leave them
   noted. If filing, they belong in `docs/fixes/FIXES.md` +
   `docs/fixes/FIX_PLAN.md`.
3. **The next prompt from round-one testing.** If the SME has found more
   prompts that refuse or return wrong data, those are the priority.
4. **The narration-quality work** for prompt 4's §2.4 shape — a
   synthesizer-side change, not a Rule 28 defect, but it is what the
   acceptance doc asks for.
5. **`DueDate` as a column.** The tool projects it now; the KG's `Invoice`
   field list does not carry it. A query like "show me the due dates for
   Lee Supplies' invoices" would name it in `fields` and the KG field-split
   would report it unresolved. One `kg_entity_field` row fixes it.

---

## 7. Files and prior reading

**Anchor docs:**
- `docs/design/INVOICE_STATUS_ACCEPTANCE.md` — the acceptance criterion and
  design shape for the five prompts. This window's authority on what is in
  scope.
- `docs/plan/WORKING_STYLE.md` — Rule 28 is the frame; Rule 15.3 is how
  every edit in this window was delivered.

**Evidence files (untracked, repo root):**
- `t_invoice_status_sweep.txt`, `t_invoice_status_sweep_final.txt`,
  `t_invoice_status_sweep_final2.txt` — the three sweeps.
- `t_pr192_gate.txt` — the ten-suite merge gate.
- `t_prompt4_rerun.txt` — the individual prompt-4 verification after the
  `pending`-trigger guard landed.
- `t_kg_rebuild.txt`, `t_kg_invoice_filters.txt`, `t_pod_check.txt` — the
  rebuild evidence.
- `prompts_ws35.txt` — the five prompts as a file.

**Key code paths, for the next window:**
- `src/spire/mcp_server/tools/invoices.py` — the tool; `search_invoices`,
  `matches()`, the paged-fetch branch.
- `src/spire/planner/planner.py` — the Invoice root guard (top of
  `generate_plan`).
- `src/spire/nl_parser/context/payables/b_invoice_status.sysprompt` — the
  new block.
- `src/spire/nl_parser/context_assembly.py` — the retained literal; block
  count.
- `scripts/sql/kg_schema.sql` — the three new `kg_entity_filter` rows.

---

*End of window-35 handoff.*