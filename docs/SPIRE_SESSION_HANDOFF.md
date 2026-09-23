# SPIRE — Session Handoff, 2026-09-23 (window 3)

**This file supersedes the previous 2026-09-23 handoff.** Same date,
third window. Windows 1 and 2 both closed work today: Window 1 closed
PR #163 (F-011 / F-018 / F-019 cluster). Window 2 shipped F-046, F-047,
F-048 on branch `phase-2-fix-F046-F047-F048-date-filters` and raised
PR #164. This window's job is to merge #164, then start Cluster 2.

**Read this first.** Then `docs/AUDIT_AND_FIX.md` (the playbook), which
points to everything else.

---

## Where we are

**Branch:** `phase-2-fix-F046-F047-F048-date-filters` — PR #164 open,
ready to merge to `hardening-master`.

**Base:** `hardening-master`.

**Commits on branch (6):**

    e7e0de7  context_bundles.yaml: add V9 sweep + analysis
    bf08f2d  V9: F-046/47/48 verified; F-049 filed (absolute-date "created" gap)
    8c9f5a5  Updating bundles
    774ee35  Session handoff 2026-09-23 (window 2)
    0bdf26c  Adding new test prompts
    b434539  F-048: vague-adjective recency defaults to a 3-month window
    78aaeb4  F-047: PO last-updated-date filters + guard-widening
    52e840f  F-046: Invoice relative-date filters + guard widening

**Test suite:** 1156 passed, 22 deselected.

**Pod:** `dabpqy`. `personas.yaml` and `IKS_FUSION_BASE_URL` both point
there.

**Ledger state:** F-046, F-047, F-048 rows in FIX_PLAN §5 are
`verified | #164 | 2026-09-23`. F-049 is `not-started | — | 2026-09-23`.

---

## What shipped this window

- **F-046** — Invoice relative-date filters. Two new KG rows
  (`older_than_n_months` → `invoice_date_before`; `created_in_last_n_months`
  → `invoice_date_after`). Sysprompt edits to `b_invoice_date` (new rules)
  and `b_invoices_for_supplier` (the "MUST include supplier" clause was
  scoped to the supplier-shaped query — pre-fix it blocked date-only
  Invoice queries). Byte-equality literal in `context_assembly.py` mirrors
  both. Invoice guard in `planner.py` widened to accept date filters as
  valid root refs, which also closes a pre-existing wrong-refusal on
  absolute-date Invoice queries ("invoices in 2024" refused before this
  branch). `kg_entity_filter` 30 → 32.

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

- **F-049 filed** — "invoices created before/since X" refuses with
  `missing_identifier`. Not fixed on this branch. Cluster 4, sysprompt-only.
  See `docs/audit/findings-log.md` F-049.

- **V9 evidence** — four-file targeted sweep. Zero `unsupported_filter`,
  zero `ERROR`, every F-046/047/048 prompt answered or refused correctly.
  Raw: `docs/phase-2/fixes/F-046-F047-F048-v9-sweep.txt`. Analysis:
  `docs/phase-2/fixes/F-046-F047-F048-v9-analysis.md`.

---

## Outstanding — merge PR #164

Everything on the branch is verified and tracked. The only remaining
step for this window's work is to merge PR #164 to `hardening-master`.

No further code, tests, or doc edits are pending on this branch. The
lockstep updates are all in place:

- FIX_PLAN §5: F-046/47/48 `verified | #164 | 2026-09-23`.
- findings-log: F-046/47/48 carry `**Update 2026-09-23 — verified on ...**`
  blocks; F-049 has its own entry.
- phase-1-audit §B.6: B-29/B-30/B-31 map to F-046/47/48, `verified 2026-09-23`.

After merge, the FIX_PLAN rows stay `verified` — the playbook only flips
to `closed` if the row's terminology distinguishes `verified` (V-standard
passed, PR merged) from `closed` (audit row updated, ledger frozen).
The FIX_PLAN §5 heading says: "verified — V-standard (§6) passed, PR
merged." So `verified` is terminal for this row; no further flip needed.

---

## First steps in the new window

1. `git log --oneline -5` — expect `e7e0de7` at HEAD while PR #164 is
   unmerged; after merge, expect the merge commit at HEAD on
   `hardening-master`.
2. `git status` — expect clean.
3. If PR #164 is not yet merged:
   - `gh pr view 164 --json state,mergeable,statusCheckRollup`
   - If `state=MERGEABLE` and checks green: `gh pr merge 164 --merge`.
   - If checks red: read the failure, address, re-push.
4. After merge: `git checkout hardening-master && git pull`.
5. `pytest -q` — expect 1156 passed, 22 deselected (or the baseline
   after any concurrent merges).
6. Open FIX_PLAN §5. Next unstarted row in §4 order is **F-017**
   (Cluster 2, projection cluster).

---

## What to watch — two operational notes

- **MCP server restart after tool signature changes.** F-047 added two
  args to `search_purchase_orders` and its wrapper. Any running MCP
  server must be re-started (`spire`) after such edits — otherwise the
  old in-memory signatures reject the new kwargs at call time. This cost
  a session mid-window; it is a known caveat and matches the handoff's own
  "Restart the MCP server after any change under
  `src/spire/mcp_server/`" rule.

- **Terminal shell exits in WSL.** The terminal occasionally exits with
  code 120 after long-running commands, showing `Failed to mount F:\`
  from dmesg. It is environmental (WSL mount), not the repo or the
  scripts. Workaround that held all window: redirect long runs to a file
  (`python ... > t.txt 2>&1`) so the output survives the exit.

- **The V9 sweep stdout/stderr trap.** The V9 command in the previous
  handoff placed `> t_all.txt 2>&1` before `--show-planner`, so
  `--show-planner` diagnostics went to the terminal, not the file. The
  file carries answers and refusals only. `MAX_TOKENS` markers were on
  stderr and were not captured — the analysis reasoned from the fact that
  every answer is a complete, coherent summary (incompatible with
  degenerate generation). Correct invocation for future runs: put all
  flags before the redirect: `python scripts/promptkit.py --run
  --prompt-file FILE --show-planner > t.txt 2>&1`.

---

## Next window — Cluster 2 (projection cluster)

Per FIX_PLAN §4 step 5, the next work is Cluster 2. One branch, four
commits, in this order:

    F-017 → F-027 → F-014 → F-021

- **F-017** — `_FIELDS_SATISFIED_BY_INCLUDE` checks only the target
  entity's catalog; child-entity fields dropped as unresolved. Site:
  `nl_parser/intent_validation.py`. Do first — retires the manual map
  F-027 assumes.

- **F-027** — "country" column request routed to Address include; display
  renders full blob. Site: `intent_validation.py` + parser sysprompt.
  Shares site with F-017.

- **F-014** — `fields` on an aggregate intent applied to the wrapper
  record; em-dash columns. Site: `graph/pipeline.py`.

- **F-021** — DFF child fetched but never rendered. Site:
  `synthesizer/synthesizer.py` + `rendering/formatters.py`.
  Display-side mechanism unresolved until this branch reads the
  rendering file.

One `--validate` (V9) run at the end of the branch covers the whole
cluster if any sysprompt edits land.

Branch name: `phase-2-fix-F017-F027-F014-F021-projection-cluster`.

---

## Open work, in FIX_PLAN order

Shipped this window: F-046, F-047, F-048 (PR #164).

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
- **F-049** — wrong-refusal on "invoices created before/since X"
  (new this window; cluster 4; sysprompt-only).

---

## Commit hashes for reference

    52e840f  F-046
    78aaeb4  F-047
    b434539  F-048
    0bdf26c  Adding new test prompts (16_date_filter_cluster.txt)
    774ee35  Session handoff 2026-09-23 (window 2)
    8c9f5a5  Updating bundles
    bf08f2d  V9: F-046/47/48 verified; F-049 filed
    e7e0de7  context_bundles.yaml: add V9 sweep + analysis (HEAD)
