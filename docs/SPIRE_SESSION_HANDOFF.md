# Spire — Window Handoff (2026-07-28)

Paste this into the new window to continue. It captures what this session
did and where the next one picks up.

---

## Who / what

Continuing **Spire** — the AI-native NL query system over Oracle Fusion
Cloud (P2P + AR). Deterministic KG pipeline: parse → plan → execute →
synthesize. Repo `github.com/bhagavansprasad/spire`, working dir
`~/pocs/spire`, pod `fa-esll-dev37-...`, creds in `personas.yaml`.

## Working style (enforce these)

- Short responses, one step at a time, interactive.
- Ask permission before generating code or significant content.
- Offer numbered options with a recommendation and why.
- Re-share the current full file before editing — never work from a stale
  copy; never deliver a patch/diff, always the COMPLETE updated file.
- One command at a time, verified before the next.
- Output to `t.txt` (`>` overwrite, `>>` append).
- Git: one branch per change, PR-based, named `git add` (never `-A`
  except bulk doc moves), heredoc commit messages. Docs-only → straight to
  master.
- **Curl the pod before changing code.** Every fix that stuck this session
  started with a curl; every theory-first attempt got reverted.

## Build sequence for a new phase

curl discovery → standalone tool → KG rows → planner → parser → server
wrapper → synthesizer → run display → prompt set → tests → verify E2E →
branch/PR/merge. The two most-skipped steps that keep biting: the server
wrapper and the display formatter.

---

## What this session shipped (all merged to master)

1. **Column-output feature.** When a prompt names columns, the output is
   an aligned table of exactly those columns, in order, with the
   synthesizer summary above it. `intent.fields` non-empty → table; empty
   → old typed path unchanged. Aggregation unaffected (its `fields` is
   empty). Tag `v1.3` marks this.

2. **Address column.** Nested `addresses` flatten to a one-line Address
   column when present (keys are PascalCase: `FormattedAddress`, `City`,
   `State`, `Country`). Self-gating — only fires when address data is on
   the rows.

3. **Graceful degradation.** When the synthesizer overruns the token cap
   (`DegenerateOutputError`) on a column query, the run no longer aborts:
   it's caught in `synthesize_node` (returns `synth_failed`, not `error`),
   the summary is skipped, and the table prints alone.

4. **`run_plan.py` retired.** Formatters moved to
   `scripts/display_formatters.py`; `run_graph.py` and `run_prompt_set.py`
   both import from there. `run_plan.py` deleted.

5. **Prompt sets updated.** `04_columns.txt` flipped from failure-capture
   to verification; `07_alacarte.txt` added as the column-feature
   regression set (12 prompts, verified 12/12 clean). README updated.

6. **Docs consolidated.** `feature_roadmap` + `spire_expansion_plan` +
   `spire_lifecycle_goal` merged into `docs/spire_plan.md` (forward-looking;
   done phases compressed to tables, all pod quirks / parser-runaway
   findings / lifecycle goal / endpoints catalog kept verbatim). Six
   superseded docs moved to `docs/archive/`. `context_bundles.yaml`
   updated (new `prompts` bundle; `root` lists only live docs; scripts
   cleaned).

## Branches / tags right now

- `master` — clean, all the above merged.
- `v1.3` — tag: column feature baseline.
- `v1.2` — tag: KG expansion complete.
- `pre-lifecycle` — branch: permanent bookmark of master before lifecycle
  work.
- `lifecycle-poc` — branch: **currently checked out, empty, where
  lifecycle work begins.**

---

## The next task: lifecycle PoC

The goal (full detail in `docs/spire_plan.md`, "The lifecycle goal"
section): Spire answers **the state of a business object across its full
lifecycle** — assembling documents across systems, reconciling amounts,
detecting exceptions, naming who must act. P2P first; O2C is the same
shape later.

**Why a PoC first:** it's the architecture test. If Spire can produce even
ONE lifecycle prompt as anticipated, the design holds and the rest is more
of the same. If it can't, that's worth knowing before building more.

**Recommended PoC target: Shape C (status matrix).** Per the gap analysis
it's the closest to reachable (~70%) — PO, lines, schedules, and
received/billed quantities are already wired. It proves the
assembly-and-reconcile capability WITHOUT waiting on the endpoints Spire
has never confirmed (holds, payments, approvals — all "needs curl").

**First steps, in order (NO code yet):**
1. **Pick the test PO.** ~1% of invoices on this pod carry a PO number, so
   most POs have no linked invoices. The PoC needs a deliberately chosen PO
   with a full chain (received + invoiced, ideally paid) — not an arbitrary
   one. PO 2144 is Closed with 2 lines and may not exercise the
   interesting cases.
2. **Curl that PO's chain** — header, lines, schedules with
   `ReceivedQuantity`/`ReceivedAmount`/`BilledQuantity`/`BilledAmount`.
   Confirm the reconciliation fields are actually populated.
3. Then design the PoC scope (which reconciliation it proves) and build.

**Known constraint from the gap analysis:** the three receiving resources
(`receivingTransactions`, `receivingReceipts`, `receivingReceiptRequests`)
all failed on 2026-07-17 (403 / 400 / staging). Received qty+amount survive
via `purchaseOrderSchedules`, so reconciliation works, but receipt
NUMBERS and DATES aren't obtainable. The 403 is a role permission — worth
re-testing with a different persona before accepting it as permanent.

---

## Open issues carried forward (not lifecycle, still real)

From the executive summary's 103-prompt run — the synthesizer-narration
defects are separate from the column work and mostly untouched:
- Page size stated as total ("25 suppliers" where 421 exist).
- Narration asserts fields not in the displayed output (paid/unpaid,
  open/closed) — several prompts.
- `count_only` and `open_only` parsed but not applied by the planner.
- Credit-memo total mixes currencies and includes a positive row.
- `pytest` NOT run since the executor signature changed (2→3 returns) —
  highest-risk unknown. **Bhagavan deferred this to after lifecycle work**,
  but it's still outstanding; `test_executor.py` likely asserts the old
  shape.
- KG tripwire drift: `kg_entity_tool` 10 vs 9, `kg_entity_filter` 25 vs 23
  — bump in both `print_kg.py` and `tests/test_kg_metadata.py`.

## Coupled optimisation (noted, not urgent)

Column-only supplier queries still run the synthesizer just to discard an
overrun result (~25K wasted tokens on the address query). Once
reconciliation/lifecycle settles, consider skipping the synthesize node
for column-only queries.

## Files to share when the new window starts a task

`docs/spire_plan.md`, `docs/spire_fusion_endpoints_reference.md`, this
handoff, plus whichever of the code files the task touches (planner,
synthesizer, server, the relevant tool). Always re-share before editing.
