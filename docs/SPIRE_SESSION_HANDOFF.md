# Spire — Session Handoff (2026-07-30, late evening)

Supersedes the 2026-07-30 evening handoff.

---

## Who / what

Continuing **Spire** — AI-native NL query over Oracle Fusion Cloud (P2P +
AR). Deterministic KG pipeline: parse → plan → execute → synthesize, two
LLM boundaries only (parser, synthesizer). Tool selection is a KG lookup,
not an LLM judgement. Not an agent architecture.

Repo `github.com/bhagavansprasad/spire`, working dir `~/pocs/spire`, pod
`fa-esll-dev37-saasfademo1.ds-fa.oraclepdemos.com`, creds in
`personas.yaml` (gitignored).

**On `master`, clean, 762 tests passing.** Four branches merged this
session.

---

## What this session did

**Phase 1 complete** (UX-05, OBS-01, OBS-02) and **Phase 2's UX-01
complete**. Four branches:

| Branch | Covers |
|---|---|
| `phase-1-diagnostic-flags` | UX-05 + OBS-01 — quiet default, per-component flags |
| `phase-1-config-precedence` | OBS-02 — pyproject.toml, env, CLI precedence |
| `phase-2-refusal-messages` | UX-01 — the refusal rewrite |
| `phase-2-refusal-tests` | its tests and three tripwires |

Full detail is in `docs/spire_enhancement_status.md` §D (Phase 1), §E
(Phase 2 discovery), §F (Phase 2 build). **Read §F9 first if you read
nothing else.**

### Phase 1 — controllable diagnostics

`stdout` carries the answer; `stderr` carries everything else.
`run_graph.py --prompt "..." 2>/dev/null` yields the answer alone.

Mechanism is stdlib `logging`, one logger per component under `spire.`.
Six OBS-01 flags plus `--show-all`. Settable in four layers, later
beating earlier: defaults → `[tool.spire.diagnostics]` in
`pyproject.toml` → `SPIRE_SHOW_*` → command line.

`spire.progress` and `spire.summary` are never gated — a ~16s run needs
progress feedback. Both on stderr, so stdout is unaffected.

**Never touches the root logger.** langchain, httpx, oracledb and fastmcp
all log at DEBUG; flipping root to see the planner would bury the answer.

New dependency: `pydantic-settings`.

Verified with `scripts/flag_matrix.sh` — 64 flag combinations plus 3
controls, all 67 stdout hashes identical, every flag lighting only its
own component.

### Phase 2 — UX-01, refusal messages

Refusals were read as breakage, by SMEs and by the developer reading nine
in a row. **One root cause.** `derive_flavor` scanned the model's reason
prose for capitalized words and treated unrecognised ones as entity
names. It matched `To`, `ID`, `Filtering` and `Receipt` — UNKNOWN_ENTITY
for four of four measured refusals, and unstable across incidental
rewording ("The request" vs "The question" flipped the flavor).

That produced both faults: the message listed a record type as supported
and then denied it, and the model's accurate reason was discarded.

**The model's diagnosis was correct all along.** The scan is deleted, not
repaired. The model now states `unanswerable_kind` directly, plus
`unanswerable_entity` for wording only (`target_entity` must stay empty —
that is the silent-rewrite guard).

Messages are three lines:

```
Reason:   I can look up receipts, but not by customer account number.
Solution: Scope them by customer or site instead — those I can do.
Example:  receipts for ABC Application Software
```

New flavor `MISSING_IDENTIFIER`. `UNKNOWN_ENTITY` splits three ways:
absent, present-but-not-a-query-root, and no entity identified.

`run_prompt_set.py` now takes the same flags as `run_graph.py` —
**reversing a Phase 1 decision** to leave it ungated.

---

## Numbers to carry forward

| Metric | Before | After |
|---|---|---|
| Tests passing | 607 | **762** |
| Deselected | 17 | **18** (one new integration-marked KG check) |
| Lifecycle 31-prompt set | 31/31 | **31/31** |
| `05_refusals` set | 9/9 | **9/9**, every message rewritten |
| Parse tokens (lifecycle path) | ~8,805–8,819 | **unchanged, 8,812 on the reference prompt** |

**Two schema fields were added to `DraftIntent` and parse input tokens
did not move.** Gemini does not count the structured-output schema in
`input_tokens`. That means the parse-token baseline is BLIND to schema
growth and cannot be used to police changes to `draft.py`.

The requirements document's §3 baseline (16.0s, 12,230 tokens) is
unchanged.

---

## Where the plan stands

`docs/spire_enhancement_status.md` is the living record; the requirements
doc is the frozen spec.

- **Phase 0** — done, merged.
- **Phase 1** (UX-05, OBS-01, OBS-02) — **done, merged.**
- **Phase 2** (UX-01, UX-02, UX-03) — **UX-01 done. UX-02 and UX-03 not
  started.**
- **Phases 3–12** — not started.
- **DEC-01, DEC-02, DEC-03** — untouched.
- **`server.py` registration pattern** — still open, still blocking the
  `server.py` maintainability split.

**The status doc's Phase 1 section (§D) should be pruned to
decisions-only** before Phase 2 grows further. That is the file's own
rule and it is now 984 lines.

---

## Next: UX-02 and UX-03

**UX-02 — narrowing guidance for over-broad queries.** Adjacent to what
was just built; the Solution/Example machinery is there.

**UX-03 — truncation disclosure.** Connects to three carried-forward
defects and is the higher-value one. Note it is **already half-built**:
`invoices for Lee Supplies` discloses "25 of 1348" in its narration and
prints a `Truncation:` block. The open defect is about TOTALS computed
over the sample, which is a different shape — and the SME report's own
cash-trends screenshot shows exactly that failure, building a
month-over-month trend narrative on 25 receipts and stating it as fact.

---

## Carried forward — still open

**Can put a wrong number in front of someone**

- **Invoice total over a sample.** A total summed over 25 of 1,348 rows,
  stated as fact.
- **"Country" returns a full address.**
- **Only the FIRST address is shown**, silently, for suppliers with many.
- **`StandardReceipt` and `AccountReceipt` model the same receipts** with
  disagreeing counts, and both are routable.
- **An aggregate stopped at exactly 50 pages / 25,000 rows** and reported
  `Synthesized answer: 0 record(s)`. Looks like `MAX_PAGES` rather than
  the end of the data — **unconfirmed**, nobody has checked whether the
  pod holds more.

**Pinned bugs**

- **`search_standard_receipts` can never report `truncated=True`.**
- **W7 — "supplier sites" mis-parses as addresses.**

**Found this session, not fixed**

- **`get_account_receipt_applications` is unreachable from natural
  language.** Tool exists and is registered; every phrasing refuses.
- **"Show invoice lines for invoice X" returns a count, not the lines.**
- **"Account activity summary for top accounts" silently re-routes** to
  an exposure ranking of the top 10 of 435 accounts.
- **Two `Answer:` headers on column queries** —
  `_format_synthesized(summary_only=True)` and `_format_projected_table`
  each emit one. In `display_formatters.py`.

**Housekeeping**

- Address flattening exists twice (`_address_info` in `p2p.py`).
- **Remote branch prune still pending** — now ~8 merged branches with
  remote copies, out of ~31 total.
- ~~17 tests DESELECTED by an unexamined marker filter~~ — **closed.**
  Explained by `addopts = "-m 'not integration'"` plus the `integration`
  marker in `pyproject.toml`. Deliberate, not a gap.

---

## Hard-won lessons (carried + new)

**Curl before code.** Unchanged, not exercised this session.

**A claim from inspection is not a finding.** Stated before; this session
is the strongest evidence yet. Every defect in Phase 2 — five of them —
was found by running something and reading output. **None was found by
reading code.** The prose scan, a regression in a field description, 14
missing entity labels, a guard testing the wrong predicate, and an
example that failed when typed.

**An example in a prompt is an instruction.** Adding
`unanswerable_kind` included the counter-example "standard receipts for
account 25750 — account number is not a receipt filter". That prompt then
STOPPED refusing: it mapped the account number onto `customer_name` and
returned zero rows. Deterministic, three for three. A refusal became a
silent empty result, which is strictly worse. A counter-example close
enough to something real teaches the opposite of what it says.

**A test that exercises the clean case is not a test of the case people
write.** `test_show_all_from_the_file` wrote a file containing ONLY
`show_all = true`, so it never caught that `show_all` is a no-op when the
file spells out every key — which is exactly how the committed template
was written.

**Deliver the complete file, never a fragment.** A
`[tool.spire.diagnostics]` section handed over as a fragment with
"replace the section you have" lost `[project]`, `[build-system]` and
`[tool.pytest.ini_options]`. The next full suite reported 33 failures
across 676 seconds, none real. The tell was `17 deselected` vanishing
from the summary line.

**Verify what you promise a user.** Refusal examples were written from
what looked plausible. One refused — and it was offered as the fix for
that very refusal, in three tables.

**A tally is not a verdict.** `05_refusals` reported 9/9 clean while
three of the nine messages were wrong. The harness says so itself, at the
bottom of every run.

---

## Reference

- KG rebuild: `python scripts/rebuild_kg.py` — always from scratch.
- **Restart the MCP server after ANY change under `src/spire/mcp_server/`.**
- Full suite: `python -m pytest -q` — **762 passed, 18 deselected, 1
  xfailed** is the current clean baseline. ~2.5 minutes.
- Lifecycle regression: `python scripts/run_prompt_set.py --prompt-file
  scripts/prompts/08_lifecycle.txt` — 31/31.
- Refusal wording: `--prompt-file scripts/prompts/05_refusals.txt` — 9/9,
  and **read the messages**, not the tally.
- Refusal examples: `--prompt-file scripts/prompts/10_refusal_examples.txt`
  — all 18 must ANSWER. A refusal there is a bug in `capability.py`.
- Flag matrix: `bash scripts/flag_matrix.sh` — ~17 minutes, 67 LLM calls.
  Run when the flag surface changes, not routinely.
- Diagnostics: `--show-planner`, `--show-all`, `--no-show-tokens`, etc.
  Same flags on both runners. `SPIRE_SHOW_PLANNER=1` for a machine
  default; `[tool.spire.diagnostics]` for a committed one.
- Pod quirks: `docs/spire_fusion_endpoints_reference.md` — nothing new
  added this session (no pod-side work).

**Concurrency:** Spire is single-threaded and sequential — `asyncio` for
non-blocking I/O, no `gather`, no threads. Two prompts from two terminals
DO run safely in parallel: separate client processes, and the MCP server
holds only a read-only `_persona` with a fresh `httpx.AsyncClient` per
tool call. Verified with two simultaneous prompts, no bleed. Caveat: that
is the easy case, not a load test. Concurrent Fusion calls are PRF-05,
phase 7.

**Files to share when starting the next task:** this handoff,
`docs/spire_enhancement_requirements.md`, `docs/spire_enhancement_status.md`,
plus the code files the task touches. Every file in this project drifts
between sessions — re-sharing is the standing rule, not an exception.
