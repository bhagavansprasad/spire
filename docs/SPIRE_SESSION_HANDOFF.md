# SPIRE — Session Handoff, 2026-09-23 (window 4)

**This file supersedes the previous 2026-09-23 handoff.** Same date,
fourth window. Window 3 closed PR #164 (F-046 / F-047 / F-048), opened
Cluster 2, and shipped F-017 / F-027 / F-014. F-021 was reclassified to
F-051 during window 4; the branch is now complete and ready for PR.

**Read this first.** Then `docs/AUDIT_AND_FIX.md` (the playbook), which
points to everything else.

---

## Where we are

**Branch:** `phase-2-fix-F017-F027-F014-F021-projection-cluster` —
pushed to origin, 6 commits ahead of the base.

**Base:** `4cb8fee` on `hardening-master` (the merge of PR #164).

**Commits on branch (6):**

    0edd467  F-027: fix file — record that the N=20 raw output is not committed
    8b0d4de  F-014: aggregate / compare intents carry no projected fields
    c5f228d  WORKING_STYLE: add rule 15.2, name a slow command's cost before the run
    94ad1f5  F-027: "country" column request on Supplier queries converges both shapes
    d9f18a8  WORKING_STYLE: add rule 15.1, full-output capture for repeatable runs
    c679e1b  Cluster 2 — capture F-027 N=20 sweep and file F-050
    44a08f5  F-017: child-entity fields resolve against the include's KG catalog

**Test suite:** 1181 passed, 22 deselected.

**Pod:** `dabpqy`.

**Ledger state:** F-017, F-027, F-014 rows in FIX_PLAN §5 are `fixed |
— | 2026-09-23`. New row F-050 added (`not-started`). F-021 remains
`not-started`.

---

## What shipped this window

- **F-017** — child-entity fields resolve against the include's KG
  catalog. `nl_parser/intent_validation.py::validate_intent`, Step 4
  field-split now checks per column: target catalog first (so a
  doubly-present column like `OrderNumber` stays in `fields`), then
  the curated `_FIELDS_SATISFIED_BY_INCLUDE` map, then the KG catalog
  of every include. Fix file `docs/phase-2/fixes/F-017.md`.

- **F-027** — "country" column on Supplier queries. Post-parse
  correction in `parser.py` plus display extraction in
  `formatters.py::_format_projected_table`. The sysprompt half is
  deferred to F-050. N=20 sweep pre-fix: 16/20 blob, 4/20
  false-unresolved, 0/20 correct; post-fix 20/20. Fix file
  `docs/phase-2/fixes/F-027.md`.

- **F-014** — aggregate / compare intents carry no projected fields.
  Post-parse correction in `parser.py` clears `intent.fields` when
  `aggregate` or `compare` is set; `graph/pipeline.py::_project_outputs`
  skips shape-wrapper buckets. Fix file `docs/phase-2/fixes/F-014.md`.

- **F-050 filed** — `columns/` parser-context blocks unreachable from
  router-scoped parses. Same class as F-003 / C-06. Fix is a one-line
  addition to `_TIER1` in `context_assembly.py`; rides the F-003 /
  F-004 branch.

- **Two process rules added** to `docs/spire-robustness/WORKING_STYLE.md`:
  15.1 (full-output capture for repeatable runs) and 15.2 (name a slow
  command's cost before the user runs it).

---

## Outstanding — branch ready for PR

F-021 was **reclassified**, not fixed. Reproduced with the finding's
own prompt 2026-09-23; both of its recorded fix sites work. The DFF
child was fetched, the synthesizer built a `ReceivablesInvoiceResponse`
carrying it, and the display would have rendered it — if it were
called. The defect is one layer up, in the caller: the branch at
`scripts/promptkit.py:437` (and two identical copies at
`run_prompt_set.py:227` and `run_graph.py:194`) chooses
`_format_synthesized(response, summary_only=True)` whenever the intent
carries `fields`, and a fields-plus-include intent then prints a blank
`Answer:` block plus the projected parent table, never the child.

The F-021 headline symptom is a single instance of a broader defect:
**the caller's summary_only gate drops child content whenever `fields`
is present**, even though the child lives only in the synthesized
response. Filed as **F-051** (open, `not-started`).

Cluster 2 therefore closes with **three fixes and one
reclassification**. The branch is complete: F-017, F-027, F-014
shipped as commits `44a08f5`, `94ad1f5`, `8b0d4de`; F-021 reclassified
to F-051 with no code change.

**Next action: open the PR.** No further commits pending on this
branch. V9 decision: no `.sysprompt` file was touched (F-027's
deferred sysprompt half did not land), so a full 12-set `--validate`
is not required by the V-standard. The three prompts in
`docs/audit/golden/` are unchanged (verified per-fix as V5). PR body
should summarise: three projection-cluster fixes; two process rules
added (WORKING_STYLE 15.1, 15.2); two findings filed (F-050, F-051);
one reclassification (F-021).

---

## First steps in the new window

1. `git log --oneline -3` — expect `0edd467` at HEAD.
2. `git status` — expect clean tree.
3. `pytest -q` — expect 1181 passed, 22 deselected.
4. Reproduce F-021:

       python scripts/promptkit.py --run \
         --prompt "Show the AR invoice with CustomerTransactionId 1002 with transaction number and flexfield" \
         --show-planner --show-synthesizer > t_f021_v1.txt 2>&1

   Then grep the full file (rule 15.1) for the shape decision:
   `grep -nE '^Intent:|^  include:|^  fields:|^Outputs:|receivablesinvoicetransactiondff|__FLEX_Context|^Answer:|DFF|shape =' t_f021_v1.txt`

5. Open `docs/phase-2/fixes/F-021.md` from the §11.1 template and start.

---

## What to watch — operational notes

- **Slow commands cost minutes.** Rule 15.2 exists because the F-014
  reproducer walked ~13k invoices across 26 pages with no warning.
  Before running any aggregate or `suppliers with open purchase orders`
  prompt, expect 2-4 minutes. Unit tests are the cheap evidence for
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

## Remaining queue after Cluster 2 merges

Per FIX_PLAN §4 order, with F-050 slotted beside F-003 / F-004 (same
`context_assembly.py::_TIER1` fix site):

1. **F-016** — plain-list row cap missing ("top 5" dropped). Schema-gap,
   small.
2. **F-003 + F-004 + F-050** — one branch, `_TIER1` reachability.
   F-004 may fall out of F-003.
3. **Reg #30** — compare path pages all POs before narrowing (perf,
   may slip to Phase 6 if architectural).
4. **F-045** — composite date silent-zero on `/purchaseOrders`.
5. **F-049** — "invoices created before/since X" refusal
   (sysprompt-only; could be a warm-up anytime).

Recommended next branch after Cluster 2 merges:
`phase-2-fix-F003-F004-F050-context-reachability`.

---

## Commit hashes for reference

    44a08f5  F-017
    c679e1b  Cluster 2 — F-027 sweep capture + F-050 filing
    d9f18a8  WORKING_STYLE 15.1
    94ad1f5  F-027
    c5f228d  WORKING_STYLE 15.2
    8b0d4de  F-014
    0edd467  F-027 fix-file amendment (HEAD)
    5227056  Removing unwanted file (t_f027_v8.txt)
