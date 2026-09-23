# SPIRE — Session Handoff, 2026-09-23 (window 2)

**This file supersedes the previous 2026-09-23 handoff.** Same date, second
window. Window 1 closed PR #163 (F-011 / F-018 / F-019 cluster, three fixes
plus two sysprompt revisions). Window 2 opened and shipped F-046, F-047,
F-048 on branch `phase-2-fix-F046-F047-F048-date-filters`.

**Read this first.** Then `docs/AUDIT_AND_FIX.md` (the playbook), which
points to everything else.

---

## Where we are

**Branch:** `phase-2-fix-F046-F047-F048-date-filters` (pushed to origin).

**Base:** `86d108f` on `hardening-master`.

**Commits on branch (4):**

    0bdf26c  Adding new test prompts (16_date_filter_cluster.txt)
    b434539  F-048: vague-adjective recency defaults to a 3-month window
    78aaeb4  F-047: PO last-updated-date filters + guard-widening
    52e840f  F-046: Invoice relative-date filters + guard widening

**Test suite:** 1156 passed, 22 deselected.

**Pod:** `dabpqy`. `personas.yaml` and `IKS_FUSION_BASE_URL` both point
there. Same as window 1.

---

## What shipped this window

- **F-046** — Invoice relative-date filters. Two new KG rows
  (`older_than_n_months` → `invoice_date_before`; `created_in_last_n_months`
  → `invoice_date_after`). Sysprompt edits to `b_invoice_date` (new rules)
  and `b_invoices_for_supplier` (the "MUST include supplier" clause was
  scoped to the supplier-shaped query — pre-fix it blocked date-only
  Invoice queries). Byte-equality literal in `context_assembly.py` mirrors
  both. Invoice guard widened to accept date filters as valid root refs,
  which also closes a pre-existing wrong-refusal on absolute-date Invoice
  queries ("invoices in 2024" refused before this branch).
  `kg_entity_filter` 30 → 32.

- **F-047** — PO LastUpdateDate filters. Two new KG rows on the
  LastUpdateDate column (`updated_older_than_n_months` → `last_updated_before`;
  `updated_in_last_n_months` → `last_updated_after`), mirroring F-011b's
  CreationDate split. `b_po_created_date.sysprompt`'s F-011c "set
  unanswerable" carve-out was replaced with two routing rules. Byte-equality
  literal mirrors. `_build_entity_fetcher_args` tuple widened.
  `search_purchase_orders` gains `last_updated_before` /
  `last_updated_after` args; sends `q=LastUpdateDate < '...'` or
  `q=LastUpdateDate >= '...'` server-side; matches client-side as a
  defence; projects `LastUpdateDate`. `server.py` wrapper forwards.
  `kg_entity_filter` 32 → 34.

- **F-048** — Vague-adjective recency defaults to a 3-month window.
  Sysprompt-only. `recent` / `new` / `latest` / `fresh` / `the most recent`
  / `recently created` — where the adjective names recency but gives no
  explicit N — emits `created_in_last_n_months: {"months": 3}` rather than
  refusing. Byte-equality literal mirrors.

- **New prompt set:** `scripts/prompts/16_date_filter_cluster.txt` — ~44
  prompts targeting the three findings, sectioned by direction (older /
  recent / absolute / composite / negative) with cross-column controls.

---

## Outstanding — V9 is the last item before the PR

V9 completed this window — PASS. Evidence at `docs/phase-2/fixes/F-046-F047-F048-v9-sweep.txt`; analysis at `docs/phase-2/fixes/F-046-F047-F048-v9-analysis.md`. The
equivalent of V9 for this branch is a **targeted four-file run**, not the
12-set manifest. The three sysprompt files edited on this branch are:

    src/spire/nl_parser/context/payables/b_invoice_date.sysprompt        (F-046 site 2a)
    src/spire/nl_parser/context/payables/b_invoices_for_supplier.sysprompt (F-046 site 2b)
    src/spire/nl_parser/context/procurement/b_po_created_date.sysprompt  (F-047 + F-048)

Command:

    python scripts/promptkit.py --run \
      --prompt-file \
        scripts/prompts/15_po_relative_date_filters.txt \
        scripts/prompts/16_date_filter_cluster.txt \
        scripts/prompts/13_child_as_root.txt \
        scripts/prompts/14_truncation_narration.txt \
      --show-planner > t_v9.txt 2>&1

Pass criteria:

    unsupported_filter count  == 0   (baseline after F-011b)
    MAX_TOKENS count          == 0   (parser prompt token ceiling)
    ERROR count               == 0
    All F-046 / F-047 / F-048 prompts answer
      (except the two bare negatives — "invoices", "purchase orders",
       which must refuse with missing_identifier)

If `t_v9.txt` exists and completes clean, that is V9 evidence. Bump the
three FIX_PLAN rows from `fixed` → `verified`, open the PR with the
FIX_PLAN §11.2 template, merge to `hardening-master`.

If V9 shows any `unsupported_filter` count > 0, the regression is in one
of the three sysprompt files — the intent lines in `t_v9.txt` will name
the exact prompt.

---

## First steps in the new window

1. `git log --oneline -5` — expect `0bdf26c` or later at HEAD.
2. `git status` — expect clean.
3. `pytest -q` — expect 1156 passed, 22 deselected.
4. V9 done. Two findings from the sweep: F-049 filed (open); F-045 unaffected.
   If absent, run the V9 command above.

---

## What to watch — two operational notes

- **MCP server restart after tool signature changes.** F-047 added two
  args to `search_purchase_orders` and its wrapper. The running MCP server
  must be re-started (`spire`) after such edits — otherwise the old
  in-memory signatures reject the new kwargs at call time. This cost a
  session mid-window; it is a known caveat and matches the handoff's own
  "Restart the MCP server after any change under
  `src/spire/mcp_server/`" rule.

- **Terminal shell exits in WSL.** The terminal occasionally exits with
  code 120 after long-running commands, showing
  `Failed to mount F:\` from dmesg. It is environmental (WSL mount), not
  the repo or the scripts. Workaround that held all window: redirect long
  runs to a file (`python ... > t.txt 2>&1`) so the output survives the
  exit.

---

## Open work, in FIX_PLAN order

Shipped this window: F-046, F-047, F-048.

Next in §4 order:

- **Cluster 2 (projection).** F-017, F-027, F-014, F-021 — all four share
  fix sites in `_FIELDS_SATISFIED_BY_INCLUDE` and `_project_outputs`.
  One branch, four commits. **Recommended next window.**
- **F-016** — no schema field for a plain-list row cap; "top 5" on a
  list query is dropped.
- **F-003 / F-004** — three PO aggregation ops unreachable from a scoped
  parse (`modes/` folder in neither `_TIER1` nor `KNOWN_MODULES`).
- **F-045** — composite `created_since AND created_before` on
  `/purchaseOrders` returns 0 with a misleading capped note.
- **Reg #30** — `Compare ordered vs invoiced for our top 3 suppliers`
  pages all POs before narrowing (perf).

---

## Commit hashes for reference

    52e840f  F-046
    78aaeb4  F-047
    b434539  F-048
    0bdf26c  Adding new test prompts (16_date_filter_cluster.txt)
