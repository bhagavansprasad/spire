# SPIRE — Session Handoff, 2026-09-23 (window 5)

**This file supersedes the previous 2026-09-23 handoff.** Same date,
fifth window. Window 4 closed PR #165 — Cluster 2 (projection) — and
reclassified F-021 to F-051. Cluster 2 is merged into
`hardening-master`; this window starts the remaining Phase 2 queue.

**Read this first.** Then `docs/AUDIT_AND_FIX.md` (the playbook), which
points to everything else.

---

## Where we are

**Branch:** `hardening-master` at `8510ddd` (the merge of PR #165).

**Test suite:** 1181 passed, 22 deselected (verify at window open).

**Pod:** `dabpqy`.

**Ledger state — FIX_PLAN §5:**

- `verified | #165 | 2026-09-23`: F-017, F-027, F-014.
- `closed-as-reclassified | #165 | 2026-09-23`: F-021.
- `not-started`: F-016, F-003, F-004, F-045, F-049, F-050, F-051,
  Reg #30.

**Everything before Cluster 2 shipped under earlier windows:** F-002,
F-006–F-015, F-018–F-020, F-033, F-036, F-039, F-041, F-043–F-044,
F-046–F-048, and the closed-as-not-a-bug family (F-013, F-022–F-026,
F-028–F-031, F-042). Full ledger in FIX_PLAN §5.

---

## What shipped in window 4

- **Cluster 2 (projection) merged as PR #165** — three fixes plus one
  reclassification:
  - **F-017** (`44a08f5`) — child-entity fields resolve against the
    include's KG catalog.
  - **F-027** (`94ad1f5`) — "country" column on Supplier queries;
    post-parse correction + display extraction. Sysprompt half
    deferred to F-050.
  - **F-014** (`8b0d4de`) — aggregate / compare intents carry no
    projected fields.
  - **F-021** reclassified to F-051 — both recorded fix sites work;
    the defect is in the caller's `summary_only` gate.
- **F-050 filed** — `columns/` parser-context blocks unreachable under
  the router.
- **F-051 filed** — the caller's `summary_only` gate drops child
  content on fields-plus-include intents. Three caller sites.
- **WORKING_STYLE rules 15.1 and 15.2 added** — full-output capture
  for repeatable runs; name a slow command's cost before the user runs
  it.

---

## Outstanding — remaining Phase 2 queue

Seven items. Order below reflects severity (wrong-data > crash >
missing-capability > cosmetic) per FIX_PLAN §8.3.1, with same-fix-site
items grouped.

1. **F-051** — `fields` + `include` intent: the caller's `summary_only`
   gate drops child content. Three sites (`promptkit.py:437`,
   `run_prompt_set.py:227`, `run_graph.py:194`). Fix options in the
   F-051 entry: extend the gate condition, or factor the branch into a
   shared helper. Small; new finding; fix-site confirmed by
   reproduction.

2. **F-016** — plain-list row cap missing ("top 5" on a list query is
   dropped). Schema-gap; small.

3. **F-003 + F-004 + F-050** — one branch, `context_assembly.py`
   `_TIER1` reachability. F-050 is confirmed; F-003 (`modes/`) is the
   same class; F-004 may fall out of F-003. Largest single lever
   remaining in Phase 2.

4. **Reg #30** — compare path pages all POs before narrowing (perf,
   may slip to Phase 6 if architectural).

5. **F-045** — composite `created_since AND created_before` on
   `/purchaseOrders` returns 0 with a misleading capped note
   (wrong-data).

6. **F-049** — "invoices created before/since X" refusal
   (sysprompt-only; could be a warm-up anytime).

**Recommendation for window 5.** Two small items are ready: **F-051**
(fix-site known, three sites, one-line gate change or shared helper)
and **F-016** (schema-gap, small). Either is a clean window. The
reachability branch (F-003 + F-004 + F-050) is the bigger win and
could be run instead if you'd rather tackle the largest remaining
lever while context is fresh.

---

## First steps in the new window

1. `git checkout hardening-master && git pull`
2. `git log --oneline -3` — expect `8510ddd` at HEAD.
3. `git status` — expect clean tree.
4. `pytest -q` — expect 1181 passed, 22 deselected.
5. Open `docs/phase-2/FIX_PLAN.md` §5. Pick the next `not-started` row
   in §4 order, or follow the recommendation above.

---

## What to watch — operational notes

- **Slow commands cost minutes.** Rule 15.2. Aggregate prompts and
  `suppliers with open purchase orders` walk ~13k records across many
  pages. Expect 2–4 minutes. Unit tests are the cheap evidence for
  deterministic fixes.

- **Full-output capture first.** Rule 15.1. Redirect complete stdout
  AND stderr to a file, then grep. Never pipe the run through a filter.

- **`parse()` vs `route_and_parse()`.** The direct call loads the full
  preamble; the router loads a scoped subset. A pipeline bug must be
  reproduced through the pipeline (`promptkit --run --show-planner`),
  not through `parse()`.

- **MCP server restart after tool signature changes.** Any edit under
  `src/spire/mcp_server/` requires `spire` restart before the new
  signature is live.

- **Terminal shell exits in WSL.** Environmental. Redirect long runs to
  a file so the output survives.

---

## Commit hashes for reference (window 4)

    44a08f5  F-017
    c679e1b  Cluster 2 — F-027 sweep capture + F-050 filing
    d9f18a8  WORKING_STYLE 15.1
    94ad1f5  F-027
    c5f228d  WORKING_STYLE 15.2
    8b0d4de  F-014
    0edd467  F-027 fix-file amendment
    5227056  Removing unwanted file (t_f027_v8.txt)
    a08c3eb  Cluster 2 close-out docs
    9693d94  F-021 reclassified to F-051 (branch tip)
    8510ddd  Merge pull request #165 (hardening-master tip)
