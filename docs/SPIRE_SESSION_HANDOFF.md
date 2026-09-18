
# SPIRE — Session Handoff, 2026-09-18

**This file supersedes the 2026-09-11 handoff.** The router / lifecycle-flip
work it teed up is DONE and merged. The current state is: Phase 1 audit
essentially complete, findings log through F-040, three small housekeeping
batches remaining.

**Read this first.** Then read `docs/audit/phase-1-audit.md` (the audit)
and `docs/audit/findings-log.md` (the log). This handoff is a launch
pad, not a document to maintain.

---

## What was done this session

The Phase 1 audit's §B was the primary work. Thirty-five findings were
written to the findings log (F-006 through F-040). Every §B row and §B.2
candidate now has an F-NNN. §D.1 is fully covered. §A is closed. §C, §E,
§F, §G were drafted from in-hand bundles. §H had four nondeterminism
observations closed.

Findings-log range: **F-001 through F-040.**

---

## The working process — four steps

The user and I worked in this loop for every entry. Continue it exactly.

**Step 1 — I name a command or a bundle.** For each finding under
investigation, I ask for one command to run (usually a
`promptkit.py --run --prompt "..." --show-stages` invocation or a `grep`)
or one bundle to share (`context_out/context_<bundle>.md`).

**Step 2 — User runs it, pastes the output.** One command at a time. No
batched commands unless they are clearly independent and stated as such.

**Step 3 — I generate the finding text.** I walk S0–S8 (see the evidence
standard below), name the mechanism with a `file:line` where possible,
disprove at least one alternative, name a falsifier, classify,
cross-ref, and list what was not checked.

**Step 4 — User search-and-replaces into the findings log.** I give the
finding as a `~~~`-fenced block plus a **single-line anchor** to search
for. The anchor is always:

```
## F-005 — `orderBy=Ordered:desc` silently ignored on `/purchaseOrders`
```

The user replaces that anchor with `[new finding block]\n\n---\n\n## F-005 — ...`
(the F-005 line stays). The new finding lands between the newest F-NNN
and F-005.

**Step 5 — User verifies with four commands.** After each paste:

```
grep -n "^## F-" docs/audit/findings-log.md
grep -c "^## F-005 — \`orderBy=Ordered:desc\` silently ignored on \`/purchaseOrders\`$" docs/audit/findings-log.md
sed -n '/^## F-005 —/,/^## F-004 —/p' docs/audit/findings-log.md | head -20
grep -c "^\*End of findings log\.\*$" docs/audit/findings-log.md
```

Expected: newest F-NNN appears between the previous newest and F-005;
anchor count is `1`; F-005 is intact; end-marker count is `1`.

**Step 6 — Audit file updates.** When a §D or §H row is closed, I give a
matching search-and-replace for `phase-1-audit.md` to add the closure
note. Same anchor discipline: single-line search, replace-with-block.

**Every finding ships with its verification commands.** Do not skip this.

---

## The evidence standard (S0–S8)

Non-negotiable. Every finding walks:

- **S0** — one-sentence claim.
- **S1** — the harm, picked from: wrong data, wrong narration, crash,
  refusal of an in-scope prompt, silent omission, cost regression,
  inconsistency between two paths. **No harm → stop.** Observation, not
  bug.
- **S2** — pasted evidence (curl-verified > runtime output > static code
  > recall; recall is not evidence).
- **S3** — mechanism, `file:line` where possible.
- **S4** — disprove one alternative.
- **S5** — name a falsifier.
- **S6** — classify (Confirmed / Candidate / Observation /
  Closed-as-not-a-bug).
- **S7** — cross-link (§A / §B / §D row, or another F-NNN).
- **S8** — list what was NOT checked.

Several findings this session closed at S1 (B-c3, B-12, B-18, D-03) —
**the S1 gate is real, use it**.

**Two `closed-as-not-a-bug` shapes.**

- **Nondeterminism cleared at N≥20.** Audit recorded an intermittent
  symptom; N=20 runs of the same prompt produce identical output. Re-open
  only if the same prompt starts varying again or the underlying
  fetch/aggregation tool changes.
- **Audit-time observation diverged.** Audit's recorded symptom does not
  appear at its own reproducer. Either the code changed (silently, or
  with a fix whose comment names the prompt) or the pod state changed.
  No git archaeology is done at closure time; the audit row stays as
  written; the finding records both the closure and the "not checked"
  clause about which side moved.

---

## The findings log's shape

Newest at top, directly below the header. Each entry:

```
## F-NNN — one-line title

**Date:** YYYY-MM-DD
**Status:** open · root-caused · fix-in-progress · fixed · closed-as-not-a-bug
**Cross-refs:** bug IDs from phase-1-audit.md

**Evidence.** Command run, output pasted. Copy-paste, not paraphrase.

**Root cause.** One paragraph. The mechanism.

**Fix location (for Phase 2).** Where the change goes, not the change.

**Not checked.** Explicit. What a future session reads to know where to look next.
```

Append-only. Corrections are new entries citing old IDs.

---

## The nested-fence rule

Nested ` ``` ` inside ` ``` ` breaks copy-paste in the user's terminal.
When a finding contains code fences (it usually does — the evidence
paste has its own fences), the outer wrapper must be `~~~`, not ` ``` `.
Same for this handoff file itself.

I got this wrong twice this session. The user had to ask for a re-emit
both times. Do not make the same mistake.

---

## Where the audit stands

**§A — Registry drift map.** Closed. Every row in §A.1 and §A.2 has a
state. Notable: A-16 (`po_status` untaught, `relationship_phrase` dead
KG rows) and A-20 (aggregate tools registered in code, not KG) are
`disagree`, with A-16 probed clean this session.

**§B — Bug inventory.** Closed. §B.6 is the audit-row-to-finding map.
Summary:
- Confirmed bugs written up: B-01→F-006, B-02→F-007, B-03→F-008,
  B-04→F-010, B-05→F-009, B-06→F-011, B-07→F-012, B-17→F-014,
  B-19→F-015, B-22→F-017, B-23→F-021, B-24→F-018, B-25→F-019,
  B-26→F-016, B-27→F-020.
- Cross-referenced into another finding: B-09→F-002, B-13→F-001,
  B-20→F-003/F-004.
- Closed-as-not-a-bug: B-10→F-022, B-11→F-013, B-12→F-026,
  B-15→F-025, B-16→F-028, B-18→F-029, B-21→F-023, B-c1→F-030,
  B-c2→F-024, B-c3→F-031.
- Folded: B-c4 → F-024 class note.

**§C — Dead code inventory.** Drafted (partial). C.1 confirmed orphans
(C-01 through C-07); C.2 candidates (C-08 through C-12); C.3 unreachable
(needs `tests` / `scripts` / `prompts` / `corpora` bundles). §C.5 has
five unrun confirmation greps for C-02 through C-07.

**§D — Inconsistency inventory.** Closed. D-01→F-032, D-02→F-034,
D-03→F-035, D-04→F-036, D-05→F-040, D-07→F-013 (cross), D-09→F-025
(cross), D-10→F-037, D-11→F-039, D-12→F-038, D-13→F-019 (cross),
D-14→F-024 (cross), D-15→F-016 (cross).

**§E — In-flight work inventory.** Drafted. E-01 through E-14 named.
E.4 has four unrun branch-state checks (E-11 through E-14).

**§F — Baseline metrics.** Drafted. §F.1 cites test-suite (913) and
validate (236/240) from the previous handoff, not re-measured. §F.2 has
a per-prompt-class token table from this session's runs.

**§G — Behavioural byte-diffs.** Drafted. Three goldens re-run:
`po_2144_and_lines.txt` identical; `count_suppliers.txt` and
`suppliers_with_open_pos.txt` diverge only on pod-grown counts and
module-set ordering.

**§H — Probabilistic-behaviour map.** Twelve observations. Four now
closed (three originally on 2026-09-18, plus the §H.1 truncation-metadata
observation closed by F-040). Eight remain as map content, not action
items.

---

## Pending work — three small batches

**Batch 1 — §C.5 confirmation greps.** Five proposed commands for C-02
through C-07. Expected output and the reference "already confirmed" for
each is in §C.1's `Confirm` column. One batch, ~5 commands.

**Batch 2 — §E.4 branch-state checks.** Four `git log` / `git branch`
inspections:
- `git log --oneline phase-4d-ui-api | head` (E-11)
- `git branch -a | grep prompt-18` (E-12)
- `git log hardening-master..fix/overnight-20260904 --oneline` and the
  same for `fix/overnight-batch2` (E-13)
- `git branch --merged hardening-master | grep feat/` (E-14)

**Batch 3 — §C.3 unreachable sweep.** Would need `tests`, `scripts`,
`prompts`, `corpora` bundles read. Each will surface unused imports,
dead helpers, stale prompt entries. This is the only remaining
substantive audit work.

---

## Carry-forward from the 2026-09-11 handoff (still open)

These items were flagged in the previous handoff and are **not closed**
this session. They belong here so a new window does not lose them.

**CF-1 — S1: planner raw-KeyError path.** The prior handoff's S1 is
"planner throws raw KeyError instead of degrading/refusing". This
session's F-006 fixed the specific `get_purchase_order_by_id` +
alpha-OrderNumber crash, but the broader "planner NEVER throws raw"
goal is unverified. F-025 closed the specific PO→Supplier include case
as by-design, but whether any other unsatisfiable-include shape still
raises raw is unmeasured. **Re-open:** run an Intent with an
unsatisfiable include directly and confirm the RefusalError wrap fires
for every shape.

**CF-2 — S2: LLM model silent dependency.** Switching `GEMINI_MODEL`
from `gemini-3.5-flash` to `gemini-3.1-flash-lite` measurably degrades
routing (per the previous handoff: 236/240 → 205/240). Untouched this
session. **Re-open:** consider pinning / enforcing the validated model
in production, or a config-time assertion that the model matches.

**CF-3 — S3: `--generate` freezes classifier flakiness.** `--generate`
runs each prompt through the non-deterministic classifier ONCE and
writes that as the corpus `module` value. A fix direction from the
previous handoff: a corpus-consistency guard (generate-time or a test)
— "structurally identical prompts must have identical expected module
sets". Untouched this session. **Re-open:** design and land the guard.

**CF-4 — Overnight register verification pass.** `docs/spire_overnight_findings.md`
(last updated 2026-08-14) still lists ~14 issues as open/verified, not
re-verified against current code. This session closed three of the
likely candidates incidentally (nondeterminism class: F-022, F-023,
F-024). The register itself has not been re-read. **Re-open:** sweep the
register and mark which issues still reproduce.

---

## Pod-state observations to carry forward

- **Pod growth is real and ongoing.** Supplier count: 431 (golden
  capture) → 450–455 (audit) → 593 → 600 → 620 → 656 (this session).
  PO count: 15,839 (2026-08-04) → 17,740 (today's aggregation).
  Golden files and pod-dependent counts will keep drifting.
- **Module-set ordering varies run-to-run** without affecting the
  answer. `classify_modules` preserves the model's returned order.
  Confirmed in F-023, F-032, and §G's diff. Goldens that capture the
  `Router:` line will show spurious diffs.
- **Model-prose variance** in `Reason:` lines is real (F-035, F-038).
  Same flavor, same Solution, different Reason text. Not a bug — a
  §H.1-class observation.
- **The parser prompt is at its token ceiling.** Any sysprompt edit
  risks degenerate generation. A parser-prompt fix needs a full 12-set
  `--validate` re-run.
- **The pod (eqjz) is the current demo pod.** `personas.yaml` holds
  credentials; Spire reads `personas.yaml` ONLY. A wrong pod usually
  means the MCP server is stale — restart after any change under
  `src/spire/mcp_server/`.

---

## Context bundles — how to request code

Code is shared as **bundles**, not individual files. `context_bundles.yaml`
at the repo root defines them; `build_context.py` builds them into
`context_out/context_<name>.md`. The bundles that matter for audit work:

- **`graph_kg`** — KG schema, loader, rebuild scripts, executor, fusion client.
- **`parser_planner`** — draft, parser, router, context_assembly, vocabulary, planner, plan_builders, lookup, registries, cached_llm, prompt_cache.
- **`parser_context`** — every `.sysprompt` block plus `order.manifest` and `classifier_menu.sysprompt`.
- **`mcp_server_tools`** — the 34 MCP tools and the server.
- **`synthesizer`** — synthesizer, ar, p2p, aggregation, response_validation, local_summary, ranking_summary, prompts, pipeline.

To build all of them:

```
python build_context.py --all
```

To build one:

```
python build_context.py parser_planner
```

Output lands in `context_out/`. Ask the user for the bundle (not the file);
they will share it. A full explainer — what a bundle is, the complete
list, per-bundle contents, and how to build each — lives in
`docs/developer/context_bundles.md`.

---

## Working-style reminders specific to this audit

- **One command at a time.** Never a block of commands. If a command
  fails mid-block, the rest fire against an unintended state.
- **No nested code fences.** `~~~` outer, ` ``` ` inner.
- **Complete files, not fragments.** Produce the whole block, not
  "insert this between X and Y".
- **Approval before generating.** Ask before writing code or long
  findings; a one-line confirmation is enough.
- **S0–S8 walk, every finding.**
- **Three update disciplines, three documents.** Doc A is frozen
  (status and deviation notes only). The phase-1 audit is a working
  document — rows close in place. The findings log is append-only —
  corrections cite old IDs.
- **Every pasteable edit ships with its verification commands.**
- **The user's audit file is UTF-8 shown under a non-UTF-8 terminal
  encoding.** `§` renders as `¬ß`, `—` as `‚Äî`. Search strings must
  match the bytes the file on disk carries. In practice this means
  matching on ASCII-only fragments where possible.

---

## What to read first, in order

1. This file.
2. `docs/audit/phase-1-audit.md` — top paragraph for state, then §A.1,
   §B.6, §C.1/C.2, §D.1, §E.1–E.4, §G, §H.1.
3. `docs/audit/findings-log.md` — skim F-001 through F-040.
4. `docs/spire-robustness/WORKING_STYLE.md` — the evidence standard's
   home.

---

## First steps in the new window

1. **Confirm ground truth.** `git log --oneline -3` (should be on the
   audit branch). `pytest -q` (expect 913 passed, 18 deselected — per
   the previous handoff; not re-run this session). MCP server up.
2. **Run Batch 1** (§C.5 greps) — five commands, one batch.
3. **Run Batch 2** (§E.4 branch checks) — four commands, one batch.
4. **Update the audit's §C.1 and §E.4 rows** from the results, using
   the same search-and-replace pattern with single-line anchors.
5. **Address the four carry-forward items (CF-1 through CF-4)** — each
   is a small investigation. CF-3 (corpus-consistency guard) is the
   most self-contained.
6. **Decide on Batch 3** — read the four remaining bundles and extend
   §C, or leave §C partial and close the audit, or move to Phase 2.

---

*End of handoff.*
